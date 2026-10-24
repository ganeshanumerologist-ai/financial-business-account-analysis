"""ARTHIVIO web app — stdlib HTTP server, server-rendered, no external deps."""
from __future__ import annotations

import csv
import html
import io
import os
import re
import secrets
import sqlite3
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import accounting as acct
from . import backup as backup_mod
from . import db, money, security

DB_PATH = os.environ.get("ARTHIVIO_DB", os.path.join("data", "arthivio.db"))
BACKUP_DIR = os.environ.get("ARTHIVIO_BACKUP_DIR", "backups")
APP_NAME = "ARTHIVIO"

CSS = """
:root{
  --ivory:#F7F5EF; --surface:#FFFFFF; --ink:#183E35; --ink-soft:#3C534B;
  --emerald:#176B4D; --emerald-700:#11543C; --sage:#DCE8D9; --sage-soft:#EEF4EC;
  --gold:#C6A15B; --line:#E5E1D6; --muted:#68766E; --danger:#A6402F; --danger-bg:#F7E7E3;
  --radius:14px; --shadow:0 1px 2px rgba(24,62,53,.05),0 8px 24px rgba(24,62,53,.05);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--ivory); color:var(--ink);
  font-family:"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
  font-size:16px; line-height:1.5; -webkit-font-smoothing:antialiased;
}
a{color:var(--emerald);text-decoration:none}
a:hover{text-decoration:underline}
h1,h2,h3{margin:0;font-weight:650;letter-spacing:-.015em;color:var(--ink)}
h1{font-size:26px} h2{font-size:19px} h3{font-size:15px}
.shell{display:grid;grid-template-columns:248px 1fr;min-height:100vh}
.side{background:linear-gradient(180deg,#124A36 0%,#0E3B2B 100%);color:#EAF2EC;padding:20px 16px 28px;position:sticky;top:0;height:100vh;overflow-y:auto}
.brand{display:flex;align-items:center;gap:10px;margin:4px 6px 26px}
.brand svg{flex:0 0 auto}
.brand .name{font-size:19px;font-weight:700;letter-spacing:.06em}
.brand .tag{display:block;font-size:10.5px;color:#A9C4B5;letter-spacing:.02em;margin-top:2px}
.nav{display:flex;flex-direction:column;gap:2px}
.nav .grp{font-size:10.5px;letter-spacing:.12em;color:#8FB0A1;margin:16px 10px 6px;text-transform:uppercase}
.nav a{display:flex;align-items:center;gap:10px;color:#DCEAE1;padding:9px 12px;border-radius:9px;font-size:14.5px}
.nav a:hover{background:rgba(255,255,255,.08);text-decoration:none}
.nav a.on{background:#F7F5EF;color:#123F2E;font-weight:600;box-shadow:0 1px 0 rgba(0,0,0,.06)}
.nav a .ico{width:16px;height:16px;opacity:.9}
.main{padding:22px 28px 56px;min-width:0}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:22px;flex-wrap:wrap}
.top .who{font-size:13px;color:var(--muted)}
.top .who b{color:var(--ink)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
.pad{padding:18px 20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin-bottom:18px}
.kpi{padding:16px 18px}
.kpi .lbl{font-size:12.5px;color:var(--muted);letter-spacing:.02em;text-transform:uppercase}
.kpi .val{font-size:26px;font-weight:680;margin-top:6px;font-variant-numeric:tabular-nums}
.kpi .sub{font-size:12.5px;color:var(--muted);margin-top:4px}
.grid2{display:grid;grid-template-columns:1.45fr 1fr;gap:16px}
.grid2>*{min-width:0}
table{width:100%;border-collapse:collapse;font-size:14.5px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line)}
th{font-size:11.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:600;background:#FBFAF6}
tbody tr:hover{background:#FCFBF7}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tfoot td{font-weight:650;background:#FBFAF6}
.btn{display:inline-flex;align-items:center;gap:8px;background:var(--emerald);color:#fff;border:0;border-radius:10px;
  padding:10px 16px;font-size:14.5px;font-weight:600;cursor:pointer}
.btn:hover{background:var(--emerald-700);text-decoration:none;color:#fff}
.btn.ghost{background:#fff;color:var(--emerald);border:1px solid #C9D8CE}
.btn.ghost:hover{background:var(--sage-soft);color:var(--emerald-700)}
.btn.small{padding:7px 12px;font-size:13.5px}
input,select{font:inherit;color:var(--ink);background:#fff;border:1px solid #D8D3C6;border-radius:9px;padding:9px 11px;width:100%}
input:focus,select:focus{outline:2px solid #BBD6C6;outline-offset:0;border-color:var(--emerald)}
label{display:block;font-size:12.5px;font-weight:600;color:var(--ink-soft);margin-bottom:5px;letter-spacing:.01em}
.field{margin-bottom:13px}
.row{display:grid;gap:12px}
.row.c2{grid-template-columns:1fr 1fr}
.row.c3{grid-template-columns:repeat(3,1fr)}
.row.c4{grid-template-columns:repeat(4,1fr)}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:4px 9px;border-radius:999px}
.badge.ok{background:var(--sage);color:#14503A}
.badge.bad{background:var(--danger-bg);color:var(--danger)}
.badge.neutral{background:#F0EDE4;color:#5C6A62}
.muted{color:var(--muted)}
.small{font-size:13px}
.err{background:var(--danger-bg);color:var(--danger);border:1px solid #E7C4BC;padding:11px 14px;border-radius:10px;margin-bottom:14px;font-size:14px}
.sect{margin-bottom:26px}
.sect-head{display:flex;align-items:end;justify-content:space-between;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.chart{display:flex;align-items:flex-end;gap:10px;height:150px;padding:10px 2px 0}
.chart .bar{flex:1;background:linear-gradient(180deg,#2E8D69,#176B4D);border-radius:6px 6px 0 0;min-height:3px;position:relative}
.chart .bar span{position:absolute;bottom:-22px;left:0;right:0;text-align:center;font-size:11px;color:var(--muted)}
.chart .bar b{position:absolute;top:-20px;left:0;right:0;text-align:center;font-size:11px;color:var(--ink-soft);font-weight:600}
.login-wrap{min-height:100vh;display:grid;place-items:center;padding:24px}
.login{width:100%;max-width:410px}
.brandline{display:flex;align-items:center;gap:11px;margin-bottom:18px}
.footer-note{color:var(--muted);font-size:12px;margin-top:26px}
.empty{padding:26px;text-align:center;color:var(--muted);font-size:14px}
@media (max-width:980px){
  .shell{grid-template-columns:1fr}
  .side{position:static;height:auto;padding:14px}
  .nav{flex-direction:row;flex-wrap:wrap}
  .nav .grp{display:none}
  .main{padding:18px}
  .grid2{grid-template-columns:1fr}
}
@media print{.side,.top .who{display:none}.shell{grid-template-columns:1fr}}
"""

LOGO = """<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
<path d="M4 26 L13 6 L20 20 L24 13 L28 26 Z" fill="#C6A15B" opacity=".95"/>
<path d="M4 26 L13 6 L20 20 Z" fill="#EAF2EC" opacity=".9"/>
<circle cx="24" cy="9" r="3.2" fill="#C6A15B"/>
</svg>"""

ICONS = {
    "dash": '<path d="M3 12h7V3H3v9zm0 9h7v-6H3v6zm9 0h9V12h-9v9zm0-18v6h9V3h-9z"/>',
    "inv": '<path d="M6 2h9l4 4v16H6V2zm8 1v4h4"/>',
    "led": '<path d="M4 4h16v16H4zM8 8h8M8 12h8M8 16h5"/>',
    "rep": '<path d="M4 20V9m5 11V4m5 16v-7m5 7V7"/>',
    "cust": '<path d="M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 4-6 8-6s8 2 8 6"/>',
    "item": '<path d="M4 7l8-4 8 4v10l-8 4-8-4V7zm8 4v10"/>',
    "audit": '<path d="M5 3h14v18H5zM9 8h6M9 12h6M9 16h3"/>',
}

NAV = [
    ("Overview", [("", "dash", "Dashboard")]),
    ("Sales", [
        ("invoices", "inv", "Invoices"),
        ("receipts", "inv", "Receipts"),
        ("credit-notes", "inv", "Credit Notes"),
    ]),
    ("Purchases", [
        ("bills", "inv", "Bills"),
        ("vendors", "cust", "Vendors"),
    ]),
    ("Books", [
        ("daybook", "led", "Day Book"),
        ("journal", "led", "Journal"),
        ("ledger", "led", "Ledger"),
    ]),
    ("Reports", [
        ("reports/trial-balance", "rep", "Trial Balance"),
        ("reports/pnl", "rep", "Profit &amp; Loss"),
        ("reports/balance-sheet", "rep", "Balance Sheet"),
        ("reports/ar-ageing", "rep", "Receivables Ageing"),
        ("reports/ap-ageing", "rep", "Payables Ageing"),
        ("reports/gst", "rep", "GST Summary"),
    ]),
    ("Masters", [
        ("customers", "cust", "Customers"),
        ("items", "item", "Items"),
        ("backup", "audit", "Backups"),
        ("audit", "audit", "Audit Log"),
    ]),
]


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def first(form: dict, key: str, default: str = "") -> str:
    vals = form.get(key)
    if not vals:
        return default
    return vals[0] if isinstance(vals, list) else str(vals)


def icon(key: str) -> str:
    d = ICONS.get(key, ICONS["dash"])
    return f'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{d}</svg>'


def layout(title: str, body: str, active: str = "", user=None, tenant=None) -> str:
    nav = []
    for group, links in NAV:
        nav.append(f'<div class="grp">{group}</div>')
        for path, ico, label in links:
            cls = " on" if path == active else ""
            nav.append(f'<a class="{cls.strip()}" href="/{path}">{icon(ico)}<span>{label}</span></a>')
    who = ""
    if user:
        who = (f'<div class="who"><b>{esc(user["full_name"])}</b> &nbsp;·&nbsp; {esc(tenant["name"]) if tenant else ""}'
               f'<form method="post" action="/logout" style="display:inline;margin-left:12px">'
               f'<button class="btn ghost small" type="submit">Sign out</button></form></div>')
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · {APP_NAME}</title><style>{CSS}</style></head>
<body><div class="shell">
<aside class="side">
  <div class="brand">{LOGO}<div><span class="name">ARTHIVIO</span><span class="tag">Smarter Finance</span></div></div>
  <nav class="nav">{''.join(nav)}</nav>
</aside>
<main class="main">
  <div class="top"><h1>{esc(title)}</h1>{who}</div>
  {body}
  <p class="footer-note">{APP_NAME} · amounts in INR · all figures derived from posted journal entries.</p>
</main></div></body></html>"""


def login_page(error: str = "") -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in · {APP_NAME}</title>
<style>{CSS}</style></head><body><div class="login-wrap"><div class="login">
<div class="brandline">{LOGO}<div><div style="font-weight:700;letter-spacing:.06em">ARTHIVIO</div>
<div class="small muted">Smarter Finance. Stronger Business.</div></div></div>
<div class="card pad">
<h2 style="margin-bottom:16px">Sign in</h2>{err}
<form method="post" action="/login">
<div class="field"><label for="email">Email</label><input id="email" name="email" type="email" required autocomplete="username"></div>
<div class="field"><label for="password">Password</label><input id="password" name="password" type="password" required autocomplete="current-password"></div>
<button class="btn" type="submit" style="width:100%;justify-content:center">Sign in</button>
</form></div>
<p class="footer-note">Demo accounts are seeded by <code>scripts/seed_demo.py</code>. No real customer data.</p>
</div></div></body></html>"""


def kpi(label: str, value: str, sub: str = "") -> str:
    return f'<div class="card kpi"><div class="lbl">{esc(label)}</div><div class="val">{esc(value)}</div><div class="sub">{esc(sub)}</div></div>'


class Handler(BaseHTTPRequestHandler):
    server_version = "ARTHIVIO/0.1"

    # ---------------- plumbing ----------------
    def log_message(self, fmt, *args):  # quieter console
        print(f"{self.address_string()} {fmt % args}")

    def _conn(self) -> sqlite3.Connection:
        return db.connect(DB_PATH)

    def _cookies(self) -> dict:
        raw = self.headers.get("Cookie", "")
        c = SimpleCookie()
        try:
            c.load(raw)
        except Exception:
            return {}
        return {k: v.value for k, v in c.items()}

    def _session(self, conn):
        return security.get_session(conn, self._cookies().get("sid"))

    def _send(self, body: str, status: int = 200, headers: dict | None = None):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, to: str, headers: dict | None = None):
        h = {"Location": to}
        h.update(headers or {})
        self.send_response(303)
        for k, v in h.items():
            self.send_header(k, v)
        self.end_headers()

    def _form(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return urllib.parse.parse_qs(raw, keep_blank_values=True)

    # ---------------- routing ----------------
    def do_GET(self):
        conn = self._conn()
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            q = urllib.parse.parse_qs(parsed.query)

            if path == "/login":
                return self._send(login_page())
            if path == "/health":
                return self._send("ok")

            sess = self._session(conn)
            if not sess:
                return self._redirect("/login")
            user = conn.execute("SELECT * FROM user WHERE id=?", (sess["user_id"],)).fetchone()
            tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (sess["tenant_id"],)).fetchone()
            if not user or not tenant:
                return self._redirect("/logout")

            if path == "/":
                return self._send(self.page_dashboard(conn, user, tenant))
            if path == "/invoices":
                return self._send(self.page_invoices(conn, user, tenant, sess))
            if path == "/invoices/new":
                return self._send(self.page_invoice_new(conn, user, tenant, sess))
            if re.fullmatch(r"/invoices/[0-9a-f]{32}", path):
                return self._send(self.page_invoice_detail(conn, user, tenant, sess,
                                                           path.rsplit("/", 1)[1]))
            if path == "/ledger":
                return self._send(self.page_ledger(conn, user, tenant, q))
            if path == "/reports/trial-balance":
                return self._send(self.page_tb(conn, user, tenant, q))
            if path == "/reports/pnl":
                return self._send(self.page_pnl(conn, user, tenant, q))
            if path == "/reports/balance-sheet":
                return self._send(self.page_bs(conn, user, tenant, q))
            if path == "/customers":
                return self._send(self.page_customers(conn, user, tenant, sess))
            if re.fullmatch(r"/customers/[0-9a-f]{32}", path):
                return self._send(self.page_customer_statement(conn, user, tenant,
                                                               path.rsplit("/", 1)[1], q))
            if path == "/receipts":
                return self._send(self.page_receipts(conn, user, tenant, sess))
            if path == "/credit-notes":
                return self._send(self.page_credit_notes(conn, user, tenant))
            if path == "/bills":
                return self._send(self.page_bills(conn, user, tenant, sess))
            if path == "/bills/new":
                return self._send(self.page_bill_new(conn, user, tenant, sess))
            if re.fullmatch(r"/bills/[0-9a-f]{32}", path):
                return self._send(self.page_bill_detail(conn, user, tenant, sess,
                                                        path.rsplit("/", 1)[1]))
            if path == "/vendors":
                return self._send(self.page_vendors(conn, user, tenant, sess))
            if re.fullmatch(r"/vendors/[0-9a-f]{32}", path):
                return self._send(self.page_vendor_statement(conn, user, tenant,
                                                             path.rsplit("/", 1)[1], q))
            if path == "/daybook":
                return self._send(self.page_daybook(conn, user, tenant, q))
            if path == "/journal":
                return self._send(self.page_journal(conn, user, tenant, sess))
            if path == "/reports/ar-ageing":
                return self._send(self.page_ageing(conn, user, tenant, q, "ar"))
            if path == "/reports/ap-ageing":
                return self._send(self.page_ageing(conn, user, tenant, q, "ap"))
            if path == "/reports/gst":
                return self._send(self.page_gst(conn, user, tenant, q))
            if path.startswith("/export/"):
                return self.export_csv(conn, user, tenant, path, q)
            if path == "/items":
                return self._send(self.page_items(conn, user, tenant, sess))
            if path == "/audit":
                return self._send(self.page_audit(conn, user, tenant))
            if path == "/backup":
                return self._send(self.page_backups(conn, user, tenant, sess, q))
            return self._send(layout("Not found", '<div class="card pad">Page not found.</div>', user=user, tenant=tenant), 404)
        finally:
            conn.close()

    def do_POST(self):
        conn = self._conn()
        try:
            path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
            form = self._form()

            if path == "/login":
                try:
                    user = security.authenticate(conn, first(form, "email"), first(form, "password"),
                                                 self.client_address[0])
                except security.AuthError as e:
                    return self._send(login_page(e.message), 401)
                rows = security.tenants_for(conn, user["id"])
                if not rows:
                    return self._send(login_page("This account has no business workspace yet."), 403)
                token, _csrf = security.create_session(conn, user["id"], rows[0]["id"],
                                                       self.client_address[0])
                acct.audit(conn, rows[0]["id"], user["id"], "auth.session_created", "session")
                return self._redirect("/", {"Set-Cookie": f"sid={token}; HttpOnly; SameSite=Lax; Path=/"})

            sess = self._session(conn)
            if not sess:
                return self._redirect("/login")

            csrf = first(form, "_csrf")
            if not csrf or not secrets.compare_digest(csrf, sess["csrf_token"]):
                return self._send(layout("Forbidden", '<div class="card pad"><div class="err">Invalid or missing CSRF token. Reload the page and try again.</div></div>'),
                                  403)
            user = conn.execute("SELECT * FROM user WHERE id=?", (sess["user_id"],)).fetchone()
            tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (sess["tenant_id"],)).fetchone()
            if not user or not tenant:
                return self._redirect("/logout")

            if path == "/logout":
                security.revoke_session(conn, self._cookies().get("sid"))
                return self._redirect("/login", {"Set-Cookie": "sid=; Max-Age=0; Path=/"})

            if path == "/backup":
                security.require(conn, user["id"], tenant["id"], "backup.run")
                try:
                    backup_mod.create_backup(DB_PATH, BACKUP_DIR)
                except Exception as exc:  # noqa: BLE001 - surface as a page error
                    return self._error_page(user, tenant, f"Backup failed: {exc}", "/backup")
                return self._redirect("/backup?done=1")

            if path == "/invoices":
                return self._create_invoice(conn, user, tenant, sess, form)
            if path == "/receipts":
                return self._create_payment(conn, user, tenant, sess, form)
            if path == "/credit-notes":
                return self._create_credit_note(conn, user, tenant, sess, form)
            if path == "/bills":
                return self._create_bill(conn, user, tenant, sess, form)
            if path == "/vendors":
                return self._create_vendor(conn, user, tenant, sess, form)
            if path == "/journal":
                return self._create_journal(conn, user, tenant, sess, form)
            if path == "/customers":
                return self._create_customer(conn, user, tenant, sess, form)
            if path == "/items":
                return self._create_item(conn, user, tenant, sess, form)

            return self._send(layout("Not found", '<div class="card pad">Page not found.</div>', user=user, tenant=tenant), 404)
        finally:
            conn.close()

    # ---------------- pages ----------------
    def page_dashboard(self, conn, user, tenant) -> str:
        today = date.today()
        start = today.replace(month=tenant["fiscal_year_start_month"], day=1)
        if start > today:
            start = start.replace(year=start.year - 1)
        d = acct.dashboard(conn, tenant["id"], start.isoformat(), today.isoformat())
        recent = conn.execute(
            "SELECT i.id, i.invoice_no, i.invoice_date, i.total_paise, c.name FROM invoice i"
            " JOIN customer c ON c.id=i.customer_id WHERE i.tenant_id=? ORDER BY i.invoice_date DESC,"
            " i.invoice_no DESC LIMIT 6", (tenant["id"],)).fetchall()

        rows = "".join(
            f'<tr><td><a href="/invoices/{esc(r["id"])}">{esc(r["invoice_no"])}</a></td>'
            f'<td>{esc(r["invoice_date"])}</td><td>{esc(r["name"])}</td><td class="num">{money.fmt(r["total_paise"])}</td></tr>'
            for r in recent) or '<tr><td colspan="4" class="empty">No invoices yet</td></tr>'

        # last 6 months revenue bars from journal lines
        bars = []
        for i in range(5, -1, -1):
            m = (today.month - i - 1) % 12 + 1
            y = today.year - ((today.month - i - 1) // 12 if today.month - i - 1 < 0 else 0)
            ym = f"{y:04d}-{m:02d}"
            row = conn.execute(
                "SELECT COALESCE(SUM(l.credit_paise - l.debit_paise),0) v FROM journal_line l"
                " JOIN journal_entry e ON e.id=l.entry_id JOIN account a ON a.id=l.account_id"
                " WHERE l.tenant_id=? AND a.type='income' AND substr(e.entry_date,1,7)=?",
                (tenant["id"], ym)).fetchone()
            bars.append((ym, row["v"] or 0))
        peak = max([b[1] for b in bars] + [1])
        chart = "".join(
            f'<div class="bar" style="height:{max(3, int((v / peak) * 120))}px">'
            f'<b>{money.fmt(v) if v else ""}</b><span>{ym[5:]}/{ym[2:4]}</span></div>'
            for ym, v in bars)

        body = f"""
<div class="kpis">
  {kpi("Revenue (FY)", money.fmt(d["revenue"]), "from posted journals")}
  {kpi("Net profit (FY)", money.fmt(d["profit"]), "income minus expenses")}
  {kpi("Cash + bank", money.fmt(d["cash"]), "accounts 1000 / 1010")}
  {kpi("Receivable", money.fmt(d["receivable"]), f'{d["open_invoices"]} open invoice(s)')}
  {kpi("Payable", money.fmt(d["payable"]), f'{d["open_bills"]} open bill(s)')}
  {kpi("Inventory", money.fmt(d["inventory"]), "perpetual valuation")}
</div>
<div class="grid2">
  <div class="card pad">
    <div class="sect-head"><h2>Revenue, last 6 months</h2><span class="badge ok">from ledger</span></div>
    <div class="chart">{chart}</div>
    <div style="height:18px"></div>
  </div>
  <div class="card pad">
    <div class="sect-head"><h2>Checks</h2></div>
    <p class="small muted" style="margin:0 0 12px">Every figure on this page is computed from posted journal lines — nothing is cached or invented.</p>
    <p class="small"><span class="badge ok">Double-entry balanced</span></p>
    <table style="margin:10px 0">
      <tr><td>Overdue receivable (60+ days)</td><td class="num">{money.fmt(d["overdue_receivable"])}</td></tr>
      <tr><td>Overdue payable (60+ days)</td><td class="num">{money.fmt(d["overdue_payable"])}</td></tr>
      <tr><td>Invoices posted this FY</td><td class="num">{d["invoice_count"]}</td></tr>
    </table>
    <a class="btn" href="/invoices/new">Create invoice</a>
    <a class="btn ghost" href="/bills/new" style="margin-left:6px">Record bill</a>
  </div>
</div>
<div class="sect" style="margin-top:20px">
  <div class="sect-head"><h2>Recent invoices</h2><a class="btn ghost small" href="/invoices">View all</a></div>
  <div class="card"><table><thead><tr><th>No</th><th>Date</th><th>Customer</th><th class="num">Total</th></tr></thead>
  <tbody>{rows}</tbody></table></div>
</div>"""
        return layout("Dashboard", body, "", user, tenant)

    def page_invoices(self, conn, user, tenant, sess) -> str:
        rows = conn.execute(
            "SELECT i.*, c.name FROM invoice i JOIN customer c ON c.id=i.customer_id"
            " WHERE i.tenant_id=? ORDER BY i.invoice_date DESC, i.invoice_no DESC LIMIT 100",
            (tenant["id"],)).fetchall()
        trs = ""
        total_out = 0
        for r in rows:
            out = acct.invoice_outstanding(conn, tenant["id"], r["id"])
            total_out += out
            status = "Paid" if out <= 0 else ("Partial" if out < r["total_paise"] else "Open")
            badge = "ok" if status == "Paid" else ("neutral" if status == "Partial" else "bad")
            trs += (f'<tr><td><a href="/invoices/{r["id"]}">{esc(r["invoice_no"])}</a></td>'
                    f'<td>{esc(r["invoice_date"])}</td><td>{esc(r["name"])}</td>'
                    f'<td class="num">{money.fmt(r["sub_total_paise"])}</td>'
                    f'<td class="num">{money.fmt(r["tax_paise"])}</td>'
                    f'<td class="num"><b>{money.fmt(r["total_paise"])}</b></td>'
                    f'<td class="num">{money.fmt(out)}</td>'
                    f'<td><span class="badge {badge}">{status}</span></td></tr>')
        trs = trs or '<tr><td colspan="8" class="empty">No invoices yet. Create the first one.</td></tr>'
        body = f"""
<div class="kpis">
  {kpi("Invoices shown", str(len(rows)), "latest 100")}
  {kpi("Outstanding", money.fmt(total_out), "from these invoices")}
</div>
<div class="sect-head"><h2>Sales invoices</h2>
<div><a class="btn" href="/invoices/new">New invoice</a>
<a class="btn ghost" href="/export/invoices.csv">Export CSV</a></div></div>
<div class="card"><table>
<thead><tr><th>No</th><th>Date</th><th>Customer</th><th class="num">Net</th><th class="num">Tax</th><th class="num">Total</th><th class="num">Outstanding</th><th>Status</th></tr></thead>
<tbody>{trs}</tbody></table></div>"""
        return layout("Invoices", body, "invoices", user, tenant)

    def page_invoice_new(self, conn, user, tenant, sess, error: str = "") -> str:
        customers = conn.execute("SELECT * FROM customer WHERE tenant_id=? ORDER BY name",
                                 (tenant["id"],)).fetchall()
        items = conn.execute("SELECT * FROM item WHERE tenant_id=? ORDER BY name",
                             (tenant["id"],)).fetchall()
        if not customers or not items:
            return layout("New invoice",
                          '<div class="card pad"><div class="err">Add at least one customer and one item first.</div>'
                          '<a class="btn ghost" href="/customers">Customers</a> <a class="btn ghost" href="/items">Items</a></div>',
                          "invoices", user, tenant)
        c_opts = "".join(f'<option value="{c["id"]}">{esc(c["name"])} ({esc(c["state_code"])})</option>' for c in customers)
        i_opts = "".join(
            f'<option value="{i["id"]}">{esc(i["name"])} — {money.fmt(i["sale_price_paise"])} @ {i["tax_rate_bp"]/100:.0f}%</option>'
            for i in items)
        err = f'<div class="err">{esc(error)}</div>' if error else ""
        row_tpl = f"""<tr>
  <td><select name="item_id">{i_opts}</select></td>
  <td><input name="qty" value="1" inputmode="decimal"></td>
  <td><input name="price" placeholder="auto" inputmode="decimal"></td>
  <td><input name="discount" value="0" inputmode="decimal"></td>
  <td><button class="btn ghost small" type="button" onclick="this.closest('tr').remove()">Remove</button></td>
</tr>"""
        rows = "".join(row_tpl for _ in range(3))
        body = f"""
{err}
<form method="post" action="/invoices">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="card pad sect">
  <div class="row c4">
    <div class="field"><label>Invoice date</label><input type="date" name="invoice_date" value="{date.today().isoformat()}" required></div>
    <div class="field"><label>Customer</label><select name="customer_id">{c_opts}</select></div>
    <div class="field"><label>Place of supply (state code)</label><input name="place_of_supply" value="{esc(tenant['state_code'])}" maxlength="2"></div>
    <div class="field"><label>Rounding</label><select name="rounding"><option value="">Exact (paise)</option><option value="1">Round to nearest ₹1</option></select></div>
  </div>
</div>
<div class="card sect">
<table><thead><tr><th style="width:44%">Item</th><th>Qty</th><th>Unit price</th><th>Discount</th><th></th></tr></thead>
<tbody id="lines">{rows}</tbody></table>
<div class="pad"><button class="btn ghost small" type="button" onclick="addRow()">+ Add line</button></div>
</div>
<button class="btn" type="submit">Post invoice</button>
<a class="btn ghost" href="/invoices" style="margin-left:8px">Cancel</a>
<script>
const tpl = document.querySelector('#lines tr').outerHTML;
function addRow(){{ const t=document.createElement('tbody'); t.innerHTML=tpl; document.getElementById('lines').appendChild(t.firstElementChild); }}
</script>"""
        return layout("New invoice", body, "invoices", user, tenant)

    def page_invoice_detail(self, conn, user, tenant, sess, invoice_id: str) -> str:
        inv = conn.execute("SELECT i.*, c.name, c.state_code FROM invoice i JOIN customer c ON c.id=i.customer_id"
                           " WHERE i.id=? AND i.tenant_id=?", (invoice_id, tenant["id"])).fetchone()
        if not inv:
            return layout("Not found", '<div class="card pad">Invoice not found.</div>', "invoices", user, tenant)
        lines = conn.execute("SELECT * FROM invoice_line WHERE invoice_id=? ORDER BY rowid",
                             (invoice_id,)).fetchall()
        trs = "".join(
            f'<tr><td>{esc(l["description"])}</td><td class="num">{l["qty_milli"]/1000:.3f}</td>'
            f'<td class="num">{money.fmt(l["unit_price_paise"])}</td><td class="num">{money.fmt(l["discount_paise"])}</td>'
            f'<td class="num">{money.fmt(l["taxable_paise"])}</td><td class="num">{l["tax_rate_bp"]/100:.0f}%</td>'
            f'<td class="num">{money.fmt(l["tax_paise"])}</td><td class="num"><b>{money.fmt(l["line_total_paise"])}</b></td></tr>'
            for l in lines)
        je = conn.execute("SELECT * FROM journal_entry WHERE id=?", (inv["journal_entry_id"],)).fetchone()
        out = acct.invoice_outstanding(conn, tenant["id"], invoice_id)
        status = "Paid" if out <= 0 else ("Part paid" if out < inv["total_paise"] else "Open")
        badge = "ok" if out <= 0 else ("neutral" if out < inv["total_paise"] else "bad")

        receipt_form = ""
        if out > 0:
            receipt_form = f"""
<div class="card pad sect"><h2 style="margin-bottom:12px">Receive payment</h2>
<form method="post" action="/receipts">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="invoice_id" value="{esc(invoice_id)}">
<div class="row c4">
<div class="field"><label>Date</label><input type="date" name="payment_date" value="{date.today().isoformat()}"></div>
<div class="field"><label>Amount</label><input name="amount" value="{money.to_str(out)}" inputmode="decimal"></div>
<div class="field"><label>Mode</label><select name="mode"><option value="bank">Bank</option><option value="cash">Cash</option><option value="upi">UPI</option><option value="cheque">Cheque</option><option value="card">Card</option></select></div>
<div class="field"><label>Reference</label><input name="reference" maxlength="60"></div>
</div>
<button class="btn" type="submit">Record receipt</button>
<span class="small muted" style="margin-left:10px">Outstanding {money.fmt(out)}</span>
</form></div>"""

        cn_lines = []
        for l in lines:
            credited = conn.execute(
                "SELECT COALESCE(SUM(cnl.qty_milli),0) q FROM credit_note_line cnl"
                " JOIN credit_note cn ON cn.id=cnl.credit_note_id"
                " WHERE cn.tenant_id=? AND cn.invoice_id=? AND cnl.invoice_line_id=?",
                (tenant["id"], invoice_id, l["id"])).fetchone()["q"]
            remaining = l["qty_milli"] - credited
            if remaining > 0:
                cn_lines.append((l, remaining))
        cn_opts = "".join(
            f'<option value="{l["id"]}">{esc(l["description"])} — {rem/1000:.3f} returnable</option>'
            for l, rem in cn_lines)
        credit_form = ""
        if cn_opts:
            credit_form = f"""
<div class="card pad sect"><h2 style="margin-bottom:12px">Credit note / sales return</h2>
<form method="post" action="/credit-notes">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="invoice_id" value="{esc(invoice_id)}">
<div class="row c4">
<div class="field"><label>Date</label><input type="date" name="note_date" value="{date.today().isoformat()}"></div>
<div class="field" style="grid-column:span 2"><label>Invoice line</label><select name="invoice_line_id">{cn_opts}</select></div>
<div class="field"><label>Quantity</label><input name="qty" value="1" inputmode="decimal"></div>
</div>
<div class="field"><label>Reason</label><input name="reason" required maxlength="200" placeholder="Damaged / short supply / return"></div>
<button class="btn ghost" type="submit">Post credit note</button>
</form></div>"""

        body = f"""
<div class="sect-head"><div><h2>{esc(inv["invoice_no"])}</h2>
<div class="small muted">{esc(inv["invoice_date"])} · {esc(inv["name"])} · place of supply {esc(inv["place_of_supply_state"])}</div></div>
<div><span class="badge {badge}">Outstanding {money.fmt(out)}</span>
<a class="btn ghost" href="/invoices" style="margin-left:8px">Back</a></div></div>
<div class="card sect"><table>
<thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Rate</th><th class="num">Disc</th><th class="num">Taxable</th><th class="num">Rate</th><th class="num">Tax</th><th class="num">Total</th></tr></thead>
<tbody>{trs}</tbody>
<tfoot>
<tr><td colspan="6">Net</td><td colspan="2" class="num">{money.fmt(inv["sub_total_paise"])}</td></tr>
<tr><td colspan="6">GST</td><td colspan="2" class="num">{money.fmt(inv["tax_paise"])}</td></tr>
<tr><td colspan="6">Round off</td><td colspan="2" class="num">{money.fmt(inv["round_off_paise"])}</td></tr>
<tr><td colspan="6">Invoice total</td><td colspan="2" class="num">{money.fmt(inv["total_paise"])}</td></tr>
</tfoot></table></div>
{receipt_form}
{credit_form}
<div class="card pad small muted">Journal entry <b>{esc(je["entry_no"])}</b> posted on {esc(je["posted_at"][:10])}. Posted entries are immutable; corrections use a credit note or reversal.</div>"""
        return layout(f'Invoice {inv["invoice_no"]}', body, "invoices", user, tenant)

    def page_receipts(self, conn, user, tenant, sess) -> str:
        rows = conn.execute(
            "SELECT p.*, c.name FROM payment p JOIN customer c ON c.id=p.party_id"
            " WHERE p.tenant_id=? AND p.direction='receipt' ORDER BY p.payment_date DESC,"
            " p.voucher_no DESC LIMIT 100", (tenant["id"],)).fetchall()
        trs = ""
        for r in rows:
            alloc = conn.execute(
                "SELECT COALESCE(SUM(amount_paise),0) a FROM payment_allocation WHERE payment_id=?",
                (r["id"],)).fetchone()["a"]
            trs += (f'<tr><td>{esc(r["voucher_no"])}</td><td>{esc(r["payment_date"])}</td>'
                    f'<td>{esc(r["name"])}</td><td>{esc(r["mode"])}</td>'
                    f'<td>{esc(r["reference"] or "")}</td>'
                    f'<td class="num">{money.fmt(r["amount_paise"])}</td>'
                    f'<td class="num">{money.fmt(alloc)}</td>'
                    f'<td class="num">{money.fmt(r["amount_paise"] - alloc)}</td></tr>')
        trs = trs or '<tr><td colspan="8" class="empty">No receipts yet</td></tr>'
        customers = conn.execute("SELECT * FROM customer WHERE tenant_id=? ORDER BY name",
                                 (tenant["id"],)).fetchall()
        c_opts = "".join(f'<option value="{c["id"]}">{esc(c["name"])}</option>' for c in customers)
        ar = acct.receivable_ageing(conn, tenant["id"])
        body = f"""
<div class="kpis">
  {kpi("Receivable outstanding", money.fmt(ar["grand_total"]), f'{len(ar["rows"])} open invoice(s)')}
  {kpi("Overdue 60+ days", money.fmt(ar["totals"]["61-90"] + ar["totals"]["90+"]), "needs follow-up")}
</div>
<div class="grid2">
  <div class="card"><table>
  <thead><tr><th>Voucher</th><th>Date</th><th>Customer</th><th>Mode</th><th>Ref</th><th class="num">Amount</th><th class="num">Allocated</th><th class="num">On account</th></tr></thead>
  <tbody>{trs}</tbody></table></div>
  <div class="card pad"><h2 style="margin-bottom:6px">Advance receipt</h2>
  <p class="small muted" style="margin:0 0 12px">To settle a specific invoice, open the invoice and use <b>Receive payment</b>.</p>
  <form method="post" action="/receipts">
  <input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
  <input type="hidden" name="direction" value="receipt">
  <div class="field"><label>Customer</label><select name="customer_id">{c_opts}</select></div>
  <div class="row c2"><div class="field"><label>Date</label><input type="date" name="payment_date" value="{date.today().isoformat()}"></div>
  <div class="field"><label>Mode</label><select name="mode"><option value="bank">Bank</option><option value="cash">Cash</option><option value="upi">UPI</option><option value="cheque">Cheque</option><option value="card">Card</option></select></div></div>
  <div class="row c2"><div class="field"><label>Amount</label><input name="amount" placeholder="0.00" inputmode="decimal"></div>
  <div class="field"><label>Reference</label><input name="reference" maxlength="60"></div></div>
  <div class="field"><label>Notes</label><input name="notes" maxlength="200"></div>
  <button class="btn" type="submit">Record receipt</button></form></div>
</div>
<p class="small muted" style="margin-top:14px">Receipts post Dr Cash/Bank, Cr Accounts Receivable with the customer tagged, so the customer statement and the control account always agree. <a href="/export/receipts.csv">Export CSV</a></p>"""
        return layout("Receipts", body, "receipts", user, tenant)

    def page_credit_notes(self, conn, user, tenant) -> str:
        rows = conn.execute(
            "SELECT n.*, c.name, i.invoice_no FROM credit_note n"
            " JOIN customer c ON c.id=n.customer_id LEFT JOIN invoice i ON i.id=n.invoice_id"
            " WHERE n.tenant_id=? ORDER BY n.note_date DESC, n.note_no DESC", (tenant["id"],)).fetchall()
        trs = "".join(
            f'<tr><td>{esc(r["note_no"])}</td><td>{esc(r["note_date"])}</td><td>{esc(r["name"])}</td>'
            f'<td>{esc(r["invoice_no"] or "—")}</td><td>{esc(r["reason"])}</td>'
            f'<td class="num">{money.fmt(r["total_paise"])}</td></tr>' for r in rows) or \
            '<tr><td colspan="6" class="empty">No credit notes yet. Open an invoice to raise one.</td></tr>'
        body = f"""
<div class="sect-head"><h2>{len(rows)} credit note(s)</h2><a class="btn ghost" href="/export/credit-notes.csv">Export CSV</a></div>
<div class="card"><table><thead><tr><th>Note</th><th>Date</th><th>Customer</th><th>Invoice</th><th>Reason</th><th class="num">Total</th></tr></thead>
<tbody>{trs}</tbody></table></div>
<p class="small muted" style="margin-top:12px">A credit note reverses revenue and GST, returns stock at cost, and reduces the invoice outstanding. The original invoice is never edited.</p>"""
        return layout("Credit notes", body, "credit-notes", user, tenant)

    def page_bills(self, conn, user, tenant, sess) -> str:
        rows = conn.execute(
            "SELECT b.*, v.name FROM bill b JOIN vendor v ON v.id=b.vendor_id"
            " WHERE b.tenant_id=? ORDER BY b.bill_date DESC, b.bill_no DESC LIMIT 100",
            (tenant["id"],)).fetchall()
        trs = ""
        for r in rows:
            out = acct.bill_outstanding(conn, tenant["id"], r["id"])
            status = "Paid" if out <= 0 else ("Partial" if out < r["total_paise"] else "Open")
            badge = "ok" if status == "Paid" else ("neutral" if status == "Partial" else "bad")
            trs += (f'<tr><td><a href="/bills/{r["id"]}">{esc(r["bill_no"])}</a></td>'
                    f'<td>{esc(r["vendor_bill_no"] or "")}</td><td>{esc(r["bill_date"])}</td>'
                    f'<td>{esc(r["name"])}</td><td class="num">{money.fmt(r["sub_total_paise"])}</td>'
                    f'<td class="num">{money.fmt(r["tax_paise"])}</td>'
                    f'<td class="num"><b>{money.fmt(r["total_paise"])}</b></td>'
                    f'<td class="num">{money.fmt(out)}</td><td><span class="badge {badge}">{status}</span></td></tr>')
        trs = trs or '<tr><td colspan="9" class="empty">No bills yet. Record your first purchase.</td></tr>'
        ap = acct.payable_ageing(conn, tenant["id"])
        body = f"""
<div class="kpis">
  {kpi("Payable outstanding", money.fmt(ap["grand_total"]), f'{len(ap["rows"])} open bill(s)')}
  {kpi("Overdue 60+ days", money.fmt(ap["totals"]["61-90"] + ap["totals"]["90+"]), "to be paid")}
</div>
<div class="sect-head"><h2>{len(rows)} bill(s)</h2>
<div><a class="btn" href="/bills/new">New bill</a> <a class="btn ghost" href="/export/bills.csv">Export CSV</a></div></div>
<div class="card"><table>
<thead><tr><th>Bill</th><th>Vendor bill no</th><th>Date</th><th>Vendor</th><th class="num">Net</th><th class="num">GST</th><th class="num">Total</th><th class="num">Outstanding</th><th>Status</th></tr></thead>
<tbody>{trs}</tbody></table></div>"""
        return layout("Bills", body, "bills", user, tenant)

    def page_bill_new(self, conn, user, tenant, sess, error: str = "") -> str:
        vendors = conn.execute("SELECT * FROM vendor WHERE tenant_id=? ORDER BY name",
                               (tenant["id"],)).fetchall()
        items = conn.execute("SELECT * FROM item WHERE tenant_id=? ORDER BY name",
                             (tenant["id"],)).fetchall()
        if not vendors or not items:
            return layout("New bill", '<div class="card pad"><div class="err">Add at least one vendor and one item first.</div>'
                          '<a class="btn ghost" href="/vendors">Vendors</a> <a class="btn ghost" href="/items">Items</a></div>',
                          "bills", user, tenant)
        v_opts = "".join(f'<option value="{v["id"]}">{esc(v["name"])} ({esc(v["state_code"])})</option>' for v in vendors)
        i_opts = "".join(
            f'<option value="{i["id"]}">{esc(i["name"])} — cost {money.fmt(i["cost_paise"])} @ {i["tax_rate_bp"]/100:.0f}%</option>'
            for i in items)
        err = f'<div class="err">{esc(error)}</div>' if error else ""
        row_tpl = f"""<tr>
  <td><select name="item_id">{i_opts}</select></td>
  <td><input name="qty" value="1" inputmode="decimal"></td>
  <td><input name="price" placeholder="auto (cost)" inputmode="decimal"></td>
  <td><input name="discount" value="0" inputmode="decimal"></td>
  <td><button class="btn ghost small" type="button" onclick="this.closest('tr').remove()">Remove</button></td>
</tr>"""
        rows = "".join(row_tpl for _ in range(2))
        body = f"""
{err}
<form method="post" action="/bills">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="card pad sect">
<div class="row c4">
<div class="field"><label>Bill date</label><input type="date" name="bill_date" value="{date.today().isoformat()}" required></div>
<div class="field"><label>Vendor</label><select name="vendor_id">{v_opts}</select></div>
<div class="field"><label>Vendor bill no</label><input name="vendor_bill_no" maxlength="60"></div>
<div class="field"><label>Place of supply</label><input name="place_of_supply" value="{esc(tenant['state_code'])}" maxlength="2"></div>
</div></div>
<div class="card sect"><table><thead><tr><th style="width:44%">Item</th><th>Qty</th><th>Unit cost</th><th>Discount</th><th></th></tr></thead>
<tbody id="lines">{rows}</tbody></table>
<div class="pad"><button class="btn ghost small" type="button" onclick="addRow()">+ Add line</button></div></div>
<button class="btn" type="submit">Post bill</button>
<a class="btn ghost" href="/bills" style="margin-left:8px">Cancel</a>
<script>
const tpl = document.querySelector('#lines tr').outerHTML;
function addRow(){{ const t=document.createElement('tbody'); t.innerHTML=tpl; document.getElementById('lines').appendChild(t.firstElementChild); }}
</script>"""
        return layout("New bill", body, "bills", user, tenant)

    def page_bill_detail(self, conn, user, tenant, sess, bill_id: str) -> str:
        bill = conn.execute("SELECT b.*, v.name, v.state_code FROM bill b JOIN vendor v ON v.id=b.vendor_id"
                            " WHERE b.id=? AND b.tenant_id=?", (bill_id, tenant["id"])).fetchone()
        if not bill:
            return layout("Not found", '<div class="card pad">Bill not found.</div>', "bills", user, tenant)
        lines = conn.execute("SELECT * FROM bill_line WHERE bill_id=? ORDER BY rowid", (bill_id,)).fetchall()
        trs = "".join(
            f'<tr><td>{esc(l["description"])}</td><td class="num">{l["qty_milli"]/1000:.3f}</td>'
            f'<td class="num">{money.fmt(l["unit_price_paise"])}</td><td class="num">{money.fmt(l["discount_paise"])}</td>'
            f'<td class="num">{money.fmt(l["taxable_paise"])}</td><td class="num">{l["tax_rate_bp"]/100:.0f}%</td>'
            f'<td class="num">{money.fmt(l["tax_paise"])}</td><td class="num"><b>{money.fmt(l["line_total_paise"])}</b></td></tr>'
            for l in lines)
        out = acct.bill_outstanding(conn, tenant["id"], bill_id)
        je = conn.execute("SELECT * FROM journal_entry WHERE id=?", (bill["journal_entry_id"],)).fetchone()
        pay_form = ""
        if out > 0:
            pay_form = f"""
<div class="card pad sect"><h2 style="margin-bottom:12px">Pay this bill</h2>
<form method="post" action="/receipts">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="direction" value="payment">
<input type="hidden" name="bill_id" value="{esc(bill_id)}">
<input type="hidden" name="vendor_id" value="{esc(bill["vendor_id"])}">
<div class="row c4">
<div class="field"><label>Date</label><input type="date" name="payment_date" value="{date.today().isoformat()}"></div>
<div class="field"><label>Amount</label><input name="amount" value="{money.to_str(out)}" inputmode="decimal"></div>
<div class="field"><label>Mode</label><select name="mode"><option value="bank">Bank</option><option value="cash">Cash</option><option value="upi">UPI</option><option value="cheque">Cheque</option></select></div>
<div class="field"><label>Reference</label><input name="reference" maxlength="60"></div>
</div>
<button class="btn" type="submit">Record payment</button></form></div>"""
        body = f"""
<div class="sect-head"><div><h2>{esc(bill["bill_no"])}</h2>
<div class="small muted">{esc(bill["bill_date"])} · {esc(bill["name"])} · vendor bill {esc(bill["vendor_bill_no"] or "—")}</div></div>
<div><span class="badge {"ok" if out <= 0 else "neutral"}">Outstanding {money.fmt(out)}</span>
<a class="btn ghost" href="/bills" style="margin-left:8px">Back</a></div></div>
<div class="card sect"><table>
<thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Rate</th><th class="num">Disc</th><th class="num">Taxable</th><th class="num">Rate</th><th class="num">Tax</th><th class="num">Total</th></tr></thead>
<tbody>{trs}</tbody>
<tfoot>
<tr><td colspan="6">Net</td><td colspan="2" class="num">{money.fmt(bill["sub_total_paise"])}</td></tr>
<tr><td colspan="6">GST input</td><td colspan="2" class="num">{money.fmt(bill["tax_paise"])}</td></tr>
<tr><td colspan="6">Round off</td><td colspan="2" class="num">{money.fmt(bill["round_off_paise"])}</td></tr>
<tr><td colspan="6">Bill total</td><td colspan="2" class="num">{money.fmt(bill["total_paise"])}</td></tr>
</tfoot></table></div>
{pay_form}
<div class="card pad small muted">Journal entry <b>{esc(je["entry_no"])}</b> posted. Bills are immutable; corrections use a debit note or reversal.</div>"""
        return layout("Bill", body, "bills", user, tenant)

    def page_vendors(self, conn, user, tenant, sess) -> str:
        rows = acct.vendor_balances(conn, tenant["id"])
        trs = "".join(
            f'<tr><td><a href="/vendors/{r["id"]}">{esc(r["name"])}</a></td>'
            f'<td>{esc(r["phone"] or "")}</td><td>{esc(r["state_code"])}</td>'
            f'<td class="num"><b>{money.fmt(r["balance"])}</b></td></tr>' for r in rows) or \
            '<tr><td colspan="4" class="empty">No vendors</td></tr>'
        body = f"""
<div class="grid2">
<div class="card"><table><thead><tr><th>Vendor</th><th>Phone</th><th>State</th><th class="num">Payable</th></tr></thead><tbody>{trs}</tbody></table></div>
<div class="card pad"><h2 style="margin-bottom:12px">Add vendor</h2>
<form method="post" action="/vendors">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="field"><label>Name</label><input name="name" required maxlength="120"></div>
<div class="row c2"><div class="field"><label>Phone</label><input name="phone" maxlength="20"></div>
<div class="field"><label>State code</label><input name="state_code" value="{esc(tenant['state_code'])}" maxlength="2"></div></div>
<div class="field"><label>GSTIN (optional)</label><input name="gstin" maxlength="15"></div>
<button class="btn" type="submit">Save vendor</button></form></div></div>"""
        return layout("Vendors", body, "vendors", user, tenant)

    def page_vendor_statement(self, conn, user, tenant, vendor_id: str, q) -> str:
        today = date.today()
        dfrom = (q.get("from") or [f"{today.year}-04-01"])[0]
        dto = (q.get("to") or [today.isoformat()])[0]
        try:
            st = acct.vendor_statement(conn, tenant["id"], vendor_id, dfrom, dto)
        except acct.AccountingError:
            return layout("Not found", '<div class="card pad">Vendor not found.</div>', "vendors", user, tenant)
        v = st["vendor"]
        rows = ""
        for r in st["rows"]:
            ref = esc(r["ref"])
            if r["source_type"] == "bill" and r["source_id"]:
                ref = f'<a href="/bills/{esc(r["source_id"])}">{esc(r["ref"])}</a>'
            rows += (f'<tr><td>{esc(r["date"])}</td><td>{ref}</td><td>{esc(r["narration"])}</td>'
                     f'<td class="num">{money.fmt(r["debit"]) if r["debit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["credit"]) if r["credit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["balance"])}</td></tr>')
        rows = rows or '<tr><td colspan="6" class="empty">No transactions in this period</td></tr>'
        body = f"""
<div class="kpis">
  {kpi("Billed (period)", money.fmt(st["billed"]), "credits to payable")}
  {kpi("Paid (period)", money.fmt(st["paid"]), "debits to payable")}
  {kpi("Closing payable", money.fmt(st["closing"]), "amount we owe")}
</div>
<form method="get" class="card pad sect">
<div class="row c4">
<div class="field"><label>From</label><input type="date" name="from" value="{esc(dfrom)}"></div>
<div class="field"><label>To</label><input type="date" name="to" value="{esc(dto)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
<div class="field" style="display:flex;align-items:flex-end"><a class="btn ghost" href="/vendors">All vendors</a></div>
</div></form>
<div class="card"><table>
<thead><tr><th>Date</th><th>Ref</th><th>Narration</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th></tr></thead>
<tbody><tr><td colspan="5" class="muted">Opening balance</td><td class="num"><b>{money.fmt(st["opening"])}</b></td></tr>
{rows}</tbody>
<tfoot><tr><td colspan="5">Closing payable</td><td class="num">{money.fmt(st["closing"])}</td></tr></tfoot>
</table></div>
<p class="small muted">Vendor: {esc(v["name"])} · state {esc(v["state_code"])} · GSTIN {esc(v["gstin"] or "—")}</p>"""
        return layout(f'Vendor — {v["name"]}', body, "vendors", user, tenant)

    def page_daybook(self, conn, user, tenant, q) -> str:
        today = date.today()
        dfrom = (q.get("from") or [f"{today.year}-04-01"])[0]
        dto = (q.get("to") or [today.isoformat()])[0]
        entries = acct.day_book(conn, tenant["id"], dfrom, dto)
        links = {"invoice": "/invoices/", "bill": "/bills/", "credit_note": "/credit-notes",
                 "receipt": "/receipts", "payment": "/receipts"}
        trs = ""
        for e in entries:
            ref = esc(e["entry_no"])
            base = links.get(e["source_type"])
            if base and e["source_id"] and base.endswith("/"):
                ref = f'<a href="{base}{esc(e["source_id"])}">{esc(e["entry_no"])}</a>'
            trs += (f'<tr><td>{esc(e["entry_date"])}</td><td>{ref}</td>'
                    f'<td>{esc(e["source_type"])}</td><td>{esc(e["narration"])}</td>'
                    f'<td class="num">{money.fmt(e["amount"])}</td>'
                    f'<td><span class="badge {"ok" if e["status"] == "posted" else "neutral"}">{esc(e["status"])}</span></td></tr>')
        trs = trs or '<tr><td colspan="6" class="empty">No vouchers in this period</td></tr>'
        body = f"""
<form method="get" class="card pad sect">
<div class="row c4">
<div class="field"><label>From</label><input type="date" name="from" value="{esc(dfrom)}"></div>
<div class="field"><label>To</label><input type="date" name="to" value="{esc(dto)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
<div class="field" style="display:flex;align-items:flex-end"><a class="btn ghost" href="/export/daybook.csv">Export CSV</a></div>
</div></form>
<div class="card"><table><thead><tr><th>Date</th><th>Voucher</th><th>Type</th><th>Narration</th><th class="num">Amount</th><th>Status</th></tr></thead>
<tbody>{trs}</tbody></table></div>
<p class="small muted" style="margin-top:12px">Every voucher is one balanced journal entry. {len(entries)} entries in this period.</p>"""
        return layout("Day book", body, "daybook", user, tenant)

    def page_journal(self, conn, user, tenant, sess) -> str:
        accounts = conn.execute("SELECT * FROM account WHERE tenant_id=? ORDER BY code",
                                (tenant["id"],)).fetchall()
        opts = "".join(f'<option value="{a["id"]}">{a["code"]} — {esc(a["name"])}</option>' for a in accounts)
        rows = "".join(
            f'<tr><td><select name="account_id">{opts}</select></td>'
            f'<td><input name="debit" value="0" inputmode="decimal"></td>'
            f'<td><input name="credit" value="0" inputmode="decimal"></td></tr>' for _ in range(4))
        body = f"""
<form method="post" action="/journal">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="card pad sect">
<div class="row c3">
<div class="field"><label>Date</label><input type="date" name="entry_date" value="{date.today().isoformat()}" required></div>
<div class="field" style="grid-column:span 2"><label>Narration</label><input name="narration" required maxlength="200"></div>
</div></div>
<div class="card sect"><table><thead><tr><th style="width:60%">Account</th><th>Debit</th><th>Credit</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<button class="btn" type="submit">Post journal</button>
<p class="small muted" style="margin-top:12px">Debits must equal credits exactly. Posting is atomic: an unbalanced entry is rejected and nothing is written.</p>
</form>"""
        return layout("Journal entry", body, "journal", user, tenant)

    def page_ageing(self, conn, user, tenant, q, kind: str) -> str:
        as_of = (q.get("as_of") or [date.today().isoformat()])[0]
        data = acct.receivable_ageing(conn, tenant["id"], as_of) if kind == "ar" else \
            acct.payable_ageing(conn, tenant["id"], as_of)
        party_key = "customer" if kind == "ar" else "vendor"
        doc_key = "invoice_no" if kind == "ar" else "bill_no"
        title = "Receivables ageing" if kind == "ar" else "Payables ageing"
        rows = "".join(
            f'<tr><td>{esc(r[doc_key])}</td><td>{esc(r["date"])}</td><td>{esc(r[party_key])}</td>'
            f'<td class="num">{money.fmt(r["total"])}</td><td class="num">{money.fmt(r["outstanding"])}</td>'
            f'<td class="num">{r["days"]}</td><td><span class="badge neutral">{esc(r["bucket"])}</span></td></tr>'
            for r in data["rows"]) or '<tr><td colspan="7" class="empty">Nothing outstanding</td></tr>'
        t = data["totals"]
        body = f"""
<div class="kpis">
  {kpi("Current (0-30)", money.fmt(t["current"]), "not yet due")}
  {kpi("31-60 days", money.fmt(t["31-60"]), "watch")}
  {kpi("61-90 days", money.fmt(t["61-90"]), "follow up")}
  {kpi("90+ days", money.fmt(t["90+"]), "escalate")}
  {kpi("Total outstanding", money.fmt(data["grand_total"]), f'as of {as_of}')}
</div>
<form method="get" class="sect" style="display:flex;gap:10px;align-items:end;flex-wrap:wrap">
<div><label>As of</label><input type="date" name="as_of" value="{esc(as_of)}"></div>
<button class="btn" type="submit">Apply</button>
<a class="btn ghost" href="/export/{kind}-ageing.csv">Export CSV</a></form>
<div class="card"><table>
<thead><tr><th>Document</th><th>Date</th><th>{party_key.title()}</th><th class="num">Document total</th><th class="num">Outstanding</th><th class="num">Days</th><th>Bucket</th></tr></thead>
<tbody>{rows}</tbody>
<tfoot><tr><td colspan="4">Total</td><td class="num">{money.fmt(data["grand_total"])}</td><td colspan="2"></td></tr></tfoot>
</table></div>"""
        return layout(title, body, f"reports/{kind}-ageing", user, tenant)

    def page_gst(self, conn, user, tenant, q) -> str:
        today = date.today()
        dfrom = (q.get("from") or [f"{today.year}-04-01"])[0]
        dto = (q.get("to") or [today.isoformat()])[0]
        g = acct.gst_summary(conn, tenant["id"], dfrom, dto)
        sales = "".join(
            f'<tr><td>{esc(r["invoice_no"])}</td><td>{esc(r["invoice_date"])}</td><td>{esc(r["party"])}</td>'
            f'<td class="num">{money.fmt(r["sub_total_paise"])}</td><td class="num">{money.fmt(r["tax_paise"])}</td>'
            f'<td class="num">{money.fmt(r["total_paise"])}</td></tr>' for r in g["sales"]) or \
            '<tr><td colspan="6" class="empty">No sales in this period</td></tr>'
        purchases = "".join(
            f'<tr><td>{esc(r["bill_no"])}</td><td>{esc(r["bill_date"])}</td><td>{esc(r["party"])}</td>'
            f'<td class="num">{money.fmt(r["sub_total_paise"])}</td><td class="num">{money.fmt(r["tax_paise"])}</td>'
            f'<td class="num">{money.fmt(r["total_paise"])}</td></tr>' for r in g["purchases"]) or \
            '<tr><td colspan="6" class="empty">No purchases in this period</td></tr>'
        out_rows = "".join(f'<tr><td>{k}</td><td class="num">{money.fmt(v)}</td></tr>' for k, v in g["output"].items())
        in_rows = "".join(f'<tr><td>{k}</td><td class="num">{money.fmt(v)}</td></tr>' for k, v in g["input"].items())
        body = f"""
<form method="get" class="card pad sect">
<div class="row c4">
<div class="field"><label>From</label><input type="date" name="from" value="{esc(dfrom)}"></div>
<div class="field"><label>To</label><input type="date" name="to" value="{esc(dto)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
<div class="field" style="display:flex;align-items:flex-end"><a class="btn ghost" href="/export/gst-sales.csv">Sales CSV</a></div>
</div></form>
<div class="grid2">
<div class="card"><div class="pad"><h2>Output tax (sales)</h2></div><table><tbody>{out_rows}</tbody>
<tfoot><tr><td>Total output</td><td class="num">{money.fmt(g["output_total"])}</td></tr></tfoot></table></div>
<div class="card"><div class="pad"><h2>Input tax (purchases)</h2></div><table><tbody>{in_rows}</tbody>
<tfoot><tr><td>Total input</td><td class="num">{money.fmt(g["input_total"])}</td></tr></tfoot></table></div>
</div>
<div class="card pad" style="margin-top:16px;display:flex;justify-content:space-between;align-items:center">
<div><div class="lbl small muted">NET GST {"PAYABLE" if g["net_payable"] >= 0 else "CREDIT"}</div>
<div style="font-size:28px;font-weight:700">{money.fmt(abs(g["net_payable"]))}</div></div>
<span class="badge neutral">{esc(dfrom)} → {esc(dto)}</span></div>
<div class="sect" style="margin-top:20px"><h2 style="margin-bottom:10px">Sales register</h2>
<div class="card"><table><thead><tr><th>Invoice</th><th>Date</th><th>Customer</th><th class="num">Taxable</th><th class="num">GST</th><th class="num">Total</th></tr></thead><tbody>{sales}</tbody></table></div></div>
<div class="sect"><h2 style="margin-bottom:10px">Purchase register</h2>
<div class="card"><table><thead><tr><th>Bill</th><th>Date</th><th>Vendor</th><th class="num">Taxable</th><th class="num">GST</th><th class="num">Total</th></tr></thead><tbody>{purchases}</tbody></table></div></div>
<p class="small muted">Working summary, not a filed return. Verify with your tax professional before filing.</p>"""
        return layout("GST summary", body, "reports/gst", user, tenant)

    def page_ledger(self, conn, user, tenant, q) -> str:
        accounts = conn.execute("SELECT * FROM account WHERE tenant_id=? ORDER BY code", (tenant["id"],)).fetchall()
        if not accounts:
            return layout("Ledger", '<div class="card pad">No accounts.</div>', "ledger", user, tenant)
        account_id = (q.get("account") or [accounts[0]["id"]])[0]
        today = date.today()
        date_from = (q.get("from") or [f"{today.year}-04-01"])[0]
        date_to = (q.get("to") or [today.isoformat()])[0]
        try:
            gl = acct.general_ledger(conn, tenant["id"], account_id, date_from, date_to)
        except acct.AccountingError:
            gl = None
        opts = "".join(
            f'<option value="{a["id"]}" {"selected" if a["id"] == account_id else ""}>{a["code"]} — {esc(a["name"])}</option>'
            for a in accounts)
        if not gl:
            return layout("Ledger", '<div class="card pad">Account not found.</div>', "ledger", user, tenant)
        rows = "".join(
            f'<tr><td>{esc(r["date"])}</td><td>{esc(r["ref"])}</td><td>{esc(r["narration"])}</td>'
            f'<td class="num">{money.fmt(r["debit"]) if r["debit"] else ""}</td>'
            f'<td class="num">{money.fmt(r["credit"]) if r["credit"] else ""}</td>'
            f'<td class="num">{money.fmt(r["balance"])}</td></tr>' for r in gl["rows"])
        rows = rows or '<tr><td colspan="6" class="empty">No movement in this period</td></tr>'
        body = f"""
<form method="get" action="/ledger" class="card pad sect">
<div class="row c4">
<div class="field"><label>Account</label><select name="account">{opts}</select></div>
<div class="field"><label>From</label><input type="date" name="from" value="{esc(date_from)}"></div>
<div class="field"><label>To</label><input type="date" name="to" value="{esc(date_to)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
</div></form>
<div class="card"><table>
<thead><tr><th>Date</th><th>Ref</th><th>Narration</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th></tr></thead>
<tbody><tr><td colspan="5" class="muted">Opening balance</td><td class="num"><b>{money.fmt(gl["opening"])}</b></td></tr>
{rows}</tbody>
<tfoot><tr><td colspan="5">Closing balance</td><td class="num">{money.fmt(gl["closing"])}</td></tr></tfoot></table></div>"""
        return layout(f'Ledger — {gl["account"]["name"]}', body, "ledger", user, tenant)

    def page_tb(self, conn, user, tenant, q) -> str:
        as_of = (q.get("as_of") or [date.today().isoformat()])[0]
        tb = acct.trial_balance(conn, tenant["id"], as_of)
        rows = "".join(
            f'<tr><td>{esc(r["code"])}</td><td>{esc(r["name"])}</td><td>{esc(r["type"])}</td>'
            f'<td class="num">{money.fmt(r["debit"]) if r["debit"] else ""}</td>'
            f'<td class="num">{money.fmt(r["credit"]) if r["credit"] else ""}</td>'
            f'<td class="num">{money.fmt(r["balance"])}</td></tr>' for r in tb["rows"])
        badge = '<span class="badge ok">Balanced</span>' if tb["balanced"] else '<span class="badge bad">Out of balance</span>'
        body = f"""
<form method="get" class="sect" style="display:flex;gap:10px;align-items:end;flex-wrap:wrap">
<div><label>As of</label><input type="date" name="as_of" value="{esc(as_of)}"></div>
<button class="btn" type="submit">Apply</button>{badge}</form>
<div class="card"><table>
<thead><tr><th>Code</th><th>Account</th><th>Type</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance (Dr+)</th></tr></thead>
<tbody>{rows}</tbody>
<tfoot><tr><td colspan="3">Totals</td><td class="num">{money.fmt(tb["total_debit"])}</td>
<td class="num">{money.fmt(tb["total_credit"])}</td><td class="num">{money.fmt(tb["total_debit"] - tb["total_credit"])}</td></tr></tfoot>
</table></div>"""
        return layout("Trial balance", body, "reports/trial-balance", user, tenant)

    def page_pnl(self, conn, user, tenant, q) -> str:
        today = date.today()
        dfrom = (q.get("from") or [f"{today.year}-04-01"])[0]
        dto = (q.get("to") or [today.isoformat()])[0]
        p = acct.profit_and_loss(conn, tenant["id"], dfrom, dto)
        inc = "".join(f'<tr><td>{esc(r["code"])}</td><td>{esc(r["name"])}</td><td class="num">{money.fmt(r["amount"])}</td></tr>'
                      for r in p["income"]) or '<tr><td colspan="3" class="empty">No income</td></tr>'
        exp = "".join(f'<tr><td>{esc(r["code"])}</td><td>{esc(r["name"])}</td><td class="num">{money.fmt(r["amount"])}</td></tr>'
                      for r in p["expense"]) or '<tr><td colspan="3" class="empty">No expenses</td></tr>'
        body = f"""
<form method="get" class="sect" style="display:flex;gap:10px;align-items:end;flex-wrap:wrap">
<div><label>From</label><input type="date" name="from" value="{esc(dfrom)}"></div>
<div><label>To</label><input type="date" name="to" value="{esc(dto)}"></div>
<button class="btn" type="submit">Apply</button></form>
<div class="grid2">
<div class="card"><div class="pad"><h2>Income</h2></div><table><tbody>{inc}</tbody>
<tfoot><tr><td colspan="2">Total income</td><td class="num">{money.fmt(p["total_income"])}</td></tr></tfoot></table></div>
<div class="card"><div class="pad"><h2>Expenses</h2></div><table><tbody>{exp}</tbody>
<tfoot><tr><td colspan="2">Total expenses</td><td class="num">{money.fmt(p["total_expense"])}</td></tr></tfoot></table></div>
</div>
<div class="card pad" style="margin-top:16px;display:flex;justify-content:space-between;align-items:center">
<div><div class="lbl small muted">NET PROFIT</div><div style="font-size:28px;font-weight:700">{money.fmt(p["net_profit"])}</div></div>
<span class="badge neutral">{esc(dfrom)} → {esc(dto)}</span></div>"""
        return layout("Profit & Loss", body, "reports/pnl", user, tenant)

    def page_bs(self, conn, user, tenant, q) -> str:
        as_of = (q.get("as_of") or [date.today().isoformat()])[0]
        bs = acct.balance_sheet(conn, tenant["id"], as_of)

        def sect(title, rows, total):
            trs = "".join(f'<tr><td>{esc(r["code"])}</td><td>{esc(r["name"])}</td><td class="num">{money.fmt(r["amount"])}</td></tr>'
                          for r in rows) or '<tr><td colspan="3" class="empty">—</td></tr>'
            return f'<div class="card"><div class="pad"><h2>{title}</h2></div><table><tbody>{trs}</tbody>' \
                   f'<tfoot><tr><td colspan="2">Total</td><td class="num">{money.fmt(total)}</td></tr></tfoot></table></div>'

        badge = '<span class="badge ok">A = L + E</span>' if bs["balanced"] else f'<span class="badge bad">Difference {money.fmt(bs["difference"])}</span>'
        body = f"""
<form method="get" class="sect" style="display:flex;gap:10px;align-items:end;flex-wrap:wrap">
<div><label>As of</label><input type="date" name="as_of" value="{esc(as_of)}"></div>
<button class="btn" type="submit">Apply</button>{badge}</form>
<div class="grid2">
{sect("Assets", bs["assets"], bs["total_assets"])}
<div>
{sect("Liabilities", bs["liabilities"], bs["total_liabilities"])}
<div style="height:14px"></div>
{sect("Equity", bs["equity"] + [{"code":"3999","name":"Retained earnings (current period)","amount":bs["retained_earnings"]}], bs["total_equity"])}
</div></div>"""
        return layout("Balance Sheet", body, "reports/balance-sheet", user, tenant)

    def page_customers(self, conn, user, tenant, sess) -> str:
        rows = acct.customer_balances(conn, tenant["id"])
        trs = "".join(
            f'<tr><td><a href="/customers/{r["id"]}">{esc(r["name"])}</a></td>'
            f'<td>{esc(r["phone"] or "")}</td><td>{esc(r["state_code"])}</td>'
            f'<td class="num"><b>{money.fmt(r["balance"])}</b></td></tr>'
            for r in rows) or '<tr><td colspan="4" class="empty">No customers</td></tr>'
        body = f"""
<div class="grid2">
<div class="card"><table><thead><tr><th>Customer</th><th>Phone</th><th>State</th><th class="num">Balance due</th></tr></thead><tbody>{trs}</tbody></table></div>
<div class="card pad"><h2 style="margin-bottom:12px">Add customer</h2>
<form method="post" action="/customers">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="field"><label>Name</label><input name="name" required maxlength="120"></div>
<div class="row c2"><div class="field"><label>Phone</label><input name="phone" maxlength="20"></div>
<div class="field"><label>State code</label><input name="state_code" value="{esc(tenant['state_code'])}" maxlength="2"></div></div>
<div class="field"><label>GSTIN (optional)</label><input name="gstin" maxlength="15"></div>
<button class="btn" type="submit">Save customer</button></form></div></div>"""
        return layout("Customers", body, "customers", user, tenant)

    def page_customer_statement(self, conn, user, tenant, customer_id: str, q) -> str:
        today = date.today()
        dfrom = (q.get("from") or [f"{today.year}-04-01"])[0]
        dto = (q.get("to") or [today.isoformat()])[0]
        try:
            st = acct.customer_statement(conn, tenant["id"], customer_id, dfrom, dto)
        except acct.AccountingError:
            return layout("Not found", '<div class="card pad">Customer not found.</div>',
                          "customers", user, tenant)
        c = st["customer"]
        rows = ""
        for r in st["rows"]:
            ref = esc(r["ref"])
            if r["source_type"] == "invoice" and r["source_id"]:
                ref = f'<a href="/invoices/{esc(r["source_id"])}">{esc(r["ref"])}</a>'
            rows += (f'<tr><td>{esc(r["date"])}</td><td>{ref}</td><td>{esc(r["narration"])}</td>'
                     f'<td class="num">{money.fmt(r["debit"]) if r["debit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["credit"]) if r["credit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["balance"])}</td></tr>')
        rows = rows or '<tr><td colspan="6" class="empty">No transactions in this period</td></tr>'
        body = f"""
<div class="kpis">
  {kpi("Invoiced (period)", money.fmt(st["invoiced"]), "debits to receivable")}
  {kpi("Received (period)", money.fmt(st["received"]), "credits to receivable")}
  {kpi("Closing balance", money.fmt(st["closing"]), "amount due from customer")}
</div>
<form method="get" class="card pad sect">
<div class="row c4">
<div class="field"><label>From</label><input type="date" name="from" value="{esc(dfrom)}"></div>
<div class="field"><label>To</label><input type="date" name="to" value="{esc(dto)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
<div class="field" style="display:flex;align-items:flex-end"><a class="btn ghost" href="/customers">All customers</a></div>
</div></form>
<div class="card"><table>
<thead><tr><th>Date</th><th>Ref</th><th>Narration</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th></tr></thead>
<tbody>
<tr><td colspan="5" class="muted">Opening balance</td><td class="num"><b>{money.fmt(st["opening"])}</b></td></tr>
{rows}</tbody>
<tfoot><tr><td colspan="5">Closing balance</td><td class="num">{money.fmt(st["closing"])}</td></tr></tfoot>
</table></div>
<p class="small muted">Customer: {esc(c["name"])} · state {esc(c["state_code"])} · GSTIN {esc(c["gstin"] or "—")}</p>"""
        return layout(f'Statement — {c["name"]}', body, "customers", user, tenant)

    def page_items(self, conn, user, tenant, sess) -> str:
        rows = conn.execute("SELECT * FROM item WHERE tenant_id=? ORDER BY name", (tenant["id"],)).fetchall()
        trs = "".join(
            f'<tr><td>{esc(r["sku"])}</td><td>{esc(r["name"])}</td><td class="num">{money.fmt(r["sale_price_paise"])}</td>'
            f'<td class="num">{r["tax_rate_bp"]/100:.0f}%</td><td class="num">{r["stock_milli"]/1000:.3f}</td>'
            f'<td class="num">{money.fmt(r["cost_paise"])}</td></tr>' for r in rows) or '<tr><td colspan="6" class="empty">No items</td></tr>'
        body = f"""
<div class="grid2">
<div class="card"><table><thead><tr><th>SKU</th><th>Name</th><th class="num">Price</th><th class="num">GST</th><th class="num">Stock</th><th class="num">Cost</th></tr></thead><tbody>{trs}</tbody></table></div>
<div class="card pad"><h2 style="margin-bottom:12px">Add item</h2>
<form method="post" action="/items">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="row c2"><div class="field"><label>SKU</label><input name="sku" required maxlength="40"></div>
<div class="field"><label>Name</label><input name="name" required maxlength="120"></div></div>
<div class="row c3"><div class="field"><label>Sale price</label><input name="price" value="0" inputmode="decimal"></div>
<div class="field"><label>Cost</label><input name="cost" value="0" inputmode="decimal"></div>
<div class="field"><label>GST %</label><input name="tax" value="18" inputmode="decimal"></div></div>
<div class="row c2"><div class="field"><label>Opening stock</label><input name="stock" value="0" inputmode="decimal"></div>
<div class="field"><label>Track stock</label><select name="track"><option value="1">Yes (goods)</option><option value="0">No (service)</option></select></div></div>
<button class="btn" type="submit">Save item</button></form></div></div>"""
        return layout("Items", body, "items", user, tenant)

    def page_backups(self, conn, user, tenant, sess, q) -> str:
        runs = backup_mod.recent_runs(conn)
        trs = "".join(
            f'<tr><td>{esc(r["created_at"][:19].replace("T"," "))}</td>'
            f'<td><span class="badge {"ok" if r["status"] == "verified" else "bad"}">{esc(r["status"])}</span></td>'
            f'<td class="num">{r["size_bytes"]:,}</td>'
            f'<td class="small"><code>{esc(r["sha256"][:16])}…</code></td>'
            f'<td class="small muted">{esc(r["path"])}</td></tr>' for r in runs) or \
            '<tr><td colspan="5" class="empty">No backups yet. Run the first one.</td></tr>'
        done = (q.get("done") or [""])[0] == "1"
        banner = ('<div class="card pad" style="margin-bottom:14px"><span class="badge ok">Backup created and verified</span> '
                  'The file is stored in <code>backups/</code> with its SHA-256 recorded above.</div>') if done else ""
        body = f"""
{banner}
<div class="kpis">
  {kpi("Backups recorded", str(len(runs)), "latest 20 shown")}
  {kpi("Verified", str(sum(1 for r in runs if r["status"] == "verified")), "integrity + balance checks")}
</div>
<div class="sect-head"><h2>Backup &amp; restore drill</h2>
<form method="post" action="/backup">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<button class="btn" type="submit">Back up now</button>
</form></div>
<div class="card"><table>
<thead><tr><th>Created (UTC)</th><th>Status</th><th class="num">Size (bytes)</th><th>SHA-256</th><th>File</th></tr></thead>
<tbody>{trs}</tbody></table></div>
<div class="card pad sect">
<h2 style="margin-bottom:8px">Restore verification</h2>
<p class="small muted" style="margin-top:0">Every backup is opened in read-only mode and checked for SQLite integrity, foreign-key violations, balanced journals and matching row counts before it is marked verified. To repeat the drill from a terminal:</p>
<pre class="small" style="background:#F4F7F4;padding:12px;border-radius:10px;overflow:auto">python scripts/backup.py
python scripts/restore_verify.py --backup backups/&lt;file&gt;.db</pre>
<p class="small muted">A failed backup is recorded as failed and never presented as safe. Restores are a manual, verified operation in this build — there is no one-click destructive restore.</p>
</div>"""
        return layout("Backups", body, "backup", user, tenant)

    def page_audit(self, conn, user, tenant) -> str:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE tenant_id=? ORDER BY created_at DESC LIMIT 100",
            (tenant["id"],)).fetchall()
        trs = "".join(
            f'<tr><td>{esc(r["created_at"][:19].replace("T"," "))}</td><td>{esc(r["action"])}</td>'
            f'<td>{esc(r["target_type"] or "")}</td><td><span class="badge {"ok" if r["result"]=="success" else "bad"}">{esc(r["result"])}</span></td>'
            f'<td class="small muted">{esc(r["meta"] or "")}</td></tr>' for r in rows) or \
            '<tr><td colspan="5" class="empty">No audit entries</td></tr>'
        body = f'<div class="card"><table><thead><tr><th>Time (UTC)</th><th>Action</th><th>Target</th><th>Result</th><th>Meta</th></tr></thead><tbody>{trs}</tbody></table></div>'
        return layout("Audit log", body, "audit", user, tenant)

    # ---------------- actions ----------------
    def _create_customer(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "customer.manage")
        name = first(form, "name").strip()
        if not name:
            return self._redirect("/customers")
        cid = db.new_id()
        conn.execute("INSERT INTO customer (id, tenant_id, name, phone, gstin, state_code, created_at)"
                     " VALUES (?,?,?,?,?,?,?)",
                     (cid, tenant["id"], name[:120], first(form, "phone")[:20],
                      first(form, "gstin")[:15], (first(form, "state_code") or tenant["state_code"])[:2], db.now()))
        acct.audit(conn, tenant["id"], user["id"], "customer.create", "customer", cid)
        return self._redirect("/customers")

    def _create_item(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "item.manage")
        sku = first(form, "sku").strip()
        name = first(form, "name").strip()
        if not sku or not name:
            return self._redirect("/items")
        try:
            price = money.parse_amount(first(form, "price") or "0")
            cost = money.parse_amount(first(form, "cost") or "0")
            rate = int(round(float(first(form, "tax") or "18") * 100))
            stock = money.parse_qty(first(form, "stock") or "0")
        except (money.MoneyError, ValueError):
            return self._redirect("/items")
        iid = db.new_id()
        conn.execute("INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise,"
                     " tax_rate_bp, stock_milli, track_stock) VALUES (?,?,?,?,?,?,?,?,?)",
                     (iid, tenant["id"], sku[:40], name[:120], price, cost, rate, stock,
                      1 if first(form, "track") != "0" else 0))
        acct.audit(conn, tenant["id"], user["id"], "item.create", "item", iid)
        return self._redirect("/items")

    def _create_invoice(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "invoice.create")
        item_ids = form.get("item_id") or []
        qtys = form.get("qty") or []
        prices = form.get("price") or []
        discounts = form.get("discount") or []

        def pick(seq, i):
            return seq[i] if i < len(seq) else ""

        lines = []
        try:
            for i, iid in enumerate(item_ids):
                q = pick(qtys, i)
                if not q or q.strip() in ("", "0", "0.0", "0.000"):
                    continue
                line = {"item_id": iid, "qty": money.parse_qty(q),
                        "discount": money.parse_amount(pick(discounts, i) or "0")}
                p = pick(prices, i).strip()
                if p:
                    line["unit_price"] = money.parse_amount(p)
                lines.append(line)
        except money.MoneyError as e:
            return self._send(self.page_invoice_new(conn, user, tenant, sess, str(e)), 400)

        if not lines:
            return self._send(self.page_invoice_new(conn, user, tenant, sess,
                                                    "Add at least one line with a quantity."), 400)
        try:
            inv = acct.create_invoice(
                conn, tenant["id"], first(form, "customer_id"), first(form, "invoice_date"),
                (first(form, "place_of_supply") or tenant["state_code"])[:2], lines,
                round_to_rupee=first(form, "rounding") == "1", created_by=user["id"])
        except acct.AccountingError as e:
            return self._send(self.page_invoice_new(conn, user, tenant, sess, e.message), 400)
        return self._redirect(f'/invoices/{inv["id"]}')


    # ---------------- actions: sales / purchases / books ----------------
    def _error_page(self, user, tenant, message: str, back: str = "/") -> str:
        return self._send(layout("Cannot post",
                                 f'<div class="card pad"><div class="err">{esc(message)}</div>'
                                 f'<a class="btn ghost" href="{esc(back)}">Back</a></div>',
                                 "", user, tenant), 400)

    def _create_payment(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "payment.record")
        invoice_id = first(form, "invoice_id")
        bill_id = first(form, "bill_id")
        back = f"/invoices/{invoice_id}" if invoice_id else (f"/bills/{bill_id}" if bill_id else "/receipts")
        try:
            amount = money.parse_amount(first(form, "amount"))
            if amount <= 0:
                raise money.MoneyError("Amount must be greater than zero")
            when = first(form, "payment_date") or date.today().isoformat()
            mode = first(form, "mode") or "bank"
            reference = first(form, "reference")
            notes = first(form, "notes")

            if invoice_id:
                inv = conn.execute("SELECT * FROM invoice WHERE id=? AND tenant_id=?",
                                   (invoice_id, tenant["id"])).fetchone()
                if not inv:
                    raise acct.AccountingError("DOC_NOT_FOUND", "Invoice not found")
                outstanding = acct.invoice_outstanding(conn, tenant["id"], invoice_id)
                if amount > outstanding:
                    raise acct.AccountingError(
                        "OVER_ALLOCATION",
                        f"Amount exceeds the outstanding balance of {money.fmt(outstanding)}")
                acct.record_payment(conn, tenant["id"], "receipt", inv["customer_id"], when, amount,
                                    mode, [{"doc_type": "invoice", "doc_id": invoice_id,
                                            "amount": amount}], reference=reference, notes=notes,
                                    created_by=user["id"])
                return self._redirect(f"/invoices/{invoice_id}")

            if bill_id:
                bill = conn.execute("SELECT * FROM bill WHERE id=? AND tenant_id=?",
                                    (bill_id, tenant["id"])).fetchone()
                if not bill:
                    raise acct.AccountingError("DOC_NOT_FOUND", "Bill not found")
                outstanding = acct.bill_outstanding(conn, tenant["id"], bill_id)
                if amount > outstanding:
                    raise acct.AccountingError(
                        "OVER_ALLOCATION",
                        f"Amount exceeds the outstanding balance of {money.fmt(outstanding)}")
                acct.record_payment(conn, tenant["id"], "payment", bill["vendor_id"], when, amount,
                                    mode, [{"doc_type": "bill", "doc_id": bill_id,
                                            "amount": amount}], reference=reference, notes=notes,
                                    created_by=user["id"])
                return self._redirect(f"/bills/{bill_id}")

            customer_id = first(form, "customer_id")
            if not customer_id:
                raise acct.AccountingError("CUSTOMER_REQUIRED", "Choose a customer")
            acct.record_payment(conn, tenant["id"], "receipt", customer_id, when, amount, mode, [],
                                reference=reference, notes=notes, created_by=user["id"])
            return self._redirect("/receipts")
        except (acct.AccountingError, money.MoneyError) as e:
            return self._error_page(user, tenant, getattr(e, "message", str(e)), back)

    def _create_credit_note(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "credit_note.create")
        invoice_id = first(form, "invoice_id")
        try:
            qty = money.parse_qty(first(form, "qty"))
            note = acct.create_credit_note(
                conn, tenant["id"], invoice_id, first(form, "note_date") or date.today().isoformat(),
                first(form, "reason"), [{"invoice_line_id": first(form, "invoice_line_id"), "qty": qty}],
                created_by=user["id"])
            return self._redirect(f"/invoices/{invoice_id}")
        except (acct.AccountingError, money.MoneyError) as e:
            return self._error_page(user, tenant, getattr(e, "message", str(e)),
                                    f"/invoices/{invoice_id}")

    def _create_bill(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "bill.create")
        item_ids = form.get("item_id") or []
        qtys = form.get("qty") or []
        prices = form.get("price") or []
        discounts = form.get("discount") or []

        def pick(seq, i):
            return seq[i] if i < len(seq) else ""

        lines = []
        try:
            for i, iid in enumerate(item_ids):
                q = pick(qtys, i)
                if not q or q.strip() in ("", "0", "0.0", "0.000"):
                    continue
                line = {"item_id": iid, "qty": money.parse_qty(q),
                        "discount": money.parse_amount(pick(discounts, i) or "0")}
                p = pick(prices, i).strip()
                if p:
                    line["unit_price"] = money.parse_amount(p)
                lines.append(line)
        except money.MoneyError as e:
            return self._send(self.page_bill_new(conn, user, tenant, sess, str(e)), 400)

        if not lines:
            return self._send(self.page_bill_new(conn, user, tenant, sess,
                                                 "Add at least one line with a quantity."), 400)
        try:
            bill = acct.create_bill(
                conn, tenant["id"], first(form, "vendor_id"), first(form, "bill_date"),
                first(form, "vendor_bill_no"),
                (first(form, "place_of_supply") or tenant["state_code"])[:2], lines,
                round_to_rupee=first(form, "rounding") == "1", created_by=user["id"])
        except acct.AccountingError as e:
            return self._send(self.page_bill_new(conn, user, tenant, sess, e.message), 400)
        return self._redirect(f'/bills/{bill["id"]}')

    def _create_vendor(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "vendor.manage")
        name = first(form, "name").strip()
        if not name:
            return self._redirect("/vendors")
        vid = db.new_id()
        conn.execute("INSERT INTO vendor (id, tenant_id, name, phone, gstin, state_code, created_at)"
                     " VALUES (?,?,?,?,?,?,?)",
                     (vid, tenant["id"], name[:120], first(form, "phone")[:20],
                      first(form, "gstin")[:15],
                      (first(form, "state_code") or tenant["state_code"])[:2], db.now()))
        acct.audit(conn, tenant["id"], user["id"], "vendor.create", "vendor", vid)
        return self._redirect("/vendors")

    def _create_journal(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "journal.post")
        accounts = form.get("account_id") or []
        debits = form.get("debit") or []
        credits = form.get("credit") or []

        def pick(seq, i):
            return seq[i] if i < len(seq) else ""

        lines = []
        try:
            for i, aid in enumerate(accounts):
                d = money.parse_amount(pick(debits, i) or "0")
                c = money.parse_amount(pick(credits, i) or "0")
                if d == 0 and c == 0:
                    continue
                lines.append({"account_id": aid, "debit": d, "credit": c})
            entry_id = acct.post_journal(
                conn, tenant["id"], first(form, "entry_date") or date.today().isoformat(),
                first(form, "narration") or "Manual journal", lines, source_type="manual",
                created_by=user["id"])
            return self._redirect("/daybook")
        except (acct.AccountingError, money.MoneyError) as e:
            return self._error_page(user, tenant, getattr(e, "message", str(e)), "/journal")

    # ---------------- exports ----------------
    def _send_bytes(self, data: bytes, content_type: str, filename: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def export_csv(self, conn, user, tenant, path, q):
        security.require(conn, user["id"], tenant["id"], "report.export")
        name = path.rsplit("/", 1)[-1]
        if not name.endswith(".csv"):
            return self._send("Not found", 404)
        key = name[:-4]
        tid = tenant["id"]
        today = date.today().isoformat()
        rows: list[list] = []

        if key == "trial-balance":
            as_of = (q.get("as_of") or [today])[0]
            tb = acct.trial_balance(conn, tid, as_of)
            rows = [["Code", "Account", "Type", "Debit", "Credit", "Balance"]]
            rows += [[r["code"], r["name"], r["type"], money.to_str(r["debit"]),
                      money.to_str(r["credit"]), money.to_str(r["balance"])] for r in tb["rows"]]
            rows.append(["", "", "TOTAL", money.to_str(tb["total_debit"]),
                         money.to_str(tb["total_credit"]), ""])
        elif key == "pnl":
            dfrom = (q.get("from") or [f"{today[:4]}-04-01"])[0]
            dto = (q.get("to") or [today])[0]
            p = acct.profit_and_loss(conn, tid, dfrom, dto)
            rows = [["Section", "Code", "Account", "Amount"]]
            rows += [["Income", r["code"], r["name"], money.to_str(r["amount"])] for r in p["income"]]
            rows += [["Expense", r["code"], r["name"], money.to_str(r["amount"])] for r in p["expense"]]
            rows.append(["", "", "Net profit", money.to_str(p["net_profit"])])
        elif key == "balance-sheet":
            as_of = (q.get("as_of") or [today])[0]
            bs = acct.balance_sheet(conn, tid, as_of)
            rows = [["Section", "Code", "Account", "Amount"]]
            rows += [["Asset", r["code"], r["name"], money.to_str(r["amount"])] for r in bs["assets"]]
            rows += [["Liability", r["code"], r["name"], money.to_str(r["amount"])] for r in bs["liabilities"]]
            rows += [["Equity", r["code"], r["name"], money.to_str(r["amount"])] for r in bs["equity"]]
            rows.append(["Equity", "3999", "Retained earnings (current period)",
                         money.to_str(bs["retained_earnings"])])
        elif key == "ledger":
            accounts = conn.execute("SELECT id FROM account WHERE tenant_id=? ORDER BY code",
                                    (tid,)).fetchall()
            account_id = (q.get("account") or [accounts[0]["id"] if accounts else ""])[0]
            dfrom = (q.get("from") or [f"{today[:4]}-04-01"])[0]
            dto = (q.get("to") or [today])[0]
            gl = acct.general_ledger(conn, tid, account_id, dfrom, dto)
            rows = [["Date", "Ref", "Narration", "Debit", "Credit", "Balance"],
                    ["", "", "Opening balance", "", "", money.to_str(gl["opening"])]]
            rows += [[r["date"], r["ref"], r["narration"], money.to_str(r["debit"]) if r["debit"] else "",
                      money.to_str(r["credit"]) if r["credit"] else "", money.to_str(r["balance"])]
                     for r in gl["rows"]]
            rows.append(["", "", "Closing balance", "", "", money.to_str(gl["closing"])])
        elif key == "daybook":
            dfrom = (q.get("from") or [f"{today[:4]}-04-01"])[0]
            dto = (q.get("to") or [today])[0]
            rows = [["Date", "Voucher", "Type", "Narration", "Amount", "Status"]]
            rows += [[e["entry_date"], e["entry_no"], e["source_type"], e["narration"],
                      money.to_str(e["amount"]), e["status"]]
                     for e in acct.day_book(conn, tid, dfrom, dto)]
        elif key in ("ar-ageing", "ap-ageing"):
            as_of = (q.get("as_of") or [today])[0]
            data = acct.receivable_ageing(conn, tid, as_of) if key == "ar-ageing" else \
                acct.payable_ageing(conn, tid, as_of)
            party = "Customer" if key == "ar-ageing" else "Vendor"
            doc = "Invoice" if key == "ar-ageing" else "Bill"
            rows = [[doc, "Date", party, "Total", "Outstanding", "Days", "Bucket"]]
            rows += [[r.get("invoice_no") or r.get("bill_no"), r["date"], r[party.lower()],
                      money.to_str(r["total"]), money.to_str(r["outstanding"]), r["days"], r["bucket"]]
                     for r in data["rows"]]
        elif key in ("gst-sales", "gst-purchases"):
            dfrom = (q.get("from") or [f"{today[:4]}-04-01"])[0]
            dto = (q.get("to") or [today])[0]
            g = acct.gst_summary(conn, tid, dfrom, dto)
            if key == "gst-sales":
                rows = [["Invoice", "Date", "Customer", "Taxable", "GST", "Total"]]
                rows += [[r["invoice_no"], r["invoice_date"], r["party"], money.to_str(r["sub_total_paise"]),
                          money.to_str(r["tax_paise"]), money.to_str(r["total_paise"])] for r in g["sales"]]
            else:
                rows = [["Bill", "Date", "Vendor", "Taxable", "GST", "Total"]]
                rows += [[r["bill_no"], r["bill_date"], r["party"], money.to_str(r["sub_total_paise"]),
                          money.to_str(r["tax_paise"]), money.to_str(r["total_paise"])] for r in g["purchases"]]
        elif key == "invoices":
            data = conn.execute(
                "SELECT i.*, c.name FROM invoice i JOIN customer c ON c.id=i.customer_id"
                " WHERE i.tenant_id=? ORDER BY i.invoice_date", (tid,)).fetchall()
            rows = [["Invoice", "Date", "Customer", "Taxable", "GST", "Total", "Outstanding", "Status"]]
            for r in data:
                out = acct.invoice_outstanding(conn, tid, r["id"])
                rows.append([r["invoice_no"], r["invoice_date"], r["name"],
                             money.to_str(r["sub_total_paise"]), money.to_str(r["tax_paise"]),
                             money.to_str(r["total_paise"]), money.to_str(out), r["status"]])
        elif key == "receipts":
            data = conn.execute(
                "SELECT p.*, c.name FROM payment p JOIN customer c ON c.id=p.party_id"
                " WHERE p.tenant_id=? AND p.direction='receipt' ORDER BY p.payment_date", (tid,)).fetchall()
            rows = [["Voucher", "Date", "Customer", "Mode", "Reference", "Amount"]]
            rows += [[r["voucher_no"], r["payment_date"], r["name"], r["mode"],
                      r["reference"] or "", money.to_str(r["amount_paise"])] for r in data]
        elif key == "bills":
            data = conn.execute(
                "SELECT b.*, v.name FROM bill b JOIN vendor v ON v.id=b.vendor_id"
                " WHERE b.tenant_id=? ORDER BY b.bill_date", (tid,)).fetchall()
            rows = [["Bill", "Vendor bill no", "Date", "Vendor", "Taxable", "GST", "Total", "Outstanding"]]
            for r in data:
                rows.append([r["bill_no"], r["vendor_bill_no"] or "", r["bill_date"], r["name"],
                             money.to_str(r["sub_total_paise"]), money.to_str(r["tax_paise"]),
                             money.to_str(r["total_paise"]),
                             money.to_str(acct.bill_outstanding(conn, tid, r["id"]))])
        elif key == "credit-notes":
            data = conn.execute(
                "SELECT n.*, c.name FROM credit_note n JOIN customer c ON c.id=n.customer_id"
                " WHERE n.tenant_id=? ORDER BY n.note_date", (tid,)).fetchall()
            rows = [["Note", "Date", "Customer", "Reason", "Taxable", "GST", "Total"]]
            rows += [[r["note_no"], r["note_date"], r["name"], r["reason"],
                      money.to_str(r["sub_total_paise"]), money.to_str(r["tax_paise"]),
                      money.to_str(r["total_paise"])] for r in data]
        else:
            return self._send("Unknown export", 404)

        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\r\n")
        writer.writerows(rows)
        data = buf.getvalue().encode("utf-8-sig")
        self._send_bytes(data, "text/csv; charset=utf-8", f"arthivio-{key}-{today}.csv")


def main(port: int = 8000):
    db.init_db(db.connect(DB_PATH))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"ARTHIVIO running on http://127.0.0.1:{port}  (db: {DB_PATH})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main(int(os.environ.get("PORT", "8000")))
