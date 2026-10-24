"""Purchase returns / debit notes: posting, stock, GST, payable and guards."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acc
from app import db

TODAY = "2026-10-24"


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Demo Co", "demo", state_code="27")
        self.vend = self.party("vendor", "Test Vendor")
        self.it = self.item()

    def tearDown(self):
        self.conn.close()

    def party(self, kind, name):
        pid = db.new_id()
        table = "customer" if kind == "customer" else "vendor"
        self.conn.execute(
            f"INSERT INTO {table} (id, tenant_id, name, state_code, created_at) VALUES (?,?,?,?,?)",
            (pid, self.t, name, "27", db.now()),
        )
        return pid

    def item(self, price=10000, cost=6000, stock=10000, rate=1800, track=1, sku="SKU1"):
        iid = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise,"
            " tax_rate_bp, stock_milli, track_stock) VALUES (?,?,?,?,?,?,?,?,?)",
            (iid, self.t, sku, f"Item {sku}", price, cost, rate, stock, track),
        )
        return iid

    def bill(self, qty=2000, price=5000, discount=0, when=TODAY, item=None):
        return acc.create_bill(
            self.conn, self.t, self.vend, when, "VB-1", "27",
            [{"item_id": item or self.it, "qty": qty, "unit_price": price,
              "discount": discount}])

    def debit(self, bill_id, qty=1000, line=None, reason="Returned to vendor", key=None):
        if line is None:
            line = self.conn.execute(
                "SELECT id FROM bill_line WHERE bill_id=? ORDER BY rowid LIMIT 1",
                (bill_id,)).fetchone()["id"]
        return acc.create_debit_note(
            self.conn, self.t, bill_id, TODAY, reason,
            [{"bill_line_id": line, "qty": qty}], idempotency_key=key)

    def tb(self):
        return {r["code"]: r["balance"]
                for r in acc.trial_balance(self.conn, self.t, TODAY)["rows"]}


class TestDebitNotes(Base):
    def test_partial_return_reverses_purchase_gst_and_stock(self):
        bill = self.bill(qty=2000, price=5000)
        note = self.debit(bill["id"], qty=1000)
        self.assertEqual(note["sub_total_paise"], 5000)
        self.assertEqual(note["tax_paise"], 900)
        self.assertEqual(note["total_paise"], 5900)

        tb = self.tb()
        self.assertEqual(tb["2000"], -5900)      # payable reduced
        self.assertEqual(tb["1200"], 5000)       # inventory reduced
        self.assertEqual(tb["2200"], 450)        # input CGST reduced
        self.assertEqual(tb["2201"], 450)        # input SGST reduced
        item = self.conn.execute("SELECT stock_milli, cost_paise FROM item WHERE id=?",
                                 (self.it,)).fetchone()
        self.assertEqual(item["stock_milli"], 11000)
        self.assertEqual(item["cost_paise"], 5909)
        self.assertEqual(acc.bill_outstanding(self.conn, self.t, bill["id"]), 5900)

    def test_full_return_clears_payable_and_inventory(self):
        bill = self.bill(qty=2000, price=5000)
        self.debit(bill["id"], qty=2000)
        tb = self.tb()
        self.assertEqual(tb["2000"], 0)
        self.assertEqual(tb["1200"], 0)
        self.assertEqual(tb["2200"], 0)
        self.assertEqual(tb["2201"], 0)
        self.assertEqual(acc.bill_outstanding(self.conn, self.t, bill["id"]), 0)
        item = self.conn.execute("SELECT stock_milli, cost_paise FROM item WHERE id=?",
                                 (self.it,)).fetchone()
        self.assertEqual(item["stock_milli"], 10000)
        self.assertEqual(item["cost_paise"], 6000)

    def test_inter_state_return_reverses_igst(self):
        bill = acc.create_bill(self.conn, self.t, self.vend, TODAY, "VB-2", "07",
                               [{"item_id": self.it, "qty": 1000, "unit_price": 5000}])
        self.debit(bill["id"], qty=1000)
        tb = self.tb()
        self.assertEqual(tb["2202"], 0)
        self.assertEqual(tb["2200"], 0)
        self.assertEqual(tb["2201"], 0)

    def test_discount_is_reversed_proportionally(self):
        bill = self.bill(qty=2000, price=10000, discount=2000)
        self.assertEqual(bill["sub_total_paise"], 18000)
        note = self.debit(bill["id"], qty=1000)
        self.assertEqual(note["sub_total_paise"], 9000)
        self.assertEqual(note["tax_paise"], 1620)
        self.assertEqual(note["total_paise"], 10620)

    def test_non_stock_return_reverses_purchases(self):
        service = self.item(price=10000, cost=0, stock=0, rate=1800, track=0, sku="SRV")
        bill = self.bill(qty=1000, price=10000, item=service)
        self.debit(bill["id"], qty=500)
        tb = self.tb()
        self.assertEqual(tb["5100"], 5000)
        self.assertEqual(tb["1200"], 0)
        self.assertEqual(tb["2000"], -5900)

    def test_over_return_rejected(self):
        bill = self.bill(qty=2000)
        with self.assertRaises(acc.AccountingError) as ctx:
            self.debit(bill["id"], qty=3000)
        self.assertEqual(ctx.exception.code, "OVER_DEBIT")
        self.assertEqual(acc.bill_outstanding(self.conn, self.t, bill["id"]), 11800)

    def test_second_return_cannot_exceed_remaining_quantity(self):
        bill = self.bill(qty=2000)
        self.debit(bill["id"], qty=1500)
        with self.assertRaises(acc.AccountingError) as ctx:
            self.debit(bill["id"], qty=1000)
        self.assertEqual(ctx.exception.code, "OVER_DEBIT")

    def test_reason_required(self):
        bill = self.bill()
        with self.assertRaises(acc.AccountingError) as ctx:
            self.debit(bill["id"], qty=1000, reason="  ")
        self.assertEqual(ctx.exception.code, "REASON_REQUIRED")

    def test_insufficient_stock_rejected(self):
        bill = self.bill(qty=2000)
        self.conn.execute("UPDATE item SET stock_milli=500 WHERE id=?", (self.it,))
        with self.assertRaises(acc.AccountingError) as ctx:
            self.debit(bill["id"], qty=1000)
        self.assertEqual(ctx.exception.code, "INSUFFICIENT_STOCK")

    def test_idempotent(self):
        bill = self.bill()
        a = self.debit(bill["id"], qty=1000, key="dn-1")
        b = self.debit(bill["id"], qty=1000, key="dn-1")
        self.assertEqual(a["id"], b["id"])
        count = self.conn.execute("SELECT COUNT(*) c FROM debit_note").fetchone()["c"]
        self.assertEqual(count, 1)
        self.assertEqual(self.tb()["1200"], 5000)

    def test_vendor_statement_and_gst_summary_include_return(self):
        bill = self.bill(qty=2000, price=5000)
        self.debit(bill["id"], qty=1000)
        st = acc.vendor_statement(self.conn, self.t, self.vend, "2026-04-01", "2027-03-31")
        self.assertEqual(st["closing"], 5900)
        self.assertEqual(st["paid"], 0)
        self.assertEqual(st["debited"], 5900)
        g = acc.gst_summary(self.conn, self.t, "2026-04-01", "2027-03-31")
        self.assertEqual(g["input"]["CGST"], 450)
        self.assertEqual(g["input"]["SGST"], 450)
        self.assertEqual(g["input_total"], 900)
        self.assertEqual(g["net_payable"], -900)

    def test_cross_tenant_bill_rejected(self):
        other = db.create_tenant(self.conn, "Other", "other", state_code="27")
        other_vendor = db.new_id()
        self.conn.execute(
            "INSERT INTO vendor (id, tenant_id, name, state_code, created_at) VALUES (?,?,?,?,?)",
            (other_vendor, other, "Other Vendor", "27", db.now()))
        other_item = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise,"
            " tax_rate_bp, stock_milli, track_stock) VALUES (?,?,?,?,?,?,?,?,?)",
            (other_item, other, "O1", "Other item", 10000, 5000, 1800, 10000, 1))
        foreign = acc.create_bill(self.conn, other, other_vendor, TODAY, "F-1", "27",
                                  [{"item_id": other_item, "qty": 1000, "unit_price": 5000}])
        with self.assertRaises(acc.AccountingError) as ctx:
            self.debit(foreign["id"], qty=100)
        self.assertEqual(ctx.exception.code, "DOC_NOT_FOUND")

    def test_paid_bill_can_still_be_returned(self):
        bill = self.bill(qty=2000, price=5000)
        acc.record_payment(self.conn, self.t, "payment", self.vend, TODAY, 11800, "bank",
                           [{"doc_type": "bill", "doc_id": bill["id"], "amount": 11800}])
        self.debit(bill["id"], qty=1000)
        self.assertEqual(acc.bill_outstanding(self.conn, self.t, bill["id"]), -5900)
        balances = {r["id"]: r["balance"] for r in acc.vendor_balances(self.conn, self.t)}
        self.assertEqual(balances[self.vend], -5900)


if __name__ == "__main__":
    unittest.main(verbosity=2)
