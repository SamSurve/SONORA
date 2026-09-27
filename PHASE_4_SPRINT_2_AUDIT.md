# SONORA — PHASE 4 SPRINT 2: FULL PRODUCTION READINESS AUDIT

**Audit Date:** September 2026  
**Auditor:** Antigravity Autonomous Agent (Google DeepMind Advanced Agentic Coding)  
**Current Git Checkpoint:** `0238f5a` (`fix: complete phase 4 sprint 1 hardening`)  
**Previous Baseline:** `5ebfc9c` (`feat: complete SONORA phase 3 product build`)  
**Repository State:** Clean working tree, 102/102 tests passing, Ruff clean (0 errors), `git diff --check` clean  
**Audit Mode:** **READ-ONLY AUDIT** (Zero modifications to production source code, tests, or legacy files)

---

## A. EXECUTIVE SUMMARY

Following the successful completion, test pass (102/102 tests), and Git push of Phase 4 Sprint 1 (`0238f5a`), this deep audit evaluated the entire SONORA repository to determine what remains before it can be considered a full-fledged, battle-tested, enterprise-grade production application.

### Key Takeaways
1. **Architectural Foundations are Strong:** The modern architecture (FastAPI ASGI, SQLite WAL with `BEGIN IMMEDIATE` write reservations, isolated thread pool worker dispatch, cooperative cancellation via `threading.Event`, isolated scratchpads, structured SSE telemetry, and sanitized error messages) is fundamentally sound.
2. **Not Yet Ready for Open Multi-Tenant Production:**
   - **Database Contention:** Schema DDL scripts (`init_db`) run on every connection creation, creating table lock contention under concurrent traffic.
   - **DNS Rebinding TOCTOU Gap:** Pre-flight DNS validation prevents direct private IP calls, but yt-dlp's internal network stack executes an unpinned secondary DNS resolution during downloads.
   - **Frontend Playlist & Polling Bugs:** Playlist checklist elements are completely unstyled in CSS, causing vertical viewport blowout; deselecting all tracks results in downloading the entire playlist; and the SSE fallback polls indefinitely without a maximum retry cap.
   - **Windows Device Name Traps:** Filename sanitization does not filter Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`), causing uncaught OS crashes on specific tracks.
   - **Deployment Gaps:** Missing Dockerfile, missing CI/CD workflow, missing healthcheck (`/healthz`), missing static type checking (`mypy`), and lack of real browser integration testing.

---

## B. CURRENT ARCHITECTURE

```
                                [ Browser Client ]
                                        │
                         HTTP REST / SSE│ (EventSource)
                                        ▼
                        [ FastAPI ASGI Application ]
                        (lifespan startup/shutdown)
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           ▼                            ▼                            ▼
  [ /metadata Router ]          [ /jobs Router ]           [ /downloads Router ]
           │                            │                            │
           ▼                            ▼                            │
 [ Metadata Service ]           [ JobManager ]                       │
(yt-dlp extract_flat)           (Singleton Service)                  │
                                        │                            │
                     ┌──────────────────┴──────────────────┐         │
                     ▼                                     ▼         ▼
             [ SQLite (WAL) ]                     [ ThreadPoolExecutor ]
         (Jobs & Tracks Tables)                     (4 Worker Threads)
                                                           │
                                                           ▼
                                                  [ yt-dlp Download ]
                                                  (temp_dir scratchpad)
                                                           │
                                                           ▼
                                                  [ Mutagen Audio Tagger ]
                                                  (MP3, M4A, FLAC, Opus)
                                                           │
                                                           ▼
                                                  [ Archive Packager ]
                                                  (ZIP creation for playlists)
                                                           │
                                                           ▼
                                                  [ Storage Delivery ]
                                                  (data/completed/<job_id>)
```

### Component Breakdown
1. **FastAPI Lifespan (`app/main.py:28-54`):** Initializes storage directories, initializes the `JobManager` singleton (reconciling orphaned zombie jobs left by prior crashes), starts the background `JanitorDaemon`, and gracefully cancels and joins workers and janitor on shutdown (`shutdown(wait=True)`).
2. **Job Manager (`app/services/job_manager.py:130-655`):** Thread-safe job state machine, sliding-window `RateLimiter`, disk threshold checker, and `ThreadPoolExecutor` (default: 4 workers). Manages cooperative cancellation via `threading.Event`, progress listeners, and bounded exponential backoff retries (3 attempts).
3. **Download Engine (`app/engine/ytdlp_engine.py:83-286`):** Invokes `yt-dlp` in isolated temporary scratchpads (`data/temp/<job_id>`) with socket timeouts, allowed protocols (`http`, `https`), progress hooks, and custom redirect SSRF inspection.
4. **Media Processing & Tagging (`app/engine/audio_tagger.py:85-278`):** Injects ID3v2, MP4, FLAC, and Opus tags with embedded cover artwork.
5. **Storage & Janitor (`app/engine/janitor.py:20-194`):** Enforces disk space threshold (>2048 MB free), isolates scratchpads, and runs background TTL cleanup (60-minute cutoff), protecting active jobs.
6. **Database Layer (`app/db/database.py:15-85`, `app/db/repository.py:11-210`):** SQLite Write-Ahead Logging (WAL) with `PRAGMA busy_timeout = 5000` and `BEGIN IMMEDIATE` write reservations.

---

## C. PRODUCTION READINESS ASSESSMENT

| Engineering Dimension | Current Rating | Summary Status |
| :--- | :---: | :--- |
| **1. Architecture & Lifecycles** | `MOSTLY READY` | Robust startup/shutdown; clean cancellation. Bottleneck: DDL execution on every connection. |
| **2. Download Workflow & Integrity** | `MOSTLY READY` | Full lifecycle single-track & playlist download, tagging, packaging. Secondary DNS rebinding unpinned. |
| **3. Real-World Edge Cases** | `NEEDS WORK` | Handles common errors; crashes on Windows reserved names (`CON`, `AUX`); downloads all tracks on empty selection. |
| **4. Security & Threat Mitigation** | `MOSTLY READY` | Strict CIDR blacklists, obfuscated IP checks, redirect inspection, path traversal protection. DNS TOCTOU window remains. |
| **5. API Specifications & Contracts** | `READY` | Standardized REST envelope, accurate status codes, sanitized error strings. |
| **6. Database & Persistence** | `NEEDS WORK` | SQLite WAL mode protects data; DDL executed on every connection; `tracks` table missing UNIQUE constraint. |
| **7. Frontend & User Experience** | `NEEDS WORK` | Intuitive Swiss aesthetic; unstyled playlist container causes layout blowout; infinite polling fallback on 404/500; no favicon. |
| **8. Testing & QA Verification** | `MOSTLY READY` | 102 passing unit/integration tests with isolated temp DBs. 0% JavaScript/browser execution; large playlist stress tests missing. |
| **9. Performance & Scalability** | `MOSTLY READY` | Event loop unblocked; disk threshold gates. RateLimiter memory leak; table lock contention on concurrent writes. |
| **10. Deployment Readiness** | `MAJOR GAP` | No Dockerfile, no CI/CD pipeline, no `/healthz` endpoint, missing `mypy` static typing. |
| **11. Legacy Preservation** | `READY` | 100% byte-for-byte baseline preservation for all 4 protected files. |

---

## D. CRITICAL FINDINGS

### CRIT-01: SQLite Schema DDL Script Execution on Every Connection Acquisition
- **Severity:** 🚨 **CRITICAL**
- **File:** `app/db/database.py`
- **Location:** Lines 38–42 in `create_connection()`
- **Problem:**
  ```python
  # Idempotently ensure database schema exists
  from app.db.repository import init_db
  init_db(conn)
  ```
  `create_connection()` is called on every invocation of `get_db_read()` and `get_db_write()`. `init_db(conn)` executes `conn.executescript(SCHEMA_SQL)` (which parses and executes 6 DDL statements) and runs `PRAGMA table_info(jobs)`.
- **Why It Matters:** Under concurrent traffic (e.g. 10–20 active downloads reporting progress every second and multiple SSE polling queries), every thread executes DDL statements on SQLite. In SQLite, DDL statements acquire exclusive schema locks, causing massive thread contention, CPU spikes, and `sqlite3.OperationalError: database is locked`.
- **Recommended Fix:** Decouple `init_db(conn)` from `create_connection()`. Execute `init_db()` strictly once during application startup in `app/main.py:lifespan()`.
- **Affected Scope:** Production code (`app/db/database.py`, `app/main.py`).

---

### CRIT-02: Unbounded Frontend SSE Polling Fallback on Server/Job Errors
- **Severity:** 🚨 **CRITICAL**
- **File:** `app/static/js/app.js`
- **Location:** Lines 432–455 in `startPollingFallback()`
- **Problem:**
  ```javascript
  context.ssePollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/v1/jobs/${jobId}`);
      const json = await res.json();
      if (res.ok && json.data) {
        ...
      }
    } catch (e) { ... }
  }, 1500);
  ```
  If `/api/v1/jobs/${jobId}` returns HTTP 404 (job expired, invalid ID, or server restarted) or HTTP 500, `res.ok` is false. The code does NOT call `clearInterval(context.ssePollInterval)`. There is no retry limit or backoff.
- **Why It Matters:** The browser client continuously fires HTTP requests every 1.5 seconds indefinitely, hammering the backend server with requests for dead jobs.
- **Recommended Fix:** Add a failure counter in `startPollingFallback()`. If 5 consecutive non-200 responses occur, clear the interval, abort, and display an actionable error message to the user.
- **Affected Scope:** Production code (`app/static/js/app.js`).

---

## E. HIGH FINDINGS

### HIGH-01: Secondary DNS Rebinding / TOCTOU Window in yt-dlp Execution
- **Severity:** ⚠️ **HIGH**
- **File:** `app/services/job_manager.py` / `app/engine/ytdlp_engine.py`
- **Location:** `job_manager.py:240-245`, `ytdlp_engine.py:268-270`
- **Problem:** `validate_url(url, resolve_dns=True)` resolves the hostname and checks IPs against CIDR blacklists prior to job enqueuing. However, `yt-dlp`'s internal network stack executes its own secondary DNS resolution when downloading.
- **Why It Matters:** An attacker controlling a DNS server with TTL=0s can return a legitimate public IP on the first pre-flight check, and then return `127.0.0.1` or `169.254.169.254` during `yt-dlp`'s download execution, bypassing pre-flight SSRF protection.
- **Recommended Fix:** Implement socket-level IP pinning in `yt-dlp`'s urllib transport handler so that the socket connects only to the IP validated during the pre-flight check.
- **Affected Scope:** Production code (`app/engine/ytdlp_engine.py`).

---

### HIGH-02: Unhandled Windows Reserved Device Names in Filename Sanitizer
- **Severity:** ⚠️ **HIGH**
- **File:** `app/engine/sanitizer.py`
- **Location:** Lines 15–48 in `sanitize_filename()`
- **Problem:** `sanitize_filename()` strips invalid characters (`<>:"/\|?*`), but does not check for Windows reserved device names: `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`.
- **Why It Matters:** If a YouTube track title is `"CON"` or `"AUX"`, the sanitized output name will be `CON.mp3`. Attempting to create or write this file on Windows raises an uncaught `OSError: [Errno 22] Invalid argument` or `PermissionError`, crashing the job.
- **Recommended Fix:** Add a regex check against `^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$` (case-insensitive) and prepend an underscore (`_CON.mp3`).
- **Affected Scope:** Production code (`app/engine/sanitizer.py`).

---

### HIGH-03: Empty Playlist Track Selection Downloads All Tracks
- **Severity:** ⚠️ **HIGH**
- **File:** `app/static/js/app.js` / `app/engine/ytdlp_engine.py`
- **Location:** `app.js:332-340`, `ytdlp_engine.py:232-234`
- **Problem:** If a user unchecks all tracks in a playlist, `context.selectedTrackIndices` is `[]`. The "Start Download" button remains enabled. The frontend submits `{ "selected_indices": [] }`. In `build_ydl_options()`:
  ```python
  if is_playlist and selected_indices:
      opts["playlist_items"] = ",".join(str(i) for i in selected_indices)
  ```
  Because `[]` is falsy, `playlist_items` is omitted, causing `yt-dlp` to download the **entire playlist** instead of none.
- **Why It Matters:** Directly violates user intent; causes unwanted network usage, disk usage, and user confusion.
- **Recommended Fix:** Disable `#start-download-btn` in `app.js` whenever `selectedTrackIndices.length === 0`. In `JobSubmitRequest` on the backend, reject empty `selected_indices` when `is_playlist=True`.
- **Affected Scope:** Production code (`app/static/js/app.js`, `app/api/v1/endpoints.py`).

---

### HIGH-04: Unstyled Playlist Checklist Container Causes Page Viewport Blowout
- **Severity:** ⚠️ **HIGH**
- **File:** `app/static/css/styles.css` / `app/static/index.html`
- **Location:** `index.html:167-175`, `styles.css`
- **Problem:** `#playlist-checklist-container`, `.checklist-header`, and `#playlist-items-list` have no rules defined in `styles.css`. There is no `max-height`, no overflow handling, and no scrollbar styling.
- **Why It Matters:** When a user inspects a 50-track playlist, the DOM renders 50 unconstrained rows, pushing the "Start Download" and "Go Back" action buttons completely off screen.
- **Recommended Fix:** Add CSS rules in `styles.css` specifying `max-height: 280px`, `overflow-y: auto`, background, border, and custom scrollbars for `.playlist-items-list`.
- **Affected Scope:** Production code (`app/static/css/styles.css`).

---

### HIGH-05: Missing UNIQUE Constraint on Playlist Tracks Table Causes Duplicate Rows on Retry
- **Severity:** ⚠️ **HIGH**
- **File:** `app/db/repository.py`
- **Location:** Lines 31–39, 137–150
- **Problem:** The `tracks` table defines:
  ```sql
  CREATE TABLE IF NOT EXISTS tracks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      job_id TEXT NOT NULL,
      track_index INTEGER NOT NULL,
      track_title TEXT NOT NULL,
      ...
  );
  ```
  There is no unique constraint on `(job_id, track_index)`. If a download fails on track 4 and `_run_job_with_retries` restarts `_execute_job_pipeline`, `add_track_to_job` executes again for tracks 1, 2, 3, inserting duplicate rows into `tracks`.
- **Why It Matters:** Corrupts track history queries; causes `/api/v1/jobs/{id}` to return duplicate tracks in JSON responses.
- **Recommended Fix:** Add `UNIQUE(job_id, track_index)` to `tracks` table schema and use `INSERT INTO tracks ... ON CONFLICT(job_id, track_index) DO UPDATE SET ...`.
- **Affected Scope:** Production code (`app/db/repository.py`).

---

### HIGH-06: Non-Interruptible Synchronous Sleep Blocks Worker Cancellation
- **Severity:** ⚠️ **HIGH**
- **File:** `app/services/job_manager.py`
- **Location:** Lines 415–416 in `_run_job_with_retries()`
- **Problem:**
  ```python
  # Bounded backoff
  sleep_duration = backoff_base_sec * (2 ** (attempt - 1))
  time.sleep(sleep_duration)
  ```
  `time.sleep()` is synchronous. If a user cancels a job while a worker thread is sleeping between retries (up to 4 seconds), the thread cannot respond to cancellation until the sleep completes.
- **Why It Matters:** Thread starvation under load; delays cooperative cancellation cleanup.
- **Recommended Fix:** Replace `time.sleep(sleep_duration)` with `context.cancel_event.wait(timeout=sleep_duration)`. If the event is set during the wait, abort immediately.
- **Affected Scope:** Production code (`app/services/job_manager.py`).

---

### HIGH-07: Incomplete Reverse Proxy Trust Breaks IP-Based Rate Limiting
- **Severity:** ⚠️ **HIGH**
- **File:** `app/api/v1/endpoints.py`
- **Location:** Line 113 in `create_download_job()`
- **Problem:**
  ```python
  client_ip = request.client.host if request.client else "unknown"
  ```
  In production behind Nginx, Caddy, or Cloudflare, `request.client.host` is always `127.0.0.1` or the proxy's internal IP.
- **Why It Matters:** All users share the exact same rate-limit bucket (10 requests/minute total across all users globally). A single user submitting 10 jobs blocks all other users worldwide from downloading.
- **Recommended Fix:** Inspect `X-Forwarded-For` or `CF-Connecting-IP` headers when a configurable `TRUSTED_PROXIES` setting is enabled.
- **Affected Scope:** Production code (`app/api/v1/endpoints.py`, `app/core/config.py`).

---

## F. MEDIUM FINDINGS

### MED-01: In-Memory RateLimiter History Memory Leak
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/services/job_manager.py`
- **Location:** Lines 73–89 in `RateLimiter`
- **Problem:** `self._history: dict[str, list[float]]` retains dictionary keys for every `client_id` that ever connects. Inactive IPs are never purged.
- **Why It Matters:** On a public server running for months, `_history` will grow indefinitely with thousands of IP entries.
- **Recommended Fix:** Add periodic cleanup in `is_allowed()` or a background sweep to delete keys whose timestamps are older than `window_seconds`.
- **Affected Scope:** Production code (`app/services/job_manager.py`).

---

### MED-02: ID3v2.4 Windows Explorer Compatibility Issue
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/engine/audio_tagger.py`
- **Location:** Line 172 in `_tag_mp3()`
- **Problem:** Mutagen saves MP3 ID3 tags as ID3v2.4 by default.
- **Why It Matters:** Windows Explorer and legacy media players do not support ID3v2.4, displaying blank titles, artists, and missing album art for downloaded MP3s.
- **Recommended Fix:** Pass `v2_version=3` to `audio.save(file_path, v2_version=3)`.
- **Affected Scope:** Production code (`app/engine/audio_tagger.py`).

---

### MED-03: Missing WAV Audio Tagging Support
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/engine/audio_tagger.py`
- **Location:** Lines 100–120 in `tag_audio_file()`
- **Problem:** `tag_audio_file()` supports MP3, M4A, FLAC, and Opus. If the user selects WAV format, the file is skipped without tagging.
- **Why It Matters:** Users downloading in WAV format receive files with no embedded title or artist metadata.
- **Recommended Fix:** Add Mutagen RIFF/WAVE `mutagen.wave.WAVE` metadata tagging.
- **Affected Scope:** Production code (`app/engine/audio_tagger.py`).

---

### MED-04: Multi-File Download Drops Additional Tracks for Non-Playlist Jobs
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/services/job_manager.py`
- **Location:** Line 573 in `_execute_job_pipeline()`
- **Problem:** If `is_playlist=False`, the pipeline takes `final_delivery_path = final_files[0]`. If yt-dlp produces multiple audio files for a URL (e.g. video + separate audio commentary or unflagged multi-track), all files except the first are ignored.
- **Why It Matters:** Silent data loss for multi-stream downloads.
- **Recommended Fix:** If `len(final_files) > 1` and `not is_playlist`, automatically package all files into a ZIP archive.
- **Affected Scope:** Production code (`app/services/job_manager.py`).

---

### MED-05: Missing Browser Favicon Causes Repeated 404 Logging
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/static/index.html`
- **Location:** Lines 1–15 in `<head>`
- **Problem:** No `<link rel="icon">` is defined in `index.html`.
- **Why It Matters:** Browsers automatically request `/favicon.ico` on every visit, cluttering backend logs with 404 errors.
- **Recommended Fix:** Add `<link rel="icon" type="image/svg+xml" href="/static/img/favicon.svg">` and provide a clean SVG audio icon.
- **Affected Scope:** Production code (`app/static/index.html`, `app/static/img/`).

---

### MED-06: Accessibility: URL Input Missing Accessible Label
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/static/index.html`
- **Location:** Line 103 in `<input id="url-input">`
- **Problem:** The URL input relies solely on a `placeholder` attribute without an associated `<label>` or `aria-label`.
- **Why It Matters:** Fails WCAG 2.1 Success Criterion 3.3.2 (Labels or Instructions). Screen readers cannot convey the input purpose.
- **Recommended Fix:** Add `<label for="url-input" class="sr-only">Media URL</label>` or `aria-label="Media URL to download"`.
- **Affected Scope:** Production code (`app/static/index.html`).

---

### MED-07: Accessibility: Format Chips Lack Radio Group Semantics
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/static/index.html` / `app/static/js/app.js`
- **Location:** `index.html:110-137`, `app.js:132-152`
- **Problem:** Format selection options are `<div>` elements without `role="radiogroup"`, `role="radio"`, `aria-checked`, or keyboard arrow navigation.
- **Why It Matters:** Keyboard-only and screen reader users cannot navigate or select audio formats.
- **Recommended Fix:** Add `role="radiogroup"` to container, `role="radio"` and `tabindex="0"` to chips, and implement Arrow key navigation in `app.js`.
- **Affected Scope:** Production code (`app/static/index.html`, `app/static/js/app.js`).

---

### MED-08: Accessibility: Dynamic Status Updates Lack ARIA Live Regions
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/static/index.html`
- **Location:** Lines 190, 199, 215, 230
- **Problem:** Progress percentages, ETA, and download status updates lack `aria-live="polite"` or `role="status"`.
- **Why It Matters:** Visually impaired users receive zero announcements when downloads progress or fail.
- **Recommended Fix:** Add `aria-live="polite"` to `#dl-status-text` and `#progress-percent`, and `aria-live="assertive"` to `#error-message`.
- **Affected Scope:** Production code (`app/static/index.html`).

---

### MED-09: Uncapped Flat Metadata Extraction Memory Spike Risk
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/engine/ytdlp_engine.py`
- **Location:** Lines 273–286 in `extract_media_info()`
- **Problem:** `extract_media_info` uses `extract_flat=True` without limiting `playlistend`.
- **Why It Matters:** Inspecting a playlist with 5,000 items creates a massive JSON dictionary in memory, freezing the thread for 30+ seconds.
- **Recommended Fix:** Add `"playlistend": settings.MAX_PLAYLIST_ITEMS` to `extract_media_info()` options.
- **Affected Scope:** Production code (`app/engine/ytdlp_engine.py`).

---

### MED-10: Incomplete Dark Mode Variables (Missing Shadows & Scrollbars)
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/static/css/styles.css`
- **Location:** Lines 55–85 in `[data-theme="dark"]`
- **Problem:** The dark theme overrides background and text colors, but omits `--shadow-sm`, `--shadow-md`, `--shadow-lg`, and dark scrollbar styles.
- **Why It Matters:** Cards and popups appear flat or blend invisibly into backgrounds in dark mode.
- **Recommended Fix:** Define elevated dark shadow variables and custom dark scrollbars in `styles.css`.
- **Affected Scope:** Production code (`app/static/css/styles.css`).

---

### MED-11: No Local Download History in Frontend
- **Severity:** 🟡 **MEDIUM**
- **File:** `app/static/js/app.js`
- **Location:** Lines 455–480
- **Problem:** Once a download completes, clicking "Download Another" resets the view, discarding all record of the completed job.
- **Why It Matters:** If a user downloads 5 songs, they cannot access earlier download links without inspecting and downloading them again.
- **Recommended Fix:** Store completed job IDs, titles, and download URLs in `localStorage` and display a "Recent Downloads" tray.
- **Affected Scope:** Production code (`app/static/js/app.js`, `app/static/index.html`).

---

## G. LOW FINDINGS

### LOW-01: Legacy Project Title Inconsistencies
- **Severity:** 🔵 **LOW**
- **File:** `pyproject.toml`, `requirements.txt`, `.env.example`
- **Problem:** References to prototype working title "Auralis" remain instead of "SONORA".
- **Recommended Fix:** Rename project metadata to `sonora` across build files.
- **Affected Scope:** Configuration / documentation.

### LOW-02: Dead Code in Audio Tagger
- **Severity:** 🔵 **LOW**
- **File:** `app/engine/audio_tagger.py`
- **Location:** Lines 23–45 (`convert_audio()`)
- **Problem:** `convert_audio()` is defined but never invoked in production workflows (transcoding is handled by yt-dlp FFmpeg postprocessors).
- **Recommended Fix:** Remove or mark as internal helper with unit test coverage.
- **Affected Scope:** Production code (`app/engine/audio_tagger.py`).

### LOW-03: Relative Default Storage Paths
- **Severity:** 🔵 **LOW**
- **File:** `app/core/config.py`
- **Location:** Lines 33–34
- **Problem:** `TEMP_DIR: Path = Path("data/temp")` is relative. If the application is launched from a directory other than the project root, files are written to the current working directory.
- **Recommended Fix:** Resolve paths relative to project root (`Path(__file__).resolve().parents[2] / "data"`).
- **Affected Scope:** Production code (`app/core/config.py`).

### LOW-04: Redundant FFmpeg Version Probing
- **Severity:** 🔵 **LOW**
- **File:** `app/engine/ffmpeg_locator.py`
- **Location:** Lines 64–112 in `get_ffmpeg_path()`
- **Problem:** `get_ffmpeg_path()` executes `subprocess.run(["ffmpeg", "-version"])` on every call. It is invoked on every single download job.
- **Why It Matters:** Redundant process spawning overhead.
- **Recommended Fix:** Cache the discovered and verified path in a module-level variable.
- **Affected Scope:** Production code (`app/engine/ffmpeg_locator.py`).

### LOW-05: Missing Print Stylesheet
- **Severity:** 🔵 **LOW**
- **File:** `app/static/css/styles.css`
- **Problem:** Printing the webpage prints dark backgrounds and unstyled interactive controls.
- **Recommended Fix:** Add `@media print` rules hiding hero forms, buttons, and animations.
- **Affected Scope:** Production code (`app/static/css/styles.css`).

### LOW-06: Small Touch Target on Clear Button
- **Severity:** 🔵 **LOW**
- **File:** `app/static/css/styles.css`
- **Location:** Lines 470–485
- **Problem:** The URL input `.clear-btn` touch target size is ~20x20px.
- **Recommended Fix:** Increase touch target padding to at least 44x44px.
- **Affected Scope:** Production code (`app/static/css/styles.css`).

---

## H. MISSING FEATURES

1. **System Health & Readiness Endpoint (`/healthz`):** No endpoint exists for uptime monitors, Docker probes, or Kubernetes healthchecks to verify DB connectivity and free disk space.
2. **Download History Panel:** No client-side history tray allowing users to view and re-download completed tracks from the current session.
3. **Audio Preview Player:** No embedded HTML5 audio player allowing users to preview a 15-second snippet before committing to a full download.
4. **WAV RIFF Metadata Tagging:** No ID3/RIFF tag embedding for uncompressed WAV downloads.
5. **Reverse Proxy Configuration (`TRUSTED_PROXIES`):** No configuration setting allowing safe extraction of `X-Forwarded-For` client IPs.
6. **Server Resource Telemetry in SSE:** Progress events do not communicate current server queue position or server load to clients.

---

## I. MISSING TESTS

1. **Real Browser / JavaScript End-to-End Tests:** Current frontend tests in `test_frontend.py` only do substring checks on HTML/CSS. Zero JavaScript logic, DOM manipulation, SSE reception, or error states are tested in a browser engine.
2. **50+ Track Playlist Stress Test:** Existing playlist tests use mocks with 1 or 2 tracks. No tests verify 50-track archive packaging, composite progress accuracy, or memory consumption.
3. **Transcode Cancellation Test:** No test verifies what happens when `cancel_event` is set while FFmpeg is actively transcoding audio.
4. **Network Timeout / Broken Pipe Simulation:** No test simulates socket drops mid-download to verify that retry backoff and scratchpad sweeping operate cleanly.
5. **Windows Reserved Name Unit Test:** No test currently passes `"CON"` or `"AUX"` to `sanitize_filename()` to verify OS-safe sanitization.

---

## J. SECURITY GAPS

1. **Secondary DNS Rebinding in yt-dlp:** Pre-flight DNS check is decoupled from yt-dlp's internal transport resolution (TOCTOU).
2. **Unbounded Metadata Extraction:** Malicious URLs with 10,000 playlist entries can trigger high memory consumption during flat extraction.
3. **Reverse Proxy IP Trust:** Absence of trusted proxy validation causes rate limiting to throttle all users under the proxy's IP.
4. **RateLimiter Memory Growth:** Inactive IP keys are never evicted, enabling slow memory exhaustion over time.

---

## K. PERFORMANCE GAPS

1. **SQLite DDL Contention on Connection:** `init_db()` running on every connection acquires table locks and degrades concurrency under multi-user loads.
2. **Non-Interruptible Sleep in Retry Backoff:** Worker threads remain blocked for up to 4 seconds during retry sleeps, ignoring cancellation tokens.
3. **Repeated FFmpeg Subprocess Version Checks:** Binary location is verified via subprocess execution on every download task instead of being cached.
4. **Artwork Memory Inefficiency:** Thumbnail images are loaded completely into byte buffers in memory during tagging.

---

## L. DEPLOYMENT GAPS

1. **Missing Dockerfile & docker-compose.yml:** The repository lacks containerization instructions with pre-installed FFmpeg, Python 3.12, and non-root execution.
2. **Missing CI/CD Workflow:** No GitHub Actions workflow exists to run pytest, Ruff, and type checks on commits and pull requests.
3. **Missing Static Type Checking (`mypy`):** No type checking step exists in the build or verification pipeline.
4. **Missing Coverage & Audit Tools:** `pytest-cov` and `pip-audit` are absent from `requirements-dev.txt`.
5. **Rigid yt-dlp Version Pinning:** `yt-dlp==2024.9.27` is strictly pinned. Video platforms frequently break older extractors; a safe auto-update or patch workflow is needed.

---

## M. RECOMMENDED REPAIR ORDER

### Phase 4 Sprint 2: Core Engineering, Concurrency & Security Hardening
1. **DB Connection Optimization (CRIT-01):** Decouple `init_db()` from `create_connection()`; run strictly once in `app/main.py:lifespan()`.
2. **Frontend SSE Fallback Bound (CRIT-02):** Add a 5-failure limit and backoff to `startPollingFallback()` in `app.js`.
3. **Windows Reserved Device Name Defense (HIGH-02):** Add reserved name sanitization in `app/engine/sanitizer.py`.
4. **Frontend Playlist UI & Selection Overhaul (HIGH-03, HIGH-04):** Add CSS rules for `.playlist-items-list` (`max-height: 280px`, scrolling); disable "Start Download" when 0 tracks are selected.
5. **Database Unique Tracks Constraint (HIGH-05):** Add `UNIQUE(job_id, track_index)` to `tracks` table schema with conflict resolution.
6. **Interruptible Worker Sleep (HIGH-06):** Replace `time.sleep()` with `context.cancel_event.wait()` in retry loop.
7. **Reverse Proxy Trust & RateLimiter Eviction (HIGH-07, MED-01):** Support `X-Forwarded-For` with `TRUSTED_PROXIES`; add TTL eviction to `RateLimiter`.
8. **Audio Tagging Polish (MED-02, MED-03):** Save MP3s with ID3v2.3 (`v2_version=3`); add WAV tagging.

### Phase 4 Sprint 3: Production UX, Accessibility, Packaging & Release
1. **WCAG 2.1 AA Accessibility (MED-06, MED-07, MED-08):** Add `<label>` to URL input; convert format chips to semantic radio group; add `aria-live` regions.
2. **Healthcheck & Observability (Missing Features 1):** Add `GET /healthz` endpoint reporting DB status, disk space, and worker pool metrics.
3. **Favicon & Brand Hygiene (MED-05, LOW-01):** Add SVG favicon; rename internal project titles to "SONORA" across build files.
4. **Docker Containerization (Deployment 1):** Multi-stage `Dockerfile` (Python 3.12-slim + FFmpeg) and `docker-compose.yml`.
5. **CI/CD Pipeline (Deployment 2):** GitHub Actions workflow executing pytest, Ruff, and `mypy` on Ubuntu and Windows.
6. **Recent Downloads History Tray (MED-11):** Add local storage persistence in frontend.

---

## N. ESTIMATED COMPLETION PERCENTAGE

- **Core Backend Architecture & Lifecycles:** **88%**
- **Download Engine & Format Processing:** **85%**
- **Security & Concurrency Boundaries:** **82%**
- **API Contracts & Error Handling:** **92%**
- **Frontend UX & Responsive Layout:** **70%**
- **Accessibility (WCAG 2.1 AA):** **45%**
- **Deployment, Packaging & CI/CD:** **20%**
- **Test Coverage & Real-World Resilience:** **75%**

**Overall Production-Readiness Completion:** **~73%**

---

## O. DEFINITION OF DONE FOR FINAL RELEASE

SONORA can be declared a **full-fledged, battle-tested, production-ready product** when:
1. **Zero Table Lock Contention:** Schema initialization runs strictly once at startup; connections acquire zero DDL locks.
2. **Zero Uncaught OS / Filesystem Exceptions:** All Windows reserved device names, unicode emojis, and path edge cases sanitize cleanly.
3. **Flawless Playlist UX:** Large playlists scroll within a bounded viewport; 0-track selection is impossible; and cancelled/failed jobs clean up cleanly.
4. **Resilient SSE & Polling:** Telemetry streams cleanly; client polling stops gracefully upon terminal error or server restart.
5. **Universal Media Player Compatibility:** MP3s display titles, artists, and artwork correctly in Windows Explorer (ID3v2.3) and Apple platforms.
6. **WCAG 2.1 AA Certified:** Full keyboard navigability, semantic radio groups, screen-reader live announcements, and compliant touch targets.
7. **Containerized & CI/CD Automated:** Verified builds passing pytest, Ruff, and `mypy` in GitHub Actions; one-command `docker run` deployment.
8. **Byte-for-Byte Legacy Integrity:** Prototype files (`app.py`, `music_fixer.py`, `templates/index.html`, `ffmpeg.exe`) remain intact.

---
*Report generated under read-only audit mode. No production source or test files were modified.*
