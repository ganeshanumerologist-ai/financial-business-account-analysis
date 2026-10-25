"""GSTR-2B working import and purchase reconciliation."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import db, gstr2b


CSV_MATCH = """GSTIN,Supplier Name,Invoice No,Invoice Date,Taxable Value,IGST,CGST,SGST,Cess,Invoice Value
27AAACL1234C1Z5,Test Vendor,INV-001,2026-08-10,10000.00,0,900.00,900.00,0,11800.00
"""

CSV_MISMATCH = """GSTIN,Supplier Name,Invoice No,Invoice Date,Taxable Value,IGST,CGST,SGST,Cess,Invoice Value
27AAACL1234C1Z5,Test Vendor,INV-001,2026-08-10,9500.00,0,855.00,855.00,0,11210.00
"""

CSV_MISSING = """GSTIN,Supplier Name,Invoice No,Invoice Date,Taxable Value,IGST,CGST,SGST,Cess,Invoice Value
27AAACL1234C1Z5,Test Vendor,INV-999,2026-08-12,5000.00,0,450.00,450.00,0,5900.00
"""


class Gstr2bBase(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Demo Co", "demo", state_code="27")
        self.vendor = db.new_id()
        self.conn.execute(
            "INSERT INTO vendor (id, tenant_id, name, gstin, state_code, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (self.vendor, self.t, "Test Vendor", "27AAACL1234C1Z5", "27", db.now()))
        self.item = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise,"
            " tax_rate_bp, stock_milli, track_stock, revenue_code) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (self.item, self.t, "SKU1", "Item", 12000, 100000, 1800, 0, 1, "4000"))
        self.bill = acct.create_bill(
            self.conn, self.t, self.vendor, "2026-08-10", "INV-001", "27",
            [{"item_id": self.item, "qty": 10000}])

    def tearDown(self):
        self.conn.close()

    def import_csv(self, text, period="2026-08", name="gstr2b.csv"):
        return gstr2b.import_2b(self.conn, self.t, period, text, name, None)


class TestParsing(unittest.TestCase):
    def test_preamble_and_aliases(self):
        text = """GSTR-2B working extract
Generated for August 2026
GSTIN of supplier,Trade name,Document Number,Document Date,Taxable Value,Integrated Tax,Central Tax,State Tax,Cess,Invoice Value
27AAACL1234C1Z5,Test Vendor,INV-001,10/08/2026,"10,000.00",0,900,900,0,11800
"""
        rows = gstr2b.parse_csv(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["invoice_no"], "INV-001")
        self.assertEqual(rows[0]["invoice_date"], "2026-08-10")
        self.assertEqual(rows[0]["taxable_paise"], 1000000)
        self.assertEqual(rows[0]["tax_paise"], 180000)

    def test_invoice_normalisation(self):
        self.assertEqual(gstr2b.normalize_invoice("Inv-001"), gstr2b.normalize_invoice("INV-1"))
        self.assertEqual(gstr2b.normalize_invoice("LH/2026/041"), "LH2026041")

    def test_bad_gstin_and_date(self):
        with self.assertRaises(gstr2b.Gstr2bError) as ctx:
            gstr2b.parse_csv(
                "GSTIN,Invoice No,Invoice Date,Taxable Value\nBAD,INV-1,2026-08-10,100\n")
        self.assertEqual(ctx.exception.code, "BAD_GSTIN")
        with self.assertRaises(gstr2b.Gstr2bError) as ctx:
            gstr2b.parse_csv(
                "GSTIN,Invoice No,Invoice Date,Taxable Value\n"
                "27AAACL1234C1Z5,INV-1,not-a-date,100\n")
        self.assertEqual(ctx.exception.code, "BAD_DATE")

    def test_empty_and_no_header(self):
        with self.assertRaises(gstr2b.Gstr2bError) as ctx:
            gstr2b.parse_csv("")
        self.assertEqual(ctx.exception.code, "EMPTY_CSV")
        with self.assertRaises(gstr2b.Gstr2bError) as ctx:
            gstr2b.parse_csv("foo,bar\n1,2\n")
        self.assertEqual(ctx.exception.code, "NO_HEADER")


class TestImport(Gstr2bBase):
    def test_duplicate_and_replacement(self):
        first = self.import_csv(CSV_MATCH)
        self.assertFalse(first["duplicate"])
        dup = self.import_csv(CSV_MATCH)
        self.assertTrue(dup["duplicate"])
        self.assertEqual(dup["import_id"], first["import_id"])
        second = self.import_csv(CSV_MISMATCH)
        self.assertFalse(second["duplicate"])
        statuses = {r["id"]: r["status"] for r in
                    gstr2b.import_history(self.conn, self.t, "2026-08")}
        self.assertEqual(statuses[first["import_id"]], "superseded")
        self.assertEqual(statuses[second["import_id"]], "active")
        self.assertEqual(gstr2b.latest_import(self.conn, self.t, "2026-08")["id"],
                         second["import_id"])

    def test_duplicate_file_points_at_existing_period(self):
        first = self.import_csv(CSV_MATCH, period="2026-08")
        dup = self.import_csv(CSV_MATCH, period="2026-09")
        self.assertTrue(dup["duplicate"])
        self.assertEqual(dup["import_id"], first["import_id"])
        self.assertEqual(dup["period"], "2026-08")

    def test_cross_tenant_isolation(self):
        t2 = db.create_tenant(self.conn, "Other Co", "other", state_code="27")
        gstr2b.import_2b(self.conn, t2, "2026-08", CSV_MATCH, "x.csv", None)
        result = gstr2b.reconcile(self.conn, self.t, "2026-08")
        self.assertIsNone(result["import"])

    def test_invalid_month(self):
        with self.assertRaises(acct.AccountingError):
            gstr2b.import_2b(self.conn, self.t, "2026-13", CSV_MATCH, "x.csv", None)


class TestReconcile(Gstr2bBase):
    def test_exact_match(self):
        self.import_csv(CSV_MATCH)
        result = gstr2b.reconcile(self.conn, self.t, "2026-08")
        row = result["rows"][0]
        self.assertEqual(row["match_status"], "matched")
        self.assertEqual(row["matched_bill_id"], self.bill["id"])
        self.assertEqual(result["summary"]["matched"]["count"], 1)
        self.assertEqual(result["summary"]["two_b"]["tax"], 180000)
        self.assertEqual(result["summary"]["books"]["tax"], 180000)
        self.assertEqual(result["summary"]["difference"], 0)
        self.assertEqual(result["books"], [])

    def test_amount_mismatch_is_reported_not_corrected(self):
        self.import_csv(CSV_MISMATCH)
        result = gstr2b.reconcile(self.conn, self.t, "2026-08")
        row = result["rows"][0]
        self.assertEqual(row["match_status"], "mismatch")
        self.assertIn("taxable", row["note"])
        self.assertEqual(result["summary"]["mismatch"]["count"], 1)
        self.assertNotEqual(result["summary"]["mismatch"]["difference"], 0)
        bill = self.conn.execute("SELECT tax_paise FROM bill WHERE id=?", (self.bill["id"],)).fetchone()
        self.assertEqual(bill["tax_paise"], 180000)

    def test_missing_in_books(self):
        self.import_csv(CSV_MISSING)
        result = gstr2b.reconcile(self.conn, self.t, "2026-08")
        self.assertEqual(result["rows"][0]["match_status"], "missing_in_books")
        self.assertEqual(result["summary"]["missing_in_books"]["count"], 1)
        self.assertEqual(result["summary"]["missing_in_2b"]["count"], 1)
        self.assertEqual(result["books"][0]["bill_no"], self.bill["bill_no"])

    def test_previous_period_bill_can_match(self):
        self.import_csv(CSV_MATCH, period="2026-09")
        result = gstr2b.reconcile(self.conn, self.t, "2026-09")
        self.assertEqual(result["rows"][0]["match_status"], "matched")
        self.assertEqual(result["summary"]["books"]["count"], 0)
        self.assertEqual(result["books"], [])


class TestReviewAndComparison(Gstr2bBase):
    def test_review_status_audit_and_hold(self):
        self.import_csv(CSV_MATCH)
        line_id = gstr2b.reconcile(self.conn, self.t, "2026-08")["rows"][0]["id"]
        saved = gstr2b.review_line(self.conn, self.t, line_id, "itc_hold", "Supplier query", None)
        self.assertEqual(saved["status"], "itc_hold")
        result = gstr2b.reconcile(self.conn, self.t, "2026-08")
        row = result["rows"][0]
        self.assertEqual(row["review_status"], "itc_hold")
        self.assertEqual(row["review_note"], "Supplier query")
        self.assertEqual(result["summary"]["review"]["itc_hold"]["count"], 1)
        self.assertEqual(result["summary"]["review"]["itc_hold"]["tax"], 180000)
        comp = gstr2b.itc_comparison(self.conn, self.t, "2026-08", result)
        self.assertEqual(comp["hold"]["tax"], 180000)
        self.assertEqual(comp["status"], "ok")
        self.assertTrue(any("on hold" in w for w in comp["warnings"]))
        audit = self.conn.execute(
            "SELECT action, meta FROM audit_log WHERE action='gstr2b.review'").fetchone()
        self.assertIsNotNone(audit)
        self.assertIn("itc_hold", audit["meta"])

    def test_review_rejects_superseded_line(self):
        first = self.import_csv(CSV_MATCH)
        old_line = gstr2b.reconcile(self.conn, self.t, "2026-08")["rows"][0]["id"]
        self.import_csv(CSV_MISMATCH)
        with self.assertRaises(gstr2b.Gstr2bError) as ctx:
            gstr2b.review_line(self.conn, self.t, old_line, "accepted", "", None)
        self.assertEqual(ctx.exception.code, "SUPERSEDED_IMPORT")

    def test_review_is_tenant_scoped(self):
        self.import_csv(CSV_MATCH)
        line_id = gstr2b.reconcile(self.conn, self.t, "2026-08")["rows"][0]["id"]
        t2 = db.create_tenant(self.conn, "Other Co", "other", state_code="27")
        with self.assertRaises(gstr2b.Gstr2bError) as ctx:
            gstr2b.review_line(self.conn, t2, line_id, "accepted", "", None)
        self.assertEqual(ctx.exception.code, "LINE_NOT_FOUND")

    def test_review_rejects_invalid_status(self):
        self.import_csv(CSV_MATCH)
        line_id = gstr2b.reconcile(self.conn, self.t, "2026-08")["rows"][0]["id"]
        with self.assertRaises(gstr2b.Gstr2bError) as ctx:
            gstr2b.review_line(self.conn, self.t, line_id, "claimed", "", None)
        self.assertEqual(ctx.exception.code, "BAD_REVIEW_STATUS")

    def test_comparison_reports_gap(self):
        self.import_csv(CSV_MISSING)
        result = gstr2b.reconcile(self.conn, self.t, "2026-08")
        comp = gstr2b.itc_comparison(self.conn, self.t, "2026-08", result)
        self.assertEqual(comp["two_b_itc"], 90000)
        self.assertEqual(comp["books_itc"], 180000)
        self.assertEqual(comp["difference"], -90000)
        self.assertEqual(comp["status"], "check")
        self.assertTrue(comp["warnings"])


if __name__ == "__main__":
    unittest.main()
