"""Authentication, sessions, RBAC and tenant context (stdlib only)."""
from __future__ import annotations

import hashlib
import hmac
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
    "report.view", "report.export", "backup.run",
    "payment.record", "bill.create", "credit_note.create", "debit_note.create",
    "vendor.manage", "journal.post", "bank.reconcile",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": set(PERMISSIONS),
    "admin": PERMISSIONS - {"tenant.manage"},
    "manager": {"ledger.post", "invoice.create", "customer.manage", "item.manage",
                "report.view", "report.export", "payment.record", "bill.create",
                "credit_note.create", "debit_note.create", "vendor.manage", "bank.reconcile"},
    "accountant": {"ledger.post", "ledger.reverse", "invoice.create", "customer.manage",
                   "report.view", "report.export", "payment.record", "bill.create",
                   "credit_note.create", "debit_note.create", "vendor.manage",
                   "journal.post", "bank.reconcile"},
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
