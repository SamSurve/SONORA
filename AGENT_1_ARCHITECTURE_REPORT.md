# Agent 1 — Architecture Audit

**Target Project:** Auralis (Modern Production-Grade Music Downloader)  
**Project Location:** `e:\MUSIC DOWNLODER`  
**Audit Phase:** Pre-Phase 3 Architecture, Integrity & Integration Audit  
**Auditor:** Agent 1 — Architecture Auditor  
**Date:** September 22, 2026  
**Operating Mode:** Strictly Read-Only (Zero code edits, zero dependency changes, zero git state modifications)  

---

## 1. Executive Summary

A comprehensive architectural and code audit of the Auralis Music Downloader was performed to evaluate its readiness prior to initiating **Phase 3 (REST API & Real-Time SSE System)**. The codebase was forensically inspected across all 13 required evaluation dimensions, including repository state, Git hygiene, Phase 1 foundation, Phase 2 download engine, SQLite persistence layer, concurrency and thread safety, worker lifecycles, storage cleanup, security boundaries, and protocol adherence.

The evaluation revealed that while significant groundwork has been laid—notably in input sanitization, dynamic FFmpeg binary discovery, and basic modular separation—the system currently harbors **4 Critical Issues**, **8 High Priority Issues**, **7 Medium Priority Issues**, and **4 Low Priority Issues**. Crucially, several fundamental operational capabilities that were documented as completed in previous phase reports either do not exist, are disconnected, or will cause catastrophic production crashes under multi-threaded real-world execution.

### Most Severe Deficiencies:
1. **Uninitialized Production Database:** Table and index creation (`init_db()`) is called exclusively within test fixtures. A fresh production run will immediately crash on the first user request with `sqlite3.OperationalError: no such table: jobs`.
2. **SQLite Write-Lock Deadlocks Under Concurrency:** `get_db()` hardcodes `BEGIN;` (deferred transaction) rather than `BEGIN IMMEDIATE;`. Under concurrent multi-worker load, threads reading and then writing to SQLite will deadlock, throwing `sqlite3.OperationalError: database is locked` immediately, bypassing busy timeouts.
3. **Zombie Jobs and Permanent Storage Leak on Restart:** There is zero startup recovery logic. Jobs interrupted by server reload or reboot remain in `downloading` status indefinitely. The Janitor explicitly treats them as active and permanently ignores them, resulting in an unrecoverable disk space leak.
4. **Premature Cleanup & Windows File-Lock Race in `cancel_job()`:** Cancellation immediately triggers `shutil.rmtree` on the temp workspace while the worker thread or child processes are actively streaming data, triggering Windows `PermissionError` (WinError 32). Furthermore, any files already moved to the completed directory are completely orphaned.
5. **Absent Pre-requisites for Phase 3:** `app/services/metadata_service.py` does not exist; the `jobs` database table lacks an `is_playlist` column required for file delivery routing; and yt-dlp lacks the promised `socket_timeout`, creating indefinite worker thread hangs.

**Final Verdict:** **NOT READY FOR PHASE 3**. Proceeding to Phase 3 without resolving these architectural flaws will cause widespread API errors, database deadlocks, corrupted media deliveries, and storage exhaustion.

---

## 2. Repository / Architecture Findings

### 2.1 Git Status and Version Control State
- **Git Commit Baseline:** The repository has exactly 1 commit (`fce58b0 chore: establish production architecture foundation`).
- **Uncommitted Modifications:** Two Phase 1 files (`app/db/database.py`, `app/db/repository.py`) have unstaged modifications reflecting Phase 2 additions.
- **Untracked Deliverables:** 13 files from Phase 2 remain untracked by Git, including all Phase 2 engine modules (`archive_packager.py`, `audio_tagger.py`, `janitor.py`, `sanitizer.py`, `ytdlp_engine.py`), the services package (`app/services/`), reports, and test files.
- **Legacy Prototype Preservation:** Verified intact. SHA256 checksums of `app.py`, `music_fixer.py`, `templates/index.html`, and `ffmpeg.exe` match their baseline hashes byte-for-byte.

### 2.2 Protocol and State File Compliance (Master AI Project Protocol)
The repository was audited for adherence to the standard project management protocol files:
- `PLAN.md`: **MISSING** (Replaced by ad-hoc `ARCHITECTURE_PROPOSAL.md` and `IMPLEMENTATION_PLAN.md`).
- `STATE.md`: **MISSING** (Current progress is scattered across narrative completion reports).
- `DECISIONS.md`: **MISSING** (Architectural decisions are not logged in an ADR register).
- `TASKS.md`: **MISSING** (No task backlog tracking completed, active, or pending items).
- `CHANGELOG.md`: **MISSING** (No chronological release or change log exists).
- `REPORT.md`: **MISSING** (Information fragmented across `PHASE_1_REPORT.md` and `PHASE_2_REPORT.md`).
- `README.md`: **MISSING** (Despite being formally referenced in `pyproject.toml` line 9, causing build failures).

### 2.3 Layering and Integration Findings
- **Clean Architecture Boundaries:** Separation exists between `core` (config, constants, logging, security), `db` (connection, repository), `engine` (yt-dlp, FFmpeg, tagger, packager, janitor), and `services` (`job_manager.py`).
- **Dead Code Disconnects:** Several components implemented and tested in Phase 2 are completely orphaned:
  - `convert_audio()` in `app/engine/audio_tagger.py` is never called by `job_manager.py`.
  - `format_track_filename()` in `app/engine/sanitizer.py` is never called by `job_manager.py`.
  - `validate_redirect()` in `app/core/security.py` is never wired into yt-dlp.
  - `JanitorDaemon` in `app/engine/janitor.py` is never instantiated or supervised.

---

## 3. Critical Issues

### CRIT-1: Missing Database Schema Auto-Initialization (`init_db` Never Invoked in Production)
- **Severity:** Critical
- **Impact:** System-wide fatal crash on fresh deployment.
- **Description:** `init_db(conn)` in `app/db/repository.py` creates the `jobs` and `tracks` tables and indexes. However, `init_db()` is called exclusively within test fixtures (`tests/conftest.py`, `tests/test_database.py`, `tests/test_janitor.py`, `tests/test_job_manager.py`). Neither `create_connection()`, `JobManager.__init__()`, nor any application lifecycle hook invokes it. When the application starts with a clean `data/auralis.db`, calling `submit_job()` immediately crashes with `sqlite3.OperationalError: no such table: jobs`.

### CRIT-2: SQLite Write-Lock Deadlock Under Concurrency (`BEGIN;` Deferred vs `BEGIN IMMEDIATE;`)
- **Severity:** Critical
- **Impact:** Background worker thread crashes with `database is locked`.
- **Description:** In `app/db/database.py` line 47, `get_db()` hardcodes `conn.execute("BEGIN;")`. In SQLite, `BEGIN;` starts a `DEFERRED` transaction. When multiple worker threads (up to `MAX_CONCURRENT_WORKERS = 4`) execute concurrently—for example, updating download progress while another thread registers track completion or the Janitor queries jobs—two threads will each acquire a shared read lock. When both subsequently attempt to write (`UPDATE jobs ...`), neither can upgrade to a reserved lock, resulting in an immediate SQLite deadlock. SQLite returns `sqlite3.OperationalError: database is locked` immediately without respecting `PRAGMA busy_timeout`.

### CRIT-3: Unhandled Zombie Jobs on Server Restart & Permanent Storage Leak
- **Severity:** Critical
- **Impact:** Indefinite storage exhaustion and stranded jobs.
- **Description:** If the application process is terminated, reloaded, or crashes while jobs are in `queued`, `fetching_metadata`, `downloading`, `converting`, or `tagging`, there is zero startup reconciliation logic. Upon reboot, `JobManager` has an empty in-memory registry, but SQLite retains the jobs in non-terminal states. Consequently:
  1. `get_active_job_ids(conn)` returns these IDs forever.
  2. `get_expired_jobs(conn)` strictly checks `WHERE status IN ('completed', 'failed', 'cancelled')`, so expired zombie jobs are never selected.
  3. `run_janitor_cleanup()` explicitly protects active IDs: `if item.name in active_job_ids: continue`.
  Any files in `data/temp/{job_id}` and `data/completed/{job_id}` belonging to interrupted jobs are permanently protected and will NEVER be purged.

### CRIT-4: Premature Workspace Purge & Windows File-Lock Race in `cancel_job()`
- **Severity:** Critical
- **Impact:** `PermissionError` crashes and unrecoverable orphaned files in `data/completed/`.
- **Description:** In `app/services/job_manager.py` lines 182–195, calling `cancel_job(job_id)` sets the cancel event, updates SQLite, and immediately calls `cleanup_job_temp_dir(job_id)`. If the worker thread is actively downloading or FFmpeg is actively transcoding, deleting the directory triggers Windows file-locking errors (`[WinError 32] The process cannot access the file because it is being used by another process`). Furthermore, if the job was cancelled during tagging after tracks were moved to `completed_dir`, `cancel_job()` and `_record_final_state()` only clean `temp_dir`—leaving completed files orphaned until TTL expiry.

---

## 4. High Priority Issues

### HIGH-1: Missing `metadata_service.py` Required for Phase 3 API
- **Severity:** High
- **Impact:** Blocks Phase 3 `POST /api/v1/metadata` endpoint implementation.
- **Description:** `app/services/metadata_service.py` was specified in the target architecture to handle pre-download URL inspection. It was omitted from Phase 2. While `extract_media_info()` exists in `ytdlp_engine.py`, it does not invoke `validate_url()` (creating an SSRF vulnerability if called directly) and returns raw yt-dlp dictionary dumps rather than normalized tracklist schemas.

### HIGH-2: Missing yt-dlp `socket_timeout` (Report Claim vs Code Reality)
- **Severity:** High
- **Impact:** Indefinite worker thread hangs on stalled network streams.
- **Description:** `PHASE_2_REPORT.md` Section 2.E explicitly claims that `socket_timeout: 20` and `nocheckcertificate: False` were configured. Inspection of `build_ydl_options()` in `app/engine/ytdlp_engine.py` reveals that neither setting exists in `opts`. A stalled TCP connection to upstream media servers will cause worker threads to hang indefinitely.

### HIGH-3: False Composite Progress in Playlist Downloads
- **Severity:** High
- **Impact:** Erratic progress bar oscillation in Phase 3 SSE and Phase 4 UI.
- **Description:** `PHASE_2_REPORT.md` claims normalized composite progress for playlists. In `app/engine/ytdlp_engine.py` lines 82–85, `percent` is calculated as `(downloaded / total) * 100` using yt-dlp's hook data, which reflects only the individual track currently downloading. For a 50-track playlist, the progress bar will repeatedly bounce from 0% to 100% 50 separate times rather than reporting monotonic aggregate progress.

### HIGH-4: WebP Thumbnail Embedding Corrupts ID3/MP4 Cover Art
- **Severity:** High
- **Impact:** Broken or invisible album art on consumer media players and car head units.
- **Description:** YouTube serves thumbnails primarily as `.webp`. In `ytdlp_engine.py`, `writethumbnail: True` downloads `.webp` files. In `audio_tagger.py`, `_tag_mp3()` embeds raw WebP into ID3v2.4 `APIC` tags (which standard players reject). Worse, `_tag_m4a()` sets `MP4Cover.FORMAT_JPEG` for any non-PNG image, wrapping raw WebP bytes in a container claiming to be JPEG. yt-dlp's `FFmpegThumbnailsConvertor` was not added to the postprocessor pipeline.

### HIGH-5: Playlist Artwork Attribution Bug
- **Severity:** High
- **Impact:** Incorrect album art attached to playlist tracks.
- **Description:** In `job_manager.py` lines 363–368, `artwork_path` is assigned by scanning for the first image found in `temp_dir`. In playlists with track-specific thumbnails, this single image is passed to `tag_audio_file()` for every track in the loop. Track 50 receives Track 1's artwork.

### HIGH-6: Architectural Quality Semantics Violated for "Native Stream Copy"
- **Severity:** High
- **Impact:** Unnecessary generational audio quality loss and slow downloads.
- **Description:** The target architecture guarantees that `NATIVE_M4A` and `NATIVE_OPUS` perform zero re-encoding direct stream copies. However, `ytdlp_engine.py` hardcodes `"format": "bestaudio/best"` and attaches `FFmpegExtractAudio` for all formats. For YouTube sources where Opus is the best stream, selecting `NATIVE_M4A` causes yt-dlp to transcode Opus into AAC (a lossy-to-lossy transcode). Stream copy (`-c:a copy`) and format filtering (`ba[ext=m4a]`, `ba[ext=webm]`) are completely absent.

### HIGH-7: Missing `is_playlist` Flag in Database Schema
- **Severity:** High
- **Impact:** Phase 3 delivery routes cannot determine whether to serve a single audio track or a ZIP archive.
- **Description:** The `jobs` table defined in `app/db/repository.py` has no `is_playlist` boolean column. `create_job()` neither accepts nor persists this flag. In Phase 3, when `GET /api/v1/jobs/{id}` or file delivery endpoints query the database, they cannot verify if a job was intended as a playlist.

### HIGH-8: Database Transactions Wrapping Heavy Filesystem I/O in Janitor
- **Severity:** High
- **Impact:** Extended database write locks during background cleanup cycles.
- **Description:** In `app/engine/janitor.py` lines 107–121, `run_janitor_cleanup()` executes `cleanup_job_completed_dir(job_id)` and `cleanup_job_temp_dir(job_id)` (`shutil.rmtree`) inside `with get_db() as conn:`. Deleting multi-gigabyte directories can take several seconds, during which an exclusive SQLite write lock is held, blocking worker progress updates.

---

## 5. Medium Priority Issues

### MED-1: Dead / Orphaned Code in Engine and Security
- **Severity:** Medium
- **Impact:** Code bloat, misleading test coverage, and maintenance friction.
- **Description:** 
  - `convert_audio()` in `app/engine/audio_tagger.py` (72 lines) is never invoked anywhere in application logic because yt-dlp handles postprocessing.
  - `format_track_filename()` in `app/engine/sanitizer.py` is never called by `job_manager.py`.
  - `validate_redirect()` in `app/core/security.py` is never invoked by any network engine.
  - `JanitorDaemon` in `app/engine/janitor.py` is never instantiated or started outside of unit tests.

### MED-2: Single-Track Playlist Packaging Inconsistency
- **Severity:** Medium
- **Impact:** Route mismatch in Phase 3 `/downloads/{id}/zip`.
- **Description:** In `job_manager.py` line 424, archive packaging executes `if is_playlist and len(final_files) > 1:`. If a playlist contains only 1 track, or the user selects 1 track via `selected_indices`, `final_delivery_path` points to a single `.mp3` file instead of a ZIP archive.

### MED-3: Lack of Initial Event Cache in SSE Subscription
- **Severity:** Medium
- **Impact:** Client EventSource hangs indefinitely waiting for updates.
- **Description:** `subscribe()` in `JobManager` attaches a listener to `JobContext`. If an SSE client connects after the job has started, `JobContext` does not cache or replay the most recent `ProgressEvent`. If the job completed prior to connection, `_active_jobs` has already popped the context, causing the subscription to silently fail and leave the client connection open forever.

### MED-4: Zero Direct Unit Tests for `ytdlp_engine.py`
- **Severity:** Medium
- **Impact:** Engine regressions undetected by test suite.
- **Description:** All tests in `tests/test_job_manager.py` mock `execute_download()`. There is no `test_ytdlp_engine.py` validating `build_ydl_options()`, postprocessor configurations, or progress hooks.

### MED-5: Incomplete Protocol Documentation Compliance
- **Severity:** Medium
- **Impact:** Project state opacity and deviation from Master AI Project Protocol.
- **Description:** The root directory lacks standard protocol tracking artifacts (`PLAN.md`, `STATE.md`, `DECISIONS.md`, `TASKS.md`, `CHANGELOG.md`, `REPORT.md`). Information is scattered across unstructured phase reports.

### MED-6: Missing `README.md` Declared in `pyproject.toml`
- **Severity:** Medium
- **Impact:** `pip install -e .` or build tools fail with `FileNotFoundError`.
- **Description:** `pyproject.toml` line 9 specifies `readme = "README.md"`, but no `README.md` file exists in the repository.

### MED-7: Lack of Destination Filename Sanitization for Tracks
- **Severity:** Medium
- **Impact:** Potential filesystem write errors with unusual YouTube video titles.
- **Description:** In `job_manager.py` line 407, finalized files are moved to `completed_dir` using `src_file.name` directly from yt-dlp, bypassing `sanitize_filename()`.

---

## 6. Low Priority Issues

### LOW-1: Configuration Inconsistency (`DISK_FREE_THRESHOLD_MB`)
- **Severity:** Low
- **Impact:** Documentation discrepancy.
- **Description:** `PHASE_2_REPORT.md` states the default disk free threshold is 500 MB. `app/core/config.py` sets `DISK_FREE_THRESHOLD_MB: int = 2048` (2 GB). Furthermore, the report references `settings.JANITOR_SWEEP_INTERVAL_SECONDS`, which is missing from `Settings`.

### LOW-2: Unrestricted Destination Ports in SSRF Validator
- **Severity:** Low
- **Impact:** Defense-in-depth weakness (port scanning).
- **Description:** `validate_url()` allows arbitrary port numbers (e.g., ports 22, 25, 3306, 6379). It should be restricted to ports 80 and 443 for media extraction.

### LOW-3: Inaccurate Documentation of Utility Signatures
- **Severity:** Low
- **Impact:** Developer confusion.
- **Description:** `PHASE_2_REPORT.md` documents `safe_path_join(base_dir, *paths)` and `format_track_filename(title, artist, track_num, ext)`, whereas actual code signatures are `safe_path_join(base_dir, untrusted_filename)` and `format_track_filename(title, extension, track_index)`.

### LOW-4: Hardcoded Subprocess Timeout in `convert_audio`
- **Severity:** Low
- **Impact:** Potential failure on large FLAC encodings if ever called.
- **Description:** `convert_audio()` hardcodes `timeout=180` seconds without configuration via `settings`.

---

## 7. Phase 3 Risks

If Phase 3 implementation begins without resolving the above issues, the following failures will occur:

```
┌───────────────────────────────────┬─────────────────────────────────────────────────────────────┐
│ PHASE 3 COMPONENT                 │ IMMINENT OPERATIONAL FAILURE                                │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 1. FastAPI App Startup            │ Crashes on first request with `no such table: jobs`         │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 2. POST /api/v1/metadata          │ Missing `metadata_service.py`; SSRF pre-flight bypassed     │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 3. GET /api/v1/jobs/{id}/events   │ SSE streams hang forever if connected post-start;           │
│    (Server-Sent Events)           │ Playlist progress percentages erratic (oscillating 0-100%)  │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 4. Concurrent Downloads           │ SQLite deadlocks with `database is locked` under load       │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 5. GET /api/v1/downloads/{id}/zip │ Crashes if single-track playlist returned raw MP3           │
├───────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ 6. Janitor Storage Lifecycle      │ Server restarts leave zombie files leaking disk permanently;│
│                                   │ Deletions lock SQLite database against API writes           │
└───────────────────────────────────┴─────────────────────────────────────────────────────────────┘
```

---

## 8. Recommended Fixes

The following targeted remediations should be executed prior to starting Phase 3:

### Step 1: Database Hardening & Schema Auto-Initialization
1. In `app/db/database.py`:
   - Change line 47 from `conn.execute("BEGIN;")` to `conn.execute("BEGIN IMMEDIATE;")` to eliminate SQLite write deadlocks.
   - In `create_connection()`, add automated schema verification: invoke `init_db(conn)` idempotently if tables do not exist.
2. In `app/db/repository.py`:
   - Add `is_playlist INTEGER NOT NULL DEFAULT 0` to `SCHEMA_SQL` and update `create_job()` to accept and persist `is_playlist`.
3. Add a startup reconciliation function `recover_orphaned_jobs()`:
   - On application startup, query jobs in `('queued', 'fetching_metadata', 'downloading', 'converting', 'tagging')`, transition them to `JobStatus.FAILED` with error `"Server restarted during processing"`, and purge their scratch directories.

### Step 2: Concurrency & Cancellation Fixes in `JobManager`
1. In `app/services/job_manager.py`:
   - In `cancel_job()`, do NOT immediately delete `temp_dir`. Rely on the cooperative token so the worker thread terminates gracefully before deleting the workspace.
   - When cancelling a queued job whose worker has not started, call `context.future.cancel()`.
   - In `_record_final_state()`, ensure BOTH `cleanup_job_temp_dir(job_id)` and `cleanup_job_completed_dir(job_id)` are executed for `FAILED` and `CANCELLED` states.
   - In `subscribe()`, cache the last emitted `ProgressEvent` in `JobContext` and replay it immediately to new subscribers.

### Step 3: Engine, Thumbnail & Progress Corrections
1. In `app/engine/ytdlp_engine.py`:
   - Add `"socket_timeout": 20` to `opts` in `build_ydl_options()`.
   - Add `FFmpegThumbnailsConvertor` with `"format": "jpg"` to `postprocessors` to ensure cover art is always valid JPEG.
   - Normalize playlist progress: calculate composite progress across tracks using `track_index` and `total_tracks`: `composite_percent = ((track_index - 1) * 100.0 + track_percent) / total_tracks`.
   - Implement true native stream copy options for `AudioFormat.NATIVE_M4A` and `AudioFormat.NATIVE_OPUS`.
2. In `app/services/job_manager.py`:
   - Always produce a ZIP archive for playlist jobs, even if `len(final_files) == 1`.
   - Match thumbnails to individual tracks by stem rather than assigning the first found image to all tracks.

### Step 4: Storage Janitor Decoupling
1. In `app/engine/janitor.py`:
   - Move `cleanup_job_completed_dir()` and `cleanup_job_temp_dir()` OUTSIDE the `with get_db() as conn:` block. Perform directory removals first, then commit SQLite status changes in short transactions.

### Step 5: Implement `metadata_service.py`
1. Create `app/services/metadata_service.py` to wrap `extract_media_info()` with SSRF validation (`validate_url()`) and output formatting adhering to the Phase 3 schema.

### Step 6: Protocol & Hygiene Compliance
1. Create root protocol tracking files: `PLAN.md`, `STATE.md`, `DECISIONS.md`, `TASKS.md`, `CHANGELOG.md`, `REPORT.md`, and `README.md`.

---

## 9. Files / Modules Affected

| File Path | Component | Severity | Description of Required Changes |
| :--- | :--- | :--- | :--- |
| `app/db/database.py` | Persistence | Critical | Change to `BEGIN IMMEDIATE;`; call `init_db()` on new connections. |
| `app/db/repository.py` | Persistence | High | Add `is_playlist` to `SCHEMA_SQL` and `create_job()`. |
| `app/services/job_manager.py` | Service Layer | Critical | Fix cancellation race; clean completed dir on failure; cache SSE events; recover orphaned jobs on boot; always ZIP playlists. |
| `app/engine/ytdlp_engine.py` | Media Engine | High | Add `socket_timeout`; add `FFmpegThumbnailsConvertor`; fix composite playlist progress; fix native stream copy. |
| `app/engine/janitor.py` | Storage | High | Move filesystem `rmtree` outside database transactions; respect zombie recovery. |
| `app/services/metadata_service.py` | Service Layer | High | **[NEW]** Create metadata service for Phase 3 endpoints. |
| `pyproject.toml` | Packaging | Medium | Create missing `README.md`. |
| Repository Root | Project Protocol | Medium | **[NEW]** Establish `PLAN.md`, `STATE.md`, `DECISIONS.md`, `TASKS.md`, `CHANGELOG.md`, `REPORT.md`. |

---

## 10. Evidence

### Finding 1: Uninitialized Database in Production
- **File:** `app/db/database.py` & `app/db/repository.py`
- **Functions:** `create_connection()` (lines 15–35), `init_db()` (lines 47–49)
- **Observation:**
  ```python
  # database.py line 15:
  def create_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
      ...
      conn = sqlite3.connect(...)
      conn.execute("PRAGMA journal_mode = WAL;")
      ...
      return conn  # init_db is NEVER called
  ```
- **Why It Matters:** Fresh installations will fail immediately with `sqlite3.OperationalError: no such table: jobs`. Tested and confirmed via isolated script.

### Finding 2: SQLite Write-Lock Deadlock Under Concurrency
- **File:** `app/db/database.py`
- **Function:** `get_db()` (lines 38–57)
- **Observation:**
  ```python
  # line 47:
  conn.execute("BEGIN;")  # DEFERRED transaction
  ```
- **Why It Matters:** Multi-threaded workers attempting concurrent updates after reading will deadlock. Verified via Python test script: two threads with deferred `BEGIN;` both reading then writing crash with `sqlite3.OperationalError: database is locked`, whereas `BEGIN IMMEDIATE;` succeeds.

### Finding 3: Zombie Jobs and Indefinite Storage Leak
- **File:** `app/engine/janitor.py` & `app/db/repository.py`
- **Functions:** `run_janitor_cleanup()` (lines 101–155), `get_expired_jobs()` (lines 160–172), `get_active_job_ids()` (lines 175–183)
- **Observation:**
  ```python
  # repository.py line 169:
  WHERE status IN ('completed', 'failed', 'cancelled')  # Excludes active states

  # janitor.py lines 130-131:
  if item.name in active_job_ids:
      continue  # Strictly protect actively running jobs
  ```
- **Why It Matters:** Jobs active during a crash or restart remain non-terminal forever. The Janitor treats them as active forever and never deletes their storage folders.

### Finding 4: Race Condition & File-Lock Error in `cancel_job()`
- **File:** `app/services/job_manager.py`
- **Function:** `cancel_job()` (lines 166–207)
- **Observation:**
  ```python
  # lines 182-194:
  context.cancel_event.set()
  update_job_status(...)
  cleanup_job_temp_dir(job_id)  # Immediately runs shutil.rmtree on active workspace!
  ```
- **Why It Matters:** Active worker threads streaming chunks or transcoding audio crash with Windows file-locking `PermissionError`.

### Finding 5: Missing `socket_timeout` in yt-dlp Options
- **File:** `app/engine/ytdlp_engine.py`
- **Function:** `build_ydl_options()` (lines 160–173)
- **Observation:**
  ```python
  opts: dict[str, Any] = {
      "format": "bestaudio/best",
      "outtmpl": outtmpl,
      "ffmpeg_location": str(Path(ffmpeg_bin).parent),
      "writethumbnail": True,
      "noplaylist": not is_playlist,
      "ignoreerrors": is_playlist,
      "quiet": True,
      "no_warnings": True,
      "progress_hooks": [_progress_hook],
      "postprocessor_hooks": [_postprocessor_hook],
      "postprocessors": postprocessors,
  }  # socket_timeout is completely missing
  ```
- **Why It Matters:** Upstream network stalls lock worker threads indefinitely. Directly contradicts `PHASE_2_REPORT.md` claims.

### Finding 6: False Composite Progress for Playlists
- **File:** `app/engine/ytdlp_engine.py`
- **Function:** `_progress_hook()` (lines 81–101)
- **Observation:**
  ```python
  total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
  downloaded = d.get("downloaded_bytes", 0)
  percent = min(100.0, round((downloaded / total) * 100, 1))
  ```
- **Why It Matters:** `downloaded` and `total` are track-scoped in yt-dlp. For playlists, progress resets to 0% on every track transition.

### Finding 7: Missing `is_playlist` Column in Schema
- **File:** `app/db/repository.py`
- **Constant:** `SCHEMA_SQL` (lines 12–28)
- **Observation:** Table `jobs` contains columns `id, url, title, format, quality, status, progress, speed, eta, file_path, file_size, error_message, created_at, completed_at, expires_at`. `is_playlist` is absent.
- **Why It Matters:** Phase 3 API endpoints cannot know whether to stream a single file or a ZIP archive.

---

## 11. Verification Performed

The following inspections, commands, and verification procedures were conducted:
1. **Repository & Git Inspection:**
   - Executed `git status`, `git log -n 10 --format=fuller`, and `git diff` to review all committed and uncommitted changes.
2. **Automated Test Execution:**
   - Ran `.venv\Scripts\pytest.exe -v` across the complete 68-test suite (100% pass rate in 4.98s).
   - Observed that all tests in `test_job_manager.py` mock `execute_download()`, masking engine and concurrency bugs.
3. **Static Analysis & Linting:**
   - Executed `.venv\Scripts\ruff.exe check app tests` (Passed with zero errors).
   - Executed `.venv\Scripts\ruff.exe check .` (Confirmed errors isolated to preserved prototype files).
4. **Database Concurrency & Deadlock Reproduction:**
   - Executed reproduction scripts in Python 3.12 simulating concurrent threads under WAL mode.
   - Proved that `BEGIN;` causes immediate `sqlite3.OperationalError: database is locked`, whereas `BEGIN IMMEDIATE;` resolves deadlocks cleanly.
5. **Fresh Database Initialization Verification:**
   - Tested instantiating a fresh SQLite connection without calling `init_db()`; confirmed failure with `no such table: jobs`.
6. **Codebase Exhaustive Search:**
   - Searched for all calls to `convert_audio`, `format_track_filename`, `validate_redirect`, and `JanitorDaemon`. Confirmed each is orphaned.

---

## 12. Final Recommendation

# **NOT READY FOR PHASE 3**

**Justification:** The project cannot safely transition to Phase 3 in its present state. While the individual utility components function in unit-test isolation, the persistence layer deadlocks under concurrent write loads, fresh deployments crash immediately due to missing schema initialization, interrupted server processes create unpurgeable zombie files, playlist downloads report broken progress telemetry and corrupt album art, and essential Phase 3 pre-requisites (`metadata_service.py` and `is_playlist` schema persistence) are completely absent.

All **Critical** and **High Priority** items identified in this report must be resolved before proceeding with Phase 3 development.
