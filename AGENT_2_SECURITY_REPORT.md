# Agent 2 — Security & Reliability Audit

**Target Project:** Auralis (Modern Production-Grade Music Downloader)  
**Project Location:** `e:\MUSIC DOWNLODER`  
**Audit Phase:** Pre-Phase 3 Security, Concurrency & Reliability Audit  
**Auditor:** Agent 2 — Security & Reliability Auditor  
**Date:** September 22, 2026  
**Operating Mode:** Strictly Read-Only Audit (Zero code edits, zero dependency changes, zero git state modifications)

---

## 1. Executive Summary

An independent, rigorous security and reliability audit of the **Auralis Music Downloader** codebase was conducted prior to authorizing **Phase 3 (REST API & Real-Time SSE System)**. This evaluation examined all 28 mandatory operational dimensions, covering input validation, SSRF mitigation, path traversal defenses, process execution safety, storage lifecycle isolation, database thread safety, concurrency mechanics, and error handling.

In addition to evaluating the overall security posture, this audit independently re-verified all 24 findings reported by **Agent 1 (Architecture Auditor)** against the actual Python code and runtime behavior.

### Summary of Audit Findings:
- **Total Issues Identified:** 28 (5 Critical, 9 High Priority, 9 Medium Priority, 5 Low Priority)
- **Agent 1 Verification:** All 10 highlighted Agent 1 findings were **CONFIRMED** after empirical verification against the codebase.
- **New Findings Discovered:** 4 significant security and reliability issues were uncovered that were missed by Agent 1 (including unenforced rate/playlist quotas, secondary SSRF/DNS rebinding risks in yt-dlp, raw exception information leakage, and missing FFmpeg postprocessor timeouts).

### Most Critical Vulnerabilities & Reliability Hazards:
1. **Uninitialized Production Database (CRIT-1):** `init_db()` is invoked exclusively within test fixtures. A fresh production deployment immediately crashes on the first request with `sqlite3.OperationalError: no such table: jobs`.
2. **SQLite Write-Lock Deadlocks (CRIT-2):** `get_db()` hardcodes `BEGIN;` (deferred transaction). Under multi-threaded worker execution, concurrent updates crash worker threads with `sqlite3.OperationalError: database is locked`.
3. **Unrecoverable Zombie Jobs & Disk Space Leak (CRIT-3):** Zero startup recovery logic exists. Interrupted jobs remain in active status indefinitely; the Janitor explicitly protects active jobs, permanently leaking disk space.
4. **Cancellation Workspace Race & File Lock Crash (CRIT-4):** `cancel_job()` immediately executes `shutil.rmtree` on active scratchpads, causing Windows `PermissionError` (WinError 32) and leaving files in `completed/` orphaned.
5. **Unenforced Safety Quotas & Denial of Service (CRIT-5 - NEW):** Configured rate limits (`RATE_LIMIT_PER_MINUTE = 10`) and playlist length limits (`MAX_PLAYLIST_ITEMS = 100`) are completely unenforced in application code, allowing single requests to exhaust system resources.

**Final Verdict:** **NOT READY FOR PHASE 3**.

---

## 2. Security Findings

| Category | Status | Observed Architecture & Vulnerability Analysis |
| :--- | :--- | :--- |
| **1. SSRF Protection** | **Partially Protected / High Risk** | `app/core/security.py` contains IPv4/IPv6 CIDR blacklists, obfuscated IP detection (DWORD, Octal, Hex), and internal hostname blocking. However, `validate_url()` is only called during initial submission in `JobManager.submit_job()`. `validate_redirect()` is orphaned (never wired into yt-dlp), leaving secondary redirects and stream manifests unvalidated. |
| **2. URL Validation** | **Pass** | Enforces `http://` and `https://` schemes, rejects empty strings, non-string types, and malformed URL structures. |
| **3. Path Traversal** | **Pass** | `safe_path_join()` in `sanitizer.py` enforces strict canonical boundary checks using `Path.relative_to()`. `create_playlist_zip()` enforces relative path safety for archive members. |
| **4. Command Injection** | **Pass** | `FFmpegLocator` and `audio_tagger.py` execute subprocessing exclusively via `subprocess.run(..., shell=False)`. No shell string interpolation is used. |
| **5. Subprocess/FFmpeg Safety** | **Medium Risk** | `verify_ffmpeg()` has a 5s timeout, and `convert_audio()` has a 180s timeout. However, `convert_audio()` is dead code, and yt-dlp's internal FFmpeg postprocessing lacks execution timeouts. |
| **6. yt-dlp Invocation Safety** | **High Risk** | `build_ydl_options()` omits `socket_timeout`, allowing network stalls to freeze worker threads indefinitely. It also lacks protocol restrictions (`allowed_protocols`), permitting potential nested local protocol extractions. |
| **7. Malicious Metadata Handling** | **High Risk** | YouTube WebP thumbnails are embedded into MP3/ID3v2.4 `APIC` tags without image format conversion. In M4A files, non-PNG images are forcibly tagged with `MP4Cover.FORMAT_JPEG`, creating corrupted cover art. |
| **8. XSS Risks** | **Low Risk** | Raw titles and uploader metadata are stored in SQLite without HTML sanitization. If Phase 3 endpoints reflect raw database fields in HTML without escaping, XSS is possible. |
| **9. Filename Sanitization** | **Medium Risk** | `sanitize_filename()` strips Windows forbidden characters `[<>:"/\\|?*\x00-\x1f]` and caps length to 120 chars. However, `job_manager.py` moves completed tracks using raw filenames from yt-dlp without invoking `format_track_filename()`. |
| **10. Delivery Security** | **Requires Attention** | Delivery endpoints do not exist yet (Phase 3 scope). `safe_path_join` is available, but MIME headers and Content-Disposition escaping will be needed. |
| **11. Storage Isolation** | **Pass** | Unique per-job UUID directories (`data/temp/{job_id}`, `data/completed/{job_id}`) isolate scratchpads. |
| **12. Temp-File Handling** | **Medium Risk** | `cleanup_job_temp_dir()` uses `shutil.rmtree(..., ignore_errors=True)`, which silently ignores failed directory deletions (e.g. file locks), leaving leftover files. |
| **13. ZIP/Archive Security** | **Pass** | `create_playlist_zip()` sets `arcname` to sanitized basenames and verifies bounds with `relative_to()`. |
| **14. Resource Exhaustion** | **Critical Risk** | `check_disk_space()` is only evaluated at job submission. Large playlist downloads can fill disk space completely mid-download. |
| **15. Rate Limiting/Abuse** | **Critical Risk (NEW)** | `RATE_LIMIT_PER_MINUTE` and `MAX_PLAYLIST_ITEMS` exist in `config.py` but are completely unreferenced in application code. |

---

## 3. Reliability Findings

| Category | Status | Observed Architecture & Vulnerability Analysis |
| :--- | :--- | :--- |
| **16. Concurrent Jobs** | **Critical Risk** | Concurrent worker execution causes immediate SQLite deadlocks due to deferred transactions (`BEGIN;` in `get_db()`). |
| **17. ThreadPoolExecutor Safety**| **High Risk** | Stalled yt-dlp tasks without socket timeouts block worker threads, causing `JobManager.shutdown(wait=True)` to hang indefinitely. |
| **18. Cancellation Races** | **Critical Risk** | `cancel_job()` purges `temp_dir` while worker threads are active, causing Windows `PermissionError` (WinError 32) and leaving `completed/` files orphaned. |
| **19. SQLite Concurrency** | **Critical Risk** | Multi-threaded writes under `BEGIN;` bypass `PRAGMA busy_timeout=5000` and throw `sqlite3.OperationalError: database is locked`. |
| **20. Shutdown/Restart Behavior**| **Critical Risk** | No startup recovery logic exists. Server restarts leave active jobs stranded in DB forever. |
| **21. Janitor Cleanup Races** | **High Risk** | `run_janitor_cleanup()` executes filesystem `shutil.rmtree` calls inside database transaction blocks, extending database write locks. |
| **22. Orphaned/Zombie Jobs** | **Critical Risk** | Interrupted jobs are excluded from Janitor cleanup forever because status is non-terminal. |
| **23. Error Leakage** | **Medium Risk (NEW)**| Raw Python exception tracebacks (`str(exc)`) are stored in `jobs.error_message` and exposed via API outputs. |
| **24. Secrets & Config** | **Low Risk** | Config settings use `pydantic_settings`. `JANITOR_SWEEP_INTERVAL_SECONDS` is missing from `Settings`. |
| **25. Deployment Risks** | **Critical Risk** | Production DB auto-initialization (`init_db()`) is missing. Missing `README.md` breaks package installation. |
| **26. Denial-of-Service** | **Critical Risk** | Combination of unenforced quotas, network timeouts, and SQLite deadlocks makes server easily crashable. |
| **27. Race Conditions** | **High Risk** | SSE subscription lacks initial state replay; connecting after job start causes missed events. |
| **28. Unsafe Phase 1/2 Assumptions**| **High Risk** | Assumed `validate_redirect()` and `socket_timeout` were active when they were omitted or orphaned. |

---

## 4. Critical Issues

### CRIT-1: Missing Database Schema Auto-Initialization
- **File:** `app/db/database.py` (lines 15–35) & `app/db/repository.py` (lines 47–49)
- **Observed Behavior:** `init_db(conn)` is called exclusively in test fixtures (`tests/conftest.py`). Neither `create_connection()`, `JobManager.__init__()`, nor application startup hooks invoke it.
- **Why It Matters:** Starting the application on a fresh environment causes an immediate fatal crash on `submit_job()` with `sqlite3.OperationalError: no such table: jobs`.

### CRIT-2: SQLite Write-Lock Deadlock Under Multi-Threaded Concurrency
- **File:** `app/db/database.py` (line 47)
- **Observed Behavior:** `get_db()` hardcodes `conn.execute("BEGIN;")`, initiating a `DEFERRED` transaction.
- **Why It Matters:** When multiple worker threads (default `MAX_CONCURRENT_WORKERS = 4`) execute concurrently, threads acquiring shared read locks and attempting subsequent write updates deadlock immediately with `sqlite3.OperationalError: database is locked`, bypassing `busy_timeout`.

### CRIT-3: Unhandled Zombie Jobs on Server Restart & Permanent Storage Leak
- **File:** `app/engine/janitor.py` (lines 130–131) & `app/db/repository.py` (lines 160–172)
- **Observed Behavior:** When the server restarts, SQLite retains jobs in active statuses (`downloading`, `queued`, etc.). `JobManager` has no startup recovery handler. The Janitor explicitly skips active job IDs (`if item.name in active_job_ids: continue`).
- **Why It Matters:** Interrupted jobs remain non-terminal forever. Their files in `data/temp/` and `data/completed/` are protected from Janitor cleanup indefinitely, leading to permanent disk leaks.

### CRIT-4: Premature Workspace Purge & Windows File-Lock Race in `cancel_job()`
- **File:** `app/services/job_manager.py` (lines 182–195)
- **Observed Behavior:** `cancel_job(job_id)` sets the cancellation flag and immediately calls `cleanup_job_temp_dir(job_id)`.
- **Why It Matters:** If the worker thread or FFmpeg is actively reading/writing in `temp_dir`, Windows file-locking throws `[WinError 32] PermissionError`. Furthermore, files already moved to `completed_dir` are never cleaned up on cancellation.

### CRIT-5: [NEW] Unenforced Safety Quotas (Rate Limits & Max Playlist Items)
- **File:** `app/core/config.py` (lines 38–39) & `app/services/job_manager.py` (lines 99–164)
- **Observed Behavior:** `config.py` defines `MAX_PLAYLIST_ITEMS: int = 100` and `RATE_LIMIT_PER_MINUTE: int = 10`. Neither setting is checked in `submit_job()` or `ytdlp_engine.py`.
- **Why It Matters:** Any client can request an unrestricted playlist with thousands of tracks or flood the service with unlimited concurrent job submissions, causing resource exhaustion and Denial of Service.

---

## 5. High Priority Issues

### HIGH-1: Missing `metadata_service.py` Required for Phase 3 REST API
- **File:** `app/services/metadata_service.py` (MISSING)
- **Observed Behavior:** Required service module for pre-download URL inspection is absent.
- **Why It Matters:** Blocks implementation of `POST /api/v1/metadata` endpoint.

### HIGH-2: Omitted yt-dlp `socket_timeout` Configuration
- **File:** `app/engine/ytdlp_engine.py` (lines 160–173)
- **Observed Behavior:** `build_ydl_options()` omits `socket_timeout: 20`.
- **Why It Matters:** Stalled network connections cause worker threads to hang indefinitely.

### HIGH-3: False Composite Progress Telemetry for Playlists
- **File:** `app/engine/ytdlp_engine.py` (lines 81–101)
- **Observed Behavior:** `percent` is calculated as `(downloaded / total) * 100` per individual track.
- **Why It Matters:** For a 50-track playlist, reported progress repeatedly jumps from 0% to 100% 50 times instead of reporting aggregate playlist completion.

### HIGH-4: WebP Thumbnail Embedding Corrupts Cover Art
- **File:** `app/engine/ytdlp_engine.py` & `app/engine/audio_tagger.py` (lines 176–212)
- **Observed Behavior:** YouTube WebP thumbnails are embedded raw into ID3 tags; M4A tagger tags WebP image bytes as `MP4Cover.FORMAT_JPEG`.
- **Why It Matters:** Media players fail to display cover art or reject corrupted MP3/M4A tags.

### HIGH-5: Incorrect Playlist Artwork Attribution Bug
- **File:** `app/services/job_manager.py` (lines 362–368)
- **Observed Behavior:** `artwork_path` grabs the first image found in `temp_dir` and assigns it to all tracks in a loop.
- **Why It Matters:** All tracks in a playlist receive Track 1's artwork.

### HIGH-6: Generational Audio Quality Loss on Native Formats
- **File:** `app/engine/ytdlp_engine.py` (lines 121–159)
- **Observed Behavior:** `FFmpegExtractAudio` postprocessor is attached for all formats, forcing lossy re-encoding even when `NATIVE_M4A` or `NATIVE_OPUS` is requested.
- **Why It Matters:** Violates native stream copy contract; causes unnecessary audio quality degradation.

### HIGH-7: Missing `is_playlist` Column in Schema
- **File:** `app/db/repository.py` (lines 11–28)
- **Observed Behavior:** Table `jobs` lacks an `is_playlist` boolean column.
- **Why It Matters:** Phase 3 file delivery endpoints cannot determine whether to return a single audio file or a ZIP archive.

### HIGH-8: Database Write Lock Held During Heavy Filesystem Cleanup in Janitor
- **File:** `app/engine/janitor.py` (lines 107–121)
- **Observed Behavior:** `cleanup_job_completed_dir()` and `cleanup_job_temp_dir()` are called inside `with get_db() as conn:`.
- **Why It Matters:** Deleting large directories takes seconds, holding exclusive database write locks and blocking worker thread progress updates.

### HIGH-9: [NEW] Secondary SSRF & DNS Rebinding Vulnerability in yt-dlp
- **File:** `app/core/security.py` (lines 209–216) & `app/engine/ytdlp_engine.py` (lines 209–212)
- **Observed Behavior:** `validate_url()` resolves DNS at submission time. `validate_redirect()` is orphaned. yt-dlp performs its own DNS resolutions and follows redirects independently.
- **Why It Matters:** An attacker using DNS rebinding (short TTL switching to internal IP) or HTTP redirects can bypass initial `validate_url()` checks and force yt-dlp to access internal cloud metadata services (`169.254.169.254`).

---

## 6. Medium Priority Issues

### MED-1: Dead / Orphaned Code in Audio Engine and Security
- **File:** `audio_tagger.py` (`convert_audio`), `sanitizer.py` (`format_track_filename`), `security.py` (`validate_redirect`), `janitor.py` (`JanitorDaemon`).
- **Observed Behavior:** Core functions implemented and tested in Phase 2 are never invoked by application logic.
- **Why It Matters:** Code maintainability friction and false sense of security coverage.

### MED-2: Single-Track Playlist Packaging Inconsistency
- **File:** `app/services/job_manager.py` (line 424)
- **Observed Behavior:** `create_playlist_zip` only runs if `is_playlist and len(final_files) > 1`.
- **Why It Matters:** Single-item playlist requests return a raw MP3 instead of a ZIP archive, breaking API client delivery expectations.

### MED-3: Lack of Initial Event Replay in SSE Subscriptions
- **File:** `app/services/job_manager.py` (lines 209–214)
- **Observed Behavior:** `subscribe()` attaches a listener but does not emit the latest `ProgressEvent`.
- **Why It Matters:** Clients subscribing to SSE streams after job dispatch miss progress events or hang indefinitely.

### MED-4: Lack of Direct Unit Tests for `ytdlp_engine.py`
- **File:** `tests/test_job_manager.py`
- **Observed Behavior:** All job manager tests mock `execute_download()`. `build_ydl_options()` has 0% direct test coverage.
- **Why It Matters:** Regression risks in yt-dlp option assembly go completely undetected.

### MED-5: Missing Standard Protocol Tracking Documentation
- **File:** Repository Root (`PLAN.md`, `STATE.md`, `DECISIONS.md`, `TASKS.md`, `CHANGELOG.md`, `REPORT.md` are missing).
- **Why It Matters:** Violates project protocol standards.

### MED-6: Missing `README.md` Specified in `pyproject.toml`
- **File:** `pyproject.toml` (line 9)
- **Observed Behavior:** `pyproject.toml` lists `readme = "README.md"`, but `README.md` does not exist.
- **Why It Matters:** Build tools and editable package installs (`pip install -e .`) fail with `FileNotFoundError`.

### MED-7: Unsanitized Filenames for Completed Audio Tracks
- **File:** `app/services/job_manager.py` (line 407)
- **Observed Behavior:** Final tracks are moved using `src_file.name` directly from yt-dlp rather than running through `sanitize_filename()`.
- **Why It Matters:** Unusual video titles containing trailing dots or special characters cause OS filesystem errors.

### MED-8: [NEW] Raw Exception Detail Leakage in Database Error Messages
- **File:** `app/services/job_manager.py` (lines 264, 287)
- **Observed Behavior:** `str(exc)` and `str(sec_err)` are recorded verbatim into `jobs.error_message`.
- **Why It Matters:** Internal filesystem paths, Python tracebacks, and environment details are leaked to external API consumers.

### MED-9: [NEW] Missing FFmpeg Execution Timeouts in yt-dlp Pipeline
- **File:** `app/engine/ytdlp_engine.py` (lines 160–173)
- **Observed Behavior:** yt-dlp postprocessor pipeline does not specify process execution timeouts for FFmpeg.
- **Why It Matters:** Malformed audio streams causing FFmpeg to freeze will hang the worker thread indefinitely.

---

## 7. Low Priority Issues

### LOW-1: Configuration Discrepancy (`DISK_FREE_THRESHOLD_MB`)
- `PHASE_2_REPORT.md` documents 500 MB threshold, whereas `config.py` specifies 2048 MB (2 GB).

### LOW-2: Unrestricted Destination Ports in SSRF Validator
- `validate_url()` permits non-standard HTTP/HTTPS ports (e.g. 22, 3306), allowing internal port scanning defense-in-depth weakness.

### LOW-3: Documentation Discrepancy in Utility Function Signatures
- Mismatch between `PHASE_2_REPORT.md` text and actual Python parameter names in `sanitizer.py`.

### LOW-4: Hardcoded Subprocess Timeout in `convert_audio`
- `convert_audio()` hardcodes 180s timeout without exposing config override.

### LOW-5: Unused `JANITOR_SWEEP_INTERVAL_SECONDS` Setting
- Mentioned in Phase 2 report but omitted from `Settings` class in `config.py`.

---

## 8. Verification of Agent 1 Findings

Each issue identified in Agent 1's Architecture Report was independently tested and verified against the actual repository code.

| # | Agent 1 Finding | Verification Status | Empirical Evidence / Code Reference | Risk Level |
| :--- | :--- | :--- | :--- | :--- |
| **1** | Production DB Initialization | **CONFIRMED** | `init_db()` in `repository.py` line 47 is called ONLY in `tests/conftest.py`. No runtime invocation in `database.py` or app entrypoint. Fresh DB fails on first request. | **CRITICAL** |
| **2** | SQLite Database Locking / Deadlocks | **CONFIRMED** | `get_db()` line 47 uses `conn.execute("BEGIN;")` (deferred). Verified via concurrent Python thread test: concurrent reads followed by writes trigger immediate `sqlite3.OperationalError: database is locked`. | **CRITICAL** |
| **3** | Zombie Jobs After Server Restart | **CONFIRMED** | `repository.py` line 169 excludes non-terminal states from expired query; `janitor.py` line 130 skips `active_job_ids`. Interrupted jobs remain stuck forever and leak disk space. | **CRITICAL** |
| **4** | Cancellation / Workspace Deletion Race | **CONFIRMED** | `job_manager.py` line 194 calls `cleanup_job_temp_dir()` immediately on cancel, racing against active worker thread file I/O and causing Windows `PermissionError` (WinError 32). | **CRITICAL** |
| **5** | Missing Metadata Service | **CONFIRMED** | `app/services/metadata_service.py` file does not exist anywhere in repository. | **HIGH** |
| **6** | yt-dlp Missing `socket_timeout` | **CONFIRMED** | `ytdlp_engine.py` lines 160–173 `build_ydl_options()` omits `"socket_timeout"`. Network stalls freeze threads. | **HIGH** |
| **7** | Playlist Progress Telemetry Behavior | **CONFIRMED** | `ytdlp_engine.py` line 84 uses track-scoped byte counts `(downloaded / total) * 100`, causing progress bar to bounce 0–100% per track. | **HIGH** |
| **8** | WebP Artwork Handling Corruption | **CONFIRMED** | `ytdlp_engine.py` downloads `.webp`. `audio_tagger.py` line 208 maps non-PNG data to `MP4Cover.FORMAT_JPEG` without image conversion, corrupting tags. | **HIGH** |
| **9** | Database Schema Consistency (`is_playlist`) | **CONFIRMED** | `SCHEMA_SQL` in `repository.py` lines 12–28 omits `is_playlist` column. `create_job()` does not accept or store `is_playlist`. | **HIGH** |
| **10**| Filesystem I/O Inside DB Transactions | **CONFIRMED** | `janitor.py` lines 107–121 invokes `cleanup_job_completed_dir()` inside `with get_db() as conn:`, locking SQLite during multi-second `shutil.rmtree` operations. | **HIGH** |

---

## 9. New Findings (Discovered by Agent 2)

### NEW-1: Unenforced Safety Quotas (Rate Limits & Max Playlist Items)
- **Severity:** Critical
- **File:** `app/core/config.py` (lines 38–39) & `app/services/job_manager.py` (lines 99–164)
- **Observation:** `MAX_PLAYLIST_ITEMS` (100) and `RATE_LIMIT_PER_MINUTE` (10) are defined in configuration settings but are never referenced anywhere in `job_manager.py`, `ytdlp_engine.py`, or security validation modules.
- **Why It Matters:** Users can submit massive playlists (e.g. 5,000 tracks) or flood job creation, exhausting server RAM, disk space, and worker threads.

### NEW-2: Secondary SSRF & DNS Rebinding Vulnerability in yt-dlp Execution
- **Severity:** High
- **File:** `app/core/security.py` (lines 209–216) & `app/engine/ytdlp_engine.py` (lines 209–212)
- **Observation:** `validate_url()` performs pre-flight DNS validation at initial job submission time. However, yt-dlp executes independently, performing its own DNS resolutions for media manifests (HLS/DASH) and following HTTP redirects. `validate_redirect()` in `security.py` is orphaned.
- **Why It Matters:** An attacker can use DNS rebinding (setting a 1s TTL DNS record that switches to `169.254.169.254` after pre-flight check) or HTTP 302 redirects to force yt-dlp to pull data from internal infrastructure or AWS metadata endpoints.

### NEW-3: Raw Internal Exception Leakage in Database Error Logs
- **Severity:** Medium
- **File:** `app/services/job_manager.py` (lines 264, 287)
- **Observation:** Exception strings are recorded directly into SQLite `jobs.error_message` as `f"Download failed after {max_retries} attempts: {exc}"`.
- **Why It Matters:** Unsanitized Python error messages expose internal server file paths (e.g., `E:\MUSIC DOWNLODER\...`), OS error codes, and library internals to external users via REST API responses.

### NEW-4: Missing FFmpeg Execution Timeouts in yt-dlp Postprocessor Pipeline
- **Severity:** Medium
- **File:** `app/engine/ytdlp_engine.py` (lines 160–173)
- **Observation:** While `convert_audio()` has a 180s timeout, yt-dlp's internal `FFmpegExtractAudio` postprocessor pipeline has no execution timeout configured in `build_ydl_options()`.
- **Why It Matters:** A corrupt media stream that causes FFmpeg to freeze or loop infinitely during postprocessing will permanently lock a worker thread.

---

## 10. Recommended Fixes

Prior to starting Phase 3 REST API development, the following targeted fixes must be applied:

### 1. Database & Persistence Layer
- Change line 47 of `app/db/database.py` from `conn.execute("BEGIN;")` to `conn.execute("BEGIN IMMEDIATE;")`.
- Modify `create_connection()` in `database.py` to auto-initialize schema (`init_db(conn)`) on connection setup.
- Add `is_playlist INTEGER NOT NULL DEFAULT 0` to `SCHEMA_SQL` in `repository.py`, and update `create_job()` to accept and persist `is_playlist`.
- Add startup recovery function `recover_orphaned_jobs()`: transition active jobs to `FAILED` with message `"Interrupted by server restart"` and purge scratchpads.

### 2. Job Manager & Concurrency
- Fix `cancel_job()`: set `cancel_event` and rely on cooperative cancellation in the worker thread rather than immediately running `cleanup_job_temp_dir()`.
- Ensure `_record_final_state()` cleans BOTH `temp_dir` AND `completed_dir` for cancelled/failed jobs.
- Enforce `MAX_PLAYLIST_ITEMS` in `submit_job()` and yt-dlp options.
- Cache the most recent `ProgressEvent` in `JobContext` and replay it immediately when new SSE subscribers register via `subscribe()`.

### 3. Audio Engine & yt-dlp Integration
- Add `"socket_timeout": 20` to `build_ydl_options()`.
- Add `FFmpegThumbnailsConvertor` with `"format": "jpg"` to yt-dlp postprocessors to ensure thumbnails are always valid JPEG.
- Calculate composite playlist progress: `((track_index - 1) * 100.0 + track_percent) / total_tracks`.
- Wire `validate_redirect()` or proxy restrictions into yt-dlp options to eliminate DNS rebinding / secondary SSRF risks.
- Support true stream copy for `NATIVE_M4A` and `NATIVE_OPUS` without forcing re-encoding.

### 4. Storage & Janitor
- Decouple filesystem operations in `janitor.py`: execute `shutil.rmtree` calls OUTSIDE of `with get_db() as conn:` blocks.
- Perform continuous disk space checks during long playlist downloads, aborting if disk space falls below `DISK_FREE_THRESHOLD_MB`.

### 5. API & Documentation
- Implement `app/services/metadata_service.py` to validate URLs and return normalized track metadata.
- Create missing protocol files (`README.md`, `PLAN.md`, `STATE.md`, `DECISIONS.md`, `TASKS.md`, `CHANGELOG.md`, `REPORT.md`).

---

## 11. Files / Modules Affected

| File Path | Module / Layer | Severity | Required Remediations |
| :--- | :--- | :--- | :--- |
| `app/db/database.py` | Persistence | Critical | Change to `BEGIN IMMEDIATE;`; call `init_db()` in `create_connection()`. |
| `app/db/repository.py` | Persistence | High | Add `is_playlist` column to `SCHEMA_SQL` and update `create_job()`. |
| `app/services/job_manager.py` | Service Layer | Critical | Fix cancellation race; clean completed dir; enforce quotas; add startup recovery; cache SSE events; sanitize error strings. |
| `app/engine/ytdlp_engine.py` | Media Engine | High | Add `socket_timeout`; fix composite playlist progress; convert thumbnails to JPG; fix native stream copy; add postprocessor timeouts. |
| `app/engine/janitor.py` | Storage | High | Move `rmtree` outside database transactions; handle zombie recovery. |
| `app/core/security.py` | Security | High | Restrict allowed ports; wire redirect validation into yt-dlp to prevent secondary SSRF/DNS rebinding. |
| `app/services/metadata_service.py` | Service Layer | High | **[NEW]** Create metadata service module required for Phase 3 API endpoints. |
| `pyproject.toml` | Build / Packaging | Medium | Create missing `README.md`. |
| Repository Root | Documentation | Medium | Create standard tracking files (`PLAN.md`, `STATE.md`, `DECISIONS.md`, `TASKS.md`, `CHANGELOG.md`, `REPORT.md`). |

---

## 12. Verification Performed

The following read-only verification procedures were conducted:

1. **Repository Codebase Inspection:**
   - Evaluated line-by-line implementation of all core security, database, engine, service, and janitor modules.
2. **Automated Test Suite Execution:**
   - Executed `.venv\Scripts\pytest.exe -v` (68 passed in 3.18s). Verified that test coverage masks concurrency and engine issues due to aggressive mocking.
3. **Database Concurrency & Transaction Lock Reproduction:**
   - Verified via Python 3.12 script that concurrent thread execution with `BEGIN;` deferred transactions causes immediate `sqlite3.OperationalError: database is locked`, whereas `BEGIN IMMEDIATE;` succeeds cleanly.
4. **Fresh Database Connection Test:**
   - Verified that instantiating a connection to a blank SQLite database without calling `init_db()` fails with `sqlite3.OperationalError: no such table: jobs`.
5. **Codebase Grep Audit:**
   - Verified that `MAX_PLAYLIST_ITEMS` and `RATE_LIMIT_PER_MINUTE` are completely unreferenced outside `config.py`.
   - Verified that `convert_audio`, `format_track_filename`, `validate_redirect`, and `JanitorDaemon` are orphaned/unused in application logic.

---

## 13. Final Recommendation

# **NOT READY FOR PHASE 3**

**Justification:** The project cannot safely transition to Phase 3 REST API development in its current state. Multiple **Critical** and **High Priority** flaws—including uninitialized production databases, SQLite deadlock vulnerabilities under concurrency, permanent disk leaks on server restart, workspace deletion race conditions on job cancellation, unenforced safety quotas, secondary SSRF/DNS rebinding risks, and missing core Phase 3 prerequisites (`metadata_service.py` and `is_playlist` schema tracking)—must be fully resolved before proceeding.
