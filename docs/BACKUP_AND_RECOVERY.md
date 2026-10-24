# ARTHIVIO — Backup and Recovery

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-10-24 |
| Status | Draft for owner approval |
| Phase 1 target | Local, verified, restorable backups |
| Phase 10 target | Off-site + immutable copy, monitored |

> Core rule: **a backup that has never been restored is not a backup — it is a hope.** Every claim in this document requires a recorded restore drill before it counts.

---

## 1. Objectives

| Objective | Phase 1 target | Production target |
|---|---|---|
| RPO (max acceptable data loss) | ≤ 24 h | ≤ 1 h |
| RTO (max acceptable downtime) | ≤ 30 min | ≤ 4 h |
| Retention (daily) | 14 days | 35 days |
| Retention (monthly) | — | 12 months |
| Restore drill frequency | Before Phase 1 sign-off, then monthly | Weekly automated + monthly manual |
| Backup verification | Every backup hashed; weekly restore into clean DB | Every backup verified |

Phase 1 runs on one machine. That means **no true disaster recovery** yet — a disk failure loses both primary and backup. This is stated plainly rather than hidden.

---

## 2. What gets backed up

| Item | Included | Notes |
|---|---|---|
| SQLite database | ✅ | Consistent snapshot via `VACUUM INTO` |
| Uploaded documents (later) | ✅ (Phase 3+) | Stored outside DB |
| Configuration | ✅ `.env.example` only | **Never** back up `.env` with live secrets into the same archive |
| Audit log | ✅ | Part of DB; also exported as append-only JSONL |
| Code | ✅ via git | Remote push is a separate, owner-approved action |
| Secrets | ❌ | Backed up separately in a password manager, never in the data archive |

---

## 3. Backup procedure (Phase 1)

1. Acquire a DB lock/short transaction and run:
   ```sql
   VACUUM INTO 'backups/arthivio-YYYYMMDD-HHMMSS.db';
   ```
2. Compute SHA-256 and size; write a row to `backup_run` (`status=running` → `success`).
3. Copy to a second local folder with restricted permissions (`backups/` is git-ignored).
4. Write a manifest: timestamp, engine version, schema revision (`alembic current`), row counts per table, checksum.
5. Log completion; on any error, mark `failed` and raise an alert entry.

Scheduling: Windows Task Scheduler daily at a fixed hour (documented in `scripts/`), or manual run for Phase 1. A scheduled job that silently fails is worse than none, so failure must write `status=failed` **and** a visible log line.

---

## 4. Encryption and access

| Control | Phase 1 | Production |
|---|---|---|
| Archive encryption | 7-Zip AES-256 with a passphrase held outside the repo | Managed KMS / age keys |
| Access | OS user only; folder ACL restricted | Least-privilege service account |
| Key storage | Owner's password manager | KMS + rotation policy |
| Transport | Local only | TLS to off-site store |

Encryption key loss = permanent data loss. Two independent copies of the key, stored separately, is the minimum.

---

## 5. Restore procedure (the part that matters)

**Drill script: `scripts/restore-verify.ps1` (to be written in Phase 1).**

1. Pick the backup to test (default: newest).
2. Restore into a **fresh, empty path** — never over the live database.
3. Open read-only; run `PRAGMA integrity_check` (SQLite) / `pg_restore --list` sanity (PostgreSQL).
4. Compare against the manifest:
   - row count per table,
   - SHA-256 of a deterministic export of critical columns,
   - `alembic current` matches the app's expected revision.
5. Assert tenant boundaries: spot-check that tenant A rows do not appear under tenant B.
6. Record the outcome in `backup_run.restore_test_result` and in `docs/TEST_RESULTS.md`.
7. Delete the restored copy (or keep briefly under quarantine) and log the deletion.

**Pass criteria:** all table counts match, checksum matches, integrity check clean, tenant spot-check clean, schema revision correct.

**Fail behaviour:** restore marked failed, alert raised, **no claim of recoverability**. A failed drill is a release blocker.

---

## 6. Restore drill log (template)

| Date | Backup file | Size | SHA-256 (first 12) | Rows match | Checksum | Integrity | Tenant check | Result | Duration |
|---|---|---|---|---|---|---|---|---|---|
| _(to be filled by the first Phase 1 drill)_ | | | | | | | | | |

Until this table has at least one **PASS** row, ARTHIVIO has **no verified recovery capability**.

---

## 7. Failure handling and alerts

| Failure | Detection | Action |
|---|---|---|
| Backup job did not run | Missing `backup_run` row for the day | Alert on next app start / dashboard banner |
| Backup failed mid-way | `status=failed`, error recorded | Retry once, then alert |
| Checksum mismatch | Manifest comparison | Treat as corrupt; do not delete older good backups |
| Disk full | Write error | Alert; retention cleanup must not delete the last good backup |
| Restore fails | Drill result `failed` | Release blocker; investigate before any migration |

---

## 8. Retention, deletion, legal hold

- Daily backups: 14 days (Phase 1), then delete oldest-first.
- Never delete the last known-good verified backup, even if older than retention.
- Owner-requested deletion of a tenant's data must consider legal retention obligations and backups: document the policy before any deletion feature is built.
- Legal hold: if requested, suspend deletion of the affected tenant's backups and record the hold.

---

## 9. Disaster scenarios

| Scenario | Phase 1 reality | Mitigation |
|---|---|---|
| Corrupted DB file | Restore from last verified backup | Integrity check on restore |
| Accidental mass edit | Restore into a side copy, extract correct rows | Audit log to identify scope |
| Disk failure | **Both copies lost** | Phase 10: off-site copy |
| Ransomware | Local copies may be encrypted | Phase 10: immutable/off-site copy |
| Machine theft | Encryption at rest | Full-disk encryption + archive encryption |
| Migration bug | Restore pre-migration backup | Mandatory pre-migration backup |

---

## 10. Phase 10 requirements (not satisfied today)

- [ ] Backup stored in a **separate location** from primary (a second folder on the same disk does not count).
- [ ] Immutable or object-lock retention.
- [ ] Automated restore verification on a schedule, with results recorded.
- [ ] Measured RTO/RPO from real drills.
- [ ] Restoration tested by someone other than the author of the backup script.
- [ ] Monitoring + alerting outside the app process.

---

## 11. Honest current status

| Capability | Status |
|---|---|
| Backup script | ❌ Not written |
| Restore-verify script | ❌ Not written |
| First successful backup | ❌ Not executed |
| First successful restore drill | ❌ Not executed |
| Off-site protection | ❌ None |
| Encryption | ❌ Not implemented |

**Therefore: ARTHIVIO currently has no recovery capability at all.** This table is the honest baseline, and it must be updated with evidence — not promises — as Phase 1 progresses.
