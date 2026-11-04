"""Runtime diagnostics: error IDs, file logging and a health snapshot.

The app deliberately keeps this small and dependency-free. It is used by the
HTTP error handler and by the owner-facing System Check page.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import sqlite3
import sys
import traceback
import uuid
from collections import deque
from datetime import datetime, timezone

LOG_DIR = os.environ.get("ARTHIVIO_LOG_DIR", "logs")
_STARTED_AT = datetime.now(timezone.utc)


def log_path() -> str:
    return os.path.abspath(os.path.join(LOG_DIR, "arthivio.log"))


def setup_logging() -> None:
    """Create a file + stderr logger once. Safe to call repeatedly."""
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("arthivio")
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    logger.propagate = False
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    try:
        fh = logging.FileHandler(log_path(), encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        # A read-only filesystem should not stop the accounting app.
        pass
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)


def new_error_id() -> str:
    return "ERR-" + uuid.uuid4().hex[:10].upper()


def log_info(message: str, **fields) -> None:
    setup_logging()
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    logging.getLogger("arthivio").info("%s %s", message, extra)


def log_exception(error_id: str, method: str, path: str, exc: BaseException) -> None:
    setup_logging()
    logging.getLogger("arthivio").error(
        "error_id=%s method=%s path=%s exception=%r\n%s",
        error_id, method, path, exc, traceback.format_exc(),
    )


def _tail(path: str, lines: int = 20) -> list[str]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return [line.rstrip("\n") for line in deque(fh, maxlen=lines)]
    except OSError:
        return []


def health_snapshot(db_path: str, backup_dir: str, version: str = "unknown") -> dict:
    """Read-only health data for the System Check page.

    This function never writes to the database. It reports the checks that
    matter for a small accounting deployment: SQLite integrity, foreign keys,
    balanced journals, disk space, the latest backup and recent log lines.
    """
    now = datetime.now(timezone.utc)
    db_abs = os.path.abspath(db_path)
    backup_abs = os.path.abspath(backup_dir)
    snap: dict = {
        "ok": True,
        "checked_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "uptime_seconds": max(0, int((now - _STARTED_AT).total_seconds())),
        "version": version,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "db_path": db_abs,
        "db_exists": os.path.exists(db_abs),
        "db_size_bytes": os.path.getsize(db_abs) if os.path.exists(db_abs) else 0,
        "backup_dir": backup_abs,
        "backup_count": 0,
        "last_backup": None,
        "integrity": "not checked",
        "foreign_keys": "not checked",
        "journals": "not checked",
        "disk_free_bytes": 0,
        "log_path": log_path(),
        "log_tail": _tail(log_path(), 20),
        "errors": [],
    }

    try:
        usage = shutil.disk_usage(os.path.dirname(db_abs) if os.path.exists(db_abs) else ".")
        snap["disk_free_bytes"] = usage.free
    except OSError as exc:
        snap["errors"].append(f"disk check failed: {exc}")

    if not snap["db_exists"]:
        snap["ok"] = False
        snap["errors"].append("database file does not exist")
        return snap

    try:
        conn = sqlite3.connect(f"file:{db_abs}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        snap["ok"] = False
        snap["errors"].append(f"cannot open database: {exc}")
        return snap

    try:
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        snap["integrity"] = integrity
        if integrity != "ok":
            snap["ok"] = False
            snap["errors"].append(f"integrity check: {integrity}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            snap["foreign_keys"] = f"{len(fk)} violation(s)"
            snap["ok"] = False
            snap["errors"].append(f"{len(fk)} foreign key violation(s)")
        else:
            snap["foreign_keys"] = "ok"

        rows = conn.execute(
            "SELECT tenant_id, COALESCE(SUM(debit_paise),0) d,"
            " COALESCE(SUM(credit_paise),0) c"
            " FROM journal_line GROUP BY tenant_id"
        ).fetchall()
        unbalanced = [r["tenant_id"] for r in rows if r["d"] != r["c"]]
        if unbalanced:
            snap["journals"] = f"{len(unbalanced)} unbalanced tenant(s)"
            snap["ok"] = False
            snap["errors"].append(
                "unbalanced journal(s): " + ", ".join(str(x) for x in unbalanced)
            )
        else:
            snap["journals"] = f"balanced ({len(rows)} tenant(s))"

        try:
            count = conn.execute("SELECT COUNT(*) FROM backup_run").fetchone()[0]
            snap["backup_count"] = int(count)
            latest = conn.execute(
                "SELECT created_at, status, size_bytes, path FROM backup_run"
                " ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if latest:
                snap["last_backup"] = dict(latest)
        except sqlite3.Error:
            snap["backup_count"] = 0
    except sqlite3.Error as exc:
        snap["ok"] = False
        snap["errors"].append(f"database check failed: {exc}")
    finally:
        conn.close()

    return snap
