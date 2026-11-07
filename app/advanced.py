"""Advanced operational registers.

These registers are additive and deliberately separate from the double-entry
core. A batch, production order or dimension budget never changes a posted
journal, stock quantity or tax figure on its own. Reports read the registers
as operational working papers and label the source clearly.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from . import db

DIMENSION_KINDS = {
    "project": "Project / Job",
    "cost_centre": "Cost centre",
    "department": "Department",
    "branch": "Branch",
}

BUCKETS = ("Expired", "0-30 days", "31-90 days", "91-180 days", "181+ days")


class AdvancedError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _tenant_id(tenant) -> str:
    return tenant["id"] if hasattr(tenant, "keys") else str(tenant)


def _parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except (TypeError, ValueError):
        raise AdvancedError("BAD_DATE", f"{label} must be a valid date")


def _audit(conn, tenant_id, actor, action, target_type, target_id, meta=None):
    conn.execute(
        "INSERT INTO audit_log (id, tenant_id, actor_user_id, action, target_type,"
        " target_id, result, meta, created_at) VALUES (?,?,?,?,?,?, 'success', ?, ?)",
        (db.new_id(), tenant_id, actor, action, target_type, target_id,
         None if meta is None else __import__("json").dumps(meta, separators=(",", ":")),
         db.now()),
    )


def _check_kind(kind: str) -> str:
    kind = (kind or "").strip()
    if kind not in DIMENSION_KINDS:
        raise AdvancedError("BAD_KIND", "Choose a valid dimension type")
    return kind


def list_dimensions(conn: sqlite3.Connection, tenant, kind: str | None = None,
                    active_only: bool = False) -> list[dict]:
    tenant_id = _tenant_id(tenant)
    sql = ("SELECT d.*, (SELECT COUNT(*) FROM journal_line l"
           " WHERE l.tenant_id=d.tenant_id AND l.dimension_id=d.id) AS tagged_lines"
           " FROM dimension d WHERE d.tenant_id=?")
    params: list = [tenant_id]
    if kind:
        sql += " AND d.kind=?"
        params.append(_check_kind(kind))
    if active_only:
        sql += " AND d.active=1"
    sql += " ORDER BY d.kind, d.code, d.name"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def create_dimension(conn: sqlite3.Connection, tenant, kind: str, code: str, name: str,
                     note: str = "", created_by: str | None = None) -> str:
    tenant_id = _tenant_id(tenant)
    kind = _check_kind(kind)
    code = (code or "").strip().upper()
    name = (name or "").strip()
    if not code:
        raise AdvancedError("CODE_REQUIRED", "Enter a short code")
    if not name:
        raise AdvancedError("NAME_REQUIRED", "Enter a name")
    if len(code) > 30 or len(name) > 120:
        raise AdvancedError("TOO_LONG", "Code or name is too long")
    existing = conn.execute(
        "SELECT id FROM dimension WHERE tenant_id=? AND kind=? AND code=?",
        (tenant_id, kind, code)).fetchone()
    if existing:
        raise AdvancedError("DUPLICATE", "This code already exists for that dimension type")
    dim_id = db.new_id()
    conn.execute(
        "INSERT INTO dimension (id, tenant_id, kind, code, name, active, note,"
        " created_by, created_at) VALUES (?,?,?,?,?,1,?,?,?)",
        (dim_id, tenant_id, kind, code, name, (note or "").strip()[:200],
         created_by, db.now()))
    _audit(conn, tenant_id, created_by, "dimension.create", "dimension", dim_id,
           {"kind": kind, "code": code, "name": name})
    return dim_id


def update_dimension(conn: sqlite3.Connection, tenant, dimension_id: str, name: str,
                     note: str = "", active: bool = True,
                     updated_by: str | None = None) -> None:
    tenant_id = _tenant_id(tenant)
    row = conn.execute("SELECT * FROM dimension WHERE id=? AND tenant_id=?",
                       (dimension_id, tenant_id)).fetchone()
    if not row:
        raise AdvancedError("NOT_FOUND", "Dimension not found")
    name = (name or "").strip()
    if not name:
        raise AdvancedError("NAME_REQUIRED", "Enter a name")
    conn.execute(
        "UPDATE dimension SET name=?, note=?, active=? WHERE id=? AND tenant_id=?",
        (name[:120], (note or "").strip()[:200], 1 if active else 0,
         dimension_id, tenant_id))
    _audit(conn, tenant_id, updated_by, "dimension.update", "dimension", dimension_id,
           {"name": name, "active": bool(active)})


def set_dimension_budget(conn: sqlite3.Connection, tenant, dimension_id: str,
                         period: str, amount_paise: int, note: str = "",
                         actor: str | None = None) -> str:
    tenant_id = _tenant_id(tenant)
    period = (period or "").strip()
    try:
        date.fromisoformat(period + "-01")
    except ValueError:
        raise AdvancedError("BAD_PERIOD", "Choose a valid budget month")
    try:
        amount_paise = int(amount_paise)
    except (TypeError, ValueError):
        raise AdvancedError("BAD_AMOUNT", "Budget must be a whole paise amount")
    if amount_paise < 0:
        raise AdvancedError("BAD_AMOUNT", "Budget cannot be negative")
    dim = conn.execute("SELECT * FROM dimension WHERE id=? AND tenant_id=?",
                       (dimension_id, tenant_id)).fetchone()
    if not dim:
        raise AdvancedError("NOT_FOUND", "Dimension not found")
    if dim["kind"] != "cost_centre":
        raise AdvancedError("BAD_KIND", "Budgets can only be set for cost centres")
    row = conn.execute(
        "SELECT id FROM dimension_budget WHERE tenant_id=? AND dimension_id=? AND period=?",
        (tenant_id, dimension_id, period)).fetchone()
    now = db.now()
    if row:
        conn.execute(
            "UPDATE dimension_budget SET amount_paise=?, note=?, updated_at=?, updated_by=?"
            " WHERE id=? AND tenant_id=?",
            (amount_paise, (note or "").strip()[:200], now, actor, row["id"], tenant_id))
        budget_id = row["id"]
    else:
        budget_id = db.new_id()
        conn.execute(
            "INSERT INTO dimension_budget (id, tenant_id, dimension_id, period,"
            " amount_paise, note, created_by, created_at, updated_at, updated_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (budget_id, tenant_id, dimension_id, period, amount_paise,
             (note or "").strip()[:200], actor, now, now, actor))
    _audit(conn, tenant_id, actor, "dimension_budget.set", "dimension_budget", budget_id,
           {"dimension_id": dimension_id, "period": period, "amount_paise": amount_paise})
    return budget_id


def list_dimension_budgets(conn: sqlite3.Connection, tenant, period: str | None = None):
    tenant_id = _tenant_id(tenant)
    sql = ("SELECT b.*, d.code, d.name FROM dimension_budget b"
           " JOIN dimension d ON d.id=b.dimension_id AND d.tenant_id=b.tenant_id"
           " WHERE b.tenant_id=?")
    params: list = [tenant_id]
    if period:
        sql += " AND b.period=?"
        params.append(period)
    sql += " ORDER BY b.period DESC, d.code"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _batch_bucket(days: int) -> str:
    if days < 0:
        return BUCKETS[0]
    if days <= 30:
        return BUCKETS[1]
    if days <= 90:
        return BUCKETS[2]
    if days <= 180:
        return BUCKETS[3]
    return BUCKETS[4]


def list_batches(conn: sqlite3.Connection, tenant, as_of: str | None = None,
                 include_void: bool = False) -> dict:
    tenant_id = _tenant_id(tenant)
    as_of = as_of or date.today().isoformat()
    as_of_d = _parse_date(as_of, "As of")
    sql = ("SELECT b.*, i.sku, i.name, i.unit FROM inventory_batch b"
           " JOIN item i ON i.id=b.item_id AND i.tenant_id=b.tenant_id"
           " WHERE b.tenant_id=?")
    params: list = [tenant_id]
    if not include_void:
        sql += " AND b.status='active'"
    sql += " ORDER BY b.expiry_date, i.name, b.batch_no"
    rows = []
    for r in conn.execute(sql, params).fetchall():
        expiry = _parse_date(r["expiry_date"], "Expiry")
        days = (expiry - as_of_d).days
        qty = int(r["qty_milli"])
        cost = int(r["cost_paise"])
        rows.append({
            **dict(r),
            "days": days,
            "bucket": _batch_bucket(days),
            "value": (qty * cost + 500) // 1000,
        })
    totals = {
        "batches": len(rows),
        "qty": sum(r["qty_milli"] for r in rows),
        "value": sum(r["value"] for r in rows),
        "expired": sum(1 for r in rows if r["days"] < 0),
        "expiring_30": sum(1 for r in rows if 0 <= r["days"] <= 30),
        "expired_value": sum(r["value"] for r in rows if r["days"] < 0),
        "expiring_value": sum(r["value"] for r in rows if 0 <= r["days"] <= 30),
    }
    buckets = []
    for name in BUCKETS:
        bucket_rows = [r for r in rows if r["bucket"] == name]
        buckets.append({"name": name, "batches": len(bucket_rows),
                        "qty": sum(r["qty_milli"] for r in bucket_rows),
                        "value": sum(r["value"] for r in bucket_rows)})
    return {"as_of": as_of, "rows": rows, "totals": totals, "buckets": buckets}


def create_batch(conn: sqlite3.Connection, tenant, item_id: str, batch_no: str,
                 expiry_date: str, qty_milli: int, cost_paise: int,
                 note: str = "", created_by: str | None = None) -> str:
    tenant_id = _tenant_id(tenant)
    item = conn.execute("SELECT * FROM item WHERE id=? AND tenant_id=?",
                        (item_id, tenant_id)).fetchone()
    if not item:
        raise AdvancedError("ITEM_NOT_FOUND", "Item not found in this business")
    batch_no = (batch_no or "").strip().upper()
    if not batch_no:
        raise AdvancedError("BATCH_REQUIRED", "Enter a batch or lot number")
    if len(batch_no) > 60:
        raise AdvancedError("BATCH_TOO_LONG", "Batch number is too long")
    expiry = _parse_date(expiry_date, "Expiry date").isoformat()
    try:
        qty_milli = int(qty_milli)
        cost_paise = int(cost_paise)
    except (TypeError, ValueError):
        raise AdvancedError("BAD_NUMBER", "Quantity and cost must be whole numbers")
    if qty_milli < 0 or cost_paise < 0:
        raise AdvancedError("BAD_NUMBER", "Quantity and cost cannot be negative")
    if conn.execute(
        "SELECT 1 FROM inventory_batch WHERE tenant_id=? AND item_id=? AND batch_no=?",
        (tenant_id, item_id, batch_no)).fetchone():
        raise AdvancedError("DUPLICATE", "This batch number already exists for the item")
    batch_id = db.new_id()
    conn.execute(
        "INSERT INTO inventory_batch (id, tenant_id, item_id, batch_no, expiry_date,"
        " qty_milli, cost_paise, status, note, created_by, created_at)"
        " VALUES (?,?,?,?,?,?,?, 'active', ?,?,?)",
        (batch_id, tenant_id, item_id, batch_no, expiry, qty_milli, cost_paise,
         (note or "").strip()[:200], created_by, db.now()))
    _audit(conn, tenant_id, created_by, "batch.create", "inventory_batch", batch_id,
           {"item_id": item_id, "batch_no": batch_no, "expiry_date": expiry,
            "qty_milli": qty_milli, "cost_paise": cost_paise})
    return batch_id


def void_batch(conn: sqlite3.Connection, tenant, batch_id: str, reason: str,
               actor: str | None = None) -> None:
    tenant_id = _tenant_id(tenant)
    reason = (reason or "").strip()
    if not reason:
        raise AdvancedError("REASON_REQUIRED", "Enter a reason for voiding the batch")
    row = conn.execute("SELECT * FROM inventory_batch WHERE id=? AND tenant_id=?",
                       (batch_id, tenant_id)).fetchone()
    if not row:
        raise AdvancedError("NOT_FOUND", "Batch not found")
    if row["status"] == "void":
        raise AdvancedError("ALREADY_VOID", "Batch is already void")
    conn.execute("UPDATE inventory_batch SET status='void', note=? WHERE id=? AND tenant_id=?",
                 (reason[:200], batch_id, tenant_id))
    _audit(conn, tenant_id, actor, "batch.void", "inventory_batch", batch_id,
           {"reason": reason[:200], "batch_no": row["batch_no"]})


def list_production_orders(conn: sqlite3.Connection, tenant,
                           date_from: str | None = None,
                           date_to: str | None = None,
                           status: str | None = None) -> list[dict]:
    tenant_id = _tenant_id(tenant)
    sql = ("SELECT p.*, oi.sku AS output_sku, oi.name AS output_name, oi.unit AS output_unit,"
           " ii.sku AS input_sku, ii.name AS input_name, ii.unit AS input_unit"
           " FROM production_order p"
           " JOIN item oi ON oi.id=p.output_item_id AND oi.tenant_id=p.tenant_id"
           " JOIN item ii ON ii.id=p.input_item_id AND ii.tenant_id=p.tenant_id"
           " WHERE p.tenant_id=?")
    params: list = [tenant_id]
    if date_from:
        sql += " AND p.order_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND p.order_date <= ?"
        params.append(date_to)
    if status:
        sql += " AND p.status=?"
        params.append(status)
    sql += " ORDER BY p.order_date, p.order_no"
    out = []
    for r in conn.execute(sql, params).fetchall():
        input_qty = int(r["input_qty_milli"])
        output_qty = int(r["output_qty_milli"])
        standard = int(r["standard_input_qty_milli"])
        input_value = (input_qty * int(r["input_cost_paise"]) + 500) // 1000
        output_value = (output_qty * int(r["output_cost_paise"]) + 500) // 1000
        variance_qty = input_qty - standard if standard > 0 else None
        variance_pct = (variance_qty * 10000 // standard) if standard > 0 and variance_qty is not None else None
        yield_pct = (output_qty * 10000 // input_qty) if input_qty > 0 else None
        wastage_pct = (10000 - yield_pct) if yield_pct is not None else None
        wip_value = (input_value - output_value) if r["status"] == "open" else 0
        out.append({
            **dict(r),
            "input_value": input_value,
            "output_value": output_value,
            "wip_value": wip_value,
            "variance_qty": variance_qty,
            "variance_pct": variance_pct,
            "yield_pct": yield_pct,
            "wastage_pct": wastage_pct,
        })
    return out


def create_production_order(conn: sqlite3.Connection, tenant, order_date: str,
                            input_item_id: str, output_item_id: str,
                            input_qty_milli: int, output_qty_milli: int,
                            standard_input_qty_milli: int = 0,
                            input_cost_paise: int | None = None,
                            output_cost_paise: int | None = None,
                            note: str = "", order_no: str = "",
                            created_by: str | None = None) -> str:
    tenant_id = _tenant_id(tenant)
    order_date = _parse_date(order_date, "Order date").isoformat()
    input_item = conn.execute("SELECT * FROM item WHERE id=? AND tenant_id=?",
                              (input_item_id, tenant_id)).fetchone()
    output_item = conn.execute("SELECT * FROM item WHERE id=? AND tenant_id=?",
                               (output_item_id, tenant_id)).fetchone()
    if not input_item or not output_item:
        raise AdvancedError("ITEM_NOT_FOUND", "Choose valid input and output items")
    try:
        input_qty_milli = int(input_qty_milli)
        output_qty_milli = int(output_qty_milli)
        standard_input_qty_milli = int(standard_input_qty_milli or 0)
        input_cost_paise = int(input_cost_paise if input_cost_paise is not None
                               else input_item["cost_paise"])
        output_cost_paise = int(output_cost_paise if output_cost_paise is not None
                                else output_item["cost_paise"])
    except (TypeError, ValueError):
        raise AdvancedError("BAD_NUMBER", "Quantities and costs must be whole numbers")
    if input_qty_milli <= 0 or output_qty_milli < 0:
        raise AdvancedError("BAD_QTY", "Input quantity must be positive")
    if standard_input_qty_milli < 0 or input_cost_paise < 0 or output_cost_paise < 0:
        raise AdvancedError("BAD_NUMBER", "Standard quantity and costs cannot be negative")
    order_no = (order_no or "").strip().upper()
    if order_no:
        if conn.execute("SELECT 1 FROM production_order WHERE tenant_id=? AND order_no=?",
                        (tenant_id, order_no)).fetchone():
            raise AdvancedError("DUPLICATE", "This production order number already exists")
    else:
        order_no = db.next_number(conn, tenant_id, "production_order", "PRD")
    order_id = db.new_id()
    conn.execute(
        "INSERT INTO production_order (id, tenant_id, order_no, order_date,"
        " output_item_id, input_item_id, output_qty_milli, input_qty_milli,"
        " standard_input_qty_milli, input_cost_paise, output_cost_paise, status,"
        " note, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'open', ?,?,?)",
        (order_id, tenant_id, order_no, order_date, output_item_id, input_item_id,
         output_qty_milli, input_qty_milli, standard_input_qty_milli,
         input_cost_paise, output_cost_paise, (note or "").strip()[:200],
         created_by, db.now()))
    _audit(conn, tenant_id, created_by, "production.create", "production_order", order_id,
           {"order_no": order_no, "input_item_id": input_item_id,
            "output_item_id": output_item_id, "input_qty_milli": input_qty_milli,
            "output_qty_milli": output_qty_milli})
    return order_id


def set_production_status(conn: sqlite3.Connection, tenant, order_id: str,
                          status: str, reason: str = "",
                          actor: str | None = None) -> None:
    tenant_id = _tenant_id(tenant)
    if status not in {"open", "completed", "void"}:
        raise AdvancedError("BAD_STATUS", "Choose a valid production status")
    row = conn.execute("SELECT * FROM production_order WHERE id=? AND tenant_id=?",
                       (order_id, tenant_id)).fetchone()
    if not row:
        raise AdvancedError("NOT_FOUND", "Production order not found")
    if row["status"] == "void":
        raise AdvancedError("ALREADY_VOID", "Production order is already void")
    if status == "void" and not (reason or "").strip():
        raise AdvancedError("REASON_REQUIRED", "Enter a reason for voiding the order")
    completed_at = db.now() if status == "completed" else None
    conn.execute(
        "UPDATE production_order SET status=?, completed_at=?, note=CASE WHEN ?='' THEN note ELSE ? END"
        " WHERE id=? AND tenant_id=?",
        (status, completed_at, (reason or "").strip()[:200], (reason or "").strip()[:200],
         order_id, tenant_id))
    _audit(conn, tenant_id, actor, "production.status", "production_order", order_id,
           {"from": row["status"], "to": status, "reason": (reason or "")[:200]})


def consolidation_tenants(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    """Tenants the user may consolidate: active owner/admin memberships only."""
    rows = conn.execute(
        "SELECT t.id, t.name, t.slug, m.role FROM membership m"
        " JOIN tenant t ON t.id=m.tenant_id"
        " WHERE m.user_id=? AND m.status='active' AND t.status='active'"
        " AND m.role IN ('owner','admin') ORDER BY t.name", (user_id,)).fetchall()
    return [dict(r) for r in rows]
