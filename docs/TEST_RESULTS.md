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
