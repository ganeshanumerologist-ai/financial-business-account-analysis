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
    _r("R-110", "Financial statements", "Trial Balance Exception Report", "planned", "", "Entries failing balance or precision checks"),
    # Group 2 — accounting and audit
    _r("R-201", "Accounting & audit", "Audit Trail", "working", "/audit", "Chronological actor, action and target"),
    _r("R-202", "Accounting & audit", "Reversal & Correction Register", "working", "/reports/reversals", "Original entry and its reversal, with reason"),
    _r("R-203", "Accounting & audit", "Account Activity Summary", "working", "/reports/account-activity", "Line count, debit, credit and net per account"),
    _r("R-204", "Accounting & audit", "Unposted / Draft Entries", "planned", "", "Draft entries and their age"),
    _r("R-205", "Accounting & audit", "Locked Period Register", "planned", "", "Locked periods and who locked them"),
    _r("R-206", "Accounting & audit", "Rule Version Usage", "planned", "", "Entries grouped by applied rule version"),
    # Group 3 — sales
    _r("R-301", "Sales & customers", "Sales Register", "working", "/reports/sales-register", "Posted invoices with taxable, tax and total"),
    _r("R-302", "Sales & customers", "Sales Summary by Period", "planned", "", "Grouped totals and growth"),
    _r("R-303", "Sales & customers", "Top Customers", "planned", "", "Rank by revenue and share"),
    _r("R-304", "Sales & customers", "Customer Ageing", "working", "/reports/ar-ageing", "Open AR buckets 0-30/31-60/61-90/90+"),
    _r("R-305", "Sales & customers", "Customer Statement", "working", "/customers", "Opening + invoices − receipts = closing"),
    _r("R-306", "Sales & customers", "Sales Returns", "planned", "", "Credit notes and return rate"),
    _r("R-307", "Sales & customers", "Product-wise Sales", "planned", "", "Quantity, revenue and margin by product"),
    _r("R-308", "Sales & customers", "Salesperson Performance", "planned", "", "Revenue and collection per user"),
    _r("R-309", "Sales & customers", "Discount Analysis", "planned", "", "Discount value and share of gross"),
    # Group 4 — purchases
    _r("R-401", "Purchases & suppliers", "Purchase Register", "working", "/reports/purchase-register", "Posted bills with taxable, tax and total"),
    _r("R-402", "Purchases & suppliers", "Supplier Ageing", "working", "/reports/ap-ageing", "Open AP buckets 0-30/31-60/61-90/90+"),
    _r("R-403", "Purchases & suppliers", "Supplier Statement", "working", "/vendors", "Opening + purchases − payments = closing"),
    _r("R-404", "Purchases & suppliers", "Top Suppliers / Concentration", "planned", "", "Rank and share of purchases"),
    _r("R-405", "Purchases & suppliers", "Price Variance", "planned", "", "Actual versus last or standard price"),
    _r("R-406", "Purchases & suppliers", "Purchase Return Analysis", "planned", "", "Debit notes and return rate"),
    # Group 5 — inventory
    _r("R-501", "Inventory & warehouse", "Stock Summary", "planned", "", "In − out per item"),
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
    _r("R-706", "Cash, credit & risk", "Credit Limit Utilisation", "planned", "", "Outstanding ÷ credit limit"),
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
