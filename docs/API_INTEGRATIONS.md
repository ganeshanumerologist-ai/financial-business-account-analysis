# ARTHIVIO — API Integrations

| Field | Value |
|---|---|
| Version | 2.1 |
| Date | 2026-11-08 |
| Status | **No external provider is connected; internal imports, reports and analytics API are implemented through Build 0.21** |
| Policy | No paid APIs, no credentials, no fabrication |

> Current state: **0 external integrations configured. 0 provider credentials stored. 0 outbound API calls made by the product.** Manual CSV/`.xlsx` import and the internal session-authenticated analytics/Power BI export surface are implemented; everything below labelled planned still needs external access, credentials or owner decisions.

---

## 1. Integration rules (non-negotiable)

1. No integration is claimed to work until a real successful call is recorded in `docs/TEST_RESULTS.md`, including the sandbox endpoint used.
2. Secrets come from environment variables only; never committed, never bundled into the frontend.
3. Sandbox/test environments first. Production credentials require explicit owner approval.
4. Every outbound call is logged (endpoint, status, latency, request ID) **without** sensitive payloads.
5. Retries use idempotency keys; no blind retry on a financial mutation.
6. A failed call must surface a visible error, never a silent success.
7. Government/statutory responses (IRN, filing acknowledgement) are stored verbatim with timestamps — and never fabricated.
8. Rate limits and quotas are respected; 429 handled with backoff.

---

## 2. Integration inventory

| ID | Integration | Purpose | Phase | Status | Prerequisite |
|---|---|---|---|---|---|
| INT-01 | GST e-Invoice (IRN) | Statutory invoice registration | 9 | ⛔ Not connected | Official API access, GSTIN, sandbox onboarding, CA review |
| INT-02 | e-Way Bill | Goods transport documentation | 9 | ⛔ Not connected | Official access |
| INT-03 | GST portal (GSTR working data) | Export/reconcile filing data | 9 | ⛔ Not connected | Filing authorisation; no direct filing in scope initially |
| INT-04 | Payment gateway (UPI/cards) | Collect payments | 9 | ⛔ Not connected | Provider account + fees (owner cost approval), PCI scope review |
| INT-05 | UPI QR (non-statutory) | Display a payment QR | 9 | ⛔ Not connected | Provider/UPI ID; must be labelled non-statutory |
| INT-06 | Bank statement import | Reconciliation feed | 3 | **Manual CSV/`.xlsx` implemented**; no bank API | Manual file only; no bank credentials |
| INT-07 | Bank API (account information) | Automated bank feed | 10 | ⛔ Not connected | Bank approval, consent framework, security review |
| INT-08 | Email/SMS notifications | Reminders, alerts | 6 | ⛔ Not connected | Provider account (may cost) |
| INT-09 | WhatsApp Business API | Invoice/reminder delivery | 9 | ⛔ Not connected | Meta verification + provider |
| INT-10 | AI provider (LLM) | Explanations/insights | 8 | **No provider; deterministic grounded insights implemented** | Consent, data-protection review, cost approval |
| INT-11 | Tally/other accounting import | Migration | 3 | ⛔ Not connected | Format research |
| INT-12 | Barcode hardware (USB/BT scanner) | Input device | 4 | ⛔ Not connected | No API; keyboard-wedge input handling |

---

## 3. Per-integration detail (highest-risk items)

### INT-01 — GST e-Invoice (IRN)

| Item | Detail |
|---|---|
| Direction | Outbound to government sandbox/production |
| Auth | Client credentials issued by the portal (per GSTIN) |
| Data sent | Invoice JSON per official schema |
| Data received | IRN, acknowledgement number, signed QR |
| Failure modes | Auth failure, schema rejection, duplicate IRN, timeout after success (dangerous) |
| Critical rule | On timeout, **do not assume failure** — query by reference before retrying |
| Evidence required | Sandbox success + stored response; production requires owner sign-off |
| Never | Generate a fake IRN or QR |

### INT-04 — Payment gateway

| Item | Detail |
|---|---|
| Direction | Outbound + webhook inbound |
| Auth | API key/secret in env; webhook signature verification mandatory |
| Critical rule | Payment is "confirmed" **only** on a verified provider confirmation or an authorised, audited manual entry |
| Failure modes | Webhook replay, amount mismatch, partial capture |
| Idempotency | Provider payment ID is the idempotency key |

### INT-10 — AI provider

| Item | Detail |
|---|---|
| Direction | Outbound prompts, inbound text |
| Data policy | Only data the user is authorised to see; no cross-tenant context |
| Consent | Explicit, recorded; configurable off by default |
| Critical rule | AI must not compute authoritative financial totals — deterministic engine does that |
| Failure modes | Hallucinated figures, data leakage |
| Mitigation | Ground answers in retrieved records; cite source IDs; label estimates. Build 0.12 ships a deterministic `engine=deterministic_rules_v1` fallback with `generative_ai=false`; no external model is called |

---

## 4. What exists today

| Capability | Status |
|---|---|
| HTTP client for outbound calls | ❌ Not implemented |
| Credential storage/rotation | ❌ Not implemented |
| Webhook receiver with signature verification | ❌ Not implemented |
| Retry/backoff/idempotency framework | ❌ Not implemented |
| Integration audit logging | Not implemented for external calls; accounting/import actions use the existing audit log |
| Sandbox test harness | ❌ Not implemented |
| Internal analytics JSON API | Session-authenticated, tenant-scoped, `report.view`; `/api/v1/analytics/catalog`, `/api/v1/analytics/overview` and `/api/v1/analytics/insights`; no external token yet | Implemented (internal only) |
| CSV/`.xlsx` bank statement import | Implemented manually; SHA-256 dedup and matching; no bank feed |

---

### 4.1 Build 0.12 internal surfaces (not external integrations)

| Surface | Status |
|---|---|
| `/export/workbook.xlsx` | Real `.xlsx` actuals workbook; session + `report.export`; no external service |
| `/export/powerbi.zip` | Static import ZIP for Power BI Desktop; no Service connection, token or refresh |
| `/api/v1/analytics/insights` | Deterministic grounded observations; session + `report.view`; no model provider |
| `/static/echarts.min.js` | Locally vendored chart asset; no CDN or third-party request |
| `.xlsx` upload | Opening balances, bank statements and GSTR-2B; server-side conversion; no cloud storage |

### 4.2 Build 0.13 internal report surfaces (not external integrations)

| Surface | Status |
|---|---|
| `/reports/library` | All 66 catalogued reports with honest working/partial/planned state; session only |
| `/reports/cash-flow` | R-104 direct movement and indirect bridge; no forecast |
| `/reports/ratios` | R-108 ratios from posted P&L and balance sheet |
| `/reports/comparison` | R-109 equal-length period comparison |
| `/reports/reversals`, `/reports/account-activity` | R-202 and R-203 audit/activity views |
| `/reports/sales-register`, `/reports/purchase-register` | R-301 and R-401 posted-document registers |
| `/reports/expense-breakdown`, `/reports/working-capital` | R-903 and R-905 management views |
| `/reports/tb-exceptions`, `/reports/sales-summary`, `/reports/top-customers`, `/reports/product-sales` | Build 0.16 journal-exception, sales-summary, customer-ranking and product reports |
| `/reports/discounts`, `/reports/sales-returns`, `/reports/top-suppliers`, `/reports/purchase-returns` | Build 0.16 discount, return and supplier-concentration reports |
| `/reports/stock-summary`, `/reports/credit-limits` | Build 0.16 document-derived stock and open-receivable credit-limit reports |
| `/reports/opening-closing`, `/reports/locked-periods`, `/reports/rule-versions`, `/reports/salesperson`, `/reports/price-variance` | Build 0.17 ledger reconciliation, lock register, creator performance and purchase price-variance reports |
| `/reports/stock-movements`, `/reports/inventory-valuation`, `/reports/reorder`, `/reports/dead-stock`, `/reports/inventory-gl`, `/reports/receivables-risk` | Build 0.17 stock history/valuation/reorder/dead-stock/GL reconciliation and receivables-risk reports |
| `/reports/cash-flow-forecast`, `/reports/tax-ledger`, `/reports/kpi-pack` | Build 0.17 labelled cash forecast, tax ledger and actual-only KPI pack |
| `/reports/trend-explanation`, `/reports/revenue-forecast`, `/reports/anomaly-digest` | Build 0.17 deterministic narrative, labelled revenue forecast and rule-based review prompts |
| `/budgets`, `/reports/budget` | Build 0.17 budget entry (`budget.manage`) and R-901 budget vs actual (`report.view`); budget rows are planning data, not journal entries |
| `/reports/draft-entries` | Build 0.18 R-204 draft sales-invoice register with age and ageing buckets; `report.view` |
| `/invoices/<id>/post`, `/invoices/<id>/void` | Build 0.18 draft actions; `invoice.create`; posting revalidates stock and assigns the next INV number; voiding requires a reason |
| `/export/cash-flow.csv`, `/export/sales-register.csv`, `/export/purchase-register.csv`, `/export/expense-breakdown.csv` | Session + `report.export`; exact decimal strings; no external service |
| `/export/sales-summary.csv`, `/export/top-customers.csv`, `/export/product-sales.csv`, `/export/discounts.csv`, `/export/sales-returns.csv`, `/export/top-suppliers.csv`, `/export/purchase-returns.csv`, `/export/stock-summary.csv`, `/export/credit-limits.csv`, `/export/tb-exceptions.csv` | Build 0.16 CSV exports; session + `report.export`; exact decimal strings and three-decimal quantities; no external service |
| `/export/opening-closing.csv`, `/export/locked-periods.csv`, `/export/rule-versions.csv`, `/export/salesperson.csv`, `/export/price-variance.csv`, `/export/stock-movements.csv`, `/export/inventory-valuation.csv`, `/export/reorder.csv`, `/export/dead-stock.csv`, `/export/inventory-gl.csv`, `/export/receivables-risk.csv` | Build 0.17 CSV exports; session + `report.export`; exact decimal strings and three-decimal quantities; no external service |
| `/export/cash-flow-forecast.csv`, `/export/tax-ledger.csv`, `/export/kpi-pack.csv`, `/export/trend-explanation.csv`, `/export/revenue-forecast.csv`, `/export/anomaly-digest.csv` | Build 0.17 CSV exports; session + `report.export`; exact decimal strings; forecasts and actuals are separated; no external service |
| `/export/budget.csv` | Build 0.17 CSV export; session + `report.export`; budget, actual, variance, variance %, status and budget months; no external service |
| `/export/draft-entries.csv` | Build 0.18 CSV export; session + `report.export`; draft number, date, customer, taxable, GST, total, age days, bucket and created timestamp; no external service |
| `/dimensions`, `/dimensions/update`, `/dimensions/budget` | Build 0.19 dimension master and monthly cost-centre budget; `budget.manage`; additive register, no journal or stock effect |
| `/batches`, `/batches/void` | Build 0.19 manual batch/expiry register; `item.manage`; no stock movement or journal |
| `/production-orders`, `/production-orders/status` | Build 0.19 production-order register; `item.manage`; no stock movement or journal |
| `/reports/expiry` | Build 0.19 R-508 expiry/batch working paper; `report.view` |
| `/reports/project-costing`, `/reports/cost-centre`, `/reports/dimension-pnl` | Build 0.19 R-601, R-605 and R-902 tagged-journal reports with explicit unallocated rows; `report.view` |
| `/reports/wip`, `/reports/production-consumption`, `/reports/yield` | Build 0.19 R-602, R-603 and R-604 production-register reports; `report.view` |
| `/reports/consolidated` | Build 0.19 R-1004 read-only owner/admin consolidation; intercompany-flagged journals excluded from combined totals; `report.view` |
| `/export/expiry.csv`, `/export/project-costing.csv`, `/export/wip.csv`, `/export/production-consumption.csv`, `/export/yield.csv`, `/export/cost-centre.csv`, `/export/dimension-pnl.csv`, `/export/consolidated.csv` | Build 0.19 CSV exports; session + `report.export`; exact decimal strings and three-decimal quantities; no external service |
| `/invoices/<id>/edit`, `/invoices/<id>/submit`, `/invoices/<id>/approve`, `/invoices/<id>/reject`, `/invoices/<id>/withdraw` | Build 0.20 draft invoice editing and optional maker-checker; edit is allowed only while `status='draft'` and `approval_status` is not `pending`; approve/reject require `document.approve` |
| `/invoices/<id>/replace`, `/invoices/<id>/void-posted` | Build 0.20 audit-safe posted invoice correction/void; reverse journal, restore stock, mark old `void`, post linked replacement |
| `/bills/drafts`, `/bills/drafts/<id>`, `/bills/drafts/<id>/post`, `/bills/drafts/<id>/reject`, `/bills/drafts/<id>/void` | Build 0.20 draft purchase-bill lifecycle; no ledger, stock, payable or GST effect before posting |
| `/journals/drafts`, `/journals/drafts/<id>`, `/journals/drafts/<id>/post`, `/journals/drafts/<id>/reject`, `/journals/drafts/<id>/void` | Build 0.20 draft journal lifecycle; no ledger effect before posting |
| `/bills/<id>/replace`, `/bills/<id>/void` | Build 0.20 audit-safe posted bill correction/void; blocked with `BILL_STOCK_CONSUMED` when stock has already been sold or consumed |
| `/receipts/<id>`, `/receipts/<id>/replace`, `/receipts/<id>/void` | Build 0.20 receipt and vendor-payment detail, correction and void; allocations carry forward by default |
| `/approvals` | Build 0.20 pending approval queue; requires `document.approve`; single optional maker-checker step |
| `/opening-balance/replace` | Build 0.20 direct opening-balance correction; reverses the old opening journal and posts a replacement in one transaction |

There is still no external BI token API. The session-authenticated JSON analytics API remains the
only machine-readable external surface, and it exposes actuals only.

## 5. Sequencing rationale

1. **Manual data paths first** (CSV import/export) — they solve 80% of reconciliation needs without credentials or cost.
2. **Notifications** after the core is stable — cheap, low risk.
3. **Payments** only with a provider account and explicit cost approval.
4. **Government APIs** last, and only with verified access — the highest compliance risk and the easiest place to accidentally fabricate a status.

This ordering is deliberate: nothing external is required to deliver a correct, testable accounting core.

---

## 6. Owner decisions needed

| ID | Decision | Blocks |
|---|---|---|
| INT-D1 | Which payment provider (if any) to evaluate first | Phase 9 |
| INT-D2 | Whether AI features are wanted at all, and with which provider/cost ceiling | Phase 8 |
| INT-D3 | Whether GSTIN/e-invoice is in scope for the first launch | Phase 9 |
| INT-D4 | Email/SMS provider and budget | Phase 6 |
