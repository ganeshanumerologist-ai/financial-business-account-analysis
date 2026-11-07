"""Management-report tests: deterministic formulas, reconciliation and isolation."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta

from app import accounting as acct
from app import advanced, budgeting, db, reports, stock_adjustments
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

    def _stock_item(self, stock_milli: int = 100000, cost_paise: int = 10000,
                    track_stock: int = 1) -> str:
        item_id = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, unit, cost_paise,"
            " stock_milli, track_stock) VALUES (?,?,?,?,?,?,?,?)",
            (item_id, self.tenant["id"], f"STK-{item_id[:8]}", "Adjustment test item",
             "pcs", cost_paise, stock_milli, track_stock),
        )
        return item_id

    def test_catalog_has_66_rows_and_all_working(self):
        cat = reports.catalog()
        self.assertEqual(cat["total"], 66)
        self.assertEqual(cat["working"], 66)
        self.assertEqual(cat["partial"], 0)
        self.assertEqual(cat["planned"], 0)
        working = [r for g in cat["groups"] for r in g["reports"] if r["status"] == "working"]
        self.assertTrue(all(r["route"] for r in working))
        for rid in ("R-104", "R-107", "R-108", "R-109", "R-110", "R-202", "R-203", "R-204",
                    "R-205", "R-206", "R-301", "R-302", "R-303", "R-306", "R-307", "R-308",
                    "R-309", "R-401", "R-404", "R-405", "R-406", "R-501", "R-502",
                    "R-503", "R-504", "R-505", "R-506", "R-507", "R-508", "R-601", "R-602",
                    "R-603", "R-604", "R-605", "R-704", "R-705", "R-706", "R-807", "R-901",
                    "R-902", "R-903", "R-904", "R-905", "R-1001", "R-1002", "R-1003",
                    "R-1004"):
            row = next(r for r in reports.REPORT_CATALOG if r["id"] == rid)
            self.assertEqual(row["status"], "working", rid)
            self.assertTrue(row["route"], rid)

    def test_batch_register_and_expiry_buckets(self):
        item_id = self._stock_item()
        today = date.today()
        advanced.create_batch(self.conn, self.tenant, item_id, "B-EXPIRED",
                              (today - timedelta(days=1)).isoformat(), 2000, 10000)
        advanced.create_batch(self.conn, self.tenant, item_id, "B-30",
                              (today + timedelta(days=10)).isoformat(), 3000, 20000)
        advanced.create_batch(self.conn, self.tenant, item_id, "B-90",
                              (today + timedelta(days=60)).isoformat(), 4000, 30000)
        data = reports.expiry_batch_report(self.conn, self.tenant, today.isoformat())
        self.assertEqual(data["totals"]["batches"], 3)
        self.assertEqual(data["totals"]["expired"], 1)
        self.assertEqual(data["totals"]["expiring_30"], 1)
        self.assertEqual(data["totals"]["value"], 20000 + 60000 + 120000)
        buckets = {b["name"]: b["batches"] for b in data["buckets"]}
        self.assertEqual(buckets["Expired"], 1)
        self.assertEqual(buckets["0-30 days"], 1)
        self.assertEqual(buckets["31-90 days"], 1)

    def test_project_costing_and_dimension_pnl_are_tagged_only(self):
        today = date.today().isoformat()
        project = advanced.create_dimension(self.conn, self.tenant, "project", "PRJ-1",
                                            "Website")
        department = advanced.create_dimension(self.conn, self.tenant, "department", "DEP-1",
                                               "Operations")
        acct.post_journal(
            self.conn, self.tenant["id"], today, "Project revenue",
            [{"account_id": db.account_id(self.conn, self.tenant["id"], "1100"),
              "debit": 50000, "credit": 0, "dimension_id": project},
             {"account_id": db.account_id(self.conn, self.tenant["id"], "4000"),
              "debit": 0, "credit": 50000, "dimension_id": project}],
            source_type="manual")
        acct.post_journal(
            self.conn, self.tenant["id"], today, "Project cost",
            [{"account_id": db.account_id(self.conn, self.tenant["id"], "6000"),
              "debit": 10000, "credit": 0, "dimension_id": project},
             {"account_id": db.account_id(self.conn, self.tenant["id"], "1000"),
              "debit": 0, "credit": 10000, "dimension_id": project}],
            source_type="manual")
        acct.post_journal(
            self.conn, self.tenant["id"], today, "Department cost",
            [{"account_id": db.account_id(self.conn, self.tenant["id"], "6010"),
              "debit": 7000, "credit": 0, "dimension_id": department},
             {"account_id": db.account_id(self.conn, self.tenant["id"], "1000"),
              "debit": 0, "credit": 7000, "dimension_id": department}],
            source_type="manual")
        project_data = reports.project_costing(self.conn, self.tenant, today, today)
        row = next(r for r in project_data["rows"] if r["id"] == project)
        self.assertEqual(row["revenue"], 50000)
        self.assertEqual(row["expense"], 10000)
        self.assertEqual(row["net"], 40000)
        unalloc = next(r for r in project_data["rows"] if r["kind"] == "unallocated")
        self.assertEqual(unalloc["expense"], 7000)
        dept_data = reports.department_branch_pnl(self.conn, self.tenant, today, today)
        dept = next(r for r in dept_data["rows"] if r["id"] == department)
        self.assertEqual(dept["expense"], 7000)
        self.assertEqual(dept["net"], -7000)

    def test_cost_centre_budget_actual_and_variance(self):
        today = date.today()
        centre = advanced.create_dimension(self.conn, self.tenant, "cost_centre", "CC-1",
                                           "Admin")
        advanced.set_dimension_budget(self.conn, self.tenant, centre,
                                      today.isoformat()[:7], 50000)
        acct.post_journal(
            self.conn, self.tenant["id"], today.isoformat(), "Admin cost",
            [{"account_id": db.account_id(self.conn, self.tenant["id"], "6000"),
              "debit": 20000, "credit": 0, "dimension_id": centre},
             {"account_id": db.account_id(self.conn, self.tenant["id"], "1000"),
              "debit": 0, "credit": 20000, "dimension_id": centre}],
            source_type="manual")
        data = reports.cost_centre_performance(
            self.conn, self.tenant, today.isoformat(), today.isoformat())
        row = next(r for r in data["rows"] if r["id"] == centre)
        self.assertEqual(row["actual"], 20000)
        self.assertEqual(row["budget"], 50000)
        self.assertEqual(row["variance"], 30000)
        self.assertEqual(row["status"], "Under budget")

    def test_production_wip_consumption_and_yield(self):
        today = date.today().isoformat()
        input_item = self._stock_item()
        output_item = self._stock_item()
        order_id = advanced.create_production_order(
            self.conn, self.tenant, today, input_item, output_item,
            10000, 9000, 9500, 10000, 10000)
        wip = reports.wip_report(self.conn, self.tenant, today, today)
        self.assertEqual(wip["totals"]["wip"], 10000)
        consumption = reports.production_consumption(self.conn, self.tenant, today, today)
        row = next(r for r in consumption["rows"] if r["id"] == order_id)
        self.assertEqual(row["variance_qty"], 500)
        self.assertEqual(consumption["totals"]["variance_pct"], 526)
        yield_data = reports.yield_wastage(self.conn, self.tenant, today, today)
        self.assertEqual(yield_data["totals"]["yield_pct"], 9000)
        self.assertEqual(yield_data["totals"]["wastage_pct"], 1000)
        advanced.set_production_status(self.conn, self.tenant, order_id, "completed")
        wip_done = reports.wip_report(self.conn, self.tenant, today, today)
        self.assertEqual(wip_done["totals"]["wip"], 0)

    def test_consolidated_summary_excludes_intercompany_entries(self):
        today = date.today().isoformat()
        first_id = db.create_tenant(self.conn, "First Co", "first-co")
        second_id = db.create_tenant(self.conn, "Second Co", "second-co")
        acct.post_journal(
            self.conn, first_id, today, "Normal sale",
            [{"account_id": db.account_id(self.conn, first_id, "1100"),
              "debit": 100000, "credit": 0},
             {"account_id": db.account_id(self.conn, first_id, "4000"),
              "debit": 0, "credit": 100000}],
            source_type="manual")
        acct.post_journal(
            self.conn, first_id, today, "Intercompany sale",
            [{"account_id": db.account_id(self.conn, first_id, "1100"),
              "debit": 20000, "credit": 0},
             {"account_id": db.account_id(self.conn, first_id, "4000"),
              "debit": 0, "credit": 20000}],
            source_type="manual", is_intercompany=True)
        acct.post_journal(
            self.conn, first_id, today, "Intercompany cost",
            [{"account_id": db.account_id(self.conn, first_id, "6000"),
              "debit": 20000, "credit": 0},
             {"account_id": db.account_id(self.conn, first_id, "2000"),
              "debit": 0, "credit": 20000}],
            source_type="manual", is_intercompany=True)
        acct.post_journal(
            self.conn, second_id, today, "Second sale",
            [{"account_id": db.account_id(self.conn, second_id, "1100"),
              "debit": 50000, "credit": 0},
             {"account_id": db.account_id(self.conn, second_id, "4000"),
              "debit": 0, "credit": 50000}],
            source_type="manual")
        data = reports.consolidated_summary(self.conn, [first_id, second_id], today)
        self.assertEqual(data["totals"]["tenants"], 2)
        self.assertEqual(data["totals"]["revenue"], 150000)
        self.assertEqual(data["totals"]["intercompany_entries"], 2)
        self.assertEqual(data["totals"]["intercompany_value"], 40000)
        first = next(r for r in data["rows"] if r["id"] == first_id)
        self.assertEqual(first["revenue"], 100000)

    def test_budget_vs_actual_marks_favourable_and_unfavourable(self):
        tenant_id = db.create_tenant(self.conn, "Budget Test Co", "budget-test-co")
        rent = db.account_id(self.conn, tenant_id, "6000")
        sales = db.account_id(self.conn, tenant_id, "4000")
        cash = db.account_id(self.conn, tenant_id, "1000")
        budgeting.set_budget(self.conn, tenant_id, rent, "2026-04", 200000)
        budgeting.set_budget(self.conn, tenant_id, sales, "2026-04", 150000)
        acct.post_journal(
            self.conn, tenant_id, "2026-04-15", "Rent over budget",
            [{"account_id": rent, "debit": 300000, "credit": 0},
             {"account_id": cash, "debit": 0, "credit": 300000}], "manual")
        acct.post_journal(
            self.conn, tenant_id, "2026-04-20", "Sales under budget",
            [{"account_id": cash, "debit": 100000, "credit": 0},
             {"account_id": sales, "debit": 0, "credit": 100000}], "manual")
        data = budgeting.budget_vs_actual(self.conn, tenant_id, "2026-04-01", "2026-04-30")
        by_code = {r["code"]: r for r in data["rows"]}
        self.assertEqual(by_code["6000"]["actual"], 300000)
        self.assertEqual(by_code["6000"]["budget"], 200000)
        self.assertEqual(by_code["6000"]["variance"], 100000)
        self.assertFalse(by_code["6000"]["favourable"])
        self.assertEqual(by_code["4000"]["actual"], 100000)
        self.assertEqual(by_code["4000"]["variance"], -50000)
        self.assertFalse(by_code["4000"]["favourable"])
        self.assertEqual(data["totals"]["income_budget"], 150000)
        self.assertEqual(data["totals"]["expense_actual"], 300000)
        self.assertEqual(data["totals"]["net_variance"], -150000)
        self.assertFalse(data["totals"]["net_favourable"])

    def test_budget_set_update_delete_is_audited(self):
        tenant_id = db.create_tenant(self.conn, "Budget Audit Co", "budget-audit-co")
        rent = db.account_id(self.conn, tenant_id, "6000")
        budget_id = budgeting.set_budget(
            self.conn, tenant_id, rent, "2026-05", 100000, "first", None)
        budgeting.set_budget(
            self.conn, tenant_id, rent, "2026-05", 125000, "revised", None)
        register = budgeting.register(self.conn, tenant_id, "2026-05-01", "2026-05-31")
        self.assertEqual(register["totals"]["entries"], 1)
        self.assertEqual(register["rows"][0]["amount"], 125000)
        self.assertEqual(register["rows"][0]["note"], "revised")
        actions = [r["action"] for r in self.conn.execute(
            "SELECT action FROM audit_log WHERE tenant_id=? AND target_type='budget'"
            " ORDER BY created_at", (tenant_id,)).fetchall()]
        self.assertIn("budget.create", actions)
        self.assertIn("budget.update", actions)
        budgeting.delete_budget(self.conn, tenant_id, budget_id, None)
        self.assertEqual(budgeting.register(
            self.conn, tenant_id, "2026-05-01", "2026-05-31")["totals"]["entries"], 0)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE tenant_id=? AND action='budget.delete'",
            (tenant_id,)).fetchone()["c"], 1)

    def test_budget_rejects_non_income_expense_and_negative_amount(self):
        tenant_id = db.create_tenant(self.conn, "Budget Reject Co", "budget-reject-co")
        cash = db.account_id(self.conn, tenant_id, "1000")
        rent = db.account_id(self.conn, tenant_id, "6000")
        with self.assertRaises(budgeting.BudgetError):
            budgeting.set_budget(self.conn, tenant_id, cash, "2026-04", 100000)
        with self.assertRaises(budgeting.BudgetError):
            budgeting.set_budget(self.conn, tenant_id, rent, "2026-04", -1)

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

    def test_sales_summary_and_top_customers_reconcile(self):
        summary = reports.sales_summary_by_period(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        register = reports.sales_register(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(summary["totals"]["invoices"], register["totals"]["count"])
        self.assertEqual(summary["totals"]["total"], register["totals"]["total"])
        self.assertEqual(summary["totals"]["taxable"], register["totals"]["taxable"])
        self.assertTrue(summary["rows"])
        self.assertEqual(summary["rows"][0]["growth"], None)
        for row in summary["rows"][1:]:
            self.assertIsNotNone(row["growth"])

        top = reports.top_customers(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(top["totals"]["total"], register["totals"]["total"])
        self.assertEqual(top["rows"][0]["rank"], 1)
        self.assertAlmostEqual(sum(r["share"] for r in top["rows"]), 1.0, places=6)
        self.assertAlmostEqual(top["rows"][-1]["cumulative_share"], 1.0, places=6)

    def test_product_sales_and_discounts_reconcile_to_invoice_lines(self):
        sales = reports.sales_register(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        products = reports.product_sales(self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(products["totals"]["revenue"], sales["totals"]["taxable"])
        self.assertTrue(products["rows"])
        for row in products["rows"]:
            self.assertEqual(row["margin"], row["revenue"] - row["cost"])
            self.assertGreaterEqual(row["revenue"], 0)
        self.assertAlmostEqual(sum(r["share"] for r in products["rows"]), 1.0, places=6)

        discounts = reports.discount_analysis(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(discounts["totals"]["taxable"], sales["totals"]["taxable"])
        self.assertGreater(discounts["totals"]["discount"], 0)
        self.assertGreater(discounts["totals"]["invoices_with_discount"], 0)
        self.assertLessEqual(discounts["totals"]["discount"], discounts["totals"]["gross"])

    def test_returns_and_supplier_concentration(self):
        returns = reports.sales_returns(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(returns["totals"]["notes"], 1)
        self.assertEqual(returns["totals"]["total"],
                         returns["totals"]["taxable"] + returns["totals"]["tax"])
        self.assertGreater(returns["totals"]["return_rate"], 0)

        purchases = reports.purchase_register(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        suppliers = reports.top_suppliers(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(suppliers["totals"]["total"], purchases["totals"]["total"])
        self.assertAlmostEqual(sum(r["share"] for r in suppliers["rows"]), 1.0, places=6)
        purchase_returns = reports.purchase_returns(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(purchase_returns["totals"]["notes"], 0)
        self.assertEqual(purchase_returns["totals"]["return_rate"], 0)

    def test_stock_summary_reconstructs_period_quantities(self):
        data = reports.stock_summary(
            self.conn, self.tenant, "2026-04-01", "2026-12-31")
        self.assertTrue(data["rows"])
        self.assertGreater(data["totals"]["closing_value"], 0)
        current = {r["id"]: r["stock_milli"] for r in self.conn.execute(
            "SELECT id, stock_milli FROM item WHERE tenant_id=?", (self.tenant["id"],))}
        for row in data["rows"]:
            self.assertEqual(row["opening"] + row["in_period"] - row["out_period"],
                             row["closing"])
            self.assertEqual(row["closing"], current[row["id"]])

    def test_credit_limit_utilisation_and_over_limit(self):
        data = reports.credit_limit_utilisation(
            self.conn, self.tenant, "2026-10-31")
        ageing = acct.receivable_ageing(self.conn, self.tenant["id"], "2026-10-31")
        self.assertEqual(data["totals"]["outstanding"], ageing["grand_total"])
        self.assertTrue(data["rows"])
        self.assertTrue(all(r["no_limit"] for r in data["rows"]))

        customer_id = next(r["customer_id"] for r in ageing["rows"]
                           if r.get("customer_id"))
        due = next(r["outstanding"] for r in ageing["rows"]
                   if r.get("customer_id") == customer_id)
        self.conn.execute(
            "UPDATE customer SET credit_limit_paise=? WHERE id=?",
            (max(1, due - 1), customer_id))
        data = reports.credit_limit_utilisation(self.conn, self.tenant, "2026-10-31")
        row = next(r for r in data["rows"] if r["id"] == customer_id)
        self.assertTrue(row["over_limit"])
        self.assertEqual(data["totals"]["over_limit"], 1)

    def test_trial_balance_exceptions_find_malformed_entry(self):
        clean = reports.trial_balance_exceptions(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(clean["exceptions"], 0)
        self.assertGreater(clean["checked"], 0)

        tenant_id = self.tenant["id"]
        entry_id = db.new_id()
        self.conn.execute(
            "INSERT INTO journal_entry (id, tenant_id, entry_no, entry_date, narration,"
            " source_type, status, posted_at) VALUES (?,?,?,?,?,?,?,?)",
            (entry_id, tenant_id, "BAD-1", "2026-10-31", "Malformed test entry",
             "manual", "posted", db.now()))
        self.conn.execute(
            "INSERT INTO journal_line (id, tenant_id, entry_id, line_no, account_id,"
            " debit_paise, credit_paise) VALUES (?,?,?,?,?,?,?)",
            (db.new_id(), tenant_id, entry_id, 1,
             db.account_id(self.conn, tenant_id, "1000"), 1000, 0))
        self.conn.execute(
            "INSERT INTO journal_line (id, tenant_id, entry_id, line_no, account_id,"
            " debit_paise, credit_paise) VALUES (?,?,?,?,?,?,?)",
            (db.new_id(), tenant_id, entry_id, 2,
             db.account_id(self.conn, tenant_id, "4000"), 0, 900))
        data = reports.trial_balance_exceptions(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(data["exceptions"], 1)
        self.assertEqual(data["rows"][0]["entry_no"], "BAD-1")
        self.assertEqual(data["rows"][0]["difference"], 100)
        self.assertIn("Debit and credit differ", data["rows"][0]["issues"])

    def test_opening_closing_balances_reconcile(self):
        data = reports.opening_closing_balances(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertTrue(data["rows"])
        self.assertTrue(data["totals"]["reconciled"])
        for row in data["rows"]:
            self.assertEqual(row["opening"] + row["debit"] - row["credit"],
                             row["closing"])
        self.assertEqual(data["totals"]["debit"], data["totals"]["credit"])

    def test_draft_entries_report_only_unposted_invoices_with_age(self):
        tenant_id = self.tenant["id"]
        customer_id = self.conn.execute(
            "SELECT id FROM customer WHERE tenant_id=? LIMIT 1", (tenant_id,)
        ).fetchone()["id"]
        item_id = self._stock_item(stock_milli=0, track_stock=0)
        self.conn.execute(
            "UPDATE item SET sale_price_paise=10000, tax_rate_bp=1800 WHERE id=?",
            (item_id,),
        )
        draft = acct.save_invoice_draft(
            self.conn, tenant_id, customer_id, "2026-09-01", "27",
            [{"item_id": item_id, "qty": 1000}],
        )
        voided = acct.save_invoice_draft(
            self.conn, tenant_id, customer_id, "2026-10-01", "27",
            [{"item_id": item_id, "qty": 1000}],
        )
        acct.void_draft_invoice(self.conn, tenant_id, voided["id"], "Duplicate")

        data = reports.draft_entries(self.conn, self.tenant, "2026-10-31")
        self.assertEqual(data["totals"]["drafts"], 1)
        self.assertEqual(data["totals"]["value"], draft["total_paise"])
        self.assertEqual(data["totals"]["oldest_days"], 60)
        self.assertEqual(data["totals"]["over_30"], 1)
        self.assertEqual(data["rows"][0]["invoice_no"], draft["invoice_no"])
        self.assertEqual(data["rows"][0]["bucket"], "31-60")
        self.assertIn("draft sales invoices only", data["method"])

        acct.post_draft_invoice(self.conn, tenant_id, draft["id"])
        after = reports.draft_entries(self.conn, self.tenant, "2026-10-31")
        self.assertEqual(after["totals"]["drafts"], 0)
        self.assertEqual(after["rows"], [])

    def test_locked_period_register_reads_lock_actor(self):
        tenant_id = self.tenant["id"]
        user_id = self.conn.execute("SELECT id FROM user LIMIT 1").fetchone()["id"]
        self.conn.execute(
            "INSERT INTO period_lock (tenant_id, period_start, period_end, locked_at,"
            " locked_by) VALUES (?,?,?,?,?)",
            (tenant_id, "2026-04-01", "2026-04-30", db.now(), user_id))
        data = reports.locked_periods(self.conn, self.tenant)
        self.assertEqual(data["totals"]["periods"], 1)
        self.assertEqual(data["rows"][0]["period_start"], "2026-04-01")
        self.assertTrue(data["rows"][0]["locked_by_name"])

    def test_salesperson_revenue_and_collections_reconcile(self):
        data = reports.salesperson_performance(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        sales = reports.sales_register(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(data["totals"]["total"], sales["totals"]["total"])
        self.assertEqual(data["totals"]["invoices"], sales["totals"]["count"])
        receipts = self.conn.execute(
            "SELECT COALESCE(SUM(amount_paise),0) FROM payment WHERE tenant_id=?"
            " AND direction='receipt' AND payment_date BETWEEN ? AND ?",
            (self.tenant["id"], "2026-04-01", "2026-10-31")).fetchone()[0]
        self.assertEqual(data["totals"]["collected"], receipts)

    def test_price_variance_uses_latest_and_current_cost(self):
        data = reports.price_variance(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertTrue(data["rows"])
        for row in data["rows"]:
            self.assertGreater(row["latest_price"], 0)
            self.assertGreater(row["current_cost"], 0)
            if row["previous_price"] is not None:
                self.assertEqual(row["variance"],
                                 row["latest_price"] - row["previous_price"])
            self.assertEqual(row["vs_cost"], row["latest_price"] - row["current_cost"])

    def test_stock_movements_match_stock_summary_quantities(self):
        movements = reports.stock_movements(
            self.conn, self.tenant, "2026-04-01", "2026-12-31")
        summary = reports.stock_summary(
            self.conn, self.tenant, "2026-04-01", "2026-12-31")
        self.assertEqual(movements["totals"]["in_qty"],
                         sum(r["in_period"] for r in summary["rows"]))
        self.assertEqual(movements["totals"]["out_qty"],
                         sum(r["out_period"] for r in summary["rows"]))
        self.assertTrue(all(r["direction"] in ("In", "Out") for r in movements["rows"]))

    def test_inventory_valuation_matches_stock_summary_value(self):
        valuation = reports.inventory_valuation(
            self.conn, self.tenant, "2026-12-31")
        summary = reports.stock_summary(
            self.conn, self.tenant, "2026-04-01", "2026-12-31")
        self.assertEqual(valuation["totals"]["value"],
                         summary["totals"]["closing_value"])
        self.assertTrue(valuation["rows"])

    def test_reorder_shortage_uses_item_level(self):
        item = self.conn.execute(
            "SELECT id, stock_milli FROM item WHERE tenant_id=? AND track_stock=1"
            " ORDER BY name LIMIT 1", (self.tenant["id"],)).fetchone()
        self.conn.execute(
            "UPDATE item SET reorder_level_milli=? WHERE id=?",
            (int(item["stock_milli"]) + 5000, item["id"]))
        data = reports.reorder_shortage(self.conn, self.tenant, "2026-12-31")
        row = next(r for r in data["rows"] if r["id"] == item["id"])
        self.assertTrue(row["has_level"])
        self.assertEqual(row["status"], "Below reorder level")
        self.assertEqual(row["shortage"], 5000)
        self.assertEqual(data["totals"]["below_level"], 1)

    def test_dead_stock_uses_last_posted_movement(self):
        data = reports.dead_stock(self.conn, self.tenant, 0, "2026-12-31")
        self.assertTrue(data["rows"])
        for row in data["rows"]:
            self.assertGreater(row["stock"], 0)
            self.assertGreaterEqual(row["value"], 0)
            if row["last_date"]:
                self.assertIsNotNone(row["age_days"])
        self.assertGreaterEqual(data["totals"]["items"], 1)

    def test_stock_adjustment_posts_and_register_reconciles(self):
        item_id = self._stock_item(stock_milli=100000, cost_paise=10000)
        increase = stock_adjustments.adjust_stock(
            self.conn, self.tenant["id"], item_id, "2026-10-15", 1000,
            "Physical count gain")
        self.assertTrue(increase["adjustment_no"].startswith("STK-"))
        self.assertEqual(increase["qty_milli"], 1000)
        self.assertEqual(increase["value_paise"], 10000)

        entry = self.conn.execute(
            "SELECT * FROM journal_entry WHERE id=?",
            (increase["journal_entry_id"],)).fetchone()
        self.assertEqual(entry["source_type"], "stock_adjustment")
        lines = self.conn.execute(
            "SELECT a.code, l.debit_paise, l.credit_paise FROM journal_line l"
            " JOIN account a ON a.id=l.account_id WHERE l.entry_id=?"
            " ORDER BY a.code", (entry["id"],)).fetchall()
        self.assertEqual([(r["code"], r["debit_paise"], r["credit_paise"])
                          for r in lines],
                         [("1200", 10000, 0), ("5950", 0, 10000)])
        stock = self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0]
        self.assertEqual(stock, 101000)

        decrease = stock_adjustments.adjust_stock(
            self.conn, self.tenant["id"], item_id, "2026-10-16", -500,
            "Damaged in storage")
        self.assertEqual(decrease["value_paise"], -5000)
        lines = self.conn.execute(
            "SELECT a.code, l.debit_paise, l.credit_paise FROM journal_line l"
            " JOIN account a ON a.id=l.account_id WHERE l.entry_id=?"
            " ORDER BY a.code", (decrease["journal_entry_id"],)).fetchall()
        self.assertEqual([(r["code"], r["debit_paise"], r["credit_paise"])
                          for r in lines],
                         [("1200", 0, 5000), ("5950", 5000, 0)])
        stock = self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0]
        self.assertEqual(stock, 100500)

        data = reports.stock_adjustment_register(
            self.conn, self.tenant, "2026-10-01", "2026-10-31")
        self.assertEqual(data["totals"]["adjustments"], 2)
        self.assertEqual(data["totals"]["items"], 1)
        self.assertEqual(data["totals"]["increase_qty"], 1000)
        self.assertEqual(data["totals"]["decrease_qty"], 500)
        self.assertEqual(data["totals"]["net_qty"], 500)
        self.assertEqual(data["totals"]["increase_value"], 10000)
        self.assertEqual(data["totals"]["decrease_value"], 5000)
        self.assertEqual(data["totals"]["net_value"], 5000)

        movements = reports.stock_movements(
            self.conn, self.tenant, "2026-10-01", "2026-10-31")
        adjustment_rows = [r for r in movements["rows"]
                           if r["doc_type"] == "Stock adjustment"]
        self.assertEqual(len(adjustment_rows), 2)
        self.assertEqual(sum(r["in_qty"] for r in adjustment_rows), 1000)
        self.assertEqual(sum(r["out_qty"] for r in adjustment_rows), 500)

        summary = reports.stock_summary(
            self.conn, self.tenant, "2026-10-01", "2026-10-31")
        summary_row = next(r for r in summary["rows"] if r["id"] == item_id)
        self.assertEqual(summary_row["opening"], 100000)
        self.assertEqual(summary_row["in_period"], 1000)
        self.assertEqual(summary_row["out_period"], 500)
        self.assertEqual(summary_row["closing"], 100500)

        audits = self.conn.execute(
            "SELECT action FROM audit_log WHERE tenant_id=? AND action='stock.adjust'",
            (self.tenant["id"],)).fetchall()
        self.assertEqual(len(audits), 2)

    def test_stock_adjustment_rejects_invalid_quantities(self):
        tracked = self._stock_item(stock_milli=1000, cost_paise=10000)
        with self.assertRaises(stock_adjustments.StockAdjustmentError) as ctx:
            stock_adjustments.adjust_stock(
                self.conn, self.tenant["id"], tracked, "2026-10-15", -2000,
                "Too much")
        self.assertEqual(ctx.exception.code, "INSUFFICIENT_STOCK")
        with self.assertRaises(stock_adjustments.StockAdjustmentError) as ctx:
            stock_adjustments.adjust_stock(
                self.conn, self.tenant["id"], tracked, "2026-10-15", 0,
                "Nothing")
        self.assertEqual(ctx.exception.code, "BAD_QTY")

        untracked = self._stock_item(track_stock=0)
        with self.assertRaises(stock_adjustments.StockAdjustmentError) as ctx:
            stock_adjustments.adjust_stock(
                self.conn, self.tenant["id"], untracked, "2026-10-15", 1000,
                "Not tracked")
        self.assertEqual(ctx.exception.code, "NOT_TRACKED")

        zero_cost = self._stock_item(cost_paise=0)
        with self.assertRaises(stock_adjustments.StockAdjustmentError) as ctx:
            stock_adjustments.adjust_stock(
                self.conn, self.tenant["id"], zero_cost, "2026-10-15", 1000,
                "No cost")
        self.assertEqual(ctx.exception.code, "COST_REQUIRED")

        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM stock_adjustment WHERE tenant_id=?",
            (self.tenant["id"],)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (tracked,)).fetchone()[0],
            1000)

    def test_stock_adjustment_idempotency_does_not_double_post(self):
        item_id = self._stock_item()
        first = stock_adjustments.adjust_stock(
            self.conn, self.tenant["id"], item_id, "2026-10-15", 1000,
            "Count gain", idempotency_key="stock-test-key-1")
        second = stock_adjustments.adjust_stock(
            self.conn, self.tenant["id"], item_id, "2026-10-15", 1000,
            "Count gain", idempotency_key="stock-test-key-1")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM stock_adjustment WHERE tenant_id=?",
            (self.tenant["id"],)).fetchone()[0], 1)
        self.assertEqual(self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0],
            101000)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE tenant_id=? AND action='stock.adjust'",
            (self.tenant["id"],)).fetchone()[0], 1)

    def test_inventory_gl_reconciliation_shows_difference(self):
        data = reports.inventory_gl_reconciliation(
            self.conn, self.tenant, "2026-12-31")
        self.assertEqual(data["totals"]["stock_value"],
                         sum(r["value"] for r in data["rows"]))
        self.assertEqual(data["totals"]["difference"],
                         data["totals"]["stock_value"] - data["totals"]["gl_balance"])
        self.assertTrue(data["gl_accounts"])

    def test_receivables_risk_reconciles_to_ageing(self):
        data = reports.receivables_risk(
            self.conn, self.tenant, "2026-10-31", 30)
        ageing = acct.receivable_ageing(self.conn, self.tenant["id"], "2026-10-31")
        self.assertEqual(data["totals"]["outstanding"], ageing["grand_total"])
        self.assertEqual(data["prior_as_of"], "2026-10-01")
        self.assertTrue(data["rows"])
        for row in data["rows"]:
            self.assertLessEqual(row["overdue"], row["outstanding"])
            self.assertIn(row["risk"], ("High", "Medium", "Low"))

    def test_rule_version_usage_groups_posted_entries(self):
        data = reports.rule_version_usage(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(data["current_version"], "posting-v1")
        self.assertEqual(data["totals"]["versions"], 1)
        self.assertEqual(data["totals"]["difference"], 0)
        self.assertEqual(data["rows"][0]["rule_version"], "posting-v1")
        entry_id = self.conn.execute(
            "SELECT id FROM journal_entry WHERE tenant_id=? LIMIT 1",
            (self.tenant["id"],)).fetchone()["id"]
        self.conn.execute(
            "UPDATE journal_entry SET rule_version='test-v2' WHERE id=?", (entry_id,))
        try:
            changed = reports.rule_version_usage(
                self.conn, self.tenant, "2026-04-01", "2026-10-31")
            self.assertEqual(changed["totals"]["versions"], 2)
            self.assertEqual(changed["totals"]["difference"], 0)
            versions = {r["rule_version"] for r in changed["rows"]}
            self.assertEqual(versions, {"posting-v1", "test-v2"})
        finally:
            self.conn.execute(
                "UPDATE journal_entry SET rule_version='posting-v1' WHERE id=?",
                (entry_id,))

    def test_cash_flow_forecast_reconciles_opening_to_closing(self):
        data = reports.cash_flow_forecast(
            self.conn, self.tenant, "2026-10-31", 90)
        self.assertEqual(data["opening_cash"] + data["scheduled_inflow"]
                         - data["scheduled_outflow"], data["closing_cash"])
        self.assertEqual(data["rows"][-1]["closing"], data["closing_cash"])
        self.assertEqual(data["scheduled_inflow"] + data["beyond_inflow"],
                         data["open_receivables"])
        self.assertEqual(data["scheduled_outflow"] + data["beyond_outflow"],
                         data["open_payables"])
        self.assertGreaterEqual(data["overdue_receivables"], 0)

    def test_tax_ledger_reconciles_output_and_input(self):
        data = reports.tax_ledger(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertTrue(data["rows"])
        self.assertEqual(data["totals"]["net_payable"],
                         data["totals"]["output_payable"] - data["totals"]["input_credit"])
        for row in data["rows"]:
            self.assertEqual(row["opening"] + row["debit"] - row["credit"],
                             row["closing"])
        self.assertEqual(data["totals"]["debit"],
                         sum(r["debit"] for r in data["rows"]))

    def test_kpi_pack_is_actual_only_and_checks_balance(self):
        data = reports.kpi_dashboard(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertTrue(data["kpis"])
        self.assertTrue(all(k["actual"] for k in data["kpis"]))
        self.assertTrue(data["checks"]["balance_sheet_balanced"])
        self.assertEqual(data["checks"]["cash_flow_difference"], 0)
        labels = {k["label"] for k in data["kpis"]}
        for label in ("Revenue", "Net profit", "Cash and bank", "Receivables",
                      "Payables", "Inventory value", "DSO", "DIO", "DPO"):
            self.assertIn(label, labels)

    def test_trend_explanation_matches_monthly_sales(self):
        data = reports.trend_explanation(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        summary = reports.sales_summary_by_period(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(sum(r["revenue"] for r in data["rows"]),
                         summary["totals"]["taxable"])
        self.assertEqual(len(data["rows"]), 7)
        self.assertTrue(data["narrative"])
        self.assertIn("No estimate or forecast", data["method"])

    def test_revenue_forecast_separates_actuals_and_forecast(self):
        data = reports.revenue_forecast(
            self.conn, self.tenant, "2026-04-01", "2026-10-31", 3)
        summary = reports.sales_summary_by_period(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertEqual(sum(r["revenue"] for r in data["actuals"]),
                         summary["totals"]["taxable"])
        self.assertTrue(all(r["actual"] for r in data["actuals"]))
        self.assertEqual(len(data["forecast"]), 3)
        self.assertTrue(all(not r["actual"] for r in data["forecast"]))
        for row in data["forecast"]:
            self.assertGreaterEqual(row["revenue"], 0)
            self.assertLessEqual(row["lower"], row["revenue"])
            self.assertGreaterEqual(row["upper"], row["revenue"])
        self.assertIn(data["confidence"], ("low", "medium", "high"))

    def test_anomaly_digest_returns_review_prompts(self):
        data = reports.anomaly_digest(
            self.conn, self.tenant, "2026-04-01", "2026-10-31")
        self.assertGreaterEqual(data["totals"]["findings"], 0)
        self.assertEqual(data["totals"]["findings"],
                         data["totals"]["high"] + data["totals"]["medium"]
                         + data["totals"]["low"])
        self.assertIn("not fraud findings", data["method"])
        for row in data["rows"]:
            self.assertIn(row["severity"], ("High", "Medium", "Low"))
            self.assertTrue(row["kind"])

    def test_other_tenant_is_isolated(self):
        other = db.create_tenant(self.conn, "Other Reports Co", "other-reports", state_code="27")
        cash = reports.cash_flow(self.conn, other, "2026-04-01", "2026-10-31")
        self.assertEqual(cash["rows"], [])
        self.assertEqual(cash["closing"], 0)
        self.assertEqual(reports.sales_register(self.conn, other, "2026-04-01", "2026-10-31")["rows"], [])
        self.assertEqual(reports.reversal_register(self.conn, other, "2026-04-01", "2026-10-31")["rows"], [])


if __name__ == "__main__":
    unittest.main()
