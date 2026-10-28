# ARTHIVIO — Test Plan

| Field | Value |
|---|---|
| Version | 1.1 (active; Build 0.12) |
| Date | 2026-10-28 |
| Status | **Active; 245 automated tests execute on the local build** (see `docs/TEST_RESULTS.md` section 25) |
| Owner | Project owner (approval), OpenCode agent (authoring & execution) |
| Data policy | Synthetic data only. No real bank credentials, no real customer financial data. |

---

## 1. Purpose and scope

Define how ARTHIVIO will be verified so that no financial or security claim is made without evidence.

**In scope:** every feature listed in `docs/FEATURE_INVENTORY.md` — public site, auth/tenants/roles, accounting engine, billing, inventory, offline sync, reports, AI insights, documents/compliance, settings, backups/DR.

**Out of scope for now:** live GST/e-invoice API calls, payment gateways, bank feeds, production deployment, penetration testing by a third party (all Phase 9/10, and all require credentials or approvals that do not exist).

---

## 2. Test levels and gates

| Level | Tool | Gate |
|---|---|---|
| Unit | `pytest` | 100% of critical calc functions covered; all pass |
| Property / invariant | `pytest` + Hypothesis | Journal balance, TB equality, BS equation hold over randomised inputs |
| Integration | `pytest` + DB fixtures | Posting→ledger→report path consistent |
| API / contract | `httpx` against test app | Status codes, authz, validation errors |
| Security | `pytest` + (later) OWASP ZAP | Cross-tenant and privilege-escalation attempts all denied |
| E2E / UI | Playwright (deferred; needs Node) | Critical journeys only |
| Accessibility | axe-core (deferred) | No critical violations on core screens |
| Performance | Locust/k6 (deferred) | Report page p95 within agreed budget |
| Restore drill | Scripted backup→restore→verify | Data integrity + tenant boundaries intact |

**Release gate:** critical financial invariants + security tests must pass. If a critical test fails, the affected posting or report must **block**, not guess.

---

## 3. Environments

| Env | Purpose | State |
|---|---|---|
| Local dev | Development + unit tests | ✅ Python 3.14.6 available; deps NOT installed |
| Local test DB | Isolated test database, seeded per run | ⛔ Not created |
| CI | Automated regression | ⛔ No CI, no git |
| Staging | Pre-production verification | ⛔ Does not exist |

**Known constraint (corrected after deeper inspection):** portable **Node 20.20.2 / npm 10.8.2** and **git 2.56.0** exist on this machine but are **not on `PATH`**; PostgreSQL and Docker are absent (verified — see `docs/SOFTWARE_AUDIT.md` §3). Commands must prefix `PATH` or use absolute paths. Any test requiring a real PostgreSQL server is `BLOCKED` until the database decision is made (`docs/DECISION_LOG.md` DF-01).

---

## 4. Test data strategy

- **Synthetic only.** Generated ledgers/invoices with obviously fake names (`Test Customer 001`), fake GSTIN formats that fail checksum, and no real PAN/mobile/bank numbers.
- **Fixture set A — empty:** brand-new tenant with zero transactions. Verifies empty states and zero-division safety.
- **Fixture set B — small balanced book:** ~20 journals, 2 customers, 2 suppliers, 5 products. Hand-computed expected values, stored as constants in tests.
- **Fixture set C — edge cases:** zero-value lines, negative amounts (credit notes), max-precision amounts, same-day duplicates, period-boundary dates (first/last day of FY), leap year, multi-currency.
- **Fixture set D — hostile:** malformed CSV, wrong headers, 0-byte file, 500k-row import, SQL-injection strings, XSS payloads in names, oversized uploads.
- **Fixture set E — two tenants:** identical-looking data across tenants to prove isolation.
- Hand-computed expected totals are committed alongside fixtures so reports can be independently recalculated (Layer 5 validation).

---

## 5. Test cases

### 5.1 Audit-time checks (executed now)

| ID | Test | Expected | Method |
|---|---|---|---|
| A-001 | Workspace contains application source | Source tree present | `Get-ChildItem -Recurse` |
| A-002 | Dependency manifest exists | `package.json`/`requirements.txt` found | File scan |
| A-003 | Test suite exists | `tests/` with runnable tests | File scan |
| A-004 | Git repository present | `.git` present, `git status` runs | `Get-Command git` |
| A-005 | Node toolchain available | `node -v` succeeds | `Get-Command node` |
| A-006 | DB server available | `psql --version` succeeds | `Get-Command psql` |
| A-007 | Secrets committed | None present | File scan for `.env`, keys |
| A-008 | Real customer data present | None present | File scan |
| A-009 | Spec available in repo | Present | File scan |
| A-010 | Mockups meet design constraints | Compliant | Visual review vs spec §4 |
| A-011 | Mockup resolution adequate for 8K/retina use | ≥ 3840 px wide | Binary header parse |
| A-012 | Remote repository inspected (contents + history) | Contents and commits known | GitHub API |

### 5.2 Accounting invariants (blocked — no engine)

| ID | Test | Expected | Severity if fail |
|---|---|---|---|
| ACC-001 | Posted journal with unequal debit/credit is rejected | Rejected, no DB write | Critical |
| ACC-002 | Balanced journal posts atomically (all lines or none) | Atomic | Critical |
| ACC-003 | Trial balance debits == credits | Equal to precision | Critical |
| ACC-004 | Balance sheet: Assets == Liabilities + Equity | Equal | Critical |
| ACC-005 | Opening + Σ movements == closing balance, per account | Equal | Critical |
| ACC-006 | P&L net profit == retained-earnings movement in equity | Equal | Critical |
| ACC-007 | Cash flow closing cash == balance-sheet cash | Equal | Critical |
| ACC-008 | AR subledger total == GL AR control account | Equal | Critical |
| ACC-009 | AP subledger total == GL AP control account | Equal | Critical |
| ACC-010 | Inventory ledger total == GL inventory account (perpetual) | Equal | High |
| ACC-011 | Money math uses Decimal, not float | No float on authoritative path | Critical |
| ACC-012 | Rounding applied per policy; residual allocated, sum preserved | Sum exact | High |
| ACC-013 | Journal dated in locked period is rejected | Rejected | High |
| ACC-014 | Posted entry cannot be edited; reversal only | Blocked + reversal path | Critical |
| ACC-015 | Reversal restores original balances exactly | Net zero | High |

### 5.3 Duplicates, dates, concurrency

| ID | Test | Expected |
|---|---|---|
| DUP-001 | Same idempotency key posted twice → one posting | Second is no-op, logged |
| DUP-002 | Duplicate invoice number in same FY/tenant | Rejected |
| DUP-003 | Duplicate invoice number across tenants | Allowed (isolation) |
| DUP-004 | Two concurrent posts of same doc | Exactly one succeeds |
| DT-001 | Range 01-Apr..30-Apr includes both endpoints | Included |
| DT-002 | Transaction on first/last day of FY counted in correct FY | Correct |
| DT-003 | Leap-day transaction | Valid, correctly bucketed |
| DT-004 | Timezone-dependent date shift | No off-by-one across TZ |
| DT-005 | Future-dated posting | Per policy (warn or block), consistent |

### 5.4 Reports and reconciliation

| ID | Test | Expected |
|---|---|---|
| REP-001 | Report total == independent recalculation from source rows | Equal |
| REP-002 | Drill-down rows sum to the displayed total | Equal |
| REP-003 | Filters change totals consistently (no cached leakage) | Consistent |
| REP-004 | Empty data → zero/empty state, never fabricated figures | No invented data |
| REP-005 | Stale data flagged | "Stale" badge shown |
| REP-006 | Report blocked when invariant fails | Blocked with reason |
| REP-007 | Actual vs estimate vs forecast visually separated | Labelled |
| REC-001 | Bank reconciliation difference resolves to 0 or is explained | Explained |
| REC-002 | Statement vs ledger mismatch raises Needs Review | Flagged, not auto-corrected |

### 5.5 Import / export

| ID | Test | Expected |
|---|---|---|
| IMP-001 | Valid CSV imports all rows, reports count | Success + count |
| IMP-002 | Wrong headers → clear error, zero writes | Rejected |
| IMP-003 | Invalid types → row-level errors with line numbers | Rejected with report |
| IMP-004 | 0-byte file | Graceful message, no crash |
| IMP-005 | Duplicate keys in file | Rejected or flagged per policy |
| IMP-006 | 500k-row file | Completes or fails cleanly within budget |
| IMP-007 | Partial failure never leaves half-imported book | Transactional rollback |
| EXP-001 | CSV/Excel totals equal on-screen totals | Equal |
| EXP-002 | Export without permission → 403, no data leak | Denied |
| EXP-003 | PDF layout complete; no clipped totals; page breaks sane | Correct |
| EXP-004 | Unicode/Hindi text in export | Renders correctly |
| EXP-005 | Export of empty report | Valid empty file, no crash |

### 5.6 Security

| ID | Test | Expected |
|---|---|---|
| SEC-001 | Tenant A user requests Tenant B record by ID | 403/404, no data |
| SEC-002 | Tenant A user lists records with B's tenant_id param | Filtered/rejected |
| SEC-003 | Role escalation (cashier → admin endpoint) | Denied server-side |
| SEC-004 | Hidden UI element ≠ authorization (direct API call) | Denied |
| SEC-005 | Export permission enforced server-side | Denied |
| SEC-006 | SQL injection in search/filter fields | No effect, no error leak |
| SEC-007 | XSS payload in customer name rendered in report | Escaped |
| SEC-008 | Session fixation / missing rotation on login | Prevented |
| SEC-009 | Idle session expiry | Enforced |
| SEC-010 | Password stored with strong KDF + salt | Verified format |
| SEC-011 | Secrets not in source or logs | Absent |
| SEC-012 | Cross-tenant backup restore cannot mix data | Isolated |
| SEC-013 | Unauthorized file upload type rejected | Rejected |
| SEC-014 | Rate limiting on login | Enforced |

### 5.7 Backup / restore

| ID | Test | Expected |
|---|---|---|
| BAK-001 | Backup runs on schedule; status recorded | Success logged |
| BAK-002 | Backup failure raises alert | Alert fires |
| BAK-003 | Restore into clean environment reproduces all records | Row counts + checksums match |
| BAK-004 | Restore preserves tenant boundaries | No cross-tenant bleed |
| BAK-005 | Restore of corrupted backup fails loudly | No silent partial restore |
| BAK-006 | Backup is encrypted; key managed separately | Verified |
| BAK-007 | Restore time within RTO target | Measured and recorded |
| BAK-008 | Backup stored in a separate location from primary | Verified (not same disk) |

### 5.8 UI / accessibility / i18n

| ID | Test | Expected |
|---|---|---|
| UI-001 | All nav items reachable; no dead links | 100% reachable |
| UI-002 | Nav hides irrelevant modules by role | Correct per role |
| UI-003 | Forms validate required fields with readable errors | Clear messages |
| UI-004 | Empty / loading / error / offline / permission-denied states | All present |
| UI-005 | Keyboard-only navigation of core flows | Complete |
| UI-006 | Contrast meets WCAG AA on all text | Pass |
| UI-007 | Responsive at 360 / 768 / 1440 / 2560 px | No overflow or clipping |
| UI-008 | Hindi/English switch translates nav, validation, reports | Complete |
| UI-009 | Text remains sharp and readable at 200% zoom | No blur/clipping |
| UI-010 | Charts readable at high DPI; vectors where possible | Sharp |
| UI-011 | Massive screens (4K+) do not stretch text to unreadable sizes | Layout scales sanely |

---

## 6. Traceability

| Requirement group | Test IDs |
|---|---|
| Accounting engine (§9) | ACC-001…015, DUP-001…004, REP-001…007 |
| Billing (§10) | IMP-*, EXP-*, DUP-002, REP-001 |
| Inventory (§11) | ACC-010, REC-*, IMP-004 |
| Offline (§12) | DUP-001, DUP-004, UI-004 |
| Six-layer validation (§13) | ACC-*, REP-006, REC-002 |
| Reports (§14) | REP-001…007, UI-010 |
| AI insights (§15) | REP-007, SEC-001 |
| Backups (§16) | BAK-001…008 |
| Security (§17) | SEC-001…014 |
| Languages/a11y (§19) | UI-005…009 |
| Testing gates (§22) | All |

---

## 7. Execution procedure

1. Confirm environment prerequisites for the selected stack (see `docs/DECISION_LOG.md`).
2. Install dependencies (owner-approved), record exact versions.
3. Run, in order: format → lint → type-check → unit → property → integration → security → build.
4. Record every command and its literal output in `docs/TEST_RESULTS.md`.
5. Never edit results after the fact; append a new run with date.
6. If a command cannot run, record why. "Could not run" is a valid, honest result; "assumed pass" is not.

---

## 8. Entry / exit criteria

**Entry (per phase):** dependencies installed, test DB available, fixtures seeded, previous phase gate passed.

**Exit (per phase):** all critical tests pass; non-critical failures have documented waiver with owner sign-off; results recorded; docs synchronized.

**Hard stop conditions:** any ACC-001…014, SEC-001…005, or BAK-003 failure blocks progression until fixed.

---

## 9. Defect severity model

| Severity | Definition | Example |
|---|---|---|
| Critical / Blocker | Wrong money, cross-tenant leak, unbalanced posting, data loss | Journal posts unbalanced |
| High | Material misstatement, broken core flow, missing safeguard | Report total ≠ ledger |
| Medium | Degraded UX, missing non-core control | Filter resets on reload |
| Low | Cosmetic / minor | Label typo |
| Info | Observation, no action required | Raster mockup resolution |

---

## 10. Current plan status

| Item | Status |
|---|---|
| Test plan authored | ✅ DONE |
| Tests executable | ✅ YES (stdlib + temporary SQLite) |
| Test cases defined | 222 automated application tests plus 12 audit-time checks |
| Test cases executed | 222 application tests in `RUN-2026-10-27-03` |
| Test cases passed | 222 |
| Test cases failed | 0 |
| Test cases blocked | 0 |
| Application tests executed | **222** |
| Last verified | 2026-10-27, Python 3.14.6, Windows |

See `docs/TEST_RESULTS.md` for the literal run evidence and `docs/BUG_REPORT.md` for defects.

### Build 0.6 additions

- `T-401`–`T-412`: GSTR-2B CSV parsing, dedup/supersede, matching, differences, history,
  duplicate-period redirect, tenant isolation and export.
- `T-501`–`T-511`: invite create/accept/expiry, existing-user password, owner/self guards,
  role change, suspension session revocation, statement scope/expiry/revoke/view count.
- `T-601`–`T-604`: HTTP E2E for team invite acceptance, share/print/revoke, GSTR-2B import/export
  and business switching.

### Build 0.7 additions

- `T-701`–`T-705`: ITC review status + note + audit, superseded-import rejection, tenant scope,
  invalid status rejection, and 3B-vs-2B gap comparison.
- `T-706`: HTTP review POST, redirect, rendered status, comparison card and CSV review columns.
- `T-707`: Lighthouse accessibility/best-practices/SEO on the GSTR-2B review page.
- `T-708`: backup table list covers every persistent schema table (B-026 regression guard).

Operational checks in the same run: live GSTR-2B August 2026 reconciliation and ITC acceptance,
public statement creation/print/revoke, backup integrity + restore, and Lighthouse audits.

### Build 0.8 additions

- `T-801`: unauthenticated `/` returns the public product home page (200, no login redirect),
  contains the headline, trust strip and synthetic-data note, and still leaves
  `/dashboard-does-not-exist` protected.
- `T-802`: `/demo` is opt-in, loopback-only, creates a normal session and audit event, and returns
  404 when disabled.
- `T-803`: authenticated `/` still renders the dashboard.
- `T-804`: Lighthouse on `/home` returns 100 / 100 / 100 for accessibility, best practices and SEO.
- `T-805`: desktop and narrow-mobile browser checks; the hero, detailed preview, six feature cards,
  five reasons and trust strip stay readable and no horizontal scrollbar appears.
- `T-806`: the reference's customer, country and uptime figures are visibly marked `*` and footnoted
  as illustrative marketing metrics, not verified production claims.

### Build 0.9 additions

- `T-901`: grouped Tally-style top navigation renders Transactions, Books, Reports, Tax Returns,
  Masters and Settings as dropdown parents, with credit/debit notes, GST working papers,
  ledger/cash book/bank book and the existing reports inside the correct groups.
- `T-902`: `/reports/cash-book` renders the cash account book from posted journal lines with
  opening, receipts, payments and closing balance.
- `T-903`: `/reports/bank-book` renders the bank account book from posted journal lines with
  opening, receipts, payments and closing balance. The old Tax Returns parent in `T-901` is
  superseded by Build 0.10's single Reports parent.

### Build 0.10 additions

- `T-1001`: `/ledger` lists every account by type, shows Dr/Cr balances, opens the selected
  account's full ledger, and exposes the inline add-account form for permitted roles.
- `T-1002`: account creation validates code/name/type, rejects duplicates, audits
  `account.create`, and redirects to the new ledger.
- `T-1003`: `/accounts` returns 403 for a read-only member; `account.manage` is granted only to
  owner, admin and accountant.
- `T-1004`: `/bank-accounts` creates an asset ledger plus full bank details atomically, rejects
  duplicate codes and bad IFSC, lists the legacy 1010 account, and links Bank Book/Reconciliation.
- `T-1005`: a new bank account opens in Bank Book with its full details and in Bank Entry with the
  account preselected.
- `T-1006`: `/entries/cash`, `/entries/bank` and `/entries/journal` render separate entry modes;
  cash and bank controls are preselected, and posting redirects to the affected ledger.
- `T-1007`: a posted manual journal can be reversed only with permission and a reason; the
  original is marked reversed, a mirrored entry is posted, and `journal.reverse` is audited.
- `T-1008`: grouped navigation has Dashboard plus Transactions, Entries, Books, Reports, Masters
  and Settings; the old Tax Returns parent is absent and all report/GST links are under Reports.
- `T-1009`: dashboard cash includes cash 1000 plus every linked bank account.
- `T-1010`: ledger balances show Dr/Cr by normal side; zero balances stay plain `₹0.00`.
- `T-1011`: setting a debit opening balance posts a balanced journal to the selected account and
  the auto-created `3200 Opening Balance Equity`; the trial balance remains balanced.
- `T-1012`: a credit opening balance on a liability posts the expected credit to the account and
  debit to Opening Balance Equity.
- `T-1013`: a duplicate opening balance is rejected; after a permission-controlled reversal with a
  reason, a replacement opening balance can be posted and only the replacement remains effective.
- `T-1014`: an opening balance dated after the account's first posted transaction is rejected, while
  a date on or before the first activity is accepted.
- `T-1015`: zero/negative amounts, invalid sides and future dates are rejected; the account page
  exposes the form before and after account creation and the web flow posts, reverses and re-posts
  an opening balance.
- `T-1016`: creating a debtor account with a full company/contact/GSTIN/PAN/CIN/industry/credit
  profile and an opening balance saves one atomic profile, links a customer sub-ledger, tags the
  opening line with the party and keeps the trial balance balanced.
- `T-1017`: an invoice and receipt for a linked debtor post to that debtor's ledger, clear the party
  statement and leave the control total consistent; the equivalent vendor bill/payment path is
  covered for a linked creditor.
- `T-1018`: incompatible group/type, bad GSTIN, loan without a lender, bank without bank details
  and an invalid opening date are rejected without leaving partial accounts or parties behind.
- `T-1019`: profile edit updates the ledger name, profile and linked customer/vendor details,
  preserves the group, never changes posted amounts and writes `account.update`.
- `T-1020`: a bank account created through the Account 360 form saves bank/IFSC/branch/holder and
  opening balance, appears in Bank Book, and a loan account saves lender/account/sanction/maturity/
  interest/tenure/EMI/security.
- `T-1021`: the product master saves category, brand, barcode, HSN/SAC, MRP, cost, margin, GST,
  stock, tracking and sales ledger; a blank sale price is computed as cost + margin; MRP below the
  sale price is rejected.
- `T-1022`: percentage parsing accepts whole/decimal percentages into basis points and rejects
  floats and more than two decimal places; the new `account_profile` table is included in backup
  row-count verification.
- `T-1023`: an existing database whose `account`, `customer`, `vendor` and `item` tables predate
  Account 360 upgrades cleanly, gains the new columns and then the indexes that depend on them, and
  keeps its rows.
- `T-1024`: running `init_db` twice on that database is idempotent and leaves exactly one
  `account_profile` and `bank_account` table.
- `T-1025`: creating a Sundry Debtors ledger with the name of an existing customer links that
  customer to the new ledger and preserves phone, GSTIN, email, address, state and credit terms that
  were left blank on the account form.
- `T-1026`: the new-account form exposes one Account type / group selector containing cash, bank,
  debtors, creditors, inventory, fixed assets, loans, tax, suspense, capital, drawings, retained
  earnings, P&L, purchase, sales, depreciation and other classifications; posting only
  `group_code=suspense` stores a liability account, and the form no longer posts a separate `type`
  field.

### Build 0.11 additions

- `T-1027`: `/ledger/opening-balances` previews a CSV with `code, side, amount, as_of, note`,
  normalises Dr/d and Cr/c, shows row status and Dr/Cr totals, and writes nothing until Post all;
  the downloadable template has the required headers.
- `T-1028`: bulk import rejects a missing/duplicate header, empty file, duplicate code, unknown or
  non-postable account, malformed or non-positive amount, invalid side, future date, locked period,
  date after first activity, existing opening and the Opening Balance Equity account, reporting every
  bad row without posting a good one.
- `T-1029`: posting a valid file creates one balanced opening journal per account against Opening
  Balance Equity, appends the CSV note to narration, writes `opening_balance.set` per account plus one
  `opening_balance.bulk_import`, and keeps the trial balance balanced; re-posting the same file is
  rejected and does not duplicate entries.
- `T-1030`: a simulated failure on the second row rolls back the first row, the Opening Balance Equity
  account and the bulk-import audit; codes that exist only in another tenant are rejected; the page
  requires `account.manage` and appears under Books → Ledgers.
- `T-1031`: the signed-in workspace stylesheet has four light palettes — Ocean, Emerald, Violet and
  Sunset — plus a white topbar, neutral charcoal ink `#212529`, electric-blue default accents and
  success green; no `#0B1F3A` / `#04162F` navy token or legacy ivory/emerald/gold token is present in
  the app CSS; the workspace logo keeps the cyan/blue mark and printed documents resolve their colours
  from the theme variables rather than a hard-coded blue. It also checks the four `LANDING_THEMES`
  dark variants, the `--lp-*` landing variables, the visible Colour picker, the Royal Violet
  landing document and Ocean fallback for an invalid theme key.
- `T-1032`: a signed-in user can open Settings → Appearance, see all four palette cards, save a
  different palette, and get the new `data-theme` on the dashboard, sign-in page and invoice print;
  the choice persists in `user.theme`, writes one `user.theme_updated` audit event, rejects an
  unknown palette with HTTP 400, and the test restores Ocean. The same test requests
  `/home?theme=emerald`, checks the landing `data-theme` and hero tokens, confirms the cookie keeps
  Emerald on the next `/home` request, then restores Ocean.
- `T-1033`: a zero-balance ordinary ledger can be archived with a reason, writes
  `account.archive`, keeps its history and becomes non-postable; restore clears the archive state,
  writes `account.restore`, and makes it postable again.
- `T-1034`: archiving is rejected for a non-zero balance, a system/control account, a
  customer/vendor-linked ledger (including a legacy pointer without `account_profile`) and an income
  ledger referenced by products; the error names the guard rail instead of partially changing data.
- `T-1035`: merging two expense ledgers with balances posts one balanced `source_type='merge'`
  journal for the source's net balance, leaves the source ledger at zero and archived, combines the
  target balance, preserves the trial balance and keeps profit & loss total expense unchanged.
- `T-1036`: merge rejects different accounting types, different customer/vendor parties, bank to
  non-bank combinations, a system/control source or target, and an archived source or target;
  posting into the archived source is rejected with `ACCOUNT_ARCHIVED`.
- `T-1037`: merging income ledgers repoints products to the target sales ledger; merging a
  same-party ledger repoints the customer/vendor account pointer; archived bank ledgers disappear
  from the Bank Book account list; opening-balance import rejects an archived account.
- `T-1038`: the HTTP ledger page exposes **Archive or merge**, shows the all-time balance and
  compatible target choices, posts a merge, shows the archived source with its merged target,
  archives a second ledger, blocks a journal into it, restores it, and locks the cash control
  account page (`test_web.test_39`).
- `T-1039`: the analytics registry exposes the required actual-only metric keys with a written
  formula, `report.view` permission and drill-down, and contains no forecast/estimate kind
  (`tests/test_analytics.py`).
- `T-1040`: the snapshot's revenue, expense, profit, cash+bank, trial-balance and balance-sheet
  checks reconcile to the posted journal rows and existing report functions; freshness carries the
  entry count and last entry date.
- `T-1041`: the monthly series returns every month in the range, zero-fills a month with no
  postings, and its totals equal the posted income and expense actuals.
- `T-1042`: expense composition ranks expense accounts correctly; top customers ranks posted
  invoices by net sales and invoice count.
- `T-1043`: analytics is tenant-scoped (a second tenant sees zeroes/empty lists); invalid dates raise
  `BAD_DATE` and a reversed period raises `BAD_PERIOD`.
- `T-1044`: `v_analytics_journal` row count equals the tenant's journal-line count and
  `v_analytics_monthly` income/expense totals equal the posted actuals.
- `T-1045`: HTTP analytics requires sign-in (`401` JSON), then serves the catalog and overview for a
  member with `report.view`, returns `400 BAD_DATE` for a bad date, renders the Analytics Overview
  page, and falls back to the default period with a visible error (`test_web.test_40`).
- `T-1046`: the real `.xlsx` workbook opens with 20 expected sheets, contains native Excel charts,
  preserves exact integer-paise KPI source values beside displayed INR amounts, stays actuals-only
  and rejects an inverted period (`tests/test_excel.py`, `test_web.test_41`).
- `T-1047`: the Power BI import ZIP contains the manifest, analytics JSON, metric catalog,
  journal/monthly facts, account/party dimensions, Power Query starter and README; manifest hashes
  match the files, money stays integer paise, and a second tenant cannot leak into the pack
  (`tests/test_bi.py`, `test_web.test_42`).
- `T-1048`: the Analytics page serves the locally vendored ECharts asset, renders the actual monthly
  and expense-composition chart containers with fallback tables, and makes no external CDN request
  (`test_web.test_43`).
- `T-1049`: the insights endpoint is deterministic (`engine=deterministic_rules_v1`,
  `generative_ai=false`, `actuals_only=true`, `forecast_included=false`), every observation carries
  a written basis and metric keys, and an empty period says "not generated" rather than inventing
  a finding (`tests/test_insights.py`, `test_web.test_44`).
- `T-1050`: a real `.xlsx` upload is parsed server-side into neutral CSV for opening balances, bank
  statements and GSTR-2B; dates and decimals survive, cached formula values are used, blank rows and
  trailing empty columns are dropped, oversized/malformed files fail visibly, and the existing
  preview/confirm rules still control posting (`tests/test_xlsx_import.py`, `test_web.test_45`).
