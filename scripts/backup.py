"""Create a verified backup. Usage: python scripts/backup.py [--db PATH] [--out DIR]"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and verify an ARTHIVIO backup")
    parser.add_argument("--db", default=os.environ.get("ARTHIVIO_DB", os.path.join("data", "arthivio.db")))
    parser.add_argument("--out", default="backups")
    args = parser.parse_args()

    try:
        result = backup.create_backup(args.db, args.out)
    except FileNotFoundError as exc:
        print(f"FAIL: {exc}")
        return 1

    print(f"Backup:   {result['path']}")
    print(f"SHA-256:  {result['sha256']}")
    print(f"Size:     {result['size_bytes']} bytes")
    print(f"Status:   {result['status'].upper()}")
    for check in result["verification"]["checks"]:
        print(f"  ok   {check}")
    for error in result["verification"]["errors"]:
        print(f"  FAIL {error}")
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
