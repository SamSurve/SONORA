"""Auralis Playlist ZIP Packaging Utility.

Packages completed playlist tracks into a single compressed ZIP archive with
path traversal protection.
"""

import logging
import zipfile
from pathlib import Path

from app.engine.sanitizer import sanitize_filename

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".opus", ".flac", ".wav"}


def create_playlist_zip(
    job_id: str,
    job_completed_dir: Path,
    playlist_title: str | None = None,
) -> tuple[Path, int]:
    """Compresses all finalized audio tracks in a job directory into a ZIP archive.

    Guarantees that:
    1. Only finalized audio files belonging to the job are packaged.
    2. Path traversal within the archive is strictly prevented.
    3. Temporary, partial, or hidden files are excluded.

    Args:
        job_id: Unique job identifier.
        job_completed_dir: Canonical directory containing completed tracks for this job.
        playlist_title: Optional title used for naming the zip file.

    Returns:
        tuple (Path to created zip file, total file size in bytes)

    Raises:
        FileNotFoundError: If the directory does not exist or has no audio tracks.
        ValueError: If directory traversal is detected.
    """
    if not job_completed_dir.exists() or not job_completed_dir.is_dir():
        raise FileNotFoundError(
            f"Completed directory for job '{job_id}' not found: {job_completed_dir}"
        )

    resolved_base = job_completed_dir.resolve()

    # Collect audio files, sorting by track index if possible
    audio_files: list[Path] = []
    for item in sorted(job_completed_dir.iterdir()):
        if item.is_file() and item.suffix.lower() in AUDIO_EXTENSIONS:
            # Traversal check: ensure each item is strictly within resolved_base
            resolved_item = item.resolve()
            try:
                resolved_item.relative_to(resolved_base)
            except ValueError as e:
                raise ValueError(
                    f"Path traversal detected: '{item}' is outside '{job_completed_dir}'"
                ) from e
            audio_files.append(item)

    if not audio_files:
        raise FileNotFoundError(
            f"No finalized audio tracks found in '{job_completed_dir}' to archive."
        )

    # Name the ZIP archive safely
    clean_title = sanitize_filename(playlist_title or f"playlist_{job_id[:8]}")
    zip_path = job_completed_dir / f"{clean_title}.zip"

    logger.info("Packaging %d tracks into ZIP archive: %s", len(audio_files), zip_path)

    # Write ZIP archive
    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as zf:
        for audio_file in audio_files:
            # Strictly use the sanitized basename for arcname to prevent path injection
            safe_arcname = audio_file.name
            zf.write(audio_file, arcname=safe_arcname)

    total_size = zip_path.stat().st_size
    logger.info("Successfully created ZIP archive: %s (%d bytes)", zip_path, total_size)
    return zip_path, total_size
