"""GSTR-3B working summary and GSTR-1/ledger reconciliation tests."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import db, demo


class Gstr3bDemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="arthivio-gstr3b-")
        cls.conn = db.connect(os.path.join(cls.tmp, "gstr3b.db"))
        db.init_db(cls.conn)
        demo.seed_demo(cls.conn)
        cls.tid = cls.conn.execute(
            "SELECT id FROM tenant WHERE slug='arthivio-demo'").fetchone()["id"]
        # One October purchase return so the ITC-reversal path is exercised.
        line = cls.conn.execute(
            "SELECT bl.id, bl.bill_id FROM bill_line bl JOIN bill b ON b.id=bl.bill_id"
            " JOIN item i ON i.id=bl.item_id WHERE b.tenant_id=? AND i.sku='TRD-004'",
            (cls.tid,)).fetchone()
        acct.create_debit_note(
            cls.conn, cls.tid, line["bill_id"], "2026-10-24", "Demo return",
            [{"bill_line_id": line["id"], "qty": 1000}],
            idempotency_key="gstr3b-demo-return")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_month_bounds(self):
        self.assertEqual(acct.month_bounds("2026-06"), ("2026-06-01", "2026-06-30"))
        self.assertEqual(acct.month_bounds("2024-02"), ("2024-02-01", "2024-02-29"))
        self.assertEqual(acct.month_bounds("2026-02"), ("2026-02-01", "2026-02-28"))
        for bad in ("2026-13", "2026-00", "June", "2026-6-1", "", "1999-12"):
            with self.assertRaises(acct.AccountingError) as ctx:
                acct.month_bounds(bad)
            self.assertEqual(ctx.exception.code, "BAD_MONTH")

    def test_june_is_net_of_credit_note(self):
        g = acct.gstr3b_data(self.conn, self.tid, "2026-06")
        inv = self.conn.execute(
            "SELECT COALESCE(SUM(sub_total_paise),0) taxable, COALESCE(SUM(tax_paise),0) tax"
            " FROM invoice WHERE tenant_id=? AND status='posted'"
            " AND invoice_date BETWEEN '2026-06-01' AND '2026-06-30'", (self.tid,)).fetchone()
        cn = self.conn.execute(
            "SELECT COALESCE(SUM(sub_total_paise),0) taxable, COALESCE(SUM(tax_paise),0) tax"
            " FROM credit_note WHERE tenant_id=?"
            " AND note_date BETWEEN '2026-06-01' AND '2026-06-30'", (self.tid,)).fetchone()
        self.assertGreater(cn["taxable"], 0)
        self.assertEqual(g["outward"]["taxable_gross"], inv["taxable"])
        self.assertEqual(g["outward"]["credit_note_taxable"], cn["taxable"])
        self.assertEqual(g["outward"]["taxable_net"], inv["taxable"] - cn["taxable"])
        self.assertEqual(g["outward"]["output_total"], inv["tax"] - cn["tax"])
        self.assertEqual(g["payment"]["output_total"], inv["tax"] - cn["tax"])
        self.assertEqual(g["reconciliation"]["failed"], 0)
        for c in g["reconciliation"]["checks"]:
            self.assertEqual(c["status"], "ok", c)

    def test_october_debit_note_reduces_itc(self):
        g = acct.gstr3b_data(self.conn, self.tid, "2026-10")
        self.assertEqual(g["itc"]["gross_total"], 0)
        self.assertEqual(g["itc"]["reversal_total"], 37800)
        self.assertEqual(g["itc"]["net_total"], -37800)
        self.assertEqual(g["itc"]["excess_reversal_total"], 37800)
        self.assertEqual(g["payment"]["excess_reversal_total"], 37800)
        self.assertEqual(g["payment"]["cash_payable_total"], 537884 + 37800)
        self.assertEqual(g["reconciliation"]["failed"], 0)
        self.assertTrue(any("ITC reversal exceeds" in w for w in g["warnings"]))

    def test_month_filter_and_counts(self):
        june = acct.gstr3b_data(self.conn, self.tid, "2026-06")
        october = acct.gstr3b_data(self.conn, self.tid, "2026-10")
        self.assertEqual(june["docs"]["invoices"], 2)
        self.assertEqual(june["docs"]["credit_notes"], 1)
        self.assertEqual(october["docs"]["invoices"], 2)
        self.assertEqual(october["docs"]["debit_notes"], 1)
        self.assertNotEqual(june["outward"]["taxable_net"], october["outward"]["taxable_net"])

    def test_empty_month_is_safe(self):
        g = acct.gstr3b_data(self.conn, self.tid, "2026-01")
        self.assertEqual(g["outward"]["taxable_net"], 0)
        self.assertEqual(g["outward"]["output_total"], 0)
        self.assertEqual(g["itc"]["net_total"], 0)
        self.assertEqual(g["payment"]["cash_payable_total"], 0)
        self.assertEqual(g["reconciliation"]["failed"], 0)
        self.assertTrue(any("No posted invoices" in w for w in g["warnings"]))

    def test_cross_tenant_invoice_not_included(self):
        other = db.create_tenant(self.conn, "Other GST Co", "other-gst", state_code="27")
        before = acct.gstr3b_data(self.conn, self.tid, "2026-06")
        after = acct.gstr3b_data(self.conn, other, "2026-06")
        self.assertEqual(after["outward"]["taxable_net"], 0)
        self.assertGreater(before["outward"]["taxable_net"], 0)


class Gstr3bReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "GST Co", "gst-co", state_code="27")
        self.cust = db.new_id()
        self.conn.execute(
            "INSERT INTO customer (id, tenant_id, name, state_code, gstin, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (self.cust, self.t, "Buyer Pvt Ltd", "27", "27AAAAA0000A1Z5", db.now()))
        self.item = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise,"
            " tax_rate_bp, stock_milli, track_stock) VALUES (?,?,?,?,?,?,?,?,?)",
            (self.item, self.t, "S1", "Service", 10000, 0, 1800, 0, 0))
        self.inv = acct.create_invoice(
            self.conn, self.t, self.cust, "2026-10-10", "27",
            [{"item_id": self.item, "qty": 1000, "unit_price": 10000}])

    def tearDown(self):
        self.conn.close()

    def test_clean_books_reconcile(self):
        g = acct.gstr3b_data(self.conn, self.t, "2026-10")
        self.assertEqual(g["outward"]["taxable_net"], 10000)
        self.assertEqual(g["outward"]["output_total"], 1800)
        self.assertEqual(g["reconciliation"]["failed"], 0)

    def test_manual_output_journal_is_flagged(self):
        rounding = db.account_id(self.conn, self.t, "5900")
        output_cgst = db.account_id(self.conn, self.t, "2100")
        acct.post_journal(
            self.conn, self.t, "2026-10-20", "Manual GST adjustment",
            [{"account_id": rounding, "debit": 100, "credit": 0, "memo": "Adjust"},
             {"account_id": output_cgst, "debit": 0, "credit": 100, "memo": "Adjust"}],
            source_type="journal", idempotency_key="manual-gst-1")
        g = acct.gstr3b_data(self.conn, self.t, "2026-10")
        check = next(c for c in g["reconciliation"]["checks"] if c["key"] == "ledger_output")
        self.assertEqual(check["difference"], 100)
        self.assertEqual(check["status"], "check")
        self.assertGreater(g["reconciliation"]["failed"], 0)
        self.assertTrue(any("reconciliation check" in w for w in g["warnings"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
