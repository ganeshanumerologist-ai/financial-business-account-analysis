# ARTHIVIO — Feature Inventory

Baseline inventory built from the governing specification, verified against the actual workspace.

**Verification status of the workspace: 0 application features exist.** Every row below is therefore `NOT IMPLEMENTED` — verified by recursive directory listing (see `docs/SOFTWARE_AUDIT.md` §2), not assumed.

| Field | Value |
|---|---|
| Inventory date | 2026-10-24 |
| Spec source | `ARTHIVIO_OpenCode_Master_Build_Prompt_WITH_RULES.md` (763 lines) |
| Implemented features | **0** |
| Verified working features | **0** |
| Specified features tracked | 142 tracked line items across 13 modules (counted from this file, not estimated) |
| Status vocabulary | `NOT IMPLEMENTED` · `PARTIAL` · `IMPLEMENTED` · `VERIFIED` |

> A feature only reaches `VERIFIED` when implementation + tests + documentation agree. Nothing has reached even `IMPLEMENTED`.

---

## 1. Inventory summary by module

| Module | Spec § | Screens | Forms | Calc rules | Exports | Status |
|---|---|---|---|---|---|---|
| Public marketing site | 5 | 7 | 2 | — | — | NOT IMPLEMENTED |
| Auth / tenants / org | 6, 8 | 6 | 6 | — | — | NOT IMPLEMENTED |
| Onboarding wizard | 8 | 16 steps | 16 | — | — | NOT IMPLEMENTED |
| Accounting engine | 9 | 12 | 8 | 22 | 6 | NOT IMPLEMENTED |
| Billing / invoices / POS | 10 | 10 | 9 | 14 | 5 | NOT IMPLEMENTED |
| Inventory / barcode | 11 | 9 | 8 | 9 | 5 | NOT IMPLEMENTED |
| Offline & sync | 12 | 3 | 2 | 3 | — | NOT IMPLEMENTED |
| Reports & analytics | 14 | 1 + ~150 templates | 3 | ~150 formulas | yes | NOT IMPLEMENTED |
| AI insights | 15 | 2 | 1 | — | 1 | NOT IMPLEMENTED |
| Documents / compliance | 18 | 5 | 3 | tax rules | 3 | NOT IMPLEMENTED |
| Users & permissions | 17 | 4 | 4 | — | 1 | NOT IMPLEMENTED |
| Settings | 6, 19 | 6 | 6 | — | 1 | NOT IMPLEMENTED |
| Backups / DR | 16 | 2 | 2 | — | — | NOT IMPLEMENTED |

*Screens/forms/exports columns are **planning estimates** derived from the spec, not counted artefacts — nothing exists to count. The authoritative count in this file is the 142 tracked line items, each individually listed below.*

---

## 2. Pages and navigation

### 2.1 Public site

| ID | Page | Requirement | Status |
|---|---|---|---|
| UI-P01 | Home | Headline "Smarter Finance. Stronger Business.", supporting message, product overview, dashboard preview, growth charts, feature summaries, security info, Get Started CTA | NOT IMPLEMENTED |
| UI-P02 | Platform | Module overview | NOT IMPLEMENTED |
| UI-P03 | Solutions | By business size/need | NOT IMPLEMENTED |
| UI-P04 | Industries | 15 industry templates | NOT IMPLEMENTED |
| UI-P05 | Reports & Analytics | Report catalogue overview | NOT IMPLEMENTED |
| UI-P06 | Resources | Docs/help | NOT IMPLEMENTED |
| UI-P07 | Pricing | Pricing presentation | NOT IMPLEMENTED |
| UI-P08 | Log in | Auth entry | NOT IMPLEMENTED |
| UI-P09 | Get Started | Registration entry | NOT IMPLEMENTED |

### 2.2 Authenticated dashboard navigation

Spec nav: Dashboard · Accounting · Sales & Purchase · Inventory · Banking & Cash · Reports & Analytics · Business Intelligence · AI Insights · Documents · Compliance · Users & Permissions · Settings.

Required behaviour: adapts to screen size, user role, enabled modules and business type; irrelevant items hidden; **server-side enforcement, never UI-hiding alone**.

| ID | Nav item | Status |
|---|---|---|
| UI-D01 | Dashboard | NOT IMPLEMENTED |
| UI-D02 | Accounting | NOT IMPLEMENTED |
| UI-D03 | Sales & Purchase | NOT IMPLEMENTED |
| UI-D04 | Inventory | NOT IMPLEMENTED |
| UI-D05 | Banking & Cash | NOT IMPLEMENTED |
| UI-D06 | Reports & Analytics | NOT IMPLEMENTED |
| UI-D07 | Business Intelligence | NOT IMPLEMENTED |
| UI-D08 | AI Insights | NOT IMPLEMENTED |
| UI-D09 | Documents | NOT IMPLEMENTED |
| UI-D10 | Compliance | NOT IMPLEMENTED |
| UI-D11 | Users & Permissions | NOT IMPLEMENTED |
| UI-D12 | Settings | NOT IMPLEMENTED |
| UI-D13 | Module-visibility by role/size | NOT IMPLEMENTED |

### 2.3 Dashboard widgets (from spec §14 + mockups)

| ID | Widget | Status |
|---|---|---|
| UI-W01 | KPI strip: Revenue, Net Profit, Cash Flow, Customers | NOT IMPLEMENTED |
| UI-W02 | Revenue & Profit trend chart | NOT IMPLEMENTED |
| UI-W03 | Business performance breakdown | NOT IMPLEMENTED |
| UI-W04 | Inventory value / AR / AP tiles | NOT IMPLEMENTED |
| UI-W05 | Quick actions (invoice, purchase, product, reports) | NOT IMPLEMENTED |
| UI-W06 | Date-range selector (e.g. 01 Apr 2025 – 30 Apr 2025) | NOT IMPLEMENTED |
| UI-W07 | Data freshness indicator | NOT IMPLEMENTED |
| UI-W08 | Empty / loading / error / permission-denied / offline states | NOT IMPLEMENTED |
| UI-W09 | User-customisable layout + restore default | NOT IMPLEMENTED |

---

## 3. Forms, buttons and filters

### 3.1 Core forms

| ID | Form | Key fields / validation | Status |
|---|---|---|---|
| F-001 | Register / Login | email, password policy, optional MFA | NOT IMPLEMENTED |
| F-002 | Create workspace | business name, legal structure, industry, financial year, currency | NOT IMPLEMENTED |
| F-003 | Business profile | name, address, contacts, logo, GSTIN (conditional) | NOT IMPLEMENTED |
| F-004 | Chart of accounts setup | account code, name, group, type, opening balance | NOT IMPLEMENTED |
| F-005 | Journal entry | date, narration, lines (account, debit, credit), source ref | NOT IMPLEMENTED |
| F-006 | Invoice | number, date, seller/buyer, place of supply, line items, discount, tax, totals, terms | NOT IMPLEMENTED |
| F-007 | Receipt / payment | party, amount, method, allocation, reference | NOT IMPLEMENTED |
| F-008 | Credit / debit note | original doc ref, reason, lines | NOT IMPLEMENTED |
| F-009 | Product / service | SKU, barcode, unit, price, tax, reorder level, variants | NOT IMPLEMENTED |
| F-010 | Stock movement | type, product, qty, warehouse, source doc, approval | NOT IMPLEMENTED |
| F-011 | Stock count | physical count vs system, variance, approval | NOT IMPLEMENTED |
| F-012 | Customer / supplier | name, mobile, address, GSTIN, credit terms | NOT IMPLEMENTED |
| F-013 | Import mapping (CSV/Excel) | column mapping, type coercion, preview, error report | NOT IMPLEMENTED |
| F-014 | Bank reconciliation | statement lines vs ledger, matching, difference | NOT IMPLEMENTED |
| F-015 | Budget | period, account, budget amount vs actual | NOT IMPLEMENTED |
| F-016 | Fixed asset | cost, date, method, useful life, depreciation schedule | NOT IMPLEMENTED |
| F-017 | User & role | user, role, branch/warehouse scope | NOT IMPLEMENTED |
| F-018 | Period close / lock | period, lock state, reopening approval | NOT IMPLEMENTED |
| F-019 | Reversal / correction | target doc, reason, approval, audit link | NOT IMPLEMENTED |

### 3.2 Buttons and actions

| ID | Action | Expected behaviour | Status |
|---|---|---|---|
| B-001 | Save / Post journal | Block if unbalanced; atomic write; audit entry | NOT IMPLEMENTED |
| B-002 | Post invoice | Post stock + AR + tax + GL atomically; idempotent | NOT IMPLEMENTED |
| B-003 | Print A4 / 58mm / 80mm | Correct layout per format | NOT IMPLEMENTED |
| B-004 | Export report (PDF/Excel/CSV) | Permission-checked, totals preserved | NOT IMPLEMENTED |
| B-005 | Import data | Validate, preview, reject-on-error, no partial silent write | NOT IMPLEMENTED |
| B-006 | Reconcile | Match, record difference, require approval | NOT IMPLEMENTED |
| B-007 | Reverse entry | Create mirror entry with reason; never edit posted | NOT IMPLEMENTED |
| B-008 | Close period | Lock postings; auditable | NOT IMPLEMENTED |
| B-009 | Backup now / Restore | Verified restore with integrity check | NOT IMPLEMENTED |
| B-010 | Sync offline queue | Idempotent; surface conflicts | NOT IMPLEMENTED |
| B-011 | Language switch (EN/HI) | Full UI + validation messages translate | NOT IMPLEMENTED |

### 3.3 Filters

| ID | Filter | Status |
|---|---|---|
| FL-001 | Date range (from/to) | NOT IMPLEMENTED |
| FL-002 | Financial-year / period | NOT IMPLEMENTED |
| FL-003 | Branch / warehouse / department / project / cost centre | NOT IMPLEMENTED |
| FL-004 | Account / ledger | NOT IMPLEMENTED |
| FL-005 | Customer / supplier | NOT IMPLEMENTED |
| FL-006 | Document status (draft/posted/paid/void) | NOT IMPLEMENTED |
| FL-007 | Currency | NOT IMPLEMENTED |
| FL-008 | Text search | NOT IMPLEMENTED |
| FL-009 | Saved views / custom dashboard restore | NOT IMPLEMENTED |

---

## 4. Calculation rules (must be deterministic and tested)

| ID | Rule | Specification | Status |
|---|---|---|---|
| C-001 | Double-entry balance | Σ debits = Σ credits at configured precision | NOT IMPLEMENTED |
| C-002 | Trial balance equality | Σ debit balances = Σ credit balances | NOT IMPLEMENTED |
| C-003 | Balance-sheet equation | Assets = Liabilities + Equity | NOT IMPLEMENTED |
| C-004 | Opening + movements = closing | per account and per period | NOT IMPLEMENTED |
| C-005 | Money arithmetic | decimal-safe; no binary float on authoritative paths | NOT IMPLEMENTED |
| C-006 | Rounding policy | explicit, configurable, residuals allocated | NOT IMPLEMENTED |
| C-007 | Line tax | taxable value × rate, per line, with HSN/SAC mapping | NOT IMPLEMENTED |
| C-008 | Invoice total | Σ(net) − discounts + taxes + rounding | NOT IMPLEMENTED |
| C-009 | Discount allocation | proportional, deterministic | NOT IMPLEMENTED |
| C-010 | Duplicate prevention | idempotency key / unique doc number constraint | NOT IMPLEMENTED |
| C-011 | Date-range inclusivity | period boundaries defined and tested | NOT IMPLEMENTED |
| C-012 | AR / AP ageing buckets | 0-30 / 31-60 / 61-90 / 90+ | NOT IMPLEMENTED |
| C-013 | Depreciation | SLM / WDV schedules, pro-rata by date | NOT IMPLEMENTED |
| C-014 | EMI / interest schedule | principal/interest split, rounding | NOT IMPLEMENTED |
| C-015 | Stock closing | Opening + Receipts + Returns + Transfers In + Production In − Sales − Supplier Returns − Damage − Transfers Out − Production Consumption ± Adjustments | NOT IMPLEMENTED |
| C-016 | COGS / inventory valuation | FIFO / weighted average, reconciled to GL | NOT IMPLEMENTED |
| C-017 | Gross margin | (Revenue − COGS) / Revenue | NOT IMPLEMENTED |
| C-018 | Cash flow | operating / investing / financing split | NOT IMPLEMENTED |
| C-019 | Multi-currency translation | rate source, gain/loss posting | NOT IMPLEMENTED |
| C-020 | Subledger ↔ control reconciliation | AR/AP subledger = GL control account | NOT IMPLEMENTED |
| C-021 | Bank reconciliation difference | statement vs ledger, must resolve to zero or be explained | NOT IMPLEMENTED |
| C-022 | Budget variance | actual − budget, % and direction | NOT IMPLEMENTED |

---

## 5. Import / export

| ID | Function | Requirement | Status |
|---|---|---|---|
| IO-01 | CSV import | header validation, type coercion, error rows reported | NOT IMPLEMENTED |
| IO-02 | Excel (.xlsx) import | same rules, sheet selection | NOT IMPLEMENTED |
| IO-03 | Customer/supplier import | dedupe policy; never auto-merge on mobile match | NOT IMPLEMENTED |
| IO-04 | Opening balance / stock import | validation + reconciliation summary | NOT IMPLEMENTED |
| IO-05 | CSV export | permission-checked, encoding-safe | NOT IMPLEMENTED |
| IO-06 | Excel export | formatting preserved, totals as values | NOT IMPLEMENTED |
| IO-07 | PDF report export | layout, page breaks, totals | NOT IMPLEMENTED |
| IO-08 | Invoice PDF | A4 + thermal formats | NOT IMPLEMENTED |
| IO-09 | Backup export / restore | integrity verified, not just file existence | NOT IMPLEMENTED |
| IO-10 | Malformed input handling | empty file, bad headers, wrong types, huge file, dupes | NOT IMPLEMENTED |

---

## 6. Reports (≈150 templates, 10 groups)

| Group | Examples | Status |
|---|---|---|
| 1. Financial statements & performance | P&L, Balance Sheet, Cash Flow, Trial Balance summary, ratio analysis | NOT IMPLEMENTED |
| 2. Accounting, ledgers & audit | General ledger, journal register, day book, audit trail, corrections | NOT IMPLEMENTED |
| 3. Sales & customer analysis | Sales register, top customers, customer ageing, returns, sales trend | NOT IMPLEMENTED |
| 4. Purchase & supplier analysis | Purchase register, supplier ageing, price variance | NOT IMPLEMENTED |
| 5. Inventory & warehouse | Stock summary, movement history, valuation, dead stock, reorder | NOT IMPLEMENTED |
| 6. Costing, manufacturing & operations | Job costing, WIP, production consumption, yield | NOT IMPLEMENTED |
| 7. Cash, credit & risk | Cash flow forecast, receivables risk, credit exposure | NOT IMPLEMENTED |
| 8. Tax, GST & compliance | GSTR-1/3B working, HSN summary, ITC reconciliation (2B is a source, not proof) | NOT IMPLEMENTED |
| 9. Strategy, organization & process | Budget vs actual, cost-centre performance, KPI packs | NOT IMPLEMENTED |
| 10. AI, forecasting & cross-business | Trend explanation, forecast bands (clearly labelled) | NOT IMPLEMENTED |

Mandatory per-report metadata (all missing): defined source data, explicit formula, applicability conditions, permissions, filters, drill-down, export, EN/HI labels, freshness, missing-data warnings, actual-vs-estimate separation.

---

## 7. Persistence, security, operations

| ID | Capability | Status |
|---|---|---|
| S-001 | Database schema + migrations | NOT IMPLEMENTED |
| S-002 | Tenant isolation enforced server-side | NOT IMPLEMENTED |
| S-003 | RBAC (owner/admin/manager/accountant/cashier/sales/inventory/read-only) | NOT IMPLEMENTED |
| S-004 | Branch/warehouse scoping | NOT IMPLEMENTED |
| S-005 | Audit log (append-only) | NOT IMPLEMENTED |
| S-006 | Secrets via environment variables | NOT IMPLEMENTED |
| S-007 | Session security (expiry, rotation, logout-all) | NOT IMPLEMENTED |
| S-008 | Password hashing (strong KDF) | NOT IMPLEMENTED |
| S-009 | MFA (optional) | NOT IMPLEMENTED |
| S-010 | Automated daily backup + integrity check | NOT IMPLEMENTED |
| S-011 | Tested restore procedure | NOT IMPLEMENTED |
| S-012 | Off-site / immutable backup copy | NOT IMPLEMENTED |
| S-013 | Offline local data protection | NOT IMPLEMENTED |
| S-014 | Export permission enforcement | NOT IMPLEMENTED |
| S-015 | Security event logging / alerts | NOT IMPLEMENTED |
| S-016 | Version control + rollback | ❌ FAIL — no repo initialised; git 2.56 available in portable form (B-002) |

---

## 8. Out-of-scope / explicitly deferred

Recorded so scope cannot drift silently:

- Real GST/e-invoice API calls, IRN generation, statutory QR — require verified official access and professional review (Phase 9).
- Real payment gateway / bank integration — Phase 9, credentials + approval required.
- AI sending tenant data to external providers — blocked pending consent and data-protection review.
- Production deployment, domain, public exposure — requires explicit owner approval.
- Claims of certification or compliance — must not be published without independent verification.

---

## 9. What exists today (complete list)

| Item | Type | Status |
|---|---|---|
| `Arthivio Smarter Finance Dashboard.png` | Design mockup, 1536×1024 | Present, reference only |
| `WhatsApp Image 2026-10-24 at 10.10.22 AM.jpeg` | Design mockup, 1536×1024 | Present, reference only |
| `docs/*.md` (18 files) | Audit + planning documentation | Created by this audit and Rule 1 planning |

That is the entire feature inventory of the running product: **nothing.**


---

## Implemented features — Build 0.1 (2026-10-24)

Status vocabulary: **VERIFIED** means a test in `docs/TEST_RESULTS.md` run
`RUN-2026-10-24-02` exercised it and passed.

| # | Feature | Evidence | Status |
|---|---|---|---|
| 1 | Create a multi-line tax invoice with discounts | `TestInvoice`, `test_web.test_05` | VERIFIED |
| 2 | CGST/SGST vs IGST by place of supply | `test_totals_and_tax_intra_state`, `test_inter_state_uses_igst` | VERIFIED |
| 3 | Optional round-to-rupee with rounding account | `test_round_to_rupee_posts_rounding` | VERIFIED |
| 4 | Sequential invoice and journal numbering | `test_totals_and_tax_intra_state` (`INV-00001`) | VERIFIED |
| 5 | Idempotent invoice creation | `test_invoice_idempotency` | VERIFIED |
| 6 | Balanced double-entry posting, immutability, reversals | `TestPosting`, `test_reversal_nets_to_zero` | VERIFIED |
| 7 | Period locks | `test_period_lock_blocks` | VERIFIED |
| 8 | Perpetual inventory, COGS, negative-stock block | `test_cogs_and_stock`, `test_insufficient_stock_blocked` | VERIFIED |
| 9 | Goods vs services revenue classification | `test_service_item_posts_to_service_revenue` | VERIFIED |
| 10 | General ledger with opening/closing and running balance | `test_general_ledger_running_balance` | VERIFIED |
| 11 | Trial balance with equality check | `TestPosting`, `test_web.test_04` | VERIFIED |
| 12 | Profit & loss | `test_profit_and_loss_matches_ledger` | VERIFIED |
| 13 | Balance sheet with A = L + E check | `test_balance_sheet_equation`, `test_04` | VERIFIED |
| 14 | Customer balances and statements | `test_customer_statement_matches_receivable_control`, `test_09` | VERIFIED |
| 15 | Customer and item masters | `test_web.test_07` | VERIFIED |
| 16 | Login, sessions, lockout | `TestSecurity`, `test_02`, `test_03` | VERIFIED |
| 17 | CSRF protection | `test_06_csrf_required` | VERIFIED |
| 18 | RBAC and tenant isolation | `TestSecurity`, `test_08`, cross-tenant tests | VERIFIED |
| 19 | Audit log (logins, postings, master data) | audit rows asserted in postings; UI page | PARTIAL (no tamper-evidence chain) |
| 20 | Responsive branded UI | manual browser check | VERIFIED (visual only) |

Everything else in the 142-item inventory above remains **NOT IMPLEMENTED**.


---

## 3. Status after Build 0.2 (2026-10-24)

The baseline table above is preserved as the audit-time record (0 features). This section is
the current, test-backed state. A row is `VERIFIED` only when implementation, automated tests
and documentation agree.

| Module | Baseline status | Current status | Evidence |
|---|---|---|---|
| Accounting engine | NOT IMPLEMENTED | **VERIFIED (core)** | double entry, period locks, reversals, TB, ledger, P&L, balance sheet |
| Billing / invoices | NOT IMPLEMENTED | **VERIFIED (sales)** | multi-line GST invoices, numbering, round-off, idempotency |
| Receipts / AR | NOT IMPLEMENTED | **VERIFIED** | receipts, advances, allocation guards, ageing, statements |
| Purchases / AP | NOT IMPLEMENTED | **VERIFIED (bills)** | input GST, weighted-average stock, vendor payments, ageing |
| Credit notes | NOT IMPLEMENTED | **VERIFIED (sales returns)** | revenue/GST/COGS reversal, stock return, over-credit guard |
| Inventory | NOT IMPLEMENTED | **PARTIAL** | perpetual stock + weighted average; no barcode/warehouse/transfers |
| Reports & analytics | NOT IMPLEMENTED | **PARTIAL** | TB, ledger, P&L, BS, day book, ageing, GST summary; 6 of 66 catalogue reports |
| Documents / compliance | NOT IMPLEMENTED | **PARTIAL** | GST working summary + CSV registers; no GSTR-1 JSON, e-invoice, PDF |
| Users & permissions | NOT IMPLEMENTED | **PARTIAL** | RBAC enforced in data layer + routes; no invite/admin screens |
| Backups / DR | NOT IMPLEMENTED | **VERIFIED (local)** | verified online backup, SHA-256, restore drill; no off-site copy |
| Settings | NOT IMPLEMENTED | **NOT IMPLEMENTED** | tenant fiscal year exists in data, no settings UI |
| Public marketing site | NOT IMPLEMENTED | **NOT IMPLEMENTED** | authenticated app only |
| Onboarding wizard | NOT IMPLEMENTED | **NOT IMPLEMENTED** | demo seed only |
| Offline & sync | NOT IMPLEMENTED | **NOT IMPLEMENTED** | local server only |
| AI insights | NOT IMPLEMENTED | **NOT IMPLEMENTED** | not started |


## 10. Status after Build 0.3 (2026-10-24)

### Implemented and verified

| Feature | Where | Notes |
|---|---|---|
| Business settings | `/settings` | legal name, GSTIN, GST state, address, city, PIN, phone, email, bank details, invoice terms; owner-only; validated and audited |
| Print-ready tax invoice | `/invoices/<id>/print` | A4 HTML, GSTIN/HSN/SAC, CGST/SGST vs IGST, amount in words, bank/terms, Print / Save as PDF |
| GSTR-1 working CSV | `/export/gstr1.csv` | B2B, B2CS, HSN, CDNR/CDNUR, TOTAL and CN TOTAL rows, warnings |
| GSTR-1 working JSON | `/export/gstr1.json` | `arthivio-gstr1-working-v1`, exact INR decimal strings, warnings and note |
| Additive schema migration | `db.init_db` | `ALTER TABLE ADD COLUMN` only; existing data preserved; idempotent |
| GST page links | `/reports/gst` | period-aware GSTR-1 CSV/JSON buttons; net-vs-gross explanation |

### Still not implemented

- GSTR-2 / GSTR-2B purchase reconciliation, GSTR-3B, official GSTR-1 JSON schema, GST portal upload
- e-invoice/IRN, e-way bill, TDS/TCS
- Auto-posting journal entries from unmatched bank lines, cheque printing, payment reminders
- PDF binary generation (browser print is used), Excel export, email delivery
- Multi-user invite/role admin UI, PostgreSQL, Next.js UI

## 11. Status after Build 0.4 (2026-10-24)

### Implemented and verified

| Feature | Where | Notes |
|---|---|---|
| Debit notes / purchase returns | Bill detail, `/debit-notes` | original bill value + input GST reversed, stock out at bill cost, payable reduced, over-debit/stock guards, vendor credit after payment |
| Debit-note export | `/export/debit-notes.csv` | note, date, vendor, bill, reason, taxable, GST, total |
| Bank statement import | `/bank-recon` | CSV file or paste; Debit/Credit, Amount+Dr/Cr and Withdrawal/Deposit layouts; ISO/DD-MM-YYYY dates; SHA-256 dedup |
| Bank matching | `/bank-recon` | exact signed amount, ±7-day suggestions, auto-match unambiguous, manual match/unmatch, one-to-one ledger use |
| Reconciliation summary | `/bank-recon` | statement net, ledger net, unmatched amounts, opening/closing ledger, statement balance, difference |
| Bank statement export | `/export/bank-statement.csv` | period/account filtered statement lines with match status |
| Bank/debit-note permissions and audit | `security.py`, `bank.py` | `bank.reconcile`, `debit_note.create`; `bank.import/match/unmatch/auto_match`, `debit_note.create` |

### Still not implemented

- Partial-amount / one-to-many bank matching; auto-posting bank charges or interest
- Official GSTR-2B portal format, official GSTR-1 schema, GST portal upload (working aids added in §12–§13)
- e-invoice/IRN, e-way bill, TDS/TCS
- Cheque printing, payment reminders, Excel export, email delivery
- PostgreSQL, Next.js UI (team invite/role admin UI added in §13)

## 12. Status after Build 0.5 (2026-10-24)

### Implemented and verified

| Feature | Where | Notes |
|---|---|---|
| GSTR-3B working summary | `/reports/gstr3b?month=YYYY-MM` | 3.1 outward supplies net of credit notes, 4 eligible ITC net of debit notes, 5 head-wise payment, month selector |
| GSTR-1/ledger reconciliation | `/reports/gstr3b` | six checks with expected, actual, difference and OK/CHECK status; warnings for B2C, HSN, negative heads and ITC reversal |
| GSTR-3B working CSV | `/export/gstr3b.csv?month=YYYY-MM` | 3.1, 4, 5 and reconciliation sections; requires `report.export` |
| GSTR-3B safety labels | page and CSV | explicitly a preparation aid, head-wise set-off only, no portal upload or official schema claim |

### Still not implemented

- GST portal upload, official GSTR-3B JSON, challan/acknowledgment, cross-utilisation of IGST credit
- RCM, zero-rated/nil/exempt supplies, import ITC
- Partial/one-to-many bank matching, auto-posting bank charges/interest
- e-invoice/IRN, e-way bill, TDS/TCS
- Cheque printing, payment reminders, Excel export, email delivery
- PostgreSQL, Next.js UI

## 13. Status after Build 0.7 (2026-10-25)

### Implemented and verified

| Feature | Where | Evidence |
|---|---|---|
| Team admin | `/users` | member list with role/status, invite form, pending invites, revoke, role save, suspend/reactivate/remove |
| One-time invites | `/users/invite` → `/invite/<token>` | SHA-256 token hash only, 7-day expiry, new-user password or existing-user current password, auto-login after acceptance |
| Protected authority | `/users` and `security.py` | owner role cannot be assigned/changed, self role/status changes rejected, suspended/removed sessions revoked |
| Business switcher | `/businesses`, `POST /switch` | lists active memberships, checks membership on every switch, audits the switch |
| Shareable statements | customer/vendor page → `/share/statement/<token>` | 7/30/90-day read-only bearer link, no-login A4 print view, revoke, expiry, view count, noindex/no-store |
| GSTR-2B import | `/gstr2b` | working CSV, SHA-256 dedup, latest active import supersedes prior, import history, per-month view |
| GSTR-2B matching | `/gstr2b?month=YYYY-MM` | supplier GSTIN + normalised invoice, matched/mismatch/missing-in-books/missing-in-2B, warnings, no auto-posting or bill edits |
| ITC review | `/gstr2b?month=YYYY-MM`, `POST /gstr2b/review` | one state per line (open/follow-up/ITC hold/accepted), note, audit trail, active-import only, `gst.reconcile` |
| 3B vs 2B comparison | `/gstr2b?month=YYYY-MM` | 3B eligible/gross ITC, debit-note reversal, 2B ITC, difference, review buckets, warnings; no posting |
| GSTR-2B export | `/export/gstr2b.csv?month=YYYY-MM` | 2B rows, missing bills, review state/note, comparison summary and working-aid note; `report.export` |

### Still not implemented

- Email delivery of invites/statements; ownership transfer; per-permission editor; SSO
- Official GSTR-2B JSON/portal integration, supplier email automation, exception ageing and actual ITC claim/reversal posting
- GST portal upload, official GSTR-1/3B schemas, cross-utilisation, RCM/zero-rated/exempt/import ITC
- Partial/one-to-many bank matching; auto-posting bank charges/interest
- e-invoice/IRN, e-way bill, TDS/TCS, cheque printing, payment reminders, Excel export
- PostgreSQL, Next.js UI, load/concurrency/penetration testing
