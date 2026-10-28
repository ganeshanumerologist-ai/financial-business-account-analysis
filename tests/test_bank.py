"""Bank statement parsing, import idempotency, matching and reconciliation."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acc
from app import bank, db

TODAY = "2026-10-24"


class BankBase(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Demo Co", "demo", state_code="27")
        self.bank = db.account_id(self.conn, self.t, "1010")
        self.cash = db.account_id(self.conn, self.t, "1000")
        self.ar = db.account_id(self.conn, self.t, "1100")
        self.expense = db.account_id(self.conn, self.t, "6000")
        self.receipt_line = self.post("Customer receipt", [
            {"account_id": self.bank, "debit": 1180000, "credit": 0, "memo": "In"},
            {"account_id": self.ar, "debit": 0, "credit": 1180000, "memo": "In"},
        ], "receipt", "r-1")
        self.payment_line = self.post("Bank charge", [
            {"account_id": self.expense, "debit": 500000, "credit": 0, "memo": "Out"},
            {"account_id": self.bank, "debit": 0, "credit": 500000, "memo": "Out"},
        ], "expense", "e-1")

    def tearDown(self):
        self.conn.close()

    def post(self, narration, lines, source, key):
        entry = acc.post_journal(self.conn, self.t, TODAY, narration, lines,
                                 source_type=source, idempotency_key=key)
        return self.conn.execute(
            "SELECT id FROM journal_line WHERE entry_id=? AND account_id=? ORDER BY line_no LIMIT 1",
            (entry, self.bank)).fetchone()["id"]

    def import_text(self, text, filename="statement.csv"):
        rows = bank.parse_csv(text)
        return bank.import_statement(self.conn, self.t, self.bank, rows, filename)

    def stmt_id(self, *, credit=None, debit=None):
        if credit is not None:
            row = self.conn.execute(
                "SELECT id FROM bank_statement_line WHERE tenant_id=? AND credit_paise=?",
                (self.t, credit)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT id FROM bank_statement_line WHERE tenant_id=? AND debit_paise=?",
                (self.t, debit)).fetchone()
        return row["id"]


class TestCsvParsing(unittest.TestCase):
    def test_debit_credit_columns_and_dates(self):
        rows = bank.parse_csv(
            "Date,Description,Reference,Debit,Credit,Balance\n"
            "24/10/2026,NEFT CR ACME,NEFT-1,,11800.00,123456.00\n"
            "2026-10-24,BANK CHARGE,CHG-1,50.00,,123406.00\n")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["txn_date"], "2026-10-24")
        self.assertEqual(rows[0]["credit_paise"], 1180000)
        self.assertEqual(rows[0]["debit_paise"], 0)
        self.assertEqual(rows[0]["balance_paise"], 12345600)
        self.assertEqual(rows[1]["debit_paise"], 5000)

    def test_amount_and_dr_cr(self):
        rows = bank.parse_csv(
            "Date,Narration,Amount,Dr/Cr\n"
            "2026-10-24,Receipt,11800,Cr\n"
            "2026-10-24,Payment,5000,Dr\n")
        self.assertEqual(rows[0]["credit_paise"], 1180000)
        self.assertEqual(rows[1]["debit_paise"], 500000)

    def test_withdrawal_deposit_columns(self):
        rows = bank.parse_csv(
            "Txn Date,Particulars,Withdrawal Amt,Deposit Amt\n"
            "24/10/2026,Receipt,,11800\n"
            "24-10-2026,Payment,5000,\n")
        self.assertEqual(rows[0]["credit_paise"], 1180000)
        self.assertEqual(rows[1]["debit_paise"], 500000)

    def test_preamble_and_blank_lines_are_skipped(self):
        rows = bank.parse_csv(
            "My Bank\nAccount 123\n\n"
            "Date,Description,Debit,Credit\n"
            "2026-10-24,Receipt,,100\n\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["credit_paise"], 10000)

    def test_blank_balance_stays_none(self):
        rows = bank.parse_csv(
            "Date,Description,Debit,Credit,Balance\n"
            "2026-10-24,Receipt,,100,\n")
        self.assertIsNone(rows[0]["balance_paise"])

    def test_bad_date_rejected_with_line_number(self):
        with self.assertRaises(bank.BankError) as ctx:
            bank.parse_csv("Date,Description,Debit,Credit\nnot-a-date,X,10,\n")
        self.assertEqual(ctx.exception.code, "BAD_DATE")
        self.assertIn("Line 2", ctx.exception.message)

    def test_missing_header_rejected(self):
        with self.assertRaises(bank.BankError) as ctx:
            bank.parse_csv("hello,world\n1,2\n")
        self.assertEqual(ctx.exception.code, "NO_HEADER")

    def test_empty_rejected(self):
        with self.assertRaises(bank.BankError):
            bank.parse_csv("   ")


class TestImportAndMatch(BankBase):
    CSV = ("Date,Description,Reference,Debit,Credit,Balance\n"
           "2026-10-24,NEFT CR TEST CUSTOMER,NEFT-1,,11800.00,123456.00\n"
           "2026-10-24,BANK CHARGE,CHG-1,5000.00,,118456.00\n")

    def test_import_and_deduplicate(self):
        first = self.import_text(self.CSV)
        self.assertEqual(first["imported"], 2)
        self.assertEqual(first["duplicates"], 0)
        second = self.import_text(self.CSV)
        self.assertEqual(second["imported"], 0)
        self.assertEqual(second["duplicates"], 2)
        count = self.conn.execute(
            "SELECT COUNT(*) c FROM bank_statement_line WHERE tenant_id=?", (self.t,)
        ).fetchone()["c"]
        self.assertEqual(count, 2)

    def test_reconciliation_totals_and_difference(self):
        self.import_text(self.CSV)
        rec = bank.reconciliation(self.conn, self.t, self.bank, "2026-10-01", "2026-10-31")
        self.assertEqual(rec["statement_count"], 2)
        self.assertEqual(rec["statement_net"], 6800 * 100)
        self.assertEqual(rec["ledger_net"], 6800 * 100)
        self.assertEqual(rec["difference"], 0)
        self.assertEqual(rec["unmatched_count"], 2)
        self.assertEqual(len(rec["unmatched_ledger"]), 2)
        self.assertEqual(rec["closing_ledger"], 6800 * 100)

    def test_suggestions_use_exact_amount(self):
        self.import_text(self.CSV)
        suggestions = bank.suggest_matches(self.conn, self.t, self.bank,
                                           "2026-10-01", "2026-10-31")
        self.assertEqual(len(suggestions), 2)
        for item in suggestions:
            self.assertEqual(len(item["candidates"]), 1)
            self.assertEqual(item["best"]["line_id"], item["candidates"][0]["line_id"])
            self.assertEqual(item["best"]["days_apart"], 0)

    def test_manual_match_and_unmatch(self):
        self.import_text(self.CSV)
        sid = self.stmt_id(credit=1180000)
        bank.match_line(self.conn, self.t, sid, self.receipt_line)
        rec = bank.reconciliation(self.conn, self.t, self.bank, "2026-10-01", "2026-10-31")
        self.assertEqual(rec["matched_count"], 1)
        self.assertEqual(rec["unmatched_count"], 1)
        self.assertEqual(len(rec["unmatched_ledger"]), 1)
        self.assertEqual(rec["difference"], 0)
        self.assertEqual(rec["reconciled_difference"], 0)

        bank.unmatch_line(self.conn, self.t, sid)
        rec = bank.reconciliation(self.conn, self.t, self.bank, "2026-10-01", "2026-10-31")
        self.assertEqual(rec["matched_count"], 0)
        self.assertEqual(rec["unmatched_count"], 2)

    def test_auto_match_unambiguous(self):
        self.import_text(self.CSV)
        result = bank.auto_match(self.conn, self.t, self.bank, "2026-10-01", "2026-10-31")
        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["ambiguous"], 0)
        rec = bank.reconciliation(self.conn, self.t, self.bank, "2026-10-01", "2026-10-31")
        self.assertEqual(rec["unmatched_count"], 0)
        self.assertEqual(rec["difference"], 0)

    def test_amount_mismatch_rejected(self):
        self.import_text(
            "Date,Description,Debit,Credit\n2026-10-24,Unknown credit,,999.00\n")
        sid = self.stmt_id(credit=99900)
        with self.assertRaises(bank.BankError) as ctx:
            bank.match_line(self.conn, self.t, sid, self.receipt_line)
        self.assertEqual(ctx.exception.code, "AMOUNT_MISMATCH")

    def test_wrong_bank_account_rejected(self):
        cash_entry = acc.post_journal(
            self.conn, self.t, TODAY, "Cash receipt",
            [{"account_id": self.cash, "debit": 1180000, "credit": 0, "memo": "Cash"},
             {"account_id": self.ar, "debit": 0, "credit": 1180000, "memo": "Cash"}],
            source_type="receipt", idempotency_key="cash-1")
        cash_line = self.conn.execute(
            "SELECT id FROM journal_line WHERE entry_id=? AND account_id=?",
            (cash_entry, self.cash)).fetchone()["id"]
        self.import_text(self.CSV)
        with self.assertRaises(bank.BankError) as ctx:
            bank.match_line(self.conn, self.t, self.stmt_id(credit=1180000), cash_line)
        self.assertEqual(ctx.exception.code, "WRONG_ACCOUNT")

    def test_double_match_rejected(self):
        self.import_text(self.CSV)
        sid = self.stmt_id(credit=1180000)
        bank.match_line(self.conn, self.t, sid, self.receipt_line)
        with self.assertRaises(bank.BankError) as ctx:
            bank.match_line(self.conn, self.t, sid, self.receipt_line)
        self.assertEqual(ctx.exception.code, "ALREADY_MATCHED")

    def test_period_filter(self):
        self.import_text(
            "Date,Description,Debit,Credit\n"
            "2026-09-01,Old receipt,,100.00\n"
            "2026-10-24,New receipt,,200.00\n")
        rec = bank.reconciliation(self.conn, self.t, self.bank, "2026-10-01", "2026-10-31")
        self.assertEqual(rec["statement_count"], 1)
        self.assertEqual(rec["statement_net"], 20000)

    def test_duplicate_ledger_line_cannot_be_matched_twice(self):
        self.import_text(
            "Date,Description,Debit,Credit\n"
            "2026-10-24,Receipt A,,11800.00\n"
            "2026-10-24,Receipt B,,11800.00\n")
        first = self.conn.execute(
            "SELECT id FROM bank_statement_line WHERE tenant_id=? ORDER BY description LIMIT 1",
            (self.t,)).fetchone()["id"]
        second = self.conn.execute(
            "SELECT id FROM bank_statement_line WHERE tenant_id=? ORDER BY description DESC LIMIT 1",
            (self.t,)).fetchone()["id"]
        bank.match_line(self.conn, self.t, first, self.receipt_line)
        with self.assertRaises(bank.BankError) as ctx:
            bank.match_line(self.conn, self.t, second, self.receipt_line)
        self.assertEqual(ctx.exception.code, "ALREADY_MATCHED")


class TestBankAccounts(BankBase):
    def create(self, code="1020", name="HDFC Current A/c", number="50200099998888",
               ifsc="HDFC0001234"):
        return bank.create_bank_account(
            self.conn, self.t, code, name, "HDFC Bank", number, ifsc,
            "Andheri West", "Demo Co")

    def test_create_links_ledger_and_bank_details(self):
        created = self.create()
        row = self.conn.execute(
            "SELECT a.code, a.type, a.group_code, b.bank_name, b.account_number, b.ifsc, b.branch"
            " FROM account a JOIN bank_account b ON b.account_id=a.id"
            " WHERE a.id=?", (created["account_id"],)).fetchone()
        self.assertEqual(row["code"], "1020")
        self.assertEqual(row["type"], "asset")
        self.assertEqual(row["group_code"], "bank")
        self.assertEqual(row["bank_name"], "HDFC Bank")
        self.assertEqual(row["account_number"], "50200099998888")
        self.assertEqual(row["ifsc"], "HDFC0001234")
        self.assertEqual(row["branch"], "Andheri West")
        audit = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE tenant_id=? AND action='bank_account.create'",
            (self.t,)).fetchone()["c"]
        self.assertEqual(audit, 1)

    def test_listing_includes_legacy_and_new_bank_accounts(self):
        self.create()
        accounts = bank.bank_accounts(self.conn, self.t)
        self.assertEqual([a["code"] for a in accounts], ["1010", "1020"])
        self.assertEqual(accounts[1]["bank_name"], "HDFC Bank")

    def test_next_code_skips_used_codes(self):
        self.assertEqual(bank.next_bank_code(self.conn, self.t), "1020")
        self.create()
        self.assertEqual(bank.next_bank_code(self.conn, self.t), "1030")

    def test_duplicate_code_and_bad_ifsc_rejected(self):
        self.create()
        with self.assertRaises(bank.BankError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, "CODE_TAKEN")
        with self.assertRaises(bank.BankError) as ctx:
            self.create(code="1030", number="12345678", ifsc="BADIFSC")
        self.assertEqual(ctx.exception.code, "BAD_IFSC")

    def test_new_bank_account_can_be_reconciled(self):
        created = self.create()
        gl = acc.general_ledger(self.conn, self.t, created["account_id"],
                                "2026-10-01", "2026-10-31")
        self.assertEqual(gl["closing"], 0)
        rec = bank.reconciliation(self.conn, self.t, created["account_id"],
                                  "2026-10-01", "2026-10-31")
        self.assertEqual(rec["difference"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
