# SONORA — CHANGELOG

All notable changes to the SONORA platform are documented in this file.

## [4.0.0-phase6] - 2026-09-28

### Phase 6: Public Web / Google Search / Production Readiness
- **Production Observability & Probes (`app/main.py`):**
  - Added `/healthz` liveness probe endpoint returning lightweight HTTP 200 health confirmation.
  - Added `/readyz` readiness probe endpoint performing real-time health checks on SQLite database connectivity, storage scratchpad write access, and threadpool worker health.
- **Search Engine Optimization & Indexability (`app/main.py`, `app/static/index.html`):**
  - Added `/robots.txt` endpoint dynamically generating crawl rules that explicitly disallow private `/api/` and `/data/` paths while declaring canonical sitemap location.
  - Added `/sitemap.xml` endpoint serving valid XML referencing only public canonical endpoints (`/`, `/privacy`, `/terms`).
  - Added canonical `<link rel="canonical">`, Open Graph, Twitter Cards, and Schema.org JSON-LD `@graph` (`SoftwareApplication`, `WebSite`) structured data.
- **Defense-in-Depth Security Headers (`app/main.py`):**
  - Added HTTP middleware injecting `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, and `Cross-Origin-Opener-Policy: same-origin`.
  - Added `X-Robots-Tag: noindex, nofollow, noarchive` on all `/api/*` and `/data/*` responses to ensure zero search engine indexing of private jobs or downloads.
- **Public Informational Sections & Legal Pages (`app/static/index.html`, `app/static/css/styles.css`, `app/static/js/app.js`):**
  - Added public *How It Works* step breakdown, *Download Profiles & Codec Fidelity* showcase, and *Trust & Privacy* statements into initial HTML.
  - Added accessible modal dialogs and dedicated routes (`/privacy`, `/terms`) for Privacy Policy, Terms of Service, and DMCA Copyright Guidance.
- **Containerization & Deployment (`Dockerfile`, `.dockerignore`, `docker-compose.yml`):**
  - Created multi-stage Debian-slim `Dockerfile` with system FFmpeg, non-root user `sonora`, `/healthz` container healthcheck, volume mounts for `/app/data`, and optimized production `uvicorn` entrypoint.
  - Configured production `docker-compose.yml` and `.dockerignore`.
- **Continuous Integration (`.github/workflows/ci.yml`):**
  - Created GitHub Actions CI workflow running Ruff linting and pytest automated testing on Python 3.12.
- **Automated Test Suite (`tests/test_production_readiness.py`):**
  - Created test suite validating liveness/readiness probes, robots.txt, XML sitemaps, security headers, X-Robots-Tag directives, JSON-LD schemas, and legal routes.

## [3.7.0-phase5.feature3] - 2026-09-28

### Phase 5 / Feature 3: Persistent Download Library & History
- **Database Repository Query Aggregation (`app/db/repository.py`):**
  - Added `list_jobs_paginated()` supporting limit/offset pagination, status filtering, profile filtering, parameterized search matching title/url/id, and `COUNT(t.id) AS track_count` aggregation.
- **REST Endpoints & Path Confinement Security (`app/api/v1/endpoints.py`):**
  - Added `GET /api/v1/jobs` delivering paginated job items with pagination metadata (`page`, `page_size`, `total_items`, `total_pages`, `has_next`, `has_prev`).
  - Redacted internal raw filesystem `file_path` from API payloads to prevent internal server path leakage.
  - Implemented `_check_file_availability()` with strict `is_relative_to(settings.COMPLETED_DIR.resolve())` confinement, exposing `file_available: bool` and `download_url: str | None`.
  - Updated `GET /api/v1/jobs/{job_id}` to include sanitized error messages, file availability flags, and ordered playlist tracks.
  - Added `POST /api/v1/jobs/{job_id}/retry` to safely requeue failed, cancelled, or completed download jobs with preserved parameters and track selections, while guarding against retrying in-flight active jobs.
- **Frontend UI & Interactive Experience (`app/static/index.html`, `app/static/css/styles.css`, `app/static/js/app.js`):**
  - Added `#library` section in navigation and main content area.
  - Implemented search input with 300ms debounce and stale response prevention.
  - Implemented status and profile filter dropdowns, manual refresh button, and responsive table list view.
  - Implemented Job Details & Tracklist modal dialog inspecting comprehensive job metadata, error traces, and playlist items.
  - Added dynamic row actions for direct file downloads, Purged indicators for storage-cleaned jobs, and one-click Retry buttons that switch into downloading state.
- **Automated Regression Test Suite (`tests/test_library.py`):**
  - Created test suite verifying repository pagination/filtering/aggregation, API endpoints, file availability checking, retry validation/rate limiting, and frontend template contracts.

## [3.6.0-phase5.feature2] - 2026-09-28

### Phase 5 / Feature 2: Pre-Download Metadata & Artwork Editor
- **Metadata Override Model (`app/models/metadata.py`):**
  - Implemented `MetadataOverride` Pydantic model supporting optional `title`, `artist`, `album`, `year` (1000..2100), and `artwork` (base64/data URL).
  - Implemented ASCII control character stripping preserving international Unicode song titles and artists.
  - Implemented safe base64 decoding with strict 10MB payload size limits and magic-byte validation (JPEG, PNG, WEBP).
  - Implemented `save_artwork_to_isolated_temp()` ensuring uploaded images are confined to job-isolated scratchpads.
- **Audio Tagging Year Support (`app/engine/audio_tagger.py`):**
  - Added release year tag embedding across all supported audio containers: MP3 (`TYER`/`TDRC`), M4A (`©day`), FLAC (`date`), Opus (`date`), and WAV (`TYER`).
- **Job Pipeline & Tagging Precedence (`app/services/job_manager.py`):**
  - Updated `submit_job()`, `_run_job_with_retries()`, and `_execute_job_pipeline()` to accept `metadata_overrides` and `track_overrides`.
  - Enforced strict metadata precedence: User Override > Scraped yt-dlp Metadata > Default Fallback.
  - Ensured temporary custom artwork is stored in job-scoped temp directory and cleaned up safely upon job completion, failure, or cancellation.
- **API Request Contract (`app/api/v1/endpoints.py`):**
  - Extended `JobSubmitRequest` with optional `metadata_overrides` and `track_overrides` fields while maintaining full backward compatibility with legacy requests.
- **Frontend Review & Editor UI (`app/static/index.html`, `app/static/css/styles.css`, `app/static/js/app.js`):**
  - Replaced immediate auto-download flow with interactive Pre-Download Metadata Review & Editor.
  - Added editable form fields for Track Title, Artist, Album, and Year with Revert to Detected button.
  - Added interactive Album Cover Dropzone with drag & drop support, file picker, live thumbnail preview, and original artwork restoration.
  - Added playlist track switching for individual track metadata review while preserving multi-track selection for batch downloads.
- **Automated Regression Test Suite (`tests/test_metadata_editor.py`):**
  - Added comprehensive test suite covering validation models, image magic bytes, isolated temp storage, tagging precedence, year embedding, API payloads, and frontend DOM semantics.

## [3.5.0-phase5.feature1] - 2026-09-28

### Phase 5 / Feature 1: Download Profiles Implementation
- **Core Profile Taxonomy:** Added `DownloadProfile` enum (`audiophile`, `standard`, `space_saver`, `raw_video`) and `PROFILE_TAXONOMY` metadata mapping specifications in `app/core/constants.py`.
- **Database Schema & Persistence:** Added `profile TEXT NOT NULL DEFAULT 'standard'` column to `jobs` table in `app/db/repository.py:SCHEMA_SQL` and column migration in `init_db(conn)`. Updated `create_job()` to accept and persist `profile`.
- **Engine / yt-dlp Options Assembly:** Updated `build_ydl_options()` and `execute_download()` in `app/engine/ytdlp_engine.py` to support profile-driven options:
  - `AUDIOPHILE`: `format="bestaudio/best"`, `preferredcodec="flac"`
  - `STANDARD`: `format="bestaudio/best"`, `preferredcodec="mp3"`, `preferredquality="320"`
  - `SPACE_SAVER`: `format="bestaudio[ext=m4a]/bestaudio[acodec=aac]/bestaudio/best"`, `preferredcodec="m4a"`, `preferredquality="128"`
  - `RAW_VIDEO`: `format="bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"`, `merge_output_format="mp4"`, no audio extraction
  - Preserved backward compatibility when `profile` is omitted.
- **Video Packaging & Audio Tagging:**
  - Expanded `MEDIA_EXTENSIONS` in `app/engine/archive_packager.py` and scratchpad discovery in `app/services/job_manager.py` to support `.mp4`, `.mkv`, and `.webm`.
  - Added `.mp4` container tagging support in `app/engine/audio_tagger.py:tag_audio_file()`.
- **API Endpoints & Validation:**
  - Added `GET /api/v1/profiles` endpoint delivering full profile taxonomy and metadata.
  - Added `profile` field with `@field_validator` in `JobSubmitRequest` (`app/api/v1/endpoints.py`).
  - Added `video/mp4` and `video/x-matroska` MIME type handling in `download_job_file`.
- **Frontend UI & Accessibility:**
  - Added Download Profile selector chips in `app/static/index.html` with `role="radiogroup"`, `role="radio"`, and dynamic descriptions.
  - Implemented responsive `.profile-grid` and `.profile-chip` styles in `app/static/css/styles.css`.
  - Added profile selection, keyboard arrow navigation, and profile inclusion in `/api/v1/jobs` payload in `app/static/js/app.js`.
- **Automated Tests:**
  - Created `tests/test_profiles.py` with 17 unit and integration tests.
  - Added `test_download_profiles_dom_semantics_and_styles` in `tests/test_frontend.py`.

## [3.4.0-phase4.sprint2.batch3] - 2026-09-28

### Medium-Priority Production Hardening
- **MED-01 (RateLimiter Memory Growth & Pruning):** Added bounded storage (`max_tracked_clients=10000`)
  and automatic periodic pruning of stale timestamps in `RateLimiter` (`app/services/job_manager.py`),
  preventing long-term memory bloat. Added unit tests in `tests/test_quota_enforcement.py`.
- **MED-02 (ID3v2.3 MP3 Windows Explorer Compatibility):** Configured `v2_version=3` when saving MP3
  metadata in `app/engine/audio_tagger.py:_tag_mp3()`, resolving ID3v2.4 parsing incompatibility in
  Windows Explorer and legacy players. Added regression test in `tests/test_audio_tagger.py`.
- **MED-03 (WAV RIFF/ID3 Tagging Support):** Implemented `_tag_wav()` using `mutagen.wave.WAVE` and
  ID3 chunks in `app/engine/audio_tagger.py`, embedding Title, Artist, Album, and Cover Art into WAV
  downloads. Added regression test in `tests/test_audio_tagger.py`.
- **MED-04 (Multi-File Non-Playlist ZIP Packaging):** Updated `_execute_job_pipeline()` in
  `app/services/job_manager.py` to automatically package all generated audio files into a ZIP archive
  whenever `is_playlist or len(final_files) > 1`. Added regression test in `tests/test_job_manager.py`.
- **MED-05 (Browser Favicon & 404 Prevention):** Created modern brand SVG favicon
  `app/static/img/favicon.svg`, linked it in `app/static/index.html`, and added `/favicon.ico` route
  in `app/main.py`. Added regression test in `tests/test_frontend.py`.
- **MED-06 (URL Input Accessibility & Screen Reader Label):** Added `<label for="url-input" class="sr-only">`,
  `aria-label`, and `.sr-only` CSS utility in `index.html` and `styles.css`. Added regression test
  in `tests/test_frontend.py`.
- **MED-07 (Format Chips Radiogroup Semantics & Arrow Navigation):** Added `role="radiogroup"`,
  `role="radio"`, and `aria-checked` to format options in `index.html`. Implemented arrow key navigation
  (`ArrowRight`, `ArrowLeft`, `ArrowDown`, `ArrowUp`) and roving `tabindex` in `app/static/js/app.js`.
  Added regression test in `tests/test_frontend.py`.
- **MED-08 (Dynamic Status & Error ARIA Live Regions):** Added `role="status"` and `aria-live="polite"`
  on `#dl-status-text` and `#progress-percent`, `role="progressbar"` on `#progress-bar-track`, and
  `role="alert"` / `aria-live="assertive"` on `#error-message`. Added test in `tests/test_frontend.py`.
- **MED-09 (Uncapped Metadata Extraction Cap):** Added `"playlistend": settings.MAX_PLAYLIST_ITEMS` in
  `extract_media_info()` (`app/engine/ytdlp_engine.py`), guarding against memory exhaustion on large
  playlists. Added test in `tests/test_metadata_service.py`.
- **MED-10 (Dark Mode Depth & Elevation Tokens):** Added `--shadow-sm/md/lg` tokens and
  `color-scheme: dark;` to `[data-theme="dark"]` in `app/static/css/styles.css`. Added regression test
  in `tests/test_frontend.py`.

## [3.3.0-phase4.sprint2.batch2] - 2026-09-27

### High-Priority Security & Edge Case Hardening
- **HIGH-01 (Secondary DNS Rebinding / Pre-Send Validation):** Enhanced `install_ssrf_redirect_protection()` in `app/engine/ytdlp_engine.py` to hook `yt_dlp.networking._urllib.UrllibHandler` (`_send`/`send`) to perform pre-send hostname resolution and CIDR validation via `validate_url(req_url, resolve_dns=True)`. Added regression test in `tests/test_api.py`.
- **HIGH-02 (Windows Reserved Device Names Protection):** Added `WINDOWS_RESERVED_NAMES_REGEX` matching `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9` in `app/engine/sanitizer.py`. Safely prefixed matching filenames with an underscore in `sanitize_filename()`, `format_track_filename()`, and `safe_path_join()`, preventing Win32 device name collision crashes. Added comprehensive tests in `tests/test_sanitizer.py`.
- **HIGH-03 (Empty Playlist Selection Prevention):** Fixed logic where deselecting all playlist items downloaded the full playlist. In `app/static/js/app.js`, disabled the download button when 0 items are selected. In `app/api/v1/endpoints.py`, rejected empty `selected_indices` with HTTP 400 `INVALID_URL`. In `app/engine/ytdlp_engine.py`, explicitly configured `opts["playlist_items"] = "0"` when an empty list is passed. Added regression tests in `tests/test_api.py` and `tests/test_frontend.py`.
- **HIGH-04 (Playlist Checklist Layout Constraints):** Implemented `.playlist-checklist-container`, `.checklist-header`, and `.playlist-items-list` with `max-height: 280px; overflow-y: auto;` and styled custom scrollbars in `app/static/css/styles.css`, preventing unbounded vertical growth on large playlists. Added regression test in `tests/test_frontend.py`.
- **HIGH-05 (Tracks Table Uniqueness & Idempotent Upsert):** Added `UNIQUE(job_id, track_index)` constraint and `idx_tracks_job_track` unique index in `app/db/repository.py:SCHEMA_SQL`. Added migration in `init_db(conn)` and upgraded `add_track_to_job()` to use `ON CONFLICT(job_id, track_index) DO UPDATE`, preventing duplicate track records on retry. Added regression test in `tests/test_database.py`.
- **HIGH-06 (Cancellation-Aware Retry Backoff):** Replaced uninterruptible `time.sleep` in `app/services/job_manager.py:_run_job_with_retries()` with `context.cancel_event.wait(timeout=sleep_duration)`, allowing instant cancellation response and rapid worker shutdown during retry backoff. Added configurable `settings.RETRY_BACKOFF_BASE_SECONDS` and regression test in `tests/test_job_manager.py`.
- **HIGH-07 (Reverse Proxy Client IP Trust & Spoofing Defense):** Added `TRUSTED_PROXIES` configuration setting in `app/core/config.py` with comma-separated validator. Implemented `extract_client_ip()` in `app/api/v1/endpoints.py` to safely inspect `X-Forwarded-For` and `X-Real-IP` only when connecting from trusted proxies. Added regression test in `tests/test_api.py`.

## [3.2.0-phase4.sprint2.batch1] - 2026-09-27

### Reliability & Concurrency Hardening
- **CRIT-01 (Database Schema DDL Contention):** Eliminated repeated schema initialization DDL calls (`init_db`) on every database connection acquisition in `app/db/database.py`. Implemented thread-safe `_INITIALIZED_DATABASES` set cache and upfront schema initialization in `app/main.py:lifespan()`. Added regression test `test_schema_init_db_runs_only_once_per_database_path` in `tests/test_database.py`.
- **CRIT-02 (Frontend Bounded SSE Polling Fallback):** Resolved unbounded polling loop in `app/static/js/app.js:startPollingFallback()`. Enforced strict boundaries: `MAX_POLL_404_RETRIES = 2`, `MAX_POLL_FAILURES = 5`, and `MAX_POLL_ATTEMPTS = 180` (6 minutes maximum duration), with guaranteed cleanup in `cancelDownload()`. Added regression test `test_sse_polling_fallback_bounded_retries` in `tests/test_frontend.py`.

## [3.1.0-phase4.sprint1] - 2026-09-23

### Security & Hardening
- **CRIT-01 (SSE Progress Event Attribute Crash):** Corrected `stream_job_events` attribute mapping in `endpoints.py` to match `ProgressEvent` canonical dataclass fields (`stage`, `speed_bytes`, `current_track`, `track_index`). Added clean termination upon entering terminal states.
- **CRIT-02 (DOM XSS in Playlist Rendering):** Replaced `innerHTML` injection in `renderPlaylistItems()` in `app.js` with safe programmatic DOM node creation and `textContent` assignment, neutralizing script injection vectors from untrusted metadata.
- **CRIT-03 (Application Shutdown Lifecycle):** Updated FastAPI `lifespan` in `main.py` to invoke `get_job_manager().shutdown(wait=True)` and `janitor.join(timeout=5.0)`, preventing abandoned background threads and child processes upon server shutdown.
- **CRIT-04 (Secondary SSRF & Redirect Protection):** Wired `validate_redirect()` into `yt-dlp` redirect handler via `install_ssrf_redirect_protection()`, scoped to execution time to eliminate global monkeypatching of standard library `urllib`.
- **CRIT-05 (CORS Policy Hardening):** Removed unsafe `allow_origins=["*"]` + `allow_credentials=True` combination. Implemented configurable `CORS_ORIGINS` whitelist, safe credentials handling, and comma-separated string parsing in `config.py` and `main.py`.
- **CRIT-06 (Vulnerable Multipart Dependency):** Upgraded `python-multipart` from `0.0.12` to `>=0.0.20` in `requirements.txt` and `pyproject.toml` to remediate CVE-2024-53981 and header DoS risks.
- **CRIT-07 (Metadata Inspection Deadlock):** Added `AbortController` with a 15-second bounded timeout and a user-facing Cancel button (`#cancel-inspecting-btn`) in `app.js` and `index.html`.
- **HIGH-02 (File Delivery Directory Confinement):** Added path resolution confinement validation in `download_job_file` in `endpoints.py`, ensuring requested files strictly reside within `settings.COMPLETED_DIR`.
- **HIGH-06 (Double-Submit Network Race Conditions):** Disabled `#submit-btn` and `#start-download-btn` during active network requests with visual state feedback to prevent redundant job creation.
- **HIGH-07 (CSS Syntax Error):** Fixed unclosed brace on `.feature-icon` in `styles.css` that corrupted `.mobile-menu-btn`.
- **TEST-ISOLATION (Test Database Isolation & Thread Safety):** Added autouse `isolate_test_environment` fixture in `tests/conftest.py` ensuring all tests operate strictly in `tmp_path`, with teardown cancellation of active `JobContext` instances. Mocked threadpool execution in endpoint tests to prevent background worker thread leakage, yt-dlp retry loops, and I/O exceptions on closed log streams.
- **AUDIT-01 (Rate Limit Test Worker Leakage):** Mocked `job_mgr._executor.submit` in `tests/test_quota_enforcement.py` to prevent background threads from reaching real YouTube endpoints during rate limit assertions.
- **AUDIT-02 (Urllib Monkeypatch Contamination):** Removed global `urllib.request` handler monkeypatching; restricted redirect validation to `yt-dlp` execution and documented TOCTOU DNS rebinding boundary.
- **AUDIT-03 (SSE Stream Timing Flakiness):** Replaced static event emission with registration callback hook in `tests/test_api.py`, ensuring 100% deterministic SSE event delivery.
- **AUDIT-04 (SSE Database Fallback Schema Parity):** Aligned keys in database fallback events (`stage`, `current_title`, `current_track`, `total_tracks`, `completed_tracks`, `track_index`) with canonical `ProgressEvent` schema in `endpoints.py`.
- **AUDIT-07 (Comma-Separated CORS Environment Parsing):** Added Pydantic `field_validator` in `config.py` to parse comma-separated `CORS_ORIGINS` environment variables cleanly into `list[str]`.
- **AUDIT-08 (Worker Abandonment on Test Shutdown):** Updated all test fixture shutdowns (`test_job_manager.py`, `test_quota_enforcement.py`) from `wait=False` to `wait=True`.
- **REGRESSION-TESTS:** Added 4 new regression tests in `tests/test_api.py` covering database fallback schema, CORS parsing, urllib isolation, and yt-dlp redirect protection. Maintained 0 Ruff linter errors.

## [3.0.0-phase3.m10] - 2026-09-22

### Added
- **Full SONORA Phase 3 Web Experience:**
  - Swiss-inspired typography, minimal aesthetics, warm off-white background (`#F9F8F6`), and elevated white cards.
  - Startup Animation: 4-cord acoustic harmonic SVG curves, wordmark reveal, subtitle reveal, and full `prefers-reduced-motion` compliance.
  - Complete Landing Page: Sticky header, responsive navigation, mobile drawer menu, feature grid, supported sites, FAQ accordion, and semantic footer.
  - Honest Format & Quality Selection: Transcoded MP3 (320kbps, 256kbps, VBR V0), Direct Stream Copy (M4A AAC, Opus), and FLAC container.
  - Playlist Queue Experience: Track checklist with individual item checkboxes, Select All / Deselect All toggle, live counter, and ZIP delivery.
  - Real-Time Telemetry: Server-Sent Events (`/api/v1/jobs/{id}/events`) with live progress bar %, download speed (MB/s), ETA (s), and polling fallback.
  - State Management: Cooperative cancellation, error sanitization cards (no internal path or raw traceback leakage), and reset flows.
  - Full Mobile & Accessibility Support: 375px/768px/1280px responsive viewports, touch targets ≥ 44px, `:focus-visible` focus rings, and ARIA attributes.
  - Automated Frontend & API Test Suite: 90/90 passing automated pytest unit/integration tests with 0 Ruff linter errors.

## [3.0.0-phase3.m1] - 2026-09-22

### Added
- **FastAPI ASGI Server (`app/main.py`):** Mounted static directory, CORS middleware, API v1 router, and background lifecycles for JobManager and Janitor.
- **REST & SSE Endpoints (`app/api/v1/endpoints.py`):**
  - `POST /api/v1/metadata`: pre-flight SSRF check & tracklist discovery.
  - `POST /api/v1/jobs`: download task dispatch with rate limiting & quota checks.
  - `GET /api/v1/jobs/{id}`: status and telemetry query.
  - `POST /api/v1/jobs/{id}/cancel`: cooperative cancellation token trigger.
  - `GET /api/v1/jobs/{id}/events`: real-time SSE stream.
  - `GET /api/v1/downloads/{id}/file`: safe completed file delivery.
- **SONORA Single-Page App (`app/static/index.html`):** Complete semantic HTML shell with startup overlay, hero, state views, and features.
- **Swiss Design System (`app/static/css/styles.css`):** Light/dark CSS tokens, typography hierarchy, responsive grids, and animation keyframes.
- **State Machine Controller (`app/static/js/app.js`):** Client-side state transitions, SSE listener, theme toggle, and playlist selector.
- **Automated Integration Tests (`tests/test_api.py`):** 7 comprehensive endpoint tests verifying web delivery, SSRF rejection, and lifecycle queries.

### Fixed
- Fixed SQLite WAL concurrency transactions (`get_db_read` vs `get_db_write`).
- Fixed zombie startup recovery and Janitor decoupled deletions.
- Fixed YouTube WebP to JPEG thumbnail conversion before ID3 tagging.
- Fixed native M4A and Opus stream copying without re-encoding loss.
- Fixed composite playlist monotonic progress calculation.
