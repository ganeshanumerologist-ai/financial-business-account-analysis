"""Double-entry accounting core: posting, invoicing, reports.

All amounts are integer paise. Every posting is validated, balanced and atomic.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date

from . import db
from .money import mul_qty_price, split_tax, tax_on


class AccountingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _today_iso() -> str:
    return date.today().isoformat()


def _assert_period_open(conn: sqlite3.Connection, tenant_id: str, on_date: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM period_lock WHERE tenant_id=? AND ? BETWEEN period_start AND period_end",
        (tenant_id, on_date),
    ).fetchone()
    if row:
        raise AccountingError("PERIOD_LOCKED", f"Period containing {on_date} is locked")


def _assert_accounts(conn: sqlite3.Connection, tenant_id: str, account_ids: set[str]) -> None:
    for aid in account_ids:
        row = conn.execute(
            "SELECT is_postable FROM account WHERE id=? AND tenant_id=?", (aid, tenant_id)
        ).fetchone()
        if not row:
            raise AccountingError("ACCOUNT_NOT_FOUND", f"Account {aid} not in this tenant")
        if not row["is_postable"]:
            raise AccountingError("ACCOUNT_NOT_POSTABLE", f"Account {aid} is not postable")


def audit(conn: sqlite3.Connection, tenant_id: str | None, actor: str | None, action: str,
          target_type: str | None = None, target_id: str | None = None,
          result: str = "success", meta: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (id, tenant_id, actor_user_id, action, target_type, target_id, result, meta, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (db.new_id(), tenant_id, actor, action, target_type, target_id, result,
         json.dumps(meta or {}), db.now()),
    )


# --------------------------------------------------------------------------
# journal posting
# --------------------------------------------------------------------------

def post_journal(conn: sqlite3.Connection, tenant_id: str, entry_date: str, narration: str,
                 lines: list[dict], source_type: str, source_id: str | None = None,
                 idempotency_key: str | None = None, created_by: str | None = None) -> str:
    """Post a balanced journal entry atomically. Returns entry id.

    lines: [{"account_id":..., "debit": paise, "credit": paise, "memo":...}]
    """
    if len(lines) < 2:
        raise AccountingError("TOO_FEW_LINES", "A journal entry needs at least two lines")

    total_debit = total_credit = 0
    clean = []
    for ln in lines:
        d = int(ln.get("debit", 0))
        c = int(ln.get("credit", 0))
        if d < 0 or c < 0:
            raise AccountingError("NEGATIVE_AMOUNT", "Debit/credit must be >= 0")
        if (d == 0) == (c == 0):
            raise AccountingError("LINE_SIDE", "Exactly one of debit/credit must be non-zero")
        total_debit += d
        total_credit += c
        clean.append((ln["account_id"], d, c, ln.get("memo"), ln.get("party_id")))

    if total_debit != total_credit:
        raise AccountingError(
            "UNBALANCED",
            f"Entry does not balance: debit {total_debit} != credit {total_credit}",
        )
    if total_debit == 0:
        raise AccountingError("ZERO_ENTRY", "Entry has no value")

    _assert_accounts(conn, tenant_id, {c[0] for c in clean})
    _assert_period_open(conn, tenant_id, entry_date)

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            row = conn.execute(
                "SELECT id FROM journal_entry WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if row:
                conn.execute("COMMIT")
                return row["id"]

        entry_id = db.new_id()
        entry_no = db.next_number(conn, tenant_id, "journal", "JV")
        conn.execute(
            "INSERT INTO journal_entry (id, tenant_id, entry_no, entry_date, narration, source_type,"
            " source_id, idempotency_key, status, posted_at, created_by)"
            " VALUES (?,?,?,?,?,?,?,?, 'posted', ?, ?)",
            (entry_id, tenant_id, entry_no, entry_date, narration, source_type,
             source_id, idempotency_key, db.now(), created_by),
        )
        for i, (aid, d, c, memo, party) in enumerate(clean, start=1):
            conn.execute(
                "INSERT INTO journal_line (id, tenant_id, entry_id, line_no, account_id, party_id,"
                " debit_paise, credit_paise, memo) VALUES (?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, entry_id, i, aid, party, d, c, memo),
            )
        audit(conn, tenant_id, created_by, "ledger.post", "journal_entry", entry_id,
              meta={"amount": total_debit, "lines": len(clean), "source": source_type})
        conn.execute("COMMIT")
        return entry_id
    except Exception:
        conn.execute("ROLLBACK")
        raise


def reverse_entry(conn: sqlite3.Connection, tenant_id: str, entry_id: str, reason: str,
                  created_by: str | None = None) -> str:
    if not reason or not reason.strip():
        raise AccountingError("REASON_REQUIRED", "A reversal reason is required")
    entry = conn.execute(
        "SELECT * FROM journal_entry WHERE id=? AND tenant_id=?", (entry_id, tenant_id)
    ).fetchone()
    if not entry:
        raise AccountingError("ENTRY_NOT_FOUND", "Journal entry not found")
    if entry["status"] == "reversed":
        raise AccountingError("ALREADY_REVERSED", "Entry is already reversed")

    lines = conn.execute(
        "SELECT * FROM journal_line WHERE entry_id=? ORDER BY line_no", (entry_id,)
    ).fetchall()
    mirrored = [{"account_id": l["account_id"], "debit": l["credit_paise"],
                 "credit": l["debit_paise"], "party_id": l["party_id"],
                 "memo": f"Reversal: {reason}"} for l in lines]

    new_id = post_journal(conn, tenant_id, entry["entry_date"], f"Reversal of {entry['entry_no']}: {reason}",
                          mirrored, source_type="reversal", source_id=entry_id, created_by=created_by)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE journal_entry SET status='reversed' WHERE id=?", (entry_id,))
        conn.execute("UPDATE journal_entry SET reversal_of=? WHERE id=?", (entry_id, new_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return new_id


# --------------------------------------------------------------------------
# invoicing
# --------------------------------------------------------------------------

def create_invoice(conn: sqlite3.Connection, tenant_id: str, customer_id: str, invoice_date: str,
                   place_of_supply_state: str, items: list[dict],
                   idempotency_key: str | None = None, round_to_rupee: bool = False,
                   created_by: str | None = None) -> dict:
    """Create + post an invoice. items: [{item_id, qty, unit_price, discount, tax_rate_bp}]"""
    if not items:
        raise AccountingError("NO_ITEMS", "An invoice needs at least one line")

    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    if not tenant:
        raise AccountingError("TENANT_NOT_FOUND", "Tenant not found")
    customer = conn.execute(
        "SELECT * FROM customer WHERE id=? AND tenant_id=?", (customer_id, tenant_id)
    ).fetchone()
    if not customer:
        raise AccountingError("CUSTOMER_NOT_FOUND", "Customer not in this tenant")
    _assert_period_open(conn, tenant_id, invoice_date)

    intra = place_of_supply_state == tenant["state_code"]

    computed = []
    sub_total = tax_total = cogs_total = 0
    revenue_by_account: dict[str, int] = {}
    for ln in items:
        item = conn.execute(
            "SELECT * FROM item WHERE id=? AND tenant_id=?", (ln["item_id"], tenant_id)
        ).fetchone()
        if not item:
            raise AccountingError("ITEM_NOT_FOUND", f"Item {ln['item_id']} not in this tenant")

        qty_milli = int(ln["qty"])
        price = int(ln.get("unit_price", item["sale_price_paise"]))
        discount = int(ln.get("discount", 0))
        rate_bp = int(ln.get("tax_rate_bp", item["tax_rate_bp"]))
        if qty_milli <= 0:
            raise AccountingError("BAD_QTY", "Quantity must be positive")
        if price < 0 or discount < 0 or rate_bp < 0:
            raise AccountingError("BAD_AMOUNT", "Negative price/discount/rate")

        gross = mul_qty_price(qty_milli, price)
        if discount > gross:
            raise AccountingError("BAD_DISCOUNT", "Discount cannot exceed line value")
        taxable = gross - discount
        tax = tax_on(taxable, rate_bp)
        line_total = taxable + tax

        if item["track_stock"]:
            if item["stock_milli"] < qty_milli:
                raise AccountingError(
                    "INSUFFICIENT_STOCK",
                    f"Not enough stock for {item['name']}: have {item['stock_milli']/1000:.3f}, need {qty_milli/1000:.3f}",
                )
            cogs_total += (item["cost_paise"] * qty_milli + 500) // 1000

        sub_total += taxable
        tax_total += tax
        revenue_by_account[item["revenue_code"]] = revenue_by_account.get(item["revenue_code"], 0) + taxable
        computed.append({
            "item_id": item["id"], "description": ln.get("description", item["name"]),
            "qty_milli": qty_milli, "unit_price_paise": price, "gross_paise": gross,
            "discount_paise": discount, "taxable_paise": taxable, "tax_rate_bp": rate_bp,
            "tax_paise": tax, "line_total_paise": line_total,
        })

    base_total = sub_total + tax_total
    if round_to_rupee:
        total = ((base_total + 50) // 100) * 100
    else:
        total = base_total
    round_off = total - base_total

    acct = db.account_id
    ar = acct(conn, tenant_id, "1100")
    cogs = acct(conn, tenant_id, "5000")
    inventory = acct(conn, tenant_id, "1200")
    round_acc = acct(conn, tenant_id, "5900")

    if intra:
        cgst, sgst = split_tax(tax_total)
        tax_lines = [(acct(conn, tenant_id, "2100"), cgst), (acct(conn, tenant_id, "2101"), sgst)]
    else:
        tax_lines = [(acct(conn, tenant_id, "2102"), tax_total)]

    lines = [{"account_id": ar, "debit": total, "credit": 0, "party_id": customer_id,
              "memo": "Invoice receivable"}]
    for code, amount in revenue_by_account.items():
        if not amount:
            continue
        try:
            revenue_account = acct(conn, tenant_id, code)
        except KeyError as exc:
            raise AccountingError("REVENUE_ACCOUNT_NOT_FOUND",
                                  f"Revenue account {code} is missing from the chart of accounts") from exc
        lines.append({"account_id": revenue_account, "debit": 0, "credit": amount,
                      "memo": "Revenue"})
    for acc, amt in tax_lines:
        if amt:
            lines.append({"account_id": acc, "debit": 0, "credit": amt, "memo": "GST output"})
    if cogs_total:
        lines.append({"account_id": cogs, "debit": cogs_total, "credit": 0, "memo": "COGS"})
        lines.append({"account_id": inventory, "debit": 0, "credit": cogs_total, "memo": "Inventory out"})
    if round_off > 0:
        lines.append({"account_id": round_acc, "debit": 0, "credit": round_off, "memo": "Round off"})
    elif round_off < 0:
        lines.append({"account_id": round_acc, "debit": -round_off, "credit": 0, "memo": "Round off"})

    entry_id = post_journal(conn, tenant_id, invoice_date,
                            f"Invoice for {customer['name']}", lines,
                            source_type="invoice", idempotency_key=idempotency_key,
                            created_by=created_by)

    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            "SELECT * FROM invoice WHERE tenant_id=? AND journal_entry_id=?",
            (tenant_id, entry_id),
        ).fetchone()
        if existing:
            conn.execute("COMMIT")
            return dict(existing)

        invoice_id = db.new_id()
        invoice_no = db.next_number(conn, tenant_id, "invoice", "INV")
        conn.execute(
            "INSERT INTO invoice (id, tenant_id, invoice_no, invoice_date, customer_id,"
            " place_of_supply_state, sub_total_paise, tax_paise, round_off_paise, total_paise,"
            " status, idempotency_key, journal_entry_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?, 'posted', ?,?,?)",
            (invoice_id, tenant_id, invoice_no, invoice_date, customer_id, place_of_supply_state,
             sub_total, tax_total, round_off, total, idempotency_key, entry_id, db.now()),
        )
        for c in computed:
            conn.execute(
                "INSERT INTO invoice_line (id, tenant_id, invoice_id, item_id, description, qty_milli,"
                " unit_price_paise, gross_paise, discount_paise, taxable_paise, tax_rate_bp,"
                " tax_paise, line_total_paise) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, invoice_id, c["item_id"], c["description"], c["qty_milli"],
                 c["unit_price_paise"], c["gross_paise"], c["discount_paise"], c["taxable_paise"],
                 c["tax_rate_bp"], c["tax_paise"], c["line_total_paise"]),
            )
            conn.execute(
                "UPDATE item SET stock_milli = stock_milli - ? WHERE id=?",
                (c["qty_milli"], c["item_id"]),
            )
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (invoice_id, entry_id))
        audit(conn, tenant_id, created_by, "invoice.create", "invoice", invoice_id,
              meta={"total": total, "invoice_no": invoice_no})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM invoice WHERE id=?", (invoice_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------

def trial_balance(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or _today_iso()
    rows = conn.execute(
        """
        SELECT a.id, a.code, a.name, a.type,
               COALESCE(SUM(l.debit_paise),0)  AS debit,
               COALESCE(SUM(l.credit_paise),0) AS credit
        FROM account a
        LEFT JOIN journal_line l ON l.account_id = a.id AND l.tenant_id = a.tenant_id
        LEFT JOIN journal_entry e ON e.id = l.entry_id AND e.entry_date <= ?
        WHERE a.tenant_id = ?
        GROUP BY a.id
        ORDER BY a.code
        """,
        (as_of, tenant_id),
    ).fetchall()
    out = []
    for r in rows:
        debit = r["debit"] or 0
        credit = r["credit"] or 0
        out.append({"account_id": r["id"], "code": r["code"], "name": r["name"], "type": r["type"],
                    "debit": debit, "credit": credit, "balance": debit - credit})
    total_debit = sum(r["debit"] for r in out)
    total_credit = sum(r["credit"] for r in out)
    return {"as_of": as_of, "rows": out, "total_debit": total_debit,
            "total_credit": total_credit, "balanced": total_debit == total_credit}


def general_ledger(conn: sqlite3.Connection, tenant_id: str, account_id: str,
                   date_from: str, date_to: str) -> dict:
    acct = conn.execute(
        "SELECT * FROM account WHERE id=? AND tenant_id=?", (account_id, tenant_id)
    ).fetchone()
    if not acct:
        raise AccountingError("ACCOUNT_NOT_FOUND", "Account not in this tenant")
    opening_row = conn.execute(
        """SELECT COALESCE(SUM(l.debit_paise - l.credit_paise),0) AS bal
           FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
           WHERE l.tenant_id=? AND l.account_id=? AND e.entry_date < ?""",
        (tenant_id, account_id, date_from),
    ).fetchone()
    opening = opening_row["bal"] or 0
    rows = conn.execute(
        """SELECT e.entry_no, e.entry_date, e.narration, l.debit_paise, l.credit_paise, l.memo
           FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
           WHERE l.tenant_id=? AND l.account_id=? AND e.entry_date BETWEEN ? AND ?
           ORDER BY e.entry_date, e.entry_no, l.line_no""",
        (tenant_id, account_id, date_from, date_to),
    ).fetchall()
    running = opening
    out = []
    for r in rows:
        running += (r["debit_paise"] or 0) - (r["credit_paise"] or 0)
        out.append({"date": r["entry_date"], "ref": r["entry_no"], "narration": r["narration"],
                    "debit": r["debit_paise"], "credit": r["credit_paise"], "balance": running})
    return {"account": dict(acct), "from": date_from, "to": date_to,
            "opening": opening, "rows": out, "closing": running}


def customer_balances(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> list[dict]:
    """AR balance per customer, from party-tagged journal lines."""
    as_of = as_of or _today_iso()
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.phone, c.state_code,
               COALESCE(SUM(p.debit_paise - p.credit_paise), 0) AS balance
        FROM customer c
        LEFT JOIN (
            SELECT l.party_id, l.debit_paise, l.credit_paise
            FROM journal_line l
            JOIN journal_entry e ON e.id = l.entry_id
            WHERE l.tenant_id = ? AND l.party_id IS NOT NULL AND e.entry_date <= ?
        ) p ON p.party_id = c.id
        WHERE c.tenant_id = ?
        GROUP BY c.id
        ORDER BY c.name
        """,
        (tenant_id, as_of, tenant_id),
    ).fetchall()
    return [dict(r) for r in rows]


def customer_statement(conn: sqlite3.Connection, tenant_id: str, customer_id: str,
                       date_from: str, date_to: str) -> dict:
    customer = conn.execute(
        "SELECT * FROM customer WHERE id=? AND tenant_id=?", (customer_id, tenant_id)
    ).fetchone()
    if not customer:
        raise AccountingError("CUSTOMER_NOT_FOUND", "Customer not in this tenant")

    opening = conn.execute(
        """SELECT COALESCE(SUM(l.debit_paise - l.credit_paise), 0) AS bal
           FROM journal_line l JOIN journal_entry e ON e.id = l.entry_id
           WHERE l.tenant_id=? AND l.party_id=? AND e.entry_date < ?""",
        (tenant_id, customer_id, date_from),
    ).fetchone()["bal"] or 0

    rows = conn.execute(
        """SELECT e.entry_no, e.entry_date, e.narration, e.source_type, e.source_id,
                  l.debit_paise, l.credit_paise
           FROM journal_line l JOIN journal_entry e ON e.id = l.entry_id
           WHERE l.tenant_id=? AND l.party_id=? AND e.entry_date BETWEEN ? AND ?
           ORDER BY e.entry_date, e.entry_no, l.line_no""",
        (tenant_id, customer_id, date_from, date_to),
    ).fetchall()

    running = opening
    out = []
    invoiced = received = 0
    for r in rows:
        running += (r["debit_paise"] or 0) - (r["credit_paise"] or 0)
        invoiced += r["debit_paise"] or 0
        received += r["credit_paise"] or 0
        out.append({"date": r["entry_date"], "ref": r["entry_no"], "narration": r["narration"],
                    "source_type": r["source_type"], "source_id": r["source_id"],
                    "debit": r["debit_paise"], "credit": r["credit_paise"], "balance": running})
    return {"customer": dict(customer), "from": date_from, "to": date_to,
            "opening": opening, "rows": out, "closing": running,
            "invoiced": invoiced, "received": received}


def profit_and_loss(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> dict:
    rows = conn.execute(
        """SELECT a.type, a.code, a.name,
                  COALESCE(SUM(l.debit_paise),0) AS debit,
                  COALESCE(SUM(l.credit_paise),0) AS credit
           FROM account a
           JOIN journal_line l ON l.account_id=a.id AND l.tenant_id=a.tenant_id
           JOIN journal_entry e ON e.id=l.entry_id AND e.entry_date BETWEEN ? AND ?
           WHERE a.tenant_id=? AND a.type IN ('income','expense')
           GROUP BY a.id ORDER BY a.code""",
        (date_from, date_to, tenant_id),
    ).fetchall()
    income, expense = [], []
    for r in rows:
        if r["type"] == "income":
            amount = (r["credit"] or 0) - (r["debit"] or 0)
            income.append({"code": r["code"], "name": r["name"], "amount": amount})
        else:
            amount = (r["debit"] or 0) - (r["credit"] or 0)
            expense.append({"code": r["code"], "name": r["name"], "amount": amount})
    total_income = sum(i["amount"] for i in income)
    total_expense = sum(e["amount"] for e in expense)
    return {"from": date_from, "to": date_to, "income": income, "expense": expense,
            "total_income": total_income, "total_expense": total_expense,
            "net_profit": total_income - total_expense}


def balance_sheet(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or _today_iso()
    tb = trial_balance(conn, tenant_id, as_of)
    assets = liabilities = equity = 0
    a_rows, l_rows, e_rows = [], [], []
    for r in tb["rows"]:
        bal = r["balance"]  # debit positive
        if r["type"] == "asset":
            assets += bal
            a_rows.append({**r, "amount": bal})
        elif r["type"] == "liability":
            amt = -bal
            liabilities += amt
            l_rows.append({**r, "amount": amt})
        elif r["type"] == "equity":
            amt = -bal
            equity += amt
            e_rows.append({**r, "amount": amt})

    pnl = profit_and_loss(conn, tenant_id, "0000-01-01", as_of)
    retained = pnl["net_profit"]
    equity += retained
    return {"as_of": as_of, "assets": a_rows, "liabilities": l_rows, "equity": e_rows,
            "total_assets": assets, "total_liabilities": liabilities,
            "retained_earnings": retained, "total_equity": equity,
            "balanced": assets == liabilities + equity,
            "difference": assets - (liabilities + equity)}


def dashboard(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> dict:
    pnl = profit_and_loss(conn, tenant_id, date_from, date_to)
    tb = {r["code"]: r for r in trial_balance(conn, tenant_id, date_to)["rows"]}
    ar = tb.get("1100", {}).get("balance", 0)
    cash = tb.get("1000", {}).get("balance", 0) + tb.get("1010", {}).get("balance", 0)
    inventory = tb.get("1200", {}).get("balance", 0)
    inv_count = conn.execute(
        "SELECT COUNT(*) c FROM invoice WHERE tenant_id=? AND invoice_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchone()["c"]
    return {"revenue": pnl["total_income"], "expense": pnl["total_expense"],
            "profit": pnl["net_profit"], "receivable": ar, "cash": cash,
            "inventory": inventory, "invoice_count": inv_count}
