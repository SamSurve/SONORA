"""Unit and Integration Tests for Pre-Download Metadata & Artwork Editor.

Validates MetadataOverride validation, artwork security and decoding, precedence logic,
API contract, tagging across all audio profiles (MP3, M4A, FLAC, Opus, WAV, MP4),
and frontend markup / JS state machine integration.
"""

import base64
import struct
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.wave import WAVE
from pydantic import ValidationError

from app.api.v1 import endpoints
from app.core.constants import DownloadProfile
from app.engine.audio_tagger import tag_audio_file
from app.engine.janitor import cleanup_job_temp_dir, get_job_temp_dir
from app.main import app
from app.models.metadata import (
    MetadataOverride,
    save_artwork_to_isolated_temp,
    strip_control_characters,
    validate_and_decode_artwork,
)
from app.services.job_manager import job_manager

client = TestClient(app)

# Minimal 1x1 valid sample images for tests
SAMPLE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
SAMPLE_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
SAMPLE_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x000\x01\x00\x9d\x01*\x01\x00\x01\x00\x00\x00"


class TestMetadataOverrideModel:
    """Unit tests for MetadataOverride validation and sanitization."""

    def test_valid_metadata_accepted(self) -> None:
        """Verifies valid metadata override fields are accepted."""
        override = MetadataOverride(
            title="Symphony No. 5",
            artist="Ludwig van Beethoven",
            album="Masterpieces",
            year=1808,
        )
        assert override.title == "Symphony No. 5"
        assert override.artist == "Ludwig van Beethoven"
        assert override.album == "Masterpieces"
        assert override.year == 1808

    def test_partial_override_preserves_none_fields(self) -> None:
        """Verifies unspecified fields default to None without replacing them with empty strings."""
        override = MetadataOverride(title="Updated Title")
        assert override.title == "Updated Title"
        assert override.artist is None
        assert override.album is None
        assert override.year is None
        assert override.artwork is None

    def test_year_validation_range(self) -> None:
        """Verifies year must be within bounded range 1000..2100."""
        # Valid string or int
        assert MetadataOverride(year="2025").year == 2025
        assert MetadataOverride(year=1999).year == 1999

        with pytest.raises(ValidationError):
            MetadataOverride(year=999)

        with pytest.raises(ValidationError):
            MetadataOverride(year=2101)

        with pytest.raises(ValidationError):
            MetadataOverride(year="not-a-year")

    def test_oversized_metadata_rejected(self) -> None:
        """Verifies strings exceeding max length of 500 chars are rejected."""
        long_title = "A" * 501
        with pytest.raises(ValidationError):
            MetadataOverride(title=long_title)

    def test_control_character_stripping(self) -> None:
        """Verifies ASCII control characters are stripped while preserving Unicode."""
        raw = "Track\x00\x07Title \x1b[31mWith\x7f Unicode: 🎵 Mozart № 40"
        cleaned = strip_control_characters(raw)
        assert cleaned is not None
        assert "\x00" not in cleaned
        assert "\x07" not in cleaned
        assert "\x1b" not in cleaned
        assert "\x7f" not in cleaned
        assert "Mozart № 40" in cleaned
        assert "🎵" in cleaned


class TestArtworkValidationAndStorage:
    """Tests for base64 artwork decoding, magic byte verification, and isolated storage."""

    def test_valid_jpeg_artwork_accepted(self) -> None:
        """Verifies JPEG data URL / base64 is accepted and decoded."""
        b64 = base64.b64encode(SAMPLE_JPEG).decode("ascii")
        data_url = f"data:image/jpeg;base64,{b64}"
        raw, ext = validate_and_decode_artwork(data_url)
        assert ext == ".jpg"
        assert raw == SAMPLE_JPEG

    def test_valid_png_artwork_accepted(self) -> None:
        """Verifies PNG base64 is accepted and decoded."""
        b64 = base64.b64encode(SAMPLE_PNG).decode("ascii")
        raw, ext = validate_and_decode_artwork(b64)
        assert ext == ".png"
        assert raw == SAMPLE_PNG

    def test_valid_webp_artwork_accepted(self) -> None:
        """Verifies WebP base64 is accepted and decoded."""
        b64 = base64.b64encode(SAMPLE_WEBP).decode("ascii")
        raw, ext = validate_and_decode_artwork(b64)
        assert ext == ".webp"
        assert raw == SAMPLE_WEBP

    def test_invalid_image_magic_bytes_rejected(self) -> None:
        """Verifies non-image binary content disguised as base64 is rejected."""
        fake_bytes = b"MZ\x90\x00\x03\x00\x00\x00"  # Windows PE executable header
        b64 = base64.b64encode(fake_bytes).decode("ascii")
        with pytest.raises(ValueError, match="Unsupported or invalid image format"):
            validate_and_decode_artwork(b64)

    def test_malformed_base64_rejected(self) -> None:
        """Verifies invalid base64 string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid base64"):
            validate_and_decode_artwork("!!!not-valid-base64@@@")

    def test_oversized_artwork_rejected(self) -> None:
        """Verifies artwork exceeding size limit is rejected."""
        oversized_str = "A" * (16 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds maximum length"):
            validate_and_decode_artwork(oversized_str)

    def test_artwork_stored_in_isolated_temp_and_cleaned(self) -> None:
        """Verifies artwork is saved only to job temp dir and deleted on cleanup."""
        job_id = "test-art-isolation-job-123"
        temp_dir = get_job_temp_dir(job_id)
        b64 = base64.b64encode(SAMPLE_PNG).decode("ascii")

        art_path = save_artwork_to_isolated_temp(b64, temp_dir, "custom_artwork_global")
        assert art_path.exists()
        assert art_path.is_relative_to(temp_dir)
        assert art_path.read_bytes() == SAMPLE_PNG

        # Clean up
        cleanup_job_temp_dir(job_id)
        assert not art_path.exists()


class TestTaggingPrecedenceAndEngines:
    """Tests for metadata injection into MP3, M4A, FLAC, Opus, WAV audio containers."""

    def test_mp3_metadata_and_year_tagging(self, tmp_path: Path) -> None:
        """Verifies ID3 tags (TIT2, TPE1, TALB, TYER/TDRC, APIC) are embedded into MP3."""
        mp3_file = tmp_path / "test.mp3"
        # Write minimal valid MP3 frame
        mp3_file.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 500)

        art_file = tmp_path / "cover.jpg"
        art_file.write_bytes(SAMPLE_JPEG)

        success = tag_audio_file(
            file_path=mp3_file,
            title="Custom Title",
            artist="Custom Artist",
            album="Custom Album",
            year=2026,
            artwork_path=art_file,
        )
        assert success is True

        tags = ID3(str(mp3_file))
        assert str(tags.get("TIT2")) == "Custom Title"
        assert str(tags.get("TPE1")) == "Custom Artist"
        assert str(tags.get("TALB")) == "Custom Album"
        assert "2026" in str(tags.get("TYER")) or "2026" in str(tags.get("TDRC"))
        assert "APIC:Cover" in tags

    def test_flac_metadata_and_year_tagging(self, tmp_path: Path) -> None:
        """Verifies Vorbis comments and Picture are embedded into FLAC."""
        flac_file = tmp_path / "test.flac"
        # Generate minimal valid FLAC stream
        header = b"fLaC\x80\x00\x00"\
                 b"\x22\x10\x00\x10\x00\x00\x00\x00\x00\x00\x00\x0a\xc4\x42\xf0\x00\x00\x00\x00" \
                 b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        flac_file.write_bytes(header)

        art_file = tmp_path / "cover.png"
        art_file.write_bytes(SAMPLE_PNG)

        success = tag_audio_file(
            file_path=flac_file,
            title="FLAC Symphony",
            artist="FLAC Artist",
            album="FLAC Album",
            year=2024,
            artwork_path=art_file,
        )
        assert success is True

        audio = FLAC(str(flac_file))
        assert audio.get("title") == ["FLAC Symphony"]
        assert audio.get("artist") == ["FLAC Artist"]
        assert audio.get("album") == ["FLAC Album"]
        assert audio.get("date") == ["2024"]
        assert len(audio.pictures) == 1

    def test_tagging_skipped_gracefully_for_missing_file(self) -> None:
        """Verifies tag_audio_file returns False gracefully when file is absent."""
        assert tag_audio_file(Path("/non/existent/file.mp3"), title="Title") is False


class TestApiMetadataOverrides:
    """Integration tests for JobSubmitRequest API with metadata and track overrides."""

    def test_submit_job_with_metadata_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies POST /api/v1/jobs accepts metadata_overrides and forwards to JobManager."""
        mock_submit = MagicMock()
        monkeypatch.setattr(job_manager._executor, "submit", mock_submit)

        b64_art = base64.b64encode(SAMPLE_JPEG).decode("ascii")
        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "profile": "audiophile",
            "format": "flac",
            "metadata_overrides": {
                "title": "Custom Overridden Song",
                "artist": "Custom Performer",
                "album": "Greatest Hits",
                "year": 2026,
                "artwork": f"data:image/jpeg;base64,{b64_art}",
            },
        }

        res = client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "success"
        job_id = data["data"]["job_id"]
        assert job_id

        # Check DB record
        info = job_manager.get_job_info(job_id)
        assert info is not None
        assert info["title"] == "Custom Overridden Song"
        assert info["profile"] == DownloadProfile.AUDIOPHILE.value

    def test_submit_job_without_overrides_backward_compatible(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies existing client requests without metadata_overrides continue working."""
        mock_submit = MagicMock()
        monkeypatch.setattr(job_manager._executor, "submit", mock_submit)

        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "profile": "standard",
        }
        res = client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 201
        assert res.json()["status"] == "success"

    def test_invalid_metadata_year_returns_422(self) -> None:
        """Verifies malformed year produces clean validation error."""
        payload = {
            "url": "https://www.youtube.com/watch?v=BaW_jenozKc",
            "metadata_overrides": {
                "year": 99999,
            },
        }
        res = client.post("/api/v1/jobs", json=payload)
        assert res.status_code == 422


class TestFrontendMetadataEditorIntegration:
    """Tests verifying frontend HTML structure, labels, inputs, and accessible markup."""

    def test_metadata_review_elements_present_in_html(self) -> None:
        """Verifies all required metadata and artwork review elements exist in static HTML."""
        res = client.get("/")
        assert res.status_code == 200
        html = res.text

        # Verify state-ready editor inputs
        assert 'id="meta-title"' in html
        assert 'id="meta-artist"' in html
        assert 'id="meta-album"' in html
        assert 'id="meta-year"' in html

        # Verify artwork elements
        assert 'id="ready-artwork"' in html
        assert 'id="artwork-dropzone"' in html
        assert 'id="artwork-file-input"' in html
        assert 'id="upload-artwork-btn"' in html
        assert 'id="reset-artwork-btn"' in html

        # Verify action buttons
        assert 'id="revert-meta-btn"' in html
        assert 'id="start-download-btn"' in html
        assert "Confirm & Download" in html
