"""Verify a backup against the live database. Usage:
python scripts/restore_verify.py --backup backups/arthivio-YYYYmmdd-HHMMSS.db
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an ARTHIVIO backup (restore drill)")
    parser.add_argument("--backup", required=True)
    parser.add_argument("--db", default=os.environ.get("ARTHIVIO_DB", os.path.join("data", "arthivio.db")))
    args = parser.parse_args()

    result = backup.verify_backup(args.backup, args.db)
    print(f"Backup: {args.backup}")
    print(f"SHA-256: {result.get('sha256', 'n/a')}")
    for check in result["checks"]:
        print(f"  ok   {check}")
    for error in result["errors"]:
        print(f"  FAIL {error}")
    print("RESULT:", "PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
