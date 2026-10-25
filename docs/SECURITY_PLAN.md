# ARTHIVIO — Security Plan

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-10-24 |
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

| Role | Tenancy | Users | Ledger | Invoices | Inventory | Reports | Export | Backup |
|---|---|---|---|---|---|---|---|---|
| owner | manage | full | post/reverse | full | full | all | yes | run/restore |
| admin | manage | full | post/reverse | full | full | all | yes | run |
| manager | — | invite | post | approve | adjust | all | yes | — |
| accountant | — | — | post/reverse | create | view | all | yes | — |
| cashier | — | — | — | create/receipt | view | own-day | no | — |
| sales | — | — | — | create | view | own | no | — |
| inventory | — | — | — | — | full | stock | yes | — |
| readonly | — | — | view | view | view | view | no | — |

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
