"""Tests for Metadata Extraction Service.

Verifies URL validation, pre-flight SSRF protection, and metadata output normalization.
"""

from unittest.mock import patch

import pytest

from app.core.security import SSRFSecurityException
from app.services.metadata_service import extract_metadata


def test_extract_metadata_ssrf_rejection() -> None:
    """Verifies that extract_metadata rejects internal IP and localhost targets."""
    with pytest.raises(SSRFSecurityException):
        extract_metadata("http://127.0.0.1/watch?v=internal")


def test_extract_metadata_single_track_normalization() -> None:
    """Verifies metadata normalization for a single audio track."""
    mock_info = {
        "id": "single_123",
        "title": "Auralis Track",
        "uploader": "Auralis Sound",
        "duration": 180,
        "thumbnail": "https://example.com/thumb.jpg",
        "entries": None,
    }

    mock_addr = [(2, 1, 6, "", ("142.250.190.46", 443))]
    with (
        patch("socket.getaddrinfo", return_value=mock_addr),
        patch("app.services.metadata_service.extract_media_info", return_value=mock_info),
    ):
        result = extract_metadata("https://music.youtube.com/watch?v=single_123")

    assert result["id"] == "single_123"
    assert result["title"] == "Auralis Track"
    assert result["uploader"] == "Auralis Sound"
    assert result["duration_seconds"] == 180
    assert result["is_playlist"] is False
    assert result["track_count"] == 1
    assert result["tracks"][0]["index"] == 1
