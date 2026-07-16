# Backup and Restore Runbook

## Scope

PostgreSQL and object storage are authoritative. Redis is transient. Neo4j is rebuildable projection. Target policy: daily encrypted off-host backup, 14 daily copies, 8 weekly copies, and quarterly restore drill. Operators must choose RPO/RTO based on deployment needs.

## Backup

1. Verify stack health and free disk space at least twice estimated backup size.
2. Run `BACKUP_ROOT=/secure/path scripts/backup.sh`.
3. Verify `SHA256SUMS` and `manifest.txt`.
4. Encrypt backup with organization-approved tooling.
5. Copy encrypted artifact off-host. Never include `.env`.
6. Record timestamp, size, checksum, operator, Git SHA, image references, and Alembic revision.
7. Alert if newest successful off-host backup exceeds 26 hours.

External S3 deployments must use provider-native versioning/export instead of local RustFS volume copy.

## Restore

Restore is destructive. Use isolated recovery environment first.

1. Record incident state and stop writes.
2. Select verified backup matching desired recovery point.
3. Confirm checksum and decrypt into protected local path.
4. Ensure `.env` targets intended environment.
5. Run `RESTORE_CONFIRM=RESTORE scripts/restore.sh backups/<timestamp>`.
6. Verify `/api/ready`, project authentication, object reads, upload, graph extraction, evidence, and migrations.
7. Reconcile or rebuild Neo4j projection from authoritative stores.
8. Compare row/object counts and run smoke evaluation.
9. Reopen traffic only after owner approval.

## Abort and Escalate

Abort if checksum fails, target environment is ambiguous, backup is incomplete, schema compatibility is unknown, or available disk is insufficient. Preserve failed restore logs. Escalate to database/platform owner. Never repeatedly rerun destructive restore against same production database without diagnosis.
