"""Automated Tests for Dynamic FFmpeg Discovery & Verification."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.engine.ffmpeg_locator import (
    FFmpegNotFoundException,
    get_ffmpeg_path,
    verify_ffmpeg,
)


class TestFFmpegVerification:
    """Tests for binary execution and version parsing."""

    def test_verify_nonexistent_file(self) -> None:
        is_valid, msg = verify_ffmpeg("non_existent_ffmpeg_binary_xyz.exe")
        assert is_valid is False
        assert "does not exist" in msg

    def test_verify_non_ffmpeg_file(self) -> None:
        # A text file is not a valid executable
        is_valid, msg = verify_ffmpeg("requirements.txt")
        assert is_valid is False

    def test_verify_existing_root_ffmpeg(self) -> None:
        # Check if the root ffmpeg.exe exists and runs
        root_ffmpeg = Path("ffmpeg.exe")
        if root_ffmpeg.exists():
            is_valid, version_str = verify_ffmpeg(root_ffmpeg)
            assert is_valid is True
            assert "ffmpeg version" in version_str.lower()


class TestFFmpegResolutionOrder:
    """Tests resolution priority: custom -> config -> system -> root -> vendor."""

    def test_successful_discovery(self) -> None:
        # When root ffmpeg.exe is present, it should resolve successfully
        path = get_ffmpeg_path()
        assert Path(path).exists()
        assert Path(path).name.startswith("ffmpeg")

    def test_custom_path_precedence(self) -> None:
        # If custom path is provided and valid, it takes priority
        root_ffmpeg = Path("ffmpeg.exe")
        if root_ffmpeg.exists():
            resolved = get_ffmpeg_path(custom_path=str(root_ffmpeg))
            assert Path(resolved).resolve() == root_ffmpeg.resolve()

    def test_missing_ffmpeg_raises_exception(self) -> None:
        # Simulate all lookups failing
        with (
            patch("shutil.which", return_value=None),
            patch("pathlib.Path.exists", return_value=False),
        ):
            with pytest.raises(
                FFmpegNotFoundException, match="Could not locate a functioning FFmpeg binary"
            ):
                get_ffmpeg_path()
