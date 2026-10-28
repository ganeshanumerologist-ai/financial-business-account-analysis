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

    def test_readonly_cannot_manage_accounts(self):
        uid = security.create_user(self.conn, "m@b.com", "averylongpassword", "M")
        security.add_membership(self.conn, self.t, uid, "readonly")
        with self.assertRaises(security.AuthError) as ctx:
            security.require(self.conn, uid, self.t, "account.manage")
        self.assertEqual(ctx.exception.code, "FORBIDDEN")


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
