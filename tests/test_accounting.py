"""Deterministic tests for the accounting core. stdlib unittest, no network."""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acc
from app import db, drafts, i18n, money, security


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Demo Co", "demo", state_code="27")
        self.cust = db.new_id()
        self.conn.execute(
            "INSERT INTO customer (id, tenant_id, name, state_code, created_at) VALUES (?,?,?,?,?)",
            (self.cust, self.t, "Test Customer", "27", db.now()),
        )

    def tearDown(self):
        self.conn.close()

    def item(self, price=10000, cost=6000, stock=10000, rate=1800, track=1, sku="SKU1",
             revenue_code="4000"):
        iid = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise,"
            " tax_rate_bp, stock_milli, track_stock, revenue_code) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (iid, self.t, sku, f"Item {sku}", price, cost, rate, stock, track, revenue_code),
        )
        return iid

    def invoice(self, items, state="27", round_to_rupee=False, key=None):
        return acc.create_invoice(self.conn, self.t, self.cust, "2026-10-24", state, items,
                                  idempotency_key=key, round_to_rupee=round_to_rupee)


class TestMoney(unittest.TestCase):
    def test_parse_rejects_float(self):
        with self.assertRaises(money.MoneyError):
            money.parse_amount(10.5)

    def test_parse_and_format(self):
        self.assertEqual(money.parse_amount("1,234.56"), 123456)
        self.assertEqual(money.fmt(123456), "\u20b91,234.56")
        self.assertEqual(money.fmt(123456789), "\u20b912,34,567.89")
        self.assertEqual(money.fmt(-100), "-\u20b91.00")

    def test_hindi_display_uses_devanagari_digits_and_narration(self):
        token = i18n.set_current_language("hi")
        try:
            self.assertEqual(money.fmt(123456), "\u20b9१,२३४.५६")
            self.assertEqual(
                i18n.auto("Invoice for {party}", party="Test Customer"),
                "Test Customer के लिए चालान")
        finally:
            i18n.reset_current_language(token)
        self.assertEqual(money.fmt(123456), "\u20b91,234.56")

    def test_three_decimals_rejected(self):
        with self.assertRaises(money.MoneyError):
            money.parse_amount("10.005")

    def test_parse_percent_to_basis_points(self):
        self.assertEqual(money.parse_percent("18"), 1800)
        self.assertEqual(money.parse_percent("18.5%"), 1850)
        self.assertEqual(money.parse_percent(""), 0)
        with self.assertRaises(money.MoneyError):
            money.parse_percent(18.5)
        with self.assertRaises(money.MoneyError):
            money.parse_percent("18.555")

    def test_tax_half_up(self):
        # 9999 * 5% = 499.95 paise -> 500 paise
        self.assertEqual(money.tax_on(9999, 500), 500)
        # 1 paise at 18% = 0.18 -> 0
        self.assertEqual(money.tax_on(1, 1800), 0)
        # exact half rounds up: base 50 bp 100 (=1%) => 0.5 -> 1
        self.assertEqual(money.tax_on(50, 100), 1)

    def test_allocate_sums_exactly(self):
        parts = money.allocate(10000, [1, 1, 1])
        self.assertEqual(sum(parts), 10000)
        self.assertEqual(sorted(parts), [3333, 3333, 3334])
        parts = money.allocate(1, [1, 1, 1])
        self.assertEqual(sum(parts), 1)


class TestPosting(Base):
    def test_unbalanced_rejected(self):
        a = db.account_id(self.conn, self.t, "1000")
        b = db.account_id(self.conn, self.t, "4000")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.post_journal(self.conn, self.t, "2026-10-24", "bad",
                             [{"account_id": a, "debit": 100, "credit": 0},
                              {"account_id": b, "debit": 0, "credit": 99}], "manual")
        self.assertEqual(ctx.exception.code, "UNBALANCED")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM journal_entry").fetchone()["c"], 0)

    def test_zero_and_single_side(self):
        a = db.account_id(self.conn, self.t, "1000")
        b = db.account_id(self.conn, self.t, "4000")
        with self.assertRaises(acc.AccountingError):
            acc.post_journal(self.conn, self.t, "2026-10-24", "both sides",
                             [{"account_id": a, "debit": 100, "credit": 100},
                              {"account_id": b, "debit": 0, "credit": 0}], "manual")

    def test_balanced_posts_and_tb_balances(self):
        a = db.account_id(self.conn, self.t, "1000")
        b = db.account_id(self.conn, self.t, "3000")
        acc.post_journal(self.conn, self.t, "2026-10-24", "capital",
                         [{"account_id": a, "debit": 500000, "credit": 0},
                          {"account_id": b, "debit": 0, "credit": 500000}], "manual")
        tb = acc.trial_balance(self.conn, self.t, "2026-10-25")
        self.assertTrue(tb["balanced"])
        self.assertEqual(tb["total_debit"], 500000)

    def test_idempotent_posting(self):
        a = db.account_id(self.conn, self.t, "1000")
        b = db.account_id(self.conn, self.t, "3000")
        lines = [{"account_id": a, "debit": 1000, "credit": 0},
                 {"account_id": b, "debit": 0, "credit": 1000}]
        e1 = acc.post_journal(self.conn, self.t, "2026-10-24", "x", lines, "manual", idempotency_key="k1")
        e2 = acc.post_journal(self.conn, self.t, "2026-10-24", "x", lines, "manual", idempotency_key="k1")
        self.assertEqual(e1, e2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM journal_entry").fetchone()["c"], 1)

    def test_period_lock_blocks(self):
        self.conn.execute(
            "INSERT INTO period_lock (tenant_id, period_start, period_end, locked_at)"
            " VALUES (?,?,?,?)", (self.t, "2026-04-01", "2026-04-30", db.now()))
        a = db.account_id(self.conn, self.t, "1000")
        b = db.account_id(self.conn, self.t, "3000")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.post_journal(self.conn, self.t, "2026-04-15", "locked",
                             [{"account_id": a, "debit": 100, "credit": 0},
                              {"account_id": b, "debit": 0, "credit": 100}], "manual")
        self.assertEqual(ctx.exception.code, "PERIOD_LOCKED")

    def test_cross_tenant_account_rejected(self):
        other = db.create_tenant(self.conn, "Other Co", "other", state_code="29")
        foreign = db.account_id(self.conn, other, "1000")
        mine = db.account_id(self.conn, self.t, "4000")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.post_journal(self.conn, self.t, "2026-10-24", "leak",
                             [{"account_id": foreign, "debit": 100, "credit": 0},
                              {"account_id": mine, "debit": 0, "credit": 100}], "manual")
        self.assertEqual(ctx.exception.code, "ACCOUNT_NOT_FOUND")


class TestEntryCorrection(Base):
    def _entry(self, amount=1000):
        cash = db.account_id(self.conn, self.t, "1000")
        rent = db.account_id(self.conn, self.t, "6000")
        entry_id = acc.post_journal(
            self.conn, self.t, "2026-10-24", "Original rent entry",
            [{"account_id": rent, "debit": amount, "credit": 0},
             {"account_id": cash, "debit": 0, "credit": amount}],
            "manual")
        return entry_id, cash, rent

    def test_replace_reverses_and_reposts_with_audit(self):
        entry_id, cash, rent = self._entry(1000)
        result = acc.replace_entry(
            self.conn, self.t, entry_id, "2026-10-25", "Corrected rent entry",
            [{"account_id": rent, "debit": 1250, "credit": 0},
             {"account_id": cash, "debit": 0, "credit": 1250}],
            "Wrong amount entered")
        self.assertEqual(result["original_id"], entry_id)
        original = self.conn.execute(
            "SELECT * FROM journal_entry WHERE id=?", (entry_id,)).fetchone()
        self.assertEqual(original["status"], "reversed")
        reversal = self.conn.execute(
            "SELECT * FROM journal_entry WHERE id=?", (result["reversal_id"],)).fetchone()
        self.assertEqual(reversal["source_type"], "reversal")
        self.assertEqual(reversal["reversal_of"], entry_id)
        corrected = self.conn.execute(
            "SELECT * FROM journal_entry WHERE id=?", (result["entry_id"],)).fetchone()
        self.assertEqual(corrected["status"], "posted")
        self.assertEqual(corrected["source_type"], "manual")
        self.assertEqual(corrected["source_id"], entry_id)
        self.assertEqual(corrected["narration"], "Corrected rent entry")
        audit = self.conn.execute(
            "SELECT * FROM audit_log WHERE action='journal.edit'").fetchone()
        self.assertIsNotNone(audit)
        meta = json.loads(audit["meta"])
        self.assertEqual(meta["original_entry"], entry_id)
        self.assertEqual(meta["corrected_entry"], result["entry_id"])
        balances = {a["code"]: a for a in acc.account_balances(self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["1000"]["balance"], -1250)
        self.assertEqual(balances["6000"]["balance"], 1250)

    def test_bad_replacement_rolls_back_the_reversal(self):
        entry_id, cash, rent = self._entry(1000)
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.replace_entry(
                self.conn, self.t, entry_id, "2026-10-25", "Broken correction",
                [{"account_id": rent, "debit": 900, "credit": 0},
                 {"account_id": cash, "debit": 0, "credit": 1000}],
                "Try an unbalanced correction")
        self.assertEqual(ctx.exception.code, "UNBALANCED")
        original = self.conn.execute(
            "SELECT * FROM journal_entry WHERE id=?", (entry_id,)).fetchone()
        self.assertEqual(original["status"], "posted")
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) c FROM journal_entry WHERE source_type='reversal'").fetchone()["c"], 0)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE action='journal.edit'").fetchone()["c"], 0)

    def test_non_manual_reason_and_cross_tenant_are_rejected(self):
        entry_id, cash, rent = self._entry(1000)
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.replace_entry(
                self.conn, self.t, entry_id, "2026-10-25", "No reason",
                [{"account_id": rent, "debit": 1000, "credit": 0},
                 {"account_id": cash, "debit": 0, "credit": 1000}], "")
        self.assertEqual(ctx.exception.code, "REASON_REQUIRED")

        other = db.create_tenant(self.conn, "Other Co", "other", state_code="29")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.replace_entry(
                self.conn, other, entry_id, "2026-10-25", "Leak",
                [{"account_id": rent, "debit": 1000, "credit": 0},
                 {"account_id": cash, "debit": 0, "credit": 1000}], "cross tenant")
        self.assertEqual(ctx.exception.code, "ENTRY_NOT_FOUND")

        opening = acc.set_opening_balance(
            self.conn, self.t, db.account_id(self.conn, self.t, "1010"),
            "2026-04-01", 5000, "debit")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.replace_entry(
                self.conn, self.t, opening, "2026-04-01", "Opening edit",
                [{"account_id": rent, "debit": 5000, "credit": 0},
                 {"account_id": cash, "debit": 0, "credit": 5000}], "not manual")
        self.assertEqual(ctx.exception.code, "NOT_EDITABLE")


class TestInvoice(Base):
    def test_totals_and_tax_intra_state(self):
        it = self.item(price=10000, cost=6000, stock=10000)  # ₹100 + 18%
        inv = self.invoice([{"item_id": it, "qty": 1000}])   # qty 1.000
        self.assertEqual(inv["sub_total_paise"], 10000)
        self.assertEqual(inv["tax_paise"], 1800)
        self.assertEqual(inv["total_paise"], 11800)
        self.assertEqual(inv["invoice_no"], "INV-00001")

        tb = {r["code"]: r for r in acc.trial_balance(self.conn, self.t, "2026-10-25")["rows"]}
        self.assertEqual(tb["1100"]["balance"], 11800)   # AR
        self.assertEqual(tb["4000"]["balance"], -10000)  # Sales credit
        self.assertEqual(tb["2100"]["balance"], -900)    # CGST half
        self.assertEqual(tb["2101"]["balance"], -900)    # SGST half

    def test_inter_state_uses_igst(self):
        it = self.item(price=10000, cost=0, stock=10000, track=0, sku="S2")
        inv = self.invoice([{"item_id": it, "qty": 1000}], state="29")
        self.assertEqual(inv["tax_paise"], 1800)
        tb = {r["code"]: r for r in acc.trial_balance(self.conn, self.t, "2026-10-25")["rows"]}
        self.assertEqual(tb["2102"]["balance"], -1800)
        self.assertEqual(tb["2100"]["balance"], 0)

    def test_service_item_posts_to_service_revenue(self):
        it = self.item(price=250000, cost=0, stock=0, track=0, sku="SRV", revenue_code="4100")
        inv = self.invoice([{"item_id": it, "qty": 2000}])  # 2 hours
        self.assertEqual(inv["sub_total_paise"], 500000)
        tb = {r["code"]: r for r in acc.trial_balance(self.conn, self.t, "2026-10-25")["rows"]}
        self.assertEqual(tb["4100"]["balance"], -500000)
        self.assertEqual(tb["4000"]["balance"], 0)

    def test_cogs_and_stock(self):
        it = self.item(price=10000, cost=6000, stock=2000)
        self.invoice([{"item_id": it, "qty": 1000}])
        stock = self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (it,)).fetchone()[0]
        self.assertEqual(stock, 1000)
        tb = {r["code"]: r for r in acc.trial_balance(self.conn, self.t, "2026-10-25")["rows"]}
        self.assertEqual(tb["5000"]["balance"], 6000)
        self.assertEqual(tb["1200"]["balance"], -6000)

    def test_insufficient_stock_blocked(self):
        it = self.item(stock=500)
        with self.assertRaises(acc.AccountingError) as ctx:
            self.invoice([{"item_id": it, "qty": 1000}])
        self.assertEqual(ctx.exception.code, "INSUFFICIENT_STOCK")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM invoice").fetchone()["c"], 0)

    def test_discount_cannot_exceed_line(self):
        it = self.item(price=10000)
        with self.assertRaises(acc.AccountingError) as ctx:
            self.invoice([{"item_id": it, "qty": 1000, "discount": 20000}])
        self.assertEqual(ctx.exception.code, "BAD_DISCOUNT")

    def test_round_to_rupee_posts_rounding(self):
        it = self.item(price=9999, cost=0, stock=10000, track=0)
        inv = self.invoice([{"item_id": it, "qty": 1000}], round_to_rupee=True)
        self.assertEqual(inv["sub_total_paise"], 9999)
        self.assertEqual(inv["tax_paise"], 1800)
        self.assertEqual(inv["round_off_paise"], 1)
        self.assertEqual(inv["total_paise"], 11800)
        tb = acc.trial_balance(self.conn, self.t, "2026-10-25")
        self.assertTrue(tb["balanced"])

    def test_invoice_idempotency(self):
        it = self.item()
        a = self.invoice([{"item_id": it, "qty": 1000}], key="inv-key-1")
        b = self.invoice([{"item_id": it, "qty": 1000}], key="inv-key-1")
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM invoice").fetchone()["c"], 1)
        # stock must be decremented once only
        stock = self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (it,)).fetchone()[0]
        self.assertEqual(stock, 9000)

    def test_draft_invoice_has_no_journal_or_stock_effect(self):
        it = self.item(price=10000, cost=6000, stock=2000)
        draft = acc.save_invoice_draft(
            self.conn, self.t, self.cust, "2026-10-24", "27",
            [{"item_id": it, "qty": 1000}])
        self.assertEqual(draft["status"], "draft")
        self.assertTrue(draft["invoice_no"].startswith("DRAFT-"))
        self.assertIsNone(draft["journal_entry_id"])
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM journal_entry").fetchone()["c"], 0)
        self.assertEqual(
            self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (it,)).fetchone()[0],
            2000)
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, draft["id"]), 0)

    def test_post_draft_assigns_invoice_number_and_posts(self):
        it = self.item(price=10000, cost=6000, stock=2000)
        draft = acc.save_invoice_draft(
            self.conn, self.t, self.cust, "2026-10-24", "27",
            [{"item_id": it, "qty": 1000}])
        posted = acc.post_draft_invoice(self.conn, self.t, draft["id"])
        self.assertEqual(posted["status"], "posted")
        self.assertEqual(posted["invoice_no"], "INV-00001")
        self.assertIsNotNone(posted["journal_entry_id"])
        self.assertEqual(
            self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (it,)).fetchone()[0],
            1000)
        tb = {r["code"]: r for r in acc.trial_balance(
            self.conn, self.t, "2026-10-25")["rows"]}
        self.assertEqual(tb["1100"]["balance"], 11800)
        self.assertEqual(tb["5000"]["balance"], 6000)
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, draft["id"]), 11800)
        # A later posted invoice continues the INV sequence after the draft was posted.
        second = self.invoice([{"item_id": it, "qty": 1000}])
        self.assertEqual(second["invoice_no"], "INV-00002")

    def test_draft_can_wait_for_stock_but_post_revalidates(self):
        it = self.item(stock=500)
        draft = acc.save_invoice_draft(
            self.conn, self.t, self.cust, "2026-10-24", "27",
            [{"item_id": it, "qty": 1000}])
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.post_draft_invoice(self.conn, self.t, draft["id"])
        self.assertEqual(ctx.exception.code, "INSUFFICIENT_STOCK")
        row = self.conn.execute("SELECT status FROM invoice WHERE id=?", (draft["id"],)).fetchone()
        self.assertEqual(row["status"], "draft")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM journal_entry").fetchone()["c"], 0)
        self.assertEqual(
            self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (it,)).fetchone()[0],
            500)

    def test_void_draft_requires_reason_and_has_no_effect(self):
        it = self.item(price=10000, cost=6000, stock=2000)
        draft = acc.save_invoice_draft(
            self.conn, self.t, self.cust, "2026-10-24", "27",
            [{"item_id": it, "qty": 1000}])
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.void_draft_invoice(self.conn, self.t, draft["id"], "")
        self.assertEqual(ctx.exception.code, "REASON_REQUIRED")
        voided = acc.void_draft_invoice(self.conn, self.t, draft["id"], "Duplicate entry")
        self.assertEqual(voided["status"], "void")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM journal_entry").fetchone()["c"], 0)
        self.assertEqual(
            self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (it,)).fetchone()[0],
            2000)
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, draft["id"]), 0)
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.post_draft_invoice(self.conn, self.t, draft["id"])
        self.assertEqual(ctx.exception.code, "INVOICE_NOT_DRAFT")

    def test_post_draft_is_idempotent(self):
        it = self.item(stock=2000)
        draft = acc.save_invoice_draft(
            self.conn, self.t, self.cust, "2026-10-24", "27",
            [{"item_id": it, "qty": 1000}])
        first = acc.post_draft_invoice(self.conn, self.t, draft["id"])
        second = acc.post_draft_invoice(self.conn, self.t, draft["id"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM invoice").fetchone()["c"], 1)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM journal_entry").fetchone()["c"], 1)
        self.assertEqual(
            self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (it,)).fetchone()[0],
            1000)

    def test_receipt_cannot_allocate_to_draft(self):
        it = self.item(price=10000, cost=6000, stock=2000)
        draft = acc.save_invoice_draft(
            self.conn, self.t, self.cust, "2026-10-24", "27",
            [{"item_id": it, "qty": 1000}])
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.record_payment(
                self.conn, self.t, "receipt", self.cust, "2026-10-25", 11800, "bank",
                [{"doc_type": "invoice", "doc_id": draft["id"], "amount": 11800}])
        self.assertEqual(ctx.exception.code, "INVOICE_NOT_POSTED")
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM payment").fetchone()["c"], 0)

    def test_hindi_auto_narration_for_invoice_and_receipt(self):
        it = self.item(stock=2000)
        token = i18n.set_current_language("hi")
        try:
            inv = self.invoice([{"item_id": it, "qty": 1000}])
            narration = self.conn.execute(
                "SELECT narration FROM journal_entry WHERE id=?",
                (inv["journal_entry_id"],)).fetchone()["narration"]
            self.assertEqual(narration, "Test Customer के लिए चालान")

            pay = acc.record_payment(
                self.conn, self.t, "receipt", self.cust, "2026-10-24", 5000,
                allocations=[{"doc_type": "invoice", "doc_id": inv["id"], "amount": 5000}])
            pay_narration = self.conn.execute(
                "SELECT narration FROM journal_entry WHERE id=?",
                (pay["journal_entry_id"],)).fetchone()["narration"]
            self.assertEqual(pay_narration, "Test Customer से रसीद")
        finally:
            i18n.reset_current_language(token)


class TestReports(Base):
    def test_balance_sheet_equation(self):
        it = self.item(price=10000, cost=6000, stock=5000)
        self.invoice([{"item_id": it, "qty": 2000}])
        bs = acc.balance_sheet(self.conn, self.t, "2026-10-25")
        self.assertTrue(bs["balanced"], f"diff={bs['difference']}")
        self.assertEqual(bs["total_assets"], bs["total_liabilities"] + bs["total_equity"])

    def test_profit_and_loss_matches_ledger(self):
        it = self.item(price=10000, cost=6000, stock=5000)
        self.invoice([{"item_id": it, "qty": 1000}])
        pnl = acc.profit_and_loss(self.conn, self.t, "2026-04-01", "2027-03-31")
        self.assertEqual(pnl["total_income"], 10000)
        self.assertEqual(pnl["total_expense"], 6000)
        self.assertEqual(pnl["net_profit"], 4000)

    def test_general_ledger_running_balance(self):
        a = db.account_id(self.conn, self.t, "1000")
        b = db.account_id(self.conn, self.t, "3000")
        for i in range(2):
            acc.post_journal(self.conn, self.t, "2026-10-2%d" % (i + 1), "cap",
                             [{"account_id": a, "debit": 1000, "credit": 0},
                              {"account_id": b, "debit": 0, "credit": 1000}], "manual")
        gl = acc.general_ledger(self.conn, self.t, a, "2026-10-01", "2026-10-31")
        self.assertEqual(gl["closing"], 2000)
        self.assertEqual([r["balance"] for r in gl["rows"]], [1000, 2000])

    def test_reversal_nets_to_zero(self):
        it = self.item(price=10000, cost=6000, stock=5000)
        inv = self.invoice([{"item_id": it, "qty": 1000}])
        acc.reverse_entry(self.conn, self.t, inv["journal_entry_id"], "customer cancelled")
        tb = acc.trial_balance(self.conn, self.t, "2026-10-25")
        self.assertTrue(tb["balanced"])
        ar = [r for r in tb["rows"] if r["code"] == "1100"][0]
        self.assertEqual(ar["balance"], 0)

    def test_customer_statement_matches_receivable_control(self):
        it = self.item(price=10000, cost=6000, stock=5000)
        self.invoice([{"item_id": it, "qty": 1000}])
        self.invoice([{"item_id": it, "qty": 2000}])
        st = acc.customer_statement(self.conn, self.t, self.cust, "2026-04-01", "2027-03-31")
        tb = {r["code"]: r for r in acc.trial_balance(self.conn, self.t, "2026-10-25")["rows"]}
        self.assertEqual(st["closing"], 35400)
        self.assertEqual(st["closing"], tb["1100"]["balance"])
        balances = acc.customer_balances(self.conn, self.t, "2026-10-25")
        self.assertEqual(sum(b["balance"] for b in balances), tb["1100"]["balance"])

    def test_customer_statement_cross_tenant_blocked(self):
        other = db.create_tenant(self.conn, "Other", "other3", state_code="27")
        foreign = db.new_id()
        self.conn.execute(
            "INSERT INTO customer (id, tenant_id, name, state_code, created_at) VALUES (?,?,?,?,?)",
            (foreign, other, "Foreign", "27", db.now()))
        with self.assertRaises(acc.AccountingError):
            acc.customer_statement(self.conn, self.t, foreign, "2026-01-01", "2026-12-31")

    def test_cross_tenant_ledger_blocked(self):
        other = db.create_tenant(self.conn, "Other", "other2", state_code="27")
        foreign_acct = db.account_id(self.conn, other, "1000")
        with self.assertRaises(acc.AccountingError):
            acc.general_ledger(self.conn, self.t, foreign_acct, "2026-01-01", "2026-12-31")

    def test_report_totals_equal_source_rows(self):
        it = self.item(price=12345, cost=7000, stock=9000)
        self.invoice([{"item_id": it, "qty": 1234}])
        self.invoice([{"item_id": it, "qty": 777}])
        tb = acc.trial_balance(self.conn, self.t, "2026-10-25")
        # independent recalculation straight from journal lines
        src = self.conn.execute(
            "SELECT COALESCE(SUM(debit_paise),0) d, COALESCE(SUM(credit_paise),0) c"
            " FROM journal_line WHERE tenant_id=?", (self.t,)).fetchone()
        self.assertEqual(tb["total_debit"], src["d"])
        self.assertEqual(tb["total_credit"], src["c"])


class TestSecurity(Base):
    def test_password_hash_and_verify(self):
        h = security.hash_password("correct horse battery")
        self.assertTrue(h.startswith("scrypt$"))
        self.assertTrue(security.verify_password("correct horse battery", h))
        self.assertFalse(security.verify_password("wrong password", h))

    def test_weak_password_rejected(self):
        with self.assertRaises(security.AuthError):
            security.hash_password("short")

    def test_login_and_session(self):
        uid = security.create_user(self.conn, "a@b.com", "averylongpassword", "A")
        security.add_membership(self.conn, self.t, uid, "owner")
        user = security.authenticate(self.conn, "a@b.com", "averylongpassword")
        self.assertEqual(user["id"], uid)
        token, csrf = security.create_session(self.conn, uid, self.t)
        s = security.get_session(self.conn, token)
        self.assertIsNotNone(s)
        self.assertTrue(csrf)
        security.revoke_session(self.conn, token)
        self.assertIsNone(security.get_session(self.conn, token))

    def test_bad_login_logged_and_locked(self):
        security.create_user(self.conn, "c@d.com", "averylongpassword", "C")
        for _ in range(5):
            with self.assertRaises(security.AuthError):
                security.authenticate(self.conn, "c@d.com", "nope")
        with self.assertRaises(security.AuthError) as ctx:
            security.authenticate(self.conn, "c@d.com", "averylongpassword")
        self.assertEqual(ctx.exception.code, "LOCKED")

    def test_rbac_denies_readonly_write(self):
        uid = security.create_user(self.conn, "r@b.com", "averylongpassword", "R")
        security.add_membership(self.conn, self.t, uid, "readonly")
        security.require(self.conn, uid, self.t, "report.view")
        with self.assertRaises(security.AuthError) as ctx:
            security.require(self.conn, uid, self.t, "ledger.post")
        self.assertEqual(ctx.exception.code, "FORBIDDEN")

    def test_no_membership_means_no_access(self):
        uid = security.create_user(self.conn, "x@b.com", "averylongpassword", "X")
        with self.assertRaises(security.AuthError) as ctx:
            security.require(self.conn, uid, self.t, "report.view")
        self.assertEqual(ctx.exception.code, "NO_MEMBERSHIP")

    def test_readonly_cannot_manage_accounts(self):
        uid = security.create_user(self.conn, "m@b.com", "averylongpassword", "M")
        security.add_membership(self.conn, self.t, uid, "readonly")
        with self.assertRaises(security.AuthError) as ctx:
            security.require(self.conn, uid, self.t, "account.manage")
        self.assertEqual(ctx.exception.code, "FORBIDDEN")

    def test_create_business_is_empty_and_makes_creator_owner(self):
        uid = security.create_user(self.conn, "fresh@b.com", "averylongpassword", "Fresh")
        result = security.create_business(self.conn, uid, "Fresh Test Co", "27", "")
        tenant = self.conn.execute(
            "SELECT * FROM tenant WHERE id=?", (result["tenant_id"],)).fetchone()
        self.assertEqual(tenant["name"], "Fresh Test Co")
        self.assertEqual(tenant["slug"], "fresh-test-co")
        membership = self.conn.execute(
            "SELECT role FROM membership WHERE tenant_id=? AND user_id=?",
            (result["tenant_id"], uid)).fetchone()
        self.assertEqual(membership["role"], "owner")
        self.assertGreater(self.conn.execute(
            "SELECT COUNT(*) c FROM account WHERE tenant_id=?",
            (result["tenant_id"],)).fetchone()["c"], 0)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) c FROM journal_entry WHERE tenant_id=?",
            (result["tenant_id"],)).fetchone()["c"], 0)
        audit = self.conn.execute(
            "SELECT * FROM audit_log WHERE tenant_id=? AND action='business.created'",
            (result["tenant_id"],)).fetchone()
        self.assertIsNotNone(audit)


class TestAccountManagement(Base):
    def test_create_account_appears_in_balances_and_audit(self):
        cash = db.account_id(self.conn, self.t, "1000")
        account_id = acc.create_account(
            self.conn, self.t, "6100", "Travel Expense", "expense")
        acc.post_journal(self.conn, self.t, "2026-10-25", "Travel", [
            {"account_id": account_id, "debit": 125000, "credit": 0},
            {"account_id": cash, "debit": 0, "credit": 125000},
        ], source_type="manual")
        balances = {a["id"]: a for a in acc.account_balances(self.conn, self.t, "2026-10-25")}
        self.assertEqual(balances[account_id]["balance"], 125000)
        audit_count = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_log WHERE tenant_id=? AND action='account.create'",
            (self.t,)).fetchone()["c"]
        self.assertEqual(audit_count, 1)

    def test_duplicate_account_code_rejected(self):
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.create_account(self.conn, self.t, "1000", "Another Cash", "asset")
        self.assertEqual(ctx.exception.code, "ACCOUNT_CODE_TAKEN")

    def test_invalid_account_type_rejected(self):
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.create_account(self.conn, self.t, "6100", "Weird", "memo")
        self.assertEqual(ctx.exception.code, "BAD_ACCOUNT_TYPE")


class TestAccountProfile(Base):
    def profile(self, **overrides):
        data = {
            "legal_name": "City Hospital Pvt Ltd",
            "contact_person": "Dr Rao",
            "phone": "9876543210",
            "email": "ap@cityhospital.test",
            "website": "https://cityhospital.test",
            "address": "12 Main Road",
            "city": "Pune",
            "state_code": "27",
            "pincode": "411001",
            "country": "India",
            "gstin": "27ABCDE1234F1Z5",
            "pan": "ABCDE1234F",
            "cin": "U85110MH2020PTC123456",
            "organisation_type": "Private Limited",
            "industry": "Hospital / Healthcare",
            "credit_days": 30,
            "credit_limit_paise": 50000000,
            "notes": "Quarterly settlement",
        }
        data.update(overrides)
        return data

    def test_full_profile_and_opening_are_saved_together(self):
        account_id = acc.create_account(
            self.conn, self.t, "1300", "City Hospital", "asset",
            group_code="receivable", profile=self.profile(),
            opening={"amount": 250000, "as_of": "2026-04-01", "side": "debit"})
        account = self.conn.execute(
            "SELECT * FROM account WHERE id=?", (account_id,)).fetchone()
        self.assertEqual(account["group_code"], "receivable")
        profile = acc.account_profile(self.conn, self.t, account_id)
        self.assertEqual(profile["gstin"], "27ABCDE1234F1Z5")
        self.assertEqual(profile["industry"], "Hospital / Healthcare")
        self.assertEqual(profile["party_type"], "customer")
        customer = self.conn.execute(
            "SELECT * FROM customer WHERE account_id=? AND tenant_id=?",
            (account_id, self.t)).fetchone()
        self.assertIsNotNone(customer)
        self.assertEqual(profile["party_id"], customer["id"])
        self.assertEqual(customer["credit_days"], 30)

        balances = {a["code"]: a for a in acc.account_balances(
            self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["1300"]["balance"], 250000)
        self.assertEqual(balances["1300"]["group_label"],
                         "Sundry Debtors / Accounts Receivable")
        self.assertTrue(acc.trial_balance(self.conn, self.t, "2026-10-26")["balanced"])
        statement = acc.customer_statement(
            self.conn, self.t, customer["id"], "2026-04-01", "2026-10-26")
        self.assertEqual(statement["closing"], 250000)
        self.assertEqual(statement["rows"][0]["source_type"], "opening")

    def test_linked_debtor_ledger_gets_invoice_and_receipt(self):
        account_id = acc.create_account(
            self.conn, self.t, "1310", "Linked Customer", "asset",
            group_code="receivable",
            profile=self.profile(legal_name="Linked Customer Pvt Ltd"))
        customer = self.conn.execute(
            "SELECT * FROM customer WHERE account_id=?", (account_id,)).fetchone()
        item_id = self.item(price=10000, cost=6000, stock=10000, sku="LINK1")
        inv = acc.create_invoice(
            self.conn, self.t, customer["id"], "2026-10-24", "27",
            [{"item_id": item_id, "qty": 1000}])
        ar_line = self.conn.execute(
            "SELECT account_id FROM journal_line WHERE entry_id=? AND party_id=?",
            (inv["journal_entry_id"], customer["id"])).fetchone()
        self.assertEqual(ar_line["account_id"], account_id)
        acc.record_payment(
            self.conn, self.t, "receipt", customer["id"], "2026-10-25",
            inv["total_paise"], mode="bank",
            allocations=[{"doc_type": "invoice", "doc_id": inv["id"],
                          "amount": inv["total_paise"]}])
        statement = acc.customer_statement(
            self.conn, self.t, customer["id"], "2026-04-01", "2026-10-26")
        self.assertEqual(statement["closing"], 0)
        balances = {a["code"]: a for a in acc.account_balances(
            self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["1310"]["balance"], 0)

    def test_linked_creditor_ledger_gets_bill_and_payment(self):
        account_id = acc.create_account(
            self.conn, self.t, "2310", "Linked Supplier", "liability",
            group_code="payable",
            profile=self.profile(legal_name="Linked Supplier Pvt Ltd"))
        vendor = self.conn.execute(
            "SELECT * FROM vendor WHERE account_id=?", (account_id,)).fetchone()
        item_id = self.item(price=10000, cost=6000, stock=10000, sku="LINK2")
        bill = acc.create_bill(
            self.conn, self.t, vendor["id"], "2026-10-24", "BILL-1", "27",
            [{"item_id": item_id, "qty": 1000, "unit_price": 6000}])
        ap_line = self.conn.execute(
            "SELECT account_id FROM journal_line WHERE entry_id=? AND party_id=?",
            (bill["journal_entry_id"], vendor["id"])).fetchone()
        self.assertEqual(ap_line["account_id"], account_id)
        acc.record_payment(
            self.conn, self.t, "payment", vendor["id"], "2026-10-25",
            bill["total_paise"], mode="bank",
            allocations=[{"doc_type": "bill", "doc_id": bill["id"],
                          "amount": bill["total_paise"]}])
        balances = {a["code"]: a for a in acc.account_balances(
            self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["2310"]["balance"], 0)

    def test_validation_and_atomic_rollback(self):
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.create_account(self.conn, self.t, "1400", "Wrong", "asset",
                               group_code="sales")
        self.assertEqual(ctx.exception.code, "ACCOUNT_GROUP_TYPE")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.create_account(self.conn, self.t, "1401", "Bad GST", "asset",
                               group_code="receivable",
                               profile=self.profile(gstin="BAD"))
        self.assertEqual(ctx.exception.code, "BAD_PROFILE_GSTIN")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.create_account(self.conn, self.t, "2400", "Bank Loan", "liability",
                               group_code="loans")
        self.assertEqual(ctx.exception.code, "LOAN_LENDER_REQUIRED")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.create_account(self.conn, self.t, "1590", "Bad Bank", "asset",
                               group_code="bank")
        self.assertEqual(ctx.exception.code, "BANK_DETAILS_REQUIRED")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.create_account(
                self.conn, self.t, "1600", "Atomic Test", "asset",
                group_code="receivable", profile=self.profile(),
                opening={"amount": 100, "as_of": "2099-04-01", "side": "debit"})
        self.assertEqual(ctx.exception.code, "BAD_OPENING_DATE")
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM account WHERE tenant_id=? AND code='1600'", (self.t,)).fetchone())
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM customer WHERE tenant_id=? AND name='City Hospital Pvt Ltd'",
            (self.t,)).fetchone())

    def test_update_profile_changes_details_not_posted_amounts(self):
        account_id = acc.create_account(
            self.conn, self.t, "1320", "Update Customer", "asset",
            group_code="receivable", profile=self.profile())
        acc.update_account_profile(
            self.conn, self.t, account_id, "Updated Customer",
            self.profile(legal_name="Updated Customer Pvt Ltd", phone="9999999999"))
        account = self.conn.execute(
            "SELECT * FROM account WHERE id=?", (account_id,)).fetchone()
        self.assertEqual(account["name"], "Updated Customer")
        self.assertEqual(account["group_code"], "receivable")
        self.assertEqual(acc.account_profile(self.conn, self.t, account_id)["phone"],
                         "9999999999")
        customer = self.conn.execute(
            "SELECT * FROM customer WHERE account_id=?", (account_id,)).fetchone()
        self.assertEqual(customer["name"], "Updated Customer Pvt Ltd")

    def test_linking_existing_party_preserves_unentered_details(self):
        self.conn.execute(
            "UPDATE customer SET phone=?, gstin=?, email=?, address=?, state_code=?,"
            " credit_days=?, credit_limit_paise=? WHERE id=?",
            ("9876501111", "27ABCDE1234F1Z5", "old@example.test", "Old Road",
             "29", 30, 500000, self.cust),
        )
        account_id = acc.create_account(
            self.conn, self.t, "1111", "Test Customer", "asset",
            group_code="receivable", profile={})
        customer = self.conn.execute(
            "SELECT * FROM customer WHERE id=?", (self.cust,)).fetchone()
        self.assertEqual(customer["account_id"], account_id)
        self.assertEqual(customer["phone"], "9876501111")
        self.assertEqual(customer["gstin"], "27ABCDE1234F1Z5")
        self.assertEqual(customer["email"], "old@example.test")
        self.assertEqual(customer["address"], "Old Road")
        self.assertEqual(customer["state_code"], "29")
        self.assertEqual(customer["credit_days"], 30)
        self.assertEqual(customer["credit_limit_paise"], 500000)

    def test_update_bank_profile_validates_ifsc_and_account_number(self):
        account_id = acc.create_account(
            self.conn, self.t, "1030", "Edit Bank", "asset", group_code="bank",
            bank_details={"bank_name": "HDFC Bank", "account_number": "12345678",
                          "ifsc": "HDFC0001234"})
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.update_account_profile(
                self.conn, self.t, account_id, "Edit Bank", self.profile(),
                bank_details={"bank_name": "HDFC Bank", "account_number": "12345678",
                              "ifsc": "BADIFSC"})
        self.assertEqual(ctx.exception.code, "BAD_BANK_IFSC")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.update_account_profile(
                self.conn, self.t, account_id, "Edit Bank", self.profile(),
                bank_details={"bank_name": "HDFC Bank", "account_number": "x",
                              "ifsc": "HDFC0001234"})
        self.assertEqual(ctx.exception.code, "BAD_BANK_ACCOUNT")
        row = self.conn.execute(
            "SELECT * FROM bank_account WHERE account_id=?", (account_id,)).fetchone()
        self.assertEqual(row["account_number"], "12345678")
        self.assertEqual(row["ifsc"], "HDFC0001234")

class TestOpeningBalance(Base):
    def test_debit_opening_posts_balanced_and_creates_equity(self):
        travel = acc.create_account(self.conn, self.t, "6100", "Travel Expense", "expense")
        entry_id = acc.set_opening_balance(
            self.conn, self.t, travel, "2026-04-01", 750000, "debit")
        opening = acc.opening_balance_entry(self.conn, self.t, travel)
        self.assertEqual(opening["id"], entry_id)
        self.assertEqual(opening["debit_paise"], 750000)
        self.assertEqual(opening["entry_date"], "2026-04-01")

        equity = self.conn.execute(
            "SELECT id FROM account WHERE tenant_id=? AND name=?",
            (self.t, acc.OPENING_EQUITY_NAME)).fetchone()
        self.assertIsNotNone(equity)
        tb = acc.trial_balance(self.conn, self.t, "2026-10-26")
        self.assertTrue(tb["balanced"])
        balances = {a["code"]: a for a in acc.account_balances(self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["6100"]["balance"], 750000)
        self.assertEqual(balances["3200"]["balance"], -750000)

    def test_credit_opening_for_liability(self):
        loan = acc.create_account(self.conn, self.t, "2300", "Bank Loan", "liability")
        acc.set_opening_balance(self.conn, self.t, loan, "2026-04-01", 2500000, "credit")
        balances = {a["code"]: a for a in acc.account_balances(self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["2300"]["balance"], -2500000)
        self.assertEqual(balances["3200"]["balance"], 2500000)

    def test_duplicate_opening_blocked_and_reversal_allows_replacement(self):
        cash = db.account_id(self.conn, self.t, "1000")
        first_id = acc.set_opening_balance(
            self.conn, self.t, cash, "2026-04-01", 100000, "debit")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.set_opening_balance(self.conn, self.t, cash, "2026-04-01", 200000, "debit")
        self.assertEqual(ctx.exception.code, "OPENING_EXISTS")

        acc.reverse_entry(self.conn, self.t, first_id, "Opening figure corrected")
        self.assertIsNone(acc.opening_balance_entry(self.conn, self.t, cash))
        second_id = acc.set_opening_balance(
            self.conn, self.t, cash, "2026-04-01", 200000, "debit")
        self.assertNotEqual(first_id, second_id)
        statuses = self.conn.execute(
            "SELECT status FROM journal_entry WHERE source_type='opening' ORDER BY entry_no"
        ).fetchall()
        self.assertEqual([r["status"] for r in statuses], ["reversed", "posted"])
        balances = {a["code"]: a for a in acc.account_balances(self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["1000"]["balance"], 200000)

    def test_opening_after_activity_rejected(self):
        rent = db.account_id(self.conn, self.t, "6000")
        cash = db.account_id(self.conn, self.t, "1000")
        acc.post_journal(self.conn, self.t, "2026-06-15", "Rent paid", [
            {"account_id": rent, "debit": 50000, "credit": 0},
            {"account_id": cash, "debit": 0, "credit": 50000},
        ], source_type="manual")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.set_opening_balance(self.conn, self.t, rent, "2026-06-16", 10000, "debit")
        self.assertEqual(ctx.exception.code, "OPENING_AFTER_ACTIVITY")
        # An opening figure dated before the first activity is still valid.
        acc.set_opening_balance(self.conn, self.t, rent, "2026-04-01", 10000, "debit")
        gl = acc.general_ledger(self.conn, self.t, rent, "2026-04-01", "2026-10-26")
        self.assertEqual(gl["rows"][0]["source_type"], "opening")
        self.assertEqual(gl["closing"], 60000)

    def test_opening_date_and_amount_validated(self):
        cash = db.account_id(self.conn, self.t, "1000")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.set_opening_balance(self.conn, self.t, cash, "2026-04-01", 0, "debit")
        self.assertEqual(ctx.exception.code, "BAD_OPENING_AMOUNT")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.set_opening_balance(self.conn, self.t, cash, "2026-04-01", 100, "sideways")
        self.assertEqual(ctx.exception.code, "BAD_OPENING_SIDE")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.set_opening_balance(self.conn, self.t, cash, "2099-04-01", 100, "debit")
        self.assertEqual(ctx.exception.code, "BAD_OPENING_DATE")

    def test_replace_opening_balance_reverses_old_and_posts_new(self):
        cash = db.account_id(self.conn, self.t, "1000")
        first = acc.set_opening_balance(
            self.conn, self.t, cash, "2026-04-01", 100000, "debit")
        result = acc.replace_opening_balance(
            self.conn, self.t, cash, "2026-04-01", 150000, "debit",
            "Opening cash was understated")
        self.assertEqual(result["original_id"], first)
        self.assertNotEqual(result["entry_id"], first)
        self.assertNotEqual(result["reversal_id"], first)
        balances = {a["code"]: a for a in acc.account_balances(self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["1000"]["balance"], 150000)
        self.assertEqual(balances["3200"]["balance"], -150000)
        statuses = self.conn.execute(
            "SELECT status FROM journal_entry WHERE source_type='opening' ORDER BY entry_no"
        ).fetchall()
        self.assertEqual([r["status"] for r in statuses], ["reversed", "posted"])
        audit = self.conn.execute(
            "SELECT 1 FROM audit_log WHERE tenant_id=? AND action='opening_balance.replace'",
            (self.t,)).fetchone()
        self.assertIsNotNone(audit)

    def test_replace_opening_requires_existing_and_reason(self):
        cash = db.account_id(self.conn, self.t, "1000")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.replace_opening_balance(
                self.conn, self.t, cash, "2026-04-01", 100, "debit", "reason")
        self.assertEqual(ctx.exception.code, "OPENING_NOT_FOUND")
        acc.set_opening_balance(self.conn, self.t, cash, "2026-04-01", 100, "debit")
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.replace_opening_balance(
                self.conn, self.t, cash, "2026-04-01", 200, "debit", "")
        self.assertEqual(ctx.exception.code, "REASON_REQUIRED")


class TestDraftsAndApproval(Base):
    def vendor(self, name="Test Vendor"):
        vid = db.new_id()
        self.conn.execute(
            "INSERT INTO vendor (id, tenant_id, name, state_code, created_at)"
            " VALUES (?,?,?,?,?)", (vid, self.t, name, "27", db.now()))
        return vid

    def bill_items(self, item_id, qty=2000, price=6000):
        return [{"item_id": item_id, "qty": qty, "unit_price": price, "discount": 0}]

    def test_bill_draft_lifecycle_has_no_ledger_effect_until_approval(self):
        item_id = self.item(stock=1000)
        vendor_id = self.vendor()
        draft = drafts.save_bill_draft(
            self.conn, self.t, vendor_id, "2026-10-24", "VB-1", "27",
            self.bill_items(item_id))
        self.assertEqual(draft["status"], "draft")
        self.assertTrue(draft["draft_no"].startswith("DRAFT-BILL-"))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM bill").fetchone()["c"], 0)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM journal_entry").fetchone()["c"], 0)
        self.assertEqual(
            self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0],
            1000)

        updated = drafts.update_bill_draft(
            self.conn, self.t, draft["id"], vendor_id, "2026-10-24", "VB-1", "27",
            self.bill_items(item_id, qty=3000, price=7000))
        self.assertEqual(updated["total_paise"], 3000 * 7000 * 118 // 100 // 1000)

        drafts.submit_bill_draft(self.conn, self.t, draft["id"])
        self.assertEqual(
            self.conn.execute("SELECT status FROM bill_draft WHERE id=?",
                              (draft["id"],)).fetchone()["status"], "pending")
        with self.assertRaises(acc.AccountingError) as ctx:
            drafts.update_bill_draft(
                self.conn, self.t, draft["id"], vendor_id, "2026-10-24", "VB-1", "27",
                self.bill_items(item_id))
        self.assertEqual(ctx.exception.code, "DRAFT_NOT_EDITABLE")

        posted = drafts.approve_bill_draft(self.conn, self.t, draft["id"])
        self.assertEqual(posted["status"], "posted")
        self.assertIsNotNone(posted["posted_bill_id"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) c FROM bill").fetchone()["c"], 1)
        self.assertEqual(
            self.conn.execute("SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0],
            4000)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM journal_entry").fetchone()["c"], 1)
        self.assertEqual(drafts.pending_approvals(self.conn, self.t), [])

    def test_rejected_bill_draft_can_be_edited_and_resubmitted(self):
        item_id = self.item(stock=1000)
        vendor_id = self.vendor()
        draft = drafts.save_bill_draft(
            self.conn, self.t, vendor_id, "2026-10-24", "VB-2", "27",
            self.bill_items(item_id))
        drafts.submit_bill_draft(self.conn, self.t, draft["id"])
        rejected = drafts.reject_bill_draft(
            self.conn, self.t, draft["id"], "Wrong vendor bill number")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(rejected["rejection_reason"], "Wrong vendor bill number")
        updated = drafts.update_bill_draft(
            self.conn, self.t, draft["id"], vendor_id, "2026-10-24", "VB-2A", "27",
            self.bill_items(item_id))
        self.assertEqual(updated["status"], "draft")
        self.assertEqual(updated["rejection_reason"], "")

    def test_journal_draft_lifecycle_and_balance_validation(self):
        cash = db.account_id(self.conn, self.t, "1000")
        rent = db.account_id(self.conn, self.t, "6000")
        lines = [{"account_id": rent, "debit": 50000, "credit": 0},
                 {"account_id": cash, "debit": 0, "credit": 50000}]
        draft = drafts.save_journal_draft(
            self.conn, self.t, "2026-10-24", "October rent", lines)
        self.assertTrue(draft["draft_no"].startswith("DRAFT-JV-"))
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM journal_entry").fetchone()["c"], 0)
        with self.assertRaises(acc.AccountingError) as ctx:
            drafts.save_journal_draft(
                self.conn, self.t, "2026-10-24", "Unbalanced", [
                    {"account_id": rent, "debit": 100, "credit": 0},
                    {"account_id": cash, "debit": 0, "credit": 99}])
        self.assertEqual(ctx.exception.code, "UNBALANCED")
        drafts.submit_journal_draft(self.conn, self.t, draft["id"])
        posted = drafts.approve_journal_draft(self.conn, self.t, draft["id"])
        self.assertEqual(posted["status"], "posted")
        self.assertIsNotNone(posted["posted_entry_id"])
        balances = {a["code"]: a for a in acc.account_balances(self.conn, self.t, "2026-10-26")}
        self.assertEqual(balances["6000"]["balance"], 50000)
        self.assertEqual(balances["1000"]["balance"], -50000)

    def test_invoice_approval_queue_and_approve_posts(self):
        item_id = self.item(stock=5000)
        draft = acc.save_invoice_draft(
            self.conn, self.t, self.cust, "2026-10-24", "27",
            [{"item_id": item_id, "qty": 1000}])
        submitted = drafts.submit_invoice_draft(self.conn, self.t, draft["id"])
        self.assertEqual(submitted["approval_status"], "pending")
        queue = drafts.pending_approvals(self.conn, self.t)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["kind"], "invoice")
        posted = drafts.approve_invoice_draft(self.conn, self.t, draft["id"])
        self.assertEqual(posted["status"], "posted")
        self.assertEqual(posted["approval_status"], "approved")
        self.assertEqual(drafts.pending_approvals(self.conn, self.t), [])

    def test_drafts_are_tenant_scoped(self):
        item_id = self.item(stock=1000)
        vendor_id = self.vendor()
        draft = drafts.save_bill_draft(
            self.conn, self.t, vendor_id, "2026-10-24", "VB-3", "27",
            self.bill_items(item_id))
        other = db.create_tenant(self.conn, "Other Co", "other")
        with self.assertRaises(acc.AccountingError) as ctx:
            drafts.submit_bill_draft(self.conn, other, draft["id"])
        self.assertEqual(ctx.exception.code, "DRAFT_NOT_FOUND")
        self.assertEqual(drafts.list_bill_drafts(self.conn, other), [])


class TestPostedCorrections(Base):
    def vendor(self, name="Correction Vendor"):
        vid = db.new_id()
        self.conn.execute(
            "INSERT INTO vendor (id, tenant_id, name, state_code, created_at)"
            " VALUES (?,?,?,?,?)", (vid, self.t, name, "27", db.now()))
        return vid

    def bill(self, vendor_id, item_id, qty=5000, price=4000):
        return acc.create_bill(
            self.conn, self.t, vendor_id, "2026-10-24", "VB-CORR", "27",
            [{"item_id": item_id, "qty": qty, "unit_price": price}])

    def test_void_posted_invoice_restores_stock_and_reverses_journal(self):
        item_id = self.item(stock=10000)
        inv = self.invoice([{"item_id": item_id, "qty": 2000}])
        self.assertEqual(self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0], 8000)
        voided = acc.void_posted_invoice(self.conn, self.t, inv["id"], "Duplicate invoice")
        self.assertEqual(voided["status"], "void")
        self.assertEqual(voided["void_reason"], "Duplicate invoice")
        self.assertEqual(self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0], 10000)
        entry = self.conn.execute(
            "SELECT status FROM journal_entry WHERE id=?", (inv["journal_entry_id"],)).fetchone()
        self.assertEqual(entry["status"], "reversed")
        reversals = self.conn.execute(
            "SELECT COUNT(*) c FROM journal_entry WHERE tenant_id=? AND source_type='reversal'",
            (self.t,)).fetchone()["c"]
        self.assertEqual(reversals, 1)
        self.assertIsNotNone(self.conn.execute(
            "SELECT 1 FROM audit_log WHERE tenant_id=? AND action='invoice.void'",
            (self.t,)).fetchone())

    def test_replace_posted_invoice_links_new_number_and_balances(self):
        item_id = self.item(stock=10000)
        old = self.invoice([{"item_id": item_id, "qty": 2000}])
        new = acc.replace_posted_invoice(
            self.conn, self.t, old["id"], self.cust, "2026-10-24", "27",
            [{"item_id": item_id, "qty": 3000}], "Quantity was entered wrong")
        self.assertEqual(new["status"], "posted")
        self.assertNotEqual(new["invoice_no"], old["invoice_no"])
        self.assertEqual(new["replaces_id"], old["id"])
        self.assertEqual(new["approval_status"], "approved")
        old_row = self.conn.execute(
            "SELECT status, void_reason FROM invoice WHERE id=?", (old["id"],)).fetchone()
        self.assertEqual(old_row["status"], "void")
        self.assertEqual(old_row["void_reason"], "Quantity was entered wrong")
        self.assertEqual(self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0], 7000)
        totals = self.conn.execute(
            "SELECT COALESCE(SUM(debit_paise),0) d, COALESCE(SUM(credit_paise),0) c"
            " FROM journal_line WHERE tenant_id=?", (self.t,)).fetchone()
        self.assertEqual(totals["d"], totals["c"])
        self.assertIsNotNone(self.conn.execute(
            "SELECT 1 FROM audit_log WHERE tenant_id=? AND action='invoice.replace'",
            (self.t,)).fetchone())

    def test_replace_posted_invoice_blocked_by_receipt(self):
        item_id = self.item(stock=10000)
        inv = self.invoice([{"item_id": item_id, "qty": 2000}])
        acc.record_payment(
            self.conn, self.t, "receipt", self.cust, "2026-10-24", 5000,
            allocations=[{"doc_type": "invoice", "doc_id": inv["id"], "amount": 5000}])
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.replace_posted_invoice(
                self.conn, self.t, inv["id"], self.cust, "2026-10-24", "27",
                [{"item_id": item_id, "qty": 2000}], "No longer needed")
        self.assertEqual(ctx.exception.code, "INVOICE_HAS_PAYMENTS")

    def test_void_posted_bill_removes_stock_and_reverses(self):
        item_id = self.item(stock=10000)
        vendor_id = self.vendor()
        bill = self.bill(vendor_id, item_id, qty=5000, price=4000)
        self.assertEqual(self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0], 15000)
        voided = acc.void_posted_bill(self.conn, self.t, bill["id"], "Wrong vendor bill")
        self.assertEqual(voided["status"], "void")
        self.assertEqual(self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0], 10000)
        self.assertEqual(self.conn.execute(
            "SELECT status FROM journal_entry WHERE id=?", (bill["journal_entry_id"],)
        ).fetchone()["status"], "reversed")

    def test_replace_posted_bill_updates_stock_and_links_old(self):
        item_id = self.item(stock=10000)
        vendor_id = self.vendor()
        old = self.bill(vendor_id, item_id, qty=5000, price=4000)
        new = acc.replace_posted_bill(
            self.conn, self.t, old["id"], vendor_id, "2026-10-24", "VB-CORR-2", "27",
            [{"item_id": item_id, "qty": 7000, "unit_price": 4500}],
            "Supplier bill quantity corrected")
        self.assertEqual(new["status"], "posted")
        self.assertEqual(new["replaces_id"], old["id"])
        self.assertEqual(new["vendor_bill_no"], "VB-CORR-2")
        self.assertEqual(self.conn.execute(
            "SELECT status FROM bill WHERE id=?", (old["id"],)).fetchone()["status"], "void")
        self.assertEqual(self.conn.execute(
            "SELECT stock_milli FROM item WHERE id=?", (item_id,)).fetchone()[0], 17000)
        totals = self.conn.execute(
            "SELECT COALESCE(SUM(debit_paise),0) d, COALESCE(SUM(credit_paise),0) c"
            " FROM journal_line WHERE tenant_id=?", (self.t,)).fetchone()
        self.assertEqual(totals["d"], totals["c"])

    def test_replace_posted_bill_blocked_when_stock_consumed(self):
        item_id = self.item(stock=10000)
        vendor_id = self.vendor()
        bill = self.bill(vendor_id, item_id, qty=5000, price=4000)
        self.conn.execute("UPDATE item SET stock_milli=1000 WHERE id=?", (item_id,))
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.replace_posted_bill(
                self.conn, self.t, bill["id"], vendor_id, "2026-10-24", "VB-X", "27",
                [{"item_id": item_id, "qty": 5000, "unit_price": 4000}], "Correct it")
        self.assertEqual(ctx.exception.code, "BILL_STOCK_CONSUMED")

    def test_void_posted_payment_restores_outstanding(self):
        item_id = self.item(stock=10000)
        inv = self.invoice([{"item_id": item_id, "qty": 2000}])
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, inv["id"]), 23600)
        pay = acc.record_payment(
            self.conn, self.t, "receipt", self.cust, "2026-10-24", 10000,
            allocations=[{"doc_type": "invoice", "doc_id": inv["id"], "amount": 10000}])
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, inv["id"]), 13600)
        voided = acc.void_posted_payment(self.conn, self.t, pay["id"], "Wrong bank account")
        self.assertEqual(voided["status"], "void")
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, inv["id"]), 23600)
        self.assertEqual(self.conn.execute(
            "SELECT status FROM journal_entry WHERE id=?", (pay["journal_entry_id"],)
        ).fetchone()["status"], "reversed")

    def test_replace_posted_payment_keeps_allocations_and_links_old(self):
        item_id = self.item(stock=10000)
        inv = self.invoice([{"item_id": item_id, "qty": 2000}])
        old = acc.record_payment(
            self.conn, self.t, "receipt", self.cust, "2026-10-24", 10000,
            allocations=[{"doc_type": "invoice", "doc_id": inv["id"], "amount": 10000}])
        new = acc.replace_posted_payment(
            self.conn, self.t, old["id"], "2026-10-24", 12000, "upi",
            reference="UPI-CORR", reason="Amount entered short")
        self.assertEqual(new["status"], "posted")
        self.assertEqual(new["replaces_id"], old["id"])
        self.assertEqual(new["amount_paise"], 12000)
        self.assertEqual(new["mode"], "upi")
        self.assertEqual(self.conn.execute(
            "SELECT status FROM payment WHERE id=?", (old["id"],)).fetchone()["status"], "void")
        alloc = self.conn.execute(
            "SELECT COALESCE(SUM(amount_paise),0) a FROM payment_allocation"
            " WHERE payment_id=?", (new["id"],)).fetchone()["a"]
        self.assertEqual(alloc, 10000)
        self.assertEqual(acc.invoice_outstanding(self.conn, self.t, inv["id"]), 13600)

    def test_replace_posted_payment_rejects_amount_below_allocations(self):
        item_id = self.item(stock=10000)
        inv = self.invoice([{"item_id": item_id, "qty": 2000}])
        old = acc.record_payment(
            self.conn, self.t, "receipt", self.cust, "2026-10-24", 10000,
            allocations=[{"doc_type": "invoice", "doc_id": inv["id"], "amount": 10000}])
        with self.assertRaises(acc.AccountingError) as ctx:
            acc.replace_posted_payment(
                self.conn, self.t, old["id"], "2026-10-24", 5000, "bank",
                reason="Trying to reduce below allocation")
        self.assertEqual(ctx.exception.code, "OVER_ALLOCATION")
        self.assertEqual(self.conn.execute(
            "SELECT status FROM payment WHERE id=?", (old["id"],)).fetchone()["status"], "posted")


if __name__ == "__main__":
    unittest.main(verbosity=2)
