"""Automated Tests for Storage Lifecycle, Job Isolation, and Janitor Cleanup."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.db.database import get_db
from app.db.repository import create_job, get_job, init_db
from app.engine.janitor import (
    JanitorDaemon,
    check_disk_space,
    cleanup_job_completed_dir,
    cleanup_job_temp_dir,
    get_job_completed_dir,
    get_job_temp_dir,
    run_janitor_cleanup,
)


class TestJobStorageIsolation:
    """Tests for job workspace isolation."""

    def test_job_workspace_directories_are_isolated(self) -> None:
        dir_a = get_job_temp_dir("job_aaa")
        dir_b = get_job_temp_dir("job_bbb")

        assert dir_a != dir_b
        assert dir_a.name == "job_aaa"
        assert dir_b.name == "job_bbb"

        # Write to A
        file_a = dir_a / "temp.opus"
        file_a.write_bytes(b"data A")

        # Verify B does not see file from A
        assert not (dir_b / "temp.opus").exists()

        # Clean up
        cleanup_job_temp_dir("job_aaa")
        cleanup_job_temp_dir("job_bbb")
        assert not dir_a.exists()
        assert not dir_b.exists()


class TestJanitorCleanupLifecycle:
    """Tests for TTL expiration and automated storage garbage collection."""

    def test_cleanup_expired_jobs_in_database(self, temp_db_path: Path) -> None:
        # Patch settings DB_PATH to use our isolated temp DB
        with patch.object(settings, "DB_PATH", temp_db_path):
            with get_db() as conn:
                init_db(conn)

                # Job 1: Expired 10 minutes ago
                expired_time = datetime.now(UTC) - timedelta(minutes=10)
                create_job(
                    conn,
                    job_id="job_expired",
                    url="https://music.youtube.com/watch?v=exp",
                    target_format="mp3_320",
                    quality="320",
                    expires_at=expired_time,
                )
                # Set status to completed so it qualifies for expiry
                conn.execute("UPDATE jobs SET status = 'completed' WHERE id = 'job_expired'")

                # Job 2: Still active (expires in 50 minutes)
                active_time = datetime.now(UTC) + timedelta(minutes=50)
                create_job(
                    conn,
                    job_id="job_active",
                    url="https://music.youtube.com/watch?v=act",
                    target_format="mp3_320",
                    quality="320",
                    expires_at=active_time,
                )
                conn.execute("UPDATE jobs SET status = 'completed' WHERE id = 'job_active'")

            # Create completed folders for both jobs
            comp_expired = get_job_completed_dir("job_expired")
            (comp_expired / "track.mp3").write_bytes(b"expired track data")

            comp_active = get_job_completed_dir("job_active")
            (comp_active / "track.mp3").write_bytes(b"active track data")

            # Run janitor cleanup
            purged = run_janitor_cleanup()
            assert purged >= 1

            # Verify expired job folder was deleted
            assert not comp_expired.exists()

            # Verify active job folder is preserved
            assert comp_active.exists()

            # Verify database status
            with get_db() as conn:
                expired_record = get_job(conn, "job_expired")
                assert expired_record is not None
                assert expired_record["status"] == "expired"

                active_record = get_job(conn, "job_active")
                assert active_record is not None
                assert active_record["status"] == "completed"

            # Clean up active job test dir
            cleanup_job_completed_dir("job_active")

    def test_active_jobs_protected_from_janitor_cleanup(self, temp_db_path: Path) -> None:
        with patch.object(settings, "DB_PATH", temp_db_path):
            with get_db() as conn:
                init_db(conn)
                # Job is past expiration, but actively downloading
                past_time = datetime.now(UTC) - timedelta(minutes=60)
                create_job(
                    conn,
                    job_id="job_downloading_now",
                    url="https://music.youtube.com/watch?v=now",
                    target_format="mp3_320",
                    quality="320",
                    expires_at=past_time,
                )
                conn.execute(
                    "UPDATE jobs SET status = 'downloading' WHERE id = 'job_downloading_now'"
                )

            # Temp scratch directory for downloading job
            temp_dir = get_job_temp_dir("job_downloading_now")
            (temp_dir / "chunk.part").write_bytes(b"downloading chunk")

            # Run janitor
            run_janitor_cleanup()

            # Active job temp folder MUST NOT be purged
            assert temp_dir.exists()
            assert (temp_dir / "chunk.part").exists()

            # Clean up
            cleanup_job_temp_dir("job_downloading_now")

    @patch("shutil.disk_usage")
    def test_check_disk_space_threshold(self, mock_usage: MagicMock) -> None:
        # Mock 500 MB free (< 2048 MB threshold)
        mock_usage.return_value = MagicMock(free=500 * 1024 * 1024)
        assert check_disk_space(min_free_mb=2048) is False

        # Mock 5000 MB free (>= 2048 MB threshold)
        mock_usage.return_value = MagicMock(free=5000 * 1024 * 1024)
        assert check_disk_space(min_free_mb=2048) is True

    def test_janitor_daemon_start_and_stop(self) -> None:
        daemon = JanitorDaemon(interval_seconds=1)
        daemon.start()
        assert daemon.is_alive()
        daemon.stop()
        daemon.join(timeout=3)
        assert not daemon.is_alive()
