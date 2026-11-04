"""Management-report tests: deterministic formulas, reconciliation and isolation."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import db, reports
from app.demo import seed_demo


class ReportsTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        seed_demo(self.conn)
        self.tenant = self.conn.execute(
            "SELECT * FROM tenant WHERE slug='arthivio-demo'").fetchone()

    def tearDown(self):
        self.conn.close()

    def test_catalog_has_66_rows_and_28_working(self):
        cat = reports.catalog()
        self.assertEqual(cat["total"], 66)
        self.assertEqual(cat["working"], 28)
        self.assertEqual(cat["partial"], 1)
        self.assertEqual(cat["planned"], 37)
        working = [r for g in cat["groups"] for r in g["reports"] if r["status"] == "working"]
        self.assertTrue(all(r["route"] for r in working))
        for rid in ("R-104", "R-108", "R-109", "R-202", "R-203",
                    "R-301", "R-401", "R-903", "R-905"):
            row = next(r for r in reports.REPORT_CATALOG if r["id"] == rid)
            self.assertEqual(row["status"], "working", rid)
            self.assertTrue(row["route"], rid)

    def test_cash_flow_reconciles_to_cash_and_bank(self):
        data = reports.cash_flow(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(data["opening"], 0)
        self.assertEqual(data["closing"], 49076000)
        self.assertEqual(data["net_change"], 49076000)
        self.assertEqual(data["bridge_total"], data["net_change"])
        self.assertEqual(data["difference"], 0)
        self.assertEqual(data["cash_accounts"], 2)
        self.assertTrue(data["rows"])
        self.assertTrue(any(c["category"] == "Customer receipts" for c in data["categories"]))

    def test_cash_flow_bridge_includes_custom_ungrouped_liability(self):
        tenant_id = self.tenant["id"]
        custom = acct.create_account(
            self.conn, tenant_id, "9001", "Custom ungrouped liability", "liability",
            group_code="")
        acct.post_journal(
            self.conn, tenant_id, "2026-06-30", "Custom liability receipt",
            [{"account_id": db.account_id(self.conn, tenant_id, "1000"),
              "debit": 700000, "credit": 0},
             {"account_id": custom, "debit": 0, "credit": 700000}],
            "manual")
        data = reports.cash_flow(self.conn, tenant_id, "2026-04-01", "2026-10-31")
        self.assertEqual(data["difference"], 0)
        self.assertEqual(data["bridge_total"], data["net_change"])

    def test_financial_ratios_match_posted_pnl_and_balance_sheet(self):
        data = reports.financial_ratios(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        inputs = data["inputs"]
        pnl = acct.profit_and_loss(self.conn, self.tenant["id"], "2026-04-01", "2026-10-31")
        self.assertEqual(inputs["revenue"], pnl["total_income"])
        self.assertEqual(inputs["net_profit"], pnl["net_profit"])
        self.assertTrue(data["balanced"])
        self.assertEqual(data["difference"], 0)
        ratios = {r["key"]: r for r in data["rows"]}
        self.assertGreater(ratios["current_ratio"]["value"], 1)
        self.assertIsNotNone(ratios["gross_margin"]["value"])
        self.assertIsNotNone(ratios["working_capital"]["value"])

    def test_period_comparison_uses_equal_length_prior_period(self):
        data = reports.period_comparison(self.conn, self.tenant, "2026-05-01", "2026-05-31")
        self.assertEqual(data["previous_from"], "2026-03-31")
        self.assertEqual(data["previous_to"], "2026-04-30")
        pnl = acct.profit_and_loss(self.conn, self.tenant["id"], "2026-05-01", "2026-05-31")
        self.assertEqual(data["metrics"]["revenue"]["current"], pnl["total_income"])
        self.assertTrue(data["rows"])
        self.assertTrue(any(r["section"] == "Income" for r in data["rows"]))

    def test_sales_and_purchase_registers_reconcile(self):
        sales = reports.sales_register(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(sales["totals"]["count"], 11)
        self.assertEqual(sales["totals"]["total"],
                         sales["totals"]["taxable"] + sales["totals"]["tax"]
                         + sales["totals"]["round_off"])
        purchases = reports.purchase_register(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(purchases["totals"]["count"], 3)
        self.assertEqual(purchases["totals"]["total"],
                         purchases["totals"]["taxable"] + purchases["totals"]["tax"]
                         + purchases["totals"]["round_off"])

    def test_expense_breakdown_and_account_activity_reconcile(self):
        expenses = reports.expense_breakdown(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        pnl = acct.profit_and_loss(self.conn, self.tenant["id"], "2026-04-01", "2026-10-31")
        self.assertEqual(expenses["total"], pnl["total_expense"])
        self.assertEqual(sum(r["amount"] for r in expenses["rows"]), expenses["total"])
        activity = reports.account_activity(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(activity["totals"]["debit"], activity["totals"]["credit"])
        self.assertTrue(activity["rows"])

    def test_reversal_register_keeps_original_and_reason(self):
        tenant_id = db.create_tenant(self.conn, "Reversal Co", "reversal-co", state_code="27")
        entry_id = acct.post_journal(
            self.conn, tenant_id, "2026-05-10", "Wrong posting",
            [{"account_id": db.account_id(self.conn, tenant_id, "1000"),
              "debit": 250000, "credit": 0},
             {"account_id": db.account_id(self.conn, tenant_id, "4000"),
              "debit": 0, "credit": 250000}],
            "manual")
        acct.reverse_entry(self.conn, tenant_id, entry_id, "wrong account")
        data = reports.reversal_register(self.conn, tenant_id, "2026-05-01", "2026-05-31")
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["original_id"], entry_id)
        self.assertEqual(row["amount"], 250000)
        self.assertIn("wrong account", row["reason"])

    def test_working_capital_cycle_formula(self):
        data = reports.working_capital(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(data["days"], 214)
        self.assertIsNotNone(data["dso"])
        self.assertIsNotNone(data["dio"])
        self.assertIsNotNone(data["dpo"])
        self.assertAlmostEqual(data["ccc"], data["dso"] + data["dio"] - data["dpo"], places=6)

    def test_other_tenant_is_isolated(self):
        other = db.create_tenant(self.conn, "Other Reports Co", "other-reports", state_code="27")
        cash = reports.cash_flow(self.conn, other, "2026-04-01", "2026-10-31")
        self.assertEqual(cash["rows"], [])
        self.assertEqual(cash["closing"], 0)
        self.assertEqual(reports.sales_register(self.conn, other, "2026-04-01", "2026-10-31")["rows"], [])
        self.assertEqual(reports.reversal_register(self.conn, other, "2026-04-01", "2026-10-31")["rows"], [])


if __name__ == "__main__":
    unittest.main()
