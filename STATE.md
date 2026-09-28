# SONORA — PROJECT STATE

**Current Phase:** Phase 5 — Core Product Enhancements
**Current Feature:** Feature 2 — Pre-Download Metadata & Artwork Editor (COMPLETED)
**Baseline Commit:** `d4e3cd9` (`feat: add download profiles`)
**Remote:** `https://github.com/SamSurve/SONORA.git`
**Branch:** `master`
**Status:** Phase 5 Feature 2 Implemented & Verified — Ready for Review & Checkpoint

---

## 1. Phase 4 Sprint 1 Status Matrix

| Task ID | Component | Issue Addressed | Status | Implementation Details |
| :--- | :--- | :--- | :--- | :--- |
| **CRIT-01** | Backend / SSE | SSE `AttributeError` on ProgressEvent | **FIXED** | Mapped canonical dataclass fields (`stage`, `speed_bytes`, `current_track`, `track_index`) in `endpoints.py`. |
| **CRIT-02** | Frontend / Sec | DOM XSS in Playlist Rendering | **FIXED** | Replaced `innerHTML` with `document.createElement()` and `textContent` in `renderPlaylistItems()` in `app.js`. |
| **CRIT-03** | Backend / Arch | Process/Thread abandonment on shutdown | **FIXED** | Added `get_job_manager().shutdown(wait=True)` and `janitor.join(timeout=5.0)` to lifespan in `main.py`. |
| **CRIT-04** | Security / SSRF| Dead redirect validation in yt-dlp | **FIXED** | Installed `install_ssrf_redirect_protection()` hooking `validate_redirect()` into `yt-dlp` handlers, scoped to execution, leaving standard `urllib` clean. |
| **CRIT-05** | Security / API | Wildcard CORS + credentials violation | **FIXED** | Configured explicit `CORS_ORIGINS` whitelist, safe credentials, and comma-separated env parsing in `config.py` and `main.py`. |
| **CRIT-06** | Dependencies | CVE-2024-53981 in `python-multipart` | **FIXED** | Upgraded `python-multipart>=0.0.20` in `requirements.txt` and `pyproject.toml`. |
| **CRIT-07** | Frontend / UX | Permanent deadlock in INSPECTING state | **FIXED** | Added `AbortController` (15s timeout) and `#cancel-inspecting-btn` in `index.html` and `app.js`. |
| **HIGH-02** | Security / Storage| Arbitrary file read in download endpoint | **FIXED** | Enforced `resolved_file.is_relative_to(settings.COMPLETED_DIR.resolve())` in `download_job_file`. |
| **HIGH-06** | Frontend / UX | Double-submit network race conditions | **FIXED** | Added disabled state guards to `#submit-btn` and `#start-download-btn` during async requests. |
| **HIGH-07** | CSS / Layout | CSS syntax error (missing brace on `.feature-icon`) | **FIXED** | Fixed unclosed brace and removed duplicate stub before `.mobile-menu-btn` in `styles.css`. |
| **ISOLATION**| Test Suite | Test suite polluting production DB | **FIXED** | Added autouse `isolate_test_environment` fixture in `tests/conftest.py` isolating `DB_PATH`, `TEMP_DIR`, and `COMPLETED_DIR`. |
| **AUDIT-01** | Test Suite | Quota test worker leakage to YouTube | **FIXED** | Mocked `_executor.submit` in rate limiting tests and ensured `wait=True` on fixture shutdown. |
| **AUDIT-02** | Security / SSRF| Process-global urllib monkeypatch | **FIXED** | Removed global `urllib.request` patch; scoped hook to `yt-dlp` redirect handler during execution. |
| **AUDIT-03** | Test Suite | Flaky SSE event stream test timing | **FIXED** | Added registration callback hook to dispatch `ProgressEvent` deterministically upon client connection. |
| **AUDIT-04** | API / SSE | DB fallback missing schema fields | **FIXED** | Aligned DB fallback event keys with `ProgressEvent` dataclass schema in `endpoints.py`. |
| **AUDIT-07** | Config / CORS | Comma-separated CORS string parsing | **FIXED** | Added Pydantic `@field_validator` to parse comma-separated `CORS_ORIGINS` strings into `list[str]`. |
| **AUDIT-08** | Concurrency | `shutdown(wait=False)` worker abandonment | **FIXED** | Converted all test fixture shutdowns to `shutdown(wait=True)`. |

---

## 2. Test Suite & Code Quality Status
- **Test Modules:** 19 modules, 120+ tests
- **New Regression Tests (Sprint 2 Batches 1, 2 & 3):**
  - `test_schema_init_db_runs_only_once_per_database_path` in `test_database.py` (CRIT-01)
  - `test_sse_polling_fallback_bounded_retries` in `test_frontend.py` (CRIT-02)
  - `test_ytdlp_presend_ssrf_validation_hook` in `test_api.py` (HIGH-01)
  - `test_windows_reserved_device_names_prefixed` in `test_sanitizer.py` (HIGH-02)
  - `test_format_track_filename_windows_reserved` in `test_sanitizer.py` (HIGH-02)
  - `test_safe_path_join_handles_windows_reserved_names` in `test_sanitizer.py` (HIGH-02)
  - `test_create_job_empty_playlist_rejected` in `test_api.py` (HIGH-03)
  - `test_build_ydl_options_empty_playlist_indices` in `test_api.py` (HIGH-03)
  - `test_empty_playlist_selection_ui_behavior` in `test_frontend.py` (HIGH-03)
  - `test_playlist_checklist_css_constraints` in `test_frontend.py` (HIGH-04)
  - `test_tracks_unique_constraint_and_upsert` in `test_database.py` (HIGH-05)
  - `test_cancellation_during_retry_backoff` in `test_job_manager.py` (HIGH-06)
  - `test_trusted_proxies_client_ip_extraction` in `test_api.py` (HIGH-07)
  - `test_rate_limiter_stale_history_pruning` in `test_quota_enforcement.py` (MED-01)
  - `test_rate_limiter_capacity_bounding` in `test_quota_enforcement.py` (MED-01)
  - `test_tag_mp3_metadata_and_artwork` (asserts ID3v2.3) in `test_audio_tagger.py` (MED-02)
  - `test_tag_wav_metadata_and_artwork` in `test_audio_tagger.py` (MED-03)
  - `test_multi_file_non_playlist_job_packages_zip` in `test_job_manager.py` (MED-04)
  - `test_favicon_delivery_and_html_link` in `test_frontend.py` (MED-05)
  - `test_url_input_accessible_label` in `test_frontend.py` (MED-06)
  - `test_format_chips_radio_group_semantics` in `test_frontend.py` (MED-07)
  - `test_dynamic_status_aria_live_regions` in `test_frontend.py` (MED-08)
  - `test_extract_media_info_playlistend_cap` in `test_metadata_service.py` (MED-09)
  - `test_dark_mode_elevation_shadows` in `test_frontend.py` (MED-10)
- **Legacy File Integrity:** 100% byte-for-byte preserved (`app.py`, `music_fixer.py`, `templates/index.html`, `ffmpeg.exe`).

---

## 3. Phase 4 Sprint 2 Status Matrix

| Task ID | Component | Issue Addressed | Status | Implementation Details |
| :--- | :--- | :--- | :--- | :--- |
| **CRIT-01** | Database / Concurrency | Repeated `init_db()` DDL execution on connection | **FIXED** | Implemented `_INITIALIZED_DATABASES` set cache and `ensure_db_initialized()` in `database.py` and `main.py`. |
| **CRIT-02** | Frontend / Resiliency | Unbounded SSE / status polling fallback | **FIXED** | Added bounded retries (`MAX_POLL_FAILURES=5`, `MAX_POLL_404_RETRIES=2`, `MAX_POLL_ATTEMPTS=180`) in `app.js`. |
| **HIGH-01** | Security / SSRF | Secondary DNS rebinding / TOCTOU window in yt-dlp | **FIXED** | Added pre-send `UrllibHandler._send`/`send` validation hook calling `validate_url(req_url, resolve_dns=True)`. |
| **HIGH-02** | Engine / Storage | Windows reserved device names in filenames | **FIXED** | Added `WINDOWS_RESERVED_NAMES_REGEX` and `_` prefixing in `sanitizer.py` (`sanitize_filename`, `format_track_filename`, `safe_path_join`). |
| **HIGH-03** | UX & Engine | Empty playlist selection downloads entire playlist | **FIXED** | Disabled download button on empty selection in `app.js`, rejected with HTTP 400 in `endpoints.py`, and set `playlist_items="0"` in `ytdlp_engine.py`. |
| **HIGH-04** | Frontend / CSS | Playlist checklist UI lacks max-height constraints | **FIXED** | Added `.playlist-checklist-container`, `.playlist-items-list` (`max-height: 280px; overflow-y: auto;`) and custom scrollbars in `styles.css`. |
| **HIGH-05** | Database / Schema | `tracks` table missing UNIQUE constraint | **FIXED** | Added `UNIQUE(job_id, track_index)` to `tracks` table and `SCHEMA_SQL`, added migration in `init_db`, and used `ON CONFLICT DO UPDATE` in `add_track_to_job`. |
| **HIGH-06** | Engine / Concurrency | Uninterruptible `time.sleep` in retry backoff loop | **FIXED** | Replaced `time.sleep` with `context.cancel_event.wait(timeout=sleep_duration)` and added configurable `RETRY_BACKOFF_BASE_SECONDS`. |
| **HIGH-07** | Security / Reverse Proxy | Reverse proxy trust not configurable (`X-Forwarded-For` spoofing) | **FIXED** | Added `TRUSTED_PROXIES` in `config.py` and implemented `extract_client_ip()` in `endpoints.py` to only trust forwarded headers from approved proxies. |
| **MED-01** | Backend / Memory | RateLimiter unbounded client history leak | **FIXED** | Added `max_tracked_clients=10000`, `_prune_expired_locked()`, and automatic pruning in `RateLimiter` (`job_manager.py`). |
| **MED-02** | Engine / Compatibility | Mutagen ID3v2.4 Windows Explorer incompatibility | **FIXED** | Enforced `v2_version=3` in `_tag_mp3()` (`audio_tagger.py`), enabling native Windows Explorer metadata display. |
| **MED-03** | Engine / Metadata | Missing WAV RIFF/ID3 audio tagging | **FIXED** | Added `_tag_wav()` using `mutagen.wave.WAVE` and ID3 chunk tagging in `audio_tagger.py`. |
| **MED-04** | Engine / Packaging | Multi-file non-playlist download drops tracks | **FIXED** | Packaged multiple output files into ZIP archive if `is_playlist or len(final_files) > 1` in `job_manager.py`. |
| **MED-05** | Frontend / Assets | Missing browser favicon causing 404 spam | **FIXED** | Added `app/static/img/favicon.svg`, linked in `index.html`, and added `/favicon.ico` route in `main.py`. |
| **MED-06** | Accessibility / WCAG | `#url-input` missing accessible label | **FIXED** | Added `<label for="url-input" class="sr-only">`, `aria-label`, and `.sr-only` CSS utility in `index.html` and `styles.css`. |
| **MED-07** | Accessibility / UX | Format chips lack radio group semantics | **FIXED** | Added `role="radiogroup"`, `role="radio"`, `aria-checked`, and keyboard arrow navigation in `index.html` and `app.js`. |
| **MED-08** | Accessibility / Telemetry| Dynamic progress/status lack ARIA live regions | **FIXED** | Added `role="status"` and `aria-live="polite"` on `#dl-status-text`/`#progress-percent` and `role="alert"`/`aria-live="assertive"` on `#error-message`. |
| **MED-09** | Engine / Memory | Uncapped flat metadata extraction memory spike | **FIXED** | Added `"playlistend": settings.MAX_PLAYLIST_ITEMS` in `extract_media_info()` in `ytdlp_engine.py`. |
| **MED-10** | CSS / Theming | Missing dark mode shadows & scrollbars | **FIXED** | Added dark mode `--shadow-sm/md/lg` tokens and `color-scheme: dark` in `styles.css`. |

---

## 4. Phase 5 Feature 1 — Download Profiles Matrix

| Component | Feature Specification | Status | Implementation Details |
| :--- | :--- | :--- | :--- |
| **Taxonomy** | Core Profile Enum & Semantics | **COMPLETED** | Added `DownloadProfile` enum (`AUDIOPHILE`, `STANDARD`, `SPACE_SAVER`, `RAW_VIDEO`) and `PROFILE_TAXONOMY` in `app/core/constants.py`. |
| **Database** | Profile Persistence & Migration | **COMPLETED** | Added `profile TEXT NOT NULL DEFAULT 'standard'` to `jobs` table schema, migration in `init_db()`, and updated `create_job()` in `app/db/repository.py`. |
| **Engine / ytdlp** | Profile-driven options assembly | **COMPLETED** | Updated `build_ydl_options()` and `execute_download()` in `app/engine/ytdlp_engine.py` to configure format selectors and postprocessors per profile. |
| **Engine / Packaging** | Support video containers in ZIP | **COMPLETED** | Expanded `MEDIA_EXTENSIONS` in `app/engine/archive_packager.py` to include `.mp4`, `.mkv`, and `.webm`. |
| **Engine / Tagging** | Support MP4 video metadata | **COMPLETED** | Updated `tag_audio_file()` in `app/engine/audio_tagger.py` to support `.mp4` containers via Mutagen `MP4`. |
| **Job Manager** | Pipeline lifecycle for video & audio | **COMPLETED** | Updated `submit_job()`, `_run_job_with_retries()`, and `_execute_job_pipeline()` in `app/services/job_manager.py` for profile resolution, scratchpad media discovery, and tagging. |
| **API Endpoints** | REST endpoints & validation | **COMPLETED** | Added `GET /api/v1/profiles`, added `profile` field with `@field_validator` in `JobSubmitRequest`, and supported `video/mp4` MIME delivery in `app/api/v1/endpoints.py`. |
| **Frontend UI** | Download Profile selection panel | **COMPLETED** | Added accessible chips with `role="radiogroup"` / `role="radio"` in `index.html`, grid styles in `styles.css`, and selection + keyboard navigation in `app.js`. |
| **Testing** | Automated regression coverage | **COMPLETED** | Created `tests/test_profiles.py` (17 tests) and added frontend tests in `tests/test_frontend.py`. |

---

## 5. Phase 5 Feature 2 — Metadata & Artwork Editor Matrix

| Component | Feature Specification | Status | Implementation Details |
| :--- | :--- | :--- | :--- |
| **Model** | Strongly Validated Override Model | **COMPLETED** | Created `MetadataOverride` in `app/models/metadata.py` with Title, Artist, Album, Year (1000..2100), and Artwork validation. |
| **Security** | Safe Artwork Decoding & Isolation | **COMPLETED** | Implemented `validate_and_decode_artwork` and `save_artwork_to_isolated_temp` with size limits (10MB), MIME/magic-byte checks (JPEG/PNG/WEBP), and job-scoped scratchpad isolation. |
| **Precedence** | Tagging Precedence Integration | **COMPLETED** | Updated `_execute_job_pipeline` in `app/services/job_manager.py` enforcing User Override > Scraped yt-dlp > Fallback defaults. |
| **Tagging** | Year Tagging Support | **COMPLETED** | Extended `tag_audio_file()` in `app/engine/audio_tagger.py` to tag release year across MP3 (TYER/TDRC), M4A (`©day`), FLAC (`date`), Opus (`date`), and WAV. |
| **API** | Request Contract Extension | **COMPLETED** | Added `metadata_overrides` and `track_overrides` fields with `@field_validator` in `JobSubmitRequest` (`app/api/v1/endpoints.py`). |
| **Frontend** | Metadata Review & Artwork Editor UI | **COMPLETED** | Added editable Title, Artist, Album, Year fields, drag-and-drop / upload artwork dropzone, restore buttons, and playlist track switching in `index.html`, `styles.css`, and `app.js`. |
| **Testing** | Comprehensive Automated Test Suite | **COMPLETED** | Created `tests/test_metadata_editor.py` with unit and integration tests covering model validation, artwork security, precedence, tagging, and API delivery. |

---

## 6. Phase 5 Feature 3 — Persistent Download Library & History Matrix

| Component | Feature Specification | Status | Implementation Details |
| :--- | :--- | :--- | :--- |
| **Database** | Paginated & Filtered Query Aggregation | **COMPLETED** | Added `list_jobs_paginated()` in `app/db/repository.py` with parameterized search (title/URL/ID), status and profile filtering, pagination limit/offset, and `COUNT(t.id)` track aggregation. |
| **API / List** | `GET /api/v1/jobs` | **COMPLETED** | Added paginated list endpoint with query filters (`page`, `page_size`, `status`, `profile`, `q`), total items/pages metadata, and internal path redaction. |
| **API / Detail** | `GET /api/v1/jobs/{id}` | **COMPLETED** | Sanitized error messages, verified storage file existence (`file_available`), generated download link, and included ordered playlist tracks. |
| **API / Retry** | `POST /api/v1/jobs/{id}/retry` | **COMPLETED** | Added retry/requeue endpoint recreating download jobs with original parameters, rate limiting, and 400 rejection for active in-flight jobs. |
| **Security** | Internal Path Leak Protection | **COMPLETED** | Redacted raw server `file_path` from API responses; enforced `is_relative_to(settings.COMPLETED_DIR.resolve())` confinement for `file_available` check. |
| **Frontend UI** | Library Table, Toolbar & Pagination | **COMPLETED** | Added `#library` section in `index.html`, responsive styling in `styles.css`, and search/filter/pagination controller in `app.js`. |
| **Frontend UX** | Details Modal & Dynamic Actions | **COMPLETED** | Added modal dialog inspecting full job details & tracks, debounced search (300ms) with out-of-order response guard, Purged status indicators, and Retry action buttons. |
| **Testing** | Comprehensive Automated Test Suite | **COMPLETED** | Created `tests/test_library.py` covering repository aggregation, API pagination, search/filtering, file availability detection, retry guards, and template contracts. |


