# ARTHIVIO — Requirements Traceability

| Field | Value |
|---|---|
| Version | 1.2 |
| Date | 2026-11-05 |
| Purpose | Prove every requirement has a planned module, a test, and a documented status |
| Source | `docs/PROJECT_SPEC.md` → `docs/REQUIREMENTS.md` → modules → tests |

Status: **NS** = Not started · **IP** = In progress · **DONE** (requires passing tests) · **BLOCKED**

> The early baseline rows show **NS** because they record the empty starting point. Current
> evidence-backed status is in section 26 (Build 0.18); the matrix exists so progress cannot be claimed
> without evidence.

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
| docs/API_INTEGRATIONS.md | ✅ | 11 planned, 0 connected |
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
| Fresh test business | **Verified** | owner-only `/businesses/create` creates a separate tenant with standard chart and zero entries, makes creator owner, audits `business.created` and switches session; `test_create_business_is_empty_and_makes_creator_owner`, `test_web.test_48` |
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


## 15. Status after Build 0.8 (2026-10-25)

| Requirement area | Status | Evidence |
|---|---|---|
| Public home page | **Verified** | unauthenticated `GET /` and `GET /home` return the reference-matched standalone landing page; its dark hero supports four cookie-backed colour variants and a visible picker; `test_00_public_landing_page`, `test_37`, `test_38` |
| Responsive visual design | **Verified** | desktop and narrow-mobile browser checks, no horizontal overflow, stacked hero/preview; earlier `/home` Lighthouse 100/100/100 baseline, not re-run after the landing colour picker |
| Synthetic preview honesty | **Verified** | preview labelled "Sample workspace ? synthetic data"; reference metrics marked `*` and footnoted illustrative; no customer logos or testimonials |
| Authenticated dashboard preserved | **Verified** | `test_03_login_and_dashboard` still renders ledger figures at `/` |
| Opt-in no-signin demo | **Verified** | flag + loopback check, 404 when disabled, normal session and `auth.demo_login` audit; `test_26_local_demo_autologin_is_opt_in` |
| Hosted public demo or signup | **Not implemented** | `/demo` is local-only; no account creation, email verification or billing |

## 16. Status after Build 0.9 (2026-10-25)

| Requirement area | Status | Evidence |
|---|---|---|
| Grouped main navigation | **Verified** | direct Dashboard plus Transactions, Books, Reports, Tax Returns, Masters and Settings dropdowns; `test_27_grouped_dropdown_navigation` |
| Related transactions grouped | **Verified** | Sales group: Invoices, Receipts, Credit Notes; Purchases group: Bills, Debit Notes, Vendors |
| Related books grouped | **Verified** | Day Book, Journal, Ledger, Cash Book, Bank Book, Bank Reconciliation |
| Related reports grouped | **Verified** | Trial Balance, P&L, Balance Sheet, AR/AP Ageing |
| Tax working papers grouped | **Verified** | GST Summary & GSTR-1, GSTR-3B Working, GSTR-2B Reconciliation under Tax Returns; still preparation aids only |
| Cash book | **Verified** | `/reports/cash-book` from posted account 1000 lines; `test_14_new_pages_render` |
| Bank book | **Verified** | `/reports/bank-book` from posted account 1010 lines; `test_14_new_pages_render` |
| Keyboard/no-JavaScript menu operation | **Verified** | native `details`/`summary`, Escape/outside-click script; local Chromium check only |
| Screen-reader and cross-browser matrix | **Not verified** | disclosed in `docs/TEST_RESULTS.md` run 14 |

## 17. Status after Build 0.11 (2026-10-26)

| Requirement area | Status | Evidence |
|---|---|---|
| Ledger lists every account | **Verified** | `/ledger` groups all accounts by asset, liability, equity, income and expense; balances carry Dr/Cr; browser check and `test_28` |
| Clicking account opens its ledger | **Verified** | account link sets `?account=` and renders that account's full posted ledger; browser check |
| Add ledger account from Ledger | **Verified** | full Account 360 form POST `/accounts`; validated, audited and redirected to the new ledger; `TestAccountManagement`, `TestAccountProfile`, `test_28`, `test_32` |
| Full account details at creation | **Verified** | classification/group, company/contact/address, GSTIN/PAN/CIN, organisation/industry, credit terms, bank, loan and notes saved atomically; `account_profile`; `TestAccountProfile`, `test_32`, `test_33` |
| Long account-type classification list | **Verified** | one Account type / group selector covers cash, bank, debtors, creditors, inventory, fixed assets, loans, tax, suspense, capital, drawings, retained earnings, P&L, purchase, sales, depreciation and other groups; type is derived and stored separately; `test_35` |
| Debtor/creditor classification and sub-ledger | **Verified** | `receivable`/`payable` groups create or link customer/vendor; invoices, bills, receipts, payments and notes post to the linked ledger; opening balances are party-tagged; `TestAccountProfile`, `test_32` |
| Account profile editing | **Verified** | `/ledger/account/<id>/edit` and `/accounts/update`; `account.manage`, descriptive fields only, `account.update` audit; `test_32` |
| Product margin/tax master | **Verified** | `/items` stores category, brand, barcode, HSN/SAC, MRP, cost, margin, GST rate, sale price, stock and sales ledger; blank price = cost + margin; `test_34` |
| Opening balance at creation or later | **Verified** | form on `/ledger?account=<id>` posts a balanced Dr/Cr journal against the auto-created `3200 Opening Balance Equity`; the post-creation redirect opens the form; `TestOpeningBalance`, `test_31` |
| Opening balance validation and correction | **Verified** | amount/side/date validated, no future date, date on or before first activity, one posted opening per account, replacement only after permission-controlled reversal, `opening_balance.set` audited; `TestOpeningBalance`, `test_31` |
| Bulk opening-balance import | **Verified** | `/ledger/opening-balances` and **Books → Ledgers → Bulk Opening Balances**; CSV preview before posting, template download, all-or-nothing posting, per-row opening journals, tenant-scoped codes and audit; `TestOpeningImport` (8), `test_36`, browser check `RUN-2026-10-26-04` |
| Bulk import validation | **Verified** | rejects invalid headers, duplicate codes, unknown/non-postable accounts, bad amounts/sides, future or locked dates, dates after first activity, existing openings and the equity account; no partial posting; `TestOpeningImport` |
| Bulk import atomicity and audit | **Verified** | one outer transaction; simulated second-row failure rolled back the first row, the equity account and the bulk audit; one `opening_balance.set` per account plus `opening_balance.bulk_import`; `test_07_failure_after_first_entry_rolls_back_the_whole_import`, `test_05_post_is_balanced_audited_and_keeps_notes` |
| Entry creation separate from viewing | **Verified** | `/entries/cash`, `/entries/bank`, `/entries/journal`; Cash/Bank preselect the control account; `test_30` |
| Corrections with permission | **Verified** | manual journal reversal requires `ledger.reverse` and a reason; mirrored entry + original marked reversed + audit; `test_30` |
| Edit manual entries | **Verified** | `/journal?edit=<id>` pre-fills the original; `POST /journal/edit` requires both `journal.post` and `ledger.reverse`, a reason, and a balanced replacement; original is reversed and corrected entry posted in one transaction; failure rolls back the reversal; `journal.edit` audit; Edit/Reverse actions on ledger, day book, cash book, bank book and entry pages; `TestEntryCorrection`, `test_web.test_48` |
| New bank account with full details | **Verified** | `/bank-accounts` creates a linked asset ledger plus bank name, account number, IFSC, branch and holder; `TestBankAccounts`, `test_29` |
| Multiple bank accounts in books | **Verified** | Bank Book and Reconciliation select among 1010 and every linked bank account; browser check and `test_29` |
| Reports in one dropdown | **Verified** | Reports holds Trial Balance, P&L, Balance Sheet, AR/AP Ageing, GST Summary & GSTR-1, GSTR-3B Working and GSTR-2B; no Tax Returns heading |
| Permission matrix | **Verified** | `account.manage` for owner/admin/accountant; read-only denied; `test_readonly_cannot_manage_accounts` |
| Dashboard cash includes all banks | **Verified** | KPI sums cash 1000 and every linked bank account; `TestAccountManagement` and browser check |
| Zoho-style workflow grouping | **Verified** | transactions, entries, books, reports, masters and settings remain separate; visual design is ARTHIVIO's own, not a Zoho clone (D-025) |
| Shared UI palette / no navy | **Verified** | signed-in workspace uses a white topbar, neutral charcoal ink `#212529`, a light page and the electric-blue/cyan/green default family; no navy token remains in app CSS; the public landing hero stays dark, is slightly lighter than the original navy and has a page-level four-colour picker; `test_37`, browser checks in `RUN-2026-10-27-01` (D-031, D-032) |
| User-selectable colour themes | **Verified** | **Settings → Appearance** offers Ocean Blue, Emerald Green, Royal Violet and Warm Sunset; the choice is stored per user in additive `user.theme`, CSRF-protected and audited as `user.theme_updated`; dashboard, sign-in page and invoice print follow the saved palette; `test_38`, `RUN-2026-10-27-01` (D-031) |
| Public landing colour choice | **Verified** | the dark landing hero is slightly lighter than the original navy and offers four dark variants (Ocean, Emerald, Violet, Sunset) through the visible Colour picker; `/home?theme=<key>` validates the key, sets the non-sensitive `ui_theme` cookie, redirects and falls back to Ocean; page-level only, never writes `user.theme`; `test_37`, `test_38`, `RUN-2026-10-27-01` (D-032) |
| Bank-account deactivate | **Not implemented** | disclosed in `docs/FEATURE_INVENTORY.md` §18 |
| Cross-browser/screen-reader/pixel regression | **Not verified** | disclosed in `docs/TEST_RESULTS.md` run 23 |

## 18. Status after account archive/merge (Build 0.11, 2026-10-27)

| Requirement area | Status | Evidence |
|---|---|---|
| Archive a ledger without deleting history | **Verified** | zero-balance ordinary ledgers can be archived with a reason; `account.status`/`archived_at`/`archived_by` are additive; `account.archive` audit; ledger history remains; new postings and selectors exclude archived accounts; `tests/test_account_archive.py`, `test_web.test_39`, `RUN-2026-10-27-02` |
| Merge duplicate ledgers | **Verified** | same-type active target; one balanced `source_type='merge'` journal moves the net balance; source archived with `merged_into_id`; trial balance stays balanced; `test_merge_posts_a_reclassification_and_archives_source`, `test_39` |
| Archive/merge guard rails | **Verified** | non-zero balances, system/control codes, party-linked ledgers (including legacy pointers), product-used sales ledgers, different types, different parties, bank/non-bank and future-dated activity are rejected; `tests/test_account_archive.py` |
| Restore and correction path | **Verified** | restore clears archive metadata and writes `account.restore`; a merge is not auto-reversed, so corrections remain explicit manual journals; `test_39`, service test |
| Repoint products and party pointer | **Verified** | income-account merge updates `item.revenue_code`; same-party merge updates `customer`/`vendor.account_id`; `test_merge_validates_type_party_and_repoints_items` |
| Archived-account visibility | **Verified** | archived accounts stay in a separate ledger list with full history; Bank Book, posting selectors, opening import and item revenue choices exclude them; `test_bank_list_hides_archived_accounts_and_targets_stay_compatible`, `test_opening_import_rejects_archived_account`, `test_39` |
| Audit trail | **Verified** | `account.archive`, `account.merge` and `account.restore` records include actor, reason, source/target, balance, journal entry and repointing counts; service tests and `test_39` |
| One-click merge undo / moving bank statement lines | **Not implemented** | restore reopens the source but leaves the reclassification journal; bank-statement lines stay on the archived source; disclosed in `docs/FEATURE_INVENTORY.md` §18 |


## 19. Status after analytics foundation and pilot (Build 0.11, 2026-10-27)

| Requirement area | Status | Evidence |
|---|---|---|
| Read-only analytics views | **Verified** | `v_analytics_journal` and `v_analytics_monthly` are additive views derived from posted journals; row/amount reconciliation test; `tests/test_analytics.py::test_analytics_views_reconcile_to_journal_rows` |
| Metric registry and source/formula | **Verified for 19 metrics** | catalog exposes key, label, unit, source, formula, `report.view` and drill-down; actual-only; `test_catalog_is_actuals_only_and_has_stable_metric_keys` |
| Totals reconcile to the ledger | **Verified** | snapshot revenue/expense/profit/cash/AR/AP/GST and checks equal existing deterministic functions; `test_snapshot_matches_pnl_and_balanced_checks` |
| Monthly actuals and empty periods | **Verified** | zero-filled monthly revenue/expense/profit; gaps are zero, not estimates; `test_monthly_series_zero_fills_missing_months` |
| Expense and top-party analysis | **Verified for pilot scope** | expense composition and posted-invoice/customer and bill/vendor ranking; `test_expense_breakdown_and_customer_ranking` |
| Tenant isolation and bad dates | **Verified** | second tenant sees zeroes/empty lists; `BAD_DATE`/`BAD_PERIOD` JSON errors; `test_tenant_isolation_and_date_validation` |
| API permission and headers | **Verified** | session + `report.view` + membership; `401` unauthenticated; `no-store`, `nosniff`, `DENY`, `same-origin`; `test_web.test_40` |
| Analytics Overview screen | **Verified** | `/reports/analytics` under the single Reports dropdown; KPI cards, bars, composition, top parties, checks/freshness; live browser and JSON checks in `RUN-2026-10-27-03` |
| AI insights | **Not implemented** | no provider, grounded Q&A, anomaly engine or forecast; plan only |
| AI-based Excel | **Not implemented** | `.xlsx` and AI workbook remain Phase C; CSV only today |
| Power BI | **Not implemented** | no model/`.pbix`/Power Query/RLS; internal session API only |
| Full 66 reports / ~150 templates / chart engine | **Not implemented** | 19/66 catalogued reports plus an uncounted pilot; full chart/dashboard and EN/HI remain Phase B |
| Mobile/screen-reader/4K verification | **Not verified** | one desktop Chromium check; phone link is an access check, not a responsive test matrix |


## 20. Status after real Excel, Power BI pack and grounded insights (Build 0.12, 2026-10-28)

| Requirement area | Status | Evidence |
|---|---|---|
| Real `.xlsx` export | **Verified for the actuals workbook** | 20-sheet workbook with 3 native charts and exact integer-paise KPI source; `tests/test_excel.py` (6), `test_web.test_41`, live download 57,877 bytes in `RUN-2026-10-28-01` |
| Real `.xlsx` import | **Verified for three flows** | opening balances, bank statements and GSTR-2B convert server-side to neutral CSV and reuse the existing validators; 8 MB/50,000-row limit; `tests/test_xlsx_import.py` (5), `test_web.test_45` |
| AI-based Excel workbook | **Not implemented** | no generative provider or AI-authored formulas; the AI Insights sheet is deterministic text with written bases, not AI-authored calculations |
| Power BI static import pack | **Verified** | `/export/powerbi.zip` with facts, dimensions, catalog, Power Query starter and SHA-256 manifest; `tests/test_bi.py` (4), `test_web.test_42` |
| Power BI Service / `.pbix` / RLS / refresh | **Not implemented** | no Desktop-vs-Service scope or licensing decision; the pack is a static snapshot only |
| Grounded deterministic insights | **Verified** | observations with basis, metric keys, drill-down and source; no external model; `tests/test_insights.py` (3), `test_web.test_44` |
| Generative AI / Q&A / anomaly / forecast | **Not implemented** | explicit `generative_ai=false` and no-provider label; provider, consent, privacy and cost decisions remain open |
| Interactive charts | **Verified for two actuals views** | ECharts 5.5.1 vendored locally, no CDN; monthly revenue/expense/profit and expense-composition donut; `test_web.test_43`; the full chart/report library is still missing |
| Actual vs estimate vs forecast | **Verified for delivered surfaces** | workbook and Power BI facts are actuals-only; insights carry `actuals_only=true` and `forecast_included=false`; no forecast is displayed as actual |
| Full 66 reports / ~150 templates / saved dashboards / EN-HI | **Not implemented** | 19/66 catalogued reports plus an uncounted Analytics pilot; saved layouts, full drill-down and EN/HI remain Phase B |
| Mobile / screen-reader / contrast / cross-browser / 4K | **Not verified** | the public phone URL is an access check only; no real viewport or accessibility matrix was run |
| Dependency approval | **Recorded** | owner approved dependencies; `openpyxl==3.1.5` is the only new runtime package; ECharts is vendored locally (D-035) |

## 21. Status after Report Library and management reports (Build 0.13, 2026-11-04)

| Requirement area | Status | Evidence |
|---|---|---|
| Report Library | **Verified** | `/reports/library` lists 66 catalogued reports with group, source/formula and working/partial/planned status; filters and honest empty states; `test_web.test_46` |
| Cash flow | **Verified as a working paper** | R-104 direct cash movement plus indirect bridge; clean demo seed reconciles to ₹0 difference; a non-zero difference is displayed; `tests/test_reports.py` |
| Financial ratios | **Verified** | R-108 current/quick ratio, gross/net margin, ROE, ROCE, debt-equity, asset turnover and working capital from posted records; zero denominators show `n/a` |
| Period comparison | **Verified** | R-109 compares equal-length current and prior periods with delta and delta %; missing prior values are `n/a`, not estimates |
| Audit and activity registers | **Verified** | R-202 reversal register keeps original and reason; R-203 shows line count, debit, credit and net per account |
| Sales and purchase registers | **Verified** | R-301 and R-401 show posted documents with taxable, GST, round-off and total; totals reconcile; CSV exports available |
| Expense and working-capital reports | **Verified** | R-903 expense breakdown with share; R-905 DSO + DIO − DPO with explicit inputs and `n/a` handling |
| Report coverage | **28 of 66** | 19 prior working reports plus nine Build 0.13 reports; 1 partial and 37 planned remain |
| Remaining report/chart library | **Not implemented** | 38 catalogued report screens, saved dashboards, full drill-down, EN/HI labels and the ~150-template target remain Phase B |
| Mobile / screen-reader / contrast / cross-browser / 4K | **Not verified** | no real viewport or accessibility matrix was run for the new report pages |

## 22. Status after first-run setup and offline package (Build 0.14, 2026-11-04)

| Requirement area | Status | Evidence |
|---|---|---|
| First-run owner setup | **Verified** | `/setup` appears only while the user table is empty; local-only guard; setup CSRF cookie; one atomic tenant/chart/user/owner transaction; permanent closure after first owner; `tests/test_first_run.py` (6) |
| Empty-install login flow | **Verified** | `/login` redirects to `/setup` before the first user and returns to sign-in afterwards |
| Offline Windows package | **Verified on this machine** | embedded Python 3.14.6, `openpyxl` 3.1.5, local SQLite; `dist/ARTHIVIO-Offline` and ZIP; embedded import, `/health`, setup and dashboard smoke-tested |
| External-drive backup | **Verified on this machine** | verified local backup, SHA-256-matched copy, read-only re-verification, optional pruning |
| Offline launcher and autostart | **Implemented** | free-port choice, duplicate-instance detection, package-local data/backup/log paths, desktop and Windows Startup shortcuts |
| Windows installer / service / signing | **Not implemented** | no MSI, Windows service, code signing, clean-machine test or antivirus reputation check |
| Offline-to-online sync | **Not implemented** | no outage queue, device IDs, idempotency, conflict rules or tests |
| Permanent hosting / updates / UPS | **Not implemented** | no permanent URL, automatic update delivery, cloud backup or UPS integration |
| Mobile / accessibility / load / security review | **Not verified** | no real phone, screen-reader, contrast, cross-browser, 4K, load, penetration or independent accounting review for Build 0.14 |



## 23. Status after editable manual entries and fresh test books (Build 0.15, 2026-11-05)

| Requirement area | Status | Evidence |
|---|---|---|
| Edit manual cash/bank/journal entry | **Verified** | pre-filled `/journal?edit=<id>`; `POST /journal/edit` requires a reason; original reversed and corrected replacement posted in one transaction; `journal.edit` audit; `TestEntryCorrection`, `test_web.test_48` |
| Correction atomicity and guards | **Verified** | invalid/unbalanced replacement rolls back the reversal; reason required; non-manual and cross-tenant entries rejected; original remains posted |
| Edit/Reverse visibility | **Verified** | ledger, day book, cash book, bank book and entry pages show actions for manual rows under `journal.post` + `ledger.reverse`; source documents open their own page |
| Fresh business / test books | **Verified** | owner-only `/businesses/create` creates a separate tenant with standard chart and zero entries, creator becomes owner, `business.created` audit, session switches to empty ledger |
| Offline package 0.15 | **Verified on this machine** | `dist\ARTHIVIO-Offline`, `dist\ARTHIVIO-Offline-0.15.zip`; embedded runtime import, `/health` and setup page smoke-tested |
| Source-document in-place editing | **Not implemented** | invoices, bills, receipts and credit/debit notes keep their existing correction paths; no overwrite |
| Approval workflow / bulk correction | **Not implemented** | no correction approval step, edit-history UI beyond audit log, or bulk correction |
| Mobile / accessibility / load / security review | **Not verified** | no real phone, screen-reader, contrast, cross-browser, 4K, load, penetration or independent accounting review for Build 0.15 |

## 24. Status after ten report screens (Build 0.16, 2026-11-05)

| Requirement area | Status | Evidence |
|---|---|---|
| Sales and customer reports | **Verified** | R-302 sales summary, R-303 top customers, R-306 sales returns, R-307 product-wise sales and R-309 discount analysis; posted invoices/lines/credit notes only; CSV exports; `tests/test_reports.py` |
| Supplier and purchase reports | **Verified** | R-404 top suppliers and R-406 purchase returns; posted bills/debit notes only; share and return-rate formulas; CSV exports |
| Inventory report | **Verified as a document-derived working paper** | R-501 stock summary reconstructs opening/in/out/closing from posted invoice, bill, credit-note and debit-note lines; current item master stock is the anchor; no manual stock-adjustment table exists |
| Credit-risk report | **Verified** | R-706 credit-limit utilisation combines open posted receivables with customer master limits and flags over-limit/no-limit customers; it never blocks a sale |
| Journal exception report | **Verified** | R-110 detects debit/credit differences, fewer than two lines, zero-value entries and duplicate line numbers without repairing them; malformed-entry test proves detection |
| Report coverage | **38 of 66** | 28 prior working reports plus ten Build 0.16 reports; 1 partial and 27 planned remain |
| Offline package 0.16 | **Verified on this machine** | `dist\ARTHIVIO-Offline`, `dist\ARTHIVIO-Offline-0.16.zip`; embedded runtime import and `/health` smoke-tested |
| Manual stock adjustment / historical cost | **Not implemented** | stock report uses document movements and current item cost; product margin is labelled as an estimate |
| Mobile / accessibility / load / security review | **Not verified** | no real phone, screen-reader, contrast, cross-browser, 4K, load, penetration or independent accounting review for Build 0.16 |

## 25. Status after nineteen more report screens (Build 0.17, 2026-11-06)

| Requirement area | Status | Evidence |
|---|---|---|
| Ledger reconciliation | **Verified** | R-107 shows opening + period debit ? period credit = closing for every ledger and flags any mismatch; `test_opening_closing_balances_reconcile` |
| Locked periods | **Verified as a read-only register** | R-205 reads `period_lock` with actor and timestamp; posting guard already rejects locked dates; `test_locked_period_register_reads_lock_actor` |
| Rule version usage | **Verified with a source limit** | R-206 groups posted entries by `journal_entry.rule_version`; existing rows default to `posting-v1`; it is a usage register, not a rule-change history; `test_rule_version_usage_groups_posted_entries` |
| Salesperson performance | **Verified with a source limit** | R-308 groups posted invoices and receipts by journal creator, not a separate salesperson master; collection rate can exceed 100%; `test_salesperson_revenue_and_collections_reconcile` |
| Purchase price variance | **Verified with a source limit** | R-405 compares latest bill price with previous bill and current moving weighted-average cost; higher price is not automatically an error; `test_price_variance_uses_latest_and_current_cost` |
| Stock movement history | **Verified as a document history** | R-502 lists posted purchase, sale, credit-note, debit-note and manual-adjustment lines with source and party; opening stock is excluded; `test_stock_movements_match_stock_summary_quantities` |
| Stock adjustment register | **Verified as a current-cost register** | R-506 lists signed quantity, current moving weighted-average cost, value, reason, journal and posting user; increases post Dr Inventory / Cr Stock Adjustments and decreases reverse; `test_stock_adjustment_posts_and_register_reconciles`, `test_50_stock_adjustment_entry_report_and_csv` |
| Inventory valuation | **Verified as current-cost working paper** | R-503 reconstructs closing quantity at a date and applies current moving weighted-average cost; no FIFO/historical layers; `test_inventory_valuation_matches_stock_summary_value` |
| Reorder / shortage | **Verified** | R-504 uses additive `item.reorder_level_milli` and also shows zero/negative stock; advisory only; `test_reorder_shortage_uses_item_level` |
| Dead / slow stock | **Verified as a review prompt** | R-505 finds stocked items with no posted movement for N days, including never-moved stock; not an automatic write-off; `test_dead_stock_uses_last_posted_movement` |
| Inventory-to-GL reconciliation | **Verified** | R-507 compares item-master stock value with the posted inventory account balance and shows the difference; never posts a correction; `test_inventory_gl_reconciliation_shows_difference` |
| Receivables risk | **Verified as advisory** | R-704 combines open receivable ageing, credit days, limits and prior-period overdue; never blocks a sale; `test_receivables_risk_reconciles_to_ageing` |
| Budget vs actual | **Verified as planning data** | R-901 compares stored monthly income/expense budgets with posted actuals, shows variance and favourable/unfavourable states, and never changes a posted balance; `test_budget_vs_actual_marks_favourable_and_unfavourable` |
| Budget entry and audit | **Verified** | `/budgets` upserts one ledger-month, removes rows and writes `budget.create`/`budget.update`/`budget.delete`; protected by `budget.manage`; `test_budget_set_update_delete_is_audited` |
| Cash-flow forecast | **Verified as a labelled forecast** | R-705 places open collections and payments by due date, puts overdue items in the first bucket and reconciles opening cash to closing cash; `test_cash_flow_forecast_reconciles_opening_to_closing` |
| Tax ledger | **Verified as a working aid** | R-807 shows output-tax and input-credit ledgers with opening, debit, credit, closing and net payable; not a filed return; `test_tax_ledger_reconciles_output_and_input` |
| KPI dashboard pack | **Verified as actual-only** | R-904 assembles revenue, profit, cash, receivables, payables, inventory, margins, ratios, DSO/DIO/DPO and CCC from existing reports; `test_kpi_pack_is_actual_only_and_checks_balance` |
| Trend explanation | **Verified as deterministic** | R-1001 explains monthly actual revenue and expenses with the largest moves; no generative AI; `test_trend_explanation_matches_monthly_sales` |
| Revenue forecast | **Verified as a labelled forecast** | R-1002 fits a least-squares line to monthly actual net revenue and keeps forecast rows separate from actual rows; `test_revenue_forecast_separates_actuals_and_forecast` |
| Anomaly digest | **Verified as a review aid** | R-1003 lists deterministic review prompts for journal structure, large entries, duplicates, backdating, negative stock and 90+ day receivables; not a fraud finding; `test_anomaly_digest_returns_review_prompts` |
| Report coverage | **57 of 66** | 38 prior working reports plus nineteen Build 0.17 reports; 0 partial and 9 planned remain |
| Offline package 0.17 | **Verified on this machine** | `dist\ARTHIVIO-Offline`, `dist\ARTHIVIO-Offline-0.17.zip`; embedded runtime import and `/health` smoke-tested |
| Historical cost / batch / job costing | **Not implemented** | stock adjustments and valuation use current moving weighted-average cost; FIFO, batch/expiry, job/project, WIP and cost-centre models remain future work |
| Mobile / accessibility / load / security review | **Not verified** | no real phone, screen-reader, contrast, cross-browser, 4K, load, penetration or independent accounting review for Build 0.17 |

## 26. Status after draft sales invoices and R-204 (Build 0.18, 2026-11-06)

| Requirement area | Status | Evidence |
|---|---|---|
| Draft sales invoice | **Verified** | `/invoices/new` can save a draft with a `DRAFT-#####` number, no journal, no stock movement, no receivable and no tax-invoice print; `test_draft_invoice_has_no_journal_or_stock_effect`, `test_51_draft_invoice_save_post_void_and_report` |
| Post draft | **Verified** | posting re-reads live items, aggregates duplicate-line stock, rejects short stock, assigns `INV-#####`, posts one balanced journal, reduces stock and audits `invoice.post`; `test_post_draft_assigns_invoice_number_and_posts`, `test_draft_can_wait_for_stock_but_post_revalidates` |
| Void draft | **Verified** | requires a reason, sets `status='void'`, audits `invoice.void_draft`, posts nothing and keeps the draft in history; `test_void_draft_requires_reason_and_has_no_effect` |
| Draft isolation | **Verified** | drafts are excluded from sales, receivables, GST, dashboard posted counts and recent posted invoices; receipts cannot allocate to a draft; drafts cannot print as tax invoices; `test_receipt_cannot_allocate_to_draft`, `test_51_draft_invoice_save_post_void_and_report` |
| Idempotent posting | **Verified** | posting the same draft twice returns the same posted invoice with one journal and one stock movement; `test_post_draft_is_idempotent` |
| R-204 unposted / draft entries | **Verified for draft sales invoices** | `/reports/draft-entries` lists drafts with age, value and 0-7 / 8-30 / 31-60 / 60+ buckets; `/export/draft-entries.csv` exports the same rows; `test_draft_entries_report_only_unposted_invoices_with_age` |
| Report coverage | **58 of 66** | 57 prior working reports plus R-204; 0 partial and 8 planned remain |
| Offline package 0.18 | **Verified on this machine** | `dist\ARTHIVIO-Offline`, `dist\ARTHIVIO-Offline-0.18.zip`; embedded runtime import and `/health` returned `ok` |
| Draft bills / draft journals | **Not implemented** | `journal_entry.status` has no draft state and `bill.status` supports only posted and void; R-204 covers draft sales invoices only |
| Draft line editing / approval | **Not implemented** | void and recreate a draft; there is no in-place line editor or second-person approval workflow |
| Mobile / accessibility / load / security review | **Not verified** | no real phone, screen-reader, contrast, cross-browser, 4K, load, penetration or independent accounting review for Build 0.18 |
