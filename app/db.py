"""SQLite persistence: schema, connection, seeds, sequences.

Zero external dependencies. Schema is written to stay PostgreSQL-compatible
(no SQLite-only types beyond INTEGER/TEXT, no autoincrement business keys).
"""
from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenant (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    state_code TEXT NOT NULL DEFAULT '27',
    currency TEXT NOT NULL DEFAULT 'INR',
    fiscal_year_start_month INTEGER NOT NULL DEFAULT 4,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','closed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','locked','disabled')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS membership (
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    user_id TEXT NOT NULL REFERENCES user(id),
    role TEXT NOT NULL CHECK (role IN ('owner','admin','manager','accountant','cashier','sales','inventory','readonly')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('invited','active','suspended','removed')),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS session (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES user(id),
    tenant_id TEXT REFERENCES tenant(id),
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    tenant_id TEXT,
    actor_user_id TEXT,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    result TEXT NOT NULL CHECK (result IN ('success','denied','error')),
    meta TEXT,
    ip TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('asset','liability','equity','income','expense')),
    is_postable INTEGER NOT NULL DEFAULT 1,
    UNIQUE (tenant_id, code)
);

CREATE TABLE IF NOT EXISTS journal_entry (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    entry_no TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    narration TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    idempotency_key TEXT,
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted','reversed')),
    reversal_of TEXT REFERENCES journal_entry(id),
    posted_at TEXT NOT NULL,
    created_by TEXT,
    UNIQUE (tenant_id, entry_no),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS journal_line (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    entry_id TEXT NOT NULL REFERENCES journal_entry(id),
    line_no INTEGER NOT NULL,
    account_id TEXT NOT NULL REFERENCES account(id),
    party_id TEXT,
    debit_paise INTEGER NOT NULL DEFAULT 0 CHECK (debit_paise >= 0),
    credit_paise INTEGER NOT NULL DEFAULT 0 CHECK (credit_paise >= 0),
    memo TEXT,
    CHECK ((debit_paise = 0) <> (credit_paise = 0))
);

CREATE TABLE IF NOT EXISTS customer (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    name TEXT NOT NULL,
    phone TEXT,
    gstin TEXT,
    state_code TEXT NOT NULL DEFAULT '27',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'pcs',
    sale_price_paise INTEGER NOT NULL DEFAULT 0,
    cost_paise INTEGER NOT NULL DEFAULT 0,
    tax_rate_bp INTEGER NOT NULL DEFAULT 1800,
    hsn TEXT,
    stock_milli INTEGER NOT NULL DEFAULT 0,
    track_stock INTEGER NOT NULL DEFAULT 1,
    revenue_code TEXT NOT NULL DEFAULT '4000',
    UNIQUE (tenant_id, sku)
);

CREATE TABLE IF NOT EXISTS invoice (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    invoice_no TEXT NOT NULL,
    invoice_date TEXT NOT NULL,
    customer_id TEXT NOT NULL REFERENCES customer(id),
    place_of_supply_state TEXT NOT NULL,
    sub_total_paise INTEGER NOT NULL,
    tax_paise INTEGER NOT NULL,
    round_off_paise INTEGER NOT NULL DEFAULT 0,
    total_paise INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('draft','posted','void')),
    idempotency_key TEXT,
    journal_entry_id TEXT REFERENCES journal_entry(id),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, invoice_no),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS invoice_line (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    invoice_id TEXT NOT NULL REFERENCES invoice(id),
    item_id TEXT REFERENCES item(id),
    description TEXT NOT NULL,
    qty_milli INTEGER NOT NULL,
    unit_price_paise INTEGER NOT NULL,
    gross_paise INTEGER NOT NULL,
    discount_paise INTEGER NOT NULL DEFAULT 0,
    taxable_paise INTEGER NOT NULL,
    tax_rate_bp INTEGER NOT NULL,
    tax_paise INTEGER NOT NULL,
    line_total_paise INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sequence (
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    doc_type TEXT NOT NULL,
    next_no INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, doc_type)
);

CREATE TABLE IF NOT EXISTS period_lock (
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    locked_by TEXT,
    PRIMARY KEY (tenant_id, period_start, period_end)
);

CREATE INDEX IF NOT EXISTS ix_jl_tenant_account ON journal_line (tenant_id, account_id);
CREATE INDEX IF NOT EXISTS ix_jl_party ON journal_line (tenant_id, party_id);
CREATE INDEX IF NOT EXISTS ix_je_tenant_date ON journal_entry (tenant_id, entry_date);
CREATE INDEX IF NOT EXISTS ix_inv_tenant_date ON invoice (tenant_id, invoice_date);
CREATE INDEX IF NOT EXISTS ix_audit_tenant_time ON audit_log (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS ix_session_token ON session (token_hash);
"""

CHART = [
    ("1000", "Cash", "asset"),
    ("1010", "Bank", "asset"),
    ("1100", "Accounts Receivable", "asset"),
    ("1200", "Inventory", "asset"),
    ("1500", "Fixed Assets", "asset"),
    ("2000", "Accounts Payable", "liability"),
    ("2100", "GST Output - CGST", "liability"),
    ("2101", "GST Output - SGST", "liability"),
    ("2102", "GST Output - IGST", "liability"),
    ("2200", "GST Input - CGST", "asset"),
    ("2201", "GST Input - SGST", "asset"),
    ("2202", "GST Input - IGST", "asset"),
    ("3000", "Owner's Equity", "equity"),
    ("3100", "Retained Earnings", "equity"),
    ("4000", "Sales Revenue", "income"),
    ("4100", "Service Revenue", "income"),
    ("5000", "Cost of Goods Sold", "expense"),
    ("5100", "Purchases", "expense"),
    ("5900", "Rounding Off", "expense"),
    ("6000", "Rent", "expense"),
    ("6010", "Salaries", "expense"),
    ("6020", "Utilities", "expense"),
    ("6030", "Professional Fees", "expense"),
]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def next_number(conn: sqlite3.Connection, tenant_id: str, doc_type: str, prefix: str) -> str:
    """Transactional per-tenant sequence. Caller must hold a transaction."""
    row = conn.execute(
        "SELECT next_no FROM sequence WHERE tenant_id=? AND doc_type=?", (tenant_id, doc_type)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO sequence (tenant_id, doc_type, next_no) VALUES (?,?,?)",
            (tenant_id, doc_type, 2),
        )
        n = 1
    else:
        n = row["next_no"]
        conn.execute(
            "UPDATE sequence SET next_no=? WHERE tenant_id=? AND doc_type=?",
            (n + 1, tenant_id, doc_type),
        )
    return f"{prefix}-{n:05d}"


def seed_chart(conn: sqlite3.Connection, tenant_id: str) -> dict[str, str]:
    """Insert the default chart; return {code: account_id}."""
    out: dict[str, str] = {}
    for code, name, typ in CHART:
        existing = conn.execute(
            "SELECT id FROM account WHERE tenant_id=? AND code=?", (tenant_id, code)
        ).fetchone()
        if existing:
            out[code] = existing["id"]
            continue
        aid = new_id()
        conn.execute(
            "INSERT INTO account (id, tenant_id, code, name, type) VALUES (?,?,?,?,?)",
            (aid, tenant_id, code, name, typ),
        )
        out[code] = aid
    return out


def create_tenant(conn: sqlite3.Connection, name: str, slug: str, state_code: str = "27") -> str:
    tid = new_id()
    conn.execute(
        "INSERT INTO tenant (id, name, slug, state_code, created_at) VALUES (?,?,?,?,?)",
        (tid, name, slug, state_code, now()),
    )
    seed_chart(conn, tid)
    return tid


def account_id(conn: sqlite3.Connection, tenant_id: str, code: str) -> str:
    row = conn.execute(
        "SELECT id FROM account WHERE tenant_id=? AND code=?", (tenant_id, code)
    ).fetchone()
    if not row:
        raise KeyError(f"account {code} not found for tenant")
    return row["id"]
