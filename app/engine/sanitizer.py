"""Auralis Filename and Path Sanitization Utility.

Ensures deterministic, cross-platform, filesystem-safe filenames and prevents
directory traversal attacks.
"""

import re
from pathlib import Path

# Characters strictly forbidden on Windows/Linux/macOS filesystems
FORBIDDEN_CHARS_REGEX = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
COLLAPSE_SPACES_REGEX = re.compile(r"\s+")


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """Sanitizes a string for safe usage as a filename.

    Strips forbidden characters, collapses whitespace, trims trailing periods and spaces,
    and caps total character length.

    Args:
        name: Raw string (e.g. video title).
        max_length: Maximum allowed length for the base name.

    Returns:
        Filesystem-safe sanitized filename string.
    """
    if not name or not isinstance(name, str):
        return "unnamed_track"

    # Replace forbidden characters with empty string or underscore
    cleaned = FORBIDDEN_CHARS_REGEX.sub("", name)

    # Normalize whitespace
    cleaned = COLLAPSE_SPACES_REGEX.sub(" ", cleaned).strip()

    # Strip characters problematic on Windows at the end of filenames
    cleaned = cleaned.rstrip(". ")

    if not cleaned:
        cleaned = "unnamed_track"

    # Truncate to maximum length safely
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(". ")

    return cleaned


def format_track_filename(title: str, extension: str, track_index: int | None = None) -> str:
    """Formats a standardized output filename.

    If track_index is provided, formats as '001 - Title.ext'.
    Otherwise formats as 'Title.ext'.
    """
    safe_title = sanitize_filename(title)
    clean_ext = extension.lstrip(".").lower()

    if track_index is not None and track_index > 0:
        return f"{track_index:03d} - {safe_title}.{clean_ext}"
    return f"{safe_title}.{clean_ext}"


def safe_path_join(base_dir: Path, untrusted_filename: str) -> Path:
    """Joins an untrusted filename to a base directory, verifying no directory traversal.

    Args:
        base_dir: Canonical root directory for storage.
        untrusted_filename: User- or metadata-supplied filename.

    Returns:
        Resolved Path inside base_dir.

    Raises:
        ValueError: If path escapes base_dir.
    """
    safe_name = Path(untrusted_filename).name  # Strips any leading directory components
    if not safe_name or safe_name in (".", ".."):
        raise ValueError(f"Invalid filename: '{untrusted_filename}'")

    target_path = (base_dir / safe_name).resolve()
    base_resolved = base_dir.resolve()

    try:
        target_path.relative_to(base_resolved)
    except ValueError as e:
        raise ValueError(
            f"Path traversal detected: '{untrusted_filename}' escapes '{base_dir}'"
        ) from e

    if target_path == base_resolved:
        raise ValueError(f"Target path cannot be the base directory: '{untrusted_filename}'")

    return target_path
