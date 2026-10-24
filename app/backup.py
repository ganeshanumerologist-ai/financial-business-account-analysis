"""Backup and restore-verification helpers.

Backups use SQLite's online backup API, so they are consistent even while the
app is running. Every backup is hashed and verified (integrity, foreign keys,
balanced journals, row counts) before it is marked verified.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

TABLES = [
    "tenant", "user", "membership", "account", "customer", "vendor", "item",
    "invoice", "invoice_line", "bill", "bill_line", "payment", "payment_allocation",
    "credit_note", "credit_note_line", "journal_entry", "journal_line",
    "audit_log", "period_lock", "sequence",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    existing = {r[0] for r in rows}
    return [t for t in TABLES if t in existing]


def _counts(conn: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_backup(backup_path: str, source_path: str | None = None) -> dict:
    """Verify a backup file. Returns {ok, errors, checks, counts, sha256}."""
    errors: list[str] = []
    checks: list[str] = []
    counts: dict[str, int] = {}
    if not os.path.exists(backup_path):
        return {"ok": False, "errors": ["backup file does not exist"], "checks": [], "counts": {}}

    try:
        conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        return {"ok": False, "errors": [f"cannot open backup: {exc}"], "checks": [], "counts": {}}

    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity == "ok":
            checks.append("integrity_check: ok")
        else:
            errors.append(f"integrity_check: {integrity}")

        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            errors.append(f"{len(fk)} foreign key violation(s)")
        else:
            checks.append("foreign_key_check: ok")

        rows = conn.execute(
            "SELECT tenant_id, COALESCE(SUM(debit_paise),0) d, COALESCE(SUM(credit_paise),0) c"
            " FROM journal_line GROUP BY tenant_id"
        ).fetchall()
        unbalanced = [r["tenant_id"] for r in rows if r["d"] != r["c"]]
        if unbalanced:
            errors.append(f"unbalanced journal(s) for tenant(s): {', '.join(unbalanced)}")
        else:
            checks.append(f"journals balanced: {len(rows)} tenant(s)")

        tables = _tables(conn)
        counts = _counts(conn, tables)
        checks.append(f"tables present: {len(tables)}")
    except sqlite3.Error as exc:
        errors.append(f"verification failed: {exc}")
        conn.close()
        return {"ok": False, "errors": errors, "checks": checks, "counts": counts}

    conn.close()

    if source_path and os.path.exists(source_path):
        try:
            src = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
            src_tables = _tables(src)
            src_counts = _counts(src, src_tables)
            src.close()
            mismatches = [t for t, c in counts.items() if src_counts.get(t) != c]
            if mismatches:
                errors.append(f"row count mismatch: {', '.join(mismatches)}")
            else:
                checks.append("row counts match source")
        except sqlite3.Error as exc:
            errors.append(f"source comparison failed: {exc}")

    return {"ok": not errors, "errors": errors, "checks": checks, "counts": counts,
            "sha256": _sha256(backup_path), "size_bytes": os.path.getsize(backup_path)}


def create_backup(db_path: str, out_dir: str = "backups") -> dict:
    """Take a consistent online backup, verify it, and record the run."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"database not found: {db_path}")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.abspath(os.path.join(out_dir, f"arthivio-{stamp}.db"))
    n = 1
    while os.path.exists(path):
        n += 1
        path = os.path.abspath(os.path.join(out_dir, f"arthivio-{stamp}-{n}.db"))
    tmp = path + ".tmp"

    src = sqlite3.connect(db_path)
    try:
        dest = sqlite3.connect(tmp)
        try:
            src.backup(dest)
        finally:
            dest.close()
        os.replace(tmp, path)
    finally:
        src.close()

    sha = _sha256(path)
    size = os.path.getsize(path)
    verification = verify_backup(path, db_path)
    status = "verified" if verification["ok"] else "failed"

    src = sqlite3.connect(db_path)
    try:
        src.execute(
            "INSERT INTO backup_run (id, path, sha256, size_bytes, status, created_at,"
            " verified_at, note) VALUES (?,?,?,?,?,?,?,?)",
            (os.urandom(16).hex(), path, sha, size, status, _now(),
             _now() if verification["ok"] else None,
             json.dumps(verification["errors"])[:500]),
        )
        src.commit()
    except sqlite3.Error:
        pass
    finally:
        src.close()

    return {"path": path, "sha256": sha, "size_bytes": size, "status": status,
            "verification": verification}


def recent_runs(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM backup_run ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
