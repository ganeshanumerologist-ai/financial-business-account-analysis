"""Deterministic management reports built only from posted records.

The functions in this module do not cache, forecast or invent figures. Every
number is derived from journal rows, invoices, bills or the chart of accounts.
Ratios may be floats; money stays in integer paise until display.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from . import accounting as acct
from . import advanced


class ReportError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# dates and tenant helpers
# ---------------------------------------------------------------------------

def _tenant_id(tenant) -> str:
    if isinstance(tenant, str):
        return tenant
    try:
        return tenant["id"]
    except (KeyError, IndexError, TypeError):
        raise ReportError("BAD_TENANT", "A tenant is required")


def _fiscal_start(tenant, today: date) -> date:
    start_month = 4
    try:
        start_month = int(tenant["fiscal_year_start_month"] or 4)
    except (KeyError, IndexError, TypeError):
        pass
    year = today.year if today.month >= start_month else today.year - 1
    return date(year, start_month, 1)


def resolve_period(tenant, date_from: str | None = None,
                   date_to: str | None = None) -> dict:
    today = date.today()
    default_from = _fiscal_start(tenant, today).isoformat()
    dfrom = date_from or default_from
    dto = date_to or today.isoformat()
    _validate_period(dfrom, dto)
    return {"from": dfrom, "to": dto}


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ReportError("BAD_DATE", f"{field} must be a valid YYYY-MM-DD date")


def _validate_period(date_from: str, date_to: str) -> None:
    start = _parse_date(date_from, "From")
    end = _parse_date(date_to, "To")
    if start > end:
        raise ReportError("BAD_PERIOD", "From date must be on or before To date")


def _before(value: str) -> str:
    return (date.fromisoformat(value) - timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# account balances
# ---------------------------------------------------------------------------

def _balance(conn: sqlite3.Connection, tenant_id: str, groups: tuple[str, ...],
             as_of: str) -> int:
    if not groups:
        return 0
    placeholders = ",".join("?" for _ in groups)
    row = conn.execute(
        f"""SELECT COALESCE(SUM(l.debit_paise - l.credit_paise), 0) AS bal
            FROM journal_line l
            JOIN journal_entry e ON e.id = l.entry_id AND e.tenant_id = l.tenant_id
            JOIN account a ON a.id = l.account_id AND a.tenant_id = l.tenant_id
            WHERE l.tenant_id = ? AND a.group_code IN ({placeholders})
              AND e.entry_date <= ?""",
        (tenant_id, *groups, as_of),
    ).fetchone()
    return int(row["bal"] or 0)


def _groups_for_type(conn: sqlite3.Connection, tenant_id: str, typ: str) -> list[str]:
    # Include the empty group: a custom ledger with no group still has a type and
    # must appear in the cash-flow bridge rather than silently becoming a residual.
    return [r["group_code"] if r["group_code"] is not None else ""
            for r in conn.execute(
                "SELECT DISTINCT group_code FROM account WHERE tenant_id=? AND type=?",
                (tenant_id, typ),
            ).fetchall()]


def _cash_balance(conn: sqlite3.Connection, tenant_id: str, as_of: str) -> int:
    return _balance(conn, tenant_id, ("cash", "bank"), as_of)


def _cash_account_ids(conn: sqlite3.Connection, tenant_id: str) -> list[str]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM account WHERE tenant_id=? AND group_code IN ('cash','bank')",
        (tenant_id,),
    ).fetchall()]


# ---------------------------------------------------------------------------
# R-104 cash flow
# ---------------------------------------------------------------------------

OPERATING_IN = {
    "Customer receipts", "Operating receipts", "Supplier refunds",
    "Tax refunds", "Inventory sales", "Other operating receipts",
}
OPERATING_OUT = {
    "Supplier payments", "Operating payments", "Customer refunds",
    "Tax payments", "Inventory purchases", "Other operating payments",
}


def _classify_cash_entry(entry, cash_delta: int, other_rows: list[sqlite3.Row]) -> str:
    if entry["source_type"] == "opening":
        return "Opening balances"
    groups = {r["group_code"] for r in other_rows if r["group_code"]}
    types = {r["type"] for r in other_rows if r["type"]}
    if "fixed_asset" in groups:
        return "Investing"
    if groups & {"capital", "retained_earnings", "loan"}:
        return "Financing"
    if cash_delta > 0:
        if "receivable" in groups:
            return "Customer receipts"
        if "income" in types:
            return "Operating receipts"
        if "payable" in groups:
            return "Supplier refunds"
        if groups & {"duties_taxes", "gst_input"}:
            return "Tax refunds"
        if "inventory" in groups:
            return "Inventory sales"
        return "Other operating receipts"
    if "payable" in groups:
        return "Supplier payments"
    if "expense" in types:
        return "Operating payments"
    if "inventory" in groups:
        return "Inventory purchases"
    if groups & {"duties_taxes", "gst_input"}:
        return "Tax payments"
    if "receivable" in groups:
        return "Customer refunds"
    return "Other operating payments"


def cash_flow(conn: sqlite3.Connection, tenant, date_from: str, date_to: str) -> dict:
    """R-104: direct cash movement with an indirect reconciliation bridge."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    cash_ids = _cash_account_ids(conn, tenant_id)
    opening = _cash_balance(conn, tenant_id, _before(date_from))
    closing = _cash_balance(conn, tenant_id, date_to)
    if not cash_ids:
        return {
            "from": date_from, "to": date_to, "opening": opening, "closing": closing,
            "net_change": closing - opening, "rows": [], "categories": [],
            "bridge": [], "bridge_total": 0, "difference": closing - opening,
            "cash_accounts": 0,
        }

    placeholders = ",".join("?" for _ in cash_ids)
    entries = conn.execute(
        f"""SELECT e.id, e.entry_no, e.entry_date, e.narration, e.source_type,
                   COALESCE(SUM(CASE WHEN l.account_id IN ({placeholders})
                                     THEN l.debit_paise - l.credit_paise ELSE 0 END), 0) AS cash_delta
            FROM journal_entry e
            JOIN journal_line l ON l.entry_id = e.id AND l.tenant_id = e.tenant_id
            WHERE e.tenant_id = ? AND e.entry_date BETWEEN ? AND ?
            GROUP BY e.id
            HAVING cash_delta <> 0
            ORDER BY e.entry_date, e.entry_no""",
        (*cash_ids, tenant_id, date_from, date_to),
    ).fetchall()

    totals: dict[str, int] = {}
    rows: list[dict] = []
    for entry in entries:
        other = conn.execute(
            f"""SELECT a.type, a.group_code,
                       COALESCE(SUM(l.debit_paise - l.credit_paise), 0) AS signed
                FROM journal_line l
                JOIN account a ON a.id = l.account_id AND a.tenant_id = l.tenant_id
                WHERE l.entry_id = ? AND l.account_id NOT IN ({placeholders})
                GROUP BY a.type, a.group_code
                ORDER BY ABS(COALESCE(SUM(l.debit_paise - l.credit_paise), 0)) DESC""",
            (entry["id"], *cash_ids),
        ).fetchall()
        category = _classify_cash_entry(entry, int(entry["cash_delta"]), other)
        amount = int(entry["cash_delta"])
        totals[category] = totals.get(category, 0) + amount
        rows.append({
            "date": entry["entry_date"], "ref": entry["entry_no"],
            "narration": entry["narration"], "category": category,
            "amount": amount,
        })

    classified = sum(totals.values())
    net_change = closing - opening
    if classified != net_change:
        residual = net_change - classified
        totals["Unclassified / other"] = residual
        rows.append({
            "date": "", "ref": "", "narration": "Reconciliation residual",
            "category": "Unclassified / other", "amount": residual,
        })

    categories = [
        {"category": k, "amount": v,
         "direction": "in" if v >= 0 else "out"}
        for k, v in sorted(totals.items(), key=lambda kv: (kv[1] < 0, -abs(kv[1])))
    ]
    operating_in = sum(v for k, v in totals.items() if k in OPERATING_IN and v > 0)
    operating_out = -sum(v for k, v in totals.items() if k in OPERATING_OUT and v < 0)
    investing = sum(v for k, v in totals.items() if k == "Investing")
    financing = sum(v for k, v in totals.items()
                    if k in ("Financing", "Opening balances"))

    bridge = _cash_bridge(conn, tenant_id, date_from, date_to, opening, closing)
    return {
        "from": date_from, "to": date_to, "opening": opening, "closing": closing,
        "net_change": net_change, "rows": rows, "categories": categories,
        "operating_in": operating_in, "operating_out": operating_out,
        "investing": investing, "financing": financing,
        "bridge": bridge["rows"], "bridge_total": bridge["total"],
        "difference": bridge["difference"], "cash_accounts": len(cash_ids),
    }


def _cash_bridge(conn: sqlite3.Connection, tenant_id: str, date_from: str,
                 date_to: str, opening: int, closing: int) -> dict:
    before = _before(date_from)
    pnl = acct.profit_and_loss(conn, tenant_id, date_from, date_to)

    def pair(groups: tuple[str, ...]) -> tuple[int, int]:
        return (_balance(conn, tenant_id, groups, before),
                _balance(conn, tenant_id, groups, date_to))

    ar_open, ar_close = pair(("receivable",))
    inv_open, inv_close = pair(("inventory",))
    ap_open, ap_close = pair(("payable",))
    gst_open, gst_close = pair(("duties_taxes", "gst_input"))
    fixed_open, fixed_close = pair(("fixed_asset",))
    equity_groups = tuple(_groups_for_type(conn, tenant_id, "equity"))
    equity_open, equity_close = pair(equity_groups)

    asset_groups = _groups_for_type(conn, tenant_id, "asset")
    liability_groups = _groups_for_type(conn, tenant_id, "liability")
    other_asset_groups = tuple(
        g for g in asset_groups
        if g not in ("cash", "bank", "receivable", "inventory", "fixed_asset", "gst_input")
    )
    other_liability_groups = tuple(
        g for g in liability_groups
        if g not in ("payable", "duties_taxes")
    )
    oa_open, oa_close = pair(other_asset_groups)
    ol_open, ol_close = pair(other_liability_groups)

    # Liability balances are credit-positive when shown as a positive number.
    ap_open, ap_close = -ap_open, -ap_close
    gst_open, gst_close = -gst_open, -gst_close
    equity_open, equity_close = -equity_open, -equity_close
    ol_open, ol_close = -ol_open, -ol_close

    rows = [
        {"label": "Net profit", "amount": pnl["net_profit"],
         "basis": "posted income minus posted expenses"},
        {"label": "Change in receivables", "amount": -(ar_close - ar_open),
         "basis": "increase in receivable uses cash"},
        {"label": "Change in inventory", "amount": -(inv_close - inv_open),
         "basis": "increase in inventory uses cash"},
        {"label": "Change in payables", "amount": ap_close - ap_open,
         "basis": "increase in payable preserves cash"},
        {"label": "Change in net GST", "amount": gst_close - gst_open,
         "basis": "increase in net GST liability preserves cash"},
        {"label": "Investing: fixed assets", "amount": -(fixed_close - fixed_open),
         "basis": "fixed-asset purchases use cash"},
        {"label": "Financing: equity", "amount": equity_close - equity_open,
         "basis": "capital introduced or returned"},
        {"label": "Other balance-sheet movements",
         "amount": -(oa_close - oa_open) + (ol_close - ol_open),
         "basis": "remaining asset and liability changes"},
    ]
    total = sum(r["amount"] for r in rows)
    actual = closing - opening
    return {"rows": rows, "total": total, "actual": actual,
            "difference": actual - total}


# ---------------------------------------------------------------------------
# R-108 financial ratios
# ---------------------------------------------------------------------------

def _ratio(numerator, denominator):
    if denominator in (0, None):
        return None
    return numerator / denominator


def financial_ratios(conn: sqlite3.Connection, tenant, date_from: str,
                     date_to: str) -> dict:
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    pnl = acct.profit_and_loss(conn, tenant_id, date_from, date_to)
    bs = acct.balance_sheet(conn, tenant_id, date_to)
    fixed_assets = _balance(conn, tenant_id, ("fixed_asset",), date_to)
    inventory = _balance(conn, tenant_id, ("inventory",), date_to)
    current_assets = bs["total_assets"] - fixed_assets
    current_liabilities = bs["total_liabilities"]
    equity = bs["total_equity"]
    revenue = pnl["total_income"]
    cogs = sum(r["amount"] for r in pnl["expense"]
               if _expense_group(conn, tenant_id, r["code"]) == "cost_of_goods_sold")
    gross_profit = revenue - cogs
    net_profit = pnl["net_profit"]
    capital_employed = bs["total_assets"] - current_liabilities

    rows = [
        {"key": "current_ratio", "label": "Current ratio", "kind": "ratio",
         "value": _ratio(current_assets, current_liabilities),
         "formula": "current assets ÷ current liabilities",
         "note": "Current assets exclude fixed assets; liabilities are current in this chart."},
        {"key": "quick_ratio", "label": "Quick ratio", "kind": "ratio",
         "value": _ratio(current_assets - inventory, current_liabilities),
         "formula": "(current assets − inventory) ÷ current liabilities",
         "note": "Inventory is excluded because it may not convert quickly."},
        {"key": "gross_margin", "label": "Gross margin", "kind": "percent",
         "value": _ratio(gross_profit, revenue),
         "formula": "(revenue − COGS) ÷ revenue",
         "note": "COGS uses the cost_of_goods_sold account group."},
        {"key": "net_margin", "label": "Net margin", "kind": "percent",
         "value": _ratio(net_profit, revenue),
         "formula": "net profit ÷ revenue",
         "note": "Net profit is posted income minus posted expenses."},
        {"key": "roe", "label": "Return on equity", "kind": "percent",
         "value": _ratio(net_profit, equity),
         "formula": "net profit ÷ total equity",
         "note": "Equity includes current-period retained earnings."},
        {"key": "roce", "label": "Return on capital employed", "kind": "percent",
         "value": _ratio(net_profit, capital_employed),
         "formula": "net profit ÷ (total assets − current liabilities)",
         "note": "No interest expense is assumed in this build."},
        {"key": "debt_equity", "label": "Debt to equity", "kind": "ratio",
         "value": _ratio(bs["total_liabilities"], equity),
         "formula": "total liabilities ÷ total equity",
         "note": "All liabilities in the chart are treated as debt for this ratio."},
        {"key": "asset_turnover", "label": "Asset turnover", "kind": "ratio",
         "value": _ratio(revenue, bs["total_assets"]),
         "formula": "revenue ÷ total assets",
         "note": "Uses period revenue and closing assets."},
        {"key": "working_capital", "label": "Working capital", "kind": "money",
         "value": current_assets - current_liabilities,
         "formula": "current assets − current liabilities",
         "note": "A negative value means current liabilities exceed current assets."},
    ]
    return {
        "from": date_from, "to": date_to,
        "rows": rows,
        "inputs": {
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
            "inventory": inventory,
            "fixed_assets": fixed_assets,
            "total_assets": bs["total_assets"],
            "total_liabilities": bs["total_liabilities"],
            "equity": equity,
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "capital_employed": capital_employed,
        },
        "balanced": bs["balanced"],
        "difference": bs["difference"],
    }


def _expense_group(conn: sqlite3.Connection, tenant_id: str, code: str) -> str:
    row = conn.execute(
        "SELECT group_code FROM account WHERE tenant_id=? AND code=?",
        (tenant_id, code),
    ).fetchone()
    return row["group_code"] if row else ""


# ---------------------------------------------------------------------------
# R-109 period comparison
# ---------------------------------------------------------------------------

def _previous_period(date_from: str, date_to: str) -> tuple[str, str]:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    return prev_start.isoformat(), prev_end.isoformat()


def period_comparison(conn: sqlite3.Connection, tenant, date_from: str,
                      date_to: str) -> dict:
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    prev_from, prev_to = _previous_period(date_from, date_to)
    current = acct.profit_and_loss(conn, tenant_id, date_from, date_to)
    previous = acct.profit_and_loss(conn, tenant_id, prev_from, prev_to)

    def indexed(pnl):
        out = {}
        for section, key in (("Income", "income"), ("Expense", "expense")):
            for r in pnl[key]:
                out[(section, r["code"], r["name"])] = r["amount"]
        return out

    cur = indexed(current)
    prev = indexed(previous)
    rows = []
    for key in sorted(set(cur) | set(prev), key=lambda k: (k[0] != "Income", k[1], k[2])):
        c = cur.get(key, 0)
        p = prev.get(key, 0)
        delta = c - p
        rows.append({
            "section": key[0], "code": key[1], "name": key[2],
            "current": c, "previous": p, "delta": delta,
            "pct": _ratio(delta, p),
        })
    return {
        "from": date_from, "to": date_to,
        "previous_from": prev_from, "previous_to": prev_to,
        "rows": rows,
        "metrics": {
            "revenue": {"current": current["total_income"],
                        "previous": previous["total_income"]},
            "expense": {"current": current["total_expense"],
                        "previous": previous["total_expense"]},
            "net_profit": {"current": current["net_profit"],
                           "previous": previous["net_profit"]},
        },
    }


# ---------------------------------------------------------------------------
# registers
# ---------------------------------------------------------------------------

def sales_register(conn: sqlite3.Connection, tenant, date_from: str,
                   date_to: str) -> dict:
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT i.id, i.invoice_no, i.invoice_date, c.name AS customer,
                  i.sub_total_paise AS taxable, i.tax_paise AS tax,
                  i.round_off_paise AS round_off,
                  i.total_paise AS total, i.status,
                  (SELECT COUNT(*) FROM invoice_line l WHERE l.invoice_id=i.id) AS lines
           FROM invoice i JOIN customer c ON c.id=i.customer_id
           WHERE i.tenant_id=? AND i.invoice_date BETWEEN ? AND ?
             AND i.status='posted'
           ORDER BY i.invoice_date, i.invoice_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = [dict(r) for r in rows]
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "taxable": sum(r["taxable"] for r in out),
            "tax": sum(r["tax"] for r in out),
            "round_off": sum(r["round_off"] for r in out),
            "total": sum(r["total"] for r in out),
            "count": len(out),
        },
    }


def purchase_register(conn: sqlite3.Connection, tenant, date_from: str,
                      date_to: str) -> dict:
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT b.id, b.bill_no, b.vendor_bill_no, b.bill_date, v.name AS vendor,
                  b.sub_total_paise AS taxable, b.tax_paise AS tax,
                  b.round_off_paise AS round_off,
                  b.total_paise AS total, b.status,
                  (SELECT COUNT(*) FROM bill_line l WHERE l.bill_id=b.id) AS lines
           FROM bill b JOIN vendor v ON v.id=b.vendor_id
           WHERE b.tenant_id=? AND b.bill_date BETWEEN ? AND ?
             AND b.status='posted'
           ORDER BY b.bill_date, b.bill_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = [dict(r) for r in rows]
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "taxable": sum(r["taxable"] for r in out),
            "tax": sum(r["tax"] for r in out),
            "round_off": sum(r["round_off"] for r in out),
            "total": sum(r["total"] for r in out),
            "count": len(out),
        },
    }


# ---------------------------------------------------------------------------
# R-903 expense breakdown, R-203 account activity, R-202 reversals
# ---------------------------------------------------------------------------

def expense_breakdown(conn: sqlite3.Connection, tenant, date_from: str,
                      date_to: str) -> dict:
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    pnl = acct.profit_and_loss(conn, tenant_id, date_from, date_to)
    total = pnl["total_expense"]
    rows = []
    for r in pnl["expense"]:
        rows.append({
            **r,
            "share": _ratio(r["amount"], total),
            "group": _expense_group(conn, tenant_id, r["code"]),
        })
    return {"from": date_from, "to": date_to, "rows": rows, "total": total}


def account_activity(conn: sqlite3.Connection, tenant, date_from: str,
                     date_to: str) -> dict:
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT a.code, a.name, a.type, a.group_code,
                  COUNT(l.id) AS lines,
                  COALESCE(SUM(l.debit_paise), 0) AS debit,
                  COALESCE(SUM(l.credit_paise), 0) AS credit,
                  COALESCE(SUM(l.debit_paise - l.credit_paise), 0) AS net
           FROM account a
           JOIN journal_line l ON l.account_id=a.id AND l.tenant_id=a.tenant_id
           JOIN journal_entry e ON e.id=l.entry_id AND e.tenant_id=l.tenant_id
           WHERE a.tenant_id=? AND e.entry_date BETWEEN ? AND ?
           GROUP BY a.id
           HAVING lines > 0
           ORDER BY a.code""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = [dict(r) for r in rows]
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "debit": sum(r["debit"] for r in out),
            "credit": sum(r["credit"] for r in out),
            "lines": sum(r["lines"] for r in out),
        },
    }


def reversal_register(conn: sqlite3.Connection, tenant, date_from: str,
                      date_to: str) -> dict:
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT r.id AS reversal_id, r.entry_no AS reversal_no,
                  r.entry_date AS reversal_date, r.narration AS reversal_narration,
                  o.id AS original_id, o.entry_no AS original_no,
                  o.entry_date AS original_date, o.narration AS original_narration,
                  (SELECT COALESCE(SUM(debit_paise),0) FROM journal_line
                   WHERE entry_id=o.id) AS amount
           FROM journal_entry r
           JOIN journal_entry o ON o.id=r.reversal_of AND o.tenant_id=r.tenant_id
           WHERE r.tenant_id=? AND r.entry_date BETWEEN ? AND ?
           ORDER BY r.entry_date, r.entry_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = []
    for r in rows:
        reason = r["reversal_narration"]
        if ": " in reason:
            reason = reason.split(": ", 1)[1]
        out.append({**dict(r), "reason": reason})
    return {"from": date_from, "to": date_to, "rows": out,
            "total": sum(r["amount"] for r in out)}


# ---------------------------------------------------------------------------
# R-905 working-capital cycle
# ---------------------------------------------------------------------------

def working_capital(conn: sqlite3.Connection, tenant, date_from: str,
                    date_to: str) -> dict:
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    days = (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days + 1
    pnl = acct.profit_and_loss(conn, tenant_id, date_from, date_to)
    ar = _balance(conn, tenant_id, ("receivable",), date_to)
    ap = -_balance(conn, tenant_id, ("payable",), date_to)
    inventory = _balance(conn, tenant_id, ("inventory",), date_to)
    revenue = pnl["total_income"]
    cogs = sum(r["amount"] for r in pnl["expense"]
               if _expense_group(conn, tenant_id, r["code"]) == "cost_of_goods_sold")
    purchases = conn.execute(
        """SELECT COALESCE(SUM(total_paise),0) AS total FROM bill
           WHERE tenant_id=? AND bill_date BETWEEN ? AND ? AND status='posted'""",
        (tenant_id, date_from, date_to),
    ).fetchone()["total"] or 0
    dso = _ratio(ar * days, revenue)
    dio = _ratio(inventory * days, cogs)
    dpo = _ratio(ap * days, purchases)
    ccc = (dso + dio - dpo) if None not in (dso, dio, dpo) else None
    return {
        "from": date_from, "to": date_to, "days": days,
        "inputs": {"receivable": ar, "payable": ap, "inventory": inventory,
                   "revenue": revenue, "cogs": cogs, "purchases": purchases},
        "dso": dso, "dio": dio, "dpo": dpo, "ccc": ccc,
    }


# ---------------------------------------------------------------------------
# R-302 sales summary, R-303 top customers, R-307 product sales, R-309 discounts
# ---------------------------------------------------------------------------

def sales_summary_by_period(conn: sqlite3.Connection, tenant, date_from: str,
                            date_to: str) -> dict:
    """R-302: posted invoice value grouped by calendar month."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT substr(i.invoice_date, 1, 7) AS period,
                  COUNT(*) AS invoices,
                  COALESCE(SUM(i.sub_total_paise), 0) AS taxable,
                  COALESCE(SUM(i.tax_paise), 0) AS tax,
                  COALESCE(SUM(i.total_paise), 0) AS total
           FROM invoice i
           WHERE i.tenant_id = ? AND i.status = 'posted'
             AND i.invoice_date BETWEEN ? AND ?
           GROUP BY period ORDER BY period""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = []
    previous = None
    for row in rows:
        total = int(row["total"])
        out.append({
            "period": row["period"],
            "invoices": int(row["invoices"]),
            "taxable": int(row["taxable"]),
            "tax": int(row["tax"]),
            "total": total,
            "growth": _ratio(total - previous, previous) if previous not in (None, 0) else None,
        })
        previous = total
    total_all = sum(r["total"] for r in out)
    invoices = sum(r["invoices"] for r in out)
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "periods": len(out), "invoices": invoices,
            "taxable": sum(r["taxable"] for r in out),
            "tax": sum(r["tax"] for r in out),
            "total": total_all,
            "average_invoice": total_all // invoices if invoices else 0,
        },
    }


def top_customers(conn: sqlite3.Connection, tenant, date_from: str,
                  date_to: str) -> dict:
    """R-303: posted invoice revenue ranked by customer and share."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT c.id, c.name, COUNT(i.id) AS invoices,
                  COALESCE(SUM(i.sub_total_paise), 0) AS taxable,
                  COALESCE(SUM(i.total_paise), 0) AS total
           FROM invoice i JOIN customer c ON c.id = i.customer_id
           WHERE i.tenant_id = ? AND i.status = 'posted'
             AND i.invoice_date BETWEEN ? AND ?
           GROUP BY c.id, c.name
           ORDER BY total DESC, c.name""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    total_all = sum(int(r["total"]) for r in rows)
    out = []
    cumulative = 0
    for index, row in enumerate(rows, start=1):
        amount = int(row["total"])
        cumulative += amount
        out.append({
            "rank": index, "id": row["id"], "name": row["name"],
            "invoices": int(row["invoices"]), "taxable": int(row["taxable"]),
            "total": amount, "share": _ratio(amount, total_all),
            "cumulative_share": _ratio(cumulative, total_all),
        })
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "customers": len(out), "invoices": sum(r["invoices"] for r in out),
            "taxable": sum(r["taxable"] for r in out), "total": total_all,
            "top5_share": _ratio(sum(r["total"] for r in out[:5]), total_all),
        },
    }


def product_sales(conn: sqlite3.Connection, tenant, date_from: str,
                  date_to: str) -> dict:
    """R-307: quantity and taxable revenue by item.

    Margin uses the item master's current cost, not a historical cost layer.
    That limit is shown on the screen and in the CSV.
    """
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT l.item_id,
                  COALESCE(i.sku, '') AS sku,
                  COALESCE(i.name, l.description) AS name,
                  COALESCE(i.unit, '') AS unit,
                  COALESCE(i.cost_paise, 0) AS cost_paise,
                  COALESCE(SUM(l.qty_milli), 0) AS qty_milli,
                  COALESCE(SUM(l.taxable_paise), 0) AS revenue,
                  COALESCE(SUM(l.gross_paise), 0) AS gross,
                  COALESCE(SUM(l.discount_paise), 0) AS discount
           FROM invoice_line l
           JOIN invoice inv ON inv.id = l.invoice_id AND inv.tenant_id = l.tenant_id
           LEFT JOIN item i ON i.id = l.item_id AND i.tenant_id = l.tenant_id
           WHERE inv.tenant_id = ? AND inv.status = 'posted'
             AND inv.invoice_date BETWEEN ? AND ?
           GROUP BY l.item_id, COALESCE(i.name, l.description), i.sku, i.unit,
                    i.cost_paise
           ORDER BY revenue DESC, name""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    total_revenue = sum(int(r["revenue"]) for r in rows)
    out = []
    for row in rows:
        qty = int(row["qty_milli"])
        revenue = int(row["revenue"])
        cost = (int(row["cost_paise"]) * qty + 500) // 1000
        margin = revenue - cost
        out.append({
            "item_id": row["item_id"], "sku": row["sku"], "name": row["name"],
            "unit": row["unit"], "qty_milli": qty, "revenue": revenue,
            "gross": int(row["gross"]), "discount": int(row["discount"]),
            "cost": cost, "margin": margin, "margin_pct": _ratio(margin, revenue),
            "share": _ratio(revenue, total_revenue),
        })
    total_cost = sum(r["cost"] for r in out)
    total_margin = sum(r["margin"] for r in out)
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "products": len(out), "revenue": total_revenue,
            "cost": total_cost, "margin": total_margin,
            "margin_pct": _ratio(total_margin, total_revenue),
            "top_share": _ratio(out[0]["revenue"], total_revenue) if out else None,
        },
    }


def discount_analysis(conn: sqlite3.Connection, tenant, date_from: str,
                      date_to: str) -> dict:
    """R-309: line-level discounts on posted invoices."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT i.id, i.invoice_no, i.invoice_date, c.name AS customer,
                  COALESCE(SUM(l.gross_paise), 0) AS gross,
                  COALESCE(SUM(l.discount_paise), 0) AS discount,
                  COALESCE(SUM(l.taxable_paise), 0) AS taxable,
                  i.total_paise AS total
           FROM invoice i
           JOIN customer c ON c.id = i.customer_id
           JOIN invoice_line l ON l.invoice_id = i.id AND l.tenant_id = i.tenant_id
           WHERE i.tenant_id = ? AND i.status = 'posted'
             AND i.invoice_date BETWEEN ? AND ?
           GROUP BY i.id, i.invoice_no, i.invoice_date, c.name, i.total_paise
           ORDER BY discount DESC, i.invoice_date, i.invoice_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = []
    for row in rows:
        gross = int(row["gross"])
        discount = int(row["discount"])
        out.append({
            "id": row["id"], "invoice_no": row["invoice_no"],
            "date": row["invoice_date"], "customer": row["customer"],
            "gross": gross, "discount": discount, "taxable": int(row["taxable"]),
            "total": int(row["total"]), "discount_pct": _ratio(discount, gross),
        })
    total_gross = sum(r["gross"] for r in out)
    total_discount = sum(r["discount"] for r in out)
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "invoices": len(out),
            "invoices_with_discount": sum(1 for r in out if r["discount"] > 0),
            "gross": total_gross, "discount": total_discount,
            "taxable": sum(r["taxable"] for r in out),
            "discount_share": _ratio(total_discount, total_gross),
        },
    }


# ---------------------------------------------------------------------------
# R-404 suppliers, R-406 purchase returns
# ---------------------------------------------------------------------------

def top_suppliers(conn: sqlite3.Connection, tenant, date_from: str,
                  date_to: str) -> dict:
    """R-404: posted bill value ranked by supplier and share."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT v.id, v.name, COUNT(b.id) AS bills,
                  COALESCE(SUM(b.sub_total_paise), 0) AS taxable,
                  COALESCE(SUM(b.total_paise), 0) AS total
           FROM bill b JOIN vendor v ON v.id = b.vendor_id
           WHERE b.tenant_id = ? AND b.status = 'posted'
             AND b.bill_date BETWEEN ? AND ?
           GROUP BY v.id, v.name
           ORDER BY total DESC, v.name""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    total_all = sum(int(r["total"]) for r in rows)
    out = []
    cumulative = 0
    for index, row in enumerate(rows, start=1):
        amount = int(row["total"])
        cumulative += amount
        out.append({
            "rank": index, "id": row["id"], "name": row["name"],
            "bills": int(row["bills"]), "taxable": int(row["taxable"]),
            "total": amount, "share": _ratio(amount, total_all),
            "cumulative_share": _ratio(cumulative, total_all),
        })
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "suppliers": len(out), "bills": sum(r["bills"] for r in out),
            "taxable": sum(r["taxable"] for r in out), "total": total_all,
            "top5_share": _ratio(sum(r["total"] for r in out[:5]), total_all),
        },
    }


def sales_returns(conn: sqlite3.Connection, tenant, date_from: str,
                  date_to: str) -> dict:
    """R-306: credit notes and return rate against posted invoice value."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT n.id, n.note_no, n.note_date, c.name AS customer,
                  i.invoice_no, n.reason, n.sub_total_paise AS taxable,
                  n.tax_paise AS tax, n.total_paise AS total
           FROM credit_note n
           JOIN customer c ON c.id = n.customer_id
           LEFT JOIN invoice i ON i.id = n.invoice_id
           WHERE n.tenant_id = ? AND n.note_date BETWEEN ? AND ?
           ORDER BY n.note_date, n.note_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = [dict(r) for r in rows]
    sales = sales_register(conn, tenant_id, date_from, date_to)
    taxable = sum(int(r["taxable"]) for r in out)
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "notes": len(out), "taxable": taxable,
            "tax": sum(int(r["tax"]) for r in out),
            "total": sum(int(r["total"]) for r in out),
            "sales_taxable": sales["totals"]["taxable"],
            "return_rate": _ratio(taxable, sales["totals"]["taxable"]),
        },
    }


def purchase_returns(conn: sqlite3.Connection, tenant, date_from: str,
                     date_to: str) -> dict:
    """R-406: debit notes and return rate against posted bill value."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT n.id, n.note_no, n.note_date, v.name AS vendor,
                  b.bill_no, n.reason, n.sub_total_paise AS taxable,
                  n.tax_paise AS tax, n.total_paise AS total
           FROM debit_note n
           JOIN vendor v ON v.id = n.vendor_id
           LEFT JOIN bill b ON b.id = n.bill_id
           WHERE n.tenant_id = ? AND n.note_date BETWEEN ? AND ?
           ORDER BY n.note_date, n.note_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = [dict(r) for r in rows]
    purchases = purchase_register(conn, tenant_id, date_from, date_to)
    taxable = sum(int(r["taxable"]) for r in out)
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "notes": len(out), "taxable": taxable,
            "tax": sum(int(r["tax"]) for r in out),
            "total": sum(int(r["total"]) for r in out),
            "purchase_taxable": purchases["totals"]["taxable"],
            "return_rate": _ratio(taxable, purchases["totals"]["taxable"]),
        },
    }


# ---------------------------------------------------------------------------
# R-501 stock summary
# ---------------------------------------------------------------------------

def stock_summary(conn: sqlite3.Connection, tenant, date_from: str,
                  date_to: str) -> dict:
    """R-501: derive period in/out and closing quantity from posted documents.

    The item master holds current stock. Movements after the selected end date
    are removed to reconstruct the closing quantity at that date. Manual stock
    adjustments are included as a movement source; they are valued at the item's
    current moving weighted-average cost.
    """
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """WITH movements AS (
               SELECT l.item_id, i.invoice_date AS doc_date, -l.qty_milli AS qty
               FROM invoice_line l
               JOIN invoice i ON i.id = l.invoice_id AND i.tenant_id = l.tenant_id
               WHERE i.tenant_id = ? AND i.status = 'posted' AND l.item_id IS NOT NULL
               UNION ALL
               SELECT l.item_id, b.bill_date, l.qty_milli
               FROM bill_line l
               JOIN bill b ON b.id = l.bill_id AND b.tenant_id = l.tenant_id
               WHERE b.tenant_id = ? AND b.status = 'posted' AND l.item_id IS NOT NULL
               UNION ALL
               SELECT l.item_id, n.note_date, l.qty_milli
               FROM credit_note_line l
               JOIN credit_note n ON n.id = l.credit_note_id AND n.tenant_id = l.tenant_id
               WHERE n.tenant_id = ? AND l.item_id IS NOT NULL
               UNION ALL
               SELECT l.item_id, n.note_date, -l.qty_milli
               FROM debit_note_line l
               JOIN debit_note n ON n.id = l.debit_note_id AND n.tenant_id = l.tenant_id
               WHERE n.tenant_id = ? AND l.item_id IS NOT NULL
               UNION ALL
               SELECT a.item_id, a.adjustment_date, a.qty_milli
               FROM stock_adjustment a
               WHERE a.tenant_id = ?
           )
           SELECT i.id, i.sku, i.name, i.unit, i.stock_milli AS current_stock,
                  i.cost_paise,
                  COALESCE(SUM(CASE WHEN m.doc_date BETWEEN ? AND ? AND m.qty > 0
                                    THEN m.qty ELSE 0 END), 0) AS in_period,
                  COALESCE(SUM(CASE WHEN m.doc_date BETWEEN ? AND ? AND m.qty < 0
                                    THEN -m.qty ELSE 0 END), 0) AS out_period,
                  COALESCE(SUM(CASE WHEN m.doc_date > ? THEN m.qty ELSE 0 END), 0) AS net_after
           FROM item i
           LEFT JOIN movements m ON m.item_id = i.id
           WHERE i.tenant_id = ? AND i.track_stock = 1
           GROUP BY i.id, i.sku, i.name, i.unit, i.stock_milli, i.cost_paise
           ORDER BY i.name""",
        (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id,
         date_from, date_to, date_from, date_to, date_to, tenant_id),
    ).fetchall()
    out = []
    for row in rows:
        current = int(row["current_stock"])
        in_period = int(row["in_period"])
        out_period = int(row["out_period"])
        net_after = int(row["net_after"])
        closing = current - net_after
        opening = closing - in_period + out_period
        value = (closing * int(row["cost_paise"]) + 500) // 1000
        out.append({
            "id": row["id"], "sku": row["sku"], "name": row["name"],
            "unit": row["unit"], "opening": opening, "in_period": in_period,
            "out_period": out_period, "closing": closing, "value": value,
            "moved": bool(in_period or out_period), "negative": closing < 0,
        })
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "items": len(out), "moved": sum(1 for r in out if r["moved"]),
            "negative": sum(1 for r in out if r["negative"]),
            "closing_value": sum(r["value"] for r in out),
        },
    }


# ---------------------------------------------------------------------------
# R-706 credit limit utilisation
# ---------------------------------------------------------------------------

def credit_limit_utilisation(conn: sqlite3.Connection, tenant,
                             as_of: str | None = None) -> dict:
    """R-706: open receivable against the customer master credit limit."""
    as_of = as_of or date.today().isoformat()
    _parse_date(as_of, "As of")
    tenant_id = _tenant_id(tenant)
    ageing = acct.receivable_ageing(conn, tenant_id, as_of)
    outstanding: dict[str, int] = {}
    for row in ageing["rows"]:
        customer_id = row.get("customer_id")
        if customer_id:
            outstanding[customer_id] = outstanding.get(customer_id, 0) + int(row["outstanding"])
    customers = conn.execute(
        """SELECT id, name, credit_days, credit_limit_paise
           FROM customer WHERE tenant_id = ? ORDER BY name""",
        (tenant_id,),
    ).fetchall()
    rows = []
    for customer in customers:
        due = outstanding.get(customer["id"], 0)
        limit = int(customer["credit_limit_paise"])
        if limit <= 0 and due <= 0:
            continue
        rows.append({
            "id": customer["id"], "name": customer["name"],
            "credit_days": int(customer["credit_days"]), "limit": limit,
            "outstanding": due, "available": limit - due if limit > 0 else None,
            "utilisation": _ratio(due, limit) if limit > 0 else None,
            "over_limit": limit > 0 and due > limit,
            "no_limit": limit <= 0,
        })
    rows.sort(key=lambda r: (-(r["utilisation"] or 0), -r["outstanding"], r["name"]))
    total_limit = sum(r["limit"] for r in rows if r["limit"] > 0)
    total_outstanding = sum(r["outstanding"] for r in rows)
    return {
        "as_of": as_of, "rows": rows,
        "totals": {
            "customers": len(rows),
            "with_limit": sum(1 for r in rows if r["limit"] > 0),
            "no_limit": sum(1 for r in rows if r["no_limit"]),
            "over_limit": sum(1 for r in rows if r["over_limit"]),
            "limit": total_limit, "outstanding": total_outstanding,
            "available": total_limit - sum(r["outstanding"] for r in rows if r["limit"] > 0),
            "utilisation": _ratio(
                sum(r["outstanding"] for r in rows if r["limit"] > 0), total_limit),
        },
    }


# ---------------------------------------------------------------------------
# R-110 trial balance exceptions
# ---------------------------------------------------------------------------

def trial_balance_exceptions(conn: sqlite3.Connection, tenant, date_from: str,
                             date_to: str) -> dict:
    """R-110: find journal entries that fail structural checks."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT e.id, e.entry_no, e.entry_date, e.narration, e.source_type,
                  e.status, COUNT(l.id) AS lines,
                  COUNT(DISTINCT l.line_no) AS distinct_lines,
                  COALESCE(SUM(l.debit_paise), 0) AS debit,
                  COALESCE(SUM(l.credit_paise), 0) AS credit
           FROM journal_entry e
           LEFT JOIN journal_line l ON l.entry_id = e.id AND l.tenant_id = e.tenant_id
           WHERE e.tenant_id = ? AND e.entry_date BETWEEN ? AND ?
           GROUP BY e.id, e.entry_no, e.entry_date, e.narration, e.source_type, e.status
           ORDER BY e.entry_date, e.entry_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = []
    for row in rows:
        debit = int(row["debit"])
        credit = int(row["credit"])
        lines = int(row["lines"])
        issues = []
        if debit != credit:
            issues.append("Debit and credit differ")
        if lines < 2:
            issues.append("Fewer than two lines")
        if debit == 0 and credit == 0:
            issues.append("Zero-value entry")
        if lines != int(row["distinct_lines"]):
            issues.append("Duplicate line number")
        if issues:
            out.append({
                "id": row["id"], "entry_no": row["entry_no"],
                "date": row["entry_date"], "narration": row["narration"],
                "source_type": row["source_type"], "status": row["status"],
                "lines": lines, "debit": debit, "credit": credit,
                "difference": debit - credit, "issues": issues,
            })
    return {
        "from": date_from, "to": date_to, "rows": out,
        "checked": len(rows), "exceptions": len(out),
    }


# ---------------------------------------------------------------------------
# R-107 opening vs closing balances
# ---------------------------------------------------------------------------

def opening_closing_balances(conn: sqlite3.Connection, tenant, date_from: str,
                             date_to: str) -> dict:
    """R-107: opening balance + period movement = closing balance per ledger."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    opening_date = _before(date_from)
    opening = {r["id"]: r for r in acct.account_balances(conn, tenant_id, opening_date)}
    closing = {r["id"]: r for r in acct.account_balances(conn, tenant_id, date_to)}
    movements = {
        r["account_id"]: {"debit": int(r["debit"] or 0), "credit": int(r["credit"] or 0)}
        for r in conn.execute(
            """SELECT l.account_id,
                      COALESCE(SUM(l.debit_paise), 0) AS debit,
                      COALESCE(SUM(l.credit_paise), 0) AS credit
               FROM journal_line l
               JOIN journal_entry e ON e.id = l.entry_id AND e.tenant_id = l.tenant_id
               WHERE l.tenant_id = ? AND e.entry_date BETWEEN ? AND ?
               GROUP BY l.account_id""",
            (tenant_id, date_from, date_to),
        ).fetchall()
    }
    out = []
    for account_id, row in closing.items():
        op = opening.get(account_id)
        opening_balance = int(op["balance"]) if op else 0
        move = movements.get(account_id, {"debit": 0, "credit": 0})
        movement = move["debit"] - move["credit"]
        closing_balance = int(row["balance"])
        if not any((opening_balance, move["debit"], move["credit"], closing_balance)):
            continue
        out.append({
            "id": account_id, "code": row["code"], "name": row["name"],
            "type": row["type"], "group": row["group_label"],
            "opening": opening_balance, "debit": move["debit"],
            "credit": move["credit"], "movement": movement,
            "closing": closing_balance,
            "reconciled": opening_balance + movement == closing_balance,
        })
    return {
        "from": date_from, "to": date_to, "opening_date": opening_date,
        "rows": out,
        "totals": {
            "accounts": len(out),
            "opening_debit": sum(r["opening"] for r in out if r["opening"] > 0),
            "opening_credit": -sum(r["opening"] for r in out if r["opening"] < 0),
            "debit": sum(r["debit"] for r in out),
            "credit": sum(r["credit"] for r in out),
            "closing_debit": sum(r["closing"] for r in out if r["closing"] > 0),
            "closing_credit": -sum(r["closing"] for r in out if r["closing"] < 0),
            "reconciled": all(r["reconciled"] for r in out),
        },
    }


# ---------------------------------------------------------------------------
# R-205 locked periods
# ---------------------------------------------------------------------------

def draft_entries(conn: sqlite3.Connection, tenant, as_of: str | None = None) -> dict:
    """R-204: unposted draft sales invoices and their age."""
    tenant_id = _tenant_id(tenant)
    as_of_date = _parse_date(as_of or date.today().isoformat(), "As of")
    rows = conn.execute(
        """SELECT i.id, i.invoice_no, i.invoice_date, i.sub_total_paise, i.tax_paise,
                  i.total_paise, i.created_at, c.name AS customer
           FROM invoice i JOIN customer c ON c.id = i.customer_id
           WHERE i.tenant_id = ? AND i.status = 'draft'
           ORDER BY i.invoice_date, i.invoice_no""",
        (tenant_id,),
    ).fetchall()
    out = []
    buckets = {"0-7": 0, "8-30": 0, "31-60": 0, "60+": 0}
    for row in rows:
        age_days = max(0, (as_of_date - date.fromisoformat(row["invoice_date"])).days)
        if age_days <= 7:
            bucket = "0-7"
        elif age_days <= 30:
            bucket = "8-30"
        elif age_days <= 60:
            bucket = "31-60"
        else:
            bucket = "60+"
        buckets[bucket] += 1
        out.append({
            "id": row["id"], "invoice_no": row["invoice_no"],
            "invoice_date": row["invoice_date"], "customer": row["customer"],
            "sub_total": int(row["sub_total_paise"]), "tax": int(row["tax_paise"]),
            "total": int(row["total_paise"]), "created_at": row["created_at"],
            "age_days": age_days, "bucket": bucket,
        })
    return {
        "as_of": as_of_date.isoformat(), "rows": out,
        "totals": {
            "drafts": len(out),
            "value": sum(r["total"] for r in out),
            "oldest_days": max((r["age_days"] for r in out), default=0),
            "over_30": sum(1 for r in out if r["age_days"] > 30),
            "buckets": buckets,
        },
        "method": "Reads invoice rows with status='draft'. Drafts have no journal entry, "
                  "no stock movement and no tax-invoice number until posted. This build has "
                  "no draft journal-entry workflow, so the report covers draft sales invoices only.",
    }


def locked_periods(conn: sqlite3.Connection, tenant) -> dict:
    """R-205: periods whose postings are blocked, with the locking actor."""
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT p.period_start, p.period_end, p.locked_at, p.locked_by,
                  COALESCE(u.full_name, 'Unknown') AS locked_by_name
           FROM period_lock p
           LEFT JOIN user u ON u.id = p.locked_by
           WHERE p.tenant_id = ?
           ORDER BY p.period_start, p.period_end""",
        (tenant_id,),
    ).fetchall()
    return {
        "rows": [dict(r) for r in rows],
        "totals": {"periods": len(rows)},
    }


# ---------------------------------------------------------------------------
# R-308 salesperson performance
# ---------------------------------------------------------------------------

def salesperson_performance(conn: sqlite3.Connection, tenant, date_from: str,
                            date_to: str) -> dict:
    """R-308: posted invoice revenue and receipt collections grouped by creator."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    revenue_rows = conn.execute(
        """SELECT COALESCE(e.created_by, '') AS user_id,
                  COALESCE(u.full_name, 'Unassigned') AS name,
                  COUNT(DISTINCT i.id) AS invoices,
                  COALESCE(SUM(i.sub_total_paise), 0) AS taxable,
                  COALESCE(SUM(i.total_paise), 0) AS total
           FROM invoice i
           JOIN journal_entry e ON e.id = i.journal_entry_id
           LEFT JOIN user u ON u.id = e.created_by
           WHERE i.tenant_id = ? AND i.status = 'posted'
             AND i.invoice_date BETWEEN ? AND ?
           GROUP BY e.created_by, u.full_name""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    collection_rows = conn.execute(
        """SELECT COALESCE(e.created_by, '') AS user_id,
                  COALESCE(u.full_name, 'Unassigned') AS name,
                  COUNT(DISTINCT p.id) AS receipts,
                  COALESCE(SUM(p.amount_paise), 0) AS collected
           FROM payment p
           JOIN journal_entry e ON e.id = p.journal_entry_id
           LEFT JOIN user u ON u.id = e.created_by
           WHERE p.tenant_id = ? AND p.direction = 'receipt'
             AND p.payment_date BETWEEN ? AND ?
           GROUP BY e.created_by, u.full_name""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    people: dict[str, dict] = {}
    for row in revenue_rows:
        key = row["user_id"] or "unassigned"
        people.setdefault(key, {"user_id": row["user_id"], "name": row["name"],
                                "invoices": 0, "taxable": 0, "total": 0,
                                "receipts": 0, "collected": 0})
        people[key].update({"name": row["name"], "invoices": int(row["invoices"]),
                            "taxable": int(row["taxable"]), "total": int(row["total"])})
    for row in collection_rows:
        key = row["user_id"] or "unassigned"
        people.setdefault(key, {"user_id": row["user_id"], "name": row["name"],
                                "invoices": 0, "taxable": 0, "total": 0,
                                "receipts": 0, "collected": 0})
        people[key].update({"name": row["name"], "receipts": int(row["receipts"]),
                            "collected": int(row["collected"])})
    out = []
    for person in people.values():
        person["collection_rate"] = _ratio(person["collected"], person["total"])
        out.append(person)
    out.sort(key=lambda r: (-r["total"], -r["collected"], r["name"]))
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "people": len(out),
            "invoices": sum(r["invoices"] for r in out),
            "taxable": sum(r["taxable"] for r in out),
            "total": sum(r["total"] for r in out),
            "receipts": sum(r["receipts"] for r in out),
            "collected": sum(r["collected"] for r in out),
            "collection_rate": _ratio(sum(r["collected"] for r in out),
                                      sum(r["total"] for r in out)),
        },
    }


# ---------------------------------------------------------------------------
# R-405 price variance
# ---------------------------------------------------------------------------

def price_variance(conn: sqlite3.Connection, tenant, date_from: str,
                   date_to: str) -> dict:
    """R-405: latest purchase price versus the previous bill and current cost."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT l.item_id, i.sku, i.name, i.unit, i.cost_paise AS current_cost,
                  b.bill_date, b.bill_no, l.qty_milli, l.unit_price_paise
           FROM bill_line l
           JOIN bill b ON b.id = l.bill_id AND b.tenant_id = l.tenant_id
           JOIN item i ON i.id = l.item_id AND i.tenant_id = l.tenant_id
           WHERE b.tenant_id = ? AND b.status = 'posted'
             AND b.bill_date BETWEEN ? AND ? AND l.item_id IS NOT NULL
           ORDER BY l.item_id, b.bill_date, b.bill_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    by_item: dict[str, dict] = {}
    for row in rows:
        item = by_item.setdefault(row["item_id"], {
            "id": row["item_id"], "sku": row["sku"], "name": row["name"],
            "unit": row["unit"], "current_cost": int(row["current_cost"]),
            "documents": {},
        })
        doc = item["documents"].setdefault((row["bill_date"], row["bill_no"]),
                                           {"qty": 0, "value": 0})
        qty = int(row["qty_milli"])
        doc["qty"] += qty
        doc["value"] += int(row["unit_price_paise"]) * qty
    out = []
    for item in by_item.values():
        docs = []
        for (doc_date, doc_no), values in item["documents"].items():
            qty = values["qty"]
            price = (values["value"] + qty // 2) // qty if qty else 0
            docs.append({"date": doc_date, "doc_no": doc_no, "qty": qty,
                         "price": price, "value": values["value"] // 1000})
        docs.sort(key=lambda d: (d["date"], d["doc_no"]))
        latest = docs[-1]
        previous = docs[-2] if len(docs) > 1 else None
        variance = latest["price"] - previous["price"] if previous else None
        vs_cost = latest["price"] - item["current_cost"]
        out.append({
            "id": item["id"], "sku": item["sku"], "name": item["name"],
            "unit": item["unit"], "purchases": len(docs),
            "latest_date": latest["date"], "latest_doc": latest["doc_no"],
            "latest_price": latest["price"], "previous_price":
                previous["price"] if previous else None,
            "variance": variance,
            "variance_pct": _ratio(variance, previous["price"])
                if previous and previous["price"] else None,
            "current_cost": item["current_cost"], "vs_cost": vs_cost,
            "vs_cost_pct": _ratio(vs_cost, item["current_cost"])
                if item["current_cost"] else None,
            "latest_value": latest["value"],
        })
    out.sort(key=lambda r: (-abs(r["vs_cost"]), r["name"]))
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "items": len(out),
            "latest_value": sum(r["latest_value"] for r in out),
            "above_cost": sum(1 for r in out if r["vs_cost"] > 0),
            "below_cost": sum(1 for r in out if r["vs_cost"] < 0),
            "unchanged": sum(1 for r in out if r["vs_cost"] == 0),
        },
    }


# ---------------------------------------------------------------------------
# R-502 stock movement history
# ---------------------------------------------------------------------------

STOCK_MOVEMENTS_CTE = """
WITH movements AS (
    SELECT b.bill_date AS doc_date, 'Purchase bill' AS doc_type, b.bill_no AS doc_no,
           l.item_id, l.qty_milli AS qty, l.unit_price_paise AS unit_price,
           l.taxable_paise AS value, v.name AS party
    FROM bill_line l
    JOIN bill b ON b.id = l.bill_id AND b.tenant_id = l.tenant_id
    JOIN vendor v ON v.id = b.vendor_id AND v.tenant_id = b.tenant_id
    WHERE b.tenant_id = ? AND b.status = 'posted' AND l.item_id IS NOT NULL
    UNION ALL
    SELECT i.invoice_date, 'Sales invoice', i.invoice_no, l.item_id,
           -l.qty_milli, l.unit_price_paise, l.taxable_paise, c.name
    FROM invoice_line l
    JOIN invoice i ON i.id = l.invoice_id AND i.tenant_id = l.tenant_id
    JOIN customer c ON c.id = i.customer_id AND c.tenant_id = i.tenant_id
    WHERE i.tenant_id = ? AND i.status = 'posted' AND l.item_id IS NOT NULL
    UNION ALL
    SELECT n.note_date, 'Credit note', n.note_no, l.item_id,
           l.qty_milli, l.unit_price_paise, l.taxable_paise, c.name
    FROM credit_note_line l
    JOIN credit_note n ON n.id = l.credit_note_id AND n.tenant_id = l.tenant_id
    JOIN customer c ON c.id = n.customer_id AND c.tenant_id = n.tenant_id
    WHERE n.tenant_id = ? AND l.item_id IS NOT NULL
    UNION ALL
    SELECT n.note_date, 'Debit note', n.note_no, l.item_id,
           -l.qty_milli, l.unit_price_paise, l.taxable_paise, v.name
    FROM debit_note_line l
    JOIN debit_note n ON n.id = l.debit_note_id AND n.tenant_id = l.tenant_id
    JOIN vendor v ON v.id = n.vendor_id AND v.tenant_id = n.tenant_id
    WHERE n.tenant_id = ? AND l.item_id IS NOT NULL
    UNION ALL
    SELECT a.adjustment_date, 'Stock adjustment', a.adjustment_no, a.item_id,
           a.qty_milli, a.unit_cost_paise, ABS(a.value_paise), 'Manual adjustment'
    FROM stock_adjustment a
    WHERE a.tenant_id = ?
)
"""


def stock_movements(conn: sqlite3.Connection, tenant, date_from: str,
                    date_to: str) -> dict:
    """R-502: chronological posted stock movements, including manual adjustments."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        STOCK_MOVEMENTS_CTE + """
        SELECT m.doc_date, m.doc_type, m.doc_no, m.party, m.qty, m.unit_price,
               m.value, i.sku, i.name, i.unit
        FROM movements m
        JOIN item i ON i.id = m.item_id AND i.tenant_id = ?
        WHERE m.doc_date BETWEEN ? AND ? AND i.track_stock = 1
        ORDER BY m.doc_date, m.doc_type, m.doc_no, i.name""",
        (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id, tenant_id,
         date_from, date_to),
    ).fetchall()
    out = []
    for row in rows:
        qty = int(row["qty"])
        out.append({
            "date": row["doc_date"], "doc_type": row["doc_type"],
            "doc_no": row["doc_no"], "party": row["party"],
            "sku": row["sku"], "name": row["name"], "unit": row["unit"],
            "qty": qty, "in_qty": qty if qty > 0 else 0,
            "out_qty": -qty if qty < 0 else 0,
            "unit_price": int(row["unit_price"]), "value": int(row["value"]),
            "direction": "In" if qty > 0 else "Out",
        })
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "movements": len(out),
            "in_qty": sum(r["in_qty"] for r in out),
            "out_qty": sum(r["out_qty"] for r in out),
            "in_value": sum(r["value"] for r in out if r["qty"] > 0),
            "out_value": sum(r["value"] for r in out if r["qty"] < 0),
        },
    }


# ---------------------------------------------------------------------------
# R-503 inventory valuation
# ---------------------------------------------------------------------------

def _closing_stock(conn: sqlite3.Connection, tenant_id: str, as_of: str) -> dict[str, int]:
    """Closing quantity at a date from current item stock and later movements."""
    rows = conn.execute(
        """WITH movements AS (
               SELECT l.item_id, i.invoice_date AS doc_date, -l.qty_milli AS qty
               FROM invoice_line l
               JOIN invoice i ON i.id = l.invoice_id AND i.tenant_id = l.tenant_id
               WHERE i.tenant_id = ? AND i.status = 'posted' AND l.item_id IS NOT NULL
               UNION ALL
               SELECT l.item_id, b.bill_date, l.qty_milli
               FROM bill_line l
               JOIN bill b ON b.id = l.bill_id AND b.tenant_id = l.tenant_id
               WHERE b.tenant_id = ? AND b.status = 'posted' AND l.item_id IS NOT NULL
               UNION ALL
               SELECT l.item_id, n.note_date, l.qty_milli
               FROM credit_note_line l
               JOIN credit_note n ON n.id = l.credit_note_id AND n.tenant_id = l.tenant_id
               WHERE n.tenant_id = ? AND l.item_id IS NOT NULL
               UNION ALL
               SELECT l.item_id, n.note_date, -l.qty_milli
               FROM debit_note_line l
               JOIN debit_note n ON n.id = l.debit_note_id AND n.tenant_id = l.tenant_id
               WHERE n.tenant_id = ? AND l.item_id IS NOT NULL
               UNION ALL
               SELECT a.item_id, a.adjustment_date, a.qty_milli
               FROM stock_adjustment a
               WHERE a.tenant_id = ?
           )
           SELECT i.id, i.stock_milli
                  - COALESCE(SUM(CASE WHEN m.doc_date > ? THEN m.qty ELSE 0 END), 0) AS closing
           FROM item i
           LEFT JOIN movements m ON m.item_id = i.id
           WHERE i.tenant_id = ?
           GROUP BY i.id, i.stock_milli""",
        (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id, as_of, tenant_id),
    ).fetchall()
    return {row["id"]: int(row["closing"]) for row in rows}


def inventory_valuation(conn: sqlite3.Connection, tenant,
                        as_of: str | None = None) -> dict:
    """R-503: current moving weighted-average cost applied to closing quantity."""
    as_of = as_of or date.today().isoformat()
    _parse_date(as_of, "As of")
    tenant_id = _tenant_id(tenant)
    closing = _closing_stock(conn, tenant_id, as_of)
    rows = conn.execute(
        """SELECT id, sku, name, unit, stock_milli, cost_paise, track_stock
           FROM item WHERE tenant_id = ? AND track_stock = 1 ORDER BY name""",
        (tenant_id,),
    ).fetchall()
    out = []
    for row in rows:
        qty = closing.get(row["id"], int(row["stock_milli"]))
        value = (qty * int(row["cost_paise"]) + 500) // 1000
        if qty == 0 and value == 0:
            continue
        out.append({
            "id": row["id"], "sku": row["sku"], "name": row["name"],
            "unit": row["unit"], "qty": qty, "cost": int(row["cost_paise"]),
            "value": value, "negative": qty < 0,
        })
    total = sum(r["value"] for r in out)
    for row in out:
        row["share"] = _ratio(row["value"], total)
    out.sort(key=lambda r: (-r["value"], r["name"]))
    return {
        "as_of": as_of, "rows": out,
        "totals": {
            "items": len(out), "qty": sum(r["qty"] for r in out),
            "value": total, "negative": sum(1 for r in out if r["negative"]),
        },
    }


# ---------------------------------------------------------------------------
# R-504 reorder / shortage
# ---------------------------------------------------------------------------

def reorder_shortage(conn: sqlite3.Connection, tenant,
                     as_of: str | None = None) -> dict:
    """R-504: items at or below their configured reorder level, or out of stock."""
    as_of = as_of or date.today().isoformat()
    _parse_date(as_of, "As of")
    tenant_id = _tenant_id(tenant)
    closing = _closing_stock(conn, tenant_id, as_of)
    rows = conn.execute(
        """SELECT id, sku, name, unit, stock_milli, reorder_level_milli, cost_paise
           FROM item WHERE tenant_id = ? AND track_stock = 1 ORDER BY name""",
        (tenant_id,),
    ).fetchall()
    out = []
    for row in rows:
        qty = closing.get(row["id"], int(row["stock_milli"]))
        level = int(row["reorder_level_milli"])
        if qty > 0 and (level <= 0 or qty > level):
            continue
        shortage = max(0, level - qty)
        out.append({
            "id": row["id"], "sku": row["sku"], "name": row["name"],
            "unit": row["unit"], "stock": qty, "reorder_level": level,
            "shortage": shortage,
            "value": (qty * int(row["cost_paise"]) + 500) // 1000,
            "status": "Out of stock" if qty <= 0 else "Below reorder level",
            "has_level": level > 0,
        })
    out.sort(key=lambda r: (r["status"] != "Out of stock", -r["shortage"], r["name"]))
    return {
        "as_of": as_of, "rows": out,
        "totals": {
            "items": len(out),
            "out_of_stock": sum(1 for r in out if r["stock"] <= 0),
            "below_level": sum(1 for r in out if r["stock"] > 0),
            "shortage_qty": sum(r["shortage"] for r in out),
            "value": sum(r["value"] for r in out),
        },
    }


# ---------------------------------------------------------------------------
# R-505 dead / slow stock
# ---------------------------------------------------------------------------

def dead_stock(conn: sqlite3.Connection, tenant, days: int = 90,
               as_of: str | None = None) -> dict:
    """R-505: stocked items with no posted movement for the selected number of days."""
    as_of = as_of or date.today().isoformat()
    as_of_d = _parse_date(as_of, "As of")
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise ReportError("BAD_DAYS", "Days must be a whole number")
    if days < 0 or days > 3650:
        raise ReportError("BAD_DAYS", "Days must be between 0 and 3650")
    tenant_id = _tenant_id(tenant)
    closing = _closing_stock(conn, tenant_id, as_of)
    last_rows = conn.execute(
        STOCK_MOVEMENTS_CTE + """
        SELECT m.item_id, MAX(m.doc_date) AS last_date
        FROM movements m
        WHERE m.doc_date <= ?
        GROUP BY m.item_id""",
        (tenant_id, tenant_id, tenant_id, tenant_id, tenant_id, as_of),
    ).fetchall()
    last = {row["item_id"]: row["last_date"] for row in last_rows}
    rows = conn.execute(
        """SELECT id, sku, name, unit, stock_milli, cost_paise
           FROM item WHERE tenant_id = ? AND track_stock = 1 ORDER BY name""",
        (tenant_id,),
    ).fetchall()
    out = []
    for row in rows:
        qty = closing.get(row["id"], int(row["stock_milli"]))
        if qty <= 0:
            continue
        last_date = last.get(row["id"])
        age = (as_of_d - date.fromisoformat(last_date)).days if last_date else None
        if age is not None and age < days:
            continue
        out.append({
            "id": row["id"], "sku": row["sku"], "name": row["name"],
            "unit": row["unit"], "stock": qty, "last_date": last_date,
            "age_days": age,
            "value": (qty * int(row["cost_paise"]) + 500) // 1000,
            "never_moved": last_date is None,
        })
    out.sort(key=lambda r: (-(r["age_days"] if r["age_days"] is not None else 999999),
                            r["name"]))
    return {
        "as_of": as_of, "days": days, "rows": out,
        "totals": {
            "items": len(out),
            "never_moved": sum(1 for r in out if r["never_moved"]),
            "value": sum(r["value"] for r in out),
        },
    }


# ---------------------------------------------------------------------------
# R-506 stock adjustment register
# ---------------------------------------------------------------------------

def stock_adjustment_register(conn: sqlite3.Connection, tenant,
                              date_from: str, date_to: str) -> dict:
    """R-506: chronological manual stock adjustments with value and reason.

    Each row is a posted adjustment. Quantity is signed (positive increases,
    negative decreases). The unit cost is the item's current moving
    weighted-average cost at the time of the adjustment; the register does not
    recalculate historical cost layers.
    """
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT a.*, i.sku, i.name, i.unit,
                  i.stock_milli AS current_stock, i.cost_paise AS current_cost,
                  e.entry_no, u.full_name AS created_by_name
           FROM stock_adjustment a
           JOIN item i ON i.id = a.item_id AND i.tenant_id = a.tenant_id
           LEFT JOIN journal_entry e ON e.id = a.journal_entry_id
           LEFT JOIN user u ON u.id = a.created_by
           WHERE a.tenant_id = ? AND a.adjustment_date BETWEEN ? AND ?
           ORDER BY a.adjustment_date, a.adjustment_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = []
    for row in rows:
        qty = int(row["qty_milli"])
        value = int(row["value_paise"])
        out.append({
            "id": row["id"], "item_id": row["item_id"],
            "adjustment_no": row["adjustment_no"],
            "date": row["adjustment_date"], "sku": row["sku"],
            "name": row["name"], "unit": row["unit"],
            "direction": "Increase" if qty > 0 else "Decrease",
            "qty": abs(qty), "signed_qty": qty,
            "unit_cost": int(row["unit_cost_paise"]),
            "value": value, "abs_value": abs(value),
            "reason": row["reason"], "note": row["note"],
            "entry_no": row["entry_no"] or "",
            "created_by_name": row["created_by_name"] or "",
            "created_at": row["created_at"],
            "current_stock": int(row["current_stock"]),
            "current_cost": int(row["current_cost"]),
        })
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "adjustments": len(out),
            "items": len({r["item_id"] for r in out}),
            "increase_qty": sum(r["qty"] for r in out if r["signed_qty"] > 0),
            "decrease_qty": sum(r["qty"] for r in out if r["signed_qty"] < 0),
            "increase_value": sum(r["value"] for r in out if r["value"] > 0),
            "decrease_value": sum(-r["value"] for r in out if r["value"] < 0),
            "net_qty": sum(r["signed_qty"] for r in out),
            "net_value": sum(r["value"] for r in out),
        },
        "method": (
            "Quantity increases are posted Dr Inventory / Cr Stock Adjustments; "
            "decreases are posted Dr Stock Adjustments / Cr Inventory. Values use "
            "the current moving weighted-average item cost and never rewrite a "
            "historical cost layer."
        ),
    }


# ---------------------------------------------------------------------------
# R-507 inventory to GL reconciliation
# ---------------------------------------------------------------------------

def inventory_gl_reconciliation(conn: sqlite3.Connection, tenant,
                                as_of: str | None = None) -> dict:
    """R-507: item-master stock value versus the inventory ledger balance."""
    as_of = as_of or date.today().isoformat()
    _parse_date(as_of, "As of")
    tenant_id = _tenant_id(tenant)
    valuation = inventory_valuation(conn, tenant, as_of)
    gl_balance = _balance(conn, tenant_id, ("inventory",), as_of)
    gl_rows = conn.execute(
        """SELECT a.code, a.name,
                  COALESCE(SUM(l.debit_paise - l.credit_paise), 0) AS balance
           FROM account a
           LEFT JOIN journal_line l
             ON l.account_id = a.id AND l.tenant_id = a.tenant_id
           LEFT JOIN journal_entry e
             ON e.id = l.entry_id AND e.entry_date <= ?
           WHERE a.tenant_id = ? AND a.group_code = 'inventory'
           GROUP BY a.id, a.code, a.name ORDER BY a.code""",
        (as_of, tenant_id),
    ).fetchall()
    stock_value = valuation["totals"]["value"]
    difference = stock_value - gl_balance
    return {
        "as_of": as_of, "rows": valuation["rows"],
        "gl_accounts": [dict(r) for r in gl_rows],
        "totals": {
            "items": valuation["totals"]["items"],
            "stock_value": stock_value,
            "gl_balance": gl_balance,
            "difference": difference,
            "reconciled": difference == 0,
        },
    }


# ---------------------------------------------------------------------------
# R-704 receivables risk
# ---------------------------------------------------------------------------

def receivables_risk(conn: sqlite3.Connection, tenant,
                     as_of: str | None = None, prior_days: int = 30) -> dict:
    """R-704: overdue exposure, credit utilisation and the prior-period trend."""
    as_of = as_of or date.today().isoformat()
    as_of_d = _parse_date(as_of, "As of")
    try:
        prior_days = int(prior_days)
    except (TypeError, ValueError):
        raise ReportError("BAD_DAYS", "Prior days must be a whole number")
    if prior_days < 1 or prior_days > 3650:
        raise ReportError("BAD_DAYS", "Prior days must be between 1 and 3650")
    tenant_id = _tenant_id(tenant)
    prior_as_of = (as_of_d - timedelta(days=prior_days)).isoformat()
    current = acct.receivable_ageing(conn, tenant_id, as_of)
    prior = acct.receivable_ageing(conn, tenant_id, prior_as_of)
    customers = {
        row["id"]: row for row in conn.execute(
            """SELECT id, name, credit_days, credit_limit_paise
               FROM customer WHERE tenant_id = ?""",
            (tenant_id,),
        ).fetchall()
    }

    def summarise(ageing):
        result: dict[str, dict] = {}
        for row in ageing["rows"]:
            cid = row.get("customer_id")
            if not cid:
                continue
            customer = customers.get(cid)
            credit_days = int(customer["credit_days"]) if customer else 0
            entry = result.setdefault(cid, {
                "outstanding": 0, "overdue": 0, "current": 0,
                "oldest_days": 0, "invoices": 0,
            })
            amount = int(row["outstanding"])
            entry["outstanding"] += amount
            entry["invoices"] += 1
            entry["oldest_days"] = max(entry["oldest_days"], int(row["days"]))
            if int(row["days"]) > credit_days:
                entry["overdue"] += amount
            else:
                entry["current"] += amount
        return result

    current_by_customer = summarise(current)
    prior_by_customer = summarise(prior)
    out = []
    for cid, entry in current_by_customer.items():
        customer = customers.get(cid)
        if not customer:
            continue
        limit = int(customer["credit_limit_paise"])
        utilisation = _ratio(entry["outstanding"], limit) if limit > 0 else None
        over_limit = limit > 0 and entry["outstanding"] > limit
        prior_overdue = prior_by_customer.get(cid, {}).get("overdue", 0)
        if over_limit or (entry["overdue"] > 0 and entry["oldest_days"] > 90):
            risk = "High"
        elif entry["overdue"] > 0 or (utilisation is not None and utilisation >= 0.8):
            risk = "Medium"
        else:
            risk = "Low"
        out.append({
            "id": cid, "name": customer["name"],
            "credit_days": int(customer["credit_days"]), "limit": limit,
            "outstanding": entry["outstanding"], "overdue": entry["overdue"],
            "current": entry["current"], "oldest_days": entry["oldest_days"],
            "invoices": entry["invoices"], "utilisation": utilisation,
            "over_limit": over_limit, "prior_overdue": prior_overdue,
            "overdue_change": entry["overdue"] - prior_overdue,
            "risk": risk,
        })
    rank = {"High": 0, "Medium": 1, "Low": 2}
    out.sort(key=lambda r: (rank[r["risk"]], -r["overdue"], -r["outstanding"], r["name"]))
    return {
        "as_of": as_of, "prior_as_of": prior_as_of, "rows": out,
        "totals": {
            "customers": len(out),
            "outstanding": sum(r["outstanding"] for r in out),
            "overdue": sum(r["overdue"] for r in out),
            "current": sum(r["current"] for r in out),
            "over_limit": sum(1 for r in out if r["over_limit"]),
            "high_risk": sum(1 for r in out if r["risk"] == "High"),
            "prior_overdue": sum(r["prior_overdue"] for r in out),
            "overdue_change": sum(r["overdue_change"] for r in out),
        },
    }



# ---------------------------------------------------------------------------
# R-705 cash flow forecast
# ---------------------------------------------------------------------------

def cash_flow_forecast(conn: sqlite3.Connection, tenant, as_of: str | None = None,
                       horizon_days: int = 90) -> dict:
    """R-705: deterministic collection/payment forecast from open documents.

    This is a forecast, not an actual. Overdue receivables are assumed to arrive
    in the first bucket; overdue payables are assumed to leave in the first bucket.
    Items not yet due are placed in the week containing their due date.
    """
    as_of = as_of or date.today().isoformat()
    as_of_d = _parse_date(as_of, "As of")
    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError):
        raise ReportError("BAD_HORIZON", "Horizon days must be a whole number")
    if horizon_days < 7 or horizon_days > 365:
        raise ReportError("BAD_HORIZON", "Horizon days must be between 7 and 365")
    tenant_id = _tenant_id(tenant)
    weeks = (horizon_days + 6) // 7
    buckets = [{"week": i + 1, "start_day": i * 7,
                "end_day": min(horizon_days, (i + 1) * 7 - 1),
                "inflow": 0, "outflow": 0} for i in range(weeks)]

    def place(amount: int, planned: date, key: str) -> bool:
        index = max(0, (planned - as_of_d).days) // 7
        if index >= weeks:
            return False
        buckets[index][key] += amount
        return True

    opening = _cash_balance(conn, tenant_id, as_of)
    open_receivables = 0
    open_payables = 0
    overdue_receivables = 0
    overdue_payables = 0
    beyond_in = 0
    beyond_out = 0
    invoices = conn.execute(
        """SELECT i.id, i.invoice_no, i.invoice_date, c.name AS party,
                  c.credit_days
           FROM invoice i JOIN customer c ON c.id = i.customer_id
           WHERE i.tenant_id = ? AND i.status = 'posted' AND i.invoice_date <= ?
           ORDER BY i.invoice_date""",
        (tenant_id, as_of),
    ).fetchall()
    for row in invoices:
        outstanding = acct.invoice_outstanding(conn, tenant_id, row["id"])
        if outstanding <= 0:
            continue
        open_receivables += outstanding
        due = date.fromisoformat(row["invoice_date"]) + timedelta(days=int(row["credit_days"]))
        if due < as_of_d:
            overdue_receivables += outstanding
            planned = as_of_d
        else:
            planned = due
        if not place(outstanding, planned, "inflow"):
            beyond_in += outstanding
    bills = conn.execute(
        """SELECT b.id, b.bill_no, b.bill_date, v.name AS party,
                  v.credit_days
           FROM bill b JOIN vendor v ON v.id = b.vendor_id
           WHERE b.tenant_id = ? AND b.status = 'posted' AND b.bill_date <= ?
           ORDER BY b.bill_date""",
        (tenant_id, as_of),
    ).fetchall()
    for row in bills:
        outstanding = acct.bill_outstanding(conn, tenant_id, row["id"])
        if outstanding <= 0:
            continue
        open_payables += outstanding
        due = date.fromisoformat(row["bill_date"]) + timedelta(days=int(row["credit_days"]))
        if due < as_of_d:
            overdue_payables += outstanding
            planned = as_of_d
        else:
            planned = due
        if not place(outstanding, planned, "outflow"):
            beyond_out += outstanding

    running = opening
    rows = []
    for bucket in buckets:
        net = bucket["inflow"] - bucket["outflow"]
        running += net
        rows.append({**bucket, "net": net, "closing": running})
    return {
        "as_of": as_of, "horizon_days": horizon_days,
        "opening_cash": opening, "closing_cash": running,
        "open_receivables": open_receivables, "open_payables": open_payables,
        "overdue_receivables": overdue_receivables,
        "overdue_payables": overdue_payables,
        "scheduled_inflow": sum(b["inflow"] for b in buckets),
        "scheduled_outflow": sum(b["outflow"] for b in buckets),
        "beyond_inflow": beyond_in, "beyond_outflow": beyond_out,
        "rows": rows,
        "method": "Overdue items are assumed in week 1; not-yet-due items are placed in "
                  "the week containing their due date. No new sales or purchases are assumed.",
    }


# ---------------------------------------------------------------------------
# R-807 tax ledger
# ---------------------------------------------------------------------------

def tax_ledger(conn: sqlite3.Connection, tenant, date_from: str,
               date_to: str) -> dict:
    """R-807: movement on output-tax and input-credit ledgers."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    accounts = conn.execute(
        """SELECT id, code, name, group_code, type
           FROM account
           WHERE tenant_id = ? AND group_code IN ('duties_taxes', 'gst_input')
           ORDER BY code""",
        (tenant_id,),
    ).fetchall()
    movements = {
        row["account_id"]: {"debit": int(row["debit"] or 0),
                            "credit": int(row["credit"] or 0)}
        for row in conn.execute(
            """SELECT l.account_id,
                      COALESCE(SUM(l.debit_paise), 0) AS debit,
                      COALESCE(SUM(l.credit_paise), 0) AS credit
               FROM journal_line l
               JOIN journal_entry e ON e.id = l.entry_id AND e.tenant_id = l.tenant_id
               WHERE l.tenant_id = ? AND e.entry_date BETWEEN ? AND ?
               GROUP BY l.account_id""",
            (tenant_id, date_from, date_to),
        ).fetchall()
    }
    rows = []
    for account in accounts:
        opening = acct.account_balance(conn, tenant_id, account["id"], _before(date_from))
        move = movements.get(account["id"], {"debit": 0, "credit": 0})
        closing = opening + move["debit"] - move["credit"]
        if not any((opening, move["debit"], move["credit"], closing)):
            continue
        kind = "Output tax" if account["group_code"] == "duties_taxes" else "Input credit"
        rows.append({
            "code": account["code"], "name": account["name"], "kind": kind,
            "group": account["group_code"], "opening": opening,
            "debit": move["debit"], "credit": move["credit"], "closing": closing,
        })
    output_payable = sum(-r["closing"] for r in rows if r["group"] == "duties_taxes")
    input_credit = sum(r["closing"] for r in rows if r["group"] == "gst_input")
    return {
        "from": date_from, "to": date_to, "rows": rows,
        "totals": {
            "accounts": len(rows),
            "debit": sum(r["debit"] for r in rows),
            "credit": sum(r["credit"] for r in rows),
            "output_payable": output_payable,
            "input_credit": input_credit,
            "net_payable": output_payable - input_credit,
        },
    }


# ---------------------------------------------------------------------------
# R-904 KPI dashboard pack
# ---------------------------------------------------------------------------

def kpi_dashboard(conn: sqlite3.Connection, tenant, date_from: str,
                  date_to: str) -> dict:
    """R-904: one actual-only KPI pack assembled from existing deterministic reports."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    pnl = acct.profit_and_loss(conn, tenant_id, date_from, date_to)
    bs = acct.balance_sheet(conn, tenant_id, date_to)
    ratios = financial_ratios(conn, tenant, date_from, date_to)
    cash = cash_flow(conn, tenant, date_from, date_to)
    wc = working_capital(conn, tenant, date_from, date_to)
    ar = acct.receivable_ageing(conn, tenant_id, date_to)
    ap = acct.payable_ageing(conn, tenant_id, date_to)
    valuation = inventory_valuation(conn, tenant, date_to)
    ratio_map = {r["key"]: r for r in ratios["rows"]}
    monthly = sales_summary_by_period(conn, tenant, date_from, date_to)
    growth = None
    if len(monthly["rows"]) >= 2:
        last = monthly["rows"][-1]
        prev = monthly["rows"][-2]
        growth = _ratio(last["taxable"] - prev["taxable"], prev["taxable"])

    def kpi(label, value, kind, formula, source):
        return {"label": label, "value": value, "kind": kind,
                "formula": formula, "source": source, "actual": True}

    kpis = [
        kpi("Revenue", pnl["total_income"], "money", "posted income", "P&L"),
        kpi("Net profit", pnl["net_profit"], "money", "income - expenses", "P&L"),
        kpi("Cash and bank", cash["closing"], "money", "posted cash/bank balance", "cash flow"),
        kpi("Receivables", ar["grand_total"], "money", "open posted invoices", "ageing"),
        kpi("Payables", ap["grand_total"], "money", "open posted bills", "ageing"),
        kpi("Inventory value", valuation["totals"]["value"], "money",
            "closing quantity x current cost", "inventory valuation"),
        kpi("Gross margin", ratio_map["gross_margin"]["value"], "percent",
            ratio_map["gross_margin"]["formula"], "ratios"),
        kpi("Net margin", ratio_map["net_margin"]["value"], "percent",
            ratio_map["net_margin"]["formula"], "ratios"),
        kpi("Current ratio", ratio_map["current_ratio"]["value"], "ratio",
            ratio_map["current_ratio"]["formula"], "ratios"),
        kpi("DSO", wc["dso"], "days", "receivable days", "working capital"),
        kpi("DIO", wc["dio"], "days", "inventory days", "working capital"),
        kpi("DPO", wc["dpo"], "days", "payable days", "working capital"),
        kpi("Cash conversion cycle", wc["ccc"], "days", "DSO + DIO - DPO", "working capital"),
        kpi("Revenue growth", growth, "percent", "latest month vs previous month", "sales summary"),
    ]
    return {
        "from": date_from, "to": date_to, "kpis": kpis,
        "checks": {
            "balance_sheet_balanced": bs["balanced"],
            "balance_sheet_difference": bs["difference"],
            "cash_flow_difference": cash["difference"],
            "working_capital_days": wc["days"],
        },
    }


# ---------------------------------------------------------------------------
# R-1001 trend explanation
# ---------------------------------------------------------------------------

def _months_between(date_from: str, date_to: str, limit: int = 12) -> list[str]:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month) and len(months) < limit:
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return months


def _inr(paise: int) -> str:
    return f"Rs {paise / 100:,.2f}"


def trend_explanation(conn: sqlite3.Connection, tenant, date_from: str,
                      date_to: str) -> dict:
    """R-1001: deterministic narrative over monthly posted revenue and expenses."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    months = _months_between(date_from, date_to)
    revenue = {
        row["period"]: int(row["taxable"])
        for row in conn.execute(
            """SELECT substr(invoice_date, 1, 7) AS period,
                      COALESCE(SUM(sub_total_paise), 0) AS taxable
               FROM invoice
               WHERE tenant_id = ? AND status = 'posted'
                 AND invoice_date BETWEEN ? AND ?
               GROUP BY period""",
            (tenant_id, date_from, date_to),
        ).fetchall()
    }
    expenses = {
        row["period"]: int(row["amount"])
        for row in conn.execute(
            """SELECT substr(e.entry_date, 1, 7) AS period,
                      COALESCE(SUM(l.debit_paise - l.credit_paise), 0) AS amount
               FROM journal_line l
               JOIN journal_entry e ON e.id = l.entry_id AND e.tenant_id = l.tenant_id
               JOIN account a ON a.id = l.account_id AND a.tenant_id = l.tenant_id
               WHERE l.tenant_id = ? AND a.type = 'expense'
                 AND e.entry_date BETWEEN ? AND ?
               GROUP BY period""",
            (tenant_id, date_from, date_to),
        ).fetchall()
    }
    rows = []
    for month in months:
        rev = revenue.get(month, 0)
        exp = expenses.get(month, 0)
        rows.append({"period": month, "revenue": rev, "expenses": exp,
                     "net": rev - exp})
    narrative = []
    if len(rows) >= 2:
        first_rev = next((r for r in rows if r["revenue"]), rows[0])
        last_rev = next((r for r in reversed(rows) if r["revenue"]), rows[-1])
        first_exp = next((r for r in rows if r["expenses"]), rows[0])
        last_exp = next((r for r in reversed(rows) if r["expenses"]), rows[-1])
        rev_change = last_rev["revenue"] - first_rev["revenue"]
        exp_change = last_exp["expenses"] - first_exp["expenses"]
        rev_pct = _ratio(rev_change, first_rev["revenue"])
        exp_pct = _ratio(exp_change, first_exp["expenses"])
        narrative.append(
            f"Revenue moved from {_inr(first_rev['revenue'])} in {first_rev['period']} to "
            f"{_inr(last_rev['revenue'])} in {last_rev['period']} "
            f"({_signed_pct(rev_pct)}).")
        narrative.append(
            f"Expenses moved from {_inr(first_exp['expenses'])} in {first_exp['period']} to "
            f"{_inr(last_exp['expenses'])} in {last_exp['period']} "
            f"({_signed_pct(exp_pct)}).")
        revenue_moves = [(rows[i]["revenue"] - rows[i - 1]["revenue"], rows[i]["period"])
                         for i in range(1, len(rows))]
        expense_moves = [(rows[i]["expenses"] - rows[i - 1]["expenses"], rows[i]["period"])
                         for i in range(1, len(rows))]
        if revenue_moves:
            amount, month = max(revenue_moves)
            narrative.append(
                f"The largest month-on-month revenue change was {_inr(amount)} in {month}.")
        if expense_moves:
            amount, month = max(expense_moves)
            narrative.append(
                f"The largest month-on-month expense change was {_inr(amount)} in {month}.")
    else:
        narrative.append("Not enough monthly actuals to explain a trend.")
    return {
        "from": date_from, "to": date_to, "rows": rows, "narrative": narrative,
        "method": "Actual posted invoices and expense-account journal lines, grouped by month. "
                  "No estimate or forecast is included.",
    }


def _signed_pct(value) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.2f}%"


# ---------------------------------------------------------------------------
# R-1002 revenue forecast
# ---------------------------------------------------------------------------

def _next_month(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    month += 1
    if month == 13:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}"


def revenue_forecast(conn: sqlite3.Connection, tenant, date_from: str,
                     date_to: str, periods: int = 3) -> dict:
    """R-1002: transparent linear forecast from monthly actual net revenue."""
    _validate_period(date_from, date_to)
    try:
        periods = int(periods)
    except (TypeError, ValueError):
        raise ReportError("BAD_PERIODS", "Forecast periods must be a whole number")
    if periods < 1 or periods > 12:
        raise ReportError("BAD_PERIODS", "Forecast periods must be between 1 and 12")
    tenant_id = _tenant_id(tenant)
    months = _months_between(date_from, date_to)
    revenue = {
        row["period"]: int(row["taxable"])
        for row in conn.execute(
            """SELECT substr(invoice_date, 1, 7) AS period,
                      COALESCE(SUM(sub_total_paise), 0) AS taxable
               FROM invoice
               WHERE tenant_id = ? AND status = 'posted'
                 AND invoice_date BETWEEN ? AND ?
               GROUP BY period""",
            (tenant_id, date_from, date_to),
        ).fetchall()
    }
    actuals = [{"period": m, "revenue": revenue.get(m, 0), "actual": True}
               for m in months]
    if not actuals:
        return {"from": date_from, "to": date_to, "actuals": [],
                "forecast": [], "method": "No actual months in the selected period.",
                "confidence": "none", "slope": 0, "intercept": 0,
                "r_squared": None, "residual_std": None}
    values = [row["revenue"] for row in actuals]
    n = len(values)
    if n >= 3:
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        denom = sum((i - x_mean) ** 2 for i in range(n))
        slope = sum((i - x_mean) * (values[i] - y_mean) for i in range(n)) / denom
        intercept = y_mean - slope * x_mean
        fitted = [intercept + slope * i for i in range(n)]
        residuals = [values[i] - fitted[i] for i in range(n)]
        residual_std = (sum(r * r for r in residuals) / max(1, n - 2)) ** 0.5
        total = sum((v - y_mean) ** 2 for v in values)
        r_squared = 1 - (sum(r * r for r in residuals) / total) if total else None
        confidence = "medium" if n >= 6 else "low"
    else:
        slope = 0
        intercept = sum(values) / n
        residual_std = (sum((v - intercept) ** 2 for v in values) / n) ** 0.5
        r_squared = None
        confidence = "low"
    forecast = []
    last_period = actuals[-1]["period"]
    for step in range(1, periods + 1):
        period = _next_month(last_period)
        for _ in range(step - 1):
            period = _next_month(period)
        value = intercept + slope * (n - 1 + step)
        value = max(0, int(round(value)))
        band = int(round(1.96 * (residual_std or 0)))
        forecast.append({
            "period": period, "revenue": value, "actual": False,
            "lower": max(0, value - band), "upper": value + band,
        })
    return {
        "from": date_from, "to": date_to, "actuals": actuals, "forecast": forecast,
        "method": "Ordinary least-squares line through monthly actual net revenue. "
                  "The band is +/- 1.96 residual standard errors and is indicative only.",
        "confidence": confidence, "slope": slope, "intercept": intercept,
        "r_squared": r_squared, "residual_std": residual_std,
    }


# ---------------------------------------------------------------------------
# R-1003 anomaly digest
# ---------------------------------------------------------------------------

def anomaly_digest(conn: sqlite3.Connection, tenant, date_from: str,
                   date_to: str) -> dict:
    """R-1003: rule-based review prompts, never a fraud finding."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = []

    exceptions = trial_balance_exceptions(conn, tenant, date_from, date_to)
    for row in exceptions["rows"][:10]:
        rows.append({
            "kind": "Journal structure", "severity": "High",
            "date": row["date"], "reference": row["entry_no"],
            "description": ", ".join(row["issues"]), "amount": row["difference"],
        })

    entries = conn.execute(
        """SELECT e.id, e.entry_no, e.entry_date, e.narration,
                  COALESCE(SUM(l.debit_paise), 0) AS total
           FROM journal_entry e
           LEFT JOIN journal_line l ON l.entry_id = e.id AND l.tenant_id = e.tenant_id
           WHERE e.tenant_id = ? AND e.entry_date BETWEEN ? AND ?
           GROUP BY e.id
           HAVING total > 0
           ORDER BY total DESC""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    if entries:
        totals = [int(e["total"]) for e in entries]
        mean = sum(totals) / len(totals)
        variance = sum((t - mean) ** 2 for t in totals) / len(totals)
        std = variance ** 0.5
        threshold = mean + 2 * std
        for entry in entries:
            total = int(entry["total"])
            if total <= threshold or total < 100000:
                continue
            rows.append({
                "kind": "Large journal", "severity": "Medium",
                "date": entry["entry_date"], "reference": entry["entry_no"],
                "description": f"Entry value is above the two-standard-deviation review line "
                               f"({_inr(int(threshold))}).",
                "amount": total,
            })
            if sum(1 for r in rows if r["kind"] == "Large journal") >= 10:
                break

    duplicates = conn.execute(
        """SELECT i.invoice_date, i.total_paise, c.name AS customer,
                  COUNT(*) AS n, GROUP_CONCAT(i.invoice_no) AS refs
           FROM invoice i JOIN customer c ON c.id = i.customer_id
           WHERE i.tenant_id = ? AND i.status = 'posted'
             AND i.invoice_date BETWEEN ? AND ?
           GROUP BY i.customer_id, i.invoice_date, i.total_paise
           HAVING n > 1
           ORDER BY i.invoice_date DESC""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    for row in duplicates[:10]:
        rows.append({
            "kind": "Possible duplicate invoice", "severity": "Medium",
            "date": row["invoice_date"], "reference": row["refs"],
            "description": f"{row['n']} posted invoices for {row['customer']} share the "
                           f"same date and total.",
            "amount": int(row["total_paise"]),
        })

    backdated = conn.execute(
        """SELECT entry_no, entry_date, posted_at, narration
           FROM journal_entry
           WHERE tenant_id = ? AND entry_date BETWEEN ? AND ?
           ORDER BY entry_date""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    for row in backdated:
        try:
            created = date.fromisoformat(str(row["posted_at"])[:10])
            entry_date = date.fromisoformat(row["entry_date"])
        except ValueError:
            continue
        if (created - entry_date).days > 7:
            rows.append({
                "kind": "Backdated entry", "severity": "Low",
                "date": row["entry_date"], "reference": row["entry_no"],
                "description": f"Created {created.isoformat()}, more than 7 days after the "
                               f"entry date. Narration: {row['narration'][:80]}",
                "amount": 0,
            })
            if sum(1 for r in rows if r["kind"] == "Backdated entry") >= 10:
                break

    negative = conn.execute(
        """SELECT sku, name, stock_milli FROM item
           WHERE tenant_id = ? AND track_stock = 1 AND stock_milli < 0
           ORDER BY stock_milli LIMIT 10""",
        (tenant_id,),
    ).fetchall()
    for row in negative:
        rows.append({
            "kind": "Negative stock", "severity": "High", "date": date_to,
            "reference": row["sku"],
            "description": f"{row['name']} has negative stock "
                           f"({row['stock_milli'] / 1000:.3f}).",
            "amount": 0,
        })

    ageing = acct.receivable_ageing(conn, tenant_id, date_to)
    for row in ageing["rows"]:
        if int(row["days"]) > 90 and int(row["outstanding"]) > 0:
            rows.append({
                "kind": "Overdue receivable", "severity": "Medium",
                "date": row["date"], "reference": row["invoice_no"],
                "description": f"{row['customer']} is {row['days']} days old with "
                               f"{_inr(int(row['outstanding']))} outstanding.",
                "amount": int(row["outstanding"]),
            })
            if sum(1 for r in rows if r["kind"] == "Overdue receivable") >= 10:
                break

    rank = {"High": 0, "Medium": 1, "Low": 2}
    rows.sort(key=lambda r: (rank[r["severity"]], r["date"], r["reference"]))
    return {
        "from": date_from, "to": date_to, "rows": rows,
        "totals": {
            "findings": len(rows),
            "high": sum(1 for r in rows if r["severity"] == "High"),
            "medium": sum(1 for r in rows if r["severity"] == "Medium"),
            "low": sum(1 for r in rows if r["severity"] == "Low"),
        },
        "method": "Deterministic review rules over posted rows: journal structure, large entries, "
                  "same-date/same-total invoices, backdating, negative stock and 90+ day receivables. "
                  "These are review prompts, not fraud findings.",
    }


# ---------------------------------------------------------------------------
# R-206 rule version usage
# ---------------------------------------------------------------------------

def rule_version_usage(conn: sqlite3.Connection, tenant, date_from: str,
                       date_to: str) -> dict:
    """R-206: which posting-rule version created the posted entries."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT e.rule_version,
                  COUNT(DISTINCT e.id) AS entries,
                  COALESCE(SUM(l.debit_paise), 0) AS debit,
                  COALESCE(SUM(l.credit_paise), 0) AS credit,
                  MIN(e.entry_date) AS first_date,
                  MAX(e.entry_date) AS last_date,
                  COUNT(DISTINCT e.source_type) AS source_types
           FROM journal_entry e
           LEFT JOIN journal_line l ON l.entry_id = e.id AND l.tenant_id = e.tenant_id
           WHERE e.tenant_id = ? AND e.entry_date BETWEEN ? AND ?
           GROUP BY e.rule_version
           ORDER BY entries DESC, e.rule_version""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out = []
    for row in rows:
        debit = int(row["debit"] or 0)
        credit = int(row["credit"] or 0)
        out.append({
            "rule_version": row["rule_version"],
            "entries": int(row["entries"]),
            "debit": debit,
            "credit": credit,
            "difference": debit - credit,
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "source_types": int(row["source_types"]),
        })
    return {
        "from": date_from, "to": date_to, "rows": out,
        "current_version": acct.RULE_VERSION,
        "totals": {
            "versions": len(out),
            "entries": sum(r["entries"] for r in out),
            "debit": sum(r["debit"] for r in out),
            "credit": sum(r["credit"] for r in out),
            "difference": sum(r["difference"] for r in out),
        },
        "method": "Groups posted journal entries by the rule_version stored at posting time. "
                  "The current posting rule is reported separately; no historical rule engine exists.",
    }


# ---------------------------------------------------------------------------
# advanced operational reports
# ---------------------------------------------------------------------------

def _dimension_pl(conn: sqlite3.Connection, tenant_id: str, date_from: str,
                  date_to: str, kinds: tuple[str, ...]) -> dict:
    """P&L contribution for dimensions, plus one explicit unallocated row.

    Only journal lines tagged with a dimension of the requested kinds count as
    allocated. Everything else is shown as unallocated; there is no automatic
    cost allocation and no invented split.
    """
    _validate_period(date_from, date_to)
    marks = ",".join("?" for _ in kinds)
    rows = conn.execute(
        f"""SELECT d.id, d.kind, d.code, d.name, d.active,
                  COALESCE(SUM(CASE WHEN x.type='income'
                                    THEN x.credit_paise - x.debit_paise ELSE 0 END), 0) AS revenue,
                  COALESCE(SUM(CASE WHEN x.type='expense'
                                    THEN x.debit_paise - x.credit_paise ELSE 0 END), 0) AS expense,
                  COUNT(x.line_id) AS lines
           FROM dimension d
           LEFT JOIN (
               SELECT l.id AS line_id, l.dimension_id, l.debit_paise, l.credit_paise, a.type
               FROM journal_line l
               JOIN journal_entry e ON e.id=l.entry_id AND e.tenant_id=l.tenant_id
               JOIN account a ON a.id=l.account_id AND a.tenant_id=l.tenant_id
               WHERE l.tenant_id=? AND e.entry_date BETWEEN ? AND ?
           ) x ON x.dimension_id=d.id
           WHERE d.tenant_id=? AND d.kind IN ({marks})
           GROUP BY d.id
           ORDER BY d.kind, d.code""",
        (tenant_id, date_from, date_to, tenant_id, *kinds),
    ).fetchall()
    out = []
    for r in rows:
        revenue = int(r["revenue"])
        expense = int(r["expense"])
        out.append({
            "id": r["id"], "kind": r["kind"], "code": r["code"], "name": r["name"],
            "active": bool(r["active"]), "revenue": revenue, "expense": expense,
            "net": revenue - expense, "lines": int(r["lines"]),
        })
    unalloc = conn.execute(
        f"""SELECT COALESCE(SUM(CASE WHEN a.type='income'
                                     THEN l.credit_paise - l.debit_paise ELSE 0 END), 0) AS revenue,
                   COALESCE(SUM(CASE WHEN a.type='expense'
                                     THEN l.debit_paise - l.credit_paise ELSE 0 END), 0) AS expense,
                   COUNT(l.id) AS lines
            FROM journal_line l
            JOIN journal_entry e ON e.id=l.entry_id AND e.tenant_id=l.tenant_id
            JOIN account a ON a.id=l.account_id AND a.tenant_id=l.tenant_id
            WHERE l.tenant_id=? AND e.entry_date BETWEEN ? AND ?
              AND (l.dimension_id IS NULL OR l.dimension_id NOT IN
                   (SELECT id FROM dimension WHERE tenant_id=? AND kind IN ({marks})))""",
        (tenant_id, date_from, date_to, tenant_id, *kinds),
    ).fetchone()
    unallocated = {
        "id": "", "kind": "unallocated", "code": "UNALLOC", "name": "Unallocated",
        "active": True, "revenue": int(unalloc["revenue"]), "expense": int(unalloc["expense"]),
        "net": int(unalloc["revenue"]) - int(unalloc["expense"]),
        "lines": int(unalloc["lines"]),
    }
    if unallocated["lines"] or unallocated["revenue"] or unallocated["expense"]:
        out.append(unallocated)
    return {
        "from": date_from, "to": date_to, "kinds": list(kinds), "rows": out,
        "totals": {
            "revenue": sum(r["revenue"] for r in out),
            "expense": sum(r["expense"] for r in out),
            "net": sum(r["net"] for r in out),
            "lines": sum(r["lines"] for r in out),
            "dimensions": len([r for r in out if r["kind"] != "unallocated"]),
        },
    }


def project_costing(conn: sqlite3.Connection, tenant, date_from: str,
                    date_to: str) -> dict:
    """R-601: direct tagged project/job revenue and cost.

    This is a tagged-journal report, not a full job-costing engine. Indirect
    cost allocation and timesheets are not posted, so the report never invents
    them.
    """
    data = _dimension_pl(conn, _tenant_id(tenant), date_from, date_to, ("project",))
    data["method"] = ("Direct project-tagged journal lines only. No indirect allocation, "
                      "timesheet or WIP adjustment is posted automatically.")
    return data


def cost_centre_performance(conn: sqlite3.Connection, tenant, date_from: str,
                            date_to: str) -> dict:
    """R-605: cost-centre actual expense against the monthly cost-centre budget."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    period_from = date_from[:7]
    period_to = date_to[:7]
    rows = conn.execute(
        """SELECT d.id, d.code, d.name, d.active,
                  COALESCE(a.actual, 0) AS actual,
                  COALESCE(b.budget, 0) AS budget,
                  COALESCE(a.lines, 0) AS lines
           FROM dimension d
           LEFT JOIN (
               SELECT l.dimension_id, SUM(l.debit_paise - l.credit_paise) AS actual,
                      COUNT(l.id) AS lines
               FROM journal_line l
               JOIN journal_entry e ON e.id=l.entry_id AND e.tenant_id=l.tenant_id
               JOIN account a ON a.id=l.account_id AND a.tenant_id=l.tenant_id
               WHERE l.tenant_id=? AND e.entry_date BETWEEN ? AND ?
                 AND a.type='expense'
               GROUP BY l.dimension_id
           ) a ON a.dimension_id=d.id
           LEFT JOIN (
               SELECT dimension_id, SUM(amount_paise) AS budget
               FROM dimension_budget
               WHERE tenant_id=? AND period BETWEEN ? AND ?
               GROUP BY dimension_id
           ) b ON b.dimension_id=d.id
           WHERE d.tenant_id=? AND d.kind='cost_centre'
           ORDER BY d.code""",
        (tenant_id, date_from, date_to, tenant_id, period_from, period_to, tenant_id),
    ).fetchall()
    out = []
    for r in rows:
        actual = int(r["actual"])
        budget = int(r["budget"])
        variance = budget - actual
        out.append({
            "id": r["id"], "code": r["code"], "name": r["name"], "active": bool(r["active"]),
            "actual": actual, "budget": budget, "variance": variance,
            "variance_pct": (variance * 10000 // budget) if budget else None,
            "status": ("No budget" if budget == 0 else
                       ("Under budget" if variance >= 0 else "Over budget")),
            "lines": int(r["lines"]),
        })
    unalloc = conn.execute(
        """SELECT COALESCE(SUM(l.debit_paise - l.credit_paise), 0) AS actual,
                  COUNT(l.id) AS lines
           FROM journal_line l
           JOIN journal_entry e ON e.id=l.entry_id AND e.tenant_id=l.tenant_id
           JOIN account a ON a.id=l.account_id AND a.tenant_id=l.tenant_id
           WHERE l.tenant_id=? AND e.entry_date BETWEEN ? AND ? AND a.type='expense'
             AND (l.dimension_id IS NULL OR l.dimension_id NOT IN
                  (SELECT id FROM dimension WHERE tenant_id=? AND kind='cost_centre'))""",
        (tenant_id, date_from, date_to, tenant_id),
    ).fetchone()
    if unalloc["lines"]:
        out.append({
            "id": "", "code": "UNALLOC", "name": "Unallocated", "active": True,
            "actual": int(unalloc["actual"]), "budget": 0,
            "variance": -int(unalloc["actual"]), "variance_pct": None,
            "status": "No budget", "lines": int(unalloc["lines"]),
        })
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "actual": sum(r["actual"] for r in out),
            "budget": sum(r["budget"] for r in out),
            "variance": sum(r["variance"] for r in out),
            "over": sum(1 for r in out if r["status"] == "Over budget"),
            "under": sum(1 for r in out if r["status"] == "Under budget"),
            "no_budget": sum(1 for r in out if r["status"] == "No budget"),
        },
        "method": ("Actual expense is the net debit on cost-centre-tagged expense lines. "
                   "Budget is the sum of monthly cost-centre budgets in the period. "
                   "Unallocated expense has no budget by design."),
    }


def department_branch_pnl(conn: sqlite3.Connection, tenant, date_from: str,
                          date_to: str, kind: str | None = None) -> dict:
    """R-902: contribution by department and/or branch, with unallocated row."""
    kinds = ("department", "branch") if not kind else (kind,)
    if any(k not in ("department", "branch") for k in kinds):
        raise ReportError("BAD_KIND", "Choose department, branch or both")
    data = _dimension_pl(conn, _tenant_id(tenant), date_from, date_to, kinds)
    data["method"] = ("Only journal lines tagged to the selected department/branch are allocated. "
                      "Project and cost-centre tags are shown as unallocated here; no automatic "
                      "recharge or allocation is posted.")
    return data


def expiry_batch_report(conn: sqlite3.Connection, tenant, as_of: str | None = None) -> dict:
    """R-508: batch/expiry working paper from the manual batch register."""
    return advanced.list_batches(conn, tenant, as_of=as_of)


def wip_report(conn: sqlite3.Connection, tenant, date_from: str,
               date_to: str) -> dict:
    """R-602: open production-order input value less completed output value."""
    _validate_period(date_from, date_to)
    orders = [r for r in advanced.list_production_orders(
        conn, tenant, date_from=date_from, date_to=date_to) if r["status"] != "void"]
    out = []
    for r in orders:
        out.append({
            **r,
            "wip": r["wip_value"],
        })
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "orders": len(out), "open": sum(1 for r in out if r["status"] == "open"),
            "completed": sum(1 for r in out if r["status"] == "completed"),
            "input_value": sum(r["input_value"] for r in out),
            "output_value": sum(r["output_value"] for r in out),
            "wip": sum(r["wip"] for r in out),
        },
        "method": ("Operational production register only. WIP is input value less output value "
                   "for open orders; completed orders show zero WIP. No journal or stock movement "
                   "is posted by this register."),
    }


def production_consumption(conn: sqlite3.Connection, tenant, date_from: str,
                           date_to: str) -> dict:
    """R-603: actual input quantity against standard input quantity."""
    _validate_period(date_from, date_to)
    orders = [r for r in advanced.list_production_orders(
        conn, tenant, date_from=date_from, date_to=date_to) if r["status"] != "void"]
    out = []
    for r in orders:
        out.append({
            **r,
            "variance_qty": r["variance_qty"],
            "variance_pct": r["variance_pct"],
        })
    measured = [r for r in out if r["standard_input_qty_milli"] > 0]
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "orders": len(out), "measured": len(measured),
            "actual_qty": sum(r["input_qty_milli"] for r in out),
            "standard_qty": sum(r["standard_input_qty_milli"] for r in out),
            "variance_qty": sum((r["variance_qty"] or 0) for r in measured),
            "variance_pct": ((sum((r["variance_qty"] or 0) for r in measured) * 10000
                              // sum(r["standard_input_qty_milli"] for r in measured))
                             if measured and sum(r["standard_input_qty_milli"] for r in measured)
                             else None),
            "over": sum(1 for r in measured if (r["variance_qty"] or 0) > 0),
            "under": sum(1 for r in measured if (r["variance_qty"] or 0) < 0),
        },
        "method": ("Actual input quantity is entered on the production order. Standard input "
                   "quantity is the user-entered benchmark. Orders with no standard are shown "
                   "but excluded from variance totals."),
    }


def yield_wastage(conn: sqlite3.Connection, tenant, date_from: str,
                  date_to: str) -> dict:
    """R-604: output quantity divided by input quantity, with wastage balance."""
    _validate_period(date_from, date_to)
    orders = [r for r in advanced.list_production_orders(
        conn, tenant, date_from=date_from, date_to=date_to) if r["status"] != "void"]
    out = []
    for r in orders:
        out.append({
            **r,
            "yield_pct": r["yield_pct"],
            "wastage_pct": r["wastage_pct"],
            "loss_value": max(0, r["input_value"] - r["output_value"]),
        })
    input_qty = sum(r["input_qty_milli"] for r in out)
    output_qty = sum(r["output_qty_milli"] for r in out)
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "orders": len(out), "input_qty": input_qty, "output_qty": output_qty,
            "yield_pct": (output_qty * 10000 // input_qty) if input_qty else None,
            "wastage_pct": ((input_qty - output_qty) * 10000 // input_qty) if input_qty else None,
            "loss_value": sum(r["loss_value"] for r in out),
        },
        "method": ("Yield is output quantity / input quantity. Wastage is the balance. "
                   "Loss value is input value less output value where positive; it is an "
                   "operational indicator, not a posted expense."),
    }


def consolidated_summary(conn: sqlite3.Connection, tenant_ids: list[str],
                         as_of: str | None = None) -> dict:
    """R-1004: read-only consolidation of owner/admin-accessible tenants.

    Intercompany-flagged journal entries are shown separately and excluded from
    the combined totals. There is no automatic matching or elimination engine.
    """
    as_of = as_of or date.today().isoformat()
    _parse_date(as_of, "As of")
    out = []
    for tenant_id in tenant_ids:
        t = conn.execute("SELECT id, name, slug FROM tenant WHERE id=?",
                         (tenant_id,)).fetchone()
        if not t:
            continue
        r = conn.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN a.type='income' AND e.is_intercompany=0
                                   THEN l.credit_paise - l.debit_paise ELSE 0 END), 0) AS revenue,
                 COALESCE(SUM(CASE WHEN a.type='expense' AND e.is_intercompany=0
                                   THEN l.debit_paise - l.credit_paise ELSE 0 END), 0) AS expense,
                 COALESCE(SUM(CASE WHEN a.type='asset' AND e.is_intercompany=0
                                   THEN l.debit_paise - l.credit_paise ELSE 0 END), 0) AS assets,
                 COALESCE(SUM(CASE WHEN a.type='liability' AND e.is_intercompany=0
                                   THEN l.credit_paise - l.debit_paise ELSE 0 END), 0) AS liabilities,
                 COALESCE(SUM(CASE WHEN a.type='equity' AND e.is_intercompany=0
                                   THEN l.credit_paise - l.debit_paise ELSE 0 END), 0) AS equity,
                 COUNT(DISTINCT CASE WHEN e.is_intercompany=1 THEN e.id END) AS ic_entries,
                 COALESCE(SUM(CASE WHEN e.is_intercompany=1 THEN l.debit_paise ELSE 0 END), 0)
                   AS ic_value
               FROM journal_line l
               JOIN journal_entry e ON e.id=l.entry_id AND e.tenant_id=l.tenant_id
               JOIN account a ON a.id=l.account_id AND a.tenant_id=l.tenant_id
               WHERE l.tenant_id=? AND e.entry_date <= ?""",
            (tenant_id, as_of),
        ).fetchone()
        revenue = int(r["revenue"])
        expense = int(r["expense"])
        out.append({
            "id": t["id"], "name": t["name"], "slug": t["slug"],
            "revenue": revenue, "expense": expense, "profit": revenue - expense,
            "assets": int(r["assets"]), "liabilities": int(r["liabilities"]),
            "equity": int(r["equity"]), "intercompany_entries": int(r["ic_entries"]),
            "intercompany_value": int(r["ic_value"]),
        })
    return {
        "as_of": as_of, "rows": out,
        "totals": {
            "tenants": len(out),
            "revenue": sum(r["revenue"] for r in out),
            "expense": sum(r["expense"] for r in out),
            "profit": sum(r["profit"] for r in out),
            "assets": sum(r["assets"] for r in out),
            "liabilities": sum(r["liabilities"] for r in out),
            "equity": sum(r["equity"] for r in out),
            "intercompany_entries": sum(r["intercompany_entries"] for r in out),
            "intercompany_value": sum(r["intercompany_value"] for r in out),
        },
        "method": ("Sums posted balances for tenants where you are owner/admin. "
                   "Manual journals marked intercompany are excluded from combined totals and "
                   "reported separately. No automatic intercompany matching is performed."),
    }


# ---------------------------------------------------------------------------
# report catalogue used by the in-app library
# ---------------------------------------------------------------------------

def _r(id_, group, title, status, route, formula):
    return {"id": id_, "group": group, "title": title, "status": status,
            "route": route, "formula": formula}


REPORT_CATALOG = [
    # Group 1 — financial statements
    _r("R-101", "Financial statements", "Trial Balance", "working", "/reports/trial-balance", "Σ debit and credit by account; closing signed balance"),
    _r("R-102", "Financial statements", "Profit & Loss", "working", "/reports/pnl", "Posted income − posted expenses"),
    _r("R-103", "Financial statements", "Balance Sheet", "working", "/reports/balance-sheet", "Assets = liabilities + equity, including retained earnings"),
    _r("R-104", "Financial statements", "Cash Flow", "working", "/reports/cash-flow", "Direct cash movement + indirect bridge from net profit and working capital"),
    _r("R-105", "Financial statements", "General Ledger", "working", "/ledger", "Running balance per account"),
    _r("R-106", "Financial statements", "Journal Register / Day Book", "working", "/daybook", "Chronological posted entries with totals"),
    _r("R-107", "Financial statements", "Opening vs Closing Balances", "working", "/reports/opening-closing", "Opening + period debit - period credit = closing per ledger"),
    _r("R-108", "Financial statements", "Financial Ratios", "working", "/reports/ratios", "Liquidity, margin, return and leverage ratios from posted records"),
    _r("R-109", "Financial statements", "Period-over-Period Comparison", "working", "/reports/comparison", "Current period versus equal-length prior period"),
    _r("R-110", "Financial statements", "Trial Balance Exception Report", "working", "/reports/tb-exceptions", "Entries failing balance or precision checks"),
    # Group 2 — accounting and audit
    _r("R-201", "Accounting & audit", "Audit Trail", "working", "/audit", "Chronological actor, action and target"),
    _r("R-202", "Accounting & audit", "Reversal & Correction Register", "working", "/reports/reversals", "Original entry and its reversal, with reason"),
    _r("R-203", "Accounting & audit", "Account Activity Summary", "working", "/reports/account-activity", "Line count, debit, credit and net per account"),
    _r("R-204", "Accounting & audit", "Unposted / Draft Entries", "working", "/reports/draft-entries", "Draft sales invoices and their age; no journal or stock effect until posted"),
    _r("R-205", "Accounting & audit", "Locked Period Register", "working", "/reports/locked-periods", "Locked periods with locking actor and timestamp"),
    _r("R-206", "Accounting & audit", "Rule Version Usage", "working", "/reports/rule-versions", "Posted entries grouped by the rule version stored at posting time"),
    # Group 3 — sales
    _r("R-301", "Sales & customers", "Sales Register", "working", "/reports/sales-register", "Posted invoices with taxable, tax and total"),
    _r("R-302", "Sales & customers", "Sales Summary by Period", "working", "/reports/sales-summary", "Grouped posted-invoice totals and month-on-month growth"),
    _r("R-303", "Sales & customers", "Top Customers", "working", "/reports/top-customers", "Rank by posted-invoice revenue, share and cumulative share"),
    _r("R-304", "Sales & customers", "Customer Ageing", "working", "/reports/ar-ageing", "Open AR buckets 0-30/31-60/61-90/90+"),
    _r("R-305", "Sales & customers", "Customer Statement", "working", "/customers", "Opening + invoices − receipts = closing"),
    _r("R-306", "Sales & customers", "Sales Returns", "working", "/reports/sales-returns", "Posted credit notes and return rate against invoice value"),
    _r("R-307", "Sales & customers", "Product-wise Sales", "working", "/reports/product-sales", "Quantity, revenue and margin by product at current item cost"),
    _r("R-308", "Sales & customers", "Salesperson Performance", "working", "/reports/salesperson", "Posted invoice revenue and receipt collections grouped by creator"),
    _r("R-309", "Sales & customers", "Discount Analysis", "working", "/reports/discounts", "Line-level discount value and share of gross"),
    # Group 4 — purchases
    _r("R-401", "Purchases & suppliers", "Purchase Register", "working", "/reports/purchase-register", "Posted bills with taxable, tax and total"),
    _r("R-402", "Purchases & suppliers", "Supplier Ageing", "working", "/reports/ap-ageing", "Open AP buckets 0-30/31-60/61-90/90+"),
    _r("R-403", "Purchases & suppliers", "Supplier Statement", "working", "/vendors", "Opening + purchases − payments = closing"),
    _r("R-404", "Purchases & suppliers", "Top Suppliers / Concentration", "working", "/reports/top-suppliers", "Rank by posted-bill value, share and cumulative share"),
    _r("R-405", "Purchases & suppliers", "Price Variance", "working", "/reports/price-variance", "Latest bill price vs previous bill price and current weighted-average cost"),
    _r("R-406", "Purchases & suppliers", "Purchase Return Analysis", "working", "/reports/purchase-returns", "Posted debit notes and return rate against bill value"),
    # Group 5 — inventory
    _r("R-501", "Inventory & warehouse", "Stock Summary", "working", "/reports/stock-summary", "Opening + posted in - posted out = closing per item"),
    _r("R-502", "Inventory & warehouse", "Stock Movement History", "working", "/reports/stock-movements", "Chronological posted stock in/out with source document"),
    _r("R-503", "Inventory & warehouse", "Inventory Valuation", "working", "/reports/inventory-valuation", "Closing quantity x current moving weighted-average cost"),
    _r("R-504", "Inventory & warehouse", "Reorder / Shortage", "working", "/reports/reorder", "Items at or below reorder level, or out of stock"),
    _r("R-505", "Inventory & warehouse", "Dead / Slow Stock", "working", "/reports/dead-stock", "Stocked items with no posted movement for N days"),
    _r("R-506", "Inventory & warehouse", "Stock Adjustment Register", "working", "/reports/stock-adjustments", "Chronological manual adjustments with signed quantity, current-cost value, reason and journal"),
    _r("R-507", "Inventory & warehouse", "Inventory to GL Reconciliation", "working", "/reports/inventory-gl", "Item-master stock value versus inventory ledger balance"),
    _r("R-508", "Inventory & warehouse", "Expiry / Batch Report", "working", "/reports/expiry", "Days to expiry buckets from the manual batch register"),
    # Group 6 — costing
    _r("R-601", "Costing & operations", "Job / Project Costing", "working", "/reports/project-costing", "Direct project-tagged journal revenue and cost; no automatic indirect allocation"),
    _r("R-602", "Costing & operations", "WIP Report", "working", "/reports/wip", "Open production-order input value less completed output value"),
    _r("R-603", "Costing & operations", "Production Consumption", "working", "/reports/production-consumption", "Actual input quantity versus user-entered standard input quantity"),
    _r("R-604", "Costing & operations", "Yield / Wastage", "working", "/reports/yield", "Output ÷ input and wastage percentage"),
    _r("R-605", "Costing & operations", "Cost Centre Performance", "working", "/reports/cost-centre", "Cost-centre actual expense versus monthly cost-centre budget"),
    # Group 7 — cash and risk
    _r("R-701", "Cash, credit & risk", "Cash Book", "working", "/reports/cash-book", "Opening + receipts − payments"),
    _r("R-702", "Cash, credit & risk", "Bank Book", "working", "/reports/bank-book", "Opening + receipts − payments per bank"),
    _r("R-703", "Cash, credit & risk", "Bank Reconciliation Statement", "working", "/bank-recon", "Difference = timing + errors"),
    _r("R-704", "Cash, credit & risk", "Receivables Risk", "working", "/reports/receivables-risk", "Overdue exposure, credit utilisation and prior-period trend"),
    _r("R-705", "Cash, credit & risk", "Cash Flow Forecast", "working", "/reports/cash-flow-forecast", "Weekly opening cash + scheduled collections - scheduled payments"),
    _r("R-706", "Cash, credit & risk", "Credit Limit Utilisation", "working", "/reports/credit-limits", "Open receivable against customer credit limit"),
    # Group 8 — tax
    _r("R-801", "Tax & compliance", "GST Output Summary", "working", "/reports/gst", "Tax by rate and HSN"),
    _r("R-802", "Tax & compliance", "GST Input Summary", "working", "/reports/gst", "Input tax by rate and HSN"),
    _r("R-803", "Tax & compliance", "GSTR-1 Working Paper", "working", "/reports/gst", "Period-wise outward supplies"),
    _r("R-804", "Tax & compliance", "GSTR-3B Working Paper", "working", "/reports/gstr3b", "Output tax − eligible ITC, head-wise"),
    _r("R-805", "Tax & compliance", "HSN/SAC Summary", "working", "/reports/gst", "Quantity, value and tax per HSN/SAC"),
    _r("R-806", "Tax & compliance", "ITC Reconciliation (2B)", "working", "/gstr2b", "Matched, mismatched and missing ITC"),
    _r("R-807", "Tax & compliance", "Tax Ledger", "working", "/reports/tax-ledger", "Opening + output tax - input credit = closing per tax ledger"),
    # Group 9 — strategy and process
    _r("R-901", "Strategy & process", "Budget vs Actual", "working", "/reports/budget", "Variance = actual - budget for stored monthly income and expense budgets"),
    _r("R-902", "Strategy & process", "Department / Branch P&L", "working", "/reports/dimension-pnl", "Tagged department/branch contribution plus an explicit unallocated row"),
    _r("R-903", "Strategy & process", "Expense Breakdown", "working", "/reports/expense-breakdown", "Expense by account with share of total"),
    _r("R-904", "Management & KPIs", "KPI Dashboard Pack", "working", "/reports/kpi-pack", "Actual-only KPI cards from statements, ratios, cash, ageing and inventory"),
    _r("R-905", "Strategy & process", "Working Capital Cycle", "working", "/reports/working-capital", "DSO + DIO − DPO"),
    # Group 10 — AI and cross-business
    _r("R-1001", "AI-assisted analysis", "Trend Explanation", "working", "/reports/trend-explanation", "Deterministic narrative over monthly actual revenue and expenses"),
    _r("R-1002", "AI-assisted analysis", "Revenue Forecast", "working", "/reports/revenue-forecast", "Least-squares forecast from monthly actual net revenue, with an indicative band"),
    _r("R-1003", "AI-assisted analysis", "Anomaly Digest", "working", "/reports/anomaly-digest", "Rule-based review prompts over posted journals, invoices, stock and receivables"),
    _r("R-1004", "AI & cross-business", "Consolidated Multi-Company", "working", "/reports/consolidated", "Owner/admin consolidation with intercompany-flagged journals excluded from combined totals"),
]


def catalog() -> dict:
    groups: list[dict] = []
    for row in REPORT_CATALOG:
        group = next((g for g in groups if g["name"] == row["group"]), None)
        if group is None:
            group = {"name": row["group"], "reports": []}
            groups.append(group)
        group["reports"].append(row)
    working = sum(1 for r in REPORT_CATALOG if r["status"] == "working")
    partial = sum(1 for r in REPORT_CATALOG if r["status"] == "partial")
    return {
        "groups": groups,
        "total": len(REPORT_CATALOG),
        "working": working,
        "partial": partial,
        "planned": len(REPORT_CATALOG) - working - partial,
    }
