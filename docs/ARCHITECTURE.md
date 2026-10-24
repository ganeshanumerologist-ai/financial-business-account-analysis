# ARTHIVIO — Architecture

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-10-24 |
| Status | Draft for owner approval |
| Decision | **Option A** — Next.js (TypeScript) + FastAPI (Python), approved 2026-10-24 (D-001) |

---

## 1. Stack

| Layer | Choice | Version (target) | Why |
|---|---|---|---|
| Frontend | Next.js (App Router) + TypeScript | 15.x / TS 5.x | Component UI, high-DPI vector rendering, future report density, spec §20 fit |
| Styling | Plain CSS modules + design tokens (no heavy UI kit) | — | Full control over the ivory/emerald/gold palette; avoid licensing and bloat |
| Charts | Apache ECharts | 5.x | Maintained, canvas/SVG, crisp at 4K, large datasets |
| Backend | FastAPI | 0.11x | Typed API, automatic OpenAPI, Python ecosystem for finance logic |
| Validation | Pydantic v2 | 2.x | Strict schemas, decimal support |
| ORM / SQL | SQLAlchemy 2.x + Alembic | 2.x | Explicit transactions, migrations |
| Database | SQLite (Phase 1) → PostgreSQL (production path) | — | Zero-install now; PostgreSQL-ready schema, no SQLite-only SQL |
| Password KDF | Argon2id (`argon2-cffi`) | — | Current best practice, no external service |
| Sessions | Server-side session table + opaque cookie | — | Revocable, no JWT-in-localStorage risk |
| Tests | pytest (+ Hypothesis later), Vitest/Playwright at Phase 6 | — | Deterministic finance tests are the release gate |

Runtime note: `C:\Users\vicky\node-portable\node-v20.20.2-win-x64` (Node 20.20.2 / npm 10.8.2) and `C:\Users\vicky\git-portable` (git 2.56.0). Neither is on `PATH`; a `dev.ps1` bootstrap will set it per session.

---

## 2. Component view

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (desktop / tablet / mobile)                          │
│  Next.js UI — server components + client islands              │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTPS (local: http://localhost)
                            │ credentials: session cookie
┌───────────────────────────▼──────────────────────────────────┐
│  Next.js server (port 3000 in dev)                            │
│  • renders pages, holds no secrets                            │
│  • calls backend with the user's session cookie               │
└───────────────────────────┬──────────────────────────────────┘
                            │ JSON /api/v1
┌───────────────────────────▼──────────────────────────────────┐
│  FastAPI app (port 8000)                                      │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Auth       │  │ Authorisation│  │ Domain services      │   │
│  │ sessions   │→ │ tenant+role  │→ │ (Phase 2+: ledger,   │   │
│  │ CSRF       │  │ policy gate  │  │  invoicing, stock)   │   │
│  └────────────┘  └──────────────┘  └──────────┬───────────┘   │
│         │                                      │              │
│  ┌──────▼──────────────────────────────────────▼───────────┐  │
│  │ Data access layer — every query takes tenant_id         │  │
│  │ SQLAlchemy 2.x · explicit transactions                  │  │
│  └──────────────────────────┬──────────────────────────────┘  │
└─────────────────────────────┼─────────────────────────────────┘
                              │
                   ┌──────────▼───────────┐      ┌──────────────┐
                   │ SQLite (WAL) Phase 1 │      │ Backup store │
                   │ → PostgreSQL prod    │─────▶│ ./backups    │
                   └──────────────────────┘      └──────────────┘
```

---

## 3. Request flow with tenancy enforcement

1. Request arrives with session cookie.
2. `resolve_session()` → user, membership list, active tenant.
3. `require_permission(permission, tenant_scope)` → 403 if not allowed.
4. Handler calls a service with an explicit `TenantContext` object.
5. Repository methods require `TenantContext` and inject `tenant_id` into **every** query — there is no code path that queries a tenant table without it.
6. Response is serialised from a schema that contains no other tenant's identifiers.

Defence in depth: application-level scoping now, **PostgreSQL Row-Level Security planned** for production (`SET LOCAL app.tenant_id`). The file DB cannot enforce RLS, so Phase 1 compensates with a single repository entry point plus tests that attempt cross-tenant reads.

---

## 4. Proposed repository layout

```
/
├── apps/
│   ├── web/                 # Next.js front end
│   │   ├── app/             # routes (App Router)
│   │   ├── components/
│   │   ├── lib/             # api client, auth helpers
│   │   └── styles/          # tokens, modules
│   └── api/                 # FastAPI back end
│       ├── app/
│       │   ├── main.py
│       │   ├── core/        # config, security, tenancy, errors
│       │   ├── models/      # SQLAlchemy
│       │   ├── schemas/     # Pydantic
│       │   ├── services/    # domain logic (no HTTP)
│       │   ├── api/v1/      # routers
│       │   └── db/          # session, repositories
│       ├── migrations/      # Alembic
│       └── tests/
├── docs/
├── scripts/                 # dev.ps1, backup, restore-verify
└── .github/                 # CI later (no auto-push)
```

---

## 5. API conventions

- Base path `/api/v1`, JSON only, UTF-8.
- Error envelope: `{"error": {"code": "TENANT_FORBIDDEN", "message": "...", "fields": {...}, "correlation_id": "..."}}`.
- Never leak stack traces or SQL; log them server-side with the correlation ID.
- Idempotency: `Idempotency-Key` header required on document-creating endpoints (Phase 2+).
- Pagination: cursor-based for ledgers, `limit` + `after`; page-based only for small reference lists.
- Dates: ISO 8601; all timestamps stored UTC; business dates stored as `DATE` in the tenant's timezone context.

---

## 6. Frontend architecture

- Server components for data-heavy pages; client islands only for interactivity (filters, forms).
- Design tokens in one place: ivory `#F7F5EF`, emerald `#176B4D`, sage `#DCE8D9`, gold `#C6A15B`, ink `#183E35`.
- Typography scale with a minimum 16 px body, 1.5 line-height; contrast checked to WCAG AA.
- Charts: ECharts with `devicePixelRatio` respected → sharp on 4K/8K, no raster backgrounds.
- No city photography, no unverifiable statistics (spec §4, §5; defects B-004, B-005).
- States required on every data view: loading, empty, error, permission-denied, offline/stale.

---

## 7. Security architecture (summary — detail in `docs/SECURITY_PLAN.md`)

| Concern | Approach |
|---|---|
| Passwords | Argon2id, per-user salt, pepper from env, configurable cost |
| Sessions | Opaque 256-bit token, hashed at rest, HttpOnly/Secure/SameSite=Lax, 30 min idle + 12 h absolute |
| CSRF | Double-submit token bound to session, required on mutating requests |
| Authorisation | Permission strings (`ledger.post`, `export.report`) checked server-side |
| Tenancy | `TenantContext` required by repositories + RLS plan |
| Secrets | `.env` (git-ignored) + `.env.example` documented; no defaults for production |
| Audit | Append-only `audit_log` with actor, tenant, action, target, result, IP, UA |
| Backups | Local encrypted archive + restore drill; off-site in Phase 10 |

---

## 8. Environments

| Env | Purpose | Database | Notes |
|---|---|---|---|
| dev | Local development | SQLite file | `dev.ps1` sets `PATH`, starts both apps |
| test | Automated tests | In-memory/temp SQLite or per-test file | Isolated per test, no shared state |
| prod | Not built yet | PostgreSQL | Requires Phase 10 readiness + owner approval |

---

## 9. Key trade-offs (recorded honestly)

| Decision | Benefit | Cost / risk |
|---|---|---|
| SQLite first | Zero install, fast start, real transactions | No RLS, single-writer concurrency; must migrate before multi-user |
| Two languages (TS + Python) | Best UI + best finance libraries | More setup; contract drift risk → mitigated by generated OpenAPI types later |
| No UI kit | Exact brand control, no bloat | More hand-built components; slower Phase 6 |
| Server-side sessions | Revocable, simple to reason about | Needs a session table and cleanup job |
| Python 3.14 | Already installed | Some packages may lag; fallback to a 3.12 portable build if wheels are unavailable |

---

## 10. What is deliberately NOT designed yet

Ledger schema details beyond the outline, tax/GST rules, offline sync protocol, AI grounding pipeline, and reporting query engine. Designing them now would be speculation; they get their own architecture pass in their phase, with tests.

---

## 11. Phase 1 build order (approved scope only)

1. `dev.ps1` bootstrap + repo skeleton (no features).
2. Config + secrets loader + error envelope + correlation IDs.
3. Database models, migrations, tenant/user/membership/role/session/audit tables.
4. Auth: register, login, logout, session rotation, password policy.
5. Authorisation: permission catalog, role matrix, dependency guards.
6. Tenant context plumbing + cross-tenant tests.
7. Audit logging.
8. Backup script + **restore-verify** script + drill.
9. Test suite + evidence in `docs/TEST_RESULTS.md`.
10. Stop, report, wait for owner approval before Phase 2 (accounting core).
