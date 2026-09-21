"""Tests for Safety Quota and Rate Limiting Enforcement.

Verifies MAX_PLAYLIST_ITEMS enforcement and client_id rate limiting in JobManager.
"""

from unittest.mock import patch

import pytest

from app.services.job_manager import (
    JobManager,
    PlaylistQuotaExceededException,
    RateLimitExceededException,
)


def test_playlist_max_items_quota_enforcement() -> None:
    """Verifies that playlist requests exceeding MAX_PLAYLIST_ITEMS are rejected."""
    job_mgr = JobManager(max_workers=2)

    # 105 items exceeds default limit of 100
    excessive_indices = list(range(1, 106))

    try:
        with pytest.raises(PlaylistQuotaExceededException) as exc_info:
            job_mgr.submit_job(
                url="https://music.youtube.com/playlist?list=PLtest",
                is_playlist=True,
                selected_indices=excessive_indices,
            )
        assert "exceed maximum allowed limit" in str(exc_info.value)
    finally:
        job_mgr.shutdown(wait=False)


def test_client_id_rate_limiting_enforcement() -> None:
    """Verifies that rapid submissions from a single client_id breach rate limits."""
    job_mgr = JobManager(max_workers=2)
    client = "192.168.1.50"

    mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
    try:
        with patch("socket.getaddrinfo", return_value=mock_addr):
            # Submit 10 allowed requests
            for _ in range(10):
                job_id = job_mgr.submit_job(
                    url="https://music.youtube.com/watch?v=valid_track",
                    client_id=client,
                )
                assert job_id is not None

            # 11th request should breach rate limit
            with pytest.raises(RateLimitExceededException) as exc_info:
                job_mgr.submit_job(
                    url="https://music.youtube.com/watch?v=valid_track",
                    client_id=client,
                )
            assert f"Rate limit exceeded for client '{client}'" in str(exc_info.value)

            # A different client identity should still be allowed
            other_client = "192.168.1.51"
            other_job_id = job_mgr.submit_job(
                url="https://music.youtube.com/watch?v=valid_track",
                client_id=other_client,
            )
            assert other_job_id is not None
    finally:
        job_mgr.shutdown(wait=False)
