# SONORA — PHASE 5 FEATURE 1 REPORT
## Download Profiles Implementation (Audiophile, Standard, Space Saver, Raw Video)

**Date:** 2026-09-28  
**Phase:** Phase 5 — Core Product Enhancements  
**Feature:** Feature 1 — Download Profiles  
**Baseline Commit:** `0238f5a`  
**Status:** IMPLEMENTED & REGRESSION TESTED  

---

## 1. Executive Summary

Phase 5 Feature 1 introduces a first-class **Download Profile** architecture into SONORA, allowing users to select their target media profile prior to downloading. The download profile governs the entire processing pipeline from format selection in yt-dlp, FFmpeg transcoding/muxing, scratchpad discovery, metadata tagging, ZIP packaging, and final file delivery.

All 4 required download profiles have been cleanly implemented with full backward compatibility:
1. **AUDIOPHILE:** Lossless audio extraction encapsulated in FLAC containers.
2. **STANDARD (Default):** Universal compatibility MP3 transcode at 320 kbps CBR.
3. **SPACE_SAVER:** Lightweight and storage-efficient M4A/AAC audio transcode at 128 kbps CBR.
4. **RAW_VIDEO:** High-definition MP4 video container preserving both audio and video streams without extracting audio.

---

## 2. Technical Profile Taxonomy & Specifications

| Profile ID | Display Name | Container Ext | Target Format | Bitrate / Quality | Video Stream | FFmpeg Postprocessor |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `audiophile` | Audiophile | `.flac` | `AudioFormat.FLAC` | Lossless / PCM | No | `FFmpegExtractAudio` (flac) |
| `standard` | Standard *(Default)* | `.mp3` | `AudioFormat.MP3_320`| 320 kbps CBR | No | `FFmpegExtractAudio` (mp3, 320k) |
| `space_saver` | Space Saver | `.m4a` | `m4a` | 128 kbps CBR | No | `FFmpegExtractAudio` (m4a, 128k) |
| `raw_video` | Raw Video | `.mp4` | `mp4` | Best Available | **Yes** | None *(Mux to MP4 container)* |

---

## 3. Architecture & Implementation Across Layers

### 3.1. Core Constants (`app/core/constants.py`)
- Defined `DownloadProfile` string enum with `AUDIOPHILE`, `STANDARD`, `SPACE_SAVER`, and `RAW_VIDEO`.
- Defined `ProfileSemantics` NamedTuple and `PROFILE_TAXONOMY` mapping each profile to its canonical technical metadata (name, display name, description, extension, is_video, audio_format, bitrate_kbps).

### 3.2. Database & Persistence Layer (`app/db/repository.py`)
- **Schema DDL:** Added `profile TEXT NOT NULL DEFAULT 'standard'` to `jobs` table in `SCHEMA_SQL`.
- **Column Migration:** Updated `init_db(conn)` to inspect existing database schemas via `PRAGMA table_info(jobs)` and dynamically execute `ALTER TABLE jobs ADD COLUMN profile TEXT NOT NULL DEFAULT 'standard';` if missing.
- **Repository CRUD:** Updated `create_job()` to accept `profile: str = "standard"` and bind it in the SQL `INSERT` statement.

### 3.3. Engine & Transcoding Layer (`app/engine/ytdlp_engine.py`)
- Updated `build_ydl_options()` and `execute_download()` to accept `profile: DownloadProfile | str | None = None`.
- For `AUDIOPHILE`: Configures `format="bestaudio/best"` and `preferredcodec="flac"`.
- For `STANDARD`: Configures `format="bestaudio/best"` and `preferredcodec="mp3"` at 320k.
- For `SPACE_SAVER`: Configures `format="bestaudio[ext=m4a]/bestaudio[acodec=aac]/bestaudio/best"` and `preferredcodec="m4a"` at 128k.
- For `RAW_VIDEO`: Configures `format="bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"` with `merge_output_format="mp4"`, omitting any audio extraction postprocessor.
- Preserved 100% backward compatibility for calls omitting `profile`.

### 3.4. Video Packaging & Audio Tagging (`app/engine/archive_packager.py`, `app/engine/audio_tagger.py`)
- **Archive Packager:** Expanded `MEDIA_EXTENSIONS` to include `{".mp3", ".m4a", ".opus", ".flac", ".wav", ".mp4", ".mkv", ".webm"}` and aliased `AUDIO_EXTENSIONS = MEDIA_EXTENSIONS`, allowing video playlists to be compressed into ZIP archives without path traversal vulnerabilities.
- **Audio/Video Tagging:** Updated `tag_audio_file()` in `audio_tagger.py` to route `.mp4` video files to `_tag_m4a()`, embedding Title, Artist, Album, and Cover Art into MP4 containers via Mutagen.

### 3.5. Job Management Service (`app/services/job_manager.py`)
- Updated `submit_job()` signature to accept `profile: DownloadProfile | str = DownloadProfile.STANDARD`.
- Implemented intelligent profile inference: if `profile` is defaulted but a non-standard `target_format` (e.g. `flac` or `mp4`) is supplied, resolves the matching profile.
- Propagated `profile` through `_run_job_with_retries()` and `_execute_job_pipeline()`.
- Updated scratchpad file discovery to look for `media_extensions` (including `.mp4`), preventing `FileNotFoundError` during video downloads.

### 3.6. API Layer (`app/api/v1/endpoints.py`)
- Added `GET /api/v1/profiles` endpoint returning full profile definitions and taxonomy metadata.
- Added `profile` field with `@field_validator("profile", mode="before")` in `JobSubmitRequest`, validating profile strings and returning HTTP 422 with a helpful error message on invalid input.
- Updated `download_job_file` to support `video/mp4` and `video/x-matroska` MIME types.

### 3.7. Modern Frontend UI (`app/static/index.html`, `app/static/js/app.js`, `app/static/css/styles.css`)
- **HTML:** Added Download Profile Selection Panel in `#state-idle` with ARIA radio semantics (`role="radiogroup"`, `role="radio"`, `aria-checked="true"` for standard by default).
- **CSS:** Added `.profile-selection-panel`, `.profile-grid` (2-column layout), `.profile-chip`, and `.profile-chip.active` styles with hover elevation and dark mode support.
- **JavaScript:**
  - Added `context.selectedProfile = 'standard'`.
  - Added `selectProfileChip()` and `initProfileSelection()` supporting click selection, roving tabindex, and full keyboard arrow navigation (`ArrowRight`, `ArrowLeft`, `ArrowDown`, `ArrowUp`, `Enter`, `Space`).
  - Added `profile` field to `startDownload()` JSON payload when calling `POST /api/v1/jobs`.

---

## 4. Protected Legacy File Verification

As strictly mandated by the project protocol, all protected legacy files remain **100% byte-for-byte untouched**:
- `app.py`: **UNTOUCHED**
- `music_fixer.py`: **UNTOUCHED**
- `templates/index.html`: **UNTOUCHED**
- `ffmpeg.exe`: **UNTOUCHED**

---

## 5. Verification & Test Suite Additions

### 5.1. New Automated Test Suite: `tests/test_profiles.py` (17 Tests)
- `TestDownloadProfileTaxonomy`:
  - `test_all_expected_profiles_exist`
  - `test_profile_taxonomy_semantics`
- `TestYtdlpEngineProfiles`:
  - `test_audiophile_flac_options`
  - `test_standard_mp3_options`
  - `test_space_saver_m4a_options`
  - `test_raw_video_mp4_options`
  - `test_backward_compatibility_without_profile`
- `TestDatabaseRepositoryProfile`:
  - `test_create_and_get_job_persists_profile`
  - `test_default_profile_is_standard`
- `TestArchivePackagerMediaExtensions`:
  - `test_media_extensions_includes_video_formats`
  - `test_create_playlist_zip_with_mp4_files`
- `TestApiDownloadProfiles`:
  - `test_list_profiles_endpoint`
  - `test_submit_job_with_audiophile_profile`
  - `test_submit_job_with_raw_video_profile`
  - `test_submit_job_with_space_saver_profile`
  - `test_submit_job_default_profile_is_standard`
  - `test_submit_job_invalid_profile_returns_422`
- `TestJobManagerPipelineProfiles`:
  - `test_pipeline_executes_raw_video_profile`
  - `test_pipeline_executes_audiophile_flac_profile`

### 5.2. Frontend UI Tests: `tests/test_frontend.py`
- `test_download_profiles_dom_semantics_and_styles`: Verifies DOM hierarchy, ARIA radiogroup/radio semantics, default active state, CSS rule definitions, and JS controller hooks.

---

## 6. Summary of Changed Files

| File Path | Action | Description |
| :--- | :--- | :--- |
| `app/core/constants.py` | Modified | Added `DownloadProfile` enum, `ProfileSemantics`, and `PROFILE_TAXONOMY`. |
| `app/db/repository.py` | Modified | Added `profile` column to schema DDL, `init_db()` migration, and `create_job()`. |
| `app/engine/ytdlp_engine.py` | Modified | Updated `build_ydl_options()` and `execute_download()` with profile options. |
| `app/engine/archive_packager.py` | Modified | Expanded `MEDIA_EXTENSIONS` to include video formats (`.mp4`, `.mkv`, `.webm`). |
| `app/engine/audio_tagger.py` | Modified | Added `.mp4` container tagging support in `tag_audio_file()`. |
| `app/services/job_manager.py` | Modified | Added profile handling to `submit_job()`, worker dispatch, and media file discovery. |
| `app/api/v1/endpoints.py` | Modified | Added `GET /api/v1/profiles`, `JobSubmitRequest.profile` validation, and video MIME type delivery. |
| `app/static/index.html` | Modified | Added Download Profile selector chips panel with ARIA attributes. |
| `app/static/css/styles.css` | Modified | Added CSS rules for `.profile-selection-panel`, `.profile-grid`, and `.profile-chip`. |
| `app/static/js/app.js` | Modified | Added profile state tracking, radio selection, keyboard navigation, and submit payload. |
| `tests/test_profiles.py` | Created | Comprehensive 17-test regression suite covering profiles across all layers. |
| `tests/test_frontend.py` | Modified | Added frontend test verifying profile selector chips, CSS, and JS. |
| `STATE.md` | Modified | Updated project state to Phase 5 Feature 1 (COMPLETED) with status matrix. |
| `CHANGELOG.md` | Modified | Added version 3.5.0-phase5.feature1 release notes. |
