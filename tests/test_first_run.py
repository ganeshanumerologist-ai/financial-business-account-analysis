"""First-run setup tests.

The first account created on an empty installation becomes the owner. Setup must
then close permanently, and it must reject a cross-site form without a valid
setup token.
"""
from __future__ import annotations

import http.cookiejar
import os
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from app import db, security, server


class FirstRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="arthivio-first-run-")
        cls.db_path = os.path.join(cls.tmp, "first-run.db")
        cls.old_db_path = server.DB_PATH
        server.DB_PATH = cls.db_path
        conn = db.connect(cls.db_path)
        db.init_db(conn)
        conn.close()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.DB_PATH = cls.old_db_path

    def setUp(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        with self.opener.open(self.url(path), timeout=15) as r:
            return r.status, r.read().decode("utf-8"), r.geturl()

    def post(self, path, data):
        body = urllib.parse.urlencode(data, doseq=True).encode()
        req = urllib.request.Request(self.url(path), data=body, method="POST")
        try:
            with self.opener.open(req, timeout=15) as r:
                return r.status, r.read().decode("utf-8"), r.geturl()
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read().decode("utf-8"), e.geturl()
            finally:
                e.close()

    def token(self, page):
        m = re.search(r'name="_setup_csrf" value="([^"]+)"', page)
        self.assertIsNotNone(m, "setup CSRF token missing")
        return m.group(1)

    def test_01_empty_install_shows_setup(self):
        status, page, final = self.get("/setup")
        self.assertEqual(status, 200)
        self.assertIn("Create your business", page)
        self.assertIn("First run", page)
        self.assertIn('action="/setup"', page)
        self.assertIn("27ABCDE1234F1Z5", page)

    def test_02_login_redirects_to_setup_when_empty(self):
        status, page, final = self.get("/login")
        self.assertEqual(status, 200)
        self.assertIn("Create your business", page)

    def test_03_setup_requires_token(self):
        status, page, _ = self.post("/setup", {
            "full_name": "Vicky Owner", "business_name": "Vicky Traders",
            "email": "vicky@example.test", "state_code": "27",
            "gstin": "", "password": "VeryLongPassword!2026",
            "confirm_password": "VeryLongPassword!2026",
        })
        self.assertEqual(status, 403)
        self.assertIn("expired", page)

    def test_04_validation_errors(self):
        status, page, _ = self.get("/setup")
        token = self.token(page)
        status, page, _ = self.post("/setup", {
            "_setup_csrf": token, "full_name": "Vicky Owner",
            "business_name": "Vicky Traders", "email": "vicky@example.test",
            "state_code": "27", "gstin": "",
            "password": "short", "confirm_password": "short",
        })
        self.assertEqual(status, 400)
        self.assertIn("at least 12 characters", page)

        status, page, _ = self.post("/setup", {
            "_setup_csrf": token, "full_name": "Vicky Owner",
            "business_name": "Vicky Traders", "email": "vicky@example.test",
            "state_code": "27", "gstin": "",
            "password": "VeryLongPassword!2026",
            "confirm_password": "DifferentPassword!2026",
        })
        self.assertEqual(status, 400)
        self.assertIn("do not match", page)

        status, page, _ = self.post("/setup", {
            "_setup_csrf": token, "full_name": "Vicky Owner",
            "business_name": "Vicky Traders", "email": "vicky@example.test",
            "state_code": "27", "gstin": "BAD",
            "password": "VeryLongPassword!2026",
            "confirm_password": "VeryLongPassword!2026",
        })
        self.assertEqual(status, 400)
        self.assertIn("GSTIN must be 15 characters", page)

    def test_05_create_owner_and_sign_in(self):
        status, page, _ = self.get("/setup")
        token = self.token(page)
        status, page, final = self.post("/setup", {
            "_setup_csrf": token, "full_name": "Vicky Owner",
            "business_name": "Vicky Traders", "email": "vicky@example.test",
            "state_code": "27", "gstin": "27ABCDE1234F1Z5",
            "password": "VeryLongPassword!2026",
            "confirm_password": "VeryLongPassword!2026",
        })
        self.assertEqual(status, 200)
        self.assertIn("Dashboard", page)
        self.assertIn("Revenue", page)
        self.assertTrue(final.endswith("/"))

        conn = db.connect(self.db_path)
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM user").fetchone()[0], 1)
            tenant = conn.execute(
                "SELECT * FROM tenant WHERE name='Vicky Traders'").fetchone()
            self.assertIsNotNone(tenant)
            self.assertEqual(tenant["gstin"], "27ABCDE1234F1Z5")
            user = conn.execute(
                "SELECT * FROM user WHERE email='vicky@example.test'").fetchone()
            self.assertIsNotNone(user)
            membership = conn.execute(
                "SELECT * FROM membership WHERE tenant_id=? AND user_id=?",
                (tenant["id"], user["id"])).fetchone()
            self.assertEqual(membership["role"], "owner")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM audit_log"
                             " WHERE action='setup.owner_created'").fetchone()[0], 1)
            self.assertGreater(
                conn.execute("SELECT COUNT(*) FROM account WHERE tenant_id=?",
                             (tenant["id"],)).fetchone()[0], 0)
        finally:
            conn.close()

        # A new browser session can sign in with the owner credentials.
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        body = urllib.parse.urlencode({
            "email": "vicky@example.test", "password": "VeryLongPassword!2026",
        }).encode()
        req = urllib.request.Request(self.url("/login"), data=body, method="POST")
        with opener.open(req, timeout=15) as r:
            self.assertIn("Dashboard", r.read().decode("utf-8"))

    def test_06_setup_closes_permanently(self):
        status, page, _ = self.get("/setup")
        self.assertIn("Sign in", page)
        self.assertNotIn("Create your business", page)

        status, page, _ = self.post("/setup", {
            "full_name": "Attacker", "business_name": "Attacker Co",
            "email": "attacker@example.test", "state_code": "27",
            "gstin": "", "password": "VeryLongPassword!2026",
            "confirm_password": "VeryLongPassword!2026",
        })
        self.assertIn("Sign in", page)
        conn = db.connect(self.db_path)
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM user").fetchone()[0], 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
