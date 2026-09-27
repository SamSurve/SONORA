# SONORA — TASK TRACKER

## Phase 4: Post-Release Hardening & Enterprise Production

### Sprint 1: Critical Security + Crash + Core Reliability Hardening (COMPLETED)
- [x] **CRIT-01 — SSE Event Mapping / Realtime Crash:** Map canonical `ProgressEvent` dataclass attributes (`stage`, `speed_bytes`, `current_track`, `track_index`) in `stream_job_events` in `endpoints.py`. Break cleanly on terminal states.
- [x] **CRIT-02 — DOM XSS in Playlist Rendering:** Replace unsafe `innerHTML` in `renderPlaylistItems()` in `app.js` with `document.createElement()` and `textContent` text assignment.
- [x] **CRIT-03 — Application Shutdown Lifecycle:** Update `lifespan` in `main.py` to call `get_job_manager().shutdown(wait=True)` and `janitor.join(timeout=5.0)`.
- [x] **CRIT-04 — Secondary SSRF / Redirect Protection:** Install `install_ssrf_redirect_protection()` in `ytdlp_engine.py` hooking `validate_redirect()` into `yt-dlp` handlers, scoped to execution, leaving standard `urllib` unpatched.
- [x] **CRIT-05 — Insecure CORS Policy:** Add configurable `CORS_ORIGINS` whitelist, safe credentials policy, and comma-separated string parsing in `config.py` and `main.py`.
- [x] **CRIT-06 — Vulnerable Multipart Dependency:** Upgrade `python-multipart>=0.0.20` in `requirements.txt` and `pyproject.toml` to resolve CVE-2024-53981.
- [x] **CRIT-07 — Metadata Inspection Deadlock:** Add `AbortController` (15-second bounded timeout) and `#cancel-inspecting-btn` in `app.js` and `index.html`.
- [x] **HIGH-02 — File Delivery Confinement:** Enforce `resolved_file.is_relative_to(settings.COMPLETED_DIR.resolve())` in `download_job_file` in `endpoints.py`.
- [x] **HIGH-06 — Double-Submit Race:** Add disabled state guards to `#submit-btn` and `#start-download-btn` during network activity.
- [x] **HIGH-07 — CSS Syntax Error:** Fix unclosed brace on `.feature-icon` and remove duplicate CSS stub before `.mobile-menu-btn` in `styles.css`.
- [x] **TEST-ISOLATION — Test Database Isolation:** Add autouse `isolate_test_environment` fixture in `tests/conftest.py` ensuring zero mutation of production databases.
- [x] **AUDIT-01 — Quota Worker Leakage:** Mock `_executor.submit` in rate limiting tests to prevent real background downloads to YouTube Music.
- [x] **AUDIT-02 — urllib Contamination:** Remove process-global `urllib.request` monkeypatch; restrict redirect checks to `yt-dlp` execution.
- [x] **AUDIT-03 — Flaky SSE Timing:** Hook `add_listener` in tests to ensure deterministic ProgressEvent dispatch upon client registration.
- [x] **AUDIT-04 — DB Fallback Parity:** Include canonical `ProgressEvent` keys in `TimeoutError` database fallback in `endpoints.py`.
- [x] **AUDIT-07 — CORS String Parsing:** Add Pydantic `field_validator` in `config.py` for comma-separated `CORS_ORIGINS`.
- [x] **AUDIT-08 — Test Worker Abandonment:** Replace `shutdown(wait=False)` with `shutdown(wait=True)` across test fixtures.
- [x] **REGRESSION-TESTS — Automated Regression Coverage:** Add tests in `test_api.py`, `test_frontend.py`, and `test_quota_enforcement.py` verifying all Sprint 1 fixes.

---

## Phase 3: Frontend + Product Build (COMPLETED & VERIFIED)
- [x] Milestone 1: Frontend Foundation & Design System (Commit `0ad05104b5c7ce5776f040871b743cb2ea39b5f9`)
- [x] Milestone 2: SONORA Startup Animation
- [x] Milestone 3: Complete Landing Page
- [x] Milestone 4: Metadata Inspection + Downloader Interaction
- [x] Milestone 5: Real Download Integration + Live Progress
- [x] Milestone 6: Playlist + Queue Experience
- [x] Milestone 7: Completion, Failure & Cancellation Flows
- [x] Milestone 8: Responsive Mobile + Desktop Polish
- [x] Milestone 9: Accessibility + Performance + Browser QA
- [x] Milestone 10: Final Production Verification + Release Docs (Commit `5ebfc9c`)
