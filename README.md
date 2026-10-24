# ARTHIVIO — Smarter Finance. Stronger Business.

Business finance, accounting and analytics platform for Indian SMEs.

**Status: working local prototype (Build 0.1).** Invoices, ledger, trial balance, P&L,
balance sheet and customer statements are implemented, posted through a real double-entry
engine, and covered by **42 automated tests that pass on this machine** (see
`docs/TEST_RESULTS.md`, run `RUN-2026-10-24-02`).

It is **not production-ready yet**: payments/receipts, purchases/AP, GST returns, exports
and multi-user administration are not built. Do not put real customer data in it.

---

## Quick start

Requirements: Python 3.12+ (verified on 3.14.6). No pip packages, no Node, no database
server needed.

```powershell
cd "D:\financial business account data analysis"
.\dev.ps1                 # runs tests, seeds demo data, starts http://127.0.0.1:8000
```

Or step by step:

```powershell
python -m unittest discover -s tests     # 42 tests
python scripts/seed_demo.py              # demo books (idempotent)
python -m app.server                     # http://127.0.0.1:8000
```

Demo logins (synthetic data only — change before any real use):

| Role | Email | Password |
|---|---|---|
| Owner | `owner@arthivio.test` | `ArthivioDemo!2026` |
| Admin | `admin@arthivio.test` | `ArthivioDemo!2026` |

Override the password with `ARTHIVIO_DEMO_PASSWORD`, the database path with
`ARTHIVIO_DB`, and the port with `PORT`.

---

## What actually works

| Area | Behaviour | Evidence |
|---|---|---|
| Invoices | Multi-line, discounts, per-line GST, CGST/SGST vs IGST by place of supply, optional round-to-rupee, sequential numbering, idempotent creation | `test_accounting.TestInvoice`, `test_web.test_05` |
| Posting engine | Integer-paise double entry, exact balance enforcement, per-tenant accounts, period locks, immutable entries + reversals | `TestPosting`, `TestReports.test_reversal_nets_to_zero` |
| Inventory | Perpetual stock, COGS posting at item cost, negative-stock block | `test_cogs_and_stock`, `test_insufficient_stock_blocked` |
| Receivables | Customer-wise balances and statements, reconciled to the AR control account | `test_customer_statement_matches_receivable_control` |
| Reports | Trial balance, general ledger with running balance, P&L, balance sheet (A = L + E badge) | `test_04`, `test_balance_sheet_equation` |
| Security | scrypt password hashing, server sessions with idle/absolute expiry, CSRF on every POST, RBAC matrix, login lockout, audit log | `TestSecurity`, `test_06_csrf_required` |
| Tenancy | Every query is tenant-scoped; cross-tenant account, ledger, invoice and statement access is blocked and tested | `test_cross_tenant_account_rejected`, `test_08` |
| UI | Responsive server-rendered UI in the ARTHIVIO palette (ivory/emerald/gold), no stock photos, no invented statistics | manual browser checks |

## What is not built yet (honest gaps)

- Receipts/payments against invoices, credit notes, debit notes
- Purchases, accounts payable, vendor ledger, expenses beyond simple journals
- GST returns (GSTR-1/3B), e-invoice/e-way integration, TDS/TCS
- Bank reconciliation, cash/bank books with payment modes
- PDF/Excel export, printing, email delivery
- Multi-user invite/role administration UI (roles exist in the data layer)
- Fixed-asset depreciation, payroll, budgets, cost centres
- Backup + restore drill automation (documented, not implemented)
- PostgreSQL deployment path, Next.js front end, hosting
- Load, concurrency and penetration testing

## Architecture

Zero-dependency Python 3 + SQLite (WAL). This was a deliberate response to PyPI being
unreachable on this machine (decision D-007); it removes the supply-chain surface for the
accounting core and keeps the app runnable offline.

```
app/
  money.py        integer paise, half-up rounding, largest-remainder allocation
  db.py           schema, chart of accounts, per-tenant sequences
  accounting.py   posting, invoicing, reversals, ledger/TB/P&L/BS, customer statements
  security.py     scrypt hashing, sessions, RBAC, tenant authorisation
  server.py       HTTP server + server-rendered UI (stdlib only)
  demo.py         synthetic demo books
tests/            42 unittest cases (unit + end-to-end HTTP)
scripts/          seed_demo.py
dev.ps1           test → seed → run
```

Money is always integer paise; binary floats are rejected on every financial path.
Rounding is half-up at the minor unit. Every report is computed from posted journal lines —
nothing is cached, estimated or hard-coded.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Last verified: **42 tests, OK, ~3.4 s**, Python 3.14.6, Windows.

## Documentation

| Document | Purpose |
|---|---|
| `docs/PROJECT_SPEC.md` | Governing specification (hash-verified copy) |
| `docs/SOFTWARE_AUDIT.md` | Evidence-based audit of the starting state |
| `docs/TEST_RESULTS.md` | Executed runs and evidence (`RUN-2026-10-24-02`) |
| `docs/TEST_PLAN.md` | 90 planned cases |
| `docs/BUG_REPORT.md` | Defects and known gaps |
| `docs/ARCHITECTURE.md` | Design and current implementation status |
| `docs/DATABASE_DESIGN.md` | Schema |
| `docs/SECURITY_PLAN.md` | Threat model, RBAC, security gates |
| `docs/ACCOUNTING_RULES.md` | Money, rounding, posting and report formulas |
| `docs/REQUIREMENTS_TRACEABILITY.md` | Requirement → module → test → status |
| `docs/DECISION_LOG.md` | Decisions D-000 … D-008 |
| `docs/REPORT_CATALOG.md` | 66 target reports |
| `docs/DEVELOPMENT_ROADMAP.md` | Phases and gates |
| `docs/BACKUP_AND_RECOVERY.md` | RPO/RTO and restore drill (not implemented) |

## Rules this build follows

- No Firebase, no paid APIs, no new external services.
- No real customer or bank data in demo/tests.
- No unverified claim: every "works" line above maps to a test that ran.
- Nothing is pushed to GitHub from this machine.

## Next slice (recommended order)

1. Receipts against invoices → AR ageing → customer statement with payments.
2. Purchases/AP → vendor ledger → expense categories.
3. Credit notes and reversals in the UI.
4. GST summary (GSTR-1 style) and export to CSV/PDF.
5. Backup + restore drill with a recorded verification.
6. Then multi-user admin UI, PostgreSQL, and the Next.js front end.
