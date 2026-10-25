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
