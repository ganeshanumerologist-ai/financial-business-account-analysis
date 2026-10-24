"""Tests for receipts, vendor bills/payments, credit notes, ageing, GST and day book."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acc
from app import db

TODAY = "2026-10-24"


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Demo Co", "demo", state_code="27")
        self.cust = self.party("customer", "Test Customer")
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

    def invoice(self, qty=1000, when=TODAY, price=None):
        payload = {"item_id": self.it, "qty": qty}
        if price is not None:
            payload["unit_price"] = price
        return acc.create_invoice(self.conn, self.t, self.cust, when, "27", [payload])

    def bill(self, qty=1000, price=10000, when=TODAY):
        return acc.create_bill(self.conn, self.t, self.vend, when, "VB-1", "27",
                               [{"item_id": self.it, "qty": qty, "unit_price": price}])

    def receipt(self, amount, alloc, inv_id, key=None):
        return acc.record_payment(self.conn, self.t, "receipt", self.cust, TODAY, amount, "bank",
                                  [{"doc_type": "invoice", "doc_id": inv_id, "amount": alloc}],
                                  idempotency_key=key)

    def vendor_payment(self, amount, alloc, bill_id, key=None):
        return acc.record_payment(self.conn, self.t, "payment", self.vend, TODAY, amount, "bank",
                                  [{"doc_type": "bill", "doc_id": bill_id, "amount": alloc}],
                                  idempotency_key=key)

    def tb(self):
        return {r["code"]: r["balance"] for r in acc.trial_balance(self.conn, self.t, TODAY)["rows"]}


class TestReceipts(Base):
    def test_full_receipt_clears_receivable(self):
        inv = self.invoice()
        self.receipt(11800, 11800, inv["id"])
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, inv["id"]), 0)
        tb = self.tb()
        self.assertEqual(tb["1100"], 0)
        self.assertEqual(tb["1010"], 11800)

    def test_partial_receipt(self):
        inv = self.invoice()
        self.receipt(5000, 5000, inv["id"])
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, inv["id"]), 6800)
        self.assertEqual(self.tb()["1100"], 6800)

    def test_over_allocation_rejected(self):
        inv = self.invoice()
        with self.assertRaises(acc.AccountingError) as ctx:
            self.receipt(20000, 20000, inv["id"])
        self.assertEqual(ctx.exception.code, "OVER_ALLOCATION")
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, inv["id"]), 11800)

    def test_allocations_cannot_exceed_amount(self):
        inv = self.invoice()
        with self.assertRaises(acc.AccountingError) as ctx:
            self.receipt(5000, 6000, inv["id"])
        self.assertEqual(ctx.exception.code, "OVER_ALLOCATION")

    def test_receipt_idempotent(self):
        inv = self.invoice()
        a = self.receipt(11800, 11800, inv["id"], key="rcpt-1")
        b = self.receipt(11800, 11800, inv["id"], key="rcpt-1")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM payment").fetchone()["c"], 1)
        self.assertEqual(self.tb()["1010"], 11800)

    def test_foreign_invoice_rejected(self):
        other = db.create_tenant(self.conn, "Other", "other", state_code="27")
        other_cust = db.new_id()
        self.conn.execute(
            "INSERT INTO customer (id, tenant_id, name, state_code, created_at) VALUES (?,?,?,?,?)",
            (other_cust, other, "Foreign", "27", db.now()))
        other_item = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise, tax_rate_bp,"
            " stock_milli, track_stock) VALUES (?,?,?,?,?,?,?,?,?)",
            (other_item, other, "F1", "Foreign item", 10000, 0, 1800, 10000, 0))
        foreign = acc.create_invoice(self.conn, other, other_cust, TODAY, "27",
                                     [{"item_id": other_item, "qty": 1000}])
        with self.assertRaises(acc.AccountingError) as ctx:
            self.receipt(11800, 11800, foreign["id"])
        self.assertEqual(ctx.exception.code, "DOC_NOT_FOUND")

    def test_customer_statement_includes_receipt(self):
        inv = self.invoice()
        self.receipt(5000, 5000, inv["id"])
        st = acc.customer_statement(self.conn, self.t, self.cust, "2026-04-01", "2027-03-31")
        self.assertEqual(st["closing"], 6800)
        self.assertEqual(st["received"], 5000)
        self.assertEqual(st["invoiced"], 11800)


class TestBills(Base):
    def test_bill_posts_input_tax_and_stock(self):
        bill = self.bill(qty=2000, price=5000)
        self.assertEqual(bill["sub_total_paise"], 10000)
        self.assertEqual(bill["tax_paise"], 1800)
        self.assertEqual(bill["total_paise"], 11800)
        tb = self.tb()
        self.assertEqual(tb["2000"], -11800)
        self.assertEqual(tb["2200"], 900)
        self.assertEqual(tb["2201"], 900)
        self.assertEqual(tb["1200"], 10000)

    def test_weighted_average_cost(self):
        self.bill(qty=2000, price=5000)
        item = self.conn.execute("SELECT stock_milli, cost_paise FROM item WHERE id=?", (self.it,)).fetchone()
        self.assertEqual(item["stock_milli"], 12000)
        self.assertEqual(item["cost_paise"], 5833)  # (10 x 6000 + 2 x 5000) / 12

    def test_purchase_at_current_cost_keeps_average(self):
        self.bill(qty=2000, price=6000)
        item = self.conn.execute("SELECT stock_milli, cost_paise FROM item WHERE id=?", (self.it,)).fetchone()
        self.assertEqual(item["stock_milli"], 12000)
        self.assertEqual(item["cost_paise"], 6000)

    def test_service_invoice_does_not_touch_stock(self):
        service = self.item(price=250000, cost=0, stock=0, rate=1800, track=0, sku="SRV1")
        before = self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (service,)).fetchone()[0]
        inv = acc.create_invoice(self.conn, self.t, self.cust, TODAY, "27",
                                 [{"item_id": service, "qty": 2000}])
        after = self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (service,)).fetchone()[0]
        self.assertEqual(before, 0)
        self.assertEqual(after, 0)
        self.assertEqual(self.tb()["4000"], -500000)
        self.assertEqual(self.tb()["5000"], 0)

    def test_vendor_payment_clears_payable(self):
        bill = self.bill()
        self.vendor_payment(11800, 11800, bill["id"])
        self.assertEqual(acc.bill_outstanding(self.conn, self.t, bill["id"]), 0)
        self.assertEqual(self.tb()["2000"], 0)

    def test_bill_overpayment_rejected(self):
        bill = self.bill()
        with self.assertRaises(acc.AccountingError) as ctx:
            self.vendor_payment(20000, 20000, bill["id"])
        self.assertEqual(ctx.exception.code, "OVER_ALLOCATION")

    def test_inter_state_bill_uses_igst(self):
        other_vendor = db.new_id()
        self.conn.execute(
            "INSERT INTO vendor (id, tenant_id, name, state_code, created_at) VALUES (?,?,?,?,?)",
            (other_vendor, self.t, "Outside", "29", db.now()))
        bill = acc.create_bill(self.conn, self.t, other_vendor, TODAY, "VB-9", "29",
                               [{"item_id": self.it, "qty": 1000, "unit_price": 5000}])
        tb = self.tb()
        self.assertEqual(tb["2202"], 900)
        self.assertEqual(tb["2200"], 0)
        self.assertEqual(bill["total_paise"], 5900)


class TestCreditNotes(Base):
    def test_credit_note_reverses_sale_and_restores_stock(self):
        inv = self.invoice()
        line = self.conn.execute("SELECT * FROM invoice_line WHERE invoice_id=?", (inv["id"],)).fetchone()
        note = acc.create_credit_note(self.conn, self.t, inv["id"], TODAY, "Damaged return",
                                      [{"invoice_line_id": line["id"], "qty": 1000}])
        self.assertEqual(note["total_paise"], 11800)
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, inv["id"]), 0)
        tb = self.tb()
        self.assertEqual(tb["1100"], 0)
        self.assertEqual(tb["4000"], 0)
        self.assertEqual(tb["5000"], 0)
        stock = self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (self.it,)).fetchone()[0]
        self.assertEqual(stock, 10000)

    def test_partial_credit_note(self):
        inv = self.invoice(qty=2000)
        line = self.conn.execute("SELECT * FROM invoice_line WHERE invoice_id=?", (inv["id"],)).fetchone()
        note = acc.create_credit_note(self.conn, self.t, inv["id"], TODAY, "Short supply",
                                      [{"invoice_line_id": line["id"], "qty": 500}])
        self.assertEqual(note["sub_total_paise"], 5000)
        self.assertEqual(note["tax_paise"], 900)
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, inv["id"]), 17700)

    def test_over_credit_rejected(self):
        inv = self.invoice()
        line = self.conn.execute("SELECT * FROM invoice_line WHERE invoice_id=?", (inv["id"],)).fetchone()
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.create_credit_note(self.conn, self.t, inv["id"], TODAY, "Too much",
                                   [{"invoice_line_id": line["id"], "qty": 2000}])
        self.assertEqual(ctx.exception.code, "OVER_CREDIT")

    def test_reason_required(self):
        inv = self.invoice()
        line = self.conn.execute("SELECT * FROM invoice_line WHERE invoice_id=?", (inv["id"],)).fetchone()
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.create_credit_note(self.conn, self.t, inv["id"], TODAY, "  ",
                                   [{"invoice_line_id": line["id"], "qty": 1000}])
        self.assertEqual(ctx.exception.code, "REASON_REQUIRED")


class TestAgeingAndGST(Base):
    def test_receivable_ageing_buckets(self):
        old_date = (date.fromisoformat(TODAY) - timedelta(days=100)).isoformat()
        mid_date = (date.fromisoformat(TODAY) - timedelta(days=45)).isoformat()
        recent = self.invoice(qty=1000)
        older = self.invoice(qty=1000, when=mid_date)
        oldest = self.invoice(qty=1000, when=old_date)
        age = acc.receivable_ageing(self.conn, self.t, TODAY)
        self.assertEqual(age["totals"]["current"], 11800)
        self.assertEqual(age["totals"]["31-60"], 11800)
        self.assertEqual(age["totals"]["90+"], 11800)
        self.assertEqual(age["grand_total"], 35400)

        self.receipt(11800, 11800, recent["id"])
        age = acc.receivable_ageing(self.conn, self.t, TODAY)
        self.assertEqual(age["totals"]["current"], 0)
        self.assertEqual(age["grand_total"], 23600)

    def test_payable_ageing(self):
        self.bill()
        age = acc.payable_ageing(self.conn, self.t, TODAY)
        self.assertEqual(age["grand_total"], 11800)
        self.assertEqual(age["totals"]["current"], 11800)

    def test_gst_summary_nets_output_and_input(self):
        self.invoice()
        self.bill()
        g = acc.gst_summary(self.conn, self.t, "2026-04-01", "2027-03-31")
        self.assertEqual(g["output_total"], 1800)
        self.assertEqual(g["input_total"], 1800)
        self.assertEqual(g["net_payable"], 0)
        self.assertEqual(len(g["sales"]), 1)
        self.assertEqual(len(g["purchases"]), 1)

    def test_day_book_lists_all_vouchers(self):
        inv = self.invoice()
        self.receipt(11800, 11800, inv["id"])
        self.bill()
        entries = acc.day_book(self.conn, self.t, "2026-04-01", "2027-03-31")
        self.assertEqual(len(entries), 3)
        self.assertTrue(all(e["amount"] > 0 for e in entries))
        types = {e["source_type"] for e in entries}
        self.assertEqual(types, {"invoice", "receipt", "bill"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
