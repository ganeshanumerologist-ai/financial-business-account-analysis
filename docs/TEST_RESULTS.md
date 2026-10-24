# ARTHIVIO — Test Results

| Field | Value |
|---|---|
| Run ID | `RUN-2026-10-24-01` |
| Date | 2026-10-24 |
| Type | Baseline audit run (read-only) |
| Environment | Windows, Python 3.14.6, no Node / git / PostgreSQL / Docker |
| Tests executed | 12 (audit-time checks only) |
| Application tests executed | **0** |
| Result | **5 PASS · 6 FAIL · 1 BLOCKED** |

> Read this first: **no application feature was tested, because no application exists.** Every module-level row below is `BLOCKED`, not `PASS`. A pass here would be a fabrication and is explicitly prohibited by audit rule 6.

---

## 1. Audit-time checks (actually executed)

| ID | Test | Expected | Actual | Status | Evidence |
|---|---|---|---|---|---|
| A-001 | Application source exists | Source tree present | Only 2 image files; no `src/`, `app/`, `lib/` | **FAIL** | Recursive listing, `docs/SOFTWARE_AUDIT.md` §2.2 |
| A-002 | Dependency manifest exists | `package.json` / `requirements.txt` / `pyproject.toml` | None found | **FAIL** | File scan of workspace |
| A-003 | Test suite exists | `tests/` with runnable tests | None found | **FAIL** | File scan |
| A-004 | Git repository present in workspace | `.git` exists, `git status` runs | `.git` absent. Portable git 2.56.0 **is** available at `C:\Users\vicky\git-portable` and runs when called by path | **FAIL** | `Test-Path .git` → False; `git --version` → 2.56.0.windows.2 |
| A-005 | Node toolchain available | `node -v` succeeds | `node -v` → v20.20.2, `npm -v` → 10.8.2 (portable, off-`PATH`) | **PASS** | Session `PATH` prefix + literal output |
| A-006 | PostgreSQL available | `psql --version` succeeds | Command not found; no server installed | **BLOCKED** | `Get-Command psql/postgres` → nothing |
| A-007 | Secrets committed | None | None found | **PASS** | No `.env`/key files in workspace |
| A-008 | Real customer/bank data present | None | None found | **PASS** | Workspace contains only images |
| A-009 | Governing spec locatable | File readable at known path | Found, 763 lines, hash `4556C714…` | **PASS** | `Get-FileHash`, `Get-Content` |
| A-010 | Mockups meet design constraints (§4/§5) | Compliant | City-photo hero; unsupported stats | **FAIL** | Visual review; see B-004, B-005 |
| A-011 | Mockup resolution sufficient for 8K/retina | ≥ 3840 px wide | 1536 × 1024 | **FAIL** | PNG IHDR / JPEG SOF parse |
| A-012 | Remote repository inspected | Contents known and recorded | Public repo; 1 file `README.md` (144 B); 2 commits; **no code, no theme** | **PASS** | GitHub contents + commits API |

**Note on the six FAILs:** five describe *absence of build artefacts* in an empty project (A-001/002/003/004/011) and one describes design-spec non-compliance (A-010). None is a runtime bug in shipped software — there is no shipped software. They are recorded honestly as failures of the audit's expectations, and mapped to defects B-001…B-009.

---

## 2. Feature test matrix — application functionality

Every row: expected result comes from the spec; actual result is unobservable; status is `BLOCKED`; evidence explains why.

### 2.1 Public site and UI

| Feature | Expected result | Actual result | Status | Evidence | Severity |
|---|---|---|---|---|---|
| Home page renders with headline/CTA | Renders, responsive, accessible | Nothing to load | BLOCKED | No code; mockups are flat images | Critical |
| Nav links (9 public pages) | All reachable, no dead links | No pages exist | BLOCKED | No routes defined | High |
| Dashboard nav (12 items) | Reachable, role-filtered | No routes exist | BLOCKED | No code | Critical |
| KPI tiles | Match ledger-derived values | No UI, no data | BLOCKED | — | Critical |
| Revenue/Profit charts | Accurate, high-DPI sharp | No chart library installed | BLOCKED | No deps installed | High |
| Date-range filter | Correct inclusive boundaries | No filter existed | BLOCKED | — | High |
| Empty / error / offline states | All present and clear | Not implemented | BLOCKED | — | Medium |
| Responsive 360→4K | No clipping, readable | Not implemented | BLOCKED | — | Medium |
| i18n EN/HI | All strings translated | Not implemented | BLOCKED | — | Medium |

### 2.2 Accounting

| Feature | Expected result | Actual result | Status | Evidence | Severity |
|---|---|---|---|---|---|
| Double-entry posting | Rejects unbalanced; atomic | No engine | BLOCKED | No journal code | Critical |
| Trial balance | Debits == credits | No report | BLOCKED | — | Critical |
| P&L | Reconciles to ledger | No report | BLOCKED | — | Critical |
| Balance sheet | A = L + E | No report | BLOCKED | — | Critical |
| Cash flow | Closing cash == BS cash | No report | BLOCKED | — | Critical |
| General ledger | Opening + movements = closing | No report | BLOCKED | — | Critical |
| AR/AP subledgers | Equal control accounts | Not implemented | BLOCKED | — | Critical |
| Opening balances | Carried correctly, once | Not implemented | BLOCKED | — | Critical |
| Rounding policy | Deterministic, sum preserved | Not implemented | BLOCKED | — | High |
| Period lock | Rejects postings to locked period | Not implemented | BLOCKED | — | High |
| Reversal/correction | Mirror entry, posted rows immutable | Not implemented | BLOCKED | — | Critical |
| Multi-currency | Rate applied, gain/loss posted | Not implemented | BLOCKED | — | Medium |
| Depreciation / EMI | Schedules match formulas | Not implemented | BLOCKED | — | Medium |

### 2.3 Billing, inventory, offline

| Feature | Expected result | Actual result | Status | Evidence | Severity |
|---|---|---|---|---|---|
| Invoice create/post | Stock + AR + tax + GL atomic | No module | BLOCKED | — | Critical |
| Tax calculation | Per-line, HSN/SAC mapped | No module | BLOCKED | — | Critical |
| Invoice numbering | Unique per tenant/FY, gap policy | No module | BLOCKED | — | High |
| Duplicate invoice | Rejected / idempotent | No module | BLOCKED | — | Critical |
| A4 + 58/80 mm print | Correct layouts | No module | BLOCKED | — | Medium |
| Stock movement ledger | Every movement traceable | No module | BLOCKED | — | High |
| Stock closing formula | Matches spec §11 formula | No module | BLOCKED | — | Critical |
| Barcode scan/label | Works with scanner input | No module | BLOCKED | — | Medium |
| Offline queue + sync | Idempotent, no dup postings | No module | BLOCKED | — | High |
| Conflict detection | Surfaced, never silent overwrite | No module | BLOCKED | — | High |

### 2.4 Reports, imports/exports, security, backups

| Feature | Expected result | Actual result | Status | Evidence | Severity |
|---|---|---|---|---|---|
| ≈150 report templates | Defined source + formula + drill-down | 0 implemented | BLOCKED | — | High |
| Report total vs ledger | Equal (independent recalc) | No reports | BLOCKED | — | Critical |
| Stale-data flag | Shown when data old | Not implemented | BLOCKED | — | Medium |
| CSV import | Validate, preview, all-or-nothing | No importer | BLOCKED | — | High |
| Excel import/export | Correct types, totals preserved | No handler | BLOCKED | — | High |
| PDF export | Complete layout, no clipping | No generator | BLOCKED | — | Medium |
| Invalid input handling | Clear errors, no crash | No input path | BLOCKED | — | High |
| Tenant isolation | 403 on cross-tenant access | No server | BLOCKED | — | Critical |
| RBAC enforcement | Denied server-side | No server | BLOCKED | — | Critical |
| Audit log | Append-only, complete | Not implemented | BLOCKED | — | High |
| Secrets in env only | Never in source/logs | Nothing yet; clean baseline | BLOCKED | A-007 PASS for current files | High |
| Backup + verified restore | Restore reproduces data | No data store | BLOCKED | — | Critical |
| Export permissions | Enforced, no leak | No export path | BLOCKED | — | High |

---

## 3. Commands run in this run

```powershell
Get-ChildItem -Force
Get-ChildItem -Recurse -Depth 2 -Force -Directory
Get-ChildItem -Force -Recurse | Select-Object FullName, Length
Get-ChildItem "D:\" -Force -Directory
Get-ChildItem "$env:USERPROFILE\Desktop","$env:USERPROFILE\Downloads","$env:USERPROFILE\Documents"
foreach($t in @("node","npm","npx","git","psql","postgres","pnpm","yarn","docker")){ Get-Command $t }
Get-ChildItem "C:\Program Files\nodejs" -ErrorAction SilentlyContinue
python -c "import sys; print(sys.version)"
python -m pip --version
python -m pip list | Select-String "fastapi|uvicorn|jinja|sqlalchemy|pydantic|alembic|pytest|openpyxl|pandas|reportlab|bcrypt|passlib|httpx"
Get-PSDrive D
Get-FileHash "…WITH_RULES.md","…WITH_RULES (1).md" -Algorithm SHA256
python <PNG IHDR / JPEG SOF dimension parse>
# --- second pass, after deeper inspection ---
$env:PATH="C:\Users\vicky\git-portable\cmd;C:\Users\vicky\git-portable\usr\bin;C:\Users\vicky\node-portable\node-v20.20.2-win-x64;$env:PATH"
git --version; node -v; npm -v
Get-ChildItem C:\Users\vicky,D:\ -Recurse -File -Include *.html,*.css  # (timed out at depth; re-run depth-limited)
Get-ChildItem C:\Users\vicky\Desktop,"C:\Users\vicky\Documents" -Recurse -Depth 3 -Include *.html,*.css
Get-Content "C:\Users\vicky\Documents\Default Project\.git\config"
curl https://api.github.com/users/ganeshanumerologist-ai/repos
curl https://api.github.com/repos/ganeshanumerologist-ai/financial-business-account-analysis/contents/
curl https://api.github.com/repos/ganeshanumerologist-ai/financial-business-account-analysis/commits
```

**Commands not run because they do not exist:** `npm test`, `npm run build`, `npm run lint`, `pytest`, `tsc`, `alembic upgrade`, any deploy command. The absence is the finding; no substitute command was invented.

---

## 4. Summary

| Category | Count |
|---|---|
| Audit-time checks executed | 12 |
| — PASS | 5 |
| — FAIL | 6 |
| — BLOCKED | 1 |
| Application-level test cases defined in `TEST_PLAN.md` | 78 |
| — of those executed | 0 |
| — Executed | 0 |
| — Blocked (no code) | 38 inventory groups covering all modules |
| — PASS | **0** |
| Reports whose totals were verified against transactions | **0** (unverifiable — no reports, no transactions) |

**Report accuracy assessment:** *not measurable.* No report exists. Any statement that totals reconcile would be false.

---

## 5. Honest conclusion

The software cannot be described as working, partially working, or broken at the feature level. It does not exist yet. The audit's value is the enforceable baseline: environment constraints identified, spec conflicts caught before they were coded, defects logged, and an 89-case test plan waiting to be executed.

Next step is an owner decision on stack and system installs, then Phase 1 implementation with the security and accounting gates in `docs/TEST_PLAN.md` §8.


---

## 6. Application run `RUN-2026-10-24-02` — first implementation slice

| Field | Value |
|---|---|
| Date | 2026-10-24 |
| Type | Automated unit + end-to-end HTTP tests (real server, temporary SQLite DB) |
| Command | `python -m unittest discover -s tests` |
| Environment | Windows, Python 3.14.6, SQLite (stdlib), zero pip packages |
| Tests | **42 executed, 42 passed, 0 failed** (~3.4 s) |
| Verdict | Accounting core and the Phase 1 security controls verified for this build |

### 6.1 What was actually executed

| Suite | Tests | Verified behaviour |
|---|---|---|
| `TestMoney` | 5 | float rejection, 2-dp validation, half-up tax rounding, largest-remainder allocation sums exactly |
| `TestPosting` | 6 | unbalanced entries rejected with no rows written, one-sided lines enforced, idempotency, period lock, cross-tenant account rejection |
| `TestInvoice` | 7 | CGST/SGST split, IGST for inter-state, COGS + stock decrement, negative-stock block, discount guard, round-off posting, invoice idempotency, service-revenue classification |
| `TestReports` | 8 | TB totals equal raw journal sums, balance sheet A = L + E, P&L matches ledger, running balances, reversal nets to zero, customer statement equals AR control, cross-tenant ledger/statement blocked |
| `TestSecurity` | 5 | scrypt hash/verify, weak-password rejection, session issue/revoke, lockout after 5 failures, RBAC denial, missing-membership denial |
| `test_web.WebTest` | 9 | login required, bad password 401, dashboard renders without None/NaN, report pages render and balance, invoice creation through the form flows into reports, CSRF 403, customer creation, cross-tenant invoice hidden, customer statement links to invoices |

### 6.2 Defects found and fixed during this run

| ID | Symptom | Root cause | Fix | Regression test |
|---|---|---|---|---|
| B-010 | Duplicate `JV-00001`, `UNIQUE constraint failed` on the second posting | `sequence` row inserted with `next_no = 1`, so the next call returned 1 again | Insert with `next_no = 2` | `TestPosting.test_balanced_posts_and_tb_balances` and all invoice tests |
| B-011 | Customer statement rows did not link to invoices | Journal entry created before the invoice row, so `source_id` stayed `NULL` | Update `journal_entry.source_id` inside the invoice transaction | `test_web.test_09_customer_statement` |
| B-012 | Demo inventory negative; service revenue posted to Sales | No opening-stock journal; invoices always credited account 4000 | Opening inventory posted; per-item `revenue_code` (4000 goods / 4100 services) | `test_service_item_posts_to_service_revenue` |

### 6.3 Verified by manual browser check

Dashboard, invoices list, invoice detail, trial balance, P&L, balance sheet, customers and
customer statement were opened in a real browser against the seeded demo books. Observed:
TB totals equal on both sides (₹11,57,502.32), balance sheet badge `A = L + E`, P&L net
profit ₹63,169.43 matching the balance sheet's retained-earnings line, customer balances
summing to the AR control account (₹2,32,282.00).

### 6.4 Explicitly NOT verified

Payments/receipts, purchases/AP, credit notes, GST returns, exports/PDF, backup/restore,
multi-user invitations, PostgreSQL, concurrency/load, penetration testing, the Next.js UI,
accessibility audit, and behaviour under real data volumes. These remain open and are not
claimed anywhere.


---

## 7. Application run `RUN-2026-10-24-03` ? receipts, purchases, credit notes, GST, backup

| Field | Value |
|---|---|
| Date | 2026-10-24 |
| Type | Automated unit + end-to-end HTTP tests, plus a real-browser walkthrough and a backup/restore drill |
| Command | `python -m unittest discover -s tests` |
| Environment | Windows, Python 3.14.6, SQLite (stdlib), zero pip packages |
| Tests | **75 executed, 75 passed, 0 failed** (~9 s) |
| Verdict | Sales cycle, purchase cycle, returns, GST summary, day book, exports and backup verification work end-to-end for this build |

### 7.1 What was actually executed

| Suite | Tests | Verified behaviour |
|---|---|---|
| `TestMoney` | 5 | float rejection, 2-dp validation, half-up tax rounding, largest-remainder allocation |
| `TestPosting` | 6 | unbalanced rejection, one-sided lines, idempotency, period lock, cross-tenant rejection |
| `TestInvoice` | 8 | CGST/SGST split, IGST, COGS + stock decrement, negative-stock block, discount guard, round-off, idempotency, service revenue |
| `TestReports` | 8 | TB totals, balance sheet, P&L, ledger running balances, reversal, statements, tenant isolation |
| `TestSecurity` | 6 | scrypt, weak password, session revoke, lockout, RBAC, membership |
| `TestReceipts` | 7 | full receipt clears AR, partial receipt, over-allocation rejected, allocations cannot exceed amount, idempotent receipt, cross-tenant invoice rejected, statement includes receipt |
| `TestBills` | 7 | input GST, stock in, weighted average cost, purchase at current cost keeps average, vendor payment clears AP, overpayment rejected, inter-state IGST, service item leaves stock untouched |
| `TestCreditNotes` | 4 | full return reverses sale/GST/COGS and restores stock, partial return, over-credit rejected, reason required |
| `TestAgeingAndGST` | 4 | receivable buckets, payable buckets, GST output vs input nets to zero, day book lists all vouchers |
| `TestBackup` | 5 | backup verified and recorded, restore verification matches source, corrupt file fails, row tampering detected, missing DB raises |
| `test_web.WebTest` | 15 | login/CSRF/RBAC, invoice flow, receipt through the form reduces outstanding by exactly the amount, bill + vendor payment, credit note, four CSV exports, ten new pages render, backup over HTTP |

### 7.2 Defects found and fixed during this run

| ID | Symptom | Root cause | Fix | Regression test |
|---|---|---|---|---|
| B-013 | Weighted-average cost fell sharply after a purchase (TRD-001 92000 ? 62352 paise) | Purchase taxable value is paise for the whole line, while stock is held in thousandths; the two were added without unit conversion | Convert purchase value to milli-paise (`taxable * 1000`) before averaging | `TestBills.test_weighted_average_cost`, `test_purchase_at_current_cost_keeps_average` |
| B-014 | Service item stock drifted negative (`SRV-001` ?20 units) | Invoices decremented stock for every item, ignoring `track_stock` | Decrement only when `track_stock` is set | `TestBills.test_service_invoice_does_not_touch_stock` |
| B-015 | Replaying an identical receipt failed with "exceeds outstanding" instead of returning the original | Allocation validation ran before the idempotency lookup | Look up the stored payment by key before validating allocations | `TestReceipts.test_receipt_idempotent` |
| B-016 | Invoice/bill/receipt posting could leave an orphan journal if the document insert failed | Journal committed in its own transaction before the document row | Composite operations now open one transaction; `post_journal` uses a savepoint when already inside one | `TestPosting`, `TestReceipts`, `TestBills`, `TestCreditNotes` (all pass) |

### 7.3 Verified demo figures (seeded synthetic books, as of 2026-10-24)

| Check | Value |
|---|---|
| Trial balance | balanced, ?14,54,864.30 on each side |
| Net profit (FY) | ?63,011.23 |
| Receivables | ?1,26,310.02 across 8 open invoices |
| Payables | ?57,680.00 across 2 open bills |
| GST | output ?24,238.79, input ?12,090.00, net payable ?12,148.79 |
| Stock | no negative quantities; costs remain at purchase cost (92000 / 38000 / 14500 / 210000 paise) |
| Balance sheet | assets ?9,25,330.02 = liabilities + equity |

### 7.4 Backup / restore drill (executed)

| Field | Value |
|---|---|
| Command | `python scripts/backup.py` then `python scripts/restore_verify.py --backup backups/arthivio-20261024-160327.db` |
| Backup file | `backups/arthivio-20261024-160327.db` (372,736 bytes) |
| SHA-256 | `b31093d78ee9bd4c9cef7668c0569d08cfe2c64bb5cd1350dab842270410fb1b` |
| Checks | integrity `ok`, foreign keys `ok`, journals balanced, 20 tables, row counts match source |
| Result | **PASS** |

A second backup was created through the UI (`POST /backup`), returned the banner
"Backup created and verified", and was recorded in `backup_run`.

### 7.5 Verified by manual browser check

Dashboard, invoices, invoice detail, receipts, credit notes, bills, bill detail, vendors,
day book, journal, AR ageing, AP ageing, GST summary, backups and audit log were opened in a
real browser against the seeded books. A ?4,518.02 receipt was posted through the invoice
form; the page immediately showed `Outstanding ?0.00` and the receipt form disappeared.
The backup page created and verified a backup without leaving the UI.

### 7.6 Explicitly NOT verified

PDF invoices, e-invoicing/IRN, GSTR-1 JSON export, debit notes, multi-currency, fixed-asset
depreciation, bank reconciliation, payroll, multi-user invitation UI, PostgreSQL,
concurrency/load testing, penetration testing, the Next.js UI, accessibility audit, Hindi
localisation, and behaviour under real data volumes. These remain open and are not claimed.

Restores are verified but not automated as a one-click destructive operation; restoring is a
deliberate manual step.


## 8. Application run `RUN-2026-10-24-04` - settings, tax invoice print, GSTR-1 working export

### 8.1 What was actually executed

| Command | Result |
|---|---|
| `python -m unittest discover -s tests` | **87 tests, OK**, 8.5 s, Python 3.14.6, Windows |
| `python -m app.server` + browser checks | settings, print invoice, GST page, GSTR-1 CSV and JSON |
| In-place migration of `data/arthivio.db` | new tenant/customer columns added, existing rows preserved |

New tests added in this run:

- `tests/test_gstr1.py` - per-invoice tax split reconciliation, GSTR-1 totals vs posted
  invoices, B2B/B2C split, HSN summary reconciliation, credit-note section, missing-GSTIN
  warning, additive migration (legacy table + data preserved, idempotent re-run), amount in
  words.
- `tests/test_web.py` - settings validation and save, print invoice HTML, GSTR-1 CSV, GSTR-1
  JSON.

### 8.2 Verified demo figures (GSTR-1 working export, 2026-04-01 to 2026-10-24)

| Section | Taxable | CGST | SGST | IGST |
|---|---|---|---|---|
| B2B + B2C small (11 invoices) | 207,988.00 | 6,426.86 | 6,426.86 | 11,438.85 |
| Credit note CN-00001 | 448.20 | 26.89 | 26.89 | 0.00 |

- 12 B2B rate rows (9 registered invoices, two of them multi-rate), 1 B2C-small aggregate row.
- 5 HSN/SAC groups (6205, 6214, 7418, 9403, 998391).
- 2 invoices without buyer GSTIN are grouped as B2C small and flagged in warnings.
- The GST summary page shows **net** output tax after credit notes (CGST 6,399.97 +
  SGST 6,399.97 + IGST 11,438.85 = 24,238.79); the GSTR-1 export lists gross invoices and
  the credit note separately. Both reconcile: 6,426.86 - 26.89 = 6,399.97.

### 8.3 Print invoice verified in the browser

`INV-00011` (Northern Lights LLP, inter-state):

- seller GSTIN `27AABCS1429B1Z1`, buyer GSTIN `07AAFCN4321P1Z9`, place of supply `07 - Delhi`
- line: Interior Consulting 8.000 hour @ 2,500.00, HSN/SAC 998391, IGST 18% = 3,600.00
- taxable 20,000.00, invoice total 23,600.00, round off 0.00
- amount in words: "Twenty Three Thousand Six Hundred Rupees Only"
- bank details and terms printed; browser Print / Save as PDF button present

### 8.4 In-place schema migration (no data loss)

`db.init_db` now runs additive `ALTER TABLE ... ADD COLUMN` migrations for tenant profile
fields and customer address. Verified against a legacy-shaped tenant table and against the
existing demo database: existing rows and balances were unchanged, new fields defaulted to
empty, and a second `init_db` run made no further changes.

### 8.5 Defects found and fixed during this run

- `B-017` - web test selected the "latest" invoice by `created_at`, which is stored to the
  second; seeded and newly created invoices could tie and the test intermittently picked a
  fully paid invoice. Test now selects by document number (deterministic).
- `B-018` - GSTR-1 HSN aggregation omitted `rate_bp`, causing a `KeyError` in sorting. Fixed
  and covered by `test_hsn_summary_matches_totals`.

### 8.6 Explicitly NOT verified

- Upload to the GST portal or the official GSTR-1 JSON schema (this is a working CSV/JSON
  preparation aid, labelled as such in the file).
- Binary PDF generation (the browser's Print / Save as PDF is used; no PDF library).
- GSTR-3B, e-invoice/IRN, e-way bill, debit notes, bank reconciliation.
- Multi-user invitation UI, PostgreSQL, Next.js, load/penetration testing.


### 8.7 Backup / restore drill after the migration (executed)

| Item | Value |
|---|---|
| Backup file | `backups/arthivio-20261024-201058.db` |
| SHA-256 | `f6b563522547b774c28805b884ea317ea9b8d838169130ec3294d91ffc4ba7a4` |
| Size | 372,736 bytes |
| Integrity check | ok |
| Foreign-key check | ok |
| Journals balanced | 1 tenant |
| Tables present | 20 |
| Row counts vs source | match |
| Restore verification | **PASS** |

The backup was taken from the migrated demo database, proving the additive schema changes did
not break online backup or restore verification.
