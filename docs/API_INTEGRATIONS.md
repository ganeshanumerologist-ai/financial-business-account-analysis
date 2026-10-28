# ARTHIVIO — API Integrations

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-10-28 |
| Status | Draft - **no external provider is connected; internal imports and analytics API are implemented** |
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
