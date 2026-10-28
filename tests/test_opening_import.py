"""Tests for bulk opening-balance CSV import. No network, no mocks."""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import db
from app import opening_import as opening


class OpeningImportTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Bulk Co", "bulk", state_code="27")
        self.asset = acct.create_account(
            self.conn, self.t, "1601", "Bulk Asset", "asset", group_code="other_asset")
        self.liability = acct.create_account(
            self.conn, self.t, "2601", "Bulk Liability", "liability",
            group_code="other_liability")
        self.expense = acct.create_account(
            self.conn, self.t, "6071", "Bulk Expense", "expense",
            group_code="other_expense")

    def tearDown(self):
        self.conn.close()

    def test_01_valid_preview_parses_sides_amounts_and_notes(self):
        text = (
            "code,side,amount,as_of,note\n"
            "1601,Dr,\"1,234.56\",2026-04-01,Asset opening\n"
            "2601,credit,1000.00,2026-04-01,Liability opening\n"
        )
        result = opening.preview(self.conn, self.t, text, "2026-04-01")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["valid_count"], 2)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["total_debit"], 123456)
        self.assertEqual(result["total_credit"], 100000)
        self.assertEqual(result["rows"][0]["account_name"], "Bulk Asset")
        self.assertEqual(result["rows"][0]["side"], "debit")
        self.assertEqual(result["rows"][0]["note"], "Asset opening")

    def test_02_duplicate_missing_and_bad_rows_are_all_reported(self):
        text = (
            "code,side,amount\n"
            "1601,debit,10.00\n"
            "1601,credit,20.00\n"
            "9999,debit,5.00\n"
            "6071,sideways,not-a-number\n"
        )
        result = opening.preview(self.conn, self.t, text, "2026-04-01")
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(len(result["errors"]), 3)
        messages = " ".join(e["message"] for e in result["errors"])
        self.assertIn("Duplicate account code", messages)
        self.assertIn("not found in this business", messages)
        self.assertIn("Side must be", messages)
        self.assertIn("amount", messages.lower())

    def test_03_existing_opening_and_future_date_are_rejected(self):
        acct.set_opening_balance(
            self.conn, self.t, self.asset, "2026-04-01", 10000, "debit")
        text = "code,side,amount,as_of\n1601,debit,100.00,2026-04-01\n"
        result = opening.preview(self.conn, self.t, text, "2026-04-01")
        self.assertEqual(result["valid_count"], 0)
        self.assertIn("already set", result["errors"][0]["message"])

        text = "code,side,amount,as_of\n2601,credit,100.00,2099-04-01\n"
        result = opening.preview(self.conn, self.t, text, "2026-04-01")
        self.assertEqual(result["valid_count"], 0)
        self.assertIn("future", result["errors"][0]["message"])

    def test_04_date_after_first_activity_is_rejected(self):
        acct.post_journal(
            self.conn, self.t, "2026-05-10", "Expense paid",
            [
                {"account_id": self.expense, "debit": 5000, "credit": 0},
                {"account_id": self.liability, "debit": 0, "credit": 5000},
            ],
            source_type="manual", created_by=None,
        )
        text = "code,side,amount,as_of\n6071,debit,100.00,2026-05-11\n"
        result = opening.preview(self.conn, self.t, text, "2026-04-01")
        self.assertEqual(result["valid_count"], 0)
        self.assertIn("first posted entry", result["errors"][0]["message"])

    def test_05_post_is_balanced_audited_and_keeps_notes(self):
        text = (
            "code,side,amount,as_of,note\n"
            "1601,debit,1500.50,2026-04-01,Asset migration\n"
            "2601,credit,500.25,2026-04-01,Liability migration\n"
        )
        result = opening.post_import(
            self.conn, self.t, text, "2026-04-01", "openings.csv", None)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["total_debit"], 150050)
        self.assertEqual(result["total_credit"], 50025)

        entries = self.conn.execute(
            "SELECT entry_no, narration, source_type FROM journal_entry"
            " WHERE tenant_id=? AND source_type='opening' ORDER BY entry_no", (self.t,)
        ).fetchall()
        self.assertEqual(len(entries), 2)
        self.assertIn("Asset migration", entries[0]["narration"])
        self.assertIn("Liability migration", entries[1]["narration"])
        self.assertTrue(acct.trial_balance(self.conn, self.t, "2026-10-26")["balanced"])

        balances = {a["code"]: a["balance"] for a in acct.account_balances(
            self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["1601"], 150050)
        self.assertEqual(balances["2601"], -50025)
        self.assertEqual(balances["3200"], -100025)
        audit = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE tenant_id=? AND action='opening_balance.set'",
            (self.t,)).fetchone()["c"]
        bulk = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE tenant_id=? AND"
            " action='opening_balance.bulk_import'", (self.t,)).fetchone()["c"]
        self.assertEqual(audit, 2)
        self.assertEqual(bulk, 1)

    def test_06_one_bad_row_posts_nothing(self):
        text = (
            "code,side,amount\n"
            "1601,debit,1500.00\n"
            "9999,debit,500.00\n"
        )
        with self.assertRaises(opening.OpeningImportError) as ctx:
            opening.post_import(self.conn, self.t, text, "2026-04-01", "bad.csv", None)
        self.assertIn("Nothing was posted", ctx.exception.message)
        self.assertIsNotNone(ctx.exception.preview)
        count = self.conn.execute(
            "SELECT COUNT(*) c FROM journal_entry WHERE tenant_id=? AND source_type='opening'",
            (self.t,)).fetchone()["c"]
        self.assertEqual(count, 0)

    def test_07_failure_after_first_entry_rolls_back_the_whole_import(self):
        real = acct.set_opening_balance
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise acct.AccountingError("TEST_FAIL", "simulated second-row failure")
            return real(*args, **kwargs)

        text = (
            "code,side,amount\n"
            "1601,debit,1500.00\n"
            "2601,credit,500.00\n"
        )
        with mock.patch.object(acct, "set_opening_balance", side_effect=flaky):
            with self.assertRaises(acct.AccountingError):
                opening.post_import(self.conn, self.t, text, "2026-04-01", "race.csv", None)

        count = self.conn.execute(
            "SELECT COUNT(*) c FROM journal_entry WHERE tenant_id=? AND source_type='opening'",
            (self.t,)).fetchone()["c"]
        self.assertEqual(count, 0)
        equity = self.conn.execute(
            "SELECT COUNT(*) c FROM account WHERE tenant_id=? AND name=?",
            (self.t, acct.OPENING_EQUITY_NAME)).fetchone()["c"]
        self.assertEqual(equity, 0)
        bulk = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE tenant_id=? AND"
            " action='opening_balance.bulk_import'", (self.t,)).fetchone()["c"]
        self.assertEqual(bulk, 0)

    def test_08_codes_are_tenant_scoped_and_template_is_parseable(self):
        other = db.create_tenant(self.conn, "Other Co", "other", state_code="27")
        acct.create_account(self.conn, other, "9999", "Other Only", "asset",
                            group_code="other_asset")
        result = opening.preview(
            self.conn, self.t, "code,side,amount\n9999,debit,10.00\n", "2026-04-01")
        self.assertEqual(result["valid_count"], 0)
        self.assertIn("not found", result["errors"][0]["message"])

        parsed = opening.parse_csv(opening.template_csv(), "2026-04-01")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["code"], "1000")
        self.assertEqual(parsed[0]["side"], "debit")
        self.assertEqual(parsed[0]["amount_text"], "25000.00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
