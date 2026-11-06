# ARTHIVIO — Database Design

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-10-24 |
| Status | Draft for owner approval |
| Phase 1 engine | SQLite (WAL mode) via SQLAlchemy 2.x |
| Production target | PostgreSQL 16+ (schema must remain compatible) |

---

## 1. Conventions (apply to every table)

| Rule | Detail |
|---|---|
| Primary keys | `TEXT` ULID (26 chars, lexicographically sortable, no sequence leakage) |
| Tenant scoping | Every business table carries `tenant_id TEXT NOT NULL` + index. No exceptions. |
| Money | `BIGINT` **minor units** (paise/cents) + `CHAR(3)` currency + documented scale. **Never** float. |
| Timestamps | UTC, `TIMESTAMP` (SQLite stores ISO-8601 text; PostgreSQL uses `TIMESTAMPTZ`). Never local time. |
| Business dates | `DATE` (no time component) — e.g. invoice date, posting date. |
| Booleans | `INTEGER 0/1` in SQLite, `BOOLEAN` in PostgreSQL — mapped by SQLAlchemy |
| Soft delete | Only where legally required; otherwise explicit `status` column. Financial rows are **never** deleted. |
| Audit columns | `created_at`, `created_by`, `updated_at`, `updated_by` on mutable tables |
| Naming | `snake_case`, singular table names, `fk_`/`ix_`/`uq_`/`ck_` prefixes |
| Referential integrity | Foreign keys enforced (`PRAGMA foreign_keys=ON`) |
| Case sensitivity | Emails and codes stored lower-cased; unique indexes on the lower-cased value |

**Why integer minor units:** SQLite has no true fixed-point type; `NUMERIC` can silently become float. Integers make rounding explicit and testable, and migrate cleanly to PostgreSQL `BIGINT`.

---

## 2. Phase 1 entity-relationship outline

```
tenant ──┬── membership ── user
         │        │
         │        └── membership_scope ── (branch | warehouse)
         ├── session
         ├── audit_log
         ├── backup_run
         └── legal_entity ──┬── branch ── warehouse
                            └── department

role ── role_permission ── permission
membership.role_key ── role.key
```

---

## 3. Phase 1 tables

### 3.1 `tenant`

| Column | Type | Constraints |
|---|---|---|
| id | TEXT | PK |
| name | TEXT | NOT NULL, 1–120 chars |
| slug | TEXT | NOT NULL, UNIQUE, `^[a-z0-9-]{3,40}$` |
| status | TEXT | NOT NULL, CHECK IN (`active`,`suspended`,`closed`), default `active` |
| created_at / updated_at | TIMESTAMP | NOT NULL |

### 3.2 `user`

| Column | Type | Constraints |
|---|---|---|
| id | TEXT | PK |
| email | TEXT | NOT NULL, UNIQUE (lower-cased) |
| password_hash | TEXT | NOT NULL (Argon2id encoded string) |
| full_name | TEXT | NOT NULL |
| status | TEXT | CHECK IN (`active`,`locked`,`disabled`), default `active` |
| theme | TEXT | NOT NULL default `ocean`; one of `ocean`, `emerald`, `violet`, `sunset` |
| mfa_secret | TEXT | NULL |
| mfa_enabled | INTEGER | NOT NULL default 0 |
| failed_login_count | INTEGER | NOT NULL default 0 |
| locked_until | TIMESTAMP | NULL |
| last_login_at | TIMESTAMP | NULL |
| password_changed_at | TIMESTAMP | NOT NULL |
| created_at / updated_at | TIMESTAMP | NOT NULL |

Indexes: `uq_user_email_lower`, `ix_user_status`.

### 3.3 `role` and `permission`

| Table | Columns |
|---|---|
| `role` | `key` PK-ish UNIQUE (`owner`,`admin`,`manager`,`accountant`,`cashier`,`sales`,`inventory`,`readonly`), `name`, `description`, `is_system` |
| `permission` | `key` UNIQUE (e.g. `tenant.manage`, `user.invite`, `role.assign`, `ledger.post`, `report.export`, `backup.run`), `description` |
| `role_permission` | `role_key` FK, `permission_key` FK, PK(role_key, permission_key) |

Roles are seeded, not user-created, in Phase 1 — prevents privilege-invention.

### 3.4 `membership`

| Column | Type | Constraints |
|---|---|---|
| id | TEXT | PK |
| tenant_id | TEXT | FK tenant, NOT NULL |
| user_id | TEXT | FK user, NOT NULL |
| role_key | TEXT | FK role, NOT NULL |
| status | TEXT | CHECK IN (`invited`,`active`,`suspended`,`removed`) |
| invited_by | TEXT | FK user, NULL |
| created_at / updated_at | TIMESTAMP | NOT NULL |

Unique: `(tenant_id, user_id)` — one membership per user per tenant.
Index: `ix_membership_user` for "my businesses" lookup.

### 3.5 `membership_scope` (branch/warehouse restriction)

| Column | Type | Constraints |
|---|---|---|
| membership_id | TEXT | FK membership |
| scope_type | TEXT | CHECK IN (`branch`,`warehouse`,`department`) |
| scope_id | TEXT | NOT NULL (FK by type, enforced in service) |
| PRIMARY KEY | (membership_id, scope_type, scope_id) | |

Rule: empty scope set = tenant-wide. Non-empty = restricted to those scopes. Enforced in the authorisation layer, with tests.

### 3.6 `session`

| Column | Type | Constraints |
|---|---|---|
| id | TEXT | PK |
| user_id | TEXT | FK user, NOT NULL |
| token_hash | TEXT | NOT NULL, UNIQUE (SHA-256 of the opaque token) |
| active_tenant_id | TEXT | FK tenant, NULL |
| created_at | TIMESTAMP | NOT NULL |
| last_seen_at | TIMESTAMP | NOT NULL |
| idle_expires_at | TIMESTAMP | NOT NULL (30 min sliding) |
| absolute_expires_at | TIMESTAMP | NOT NULL (12 h) |
| revoked_at | TIMESTAMP | NULL |
| ip | TEXT | NULL |
| user_agent | TEXT | NULL |

Raw tokens are never stored. Index on `(user_id, revoked_at)`.

### 3.7 `audit_log` (append-only)

| Column | Type | Constraints |
|---|---|---|
| id | TEXT | PK |
| tenant_id | TEXT | NULL (null for pre-tenant events such as failed login) |
| actor_user_id | TEXT | NULL (null for anonymous) |
| action | TEXT | NOT NULL (e.g. `auth.login`, `auth.login_failed`, `role.assign`, `backup.restore`) |
| target_type | TEXT | NULL |
| target_id | TEXT | NULL |
| result | TEXT | CHECK IN (`success`,`denied`,`error`) |
| ip | TEXT | NULL |
| user_agent | TEXT | NULL |
| meta | TEXT | JSON, NULL — **never** contains passwords, tokens, or full financial payloads |
| created_at | TIMESTAMP | NOT NULL |

Rules: no UPDATE, no DELETE (enforced by app + DB grants later). Indexes: `(tenant_id, created_at)`, `(actor_user_id, created_at)`.

### 3.8 `login_attempt` (rate limiting / lockout evidence)

| Column | Type | Constraints |
|---|---|---|
| id | TEXT | PK |
| email_lower | TEXT | NOT NULL |
| ip | TEXT | NOT NULL |
| success | INTEGER | NOT NULL |
| created_at | TIMESTAMP | NOT NULL |

Index `(email_lower, created_at)`, `(ip, created_at)`.

### 3.9 `backup_run`

| Column | Type | Constraints |
|---|---|---|
| id | TEXT | PK |
| started_at / finished_at | TIMESTAMP | NOT NULL / NULL |
| status | TEXT | CHECK IN (`running`,`success`,`failed`,`verified`) |
| path | TEXT | NOT NULL |
| size_bytes | BIGINT | NULL |
| sha256 | TEXT | NULL |
| verified_at | TIMESTAMP | NULL |
| restore_test_result | TEXT | NULL |
| error | TEXT | NULL |

### 3.10 Organisation skeleton (needed for scoping, minimal fields)

| Table | Key columns |
|---|---|
| `legal_entity` | id, tenant_id, name, entity_type, country_code, base_currency CHAR(3), fiscal_year_start_month INT, status |
| `branch` | id, tenant_id, legal_entity_id, name, code, timezone, status |
| `warehouse` | id, tenant_id, branch_id, name, code, status |
| `department` | id, tenant_id, legal_entity_id, name, code, status |

Unique: `(tenant_id, code)` on branch/warehouse/department.

---

## 4. Phase 2 outline (accounting core — designed, not built)

| Table | Purpose | Critical columns |
|---|---|---|
| `account` | Chart of accounts | id, tenant_id, code, name, type (asset/liability/equity/income/expense), normal_balance, parent_id, is_postable, status |
| `fiscal_period` | Periods + locks | id, tenant_id, name, start_date, end_date, status (`open`,`locked`,`closed`) |
| `journal_entry` | Header | id, tenant_id, entry_no, posting_date, period_id, narration, source_type, source_id, idempotency_key UNIQUE(tenant,key), status (`draft`,`posted`,`reversed`), posted_by, posted_at, reversal_of |
| `journal_line` | Lines | id, tenant_id, entry_id, line_no, account_id, debit_minor BIGINT, credit_minor BIGINT, currency, memo |
| `document_sequence` | Numbering | tenant_id, doc_type, fiscal_year, prefix, next_value — allocated transactionally |
| `account_balance` (derived) | Snapshot/rollup | tenant_id, account_id, period_id, opening_minor, debit_minor, credit_minor, closing_minor |

Invariants enforced in the posting service **and** re-checked before commit:

```sql
-- per entry
SUM(debit_minor) = SUM(credit_minor)                 -- C-001
-- per line
(debit_minor = 0) <> (credit_minor = 0)              -- exactly one side
debit_minor >= 0 AND credit_minor >= 0
-- per entry
COUNT(lines) >= 2
```

Deferred `CHECK`/trigger equivalents on PostgreSQL will be added at migration time; SQLite relies on the service layer plus tests (documented limitation).

---

## 5. Index strategy

1. Every `tenant_id` column indexed — nearly every query filters on it first.
2. Composite indexes for the hot paths: `(tenant_id, posting_date)`, `(tenant_id, account_id, period_id)`, `(tenant_id, status)`.
3. No index on free-text `narration`/`memo` until search is designed.
4. `EXPLAIN QUERY PLAN` reviewed for reports over 10k rows before Phase 6 sign-off.

---

## 6. Row-Level Security plan (PostgreSQL, production)

```sql
ALTER TABLE journal_line ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON journal_line
  USING (tenant_id = current_setting('app.tenant_id', true));
```

The app sets `SET LOCAL app.tenant_id = :tenant` per transaction. Defence in depth only — the service layer must still scope queries, because a missing `SET LOCAL` would otherwise fail open. Phase 1 tests target the service layer.

---

## 7. Migrations

- Alembic, autogenerate reviewed by hand (never trusted blindly).
- One logical change per migration; both `upgrade` and `downgrade` where safe.
- **Backup before every migration** on data-bearing databases; restore verified afterwards when the migration is destructive.
- Migration tested on a copy of the DB first.
- `alembic upgrade head` must be idempotent from an empty DB and from the current head.

---

## 8. Seed data (synthetic only)

| Seed | Content |
|---|---|
| Roles | 8 system roles |
| Permissions | catalogue of permission keys |
| Demo tenant | `demo-tenant`, clearly labelled DEMO, synthetic figures only |
| Users | `owner@demo.local`, `accountant@demo.local`, `readonly@demo.local` with documented dev-only passwords in `.env.example` |
| Chart of accounts | minimal 20-account set for Phase 2 tests |

**Never** seed real customers, real GSTINs, real bank accounts, or anything resembling production data.

---

## 9. Backup interaction

- SQLite: `VACUUM INTO 'backup.db'` for a consistent snapshot while the app runs.
- Record size + SHA-256 in `backup_run`.
- Restore drill: restore into a **fresh** path, open read-only, compare row counts per table + a checksum of critical columns, then mark `verified`.
- A backup is not "successful" until a restore has been verified. See `docs/BACKUP_AND_RECOVERY.md` §5.

---

## 10. Open items

| ID | Item | Needed by |
|---|---|---|
| DB-01 | Confirm default currency + fiscal year start (OQ-03) | Phase 2 |
| DB-02 | Decide ULID vs UUIDv7 library | Phase 1 implementation |
| DB-03 | PostgreSQL hosting choice (local installer vs managed) | Phase 10 |
| DB-04 | Retention policy for `audit_log` and `login_attempt` | Phase 1 |
| DB-05 | Whether soft delete is needed for any Phase 1 table | Phase 1 |

---

## 11. Build 0.6 additive tables (2026-10-25)

These tables were added with `CREATE TABLE IF NOT EXISTS`; no existing table or column was
dropped, renamed or rewritten.

| Table | Purpose | Key constraints |
|---|---|---|
| `member_invite` | One-time team invite | `token_hash UNIQUE` (SHA-256 only), role CHECK, status CHECK, 7-day expiry, tenant FK, inviter FK |
| `statement_share` | Bearer link for one customer/vendor statement | `token_hash UNIQUE` (SHA-256 only), party_type CHECK, tenant FK, date range, expiry/revoke/view count |
| `gstr2b_import` | One imported 2B working file | `UNIQUE (tenant_id, sha256)`, month period, totals in paise, active/superseded status, tenant FK |
| `gstr2b_line` | Normalised 2B rows and match result | import FK, tenant FK, match status CHECK, nullable matched bill FK, amounts in paise |

Indexes cover tenant + period/status, tenant + party, and tenant + invoice lookup. Invite/share
tokens are never stored in plaintext. GSTR-2B imports are superseded rather than deleted.

## 12. Build 0.7 additive table (2026-10-25)

Added with `CREATE TABLE IF NOT EXISTS`; existing 2B import and line rows were not rewritten.

| Table | Purpose | Key constraints |
|---|---|---|
| `gstr2b_review` | Current ITC review annotation for one 2B line | `line_id UNIQUE` FK to `gstr2b_line`, tenant FK, status CHECK (`open`/`follow_up`/`itc_hold`/`accepted`), note text, `updated_by` FK, timestamp |

A line without a review row is presented as `open`. The unique `line_id` keeps one current state;
history is retained in `audit_log` (`gstr2b.review`, previous/new state and note). Index
`ix_gstr2b_review_tenant` supports tenant/status summaries. The table stores no ITC amount: all
displayed tax values come from the immutable 2B line and posted books.

## 13. Build 0.10 additive table (2026-10-25)

Added with `CREATE TABLE IF NOT EXISTS`; no existing account or journal data was rewritten.

| Table | Purpose | Key constraints |
|---|---|---|
| `bank_account` | Full bank details for a bank ledger account | `account_id UNIQUE` FK to `account`, tenant FK, bank name, account number, IFSC, branch, holder, timestamp |

Creating a bank account inserts a postable asset `account` and exactly one linked `bank_account`
row in the same transaction. The legacy `1010 Bank` account remains usable with the bank details
stored in `tenant`/Business Settings; new bank accounts carry their own details. The table stores no
balance: every book and reconciliation figure is derived from posted `journal_line` rows. Index
`ix_bank_account_tenant` supports tenant listing.

Opening balances (Build 0.10) add **no table**. They are ordinary balanced `journal_entry` rows with
`source_type='opening'` plus two `journal_line` rows, and the contra account is a normal `account`
row named **Opening Balance Equity** (created lazily from code `3200`). The audit trail records
`opening_balance.set`; replacement uses the same reversal rows as a manual journal.

Bulk opening-balance import (Build 0.11) also adds **no table and no column**. The uploaded/pasted CSV
is validated in memory and is not retained. Each accepted row becomes an ordinary opening journal, so
the existing `journal_entry`, `journal_line` and `audit_log` rows are the record. In addition to the
per-account `opening_balance.set` events, one `opening_balance.bulk_import` audit row stores the
filename, row count, Dr/Cr totals and created entry IDs. The import is one outer transaction; a
failure rolls back every row and any Opening Balance Equity account created by that attempt.

## 14. Build 0.10 Account 360 additive schema (2026-10-26)

All changes are additive columns or `CREATE TABLE IF NOT EXISTS`; no account, journal, party or item
row is deleted or rewritten.

| Object | Change | Purpose / constraints |
|---|---|---|
| `account.group_code` | `TEXT NOT NULL DEFAULT ''` | Classification such as `receivable`, `payable`, `bank`, `loans`, `duties_taxes`, `suspense`, `capital`, `drawings`, `retained_earnings`, `profit_loss`, `sales`, `purchase`, `depreciation`, `opening_equity`. The five `account.type` values still decide debit/credit normal balance. |
| `account_profile` | new table | One descriptive profile per account: legal/company name, contact, phone, email, website, address, city, state, PIN, country, GSTIN, PAN, CIN, organisation type, industry, credit days/limit, linked `party_type`/`party_id`, lender, loan account, sanction/maturity dates, interest basis points, tenure, EMI paise, security and notes, plus created/updated by/time. `UNIQUE (tenant_id, account_id)`; tenant and account FKs. |
| `customer.account_id`, `vendor.account_id` | nullable `TEXT` | Optional one-to-one link to the party's sub-ledger account. Indexed by `(tenant_id, account_id)`. |
| `customer.credit_days`, `credit_limit_paise`; same on `vendor` | `INTEGER DEFAULT 0` | Party credit terms copied from the account profile and editable through the same flow. |
| `item.hsn` | `TEXT NOT NULL DEFAULT ''` | HSN/SAC for GST-ready invoices. |
| `item.category`, `item.brand`, `item.barcode` | `TEXT NOT NULL DEFAULT ''` | Product grouping and identification. |
| `item.mrp_paise`, `item.margin_bp` | `INTEGER DEFAULT 0` | MRP in paise and margin in basis points; sale price, cost and GST remain integer values. |

The known seed chart is backfilled to its group; bank ledgers created before groups existed are
backfilled to `group_code='bank'`. Custom ledgers are not guessed. `account_profile` is included in
backup row-count verification. Indexes on newly added party columns are created **after**
`_ensure_columns`; creating them inside the base schema would fail on an existing database. An
existing pre-Account-360 database is regression-tested by `TestAdditiveMigration`. Account edits
update only descriptive fields and the party/bank profile; posted `journal_entry` and `journal_line`
rows are immutable.

## 15. Build 0.11 per-user theme column (2026-10-26)

This is an additive column only; no accounting table, journal, party, item or account row changes.

| Object | Change | Purpose / constraints |
|---|---|---|
| `user.theme` | `TEXT NOT NULL DEFAULT 'ocean'` | Personal workspace palette: `ocean`, `emerald`, `violet` or `sunset`. Applied by `layout()` through `data-theme`; changed from Settings → Appearance; defaulted for existing users by `_ensure_columns`. |

`POST /preferences/theme` is CSRF-protected, available to any signed-in member (it changes only that
user's screens), and writes one `user.theme_updated` `audit_log` row with the old and new palette.
The value is a fixed allow-list; unknown values are rejected with HTTP 400. A non-sensitive
`ui_theme` cookie mirrors the choice for the sign-in page and the public landing page's dark colour
variant. The landing picker sets only that cookie through a validated `/home?theme=<key>` GET; it
does not write `user.theme` or an audit row. Backups include the `user` table automatically; the
theme is not derived from or written to any ledger row.

## 16. Build 0.11 account archive/merge columns (2026-10-27)

Additive columns only; no account, journal, party, item or opening-balance row is deleted or
rewritten. The columns are present in the base schema and added to an existing database by
`_ensure_columns` before dependent indexes are created.

| Object | Change | Purpose / constraints |
|---|---|---|
| `account.status` | `TEXT NOT NULL DEFAULT 'active'` | `active` or `archived`. Posting paths and new-posting selectors require `active`; archived ledgers remain visible in the ledger hub's archived list. |
| `account.archived_at` | `TEXT NULL` | UTC timestamp of the archive/merge action. |
| `account.archived_by` | `TEXT NULL` | User ID that archived or merged the source. |
| `account.merged_into_id` | `TEXT NULL` | Target account ID when the source was merged; null for a plain archive. The source stays `archived`. |
| `ix_account_status` | `CREATE INDEX` after migration | Supports tenant + status filtering; created after the additive columns exist. |

Archive/merge itself posts no new table. A merge with a non-zero net balance writes one ordinary
balanced `journal_entry` (`source_type='merge'`, `source_id` = source account) plus two
`journal_line` rows, then updates the source account's status/metadata. A zero-balance merge writes
no journal. The source's existing `journal_line` rows are not moved, renumbered or edited, so the
trial balance and all reports remain derived from the same immutable lines. `account.archive`,
`account.merge` and `account.restore` audit rows carry the reason, codes, amount, journal entry and
repointing counts. `account_profile` and `bank_account` rows are retained for archived ledgers;
Bank Book and reconciliation selectors hide them, but their details are available if restored.


## 17. Build 0.11 read-only analytics views (2026-10-27)

These are `CREATE VIEW IF NOT EXISTS` objects, not tables. They copy no rows and add no cached
totals. `db.init_db` creates them after `SCHEMA`, `_ensure_columns` and `POST_MIGRATION_INDEXES`, so
an existing database upgrades without rewriting any accounting row.

| Object | Columns / purpose |
|---|---|
| `v_analytics_journal` | Tenant, entry id/no/date/month, source type/id, status, reversal, line id/no, account id/code/name/type/group, party id, debit, credit, signed amount and memo. Joins `journal_entry`, `journal_line` and `account`; history stays immutable. |
| `v_analytics_monthly` | Per tenant, month and account type: debit, credit, income amount (credit - debit for income), expense amount (debit - credit for expense) and signed amount (debit - credit). Built only from `v_analytics_journal`. |

The views are read-only contracts for the internal JSON API, the Analytics Overview pilot and the
Build 0.12 Excel/Power BI adapters. Every API query also filters by `tenant_id`; the views do not enforce
tenant isolation on their own. Reports and metrics continue to use integer paise and the existing
deterministic accounting functions. No view is treated as an authoritative source separate from the
posted journal.

The schema also supports the optional `ARTHIVIO_HOST` server binding (default `127.0.0.1`). This is
a process setting, not a database change.


## 18. Build 0.12 Excel, Power BI and insights: no schema change (2026-10-28)

Build 0.12 adds **no table, no column and no index**. The Excel workbook, static Power BI ZIP and
grounded-insight layer are read-only adapters over the existing journal and analytics views:

- `.xlsx` import is converted to neutral CSV in memory and then handled by the same
  `opening_import`, `bank` and `gstr2b` services. Uploaded files are not stored in SQLite or on disk.
  The existing `bank_import`, `bank_statement_line`, `gstr2b_import`, `gstr2b_line`, journal and
  audit tables remain the record.
- The workbook and Power BI ZIP are generated from posted journal lines and the same deterministic
  report functions; they create no cache table and no second ledger.
- Insights are computed on request from the actuals contract; they are not persisted, so there is
  no table of AI claims that could drift from the ledger.
- All Build 0.12 queries remain tenant-scoped and money remains integer paise. No posted row is
  rewritten by an export, an insight request or a `.xlsx` import preview.


## 19. Build 0.13 Report Library and management reports: no schema change (2026-11-04)

Build 0.13 adds **no table, no column and no index**. The Report Library catalogue is a static
in-code list; the nine management reports are computed on request from the same posted journal,
invoice, bill and account rows:

- Cash flow, ratios, period comparison, reversal register, account activity, sales register,
  purchase register, expense breakdown and working-capital cycle use tenant-scoped queries and the
  existing `profit_and_loss`, `balance_sheet` and account-balance functions.
- No report total is cached or persisted. Every screen recomputes from posted records, so a report
  cannot drift from the ledger.
- CSV exports stream the same computed rows; amounts are exact decimal strings derived from integer
  paise. No export writes a journal or changes a posted row.
- The `period_lock` table remains the posting guard; reports may read a locked period but cannot
  post into it.


## 20. Build 0.14 first-run setup and offline package: no schema change (2026-11-04)

Build 0.14 adds **no table, no column and no index**. First-run setup uses the existing `tenant`,
`user`, `membership`, `account` and `audit_log` tables:

- `security.create_owner()` creates the tenant, the default chart of accounts, the user and the
  owner membership inside one `BEGIN IMMEDIATE` transaction. The empty-user check is repeated
  inside the transaction, so concurrent first-run requests cannot create two owners.
- The setup audit event is `setup.owner_created`; the normal session audit event follows after the
  session is created.
- The offline package is a packaging and runtime change only. It uses the same SQLite schema and
  the same database file inside the package's `data` folder.
- The external-drive backup is a byte-for-byte copy of a verified SQLite backup; it does not write
  to the source database except for the existing `backup_run` record.


## 21. Build 0.15 editable manual entries: no schema change (2026-11-05)

Build 0.15 adds **no table, no column and no index**. It uses the existing journal and audit
structures:

- The original journal keeps `status='reversed'`; the mirrored reversal is a normal journal row
  with `source_type='reversal'` and `reversal_of` set to the original.
- The corrected replacement is a normal posted journal with `source_type='manual'` and
  `source_id` set to the original entry id. This is provenance, not a foreign-key relation.
- `audit_log.action='journal.edit'` stores the original, reversal and corrected entry ids, the
  reason and the line count in its JSON metadata.
- `security.create_business()` reuses `tenant`, `account`, `membership` and `audit_log`; it creates
  a new tenant with the standard chart and no journal rows.


## 22. Build 0.16 report screens: no schema change (2026-11-05)

Build 0.16 adds **no table, no column, no index and no cached total**. The ten new reports read the
existing posted invoice, invoice_line, bill, bill_line, credit_note, credit_note_line, debit_note,
debit_note_line, item, customer, journal_entry and journal_line rows.

- `receivable_ageing()` now selects `invoice.customer_id` and includes it in each result row. This is
  a read-only query change, not a schema change. Credit-limit utilisation uses it to aggregate open
  invoices by customer id instead of matching customer names.
- Stock summary derives period movements from the document-line tables and uses `item.stock_milli`
  as the current anchor. It does not write or adjust stock.
- Report CSV exports are generated from the same functions and are not stored.
- No report caches a total. Every screen recalculates from posted rows on each request.

## 23. Build 0.17 report screens: two additive columns and one additive table (2026-11-06)

Build 0.17 adds **two additive columns and one additive table**. No existing column, table or
cached total is dropped or rewritten.

- `item.reorder_level_milli INTEGER NOT NULL DEFAULT 0` stores the item's reorder threshold in the
  same thousandth-unit convention as `stock_milli`. Existing items receive zero, which means "no
  level configured". The migration uses the existing additive `_ensure_columns()` path and does not
  rewrite rows.
- `journal_entry.rule_version TEXT NOT NULL DEFAULT 'posting-v1'` records the posting-rule
  version on every new entry. The additive migration labels existing rows `posting-v1` without
  rewriting journal amounts or dates.
- `budget` stores one planning amount per tenant, income/expense ledger and month:

```sql
CREATE TABLE budget (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    account_id TEXT NOT NULL REFERENCES account(id),
    period TEXT NOT NULL,                 -- YYYY-MM
    amount_paise INTEGER NOT NULL DEFAULT 0 CHECK (amount_paise >= 0),
    note TEXT NOT NULL DEFAULT '',
    created_by TEXT REFERENCES user(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES user(id),
    UNIQUE (tenant_id, account_id, period)
);
CREATE INDEX ix_budget_tenant_period ON budget (tenant_id, period);
```

- Budget rows are planning data, not journal entries. They never change a posted balance. The
  `/budgets` screen creates, updates or removes one ledger-month and writes `budget.create`,
  `budget.update` or `budget.delete` to `audit_log`. `budget.manage` is required to change a budget;
  `report.view` is enough to read R-901.
- The item master form accepts the reorder level and stores it with `money.parse_qty()`.
- R-504 uses the column for below-level shortages and also surfaces zero/negative stock when no level
  is configured. It never changes stock.
- The other reports read existing journal, document, item, customer, vendor, user and `period_lock`
  rows. No new table is required for opening/closing, locked periods, salesperson performance,
  price variance, stock movements, inventory valuation, dead/slow stock, inventory-to-GL
  reconciliation, receivables risk, rule version usage, cash-flow forecast, tax ledger, KPI pack,
  trend explanation, revenue forecast or anomaly digest.
- Stock valuation uses the current moving weighted-average `item.cost_paise`; no historical cost
  layer table exists. FIFO and batch/expiry remain future schema work.
- No report caches a total. Every screen recalculates from posted rows on each request.

## 24. Build 0.17 stock adjustments: one additive table and one additive chart account (2026-11-06)

Build 0.17 also adds the R-506 manual stock-adjustment register. It adds **one table and one chart
account**; no existing column, table or cached total is dropped or rewritten.

```sql
CREATE TABLE stock_adjustment (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(id),
    adjustment_no TEXT NOT NULL,
    adjustment_date TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES item(id),
    qty_milli INTEGER NOT NULL CHECK (qty_milli <> 0),
    unit_cost_paise INTEGER NOT NULL CHECK (unit_cost_paise >= 0),
    value_paise INTEGER NOT NULL CHECK (value_paise <> 0),
    reason TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    journal_entry_id TEXT NOT NULL REFERENCES journal_entry(id),
    idempotency_key TEXT,
    created_by TEXT REFERENCES user(id),
    created_at TEXT NOT NULL,
    UNIQUE (tenant_id, adjustment_no),
    UNIQUE (tenant_id, idempotency_key)
);
CREATE INDEX ix_stock_adjustment_tenant_date
    ON stock_adjustment (tenant_id, adjustment_date);
CREATE INDEX ix_stock_adjustment_item
    ON stock_adjustment (tenant_id, item_id, adjustment_date);
```

- `qty_milli` is signed: positive increases stock, negative decreases it. `value_paise` is signed to
  match the direction and is snapshotted at the item's current `cost_paise`. The item's cost is not
  changed by the adjustment.
- The new `5950 Stock Adjustments` expense account is in the standard chart. Existing tenants receive
  it on their first adjustment through `db.seed_chart()`. An increase debits `1200 Inventory` and
  credits `5950`; a decrease reverses those lines. Both post through the existing balanced
  `post_journal()` path and write a normal journal entry with `source_type='stock_adjustment'`.
- The register row stores the reason, note, journal id, optional idempotency key and creator.
  `audit_log.action='stock.adjust'` records the item, signed quantity, unit cost, value, reason and
  journal id. There is no approval workflow.
- R-502, R-501, R-503, R-505 and R-507 include `stock_adjustment` as a movement source. `stock now`
  is always the current item-master quantity, not a historical balance at the adjustment date.
- The backup table list includes `stock_adjustment`; backup verification compares its row count with
  the source database.
- `5950` is an expense ledger. A positive adjustment therefore credits an expense account and a
  negative adjustment debits it. The P&L shows the net stock-adjustment expense; it is not an
  other-income or revaluation reserve.

## 25. Build 0.18 draft invoices: no new table or column (2026-11-06)

Build 0.18 adds the R-204 draft sales-invoice workflow without a schema migration. The existing
`invoice.status` CHECK already allowed `draft`, and `invoice_line` already stores the priced lines.

- A draft stores `status='draft'`, `journal_entry_id=NULL` and a separate `DRAFT-#####` number from
  the additive `invoice_draft` number sequence. `invoice.invoice_no` stays unique per tenant.
- Posting updates the same invoice row to `status='posted'`, assigns the next `INV-#####`, sets
  `journal_entry_id` and reduces `item.stock_milli` in one transaction. The draft number is retained
  only in the `invoice.post` audit metadata.
- Voiding sets `status='void'` and writes `invoice.void_draft`; no row is deleted.
- There is no draft state in `journal_entry` and no draft state in `bill`. R-204 therefore reads only
  `invoice.status='draft'` and is labelled as draft sales invoices only.
- No table, column, index, cached total or destructive migration was removed or rewritten.
