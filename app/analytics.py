"""Read-only analytics semantic layer and metric registry.

This module is the contract that the web UI, Excel exports and Power BI will
share. It never posts, edits or caches an authoritative total: every metric is
derived from posted journal rows and existing deterministic report functions.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

from . import accounting as acct

SCHEMA_VERSION = "1.0"
PERMISSION = "report.view"
UNIT_PAISE = "INR paise"
UNIT_COUNT = "count"
UNIT_BOOLEAN = "boolean"

METRICS = (
    {
        "key": "revenue_paise",
        "label": "Revenue",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "journal_line, account type income",
        "formula": "sum(credit_paise - debit_paise) for income accounts in the period",
        "permission": PERMISSION,
        "drilldown": "/reports/pnl",
    },
    {
        "key": "expense_paise",
        "label": "Expenses",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "journal_line, account type expense",
        "formula": "sum(debit_paise - credit_paise) for expense accounts in the period",
        "permission": PERMISSION,
        "drilldown": "/reports/pnl",
    },
    {
        "key": "net_profit_paise",
        "label": "Net profit",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "profit_and_loss",
        "formula": "revenue minus expenses",
        "permission": PERMISSION,
        "drilldown": "/reports/pnl",
    },
    {
        "key": "total_assets_paise",
        "label": "Total assets",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "balance_sheet",
        "formula": "sum of signed asset balances as of the period end",
        "permission": PERMISSION,
        "drilldown": "/reports/balance-sheet",
    },
    {
        "key": "total_liabilities_paise",
        "label": "Total liabilities",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "balance_sheet",
        "formula": "sum of credit-normal liability balances as of the period end",
        "permission": PERMISSION,
        "drilldown": "/reports/balance-sheet",
    },
    {
        "key": "total_equity_paise",
        "label": "Total equity",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "balance_sheet",
        "formula": "equity balances plus retained earnings as of the period end",
        "permission": PERMISSION,
        "drilldown": "/reports/balance-sheet",
    },
    {
        "key": "cash_and_bank_paise",
        "label": "Cash and bank",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "account_balances, cash and bank groups",
        "formula": "sum of cash and linked bank account balances as of the period end",
        "permission": PERMISSION,
        "drilldown": "/reports/cash-book",
    },
    {
        "key": "receivable_paise",
        "label": "Receivable",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "account_balances, receivable group",
        "formula": "sum of customer receivable balances as of the period end",
        "permission": PERMISSION,
        "drilldown": "/reports/ar-ageing",
    },
    {
        "key": "payable_paise",
        "label": "Payable",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "account_balances, payable group",
        "formula": "sum of supplier payable balances as of the period end",
        "permission": PERMISSION,
        "drilldown": "/reports/ap-ageing",
    },
    {
        "key": "inventory_paise",
        "label": "Inventory",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "account_balances, inventory group",
        "formula": "inventory ledger balance as of the period end",
        "permission": PERMISSION,
        "drilldown": "/items",
    },
    {
        "key": "open_invoices",
        "label": "Open invoices",
        "unit": UNIT_COUNT,
        "kind": "actual",
        "source": "receivable_ageing",
        "formula": "count of posted invoices with an outstanding balance",
        "permission": PERMISSION,
        "drilldown": "/reports/ar-ageing",
    },
    {
        "key": "open_bills",
        "label": "Open bills",
        "unit": UNIT_COUNT,
        "kind": "actual",
        "source": "payable_ageing",
        "formula": "count of posted bills with an outstanding balance",
        "permission": PERMISSION,
        "drilldown": "/reports/ap-ageing",
    },
    {
        "key": "overdue_receivable_paise",
        "label": "Overdue receivable (60+ days)",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "receivable_ageing",
        "formula": "sum of 61-90 and 90+ receivable buckets",
        "permission": PERMISSION,
        "drilldown": "/reports/ar-ageing",
    },
    {
        "key": "overdue_payable_paise",
        "label": "Overdue payable (60+ days)",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "payable_ageing",
        "formula": "sum of 61-90 and 90+ payable buckets",
        "permission": PERMISSION,
        "drilldown": "/reports/ap-ageing",
    },
    {
        "key": "gst_output_paise",
        "label": "GST output tax",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "gst_summary",
        "formula": "output CGST + SGST + IGST for the period",
        "permission": PERMISSION,
        "drilldown": "/reports/gst",
    },
    {
        "key": "gst_input_paise",
        "label": "GST input tax",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "gst_summary",
        "formula": "input CGST + SGST + IGST for the period",
        "permission": PERMISSION,
        "drilldown": "/reports/gst",
    },
    {
        "key": "gst_net_payable_paise",
        "label": "GST net payable",
        "unit": UNIT_PAISE,
        "kind": "actual",
        "source": "gst_summary",
        "formula": "output tax minus input tax; negative means net input credit",
        "permission": PERMISSION,
        "drilldown": "/reports/gst",
    },
    {
        "key": "trial_balance_balanced",
        "label": "Trial balance balanced",
        "unit": UNIT_BOOLEAN,
        "kind": "actual",
        "source": "trial_balance",
        "formula": "sum(debit_paise) equals sum(credit_paise) as of the period end",
        "permission": PERMISSION,
        "drilldown": "/reports/trial-balance",
    },
    {
        "key": "balance_sheet_balanced",
        "label": "Balance sheet balanced",
        "unit": UNIT_BOOLEAN,
        "kind": "actual",
        "source": "balance_sheet",
        "formula": "assets equal liabilities plus equity as of the period end",
        "permission": PERMISSION,
        "drilldown": "/reports/balance-sheet",
    },
)


class AnalyticsError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def catalog() -> dict:
    """Return the stable metric contract used by API, Excel and Power BI."""
    return {
        "schema_version": SCHEMA_VERSION,
        "permission": PERMISSION,
        "metrics": [dict(m) for m in METRICS],
        "notes": [
            "All registered metrics are actuals from posted journal lines.",
            "Forecast and estimate metrics are not part of schema version 1.0.",
            "Amounts are integer paise; the API does not return binary floats.",
        ],
    }


def _fiscal_start(tenant, as_of: date) -> date:
    try:
        month = int(tenant["fiscal_year_start_month"] or 4)
    except (KeyError, TypeError, ValueError):
        month = 4
    month = max(1, min(12, month))
    start = date(as_of.year, month, 1)
    if start > as_of:
        start = date(as_of.year - 1, month, 1)
    return start


def _tenant_key(tenant) -> str:
    """Accept a tenant row or a tenant id string for the read-only layer."""
    try:
        return tenant["id"]
    except (KeyError, TypeError, IndexError):
        return str(tenant)


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except (TypeError, ValueError):
        raise AnalyticsError("BAD_DATE", f"{field} must be a valid YYYY-MM-DD date.")


def _period(tenant, date_from: str | None = None,
            date_to: str | None = None) -> tuple[date, date]:
    end = _parse_date(date_to, "to") if date_to else date.today()
    start = _parse_date(date_from, "from") if date_from else _fiscal_start(tenant, end)
    if start > end:
        raise AnalyticsError("BAD_PERIOD", "The start date cannot be after the end date.")
    return start, end


def resolve_period(tenant, date_from: str | None = None,
                   date_to: str | None = None) -> dict:
    start, end = _period(tenant, date_from, date_to)
    return {"from": start.isoformat(), "to": end.isoformat()}


def _month_keys(start: date, end: date) -> list[str]:
    keys = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return keys


def _freshness(conn: sqlite3.Connection, tenant_id: str) -> dict:
    row = conn.execute(
        """SELECT COUNT(*) AS entries,
                  MAX(entry_date) AS last_entry_date,
                  MAX(posted_at) AS last_posted_at
           FROM journal_entry WHERE tenant_id=?""",
        (tenant_id,),
    ).fetchone()
    line_count = conn.execute(
        "SELECT COUNT(*) AS n FROM journal_line WHERE tenant_id=?", (tenant_id,)
    ).fetchone()["n"]
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "last_entry_date": row["last_entry_date"],
        "last_posted_at": row["last_posted_at"],
        "journal_entries": int(row["entries"] or 0),
        "journal_lines": int(line_count or 0),
    }


def _unbalanced_entries(conn: sqlite3.Connection, tenant_id: str) -> int:
    row = conn.execute(
        """SELECT COUNT(*) AS n FROM (
               SELECT entry_id
               FROM journal_line WHERE tenant_id=?
               GROUP BY entry_id
               HAVING SUM(debit_paise) != SUM(credit_paise)
           )""",
        (tenant_id,),
    ).fetchone()
    return int(row["n"] or 0)


def snapshot(conn: sqlite3.Connection, tenant: str | sqlite3.Row,
             date_from: str | None = None, date_to: str | None = None) -> dict:
    """Return the canonical actuals snapshot for one tenant and period."""
    tenant_id = _tenant_key(tenant)
    start, end = _period(tenant, date_from, date_to)
    dfrom, dto = start.isoformat(), end.isoformat()
    pnl = acct.profit_and_loss(conn, tenant_id, dfrom, dto)
    bs = acct.balance_sheet(conn, tenant_id, dto)
    tb = acct.trial_balance(conn, tenant_id, dto)
    gst = acct.gst_summary(conn, tenant_id, dfrom, dto)
    ar = acct.receivable_ageing(conn, tenant_id, dto)
    ap = acct.payable_ageing(conn, tenant_id, dto)
    dash = acct.dashboard(conn, tenant_id, dfrom, dto)

    metrics = {
        "revenue_paise": pnl["total_income"],
        "expense_paise": pnl["total_expense"],
        "net_profit_paise": pnl["net_profit"],
        "total_assets_paise": bs["total_assets"],
        "total_liabilities_paise": bs["total_liabilities"],
        "total_equity_paise": bs["total_equity"],
        "cash_and_bank_paise": dash["cash"],
        "receivable_paise": dash["receivable"],
        "payable_paise": dash["payable"],
        "inventory_paise": dash["inventory"],
        "open_invoices": dash["open_invoices"],
        "open_bills": dash["open_bills"],
        "overdue_receivable_paise": dash["overdue_receivable"],
        "overdue_payable_paise": dash["overdue_payable"],
        "gst_output_paise": gst["output_total"],
        "gst_input_paise": gst["input_total"],
        "gst_net_payable_paise": gst["net_payable"],
        "trial_balance_balanced": bool(tb["balanced"]),
        "balance_sheet_balanced": bool(bs["balanced"]),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "period": {"from": dfrom, "to": dto},
        "as_of": dto,
        "metrics": metrics,
        "checks": {
            "trial_balance_balanced": bool(tb["balanced"]),
            "trial_balance_difference_paise": tb["total_debit"] - tb["total_credit"],
            "balance_sheet_balanced": bool(bs["balanced"]),
            "balance_sheet_difference_paise": bs["difference"],
            "unbalanced_entries": _unbalanced_entries(conn, tenant_id),
        },
        "gst": {
            "output_paise": gst["output_total"],
            "input_paise": gst["input_total"],
            "net_payable_paise": gst["net_payable"],
            "note": "GST figures are working aids, not filed returns or claimed ITC.",
        },
        "ageing": {
            "receivable": {"totals": ar["totals"], "grand_total_paise": ar["grand_total"]},
            "payable": {"totals": ap["totals"], "grand_total_paise": ap["grand_total"]},
        },
        "freshness": _freshness(conn, tenant_id),
        "notes": [
            "Actuals only; this schema version contains no estimates or forecasts.",
            "Every amount is integer paise derived from posted journal lines.",
            "Empty periods return zero values and empty lists, never invented data.",
        ],
    }


def monthly_series(conn: sqlite3.Connection, tenant: str | sqlite3.Row,
                   date_from: str | None = None, date_to: str | None = None) -> dict:
    """Monthly revenue, expense and profit actuals with zero-filled gaps."""
    tenant_id = _tenant_key(tenant)
    start, end = _period(tenant, date_from, date_to)
    rows = conn.execute(
        """SELECT period_month,
                  COALESCE(SUM(income_paise), 0) AS revenue,
                  COALESCE(SUM(expense_paise), 0) AS expense
           FROM v_analytics_monthly
           WHERE tenant_id=? AND period_month BETWEEN ? AND ?
           GROUP BY period_month ORDER BY period_month""",
        (tenant_id, start.isoformat()[:7], end.isoformat()[:7]),
    ).fetchall()
    by_month = {r["period_month"]: r for r in rows}
    months = []
    for key in _month_keys(start, end):
        row = by_month.get(key)
        revenue = int(row["revenue"] or 0) if row else 0
        expense = int(row["expense"] or 0) if row else 0
        months.append({"month": key, "revenue_paise": revenue,
                       "expense_paise": expense, "profit_paise": revenue - expense})
    return {
        "from": start.isoformat(), "to": end.isoformat(), "months": months,
        "total_revenue_paise": sum(m["revenue_paise"] for m in months),
        "total_expense_paise": sum(m["expense_paise"] for m in months),
        "total_profit_paise": sum(m["profit_paise"] for m in months),
        "note": "Monthly actuals from posted journal lines; missing months are zero, not estimates.",
    }


def expense_breakdown(conn: sqlite3.Connection, tenant: str | sqlite3.Row,
                      date_from: str | None = None, date_to: str | None = None,
                      limit: int = 10) -> dict:
    tenant_id = _tenant_key(tenant)
    start, end = _period(tenant, date_from, date_to)
    rows = conn.execute(
        """SELECT account_id, account_code, account_name,
                  SUM(signed_paise) AS amount_paise
           FROM v_analytics_journal
           WHERE tenant_id=? AND account_type='expense'
             AND entry_date BETWEEN ? AND ?
           GROUP BY account_id, account_code, account_name
           HAVING SUM(signed_paise) > 0
           ORDER BY amount_paise DESC, account_code""",
        (tenant_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    total = sum(int(r["amount_paise"] or 0) for r in rows)
    keep = max(1, min(int(limit or 10), 100))
    shown = [{"account_id": r["account_id"], "code": r["account_code"],
              "name": r["account_name"], "amount_paise": int(r["amount_paise"] or 0)}
             for r in rows[:keep]]
    return {
        "from": start.isoformat(), "to": end.isoformat(),
        "total_paise": total, "rows": shown,
        "other_paise": total - sum(r["amount_paise"] for r in shown),
        "note": "Expense accounts only; negative or net-credit expense balances are excluded.",
    }


def top_customers(conn: sqlite3.Connection, tenant: str | sqlite3.Row,
                  date_from: str | None = None, date_to: str | None = None,
                  limit: int = 5) -> list[dict]:
    tenant_id = _tenant_key(tenant)
    start, end = _period(tenant, date_from, date_to)
    keep = max(1, min(int(limit or 5), 50))
    rows = conn.execute(
        """SELECT c.id AS party_id, c.name,
                  COUNT(i.id) AS documents,
                  COALESCE(SUM(i.total_paise), 0) AS amount_paise
           FROM invoice i
           JOIN customer c ON c.id=i.customer_id AND c.tenant_id=i.tenant_id
           WHERE i.tenant_id=? AND i.status='posted'
             AND i.invoice_date BETWEEN ? AND ?
           GROUP BY c.id, c.name
           ORDER BY amount_paise DESC, c.name LIMIT ?""",
        (tenant_id, start.isoformat(), end.isoformat(), keep),
    ).fetchall()
    return [dict(r) for r in rows]


def top_vendors(conn: sqlite3.Connection, tenant: str | sqlite3.Row,
                date_from: str | None = None, date_to: str | None = None,
                limit: int = 5) -> list[dict]:
    tenant_id = _tenant_key(tenant)
    start, end = _period(tenant, date_from, date_to)
    keep = max(1, min(int(limit or 5), 50))
    rows = conn.execute(
        """SELECT v.id AS party_id, v.name,
                  COUNT(b.id) AS documents,
                  COALESCE(SUM(b.total_paise), 0) AS amount_paise
           FROM bill b
           JOIN vendor v ON v.id=b.vendor_id AND v.tenant_id=b.tenant_id
           WHERE b.tenant_id=? AND b.status='posted'
             AND b.bill_date BETWEEN ? AND ?
           GROUP BY v.id, v.name
           ORDER BY amount_paise DESC, v.name LIMIT ?""",
        (tenant_id, start.isoformat(), end.isoformat(), keep),
    ).fetchall()
    return [dict(r) for r in rows]


def overview(conn: sqlite3.Connection, tenant: str | sqlite3.Row,
             date_from: str | None = None, date_to: str | None = None) -> dict:
    """One read-only payload for the UI, Excel and Power BI adapters."""
    start, end = _period(tenant, date_from, date_to)
    base = snapshot(conn, tenant, start.isoformat(), end.isoformat())
    return {
        **base,
        "monthly": monthly_series(conn, tenant, start.isoformat(), end.isoformat()),
        "expense_breakdown": expense_breakdown(
            conn, tenant, start.isoformat(), end.isoformat()),
        "top_customers": top_customers(conn, tenant, start.isoformat(), end.isoformat()),
        "top_vendors": top_vendors(conn, tenant, start.isoformat(), end.isoformat()),
    }
