"""Account archive and merge behaviour: balances, audit and guard rails."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import bank as bank_mod
from app import db, opening_import


class AccountArchiveTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Archive Co", "archive", state_code="27")
        self.today = date.today().isoformat()

    def tearDown(self):
        self.conn.close()

    def account(self, code: str, name: str, typ: str = "expense",
                group: str = "other_expense", profile=None) -> str:
        return acct.create_account(self.conn, self.t, code, name, typ,
                                   group_code=group, profile=profile)

    def post(self, debit_id: str, credit_id: str, amount: int, narration: str = "Test"):
        return acct.post_journal(
            self.conn, self.t, self.today, narration,
            [{"account_id": debit_id, "debit": amount, "credit": 0},
             {"account_id": credit_id, "debit": 0, "credit": amount}],
            "manual",
        )

    def test_merge_posts_a_reclassification_and_archives_source(self):
        source = self.account("6071", "Old Office Expenses")
        target = self.account("6072", "Office Expenses")
        cash = db.account_id(self.conn, self.t, "1000")
        self.post(source, cash, 100000)
        self.post(target, cash, 50000)

        result = acct.merge_accounts(self.conn, self.t, source, target,
                                     "Duplicate office-expense ledger", merged_by="u1")

        source_row = self.conn.execute("SELECT * FROM account WHERE id=?", (source,)).fetchone()
        target_row = self.conn.execute("SELECT * FROM account WHERE id=?", (target,)).fetchone()
        entry = self.conn.execute(
            "SELECT * FROM journal_entry WHERE id=?", (result["entry_id"],)).fetchone()
        lines = self.conn.execute(
            "SELECT * FROM journal_line WHERE entry_id=? ORDER BY line_no",
            (result["entry_id"],)).fetchall()
        audit = self.conn.execute(
            "SELECT * FROM audit_log WHERE action='account.merge'"
            " AND target_id=? ORDER BY created_at DESC LIMIT 1", (source,)).fetchone()

        self.assertEqual(source_row["status"], "archived")
        self.assertEqual(source_row["merged_into_id"], target)
        self.assertEqual(target_row["status"], "active")
        self.assertEqual(acct.account_balance(self.conn, self.t, source), 0)
        self.assertEqual(acct.account_balance(self.conn, self.t, target), 150000)
        self.assertEqual(entry["source_type"], "merge")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["credit_paise"], 100000)
        self.assertEqual(lines[1]["debit_paise"], 100000)
        self.assertIn("Duplicate office-expense ledger", entry["narration"])
        self.assertIn('"items_repointed": 0', audit["meta"])
        self.assertTrue(acct.trial_balance(self.conn, self.t)["balanced"])

        pnl = acct.profit_and_loss(self.conn, self.t, "0000-01-01", self.today)
        self.assertEqual(pnl["total_expense"], 150000)

        with self.assertRaises(acct.AccountingError) as ctx:
            self.post(source, cash, 100)
        self.assertEqual(ctx.exception.code, "ACCOUNT_ARCHIVED")

        restored = acct.restore_account(self.conn, self.t, source, "Merged in error",
                                        restored_by="u1")
        self.assertEqual(restored["merged_into"], target)
        source_row = self.conn.execute("SELECT * FROM account WHERE id=?", (source,)).fetchone()
        self.assertEqual(source_row["status"], "active")
        self.assertIsNone(source_row["merged_into_id"])

    def test_archive_requires_zero_balance_and_protects_controls_and_parties(self):
        zero = self.account("6073", "Obsolete Expense")
        acct.archive_account(self.conn, self.t, zero, "No longer used", archived_by="u1")
        self.assertEqual(
            self.conn.execute("SELECT status FROM account WHERE id=?", (zero,)).fetchone()["status"],
            "archived")
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) c FROM audit_log WHERE action='account.archive' AND target_id=?",
                (zero,)).fetchone()["c"], 1)

        nonzero = self.account("6074", "Still In Use")
        cash = db.account_id(self.conn, self.t, "1000")
        self.post(nonzero, cash, 2500)
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.archive_account(self.conn, self.t, nonzero, "Try")
        self.assertEqual(ctx.exception.code, "ACCOUNT_HAS_BALANCE")
        self.assertIn("25.00", ctx.exception.message)

        with self.assertRaises(acct.AccountingError) as ctx:
            acct.archive_account(self.conn, self.t, cash, "Try")
        self.assertEqual(ctx.exception.code, "SYSTEM_ACCOUNT")

        party = self.account("1327", "Party Ledger", "asset", "receivable")
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.archive_account(self.conn, self.t, party, "Try")
        self.assertEqual(ctx.exception.code, "PARTY_ACCOUNT")

    def test_merge_validates_type_party_and_repoints_items(self):
        income_source = self.account("4090", "Old Sales", "income", "sales")
        income_target = self.account("4091", "Sales", "income", "sales")
        item_id = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, revenue_code)"
            " VALUES (?,?,?,?,?)",
            (item_id, self.t, "ARCHIVE-1", "Archive item", "4090"))
        cash = db.account_id(self.conn, self.t, "1000")
        acct.post_journal(
            self.conn, self.t, self.today, "Sale",
            [{"account_id": cash, "debit": 100000, "credit": 0},
             {"account_id": income_source, "debit": 0, "credit": 100000}],
            "manual")
        acct.merge_accounts(self.conn, self.t, income_source, income_target, "Duplicate sales")
        item = self.conn.execute("SELECT revenue_code FROM item WHERE id=?", (item_id,)).fetchone()
        self.assertEqual(item["revenue_code"], "4091")

        with self.assertRaises(acct.AccountingError) as ctx:
            acct.archive_account(self.conn, self.t, income_target, "Still used by an item")
        self.assertEqual(ctx.exception.code, "ACCOUNT_IN_USE")

        expense = self.account("6075", "Other Expense")
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.merge_accounts(self.conn, self.t, income_target, expense, "Wrong type")
        self.assertEqual(ctx.exception.code, "TYPE_MISMATCH")

        purchases = db.account_id(self.conn, self.t, "5100")
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.merge_accounts(self.conn, self.t, purchases, expense, "System source")
        self.assertEqual(ctx.exception.code, "SYSTEM_ACCOUNT")
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.merge_accounts(self.conn, self.t, expense, purchases, "System target")
        self.assertEqual(ctx.exception.code, "SYSTEM_ACCOUNT")

        future_source = self.account("6077", "Future Expense")
        future_target = self.account("6078", "Future Target")
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        acct.post_journal(
            self.conn, self.t, tomorrow, "Future-dated expense",
            [{"account_id": future_source, "debit": 1000, "credit": 0},
             {"account_id": cash, "debit": 0, "credit": 1000}],
            "manual")
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.merge_accounts(self.conn, self.t, future_source, future_target,
                                "Future activity")
        self.assertEqual(ctx.exception.code, "FUTURE_ACTIVITY")

        cust_a = self.account("1328", "Customer A", "asset", "receivable")
        cust_b = self.account("1329", "Customer B", "asset", "receivable")
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.merge_accounts(self.conn, self.t, cust_a, cust_b, "Different parties")
        self.assertEqual(ctx.exception.code, "PARTY_MISMATCH")

        target_a = self.account("1331", "Customer Target", "asset", "receivable")
        source_a = self.account("1332", "Customer Source", "asset", "receivable")
        target_party = acct._account_party(self.conn, self.t, target_a)[1]
        source_party = acct._account_party(self.conn, self.t, source_a)[1]
        self.conn.execute("DELETE FROM customer WHERE tenant_id=? AND id=?",
                          (self.t, source_party))
        self.conn.execute(
            "UPDATE account_profile SET party_id=? WHERE tenant_id=? AND account_id=?",
            (target_party, self.t, source_a))
        self.conn.execute("UPDATE customer SET account_id=? WHERE tenant_id=? AND id=?",
                          (source_a, self.t, target_party))
        result = acct.merge_accounts(self.conn, self.t, source_a, target_a,
                                     "Duplicate customer ledger")
        self.assertEqual(result["party_repointed"], 1)
        pointer = self.conn.execute(
            "SELECT account_id FROM customer WHERE tenant_id=? AND id=?",
            (self.t, target_party)).fetchone()["account_id"]
        self.assertEqual(pointer, target_a)

    def test_bank_list_hides_archived_accounts_and_targets_stay_compatible(self):
        bank = bank_mod.create_bank_account(
            self.conn, self.t, "1038", "Old Current A/c", "Test Bank",
            "12345678", "TEST0001234")
        bank_id = bank["account_id"]
        other_bank = bank_mod.create_bank_account(
            self.conn, self.t, "1039", "Current A/c", "Test Bank",
            "87654321", "TEST0001234")
        self.assertIn(bank_id, {a["id"] for a in bank_mod.bank_accounts(self.conn, self.t)})
        acct.archive_account(self.conn, self.t, bank_id, "Closed bank account")
        self.assertNotIn(bank_id, {a["id"] for a in bank_mod.bank_accounts(self.conn, self.t)})
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.merge_accounts(self.conn, self.t, bank_id, other_bank["account_id"],
                                "Archived source")
        self.assertEqual(ctx.exception.code, "ACCOUNT_ARCHIVED")
        acct.restore_account(self.conn, self.t, bank_id, "Reopened")
        self.assertIn(bank_id, {a["id"] for a in bank_mod.bank_accounts(self.conn, self.t)})

        acct.archive_account(self.conn, self.t, other_bank["account_id"], "Old target")
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.merge_accounts(self.conn, self.t, bank_id, other_bank["account_id"],
                                "Archived target")
        self.assertEqual(ctx.exception.code, "ACCOUNT_ARCHIVED")
        acct.restore_account(self.conn, self.t, other_bank["account_id"], "Target reopened")

        ordinary = self.account("1530", "Other Asset", "asset", "other_asset")
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.merge_accounts(self.conn, self.t, bank_id, ordinary, "Bank to non-bank")
        self.assertEqual(ctx.exception.code, "BANK_MISMATCH")

        targets = acct.merge_targets(self.conn, self.t, bank_id)
        target_ids = {t["id"] for t in targets}
        self.assertIn(other_bank["account_id"], target_ids)
        self.assertNotIn(bank_id, target_ids)
        self.assertNotIn(ordinary, target_ids)

    def test_legacy_customer_pointer_blocks_archive_without_profile(self):
        account = self.account("1330", "Legacy Customer Ledger", "asset", "other_asset")
        cust = db.new_id()
        self.conn.execute(
            "INSERT INTO customer (id, tenant_id, name, state_code, created_at, account_id)"
            " VALUES (?,?,?,?,?,?)",
            (cust, self.t, "Legacy Customer", "27", db.now(), account))
        with self.assertRaises(acct.AccountingError) as ctx:
            acct.archive_account(self.conn, self.t, account, "Try legacy archive")
        self.assertEqual(ctx.exception.code, "PARTY_ACCOUNT")
        self.assertEqual(acct._account_party(self.conn, self.t, account),
                         ("customer", cust))

    def test_opening_import_rejects_archived_account(self):
        account = self.account("6076", "Archived Opening")
        acct.archive_account(self.conn, self.t, account, "Archived before import")
        preview = opening_import.preview(
            self.conn, self.t, "code,side,amount\n6076,debit,10.00\n",
            self.today)
        self.assertEqual(preview["valid_count"], 0)
        self.assertIn("archived", preview["errors"][0]["message"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
