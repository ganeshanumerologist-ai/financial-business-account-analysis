# ARTHIVIO — Requirements

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-10-28 |
| Status | Draft for owner approval. The per-row status column below is the original full-scope baseline and is stale; current Build 0.12 evidence is in `docs/REQUIREMENTS_TRACEABILITY.md` section 20. |
| Source of truth | `docs/PROJECT_SPEC.md` (763 lines, SHA-256 `4556C714…`) |
| Stack | Original Option A was Next.js + FastAPI; the delivered local prototype is standard-library Python + SQLite under D-007, with approved `openpyxl` for `.xlsx` workbooks |

Priority: **P0** = release-gate / must exist before any financial feature · **P1** = required for usable product · **P2** = valuable, later phase.

---

> **Status note (2026-10-28):** This is the original full-scope requirements list. The `Status`
> column has not been maintained row-by-row and must not be read as the current build state. See
> `docs/REQUIREMENTS_TRACEABILITY.md` section 20 for the evidence-backed status through Build 0.12
> and `docs/FEATURE_INVENTORY.md` section 20 for the honest implemented/partial/missing inventory.

## 1. Product requirements

| ID | Requirement | Priority | Phase | Status |
|---|---|---|---|---|
| REQ-001 | Public marketing site, separate from the authenticated app | P1 | 6 | Not started |
| REQ-002 | Multi-tenant workspaces: User → Tenant → Legal Entity → Branch → Warehouse → Department/Project | P0 | 1 | Not started |
| REQ-003 | One user may access multiple businesses; one business may have multiple users | P0 | 1 | Not started |
| REQ-004 | Server-side tenant isolation on every request (never UI-only) | P0 | 1 | Not started |
| REQ-005 | Role-based, least-privilege permissions (owner, admin, manager, accountant, cashier, sales, inventory, read-only) | P0 | 1 | Not started |
| REQ-006 | Authentication with strong password policy, secure sessions, optional MFA | P0 | 1 | Not started |
| REQ-007 | Append-only audit log for security- and finance-relevant actions | P0 | 1 | Not started |
| REQ-008 | Automated backup + **verified restore** procedure | P0 | 1 | Not started |
| REQ-009 | Secrets only via environment variables; never in source or logs | P0 | 1 | Not started |
| REQ-010 | Configurable chart of accounts | P0 | 2 | Not started |
| REQ-011 | Balanced double-entry journal engine, atomic posting | P0 | 2 | Not started |
| REQ-012 | General ledger with opening + movements = closing | P0 | 2 | Not started |
| REQ-013 | Trial balance, P&L, Balance Sheet, Cash Flow reconciling to ledger | P0 | 2 | Not started |
| REQ-014 | Posted entries immutable; corrections via reversal with reason + approval | P0 | 2 | Not started |
| REQ-015 | Period close/lock; postings to locked periods rejected | P0 | 2 | Not started |
| REQ-016 | Idempotent posting; duplicate document prevention | P0 | 2 | Not started |
| REQ-017 | AR/AP subledgers reconciling to GL control accounts | P0 | 3 | Not started |
| REQ-018 | Invoicing: numbering, line items, discounts, tax, rounding, totals | P0 | 3 | Not started |
| REQ-019 | Receipts, payments, credit/debit notes, partial payments, advances | P0 | 3 | Not started |
| REQ-020 | Inventory movements with full traceability | P1 | 4 | Not started |
| REQ-021 | Stock reconciliation formula per spec §11 | P1 | 4 | Not started |
| REQ-022 | Barcode scan + label printing (supported formats only) | P2 | 4 | Not started |
| REQ-023 | Offline billing queue with idempotent sync and conflict surfacing | P1 | 5 | Not started |
| REQ-024 | Report catalogue (≈150 templates) with defined source/formula/drill-down | P1 | 6 | Not started |
| REQ-025 | Excel/CSV import with validation and all-or-nothing writes | P1 | 3/4 | Not started |
| REQ-026 | Excel/CSV/PDF export, permission-enforced | P1 | 3/6 | Not started |
| REQ-027 | AI insights grounded in authorised data, clearly labelled | P2 | 8 | Not started |
| REQ-028 | Hindi + English UI, translated validation messages | P1 | 6 | Not started |
| REQ-029 | Industry templates (15) | P2 | 7 | Not started |
| REQ-030 | External tax/payment/bank integrations (only after verified access) | P2 | 9 | Not started |

---

## 2. Financial correctness requirements

| ID | Requirement | Priority | Phase |
|---|---|---|---|
| FIN-001 | Money stored and computed as exact decimal — no binary floating point in authoritative paths | P0 | 1 |
| FIN-002 | Documented precision/rounding policy per currency; residual allocation deterministic | P0 | 2 |
| FIN-003 | Every posting balances at posting precision or is blocked | P0 | 2 |
| FIN-004 | Every figure traceable to source document, formula, filters, period, rule version | P0 | 2 |
| FIN-005 | Reports must equal an independent recalculation of source rows | P0 | 2 |
| FIN-006 | Invariant failure blocks the posting/report rather than guessing | P0 | 2 |
| FIN-007 | Opening balances carried exactly once; opening + movements = closing | P0 | 2 |
| FIN-008 | Six validation layers implemented (transaction, cross-ledger, cross-report, anomaly, independent recalc, approval/audit) | P0 | 2–3 |
| FIN-009 | Actuals, estimates, forecasts visually and structurally separated | P1 | 6 |

---

## 3. Security requirements

| ID | Requirement | Priority | Phase |
|---|---|---|---|
| SEC-001 | Every query scoped by `tenant_id` at the data-access layer; cross-tenant access returns 404/403 | P0 | 1 |
| SEC-002 | Authorisation enforced on the server for every endpoint and every export | P0 | 1 |
| SEC-003 | Argon2id password hashing; minimum length + breach-resistant policy | P0 | 1 |
| SEC-004 | Server-side sessions, HttpOnly + Secure + SameSite cookies, rotation on login, idle + absolute expiry | P0 | 1 |
| SEC-005 | CSRF protection on state-changing requests | P0 | 1 |
| SEC-006 | Rate limiting on auth endpoints | P1 | 1 |
| SEC-007 | No secrets in repo, logs, or error responses | P0 | 1 |
| SEC-008 | Audit log records actor, tenant, action, target, timestamp, result | P0 | 1 |
| SEC-009 | Encryption in transit (TLS) in any non-local environment | P0 | 10 |
| SEC-010 | Automated dependency and secret scanning | P1 | 10 |
| SEC-011 | Tested cross-tenant and privilege-escalation tests in CI | P0 | 1 |

---

## 4. Quality / operational requirements

| ID | Requirement | Target | Phase |
|---|---|---|---|
| NFR-001 | Cold start of dev app | < 5 s | 1 |
| NFR-002 | List page p95 response (1k rows) | < 300 ms | 2 |
| NFR-003 | Report generation (10k journal lines) | < 3 s | 2 |
| NFR-004 | Accessibility | WCAG 2.1 AA on core screens | 6 |
| NFR-005 | Responsive breakpoints | 360 / 768 / 1440 / 2560 / 3840 px, no clipping | 6 |
| NFR-006 | Visual output | resolution-independent: SVG icons, CSS layout, no raster upscaling | 6 |
| NFR-007 | Backup RPO / RTO (Phase 1, local) | RPO ≤ 24 h · RTO ≤ 30 min | 1 |
| NFR-008 | Restore drill | executed and evidenced before Phase 1 sign-off | 1 |
| NFR-009 | Test coverage on critical calc modules | ≥ 90% line, 100% of FIN-001…008 paths | 2 |
| NFR-010 | Logging | structured JSON, correlation ID per request, no PII in logs | 1 |

---

## 5. Constraints

1. **No paid services.** No Firebase, no managed DB, no paid APIs without a new decision-log entry + owner approval.
2. **No production deployment** during Phases 1–2.
3. **No real customer/bank data** in dev or tests; synthetic fixtures only.
4. **No automatic GitHub push.**
5. Python 3.14.6 is the only installed interpreter; portable Node 20.20.2 + git 2.56.0 are off-`PATH`.
6. PostgreSQL is not installed → file-based DB for Phase 1, PostgreSQL-ready schema.

---

## 6. Assumptions (must be confirmed or corrected)

| ID | Assumption | Risk if wrong |
|---|---|---|
| AS-001 | The two PNG mockups are the only visual reference available | UI rework when the real theme appears |
| AS-002 | Python 3.14-compatible wheels exist for FastAPI/SQLAlchemy/Alembic/Argon2 | May need a second interpreter or older versions |
| AS-003 | SQLite is acceptable for Phase 1 single-user dev, with PostgreSQL for real multi-user use | Concurrency limits if used in production |
| AS-004 | Owner operates on Windows, single machine, no server | Backup/RTO design must stay local |
| AS-005 | Indian GST specifics will be professionally reviewed before any tax output | Non-compliant tax calculations if skipped |

---

## 7. Explicitly out of scope for Phase 1

Billing, invoicing, journals, ledgers, financial statements, inventory, offline sync, reports, AI, tax integrations, public marketing site. Phase 1 is **auth + tenancy + RBAC + audit + backups only**.

---

## 8. Acceptance criteria for Phase 1

Phase 1 passes only when **all** are true and evidenced in `docs/TEST_RESULTS.md`:

- [ ] A user can register, log in, log out; sessions expire correctly.
- [ ] A second tenant's data is unreachable by ID, by list, and by export (tested).
- [ ] Every role can do exactly its allowed actions and nothing more (tested).
- [ ] Audit log captures login, role change, and data mutation with actor + tenant.
- [ ] Secrets are read from env; a scan finds none in the repo.
- [ ] A backup is created, then **restored into a clean DB**, and row counts + checksums match.
- [ ] Cross-tenant and privilege-escalation test suites pass.
- [ ] No financial module has been written yet (scope discipline).

---

## 9. Open questions for the owner

| ID | Question | Blocks |
|---|---|---|
| OQ-01 | Location of the home-page theme (path or link), or confirm the PNG mockups are the theme | UI phase (6) — **not Phase 1** |
| OQ-02 | Primary launch jurisdiction: India-only first, or multi-country from day one? | Tax design (Phase 3/9) |
| OQ-03 | Default currency and financial year (e.g. INR, 1 Apr – 31 Mar)? | Phase 2 |
| OQ-04 | Should the two PNGs be deleted from the repo once a real theme exists? (kept for now) | Housekeeping |
