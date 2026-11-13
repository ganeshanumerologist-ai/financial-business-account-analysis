"""Power BI-style visual gallery built only from posted actuals.

This module is a presentation layer, not a second accounting engine. Every
series is derived from the same deterministic analytics/report functions used
by the web pages, Excel workbook and static Power BI pack. It renders with the
vendored ECharts library; it does **not** create a ``.pbix``, execute R/Python,
call Azure Maps or claim to be a Power BI Service report.

Empty actuals stay empty. No chart invents a zero, a forecast or a smoothed
point.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from . import accounting as acct
from . import analytics
from . import budgeting
from . import i18n
from . import insights as insights_mod

# GST state codes are the stable source value in customer/vendor records. The
# names match the bundled India state GeoJSON so map series join without a
# second lookup table.
STATE_NAMES = {
    "01": "Jammu & Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman & Nicobar",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}

MAP_NAME = "arthivio-india"
MAP_URL = "/static/india_states.geojson"
MAP_SOURCE_NOTE = (
    "Offline India state map bundled with ARTHIVIO. State totals come from "
    "posted invoices by customer GST state code; blank or unmapped codes are "
    "listed below the chart."
)


def _money(value) -> float:
    """Convert integer paise to display rupees without changing the source."""
    return round(int(value or 0) / 100, 2)


def _t(lang: str, key: str) -> str:
    return i18n.t(lang, key)


def _empty(message: str) -> dict:
    return {"empty": True, "message": message}


def _months(conn, tenant, dfrom: str, dto: str) -> list[dict]:
    return analytics.monthly_series(conn, tenant, dfrom, dto)["months"]


def _state_sales(conn: sqlite3.Connection, tenant_id: str,
                 dfrom: str, dto: str) -> list[dict]:
    rows = conn.execute(
        """SELECT COALESCE(NULLIF(c.state_code, ''), '') AS state_code,
                  COALESCE(SUM(i.total_paise), 0) AS amount_paise,
                  COUNT(*) AS invoices
           FROM invoice i
           JOIN customer c ON c.id=i.customer_id AND c.tenant_id=i.tenant_id
           WHERE i.tenant_id=? AND i.status='posted'
             AND i.invoice_date BETWEEN ? AND ?
           GROUP BY c.state_code
           ORDER BY amount_paise DESC""",
        (tenant_id, dfrom, dto),
    ).fetchall()
    out = []
    for row in rows:
        code = str(row["state_code"] or "")
        name = STATE_NAMES.get(code, "")
        out.append({"state_code": code, "state": name,
                    "amount_paise": int(row["amount_paise"] or 0),
                    "invoices": int(row["invoices"] or 0)})
    return out


def _monthly_expense_matrix(conn: sqlite3.Connection, tenant_id: str,
                            months: list[dict], dfrom: str, dto: str,
                            lang: str, keep: int = 5) -> dict:
    """Expense accounts by month, top accounts plus an explicit remainder.

    Accounts whose net period total is zero or negative are excluded, matching
    the analytics expense-breakdown contract. A month can still carry a negative
    net for an included account when a reversal exceeds that month's expense;
    the caller does not draw a 100% view when that happens.
    """
    labels = [m["month"] for m in months]
    rows = conn.execute(
        """SELECT substr(e.entry_date, 1, 7) AS period,
                  a.id AS account_id, a.code, a.name,
                  COALESCE(SUM(l.debit_paise - l.credit_paise), 0) AS amount_paise
           FROM journal_line l
           JOIN journal_entry e ON e.id=l.entry_id AND e.tenant_id=l.tenant_id
           JOIN account a ON a.id=l.account_id AND a.tenant_id=l.tenant_id
           WHERE l.tenant_id=? AND a.type='expense'
             AND e.entry_date BETWEEN ? AND ?
           GROUP BY period, a.id
           ORDER BY period, amount_paise DESC""",
        (tenant_id, dfrom, dto),
    ).fetchall()
    by_account: dict[str, dict] = {}
    by_period: dict[str, dict[str, int]] = {}
    for row in rows:
        key = row["account_id"]
        amount = int(row["amount_paise"] or 0)
        item = by_account.setdefault(key, {
            "code": row["code"], "name": row["name"], "total": 0})
        item["total"] += amount
        by_period.setdefault(key, {})[row["period"]] = amount
    top = [pair for pair in sorted(
        by_account.items(), key=lambda pair: pair[1]["total"], reverse=True)
        if pair[1]["total"] > 0][:max(1, keep)]
    top_ids = {key for key, _ in top}
    series = []
    for key, item in top:
        values = [round(by_period.get(key, {}).get(label, 0) / 100, 2)
                  for label in labels]
        series.append({"name": f'{item["code"]} {item["name"]}', "data": values})
    other_values = []
    for label in labels:
        total = 0
        for key, _item in by_account.items():
            if key not in top_ids:
                total += by_period.get(key, {}).get(label, 0)
        other_values.append(round(total / 100, 2))
    if any(other_values):
        series.append({"name": _t(lang, "Other expense ledgers"),
                       "data": other_values})
    return {
        "labels": labels,
        "series": series,
        "non_negative": all(value >= 0 for item in series
                            for value in item["data"]),
    }


def _expense_drivers(conn: sqlite3.Connection, tenant_id: str,
                     dfrom: str, dto: str, limit: int = 7) -> dict:
    """Current vs previous equal-length period by expense account."""
    start = date.fromisoformat(dfrom)
    end = date.fromisoformat(dto)
    days = max(1, (end - start).days + 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    rows = conn.execute(
        """SELECT a.id AS account_id, a.code, a.name,
                  COALESCE(SUM(CASE WHEN e.entry_date BETWEEN ? AND ?
                                    THEN l.debit_paise - l.credit_paise ELSE 0 END), 0)
                      AS current_paise,
                  COALESCE(SUM(CASE WHEN e.entry_date BETWEEN ? AND ?
                                    THEN l.debit_paise - l.credit_paise ELSE 0 END), 0)
                      AS previous_paise
           FROM account a
           JOIN journal_line l ON l.account_id=a.id AND l.tenant_id=a.tenant_id
           JOIN journal_entry e ON e.id=l.entry_id AND e.tenant_id=l.tenant_id
           WHERE a.tenant_id=? AND a.type='expense'
             AND e.entry_date BETWEEN ? AND ?
           GROUP BY a.id, a.code, a.name
           HAVING current_paise != 0 OR previous_paise != 0
           ORDER BY ABS(current_paise - previous_paise) DESC
           LIMIT ?""",
        (dfrom, dto, prev_start.isoformat(), prev_end.isoformat(),
         tenant_id, prev_start.isoformat(), dto, max(1, limit)),
    ).fetchall()
    items = []
    for row in rows:
        current = int(row["current_paise"] or 0)
        previous = int(row["previous_paise"] or 0)
        items.append({
            "code": row["code"], "name": row["name"],
            "current_paise": current, "previous_paise": previous,
            "change_paise": current - previous,
        })
    return {"from": prev_start.isoformat(), "to": prev_end.isoformat(),
            "current_from": dfrom, "current_to": dto, "items": items}


def _account_mix(conn: sqlite3.Connection, tenant_id: str, as_of: str) -> dict:
    bs = acct.balance_sheet(conn, tenant_id, as_of)
    return {
        "assets": int(bs["total_assets"]),
        "liabilities": int(bs["total_liabilities"]),
        "equity": int(bs["total_equity"]),
        "retained_earnings": int(bs["retained_earnings"]),
        "balanced": bool(bs["balanced"]),
    }


EXPECTED_VISUALS = {
    "comparison": (
        "clustered-column", "clustered-bar", "stacked-column", "stacked-bar",
        "100-stacked-column", "100-stacked-bar",
    ),
    "trend": (
        "line", "area", "stacked-area", "100-stacked-area",
        "line-stacked-column", "waterfall",
    ),
    "part": ("funnel", "pie", "donut", "treemap"),
    "dist": ("scatter", "map", "filled-map", "shape-map"),
    "advanced": (
        "key-influencers", "decomposition-tree", "smart-narrative", "goals",
        "paginated-report", "r-python", "azure-map",
    ),
}

VISUAL_TITLES = {
    "clustered-column": "Clustered column",
    "clustered-bar": "Clustered bar",
    "stacked-column": "Stacked column",
    "stacked-bar": "Stacked bar",
    "100-stacked-column": "100% stacked column",
    "100-stacked-bar": "100% stacked bar",
    "line": "Line chart",
    "area": "Area chart",
    "stacked-area": "Stacked area",
    "100-stacked-area": "100% stacked area",
    "line-stacked-column": "Line and stacked column",
    "waterfall": "Waterfall (ribbon-style)",
    "funnel": "Funnel",
    "pie": "Pie",
    "donut": "Donut",
    "treemap": "Treemap",
    "scatter": "Scatter",
    "map": "Map",
    "filled-map": "Filled map",
    "shape-map": "Shape map",
    "key-influencers": "Key influencers",
    "decomposition-tree": "Decomposition tree",
    "smart-narrative": "Smart narrative",
    "goals": "Goals",
    "paginated-report": "Paginated report",
    "r-python": "R / Python script visuals",
    "azure-map": "Azure Maps",
}

EMPTY_NOTES = {
    "goals": "No stored monthly budgets for this period. Set a budget to use this visual.",
    "100-stacked-column": (
        "Not drawn because a month has a net negative expense actual. "
        "The stacked column still shows the signed actuals."),
    "100-stacked-bar": "No posted customer sales in this period.",
    "map": "No posted invoice state codes in this period.",
    "filled-map": "No posted invoice state codes in this period.",
    "shape-map": "No posted invoice state codes in this period.",
}


def _empty_card(key: str, title: str, note: str, group: str) -> dict:
    return {"id": f"vis-{key}", "key": key, "title": title, "note": note,
            "kind": "empty", "group": group}


def _chart_card(key: str, title: str, note: str, option: dict,
                height: int = 300, fmt: str = "money",
                group: str = "comparison") -> dict:
    return {
        "id": f"vis-{key}",
        "key": key,
        "title": title,
        "note": note,
        "option": option,
        "height": height,
        "format": fmt,
        "group": group,
    }


def _axis_grid() -> dict:
    return {"left": 64, "right": 24, "top": 44, "bottom": 38,
            "containLabel": True}


def _legend() -> dict:
    return {"top": 0, "type": "scroll"}


def _tooltip_axis() -> dict:
    return {"trigger": "axis"}


def _tooltip_item() -> dict:
    return {"trigger": "item"}


def _bar_series(name: str, data: list, **extra) -> dict:
    return {"name": name, "type": "bar", "data": data, **extra}


def _line_series(name: str, data: list, **extra) -> dict:
    return {"name": name, "type": "line", "smooth": True, "symbolSize": 6,
            "data": data, **extra}


def _percent_series(series: list[dict], labels: list[str]) -> list[dict]:
    """Normalise each label across series to 100 without changing totals."""
    out = [{"name": item["name"], "data": [0.0] * len(labels)}
           for item in series]
    for index, _label in enumerate(labels):
        total = sum(float(item["data"][index] or 0) for item in series)
        for pos, item in enumerate(series):
            value = float(item["data"][index] or 0)
            out[pos]["data"][index] = round((value / total) * 100, 1) if total else 0.0
    return out


def _monthly_payload(conn, tenant, dfrom: str, dto: str) -> dict:
    months = _months(conn, tenant, dfrom, dto)
    return {
        "months": months,
        "labels": [m["month"] for m in months],
        "revenue": [_money(m["revenue_paise"]) for m in months],
        "expense": [_money(m["expense_paise"]) for m in months],
        "profit": [_money(m["profit_paise"]) for m in months],
    }


def _expense_payload(conn, tenant, dfrom: str, dto: str, lang: str) -> dict:
    data = analytics.expense_breakdown(conn, tenant, dfrom, dto)
    labels = [f'{r["code"]} {r["name"]}' for r in data["rows"]]
    values = [_money(r["amount_paise"]) for r in data["rows"]]
    other = int(data["other_paise"] or 0)
    if other:
        labels.append(_t(lang, "Other expense ledgers"))
        values.append(_money(other))
    return {"labels": labels, "values": values,
            "total_paise": int(data["total_paise"] or 0)}


def _top_payload(rows: list[dict]) -> dict:
    return {
        "labels": [r["name"] for r in rows],
        "values": [_money(r["amount_paise"]) for r in rows],
        "documents": [int(r["documents"] or 0) for r in rows],
    }


def _state_payload(rows: list[dict]) -> dict:
    mapped = [r for r in rows if r["state"]]
    unmapped = [r for r in rows if not r["state"]]
    return {
        "data": [{"name": r["state"], "value": _money(r["amount_paise"])}
                 for r in mapped],
        "unmapped": [{"state_code": r["state_code"] or "blank",
                      "amount": _money(r["amount_paise"]),
                      "invoices": r["invoices"]} for r in unmapped],
        "total": sum(_money(r["amount_paise"]) for r in rows),
    }


def _map_option(data: list[dict], *, filled: bool, shape: bool) -> dict:
    option = {
        "tooltip": _tooltip_item(),
        "series": [{
            "type": "map",
            "map": MAP_NAME,
            "roam": shape,
            "data": data,
            "label": {"show": shape, "fontSize": 9},
            "emphasis": {"label": {"show": True}},
            "itemStyle": {"borderColor": "#FFFFFF", "borderWidth": 0.7},
        }],
    }
    if filled:
        values = [float(item["value"]) for item in data if item.get("value")]
        top = max(values) if values else 1
        option["visualMap"] = {
            "min": 0, "max": top, "left": 8, "bottom": 8,
            "calculable": False, "itemHeight": 100, "itemWidth": 12,
            "text": ["High", "Low"], "textStyle": {"fontSize": 10},
            "inRange": {"color": ["#DBEAFE", "#93C5FD", "#2563EB", "#0C3157"]},
        }
    return option


def _narrative(conn, tenant, dfrom: str, dto: str) -> dict:
    payload = insights_mod.grounded(conn, tenant, dfrom, dto)
    return {
        "summary": payload.get("summary", ""),
        "observations": payload.get("observations", [])[:4],
        "actuals_only": bool(payload.get("actuals_only")),
        "generative_ai": bool(payload.get("generative_ai")),
        "forecast_included": bool(payload.get("forecast_included")),
    }


def _goal_payload(conn, tenant, dfrom: str, dto: str, lang: str) -> dict | None:
    try:
        data = budgeting.budget_vs_actual(conn, tenant, dfrom, dto)
    except Exception:
        return None
    totals = data["totals"]
    if not totals.get("budgeted_accounts"):
        return None
    return {
        "labels": [_t(lang, "Income"), _t(lang, "Expenses")],
        "budget": [_money(totals["income_budget"]), _money(totals["expense_budget"])],
        "actual": [_money(totals["income_actual"]), _money(totals["expense_actual"])],
        "budgeted_accounts": int(totals["budgeted_accounts"]),
        "unbudgeted_accounts": int(totals["unbudgeted_accounts"]),
    }


def gallery(conn: sqlite3.Connection, tenant, dfrom: str, dto: str,
            lang: str = "en") -> dict:
    """Build the complete visual-gallery payload for one tenant and period."""
    tenant_id = tenant["id"] if not isinstance(tenant, str) else tenant
    monthly = _monthly_payload(conn, tenant, dfrom, dto)
    expense = _expense_payload(conn, tenant, dfrom, dto, lang)
    customers = _top_payload(analytics.top_customers(
        conn, tenant, dfrom, dto, limit=7))
    vendors = _top_payload(analytics.top_vendors(
        conn, tenant, dfrom, dto, limit=7))
    states = _state_payload(_state_sales(conn, tenant_id, dfrom, dto))
    expense_matrix = _monthly_expense_matrix(
        conn, tenant_id, monthly["months"], dfrom, dto, lang)
    drivers = _expense_drivers(conn, tenant_id, dfrom, dto)
    ageing = acct.receivable_ageing(conn, tenant_id, dto)
    payable = acct.payable_ageing(conn, tenant_id, dto)
    gst = acct.gst_summary(conn, tenant_id, dfrom, dto)
    mix = _account_mix(conn, tenant_id, dto)
    goals = _goal_payload(conn, tenant, dfrom, dto, lang)
    narrative = _narrative(conn, tenant, dfrom, dto)

    labels = monthly["labels"]
    revenue = monthly["revenue"]
    expenses = monthly["expense"]
    profit = monthly["profit"]
    has_monthly = bool(labels) and (any(revenue) or any(expenses))
    has_expense = bool(expense["labels"]) and any(expense["values"])
    has_customers = bool(customers["labels"]) and any(customers["values"])
    has_vendors = bool(vendors["labels"]) and any(vendors["values"])
    has_states = bool(states["data"])
    has_drivers = bool(drivers["items"])

    groups: list[dict] = []

    # ---------------- comparison ----------------
    comparison: list[dict] = []
    if has_monthly:
        comparison.append(_chart_card(
            "clustered-column", _t(lang, "Clustered column"),
            _t(lang, "Monthly posted revenue and expenses side by side."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category", "data": labels},
                "yAxis": {"type": "value"},
                "series": [
                    _bar_series(_t(lang, "Revenue"), revenue, barMaxWidth=28),
                    _bar_series(_t(lang, "Expenses"), expenses, barMaxWidth=28),
                ],
            }, group="comparison"))
    if has_vendors:
        comparison.append(_chart_card(
            "clustered-bar", _t(lang, "Clustered bar"),
            _t(lang, "Top vendors by posted purchase value."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": {"left": 18, "right": 36, "top": 18, "bottom": 18,
                         "containLabel": True},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category", "data": list(reversed(vendors["labels"]))},
                "series": [_bar_series(_t(lang, "Purchases"),
                                       list(reversed(vendors["values"])),
                                       barMaxWidth=18)],
            }, group="comparison"))
    if expense_matrix["series"] and any(any(s["data"]) for s in expense_matrix["series"]):
        comparison.append(_chart_card(
            "stacked-column", _t(lang, "Stacked column"),
            _t(lang, "Monthly expense composition; top accounts plus an explicit remainder."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category", "data": expense_matrix["labels"]},
                "yAxis": {"type": "value"},
                "series": [_bar_series(s["name"], s["data"], stack="total",
                                       barMaxWidth=34)
                           for s in expense_matrix["series"]],
            }, group="comparison"))
    if has_drivers:
        driver_items = list(reversed(drivers["items"]))
        comparison.append(_chart_card(
            "stacked-bar", _t(lang, "Stacked bar"),
            _t(lang, "Expense accounts: current period and previous equal-length period."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": {"left": 18, "right": 36, "top": 28, "bottom": 18,
                         "containLabel": True},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category",
                          "data": [f'{i["code"]} {i["name"]}' for i in driver_items]},
                "series": [
                    _bar_series(_t(lang, "Current period"),
                                [_money(i["current_paise"]) for i in driver_items],
                                stack="period", barMaxWidth=18),
                    _bar_series(_t(lang, "Previous period"),
                                [_money(i["previous_paise"]) for i in driver_items],
                                stack="period", barMaxWidth=18),
                ],
            }, group="comparison"))
    if (expense_matrix["series"] and expense_matrix["non_negative"]
            and any(any(s["data"]) for s in expense_matrix["series"])):
        percent_series = _percent_series(expense_matrix["series"],
                                         expense_matrix["labels"])
        comparison.append(_chart_card(
            "100-stacked-column", _t(lang, "100% stacked column"),
            _t(lang, "Each month's expense mix normalised to 100%; tooltips show shares."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category", "data": expense_matrix["labels"]},
                "yAxis": {"type": "value", "max": 100},
                "series": [_bar_series(s["name"], s["data"], stack="total",
                                       barMaxWidth=34)
                           for s in percent_series],
            }, height=300, fmt="percent", group="comparison"))
    if has_customers:
        customer_total = sum(customers["values"]) or 1
        shares = [round(value / customer_total * 100, 1)
                  for value in customers["values"]]
        comparison.append(_chart_card(
            "100-stacked-bar", _t(lang, "100% stacked bar"),
            _t(lang, "Customer concentration: each customer's share of posted sales."),
            {
                "tooltip": _tooltip_item(), "legend": _legend(),
                "grid": {"left": 18, "right": 24, "top": 34, "bottom": 18,
                         "containLabel": True},
                "xAxis": {"type": "value", "max": 100},
                "yAxis": {"type": "category", "data": [_t(lang, "Revenue")]},
                "series": [
                    _bar_series(name, [share], stack="share", barMaxWidth=48)
                    for name, share in zip(customers["labels"], shares)
                ],
            }, height=260, fmt="percent", group="comparison"))

    groups.append({"key": "comparison",
                   "title": _t(lang, "Comparison"),
                   "note": _t(lang, "Compare posted actuals across time, parties and expense ledgers."),
                   "visuals": comparison})

    # ---------------- trend ----------------
    trend: list[dict] = []
    if has_monthly:
        trend.append(_chart_card(
            "line", _t(lang, "Line chart"),
            _t(lang, "Monthly posted revenue and net profit."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category", "data": labels},
                "yAxis": {"type": "value"},
                "series": [
                    _line_series(_t(lang, "Revenue"), revenue),
                    _line_series(_t(lang, "Profit"), profit),
                ],
            }, group="trend"))
        trend.append(_chart_card(
            "area", _t(lang, "Area chart"),
            _t(lang, "Monthly posted revenue as an area; no interpolation beyond the month."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category", "data": labels, "boundaryGap": False},
                "yAxis": {"type": "value"},
                "series": [{
                    "name": _t(lang, "Revenue"), "type": "line", "smooth": True,
                    "symbolSize": 6, "areaStyle": {}, "data": revenue,
                }],
            }, group="trend"))
        trend.append(_chart_card(
            "stacked-area", _t(lang, "Stacked area"),
            _t(lang, "Revenue and expenses stacked as posted monthly actuals."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category", "data": labels, "boundaryGap": False},
                "yAxis": {"type": "value"},
                "series": [
                    {"name": _t(lang, "Revenue"), "type": "line", "smooth": True,
                     "stack": "total", "areaStyle": {}, "data": revenue},
                    {"name": _t(lang, "Expenses"), "type": "line", "smooth": True,
                     "stack": "total", "areaStyle": {}, "data": expenses},
                ],
            }, group="trend"))
        percent_rev = _percent_series(
            [{"name": _t(lang, "Revenue"), "data": revenue},
             {"name": _t(lang, "Expenses"), "data": expenses}], labels)
        trend.append(_chart_card(
            "100-stacked-area", _t(lang, "100% stacked area"),
            _t(lang, "Revenue and expense share of each month; tooltips show percentages."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category", "data": labels, "boundaryGap": False},
                "yAxis": {"type": "value", "max": 100},
                "series": [
                    {"name": s["name"], "type": "line", "smooth": True,
                     "stack": "total", "areaStyle": {}, "data": s["data"]}
                    for s in percent_rev
                ],
            }, fmt="percent", group="trend"))
    if has_monthly and expense_matrix["series"] and any(
            any(s["data"]) for s in expense_matrix["series"]):
        trend.append(_chart_card(
            "line-stacked-column", _t(lang, "Line and stacked column"),
            _t(lang, "Stacked expense composition with the posted profit line."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category", "data": labels},
                "yAxis": [
                    {"type": "value", "name": _t(lang, "Expenses")},
                    {"type": "value", "name": _t(lang, "Profit")},
                ],
                "series": [
                    *[_bar_series(s["name"], s["data"], stack="total",
                                  barMaxWidth=34)
                      for s in expense_matrix["series"]],
                    _line_series(_t(lang, "Profit"), profit,
                                 yAxisIndex=1),
                ],
            }, group="trend"))
    if has_monthly:
        total_revenue = sum(revenue)
        total_expense = sum(expenses)
        total_profit = total_revenue - total_expense
        trend.append(_chart_card(
            "waterfall", _t(lang, "Waterfall (ribbon-style)"),
            _t(lang, "Revenue to expenses to net profit. No forecast or estimate is added."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category",
                          "data": [_t(lang, "Revenue"), _t(lang, "Expenses"),
                                   _t(lang, "Net profit")]},
                "yAxis": {"type": "value"},
                "series": [
                    {"name": _t(lang, "Base"), "type": "bar", "stack": "total",
                     "itemStyle": {"color": "transparent"}, "silent": True,
                     "data": [0, total_profit, 0]},
                    {"name": _t(lang, "Actual"), "type": "bar", "stack": "total",
                     "barMaxWidth": 54,
                     "label": {"show": True, "position": "top"},
                     "data": [
                         {"value": total_revenue, "itemStyle": {"color": "#2563EB"}},
                         {"value": total_expense, "itemStyle": {"color": "#D97706"}},
                         {"value": total_profit, "itemStyle": {"color": "#0F766E"}},
                     ]},
                ],
            }, group="trend"))

    groups.append({"key": "trend", "title": _t(lang, "Trend"),
                   "note": _t(lang, "Trend views use the same posted monthly actuals."),
                   "visuals": trend})

    # ---------------- part-to-whole ----------------
    part: list[dict] = []
    if has_expense:
        pie_data = [{"name": name, "value": value}
                    for name, value in zip(expense["labels"], expense["values"])]
        part.append(_chart_card(
            "funnel", _t(lang, "Funnel"),
            _t(lang, "Expense ledgers sorted by posted amount; the funnel is descriptive, not a target."),
            {
                "tooltip": _tooltip_item(), "legend": _legend(),
                "series": [{
                    "type": "funnel", "sort": "descending", "gap": 2,
                    "label": {"show": True, "position": "inside"},
                    "data": pie_data,
                }],
            }, group="part"))
        part.append(_chart_card(
            "pie", _t(lang, "Pie"),
            _t(lang, "Expense composition for the selected period."),
            {
                "tooltip": _tooltip_item(), "legend": _legend(),
                "series": [{
                    "type": "pie", "radius": "66%", "center": ["50%", "48%"],
                    "data": pie_data,
                }],
            }, group="part"))
        part.append(_chart_card(
            "donut", _t(lang, "Donut"),
            _t(lang, "Expense composition with the total in the centre."),
            {
                "tooltip": _tooltip_item(), "legend": _legend(),
                "series": [{
                    "type": "pie", "radius": ["46%", "70%"],
                    "center": ["50%", "48%"],
                    "label": {"show": True},
                    "data": pie_data,
                }],
            }, group="part"))
        part.append(_chart_card(
            "treemap", _t(lang, "Treemap"),
            _t(lang, "Expense ledgers sized by posted amount."),
            {
                "tooltip": _tooltip_item(),
                "series": [{
                    "type": "treemap", "roam": False, "nodeClick": False,
                    "breadcrumb": {"show": False},
                    "label": {"show": True, "fontSize": 11},
                    "data": pie_data,
                }],
            }, height=340, group="part"))

    groups.append({"key": "part", "title": _t(lang, "Part-to-whole"),
                   "note": _t(lang, "Composition views use posted expense actuals only."),
                   "visuals": part})

    # ---------------- distribution and geography ----------------
    dist: list[dict] = []
    if has_monthly:
        scatter_data = [
            {"name": label, "value": [rev, exp],
             "symbolSize": 14}
            for label, rev, exp in zip(labels, revenue, expenses)
        ]
        dist.append(_chart_card(
            "scatter", _t(lang, "Scatter"),
            _t(lang, "Each point is a month: x = posted revenue, y = posted expenses."),
            {
                "tooltip": _tooltip_item(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "value", "name": _t(lang, "Revenue")},
                "yAxis": {"type": "value", "name": _t(lang, "Expenses")},
                "series": [{
                    "name": _t(lang, "Months"), "type": "scatter",
                    "data": scatter_data,
                }],
            }, group="dist"))
    if has_states:
        dist.append(_chart_card(
            "map", _t(lang, "Map"),
            _t(lang, "Posted sales by customer GST state code. Blank codes are listed below."),
            _map_option(states["data"], filled=False, shape=False),
            height=360, group="dist"))
        dist.append(_chart_card(
            "filled-map", _t(lang, "Filled map"),
            _t(lang, "State sales shaded by posted invoice value."),
            _map_option(states["data"], filled=True, shape=False),
            height=360, group="dist"))
        dist.append(_chart_card(
            "shape-map", _t(lang, "Shape map"),
            _t(lang, "State shapes with labels and pan/zoom; same posted state totals."),
            _map_option(states["data"], filled=False, shape=True),
            height=360, group="dist"))
    groups.append({"key": "dist", "title": _t(lang, "Distribution & geography"),
                   "note": _t(lang, "Geography joins customer GST state codes to the bundled offline India map."),
                   "visuals": dist})

    # ---------------- advanced / Power BI extras ----------------
    advanced: list[dict] = []
    if has_drivers:
        driver_items = drivers["items"]
        advanced.append(_chart_card(
            "key-influencers", _t(lang, "Key influencers"),
            _t(lang, "Deterministic expense-change ranking versus the previous equal-length period. Not AI."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": {"left": 18, "right": 36, "top": 18, "bottom": 18,
                         "containLabel": True},
                "xAxis": {"type": "value"},
                "yAxis": {"type": "category",
                          "data": [f'{i["code"]} {i["name"]}'
                                   for i in reversed(driver_items)]},
                "series": [{
                    "name": _t(lang, "Change"),
                    "type": "bar", "barMaxWidth": 18,
                    "data": [{
                        "value": _money(i["change_paise"]),
                        "itemStyle": {"color": "#B91C1C" if i["change_paise"] > 0
                                      else "#0F766E"},
                    } for i in reversed(driver_items)],
                }],
            }, group="advanced"))
    if has_customers or has_expense:
        children = []
        if has_customers:
            children.append({
                "name": _t(lang, "Revenue"),
                "children": [{"name": name, "value": value}
                             for name, value in zip(customers["labels"],
                                                    customers["values"])],
            })
        if has_expense:
            children.append({
                "name": _t(lang, "Expenses"),
                "children": [{"name": name, "value": value}
                             for name, value in zip(expense["labels"],
                                                    expense["values"])],
            })
        advanced.append(_chart_card(
            "decomposition-tree", _t(lang, "Decomposition tree"),
            _t(lang, "Expand revenue and expense branches to the posted document/category level."),
            {
                "tooltip": _tooltip_item(),
                "series": [{
                    "type": "tree", "layout": "orthogonal", "orient": "LR",
                    "roam": True, "expandAndCollapse": True,
                    "initialTreeDepth": 2, "symbolSize": 8,
                    "label": {"position": "left", "verticalAlign": "middle",
                              "align": "right", "fontSize": 10},
                    "leaves": {"label": {"position": "right", "align": "left"}},
                    "data": [{"name": _t(lang, "Business"), "children": children}],
                }],
            }, height=420, group="advanced"))
    if goals:
        advanced.append(_chart_card(
            "goals", _t(lang, "Goals"),
            _t(lang, "Stored monthly budgets versus posted actuals. No forecast is shown."),
            {
                "tooltip": _tooltip_axis(), "legend": _legend(),
                "grid": _axis_grid(),
                "xAxis": {"type": "category", "data": goals["labels"]},
                "yAxis": {"type": "value"},
                "series": [
                    _bar_series(_t(lang, "Budget"), goals["budget"], barMaxWidth=30),
                    _bar_series(_t(lang, "Actual"), goals["actual"], barMaxWidth=30),
                ],
            }, group="advanced"))
    if narrative["observations"] or narrative["summary"]:
        advanced.append({
            "id": "vis-smart-narrative", "key": "smart-narrative",
            "title": _t(lang, "Smart narrative"),
            "note": _t(lang, "Grounded deterministic observations; no external model was called."),
            "kind": "narrative", "group": "advanced",
        })
    advanced.append({
        "id": "vis-paginated-report", "key": "paginated-report",
        "title": _t(lang, "Paginated report"),
        "note": _t(lang, "Printable report links with the same posted actuals."),
        "kind": "links", "group": "advanced",
    })
    advanced.append({
        "id": "vis-r-python", "key": "r-python",
        "title": _t(lang, "R / Python script visuals"),
        "note": _t(lang, "Native R and Python visuals need Power BI Desktop plus an R/Python runtime. ARTHIVIO does not execute scripts in this page."),
        "kind": "status", "group": "advanced",
    })
    advanced.append({
        "id": "vis-azure-map", "key": "azure-map",
        "title": _t(lang, "Azure Maps"),
        "note": _t(lang, "Azure Maps needs an Azure subscription key. The offline state map above uses the same posted state totals."),
        "kind": "status", "group": "advanced",
    })
    groups.append({"key": "advanced", "title": _t(lang, "Advanced & Power BI extras"),
                   "note": _t(lang, "Implemented where the local stack can stay deterministic and offline; native-only visuals are labelled honestly."),
                   "visuals": advanced})

    # Keep the full visual catalogue visible even when a period has no rows for
    # a particular shape. Empty cards explain the absence; they never draw a
    # zero series or hide the fact that a visual type exists.
    by_key = {group["key"]: group for group in groups}
    for group_key, expected in EXPECTED_VISUALS.items():
        group = by_key[group_key]
        present = {visual["key"] for visual in group["visuals"]}
        for key in expected:
            if key in present:
                continue
            note_key = EMPTY_NOTES.get(key, "No posted actuals for this visual in the selected period.")
            group["visuals"].append(_empty_card(
                key, _t(lang, VISUAL_TITLES[key]), _t(lang, note_key), group_key))

    return {
        "period": {"from": dfrom, "to": dto},
        "totals": {
            "revenue_paise": sum(int(m["revenue_paise"]) for m in monthly["months"]),
            "expense_paise": sum(int(m["expense_paise"]) for m in monthly["months"]),
            "profit_paise": sum(int(m["profit_paise"]) for m in monthly["months"]),
        },
        "groups": groups,
        "narrative": narrative,
        "goals": goals,
        "map": {"name": MAP_NAME, "url": MAP_URL},
        "map_note": MAP_SOURCE_NOTE,
        "unmapped_states": states["unmapped"],
        "account_mix": mix,
        "ageing": {"receivable": ageing["totals"],
                   "payable": payable["totals"],
                   "receivable_total": ageing["grand_total"],
                   "payable_total": payable["grand_total"]},
        "gst": {"output": int(gst["output_total"] or 0),
                "input": int(gst["input_total"] or 0),
                "net": int(gst["net_payable"] or 0)},
        "drivers": drivers,
        "actuals_only": True,
        "forecast_included": False,
    }


def chart_items(payload: dict) -> list[dict]:
    """Return only renderable ECharts items from a gallery payload."""
    items = []
    for group in payload.get("groups", []):
        for visual in group.get("visuals", []):
            if visual.get("option"):
                items.append({"id": visual["id"], "option": visual["option"],
                              "format": visual.get("format", "money")})
    return items
