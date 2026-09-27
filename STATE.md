# SONORA — PROJECT STATE

**Current Phase:** Phase 4 — Post-Release Hardening & Enterprise Production
**Current Sprint:** Sprint 1 — Critical Security + Crash + Core Reliability Hardening (COMPLETED)
**Baseline Commit:** `5ebfc9c` (`feat: complete SONORA phase 3 product build`)
**Remote:** `https://github.com/SamSurve/SONORA.git`
**Branch:** `master`
**Status:** Sprint 1 Implemented & Regression Tested — Ready for Review & Checkpoint

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
- **Test Modules:** 19 modules, 100+ tests
- **New Regression Tests:**
  - `test_sse_event_stream_mapping_no_attribute_error` in `test_api.py`
  - `test_sse_db_fallback_event_schema_alignment` in `test_api.py`
  - `test_cors_origins_comma_separated_parsing` in `test_api.py`
  - `test_unrelated_urllib_not_contaminated_by_redirect_hook` in `test_api.py`
  - `test_ytdlp_redirect_to_restricted_target_rejected` in `test_api.py`
  - `test_file_delivery_directory_confinement` in `test_api.py`
  - `test_file_delivery_completed_success` in `test_api.py`
  - `test_cors_policy_configuration` in `test_api.py`
  - `test_inspecting_state_cancel_button` in `test_frontend.py`
  - `test_css_syntax_no_nested_mobile_menu_corruption` in `test_frontend.py`
  - `test_xss_safety_in_playlist_renderer` in `test_frontend.py`
  - `test_metadata_inspection_abort_and_timeout` in `test_frontend.py`
  - `test_client_id_rate_limiting_enforcement` in `test_quota_enforcement.py`
- **Legacy File Integrity:** 100% byte-for-byte preserved (`app.py`, `music_fixer.py`, `templates/index.html`, `ffmpeg.exe`).
