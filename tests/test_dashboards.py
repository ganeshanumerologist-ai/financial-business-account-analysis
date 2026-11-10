"""Saved analytics dashboards: validation, CRUD, templates and tenant isolation."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta

from app import dashboards, db
from app.demo import seed_demo


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="arthivio-dashboard-test-")
        self.conn = db.connect(os.path.join(self.tmp, "test.db"))
        db.init_db(self.conn)
        seed_demo(self.conn)
        self.tenant = self.conn.execute(
            "SELECT * FROM tenant WHERE slug='arthivio-demo'").fetchone()
        self.user = self.conn.execute(
            "SELECT * FROM user WHERE email='owner@arthivio.test'").fetchone()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def config(self, **overrides):
        base = {
            "period": "this_month",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "net_profit_paise"],
            "charts": ["monthly"],
            "language": "en",
        }
        base.update(overrides)
        return base

    def test_create_list_get_delete_and_audit(self):
        dashboard_id = dashboards.create_dashboard(
            self.conn, self.tenant["id"], self.user["id"], "Owner view",
            self.config(language="hi"), "private", "Monthly owner view")
        self.assertEqual(len(dashboard_id), 32)

        row = dashboards.get_dashboard(self.conn, self.tenant["id"], dashboard_id)
        self.assertEqual(row["name"], "Owner view")
        self.assertEqual(row["config"]["language"], "hi")
        self.assertEqual(row["config"]["metrics"], ["revenue_paise", "net_profit_paise"])
        self.assertEqual(row["creator_name"], self.user["full_name"])

        listed = dashboards.list_dashboards(self.conn, self.tenant["id"], self.user["id"])
        self.assertEqual([item["id"] for item in listed], [dashboard_id])

        dashboards.delete_dashboard(
            self.conn, self.tenant["id"], self.user["id"], dashboard_id)
        with self.assertRaises(dashboards.DashboardError) as ctx:
            dashboards.get_dashboard(self.conn, self.tenant["id"], dashboard_id)
        self.assertEqual(ctx.exception.code, "NOT_FOUND")

        actions = {row["action"] for row in self.conn.execute(
            "SELECT action FROM audit_log WHERE target_id=?", (dashboard_id,))}
        self.assertIn("dashboard.created", actions)
        self.assertIn("dashboard.deleted", actions)

    def test_validation(self):
        with self.assertRaises(dashboards.DashboardError) as ctx:
            dashboards.create_dashboard(
                self.conn, self.tenant["id"], self.user["id"], "No metrics",
                self.config(metrics=[]))
        self.assertEqual(ctx.exception.code, "NO_METRICS")

        with self.assertRaises(dashboards.DashboardError) as ctx:
            dashboards.create_dashboard(
                self.conn, self.tenant["id"], self.user["id"], "Bad period",
                self.config(period="last_century"))
        self.assertEqual(ctx.exception.code, "BAD_PERIOD")

        with self.assertRaises(dashboards.DashboardError) as ctx:
            dashboards.create_dashboard(
                self.conn, self.tenant["id"], self.user["id"], "No custom dates",
                self.config(period="custom"))
        self.assertEqual(ctx.exception.code, "BAD_PERIOD")

        dashboards.create_dashboard(
            self.conn, self.tenant["id"], self.user["id"], "Duplicate",
            self.config())
        with self.assertRaises(dashboards.DashboardError) as ctx:
            dashboards.create_dashboard(
                self.conn, self.tenant["id"], self.user["id"], "Duplicate",
                self.config())
        self.assertEqual(ctx.exception.code, "NAME_TAKEN")

    def test_template_library(self):
        template = dashboards.template("owner_monthly")
        self.assertIsNotNone(template)
        self.assertIn("revenue_paise", template["config"]["metrics"])
        dashboard_id = dashboards.create_dashboard(
            self.conn, self.tenant["id"], self.user["id"],
            template["name"], template["config"], "private", template["description"])
        row = dashboards.get_dashboard(self.conn, self.tenant["id"], dashboard_id)
        self.assertEqual(row["name"], "Owner monthly")
        self.assertIn("expense_breakdown", row["config"]["charts"])
        self.assertIsNone(dashboards.template("not-a-template"))

    def test_template_library_is_grouped_and_valid(self):
        library = dashboards.templates()
        self.assertGreaterEqual(len(library), 35)
        keys = [item["key"] for item in library]
        self.assertEqual(len(keys), len(set(keys)))
        names = [item["name"] for item in library]
        self.assertEqual(len(names), len(set(names)))
        categories = {item["category"] for item in library}
        for required in ("Starter", "Cash", "Tax", "Receivables", "Payables",
                         "Profitability", "Balance sheet", "Close", "Review"):
            self.assertIn(required, categories)
        for item in library:
            normalized = dashboards.normalize_config(item["config"])
            self.assertTrue(normalized["metrics"])
            self.assertLessEqual(len(normalized["metrics"]),
                                 dashboards.MAX_METRICS)
            for metric_key in normalized["metrics"]:
                self.assertIn(metric_key, dashboards.METRIC_BY_KEY)
            for chart_key in normalized["charts"]:
                self.assertIn(chart_key, dashboards.CHART_KEYS)
            self.assertEqual(dashboards.template(item["key"])["category"],
                             item["category"])
        for key in ("collections_and_payments", "inventory_working_capital",
                    "tax_close_checklist", "board_snapshot", "cash_conversion",
                    "quarterly_tax_profit"):
            self.assertIsNotNone(dashboards.template(key))
        full = dashboards.normalize_config(
            dashboards.template("full_finance")["config"])
        self.assertEqual(full["metrics"], list(dashboards.METRIC_KEYS))

    def test_private_and_shared_visibility(self):
        private_id = dashboards.create_dashboard(
            self.conn, self.tenant["id"], self.user["id"], "Private view",
            self.config(), "private")
        shared_id = dashboards.create_dashboard(
            self.conn, self.tenant["id"], self.user["id"], "Shared view",
            self.config(), "tenant")

        other_user_id = db.new_id()
        self.conn.execute(
            "INSERT INTO user (id,email,password_hash,full_name,status,theme,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (other_user_id, "other@arthivio.test", "x", "Other User", "active", "ocean", db.now()))
        listed = dashboards.list_dashboards(
            self.conn, self.tenant["id"], other_user_id)
        ids = {item["id"] for item in listed}
        self.assertNotIn(private_id, ids)
        self.assertIn(shared_id, ids)

        with self.assertRaises(dashboards.DashboardError) as ctx:
            dashboards.delete_dashboard(
                self.conn, self.tenant["id"], other_user_id, private_id)
        self.assertEqual(ctx.exception.code, "FORBIDDEN")

    def test_tenant_isolation(self):
        dashboard_id = dashboards.create_dashboard(
            self.conn, self.tenant["id"], self.user["id"], "Tenant A only",
            self.config())
        other_tenant_id = db.new_id()
        self.conn.execute(
            "INSERT INTO tenant (id,name,slug,state_code,currency,fiscal_year_start_month,"
            "status,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (other_tenant_id, "Other Co", "other-co", "27", "INR", 4, "active", db.now()))
        with self.assertRaises(dashboards.DashboardError) as ctx:
            dashboards.get_dashboard(self.conn, other_tenant_id, dashboard_id)
        self.assertEqual(ctx.exception.code, "NOT_FOUND")

    def test_period_resolution(self):
        today = date.today()
        this_month = dashboards.resolve_period(self.tenant, self.config(period="this_month"))
        self.assertEqual(this_month["from"], today.replace(day=1).isoformat())
        self.assertEqual(this_month["to"], today.isoformat())

        last_month = dashboards.resolve_period(self.tenant, self.config(period="last_month"))
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        self.assertEqual(last_month["from"], last_prev.replace(day=1).isoformat())
        self.assertEqual(last_month["to"], last_prev.isoformat())

        custom = dashboards.resolve_period(
            self.tenant, self.config(period="custom", **{"from": "2026-04-01", "to": "2026-04-30"}))
        self.assertEqual(custom, {"from": "2026-04-01", "to": "2026-04-30"})


if __name__ == "__main__":
    unittest.main()
