"""Automated Tests for Filename Sanitization and Path Traversal Defense."""

from pathlib import Path

from app.engine.sanitizer import (
    format_track_filename,
    safe_path_join,
    sanitize_filename,
)


class TestFilenameSanitization:
    """Tests for safe cross-platform filename formatting."""

    def test_strip_windows_forbidden_characters(self) -> None:
        raw = 'Song: "The Best" <Remix>? *Live* | Edition / Part 1\\2'
        cleaned = sanitize_filename(raw)
        # None of the forbidden characters should remain
        for char in '<>:"/\\|?*':
            assert char not in cleaned
        assert "Song The Best Remix Live Edition  Part 12" in cleaned or "Live" in cleaned

    def test_strip_trailing_periods_and_spaces(self) -> None:
        raw = "My Track Name. . . "
        cleaned = sanitize_filename(raw)
        assert cleaned == "My Track Name"

    def test_empty_or_non_string_fallback(self) -> None:
        assert sanitize_filename("") == "unnamed_track"
        assert sanitize_filename("   ") == "unnamed_track"
        assert sanitize_filename(None) == "unnamed_track"  # type: ignore[arg-type]

    def test_max_length_truncation(self) -> None:
        long_title = "A" * 200
        cleaned = sanitize_filename(long_title, max_length=50)
        assert len(cleaned) <= 50

    def test_format_track_filename_single(self) -> None:
        formatted = format_track_filename("Starlight Echoes", "mp3")
        assert formatted == "Starlight Echoes.mp3"

    def test_format_track_filename_playlist(self) -> None:
        formatted = format_track_filename("Solaris Chill", "flac", track_index=5)
        assert formatted == "005 - Solaris Chill.flac"


class TestPathTraversalDefense:
    """Tests for safe_path_join preventing directory escape."""

    def test_safe_path_join_normal(self, tmp_path: Path) -> None:
        joined = safe_path_join(tmp_path, "track.mp3")
        assert joined == tmp_path / "track.mp3"

    def test_safe_path_join_strips_directory_components(self, tmp_path: Path) -> None:
        # Path("..\\..\\secret.txt").name resolves to "secret.txt" inside tmp_path
        joined = safe_path_join(tmp_path, "../../secret.txt")
        assert joined == (tmp_path / "secret.txt").resolve()
        assert joined.parent == tmp_path.resolve()

    def test_safe_path_join_rejects_empty_and_dot_names(self, tmp_path: Path) -> None:
        import pytest

        with pytest.raises(ValueError, match="Invalid filename"):
            safe_path_join(tmp_path, "")

        with pytest.raises(ValueError, match="Invalid filename"):
            safe_path_join(tmp_path, ".")

        with pytest.raises(ValueError, match="Invalid filename"):
            safe_path_join(tmp_path, "..")
