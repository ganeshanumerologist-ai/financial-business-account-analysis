# ARTHIVIO — Architecture

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-10-24 |
| Status | Draft for owner approval |
| Decision | **Option A** — Next.js (TypeScript) + FastAPI (Python), approved 2026-10-24 (D-001) |

---

## 1. Stack

| Layer | Choice | Version (target) | Why |
|---|---|---|---|
| Frontend | Next.js (App Router) + TypeScript | 15.x / TS 5.x | Component UI, high-DPI vector rendering, future report density, spec §20 fit |
| Styling | Plain CSS modules + design tokens (no heavy UI kit) | — | Full control over the ivory/emerald/gold palette; avoid licensing and bloat |
| Charts | Apache ECharts | 5.x | Maintained, canvas/SVG, crisp at 4K, large datasets |
| Backend | FastAPI | 0.11x | Typed API, automatic OpenAPI, Python ecosystem for finance logic |
| Validation | Pydantic v2 | 2.x | Strict schemas, decimal support |
| ORM / SQL | SQLAlchemy 2.x + Alembic | 2.x | Explicit transactions, migrations |
| Database | SQLite (Phase 1) → PostgreSQL (production path) | — | Zero-install now; PostgreSQL-ready schema, no SQLite-only SQL |
| Password KDF | Argon2id (`argon2-cffi`) | — | Current best practice, no external service |
| Sessions | Server-side session table + opaque cookie | — | Revocable, no JWT-in-localStorage risk |
| Tests | pytest (+ Hypothesis later), Vitest/Playwright at Phase 6 | — | Deterministic finance tests are the release gate |

Runtime note: `C:\Users\vicky\node-portable\node-v20.20.2-win-x64` (Node 20.20.2 / npm 10.8.2) and `C:\Users\vicky\git-portable` (git 2.56.0). Neither is on `PATH`; a `dev.ps1` bootstrap will set it per session.

---

## 2. Component view

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (desktop / tablet / mobile)                          │
│  Next.js UI — server components + client islands              │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS (local: http://localhost)
                            │ credentials: session cookie
┌───────────────────────────▼──────────────────────────────────┐
│  Next.js server (port 3000 in dev)                            │
│  • renders pages, holds no secrets                            │
│  • calls backend with the user's session cookie               │
└───────────────────────────┬──────────────────────────────────┘
                            │ JSON /api/v1
┌───────────────────────────▼──────────────────────────────────┐
│  FastAPI app (port 8000)                                      │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Auth       │  │ Authorisation│  │ Domain services      │   │
│  │ sessions   │→ │ tenant+role  │→ │ (Phase 2+: ledger,   │   │
│  │ CSRF       │  │ policy gate  │  │  invoicing, stock)   │   │
│  └────────────┘  └──────────────┘  └──────────┬───────────┘   │
│         │                                      │              │
│  ┌──────▼──────────────────────────────────────▼───────────┐  │
│  │ Data access layer — every query takes tenant_id         │  │
│  │ SQLAlchemy 2.x · explicit transactions                  │  │
│  └──────────────────────────┬──────────────────────────────┘  │
└─────────────────────────────┼─────────────────────────────────┘
                              │
                   ┌──────────▼───────────┐      ┌──────────────┐
                   │ SQLite (WAL) Phase 1 │      │ Backup store │
                   │ → PostgreSQL prod    │─────▶│ ./backups    │
                   └──────────────────────┘      └──────────────┘
```

---

## 3. Request flow with tenancy enforcement

1. Request arrives with session cookie.
2. `resolve_session()` → user, membership list, active tenant.
3. `require_permission(permission, tenant_scope)` → 403 if not allowed.
4. Handler calls a service with an explicit `TenantContext` object.
5. Repository methods require `TenantContext` and inject `tenant_id` into **every** query — there is no code path that queries a tenant table without it.
6. Response is serialised from a schema that contains no other tenant's identifiers.

Defence in depth: application-level scoping now, **PostgreSQL Row-Level Security planned** for production (`SET LOCAL app.tenant_id`). The file DB cannot enforce RLS, so Phase 1 compensates with a single repository entry point plus tests that attempt cross-tenant reads.

---

## 4. Proposed repository layout

```
/
├── apps/
│   ├── web/                 # Next.js front end
│   │   ├── app/             # routes (App Router)
│   │   ├── components/
│   │   ├── lib/             # api client, auth helpers
│   │   └── styles/          # tokens, modules
│   └── api/                 # FastAPI back end
│       ├── app/
│       │   ├── main.py
│       │   ├── core/        # config, security, tenancy, errors
│       │   ├── models/      # SQLAlchemy
│       │   ├── schemas/     # Pydantic
│       │   ├── services/    # domain logic (no HTTP)
│       │   ├── api/v1/      # routers
│       │   └── db/          # session, repositories
│       ├── migrations/      # Alembic
│       └── tests/
├── docs/
├── scripts/                 # dev.ps1, backup, restore-verify
└── .github/                 # CI later (no auto-push)
```

---

## 5. API conventions

- Base path `/api/v1`, JSON only, UTF-8.
- Error envelope: `{"error": {"code": "TENANT_FORBIDDEN", "message": "...", "fields": {...}, "correlation_id": "..."}}`.
- Never leak stack traces or SQL; log them server-side with the correlation ID.
- Idempotency: `Idempotency-Key` header required on document-creating endpoints (Phase 2+).
- Pagination: cursor-based for ledgers, `limit` + `after`; page-based only for small reference lists.
- Dates: ISO 8601; all timestamps stored UTC; business dates stored as `DATE` in the tenant's timezone context.

---

## 6. Frontend architecture

- Server components for data-heavy pages; client islands only for interactivity (filters, forms).
- Design tokens in one place: ivory `#F7F5EF`, emerald `#176B4D`, sage `#DCE8D9`, gold `#C6A15B`, ink `#183E35`.
- Typography scale with a minimum 16 px body, 1.5 line-height; contrast checked to WCAG AA.
- Charts: ECharts with `devicePixelRatio` respected → sharp on 4K/8K, no raster backgrounds.
- No city photography, no unverifiable statistics (spec §4, §5; defects B-004, B-005).
- States required on every data view: loading, empty, error, permission-denied, offline/stale.

---

## 7. Security architecture (summary — detail in `docs/SECURITY_PLAN.md`)

| Concern | Approach |
|---|---|
| Passwords | Argon2id, per-user salt, pepper from env, configurable cost |
| Sessions | Opaque 256-bit token, hashed at rest, HttpOnly/Secure/SameSite=Lax, 30 min idle + 12 h absolute |
| CSRF | Double-submit token bound to session, required on mutating requests |
| Authorisation | Permission strings (`ledger.post`, `export.report`) checked server-side |
| Tenancy | `TenantContext` required by repositories + RLS plan |
| Secrets | `.env` (git-ignored) + `.env.example` documented; no defaults for production |
| Audit | Append-only `audit_log` with actor, tenant, action, target, result, IP, UA |
| Backups | Local encrypted archive + restore drill; off-site in Phase 10 |

---

## 8. Environments

| Env | Purpose | Database | Notes |
|---|---|---|---|
| dev | Local development | SQLite file | `dev.ps1` sets `PATH`, starts both apps |
| test | Automated tests | In-memory/temp SQLite or per-test file | Isolated per test, no shared state |
| prod | Not built yet | PostgreSQL | Requires Phase 10 readiness + owner approval |

---

## 9. Key trade-offs (recorded honestly)

| Decision | Benefit | Cost / risk |
|---|---|---|
| SQLite first | Zero install, fast start, real transactions | No RLS, single-writer concurrency; must migrate before multi-user |
| Two languages (TS + Python) | Best UI + best finance libraries | More setup; contract drift risk → mitigated by generated OpenAPI types later |
| No UI kit | Exact brand control, no bloat | More hand-built components; slower Phase 6 |
| Server-side sessions | Revocable, simple to reason about | Needs a session table and cleanup job |
| Python 3.14 | Already installed | Some packages may lag; fallback to a 3.12 portable build if wheels are unavailable |

---

## 10. What is deliberately NOT designed yet

Ledger schema details beyond the outline, tax/GST rules, offline sync protocol, AI grounding pipeline, and reporting query engine. Designing them now would be speculation; they get their own architecture pass in their phase, with tests.

---

## 11. Phase 1 build order (approved scope only)

1. `dev.ps1` bootstrap + repo skeleton (no features).
2. Config + secrets loader + error envelope + correlation IDs.
3. Database models, migrations, tenant/user/membership/role/session/audit tables.
4. Auth: register, login, logout, session rotation, password policy.
5. Authorisation: permission catalog, role matrix, dependency guards.
6. Tenant context plumbing + cross-tenant tests.
7. Audit logging.
8. Backup script + **restore-verify** script + drill.
9. Test suite + evidence in `docs/TEST_RESULTS.md`.
10. Stop, report, wait for owner approval before Phase 2 (accounting core).


---

## 11. Implementation status (2026-10-24, Build 0.1)

| Module | Responsibility | State |
|---|---|---|
| `app/money.py` | integer paise, half-up rounding, largest-remainder allocation | Implemented, tested |
| `app/db.py` | schema, chart of accounts, per-tenant sequences, WAL connection | Implemented, tested |
| `app/accounting.py` | posting, reversals, invoicing, ledger, TB, P&L, balance sheet, customer statements | Implemented, tested |
| `app/security.py` | scrypt hashing, sessions, CSRF token, RBAC, tenant authorisation, lockout | Implemented, tested |
| `app/server.py` | HTTP routing, server-rendered UI, cookie/CSRF handling | Implemented, HTTP-tested |
| `app/demo.py`, `scripts/seed_demo.py` | synthetic demo books | Implemented |
| `dev.ps1` | test → seed → run | Implemented |

Deviations from the original plan, both recorded in `docs/DECISION_LOG.md`:

1. **D-007** — runtime is the Python standard library plus SQLite, not FastAPI + Next.js,
   because PyPI is unreachable on this machine. The schema and service boundaries are
   framework-neutral so the API can be wrapped later.
2. **D-008** — accounting features ship in the same slice as the security foundation, but
   every posting still passes tenant authorisation and writes an audit record.

Not yet implemented from Phases 1–6: automated backup + restore drill, payment/receipt
posting, purchases/AP, credit notes in the UI, GST returns, exports, multi-user admin UI,
PostgreSQL deployment, and the React front end.


---

## 12. Implementation status (2026-10-24, Build 0.2)

The transaction model is now complete for the SME bookkeeping loop:

```
customer ?? invoice ??? AR ?? receipt ??? cash/bank
              ?            ?
              ? credit note? (revenue + GST reversed, stock returned at cost)

vendor ?? bill ??? AP ?? vendor payment ??? cash/bank
            ?
            ? inventory in at weighted-average cost (or purchases for non-stock items)
```

| Concern | Implementation |
|---|---|
| Atomicity | Invoice, bill, receipt/payment, credit note and reversal each run in one `BEGIN IMMEDIATE` transaction. `post_journal` detects an open transaction and uses a savepoint instead of nesting. |
| Idempotency | Document tables and journal entries carry `idempotency_key`; lookups happen before validation so replays return the original document. |
| Allocation | `payment_allocation` links a receipt/payment to invoices/bills; outstanding = document total ? allocated ? credit notes. Over-allocation is rejected inside the same transaction. |
| Stock valuation | Perpetual, weighted average: `new_cost = (old_qty*old_cost + taxable*1000) / (old_qty + qty)` in milli-paise, half-up. Only `track_stock` items move. |
| Returns | Credit note reads invoice lines, validates remaining returnable quantity, reverses revenue by item `revenue_code`, reverses output GST by place of supply, and restores stock at current cost. |
| Ageing | Derived from outstanding balances and document dates; buckets current / 31-60 / 61-90 / 90+. |
| GST | Working summary from GST control accounts plus sales/purchase registers. Explicitly not a filed return. |
| Backup | `app/backup.py` online backup + four checks (integrity, foreign keys, balanced journals, row counts) before a run is marked verified. |
| UI | Grouped navigation (Overview / Sales / Purchases / Books / Reports / Masters); every list links to its source document. |

Known architectural limits: single-process HTTP server, SQLite single-writer, no background
jobs, no PDF renderer, no bank-feed integration. These are deployment decisions, not
accounting shortcuts.


## 13. Implementation status (2026-10-24, Build 0.3)

### 13.1 Business profile and additive migration

`tenant` now stores the details a GST invoice needs: legal name, GSTIN, GST state code and
state name, address, city, PIN, phone, email, bank name/account/IFSC and invoice terms.
`customer` stores a billing address. `db.init_db` runs an idempotent `_ensure_columns`
migration (`ALTER TABLE ... ADD COLUMN` only); no table is dropped or rewritten and existing
rows are preserved. Fresh databases get the same columns from the base schema.

Settings are edited at `/settings` and require the `tenant.manage` permission (owner role).
Every change is audited as `tenant.settings_updated`. Validation covers GSTIN, GST state,
PIN code, email and IFSC.

### 13.2 Print-ready tax invoice

`GET /invoices/<id>/print` renders a standalone A4 HTML document (no application shell) with
its own `PRINT_CSS`:

- seller identity/GSTIN/address/contact, buyer identity/GSTIN/state, invoice number/date,
  place of supply, reverse charge
- per-line HSN/SAC, quantity, rate, discount, taxable value, GST rate and CGST/SGST or IGST
- rate-wise totals, round-off, invoice total, amount in words (Indian numbering)
- bank details, terms and signature block
- a `window.print()` button; users choose "Save as PDF" in the browser

Per-line CGST/SGST allocation is derived from the invoice tax total with a largest-remainder
style correction, so `sum(line CGST) + sum(line SGST) == invoice tax` exactly, including
odd-paise invoices. Inter-state invoices put the whole line tax in IGST.

The print view uses the same tenant-scoped invoice query as the detail page, so a foreign
invoice id returns 404.

### 13.3 GSTR-1 style working export

`accounting.gstr1_data(conn, tenant_id, from, to)` prepares:

- **B2B** - registered buyers, one row per invoice per rate; invoice value appears once per
  invoice (first rate row) to avoid double counting
- **B2CS** - unregistered buyers aggregated by place of supply and rate
- **HSN** - item HSN/SAC + rate, quantity, taxable value, CGST/SGST/IGST and total value
- **Credit notes** - `CDNR` (registered) / `CDNUR` (unregistered), with GST split by the note's
  place of supply
- document counts and warnings (missing supplier GSTIN, B2C invoices, missing HSN)

`/export/gstr1.csv` writes one UTF-8-BOM CSV with a `Section` column and `TOTAL` / `CN TOTAL`
rows. `/export/gstr1.json` writes `arthivio-gstr1-working-v1` with amounts as exact INR
decimal **strings** (no binary floats) plus `amount_unit`, `note` and `warnings`. Neither file
claims to be an uploaded or filed return.

### 13.4 Deliberate limits

- No PDF library, no GST portal integration, no official GSTR-1 schema claim.
- Settings are owner-only; admin/manager roles can view but not change them.
- Credit notes are reported at document level in GSTR-1 (rate-wise credit-note rows are a
  later refinement).

## 14. Implementation status (2026-10-24, Build 0.4)

### 14.1 Debit notes / purchase returns

`accounting.create_debit_note` mirrors `create_credit_note` on the purchase side:

- requires a reason and at least one bill line; the bill must be posted
- reverses the line's taxable value (discount apportioned by quantity) and input GST
  (CGST/SGST for intra-state, IGST for inter-state, using the bill's place of supply)
- debits Accounts Payable and credits Inventory (stock items) or Purchases (non-stock items)
  plus the input GST accounts
- takes stock out at the original bill value and restates the weighted-average cost from the
  remaining inventory value; a negative restatement is blocked with `COST_UNDERFLOW`
- blocks returns above the unreturned quantity (`OVER_DEBIT`) and above available stock
  (`INSUFFICIENT_STOCK`); a paid bill can still be returned, leaving a vendor credit
- is idempotent, uses the `DBN-00001` sequence, and writes `debit_note.create` to the audit log

`bill_outstanding` subtracts posted debit notes, so bill status, AP ageing and vendor balances
agree. The vendor statement reports payments and debit notes separately.

### 14.2 Bank reconciliation

`app/bank.py` adds `bank_import` and `bank_statement_line`. The flow is:

1. parse a CSV (`Date`, `Description`, `Reference`, `Debit`, `Credit`, optional `Balance`;
   or `Amount` + `Dr/Cr`; or `Withdrawal`/`Deposit`), accepting ISO, `DD/MM/YYYY`,
   `DD-MM-YYYY`, dotted and month-name dates
2. import idempotently; the unique key is `(tenant, bank account, SHA-256 row hash)`
3. suggest matches on the bank account's posted journal lines with the exact signed amount
   and a date difference of at most 7 days (reference matches rank first)
4. auto-match only when the best candidate is unique; ties stay for manual review
5. manual match/unmatch; matching validates tenant, account, posted status, amount equality
   and one-to-one use of the ledger line
6. report statement net, ledger net, matched/unmatched amounts, opening/closing ledger
   balance, latest statement balance and the difference

Permissions: `bank.reconcile` (owner/admin/manager/accountant) and `debit_note.create`
(owner/admin/manager/accountant). Audit events: `bank.import`, `bank.match`, `bank.unmatch`,
`bank.auto_match`, `debit_note.create`. Matching never writes a journal entry; the ledger stays
the single source of truth.

### 14.3 Deliberate limits

- No partial-amount or one-to-many bank matching; no auto-posting of bank charges/interest.
- No GSTR-2/2B purchase reconciliation or GSTR-3B.
- CSV only; bank API feeds, Excel import and cheque printing are future work.

