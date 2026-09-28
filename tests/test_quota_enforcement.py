"""Tests for Safety Quota and Rate Limiting Enforcement.

Verifies MAX_PLAYLIST_ITEMS enforcement and client_id rate limiting in JobManager.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.job_manager import (
    JobManager,
    PlaylistQuotaExceededException,
    RateLimitExceededException,
    RateLimiter,
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
        job_mgr.shutdown(wait=True)


def test_client_id_rate_limiting_enforcement() -> None:
    """Verifies that rapid submissions from a single client_id breach rate limits."""
    job_mgr = JobManager(max_workers=2)
    client = "192.168.1.50"

    mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
    try:
        with (
            patch("socket.getaddrinfo", return_value=mock_addr),
            patch.object(job_mgr._executor, "submit", return_value=MagicMock()),
        ):
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
        job_mgr.shutdown(wait=True)


def test_rate_limiter_stale_history_pruning() -> None:
    """Verifies MED-01: Inactive client history keys are pruned upon window expiration."""
    limiter = RateLimiter(max_requests=5, window_seconds=10)

    # Seed client with timestamp older than window
    limiter._history["stale_client_1"] = [100.0]
    limiter._history["active_client"] = [time.time()]

    # Explicit prune
    limiter.prune(force=True)

    assert "stale_client_1" not in limiter._history
    assert "active_client" in limiter._history


def test_rate_limiter_capacity_bounding() -> None:
    """Verifies MED-01: RateLimiter bounds total tracked clients to max_tracked_clients."""
    limiter = RateLimiter(max_requests=5, window_seconds=60, max_tracked_clients=10)

    for i in range(25):
        limiter.is_allowed(f"client_{i}")

    assert len(limiter._history) <= 10
