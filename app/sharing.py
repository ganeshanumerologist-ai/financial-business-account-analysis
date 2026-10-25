"""Shareable customer/vendor statement links (stdlib only).

A share link is a bearer secret. Only its SHA-256 hash is stored, it has an
expiry, can be revoked, and is scoped to one party and one date range.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone

from . import accounting as acct
from . import db


class ShareError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _check_dates(date_from: str, date_to: str) -> tuple[str, str]:
    try:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    except (TypeError, ValueError) as exc:
        raise ShareError("BAD_DATES", "Use valid ISO dates (YYYY-MM-DD)") from exc
    if start > end:
        raise ShareError("BAD_DATES", "The start date must be on or before the end date")
    return start.isoformat(), end.isoformat()


def create_statement_share(conn: sqlite3.Connection, tenant_id: str, party_type: str,
                           party_id: str, date_from: str, date_to: str,
                           created_by: str | None = None, days: int = 30) -> dict:
    if party_type not in {"customer", "vendor"}:
        raise ShareError("BAD_PARTY_TYPE", "Share only supports customer or vendor statements")
    party = conn.execute(
        f"SELECT * FROM {party_type} WHERE id=? AND tenant_id=?", (party_id, tenant_id)
    ).fetchone()
    if not party:
        raise ShareError("PARTY_NOT_FOUND", "Customer or vendor not found")
    date_from, date_to = _check_dates(date_from, date_to)
    days = max(1, min(int(days), 90))
    token = secrets.token_urlsafe(32)
    share_id = db.new_id()
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=days)).replace(microsecond=0)
    conn.execute(
        "INSERT INTO statement_share (id, tenant_id, party_type, party_id, token_hash,"
        " date_from, date_to, created_by, created_at, expires_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (share_id, tenant_id, party_type, party_id, _token_hash(token), date_from, date_to,
         created_by, now.replace(microsecond=0).isoformat(), expires.isoformat()),
    )
    acct.audit(conn, tenant_id, created_by, "statement.share_created", "statement_share",
               share_id, meta={"party_type": party_type, "party_id": party_id,
                               "date_from": date_from, "date_to": date_to,
                               "expires_at": expires.isoformat()})
    return {"id": share_id, "token": token, "date_from": date_from, "date_to": date_to,
            "expires_at": expires.isoformat(), "party_name": party["name"]}


def resolve_statement_share(conn: sqlite3.Connection, token: str) -> dict:
    token = (token or "").strip()
    if not token:
        raise ShareError("SHARE_NOT_FOUND", "This statement link is not valid")
    share = conn.execute(
        "SELECT * FROM statement_share WHERE token_hash=?", (_token_hash(token),)
    ).fetchone()
    if not share:
        raise ShareError("SHARE_NOT_FOUND", "This statement link is not valid")
    if share["revoked_at"]:
        raise ShareError("SHARE_REVOKED", "This statement link has been revoked")
    if share["expires_at"] < _now():
        raise ShareError("SHARE_EXPIRED", "This statement link has expired")
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (share["tenant_id"],)).fetchone()
    if not tenant:
        raise ShareError("SHARE_NOT_FOUND", "Business not found")
    if tenant["status"] != "active":
        raise ShareError("TENANT_INACTIVE", "This business is not active")
    if share["party_type"] == "customer":
        statement = acct.customer_statement(conn, share["tenant_id"], share["party_id"],
                                            share["date_from"], share["date_to"])
    else:
        statement = acct.vendor_statement(conn, share["tenant_id"], share["party_id"],
                                          share["date_from"], share["date_to"])
    conn.execute(
        "UPDATE statement_share SET last_viewed_at=?, view_count=view_count+1 WHERE id=?",
        (_now(), share["id"]),
    )
    return {"share": dict(share), "tenant": dict(tenant), "statement": statement}


def list_statement_shares(conn: sqlite3.Connection, tenant_id: str,
                          party_type: str | None = None,
                          party_id: str | None = None) -> list[dict]:
    sql = "SELECT * FROM statement_share WHERE tenant_id=?"
    params: list = [tenant_id]
    if party_type:
        sql += " AND party_type=?"
        params.append(party_type)
    if party_id:
        sql += " AND party_id=?"
        params.append(party_id)
    sql += " ORDER BY created_at DESC LIMIT 25"
    now = _now()
    out = []
    for row in conn.execute(sql, params).fetchall():
        item = dict(row)
        if item["revoked_at"]:
            item["link_status"] = "revoked"
        elif item["expires_at"] < now:
            item["link_status"] = "expired"
        else:
            item["link_status"] = "active"
        out.append(item)
    return out


def revoke_statement_share(conn: sqlite3.Connection, tenant_id: str, share_id: str,
                           actor_user_id: str | None) -> None:
    row = conn.execute(
        "SELECT * FROM statement_share WHERE id=? AND tenant_id=?", (share_id, tenant_id)
    ).fetchone()
    if not row:
        raise ShareError("SHARE_NOT_FOUND", "Share link not found")
    if row["revoked_at"]:
        return
    conn.execute("UPDATE statement_share SET revoked_at=? WHERE id=?", (_now(), share_id))
    acct.audit(conn, tenant_id, actor_user_id, "statement.share_revoked", "statement_share",
               share_id, meta={"party_type": row["party_type"], "party_id": row["party_id"]})
