# ARTHIVIO — Smarter Finance. Stronger Business.

Business finance, accounting and analytics platform for Indian SMEs.

**Status: working local prototype (Build 0.17).** The sales cycle (invoice → receipt →
outstanding), the purchase cycle (bill → vendor payment → payable), credit notes, debit notes
(purchase returns), day book, manual journals, bank reconciliation, cash book, bank book, GST
summary, GSTR-1 working export, a **GSTR-3B working summary with GSTR-1/ledger reconciliation
checks**, a **GSTR-2B purchase reconciliation and ITC review working aid**, **team invitations and
role administration**, **shareable customer/vendor statement print links**, a **reference-matched
public product home page with an opt-in, loopback-only no-signin demo**, and a **Tally-style grouped
top menu with dropdowns** are implemented through a real double-entry engine. Build 0.10 adds a
**Ledger hub listing every account with balances and account creation**, separate
**Cash Entry / Bank Entry / Journal Entry** pages, **permission-controlled journal reversal**,
**multiple bank accounts with full details, each with its own ledger, bank book and reconciliation**,
**opening balances posted as balanced journals against Opening Balance Equity**, and an
**Account 360 profile captured when a ledger is created** (classification, company/contact,
GSTIN/PAN/CIN, credit terms, bank, loan and linked customer/vendor sub-ledger). Product-wise
margin, MRP, HSN/SAC and GST are captured in the item master. Account creation uses one
**account type / group** selector covering cash, bank, debtors, creditors, inventory, fixed assets,
loans, tax, suspense, capital, drawings, retained earnings, P&L, purchase, sales, depreciation and
other business classifications. Build 0.11 adds **bulk opening-balance import from CSV** with a
validate-before-post preview, all-or-nothing posting, per-row opening journals and an audit record.
It also adds **four user-selectable light palettes** under **Settings → Appearance** — Ocean Blue,
Emerald Green, Royal Violet and Warm Sunset — with a white topbar, neutral charcoal text and no
navy app chrome. The public landing page keeps a dark hero that is now slightly lighter, with a
page-level colour picker for Ocean, Emerald, Violet and Sunset; it never becomes a light page.
Build 0.11 also adds **account archive and merge**: a zero-balance ledger can be archived with a
reason, or merged into another same-type ledger through one balanced reclassification journal while
the source is archived and every posted line stays in history. The analytics foundation now has
**read-only semantic views, a 19-metric registry, a session-authenticated JSON API and an Analytics
Overview screen** with actual-only monthly revenue/expense bars, expense composition, top customers
and vendors, trial-balance/balance-sheet checks and freshness. Build 0.12 adds the first real
**Excel layer**: a 20-sheet `.xlsx` actuals workbook with KPI/statements/ageing/GST/inventory/journal
sheets and native Excel charts, plus server-side `.xlsx` import for opening balances, bank statements
and GSTR-2B. It also adds a **static Power BI import pack**, a locally vendored **ECharts** interactive
monthly and expense-composition charts, and a **grounded deterministic insight layer** with an AI Insights page, JSON endpoint
and workbook sheet. No generative AI provider is configured yet, so the insight engine is explicitly
rule-based and cites every metric; no forecast is mixed into actuals. Build 0.13 adds a **Report
Library** and nine management reports: **R-104 Cash Flow** (direct movement plus indirect
reconciliation), **R-108 Financial Ratios**, **R-109 Period-over-Period Comparison**, **R-202
Reversal Register**, **R-203 Account Activity**, **R-301 Sales Register**, **R-401 Purchase
Register**, **R-903 Expense Breakdown** and **R-905 Working Capital Cycle**. Build 0.13 took
coverage to **28 of 66**. Build 0.14 adds **first-run owner setup** for a clean
installation (the setup page closes permanently after the first owner is created) and a
**self-contained Windows offline package** with an embedded Python runtime, local SQLite, verified
external-drive backup and optional login autostart. Build 0.15 adds **editable manual entries**:
cash, bank and journal vouchers can be corrected from the entry page, ledger, day book, cash book or
bank book. Saving an edit posts a reversal plus a corrected replacement in one transaction, requires
a reason and keeps both versions in the audit trail. It also adds **Start fresh books** under
Businesses, so an owner can create a new business with the standard chart of accounts and zero
entries and test new ledgers without touching the demo. Build 0.16 adds ten more working reports:
**R-110 Trial Balance Exceptions**, **R-302 Sales Summary**, **R-303 Top Customers**, **R-306 Sales
Returns**, **R-307 Product-wise Sales**, **R-309 Discount Analysis**, **R-404 Top Suppliers**,
**R-406 Purchase Returns**, **R-501 Stock Summary** and **R-706 Credit Limit Utilisation**, with
CSV exports. Build 0.17 adds eighteen more working reports: **R-107 Opening vs Closing**, **R-205
Locked Period Register**, **R-206 Rule Version Usage**, **R-308 Salesperson Performance**, **R-405 Price Variance**, **R-502
Stock Movement History**, **R-503 Inventory Valuation**, **R-504 Reorder / Shortage**, **R-505
Dead / Slow Stock**, **R-507 Inventory to GL Reconciliation**, **R-704 Receivables Risk**, **R-705
Cash Flow Forecast**, **R-807 Tax Ledger**, **R-904 KPI Dashboard Pack**, **R-1001 Trend
Explanation**, **R-1002 Revenue Forecast**, **R-1003 Anomaly Digest** and **R-901 Budget vs
Actual**, with CSV exports.
Coverage is now **56 of 66** working reports. Saved dashboards, EN/HI labels, Power BI Service
refresh/RLS and a generative AI provider remain planned. Covered by **295 automated tests that pass
on this machine** (see `docs/TEST_RESULTS.md`, run `RUN-2026-11-06-01`).

It is **not production-ready yet**: GST portal upload, e-invoice/IRN, e-way bills, TDS/TCS,
email delivery, ownership transfer, PostgreSQL and the Next.js front end are not built. GSTR-1,
GSTR-3B and GSTR-2B outputs are preparation aids, not filed returns. ITC review states are internal
annotations and never claim or post ITC. Do not put real customer data in it.

---

## Quick start

Requirements: Python 3.12+ (verified on 3.14.6). The accounting core uses only the standard
library and SQLite; the approved Excel layer needs `openpyxl`. No Node or database server is needed.

```powershell
cd "D:\financial business account data analysis"
.\dev.ps1                 # runs tests, seeds demo data, starts http://127.0.0.1:8000
.\dev.ps1 -Demo          # same, plus loopback-only no-signin demo at /demo
```

Or step by step:

```powershell
python -m pip install -r requirements.txt  # approved openpyxl dependency
python -m unittest discover -s tests       # 295 tests
python -m app.server                       # http://127.0.0.1:8000
```

On a clean database, `/login` opens the first-run setup page. Create the owner account there;
the page closes permanently after the first owner exists. The demo seeder is optional:

```powershell
python scripts/seed_demo.py                # demo books (idempotent)
```

To open the no-signin demo without the runner:

```powershell
$env:ARTHIVIO_DEMO_AUTOLOGIN = "1"
python -m app.server                     # open http://127.0.0.1:8000/demo
```

The demo route refuses non-loopback requests, creates normal server sessions, and records
`auth.demo_login` in the audit trail. It is a local convenience only; disable the flag before
exposing the server on a network.

Demo logins (synthetic data only — change before any real use):

| Role | Email | Password |
|---|---|---|
| Owner | `owner@arthivio.test` | `ArthivioDemo!2026` |
| Admin | `admin@arthivio.test` | `ArthivioDemo!2026` |

Override the password with `ARTHIVIO_DEMO_PASSWORD`, the database path with `ARTHIVIO_DB`,
the backup folder with `ARTHIVIO_BACKUP_DIR`, and the port with `PORT`.

To open the workspace on a phone on the **same trusted Wi-Fi/LAN**:

```powershell
$env:ARTHIVIO_HOST = "0.0.0.0"
python -m app.server
```

Then open `http://<this-PC-LAN-IP>:8000/login` on the phone. Windows Firewall may need an inbound
allow rule for TCP 8000; do not expose this local demo server to an untrusted network. The default
binding stays on `127.0.0.1` when `ARTHIVIO_HOST` is not set.

---

## Windows offline package

Build a self-contained folder that needs no Python installation and no internet:

```powershell
.\.venv\Scripts\python.exe scripts\build_windows_portable.py --zip
```

The result is `dist\ARTHIVIO-Offline\` and `dist\ARTHIVIO-Offline-0.17.zip`. It contains the
official Python 3.14.6 embeddable runtime, `openpyxl`, the app, and Windows launchers:

- `Start ARTHIVIO.bat` starts the local server and opens the browser.
- `Backup ARTHIVIO.bat` creates a verified backup and copies it to an external-drive folder.
- `Install autostart.bat` adds a desktop shortcut and starts ARTHIVIO minimized at Windows login.
- `Remove autostart.bat` removes those shortcuts.

The first run opens `/setup` and creates the owner login. Data stays in the package's `data`
folder; logs are in `logs`; local backups are in `backups`. See `docs/OFFLINE_EDITION.md` for the
full operating and restore procedure. The package is still a single-user local build, not a
permanent hosted service and not a substitute for an independent accounting review.

---

## Public demo deployment

The repo includes a `Dockerfile` and `render.yaml` for a free Render web service. After the owner
signs in to Render with GitHub, the Blueprint creates a stable public URL:

[Deploy the demo on Render](https://render.com/deploy?repo=https://github.com/ganeshanumerologist-ai/financial-business-account-analysis)

Free Render services sleep after inactivity and use an ephemeral filesystem, so the synthetic demo
books are reseeded after a restart. Do not enter real financial data. Persistent storage requires a
paid disk or a VPS; see `docs/DEPLOYMENT.md`.

## What actually works

| Area | Behaviour | Evidence |
|---|---|---|
| Invoices | Multi-line, discounts, per-line GST, CGST/SGST vs IGST by place of supply, optional round-to-rupee, sequential numbering, idempotent creation | `TestInvoice`, `test_web.test_05` |
| Receipts | Customer receipts against an invoice (full or partial), cash/bank/UPI/cheque/card, advance receipts, allocation guards, idempotency; invoice status becomes Paid/Partial/Open | `TestReceipts`, `test_web.test_10` |
| Bills / AP | Purchase bills with input GST (CGST/SGST or IGST), inventory in at weighted-average cost, purchases for non-stock items, vendor payments, payable ageing | `TestBills`, `test_web.test_11` |
| Credit notes | Sales returns against invoice lines, revenue + GST reversal, stock returned at cost, COGS reversal, over-credit guard | `TestCreditNotes`, `test_web.test_12` |
| Debit notes | Purchase returns against bill lines, purchase value + input GST reversal, stock out at bill cost with average-cost restatement, payable reduction, over-debit and stock guards, vendor credit after payment | `TestDebitNotes`, `test_web.test_19` |
| Bank reconciliation | CSV or server-side `.xlsx` import (Date/Description/Reference/Debit/Credit or Amount+Dr/Cr, multiple date formats), SHA-256 dedup, exact-amount suggestions within ±7 days, auto-match unambiguous, manual match/unmatch, statement-vs-ledger difference; selectable per bank account | `TestCsvParsing`, `TestImportAndMatch`, `test_web.test_20`, `test_web.test_29` |
| Bank accounts | Every bank account has its own asset ledger, full bank details (bank, account number, IFSC, branch, holder), bank book and reconciliation; the legacy 1010 account keeps using Business Settings | `TestBankAccounts`, `test_web.test_29` |
| Posting engine | Integer-paise double entry, exact balance enforcement, per-tenant accounts, period locks, immutable entries + reversals, atomic document posting | `TestPosting`, `TestReports.test_reversal_nets_to_zero` |
| Ledger hub | All accounts grouped by type with balances; click any account for its full ledger; add a new ledger account inline; separate Cash/Bank/Journal entry actions; **Edit** a manual cash/bank/journal entry (reverse + corrected repost in one transaction), or reverse it with a required reason; every correction is audited | `TestAccountManagement`, `test_web.test_28`, `test_web.test_30`, `test_web.test_48` |
| Opening balances | Set on a new or existing account from its ledger; posts a balanced Dr/Cr journal against an automatically created Opening Balance Equity account; date must be on or before the first posted activity; one posted opening per account; replacement requires reversal; audited | `TestOpeningBalance`, `test_web.test_31` |
| Bulk opening balances | `/ledger/opening-balances` previews and validates a CSV or server-side `.xlsx` file, rejects duplicate/missing accounts, existing openings, locked periods and bad dates, then posts every row as its own opening journal in one all-or-nothing transaction; downloadable template and `opening_balance.bulk_import` audit | `TestOpeningImport` (8), `test_web.test_36` |
| Account 360 | One creation flow captures account group/classification, company/legal name, contact, address, GSTIN, PAN, CIN, organisation/industry, credit days and limit, bank details, loan lender/account/sanction/maturity/interest/tenure/EMI/security and notes; a single type/group selector covers cash, bank, debtors, creditors, inventory, fixed assets, loans, tax, suspense, capital, drawings, retained earnings, P&L, purchase, sales, depreciation and other groups; customer/vendor groups create a linked sub-ledger used by invoices, bills, receipts and payments; profile edits never change posted amounts and are audited | `TestAccountProfile` (7), `test_web.test_32`, `test_web.test_33`, `test_web.test_35` |
| Account archive / merge | Archive a zero-balance ordinary ledger with a reason, or merge it into another active ledger of the same type; merge posts one balanced reclassification journal for the net balance, archives the source and keeps all history; same-party, bank-to-bank and system-control guard rails; restore, item/party repointing and `account.archive`/`account.merge`/`account.restore` audit | `tests/test_account_archive.py` (6), `test_web.test_39` |
| Product master | Item-wise category, brand, barcode, HSN/SAC, MRP, cost, margin, GST rate, sale price, opening stock, stock-tracking and default sales ledger; blank sale price is computed from cost + margin; MRP below sale price is rejected | `test_web.test_34`, `test_parse_percent_to_basis_points` |
| Entry pages | Separate `/entries/cash`, `/entries/bank` and `/entries/journal` pages; cash and bank accounts preselected, balanced multi-line posting, redirect to the affected ledger; a recent-entries table gives every manual entry an **Edit** and **Reverse** action; Edit opens the original lines pre-filled and saves a reversal plus corrected repost atomically | `test_web.test_30`, `test_web.test_48` |
| Inventory | Perpetual stock, weighted-average cost, COGS at cost, negative-stock block, service items never touch stock | `test_cogs_and_stock`, `test_purchase_at_current_cost_keeps_average`, `test_service_invoice_does_not_touch_stock` |
| Receivables / payables | Customer and vendor balances + statements, open-invoice and open-bill ageing (current / 31-60 / 61-90 / 90+), reconciled to control accounts | `TestReceipts`, `TestAgeingAndGST`, `test_customer_statement_matches_receivable_control` |
| Reports | One Reports menu with trial balance, P&L, balance sheet (A = L + E), receivable/payable ageing and GST working papers; general ledger with running balance, cash book, bank book and day book are derived views with **Edit/Reverse** actions for manual entries; nothing is overwritten | `test_04`, `test_balance_sheet_equation`, `TestAgeingAndGST`, `test_14_new_pages_render`, `test_27_grouped_dropdown_navigation`, `test_web.test_48` |
| Report Library and management reports | `/reports/library` lists all 66 catalogued reports with source/formula and honest working/partial/planned state; thirty-seven deterministic management reports: cash flow with indirect bridge, financial ratios, period comparison, reversal register, account activity, sales register, purchase register, expense breakdown, working-capital cycle, trial balance exceptions, sales summary, top customers, product-wise sales, discount analysis, sales returns, top suppliers, purchase returns, stock summary and credit-limit utilisation, opening vs closing, locked periods, rule version usage, salesperson performance, price variance, stock movements, inventory valuation, reorder/shortage, dead/slow stock, inventory-to-GL reconciliation, receivables risk, budget vs actual, cash flow forecast, tax ledger, KPI dashboard pack, trend explanation, revenue forecast and anomaly digest; 56 of 66 working; CSV exports for every new report | `tests/test_reports.py` (36), `test_web.test_46`, `test_web.test_49`, `RUN-2026-11-04-01`, `RUN-2026-11-05-02`, `RUN-2026-11-05-03`, `RUN-2026-11-06-01` |
| Analytics foundation | Read-only `v_analytics_journal` / `v_analytics_monthly` views; 19-metric actual-only registry; `/api/v1/analytics/catalog`, `/api/v1/analytics/overview` and `/api/v1/analytics/insights` (session + `report.view`, tenant-scoped, `no-store`); `/reports/analytics` shows KPI cards, monthly bars, expense composition, top customers/vendors, checks/freshness and a locally vendored ECharts interactive view; no forecast or authoritative total is invented | `tests/test_analytics.py` (6), `tests/test_insights.py` (3), `test_web.test_40`, `test_web.test_43`, `test_web.test_44`, `RUN-2026-10-28-01` |
| Excel workbook export | Real `.xlsx` via approved `openpyxl`: `/export/workbook.xlsx` builds 20 sheets (cover, read-me, data dictionary, KPIs, monthly, P&L, balance sheet, trial balance, expense, top parties, AR/AP ageing, cash/bank, inventory, GST working/sales/purchases, journal, AI Insights) with native Excel charts; amounts show INR while the exact integer-paise source stays beside each KPI; permission `report.export`, `no-store` | `tests/test_excel.py` (6), `test_web.test_41`, `RUN-2026-10-28-01` |
| Excel import | Real `.xlsx` upload for bulk opening balances, bank statements and GSTR-2B; server-side `openpyxl` reads the first worksheet (or named sheet), converts dates/numbers to neutral CSV, then the existing validators still preview and post atomically; 8 MB/50,000-row guard, formula cells use cached values only, malformed files fail visibly | `tests/test_xlsx_import.py` (5), `test_web.test_45`, `RUN-2026-10-28-01` |
| Power BI import pack | `/export/powerbi.zip` packages the analytics snapshot, metric catalog, journal/monthly facts, account/party dimensions, a Power Query starter and a manifest with SHA-256 hashes; money stays integer paise; explicitly a static import pack, not a `.pbix`, Service dataset, RLS model or scheduled refresh | `tests/test_bi.py` (4), `test_web.test_42`, `RUN-2026-10-28-01` |
| Grounded insights | Deterministic rules over the actuals contract: margin, largest expense, overdue share, GST working amount, ledger checks, open documents and freshness; every observation has a written basis, metric keys, drill-down and source; `/reports/analytics` AI Insights card and `/api/v1/analytics/insights`; no external model, no forecast, empty periods say "not generated" | `tests/test_insights.py` (3), `test_web.test_44`, `RUN-2026-10-28-01` |
| Exports | CSV for trial balance, P&L, balance sheet, ledger, day book, invoices, receipts, bills, credit notes, debit notes, bank statement, ageing and GST registers (UTF-8 with BOM); GSTR-1 style CSV/JSON with B2B, B2C small, HSN and credit-note sections; GSTR-3B working CSV; GSTR-2B reconciliation and ITC review CSV; Build 0.13 cash-flow, sales-register, purchase-register and expense-breakdown CSV; Build 0.16 sales-summary, top-customers, product-sales, discounts, sales-returns, top-suppliers, purchase-returns, stock-summary, credit-limits, trial-balance-exceptions, opening-closing, locked-periods, salesperson, price-variance, stock-movements, inventory-valuation, reorder, dead-stock, inventory-gl and receivables-risk CSV; real `.xlsx` actuals workbook and static Power BI ZIP | `test_13_csv_exports`, `test_17`, `test_18`, `test_19`, `test_20`, `test_21`, `test_24`, `tests/test_excel.py`, `tests/test_bi.py`, `test_web.test_41`, `test_web.test_42`, `test_web.test_46` |
| GSTR-3B working | Month-wise 3.1 outward supplies, 4 eligible ITC and head-wise payment view; output net of credit notes, ITC net of debit notes; six reconciliation checks against GSTR-1 and the tax ledger; negative-head carry-forward shown explicitly | `tests/test_gstr3b.py` (8), `test_21_gstr3b_page_and_csv`, browser check `RUN-2026-10-24-06` |
| GSTR-2B working | Month-scoped CSV or server-side `.xlsx` import, SHA-256 duplicate detection, latest active import supersedes the prior one, supplier GSTIN + normalised invoice matching, amount differences reported but never corrected, missing-in-books and missing-in-2B lists, per-line ITC review (open / supplier follow-up / ITC hold / accepted) with notes and audit trail, **GSTR-3B eligible-ITC vs GSTR-2B comparison**, import history and CSV export; nothing is auto-posted and review states never change the books | `tests/test_gstr2b.py` (17), `test_24_gstr2b_import_and_export`, browser check `RUN-2026-10-25-02` |
| Fresh business / test books | `/businesses` now has a **Start fresh books** form for owners: creates a separate tenant with the standard chart of accounts and zero entries, makes the creator its owner, switches the session to it, and lands on an empty ledger with a notice; use it to test new ledgers and entries without touching demo data | `TestSecurity.test_create_business_is_empty_and_makes_creator_owner`, `test_web.test_48` |
| Team access | One-time invite links (SHA-256 token hashes, 7-day expiry), new-user password setup or existing-user current-password join, role changes, suspend/reactivate/remove, immediate session revocation, protected owner role, audit trail, business switcher | `tests/test_team_sharing.py` (11), `test_22_team_invite_accept_and_role_change`, `test_25_business_switcher_checks_membership` |
| Shareable statements | Customer/vendor statement can be shared as a read-only, no-login print link scoped to business, party and date range; 7/30/90-day expiry, revoke, view count, `noindex` and `no-store` headers, A4 Print / Save as PDF | `tests/test_team_sharing.py` (4 sharing tests), `test_23_shareable_statement_and_revoke`, browser check `RUN-2026-10-25-01` |
| Tax invoice | A4 print view with seller/buyer GSTIN, HSN/SAC, CGST/SGST vs IGST, amount in words, bank details and terms; browser Print / Save as PDF | `test_16_settings_and_print_invoice` |
| Business settings | Owner-editable legal name, GSTIN, GST state, address, contact, bank details and invoice terms; validated and audited | `test_16_settings_and_print_invoice`, `MigrationTest` |
| Backups | Consistent online backup, SHA-256, integrity + foreign-key + balanced-journal + row-count verification, recorded runs, CLI restore drill | `TestBackup`, `test_15_backup_over_http`, `scripts/backup.py` |
| Diagnostics | `/system-check` read-only page for SQLite quick check, foreign keys, journal balance, latest backup, disk space and recent log; unhandled request errors return a friendly 500 page with an `ERR-XXXXXXXXXX` ID and `X-Error-ID` header, matched to `logs/arthivio.log` | `app/diagnostics.py`, `test_47_system_check_and_traceable_error_page`, `RUN-2026-11-04-02` |
| Security | scrypt password hashing, server sessions with idle/absolute expiry, CSRF on every POST, RBAC matrix, login lockout, audit log | `TestSecurity`, `test_06_csrf_required` |
| Tenancy | Every query is tenant-scoped; cross-tenant account, ledger, invoice, statement, receipt and export access is blocked and tested | `test_cross_tenant_account_rejected`, `test_08`, `test_foreign_invoice_rejected` |
| UI | Responsive server-rendered UI: Tally-style grouped top menu with accessible dropdowns (Transactions, Entries, Books, Reports, Masters, Settings), ledger hub with account sidebar, white topbar with neutral charcoal ink, four saved light palettes (Ocean, Emerald, Violet, Sunset) chosen per user under Settings → Appearance, and a public product home page with inline SVG cityscape, a slightly lighter dark hero, a page-level four-colour picker and a dashboard preview; reference metrics are visibly labelled illustrative; no stock photos | `test_27_grouped_dropdown_navigation`, `test_28`, `test_29`, `test_30`, `test_37`, `test_38`, manual browser checks at desktop width; earlier `/home` Lighthouse 100 / 100 / 100 baseline not re-run after the landing picker |
| Local demo mode | Opt-in `/demo` route (`ARTHIVIO_DEMO_AUTOLOGIN=1`), loopback-only, auto-login as the demo owner, normal session + audit event; 404 when disabled or non-loopback | `test_26_local_demo_autologin_is_opt_in`, `test_00_public_landing_page` |

## What is not built yet (honest gaps)

- GST portal upload, official GSTR-2B/2A formats, e-invoice/IRN, e-way bills, TDS/TCS; GSTR-1/3B/2B are working preparation aids only, and ITC review states do not claim or reverse ITC
- The full analytics product: 66-report completion, saved dashboards, EN/HI labels, drill-down everywhere and the ~150-template expansion (the analytics pilot and 20-sheet workbook are not a substitute for all 66 reports)
- Auto-posting journal entries from unmatched bank lines (bank charges/interest), cheque printing, payment reminders
- A generative AI provider, AI-generated narratives/forecasts and AI workbook authoring; the current insight layer is deterministic and grounded only
- Power BI Service dataset, scheduled refresh, row-level security and a token-authenticated public BI API; the current pack is a static desktop import
- Email delivery of invites/statements, e-invoice QR
- Ownership transfer, per-page permission editing, SSO; invite links are copied and sent manually
- Fixed-asset depreciation, payroll, budgets, cost centres, multi-currency
- One-click destructive restore (restore is verified but deliberately manual)
- PostgreSQL deployment path, Next.js front end, hosting
- Load, concurrency and penetration testing

## Architecture

Standard-library Python 3 + SQLite (WAL) for the accounting core, plus one approved optional
package (`openpyxl`) for real `.xlsx` workbooks. ECharts is vendored locally as a 1.03 MB JS asset;
there is no runtime CDN call. The accounting core still runs without Node, a database server or a
paid service.

```
app/
  money.py        integer paise, half-up rounding, largest-remainder allocation
  db.py           schema, chart of accounts, per-tenant sequences
  accounting.py   posting, invoices, receipts, bills, credit notes, debit notes, ageing, GST, reports
  analytics.py    read-only semantic views, metric registry, actuals snapshot and JSON API payloads
  insights.py     deterministic grounded observations with metric keys, basis and drill-down
  excel.py        real .xlsx actuals workbook (20 sheets, native charts, KPI paise trace)
  xlsx_import.py  safe .xlsx -> CSV conversion for the existing import validators
  bi.py           static Power BI ZIP: facts, dimensions, catalog, manifest and Power Query starter
  static/         locally vendored ECharts 5.5.1 (Apache-2.0) and notice
  bank.py         bank statement CSV/Excel parsing, import dedup, matching, reconciliation summary
  gstr2b.py       GSTR-2B working CSV/.xlsx parsing, import/supersede, invoice matching, ITC review, 3B comparison
  sharing.py      statement share tokens, expiry/revocation, public statement resolution
  security.py     scrypt hashing, sessions, RBAC, tenant authorisation, invites and roles
  backup.py       online backup + verification (integrity, FKs, balance, row counts)
  server.py       HTTP server + server-rendered UI (stdlib only)
  demo.py         synthetic demo books
tests/            257 unittest cases (unit + end-to-end HTTP)
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

Last verified: **295 tests, OK, 28.976 s**, Python 3.14.6, Windows.

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
| `docs/TEST_RESULTS.md` | Executed runs and evidence (`RUN-2026-11-04-02`) |
| `docs/TESTING_GUIDE.md` | A-to-Z single-user trial checklist and bug-report format |
| `docs/TEST_PLAN.md` | 256 executed application cases |
| `docs/BUG_REPORT.md` | Defects and known gaps |
| `docs/ARCHITECTURE.md` | Design and current implementation status |
| `docs/DATABASE_DESIGN.md` | Schema |
| `docs/SECURITY_PLAN.md` | Threat model, RBAC, security gates |
| `docs/ACCOUNTING_RULES.md` | Money, rounding, posting and report formulas |
| `docs/REQUIREMENTS_TRACEABILITY.md` | Requirement → module → test → status |
| `docs/DECISION_LOG.md` | Decisions D-000 to D-042 |
| `docs/REPORT_CATALOG.md` | 66 target reports |
| `docs/ANALYTICS_AI_EXCEL_POWERBI_PLAN.md` | Analytics/AI/Excel/Power BI plan; Phase A and first Excel/Power BI/grounded-insight slices delivered |
| `docs/DEVELOPMENT_ROADMAP.md` | Phases and gates |
| `docs/BACKUP_AND_RECOVERY.md` | RPO/RTO and restore drill |

## Rules this build follows

- No Firebase, no paid APIs, no new external services.
- No real customer or bank data in demo/tests.
- No unverified claim: every "works" line above maps to a test that ran.
- Nothing is pushed to GitHub from this machine.

## Next slice (recommended order)

1. Complete analytics Phase B: the remaining 66-report catalogue, drill-down/filters, empty states,
   EN/HI labels and saved dashboard layouts.
2. Turn the static Power BI pack into an optional Service model only if the owner chooses that scope:
   token-authenticated read-only API, star schema, RLS and refresh reconciliation.
3. Add a real AI provider behind explicit consent and a kill switch; keep deterministic totals and
   require citations. The current AI Insights sheet stays the no-provider fallback.
3. Partial/one-to-many bank matching; auto-post bank charges and interest.
4. GSTR-2B exception ageing and supplier-wise follow-up summary; period comparison trends.
5. Statement/invite email delivery and ownership transfer, with an explicit permission editor.
6. Then PostgreSQL, concurrency hardening and the Next.js front end.
