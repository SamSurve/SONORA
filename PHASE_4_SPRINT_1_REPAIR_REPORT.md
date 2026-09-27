# SONORA — PHASE 4 SPRINT 1 POST-AUDIT REPAIR REPORT

**Date:** 2026-09-27  
**Baseline Commit:** `5ebfc9c` (`feat: complete SONORA phase 3 product build`)  
**Branch:** `master`  
**Status:** All 6 Post-Audit Repairs Implemented & Regression-Tested  

---

## 1. Executive Summary

Following the deep audit documented in `PHASE_4_SPRINT_1_POST_FIX_AUDIT.md`, six specific repairs were identified to ensure rock-solid production reliability, clean test suite isolation, safe SSRF defense-in-depth, and rigorous schema alignment.

All six repairs have been implemented with zero modifications to legacy prototype files (`app.py`, `music_fixer.py`, `templates/index.html`, `ffmpeg.exe`), adhering strictly to all architectural constraints, line length limitations (≤ 100 characters), isort import sorting, and Ruff compliance.

---

## 2. Detailed Root-Cause & Repair Analysis

### Repair 1 (AUDIT-01): Test Worker Leakage & Real yt-dlp Execution
- **Root Cause:** In `tests/test_quota_enforcement.py::test_client_id_rate_limiting_enforcement`, `submit_job()` was invoked 11 times. While public DNS was mocked, `job_mgr._executor.submit` was NOT mocked. This spawned 10 background worker threads into `ThreadPoolExecutor`, which attempted real downloads against YouTube Music, caught upstream network errors, logged exceptions, and triggered retries on closed test loggers.
- **Repair:**
  - Mocked `job_mgr._executor.submit` with `return_value=MagicMock()` in `test_client_id_rate_limiting_enforcement`. Rate limiting and client submission logic are thoroughly validated without spawning any real background execution threads.
  - Replaced `job_mgr.shutdown(wait=False)` with `job_mgr.shutdown(wait=True)` in both quota enforcement tests.

### Repair 2 (AUDIT-02): Global urllib Monkeypatch Removal & Scoped yt-dlp Redirect Protection
- **Root Cause:** `app/engine/ytdlp_engine.py` performed a top-level monkeypatch on standard library `urllib.request.HTTPRedirectHandler.redirect_request` at module import time (`install_ssrf_redirect_protection()`). This globally contaminated all standard-library `urllib` usage across the entire Python process, including third-party libraries and test runners.
- **Repair:**
  - Removed top-level `install_ssrf_redirect_protection()` call on module import.
  - Removed `import urllib.request` from module-level imports.
  - Removed standard-library `urllib.request.HTTPRedirectHandler` monkeypatching entirely.
  - Scoped `install_ssrf_redirect_protection()` strictly to `yt_dlp.networking._urllib.RedirectHandler.redirect_request`.
  - Added explicit calls to `install_ssrf_redirect_protection()` inside `execute_download()` and `extract_media_info()` just before `yt_dlp.YoutubeDL` invocation.
  - Documented the TOCTOU DNS rebinding boundary transparently.

### Repair 3 (AUDIT-03): SSE Stream Completion, ASGITransport Lifecycle & Test Determinism
- **Root Cause:**
  1. *TestClient / ASGITransport Streaming Lifecycle:* In `httpx.ASGITransport` (used by FastAPI's `TestClient`), `client.stream()` executes the ASGI application callable `app(scope, receive, send)` to completion, collecting body parts until `more_body=False` before returning the response. Because `test_sse_event_stream_mapping_no_attribute_error` only emitted a non-terminal `ProgressEvent(stage="downloading")`, and the background worker was mocked, the generator entered an infinite `while True:` loop. The ASGI app never completed, causing `client.stream()` to hang indefinitely before entering the `with` block.
  2. *ASGI `receive()` Contamination:* `stream_job_events` in `endpoints.py` invoked `await request.is_disconnected()` on every loop iteration while Starlette's `StreamingResponse` was concurrently running `listen_for_disconnect(receive)` on the same ASGI receive channel, violating the ASGI single-receiver contract.
  3. *Immediate DB Check for Inactive Contexts:* When a client connected to an already-completed job where `context` was `None`, the generator previously waited on an empty queue for 1.0 second before checking the database.
- **Repair:**
  - In `tests/test_api.py`, updated `emit_after_registration` to emit both the intermediate `downloading` event and a terminal `completed` event upon client registration. This allows `ASGITransport` to finish streaming cleanly, yielding all events into `received_events` where `downloading` attributes are rigorously asserted. Cleaned up `_active_jobs` in a `finally:` block.
  - In `app/api/v1/endpoints.py`, removed concurrent `await request.is_disconnected()` calls in favor of standard `except asyncio.CancelledError:` handling when Starlette's task group cancels on client disconnect.
  - Added an immediate DB inspection branch when `context` is `None`: if the job in SQLite is already in a terminal state, the event is yielded and the stream terminates instantly with 0ms delay.

### Repair 4 (AUDIT-08): ThreadPoolExecutor Worker Abandonment Elimination
- **Root Cause:** `tests/test_job_manager.py` fixture `test_job_mgr` and quota enforcement tests executed `shutdown(wait=False)`. If any job worker thread remained active during test teardown, the fixture exited while threads were still running, causing threads to access closed SQLite connections, write to deleted temporary directories, and log to closed pytest streams.
- **Repair:**
  - Replaced `shutdown(wait=False)` with `shutdown(wait=True)` in `test_job_mgr` fixture (`tests/test_job_manager.py`) and across all quota enforcement tests.

### Repair 5 (AUDIT-04): Database Fallback Event Schema Alignment
- **Root Cause:** In `app/api/v1/endpoints.py::stream_job_events`, the `except TimeoutError:` database fallback event dictionary included `{"job_id", "status", "progress", "speed", "eta", "title", "error_message"}`, but omitted canonical `ProgressEvent` keys expected by the frontend SSE handler (`stage`, `current_title`, `current_track`, `total_tracks`, `completed_tracks`, `track_index`).
- **Repair:**
  - Aligned the database fallback dictionary to provide all canonical fields (`stage`, `current_title`, `current_track`, `total_tracks`, `completed_tracks`, `track_index`), matching the live event dictionary schema and preventing frontend parsing discrepancies.

### Repair 6 (AUDIT-07): Comma-Separated CORS_ORIGINS Configuration Parsing
- **Root Cause:** Pydantic's `BaseSettings` expecting `list[str]` for `CORS_ORIGINS` would raise validation errors if an environment variable passed a comma-separated string (e.g. `CORS_ORIGINS=http://localhost:8000,http://example.com`) rather than a JSON-formatted list string.
- **Repair:**
  - Added `@field_validator("CORS_ORIGINS", mode="before")` to `app/core/config.py` in `Settings`.
  - Parses comma-separated strings into cleaned `list[str]` while preserving list/tuple inputs.

---

## 3. Defense-in-Depth & TOCTOU Boundary Analysis

Application-layer SSRF validation operates by resolving hostnames and checking resulting IPs against private/reserved ranges before initiating requests:
1. **Pre-flight URL validation (`validate_url`):** Blocks non-HTTP(S) schemes, private IP literals, and hostnames resolving to private/reserved IP blocks before metadata extraction or job creation.
2. **Redirect protection (`install_ssrf_redirect_protection`):** Inspects redirect targets within yt-dlp's networking layer, preventing 3xx hops to internal or loopback destinations.
3. **DNS Rebinding (TOCTOU) Boundary:** Hostname resolution performed during validation and subsequent socket connections performed by HTTP engines occur in separate DNS lookups. Full elimination of DNS rebinding requires socket-level IP pinning. The current architecture enforces robust defense-in-depth across pre-flight validation and redirect handlers without polluting the process-global runtime.

---

## 4. Regression Test Matrix

| Test Identifier | File | Focus Area | Status |
| :--- | :--- | :--- | :--- |
| `test_sse_event_stream_mapping_no_attribute_error` | `tests/test_api.py` | Deterministic ProgressEvent SSE delivery | **PASS** |
| `test_sse_db_fallback_event_schema_alignment` | `tests/test_api.py` | DB fallback event schema parity | **PASS** |
| `test_cors_origins_comma_separated_parsing` | `tests/test_api.py` | Comma-separated CORS env parsing | **PASS** |
| `test_unrelated_urllib_not_contaminated_by_redirect_hook` | `tests/test_api.py` | Standard library urllib unpatched | **PASS** |
| `test_ytdlp_redirect_to_restricted_target_rejected` | `tests/test_api.py` | yt-dlp redirect SSRF protection | **PASS** |
| `test_client_id_rate_limiting_enforcement` | `tests/test_quota_enforcement.py` | Rate limiting without worker leakage | **PASS** |
| `test_playlist_max_items_quota_enforcement` | `tests/test_quota_enforcement.py` | Quota enforcement with clean shutdown | **PASS** |
| `test_job_mgr` fixture teardown | `tests/test_job_manager.py` | Await worker shutdown (`wait=True`) | **PASS** |

---

## 5. Legacy Prototype Verification

All legacy prototype files remain 100% byte-for-byte identical to baseline:
- `app.py`: UNCHANGED
- `music_fixer.py`: UNCHANGED
- `templates/index.html`: UNCHANGED
- `ffmpeg.exe`: UNCHANGED

---

## 6. Current Repository Status

- **Uncommitted Changes:** Only intended Phase 4 Sprint 1 hardening and post-audit repairs.
- **Git Commit / Push:** NOT committed, NOT pushed, awaiting user gate check.
