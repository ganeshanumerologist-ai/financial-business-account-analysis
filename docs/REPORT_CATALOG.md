# ARTHIVIO — Report Catalog

| Field | Value |
|---|---|
| Version | 1.7 |
| Date | 2026-11-06 |
| Status | **58 of 66 catalogued reports have a working screen or export** (Build 0.13 added the Report Library and nine management reports; Build 0.16 added ten; Build 0.17 added nineteen more, including R-506; Build 0.18 adds R-204 draft entries) |
| Target | ≈150 templates across 10 groups (spec §14) |
| Catalogued here | 66 named reports (Phase 2–6 priorities) |

Every report must declare: source data, formula, applicability, permissions, filters, drill-down, export, EN/HI labels, freshness, missing-data warning, and actual-vs-estimate separation.

> **Build 0.11/0.12 pilot:** `/reports/analytics` is a cross-cutting **Analytics Overview** (actual
> monthly revenue/expense, expense composition, top customers/vendors, balance checks, freshness,
> locally vendored ECharts monthly and expense-composition views and deterministic grounded insights). It is **not
> counted** in the working-report count until it gets a catalogue ID and the full per-report metadata,
> export and drill-down set above. It is not a substitute for the missing reports.
>
> **Build 0.13 Report Library:** `/reports/library` shows all 66 catalogued reports, their group,
> formula/source and honest delivery state. Build 0.13 added nine working reports: R-104, R-108,
> R-109, R-202, R-203, R-301, R-401, R-903 and R-905.
>
> **Build 0.16 report batch:** ten more working reports were added with CSV exports: R-110 trial
> balance exceptions, R-302 sales summary, R-303 top customers, R-306 sales returns, R-307
> product-wise sales, R-309 discount analysis, R-404 top suppliers, R-406 purchase returns, R-501
> stock summary and R-706 credit-limit utilisation.
>
> **Build 0.17 report batch:** nineteen more working reports were added with CSV exports: R-107 opening
> vs closing balances, R-205 locked period register, R-206 rule version usage, R-308 salesperson performance, R-405 price
> variance, R-502 stock movement history, R-503 inventory valuation, R-504 reorder/shortage, R-505
> dead/slow stock, R-506 stock adjustment register, R-507 inventory-to-GL reconciliation, R-704
> receivables risk, R-705 cash flow forecast, R-807 tax ledger, R-904 KPI dashboard pack, R-1001 trend
> explanation, R-1002 revenue forecast, R-1003 anomaly digest and R-901 budget vs actual. The library
> now marks **57 working, 0 partial and 9 planned**; planned rows still have no route and are never
> filled with sample data.
>
> **Build 0.18 report batch:** R-204 unposted / draft entries is now working at
> `/reports/draft-entries` with `/export/draft-entries.csv`. It reads `invoice.status='draft'` and
> reports draft sales invoices with age, value and ageing buckets. Build 0.18 also adds an
> audit-safe draft invoice workflow: save draft, post draft and void draft. A draft has no journal
> entry, no stock movement and no tax-invoice number; posting assigns the next INV number and
> revalidates live stock. The library now marks **58 working, 0 partial and 8 planned**. There is
> still no draft journal-entry workflow, so R-204 covers draft sales invoices only and says so on
> the screen.
>
> **Build 0.12 export surfaces:** the 20-sheet actuals workbook (`/export/workbook.xlsx`) includes
> trial balance, P&L, balance sheet, ageing, cash/bank, inventory and GST working sheets, and the
> static Power BI ZIP (`/export/powerbi.zip`) packages actuals facts and dimensions. These are
> export/BI surfaces; they do not change the screen count, and neither is the full ~150-template
> report/chart library.

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
| Export | CSV and/or `.xlsx` where implemented, PDF through print (permission-checked); per-report coverage is still incomplete |
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
| R-104 | Cash Flow (direct + indirect bridge) | journal_line + cash/bank accounts | Direct cash movements classified by counterpart; bridge = net profit ± working capital ± investing/financing | To movement detail | 2 | Working (Build 0.13) |
| R-105 | General Ledger | journal_line | Running balance per account | To journal entry | 2 | Working (Build 0.1) |
| R-106 | Journal Register / Day Book | journal_entry + lines | Chronological list, entry totals | To entry | 2 | Working (Build 0.1) |
| R-107 | Opening vs Closing Balances | journal_line + account | Opening + period debit ? period credit = closing per ledger | To ledger | 2 | Working (Build 0.17) |
| R-108 | Financial Ratios | P&L + BS | Current/quick ratio, gross/net margin, ROE, ROCE, debt-equity, asset turnover, working capital | To inputs table | 6 | Working (Build 0.13) |
| R-109 | Period-over-Period Comparison | account_balance | Δ amount and Δ % between two equal-length periods | To both periods | 6 | Working (Build 0.13) |
| R-110 | Trial Balance Exception Report | journal_entry + journal_line | Entries failing balance/line-structure checks | To entry | 2 | Working (Build 0.16) |

---

## 3. Group 2 — Accounting, ledgers and audit

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-201 | Audit Trail | audit_log | Chronological actor/action/target | 1 | Working (Build 0.1) |
| R-202 | Reversal & Correction Register | journal_entry (reversal_of) | List with reasons and links | 2 | Working (Build 0.13) |
| R-203 | Account Activity Summary | journal_line | Count + value per account per period | 2 | Working (Build 0.13) |
| R-204 | Unposted / Draft Entries | `invoice.status='draft'` | Draft sales invoices with age, value and ageing buckets; no journal, stock or tax-invoice effect until posted | To invoice | 2 | Working (Build 0.18) |
| R-205 | Locked Period Register | period_lock + user | Locked periods with locking actor and timestamp | To audit log | 2 | Working (Build 0.17) |
| R-206 | Rule Version Usage | journal_entry | Posted entries grouped by the rule version stored at posting time | 2 | Working (Build 0.17) |

---

## 4. Group 3 — Sales and customer analysis

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-301 | Sales Register | invoice + lines | Σ taxable, tax, round-off, gross per posted invoice | 3 | Working (Build 0.13) |
| R-302 | Sales Summary by Period | invoice | Grouped totals + month growth % | 3 | Working (Build 0.16) |
| R-303 | Top Customers | invoice + customer | Rank by revenue, share % | 3 | Working (Build 0.16) |
| R-304 | Customer Ageing | open AR items | Buckets 0-30/31-60/61-90/90+ | 3 | Working (Build 0.2) |
| R-305 | Customer Statement | invoice + receipt | Opening + invoices − receipts = closing | 3 | Working + share link (Build 0.6) |
| R-306 | Sales Returns | credit notes | Returns and return rate % | 3 | Working (Build 0.16) |
| R-307 | Product-wise Sales | invoice lines + product | Qty, revenue, margin at current cost | 3 | Working (Build 0.16) |
| R-308 | Salesperson Performance | invoice + payment + journal creator | Posted invoice revenue and receipt collections per creator | To invoices/receipts | 6 | Working (Build 0.17) |
| R-309 | Discount Analysis | invoice lines | Discount value and % of gross | 6 | Working (Build 0.16) |

---

## 5. Group 4 — Purchase and supplier analysis

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-401 | Purchase Register | bill + lines | Σ taxable, tax, round-off, gross per posted bill | 3 | Working (Build 0.13) |
| R-402 | Supplier Ageing | open AP items | Buckets 0-30/31-60/61-90/90+ | 3 | Working (Build 0.2) |
| R-403 | Supplier Statement | purchase + payment | Opening + purchases − payments | 3 | Working + share link (Build 0.6) |
| R-404 | Top Suppliers / Concentration | purchase + vendor | Rank + share % | 6 | Working (Build 0.16) |
| R-405 | Price Variance | bill lines + item cost | Latest bill price vs previous bill and current weighted-average cost | To bill | 6 | Working (Build 0.17) |
| R-406 | Purchase Return Analysis | debit notes | Returns + rate | 3 | Working (Build 0.16) |

---

## 6. Group 5 — Inventory and warehouse

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-501 | Stock Summary | posted invoice/bill/credit/debit lines + item | Opening + in - out = closing per item | 4 | Working (Build 0.16) |
| R-502 | Stock Movement History | posted invoice/bill/credit/debit lines | Chronological in/out with source document | To document | 4 | Working (Build 0.17) |
| R-503 | Inventory Valuation | item stock + current cost | Closing quantity ? current moving weighted-average cost | To item | 4 | Working (Build 0.17) |
| R-504 | Reorder / Shortage | item stock + reorder level | Items at or below reorder level, or out of stock | To item | 4 | Working (Build 0.17) |
| R-505 | Dead / Slow Stock | posted stock movements + item | Stocked items with no movement for N days | To item | 4 | Working (Build 0.17) |
| R-506 | Stock Adjustment Register | `stock_adjustment` + item + journal_entry | Signed quantity, current-cost value, reason, note, journal and posting user; no approval workflow | To stock movements / item | 4 | Working (Build 0.17) |
| R-507 | Inventory ? GL Reconciliation | item stock value + inventory ledger | Item-master stock value versus inventory account balance | To ledger/item | 4 | Working (Build 0.17) |
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
| R-701 | Cash Book | journal_line (cash accounts) | Opening + receipts − payments | 2 | Working (Build 0.9) |
| R-702 | Bank Book | journal_line (each linked bank account) | Opening + receipts - payments | 2 | Working (Build 0.10, multi-bank) |
| R-703 | Bank Reconciliation Statement | statement + ledger | Difference = timing + errors (explained) | 3 | Working (Build 0.4) |
| R-704 | Receivables Risk | open AR + ageing + credit limit | Overdue exposure, credit utilisation and prior-period trend | To customer/invoice | 6 | Working (Build 0.17) |
| R-705 | Cash Flow Forecast | open AR/AP + due dates | Weekly opening cash + scheduled collections - scheduled payments (**labelled forecast**) | To customer/vendor | 6 | Working (Build 0.17) |
| R-706 | Credit Limit Utilisation | customer + open AR | Outstanding vs limit | 6 | Working (Build 0.16) |

---

## 9. Group 8 — Tax, GST and compliance

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-801 | GST Output Summary | invoice lines | Σ tax by rate/HSN | 3 | Working (Build 0.3) |
| R-802 | GST Input Summary | purchase lines | Σ tax by rate/HSN | 3 | Working (Build 0.3) |
| R-803 | GSTR-1 Working Paper | invoices | Period-wise outward supplies | 9 | Working CSV/JSON (Build 0.3) |
| R-804 | GSTR-3B Working Paper | invoices, credit notes, bills, debit notes | Output − eligible ITC, head-wise | 9 | Working (Build 0.5) |
| R-805 | HSN/SAC Summary | invoice/purchase lines | Qty + value + tax per code | 3 | Working (GSTR-1 HSN section, Build 0.3) |
| R-806 | ITC Reconciliation (2B) | imported 2B + purchase | Matched / mismatched / missing + ITC review + 3B eligible ITC | 9 | Working (Build 0.7, working CSV; no ITC posting) |
| R-807 | Tax Ledger | journal_line on tax accounts | Opening + output tax - input credit = closing per tax ledger | To ledger | 3 | Working (Build 0.17) |

⚠️ Tax reports require professional review; none may be presented as a filed return.

---

## 10. Group 9 — Strategy, organisation and process

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-901 | Budget vs Actual | budget + journal_line | Variance = actual − budget | 6 | Working (Build 0.17) |
| R-902 | Department / Branch P&L | journal_line + scoping | Contribution by scope | 6 | Not implemented |
| R-903 | Expense Breakdown | journal_line (expense) | Σ by account + share % | 6 | Working (Build 0.13) |
| R-904 | KPI Dashboard Pack | statements + ratios + cash + ageing + inventory | Actual-only KPI cards with formula and source | To source report | 6 | Working (Build 0.17) |
| R-905 | Working Capital Cycle | BS + AR/AP + bills | DSO + DIO - DPO | 6 | Working (Build 0.13) |

---

## 11. Group 10 — AI, forecasting and cross-business

| ID | Report | Source | Formula | Phase | Status |
|---|---|---|---|---|---|
| R-1001 | Trend Explanation | posted monthly revenue + expenses | Deterministic statistics and narrative, sources cited | To month | 8 | Working (Build 0.17) |
| R-1002 | Revenue Forecast | posted monthly revenue | Least-squares output, **explicitly labelled forecast** with indicative band | To actual month | 8 | Working (Build 0.17) |
| R-1003 | Anomaly Digest | journal + invoice + stock + AR | Rule-based review prompts with reasons | To document | 8 | Working (Build 0.17) |
| R-1004 | Consolidated Multi-Company | multiple tenants/entities | Sum with intercompany eliminations (**authorised only**) | 7 | Not implemented |

**Rule:** AI reports never replace deterministic calculations; every number must trace to records.

---

## 12. Coverage summary

| Group | Catalogued | Implemented | Verified |
|---|---|---|---|
| Financial statements | 10 | 10 | 10 |
| Accounting & audit | 6 | 5 | 5 |
| Sales & customers | 9 | 9 | 9 |
| Purchases & suppliers | 6 | 6 | 6 |
| Inventory & warehouse | 8 | 7 | 7 |
| Costing & operations | 5 | 0 | 0 |
| Cash, credit & risk | 6 | 6 | 6 |
| Tax & compliance | 7 | 7 | 7 |
| Strategy & process | 4 | 3 | 3 |
| Management & KPIs | 1 | 1 | 1 |
| AI-assisted analysis | 3 | 3 | 3 |
| AI & cross-business | 1 | 0 | 0 |
| **Total** | **66** | **57** | **57** |

Implemented counts include only reports with a route and a passing automated check; partial
working papers (for example opening/closing statement balances) are noted in the group tables but
not counted as complete. Build 0.6 adds GSTR-2B reconciliation (R-806) and statement sharing for
R-305/R-403; Build 0.7 adds per-line ITC review and a GSTR-3B-vs-2B comparison inside R-806;
Build 0.9 adds cash book (R-701) and bank book (R-702). Build 0.10 makes the bank book selectable
for every linked bank account, but adds no new catalogue row or report count. Build 0.17 adds
R-901 budget vs actual with stored monthly budgets, and R-506 stock adjustment register with
current-cost manual adjustments.

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
