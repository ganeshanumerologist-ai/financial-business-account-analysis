"""Saved analytics dashboards and the built-in dashboard template library.

A saved dashboard is a named, read-only selection of registered metrics and
charts for one period. It stores configuration only: every number is still
computed from posted journal rows when the dashboard is opened. Nothing here
caches or invents an authoritative total.

The table is additive. Existing databases gain it through ``db.init_db`` and no
historical row is rewritten.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from . import accounting as acct
from . import analytics as analytics_mod
from . import db

PERMISSION = analytics_mod.PERMISSION
MAX_NAME = 80
PERIODS = ("fiscal_ytd", "this_month", "last_month", "this_quarter", "custom")
VISIBILITIES = ("private", "tenant")
CHART_KEYS = ("monthly", "expense_breakdown", "top_customers", "top_vendors")
LANGUAGES = ("en", "hi")
METRIC_BY_KEY = {m["key"]: m for m in analytics_mod.METRICS}
METRIC_KEYS = tuple(METRIC_BY_KEY)

# The template library is a set of honest starting points. Each template is
# only a configuration; the user can change it after creating a dashboard. The
# library is intentionally grouped by the question a business owner is asking.
TEMPLATES = (
    {
        "key": "owner_monthly",
        "name": "Owner monthly",
        "category": "Starter",
        "description": "Revenue, expenses, profit, cash, receivable and payable for the current month.",
        "config": {
            "period": "this_month",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "expense_paise", "net_profit_paise",
                        "cash_and_bank_paise", "receivable_paise", "payable_paise"],
            "charts": ["monthly", "expense_breakdown"],
            "language": "en",
        },
    },
    {
        "key": "owner_quarterly",
        "name": "Owner quarterly",
        "category": "Starter",
        "description": "The owner's quarter: profit, cash, working capital and customer concentration.",
        "config": {
            "period": "this_quarter",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "expense_paise", "net_profit_paise",
                        "cash_and_bank_paise", "receivable_paise", "payable_paise",
                        "inventory_paise"],
            "charts": ["monthly", "expense_breakdown", "top_customers"],
            "language": "en",
        },
    },
    {
        "key": "working_capital",
        "name": "Working capital",
        "category": "Cash",
        "description": "Cash, receivable, payable, inventory and overdue balances for the fiscal year to date.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["cash_and_bank_paise", "receivable_paise", "payable_paise",
                        "inventory_paise", "overdue_receivable_paise",
                        "overdue_payable_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "cash_position",
        "name": "Cash position",
        "category": "Cash",
        "description": "Cash and bank, receivable, payable and inventory for the fiscal year to date.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["cash_and_bank_paise", "receivable_paise", "payable_paise",
                        "inventory_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "cash_burn",
        "name": "Cash burn",
        "category": "Cash",
        "description": "Expenses, cash and profit for the quarter. Shows actual burn, not a forecast.",
        "config": {
            "period": "this_quarter",
            "from": "",
            "to": "",
            "metrics": ["expense_paise", "cash_and_bank_paise", "net_profit_paise"],
            "charts": ["monthly", "expense_breakdown"],
            "language": "en",
        },
    },
    {
        "key": "gst_working_paper",
        "name": "GST working paper",
        "category": "Tax",
        "description": "Output tax, input tax and net payable for the current month. Working aid, not a filed return.",
        "config": {
            "period": "this_month",
            "from": "",
            "to": "",
            "metrics": ["gst_output_paise", "gst_input_paise", "gst_net_payable_paise",
                        "revenue_paise", "expense_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "gst_input_credit",
        "name": "GST input credit",
        "category": "Tax",
        "description": "Input tax, output tax and net payable for the current month. Working aid only.",
        "config": {
            "period": "this_month",
            "from": "",
            "to": "",
            "metrics": ["gst_input_paise", "gst_output_paise", "gst_net_payable_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "gst_output_liability",
        "name": "GST output liability",
        "category": "Tax",
        "description": "Output tax, revenue and net payable for the current month. Working aid only.",
        "config": {
            "period": "this_month",
            "from": "",
            "to": "",
            "metrics": ["gst_output_paise", "revenue_paise", "gst_net_payable_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "statutory_dues",
        "name": "Statutory dues",
        "category": "Tax",
        "description": "GST output, input, net payable and total liabilities for the current month.",
        "config": {
            "period": "this_month",
            "from": "",
            "to": "",
            "metrics": ["gst_output_paise", "gst_input_paise", "gst_net_payable_paise",
                        "total_liabilities_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "receivables_followup",
        "name": "Receivables follow-up",
        "category": "Receivables",
        "description": "Outstanding receivables, open invoices and the 60+ day overdue balance.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["receivable_paise", "open_invoices",
                        "overdue_receivable_paise"],
            "charts": ["top_customers"],
            "language": "en",
        },
    },
    {
        "key": "receivables_ageing",
        "name": "Receivables ageing",
        "category": "Receivables",
        "description": "Receivable, open invoices and overdue balance with the top customer list.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["receivable_paise", "open_invoices",
                        "overdue_receivable_paise"],
            "charts": ["top_customers", "monthly"],
            "language": "en",
        },
    },
    {
        "key": "overdue_collections",
        "name": "Overdue collections",
        "category": "Receivables",
        "description": "Overdue receivable, total receivable and open invoice count for collections.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["overdue_receivable_paise", "receivable_paise", "open_invoices"],
            "charts": ["top_customers"],
            "language": "en",
        },
    },
    {
        "key": "customer_concentration",
        "name": "Customer concentration",
        "category": "Receivables",
        "description": "Revenue, receivable and overdue exposure with the top customer list.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "receivable_paise", "open_invoices",
                        "overdue_receivable_paise"],
            "charts": ["top_customers", "monthly"],
            "language": "en",
        },
    },
    {
        "key": "payables_ageing",
        "name": "Payables ageing",
        "category": "Payables",
        "description": "Payable, open bills and overdue balance with the top vendor list.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["payable_paise", "open_bills", "overdue_payable_paise"],
            "charts": ["top_vendors", "monthly"],
            "language": "en",
        },
    },
    {
        "key": "payment_obligations",
        "name": "Payment obligations",
        "category": "Payables",
        "description": "Overdue payable, total payable and open bill count for payment planning.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["overdue_payable_paise", "payable_paise", "open_bills"],
            "charts": ["top_vendors"],
            "language": "en",
        },
    },
    {
        "key": "purchase_performance",
        "name": "Purchase performance",
        "category": "Payables",
        "description": "Expenses, payable and open bills for the current month with vendor concentration.",
        "config": {
            "period": "this_month",
            "from": "",
            "to": "",
            "metrics": ["expense_paise", "payable_paise", "open_bills"],
            "charts": ["monthly", "top_vendors"],
            "language": "en",
        },
    },
    {
        "key": "vendor_concentration",
        "name": "Vendor concentration",
        "category": "Payables",
        "description": "Expenses, payable and overdue exposure with the top vendor list.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["expense_paise", "payable_paise", "open_bills",
                        "overdue_payable_paise"],
            "charts": ["top_vendors", "monthly"],
            "language": "en",
        },
    },
    {
        "key": "sales_performance",
        "name": "Sales performance",
        "category": "Profitability",
        "description": "Revenue, profit and open invoices for the current month with customer concentration.",
        "config": {
            "period": "this_month",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "net_profit_paise", "open_invoices"],
            "charts": ["monthly", "top_customers"],
            "language": "en",
        },
    },
    {
        "key": "gross_margin",
        "name": "Gross margin",
        "category": "Profitability",
        "description": "Revenue, expenses and net profit for the quarter with the expense mix.",
        "config": {
            "period": "this_quarter",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "expense_paise", "net_profit_paise"],
            "charts": ["monthly", "expense_breakdown"],
            "language": "en",
        },
    },
    {
        "key": "expense_control",
        "name": "Expense control",
        "category": "Profitability",
        "description": "Expense, profit and input tax for the fiscal year to date with the expense mix.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["expense_paise", "net_profit_paise", "gst_input_paise"],
            "charts": ["monthly", "expense_breakdown"],
            "language": "en",
        },
    },
    {
        "key": "revenue_vs_expense",
        "name": "Revenue vs expense",
        "category": "Profitability",
        "description": "Revenue, expenses and net profit for the fiscal year to date.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "expense_paise", "net_profit_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "inventory_position",
        "name": "Inventory position",
        "category": "Inventory",
        "description": "Inventory, cash and payable for the fiscal year to date.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["inventory_paise", "cash_and_bank_paise", "payable_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "balance_sheet_health",
        "name": "Balance sheet health",
        "category": "Balance sheet",
        "description": "Assets, liabilities, equity, cash, receivable and payable for the fiscal year to date.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["total_assets_paise", "total_liabilities_paise",
                        "total_equity_paise", "cash_and_bank_paise",
                        "receivable_paise", "payable_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "asset_liability_mix",
        "name": "Asset and liability mix",
        "category": "Balance sheet",
        "description": "Assets, liabilities, equity, cash and inventory for the fiscal year to date.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["total_assets_paise", "total_liabilities_paise",
                        "total_equity_paise", "cash_and_bank_paise",
                        "inventory_paise"],
            "charts": ["monthly"],
            "language": "en",
        },
    },
    {
        "key": "month_end_close",
        "name": "Month-end close",
        "category": "Close",
        "description": "Current-month profit, GST and both balance checks for the month-end review.",
        "config": {
            "period": "this_month",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "expense_paise", "net_profit_paise",
                        "gst_net_payable_paise", "trial_balance_balanced",
                        "balance_sheet_balanced"],
            "charts": ["monthly", "expense_breakdown"],
            "language": "en",
        },
    },
    {
        "key": "operational_counts",
        "name": "Operational counts",
        "category": "Close",
        "description": "Open invoices, open bills and both balance checks for the fiscal year to date.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["open_invoices", "open_bills", "trial_balance_balanced",
                        "balance_sheet_balanced"],
            "charts": [],
            "language": "en",
        },
    },
    {
        "key": "quarterly_review",
        "name": "Quarterly review",
        "category": "Review",
        "description": "Quarterly profit, balance sheet, cash and both party lists.",
        "config": {
            "period": "this_quarter",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "expense_paise", "net_profit_paise",
                        "total_assets_paise", "total_liabilities_paise",
                        "cash_and_bank_paise"],
            "charts": ["monthly", "expense_breakdown", "top_customers", "top_vendors"],
            "language": "en",
        },
    },
    {
        "key": "year_end_review",
        "name": "Year-end review",
        "category": "Review",
        "description": "A twelve-metric year-end pack with all four chart panels. Actuals only.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": ["revenue_paise", "expense_paise", "net_profit_paise",
                        "total_assets_paise", "total_liabilities_paise",
                        "total_equity_paise", "cash_and_bank_paise",
                        "receivable_paise", "payable_paise", "inventory_paise",
                        "gst_net_payable_paise", "trial_balance_balanced"],
            "charts": ["monthly", "expense_breakdown", "top_customers", "top_vendors"],
            "language": "en",
        },
    },
    {
        "key": "full_finance",
        "name": "Full finance pack",
        "category": "Full pack",
        "description": "Every registered actual metric and all four chart panels for the fiscal year to date.",
        "config": {
            "period": "fiscal_ytd",
            "from": "",
            "to": "",
            "metrics": list(METRIC_KEYS),
            "charts": list(CHART_KEYS),
            "language": "en",
        },
    },
)
TEMPLATE_BY_KEY = {t["key"]: t for t in TEMPLATES}

# Small, deliberate label set for the saved-dashboard surface. This is not a
# claim that the whole application is translated. English remains the fallback.
LABELS = {
    "en": {
        "Revenue": "Revenue",
        "Expenses": "Expenses",
        "Net profit": "Net profit",
        "Total assets": "Total assets",
        "Total liabilities": "Total liabilities",
        "Total equity": "Total equity",
        "Cash and bank": "Cash and bank",
        "Receivable": "Receivable",
        "Payable": "Payable",
        "Inventory": "Inventory",
        "Open invoices": "Open invoices",
        "Open bills": "Open bills",
        "Overdue receivable (60+ days)": "Overdue receivable (60+ days)",
        "Overdue payable (60+ days)": "Overdue payable (60+ days)",
        "GST output tax": "GST output tax",
        "GST input tax": "GST input tax",
        "GST net payable": "GST net payable",
        "Trial balance balanced": "Trial balance balanced",
        "Balance sheet balanced": "Balance sheet balanced",
        "Saved dashboards": "Saved dashboards",
        "Dashboard templates": "Dashboard templates",
        "Create a dashboard": "Create a dashboard",
        "Name": "Name",
        "Visibility": "Visibility",
        "Private": "Private",
        "Shared with this business": "Shared with this business",
        "Period": "Period",
        "Fiscal year to date": "Fiscal year to date",
        "This month": "This month",
        "Last month": "Last month",
        "This quarter": "This quarter",
        "Custom dates": "Custom dates",
        "From": "From",
        "To": "To",
        "Language": "Language",
        "Metrics": "Metrics",
        "Charts": "Charts",
        "Monthly revenue and expenses": "Monthly revenue and expenses",
        "Expense breakdown": "Expense breakdown",
        "Top customers": "Top customers",
        "Top vendors": "Top vendors",
        "Create dashboard": "Create dashboard",
        "Use template": "Use template",
        "Open": "Open",
        "Delete": "Delete",
        "Actuals only": "Actuals only",
        "Actuals from posted journals": "Actuals from posted journals",
        "Filtered actuals": "Filtered actuals",
        "Unfiltered actuals (not filterable)": "Unfiltered actuals (not filterable)",
        "Charts hidden while filters are active": "Charts hidden while filters are active",
        "Yes": "Yes",
        "No": "No",
        "No saved dashboards yet.": "No saved dashboards yet.",
        "No data in this period.": "No data in this period.",
        "Posted journal actuals; no estimate or forecast is included.": (
            "Posted journal actuals; no estimate or forecast is included."),
        "Back to analytics": "Back to analytics",
        "Created by": "Created by",
        "Updated": "Updated",
        "This dashboard is private to its creator.": "This dashboard is private to its creator.",
    },
    "hi": {
        "Revenue": "आय",
        "Expenses": "व्यय",
        "Net profit": "शुद्ध लाभ",
        "Total assets": "कुल संपत्ति",
        "Total liabilities": "कुल देनदारियाँ",
        "Total equity": "कुल पूंजी",
        "Cash and bank": "नकद और बैंक",
        "Receivable": "प्राप्य",
        "Payable": "देय",
        "Inventory": "स्टॉक",
        "Open invoices": "खुली बिक्री बिल",
        "Open bills": "खुली खरीद बिल",
        "Overdue receivable (60+ days)": "अतिदेय प्राप्य (60+ दिन)",
        "Overdue payable (60+ days)": "अतिदेय देय (60+ दिन)",
        "GST output tax": "जीएसटी आउटपुट कर",
        "GST input tax": "जीएसटी इनपुट कर",
        "GST net payable": "जीएसटी शुद्ध देय",
        "Trial balance balanced": "ट्रायल बैलेंस संतुलित",
        "Balance sheet balanced": "बैलेंस शीट संतुलित",
        "Saved dashboards": "सहेजे गए डैशबोर्ड",
        "Dashboard templates": "डैशबोर्ड टेम्पलेट",
        "Create a dashboard": "डैशबोर्ड बनाएँ",
        "Name": "नाम",
        "Visibility": "दृश्यता",
        "Private": "निजी",
        "Shared with this business": "इस व्यवसाय के साथ साझा",
        "Period": "अवधि",
        "Fiscal year to date": "वित्त वर्ष अब तक",
        "This month": "इस महीने",
        "Last month": "पिछले महीने",
        "This quarter": "इस तिमाही",
        "Custom dates": "कस्टम तिथियाँ",
        "From": "से",
        "To": "तक",
        "Language": "भाषा",
        "Metrics": "मापदंड",
        "Charts": "चार्ट",
        "Monthly revenue and expenses": "मासिक आय और व्यय",
        "Expense breakdown": "व्यय विवरण",
        "Top customers": "शीर्ष ग्राहक",
        "Top vendors": "शीर्ष आपूर्तिकर्ता",
        "Create dashboard": "डैशबोर्ड बनाएँ",
        "Use template": "टेम्पलेट का उपयोग करें",
        "Open": "खोलें",
        "Delete": "हटाएँ",
        "Actuals only": "केवल वास्तविक",
        "Actuals from posted journals": "पोस्ट किए गए जर्नल से वास्तविक",
        "Filtered actuals": "फ़िल्टर किए गए वास्तविक",
        "Unfiltered actuals (not filterable)": "बिना फ़िल्टर वास्तविक (फ़िल्टर लागू नहीं)",
        "Charts hidden while filters are active": "फ़िल्टर सक्रिय होने पर चार्ट छिपे हैं",
        "Yes": "हाँ",
        "No": "नहीं",
        "No saved dashboards yet.": "अभी कोई सहेजा गया डैशबोर्ड नहीं है।",
        "No data in this period.": "इस अवधि में कोई डेटा नहीं है।",
        "Posted journal actuals; no estimate or forecast is included.": (
            "पोस्ट किए गए जर्नल से वास्तविक; कोई अनुमान या पूर्वानुमान शामिल नहीं है।"),
        "Back to analytics": "विश्लेषण पर वापस",
        "Created by": "बनाने वाला",
        "Updated": "अद्यतन",
        "This dashboard is private to its creator.": "यह डैशबोर्ड केवल इसके बनाने वाले के लिए है।",
    },
}


class DashboardError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def t(lang: str, key: str) -> str:
    """Translate a saved-dashboard label, falling back to English and the key."""
    return LABELS.get(lang, LABELS["en"]).get(key, LABELS["en"].get(key, key))


def metric_label(key: str, lang: str = "en") -> str:
    metric = METRIC_BY_KEY.get(key)
    if not metric:
        return key
    return t(lang, metric["label"])


def templates() -> list[dict]:
    """Return template metadata without exposing shared mutable configs."""
    return [{"key": item["key"], "name": item["name"],
             "category": item.get("category", "Starter"),
             "description": item["description"],
             "config": json.loads(json.dumps(item["config"]))}
            for item in TEMPLATES]


def template(key: str) -> dict | None:
    item = TEMPLATE_BY_KEY.get((key or "").strip())
    if not item:
        return None
    return {"key": item["key"], "name": item["name"],
            "category": item.get("category", "Starter"),
            "description": item["description"],
            "config": json.loads(json.dumps(item["config"]))}


def normalize_config(config: dict | None) -> dict:
    config = config or {}
    period = str(config.get("period") or "fiscal_ytd")
    if period not in PERIODS:
        raise DashboardError("BAD_PERIOD", "Choose a valid dashboard period.")

    raw_metrics = config.get("metrics") or []
    if isinstance(raw_metrics, str):
        raw_metrics = [raw_metrics]
    metrics = [str(key) for key in raw_metrics if str(key) in METRIC_BY_KEY]
    metrics = list(dict.fromkeys(metrics))
    if not metrics:
        raise DashboardError("NO_METRICS", "Choose at least one metric for the dashboard.")
    metrics = metrics[:12]

    raw_charts = config.get("charts") or []
    if isinstance(raw_charts, str):
        raw_charts = [raw_charts]
    charts = [str(key) for key in raw_charts if str(key) in CHART_KEYS]
    charts = list(dict.fromkeys(charts))

    language = str(config.get("language") or "en")
    if language not in LANGUAGES:
        language = "en"

    date_from = str(config.get("from") or "").strip()
    date_to = str(config.get("to") or "").strip()
    for label, value in (("From", date_from), ("To", date_to)):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise DashboardError("BAD_DATE", f"{label} must be a valid YYYY-MM-DD date.")
    if date_from and date_to and date_from > date_to:
        raise DashboardError("BAD_PERIOD", "The start date cannot be after the end date.")
    if period == "custom" and not (date_from and date_to):
        raise DashboardError("BAD_PERIOD", "Custom dates need both a start and an end date.")

    return {"period": period, "from": date_from, "to": date_to,
            "metrics": metrics, "charts": charts, "language": language}


def resolve_period(tenant, config: dict) -> dict:
    """Resolve a saved dashboard period to concrete ISO dates."""
    period = (config or {}).get("period") or "fiscal_ytd"
    today = date.today()
    if period == "this_month":
        return analytics_mod.resolve_period(tenant, today.replace(day=1).isoformat(),
                                            today.isoformat())
    if period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return analytics_mod.resolve_period(tenant, last_prev.replace(day=1).isoformat(),
                                            last_prev.isoformat())
    if period == "this_quarter":
        start_month = ((today.month - 1) // 3) * 3 + 1
        return analytics_mod.resolve_period(tenant, date(today.year, start_month, 1).isoformat(),
                                            today.isoformat())
    if period == "custom" and config.get("from") and config.get("to"):
        return analytics_mod.resolve_period(tenant, config["from"], config["to"])
    return analytics_mod.resolve_period(tenant)


def list_dashboards(conn: sqlite3.Connection, tenant_id: str, user_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT d.id, d.tenant_id, d.name, d.description, d.config_json,
                  d.visibility, d.created_by, d.created_at, d.updated_at,
                  u.full_name AS creator_name
           FROM saved_dashboard d
           JOIN user u ON u.id = d.created_by
           WHERE d.tenant_id=? AND (d.created_by=? OR d.visibility='tenant')
           ORDER BY d.updated_at DESC, d.name""",
        (tenant_id, user_id),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["config"] = normalize_config(json.loads(item.pop("config_json")))
        except (ValueError, TypeError, DashboardError):
            item["config"] = normalize_config({"metrics": ["revenue_paise"]})
        out.append(item)
    return out


def get_dashboard(conn: sqlite3.Connection, tenant_id: str, dashboard_id: str) -> dict:
    row = conn.execute(
        """SELECT d.*, u.full_name AS creator_name
           FROM saved_dashboard d
           JOIN user u ON u.id = d.created_by
           WHERE d.id=? AND d.tenant_id=?""",
        (dashboard_id, tenant_id),
    ).fetchone()
    if not row:
        raise DashboardError("NOT_FOUND", "Dashboard not found in this business.")
    item = dict(row)
    try:
        item["config"] = normalize_config(json.loads(item.pop("config_json")))
    except (ValueError, TypeError, DashboardError):
        item["config"] = normalize_config({"metrics": ["revenue_paise"]})
    return item


def create_dashboard(conn: sqlite3.Connection, tenant_id: str, user_id: str,
                     name: str, config: dict | None,
                     visibility: str = "private", description: str = "") -> str:
    name = (name or "").strip()
    if not name:
        raise DashboardError("NAME_REQUIRED", "Give the dashboard a name.")
    if len(name) > MAX_NAME:
        raise DashboardError("NAME_TOO_LONG", f"Keep the dashboard name under {MAX_NAME} characters.")
    if visibility not in VISIBILITIES:
        visibility = "private"
    clean = normalize_config(config)
    existing = conn.execute(
        "SELECT id FROM saved_dashboard WHERE tenant_id=? AND name=?",
        (tenant_id, name),
    ).fetchone()
    if existing:
        raise DashboardError("NAME_TAKEN", "A dashboard with that name already exists in this business.")
    dashboard_id = db.new_id()
    now = db.now()
    conn.execute(
        """INSERT INTO saved_dashboard
           (id, tenant_id, name, description, config_json, visibility, created_by,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (dashboard_id, tenant_id, name, (description or "").strip(),
         json.dumps(clean, ensure_ascii=False), visibility, user_id, now, now),
    )
    acct.audit(conn, tenant_id, user_id, "dashboard.created", "saved_dashboard",
               dashboard_id, meta={"name": name, "visibility": visibility,
                                   "metrics": clean["metrics"], "charts": clean["charts"]})
    return dashboard_id


def delete_dashboard(conn: sqlite3.Connection, tenant_id: str, user_id: str,
                     dashboard_id: str, can_manage_all: bool = False) -> None:
    row = conn.execute(
        "SELECT * FROM saved_dashboard WHERE id=? AND tenant_id=?",
        (dashboard_id, tenant_id),
    ).fetchone()
    if not row:
        raise DashboardError("NOT_FOUND", "Dashboard not found in this business.")
    if row["created_by"] != user_id and not can_manage_all:
        raise DashboardError("FORBIDDEN",
                             "Only the creator or an owner/admin can delete this dashboard.")
    conn.execute("DELETE FROM saved_dashboard WHERE id=? AND tenant_id=?",
                 (dashboard_id, tenant_id))
    acct.audit(conn, tenant_id, user_id, "dashboard.deleted", "saved_dashboard",
               dashboard_id, meta={"name": row["name"]})
