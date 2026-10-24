# ARTHIVIO — Smarter Finance. Stronger Business.

Business finance, accounting and analytics platform. This repository currently contains **audit documentation and design references only** — no application code has been written yet.

> **Status: NOT RUNNABLE.** There is no app to start. That is a verified fact, not a placeholder.

---

## What is in this folder right now

```
D:\financial business account data analysis\
├── Arthivio Smarter Finance Dashboard.png          design reference (1536×1024)
├── WhatsApp Image 2026-10-24 at 10.10.22 AM.jpeg   design reference (1536×1024)
├── README.md                                        this file
├── .gitignore                                       secrets/db/node excluded
└── docs\
    ├── SOFTWARE_AUDIT.md              audit report (evidence-based)
    ├── FEATURE_INVENTORY.md           142 specified features, all NOT IMPLEMENTED
    ├── TEST_PLAN.md                   90 test cases
    ├── TEST_RESULTS.md                results of run RUN-2026-10-24-01
    ├── BUG_REPORT.md                  9 open defects (B-001 … B-009)
    ├── REQUIREMENTS.md                30 product + 9 financial + 11 security + 10 NFR requirements
    ├── ARCHITECTURE.md                decided stack, boundaries, layout
    ├── DATABASE_DESIGN.md             Phase 1 schema + Phase 2 outline
    ├── SECURITY_PLAN.md               threat model, RBAC, security gates
    ├── BACKUP_AND_RECOVERY.md         RPO/RTO, restore drill, honest status
    ├── ACCOUNTING_RULES.md            money, rounding, posting, report formulas
    ├── COMPLIANCE_MATRIX.md           30 rows, 0 implemented
    ├── API_INTEGRATIONS.md            12 planned, 0 connected
    ├── REPORT_CATALOG.md              66 reports, 0 implemented
    ├── DEVELOPMENT_ROADMAP.md         phases 0–10 with gates
    ├── REQUIREMENTS_TRACEABILITY.md   requirement → module → test → status
    ├── DECISION_LOG.md                decisions (D-001-D: Option A approved)
    └── PROJECT_SPEC.md                governing specification (copied, hash-verified)
```

Baseline commit: `9052071` on branch `main`. Nothing pushed to GitHub.

---

## How to run it

You can't. There is no code.

```powershell
cd "D:\financial business account data analysis"
# no package.json, no requirements.txt, no app entry point
```

Once Phase 1 exists, this section will contain the exact commands. Until then, any command claiming to start ARTHIVIO would be false.

---

## Verified environment

| Tool | Status |
|---|---|
| Python 3.14.6 + pip 26.1.2 | ✅ installed |
| Node.js 20.20.2 + npm 10.8.2 | ✅ **portable** (`C:\Users\vicky\node-portable\…`) — not on `PATH` |
| git 2.56.0 | ✅ **portable** (`C:\Users\vicky\git-portable`) — not on `PATH` |
| PostgreSQL | ❌ not installed |
| Docker | ❌ not installed (not required locally) |
| Disk free on D: | ✅ ≈ 876 GB |

Full detail: `docs/SOFTWARE_AUDIT.md` §3.

---

## Current audit conclusion

- Features implemented: **0**
- Features verified working: **0**
- Reports verified against transactions: **0** (none exist)
- Tests executed against application code: **0**
- Audit checks executed: **12** → 5 pass, 6 fail, 1 blocked
- Remote GitHub repository inspected: exists, but contains **only a 144-byte README** — no code
- Blocking defect: **B-001 — no application source**

The audit did **not** invent results. Everything that could not be checked is marked `BLOCKED`, not `PASS`.

---

## Decisions — settled

1. ✅ **Stack: Option A** — Next.js (TypeScript) + FastAPI (Python), approved 2026-10-24 (`D-001-D`). Node 20 and git are already on the machine in portable form; no installs needed.
2. ✅ **Database** — file-based DB for Phase 1 (SQLite/WAL), PostgreSQL-ready schema, migration path documented (`DATABASE_DESIGN.md`, `DF-01`).
3. ✅ **Version control** — repository initialised, baseline committed. No push to GitHub.

**Open (non-blocking):** location of the home-page theme (OQ-01) — needed only at Phase 6 (UI), not Phase 1.

---

## Where we are

| Phase | Status |
|---|---|
| Phase 0 — audit + planning | ✅ **Complete** (this documentation set) |
| Phase 1 — secure foundation | ⏳ **Awaiting owner go-ahead** |
| Phases 2–10 | Not started |

Phase 1 = authentication, tenant isolation, roles/permissions, audit log, backup + verified restore. No financial modules until that gate passes.

---

## Rules this project follows

No silent failure. No silent financial correction. No unsupported financial claim. No unverified critical output. No cross-tenant data access. No false payment or government-verification status.

Corollary used throughout the audit: **a feature is not "done" until implementation, tests and documentation agree.** Nothing here claims otherwise.

---

## ओनर के लिए हिंदी में सार

- अभी इस फोल्डर में **कोई सॉफ्टवेयर नहीं है** — सिर्फ दो डिज़ाइन तस्वीरें और पूरा प्लान/ऑडिट डॉक्यूमेंट है।
- इसलिए ऑडिट में हर फीचर `BLOCKED` लिखा है, `PASS` नहीं। झूठी रिपोर्ट नहीं बनाई गई।
- कंप्यूटर में Python है, और Node.js + Git भी हैं (पोर्टेबल फोल्डर में, PATH में नहीं)। PostgreSQL नहीं है — इसलिए Phase 1 में SQLite। 
- आपने Option A approve किया — अब Git repo बन गया और पहला commit हो गया (कुछ भी GitHub पर push नहीं हुआ)।
- अगला कदम: आपकी हाँ के बाद **Phase 1** — लॉगिन, अलग-अलग कंपनी का डेटा अलग रखना, roles, ऑडिट लॉग, बैकअप + restore टेस्ट।
- पूरी रिपोर्ट: `docs/SOFTWARE_AUDIT.md`, और प्लान: `docs/DEVELOPMENT_ROADMAP.md`।
