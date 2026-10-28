"""Grounded insight layer tests: actuals, citations and no fabricated forecasts."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import analytics, db, insights


class InsightsTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Insight Co", "insight-co", state_code="27")
        self.tenant = self.conn.execute("SELECT * FROM tenant WHERE id=?", (self.t,)).fetchone()
        self.post("1000", "4000", 100000, "2026-04-10", "Sale")
        self.post("6000", "1000", 40000, "2026-05-10", "Rent")

    def tearDown(self):
        self.conn.close()

    def post(self, debit_code: str, credit_code: str, amount: int,
             entry_date: str, narration: str):
        return acct.post_journal(
            self.conn, self.t, entry_date, narration,
            [{"account_id": db.account_id(self.conn, self.t, debit_code),
              "debit": amount, "credit": 0},
             {"account_id": db.account_id(self.conn, self.t, credit_code),
              "debit": 0, "credit": amount}],
            "manual")

    def test_insights_are_grounded_and_actual_only(self):
        payload = insights.grounded(self.conn, self.tenant, "2026-04-01", "2026-06-30")
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["engine"], "deterministic_rules_v1")
        self.assertFalse(payload["generative_ai"])
        self.assertTrue(payload["actuals_only"])
        self.assertFalse(payload["forecast_included"])
        self.assertIn("no external model was called", payload["summary"].lower())
        keys = {o["key"] for o in payload["observations"]}
        for key in ("net_profit_margin", "revenue_minus_expenses", "largest_expense_ledger",
                    "overdue_receivable_share", "gst_net_payable", "journal_checks",
                    "open_documents", "freshness"):
            self.assertIn(key, keys)
        for observation in payload["observations"]:
            self.assertEqual(observation["kind"], "actual")
            self.assertTrue(observation["basis"])
            self.assertTrue(observation["drilldown"])
            self.assertIn("source", observation)
        margin = next(o for o in payload["observations"] if o["key"] == "net_profit_margin")
        self.assertEqual(margin["value_bp"], 6000)
        self.assertEqual(margin["value_text"], "60.00%")
        self.assertIn("net_profit_paise / revenue_paise", margin["basis"])
        profit = next(o for o in payload["observations"] if o["key"] == "revenue_minus_expenses")
        self.assertEqual(profit["value_paise"], 60000)

    def test_empty_period_does_not_invent_margin_or_expense(self):
        payload = insights.grounded(self.conn, self.tenant, "2025-01-01", "2025-02-28")
        margin = next(o for o in payload["observations"] if o["key"] == "net_profit_margin")
        self.assertEqual(margin["value_bp"], None)
        self.assertEqual(margin["value_text"], "not generated")
        expense = next(o for o in payload["observations"] if o["key"] == "largest_expense_ledger")
        self.assertEqual(expense["value_text"], "not generated")
        self.assertIn("No revenue actuals", payload["summary"])

    def test_tenant_isolation_and_bad_date(self):
        other = db.create_tenant(self.conn, "Other Insight", "other-insight", state_code="27")
        other_row = self.conn.execute("SELECT * FROM tenant WHERE id=?", (other,)).fetchone()
        payload = insights.grounded(self.conn, other_row, "2026-04-01", "2026-06-30")
        margin = next(o for o in payload["observations"] if o["key"] == "net_profit_margin")
        self.assertEqual(margin["value_text"], "not generated")
        with self.assertRaises(analytics.AnalyticsError) as ctx:
            insights.grounded(self.conn, self.tenant, "bad-date", "2026-06-30")
        self.assertEqual(ctx.exception.code, "BAD_DATE")


if __name__ == "__main__":
    unittest.main()
