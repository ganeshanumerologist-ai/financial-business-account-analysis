"""Manual stock adjustments at the current moving weighted-average cost.

A stock adjustment changes only the item quantity. It never invents a new cost
or a historical valuation layer. The quantity is valued at the item's current
cost, so a positive adjustment debits Inventory and credits Stock Adjustments,
while a negative adjustment does the reverse. Every adjustment is posted as a
balanced journal and written to the audit trail.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from . import accounting as acct, db, i18n

STOCK_ADJUSTMENT_ACCOUNT = "5950"
INVENTORY_ACCOUNT = "1200"


class StockAdjustmentError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _item_or_raise(conn: sqlite3.Connection, tenant_id: str,
                   item_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM item WHERE id=? AND tenant_id=?", (item_id, tenant_id)
    ).fetchone()
    if not row:
        raise StockAdjustmentError("ITEM_NOT_FOUND", "Item not found in this business.")
    return row


def adjust_stock(conn: sqlite3.Connection, tenant_id: str, item_id: str,
                 adjustment_date: str, qty_milli: int, reason: str,
                 note: str = "", idempotency_key: str | None = None,
                 created_by: str | None = None) -> dict:
    """Post one quantity adjustment and return the stored register row.

    ``qty_milli`` is signed: positive increases stock, negative decreases it.
    The item cost is the current moving weighted-average cost and is snapshotted
    on the register row. The item cost itself is not changed by this operation.
    """
    try:
        adjustment_date = date.fromisoformat((adjustment_date or "").strip()).isoformat()
    except ValueError as exc:
        raise StockAdjustmentError(
            "BAD_DATE", "Choose a valid adjustment date (YYYY-MM-DD)."
        ) from exc

    try:
        qty_milli = int(qty_milli)
    except (TypeError, ValueError) as exc:
        raise StockAdjustmentError("BAD_QTY", "Quantity must be a number.") from exc
    if qty_milli == 0:
        raise StockAdjustmentError("BAD_QTY", "Adjustment quantity cannot be zero.")

    reason = (reason or "").strip()
    if not reason:
        raise StockAdjustmentError("REASON_REQUIRED", "Enter a reason for the stock adjustment.")
    reason = reason[:200]
    note = (note or "").strip()[:200]
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip() or None

    own_tx = not conn.in_transaction
    if own_tx:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute("SAVEPOINT sp_stock_adjust")
    try:
        if idempotency_key:
            existing = conn.execute(
                "SELECT * FROM stock_adjustment WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if existing:
                if own_tx:
                    conn.execute("COMMIT")
                else:
                    conn.execute("RELEASE sp_stock_adjust")
                return dict(existing)
            # A journal with this key but no register row would be an inconsistent
            # retry from another source. Refuse it rather than reusing the entry.
            if conn.execute(
                "SELECT 1 FROM journal_entry WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone():
                raise StockAdjustmentError(
                    "IDEMPOTENCY_CONFLICT",
                    "That request key is already used by another posting.",
                )

        item = _item_or_raise(conn, tenant_id, item_id)
        if not item["track_stock"]:
            raise StockAdjustmentError(
                "NOT_TRACKED",
                f"{item['name']} is not a stock-tracked item.",
            )

        unit_cost = int(item["cost_paise"])
        if unit_cost <= 0:
            raise StockAdjustmentError(
                "COST_REQUIRED",
                f"Set the cost for {item['name']} before adjusting its stock.",
            )

        if qty_milli < 0:
            needed = -qty_milli
            if int(item["stock_milli"]) < needed:
                raise StockAdjustmentError(
                    "INSUFFICIENT_STOCK",
                    f"Not enough stock for {item['name']}: have "
                    f"{int(item['stock_milli']) / 1000:.3f}, need {needed / 1000:.3f}.",
                )

        value = (abs(qty_milli) * unit_cost + 500) // 1000
        if value <= 0:
            raise StockAdjustmentError(
                "ZERO_VALUE",
                "The adjustment value is zero. Check the item quantity and cost.",
            )
        signed_value = value if qty_milli > 0 else -value

        # Existing tenants receive 5950 on their first adjustment; new tenants
        # already have it from the standard chart.
        db.seed_chart(conn, tenant_id)
        inventory = db.account_id(conn, tenant_id, INVENTORY_ACCOUNT)
        adjustment_account = db.account_id(conn, tenant_id, STOCK_ADJUSTMENT_ACCOUNT)

        adjustment_id = db.new_id()
        if qty_milli > 0:
            lines = [
                {"account_id": inventory, "debit": value, "credit": 0,
                 "memo": i18n.auto("Stock increase")},
                {"account_id": adjustment_account, "debit": 0, "credit": value,
                 "memo": i18n.auto("Stock adjustment")},
            ]
            narration = i18n.auto("Stock increase: {item}", item=item["name"])
        else:
            lines = [
                {"account_id": adjustment_account, "debit": value, "credit": 0,
                 "memo": i18n.auto("Stock adjustment")},
                {"account_id": inventory, "debit": 0, "credit": value,
                 "memo": i18n.auto("Stock decrease")},
            ]
            narration = i18n.auto("Stock decrease: {item}", item=item["name"])

        entry_id = acct.post_journal(
            conn, tenant_id, adjustment_date, narration, lines,
            source_type="stock_adjustment", source_id=adjustment_id,
            idempotency_key=idempotency_key, created_by=created_by,
        )
        adjustment_no = db.next_number(conn, tenant_id, "stock_adjustment", "STK")
        conn.execute(
            "INSERT INTO stock_adjustment (id, tenant_id, adjustment_no, adjustment_date,"
            " item_id, qty_milli, unit_cost_paise, value_paise, reason, note,"
            " journal_entry_id, idempotency_key, created_by, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (adjustment_id, tenant_id, adjustment_no, adjustment_date, item_id,
             qty_milli, unit_cost, signed_value, reason, note, entry_id,
             idempotency_key, created_by, db.now()),
        )
        conn.execute(
            "UPDATE item SET stock_milli = stock_milli + ? WHERE id=? AND tenant_id=?",
            (qty_milli, item_id, tenant_id),
        )
        acct.audit(
            conn, tenant_id, created_by, "stock.adjust", "stock_adjustment",
            adjustment_id,
            meta={
                "adjustment_no": adjustment_no,
                "item_id": item_id,
                "sku": item["sku"],
                "qty_milli": qty_milli,
                "unit_cost_paise": unit_cost,
                "value_paise": signed_value,
                "journal_entry_id": entry_id,
                "reason": reason,
            },
        )
        if own_tx:
            conn.execute("COMMIT")
        else:
            conn.execute("RELEASE sp_stock_adjust")
        return dict(conn.execute(
            "SELECT * FROM stock_adjustment WHERE id=?", (adjustment_id,)
        ).fetchone())
    except Exception:
        if own_tx:
            conn.execute("ROLLBACK")
        else:
            conn.execute("ROLLBACK TO sp_stock_adjust")
            conn.execute("RELEASE sp_stock_adjust")
        raise
