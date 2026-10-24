# ARTHIVIO — Requirements Traceability

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-10-24 |
| Purpose | Prove every requirement has a planned module, a test, and a documented status |
| Source | `docs/PROJECT_SPEC.md` → `docs/REQUIREMENTS.md` → modules → tests |

Status: **NS** = Not started · **IP** = In progress · **DONE** (requires passing tests) · **BLOCKED**

> Today every implementation row is **NS**. That is the honest baseline; the matrix exists so progress cannot be claimed without evidence.

---

## 1. Foundation requirements

| REQ | Requirement | Module | Tests | Docs | Status |
|---|---|---|---|---|---|
| REQ-002 | Tenant hierarchy | `core/tenancy`, models | SEC-001, SEC-002 | ARCHITECTURE §3, DATABASE_DESIGN §3 | NS |
| REQ-003 | Multi-business membership | `membership` | SEC-001 | DB §3.4 | NS |
| REQ-004 | Server-side tenant isolation | repository layer | SEC-001, SEC-002, SEC-012 | SECURITY_PLAN §6 | NS |
| REQ-005 | RBAC + least privilege | `core/authz` | SEC-003, SEC-004, SEC-005 | SECURITY_PLAN §5 | NS |
| REQ-006 | Auth + sessions + MFA | `core/auth` | SEC-008, SEC-009, SEC-010, SEC-014 | SECURITY_PLAN §4 | NS |
| REQ-007 | Append-only audit log | `audit` | SEC-001 (audit case) | DB §3.7 | NS |
| REQ-008 | Backup + verified restore | `scripts/backup`, `scripts/restore-verify` | BAK-001…008 | BACKUP_AND_RECOVERY | NS |
| REQ-009 | Secrets via env | `core/config` | SEC-011 | SECURITY_PLAN §8 | NS |

---

## 2. Financial core requirements

| REQ | Requirement | Module | Tests | Docs | Status |
|---|---|---|---|---|---|
| REQ-010 | Chart of accounts | `services/accounts` | ACC-001…005 | ACCOUNTING_RULES §3 | NS |
| REQ-011 | Balanced double-entry posting | `services/posting` | ACC-001, ACC-002 | ACCOUNTING_RULES §3 | NS |
| REQ-012 | General ledger | `services/reports/gl` | ACC-005, REP-001 | REPORT_CATALOG R-105 | NS |
| REQ-013 | TB / P&L / BS / CF | `services/reports/statements` | ACC-003…007, REP-001 | REPORT_CATALOG R-101…104 | NS |
| REQ-014 | Immutable postings + reversal | `services/reversal` | ACC-014, ACC-015 | ACCOUNTING_RULES §11 | NS |
| REQ-015 | Period close/lock | `services/periods` | ACC-013, DT-002 | ACCOUNTING_RULES §6 | NS |
| REQ-016 | Idempotent posting | `services/idempotency` | DUP-001…004 | ACCOUNTING_RULES §5 | NS |
| REQ-017 | AR/AP subledgers | `services/subledger` | ACC-008, ACC-009, REP-002 | REPORT_CATALOG R-304, R-402 | NS |
| REQ-018 | Invoicing + tax + rounding | `services/billing` | ACC-012, EXP-001, REP-001 | ACCOUNTING_RULES §2, §7 | NS |
| REQ-019 | Receipts/payments/notes | `services/payments` | DUP-002, REP-001 | REPORT_CATALOG R-305 | NS |

---

## 3. Operations requirements

| REQ | Requirement | Module | Tests | Docs | Status |
|---|---|---|---|---|---|
| REQ-020 | Inventory movements | `services/inventory` | ACC-010, REC-001 | ACCOUNTING_RULES §10 | NS |
| REQ-021 | Stock formula | `services/inventory` | ACC-010 | REPORT_CATALOG R-501 | NS |
| REQ-022 | Barcode | `services/barcode` | UI-003 | REPORT_CATALOG R-502 | NS |
| REQ-023 | Offline sync | `offline` | DUP-001, DUP-004 | ARCHITECTURE §10 | NS |
| REQ-024 | Report catalogue | `services/reports` | REP-001…007 | REPORT_CATALOG | NS |
| REQ-025 | Import validation | `services/import` | IMP-001…007 | FEATURE_INVENTORY IO-01…10 | NS |
| REQ-026 | Export + permissions | `services/export` | EXP-001…005, SEC-005 | FEATURE_INVENTORY IO-05…10 | NS |
| REQ-027 | AI insights | `services/ai` | REP-007, SEC-001 | API_INTEGRATIONS INT-10 | NS |
| REQ-028 | Hindi/English | `i18n` | UI-008 | REQUIREMENTS §1 | NS |
| REQ-029 | Industry templates | `templates/*` | per-template suite | ROADMAP Phase 7 | NS |
| REQ-030 | External integrations | `integrations/*` | per-integration suite | API_INTEGRATIONS | NS |

---

## 4. Financial invariants

| ID | Requirement | Tests | Doc reference | Status |
|---|---|---|---|---|
| FIN-001 | Decimal-only money | ACC-011 | ACCOUNTING_RULES §1 | NS |
| FIN-002 | Rounding + residual allocation | ACC-012 | ACCOUNTING_RULES §2 | NS |
| FIN-003 | Every posting balances | ACC-001 | ACCOUNTING_RULES §3 | NS |
| FIN-004 | Source traceability | REP-002 | ACCOUNTING_RULES §8 | NS |
| FIN-005 | Report = independent recalculation | REP-001 | TEST_PLAN §5.4 | NS |
| FIN-006 | Block on invariant failure | REP-006 | ACCOUNTING_RULES §9 | NS |
| FIN-007 | Opening + movements = closing | ACC-005, ACC-007 | ACCOUNTING_RULES §6 | NS |
| FIN-008 | Six validation layers | ACC-*, REC-*, REP-006 | PROJECT_SPEC §13 | NS |
| FIN-009 | Actual vs estimate vs forecast | REP-007 | REPORT_CATALOG §11 | NS |

---

## 5. Test coverage map (application tests defined in `TEST_PLAN.md`)

| Test family | Count | Requirement coverage |
|---|---|---|
| ACC-* | 15 | REQ-010…019, FIN-001…007 |
| DUP-* / DT-* | 9 | REQ-016, REQ-023 |
| REP-* / REC-* | 9 | REQ-012…013, REQ-024, FIN-004…006 |
| IMP-* / EXP-* | 12 | REQ-025, REQ-026 |
| SEC-* | 14 | REQ-004…009 |
| BAK-* | 8 | REQ-008 |
| UI-* | 11 | REQ-028, NFR-004…006 |
| **Total** | **78** | |

Executed against application code: **0**.

---

## 6. Documentation coverage

| Spec-required document | Exists | Notes |
|---|---|---|
| README.md | ✅ | Status + Hindi summary |
| docs/REQUIREMENTS.md | ✅ | 30 product + 9 financial + 11 security + 10 NFR |
| docs/ARCHITECTURE.md | ✅ | Decided stack, boundaries, layout |
| docs/DATABASE_DESIGN.md | ✅ | Phase 1 schema + Phase 2 outline |
| docs/SECURITY_PLAN.md | ✅ | Threat model, RBAC, gates |
| docs/BACKUP_AND_RECOVERY.md | ✅ | RPO/RTO, restore drill, honest status |
| docs/ACCOUNTING_RULES.md | ✅ | Money, rounding, posting, reports |
| docs/COMPLIANCE_MATRIX.md | ✅ | 31 rows, 0 implemented |
| docs/API_INTEGRATIONS.md | ✅ | 12 planned, 0 connected |
| docs/REPORT_CATALOG.md | ✅ | 66 reports, 0 implemented |
| docs/TEST_PLAN.md | ✅ | 90 cases |
| docs/DEVELOPMENT_ROADMAP.md | ✅ | Phases + gates |
| docs/DECISION_LOG.md | ✅ | 7 decisions + 8 deferred |
| docs/REQUIREMENTS_TRACEABILITY.md | ✅ | This file |
| docs/SOFTWARE_AUDIT.md | ✅ | Evidence-based audit |
| docs/FEATURE_INVENTORY.md | ✅ | 142 items, all NS |
| docs/TEST_RESULTS.md | ✅ | 12 checks executed |
| docs/BUG_REPORT.md | ✅ | 9 open defects |
| docs/PROJECT_SPEC.md | ✅ | Hash-verified source of truth |

---

## 7. Phase 1 gate checklist (must all be PASS with evidence)

| # | Criterion | Test | Status |
|---|---|---|---|
| 1 | Register / login / logout work | manual + SEC-008 | NS |
| 2 | Session expiry enforced | SEC-009 | NS |
| 3 | Cross-tenant read blocked | SEC-001 | NS |
| 4 | Cross-tenant list blocked | SEC-002 | NS |
| 5 | Privilege escalation blocked | SEC-003, SEC-004 | NS |
| 6 | Export permission enforced | SEC-005 | NS |
| 7 | Audit log captures key events | audit test | NS |
| 8 | No secrets in repo/logs | SEC-011 | NS |
| 9 | Backup created | BAK-001 | NS |
| 10 | Restore verified with matching counts | BAK-003 | NS |
| 11 | No financial module written | scope review | NS |
| 12 | Docs synchronized | doc review | NS |

**Phase 1 is not complete until all 12 rows read PASS in `docs/TEST_RESULTS.md`.**

---

## 8. Traceability rules

1. A requirement without a test is a wish, not a requirement.
2. A test without recorded output is not evidence.
3. A doc row that says DONE without a passing test ID is a documentation defect.
4. Removing a requirement requires a decision-log entry, never a silent deletion.
