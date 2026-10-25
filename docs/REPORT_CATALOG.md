# ARTHIVIO — Report Catalog

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-10-24 |
| Status | Catalogue only — **0 reports implemented** |
| Target | ≈150 templates across 10 groups (spec §14) |
| Catalogued here | 66 named reports (Phase 2–6 priorities) |

Every report must declare: source data, formula, applicability, permissions, filters, drill-down, export, EN/HI labels, freshness, missing-data warning, and actual-vs-estimate separation.

---

## 1. Mandatory metadata (per report)

| Field | Requirement |
|---|---|
| Source | Exact tables/rows feeding the report |
| Formula | Written formula, not "calculated in code" |
| Period | Default range + override behaviour |
| Currency | Display currency + rate source |
| Permission | Permission key required to view/export |
| Drill-down | Link from every total to contributing lines |
| Export | CSV / Excel / PDF (permission-checked) |
| Freshness | As-of timestamp + staleness threshold |
| Empty state | Explicit "no data", never fabricated values |
| Labels | EN + HI |

---

## 2. Group 1 — Financial statements and performance

| ID | Report | Source | Formula | Drill-down | Phase | Status |
|---|---|---|---|---|---|---|
| R-101 | Trial Balance | journal_line, account | Per account: Σdebit, Σcredit, closing signed balance | To ledger | 2 | Working (Build 0.1) |
| R-102 | Profit & Loss | journal_line, account type income/expense | Σincome(credit−debit) − Σexpense(debit−credit) | To ledger | 2 | Working (Build 0.1) |
| R-103 | Balance Sheet | journal_line, account type A/L/E | Assets = Liabilities + Equity (retained earnings included) | To ledger | 2 | Working (Build 0.1) |
| R-104 | Cash Flow (indirect) | journal_line + cash accounts | Net profit + non-cash adj ± working capital ± investing/financing | To ledger | 2 | Not implemented |
| R-105 | General Ledger | journal_line | Running balance per account | To journal entry | 2 | Working (Build 0.1) |
| R-106 | Journal Register / Day Book | journal_entry + lines | Chronological list, entry totals | To entry | 2 | Working (Build 0.1) |
| R-107 | Opening vs Closing Balances | account_balance | Opening + movements = closing | To ledger | 2 | Partial (statement opening/closing) |
| R-108 | Financial Ratios | P&L + BS | Current ratio, gross/net margin, ROCE, debt-equity | To source lines | 6 | Not implemented |
| R-109 | Period-over-Period Comparison | account_balance | Δ amount and Δ % between two periods | To both periods | 6 | Not implemented |
| R-110 | Trial Balance Exception Report | journal_entry | Entries failing balance/precision checks | To entry | 2 | Not implemented |

---

## 3. Group 2 — Accounting, ledgers and audit

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-201 | Audit Trail | audit_log | Chronological actor/action/target | 1 | Working (Build 0.1) |
| R-202 | Reversal & Correction Register | journal_entry (reversal_of) | List with reasons and links | 2 | Not implemented |
| R-203 | Account Activity Summary | journal_line | Count + value per account per period | 2 | Not implemented |
| R-204 | Unposted / Draft Entries | journal_entry status=draft | List + age | 2 | Not implemented |
| R-205 | Locked Period Register | fiscal_period | Periods with status + who locked | 2 | Not implemented |
| R-206 | Rule Version Usage | journal_entry | Entries grouped by applied rule version | 2 | Not implemented |

---

## 4. Group 3 — Sales and customer analysis

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-301 | Sales Register | invoice lines | Σ net, tax, gross per invoice | 3 | Not implemented |
| R-302 | Sales Summary by Period | invoice | Grouped totals + growth % | 3 | Not implemented |
| R-303 | Top Customers | invoice | Rank by revenue, share % | 3 | Not implemented |
| R-304 | Customer Ageing | open AR items | Buckets 0-30/31-60/61-90/90+ | 3 | Working (Build 0.2) |
| R-305 | Customer Statement | invoice + receipt | Opening + invoices − receipts = closing | 3 | Working + share link (Build 0.6) |
| R-306 | Sales Returns | credit notes | Σ returns, return rate % | 3 | Not implemented |
| R-307 | Product-wise Sales | invoice lines + product | Qty, revenue, margin | 3 | Not implemented |
| R-308 | Salesperson Performance | invoice + user | Revenue and collection per user | 6 | Not implemented |
| R-309 | Discount Analysis | invoice lines | Discount value and % of gross | 6 | Not implemented |

---

## 5. Group 4 — Purchase and supplier analysis

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-401 | Purchase Register | purchase lines | Σ net, tax, gross | 3 | Not implemented |
| R-402 | Supplier Ageing | open AP items | Buckets 0-30/31-60/61-90/90+ | 3 | Working (Build 0.2) |
| R-403 | Supplier Statement | purchase + payment | Opening + purchases − payments | 3 | Working + share link (Build 0.6) |
| R-404 | Top Suppliers / Concentration | purchase | Rank + share % | 6 | Not implemented |
| R-405 | Price Variance | purchase lines | Actual vs last/standard price | 6 | Not implemented |
| R-406 | Purchase Return Analysis | debit notes | Σ returns + rate | 3 | Not implemented |

---

## 6. Group 5 — Inventory and warehouse

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-501 | Stock Summary | stock_movement | Per item: in − out per the §11 formula | 4 | Not implemented |
| R-502 | Stock Movement History | stock_movement | Chronological with source doc | 4 | Not implemented |
| R-503 | Inventory Valuation | stock + cost layer | FIFO / weighted average | 4 | Not implemented |
| R-504 | Reorder / Shortage | stock + reorder level | Items below threshold | 4 | Not implemented |
| R-505 | Dead / Slow Stock | stock_movement | No movement in N days | 4 | Not implemented |
| R-506 | Stock Adjustment Register | adjustments | List with reasons + approver | 4 | Not implemented |
| R-507 | Inventory ↔ GL Reconciliation | stock value vs GL | Difference + cause | 4 | Not implemented |
| R-508 | Expiry / Batch Report | batch | Days to expiry buckets | 4 | Not implemented |

---

## 7. Group 6 — Costing, manufacturing and operations

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-601 | Job / Project Costing | cost entries | Direct + allocated indirect cost | 7 | Not implemented |
| R-602 | WIP Report | production orders | Inputs − completed output | 7 | Not implemented |
| R-603 | Production Consumption | production | Actual vs standard consumption | 7 | Not implemented |
| R-604 | Yield / Wastage | production | Output ÷ input, wastage % | 7 | Not implemented |
| R-605 | Cost Centre Performance | cost entries | Budget vs actual per centre | 6 | Not implemented |

---

## 8. Group 7 — Cash, credit and risk

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-701 | Cash Book | journal_line (cash accounts) | Opening + receipts − payments | 2 | Not implemented |
| R-702 | Bank Book | journal_line (bank accounts) | Opening + receipts − payments | 2 | Not implemented |
| R-703 | Bank Reconciliation Statement | statement + ledger | Difference = timing + errors (explained) | 3 | Working (Build 0.4) |
| R-704 | Receivables Risk | AR + ageing + history | Overdue value, exposure, trend | 6 | Not implemented |
| R-705 | Cash Flow Forecast | AR/AP due dates + history | Projected inflows/outflows (**labelled forecast**) | 6 | Not implemented |
| R-706 | Credit Limit Utilisation | customer + AR | Outstanding ÷ limit | 6 | Not implemented |

---

## 9. Group 8 — Tax, GST and compliance

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-801 | GST Output Summary | invoice lines | Σ tax by rate/HSN | 3 | Working (Build 0.3) |
| R-802 | GST Input Summary | purchase lines | Σ tax by rate/HSN | 3 | Working (Build 0.3) |
| R-803 | GSTR-1 Working Paper | invoices | Period-wise outward supplies | 9 | Working CSV/JSON (Build 0.3) |
| R-804 | GSTR-3B Working Paper | invoices, credit notes, bills, debit notes | Output − eligible ITC, head-wise | 9 | Working (Build 0.5) |
| R-805 | HSN/SAC Summary | invoice/purchase lines | Qty + value + tax per code | 3 | Working (GSTR-1 HSN section, Build 0.3) |
| R-806 | ITC Reconciliation (2B) | imported 2B + purchase | Matched / mismatched / missing | 9 | Working (Build 0.6, working CSV) |
| R-807 | Tax Ledger | journal_line (tax accounts) | Opening + payable − paid = closing | 3 | Not implemented |

⚠️ Tax reports require professional review; none may be presented as a filed return.

---

## 10. Group 9 — Strategy, organisation and process

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-901 | Budget vs Actual | budget + journal_line | Variance = actual − budget | 6 | Not implemented |
| R-902 | Department / Branch P&L | journal_line + scoping | Contribution by scope | 6 | Not implemented |
| R-903 | Expense Breakdown | journal_line (expense) | Σ by category + share % | 6 | Not implemented |
| R-904 | KPI Dashboard Pack | multiple | Composite with definitions shown | 6 | Not implemented |
| R-905 | Working Capital Cycle | BS + AR/AP | DSO + DIO − DPO | 6 | Not implemented |

---

## 11. Group 10 — AI, forecasting and cross-business

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-1001 | Trend Explanation | historical series | Deterministic stats + narrative, sources cited | 8 | Not implemented |
| R-1002 | Revenue Forecast | history | Model output, **explicitly labelled forecast** with error band | 8 | Not implemented |
| R-1003 | Anomaly Digest | ledger + rules | Flagged items with reasons | 8 | Not implemented |
| R-1004 | Consolidated Multi-Company | multiple tenants/entities | Sum with intercompany eliminations (**authorised only**) | 7 | Not implemented |

**Rule:** AI reports never replace deterministic calculations; every number must trace to records.

---

## 12. Coverage summary

| Group | Catalogued | Implemented | Verified |
|---|---|---|---|
| 1 Financial statements | 10 | 5 | 5 |
| 2 Accounting/audit | 6 | 1 | 1 |
| 3 Sales | 9 | 2 | 2 |
| 4 Purchase | 6 | 2 | 2 |
| 5 Inventory | 8 | 0 | 0 |
| 6 Costing/manufacturing | 5 | 0 | 0 |
| 7 Cash/credit/risk | 6 | 1 | 1 |
| 8 Tax/compliance | 7 | 6 | 6 |
| 9 Strategy/process | 5 | 0 | 0 |
| 10 AI/forecast | 4 | 0 | 0 |
| **Total** | **66** | **17** | **17** |

Implemented counts include only reports with a route and a passing automated check; partial
working papers (for example opening/closing statement balances) are noted in the group tables but
not counted as complete. Build 0.6 adds GSTR-2B reconciliation (R-806) and statement sharing for
R-305/R-403.

The spec's ≈150 target will be reached by extending groups 1–10; the 66 catalogued here are the ones with a defined formula and a clear user. Reports without a defined source and formula are not catalogued — they would be decoration, not information.

---

## 13. Report correctness gate

No report ships until:

- [ ] Its formula is written down and reviewed.
- [ ] Its total equals an independent recalculation from source rows (REP-001).
- [ ] Drill-down sums to the displayed total (REP-002).
- [ ] Empty data shows an empty state, not zeros or invented values (REP-004).
- [ ] Freshness and period filters behave correctly (REP-003, REP-005).
- [ ] Export totals equal on-screen totals (EXP-001).
