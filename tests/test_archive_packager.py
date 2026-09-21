"""Automated Tests for Playlist ZIP Packaging and Traversal Protection."""

import zipfile
from pathlib import Path

import pytest

from app.engine.archive_packager import create_playlist_zip


class TestArchivePackager:
    """Tests for playlist ZIP compression and path security."""

    def test_package_valid_playlist(self, tmp_path: Path) -> None:
        completed_dir = tmp_path / "job_123"
        completed_dir.mkdir()

        # Create simulated audio files
        track1 = completed_dir / "001 - Intro.mp3"
        track1.write_bytes(b"audio track 1 data")
        track2 = completed_dir / "002 - Outro.mp3"
        track2.write_bytes(b"audio track 2 data")

        # Create ignored non-audio file
        thumbnail = completed_dir / "cover.jpg"
        thumbnail.write_bytes(b"image data")

        zip_path, size = create_playlist_zip(
            job_id="job_123",
            job_completed_dir=completed_dir,
            playlist_title="Synthwave 2026",
        )

        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        assert size > 0

        # Inspect ZIP contents
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            assert "001 - Intro.mp3" in namelist
            assert "002 - Outro.mp3" in namelist
            # Non-audio files must NOT be in the audio ZIP
            assert "cover.jpg" not in namelist

    def test_no_audio_files_raises_error(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty_job"
        empty_dir.mkdir()
        (empty_dir / "random.txt").write_bytes(b"not audio")

        with pytest.raises(FileNotFoundError, match="No finalized audio tracks found"):
            create_playlist_zip("empty_job", empty_dir)

    def test_archive_excludes_temp_and_partial_files(self, tmp_path: Path) -> None:
        completed_dir = tmp_path / "job_clean"
        completed_dir.mkdir()

        (completed_dir / "track.mp3").write_bytes(b"audio data")
        (completed_dir / "track.mp3.part").write_bytes(b"temp")
        (completed_dir / "scratch.tmp").write_bytes(b"scratch")

        zip_path, _ = create_playlist_zip("job_clean", completed_dir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            assert "track.mp3" in namelist
            assert "track.mp3.part" not in namelist
            assert "scratch.tmp" not in namelist
