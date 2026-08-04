"""Integration test -- backup/restore round-trip verification (T20).

Verifies the backup and restore scripts produce a faithful round-trip:
  1. Create a separate test database (does NOT touch the production DB)
  2. Run migrations + seed known test data (incident, observation, alert, task)
  3. Upload a test file to the MinIO "models" bucket
  4. Run scripts/backup.sh -> backups/<timestamp>/
  5. Record row counts + a sample observation's fields
  6. Drop the test DB schema + delete the MinIO test file
  7. Run scripts/restore.sh -> restores from the backup
  8. Assert row counts match and the sample observation is identical
  9. Assert the MinIO test file is restored
 10. Clean up the test database and backup artifacts

The test connects directly to the Docker PostgreSQL (localhost:5433) and
MinIO (localhost:9000), bypassing the app's DATABASE_URL so the production
disaster database is never modified.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest

# ── Docker stack connection constants ────────────────────────────────────────
PG_HOST = "localhost"
PG_PORT = 5433
PG_USER = "disaster"
PG_PASSWORD = "disaster"
PG_ADMIN_DB = "disaster"          # connect here to CREATE/DROP the test DB
TEST_DB = "resqnet_backup_test"

MINIO_HOST = "localhost"
MINIO_PORT = 9000
MINIO_USER = "minio"
MINIO_PASSWORD = "minio123"
MINIO_BUCKET = "models"
TEST_MINIO_OBJECT = "backup_restore_test_file.bin"

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
BACKUPS = ROOT / "backups"

# Tables to verify in the round-trip
COUNT_TABLES = ("observations", "incidents", "alerts", "operational_tasks")

# Fixed timestamps and IDs for deterministic test data
NOW = 1753708800000  # 2025-07-28T12:00:00Z in epoch ms
INCIDENT_ID = "01J9BACK000000000000000001"
OBSERVATION_ID = "01J9BACK000000000000000002"
ALERT_ID = "01J9BACK000000000000000003"
TASK_ID = "01J9BACK000000000000000004"
ORG_ID = "org_backup_test"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _admin_dsn() -> str:
    return f"host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASSWORD} dbname={PG_ADMIN_DB}"


def _test_dsn() -> str:
    return f"host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASSWORD} dbname={TEST_DB}"


def _run(cmd: list[str], env: dict | None = None, check: bool = True, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, env=env, check=check, cwd=cwd)


def _docker_exec(service: str, cmd: str, check: bool = True) -> str:
    result = _run(["docker", "compose", "exec", "-T", service, "sh", "-c", cmd], check=check)
    return result.stdout


def _create_test_db() -> None:
    """Create a fresh test database in the Docker PG (idempotent)."""
    with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        conn.execute(f"CREATE DATABASE {TEST_DB} OWNER {PG_USER}")


def _drop_test_db() -> None:
    with psycopg.connect(_admin_dsn(), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")


def _run_migrations() -> None:
    """Run alembic upgrade head against the test database."""
    env = os.environ.copy()
    env["DATABASE_URL"] = f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{TEST_DB}"
    env["PYTHONPATH"] = str(ROOT / "backend")
    _run(
        [str(ROOT / "backend" / ".venv" / "bin" / "alembic"), "upgrade", "head"],
        env=env,
        cwd=str(ROOT / "backend"),
    )


def _seed_test_data() -> None:
    """Insert a known incident, observation, alert, and task."""
    with psycopg.connect(_test_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO incidents
                   (id, org_id, title, disaster_type, severity, status,
                    start_time, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (INCIDENT_ID, ORG_ID, "Backup Test Incident", "flood",
                 "moderate", "active", NOW, NOW, NOW),
            )
            cur.execute(
                """INSERT INTO observations
                   (observation_id, event_type, phenomenon, value, unit,
                    geometry, geometry_uncertainty, observed_at, valid_from,
                    received_at, source_id, source_type, collection_method,
                    source_reliability, freshness, corroboration_state,
                    quality_flags, access_policy, provenance_chain,
                    raw_data_hash, org_id, incident_id)
                   VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s,%s),4326),
                           %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (OBSERVATION_ID, "sensor_reading", "water_level", 1.75, "m",
                 72.85, 19.07, 10.0, NOW, NOW, NOW, "src_test_01", "sensor",
                 "automated", 0.95, 1.0, "unverified",
                 '{"test": true}', "internal", '{"source": "test"}',
                 "abc123hash", ORG_ID, INCIDENT_ID),
            )
            cur.execute(
                """INSERT INTO alerts
                   (id, org_id, incident_id, alert_type, title, message,
                    severity, status, created_by, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (ALERT_ID, ORG_ID, INCIDENT_ID, "flood_warning",
                 "Backup Test Alert", "Test alert for backup verification",
                 "warning", "draft", "system", NOW, NOW),
            )
            cur.execute(
                """INSERT INTO operational_tasks
                   (id, org_id, incident_id, title, status, priority,
                    created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (TASK_ID, ORG_ID, INCIDENT_ID, "Backup Test Task",
                 "pending", "medium", NOW, NOW),
            )
        conn.commit()


def _get_row_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with psycopg.connect(_test_dsn()) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for table in COUNT_TABLES:
                try:
                    cur.execute(f"SELECT count(*) FROM {table}")
                    counts[table] = cur.fetchone()[0]
                except psycopg.errors.UndefinedTable:
                    counts[table] = 0
    return counts


def _get_sample_observation() -> dict:
    with psycopg.connect(_test_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT observation_id, event_type, phenomenon, value, unit,
                          source_id, source_type, corroboration_state,
                          org_id, incident_id
                   FROM observations WHERE observation_id = %s""",
                (OBSERVATION_ID,),
            )
            row = cur.fetchone()
            return {
                "observation_id": row[0],
                "event_type": row[1],
                "phenomenon": row[2],
                "value": row[3],
                "unit": row[4],
                "source_id": row[5],
                "source_type": row[6],
                "corroboration_state": row[7],
                "org_id": row[8],
                "incident_id": row[9],
            }


def _upload_minio_test_file() -> None:
    """Upload a uniquely-named test file to the MinIO models bucket."""
    _docker_exec("minio", f"mc alias set local http://localhost:9000 {MINIO_USER} {MINIO_PASSWORD}")
    _docker_exec("minio", f"mc mb -p local/{MINIO_BUCKET} 2>/dev/null || true")
    _docker_exec("minio", f"sh -c 'echo backup-test-content > /tmp/{TEST_MINIO_OBJECT}'")
    _docker_exec("minio", f"mc cp /tmp/{TEST_MINIO_OBJECT} local/{MINIO_BUCKET}/{TEST_MINIO_OBJECT}")


def _write_metadata_dir(path: Path) -> None:
    """Write the seven files production backup.sh requires.

    The hardened envelope validates queue offsets, model/object metadata
    consistency, signing-key escrow policy, and the audit hash chain, so
    the fixtures must be self-consistent rather than empty placeholders.
    """
    import hashlib
    import json

    path.mkdir(parents=True, exist_ok=True)

    def _now_ms() -> int:
        from app.lib.time import now_ms
        return now_ms()

    test_file_bytes = b"backup-test-content\n"
    object_sha256 = hashlib.sha256(test_file_bytes).hexdigest()

    events = [
        {
            "sequence": 1,
            "prev_hash": None,
            "action": "create",
            "entity": f"raw_events:{OBSERVATION_ID}",
            "payload": {"value": 1.75},
        },
        {
            "sequence": 2,
            "prev_hash": None,
            "action": "project",
            "entity": f"evaluation_jobs:{OBSERVATION_ID}",
            "payload": {"status": "completed"},
        },
    ]
    for index, event in enumerate(events):
        if index > 0:
            event["prev_hash"] = events[0]["hash"]
        body = {key: value for key, value in event.items() if key != "hash"}
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        event["hash"] = f"sha256:{digest}"

    (path / "queue_offsets.json").write_text(json.dumps({
        "broker": "redpanda:9092",
        "consumer_group": "observations-consumer",
        "topics": [
            {"topic": "observations.normalized", "partition": 0, "offset": 42},
            {"topic": "observations.dlq", "partition": 0, "offset": 3},
        ],
    }))
    (path / "model_manifests.json").write_text(json.dumps([{
        "model_id": "test-model",
        "version": "1.0.0",
        "checksum": object_sha256,
        "artifact": {
            "r2_key": TEST_MINIO_OBJECT,
            "sha256": object_sha256,
        },
        "validation_status": "validated",
        "signed": True,
    }]))
    (path / "object_metadata.json").write_text(json.dumps([{
        "bucket": MINIO_BUCKET,
        "key": TEST_MINIO_OBJECT,
        "size": len(test_file_bytes),
        "sha256": object_sha256,
        "etag": "test-etag",
    }]))
    (path / "signing_key_escrow.json").write_text(json.dumps({
        "algorithm": "Ed25519",
        "live_keys_external": True,
        "private_keys_in_backup": False,
        "escrow_reference": "secret-manager/backup-signing-key",
        "public_key_ids": ["01J9BACKUPKEY00000000000001"],
        "policy": "restore public verification metadata only",
    }))
    (path / "audit_chain.json").write_text(json.dumps({
        "org_id": ORG_ID,
        "events": events,
        "head": {
            "last_sequence": len(events),
            "last_hash": events[-1]["hash"],
        },
    }))
    (path / "source_snapshot.json").write_text(json.dumps({
        "latest_source_event_at_ms": _now_ms(),
        "source": "test-clock",
        "checkpoint": "backup-test-001",
    }))
    (path / "row_counts.json").write_text(json.dumps({
        "raw_events": 1,
        "evaluation_jobs": 1,
        "audit_chain_heads": 1,
    }))


def _delete_minio_test_file() -> None:
    _docker_exec("minio", f"mc rm local/{MINIO_BUCKET}/{TEST_MINIO_OBJECT} 2>/dev/null || true")


def _minio_test_file_exists() -> bool:
    result = _run(
        ["docker", "compose", "exec", "-T", "minio", "sh", "-c",
         f"mc stat local/{MINIO_BUCKET}/{TEST_MINIO_OBJECT} 2>/dev/null && echo EXISTS || echo MISSING"],
        check=False,
    )
    return "EXISTS" in result.stdout


def _run_backup(encryption_key: Path, metadata_dir: Path) -> Path:
    """Run scripts/backup.sh with PG_DB=TEST_DB, return the backup directory path."""
    env = os.environ.copy()
    env["PG_DB"] = TEST_DB
    env["PG_USER"] = PG_USER
    env["BACKUP_ENCRYPTION_KEY_FILE"] = str(encryption_key)
    env["BACKUP_METADATA_DIR"] = str(metadata_dir)
    result = _run(["bash", str(SCRIPTS / "backup.sh")], env=env)
    for line in result.stdout.splitlines():
        if "BACKUP_SUCCESS" in line:
            return ROOT / line.split("path=", 1)[1].split()[0]
    raise RuntimeError(f"Could not find backup path in output:\n{result.stdout}\n{result.stderr}")


def _run_restore(backup_path: Path, encryption_key: Path) -> None:
    env = os.environ.copy()
    env["PG_DB"] = TEST_DB
    env["PG_USER"] = PG_USER
    env["BACKUP_ENCRYPTION_KEY_FILE"] = str(encryption_key)
    env["RESTORE_TARGET_DIR"] = str(backup_path / "clean-room")
    env["RESTORE_REPORT"] = str(backup_path / "restore.report.json")
    env["RESTORE_SUCCESS_MARKER"] = str(backup_path / f"restore.{_restore_serial()}.success")
    _run(["bash", str(SCRIPTS / "restore.sh"), str(backup_path)], env=env)


_RESTORE_COUNT = 0


def _restore_serial() -> int:
    global _RESTORE_COUNT
    _RESTORE_COUNT += 1
    return _RESTORE_COUNT


_RESTORE_KEY: Path | None = None


def _restore_key() -> Path:
    assert _RESTORE_KEY is not None, "restore key not set by fixture"
    return _RESTORE_KEY


# ── Test fixture ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def backup_dir(tmp_path_factory) -> Path:
    """Set up test DB, seed data, back up, and yield the backup path.

    Teardown drops the test database and removes the backup directory.
    """
    global _RESTORE_KEY
    tmp = tmp_path_factory.mktemp("backup-restore")
    encryption_key = tmp / "backup.key"
    encryption_key.write_text("test-backup-key-material")
    _RESTORE_KEY = encryption_key
    metadata_dir = tmp / "metadata"
    _write_metadata_dir(metadata_dir)
    _create_test_db()
    _run_migrations()
    _seed_test_data()
    _upload_minio_test_file()
    bdir = _run_backup(encryption_key, metadata_dir)
    yield bdir
    _drop_test_db()
    _delete_minio_test_file()
    if bdir.exists():
        shutil.rmtree(bdir, ignore_errors=True)


# ── Tests ────────────────────────────────────────────────────────────────────

def test_backup_creates_artifacts(backup_dir: Path) -> None:
    """backup.sh produces backup.enc, manifest.json, and manifest.sha256."""
    assert (backup_dir / "backup.enc").exists(), "backup.enc missing"
    assert (backup_dir / "backup.enc").stat().st_size > 0, "backup.enc is empty"
    assert (backup_dir / "manifest.json").exists(), "manifest.json missing"
    assert (backup_dir / "manifest.sha256").exists(), "manifest.sha256 missing"
    assert (backup_dir / "backup.success").exists(), "backup.success marker missing"


def test_restore_preserves_row_counts(backup_dir: Path) -> None:
    """After drop + restore, row counts match the pre-drop state."""
    before = _get_row_counts()
    assert before["observations"] >= 1, "no observations seeded"
    assert before["incidents"] >= 1
    assert before["alerts"] >= 1
    assert before["operational_tasks"] >= 1

    # Drop the schema to simulate data loss
    with psycopg.connect(_test_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.commit()
    assert _get_row_counts() == {t: 0 for t in COUNT_TABLES}, "schema not dropped"

    # Delete the MinIO test file
    _delete_minio_test_file()
    assert not _minio_test_file_exists(), "MinIO test file not deleted"

    # Restore from backup
    _run_restore(backup_dir, _restore_key())

    after = _get_row_counts()
    assert after == before, f"row count mismatch: before={before}, after={after}"


def test_restore_preserves_observation_fields(backup_dir: Path) -> None:
    """A sample observation has identical fields after restore."""
    before = _get_sample_observation()
    assert before["observation_id"] == OBSERVATION_ID

    # Drop and restore
    with psycopg.connect(_test_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.commit()
    _run_restore(backup_dir, _restore_key())

    after = _get_sample_observation()
    assert after == before, f"observation mismatch:\nbefore={before}\nafter={after}"


def test_restore_preserves_minio_files(backup_dir: Path) -> None:
    """MinIO test file is restored after delete + restore."""
    _delete_minio_test_file()
    assert not _minio_test_file_exists()
    _run_restore(backup_dir, _restore_key())
    assert _minio_test_file_exists(), "MinIO test file not restored"
