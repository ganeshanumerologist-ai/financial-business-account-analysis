"""End-to-end HTTP tests: login, CSRF, invoice creation, report pages.

Runs the real server against a temporary database — no mocks.
"""
from __future__ import annotations

import http.cookiejar
import os
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import db, server
from app.demo import DEMO_PASSWORD, seed_demo


class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="arthivio-test-")
        cls.db_path = os.path.join(cls.tmp, "test.db")
        server.DB_PATH = cls.db_path
        server.BACKUP_DIR = os.path.join(cls.tmp, "backups")
        conn = db.connect(cls.db_path)
        db.init_db(conn)
        seed_demo(conn)
        cls.tenant_id = conn.execute("SELECT id FROM tenant WHERE slug='arthivio-demo'").fetchone()["id"]
        cls.customer_id = conn.execute("SELECT id FROM customer WHERE tenant_id=? LIMIT 1", (cls.tenant_id,)).fetchone()["id"]
        cls.item_id = conn.execute("SELECT id FROM item WHERE tenant_id=? AND track_stock=1 LIMIT 1", (cls.tenant_id,)).fetchone()["id"]
        conn.close()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

        cls.jar = http.cookiejar.CookieJar()
        cls.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cls.jar))

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    # ---------- helpers ----------
    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        with self.opener.open(self.url(path), timeout=15) as r:
            return r.status, r.read().decode("utf-8")

    def post(self, path, data: dict):
        body = urllib.parse.urlencode(data, doseq=True).encode()
        req = urllib.request.Request(self.url(path), data=body, method="POST")
        try:
            with self.opener.open(req, timeout=15) as r:
                return r.status, r.read().decode("utf-8"), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), e.geturl()

    def csrf(self, page: str) -> str:
        m = re.search(r'name="_csrf" value="([^"]+)"', page)
        self.assertIsNotNone(m, "CSRF token missing from page")
        return m.group(1)

    def login(self):
        status, body, _ = self.post("/login", {"email": "owner@arthivio.test", "password": DEMO_PASSWORD})
        self.assertEqual(status, 200)
        self.assertIn("Dashboard", body)

    # ---------- tests ----------
    def test_01_login_required(self):
        s, body = self.get("/dashboard-does-not-exist")
        self.assertIn("Sign in", body)

    def test_02_bad_password_rejected(self):
        status, body, _ = self.post("/login", {"email": "owner@arthivio.test", "password": "wrong-password"})
        self.assertEqual(status, 401)
        self.assertIn("Invalid email or password", body)

    def test_03_login_and_dashboard(self):
        self.login()
        s, body = self.get("/")
        self.assertEqual(s, 200)
        self.assertIn("Revenue", body)
        self.assertIn("Net profit", body)
        self.assertNotIn("None", body)
        self.assertNotIn("NaN", body)

    def test_04_reports_render_and_balance(self):
        self.login()
        s, tb = self.get("/reports/trial-balance")
        self.assertIn("Balanced", tb)
        self.assertNotIn("Out of balance", tb)
        s, pnl = self.get("/reports/pnl")
        self.assertIn("NET PROFIT", pnl)
        s, bs = self.get("/reports/balance-sheet")
        self.assertIn("A = L + E", bs)
        s, ledger = self.get("/ledger")
        self.assertIn("Closing balance", ledger)

    def test_05_invoice_creation_flows_to_reports(self):
        self.login()
        s, page = self.get("/invoices/new")
        token = self.csrf(page)
        status, body, final = self.post("/invoices", {
            "_csrf": token,
            "customer_id": self.customer_id,
            "invoice_date": "2026-10-22",
            "place_of_supply": "27",
            "rounding": "1",
            "item_id": [self.item_id],
            "qty": ["2"],
            "price": [""],
            "discount": ["0"],
        })
        self.assertEqual(status, 200)
        self.assertIn("Invoice total", body)
        self.assertRegex(final, r"/invoices/[0-9a-f]{32}$")

        s, tb = self.get("/reports/trial-balance")
        self.assertIn("Balanced", tb)
        s, pnl = self.get("/reports/pnl")
        self.assertIn("Sales Revenue", pnl)

    def test_06_csrf_required(self):
        self.login()
        status, body, _ = self.post("/invoices", {
            "customer_id": self.customer_id, "invoice_date": "2026-10-22",
            "item_id": [self.item_id], "qty": ["1"], "discount": ["0"],
        })
        self.assertEqual(status, 403)
        self.assertIn("CSRF", body)

    def test_07_customer_creation(self):
        self.login()
        s, page = self.get("/customers")
        token = self.csrf(page)
        status, _, _ = self.post("/customers", {"_csrf": token, "name": "Test Buyer Pvt Ltd",
                                                "phone": "9999999999", "state_code": "27", "gstin": ""})
        self.assertEqual(status, 200)
        s, page = self.get("/customers")
        self.assertIn("Test Buyer Pvt Ltd", page)

    def test_08_invoice_not_visible_across_tenants(self):
        self.login()
        conn = db.connect(self.db_path)
        other_tenant = db.create_tenant(conn, "Other Books", "other-books", state_code="29")
        from app import security
        uid = security.create_user(conn, "other@arthivio.test", "AnotherLongPass!2026", "Other")
        security.add_membership(conn, other_tenant, uid, "owner")
        foreign_invoice = conn.execute(
            "SELECT id FROM invoice WHERE tenant_id=? LIMIT 1", (self.tenant_id,)).fetchone()["id"]
        conn.close()

        other_jar = http.cookiejar.CookieJar()
        other = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(other_jar))
        req = urllib.request.Request(self.url("/login"),
                                     data=urllib.parse.urlencode({"email": "other@arthivio.test",
                                                                  "password": "AnotherLongPass!2026"}).encode(),
                                     method="POST")
        with other.open(req, timeout=15) as r:
            r.read()
        with other.open(self.url(f"/invoices/{foreign_invoice}"), timeout=15) as r:
            body = r.read().decode()
        self.assertIn("Invoice not found", body)


    def test_09_customer_statement(self):
        self.login()
        s, page = self.get("/customers")
        self.assertIn("Balance due", page)
        m = re.search(r'href="(/customers/[0-9a-f]{32})"', page)
        self.assertIsNotNone(m, "customer statement link missing")
        s, st = self.get(m.group(1))
        self.assertIn("Closing balance", st)
        self.assertIn("Statement", st)
        self.assertIn('href="/invoices/', st)


    def test_10_receipt_posts_and_reduces_outstanding(self):
        self.login()
        conn = db.connect(self.db_path)
        inv = conn.execute("SELECT id FROM invoice WHERE tenant_id=? ORDER BY created_at DESC LIMIT 1",
                           (self.tenant_id,)).fetchone()
        before = acct.invoice_outstanding(conn, self.tenant_id, inv["id"])
        conn.close()
        self.assertGreater(before, 100)

        page = self.get(f"/invoices/{inv['id']}")[1]
        token = self.csrf(page)
        status, body, _ = self.post("/receipts", {
            "_csrf": token, "invoice_id": inv["id"], "amount": "1.00", "mode": "bank",
            "payment_date": "2026-10-23", "reference": "TEST-RCPT"})
        self.assertEqual(status, 200)
        self.assertIn("Outstanding", body)

        conn = db.connect(self.db_path)
        after = acct.invoice_outstanding(conn, self.tenant_id, inv["id"])
        conn.close()
        self.assertEqual(after, before - 100)

    def test_11_bill_and_vendor_payment(self):
        self.login()
        page = self.get("/vendors")[1]
        token = self.csrf(page)
        self.post("/vendors", {"_csrf": token, "name": "Test Supplier", "phone": "",
                               "state_code": "27", "gstin": ""})
        conn = db.connect(self.db_path)
        vendor = conn.execute("SELECT id FROM vendor WHERE tenant_id=? AND name='Test Supplier'",
                              (self.tenant_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(vendor)

        page = self.get("/bills/new")[1]
        token = self.csrf(page)
        status, body, final = self.post("/bills", {
            "_csrf": token, "vendor_id": vendor["id"], "bill_date": "2026-10-23",
            "vendor_bill_no": "T-1", "place_of_supply": "27",
            "item_id": [self.item_id], "qty": ["2"], "price": ["50"], "discount": ["0"]})
        self.assertEqual(status, 200)
        self.assertIn("Bill total", body)
        self.assertRegex(final, r"/bills/[0-9a-f]{32}$")

        bill_id = final.rsplit("/", 1)[-1]
        token = self.csrf(body)
        status, paid, _ = self.post("/receipts", {
            "_csrf": token, "direction": "payment", "bill_id": bill_id,
            "amount": "105.00", "mode": "bank", "payment_date": "2026-10-23"})
        self.assertEqual(status, 200)
        self.assertIn("Outstanding ₹0.00", paid)

    def test_12_credit_note_from_invoice(self):
        self.login()
        conn = db.connect(self.db_path)
        inv = conn.execute("SELECT id FROM invoice WHERE tenant_id=? ORDER BY created_at DESC LIMIT 1",
                           (self.tenant_id,)).fetchone()
        line = conn.execute("SELECT id FROM invoice_line WHERE invoice_id=? LIMIT 1",
                            (inv["id"],)).fetchone()
        conn.close()

        page = self.get(f"/invoices/{inv['id']}")[1]
        token = self.csrf(page)
        status, body, _ = self.post("/credit-notes", {
            "_csrf": token, "invoice_id": inv["id"], "invoice_line_id": line["id"],
            "qty": "1", "note_date": "2026-10-23", "reason": "Web test return"})
        self.assertEqual(status, 200)
        self.assertIn("Credit note", body)

        conn = db.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) c FROM credit_note WHERE tenant_id=? AND reason='Web test return'",
                             (self.tenant_id,)).fetchone()["c"]
        conn.close()
        self.assertEqual(count, 1)

    def test_13_csv_exports(self):
        self.login()
        for path, needle in [("/export/trial-balance.csv", "TOTAL"),
                             ("/export/gst-sales.csv", "Taxable"),
                             ("/export/invoices.csv", "Outstanding"),
                             ("/export/daybook.csv", "Voucher")]:
            status, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertIn(needle, body, path)

    def test_14_new_pages_render(self):
        self.login()
        pages = {
            "/receipts": "Advance receipt",
            "/bills": "New bill",
            "/vendors": "Add vendor",
            "/daybook": "Day book",
            "/journal": "Post journal",
            "/reports/ar-ageing": "Receivables ageing",
            "/reports/ap-ageing": "Payables ageing",
            "/reports/gst": "Output tax",
            "/credit-notes": "credit note",
            "/backup": "Backup",
        }
        for path, needle in pages.items():
            status, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertIn(needle, body, path)
            self.assertNotIn("Internal server error", body, path)

    def test_15_backup_over_http(self):
        self.login()
        page = self.get("/backup")[1]
        token = self.csrf(page)
        status, body, final = self.post("/backup", {"_csrf": token})
        self.assertEqual(status, 200)
        self.assertIn("Backup created and verified", body)
        self.assertIn("done=1", final)
        backup_dir = os.path.join(self.tmp, "backups")
        self.assertTrue(os.path.isdir(backup_dir))
        self.assertTrue([f for f in os.listdir(backup_dir) if f.endswith(".db")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
