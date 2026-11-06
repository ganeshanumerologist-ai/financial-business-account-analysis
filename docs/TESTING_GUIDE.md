# ARTHIVIO single-user trial test guide

This guide is for checking the software end to end before a real accounting
pilot. Use **synthetic data only**. Do not enter real customer, bank or GST data
in the public trial URL.

## 1. How to open the trial

- Local laptop: `http://127.0.0.1:8000/login`
- Public trial URL: the current `trycloudflare.com` link shared in chat
- Trial login: `ganesha4558@gmail.com` / `Ganesha4558!2026`
- Demo login: `owner@arthivio.test` / `ArthivioDemo!2026`

The public trial runs against a separate database:
`data/arthivio-trial.db`. It is not the main local database.

On a clean offline install, `/login` opens `/setup` instead. Create the owner there; the setup page
closes permanently after the first account. The Windows offline package and its backup/restore
steps are in `docs/OFFLINE_EDITION.md`.

## 2. How to know if something stopped or failed

### Page does not open

1. Open `/health`.
   - Body `ok` means the ARTHIVIO server is running.
   - No response means the server, tunnel or internet connection is down.
2. Open `/system-check` after signing in.
   - Shows SQLite integrity, foreign keys, journal balance, backups, disk space
     and the last 20 log lines.
3. Check the log file on the machine running the trial:
   - `logs-trial/arthivio.log`
   - Local server: `logs/arthivio.log`

### Page shows an error

The app now shows a **500 error page** with an error ID such as
`ERR-04057DC89B`. The same ID is written to the log with the full traceback.
Send that ID, the page URL, the time and what you clicked.

### Data safety after a power cut

- A posted entry is committed to SQLite before the page returns.
- A power cut cannot create a half-posted journal.
- Text still sitting in an unsaved form is lost.
- Use a UPS and take regular backups to an external drive.

## 3. A-to-Z test checklist

Mark each item **Pass / Fail / Confusing** and add a note.

### A. Login and session

- [ ] Open the login page
- [ ] Wrong password shows a clear error
- [ ] Correct password opens the dashboard
- [ ] Refresh keeps the session
- [ ] Sign out returns to login
- [ ] Directly opening a private page while signed out redirects to login

### B. Business identity

- [ ] Open Settings
- [ ] Change business name, GSTIN, address, bank details
- [ ] Invalid GSTIN is rejected with a clear message
- [ ] Theme switch works (Ocean Blue, Emerald Green, Royal Violet, Warm Sunset)

### B2. Fresh test books (recommended before entering entries)

- [ ] Open **Businesses**
- [ ] Under **Start fresh books**, enter a new business name and GST state
- [ ] Create it; the page must switch to an empty ledger with a notice
- [ ] Confirm the new business has no journal entries
- [ ] Add your own ledger account, or use the ready-made Cash/Bank/Sales/Expense accounts
- [ ] Switch back to the demo business at any time from **Businesses**

### C. Masters

- [ ] Create a customer
- [ ] Create a vendor
- [ ] Create an item/product
- [ ] Create a ledger account
- [ ] Add opening balance
- [ ] Edit an account profile
- [ ] Archive an account with a reason
- [ ] Restore an archived account
- [ ] Try archiving an account with a non-zero balance

### D. Sales cycle

- [ ] Create an invoice with one line
- [ ] Create an invoice with multiple lines, discount and GST
- [ ] Check the invoice total manually
- [ ] Print the invoice
- [ ] Record a receipt against the invoice
- [ ] Check the customer outstanding reduces
- [ ] Create a credit note against the invoice
- [ ] Check the credit note posts a balanced journal

### E. Purchase cycle

- [ ] Create a bill
- [ ] Record a vendor payment
- [ ] Check the vendor outstanding reduces
- [ ] Create a debit note against the bill
- [ ] Check the purchase register

### F. Banking

- [ ] Create a bank account
- [ ] Import a bank statement CSV or XLSX
- [ ] Run auto-match
- [ ] Manually match one line
- [ ] Unmatch one line
- [ ] Check the bank book

### G. Entries

- [ ] Post a cash entry
- [ ] Post a bank entry
- [ ] Post a journal entry with equal debit and credit
- [ ] Try an unbalanced journal; it must be rejected
- [ ] Open **Edit** on a cash, bank or journal entry
- [ ] Change the amount or narration, give a reason and save
- [ ] Confirm the original is marked **reversed** and a corrected voucher is posted
- [ ] Confirm the ledger, cash book, bank book and day book show Edit/Reverse actions
- [ ] Try an unbalanced correction; the original must stay posted
- [ ] Reverse a journal with a reason

### H. Books

- [ ] Ledger shows opening, movement and closing
- [ ] Cash Book shows Edit/Reverse on manual entries
- [ ] Bank Book shows Edit/Reverse on manual entries
- [ ] Day Book lists the new entries and gives Edit/Reverse on manual entries
- [ ] Source documents show **Open source**, not a direct overwrite

### I. Financial statements

- [ ] Trial Balance shows **Balanced**
- [ ] Profit & Loss shows revenue, expenses and net profit
- [ ] Balance Sheet shows **A = L + E**
- [ ] Cash Flow shows **Reconciled**
- [ ] Financial Ratios render
- [ ] Period Comparison renders
- [ ] Working Capital Cycle renders

### J. Registers and ageing

- [ ] Sales Register
- [ ] Purchase Register
- [ ] Expense Breakdown
- [ ] Receivables Ageing
- [ ] Payables Ageing
- [ ] Reversal Register
- [ ] Account Activity

### K. GST working papers

- [ ] GST Summary / GSTR-1
- [ ] GSTR-3B Working
- [ ] GSTR-2B import
- [ ] GSTR-2B review
- [ ] Check the page says it is a working aid, not a filed return

### L. Exports

- [ ] CSV export opens in Excel
- [ ] Excel workbook downloads and opens
- [ ] Power BI ZIP downloads and contains the expected files
- [ ] GSTR-1 JSON downloads
- [ ] Totals in the export match the screen

### M. Report Library

- [ ] Report Library opens
- [ ] It shows 57 of 66 working
- [ ] Planned reports are clearly marked and do not show fake data
- [ ] Every working report opens without a 500 error
- [ ] Sales summary, top customers, product sales, discounts and sales returns open
- [ ] Top suppliers and purchase returns open
- [ ] Stock summary shows opening + in - out = closing for each item
- [ ] Stock adjustments post an increase/decrease with a reason and appear in the register
- [ ] A stock decrease below available quantity is rejected
- [ ] Credit-limit utilisation flags over-limit or no-limit customers
- [ ] Trial balance exceptions shows a clean result on the demo and a review badge when a bad entry exists
- [ ] Budget vs Actual opens from the Reports menu
- [ ] A budget can be set for an income/expense ledger and month
- [ ] Setting the same month and ledger updates the existing amount
- [ ] A budget can be removed and the removal appears in the Audit Log
- [ ] Budget vs Actual shows `No budget` when no budget is stored
- [ ] Each new report's CSV downloads and opens

### N. Backup and restore

- [ ] Create a backup
- [ ] Backup shows `verified`
- [ ] Backup file exists in the backup folder
- [ ] Run the restore verification script
- [ ] Stop the server, restart it, and confirm the data is still there

### O. Error handling

- [ ] Open `/system-check`
- [ ] It shows database, backup and log health
- [ ] Force a test error (developer only) and confirm an error ID appears
- [ ] Confirm the same error ID is in `logs-trial/arthivio.log`

### P. Mobile browser

- [ ] Open the public trial URL on a phone using Wi-Fi
- [ ] Open it using mobile data/SIM
- [ ] Login works
- [ ] Dashboard is readable
- [ ] Invoice page is usable
- [ ] Report tables scroll horizontally
- [ ] Buttons are not cut off

### Q. Network and power interruption

- [ ] Turn off Wi-Fi while the app is open; see what the browser shows
- [ ] Turn Wi-Fi back on and refresh
- [ ] Close the browser mid-entry; confirm no partial journal was posted
- [ ] Stop the server; confirm `/health` stops responding
- [ ] Restart the server; confirm data is still there
- [ ] Simulate a power cut only after taking a backup

### R. Security checks

- [ ] Open another user's invoice ID; it must not be visible
- [ ] Submit a form without the CSRF token; it must be rejected
- [ ] Try a very large upload; it must be rejected
- [ ] Check that sign-out revokes the session
- [ ] Check the Audit Log records important actions

### S. Performance

- [ ] Dashboard loads in a reasonable time
- [ ] Report Library loads
- [ ] Excel export completes
- [ ] Power BI ZIP completes
- [ ] No page shows `None`, `NaN` or a raw Python traceback

## 4. What to send for each problem

Copy this format:

```text
Time:
Page / URL:
Login used:
What I clicked:
What I expected:
What happened:
Error ID (if shown):
Screenshot:
```

## 5. Known limits in this trial

- 57 of 66 catalogued reports are working; none is partial and 9 are planned.
- No generative AI provider is connected.
- Power BI is an external reporting layer, not an embedded live model.
- The public trial URL is temporary and has no uptime guarantee.
- There is no automatic offline-to-online sync in this build.
- A standalone Android/iOS app is not built; mobile uses the browser.
- Free hosting can reset data; the trial database is for checking only.
