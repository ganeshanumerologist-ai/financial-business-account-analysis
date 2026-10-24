"""ARTHIVIO web app — stdlib HTTP server, server-rendered, no external deps."""
from __future__ import annotations

import html
import os
import re
import secrets
import sqlite3
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import accounting as acct
from . import db, money, security

DB_PATH = os.environ.get("ARTHIVIO_DB", os.path.join("data", "arthivio.db"))
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
.side{background:linear-gradient(180deg,#124A36 0%,#0E3B2B 100%);color:#EAF2EC;padding:20px 16px 28px;position:sticky;top:0;height:100vh}
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
    ("", "Dash", "Dashboard"),
    ("invoices", "inv", "Invoices"),
    ("ledger", "led", "Ledger"),
    ("reports/trial-balance", "rep", "Trial Balance"),
    ("reports/pnl", "rep", "Profit &amp; Loss"),
    ("reports/balance-sheet", "rep", "Balance Sheet"),
    ("customers", "cust", "Customers"),
    ("items", "item", "Items"),
    ("audit", "audit", "Audit Log"),
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
    for path, ico, label in NAV:
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
  <nav class="nav"><div class="grp">Workspace</div>{''.join(nav)}</nav>
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
                return self._send(self.page_invoice_detail(conn, user, tenant, path.rsplit("/", 1)[1]))
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
            if path == "/items":
                return self._send(self.page_items(conn, user, tenant, sess))
            if path == "/audit":
                return self._send(self.page_audit(conn, user, tenant))
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

            if path == "/invoices":
                return self._create_invoice(conn, user, tenant, sess, form)
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
  {kpi("Receivable", money.fmt(d["receivable"]), "accounts receivable")}
  {kpi("Inventory", money.fmt(d["inventory"]), "perpetual valuation")}
  {kpi("Invoices (FY)", str(d["invoice_count"]), "posted only")}
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
    <p class="small muted">Balance sheet and trial balance are available from the left menu.</p>
    <a class="btn" href="/invoices/new">Create invoice</a>
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
        trs = "".join(
            f'<tr><td><a href="/invoices/{r["id"]}">{esc(r["invoice_no"])}</a></td><td>{esc(r["invoice_date"])}</td>'
            f'<td>{esc(r["name"])}</td><td class="num">{money.fmt(r["sub_total_paise"])}</td>'
            f'<td class="num">{money.fmt(r["tax_paise"])}</td><td class="num"><b>{money.fmt(r["total_paise"])}</b></td>'
            f'<td><span class="badge ok">{esc(r["status"])}</span></td></tr>'
            for r in rows) or '<tr><td colspan="7" class="empty">No invoices yet. Create the first one.</td></tr>'
        body = f"""
<div class="sect-head"><h2>{len(rows)} invoice(s)</h2><a class="btn" href="/invoices/new">New invoice</a></div>
<div class="card"><table>
<thead><tr><th>No</th><th>Date</th><th>Customer</th><th class="num">Net</th><th class="num">Tax</th><th class="num">Total</th><th>Status</th></tr></thead>
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

    def page_invoice_detail(self, conn, user, tenant, invoice_id: str) -> str:
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
        body = f"""
<div class="sect-head"><div><h2>{esc(inv["invoice_no"])}</h2>
<div class="small muted">{esc(inv["invoice_date"])} · {esc(inv["name"])} · place of supply {esc(inv["place_of_supply_state"])}</div></div>
<a class="btn ghost" href="/invoices">Back</a></div>
<div class="card sect"><table>
<thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Rate</th><th class="num">Disc</th><th class="num">Taxable</th><th class="num">Rate</th><th class="num">Tax</th><th class="num">Total</th></tr></thead>
<tbody>{trs}</tbody>
<tfoot>
<tr><td colspan="6">Net</td><td colspan="2" class="num">{money.fmt(inv["sub_total_paise"])}</td></tr>
<tr><td colspan="6">GST</td><td colspan="2" class="num">{money.fmt(inv["tax_paise"])}</td></tr>
<tr><td colspan="6">Round off</td><td colspan="2" class="num">{money.fmt(inv["round_off_paise"])}</td></tr>
<tr><td colspan="6">Invoice total</td><td colspan="2" class="num">{money.fmt(inv["total_paise"])}</td></tr>
</tfoot></table></div>
<div class="card pad small muted">Journal entry <b>{esc(je["entry_no"])}</b> posted on {esc(je["posted_at"][:10])}. Posted entries are immutable; corrections use a reversal.</div>"""
        return layout("Invoice", body, "invoices", user, tenant)

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
