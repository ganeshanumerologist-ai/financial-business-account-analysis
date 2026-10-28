# ARTHIVIO — Analytics, AI, Excel and Power BI Plan

| Field | Value |
|---|---|
| Version | 0.3 (Phase A plus first Excel/BI/insight slices) |
| Date | 2026-10-28 |
| Status | **Phase A and first Excel/Power BI/grounded-insight slices implemented; Phase B and full AI/Service scope pending** |
| Scope | Financial/business analytics, chart and report library, Excel import/export and AI-assisted workbooks, Power BI data model, grounded AI insights |
| Governing rules | Deterministic accounting totals, integer paise, balanced postings, audit trail, tenant isolation, no fabricated numbers, actual vs estimate vs forecast separation, AI must not calculate authoritative figures |

> This document answers one question honestly: **is the current platform already the full
> financial-analysis + AI + Excel + Power BI product described in the brief?** No. The accounting
> core, Phase A analytics, real `.xlsx` export/import, a static Power BI import pack and a
> deterministic grounded-insight layer now exist. The full 66-report/chart library, generative AI,
> Power BI Service refresh/RLS and AI-assisted workbook authoring are still to be built.
> **Update 2026-10-28:** Build 0.12 adds a 20-sheet actuals workbook, server-side `.xlsx` import for
> three existing import flows, a static Power BI ZIP, locally vendored ECharts views and an AI
> Insights layer that is explicitly rule-based. It does **not** add a generative model or a
> Power BI Service dataset.

---

## 1. Short answer

| Area | Current state | Is it fully included? |
|---|---|---|
| Double-entry accounting core | Working: invoices, bills, receipts, payments, journals, GST working papers, bank reconciliation, opening balances, audit | **Yes, foundation** |
| Financial statements | Trial balance, P&L, balance sheet, ledger, day book, cash book, bank book, ageing, GST summaries | **Partial** |
| Report library | 19 of 66 catalogued reports have a working screen or export, plus a cross-cutting Analytics Overview pilot; target is ~150 templates | **No** |
| Charts and visual analytics | Analytics Overview pilot: actual monthly revenue/expense bars, expense composition, top-party tables and checks; dashboard bars and landing SVG remain; no full chart engine or custom dashboards | **Partial / early** |
| Excel import | Real `.xlsx` upload for opening balances, bank statements and GSTR-2B; not a general workbook importer | **Partial / real slice** |
| Excel export | Real 20-sheet `.xlsx` actuals workbook with native charts and exact paise source; no formula-driven AI workbook or pivot model | **Partial / real slice** |
| Power BI | Static import ZIP with facts, dimensions, metric catalog, manifest and Power Query starter; no `.pbix`, Service dataset, token API, RLS or refresh | **Partial / static pack only** |
| AI insights | Deterministic grounded observations with written basis, metric keys and drill-down; no generative provider, Q&A, anomaly model or forecast | **Partial / no generative AI** |
| Hindi/English report labels | Not implemented across all reports | **No** |
| Dashboard customisation, drill-down, freshness | Analytics Overview shows freshness and ledger checks; saved layouts and drill-down on most screens are still missing | **Partial** |

**Bottom line:** the platform has a sound accounting/audit base, a working Phase A analytics
foundation, real Excel import/export and a static Power BI pack. It is still **not** the full
financial-analysis + AI + Excel + Power BI platform in the brief: generative AI, Power BI Service
refresh/RLS, the full 66-report chart library and AI-assisted workbooks are not delivered.

---

## 2. What is already reusable

These are real foundations, not placeholders:

- Integer-paise money and balanced double-entry postings.
- Journal lines, source documents, reversal reasons and audit log.
- Tenant isolation and role-based permissions.
- Account 360, customer/vendor sub-ledgers, bank accounts and opening balances.
- Trial balance, P&L, balance sheet, ledger, day book, cash book, bank book, ageing and GST working
  reports.
- CSV exports for many reports and registers.
- Read-only analytics views, a 19-metric actual-only registry, a session-authenticated JSON
  overview API and an Analytics Overview page (Build 0.11 Phase A).
- Real `.xlsx` actuals workbook, `.xlsx` import for three flows, static Power BI import ZIP,
  vendored ECharts and deterministic grounded insights (Build 0.12).
- Backups, integrity checks and 245 passing automated tests.
- User-selectable workspace themes and a separate dark public landing page.

The analytics layer should read these records, not duplicate or override them.

### 2.1 Phase A foundation actually delivered (Build 0.11)

| Item | Delivered | Evidence |
|---|---|---|
| Read-only semantic views | `v_analytics_journal` (entry/line/account/party fact) and `v_analytics_monthly` (month/account-type rollup), created idempotently after schema migration | `app/db.py`, `tests/test_analytics.py::test_analytics_views_reconcile_to_journal_rows` |
| Metric registry | 19 actual-only metrics with key, label, unit, source, written formula, permission and drill-down | `/api/v1/analytics/catalog`, `test_catalog_is_actuals_only_and_has_stable_metric_keys` |
| Canonical snapshot | Revenue, expenses, net profit, assets, liabilities, equity, cash+bank, AR/AP, inventory, open counts, overdue, GST output/input/net, trial-balance and balance-sheet checks, freshness | `GET /api/v1/analytics/overview`, `test_snapshot_matches_pnl_and_balanced_checks` |
| Series and breakdowns | Zero-filled monthly revenue/expense/profit; expense-account composition; top customers and vendors | `monthly_series`, `expense_breakdown`, `top_customers`, `top_vendors`, `test_monthly_series_zero_fills_missing_months`, `test_expense_breakdown_and_customer_ranking` |
| API security | Session authentication, `report.view`, tenant-scoped queries, JSON error codes, `no-store` and security headers | `test_web.test_40_analytics_api_contract_and_auth` |
| Pilot screen | Reports > Analysis > Analytics Overview with date filter, KPI cards, grouped monthly bars, expense shares, top-party tables, freshness and explicit actual-only wording | `GET /reports/analytics`, live browser check in `RUN-2026-10-27-03` |

### 2.2 Build 0.12 slice actually delivered

| Item | Delivered | Evidence |
|---|---|---|
| Real `.xlsx` workbook | 20 sheets: cover, read-me, data dictionary, executive KPIs, monthly, P&L, balance sheet, trial balance, expense breakdown, top customers/vendors, AR/AP ageing, cash/bank, inventory, GST working/sales/purchases, journal and AI Insights; 3 native Excel charts; exact integer-paise KPI source beside displayed INR | `app/excel.py`, `tests/test_excel.py` (6), `test_web.test_41` |
| Real `.xlsx` import | Opening balances, bank statements and GSTR-2B; server-side conversion to neutral CSV before the existing validators; first worksheet by default; cached formula values only; 8 MB/50,000-row guard; nothing posts without the existing preview/confirm or import rules | `app/xlsx_import.py`, `tests/test_xlsx_import.py` (5), `test_web.test_45` |
| Static Power BI pack | `/export/powerbi.zip`: analytics JSON, metric catalog, integer-paise journal/monthly facts, account/party dimensions, Power Query starter, README, manifest SHA-256 | `app/bi.py`, `tests/test_bi.py` (4), `test_web.test_42` |
| Interactive charts | ECharts 5.5.1 vendored locally; actual monthly revenue/expense/profit view and expense-composition donut, both with accessible fallback tables; no runtime CDN call | `app/static/echarts.min.js`, `test_web.test_43` |
| Grounded insights | Deterministic rules over actuals: margin, largest expense, overdue share, GST working amount, ledger checks, open documents and freshness; every observation has a basis, metric keys, drill-down and source | `app/insights.py`, `tests/test_insights.py` (3), `test_web.test_44` |

**Still Phase B/F work:** token-authenticated API for external BI, pagination, full fact/dimension
model (invoices, bills, payments, notes, inventory, bank), saved dashboards, the full chart/report
library, all 66 catalogued reports, EN/HI labels, drill-down on every total, generative AI and Power
BI Service refresh/RLS. The ~150-template target is not met.

---

## 3. Target architecture

```
Source documents and journals
        |
        v
Deterministic accounting engine  <-- only source of authoritative totals
        |
        v
Analytics data mart / semantic views  <-- read-only, reconciled to the ledger
        |
        +--> Report and chart engine (web)
        +--> Excel workbook builder / importer
        +--> Power BI dataset, API and Power Query templates
        +--> AI insight layer (citations, labels, no arithmetic authority)
```

### 3.1 Canonical analytics model

Build read-only views or additive tables for:

> **Build 0.11:** only `v_analytics_journal` and `v_analytics_monthly` exist. The documents below,
> including invoice/bill/payment facts, item/date dimensions, forecast/budget facts and metric
> dimension tables, are the target model and remain to be built.

- `fact_journal_line` — date, account, debit, credit, party, document, tenant.
- `fact_invoice`, `fact_bill`, `fact_payment`, `fact_credit_note`, `fact_debit_note`.
- `dim_account`, `dim_party`, `dim_item`, `dim_date`, `dim_bank`, `dim_gst_rate`.
- `dim_report`, `dim_metric` — report and metric definitions, formula, permissions and labels.
- `fact_forecast` — model output, model version, error band and generated timestamp.
- Optional `fact_budget` for budget-vs-actual analysis.

Rules:

- No floating-point money in the model.
- Each metric has one written formula and one owner.
- Every total can drill to journal lines or source documents.
- Snapshot/freshness timestamp is exposed with every API/export.
- Actual, estimate and forecast values are separate fields, never mixed silently.

---

## 4. Workstream A — Report and chart engine

### 4.1 Report coverage

The catalogue currently defines 66 reports. The brief asks for approximately 150 visual/report
templates across ten groups. Complete the 66 first, then extend to 150 without inventing formulas.

| Group | Catalogued | Working today | Target |
|---|---:|---:|---:|
| 1. Financial statements and performance | 10 | 5 | 15+ |
| 2. Accounting, ledgers and audit | 6 | 1 | 12+ |
| 3. Sales and customer analysis | 9 | 2 | 20+ |
| 4. Purchase and supplier analysis | 6 | 2 | 15+ |
| 5. Inventory and warehouse | 8 | 0 | 20+ |
| 6. Costing, manufacturing and operations | 5 | 0 | 15+ |
| 7. Cash, credit and risk | 6 | 3 | 15+ |
| 8. Tax, GST and compliance | 7 | 6 | 15+ |
| 9. Strategy, organisation and process | 5 | 0 | 15+ |
| 10. AI, forecasting and cross-business | 4 | 0 | 8+ |
| **Total** | **66** | **19** | **~150** |

The Build 0.11 Analytics Overview is a cross-cutting pilot, not a catalogued report: it combines
actual KPIs, monthly trends, expense composition and top parties but does not yet carry every
mandatory per-report field. It is therefore **not counted** in the 19 until the catalogue entry and
export/drill-down metadata are complete.

Each report must declare source, formula, period, currency, permission, drill-down, export,
freshness, empty state, EN/HI labels and actual/estimate/forecast status.

### 4.2 Chart library

Use a local, no-paid-service chart layer (ECharts is the planned choice; vendor the JS locally or
build server-rendered SVG if dependencies stay forbidden). Required chart families:

- Revenue and profit trend; actual vs budget vs forecast.
- Cash-flow waterfall and runway/forecast bands.
- Expense and income composition.
- Balance-sheet composition and working-capital cycle.
- Receivables/payables ageing and risk heatmap.
- Top customers/suppliers, concentration and product mix.
- Sales/purchase returns, discounts and price variance.
- Inventory movement, valuation, dead/slow stock and reorder.
- GST output/input/liability and reconciliation status.
- KPI pack: margins, ratios, DSO/DIO/DPO, growth, liquidity.
- Audit/anomaly digest and trend explanations.

Rules:

- Do not show every chart to every role; filter by role, module, data availability and period.
- Allow dashboard customisation and restore-default.
- No chart may fill a gap with invented values.
- Charts must be legible at 4K/8K and accessible; no colour-only meaning.
- Every chart has a drill-down or a written reason why drill-down is not possible.

### 4.3 Dashboard

- Role-aware home dashboard with a small set of high-value KPIs.
- Saved layouts per user; reset to default.
- Freshness/as-of timestamp and empty-state guidance.
- Links to the underlying report and source document.

---

## 5. Workstream B — Excel

Excel has three distinct meanings. They should not be conflated.

### Option B1 — Excel export/import (recommended first)

- Export real `.xlsx` workbooks, not renamed CSV.
- Workbook sheets: Cover, Read Me, Data Dictionary, Trial Balance, P&L, Balance Sheet, Cash Flow,
  Sales, Purchases, Inventory, Ageing, GST, KPI and AI Insights.
- Use Excel Tables, filters, frozen panes, number formats and formulas where safe.
- Values must equal on-screen totals; include formula/source notes.
- Import `.xlsx` for opening balances, bank statements, GSTR-2B and master data with sheet
  selection, column mapping, type coercion, preview, error report and all-or-nothing posting.
- AI-assisted mapping may suggest columns, but validation and posting remain deterministic and
  require human confirmation.

### Option B2 — AI-generated workbook

- Add an "AI Insights" sheet with narrative, variance explanations, anomaly list and forecast
  bands.
- Every AI statement cites the report/metric and source record range.
- Forecast sheets are clearly labelled and show model, assumptions and error band.
- No macro or hidden external call is required for the workbook to open.
- This is local generation, not Microsoft Copilot.

### Option B3 — AI inside Microsoft Excel

This requires an Office Add-in or Microsoft 365 Copilot integration. It needs Microsoft licensing,
an external AI provider, tenant consent and a data-protection review. It is **not** part of the
free/local path and should be a separate owner decision.

**Dependency note:** true `.xlsx` generation/import needs an approved library such as `openpyxl` or
`xlsxwriter` (free/open-source). If the project must remain standard-library-only, the fallback is
CSV plus Excel-compatible XML, which does not provide full workbook fidelity.

---

## 6. Workstream C — Power BI

Power BI is an external presentation layer, not a chart package embedded in this web app.

### C1 — Read-only analytics API and export package

- Token-authenticated, tenant-scoped, read-only endpoints under `/api/v1/analytics/...`.
- JSON and CSV exports for each fact/dimension and metric.
- Stable schema version, as-of timestamp, pagination and row-count metadata.
- No secrets, no cross-tenant rows, permission checked before export.

### C2 — Semantic model and Power Query templates

- Star schema: journal facts, invoice/bill/payment facts, account/party/item/date dimensions.
- Written DAX measures for revenue, profit, cash, AR/AP, ageing, GST and ratios.
- Power Query M templates for the REST/CSV endpoints.
- A starter `.pbix`/`.pbit` build guide. A binary `.pbix` is normally authored once in Power BI
  Desktop, not generated by the accounting app.
- Scheduled refresh only if the owner chooses Power BI Service (paid licensing); otherwise manual
  Desktop refresh from the export package.

### C3 — Security and truth rules

- Row-level security by tenant and, where required, branch/role.
- Power BI totals must reconcile to the app's deterministic totals.
- AI visuals or Copilot in Power BI are optional and separately licensed; they do not become the
  source of truth.
- No Power BI visual may be treated as an audited financial statement without the app's report
  drill-down and period labels.

---

## 7. Workstream D — AI insights

### 7.1 AI maturity ladder

1. **Descriptive** — deterministic metrics, trends and comparisons.
2. **Diagnostic** — variance explanations and anomaly indicators.
3. **Predictive** — forecasts with explicit assumptions and error bands.
4. **Prescriptive** — suggested actions, never automatic posting.
5. **Conversational** — grounded Q&A over authorised records.

Start at levels 1–3 with deterministic/local logic. Add an LLM only when the owner approves a
provider, consent model and cost ceiling.

### 7.2 Required features

- Grounded Q&A: "Why did profit fall this month?" with citations to journal/report rows.
- Trend explanation and period comparison.
- Anomaly digest: unusual entries, duplicate-looking documents, margin/expense shifts, overdue
  concentration. Findings are indicators for review, not proof of misconduct.
- Forecasts: cash flow, revenue and expense, labelled **forecast**, with model name, assumptions
  and error band.
- AI narrative for reports and Excel/Power BI exports.
- No AI-generated journal postings or edits.

### 7.3 Grounding pipeline

```
question
  -> permission + tenant filter
  -> deterministic metric/report resolver
  -> source-record retrieval
  -> optional LLM narrative (receives verified metrics and citations)
  -> numeric consistency check
  -> label actual/estimate/forecast
  -> audit log
  -> answer with source links
```

The LLM never receives authority to calculate totals. The deterministic engine calculates; the AI
explains.

### 7.4 Privacy and provider options

| Option | Data leaves machine? | Cost | Recommendation |
|---|---|---|---|
| Local statistical engine only | No | Free | Start here |
| Local LLM (e.g. Ollama-class runtime) | No | Free software; hardware cost | Optional privacy-first Q&A |
| External AI API | Yes, with consent/config | Usage-based | Only after owner approval and data-protection review |
| Microsoft 365 Copilot in Excel | Yes, Microsoft ecosystem | Licence | Separate decision |
| Power BI Copilot | Yes, Microsoft ecosystem | Licence | Separate decision |

Requirements: AI off by default, explicit consent, tenant isolation, redaction, no cross-tenant
context, audit of AI actions, rate/cost limits and a kill switch.

---

## 8. Workstream E — Governance and quality

Every analytics feature must pass:

- Formula and source documented.
- Displayed total equals independent recalculation from source rows.
- Drill-down sums to the displayed total.
- Empty data shows an empty state, not zeros or invented values.
- Export totals equal on-screen totals.
- Permission and tenant filter proven.
- Freshness timestamp and period label shown.
- Actual/estimate/forecast separated.
- AI claims cite records and pass numeric consistency checks.
- No fabricated metrics or unsupported conclusions.
- Mobile/desktop/4K, keyboard and screen-reader checks recorded.
- Backups and restore still pass after additive schema changes.

---

## 9. Delivery phases

Effort bands are indicative for one developer working part-time, not commitments.

| Phase | Deliverable | Gate | Indicative effort |
|---|---|---|---:|
| A. Analytics foundation | Star-schema views/data mart, metric registry, API/export contract, freshness and permissions | Every metric reconciles to ledger; no new authoritative totals | 1–2 weeks |
| B. Report engine and charts | Complete 66 reports, ECharts/SVG layer, drill-down, filters, empty states, exports, EN/HI, dashboard customisation | REP-001–007; totals equal; accessibility and 4K checks | 4–6 weeks |
| C. Excel | `.xlsx` import/export, templates, validation, AI Insights sheet, workbook tests | Import/export totals equal; bad files rejected; no partial posting | 2–3 weeks |
| D. Power BI | Read-only API, CSV/JSON package, star-schema model, Power Query templates, starter report and RLS | Refresh reconciles; cross-tenant test fails closed; documented build | 2–3 weeks |
| E. AI | Local insight engine, anomaly digest, forecasts with bands; optional grounded LLM | No invented figures; citations; consent; tenant isolation; audit | 3–4 weeks |
| F. Scale to ~150 | Extend report groups, cross-business/consolidation where authorised, performance and hardening | Catalogue coverage, load tests, independent review | 3–5 weeks |

**Recommended order:** A -> B -> C -> D -> E -> F. Do not start with AI or Power BI before the
metric/report layer is trustworthy.

**Progress:** Phase A foundation is delivered in Build 0.11 (views, 19 metrics, snapshot API, pilot
screen). The gate is partly met: every exposed metric reconciles to the ledger and the API is
tenant-scoped, but external token auth, the full star schema, export package and pagination remain.
Phase B is next. Phase C/D/E first slices are delivered; the remaining full scope still depends on the open owner decisions in section 10.

---

## 10. Owner decisions required before build

**Status (2026-10-28):** AN-D3 (free/open-source dependencies) is **approved**; `openpyxl` is the only new runtime package and ECharts is vendored locally. The delivered slice uses a static Power BI export and deterministic insights only. AN-D1, AN-D2, the AI-provider choice in AN-D4, AN-D5 to AN-D8 and the full report/chart scope remain open.

| ID | Decision | Why it matters |
|---|---|---|
| AN-D1 | Is "AI-based Excel" export + AI narrative, or a Microsoft Excel add-in/Copilot integration? | Add-in/Copilot needs Microsoft licensing and external data consent |
| AN-D2 | Power BI Desktop-only export, or Power BI Service with scheduled refresh? | Service requires paid licensing |
| AN-D3 | May we add free/open-source dependencies (`openpyxl`/`xlsxwriter`, ECharts, maybe `numpy`)? | **Approved (D-035):** `openpyxl` added; ECharts vendored locally; `xlsxwriter`/`numpy` not used |
| AN-D4 | AI provider: local-only, bring-your-own API key, or no LLM (deterministic insights only)? | **No LLM chosen yet;** Build 0.12 ships deterministic insights only |
| AN-D5 | Is Hindi/English report labelling required at launch? | Affects every report and export |
| AN-D6 | Which report groups are launch-critical: financial, sales, purchase, inventory, tax, strategy? | Prevents building 150 templates before the core 66 |
| AN-D7 | Is multi-company consolidation in the first release? | Requires authorised cross-tenant design and eliminations |
| AN-D8 | Desired export/drill-down retention and audit policy | Compliance and storage |

---

## 11. What not to do

- Do not call CSV files "Excel workbooks".
- Do not call a basic CSS bar chart "the full analytics platform".
- Do not let AI calculate or invent a financial total.
- Do not embed Power BI visuals in the app without a licensing decision.
- Do not send tenant data to an external AI provider without consent, configuration and review.
- Do not ship a report or chart without a written formula and source.
- Do not fill empty charts with sample numbers.
- Do not mix actuals, estimates and forecasts in one unlabelled series.
- Do not claim the 150-template target is complete until every template has a defined source,
  formula, permission, drill-down and test.

---

## 12. Definition of done

The analytics/AI/Excel/Power BI scope is complete only when:

- The 66-report catalogue is working and tested; the ~150-template target has a defined,
  prioritised expansion plan.
- Every report has a source, formula, permission, period, drill-down, export, freshness, empty
  state and EN/HI labels.
- The dashboard supports role-aware widgets and saved layouts.
- `.xlsx` import/export works with validation and totals that equal the screen.
- A Power BI user can refresh a documented star-schema model, with RLS and reconciliation evidence.
- AI answers are grounded, cited, tenant-isolated, consent-controlled and audited.
- Forecasts and estimates are visibly separated from actuals.
- All tests, accessibility checks and independent accounting/tax reviews pass.

---

## 13. Immediate next slice

1. Owner dependency approval is recorded (D-035). AI provider scope and Power BI Desktop-vs-Service
   licensing/consent decisions remain open.
2. Phase A is delivered (views, 19 metrics, snapshot API, pilot page). Remaining Phase A boundary:
   token/API auth for BI, full fact/dimension views, JSON/CSV export package and pagination.
3. Complete the 66-report catalogue and chart layer (Phase B). **Still pending.**
4. `.xlsx` export/import (Phase C): **first slice delivered** - 20-sheet actuals workbook and
   server-side import for three flows; general workbook import and AI-authored formulas pending.
5. Power BI (Phase D): **static import pack delivered**; Service dataset, RLS, refresh and a
   token-authenticated API pending.
6. Deterministic insights (Phase E): **delivered**; optional LLM/Q&A/forecast pending consent and
   provider decisions.
7. Expand to ~150 templates and harden (Phase F). **Still pending.**

Excel export/import and a static Power BI pack are now real, and the insight layer is grounded but
rule-based. Generative AI and Power BI Service should still be treated as planned integrations, not
delivered features. The Analytics Overview pilot is not the full report/chart library.
