"""Deterministic tests for the accounting core. stdlib unittest, no network."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acc
from app import db, money, security


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

    def test_three_decimals_rejected(self):
        with self.assertRaises(money.MoneyError):
            money.parse_amount("10.005")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
