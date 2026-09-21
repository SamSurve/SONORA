"""Tests for yt-dlp Core Download Engine Options and Progress Hooks.

Verifies option building, socket timeouts, allowed protocols, thumbnail postprocessors,
and composite playlist progress calculations.
"""

from pathlib import Path

from app.engine.ytdlp_engine import ProgressEvent, build_ydl_options


def test_build_ydl_options_timeouts_and_protocols(tmp_path: Path) -> None:
    """Verifies socket_timeout and allowed_protocols in yt-dlp option dictionary."""
    temp_dir = tmp_path / "scratch"
    temp_dir.mkdir(parents=True, exist_ok=True)

    opts = build_ydl_options(
        job_id="test_job_123",
        temp_dir=temp_dir,
        target_format="mp3",
        is_playlist=False,
    )

    assert opts["socket_timeout"] == 20
    assert opts["allowed_protocols"] == ["http", "https"]
    assert opts["noplaylist"] is True
    assert opts["writethumbnail"] is True

    # Verify FFmpegThumbnailsConvertor is present
    has_thumb_conv = any(
        pp.get("key") == "FFmpegThumbnailsConvertor" for pp in opts.get("postprocessors", [])
    )
    assert has_thumb_conv is True


def test_composite_playlist_progress_calculation(tmp_path: Path) -> None:
    """Verifies composite percentage calculation across multi-track playlists."""
    temp_dir = tmp_path / "scratch"
    temp_dir.mkdir(parents=True, exist_ok=True)

    events: list[ProgressEvent] = []

    def mock_callback(event: ProgressEvent) -> None:
        events.append(event)

    opts = build_ydl_options(
        job_id="playlist_job_456",
        temp_dir=temp_dir,
        target_format="mp3",
        is_playlist=True,
        progress_callback=mock_callback,
    )

    hook = opts["progress_hooks"][0]

    # Simulate downloading Track 2 of 5 at 50% byte completion
    d = {
        "status": "downloading",
        "total_bytes": 1000,
        "downloaded_bytes": 500,
        "speed": 100000.0,
        "eta": 5,
        "filename": "002 - Track Title.opus",
        "info_dict": {
            "title": "Track Title 2",
            "playlist_index": 2,
            "n_entries": 5,
        },
    }

    hook(d)

    assert len(events) == 1
    evt = events[0]
    # Composite calculation: ((2 - 1) * 100 + 50) / 5 = 150 / 5 = 30.0%
    assert evt.percent == 30.0
    assert evt.track_index == 2
    assert evt.total_tracks == 5
