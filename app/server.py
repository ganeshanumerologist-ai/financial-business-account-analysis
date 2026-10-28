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
from email.parser import BytesParser
from email.policy import default as email_policy
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import accounting as acct
from . import analytics as analytics_mod
from . import backup as backup_mod
from . import bank as bank_mod
from . import bi as bi_mod
from . import db, money, security
from . import excel as excel_mod
from . import gstr2b as gstr2b_mod
from . import insights as insights_mod
from . import opening_import as opening_mod
from . import sharing
from . import xlsx_import as xlsx_mod

DB_PATH = os.environ.get("ARTHIVIO_DB", os.path.join("data", "arthivio.db"))
BACKUP_DIR = os.environ.get("ARTHIVIO_BACKUP_DIR", "backups")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
APP_NAME = "ARTHIVIO"
DEMO_AUTOLOGIN = os.environ.get("ARTHIVIO_DEMO_AUTOLOGIN") == "1"
DEMO_EMAIL = os.environ.get("ARTHIVIO_DEMO_EMAIL", "owner@arthivio.test")

DEFAULT_THEME = "ocean"
MAX_POST_BYTES = 10 * 1024 * 1024
THEMES = {
    "ocean": {
        "label": "Ocean Blue",
        "description": "Cool electric blue with cyan highlights.",
        "swatches": ("#2563EB", "#67E8F9", "#22C55E", "#F6F9FF"),
    },
    "emerald": {
        "label": "Emerald Green",
        "description": "Fresh green with soft teal highlights.",
        "swatches": ("#15803D", "#5EEAD4", "#22C55E", "#F4FBF7"),
    },
    "violet": {
        "label": "Royal Violet",
        "description": "Soft violet with lavender highlights.",
        "swatches": ("#7C3AED", "#C4B5FD", "#22C55E", "#F8F5FF"),
    },
    "sunset": {
        "label": "Warm Sunset",
        "description": "Warm terracotta with peach highlights.",
        "swatches": ("#C2410C", "#FDBA74", "#16A34A", "#FFF8F1"),
    },
}

# Dark-but-not-black landing-page variants. These are deliberately separate from
# the light workspace palettes so a marketing visitor can preview a colour without
# turning the hero into a white page.
LANDING_THEMES = {
    "ocean": {
        "hero_a": "#0C3157", "hero_b": "#0A2A48", "hero_c": "#061A30",
        "overlay_1": "rgba(4,22,47,.94)", "overlay_2": "rgba(4,22,47,.84)",
        "overlay_3": "rgba(4,22,47,.50)", "overlay_4": "rgba(4,22,47,.22)",
        "accent": "#67E8F9", "accent_2": "#5EEAD4", "accent_3": "#86EFAC",
        "primary": "#2563EB", "primary_2": "#1D4ED8",
        "proof_a": "#08223D", "proof_b": "#0A2A48",
        "side_a": "#0A2A48", "side_b": "#061A30",
        "glow": "rgba(56,189,248,.30)",
    },
    "emerald": {
        "hero_a": "#0D3F31", "hero_b": "#0A3328", "hero_c": "#052019",
        "overlay_1": "rgba(5,32,25,.94)", "overlay_2": "rgba(5,32,25,.84)",
        "overlay_3": "rgba(5,32,25,.50)", "overlay_4": "rgba(5,32,25,.22)",
        "accent": "#86EFAC", "accent_2": "#5EEAD4", "accent_3": "#BBF7D0",
        "primary": "#15803D", "primary_2": "#166534",
        "proof_a": "#0A3328", "proof_b": "#0D3F31",
        "side_a": "#0A3328", "side_b": "#052019",
        "glow": "rgba(52,211,153,.28)",
    },
    "violet": {
        "hero_a": "#2D1D52", "hero_b": "#241544", "hero_c": "#150C28",
        "overlay_1": "rgba(21,12,40,.94)", "overlay_2": "rgba(21,12,40,.84)",
        "overlay_3": "rgba(21,12,40,.50)", "overlay_4": "rgba(21,12,40,.22)",
        "accent": "#C4B5FD", "accent_2": "#A78BFA", "accent_3": "#DDD6FE",
        "primary": "#7C3AED", "primary_2": "#6D28D9",
        "proof_a": "#241544", "proof_b": "#2D1D52",
        "side_a": "#241544", "side_b": "#150C28",
        "glow": "rgba(167,139,250,.28)",
    },
    "sunset": {
        "hero_a": "#4E271A", "hero_b": "#3B1D12", "hero_c": "#26100A",
        "overlay_1": "rgba(38,16,10,.94)", "overlay_2": "rgba(38,16,10,.84)",
        "overlay_3": "rgba(38,16,10,.50)", "overlay_4": "rgba(38,16,10,.22)",
        "accent": "#FDBA74", "accent_2": "#FB923C", "accent_3": "#FDE68A",
        "primary": "#C2410C", "primary_2": "#9A3412",
        "proof_a": "#3B1D12", "proof_b": "#4E271A",
        "side_a": "#3B1D12", "side_b": "#26100A",
        "glow": "rgba(251,146,60,.26)",
    },
}


def landing_theme_style(theme: str) -> str:
    """Inline custom properties for the standalone landing page."""
    t = LANDING_THEMES.get(theme, LANDING_THEMES[DEFAULT_THEME])
    return ";".join(f"--lp-{k.replace('_', '-')}:{v}" for k, v in t.items())


THEME_CSS = """
:root,[data-theme="ocean"]{
  --page:#F6F9FF; --surface:#FFFFFF; --ink:#212529; --ink-soft:#3F4650;
  --primary:#2563EB; --primary-strong:#1D4ED8; --primary-soft:#DBEAFE; --primary-pale:#EFF6FF;
  --primary-line:#BFDBFE; --primary-ink:#1E40AF; --chart-a:#60A5FA; --chart-b:#2563EB;
  --success:#22C55E; --success-soft:#DCFCE7; --success-ink:#166534;
  --line:#E6EDF7; --muted:#6C757D; --danger:#DC2626; --danger-bg:#FEF2F2;
  --radius:14px; --shadow:0 1px 2px rgba(33,37,41,.05),0 8px 24px rgba(33,37,41,.06);
}
[data-theme="emerald"]{
  --page:#F4FBF7; --primary:#15803D; --primary-strong:#166534;
  --primary-soft:#DCFCE7; --primary-pale:#F0FDF4; --primary-line:#BBF7D0;
  --primary-ink:#166534; --chart-a:#4ADE80; --chart-b:#16A34A;
  --line:#DDF0E4; --muted:#5F6B66;
}
[data-theme="violet"]{
  --page:#F8F5FF; --primary:#7C3AED; --primary-strong:#6D28D9;
  --primary-soft:#EDE9FE; --primary-pale:#F5F3FF; --primary-line:#DDD6FE;
  --primary-ink:#5B21B6; --chart-a:#A78BFA; --chart-b:#7C3AED;
  --line:#E9E3F7; --muted:#6B6478;
}
[data-theme="sunset"]{
  --page:#FFF8F1; --primary:#C2410C; --primary-strong:#9A3412;
  --primary-soft:#FFEDD5; --primary-pale:#FFF7ED; --primary-line:#FED7AA;
  --primary-ink:#9A3412; --chart-a:#FDBA74; --chart-b:#C2410C;
  --line:#F3E3D3; --muted:#7A6A5C;
}
"""

CSS = THEME_CSS + """
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--page); color:var(--ink);
  font-family:"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;
  font-size:16px; line-height:1.5; -webkit-font-smoothing:antialiased;
}
a{color:var(--primary);text-decoration:none}
a:hover{text-decoration:underline}
h1,h2,h3{margin:0;font-weight:650;letter-spacing:-.015em;color:var(--ink)}
h1{font-size:26px} h2{font-size:19px} h3{font-size:15px}
.shell{min-height:100vh}
.topbar{position:sticky;top:0;z-index:60;background:rgba(255,255,255,.97);color:var(--ink);border-bottom:1px solid var(--line);backdrop-filter:blur(16px);box-shadow:0 8px 24px rgba(33,37,41,.05)}
.topbar-inner{max-width:1600px;margin:0 auto;padding:0 22px;min-height:64px;display:flex;align-items:center;gap:16px}
.brand{display:flex;align-items:center;gap:10px;margin:0;flex:0 0 auto;color:var(--ink);text-decoration:none}
.brand:hover{text-decoration:none;color:var(--primary)}
.brand svg{flex:0 0 auto}
.brand .name{font-size:19px;font-weight:700;letter-spacing:.06em}
.brand .tag{display:block;font-size:10.5px;color:var(--muted);letter-spacing:.02em;margin-top:2px}
.mainnav{display:flex;align-items:stretch;gap:1px;flex:1;min-width:0}
.navlink,.menu>summary{display:flex;align-items:center;gap:7px;height:64px;padding:0 12px;color:var(--ink-soft);font-size:13.5px;font-weight:600;cursor:pointer;list-style:none;white-space:nowrap;border-radius:0}
.navlink:hover,.menu>summary:hover{background:var(--primary-pale);text-decoration:none;color:var(--primary-strong)}
.navlink.on,.menu.on>summary{background:var(--primary-pale);color:var(--primary);box-shadow:inset 0 -2px 0 var(--primary)}
.navlink:focus-visible,.menu>summary:focus-visible{outline:2px solid var(--primary);outline-offset:-3px}
.navlink .ico,.menu>summary .ico{width:16px;height:16px;opacity:.9}
.menu{position:relative}
.menu>summary::-webkit-details-marker{display:none}
.menu>summary .chev{width:12px;height:12px;margin-left:2px;transition:transform .15s;opacity:.7}
.menu[open]>summary .chev{transform:rotate(180deg)}
.menu-panel{position:absolute;top:calc(100% + 8px);left:0;z-index:70;min-width:250px;background:#fff;color:var(--ink);border:1px solid var(--line);border-radius:12px;box-shadow:0 18px 50px rgba(33,37,41,.18);padding:10px;display:grid;gap:8px}
.menu-group{min-width:220px}
.menu-title{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:700;padding:6px 10px 3px}
.menu-panel a{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;color:var(--ink-soft);font-size:13.5px;font-weight:500;white-space:nowrap}
.menu-panel a:hover{background:var(--primary-pale);color:var(--primary-strong);text-decoration:none}
.menu-panel a.on{background:var(--primary-soft);color:var(--primary-strong);font-weight:700}
.menu-panel a .ico{width:15px;height:15px;opacity:.85}
.menu-group + .menu-group{border-top:1px solid var(--line);padding-top:6px}
.userbox{display:flex;align-items:center;gap:8px;margin-left:auto;flex:0 0 auto}
.usertext{font-size:12px;line-height:1.25;color:var(--muted);text-align:right}
.usertext b{display:block;color:var(--ink);font-size:12.5px}
.topbar .btn.ghost{background:#fff;border-color:var(--line);color:var(--primary)}
.topbar .btn.ghost:hover{background:var(--primary-pale);color:var(--primary-strong)}
.main{padding:26px 30px 56px;min-width:0;max-width:1600px;margin:0 auto;width:100%}
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
.ledger-layout{display:grid;grid-template-columns:330px minmax(0,1fr);gap:16px;align-items:start}
.ledger-side{position:sticky;top:80px;max-height:calc(100vh - 100px);overflow:auto;padding:14px}
.ledger-side h2{font-size:15px}
.ledger-group{margin-top:12px}
.ledger-group-title{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700;padding:5px 8px 3px}
.ledger-item{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 9px;border-radius:8px;color:var(--ink-soft);font-size:13px;line-height:1.25}
.ledger-item:hover{background:var(--primary-pale);color:var(--primary-strong);text-decoration:none}
.ledger-item.on{background:var(--primary-soft);color:var(--primary-strong);font-weight:700}
.ledger-item.archived{opacity:.68}
.ledger-item.archived .name{font-style:italic}
.ledger-item .code{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11.5px;flex:0 0 auto}
.ledger-item.on .code{color:var(--primary-strong)}
.ledger-item .name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ledger-item .bal{font-variant-numeric:tabular-nums;font-size:11.5px;white-space:nowrap}
.ledger-add{border-top:1px solid var(--line);margin-top:14px;padding-top:12px}
.ledger-add>summary{cursor:pointer;color:var(--primary);font-size:13px;font-weight:650;list-style:none}
.ledger-add>summary::-webkit-details-marker{display:none}
.ledger-add[open]>summary{margin-bottom:10px}
.ledger-add form{display:grid;gap:9px}
.ledger-add .row.c2{gap:8px}
.entry-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.entry-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}
.entry-tab{padding:8px 13px;border-radius:999px;border:1px solid var(--line);background:#fff;color:var(--ink-soft);font-size:13px;font-weight:600}
.entry-tab:hover{background:var(--primary-pale);text-decoration:none;color:var(--primary-strong)}
.entry-tab.on{background:var(--primary);border-color:var(--primary);color:#fff}
.entry-tab.on:hover{color:#fff}
.notice{background:var(--primary-pale);border:1px solid var(--primary-line);color:var(--primary-ink);padding:10px 13px;border-radius:10px;margin-bottom:14px;font-size:13.5px}
.pill{display:inline-flex;align-items:center;font-size:11px;font-weight:600;padding:2px 7px;border-radius:999px;background:#F1F5F9;color:#475569;white-space:nowrap}
table{width:100%;border-collapse:collapse;font-size:14.5px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line)}
th{font-size:11.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:600;background:#F8FAFC}
tbody tr:hover{background:#F8FAFC}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tfoot td{font-weight:650;background:#F8FAFC}
.table-wrap{overflow-x:auto}
.review-cell{min-width:210px}
.review-form summary{cursor:pointer;color:var(--primary);font-size:12px;font-weight:600;margin-top:4px}
.review-form[open] summary{margin-bottom:6px}
.review-form form{display:grid;gap:5px;min-width:190px}
.review-form select,.review-form input{font-size:12.5px;padding:6px 8px}
.btn{display:inline-flex;align-items:center;gap:8px;background:var(--primary);color:#fff;border:0;border-radius:10px;
  padding:10px 16px;font-size:14.5px;font-weight:600;cursor:pointer}
.btn:hover{background:var(--primary-strong);text-decoration:none;color:#fff}
.btn.ghost{background:#fff;color:var(--primary);border:1px solid var(--primary-line)}
.btn.ghost:hover{background:var(--primary-pale);color:var(--primary-strong)}
.btn.small{padding:7px 12px;font-size:13.5px}
input,select,textarea{font:inherit;color:var(--ink);background:#fff;border:1px solid var(--line);border-radius:9px;padding:9px 11px;width:100%}
input:focus,select:focus,textarea:focus{outline:2px solid var(--primary-line);outline-offset:0;border-color:var(--primary)}
label{display:block;font-size:12.5px;font-weight:600;color:var(--ink-soft);margin-bottom:5px;letter-spacing:.01em}
.field{margin-bottom:13px}
.row{display:grid;gap:12px}
.row.c2{grid-template-columns:1fr 1fr}
.row.c3{grid-template-columns:repeat(3,1fr)}
.row.c4{grid-template-columns:repeat(4,1fr)}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:4px 9px;border-radius:999px}
.badge.ok{background:var(--success-soft);color:var(--success-ink)}
.badge.bad{background:var(--danger-bg);color:var(--danger)}
.badge.neutral{background:#F1F5F9;color:#475569}
.theme-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;border:0;padding:0;margin:0}
.theme-option{position:relative;display:block;border:1px solid var(--line);border-radius:12px;padding:10px;background:#fff;cursor:pointer}
.theme-option:hover{border-color:var(--primary-line);background:var(--primary-pale)}
.theme-option:has(input:checked){border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-soft)}
.theme-option:focus-within{outline:2px solid var(--primary);outline-offset:2px}
.theme-option input{position:absolute;opacity:0;pointer-events:none}
.theme-preview{display:flex;gap:3px;margin-bottom:8px}
.theme-preview i{height:18px;flex:1;border-radius:4px;display:block}
.theme-name{display:block;font-size:13px;font-weight:700;color:var(--ink)}
.theme-desc{display:block;font-size:11.5px;color:var(--muted);line-height:1.35;margin-top:2px}
.theme-save{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px}
.muted{color:var(--muted)}
.small{font-size:13px}
.err{background:var(--danger-bg);color:var(--danger);border:1px solid #FECACA;padding:11px 14px;border-radius:10px;margin-bottom:14px;font-size:14px}
.sect{margin-bottom:26px}
.sect-head{display:flex;align-items:end;justify-content:space-between;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.chart{display:flex;align-items:flex-end;gap:10px;height:150px;padding:10px 2px 0}
.chart .bar{flex:1;background:linear-gradient(180deg,var(--chart-a),var(--chart-b));border-radius:6px 6px 0 0;min-height:3px;position:relative}
.chart .bar span{position:absolute;bottom:-22px;left:0;right:0;text-align:center;font-size:11px;color:var(--muted)}
.chart .bar b{position:absolute;top:-20px;left:0;right:0;text-align:center;font-size:11px;color:var(--ink-soft);font-weight:600}
.chart2{display:flex;align-items:flex-end;gap:14px;height:176px;padding:20px 2px 0}
.chart2 .m{flex:1;display:flex;align-items:flex-end;gap:3px;height:100%;position:relative;min-width:0}
.chart2 .m i{flex:1;border-radius:5px 5px 0 0;min-height:2px;display:block}
.chart2 .m i.rev{background:linear-gradient(180deg,var(--chart-a),var(--chart-b))}
.chart2 .m i.exp{background:linear-gradient(180deg,#FBBF24,#F59E0B)}
.chart2 .m span{position:absolute;bottom:-22px;left:0;right:0;text-align:center;font-size:11px;color:var(--muted);white-space:nowrap}
.legend{display:flex;gap:16px;align-items:center;font-size:12px;color:var(--muted);flex-wrap:wrap}
.legend i{width:10px;height:10px;border-radius:3px;display:inline-block;margin-right:5px;vertical-align:-1px}
.legend .rev{background:linear-gradient(180deg,var(--chart-a),var(--chart-b))}
.legend .exp{background:#F59E0B}
.mini-bar{height:8px;background:var(--line);border-radius:999px;overflow:hidden;min-width:70px}
.mini-bar i{display:block;height:100%;background:linear-gradient(90deg,var(--chart-a),var(--chart-b));border-radius:999px}
.login-wrap{min-height:100vh;display:grid;place-items:center;padding:24px}
.login{width:100%;max-width:410px}
.brandline{display:flex;align-items:center;gap:11px;margin-bottom:18px}
.footer-note{color:var(--muted);font-size:12px;margin-top:26px}
.empty{padding:26px;text-align:center;color:var(--muted);font-size:14px}
@media (max-width:1180px){
  .topbar-inner{padding:0 14px;gap:10px}
  .navlink,.menu>summary{padding:0 9px;font-size:12.5px}
  .usertext{display:none}
}
@media (max-width:1260px){
  .topbar-inner{flex-wrap:wrap;padding:10px 14px;min-height:0;gap:8px 10px}
  .mainnav{order:3;flex:0 0 100%;width:100%;flex-wrap:nowrap;overflow-x:auto;overflow-y:visible;border-top:1px solid var(--line);padding-top:4px}
  .navlink,.menu>summary{height:44px;padding:0 8px;font-size:12px;gap:5px;flex:0 0 auto}
  .menu{position:static}
  .menu-panel{position:absolute;left:12px;right:12px;top:calc(100% + 6px);width:auto;min-width:0;max-height:70vh;overflow:auto;background:#fff;color:var(--ink);border:1px solid var(--line);box-shadow:0 18px 50px rgba(33,37,41,.18)}
  .menu-title{color:var(--muted)}
  .menu-panel a{color:var(--ink-soft)}
  .menu-panel a:hover{background:var(--primary-pale);color:var(--primary-strong)}
  .menu-panel a.on{background:var(--primary-soft);color:var(--primary-strong)}
  .menu-group + .menu-group{border-top-color:var(--line)}
  .main{padding:18px}
  .grid2{grid-template-columns:1fr}
  .row.c3,.row.c4{grid-template-columns:1fr 1fr}
}
@media (max-width:900px){
  .ledger-layout{grid-template-columns:1fr}
  .ledger-side{position:static;max-height:none}
}
@media (max-width:620px){.row.c3,.row.c4{grid-template-columns:1fr}}
@media print{.topbar,.top .who{display:none}.main{max-width:none;padding:0}}
"""

PRINT_CSS = """
@page{size:A4;margin:12mm}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font-family:"Segoe UI",system-ui,Arial,sans-serif;font-size:12px;line-height:1.45}
.toolbar{max-width:190mm;margin:14px auto;display:flex;gap:10px;justify-content:flex-end}
.toolbar a,.toolbar button{font:inherit;font-size:13px;padding:8px 14px;border-radius:8px;border:1px solid var(--primary-line);background:#fff;color:var(--primary);cursor:pointer;text-decoration:none}
.toolbar button{background:var(--primary);color:#fff;border-color:var(--primary)}
.sheet{width:190mm;min-height:270mm;margin:0 auto 20px;background:#fff;padding:14mm 14mm 12mm;box-shadow:0 4px 24px rgba(33,37,41,.08)}
.head{display:flex;justify-content:space-between;gap:18px;border-bottom:2px solid var(--primary);padding-bottom:10px}
.head .brand{font-size:21px;font-weight:700;letter-spacing:.03em;color:var(--ink)}
.head .meta{text-align:right;min-width:58mm}
.head .meta .doc{font-size:15px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--ink)}
.addr{font-size:11px;color:var(--ink-soft);margin-top:3px}
.parties{display:flex;gap:16px;margin:12px 0}
.parties>div{flex:1;border:1px solid var(--line);border-radius:6px;padding:8px 10px;min-height:24mm}
.parties h4{margin:0 0 4px;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:11px}
th,td{border:1px solid var(--line);padding:5px 6px;vertical-align:top}
th{background:var(--primary-pale);font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-soft);text-align:left}
.num{text-align:right;white-space:nowrap}
.totals{margin-left:auto;width:62mm;margin-top:8px}
.totals td{border:none;padding:3px 0}
.totals .amt{text-align:right;white-space:nowrap}
.totals .grand td{border-top:1px solid var(--primary);font-weight:700;font-size:13px;padding-top:5px}
.words{margin-top:10px;font-size:11px;background:var(--primary-pale);border:1px solid var(--line);border-radius:5px;padding:7px 9px}
.foot{display:flex;justify-content:space-between;gap:18px;margin-top:14px;font-size:10.5px;color:var(--ink-soft)}
.foot .box{flex:1}
.sign .line{margin-top:26px;border-top:1px solid var(--line);display:block;padding-top:4px;text-align:center}
.foot .sign{flex:0 0 58mm;text-align:center;margin:0}
.note{margin-top:10px;font-size:10px;color:var(--muted)}
.warn{max-width:190mm;margin:12px auto 0;background:var(--danger-bg);border:1px solid #FECACA;color:var(--danger);padding:8px 12px;border-radius:8px;font-size:12px}
@media print{body{background:#fff}.toolbar,.warn{display:none}.sheet{box-shadow:none;margin:0;width:auto;min-height:0;padding:0}}
"""

LOGO = """<svg width="30" height="30" viewBox="0 0 36 36" aria-hidden="true">
<path d="M3 30 L13 5 L21 24 Z" fill="#22D3EE"/>
<path d="M11 30 L19 9 L30 30 Z" fill="#3B82F6"/>
<path d="M18 30 L24 18 L33 30 Z" fill="#A78BFA" opacity=".92"/>
<path d="M6 30 L13 13 L18 30 Z" fill="#38BDF8" opacity=".48"/>
</svg>"""

LANDING_LOGO = """<svg width="38" height="38" viewBox="0 0 36 36" aria-hidden="true">
<path d="M3 30 L13 5 L21 24 Z" fill="#22D3EE"/>
<path d="M11 30 L19 9 L30 30 Z" fill="#2563EB"/>
<path d="M18 30 L24 18 L33 30 Z" fill="#7C3AED" opacity=".92"/>
<path d="M6 30 L13 13 L18 30 Z" fill="#0EA5E9" opacity=".48"/>
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
    "bank": '<path d="M3 9l9-5 9 5M5 9v9M9 9v9M15 9v9M19 9v9M3 21h18"/>',
    "gst": '<path d="M19 5L5 19M7.5 7.5a2 2 0 100-4 2 2 0 000 4zM16.5 20.5a2 2 0 100-4 2 2 0 000 4z"/>',
    "chev": '<path d="M6 9l6 6 6-6"/>',
}

NAV = [
    {
        "key": "dashboard",
        "label": "Dashboard",
        "icon": "dash",
        "href": "",
        "groups": [],
    },
    {
        "key": "transactions",
        "label": "Transactions",
        "icon": "inv",
        "groups": [
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
        ],
    },
    {
        "key": "entries",
        "label": "Entries",
        "icon": "led",
        "groups": [
            ("Record a new entry", [
                ("entries/cash", "led", "Cash Entry"),
                ("entries/bank", "bank", "Bank Entry"),
                ("entries/journal", "led", "Journal Entry"),
            ]),
        ],
    },
    {
        "key": "books",
        "label": "Books",
        "icon": "led",
        "groups": [
            ("Ledgers", [
                ("ledger", "led", "Ledger"),
                ("ledger/opening-balances", "led", "Bulk Opening Balances"),
                ("reports/cash-book", "led", "Cash Book"),
                ("reports/bank-book", "bank", "Bank Book"),
            ]),
            ("Day book", [
                ("daybook", "led", "Day Book"),
            ]),
            ("Banking", [
                ("bank-accounts", "bank", "Bank Accounts"),
                ("bank-recon", "bank", "Bank Reconciliation"),
            ]),
        ],
    },
    {
        "key": "reports",
        "label": "Reports",
        "icon": "rep",
        "groups": [
            ("Analysis", [
                ("reports/analytics", "rep", "Analytics Overview"),
            ]),
            ("Financial statements", [
                ("reports/trial-balance", "rep", "Trial Balance"),
                ("reports/pnl", "rep", "Profit &amp; Loss"),
                ("reports/balance-sheet", "rep", "Balance Sheet"),
            ]),
            ("Receivables &amp; payables", [
                ("reports/ar-ageing", "rep", "Receivables Ageing"),
                ("reports/ap-ageing", "rep", "Payables Ageing"),
            ]),
            ("GST &amp; tax working papers", [
                ("reports/gst", "gst", "GST Summary &amp; GSTR-1"),
                ("reports/gstr3b", "gst", "GSTR-3B Working"),
                ("gstr2b", "gst", "GSTR-2B Reconciliation"),
            ]),
        ],
    },
    {
        "key": "masters",
        "label": "Masters",
        "icon": "cust",
        "groups": [
            ("Parties", [
                ("customers", "cust", "Customers"),
                ("vendors", "cust", "Vendors"),
            ]),
            ("Products", [
                ("items", "item", "Items"),
            ]),
        ],
    },
    {
        "key": "settings",
        "label": "Settings",
        "icon": "gear",
        "groups": [
            ("Workspace", [
                ("businesses", "gear", "Businesses"),
                ("users", "cust", "Team &amp; Roles"),
                ("settings", "gear", "Business Settings"),
            ]),
            ("Controls", [
                ("backup", "audit", "Backups"),
                ("audit", "audit", "Audit Log"),
            ]),
        ],
    },
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


def nav_html(active: str) -> str:
    """Render the Tally-style top menu with grouped dropdowns."""
    out = []
    for item in NAV:
        links = [link for _group, group_links in item["groups"] for link in group_links]
        is_parent = any(path == active for path, _ico, _label in links)
        if not item["groups"]:
            cls = "navlink on" if item["href"] == active else "navlink"
            out.append(f'<a class="{cls}" href="/{item["href"]}">{icon(item["icon"])}<span>{item["label"]}</span></a>')
            continue
        cls = "menu on" if is_parent else "menu"
        chev = ('<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                f'{ICONS["chev"]}</svg>')
        out.append(f'<details class="{cls}"><summary>{icon(item["icon"])}'
                   f'<span>{item["label"]}</span>{chev}</summary>'
                   f'<div class="menu-panel">')
        for group, group_links in item["groups"]:
            out.append(f'<div class="menu-group"><div class="menu-title">{group}</div>')
            for path, ico, label in group_links:
                link_cls = " on" if path == active else ""
                out.append(f'<a class="{link_cls.strip()}" href="/{path}">{icon(ico)}<span>{label}</span></a>')
            out.append('</div>')
        out.append('</div></details>')
    return "".join(out)


def theme_for(user) -> str:
    """Return the saved theme for a user, falling back safely for old rows."""
    if not user:
        return DEFAULT_THEME
    try:
        value = user["theme"]
    except (IndexError, KeyError):
        return DEFAULT_THEME
    return value if value in THEMES else DEFAULT_THEME


def theme_options(current: str) -> str:
    """Render the four saved-palette choices without changing page layout."""
    current = current if current in THEMES else DEFAULT_THEME
    out = []
    for key, meta in THEMES.items():
        checked = " checked" if key == current else ""
        swatches = "".join(
            f'<i style="background:{color}" aria-hidden="true"></i>'
            for color in meta["swatches"])
        out.append(
            f'<label class="theme-option"><input type="radio" name="theme" value="{key}"{checked}>'
            f'<span class="theme-preview" aria-hidden="true">{swatches}</span>'
            f'<span class="theme-name">{esc(meta["label"])}</span>'
            f'<span class="theme-desc">{esc(meta["description"])}</span></label>')
    return "".join(out)


def layout(title: str, body: str, active: str = "", user=None, tenant=None) -> str:
    nav = nav_html(active)
    theme = theme_for(user)
    who = ""
    if user:
        who = (f'<div class="userbox"><div class="usertext"><b>{esc(user["full_name"])}</b>'
               f'{esc(tenant["name"]) if tenant else ""}</div>'
               f'<a class="btn ghost small" href="/businesses">Businesses</a>'
               f'<form method="post" action="/logout" style="display:inline;margin:0">'
               f'<button class="btn ghost small" type="submit">Sign out</button></form></div>')
    return f"""<!doctype html><html lang="en" data-theme="{theme}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="description" content="ARTHIVIO private accounting workspace: double-entry books, GST working papers and financial statements.">
<title>{esc(title)} · {APP_NAME}</title><style>{CSS}</style></head>
<body><div class="shell">
<header class="topbar"><div class="topbar-inner">
  <a class="brand" href="/" aria-label="ARTHIVIO dashboard">{LOGO}<div><span class="name">ARTHIVIO</span><span class="tag">Smarter Finance</span></div></a>
  <nav class="mainnav" aria-label="Main navigation">{nav}</nav>
  {who}
</div></header>
<main class="main">
  <div class="top"><h1>{esc(title)}</h1></div>
  {body}
  <p class="footer-note">{APP_NAME} · amounts in INR · all figures derived from posted documents and journal entries.</p>
</main></div>
<script>
(() => {{
  const menus = Array.from(document.querySelectorAll('.menu'));
  const closeOthers = keep => menus.forEach(m => {{ if (m !== keep) m.open = false; }});
  menus.forEach(menu => {{
    menu.addEventListener('toggle', () => {{ if (menu.open) closeOthers(menu); }});
  }});
  document.addEventListener('click', event => {{
    if (!event.target.closest('.menu')) closeOthers(null);
  }});
  document.addEventListener('keydown', event => {{
    if (event.key === 'Escape') closeOthers(null);
  }});
}})();
</script>
</body></html>"""


def login_page(error: str = "", theme: str = DEFAULT_THEME) -> str:
    theme = theme if theme in THEMES else DEFAULT_THEME
    err = f'<div class="err">{esc(error)}</div>' if error else ""
    return f"""<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
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


L_ICONS = {
    "grid": '<path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/>',
    "invoice": '<path d="M6 3h9l3 3v15H6zM15 3v4h4M9 11h6M9 15h6M9 19h3"/>',
    "cart": '<path d="M3 4h2l2.2 10.2a2 2 0 002 1.6h8.4a2 2 0 002-1.6L21 7H6M9 21a1 1 0 100-2 1 1 0 000 2zM18 21a1 1 0 100-2 1 1 0 000 2z"/>',
    "box": '<path d="M4 7l8-4 8 4v10l-8 4-8-4V7zM12 11v10M4 7l8 4 8-4"/>',
    "bank": '<path d="M3 9l9-5 9 5M5 9v9M9 9v9M15 9v9M19 9v9M3 21h18"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20V7"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.4 8-8 9-4.6-1-8-4-8-9V6l8-3z"/><path d="M8 12l2.5 2.5L16 9"/>',
    "cloud": '<path d="M7 18a4 4 0 01-.4-8A6 6 0 0118 11a3.5 3.5 0 01-.5 7H7z"/>',
    "lock": '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 018 0v3"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>',
    "trend": '<path d="M3 17l6-6 4 4 7-8M15 7h5v5"/>',
    "users": '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.2 2.7-5 6-5s6 1.8 6 5M16 5a3 3 0 010 6M18 14c2.2.5 3 2 3 4"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/>',
    "audit": '<path d="M5 3h14v18H5zM9 8h6M9 12h6M9 16h3"/>',
    "wallet": '<path d="M3 6h18v14H3zM3 10h18M16 15h2"/>',
    "gst": '<path d="M19 5L5 19M7.5 7.5a2 2 0 100-4 2 2 0 000 4zM16.5 20.5a2 2 0 100-4 2 2 0 000 4z"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "calc": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 19h.01M12 19h.01M16 19h.01"/>',
    "spark": '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z"/><path d="M19 15l.7 1.8L21.5 18l-1.8.7L19 21l-.7-2.3L16.5 18l1.8-1.2L19 15z"/>',
    "building": '<path d="M4 21V8l8-4v17M12 21V11l8 4v6M7 10h2M7 14h2M7 18h2M16 16h1M16 19h1"/>',
    "gear": '<circle cx="12" cy="12" r="3.1"/><path d="M19 12a7 7 0 00-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 00-2-1.2L14.2 3h-4.4l-.3 2.6a7 7 0 00-2 1.2l-2.4-1-2 3.4 2 1.6A7 7 0 005 12c0 .4 0 .8.1 1.2l-2 1.6 2 3.4 2.4-1a7 7 0 002 1.2l.3 2.6h4.4l.3-2.6a7 7 0 002-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z"/>',
    "bell": '<path d="M6 9a6 6 0 1112 0c0 7 3 7 3 9H3c0-2 3-2 3-9zM10 21h4"/>',
    "chev": '<path d="M6 9l6 6 6-6"/>',
    "check": '<path d="M4 12l5 5L20 6"/>',
    "play": '<path d="M8 5l11 7-11 7z"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "headset": '<path d="M4 13a8 8 0 0116 0M4 13v5a2 2 0 002 2h2v-7H6M20 13v5a2 2 0 01-2 2h-2v-7h2"/>',
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 9a7 7 0 0111.6-2L20 12M4 12l2.3 5a7 7 0 0011.6-2"/>',
    "scale": '<path d="M4 20V10M10 20V4M16 20v-7M22 20V7"/>',
    "arrowup": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    "palette": '<circle cx="12" cy="12" r="9"/><circle cx="9" cy="9" r="1.1"/><circle cx="15" cy="9" r="1.1"/><circle cx="9" cy="15" r="1.1"/><circle cx="15" cy="15" r="1.1"/>',
}


def l_icon(name: str, cls: str = "lp-ico") -> str:
    path = L_ICONS.get(name, L_ICONS["grid"])
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            f'{path}</svg>')


LANDING_CSS = """
*{box-sizing:border-box}
html,body{margin:0;padding:0}
.lp-body{background:#FFFFFF;color:#0B1F3A;overflow-x:hidden;font-family:"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;font-size:16px;line-height:1.5;-webkit-font-smoothing:antialiased}
.lp h1,.lp h2,.lp h3{margin:0;font-weight:650;letter-spacing:-.015em;color:#0B1F3A}
.lp a{text-decoration:none}
.lp-body a{color:var(--lp-primary);text-decoration:none}
.lp-body a:hover{text-decoration:none}
.lp{min-height:100vh}
.lp-skip{position:absolute;left:16px;top:-60px;z-index:100;background:#F6F9FF;color:#0B1F3A!important;padding:10px 14px;border-radius:8px;font-weight:700;box-shadow:0 8px 24px rgba(0,0,0,.2)}
.lp-skip:focus{top:12px}
.lp-ico{width:16px;height:16px;flex:0 0 auto;display:inline-block;vertical-align:middle}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.lp-wrap{max-width:1340px;margin:0 auto;padding:0 28px}

/* Header */
.lp-nav{position:sticky;top:0;z-index:40;background:rgba(255,255,255,.97);border-bottom:1px solid #E6EDF7;backdrop-filter:blur(16px);box-shadow:0 8px 30px rgba(33,37,41,.05)}
.lp-nav-inner{max-width:1400px;margin:auto;padding:0 28px;height:74px;display:flex;align-items:center;gap:18px}
.lp-brand{display:flex;align-items:center;gap:10px;color:#0B1F3A;flex:0 0 auto}
.lp-brand .mark{width:39px;height:39px;display:grid;place-items:center}
.lp-brand .mark svg{width:39px;height:39px}
.lp-name{display:block;font-size:20px;font-weight:800;letter-spacing:.10em;line-height:1;color:#0B1F3A}
.lp-tag{display:block;font-size:9.5px;color:#64748B;margin-top:4px;letter-spacing:.02em}
.lp-menu{display:flex;align-items:center;gap:19px;margin-left:16px}
.lp-menu a{position:relative;display:inline-flex;align-items:center;gap:3px;padding:27px 0;font-size:12.5px;font-weight:600;color:#475569;white-space:nowrap}
.lp-menu a:hover,.lp-menu a.on{color:var(--lp-primary-2)}
.lp-menu a.on:after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;background:var(--lp-primary);border-radius:2px 2px 0 0}
.lp-chev{width:9px;height:9px;color:#64748B;stroke-width:2}
.lp-nav-actions{margin-left:auto;display:flex;align-items:center;gap:10px;flex:0 0 auto}
.lp-icon-btn{position:relative;width:30px;height:30px;border-radius:50%;display:grid;place-items:center;color:#475569;background:#F8FAFC;border:1px solid #E6EDF7}
.lp-icon-btn:hover{color:#1D4ED8;background:#EFF6FF;border-color:#DBEAFE}
.lp-icon-btn .lp-ico{width:14px;height:14px}
.lp-icon-btn .dot{position:absolute;right:5px;top:5px;width:5px;height:5px;border-radius:50%;background:#EF4444;border:1px solid #fff}
.lp-lang{display:flex;align-items:center;gap:4px;font-size:10.5px;font-weight:700;color:#475569;padding:0 2px}
.lp-lang .lp-ico{width:13px;height:13px;color:#64748B}
.lp-user{display:flex;align-items:center;gap:8px;padding:4px 5px;border-radius:999px;color:#0B1F3A!important}
.lp-user:hover{background:#EFF6FF}
.lp-user .avatar{width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,#DBEAFE,#DBEAFE);color:#1D4ED8;font-size:9px;font-weight:800;display:grid;place-items:center;border:1px solid #BFDBFE}
.lp-user b{display:block;font-size:9.5px;line-height:1.15;font-weight:700}
.lp-user span span{display:block;font-size:8px;line-height:1.2;color:#64748B;margin-top:2px}
.lp-theme{position:relative;flex:0 0 auto}
.lp-theme-btn{width:auto;height:30px;padding:0 9px;border-radius:999px;display:inline-flex;align-items:center;gap:5px;color:#475569;background:#F8FAFC;border:1px solid #E6EDF7;cursor:pointer;list-style:none;font-size:10px;font-weight:700;letter-spacing:.01em}
.lp-theme-btn::-webkit-details-marker{display:none}
.lp-theme-btn:hover{color:var(--lp-primary-2);background:#EFF6FF;border-color:#DBEAFE}
.lp-theme-btn .lp-ico{width:14px;height:14px}
.lp-theme-btn .lp-chev{width:9px;height:9px;transform:rotate(90deg)}
.lp-theme-menu{position:absolute;right:0;top:calc(100% + 10px);z-index:90;min-width:194px;background:#fff;border:1px solid #E6EDF7;border-radius:12px;box-shadow:0 18px 45px rgba(11,31,58,.18);padding:7px}
.lp-theme-title{display:block;font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:#64748B;font-weight:800;padding:6px 9px 4px}
.lp-theme-menu a{display:flex;align-items:center;gap:8px;padding:8px 9px;border-radius:8px;font-size:12px;color:#334A66;font-weight:600;white-space:nowrap}
.lp-theme-menu a:hover{background:#F6F9FF;color:#0B1F3A}
.lp-theme-menu a.on{background:#EFF6FF;color:var(--lp-primary-2)}
.lp-theme-menu a i{width:14px;height:14px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #DCE6F2;flex:0 0 auto}
.lp-theme-menu .lp-check{width:14px;height:14px;margin-left:auto;color:var(--lp-primary-2)}
.lp-theme-note{display:block;font-size:9px;line-height:1.35;color:#7C8CA3;padding:6px 9px 3px;border-top:1px solid #EEF3FA;margin-top:4px}

/* Hero */
.lp-hero{position:relative;isolation:isolate;overflow:hidden;padding:64px 0 74px;background:linear-gradient(135deg,var(--lp-hero-a) 0%,var(--lp-hero-b) 55%,var(--lp-hero-c) 100%);color:#F0F9FF;min-height:620px}
.lp-hero-art{position:absolute;inset:0;width:100%;height:100%;z-index:0;pointer-events:none;opacity:.82}
.lp-hero:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,var(--lp-overlay-1) 0%,var(--lp-overlay-2) 34%,var(--lp-overlay-3) 62%,var(--lp-overlay-4) 100%);z-index:1;pointer-events:none}
.lp-hero-inner{position:relative;z-index:2;max-width:1340px;margin:auto;padding:0 28px;display:grid;grid-template-columns:1fr 1.05fr;gap:52px;align-items:center}
.lp-hero-copy{min-width:0}
.lp-eyebrow{display:inline-flex;align-items:center;gap:10px;font-size:10.5px;letter-spacing:.18em;font-weight:800;color:var(--lp-accent)}
.lp-eyebrow span{width:24px;height:1px;background:var(--lp-accent);display:inline-block;box-shadow:0 0 10px var(--lp-accent)}
.lp-hero h1{font-size:clamp(44px,4.5vw,68px);line-height:.95;letter-spacing:-.05em;color:#fff;margin:18px 0 0;max-width:720px;font-weight:800}
.lp-hero h1 em{font-style:normal;color:var(--lp-accent);display:block;padding-bottom:3px}
@supports((background-clip:text) or (-webkit-background-clip:text)){
  .lp-hero h1 em{background:linear-gradient(90deg,var(--lp-accent) 0%,var(--lp-accent-2) 42%,var(--lp-accent-3) 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent}
}
.lp-hero-copy p{font-size:15.5px;line-height:1.72;color:#D4E3F5;max-width:585px;margin:23px 0 0}
.lp-ctas{display:flex;gap:12px;flex-wrap:wrap;margin:30px 0 0}
.lp-btn{display:inline-flex;align-items:center;justify-content:center;gap:9px;border-radius:10px;padding:13px 20px;font-size:13.5px;font-weight:700;transition:transform .16s ease,background .16s ease,box-shadow .16s ease}
.lp-btn:hover{transform:translateY(-1px)}
.lp-btn.primary{background:linear-gradient(135deg,var(--lp-primary-2),var(--lp-primary) 58%,var(--lp-primary-2));color:#fff!important;box-shadow:0 14px 30px rgba(4,22,47,.28)}
.lp-btn.primary:hover{filter:brightness(.93)}
.lp-btn.secondary{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.32);color:#F1F7FF!important}
.lp-btn.secondary:hover{background:rgba(255,255,255,.13)}
.lp-btn.green{background:linear-gradient(135deg,#15803D,#22C55E);color:#fff!important;box-shadow:0 12px 26px rgba(34,197,94,.28)}
.lp-btn.green:hover{background:linear-gradient(135deg,#166534,#22C55E)}
.lp-btn .play{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;border:1px solid rgba(255,255,255,.55);font-size:9px;padding-left:1px}
.lp-btn .play .lp-ico{width:9px;height:9px;stroke-width:2.4;margin-left:1px}
.lp-trust{display:flex;flex-wrap:wrap;gap:9px 20px;margin-top:28px;color:#BBD2EA;font-size:11.5px}
.lp-trust span{display:inline-flex;align-items:center;gap:6px}
.lp-trust i{width:16px;height:16px;border-radius:50%;display:grid;place-items:center;background:var(--lp-primary);color:#EFF6FF;font-style:normal;font-size:9px;font-weight:800}

/* Dashboard preview */
.lp-preview{position:relative;z-index:2;min-width:0;isolation:isolate}
.lp-preview:before{content:"";position:absolute;inset:8% -7% -11%;background:radial-gradient(circle,var(--lp-glow),transparent 67%);filter:blur(24px);z-index:-1;pointer-events:none}
.pv-window{background:#fff;border:1px solid rgba(255,255,255,.55);border-radius:16px;box-shadow:0 34px 80px rgba(0,0,0,.38),0 2px 0 rgba(255,255,255,.6) inset;overflow:hidden;color:#0B1F3A;transform:rotate(-.25deg)}
.pv-top{height:50px;display:flex;align-items:center;gap:9px;padding:0 12px;background:#FBFDFF;border-bottom:1px solid #E6EDF7}
.pv-brand{display:flex;align-items:center;gap:5px;font-size:8.5px;font-weight:800;letter-spacing:.08em;color:#1D4ED8;white-space:nowrap}
.pv-brand svg{width:19px;height:19px}
.pv-search{flex:1;max-width:170px;height:24px;border-radius:999px;background:#EFF6FF;color:#64748B;font-size:8px;display:flex;align-items:center;gap:4px;padding:0 8px;margin-left:5px;white-space:nowrap}
.pv-search .lp-ico{width:10px;height:10px}
.pv-top-icons{display:flex;align-items:center;gap:8px;color:#64748B;margin-left:auto}
.pv-top-icons .lp-ico{width:11px;height:11px}
.pv-company{display:flex;align-items:center;gap:5px;border-left:1px solid #E6EDF7;padding-left:8px;font-size:6.5px;line-height:1.15;color:#64748B}
.pv-company .avatar{width:20px;height:20px;border-radius:50%;background:#DBEAFE;color:#1D4ED8;font-size:6.5px;font-weight:800;display:grid;place-items:center}
.pv-body{display:grid;grid-template-columns:124px 1fr;min-height:424px}
.pv-side{background:linear-gradient(180deg,var(--lp-side-a),var(--lp-side-b));padding:11px 8px;color:#B9D0EA}
.pv-side-item{display:flex;align-items:center;gap:6px;font-size:8.1px;padding:5.5px 7px;border-radius:5px;white-space:nowrap;margin-bottom:1.5px}
.pv-side-item.active{background:linear-gradient(90deg,var(--lp-primary-2),var(--lp-primary));color:#FFFFFF;font-weight:700;box-shadow:0 4px 10px rgba(4,22,47,.32)}
.pv-side .lp-ico{width:10px;height:10px;flex:0 0 auto;stroke-width:1.8}
.pv-main{padding:13px;background:#F7FAFF;min-width:0;overflow:hidden}
.pv-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.pv-head h2{font-size:15px;letter-spacing:-.02em;color:#0B1F3A;line-height:1.1}
.pv-head p{font-size:7px;color:#64748B;margin:3px 0 0}
.pv-date{font-size:6.5px;color:#64748B;background:#EFF6FF;padding:4px 6px;border-radius:5px;white-space:nowrap}
.pv-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:10px}
.pv-kpi{background:#fff;border:1px solid #E6EDF7;border-radius:7px;padding:7px 7px 6px;min-width:0}
.pv-kpi span{display:block;font-size:6.5px;color:#64748B;text-transform:uppercase;letter-spacing:.045em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pv-kpi b{display:block;font-size:12.2px;margin-top:3px;color:#0B1F3A;font-variant-numeric:tabular-nums;white-space:nowrap;letter-spacing:-.02em}
.pv-kpi small{font-size:6.2px;color:#15803D;white-space:nowrap;font-weight:700}
.pv-grid{display:grid;grid-template-columns:1.58fr 1fr;gap:7px;margin-top:7px}
.pv-card{background:#fff;border:1px solid #E6EDF7;border-radius:7px;padding:8px;min-width:0}
.pv-card h3{font-size:8px;color:#475569;line-height:1.2}
.pv-card-head{display:flex;align-items:center;justify-content:space-between;gap:6px}
.pv-legend-inline{display:flex;gap:7px;font-size:6px;color:#64748B;white-space:nowrap}
.pv-legend-inline i{display:inline-block;width:5px;height:5px;border-radius:50%;margin-right:3px}
.pv-legend-inline .blue{background:#2563EB}
.pv-legend-inline .green{background:#22C55E}
.pv-chart{width:100%;height:91px;margin-top:4px;display:block}
.pv-performance{display:flex;align-items:center;gap:9px;margin-top:9px}
.pv-donut{width:78px;height:78px;border-radius:50%;background:conic-gradient(#2563EB 0 48%,#22C55E 48% 72%,#A78BFA 72% 86%,#F59E0B 86% 100%);display:grid;place-items:center;position:relative;flex:0 0 auto}
.pv-donut:after{content:"";position:absolute;inset:13px;background:#fff;border-radius:50%}
.pv-donut b{position:relative;z-index:1;font-size:10.5px;color:#0B1F3A;line-height:1}
.pv-donut small{position:relative;z-index:1;font-size:5.8px;color:#64748B;text-transform:uppercase;letter-spacing:.08em;margin-top:2px}
.pv-donut .donut-label{position:relative;z-index:1;display:grid;place-items:center}
.pv-legend{display:grid;gap:4px;font-size:6.1px;color:#64748B;min-width:0}
.pv-legend span{display:flex;align-items:center;white-space:nowrap}
.pv-legend i{display:inline-block;width:5px;height:5px;border-radius:50%;margin-right:4px;flex:0 0 auto}
.pv-legend b{margin-left:auto;color:#475569;font-weight:700;padding-left:6px}
.pv-quick{display:flex;align-items:center;gap:5px;margin-top:8px;font-size:6.3px;color:#64748B;white-space:nowrap;overflow:hidden}
.pv-quick b{color:#2563EB;font-size:6.5px}
.pv-quick span{display:inline-flex;align-items:center;gap:2px;background:#EFF6FF;border-radius:4px;padding:3px 5px}
.pv-quick .lp-ico{width:8px;height:8px}
.pv-mini{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:7px}
.pv-mini div{background:#fff;border:1px solid #E6EDF7;border-radius:6px;padding:6px 7px;min-width:0}
.pv-mini span{display:block;font-size:6.2px;color:#64748B;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pv-mini b{display:block;font-size:10px;margin-top:2px;white-space:nowrap;color:#0B1F3A}
.pv-mini small{font-size:5.8px;color:#15803D;font-weight:700}
.pv-note{margin-top:7px;font-size:5.9px;color:#64748B;text-align:right;letter-spacing:.02em}

/* Feature band */
.lp-feature-band{padding:32px 0 36px;background:#fff;border-bottom:1px solid #E6EDF7}
.lp-feature-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}
.lp-feature{background:#fff;border:1px solid #E6EDF7;border-radius:14px;padding:17px 14px;display:flex;align-items:flex-start;gap:11px;box-shadow:0 2px 5px rgba(33,37,41,.05);transition:transform .16s ease,box-shadow .16s ease}
.lp-feature:hover{transform:translateY(-3px);box-shadow:0 16px 34px rgba(33,37,41,.10)}
.lp-fi{width:44px;height:44px;border-radius:13px;display:grid;place-items:center;background:#EFF6FF;color:#2563EB;flex:0 0 auto}
.lp-fi .lp-ico{width:21px;height:21px}
.lp-fi.blue{background:#EFF6FF;color:#2563EB}
.lp-fi.violet{background:#F3E8FF;color:#7C3AED}
.lp-fi.green{background:#DCFCE7;color:#22C55E}
.lp-fi.amber{background:#FEF3C7;color:#D97706}
.lp-feature h3{font-size:12.5px;margin:1px 0 4px;letter-spacing:-.015em;line-height:1.2}
.lp-feature p{font-size:10.5px;line-height:1.45;color:#64748B;margin:0}

/* Why */
.lp-why{padding:68px 0 76px;background:#fff;border-bottom:1px solid #E6EDF7}
.lp-why-inner{display:grid;grid-template-columns:.70fr 1.30fr;gap:50px;align-items:center}
.lp-why h2{font-size:clamp(30px,3.2vw,44px);line-height:1.06;letter-spacing:-.04em;margin:0 0 17px;font-weight:750}
.lp-why h2 em{font-style:normal;background:linear-gradient(transparent 72%,#DCFCE7 72%);padding:0 2px}
.lp-kicker{display:block;font-size:10px;letter-spacing:.17em;font-weight:800;color:var(--lp-primary);margin-bottom:12px}
.lp-why-copy p{font-size:14px;line-height:1.72;color:#475569;max-width:390px;margin:0 0 24px}
.lp-why-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.lp-why-card{background:#fff;border:1px solid #E6EDF7;border-radius:14px;padding:16px 12px;min-height:174px;box-shadow:0 3px 10px rgba(33,37,41,.05);transition:transform .16s ease,box-shadow .16s ease}
.lp-why-card:hover{transform:translateY(-3px);box-shadow:0 14px 28px rgba(33,37,41,.10)}
.lp-why-card .lp-fi{width:38px;height:38px;border-radius:11px;margin:0 0 13px}
.lp-why-card .lp-fi .lp-ico{width:18px;height:18px}
.lp-why-card h3{font-size:11.5px;margin-bottom:6px;line-height:1.2}
.lp-why-card p{font-size:10.5px;line-height:1.5;color:#64748B;margin:0}

/* Trust strip */
.lp-proof{background:linear-gradient(90deg,var(--lp-proof-a),var(--lp-proof-b) 55%,var(--lp-proof-a));color:#EFF6FF;padding:32px 0}
.lp-proof-grid{display:grid;grid-template-columns:1.55fr .82fr .72fr .72fr 1fr;gap:24px;align-items:center}
.lp-proof-intro,.lp-mission{display:flex;gap:11px;align-items:flex-start;min-width:0}
.lp-proof-intro .lp-ico,.lp-mission .lp-ico{width:24px;height:24px;color:var(--lp-accent);flex:0 0 auto;margin-top:2px}
.lp-proof-intro b,.lp-mission b{display:block;font-size:12.5px;color:#fff;line-height:1.3}
.lp-proof-intro span{display:block;font-size:9.5px;line-height:1.5;color:#9EBBD9;margin-top:3px}
.lp-proof-stat{display:flex;align-items:center;gap:9px;min-width:0}
.lp-proof-stat .lp-ico{width:22px;height:22px;color:var(--lp-accent);flex:0 0 auto}
.lp-proof-stat b{display:block;font-size:20px;line-height:1;color:#fff;font-weight:750;letter-spacing:-.02em}
.lp-proof-stat span{display:block;font-size:9.5px;color:#9EBBD9;margin-top:4px;white-space:nowrap}
.lp-mission b{font-size:12.5px}
.lp-mission em{font-style:normal;display:inline-block;color:var(--lp-accent-3);background:linear-gradient(transparent 72%,rgba(255,255,255,.22) 72%);padding:0 2px}
.lp-demo-note{background:#041326;color:#A9B8CC;font-size:9.5px;text-align:center;padding:9px 18px;letter-spacing:.02em}

@media(max-width:1180px){
  .lp-menu{display:none}
  .lp-why-inner{grid-template-columns:.8fr 1.2fr;gap:32px}
  .lp-why-grid{grid-template-columns:repeat(3,1fr)}
  .lp-why-card{min-height:150px}
}
@media(max-width:1080px){
  .lp-hero-inner{grid-template-columns:1fr;gap:38px}
  .lp-hero-copy{max-width:760px}
  .lp-preview{max-width:720px;margin:0 auto;width:100%}
  .lp-feature-grid{grid-template-columns:repeat(3,1fr)}
  .lp-why-inner{grid-template-columns:1fr;gap:30px}
  .lp-why-copy p{max-width:620px}
  .lp-proof-grid{grid-template-columns:repeat(3,1fr);row-gap:22px}
  .lp-proof-intro{grid-column:span 2}
}
@media(max-width:760px){
  .lp-nav-inner{height:66px;padding:0 18px;gap:12px}
  .lp-brand .mark,.lp-brand .mark svg{width:34px;height:34px}
  .lp-name{font-size:18px}
  .lp-tag{font-size:8.5px}
  .lp-icon-btn,.lp-lang{display:none}
  .lp-theme-btn{width:30px;padding:0;justify-content:center}
  .lp-theme-btn span,.lp-theme-btn .lp-chev{display:none}
  .lp-user b,.lp-user span span{display:none}
  .lp-user{padding:2px}
  .lp-wrap,.lp-hero-inner{padding:0 18px}
  .lp-hero{padding:44px 0 54px;min-height:0}
  .lp-hero:after{background:linear-gradient(180deg,var(--lp-overlay-1),var(--lp-overlay-3))}
  .lp-hero h1{font-size:clamp(42px,12vw,60px)}
  .lp-hero-copy p{font-size:14px}
  .lp-ctas{gap:9px}
  .lp-btn{padding:12px 15px;font-size:12.5px}
  .lp-trust{gap:7px 13px;font-size:10.5px}
  .pv-body{grid-template-columns:92px 1fr;min-height:0}
  .pv-side-item{font-size:7px;padding:5px 4px;gap:4px}
  .pv-main{padding:9px}
  .pv-kpis{grid-template-columns:repeat(2,1fr)}
  .pv-grid{grid-template-columns:1fr}
  .pv-card:nth-child(2){display:none}
  .pv-company{display:none}
  .pv-search{max-width:130px}
  .lp-feature-band{padding:24px 0}
  .lp-feature-grid{grid-template-columns:repeat(2,1fr)}
  .lp-why{padding:52px 0 58px}
  .lp-why-grid{grid-template-columns:repeat(2,1fr)}
  .lp-why-card{min-height:0}
  .lp-proof-grid{grid-template-columns:repeat(2,1fr);gap:18px}
  .lp-proof-intro{grid-column:1/-1}
  .lp-proof-stat span{white-space:normal}
}
@media(max-width:480px){
  .lp-feature-grid,.lp-why-grid,.lp-proof-grid{grid-template-columns:1fr}
  .lp-proof-intro{grid-column:auto}
  .pv-side{display:none}
  .pv-body{grid-template-columns:1fr}
  .pv-kpis{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:380px){
  .lp-wrap,.lp-hero-inner{padding:0 14px}
  .lp-hero h1{font-size:34px}
  .lp-hero-copy p{font-size:13px}
  .pv-search,.pv-top-icons,.pv-quick{display:none}
  .pv-kpis{grid-template-columns:1fr}
  .pv-main{padding:8px}
}
@media(prefers-reduced-motion:reduce){
  .lp *{transition:none!important}
}
"""

LANDING_JS = """
(function(){var d=document.querySelector('details.lp-theme');if(!d)return;document.addEventListener('click',function(e){if(d.open&&!d.contains(e.target))d.open=false;});document.addEventListener('keydown',function(e){if(e.key==='Escape')d.open=false;});})();
"""


def landing_page(theme: str = DEFAULT_THEME) -> str:
    theme = theme if theme in LANDING_THEMES else DEFAULT_THEME
    demo = "/demo" if DEMO_AUTOLOGIN else "/login"
    app_link = demo

    nav_menu = "".join(
        f'<a class="{"on" if label == "Dashboard" else ""}" href="{app_link}">{label}{l_icon("chev", "lp-chev")}</a>'
        for label in ("Dashboard", "Accounting", "Sales &amp; Purchase", "Inventory",
                      "Reports &amp; Analytics", "Business Intelligence")
    )
    theme_links = []
    for key in LANDING_THEMES:
        meta = THEMES[key]
        active = " on" if key == theme else ""
        current = ' aria-current="true"' if key == theme else ""
        check = l_icon("check", "lp-check") if key == theme else ""
        theme_links.append(
            f'<a href="/home?theme={key}" class="{active.strip()}"{current}>'
            f'<i style="background:{meta["swatches"][0]}"></i>{meta["label"]}{check}</a>'
        )
    theme_links = "".join(theme_links)

    feature_cards = "".join(
        f'<article class="lp-feature"><div class="lp-fi {tone}">{l_icon(ico)}</div>'
        f'<div><h3>{title}</h3><p>{copy}</p></div></article>'
        for ico, tone, title, copy in (
            ("calc", "blue", "Accounting &amp; Finance", "Smart. Accurate. Compliant."),
            ("cart", "violet", "Sales &amp; POS", "Fast. Flexible. Everywhere."),
            ("box", "green", "Inventory &amp; Warehouse", "Track. Manage. Optimize."),
            ("chart", "amber", "Business Analytics", "Data to Decisions."),
            ("spark", "violet", "AI Insights", "Smarter Decisions."),
            ("building", "green", "Multi-Company", "Grow Without Limits."),
        )
    )

    why_cards = "".join(
        f'<article class="lp-why-card"><div class="lp-fi {tone}">{l_icon(ico)}</div>'
        f'<h3>{title}</h3><p>{copy}</p></article>'
        for ico, tone, title, copy in (
            ("shield", "green", "100% Data Accuracy", "Your data is always accurate, secure and up to date."),
            ("cloud", "blue", "Offline &amp; Online", "Work anytime, anywhere — online or offline."),
            ("lock", "green", "Advanced Security", "Bank-level security to keep your business data safe."),
            ("headset", "blue", "Global Support", "24/7 support in multiple languages, wherever you are."),
            ("trend", "green", "Scalable for Growth", "From startup to enterprise, we grow with you."),
        )
    )

    preview = f"""
<div class="pv-window" aria-label="Illustrative ARTHIVIO dashboard preview">
  <div class="pv-top">
    <div class="pv-brand">{LANDING_LOGO}<span>ARTHIVIO</span></div>
    <div class="pv-search">{l_icon("search")}<span>Search anything...</span></div>
    <div class="pv-top-icons">{l_icon("bell")}{l_icon("globe")}</div>
    <div class="pv-company"><span class="avatar">GT</span><span>Global Tech<br>Solutions</span></div>
  </div>
  <div class="pv-body">
    <div class="pv-side">
      <div class="pv-side-item active">{l_icon("grid")} Dashboard</div>
      <div class="pv-side-item">{l_icon("invoice")} Accounting</div>
      <div class="pv-side-item">{l_icon("cart")} Sales</div>
      <div class="pv-side-item">{l_icon("cart")} Purchases</div>
      <div class="pv-side-item">{l_icon("box")} Inventory</div>
      <div class="pv-side-item">{l_icon("bank")} Banking</div>
      <div class="pv-side-item">{l_icon("chart")} Reports</div>
      <div class="pv-side-item">{l_icon("chart")} Business Analytics</div>
      <div class="pv-side-item">{l_icon("spark")} AI Insights</div>
      <div class="pv-side-item">{l_icon("gear")} Settings</div>
    </div>
    <div class="pv-main">
      <div class="pv-head">
        <div><h2>Business Overview</h2><p>Sample workspace · synthetic data</p></div>
        <span class="pv-date">01 Apr 2025 - 30 Apr 2025</span>
      </div>
      <div class="pv-kpis">
        <div class="pv-kpi"><span>Total Revenue</span><b>$248,620</b><small>↗ 18.6%</small></div>
        <div class="pv-kpi"><span>Net Profit</span><b>$185,430</b><small>↗ 22.4%</small></div>
        <div class="pv-kpi"><span>Cash Flow</span><b>$96,240</b><small>↗ 12.8%</small></div>
        <div class="pv-kpi"><span>Total Customers</span><b>1,248</b><small>↗ 8.2%</small></div>
      </div>
      <div class="pv-grid">
        <div class="pv-card">
          <div class="pv-card-head"><h3>Revenue &amp; Profit Trend</h3><div class="pv-legend-inline"><span><i class="blue"></i>Revenue</span><span><i class="green"></i>Profit</span></div></div>
          <svg class="pv-chart" viewBox="0 0 360 118" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="lp-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="#2563EB" stop-opacity=".20"/>
                <stop offset="1" stop-color="#2563EB" stop-opacity="0"/>
              </linearGradient>
            </defs>
            <g stroke="#E2E8F0" stroke-width="1">
              <line x1="0" y1="103" x2="360" y2="103"/><line x1="0" y1="76" x2="360" y2="76"/>
              <line x1="0" y1="49" x2="360" y2="49"/><line x1="0" y1="22" x2="360" y2="22"/>
            </g>
            <path d="M0 94 C38 88 58 76 94 78 S146 62 184 61 S234 44 272 46 S326 24 360 20 L360 118 L0 118 Z" fill="url(#lp-area)"/>
            <path d="M0 94 C38 88 58 76 94 78 S146 62 184 61 S234 44 272 46 S326 24 360 20" fill="none" stroke="#2563EB" stroke-width="2.1" stroke-linecap="round"/>
            <path d="M0 106 C40 102 62 96 98 97 S150 88 188 89 S240 80 278 78 S330 66 360 63" fill="none" stroke="#22C55E" stroke-width="1.7" stroke-linecap="round"/>
            <g fill="#2563EB"><circle cx="94" cy="78" r="2.3"/><circle cx="272" cy="46" r="2.3"/></g>
          </svg>
        </div>
        <div class="pv-card">
          <h3>Business Performance</h3>
          <div class="pv-performance">
            <div class="pv-donut"><div class="donut-label"><b>18.3%</b><small>Growth</small></div></div>
            <div class="pv-legend">
              <span><i style="background:#2563EB"></i>Sales <b>48%</b></span>
              <span><i style="background:#22C55E"></i>Services <b>24%</b></span>
              <span><i style="background:#A78BFA"></i>Inventory <b>14%</b></span>
              <span><i style="background:#F59E0B"></i>Other <b>14%</b></span>
            </div>
          </div>
        </div>
      </div>
      <div class="pv-quick"><b>Quick Actions</b><span>{l_icon("invoice")} New Invoice</span><span>{l_icon("users")} Add Customer</span><span>{l_icon("wallet")} Record Payment</span><span>{l_icon("chart")} View Reports</span></div>
      <div class="pv-mini">
        <div><span>Inventory Value</span><b>$112,480 <small>↗ 6.4%</small></b></div>
        <div><span>Accounts Receivable</span><b>$268,900 <small>↗ 9.2%</small></b></div>
        <div><span>Accounts Payable</span><b>$142,350 <small>↘ 4.1%</small></b></div>
      </div>
      <div class="pv-note">Illustrative dashboard · synthetic sample data</div>
    </div>
  </div>
</div>"""

    hero_art = """
<svg class="lp-hero-art" viewBox="0 0 1440 700" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
  <defs>
    <linearGradient id="lp-sky" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#031126"/><stop offset=".50" stop-color="#062A50"/><stop offset="1" stop-color="#0B3F72"/>
    </linearGradient>
    <linearGradient id="lp-bld" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0A2C52"/><stop offset="1" stop-color="#041A33"/>
    </linearGradient>
    <linearGradient id="lp-bld2" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0D365F"/><stop offset="1" stop-color="#06213D"/>
    </linearGradient>
    <linearGradient id="lp-arrow" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#22C55E" stop-opacity="0"/><stop offset=".55" stop-color="#34D399"/><stop offset="1" stop-color="#86EFAC" stop-opacity="0"/>
    </linearGradient>
    <pattern id="lp-windows" width="11" height="15" patternUnits="userSpaceOnUse">
      <rect x="2" y="3" width="2" height="4" fill="#38BDF8" opacity=".38"/>
    </pattern>
    <pattern id="lp-windows2" width="14" height="18" patternUnits="userSpaceOnUse">
      <rect x="3" y="4" width="2.4" height="4.5" fill="#7DD3FC" opacity=".24"/>
    </pattern>
    <radialGradient id="lp-glow" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="#38BDF8" stop-opacity=".40"/><stop offset="1" stop-color="#38BDF8" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1440" height="700" fill="url(#lp-sky)"/>
  <circle cx="1100" cy="340" r="310" fill="url(#lp-glow)"/>
  <g opacity=".62" fill="url(#lp-bld2)">
    <rect x="0" y="390" width="90" height="310"/><rect x="100" y="330" width="70" height="370"/>
    <rect x="180" y="285" width="64" height="415"/><rect x="254" y="410" width="86" height="290"/>
    <rect x="350" y="345" width="78" height="355"/><rect x="438" y="300" width="92" height="400"/>
    <rect x="540" y="390" width="70" height="310"/><rect x="620" y="330" width="86" height="370"/>
    <rect x="716" y="250" width="66" height="450"/><rect x="792" y="320" width="80" height="380"/>
    <rect x="882" y="380" width="72" height="320"/><rect x="964" y="300" width="92" height="400"/>
    <rect x="1066" y="350" width="78" height="350"/><rect x="1154" y="275" width="70" height="425"/>
    <rect x="1234" y="395" width="86" height="305"/><rect x="1330" y="335" width="110" height="365"/>
  </g>
  <g fill="url(#lp-bld)">
    <rect x="0" y="450" width="118" height="250"/><rect x="130" y="382" width="84" height="318"/>
    <rect x="226" y="330" width="72" height="370"/><rect x="310" y="455" width="96" height="245"/>
    <rect x="418" y="370" width="82" height="330"/><rect x="512" y="315" width="96" height="385"/>
    <rect x="620" y="410" width="78" height="290"/><rect x="710" y="278" width="70" height="422"/>
    <rect x="792" y="350" width="92" height="350"/><rect x="896" y="428" width="74" height="272"/>
    <rect x="982" y="352" width="88" height="348"/><rect x="1082" y="300" width="74" height="400"/>
    <rect x="1168" y="410" width="92" height="290"/><rect x="1272" y="345" width="168" height="355"/>
  </g>
  <g fill="url(#lp-windows)" opacity=".75">
    <rect x="0" y="450" width="118" height="250"/><rect x="130" y="382" width="84" height="318"/>
    <rect x="226" y="330" width="72" height="370"/><rect x="310" y="455" width="96" height="245"/>
    <rect x="418" y="370" width="82" height="330"/><rect x="512" y="315" width="96" height="385"/>
    <rect x="620" y="410" width="78" height="290"/><rect x="710" y="278" width="70" height="422"/>
    <rect x="792" y="350" width="92" height="350"/><rect x="896" y="428" width="74" height="272"/>
    <rect x="982" y="352" width="88" height="348"/><rect x="1082" y="300" width="74" height="400"/>
    <rect x="1168" y="410" width="92" height="290"/><rect x="1272" y="345" width="168" height="355"/>
  </g>
  <g fill="url(#lp-windows2)" opacity=".55">
    <rect x="130" y="382" width="84" height="318"/><rect x="310" y="455" width="96" height="245"/>
    <rect x="512" y="315" width="96" height="385"/><rect x="792" y="350" width="92" height="350"/>
    <rect x="1082" y="300" width="74" height="400"/><rect x="1272" y="345" width="168" height="355"/>
  </g>
  <rect y="628" width="1440" height="72" fill="#03162C" opacity=".92"/>
  <g stroke="#2B7BAA" stroke-width="1" opacity=".22">
    <path d="M0 646h1440M0 662h1440M0 678h1440M0 694h1440"/>
    <path d="M120 654h170M420 670h250M830 646h180M1140 682h210" opacity=".6"/>
  </g>
  <path d="M70 654 C420 610 636 468 1002 330" fill="none" stroke="url(#lp-arrow)" stroke-width="24" opacity=".18" stroke-linecap="round"/>
  <path d="M958 306 L1058 312 L1004 382 Z" fill="#34D399" opacity=".16"/>
</svg>"""

    return f"""<!doctype html><html lang="en" data-theme="{theme}" style="{landing_theme_style(theme)}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="index,follow">
<meta name="theme-color" content="#0B1F3A">
<meta name="description" content="ARTHIVIO brings together accounting, finance, inventory, analytics and AI in one powerful platform for businesses of every size.">
<title>ARTHIVIO · Smarter Finance. Stronger Business.</title>
<style>{LANDING_CSS}</style></head>
<body class="lp-body"><div class="lp">
<a class="lp-skip" href="#main">Skip to content</a>
<header class="lp-nav"><div class="lp-nav-inner">
  <a class="lp-brand" href="/"><span class="mark">{LANDING_LOGO}</span><span><span class="lp-name">ARTHIVIO</span><span class="lp-tag">Business, Seen Clearly.</span></span></a>
  <nav class="lp-menu" aria-label="Main navigation">{nav_menu}</nav>
  <div class="lp-nav-actions">
    <details class="lp-theme">
      <summary class="lp-theme-btn" aria-label="Choose background colour" title="Choose background colour">{l_icon("palette")}<span>Colour</span>{l_icon("chev", "lp-chev")}</summary>
      <div class="lp-theme-menu"><span class="lp-theme-title">Landing colour</span>{theme_links}<span class="lp-theme-note">Workspace theme: Settings → Appearance.</span></div>
    </details>
    <a class="lp-icon-btn" href="{app_link}" aria-label="Settings">{l_icon("gear")}</a>
    <a class="lp-icon-btn" href="{app_link}" aria-label="Notifications">{l_icon("bell")}<span class="dot"></span></a>
    <span class="lp-lang">{l_icon("globe")} EN {l_icon("chev", "lp-chev")}</span>
    <a class="lp-user" href="/login"><span class="avatar" aria-hidden="true">BU</span><span><b>Welcome</b><span>Business User</span></span><span class="sr-only">Sign in</span></a>
  </div>
</div></header>

<main id="main">
<section class="lp-hero">
  {hero_art}
  <div class="lp-hero-inner">
    <div class="lp-hero-copy">
      <div class="lp-eyebrow"><span></span>GLOBAL BUSINESS MANAGEMENT PLATFORM</div>
      <h1>Smarter Finance.<em>Stronger Business.</em></h1>
      <p>ARTHIVIO brings together accounting, finance, inventory, analytics and AI — in one powerful platform. Built for businesses of every size. Trusted worldwide.</p>
      <div class="lp-ctas">
        <a class="lp-btn primary" href="{demo}">Get Started Free {l_icon("arrow")}</a>
        <a class="lp-btn secondary" href="{demo}"><span class="play">{l_icon("play")}</span> Watch Demo</a>
      </div>
      <div class="lp-trust">
        <span><i>✓</i> Secure</span><span><i>✓</i> Scalable</span>
        <span><i>✓</i> Multi-Language</span><span><i>✓</i> Global Ready</span>
      </div>
    </div>
    <div class="lp-preview" id="preview">{preview}</div>
  </div>
</section>

<section class="lp-feature-band" id="features"><div class="lp-wrap">
  <div class="lp-feature-grid">{feature_cards}</div>
</div></section>

<section class="lp-why" id="why"><div class="lp-wrap">
  <div class="lp-why-inner">
    <div class="lp-why-copy">
      <span class="lp-kicker">WHY ARTHIVIO?</span>
      <h2>Everything You Need to Run Your Business — <em>Smarter.</em></h2>
      <p>From daily operations to strategic decisions, ARTHIVIO gives you the power of real-time data, advanced analytics and automation — all in one platform.</p>
      <a class="lp-btn green" href="{demo}">Explore All Features {l_icon("arrow")}</a>
    </div>
    <div class="lp-why-grid">{why_cards}</div>
  </div>
</div></section>

<section class="lp-proof" id="trust"><div class="lp-wrap"><div class="lp-proof-grid">
  <div class="lp-proof-intro">{l_icon("globe")}<div><b>Trusted by Businesses Worldwide</b><span>Retail · Manufacturing · Trading · Services · Healthcare · Education · and more...</span></div></div>
  <div class="lp-proof-stat">{l_icon("users")}<div><b>50,000+*</b><span>Happy Businesses</span></div></div>
  <div class="lp-proof-stat">{l_icon("globe")}<div><b>120+*</b><span>Countries</span></div></div>
  <div class="lp-proof-stat">{l_icon("shield")}<div><b>99.99%*</b><span>Uptime</span></div></div>
  <div class="lp-mission">{l_icon("trend")}<div><b>Your Growth.<br><em>Our Mission.</em></b></div></div>
</div></div></section>
<div class="lp-demo-note">Local prototype ? *illustrative marketing metrics, not verified production figures ? demo data is synthetic.</div>
</main>
</div>
<script>{LANDING_JS}</script>
</body></html>"""


def kpi(label: str, value: str, sub: str = "") -> str:
    return f'<div class="card kpi"><div class="lbl">{esc(label)}</div><div class="val">{esc(value)}</div><div class="sub">{esc(sub)}</div></div>'


class Handler(BaseHTTPRequestHandler):
    server_version = "ARTHIVIO/0.12"

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

    def _demo_login(self, conn):
        """Local-only convenience login for the synthetic demo.

        Disabled unless ARTHIVIO_DEMO_AUTOLOGIN=1 and the request comes from
        loopback. It never runs on a remotely reachable server.
        """
        if not DEMO_AUTOLOGIN:
            return self._send("Not found", 404)
        host = (self.client_address[0] or "").lower()
        if not (host in ("127.0.0.1", "::1") or host.startswith("127.")):
            return self._send("Not found", 404)
        row = conn.execute(
            "SELECT u.id AS user_id, m.tenant_id FROM user u"
            " JOIN membership m ON m.user_id=u.id"
            " JOIN tenant t ON t.id=m.tenant_id"
            " WHERE u.email=? AND u.status='active' AND m.status='active'"
            " AND m.role='owner' AND t.status='active'"
            " ORDER BY u.created_at LIMIT 1", (DEMO_EMAIL,),
        ).fetchone()
        if not row:
            return self._send("Demo owner not found", 404)
        token, _csrf = security.create_session(conn, row["user_id"], row["tenant_id"],
                                               self.client_address[0])
        acct.audit(conn, row["tenant_id"], row["user_id"], "auth.demo_login", "session",
                   meta={"mode": "loopback_autologin", "email": DEMO_EMAIL})
        return self._redirect("/", {
            "Set-Cookie": f"sid={token}; HttpOnly; SameSite=Lax; Path=/",
            "Cache-Control": "no-store",
        })

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

    def _serve_static(self, path: str):
        """Serve only known, flat static assets; reject traversal and unknown files."""
        name = path[len("/static/"):]
        allowed = {
            "echarts.min.js": "application/javascript; charset=utf-8",
            "ECHARTS_NOTICE.txt": "text/plain; charset=utf-8",
        }
        content_type = allowed.get(name)
        if not content_type:
            return self._send("Not found", 404)
        full = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(full):
            return self._send("Not found", 404)
        with open(full, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict | list, status: int = 200,
              headers: dict | None = None):
        """Send a stable UTF-8 JSON response with no-store and security headers."""
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Vary", "Cookie")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _form(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        content_type = (self.headers.get("Content-Type") or "").lower()
        self._uploaded_files = {}
        if content_type.startswith("multipart/form-data"):
            return self._multipart_form(raw, self.headers.get("Content-Type") or "")
        return urllib.parse.parse_qs(raw.decode("utf-8", errors="replace"),
                                     keep_blank_values=True)

    def _multipart_form(self, raw: bytes, content_type: str) -> dict:
        """Parse a small multipart upload without the removed cgi module.

        Text fields are returned in the same list shape as parse_qs. File parts
        are kept only for this request in self._uploaded_files.
        """
        envelope = (
            b"Content-Type: " + content_type.encode("latin-1", errors="replace")
            + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
        )
        try:
            message = BytesParser(policy=email_policy).parsebytes(envelope)
        except Exception:  # noqa: BLE001 - malformed multipart is a client error
            return {}
        form: dict[str, list[str]] = {}
        files: dict[str, dict] = {}
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                files[name] = {
                    "filename": filename,
                    "content": payload,
                    "content_type": part.get_content_type(),
                }
            else:
                charset = part.get_content_charset() or "utf-8"
                form.setdefault(name, []).append(
                    payload.decode(charset, errors="replace")
                )
        self._uploaded_files = files
        return form

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
                return self._send(login_page(theme=self._cookies().get("ui_theme", DEFAULT_THEME)))
            if path == "/health":
                return self._send("ok")
            if path.startswith("/static/"):
                return self._serve_static(path)
            if path == "/demo":
                return self._demo_login(conn)
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
            landing_theme = self._cookies().get("ui_theme", DEFAULT_THEME)
            if landing_theme not in LANDING_THEMES:
                landing_theme = DEFAULT_THEME
            requested_theme = (q.get("theme") or [None])[0]
            if requested_theme in LANDING_THEMES and (path == "/home" or (path == "/" and not sess)):
                return self._redirect(path, {
                    "Set-Cookie": f"ui_theme={requested_theme}; Path=/; Max-Age=31536000; SameSite=Lax",
                    "Cache-Control": "no-store",
                })
            landing_headers = {"Cache-Control": "no-cache", "Vary": "Cookie"}
            if path == "/home":
                return self._send(landing_page(landing_theme), headers=landing_headers)
            if path == "/" and not sess:
                return self._send(landing_page(landing_theme), headers=landing_headers)
            if not sess:
                if path.startswith("/api/"):
                    return self._json({"error": "Authentication required.", "code": "UNAUTHENTICATED"},
                                      status=401)
                return self._redirect("/login")
            user = conn.execute("SELECT * FROM user WHERE id=?", (sess["user_id"],)).fetchone()
            tenant = conn.execute("SELECT * FROM tenant WHERE id=?", (sess["tenant_id"],)).fetchone()
            if not user or not tenant:
                return self._redirect("/logout")

            if path == "/api/v1/analytics/catalog":
                return self.api_analytics_catalog(conn, user, tenant)
            if path == "/api/v1/analytics/overview":
                return self.api_analytics_overview(conn, user, tenant, q)
            if path == "/api/v1/analytics/insights":
                return self.api_analytics_insights(conn, user, tenant, q)
            if path.startswith("/api/"):
                return self._json({"error": "Not found.", "code": "NOT_FOUND"}, status=404)

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
            if path == "/ledger/account/new":
                return self._send(self.page_account_new(conn, user, tenant, sess, q))
            if re.fullmatch(r"/ledger/account/[0-9a-f]{32}/edit", path):
                return self._send(self.page_account_edit(conn, user, tenant, sess,
                                                         path.split("/")[3], q))
            if re.fullmatch(r"/ledger/account/[0-9a-f]{32}/archive", path):
                return self._send(self.page_account_archive(conn, user, tenant, sess,
                                                            path.split("/")[3], q))
            if path == "/ledger/opening-balances/template.csv":
                return self._opening_template(conn, user, tenant)
            if path == "/ledger/opening-balances":
                return self._send(self.page_opening_import(conn, user, tenant, sess, q))
            if path == "/ledger":
                return self._send(self.page_ledger(conn, user, tenant, q, sess))
            if path == "/bank-accounts":
                return self._send(self.page_bank_accounts(conn, user, tenant, sess, q))
            if path == "/reports/cash-book":
                return self._send(self.page_book(conn, user, tenant, q, "1000", "Cash Book",
                                                 "reports/cash-book"))
            if path == "/reports/bank-book":
                return self._send(self.page_book(conn, user, tenant, q, "1010", "Bank Book",
                                                 "reports/bank-book", bank=True))
            if path == "/reports/trial-balance":
                return self._send(self.page_tb(conn, user, tenant, q))
            if path == "/reports/pnl":
                return self._send(self.page_pnl(conn, user, tenant, q))
            if path == "/reports/balance-sheet":
                return self._send(self.page_bs(conn, user, tenant, q))
            if path == "/reports/analytics":
                return self._send(self.page_analytics(conn, user, tenant, q))
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
                return self._send(self.page_journal(conn, user, tenant, sess, q))
            if re.fullmatch(r"/entries/(cash|bank|journal)", path):
                mode = path.rsplit("/", 1)[1]
                return self._send(self.page_journal(conn, user, tenant, sess, q, mode=mode))
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
            if path == "/export/workbook.xlsx":
                return self.export_workbook(conn, user, tenant, q)
            if path == "/export/powerbi.zip":
                return self.export_powerbi_pack(conn, user, tenant, q)
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
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_POST_BYTES:
                self.close_connection = True
                return self._send(
                    layout("Request too large",
                           '<div class="card pad"><div class="err">That upload is too large. '
                           'The maximum request size is 10 MB.</div></div>'),
                    413)
            form = self._form()

            if path == "/login":
                try:
                    user = security.authenticate(conn, first(form, "email"), first(form, "password"),
                                                 self.client_address[0])
                except security.AuthError as e:
                    return self._send(
                        login_page(e.message, self._cookies().get("ui_theme", DEFAULT_THEME)), 401)
                rows = security.tenants_for(conn, user["id"])
                if not rows:
                    return self._send(
                        login_page("This account has no business workspace yet.",
                                   self._cookies().get("ui_theme", DEFAULT_THEME)), 403)
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
            if path == "/preferences/theme":
                return self._save_theme(conn, user, tenant, form)

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
            if path == "/journal/reverse":
                return self._reverse_journal(conn, user, tenant, form)
            if path == "/accounts":
                return self._create_account(conn, user, tenant, form, sess)
            if path == "/accounts/update":
                return self._update_account(conn, user, tenant, form, sess)
            if path == "/accounts/archive":
                return self._archive_account(conn, user, tenant, form, sess)
            if path == "/accounts/restore":
                return self._restore_account(conn, user, tenant, form, sess)
            if path == "/accounts/merge":
                return self._merge_account(conn, user, tenant, form, sess)
            if path == "/ledger/opening-balances":
                return self._bulk_opening_import(conn, user, tenant, sess, form)
            if path == "/opening-balance":
                return self._set_opening_balance(conn, user, tenant, form)
            if path == "/bank-accounts":
                return self._create_bank_account(conn, user, tenant, form)
            if path == "/customers":
                return self._create_customer(conn, user, tenant, sess, form)
            if path == "/items":
                return self._create_item(conn, user, tenant, sess, form)

            return self._send(layout("Not found", '<div class="card pad">Page not found.</div>', user=user, tenant=tenant), 404)
        finally:
            conn.close()

    # ---------------- pages ----------------
    def api_analytics_catalog(self, conn, user, tenant):
        try:
            security.require(conn, user["id"], tenant["id"], analytics_mod.PERMISSION)
        except security.AuthError as e:
            return self._json({"error": e.message, "code": e.code}, status=403)
        return self._json(analytics_mod.catalog())

    def api_analytics_overview(self, conn, user, tenant, q):
        try:
            security.require(conn, user["id"], tenant["id"], analytics_mod.PERMISSION)
            payload = analytics_mod.overview(
                conn, tenant,
                (q.get("from") or [None])[0],
                (q.get("to") or [None])[0],
            )
        except security.AuthError as e:
            return self._json({"error": e.message, "code": e.code}, status=403)
        except analytics_mod.AnalyticsError as e:
            return self._json({"error": e.message, "code": e.code}, status=400)
        except acct.AccountingError as e:
            return self._json({"error": e.message, "code": e.code}, status=400)
        return self._json(payload)

    def api_analytics_insights(self, conn, user, tenant, q):
        try:
            security.require(conn, user["id"], tenant["id"], analytics_mod.PERMISSION)
            payload = insights_mod.grounded(
                conn, tenant,
                (q.get("from") or [None])[0],
                (q.get("to") or [None])[0],
            )
        except security.AuthError as e:
            return self._json({"error": e.message, "code": e.code}, status=403)
        except analytics_mod.AnalyticsError as e:
            return self._json({"error": e.message, "code": e.code}, status=400)
        except acct.AccountingError as e:
            return self._json({"error": e.message, "code": e.code}, status=400)
        return self._json(payload)

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
  {kpi("Cash + bank", money.fmt(d["cash"]), "cash and all linked bank accounts")}
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
        theme = theme_for(user)
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

        return f"""<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tax Invoice {esc(inv["invoice_no"])} &middot; {esc(t["name"])}</title>
<style>{THEME_CSS}{PRINT_CSS}</style></head><body>
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

    def page_journal(self, conn, user, tenant, sess, q=None, mode: str = "journal") -> str:
        q = q or {}
        accounts = conn.execute(
            "SELECT * FROM account WHERE tenant_id=? AND status='active' ORDER BY code",
            (tenant["id"],)).fetchall()
        account_by_id = {a["id"]: a for a in accounts}
        title_map = {"cash": "Cash entry", "bank": "Bank entry", "journal": "Journal entry"}
        title = title_map.get(mode, "Journal entry")
        active = f"entries/{mode}" if mode in title_map else "entries/journal"

        try:
            security.require(conn, user["id"], tenant["id"], "journal.post")
            can_post = True
        except security.AuthError:
            can_post = False
        try:
            security.require(conn, user["id"], tenant["id"], "ledger.reverse")
            can_reverse = True
        except security.AuthError:
            can_reverse = False

        def tabs_html() -> str:
            return ('<div class="entry-tabs">' + "".join(
                f'<a class="entry-tab{" on" if value == mode else ""}" href="/entries/{value}">'
                f'{label}</a>' for value, label in
                [("cash", "Cash entry"), ("bank", "Bank entry"), ("journal", "Journal entry")])
                + '</div>')

        reverse_id = (q.get("reverse") or [""])[0]
        if reverse_id:
            entry = conn.execute(
                "SELECT * FROM journal_entry WHERE id=? AND tenant_id=?",
                (reverse_id, tenant["id"])).fetchone()
            if not entry:
                body = ('<div class="card pad"><div class="err">Journal entry not found in this business.</div>'
                        '<a class="btn ghost" href="/ledger">Back to ledger</a></div>')
                return layout("Reverse journal entry", body, "entries/journal", user, tenant)
            lines = conn.execute(
                "SELECT l.*, a.code, a.name FROM journal_line l"
                " JOIN account a ON a.id=l.account_id"
                " WHERE l.entry_id=? ORDER BY l.line_no", (entry["id"],)).fetchall()
            first_account = lines[0]["account_id"] if lines else ""
            back = f'/ledger?account={first_account}' if first_account else "/ledger"
            if not can_reverse:
                body = ('<div class="card pad"><div class="err">Your role cannot reverse journal entries.</div>'
                        f'<a class="btn ghost" href="{back}">Back to ledger</a></div>')
                return layout("Reverse journal entry", body, "entries/journal", user, tenant)
            if entry["source_type"] not in ("manual", "opening"):
                body = (f'<div class="card pad"><div class="err">Only manual journals and opening balances can be reversed here. '
                        f'This entry came from <b>{esc(entry["source_type"])}</b>. Use the source document, a credit note, '
                        f'a debit note or a void action for that correction.</div>'
                        f'<a class="btn ghost" href="{back}">Back to ledger</a></div>')
                return layout("Reverse journal entry", body, "entries/journal", user, tenant)
            if entry["status"] == "reversed":
                body = (f'<div class="card pad"><div class="err">Entry {esc(entry["entry_no"])} is already reversed.</div>'
                        f'<a class="btn ghost" href="{back}">Back to ledger</a></div>')
                return layout("Reverse journal entry", body, "entries/journal", user, tenant)
            line_rows = "".join(
                f'<tr><td>{esc(l["code"])}</td><td>{esc(l["name"])}</td>'
                f'<td class="num">{money.fmt(l["debit_paise"]) if l["debit_paise"] else ""}</td>'
                f'<td class="num">{money.fmt(l["credit_paise"]) if l["credit_paise"] else ""}</td></tr>'
                for l in lines)
            body = f"""
{tabs_html()}
<div class="card pad" style="max-width:900px">
<h2>Reverse {esc(entry["entry_no"])}</h2>
<p class="muted">Original date {esc(entry["entry_date"])} · {esc(entry["narration"])}</p>
<div class="table-wrap"><table>
<thead><tr><th>Code</th><th>Account</th><th class="num">Debit</th><th class="num">Credit</th></tr></thead>
<tbody>{line_rows}</tbody></table></div>
<form method="post" action="/journal/reverse" style="margin-top:16px">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="entry_id" value="{esc(entry["id"])}">
<div class="field"><label for="reason">Reversal reason</label>
<input id="reason" name="reason" maxlength="200" required placeholder="e.g. Wrong account selected"></div>
<div class="entry-actions">
<button class="btn" type="submit">Post reversal</button>
<a class="btn ghost" href="{back}">Cancel</a>
</div></form>
<p class="small muted">The original entry stays in the books and is marked reversed. A new mirrored entry is posted with its own audit trail.</p>
</div>"""
            return layout("Reverse journal entry", body, "entries/journal", user, tenant)

        if not can_post:
            body = (tabs_html() + '<div class="card pad"><div class="err">Your role cannot post journal entries. '
                    'Ask an owner, admin or accountant for journal posting permission.</div>'
                    '<a class="btn ghost" href="/ledger">Back to ledger</a></div>')
            return layout(title, body, active, user, tenant)

        bank_accounts = bank_mod.bank_accounts(conn, tenant["id"])
        bank_ids = {a["id"] for a in bank_accounts}
        cash_id = next((a["id"] for a in accounts if a["code"] == "1000"), "")
        bank_id = next((a["id"] for a in bank_accounts if a["code"] == "1010"),
                       bank_accounts[0]["id"] if bank_accounts else "")
        selected = (q.get("account") or [""])[0]
        if mode == "cash":
            first_account = cash_id
            hint = "Row 1 is preselected as Cash. Add the other side of the entry in row 2."
        elif mode == "bank":
            first_account = selected if selected in bank_ids else bank_id
            hint = ("Row 1 is preselected with a bank account. Choose a different bank in row 1 if needed. "
                    "Add the other side of the entry in row 2.")
        else:
            first_account = selected if selected in account_by_id else ""
            hint = "Choose any two or more accounts. Debits must equal credits exactly."

        def account_options(chosen: str) -> str:
            return ('<option value="">— choose account —</option>' + "".join(
                f'<option value="{a["id"]}"{" selected" if a["id"] == chosen else ""}>'
                f'{esc(a["code"])} — {esc(a["name"])}</option>' for a in accounts))

        row_html = ""
        for i in range(4):
            chosen = first_account if i == 0 else ""
            row_html += (
                f'<tr><td><select name="account_id">{account_options(chosen)}</select></td>'
                f'<td><input name="debit" value="" inputmode="decimal" placeholder="0.00"></td>'
                f'<td><input name="credit" value="" inputmode="decimal" placeholder="0.00"></td></tr>')

        narration_hint = {"cash": "Cash receipt or payment", "bank": "Bank receipt or payment",
                          "journal": "Manual journal narration"}.get(mode, "Narration")
        body = f"""
{tabs_html()}
<div class="notice">{esc(hint)}</div>
<form method="post" action="/journal">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="mode" value="{esc(mode)}">
<div class="card pad sect">
<div class="row c3">
<div class="field"><label>Date</label><input type="date" name="entry_date" value="{date.today().isoformat()}" required></div>
<div class="field" style="grid-column:span 2"><label>Narration</label>
<input name="narration" required maxlength="200" placeholder="{esc(narration_hint)}"></div>
</div></div>
<div class="card sect table-wrap"><table>
<thead><tr><th style="width:58%">Account</th><th>Debit</th><th>Credit</th></tr></thead>
<tbody>{row_html}</tbody></table></div>
<div class="entry-actions">
<button class="btn" type="submit">Post {esc(title.lower())}</button>
<a class="btn ghost" href="/ledger">Back to ledger</a>
</div>
<p class="small muted" style="margin-top:12px">Debits must equal credits exactly. Posting is atomic: an unbalanced entry is rejected and nothing is written.</p>
</form>"""
        return layout(title, body, active, user, tenant)

    def page_bank_accounts(self, conn, user, tenant, sess, q) -> str:
        accounts = bank_mod.bank_accounts(conn, tenant["id"])
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
            can_manage = True
        except security.AuthError:
            can_manage = False

        rows = ""
        for a in accounts:
            bank_name = a.get("bank_name") or (tenant["bank_name"] if a["code"] == "1010" else "")
            account_number = a.get("account_number") or (tenant["bank_account"] if a["code"] == "1010" else "")
            ifsc = a.get("ifsc") or (tenant["bank_ifsc"] if a["code"] == "1010" else "")
            branch = a.get("branch") or ""
            holder = a.get("holder_name") or (tenant["name"] if a["code"] == "1010" else "")
            source = ("Business Settings" if not a.get("bank_account_id") else "Bank Accounts")
            details = " · ".join(x for x in [
                esc(bank_name) if bank_name else "Details not set",
                f'A/c {esc(account_number)}' if account_number else "",
                f'IFSC {esc(ifsc)}' if ifsc else "",
                f'Branch {esc(branch)}' if branch else "",
                f'Holder {esc(holder)}' if holder else "",
            ] if x)
            rows += (f'<tr><td><b>{esc(a["code"])}</b><br><span class="small muted">{esc(a["name"])}</span></td>'
                     f'<td>{details}<div class="small muted">{esc(source)}</div></td>'
                     f'<td><a class="small" href="/ledger?account={a["id"]}">Ledger</a> · '
                     f'<a class="small" href="/reports/bank-book?account={a["id"]}">Bank Book</a> · '
                     f'<a class="small" href="/bank-recon?account={a["id"]}">Reconcile</a></td></tr>')
        rows = rows or '<tr><td colspan="3" class="empty">No bank accounts yet.</td></tr>'

        notice = ""
        if q.get("created"):
            notice = '<div class="notice">Bank account created. You can post a bank entry or import a statement now.</div>'
        add_card = ""
        if can_manage:
            try:
                next_code = bank_mod.next_bank_code(conn, tenant["id"])
            except bank_mod.BankError:
                next_code = ""
            add_card = f"""
<div class="card pad sect">
<h2 style="margin-bottom:12px">Add bank account</h2>
<form method="post" action="/bank-accounts">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="row c3">
<div class="field"><label>Ledger code</label><input name="code" maxlength="12" required value="{esc(next_code)}" placeholder="1020"></div>
<div class="field"><label>Ledger name</label><input name="name" maxlength="80" required placeholder="HDFC Current A/c"></div>
<div class="field"><label>Bank name</label><input name="bank_name" maxlength="80" required placeholder="HDFC Bank"></div>
</div>
<div class="row c3">
<div class="field"><label>Account number</label><input name="account_number" maxlength="34" required placeholder="50200012345678"></div>
<div class="field"><label>IFSC</label><input name="ifsc" maxlength="11" placeholder="HDFC0001234"></div>
<div class="field"><label>Branch</label><input name="branch" maxlength="80" placeholder="Andheri West"></div>
</div>
<div class="field"><label>Account holder</label><input name="holder_name" maxlength="120" value="{esc(tenant['name'])}"></div>
<button class="btn" type="submit">Add bank account</button>
</form>
<p class="small muted" style="margin:10px 0 0">This creates a new asset ledger account and links it to the bank book and reconciliation. The original bank account 1010 keeps using Business Settings.</p>
</div>"""
        else:
            add_card = ('<div class="card pad small muted">Your role can view bank accounts but cannot add them. '
                        'Ask an owner, admin or accountant to grant account management permission.</div>')

        body = f"""
{notice}
<div class="sect-head"><div><h2>Bank accounts</h2>
<div class="small muted">Every bank account has its own ledger, bank book and reconciliation.</div></div>
<div class="entry-actions"><a class="btn ghost small" href="/settings">Business Settings</a></div></div>
<div class="card table-wrap sect"><table>
<thead><tr><th>Ledger</th><th>Bank details</th><th>Open</th></tr></thead>
<tbody>{rows}</tbody></table></div>
{add_card}"""
        return layout("Bank accounts", body, "bank-accounts", user, tenant)

    def page_bank_recon(self, conn, user, tenant, sess, q) -> str:
        today = date.today()
        dfrom = (q.get("from") or [fiscal_start(today, tenant["fiscal_year_start_month"])])[0]
        dto = (q.get("to") or [today.isoformat()])[0]
        accounts = bank_mod.bank_accounts(conn, tenant["id"])
        if not accounts:
            body = ('<div class="card pad"><div class="err">No bank account exists in this '
                    'business chart of accounts.</div>'
                    '<a class="btn ghost" href="/bank-accounts">Add a bank account</a></div>')
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
<form method="post" action="/bank-recon/import" enctype="multipart/form-data">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="account_id" value="{esc(account_id)}">
<input type="hidden" name="filename" id="filename" value="">
<div class="row c2">
<div class="field"><label>CSV file (read in browser)</label><input type="file" id="csvfile" accept=".csv,text/csv"></div>
<div class="field"><label>Excel .xlsx file (server-side)</label><input type="file" name="xlsx_file" id="xlsxfile" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"></div>
</div>
<div class="field"><label>Or paste CSV</label><textarea name="csv_text" id="csv_text" rows="5" placeholder="Date,Description,Reference,Debit,Credit,Balance&#10;2026-06-01,NEFT CR SUNDARAM,NEFT-88421,,23600.00,523600.00"></textarea></div>
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
<button class="btn" type="submit">Import statement</button>
<span class="small muted">Columns: Date, Description, Reference, Debit, Credit (or Amount + Dr/Cr). Duplicate rows are skipped. Excel uses the first worksheet; header must be the first non-empty row.</span>
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
<form method="post" action="/gstr2b/import" enctype="multipart/form-data">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="month" value="{esc(month)}">
<input type="hidden" name="filename" id="gstr2b_filename" value="">
<div class="row c2">
<div class="field"><label for="gstr2b_file">CSV file (read in browser)</label><input type="file" id="gstr2b_file" accept=".csv,text/csv"></div>
<div class="field"><label for="gstr2b_xlsx">Excel .xlsx file (server-side)</label><input type="file" name="xlsx_file" id="gstr2b_xlsx" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"></div>
</div>
<div class="field"><label for="gstr2b_text">Or paste CSV</label><textarea name="csv_text" id="gstr2b_text" rows="6" placeholder="Supplier GSTIN,Supplier Name,Invoice No,Invoice Date,Taxable Value,IGST,CGST,SGST,Cess,Invoice Value&#10;27AAACL1234C1Z5,Loom House Pvt Ltd,LH-2026-097,2026-08-10,42000.00,0,3780.00,3780.00,0,49560.00"></textarea></div>
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
<button class="btn" type="submit">Import GSTR-2B</button>
<span class="small muted">Expected columns: GSTIN, invoice no, invoice date, taxable value, IGST, CGST, SGST. Excel uses the first worksheet. This is a working reconciliation aid, not the portal's official schema.</span>
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

    def page_book(self, conn, user, tenant, q, code: str, title: str, active: str,
                  bank: bool = False) -> str:
        """Cash book / bank book from the posted ledger of a control account."""
        if bank:
            accounts = bank_mod.bank_accounts(conn, tenant["id"])
        else:
            accounts = conn.execute(
                "SELECT * FROM account WHERE tenant_id=? AND code=? AND status='active'"
                " ORDER BY name", (tenant["id"], code)).fetchall()
        if not accounts:
            body = (f'<div class="card pad"><div class="err">No {esc(title.lower())} account exists in this '
                    f'business chart of accounts.</div>'
                    + (f'<a class="btn ghost" href="/bank-accounts">Add a bank account</a>' if bank else "")
                    + '</div>')
            return layout(title, body, active, user, tenant)
        account_id = (q.get("account") or [accounts[0]["id"]])[0]
        if account_id not in {a["id"] for a in accounts}:
            account_id = accounts[0]["id"]
        selected = dict(next(a for a in accounts if a["id"] == account_id))
        today = date.today()
        date_from = (q.get("from") or [fiscal_start(today, tenant["fiscal_year_start_month"])])[0]
        date_to = (q.get("to") or [today.isoformat()])[0]
        gl = acct.general_ledger(conn, tenant["id"], account_id, date_from, date_to)
        opts = "".join(
            f'<option value="{a["id"]}" {"selected" if a["id"] == account_id else ""}>{a["code"]} — {esc(a["name"])}</option>'
            for a in accounts)
        rows = "".join(
            f'<tr><td>{esc(r["date"])}</td><td>{esc(r["ref"])}</td><td>{esc(r["narration"])}</td>'
            f'<td class="num">{money.fmt(r["debit"]) if r["debit"] else ""}</td>'
            f'<td class="num">{money.fmt(r["credit"]) if r["credit"] else ""}</td>'
            f'<td class="num">{money.fmt(r["balance"])}</td></tr>' for r in gl["rows"])
        rows = rows or '<tr><td colspan="6" class="empty">No movement in this period</td></tr>'
        bank_meta = ""
        if bank:
            bank_name = selected.get("bank_name") or tenant["bank_name"] or ""
            account_number = selected.get("account_number") or tenant["bank_account"] or ""
            ifsc = selected.get("ifsc") or tenant["bank_ifsc"] or ""
            branch = selected.get("branch") or ""
            holder = selected.get("holder_name") or tenant["name"]
            details = " · ".join(x for x in [
                f'<b>{esc(bank_name)}</b>' if bank_name else "",
                f'A/c {esc(account_number)}' if account_number else "",
                f'IFSC {esc(ifsc)}' if ifsc else "",
                f'Branch {esc(branch)}' if branch else "",
                f'Holder {esc(holder)}' if holder else "",
            ] if x)
            if details:
                bank_meta = f'<div class="card pad small muted" style="margin-bottom:14px">{details}</div>'
        entry_href = f'/entries/bank?account={account_id}' if bank else f'/entries/cash?account={account_id}'
        entry_label = "Bank entry" if bank else "Cash entry"
        body = f"""
<div class="sect-head"><div></div><div class="entry-actions">
<a class="btn small" href="{entry_href}">New {esc(entry_label.lower())}</a>
<a class="btn ghost small" href="/ledger?account={account_id}">Open ledger</a>
{f'<a class="btn ghost small" href="/bank-accounts">Bank accounts</a>' if bank else ''}
</div></div>
{bank_meta}
<form method="get" action="/{active}" class="card pad sect">
<div class="row c4">
<div class="field"><label>Account</label><select name="account">{opts}</select></div>
<div class="field"><label>From</label><input type="date" name="from" value="{esc(date_from)}"></div>
<div class="field"><label>To</label><input type="date" name="to" value="{esc(date_to)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
</div></form>
<div class="card"><table>
<thead><tr><th>Date</th><th>Ref</th><th>Particulars</th><th class="num">Receipts</th><th class="num">Payments</th><th class="num">Balance</th></tr></thead>
<tbody><tr><td colspan="5" class="muted">Opening balance</td><td class="num"><b>{money.fmt(gl["opening"])}</b></td></tr>
{rows}</tbody>
<tfoot><tr><td colspan="5">Closing balance</td><td class="num">{money.fmt(gl["closing"])}</td></tr></tfoot></table></div>
<p class="small muted" style="margin-top:12px">This book is computed from posted journal lines. Nothing is cached or entered directly here.</p>"""
        return layout(f'{title} — {gl["account"]["name"]}', body, active, user, tenant)

    def _account_form(self, action: str, sess, tenant, account=None, profile=None,
                      bank=None, values=None, submit: str = "Create ledger account") -> str:
        profile = profile or {}
        bank = bank or {}
        values = {key: (val[0] if isinstance(val, list) else val)
                  for key, val in (values or {}).items()}

        def v(name: str, default: str = "") -> str:
            if name in values:
                return values.get(name, default) or ""
            return str(profile.get(name, default) or "")

        def money_v(name: str) -> str:
            if name in values:
                return values.get(name, "") or ""
            value = int(profile.get(name, 0) or 0)
            return money.to_str(value) if value else ""

        def pct_v(name: str) -> str:
            if name in values:
                return values.get(name, "") or ""
            value = int(profile.get(name, 0) or 0)
            return f"{value / 100:.2f}".rstrip("0").rstrip(".") if value else ""

        editing = account is not None
        code = (values.get("code") if "code" in values else (account["code"] if editing else "")) or ""
        name = (values.get("name") if "name" in values else (account["name"] if editing else "")) or ""
        account_type = ((values.get("type") if "type" in values
                         else (account["type"] if editing else "asset")) or "asset").lower()
        group_code = ((values.get("group_code") if "group_code" in values
                       else (account["group_code"] if editing else "")) or "")
        if not group_code:
            group_code = acct.default_group_for_type(account_type)
        group = acct.ACCOUNT_GROUPS.get(group_code)
        if group:
            account_type = group["type"]

        type_defs = [("asset", "Asset"), ("liability", "Liability"),
                     ("equity", "Capital / Equity"), ("income", "Revenue / Income"),
                     ("expense", "Expense")]
        if editing:
            identity = f"""
<div class="card pad sect">
<h2 style="margin-bottom:4px">Ledger identity</h2>
<p class="small muted" style="margin:0 0 14px">Code, type and group stay fixed after posting so reports
and prior entries remain comparable. You can correct the display name and profile details.</p>
<div class="row c3">
<div class="field"><label>Code</label><input value="{esc(code)}" readonly></div>
<div class="field"><label>Type</label><input value="{esc(account_type.title())}" readonly></div>
<div class="field"><label>Group</label><input value="{esc(acct.account_group_label(group_code, account_type))}" readonly></div>
</div>
<div class="field"><label>Ledger name</label><input name="name" maxlength="80" required value="{esc(name)}"></div>
</div>"""
        else:
            group_options = ""
            for typ, typ_label in type_defs:
                options = "".join(
                    f'<option value="{g["code"]}" data-type="{g["type"]}"'
                    f' data-hint="{esc(g["hint"])}" data-side="{g["default_side"]}"'
                    f'{" selected" if group_code == g["code"] else ""}>{esc(g["label"])}</option>'
                    for g in acct.account_groups_for_type(typ))
                group_options += f'<optgroup label="{typ_label}">{options}</optgroup>'
            identity = f"""
<div class="card pad sect">
<h2 style="margin-bottom:4px">Account classification</h2>
<p class="small muted" style="margin:0 0 14px">Choose what this account is in your own books: Cash,
Bank, Sundry Debtors, Sundry Creditors, Loan, Purchase, Sales, Suspense and so on. ARTHIVIO derives the
accounting type and normal debit/credit side from your choice.</p>
<div class="row c3">
<div class="field"><label>Ledger code</label><input name="code" maxlength="12" required value="{esc(code)}" placeholder="6050"></div>
<div class="field"><label>Account type / group</label><select name="group_code" id="accountGroup">{group_options}</select></div>
<div class="field"><label>Ledger name</label><input name="name" maxlength="80" required value="{esc(name)}" placeholder="City Hospital Pvt Ltd"></div>
</div>
<p class="small muted" id="groupHint" style="margin:0"></p>
</div>"""

        opening_card = ""
        if not editing:
            opening_side = (values.get("opening_side")
                            or acct.ACCOUNT_GROUPS.get(group_code, {}).get("default_side", "debit"))
            opening_card = f"""
<div class="card pad sect">
<h2 style="margin-bottom:4px">Opening balance</h2>
<p class="small muted" style="margin:0 0 14px">Optional. It posts a balanced journal against Opening
Balance Equity. Leave the amount blank if this account starts at zero; you can add it later from the ledger.</p>
<div class="row c3">
<div class="field"><label>Opening amount</label><input name="opening_amount" inputmode="decimal" value="{esc(values.get("opening_amount", ""))}" placeholder="0.00"></div>
<div class="field"><label>Balance side</label><select name="opening_side" id="openingSide">
<option value="debit"{" selected" if opening_side == "debit" else ""}>Debit (Dr)</option>
<option value="credit"{" selected" if opening_side == "credit" else ""}>Credit (Cr)</option>
</select></div>
<div class="field"><label>As of</label><input type="date" name="opening_as_of" value="{esc(values.get("opening_as_of") or fiscal_start(date.today(), tenant["fiscal_year_start_month"]))}"></div>
</div>
<p class="small muted" style="margin:0">Debit is usual for assets and expenses; credit is usual for
liabilities, equity and income. The date cannot be in the future.</p>
</div>"""

        state_opts = state_options(v("state_code") or tenant["state_code"])
        party_note = ("Saving a Sundry Debtors or Sundry Creditors account also creates a linked customer or "
                      "vendor master. Invoices, bills, receipts and payments then post to this ledger.")
        company_card = f"""
<div class="card pad sect">
<h2 style="margin-bottom:4px">Company, contact and credit details</h2>
<p class="small muted" style="margin:0 0 14px">Optional but recommended. {party_note}</p>
<div class="row c3">
<div class="field"><label>Legal / company name</label><input name="legal_name" maxlength="120" value="{esc(v("legal_name"))}" placeholder="As per GST / PAN"></div>
<div class="field"><label>Contact person</label><input name="contact_person" maxlength="80" value="{esc(v("contact_person"))}"></div>
<div class="field"><label>Phone</label><input name="phone" maxlength="24" value="{esc(v("phone"))}"></div>
</div>
<div class="row c3">
<div class="field"><label>Email</label><input type="email" name="email" maxlength="120" value="{esc(v("email"))}"></div>
<div class="field"><label>Website</label><input name="website" maxlength="120" value="{esc(v("website"))}" placeholder="https://"></div>
<div class="field"><label>Organisation type</label><input name="organisation_type" list="orgTypes" maxlength="80" value="{esc(v("organisation_type"))}" placeholder="Private Limited"></div>
</div>
<datalist id="orgTypes">
<option value="Proprietorship"><option value="Partnership"><option value="LLP">
<option value="Private Limited"><option value="Public Limited"><option value="Trust">
<option value="Society"><option value="Government"><option value="Individual">
</datalist>
<div class="row c3">
<div class="field"><label>Industry / business type</label><input name="industry" list="industryTypes" maxlength="80" value="{esc(v("industry"))}" placeholder="Hospital, School, Retail, Real Estate"></div>
<datalist id="industryTypes">
<option value="Retail"><option value="Wholesale / Trading"><option value="Manufacturing">
<option value="Services"><option value="Hospital / Healthcare"><option value="School / College">
<option value="Real Estate"><option value="Construction"><option value="Transport">
<option value="Hospitality"><option value="NGO"><option value="Multinational"><option value="Other">
</datalist>
<div class="field"><label>Credit days</label><input name="credit_days" inputmode="numeric" value="{esc(v("credit_days") if v("credit_days") != "0" else "")}" placeholder="0"></div>
<div class="field"><label>Credit limit</label><input name="credit_limit" inputmode="decimal" value="{esc(money_v("credit_limit_paise"))}" placeholder="0.00"></div>
</div>
<div class="field"><label>Address</label><textarea name="address" rows="2" maxlength="240" placeholder="Building, street, area">{esc(v("address"))}</textarea></div>
<div class="row c3">
<div class="field"><label>City</label><input name="city" maxlength="60" value="{esc(v("city"))}"></div>
<div class="field"><label>State</label><select name="state_code">{state_opts}</select></div>
<div class="field"><label>PIN code</label><input name="pincode" maxlength="6" inputmode="numeric" value="{esc(v("pincode"))}"></div>
</div>
<div class="row c3">
<div class="field"><label>Country</label><input name="country" maxlength="60" value="{esc(v("country") or "India")}"></div>
<div class="field"><label>GSTIN</label><input name="gstin" maxlength="15" value="{esc(v("gstin"))}" placeholder="27ABCDE1234F1Z5"></div>
<div class="field"><label>PAN</label><input name="pan" maxlength="10" value="{esc(v("pan"))}" placeholder="ABCDE1234F"></div>
</div>
<div class="row c2">
<div class="field"><label>CIN (companies)</label><input name="cin" maxlength="21" value="{esc(v("cin"))}"></div>
<div class="field"><label>Internal notes</label><input name="notes" maxlength="500" value="{esc(v("notes"))}" placeholder="Payment behaviour, agreed terms, etc."></div>
</div>
</div>"""

        bank_card = f"""
<div class="card pad sect">
<h2 style="margin-bottom:4px">Bank details</h2>
<p class="small muted" style="margin:0 0 14px">Used only when the group is <b>Bank Account</b>.
These details drive the bank book and reconciliation; for other groups they are ignored.</p>
<div class="row c3">
<div class="field"><label>Bank name</label><input name="bank_name" maxlength="80" value="{esc(bank.get("bank_name") or values.get("bank_name", ""))}" placeholder="HDFC Bank"></div>
<div class="field"><label>Account number</label><input name="bank_account_number" maxlength="34" value="{esc(bank.get("account_number") or values.get("bank_account_number", ""))}" placeholder="50200012345678"></div>
<div class="field"><label>IFSC</label><input name="ifsc" maxlength="11" value="{esc(bank.get("ifsc") or values.get("ifsc", ""))}" placeholder="HDFC0001234"></div>
</div>
<div class="row c2">
<div class="field"><label>Branch</label><input name="branch" maxlength="80" value="{esc(bank.get("branch") or values.get("branch", ""))}"></div>
<div class="field"><label>Account holder</label><input name="holder_name" maxlength="120" value="{esc(bank.get("holder_name") or values.get("holder_name", "") or tenant["name"])}"></div>
</div>
</div>"""

        loan_card = f"""
<div class="card pad sect">
<h2 style="margin-bottom:4px">Loan / borrowing details</h2>
<p class="small muted" style="margin:0 0 14px">Use this for a <b>Loans (Liability)</b> ledger. The lender
name is required for that group; the rest is optional and never affects posting arithmetic.</p>
<div class="row c3">
<div class="field"><label>Lender name</label><input name="loan_lender" maxlength="120" value="{esc(v("loan_lender"))}" placeholder="HDFC Bank / Director / NBFC"></div>
<div class="field"><label>Loan account no.</label><input name="loan_account_no" maxlength="60" value="{esc(v("loan_account_no"))}"></div>
<div class="field"><label>Sanction date</label><input type="date" name="loan_sanction_date" value="{esc(v("loan_sanction_date"))}"></div>
</div>
<div class="row c4">
<div class="field"><label>Maturity date</label><input type="date" name="loan_maturity_date" value="{esc(v("loan_maturity_date"))}"></div>
<div class="field"><label>Interest % p.a.</label><input name="interest_rate" inputmode="decimal" value="{esc(pct_v("interest_rate_bp"))}" placeholder="9.5"></div>
<div class="field"><label>Tenure (months)</label><input name="tenure_months" inputmode="numeric" value="{esc(v("tenure_months") if v("tenure_months") != "0" else "")}" placeholder="60"></div>
<div class="field"><label>EMI amount</label><input name="emi" inputmode="decimal" value="{esc(money_v("emi_paise"))}" placeholder="0.00"></div>
</div>
<div class="field"><label>Security / collateral</label><input name="security_details" maxlength="240" value="{esc(v("security_details"))}" placeholder="Property, stock, personal guarantee, etc."></div>
</div>"""

        hidden = ""
        if editing:
            hidden = (f'<input type="hidden" name="account_id" value="{esc(account["id"])}">')
        cancel = f'/ledger?account={account["id"]}' if editing else "/ledger"
        return f"""
<form method="post" action="{esc(action)}">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
{hidden}
{identity}
{opening_card}
{company_card}
{bank_card}
{loan_card}
<div class="entry-actions" style="margin-bottom:18px">
<button class="btn" type="submit">{esc(submit)}</button>
<a class="btn ghost" href="{cancel}">Cancel</a>
<span class="small muted">All postings remain balanced and audited.</span>
</div>
</form>
<script>
const accountTypeNames = {{
  asset: 'Asset', liability: 'Liability', equity: 'Capital / Equity',
  income: 'Revenue / Income', expense: 'Expense'
}};
function updateGroupHint(autoSide) {{
  const group = document.getElementById('accountGroup');
  const hint = document.getElementById('groupHint');
  if (!group || !hint) return;
  const option = group.options[group.selectedIndex];
  if (!option) {{ hint.textContent = ''; return; }}
  const typeName = accountTypeNames[option.dataset.type] || '';
  const detail = option.dataset.hint || '';
  hint.textContent = (typeName ? 'Accounting type: ' + typeName + '. ' : '') + detail;
  if (autoSide) {{
    const side = document.getElementById('openingSide');
    if (side && option.dataset.side) side.value = option.dataset.side;
  }}
}}
if (document.getElementById('accountGroup')) {{
  document.getElementById('accountGroup').addEventListener('change', function () {{
    updateGroupHint(true);
  }});
  updateGroupHint(false);
}}
</script>"""

    def page_account_new(self, conn, user, tenant, sess, q, error: str = "") -> str:
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
        except security.AuthError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    '<a class="btn ghost" href="/ledger">Back to ledger</a></div>')
            return layout("New ledger account", body, "ledger", user, tenant)
        form = self._account_form("/accounts", sess, tenant, values=q,
                                  submit="Create ledger account")
        error_html = f'<div class="err" style="margin-bottom:14px">{esc(error)}</div>' if error else ""
        body = f"""
<div class="sect-head"><div><h2>New ledger account</h2>
<div class="small muted">Create the account and capture its full profile in one flow. Product-wise
price, margin and GST are maintained in <a href="/items">Masters → Items</a>, because one ledger can
contain many products.</div></div>
<a class="btn ghost small" href="/ledger">Back to ledger</a></div>
{error_html}
{form}"""
        return layout("New ledger account", body, "ledger", user, tenant)

    def page_account_edit(self, conn, user, tenant, sess, account_id: str, q,
                          error: str = "") -> str:
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
        except security.AuthError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    f'<a class="btn ghost" href="/ledger?account={esc(account_id)}">Back to ledger</a></div>')
            return layout("Edit account", body, "ledger", user, tenant)
        account = conn.execute(
            "SELECT * FROM account WHERE id=? AND tenant_id=?", (account_id, tenant["id"])
        ).fetchone()
        if not account:
            return layout("Account not found",
                          '<div class="card pad">Account not found in this business.</div>',
                          "ledger", user, tenant)
        profile = acct.account_profile(conn, tenant["id"], account_id) or {}
        bank = conn.execute(
            "SELECT * FROM bank_account WHERE tenant_id=? AND account_id=?",
            (tenant["id"], account_id),
        ).fetchone() or {}
        form = self._account_form("/accounts/update", sess, tenant, account=account,
                                  profile=profile, bank=dict(bank), values=q if q else None,
                                  submit="Save account details")
        error_html = f'<div class="err" style="margin-bottom:14px">{esc(error)}</div>' if error else ""
        body = f"""
<div class="sect-head"><div><h2>{esc(account["name"])}</h2>
<div class="small muted">{esc(account["code"])} · {esc(acct.account_group_label(account["group_code"], account["type"]))}</div></div>
<a class="btn ghost small" href="/ledger?account={esc(account_id)}">Back to ledger</a></div>
{error_html}
{form}"""
        return layout(f'Edit {account["name"]}', body, "ledger", user, tenant)

    def page_account_archive(self, conn, user, tenant, sess, account_id: str, q,
                             error: str = "") -> str:
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
        except security.AuthError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    '<a class="btn ghost" href="/ledger">Back to ledger</a></div>')
            return layout("Archive or merge account", body, "ledger", user, tenant)
        account = conn.execute(
            "SELECT * FROM account WHERE id=? AND tenant_id=?", (account_id, tenant["id"])
        ).fetchone()
        if not account:
            return layout("Account not found",
                          '<div class="card pad">Account not found in this business.</div>',
                          "ledger", user, tenant)
        profile = acct.account_profile(conn, tenant["id"], account_id) or {}
        bank_row = conn.execute(
            "SELECT * FROM bank_account WHERE tenant_id=? AND account_id=?",
            (tenant["id"], account_id)).fetchone()
        balance = acct.account_balance(conn, tenant["id"], account_id)
        is_archived = account["status"] == "archived"
        is_system = acct.account_is_system(account)
        party = acct._account_party(conn, tenant["id"], account_id)
        party_type = party[0] if party else ""
        item_refs = conn.execute(
            "SELECT COUNT(*) AS c FROM item WHERE tenant_id=? AND revenue_code=?",
            (tenant["id"], account["code"])).fetchone()["c"]
        merged_target = None
        if account["merged_into_id"]:
            merged_target = conn.execute(
                "SELECT id, code, name FROM account WHERE id=? AND tenant_id=?",
                (account["merged_into_id"], tenant["id"])).fetchone()
        targets = acct.merge_targets(conn, tenant["id"], account_id) if (
            not is_archived and not is_system) else []

        def balance_text(value: int) -> str:
            if not value:
                return money.fmt(0)
            return f'{money.fmt(abs(value))} {"Dr" if value > 0 else "Cr"}'

        error_html = f'<div class="err" style="margin-bottom:14px">{esc(error)}</div>' if error else ""
        status_bits = [f'<span class="pill">{esc(account["status"])}</span>']
        if merged_target:
            status_bits.append(
                f'<span class="small muted">Merged into <a href="/ledger?account={merged_target["id"]}">'
                f'{esc(merged_target["code"])} — {esc(merged_target["name"])}</a></span>')
        if is_archived and account["archived_at"]:
            status_bits.append(f'<span class="small muted">on {esc(account["archived_at"])}</span>')
        summary = f"""
<div class="card pad" style="margin-bottom:14px">
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
<span class="pill">{esc(account["code"])}</span>
<b>{esc(account["name"])}</b>
{"".join(status_bits)}
<span class="small muted" style="margin-left:auto">All-time balance:
<b>{balance_text(balance)}</b></span>
</div>
<div class="small muted" style="margin-top:8px">
{esc(account["type"]).title()} · {esc(acct.account_group_label(account["group_code"], account["type"]))}
{f' · Party: {esc(party_type.title())}' if party_type else ''}
{f' · Bank: {esc(bank_row["bank_name"])} A/c {esc(bank_row["account_number"])}' if bank_row else ''}
{f' · Used by {item_refs} product(s)' if item_refs else ''}
</div>
</div>"""

        if is_archived:
            archived_card = f"""
<div class="card pad" style="margin-bottom:14px;border-color:var(--border-strong)">
<h2 style="margin-bottom:4px">Restore this ledger</h2>
<p class="small muted" style="margin:0 0 12px">Restore makes the account active again. Its history and
current balance stay exactly as posted. If it was merged, the reclassification journal is not reversed;
use a manual journal if the merged balance also needs to move back.</p>
<form method="post" action="/accounts/restore">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="account_id" value="{esc(account_id)}">
<div class="field"><label for="restore_reason">Restore reason (optional)</label>
<input id="restore_reason" name="reason" maxlength="200" placeholder="e.g. Account closed by mistake"></div>
<button class="btn" type="submit">Restore account</button>
<a class="btn ghost" href="/ledger?account={esc(account_id)}">Back to ledger</a>
</form></div>"""
            archive_card = ""
            merge_card = ""
        else:
            archived_card = ""
            if is_system:
                archive_card = ('<div class="card pad" style="margin-bottom:14px"><h2 style="margin-bottom:4px">'
                                'Archive</h2><p class="small muted" style="margin:0">This is a system or '
                                'control ledger. Archive and merge are locked so code-based postings and '
                                'reports keep working.</p></div>')
            elif party_type:
                archive_card = ('<div class="card pad" style="margin-bottom:14px"><h2 style="margin-bottom:4px">'
                                'Archive</h2><p class="small muted" style="margin:0">This ledger is linked to a '
                                'customer or vendor. Archive is unavailable; merge it into another ledger for '
                                'the same party so the party statement and account pointer stay consistent.</p></div>')
            elif item_refs:
                archive_card = (f'<div class="card pad" style="margin-bottom:14px"><h2 style="margin-bottom:4px">'
                                f'Archive</h2><p class="small muted" style="margin:0">This sales ledger is used by '
                                f'{item_refs} product(s). Move those products to another active sales ledger, or '
                                f'merge this ledger into that target, before archiving.</p></div>')
            elif balance:
                archive_card = (f'<div class="card pad" style="margin-bottom:14px"><h2 style="margin-bottom:4px">'
                                f'Archive</h2><p class="small muted" style="margin:0">Archive is available only at '
                                f'an all-time balance of zero. This ledger has {balance_text(balance)}. Merge it into '
                                f'another ledger or post a zeroing journal first.</p></div>')
            else:
                archive_card = f"""
<div class="card pad" style="margin-bottom:14px;border-color:var(--border-strong)">
<h2 style="margin-bottom:4px">Archive this ledger</h2>
<p class="small muted" style="margin:0 0 12px">Archive keeps all posted history but blocks new postings.
It is available only when the all-time balance is exactly zero. No journal is posted by archiving.</p>
<form method="post" action="/accounts/archive" onsubmit="return confirm('Archive this ledger? New postings will be blocked.');">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="account_id" value="{esc(account_id)}">
<div class="field"><label for="archive_reason">Archive reason</label>
<input id="archive_reason" name="reason" maxlength="200" required placeholder="e.g. Obsolete ledger, replaced by 6050"></div>
<button class="btn" type="submit">Archive account</button>
</form></div>"""

            if is_system:
                merge_card = ""
            elif targets:
                target_opts = "".join(
                    f'<option value="{t["id"]}">{esc(t["code"])} — {esc(t["name"])}'
                    f' ({esc(t["group_label"])}) · {balance_text(t["balance"])}</option>'
                    for t in targets)
                hints = []
                if party_type:
                    hints.append("The customer/vendor account pointer is repointed to the target.")
                if item_refs:
                    hints.append(f"{item_refs} product(s) are repointed to the target sales ledger.")
                if account["group_code"] == "bank":
                    hints.append("Bank statement history stays on the archived source ledger.")
                merge_card = f"""
<div class="card pad" style="border-color:var(--border-strong)">
<h2 style="margin-bottom:4px">Merge into another ledger</h2>
<p class="small muted" style="margin:0 0 12px">Merge posts one balanced reclassification journal dated
today for the source's net balance, then archives the source. The source history is never edited.
Both ledgers must have the same accounting type; bank ledgers only merge into bank ledgers and party
ledgers only into the same party.</p>
<form method="post" action="/accounts/merge" onsubmit="return confirm('Merge this ledger and archive the source? A reclassification journal will be posted today.');">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="account_id" value="{esc(account_id)}">
<div class="field"><label for="merge_target">Target ledger</label>
<select id="merge_target" name="target_id" required>{target_opts}</select></div>
<div class="field"><label for="merge_reason">Merge reason</label>
<input id="merge_reason" name="reason" maxlength="200" required placeholder="e.g. Duplicate ledger, same account"></div>
<p class="small muted" style="margin:0 0 12px">Transfer amount: <b>{balance_text(balance)}</b>.
{" ".join(hints)}</p>
<button class="btn" type="submit">Merge and archive</button>
</form></div>"""
            else:
                merge_card = ('<div class="card pad"><h2 style="margin-bottom:4px">Merge into another ledger</h2>'
                              '<p class="small muted" style="margin:0">No compatible active target exists. '
                              'Create another ledger with the same accounting type (and the same party or '
                              'bank group, if this one is linked) first.</p></div>')

        body = f"""
<div class="sect-head"><div><h2>Archive or merge</h2>
<div class="small muted">Close an obsolete ledger without deleting posted history. Every change is
audited and every balance transfer is a balanced journal.</div></div>
<a class="btn ghost small" href="/ledger?account={esc(account_id)}">Back to ledger</a></div>
{error_html}
{summary}
{archived_card}
{archive_card}
{merge_card}
<p class="small muted" style="margin-top:14px">Archiving is not deletion. Reports, ledgers and the audit
trail keep the account code and its posted entries. Merged balances move through a journal, never by
editing posted lines.</p>"""
        return layout("Archive or merge account", body, "ledger", user, tenant)

    def page_opening_import(self, conn, user, tenant, sess, q, values=None,
                            preview=None, error: str = "") -> str:
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
        except security.AuthError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    '<a class="btn ghost" href="/ledger">Back to ledger</a></div>')
            return layout("Bulk opening balances", body, "ledger/opening-balances", user, tenant)

        today = date.today()
        default_date = fiscal_start(today, tenant["fiscal_year_start_month"])
        csv_text = ""
        filename = ""
        if values:
            default_date = values.get("default_as_of") or default_date
            csv_text = values.get("csv_text", "")
            filename = values.get("filename", "")

        notices = ""
        posted = (q.get("posted") or [""])[0]
        if posted:
            notices += (f'<div class="notice">{esc(posted)} opening balance entr'
                        f'{"y" if posted == "1" else "ies"} posted against Opening Balance Equity. '
                        'Open the ledger to review each account.</div>')
        if error:
            notices += f'<div class="err" style="margin-bottom:14px">{esc(error)}</div>'

        preview_card = ""
        if preview:
            error_count = len(preview["errors"])
            net = preview["total_credit"] - preview["total_debit"]
            if net > 0:
                equity_effect = f"{money.fmt(net)} Cr"
            elif net < 0:
                equity_effect = f"{money.fmt(-net)} Dr"
            else:
                equity_effect = "Nil"
            rows_html = ""
            for row in preview["rows"]:
                if row["error"]:
                    check = f'<span class="small" style="color:var(--danger)">{esc(row["error"])}</span>'
                    status = '<span class="badge bad">Fix</span>'
                else:
                    check = '<span class="small muted">Ready</span>'
                    status = '<span class="badge ok">OK</span>'
                amount = money.fmt(row["amount_paise"]) if row["amount_paise"] else esc(row["amount_text"])
                side = {"debit": "Dr", "credit": "Cr"}.get(row["side"], esc(row["side_text"]))
                rows_html += (
                    f'<tr><td>{row["line"]}</td><td><b>{esc(row["code"])}</b></td>'
                    f'<td>{esc(row["account_name"] or "—")}</td><td>{esc(side)}</td>'
                    f'<td class="num">{amount}</td><td>{esc(row["as_of"])}</td>'
                    f'<td>{esc(row["note"])}</td><td>{status}</td><td>{check}</td></tr>'
                )
            errors_html = ""
            if preview["errors"]:
                items = "".join(
                    f'<li>Line {e["line"]}{" · " + esc(e["code"]) if e["code"] else ""}: '
                    f'{esc(e["message"])}</li>'
                    for e in preview["errors"]
                )
                errors_html = (f'<div class="card pad" style="margin-bottom:14px">'
                               f'<h3 style="margin:0 0 8px">Fix these rows before posting</h3>'
                               f'<ul class="small" style="margin:0;padding-left:20px">{items}</ul></div>')
            post_button = ""
            if not preview["errors"] and preview["valid_count"] == preview["count"]:
                post_button = (f'<button class="btn" type="submit" name="action" value="post">'
                               f'Post all {preview["count"]} opening balances</button>')
            preview_card = f"""
<div class="sect">
<div class="sect-head"><div><h2>Preview</h2>
<div class="small muted">Nothing has been posted yet. Each ready row becomes one balanced
opening journal; the net is absorbed by Opening Balance Equity.</div></div>
<span class="badge {'ok' if not preview['errors'] else 'bad'}">
{preview['valid_count']}/{preview['count']} ready</span></div>
<div class="kpis">
  {kpi("Rows", str(preview["count"]), f'{preview["valid_count"]} ready')}
  {kpi("Account Dr openings", money.fmt(preview["total_debit"]), "valid rows")}
  {kpi("Account Cr openings", money.fmt(preview["total_credit"]), "valid rows")}
  {kpi("Opening Balance Equity", equity_effect, "balancing side")}
</div>
{errors_html}
<div class="card table-wrap"><table>
<thead><tr><th>Line</th><th>Code</th><th>Account</th><th>Side</th><th class="num">Amount</th>
<th>As of</th><th>Note</th><th>Status</th><th>Check</th></tr></thead>
<tbody>{rows_html}</tbody></table></div>
<p class="small muted" style="margin-top:10px">Debit and credit openings do not need to match each
other. Every row is a separate balanced journal, so the books stay in balance and Opening Balance
Equity carries the net difference.</p>
</div>"""

        file_script = """
<script>
(function () {
  const file = document.getElementById('opening_file');
  if (!file) return;
  file.addEventListener('change', function () {
    const picked = this.files && this.files[0];
    if (!picked) return;
    document.getElementById('opening_filename').value = picked.name;
    const reader = new FileReader();
    reader.onload = function () {
      document.getElementById('opening_text').value = reader.result;
    };
    reader.readAsText(picked);
  });
})();
</script>"""

        body = f"""
<div class="sect-head"><div><h2>Bulk opening balances</h2>
<div class="small muted">Migrate many ledgers at once from a CSV. Use this only for starting
balances, not for normal transactions.</div></div>
<div class="entry-actions"><a class="btn ghost small" href="/ledger">Back to ledger</a></div></div>
{notices}
<div class="card pad sect">
<h2 style="margin-bottom:8px">How this works</h2>
<p class="small muted" style="margin-top:0">Preview first. Nothing is written until you press
<b>Post all</b>. Each row posts a separate opening journal against
<b>Opening Balance Equity</b>, so every entry is balanced and auditable. Existing opening
balances are rejected and must be reversed first. A future date, a locked period, or a date after
the account's first posted entry is also rejected.</p>
<div class="row c2">
  <div><div class="small muted">Required columns</div><div><code>code, side, amount</code></div></div>
  <div><div class="small muted">Optional columns</div><div><code>as_of, note</code></div></div>
</div>
<div class="small muted" style="margin-top:10px">Example: <code>1000,debit,25000.00,2026-04-01,Cash opening</code>.
<code>side</code> accepts debit/Dr/d or credit/Cr/c. If <code>as_of</code> is blank, the default date below is used.</div>
</div>
<div class="card pad sect">
<h2 style="margin-bottom:12px">Import CSV or Excel</h2>
<form method="post" action="/ledger/opening-balances" enctype="multipart/form-data">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="filename" id="opening_filename" value="{esc(filename)}">
<div class="row c3">
  <div class="field"><label>Default as-of date</label>
  <input type="date" name="default_as_of" required value="{esc(default_date)}"></div>
  <div class="field"><label>CSV file (read in browser)</label>
  <input type="file" id="opening_file" accept=".csv,text/csv,text/plain"></div>
  <div class="field"><label>Excel .xlsx file (server-side)</label>
  <input type="file" name="xlsx_file" id="opening_xlsx" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"></div>
</div>
<div class="field"><label>Or paste CSV rows</label>
<textarea name="csv_text" id="opening_text" rows="10" spellcheck="false"
placeholder="code,side,amount,as_of,note">{esc(csv_text)}</textarea></div>
<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
  <button class="btn" type="submit" name="action" value="preview">Preview / validate</button>
  {post_button if preview else ''}
  <a class="btn ghost" href="/ledger/opening-balances/template.csv">Download CSV template</a>
</div>
</form>
<p class="small muted" style="margin:10px 0 0">Use the first worksheet; the header must be the first non-empty row.
The default date applies only where a row leaves <code>as_of</code> blank. Files are not stored;
the posted journals and audit log are the record.</p>
</div>
{preview_card}
{file_script}"""
        return layout("Bulk opening balances", body, "ledger/opening-balances", user, tenant)

    def page_ledger(self, conn, user, tenant, q, sess) -> str:
        accounts = acct.account_balances(conn, tenant["id"])
        if not accounts:
            return layout("Ledger", '<div class="card pad">No accounts.</div>', "ledger", user, tenant)
        active_accounts = [a for a in accounts if a["status"] == "active"]
        default_account = (active_accounts or accounts)[0]
        account_id = (q.get("account") or [default_account["id"]])[0]
        if account_id not in {a["id"] for a in accounts}:
            account_id = default_account["id"]
        today = date.today()
        date_from = (q.get("from") or [fiscal_start(today, tenant["fiscal_year_start_month"])])[0]
        date_to = (q.get("to") or [today.isoformat()])[0]
        try:
            gl = acct.general_ledger(conn, tenant["id"], account_id, date_from, date_to)
        except acct.AccountingError:
            gl = None
        if not gl:
            return layout("Ledger", '<div class="card pad">Account not found.</div>', "ledger", user, tenant)
        is_archived = gl["account"].get("status") == "archived"

        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
            can_manage = True
        except security.AuthError:
            can_manage = False
        try:
            security.require(conn, user["id"], tenant["id"], "ledger.reverse")
            can_reverse = True
        except security.AuthError:
            can_reverse = False

        profile = acct.account_profile(conn, tenant["id"], account_id) or {}
        bank_row = conn.execute(
            "SELECT * FROM bank_account WHERE tenant_id=? AND account_id=?",
            (tenant["id"], account_id),
        ).fetchone()
        merged_target = None
        if gl["account"].get("merged_into_id"):
            merged_target = conn.execute(
                "SELECT id, code, name FROM account WHERE id=? AND tenant_id=?",
                (gl["account"]["merged_into_id"], tenant["id"])).fetchone()
        details = []
        if profile.get("legal_name"):
            details.append(("Legal name", profile["legal_name"]))
        if profile.get("contact_person"):
            details.append(("Contact person", profile["contact_person"]))
        if profile.get("phone"):
            details.append(("Phone", profile["phone"]))
        if profile.get("email"):
            details.append(("Email", profile["email"]))
        if profile.get("website"):
            details.append(("Website", profile["website"]))
        if profile.get("organisation_type"):
            details.append(("Organisation type", profile["organisation_type"]))
        if profile.get("industry"):
            details.append(("Industry", profile["industry"]))
        address = " · ".join(x for x in [
            profile.get("address"), profile.get("city"),
            profile.get("pincode"), profile.get("country"),
        ] if x)
        if address:
            details.append(("Address", address))
        if profile.get("gstin"):
            details.append(("GSTIN", profile["gstin"]))
        if profile.get("pan"):
            details.append(("PAN", profile["pan"]))
        if profile.get("cin"):
            details.append(("CIN", profile["cin"]))
        if profile.get("credit_days") or profile.get("credit_limit_paise"):
            details.append(("Credit terms", f'{profile.get("credit_days", 0)} day(s) · limit '
                                            f'{money.fmt(profile.get("credit_limit_paise", 0))}'))
        if profile.get("loan_lender"):
            details.append(("Lender", profile["loan_lender"]))
        if profile.get("loan_account_no"):
            details.append(("Loan account", profile["loan_account_no"]))
        if profile.get("loan_sanction_date"):
            details.append(("Sanction date", profile["loan_sanction_date"]))
        if profile.get("loan_maturity_date"):
            details.append(("Maturity date", profile["loan_maturity_date"]))
        if profile.get("interest_rate_bp"):
            details.append(("Interest", f'{profile["interest_rate_bp"] / 100:.2f}% p.a.'))
        if profile.get("tenure_months"):
            details.append(("Tenure", f'{profile["tenure_months"]} month(s)'))
        if profile.get("emi_paise"):
            details.append(("EMI", money.fmt(profile["emi_paise"])))
        if profile.get("security_details"):
            details.append(("Security", profile["security_details"]))
        if profile.get("notes"):
            details.append(("Notes", profile["notes"]))
        if bank_row:
            details.append(("Bank", " · ".join(x for x in [
                bank_row["bank_name"], f'A/c {bank_row["account_number"]}',
                f'IFSC {bank_row["ifsc"]}' if bank_row["ifsc"] else "",
                bank_row["branch"], bank_row["holder_name"],
            ] if x)))
        if is_archived:
            details.append(("Status", f'Archived {gl["account"]["archived_at"] or ""}'.strip()))
            if merged_target:
                details.append(("Merged into",
                                f'{merged_target["code"]} — {merged_target["name"]}'))
        party_link = ""
        if profile.get("party_type") in ("customer", "vendor") and profile.get("party_id"):
            party_link = (f'<a class="small" href="/{profile["party_type"]}s/{profile["party_id"]}">'
                          f'Open {profile["party_type"]} statement</a>')
        profile_actions = ""
        if can_manage:
            merge_note = "Restore / view archive" if is_archived else "Archive or merge"
            profile_actions = (
                f'<a class="btn ghost small" style="margin-left:auto" '
                f'href="/ledger/account/{account_id}/edit">Edit account details</a>'
                f'<a class="btn ghost small" href="/ledger/account/{account_id}/archive">'
                f'{merge_note}</a>')
        detail_rows = "".join(
            f'<tr><td class="muted" style="width:190px">{esc(label)}</td><td>{esc(value)}</td></tr>'
            for label, value in details)
        profile_card = f"""
<details class="card pad" style="margin-bottom:14px" open>
<summary style="cursor:pointer;font-weight:650">Account profile · {esc(acct.account_group_label(gl["account"]["group_code"], gl["account"]["type"]))}{' <span class="pill">archived</span>' if is_archived else ''}</summary>
<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:10px 0 6px">
<span class="small muted">Company, contact, tax and loan details are part of this ledger. They never change posted amounts.</span>
{profile_actions}
</div>
{f'<table><tbody>{detail_rows}</tbody></table>' if detail_rows else '<p class="small muted" style="margin:0">No extra profile details yet. Use Edit account details to add company name, GSTIN, contact, credit terms, bank or loan information.</p>'}
{party_link}
</details>"""

        opening_entry = acct.opening_balance_entry(conn, tenant["id"], account_id)
        is_opening_equity = (gl["account"]["type"] == "equity"
                             and gl["account"]["name"] == acct.OPENING_EQUITY_NAME)
        opening_card = ""
        if opening_entry:
            opening_amount = opening_entry["debit_paise"] or opening_entry["credit_paise"]
            opening_side = "Dr" if opening_entry["debit_paise"] else "Cr"
            reverse_opening = ""
            if can_reverse and not is_archived:
                reverse_opening = (
                    f'<a class="btn ghost small" style="margin-top:10px" '
                    f'href="/journal?reverse={esc(opening_entry["id"])}">Reverse opening entry</a>')
            opening_card = f"""
<details class="card pad" style="margin-bottom:14px">
<summary style="cursor:pointer;font-weight:650">Opening balance entry · {money.fmt(opening_amount)} {opening_side}</summary>
<p class="small muted" style="margin:10px 0 0">Posted as <b>{esc(opening_entry["entry_no"])}</b> on
{esc(opening_entry["entry_date"])} against Opening Balance Equity. To replace it, reverse that entry first;
posted entries are never edited.</p>
{reverse_opening}
</details>"""
        elif is_opening_equity:
            opening_card = """
<div class="card pad small muted" style="margin-bottom:14px">
This equity account is created automatically when the first opening balance is posted. It collects the
other side of opening balances so the books stay balanced.
</div>"""
        elif can_manage and not is_archived:
            default_side = "credit" if gl["account"]["type"] in ("liability", "equity", "income") else "debit"
            open_attr = " open" if q.get("created") else ""
            opening_card = f"""
<details class="card pad" style="margin-bottom:14px"{open_attr}>
<summary style="cursor:pointer;font-weight:650">Set opening balance</summary>
<p class="small muted" style="margin:10px 0">Use this for the starting balance of a new account. It posts a
balanced journal against <b>Opening Balance Equity</b>; it does not edit the account directly. The date must
be on or before the account's first posted transaction. It is normally used for asset, liability and equity
accounts; income/expense openings are for migration only.</p>
<form method="post" action="/opening-balance" style="margin-top:10px">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<input type="hidden" name="account_id" value="{esc(account_id)}">
<div class="row c3">
<div class="field"><label>Opening amount</label><input name="amount" inputmode="decimal" required placeholder="0.00"></div>
<div class="field"><label>Balance</label><select name="side">
<option value="debit"{' selected' if default_side == 'debit' else ''}>Debit (Dr)</option>
<option value="credit"{' selected' if default_side == 'credit' else ''}>Credit (Cr)</option>
</select></div>
<div class="field"><label>As of</label><input type="date" name="as_of" required value="{esc(fiscal_start(today, tenant['fiscal_year_start_month']))}"></div>
</div>
<button class="btn small" type="submit">Post opening balance</button>
</form>
</details>"""

        type_labels = [("asset", "Assets"), ("liability", "Liabilities"), ("equity", "Equity"),
                       ("income", "Income"), ("expense", "Expenses")]

        def balance_label(value: int) -> str:
            if not value:
                return money.fmt(0)
            return f'{money.fmt(abs(value))} {"Dr" if value > 0 else "Cr"}'

        grouped = ""
        for typ, label in type_labels:
            rows_for_type = [a for a in active_accounts if a["type"] == typ]
            if not rows_for_type:
                continue
            links = "".join(
                f'<a class="ledger-item{" on" if a["id"] == account_id else ""}" '
                f'href="/ledger?account={a["id"]}" title="{esc(a["group_label"])}">'
                f'<span class="code">{esc(a["code"])}</span>'
                f'<span class="name">{esc(a["name"])}</span>'
                f'<span class="bal">{balance_label(a["balance"])}</span></a>'
                for a in rows_for_type)
            grouped += f'<div class="ledger-group"><div class="ledger-group-title">{label}</div>{links}</div>'
        archived_accounts = [a for a in accounts if a["status"] == "archived"]
        if archived_accounts:
            archived_links = "".join(
                f'<a class="ledger-item archived{" on" if a["id"] == account_id else ""}" '
                f'href="/ledger?account={a["id"]}" '
                f'title="{esc(a["group_label"])}{" - merged" if a["merged_into_id"] else ""}">'
                f'<span class="code">{esc(a["code"])}</span>'
                f'<span class="name">{esc(a["name"])}</span>'
                f'<span class="pill">archived</span></a>'
                for a in archived_accounts)
            grouped += (
                f'<details class="ledger-group"{" open" if is_archived else ""}>'
                f'<summary class="ledger-group-title" style="cursor:pointer">'
                f'Archived ({len(archived_accounts)})</summary>{archived_links}</details>')

        add_form = ""
        if can_manage:
            add_form = f"""
<div class="ledger-add">
<form method="get" action="/ledger/account/new">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<button class="btn small" type="submit" style="width:100%;justify-content:center">+ Add ledger account</button>
</form>
<a class="btn ghost small" href="/ledger/opening-balances"
style="width:100%;justify-content:center;margin-top:8px">Bulk opening balances</a>
<p class="small muted" style="margin:8px 0 0">Opens the full account form: group, opening balance,
company/contact details, GSTIN/PAN, credit terms, bank or loan details. Use bulk opening balances
to migrate many ledgers from a CSV.</p>
</div>"""

        bank_accounts = bank_mod.bank_accounts(conn, tenant["id"])
        bank_ids = {a["id"] for a in bank_accounts}
        cash_id = next((a["id"] for a in accounts if a["code"] == "1000"), accounts[0]["id"])
        bank_id = next((a["id"] for a in bank_accounts if a["code"] == "1010"),
                       bank_accounts[0]["id"] if bank_accounts else account_id)
        bank_target = account_id if account_id in bank_ids else bank_id
        entry_actions = ""
        if not is_archived:
            entry_actions = f"""
<div class="entry-actions">
<a class="btn small" href="/entries/cash?account={cash_id}">Cash entry</a>
<a class="btn small ghost" href="/entries/bank?account={bank_target}">Bank entry</a>
<a class="btn small ghost" href="/entries/journal?account={account_id}">Journal entry</a>
</div>"""

        rows = ""
        for r in gl["rows"]:
            badges = ""
            if r["status"] == "reversed":
                badges = ' <span class="pill">reversed</span>'
            elif r["source_type"] == "reversal":
                badges = ' <span class="pill">reversal</span>'
            action = ""
            if (can_reverse and not is_archived
                    and r["source_type"] in ("manual", "opening") and r["status"] != "reversed"):
                action = (f'<a class="small" href="/journal?reverse={esc(r["entry_id"])}">Reverse</a>')
            elif r["source_type"] not in ("manual", "reversal", "opening"):
                action = f'<span class="small muted">{esc(r["source_type"].replace("_", " "))}</span>'
            rows += (f'<tr><td>{esc(r["date"])}</td><td>{esc(r["ref"])}{badges}</td>'
                     f'<td>{esc(r["narration"])}</td>'
                     f'<td class="num">{money.fmt(r["debit"]) if r["debit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["credit"]) if r["credit"] else ""}</td>'
                     f'<td class="num">{money.fmt(r["balance"])}</td><td>{action}</td></tr>')
        rows = rows or '<tr><td colspan="7" class="empty">No movement in this period</td></tr>'

        notice = ""
        if q.get("posted"):
            notice += '<div class="notice">Entry posted. The ledger below includes it.</div>'
        if q.get("created"):
            notice += ('<div class="notice">Ledger account created with its profile. Review the details '
                       'below; posted amounts were not changed.</div>')
        if q.get("updated"):
            notice += '<div class="notice">Account details updated and recorded in the audit log. Posted amounts were not changed.</div>'
        if q.get("opening"):
            notice += '<div class="notice">Opening balance posted against Opening Balance Equity.</div>'
        if q.get("reversed"):
            notice += '<div class="notice">Reversal entry posted. The original entry is marked reversed.</div>'
        if q.get("archived"):
            notice += ('<div class="notice">Account archived. Its posted history remains visible; '
                       'new postings are blocked.</div>')
        if q.get("restored"):
            notice += '<div class="notice">Account restored. It can receive postings again.</div>'
        if q.get("merged"):
            notice += ('<div class="notice">The source ledger was merged into this account and archived. '
                       'The reclassification journal is shown in both ledgers.</div>')

        side = f"""
<aside class="card ledger-side">
<div class="sect-head" style="margin-bottom:8px"><h2>Ledger accounts</h2>
<span class="badge neutral">{len(accounts)}</span></div>
<p class="small muted" style="margin:0 0 4px">Click any account to open its full ledger.</p>
{grouped}
{add_form}
</aside>"""

        body = f"""
{notice}
<div class="ledger-layout">
{side}
<section style="min-width:0">
<div class="sect-head">
<div><h2>{esc(gl["account"]["code"])} — {esc(gl["account"]["name"])}{' <span class="pill">archived</span>' if is_archived else ''}</h2>
<div class="small muted">{esc(gl["account"]["type"]).title()} · {esc(acct.account_group_label(gl["account"]["group_code"], gl["account"]["type"]))} · period opening {money.fmt(gl["opening"])}</div></div>
{entry_actions}
</div>
{f'<div class="card pad small muted" style="margin-bottom:14px"><b>Archived ledger.</b> New postings are blocked. Posted history and balances remain visible; use Restore on the archive page if this was a mistake.</div>' if is_archived else ''}
{profile_card}
{opening_card}
<form method="get" action="/ledger" class="card pad sect">
<input type="hidden" name="account" value="{esc(account_id)}">
<div class="row c3">
<div class="field"><label>From</label><input type="date" name="from" value="{esc(date_from)}"></div>
<div class="field"><label>To</label><input type="date" name="to" value="{esc(date_to)}"></div>
<div class="field" style="display:flex;align-items:flex-end"><button class="btn" type="submit">Apply</button></div>
</div></form>
<div class="card table-wrap"><table>
<thead><tr><th>Date</th><th>Ref</th><th>Narration</th><th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th><th>Action</th></tr></thead>
<tbody><tr><td colspan="5" class="muted">Opening balance (before period)</td><td class="num"><b>{money.fmt(gl["opening"])}</b></td><td></td></tr>
{rows}</tbody>
<tfoot><tr><td colspan="5">Closing balance</td><td class="num">{money.fmt(gl["closing"])}</td><td></td></tr></tfoot></table></div>
<p class="small muted" style="margin-top:12px">Posted entries are never edited. Manual journals and opening balances can be reversed with a reason; reversals create a mirrored entry and keep both sides in the audit trail.</p>
</section></div>"""
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

    def page_analytics(self, conn, user, tenant, q) -> str:
        default = analytics_mod.resolve_period(tenant)
        dfrom = (q.get("from") or [default["from"]])[0] or default["from"]
        dto = (q.get("to") or [default["to"]])[0] or default["to"]
        error = ""
        try:
            data = analytics_mod.overview(conn, tenant, dfrom, dto)
        except analytics_mod.AnalyticsError as e:
            error = e.message
            dfrom, dto = default["from"], default["to"]
            data = analytics_mod.overview(conn, tenant, dfrom, dto)
        except acct.AccountingError as e:
            error = e.message
            dfrom, dto = default["from"], default["to"]
            data = analytics_mod.overview(conn, tenant, dfrom, dto)

        m = data["metrics"]
        months = data["monthly"]["months"]
        insight_payload = insights_mod.grounded(conn, tenant, dfrom, dto)
        insight_q = urllib.parse.urlencode({"from": dfrom, "to": dto})
        insight_rows = "".join(
            f'<tr><td><b>{esc(o["label"])}</b></td><td>{esc(o["text"])}</td>'
            f'<td class="small muted">{esc(o["basis"])}</td></tr>'
            for o in insight_payload["observations"]
        )
        peak = max([max(int(x["revenue_paise"]), int(x["expense_paise"])) for x in months] + [1])
        chart = "".join(
            f'<div class="m">'
            f'<i class="rev" style="height:{max(2, int((int(x["revenue_paise"]) / peak) * 140))}px"'
            f' title="Revenue {esc(money.fmt(x["revenue_paise"]))}"></i>'
            f'<i class="exp" style="height:{max(2, int((int(x["expense_paise"]) / peak) * 140))}px"'
            f' title="Expense {esc(money.fmt(x["expense_paise"]))}"></i>'
            f'<span>{esc(x["month"][5:] + "/" + x["month"][2:4])}</span></div>'
            for x in months)

        exp_total = int(data["expense_breakdown"]["total_paise"])
        exp_rows = "".join(
            f'<tr><td>{esc(r["code"])} {esc(r["name"])}</td>'
            f'<td class="num">{money.fmt(r["amount_paise"])}</td>'
            f'<td><div class="mini-bar"><i style="width:{int((r["amount_paise"] / exp_total) * 100) if exp_total else 0}%"></i></div></td></tr>'
            for r in data["expense_breakdown"]["rows"])
        other = int(data["expense_breakdown"]["other_paise"])
        if other:
            exp_rows += (f'<tr><td>Other expense ledgers</td><td class="num">{money.fmt(other)}</td>'
                         f'<td><div class="mini-bar"><i style="width:{int((other / exp_total) * 100) if exp_total else 0}%"></i></div></td></tr>')
        exp_rows = exp_rows or '<tr><td colspan="3" class="empty">No expense actuals in this period</td></tr>'

        def party_rows(items: list[dict]) -> str:
            return "".join(
                f'<tr><td>{esc(r["name"])}</td><td class="num">{r["documents"]}</td>'
                f'<td class="num">{money.fmt(r["amount_paise"])}</td></tr>'
                for r in items) or '<tr><td colspan="3" class="empty">None in this period</td></tr>'

        tb_badge = ('<span class="badge ok">Balanced</span>' if data["checks"]["trial_balance_balanced"]
                    else '<span class="badge bad">Out of balance</span>')
        bs_badge = ('<span class="badge ok">A = L + E</span>' if data["checks"]["balance_sheet_balanced"]
                    else f'<span class="badge bad">Difference {money.fmt(data["checks"]["balance_sheet_difference_paise"])}</span>')
        err_html = (f'<div class="card pad" style="border-color:var(--danger);margin-bottom:14px">'
                    f'<b>Could not use that period.</b> {esc(error)} Showing the default period instead.</div>'
                    if error else "")
        api_q = urllib.parse.urlencode({"from": dfrom, "to": dto})
        chart_payload = {
            "months": [x["month"] for x in months],
            "revenue": [round(int(x["revenue_paise"]) / 100, 2) for x in months],
            "expense": [round(int(x["expense_paise"]) / 100, 2) for x in months],
            "profit": [round(int(x["profit_paise"]) / 100, 2) for x in months],
        }
        expense_payload = {
            "labels": ([f'{r["code"]} {r["name"]}' for r in data["expense_breakdown"]["rows"]]
                       + (["Other expense ledgers"] if other else [])),
            "values": ([round(int(r["amount_paise"]) / 100, 2)
                        for r in data["expense_breakdown"]["rows"]]
                       + ([round(other / 100, 2)] if other else [])),
        }
        chart_json = json.dumps(chart_payload, ensure_ascii=False).replace("</", "<\\/")
        expense_json = json.dumps(expense_payload, ensure_ascii=False).replace("</", "<\\/")
        chart_script = """
<script src="/static/echarts.min.js"></script>
<script>
(function () {
  const el = document.getElementById('echarts-monthly');
  if (!el || !window.echarts) return;
  const data = __DATA__;
  const expenseData = __EXPENSE_DATA__;
  const chart = echarts.init(el, null, { renderer: 'canvas' });
  const inr = function (value) {
    return '\\u20b9' + Number(value).toLocaleString('en-IN', {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    });
  };
  chart.setOption({
    animationDuration: 400,
    color: ['#0C3157', '#D97706', '#2E7D8F'],
    tooltip: { trigger: 'axis', valueFormatter: inr },
    legend: { top: 0, data: ['Revenue', 'Expenses', 'Profit'] },
    grid: { left: 72, right: 28, top: 42, bottom: 34 },
    xAxis: { type: 'category', data: data.months, axisLabel: { color: '#52606D' } },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#52606D',
        formatter: function (value) {
          if (Math.abs(value) >= 10000000) return (value / 10000000).toFixed(1) + ' Cr';
          if (Math.abs(value) >= 100000) return (value / 100000).toFixed(1) + ' L';
          return value;
        }
      },
      splitLine: { lineStyle: { color: '#E4EBF2' } }
    },
    series: [
      { name: 'Revenue', type: 'bar', data: data.revenue, barMaxWidth: 28 },
      { name: 'Expenses', type: 'bar', data: data.expense, barMaxWidth: 28 },
      { name: 'Profit', type: 'line', smooth: true, data: data.profit, symbolSize: 6 }
    ]
  });
  window.addEventListener('resize', function () { chart.resize(); });
  const expenseEl = document.getElementById('echarts-expense');
  if (expenseEl && expenseData.labels.length) {
    const expenseChart = echarts.init(expenseEl, null, { renderer: 'canvas' });
    expenseChart.setOption({
      animationDuration: 400,
      color: ['#0C3157', '#2E7D8F', '#D97706', '#7C3AED', '#059669', '#B45309', '#64748B'],
      tooltip: { trigger: 'item', valueFormatter: inr },
      legend: { type: 'scroll', bottom: 0, textStyle: { color: '#52606D' } },
      series: [{
        name: 'Expense actuals', type: 'pie', radius: ['46%', '70%'], center: ['50%', '44%'],
        avoidLabelOverlap: true,
        label: { formatter: function (p) { return p.name + '  ' + p.percent + '%'; }, color: '#27313B', fontSize: 11 },
        data: expenseData.labels.map(function (name, i) {
          return { name: name, value: expenseData.values[i] };
        })
      }]
    });
    window.addEventListener('resize', function () { expenseChart.resize(); });
  }
})();
</script>"""
        chart_script = chart_script.replace("__DATA__", chart_json).replace("__EXPENSE_DATA__", expense_json)
        expense_chart_html = ('<div id="echarts-expense" style="height:280px;width:100%"></div>'
                              if exp_total else
                              '<p class="small muted">No expense actuals to chart in this period.</p>')
        body = f"""
{err_html}
<form method="get" action="/reports/analytics" class="sect" style="display:flex;gap:10px;align-items:end;flex-wrap:wrap">
<div><label>From</label><input type="date" name="from" value="{esc(dfrom)}"></div>
<div><label>To</label><input type="date" name="to" value="{esc(dto)}"></div>
<button class="btn" type="submit">Apply</button>
<span class="badge neutral">Actuals only</span>
</form>
<div class="kpis">
  {kpi("Revenue", money.fmt(m["revenue_paise"]), "posted income journals")}
  {kpi("Expenses", money.fmt(m["expense_paise"]), "posted expense journals")}
  {kpi("Net profit", money.fmt(m["net_profit_paise"]), "revenue minus expenses")}
  {kpi("Cash + bank", money.fmt(m["cash_and_bank_paise"]), "as of period end")}
  {kpi("Receivable", money.fmt(m["receivable_paise"]), f'{m["open_invoices"]} open invoice(s)')}
  {kpi("Payable", money.fmt(m["payable_paise"]), f'{m["open_bills"]} open bill(s)')}
  {kpi("GST net", money.fmt(m["gst_net_payable_paise"]), "output minus input; working aid")}
  {kpi("Inventory", money.fmt(m["inventory_paise"]), "perpetual valuation")}
</div>
<div class="card pad sect">
  <div class="sect-head"><h2>AI Insights</h2>
    <span class="badge neutral">Grounded rules · no provider configured</span></div>
  <p class="small" style="margin:0 0 10px">{esc(insight_payload["summary"])}</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Observation</th><th>What the actuals show</th><th>Basis</th></tr></thead>
    <tbody>{insight_rows}</tbody></table></div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
    <a class="btn ghost small" href="/api/v1/analytics/insights?{esc(insight_q)}">Open insight JSON</a>
    <span class="small muted" style="align-self:center">No external model was called. No forecast is included.</span>
  </div>
</div>
<div class="grid2">
  <div class="card pad">
    <div class="sect-head"><h2>Revenue and expenses by month</h2>
      <div class="legend"><span><i class="rev"></i>Revenue</span><span><i class="exp"></i>Expense</span></div></div>
    <div class="chart2">{chart}</div>
    <div style="height:24px"></div>
    <table><thead><tr><th>Period</th><th class="num">Revenue</th><th class="num">Expense</th><th class="num">Profit</th></tr></thead>
      <tbody><tr><td>{esc(dfrom)} to {esc(dto)}</td><td class="num">{money.fmt(data["monthly"]["total_revenue_paise"])}</td>
      <td class="num">{money.fmt(data["monthly"]["total_expense_paise"])}</td>
      <td class="num">{money.fmt(data["monthly"]["total_profit_paise"])}</td></tr></tbody></table>
    <p class="small muted" style="margin:10px 0 0">Monthly gaps are shown as zero actuals, never estimates. Forecasts are deliberately excluded from this view.</p>
  </div>
  <div class="card pad">
    <div class="sect-head"><h2>Checks and freshness</h2>{tb_badge}</div>
    <table style="margin:0 0 12px">
      <tr><td>Trial balance</td><td class="num">{tb_badge}</td></tr>
      <tr><td>Balance sheet</td><td class="num">{bs_badge}</td></tr>
      <tr><td>Unbalanced entries</td><td class="num">{data["checks"]["unbalanced_entries"]}</td></tr>
      <tr><td>Journal entries</td><td class="num">{data["freshness"]["journal_entries"]}</td></tr>
      <tr><td>Journal lines</td><td class="num">{data["freshness"]["journal_lines"]}</td></tr>
      <tr><td>Last entry date</td><td class="num">{esc(data["freshness"]["last_entry_date"] or "none")}</td></tr>
      <tr><td>Last posted at</td><td class="num small">{esc(data["freshness"]["last_posted_at"] or "none")}</td></tr>
    </table>
    <p class="small muted" style="margin:0 0 10px">Every figure is computed from posted journal lines. No AI, cache or forecast writes an authoritative total.</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <a class="btn small" href="/export/workbook.xlsx?{esc(api_q)}">Download Excel workbook</a>
      <a class="btn ghost small" href="/export/powerbi.zip?{esc(api_q)}">Power BI pack</a>
      <a class="btn ghost small" href="/api/v1/analytics/overview?{esc(api_q)}">Open JSON contract</a>
    </div>
    <p class="small muted" style="margin:10px 0 0">The .xlsx pack includes KPI, P&amp;L, balance sheet, trial balance, monthly charts, ageing, GST, inventory, journal and grounded insight sheets. The Power BI pack is a static import ZIP, not a .pbix or a scheduled Service dataset. Actuals only; no forecasts.</p>
  </div>
</div>
<div class="card pad sect">
  <div class="sect-head"><h2>Interactive monthly view</h2>
    <span class="badge neutral">ECharts · actuals only</span></div>
  <div id="echarts-monthly" style="height:340px;width:100%"></div>
  <p class="small muted" style="margin:8px 0 0">Same posted-journal actuals as the chart above. Hover for rupee values; no forecast or estimate is plotted.</p>
</div>
<div class="grid2" style="margin-top:16px">
  <div class="card pad">
    <div class="sect-head"><h2>Expense breakdown</h2><span class="badge neutral">{money.fmt(exp_total)}</span></div>
    {expense_chart_html}
    <table><thead><tr><th>Ledger</th><th class="num">Actual</th><th>Share</th></tr></thead><tbody>{exp_rows}</tbody></table>
  </div>
  <div>
    <div class="card pad">
      <div class="sect-head"><h2>Top customers</h2><a class="btn ghost small" href="/reports/ar-ageing">Ageing</a></div>
      <table><thead><tr><th>Customer</th><th class="num">Invoices</th><th class="num">Net sales</th></tr></thead>
      <tbody>{party_rows(data["top_customers"])}</tbody></table>
    </div>
    <div style="height:14px"></div>
    <div class="card pad">
      <div class="sect-head"><h2>Top vendors</h2><a class="btn ghost small" href="/reports/ap-ageing">Ageing</a></div>
      <table><thead><tr><th>Vendor</th><th class="num">Bills</th><th class="num">Purchases</th></tr></thead>
      <tbody>{party_rows(data["top_vendors"])}</tbody></table>
    </div>
  </div>
</div>
<p class="small muted" style="margin-top:14px">GST figures are working aids, not filed returns. Receivable and payable ageing use posted invoices and bills as of the period end.</p>
{chart_script}"""
        return layout("Analytics overview", body, "reports/analytics", user, tenant)

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

        def item_margin(row) -> int:
            if row["margin_bp"] or not row["cost_paise"]:
                return row["margin_bp"]
            return max(0, ((row["sale_price_paise"] - row["cost_paise"]) * 10000)
                       // row["cost_paise"])

        trs = "".join(
            f'<tr><td>{esc(r["sku"])}</td><td>{esc(r["name"])}'
            f'{"<div class=\"small muted\">" + esc(r["brand"]) + "</div>" if r["brand"] else ""}</td>'
            f'<td>{esc(r["category"]) or "—"}</td><td>{esc(r["hsn"]) or "—"}</td>'
            f'<td class="num">{money.fmt(r["sale_price_paise"])}</td>'
            f'<td class="num">{item_margin(r)/100:.2f}%</td>'
            f'<td class="num">{r["tax_rate_bp"]/100:.2f}%</td>'
            f'<td class="num">{r["stock_milli"]/1000:.3f}</td>'
            f'<td class="num">{money.fmt(r["cost_paise"])}</td></tr>' for r in rows) or \
            '<tr><td colspan="9" class="empty">No items</td></tr>'
        income_accounts = conn.execute(
            "SELECT code, name FROM account WHERE tenant_id=? AND type='income'"
            " AND status='active' ORDER BY code", (tenant["id"],)).fetchall()
        revenue_options = "".join(
            f'<option value="{esc(a["code"])}"{" selected" if a["code"] == "4000" else ""}>'
            f'{esc(a["code"])} — {esc(a["name"])}</option>' for a in income_accounts)
        body = f"""
<div class="sect-head"><div><h2>Products / services</h2>
<div class="small muted">Price, margin, GST, HSN and stock belong to the item master. A ledger account
only classifies the accounting posting, so one Sales ledger can hold many products.</div></div></div>
<div class="grid2">
<div class="card table-wrap"><table><thead><tr><th>SKU</th><th>Name</th><th>Category</th><th>HSN</th>
<th class="num">Sale price</th><th class="num">Margin</th><th class="num">GST</th><th class="num">Stock</th><th class="num">Cost</th></tr></thead>
<tbody>{trs}</tbody></table></div>
<div class="card pad"><h2 style="margin-bottom:12px">Add product / service</h2>
<form method="post" action="/items">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="row c2"><div class="field"><label>SKU / code</label><input name="sku" required maxlength="40" placeholder="SKU-001"></div>
<div class="field"><label>Name</label><input name="name" required maxlength="120" placeholder="Consultation / Item name"></div></div>
<div class="row c2"><div class="field"><label>Category</label><input name="category" maxlength="60" placeholder="Clinical consumables"></div>
<div class="field"><label>Brand</label><input name="brand" maxlength="60" placeholder="Optional"></div></div>
<div class="row c3"><div class="field"><label>HSN / SAC</label><input name="hsn" maxlength="12" placeholder="3004 / 9983"></div>
<div class="field"><label>Barcode</label><input name="barcode" maxlength="40" placeholder="Optional"></div>
<div class="field"><label>Sales ledger</label><select name="revenue_code">{revenue_options}</select></div></div>
<div class="row c4"><div class="field"><label>Cost price</label><input name="cost" value="0" inputmode="decimal"></div>
<div class="field"><label>Margin % (on cost)</label><input name="margin" inputmode="decimal" placeholder="20"></div>
<div class="field"><label>Sale price</label><input name="price" inputmode="decimal" placeholder="Blank = cost + margin"></div>
<div class="field"><label>MRP</label><input name="mrp" inputmode="decimal" placeholder="0.00"></div></div>
<div class="row c3"><div class="field"><label>GST %</label><input name="tax" value="18" inputmode="decimal"></div>
<div class="field"><label>Opening stock</label><input name="stock" value="0" inputmode="decimal"></div>
<div class="field"><label>Stock tracking</label><select name="track"><option value="1">Yes (goods)</option><option value="0">No (service)</option></select></div></div>
<button class="btn" type="submit">Save product</button>
<p class="small muted" style="margin:8px 0 0">GST is a working rate for invoices, not a claim of input
credit. HSN/SAC is required for GST-ready invoices.</p></form></div></div>"""
        return layout("Items", body, "items", user, tenant)

    def page_settings(self, conn, user, tenant, sess, q) -> str:
        try:
            security.require(conn, user["id"], tenant["id"], "tenant.manage")
            can_edit = True
        except security.AuthError:
            can_edit = False
        theme = theme_for(user)
        theme_saved = ('<div class="badge ok" style="margin-bottom:12px">Theme saved</div>'
                       if q.get("theme_saved") else "")
        theme_card = f"""
<div class="card pad sect">
<h2 style="margin-bottom:4px">Appearance</h2>
<p class="small muted" style="margin:0 0 12px">Choose a colour theme for your workspace. This changes
only your screens; business data, reports and other users' preferences are untouched.</p>
{theme_saved}
<form method="post" action="/preferences/theme">
<input type="hidden" name="_csrf" value="{esc(sess['csrf_token'])}">
<div class="small muted" style="margin-bottom:8px">Colour theme</div>
<div class="theme-grid" role="radiogroup" aria-label="Colour theme">{theme_options(theme)}</div>
<div class="theme-save"><button class="btn" type="submit">Save theme</button>
<span class="small muted">Current: <b>{esc(THEMES[theme]['label'])}</b></span></div>
</form></div>"""
        if not can_edit:
            body = f"""{theme_card}
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
Currency {esc(tenant['currency'])}. GSTIN, PIN code and IFSC are validated on save.</div>
{theme_card}"""
        return layout("Settings", body, "settings", user, tenant)

    def _settings_error(self, user, tenant, message: str):
        body = (f'<div class="card pad"><div class="err">{esc(message)}</div>'
                '<a class="btn ghost" href="/settings">Back to settings</a></div>')
        return self._send(layout("Settings", body, "settings", user, tenant), 400)

    def _save_theme(self, conn, user, tenant, form):
        theme = first(form, "theme").strip()
        if theme not in THEMES:
            return self._settings_error(user, tenant, "Choose a valid colour theme.")
        old = theme_for(user)
        conn.execute("UPDATE user SET theme=? WHERE id=?", (theme, user["id"]))
        acct.audit(conn, tenant["id"], user["id"], "user.theme_updated", "user", user["id"],
                   meta={"from": old, "to": theme})
        cookie = f"ui_theme={theme}; Path=/; Max-Age=31536000; SameSite=Lax"
        return self._redirect("/settings?theme_saved=1", {"Set-Cookie": cookie})

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
<pre class="small" style="background:#F8FAFC;padding:12px;border-radius:10px;overflow:auto">python scripts/backup.py
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
        note = (f'<div class="card pad small" style="background:#F8FAFC;margin-bottom:14px">'
                f'<b>{esc(invite["email"])}</b> already has an ARTHIVIO login. Enter its current password to join '
                f'<b>{esc(invite["tenant_name"])}</b> as {esc(role_name(invite["role"]))}.</div>') if existing else (
                f'<div class="card pad small" style="background:#F8FAFC;margin-bottom:14px">'
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
        rows = rows or '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:18px">No transactions in this period</td></tr>'
        business_addr = ", ".join(x for x in (tenant["address"], tenant["city"], tenant["state_name"],
                                              tenant["pincode"]) if x)
        party_addr = ", ".join(x for x in (party.get("address", ""), state_name(party.get("state_code", ""))) if x)
        heading = "Statement of account" if is_customer else "Vendor account statement"
        counterparty = "Customer" if is_customer else "Vendor"
        closing_label = "Amount due from customer" if is_customer else "Amount payable to vendor"
        extra_css = """
.stmt-title{margin:0 0 2px;font-size:18px;font-weight:700;color:var(--ink)}
.stmt-period{font-size:11px;color:var(--ink-soft);margin-top:2px}
.stmt-note{margin-top:10px;font-size:10px;color:var(--muted)}
.stmt-total td{font-weight:700;border-top:2px solid var(--primary)}
.stmt-toolbar{justify-content:space-between;align-items:center}
.stmt-toolbar .tag{font-size:11px;color:var(--muted);letter-spacing:.03em}
"""
        return f"""<!doctype html><html lang="en" data-theme="{DEFAULT_THEME}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<meta name="description" content="Shared statement of account issued by {esc(tenant["name"])} from ARTHIVIO.">
<title>{esc(heading)} · {esc(tenant["name"])}</title><style>{THEME_CSS}{PRINT_CSS}{extra_css}</style></head>
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
      <tr><td colspan="5" style="color:var(--muted)">Opening balance</td><td class="num"><b>{money.fmt(st["opening"])}</b></td></tr>
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
<div class="card pad" style="margin:0 0 14px;background:#F8FAFC">
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
    def _profile_from_form(self, form) -> dict:
        def integer(name: str, label: str) -> int:
            text = first(form, name).strip()
            if not text:
                return 0
            if not re.fullmatch(r"-?[0-9]{1,6}", text):
                raise acct.AccountingError("BAD_PROFILE_NUMBER",
                                           f"{label} must be a whole number.")
            return int(text)

        def amount(name: str, label: str) -> int:
            text = first(form, name).strip()
            if not text:
                return 0
            try:
                return money.parse_amount(text)
            except money.MoneyError as exc:
                raise acct.AccountingError("BAD_PROFILE_AMOUNT",
                                           f"{label}: {exc}") from exc

        profile = {}
        for name in ("legal_name", "contact_person", "phone", "email", "website",
                     "address", "city", "state_code", "pincode", "country", "gstin",
                     "pan", "cin", "organisation_type", "industry", "loan_lender",
                     "loan_account_no", "loan_sanction_date", "loan_maturity_date",
                     "security_details", "notes"):
            profile[name] = first(form, name).strip()
        profile["credit_days"] = integer("credit_days", "Credit days")
        profile["credit_limit_paise"] = amount("credit_limit", "Credit limit")
        profile["tenure_months"] = integer("tenure_months", "Loan tenure")
        profile["emi_paise"] = amount("emi", "EMI")
        try:
            profile["interest_rate_bp"] = money.parse_percent(
                first(form, "interest_rate") or "0")
        except money.MoneyError as exc:
            raise acct.AccountingError("BAD_PROFILE_INTEREST",
                                       f"Interest rate: {exc}") from exc
        return profile

    def _bank_from_form(self, form) -> dict:
        return {
            "bank_name": first(form, "bank_name").strip(),
            "account_number": first(form, "bank_account_number").strip(),
            "ifsc": first(form, "ifsc").strip().upper(),
            "branch": first(form, "branch").strip(),
            "holder_name": first(form, "holder_name").strip(),
        }

    def _create_account(self, conn, user, tenant, form, sess):
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
        except security.AuthError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    '<a class="btn ghost" href="/ledger">Back to ledger</a></div>')
            return self._send(layout("Forbidden", body, "ledger", user, tenant), 403)
        try:
            group_code = first(form, "group_code").strip().lower()
            account_type = first(form, "type").strip().lower()
            if not group_code and account_type:
                group_code = acct.default_group_for_type(account_type)
            group = acct.ACCOUNT_GROUPS.get(group_code)
            if group:
                account_type = group["type"]
            profile = self._profile_from_form(form)
            opening = None
            opening_text = first(form, "opening_amount").strip()
            if opening_text:
                opening_amount = money.parse_amount(opening_text)
                if opening_amount > 0:
                    opening_date = first(form, "opening_as_of").strip()
                    if not opening_date:
                        raise acct.AccountingError(
                            "OPENING_DATE_REQUIRED",
                            "Choose an as-of date for the opening balance.")
                    group = acct.ACCOUNT_GROUPS.get(group_code) or {}
                    side = (first(form, "opening_side").strip().lower()
                            or group.get("default_side", "debit"))
                    opening = {"amount": opening_amount, "as_of": opening_date,
                               "side": side}
            bank_details = self._bank_from_form(form) if group_code == "bank" else None
            account_id = acct.create_account(
                conn, tenant["id"], first(form, "code"), first(form, "name"),
                account_type, created_by=user["id"], group_code=group_code,
                profile=profile, opening=opening, bank_details=bank_details)
        except acct.AccountingError as e:
            return self._send(self.page_account_new(conn, user, tenant, sess, form,
                                                    error=e.message), 400)
        except money.MoneyError as e:
            return self._send(self.page_account_new(conn, user, tenant, sess, form,
                                                    error=str(e)), 400)
        return self._redirect(f"/ledger?account={account_id}&created=1")

    def _update_account(self, conn, user, tenant, form, sess):
        account_id = first(form, "account_id")
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
        except security.AuthError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    f'<a class="btn ghost" href="/ledger?account={esc(account_id)}">Back to ledger</a></div>')
            return self._send(layout("Forbidden", body, "ledger", user, tenant), 403)
        try:
            profile = self._profile_from_form(form)
            bank_details = self._bank_from_form(form)
            acct.update_account_profile(
                conn, tenant["id"], account_id, first(form, "name"), profile,
                bank_details=bank_details, updated_by=user["id"])
        except acct.AccountingError as e:
            return self._send(self.page_account_edit(conn, user, tenant, sess, account_id,
                                                     form, error=e.message), 400)
        return self._redirect(f"/ledger?account={account_id}&updated=1")

    def _archive_account(self, conn, user, tenant, form, sess):
        account_id = first(form, "account_id")
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
            acct.archive_account(conn, tenant["id"], account_id, first(form, "reason"),
                                 archived_by=user["id"])
        except security.AuthError as e:
            return self._send(self.page_account_archive(
                conn, user, tenant, sess, account_id, {}, error=e.message), 403)
        except acct.AccountingError as e:
            return self._send(self.page_account_archive(
                conn, user, tenant, sess, account_id, {}, error=e.message), 400)
        return self._redirect(f"/ledger?account={account_id}&archived=1")

    def _restore_account(self, conn, user, tenant, form, sess):
        account_id = first(form, "account_id")
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
            acct.restore_account(conn, tenant["id"], account_id, first(form, "reason"),
                                 restored_by=user["id"])
        except security.AuthError as e:
            return self._send(self.page_account_archive(
                conn, user, tenant, sess, account_id, {}, error=e.message), 403)
        except acct.AccountingError as e:
            return self._send(self.page_account_archive(
                conn, user, tenant, sess, account_id, {}, error=e.message), 400)
        return self._redirect(f"/ledger?account={account_id}&restored=1")

    def _merge_account(self, conn, user, tenant, form, sess):
        source_id = first(form, "account_id")
        target_id = first(form, "target_id")
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
            acct.merge_accounts(conn, tenant["id"], source_id, target_id,
                                first(form, "reason"), merged_by=user["id"])
        except security.AuthError as e:
            return self._send(self.page_account_archive(
                conn, user, tenant, sess, source_id, {}, error=e.message), 403)
        except acct.AccountingError as e:
            return self._send(self.page_account_archive(
                conn, user, tenant, sess, source_id, {}, error=e.message), 400)
        return self._redirect(f"/ledger?account={target_id}&merged=1")

    def _opening_template(self, conn, user, tenant):
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
        except security.AuthError:
            return self._send("Forbidden", 403)
        return self._send_bytes(
            opening_mod.template_csv().encode("utf-8"),
            "text/csv; charset=utf-8",
            "arthivio-opening-balances.csv",
        )

    def _bulk_opening_import(self, conn, user, tenant, sess, form):
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
        except security.AuthError as e:
            return self._send(
                self.page_opening_import(conn, user, tenant, sess, {}, error=e.message), 403)

        csv_text = first(form, "csv_text")
        default_as_of = (first(form, "default_as_of")
                         or fiscal_start(date.today(), tenant["fiscal_year_start_month"]))
        filename = first(form, "filename")
        upload = getattr(self, "_uploaded_files", {}).get("xlsx_file")
        if upload and upload.get("content"):
            try:
                csv_text = xlsx_mod.xlsx_to_csv(upload["content"])
            except xlsx_mod.XlsxImportError as e:
                return self._send(
                    self.page_opening_import(conn, user, tenant, sess, {}, error=e.message), 400)
            filename = upload.get("filename") or "opening-balances.xlsx"
        values = {"csv_text": csv_text, "default_as_of": default_as_of, "filename": filename}
        action = first(form, "action") or "preview"

        if action == "post":
            try:
                result = opening_mod.post_import(
                    conn, tenant["id"], csv_text, default_as_of, filename, user["id"])
            except opening_mod.OpeningImportError as e:
                return self._send(
                    self.page_opening_import(conn, user, tenant, sess, {}, values=values,
                                             preview=e.preview, error=e.message), 400)
            except acct.AccountingError as e:
                try:
                    current = opening_mod.preview(conn, tenant["id"], csv_text, default_as_of)
                except opening_mod.OpeningImportError:
                    current = None
                return self._send(
                    self.page_opening_import(conn, user, tenant, sess, {}, values=values,
                                             preview=current, error=e.message), 400)
            return self._redirect(f"/ledger/opening-balances?posted={result['count']}")

        try:
            current = opening_mod.preview(conn, tenant["id"], csv_text, default_as_of)
        except opening_mod.OpeningImportError as e:
            return self._send(
                self.page_opening_import(conn, user, tenant, sess, {}, values=values,
                                         error=e.message), 400)
        return self._send(self.page_opening_import(conn, user, tenant, sess, {},
                                                   values=values, preview=current))

    def _set_opening_balance(self, conn, user, tenant, form):
        account_id = first(form, "account_id")
        back = f"/ledger?account={account_id}" if account_id else "/ledger"
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
            amount = money.parse_amount(first(form, "amount"))
            acct.set_opening_balance(
                conn, tenant["id"], account_id, first(form, "as_of"), amount,
                first(form, "side"), created_by=user["id"])
        except security.AuthError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    f'<a class="btn ghost" href="{esc(back)}">Back to ledger</a></div>')
            return self._send(layout("Forbidden", body, "ledger", user, tenant), 403)
        except acct.AccountingError as e:
            return self._error_page(user, tenant, e.message, back)
        except money.MoneyError as e:
            return self._error_page(user, tenant, str(e), back)
        return self._redirect(f"{back}{'&' if '?' in back else '?'}opening=1")

    def _create_bank_account(self, conn, user, tenant, form):
        try:
            security.require(conn, user["id"], tenant["id"], "account.manage")
        except security.AuthError as e:
            body = (f'<div class="card pad"><div class="err">{esc(e.message)}</div>'
                    '<a class="btn ghost" href="/bank-accounts">Back to bank accounts</a></div>')
            return self._send(layout("Forbidden", body, "bank-accounts", user, tenant), 403)
        try:
            bank_mod.create_bank_account(
                conn, tenant["id"], first(form, "code"), first(form, "name"),
                first(form, "bank_name"), first(form, "account_number"),
                first(form, "ifsc"), first(form, "branch"), first(form, "holder_name"),
                created_by=user["id"])
        except bank_mod.BankError as e:
            return self._error_page(user, tenant, e.message, "/bank-accounts")
        return self._redirect("/bank-accounts?created=1")

    def _reverse_journal(self, conn, user, tenant, form):
        entry_id = first(form, "entry_id")
        back = "/ledger"
        try:
            security.require(conn, user["id"], tenant["id"], "ledger.reverse")
            entry = conn.execute(
                "SELECT * FROM journal_entry WHERE id=? AND tenant_id=?",
                (entry_id, tenant["id"])).fetchone()
            if not entry:
                raise acct.AccountingError("ENTRY_NOT_FOUND", "Journal entry not found")
            if entry["source_type"] not in ("manual", "opening"):
                raise acct.AccountingError(
                    "NOT_MANUAL",
                    "Only manual journals and opening balances can be reversed here. "
                    "Use the source document or a credit/debit note.")
            first_line = conn.execute(
                "SELECT account_id FROM journal_line WHERE entry_id=? ORDER BY line_no LIMIT 1",
                (entry_id,)).fetchone()
            if first_line:
                back = f'/ledger?account={first_line["account_id"]}'
            reverse_id = acct.reverse_entry(
                conn, tenant["id"], entry_id, first(form, "reason"), created_by=user["id"])
            acct.audit(conn, tenant["id"], user["id"], "journal.reverse", "journal_entry", entry_id,
                       meta={"reversal_entry": reverse_id,
                             "reason": first(form, "reason").strip()[:200]})
        except (security.AuthError, acct.AccountingError) as e:
            return self._error_page(user, tenant, e.message, back)
        return self._redirect(f"{back}{'&' if '?' in back else '?'}reversed=1")

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
            return self._item_error(user, tenant, "SKU and item name are required.")
        try:
            cost = money.parse_amount(first(form, "cost") or "0")
            margin_bp = money.parse_percent(first(form, "margin") or "0")
            price_text = first(form, "price").strip()
            price = money.parse_amount(price_text) if price_text else 0
            if not price and cost:
                price = (cost * (10000 + margin_bp) + 5000) // 10000
            if price and not margin_bp and cost:
                margin_bp = max(0, ((price - cost) * 10000) // cost)
            rate = money.parse_percent(first(form, "tax") or "18")
            stock = money.parse_qty(first(form, "stock") or "0")
            mrp = money.parse_amount(first(form, "mrp") or "0")
        except money.MoneyError as e:
            return self._item_error(user, tenant, str(e))
        revenue_code = first(form, "revenue_code") or "4000"
        revenue = conn.execute(
            "SELECT 1 FROM account WHERE tenant_id=? AND code=? AND type='income'"
            " AND status='active'", (tenant["id"], revenue_code)).fetchone()
        if not revenue:
            return self._item_error(user, tenant, "Choose a valid income ledger for sales.")
        if mrp and price > mrp:
            return self._item_error(user, tenant, "MRP cannot be lower than the sale price.")
        iid = db.new_id()
        conn.execute(
            "INSERT INTO item (id, tenant_id, sku, name, sale_price_paise, cost_paise,"
            " tax_rate_bp, hsn, stock_milli, track_stock, revenue_code, category, brand,"
            " barcode, mrp_paise, margin_bp)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (iid, tenant["id"], sku[:40], name[:120], price, cost, rate,
             first(form, "hsn").strip()[:12], stock,
             1 if first(form, "track") != "0" else 0, revenue_code,
             first(form, "category").strip()[:60], first(form, "brand").strip()[:60],
             first(form, "barcode").strip()[:40], mrp, margin_bp))
        acct.audit(conn, tenant["id"], user["id"], "item.create", "item", iid,
                   meta={"sku": sku[:40], "margin_bp": margin_bp, "tax_rate_bp": rate})
        return self._redirect("/items?created=1")

    def _item_error(self, user, tenant, message: str):
        body = (f'<div class="card pad"><div class="err">{esc(message)}</div>'
                '<a class="btn ghost" href="/items">Back to items</a></div>')
        return self._send(layout("Items", body, "items", user, tenant), 400)

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
        csv_text = first(form, "csv_text")
        filename = first(form, "filename")
        upload = getattr(self, "_uploaded_files", {}).get("xlsx_file")
        if upload and upload.get("content"):
            try:
                csv_text = xlsx_mod.xlsx_to_csv(upload["content"])
            except xlsx_mod.XlsxImportError as e:
                return self._send(self.page_gstr2b(conn, user, tenant,
                                                   {"csrf_token": form.get("_csrf", [""])[0]},
                                                   {"month": [month]}, e.message), 400)
            filename = upload.get("filename") or "gstr2b.xlsx"
        try:
            result = gstr2b_mod.import_2b(conn, tenant["id"], month,
                                          csv_text, filename,
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
        csv_text = first(form, "csv_text")
        filename = first(form, "filename")
        upload = getattr(self, "_uploaded_files", {}).get("xlsx_file")
        if upload and upload.get("content"):
            try:
                csv_text = xlsx_mod.xlsx_to_csv(upload["content"])
            except xlsx_mod.XlsxImportError as e:
                return self._error_page(user, tenant, e.message, "/bank-recon")
            filename = upload.get("filename") or "bank-statement.xlsx"
        try:
            rows = bank_mod.parse_csv(csv_text)
            result = bank_mod.import_statement(
                conn, tenant["id"], account_id, rows,
                filename=filename, created_by=user["id"])
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
            first_account = lines[0]["account_id"] if lines else ""
            if first_account:
                return self._redirect(f"/ledger?account={first_account}&posted=1")
            return self._redirect("/daybook")
        except (acct.AccountingError, money.MoneyError) as e:
            return self._error_page(user, tenant, getattr(e, "message", str(e)), "/journal")

    # ---------------- exports ----------------
    def _send_bytes(self, data: bytes, content_type: str, filename: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def export_workbook(self, conn, user, tenant, q):
        try:
            security.require(conn, user["id"], tenant["id"], "report.export")
        except security.AuthError as e:
            return self._send(e.message, 403)
        dfrom = (q.get("from") or [None])[0]
        dto = (q.get("to") or [None])[0]
        try:
            data = excel_mod.build_workbook(conn, tenant, dfrom, dto)
        except analytics_mod.AnalyticsError as e:
            return self._send(f"Invalid period: {e.message}", 400)
        except excel_mod.ExcelError as e:
            return self._send(str(e), 500)
        except acct.AccountingError as e:
            return self._send(f"Could not build the workbook: {e.message}", 400)
        self._send_bytes(
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            excel_mod.filename(tenant, dto or date.today().isoformat()),
        )

    def export_powerbi_pack(self, conn, user, tenant, q):
        try:
            security.require(conn, user["id"], tenant["id"], "report.export")
        except security.AuthError as e:
            return self._send(e.message, 403)
        dfrom = (q.get("from") or [None])[0]
        dto = (q.get("to") or [None])[0]
        try:
            data = bi_mod.build_pack(conn, tenant, dfrom, dto)
        except analytics_mod.AnalyticsError as e:
            return self._send(f"Invalid period: {e.message}", 400)
        except acct.AccountingError as e:
            return self._send(f"Could not build the Power BI pack: {e.message}", 400)
        self._send_bytes(data, "application/zip",
                         bi_mod.filename(tenant, dto or date.today().isoformat()))

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
    host = os.environ.get("ARTHIVIO_HOST", "127.0.0.1")
    db.init_db(db.connect(DB_PATH))
    srv = ThreadingHTTPServer((host, port), Handler)
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print(f"ARTHIVIO running on http://{shown}:{port}  (db: {DB_PATH})")
    if host in ("0.0.0.0", "::"):
        print("LAN access is enabled by ARTHIVIO_HOST. Use only on a trusted network.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main(int(os.environ.get("PORT", "8000")))
