"""Automated Tests for SONORA Download Profiles (Phase 5 / Feature 1).

Covers profile taxonomy, yt-dlp option builders, database schema persistence,
job execution pipelines (including Raw Video .mp4 and Audiophile .flac),
API endpoint validation, and file delivery MIME mappings.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.constants import PROFILE_TAXONOMY, AudioFormat, DownloadProfile
from app.db.database import get_db, get_db_read
from app.db.repository import create_job, get_job, init_db
from app.engine.archive_packager import MEDIA_EXTENSIONS, create_playlist_zip
from app.engine.ytdlp_engine import build_ydl_options
from app.main import app
from app.services.job_manager import JobManager, job_manager

client = TestClient(app)


class TestDownloadProfileTaxonomy:
    """Verifies profile definitions and taxonomy specifications."""

    def test_all_expected_profiles_exist(self) -> None:
        """Verifies the four required download profiles exist in the enum."""
        assert DownloadProfile.AUDIOPHILE.value == "audiophile"
        assert DownloadProfile.STANDARD.value == "standard"
        assert DownloadProfile.SPACE_SAVER.value == "space_saver"
        assert DownloadProfile.RAW_VIDEO.value == "raw_video"

    def test_profile_taxonomy_semantics(self) -> None:
        """Verifies technical semantics defined for each profile."""
        audiophile = PROFILE_TAXONOMY[DownloadProfile.AUDIOPHILE]
        assert audiophile.extension == "flac"
        assert not audiophile.is_video
        assert audiophile.audio_format == AudioFormat.FLAC

        standard = PROFILE_TAXONOMY[DownloadProfile.STANDARD]
        assert standard.extension == "mp3"
        assert not standard.is_video
        assert standard.bitrate_kbps == "320"

        space_saver = PROFILE_TAXONOMY[DownloadProfile.SPACE_SAVER]
        assert space_saver.extension == "m4a"
        assert not space_saver.is_video
        assert space_saver.bitrate_kbps == "128"

        raw_video = PROFILE_TAXONOMY[DownloadProfile.RAW_VIDEO]
        assert raw_video.extension == "mp4"
        assert raw_video.is_video


class TestYtdlpEngineProfiles:
    """Verifies yt-dlp options generation for each profile."""

    def test_audiophile_flac_options(self, tmp_path: Path) -> None:
        """Verifies audiophile profile generates FLAC extraction options."""
        opts = build_ydl_options(
            job_id="test_flac",
            temp_dir=tmp_path,
            profile=DownloadProfile.AUDIOPHILE,
        )
        assert opts["format"] == "bestaudio/best"
        postprocessors = opts.get("postprocessors", [])
        extract_pp = [pp for pp in postprocessors if pp.get("key") == "FFmpegExtractAudio"]
        assert len(extract_pp) == 1
        assert extract_pp[0]["preferredcodec"] == "flac"
        assert "merge_output_format" not in opts

    def test_standard_mp3_options(self, tmp_path: Path) -> None:
        """Verifies standard profile generates MP3 320 kbps options."""
        opts = build_ydl_options(
            job_id="test_std",
            temp_dir=tmp_path,
            profile=DownloadProfile.STANDARD,
        )
        assert opts["format"] == "bestaudio/best"
        postprocessors = opts.get("postprocessors", [])
        extract_pp = [pp for pp in postprocessors if pp.get("key") == "FFmpegExtractAudio"]
        assert len(extract_pp) == 1
        assert extract_pp[0]["preferredcodec"] == "mp3"
        assert extract_pp[0]["preferredquality"] == "320"

    def test_space_saver_m4a_options(self, tmp_path: Path) -> None:
        """Verifies space saver profile generates M4A 128 kbps options."""
        opts = build_ydl_options(
            job_id="test_saver",
            temp_dir=tmp_path,
            profile=DownloadProfile.SPACE_SAVER,
        )
        assert "bestaudio[ext=m4a]" in opts["format"]
        postprocessors = opts.get("postprocessors", [])
        extract_pp = [pp for pp in postprocessors if pp.get("key") == "FFmpegExtractAudio"]
        assert len(extract_pp) == 1
        assert extract_pp[0]["preferredcodec"] == "m4a"
        assert extract_pp[0]["preferredquality"] == "128"

    def test_raw_video_mp4_options(self, tmp_path: Path) -> None:
        """Verifies raw video profile merges to MP4 and omits audio extraction."""
        opts = build_ydl_options(
            job_id="test_video",
            temp_dir=tmp_path,
            profile=DownloadProfile.RAW_VIDEO,
        )
        assert "bestvideo[ext=mp4]+bestaudio[ext=m4a]" in opts["format"]
        assert opts.get("merge_output_format") == "mp4"
        postprocessors = opts.get("postprocessors", [])
        extract_pp = [pp for pp in postprocessors if pp.get("key") == "FFmpegExtractAudio"]
        assert len(extract_pp) == 0

    def test_backward_compatibility_without_profile(self, tmp_path: Path) -> None:
        """Verifies omitting profile preserves legacy target_format behavior."""
        opts = build_ydl_options(
            job_id="test_legacy",
            temp_dir=tmp_path,
            target_format="opus",
        )
        postprocessors = opts.get("postprocessors", [])
        extract_pp = [pp for pp in postprocessors if pp.get("key") == "FFmpegExtractAudio"]
        assert len(extract_pp) == 1
        assert extract_pp[0]["preferredcodec"] == "opus"


class TestDatabaseRepositoryProfile:
    """Verifies SQLite profile schema column, migration, and persistence."""

    def test_create_and_get_job_persists_profile(self, temp_db_path: Path) -> None:
        """Verifies creating a job with custom profile stores it in SQLite."""
        with patch.object(settings, "DB_PATH", temp_db_path):
            with get_db() as conn:
                init_db(conn)
                job = create_job(
                    conn=conn,
                    job_id="prof_job_1",
                    url="https://example.com/audio",
                    target_format="flac",
                    quality="lossless",
                    profile="audiophile",
                )
                assert job["profile"] == "audiophile"

                fetched = get_job(conn, "prof_job_1")
                assert fetched is not None
                assert fetched["profile"] == "audiophile"

    def test_default_profile_is_standard(self, temp_db_path: Path) -> None:
        """Verifies creating a job without explicit profile defaults to standard."""
        with patch.object(settings, "DB_PATH", temp_db_path):
            with get_db() as conn:
                init_db(conn)
                job = create_job(
                    conn=conn,
                    job_id="prof_job_2",
                    url="https://example.com/audio",
                    target_format="mp3_320",
                    quality="320",
                )
                assert job["profile"] == "standard"


class TestArchivePackagerMediaExtensions:
    """Verifies MEDIA_EXTENSIONS and packaging support video formats."""

    def test_media_extensions_includes_video_formats(self) -> None:
        """Verifies MEDIA_EXTENSIONS includes mp4, mkv, webm alongside audio."""
        assert ".mp4" in MEDIA_EXTENSIONS
        assert ".mkv" in MEDIA_EXTENSIONS
        assert ".webm" in MEDIA_EXTENSIONS
        assert ".mp3" in MEDIA_EXTENSIONS
        assert ".flac" in MEDIA_EXTENSIONS

    def test_create_playlist_zip_with_mp4_files(self, tmp_path: Path) -> None:
        """Verifies create_playlist_zip packages .mp4 files into a valid ZIP."""
        completed_dir = tmp_path / "test_completed_dir"
        completed_dir.mkdir(parents=True, exist_ok=True)
        (completed_dir / "001 - Video Track.mp4").write_bytes(b"dummy mp4 video content")
        (completed_dir / "002 - Video Track 2.mp4").write_bytes(b"dummy mp4 video 2 content")

        zip_path, total_size = create_playlist_zip(
            job_id="test_pack_video",
            job_completed_dir=completed_dir,
            playlist_title="Video Collection",
        )
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        assert total_size > 0


class TestApiDownloadProfiles:
    """Verifies API endpoints for profile listing, submission, and delivery."""

    def test_list_profiles_endpoint(self) -> None:
        """Verifies GET /api/v1/profiles returns 4 profiles with valid taxonomy."""
        response = client.get("/api/v1/profiles")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        profile_list = data["data"]
        assert len(profile_list) == 4
        ids = {p["id"] for p in profile_list}
        assert ids == {"audiophile", "standard", "space_saver", "raw_video"}

    def test_submit_job_with_audiophile_profile(self, monkeypatch) -> None:
        """Verifies submitting a job with profile='audiophile'."""
        monkeypatch.setattr(job_manager._executor, "submit", MagicMock())

        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "profile": "audiophile",
        }
        res = client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 201
        job_id = res.json()["data"]["job_id"]

        status_res = client.get(f"/api/v1/jobs/{job_id}")
        assert status_res.status_code == 200
        job_data = status_res.json()["data"]
        assert job_data["profile"] == "audiophile"
        assert job_data["format"] == "flac"

    def test_submit_job_with_raw_video_profile(self, monkeypatch) -> None:
        """Verifies submitting a job with profile='raw_video'."""
        monkeypatch.setattr(job_manager._executor, "submit", MagicMock())

        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "profile": "raw_video",
        }
        res = client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 201
        job_id = res.json()["data"]["job_id"]

        status_res = client.get(f"/api/v1/jobs/{job_id}")
        assert status_res.status_code == 200
        job_data = status_res.json()["data"]
        assert job_data["profile"] == "raw_video"
        assert job_data["format"] == "mp4"

    def test_submit_job_with_space_saver_profile(self, monkeypatch) -> None:
        """Verifies submitting a job with profile='space_saver'."""
        monkeypatch.setattr(job_manager._executor, "submit", MagicMock())

        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "profile": "space_saver",
        }
        res = client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 201
        job_id = res.json()["data"]["job_id"]

        status_res = client.get(f"/api/v1/jobs/{job_id}")
        assert status_res.status_code == 200
        job_data = status_res.json()["data"]
        assert job_data["profile"] == "space_saver"
        assert job_data["format"] == "m4a"
        assert job_data["quality"] == "128"

    def test_submit_job_default_profile_is_standard(self, monkeypatch) -> None:
        """Verifies omitting profile defaults to standard MP3 320 kbps."""
        monkeypatch.setattr(job_manager._executor, "submit", MagicMock())

        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
        }
        res = client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 201
        job_id = res.json()["data"]["job_id"]

        status_res = client.get(f"/api/v1/jobs/{job_id}")
        assert status_res.status_code == 200
        job_data = status_res.json()["data"]
        assert job_data["profile"] == "standard"
        assert job_data["format"] == "mp3_320"

    def test_submit_job_invalid_profile_returns_422(self) -> None:
        """Verifies submitting an invalid profile string returns 422 Unprocessable Entity."""
        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "profile": "non_existent_profile",
        }
        res = client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 422
        errors = res.json().get("detail", [])
        assert any("profile" in str(err) for err in errors)


class TestJobManagerPipelineProfiles:
    """Verifies end-to-end pipeline execution with different media profiles."""

    @patch("app.services.job_manager.execute_download")
    def test_pipeline_executes_raw_video_profile(
        self, mock_exec: MagicMock, temp_db_path: Path, tmp_path: Path
    ) -> None:
        """Verifies pipeline successfully processes, tags, and delivers .mp4 video files."""
        def fake_download(job_id, url, temp_dir, **kwargs):
            video_file = temp_dir / "Sample Video.mp4"
            video_file.write_bytes(b"dummy mp4 video bytes")
            return {"title": "Sample Video", "uploader": "Video Creator"}

        mock_exec.side_effect = fake_download

        with patch.object(settings, "DB_PATH", temp_db_path):
            with get_db() as conn:
                init_db(conn)
            mgr = JobManager(max_workers=1)

            mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
            with patch("socket.getaddrinfo", return_value=mock_addr):
                job_id = mgr.submit_job(
                    url="https://www.youtube.com/watch?v=video123",
                    profile=DownloadProfile.RAW_VIDEO,
                )

            # Wait for completion
            deadline = 5.0
            completed = False
            start = time.time()
            while time.time() - start < deadline:
                with get_db_read() as conn:
                    job = get_job(conn, job_id)
                if job and job["status"] in ("completed", "failed"):
                    completed = True
                    break
                time.sleep(0.05)

            mgr.shutdown(wait=True)
            assert completed, "Job did not finish in time"
            assert job["status"] == "completed"
            assert job["profile"] == "raw_video"
            assert job["file_path"].endswith(".mp4")

    @patch("app.services.job_manager.execute_download")
    def test_pipeline_executes_audiophile_flac_profile(
        self, mock_exec: MagicMock, temp_db_path: Path, tmp_path: Path
    ) -> None:
        """Verifies pipeline successfully processes, tags, and delivers .flac files."""
        def fake_download(job_id, url, temp_dir, **kwargs):
            flac_file = temp_dir / "Acoustic Symphony.flac"
            flac_file.write_bytes(b"dummy flac audio bytes")
            return {"title": "Acoustic Symphony", "uploader": "Orchestra"}

        mock_exec.side_effect = fake_download

        with patch.object(settings, "DB_PATH", temp_db_path):
            with get_db() as conn:
                init_db(conn)
            mgr = JobManager(max_workers=1)

            mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
            with patch("socket.getaddrinfo", return_value=mock_addr):
                job_id = mgr.submit_job(
                    url="https://www.youtube.com/watch?v=flac123",
                    profile=DownloadProfile.AUDIOPHILE,
                )

            # Wait for completion
            deadline = 5.0
            completed = False
            start = time.time()
            while time.time() - start < deadline:
                with get_db_read() as conn:
                    job = get_job(conn, job_id)
                if job and job["status"] in ("completed", "failed"):
                    completed = True
                    break
                time.sleep(0.05)

            mgr.shutdown(wait=True)
            assert completed, "Job did not finish in time"
            assert job["status"] == "completed"
            assert job["profile"] == "audiophile"
            assert job["file_path"].endswith(".flac")
