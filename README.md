# ARTHIVIO — Smarter Finance. Stronger Business.

Business finance, accounting and analytics platform for Indian SMEs.

**Status: working local prototype (Build 0.2).** The sales cycle (invoice → receipt →
outstanding), the purchase cycle (bill → vendor payment → payable), credit notes, day book,
manual journals, GST summary, ageing reports, CSV exports and verified backups are implemented
through a real double-entry engine and covered by **75 automated tests that pass on this
machine** (see `docs/TEST_RESULTS.md`, run `RUN-2026-10-24-03`).

It is **not production-ready yet**: PDF/e-invoice, GSTR-1 JSON, debit notes, bank
reconciliation, multi-user admin UI and the Next.js front end are not built. Do not put real
customer data in it.

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
python -m unittest discover -s tests     # 75 tests
python scripts/seed_demo.py              # demo books (idempotent)
python -m app.server                     # http://127.0.0.1:8000
```

Demo logins (synthetic data only — change before any real use):

| Role | Email | Password |
|---|---|---|
| Owner | `owner@arthivio.test` | `ArthivioDemo!2026` |
| Admin | `admin@arthivio.test` | `ArthivioDemo!2026` |

Override the password with `ARTHIVIO_DEMO_PASSWORD`, the database path with `ARTHIVIO_DB`,
the backup folder with `ARTHIVIO_BACKUP_DIR`, and the port with `PORT`.

---

## What actually works

| Area | Behaviour | Evidence |
|---|---|---|
| Invoices | Multi-line, discounts, per-line GST, CGST/SGST vs IGST by place of supply, optional round-to-rupee, sequential numbering, idempotent creation | `TestInvoice`, `test_web.test_05` |
| Receipts | Customer receipts against an invoice (full or partial), cash/bank/UPI/cheque/card, advance receipts, allocation guards, idempotency; invoice status becomes Paid/Partial/Open | `TestReceipts`, `test_web.test_10` |
| Bills / AP | Purchase bills with input GST (CGST/SGST or IGST), inventory in at weighted-average cost, purchases for non-stock items, vendor payments, payable ageing | `TestBills`, `test_web.test_11` |
| Credit notes | Sales returns against invoice lines, revenue + GST reversal, stock returned at cost, COGS reversal, over-credit guard | `TestCreditNotes`, `test_web.test_12` |
| Posting engine | Integer-paise double entry, exact balance enforcement, per-tenant accounts, period locks, immutable entries + reversals, atomic document posting | `TestPosting`, `TestReports.test_reversal_nets_to_zero` |
| Inventory | Perpetual stock, weighted-average cost, COGS at cost, negative-stock block, service items never touch stock | `test_cogs_and_stock`, `test_purchase_at_current_cost_keeps_average`, `test_service_invoice_does_not_touch_stock` |
| Receivables / payables | Customer and vendor balances + statements, open-invoice and open-bill ageing (current / 31-60 / 61-90 / 90+), reconciled to control accounts | `TestReceipts`, `TestAgeingAndGST`, `test_customer_statement_matches_receivable_control` |
| Reports | Trial balance, general ledger with running balance, P&L, balance sheet (A = L + E), day book, GST summary with sales/purchase registers | `test_04`, `test_balance_sheet_equation`, `TestAgeingAndGST` |
| Exports | CSV for trial balance, P&L, balance sheet, ledger, day book, invoices, receipts, bills, credit notes, ageing and GST registers (UTF-8 with BOM for Excel) | `test_13_csv_exports` |
| Backups | Consistent online backup, SHA-256, integrity + foreign-key + balanced-journal + row-count verification, recorded runs, CLI restore drill | `TestBackup`, `test_15_backup_over_http`, `scripts/backup.py` |
| Security | scrypt password hashing, server sessions with idle/absolute expiry, CSRF on every POST, RBAC matrix, login lockout, audit log | `TestSecurity`, `test_06_csrf_required` |
| Tenancy | Every query is tenant-scoped; cross-tenant account, ledger, invoice, statement, receipt and export access is blocked and tested | `test_cross_tenant_account_rejected`, `test_08`, `test_foreign_invoice_rejected` |
| UI | Responsive server-rendered UI in the ARTHIVIO palette (ivory/emerald/gold), grouped navigation, no stock photos, no invented statistics | manual browser checks |

## What is not built yet (honest gaps)

- Debit notes, purchase returns, expense categories beyond simple journals
- GSTR-1/3B returns, e-invoice/IRN, e-way bills, TDS/TCS
- Bank reconciliation, cheque printing, payment reminders
- PDF invoices, Excel (xlsx) export, printing, email delivery
- Multi-user invite/role administration UI (roles exist in the data layer)
- Fixed-asset depreciation, payroll, budgets, cost centres, multi-currency
- One-click destructive restore (restore is verified but deliberately manual)
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
  accounting.py   posting, invoices, receipts, bills, credit notes, ageing, GST, reports
  security.py     scrypt hashing, sessions, RBAC, tenant authorisation
  backup.py       online backup + verification (integrity, FKs, balance, row counts)
  server.py       HTTP server + server-rendered UI (stdlib only)
  demo.py         synthetic demo books
tests/            75 unittest cases (unit + end-to-end HTTP)
scripts/          seed_demo.py, backup.py, restore_verify.py
dev.ps1           test → seed → run
```

Money is always integer paise; binary floats are rejected on every financial path.
Rounding is half-up at the minor unit. Every report is computed from posted journal lines —
nothing is cached, estimated or hard-coded. Composite postings (invoice, bill, receipt,
credit note, reversal) run in a single transaction, so a document can never exist without its
balanced journal or vice versa.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Last verified: **75 tests, OK, ~9 s**, Python 3.14.6, Windows.

Backup drill:

```powershell
python scripts/backup.py
python scripts/restore_verify.py --backup backups\<file>.db
```

## Documentation

| Document | Purpose |
|---|---|
| `docs/PROJECT_SPEC.md` | Governing specification (hash-verified copy) |
| `docs/SOFTWARE_AUDIT.md` | Evidence-based audit of the starting state |
| `docs/TEST_RESULTS.md` | Executed runs and evidence (`RUN-2026-10-24-03`) |
| `docs/TEST_PLAN.md` | 90 planned cases |
| `docs/BUG_REPORT.md` | Defects and known gaps |
| `docs/ARCHITECTURE.md` | Design and current implementation status |
| `docs/DATABASE_DESIGN.md` | Schema |
| `docs/SECURITY_PLAN.md` | Threat model, RBAC, security gates |
| `docs/ACCOUNTING_RULES.md` | Money, rounding, posting and report formulas |
| `docs/REQUIREMENTS_TRACEABILITY.md` | Requirement → module → test → status |
| `docs/DECISION_LOG.md` | Decisions D-000 … D-009 |
| `docs/REPORT_CATALOG.md` | 66 target reports |
| `docs/DEVELOPMENT_ROADMAP.md` | Phases and gates |
| `docs/BACKUP_AND_RECOVERY.md` | RPO/RTO and restore drill |

## Rules this build follows

- No Firebase, no paid APIs, no new external services.
- No real customer or bank data in demo/tests.
- No unverified claim: every "works" line above maps to a test that ran.
- Nothing is pushed to GitHub from this machine.

## Next slice (recommended order)

1. PDF invoice printing and a shareable customer statement.
2. GSTR-1 style JSON/CSV export and purchase register reconciliation.
3. Debit notes, expense categories and a simple cash/bank book.
4. Multi-user invitation and role administration UI.
5. Bank reconciliation import (CSV) with a matching workflow.
6. Then PostgreSQL, concurrency hardening and the Next.js front end.
