# ARTHIVIO — Decision Log

Append-only. New decisions get a new ID; superseded ones are marked, never deleted.

---

## D-000 — Audit performed read-only

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided |
| Context | Owner requested a full audit of an "existing" financial software. |
| Decision | Perform inspection, evidence collection and documentation only. No application files created or modified, no fixes applied, no behaviour changed. |
| Rationale | Audit execution policy: "Do not implement fixes yet. Do not modify application behavior during this audit." |
| Consequence | Zero runtime verification possible; every feature recorded `BLOCKED`. |

---

## D-001 — Application stack for Phase 1

| | |
|---|---|
| Date | 2026-10-24 |
| Status | ~~PENDING~~ → **DECIDED as Option A on 2026-10-24** (see D-001-D). Toolchain facts revised in D-001-R1. |
| Context | Spec §20 proposes Next.js + TypeScript, Python + FastAPI, PostgreSQL. Original finding: only Python installed. **Corrected in D-001-R1:** portable Node 20.20.2 and git 2.56.0 exist; PostgreSQL and Docker are absent. |
| Decision | Not yet made. |
| Blocker | Cannot start Phase 1 without an approved stack, because it determines dependency installs, project layout and every architecture document. |

### Options

**Option A — Follow the spec literally**
~~Install Node.js LTS + Git~~ *(no install needed — portable Node 20 + git found; see D-001-R1)*, then Next.js (TS) frontend, FastAPI backend, PostgreSQL.

- ➕ Matches spec §20 exactly; strongest ecosystem for the premium dashboard UI; Playwright E2E available.
- ➖ PostgreSQL still needs a decision (installer, portable server, or paid managed service); heavier for a beginner owner to operate than a single-language stack.
- Cost: ₹0 in licences. Risk: setup friction, version drift.

**Option B — Python-only Phase 1 (recommended)**
FastAPI + server-rendered Jinja2 templates + HTMX + a small amount of vanilla JS, SQLite for local dev with a documented PostgreSQL migration path.

- ➕ Runs on what is already installed — zero system installs to start; fastest route to a *tested* secure foundation (auth, tenant isolation, RBAC, audit log, backup/restore); single language for the owner to learn; the JSON API boundary is preserved so a Next.js front end can be added later without rewriting the backend.
- ➖ Server-rendered UI is less "SaaS-modern" out of the box than React — but achievable at premium quality with disciplined CSS, SVG and a chart library; the ≈150-template analytics layer will eventually want a richer client, so a Next.js migration is likely in Phase 6.
- Cost: ₹0. Risk: UI polish requires more hand-crafting; eventual front-end migration effort.

**Option C — Full stack with Docker**
Containerise everything for reproducibility.

- ➕ Clean, reproducible environments.
- ➖ Docker is not installed; heaviest setup burden; overkill before a working foundation exists.

### Recommendation

**Option B for Phase 1, plus initialising a git repository regardless** (B-002 is a data-loss risk; git 2.56 is already available, so no install). Re-evaluate at Phase 6, when report density justifies a React-class client. **See D-001-R1: if the owner is comfortable approving dependency downloads, Option A is now equally practical and is the better long-term fit for the 4K–8K analytics UI.**

Rationale in one line: *the fastest path to a verified, tested, secure foundation is the stack that already runs on this machine.*

### What the owner must say

> "Approve Option B" — or — "Approve Option A" (and confirm I may download npm/pip dependencies and choose the Phase 1 database).

No code will be written before this answer.

---

## D-001-R1 — Revision to D-001 (toolchain found, recommendation updated)

| | |
|---|---|
| Date | 2026-10-24 (second pass, same day) |
| Status | **Supersedes the context of D-001; decision still PENDING** |
| Trigger | Deeper machine inspection found portable **Node 20.20.2 / npm 10.8.2** (`C:\Users\vicky\node-portable\node-v20.20.2-win-x64`) and **git 2.56.0** (`C:\Users\vicky\git-portable`). Both run correctly when called by path. |

**What changes**

- D-001's premise that "Node must be installed for Option A" is **wrong** and is withdrawn. Option A requires **no installation** — only `npm install` of project dependencies (free, network download).
- Therefore the *only* genuine technical blocker left is the **database**: PostgreSQL is absent, and a managed service would be a paid external service (prohibited without approval).
- B-003 is downgraded High → Medium; B-002 becomes trivially fixable with the portable git.

**Revised recommendation**

- If the owner approves downloading npm + pip dependencies: **Option A** (Next.js + FastAPI), file-based DB for Phase 1, PostgreSQL path documented. Best fit for a premium high-density analytics UI at 4K–8K.
- If the owner prefers the fastest path to a *tested* secure foundation: **Option B** still stands and remains the lower-risk choice.
- Either way, `git init` + baseline commit should happen first — it is reversible, local-only, and protects the work. **No push.**

**Unchanged:** no application code until the owner answers.

---

## D-001-D — Owner decision: Option A approved

| | |
|---|---|
| Date | 2026-10-24 |
| Status | **DECIDED — Option A approved** |
| Owner input | "a" (in response to the stack question, interpreted as Option A: Next.js + FastAPI) |
| Decision | Build with **Next.js (TypeScript) + FastAPI (Python)**, file-based DB for Phase 1 with a documented PostgreSQL migration path. |
| Implications | `npm install` and `pip install` approved (free, no paid services) · no system installs required · portable Node 20 + git used via `dev.ps1` |
| Scope boundary | This approves the **stack**, not unrestricted feature work. Phase 1 remains auth + tenancy + RBAC + audit + backups. |
| Immediate actions taken | `git init` (branch `main`), `.gitignore` created, baseline commit `9052071` (11 files), no push |
| Next gate | Owner approval to begin **Rule 2 / Phase 1 implementation** |

---

## D-002 — Governing specification copied into the repository

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided |
| Context | B-007: spec lived only in `C:\Users\vicky\Downloads`, duplicated, unversioned. |
| Decision | Copy byte-for-byte to `docs/PROJECT_SPEC.md`. |
| Verification | Line count 763; SHA-256 `4556C71479BB5D26F95641EA650F214DE0314FD1BCD925711B08F4062E967682` — identical to source and to the second copy. |
| Consequence | Requirements now survive outside Downloads. The Downloads copies are **not** deleted (owner confirmation required). |

---

## D-003 — Mockups are design references, not the specification of record

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided |
| Context | The two mockups conflict with spec §4 (city-photo hero) and §5 (unverified statistics) — B-004, B-005 — and with each other (B-008). |
| Decision | Where a mockup and the spec disagree, **the spec wins**. Preserve the mockups' layout language (nav, KPI strip, chart grid, module tiles); reject the photographic hero and all statistical claims. |
| Rationale | Spec §4/§5 are explicit, owner-authored constraints. Mockups are concepts. |
| Consequence | The delivered UI will look structurally similar to the mockups but not pixel-identical. This is intentional and must not be treated as a regression. |

---

## D-004 — "8K UHD / high resolution" interpreted as resolution independence

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided |
| Context | Owner asked for 8K UHD visual quality. Both mockups are 1536×1024 raster (B-006). Spec §4 notes "8K is not a substitute for responsive design, sharp assets or accessible text." |
| Decision | Target: vector UI (SVG icons/logo), CSS layout that scales to 7680×4320, DPI-independent charts, `srcset` for any photography, readable type at all densities. Do **not** upscale the raster mockups. |
| Consequence | Visual quality is a property of the implementation, not of the reference images. Acceptance is judged at 360 px, 1440 px, 2560 px and 4K with text legibility and contrast measured (WCAG AA), not by pixel count alone. |

---

## D-005 — No Firebase, no paid APIs, no new modules beyond spec

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided |
| Context | Owner's audit rules 2–3. |
| Decision | Use only free/local components. Any paid or external service requires a new decision entry plus owner approval. |
| Consequence | Auth is self-hosted (session cookies + strong KDF), storage is local, charts are open-source. |

---

## D-006 — No application tests reported as passing

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided |
| Context | Audit rule 6 and spec §2.8. |
| Decision | In `TEST_RESULTS.md`, unexecutable tests are `BLOCKED`, never `PASS`. "Passed" requires literal command output captured in the same run. |
| Consequence | Current reported pass count (3) covers only environment/document checks, not product behaviour. |

---

## Deferred decisions (not blocking Phase 1 start)

| ID | Topic | When |
|---|---|---|
| DF-01 | Development DB vs production DB final choice (SQLite dev → PostgreSQL prod) | Phase 1, before migrations are written to production |
| DF-02 | Password hashing parameters and session lifetime policy | Phase 1 |
| DF-03 | Chart library selection (ECharts vs alternatives) | Phase 6 |
| DF-04 | Front-end migration to Next.js | Phase 6 review |
| DF-05 | Hosting provider and cost ceiling | Phase 10, owner approval |
| DF-06 | Real GST/e-invoice API onboarding | Phase 9, after official access + professional review |
| DF-07 | Backup off-site destination | Phase 1 backup foundation → hardening in Phase 10 |
| DF-08 | Brand name/domain/trademark availability | Before public launch |


---

## D-007 — Runtime stack: zero-dependency Python + SQLite (deviation from D-001-D)

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided, owner acknowledgement pending |
| Context | Option A (Next.js + FastAPI) was approved. On this machine PyPI is unreachable: `pip install` times out even for SQLAlchemy (`Connection timed out while downloading`, `No matching distribution found`). npm responds (PONG in ~6 s), so npm works, but the Python backend could not be installed at all. |
| Decision | Build the accounting core and Phase 1 controls with the Python standard library only (`http.server`, `sqlite3`, `hashlib.scrypt`, `unittest`), and defer the Next.js front end until dependency installation is reliable. |
| Rationale | The release gate is financial correctness and security, not the HTTP framework. A stdlib build is runnable and testable today, has no supply-chain surface, and keeps the same schema and service boundaries so FastAPI/Next.js can wrap it later without rewriting accounting logic. |
| Consequence | The UI is server-rendered rather than React. `docs/ARCHITECTURE.md` and the Phase 6 plan change. Revisit when PyPI is reachable or a vendored wheel set is approved. **Amended by D-035 (2026-10-28):** the accounting core stays standard-library + SQLite; `openpyxl==3.1.5` is approved for `.xlsx`, and ECharts is vendored locally. No framework migration was made. |

## D-008 — Build order: accounting slice before the React front end

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided |
| Context | Owner requires invoices, ledger and reports ("pura account"), not a foundation-only deliverable. |
| Decision | Deliver a vertical slice — posting engine → invoices → ledger/TB/P&L/BS → customer statements → UI — with tests at each step, then continue with receipts, purchases, credit notes and GST. |
| Consequence | The foundation controls (tenancy, RBAC, CSRF, audit, sessions) ship inside the same slice rather than as a separate phase, so no accounting feature exists without tenant isolation and an audit trail. |


## D-009 - Complete the transaction cycles before adding breadth

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided |
| Context | Owner asked for a platform that behaves like a real accounting product ("jis tarah se kaam karta ho usi tarah"), not an invoice-only demo. |
| Decision | Finish the two core cycles end-to-end before adding secondary features: sales (invoice to receipt to ageing to statement) and purchases (bill to vendor payment to ageing to vendor statement), plus credit notes, day book, manual journals, GST summary and CSV exports. Each slice ships with unit + HTTP tests and a browser check. |
| Consequence | The product now covers the daily bookkeeping loop an SME actually performs. Debit notes, GSTR-1 JSON, PDF and bank reconciliation remain explicitly out of scope for this build and are listed as open gaps. |

## D-010 - Backups are only "verified" after four independent checks

| | |
|---|---|
| Date | 2026-10-24 |
| Status | Decided |
| Context | A backup that has never been opened is not a backup. The audit rules require evidence, not claims. |
| Decision | `app/backup.py` uses SQLite's online backup API, then opens the copy read-only and checks: (1) `PRAGMA integrity_check`, (2) `PRAGMA foreign_key_check`, (3) every tenant's journal debits equal credits, (4) row counts match the live source. Only then is the run stored as `verified` with its SHA-256. Restores stay manual and are re-verified with `scripts/restore_verify.py`. |
| Consequence | Failed or tampered backups are recorded as `failed` and never presented as safe. There is no one-click destructive restore in this build. The row-count list is schema-complete for persistent business tables (29 at Build 0.7), excluding only ephemeral sessions and the backup-run log; a test compares it with `sqlite_master` so additive tables cannot escape verification. |


## D-011 - GSTR-1 export is a labelled working aid, not a filing

**Date:** 2026-10-24. **Status:** accepted for Build 0.3.

The GST portal's GSTR-1 JSON schema changes and requires supplier credentials. Building an
"upload" claim without portal verification would violate the no-unverified-claims rule.
Therefore the product produces a sectioned CSV and a documented JSON
(`arthivio-gstr1-working-v1`) with B2B, B2C small, HSN and credit-note data, exact INR decimal
strings, warnings and an explicit note that it is not a filed return. Portal upload, GSTR-3B
and the official schema remain future work.

## D-012 - Invoice PDF is produced by the browser, not a PDF library

**Date:** 2026-10-24. **Status:** accepted for Build 0.3.

The print view is a standalone A4 HTML document with print CSS and a `window.print()` action;
the user chooses "Save as PDF". This avoids adding an unverified PDF dependency and keeps the
zero-dependency runtime. A server-side PDF renderer can be added later without changing the
invoice data model.

## D-013 - Settings are owner-only; schema changes are additive

**Date:** 2026-10-24. **Status:** accepted for Build 0.3.

GSTIN, bank details and invoice terms affect legal documents, so only the owner
(`tenant.manage`) can change them; other roles can view. New columns are added with
`ALTER TABLE ... ADD COLUMN` and defaults, never by dropping or rebuilding tables, so existing
books survive upgrades. There is still no general migration framework; destructive schema
changes remain prohibited.

## D-014 - Purchase returns reverse the original bill value, not the current average cost

**Date:** 2026-10-24. **Status:** accepted for Build 0.4.

A debit note against a bill reverses the bill line's taxable value and input GST, reduces the
vendor payable, and takes stock out at the original purchase value. The item's weighted-average
cost is then restated from the remaining inventory value, so the balance sheet does not invent a
gain or loss. Quantity is capped at the unreturned quantity on that bill line; stock cannot go
negative; a paid bill can still be returned, producing a vendor credit (negative payable).
Returns of non-stock purchases credit the Purchases account instead of inventory. The original
bill is never edited.

## D-015 - Bank reconciliation links statement lines to existing journal lines only

**Date:** 2026-10-24. **Status:** accepted for Build 0.4.

A bank statement line never creates a journal entry by itself. Imported lines are matched to
posted journal lines on the bank account (`1010`) with the exact same signed amount. Suggestions
use a ±7-day window; auto-match only takes candidates with a unique best score and leaves ties
for manual review. CSV imports are deduplicated by a SHA-256 hash of account, date, normalized
description/reference and amounts. Manual match/unmatch is audited. Unmatched statement lines
that need a journal (bank charges, interest) are surfaced with a note; auto-posting them is
deliberately left for a later slice.

## D-016 - GSTR-3B is a working, head-wise preparation aid

**Date:** 2026-10-24. **Status:** accepted for Build 0.5.

GSTR-3B figures are computed from posted documents: outward taxable value and output tax from
invoices less credit notes; ITC from purchase bills less debit notes. The tax control accounts
are used as an independent reconciliation check, not as the source of the return. Set-off is
head-wise only, so IGST credit is not cross-utilised against CGST/SGST; a negative output head is
carried forward and an ITC reversal above available ITC is shown as payable. RCM, zero-rated,
nil/exempt and import ITC are not modelled. The page and CSV state clearly that this is a
preparation aid, not a filed return, and every reconciliation check exposes its difference rather
than hiding or auto-correcting it.

## D-017 - Team access uses one-time invite links and protected owner authority

**Date:** 2026-10-25. **Status:** accepted for Build 0.6.

ARTHIVIO does not send email in this build. An owner/admin creates an invite and receives a
one-time link; only the SHA-256 hash of the bearer token is stored. Invites expire after seven
days and are revoked when a newer invite is created for the same business/email. A new email sets
its own password (minimum 12 characters); an email that already has an ARTHIVIO login must enter
its current password and is not silently merged. The owner role cannot be assigned or changed
through the UI, self role/status changes are blocked, and suspending or removing a member revokes
that member's sessions immediately. Existing users can belong to multiple businesses and switch
the session's active business; every switch is checked against an active membership. Ownership
transfer and per-permission editing are deliberately not implemented yet.

## D-018 - Customer/vendor statements can be shared as read-only bearer links

**Date:** 2026-10-25. **Status:** accepted for Build 0.6.

A statement share is scoped to one business, one customer or vendor, and an explicit date range.
The link contains a random bearer token; only its SHA-256 hash is stored, and the token is shown
once at creation. Links expire after 7, 30 or 90 days, can be revoked immediately, and can be
viewed without an ARTHIVIO login. The public page is a print-ready A4 statement with
`noindex, nofollow` and `Cache-Control: no-store`; it exposes no internal document IDs, other
parties, ledger accounts or business settings. View counts are recorded. The link grants only
that one statement, not access to the business.

## D-019 - GSTR-2B reconciliation reports differences and never changes the books

**Date:** 2026-10-25. **Status:** accepted for Build 0.6.

The GSTR-2B import accepts a documented working CSV, not the GST portal's official JSON schema.
Files are deduplicated by SHA-256 across the business; importing the same file again returns the
existing period and adds nothing. A new file for the same month supersedes the previous active
import, while the prior import and its rows remain in history. Matching uses supplier GSTIN plus
a normalised invoice number; exact taxable/tax amounts give `matched`, amount differences give
`mismatch`, a 2B line without a posted bill gives `missing_in_books`, and a posted bill in the
month without a 2B line gives `missing_in_2b`. Differences are reported with expected/actual
figures and warnings; bills are never edited, ITC is never auto-posted, and no return is filed or
uploaded. Duplicate 2B invoice numbers and multiple posted bills with the same vendor invoice are
surfaced as warnings rather than silently resolved.

## D-020 - ITC review is an annotation, not an ITC claim or accounting entry

**Date:** 2026-10-25. **Status:** accepted for Build 0.7.

Each active GSTR-2B line can carry one current ITC review state: `open`, `follow_up`, `itc_hold`
or `accepted`, with a 500-character note, the reviewing user and a timestamp. A line with no row
is treated as `open`. Only the latest active import can be reviewed; superseded lines are
read-only. Every change is audited with the previous and new state. Review states are internal
working-paper annotations: `itc_hold` does not post an ITC reversal, `accepted` does not claim
ITC, and no review action edits a bill, journal, GSTR-2B amount or GSTR-3B figure.

The monthly comparison shows GSTR-3B eligible ITC (net of debit notes), the gross 3B figure,
debit-note reversal, GSTR-2B ITC, the difference, and review amounts by state. The difference is
reported, never forced to zero. The comparison is explicitly a preparation aid, not a filed
return, and it does not assert that a portal ITC claim was made. Review actions require
`gst.reconcile`; read-only roles see the state but cannot change it.


## D-021 - Public home page is read-only; the no-signin demo is an explicit local flag

**Date:** 2026-10-25. **Status:** accepted for Build 0.8.

`GET /` for a signed-out visitor (and `GET /home` always) returns a static product page built
from inline CSS/SVG. It is intentionally independent of tenant data and uses a clearly labelled
synthetic dashboard preview, avoiding customer logos, testimonials and invented usage statistics.
Signed-in `/` remains the existing dashboard, so the change does not replace the app's working
surface.

A no-signin link was requested for demoing. Instead of weakening login globally, `/demo` is
opt-in via `ARTHIVIO_DEMO_AUTOLOGIN=1`, checks the peer address is loopback, creates a normal
session for the demo owner, and writes `auth.demo_login` to the audit log. With the flag off or a
remote peer, the route returns 404. `dev.ps1 -Demo` sets the flag for local use; normal runs remove
it. This keeps the public repository and any network-bound run on the authenticated path.

## D-022 - Public home page uses the supplied navy/electric-blue reference palette

**Date:** 2026-10-25. **Status:** accepted for Build 0.8. Workspace palette part superseded by D-030, then by D-031.

The supplied home-page reference uses a dark navy hero, electric-blue actions, a cyan headline
accent and restrained green accents. The public landing page follows that palette and the
reference's section rhythm: dashboard navigation, hero plus dashboard preview, six feature cards,
five reasons, and the trust strip. The reference's marketing metrics are retained as visibly
labelled illustrative values (`*` plus a footnote), not verified production claims. The signed-in
workspace keeps its established ivory/emerald/gold theme so operational screens, printed documents
and accounting state styling stay stable. The landing page is self-contained: it no longer includes
the workspace CSS, and its preview is labelled synthetic sample data.

## D-023 - Tally-style grouped top navigation replaces the flat workspace sidebar

**Date:** 2026-10-25. **Status:** accepted for Build 0.9.

The owner asked for a Tally-like menu bar where related pages sit under one main heading instead
of appearing as a long flat list. The workspace now uses a sticky top menu with direct Dashboard
plus grouped dropdowns: Transactions (Sales/Purchases), Books (day books, ledgers, banking),
Reports (financial statements, ageing), Tax Returns (GST working papers), Masters (customers,
vendors, items) and Settings (workspace, controls). Native `<details>/<summary>` elements provide
keyboard and no-JavaScript operation; a small script closes other menus, outside clicks and Escape.
Cash Book and Bank Book were added under Books as posted-ledger views of accounts 1000 and 1010,
not cached or manually entered books. The public landing page is unchanged.

## D-024 - Ledger is the account hub; entries are separate and corrections are reversible

**Date:** 2026-10-25. **Status:** accepted for Build 0.10.

The owner asked to see every ledger account in one place, open any account's full ledger, and add
a new account from that same page instead of hunting through settings. The Ledger page therefore
lists all accounts grouped by the five account types, shows each balance with Dr/Cr, and carries an
inline add-account form for roles with `account.manage`. Clicking an account changes only the
selected ledger on the same page.

Recording is deliberately separate from viewing. The Entries menu holds Cash Entry, Bank Entry and
Journal Entry. Cash and Bank Entry preselect the relevant control account; Journal Entry is the
general balanced-entry screen. Posting still goes through the same integer-paise engine, and a
successful post redirects to the affected ledger.

Manual journals are corrected by reversal, never by editing posted lines. The reversal requires a
reason, posts a mirrored entry, marks the original `reversed`, and records `journal.reverse` in the
audit trail. Invoice and bill corrections continue to use credit/debit notes or source-document
actions. `account.manage` is granted to owner, admin and accountant, not to read-only users.

## D-025 - Zoho Books is a workflow reference, not a visual template

**Date:** 2026-10-25. **Status:** accepted for Build 0.10.

The owner reviewed Zoho Books' sidebar and dashboard to explain the accounting workflow, and
explicitly said the product should not be copied as-is. The useful lesson is the grouping:

- day-to-day sales and purchases stay together as transactions;
- banking has its own area for accounts, books and reconciliation;
- accounting/ledger work is separate from recording entries;
- every report sits under one Reports heading;
- masters and settings stay out of the daily posting flow.

ARTHIVIO keeps its own Tally-style grouped top menu and ivory/emerald/gold workspace. It does not
copy Zoho's visual design, student-edition branding or dashboard metrics. The information
architecture follows the workflow above, with the Ledger hub as the chart-of-accounts entry point
and Cash/Bank/Journal entries kept separate.

## D-026 - Opening balances are balanced journals, never editable account fields

**Date:** 2026-10-26. **Status:** accepted for Build 0.10.

The owner asked how to add a ledger account and how to enter its opening balance, both when the
account is created and later. A plain "opening balance" number on the account row would make the
books silently unbalanced, so the implementation uses the existing posting engine instead:

- the selected account's ledger carries a **Set opening balance** form for roles with
  `account.manage`;
- the form takes an amount, an explicit Debit/Credit side (defaulted from the account type) and a
  date, then posts one journal entry with `source_type='opening'`;
- the other side goes to **Opening Balance Equity** (`3200`, created lazily per tenant so an
  existing `3200` owned by the business is never reused);
- the date cannot be in the future and must be on or before the account's first posted activity;
- only one posted opening entry is allowed per account; replacing it requires reversing the entry
  with a reason, exactly like a manual journal;
- every opening balance writes `opening_balance.set` to the audit trail.

The post-creation redirect opens the form automatically, so the user can create the account and
enter the opening figure in one flow. Income and expense accounts can accept an opening figure for
migration, but their normal year-end treatment is outside this decision. Bulk opening-balance
import remains unbuilt; profile editing does not change the opening journal.

## D-027 - One Account 360 profile at creation; product economics stay in the item master

**Date:** 2026-10-26. **Status:** accepted for Build 0.10.

The owner asked that opening a ledger account capture every relevant detail at once, for any kind
of account-using entity (company, shop, hospital, real-estate company, school/college, multinational
or other). Waiting until later produces incomplete ledgers and silently different behaviour
between customers, vendors and ordinary accounts.

The account flow is therefore **Account 360**:

- account classification is a real group (`debtor`, `creditor`, `bank`, `loan`, `sales`, `purchase`,
  etc.) stored on `account.group_code`; the five accounting types remain the posting balance rule;
- company/legal name, contact, address, GSTIN, PAN, CIN, organisation type, industry, credit days
  and credit limit, bank details, loan lender/account/sanction/maturity/interest/tenure/EMI/security
  and free notes are stored in one additive `account_profile` row;
- a debtor or creditor group also creates or links a customer or vendor sub-ledger; invoices, bills,
  receipts, payments, credit notes and debit notes post to that linked ledger when present;
- an opening balance is still a balanced journal (D-026), never an account field;
- profile edits change descriptive data only, require `account.manage`, and write `account.update`
  to the audit trail. Posted amounts are never rewritten.

**Product-wise price, margin and GST do not belong on the ledger.** One sales ledger can contain
many products, so margin, MRP, HSN/SAC, category, brand, barcode, cost, sale price, GST rate, stock
and the default sales ledger are captured in the **item master**. The account form links to Items
instead of duplicating those fields. This keeps the chart of accounts and the product catalogue as
separate concepts while still capturing both at the point of setup.

## D-028 - One account type / group selector, five internal accounting types

**Date:** 2026-10-26. **Status:** accepted for Build 0.10.

The owner expects the account-creation choice to look like the long classification list used by
Indian accounting software: asset, liability, capital/equity, revenue/income, expense, receivable,
cash, bank, inventory, fixed asset, loan, tax, suspense, retained earnings, drawings, depreciation,
purchase, sales, profit & loss, debtor, creditor, sundry debtor and sundry creditor. A separate
five-option Type dropdown made those business choices harder to find.

The form therefore uses one **Account type / group** selector. Every option is a real group with one
of the five accounting types behind it; selecting a group derives the type, normal Dr/Cr side and
group hint. The server still stores and validates `account.type` and `account.group_code`
separately, and legacy `type`-only account creation remains accepted. This keeps debit/credit
correctness, the trial balance, reports and audit trail unchanged while giving the user the long
business classification list in one place.

`Suspense A/c` is a temporary liability group; it is not automatically cleared. `Profit & Loss A/c`
is an equity group for workflows that keep a separate P&L account; the P&L report is still computed
from income and expense postings and year-end closing remains unbuilt.

## D-029 - Bulk opening balances are a validated, all-or-nothing wrapper over one journal per account

**Date:** 2026-10-26. **Status:** accepted for Build 0.11.

Migrating an existing business means entering many opening balances at once. The owner asked for a
practical import path, but opening figures are exactly where a partial or silently corrected import
would damage the books. The implementation therefore keeps the existing accounting rule (D-026) and
adds only a preview-and-posting wrapper:

- **Preview first.** The CSV is parsed and every row is validated before anything is written. The
  preview shows the account, side, amount, date, note, row status and per-account Dr/Cr totals. The
  net difference is shown as the Opening Balance Equity side.
- **One journal per row.** Each row calls the same `set_opening_balance` service used by the ledger
  form. It posts a balanced `source_type='opening'` journal against Opening Balance Equity, so each
  account keeps its own opening entry that can be reviewed, party-tagged or reversed individually.
  A single compound journal was rejected because one correction would disturb unrelated accounts.
- **All-or-nothing.** Posting runs inside one outer transaction. If any row fails after an earlier
  row has posted, the whole import rolls back: no partial opening balances and no half-created
  Opening Balance Equity account.
- **No silent account creation and no re-import.** A missing code is an error, not a request to
  invent a ledger. An account with an existing opening is rejected; correction still requires
  reversing the old entry and importing a replacement. This prevents duplicate opening figures.
- **Same date/lock/permission rules.** A row's date must be valid, not in the future, not inside a
  locked period and on or before the account's first posted activity. Posting requires
  `account.manage`.
- **Audit, not a file store.** The CSV itself is not retained. The audit log records the filename,
  row count, Dr/Cr totals and created entry IDs; each account also gets the normal
  `opening_balance.set` event. A CSV `note` is appended to the journal narration and copied into the
  per-account audit metadata.
- **No schema change.** There is no import table and no new account column. The journals, their
  lines and the audit log remain the record.

The import lives under **Books → Ledgers → Bulk Opening Balances** and is linked from the Ledger
page. It is a starting-balance migration tool, not a recurring transaction import and not a
replacement for period closing.

## D-030 - Workspace uses the public home page palette

**Date:** 2026-10-26. **Status:** accepted for Build 0.11; the navy topbar/ink part is superseded by D-031.

The owner asked that the signed-in pages use the colour combination of the public home page; a
separate workspace theme looked disconnected. The workspace now uses the public page's navy
`#0B1F3A`, electric blue `#2563EB`, cyan `#67E8F9`, light blue `#F6F9FF` and restrained green
`#22C55E` family. The logo mark, navigation, cards, forms, tables, badges, buttons, print invoices
and statements all follow those tokens. Red remains reserved for danger and error states.

Layout, spacing, navigation structure, accounting semantics, ledger behaviour and printed document
content are unchanged. The old ivory/emerald/gold workspace tokens are removed rather than kept as
a second theme, so pages cannot drift back accidentally. D-022's public-page palette decision still
stands; its statement that the signed-in workspace keeps the ivory/emerald/gold theme is superseded
by this decision.

## D-031 - White workspace topbar and four user-selectable light palettes

**Date:** 2026-10-26. **Status:** accepted for Build 0.11. Amends D-030; the public-landing sentence is amended by D-032.

The owner asked for three or four colour options so each user can change the whole platform to their
own preference, and separately asked that the signed-in pages use **no dark blue or navy blue**.
D-030's navy `#0B1F3A` topbar and ink therefore no longer apply to the workspace.

The signed-in app now uses a white topbar, neutral charcoal ink `#212529`, a light page ground and
four saved palettes:

| Key | Name | Primary | Page / line family |
|---|---|---|---|
| `ocean` (default) | Ocean Blue | `#2563EB` | `#F6F9FF` / cool blue |
| `emerald` | Emerald Green | `#15803D` | `#F4FBF7` / green |
| `violet` | Royal Violet | `#7C3AED` | `#F8F5FF` / violet |
| `sunset` | Warm Sunset | `#C2410C` | `#FFF8F1` / terracotta |

The choice is personal, not tenant-wide: it is stored in the additive `user.theme` column (default
`ocean`) and saved from **Settings → Appearance** through `POST /preferences/theme`. Saving requires
a signed-in user and CSRF, writes `user.theme_updated` to the audit log, and sets a non-sensitive
`ui_theme` cookie so the sign-in page reflects the last chosen palette. Print invoices and public
statement pages use the same tokens, with the public statement defaulting to Ocean.

Layout, spacing, navigation structure, accounting semantics, ledger behaviour, reports and printed
document content are unchanged. No dark-blue/navy token remains in the signed-in stylesheet. The
public landing hero was unchanged by this decision; D-032 later made it slightly lighter and added a
page-level picker. `test_37` guards the four palettes and the no-navy rule; `test_38` covers
selection, persistence, audit, login-page cookie and printed-document theming.

## D-032 - Slightly lighter landing hero with a page-level colour picker

**Date:** 2026-10-27. **Status:** accepted for Build 0.11. Amends the public-landing sentence in
D-030/D-031.

The owner asked to make the public landing hero “a little lighter” and to give users a colour-choice
option. The landing page therefore keeps a **dark** hero but moves from the original near-black navy
to a lighter navy gradient (`#0C3157` → `#0A2A48` → `#061A30`) with four dark variants:

| Key | Landing hero family | Accent |
|---|---|---|
| `ocean` (default) | lighter navy | cyan/teal |
| `emerald` | dark green | mint |
| `violet` | dark violet | lavender |
| `sunset` | dark terracotta | peach |

A compact palette button in the landing header links to `/home?theme=<key>`. The server validates the
key against the fixed allow-list, sets the non-sensitive `ui_theme` cookie and redirects to `/home`;
invalid or missing values fall back to Ocean. The landing page reads only that cookie, never tenant
data, and remains a standalone document without the workspace stylesheet. The picker does **not**
write `user.theme` or the audit log: the saved workspace palette remains **Settings → Appearance**
(D-031). The landing page is still dark in every variant and never turns into a light page.

Layout, navigation structure, accounting semantics and the signed-in white/no-navy workspace are
unchanged. `test_37` checks the landing theme map, dark CSS variables and picker links; `test_38`
checks the theme query/cookie switch and restores Ocean afterwards.

## D-033 - Account archive and merge are additive, audited and never destructive

**Date:** 2026-10-27. **Status:** accepted for Build 0.11.

The owner asked for the next accounting slice to let obsolete ledgers be closed without deleting
history or silently editing posted entries. Account deletion was rejected because posted
`journal_line` rows must remain immutable and auditable.

The `account` table gains four additive columns: `status` (`active`/`archived`, default `active`),
`archived_at`, `archived_by` and `merged_into_id`. Existing databases receive them through
`_ensure_columns`; no existing account, journal, party or item row is rewritten.

**Archive rules**

- Requires `account.manage`, a reason and an all-time balance of exactly zero.
- System/control accounts are locked: cash 1000, receivable 1100, inventory 1200, payable 2000,
  GST control accounts 2100-2102 and 2200-2202, COGS 5000, purchases 5100, rounding 5900, and the
  Opening Balance Equity group.
- Customer/vendor-linked ledgers cannot be archived; they must be merged into another ledger for
  the same party so the party pointer and statement stay consistent.
- An income ledger referenced by products cannot be archived until those products are repointed.
- Archiving writes `account.archive` and hides the account from new posting selectors while keeping
  its full ledger, reports and history. No journal is posted by archiving.
- Restore clears the archive fields, writes `account.restore` and makes the account postable again.
  It does not reverse a previous merge journal; a correction remains an explicit manual journal.

**Merge rules**

- Requires `account.manage`, a reason, an active source and an active target of the same
  `account.type`; source and target must be different.
- The source's net balance is moved by one balanced `source_type='merge'` journal dated today.
  History is never edited or deleted, and the trial balance stays balanced.
- Bank ledgers can only merge into bank ledgers. Customer/vendor ledgers can only merge into a
  ledger linked to the same party; the customer/vendor pointer is repointed to the target.
  Products using a merged income ledger are repointed to the target sales ledger.
- System/control accounts cannot be a source or target, and the source cannot have future-dated
  activity. A locked posting period still blocks the reclassification journal.
- The source is then marked `archived` with `merged_into_id` set. `account.merge` records the reason,
  source/target codes, transfer amount, journal entry and repointing counts.
- A merge is intentionally not a one-click undo. Restore can reopen the source, but the
  reclassification journal remains; correcting the balance requires an explicit manual journal.

The archive/merge UI is reached from the ledger's profile card. Archived ledgers remain selectable
in the ledger hub under a separate archived list and keep their posted history. No schema or UI
change was made to Cash Book, Bank Book or Ledger read-only calculations.


## D-034 - Phase A analytics uses read-only views and an explicit actual-only contract

**Date:** 2026-10-27. **Status:** accepted for Build 0.11.

The owner approved starting the analytics work while the AI, `.xlsx` and Power BI decisions remain
open. Phase A therefore uses only the existing standard library and SQLite:

- Two additive read-only views, `v_analytics_journal` and `v_analytics_monthly`, derive facts from
  the immutable journal. They do not copy rows, cache totals or create a second ledger.
- `app/analytics.py` publishes 19 actual-only metrics with a written source, formula, permission and
  drill-down. Every amount remains integer paise.
- `GET /api/v1/analytics/catalog` and `GET /api/v1/analytics/overview` require a session,
  `report.view` and tenant membership; they return `no-store` JSON and never expose another tenant.
- `/reports/analytics` is a pilot screen under the existing single Reports dropdown. It shows
  actuals, zero-filled monthly gaps, composition and top parties; it does not mix estimates or
  forecasts and is not counted as one of the 66 catalogued reports yet.
- No AI, `.xlsx`, Power BI writer, external provider or paid service is added. Those phases remain
  blocked on owner decisions AN-D1 to AN-D4 and dependency approval AN-D3.
- The server keeps its loopback default. `ARTHIVIO_HOST=0.0.0.0` is an explicit opt-in for trusted
  LAN/phone access; the local demo must not be exposed to an untrusted network.

This decision is intentionally reversible: the views and API can be extended without changing
accounting tables or posted history.


## D-035 - Approved Excel/BI dependencies and the no-provider AI boundary

**Date:** 2026-10-28. **Status:** accepted for Build 0.12; dependency approval recorded.

The owner confirmed the previously requested dependency approval ("approval to diya tha... approval
h"). Build 0.12 therefore uses the smallest approved set and keeps every financial authority in the
deterministic accounting engine:

- `openpyxl==3.1.5` is the only new Python runtime dependency. It is used both to build the real
  `.xlsx` actuals workbook and to convert an uploaded `.xlsx` file to neutral CSV before the existing
  opening-balance, bank-statement and GSTR-2B validators run. Uploads are capped at 8 MB and 50,000
  non-empty rows; formulas use cached values only and are never evaluated by ARTHIVIO.
- Apache ECharts 5.5.1 is vendored at `app/static/echarts.min.js` under its Apache-2.0 notice and
  served locally. There is no runtime CDN call and no chart data is fabricated; the chart consumes
  the same deterministic monthly actuals series as the fallback table.
- The Power BI deliverable is a **static import ZIP** containing actuals facts, dimensions, the
  metric catalog, a Power Query starter and a SHA-256 manifest. It is not a `.pbix`, a Power BI
  Service dataset, a token API, an RLS model or a scheduled-refresh package.
- The AI deliverable is explicitly **deterministic grounded insights** (`engine=deterministic_rules_v1`,
  `generative_ai=false`). Every observation has a written basis, metric keys, a drill-down target and
  a source. No external model is called and no forecast is mixed into actual totals.
- No generative AI provider, Power BI Service scope, schema change or paid service is added. Those
  remain separate decisions requiring provider/key, consent, privacy, cost and licensing choices.
- Build 0.12 is verified by **245 tests, OK**, 23.224 s, Python 3.14.6, Windows, plus live read-only
  checks recorded in `docs/TEST_RESULTS.md` `RUN-2026-10-28-01`.

