# ARTHIVIO — Bug Report

| Field | Value |
|---|---|
| Report date | 2026-10-24 |
| Run | `RUN-2026-10-24-01` |
| Open defects | 9 |
| Fixed defects | 0 |
| Status | No fixes implemented — audit-only run per policy |

Severity: **Blocker** (cannot proceed) · **High** (material risk / spec violation) · **Medium** (degraded quality or safeguard gap) · **Low** (minor) · **Info** (observation).

---

## B-001 — No application source code exists

| Field | Value |
|---|---|
| Severity | **Blocker** |
| Area | Whole project |
| Status | Open |
| Blocks | Every functional audit task, every test, all phases |

**Description**
The workspace `D:\financial business account data analysis` contains only two image files. There is no source code, entry point, dependency manifest, configuration, database or test suite. The requested "audit of the existing software" has no subject.

**Reproduction**
```powershell
cd "D:\financial business account data analysis"
Get-ChildItem -Force -Recurse | Select-Object FullName, Length
```

**Expected:** application source tree, manifest, tests, config, at minimum a runnable entry point.
**Actual:** 2 files — `Arthivio Smarter Finance Dashboard.png`, `WhatsApp Image 2026-10-24 at 10.10.22 AM.jpeg`. No directories.

**Impact:** Software cannot be launched, so navigation, forms, calculations, imports/exports, reports, persistence and security cannot be verified. Zero features can be claimed as working.

**Recommended fix (not implemented):** proceed to Phase 1 implementation from the approved plan. This is a *build* defect, not a code defect — it cannot be "fixed" by patching.

---

## B-002 — No git repository in the workspace

| Field | Value |
|---|---|
| Severity | **High** |
| Area | Engineering process / data safety |
| Status | Open |
| Correction | The first pass said "git not installed". That was wrong: git **2.56.0** exists at `C:\Users\vicky\git-portable` and runs correctly. It is simply not on `PATH`. The absence of a *repository* is the actual defect. |

**Description**
The workspace is not a git repository. There is no change history, no diff, no rollback. The audit rules require that existing work never be corrupted; without version control that guarantee rests on manual discipline alone.

**Reproduction**
```powershell
Test-Path "D:\financial business account data analysis\.git"   # False
$env:PATH="C:\Users\vicky\git-portable\cmd;$env:PATH"; git --version   # git version 2.56.0.windows.2
```

**Expected:** repository initialised, baseline commit tagged, `.gitignore` excluding secrets and databases.
**Actual:** no repository exists. A working git binary is available at an absolute path.

**Impact:** A mistaken edit can destroy work irreversibly. Once a database exists, unprotected schema/data changes become a real data-loss path.

**Recommended fix:** run `git init` with the portable binary, commit the audit baseline + mockups + spec, add `.gitignore` (`*.db`, `.env*`, `__pycache__/`, `node_modules/`, `dist/`). **No push** (rule 7). No installation needed.

---

## B-003 — Toolchain not on `PATH`; no database server

| Field | Value |
|---|---|
| Severity | **Medium** *(downgraded from High — Node and git exist after all)* |
| Area | Toolchain / architecture |
| Status | Open |

**Description**
Node **v20.20.2** and npm **10.8.2** are present at `C:\Users\vicky\node-portable\node-v20.20.2-win-x64`, and git at `C:\Users\vicky\git-portable`. None is on `PATH`, so ordinary commands fail with "not recognized". PostgreSQL is genuinely absent.

Two consequences:
1. Every command must either use absolute paths or a session-scoped `PATH` prefix — easy to forget, produces confusing failures.
2. No relational server exists, so the spec's PostgreSQL target needs a decision (portable server, managed service = paid and prohibited without approval, or file-based DB first).

**Reproduction**
```powershell
node -v                                              # fails: not recognized
$env:PATH="C:\Users\vicky\node-portable\node-v20.20.2-win-x64;$env:PATH"; node -v   # v20.20.2
Get-Command psql -ErrorAction SilentlyContinue       # nothing
```

**Expected:** toolchain callable by name; database target chosen and reachable.
**Actual:** portable tools exist but are off-`PATH`; no database server.

**Impact:** Blocks reproducible builds and any DB-dependent test. Does **not** block frontend development, so the original "front end cannot build" claim is withdrawn.

**Recommended fix:** add both portable folders to the user `PATH` (reversible, requires approval), document a `dev.ps1` bootstrap that sets `PATH` for the session, and record the database decision in `docs/DECISION_LOG.md` (DF-01).

---

## B-004 — Reference mockups violate the design constraints

| Field | Value |
|---|---|
| Severity | **Medium** |
| Area | UI / brand compliance |
| Status | Open |

**Description**
Spec §4 mandates: *"Do not use a large city image as the main visual element"*, *"Business dashboards, modern data visualizations and a restrained growth motif should be the main visual focus"*, and a warm-ivory ground (`#F7F5EF`). Both mockups use a full-bleed dusk **city skyline photograph** as the dominant hero, with white as the page ground and the ivory palette unused.

**Reproduction**
1. Open `Arthivio Smarter Finance Dashboard.png`.
2. Observe hero: photograph occupies roughly the top half, skyline + globe + light-streak motif.
3. Compare against spec §4 constraints.

**Expected:** data-visualisation-led hero on warm ivory, restrained growth motif, no decorative photography dominant.
**Actual:** photographic city hero; ivory absent; photographic depth competes with the dashboard panel.

**Impact:** Implementing the mockups literally would ship a design that fails its own governing spec, and reduce legibility/contrast of dashboard content against a busy photograph.

**Recommended fix:** keep the mockup's *structure* (nav, KPI strip, chart grid, module tiles) but rebuild the hero as a vector/data composition on `#F7F5EF`, with an illustrated growth motif instead of stock photography.

---

## B-005 — Mockups publish unsupported business claims

| Field | Value |
|---|---|
| Severity | **High** |
| Area | Legal / marketing integrity |
| Status | Open |

**Description**
Both mockups display: **"50,000+ Happy Businesses"**, **"120+ Countries"**, **"99.99% Uptime"**, **"Trusted by Businesses Worldwide"**, and a logos/"Retail · Manufacturing · …" trust bar. Spec §5 forbids publishing unsupported customer counts, uptime percentages or performance claims; §2.8 forbids fabricating results.

**Reproduction**
1. Open either mockup.
2. Read the footer statistics band.

**Expected:** no unverifiable claims; illustrative figures clearly labelled or omitted.
**Actual:** specific quantitative claims with no data source.

**Impact:** If shipped, these are unsubstantiated marketing assertions — a legal/trust risk, and a direct violation of the governing instructions.

**Recommended fix:** remove the numeric claims entirely for launch, or replace with explicitly labelled illustrative placeholders in non-public drafts. Never publish uptime or customer counts without measured evidence.

---

## B-006 — Mockups are 1536×1024 raster, not usable as 8K assets

| Field | Value |
|---|---|
| Severity | **Info** |
| Area | Asset quality |
| Status | Open |

**Description**
Both images measure **1536 × 1024 px** (verified by parsing PNG IHDR and JPEG SOF headers). The owner requested "8K UHD" quality. These are small raster comps of a marketing page; they cannot be scaled to 4K/8K displays without blur, and they cannot serve as UI at all.

**Reproduction**
```powershell
python -c "<parse PNG IHDR / JPEG SOF>"   # PNG 1536x1024 · JPEG 1536x1024
```

**Expected for 8K-class delivery:** vector UI, CSS/SVG assets, `srcset` for photography, layout that scales to 7680×4320 without raster upscaling.
**Actual:** 1536×1024 screenshots.

**Impact:** None functionally. Sets the correct expectation: "8K" will be achieved through responsive vector UI and high-DPI rendering, not by blowing up these files.

**Recommended fix:** none on the files. Build the UI as components (SVG icons, CSS gradients, canvas/ECharts charts) so output is resolution-independent.

---

## B-007 — Governing specification lives outside the repository

| Field | Value |
|---|---|
| Severity | **Medium** |
| Area | Documentation / governance |
| Status | Open |

**Description**
The 763-line master spec resides at `C:\Users\vicky\Downloads\ARTHIVIO_OpenCode_Master_Build_Prompt_WITH_RULES.md`, outside the project. Two byte-identical copies exist (same SHA-256), so there is no version conflict today — but if Downloads is cleaned or the machine changes, the source of truth is lost, and any future edit to one copy diverges silently.

**Reproduction**
```powershell
Get-FileHash "C:\Users\vicky\Downloads\ARTHIVIO_OpenCode_Master_Build_Prompt_WITH_RULES.md" -Algorithm SHA256
```

**Expected:** spec committed inside the repo, versioned.
**Actual:** external, unversioned, duplicated.

**Impact:** Requirements governance risk; future sessions may work from a stale or missing spec.

**Recommended fix:** copy the spec into `docs/PROJECT_SPEC.md`, record the hash in `docs/DECISION_LOG.md`, and delete the duplicate from Downloads after owner confirmation.

---

## B-008 — The two mockups disagree on dashboard figures

| Field | Value |
|---|---|
| Severity | **Low** |
| Area | Design consistency |
| Status | Open |

**Description**
The two mockups are near-identical but differ in numbers: "Business Performance" shows Sales 48% / Services 24% / Inventory 14% / Other 8% in one, and 62% / 18% / 12% / 8% in the other. Inventory value reads `$1,12,480` (Indian grouping) alongside `$248,620` (Western grouping) in the same screen.

**Reproduction**
1. Open both images side by side.
2. Compare the donut legend percentages and the currency formatting.

**Expected:** a single authoritative data contract for a dashboard preview, and one consistent locale format.
**Actual:** conflicting percentages; mixed `1,12,480` and `248,620` grouping.

**Impact:** Ambiguity for implementation; risk of shipping inconsistent number formatting across locales. Note: mixed grouping in one view is a genuine formatting bug pattern to avoid in code (use a single locale formatter).

**Recommended fix:** treat both mockups as concepts only; define the real dashboard from live tenant data with a locale-aware single money formatter (`en-IN` grouping or `en-US`, chosen per tenant locale, never mixed).

---

## B-009 — Owner-reported files (prompt, theme, repository) are absent

| Field | Value |
|---|---|
| Severity | **Medium** |
| Area | Project state / expectation mismatch |
| Status | Open |

**Description**
The owner stated that the prompt/rules, a Git repository, and a home-page theme had been copied into `D:\financial business account data analysis`. Verification across three independent sources found none of them:

1. **Local disk** — recursive listing: only the 2 PNG/JPEG mockups and the 7 audit documents created by this audit. No HTML/CSS/JS/TS files, no `.git`.
2. **Machine-wide search** — no recent theme files anywhere outside an unrelated numerology website (`C:\Users\vicky\Documents\Default Project`, remote `ganesha_num.git`, last changed 2026-10-18). No portable ARTHIVIO copy.
3. **GitHub** — `ganeshanumerologist-ai/financial-business-account-analysis` exists, public, but contains **only a 144-byte README.md**. Two commits, both README-only. No code, no theme.

**Reproduction**
```powershell
Get-ChildItem "D:\financial business account data analysis" -Force -Recurse
# → 2 images + docs\*.md only

curl https://api.github.com/repos/ganeshanumerologist-ai/financial-business-account-analysis/contents/
# → [{"name":"README.md","size":144,...}]
```

**Expected:** prompt, theme source and repo present in the workspace.
**Actual:** none present in any of the three locations.

**Impact:** Work may exist somewhere not yet located — on another device, a cloud-synced folder that did not sync, or a chat attachment. If it is later found, there is a real risk of building a second, divergent copy. Nothing was lost or overwritten by this audit; the files simply were never here.

**Recommended fix:** owner supplies the exact path or a link to the theme/repo. Until then, the two mockups remain the only visual reference, and the spec in `docs/PROJECT_SPEC.md` (hash-verified) is the requirement source of truth.

---

## Defect summary

| ID | Severity | Title | Status | Fixable by code? |
|---|---|---|---|---|
| B-001 | Blocker | No application source | Open | No — requires build |
| B-002 | High | No git repository in workspace | Open | Yes — `git init` with portable git |
| B-003 | Medium | Toolchain off `PATH`; no database server | Open | Yes — `PATH` config + DB decision |
| B-004 | Medium | Mockups violate design constraints | Open | Yes — redesign hero |
| B-005 | High | Unsupported marketing claims | Open | Yes — remove claims |
| B-006 | Info | Mockups not 8K-capable | Open | N/A — build vector UI |
| B-007 | Medium | Spec outside repository | Open | Partly fixed — copied to `docs/PROJECT_SPEC.md` (D-002) |
| B-008 | Low | Mockups disagree on figures | Open | Yes — single formatter |
| B-009 | Medium | Owner-reported prompt/theme/repo absent everywhere | Open | No — owner must supply location |

**Defects found in existing application code: 0** — because no application code exists. All nine are baseline, process, toolchain or reference-asset findings.

---

## What would a *real* bug report look like after Phase 2

Recorded here as the quality bar, so this file does not stay empty-but-decorative. Example format the team must follow once the accounting engine exists:

```
BUG-2026-11-03-004 — Trial balance off by ₹0.01 after multi-line discount
Severity: Critical            Area: accounting/posting
Steps: 1) create invoice with 3 lines, 7% proportional discount, 18% GST
       2) post  3) open Trial Balance for the period
Expected: Σ debit == Σ credit exactly
Actual:   credit side short by 0.01
Evidence: test ACC-012 fails; ledger dump attached
Impact:   misstated TB; blocks reporting
Fix:      allocate rounding residual to the largest line per policy §C-006
```

Rule: no "fixed" status without a failing-then-passing test recorded in `docs/TEST_RESULTS.md`.
