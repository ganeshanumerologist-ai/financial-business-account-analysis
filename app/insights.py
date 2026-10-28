"""Grounded, deterministic insight layer.

This module is the honest bridge to the planned AI layer. It produces plain
observations from the actuals contract, with a written basis and metric keys.
It never calls an external model, never invents a number and never produces a
forecast. A future provider may turn these grounded observations into prose, but
the provider will not be allowed to calculate authoritative totals.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import analytics, money

SCHEMA_VERSION = "1.0"
ENGINE = "deterministic_rules_v1"


class InsightError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _bp(amount: int, total: int) -> int | None:
    """Return basis points (1/100 of a percent) without binary-float money."""
    if not total:
        return None
    return int(round((int(amount) * 10000) / int(total)))


def _pct_text(bp: int | None) -> str:
    if bp is None:
        return "not available"
    return f"{bp / 100:.2f}%"


def _observation(key: str, label: str, text: str, *, unit: str,
                 value_paise: int | None = None,
                 value_count: int | None = None,
                 value_bp: int | None = None,
                 value_text: str = "",
                 basis: str = "",
                 metric_keys: tuple[str, ...] = (),
                 drilldown: str = "") -> dict:
    return {
        "key": key,
        "label": label,
        "text": text,
        "kind": "actual",
        "unit": unit,
        "value_paise": value_paise,
        "value_count": value_count,
        "value_bp": value_bp,
        "value_text": value_text,
        "basis": basis,
        "metric_keys": list(metric_keys),
        "drilldown": drilldown,
        "source": "posted journal lines and deterministic reports",
    }


def grounded(conn: sqlite3.Connection, tenant,
             date_from: str | None = None,
             date_to: str | None = None) -> dict:
    """Return actual-only grounded observations for one tenant and period."""
    data = analytics.overview(conn, tenant, date_from, date_to)
    m = data["metrics"]
    revenue = int(m["revenue_paise"] or 0)
    expenses = int(m["expense_paise"] or 0)
    profit = int(m["net_profit_paise"] or 0)
    observations: list[dict] = []

    if revenue:
        margin_bp = _bp(profit, revenue)
        observations.append(_observation(
            "net_profit_margin",
            "Net profit margin",
            f"Net profit is {money.fmt(profit)} on revenue of {money.fmt(revenue)} "
            f"({_pct_text(margin_bp)}).",
            unit="basis_points",
            value_bp=margin_bp,
            value_text=_pct_text(margin_bp),
            basis="net_profit_paise / revenue_paise",
            metric_keys=("net_profit_paise", "revenue_paise"),
            drilldown="/reports/pnl",
        ))
    else:
        observations.append(_observation(
            "net_profit_margin",
            "Net profit margin",
            "No revenue actuals are posted in this period, so no margin is calculated.",
            unit="basis_points",
            value_text="not generated",
            basis="revenue_paise is zero; division is deliberately skipped",
            metric_keys=("revenue_paise", "net_profit_paise"),
            drilldown="/reports/pnl",
        ))

    observations.append(_observation(
        "revenue_minus_expenses",
        "Revenue minus expenses",
        f"Revenue {money.fmt(revenue)} minus expenses {money.fmt(expenses)} equals "
        f"net profit {money.fmt(profit)}.",
        unit="INR paise",
        value_paise=profit,
        value_text=money.fmt(profit),
        basis="revenue_paise - expense_paise",
        metric_keys=("revenue_paise", "expense_paise", "net_profit_paise"),
        drilldown="/reports/pnl",
    ))

    breakdown = data["expense_breakdown"]
    if breakdown["rows"]:
        top = breakdown["rows"][0]
        share = _bp(int(top["amount_paise"]), int(breakdown["total_paise"]))
        observations.append(_observation(
            "largest_expense_ledger",
            "Largest expense ledger",
            f'{top["code"]} {top["name"]} is the largest expense ledger at '
            f'{money.fmt(top["amount_paise"])} ({_pct_text(share)} of expenses).',
            unit="INR paise",
            value_paise=int(top["amount_paise"]),
            value_bp=share,
            value_text=_pct_text(share),
            basis="expense_breakdown amount_paise / total_paise",
            metric_keys=("expense_paise",),
            drilldown="/reports/pnl",
        ))
    else:
        observations.append(_observation(
            "largest_expense_ledger",
            "Largest expense ledger",
            "No expense actuals are posted in this period.",
            unit="INR paise",
            value_paise=0,
            value_text="not generated",
            basis="expense_breakdown is empty",
            metric_keys=("expense_paise",),
            drilldown="/reports/pnl",
        ))

    receivable = int(m["receivable_paise"] or 0)
    overdue = int(m["overdue_receivable_paise"] or 0)
    if receivable:
        overdue_bp = _bp(overdue, receivable)
        observations.append(_observation(
            "overdue_receivable_share",
            "Overdue receivable (60+ days)",
            f"{money.fmt(overdue)} is overdue out of {money.fmt(receivable)} receivable "
            f"({_pct_text(overdue_bp)}).",
            unit="INR paise",
            value_paise=overdue,
            value_bp=overdue_bp,
            value_text=_pct_text(overdue_bp),
            basis="overdue_receivable_paise / receivable_paise",
            metric_keys=("overdue_receivable_paise", "receivable_paise"),
            drilldown="/reports/ar-ageing",
        ))
    else:
        observations.append(_observation(
            "overdue_receivable_share",
            "Overdue receivable (60+ days)",
            "No receivable balance is open at the period end.",
            unit="INR paise",
            value_paise=0,
            value_text="not generated",
            basis="receivable_paise is zero",
            metric_keys=("overdue_receivable_paise", "receivable_paise"),
            drilldown="/reports/ar-ageing",
        ))

    observations.append(_observation(
        "gst_net_payable",
        "GST net payable",
        f"GST output minus input is {money.fmt(m['gst_net_payable_paise'])}. "
        "This is a working aid, not a filed return or claimed ITC.",
        unit="INR paise",
        value_paise=int(m["gst_net_payable_paise"] or 0),
        value_text=money.fmt(m["gst_net_payable_paise"]),
        basis="gst_output_paise - gst_input_paise",
        metric_keys=("gst_output_paise", "gst_input_paise", "gst_net_payable_paise"),
        drilldown="/reports/gst",
    ))

    observations.append(_observation(
        "journal_checks",
        "Ledger checks",
        "Trial balance is "
        + ("balanced" if m["trial_balance_balanced"] else "out of balance")
        + "; the balance sheet "
        + ("satisfies A = L + E" if m["balance_sheet_balanced"] else "does not satisfy A = L + E")
        + f"; {data['checks']['unbalanced_entries']} unbalanced journal entry(ies) were found.",
        unit="boolean",
        value_text=("ok" if (m["trial_balance_balanced"] and m["balance_sheet_balanced"]
                             and data["checks"]["unbalanced_entries"] == 0) else "review"),
        basis="trial_balance and balance_sheet checks plus unbalanced_entries count",
        metric_keys=("trial_balance_balanced", "balance_sheet_balanced"),
        drilldown="/reports/trial-balance",
    ))

    observations.append(_observation(
        "open_documents",
        "Open documents",
        f"{m['open_invoices']} invoice(s) and {m['open_bills']} bill(s) are open at the "
        f"period end. Receivable is {money.fmt(m['receivable_paise'])} and payable is "
        f"{money.fmt(m['payable_paise'])}.",
        unit="count",
        value_count=int(m["open_invoices"] or 0) + int(m["open_bills"] or 0),
        value_text=f"{m['open_invoices']} invoices / {m['open_bills']} bills",
        basis="open_invoices + open_bills from receivable_ageing and payable_ageing",
        metric_keys=("open_invoices", "open_bills", "receivable_paise", "payable_paise"),
        drilldown="/reports/ar-ageing",
    ))

    observations.append(_observation(
        "freshness",
        "Data freshness",
        f"{data['freshness']['journal_entries']} journal entries and "
        f"{data['freshness']['journal_lines']} lines are in the books; the last entry date is "
        f"{data['freshness']['last_entry_date'] or 'none'}.",
        unit="count",
        value_count=int(data["freshness"]["journal_entries"] or 0),
        value_text=f"{data['freshness']['journal_entries']} entries",
        basis="journal_entry and journal_line counts",
        metric_keys=(),
        drilldown="/reports/analytics",
    ))

    summary = (
        f"Actuals from {data['period']['from']} to {data['period']['to']}: "
        f"revenue {money.fmt(revenue)}, expenses {money.fmt(expenses)}, "
        f"net profit {money.fmt(profit)}. "
        + ("No revenue actuals are posted in this period. " if not revenue else "")
        + "This is a grounded summary; it is not a forecast and no external model was called."
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "engine": ENGINE,
        "generative_ai": False,
        "provider": None,
        "actuals_only": True,
        "forecast_included": False,
        "period": data["period"],
        "as_of": data["as_of"],
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "summary": summary,
        "observations": observations,
        "checks": data["checks"],
        "freshness": data["freshness"],
        "notes": [
            "Every observation is derived from posted journal lines and existing deterministic reports.",
            "The engine is rule-based, not generative AI. No external provider is configured or called.",
            "No estimate or forecast is included. Empty periods produce explicit 'not generated' text.",
            "A future AI provider may rewrite these observations, but it may not calculate authoritative totals.",
        ],
    }
