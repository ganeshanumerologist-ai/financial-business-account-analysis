# ARTHIVIO Offline Edition

**Build 0.17. Single-user Windows package. No Python install, no internet, local SQLite.**

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
- `dist\ARTHIVIO-Offline-0.17.zip`

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

## 9. Verification performed for Build 0.17

| Check | Result |
|---|---|
| Full test suite | **290 tests, OK**, 29.028 s, Python 3.14.6, Windows |
| Report tests | 32 tests: report formulas, opening/closing reconciliation, lock register, salesperson/collection, price variance, stock movements, valuation, reorder, dead stock, inventory-to-GL, receivables risk, cash-flow forecast, tax ledger, KPI pack, trend explanation, revenue forecast, anomaly digest, credit-limit detection, malformed journal detection and tenant isolation |
| Report HTTP tests | 35 report pages and 30 CSV exports, OK |
| Embedded runtime import | `openpyxl 3.1.5`, `arthivio 0.17` |
| Package health | `GET /health` returned `ok` from the embedded runtime; `Server: ARTHIVIO/0.17 Python/3.14.6` |
| Package first run | Setup page rendered from the embedded runtime; owner creation covered by `test_first_run` |
| External-drive backup | Local backup verified, copy hash matched, copy re-verified read-only (Build 0.14, unchanged code path) |
| Package size | About 30 MB (ZIP) |
| Package data reset | Smoke-test database and logs were kept outside the package; no test data was added to the built folder |

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
- AI insights are deterministic rules over posted records; no generative model is configured.
- Power BI output is a static import pack, not a Power BI Service dataset or `.pbix`.
- No permanent public URL. A Cloudflare quick tunnel or Render free service is temporary/demo-only.
