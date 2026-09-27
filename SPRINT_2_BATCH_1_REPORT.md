# SONORA — PHASE 4 SPRINT 2: BATCH 1 REPAIR REPORT

**Date:** September 2026  
**Auditor & Implementer:** Antigravity Autonomous Agent  
**Baseline Commit:** `0238f5a` (`fix: complete phase 4 sprint 1 hardening`)  
**Scope:** Resolution of Critical Reliability Findings CRIT-01 and CRIT-02  
**Status:** **REPAIRED & REGRESSION TESTED**

---

## 1. CRIT-01: SQLite Schema DDL Execution on Connection Acquisition

### Root Cause
In `app/db/database.py:38-42`, `create_connection()` previously executed:
```python
from app.db.repository import init_db
init_db(conn)
```
on every database connection creation. `init_db(conn)` parsed and executed 6 DDL statements (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) and queried `PRAGMA table_info(jobs)` on every connection. Under concurrent worker thread activity and SSE polling, competing DDL commands attempted to acquire exclusive schema locks on SQLite, causing table lock contention, performance degradation, and risk of `sqlite3.OperationalError: database is locked`.

### Fix Implementation
1. **Thread-Safe Path Tracking:** Implemented `_INITIALIZED_DATABASES: set[str]` and a thread-safe `threading.Lock()` (`_init_lock`) in `app/db/database.py`.
2. **One-Time DDL Execution:** `create_connection()` resolves the canonical path of the target database. If the path has not yet been initialized in the current process, it acquires `_init_lock`, double-checks initialization status, executes `init_db(conn)` strictly once, and caches the path in `_INITIALIZED_DATABASES`. All subsequent connections bypass DDL execution with an O(1) set check.
3. **Lifespan Startup Assurance:** Added `ensure_db_initialized(settings.DB_PATH)` to `app/main.py:lifespan()` to guarantee that the production database schema and migrations are initialized upfront at application boot before background workers or requests run.
4. **Test Isolation Support:** Added `reset_db_initialization_cache()` and integrated it into the teardown of the `isolate_test_environment` fixture in `tests/conftest.py`, ensuring every temporary test database auto-initializes cleanly without cross-test leakage.
5. **Preserved Invariants:**
   - First-run auto-initialization for fresh databases: **PRESERVED**
   - Schema and table structures: **PRESERVED**
   - Column migrations (`is_playlist`): **PRESERVED**
   - WAL journal mode and PRAGMAs: **PRESERVED**
   - Concurrency safety and startup zombie recovery: **PRESERVED**

---

## 2. CRIT-02: Unbounded Frontend SSE/Status Polling Fallback

### Root Cause
In `app/static/js/app.js:432-455`, `startPollingFallback(jobId)` executed `setInterval()` querying `/api/v1/jobs/${jobId}` every 2 seconds. When requests returned HTTP 404 (e.g. job expired, invalid ID, or server restarted) or HTTP 500, `res.ok` was false, which did not trigger termination. There was no retry limit, error counter, or backoff, causing the client to poll the backend indefinitely.

### Fix Implementation
1. **Bounded Retry Thresholds:** Added explicit constants in `app/static/js/app.js`:
   - `MAX_POLL_FAILURES = 5` (caps consecutive server 5xx or network errors)
   - `MAX_POLL_404_RETRIES = 2` (aborts quickly if job does not exist on server)
   - `MAX_POLL_ATTEMPTS = 180` (caps total polling duration at 6 minutes)
   - `POLL_INTERVAL_MS = 2000`
2. **Consecutive Error Counters:**
   - On successful responses (`res.ok && json.data`), counters are reset to 0.
   - On 404 responses, increments `consecutive404s`. If $\ge 2$, terminates polling via `closeSSE()` and displays `"Download job was not found or has expired. Please try again."`.
   - On 5xx/network errors, increments `consecutiveErrors`. If $\ge 5$, terminates polling via `closeSSE()` and displays `"Server error while checking download progress."` or network error.
   - If total polling attempts exceed `MAX_POLL_ATTEMPTS`, terminates cleanly with a timeout notification.
3. **Guaranteed Cleanup on Cancel:** Updated `cancelDownload()` with a `finally` block ensuring `closeSSE()` and `setState(States.CANCELLED)` execute reliably even if the cancellation HTTP request fails.

---

## 3. Targeted Regression Tests Added

1. **`tests/test_database.py`:**
   - `test_schema_init_db_runs_only_once_per_database_path`: Verifies that `init_db` is called exactly once on first connection, is cached in `_INITIALIZED_DATABASES`, and is bypassed on subsequent connections and `ensure_db_initialized` calls.
2. **`tests/test_frontend.py`:**
   - `test_sse_polling_fallback_bounded_retries`: Verifies that `app.js` enforces `MAX_POLL_FAILURES`, `MAX_POLL_404_RETRIES`, `MAX_POLL_ATTEMPTS`, consecutive error aborts, and polling duration boundaries.

---

## 4. Verification Results

- **CRIT-01 (DB Connection DDL):** RESOLVED & VERIFIED.
- **CRIT-02 (SSE Polling Fallback):** RESOLVED & VERIFIED.
- **Legacy Protected Files:** 100% byte-for-byte intact (`app.py`, `music_fixer.py`, `templates/index.html`, `ffmpeg.exe`).
- **Working Tree:** Cleaned and ready for checkpoint.

---

## 5. Remaining Sprint 2 Findings

The remaining findings from `PHASE_4_SPRINT_2_AUDIT.md` for subsequent batches:
- **HIGH-01:** Secondary DNS rebinding / TOCTOU window in yt-dlp execution.
- **HIGH-02:** Unhandled Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`) in `sanitizer.py`.
- **HIGH-03:** Empty playlist track selection downloads all tracks.
- **HIGH-04:** Unstyled playlist checklist container causing viewport blowout.
- **HIGH-05:** Missing `UNIQUE(job_id, track_index)` constraint on `tracks` table.
- **HIGH-06:** Non-interruptible synchronous `time.sleep` in worker retry backoff.
- **HIGH-07:** Incomplete reverse proxy trust breaking IP-based rate limiting.
- **MED-01 through MED-11:** Medium findings (ID3v2.3 MP3 tagging, WAV tagging, favicon, WCAG accessibility, dark mode shadows).
