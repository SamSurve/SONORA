# SONORA — CHANGELOG

All notable changes to the SONORA platform are documented in this file.

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
