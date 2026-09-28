"""Automated Test Suite for SONORA Persistent Library & History.

Tests SQLite repository pagination, filtering, search query aggregation,
API endpoints (/api/v1/jobs, /api/v1/jobs/{id}, /api/v1/jobs/{id}/retry),
file availability security verification, and frontend template contracts.
"""

import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.constants import DownloadProfile, JobStatus
from app.db.database import get_db_read, get_db_write
from app.db.repository import (
    add_track_to_job,
    create_job,
    list_jobs_paginated,
    update_job_status,
)
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provides a FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client


def test_repository_list_jobs_paginated() -> None:
    """Verifies repository pagination, filtering, searching, and track count aggregation."""
    job_ids = [f"test-repo-{uuid.uuid4().hex[:8]}" for _ in range(5)]

    with get_db_write() as conn:
        # Create 5 jobs with distinct attributes
        create_job(
            conn,
            job_id=job_ids[0],
            url="https://youtube.com/watch?v=libtest0",
            target_format="mp3_320",
            quality="320",
            title="Alpha Acoustic Track",
            profile=DownloadProfile.AUDIOPHILE.value,
        )
        update_job_status(conn, job_ids[0], status=JobStatus.COMPLETED.value)

        create_job(
            conn,
            job_id=job_ids[1],
            url="https://youtube.com/watch?v=libtest1",
            target_format="opus_160",
            quality="160",
            title="Beta Ambient Soundscape",
            profile=DownloadProfile.STANDARD.value,
        )
        update_job_status(conn, job_ids[1], status=JobStatus.FAILED.value)

        create_job(
            conn,
            job_id=job_ids[2],
            url="https://soundcloud.com/artist/gamma-track",
            target_format="flac_auto",
            quality="auto",
            title="Gamma Synthwave",
            profile=DownloadProfile.AUDIOPHILE.value,
            is_playlist=True,
        )
        # Add 3 tracks to job 2
        add_track_to_job(conn, job_ids[2], 1, "Track One", 180)
        add_track_to_job(conn, job_ids[2], 2, "Track Two", 200)
        add_track_to_job(conn, job_ids[2], 3, "Track Three", 220)
        update_job_status(conn, job_ids[2], status=JobStatus.COMPLETED.value)

        create_job(
            conn,
            job_id=job_ids[3],
            url="https://bandcamp.com/delta-album",
            target_format="mp3_128",
            quality="128",
            title="Delta Low-Fi Session",
            profile=DownloadProfile.SPACE_SAVER.value,
        )
        update_job_status(conn, job_ids[3], status=JobStatus.CANCELLED.value)

        create_job(
            conn,
            job_id=job_ids[4],
            url="https://youtube.com/watch?v=libtest4",
            target_format="mp4_auto",
            quality="auto",
            title="Epsilon Live Stream",
            profile=DownloadProfile.RAW_VIDEO.value,
        )
        update_job_status(conn, job_ids[4], status=JobStatus.QUEUED.value)

    with get_db_read() as conn:
        # 1. Total pagination limit/offset
        page1, total = list_jobs_paginated(conn, limit=2, offset=0)
        assert len(page1) == 2
        assert total >= 5

        # 2. Filter by status
        completed_jobs, c_total = list_jobs_paginated(
            conn, limit=10, status=JobStatus.COMPLETED.value
        )
        assert all(j["status"] == JobStatus.COMPLETED.value for j in completed_jobs)
        assert c_total >= 2

        # 3. Filter by profile
        audio_jobs, a_total = list_jobs_paginated(
            conn, limit=10, profile=DownloadProfile.AUDIOPHILE.value
        )
        assert all(j["profile"] == DownloadProfile.AUDIOPHILE.value for j in audio_jobs)
        assert a_total >= 2

        # 4. Search query by title
        search_jobs, s_total = list_jobs_paginated(
            conn, limit=10, search_query="Synthwave"
        )
        assert s_total >= 1
        assert any("Synthwave" in (j["title"] or "") for j in search_jobs)

        # 5. Search query by URL
        url_search_jobs, u_total = list_jobs_paginated(
            conn, limit=10, search_query="bandcamp.com"
        )
        assert u_total >= 1
        assert any("bandcamp.com" in j["url"] for j in url_search_jobs)

        # 6. Verify track count aggregation on playlist job
        job_gamma = next((j for j in search_jobs if j["id"] == job_ids[2]), None)
        assert job_gamma is not None
        assert job_gamma["track_count"] == 3


def test_api_list_jobs_endpoint(client: TestClient) -> None:
    """Tests GET /api/v1/jobs endpoint pagination and search filters."""
    job_id = f"test-api-{uuid.uuid4().hex[:8]}"

    with get_db_write() as conn:
        create_job(
            conn,
            job_id=job_id,
            url="https://youtube.com/watch?v=api_list_test",
            target_format="mp3_320",
            quality="320",
            title="Unique List Test Media",
            profile=DownloadProfile.STANDARD.value,
        )
        update_job_status(conn, job_id, status=JobStatus.COMPLETED.value)

    res = client.get("/api/v1/jobs?page=1&page_size=10&q=Unique+List+Test")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "success"
    items = data["data"]["items"]
    assert len(items) >= 1
    found = next((j for j in items if j["id"] == job_id), None)
    assert found is not None
    assert found["title"] == "Unique List Test Media"
    assert "file_path" not in found  # Ensure server internal paths are never leaked
    assert "file_available" in found


def test_api_job_status_and_file_availability(client: TestClient, tmp_path: Path) -> None:
    """Tests GET /api/v1/jobs/{job_id} and storage file availability detection."""
    job_id = f"test-avail-{uuid.uuid4().hex[:8]}"
    test_audio_file = settings.COMPLETED_DIR / f"{job_id}.mp3"
    test_audio_file.write_bytes(b"dummy audio data")

    try:
        with get_db_write() as conn:
            create_job(
                conn,
                job_id=job_id,
                url="https://youtube.com/watch?v=avail_test",
                target_format="mp3_320",
                quality="320",
                title="Availability Verification Track",
                profile=DownloadProfile.STANDARD.value,
            )
            update_job_status(
                conn,
                job_id,
                status=JobStatus.COMPLETED.value,
                file_path=str(test_audio_file),
                file_size=len(b"dummy audio data"),
            )

        # 1. Inspect when file exists
        res = client.get(f"/api/v1/jobs/{job_id}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["file_available"] is True
        assert data["download_url"] == f"/api/v1/downloads/{job_id}/file"
        assert "file_path" not in data

        # 2. Inspect when file is purged
        test_audio_file.unlink()
        res = client.get(f"/api/v1/jobs/{job_id}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["file_available"] is False
        assert data["download_url"] is None

    finally:
        if test_audio_file.exists():
            test_audio_file.unlink()


def test_api_retry_job_execution(client: TestClient) -> None:
    """Tests POST /api/v1/jobs/{job_id}/retry endpoint functionality and guardrails."""
    job_id = f"test-retry-{uuid.uuid4().hex[:8]}"

    with get_db_write() as conn:
        create_job(
            conn,
            job_id=job_id,
            url="https://youtube.com/watch?v=retry_test_url",
            target_format="flac_auto",
            quality="auto",
            title="Retry Source Media",
            profile=DownloadProfile.AUDIOPHILE.value,
        )
        update_job_status(conn, job_id, status=JobStatus.FAILED.value)

    # 1. Non-existent job retry -> 404
    non_existent = client.post("/api/v1/jobs/fake-id-12345/retry")
    assert non_existent.status_code == 404

    # 2. Retry active job -> 400 rejection
    active_job_id = f"test-active-{uuid.uuid4().hex[:8]}"
    with get_db_write() as conn:
        create_job(
            conn,
            job_id=active_job_id,
            url="https://youtube.com/watch?v=active_test",
            target_format="mp3_320",
            quality="320",
        )
        update_job_status(conn, active_job_id, status=JobStatus.DOWNLOADING.value)

    active_res = client.post(f"/api/v1/jobs/{active_job_id}/retry")
    assert active_res.status_code == 400

    # 3. Successful retry of failed job
    with patch("app.services.job_manager.job_manager.worker_pool.submit") as mock_submit:
        res = client.post(f"/api/v1/jobs/{job_id}/retry")
        assert res.status_code == 200
        new_job_data = res.json()["data"]
        assert new_job_data["url"] == "https://youtube.com/watch?v=retry_test_url"
        assert new_job_data["profile"] == DownloadProfile.AUDIOPHILE.value
        assert new_job_data["format"] == "flac_auto"
        assert new_job_data["id"] != job_id
        assert mock_submit.called


def test_frontend_library_elements(client: TestClient) -> None:
    """Verifies frontend HTML contains all expected Library elements."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Verify navigation & section
    assert 'id="nav-library"' in html
    assert 'id="library"' in html
    assert 'id="library-search"' in html
    assert 'id="library-status-filter"' in html
    assert 'id="library-profile-filter"' in html
    assert 'id="library-refresh-btn"' in html
    assert 'id="library-table"' in html
    assert 'id="library-tbody"' in html
    assert 'id="library-pagination"' in html
    assert 'id="job-details-modal"' in html
