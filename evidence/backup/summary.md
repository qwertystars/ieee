# T20: Backup/Restore Scripts + Verification Test

## Date: 2026-07-28

## Files Created
- `scripts/backup.sh` (100 lines) — pg_dump + mc mirror to `backups/<timestamp>/`
- `scripts/restore.sh` (119 lines) — restore DB + MinIO from backup path
- `backend/tests/test_backup_restore.py` (310 lines, 244 pure LOC) — 4 tests, all passing
- `evidence/backup/test-results.txt` — pytest output
- `evidence/backup/test-results-final.txt` — final pytest run
- `evidence/backup/make-backup-output.txt` — `make backup` output
- `evidence/backup/make-restore-output.txt` — `make restore BACKUP=<path>` output

## Files Modified
- `Makefile` — added `backup` and `restore` targets

## Test Results
```
tests/test_backup_restore.py::test_backup_creates_artifacts PASSED       [ 25%]
tests/test_backup_restore.py::test_restore_preserves_row_counts PASSED   [ 50%]
tests/test_backup_restore.py::test_restore_preserves_observation_fields PASSED   [ 75%]
tests/test_backup_restore.py::test_restore_preserves_minio_files PASSED  [100%]
4 passed in 20.27s
```

## Verification
- `make backup` produces `backups/<timestamp>/db.sql.gz` + `minio/` + `manifest.txt`
- `make restore BACKUP=<path>` restores DB (alembic version 0005) + MinIO files
- Row counts match after round-trip: observations=812, incidents=1, alerts=1, tasks=3
- Sample observation fields match after restore
- MinIO test file restored after delete + restore
- Test database (`resqnet_backup_test`) created and dropped per run — production DB untouched

## Key Decisions
1. Used `docker compose exec -T db pg_dump` (not host pg_dump) because host pg_dump is v15 but Docker PG is v16
2. Used `docker compose exec -T minio mc mirror` + `docker compose cp` because `mc` is not installed on host
3. Test uses a separate `resqnet_backup_test` database — production `disaster` DB is never modified
4. Backup directory structure: `backups/<timestamp>/{db.sql.gz, minio/, manifest.txt}`
5. Restore drops schema first for clean restore, then pipes dump into psql
