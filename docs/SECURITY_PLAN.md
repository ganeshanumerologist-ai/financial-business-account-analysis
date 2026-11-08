# ARTHIVIO — Security Plan

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-10-28 |
| Status | Draft for owner approval |
| Scope | Phase 1 foundation, with forward requirements for later phases |

> This is a plan, not a certification. No security claim in this document is verified until the corresponding test in `docs/TEST_PLAN.md` passes and the evidence is recorded in `docs/TEST_RESULTS.md`.

---

## 1. Assets to protect

| Asset | Why it matters | Impact if exposed |
|---|---|---|
| Financial transactions & ledgers | Core business record | Fraud, misstatement, competitive harm |
| Customer/supplier identities | Personal + commercial data | Privacy harm, legal exposure |
| Credentials & session tokens | Account takeover | Full tenant compromise |
| Audit log | Proof of who did what | Loss of accountability |
| Backups | Recovery capability | Total data loss |
| Tax identifiers (GSTIN etc.) | Regulated data | Compliance breach |

---

## 2. Actors and trust boundaries

| Actor | Trust |
|---|---|
| Anonymous visitor | Untrusted |
| Authenticated user (any tenant) | Untrusted beyond their permissions |
| Tenant administrator | Untrusted beyond their tenant |
| Platform operator (owner) | Privileged, must be audited |
| Backend service | Trusted, but validates all input |
| Database | Trusted store, access restricted to service credentials |
| Portable toolchain on the dev machine | Trusted for dev; never receives production secrets |

**Boundaries:** browser ↔ Next.js · Next.js ↔ FastAPI · FastAPI ↔ database · service ↔ backup storage. Every boundary validates input independently; nothing trusts the caller's claims about identity or tenant.

---

## 3. Threat model (STRIDE) and mitigations

| Threat | Example | Mitigation | Verified by |
|---|---|---|---|
| **Spoofing** | Stolen session cookie | HttpOnly+Secure+SameSite, rotation, idle/absolute expiry, revoke-all | SEC-008, SEC-009 |
| **Tampering** | Editing a posted journal via API | Immutable posted rows, reversal-only, server-side checks | ACC-014, ACC-015 |
| **Repudiation** | "I never changed that role" | Append-only audit log with actor + IP + UA | SEC-001 (audit test) |
| **Information disclosure** | Tenant A reads Tenant B invoice by guessing ID | Repository-level tenant scoping, 404 on mismatch | SEC-001, SEC-002 |
| **Denial of service** | Login brute force | Rate limit + lockout + generic error messages | SEC-014 |
| **Elevation of privilege** | Read-only user calls admin endpoint | Permission checks server-side on every route | SEC-003, SEC-004 |
| **Injection** | SQL/NoSQL injection in filters | Parameterised queries only, no string-built SQL | SEC-006 |
| **XSS** | Customer name with `<script>` | Contextual escaping, CSP header | SEC-007 |
| **CSRF** | Forged transfer request | Double-submit token bound to session | SEC (CSRF test) |
| **Supply chain** | Malicious npm package | Lockfiles, pinned versions, audit scan | SEC-010 |
| **Insider abuse** | Support user reads a tenant's data | Least privilege, scoped access, audit trail | SEC-001, review |
| **Backup theft** | Copy of DB from disk | Encryption at rest, restricted permissions, separate key | BAK-006 |

Explicit non-goals for Phase 1: DDoS mitigation, WAF, penetration testing, SOC 2/ISO certification.

---

## 4. Authentication

| Control | Requirement |
|---|---|
| Password hashing | Argon2id, per-user salt, parameters tuned to ~250 ms on target hardware; pepper from env |
| Password policy | Minimum 12 chars, reject top-10k common passwords, no composition theatre, no forced rotation |
| Login response | Generic "invalid email or password"; no account enumeration |
| Lockout | 5 failures → progressive delay, then 15 min lock; logged |
| MFA | Optional TOTP, secret encrypted at rest; not enabled by default in Phase 1 |
| Session token | 256-bit CSPRNG, opaque; stored only as SHA-256 hash |
| Cookie | `HttpOnly`, `Secure` (non-local), `SameSite=Lax`, `Path=/` |
| Rotation | New session ID on login and on privilege change; old session revoked |
| Expiry | 30 min idle sliding, 12 h absolute |
| Logout | Revokes current session; "log out everywhere" revokes all |
| Password reset | Time-limited single-use token; invalidates other sessions (Phase 1.5) |

---

## 5. Authorisation model

Permissions are explicit strings; roles are bundles. Checks happen in a dependency that runs **before** the handler body — not inside templates, not in the UI.

| Role | Tenancy | Users | Ledger / accounts | Invoices | Inventory | Reports | Export | Backup |
|---|---|---|---|---|---|---|---|---|
| owner | manage | full | post/reverse/manage | full | full | all | yes | run/restore |
| admin | manage | full | post/reverse/manage | full | full | all | yes | run |
| manager | — | invite | post | approve | adjust | all | yes | — |
| accountant | — | — | post/reverse/manage | create | view | all | yes | — |
| cashier | — | — | — | create/receipt | view | own-day | no | — |
| sales | — | — | — | create | view | own | no | — |
| inventory | — | — | — | — | full | stock | yes | — |
| readonly | — | — | view | view | view | view | no | — |

Build 0.10 adds `account.manage` for creating ledger and bank accounts, setting an opening balance,
and editing an Account 360 profile. It is granted to owner, admin and accountant; manager, cashier,
sales, inventory and readonly do not receive it. Manual journal and opening-balance reversal
continue to require `ledger.reverse`. The opening-balance and profile-update endpoints recheck
`account.manage` on the server even when the form is hidden. Build 0.11's bulk opening-balance
preview, template download and posting endpoints use the same `account.manage` check; the import is
tenant-scoped and cannot create accounts, so a CSV cannot widen access or invent a ledger.

The per-user palette endpoint `POST /preferences/theme` is available to any signed-in member but
changes only that user's own `user.theme` value. It is CSRF-protected, accepts only the four fixed
palette keys (unknown values are rejected), writes `user.theme_updated`, and sets a non-sensitive
`ui_theme` cookie used only to render the sign-in page and the public landing page's dark colour
variant. The landing picker can set that cookie through a validated `/home?theme=<key>` GET; it never
writes `user.theme`, the audit log, accounting data or tenant data. It grants no accounting, tenant
or user-management access.

Build 0.11's account archive/merge endpoints (`POST /accounts/archive`, `/accounts/restore`,
`/accounts/merge`) use the same server-side `account.manage` check, CSRF protection and tenant-scoped
account lookup. Archive/merge require a reason and are refused for system/control accounts,
party-linked ledgers, product-used sales ledgers, mismatched types/parties, bank/non-bank pairs and
future-dated source activity. A merge posts one balanced reclassification journal through the normal
posting service (period lock and balanced-posting checks still apply), then archives the source; it
never edits or deletes a posted line. `account.archive`, `account.merge` and `account.restore` are
written to `audit_log` with actor, source/target, reason, amount and journal reference. The UI hides
the actions for roles without `account.manage`, but the server rejects them even if the form is
forged.

Account profile fields can contain personal and commercial data (contact, phone, email, GSTIN, PAN,
CIN, bank/lender details). They are tenant-scoped, never rendered in public share links, and never
change posted amounts. Account update writes `account.update`; opening balance writes
`opening_balance.set`. Item master writes still require `item.manage`.

Rules:
- Least privilege by default; every new endpoint must declare a permission or it is denied.
- Branch/warehouse scoping narrows a role further (never widens).
- The UI hides what a role cannot do — **and** the server rejects it anyway.
- Permission changes are audited.

---

## 6. Tenant isolation

1. Every request resolves a `TenantContext` from the session's active tenant.
2. Membership must exist and be `active` for that tenant, else 403.
3. Repositories **require** the context; a query without `tenant_id` is a code-review rejection.
4. IDs are never trusted: fetch by id **and** tenant_id together; mismatch → 404 (not 403, to avoid existence leakage).
5. Exports and report generation receive the same context; no "admin bypass" flag exists in Phase 1.
6. Tests: SEC-001 (read by ID), SEC-002 (list with foreign tenant param), SEC-012 (restore mixing).

Known limitation: SQLite cannot enforce RLS. Compensation = single repository entry point + tests. PostgreSQL RLS is planned for production.

---

## 7. Input handling and output safety

- Pydantic schemas with strict types, max lengths, and explicit allowed values.
- Numeric inputs parsed as decimal strings → integers (money) or `Decimal`; floats rejected.
- File uploads (later phases): extension + MIME + magic-byte check, size limit, stored outside web root, never executed, served with `Content-Disposition: attachment`.
- SQL: SQLAlchemy parameter binding only. Raw SQL requires review and named parameters.
- HTML: framework escaping; `dangerouslySetInnerHTML` forbidden without sanitisation review.
- Headers: CSP, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `X-Frame-Options: DENY`, HSTS when TLS exists.
- Errors: generic message to client, full detail to server log with correlation ID.

---

## 8. Secrets management

| Rule | Detail |
|---|---|
| Storage | `.env` locally (git-ignored), environment variables elsewhere |
| Example file | `.env.example` with empty values + comments — never real secrets |
| No defaults | The app refuses to start in non-dev mode without `SECRET_KEY`, `PEPPER`, `DATABASE_URL` |
| Rotation | Documented per secret; sessions invalidated on secret rotation |
| Logging | Secrets never logged; a redaction filter scrubs known keys |
| Repo scan | Pre-commit + CI check for key-like patterns |
| Prohibited | Committing keys, hard-coding credentials, embedding tokens in the frontend bundle |

The frontend receives **no** secrets — only a public API base URL.

---

## 9. Logging, monitoring, incident response

**Log:** structured JSON, UTC, correlation ID per request, actor + tenant when known, outcome. **Never:** passwords, tokens, full card/bank numbers, full payloads of financial documents.

| Event | Logged | Audited |
|---|---|---|
| Login success/failure | yes | yes |
| Permission denial | yes | yes |
| Role/permission change | yes | yes |
| Financial posting (Phase 2) | yes | yes |
| Backup start/finish/fail | yes | yes |
| Restore executed | yes | yes |
| Unhandled exception | yes (stack server-side) | no |

**Incident response (small-team version):** detect → contain (revoke sessions, rotate secrets, isolate DB) → assess scope via audit log → notify owner → fix + regression test → write-up in `docs/BUG_REPORT.md`. No public disclosure claims without evidence.

---

## 10. Security acceptance tests (Phase 1 gate)

| ID | Test | Gate |
|---|---|---|
| SEC-001 | Cross-tenant read by ID blocked | Must pass |
| SEC-002 | Cross-tenant list/filter blocked | Must pass |
| SEC-003 | Privilege escalation blocked | Must pass |
| SEC-004 | Direct API call bypassing hidden UI blocked | Must pass |
| SEC-005 | Export requires permission | Must pass |
| SEC-006 | SQL injection attempts ineffective | Must pass |
| SEC-007 | Stored XSS escaped | Must pass |
| SEC-008 | Session rotation + fixation prevented | Must pass |
| SEC-009 | Idle/absolute expiry enforced | Must pass |
| SEC-010 | Password hash format correct (Argon2id) | Must pass |
| SEC-011 | No secrets in repo/logs | Must pass |
| SEC-014 | Login rate limiting works | Should pass |

**A Phase 1 that fails any "Must pass" item is not complete, regardless of how much code exists.**

---

## 11. What this plan does NOT claim

- Not a certification, audit opinion, or compliance statement.
- No claim that the system is "unhackable" or "100% secure".
- No independent penetration test has been performed.
- GDPR/DPDP/IT Act obligations must be reviewed for the actual launch jurisdiction and date.
- Phase 10 requires independent security review before any production exposure.

---

## 12. Build 0.6 addendum - bearer links and team authority

- **Invite tokens** are 256-bit random URL-safe values. Only SHA-256 hashes are stored; the raw
  token is shown once. Links expire after 7 days, are revoked when replaced, and are rejected for
  inactive businesses. Acceptance requires a new password (12+ characters) or the existing
  account's current password; emails are never silently merged.
- **Statement shares** are bearer links scoped to one tenant, party and date range. Only hashes
  are stored; links expire after 7/30/90 days and can be revoked. Public responses send
  `Cache-Control: no-store` and `X-Robots-Tag: noindex, nofollow`; they expose no internal IDs,
  other parties, ledger accounts or settings. Possession of the link is the access right; treat it
  like a password.
- **Authority:** owner is protected; self role/status changes are rejected; suspend/remove revokes
  all sessions. Every invite, role, status, share and switch action is audited.
- **Known residual risks:** no email verification, no rate limit dedicated to invite tokens beyond
  token entropy, no ownership-transfer workflow, no per-permission editor, no SSO, and no
  independent penetration test. A leaked invite/share link remains usable until expiry/revocation.

## 13. Build 0.7 addendum - ITC review and backup coverage

- **Review authority:** `POST /gstr2b/review` requires `gst.reconcile`, CSRF, an active session and
  membership of the active business. `review_line()` re-checks that the line belongs to that tenant
  and that its import is still active; superseded lines cannot be edited. Cross-tenant line IDs
  return `LINE_NOT_FOUND`.
- **Audit:** each review save writes `gstr2b.review` with the previous state, new state and note.
  Notes are length-limited to 500 characters and HTML-escaped on render.
- **No financial side effect:** review writes only `gstr2b_review` and `audit_log`. It cannot post a
  journal, edit a bill, change a 2B amount or alter GSTR-3B. `itc_hold` is a label, not a legal ITC
  reversal; `accepted` is not an ITC claim.
- **Backup integrity:** the verified-table list now covers every persistent table (29), including
  bank, debit-note, invite, share and GSTR-2B tables. Ephemeral sessions and the backup-run log are
  excluded from source row-count comparison; a schema-coverage test guards future additions.
- **Residual risks:** review notes may contain commercially sensitive free text and are visible to
  every member who can open the GSTR-2B page; there is no reviewer-maker/checker separation, no
  supplier notification and no independent penetration test.

## 14. Build 0.8 addendum - public home page and local demo login

- **Public surface:** `GET /` when signed out and `GET /home` always return a static,
  server-rendered marketing page. It reads no tenant, customer, bank or journal data and contains
  no session-dependent output. It is indexable; the authenticated app and shares remain `noindex`.
- **Demo gate:** `/demo` requires `ARTHIVIO_DEMO_AUTOLOGIN=1` **and** a loopback peer address
  (`127.0.0.1`, `::1` or another `127.*`). It returns a plain 404 when either condition fails.
- **Session creation:** a successful demo request uses the normal server session helper, sets the
  same HttpOnly / SameSite=Lax cookie, and writes `auth.demo_login` with mode `loopback_autologin`.
  It does not create a special role, bypass CSRF on later writes, or skip tenant membership checks.
- **Residual risk:** the flag is a deliberate local bypass. Do not enable it on a shared host or
  bind the server to a public interface. On a loopback host, any local process or user that can
  reach port 8000 can obtain the demo owner session. The route cannot be reached through a remote
  connection because of the peer-address check.
- **No secrets:** the home page contains no API keys, database paths, session IDs, real financial
  data or customer names. The preview numbers are labelled synthetic sample data. The reference's
  customer, country and uptime figures are marked `*` and footnoted as illustrative marketing
  metrics; they are not verified claims and must not be published without evidence.


## 15. Build 0.12 addendum - Excel upload, exports and vendored chart asset

- **Upload authentication:** `.xlsx` import still requires an active session, tenant membership,
  CSRF and the existing permission (`account.manage` for opening balances, `bank.reconcile` for bank
  statements, `gst.reconcile` for GSTR-2B). The file does not bypass the validators or post directly.
- **Multipart parsing:** the removed `cgi` module is not used. A bounded in-process parser reads the
  request body and keeps file parts only for that request. No upload is written to disk, object
  storage or a temporary directory.
- **Size and row limits:** the HTTP layer rejects a POST body over 10 MB before parsing; `app/xlsx_import.py` rejects workbook files over 8 MB and worksheets over 50,000 non-empty rows, and processes at most 100 columns. It reads the workbook in `read_only=True`,
  `data_only=True` mode, uses cached formula values only and never evaluates a formula.
- **Malformed input:** non-ZIP or corrupt workbooks fail with a visible `XlsxImportError`; the
  existing validators still run afterward, so a syntactically valid workbook with bad accounting
  rows cannot post.
- **Residual risk:** `.xlsx` is a ZIP container, so a small compressed file can expand substantially
  in memory before the row limit is reached. The 8 MB/row/column limits reduce but do not eliminate
  a decompression denial-of-service risk. There is no malware scanner, sandboxed parser process or
  per-user upload rate limit. Do not expose uploads to untrusted public users without adding those.
- **Exports:** `/export/workbook.xlsx` and `/export/powerbi.zip` require `report.export` (or the
  owning route's checked permission), are tenant-scoped, use `Cache-Control: no-store`, and contain
  only the active tenant's actuals. The ZIP manifest hashes are integrity aids, not signatures.
- **Chart asset:** ECharts 5.5.1 is vendored locally with its Apache-2.0 notice. There is no runtime
  CDN request, no third-party script execution and no chart data beyond the active tenant's actuals.
- **Insights:** `/api/v1/analytics/insights` requires `report.view`; it calls no external model,
  stores no observation and returns `no-store` JSON. The deterministic rules can still surface
  sensitive financial aggregates to any member with `report.view`; permission scope is unchanged
  from the rest of reporting.


## 16. Build 0.13 addendum - Report Library and management-report exports

- **Read-only reports:** the Report Library and nine management reports require an active session and
  tenant membership; they read only the active tenant's posted rows. They add no write endpoint and
  no schema change.
- **Export permission:** `/export/cash-flow.csv`, `/export/sales-register.csv`,
  `/export/purchase-register.csv` and `/export/expense-breakdown.csv` require `report.export`,
  are tenant-scoped and send `Cache-Control: no-store`.
- **No fabricated or cross-tenant data:** planned reports have no route and no sample rows. Every
  working report recomputes from posted records and shows an explicit empty state rather than
  inventing values.
- **Sensitive aggregates:** ratios, cash flow, customer/vendor registers and working-capital metrics
  reveal financial aggregates to any member with the relevant report permission. Permission scope is
  unchanged from the rest of reporting; there is no per-report ACL beyond the existing permission
  keys.
- **Residual risk:** the CSV exports are not signed or encrypted in transit beyond the deployment's
  TLS. On the free public demo, anyone with the demo owner login can export the synthetic data; do
  not enter real financial data.


## 17. Build 0.14 addendum - first-run setup and offline package

- **First-run takeover guard:** `/setup` exists only while the `user` table is empty. The route is
  local-only by default; a remote request gets a 403 unless the operator sets
  `ARTHIVIO_ALLOW_REMOTE_SETUP=1` for the first run and removes it immediately afterwards.
- **CSRF:** the setup GET issues an HttpOnly `setup_csrf` cookie and a matching hidden form token.
  The POST compares both with `secrets.compare_digest`; a missing or mismatched token returns 403.
- **Atomicity:** owner creation runs inside `BEGIN IMMEDIATE` and re-checks the empty-user condition
  inside the transaction. A failure rolls back the tenant, chart, user and membership together.
- **Closure:** after the first user exists, `/setup` redirects to `/login` and cannot create another
  owner or tenant. There is no self-service registration endpoint.
- **Offline package:** the embedded Python runtime runs the same application code and the same
  local-only binding (`127.0.0.1`) by default. It is not a Windows service and does not open a
  firewall port.
- **Backup:** the external-drive script copies a verified SQLite backup and compares SHA-256. The
  destination is user-supplied and is not authenticated; use a drive you control. Backups contain
  the full books and password hashes, so treat them as sensitive.
- **Residual risk:** the offline package is not code-signed, has no MSI/uninstaller, and has not had
  a clean-machine, antivirus, penetration or independent accounting review. A local attacker with
  access to the Windows account can read the SQLite file and backups.


## 18. Build 0.15 addendum - manual-entry correction and fresh test books

- **Two permissions:** editing a manual entry requires both `journal.post` and `ledger.reverse`.
  The GET edit page checks both; the POST re-checks both and repeats tenant ownership on the
  entry lookup.
- **Atomic correction:** `replace_entry()` runs inside `BEGIN IMMEDIATE`; the reversal is a
  savepoint and the replacement posting is another savepoint. Any validation failure rolls back
  the whole correction, so the books cannot be left with a reversal but no replacement.
- **Reason required:** the correction form rejects an empty reason. `journal.edit` audit metadata
  records the reason, original, reversal, replacement and line count.
- **No overwrite:** the original journal is not updated except for its `status` transition to
  `reversed` by the existing reversal service. Lines, amounts and narration stay unchanged.
- **Tenant isolation:** the entry is looked up by `(tenant_id, entry_id)`; a cross-tenant id returns
  `ENTRY_NOT_FOUND`. The replacement lines are validated against the same tenant, active accounts
  and the period lock.
- **Fresh business:** `/businesses/create` requires `tenant.manage` in the current business. The
  new tenant is separate, the creator becomes its owner, and `business.created` is audited. This is
  not a privilege-escalation path: the caller must already be an owner of the current business.
- **Residual risk:** there is no correction approval workflow, no four-eyes review and no separate
  edit-history screen beyond `audit_log`. A compromised owner session can still correct entries;
  use strong passwords, backups and access control on the Windows account.


## 19. Build 0.16 addendum - report screens and CSV exports

- **No new permission:** the ten new report pages are available to signed-in members, matching the
  existing report pages; the standard role set gives every role `report.view`. All ten CSV exports
  require the existing `report.export`. No role or permission was added.
- **Tenant scope:** every query filters by the session tenant id. Report functions do not accept a
  caller-supplied tenant id; the route passes the session tenant row.
- **Read-only:** the reports do not post, reverse, edit or cache. Trial balance exceptions reports
  malformed journal rows but never repairs them. Stock summary derives quantities but never adjusts
  `item.stock_milli`.
- **CSV boundary:** exports are generated in memory, sent with `no-store`, and use exact decimal
  strings from integer paise. Stock quantities use three-decimal strings.
- **No new sensitive data:** customer names, supplier names and document numbers already appear in
  the existing registers and statements. The new reports do not expose passwords, sessions, hashes,
  audit metadata or cross-tenant rows.
- **Residual risk:** the new pages have not had a penetration test or independent accounting review.
  Credit-limit utilisation is advisory and does not enforce a credit hold.

## 20. Build 0.17 addendum - eighteen report screens, a budget entry screen and additive schema

- **One new permission:** `budget.manage` gates `/budgets` and the create/update/delete POST routes.
  It is granted to owner, admin, manager and accountant. R-901 `/reports/budget` uses the existing
  `report.view`; its CSV uses `report.export`.
- **Tenant scope:** every report query and every budget query filters by the session tenant id. The
  reports and budget screen do not accept a caller-supplied tenant id. The locked-period register
  also filters by tenant.
- **Read-only reports:** the report screens do not post, reverse, edit, cache or repair. Inventory-to-GL
  reconciliation shows a difference but never posts a correction. Reorder/shortage never creates a
  purchase order. Dead/slow stock never writes off an item. R-901 never posts a budget or adjusts an
  actual.
- **Budget writes are audited:** `/budgets` upserts one ledger-month or deletes one row and writes
  `budget.create`, `budget.update` or `budget.delete` to `audit_log`. A budget is planning data and
  cannot change a posted journal.
- **Additive schema:** `item.reorder_level_milli`, `journal_entry.rule_version` and the `budget` table
  are added through the additive migration path. No table or column is dropped or rewritten. The
  item form is permission-checked by the existing `item.manage` permission.
- **CSV boundary:** exports are generated in memory, sent with `no-store`, and use exact decimal
  strings from integer paise. Stock quantities use three-decimal strings.
- **Source limits:** salesperson performance uses the journal creator, not a separate salesperson
  master. Receivables risk is advisory and never blocks a sale. Price variance is not an accusation of
  overcharging. Cash-flow and revenue forecasts are deterministic planning aids, not guarantees.
  Anomaly findings are review prompts, not proof of fraud. Rule version usage is a usage register,
  not a rule-change audit. R-901 only compares stored budgets with posted actuals; it does not
  forecast or infer a missing budget. These limits are printed on the pages.
- **Residual risk:** the new pages have not had a penetration test or independent accounting review.
  There is no approval workflow for reorder levels or budgets, and no FIFO/historical cost layer.

## 21. Build 0.18 addendum - draft sales invoices and R-204

- **Permission reuse:** saving, posting and voiding a draft use the existing `invoice.create`
  permission. R-204 uses `report.view`; its CSV uses `report.export`.
- **Tenant scope:** draft save, post, void and report queries all filter by the session tenant id.
  The routes do not accept a caller-supplied tenant id.
- **No accounting effect before posting:** a draft writes only `invoice` and `invoice_line` rows. It
  has no journal entry, no stock movement, no receivable and no tax-invoice print. Drafts are excluded
  from posted invoice counts, sales, GST, dashboard recent invoices and receivables.
- **Posting is the boundary:** `post_draft_invoice()` re-reads the live item master, aggregates stock
  across duplicate lines, rejects short stock, assigns the next INV number, posts one balanced journal
  and reduces stock in one transaction. A failed post leaves the draft untouched.
- **Void requires a reason:** `void_draft_invoice()` refuses an empty reason, sets `status='void'`
  and writes `invoice.void_draft`. Rows are never deleted.
- **Audit:** draft creation, posting and voiding write `invoice.draft_create`, `invoice.post` and
  `invoice.void_draft` with the actor and relevant amounts/numbers.
- **Print boundary:** a draft cannot print as a tax invoice; the print route returns HTTP 400. This
  prevents an unposted document from being shared as a GST tax invoice.
- **Residual risk:** there is no draft approval workflow, no in-place draft-line editing and no
  draft-bill or draft-journal workflow. The new paths have not had a penetration test or independent
  accounting review.

## 22. Build 0.19 addendum - advanced registers and consolidation

- **Permission reuse:** dimensions and cost-centre budgets use `budget.manage`; batches and
  production orders use `item.manage`; all advanced report pages use `report.view`; all CSV exports
  use `report.export`. No new permission string was added.
- **Tenant scope:** every register and report query filters by the session tenant id. Dimension
  creation and update resolve the tenant from the session, never from a caller-supplied tenant id.
  `post_journal` rejects a dimension id that is inactive or belongs to another tenant.
- **No hidden accounting effect:** the batch and production registers write only their own tables.
  They do not post a journal, change `item.stock_milli`, value inventory or compute tax. The pages
  say so explicitly.
- **Consolidation authorisation:** R-1004 first calls `advanced.consolidation_tenants(conn,
  user_id)`, which returns only active tenants where the user has an active owner or admin
  membership. The report function receives only that list. A user cannot request another tenant id
  through the query string.
- **Intercompany treatment:** `journal_entry.is_intercompany` is set only from the manual journal
  form. R-1004 excludes flagged entries from combined totals and reports their count and value
  separately. There is no automatic matching or elimination engine, so the screen cannot claim a
  complete elimination.
- **Audit:** dimension create/update, cost-centre budget set, batch create/void, production-order
  create/status and journal posting write normal audit events. Reversals preserve the original
  dimension tag and intercompany flag.
- **CSV boundary:** the eight new exports are generated in memory, sent with `no-store`, and use
  exact decimal strings from integer paise and three-decimal quantities. The consolidated export
  re-checks the owner/admin tenant list before reading.
- **Residual risk:** dimension tags are available on manual journal lines only; invoice, bill,
  receipt and payment forms do not expose the selector. There is no allocation, recharge, timesheet,
  batch-costing or intercompany matching engine. The new pages have not had a penetration test or
  independent accounting review.

## 23. Build 0.20 addendum - corrections, drafts and approvals

- **New permission:** `document.approve` is additive and held by owner and admin. It gates
  `/approvals` and the approve/reject actions. A user without it can still create and edit their own
  drafts but cannot approve them.
- **Tenant scope:** every draft, correction and approval query filters by the session tenant id.
  A draft or posted document id from another tenant returns not-found, not a cross-tenant edit.
- **Append-only history:** correction writes a reversal journal and marks the original document
  `void`; it never deletes or rewrites the posted row. The replacement is linked through
  `replaces_id`, so both documents remain auditable.
- **Replacement guards:** an invoice or bill referenced by posted payments or credit/debit notes
  cannot be replaced. A bill whose stock has already been sold or consumed is blocked with
  `BILL_STOCK_CONSUMED`. These guards prevent a correction from silently breaking allocations or
  driving stock negative.
- **Draft isolation:** draft bills and journals live in separate tables and do not touch the ledger,
  stock, payables, receivables or GST totals. Posting reuses the normal accounting functions with
  idempotency keys, so a repeated post returns the same result instead of double-posting.
- **Approval lock:** a draft with `approval_status='pending'` cannot be edited. Approve, reject with
  reason, withdraw and void all write audit events.
- **Opening balance:** direct edit reverses the old opening journal and posts the replacement in one
  transaction. The old opening entry remains in the ledger as reversed history.
- **Residual risk:** approval is a single optional step, not amount/department routing or a
  multi-step chain. Replacement is refused rather than auto-creating a credit/debit note. The new
  correction and approval pages have not had a penetration test or independent accounting review.

## 24. Build 0.21 addendum - public-surface hardening

- **Response headers:** every HTML, JSON, static and export response sends a Content Security
  Policy, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
  `X-Frame-Options: DENY`, a restrictive `Permissions-Policy`, `Cross-Origin-Opener-Policy` and
  `Cross-Origin-Resource-Policy`.
- **CSP:** `default-src 'self'`; local scripts, styles, fonts and data images are allowed. Inline
  styles and scripts remain allowed because the server-rendered pages use them; this is a
  deliberate compatibility trade-off, not a claim that inline injection is impossible.
- **HSTS:** sent only when the request is HTTPS (`X-Forwarded-Proto: https`) or the operator sets
  `ARTHIVIO_SECURE_COOKIES=1`. Plain local HTTP does not get HSTS.
- **Secure cookies:** session, first-run setup and theme cookies gain `Secure` behind HTTPS.
  `HttpOnly` and `SameSite=Lax` remain on the session and setup cookies.
- **Restore drill:** `scripts/restore_drill.py` verifies a copy of the backup, starts a second app
  process against the copy, logs in and reads a report. It never restores over the live database.
- **Load test:** `scripts/load_test.py` is read-only. It does not post financial documents.
- **Residual risk:** headers and a smoke load test are not a penetration test or a production
  capacity test. Inline script/style allowances reduce CSP strength. The app still has no
  independent security review, WAF, DDoS protection, intrusion detection or production monitoring.
