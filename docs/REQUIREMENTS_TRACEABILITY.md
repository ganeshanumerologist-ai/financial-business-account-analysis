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


---

## 9. Status after Build 0.1 (2026-10-24)

The rows in sections 2–7 were written before any code existed. This table is the current
truth and supersedes their status column only; the requirement text and test IDs stay.

| Capability | Requirement area | Test evidence | Status |
|---|---|---|---|
| Invoice creation with GST | REQ-ACC / invoicing | `TestInvoice` (7 tests) | VERIFIED |
| Double-entry integrity | FIN-01…FIN-09 | `TestPosting` (6), `TestReports` (8) | VERIFIED |
| Ledger, TB, P&L, balance sheet | reporting | `TestReports`, `test_web.test_04` | VERIFIED |
| Customer-wise receivables | AR / statements | `test_customer_statement_matches_receivable_control` | VERIFIED |
| Authentication and sessions | SEC-01…SEC-04 | `TestSecurity` (5) | VERIFIED |
| RBAC and least privilege | SEC-05 | `test_rbac_denies_readonly_write` | VERIFIED |
| Tenant isolation | SEC-06 | cross-tenant tests (3) | VERIFIED |
| CSRF protection | SEC-07 | `test_06_csrf_required` | VERIFIED |
| Audit trail | SEC-08 | rows written on postings/logins | PARTIAL |
| Backup and restore | OPS-01 | — | NOT IMPLEMENTED |
| Payments/receipts, AP, GST returns, exports | ACC / compliance | — | NOT IMPLEMENTED |
| PostgreSQL, hosting, Next.js UI | NFR / deployment | — | NOT IMPLEMENTED |


---

## 10. Status after Build 0.2 (2026-10-24)

| Capability | Requirement area | Test evidence | Status |
|---|---|---|---|
| Sales cycle: invoice to receipt to outstanding | ACC / AR | `TestReceipts` (7), `test_web.test_10` | VERIFIED |
| Purchase cycle: bill to vendor payment to payable | ACC / AP | `TestBills` (7), `test_web.test_11` | VERIFIED |
| Credit notes / sales returns | ACC / corrections | `TestCreditNotes` (4), `test_web.test_12` | VERIFIED |
| Ageing (AR and AP, four buckets) | reporting | `TestAgeingAndGST` (4) | VERIFIED |
| GST summary + sales/purchase registers | compliance | `TestAgeingAndGST.test_gst_summary_nets_output_and_input`, `/reports/gst` | PARTIAL (working summary, not a filed return) |
| Day book and manual journals | books | `TestAgeingAndGST.test_day_book_lists_all_vouchers`, `test_web.test_14` | VERIFIED |
| CSV exports | reporting / export | `test_web.test_13_csv_exports`, RBAC `report.export` | VERIFIED |
| Backup + restore verification | OPS-01 / BAK-001..003 | `TestBackup` (5), `test_web.test_15`, recorded drill | VERIFIED |
| Atomic composite postings | FIN-01 / integrity | `TestPosting`, `TestBills`, `TestReceipts`, `TestCreditNotes` | VERIFIED |
| Weighted-average inventory | inventory | `test_weighted_average_cost`, `test_purchase_at_current_cost_keeps_average` | VERIFIED |
| PDF, GSTR-1 JSON, debit notes, bank reconciliation, multi-user admin UI | various | - | NOT IMPLEMENTED |
| PostgreSQL, Next.js, hosting | NFR / deployment | - | NOT IMPLEMENTED |

Gate 9 (backup created) and gate 10 (restore verified with matching counts) from ?7 can now
be marked PASS with evidence in `docs/TEST_RESULTS.md` ?7.4. Gate 6 (export permission) is
enforced by `security.require(..., "report.export")` and covered by the HTTP export test.


## 11. Status after Build 0.3 (2026-10-24)

| Requirement area | Status | Evidence |
|---|---|---|
| GST-compliant invoice output | **Verified (print view)** | `test_16_settings_and_print_invoice`, browser check of INV-00011 |
| GSTR-1 preparation data | **Verified (working export)** | `tests/test_gstr1.py`, CSV/JSON fetched in browser |
| Supplier/buyer master data for GST | **Verified** | settings validation + migration test |
| Schema evolution without data loss | **Verified** | `MigrationTest`, in-place demo DB migration |
| GST portal upload / official return | **Not implemented** | out of scope for this slice; export is labelled a working aid |
| Debit notes / bank reconciliation | **Not implemented** | next slice |
| PDF binary / e-invoice | **Not implemented** | browser Print / Save as PDF only |

Financial invariants remain unchanged: integer paise, balanced postings, immutable entries,
tenant-scoped queries. The new print/export code reads posted documents and never writes
accounting data.

## 12. Status after Build 0.4 (2026-10-24)

| Requirement area | Status | Evidence |
|---|---|---|
| Purchase returns / debit notes | **Verified** | `tests/test_debit_notes.py` (13), browser check on BILL-00003 |
| Debit note ↔ payable / GST / stock | **Verified** | bill outstanding reduced; input GST reversed; average cost restated; vendor statement split |
| Bank CSV import and dedup | **Verified** | `tests/test_bank.py` (18), browser import 2 new / 0 duplicate |
| Bank matching (auto + manual + unmatch) | **Verified** | browser auto-match 2/2, unmatch; `test_manual_match_and_unmatch`, `test_auto_match_unambiguous` |
| Bank reconciliation difference | **Verified** | statement net 7,818.00 vs ledger -182.00, difference -8,000.00 explained by unmatched rent |
| Bank/debit-note permissions and audit | **Verified** | `bank.reconcile`, `debit_note.create`; audit events written in unit/HTTP tests |
| Partial / one-to-many matching | **Not implemented** | exact full-amount matching only |
| Auto-post bank charges/interest | **Not implemented** | unmatched lines are surfaced, not posted |
| GSTR-2/2B, portal upload | **Not implemented** | GSTR-1 working export and GSTR-3B working summary exist; neither is a filed return |
| Multi-user admin UI, PostgreSQL, Next.js | **Not implemented** | future phases |

## 13. Status after Build 0.5 (2026-10-24)

| Requirement area | Status | Evidence |
|---|---|---|
| GSTR-3B working summary | **Verified (working aid)** | `tests/test_gstr3b.py` (8), `/reports/gstr3b` browser check |
| GSTR-1 net taxable/output vs GSTR-3B | **Verified** | 6/6 reconciliation checks OK for June and October 2026 |
| Output/ITC vs tax ledger | **Verified** | document output tax and ITC compared with `gst_summary`; manual-journal mismatch test flags CHECK |
| Month-scoped reporting | **Verified** | month bounds, leap February, month filter, empty month and cross-tenant tests |
| GSTR-3B CSV export | **Verified** | `/export/gstr3b.csv?month=2026-10` HTTP 200, `test_21_gstr3b_page_and_csv` |
| GST portal upload / official GSTR-3B JSON | **Not implemented** | working CSV only; no filing claim |
| Cross-utilisation, RCM, zero-rated/exempt, official GSTR-2B | **Not implemented** | head-wise set-off only; a separate working 3B-vs-2B comparison exists; disclosed on page and in docs |
| Multi-user admin UI, PostgreSQL, Next.js | **Not implemented** | future phases |

## 14. Status after Build 0.7 (2026-10-25)

| Requirement area | Status | Evidence |
|---|---|---|
| Invite creation and one-time acceptance | **Verified** | `tests/test_team_sharing.py` (7 team tests), `test_22_team_invite_accept_and_role_change` |
| Existing-user invite without silent account merge | **Verified** | current password required; wrong password leaves membership unchanged |
| Owner protection and self-change guards | **Verified** | owner role locked, self role/status changes rejected, admin cannot promote to owner |
| Suspend/remove revokes access | **Verified** | session revoked immediately; `test_admin_can_change_role_and_suspend_revokes_sessions` |
| Business switcher | **Verified** | active membership checked on switch; `test_25_business_switcher_checks_membership` |
| Share link scope/expiry/revocation | **Verified** | tenant/party/date scope, 7/30/90 days, revoke and expired states; 4 sharing tests |
| Public statement privacy | **Verified** | no login, no internal IDs, `noindex/nofollow`, `Cache-Control: no-store`, view count |
| GSTR-2B CSV parse/import | **Verified** | preamble, aliases, GSTIN/date validation, SHA-256 dedup, supersede, history; 17 GSTR-2B tests |
| GSTR-2B matching | **Verified** | exact match, mismatch reported not corrected, missing both directions, prior-period match, duplicate warnings |
| ITC review workflow | **Verified** | open/follow-up/hold/accepted, note, audit, active-import-only, tenant scope, `gst.reconcile` |
| 3B vs 2B comparison | **Verified** | books eligible/gross/reversal vs 2B, gap, review buckets, warnings; no posting |
| GSTR-2B export | **Verified** | `/export/gstr2b.csv?month=2026-08` HTTP 200; rows, review columns and comparison in CSV |
| Email delivery, ownership transfer, per-permission editor | **Not implemented** | links are manual; disclosed in README/architecture |
| Official GSTR-2B portal schema/integration, actual ITC claim | **Not implemented** | working CSV and annotations only; explicitly not a filed return |
| PostgreSQL, Next.js | **Not implemented** | future phases |

