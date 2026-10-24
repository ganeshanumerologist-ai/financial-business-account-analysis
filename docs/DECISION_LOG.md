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
| Status | **PENDING — OWNER APPROVAL REQUIRED (blocking)**. Toolchain facts revised in D-001-R1 below; the decision itself is unchanged. |
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
