# SONORA — CHANGELOG

All notable changes to the SONORA platform are documented in this file.

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
