"""Team invites, role administration and shareable statement links."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import accounting as acct
from app import db, security, sharing


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()


class TeamBase(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.t = db.create_tenant(self.conn, "Demo Co", "demo", state_code="27")
        self.owner = security.create_user(self.conn, "owner@test.in", "averylongpassword", "Owner")
        security.add_membership(self.conn, self.t, self.owner, "owner")
        self.admin = security.create_user(self.conn, "admin@test.in", "averylongpassword", "Admin")
        security.add_membership(self.conn, self.t, self.admin, "admin")
        self.cust = db.new_id()
        self.conn.execute(
            "INSERT INTO customer (id, tenant_id, name, state_code, created_at) VALUES (?,?,?,?,?)",
            (self.cust, self.t, "Test Customer", "27", db.now()),
        )

    def tearDown(self):
        self.conn.close()

    def invite(self, email="new@test.in", role="accountant", name="New Person"):
        return security.invite_member(self.conn, self.t, email, name, role, self.owner)


class TestTeam(TeamBase):
    def test_new_user_invite_accept_and_login(self):
        link = self.invite()
        preview = security.invite_by_token(self.conn, link["token"])
        self.assertFalse(preview["existing_user"])
        self.assertEqual(preview["tenant_name"], "Demo Co")
        result = security.accept_invite(self.conn, link["token"], "New Person",
                                        "anotherlongpassword")
        self.assertTrue(result["created_user"])
        self.assertEqual(result["role"], "accountant")
        user = security.authenticate(self.conn, "new@test.in", "anotherlongpassword")
        self.assertEqual(user["id"], result["user_id"])
        members = security.list_members(self.conn, self.t)
        self.assertEqual(len(members), 3)

    def test_duplicate_invite_revokes_previous_link(self):
        first = self.invite()
        second = self.invite(role="manager")
        with self.assertRaises(security.AuthError) as ctx:
            security.invite_by_token(self.conn, first["token"])
        self.assertEqual(ctx.exception.code, "INVITE_REVOKED")
        accepted = security.accept_invite(self.conn, second["token"], "New Person",
                                          "anotherlongpassword")
        self.assertEqual(accepted["role"], "manager")

    def test_existing_user_requires_current_password(self):
        t2 = db.create_tenant(self.conn, "Second Co", "second", state_code="27")
        link = security.invite_member(self.conn, t2, "admin@test.in", "Admin", "manager",
                                      self.owner)
        preview = security.invite_by_token(self.conn, link["token"])
        self.assertTrue(preview["existing_user"])
        with self.assertRaises(security.AuthError) as ctx:
            security.accept_invite(self.conn, link["token"], "Admin", "wrong-password")
        self.assertEqual(ctx.exception.code, "BAD_CREDENTIALS")
        result = security.accept_invite(self.conn, link["token"], "Admin", "averylongpassword")
        self.assertFalse(result["created_user"])
        self.assertEqual(result["tenant_id"], t2)
        rows = security.tenants_for(self.conn, self.admin)
        self.assertEqual({r["id"] for r in rows}, {self.t, t2})

    def test_owner_and_self_role_guards(self):
        with self.assertRaises(security.AuthError) as ctx:
            security.change_member_role(self.conn, self.t, self.owner, self.owner, "admin")
        self.assertEqual(ctx.exception.code, "SELF_ROLE")
        with self.assertRaises(security.AuthError) as ctx:
            security.change_member_role(self.conn, self.t, self.admin, self.owner, "admin")
        self.assertEqual(ctx.exception.code, "OWNER_LOCKED")
        uid = security.create_user(self.conn, "promote@test.in", "averylongpassword", "Promote")
        security.add_membership(self.conn, self.t, uid, "readonly")
        with self.assertRaises(security.AuthError) as ctx:
            security.change_member_role(self.conn, self.t, self.admin, uid, "owner")
        self.assertEqual(ctx.exception.code, "BAD_ROLE")

    def test_admin_can_change_role_and_suspend_revokes_sessions(self):
        uid = security.create_user(self.conn, "staff@test.in", "averylongpassword", "Staff")
        security.add_membership(self.conn, self.t, uid, "readonly")
        security.change_member_role(self.conn, self.t, self.admin, uid, "manager")
        member = [m for m in security.list_members(self.conn, self.t) if m["user_id"] == uid][0]
        self.assertEqual(member["role"], "manager")
        token, _csrf = security.create_session(self.conn, uid, self.t, "127.0.0.1")
        self.assertIsNotNone(security.get_session(self.conn, token))
        security.set_member_status(self.conn, self.t, self.admin, uid, "suspended")
        self.assertIsNone(security.get_session(self.conn, token))
        security.set_member_status(self.conn, self.t, self.admin, uid, "active")
        member = [m for m in security.list_members(self.conn, self.t) if m["user_id"] == uid][0]
        self.assertEqual(member["member_status"], "active")

    def test_expired_and_revoked_invites(self):
        link = self.invite()
        self.conn.execute("UPDATE member_invite SET expires_at=? WHERE id=?",
                          (_past(), link["id"]))
        with self.assertRaises(security.AuthError) as ctx:
            security.invite_by_token(self.conn, link["token"])
        self.assertEqual(ctx.exception.code, "INVITE_EXPIRED")
        link2 = self.invite(email="second@test.in")
        security.revoke_invite(self.conn, self.t, link2["id"], self.owner)
        with self.assertRaises(security.AuthError) as ctx:
            security.invite_by_token(self.conn, link2["token"])
        self.assertEqual(ctx.exception.code, "INVITE_REVOKED")

    def test_active_member_cannot_be_invited_again(self):
        with self.assertRaises(security.AuthError) as ctx:
            security.invite_member(self.conn, self.t, "admin@test.in", "Admin", "manager",
                                   self.owner)
        self.assertEqual(ctx.exception.code, "ALREADY_MEMBER")


class TestSharing(TeamBase):
    def test_share_resolves_and_counts_views(self):
        share = sharing.create_statement_share(self.conn, self.t, "customer", self.cust,
                                               "2026-04-01", "2026-10-31", self.owner, 7)
        self.assertNotIn(share["token"], str(
            self.conn.execute("SELECT token_hash FROM statement_share WHERE id=?",
                              (share["id"],)).fetchone()))
        resolved = sharing.resolve_statement_share(self.conn, share["token"])
        self.assertEqual(resolved["tenant"]["id"], self.t)
        self.assertEqual(resolved["statement"]["customer"]["id"], self.cust)
        self.assertEqual(resolved["statement"]["closing"], 0)
        resolved2 = sharing.resolve_statement_share(self.conn, share["token"])
        self.assertEqual(resolved2["share"]["view_count"], 1)
        rows = sharing.list_statement_shares(self.conn, self.t, "customer", self.cust)
        self.assertEqual(rows[0]["link_status"], "active")

    def test_revoke_and_expiry(self):
        share = sharing.create_statement_share(self.conn, self.t, "customer", self.cust,
                                               "2026-04-01", "2026-10-31", self.owner, 7)
        sharing.revoke_statement_share(self.conn, self.t, share["id"], self.owner)
        with self.assertRaises(sharing.ShareError) as ctx:
            sharing.resolve_statement_share(self.conn, share["token"])
        self.assertEqual(ctx.exception.code, "SHARE_REVOKED")
        share2 = sharing.create_statement_share(self.conn, self.t, "customer", self.cust,
                                                "2026-04-01", "2026-10-31", self.owner, 7)
        self.conn.execute("UPDATE statement_share SET expires_at=? WHERE id=?",
                          (_past(), share2["id"]))
        with self.assertRaises(sharing.ShareError) as ctx:
            sharing.resolve_statement_share(self.conn, share2["token"])
        self.assertEqual(ctx.exception.code, "SHARE_EXPIRED")

    def test_bad_party_and_dates(self):
        with self.assertRaises(sharing.ShareError) as ctx:
            sharing.create_statement_share(self.conn, self.t, "customer", "missing",
                                           "2026-04-01", "2026-10-31", self.owner, 7)
        self.assertEqual(ctx.exception.code, "PARTY_NOT_FOUND")
        with self.assertRaises(sharing.ShareError) as ctx:
            sharing.create_statement_share(self.conn, self.t, "customer", self.cust,
                                           "2026-10-31", "2026-04-01", self.owner, 7)
        self.assertEqual(ctx.exception.code, "BAD_DATES")
        with self.assertRaises(sharing.ShareError) as ctx:
            sharing.create_statement_share(self.conn, self.t, "bank", self.cust,
                                           "2026-04-01", "2026-10-31", self.owner, 7)
        self.assertEqual(ctx.exception.code, "BAD_PARTY_TYPE")

    def test_statement_totals_match_accounting_report(self):
        item = db.new_id()
        self.conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise,"
            " tax_rate_bp, stock_milli, track_stock, revenue_code) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (item, self.t, "SKU1", "Item", 10000, 6000, 1800, 10000, 1, "4000"))
        acct.create_invoice(self.conn, self.t, self.cust, "2026-10-24", "27",
                            [{"item_id": item, "qty": "2", "price": "", "discount": "0"}])
        share = sharing.create_statement_share(self.conn, self.t, "customer", self.cust,
                                               "2026-04-01", "2026-10-31", self.owner, 7)
        resolved = sharing.resolve_statement_share(self.conn, share["token"])
        direct = acct.customer_statement(self.conn, self.t, self.cust, "2026-04-01", "2026-10-31")
        self.assertEqual(resolved["statement"]["closing"], direct["closing"])
        self.assertGreater(resolved["statement"]["closing"], 0)


if __name__ == "__main__":
    unittest.main()
