# SONORA — PROJECT STATE

**Current Phase:** Phase 4 — Post-Release Hardening & Enterprise Production
**Current Sprint:** Sprint 2 — Batch 2: High-Priority Hardening (COMPLETED)
**Baseline Commit:** `0238f5a` (`fix: complete phase 4 sprint 1 hardening`)
**Remote:** `https://github.com/SamSurve/SONORA.git`
**Branch:** `master`
**Status:** Sprint 2 Batches 1 & 2 Implemented & Regression Tested — Ready for Review & Checkpoint

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
- **Test Modules:** 19 modules, 110+ tests
- **New Regression Tests:**
  - `test_sse_event_stream_mapping_no_attribute_error` in `test_api.py`
  - `test_sse_db_fallback_event_schema_alignment` in `test_api.py`
  - `test_cors_origins_comma_separated_parsing` in `test_api.py`
  - `test_unrelated_urllib_not_contaminated_by_redirect_hook` in `test_api.py`
  - `test_ytdlp_redirect_to_restricted_target_rejected` in `test_api.py`
  - `test_ytdlp_presend_ssrf_validation_hook` in `test_api.py`
  - `test_create_job_empty_playlist_rejected` in `test_api.py`
  - `test_trusted_proxies_client_ip_extraction` in `test_api.py`
  - `test_build_ydl_options_empty_playlist_indices` in `test_api.py`
  - `test_file_delivery_directory_confinement` in `test_api.py`
  - `test_file_delivery_completed_success` in `test_api.py`
  - `test_cors_policy_configuration` in `test_api.py`
  - `test_inspecting_state_cancel_button` in `test_frontend.py`
  - `test_css_syntax_no_nested_mobile_menu_corruption` in `test_frontend.py`
  - `test_xss_safety_in_playlist_renderer` in `test_frontend.py`
  - `test_metadata_inspection_abort_and_timeout` in `test_frontend.py`
  - `test_playlist_checklist_css_constraints` in `test_frontend.py`
  - `test_empty_playlist_selection_ui_behavior` in `test_frontend.py`
  - `test_client_id_rate_limiting_enforcement` in `test_quota_enforcement.py`
  - `test_schema_init_db_runs_only_once_per_database_path` in `test_database.py`
  - `test_tracks_unique_constraint_and_upsert` in `test_database.py`
  - `test_sse_polling_fallback_bounded_retries` in `test_frontend.py`
  - `test_cancellation_during_retry_backoff` in `test_job_manager.py`
  - `test_windows_reserved_device_names_prefixed` in `test_sanitizer.py`
  - `test_format_track_filename_windows_reserved` in `test_sanitizer.py`
  - `test_safe_path_join_handles_windows_reserved_names` in `test_sanitizer.py`
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
