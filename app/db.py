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
    gstin TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    state_name TEXT NOT NULL DEFAULT '',
    pincode TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    bank_name TEXT NOT NULL DEFAULT '',
    bank_account TEXT NOT NULL DEFAULT '',
    bank_ifsc TEXT NOT NULL DEFAULT '',
    invoice_terms TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','locked','disabled')),
    theme TEXT NOT NULL DEFAULT 'ocean',
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
    group_code TEXT NOT NULL DEFAULT '',
    is_postable INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    archived_at TEXT,
    archived_by TEXT,
    merged_into_id TEXT,
    UNIQUE (tenant_id, code)
);

CREATE TABLE IF NOT EXISTS account_profile (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    account_id TEXT NOT NULL UNIQUE REFERENCES account(id),
    legal_name TEXT NOT NULL DEFAULT '',
    contact_person TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    state_code TEXT NOT NULL DEFAULT '',
    pincode TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT 'India',
    gstin TEXT NOT NULL DEFAULT '',
    pan TEXT NOT NULL DEFAULT '',
    cin TEXT NOT NULL DEFAULT '',
    organisation_type TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    credit_days INTEGER NOT NULL DEFAULT 0,
    credit_limit_paise INTEGER NOT NULL DEFAULT 0,
    party_type TEXT NOT NULL DEFAULT '',
    party_id TEXT,
    loan_lender TEXT NOT NULL DEFAULT '',
    loan_account_no TEXT NOT NULL DEFAULT '',
    loan_sanction_date TEXT NOT NULL DEFAULT '',
    loan_maturity_date TEXT NOT NULL DEFAULT '',
    interest_rate_bp INTEGER NOT NULL DEFAULT 0,
    tenure_months INTEGER NOT NULL DEFAULT 0,
    emi_paise INTEGER NOT NULL DEFAULT 0,
    security_details TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT REFERENCES user(id),
    updated_by TEXT REFERENCES user(id)
);

CREATE TABLE IF NOT EXISTS bank_account (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    account_id TEXT NOT NULL REFERENCES account(id),
    bank_name TEXT NOT NULL,
    account_number TEXT NOT NULL,
    ifsc TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    holder_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, account_id)
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
    email TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    state_code TEXT NOT NULL DEFAULT '27',
    account_id TEXT REFERENCES account(id),
    credit_days INTEGER NOT NULL DEFAULT 0,
    credit_limit_paise INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendor (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    name TEXT NOT NULL,
    phone TEXT,
    gstin TEXT,
    email TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    state_code TEXT NOT NULL DEFAULT '27',
    account_id TEXT REFERENCES account(id),
    credit_days INTEGER NOT NULL DEFAULT 0,
    credit_limit_paise INTEGER NOT NULL DEFAULT 0,
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
    category TEXT NOT NULL DEFAULT '',
    brand TEXT NOT NULL DEFAULT '',
    barcode TEXT NOT NULL DEFAULT '',
    mrp_paise INTEGER NOT NULL DEFAULT 0,
    margin_bp INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS bill (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    bill_no TEXT NOT NULL,
    vendor_bill_no TEXT,
    bill_date TEXT NOT NULL,
    vendor_id TEXT NOT NULL REFERENCES vendor(id),
    place_of_supply_state TEXT NOT NULL,
    sub_total_paise INTEGER NOT NULL,
    tax_paise INTEGER NOT NULL,
    round_off_paise INTEGER NOT NULL DEFAULT 0,
    total_paise INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted','void')),
    idempotency_key TEXT,
    journal_entry_id TEXT REFERENCES journal_entry(id),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, bill_no),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS bill_line (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    bill_id TEXT NOT NULL REFERENCES bill(id),
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

CREATE TABLE IF NOT EXISTS payment (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    voucher_no TEXT NOT NULL,
    payment_date TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('receipt','payment')),
    party_type TEXT NOT NULL CHECK (party_type IN ('customer','vendor')),
    party_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('cash','bank','upi','cheque','card')),
    account_id TEXT NOT NULL REFERENCES account(id),
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    reference TEXT,
    notes TEXT,
    journal_entry_id TEXT REFERENCES journal_entry(id),
    idempotency_key TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, voucher_no),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS payment_allocation (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    payment_id TEXT NOT NULL REFERENCES payment(id),
    doc_type TEXT NOT NULL CHECK (doc_type IN ('invoice','bill','credit_note')),
    doc_id TEXT NOT NULL,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0)
);

CREATE TABLE IF NOT EXISTS credit_note (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    note_no TEXT NOT NULL,
    note_date TEXT NOT NULL,
    customer_id TEXT NOT NULL REFERENCES customer(id),
    invoice_id TEXT REFERENCES invoice(id),
    place_of_supply_state TEXT NOT NULL,
    sub_total_paise INTEGER NOT NULL,
    tax_paise INTEGER NOT NULL,
    round_off_paise INTEGER NOT NULL DEFAULT 0,
    total_paise INTEGER NOT NULL,
    reason TEXT NOT NULL,
    journal_entry_id TEXT REFERENCES journal_entry(id),
    idempotency_key TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, note_no),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS credit_note_line (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    credit_note_id TEXT NOT NULL REFERENCES credit_note(id),
    item_id TEXT REFERENCES item(id),
    invoice_line_id TEXT REFERENCES invoice_line(id),
    description TEXT NOT NULL,
    qty_milli INTEGER NOT NULL,
    unit_price_paise INTEGER NOT NULL,
    taxable_paise INTEGER NOT NULL,
    tax_rate_bp INTEGER NOT NULL,
    tax_paise INTEGER NOT NULL,
    cost_paise INTEGER NOT NULL DEFAULT 0,
    line_total_paise INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS debit_note (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    note_no TEXT NOT NULL,
    note_date TEXT NOT NULL,
    vendor_id TEXT NOT NULL REFERENCES vendor(id),
    bill_id TEXT REFERENCES bill(id),
    place_of_supply_state TEXT NOT NULL,
    sub_total_paise INTEGER NOT NULL,
    tax_paise INTEGER NOT NULL,
    round_off_paise INTEGER NOT NULL DEFAULT 0,
    total_paise INTEGER NOT NULL,
    reason TEXT NOT NULL,
    journal_entry_id TEXT REFERENCES journal_entry(id),
    idempotency_key TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, note_no),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS debit_note_line (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    debit_note_id TEXT NOT NULL REFERENCES debit_note(id),
    item_id TEXT REFERENCES item(id),
    bill_line_id TEXT REFERENCES bill_line(id),
    description TEXT NOT NULL,
    qty_milli INTEGER NOT NULL,
    unit_price_paise INTEGER NOT NULL,
    taxable_paise INTEGER NOT NULL,
    tax_rate_bp INTEGER NOT NULL,
    tax_paise INTEGER NOT NULL,
    cost_paise INTEGER NOT NULL DEFAULT 0,
    line_total_paise INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_import (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    account_id TEXT NOT NULL REFERENCES account(id),
    filename TEXT NOT NULL DEFAULT '',
    period_start TEXT,
    period_end TEXT,
    rows_total INTEGER NOT NULL DEFAULT 0,
    rows_imported INTEGER NOT NULL DEFAULT 0,
    rows_duplicate INTEGER NOT NULL DEFAULT 0,
    created_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_statement_line (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    account_id TEXT NOT NULL REFERENCES account(id),
    import_id TEXT REFERENCES bank_import(id),
    txn_date TEXT NOT NULL,
    description TEXT NOT NULL,
    reference TEXT NOT NULL DEFAULT '',
    debit_paise INTEGER NOT NULL DEFAULT 0 CHECK (debit_paise >= 0),
    credit_paise INTEGER NOT NULL DEFAULT 0 CHECK (credit_paise >= 0),
    balance_paise INTEGER,
    source_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unmatched' CHECK (status IN ('unmatched','matched')),
    matched_journal_line_id TEXT REFERENCES journal_line(id),
    matched_at TEXT,
    matched_by TEXT,
    imported_at TEXT NOT NULL,
    UNIQUE (tenant_id, account_id, source_hash)
);

CREATE TABLE IF NOT EXISTS backup_run (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('created','verified','failed')),
    created_at TEXT NOT NULL,
    verified_at TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS period_lock (
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    locked_by TEXT,
    PRIMARY KEY (tenant_id, period_start, period_end)
);

CREATE TABLE IF NOT EXISTS member_invite (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner','admin','manager','accountant','cashier','sales','inventory','readonly')),
    token_hash TEXT NOT NULL UNIQUE,
    invited_by TEXT REFERENCES user(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    accepted_at TEXT,
    revoked_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','revoked','expired'))
);

CREATE TABLE IF NOT EXISTS statement_share (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    party_type TEXT NOT NULL CHECK (party_type IN ('customer','vendor')),
    party_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    created_by TEXT REFERENCES user(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    last_viewed_at TEXT,
    view_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gstr2b_import (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    period TEXT NOT NULL,
    filename TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL,
    rows_total INTEGER NOT NULL DEFAULT 0,
    taxable_paise INTEGER NOT NULL DEFAULT 0,
    igst_paise INTEGER NOT NULL DEFAULT 0,
    cgst_paise INTEGER NOT NULL DEFAULT 0,
    sgst_paise INTEGER NOT NULL DEFAULT 0,
    cess_paise INTEGER NOT NULL DEFAULT 0,
    tax_paise INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded')),
    created_by TEXT REFERENCES user(id),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, sha256)
);

CREATE TABLE IF NOT EXISTS gstr2b_line (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    import_id TEXT NOT NULL REFERENCES gstr2b_import(id),
    supplier_gstin TEXT NOT NULL DEFAULT '',
    supplier_name TEXT NOT NULL DEFAULT '',
    invoice_no TEXT NOT NULL,
    invoice_date TEXT NOT NULL,
    taxable_paise INTEGER NOT NULL DEFAULT 0,
    igst_paise INTEGER NOT NULL DEFAULT 0,
    cgst_paise INTEGER NOT NULL DEFAULT 0,
    sgst_paise INTEGER NOT NULL DEFAULT 0,
    cess_paise INTEGER NOT NULL DEFAULT 0,
    tax_paise INTEGER NOT NULL DEFAULT 0,
    total_paise INTEGER NOT NULL DEFAULT 0,
    match_status TEXT NOT NULL DEFAULT 'unmatched'
        CHECK (match_status IN ('unmatched','matched','mismatch','missing_in_books','ignored')),
    matched_bill_id TEXT REFERENCES bill(id),
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gstr2b_review (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    line_id TEXT NOT NULL UNIQUE REFERENCES gstr2b_line(id),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','follow_up','itc_hold','accepted')),
    note TEXT NOT NULL DEFAULT '',
    updated_by TEXT REFERENCES user(id),
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_jl_tenant_account ON journal_line (tenant_id, account_id);
CREATE INDEX IF NOT EXISTS ix_jl_party ON journal_line (tenant_id, party_id);
CREATE INDEX IF NOT EXISTS ix_je_tenant_date ON journal_entry (tenant_id, entry_date);
CREATE INDEX IF NOT EXISTS ix_bank_account_tenant ON bank_account (tenant_id);
CREATE INDEX IF NOT EXISTS ix_inv_tenant_date ON invoice (tenant_id, invoice_date);
CREATE INDEX IF NOT EXISTS ix_bill_tenant_date ON bill (tenant_id, bill_date);
CREATE INDEX IF NOT EXISTS ix_payment_tenant_date ON payment (tenant_id, payment_date);
CREATE INDEX IF NOT EXISTS ix_alloc_doc ON payment_allocation (tenant_id, doc_type, doc_id);
CREATE INDEX IF NOT EXISTS ix_cn_tenant_date ON credit_note (tenant_id, note_date);
CREATE INDEX IF NOT EXISTS ix_dn_tenant_date ON debit_note (tenant_id, note_date);
CREATE INDEX IF NOT EXISTS ix_bank_stmt_tenant_date ON bank_statement_line (tenant_id, account_id, txn_date);
CREATE INDEX IF NOT EXISTS ix_bank_stmt_match ON bank_statement_line (tenant_id, matched_journal_line_id);
CREATE INDEX IF NOT EXISTS ix_audit_tenant_time ON audit_log (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS ix_session_token ON session (token_hash);
CREATE INDEX IF NOT EXISTS ix_member_invite_tenant ON member_invite (tenant_id, status, expires_at);
CREATE INDEX IF NOT EXISTS ix_statement_share_tenant ON statement_share (tenant_id, party_type, party_id);
CREATE INDEX IF NOT EXISTS ix_gstr2b_import_period ON gstr2b_import (tenant_id, period, status);
CREATE INDEX IF NOT EXISTS ix_gstr2b_line_import ON gstr2b_line (import_id);
CREATE INDEX IF NOT EXISTS ix_gstr2b_review_tenant ON gstr2b_review (tenant_id, status);
"""

CHART = [
    ("1000", "Cash", "asset", "cash"),
    ("1010", "Bank", "asset", "bank"),
    ("1100", "Accounts Receivable", "asset", "receivable"),
    ("1200", "Inventory", "asset", "inventory"),
    ("1500", "Fixed Assets", "asset", "fixed_asset"),
    ("2000", "Accounts Payable", "liability", "payable"),
    ("2100", "GST Output - CGST", "liability", "duties_taxes"),
    ("2101", "GST Output - SGST", "liability", "duties_taxes"),
    ("2102", "GST Output - IGST", "liability", "duties_taxes"),
    ("2200", "GST Input - CGST", "asset", "gst_input"),
    ("2201", "GST Input - SGST", "asset", "gst_input"),
    ("2202", "GST Input - IGST", "asset", "gst_input"),
    ("3000", "Owner's Equity", "equity", "capital"),
    ("3100", "Retained Earnings", "equity", "retained_earnings"),
    ("4000", "Sales Revenue", "income", "sales"),
    ("4100", "Service Revenue", "income", "service_income"),
    ("5000", "Cost of Goods Sold", "expense", "cost_of_goods_sold"),
    ("5100", "Purchases", "expense", "purchase"),
    ("5900", "Rounding Off", "expense", "other_expense"),
    ("6000", "Rent", "expense", "other_expense"),
    ("6010", "Salaries", "expense", "employee_expense"),
    ("6020", "Utilities", "expense", "other_expense"),
    ("6030", "Professional Fees", "expense", "other_expense"),
]

# Existing databases are backfilled once from this map. New accounts carry the
# group chosen at creation, so the map is never used to overwrite user choices.
CHART_GROUPS = {code: group for code, _name, _type, group in CHART}


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


POST_MIGRATION_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_account_profile_tenant ON account_profile (tenant_id);
CREATE INDEX IF NOT EXISTS ix_account_status ON account (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_customer_account ON customer (tenant_id, account_id);
CREATE INDEX IF NOT EXISTS ix_vendor_account ON vendor (tenant_id, account_id);
"""

# Read-only analytics views. They are additive and contain no authoritative
# totals of their own: every value is derived from posted journal rows.
ANALYTICS_VIEWS = """
CREATE VIEW IF NOT EXISTS v_analytics_journal AS
SELECT e.tenant_id,
       e.id AS entry_id,
       e.entry_no,
       e.entry_date,
       substr(e.entry_date, 1, 7) AS period_month,
       e.source_type,
       e.source_id,
       e.status,
       e.reversal_of,
       l.id AS line_id,
       l.line_no,
       l.account_id,
       a.code AS account_code,
       a.name AS account_name,
       a.type AS account_type,
       a.group_code,
       l.party_id,
       l.debit_paise,
       l.credit_paise,
       (l.debit_paise - l.credit_paise) AS signed_paise,
       l.memo
FROM journal_entry e
JOIN journal_line l ON l.entry_id = e.id AND l.tenant_id = e.tenant_id
JOIN account a ON a.id = l.account_id AND a.tenant_id = l.tenant_id;

CREATE VIEW IF NOT EXISTS v_analytics_monthly AS
SELECT tenant_id,
       period_month,
       account_type,
       SUM(debit_paise) AS debit_paise,
       SUM(credit_paise) AS credit_paise,
       SUM(CASE WHEN account_type = 'income'
                THEN credit_paise - debit_paise ELSE 0 END) AS income_paise,
       SUM(CASE WHEN account_type = 'expense'
                THEN debit_paise - credit_paise ELSE 0 END) AS expense_paise,
       SUM(debit_paise - credit_paise) AS signed_paise
FROM v_analytics_journal
GROUP BY tenant_id, period_month, account_type;
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    # These indexes touch columns added by _ensure_columns on an existing database,
    # so they must run after the additive migration, never inside SCHEMA.
    conn.executescript(POST_MIGRATION_INDEXES)
    conn.executescript(ANALYTICS_VIEWS)


COLUMN_MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "user": [("theme", "TEXT NOT NULL DEFAULT 'ocean'")],
    "tenant": [
        ("gstin", "TEXT NOT NULL DEFAULT ''"),
        ("address", "TEXT NOT NULL DEFAULT ''"),
        ("city", "TEXT NOT NULL DEFAULT ''"),
        ("state_name", "TEXT NOT NULL DEFAULT ''"),
        ("pincode", "TEXT NOT NULL DEFAULT ''"),
        ("phone", "TEXT NOT NULL DEFAULT ''"),
        ("email", "TEXT NOT NULL DEFAULT ''"),
        ("bank_name", "TEXT NOT NULL DEFAULT ''"),
        ("bank_account", "TEXT NOT NULL DEFAULT ''"),
        ("bank_ifsc", "TEXT NOT NULL DEFAULT ''"),
        ("invoice_terms", "TEXT NOT NULL DEFAULT ''"),
    ],
    "account": [
        ("group_code", "TEXT NOT NULL DEFAULT ''"),
        ("status", "TEXT NOT NULL DEFAULT 'active'"),
        ("archived_at", "TEXT"),
        ("archived_by", "TEXT"),
        ("merged_into_id", "TEXT"),
    ],
    "customer": [
        ("address", "TEXT NOT NULL DEFAULT ''"),
        ("email", "TEXT NOT NULL DEFAULT ''"),
        ("account_id", "TEXT"),
        ("credit_days", "INTEGER NOT NULL DEFAULT 0"),
        ("credit_limit_paise", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "vendor": [
        ("email", "TEXT NOT NULL DEFAULT ''"),
        ("address", "TEXT NOT NULL DEFAULT ''"),
        ("account_id", "TEXT"),
        ("credit_days", "INTEGER NOT NULL DEFAULT 0"),
        ("credit_limit_paise", "INTEGER NOT NULL DEFAULT 0"),
    ],
    "item": [
        ("hsn", "TEXT"),
        ("category", "TEXT NOT NULL DEFAULT ''"),
        ("brand", "TEXT NOT NULL DEFAULT ''"),
        ("barcode", "TEXT NOT NULL DEFAULT ''"),
        ("mrp_paise", "INTEGER NOT NULL DEFAULT 0"),
        ("margin_bp", "INTEGER NOT NULL DEFAULT 0"),
    ],
}


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Additive, idempotent schema migration. Never drops or rewrites data."""
    for table, columns in COLUMN_MIGRATIONS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue
        for name, ddl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    _backfill_account_groups(conn)
    conn.commit()


def _backfill_account_groups(conn: sqlite3.Connection) -> None:
    """Give known seed ledgers their group without touching custom ledgers."""
    for code, group_code in CHART_GROUPS.items():
        conn.execute(
            "UPDATE account SET group_code=? WHERE code=? AND (group_code IS NULL OR group_code='')",
            (group_code, code),
        )
    # Bank ledgers created before group codes existed are still banks.
    conn.execute(
        "UPDATE account SET group_code='bank' WHERE (group_code IS NULL OR group_code='')"
        " AND id IN (SELECT account_id FROM bank_account)"
    )


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
    for code, name, typ, group_code in CHART:
        existing = conn.execute(
            "SELECT id FROM account WHERE tenant_id=? AND code=?", (tenant_id, code)
        ).fetchone()
        if existing:
            out[code] = existing["id"]
            continue
        aid = new_id()
        conn.execute(
            "INSERT INTO account (id, tenant_id, code, name, type, group_code)"
            " VALUES (?,?,?,?,?,?)",
            (aid, tenant_id, code, name, typ, group_code),
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
