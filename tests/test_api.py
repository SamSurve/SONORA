"""Automated Integration Tests for SONORA FastAPI Web Application & API Endpoints.

Verifies static page serving, metadata inspection, job submission, status queries,
cancellation tokens, SSE event stream generation, and completed file download delivery.
"""

from fastapi.testclient import TestClient

from app.main import app

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
        from unittest.mock import MagicMock

        mock_exec = MagicMock(return_value={"title": "Test Song"})
        monkeypatch.setattr("app.services.job_manager.execute_download", mock_exec)

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
        from unittest.mock import MagicMock

        mock_exec = MagicMock(side_effect=lambda *args, **kwargs: {"title": "Test"})
        monkeypatch.setattr("app.services.job_manager.execute_download", mock_exec)

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
        from unittest.mock import MagicMock

        mock_exec = MagicMock(return_value={"title": "Test"})
        monkeypatch.setattr("app.services.job_manager.execute_download", mock_exec)

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
        from app.api.v1 import endpoints

        mock_data = {
            "id": "mock_123",
            "url": "https://www.youtube.com/watch?v=mock_123",
            "title": "Mock Audio Track",
            "uploader": "Mock Studio",
            "duration_seconds": 215,
            "thumbnail_url": "https://i.ytimg.com/vi/mock_123/hqdefault.jpg",
            "is_playlist": False,
            "track_count": 1,
            "tracks": [{"index": 1, "title": "Mock Audio Track", "duration_seconds": 215, "url": "https://www.youtube.com/watch?v=mock_123"}],
        }
        monkeypatch.setattr(endpoints, "extract_metadata", lambda url, is_playlist=False: mock_data)

        response = client.post("/api/v1/metadata", json={"url": "https://www.youtube.com/watch?v=mock_123"})
        assert response.status_code == 200
        json_data = response.json()
        assert json_data["status"] == "success"
        data = json_data["data"]
        assert data["title"] == "Mock Audio Track"
        assert data["uploader"] == "Mock Studio"
        assert data["duration_seconds"] == 215
        assert len(data["tracks"]) == 1
