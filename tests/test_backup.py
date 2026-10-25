"""Backup + restore-verification drill tests."""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import backup, db


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="arthivio-backup-")
        self.db_path = os.path.join(self.tmp, "books.db")
        conn = db.connect(self.db_path)
        db.init_db(conn)
        self.tenant = db.create_tenant(conn, "Backup Co", "backup-co", state_code="27")
        bank = db.account_id(conn, self.tenant, "1010")
        equity = db.account_id(conn, self.tenant, "3000")
        acct.post_journal(conn, self.tenant, "2026-04-01", "Opening capital", [
            {"account_id": bank, "debit": 1000000, "credit": 0},
            {"account_id": equity, "debit": 0, "credit": 1000000},
        ], "opening")
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_backup_is_verified_and_recorded(self):
        result = backup.create_backup(self.db_path, os.path.join(self.tmp, "backups"))
        self.assertEqual(result["status"], "verified")
        self.assertTrue(os.path.exists(result["path"]))
        self.assertEqual(len(result["sha256"]), 64)
        self.assertGreater(result["size_bytes"], 0)
        self.assertTrue(result["verification"]["ok"])
        self.assertIn("integrity_check: ok", result["verification"]["checks"])
        self.assertIn("journals balanced: 1 tenant(s)", result["verification"]["checks"])

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        runs = backup.recent_runs(conn)
        conn.close()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "verified")
        self.assertEqual(runs[0]["sha256"], result["sha256"])

    def test_backup_table_list_covers_all_persistent_tables(self):
        conn = sqlite3.connect(self.db_path)
        actual = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        conn.close()
        self.assertEqual(set(backup.TABLES), actual - {"session", "backup_run"})

    def test_restore_verification_matches_source(self):
        result = backup.create_backup(self.db_path, os.path.join(self.tmp, "backups"))
        check = backup.verify_backup(result["path"], self.db_path)
        self.assertTrue(check["ok"], check["errors"])
        self.assertIn("row counts match source", check["checks"])
        self.assertEqual(check["counts"]["journal_line"], 2)

    def test_corrupt_backup_fails_verification(self):
        result = backup.create_backup(self.db_path, os.path.join(self.tmp, "backups"))
        corrupt = os.path.join(self.tmp, "corrupt.db")
        with open(result["path"], "rb") as src, open(corrupt, "wb") as dst:
            dst.write(src.read(200))
        check = backup.verify_backup(corrupt)
        self.assertFalse(check["ok"])
        self.assertTrue(check["errors"])

    def test_row_mismatch_is_detected(self):
        result = backup.create_backup(self.db_path, os.path.join(self.tmp, "backups"))
        tampered = os.path.join(self.tmp, "tampered.db")
        shutil.copyfile(result["path"], tampered)
        conn = sqlite3.connect(tampered)
        conn.execute("DELETE FROM journal_line WHERE rowid=1")
        conn.commit()
        conn.close()
        check = backup.verify_backup(tampered, self.db_path)
        self.assertFalse(check["ok"])
        self.assertTrue(any("mismatch" in e or "unbalanced" in e for e in check["errors"]))

    def test_missing_database_raises(self):
        with self.assertRaises(FileNotFoundError):
            backup.create_backup(os.path.join(self.tmp, "nope.db"), os.path.join(self.tmp, "backups"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
