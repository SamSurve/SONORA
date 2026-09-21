"""Auralis yt-dlp Core Download Engine.

Encapsulates yt-dlp execution, hooks progress telemetry into normalized events,
enforces cooperative cancellation, and structures single vs. playlist options.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp

from app.core.config import settings
from app.core.constants import AudioFormat
from app.engine.ffmpeg_locator import get_ffmpeg_path

logger = logging.getLogger(__name__)


class DownloadCancelledException(Exception):
    """Raised when a download task is cooperatively cancelled via threading.Event."""


@dataclass
class ProgressEvent:
    """Normalized progress update for consumption by job managers and future SSE."""

    job_id: str
    stage: str
    percent: float
    speed_bytes: float
    eta_seconds: int
    current_track: str
    track_index: int | None = None
    total_tracks: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes the progress event to a dictionary for SSE transmission."""
        return {
            "job_id": self.job_id,
            "stage": self.stage,
            "percent": self.percent,
            "speed_bytes": self.speed_bytes,
            "eta_seconds": self.eta_seconds,
            "current_track": self.current_track,
            "track_index": self.track_index,
            "total_tracks": self.total_tracks,
        }


def build_ydl_options(
    job_id: str,
    temp_dir: Path,
    target_format: AudioFormat | str,
    is_playlist: bool = False,
    selected_indices: list[int] | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Assembles safe, deterministic yt-dlp options.

    Configures audio extraction, output templates, progress hooks, and cancellation checks.
    """
    ffmpeg_bin = get_ffmpeg_path()
    format_str = (
        target_format.value if isinstance(target_format, AudioFormat) else str(target_format)
    )

    # Isolated scratchpad template
    if is_playlist:
        outtmpl = str(temp_dir / "%(playlist_index)03d - %(title).100B.%(ext)s")
    else:
        outtmpl = str(temp_dir / "%(title).100B.%(ext)s")

    def _progress_hook(d: dict[str, Any]) -> None:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelledException(f"Job '{job_id}' was cancelled by user.")

        if d.get("status") == "downloading" and progress_callback:
            track_total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            track_downloaded = d.get("downloaded_bytes", 0)
            track_percent = min(100.0, (track_downloaded / track_total) * 100.0)

            info_dict = d.get("info_dict", {}) or {}
            playlist_index = info_dict.get("playlist_index") or 1
            n_entries = info_dict.get("n_entries") or 1

            if is_playlist and n_entries > 1:
                percent = min(
                    100.0, round(((playlist_index - 1) * 100.0 + track_percent) / n_entries, 1)
                )
            else:
                percent = min(100.0, round(track_percent, 1))

            speed = float(d.get("speed") or 0.0)
            eta = int(d.get("eta") or 0)
            filename = Path(d.get("filename", "")).name
            track_title = info_dict.get("title") or filename

            event = ProgressEvent(
                job_id=job_id,
                stage="downloading",
                percent=percent,
                speed_bytes=speed,
                eta_seconds=eta,
                current_track=track_title,
                track_index=playlist_index if is_playlist else None,
                total_tracks=n_entries if is_playlist else None,
            )
            progress_callback(event)

    def _postprocessor_hook(d: dict[str, Any]) -> None:
        if cancel_event and cancel_event.is_set():
            raise DownloadCancelledException(
                f"Job '{job_id}' was cancelled during post-processing."
            )

        if progress_callback and d.get("status") == "started":
            event = ProgressEvent(
                job_id=job_id,
                stage="converting",
                percent=95.0,
                speed_bytes=0.0,
                eta_seconds=0,
                current_track="Audio processing in progress",
            )
            progress_callback(event)

    # Format selection and postprocessors
    postprocessors: list[dict[str, Any]] = []

    # Always add thumbnail converter to ensure WebP is converted to JPG for Mutagen
    postprocessors.append(
        {
            "key": "FFmpegThumbnailsConvertor",
            "format": "jpg",
            "when": "before_dl",
        }
    )

    format_selector = "bestaudio/best"

    if "mp3" in format_str:
        quality = "256" if "256" in format_str else ("0" if "vbr" in format_str else "320")
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }
        )
    elif "flac" in format_str:
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "flac",
            }
        )
    elif "opus" in format_str or "native_opus" in format_str:
        format_selector = "bestaudio[ext=webm]/bestaudio[acodec=opus]/bestaudio"
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "opus",
            }
        )
    elif "m4a" in format_str or "native_m4a" in format_str:
        format_selector = "bestaudio[ext=m4a]/bestaudio[acodec=aac]/bestaudio"
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
            }
        )
    elif "wav" in format_str:
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        )

    opts: dict[str, Any] = {
        "format": format_selector,
        "outtmpl": outtmpl,
        "ffmpeg_location": str(Path(ffmpeg_bin).parent),
        "writethumbnail": True,
        "noplaylist": not is_playlist,
        "playlistend": settings.MAX_PLAYLIST_ITEMS if is_playlist else None,
        "socket_timeout": settings.SOCKET_TIMEOUT,
        "allowed_protocols": ["http", "https"],
        "ignoreerrors": is_playlist,  # Skip failed tracks in a playlist without aborting whole job
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_progress_hook],
        "postprocessor_hooks": [_postprocessor_hook],
        "postprocessors": postprocessors,
    }

    if is_playlist and selected_indices:
        opts["playlist_items"] = ",".join(str(i) for i in selected_indices)

    return opts


def execute_download(
    job_id: str,
    url: str,
    temp_dir: Path,
    target_format: AudioFormat | str,
    is_playlist: bool = False,
    selected_indices: list[int] | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Executes media extraction and download within an isolated scratchpad.

    Returns:
        Extracted media info dictionary from yt-dlp.

    Raises:
        DownloadCancelledException: If user cancelled the task.
        Exception: If download fails.
    """
    opts = build_ydl_options(
        job_id=job_id,
        temp_dir=temp_dir,
        target_format=target_format,
        is_playlist=is_playlist,
        selected_indices=selected_indices,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info or {}


def extract_media_info(url: str, is_playlist: bool = False) -> dict[str, Any]:
    """Extracts media metadata without downloading streams."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist" if is_playlist else True,
        "skip_download": True,
        "socket_timeout": settings.SOCKET_TIMEOUT,
        "allowed_protocols": ["http", "https"],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}
