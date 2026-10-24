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

    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute("SAVEPOINT sp_post_journal")
    try:
        if idempotency_key:
            row = conn.execute(
                "SELECT id FROM journal_entry WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if row:
                if own_tx:
                    conn.execute("COMMIT")
                else:
                    conn.execute("RELEASE sp_post_journal")
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
        if own_tx:
            conn.execute("COMMIT")
        else:
            conn.execute("RELEASE sp_post_journal")
        return entry_id
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        else:
            conn.execute("ROLLBACK TO sp_post_journal")
            conn.execute("RELEASE sp_post_journal")
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

    conn.execute("BEGIN IMMEDIATE")
    try:
        new_id = post_journal(conn, tenant_id, entry["entry_date"],
                              f"Reversal of {entry['entry_no']}: {reason}",
                              mirrored, source_type="reversal", source_id=entry_id,
                              created_by=created_by)
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
            "track_stock": bool(item["track_stock"]),
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

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM invoice WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, invoice_date,
                                f"Invoice for {customer['name']}", lines,
                                source_type="invoice", idempotency_key=idempotency_key,
                                created_by=created_by)
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
            if c["track_stock"]:
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
# receivables / payables: receipts, vendor payments, bills, credit notes
# --------------------------------------------------------------------------

CASH_ACCOUNT = "1000"
BANK_ACCOUNT = "1010"
AR_ACCOUNT = "1100"
AP_ACCOUNT = "2000"


def _doc_or_raise(conn: sqlite3.Connection, tenant_id: str, table: str, doc_id: str,
                  label: str) -> sqlite3.Row:
    row = conn.execute(
        f"SELECT * FROM {table} WHERE id=? AND tenant_id=?", (doc_id, tenant_id)
    ).fetchone()
    if not row:
        raise AccountingError("DOC_NOT_FOUND", f"{label} not found in this business")
    return row


def invoice_outstanding(conn: sqlite3.Connection, tenant_id: str, invoice_id: str) -> int:
    inv = _doc_or_raise(conn, tenant_id, "invoice", invoice_id, "Invoice")
    allocated = conn.execute(
        "SELECT COALESCE(SUM(amount_paise),0) a FROM payment_allocation"
        " WHERE tenant_id=? AND doc_type='invoice' AND doc_id=?",
        (tenant_id, invoice_id),
    ).fetchone()["a"]
    credited = conn.execute(
        "SELECT COALESCE(SUM(total_paise),0) c FROM credit_note"
        " WHERE tenant_id=? AND invoice_id=?",
        (tenant_id, invoice_id),
    ).fetchone()["c"]
    return inv["total_paise"] - allocated - credited


def bill_outstanding(conn: sqlite3.Connection, tenant_id: str, bill_id: str) -> int:
    bill = _doc_or_raise(conn, tenant_id, "bill", bill_id, "Bill")
    allocated = conn.execute(
        "SELECT COALESCE(SUM(amount_paise),0) a FROM payment_allocation"
        " WHERE tenant_id=? AND doc_type='bill' AND doc_id=?",
        (tenant_id, bill_id),
    ).fetchone()["a"]
    debited = conn.execute(
        "SELECT COALESCE(SUM(total_paise),0) d FROM debit_note"
        " WHERE tenant_id=? AND bill_id=?",
        (tenant_id, bill_id),
    ).fetchone()["d"]
    return bill["total_paise"] - allocated - debited


def record_payment(conn: sqlite3.Connection, tenant_id: str, direction: str, party_id: str,
                   payment_date: str, amount_paise: int, mode: str = "bank",
                   allocations: list[dict] | None = None, reference: str = "", notes: str = "",
                   idempotency_key: str | None = None, created_by: str | None = None) -> dict:
    """Record a customer receipt or a vendor payment, optionally allocating it to documents."""
    if direction not in ("receipt", "payment"):
        raise AccountingError("BAD_DIRECTION", "Direction must be receipt or payment")
    if amount_paise <= 0:
        raise AccountingError("BAD_AMOUNT", "Payment amount must be greater than zero")
    if mode not in ("cash", "bank", "upi", "cheque", "card"):
        raise AccountingError("BAD_MODE", "Unknown payment mode")

    if idempotency_key:
        existing = conn.execute(
            "SELECT * FROM payment WHERE tenant_id=? AND idempotency_key=?",
            (tenant_id, idempotency_key),
        ).fetchone()
        if existing:
            return dict(existing)

    party_type = "customer" if direction == "receipt" else "vendor"
    table = "customer" if direction == "receipt" else "vendor"
    party = _doc_or_raise(conn, tenant_id, table, party_id, party_type.title())
    _assert_period_open(conn, tenant_id, payment_date)

    allocations = allocations or []
    total_alloc = 0
    for al in allocations:
        doc_type = al["doc_type"]
        expected = "invoice" if direction == "receipt" else "bill"
        if doc_type != expected:
            raise AccountingError("BAD_ALLOCATION", f"{direction} can only allocate to {expected}s")
        if int(al["amount"]) <= 0:
            raise AccountingError("BAD_ALLOCATION", "Allocation amount must be positive")
        if doc_type == "invoice":
            outstanding = invoice_outstanding(conn, tenant_id, al["doc_id"])
        else:
            outstanding = bill_outstanding(conn, tenant_id, al["doc_id"])
        if int(al["amount"]) > outstanding:
            raise AccountingError(
                "OVER_ALLOCATION",
                f"Allocation {al['amount']} exceeds outstanding {outstanding} for {doc_type}",
            )
        total_alloc += int(al["amount"])
    if total_alloc > amount_paise:
        raise AccountingError("OVER_ALLOCATION", "Allocations exceed the payment amount")

    cash_or_bank = db.account_id(
        conn, tenant_id, CASH_ACCOUNT if mode == "cash" else BANK_ACCOUNT
    )
    if direction == "receipt":
        ar = db.account_id(conn, tenant_id, AR_ACCOUNT)
        lines = [
            {"account_id": cash_or_bank, "debit": amount_paise, "credit": 0,
             "memo": f"Receipt from {party['name']}"},
            {"account_id": ar, "debit": 0, "credit": amount_paise, "party_id": party_id,
             "memo": f"Receipt from {party['name']}"},
        ]
        narration = f"Receipt from {party['name']}" + (f" ({reference})" if reference else "")
        prefix, doc_type = "RCPT", "receipt"
    else:
        ap = db.account_id(conn, tenant_id, AP_ACCOUNT)
        lines = [
            {"account_id": ap, "debit": amount_paise, "credit": 0, "party_id": party_id,
             "memo": f"Payment to {party['name']}"},
            {"account_id": cash_or_bank, "debit": 0, "credit": amount_paise,
             "memo": f"Payment to {party['name']}"},
        ]
        narration = f"Payment to {party['name']}" + (f" ({reference})" if reference else "")
        prefix, doc_type = "PYMT", "payment"

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM payment WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, payment_date, narration, lines,
                                source_type=doc_type, idempotency_key=idempotency_key,
                                created_by=created_by)
        payment_id = db.new_id()
        voucher_no = db.next_number(conn, tenant_id, doc_type, prefix)
        conn.execute(
            "INSERT INTO payment (id, tenant_id, voucher_no, payment_date, direction, party_type,"
            " party_id, mode, account_id, amount_paise, reference, notes, journal_entry_id,"
            " idempotency_key, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (payment_id, tenant_id, voucher_no, payment_date, direction, party_type, party_id,
             mode, cash_or_bank, amount_paise, reference[:120], notes[:500], entry_id,
             idempotency_key, db.now()),
        )
        for al in allocations:
            conn.execute(
                "INSERT INTO payment_allocation (id, tenant_id, payment_id, doc_type, doc_id,"
                " amount_paise) VALUES (?,?,?,?,?,?)",
                (db.new_id(), tenant_id, payment_id, al["doc_type"], al["doc_id"], int(al["amount"])),
            )
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (payment_id, entry_id))
        audit(conn, tenant_id, created_by, f"payment.{direction}", "payment", payment_id,
              meta={"amount": amount_paise, "mode": mode, "allocations": len(allocations)})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM payment WHERE id=?", (payment_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


def create_bill(conn: sqlite3.Connection, tenant_id: str, vendor_id: str, bill_date: str,
                vendor_bill_no: str, place_of_supply_state: str, items: list[dict],
                idempotency_key: str | None = None, round_to_rupee: bool = False,
                created_by: str | None = None) -> dict:
    """Post a purchase bill: input GST, inventory/purchases, and accounts payable."""
    if not items:
        raise AccountingError("NO_ITEMS", "A bill needs at least one line")
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    if not tenant:
        raise AccountingError("TENANT_NOT_FOUND", "Tenant not found")
    vendor = _doc_or_raise(conn, tenant_id, "vendor", vendor_id, "Vendor")
    _assert_period_open(conn, tenant_id, bill_date)

    intra = place_of_supply_state == tenant["state_code"]
    computed = []
    sub_total = tax_total = 0
    stock_value = 0
    purchase_value = 0

    for ln in items:
        item = _doc_or_raise(conn, tenant_id, "item", ln["item_id"], "Item")
        qty_milli = int(ln["qty"])
        price = int(ln.get("unit_price", item["cost_paise"]))
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

        if item["track_stock"]:
            stock_value += taxable
            old_qty = item["stock_milli"]
            old_cost = item["cost_paise"]
            new_qty = old_qty + qty_milli
            # old_qty is in thousandths; taxable is paise for the purchased quantity.
            # Convert taxable to milli-paise so both sides share the same unit.
            new_cost = ((old_qty * old_cost + taxable * 1000) + new_qty // 2) // new_qty if new_qty else price
        else:
            purchase_value += taxable

        sub_total += taxable
        tax_total += tax
        computed.append({
            "item_id": item["id"], "description": ln.get("description", item["name"]),
            "qty_milli": qty_milli, "unit_price_paise": price, "gross_paise": gross,
            "discount_paise": discount, "taxable_paise": taxable, "tax_rate_bp": rate_bp,
            "tax_paise": tax, "line_total_paise": taxable + tax,
            "new_qty": item["stock_milli"] + qty_milli if item["track_stock"] else None,
            "new_cost": new_cost if item["track_stock"] else None,
        })

    base_total = sub_total + tax_total
    total = ((base_total + 50) // 100) * 100 if round_to_rupee else base_total
    round_off = total - base_total

    acct = db.account_id
    ap = acct(conn, tenant_id, AP_ACCOUNT)
    inventory = acct(conn, tenant_id, "1200")
    purchases = acct(conn, tenant_id, "5100")
    round_acc = acct(conn, tenant_id, "5900")

    if intra:
        cgst, sgst = split_tax(tax_total)
        tax_lines = [(acct(conn, tenant_id, "2200"), cgst), (acct(conn, tenant_id, "2201"), sgst)]
    else:
        tax_lines = [(acct(conn, tenant_id, "2202"), tax_total)]

    lines = [{"account_id": ap, "debit": 0, "credit": total, "party_id": vendor_id,
              "memo": "Bill payable"}]
    if stock_value:
        lines.append({"account_id": inventory, "debit": stock_value, "credit": 0,
                      "memo": "Inventory in"})
    if purchase_value:
        lines.append({"account_id": purchases, "debit": purchase_value, "credit": 0,
                      "memo": "Purchases"})
    for acc, amt in tax_lines:
        if amt:
            lines.append({"account_id": acc, "debit": amt, "credit": 0, "memo": "GST input"})
    if round_off > 0:
        lines.append({"account_id": round_acc, "debit": round_off, "credit": 0, "memo": "Round off"})
    elif round_off < 0:
        lines.append({"account_id": round_acc, "debit": 0, "credit": -round_off, "memo": "Round off"})

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM bill WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, bill_date, f"Bill from {vendor['name']}", lines,
                                source_type="bill", idempotency_key=idempotency_key,
                                created_by=created_by)
        bill_id = db.new_id()
        bill_no = db.next_number(conn, tenant_id, "bill", "BILL")
        conn.execute(
            "INSERT INTO bill (id, tenant_id, bill_no, vendor_bill_no, bill_date, vendor_id,"
            " place_of_supply_state, sub_total_paise, tax_paise, round_off_paise, total_paise,"
            " status, idempotency_key, journal_entry_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?, 'posted', ?,?,?)",
            (bill_id, tenant_id, bill_no, (vendor_bill_no or "")[:60], bill_date, vendor_id,
             place_of_supply_state, sub_total, tax_total, round_off, total, idempotency_key,
             entry_id, db.now()),
        )
        for c in computed:
            conn.execute(
                "INSERT INTO bill_line (id, tenant_id, bill_id, item_id, description, qty_milli,"
                " unit_price_paise, gross_paise, discount_paise, taxable_paise, tax_rate_bp,"
                " tax_paise, line_total_paise) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, bill_id, c["item_id"], c["description"], c["qty_milli"],
                 c["unit_price_paise"], c["gross_paise"], c["discount_paise"], c["taxable_paise"],
                 c["tax_rate_bp"], c["tax_paise"], c["line_total_paise"]),
            )
            if c["new_qty"] is not None:
                conn.execute(
                    "UPDATE item SET stock_milli=?, cost_paise=? WHERE id=?",
                    (c["new_qty"], c["new_cost"], c["item_id"]),
                )
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (bill_id, entry_id))
        audit(conn, tenant_id, created_by, "bill.create", "bill", bill_id,
              meta={"total": total, "bill_no": bill_no})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM bill WHERE id=?", (bill_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


def create_credit_note(conn: sqlite3.Connection, tenant_id: str, invoice_id: str, note_date: str,
                       reason: str, lines: list[dict], idempotency_key: str | None = None,
                       created_by: str | None = None) -> dict:
    """Sales return / credit note against an invoice. Restores stock at current cost."""
    if not reason or not reason.strip():
        raise AccountingError("REASON_REQUIRED", "A credit note needs a reason")
    if not lines:
        raise AccountingError("NO_ITEMS", "A credit note needs at least one line")
    invoice = _doc_or_raise(conn, tenant_id, "invoice", invoice_id, "Invoice")
    if invoice["status"] != "posted":
        raise AccountingError("INVOICE_NOT_POSTED", "Only posted invoices can be credited")
    _assert_period_open(conn, tenant_id, note_date)

    computed = []
    sub_total = tax_total = cost_total = 0
    revenue_by_account: dict[str, int] = {}

    for ln in lines:
        inv_line = conn.execute(
            "SELECT * FROM invoice_line WHERE id=? AND invoice_id=? AND tenant_id=?",
            (ln["invoice_line_id"], invoice_id, tenant_id),
        ).fetchone()
        if not inv_line:
            raise AccountingError("LINE_NOT_FOUND", "Invoice line not found")
        qty_milli = int(ln["qty"])
        if qty_milli <= 0:
            raise AccountingError("BAD_QTY", "Quantity must be positive")
        already = conn.execute(
            "SELECT COALESCE(SUM(l.qty_milli),0) q FROM credit_note_line l"
            " JOIN credit_note n ON n.id=l.credit_note_id"
            " WHERE n.tenant_id=? AND n.invoice_id=? AND l.invoice_line_id=?",
            (tenant_id, invoice_id, inv_line["id"]),
        ).fetchone()["q"]
        if qty_milli > inv_line["qty_milli"] - already:
            raise AccountingError(
                "OVER_CREDIT",
                f"Cannot credit {qty_milli/1000:.3f}; only {(inv_line['qty_milli']-already)/1000:.3f} returnable",
            )

        gross = mul_qty_price(qty_milli, inv_line["unit_price_paise"])
        disc = (inv_line["discount_paise"] * qty_milli + inv_line["qty_milli"] // 2) // inv_line["qty_milli"]
        taxable = max(0, gross - disc)
        tax = tax_on(taxable, inv_line["tax_rate_bp"])

        item = conn.execute("SELECT * FROM item WHERE id=?", (inv_line["item_id"],)).fetchone()
        cost = 0
        if item and item["track_stock"]:
            cost = (item["cost_paise"] * qty_milli + 500) // 1000
            revenue_code = item["revenue_code"]
        else:
            revenue_code = item["revenue_code"] if item else "4000"
        revenue_by_account[revenue_code] = revenue_by_account.get(revenue_code, 0) + taxable
        sub_total += taxable
        tax_total += tax
        cost_total += cost
        computed.append({
            "invoice_line_id": inv_line["id"], "item_id": inv_line["item_id"],
            "description": inv_line["description"], "qty_milli": qty_milli,
            "unit_price_paise": inv_line["unit_price_paise"], "taxable_paise": taxable,
            "tax_rate_bp": inv_line["tax_rate_bp"], "tax_paise": tax, "cost_paise": cost,
            "line_total_paise": taxable + tax, "track_stock": bool(item and item["track_stock"]),
        })

    total = sub_total + tax_total
    intra = invoice["place_of_supply_state"] == conn.execute(
        "SELECT state_code FROM tenant WHERE id=?", (tenant_id,)).fetchone()["state_code"]

    acct = db.account_id
    ar = acct(conn, tenant_id, AR_ACCOUNT)
    inventory = acct(conn, tenant_id, "1200")
    cogs = acct(conn, tenant_id, "5000")

    if intra:
        cgst, sgst = split_tax(tax_total)
        tax_lines = [(acct(conn, tenant_id, "2100"), cgst), (acct(conn, tenant_id, "2101"), sgst)]
    else:
        tax_lines = [(acct(conn, tenant_id, "2102"), tax_total)]

    lines_j = [{"account_id": ar, "debit": 0, "credit": total, "party_id": invoice["customer_id"],
                "memo": "Credit note"}]
    for code, amount in revenue_by_account.items():
        if amount:
            lines_j.append({"account_id": acct(conn, tenant_id, code), "debit": amount, "credit": 0,
                            "memo": "Sales return"})
    for acc, amt in tax_lines:
        if amt:
            lines_j.append({"account_id": acc, "debit": amt, "credit": 0, "memo": "GST output reversal"})
    if cost_total:
        lines_j.append({"account_id": inventory, "debit": cost_total, "credit": 0, "memo": "Stock in"})
        lines_j.append({"account_id": cogs, "debit": 0, "credit": cost_total, "memo": "COGS reversal"})

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM credit_note WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, note_date, f"Credit note: {reason}", lines_j,
                                source_type="credit_note", idempotency_key=idempotency_key,
                                created_by=created_by)
        note_id = db.new_id()
        note_no = db.next_number(conn, tenant_id, "credit_note", "CN")
        conn.execute(
            "INSERT INTO credit_note (id, tenant_id, note_no, note_date, customer_id, invoice_id,"
            " place_of_supply_state, sub_total_paise, tax_paise, round_off_paise, total_paise,"
            " reason, journal_entry_id, idempotency_key, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)",
            (note_id, tenant_id, note_no, note_date, invoice["customer_id"], invoice_id,
             invoice["place_of_supply_state"], sub_total, tax_total, total, reason[:200],
             entry_id, idempotency_key, db.now()),
        )
        for c in computed:
            conn.execute(
                "INSERT INTO credit_note_line (id, tenant_id, credit_note_id, item_id,"
                " invoice_line_id, description, qty_milli, unit_price_paise, taxable_paise,"
                " tax_rate_bp, tax_paise, cost_paise, line_total_paise)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, note_id, c["item_id"], c["invoice_line_id"],
                 c["description"], c["qty_milli"], c["unit_price_paise"], c["taxable_paise"],
                 c["tax_rate_bp"], c["tax_paise"], c["cost_paise"], c["line_total_paise"]),
            )
            if c["track_stock"]:
                conn.execute("UPDATE item SET stock_milli=stock_milli+? WHERE id=?",
                             (c["qty_milli"], c["item_id"]))
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (note_id, entry_id))
        audit(conn, tenant_id, created_by, "credit_note.create", "credit_note", note_id,
              meta={"total": total, "invoice_id": invoice_id})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM credit_note WHERE id=?", (note_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


def create_debit_note(conn: sqlite3.Connection, tenant_id: str, bill_id: str, note_date: str,
                      reason: str, lines: list[dict], idempotency_key: str | None = None,
                      created_by: str | None = None) -> dict:
    """Purchase return / debit note against a bill.

    Reverses the original purchase value and input GST, and reduces the vendor
    payable. Stock is taken out at the bill line's purchase value, so the
    weighted-average cost is restated without inventing a gain or loss.
    """
    if not reason or not reason.strip():
        raise AccountingError("REASON_REQUIRED", "A debit note needs a reason")
    if not lines:
        raise AccountingError("NO_ITEMS", "A debit note needs at least one line")
    bill = _doc_or_raise(conn, tenant_id, "bill", bill_id, "Bill")
    if bill["status"] != "posted":
        raise AccountingError("BILL_NOT_POSTED", "Only posted bills can be debited")
    _assert_period_open(conn, tenant_id, note_date)
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    intra = bill["place_of_supply_state"] == tenant["state_code"]

    computed: list[dict] = []
    sub_total = tax_total = stock_value = purchase_value = 0
    stock_out: dict[str, int] = {}
    stock_value_out: dict[str, int] = {}

    for ln in lines:
        bill_line = conn.execute(
            "SELECT * FROM bill_line WHERE id=? AND bill_id=? AND tenant_id=?",
            (ln["bill_line_id"], bill_id, tenant_id),
        ).fetchone()
        if not bill_line:
            raise AccountingError("LINE_NOT_FOUND", "Bill line not found")
        qty_milli = int(ln["qty"])
        if qty_milli <= 0:
            raise AccountingError("BAD_QTY", "Quantity must be positive")
        already = conn.execute(
            "SELECT COALESCE(SUM(l.qty_milli),0) q FROM debit_note_line l"
            " JOIN debit_note n ON n.id=l.debit_note_id"
            " WHERE n.tenant_id=? AND n.bill_id=? AND l.bill_line_id=?",
            (tenant_id, bill_id, bill_line["id"]),
        ).fetchone()["q"]
        if qty_milli > bill_line["qty_milli"] - already:
            raise AccountingError(
                "OVER_DEBIT",
                f"Cannot return {qty_milli/1000:.3f}; only "
                f"{(bill_line['qty_milli']-already)/1000:.3f} returnable",
            )

        gross = mul_qty_price(qty_milli, bill_line["unit_price_paise"])
        disc = (bill_line["discount_paise"] * qty_milli
                + bill_line["qty_milli"] // 2) // bill_line["qty_milli"]
        taxable = max(0, gross - disc)
        tax = tax_on(taxable, bill_line["tax_rate_bp"])

        item = None
        if bill_line["item_id"]:
            item = conn.execute("SELECT * FROM item WHERE id=? AND tenant_id=?",
                                (bill_line["item_id"], tenant_id)).fetchone()
        track = bool(item and item["track_stock"])
        if track:
            stock_value += taxable
            stock_out[item["id"]] = stock_out.get(item["id"], 0) + qty_milli
            stock_value_out[item["id"]] = stock_value_out.get(item["id"], 0) + taxable
        else:
            purchase_value += taxable

        sub_total += taxable
        tax_total += tax
        computed.append({
            "bill_line_id": bill_line["id"], "item_id": bill_line["item_id"],
            "description": bill_line["description"], "qty_milli": qty_milli,
            "unit_price_paise": bill_line["unit_price_paise"], "taxable_paise": taxable,
            "tax_rate_bp": bill_line["tax_rate_bp"], "tax_paise": tax,
            "cost_paise": taxable if track else 0, "line_total_paise": taxable + tax,
            "track_stock": track,
        })

    # Validate stock quantity and restated average cost before posting anything.
    cost_updates: dict[str, tuple[int, int]] = {}
    for item_id, qty_out in stock_out.items():
        item = conn.execute("SELECT * FROM item WHERE id=?", (item_id,)).fetchone()
        if item["stock_milli"] < qty_out:
            raise AccountingError(
                "INSUFFICIENT_STOCK",
                f"Cannot return {qty_out/1000:.3f} of {item['name']}; only "
                f"{item['stock_milli']/1000:.3f} in stock",
            )
        new_qty = item["stock_milli"] - qty_out
        new_value_milli = item["stock_milli"] * item["cost_paise"] - stock_value_out[item_id] * 1000
        if new_qty > 0 and new_value_milli < 0:
            raise AccountingError(
                "COST_UNDERFLOW",
                f"Inventory value is lower than the purchase value being returned for {item['name']}."
                " Post an inventory revaluation journal first.",
            )
        new_cost = ((new_value_milli + new_qty // 2) // new_qty) if new_qty > 0 else item["cost_paise"]
        cost_updates[item_id] = (new_qty, max(0, new_cost))

    total = sub_total + tax_total

    acct = db.account_id
    ap = acct(conn, tenant_id, AP_ACCOUNT)
    inventory = acct(conn, tenant_id, "1200")
    purchases = acct(conn, tenant_id, "5100")

    if intra:
        cgst, sgst = split_tax(tax_total)
        tax_lines = [(acct(conn, tenant_id, "2200"), cgst), (acct(conn, tenant_id, "2201"), sgst)]
    else:
        tax_lines = [(acct(conn, tenant_id, "2202"), tax_total)]

    lines_j = [{"account_id": ap, "debit": total, "credit": 0, "party_id": bill["vendor_id"],
                "memo": "Debit note / purchase return"}]
    if stock_value:
        lines_j.append({"account_id": inventory, "debit": 0, "credit": stock_value,
                        "memo": "Stock returned"})
    if purchase_value:
        lines_j.append({"account_id": purchases, "debit": 0, "credit": purchase_value,
                        "memo": "Purchase return"})
    for acc, amt in tax_lines:
        if amt:
            lines_j.append({"account_id": acc, "debit": 0, "credit": amt,
                            "memo": "GST input reversal"})

    conn.execute("BEGIN IMMEDIATE")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM debit_note WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute("COMMIT")
                return dict(existing)

        entry_id = post_journal(conn, tenant_id, note_date, f"Debit note: {reason}", lines_j,
                                source_type="debit_note", idempotency_key=idempotency_key,
                                created_by=created_by)
        note_id = db.new_id()
        note_no = db.next_number(conn, tenant_id, "debit_note", "DBN")
        conn.execute(
            "INSERT INTO debit_note (id, tenant_id, note_no, note_date, vendor_id, bill_id,"
            " place_of_supply_state, sub_total_paise, tax_paise, round_off_paise, total_paise,"
            " reason, journal_entry_id, idempotency_key, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)",
            (note_id, tenant_id, note_no, note_date, bill["vendor_id"], bill_id,
             bill["place_of_supply_state"], sub_total, tax_total, total, reason[:200],
             entry_id, idempotency_key, db.now()),
        )
        for c in computed:
            conn.execute(
                "INSERT INTO debit_note_line (id, tenant_id, debit_note_id, item_id,"
                " bill_line_id, description, qty_milli, unit_price_paise, taxable_paise,"
                " tax_rate_bp, tax_paise, cost_paise, line_total_paise)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.new_id(), tenant_id, note_id, c["item_id"], c["bill_line_id"],
                 c["description"], c["qty_milli"], c["unit_price_paise"], c["taxable_paise"],
                 c["tax_rate_bp"], c["tax_paise"], c["cost_paise"], c["line_total_paise"]),
            )
        for item_id, (new_qty, new_cost) in cost_updates.items():
            conn.execute("UPDATE item SET stock_milli=?, cost_paise=? WHERE id=?",
                         (new_qty, new_cost, item_id))
        conn.execute("UPDATE journal_entry SET source_id=? WHERE id=?", (note_id, entry_id))
        audit(conn, tenant_id, created_by, "debit_note.create", "debit_note", note_id,
              meta={"total": total, "bill_id": bill_id})
        conn.execute("COMMIT")
        return dict(conn.execute("SELECT * FROM debit_note WHERE id=?", (note_id,)).fetchone())
    except Exception:
        conn.execute("ROLLBACK")
        raise


def receivable_ageing(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or _today_iso()
    as_of_d = date.fromisoformat(as_of)
    rows = conn.execute(
        """SELECT i.id, i.invoice_no, i.invoice_date, i.total_paise, c.name AS customer
           FROM invoice i JOIN customer c ON c.id=i.customer_id
           WHERE i.tenant_id=? AND i.status='posted' AND i.invoice_date <= ?
           ORDER BY i.invoice_date""",
        (tenant_id, as_of),
    ).fetchall()
    out = []
    totals = {"current": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for r in rows:
        outstanding = invoice_outstanding(conn, tenant_id, r["id"])
        if outstanding <= 0:
            continue
        days = (as_of_d - date.fromisoformat(r["invoice_date"])).days
        bucket = "current" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        totals[bucket] += outstanding
        out.append({"invoice_id": r["id"], "invoice_no": r["invoice_no"], "date": r["invoice_date"],
                    "customer": r["customer"], "total": r["total_paise"],
                    "outstanding": outstanding, "days": days, "bucket": bucket})
    return {"as_of": as_of, "rows": out, "totals": totals, "grand_total": sum(totals.values())}


def payable_ageing(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> dict:
    as_of = as_of or _today_iso()
    as_of_d = date.fromisoformat(as_of)
    rows = conn.execute(
        """SELECT b.id, b.bill_no, b.bill_date, b.total_paise, v.name AS vendor
           FROM bill b JOIN vendor v ON v.id=b.vendor_id
           WHERE b.tenant_id=? AND b.status='posted' AND b.bill_date <= ?
           ORDER BY b.bill_date""",
        (tenant_id, as_of),
    ).fetchall()
    out = []
    totals = {"current": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for r in rows:
        outstanding = bill_outstanding(conn, tenant_id, r["id"])
        if outstanding <= 0:
            continue
        days = (as_of_d - date.fromisoformat(r["bill_date"])).days
        bucket = "current" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        totals[bucket] += outstanding
        out.append({"bill_id": r["id"], "bill_no": r["bill_no"], "date": r["bill_date"],
                    "vendor": r["vendor"], "total": r["total_paise"],
                    "outstanding": outstanding, "days": days, "bucket": bucket})
    return {"as_of": as_of, "rows": out, "totals": totals, "grand_total": sum(totals.values())}


def day_book(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> list[dict]:
    rows = conn.execute(
        """SELECT e.id, e.entry_no, e.entry_date, e.narration, e.source_type, e.source_id,
                  e.status, COALESCE(SUM(l.debit_paise),0) AS amount
           FROM journal_entry e LEFT JOIN journal_line l ON l.entry_id=e.id
           WHERE e.tenant_id=? AND e.entry_date BETWEEN ? AND ?
           GROUP BY e.id ORDER BY e.entry_date, e.entry_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    return [dict(r) for r in rows]


def gst_summary(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> dict:
    def account_tax(code: str, debit_side: bool) -> int:
        row = conn.execute(
            """SELECT COALESCE(SUM(l.debit_paise),0) d, COALESCE(SUM(l.credit_paise),0) c
               FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
               JOIN account a ON a.id=l.account_id
               WHERE l.tenant_id=? AND a.code=? AND e.entry_date BETWEEN ? AND ?""",
            (tenant_id, code, date_from, date_to),
        ).fetchone()
        return (row["d"] - row["c"]) if debit_side else (row["c"] - row["d"])

    output = {
        "CGST": account_tax("2100", False),
        "SGST": account_tax("2101", False),
        "IGST": account_tax("2102", False),
    }
    input_tax = {
        "CGST": account_tax("2200", True),
        "SGST": account_tax("2201", True),
        "IGST": account_tax("2202", True),
    }
    sales = conn.execute(
        """SELECT i.invoice_no, i.invoice_date, i.sub_total_paise, i.tax_paise, i.total_paise,
                  c.name AS party
           FROM invoice i JOIN customer c ON c.id=i.customer_id
           WHERE i.tenant_id=? AND i.invoice_date BETWEEN ? AND ? AND i.status='posted'
           ORDER BY i.invoice_date, i.invoice_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    purchases = conn.execute(
        """SELECT b.bill_no, b.bill_date, b.sub_total_paise, b.tax_paise, b.total_paise,
                  v.name AS party
           FROM bill b JOIN vendor v ON v.id=b.vendor_id
           WHERE b.tenant_id=? AND b.bill_date BETWEEN ? AND ? AND b.status='posted'
           ORDER BY b.bill_date, b.bill_no""",
        (tenant_id, date_from, date_to),
    ).fetchall()
    out_total = sum(output.values())
    in_total = sum(input_tax.values())
    return {"from": date_from, "to": date_to, "output": output, "input": input_tax,
            "output_total": out_total, "input_total": in_total,
            "net_payable": out_total - in_total,
            "sales": [dict(r) for r in sales], "purchases": [dict(r) for r in purchases]}


def invoice_tax_breakup(conn: sqlite3.Connection, tenant_id: str, invoice_id: str) -> dict:
    """Per-line and rate-wise GST split that always sums to the invoice tax total."""
    inv = conn.execute(
        "SELECT i.*, c.name AS customer_name, c.gstin AS customer_gstin,"
        " c.address AS customer_address, c.state_code AS customer_state"
        " FROM invoice i JOIN customer c ON c.id=i.customer_id"
        " WHERE i.id=? AND i.tenant_id=?", (invoice_id, tenant_id),
    ).fetchone()
    if not inv:
        raise AccountingError("DOC_NOT_FOUND", "Invoice not found in this business")
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    lines = conn.execute("SELECT * FROM invoice_line WHERE invoice_id=? ORDER BY rowid",
                         (invoice_id,)).fetchall()
    intra = inv["place_of_supply_state"] == tenant["state_code"]
    total_tax = sum(l["tax_paise"] for l in lines)

    splits: list[dict] = []
    if intra:
        target_cgst = total_tax // 2
        base = [l["tax_paise"] // 2 for l in lines]
        diff = target_cgst - sum(base)
        for i, l in enumerate(lines):
            cgst = base[i] + (1 if i < diff else 0)
            splits.append({"cgst": cgst, "sgst": l["tax_paise"] - cgst, "igst": 0})
    else:
        splits = [{"cgst": 0, "sgst": 0, "igst": l["tax_paise"]} for l in lines]

    groups: dict[int, dict] = {}
    out_lines = []
    for l, sp in zip(lines, splits):
        g = groups.setdefault(l["tax_rate_bp"], {"rate_bp": l["tax_rate_bp"], "taxable": 0,
                                                 "cgst": 0, "sgst": 0, "igst": 0})
        g["taxable"] += l["taxable_paise"]
        g["cgst"] += sp["cgst"]
        g["sgst"] += sp["sgst"]
        g["igst"] += sp["igst"]
        out_lines.append({**dict(l), **sp})

    return {"invoice": dict(inv), "tenant": dict(tenant), "lines": out_lines,
            "groups": sorted(groups.values(), key=lambda g: g["rate_bp"]),
            "intra": intra, "total_tax": total_tax,
            "cgst": sum(s["cgst"] for s in splits), "sgst": sum(s["sgst"] for s in splits),
            "igst": sum(s["igst"] for s in splits)}


def gstr1_data(conn: sqlite3.Connection, tenant_id: str, date_from: str, date_to: str) -> dict:
    """GSTR-1 style working data: B2B, B2C small, HSN summary and document counts.

    This is a preparation aid, not an uploaded/filed return. Amounts are integer paise.
    """
    tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (tenant_id,)).fetchone()
    if not tenant:
        raise AccountingError("TENANT_NOT_FOUND", "Tenant not found")

    invoices = conn.execute(
        "SELECT i.*, c.name AS customer_name, c.gstin AS customer_gstin,"
        " c.state_code AS customer_state FROM invoice i JOIN customer c ON c.id=i.customer_id"
        " WHERE i.tenant_id=? AND i.status='posted' AND i.invoice_date BETWEEN ? AND ?"
        " ORDER BY i.invoice_date, i.invoice_no", (tenant_id, date_from, date_to),
    ).fetchall()

    b2b: list[dict] = []
    b2cs: dict[tuple[str, int], dict] = {}
    line_splits: dict[str, dict] = {}
    b2c_count = 0

    for inv in invoices:
        br = invoice_tax_breakup(conn, tenant_id, inv["id"])
        for ln in br["lines"]:
            line_splits[ln["id"]] = ln
        registered = bool((inv["customer_gstin"] or "").strip())
        if not registered:
            b2c_count += 1
        for idx, g in enumerate(br["groups"]):
            if registered:
                b2b.append({
                    "gstin": inv["customer_gstin"].strip().upper(),
                    "receiver": inv["customer_name"],
                    "invoice_no": inv["invoice_no"],
                    "invoice_date": inv["invoice_date"],
                    "invoice_value": inv["total_paise"] if idx == 0 else None,
                    "place_of_supply": inv["place_of_supply_state"],
                    "reverse_charge": "N",
                    "rate_bp": g["rate_bp"], "taxable": g["taxable"],
                    "cgst": g["cgst"], "sgst": g["sgst"], "igst": g["igst"], "cess": 0,
                })
            else:
                key = (inv["place_of_supply_state"], g["rate_bp"])
                agg = b2cs.setdefault(key, {"place_of_supply": key[0], "rate_bp": key[1],
                                            "taxable": 0, "cgst": 0, "sgst": 0, "igst": 0,
                                            "invoice_ids": set()})
                agg["taxable"] += g["taxable"]
                agg["cgst"] += g["cgst"]
                agg["sgst"] += g["sgst"]
                agg["igst"] += g["igst"]
                agg["invoice_ids"].add(inv["id"])

    hsn_rows = conn.execute(
        "SELECT l.*, i.invoice_date, i.place_of_supply_state, it.hsn, it.name AS item_name,"
        " it.unit FROM invoice_line l JOIN invoice i ON i.id=l.invoice_id"
        " JOIN item it ON it.id=l.item_id"
        " WHERE i.tenant_id=? AND i.status='posted' AND i.invoice_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchall()

    hsn: dict[tuple[str, int], dict] = {}
    for row in hsn_rows:
        sp = line_splits.get(row["id"])
        if not sp:
            continue
        code = (row["hsn"] or "").strip().upper()
        key = (code, row["tax_rate_bp"])
        agg = hsn.setdefault(key, {"hsn": code or "NOT SET", "description": row["item_name"],
                                   "uqc": row["unit"], "rate_bp": row["tax_rate_bp"],
                                   "qty_milli": 0, "taxable": 0,
                                   "cgst": 0, "sgst": 0, "igst": 0, "total_value": 0})
        agg["qty_milli"] += row["qty_milli"]
        agg["taxable"] += row["taxable_paise"]
        agg["cgst"] += sp["cgst"]
        agg["sgst"] += sp["sgst"]
        agg["igst"] += sp["igst"]
        agg["total_value"] += row["line_total_paise"]

    credit_notes = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(total_paise),0) t FROM credit_note"
        " WHERE tenant_id=? AND note_date BETWEEN ? AND ?",
        (tenant_id, date_from, date_to),
    ).fetchone()

    credit_rows = conn.execute(
        "SELECT n.*, c.name AS customer_name, c.gstin AS customer_gstin"
        " FROM credit_note n JOIN customer c ON c.id=n.customer_id"
        " WHERE n.tenant_id=? AND n.note_date BETWEEN ? AND ?"
        " ORDER BY n.note_date, n.note_no", (tenant_id, date_from, date_to),
    ).fetchall()
    credit_detail: list[dict] = []
    for n in credit_rows:
        intra = n["place_of_supply_state"] == tenant["state_code"]
        cgst = n["tax_paise"] // 2 if intra else 0
        sgst = n["tax_paise"] - cgst if intra else 0
        credit_detail.append({
            "section": "CDNR" if (n["customer_gstin"] or "").strip() else "CDNUR",
            "gstin": (n["customer_gstin"] or "").strip().upper(),
            "receiver": n["customer_name"], "note_no": n["note_no"],
            "note_date": n["note_date"], "note_value": n["total_paise"],
            "place_of_supply": n["place_of_supply_state"],
            "taxable": n["sub_total_paise"], "cgst": cgst, "sgst": sgst,
            "igst": 0 if intra else n["tax_paise"], "cess": 0,
        })
    credit_totals = {
        "taxable": sum(r["taxable"] for r in credit_detail),
        "cgst": sum(r["cgst"] for r in credit_detail),
        "sgst": sum(r["sgst"] for r in credit_detail),
        "igst": sum(r["igst"] for r in credit_detail),
    }

    warnings: list[str] = []
    if not (tenant["gstin"] or "").strip():
        warnings.append("Supplier GSTIN is not set. Add it in Settings before using this export for filing.")
    if b2c_count:
        warnings.append(f"{b2c_count} invoice(s) have no buyer GSTIN and are grouped as B2C small.")
    missing_hsn = sum(1 for h in hsn.values() if h["hsn"] == "NOT SET")
    if missing_hsn:
        warnings.append(f"{missing_hsn} HSN/SAC group(s) have no code. Add HSN/SAC on the item master.")

    totals = {
        "taxable": sum(r["taxable"] for r in b2b) + sum(r["taxable"] for r in b2cs.values()),
        "cgst": sum(r["cgst"] for r in b2b) + sum(r["cgst"] for r in b2cs.values()),
        "sgst": sum(r["sgst"] for r in b2b) + sum(r["sgst"] for r in b2cs.values()),
        "igst": sum(r["igst"] for r in b2b) + sum(r["igst"] for r in b2cs.values()),
    }
    b2cs_rows = []
    for r in b2cs.values():
        row = dict(r)
        row["invoices"] = len(row.pop("invoice_ids"))
        b2cs_rows.append(row)
    return {
        "period": {"from": date_from, "to": date_to},
        "supplier": {"gstin": (tenant["gstin"] or "").strip().upper(),
                     "name": tenant["name"], "state_code": tenant["state_code"]},
        "b2b": b2b,
        "b2cs": sorted(b2cs_rows, key=lambda r: (r["place_of_supply"], r["rate_bp"])),
        "hsn": sorted(hsn.values(), key=lambda r: (r["hsn"], r["rate_bp"])),
        "credit_notes": credit_detail,
        "credit_note_totals": credit_totals,
        "docs": {"invoices": len(invoices), "b2c_invoices": b2c_count,
                 "credit_notes": credit_notes["c"], "credit_note_value": credit_notes["t"],
                 "debit_notes": 0, "cancelled": 0},
        "totals": totals,
        "warnings": warnings,
    }


def vendor_balances(conn: sqlite3.Connection, tenant_id: str, as_of: str | None = None) -> list[dict]:
    as_of = as_of or _today_iso()
    rows = conn.execute(
        """
        SELECT v.id, v.name, v.phone, v.state_code,
               COALESCE(SUM(p.credit_paise - p.debit_paise), 0) AS balance
        FROM vendor v
        LEFT JOIN (
            SELECT l.party_id, l.debit_paise, l.credit_paise
            FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
            WHERE l.tenant_id=? AND l.party_id IS NOT NULL AND e.entry_date <= ?
        ) p ON p.party_id = v.id
        WHERE v.tenant_id=? GROUP BY v.id ORDER BY v.name
        """,
        (tenant_id, as_of, tenant_id),
    ).fetchall()
    return [dict(r) for r in rows]


def vendor_statement(conn: sqlite3.Connection, tenant_id: str, vendor_id: str,
                     date_from: str, date_to: str) -> dict:
    vendor = _doc_or_raise(conn, tenant_id, "vendor", vendor_id, "Vendor")
    opening = conn.execute(
        """SELECT COALESCE(SUM(l.credit_paise - l.debit_paise),0) bal
           FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
           WHERE l.tenant_id=? AND l.party_id=? AND e.entry_date < ?""",
        (tenant_id, vendor_id, date_from),
    ).fetchone()["bal"] or 0
    rows = conn.execute(
        """SELECT e.entry_no, e.entry_date, e.narration, e.source_type, e.source_id,
                  l.debit_paise, l.credit_paise
           FROM journal_line l JOIN journal_entry e ON e.id=l.entry_id
           WHERE l.tenant_id=? AND l.party_id=? AND e.entry_date BETWEEN ? AND ?
           ORDER BY e.entry_date, e.entry_no, l.line_no""",
        (tenant_id, vendor_id, date_from, date_to),
    ).fetchall()
    running = opening
    out = []
    billed = paid = debited = 0
    for r in rows:
        running += (r["credit_paise"] or 0) - (r["debit_paise"] or 0)
        billed += r["credit_paise"] or 0
        if r["source_type"] == "debit_note":
            debited += r["debit_paise"] or 0
        else:
            paid += r["debit_paise"] or 0
        out.append({"date": r["entry_date"], "ref": r["entry_no"], "narration": r["narration"],
                    "source_type": r["source_type"], "source_id": r["source_id"],
                    "debit": r["debit_paise"], "credit": r["credit_paise"], "balance": running})
    return {"vendor": dict(vendor), "from": date_from, "to": date_to, "opening": opening,
            "rows": out, "closing": running, "billed": billed, "paid": paid,
            "debited": debited}


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
    payable = -tb.get("2000", {}).get("balance", 0)
    ar_age = receivable_ageing(conn, tenant_id, date_to)
    ap_age = payable_ageing(conn, tenant_id, date_to)
    return {"revenue": pnl["total_income"], "expense": pnl["total_expense"],
            "profit": pnl["net_profit"], "receivable": ar, "cash": cash,
            "inventory": inventory, "invoice_count": inv_count, "payable": payable,
            "open_invoices": len(ar_age["rows"]), "open_bills": len(ap_age["rows"]),
            "overdue_receivable": ar_age["totals"]["61-90"] + ar_age["totals"]["90+"],
            "overdue_payable": ap_age["totals"]["61-90"] + ap_age["totals"]["90+"]}
