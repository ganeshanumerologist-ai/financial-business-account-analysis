"""Create a verified ARTHIVIO backup and copy it to an external drive.

Usage:
    python scripts/backup_to_drive.py --dest "E:\\ARTHIVIO-Backups"
    python scripts/backup_to_drive.py --dest E:\\ARTHIVIO-Backups --keep 30

The local backup is created with SQLite's online backup API and verified before
the copy is made. The copy is hashed and opened read-only for a second check.
Nothing is deleted from the local backups folder.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import backup  # noqa: E402


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _prune(folder: str, keep: int) -> list[str]:
    if keep <= 0:
        return []
    files = sorted(
        (os.path.join(folder, name) for name in os.listdir(folder)
         if name.startswith("arthivio-") and name.endswith(".db")),
        key=lambda p: os.path.getmtime(p), reverse=True)
    removed = []
    for path in files[keep:]:
        try:
            os.remove(path)
            removed.append(path)
        except OSError:
            pass
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a verified ARTHIVIO backup and copy it to a drive")
    parser.add_argument(
        "--db", default=os.environ.get(
            "ARTHIVIO_DB", os.path.join(ROOT, "data", "arthivio.db")))
    parser.add_argument(
        "--out", default=os.environ.get(
            "ARTHIVIO_BACKUP_DIR", os.path.join(ROOT, "backups")))
    parser.add_argument("--dest", required=True,
                        help="External-drive folder, e.g. E:\\ARTHIVIO-Backups")
    parser.add_argument("--keep", type=int, default=30,
                        help="Keep the newest N copies on the destination (0 = keep all)")
    args = parser.parse_args()

    dest = os.path.abspath(os.path.expanduser(args.dest))
    if not os.path.isdir(dest):
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError as exc:
            print(f"FAIL: cannot create destination folder: {exc}")
            return 1
    if not os.access(dest, os.W_OK):
        print(f"FAIL: destination is not writable: {dest}")
        return 1

    try:
        result = backup.create_backup(args.db, args.out)
    except FileNotFoundError as exc:
        print(f"FAIL: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - show a useful message on a failed backup
        print(f"FAIL: backup could not be created: {exc}")
        return 1

    if result["status"] != "verified":
        print(f"FAIL: local backup was not verified: {result['path']}")
        for error in result["verification"]["errors"]:
            print(f"  {error}")
        return 1

    target = os.path.join(dest, os.path.basename(result["path"]))
    try:
        shutil.copy2(result["path"], target)
    except OSError as exc:
        print(f"FAIL: could not copy to {dest}: {exc}")
        return 1

    source_hash = _sha256(result["path"])
    target_hash = _sha256(target)
    if source_hash != target_hash:
        print("FAIL: the copied file hash does not match the local backup.")
        print(f"  local: {source_hash}")
        print(f"  copy:  {target_hash}")
        return 1

    check = backup.verify_backup(target, result["path"])
    if not check["ok"]:
        print("FAIL: the copied backup did not pass verification.")
        for error in check["errors"]:
            print(f"  {error}")
        return 1

    removed = _prune(dest, args.keep)
    print("Backup verified and copied.")
    print(f"Local:  {result['path']}")
    print(f"Drive:  {target}")
    print(f"SHA-256: {source_hash}")
    print(f"Size:   {result['size_bytes']:,} bytes")
    for item in check["checks"]:
        print(f"  ok   {item}")
    if removed:
        print(f"Pruned {len(removed)} older drive copy/copies (kept {args.keep}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
