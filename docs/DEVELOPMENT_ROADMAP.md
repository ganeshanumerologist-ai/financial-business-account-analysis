# ARTHIVIO — Development Roadmap

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-10-28 |
| Status | In delivery; Build 0.12 verified, full Phase 6/8/10 gates remain |
| Rule | Each phase ends with a gate. No gate = no progression. |

Effort bands are indicative for a single developer working part-time with AI assistance. They are **not commitments**.

---

## Phase 0 — Requirements and architecture ✅ (this work)

| | |
|---|---|
| Goal | Know exactly what is being built, with what, and how it will be verified |
| Delivered | Audit, feature inventory, test plan/results, defect report, requirements, architecture, DB design, security plan, backup plan, accounting rules, compliance matrix, API integration plan, report catalogue, decision log, traceability |
| Gate | **Owner approves this plan and the stack (Option A)** |
| Effort | Done |
| Do not | Write application code |

---

## Phase 1 — Secure foundation

| | |
|---|---|
| Goal | Auth, tenancy, roles, audit, backups — provably working |
| Build | Repo skeleton · `dev.ps1` · config/secrets · DB models + migrations · register/login/logout · session rotation · password policy · permission catalog + role matrix · tenant context · audit log · backup script · **restore-verify script** · security test suite |
| Gate | All SEC "must pass" tests + backup restore drill verified + zero financial modules written |
| Effort | 1–2 weeks |
| Risks | Python 3.14 wheel availability · session/CSRF bugs · SQLite concurrency misunderstanding |
| Do not | Build invoices, ledgers, reports, dashboards beyond a placeholder shell |

---

## Phase 2 — Accounting core

| | |
|---|---|
| Goal | Deterministic double-entry engine that reconciles |
| Build | Chart of accounts · periods + locking · journal entry + lines · posting service · reversal · document sequences · trial balance · P&L · balance sheet · cash flow · GL · opening balances · idempotency · audit on every posting |
| Gate | ACC-001…015 + property tests + independent recalculation all pass; TB equals; BS equation holds; no float on money paths |
| Effort | 2–4 weeks |
| Risks | Rounding residuals · period boundaries · reversal chains · opening balance double-count |
| Do not | Add invoicing or stock until the ledger is trustworthy |

---

## Phase 3 — Customers, suppliers and billing

| | |
|---|---|
| Goal | Real documents posting to the ledger |
| Build | Customer/supplier master · invoices · receipts · payments · credit/debit notes · AR/AP subledgers + ageing · tax lines · invoice numbering · A4/thermal print · PDF · CSV/Excel import/export · bank statement import + reconciliation |
| Gate | Invoice posting equals expected ledger movements; AR/AP reconcile to control accounts; duplicate prevention proven; export totals equal on-screen |
| Effort | 3–5 weeks |
| Risks | Tax rules · rounding · numbering races · import validation gaps |
| Do not | Connect a payment gateway or e-invoice API yet |

---

## Phase 4 — Inventory and barcode

| | |
|---|---|
| Goal | Stock that matches reality and the ledger |
| Build | Products/variants/units · warehouses · movements (opening, purchase, sale, return, damage, transfer, adjustment) · stock count · valuation · reorder · barcode scan + labels · inventory↔GL reconciliation |
| Gate | Closing stock follows the §11 formula in tests; valuation reconciles to GL; no negative stock without explicit policy |
| Effort | 3–5 weeks |
| Risks | Unit conversion · batch/expiry complexity · valuation method choice |
| Do not | Enable batch/expiry before the basic engine is proven |

---

## Phase 5 — Offline and synchronisation

| | |
|---|---|
| Goal | Sell without connectivity, without duplicate money |
| Build | Local queue with globally unique transaction IDs · idempotent sync · conflict detection + resolution UI · safe invoice-number blocks · offline stock estimates · explicit "Pending Sync" states |
| Gate | Offline→online replay creates exactly one posting; conflicts surfaced, never silently merged; multi-counter test passes |
| Effort | 2–4 weeks |
| Risks | Duplicate postings · number collisions · stale price/tax |
| Do not | Claim offline success without a real disconnect/reconnect test |

---

## Phase 6 — Reports and analytics

| | |
|---|---|
| Goal | Insight that equals the ledger |
| Build | Report engine with defined source/formula, the 66 catalogued reports, dashboards, ECharts visualisations, drill-down, exports, freshness indicators, empty states, EN/HI, responsive 360-4K and WCAG AA. **Build 0.12 delivered:** analytics pilot, two ECharts actuals views (monthly and expense composition), 20-sheet `.xlsx` actuals workbook, static Power BI pack, freshness and empty states. **Still missing:** the remaining 66-report screens, saved dashboards, full drill-down, EN/HI and the ~150-template library. |
| Gate | REP-001…007 pass; every displayed total = independent recalculation; accessibility and responsive checks recorded |
| Effort | 4–6 weeks |
| Risks | Performance on large books · silent filter leakage · chart legibility at 4K |
| Do not | Invent data to fill empty charts |

---

## Phase 7 — Industry modules

15 templates, incremental, each with its own field set, chart of accounts and reports. Gate per template: worked example posting correctly + report accuracy + professional review where regulated.

---

## Phase 8 — AI insights

| | |
|---|---|
| Build | Grounded Q&A over authorised records, trend explanation, anomaly digest and forecast with explicit bands. **Build 0.12 delivered:** deterministic grounded observations with written basis, metric keys, drill-down and an explicit no-provider label. **Not delivered:** generative Q&A, anomaly model and forecast. |
| Gate | No invented figures · every claim cites records · tenant isolation proven · consent recorded · deterministic engine remains the source of totals |
| Effort | 2–4 weeks |
| Do not | Send tenant data externally without consent and review |

---

> **Planning note:** the detailed proposal for the analytics data mart, full report/chart library,
> `.xlsx` import/export, Power BI model and grounded AI layer is in
> `docs/ANALYTICS_AI_EXCEL_POWERBI_PLAN.md`. Phase A, real `.xlsx` export/import, the static Power BI
> pack, ECharts and deterministic grounded insights are delivered. Phase B and the generative
> AI/Power BI Service parts remain proposed work, not delivered scope.

## Phase 9 - External integrations

e-Invoice, e-Way bill, payments, bank feeds, notifications — each only after verified access. Gate per integration: sandbox success recorded, timeout/duplicate handling proven, secrets in env.

---

## Phase 10 — Production readiness

Independent accounting/tax review · security review · penetration test · restore drill with measured RTO · migration test · rollback test · monitoring + alerts · documentation handover · owner approval to expose publicly.

**No production launch before this gate. No exceptions.**

---

## Timeline overview

| Phase | Effort band | Cumulative |
|---|---|---|
| 0 | done | — |
| 1 | 1–2 w | 1–2 w |
| 2 | 2–4 w | 3–6 w |
| 3 | 3–5 w | 6–11 w |
| 4 | 3–5 w | 9–16 w |
| 5 | 2–4 w | 11–20 w |
| 6 | 4–6 w | 15–26 w |
| 7 | 3–6 w | 18–32 w |
| 8 | 2–4 w | 20–36 w |
| 9 | 2–4 w | 22–40 w |
| 10 | 2–3 w | 24–43 w |

A working, testable accounting core (Phases 1–3) is realistic in roughly **6–11 part-time weeks**. Anything promised faster would skip verification, which this project explicitly forbids.

---

## Immediate next actions (in order)

1. ✅ Stack approved (Option A).
2. ✅ Baseline committed (commit `9052071`).
3. ⏳ **Awaiting owner approval to begin Phase 1 implementation.**
4. Then: repo skeleton + `dev.ps1` + dependency install (npm/pip).
5. Then: DB models + migrations.
6. Then: auth + tenancy + RBAC + audit.
7. Then: backup + restore drill.
8. Then: security test suite → gate report → stop for approval before Phase 2.

---

## Current status - Build 0.11 (2026-10-27)

The stale "immediate next actions" above are superseded by the actual delivery record:

| Build | Scope | Evidence |
|---|---|---|
| 0.1 | Accounting core, sales/purchase, receipts/payments, journals, statements, backup | `RUN-2026-10-24-*` |
| 0.2 | Credit notes, purchase returns, GST summary, GSTR-1 working export, ageing | `RUN-2026-10-24-02` |
| 0.3 | Day book, bank reconciliation, invoice print, settings | `RUN-2026-10-24-04` |
| 0.4 | Debit notes, bank matching, export hardening | `RUN-2026-10-24-05` |
| 0.5 | GSTR-3B working summary and GSTR-1/ledger reconciliation | `RUN-2026-10-24-06` |
| 0.6 | Team invites/roles, shareable statements, GSTR-2B reconciliation | `RUN-2026-10-25-01` |
| 0.7 | ITC review annotations, 3B-vs-2B comparison, backup table coverage | `RUN-2026-10-25-02` |
| 0.8 | Reference-matched public product home page, detailed SVG dashboard preview, local opt-in no-signin demo | `RUN-2026-10-25-03` |
| 0.9 | Tally-style grouped top navigation, cash book, bank book | `RUN-2026-10-25-04` |
| 0.10 | Ledger hub with account creation and Dr/Cr balances, opening balances posted against Opening Balance Equity, separate Cash/Bank/Journal entries, permission-controlled reversal, multiple bank accounts, all reports in one menu, Account 360 profiles with linked debtor/creditor sub-ledgers, expanded single account type/group selector, rich product master | `RUN-2026-10-26-01`, `RUN-2026-10-26-02`, `RUN-2026-10-26-03` |
| 0.11 | Bulk opening-balance CSV import under Books → Ledgers, validate-before-post preview, all-or-nothing posting, per-row opening journals, import notes and audit; white workspace topbar with neutral charcoal ink and four per-user light palettes (Ocean, Emerald, Violet, Sunset) under Settings → Appearance, with themed login and print pages and no navy app chrome; public landing hero slightly lightened and given four dark page-level colour choices through a visible picker; account archive/merge with a required reason, zero-balance archive, balanced merge reclassification, restore, system/party/bank guard rails and audit; analytics Phase A foundation (read-only views, 19-metric actual-only registry, JSON overview API, Analytics Overview pilot) | `RUN-2026-10-26-04`, `RUN-2026-10-26-05`, `RUN-2026-10-26-06`, `RUN-2026-10-27-01`, `RUN-2026-10-27-02`, `RUN-2026-10-27-03` |
| 0.12 | Real 20-sheet actuals `.xlsx` workbook with native charts and KPI paise trace; server-side `.xlsx` import for opening balances, bank statements and GSTR-2B; static Power BI import ZIP with manifest/facts/dimensions/Power Query starter; ECharts 5.5.1 vendored locally for actual monthly and expense-composition views; deterministic grounded insights with AI Insights page, JSON API and workbook sheet (no generative provider); 245 tests | `RUN-2026-10-28-01` |

**Next:** finish analytics Phase B (remaining 66-report screens, saved dashboards, full drill-down,
filters, EN/HI labels and the ~150-template library). The static Power BI pack can become an optional
Service model only after an explicit Desktop-vs-Service scope and licensing decision; a generative
AI provider needs consent, privacy and cost approval and must keep deterministic totals with
citations. In parallel: bank-account deactivate, partial/one-to-many bank matching, bank-charge
posting, supplier follow-up ageing, email delivery and ownership transfer. Production launch still
requires the Phase 10 gate (independent review, penetration test, measured restore drill, monitoring
and owner approval).

## Standing rules for every phase

- No phase begins before the previous gate passes with evidence.
- Tests are written with the feature, not after it.
- No claim of "working" without a recorded run.
- No paid service, no silent financial correction, no cross-tenant access, no fabricated status.
- Documentation updated in the same change as the code.
