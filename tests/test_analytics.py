"""Analytics semantic-layer tests: actuals, reconciliation and tenant isolation."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import analytics, db


class AnalyticsTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Analytics Co", "analytics", state_code="27")
        self.tenant = self.conn.execute("SELECT * FROM tenant WHERE id=?", (self.t,)).fetchone()

    def tearDown(self):
        self.conn.close()

    def post(self, debit_code: str, credit_code: str, amount: int,
             entry_date: str = "2026-05-10", narration: str = "Test"):
        return acct.post_journal(
            self.conn, self.t, entry_date, narration,
            [{"account_id": db.account_id(self.conn, self.t, debit_code),
              "debit": amount, "credit": 0},
             {"account_id": db.account_id(self.conn, self.t, credit_code),
              "debit": 0, "credit": amount}],
            "manual")

    def customer(self, name: str = "Analytics Customer") -> str:
        cid = db.new_id()
        self.conn.execute(
            "INSERT INTO customer (id, tenant_id, name, state_code, created_at) VALUES (?,?,?,?,?)",
            (cid, self.t, name, "27", db.now()))
        return cid

    def item(self, sku: str = "AN-1") -> str:
        iid = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise,"
            " tax_rate_bp, stock_milli, track_stock, revenue_code)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (iid, self.t, sku, "Analytics item", 10000, 6000, 1800, 10000, 1, "4000"))
        return iid

    def test_catalog_is_actuals_only_and_has_stable_metric_keys(self):
        cat = analytics.catalog()
        self.assertEqual(cat["schema_version"], analytics.SCHEMA_VERSION)
        keys = {m["key"] for m in cat["metrics"]}
        for key in ("revenue_paise", "expense_paise", "net_profit_paise",
                    "cash_and_bank_paise", "receivable_paise", "payable_paise",
                    "gst_net_payable_paise", "trial_balance_balanced"):
            self.assertIn(key, keys)
        for metric in cat["metrics"]:
            self.assertEqual(metric["kind"], "actual")
            self.assertEqual(metric["permission"], "report.view")
            self.assertTrue(metric["formula"])
            self.assertTrue(metric["drilldown"])

    def test_snapshot_matches_pnl_and_balanced_checks(self):
        self.post("1000", "4000", 100000, "2026-04-10", "Sale")
        self.post("6000", "1000", 40000, "2026-05-10", "Rent")
        snap = analytics.snapshot(self.conn, self.tenant, "2026-04-01", "2026-06-30")
        self.assertEqual(snap["metrics"]["revenue_paise"], 100000)
        self.assertEqual(snap["metrics"]["expense_paise"], 40000)
        self.assertEqual(snap["metrics"]["net_profit_paise"], 60000)
        self.assertEqual(snap["metrics"]["cash_and_bank_paise"], 60000)
        self.assertTrue(snap["metrics"]["trial_balance_balanced"])
        self.assertTrue(snap["metrics"]["balance_sheet_balanced"])
        self.assertEqual(snap["checks"]["trial_balance_difference_paise"], 0)
        self.assertEqual(snap["checks"]["unbalanced_entries"], 0)
        self.assertEqual(snap["freshness"]["journal_entries"], 2)
        self.assertEqual(snap["freshness"]["last_entry_date"], "2026-05-10")
        self.assertIn("Actuals only", " ".join(snap["notes"]))

    def test_monthly_series_zero_fills_missing_months(self):
        self.post("1000", "4000", 100000, "2026-04-10", "Sale")
        self.post("6000", "1000", 40000, "2026-05-10", "Rent")
        series = analytics.monthly_series(self.conn, self.tenant, "2026-04-01", "2026-06-30")
        self.assertEqual([m["month"] for m in series["months"]],
                         ["2026-04", "2026-05", "2026-06"])
        self.assertEqual(series["months"][0]["revenue_paise"], 100000)
        self.assertEqual(series["months"][1]["expense_paise"], 40000)
        self.assertEqual(series["months"][2]["revenue_paise"], 0)
        self.assertEqual(series["total_profit_paise"], 60000)

    def test_expense_breakdown_and_customer_ranking(self):
        self.post("6000", "1000", 40000, "2026-05-10", "Rent")
        customer = self.customer()
        item = self.item()
        acct.create_invoice(
            self.conn, self.t, customer, "2026-05-15", "27",
            [{"item_id": item, "qty": 1000, "unit_price": 10000,
              "discount": 0, "tax_rate_bp": 1800}],
            idempotency_key="analytics-invoice")
        breakdown = analytics.expense_breakdown(self.conn, self.tenant,
                                                "2026-04-01", "2026-06-30")
        self.assertEqual(breakdown["total_paise"], 46000)
        self.assertEqual(breakdown["rows"][0]["code"], "6000")
        customers = analytics.top_customers(self.conn, self.tenant,
                                            "2026-04-01", "2026-06-30")
        self.assertEqual(customers[0]["name"], "Analytics Customer")
        self.assertEqual(customers[0]["amount_paise"], 11800)

    def test_tenant_isolation_and_date_validation(self):
        other = db.create_tenant(self.conn, "Other Co", "other-analytics", state_code="27")
        other_row = self.conn.execute("SELECT * FROM tenant WHERE id=?", (other,)).fetchone()
        self.post("1000", "4000", 100000)
        snap = analytics.snapshot(self.conn, other_row, "2026-04-01", "2026-06-30")
        self.assertEqual(snap["metrics"]["revenue_paise"], 0)
        self.assertEqual(analytics.top_customers(self.conn, other_row,
                                                 "2026-04-01", "2026-06-30"), [])
        with self.assertRaises(analytics.AnalyticsError) as ctx:
            analytics.overview(self.conn, self.tenant, "bad-date", "2026-06-30")
        self.assertEqual(ctx.exception.code, "BAD_DATE")
        with self.assertRaises(analytics.AnalyticsError) as ctx:
            analytics.overview(self.conn, self.tenant, "2026-07-01", "2026-06-30")
        self.assertEqual(ctx.exception.code, "BAD_PERIOD")

    def test_analytics_views_reconcile_to_journal_rows(self):
        self.post("1000", "4000", 100000)
        self.post("6000", "1000", 40000)
        views = {r["name"] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'")}
        self.assertIn("v_analytics_journal", views)
        self.assertIn("v_analytics_monthly", views)
        lines = self.conn.execute(
            "SELECT COUNT(*) c FROM journal_line WHERE tenant_id=?", (self.t,)).fetchone()["c"]
        view_lines = self.conn.execute(
            "SELECT COUNT(*) c FROM v_analytics_journal WHERE tenant_id=?", (self.t,)).fetchone()["c"]
        self.assertEqual(lines, view_lines)
        monthly = self.conn.execute(
            "SELECT COALESCE(SUM(income_paise),0) income, COALESCE(SUM(expense_paise),0) expense"
            " FROM v_analytics_monthly WHERE tenant_id=?", (self.t,)).fetchone()
        self.assertEqual(monthly["income"], 100000)
        self.assertEqual(monthly["expense"], 40000)


if __name__ == "__main__":
    unittest.main()
