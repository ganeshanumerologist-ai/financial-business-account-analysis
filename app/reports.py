"""Deterministic management reports built only from posted records.

The functions in this module do not cache, forecast or invent figures. Every
number is derived from journal rows, invoices, bills or the chart of accounts.
Ratios may be floats; money stays in integer paise until display.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from . import accounting as acct


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
    are removed to reconstruct the closing quantity at that date. No manual
    stock-adjustment table exists in this build, so the report states that limit.
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
        (tenant_id, tenant_id, tenant_id, tenant_id,
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
    _r("R-107", "Financial statements", "Opening vs Closing Balances", "partial", "", "Opening + movements = closing"),
    _r("R-108", "Financial statements", "Financial Ratios", "working", "/reports/ratios", "Liquidity, margin, return and leverage ratios from posted records"),
    _r("R-109", "Financial statements", "Period-over-Period Comparison", "working", "/reports/comparison", "Current period versus equal-length prior period"),
    _r("R-110", "Financial statements", "Trial Balance Exception Report", "working", "/reports/tb-exceptions", "Entries failing balance or precision checks"),
    # Group 2 — accounting and audit
    _r("R-201", "Accounting & audit", "Audit Trail", "working", "/audit", "Chronological actor, action and target"),
    _r("R-202", "Accounting & audit", "Reversal & Correction Register", "working", "/reports/reversals", "Original entry and its reversal, with reason"),
    _r("R-203", "Accounting & audit", "Account Activity Summary", "working", "/reports/account-activity", "Line count, debit, credit and net per account"),
    _r("R-204", "Accounting & audit", "Unposted / Draft Entries", "planned", "", "Draft entries and their age"),
    _r("R-205", "Accounting & audit", "Locked Period Register", "planned", "", "Locked periods and who locked them"),
    _r("R-206", "Accounting & audit", "Rule Version Usage", "planned", "", "Entries grouped by applied rule version"),
    # Group 3 — sales
    _r("R-301", "Sales & customers", "Sales Register", "working", "/reports/sales-register", "Posted invoices with taxable, tax and total"),
    _r("R-302", "Sales & customers", "Sales Summary by Period", "working", "/reports/sales-summary", "Grouped posted-invoice totals and month-on-month growth"),
    _r("R-303", "Sales & customers", "Top Customers", "working", "/reports/top-customers", "Rank by posted-invoice revenue, share and cumulative share"),
    _r("R-304", "Sales & customers", "Customer Ageing", "working", "/reports/ar-ageing", "Open AR buckets 0-30/31-60/61-90/90+"),
    _r("R-305", "Sales & customers", "Customer Statement", "working", "/customers", "Opening + invoices − receipts = closing"),
    _r("R-306", "Sales & customers", "Sales Returns", "working", "/reports/sales-returns", "Posted credit notes and return rate against invoice value"),
    _r("R-307", "Sales & customers", "Product-wise Sales", "working", "/reports/product-sales", "Quantity, revenue and margin by product at current item cost"),
    _r("R-308", "Sales & customers", "Salesperson Performance", "planned", "", "Revenue and collection per user"),
    _r("R-309", "Sales & customers", "Discount Analysis", "working", "/reports/discounts", "Line-level discount value and share of gross"),
    # Group 4 — purchases
    _r("R-401", "Purchases & suppliers", "Purchase Register", "working", "/reports/purchase-register", "Posted bills with taxable, tax and total"),
    _r("R-402", "Purchases & suppliers", "Supplier Ageing", "working", "/reports/ap-ageing", "Open AP buckets 0-30/31-60/61-90/90+"),
    _r("R-403", "Purchases & suppliers", "Supplier Statement", "working", "/vendors", "Opening + purchases − payments = closing"),
    _r("R-404", "Purchases & suppliers", "Top Suppliers / Concentration", "working", "/reports/top-suppliers", "Rank by posted-bill value, share and cumulative share"),
    _r("R-405", "Purchases & suppliers", "Price Variance", "planned", "", "Actual versus last or standard price"),
    _r("R-406", "Purchases & suppliers", "Purchase Return Analysis", "working", "/reports/purchase-returns", "Posted debit notes and return rate against bill value"),
    # Group 5 — inventory
    _r("R-501", "Inventory & warehouse", "Stock Summary", "working", "/reports/stock-summary", "Opening + posted in - posted out = closing per item"),
    _r("R-502", "Inventory & warehouse", "Stock Movement History", "planned", "", "Chronological movement with source document"),
    _r("R-503", "Inventory & warehouse", "Inventory Valuation", "planned", "", "FIFO or weighted-average valuation"),
    _r("R-504", "Inventory & warehouse", "Reorder / Shortage", "planned", "", "Items below reorder threshold"),
    _r("R-505", "Inventory & warehouse", "Dead / Slow Stock", "planned", "", "No movement in N days"),
    _r("R-506", "Inventory & warehouse", "Stock Adjustment Register", "planned", "", "Adjustments with reason and approver"),
    _r("R-507", "Inventory & warehouse", "Inventory ↔ GL Reconciliation", "planned", "", "Stock value versus inventory ledger"),
    _r("R-508", "Inventory & warehouse", "Expiry / Batch Report", "planned", "", "Days to expiry buckets"),
    # Group 6 — costing
    _r("R-601", "Costing & operations", "Job / Project Costing", "planned", "", "Direct plus allocated indirect cost"),
    _r("R-602", "Costing & operations", "WIP Report", "planned", "", "Inputs minus completed output"),
    _r("R-603", "Costing & operations", "Production Consumption", "planned", "", "Actual versus standard consumption"),
    _r("R-604", "Costing & operations", "Yield / Wastage", "planned", "", "Output ÷ input and wastage percentage"),
    _r("R-605", "Costing & operations", "Cost Centre Performance", "planned", "", "Budget versus actual per centre"),
    # Group 7 — cash and risk
    _r("R-701", "Cash, credit & risk", "Cash Book", "working", "/reports/cash-book", "Opening + receipts − payments"),
    _r("R-702", "Cash, credit & risk", "Bank Book", "working", "/reports/bank-book", "Opening + receipts − payments per bank"),
    _r("R-703", "Cash, credit & risk", "Bank Reconciliation Statement", "working", "/bank-recon", "Difference = timing + errors"),
    _r("R-704", "Cash, credit & risk", "Receivables Risk", "planned", "", "Overdue value, exposure and trend"),
    _r("R-705", "Cash, credit & risk", "Cash Flow Forecast", "planned", "", "Projected inflows and outflows, explicitly labelled forecast"),
    _r("R-706", "Cash, credit & risk", "Credit Limit Utilisation", "working", "/reports/credit-limits", "Open receivable against customer credit limit"),
    # Group 8 — tax
    _r("R-801", "Tax & compliance", "GST Output Summary", "working", "/reports/gst", "Tax by rate and HSN"),
    _r("R-802", "Tax & compliance", "GST Input Summary", "working", "/reports/gst", "Input tax by rate and HSN"),
    _r("R-803", "Tax & compliance", "GSTR-1 Working Paper", "working", "/reports/gst", "Period-wise outward supplies"),
    _r("R-804", "Tax & compliance", "GSTR-3B Working Paper", "working", "/reports/gstr3b", "Output tax − eligible ITC, head-wise"),
    _r("R-805", "Tax & compliance", "HSN/SAC Summary", "working", "/reports/gst", "Quantity, value and tax per HSN/SAC"),
    _r("R-806", "Tax & compliance", "ITC Reconciliation (2B)", "working", "/gstr2b", "Matched, mismatched and missing ITC"),
    _r("R-807", "Tax & compliance", "Tax Ledger", "planned", "", "Opening + payable − paid = closing"),
    # Group 9 — strategy and process
    _r("R-901", "Strategy & process", "Budget vs Actual", "planned", "", "Variance = actual − budget"),
    _r("R-902", "Strategy & process", "Department / Branch P&L", "planned", "", "Contribution by scope"),
    _r("R-903", "Strategy & process", "Expense Breakdown", "working", "/reports/expense-breakdown", "Expense by account with share of total"),
    _r("R-904", "Strategy & process", "KPI Dashboard Pack", "planned", "", "Composite with definitions shown"),
    _r("R-905", "Strategy & process", "Working Capital Cycle", "working", "/reports/working-capital", "DSO + DIO − DPO"),
    # Group 10 — AI and cross-business
    _r("R-1001", "AI & cross-business", "Trend Explanation", "planned", "", "Deterministic statistics and narrative with sources"),
    _r("R-1002", "AI & cross-business", "Revenue Forecast", "planned", "", "Model output, labelled forecast with error band"),
    _r("R-1003", "AI & cross-business", "Anomaly Digest", "planned", "", "Flagged items with reasons"),
    _r("R-1004", "AI & cross-business", "Consolidated Multi-Company", "planned", "", "Sum with intercompany eliminations, authorised only"),
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
