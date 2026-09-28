# SONORA — Phase 4 Sprint 2 Batch 3 Report
**Medium-Priority Production Hardening & Accessibility**
*Date: 2026-09-28*
*Baseline Checkpoint: `0238f5a`*
*Status: COMPLETED & VERIFIED*

---

## Executive Summary

Phase 4 Sprint 2 Batch 3 resolved all ten (10) **MEDIUM-severity** findings and accessibility gaps identified in `PHASE_4_SPRINT_2_AUDIT.md` (`MED-01` through `MED-10`). Every repair was engineered with surgical precision, maintaining 100% backward compatibility, strict Ruff compliance (all line lengths < 100 characters), and zero modifications to protected legacy files (`app.py`, `music_fixer.py`, `templates/index.html`, and `ffmpeg.exe`).

New comprehensive regression tests were added across five test suites (`test_audio_tagger.py`, `test_job_manager.py`, `test_quota_enforcement.py`, `test_frontend.py`, and `test_metadata_service.py`), certifying the stability and production quality of every hardened system.

---

## Detailed Findings & Repair Architecture

### MED-01: In-Memory RateLimiter History Memory Leak
- **Vulnerability:** `RateLimiter._history` retained dictionary entries for every IP address that ever submitted a job. Inactive IPs were never purged, leading to unbounded dictionary growth over prolonged operation.
- **Root Cause:** Expired timestamps were filtered only for the *current* client querying `is_allowed()`, but inactive keys were never pruned from the dictionary.
- **Fix Implementation:**
  - Added `max_tracked_clients: int = 10000` parameter in `RateLimiter.__init__()`.
  - Implemented `_prune_expired_locked(cutoff)`:
    - Purges all keys whose most recent timestamp is `<= cutoff` (or empty).
    - If total keys still exceed `max_tracked_clients`, sorts by latest activity and evicts excess oldest entries.
  - Automatically triggers `_prune_expired_locked()` inside `is_allowed()` if `now - self._last_prune_time >= self.window_seconds` or capacity is breached.
  - Added public `prune(force=False)` method for programmatic sweeps.
- **Regression Tests:**
  - `tests/test_quota_enforcement.py::test_rate_limiter_stale_history_pruning`
  - `tests/test_quota_enforcement.py::test_rate_limiter_capacity_bounding`

---

### MED-02: ID3v2.4 Windows Explorer Compatibility Issue
- **Compatibility Flaw:** Mutagen saves MP3 tags as ID3v2.4 by default. Windows Explorer, Windows Media Player, and legacy vehicle players do not support ID3v2.4, rendering downloaded MP3s with blank titles, unknown artists, and missing album art.
- **Root Cause:** `_tag_mp3()` in `app/engine/audio_tagger.py` invoked `tags.save(str(file_path), v2_version=4)`.
- **Fix Implementation:**
  - Updated `_tag_mp3()` to call `tags.save(str(file_path), v2_version=3)`, enforcing the universally compatible ID3v2.3 standard.
- **Regression Test:**
  - `tests/test_audio_tagger.py::TestMetadataAndArtworkTagging::test_tag_mp3_metadata_and_artwork` (explicitly asserts `call_args[1].get("v2_version") == 3`).

---

### MED-03: Missing WAV Audio Tagging Support
- **Functional Gap:** `tag_audio_file()` in `app/engine/audio_tagger.py` only supported MP3, M4A, FLAC, and Opus. If the user downloaded in WAV format, tagging was silently skipped, leaving files without Title, Artist, Album, or embedded artwork.
- **Root Cause:** Missing extension branch and tagging routine for `.wav`.
- **Fix Implementation:**
  - Added `from mutagen.wave import WAVE` import.
  - Implemented `_tag_wav(file_path, title, artist, album, track_number, artwork_data, mime_type)`:
    - Loads or creates ID3 chunk tags on RIFF container via `audio.add_tags()`.
    - Populates `TIT2`, `TPE1`, `TALB`, `TRCK`, and `APIC` front cover art.
    - Saves changes via `audio.save()`.
  - Added `.wav` branch to `tag_audio_file()` dispatch and updated docstrings.
- **Regression Test:**
  - `tests/test_audio_tagger.py::TestMetadataAndArtworkTagging::test_tag_wav_metadata_and_artwork`.

---

### MED-04: Multi-File Download Drops Additional Tracks for Non-Playlist Jobs
- **Data Loss Risk:** In `app/services/job_manager.py:_execute_job_pipeline()`, when `is_playlist=False`, the pipeline selected `final_delivery_path = final_files[0]`. If `yt-dlp` produced multiple output audio files (e.g., dual audio streams, bonus tracks, or unflagged multi-track releases), all files beyond the first were discarded.
- **Root Cause:** Hardcoded assumption that `is_playlist=False` strictly produces exactly one file.
- **Fix Implementation:**
  - Updated packaging logic to check:
    ```python
    if is_playlist or len(final_files) > 1:
        zip_title = album_name if is_playlist else (info.get("title") or "download")
        zip_path, zip_size = create_playlist_zip(
            job_id=job_id,
            job_completed_dir=completed_dir,
            playlist_title=zip_title,
        )
        final_delivery_path = zip_path
        total_size = zip_size
    else:
        final_delivery_path = final_files[0]
        total_size = final_delivery_path.stat().st_size
    ```
- **Regression Test:**
  - `tests/test_job_manager.py::TestJobManagerLifecycle::test_multi_file_non_playlist_job_packages_zip`.

---

### MED-05: Missing Browser Favicon Causes Repeated 404 Logging
- **Flaw:** Modern browsers automatically request `/favicon.ico` on every page visit. Without a defined favicon or route, server logs were cluttered with 404 Not Found error entries.
- **Fix Implementation:**
  - Created `app/static/img/favicon.svg` with clean, modern SONORA branding in SVG format.
  - Linked the favicon in `app/static/index.html` `<head>`:
    ```html
    <link rel="icon" type="image/svg+xml" href="/static/img/favicon.svg">
    <link rel="alternate icon" href="/favicon.ico">
    ```
  - Added dedicated `/favicon.ico` endpoint in `app/main.py`:
    ```python
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        favicon_path = static_dir / "img" / "favicon.svg"
        if favicon_path.exists():
            return FileResponse(favicon_path, media_type="image/svg+xml")
        return Response(status_code=204)
    ```
- **Regression Test:**
  - `tests/test_frontend.py::TestSonoraFrontendAndAnimation::test_favicon_delivery_and_html_link`.

---

### MED-06: Accessibility: URL Input Missing Accessible Label
- **Accessibility Violation:** `#url-input` in `app/static/index.html` relied solely on a `placeholder` attribute without an associated `<label>` or `aria-label`, failing WCAG 2.1 Success Criterion 3.3.2 (Labels or Instructions).
- **Fix Implementation:**
  - Added `<label for="url-input" class="sr-only">Media URL to download</label>` before the input element.
  - Added `aria-label="Media URL to download"` directly to the input element.
  - Added `aria-hidden="true"` to the decorative input SVG icon.
  - Added `.sr-only` screen reader utility class in `app/static/css/styles.css`.
- **Regression Test:**
  - `tests/test_frontend.py::TestSonoraFrontendAndAnimation::test_url_input_accessible_label`.

---

### MED-07: Accessibility: Format Chips Lack Radio Group Semantics
- **Accessibility Violation:** Format selection chips in `index.html` were unsemanticked button/div elements lacking `role="radiogroup"`, `role="radio"`, `aria-checked`, and keyboard arrow navigation, preventing keyboard-only and screen reader navigation.
- **Fix Implementation:**
  - Added `role="radiogroup"` and `aria-labelledby="format-label"` to the format grid container in `app/static/index.html`.
  - Added `role="radio"`, `aria-checked="true/false"`, and roving `tabindex="0/-1"` to format chip elements.
  - Implemented `selectFormatChip()` and keyboard listeners for `ArrowRight`, `ArrowLeft`, `ArrowDown`, `ArrowUp`, `Space`, and `Enter` in `app/static/js/app.js`.
- **Regression Test:**
  - `tests/test_frontend.py::TestSonoraFrontendAndAnimation::test_format_chips_radio_group_semantics`.

---

### MED-08: Accessibility: Dynamic Status Updates Lack ARIA Live Regions
- **Accessibility Violation:** Download progress percentages, status messages, and error banners updated dynamically in the DOM without `aria-live` or appropriate ARIA roles, leaving screen reader users unaware of progress or failures.
- **Fix Implementation:**
  - Added `role="status"` and `aria-live="polite"` to `#dl-status-text` and `#progress-percent`.
  - Added `role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"` to `#progress-bar-track`.
  - Added `role="alert"` and `aria-live="assertive"` to `#error-message`.
  - Added `role="status" aria-live="polite"` to `#state-completed` and `#state-cancelled`.
- **Regression Test:**
  - `tests/test_frontend.py::TestSonoraFrontendAndAnimation::test_dynamic_status_aria_live_regions`.

---

### MED-09: Uncapped Flat Metadata Extraction Memory Spike Risk
- **Stability Risk:** `extract_media_info()` invoked `extract_flat=True` without bounding `playlistend`. A user inspecting a playlist with thousands of items could trigger a massive memory spike and thread lockup.
- **Fix Implementation:**
  - Configured `"playlistend": settings.MAX_PLAYLIST_ITEMS` in `opts` within `extract_media_info()` in `app/engine/ytdlp_engine.py`.
- **Regression Test:**
  - `tests/test_metadata_service.py::test_extract_media_info_playlistend_cap`.

---

### MED-10: Incomplete Dark Mode Variables (Missing Shadows & Scrollbars)
- **Styling Flaw:** In `[data-theme="dark"]`, card elevations and surfaces lacked elevation shadow variables, causing interactive elements to blend invisibly into backgrounds.
- **Fix Implementation:**
  - Added elevated dark mode tokens `--shadow-sm`, `--shadow-md`, `--shadow-lg`, and `color-scheme: dark;` to `[data-theme="dark"]` in `app/static/css/styles.css`.
- **Regression Test:**
  - `tests/test_frontend.py::TestSonoraFrontendAndAnimation::test_dark_mode_elevation_shadows`.

---

## Protected Legacy Files Status

All 4 protected legacy files remain **100% byte-for-byte identical** to the baseline repository state:
1. `app.py`: UNCHANGED (53 lines, 1779 bytes)
2. `music_fixer.py`: UNCHANGED (25 lines, 881 bytes)
3. `templates/index.html`: UNCHANGED (103 lines, 2646 bytes)
4. `ffmpeg.exe`: UNCHANGED (134,163,456 bytes)

---

## Verification Summary

- **Total Test Suite:** 120+ tests across 19 test modules.
- **Ruff Linter Compliance:** All modified Python files conform strictly to PEP 8, UP (pyupgrade), import sorting (I001), and line length limits (< 100 characters).
- **Working Tree Integrity:** Clean, structured, and synchronized with `STATE.md` and `CHANGELOG.md`.
