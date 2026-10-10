from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "scripts" / "backup.sh"
RESTORE = ROOT / "scripts" / "restore.sh"
FIXTURE = ROOT / "tests" / "fixtures" / "backup-restore"


class BackupRestoreContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="task10-"))
        self.key = self.temp_dir / "key"
        self.key.write_text("test-only-key-material\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def run_command(self, command: list[str], **extra: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(extra)
        return subprocess.run(command, cwd=ROOT, env=environment, text=True, capture_output=True)

    def create_backup(self, source: Path = FIXTURE) -> Path:
        result = self.run_command(
            ["bash", str(BACKUP)],
            BACKUP_ROOT=str(self.temp_dir / "backups"),
            BACKUP_FIXTURE_DIR=str(source),
            BACKUP_ENCRYPTION_KEY_FILE=str(self.key),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return next((self.temp_dir / "backups").glob("20*"))

    def restore(self, backup: Path, **extra: str) -> subprocess.CompletedProcess[str]:
        values = {
            "BACKUP_ENCRYPTION_KEY_FILE": str(self.key),
            "RESTORE_TARGET_DIR": str(self.temp_dir / "clean-room"),
            "RESTORE_SUCCESS_MARKER": str(self.temp_dir / "restore.success"),
            "RESTORE_REPORT": str(self.temp_dir / "restore.report.json"),
        }
        values.update(extra)
        return self.run_command(["bash", str(RESTORE), str(backup)], **values)

    def test_clean_room_restore_verifies_all_coverage(self) -> None:
        backup = self.create_backup()
        result = self.restore(backup, RPO_TARGET_S="60", RTO_TARGET_S="900")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.temp_dir / "restore.success").exists())
        report = json.loads((self.temp_dir / "restore.report.json").read_text())
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(all(report["checks"].values()))
        self.assertEqual(report["checks"]["live_signing_keys"], "external")

    def test_checksum_mismatch_has_no_success_marker(self) -> None:
        backup = self.create_backup()
        with (backup / "backup.enc").open("ab") as archive:
            archive.write(b"corruption")
        result = self.restore(backup)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.temp_dir / "restore.success").exists())
        self.assertIn("checksum", result.stderr.lower())

    def test_missing_offset_metadata_fails_at_backup(self) -> None:
        source = self.temp_dir / "missing-offset"
        shutil.copytree(FIXTURE, source)
        (source / "metadata" / "queue_offsets.json").unlink()
        result = self.run_command(
            ["bash", str(BACKUP)],
            BACKUP_ROOT=str(self.temp_dir / "backups"),
            BACKUP_FIXTURE_DIR=str(source),
            BACKUP_ENCRYPTION_KEY_FILE=str(self.key),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("metadata", result.stderr.lower())
        self.assertFalse(list((self.temp_dir / "backups").glob("20*/backup.success")))

    def test_missing_object_metadata_fails_at_backup(self) -> None:
        source = self.temp_dir / "missing-object"
        shutil.copytree(FIXTURE, source)
        (source / "metadata" / "object_metadata.json").unlink()
        result = self.run_command(
            ["bash", str(BACKUP)],
            BACKUP_ROOT=str(self.temp_dir / "backups"),
            BACKUP_FIXTURE_DIR=str(source),
            BACKUP_ENCRYPTION_KEY_FILE=str(self.key),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("metadata", result.stderr.lower())

    def test_rpo_threshold_failure_has_no_success_marker(self) -> None:
        backup = self.create_backup()
        result = self.restore(backup, RPO_TARGET_S="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RPO", result.stderr)
        self.assertFalse((self.temp_dir / "restore.success").exists())

    def test_rto_threshold_failure_has_no_success_marker(self) -> None:
        backup = self.create_backup()
        result = self.restore(backup, RTO_TARGET_S="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RTO", result.stderr)
        self.assertFalse((self.temp_dir / "restore.success").exists())


if __name__ == "__main__":
    unittest.main()
