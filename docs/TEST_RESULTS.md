# ARTHIVIO — Test Results

> **Current status: Build 0.12.** The latest application run is `RUN-2026-10-28-01` with
> **245 tests, OK**, Python 3.14.6, Windows - see section 25. The table immediately below is the original
> 2026-10-24 baseline audit of an empty workspace and is preserved as history, not current status.

| Field | Value |
|---|---|
| Baseline run ID | `RUN-2026-10-24-01` |
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


## 9. Application run `RUN-2026-10-24-05` - debit notes and bank reconciliation

### 9.1 What was actually executed

| Command | Result |
|---|---|
| `python -m unittest discover -s tests` | **120 tests, OK**, 7.6 s, Python 3.14.6, Windows |
| `python -m app.server` + browser checks | debit note on BILL-00003, debit-note list/CSV, bank CSV import, auto-match, unmatch, trial balance |
| In-place schema upgrade of `data/arthivio.db` | `debit_note`, `debit_note_line`, `bank_import`, `bank_statement_line` created; existing rows preserved |

New tests added in this run:

- `tests/test_debit_notes.py` (13) - partial/full purchase return, CGST/SGST vs IGST reversal,
  proportional discount reversal, non-stock return to purchases, over-return and second-return
  guards, reason required, insufficient stock, idempotency, vendor statement, GST summary net
  input, cross-tenant rejection, and a return after the bill was already paid (vendor credit).
- `tests/test_bank.py` (18) - CSV layouts (Debit/Credit, Amount+Dr/Cr, Withdrawal/Deposit),
  ISO and DD/MM/YYYY dates, preamble/blank lines, blank balance, bad date/header/empty errors,
  import dedup by SHA-256, reconciliation totals, exact-amount suggestions, manual
  match/unmatch, unambiguous auto-match, amount mismatch, wrong account, double match, period
  filter, and one ledger line matched to only one statement line.
- `tests/test_web.py` (+2) - debit note created from the bill page, list and CSV export; bank
  statement import, duplicate import, match and unmatch through the real HTTP server.

### 9.2 Debit note verified in the browser

`BILL-00003` (Loom House Pvt Ltd, 2026-08-10):

- returned 1 Gift Hamper at the bill's purchase value 2,100.00 + 18% GST = **2,478.00**
- bill outstanding reduced from **49,560.00 to 47,082.00**
- debit-note list shows `DBN-00001` with the reason; CSV export contains the note
- vendor statement now separates the movements:

| Movement | Amount |
|---|---|
| Billed (period) | 1,08,150.00 |
| Paid (period) | 58,590.00 |
| Debit notes (period) | 2,478.00 |
| Closing payable | **47,082.00** |

The vendor statement reconciles exactly: 1,08,150.00 - 58,590.00 - 2,478.00 = 47,082.00.

### 9.3 Bank reconciliation verified in the browser

Imported a two-line CSV for 2026-08-01 to 2026-08-30:

| Date | Description | Debit (out) | Credit (in) |
|---|---|---|---|
| 2026-08-30 | NEFT CR SUNDARAM TRADERS (NEFT-90114) | - | 15,938.00 |
| 2026-08-01 | NEFT DR NORTHERN CRAFTS (NEFT-84210) | 8,120.00 | - |

- import result: **2 new, 0 duplicate**
- auto-match: **2 matched, 0 ambiguous**; unmatched statement lines **0**
- one ledger line remained unmatched: office rent 8,000.00 on 2026-08-05, correctly shown as
  not present in the statement
- statement net 7,818.00; ledger net -182.00; difference -8,000.00, fully explained by the rent
- unmatch restored the line and the page showed "Match removed"

Matching never creates or edits a journal entry. It only links a statement line to an existing
posted bank journal line, so the ledger remains the source of truth.

### 9.4 Explicitly NOT verified

- Real bank CSV exports from every Indian bank; only the documented layouts and date formats
  are supported.
- Partial-amount matching, one-to-many matching, and auto-posting bank charges/interest as
  journal entries (unmatched statement lines are surfaced, not posted).
- GSTR-2 / GSTR-2B purchase reconciliation, GSTR-3B, GST portal upload, e-invoice/IRN.
- Multi-user invitation UI, PostgreSQL, Next.js, load/penetration testing.

---

## 10. Application run `RUN-2026-10-24-06` - GSTR-3B working summary and reconciliation

### 10.1 What was actually executed

| Command | Result |
|---|---|
| `python -m unittest discover -s tests` | **129 tests, OK**, ~8.3 s, Python 3.14.6, Windows |
| `python -m app.server` + browser checks | GSTR-3B page for October 2026 and June 2026; CSV fetch returned HTTP 200 |
| In-place schema check | no schema change was needed for this slice |

New tests added in this run:

- `tests/test_gstr3b.py` (8) - month boundary validation (including leap February), June output
  net of a credit note, October ITC reversal from a debit note, month filtering and document
  counts, empty-month safety, cross-tenant isolation, clean-book reconciliation, and a manual
  output-tax journal that is correctly flagged as a ledger mismatch.
- `tests/test_web.py` (+1) - GSTR-3B page renders the 3.1/4/5 sections and 6/6 checks, CSV export
  contains the working sections, and an invalid month shows the YYYY-MM error instead of crashing.

### 10.2 GSTR-3B verified in the browser

October 2026 (two invoices and the demo purchase return `DBN-00001`):

| Figure | Value |
|---|---|
| Net taxable value | 37,382.00 |
| Output tax (IGST + CGST + SGST) | 5,378.84 |
| Eligible ITC (purchase bills less debit notes) | -378.00 |
| ITC reversal in excess of available ITC | 378.00 |
| Cash payable in this working view | 5,756.84 |
| Reconciliation checks | 6 / 6 OK |

June 2026 (two invoices and credit note `CN-00001`):

| Figure | Value |
|---|---|
| Net taxable value | 32,876.80 |
| Output tax | 4,341.69 |
| CGST / SGST | -26.89 each |
| Cash payable in this working view | 4,395.47 |
| Output tax carried forward | 53.78 |
| Reconciliation checks | 6 / 6 OK |

The negative CGST/SGST in June is shown with an explicit warning: the credit note was intra-state
while June invoices were inter-state, so those heads are carried forward and are not set off
against IGST. The October negative ITC is shown as an excess reversal payable, with a warning.
The CSV download returned HTTP 200 with `text/csv` and the expected 3.1(a), ITC and reconciliation
rows.

### 10.3 Explicitly NOT verified

- GSTR-3B is a **preparation aid, not a filed return**. No GST portal upload, no official JSON
  schema, no challan or acknowledgment.
- Set-off is head-wise only: IGST credit is not cross-utilised against CGST/SGST.
- RCM, zero-rated, nil-rated/exempt and import ITC are not modelled. GSTR-3B does not consume
  GSTR-2B; the separate working comparison on `/gstr2b` reports the gap without posting it.
- The ledger reconciliation check is expected to flag any manual journal or GST payment posted
  to the tax control accounts; that is a review signal, not automatic correction.
- Multi-user invitation UI, PostgreSQL, Next.js, load/penetration testing.

## 11. Application run `RUN-2026-10-25-01` - team access, statement sharing and GSTR-2B

### 11.1 What was actually executed

| Command | Result |
|---|---|
| `python -m unittest discover -s tests` | **156 tests, OK**, 12.4 s, Python 3.14.6, Windows |
| `python -m app.server` + browser checks | `/users` rendered; `/gstr2b?month=2026-08` imported and matched; duplicate-file redirect returned the existing period |
| Live GSTR-2B August 2026 | 1 portal line, ITC 7,560.00, posted bills 7,560.00, matched 1, difference 0.00, bill BILL-00003 |
| Live GSTR-2B CSV | `/export/gstr2b.csv?month=2026-08` HTTP 200 with 2B rows and summary |
| Backup drill | `backups/arthivio-20261025-081038.db`, SHA-256 `6176a27dc31fb590b67ee075936defe017ef819cd1e6f69937978e6ff5a6eea1`, 5/5 checks, restore **PASS** |
| Lighthouse | GSTR-2B **100 / 100 / 100**, Team **100 / 100 / 100**, public statement **100 / 100 / 100** (accessibility / best practices / SEO); no failed audits |

New tests added in this run:

- `tests/test_gstr2b.py` (12) - preamble/alias parsing, invoice normalisation, bad GSTIN/date,
  empty/no-header, exact match, mismatch reported without editing the bill, missing both
  directions, prior-period match, duplicate/supersede history, duplicate-file period, cross-tenant
  isolation and invalid month.
- `tests/test_team_sharing.py` (11) - new-user invite/accept/login, duplicate invite revocation,
  existing-user current password, owner/self guards, admin role change, suspend session
  revocation, expired/revoked invites, active-member duplicate, statement scope/view count,
  revoke/expiry, bad party/date, and statement totals equal the accounting report.
- `tests/test_web.py` (+4) - invite creation/accept/auto-login/role change, share creation/public
  print/revoke, GSTR-2B import/export/duplicate/invalid CSV, and business switch membership guard.

### 11.2 GSTR-2B verified in the browser

August 2026, working CSV containing `LH-2026-097` for Loom House Pvt Ltd
(`27AAACL1234C1Z5`):

| Figure | Value |
|---|---|
| GSTR-2B taxable | 42,000.00 |
| GSTR-2B tax | 7,560.00 |
| Posted purchase-bill taxable | 42,000.00 |
| Posted purchase-bill tax | 7,560.00 |
| Matched lines | 1 |
| 2B tax minus books tax | 0.00 |
| Matched bill | BILL-00003 |

Re-importing the same file while viewing October redirected to August with `duplicate=1` and
added no rows. Only the duplicate notice is shown (no contradictory "Imported 0 rows" banner),
and the import audit/history row remained visible.

### 11.3 Team and sharing evidence

The HTTP suite runs the real server against a temporary SQLite database. It verifies invite
creation via `/users`, public acceptance via `/invite/<token>`, auto-login, role change, and
business switching. It verifies a statement share created from a customer page, opens the public
`/share/statement/<token>` print view without a session, checks `noindex`, revokes the link, and
confirms the revoked link returns HTTP 404.

Live browser check on 2026-10-25: created a 7-day share for Sundaram Traders from
`/customers/<id>`, opened the public print page (closing balance 30,161.00, amount in words,
business/customer GSTIN and bank details), then revoked it. Reloading the same link returned the
`Statement unavailable` page. A GSTR-2B import was also created live for August 2026, and the
duplicate-file path was checked. Team-page browser inspection confirmed the member/invite layout;
invite acceptance and role changes are proven by the HTTP E2E suite, not by an email-delivery
integration (none exists).

### 11.4 Explicitly NOT verified

- No email is sent for invites or statements; links are copied manually. No ownership transfer,
  per-permission editor, SSO, official GSTR-2B portal format or GST portal upload.
- GSTR-2B is a **working reconciliation aid, not a filed return**. It never posts ITC, edits a
  bill or corrects an amount difference automatically.
- No partial/one-to-many bank matching, auto-posting of bank charges/interest, Excel export,
  PostgreSQL, Next.js, load or penetration testing.
- The statement share is a bearer link: anyone who has it can view that one statement until it
  expires or is revoked.

## 12. Application run `RUN-2026-10-25-02` - ITC review and GSTR-3B vs GSTR-2B

### 12.1 What was actually executed

| Command | Result |
|---|---|
| `python -m unittest discover -s tests` | **162 tests, OK**, 11.2 s, Python 3.14.6, Windows |
| Browser, `/gstr2b?month=2026-08` | August 2026 showed 1 open review and a 3B-vs-2B comparison of 7,560.00 vs 7,560.00, difference 0.00 |
| Browser, `POST /gstr2b/review` | set `accepted` with note `Matched to BILL-00003`; redirected with `reviewed=1`; page showed open reviews 0, accepted 7,560.00, amount badge **AMOUNT OK**; books and 2B amounts unchanged |
| HTTP E2E in `test_24` | review POST + redirect, rendered state/note/comparison, and CSV columns for review and 3B-vs-2B |
| Live CSV fetch | `/export/gstr2b.csv?month=2026-08` returned 16 columns, `accepted` + `Matched to BILL-00003`, review totals and the comparison summary |
| Lighthouse, GSTR-2B page | **100 / 100 / 100** accessibility / best practices / SEO; no failed audits |
| Backup drill | `backups/arthivio-20261025-101352.db`, SHA-256 `2130445b0292468c2aa258adebb4e8d731d7936e4094a3a09184443fc310a340`, 29 tables, 5/5 checks, restore **PASS**; backup contains the review row and audit event |

### 12.2 New tests and the backup fix

- `tests/test_gstr2b.py` (17, +5) - review status/note/audit, ITC-hold summary and warning,
  superseded-import rejection, tenant isolation, invalid status, and the 3B-vs-2B gap comparison.
- `tests/test_backup.py` (6, +1) - schema coverage: `backup.TABLES` must equal every persistent
  table except `session` and `backup_run` (B-026).
- B-026 fixed a real verification gap: the backup table list had stayed at the Build 0.1 schema
  and omitted nine persistent tables (bank, debit-note, invite, share and GSTR-2B data). The fresh
  backup now verifies 29 tables and the restore drill passes.
- `tests/test_web.py` `test_24_gstr2b_import_and_export` now posts a review, checks the rendered
  state and comparison card, and checks the new CSV columns.

### 12.3 Explicitly NOT verified

- No official GSTR-2B portal JSON/schema, GST portal upload, actual ITC claim or ITC reversal
  posting. `accepted` and `itc_hold` are internal working-paper annotations only.
- No supplier email automation, exception ageing or statement/invite email delivery.
- The comparison is monthly and amount-based; it does not model head-wise ITC set-off, RCM,
  zero-rated/exempt supplies, import ITC or GSTR-3B filing.
- No PostgreSQL, Next.js, load or penetration testing.


## 13. Application run `RUN-2026-10-25-03` - public home page and local demo login

### 13.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **164 tests, OK**, 13.5 s, Python 3.14.6, Windows |
| Unauthenticated `GET /` | **200** product home page; no redirect to `/login`; contains "Smarter Finance.", "GLOBAL BUSINESS MANAGEMENT PLATFORM", "Trusted by Businesses Worldwide" and the synthetic-data note |
| Authenticated `GET /` | Existing dashboard unchanged; still shows Revenue, Net profit and no `None` / `NaN` |
| `GET /demo` with `ARTHIVIO_DEMO_AUTOLOGIN=1` | **303** to `/`, sets an HttpOnly `sid`, lands on the dashboard; audit event `auth.demo_login` written |
| `GET /demo` with the flag off or from a non-loopback address | **404**; no session or audit event created |
| Browser, `/home` | Landing page renders at 1536 px desktop and 500 px mobile widths; dashboard nav, hero, detailed preview, six feature cards, five reasons and trust strip all visible; no horizontal overflow |
| Lighthouse, `/home` | **100 / 100 / 100** accessibility / best practices / SEO; no failed audits |

### 13.2 What changed

- `app/server.py` adds a public product home page (`/` when signed out, plus `/home`). It is
  server-rendered, uses only inline SVG and CSS, is self-contained (no workspace stylesheet), and
  follows the supplied reference's navy/electric-blue/cyan/green palette. It does not read tenant
  data. The dashboard preview is explicitly labelled **Sample workspace · synthetic data**; the
  reference's customer, country and uptime figures carry `*` and a visible illustrative-metrics
  footnote rather than being presented as verified production claims.
- The same file adds an opt-in `/demo` route guarded by `ARTHIVIO_DEMO_AUTOLOGIN=1` and a
  loopback-source check. It auto-logs in the demo owner through the normal session helper and writes
  `auth.demo_login` to the audit trail.
- `dev.ps1 -Demo` starts the server with the flag; without the switch it removes the variable.
- `tests/test_web.py` adds `test_00_public_landing_page` and `test_26_local_demo_autologin_is_opt_in`.
- `README.md` documents the home page, demo route and test count.

### 13.3 Explicitly NOT verified

- The demo route is **not** a public hosted demo and is not safe to expose remotely. It is
  loopback-only by design and should stay behind `127.0.0.1`.
- No video is recorded; "Watch Demo" opens the working demo route.
- No signup, email verification, password reset, OAuth/SSO or multi-currency was added.
- The home page includes the supplied reference's customer, country and uptime figures. They are
  visibly marked `*` and footnoted as illustrative marketing values, not verified production
  claims; they must not be published as fact without evidence. No customer logos or testimonials
  are present.


## 14. Application run `RUN-2026-10-25-04` - grouped navigation, cash book and bank book

### 14.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **165 tests, OK**, 16.3 s, Python 3.14.6, Windows |
| Browser, authenticated workspace | Top bar now shows direct **Dashboard** plus **Transactions**, **Books**, **Reports**, **Tax Returns**, **Masters** and **Settings** dropdown parents; no flat list of every page |
| Browser, **Transactions** dropdown | Sales group contains Invoices, Receipts and Credit Notes; Purchases group contains Bills, Debit Notes and Vendors |
| Browser, **Books** dropdown | Day Book and Journal; Ledger, Cash Book and Bank Book; Bank Reconciliation |
| Browser, **Reports** dropdown | Trial Balance, Profit & Loss, Balance Sheet; Receivables Ageing and Payables Ageing |
| Browser, **Tax Returns** dropdown | GST Summary & GSTR-1, GSTR-3B Working, GSTR-2B Reconciliation |
| Browser, 800 CSS px width | Brand and account actions on the first row; all six menu parents fit on a scrollable second row; dropdowns open below the bar without covering the menu headings |
| Browser, 1400 CSS px iframe check | Top bar remains one row; measured `scrollWidth` did not exceed the 1400 px viewport |
| Browser, `/reports/cash-book` | Cash account opening 0.00, receipt 35,400.00, closing 35,400.00, all from posted `JV-00027` |
| Browser, `/reports/bank-book` | Bank account opening 0.00, receipts and payments through the posted journal, closing 4,55,360.00 |
| Browser console | No uncaught errors observed while opening and closing menus |

### 14.2 What changed

- `app/server.py` replaces the flat left sidebar with a Tally-style grouped top menu. Menus use
  native `<details>/<summary>` elements, so they work by keyboard and do not require JavaScript;
  a small progressive-enhancement script closes other open menus, closes on outside click and
  handles Escape.
- Active parent sections are highlighted, and the current page is highlighted inside its dropdown.
- `app/server.py` adds `/reports/cash-book` and `/reports/bank-book`, both computed directly from
  posted journal lines through `accounting.general_ledger`; nothing is cached or entered directly
  in the book pages.
- `tests/test_web.py` extends `test_14_new_pages_render` for both books and adds
  `test_27_grouped_dropdown_navigation` for the menu groups and links.

### 14.3 Explicitly NOT verified

- Cash book and bank book are ledger views for the existing 1000/1010 control accounts; they do
  not add multi-bank-account selection, contra entries, cheque printing or bank-charge posting.
- No screenshot-based pixel regression suite, no screen-reader session and no cross-browser matrix
  was run. The `details` menu was checked in the local Chromium browser only.
- GSTR outputs remain working aids and are still not filed returns or GST portal uploads.


## 15. Application run `RUN-2026-10-25-05` - ledger hub, separate entries and multiple bank accounts

### 15.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **177 tests, OK**, 14.7 s, Python 3.14.6, Windows |
| Browser, `/ledger` | Every account is listed by type with a balance; 23 accounts before the run, 25 after adding `6040 Travel Expense` and bank ledger `1020` |
| Browser, add ledger account | Submitted code `6040`, type Expense, name Travel Expense; redirected to `/ledger?account=...&created=1` with notice "Ledger account created." |
| Browser, `/bank-accounts` | Listed the legacy `1010 Bank` from Business Settings and the add form; no searching or separate page needed |
| Browser, add bank account | Submitted `1020 HDFC Current A/c`, bank HDFC Bank, account ending `8888`, IFSC `HDFC0001234`, branch Andheri West and holder Arthivio Demo Trading; notice "Bank account created." |
| Browser, `/reports/bank-book?account=...` | Selected the new `1020 — HDFC Current A/c`, showed its full bank details, opening/closing and actions for New bank entry, Open ledger and Bank accounts |
| Browser, `/entries/bank?account=...` | Opened with `1020 — HDFC Current A/c` preselected in row 1 and available in the account list |
| Browser, journal posting and reversal | Posted `JV-00033` (Rent Dr 500, Cash Cr 500); reversed it with reason "Browser check: wrong account"; `JV-00033` is marked reversed, `JV-00034` is the mirrored reversal, and the ledger shows both |
| Browser, navigation | Dashboard plus Transactions, Entries, Books, Reports, Masters and Settings; **Tax Returns** is gone; Reports contains all eight report/GST links |
| Browser, ledger balances | Liabilities, equity and income now show `Cr`; assets and expenses show `Dr`; zero balances stay plain `₹0.00` |
| Browser, responsive layout | At the 800 px browser viewport the account directory stacks above the ledger; the sidebar returns beside the ledger above the 900 px breakpoint |

### 15.2 What changed

- `app/db.py` adds the additive `bank_account` table and index; `app/backup.py` includes it in
  backup coverage.
- `app/accounting.py` adds validated account creation, all-account balances and Dr/Cr-aware
  dashboard cash plus every linked bank account.
- `app/bank.py` adds bank-account listing, next-code generation and atomic bank-account creation
  with full details and audit metadata.
- `app/server.py` adds the Ledger hub, separate Cash/Bank/Journal entry pages, Bank Accounts page,
  journal reversal with a required reason, multi-bank selection in Bank Book and Reconciliation,
  and the new grouped navigation.
- `app/security.py` adds `account.manage` for owner, admin and accountant roles.
- Tests add `TestAccountManagement`, `TestBankAccounts`, and web coverage for ledger account
  creation, bank-account creation and bank book, and journal posting/reversal.
- `test_27_grouped_dropdown_navigation` now checks the seven-heading menu and the absence of the
  old Tax Returns heading.

### 15.3 Explicitly NOT verified

- The browser run used synthetic demo data only. No real bank statement, customer data or GST
  portal connection was used.
- No cross-browser matrix, screen-reader session or pixel-diff regression was run.
- Bank account editing/deactivation, contra entries, cheque printing, partial bank matching and
  bank-charge auto-posting remain unbuilt.
- GSTR-1, GSTR-3B and GSTR-2B outputs remain working aids, not filed returns or ITC claims.


## 16. Application run `RUN-2026-10-26-01` - opening balances

### 16.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **183 tests, OK**, 14.943 s, Python 3.14.6, Windows |
| Unit, `TestOpeningBalance` | 5 tests: debit opening creates balanced equity; credit opening on a liability; duplicate rejected then reversal + replacement; date-after-activity rejected; amount/side/date validation |
| Web, `test_31_opening_balance_on_creation_and_later` | Created `6050 Insurance`, reopened its ledger, posted `1,250.50 Dr` dated `2026-04-01`, verified the `3200` equity line and audit event, rejected a duplicate, reversed the opening entry, then posted `1,300.00 Dr`; trial balance stayed balanced |
| Browser, temporary seeded database on `127.0.0.1:8001` | Created `6050 Insurance`, entered `5,000.00 Dr` at `2026-04-01`; saw "Opening balance posted against Opening Balance Equity", `JV-00031`, `3200 Opening Balance Equity ₹5,000.00 Cr`, a `Reverse` action and a balanced trial balance; no console errors |
| Browser, live database on `127.0.0.1:8000` | Only the read-only form presence was checked; no opening entry was posted into the live demo database during this run |

### 16.2 What changed

- `app/accounting.py` adds `opening_equity_account`, `opening_balance_entry` and
  `set_opening_balance`; the opening journal uses `source_type='opening'` and the existing
  balanced-posting, tenant-scope and period-lock checks.
- `app/server.py` adds the **Set opening balance** form to the selected ledger, the
  `/opening-balance` POST action with server-side `account.manage`, and permission to reverse
  opening entries with a reason.
- `tests/test_accounting.py` adds `TestOpeningBalance` (5 tests).
- `tests/test_web.py` adds the end-to-end creation/posting/reversal/replacement flow.
- `docs/DECISION_LOG.md` D-026 records the balanced-journal design; `docs/ACCOUNTING_RULES.md` §6
  records the implemented rules.

### 16.3 Explicitly NOT verified

- Bulk opening-balance import was not built in this run; it was delivered in Build 0.11 (§19).
  Multi-period opening resets remain unbuilt.
- Bank-account edit/deactivate remains unbuilt.
- The browser check used a temporary synthetic database, not the live demo data; no real customer
  or bank data was used.
- No cross-browser, screen-reader or pixel-diff regression was run for the new opening form.
- Opening figures on income/expense accounts are accepted for migration, but they do not replace a
  proper prior-period P&L close or year-end retained-earnings process.
- GSTR outputs remain working aids, not filed returns or ITC claims.

## 17. Application run `RUN-2026-10-26-02` - Account 360 and product master

### 17.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **196 tests, OK**, 15.084 s, Python 3.14.6, Windows, exit 0 |
| Unit, `TestAdditiveMigration` | An existing database without `account.group_code`, party `account_id`/credit columns or item product columns still migrates cleanly; post-migration indexes are created after the columns; a second `init_db` is idempotent |
| Unit, `TestAccountProfile` | 7 tests: full profile + linked customer + party-tagged opening; linked debtor invoice/receipt; linked creditor bill/payment; incompatible group/type and validation rollback; profile update without touching posted amounts; invalid IFSC/account number on a bank-profile edit rejected without changing stored details; linking an existing customer preserves details that were not entered again |
| Unit, `TestMoney.test_parse_percent_to_basis_points` | Whole and decimal percentages become basis points; floats and three-decimal percentages are rejected |
| Unit, `TestBankAccounts.test_create_links_ledger_and_bank_details` | Bank ledger carries `group_code='bank'` as well as the linked `bank_account` row |
| Web, `test_32_full_account_profile_edit_and_party_link` | Created `1325 Sunrise Hospital` with GSTIN/PAN/CIN/industry/credit terms and a `5,000.00 Dr` opening; saw the profile card and customer-statement link; edited the profile and confirmed the `account.update` audit event |
| Web, `test_33_bank_and_loan_accounts_capture_full_details` | Created `1035 ICICI Current A/c` with bank details and `1,25,000.00 Dr` opening; created `2380 HDFC Term Loan` with lender, account, sanction/maturity, 9.5%, 60 months, EMI and credit opening; verified Bank Book |
| Web, `test_34_product_master_captures_margin_tax_and_hsn` | Created `MED-001 Surgical Kit` with cost `1,000.00`, margin `25%`, MRP `1,500.00`, GST `12%`, HSN `3004`, barcode and stock; sale price computed as `1,250.00`; MRP below sale price rejected with HTTP 400 |
| Browser, temporary seeded database on `127.0.0.1:8001` | Created `1325 Sunrise Hospital` as Sundry Debtors with full profile and `5,000.00 Dr` opening; ledger showed `JV-00031`, `3200 Opening Balance Equity`, the profile card and a reverse action; edited the phone number and saw the update notice; opened `/items` and created `MED-001`; no console errors |
| Browser, live database on `127.0.0.1:8000` | Schema migrated additively and pages rendered read-only; no test account, party, item or opening entry was written to the live demo database |
| Backup, live database after migration | `backups/arthivio-20261026-093127.db`, 610,304 bytes, SHA-256 `20dbdec3…ddfe`, status **VERIFIED**, 31 tables, row counts match, journals balanced |

### 17.2 What changed

- `app/db.py` adds `account.group_code`, the `account_profile` table, customer/vendor `account_id`
  and credit columns, item category/brand/barcode/MRP/margin columns, indexes, seed-group backfill
  and a bank-ledger group backfill. Indexes that reference newly added columns are created only after
  the additive migration, so an existing database upgrades without a `no such column` failure.
- `app/accounting.py` adds the account-group taxonomy, profile validation/save, party creation and
  linking, linked posting paths, profile update and party-tagged opening balances.
- `app/server.py` adds the Account 360 creation/edit pages and POST actions, the ledger profile card,
  real group labels, the group-aware opening-side default and the expanded product master.
- `app/bank.py` marks bank-page accounts with `group_code='bank'`; `app/backup.py` covers
  `account_profile`; `app/money.py` adds `parse_percent`.
- `tests/test_accounting.py` adds seven Account 360 tests and the percentage test;
  `tests/test_web.py` adds three end-to-end flows; `tests/test_bank.py` asserts the bank group;
  `tests/test_migrations.py` adds two existing-database upgrade regressions.
- Documentation: D-027, database design §14, accounting rules §6, feature inventory §16, test plan
  T-1016 to T-1025 and the README status.

### 17.3 Explicitly NOT verified

- At the time of this run, account deletion, archive, merge and bulk chart reclassification were
  not built. Archive/merge were added later in §23; the bulk opening-balance import was delivered in
  Build 0.11 (§19).
- Bank-account deactivate, automatic bank feeds, bank-charge posting, cheque printing and contra
  entries are not built.
- Product-master editing, batch/expiry, serial numbers, barcode printing and purchase-price history
  are not built.
- The browser check used a temporary synthetic database, not real customer or bank data. The live
  demo database was migrated and rendered, but no profile, party, item or opening entry was created
  there during this run.
- No cross-browser, screen-reader or pixel-diff regression was run for the new account form.
- The public share links do not expose the new account profile or bank/loan fields.
- GSTR outputs remain working aids, not filed returns or ITC claims.

---

## 18. Application run `RUN-2026-10-26-03` - expanded account classification selector

### 18.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m py_compile app/accounting.py app/server.py tests/test_web.py` | Passed, exit 0 |
| Targeted web tests 28, 31, 32 and 35 | **4 tests, OK**, 2.277 s, Python 3.14.6, Windows |
| `python -m unittest discover -s tests` | **197 tests, OK**, 16.775 s, Python 3.14.6, Windows, exit 0 |
| Browser, live database on `127.0.0.1:8000` | Logged in as owner, opened `/ledger/account/new`; the selector showed 32 groups in 5 categories; selecting `Suspense A/c` displayed "Accounting type: Liability", its clearing hint and `Credit (Cr)` as the suggested opening side; no console errors. The form was not submitted, so no account was created. |

### 18.2 What changed

- The new-account form now has one **Account type / group** selector. It lists every posted
  classification under its accounting type instead of a five-option Type dropdown plus a second
  Group dropdown. The form derives the accounting type and normal Dr/Cr side from the selected
  group; the five internal types remain the posting rule.
- The selector covers cash, bank, Sundry Debtors / Accounts Receivable, Sundry Creditors / Accounts
  Payable, inventory, fixed assets, investments, loans and advances, GST input, loans, duties and
  taxes (GST/TDS), provisions, **Suspense A/c**, capital, drawings, retained earnings,
  **Profit & Loss A/c**, opening-balance equity, sales, service and other income, purchase, direct
  expenses, COGS, employee costs, finance costs, depreciation and other expenses.
- Changing the classification updates the explanatory hint and the suggested opening-balance side.
  The user can still override the side; posted amounts and journal balance rules are unchanged.
- The server derives the type from the group when older callers post only `group_code`, and keeps
  accepting legacy `type`-only account creation.
- `tests/test_web.py` adds `test_35_account_type_group_selector_covers_business_classifications`,
  which checks the visible classifications and creates a Suspense account from the group alone,
  confirming it is stored as a liability.

### 18.3 Explicitly NOT verified

- The selector was checked only in the local Chromium browser; no cross-browser, screen-reader,
  tablet/mobile or pixel-diff check was run.
- `Profit & Loss A/c` is an equity classification for workflows that keep a separate P&L account;
  it does not turn the P&L report into a ledger or change year-end closing, which remains unbuilt.
- Suspense is a holding classification only. There is no automatic suspense clearing or ageing.
- The live demo database was not written to during this run.

---

## 19. Application run `RUN-2026-10-26-04` - bulk opening-balance import

### 19.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m py_compile app/opening_import.py app/accounting.py app/server.py` | Passed, exit 0 |
| `python -m unittest tests.test_opening_import -v` | **8 tests, OK**, Python 3.14.6, Windows |
| `python -m unittest tests.test_web.WebTest.test_36_bulk_opening_balance_import_preview_post_and_template -v` | **1 test, OK** |
| `python -m unittest discover -s tests` | **206 tests, OK**, 16.025 s, Python 3.14.6, Windows, exit 0 |
| Browser check on a temporary copy of the live database | `/ledger/opening-balances` rendered under **Books → Ledgers → Bulk Opening Balances**; a two-row CSV preview showed `2/2 ready`, the expected Dr/Cr totals and **Post all 2 opening balances** |
| Live server HTTP check after restart on `127.0.0.1:8000` | signed in, GET `/ledger/opening-balances` returned 200 with the page, nav item, preview button and template link; no posting performed |
| Live demo database | **Not written to.** The browser preview used a temporary copy and the live check was read-only |

The full suite emitted one standard-library `ResourceWarning` for an unclosed `HTTPError` response in an
existing share-link test. It was not a failure; all 206 tests passed.

### 19.2 What changed

- Added `app/opening_import.py`: CSV parsing, header aliases, whole-file validation, preview totals,
  atomic posting and the `opening_balance.bulk_import` audit event.
- Added **Books → Ledgers → Bulk Opening Balances** at `/ledger/opening-balances`, with a downloadable
  CSV template at `/ledger/opening-balances/template.csv`.
- The preview rejects a missing/invalid header, missing account code, duplicate code, credit/debit
  side outside Dr/Cr, non-positive or malformed amounts, a missing account, a non-postable account,
  an account that already has a posted opening, a date after the account's first posted activity,
  a future date, a locked period and the Opening Balance Equity account itself.
- Posting is all-or-nothing: every row becomes its own balanced `source_type='opening'` journal against
  Opening Balance Equity, in one outer transaction. A simulated failure on the second row in
  `test_07_failure_after_first_entry_rolls_back_the_whole_import` left zero opening entries, no
  Opening Balance Equity account and no bulk-import audit row.
- Optional CSV `note` values are appended to the journal narration and copied into the per-account
  `opening_balance.set` audit metadata. Amounts and balanced-posting rules are unchanged.
- Version label advanced to **Build 0.11**. No schema change and no rewrite of existing journals.

### 19.3 Explicitly NOT verified

- The browser check previewed but did not post from the screen; posting and rollback were verified by
  the automated tests, including a simulated mid-import failure.
- File-picker upload was exercised only through the page's JavaScript wiring; automated tests submit
  the pasted CSV text. The template download was covered by an HTTP test, not a browser download.
- No large-file timing, thousands-of-rows load test, cross-browser, screen-reader, tablet/mobile or
  pixel-diff check was run.
- The duplicate/overwrite policy remains deliberate: an existing opening must be reversed before a
  replacement can be imported. There is no in-place CSV re-import or merge.
- GST working papers, period closing, automatic suspense clearing and (at the time of this run)
  account archive/merge remained outside this run; archive/merge were added later in §23.

## 20. Application run `RUN-2026-10-26-05` - shared home-page palette

> Historical: the navy topbar described in this run was replaced by the white topbar and four
> per-user palettes in `RUN-2026-10-26-06` (§21).

### 20.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **207 tests, OK**, 16.441 s, Python 3.14.6, Windows, exit 0 |
| `test_37_workspace_uses_the_public_home_page_palette` | Passed; asserts the new tokens are present and the old workspace tokens are absent |
| Live server restart on `127.0.0.1:8000` | Serving the updated app; no database writes |
| Browser check | Public `/home`, login, dashboard, ledger hub and an invoice print page all rendered in the shared navy/blue/cyan palette |
| Old workspace palette scan | No `ivory/emerald/gold` token or matching legacy hex value remains in `app/*.py` |

The full suite emitted the same standard-library `ResourceWarning` for an unclosed `HTTPError`
response in an existing share-link test; all 207 tests passed.

### 20.2 What changed

- Workspace CSS tokens now use the public home page family: page `#F6F9FF`, navy ink `#0B1F3A`,
  electric blue `#2563EB`, soft blue `#DBEAFE`, pale blue `#EFF6FF`, cyan `#67E8F9` and success
  green `#22C55E`.
- The top bar, navigation active state, dropdowns, ledger sidebar, cards, tables, forms, buttons,
  badges, charts and notices use those tokens. Red remains limited to danger/error states.
- The workspace logo mark uses the same cyan/blue/violet geometry as the public home page.
- Print invoices and account statements use navy headings, blue rules and light-blue table headers.
- Layout, spacing, navigation structure and accounting behaviour are unchanged. No schema change.
- `test_37_workspace_uses_the_public_home_page_palette` guards the shared tokens and rejects the
  legacy workspace palette, so the two surfaces cannot silently drift apart again.
- Decision log D-030 records the palette unification; D-022 is marked as partly superseded.

### 20.3 Explicitly NOT verified

- The visual checks ran in the desktop Chrome session; no Firefox/Safari/Edge, mobile, tablet,
  screen-reader, automated contrast audit or pixel-diff run was performed.
- Lighthouse was not re-run for this palette change; the earlier `/home` score is not a claim about
  the updated workspace pages.
- The palette is a deliberate owner-directed change from the original ivory/emerald/gold spec theme;
  the governing spec text is preserved unchanged and D-030 records the deviation.

## 21. Application run `RUN-2026-10-26-06` - white topbar and four user palettes

### 21.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **208 tests, OK**, 16.425 s, Python 3.14.6, Windows, exit 0 |
| `test_37_workspace_offers_four_light_themes_without_navy` | Passed; asserts Ocean/Emerald/Violet/Sunset blocks, neutral ink, theme-driven print CSS and absence of navy/legacy app tokens |
| `test_38_user_can_choose_a_saved_colour_theme` | Passed; saves Violet, checks dashboard/login/invoice-print `data-theme`, `user.theme`, `user.theme_updated`, rejects an unknown palette and restores Ocean |
| `TestAdditiveMigration` | Passed; an existing `user` table without `theme` gains `theme TEXT NOT NULL DEFAULT 'ocean'` and an old row reads back as Ocean |
| Live server restart on `127.0.0.1:8000` | Serving the white-topbar/four-palette build; startup applied the additive `user.theme` column (both existing users default `ocean`); no ledger/account/journal writes and no theme-save audit |
| Browser check: Ocean | `/login`, dashboard, Settings → Appearance and invoice print rendered with a white topbar, light blue page and no navy app chrome |
| Browser check: Violet, Emerald, Sunset | Settings → Appearance saved each palette and the dashboard adopted the chosen tokens; Settings showed “Theme saved” and the selected card. Invoice print was additionally checked in Violet and resolved the theme variables. |
| Temporary theme-check server | Used a seeded copy in `C:\Users\vicky\AppData\Local\Temp\opencode`; temp server and database were removed after the check |

The full suite emitted the same standard-library `ResourceWarning` for an unclosed `HTTPError`
response in an existing share-link test; all 208 tests passed.

### 21.2 What changed

- The signed-in topbar is white with a light border; app ink is neutral charcoal `#212529`, not navy.
- Four light palettes are available per user: **Ocean Blue** (`#2563EB`), **Emerald Green**
  (`#15803D`), **Royal Violet** (`#7C3AED`) and **Warm Sunset** (`#C2410C`). Page, line, soft/pale,
  chart and focus colours move with the palette; success and danger keep their meaning.
- `user.theme` is an additive column defaulting to `ocean`; existing databases receive it through
  `_ensure_columns`.
- **Settings → Appearance** shows four preview cards and a Save theme button. `POST /preferences/theme`
  requires a signed-in user + CSRF, validates the allow-list, writes `user.theme_updated` and sets a
  non-sensitive `ui_theme` cookie for the sign-in page.
- `layout()` sets `data-theme` on `<html>`; `THEME_CSS` supplies the tokens to the app and to invoice
  and statement print pages. The public landing hero remained unchanged in this run; D-032 later
  lightened it and added a page-level picker (see §22).
- `test_37` and `test_38` guard the palettes, the no-navy rule, persistence and print/login theming.
  Decision log D-031 records the amendment to D-030.

### 21.3 Explicitly NOT verified

- Browser checks used the desktop opencode Chrome session; no Firefox/Safari/Edge, mobile, tablet,
  screen-reader, automated contrast audit or pixel-diff run was performed.
- The `:has(input:checked)` selected-card styling relies on modern browser support; older engines may
  not draw the selected border, though the radio choice still works.
- Lighthouse was not re-run for this palette change. The earlier `/home` score is not a claim about
  the signed-in pages.
- The public landing hero still used its navy reference background at the time of this run; only the
  signed-in workspace was changed to the white/no-navy rule. D-032 later lightened it and added a
  landing-page colour picker; see §22.
- No live accounting totals, journals, accounts or parties were changed by the theme work. The live
  database was not used for the theme-save browser check.

## 22. Application run `RUN-2026-10-27-01` - lighter landing hero and page colour picker

### 22.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **208 tests, OK**, 18.108 s, Python 3.14.6, Windows, exit 0 |
| `test_37_workspace_offers_four_light_themes_without_navy` | Passed; also asserts the four landing themes, dark landing CSS variables, picker links, the Royal Violet variant and Ocean fallback for an invalid theme |
| `test_38_user_can_choose_a_saved_colour_theme` | Passed; also requests `/home?theme=emerald`, confirms the landing `data-theme` and hero tokens, confirms the cookie persists on `/home`, then restores Ocean |
| Live server restart on `127.0.0.1:8000` | Serving the updated build; `/health` returned `ok`; no database writes |
| Browser check: Ocean | Computed hero background `rgb(12, 49, 87)` → `rgb(10, 42, 72)` → `rgb(6, 26, 48)`; proof strip and preview sidebar followed the same family; palette button rendered |
| Browser check: Violet | `/home?theme=violet` redirected and set the cookie; computed hero `rgb(45, 29, 82)` → `rgb(36, 21, 68)` → `rgb(21, 12, 40)`, accent `rgb(196, 181, 253)`, active menu item Royal Violet |
| Browser check: picker behaviour | Palette button opened the four-colour menu; an outside click and `Escape` closed it; the page remained dark in every variant |

The full suite emitted the same standard-library `ResourceWarning` for an unclosed `HTTPError`
response in an existing share-link test; all 208 tests passed.

### 22.2 What changed

- The public landing hero moved from the near-black `#04162F` navy to a lighter navy gradient
  (`#0C3157` → `#0A2A48` → `#061A30`). It is still a dark hero, not a light page.
- The landing page now has four separate dark variants: Ocean (navy), Emerald (green), Violet
  (violet) and Sunset (terracotta). Hero, proof strip, preview sidebar, accents and key buttons move
  together; the light marketing sections keep their original white/neutral treatment.
- A visible **Colour** pill in the landing header opens the four-choice **Landing colour** menu, with
  a note that the saved workspace theme is under **Settings → Appearance**. Links use
  `/home?theme=<key>`; the server validates the key against the allow-list, sets the non-sensitive
  `ui_theme` cookie, redirects to `/home` and falls back to Ocean for invalid values.
- The landing page reads only the cookie, never tenant data, and remains a standalone document
  without the workspace stylesheet. It sends `Vary: Cookie` with a revalidating cache header so a
  colour change is visible immediately instead of serving a stale page.
- The landing picker does **not** write `user.theme` or an audit event. The saved workspace palette
  remains **Settings → Appearance** (D-031); the page-level landing choice is a preview preference.
- Layout, navigation structure, accounting semantics, reports and the signed-in white/no-navy
  workspace are unchanged. D-032 records the decision.

### 22.3 Explicitly NOT verified

- Browser checks used the desktop opencode Chrome session; no Firefox/Safari/Edge, mobile, tablet,
  screen-reader, automated contrast audit or pixel-diff run was performed for the landing variants.
- Lighthouse was not re-run; the earlier `/home` score is not a claim about the updated landing page.
- The landing colour is a cookie-only preference. It is intentionally not saved to `user.theme`, and
  it does not change the workspace palette after sign-in.
- No live accounting totals, journals, accounts, parties or theme-save audit rows were changed. The
  landing checks only set the non-sensitive `ui_theme` cookie.

## 23. Application run `RUN-2026-10-27-02` - account archive, merge and restore

### 23.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **215 tests, OK**, 17.058 s, Python 3.14.6, Windows, exit 0 |
| `python -m unittest tests.test_account_archive -v` | 6 tests, OK |
| `python -m unittest tests.test_web.WebTest.test_39_account_archive_merge_and_restore -v` | 1 HTTP test, OK |
| `python -m unittest tests.test_migrations -v` | 2 tests, OK; old `account` rows gain `status='active'` and all four archive columns |
| Live database migration | `data/arthivio.db` was backed up first; `db.init_db` added the four archive columns and `ix_account_status`; all 26 existing accounts are `active`, and no account, journal or party row was archived/merged |
| Live browser check (desktop Chromium) | signed in as the demo owner; `/ledger/account/<6010>/archive` showed the zero balance, archive form, merge form and four compatible expense targets; a non-zero ledger showed the zero-balance explanation instead of an archive form; the cash control ledger showed archive/merge locked; no browser console errors |
| Live `/health` | HTTP 200 `ok` after restart; `/home` returned 200 with the dark Ocean landing |

The full suite emitted the same standard-library `ResourceWarning` for an unclosed `HTTPError`
response in an existing share-link test; all 215 tests passed.

### 23.2 What changed

- `account.status`, `archived_at`, `archived_by` and `merged_into_id` are additive columns. The base
  schema and `_ensure_columns` both supply them; existing rows default to `active`.
- `_assert_accounts` now rejects any archived account for every posting path, so invoices, bills,
  receipts, payments, notes, journals and opening balances cannot post into a closed ledger.
- Archive is limited to ordinary zero-balance ledgers with a required reason. It blocks system and
  control accounts, customer/vendor pointers (including legacy pointers without an
  `account_profile` row) and product sales-ledger references. It writes `account.archive`.
- Merge requires an active same-type target, posts one balanced `source_type='merge'`
  reclassification journal for the net source balance, archives the source and writes
  `account.merge`. Bank-to-bank, same-party, system/control source-or-target and future-activity
  rules are enforced; products and the customer/vendor account pointer are repointed where
  applicable.
- Restore is available with an optional reason and writes `account.restore`. It makes the ledger
  active again but does not reverse the merge journal.
- Archived accounts disappear from posting/account selectors, Bank Book account lists, new opening
  imports and item revenue choices. The ledger hub keeps them in a separate archived list with their
  full history; the archive page shows the merged target and the restore action.
- The ledger page hides entry and reversal actions for an archived ledger and shows the archived
  state and merge target. The archive page shows a balance explanation instead of an archive form
  when the ledger has a non-zero balance, while still offering compatible merge targets.
- New tests: six service-level cases in `tests/test_account_archive.py` and one HTTP flow in
  `test_web.test_39`; the existing migration test now checks the four new columns and index.

### 23.3 Explicitly NOT verified

- The live browser check was desktop-only and did not submit an archive or merge, so it did not
  prove live posting behaviour. The actual archive/merge/restore posting flow was exercised only on
  the temporary SQLite test database; no live account was archived or merged.
- No mobile, tablet, screen-reader, automated contrast, cross-browser or pixel-diff check was run.
- Merge is not a one-click undo. Restore reopens the source but leaves the reclassification journal
  in place; reversing it requires an explicit manual journal.
- Merging bank ledgers does not move or re-key imported bank-statement lines; those stay on the
  archived source ledger. The target ledger shows the transfer through the merge journal.
- Merging two ledgers does not move invoice/bill document numbers or rewrite historical source
  lines. Old source lines remain in the source ledger and all reports.
- No load, concurrency or penetration test was performed. The live database received only the
  additive schema migration plus the normal sign-in session/`auth.login` audit rows; no live
  journal, account status, party pointer or archive/merge audit row was changed by this
  verification.


## 24. Application run `RUN-2026-10-27-03` - analytics foundation and pilot

### 24.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **222 tests, OK**, 20.872 s, Python 3.14.6, Windows, exit 0 |
| Re-run after adding `ARTHIVIO_HOST` phone/LAN binding | **222 tests, OK**, 19.302 s, exit 0 |
| `python -m unittest tests.test_analytics -v` | 6 tests, OK |
| `python -m unittest tests.test_web.WebTest.test_40_analytics_api_contract_and_auth -v` | 1 HTTP test, OK |
| Live database backup | `backups/arthivio-pre-analytics-20261027-113909.db` created before restart |
| Live additive migration | `db.init_db` created `v_analytics_journal` and `v_analytics_monthly`; `v_analytics_journal` returned 138 rows for the demo tenant; no accounting row was rewritten |
| Live `/health` | HTTP 200 `ok` after restart |
| Live API | `/api/v1/analytics/overview` returned HTTP 200, `application/json; charset=utf-8`, `Cache-Control: no-store`, schema `1.0`, 19 metric keys, 7 monthly buckets |
| Live browser check (desktop Chromium) | Reports > Analysis > Analytics Overview rendered KPI cards, monthly revenue/expense bars, expense breakdown, top customers/vendors, balanced checks and freshness; no console errors |
| Live copy analytics check | `analytics.overview()` ran against a copy of the live database for all tenants without error; no live accounting data was mutated |

The full suite emitted the same standard-library `ResourceWarning` for an unclosed `HTTPError`
response in an existing share-link test; all 222 tests passed.

### 24.2 What changed

- `app/db.py`: two additive read-only views. `v_analytics_journal` joins posted journal lines to
  entries and accounts; `v_analytics_monthly` aggregates income, expense and signed amounts by
  tenant, month and account type. They are created after `_ensure_columns` and dependent indexes, so
  an existing database upgrades without table rewrites.
- `app/analytics.py`: 19 actual-only metrics with written source/formula/permission/drill-down
  metadata; period resolution; tenant-safe snapshot; zero-filled monthly series; expense
  composition; top customers and vendors; freshness and balance checks.
- `app/server.py`: `GET /api/v1/analytics/catalog` and `GET /api/v1/analytics/overview` require a
  session, `report.view` and tenant membership; errors are JSON with codes (`UNAUTHENTICATED`,
  `FORBIDDEN`, `BAD_DATE`, `BAD_PERIOD`); responses are `no-store` and use the same
  security headers. `/reports/analytics` is the pilot screen under the single Reports dropdown.
- `tests/test_analytics.py`: six service-level tests. `test_web.test_40` covers unauthenticated API,
  catalog, overview, invalid date and the page/fallback. `test_27` now checks the new report link.
- Documentation: README, analytics plan, report catalog, architecture, database design, feature
  inventory, roadmap, decision log, test plan and traceability updated in the same change.

### 24.3 Explicitly NOT verified / not delivered

> **Historical for Build 0.11.** Build 0.12 supersedes the Excel, Power BI and deterministic-insight gaps below; see section 25. Generative AI, Power BI Service and the full report library remain open.

- AI insights, grounded Q&A, anomaly detection and forecasts are **not implemented** (Build 0.11).
- True `.xlsx` import/export and AI workbooks are **not implemented**; CSV remains the only
  spreadsheet path.
- Power BI dataset, Power Query template, `.pbix` starter, RLS and scheduled refresh are **not
  implemented**. The JSON API is session-only and has no external token/pagination contract yet.
- The full chart engine, saved dashboard layouts, drill-down from every total, EN/HI labels and the
  66-report completion are **not delivered**; the Analytics Overview is a pilot and is not counted
  in the 19 catalogued working reports.
- Browser check was one desktop Chromium viewport (847 px CSS width). No mobile, tablet,
  screen-reader, automated contrast, cross-browser, 4K or pixel-diff check was run.
- No live invoice, journal, account, party or theme row was changed. The live database received the
  additive views plus normal sign-in session/audit rows; the live analytics page was read-only.
- No load, concurrency or penetration test was performed.


## 25. Application run `RUN-2026-10-28-01` - real Excel, Power BI pack, grounded insights and xlsx import

### 25.1 What was actually executed

| Command / check | Result |
|---|---|
| `python -m unittest discover -s tests` | **245 tests, OK**, 23.224 s, Python 3.14.6, Windows, exit 0 |
| Final re-run after the second ECharts view and script placement | **245 tests, OK**, 22.188 s, exit 0 |
| `python -m unittest tests.test_excel -v` | 6 workbook tests, OK |
| `python -m unittest tests.test_bi -v` | 4 Power BI pack tests, OK |
| `python -m unittest tests.test_insights -v` | 3 grounded-insight tests, OK |
| `python -m unittest tests.test_xlsx_import -v` | 5 real `.xlsx` conversion tests, OK |
| `python -m unittest tests.test_web.WebTest.test_41 ... test_45` | HTTP export, insights and multipart xlsx import checks, OK |
| Live `/health` after restart | HTTP 200 `ok`; server header now `ARTHIVIO/0.12` |
| Live `/reports/analytics` | HTTP 200; monthly and expense-composition ECharts containers, Excel button, Power BI button and AI Insights card all present |
| Live `/api/v1/analytics/insights` | HTTP 200, `engine=deterministic_rules_v1`, `generative_ai=false`, 8 observations |
| Live `/export/workbook.xlsx` | HTTP 200, 57,873 bytes through the public tunnel, correct OOXML content type; opened with `openpyxl`: 20 sheets, 3 native charts, KPI source paise present |
| Live `/export/powerbi.zip` | HTTP 200, 15,149 bytes through the public tunnel; 9 files including manifest, facts, dimensions, metric catalog and Power Query starter; manifest says actuals-only and integer paise |
| Public phone demo | a temporary localhost.run URL returned HTTP 200 through `localhost.run`; demo login and `/reports/analytics` returned HTTP 200 (42,729 bytes). A real Chromium session loaded both ECharts canvases with no console errors. The Serveo free tunnel expired, so it is not relied on. |

The live server was restarted on `127.0.0.1:8000`. The earlier `localhost.run` 502 was caused by the app server being down, not by the tunnel; after the server was back, `ssh -4 -R 80:127.0.0.1:8000 nokey@localhost.run` served the login, analytics page, insights JSON and downloads. Serveo also worked but its free tunnel expired. The public URL is temporary and may rotate.

### 25.2 What changed

- `requirements.txt`: approved `openpyxl==3.1.5` added; no other runtime dependency was introduced.
- `app/excel.py`: real `.xlsx` actuals workbook with 20 sheets, native Excel charts, exact
  integer-paise KPI source values beside displayed INR amounts, AR/AP ageing, cash/bank movement,
  inventory, GST working sheets, journal and an AI Insights sheet. It is actuals-only.
- `app/xlsx_import.py`: safe `.xlsx` to neutral CSV conversion for the existing validators. It reads
  the first worksheet by default (or a named sheet), handles real dates and decimals, uses cached
  formula values only, skips blank rows, strips trailing empty columns, and enforces 8 MB and 50,000
  non-empty-row limits.
- `app/server.py`: `/export/workbook.xlsx`, `/export/powerbi.zip`, `/static/echarts.min.js`,
  `/api/v1/analytics/insights`, the Analytics AI card and ECharts chart, multipart form parsing
  without the removed `cgi` module, and server-side `.xlsx` handling for opening balances, bank
  statements and GSTR-2B. Accounting validators are unchanged: nothing posts until the existing
  preview/confirm or import rules succeed.
- `app/bi.py`: static Power BI import ZIP with manifest SHA-256 hashes, analytics JSON, metric
  catalog, integer-paise journal/monthly facts, account/party dimensions, Power Query starter and a
  limitations README. It is not a `.pbix`, Service dataset, RLS model or scheduled-refresh package.
- `app/insights.py`: deterministic grounded observations with metric keys, written basis,
  drill-down targets and source labels. No external model is called and no forecast is mixed into
  actuals.
- `app/static/echarts.min.js`: ECharts 5.5.1 vendored locally with its Apache-2.0 notice; the page
  has no runtime CDN dependency and now renders two actuals charts: monthly revenue/expense/profit
  and expense composition.
- Tests: `tests/test_excel.py` (6), `tests/test_bi.py` (4), `tests/test_insights.py` (3),
  `tests/test_xlsx_import.py` (5), and HTTP `test_41` to `test_45`.

### 25.3 Explicitly NOT verified / not delivered

- No generative AI provider is configured or called. The AI Insights page and API are deterministic
  rules with an explicit no-provider label; no narrative generation, Q&A, anomaly model or forecast
  is delivered.
- Power BI is a static import pack only. There is no `.pbix`, Service dataset, token API, RLS model,
  scheduled refresh or browser check inside Power BI Desktop/Service.
- The `.xlsx` import covers only the three existing import flows (opening balances, bank statements,
  GSTR-2B). It is not a general workbook importer, does not evaluate formulas, and does not preserve
  Excel formatting or multiple-sheet relationships.
- The 66-report catalogue is still incomplete (19 catalogued working reports), and saved dashboards,
  EN/HI labels, full drill-down and the ~150-template chart/report target are not delivered.
- The public phone check proved the login and Analytics page loaded through the tunnel; it did not
  run a real phone viewport, screen-reader, contrast, cross-browser, 4K or pixel-diff test.
- No live accounting row was written by the verification. The live database received normal sign-in
  session/audit rows and read-only exports; the multipart import test used the temporary test DB.
- No load, concurrency or penetration test was performed. The Build 0.12 code was committed and
  pushed to GitHub as `56aca9d` after this run.

## 26. Deployment smoke test (2026-10-28)

- Docker is not installed on this machine, so the image was **not** built locally. The
  `Dockerfile` and `render.yaml` are committed but the actual Render build/deploy is still
  pending owner GitHub/Render authorization.
- The container runtime path was exercised without Docker: a temporary `ARTHIVIO_DB`,
  `python scripts/seed_demo.py`, then `ARTHIVIO_HOST=0.0.0.0 PORT=8010 python -m app.server`.
- Seed result: 11 invoices, 30 journal entries, trial balance balanced.
- `GET /health` returned 200; demo login and `/reports/analytics` returned 200.
- Added `Dockerfile`, `.dockerignore`, `render.yaml` and `docs/DEPLOYMENT.md`.
- Not verified: Render build, cold-start time, free-plan sleep/wake, persistent disk, TLS/custom
  domain or production security. The free plan is demo-only and its SQLite data is ephemeral.
