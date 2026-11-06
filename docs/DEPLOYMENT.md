# ARTHIVIO - Deployment

> **Status:** deployment blueprint for a public demo. It is not a production
> security or accounting certification. Use synthetic demo data only.

## 0. Firebase Hosting (public landing only)

| Field | Value |
|---|---|
| Firebase project | `financial-business-accounting` |
| Hosting URL | `https://financial-business-accounting.web.app` |
| Deployed files | `firebase-public/index.html` |
| Config | `firebase.json`, `.firebaserc` |

This release serves the **public ARTHIVIO landing page only**. Firebase Hosting
is a static file host; it cannot run the Python HTTP server, SQLite database,
server-side sessions or PDF/Excel writers in this repository. The landing page's
login and call-to-action links point to the current temporary demo tunnel, not
to an app running inside Firebase.

For the full online app, the Firebase project needs one of these:

- **Cloud Run + Cloud SQL/Firestore** under the same project. Cloud Run requires
  an enabled billing account; this project currently has no billing account.
- **A paid Render/Railway/VPS deployment with a persistent disk**, with Firebase
  Hosting redirecting to it. The app does not need a schema change.

Redeploy the static landing with:

```powershell
firebase deploy --only hosting --project financial-business-accounting
```

Do not describe the Firebase URL as a permanent production accounting service
until a persistent backend and a measured restore drill exist.

## 1. One-click Render demo

The repository contains `Dockerfile` and `render.yaml`. Render's free web
service gives a stable public URL without a credit card.

1. Open:
   `https://render.com/deploy?repo=https://github.com/ganeshanumerologist-ai/financial-business-account-analysis`
2. Sign in with GitHub and allow Render to read the repository.
3. Keep the Blueprint name `arthivio-demo` and the **Free** plan.
4. Click **Apply** and wait for the Docker build.
5. Open the service URL, then sign in with:
   - `owner@arthivio.test`
   - `ArthivioDemo!2026`

The container seeds the synthetic demo books only when the database is empty.
`ARTHIVIO_DEMO_AUTOLOGIN` is `0`, so the public `/demo` loopback route stays
disabled.

### Free-plan limits (important)

- The free service sleeps after inactivity; the first request can take
  30-60 seconds.
- Free Render services use an **ephemeral filesystem**. The SQLite database is
  recreated and reseeded after a restart, redeploy or sleep/wake cycle. Data
  entered during a session can disappear. This is acceptable for checking
  features, not for keeping real books.
- There is no custom domain, no persistent disk and no backup guarantee on the
  free plan.
- Do not enter real customer, bank, GST or accounting data into the public
  demo. Anyone with the URL can reach the demo owner login.

### Persistent data later

For a durable deployment, attach a Render persistent disk to a paid instance
and set `ARTHIVIO_DB` to the disk mount path (for example
`/var/data/arthivio.db`). A small VPS with a backed-up SQLite file is another
option. The application itself does not need a schema change.

`render.paid.yaml` is the ready-made paid blueprint:

| Setting | Value |
|---|---|
| Service | `arthivio` |
| Plan | `starter` (paid) |
| Disk | `arthivio-data`, 1 GB, mounted at `/var/data` |
| Database | `/var/data/arthivio.db` |
| Backups | `/var/data/backups` |
| Public demo autologin | disabled |

This keeps the existing SQLite application and avoids a database migration. The
Firebase Hosting URL can redirect to the Render URL once it is live. The disk is
not a substitute for an off-site backup: download the backup ZIPs regularly or
copy them to an external drive.

**Recommendation:** use this Render paid path for the first stable online
deployment. Cloud Run + Cloud SQL is a larger change because this app uses
SQLite, not a client/server database.

## 2. Run the container locally

```powershell
docker build -t arthivio-demo .
docker run --rm -p 8000:8000 -v arthivio-data:/app/data arthivio-demo
```

Then open `http://127.0.0.1:8000/login`.

## 3. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | HTTP port; Render sets this automatically |
| `ARTHIVIO_HOST` | `127.0.0.1` | Use `0.0.0.0` inside a container or on a trusted LAN |
| `ARTHIVIO_DB` | `data/arthivio.db` | SQLite path; `/app/data/arthivio.db` in the image |
| `ARTHIVIO_DEMO_AUTOLOGIN` | unset | Keep unset/`0` on any public host |

## 4. What the demo does and does not prove

It proves the application runs, the demo books load, the screens render and the
Excel/Power BI/insights downloads work on a clean host. It does **not** prove
production hardening: there is no independent penetration test, no monitored
backup/restore drill, no real phone/accessibility matrix, no Power BI Service
refresh/RLS and no generative AI provider.
