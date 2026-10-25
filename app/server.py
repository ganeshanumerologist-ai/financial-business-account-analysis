"""ARTHIVIO web app — stdlib HTTP server, server-rendered, no external deps."""
from __future__ import annotations

import csv
import html
import io
import json
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
from . import bank as bank_mod
from . import db, money, security
from . import gstr2b as gstr2b_mod
from . import sharing

DB_PATH = os.environ.get("ARTHIVIO_DB", os.path.join("data", "arthivio.db"))
BACKUP_DIR = os.environ.get("ARTHIVIO_BACKUP_DIR", "backups")
APP_NAME = "ARTHIVIO"

CSS = """
:root{
  --ivory:#F7F5EF; --surface:#FFFFFF; --ink:#183E35; --ink-soft:#3C534B;
  --emerald:#176B4D; --emerald-700:#11543C; --sage:#DCE8D9; --sage-soft:#EEF4EC;
  --gold:#C6A15B; --line:#E5E1D6; --muted:#5A685F; --danger:#A6402F; --danger-bg:#F7E7E3;
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
.table-wrap{overflow-x:auto}
.review-cell{min-width:210px}
.review-form summary{cursor:pointer;color:var(--emerald);font-size:12px;font-weight:600;margin-top:4px}
.review-form[open] summary{margin-bottom:6px}
.review-form form{display:grid;gap:5px;min-width:190px}
.review-form select,.review-form input{font-size:12.5px;padding:6px 8px}
.btn{display:inline-flex;align-items:center;gap:8px;background:var(--emerald);color:#fff;border:0;border-radius:10px;
  padding:10px 16px;font-size:14.5px;font-weight:600;cursor:pointer}
.btn:hover{background:var(--emerald-700);text-decoration:none;color:#fff}
.btn.ghost{background:#fff;color:var(--emerald);border:1px solid #C9D8CE}
.btn.ghost:hover{background:var(--sage-soft);color:var(--emerald-700)}
.btn.small{padding:7px 12px;font-size:13.5px}
input,select,textarea{font:inherit;color:var(--ink);background:#fff;border:1px solid #D8D3C6;border-radius:9px;padding:9px 11px;width:100%}
input:focus,select:focus,textarea:focus{outline:2px solid #BBD6C6;outline-offset:0;border-color:var(--emerald)}
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

PRINT_CSS = """
@page{size:A4;margin:12mm}
*{box-sizing:border-box}
body{margin:0;background:#EEECE5;color:#1B2B26;font-family:"Segoe UI",system-ui,Arial,sans-serif;font-size:12px;line-height:1.45}
.toolbar{max-width:190mm;margin:14px auto;display:flex;gap:10px;justify-content:flex-end}
.toolbar a,.toolbar button{font:inherit;font-size:13px;padding:8px 14px;border-radius:8px;border:1px solid #C9D3CD;background:#fff;color:#176B4D;cursor:pointer;text-decoration:none}
.toolbar button{background:#176B4D;color:#fff;border-color:#176B4D}
.sheet{width:190mm;min-height:270mm;margin:0 auto 20px;background:#fff;padding:14mm 14mm 12mm;box-shadow:0 4px 24px rgba(0,0,0,.08)}
.head{display:flex;justify-content:space-between;gap:18px;border-bottom:2px solid #176B4D;padding-bottom:10px}
.head .brand{font-size:21px;font-weight:700;letter-spacing:.03em;color:#123F2E}
.head .meta{text-align:right;min-width:58mm}
.head .meta .doc{font-size:15px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#123F2E}
.addr{font-size:11px;color:#44564F;margin-top:3px}
.parties{display:flex;gap:16px;margin:12px 0}
.parties>div{flex:1;border:1px solid #DDE3DF;border-radius:6px;padding:8px 10px;min-height:24mm}
.parties h4{margin:0 0 4px;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:#5A685F}
table{width:100%;border-collapse:collapse;font-size:11px}
th,td{border:1px solid #DDE3DF;padding:5px 6px;vertical-align:top}
th{background:#F4F7F4;font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:#44564F;text-align:left}
.num{text-align:right;white-space:nowrap}
.totals{margin-left:auto;width:62mm;margin-top:8px}
.totals td{border:none;padding:3px 0}
.totals .amt{text-align:right;white-space:nowrap}
.totals .grand td{border-top:1px solid #176B4D;font-weight:700;font-size:13px;padding-top:5px}
.words{margin-top:10px;font-size:11px;background:#F7F9F7;border:1px solid #E3E9E4;border-radius:5px;padding:7px 9px}
.foot{display:flex;justify-content:space-between;gap:18px;margin-top:14px;font-size:10.5px;color:#44564F}
.foot .box{flex:1}
.sign .line{margin-top:26px;border-top:1px solid #9FB0A8;display:block;padding-top:4px;text-align:center}
.foot .sign{flex:0 0 58mm;text-align:center;margin:0}
.note{margin-top:10px;font-size:10px;color:#5A685F}
.warn{max-width:190mm;margin:12px auto 0;background:#F7E7E3;border:1px solid #E7C4BC;color:#A6402F;padding:8px 12px;border-radius:8px;font-size:12px}
@media print{body{background:#fff}.toolbar,.warn{display:none}.sheet{box-shadow:none;margin:0;width:auto;min-height:0;padding:0}}
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
    "gear": '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="7" cy="18" r="2"/>',
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
        ("debit-notes", "inv", "Debit Notes"),
        ("vendors", "cust", "Vendors"),
    ]),
    ("Books", [
        ("daybook", "led", "Day Book"),
        ("journal", "led", "Journal"),
        ("bank-recon", "led", "Bank Recon"),
        ("ledger", "led", "Ledger"),
    ]),
    ("Reports", [
        ("reports/trial-balance", "rep", "Trial Balance"),
        ("reports/pnl", "rep", "Profit &amp; Loss"),
        ("reports/balance-sheet", "rep", "Balance Sheet"),
        ("reports/ar-ageing", "rep", "Receivables Ageing"),
        ("reports/ap-ageing", "rep", "Payables Ageing"),
        ("reports/gst", "rep", "GST Summary"),
        ("reports/gstr3b", "rep", "GSTR-3B"),
        ("gstr2b", "rep", "GSTR-2B Recon"),
    ]),
    ("Masters", [
        ("customers", "cust", "Customers"),
        ("items", "item", "Items"),
        ("users", "cust", "Team"),
        ("settings", "gear", "Settings"),
        ("backup", "audit", "Backups"),
        ("audit", "audit", "Audit Log"),
    ]),
]



STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan",
    "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand",
    "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory", "99": "Centre Jurisdiction",
}


def state_name(code: str, fallback: str = "") -> str:
    return STATES.get((code or "").strip(), fallback)


def state_options(selected: str) -> str:
    return "".join(
        f'<option value="{esc(code)}"{" selected" if code == selected else ""}>{esc(code)} &middot; {esc(name)}</option>'
        for code, name in STATES.items())


ROLE_CHOICES = [
    ("admin", "Admin", "Every business action except owner-only business settings"),
    ("manager", "Manager", "Sales, purchases, banking and reports"),
    ("accountant", "Accountant", "Books, GST, banking and reports"),
    ("cashier", "Cashier", "Receipts and customer balances"),
    ("sales", "Sales", "Invoices and customers"),
    ("inventory", "Inventory", "Items and stock"),
    ("readonly", "Read only", "View reports and documents"),
]
ROLE_LABELS = {role: label for role, label, _desc in ROLE_CHOICES}
ROLE_LABELS["owner"] = "Owner"


def role_options(selected: str = "readonly") -> str:
    return "".join(
        f'<option value="{esc(role)}"{" selected" if role == selected else ""}>{esc(label)}</option>'
        for role, label, _desc in ROLE_CHOICES)


def role_name(role: str) -> str:
    return ROLE_LABELS.get(role, role or "—")


def member_status_badge(status: str) -> str:
    cls = "ok" if status == "active" else ("bad" if status in ("suspended", "removed") else "neutral")
    return f'<span class="badge {cls}">{esc(status)}</span>'


def fiscal_start(today: date, start_month: int = 4) -> str:
    year = today.year if today.month >= start_month else today.year - 1
    return date(year, start_month, 1).isoformat()


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
               f'<a class="btn ghost small" href="/businesses" style="margin-left:10px">Businesses</a>'
               f'<form method="post" action="/logout" style="display:inline;margin-left:6px">'
               f'<button class="btn ghost small" type="submit">Sign out</button></form></div>')
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="description" content="ARTHIVIO private accounting workspace: double-entry books, GST working papers and financial statements.">
<title>{esc(title)} · {APP_NAME}</title><style>{CSS}</style></head>
<body><div class="shell">
<aside class="side">
  <div class="brand">{LOGO}<div><span class="name">ARTHIVIO</span><span class="tag">Smarter Finance</span></div></div>
  <nav class="nav">{''.join(nav)}</nav>
</aside>
<main class="main">
  <div class="top"><h1>{esc(title)}</h1>{who}</div>
  {body}
  <p class="footer-note">{APP_NAME} · amounts in INR · all figures derived from posted documents and journal entries.</p>
</main></div></body></html>"""


def login_page(error: str = "") -> str:
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="description" content="Sign in to your private ARTHIVIO accounting workspace.">
<title>Sign in · {APP_NAME}</title>
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

    def _base_url(self) -> str:
        fallback = f"127.0.0.1:{os.environ.get('PORT', '8000')}"
        host = (self.headers.get("Host") or fallback).strip()
        if not re.fullmatch(r"[A-Za-z0-9.:\-\[\]]+", host):
            host = fallback
        scheme = "https" if (self.headers.get("X-Forwarded-Proto") or "").lower() == "https" else "http"
        return f"{scheme}://{host}"

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
            invite_match = re.fullmatch(r"/invite/([A-Za-z0-9_-]{20,})", path)
            if invite_match:
                return self._send(self.page_invite_accept(conn, invite_match.group(1)),
                                  headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})
            share_match = re.fullmatch(r"/share/statement/([A-Za-z0-9_-]{20,})", path)
            if share_match:
                try:
                    body = self.page_statement_share(conn, share_match.group(1))
                except sharing.ShareError as e:
                    return self._send(self.page_share_error(e.message), 404,
                                      headers={"Cache-Control": "no-store",
                                               "X-Robots-Tag": "noindex, nofollow"})
                except acct.AccountingError:
                    return self._send(self.page_share_error("This statement is not available."), 404,
                                      headers={"Cache-Control": "no-store",
                                               "X-Robots-Tag": "noindex, nofollow"})
                return self._send(body, headers={"Cache-Control": "no-store",
                                                 "X-Robots-Tag": "noindex, nofollow"})

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
            if re.fullmatch(r"/invoices/[0-9a-f]{32}/print", path):
                return self._send(self.page_invoice_print(conn, user, tenant,
                                                          path.split("/")[2]))
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
                return self._send(self.page_customer_statement(conn, user, tenant, sess,
                                                               path.rsplit("/", 1)[1], q))
            if path == "/receipts":
                return self._send(self.page_receipts(conn, user, tenant, sess))
            if path == "/credit-notes":
                return self._send(self.page_credit_notes(conn, user, tenant))
            if path == "/debit-notes":
                return self._send(self.page_debit_notes(conn, user, tenant))
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
                return self._send(self.page_vendor_statement(conn, user, tenant, sess,
                                                             path.rsplit("/", 1)[1], q))
            if path == "/daybook":
                return self._send(self.page_daybook(conn, user, tenant, q))
            if path == "/journal":
                return self._send(self.page_journal(conn, user, tenant, sess))
            if path == "/bank-recon":
                return self._send(self.page_bank_recon(conn, user, tenant, sess, q))
            if path == "/reports/ar-ageing":
                return self._send(self.page_ageing(conn, user, tenant, q, "ar"))
            if path == "/reports/ap-ageing":
                return self._send(self.page_ageing(conn, user, tenant, q, "ap"))
            if path == "/reports/gst":
                return self._send(self.page_gst(conn, user, tenant, q))
            if path == "/reports/gstr3b":
                return self._send(self.page_gstr3b(conn, user, tenant, q))
            if path == "/gstr2b":
                return self._send(self.page_gstr2b(conn, user, tenant, sess, q))
            if path == "/export/gstr1.json":
                return self.export_gstr1_json(conn, user, tenant, q)
            if path.startswith("/export/"):
                return self.export_csv(conn, user, tenant, path, q)
            if path == "/items":
                return self._send(self.page_items(conn, user, tenant, sess))
            if path == "/audit":
                return self._send(self.page_audit(conn, user, tenant))
            if path == "/users":
                return self._send(self.page_users(conn, user, tenant, sess, q))
            if path == "/businesses":
                return self._send(self.page_businesses(conn, user, tenant, sess))
            if path == "/settings":
                return self._send(self.page_settings(conn, user, tenant, sess, q))
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

            invite_match = re.fullmatch(r"/invite/([A-Za-z0-9_-]{20,})", path)
            if invite_match:
                return self._accept_invite(conn, invite_match.group(1), form)

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

            if path == "/settings":
                return self._save_settings(conn, user, tenant, form)

            if path == "/switch":
                return self._switch_business(conn, user, sess, form)
            if path == "/users/invite":
                return self._invite_member(conn, user, tenant, form)
            if path == "/users/role":
                return self._change_member_role(conn, user, tenant, form)
            if path == "/users/status":
                return self._change_member_status(conn, user, tenant, form)
            if path == "/users/invite/revoke":
                return self._revoke_invite(conn, user, tenant, form)

            customer_share = re.fullmatch(r"/customers/([0-9a-f]{32})/share", path)
            if customer_share:
                return self._create_statement_share(conn, user, tenant, form,
                                                    "customer", customer_share.group(1))
            vendor_share = re.fullmatch(r"/vendors/([0-9a-f]{32})/share", path)
            if vendor_share:
                return self._create_statement_share(conn, user, tenant, form,
                                                    "vendor", vendor_share.group(1))
            if path == "/shares/revoke":
                return self._revoke_statement_share(conn, user, tenant, form)
            if path == "/gstr2b/import":
                return self._gstr2b_import(conn, user, tenant, form)
            if path == "/gstr2b/review":
                return self._gstr2b_review(conn, user, tenant, form)

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
            if path == "/debit-notes":
                return self._create_debit_note(conn, user, tenant, sess, form)
            if path == "/bank-recon/import":
                return self._bank_import(conn, user, tenant, sess, form)
            if path == "/bank-recon/auto-match":
                return self._bank_auto_match(conn, user, tenant, sess, form)
            if path == "/bank-recon/match":
                return self._bank_match(conn, user, tenant, sess, form)
            if path == "/bank-recon/unmatch":
                return self._bank_unmatch(conn, user, tenant, sess, form)
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
<a class="btn" href="/invoices/{esc(invoice_id)}/print" style="margin-left:8px">Print / PDF</a>
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

    def page_invoice_print(self, conn, user, tenant, invoice_id: str) -> str:
        try:
            br = acct.invoice_tax_breakup(conn, tenant["id"], invoice_id)
        except acct.AccountingError:
            return self._send(layout("Not found", '<div class="card pad">Invoice not found.</div>',
                                     "invoices", user, tenant), 404)
        inv, t, intra = br["invoice"], br["tenant"], br["intra"]
        hsn = {r["id"]: r["hsn"] for r in conn.execute(
            "SELECT id, hsn FROM item WHERE tenant_id=?", (tenant["id"],))}

        rows = []
        for idx, l in enumerate(br["lines"], 1):
            qty = f'{l["qty_milli"] / 1000:.3f}'.rstrip("0").rstrip(".")
            disc = money.fmt(l["discount_paise"]) if l["discount_paise"] else "&mdash;"
            if intra:
                tax_cells = (f'<td class="num">{money.fmt(l["cgst"])}</td>'
                             f'<td class="num">{money.fmt(l["sgst"])}</td>')
            else:
                tax_cells = f'<td class="num">{money.fmt(l["igst"])}</td>'
            rows.append(
                f'<tr><td class="num">{idx}</td><td>{esc(l["description"])}</td>'
                f'<td>{esc(hsn.get(l["item_id"]) or "&mdash;")}</td>'
                f'<td class="num">{qty}</td><td class="num">{money.fmt(l["unit_price_paise"])}</td>'
                f'<td class="num">{disc}</td><td class="num">{money.fmt(l["taxable_paise"])}</td>'
                f'<td class="num">{l["tax_rate_bp"] / 100:.2f}%</td>{tax_cells}'
                f'<td class="num">{money.fmt(l["line_total_paise"])}</td></tr>')

        tax_heads = ('<th class="num">CGST</th><th class="num">SGST</th>' if intra
                     else '<th class="num">IGST</th>')
        if intra:
            tax_total_rows = (f'<tr><td>CGST</td><td class="amt">{money.fmt(br["cgst"])}</td></tr>'
                              f'<tr><td>SGST</td><td class="amt">{money.fmt(br["sgst"])}</td></tr>')
        else:
            tax_total_rows = f'<tr><td>IGST</td><td class="amt">{money.fmt(br["igst"])}</td></tr>'

        pos = (f'{esc(inv["place_of_supply_state"])} &ndash; '
               f'{esc(state_name(inv["place_of_supply_state"]))}')
        seller_addr = ", ".join(x for x in [
            (t["address"] or "").strip(), (t["city"] or "").strip(),
            (f'{state_name(t["state_code"], t["state_name"])} {t["pincode"] or ""}').strip(),
        ] if x)
        buyer_addr = (inv["customer_address"] or "").strip()
        warn = ""
        if not (t["gstin"] or "").strip():
            warn = ('<div class="warn no-print">Supplier GSTIN is not set. Add it in '
                    '<a href="/settings">Settings</a> before sharing this as a tax invoice.</div>')
        bank = ""
        if (t["bank_name"] or "").strip() or (t["bank_account"] or "").strip():
            bank = (f'<div class="box"><b>Bank details</b><br>{esc(t["bank_name"])}<br>'
                    f'A/c {esc(t["bank_account"])}'
                    + (f'<br>IFSC {esc(t["bank_ifsc"])}' if t["bank_ifsc"] else "")
                    + '</div>')
        terms = ""
        if (t["invoice_terms"] or "").strip():
            terms = f'<div class="box"><b>Terms</b><br>{esc(t["invoice_terms"])}</div>'
        contact = " &nbsp;|&nbsp; ".join(x for x in [
            f'GSTIN: <b>{esc(t["gstin"])}</b>' if t["gstin"] else "",
            esc(t["phone"]) if t["phone"] else "",
            esc(t["email"]) if t["email"] else "",
        ] if x)

        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tax Invoice {esc(inv["invoice_no"])} &middot; {esc(t["name"])}</title>
<style>{PRINT_CSS}</style></head><body>
<div class="toolbar no-print">
  <a href="/invoices/{esc(inv["id"])}">Back to invoice</a>
  <button onclick="window.print()">Print / Save as PDF</button>
</div>
{warn}
<div class="sheet">
  <div class="head">
    <div>
      <div class="brand">{esc(t["name"])}</div>
      <div class="addr">{esc(seller_addr)}</div>
      <div class="addr">{contact}</div>
    </div>
    <div class="meta">
      <div class="doc">Tax Invoice</div>
      <div><b>{esc(inv["invoice_no"])}</b></div>
      <div>Date: {esc(inv["invoice_date"])}</div>
      <div>Place of supply: {pos}</div>
      <div>Reverse charge: N</div>
    </div>
  </div>
  <div class="parties">
    <div>
      <h4>Billed to</h4>
      <b>{esc(inv["customer_name"])}</b>
      {f'<div class="addr">{esc(buyer_addr)}</div>' if buyer_addr else ''}
      <div class="addr">GSTIN: {esc(inv["customer_gstin"]) if inv["customer_gstin"] else 'Unregistered'}</div>
      <div class="addr">State: {esc(inv["customer_state"])} &ndash; {esc(state_name(inv["customer_state"]))}</div>
    </div>
    <div>
      <h4>Supply &amp; tax</h4>
      <div class="addr">Type: {'Intra-state (CGST + SGST)' if intra else 'Inter-state (IGST)'}</div>
      <div class="addr">Taxable value: {money.fmt(inv["sub_total_paise"])}</div>
      <div class="addr">GST: {money.fmt(inv["tax_paise"])}</div>
      <div class="addr">Invoice total: <b>{money.fmt(inv["total_paise"])}</b></div>
    </div>
  </div>
  <table>
    <thead><tr><th class="num">#</th><th>Description</th><th>HSN/SAC</th><th class="num">Qty</th>
      <th class="num">Rate</th><th class="num">Discount</th><th class="num">Taxable</th>
      <th class="num">GST %</th>{tax_heads}<th class="num">Amount</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <div class="totals"><table>
    <tr><td>Taxable value</td><td class="amt">{money.fmt(inv["sub_total_paise"])}</td></tr>
    {tax_total_rows}
    <tr><td>Round off</td><td class="amt">{money.fmt(inv["round_off_paise"])}</td></tr>
    <tr class="grand"><td>Invoice total</td><td class="amt">{money.fmt(inv["total_paise"])}</td></tr>
  </table></div>
  <div class="words"><b>Amount in words:</b> {esc(money.amount_in_words(inv["total_paise"]))}</div>
  <div class="foot">
    {bank}{terms}
    <div class="sign"><div>For {esc(t["name"])}</div><div class="line">Authorised signatory</div></div>
  </div>
  <div class="note">Computer-generated tax invoice. Posted entries are immutable; corrections are made by credit note.</div>
</div>
</body></html>"""

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

    def page_debit_notes(self, conn, user, tenant) -> str:
        rows = conn.execute(
            "SELECT n.*, v.name, b.bill_no FROM debit_note n"
            " JOIN vendor v ON v.id=n.vendor_id LEFT JOIN bill b ON b.id=n.bill_id"
            " WHERE n.tenant_id=? ORDER BY n.note_date DESC, n.note_no DESC", (tenant["id"],)).fetchall()
        trs = ""
        for r in rows:
            bill_ref = (f'<a href="/bills/{esc(r["bill_id"])}">{esc(r["bill_no"])}</a>'
                        if r["bill_id"] else "—")
            trs += (f'<tr><td>{esc(r["note_no"])}</td><td>{esc(r["note_date"])}</td>'
                    f'<td>{esc(r["name"])}</td><td>{bill_ref}</td>'
                    f'<td>{esc(r["reason"])}</td>'
                    f'<td class="num">{money.fmt(r["total_paise"])}</td></tr>')
        trs = trs or '<tr><td colspan="6" class="empty">No debit notes yet. Open a bill to raise one.</td></tr>'
        body = f"""
<div class="sect-head"><h2>{len(rows)} debit note(s)</h2><a class="btn ghost" href="/export/debit-notes.csv">Export CSV</a></div>
<div class="card"><table><thead><tr><th>Note</th><th>Date</th><th>Vendor</th><th>Bill</th><th>Reason</th><th class="num">Total</th></tr></thead>
<tbody>{trs}</tbody></table></div>
<p class="small muted" style="margin-top:12px">A debit note reverses purchase value and input GST, takes stock out at the bill's purchase value, and reduces the vendor payable. The original bill is never edited.</p>"""
        return layout("Debit notes", body, "debit-notes", user, tenant)

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
        dn_lines = []
        for l in lines:
            returned = conn.execute(
                "SELECT COALESCE(SUM(dnl.qty_milli),0) q FROM debit_note_line dnl"
                " JOIN debit_note dn ON dn.id=dnl.debit_note_id"
                " WHERE dn.tenant_id=? AND dn.bill_id=? AND dnl.bill_line_id=?",
                (tenant["id"], bill_id, l["id"])).fetchone()["q"]
            remaining = l["qty_milli"] - returned
            if remaining > 0:
                dn_lines.append((l, remaining))
        dn_opts = "".join(
            f'<option value="{l["id"]}">{esc(l["description"])} — {rem/1000:.3f} returnable</option>'
            for l, rem in dn_lines)
        debit_form = ""
        if dn_opts:
            debit_form = f"""
<div class="card pad sect"><h2 style="margin-bottom:12px">Debit note / purchase return</h2>
<form method="post" action="/debit-notes">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="bill_id" value="{esc(bill_id)}">
<div class="row c4">
<div class="field"><label>Date</label><input type="date" name="note_date" value="{date.today().isoformat()}"></div>
<div class="field" style="grid-column:span 2"><label>Bill line</label><select name="bill_line_id">{dn_opts}</select></div>
<div class="field"><label>Quantity</label><input name="qty" value="1" inputmode="decimal"></div>
</div>
<div class="field"><label>Reason</label><input name="reason" required maxlength="200" placeholder="Damaged / short supply / return to vendor"></div>
<button class="btn ghost" type="submit">Post debit note</button>
</form></div>"""

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
{debit_form}
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

    def page_vendor_statement(self, conn, user, tenant, sess, vendor_id: str, q) -> str:
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
            elif r["source_type"] == "debit_note":
                ref = f'<a href="/debit-notes">{esc(r["ref"])}</a>'
            rows += (f'<tr><td>{esc(r["date"])}</td><td>{ref}</td><td>{esc(r["narration"])}</td>'
                     f'<td class="num">{money.fmt(r["debit"]) if r["debit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["credit"]) if r["credit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["balance"])}</td></tr>')
        rows = rows or '<tr><td colspan="6" class="empty">No transactions in this period</td></tr>'
        share_card = self._statement_share_card(conn, user, tenant, sess, "vendor", vendor_id,
                                                dfrom, dto, q)
        body = f"""
<div class="kpis">
  {kpi("Billed (period)", money.fmt(st["billed"]), "credits to payable")}
  {kpi("Paid (period)", money.fmt(st["paid"]), "payments to vendor")}
  {kpi("Debit notes (period)", money.fmt(st["debited"]), "purchase returns")}
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
{share_card}
<p class="small muted">Vendor: {esc(v["name"])} · state {esc(v["state_code"])} · GSTIN {esc(v["gstin"] or "—")}</p>"""
        return layout(f'Vendor — {v["name"]}', body, "vendors", user, tenant)

    def page_daybook(self, conn, user, tenant, q) -> str:
        today = date.today()
        dfrom = (q.get("from") or [f"{today.year}-04-01"])[0]
        dto = (q.get("to") or [today.isoformat()])[0]
        entries = acct.day_book(conn, tenant["id"], dfrom, dto)
        links = {"invoice": "/invoices/", "bill": "/bills/", "credit_note": "/credit-notes",
                 "debit_note": "/debit-notes", "receipt": "/receipts", "payment": "/receipts"}
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

    def page_bank_recon(self, conn, user, tenant, sess, q) -> str:
        today = date.today()
        dfrom = (q.get("from") or [fiscal_start(today, tenant["fiscal_year_start_month"])])[0]
        dto = (q.get("to") or [today.isoformat()])[0]
        accounts = bank_mod.bank_accounts(conn, tenant["id"])
        if not accounts:
            body = ('<div class="card pad"><div class="err">No bank account (code 1010) exists in this '
                    'business chart of accounts.</div></div>')
            return layout("Bank reconciliation", body, "bank-recon", user, tenant)
        account_id = (q.get("account") or [accounts[0]["id"]])[0]
        if account_id not in {a["id"] for a in accounts}:
            account_id = accounts[0]["id"]
        try:
            rec = bank_mod.reconciliation(conn, tenant["id"], account_id, dfrom, dto)
            all_ledger = bank_mod.ledger_candidates(conn, tenant["id"], account_id)
        except bank_mod.BankError as e:
            body = f'<div class="card pad"><div class="err">{esc(e.message)}</div></div>'
            return layout("Bank reconciliation", body, "bank-recon", user, tenant)

        imported = (q.get("imported") or [""])[0]
        dupes = (q.get("duplicates") or ["0"])[0]
        banner = ""
        if imported:
            banner = (f'<div class="card pad" style="margin-bottom:14px"><span class="badge ok">'
                      f'Imported {esc(imported)} new line(s)</span> '
                      f'<span class="small muted">{esc(dupes)} duplicate(s) skipped</span></div>')
        matched_msg = (q.get("matched") or [""])[0]
        ambiguous_msg = (q.get("ambiguous") or [""])[0]
        if matched_msg:
            if ambiguous_msg:
                banner += (f'<div class="card pad" style="margin-bottom:14px"><span class="badge ok">'
                           f'Auto-match: {esc(matched_msg)} matched</span> '
                           f'<span class="small muted">{esc(ambiguous_msg)} ambiguous line(s) left for manual review</span></div>')
            else:
                banner += (f'<div class="card pad" style="margin-bottom:14px"><span class="badge ok">'
                           f'{esc(matched_msg)} statement line(s) matched</span></div>')
        if (q.get("unmatched") or [""])[0]:
            banner += ('<div class="card pad" style="margin-bottom:14px"><span class="badge neutral">'
                       'Match removed</span></div>')

        def signed_stmt(r):
            return r["credit_paise"] - r["debit_paise"]

        def signed_line(r):
            return r["debit_paise"] - r["credit_paise"]

        stmt_rows = ""
        for r in rec["statement"]:
            if r["status"] == "matched":
                match_info = (f'<span class="badge ok">Matched</span>'
                              f'<div class="small muted">{esc(r["ledger_date"] or "")} · '
                              f'{esc(r["entry_no"] or "")} · {esc(r["narration"] or "")}</div>')
                action = f"""
<form method="post" action="/bank-recon/unmatch">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="statement_id" value="{esc(r['id'])}">
<input type="hidden" name="account_id" value="{esc(account_id)}">
<input type="hidden" name="from" value="{esc(dfrom)}">
<input type="hidden" name="to" value="{esc(dto)}">
<button class="btn ghost small" type="submit">Unmatch</button></form>"""
            else:
                match_info = '<span class="badge bad">Unmatched</span>'
                candidates = [l for l in all_ledger
                              if signed_line(l) == signed_stmt(r)]
                candidates.sort(key=lambda l: abs((date.fromisoformat(l["entry_date"])
                                                    - date.fromisoformat(r["txn_date"])).days))
                if candidates:
                    opts = "".join(
                        f'<option value="{esc(l["line_id"])}">{esc(l["entry_date"])} · '
                        f'{esc(l["entry_no"])} · {esc((l["narration"] or "")[:52])} · '
                        f'{money.fmt(abs(signed_line(l)))}</option>' for l in candidates[:25])
                    action = f"""
<form method="post" action="/bank-recon/match" style="display:flex;gap:6px;align-items:center;min-width:290px">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="statement_id" value="{esc(r['id'])}">
<input type="hidden" name="account_id" value="{esc(account_id)}">
<input type="hidden" name="from" value="{esc(dfrom)}">
<input type="hidden" name="to" value="{esc(dto)}">
<select name="journal_line_id" style="min-width:220px">{opts}</select>
<button class="btn small" type="submit">Match</button></form>"""
                else:
                    action = '<span class="small muted">No ledger line with this amount</span>'
            stmt_rows += (f'<tr><td>{esc(r["txn_date"])}</td><td>{esc(r["description"])}'
                          f'<div class="small muted">{esc(r["reference"] or "")}</div></td>'
                          f'<td class="num">{money.fmt(r["debit_paise"]) if r["debit_paise"] else ""}</td>'
                          f'<td class="num">{money.fmt(r["credit_paise"]) if r["credit_paise"] else ""}</td>'
                          f'<td>{match_info}</td><td>{action}</td></tr>')
        stmt_rows = stmt_rows or ('<tr><td colspan="6" class="empty">No statement lines in this period. '
                                  'Import a CSV above.</td></tr>')

        ledger_rows = ""
        for l in rec["unmatched_ledger"]:
            ledger_rows += (f'<tr><td>{esc(l["entry_date"])}</td><td>{esc(l["entry_no"])}</td>'
                            f'<td>{esc(l["source_type"])}</td><td>{esc(l["narration"])}</td>'
                            f'<td class="num">{money.fmt(l["debit_paise"]) if l["debit_paise"] else ""}</td>'
                            f'<td class="num">{money.fmt(l["credit_paise"]) if l["credit_paise"] else ""}</td></tr>')
        ledger_rows = ledger_rows or '<tr><td colspan="6" class="empty">Every ledger entry in this period is matched.</td></tr>'

        last = bank_mod.latest_import(conn, tenant["id"], account_id)
        last_note = ""
        if last:
            last_note = (f'<span class="small muted">Last import: {esc(last["created_at"][:19].replace("T", " "))} '
                         f'· {last["rows_imported"]} new / {last["rows_duplicate"]} duplicate</span>')
        acct_opts = "".join(
            f'<option value="{a["id"]}" {"selected" if a["id"] == account_id else ""}>'
            f'{esc(a["code"])} — {esc(a["name"])}</option>' for a in accounts)
        closing = rec["closing_ledger"]
        stmt_balance = rec["latest_statement_balance"]
        balance_note = ""
        if stmt_balance is not None:
            balance_note = (f'<tr><td>Statement closing balance</td>'
                            f'<td class="num">{money.fmt(stmt_balance)}</td></tr>')
        diff_badge = "ok" if rec["difference"] == 0 else "bad"
        export_qs = urllib.parse.urlencode({"account": account_id, "from": dfrom, "to": dto})

        body = f"""
{banner}
<div class="kpis">
  {kpi("Statement net", money.fmt(rec["statement_net"]), f'{rec["statement_count"]} line(s)')}
  {kpi("Ledger net", money.fmt(rec["ledger_net"]), f'{len(rec["unmatched_ledger"])} unmatched ledger line(s)')}
  {kpi("Unmatched statement", money.fmt(rec["unmatched_net"]), f'{rec["unmatched_count"]} line(s)')}
  {kpi("Difference", money.fmt(rec["difference"]), "ledger minus statement")}
</div>
<form method="get" action="/bank-recon" class="card pad sect">
<div class="row c4">
<div class="field"><label>Bank account</label><select name="account">{acct_opts}</select></div>
<div class="field"><label>From</label><input type="date" name="from" value="{esc(dfrom)}"></div>
<div class="field"><label>To</label><input type="date" name="to" value="{esc(dto)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
</div></form>
<div class="card pad sect">
<div class="sect-head"><h2 style="margin-bottom:0">Import bank statement</h2>{last_note}</div>
<form method="post" action="/bank-recon/import">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="account_id" value="{esc(account_id)}">
<input type="hidden" name="filename" id="filename" value="">
<div class="field"><label>CSV file</label><input type="file" id="csvfile" accept=".csv,text/csv"></div>
<div class="field"><label>Or paste CSV</label><textarea name="csv_text" id="csv_text" rows="5" placeholder="Date,Description,Reference,Debit,Credit,Balance&#10;2026-06-01,NEFT CR SUNDARAM,NEFT-88421,,23600.00,523600.00"></textarea></div>
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
<button class="btn" type="submit">Import statement</button>
<span class="small muted">Columns: Date, Description, Reference, Debit, Credit (or Amount + Dr/Cr). Duplicate rows are skipped.</span>
</div></form>
<script>
document.getElementById('csvfile').addEventListener('change', function (e) {{
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = function () {{
    document.getElementById('csv_text').value = reader.result;
    document.getElementById('filename').value = f.name;
  }};
  reader.readAsText(f);
}});
</script></div>
<div class="sect-head"><h2>Reconciliation</h2>
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
<a class="btn ghost small" href="/export/bank-statement.csv?{esc(export_qs)}">Export statement CSV</a>
<form method="post" action="/bank-recon/auto-match">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="account_id" value="{esc(account_id)}">
<input type="hidden" name="from" value="{esc(dfrom)}">
<input type="hidden" name="to" value="{esc(dto)}">
<button class="btn ghost" type="submit">Auto-match unambiguous</button></form></div></div>
<div class="card sect"><table>
<thead><tr><th>Date</th><th>Statement description</th><th class="num">Debit (out)</th><th class="num">Credit (in)</th><th>Status / match</th><th>Action</th></tr></thead>
<tbody>{stmt_rows}</tbody></table></div>
<div class="grid2 sect">
<div class="card"><div class="pad"><h2>Ledger entries not matched</h2>
<p class="small muted" style="margin:4px 0 0">Only posted journal lines on this bank account are shown.</p></div>
<table><thead><tr><th>Date</th><th>Voucher</th><th>Type</th><th>Narration</th><th class="num">In</th><th class="num">Out</th></tr></thead>
<tbody>{ledger_rows}</tbody></table></div>
<div class="card"><div class="pad"><h2>Reconciliation summary</h2></div>
<table><tbody>
<tr><td>Opening ledger balance</td><td class="num">{money.fmt(rec["opening_ledger"])}</td></tr>
<tr><td>Ledger movement (period)</td><td class="num">{money.fmt(rec["ledger_net"])}</td></tr>
<tr><td>Closing ledger balance</td><td class="num"><b>{money.fmt(closing)}</b></td></tr>
{balance_note}
<tr><td>Matched statement net</td><td class="num">{money.fmt(rec["matched_net"])}</td></tr>
<tr><td>Unmatched statement net</td><td class="num">{money.fmt(rec["unmatched_net"])}</td></tr>
<tr><td>Unmatched ledger net</td><td class="num">{money.fmt(rec["unmatched_ledger_net"])}</td></tr>
<tr><td>Difference</td><td class="num"><span class="badge {diff_badge}">{money.fmt(rec["difference"])}</span></td></tr>
</tbody></table>
<p class="small muted" style="padding:0 20px 16px">A zero difference means every bank movement in this period is represented by a ledger entry. Unmatched statement lines may need a journal entry (for example bank charges or interest); this build does not auto-post them.</p>
</div></div>
<p class="small muted">Reconciliation matches equal amounts only. The date window for suggestions is ±7 days; manual match lets you pick any ledger line with the same amount. Matching never changes a journal entry.</p>"""
        return layout("Bank reconciliation", body, "bank-recon", user, tenant)

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
        dfrom = (q.get("from") or [fiscal_start(today, tenant["fiscal_year_start_month"])])[0]
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
</div>
<div class="row c4" style="margin-top:2px">
<div class="field" style="grid-column:span 4;display:flex;align-items:flex-end;gap:8px;flex-wrap:wrap">
<a class="btn ghost" href="/export/gstr1.csv?from={esc(dfrom)}&amp;to={esc(dto)}">GSTR-1 CSV</a>
<a class="btn ghost" href="/export/gstr1.json?from={esc(dfrom)}&amp;to={esc(dto)}">GSTR-1 JSON</a>
<a class="btn ghost" href="/reports/gstr3b?month={esc(dto[:7])}">GSTR-3B working</a>
<span class="small muted">B2B + B2C small + HSN summary for this period</span>
</div></div></form>
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
<p class="small muted">Working summary, not a filed return. Input tax is net of debit notes; GSTR-1 export lists invoices (B2B + B2C small) and credit notes separately, while this page shows net GST after credit notes. Verify with your tax professional before filing.</p>"""
        return layout("GST summary", body, "reports/gst", user, tenant)

    def page_gstr3b(self, conn, user, tenant, q) -> str:
        today = date.today()
        month = (q.get("month") or [today.strftime("%Y-%m")])[0]
        try:
            g = acct.gstr3b_data(conn, tenant["id"], month)
        except acct.AccountingError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    f'<p class="small muted" style="margin:12px 0 0">Use a month in YYYY-MM format.</p>'
                    f'<p><a class="btn" href="/reports/gstr3b">Current month</a></p></div>')
            return layout("GSTR-3B", body, "reports/gstr3b", user, tenant)

        out = g["outward"]
        itc = g["itc"]
        pay = g["payment"]
        checks = g["reconciliation"]["checks"]
        check_rows = "".join(
            f'<tr><td>{esc(c["label"])}</td>'
            f'<td class="num">{money.fmt(c["expected"])}</td>'
            f'<td class="num">{money.fmt(c["actual"])}</td>'
            f'<td class="num">{money.fmt(c["difference"])}</td>'
            f'<td><span class="badge {"ok" if c["status"] == "ok" else "bad"}">'
            f'{"OK" if c["status"] == "ok" else "CHECK"}</span></td></tr>'
            for c in checks)
        warnings = "".join(f"<li>{esc(w)}</li>" for w in g["warnings"])
        warning_card = ""
        if warnings:
            warning_card = (f'<div class="card pad sect"><h2>Checks and warnings</h2>'
                            f'<ul class="small" style="margin:8px 0 0 18px;line-height:1.7">{warnings}</ul></div>')

        outward_rows = f"""
<tr><td>3.1(a)</td><td>Outward taxable supplies (other than zero-rated, nil-rated and exempted) &mdash; net of credit notes</td>
<td class="num">{money.fmt(out["taxable_net"])}</td><td class="num">{money.fmt(out["output_net"]["IGST"])}</td>
<td class="num">{money.fmt(out["output_net"]["CGST"])}</td><td class="num">{money.fmt(out["output_net"]["SGST"])}</td></tr>
<tr><td>3.1(b)</td><td>Outward taxable supplies (zero-rated)</td>
<td class="num">{money.fmt(out["zero_rated"])}</td><td class="num">{money.fmt(0)}</td>
<td class="num">{money.fmt(0)}</td><td class="num">{money.fmt(0)}</td></tr>
<tr><td>3.1(c)</td><td>Other outward supplies (nil-rated, exempted)</td>
<td class="num">{money.fmt(out["nil_exempt"])}</td><td class="num">{money.fmt(0)}</td>
<td class="num">{money.fmt(0)}</td><td class="num">{money.fmt(0)}</td></tr>
<tr><td>3.1(d)</td><td>Inward supplies liable to reverse charge</td>
<td class="num">{money.fmt(out["rcm_inward"])}</td><td class="num">{money.fmt(0)}</td>
<td class="num">{money.fmt(0)}</td><td class="num">{money.fmt(0)}</td></tr>
<tr><td>3.1(e)</td><td>Non-GST outward supplies</td>
<td class="num">{money.fmt(out["non_gst"])}</td><td class="num">{money.fmt(0)}</td>
<td class="num">{money.fmt(0)}</td><td class="num">{money.fmt(0)}</td></tr>
"""

        itc_rows = f"""
<tr><td>4(A)(5)</td><td>All other ITC &mdash; purchase bills</td>
<td class="num">{money.fmt(itc["gross"]["IGST"])}</td><td class="num">{money.fmt(itc["gross"]["CGST"])}</td>
<td class="num">{money.fmt(itc["gross"]["SGST"])}</td><td class="num">{money.fmt(itc["gross_total"])}</td></tr>
<tr><td>4(B)(2)</td><td>ITC reversal &mdash; debit notes / purchase returns</td>
<td class="num">{money.fmt(itc["reversal"]["IGST"])}</td><td class="num">{money.fmt(itc["reversal"]["CGST"])}</td>
<td class="num">{money.fmt(itc["reversal"]["SGST"])}</td><td class="num">{money.fmt(itc["reversal_total"])}</td></tr>
<tr><td></td><td><b>Net eligible ITC</b></td>
<td class="num"><b>{money.fmt(itc["net"]["IGST"])}</b></td><td class="num"><b>{money.fmt(itc["net"]["CGST"])}</b></td>
<td class="num"><b>{money.fmt(itc["net"]["SGST"])}</b></td><td class="num"><b>{money.fmt(itc["net_total"])}</b></td></tr>
<tr><td>4(A)(1)</td><td>Import of goods</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">{money.fmt(0)}</td></tr>
<tr><td>4(A)(2)</td><td>Import of services</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">{money.fmt(0)}</td></tr>
<tr><td>4(A)(3)</td><td>Inward supplies liable to reverse charge</td><td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">{money.fmt(0)}</td></tr>
"""

        pay_rows = "".join(
            f'<tr><td>{esc(h["head"])}</td>'
            f'<td class="num">{money.fmt(h["output"])}</td>'
            f'<td class="num">{money.fmt(h["itc_available"])}</td>'
            f'<td class="num">{money.fmt(h["itc_used"])}</td>'
            f'<td class="num"><b>{money.fmt(h["cash_payable"])}</b></td>'
            f'<td class="num">{money.fmt(h["itc_balance"])}</td></tr>'
            for h in pay["heads"])
        carry_note = ""
        if pay["output_carry_total"]:
            carry_note = (f'<p class="small muted" style="padding:0 20px 12px">Output tax carried '
                          f'forward (credit notes exceed invoices): '
                          f'{money.fmt(pay["output_carry_total"])}</p>')
        excess_note = ""
        if pay["excess_reversal_total"]:
            excess_note = (f'<p class="small muted" style="padding:0 20px 12px">ITC reversal in '
                           f'excess of available ITC, shown as payable: '
                           f'{money.fmt(pay["excess_reversal_total"])}</p>')

        body = f"""
<form method="get" class="card pad sect">
<div class="row c4">
<div class="field"><label for="month_filter">Month</label><input id="month_filter" type="month" name="month" value="{esc(month)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
<div class="field" style="display:flex;align-items:flex-end"><a class="btn ghost" href="/export/gstr3b.csv?month={esc(month)}">Export CSV</a></div>
<div class="field" style="display:flex;align-items:flex-end"><a class="btn ghost" href="/reports/gst?from={esc(g["period"]["from"])}&amp;to={esc(g["period"]["to"])}">GST summary</a></div>
</div></form>
<div class="kpis">
  {kpi("Net taxable", money.fmt(out["taxable_net"]), f'{g["docs"]["invoices"]} invoice(s) less credit notes')}
  {kpi("Output tax", money.fmt(out["output_total"]), "net of credit notes")}
  {kpi("Eligible ITC", money.fmt(itc["net_total"]), "purchase bills less debit notes")}
  {kpi("Cash payable", money.fmt(pay["cash_payable_total"]), "head-wise, no cross-utilisation")}
</div>
<div class="sect-head"><h2>3.1 Outward supplies</h2>
<span class="badge neutral">{esc(g["period"]["from"])} → {esc(g["period"]["to"])}</span></div>
<div class="card"><table>
<thead><tr><th>#</th><th>Description</th><th class="num">Taxable value</th><th class="num">IGST</th><th class="num">CGST</th><th class="num">SGST</th></tr></thead>
<tbody>{outward_rows}</tbody></table></div>
<div class="sect-head"><h2>4. Eligible ITC</h2><span class="small muted">Input tax credit, net of purchase returns</span></div>
<div class="card"><table>
<thead><tr><th>#</th><th>Description</th><th class="num">IGST</th><th class="num">CGST</th><th class="num">SGST</th><th class="num">Total</th></tr></thead>
<tbody>{itc_rows}</tbody></table></div>
<div class="sect-head"><h2>5. Payment of tax</h2><span class="small muted">Working set-off, not a challan</span></div>
<div class="card"><table>
<thead><tr><th>Head</th><th class="num">Output tax</th><th class="num">ITC available</th><th class="num">ITC utilised</th><th class="num">Cash payable</th><th class="num">ITC balance</th></tr></thead>
<tbody>{pay_rows}</tbody>
<tfoot><tr><td><b>Total</b></td><td class="num"><b>{money.fmt(pay["output_total"])}</b></td>
<td class="num"><b>{money.fmt(pay["itc_available_total"])}</b></td>
<td class="num"><b>{money.fmt(pay["itc_used_total"])}</b></td>
<td class="num"><b>{money.fmt(pay["cash_payable_total"])}</b></td>
<td class="num"><b>{money.fmt(pay["itc_balance_total"])}</b></td></tr></tfoot></table>
{carry_note}{excess_note}</div>
<div class="sect-head"><h2>Reconciliation checks</h2>
<span class="badge {"ok" if g["reconciliation"]["failed"] == 0 else "bad"}">{len(checks) - g["reconciliation"]["failed"]}/{len(checks)} OK</span></div>
<div class="card"><table>
<thead><tr><th>Check</th><th class="num">Expected</th><th class="num">Actual</th><th class="num">Difference</th><th>Status</th></tr></thead>
<tbody>{check_rows}</tbody></table></div>
{warning_card}
<div class="card pad small muted" style="margin-top:16px">{esc(g["note"])}</div>
"""
        return layout("GSTR-3B", body, "reports/gstr3b", user, tenant)

    def page_gstr2b(self, conn, user, tenant, sess, q, error: str = "") -> str:
        today = date.today()
        month = (q.get("month") or [today.strftime("%Y-%m")])[0]
        try:
            g = gstr2b_mod.reconcile(conn, tenant["id"], month)
        except gstr2b_mod.Gstr2bError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    '<p class="small muted" style="margin:12px 0">Use a month in YYYY-MM format.</p>'
                    '<a class="btn" href="/gstr2b">Current month</a></div>')
            return layout("GSTR-2B reconciliation", body, "gstr2b", user, tenant)
        try:
            security.require(conn, user["id"], tenant["id"], "gst.reconcile")
            can_import = True
        except security.AuthError:
            can_import = False

        comparison = (gstr2b_mod.itc_comparison(conn, tenant["id"], month, g)
                      if g["import"] else None)
        imported = g["import"]
        notices = []
        if error:
            notices.append(f'<div class="err">{esc(error)}</div>')
        duplicate = (q.get("duplicate") or [""])[0] == "1"
        imported_count = (q.get("imported") or ["0"])[0]
        if imported_count and imported_count != "0" and not duplicate:
            notices.append('<div class="card pad" style="margin-bottom:14px"><span class="badge ok">Imported</span> '
                           f'{esc(imported_count)} GSTR-2B row(s) added for this month.</div>')
        if duplicate:
            notices.append('<div class="card pad" style="margin-bottom:14px"><span class="badge neutral">Duplicate</span> '
                           f'This exact file was already imported for {esc(month)}. No rows were added.</div>')
        if (q.get("reviewed") or [""])[0] == "1":
            notices.append('<div class="card pad" style="margin-bottom:14px"><span class="badge ok">Review saved</span> '
                           'The ITC review state was updated; the books and 2B amounts were not changed.</div>')
        notice_html = "".join(notices)

        import_card = ""
        if can_import:
            import_card = f"""
<div class="card pad sect">
<div class="sect-head"><h2 style="margin-bottom:0">Import GSTR-2B working CSV</h2>
<span class="small muted">Latest active import wins for the month</span></div>
<form method="post" action="/gstr2b/import">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="month" value="{esc(month)}">
<input type="hidden" name="filename" id="gstr2b_filename" value="">
<div class="field"><label for="gstr2b_file">CSV file</label><input type="file" id="gstr2b_file" accept=".csv,text/csv"></div>
<div class="field"><label for="gstr2b_text">Or paste CSV</label><textarea name="csv_text" id="gstr2b_text" rows="6" placeholder="Supplier GSTIN,Supplier Name,Invoice No,Invoice Date,Taxable Value,IGST,CGST,SGST,Cess,Invoice Value&#10;27AAACL1234C1Z5,Loom House Pvt Ltd,LH-2026-097,2026-08-10,42000.00,0,3780.00,3780.00,0,49560.00"></textarea></div>
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
<button class="btn" type="submit">Import GSTR-2B</button>
<span class="small muted">Expected columns: GSTIN, invoice no, invoice date, taxable value, IGST, CGST, SGST. This is a working reconciliation aid, not the portal's official schema.</span>
</div></form>
<script>
document.getElementById('gstr2b_file').addEventListener('change', function (e) {{
  var f = e.target.files && e.target.files[0]; if (!f) return;
  var reader = new FileReader();
  reader.onload = function (ev) {{
    document.getElementById('gstr2b_text').value = ev.target.result;
    document.getElementById('gstr2b_filename').value = f.name;
  }};
  reader.readAsText(f);
}});
</script>
</div>"""
        else:
            import_card = ('<div class="card pad sect"><div class="err">Only owner, admin, manager or '
                           'accountant can import GSTR-2B files.</div></div>')

        if not imported:
            summary_html = f"""
<div class="card pad sect">
<h2>No GSTR-2B import yet</h2>
<p class="small muted" style="margin:8px 0 0">Import the working CSV for {esc(month)} to compare portal ITC with posted purchase bills. Nothing is posted or changed in the books.</p>
</div>"""
            history = ""
        else:
            s = g["summary"]
            warning_items = "".join(f"<li>{esc(w)}</li>" for w in g["warnings"])
            warning_card = ""
            if warning_items:
                warning_card = (f'<div class="card pad sect"><h2>Exceptions</h2>'
                                f'<ul class="small" style="margin:8px 0 0 18px;line-height:1.7">{warning_items}</ul></div>')
            status_badge = {"matched": ("ok", "MATCHED"), "mismatch": ("bad", "CHECK"),
                            "missing_in_books": ("bad", "MISSING IN BOOKS"),
                            "unmatched": ("neutral", "UNMATCHED")}
            review_cls = {"open": "neutral", "follow_up": "bad",
                          "itc_hold": "bad", "accepted": "ok"}

            def review_control(r):
                head = (f'<span class="badge {review_cls.get(r["review_status"], "neutral")}">'
                        f'{esc(r["review_label"])}</span>')
                if r["review_note"]:
                    head += (f'<div class="small muted" style="margin-top:3px">'
                             f'{esc(r["review_note"])}</div>')
                if not can_import:
                    return head
                options = "".join(
                    f'<option value="{s}" {"selected" if r["review_status"] == s else ""}>'
                    f'{esc(gstr2b_mod.REVIEW_LABELS[s])}</option>'
                    for s in gstr2b_mod.REVIEW_STATUSES)
                return (head + f"""
<details class="review-form"><summary>Update review</summary>
<form method="post" action="/gstr2b/review">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="line_id" value="{esc(r['id'])}">
<input type="hidden" name="month" value="{esc(month)}">
<select name="status" aria-label="ITC review status for invoice {esc(r['invoice_no'])}">{options}</select>
<input name="note" maxlength="500" value="{esc(r['review_note'])}" placeholder="Follow-up note">
<button class="btn small ghost" type="submit">Save review</button>
</form></details>""")

            line_rows = ""
            for r in g["rows"]:
                cls, label = status_badge.get(r["match_status"], ("neutral", r["match_status"]))
                bill = (f'<a href="/bills/{esc(r["matched_bill_id"])}">{esc(r["bill_no"])}</a>'
                        if r["matched_bill_id"] else '<span class="muted">—</span>')
                line_rows += f"""<tr>
<td><b>{esc(r["supplier_name"] or r["supplier_gstin"] or "—")}</b><div class="small muted">{esc(r["supplier_gstin"] or "GSTIN missing")}</div></td>
<td>{esc(r["invoice_no"])}<div class="small muted">{esc(r["invoice_date"])}</div></td>
<td class="num">{money.fmt(r["taxable_paise"])}</td>
<td class="num">{money.fmt(r["igst_paise"])}</td>
<td class="num">{money.fmt(r["cgst_paise"])}</td>
<td class="num">{money.fmt(r["sgst_paise"])}</td>
<td><span class="badge {cls}">{label}</span><div class="small muted">{esc(r["note"])}</div></td>
<td class="review-cell">{review_control(r)}</td>
<td>{bill}</td></tr>"""
            line_rows = line_rows or '<tr><td colspan="9" class="empty">No GSTR-2B rows</td></tr>'
            book_rows = ""
            for b in g["books"]:
                book_rows += f"""<tr>
<td>{esc(b["bill_no"])}<div class="small muted">{esc(b["bill_date"])}</div></td>
<td>{esc(b["vendor_name"])}<div class="small muted">{esc(b["vendor_gstin"] or "GSTIN missing")}</div></td>
<td>{esc(b["vendor_bill_no"] or "—")}</td>
<td class="num">{money.fmt(b["sub_total_paise"])}</td>
<td class="num">{money.fmt(b["igst_book"])}</td>
<td class="num">{money.fmt(b["cgst_book"])}</td>
<td class="num">{money.fmt(b["sgst_book"])}</td>
<td class="small muted">{esc(b["note"])}</td></tr>"""
            book_rows = book_rows or '<tr><td colspan="8" class="empty">No posted bills missing from GSTR-2B</td></tr>'
            history_rows = "".join(
                f'<tr><td>{esc(h["created_at"][:19].replace("T", " "))}</td>'
                f'<td>{esc(h["period"])}</td><td class="num">{h["rows_total"]}</td>'
                f'<td class="num">{money.fmt(h["tax_paise"])}</td>'
                f'<td><span class="badge {"ok" if h["status"] == "active" else "neutral"}">{esc(h["status"])}</span></td>'
                f'<td class="small muted">{esc(h["filename"] or "pasted CSV")}</td></tr>'
                for h in gstr2b_mod.import_history(conn, tenant["id"], month)) or \
                '<tr><td colspan="6" class="empty">No imports for this month</td></tr>'
            comparison_html = ""
            if comparison:
                cmp_cls = "ok" if comparison["status"] == "ok" else "bad"
                cmp_label = "AMOUNT OK" if comparison["status"] == "ok" else "AMOUNT CHECK"
                comparison_html = f"""
<div class="card sect">
<div class="sect-head"><h2>GSTR-3B ITC vs GSTR-2B</h2>
<span class="badge {cmp_cls}">{cmp_label}</span></div>
<table>
<thead><tr><th>ITC comparison</th><th class="num">Tax</th><th class="num">Lines</th></tr></thead>
<tbody>
<tr><td>GSTR-3B eligible ITC (net of debit notes)</td><td class="num">{money.fmt(comparison["books_itc"])}</td><td class="num">—</td></tr>
<tr><td>GSTR-3B ITC before debit-note reversal</td><td class="num">{money.fmt(comparison["books_itc_gross"])}</td><td class="num">—</td></tr>
<tr><td>Debit-note ITC reversal</td><td class="num">{money.fmt(comparison["books_itc_reversal"])}</td><td class="num">—</td></tr>
<tr><td>GSTR-2B ITC</td><td class="num">{money.fmt(comparison["two_b_itc"])}</td><td class="num">{s["two_b"]["count"]}</td></tr>
<tr><td><b>2B minus 3B eligible ITC</b></td><td class="num"><b>{money.fmt(comparison["difference"])}</b></td><td class="num">—</td></tr>
<tr><td>Accepted in review</td><td class="num">{money.fmt(comparison["accepted"]["tax"])}</td><td class="num">{comparison["accepted"]["count"]}</td></tr>
<tr><td>On ITC hold</td><td class="num">{money.fmt(comparison["hold"]["tax"])}</td><td class="num">{comparison["hold"]["count"]}</td></tr>
<tr><td>Supplier follow-up</td><td class="num">{money.fmt(comparison["follow_up"]["tax"])}</td><td class="num">{comparison["follow_up"]["count"]}</td></tr>
<tr><td>Open review</td><td class="num">{money.fmt(comparison["open_review"]["tax"])}</td><td class="num">{comparison["open_review"]["count"]}</td></tr>
</tbody></table>
<div class="small muted" style="margin-top:8px">3B eligible ITC is net of debit notes; GSTR-2B is gross for the month. This is a working comparison, not a filed return.</div>
</div>"""
            summary_html = f"""
<div class="kpis">
  {kpi("ITC in GSTR-2B", money.fmt(s["itc_available"]), f'{s["two_b"]["count"]} portal line(s)')}
  {kpi("ITC in posted bills", money.fmt(s["itc_claimed"]), f'{s["books"]["count"]} bill(s) this month')}
  {kpi("Matched", str(s["matched"]["count"]), money.fmt(s["matched"]["tax"]) + " tax")}
  {kpi("Differences", str(s["mismatch"]["count"] + s["missing_in_books"]["count"] + s["missing_in_2b"]["count"]), "mismatch + missing")}
  {kpi("Open reviews", str(s["review"]["open"]["count"]), "need a decision")}
  {kpi("ITC on hold", money.fmt(s["review"]["itc_hold"]["tax"]), f'{s["review"]["itc_hold"]["count"]} line(s)')}
</div>
<div class="card sect"><table>
<thead><tr><th>Reconciliation</th><th class="num">Taxable</th><th class="num">Tax</th><th class="num">Count</th></tr></thead>
<tbody>
<tr><td>GSTR-2B import</td><td class="num">{money.fmt(s["two_b"]["taxable"])}</td><td class="num">{money.fmt(s["two_b"]["tax"])}</td><td class="num">{s["two_b"]["count"]}</td></tr>
<tr><td>Posted purchase bills in month</td><td class="num">{money.fmt(s["books"]["taxable"])}</td><td class="num">{money.fmt(s["books"]["tax"])}</td><td class="num">{s["books"]["count"]}</td></tr>
<tr><td>Matched lines</td><td class="num">{money.fmt(s["matched"]["taxable"])}</td><td class="num">{money.fmt(s["matched"]["tax"])}</td><td class="num">{s["matched"]["count"]}</td></tr>
<tr><td>Amount mismatches</td><td class="num">{money.fmt(s["mismatch"]["taxable"])}</td><td class="num">{money.fmt(s["mismatch"]["tax"])}</td><td class="num">{s["mismatch"]["count"]}</td></tr>
<tr><td>In GSTR-2B, missing in books</td><td class="num">{money.fmt(s["missing_in_books"]["taxable"])}</td><td class="num">{money.fmt(s["missing_in_books"]["tax"])}</td><td class="num">{s["missing_in_books"]["count"]}</td></tr>
<tr><td>In books, missing in GSTR-2B</td><td class="num">{money.fmt(s["missing_in_2b"]["taxable"])}</td><td class="num">{money.fmt(s["missing_in_2b"]["tax"])}</td><td class="num">{s["missing_in_2b"]["count"]}</td></tr>
</tbody>
<tfoot><tr><td>2B tax minus books tax</td><td class="num">—</td><td class="num">{money.fmt(s["difference"])}</td><td class="num">—</td></tr></tfoot>
</table></div>
{comparison_html}
{warning_card}
<div class="sect-head"><h2>GSTR-2B lines</h2>
<span class="small muted">Matched by supplier GSTIN + normalised invoice number; amounts are not corrected</span></div>
<div class="card table-wrap"><table>
<thead><tr><th>Supplier</th><th>Invoice</th><th class="num">Taxable</th><th class="num">IGST</th><th class="num">CGST</th><th class="num">SGST</th><th>Status</th><th>ITC review</th><th>Bill</th></tr></thead>
<tbody>{line_rows}</tbody></table></div>
<div class="sect-head"><h2>Posted bills missing in GSTR-2B</h2>
<span class="small muted">Bills dated inside this month that were not matched</span></div>
<div class="card"><table>
<thead><tr><th>Bill</th><th>Vendor</th><th>Vendor invoice</th><th class="num">Taxable</th><th class="num">IGST</th><th class="num">CGST</th><th class="num">SGST</th><th>Note</th></tr></thead>
<tbody>{book_rows}</tbody></table></div>
<div class="card pad sect"><h2>Import history</h2><table>
<thead><tr><th>Imported (UTC)</th><th>Month</th><th class="num">Rows</th><th class="num">Tax</th><th>Status</th><th>File</th></tr></thead>
<tbody>{history_rows}</tbody></table></div>"""

        body = f"""
<form method="get" class="card pad sect">
<div class="row c4">
<div class="field"><label for="month_filter">Month</label><input id="month_filter" type="month" name="month" value="{esc(month)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
<div class="field" style="display:flex;align-items:flex-end"><a class="btn ghost" href="/export/gstr2b.csv?month={esc(month)}">Export CSV</a></div>
<div class="field" style="display:flex;align-items:flex-end"><a class="btn ghost" href="/reports/gst?from={esc(g["period"]["from"])}&amp;to={esc(g["period"]["to"])}">GST summary</a></div>
</div></form>
{notice_html}
{summary_html}
{import_card}
<div class="card pad small muted">GSTR-2B reconciliation is a working aid. It compares the file you imported with posted purchase bills and never auto-posts ITC, edits bills, or files a return. Verify exceptions with your tax professional before claiming ITC.</div>
"""
        return layout("GSTR-2B reconciliation", body, "gstr2b", user, tenant)

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

    def page_customer_statement(self, conn, user, tenant, sess, customer_id: str, q) -> str:
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
        share_card = self._statement_share_card(conn, user, tenant, sess, "customer", customer_id,
                                                dfrom, dto, q)
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
{share_card}
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

    def page_settings(self, conn, user, tenant, sess, q) -> str:
        try:
            security.require(conn, user["id"], tenant["id"], "tenant.manage")
            can_edit = True
        except security.AuthError:
            can_edit = False
        if not can_edit:
            body = f"""
<div class="card pad sect"><div class="err">Only the business owner can change these details.</div>
<p class="small muted" style="margin:0">GSTIN, address and bank details are used on tax invoices and in
GST exports. Ask the owner to update them.</p></div>
<div class="card pad"><table>
<tr><td>Business name</td><td><b>{esc(tenant["name"])}</b></td></tr>
<tr><td>GSTIN</td><td>{esc(tenant["gstin"]) or '<span class="muted">Not set</span>'}</td></tr>
<tr><td>GST state</td><td>{esc(tenant["state_code"])} &ndash; {esc(state_name(tenant["state_code"]))}</td></tr>
<tr><td>Address</td><td>{esc(tenant["address"])}</td></tr>
<tr><td>City / PIN</td><td>{esc(tenant["city"])} {esc(tenant["pincode"])}</td></tr>
<tr><td>Phone / email</td><td>{esc(tenant["phone"])} {esc(tenant["email"])}</td></tr>
<tr><td>Bank</td><td>{esc(tenant["bank_name"])} {esc(tenant["bank_account"])} {esc(tenant["bank_ifsc"])}</td></tr>
</table></div>"""
            return layout("Settings", body, "settings", user, tenant)

        saved = ('<div class="badge ok" style="margin-bottom:12px">Settings saved</div>'
                 if q.get("saved") else "")
        gstin_note = ("" if (tenant["gstin"] or "").strip() else
                      '<div class="err" style="margin-bottom:14px">GSTIN is not set. Invoices will print '
                      'a warning and GSTR-1 exports will flag it until you add it.</div>')
        body = f"""
{saved}{gstin_note}
<div class="card pad sect">
<h2 style="margin-bottom:4px">Business identity</h2>
<p class="small muted" style="margin:0 0 14px">These details appear on tax invoices and GST exports.
Changing them never alters posted entries.</p>
<form method="post" action="/settings">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="row c3">
  <div class="field"><label>Legal / trade name</label><input name="name" required maxlength="120" value="{esc(tenant['name'])}"></div>
  <div class="field"><label>GSTIN</label><input name="gstin" maxlength="15" placeholder="27ABCDE1234F1Z5" value="{esc(tenant['gstin'])}"></div>
  <div class="field"><label>GST state</label><select name="state_code">{state_options(tenant['state_code'])}</select></div>
</div>
<div class="field"><label>Address</label><textarea name="address" rows="2" maxlength="240" placeholder="Shop / building, street, area">{esc(tenant['address'])}</textarea></div>
<div class="row c3">
  <div class="field"><label>City</label><input name="city" maxlength="60" value="{esc(tenant['city'])}"></div>
  <div class="field"><label>PIN code</label><input name="pincode" maxlength="6" inputmode="numeric" value="{esc(tenant['pincode'])}"></div>
  <div class="field"><label>Phone</label><input name="phone" maxlength="24" value="{esc(tenant['phone'])}"></div>
</div>
<div class="field"><label>Email</label><input name="email" type="email" maxlength="120" value="{esc(tenant['email'])}"></div>
<h3 style="margin:18px 0 10px">Bank details (printed on invoices)</h3>
<div class="row c3">
  <div class="field"><label>Bank</label><input name="bank_name" maxlength="80" value="{esc(tenant['bank_name'])}"></div>
  <div class="field"><label>Account number</label><input name="bank_account" maxlength="34" value="{esc(tenant['bank_account'])}"></div>
  <div class="field"><label>IFSC</label><input name="bank_ifsc" maxlength="11" placeholder="HDFC0001234" value="{esc(tenant['bank_ifsc'])}"></div>
</div>
<div class="field"><label>Invoice terms / notes</label><textarea name="invoice_terms" rows="2" maxlength="300" placeholder="Payment due within 15 days.">{esc(tenant['invoice_terms'])}</textarea></div>
<button class="btn" type="submit">Save settings</button>
</form></div>
<div class="card pad small muted">Fiscal year starts in month {tenant['fiscal_year_start_month']:02d}.
Currency {esc(tenant['currency'])}. GSTIN, PIN code and IFSC are validated on save.</div>"""
        return layout("Settings", body, "settings", user, tenant)

    def _settings_error(self, user, tenant, message: str):
        body = (f'<div class="card pad"><div class="err">{esc(message)}</div>'
                '<a class="btn ghost" href="/settings">Back to settings</a></div>')
        return self._send(layout("Settings", body, "settings", user, tenant), 400)

    def _save_settings(self, conn, user, tenant, form):
        try:
            security.require(conn, user["id"], tenant["id"], "tenant.manage")
        except security.AuthError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    '<a class="btn ghost" href="/settings">Back</a></div>')
            return self._send(layout("Forbidden", body, "settings", user, tenant), 403)

        name = first(form, "name").strip()
        if not name:
            return self._settings_error(user, tenant, "Business name is required.")
        gstin = first(form, "gstin").strip().upper()
        if gstin and not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]", gstin):
            return self._settings_error(
                user, tenant, "GSTIN must be 15 characters, e.g. 27ABCDE1234F1Z5.")
        state_code = first(form, "state_code") or tenant["state_code"]
        if state_code not in STATES:
            return self._settings_error(user, tenant, "Choose a valid GST state.")
        pincode = first(form, "pincode").strip()
        if pincode and not re.fullmatch(r"[1-9][0-9]{5}", pincode):
            return self._settings_error(user, tenant, "PIN code must be 6 digits.")
        email = first(form, "email").strip()
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return self._settings_error(user, tenant, "Enter a valid email address.")
        ifsc = first(form, "bank_ifsc").strip().upper()
        if ifsc and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", ifsc):
            return self._settings_error(user, tenant, "IFSC must be 11 characters, e.g. HDFC0001234.")

        conn.execute(
            "UPDATE tenant SET name=?, gstin=?, state_code=?, state_name=?, address=?, city=?,"
            " pincode=?, phone=?, email=?, bank_name=?, bank_account=?, bank_ifsc=?, invoice_terms=?"
            " WHERE id=?",
            (name[:120], gstin, state_code, state_name(state_code),
             first(form, "address").strip()[:240], first(form, "city").strip()[:60], pincode,
             first(form, "phone").strip()[:24], email[:120], first(form, "bank_name").strip()[:80],
             first(form, "bank_account").strip()[:34], ifsc,
             first(form, "invoice_terms").strip()[:300], tenant["id"]))
        acct.audit(conn, tenant["id"], user["id"], "tenant.settings_updated", "tenant", tenant["id"])
        return self._redirect("/settings?saved=1")

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

    def page_users(self, conn, user, tenant, sess, q, error: str = "") -> str:
        try:
            security.require(conn, user["id"], tenant["id"], "user.invite")
            can_invite = True
        except security.AuthError:
            can_invite = False
        try:
            security.require(conn, user["id"], tenant["id"], "role.assign")
            can_assign = True
        except security.AuthError:
            can_assign = False
        if not can_invite and not can_assign:
            return layout("Team", '<div class="card pad"><div class="err">Only the owner or an admin can manage team members.</div>'
                                  '<p class="small muted" style="margin:0">Ask the business owner for access.</p></div>',
                          "users", user, tenant)

        members = security.list_members(conn, tenant["id"])
        member_rows = ""
        for m in members:
            is_self = m["user_id"] == user["id"]
            is_owner = m["role"] == "owner"
            if is_owner or is_self or not can_assign:
                role_cell = (f'<span class="badge neutral">{esc(role_name(m["role"]))}</span>'
                             + (' <span class="small muted">You</span>' if is_self else ""))
            else:
                role_cell = f"""<form method="post" action="/users/role" style="display:flex;gap:6px;align-items:center">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="user_id" value="{esc(m["user_id"])}">
<select name="role" aria-label="Role for {esc(m['full_name'])}" style="min-width:130px">{role_options(m["role"])}</select>
<button class="btn small ghost" type="submit">Save</button></form>"""
            actions = '<span class="small muted">Protected</span>' if is_owner else (
                '<span class="small muted">You</span>' if is_self else "")
            if can_assign and not is_owner and not is_self:
                action_forms = []
                if m["member_status"] == "active":
                    action_forms.append(
                        f'<form method="post" action="/users/status" style="display:inline">'
                        f'<input type="hidden" name="_csrf" value="{esc(sess["csrf_token"])}">'
                        f'<input type="hidden" name="user_id" value="{esc(m["user_id"])}">'
                        f'<input type="hidden" name="status" value="suspended">'
                        f'<button class="btn small ghost" type="submit">Suspend</button></form>')
                else:
                    action_forms.append(
                        f'<form method="post" action="/users/status" style="display:inline">'
                        f'<input type="hidden" name="_csrf" value="{esc(sess["csrf_token"])}">'
                        f'<input type="hidden" name="user_id" value="{esc(m["user_id"])}">'
                        f'<input type="hidden" name="status" value="active">'
                        f'<button class="btn small ghost" type="submit">Reactivate</button></form>')
                if m["member_status"] != "removed":
                    action_forms.append(
                        f'<form method="post" action="/users/status" style="display:inline;margin-left:4px">'
                        f'<input type="hidden" name="_csrf" value="{esc(sess["csrf_token"])}">'
                        f'<input type="hidden" name="user_id" value="{esc(m["user_id"])}">'
                        f'<input type="hidden" name="status" value="removed">'
                        f'<button class="btn small ghost" type="submit">Remove</button></form>')
                actions = " ".join(action_forms)
            member_rows += (f'<tr><td><b>{esc(m["full_name"] or "—")}</b><div class="small muted">{esc(m["email"])}</div></td>'
                            f'<td>{role_cell}</td><td>{member_status_badge(m["member_status"])}</td>'
                            f'<td>{actions}</td></tr>')
        member_rows = member_rows or '<tr><td colspan="4" class="empty">No team members</td></tr>'

        invites = security.list_invites(conn, tenant["id"])
        invite_rows = ""
        for inv in invites:
            if inv["status"] == "pending":
                actions = (f'<form method="post" action="/users/invite/revoke" style="display:inline">'
                           f'<input type="hidden" name="_csrf" value="{esc(sess["csrf_token"])}">'
                           f'<input type="hidden" name="invite_id" value="{esc(inv["id"])}">'
                           f'<button class="btn small ghost" type="submit">Revoke</button></form>')
            else:
                actions = '<span class="small muted">—</span>'
            invite_rows += (f'<tr><td><b>{esc(inv["email"])}</b><div class="small muted">{esc(inv["full_name"] or "")}</div></td>'
                            f'<td>{esc(role_name(inv["role"]))}</td>'
                            f'<td><span class="badge {"neutral" if inv["status"] != "pending" else "ok"}">{esc(inv["status"])}</span></td>'
                            f'<td class="small">{esc(inv["expires_at"][:16].replace("T", " "))}</td>'
                            f'<td>{actions}</td></tr>')
        invite_rows = invite_rows or '<tr><td colspan="5" class="empty">No invites yet</td></tr>'

        error_html = f'<div class="err">{esc(error)}</div>' if error else ""
        notice = (q.get("invited") or [""])[0]
        notice_html = ('<div class="card pad" style="margin-bottom:14px"><span class="badge ok">Invite created</span> '
                       'Copy the one-time link from the previous screen and send it to the member.</div>') if notice else ""
        if (q.get("saved") or [""])[0]:
            notice_html += ('<div class="card pad" style="margin-bottom:14px"><span class="badge ok">Team updated</span> '
                            'The change is active and recorded in the audit log.</div>')
        if (q.get("revoked") or [""])[0]:
            notice_html += ('<div class="card pad" style="margin-bottom:14px"><span class="badge neutral">Invite revoked</span> '
                            'The link can no longer be used.</div>')
        invite_form = ""
        if can_invite:
            invite_form = f"""
<div class="card pad sect">
<div class="sect-head"><h2 style="margin-bottom:0">Invite a team member</h2>
<span class="small muted">Link expires in 7 days</span></div>
{error_html}
<form method="post" action="/users/invite">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="row c2">
<div class="field"><label>Work email</label><input type="email" name="email" required maxlength="120" placeholder="name@business.in"></div>
<div class="field"><label>Full name</label><input name="full_name" maxlength="120" placeholder="As it should appear in the app"></div>
</div>
<div class="row c2">
<div class="field"><label for="invite_role">Role</label><select id="invite_role" name="role">{role_options("readonly")}</select></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Create invite link</button></div>
</div>
<p class="small muted" style="margin:0">ARTHIVIO does not send email in this build. The invite link is shown once after creation; copy it and share it securely. Existing ARTHIVIO users join with their current password.</p>
</form></div>"""

        body = f"""
{notice_html}
<div class="kpis">
  {kpi("Team members", str(len(members)), "active and suspended")}
  {kpi("Pending invites", str(sum(1 for i in invites if i["status"] == "pending")), "expire after 7 days")}
</div>
<div class="card sect"><table>
<thead><tr><th>Member</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead>
<tbody>{member_rows}</tbody></table></div>
<div class="card sect"><table>
<thead><tr><th>Invite</th><th>Role</th><th>Status</th><th>Expires (UTC)</th><th>Actions</th></tr></thead>
<tbody>{invite_rows}</tbody></table></div>
{invite_form}
<div class="card pad small muted">The owner role is protected and cannot be reassigned here. A suspended or removed member loses access immediately; their sessions are revoked. Every invite and role change is written to the audit log.</div>
"""
        return layout("Team", body, "users", user, tenant)

    def page_businesses(self, conn, user, tenant, sess) -> str:
        rows = security.tenants_for(conn, user["id"])
        trs = ""
        for r in rows:
            current = r["id"] == tenant["id"]
            action = ('<span class="badge ok">Current</span>' if current else
                      f'<form method="post" action="/switch" style="display:inline">'
                      f'<input type="hidden" name="_csrf" value="{esc(sess["csrf_token"])}">'
                      f'<input type="hidden" name="tenant_id" value="{esc(r["id"])}">'
                      f'<button class="btn small ghost" type="submit">Switch</button></form>')
            trs += (f'<tr><td><b>{esc(r["name"])}</b><div class="small muted">{esc(r["slug"])}</div></td>'
                    f'<td>{esc(role_name(r["role"]))}</td>'
                    f'<td>{esc(r["gstin"] or "—")}</td><td>{action}</td></tr>')
        body = f"""
<div class="card sect"><table>
<thead><tr><th>Business</th><th>Your role</th><th>GSTIN</th><th></th></tr></thead>
<tbody>{trs or '<tr><td colspan="4" class="empty">No active businesses</td></tr>'}</tbody></table></div>
<div class="card pad small muted">A switch changes the business for this session only. Your access is checked again against your active membership.</div>
"""
        return layout("Businesses", body, "businesses", user, tenant)

    def page_invite_created(self, user, tenant, result, link: str) -> str:
        body = f"""
<div class="card pad sect">
<div class="sect-head"><h2 style="margin-bottom:0">Invite ready for {esc(result["email"])}</h2>
<span class="badge ok">{esc(role_name(result["role"]))}</span></div>
<p class="small">Send this one-time link to the member. It expires on <b>{esc(result["expires_at"][:16].replace("T", " "))} UTC</b> and is shown only once.</p>
<div class="field"><label>One-time invite link</label>
<input readonly value="{esc(link)}" onclick="this.select()" style="font-family:ui-monospace,monospace;font-size:13px"></div>
<div style="display:flex;gap:8px;flex-wrap:wrap">
<a class="btn" href="{esc(link)}" target="_blank" rel="noopener">Open invite page</a>
<a class="btn ghost" href="/users">Back to team</a>
</div>
</div>
<div class="card pad small muted">If the email already had an ARTHIVIO login, the member will be asked for their current password. New users create a password of at least 12 characters. The link can be revoked from the Team page before it is used.</div>
"""
        return layout("Invite created", body, "users", user, tenant)

    def page_invite_accept(self, conn, token: str, error: str = "") -> str:
        try:
            invite = security.invite_by_token(conn, token)
        except security.AuthError as e:
            return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Invite unavailable · {APP_NAME}</title><style>{CSS}</style></head>
<body><div class="login-wrap"><div class="login card pad">
<div class="brandline">{LOGO}<div><div style="font-weight:700;letter-spacing:.06em">ARTHIVIO</div>
<div class="small muted">Team invitation</div></div></div>
<div class="err">{esc(e.message)}</div>
<p class="small muted">Ask the business owner for a fresh invite link.</p>
<a class="btn ghost" href="/login">Go to sign in</a>
</div></div></body></html>"""
        existing = invite["existing_user"]
        err = f'<div class="err">{esc(error)}</div>' if error else ""
        password_label = "Current password" if existing else "Create password (12+ characters)"
        password_hint = ("Enter the password for your existing ARTHIVIO login. "
                         "Your password is not changed.") if existing else "Use at least 12 characters."
        confirm = "" if existing else """
<div class="field"><label>Confirm password</label><input type="password" name="confirm" required autocomplete="new-password"></div>"""
        note = (f'<div class="card pad small" style="background:#F7F9F7;margin-bottom:14px">'
                f'<b>{esc(invite["email"])}</b> already has an ARTHIVIO login. Enter its current password to join '
                f'<b>{esc(invite["tenant_name"])}</b> as {esc(role_name(invite["role"]))}.</div>') if existing else (
                f'<div class="card pad small" style="background:#F7F9F7;margin-bottom:14px">'
                f'You are joining <b>{esc(invite["tenant_name"])}</b> as {esc(role_name(invite["role"]))}. '
                f'Use this email as your login.</div>')
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Join {esc(invite["tenant_name"])} · {APP_NAME}</title><style>{CSS}</style></head>
<body><div class="login-wrap"><div class="login card pad">
<div class="brandline">{LOGO}<div><div style="font-weight:700;letter-spacing:.06em">ARTHIVIO</div>
<div class="small muted">Team invitation</div></div></div>
<h1 style="font-size:23px;margin-bottom:6px">Join {esc(invite["tenant_name"])}</h1>
<p class="small muted" style="margin-top:0">This invite is for <b>{esc(invite["email"])}</b>.</p>
{note}{err}
<form method="post" action="/invite/{esc(token)}">
<div class="field"><label>Full name</label><input name="full_name" value="{esc(invite["full_name"])}" maxlength="120" required></div>
<div class="field"><label>{password_label}</label><input type="password" name="password" required autocomplete="{'current-password' if existing else 'new-password'}">
<div class="small muted" style="margin-top:4px">{password_hint}</div></div>
{confirm}
<button class="btn" type="submit" style="width:100%">Accept invite</button>
</form>
<p class="small muted" style="margin-bottom:0">Already a member? <a href="/login">Sign in</a>.</p>
</div></div></body></html>"""

    def page_share_error(self, message: str) -> str:
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Statement unavailable · {APP_NAME}</title><style>{CSS}</style></head>
<body><div class="login-wrap"><div class="login card pad">
<div class="brandline">{LOGO}<div><div style="font-weight:700;letter-spacing:.06em">ARTHIVIO</div>
<div class="small muted">Shared statement</div></div></div>
<div class="err">{esc(message)}</div>
<p class="small muted">Ask the business that shared this statement for a fresh link.</p>
<a class="btn ghost" href="/login">ARTHIVIO sign in</a>
</div></div></body></html>"""

    def page_statement_share(self, conn, token: str) -> str:
        resolved = sharing.resolve_statement_share(conn, token)
        share = resolved["share"]
        tenant = resolved["tenant"]
        st = resolved["statement"]
        is_customer = share["party_type"] == "customer"
        party = st["customer"] if is_customer else st["vendor"]
        rows = ""
        for r in st["rows"]:
            rows += (f'<tr><td>{esc(r["date"])}</td><td>{esc(r["ref"])}</td><td>{esc(r["narration"])}</td>'
                     f'<td class="num">{money.fmt(r["debit"]) if r["debit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["credit"]) if r["credit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["balance"])}</td></tr>')
        rows = rows or '<tr><td colspan="6" style="text-align:center;color:#5A685F;padding:18px">No transactions in this period</td></tr>'
        business_addr = ", ".join(x for x in (tenant["address"], tenant["city"], tenant["state_name"],
                                              tenant["pincode"]) if x)
        party_addr = ", ".join(x for x in (party.get("address", ""), state_name(party.get("state_code", ""))) if x)
        heading = "Statement of account" if is_customer else "Vendor account statement"
        counterparty = "Customer" if is_customer else "Vendor"
        closing_label = "Amount due from customer" if is_customer else "Amount payable to vendor"
        extra_css = """
.stmt-title{margin:0 0 2px;font-size:18px;font-weight:700;color:#123F2E}
.stmt-period{font-size:11px;color:#44564F;margin-top:2px}
.stmt-note{margin-top:10px;font-size:10px;color:#5A685F}
.stmt-total td{font-weight:700;border-top:2px solid #176B4D}
.stmt-toolbar{justify-content:space-between;align-items:center}
.stmt-toolbar .tag{font-size:11px;color:#5A685F;letter-spacing:.03em}
"""
        return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<meta name="description" content="Shared statement of account issued by {esc(tenant["name"])} from ARTHIVIO.">
<title>{esc(heading)} · {esc(tenant["name"])}</title><style>{PRINT_CSS}{extra_css}</style></head>
<body>
<div class="toolbar stmt-toolbar"><span class="tag">Shared statement · {esc(tenant["name"])}</span>
<div><a href="/login">ARTHIVIO</a> &nbsp; <button type="button" onclick="window.print()">Print / Save PDF</button></div></div>
<main class="sheet">
  <div class="head">
    <div><div class="brand">{esc(tenant["name"])}</div>
      <div class="addr">{esc(business_addr) or "Address not set"}</div>
      <div class="addr">GSTIN {esc(tenant["gstin"] or "—")} &nbsp;·&nbsp; {esc(tenant["phone"] or "")} {esc(tenant["email"] or "")}</div>
    </div>
    <div class="meta"><div class="doc">{esc(heading)}</div>
      <div class="addr">{esc(share["date_from"])} to {esc(share["date_to"])}</div>
      <div class="addr">Issued {esc(share["created_at"][:10])}</div>
    </div>
  </div>
  <div class="parties">
    <div><h4>{counterparty}</h4><b>{esc(party["name"])}</b>
      <div class="addr">{esc(party_addr) or "Address not recorded"}</div>
      <div class="addr">GSTIN {esc(party.get("gstin") or "—")} &nbsp;·&nbsp; {esc(party.get("phone") or "")}</div></div>
    <div><h4>Statement summary</h4>
      <div class="small">Opening balance: <b>{money.fmt(st["opening"])}</b></div>
      <div class="small">Closing balance: <b>{money.fmt(st["closing"])}</b></div>
      <div class="addr">{esc(closing_label)}</div></div>
  </div>
  <table>
    <thead><tr><th>Date</th><th>Reference</th><th>Particulars</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th></tr></thead>
    <tbody>
      <tr><td colspan="5" style="color:#5A685F">Opening balance</td><td class="num"><b>{money.fmt(st["opening"])}</b></td></tr>
      {rows}
    </tbody>
    <tfoot><tr class="stmt-total"><td colspan="5">Closing balance</td><td class="num">{money.fmt(st["closing"])}</td></tr></tfoot>
  </table>
  <div class="words"><b>Closing balance in words:</b> {esc(money.amount_in_words(st["closing"]))}</div>
  <div class="foot">
    <div class="box"><b>{esc(tenant["name"])}</b><div class="addr">{esc(tenant["bank_name"] or "")} {esc(tenant["bank_account"] or "")} {esc(tenant["bank_ifsc"] or "")}</div>
      <div class="stmt-note">This is a computer-generated statement from ARTHIVIO. It is shared as a read-only link and expires on {esc(share["expires_at"][:10])}.</div></div>
    <div class="sign"><span class="line">Authorised signatory</span></div>
  </div>
</main>
</body></html>"""

    def _statement_share_card(self, conn, user, tenant, sess, party_type: str, party_id: str,
                              dfrom: str, dto: str, q) -> str:
        try:
            security.require(conn, user["id"], tenant["id"], "statement.share")
        except security.AuthError:
            return ""
        token = (q.get("share") or [""])[0]
        shared = ""
        if token:
            link = f"{self._base_url()}/share/statement/{token}"
            shared = f"""
<div class="card pad" style="margin:0 0 14px;background:#F7F9F7">
<div class="sect-head" style="margin-bottom:6px"><b>Share link created</b><span class="badge ok">Shown once</span></div>
<div class="field" style="margin-bottom:8px"><input readonly value="{esc(link)}" onclick="this.select()" style="font-family:ui-monospace,monospace;font-size:13px"></div>
<div style="display:flex;gap:8px;flex-wrap:wrap"><a class="btn small" href="{esc(link)}" target="_blank" rel="noopener">Open print view</a>
<span class="small muted" style="align-self:center">Copy this link now. It cannot be shown again.</span></div></div>"""
        shares = sharing.list_statement_shares(conn, tenant["id"], party_type, party_id)
        share_rows = ""
        for s in shares:
            revoke = ""
            if s["link_status"] == "active":
                revoke = (f'<form method="post" action="/shares/revoke" style="display:inline">'
                          f'<input type="hidden" name="_csrf" value="{esc(sess["csrf_token"])}">'
                          f'<input type="hidden" name="share_id" value="{esc(s["id"])}">'
                          f'<input type="hidden" name="party_type" value="{esc(party_type)}">'
                          f'<input type="hidden" name="party_id" value="{esc(party_id)}">'
                          f'<input type="hidden" name="from" value="{esc(dfrom)}">'
                          f'<input type="hidden" name="to" value="{esc(dto)}">'
                          f'<button class="btn small ghost" type="submit">Revoke</button></form>')
            cls = "ok" if s["link_status"] == "active" else "neutral"
            share_rows += (f'<tr><td>{esc(s["date_from"])} → {esc(s["date_to"])}</td>'
                           f'<td>{esc(s["created_at"][:10])}</td><td>{esc(s["expires_at"][:10])}</td>'
                           f'<td><span class="badge {cls}">{esc(s["link_status"])}</span></td>'
                           f'<td class="num">{s["view_count"]}</td><td>{revoke}</td></tr>')
        share_rows = share_rows or '<tr><td colspan="6" class="empty">No share links yet</td></tr>'
        return f"""
<div class="card pad sect">
<div class="sect-head"><h2 style="margin-bottom:0">Share and print</h2>
<span class="small muted">Read-only link · no sign-in needed</span></div>
{shared}
<form method="post" action="/{party_type}s/{esc(party_id)}/share">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="from" value="{esc(dfrom)}">
<input type="hidden" name="to" value="{esc(dto)}">
<div class="row c3">
<div class="field"><label>Link validity</label><select name="days"><option value="7">7 days</option><option value="30" selected>30 days</option><option value="90">90 days</option></select></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Create share link</button></div>
<div class="field" style="display:flex;align-items:flex-end"><span class="small muted">Opens a print-ready statement. Revoke any time.</span></div>
</div></form>
<table><thead><tr><th>Period</th><th>Created</th><th>Expires</th><th>Status</th><th class="num">Views</th><th></th></tr></thead>
<tbody>{share_rows}</tbody></table>
</div>"""

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


    # ---------------- actions: team, sharing, GSTR-2B ----------------
    def _accept_invite(self, conn, token: str, form):
        password = first(form, "password")
        confirm = first(form, "confirm")
        try:
            invite = security.invite_by_token(conn, token)
            if not invite["existing_user"] and password != confirm:
                raise security.AuthError("PASSWORD_MISMATCH", "The two passwords do not match")
            result = security.accept_invite(conn, token, first(form, "full_name"), password)
        except security.AuthError as e:
            return self._send(self.page_invite_accept(conn, token, e.message), 400)
        sess_token, _csrf = security.create_session(conn, result["user_id"], result["tenant_id"],
                                                    self.client_address[0])
        acct.audit(conn, result["tenant_id"], result["user_id"], "auth.session_created", "session")
        return self._redirect("/", {"Set-Cookie": f"sid={sess_token}; HttpOnly; SameSite=Lax; Path=/"})

    def _switch_business(self, conn, user, sess, form):
        tenant_id = first(form, "tenant_id")
        rows = security.tenants_for(conn, user["id"])
        if tenant_id not in {r["id"] for r in rows}:
            return self._error_page(user, {"id": tenant_id, "name": "Business"},
                                    "You do not have active access to that business.", "/businesses")
        conn.execute("UPDATE session SET tenant_id=? WHERE id=? AND user_id=?",
                     (tenant_id, sess["id"], user["id"]))
        acct.audit(conn, tenant_id, user["id"], "auth.tenant_switched", "tenant", tenant_id)
        return self._redirect("/")

    def _invite_member(self, conn, user, tenant, form):
        try:
            security.require(conn, user["id"], tenant["id"], "user.invite")
        except security.AuthError as e:
            return self._send(self.page_users(conn, user, tenant, {"csrf_token": ""}, {}, e.message), 403)
        try:
            result = security.invite_member(conn, tenant["id"], first(form, "email"),
                                            first(form, "full_name"), first(form, "role"),
                                            user["id"])
        except security.AuthError as e:
            return self._send(self.page_users(conn, user, tenant,
                                              {"csrf_token": form.get("_csrf", [""])[0]}, {}, e.message), 400)
        link = f"{self._base_url()}/invite/{result['token']}"
        return self._send(self.page_invite_created(user, tenant, result, link))

    def _change_member_role(self, conn, user, tenant, form):
        try:
            security.require(conn, user["id"], tenant["id"], "role.assign")
            security.change_member_role(conn, tenant["id"], user["id"],
                                        first(form, "user_id"), first(form, "role"))
        except security.AuthError as e:
            return self._send(self.page_users(conn, user, tenant,
                                              {"csrf_token": form.get("_csrf", [""])[0]}, {}, e.message), 400)
        return self._redirect("/users?saved=1")

    def _change_member_status(self, conn, user, tenant, form):
        try:
            security.require(conn, user["id"], tenant["id"], "role.assign")
            security.set_member_status(conn, tenant["id"], user["id"],
                                       first(form, "user_id"), first(form, "status"))
        except security.AuthError as e:
            return self._send(self.page_users(conn, user, tenant,
                                              {"csrf_token": form.get("_csrf", [""])[0]}, {}, e.message), 400)
        return self._redirect("/users?saved=1")

    def _revoke_invite(self, conn, user, tenant, form):
        try:
            security.require(conn, user["id"], tenant["id"], "user.invite")
            security.revoke_invite(conn, tenant["id"], first(form, "invite_id"), user["id"])
        except security.AuthError as e:
            return self._send(self.page_users(conn, user, tenant,
                                              {"csrf_token": form.get("_csrf", [""])[0]}, {}, e.message), 400)
        return self._redirect("/users?revoked=1")

    def _create_statement_share(self, conn, user, tenant, form, party_type: str, party_id: str):
        try:
            security.require(conn, user["id"], tenant["id"], "statement.share")
            try:
                days = int(first(form, "days") or "30")
            except ValueError:
                days = 30
            result = sharing.create_statement_share(
                conn, tenant["id"], party_type, party_id,
                first(form, "from"), first(form, "to"), user["id"], days)
        except (security.AuthError, sharing.ShareError) as e:
            back = f"/{party_type}s/{party_id}"
            return self._error_page(user, tenant, e.message, back)
        qs = urllib.parse.urlencode({"from": result["date_from"], "to": result["date_to"],
                                     "share": result["token"]})
        return self._redirect(f"/{party_type}s/{party_id}?{qs}")

    def _revoke_statement_share(self, conn, user, tenant, form):
        try:
            security.require(conn, user["id"], tenant["id"], "statement.share")
            sharing.revoke_statement_share(conn, tenant["id"], first(form, "share_id"), user["id"])
        except (security.AuthError, sharing.ShareError) as e:
            return self._error_page(user, tenant, e.message, "/")
        party_type = first(form, "party_type") or "customer"
        party_id = first(form, "party_id")
        back = f"/{party_type}s/{party_id}" if party_id else "/"
        qs = urllib.parse.urlencode({"from": first(form, "from"), "to": first(form, "to"),
                                     "revoked": "1"})
        return self._redirect(f"{back}?{qs}")

    def _gstr2b_import(self, conn, user, tenant, form):
        security.require(conn, user["id"], tenant["id"], "gst.reconcile")
        month = first(form, "month") or date.today().strftime("%Y-%m")
        try:
            result = gstr2b_mod.import_2b(conn, tenant["id"], month,
                                          first(form, "csv_text"), first(form, "filename"),
                                          user["id"])
        except gstr2b_mod.Gstr2bError as e:
            return self._send(self.page_gstr2b(conn, user, tenant,
                                               {"csrf_token": form.get("_csrf", [""])[0]},
                                               {"month": [month]}, e.message), 400)
        qs = urllib.parse.urlencode({"month": result["period"],
                                     "imported": result["imported"],
                                     "duplicate": "1" if result["duplicate"] else "0"})
        return self._redirect(f"/gstr2b?{qs}")

    def _gstr2b_review(self, conn, user, tenant, form):
        security.require(conn, user["id"], tenant["id"], "gst.reconcile")
        month = first(form, "month") or date.today().strftime("%Y-%m")
        try:
            gstr2b_mod.review_line(conn, tenant["id"], first(form, "line_id"),
                                   first(form, "status"), first(form, "note"), user["id"])
        except gstr2b_mod.Gstr2bError as e:
            return self._send(self.page_gstr2b(conn, user, tenant,
                                               {"csrf_token": form.get("_csrf", [""])[0]},
                                               {"month": [month]}, e.message), 400)
        return self._redirect(f"/gstr2b?{urllib.parse.urlencode({'month': month, 'reviewed': '1'})}")

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

    def _create_debit_note(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "debit_note.create")
        bill_id = first(form, "bill_id")
        try:
            qty = money.parse_qty(first(form, "qty"))
            note = acct.create_debit_note(
                conn, tenant["id"], bill_id, first(form, "note_date") or date.today().isoformat(),
                first(form, "reason"), [{"bill_line_id": first(form, "bill_line_id"), "qty": qty}],
                created_by=user["id"])
            return self._redirect(f"/bills/{bill_id}")
        except (acct.AccountingError, money.MoneyError) as e:
            return self._error_page(user, tenant, getattr(e, "message", str(e)),
                                    f"/bills/{bill_id}")

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

    def _bank_import(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "bank.reconcile")
        account_id = first(form, "account_id")
        try:
            rows = bank_mod.parse_csv(first(form, "csv_text"))
            result = bank_mod.import_statement(
                conn, tenant["id"], account_id, rows,
                filename=first(form, "filename"), created_by=user["id"])
        except bank_mod.BankError as e:
            return self._error_page(user, tenant, e.message, "/bank-recon")
        qs = urllib.parse.urlencode({
            "account": account_id, "from": result["period_start"], "to": result["period_end"],
            "imported": result["imported"], "duplicates": result["duplicates"]})
        return self._redirect(f"/bank-recon?{qs}")

    def _bank_auto_match(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "bank.reconcile")
        account_id = first(form, "account_id")
        dfrom = first(form, "from") or fiscal_start(date.today(), tenant["fiscal_year_start_month"])
        dto = first(form, "to") or date.today().isoformat()
        try:
            result = bank_mod.auto_match(conn, tenant["id"], account_id, dfrom, dto,
                                         created_by=user["id"])
        except bank_mod.BankError as e:
            return self._error_page(user, tenant, e.message, "/bank-recon")
        qs = urllib.parse.urlencode({
            "account": account_id, "from": dfrom, "to": dto,
            "matched": result["matched"], "ambiguous": result["ambiguous"]})
        return self._redirect(f"/bank-recon?{qs}")

    def _bank_match(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "bank.reconcile")
        account_id = first(form, "account_id")
        dfrom = first(form, "from")
        dto = first(form, "to")
        try:
            bank_mod.match_line(conn, tenant["id"], first(form, "statement_id"),
                                first(form, "journal_line_id"), created_by=user["id"])
        except bank_mod.BankError as e:
            return self._error_page(user, tenant, e.message, "/bank-recon")
        qs = urllib.parse.urlencode({"account": account_id, "from": dfrom, "to": dto,
                                     "matched": 1})
        return self._redirect(f"/bank-recon?{qs}")

    def _bank_unmatch(self, conn, user, tenant, sess, form):
        security.require(conn, user["id"], tenant["id"], "bank.reconcile")
        account_id = first(form, "account_id")
        dfrom = first(form, "from")
        dto = first(form, "to")
        try:
            bank_mod.unmatch_line(conn, tenant["id"], first(form, "statement_id"),
                                  created_by=user["id"])
        except bank_mod.BankError as e:
            return self._error_page(user, tenant, e.message, "/bank-recon")
        qs = urllib.parse.urlencode({"account": account_id, "from": dfrom, "to": dto,
                                     "unmatched": 1})
        return self._redirect(f"/bank-recon?{qs}")

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
        elif key == "gstr1":
            dfrom = (q.get("from") or [fiscal_start(date.today(), tenant["fiscal_year_start_month"])])[0]
            dto = (q.get("to") or [today])[0]
            g = acct.gstr1_data(conn, tid, dfrom, dto)
            rows = [["Section", "GSTIN/UIN", "Receiver", "Invoice No", "Invoice Date",
                     "Invoice Value", "Place of Supply", "Reverse Charge", "Rate %", "Taxable",
                     "CGST", "SGST", "IGST", "Cess", "Description", "UQC", "Qty"]]
            for r in g["b2b"]:
                rows.append(["B2B", r["gstin"], r["receiver"], r["invoice_no"], r["invoice_date"],
                             money.to_str(r["invoice_value"]) if r["invoice_value"] is not None else "",
                             r["place_of_supply"], r["reverse_charge"], f'{r["rate_bp"] / 100:.2f}',
                             money.to_str(r["taxable"]), money.to_str(r["cgst"]),
                             money.to_str(r["sgst"]), money.to_str(r["igst"]),
                             money.to_str(r["cess"]), "", "", ""])
            for r in g["b2cs"]:
                rows.append(["B2CS", "", "", "B2CS", "", "", r["place_of_supply"], "N",
                             f'{r["rate_bp"] / 100:.2f}', money.to_str(r["taxable"]),
                             money.to_str(r["cgst"]), money.to_str(r["sgst"]),
                             money.to_str(r["igst"]), "0.00", "", "", ""])
            for r in g["hsn"]:
                rows.append(["HSN", "", "", "", "", "", "", "", f'{r["rate_bp"] / 100:.2f}',
                             money.to_str(r["taxable"]), money.to_str(r["cgst"]),
                             money.to_str(r["sgst"]), money.to_str(r["igst"]), "0.00",
                             r["description"], r["uqc"], f'{r["qty_milli"] / 1000:.3f}'])
            for r in g["credit_notes"]:
                rows.append([r["section"], r["gstin"], r["receiver"], r["note_no"],
                             r["note_date"], money.to_str(r["note_value"]), r["place_of_supply"],
                             "N", "", money.to_str(r["taxable"]), money.to_str(r["cgst"]),
                             money.to_str(r["sgst"]), money.to_str(r["igst"]),
                             money.to_str(r["cess"]), "Credit note", "", ""])
            rows.append(["CN TOTAL", "", "", "", "", "", "", "", "",
                         money.to_str(g["credit_note_totals"]["taxable"]),
                         money.to_str(g["credit_note_totals"]["cgst"]),
                         money.to_str(g["credit_note_totals"]["sgst"]),
                         money.to_str(g["credit_note_totals"]["igst"]), "0.00", "", "", ""])
            rows.append(["TOTAL", "", "", "", "", "", "", "", "",
                         money.to_str(g["totals"]["taxable"]), money.to_str(g["totals"]["cgst"]),
                         money.to_str(g["totals"]["sgst"]), money.to_str(g["totals"]["igst"]),
                         "0.00", "", "", ""])
            rows.append([])
            rows.append(["Note", "Working export, not a filed return. Amounts are INR decimals. "
                         "Invoice Value appears once per invoice (first rate row)."])
            for w in g["warnings"]:
                rows.append(["Warning", w])
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
        elif key == "debit-notes":
            data = conn.execute(
                "SELECT n.*, v.name, b.bill_no FROM debit_note n JOIN vendor v ON v.id=n.vendor_id"
                " LEFT JOIN bill b ON b.id=n.bill_id"
                " WHERE n.tenant_id=? ORDER BY n.note_date", (tid,)).fetchall()
            rows = [["Note", "Date", "Vendor", "Bill", "Reason", "Taxable", "GST", "Total"]]
            rows += [[r["note_no"], r["note_date"], r["name"], r["bill_no"] or "", r["reason"],
                      money.to_str(r["sub_total_paise"]), money.to_str(r["tax_paise"]),
                      money.to_str(r["total_paise"])] for r in data]
        elif key == "bank-statement":
            accounts = bank_mod.bank_accounts(conn, tid)
            account_id = (q.get("account") or [accounts[0]["id"] if accounts else ""])[0]
            dfrom = (q.get("from") or [f"{today[:4]}-04-01"])[0]
            dto = (q.get("to") or [today])[0]
            lines = (bank_mod.statement_lines(conn, tid, account_id, dfrom, dto)
                     if account_id else [])
            rows = [["Date", "Description", "Reference", "Debit", "Credit", "Balance",
                     "Status", "Matched entry"]]
            rows += [[r["txn_date"], r["description"], r["reference"],
                      money.to_str(r["debit_paise"]) if r["debit_paise"] else "",
                      money.to_str(r["credit_paise"]) if r["credit_paise"] else "",
                      money.to_str(r["balance_paise"]) if r["balance_paise"] is not None else "",
                      r["status"], r["entry_no"] or ""] for r in lines]
        elif key == "gstr3b":
            month = (q.get("month") or [date.today().strftime("%Y-%m")])[0]
            try:
                g = acct.gstr3b_data(conn, tid, month)
            except acct.AccountingError:
                return self._send("Invalid month; use YYYY-MM", 400)
            out = g["outward"]
            itc = g["itc"]
            pay = g["payment"]
            rows = [
                ["Section", "Description", "Taxable Value", "IGST", "CGST", "SGST", "Cess"],
                ["3.1(a)", "Outward taxable supplies net of credit notes",
                 money.to_str(out["taxable_net"]), money.to_str(out["output_net"]["IGST"]),
                 money.to_str(out["output_net"]["CGST"]), money.to_str(out["output_net"]["SGST"]),
                 money.to_str(0)],
                ["3.1(b)", "Outward taxable supplies zero-rated", money.to_str(0),
                 money.to_str(0), money.to_str(0), money.to_str(0), money.to_str(0)],
                ["3.1(c)", "Other outward supplies nil-rated/exempted", money.to_str(0),
                 money.to_str(0), money.to_str(0), money.to_str(0), money.to_str(0)],
                ["3.1(d)", "Inward supplies liable to reverse charge (outward side)",
                 money.to_str(0), money.to_str(0), money.to_str(0), money.to_str(0), money.to_str(0)],
                ["3.1(e)", "Non-GST outward supplies", money.to_str(0), money.to_str(0),
                 money.to_str(0), money.to_str(0), money.to_str(0)],
                [],
                ["Section", "Description", "IGST", "CGST", "SGST", "Total", "Cess"],
                ["4(A)(5)", "All other ITC - purchase bills",
                 money.to_str(itc["gross"]["IGST"]), money.to_str(itc["gross"]["CGST"]),
                 money.to_str(itc["gross"]["SGST"]), money.to_str(itc["gross_total"]), money.to_str(0)],
                ["4(B)(2)", "ITC reversal - debit notes / purchase returns",
                 money.to_str(itc["reversal"]["IGST"]), money.to_str(itc["reversal"]["CGST"]),
                 money.to_str(itc["reversal"]["SGST"]), money.to_str(itc["reversal_total"]),
                 money.to_str(0)],
                ["", "Net eligible ITC", money.to_str(itc["net"]["IGST"]),
                 money.to_str(itc["net"]["CGST"]), money.to_str(itc["net"]["SGST"]),
                 money.to_str(itc["net_total"]), money.to_str(0)],
                [],
                ["Section", "Head", "Output tax", "ITC available", "ITC utilised",
                 "Cash payable", "ITC balance"],
            ]
            rows += [[ "5", h["head"], money.to_str(h["output"]), money.to_str(h["itc_available"]),
                       money.to_str(h["itc_used"]), money.to_str(h["cash_payable"]),
                       money.to_str(h["itc_balance"])] for h in pay["heads"]]
            rows += [
                ["", "Total", money.to_str(pay["output_total"]),
                 money.to_str(pay["itc_available_total"]), money.to_str(pay["itc_used_total"]),
                 money.to_str(pay["cash_payable_total"]), money.to_str(pay["itc_balance_total"])],
                [],
                ["Reconciliation", "Check", "Expected", "Actual", "Difference", "Status", ""],
            ]
            rows += [[ "Check", c["label"], money.to_str(c["expected"]), money.to_str(c["actual"]),
                       money.to_str(c["difference"]), c["status"], ""]
                     for c in g["reconciliation"]["checks"]]
            rows += [
                [],
                ["Period", g["period"]["from"], g["period"]["to"], "", "", "", ""],
                ["Note", g["note"], "", "", "", "", ""],
            ]
        elif key == "gstr2b":
            month = (q.get("month") or [date.today().strftime("%Y-%m")])[0]
            try:
                g = gstr2b_mod.reconcile(conn, tid, month)
            except gstr2b_mod.Gstr2bError:
                return self._send("Invalid month; use YYYY-MM", 400)
            rows = [["Source", "Status", "Supplier", "GSTIN", "Invoice", "Invoice Date",
                     "Taxable", "IGST", "CGST", "SGST", "Cess", "Tax", "Bill", "Note",
                     "ITC review", "Review note"]]
            for r in g["rows"]:
                rows.append(["GSTR-2B", r["match_status"], r["supplier_name"] or "",
                             r["supplier_gstin"], r["invoice_no"], r["invoice_date"],
                             money.to_str(r["taxable_paise"]), money.to_str(r["igst_paise"]),
                             money.to_str(r["cgst_paise"]), money.to_str(r["sgst_paise"]),
                             money.to_str(r["cess_paise"]), money.to_str(r["tax_paise"]),
                             r["bill_no"], r["note"], r["review_status"], r["review_note"]])
            for b in g["books"]:
                rows.append(["Books", "missing_in_2b", b["vendor_name"], b["vendor_gstin"] or "",
                             b["vendor_bill_no"] or "", b["bill_date"],
                             money.to_str(b["sub_total_paise"]), money.to_str(b["igst_book"]),
                             money.to_str(b["cgst_book"]), money.to_str(b["sgst_book"]),
                             money.to_str(0), money.to_str(b["tax_paise"]), b["bill_no"],
                             b["note"], "n/a", ""])
            s = g["summary"]
            comp = gstr2b_mod.itc_comparison(conn, tid, month, g)
            rows += [
                [],
                ["Summary", "GSTR-2B tax", money.to_str(s["two_b"]["tax"]), "Books tax",
                 money.to_str(s["books"]["tax"]), "Difference", money.to_str(s["difference"])],
                ["Summary", "Matched", str(s["matched"]["count"]), "Mismatch",
                 str(s["mismatch"]["count"]), "Missing in books", str(s["missing_in_books"]["count"])],
                ["Summary", "Missing in 2B", str(s["missing_in_2b"]["count"]), "", "", "", ""],
                ["Review", "Open", str(s["review"]["open"]["count"]), "Follow-up",
                 str(s["review"]["follow_up"]["count"]), "ITC hold",
                 str(s["review"]["itc_hold"]["count"]), "Accepted", str(s["review"]["accepted"]["count"])],
                ["Compare", "GSTR-3B eligible ITC", money.to_str(comp["books_itc"]),
                 "GSTR-2B ITC", money.to_str(comp["two_b_itc"]),
                 "Difference", money.to_str(comp["difference"]), comp["status"], ""],
                [],
                ["Note", "Working reconciliation aid, not a filed return. Review states are internal; "
                         "no ITC was posted or changed."],
            ]
        else:
            return self._send("Unknown export", 404)

        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\r\n")
        writer.writerows(rows)
        data = buf.getvalue().encode("utf-8-sig")
        self._send_bytes(data, "text/csv; charset=utf-8", f"arthivio-{key}-{today}.csv")


    def export_gstr1_json(self, conn, user, tenant, q):
        security.require(conn, user["id"], tenant["id"], "report.export")
        today = date.today()
        dfrom = (q.get("from") or [fiscal_start(today, tenant["fiscal_year_start_month"])])[0]
        dto = (q.get("to") or [today.isoformat()])[0]
        g = acct.gstr1_data(conn, tenant["id"], dfrom, dto)
        amount_keys = ("taxable", "cgst", "sgst", "igst", "cess")

        def amounts(row, keys=amount_keys):
            return {k: money.to_str(row[k]) for k in keys}

        b2b = []
        for r in g["b2b"]:
            item = {k: r[k] for k in ("gstin", "receiver", "invoice_no", "invoice_date",
                                      "place_of_supply", "reverse_charge")}
            item["invoice_value"] = (money.to_str(r["invoice_value"])
                                     if r["invoice_value"] is not None else None)
            item["rate_pct"] = f'{r["rate_bp"] / 100:.2f}'
            item.update(amounts(r))
            b2b.append(item)
        b2cs = []
        for r in g["b2cs"]:
            item = {k: r[k] for k in ("place_of_supply", "invoices")}
            item["rate_pct"] = f'{r["rate_bp"] / 100:.2f}'
            item.update(amounts(r, ("taxable", "cgst", "sgst", "igst")))
            b2cs.append(item)
        hsn = []
        for r in g["hsn"]:
            item = {k: r[k] for k in ("hsn", "description", "uqc")}
            item["qty"] = f'{r["qty_milli"] / 1000:.3f}'
            item["rate_pct"] = f'{r["rate_bp"] / 100:.2f}'
            item.update(amounts(r, ("taxable", "cgst", "sgst", "igst", "total_value")))
            hsn.append(item)
        credit_notes = []
        for r in g["credit_notes"]:
            item = {k: r[k] for k in ("section", "gstin", "receiver", "note_no",
                                      "note_date", "place_of_supply")}
            item["note_value"] = money.to_str(r["note_value"])
            item.update(amounts(r))
            credit_notes.append(item)

        payload = {
            "format": "arthivio-gstr1-working-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "amount_unit": "INR decimal string",
            "period": g["period"],
            "supplier": g["supplier"],
            "b2b": b2b,
            "b2cs": b2cs,
            "hsn": hsn,
            "credit_notes": credit_notes,
            "credit_note_totals": {k: money.to_str(v)
                                   for k, v in g["credit_note_totals"].items()},
            "docs": {**g["docs"],
                     "credit_note_value": money.to_str(g["docs"]["credit_note_value"])},
            "totals": {k: money.to_str(v) for k, v in g["totals"].items()},
            "warnings": g["warnings"],
            "note": "Preparation aid only; not an uploaded or filed GST return. "
                    "Verify with your tax professional before filing.",
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send_bytes(data, "application/json; charset=utf-8",
                         f"arthivio-gstr1-{today.isoformat()}.json")


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
