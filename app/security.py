"""Authentication, sessions, RBAC and tenant context (stdlib only)."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from . import db

IDLE_MINUTES = 30
ABSOLUTE_HOURS = 12
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

PERMISSIONS = {
    "tenant.manage", "user.invite", "role.assign", "ledger.post", "ledger.reverse",
    "invoice.create", "invoice.void", "customer.manage", "item.manage",
    "report.view", "report.export", "backup.run", "statement.share", "gst.reconcile",
    "payment.record", "bill.create", "credit_note.create", "debit_note.create",
    "vendor.manage", "journal.post", "bank.reconcile",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": set(PERMISSIONS),
    "admin": PERMISSIONS - {"tenant.manage"},
    "manager": {"ledger.post", "invoice.create", "customer.manage", "item.manage",
                "report.view", "report.export", "payment.record", "bill.create",
                "credit_note.create", "debit_note.create", "vendor.manage", "bank.reconcile",
                "statement.share", "gst.reconcile"},
    "accountant": {"ledger.post", "ledger.reverse", "invoice.create", "customer.manage",
                   "report.view", "report.export", "payment.record", "bill.create",
                   "credit_note.create", "debit_note.create", "vendor.manage",
                   "journal.post", "bank.reconcile", "statement.share", "gst.reconcile"},
    "cashier": {"invoice.create", "customer.manage", "report.view", "payment.record"},
    "sales": {"invoice.create", "customer.manage", "report.view"},
    "inventory": {"item.manage", "report.view"},
    "readonly": {"report.view"},
}


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------
# passwords
# --------------------------------------------------------------------------

def hash_password(password: str) -> str:
    if len(password) < 12:
        raise AuthError("WEAK_PASSWORD", "Password must be at least 12 characters")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1,
                        dklen=32, maxmem=64 * 1024 * 1024)
    return f"scrypt$16384$8$1${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2,
                            maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------
# users and memberships
# --------------------------------------------------------------------------

def create_user(conn: sqlite3.Connection, email: str, password: str, full_name: str) -> str:
    email = email.strip().lower()
    if "@" not in email or len(email) < 5:
        raise AuthError("BAD_EMAIL", "Invalid email address")
    if conn.execute("SELECT 1 FROM user WHERE email=?", (email,)).fetchone():
        raise AuthError("EMAIL_TAKEN", "An account with this email already exists")
    uid = db.new_id()
    conn.execute(
        "INSERT INTO user (id, email, password_hash, full_name, created_at) VALUES (?,?,?,?,?)",
        (uid, email, hash_password(password), full_name.strip() or email, db.now()),
    )
    return uid


def add_membership(conn: sqlite3.Connection, tenant_id: str, user_id: str, role: str) -> None:
    if role not in ROLE_PERMISSIONS:
        raise AuthError("BAD_ROLE", f"Unknown role: {role}")
    conn.execute(
        "INSERT INTO membership (tenant_id, user_id, role) VALUES (?,?,?)",
        (tenant_id, user_id, role),
    )


def _failed_recently(conn: sqlite3.Connection, email: str) -> int:
    since = (datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) c FROM audit_log WHERE action='auth.login_failed' AND meta LIKE ?"
        " AND created_at >= ?",
        (f'%"{email.lower()}"%', since),
    ).fetchone()
    return row["c"] if row else 0


def authenticate(conn: sqlite3.Connection, email: str, password: str, ip: str | None = None):
    email = email.strip().lower()
    if _failed_recently(conn, email) >= MAX_FAILED_ATTEMPTS:
        raise AuthError("LOCKED", "Too many failed attempts. Try again in a few minutes.")

    row = conn.execute("SELECT * FROM user WHERE email=?", (email,)).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        conn.execute(
            "INSERT INTO audit_log (id, tenant_id, actor_user_id, action, result, meta, ip, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (db.new_id(), None, None, "auth.login_failed", "denied",
             f'{{"email":"{email}"}}', ip, db.now()),
        )
        raise AuthError("BAD_CREDENTIALS", "Invalid email or password")
    if row["status"] != "active":
        raise AuthError("DISABLED", "This account is not active")

    conn.execute(
        "INSERT INTO audit_log (id, tenant_id, actor_user_id, action, result, ip, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (db.new_id(), None, row["id"], "auth.login", "success", ip, db.now()),
    )
    return row


# --------------------------------------------------------------------------
# sessions
# --------------------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(conn: sqlite3.Connection, user_id: str, tenant_id: str | None,
                   ip: str | None = None) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO session (id, user_id, tenant_id, token_hash, csrf_token, created_at,"
        " last_seen_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
        (db.new_id(), user_id, tenant_id, _token_hash(token), csrf,
         now.isoformat(), now.isoformat(),
         (now + timedelta(minutes=IDLE_MINUTES)).isoformat()),
    )
    return token, csrf


def get_session(conn: sqlite3.Connection, token: str | None):
    if not token:
        return None
    row = conn.execute(
        "SELECT * FROM session WHERE token_hash=?", (_token_hash(token),)
    ).fetchone()
    if not row or row["revoked_at"]:
        return None
    now = datetime.now(timezone.utc)
    expires = datetime.fromisoformat(row["expires_at"])
    created = datetime.fromisoformat(row["created_at"])
    if now > expires or now > created + timedelta(hours=ABSOLUTE_HOURS):
        conn.execute("UPDATE session SET revoked_at=? WHERE id=?", (now.isoformat(), row["id"]))
        return None
    conn.execute(
        "UPDATE session SET last_seen_at=?, expires_at=? WHERE id=?",
        (now.isoformat(), (now + timedelta(minutes=IDLE_MINUTES)).isoformat(), row["id"]),
    )
    return row


def revoke_session(conn: sqlite3.Connection, token: str | None) -> None:
    if not token:
        return
    conn.execute(
        "UPDATE session SET revoked_at=? WHERE token_hash=?",
        (db.now(), _token_hash(token)),
    )


# --------------------------------------------------------------------------
# authorisation
# --------------------------------------------------------------------------

def membership_for(conn: sqlite3.Connection, user_id: str, tenant_id: str):
    return conn.execute(
        "SELECT * FROM membership WHERE user_id=? AND tenant_id=? AND status='active'",
        (user_id, tenant_id),
    ).fetchone()


def require(conn: sqlite3.Connection, user_id: str, tenant_id: str, permission: str) -> sqlite3.Row:
    if permission not in PERMISSIONS:
        raise AuthError("UNKNOWN_PERMISSION", f"Unknown permission {permission}")
    m = membership_for(conn, user_id, tenant_id)
    if not m:
        raise AuthError("NO_MEMBERSHIP", "You do not have access to this business")
    if permission not in ROLE_PERMISSIONS[m["role"]]:
        raise AuthError("FORBIDDEN", "You do not have permission for this action")
    return m


def tenants_for(conn: sqlite3.Connection, user_id: str):
    return conn.execute(
        "SELECT t.*, m.role FROM membership m JOIN tenant t ON t.id=m.tenant_id"
        " WHERE m.user_id=? AND m.status='active' ORDER BY t.name",
        (user_id,),
    ).fetchall()


# --------------------------------------------------------------------------
# member invitations and role administration
# --------------------------------------------------------------------------

INVITE_DAYS = 7


def _audit(conn: sqlite3.Connection, tenant_id: str | None, actor: str | None, action: str,
           target_type: str | None = None, target_id: str | None = None,
           meta: dict | None = None, result: str = "success") -> None:
    conn.execute(
        "INSERT INTO audit_log (id, tenant_id, actor_user_id, action, target_type, target_id,"
        " result, meta, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (db.new_id(), tenant_id, actor, action, target_type, target_id, result,
         json.dumps(meta or {}), db.now()),
    )


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_email(email: str) -> str:
    value = (email or "").strip().lower()
    if "@" not in value or len(value) < 5:
        raise AuthError("BAD_EMAIL", "Invalid email address")
    return value


def invite_member(conn: sqlite3.Connection, tenant_id: str, email: str, full_name: str,
                  role: str, invited_by: str | None = None,
                  days: int = INVITE_DAYS) -> dict:
    """Create a one-time invite link for a new or existing ARTHIVIO login."""
    email = _clean_email(email)
    if role not in ROLE_PERMISSIONS or role == "owner":
        raise AuthError("BAD_ROLE", "Choose a valid non-owner role")
    if not conn.execute("SELECT 1 FROM tenant WHERE id=?", (tenant_id,)).fetchone():
        raise AuthError("TENANT_NOT_FOUND", "Business not found")
    existing = conn.execute(
        "SELECT m.role, m.status, u.id, u.email FROM membership m JOIN user u ON u.id=m.user_id"
        " WHERE m.tenant_id=? AND u.email=?", (tenant_id, email),
    ).fetchone()
    if existing and existing["status"] in ("active", "invited"):
        raise AuthError("ALREADY_MEMBER", "This email is already part of the business")

    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=max(1, min(int(days), 90)))).replace(microsecond=0)
    token = secrets.token_urlsafe(32)
    invite_id = db.new_id()
    conn.execute(
        "UPDATE member_invite SET status='revoked', revoked_at=?"
        " WHERE tenant_id=? AND email=? AND status='pending'",
        (now.replace(microsecond=0).isoformat(), tenant_id, email),
    )
    conn.execute(
        "INSERT INTO member_invite (id, tenant_id, email, full_name, role, token_hash,"
        " invited_by, created_at, expires_at, status) VALUES (?,?,?,?,?,?,?,?,?, 'pending')",
        (invite_id, tenant_id, email, (full_name or "").strip()[:120], role,
         _token_hash(token), invited_by, now.replace(microsecond=0).isoformat(),
         expires.isoformat()),
    )
    _audit(conn, tenant_id, invited_by, "member.invite_created", "member_invite", invite_id,
           {"email": email, "role": role, "expires_at": expires.isoformat()})
    return {"id": invite_id, "token": token, "expires_at": expires.isoformat(),
            "email": email, "role": role}


def invite_by_token(conn: sqlite3.Connection, token: str) -> dict:
    token = (token or "").strip()
    if not token:
        raise AuthError("INVITE_NOT_FOUND", "This invite link is not valid")
    row = conn.execute(
        "SELECT i.*, t.name AS tenant_name, t.slug AS tenant_slug, t.status AS tenant_status"
        " FROM member_invite i JOIN tenant t ON t.id=i.tenant_id"
        " WHERE i.token_hash=?", (_token_hash(token),),
    ).fetchone()
    if not row:
        raise AuthError("INVITE_NOT_FOUND", "This invite link is not valid")
    if row["tenant_status"] != "active":
        raise AuthError("TENANT_INACTIVE", "This business is not active")
    now = _utcnow()
    if row["status"] == "revoked" or row["revoked_at"]:
        raise AuthError("INVITE_REVOKED", "This invite link has been revoked")
    if row["status"] == "accepted" or row["accepted_at"]:
        raise AuthError("INVITE_USED", "This invite link has already been used")
    if row["status"] == "expired" or row["expires_at"] < now:
        conn.execute("UPDATE member_invite SET status='expired' WHERE id=?", (row["id"],))
        raise AuthError("INVITE_EXPIRED", "This invite link has expired")
    existing = conn.execute("SELECT id, full_name FROM user WHERE email=?",
                            (row["email"],)).fetchone()
    return {**dict(row), "existing_user": bool(existing),
            "existing_user_id": existing["id"] if existing else None}


def accept_invite(conn: sqlite3.Connection, token: str, full_name: str,
                  password: str) -> dict:
    """Accept an invite. New emails create a password; existing emails verify it."""
    invite = invite_by_token(conn, token)
    email = invite["email"]
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute("SELECT * FROM user WHERE email=?", (email,)).fetchone()
        created = False
        if existing:
            if existing["status"] != "active":
                raise AuthError("DISABLED", "This account is not active")
            if not verify_password(password, existing["password_hash"]):
                raise AuthError("BAD_CREDENTIALS", "Enter the current password for this email")
            user_id = existing["id"]
            if (full_name or "").strip() and not (existing["full_name"] or "").strip():
                conn.execute("UPDATE user SET full_name=? WHERE id=?",
                             ((full_name or "").strip()[:120], user_id))
        else:
            user_id = create_user(conn, email, password, full_name or email)
            created = True

        membership = conn.execute(
            "SELECT * FROM membership WHERE tenant_id=? AND user_id=?",
            (invite["tenant_id"], user_id),
        ).fetchone()
        if membership:
            if membership["status"] == "active":
                raise AuthError("ALREADY_MEMBER", "This email is already part of the business")
            conn.execute(
                "UPDATE membership SET role=?, status='active' WHERE tenant_id=? AND user_id=?",
                (invite["role"], invite["tenant_id"], user_id))
        else:
            add_membership(conn, invite["tenant_id"], user_id, invite["role"])
        conn.execute("UPDATE member_invite SET status='accepted', accepted_at=? WHERE id=?",
                     (_utcnow(), invite["id"]))
        _audit(conn, invite["tenant_id"], user_id, "member.invite_accepted", "member_invite",
               invite["id"], meta={"email": email, "role": invite["role"],
                                   "created_user": created})
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"user_id": user_id, "tenant_id": invite["tenant_id"], "role": invite["role"],
            "email": email, "created_user": created}


def list_members(conn: sqlite3.Connection, tenant_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT u.id AS user_id, u.email, u.full_name, u.status AS user_status,"
        " m.role, m.status AS member_status, u.created_at"
        " FROM membership m JOIN user u ON u.id=m.user_id"
        " WHERE m.tenant_id=?"
        " ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,"
        " u.full_name, u.email", (tenant_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_invites(conn: sqlite3.Connection, tenant_id: str) -> list[dict]:
    conn.execute(
        "UPDATE member_invite SET status='expired'"
        " WHERE tenant_id=? AND status='pending' AND expires_at < ?", (tenant_id, _utcnow()))
    rows = conn.execute(
        "SELECT i.*, u.full_name AS inviter FROM member_invite i"
        " LEFT JOIN user u ON u.id=i.invited_by"
        " WHERE i.tenant_id=? ORDER BY i.created_at DESC LIMIT 50", (tenant_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_invite(conn: sqlite3.Connection, tenant_id: str, invite_id: str,
                  actor_user_id: str) -> None:
    row = conn.execute(
        "SELECT * FROM member_invite WHERE id=? AND tenant_id=?", (invite_id, tenant_id)
    ).fetchone()
    if not row:
        raise AuthError("INVITE_NOT_FOUND", "Invite not found")
    if row["status"] != "pending":
        raise AuthError("INVITE_NOT_PENDING", "Only a pending invite can be revoked")
    conn.execute("UPDATE member_invite SET status='revoked', revoked_at=? WHERE id=?",
                 (_utcnow(), invite_id))
    _audit(conn, tenant_id, actor_user_id, "member.invite_revoked", "member_invite", invite_id,
           {"email": row["email"]})


def change_member_role(conn: sqlite3.Connection, tenant_id: str, actor_user_id: str,
                       target_user_id: str, new_role: str) -> None:
    actor = membership_for(conn, actor_user_id, tenant_id)
    if not actor:
        raise AuthError("NO_MEMBERSHIP", "You do not have access to this business")
    if new_role not in ROLE_PERMISSIONS or new_role == "owner":
        raise AuthError("BAD_ROLE", "Choose a valid non-owner role")
    target = membership_for(conn, target_user_id, tenant_id)
    if not target:
        raise AuthError("MEMBER_NOT_FOUND", "Member not found")
    if target_user_id == actor_user_id:
        raise AuthError("SELF_ROLE", "You cannot change your own role")
    if target["role"] == "owner":
        raise AuthError("OWNER_LOCKED", "The owner role is protected")
    conn.execute("UPDATE membership SET role=? WHERE tenant_id=? AND user_id=?",
                 (new_role, tenant_id, target_user_id))
    _audit(conn, tenant_id, actor_user_id, "member.role_changed", "member", target_user_id,
           {"old_role": target["role"], "new_role": new_role})


def set_member_status(conn: sqlite3.Connection, tenant_id: str, actor_user_id: str,
                      target_user_id: str, new_status: str) -> None:
    if new_status not in {"active", "suspended", "removed"}:
        raise AuthError("BAD_STATUS", "Invalid member status")
    actor = membership_for(conn, actor_user_id, tenant_id)
    if not actor:
        raise AuthError("NO_MEMBERSHIP", "You do not have access to this business")
    target = conn.execute("SELECT * FROM membership WHERE tenant_id=? AND user_id=?",
                          (tenant_id, target_user_id)).fetchone()
    if not target:
        raise AuthError("MEMBER_NOT_FOUND", "Member not found")
    if target_user_id == actor_user_id:
        raise AuthError("SELF_STATUS", "You cannot change your own membership status")
    if target["role"] == "owner":
        raise AuthError("OWNER_LOCKED", "The owner membership is protected")
    conn.execute("UPDATE membership SET status=? WHERE tenant_id=? AND user_id=?",
                 (new_status, tenant_id, target_user_id))
    if new_status != "active":
        conn.execute(
            "UPDATE session SET revoked_at=? WHERE user_id=? AND tenant_id=? AND revoked_at IS NULL",
            (_utcnow(), target_user_id, tenant_id))
    _audit(conn, tenant_id, actor_user_id, "member.status_changed", "member", target_user_id,
           {"old_status": target["status"], "new_status": new_status})
