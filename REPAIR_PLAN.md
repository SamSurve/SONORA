# Comprehensive Repair & Hardening Plan (Pre-Phase 3) — Revised Specification

**Project:** Auralis Music Downloader  
**Phase:** Phase 1 + Phase 2 Foundation Repair & Hardening  
**Date:** September 22, 2026  
**Status:** Plan Revised — Pending User Approval  

---

## 1. Executive Summary

Three independent pre-Phase 3 audits (`AGENT_1_ARCHITECTURE_REPORT.md`, `AGENT_2_SECURITY_REPORT.md`, and `AGENT_3_QA_REPORT.md`) independently concluded that the existing Phase 1 and Phase 2 foundation is **NOT READY FOR PHASE 3**.

Empirical verification against the repository confirmed 15 critical/high architectural, database, concurrency, security, and job lifecycle issues. While the existing unit tests (68 tests) pass due to aggressive test fixture mocking, fresh production deployments crash immediately, concurrent database writes trigger immediate SQLite deadlocks under deferred transactions, server restarts leave permanent zombie jobs leaking storage disk space, job cancellations race against active Windows file handles (`WinError 32`), and safety quotas are completely unenforced.

This revised repair plan outlines targeted, minimal, root-cause remediations to harden the Phase 1 + Phase 2 foundation so that it is genuinely ready for Phase 3 REST API & SSE development.

---

## 2. Refined Architectural & Design Principles

### 2.1 Refined SQLite Concurrency Architecture
Rather than blindly applying `BEGIN IMMEDIATE` to every database connection or query, the persistence layer is refined with strict transaction scoping:

1. **Read-Only Operations (`get_db_read` / Autocommit SELECT):**
   - Read-only queries (`get_job`, `get_tracks_for_job`, `get_active_job_ids`, `get_expired_jobs`, `list_jobs`) execute via standard autocommit `SELECT` or `get_db_read()` without acquiring write locks or reserved write locks. This allows non-blocking concurrent reads under SQLite Write-Ahead Logging (WAL) mode.
2. **Write / Read-Then-Write Operations (`get_db_write` with `BEGIN IMMEDIATE`):**
   - Mutation operations (`create_job`, `update_job_status`, `add_track_to_job`, `update_track_status`, `mark_job_expired`) execute inside `get_db_write()` context manager using `conn.execute("BEGIN IMMEDIATE;")`. This acquires a reserved write lock immediately at transaction start, preventing upgrade deadlocks when concurrent worker threads read and subsequently attempt to write.
3. **Short Transaction Boundaries & Zero I/O inside Transactions:**
   - Database transactions must remain strictly sub-millisecond. Zero network requests, yt-dlp extractions, Mutagen tagging, FFmpeg conversions, or `shutil.rmtree` directory deletions are permitted inside `with get_db_...()` blocks.
4. **Empirical Concurrency Verification:**
   - A dedicated multi-threaded stress test ([test_concurrency_wal.py](file:///e:/MUSIC%20DOWNLODER/tests/test_concurrency_wal.py)) spawning 10+ concurrent worker threads performing rapid status updates must prove that zero `sqlite3.OperationalError: database is locked` errors occur.

### 2.2 Realistic SSRF & DNS Rebinding Security Boundary
SSRF protection is structured with realistic execution boundaries:

1. **Submission & Inspection Pre-Flight Validation:**
   - All incoming URLs submitted to `JobManager.submit_job()` or `metadata_service.extract_metadata()` are validated via `validate_url(url, resolve_dns=True)`.
   - `validate_url()` resolves hostnames via `socket.getaddrinfo()` and checks all returned IPv4/IPv6 addresses against CIDR blacklists (loopback `127.0.0.0/8`, `::1/128`, private RFC 1918 `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, link-local `169.254.0.0/16`, ULA `fc00::/7`, carrier-grade NAT `100.64.0.0/10`, and obfuscated IP formats).
2. **yt-dlp Engine Network Constraints:**
   - `build_ydl_options()` specifies `"allowed_protocols": ["http", "https"]` to prevent yt-dlp from accessing local files (`file://`), `gopher://`, `ftp://`, or custom protocols.
3. **Documented Architectural Limitation & Phase 3 Boundary:**
   - *Technical Limitation:* yt-dlp extracts media manifests (HLS/DASH fragments) from third-party Content Delivery Networks (CDNs) whose segment hostnames are generated dynamically during extraction. Overriding yt-dlp's internal socket transport to validate every fragment IP at runtime risks breaking YouTube CDN media stream downloads due to CDN IP rotation.
   - *Phase 3 Boundary:* Complete protection against post-submission DNS rebinding across CDN media fragments must be handled at the network/container egress boundary (e.g. firewall egress rules or isolated network namespaces) during Phase 3 deployment, rather than monkey-patching yt-dlp internals.

### 2.3 Rate Limiting & Quota Architecture
The system cleanly separates job-level quota enforcement from client-level request rate limiting without introducing fake client identities:

1. **Job-Level Quota Enforcement (Framework-Independent):**
   - Enforced directly in `JobManager.submit_job()` and `build_ydl_options()`:
     - `MAX_PLAYLIST_ITEMS` (default 100): Rejects single requests containing >100 selected playlist tracks, and passes `playlistend=settings.MAX_PLAYLIST_ITEMS` to yt-dlp options to cap metadata/stream extraction.
     - `DISK_FREE_THRESHOLD_MB` (default 2048 MB): Asserts sufficient disk space before enqueueing.
2. **Client-Level Rate Limiting Interface (API Layer Integration Ready):**
   - `JobManager.submit_job()` accepts an optional `client_id: str | None = None` parameter (e.g. IP address or API client key supplied by the caller).
   - An internal framework-independent `RateLimiter` class tracks submissions per `client_id` using a rolling window.
   - If `client_id` is `None` (e.g., direct Python usage or tests), rate limiting is bypassed. When Phase 3 FastAPI endpoints invoke `submit_job()`, FastAPI passes `request.client.host` as `client_id`, enforcing `RATE_LIMIT_PER_MINUTE` cleanly without coupling `JobManager` to HTTP frameworks.

### 2.4 Strict Scope Boundary (Phase 1+2 Repairs Only)
The current repair phase strictly excludes Phase 3 features:

- **Included in Repair Phase:** Database persistence fixes, WAL concurrency, zombie job recovery, cooperative cancellation lifecycle, quota enforcement, `socket_timeout`, composite progress hooks, WebP artwork conversion, native audio format stream copy, `is_playlist` schema persistence, janitor transaction decoupling, missing `metadata_service.py`, regression tests, and documentation.
- **Explicitly Deferred to Phase 3:** FastAPI routes, SSE streaming endpoints, SSE initial event replay caching, WebSocket connections, HTML/CSS/JS web interface, frontend assets, and Docker/deployment manifests.

---

## 3. Reconciliation Matrix & Status of All Audit Findings

| # | Issue ID | Category | Audit Finding Description | Action & Reconciliation Strategy | Primary Affected File(s) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **CRIT-1** | Database | `init_db()` never invoked in production connection handlers; fresh DB crashes on first job. | **Concrete Repair Now:** `create_connection()` / `get_db_read()` / `get_db_write()` idempotently initializes schema DDL if tables do not exist. | [database.py](file:///e:/MUSIC%20DOWNLODER/app/db/database.py) |
| **2** | **CRIT-2** | Concurrency | SQLite write-lock deadlocks under concurrent workers (`BEGIN;` deferred vs `BEGIN IMMEDIATE;`). | **Concrete Repair Now:** Separate `get_db_read()` (autocommit `SELECT`) from `get_db_write()` (`BEGIN IMMEDIATE;` write reservation). Verify via 10+ worker WAL test. | [database.py](file:///e:/MUSIC%20DOWNLODER/app/db/database.py) |
| **3** | **CRIT-3** | Lifecycle | Interrupted active jobs remain stuck across server restarts; Janitor protects zombie files forever. | **Concrete Repair Now:** Implement `reconcile_startup_jobs()` on `JobManager` init to mark active jobs as `FAILED` and purge scratchpads outside DB transactions. | [job_manager.py](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py), [janitor.py](file:///e:/MUSIC%20DOWNLODER/app/engine/janitor.py) |
| **4** | **CRIT-4** | Lifecycle | `cancel_job()` purges scratchpad immediately, causing Windows `WinError 32` file-lock race and orphaned `completed/` files. | **Concrete Repair Now:** Set cancellation token in `cancel_job()`; defer workspace `rmtree` until worker thread exits cooperatively. Clean both `temp_dir` and `completed_dir` in `_record_final_state()`. | [job_manager.py](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py) |
| **5** | **CRIT-5** | Security | Safety quotas (`MAX_PLAYLIST_ITEMS`, `RATE_LIMIT_PER_MINUTE`) defined in config but unenforced in code. | **Concrete Repair Now:** Enforce `MAX_PLAYLIST_ITEMS` in `submit_job()` and yt-dlp `playlistend`. Add optional `client_id` interface to `submit_job()` for framework-independent `RATE_LIMIT_PER_MINUTE` checking. | [job_manager.py](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py), [ytdlp_engine.py](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py) |
| **6** | **HIGH-1** | Architecture | Missing `metadata_service.py` required by target architecture and Phase 3 API specifications. | **Concrete Repair Now:** Create `app/services/metadata_service.py` with URL validation and normalized track metadata response formatting. | [metadata_service.py](file:///e:/MUSIC%20DOWNLODER/app/services/metadata_service.py) (New) |
| **7** | **HIGH-2** | Reliability | `socket_timeout` omitted from yt-dlp options, causing indefinite worker hangs on network stalls. | **Concrete Repair Now:** Add `"socket_timeout": 20` to `build_ydl_options()` and `extract_media_info()` in `ytdlp_engine.py`. | [ytdlp_engine.py](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py) |
| **8** | **HIGH-3** | Telemetry | Playlist progress resets 0-100% per track instead of reporting aggregate composite job progress. | **Concrete Repair Now:** Calculate composite playlist progress in `_progress_hook`: `((playlist_index - 1) * 100.0 + track_percent) / total_tracks`. | [ytdlp_engine.py](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py) |
| **9** | **HIGH-4** | Media/Artwork | WebP thumbnails embedded raw into MP3 ID3 tags and wrapped in JPEG M4A `covr` atoms, corrupting cover art. | **Concrete Repair Now:** Add `FFmpegThumbnailsConvertor` with `"format": "jpg"` in yt-dlp postprocessors; validate artwork MIME type in `audio_tagger.py`. | [ytdlp_engine.py](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py), [audio_tagger.py](file:///e:/MUSIC%20DOWNLODER/app/engine/audio_tagger.py) |
| **10** | **HIGH-5** | Media/Artwork | Playlist track tagging assigns the first discovered thumbnail image in `temp_dir` to every track. | **Concrete Repair Now:** Match artwork per track by stem/index when per-track images exist; fall back to playlist cover if single artwork. | [job_manager.py](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py) |
| **11** | **HIGH-6** | Media/Audio | Native format requests (`NATIVE_M4A`, `NATIVE_OPUS`) force lossy re-encoding via `FFmpegExtractAudio`. | **Concrete Repair Now:** Set yt-dlp format selector to `ba[ext=m4a]` / `ba[ext=webm]` and perform direct stream extraction without transcoding when native match exists. | [ytdlp_engine.py](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py) |
| **12** | **HIGH-7** | Database | Table `jobs` lacks `is_playlist` column; `create_job()` cannot store or query playlist type. | **Concrete Repair Now:** Add `is_playlist INTEGER NOT NULL DEFAULT 0` to `SCHEMA_SQL` and update `create_job()` to persist `is_playlist`. | [repository.py](file:///e:/MUSIC%20DOWNLODER/app/db/repository.py) |
| **13** | **HIGH-8** | Database | Janitor performs expensive `shutil.rmtree` directory deletions inside `with get_db() as conn:` transactions. | **Concrete Repair Now:** Decouple janitor logic: query expired jobs in DB, close connection, perform `shutil.rmtree` file operations, then update DB status to `expired` in short write transactions. | [janitor.py](file:///e:/MUSIC%20DOWNLODER/app/engine/janitor.py) |
| **14** | **HIGH-9** | Security | Secondary redirects in yt-dlp bypass submission-time URL validation, creating SSRF / DNS rebinding risk. | **Documented Limitation & Boundary:** Perform pre-flight validation on all submitted URLs, set `"allowed_protocols": ["http", "https"]` in yt-dlp options, and document network egress security boundary for Phase 3 deployment. | [security.py](file:///e:/MUSIC%20DOWNLODER/app/core/security.py), [ytdlp_engine.py](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py) |
| **15** | **MED-1** | Maintenance | Dead/orphaned code: `convert_audio()`, `format_track_filename()`, `validate_redirect()`, `JanitorDaemon`. | **Concrete Repair Now:** Wire `format_track_filename()` into file placement logic; document `JanitorDaemon` start hook for application lifecycle. | Various engine & service modules |
| **16** | **MED-2** | Lifecycle | Single-track playlist requests return raw MP3 instead of a ZIP archive. | **Concrete Repair Now:** Ensure `is_playlist=True` requests consistently package output as a ZIP archive regardless of final track count. | [job_manager.py](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py) |
| **17** | **MED-3** | Telemetry | SSE subscriber registration lacks initial event caching/replay on connection. | **Explicitly Deferred to Phase 3:** Event caching and replay for connecting HTTP SSE clients belongs in Phase 3 FastAPI `GET /api/v1/jobs/{id}/events` stream handler. | Phase 3 API Scope |
| **18** | **MED-4** | Testing | Zero direct unit test coverage for `ytdlp_engine.py`. | **Concrete Repair Now:** Implement `tests/test_ytdlp_engine.py` testing option assembly, postprocessor configurations, and progress calculations. | [test_ytdlp_engine.py](file:///e:/MUSIC%20DOWNLODER/tests/test_ytdlp_engine.py) (New) |
| **19** | **MED-6** | Packaging | `pyproject.toml` references `README.md` which does not exist in root. | **Concrete Repair Now:** Create project root `README.md` with system overview and build specifications. | [README.md](file:///e:/MUSIC%20DOWNLODER/README.md) (New) |
| **20** | **MED-7** | Security | Completed tracks moved using raw yt-dlp names without invoking `sanitize_filename()` / `format_track_filename()`. | **Concrete Repair Now:** Apply `sanitize_filename()` and `format_track_filename()` to finalized audio filenames before moving to `completed_dir`. | [job_manager.py](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py) |
| **21** | **MED-8** | Security | Internal exception tracebacks and Windows paths leaked directly into `jobs.error_message`. | **Concrete Repair Now:** Sanitize `error_message` stored in `jobs` DB table to safe generic descriptions while logging full tracebacks internally. | [job_manager.py](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py) |
| **22** | **LOW-1** | Config | Configuration setting discrepancies (`DISK_FREE_THRESHOLD_MB`, `JANITOR_SWEEP_INTERVAL_SECONDS`). | **Concrete Repair Now:** Align `Settings` class fields and defaults with documented specifications. | [config.py](file:///e:/MUSIC%20DOWNLODER/app/core/config.py) |

---

## 4. Root Cause Analysis & Detailed Fix Specifications

### 4.1 Persistence Layer Hardening (`CRIT-1`, `CRIT-2`, `HIGH-7`)
- **Files:** [app/db/database.py](file:///e:/MUSIC%20DOWNLODER/app/db/database.py), [app/db/repository.py](file:///e:/MUSIC%20DOWNLODER/app/db/repository.py)
- **Fix Details:**
  1. In `database.py`, create two explicit context managers:
     - `get_db_read(db_path=None)`: Opens connection in autocommit mode and yields `conn` for read-only operations without `BEGIN` or write locks.
     - `get_db_write(db_path=None)`: Opens connection and executes `conn.execute("BEGIN IMMEDIATE;")` to acquire a reserved write lock at transaction start, preventing upgrade deadlocks.
  2. In `create_connection()`, invoke `init_db(conn)` idempotently so fresh databases create `jobs` and `tracks` tables immediately on connection.
  3. In `repository.py`, add `is_playlist INTEGER NOT NULL DEFAULT 0` to `SCHEMA_SQL` and update `create_job()` to accept and persist `is_playlist`.

### 4.2 Job Manager & Concurrency Safety (`CRIT-3`, `CRIT-4`, `CRIT-5`, `HIGH-5`, `MED-2`, `MED-7`, `MED-8`)
- **Files:** [app/services/job_manager.py](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py)
- **Fix Details:**
  1. **Startup Recovery (`CRIT-3`):** Implement `reconcile_startup_jobs()` called inside `JobManager.__init__()`. Query jobs with status in `('queued', 'fetching_metadata', 'downloading', 'converting', 'tagging')`, transition them to `JobStatus.FAILED` with error message `"Job interrupted by server restart"`, and clean up scratchpad directories outside DB transactions.
  2. **Cancellation Race (`CRIT-4`):** Update `cancel_job()` to set `context.cancel_event.set()` and update SQLite state, but do NOT run `shutil.rmtree` immediately while the worker thread is running. Let cooperative cancellation exit the thread, which calls `_record_final_state()`. Update `_record_final_state()` to clean BOTH `temp_dir` AND `completed_dir` for terminal `CANCELLED` and `FAILED` states.
  3. **Quota Enforcement & Rate Limiting Interface (`CRIT-5`):**
     - Enforce `MAX_PLAYLIST_ITEMS` in `submit_job()`.
     - Accept optional `client_id: str | None = None` in `submit_job()`. If `client_id` is supplied, check against an internal rolling-window `RateLimiter` class enforcing `RATE_LIMIT_PER_MINUTE`.
  4. **Filename Sanitization & Artwork (`HIGH-5`, `MED-7`):** Apply `sanitize_filename()` and `format_track_filename()` to completed tracks. Match artwork files to individual tracks by stem when per-track thumbnails exist.
  5. **Error Sanitization (`MED-8`):** Record sanitized error messages (e.g. `"Download failed due to network or extraction error"`) into SQLite while logging raw exception tracebacks to log files.
  6. **Single-Track Playlist Packaging (`MED-2`):** Always produce a ZIP archive when `is_playlist=True` regardless of final track count.

### 4.3 Media Engine & yt-dlp Configuration (`HIGH-2`, `HIGH-3`, `HIGH-4`, `HIGH-6`, `HIGH-9`)
- **Files:** [app/engine/ytdlp_engine.py](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py), [app/engine/audio_tagger.py](file:///e:/MUSIC%20DOWNLODER/app/engine/audio_tagger.py)
- **Fix Details:**
  1. Add `"socket_timeout": 20` and `"allowed_protocols": ["http", "https"]` to `build_ydl_options()` and `extract_media_info()`.
  2. Add `FFmpegThumbnailsConvertor` with `"format": "jpg"` to yt-dlp postprocessors to ensure thumbnails are valid JPEG files.
  3. Calculate composite playlist progress in `_progress_hook`: `composite_percent = ((playlist_index - 1) * 100.0 + track_percent) / total_tracks`.
  4. Support true native stream extraction for `NATIVE_M4A` and `NATIVE_OPUS` without forcing lossy-to-lossy re-encoding when source stream is already native format.
  5. In `audio_tagger.py`, validate image data headers (`b"\xff\xd8\xff"` for JPEG, `b"\x89PNG"` for PNG) before embedding into ID3 or MP4 tags.

### 4.4 Decoupled Storage Janitor (`HIGH-8`)
- **Files:** [app/engine/janitor.py](file:///e:/MUSIC%20DOWNLODER/app/engine/janitor.py)
- **Fix Details:**
  1. In `run_janitor_cleanup()`, query expired jobs and active job IDs inside a short read connection.
  2. Close the database connection.
  3. Execute `shutil.rmtree` on expired job directories in `data/completed/` and `data/temp/`.
  4. Re-open short write transactions to mark purged jobs as `expired` (`mark_job_expired`).

### 4.5 New Metadata Service (`HIGH-1`)
- **Files:** [app/services/metadata_service.py](file:///e:/MUSIC%20DOWNLODER/app/services/metadata_service.py) (New)
- **Fix Details:**
  1. Implement `extract_metadata(url: str, is_playlist: bool = False) -> dict[str, Any]` wrapping `extract_media_info()` with pre-flight `validate_url(url, resolve_dns=True)`.
  2. Normalize and format return dictionary (title, uploader, duration, thumbnail_url, track list, is_playlist) for Phase 3 API compatibility.

---

## 5. Summary of Affected Files

| Component | File Path | Action | Summary of Changes |
| :--- | :--- | :--- | :--- |
| **Database** | `app/db/database.py` | Modify | Implement `get_db_read()` and `get_db_write()` (`BEGIN IMMEDIATE;`); auto-initialize DDL in `create_connection()`. |
| **Database** | `app/db/repository.py` | Modify | Add `is_playlist` column to `jobs` DDL; update `create_job()`. |
| **Services** | `app/services/job_manager.py` | Modify | Fix cancellation race; clean `completed_dir`; sanitize DB errors; enforce quotas & `client_id` rate limiting; add startup recovery. |
| **Services** | `app/services/metadata_service.py` | **Create** | Implement metadata inspection service with SSRF validation. |
| **Engine** | `app/engine/ytdlp_engine.py` | Modify | Add `socket_timeout`; `allowed_protocols`; JPG thumbnail converter; composite progress; native stream copy. |
| **Engine** | `app/engine/audio_tagger.py` | Modify | Fix artwork MIME type checks and WebP image validation. |
| **Engine** | `app/engine/janitor.py` | Modify | Decouple `rmtree` directory removals from active database transaction contexts. |
| **Core** | `app/core/config.py` | Modify | Ensure settings fields and defaults match report specifications. |
| **Packaging** | `README.md` | **Create** | Root documentation file referenced by `pyproject.toml`. |
| **Protocol State**| `PLAN.md`, `STATE.md`, `DECISIONS.md`, `TASKS.md`, `CHANGELOG.md`, `REPORT.md` | **Create** | Protocol tracking files. |
| **Tests** | `tests/test_ytdlp_engine.py` | **Create** | Direct unit tests for option assembly, timeouts, and progress calculations. |
| **Tests** | `tests/test_concurrency_wal.py` | **Create** | Stress test spawning 10+ concurrent worker threads verifying zero `database is locked` deadlocks. |
| **Tests** | `tests/test_startup_recovery.py` | **Create** | Integration test for startup zombie job recovery. |

---

## 6. Compatibility Risks & Mitigations

- **Database Migration:** If an un-migrated `data/auralis.db` exists, `init_db()` will execute `ALTER TABLE jobs ADD COLUMN is_playlist INTEGER NOT NULL DEFAULT 0;` safely if the column is missing.
- **Windows File Handle Locks:** Deleting workspace folders during active streaming is avoided by setting `cancel_event` and deferring `rmtree` until the worker thread exits cleanly.
- **Backward Compatibility:** All existing signatures in `JobManager` and `repository.py` maintain backward compatibility. Legacy prototype files (`app.py`, `music_fixer.py`, `templates/index.html`, `ffmpeg.exe`) remain 100% byte-for-byte untouched.

---

## 7. Test Strategy & Verification Plan

1. **Existing Unit Tests:** Run full existing test suite (`.venv\Scripts\python.exe -m pytest -v`) ensuring 100% pass rate.
2. **Fresh Database Startup Test:** Instantiation of SQLite connection on clean DB path auto-initializes DDL without manual fixture calls.
3. **10+ Worker WAL Concurrency Test (`test_concurrency_wal.py`):** Spawn 10 concurrent worker threads executing status updates under `get_db_write()` (`BEGIN IMMEDIATE;`) to verify zero `database is locked` deadlocks.
4. **Zombie Recovery Test (`test_startup_recovery.py`):** Populate SQLite with non-terminal jobs, initialize `JobManager`, and verify transition to `FAILED` and scratchpad cleanup.
5. **Cancellation & File-Lock Test:** Trigger job cancellation during active file writing on Windows and verify clean worker thread termination without `WinError 32`.
6. **Quota & Rate Limit Test:** Assert rejection of requests exceeding `MAX_PLAYLIST_ITEMS` and rate limits for a given `client_id`.
7. **Static Analysis & Linting:** Run `.venv\Scripts\python.exe -m ruff check app tests` to confirm zero linter errors.

---

## 8. Rollback Strategy

If an unrecoverable defect occurs during implementation:
- Modified files can be restored via `git restore app/ tests/`.
- Newly created untracked state files can be deleted without impacting baseline prototype or Phase 1/2 work.

---

## 9. Phase 3 Readiness Gate

The project will be certified **READY FOR PHASE 3** if and only if:
- [ ] Fresh startup works cleanly without manual DDL fixtures.
- [ ] Fresh SQLite database initializes schema automatically.
- [ ] Concurrent 10+ worker thread database writes complete with zero `database is locked` deadlocks under `get_db_write()`.
- [ ] Job cancellation halts worker threads cooperatively without Windows file lock errors (`WinError 32`).
- [ ] Interrupted active jobs are recovered on startup and purged from disk.
- [ ] Resource quotas (`MAX_PLAYLIST_ITEMS`) and `client_id` rate limits are enforced.
- [ ] Network stalls are bounded by yt-dlp `socket_timeout`.
- [ ] Error messages in database do not leak internal filesystem paths or stack traces.
- [ ] Playlist progress reports aggregate composite completion percentage.
- [ ] Cover art embedding produces valid JPEG thumbnails in ID3 and MP4 containers.
- [ ] `metadata_service.py` is implemented and verified with SSRF protection.
- [ ] All existing tests + new regression tests pass.
- [ ] Ruff static analysis passes with zero warnings.
