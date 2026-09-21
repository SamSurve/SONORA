"""Automated Tests for Job Manager, Concurrency, Cancellation, Retries, and Persistence."""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.core.constants import AudioFormat, JobStatus
from app.core.security import SSRFSecurityException
from app.db.database import get_db
from app.db.repository import get_tracks_for_job, init_db
from app.engine.ytdlp_engine import DownloadCancelledException, ProgressEvent
from app.services.job_manager import JobManager, StorageLimitExceededException


@pytest.fixture
def test_job_mgr(temp_db_path: Path) -> JobManager:
    """Creates an isolated JobManager instance connected to a temporary SQLite database."""
    with patch.object(settings, "DB_PATH", temp_db_path):
        with get_db() as conn:
            init_db(conn)
        mgr = JobManager(max_workers=2)
        yield mgr
        mgr.shutdown(wait=False)


class TestJobManagerLifecycle:
    """Tests for job submission, execution lifecycle, and database persistence."""

    @patch("app.services.job_manager.execute_download")
    def test_single_track_job_success(
        self, mock_exec: MagicMock, test_job_mgr: JobManager, tmp_path: Path
    ) -> None:
        def fake_download(job_id, url, temp_dir, **kwargs):
            # Simulate yt-dlp writing a track into temp_dir
            audio_file = temp_dir / "Single Track.mp3"
            audio_file.write_bytes(b"dummy mp3 data")
            return {"title": "Single Track", "uploader": "Auralis Lab"}

        mock_exec.side_effect = fake_download

        events_received: list[ProgressEvent] = []

        def on_progress(evt: ProgressEvent) -> None:
            events_received.append(evt)

        # Mock public DNS resolution to pass SSRF guard
        mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
        with patch("socket.getaddrinfo", return_value=mock_addr):
            job_id = test_job_mgr.submit_job(
                url="https://music.youtube.com/watch?v=single1",
                target_format=AudioFormat.MP3_320,
            )

        test_job_mgr.subscribe(job_id, on_progress)

        # Wait for worker completion
        context = test_job_mgr._active_jobs.get(job_id)
        if context and context.future:
            context.future.result(timeout=5)

        # Verify DB record
        job_record = test_job_mgr.get_job_info(job_id)

        assert job_record is not None
        assert job_record["status"] == JobStatus.COMPLETED.value
        assert job_record["progress"] == 100
        assert job_record["file_path"] is not None
        assert Path(job_record["file_path"]).exists()

        # Verify scratchpad was cleaned up
        temp_dir = settings.TEMP_DIR / job_id
        assert not temp_dir.exists(), "Scratchpad should be deleted upon completion"

        # Verify progress events were dispatched
        assert len(events_received) >= 1
        assert any(evt.stage == "completed" for evt in events_received)

    @patch("app.services.job_manager.execute_download")
    def test_playlist_job_with_zip_packaging(
        self, mock_exec: MagicMock, test_job_mgr: JobManager
    ) -> None:
        def fake_playlist_download(job_id, url, temp_dir, **kwargs):
            # Simulate multiple tracks
            (temp_dir / "001 - Track One.mp3").write_bytes(b"track 1 data")
            (temp_dir / "002 - Track Two.mp3").write_bytes(b"track 2 data")
            return {"title": "Synthwave Pack", "uploader": "Auralis Music"}

        mock_exec.side_effect = fake_playlist_download

        mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
        with patch("socket.getaddrinfo", return_value=mock_addr):
            job_id = test_job_mgr.submit_job(
                url="https://music.youtube.com/playlist?list=PLsynth",
                target_format=AudioFormat.MP3_320,
                is_playlist=True,
            )

        context = test_job_mgr._active_jobs.get(job_id)
        if context and context.future:
            context.future.result(timeout=5)

        job_record = test_job_mgr.get_job_info(job_id)
        assert job_record is not None
        assert job_record["status"] == JobStatus.COMPLETED.value
        assert job_record["file_path"].endswith(".zip")
        assert Path(job_record["file_path"]).exists()

        # Check track records in DB
        with get_db() as conn:
            tracks = get_tracks_for_job(conn, job_id)
            assert len(tracks) == 2
            assert tracks[0]["track_title"] == "Track One"
            assert tracks[1]["track_title"] == "Track Two"


class TestCancellationAndRetries:
    """Tests for cooperative cancellation tokens and retry backoff."""

    @patch("app.services.job_manager.execute_download")
    def test_cooperative_cancellation(self, mock_exec: MagicMock, test_job_mgr: JobManager) -> None:
        started_event = threading.Event()

        def slow_download(job_id, url, temp_dir, cancel_event, **kwargs):
            started_event.set()
            # Wait until cancellation flag is signaled
            while not cancel_event.is_set():
                time.sleep(0.05)
            raise DownloadCancelledException("Cancelled in mock")

        mock_exec.side_effect = slow_download

        mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
        with patch("socket.getaddrinfo", return_value=mock_addr):
            job_id = test_job_mgr.submit_job("https://music.youtube.com/watch?v=cancel_me")

        # Wait for worker to enter execution
        started_event.wait(timeout=3)

        # Cancel the job
        cancelled = test_job_mgr.cancel_job(job_id)
        assert cancelled is True

        # Wait for worker thread to finish
        context = test_job_mgr._active_jobs.get(job_id)
        if context and context.future:
            context.future.result(timeout=5)

        job_record = test_job_mgr.get_job_info(job_id)
        assert job_record is not None
        assert job_record["status"] == JobStatus.CANCELLED.value

    @patch("app.services.job_manager.execute_download")
    def test_cancellation_during_exception_remains_cancelled(
        self, mock_exec: MagicMock, test_job_mgr: JobManager
    ) -> None:
        started_event = threading.Event()

        def aborting_download(job_id, url, temp_dir, cancel_event, **kwargs):
            started_event.set()
            while not cancel_event.is_set():
                time.sleep(0.05)
            # Simulate generic network error thrown when socket is interrupted
            raise ConnectionResetError("Socket reset during abort")

        mock_exec.side_effect = aborting_download

        mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
        with patch("socket.getaddrinfo", return_value=mock_addr):
            job_id = test_job_mgr.submit_job("https://music.youtube.com/watch?v=abort_me")

        started_event.wait(timeout=3)
        test_job_mgr.cancel_job(job_id)

        # Wait for worker thread to terminate
        time.sleep(0.5)

        job_record = test_job_mgr.get_job_info(job_id)
        assert job_record is not None
        assert job_record["status"] == JobStatus.CANCELLED.value
        assert "Job was cancelled by user." in (job_record["error_message"] or "")

    @patch("app.services.job_manager.execute_download")
    @patch("app.services.job_manager.time.sleep", return_value=None)  # Instant backoff in test
    def test_retry_on_transient_error(
        self, mock_sleep: MagicMock, mock_exec: MagicMock, test_job_mgr: JobManager
    ) -> None:
        attempts = [0]

        def flaky_download(job_id, url, temp_dir, **kwargs):
            attempts[0] += 1
            if attempts[0] == 1:
                raise ConnectionResetError("Transient connection drop")
            # Success on attempt 2
            (temp_dir / "recovered.mp3").write_bytes(b"recovered data")
            return {"title": "Recovered Song"}

        mock_exec.side_effect = flaky_download

        mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
        with patch("socket.getaddrinfo", return_value=mock_addr):
            job_id = test_job_mgr.submit_job("https://music.youtube.com/watch?v=retry_me")

        context = test_job_mgr._active_jobs.get(job_id)
        if context and context.future:
            context.future.result(timeout=5)

        assert attempts[0] == 2
        job_record = test_job_mgr.get_job_info(job_id)
        assert job_record["status"] == JobStatus.COMPLETED.value

    @patch("app.services.job_manager.execute_download")
    @patch("app.services.job_manager.time.sleep", return_value=None)
    def test_exhausted_retries_marks_failed(
        self, mock_sleep: MagicMock, mock_exec: MagicMock, test_job_mgr: JobManager
    ) -> None:
        mock_exec.side_effect = RuntimeError("Persistent upstream failure")

        mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
        with patch("socket.getaddrinfo", return_value=mock_addr):
            job_id = test_job_mgr.submit_job("https://music.youtube.com/watch?v=fail_me")

        context = test_job_mgr._active_jobs.get(job_id)
        if context and context.future:
            context.future.result(timeout=5)

        job_record = test_job_mgr.get_job_info(job_id)
        assert job_record["status"] == JobStatus.FAILED.value
        assert "Persistent upstream failure" in job_record["error_message"]


class TestSecurityAndConcurrencyEnforcement:
    """Tests security gate enforcement and worker pool limits."""

    def test_ssrf_url_rejected_at_submission(self, test_job_mgr: JobManager) -> None:
        # Loopback URL must be rejected immediately by validate_url before queuing
        with pytest.raises(SSRFSecurityException):
            test_job_mgr.submit_job("http://127.0.0.1:8000/malicious")

    @patch("app.services.job_manager.check_disk_space", return_value=False)
    def test_insufficient_disk_space_rejected(
        self, mock_disk: MagicMock, test_job_mgr: JobManager
    ) -> None:
        mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
        with patch("socket.getaddrinfo", return_value=mock_addr):
            with pytest.raises(StorageLimitExceededException):
                test_job_mgr.submit_job("https://music.youtube.com/watch?v=disk_full")
