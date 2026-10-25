"""End-to-end HTTP tests: login, CSRF, invoice creation, report pages.

Runs the real server against a temporary database — no mocks.
"""
from __future__ import annotations

import http.cookiejar
import json
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
from app import db, security, server
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
        inv = conn.execute("SELECT id FROM invoice WHERE tenant_id=? ORDER BY invoice_no DESC LIMIT 1",
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
        inv = conn.execute("SELECT id FROM invoice WHERE tenant_id=? ORDER BY invoice_no DESC LIMIT 1",
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
                             ("/export/daybook.csv", "Voucher"),
                             ("/export/bank-statement.csv?from=2026-04-01&to=2026-10-24", "Status")]:
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


    def test_16_settings_and_print_invoice(self):
        self.login()
        page = self.get("/settings")[1]
        self.assertIn("Business identity", page)
        token = self.csrf(page)

        bad_status, bad_body, _ = self.post("/settings", {
            "_csrf": token, "name": "Arthivio Demo Trading", "gstin": "BAD",
            "state_code": "27"})
        self.assertEqual(bad_status, 400)
        self.assertIn("GSTIN must be 15 characters", bad_body)

        status, body, _ = self.post("/settings", {
            "_csrf": token, "name": "Arthivio Demo Trading",
            "gstin": "27AABCS1429B1Z1", "state_code": "27",
            "address": "12, Laxmi Industrial Estate", "city": "Mumbai",
            "pincode": "400053", "phone": "+91 22 4890 1200",
            "email": "accounts@arthivio.test", "bank_name": "HDFC Bank",
            "bank_account": "50200012345678", "bank_ifsc": "HDFC0001234",
            "invoice_terms": "Payment due within 15 days."})
        self.assertEqual(status, 200)
        self.assertIn("Settings saved", body)
        self.assertIn("27AABCS1429B1Z1", body)

        conn = db.connect(self.db_path)
        inv = conn.execute(
            "SELECT id, invoice_no FROM invoice WHERE tenant_id=? ORDER BY invoice_no LIMIT 1",
            (self.tenant_id,)).fetchone()
        conn.close()
        status, page = self.get(f"/invoices/{inv['id']}/print")
        self.assertEqual(status, 200)
        self.assertIn("Tax Invoice", page)
        self.assertIn(inv["invoice_no"], page)
        self.assertIn("27AABCS1429B1Z1", page)
        self.assertIn("Amount in words", page)
        self.assertIn("HDFC Bank", page)
        self.assertIn("Print / Save as PDF", page)

    def test_17_gstr1_csv_export(self):
        self.login()
        status, body = self.get("/export/gstr1.csv?from=2026-04-01&to=2026-10-24")
        self.assertEqual(status, 200)
        for needle in ("B2B", "B2CS", "HSN", "CN TOTAL", "TOTAL", "Working export"):
            self.assertIn(needle, body)
        self.assertIn("Rate %", body)

    def test_18_gstr1_json_export(self):
        self.login()
        status, body = self.get("/export/gstr1.json?from=2026-04-01&to=2026-10-24")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["format"], "arthivio-gstr1-working-v1")
        self.assertTrue(data["b2b"])
        self.assertTrue(data["hsn"])
        self.assertIsInstance(data["totals"]["taxable"], str)
        self.assertIn("not an uploaded or filed", data["note"])


    def test_19_debit_note_from_bill(self):
        self.login()
        conn = db.connect(self.db_path)
        bill = conn.execute(
            "SELECT b.id, b.total_paise, bl.id AS line_id FROM bill b"
            " JOIN bill_line bl ON bl.bill_id=b.id"
            " WHERE b.tenant_id=? ORDER BY b.bill_date DESC, b.bill_no DESC LIMIT 1",
            (self.tenant_id,)).fetchone()
        before = acct.bill_outstanding(conn, self.tenant_id, bill["id"])
        conn.close()

        page = self.get(f"/bills/{bill['id']}")[1]
        token = self.csrf(page)
        status, body, final = self.post("/debit-notes", {
            "_csrf": token, "bill_id": bill["id"], "bill_line_id": bill["line_id"],
            "qty": "1", "note_date": "2026-10-24", "reason": "Web test debit return"})
        self.assertEqual(status, 200)
        self.assertIn("Debit note", body)
        self.assertIn("Outstanding", body)
        self.assertRegex(final, rf"/bills/{bill['id']}$")

        conn = db.connect(self.db_path)
        note = conn.execute(
            "SELECT * FROM debit_note WHERE tenant_id=? AND reason='Web test debit return'",
            (self.tenant_id,)).fetchone()
        after = acct.bill_outstanding(conn, self.tenant_id, bill["id"])
        conn.close()
        self.assertIsNotNone(note)
        self.assertEqual(after, before - note["total_paise"])

        s, notes_page = self.get("/debit-notes")
        self.assertIn("Web test debit return", notes_page)
        s, csv_body = self.get("/export/debit-notes.csv")
        self.assertIn("DBN-", csv_body)
        self.assertIn("Web test debit return", csv_body)

    def test_20_bank_recon_import_match_unmatch(self):
        self.login()
        conn = db.connect(self.db_path)
        bank_line = conn.execute(
            "SELECT l.id AS line_id, l.debit_paise, e.entry_date, e.narration, p.reference"
            " FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id"
            " LEFT JOIN payment p ON p.journal_entry_id=e.id"
            " JOIN account a ON a.id=l.account_id"
            " WHERE l.tenant_id=? AND a.code='1010' AND l.debit_paise>0"
            " AND p.reference IS NOT NULL AND p.reference<>''"
            " ORDER BY e.entry_date DESC LIMIT 1", (self.tenant_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(bank_line, "demo bank receipt not found")

        amount = f'{bank_line["debit_paise"] // 100}.{bank_line["debit_paise"] % 100:02d}'
        csv_text = ("Date,Description,Reference,Debit,Credit\n"
                    f'{bank_line["entry_date"]},NEFT CR DEMO,{bank_line["reference"]},,{amount}\n')
        page = self.get(f"/bank-recon?from={bank_line['entry_date']}&to={bank_line['entry_date']}")[1]
        token = self.csrf(page)
        status, body, final = self.post("/bank-recon/import", {
            "_csrf": token, "account_id": self._bank_account_id(),
            "csv_text": csv_text, "filename": "web-test.csv"})
        self.assertEqual(status, 200)
        self.assertIn("Imported 1 new line", body)
        self.assertIn("bank-recon", final)

        status, body, _ = self.post("/bank-recon/import", {
            "_csrf": token, "account_id": self._bank_account_id(),
            "csv_text": csv_text, "filename": "web-test.csv"})
        self.assertEqual(status, 200)
        self.assertIn("0 new line", body)
        self.assertIn("1 duplicate", body)

        conn = db.connect(self.db_path)
        stmt = conn.execute(
            "SELECT id FROM bank_statement_line WHERE tenant_id=? AND credit_paise=?",
            (self.tenant_id, bank_line["debit_paise"])).fetchone()
        conn.close()
        self.assertIsNotNone(stmt)

        status, body, _ = self.post("/bank-recon/match", {
            "_csrf": token, "statement_id": stmt["id"],
            "journal_line_id": bank_line["line_id"], "account_id": self._bank_account_id(),
            "from": bank_line["entry_date"], "to": bank_line["entry_date"]})
        self.assertEqual(status, 200)
        self.assertIn("Matched", body)
        self.assertIn(bank_line["reference"], body)

        status, body, _ = self.post("/bank-recon/unmatch", {
            "_csrf": token, "statement_id": stmt["id"],
            "account_id": self._bank_account_id(),
            "from": bank_line["entry_date"], "to": bank_line["entry_date"]})
        self.assertEqual(status, 200)
        self.assertIn("Match removed", body)

    def _bank_account_id(self) -> str:
        conn = db.connect(self.db_path)
        row = conn.execute("SELECT id FROM account WHERE tenant_id=? AND code='1010'",
                           (self.tenant_id,)).fetchone()
        conn.close()
        return row["id"]

    def test_21_gstr3b_page_and_csv(self):
        self.login()
        status, page = self.get("/reports/gstr3b?month=2026-06")
        self.assertEqual(status, 200)
        self.assertIn("GSTR-3B", page)
        self.assertIn("3.1 Outward supplies", page)
        self.assertIn("Reconciliation checks", page)
        self.assertIn("6/6 OK", page)
        self.assertIn("Cash payable", page)

        status, csv_body = self.get("/export/gstr3b.csv?month=2026-06")
        self.assertEqual(status, 200)
        self.assertIn("3.1(a)", csv_body)
        self.assertIn("Net eligible ITC", csv_body)
        self.assertIn("Cash payable", csv_body)
        self.assertIn("Reconciliation", csv_body)

        status, bad = self.get("/reports/gstr3b?month=2026-13")
        self.assertEqual(status, 200)
        self.assertIn("YYYY-MM", bad)

    def test_22_team_invite_accept_and_role_change(self):
        self.login()
        status, page = self.get("/users")
        self.assertEqual(status, 200)
        self.assertIn("Invite a team member", page)
        self.assertIn("Owner", page)
        token = self.csrf(page)
        status, created, _ = self.post("/users/invite", {
            "_csrf": token, "email": "web-invite@example.com",
            "full_name": "Web Invite", "role": "accountant"})
        self.assertEqual(status, 200)
        self.assertIn("Invite ready for", created)
        match = re.search(r'value="(http://[^"]+/invite/[A-Za-z0-9_-]+)"', created)
        self.assertIsNotNone(match)
        link = match.group(1)

        with urllib.request.urlopen(link, timeout=15) as r:
            public_page = r.read().decode("utf-8")
        self.assertIn("Join Arthivio Demo Trading", public_page)
        self.assertIn("Create password", public_page)

        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        body = urllib.parse.urlencode({
            "full_name": "Web Invite", "password": "weblongpassword",
            "confirm": "weblongpassword"}).encode()
        req = urllib.request.Request(link, data=body, method="POST")
        with opener.open(req, timeout=15) as r:
            accepted = r.read().decode("utf-8")
            final = r.geturl()
        self.assertTrue(final.endswith("/"))
        self.assertIn("Dashboard", accepted)

        conn = db.connect(self.db_path)
        user_id = conn.execute("SELECT id FROM user WHERE email='web-invite@example.com'").fetchone()["id"]
        conn.close()
        status, page = self.get("/users")
        token = self.csrf(page)
        status, body, _ = self.post("/users/role", {
            "_csrf": token, "user_id": user_id, "role": "manager"})
        self.assertEqual(status, 200)
        self.assertIn("Team updated", body)

    def test_23_shareable_statement_and_revoke(self):
        self.login()
        status, page = self.get(f"/customers/{self.customer_id}")
        self.assertEqual(status, 200)
        self.assertIn("Share and print", page)
        token = self.csrf(page)
        status, page, _ = self.post(f"/customers/{self.customer_id}/share", {
            "_csrf": token, "from": "2026-04-01", "to": "2026-10-31", "days": "7"})
        self.assertEqual(status, 200)
        self.assertIn("Share link created", page)
        match = re.search(r'value="(http://[^"]+/share/statement/[A-Za-z0-9_-]+)"', page)
        self.assertIsNotNone(match)
        link = match.group(1)

        with urllib.request.urlopen(link, timeout=15) as r:
            shared = r.read().decode("utf-8")
            headers = dict(r.headers)
        self.assertIn("Statement of account", shared)
        self.assertIn("Print / Save PDF", shared)
        self.assertIn("noindex", headers.get("X-Robots-Tag", ""))

        conn = db.connect(self.db_path)
        share_id = conn.execute(
            "SELECT id FROM statement_share WHERE tenant_id=? ORDER BY created_at DESC LIMIT 1",
            (self.tenant_id,)).fetchone()["id"]
        conn.close()
        status, body, _ = self.post("/shares/revoke", {
            "_csrf": token, "share_id": share_id,
            "party_type": "customer", "party_id": self.customer_id,
            "from": "2026-04-01", "to": "2026-10-31"})
        self.assertEqual(status, 200)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(link, timeout=15)
        self.assertEqual(ctx.exception.code, 404)

    def test_24_gstr2b_import_and_export(self):
        self.login()
        status, page = self.get("/gstr2b")
        self.assertEqual(status, 200)
        self.assertIn("GSTR-2B reconciliation", page)
        self.assertIn("Import GSTR-2B working CSV", page)
        csv_text = (
            "GSTIN,Supplier Name,Invoice No,Invoice Date,Taxable Value,IGST,CGST,SGST,Cess,Invoice Value\n"
            "27AAACL1234C1Z5,Loom House Pvt Ltd,LH-2026-097,2026-08-10,42000.00,0,3780.00,3780.00,0,49560.00\n")
        token = self.csrf(page)
        status, body, final = self.post("/gstr2b/import", {
            "_csrf": token, "month": "2026-08", "csv_text": csv_text,
            "filename": "web-gstr2b.csv"})
        self.assertEqual(status, 200)
        self.assertIn("LH-2026-097", body)
        self.assertIn("MATCHED", body)
        self.assertIn("2026-08", final)

        status, csv_body = self.get("/export/gstr2b.csv?month=2026-08")
        self.assertEqual(status, 200)
        self.assertIn("GSTR-2B", csv_body)
        self.assertIn("LH-2026-097", csv_body)
        self.assertIn("Books tax", csv_body)

        status, body, _ = self.post("/gstr2b/import", {
            "_csrf": token, "month": "2026-08", "csv_text": csv_text,
            "filename": "web-gstr2b.csv"})
        self.assertEqual(status, 200)
        self.assertIn("Duplicate", body)
        self.assertNotIn("Imported 0", body)

        status, body, _ = self.post("/gstr2b/import", {
            "_csrf": token, "month": "2026-08", "csv_text": "not,a,valid\nfile\n",
            "filename": "bad.csv"})
        self.assertEqual(status, 400)
        self.assertIn("header", body.lower())

    def test_25_business_switcher_checks_membership(self):
        self.login()
        conn = db.connect(self.db_path)
        t2 = db.create_tenant(conn, "Second Co", "second", state_code="27")
        owner_id = conn.execute("SELECT id FROM user WHERE email='owner@arthivio.test'").fetchone()["id"]
        security.add_membership(conn, t2, owner_id, "owner")
        conn.close()

        status, page = self.get("/businesses")
        self.assertEqual(status, 200)
        self.assertIn("Arthivio Demo Trading", page)
        self.assertIn("Second Co", page)
        token = self.csrf(page)
        status, body, _ = self.post("/switch", {"_csrf": token, "tenant_id": t2})
        self.assertEqual(status, 200)
        self.assertIn("Second Co", body)
        status, dashboard = self.get("/")
        self.assertIn("Second Co", dashboard)

        status, page = self.get("/businesses")
        token = self.csrf(page)
        status, body, _ = self.post("/switch", {"_csrf": token, "tenant_id": "not-a-membership"})
        self.assertEqual(status, 400)
        self.assertIn("do not have active access", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
