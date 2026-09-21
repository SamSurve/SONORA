"""Auralis Metadata Extraction Service.

Provides pre-download media inspection, tracklist discovery, and URL validation
with SSRF defense enforcement.
"""

import logging
from typing import Any

from app.core.security import validate_url
from app.engine.ytdlp_engine import extract_media_info

logger = logging.getLogger(__name__)


def extract_metadata(url: str, is_playlist: bool = False) -> dict[str, Any]:
    """Inspects a media URL and returns normalized metadata with pre-flight SSRF validation.

    Args:
        url: User-supplied media URL.
        is_playlist: Hint whether target URL is expected to be a playlist.

    Returns:
        Normalized dictionary containing media title, uploader, thumbnail, duration,
        track count, and individual track items.

    Raises:
        InvalidURLException: Malformed URL or unapproved scheme.
        SSRFSecurityException: Resolved target IP is forbidden.
        RuntimeError: Metadata extraction failed in yt-dlp.
    """
    # 1. Pre-flight SSRF and URL validation
    validate_url(url, resolve_dns=True)

    # 2. Extract media info via yt-dlp flat extraction
    try:
        raw_info = extract_media_info(url, is_playlist=is_playlist)
    except Exception as e:
        logger.error("Failed to extract metadata for URL '%s': %s", url, e)
        raise RuntimeError(f"Metadata extraction failed: {e}") from e

    # 3. Normalize return structure
    entries = raw_info.get("entries") or []
    detected_is_playlist = bool(entries) or raw_info.get("_type") == "playlist" or is_playlist

    tracks: list[dict[str, Any]] = []
    if detected_is_playlist and entries:
        for idx, entry in enumerate(entries, start=1):
            if isinstance(entry, dict):
                tracks.append(
                    {
                        "index": idx,
                        "title": entry.get("title") or f"Track {idx}",
                        "duration_seconds": int(entry.get("duration") or 0),
                        "url": entry.get("url") or entry.get("webpage_url"),
                    }
                )
    else:
        tracks.append(
            {
                "index": 1,
                "title": raw_info.get("title") or "Unknown Title",
                "duration_seconds": int(raw_info.get("duration") or 0),
                "url": url,
            }
        )

    return {
        "id": raw_info.get("id") or "",
        "url": url,
        "title": raw_info.get("title") or "Unknown Media",
        "uploader": raw_info.get("uploader") or raw_info.get("channel") or "Unknown Artist",
        "duration_seconds": int(raw_info.get("duration") or 0),
        "thumbnail_url": raw_info.get("thumbnail") or "",
        "is_playlist": detected_is_playlist,
        "track_count": len(tracks),
        "tracks": tracks,
    }
