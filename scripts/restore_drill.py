"""Measured backup -> restore -> smoke-test drill.

This is deliberately a copy-based drill. It never restores over the live
database. It takes an online backup, verifies it, copies it to a scratch
database, starts a second ARTHIVIO process against that copy, logs in and reads
a report page, then stops the process. The elapsed time is the measured RTO for
this machine.

Usage:
    python scripts/restore_drill.py
    python scripts/restore_drill.py --db data/arthivio-trial.db --email owner@arthivio.test
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import backup  # noqa: E402


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(base: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/health", timeout=2) as response:
                if response.status == 200 and response.read().decode("utf-8").strip() == "ok":
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.5)
    return False


def login_and_read(base: str, email: str, password: str) -> tuple[bool, bool, str]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = urllib.parse.urlencode({"email": email, "password": password}).encode()
    try:
        with opener.open(urllib.request.Request(
                base + "/login", data=body, method="POST"), timeout=20) as response:
            page = response.read().decode("utf-8", "replace")
            login_ok = response.status == 200 and "Dashboard" in page
    except (urllib.error.URLError, OSError) as exc:
        return False, False, f"login failed: {exc}"

    try:
        with opener.open(base + "/reports/library", timeout=20) as response:
            report = response.read().decode("utf-8", "replace")
            report_ok = response.status == 200 and "66 of 66" in report
    except (urllib.error.URLError, OSError) as exc:
        return login_ok, False, f"report failed: {exc}"

    return login_ok, report_ok, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Measured ARTHIVIO restore drill")
    parser.add_argument("--db", default=os.environ.get("ARTHIVIO_DB", os.path.join("data", "arthivio.db")))
    parser.add_argument("--email", default="owner@arthivio.test")
    parser.add_argument("--password", default="ArthivioDemo!2026")
    parser.add_argument("--keep", action="store_true", help="keep the scratch restore folder")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return 2

    scratch = tempfile.mkdtemp(prefix="arthivio-restore-drill-")
    started = time.perf_counter()
    result = backup.create_backup(db_path, scratch)
    backup_seconds = time.perf_counter() - started

    backup_path = result["path"]
    verify = result["verification"]
    restored = os.path.join(scratch, "restored.db")
    shutil.copy2(backup_path, restored)

    conn = sqlite3.connect(restored)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        counts = {}
        for table in ("tenant", "user", "journal_entry", "journal_line", "invoice",
                      "bill", "payment", "audit_log", "saved_dashboard"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update({
        "ARTHIVIO_DB": restored,
        "ARTHIVIO_HOST": "127.0.0.1",
        "PORT": str(port),
        "ARTHIVIO_SEED_DEMO": "0",
        "ARTHIVIO_DEMO_AUTOLOGIN": "0",
        "ARTHIVIO_BACKUP_DIR": os.path.join(scratch, "backups"),
        "ARTHIVIO_LOG_DIR": os.path.join(scratch, "logs"),
    })
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.server"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    healthy = False
    login_ok = False
    report_ok = False
    error = ""
    try:
        healthy = wait_health(base)
        if healthy:
            login_ok, report_ok, error = login_and_read(base, args.email, args.password)
        else:
            error = "restored app did not become healthy"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    total_seconds = time.perf_counter() - started
    checks = {
        "backup_verified": verify["ok"],
        "restored_integrity": integrity == "ok",
        "restored_foreign_keys": not fk,
        "restored_app_health": healthy,
        "restored_login": login_ok,
        "restored_report": report_ok,
    }
    ok = all(checks.values())
    summary = {
        "ok": ok,
        "source_db": db_path,
        "backup_path": backup_path,
        "restored_db": restored,
        "backup_sha256": result["sha256"],
        "backup_size_bytes": result["size_bytes"],
        "backup_seconds": round(backup_seconds, 3),
        "total_restore_seconds": round(total_seconds, 3),
        "checks": checks,
        "row_counts": counts,
        "error": error,
    }
    print(json.dumps(summary, indent=2))
    print("RESULT:", "PASS" if ok else "FAIL")
    if not args.keep:
        shutil.rmtree(scratch, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
