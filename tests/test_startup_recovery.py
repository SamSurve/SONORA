"""Tests for Startup Reconciliation and Zombie Job Recovery.

Verifies that jobs left in active non-terminal states across server restarts
are safely transitioned to FAILED status and their scratchpads purged.
"""

from pathlib import Path

from app.core.config import settings
from app.db.database import get_db_read, get_db_write
from app.db.repository import create_job, get_job, update_job_status
from app.services.job_manager import JobManager


def test_reconcile_startup_zombie_jobs(tmp_path: Path, monkeypatch) -> None:
    """Verifies that non-terminal jobs left in SQLite are recovered on boot."""
    db_file = tmp_path / "test_zombie.db"
    monkeypatch.setattr(settings, "DB_PATH", db_file)
    monkeypatch.setattr(settings, "TEMP_DIR", tmp_path / "temp")
    monkeypatch.setattr(settings, "COMPLETED_DIR", tmp_path / "completed")

    # Create active non-terminal jobs in database
    with get_db_write(db_file) as conn:
        create_job(conn, "zombie_1", "https://music.youtube.com/watch?v=z1", "mp3", "320")
        update_job_status(conn, "zombie_1", "downloading", progress=45)

        create_job(conn, "zombie_2", "https://music.youtube.com/watch?v=z2", "mp3", "320")
        update_job_status(conn, "zombie_2", "converting", progress=90)

        create_job(conn, "completed_1", "https://music.youtube.com/watch?v=c1", "mp3", "320")
        update_job_status(conn, "completed_1", "completed", progress=100)

    # Create scratchpad directories for the zombie job
    z1_temp = settings.TEMP_DIR / "zombie_1"
    z1_temp.mkdir(parents=True, exist_ok=True)
    (z1_temp / "partial.opus").write_bytes(b"ephemeral_data")

    # Instantiate JobManager (triggers reconcile_startup_jobs)
    job_mgr = JobManager(max_workers=2)

    try:
        with get_db_read(db_file) as conn:
            z1_data = get_job(conn, "zombie_1")
            z2_data = get_job(conn, "zombie_2")
            c1_data = get_job(conn, "completed_1")

            assert z1_data["status"] == "failed"
            assert "interrupted by server restart" in z1_data["error_message"].lower()

            assert z2_data["status"] == "failed"
            assert "interrupted by server restart" in z2_data["error_message"].lower()

            # Completed jobs remain intact
            assert c1_data["status"] == "completed"

        # Scratchpad directory should be cleaned up
        assert not z1_temp.exists()
    finally:
        job_mgr.shutdown(wait=False)
