# ARTHIVIO — Test Plan

| Field | Value |
|---|---|
| Version | 1.0 (baseline, pre-implementation) |
| Date | 2026-10-24 |
| Status | **Active as a plan; not executable yet** — no application code exists |
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
| Test cases defined | 156 automated application tests plus 12 audit-time checks |
| Test cases executed | 156 application tests in `RUN-2026-10-25-01` |
| Test cases passed | 156 |
| Test cases failed | 0 |
| Test cases blocked | 0 |
| Application tests executed | **156** |
| Last verified | 2026-10-25, Python 3.14.6, Windows |

See `docs/TEST_RESULTS.md` for the literal run evidence and `docs/BUG_REPORT.md` for defects.

### Build 0.6 additions

- `T-401`–`T-412`: GSTR-2B CSV parsing, dedup/supersede, matching, differences, history,
  duplicate-period redirect, tenant isolation and export.
- `T-501`–`T-511`: invite create/accept/expiry, existing-user password, owner/self guards,
  role change, suspension session revocation, statement scope/expiry/revoke/view count.
- `T-601`–`T-604`: HTTP E2E for team invite acceptance, share/print/revoke, GSTR-2B import/export
  and business switching.

Operational checks in the same run: live GSTR-2B August 2026 reconciliation, public statement
creation/print/revoke, backup integrity + restore, and Lighthouse accessibility/SEO audits.
