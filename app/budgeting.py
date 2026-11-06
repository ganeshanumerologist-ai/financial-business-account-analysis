"""Budget planning data and the deterministic budget-vs-actual report.

Budgets are planning records, not journal entries. They never change a posted
balance. The report compares the stored budget with actual posted income and
expense lines; it does not forecast or invent a missing budget.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from . import accounting as acct, db


class BudgetError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _tenant_id(tenant) -> str:
    if isinstance(tenant, str):
        return tenant
    try:
        return tenant["id"]
    except (KeyError, IndexError, TypeError):
        raise BudgetError("BAD_TENANT", "A tenant is required")


def _parse_month(period: str) -> str:
    text = (period or "").strip()
    if len(text) != 7 or text[4] != "-":
        raise BudgetError("BAD_PERIOD", "Budget period must be YYYY-MM")
    try:
        date.fromisoformat(text + "-01")
    except ValueError:
        raise BudgetError("BAD_PERIOD", "Budget period must be a valid YYYY-MM month")
    return text


def _validate_period(date_from: str, date_to: str) -> None:
    try:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    except (TypeError, ValueError):
        raise BudgetError("BAD_DATE", "From and To must be valid YYYY-MM-DD dates")
    if start > end:
        raise BudgetError("BAD_PERIOD", "From date must be on or before To date")


def _months(date_from: str, date_to: str) -> list[str]:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    out = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return out


def set_budget(conn: sqlite3.Connection, tenant_id: str, account_id: str,
               period: str, amount_paise: int, note: str = "",
               user_id: str | None = None) -> str:
    """Create or update one monthly budget. Additive and audited."""
    period = _parse_month(period)
    if amount_paise < 0:
        raise BudgetError("NEGATIVE_BUDGET", "Budget amount cannot be negative")
    account = conn.execute(
        "SELECT id, type, status FROM account WHERE id=? AND tenant_id=?",
        (account_id, tenant_id),
    ).fetchone()
    if not account:
        raise BudgetError("ACCOUNT_NOT_FOUND", "Account is not in this business")
    if account["type"] not in ("income", "expense"):
        raise BudgetError("BAD_ACCOUNT_TYPE", "Budgets are only for income and expense ledgers")
    if account["status"] != "active":
        raise BudgetError("ACCOUNT_ARCHIVED", "Archived ledgers cannot receive a new budget")

    now = db.now()
    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute("SAVEPOINT sp_budget")
    try:
        existing = conn.execute(
            "SELECT id, amount_paise FROM budget WHERE tenant_id=? AND account_id=? AND period=?",
            (tenant_id, account_id, period),
        ).fetchone()
        if existing:
            budget_id = existing["id"]
            conn.execute(
                "UPDATE budget SET amount_paise=?, note=?, updated_at=?, updated_by=? WHERE id=?",
                (amount_paise, note[:200], now, user_id, budget_id),
            )
            action = "budget.update"
            old_amount = int(existing["amount_paise"] or 0)
        else:
            budget_id = db.new_id()
            conn.execute(
                "INSERT INTO budget (id, tenant_id, account_id, period, amount_paise, note,"
                " created_by, created_at, updated_at, updated_by)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (budget_id, tenant_id, account_id, period, amount_paise, note[:200],
                 user_id, now, now, user_id),
            )
            action = "budget.create"
            old_amount = None
        acct.audit(
            conn, tenant_id, user_id, action, "budget", budget_id,
            meta={"account_id": account_id, "period": period,
                  "old_amount_paise": old_amount, "amount_paise": amount_paise},
        )
        if own_tx:
            conn.execute("COMMIT")
        else:
            conn.execute("RELEASE sp_budget")
        return budget_id
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        else:
            conn.execute("ROLLBACK TO sp_budget")
            conn.execute("RELEASE sp_budget")
        raise


def delete_budget(conn: sqlite3.Connection, tenant_id: str, budget_id: str,
                  user_id: str | None = None) -> None:
    """Delete one budget row with an audit record. No journal is changed."""
    row = conn.execute(
        "SELECT id, account_id, period, amount_paise FROM budget WHERE id=? AND tenant_id=?",
        (budget_id, tenant_id),
    ).fetchone()
    if not row:
        raise BudgetError("BUDGET_NOT_FOUND", "Budget row not found")
    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute("SAVEPOINT sp_budget_delete")
    try:
        conn.execute("DELETE FROM budget WHERE id=? AND tenant_id=?", (budget_id, tenant_id))
        acct.audit(
            conn, tenant_id, user_id, "budget.delete", "budget", budget_id,
            meta={"account_id": row["account_id"], "period": row["period"],
                  "amount_paise": int(row["amount_paise"] or 0)},
        )
        if own_tx:
            conn.execute("COMMIT")
        else:
            conn.execute("RELEASE sp_budget_delete")
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        else:
            conn.execute("ROLLBACK TO sp_budget_delete")
            conn.execute("RELEASE sp_budget_delete")
        raise


def register(conn: sqlite3.Connection, tenant, date_from: str, date_to: str) -> dict:
    """Budget rows in a date range, for the entry screen."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    rows = conn.execute(
        """SELECT b.id, b.period, b.amount_paise, b.note, b.updated_at,
                  a.code, a.name, a.type,
                  COALESCE(u.full_name, '') AS updated_by_name
           FROM budget b
           JOIN account a ON a.id=b.account_id AND a.tenant_id=b.tenant_id
           LEFT JOIN user u ON u.id=b.updated_by
           WHERE b.tenant_id=? AND b.period BETWEEN ? AND ?
           ORDER BY b.period DESC, a.code""",
        (tenant_id, date_from[:7], date_to[:7]),
    ).fetchall()
    out = [{
        "id": r["id"], "period": r["period"], "amount": int(r["amount_paise"] or 0),
        "note": r["note"], "updated_at": r["updated_at"],
        "code": r["code"], "name": r["name"], "type": r["type"],
        "updated_by_name": r["updated_by_name"],
    } for r in rows]
    return {
        "from": date_from, "to": date_to, "rows": out,
        "totals": {
            "entries": len(out),
            "amount": sum(r["amount"] for r in out),
            "accounts": len({r["code"] for r in out}),
        },
    }


def budget_vs_actual(conn: sqlite3.Connection, tenant, date_from: str,
                     date_to: str) -> dict:
    """R-901: actual posted income/expense against stored monthly budgets."""
    _validate_period(date_from, date_to)
    tenant_id = _tenant_id(tenant)
    actual_rows = conn.execute(
        """SELECT a.id, a.code, a.name, a.type,
                  COALESCE(SUM(CASE WHEN a.type='income'
                                    THEN l.credit_paise - l.debit_paise
                                    ELSE l.debit_paise - l.credit_paise END), 0) AS actual
           FROM account a
           JOIN journal_line l ON l.account_id=a.id AND l.tenant_id=a.tenant_id
           JOIN journal_entry e ON e.id=l.entry_id AND e.tenant_id=l.tenant_id
           WHERE a.tenant_id=? AND a.type IN ('income','expense')
             AND e.entry_date BETWEEN ? AND ?
           GROUP BY a.id""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    actual_map = {r["id"]: int(r["actual"] or 0) for r in actual_rows}
    budget_rows = conn.execute(
        """SELECT account_id, COALESCE(SUM(amount_paise),0) AS budget,
                  COUNT(*) AS months
           FROM budget
           WHERE tenant_id=? AND period BETWEEN ? AND ?
           GROUP BY account_id""",
        (tenant_id, date_from[:7], date_to[:7]),
    ).fetchall()
    budget_map = {r["account_id"]: (int(r["budget"] or 0), int(r["months"] or 0))
                  for r in budget_rows}
    accounts = conn.execute(
        """SELECT id, code, name, type, status
           FROM account
           WHERE tenant_id=? AND type IN ('income','expense')
           ORDER BY CASE type WHEN 'income' THEN 0 ELSE 1 END, code""",
        (tenant_id,),
    ).fetchall()
    rows = []
    for a in accounts:
        actual = actual_map.get(a["id"], 0)
        budget, months = budget_map.get(a["id"], (0, 0))
        if actual == 0 and months == 0:
            continue
        variance = actual - budget
        has_budget = months > 0
        if not has_budget:
            status = "No budget"
            favourable = None
        elif variance == 0:
            status = "On budget"
            favourable = True
        elif (a["type"] == "income" and variance > 0) or (
                a["type"] == "expense" and variance < 0):
            status = "Favourable"
            favourable = True
        else:
            status = "Unfavourable"
            favourable = False
        rows.append({
            "account_id": a["id"], "code": a["code"], "name": a["name"],
            "type": a["type"], "status": a["status"],
            "budget": budget, "actual": actual, "variance": variance,
            "variance_pct": (variance / budget) if budget else None,
            "favourable": favourable, "has_budget": has_budget,
            "budget_months": months,
        })

    def total(kind: str, field: str) -> int:
        return sum(r[field] for r in rows if r["type"] == kind)

    income_budget = total("income", "budget")
    income_actual = total("income", "actual")
    expense_budget = total("expense", "budget")
    expense_actual = total("expense", "actual")
    net_budget = income_budget - expense_budget
    net_actual = income_actual - expense_actual
    return {
        "from": date_from, "to": date_to, "months": _months(date_from, date_to),
        "rows": rows,
        "totals": {
            "accounts": len(rows),
            "budgeted_accounts": sum(1 for r in rows if r["has_budget"]),
            "unbudgeted_accounts": sum(1 for r in rows if not r["has_budget"]),
            "income_budget": income_budget,
            "income_actual": income_actual,
            "income_variance": income_actual - income_budget,
            "expense_budget": expense_budget,
            "expense_actual": expense_actual,
            "expense_variance": expense_actual - expense_budget,
            "net_budget": net_budget,
            "net_actual": net_actual,
            "net_variance": net_actual - net_budget,
            "net_favourable": net_actual >= net_budget,
        },
        "method": "Budget is the stored monthly planning amount for the selected months. "
                  "Actual is posted income (credit - debit) or expense (debit - credit). "
                  "Variance is actual - budget. Budgets never change a posted balance.",
    }
