# ARTHIVIO Offline Edition

**Build 0.26. Single-user Windows package. No Python install, no internet, local SQLite.**

This document describes the offline package only. It is not permanent hosting, not a multi-user
server, and not a substitute for an independent accounting or security review.

---

## 1. What the package contains

| Part | Purpose |
|---|---|
| `runtime\python.exe` | Official Python 3.14.6 embeddable runtime |
| `app\` | ARTHIVIO application and locally vendored ECharts |
| `scripts\` | Offline launcher, backup, restore verification and setup helpers |
| `data\arthivio.db` | Local SQLite database, created on first use |
| `backups\` | Local verified backups |
| `logs\arthivio.log` | Server log, including traceable `ERR-XXXXXXXXXX` entries |
| `Start ARTHIVIO.bat` | Start the server and open the browser |
| `Backup ARTHIVIO.bat` | Verified backup copied to an external drive |
| `Install autostart.bat` | Desktop shortcut plus minimized login autostart |
| `Remove autostart.bat` | Remove those shortcuts |
| `README-OFFLINE.txt` | Short instructions shipped inside the package |

Build it from the repository with:

```powershell
.\.venv\Scripts\python.exe scripts\build_windows_portable.py --zip
```

Output:

- `dist\ARTHIVIO-Offline\`
- `dist\ARTHIVIO-Offline-0.26.zip`

The build downloads the Python embeddable ZIP once into `build-cache\`, copies `openpyxl` 3.1.5
and `et_xmlfile`, and tests the embedded runtime before reporting success. The target machine does
not need the repository, `.venv`, internet, Node, Docker or a database server.

---

## 2. First run

1. Extract the whole ZIP to a writable folder, for example `D:\ARTHIVIO`.
2. Double-click `Start ARTHIVIO.bat`.
3. The browser opens at `http://127.0.0.1:8000/`.
4. The first-run page asks for:
   - your name,
   - business name,
   - email and password (12+ characters),
   - GST state,
   - optional GSTIN.
5. The first account becomes the owner. Setup then closes permanently.

If port 8000 is already used by another program, the launcher tries 8001, 8002 and so on. If
ARTHIVIO itself is already running, the launcher opens the existing instance instead of starting a
second server.

Setup is local-only by default. A remote visitor cannot claim an empty installation. For a managed
first run behind a proxy, the operator can set `ARTHIVIO_ALLOW_REMOTE_SETUP=1` temporarily and
remove it immediately after the owner is created.

---

## 3. Daily use

- Start: `Start ARTHIVIO.bat` or the desktop shortcut.
- Stop: close the ARTHIVIO server window.
- Browser: `http://127.0.0.1:8000/`.
- Data: `data\arthivio.db`.
- Logs: `logs\arthivio.log`.
- System check: **Settings > Controls > System Check**.
- Health endpoint: `http://127.0.0.1:8000/health`.

Keep the entire folder together. Copying only `arthivio.db` while the server is running is not a
safe backup. Use `Backup ARTHIVIO.bat`, which uses SQLite's online backup API and verifies the file
before and after copying.

---

## 4. Backup to an external drive

1. Connect the external drive.
2. Double-click `Backup ARTHIVIO.bat`.
3. Enter a destination folder, for example `E:\ARTHIVIO-Backups`.
4. The script:
   - creates a local consistent backup in `backups\`,
   - verifies SQLite integrity, foreign keys, balanced journals and row counts,
   - copies the file to the external drive,
   - compares SHA-256 hashes,
   - opens the copy read-only and verifies it again,
   - keeps the newest 30 copies on the destination by default.

Nothing is deleted from the local `backups\` folder. Keep at least one verified backup on a
different physical drive. A backup on the same disk does not protect against disk failure.

Manual command:

```powershell
runtime\python.exe scripts\backup_to_drive.py --dest "E:\ARTHIVIO-Backups"
```

---

## 5. Restore procedure

There is deliberately no one-click destructive restore in this build.

1. Stop the ARTHIVIO server.
2. Copy the current `data\arthivio.db` aside as `data\arthivio-before-restore.db`.
3. Choose the backup to restore from the external drive.
4. Verify it first:

   ```powershell
   runtime\python.exe scripts\restore_verify.py --backup "E:\ARTHIVIO-Backups\arthivio-YYYYMMDD-HHMMSS.db"
   ```

5. Only if verification passes, copy the backup to `data\arthivio.db`.
6. Start ARTHIVIO and run **Settings > Controls > System Check**.
7. Open the trial balance and confirm it is balanced before entering new work.

A failed verification means do not restore that file. Try another backup and investigate.

---

## 6. Power cuts and restarts

- A committed journal entry is written to SQLite before the request returns and survives a power
  cut. Unsaved text in an open form does not.
- The database uses WAL mode. Do not copy `arthivio.db` alone while the server is running; use the
  backup button or script.
- After a power cut, start the server again. System Check reports SQLite integrity, foreign keys
  and journal balance.
- `Install autostart.bat` can start ARTHIVIO minimized at Windows login. This is a convenience,
  not a substitute for a UPS or a tested backup routine.
- A UPS is still recommended for the computer and router if the business depends on the app during
  long power cuts.

---

## 7. Optional autostart

Run `Install autostart.bat`:

- creates `ARTHIVIO.lnk` on the desktop (opens the browser),
- creates `ARTHIVIO.lnk` in the Windows Startup folder (starts minimized, no browser).

Run `Remove autostart.bat` to remove both shortcuts. Autostart uses the current Windows user; it
does not install a Windows service and does not require administrator rights.

---

## 8. Updating the package

1. Make a verified backup first.
2. Stop the old server.
3. Extract the new package to a new folder.
4. Copy the old `data\` folder into the new package.
5. Start the new package and run System Check.
6. Keep the old package and backup until the new version has been checked.

Do not overwrite a running database with a new build. The schema is additive, but an update still
deserves a verified backup and a restore drill.

---

## 9. Verification performed for Build 0.26

| Check | Result |
|---|---|
| Full test suite | **353 tests, OK**, 45.926 s, Python 3.14.6, Windows |
| Report tests | 45 tests: report formulas, opening/closing reconciliation, lock register, salesperson/collection, price variance, stock movements, valuation, reorder, dead stock, inventory-to-GL, receivables risk, rule version usage, budget vs actual, budget audit, cash-flow forecast, tax ledger, KPI pack, trend explanation, revenue forecast, anomaly digest, R-204 draft entries, R-508 expiry, R-601 project costing, R-602 WIP, R-603 consumption, R-604 yield, R-605 cost centre, R-902 dimension P&L, R-1004 consolidation, credit-limit detection, malformed journal detection and tenant isolation |
| Draft workflow tests | save draft, post draft, insufficient stock at posting, void with reason, idempotent post, receipt guard and draft-print block |
| Correction workflow tests | 9 `TestPostedCorrections` cases plus the HTTP flow: invoice, bill and payment void/replace, stock restore/undo, blocked replacement and opening-balance replacement |
| Approval tests | pending draft lock, approve, reject with reason, withdraw and `document.approve` gate |
| Security tests | `test_security_headers_and_secure_cookie`: CSP and isolation headers, conditional HSTS and Secure session cookie |
| Restore drill | `scripts/restore_drill.py` passed: backup 0.172 s, total restore + health + login + report 1.44 s, integrity and foreign keys OK |
| Load test | `scripts/load_test.py`: 10 users, 3 page loops, 190 requests, 0 errors, 21.1 req/s, p50 83.4 ms, p95 1229.7 ms |
| Advanced web flow | dimension creation, cost-centre budget, batch creation, production-order creation, dimension-tagged journal posting, all eight new report pages and the project-costing CSV |
| Report HTTP tests | 46 report pages and 41 CSV exports, OK |
| Saved dashboards | `tests/test_dashboards.py` (7 tests) and `test_web.test_54`: validation, CRUD, audit, private/shared visibility, tenant isolation, template creation, grouped template validation, Hindi labels and CSRF delete |
| Line-level drill-down | `tests/test_analytics.py` and `test_web.test_55`: canonical-vs-line reconciliation, account/dimension filters, unsupported metrics, invalid filters, tenant isolation, saved-dashboard filter panel |
| Filtered dashboard totals | `test_analytics.test_filtered_metric_totals_for_dashboard_cards` and `test_web.test_56`: full filtered aggregates, unsupported metrics, invalid-filter fallback and filter-carrying drill-down links |
| Chart-level filtering | `test_analytics.test_filtered_chart_data_uses_matching_posted_lines`: monthly revenue/expense, expense breakdown, top customers and top vendors from matching posted lines, with dimension, account, party and text filters, tenant isolation and invalid-filter rejection |
| Filtered chart surface | `test_web.test_56` confirms the monthly chart is rendered in filtered mode with the **Filtered charts use matching posted journal lines.** note; empty chart states are used instead of fabricated data |
| Embedded runtime import | `openpyxl 3.1.5`, `arthivio 0.26` |
| Package health | `GET /health` returned `ok` from the embedded runtime; `Server: ARTHIVIO/0.26 Python/3.14.6` |
| Template library | **35 templates**, including the six new packs; `full_finance` keeps all 19 registered actual metrics |
| English/Hindi shell | Saved per-user language preference; both English and हिंदी choices are visible in the topbar and on the invoice print toolbar, with the saved choice active; seven navigation headings, 23 menu groups, 89 menu links, shell buttons and common page titles translated; the dashboard, invoice list, bill list, receipts list, payment detail, invoice/bill entry and correction forms, report library and posted-invoice print document are also translated; unknown strings fall back to English |
| Hindi figures | With Hindi saved, displayed money uses Devanagari digits (for example `₹१,२३४.५६`); English restores ASCII digits; `/export/` downloads and `/api/` JSON stay ASCII for portability |
| Hindi auto narration | New invoices, bills, receipts, payments, credit/debit notes, opening balances, ledger merges, voids, replacements, stock adjustments and the manual-journal fallback write Hindi narration; existing posted narration is never rewritten |
| Hindi data boundaries | Document numbers, dates, GSTIN, HSN/SAC, account codes and IDs stay ASCII; report formulas and the invoice amount-in-words value remain English |
| Setup EXE | `ARTHIVIO-Setup.exe` built as a self-extracting EXE, installed to `%LOCALAPPDATA%\ARTHIVIO`, existing `data` and `backups` preserved, desktop and Start Menu shortcuts present, installed health returned `ARTHIVIO/0.26`; rebuilt for the post-release hotfix |
| Package first run | Setup page rendered from the embedded runtime; owner creation covered by `test_first_run` |
| External-drive backup | Local backup verified, copy hash matched, copy re-verified read-only (Build 0.14, unchanged code path) |
| Package size | approximately 15.2 MB (ZIP); 32.0 MB extracted |
| Package data reset | Smoke-test database and logs were kept outside the package; no test data was added to the built folder |

The post-release hotfix rebuilt this package with the login redirect, the Hindi dashboard and
transaction pages, the Hindi report library, the Hindi posted-invoice print document, Devanagari
money display in Hindi mode and Hindi auto narration for new accounting entries. See
`docs/TEST_RESULTS.md` section 48 for the new release hashes.

Not verified in this build:

- Windows installer/MSI, Windows service, code signing, antivirus reputation or a clean-machine
  test on a second PC.
- Real phone viewport, screen reader, contrast, cross-browser, 4K, load, penetration or independent
  accounting review.
- Automatic update delivery, cloud sync, multi-user LAN, UPS integration or permanent hosting.
- Real customer data. The trial and smoke tests used synthetic data only.

---

## 10. Known limits

- Single user, local machine. The app can bind to a LAN address for testing, but this package is
  not hardened for untrusted networks.
- No offline-to-online sync. If the online version is used later, offline entry during an internet
  outage is still a separate, unbuilt feature.
- GST outputs are working aids, not filed returns.
- The report library is translated, but individual report screen bodies and other print/export
  documents remain English. Report formulas and the invoice amount-in-words value also remain English.
- AI insights are deterministic rules over posted records; no generative model is configured.
- Power BI output is a static import pack, not a Power BI Service dataset or `.pbix`.
- No permanent public URL. A Cloudflare quick tunnel or Render free service is temporary/demo-only.
