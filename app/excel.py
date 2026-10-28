"""Real .xlsx workbook export for ARTHIVIO.

The workbook is a presentation layer only. Every amount is derived from the
posted journal through :mod:`app.analytics` and the deterministic accounting
functions; the workbook never calculates an authoritative total of its own.

Excel stores display amounts as INR decimals. The exact integer-paise source is
written alongside each KPI so an auditor can reconcile the sheet to the ledger.
"""
from __future__ import annotations

import io
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from . import accounting as acct
from . import analytics, insights as insights_mod, money

try:  # Keep the web app importable even if the optional Excel dependency is absent.
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only on a minimal install
    Workbook = None
    OPENPYXL_AVAILABLE = False

SCHEMA_VERSION = "1.0"
MONEY_FORMAT = '#,##0.00;[Red]-#,##0.00'
INTEGER_FORMAT = '#,##0'
PERCENT_FORMAT = '0.0%'

if OPENPYXL_AVAILABLE:
    TITLE_FILL = PatternFill("solid", fgColor="0C3157")
    SUBTITLE_FILL = PatternFill("solid", fgColor="0A2A48")
    HEADER_FILL = PatternFill("solid", fgColor="DCEAF5")
    TOTAL_FILL = PatternFill("solid", fgColor="E8F1F8")
    NOTE_FILL = PatternFill("solid", fgColor="FFF4D6")
    WARN_FILL = PatternFill("solid", fgColor="FDE2E1")
    WHITE_FONT = Font(name="Calibri", size=11, bold=False, color="FFFFFF")
    TITLE_FONT = Font(name="Calibri", size=24, bold=True, color="FFFFFF")
    SUBTITLE_FONT = Font(name="Calibri", size=11, color="DCEAF5")
    HEADER_FONT = Font(name="Calibri", size=10, bold=True, color="0C3157")
    BODY_FONT = Font(name="Calibri", size=10, color="1F2933")
    BOLD_FONT = Font(name="Calibri", size=10, bold=True, color="1F2933")
    SMALL_FONT = Font(name="Calibri", size=9, color="52606D")
    THIN = Side(style="thin", color="C9D6E2")
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    CENTER = Alignment(horizontal="center", vertical="center")
    LEFT = Alignment(horizontal="left", vertical="center")
    WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)


class ExcelError(Exception):
    """Raised when a workbook cannot be built safely."""


def _require_openpyxl() -> None:
    if not OPENPYXL_AVAILABLE:
        raise ExcelError(
            "Excel export needs the approved openpyxl package. "
            "Install it with: python -m pip install -r requirements.txt"
        )


def _tenant_value(tenant, key: str, default=""):
    try:
        return tenant[key]
    except (KeyError, TypeError, IndexError):
        return default


def _tenant_name(tenant) -> str:
    return str(_tenant_value(tenant, "name", "Business") or "Business")


def _tenant_slug(tenant) -> str:
    raw = str(_tenant_value(tenant, "slug", "business") or "business")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw).strip("-")
    return safe or "business"


def _inr(paise) -> float:
    if paise is None or paise == "":
        return 0.0
    value = Decimal(int(paise)) / Decimal(100)
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _pct(amount, total) -> float:
    try:
        if not total:
            return 0.0
        return float(Decimal(int(amount)) / Decimal(int(total)))
    except (TypeError, ValueError, ArithmeticError):
        return 0.0


def _fmt_value(value, unit: str):
    if unit == analytics.UNIT_BOOLEAN:
        return "Yes" if bool(value) else "No"
    if unit == analytics.UNIT_COUNT:
        return int(value or 0)
    return _inr(value)


def _sheet_title(ws, title: str, subtitle: str = "", last_col: int = 6) -> None:
    for col in range(1, last_col + 1):
        ws.cell(1, col).fill = TITLE_FILL
        ws.cell(2, col).fill = SUBTITLE_FILL
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    title_cell = ws.cell(1, 1, title)
    title_cell.font = TITLE_FONT
    title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 34

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    subtitle_cell = ws.cell(2, 1, subtitle)
    subtitle_cell.font = SUBTITLE_FONT
    subtitle_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 20


def _fit(ws, widths) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _note(ws, row: int, text: str, last_col: int, warn: bool = False) -> int:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    cell = ws.cell(row, 1, text)
    cell.font = SMALL_FONT
    cell.alignment = WRAP
    cell.fill = WARN_FILL if warn else NOTE_FILL
    for col in range(1, last_col + 1):
        ws.cell(row, col).fill = WARN_FILL if warn else NOTE_FILL
    ws.row_dimensions[row].height = 34 if len(text) > 100 else 24
    return row + 1


def _write_table(
    ws,
    headers,
    rows,
    *,
    title: str,
    subtitle: str = "",
    start_row: int = 4,
    widths=None,
    money_cols=(),
    int_cols=(),
    pct_cols=(),
    table_name: str | None = None,
    tab_color: str = "0C3157",
) -> tuple[int, int, int]:
    """Write a titled data table and return (header_row, first_data_row, last_data_row)."""
    last_col = len(headers)
    _sheet_title(ws, title, subtitle, last_col)
    ws.sheet_properties.tabColor = tab_color
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90
    if widths:
        _fit(ws, widths)

    header_row = start_row
    for index, header in enumerate(headers, start=1):
        cell = ws.cell(header_row, index, header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = BORDER
    ws.row_dimensions[header_row].height = 24

    if not rows:
        empty_row = header_row + 1
        ws.merge_cells(start_row=empty_row, start_column=1, end_row=empty_row, end_column=last_col)
        cell = ws.cell(empty_row, 1, "No actual data in this period.")
        cell.font = SMALL_FONT
        cell.alignment = LEFT
        cell.fill = NOTE_FILL
        for col in range(1, last_col + 1):
            ws.cell(empty_row, col).fill = NOTE_FILL
        ws.freeze_panes = f"A{header_row + 1}"
        ws.print_title_rows = f"1:{header_row}"
        return header_row, empty_row, empty_row

    first_data = header_row + 1
    for r_offset, row in enumerate(rows):
        excel_row = first_data + r_offset
        for c_index, value in enumerate(row, start=1):
            cell = ws.cell(excel_row, c_index, value)
            cell.font = BODY_FONT
            cell.border = BORDER
            cell.alignment = LEFT
            if c_index in money_cols and isinstance(value, (int, float)):
                cell.number_format = MONEY_FORMAT
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c_index in int_cols and isinstance(value, (int, float)):
                cell.number_format = INTEGER_FORMAT
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c_index in pct_cols and isinstance(value, (int, float)):
                cell.number_format = PERCENT_FORMAT
                cell.alignment = Alignment(horizontal="right", vertical="center")

    last_row = first_data + len(rows) - 1
    if table_name:
        try:
            from openpyxl.worksheet.table import Table, TableStyleInfo
            table = Table(displayName=table_name,
                          ref=f"A{header_row}:{get_column_letter(last_col)}{last_row}")
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2", showFirstColumn=False,
                showLastColumn=False, showRowStripes=True, showColumnStripes=False)
            ws.add_table(table)
        except Exception:  # pragma: no cover - a table is a cosmetic enhancement
            ws.auto_filter.ref = (
                f"A{header_row}:{get_column_letter(last_col)}{last_row}"
            )
    else:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(last_col)}{last_row}"

    ws.freeze_panes = f"A{first_data}"
    ws.print_title_rows = f"1:{header_row}"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    return header_row, first_data, last_row


def _total_row(ws, row: int, values, last_col: int, money_cols=(), int_cols=()) -> None:
    for index, value in enumerate(values, start=1):
        cell = ws.cell(row, index, value)
        cell.font = BOLD_FONT
        cell.fill = TOTAL_FILL
        cell.border = BORDER
        cell.alignment = LEFT
        if index in money_cols and isinstance(value, (int, float)):
            cell.number_format = MONEY_FORMAT
            cell.alignment = Alignment(horizontal="right", vertical="center")
        if index in int_cols and isinstance(value, (int, float)):
            cell.number_format = INTEGER_FORMAT
            cell.alignment = Alignment(horizontal="right", vertical="center")
    for col in range(1, last_col + 1):
        ws.cell(row, col).fill = TOTAL_FILL


def _cover(wb, tenant, data: dict) -> None:
    ws = wb.create_sheet("Cover")
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = "0C3157"
    _fit(ws, [3, 24, 28, 18, 18, 18, 18])
    for col in range(2, 8):
        ws.cell(2, col).fill = TITLE_FILL
        ws.cell(3, col).fill = SUBTITLE_FILL
    ws.merge_cells("B2:G2")
    ws.merge_cells("B3:G3")
    title = ws["B2"]
    title.value = "ARTHIVIO"
    title.font = TITLE_FONT
    title.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 52
    subtitle = ws["B3"]
    subtitle.value = "Smarter Finance. Stronger Business."
    subtitle.font = SUBTITLE_FONT
    subtitle.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[3].height = 24

    details = [
        ("Business", _tenant_name(tenant)),
        ("Period", f'{data["period"]["from"]} to {data["period"]["to"]}'),
        ("Prepared", data["freshness"]["generated_at"]),
        ("Currency", "INR (Indian rupee)"),
        ("Source", "Posted journal lines and deterministic accounting reports"),
        ("Status", "Actuals only - no estimates or forecasts"),
        ("Schema", f'Analytics contract v{data.get("schema_version", SCHEMA_VERSION)}'),
    ]
    row = 5
    for label, value in details:
        ws.cell(row, 2, label).font = BOLD_FONT
        ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=7)
        cell = ws.cell(row, 3, value)
        cell.font = BODY_FONT
        cell.alignment = LEFT
        ws.row_dimensions[row].height = 20
        row += 1

    row += 1
    ws.cell(row, 2, "EXECUTIVE SNAPSHOT").font = BOLD_FONT
    ws.cell(row, 2).fill = HEADER_FILL
    for col in range(2, 8):
        ws.cell(row, col).fill = HEADER_FILL
    row += 1

    metrics = data["metrics"]
    snapshot = [
        ("Revenue", metrics["revenue_paise"]),
        ("Expenses", metrics["expense_paise"]),
        ("Net profit", metrics["net_profit_paise"]),
        ("Cash + bank", metrics["cash_and_bank_paise"]),
        ("Receivable", metrics["receivable_paise"]),
        ("Payable", metrics["payable_paise"]),
    ]
    for label, paise in snapshot:
        ws.cell(row, 2, label).font = BODY_FONT
        ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=4)
        cell = ws.cell(row, 3, _inr(paise))
        cell.number_format = MONEY_FORMAT
        cell.font = BOLD_FONT
        cell.alignment = Alignment(horizontal="right", vertical="center")
        ws.cell(row, 5, f'{int(paise):,} paise').font = SMALL_FONT
        row += 1

    row += 1
    _note(
        ws,
        row,
        "This workbook is an output of the ARTHIVIO accounting engine. The posted journal "
        "remains the source of truth. INR values are display values converted from integer "
        "paise; the exact paise source appears on the KPI sheet. No AI, cache or forecast "
        "writes an authoritative total.",
        7,
    )


def _read_me(wb) -> None:
    ws = wb.create_sheet("Read Me")
    _sheet_title(ws, "How to read this workbook",
                 "Actuals-only finance pack generated from posted journal lines.", 7)
    ws.sheet_properties.tabColor = "2E7D8F"
    ws.sheet_view.showGridLines = False
    _fit(ws, [3, 30, 24, 18, 18, 18, 18])

    lines = [
        ("What this is", "A real .xlsx workbook built from ARTHIVIO's deterministic accounting and "
                         "analytics layer for the selected period."),
        ("What it is not", "It is not a filed return, an audited statement, a forecast or a second "
                           "ledger. GST sheets are working aids, not filed returns or claimed ITC."),
        ("Amounts", "The accounting engine stores integer paise. Sheets show INR decimals with two "
                    "places. The KPI sheet keeps the exact paise source next to each value."),
        ("Actual vs forecast", "Every sheet in this workbook is actual-only. No estimate or forecast "
                               "is mixed into an actual total. Forecast sheets are deliberately absent."),
        ("Drill-down", "The KPI and Data Dictionary sheets list the source function and the screen "
                       "that explains each metric."),
        ("Freshness", f'Generated at {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} '
                      "from the live database snapshot. Re-export after posting new entries."),
        ("AI status", "No generative AI provider is configured in this build. The AI Insights sheet "
                      "contains deterministic, grounded observations with explicit bases; it never "
                      "calculates a new authoritative total."),
        ("Security", "This workbook contains business financial data. Store and share it only with "
                     "people authorised to see the books. Do not upload it to a public service."),
    ]
    row = 4
    for heading, text in lines:
        ws.cell(row, 2, heading).font = BOLD_FONT
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)
        cell = ws.cell(row, 2, heading)
        cell.fill = HEADER_FILL
        cell.alignment = LEFT
        row += 1
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=7)
        cell = ws.cell(row, 2, text)
        cell.font = BODY_FONT
        cell.alignment = WRAP
        ws.row_dimensions[row].height = 36 if len(text) < 130 else 52
        row += 1

    row += 1
    _note(ws, row, "Sheet index: Cover, Read Me, Data Dictionary, Executive KPIs, Monthly, "
                   "Profit & Loss, Balance Sheet, Trial Balance, Expense Breakdown, Top Customers, "
                   "Top Vendors, AR Ageing, AP Ageing, Cash & Bank, Inventory, GST Working, "
                   "GST Sales, GST Purchases, Journal, AI Insights.", 7)


def _data_dictionary(wb) -> None:
    ws = wb.create_sheet("Data Dictionary")
    rows = []
    for metric in analytics.catalog()["metrics"]:
        rows.append([
            metric["key"], metric["label"], metric["unit"], metric["kind"],
            metric["source"], metric["formula"], metric["drilldown"],
        ])
    header, first, last = _write_table(
        ws,
        ["Metric key", "Label", "Unit", "Kind", "Source", "Formula", "Drill-down"],
        rows,
        title="Data Dictionary",
        subtitle="One written definition for every metric in the analytics contract.",
        widths=[27, 31, 15, 10, 34, 58, 28],
        table_name="tblDataDictionary",
        tab_color="2E7D8F",
    )
    _note(ws, last + 2, "Metric kind is 'actual' for every row in schema version 1.0. "
                        "Forecast and estimate metrics are not part of this contract.", 7)


def _kpis(wb, data: dict) -> None:
    ws = wb.create_sheet("Executive KPIs")
    rows = []
    for metric in analytics.catalog()["metrics"]:
        key = metric["key"]
        unit = metric["unit"]
        value = data["metrics"].get(key)
        source_paise = int(value or 0) if unit == analytics.UNIT_PAISE else None
        rows.append([
            metric["label"], _fmt_value(value, unit), unit, source_paise,
            metric["source"], metric["formula"], metric["drilldown"],
        ])
    header, first, last = _write_table(
        ws,
        ["Metric", "Value", "Unit", "Source paise", "Source", "Formula", "Drill-down"],
        rows,
        title="Executive KPIs",
        subtitle=f'Actuals for {data["period"]["from"]} to {data["period"]["to"]}.',
        widths=[30, 18, 14, 18, 34, 58, 28],
        money_cols=(2,),
        int_cols=(4,),
        table_name="tblExecutiveKPIs",
        tab_color="0C3157",
    )
    _note(ws, last + 2, "Value is the display value. Source paise is the exact integer-paise "
                        "amount from the ledger and is the number to reconcile against the API.", 7)


def _monthly(wb, data: dict) -> None:
    ws = wb.create_sheet("Monthly")
    months = data["monthly"]["months"]
    rows = [[m["month"], _inr(m["revenue_paise"]), _inr(m["expense_paise"]),
             _inr(m["profit_paise"])] for m in months]
    header, first, last = _write_table(
        ws,
        ["Month", "Revenue (INR)", "Expenses (INR)", "Profit (INR)"],
        rows,
        title="Monthly Actuals",
        subtitle="Zero-filled calendar months; gaps are zero actuals, never estimates.",
        widths=[16, 20, 20, 20],
        money_cols=(2, 3, 4),
        tab_color="0C3157",
    )
    if months:
        total_row = last + 1
        _total_row(ws, total_row, [
            "Total",
            _inr(data["monthly"]["total_revenue_paise"]),
            _inr(data["monthly"]["total_expense_paise"]),
            _inr(data["monthly"]["total_profit_paise"]),
        ], 4, money_cols=(2, 3, 4))

        bar = BarChart()
        bar.type = "col"
        bar.grouping = "clustered"
        bar.title = "Monthly revenue and expenses (INR)"
        bar.y_axis.title = "INR"
        bar.x_axis.title = "Month"
        bar.height = 8.5
        bar.width = 20
        bar_data = Reference(ws, min_col=2, min_row=header, max_col=3, max_row=last)
        cats = Reference(ws, min_col=1, min_row=first, max_row=last)
        bar.add_data(bar_data, titles_from_data=True)
        bar.set_categories(cats)
        ws.add_chart(bar, "F4")

        line = LineChart()
        line.title = "Monthly profit (INR)"
        line.y_axis.title = "INR"
        line.x_axis.title = "Month"
        line.height = 7
        line.width = 20
        profit_data = Reference(ws, min_col=4, min_row=header, max_col=4, max_row=last)
        line.add_data(profit_data, titles_from_data=True)
        line.set_categories(cats)
        ws.add_chart(line, "F22")

        _note(ws, total_row + 2, "Totals equal the on-screen Analytics Overview for the same period. "
                                 "The journal, not this sheet, is authoritative.", 4)
    else:
        _note(ws, last + 2, "No months in the selected period.", 4)


def _profit_and_loss(wb, pnl: dict, data: dict) -> None:
    ws = wb.create_sheet("Profit & Loss")
    rows = []
    for r in pnl["income"]:
        rows.append(["Income", r["code"], r["name"], _inr(r["amount"])])
    rows.append(["", "", "Total income", _inr(pnl["total_income"])])
    for r in pnl["expense"]:
        rows.append(["Expense", r["code"], r["name"], _inr(r["amount"])])
    rows.append(["", "", "Total expenses", _inr(pnl["total_expense"])])
    rows.append(["", "", "Net profit", _inr(pnl["net_profit"])])
    header, first, last = _write_table(
        ws,
        ["Section", "Code", "Account", "Amount (INR)"],
        rows,
        title="Profit & Loss",
        subtitle=f'{pnl["from"]} to {pnl["to"]} - actuals only.',
        widths=[14, 10, 42, 22],
        money_cols=(4,),
        table_name="tblProfitLoss",
        tab_color="2E7D8F",
    )
    _note(ws, last + 2, "Net profit equals revenue minus expenses and reconciles to the "
                        "Analytics Overview. Retained earnings on the balance sheet use the same "
                        "all-time P&L function.", 4)


def _balance_sheet(wb, bs: dict) -> None:
    ws = wb.create_sheet("Balance Sheet")
    rows = []
    for r in bs["assets"]:
        rows.append(["Asset", r["code"], r["name"], _inr(r["amount"])])
    rows.append(["", "", "Total assets", _inr(bs["total_assets"])])
    for r in bs["liabilities"]:
        rows.append(["Liability", r["code"], r["name"], _inr(r["amount"])])
    rows.append(["", "", "Total liabilities", _inr(bs["total_liabilities"])])
    for r in bs["equity"]:
        rows.append(["Equity", r["code"], r["name"], _inr(r["amount"])])
    rows.append(["Equity", "3999", "Retained earnings (current period)",
                 _inr(bs["retained_earnings"])])
    rows.append(["", "", "Total equity", _inr(bs["total_equity"])])
    rows.append(["", "", "A = L + E", "Yes" if bs["balanced"] else "No"])
    rows.append(["", "", "Difference", _inr(bs["difference"])])
    header, first, last = _write_table(
        ws,
        ["Section", "Code", "Account", "Amount (INR)"],
        rows,
        title="Balance Sheet",
        subtitle=f'As of {bs["as_of"]} - actuals only.',
        widths=[14, 10, 48, 22],
        money_cols=(4,),
        table_name="tblBalanceSheet",
        tab_color="2E7D8F",
    )
    _note(ws, last + 2, "Total equity includes retained earnings. A = L + E is checked by the "
                        "deterministic balance-sheet function; a difference is a defect, not a "
                        "rounding presentation choice.", 4, warn=not bool(bs["balanced"]))


def _trial_balance(wb, tb: dict) -> None:
    ws = wb.create_sheet("Trial Balance")
    rows = [[r["code"], r["name"], r["type"], _inr(r["debit"]), _inr(r["credit"]),
             _inr(r["balance"])] for r in tb["rows"]]
    rows.append(["", "TOTAL", "", _inr(tb["total_debit"]), _inr(tb["total_credit"]),
                 "Yes" if tb["balanced"] else "No"])
    header, first, last = _write_table(
        ws,
        ["Code", "Account", "Type", "Debit (INR)", "Credit (INR)", "Balance (INR)"],
        rows,
        title="Trial Balance",
        subtitle=f'As of {tb["as_of"]} - debit and credit totals must agree.',
        widths=[10, 44, 14, 18, 18, 18],
        money_cols=(4, 5, 6),
        table_name="tblTrialBalance",
        tab_color="2E7D8F",
    )
    _note(ws, last + 2, "The balance column is debit minus credit. The final row's Balance cell "
                        "shows whether total debit equals total credit.", 6, warn=not tb["balanced"])


def _expenses(wb, data: dict) -> None:
    ws = wb.create_sheet("Expense Breakdown")
    breakdown = data["expense_breakdown"]
    total = int(breakdown["total_paise"] or 0)
    rows = []
    for r in breakdown["rows"]:
        rows.append([r["code"], r["name"], _inr(r["amount_paise"]),
                     _pct(r["amount_paise"], total)])
    if breakdown["other_paise"]:
        rows.append(["", "Other expense ledgers", _inr(breakdown["other_paise"]),
                     _pct(breakdown["other_paise"], total)])
    if rows:
        rows.append(["", "Total expenses", _inr(total), 1.0 if total else 0.0])
    header, first, last = _write_table(
        ws,
        ["Code", "Expense ledger", "Amount (INR)", "Share"],
        rows,
        title="Expense Breakdown",
        subtitle="Expense accounts only; negative or net-credit expense balances are excluded.",
        widths=[10, 46, 20, 14],
        money_cols=(3,),
        pct_cols=(4,),
        table_name="tblExpenseBreakdown",
        tab_color="8E5A2B",
    )
    if len(rows) > 1 and total:
        pie = PieChart()
        pie.title = "Expense composition"
        pie.height = 9
        pie.width = 13
        data_ref = Reference(ws, min_col=3, min_row=header, max_row=first + len(rows) - 2)
        cats = Reference(ws, min_col=2, min_row=first, max_row=first + len(rows) - 2)
        pie.add_data(data_ref, titles_from_data=True)
        pie.set_categories(cats)
        pie.dataLabels = None
        ws.add_chart(pie, "F4")
    _note(ws, last + 2, "Share is amount divided by total expenses. Other expense ledgers is the "
                        "remainder after the top ten accounts.", 4)


def _top_parties(wb, data: dict) -> None:
    ws = wb.create_sheet("Top Customers")
    rows = [[r["name"], int(r["documents"]), _inr(r["amount_paise"])]
            for r in data["top_customers"]]
    header, first, last = _write_table(
        ws,
        ["Customer", "Invoices", "Net sales (INR)"],
        rows,
        title="Top Customers",
        subtitle="Posted invoices in the period, including GST in the invoice total.",
        widths=[40, 14, 22],
        money_cols=(3,),
        int_cols=(2,),
        table_name="tblTopCustomers",
        tab_color="2E7D8F",
    )
    if rows:
        chart = BarChart()
        chart.type = "bar"
        chart.title = "Top customers by invoice value"
        chart.height = 7
        chart.width = 18
        chart.add_data(Reference(ws, min_col=3, min_row=header, max_row=last),
                       titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=first, max_row=last))
        ws.add_chart(chart, "E4")
    _note(ws, last + 2, "Invoice value includes GST. This ranking is not net revenue; use the P&L "
                        "for revenue. The customer statement is the drill-down.", 3)

    ws2 = wb.create_sheet("Top Vendors")
    rows2 = [[r["name"], int(r["documents"]), _inr(r["amount_paise"])]
             for r in data["top_vendors"]]
    header2, first2, last2 = _write_table(
        ws2,
        ["Vendor", "Bills", "Purchases (INR)"],
        rows2,
        title="Top Vendors",
        subtitle="Posted purchase bills in the period, including input GST in the bill total.",
        widths=[40, 14, 22],
        money_cols=(3,),
        int_cols=(2,),
        table_name="tblTopVendors",
        tab_color="8E5A2B",
    )
    _note(ws2, last2 + 2, "Bill value includes input GST. This is a purchasing ranking, not an "
                          "expense total; use the P&L expense section for expenses.", 3)


def _ageing(wb, ar: dict, ap: dict) -> None:
    for sheet_name, kind, rows_key, party_key, doc_key, table_name, color in (
        ("AR Ageing", "Receivable", "rows", "customer", "invoice_no", "tblArAgeing", "2E7D8F"),
        ("AP Ageing", "Payable", "rows", "vendor", "bill_no", "tblApAgeing", "8E5A2B"),
    ):
        ws = wb.create_sheet(sheet_name)
        data = ar if kind == "Receivable" else ap
        rows = []
        for r in data[rows_key]:
            rows.append([r.get(doc_key) or "", r["date"], r[party_key],
                         _inr(r["total"]), _inr(r["outstanding"]),
                         int(r["days"]), r["bucket"]])
        header, first, last = _write_table(
            ws,
            ["Document", "Date", "Party", "Total (INR)", "Outstanding (INR)", "Days", "Bucket"],
            rows,
            title=f"{kind} Ageing",
            subtitle=f'As of {data["as_of"]}. Open documents only.',
            widths=[18, 12, 36, 18, 20, 10, 12],
            money_cols=(4, 5),
            int_cols=(6,),
            table_name=table_name,
            tab_color=color,
        )
        bucket_row = last + 2
        ws.cell(bucket_row, 1, "Bucket totals").font = BOLD_FONT
        bucket_row += 1
        ws.cell(bucket_row, 1, "Bucket").font = HEADER_FONT
        ws.cell(bucket_row, 2, "Outstanding (INR)").font = HEADER_FONT
        for col in (1, 2):
            ws.cell(bucket_row, col).fill = HEADER_FILL
            ws.cell(bucket_row, col).border = BORDER
        bucket_row += 1
        for bucket in ("current", "31-60", "61-90", "90+"):
            ws.cell(bucket_row, 1, bucket).font = BODY_FONT
            cell = ws.cell(bucket_row, 2, _inr(data["totals"][bucket]))
            cell.number_format = MONEY_FORMAT
            cell.font = BODY_FONT
            for col in (1, 2):
                ws.cell(bucket_row, col).border = BORDER
            bucket_row += 1
        ws.cell(bucket_row, 1, "Grand total").font = BOLD_FONT
        cell = ws.cell(bucket_row, 2, _inr(data["grand_total"]))
        cell.number_format = MONEY_FORMAT
        cell.font = BOLD_FONT
        for col in (1, 2):
            ws.cell(bucket_row, col).fill = TOTAL_FILL
            ws.cell(bucket_row, col).border = BORDER
        _note(ws, bucket_row + 2, "Ageing uses posted documents with an outstanding balance as of "
                                  "the period end. Buckets are current, 31-60, 61-90 and 90+ days.",
              7)


def _cash_and_bank(wb, conn, tenant, data: dict) -> None:
    ws = wb.create_sheet("Cash & Bank")
    tid = _tenant_value(tenant, "id")
    row = conn.execute(
        """SELECT COALESCE(SUM(debit_paise),0) AS inflow,
                  COALESCE(SUM(credit_paise),0) AS outflow
           FROM v_analytics_journal
           WHERE tenant_id=? AND group_code IN ('cash','bank')
             AND entry_date BETWEEN ? AND ?""",
        (tid, data["period"]["from"], data["period"]["to"]),
    ).fetchone()
    inflow = int(row["inflow"] or 0)
    outflow = int(row["outflow"] or 0)
    closing = int(data["metrics"]["cash_and_bank_paise"] or 0)
    net = inflow - outflow
    opening = closing - net
    rows = [
        ["Opening cash + bank", _inr(opening)],
        ["Inflows (debits)", _inr(inflow)],
        ["Outflows (credits)", _inr(outflow)],
        ["Net movement", _inr(net)],
        ["Closing cash + bank", _inr(closing)],
    ]
    header, first, last = _write_table(
        ws,
        ["Line", "Amount (INR)"],
        rows,
        title="Cash & Bank Movement",
        subtitle="A movement summary, not a full cash-flow statement.",
        widths=[40, 22],
        money_cols=(2,),
        table_name="tblCashBank",
        tab_color="0C3157",
    )
    _note(ws, last + 2, "Opening is derived as closing minus the period's net cash/bank movement. "
                        "The closing figure equals the Cash + bank KPI, which is the trial-balance "
                        "cash and bank group at the period end.", 2)


def _inventory(wb, conn, tenant) -> None:
    ws = wb.create_sheet("Inventory")
    tid = _tenant_value(tenant, "id")
    rows = conn.execute(
        """SELECT sku, name, category, unit, stock_milli, cost_paise, sale_price_paise
           FROM item WHERE tenant_id=? ORDER BY name, sku""", (tid,)
    ).fetchall()
    out = []
    total_value = 0
    for r in rows:
        stock = int(r["stock_milli"] or 0)
        cost = int(r["cost_paise"] or 0)
        value = (stock * cost + 500) // 1000 if stock >= 0 else -((-stock * cost + 500) // 1000)
        total_value += value
        out.append([
            r["sku"], r["name"], r["category"] or "", r["unit"] or "",
            stock / 1000, _inr(cost), _inr(r["sale_price_paise"]), _inr(value),
        ])
    if out:
        out.append(["", "TOTAL", "", "", None, None, None, _inr(total_value)])
    header, first, last = _write_table(
        ws,
        ["SKU", "Item", "Category", "Unit", "Stock qty", "Cost (INR)",
         "Sale price (INR)", "Stock value (INR)"],
        out,
        title="Inventory",
        subtitle="Perpetual stock at weighted-average cost as of the export.",
        widths=[16, 36, 18, 10, 14, 16, 18, 18],
        money_cols=(6, 7, 8),
        table_name="tblInventory",
        tab_color="8E5A2B",
    )
    _note(ws, last + 2, "Stock value is quantity x weighted-average cost, derived from the item "
                        "master and inventory ledger. It is an export view, not a new valuation "
                        "method.", 8)


def _gst(wb, gst: dict) -> None:
    ws = wb.create_sheet("GST Working")
    rows = [
        ["Output", "CGST", _inr(gst["output"]["CGST"])],
        ["Output", "SGST", _inr(gst["output"]["SGST"])],
        ["Output", "IGST", _inr(gst["output"]["IGST"])],
        ["Output", "Total output tax", _inr(gst["output_total"])],
        ["Input", "CGST", _inr(gst["input"]["CGST"])],
        ["Input", "SGST", _inr(gst["input"]["SGST"])],
        ["Input", "IGST", _inr(gst["input"]["IGST"])],
        ["Input", "Total input tax", _inr(gst["input_total"])],
        ["Net", "Net payable (negative = input credit)", _inr(gst["net_payable"])],
    ]
    header, first, last = _write_table(
        ws,
        ["Section", "Head", "Amount (INR)"],
        rows,
        title="GST Working Summary",
        subtitle=f'{gst["from"]} to {gst["to"]} - working aid, not a filed return.',
        widths=[14, 40, 22],
        money_cols=(3,),
        table_name="tblGstWorking",
        tab_color="8E5A2B",
    )
    _note(ws, last + 2, "These figures are preparation aids only. They do not file a return, claim "
                        "ITC or replace a tax professional's review.", 3, warn=True)

    ws2 = wb.create_sheet("GST Sales")
    sales = [[r["invoice_no"], r["invoice_date"], r["party"], _inr(r["sub_total_paise"]),
              _inr(r["tax_paise"]), _inr(r["total_paise"])] for r in gst["sales"]]
    sales_total = sum(int(r["total_paise"] or 0) for r in gst["sales"])
    if sales:
        sales.append(["", "TOTAL", "", "", "", _inr(sales_total)])
    header, first, last = _write_table(
        ws2,
        ["Invoice", "Date", "Customer", "Taxable (INR)", "GST (INR)", "Total (INR)"],
        sales,
        title="GST Sales Register",
        subtitle="Posted invoices in the period.",
        widths=[18, 12, 36, 18, 16, 18],
        money_cols=(4, 5, 6),
        table_name="tblGstSales",
        tab_color="8E5A2B",
    )

    ws3 = wb.create_sheet("GST Purchases")
    purchases = [[r["bill_no"], r["bill_date"], r["party"], _inr(r["sub_total_paise"]),
                  _inr(r["tax_paise"]), _inr(r["total_paise"])] for r in gst["purchases"]]
    purchase_total = sum(int(r["total_paise"] or 0) for r in gst["purchases"])
    if purchases:
        purchases.append(["", "TOTAL", "", "", "", _inr(purchase_total)])
    header, first, last = _write_table(
        ws3,
        ["Bill", "Date", "Vendor", "Taxable (INR)", "Input GST (INR)", "Total (INR)"],
        purchases,
        title="GST Purchase Register",
        subtitle="Posted purchase bills in the period.",
        widths=[18, 12, 36, 18, 18, 18],
        money_cols=(4, 5, 6),
        table_name="tblGstPurchases",
        tab_color="8E5A2B",
    )


def _journal(wb, conn, tenant, date_from: str, date_to: str, limit: int = 100000) -> None:
    ws = wb.create_sheet("Journal")
    tid = _tenant_value(tenant, "id")
    total = conn.execute(
        """SELECT COUNT(*) AS n FROM v_analytics_journal
           WHERE tenant_id=? AND entry_date BETWEEN ? AND ?""",
        (tid, date_from, date_to),
    ).fetchone()["n"]
    rows = conn.execute(
        """SELECT j.entry_date, j.entry_no, j.source_type, j.status, j.line_no,
                  j.account_code, j.account_name,
                  COALESCE(c.name, v.name, '') AS party_name,
                  j.debit_paise, j.credit_paise, j.memo
           FROM v_analytics_journal j
           LEFT JOIN customer c ON c.id=j.party_id AND c.tenant_id=j.tenant_id
           LEFT JOIN vendor v ON v.id=j.party_id AND v.tenant_id=j.tenant_id
           WHERE j.tenant_id=? AND j.entry_date BETWEEN ? AND ?
           ORDER BY j.entry_date, j.entry_no, j.line_no
           LIMIT ?""",
        (tid, date_from, date_to, limit),
    ).fetchall()
    out = [[r["entry_date"], r["entry_no"], r["source_type"], r["status"], int(r["line_no"]),
            r["account_code"], r["account_name"], r["party_name"],
            _inr(r["debit_paise"]), _inr(r["credit_paise"]), r["memo"] or ""]
           for r in rows]
    header, first, last = _write_table(
        ws,
        ["Date", "Entry", "Source", "Status", "Line", "Code", "Account", "Party",
         "Debit (INR)", "Credit (INR)", "Memo"],
        out,
        title="Journal Lines",
        subtitle="Every exported line comes from the posted journal; history is never rewritten.",
        widths=[12, 14, 14, 10, 8, 10, 32, 28, 16, 16, 40],
        money_cols=(9, 10),
        int_cols=(5,),
        tab_color="0C3157",
    )
    if total > limit:
        _note(ws, last + 2, f"Export capped at {limit:,} journal lines out of {total:,}. "
                            "Narrow the date range for a complete export.", 11, warn=True)
    else:
        _note(ws, last + 2, f"{total:,} journal line(s) in the period. Reversals remain in history "
                            "and net to zero; they are not deleted.", 11)


def _insights(wb, conn, tenant, data: dict) -> None:
    ws = wb.create_sheet("AI Insights")
    result = insights_mod.grounded(
        conn, tenant, data["period"]["from"], data["period"]["to"]
    )
    rows = [[o["label"], o["value_text"], o["basis"], o["drilldown"]]
            for o in result["observations"]]
    header, first, last = _write_table(
        ws,
        ["Grounded observation", "Value", "Basis", "Drill-down"],
        rows,
        title="AI Insights",
        subtitle="Deterministic, grounded observations. No generative AI provider is configured.",
        widths=[52, 24, 58, 28],
        table_name="tblAiInsights",
        tab_color="6B4C9A",
    )
    _note(ws, last + 2, result["summary"] + " These are rule-based observations over the actuals "
                        "payload; they are deliberately not called generative AI and do not "
                        "calculate a new authoritative total. Forecasts are excluded; a future "
                        "AI provider must cite these same metric keys and source records.", 4,
          warn=True)


def build_workbook(conn: sqlite3.Connection, tenant,
                   date_from: str | None = None, date_to: str | None = None) -> bytes:
    """Return a real .xlsx workbook for one tenant and period.

    Raises :class:`analytics.AnalyticsError` for invalid dates and
    :class:`ExcelError` if the approved Excel dependency is unavailable.
    """
    _require_openpyxl()
    period = analytics.resolve_period(tenant, date_from, date_to)
    data = analytics.overview(conn, tenant, period["from"], period["to"])
    pnl = acct.profit_and_loss(conn, _tenant_value(tenant, "id"),
                               period["from"], period["to"])
    bs = acct.balance_sheet(conn, _tenant_value(tenant, "id"), period["to"])
    tb = acct.trial_balance(conn, _tenant_value(tenant, "id"), period["to"])
    gst = acct.gst_summary(conn, _tenant_value(tenant, "id"),
                           period["from"], period["to"])
    ar = acct.receivable_ageing(conn, _tenant_value(tenant, "id"), period["to"])
    ap = acct.payable_ageing(conn, _tenant_value(tenant, "id"), period["to"])

    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = "ARTHIVIO"
    wb.properties.title = f"ARTHIVIO actuals workbook - {_tenant_name(tenant)}"
    wb.properties.description = (
        "Generated from posted journal lines. Actuals only; no estimates or forecasts."
    )
    wb.calculation.fullCalcOnLoad = True

    _cover(wb, tenant, data)
    _read_me(wb)
    _data_dictionary(wb)
    _kpis(wb, data)
    _monthly(wb, data)
    _profit_and_loss(wb, pnl, data)
    _balance_sheet(wb, bs)
    _trial_balance(wb, tb)
    _expenses(wb, data)
    _top_parties(wb, data)
    _ageing(wb, ar, ap)
    _cash_and_bank(wb, conn, tenant, data)
    _inventory(wb, conn, tenant)
    _gst(wb, gst)
    _journal(wb, conn, tenant, period["from"], period["to"])
    _insights(wb, conn, tenant, data)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def filename(tenant, date_to: str | None = None) -> str:
    return f"arthivio-{_tenant_slug(tenant)}-actuals-{date_to or date.today().isoformat()}.xlsx"
