"""Demo data for local evaluation. Synthetic only — no real customer data.

Everything here is created through the same posting engine the UI uses, so the
demo books are exactly as valid as any user's books.
"""
from __future__ import annotations

import os
import sqlite3

from . import accounting as acct
from . import db, security

DEMO_EMAIL = "owner@arthivio.test"
DEMO_ADMIN_EMAIL = "admin@arthivio.test"
DEMO_PASSWORD = os.environ.get("ARTHIVIO_DEMO_PASSWORD", "ArthivioDemo!2026")


def seed_demo(conn: sqlite3.Connection) -> dict | None:
    """Create a demo tenant once. Returns summary or None if already seeded."""
    if conn.execute("SELECT 1 FROM tenant WHERE slug='arthivio-demo'").fetchone():
        return None

    tenant_id = db.create_tenant(conn, "Arthivio Demo Trading", "arthivio-demo", state_code="27")

    owner = security.create_user(conn, DEMO_EMAIL, DEMO_PASSWORD, "Demo Owner")
    security.add_membership(conn, tenant_id, owner, "owner")
    admin = security.create_user(conn, DEMO_ADMIN_EMAIL, DEMO_PASSWORD, "Demo Admin")
    security.add_membership(conn, tenant_id, admin, "admin")

    customers = {}
    for name, phone, gstin, state in [
        ("Sundaram Traders", "+91 98200 11001", "27AABCS1429B1Z1", "27"),
        ("Kaveri Enterprises", "+91 98200 11002", "27AACCK8765M1Z4", "27"),
        ("Northern Lights LLP", "+91 98110 22003", "07AAFCN4321P1Z9", "07"),
        ("Blue Harbour Co.", "+91 90040 33004", "", "29"),
    ]:
        cid = db.new_id()
        conn.execute(
            "INSERT INTO customer (id, tenant_id, name, phone, gstin, state_code, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (cid, tenant_id, name, phone, gstin, state, db.now()),
        )
        customers[name] = cid

    items = {}
    for sku, name, price, cost, rate, stock, track in [
        ("TRD-001", "Cotton Kurta (Premium)", 149900, 92000, 500, 120000, 1),
        ("TRD-002", "Handloom Stole", 64900, 38000, 500, 150000, 1),
        ("TRD-003", "Brass Diya Set", 24900, 14500, 1200, 200000, 1),
        ("TRD-004", "Gift Hamper", 349900, 210000, 1800, 40000, 1),
        ("SRV-001", "Interior Consulting (hour)", 250000, 0, 1800, 0, 0),
    ]:
        iid = db.new_id()
        conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, unit, sale_price_paise, cost_paise,"
            " tax_rate_bp, stock_milli, track_stock, revenue_code) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (iid, tenant_id, sku, name, "pcs" if track else "hour", price, cost, rate, stock,
             track, "4000" if track else "4100"),
        )
        items[sku] = iid

    bank = db.account_id(conn, tenant_id, "1010")
    equity = db.account_id(conn, tenant_id, "3000")
    rent = db.account_id(conn, tenant_id, "6000")
    inventory = db.account_id(conn, tenant_id, "1200")

    acct.post_journal(conn, tenant_id, "2026-04-01", "Opening capital introduced", [
        {"account_id": bank, "debit": 50000000, "credit": 0, "memo": "Bank"},
        {"account_id": equity, "debit": 0, "credit": 50000000, "memo": "Owner equity"},
    ], "opening", idempotency_key="demo-capital", created_by=owner)

    # Opening stock valued at cost: 120x920 + 150x380 + 200x145 + 40x2100 = 280,400.00
    acct.post_journal(conn, tenant_id, "2026-04-01", "Opening inventory at cost", [
        {"account_id": inventory, "debit": 28040000, "credit": 0, "memo": "Opening stock"},
        {"account_id": equity, "debit": 0, "credit": 28040000, "memo": "Owner equity"},
    ], "opening", idempotency_key="demo-opening-stock", created_by=owner)

    for month in range(4, 10):
        acct.post_journal(conn, tenant_id, f"2026-{month:02d}-05", f"Office rent {month:02d}/2026", [
            {"account_id": rent, "debit": 800000, "credit": 0, "memo": "Rent"},
            {"account_id": bank, "debit": 0, "credit": 800000, "memo": "Bank"},
        ], "expense", idempotency_key=f"demo-rent-{month}", created_by=owner)

    plan = [
        ("2026-05-12", "Sundaram Traders", "27", [("TRD-001", 6, None), ("TRD-002", 4, None)]),
        ("2026-05-28", "Kaveri Enterprises", "27", [("TRD-003", 20, 10)]),
        ("2026-06-09", "Northern Lights LLP", "07", [("TRD-004", 3, None)]),
        ("2026-06-24", "Blue Harbour Co.", "29", [("TRD-002", 10, 5)]),
        ("2026-07-14", "Sundaram Traders", "27", [("TRD-001", 8, None), ("TRD-003", 12, None)]),
        ("2026-08-03", "Kaveri Enterprises", "27", [("SRV-001", 6, None)]),
        ("2026-08-21", "Northern Lights LLP", "07", [("TRD-004", 2, None), ("TRD-002", 5, None)]),
        ("2026-09-11", "Blue Harbour Co.", "29", [("TRD-001", 4, None)]),
        ("2026-09-29", "Sundaram Traders", "27", [("TRD-003", 30, 15)]),
        ("2026-10-08", "Kaveri Enterprises", "27", [("TRD-002", 8, None), ("TRD-004", 1, None)]),
        ("2026-10-19", "Northern Lights LLP", "07", [("SRV-001", 4, None)]),
    ]

    invoice_ids: list[str] = []
    for idx, (when, customer, state, lines) in enumerate(plan, start=1):
        payload = []
        for sku, qty, discount_pct in lines:
            price = conn.execute("SELECT sale_price_paise FROM item WHERE id=?", (items[sku],)).fetchone()[0]
            units = qty * 2
            gross = units * price
            payload.append({
                "item_id": items[sku], "qty": units * 1000,
                "discount": gross * (discount_pct or 0) // 100,
            })
        invoice = acct.create_invoice(
            conn, tenant_id, customers[customer], when, state, payload,
            idempotency_key=f"demo-invoice-{idx}", round_to_rupee=True, created_by=owner,
        )
        invoice_ids.append(invoice["id"])

    # ---- purchases: vendors, bills, vendor payments ----
    vendors = {}
    for name, phone, gstin, state in [
        ("Loom House Pvt Ltd", "+91 98210 55001", "27AAACL1234C1Z5", "27"),
        ("Northern Crafts", "+91 98120 66002", "07AABCN9876D1Z2", "07"),
    ]:
        vid = db.new_id()
        conn.execute(
            "INSERT INTO vendor (id, tenant_id, name, phone, gstin, state_code, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (vid, tenant_id, name, phone, gstin, state, db.now()),
        )
        vendors[name] = vid

    bill_plan = [
        ("2026-05-05", "Loom House Pvt Ltd", "27", "LH-2026-041", [("TRD-001", 40), ("TRD-002", 50)]),
        ("2026-07-01", "Northern Crafts", "07", "NC-8891", [("TRD-003", 100)]),
        ("2026-08-10", "Loom House Pvt Ltd", "27", "LH-2026-097", [("TRD-004", 20)]),
    ]
    bill_ids = []
    for idx, (when, vendor, state, vendor_bill_no, lines) in enumerate(bill_plan, start=1):
        payload = []
        for sku, units in lines:
            cost = conn.execute("SELECT cost_paise FROM item WHERE id=?", (items[sku],)).fetchone()[0]
            payload.append({"item_id": items[sku], "qty": units * 1000, "unit_price": cost})
        bill = acct.create_bill(
            conn, tenant_id, vendors[vendor], when, vendor_bill_no, state, payload,
            idempotency_key=f"demo-bill-{idx}", round_to_rupee=True, created_by=owner,
        )
        bill_ids.append(bill["id"])

    # ---- receipts against invoices ----
    def invoice_total(invoice_id: str) -> int:
        return conn.execute("SELECT total_paise FROM invoice WHERE id=?", (invoice_id,)).fetchone()[0]

    receipt_plan = [
        ("2026-06-01", invoice_ids[0], invoice_total(invoice_ids[0]), "bank", "NEFT-88421", "full"),
        ("2026-06-15", invoice_ids[1], invoice_total(invoice_ids[1]) // 2, "upi", "UPI-552013", "part"),
        ("2026-07-02", invoice_ids[2], invoice_total(invoice_ids[2]), "cheque", "CHQ-100234", "full"),
        ("2026-08-30", invoice_ids[4], invoice_total(invoice_ids[4]) // 2, "bank", "NEFT-90114", "part"),
        ("2026-10-20", invoice_ids[5], invoice_total(invoice_ids[5]), "cash", "", "full"),
    ]
    for idx, (when, invoice_id, amount, mode, reference, _kind) in enumerate(receipt_plan, start=1):
        customer_id = conn.execute("SELECT customer_id FROM invoice WHERE id=?", (invoice_id,)).fetchone()[0]
        acct.record_payment(
            conn, tenant_id, "receipt", customer_id, when, amount, mode,
            [{"doc_type": "invoice", "doc_id": invoice_id, "amount": amount}],
            reference=reference, idempotency_key=f"demo-receipt-{idx}", created_by=owner,
        )

    # ---- vendor payments ----
    def bill_total(bill_id: str) -> int:
        return conn.execute("SELECT total_paise FROM bill WHERE id=?", (bill_id,)).fetchone()[0]

    payment_plan = [
        ("2026-05-20", bill_ids[0], bill_total(bill_ids[0]), "bank", "NEFT-77120"),
        ("2026-08-01", bill_ids[1], bill_total(bill_ids[1]) // 2, "bank", "NEFT-84210"),
    ]
    for idx, (when, bill_id, amount, mode, reference) in enumerate(payment_plan, start=1):
        vendor_id = conn.execute("SELECT vendor_id FROM bill WHERE id=?", (bill_id,)).fetchone()[0]
        acct.record_payment(
            conn, tenant_id, "payment", vendor_id, when, amount, mode,
            [{"doc_type": "bill", "doc_id": bill_id, "amount": amount}],
            reference=reference, idempotency_key=f"demo-vendor-payment-{idx}", created_by=owner,
        )

    # ---- one sales return / credit note ----
    line = conn.execute(
        "SELECT l.id FROM invoice_line l JOIN invoice i ON i.id=l.invoice_id"
        " WHERE i.id=? AND l.item_id=? LIMIT 1",
        (invoice_ids[1], items["TRD-003"]),
    ).fetchone()
    if line:
        acct.create_credit_note(
            conn, tenant_id, invoice_ids[1], "2026-06-20", "Two units returned damaged in transit",
            [{"invoice_line_id": line["id"], "qty": 2000}],
            idempotency_key="demo-credit-note-1", created_by=owner,
        )

    return {"tenant_id": tenant_id, "invoices": len(plan), "bills": len(bill_plan),
            "owner": DEMO_EMAIL, "admin": DEMO_ADMIN_EMAIL, "password": DEMO_PASSWORD}


def summary(conn: sqlite3.Connection, tenant_id: str) -> dict:
    tb = acct.trial_balance(conn, tenant_id, "2026-12-31")
    return {
        "accounts": len(tb["rows"]),
        "entries": conn.execute("SELECT COUNT(*) c FROM journal_entry WHERE tenant_id=?", (tenant_id,)).fetchone()["c"],
        "balanced": tb["balanced"],
        "total_debit": tb["total_debit"],
    }
