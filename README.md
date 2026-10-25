# ARTHIVIO — Smarter Finance. Stronger Business.

Business finance, accounting and analytics platform for Indian SMEs.

**Status: working local prototype (Build 0.7).** The sales cycle (invoice → receipt →
outstanding), the purchase cycle (bill → vendor payment → payable), credit notes, debit notes
(purchase returns), day book, manual journals, bank reconciliation, GST summary, GSTR-1 working
export, a **GSTR-3B working summary with GSTR-1/ledger reconciliation checks**, a **GSTR-2B
purchase reconciliation and ITC review working aid**, **team invitations and role administration**,
and **shareable customer/vendor statement print links** are implemented through a real double-entry
engine and covered by **162 automated tests that pass on this machine** (see
`docs/TEST_RESULTS.md`, run `RUN-2026-10-25-02`).

It is **not production-ready yet**: GST portal upload, e-invoice/IRN, e-way bills, TDS/TCS,
email delivery, ownership transfer, PostgreSQL and the Next.js front end are not built. GSTR-1,
GSTR-3B and GSTR-2B outputs are preparation aids, not filed returns. ITC review states are internal
annotations and never claim or post ITC. Do not put real customer data in it.

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
python -m unittest discover -s tests     # 162 tests
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
| Debit notes | Purchase returns against bill lines, purchase value + input GST reversal, stock out at bill cost with average-cost restatement, payable reduction, over-debit and stock guards, vendor credit after payment | `TestDebitNotes`, `test_web.test_19` |
| Bank reconciliation | CSV import (Date/Description/Reference/Debit/Credit or Amount+Dr/Cr, multiple date formats), SHA-256 dedup, exact-amount suggestions within ±7 days, auto-match unambiguous, manual match/unmatch, statement-vs-ledger difference | `TestCsvParsing`, `TestImportAndMatch`, `test_web.test_20` |
| Posting engine | Integer-paise double entry, exact balance enforcement, per-tenant accounts, period locks, immutable entries + reversals, atomic document posting | `TestPosting`, `TestReports.test_reversal_nets_to_zero` |
| Inventory | Perpetual stock, weighted-average cost, COGS at cost, negative-stock block, service items never touch stock | `test_cogs_and_stock`, `test_purchase_at_current_cost_keeps_average`, `test_service_invoice_does_not_touch_stock` |
| Receivables / payables | Customer and vendor balances + statements, open-invoice and open-bill ageing (current / 31-60 / 61-90 / 90+), reconciled to control accounts | `TestReceipts`, `TestAgeingAndGST`, `test_customer_statement_matches_receivable_control` |
| Reports | Trial balance, general ledger with running balance, P&L, balance sheet (A = L + E), day book, GST summary with sales/purchase registers | `test_04`, `test_balance_sheet_equation`, `TestAgeingAndGST` |
| Exports | CSV for trial balance, P&L, balance sheet, ledger, day book, invoices, receipts, bills, credit notes, debit notes, bank statement, ageing and GST registers (UTF-8 with BOM for Excel); GSTR-1 style CSV/JSON with B2B, B2C small, HSN and credit-note sections; GSTR-3B working CSV; GSTR-2B reconciliation and ITC review CSV | `test_13_csv_exports`, `test_17`, `test_18`, `test_19`, `test_20`, `test_21`, `test_24` |
| GSTR-3B working | Month-wise 3.1 outward supplies, 4 eligible ITC and head-wise payment view; output net of credit notes, ITC net of debit notes; six reconciliation checks against GSTR-1 and the tax ledger; negative-head carry-forward shown explicitly | `tests/test_gstr3b.py` (8), `test_21_gstr3b_page_and_csv`, browser check `RUN-2026-10-24-06` |
| GSTR-2B working | Month-scoped CSV import, SHA-256 duplicate detection, latest active import supersedes the prior one, supplier GSTIN + normalised invoice matching, amount differences reported but never corrected, missing-in-books and missing-in-2B lists, per-line ITC review (open / supplier follow-up / ITC hold / accepted) with notes and audit trail, **GSTR-3B eligible-ITC vs GSTR-2B comparison**, import history and CSV export; nothing is auto-posted and review states never change the books | `tests/test_gstr2b.py` (17), `test_24_gstr2b_import_and_export`, browser check `RUN-2026-10-25-02` |
| Team access | One-time invite links (SHA-256 token hashes, 7-day expiry), new-user password setup or existing-user current-password join, role changes, suspend/reactivate/remove, immediate session revocation, protected owner role, audit trail, business switcher | `tests/test_team_sharing.py` (11), `test_22_team_invite_accept_and_role_change`, `test_25_business_switcher_checks_membership` |
| Shareable statements | Customer/vendor statement can be shared as a read-only, no-login print link scoped to business, party and date range; 7/30/90-day expiry, revoke, view count, `noindex` and `no-store` headers, A4 Print / Save as PDF | `tests/test_team_sharing.py` (4 sharing tests), `test_23_shareable_statement_and_revoke`, browser check `RUN-2026-10-25-01` |
| Tax invoice | A4 print view with seller/buyer GSTIN, HSN/SAC, CGST/SGST vs IGST, amount in words, bank details and terms; browser Print / Save as PDF | `test_16_settings_and_print_invoice` |
| Business settings | Owner-editable legal name, GSTIN, GST state, address, contact, bank details and invoice terms; validated and audited | `test_16_settings_and_print_invoice`, `MigrationTest` |
| Backups | Consistent online backup, SHA-256, integrity + foreign-key + balanced-journal + row-count verification, recorded runs, CLI restore drill | `TestBackup`, `test_15_backup_over_http`, `scripts/backup.py` |
| Security | scrypt password hashing, server sessions with idle/absolute expiry, CSRF on every POST, RBAC matrix, login lockout, audit log | `TestSecurity`, `test_06_csrf_required` |
| Tenancy | Every query is tenant-scoped; cross-tenant account, ledger, invoice, statement, receipt and export access is blocked and tested | `test_cross_tenant_account_rejected`, `test_08`, `test_foreign_invoice_rejected` |
| UI | Responsive server-rendered UI in the ARTHIVIO palette (ivory/emerald/gold), grouped navigation, no stock photos, no invented statistics | manual browser checks |

## What is not built yet (honest gaps)

- GST portal upload, official GSTR-2B/2A formats, e-invoice/IRN, e-way bills, TDS/TCS; GSTR-1/3B/2B are working preparation aids only, and ITC review states do not claim or reverse ITC
- Auto-posting journal entries from unmatched bank lines (bank charges/interest), cheque printing, payment reminders
- Excel (xlsx) export, email delivery of invites/statements, e-invoice QR
- Ownership transfer, per-page permission editing, SSO; invite links are copied and sent manually
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
  accounting.py   posting, invoices, receipts, bills, credit notes, debit notes, ageing, GST, reports
  bank.py         bank statement CSV parsing, import dedup, matching, reconciliation summary
  gstr2b.py       GSTR-2B working CSV parsing, import/supersede, invoice matching, ITC review, 3B comparison
  sharing.py      statement share tokens, expiry/revocation, public statement resolution
  security.py     scrypt hashing, sessions, RBAC, tenant authorisation, invites and roles
  backup.py       online backup + verification (integrity, FKs, balance, row counts)
  server.py       HTTP server + server-rendered UI (stdlib only)
  demo.py         synthetic demo books
tests/            162 unittest cases (unit + end-to-end HTTP)
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

Last verified: **162 tests, OK, ~12 s**, Python 3.14.6, Windows.

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
| `docs/TEST_RESULTS.md` | Executed runs and evidence (`RUN-2026-10-25-02`) |
| `docs/TEST_PLAN.md` | 162 executed application cases |
| `docs/BUG_REPORT.md` | Defects and known gaps |
| `docs/ARCHITECTURE.md` | Design and current implementation status |
| `docs/DATABASE_DESIGN.md` | Schema |
| `docs/SECURITY_PLAN.md` | Threat model, RBAC, security gates |
| `docs/ACCOUNTING_RULES.md` | Money, rounding, posting and report formulas |
| `docs/REQUIREMENTS_TRACEABILITY.md` | Requirement → module → test → status |
| `docs/DECISION_LOG.md` | Decisions D-000 … D-020 |
| `docs/REPORT_CATALOG.md` | 66 target reports |
| `docs/DEVELOPMENT_ROADMAP.md` | Phases and gates |
| `docs/BACKUP_AND_RECOVERY.md` | RPO/RTO and restore drill |

## Rules this build follows

- No Firebase, no paid APIs, no new external services.
- No real customer or bank data in demo/tests.
- No unverified claim: every "works" line above maps to a test that ran.
- Nothing is pushed to GitHub from this machine.

## Next slice (recommended order)

1. Partial/one-to-many bank matching; auto-post bank charges and interest.
2. GSTR-2B exception ageing and supplier-wise follow-up summary; period comparison trends.
3. Statement/invite email delivery and ownership transfer, with an explicit permission editor.
4. Then PostgreSQL, concurrency hardening and the Next.js front end.
