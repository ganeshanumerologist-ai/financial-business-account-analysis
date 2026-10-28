"""Power BI static import pack tests: manifest, hashes and tenant isolation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import analytics, bi, db


class PowerBiPackTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "BI Co", "bi-co", state_code="27")
        self.tenant = self.conn.execute("SELECT * FROM tenant WHERE id=?", (self.t,)).fetchone()
        self.post("1000", "4000", 100000, "2026-04-10", "Sale")
        self.post("6000", "1000", 40000, "2026-05-10", "Rent")

    def tearDown(self):
        self.conn.close()

    def post(self, debit_code: str, credit_code: str, amount: int,
             entry_date: str, narration: str):
        return acct.post_journal(
            self.conn, self.t, entry_date, narration,
            [{"account_id": db.account_id(self.conn, self.t, debit_code),
              "debit": amount, "credit": 0},
             {"account_id": db.account_id(self.conn, self.t, credit_code),
              "debit": 0, "credit": amount}],
            "manual")

    def pack(self, date_from="2026-04-01", date_to="2026-06-30"):
        data = bi.build_pack(self.conn, self.tenant, date_from, date_to)
        self.assertTrue(data.startswith(b"PK"))
        return data

    def test_pack_contents_and_manifest_hashes(self):
        data = self.pack()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            for expected in ("README.md", "manifest.json", "arthivio-analytics.json",
                             "arthivio-metric-catalog.json", "fact_journal.csv",
                             "fact_monthly.csv", "dim_account.csv", "dim_party.csv",
                             "power-query/ArthivioAnalytics.m"):
                self.assertIn(expected, names)
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest["pack"], "arthivio-powerbi-pack")
            self.assertEqual(manifest["schema_version"], "1.0")
            self.assertTrue(manifest["actuals_only"])
            self.assertEqual(manifest["source_money_unit"], "integer paise")
            self.assertEqual(manifest["period"], {"from": "2026-04-01", "to": "2026-06-30"})
            for name, meta in manifest["files"].items():
                self.assertEqual(meta["sha256"],
                                 hashlib.sha256(zf.read(name)).hexdigest())
            readme = zf.read("README.md").decode("utf-8")
            self.assertIn("No estimate or forecast", readme)
            self.assertIn("`.pbix`", readme)
            self.assertIn("not", readme)

    def test_facts_are_integer_paise_and_reconcile_to_analytics(self):
        data = self.pack()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            journal = list(csv.DictReader(io.StringIO(
                zf.read("fact_journal.csv").decode("utf-8"))))
            self.assertEqual(len(journal), 4)
            for row in journal:
                int(row["debit_paise"])
                int(row["credit_paise"])
                int(row["signed_paise"])
            monthly = list(csv.DictReader(io.StringIO(
                zf.read("fact_monthly.csv").decode("utf-8"))))
            self.assertEqual(sum(int(r["revenue_paise"]) for r in monthly), 100000)
            self.assertEqual(sum(int(r["expense_paise"]) for r in monthly), 40000)
            self.assertEqual(sum(int(r["profit_paise"]) for r in monthly), 60000)
            overview = json.loads(zf.read("arthivio-analytics.json"))
            self.assertEqual(overview["metrics"]["revenue_paise"], 100000)
            self.assertEqual(overview["metrics"]["expense_paise"], 40000)
            self.assertEqual(overview["metrics"]["net_profit_paise"], 60000)

    def test_other_tenant_gets_no_rows(self):
        other = db.create_tenant(self.conn, "Other BI", "other-bi", state_code="27")
        other_row = self.conn.execute("SELECT * FROM tenant WHERE id=?", (other,)).fetchone()
        data = bi.build_pack(self.conn, other_row, "2026-04-01", "2026-06-30")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            journal = list(csv.DictReader(io.StringIO(
                zf.read("fact_journal.csv").decode("utf-8"))))
            self.assertEqual(journal, [])
            overview = json.loads(zf.read("arthivio-analytics.json"))
            self.assertEqual(overview["metrics"]["revenue_paise"], 0)

    def test_invalid_date_and_filename(self):
        with self.assertRaises(analytics.AnalyticsError) as ctx:
            bi.build_pack(self.conn, self.tenant, "bad", "2026-06-30")
        self.assertEqual(ctx.exception.code, "BAD_DATE")
        self.assertEqual(bi.filename(self.tenant, "2026-06-30"),
                         "arthivio-powerbi-pack-bi-co-2026-06-30.zip")


if __name__ == "__main__":
    unittest.main()
