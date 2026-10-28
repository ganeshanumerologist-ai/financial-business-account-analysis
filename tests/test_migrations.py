"""Regression tests for additive schema migrations on an existing database."""
from __future__ import annotations

import unittest

from app import db


OLD_SCHEMA = """
CREATE TABLE user (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);
CREATE TABLE account (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    is_postable INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE customer (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    gstin TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE vendor (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    gstin TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE item (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'NOS',
    tax_bp INTEGER NOT NULL DEFAULT 0,
    sale_price_paise INTEGER NOT NULL DEFAULT 0,
    cost_paise INTEGER NOT NULL DEFAULT 0,
    revenue_code TEXT NOT NULL DEFAULT '4000',
    track_stock INTEGER NOT NULL DEFAULT 1,
    stock_qty_milli INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


class TestAdditiveMigration(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.conn.executescript(OLD_SCHEMA)

    def tearDown(self):
        self.conn.close()

    def test_old_tables_gain_columns_and_indexes(self):
        # Build 0.10 used to create ix_customer_account inside SCHEMA, before the
        # additive migration added customer.account_id, so an existing database
        # failed with "no such column: account_id". This is the regression guard.
        db.init_db(self.conn)

        def columns(table: str) -> set[str]:
            return {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}

        self.assertIn("group_code", columns("account"))
        self.assertIn("status", columns("account"))
        self.assertIn("archived_at", columns("account"))
        self.assertIn("archived_by", columns("account"))
        self.assertIn("merged_into_id", columns("account"))
        self.assertIn("account_id", columns("customer"))
        self.assertIn("credit_days", columns("customer"))
        self.assertIn("account_id", columns("vendor"))
        self.assertIn("credit_limit_paise", columns("vendor"))
        self.assertIn("hsn", columns("item"))
        self.assertIn("category", columns("item"))
        self.assertIn("brand", columns("item"))
        self.assertIn("barcode", columns("item"))
        self.assertIn("mrp_paise", columns("item"))
        self.assertIn("margin_bp", columns("item"))
        self.assertIn("theme", columns("user"))
        self.conn.execute(
            "INSERT INTO user (id,email,password_hash,full_name,created_at)"
            " VALUES ('u1','old@example.test','x','Old User','2026-01-01')")
        self.assertEqual(
            self.conn.execute("SELECT theme FROM user WHERE id='u1'").fetchone()["theme"],
            "ocean")
        self.conn.execute(
            "INSERT INTO account (id,tenant_id,code,name,type)"
            " VALUES ('a1','t1','1000','Cash','asset')")
        self.assertEqual(
            self.conn.execute("SELECT status FROM account WHERE id='a1'").fetchone()["status"],
            "active")

        indexes = {row["name"] for row in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("ix_account_profile_tenant", indexes)
        self.assertIn("ix_account_status", indexes)
        self.assertIn("ix_customer_account", indexes)
        self.assertIn("ix_vendor_account", indexes)

    def test_init_is_idempotent_on_existing_database(self):
        db.init_db(self.conn)
        db.init_db(self.conn)
        tables = {row["name"] for row in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("account_profile", tables)
        self.assertIn("bank_account", tables)


if __name__ == "__main__":
    unittest.main()
