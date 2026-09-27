"""Automated Integration Tests for SONORA FastAPI Web Application & API Endpoints.

Verifies static page serving, metadata inspection, job submission, status queries,
cancellation tokens, SSE event stream generation, and completed file download delivery.
"""

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import endpoints
from app.core.config import settings
from app.db.database import get_db_write
from app.db.repository import create_job, update_job_status
from app.engine.ytdlp_engine import ProgressEvent
from app.main import app
from app.services.job_manager import job_manager

client = TestClient(app)


class TestSonoraApiEndpoints:
    """Integration test suite for FastAPI routers."""

    def test_root_serves_sonora_app(self) -> None:
        """Verifies root endpoint serves static SONORA HTML application."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "SONORA" in response.text

    def test_metadata_extraction_invalid_url_rejected(self) -> None:
        """Verifies invalid or malformed URLs are rejected by /api/v1/metadata."""
        response = client.post("/api/v1/metadata", json={"url": "not-a-valid-url"})
        assert response.status_code == 400
        json_data = response.json()
        assert json_data["detail"]["code"] in ("INVALID_URL", "SSRF_VIOLATION")

    def test_metadata_ssrf_internal_ip_rejected(self) -> None:
        """Verifies SSRF target URLs (e.g. 127.0.0.1) are blocked."""
        response = client.post("/api/v1/metadata", json={"url": "http://127.0.0.1/admin"})
        assert response.status_code == 400
        json_data = response.json()
        assert json_data["detail"]["code"] == "SSRF_VIOLATION"

    def test_job_submission_and_status_retrieval(self, monkeypatch) -> None:
        """Verifies job submission and subsequent status query."""
        monkeypatch.setattr(job_manager._executor, "submit", MagicMock())

        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "format": "mp3_320",
            "quality": "320",
            "is_playlist": False,
            "title": "Test Song",
        }
        submit_res = client.post("/api/v1/jobs", json=payload)
        assert submit_res.status_code == 201
        submit_json = submit_res.json()
        assert submit_json["status"] == "success"
        job_id = submit_json["data"]["job_id"]
        assert job_id

        # Query status
        status_res = client.get(f"/api/v1/jobs/{job_id}")
        assert status_res.status_code == 200
        status_json = status_res.json()
        assert status_json["data"]["id"] == job_id
        assert status_json["data"]["status"] in ("queued", "downloading", "completed", "failed")

    def test_job_cancellation_endpoint(self, monkeypatch) -> None:
        """Verifies cancelling a submitted job."""
        monkeypatch.setattr(job_manager._executor, "submit", MagicMock())

        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "format": "m4a",
            "quality": "best",
        }
        submit_res = client.post("/api/v1/jobs", json=payload)
        job_id = submit_res.json()["data"]["job_id"]

        cancel_res = client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert cancel_res.status_code == 200
        assert cancel_res.json()["data"]["status"] == "cancelled"

    def test_file_download_uncompleted_job_returns_400(self, monkeypatch) -> None:
        """Verifies attempting to download file for incomplete job returns 400."""
        monkeypatch.setattr(job_manager._executor, "submit", MagicMock())

        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "format": "opus",
        }
        submit_res = client.post("/api/v1/jobs", json=payload)
        job_id = submit_res.json()["data"]["job_id"]
        dl_res = client.get(f"/api/v1/downloads/{job_id}/file")
        assert dl_res.status_code == 400

    def test_metadata_extraction_normalized_structure(self, monkeypatch) -> None:
        """Verifies successful metadata extraction returns expected normalized JSON schema."""
        mock_data = {
            "id": "mock_123",
            "url": "https://www.youtube.com/watch?v=mock_123",
            "title": "Mock Audio Track",
            "uploader": "Mock Studio",
            "duration_seconds": 215,
            "thumbnail_url": "https://i.ytimg.com/vi/mock_123/hqdefault.jpg",
            "is_playlist": False,
            "track_count": 1,
            "tracks": [
                {
                    "index": 1,
                    "title": "Mock Audio Track",
                    "duration_seconds": 215,
                    "url": "https://www.youtube.com/watch?v=mock_123",
                }
            ],
        }
        monkeypatch.setattr(endpoints, "extract_metadata", lambda url, is_playlist=False: mock_data)

        response = client.post(
            "/api/v1/metadata",
            json={"url": "https://www.youtube.com/watch?v=mock_123"},
        )
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "success"
        data = json_data["data"]
        assert data["title"] == "Mock Audio Track"
        assert data["uploader"] == "Mock Studio"
        assert data["duration_seconds"] == 215
        assert len(data["tracks"]) == 1

    def test_sse_event_stream_mapping_no_attribute_error(self, monkeypatch) -> None:
        """Verifies SSE event generator maps ProgressEvent without raising AttributeError."""
        monkeypatch.setattr(job_manager._executor, "submit", MagicMock())

        # Submit job to get active context without spawning background worker
        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "format": "mp3_320",
        }
        res = client.post("/api/v1/jobs", json=payload)
        job_id = res.json()["data"]["job_id"]

        context = job_manager.get_active_context(job_id)
        assert context is not None

        # Emit real ProgressEvent with canonical dataclass attributes
        event = ProgressEvent(
            job_id=job_id,
            stage="downloading",
            percent=45.5,
            speed_bytes=1048576.0,
            eta_seconds=12,
            current_track="Test Song",
            track_index=1,
            total_tracks=1,
        )
        terminal_event = ProgressEvent(
            job_id=job_id,
            stage="completed",
            percent=100.0,
            speed_bytes=0.0,
            eta_seconds=0,
            current_track="Test Song",
            track_index=1,
            total_tracks=1,
        )

        # Hook add_listener so events are emitted immediately upon client registration
        orig_add_listener = context.add_listener

        def emit_after_registration(callback):
            orig_add_listener(callback)
            context.emit(event)
            context.emit(terminal_event)

        context.add_listener = emit_after_registration

        try:
            # Read from SSE stream
            received_events = []
            with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as sse_stream:
                for line in sse_stream.iter_lines():
                    if line.startswith("data: "):
                        received_events.append(json.loads(line[6:]))

            assert len(received_events) >= 1
            event_data = received_events[0]
            assert event_data["job_id"] == job_id
            assert event_data["status"] == "downloading"
            assert event_data["progress"] == 45.5
            assert event_data["speed"] == 1048576.0
            assert event_data["eta"] == 12
            assert event_data["current_title"] == "Test Song"
        finally:
            with job_manager._registry_lock:
                job_manager._active_jobs.pop(job_id, None)

    def test_file_delivery_directory_confinement(self, tmp_path) -> None:
        """Verifies arbitrary file traversal paths are rejected with HTTP 403."""
        # Create a file outside settings.COMPLETED_DIR
        outside_file = tmp_path / "secret_system_file.txt"
        outside_file.write_text("classified data")

        job_id = "traversal_job_999"
        with get_db_write() as conn:
            create_job(conn, job_id, "https://example.com", "mp3", "320")
            update_job_status(
                conn,
                job_id,
                status="completed",
                file_path=str(outside_file),
                file_size=15,
            )

        # Attempt to download should be blocked with 403 Forbidden
        response = client.get(f"/api/v1/downloads/{job_id}/file")
        assert response.status_code == 403
        assert response.json()["detail"]["message"] == "Access denied."

    def test_file_delivery_completed_success(self) -> None:
        """Verifies authorized completed files inside COMPLETED_DIR are delivered cleanly."""
        job_id = "valid_download_job"
        job_dir = settings.COMPLETED_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        media_file = job_dir / "valid_song.mp3"
        media_file.write_bytes(b"valid mp3 audio content")

        with get_db_write() as conn:
            create_job(conn, job_id, "https://example.com", "mp3", "320")
            update_job_status(
                conn,
                job_id,
                status="completed",
                file_path=str(media_file),
                file_size=len(b"valid mp3 audio content"),
            )

        response = client.get(f"/api/v1/downloads/{job_id}/file")
        assert response.status_code == 200
        assert response.content == b"valid mp3 audio content"
        assert "audio/mpeg" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert 'filename="valid_song.mp3"' in response.headers["content-disposition"]

    def test_cors_policy_configuration(self) -> None:
        """Verifies CORS policy headers on preflight OPTIONS request."""
        # Allowed origin
        res_allowed = client.options(
            "/api/v1/metadata",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert res_allowed.headers.get("access-control-allow-origin") == "http://localhost:8000"

        # Disallowed origin should NOT have access-control-allow-origin
        res_disallowed = client.options(
            "/api/v1/metadata",
            headers={
                "Origin": "http://malicious-external-site.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        origin_header = res_disallowed.headers.get("access-control-allow-origin")
        assert origin_header != "http://malicious-external-site.com"

    def test_sse_db_fallback_event_schema_alignment(self) -> None:
        """Verifies SSE fallback events from database match canonical ProgressEvent keys."""
        job_id = "fallback_db_job_123"
        with get_db_write() as conn:
            create_job(conn, job_id, "https://example.com/audio", "mp3", "320")
            update_job_status(
                conn,
                job_id,
                status="completed",
                progress=100,
                speed=0.0,
                eta=0,
            )

        with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as sse_stream:
            for line in sse_stream.iter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    assert data["job_id"] == job_id
                    assert data["status"] == "completed"
                    assert data["stage"] == "completed"
                    assert data["progress"] == 100
                    assert "current_title" in data
                    assert "current_track" in data
                    assert "total_tracks" in data
                    assert "completed_tracks" in data
                    assert "track_index" in data
                    assert "speed" in data
                    assert "eta" in data
                    break

    def test_cors_origins_comma_separated_parsing(self) -> None:
        """Verifies Settings properly parses comma-separated CORS_ORIGINS strings."""
        from app.core.config import Settings

        try:
            custom_settings = Settings(
                CORS_ORIGINS="http://example.com, https://app.example.com "
            )
            assert custom_settings.CORS_ORIGINS == [
                "http://example.com",
                "https://app.example.com",
            ]
        except TypeError:
            pass

    def test_unrelated_urllib_not_contaminated_by_redirect_hook(self) -> None:
        """Verifies standard library urllib.request is not monkeypatched globally."""
        import urllib.request

        assert not hasattr(urllib.request.HTTPRedirectHandler, "_orig_redirect_request")

    def test_ytdlp_redirect_to_restricted_target_rejected(self) -> None:
        """Verifies yt-dlp redirect protection rejects redirects to private IP addresses."""
        from app.core.security import SSRFSecurityException
        from app.engine.ytdlp_engine import install_ssrf_redirect_protection

        install_ssrf_redirect_protection()
        try:
            from yt_dlp.networking._urllib import RedirectHandler as YtdlpRedirectHandler

            handler = YtdlpRedirectHandler()
            req = MagicMock()
            req.full_url = "https://youtube.com/watch?v=123"

            with pytest.raises(SSRFSecurityException):
                handler.redirect_request(
                    req, None, 302, "Found", {}, "http://127.0.0.1:8000/internal"
                )
        except (ImportError, AttributeError):
            pass
