"""Power BI import pack for ARTHIVIO.

This is a deliberately honest first Power BI slice: a static, read-only ZIP of
the analytics contract and its source facts. It is **not** a `.pbix` file and it
does not add a token-authenticated API. The pack keeps money in integer paise so
Power BI never receives a binary float from ARTHIVIO.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import zipfile
from datetime import date, datetime, timezone

from . import analytics

PACK_SCHEMA_VERSION = "1.0"
PACK_NAME = "arthivio-powerbi-pack"


def _tenant_value(tenant, key: str, default=""):
    try:
        return tenant[key]
    except (KeyError, TypeError, IndexError):
        return default


def _tenant_slug(tenant) -> str:
    raw = str(_tenant_value(tenant, "slug", "business") or "business")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw).strip("-")
    return safe or "business"


def _csv_bytes(headers, rows) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _json_bytes(payload) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _journal_rows(conn, tenant_id: str, date_from: str, date_to: str,
                  limit: int = 200000):
    total = conn.execute(
        """SELECT COUNT(*) AS n FROM v_analytics_journal
           WHERE tenant_id=? AND entry_date BETWEEN ? AND ?""",
        (tenant_id, date_from, date_to),
    ).fetchone()["n"]
    rows = conn.execute(
        """SELECT j.entry_id, j.entry_no, j.entry_date, j.period_month,
                  j.source_type, j.source_id, j.status, j.reversal_of,
                  j.line_id, j.line_no, j.account_id, j.account_code,
                  j.account_name, j.account_type, j.group_code, j.party_id,
                  COALESCE(c.name, v.name, '') AS party_name,
                  j.debit_paise, j.credit_paise, j.signed_paise, j.memo
           FROM v_analytics_journal j
           LEFT JOIN customer c ON c.id=j.party_id AND c.tenant_id=j.tenant_id
           LEFT JOIN vendor v ON v.id=j.party_id AND v.tenant_id=j.tenant_id
           WHERE j.tenant_id=? AND j.entry_date BETWEEN ? AND ?
           ORDER BY j.entry_date, j.entry_no, j.line_no
           LIMIT ?""",
        (tenant_id, date_from, date_to, limit),
    ).fetchall()
    return rows, int(total or 0)


def _readme(tenant, data: dict, journal_total: int, journal_rows: int) -> str:
    return f"""# ARTHIVIO Power BI pack

Business: **{_tenant_value(tenant, "name", "Business")}**
Period: **{data["period"]["from"]} to {data["period"]["to"]}**
Generated: **{data["freshness"]["generated_at"]}**
Contract: **v{data.get("schema_version", analytics.SCHEMA_VERSION)}**

## What this is

A read-only import pack for Power BI Desktop. It contains the same actuals
contract used by the ARTHIVIO web screen and API, plus the source journal facts.

It is **not** a `.pbix` file, a published Power BI Service dataset, a scheduled
refresh, or a token-authenticated API. Those need a separate Power BI scope and
licensing decision.

## Files

| File | Use |
|---|---|
| `arthivio-analytics.json` | Canonical overview snapshot for reconciliation |
| `arthivio-metric-catalog.json` | Metric keys, formula text, source and drill-down |
| `fact_journal.csv` | Posted journal lines in the period, integer paise |
| `fact_monthly.csv` | Month/account-type rollup, integer paise |
| `dim_account.csv` | Chart of accounts |
| `dim_party.csv` | Customer/vendor dimension |
| `power-query/ArthivioAnalytics.m` | Starter M query; edit the folder path |
| `manifest.json` | File hashes, row counts and export metadata |

Journal rows exported: **{journal_rows:,}** of **{journal_total:,}** in the period.

## Import in Power BI Desktop

1. Unzip this pack to a local folder.
2. Open Power BI Desktop -> **Get Data** -> **Text/CSV**.
3. Load `fact_journal.csv`, `fact_monthly.csv`, `dim_account.csv` and `dim_party.csv`.
4. In Power Query, set `entry_date` / `period_month` to Date, and every `*_paise`
   column to **Whole Number**. Do not convert paise to a binary float in the source.
5. Create relationships:
   - `fact_journal[account_id]` -> `dim_account[account_id]`
   - `fact_journal[party_id]` -> `dim_party[party_id]` (optional; blanks are normal)
6. Add the starter measures below. They divide by 100 only at the presentation
   layer, so the ledger remains integer paise.

## Starter DAX measures

```DAX
Revenue (INR) =
DIVIDE (
    CALCULATE (
        SUM ( fact_journal[credit_paise] ) - SUM ( fact_journal[debit_paise] ),
        fact_journal[account_type] = "income"
    ),
    100
)

Expenses (INR) =
DIVIDE (
    CALCULATE (
        SUM ( fact_journal[debit_paise] ) - SUM ( fact_journal[credit_paise] ),
        fact_journal[account_type] = "expense"
    ),
    100
)

Net profit (INR) = [Revenue (INR)] - [Expenses (INR)]

Cash + bank (INR) =
DIVIDE (
    CALCULATE (
        SUM ( fact_journal[debit_paise] ) - SUM ( fact_journal[credit_paise] ),
        fact_journal[group_code] IN {{ "cash", "bank" }}
    ),
    100
)
```

The `arthivio-analytics.json` snapshot is the reconciliation target. If a DAX
measure disagrees with the JSON after applying the same period filter, stop and
investigate before publishing the report.

## Truth, privacy and security

- Actuals only. No estimate or forecast is included.
- The journal is the source of truth; Power BI is a read-only reporting layer.
- GST figures are working aids, not filed returns or claimed ITC.
- This pack is a single-tenant snapshot. It has no row-level security, no user
  authentication and no automatic refresh.
- Treat the ZIP as confidential financial data. Do not publish it to a public
  workspace or upload it to an untrusted service.
- A future Service connector must add scoped tokens, tenant isolation, RLS and
  scheduled refresh; this static pack does not pretend to provide them.
"""


def _power_query() -> str:
    return '''// ARTHIVIO Power BI starter query.
// Change FolderPath to the folder where you unzipped the pack.
let
    FolderPath = "C:\\path\\to\\arthivio-powerbi-pack",
    Journal = Csv.Document(
        File.Contents(FolderPath & "\\fact_journal.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    JournalHeaders = Table.PromoteHeaders(Journal, [PromoteAllScalars = true]),
    Accounts = Csv.Document(
        File.Contents(FolderPath & "\\dim_account.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    AccountHeaders = Table.PromoteHeaders(Accounts, [PromoteAllScalars = true]),
    Parties = Csv.Document(
        File.Contents(FolderPath & "\\dim_party.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PartyHeaders = Table.PromoteHeaders(Parties, [PromoteAllScalars = true])
in
    JournalHeaders
'''


def build_pack(conn: sqlite3.Connection, tenant,
               date_from: str | None = None, date_to: str | None = None) -> bytes:
    """Build a ZIP Power BI import pack for one tenant and period."""
    tenant_id = _tenant_value(tenant, "id")
    period = analytics.resolve_period(tenant, date_from, date_to)
    data = analytics.overview(conn, tenant, period["from"], period["to"])
    journal, journal_total = _journal_rows(conn, tenant_id, period["from"], period["to"])

    journal_headers = [
        "entry_id", "entry_no", "entry_date", "period_month", "source_type", "source_id",
        "status", "reversal_of", "line_id", "line_no", "account_id", "account_code",
        "account_name", "account_type", "group_code", "party_id", "party_name",
        "debit_paise", "credit_paise", "signed_paise", "memo",
    ]
    journal_rows = [[r[key] for key in journal_headers] for r in journal]

    monthly = data["monthly"]["months"]
    monthly_headers = ["period_month", "revenue_paise", "expense_paise", "profit_paise"]
    monthly_rows = [[m["month"], m["revenue_paise"], m["expense_paise"],
                     m["profit_paise"]] for m in monthly]

    account_headers = ["account_id", "code", "name", "type", "group_code", "status",
                       "merged_into_id"]
    accounts = conn.execute(
        """SELECT id AS account_id, code, name, type, group_code, status, merged_into_id
           FROM account WHERE tenant_id=? ORDER BY code""", (tenant_id,)
    ).fetchall()
    account_rows = [[r[key] for key in account_headers] for r in accounts]

    party_headers = ["party_id", "party_type", "name", "gstin", "state_code",
                     "phone", "email", "account_id"]
    parties = conn.execute(
        """SELECT id AS party_id, 'customer' AS party_type, name, gstin, state_code,
                  phone, email, account_id
           FROM customer WHERE tenant_id=?
           UNION ALL
           SELECT id AS party_id, 'vendor' AS party_type, name, gstin, state_code,
                  phone, email, account_id
           FROM vendor WHERE tenant_id=?
           ORDER BY party_type, name""", (tenant_id, tenant_id)
    ).fetchall()
    party_rows = [[r[key] for key in party_headers] for r in parties]

    files = {
        "README.md": _readme(tenant, data, journal_total, len(journal)).encode("utf-8"),
        "arthivio-analytics.json": _json_bytes(data),
        "arthivio-metric-catalog.json": _json_bytes(analytics.catalog()),
        "fact_journal.csv": _csv_bytes(journal_headers, journal_rows),
        "fact_monthly.csv": _csv_bytes(monthly_headers, monthly_rows),
        "dim_account.csv": _csv_bytes(account_headers, account_rows),
        "dim_party.csv": _csv_bytes(party_headers, party_rows),
        "power-query/ArthivioAnalytics.m": _power_query().encode("utf-8"),
    }
    manifest = {
        "pack": PACK_NAME,
        "schema_version": PACK_SCHEMA_VERSION,
        "contract_version": data.get("schema_version", analytics.SCHEMA_VERSION),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "business": _tenant_value(tenant, "name", ""),
        "tenant_slug": _tenant_slug(tenant),
        "period": data["period"],
        "currency": "INR",
        "source_money_unit": "integer paise",
        "actuals_only": True,
        "journal_rows_exported": len(journal),
        "journal_rows_in_period": journal_total,
        "files": {name: {"bytes": len(blob), "sha256": _sha256(blob)}
                  for name, blob in files.items()},
        "limitations": [
            "Static snapshot, not a scheduled Power BI Service dataset.",
            "No token-authenticated API, RLS or multi-tenant connector in this pack.",
            "No estimate or forecast is included.",
            "GST figures are working aids, not filed returns or claimed ITC.",
        ],
    }
    files["manifest.json"] = _json_bytes(manifest)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, blob in files.items():
            zf.writestr(name, blob)
    return buf.getvalue()


def filename(tenant, date_to: str | None = None) -> str:
    return f"{PACK_NAME}-{_tenant_slug(tenant)}-{date_to or date.today().isoformat()}.zip"
