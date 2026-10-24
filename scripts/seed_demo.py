"""Seed the local demo database. Usage: python scripts/seed_demo.py"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db
from app.demo import DEMO_ADMIN_EMAIL, DEMO_EMAIL, DEMO_PASSWORD, seed_demo, summary

DB_PATH = os.environ.get("ARTHIVIO_DB", os.path.join("data", "arthivio.db"))


def main() -> int:
    conn = db.connect(DB_PATH)
    try:
        db.init_db(conn)
        result = seed_demo(conn)
        if result is None:
            print(f"Demo data already present in {DB_PATH}")
            row = conn.execute("SELECT id FROM tenant WHERE slug='arthivio-demo'").fetchone()
            s = summary(conn, row["id"])
            print(f"  journal entries: {s['entries']}  accounts: {s['accounts']}  balanced: {s['balanced']}")
            return 0
        s = summary(conn, result["tenant_id"])
        print(f"Seeded {DB_PATH}")
        print(f"  invoices: {result['invoices']}   journal entries: {s['entries']}   trial balance balanced: {s['balanced']}")
        print(f"  owner login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"  admin login: {DEMO_ADMIN_EMAIL} / {DEMO_PASSWORD}")
        print("  Change these credentials before any real use.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
