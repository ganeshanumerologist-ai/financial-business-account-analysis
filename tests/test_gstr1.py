"""GSTR-1 working export and print-invoice data tests. stdlib unittest only."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import db, demo, money

FROM = "2026-04-01"
TO = "2026-10-24"


class Gstr1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="arthivio-gstr1-")
        cls.conn = db.connect(os.path.join(cls.tmp, "gstr1.db"))
        db.init_db(cls.conn)
        demo.seed_demo(cls.conn)
        cls.tid = cls.conn.execute(
            "SELECT id FROM tenant WHERE slug='arthivio-demo'").fetchone()["id"]

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def invoice_totals(self):
        return self.conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(sub_total_paise),0) taxable,"
            " COALESCE(SUM(tax_paise),0) tax FROM invoice"
            " WHERE tenant_id=? AND status='posted' AND invoice_date BETWEEN ? AND ?",
            (self.tid, FROM, TO)).fetchone()

    def test_tax_split_reconciles_for_every_invoice(self):
        rows = self.conn.execute(
            "SELECT id, invoice_no, tax_paise FROM invoice WHERE tenant_id=?",
            (self.tid,)).fetchall()
        self.assertGreater(len(rows), 0)
        for r in rows:
            br = acct.invoice_tax_breakup(self.conn, self.tid, r["id"])
            self.assertEqual(br["cgst"] + br["sgst"] + br["igst"], r["tax_paise"],
                             f'{r["invoice_no"]} tax split must equal invoice tax')
            self.assertEqual(sum(g["taxable"] for g in br["groups"]),
                             br["invoice"]["sub_total_paise"])
            self.assertEqual(sum(g["cgst"] + g["sgst"] + g["igst"] for g in br["groups"]),
                             r["tax_paise"])

    def test_gstr1_totals_match_posted_invoices(self):
        g = acct.gstr1_data(self.conn, self.tid, FROM, TO)
        expected = self.invoice_totals()
        self.assertEqual(g["totals"]["taxable"], expected["taxable"])
        self.assertEqual(g["totals"]["cgst"] + g["totals"]["sgst"] + g["totals"]["igst"],
                         expected["tax"])
        self.assertEqual(g["docs"]["invoices"], expected["n"])

    def test_b2b_and_b2cs_split(self):
        g = acct.gstr1_data(self.conn, self.tid, FROM, TO)
        registered = self.conn.execute(
            "SELECT COUNT(DISTINCT i.id) n FROM invoice i JOIN customer c ON c.id=i.customer_id"
            " WHERE i.tenant_id=? AND i.status='posted' AND i.invoice_date BETWEEN ? AND ?"
            " AND TRIM(COALESCE(c.gstin,'')) <> ''", (self.tid, FROM, TO)).fetchone()["n"]
        unregistered = self.conn.execute(
            "SELECT COUNT(*) n FROM invoice i JOIN customer c ON c.id=i.customer_id"
            " WHERE i.tenant_id=? AND i.status='posted' AND i.invoice_date BETWEEN ? AND ?"
            " AND TRIM(COALESCE(c.gstin,'')) = ''", (self.tid, FROM, TO)).fetchone()["n"]
        self.assertEqual(len({r["invoice_no"] for r in g["b2b"]}), registered)
        self.assertEqual(sum(r["invoices"] for r in g["b2cs"]), unregistered)
        for r in g["b2b"]:
            self.assertTrue(r["gstin"])
            self.assertIn(r["reverse_charge"], ("N", "Y"))

    def test_hsn_summary_matches_totals(self):
        g = acct.gstr1_data(self.conn, self.tid, FROM, TO)
        self.assertEqual(sum(h["taxable"] for h in g["hsn"]), g["totals"]["taxable"])
        self.assertEqual(sum(h["cgst"] for h in g["hsn"]), g["totals"]["cgst"])
        self.assertEqual(sum(h["sgst"] for h in g["hsn"]), g["totals"]["sgst"])
        self.assertEqual(sum(h["igst"] for h in g["hsn"]), g["totals"]["igst"])
        self.assertTrue(all(h["hsn"] and h["hsn"] != "NOT SET" for h in g["hsn"]))

    def test_credit_notes_reported_separately(self):
        g = acct.gstr1_data(self.conn, self.tid, FROM, TO)
        expected = self.conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(sub_total_paise),0) taxable,"
            " COALESCE(SUM(tax_paise),0) tax FROM credit_note"
            " WHERE tenant_id=? AND note_date BETWEEN ? AND ?",
            (self.tid, FROM, TO)).fetchone()
        self.assertGreater(expected["n"], 0)
        self.assertEqual(len(g["credit_notes"]), expected["n"])
        self.assertEqual(g["credit_note_totals"]["taxable"], expected["taxable"])
        self.assertEqual(sum(r["cgst"] + r["sgst"] + r["igst"] for r in g["credit_notes"]),
                         expected["tax"])
        for r in g["credit_notes"]:
            self.assertIn(r["section"], ("CDNR", "CDNUR"))

    def test_missing_gstin_is_flagged(self):
        conn = db.connect(":memory:")
        db.init_db(conn)
        tid = db.create_tenant(conn, "No GST Co", "no-gst", state_code="27")
        g = acct.gstr1_data(conn, tid, FROM, TO)
        self.assertTrue(any("Supplier GSTIN" in w for w in g["warnings"]))
        conn.close()


class MigrationTest(unittest.TestCase):
    def test_legacy_tenant_gets_new_columns_without_data_loss(self):
        conn = db.connect(":memory:")
        conn.executescript(
            "CREATE TABLE tenant (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,"
            " state_code TEXT NOT NULL DEFAULT '27', currency TEXT NOT NULL DEFAULT 'INR',"
            " fiscal_year_start_month INTEGER NOT NULL DEFAULT 4,"
            " status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL);"
            "INSERT INTO tenant (id, name, slug, created_at)"
            " VALUES ('legacy1','Legacy Co','legacy-co','2026-01-01T00:00:00+00:00');")
        db.init_db(conn)
        row = conn.execute("SELECT * FROM tenant WHERE id='legacy1'").fetchone()
        self.assertEqual(row["name"], "Legacy Co")
        for col in ("gstin", "address", "city", "state_name", "pincode", "phone", "email",
                    "bank_name", "bank_account", "bank_ifsc", "invoice_terms"):
            self.assertIn(col, row.keys())
            self.assertEqual(row[col], "")
        db.init_db(conn)  # idempotent
        self.assertEqual(conn.execute("SELECT COUNT(*) c FROM tenant").fetchone()["c"], 1)
        conn.close()


class WordsTest(unittest.TestCase):
    def test_amount_in_words(self):
        self.assertEqual(money.amount_in_words(0), "Zero Rupees Only")
        self.assertEqual(money.amount_in_words(100), "One Rupee Only")
        self.assertEqual(money.amount_in_words(11800), "One Hundred Eighteen Rupees Only")
        self.assertEqual(money.amount_in_words(1004000), "Ten Thousand Forty Rupees Only")
        self.assertEqual(money.amount_in_words(145486430),
                         "Fourteen Lakh Fifty Four Thousand Eight Hundred Sixty Four"
                         " Rupees and Thirty Paise Only")
        self.assertEqual(money.amount_in_words(12345678),
                         "One Lakh Twenty Three Thousand Four Hundred Fifty Six"
                         " Rupees and Seventy Eight Paise Only")

    def test_negative_amount_in_words(self):
        self.assertTrue(money.amount_in_words(-100).startswith("Minus "))


if __name__ == "__main__":
    unittest.main()
