# SONORA — Phase 4 Comprehensive Post-Release Audit Report

**Date:** September 23, 2026  
**Baseline Release Commit:** `5ebfc9c` (`feat: complete SONORA phase 3 product build`)  
**Branch:** `master` | **Remote:** `https://github.com/SamSurve/SONORA.git`  
**Audit Scope:** Full repository deep-dive — Backend Architecture, API Contracts, Downloader Engine, Security & Boundaries, Storage & Janitor, Frontend UI/UX, Browser Behavior, Accessibility (WCAG 2.1 AA), Performance, Concurrency, Testing Suite, Dependencies, Documentation Integrity, and Git State.  
**Auditor:** Autonomous Inspection & Maintenance Agent (Pair Programming with ChatGPT Architect / Project Manager)  
**Execution Policy:** Read-only audit probe. Zero production code modified. Zero commits created. Zero pushes executed.

---

## 1. Executive Summary & Audit Scorecard

The SONORA Phase 3 release represents an impressive milestone: a clean Swiss-inspired frontend design, unified single-page architecture, SQLite WAL persistence with `BEGIN IMMEDIATE` write reservations, cooperative cancellation tokens, isolated scratchpad directories, and a 90/90 passing test suite.

However, an exhaustive, line-by-line inspection of the actual source code, tests, and configuration—independent of previous self-reported summaries—reveals critical defects that directly threaten production stability, security, and user experience.

### Audit Severity Scorecard

```
┌─────────────────────────────────────────────────────────────┐
│                   AUDIT FINDINGS BY SEVERITY                │
├─────────────────────┬───────┬───────────────────────────────┤
│ 🚨 CRITICAL         │   7   │ Immediate crashes / security  │
│ ⚠️ HIGH             │  14   │ Major flaws / bypasses / bugs │
│ 🟡 MEDIUM           │  15   │ Performance / UX / a11y gaps  │
│ 🔵 LOW              │  10   │ Debt / naming / doc anomalies │
├─────────────────────┼───────┼───────────────────────────────┤
│ TOTAL FINDINGS      │  46   │ Fully documented below        │
└─────────────────────┴───────┴───────────────────────────────┘
```

---

## 2. Master Findings Matrix

| Finding ID | Domain | Severity | Title / Summary | Exact File & Line Reference |
|:---|:---|:---:|:---|:---|
| **CRIT-01** | Backend / SSE | 🚨 **CRITICAL** | SSE stream crashes on every progress event (`AttributeError`) | [`endpoints.py#L259-L268`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L259-L268) |
| **CRIT-02** | Frontend / Sec | 🚨 **CRITICAL** | DOM-based XSS vulnerability in playlist item rendering | [`app.js#L244-L249`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L244-L249) |
| **CRIT-03** | Backend / Lifecycle | 🚨 **CRITICAL** | Worker pool and child processes abandoned on server shutdown | [`main.py#L28-L51`](file:///e:/MUSIC%20DOWNLODER/app/main.py#L28-L51) |
| **CRIT-04** | Security / SSRF | 🚨 **CRITICAL** | `validate_redirect()` is dead code; yt-dlp follows redirects unchecked | [`security.py#L209-L217`](file:///e:/MUSIC%20DOWNLODER/app/core/security.py#L209-L217) |
| **CRIT-05** | Security / API | 🚨 **CRITICAL** | Insecure CORS configuration (`allow_origins=["*"]` + `allow_credentials=True`) | [`main.py#L60-L66`](file:///e:/MUSIC%20DOWNLODER/app/main.py#L60-L66) |
| **CRIT-06** | Dependencies | 🚨 **CRITICAL** | Known CVE-2024-53981 & DoS in pinned `python-multipart==0.0.12` | [`requirements.txt#L10`](file:///e:/MUSIC%20DOWNLODER/requirements.txt#L10) |
| **CRIT-07** | Frontend / UX | 🚨 **CRITICAL** | Permanent UI deadlock in `INSPECTING` state on network stall | [`app.js#L165-L188`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L165-L188) |
| **HIGH-01** | Security / SSRF | ⚠️ **HIGH** | TOCTOU DNS rebinding window between pre-flight check and yt-dlp | [`security.py#L110-L150`](file:///e:/MUSIC%20DOWNLODER/app/core/security.py#L110-L150) |
| **HIGH-02** | Security / Storage | ⚠️ **HIGH** | Arbitrary file read in download endpoint (no directory confinement) | [`endpoints.py#L305-L364`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L305-L364) |
| **HIGH-03** | Architecture | ⚠️ **HIGH** | Dual `JobManager` singletons instantiate competing thread pools | [`endpoints.py#L36-L45`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L36-L45), [`job_manager.py#L658`](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py#L658) |
| **HIGH-04** | Security / DoS | ⚠️ **HIGH** | `RateLimiter` monotonic memory leak and reverse proxy DoS lock-out | [`job_manager.py#L67-L90`](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py#L67-L90), [`endpoints.py#L118`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L118) |
| **HIGH-05** | Logic / Quota | ⚠️ **HIGH** | Playlist quota completely bypassed when `selected_indices` is `None` | [`job_manager.py#L194-L200`](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py#L194-L200) |
| **HIGH-06** | Frontend / Concurrency | ⚠️ **HIGH** | Double-submit race condition on inspection and download buttons | [`app.js#L156-L161`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L156-L161), [`app.js#L280-L317`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L280-L317) |
| **HIGH-07** | CSS / Layout | ⚠️ **HIGH** | CSS syntax error (missing brace) corrupts mobile navigation menu | [`styles.css#L790-L812`](file:///e:/MUSIC%20DOWNLODER/app/static/css/styles.css#L790-L812) |
| **HIGH-08** | CSS / Layout | ⚠️ **HIGH** | Zero CSS styles for playlist checklist (container layout blowout) | [`styles.css`](file:///e:/MUSIC%20DOWNLODER/app/static/css/styles.css), [`index.html#L166-L174`](file:///e:/MUSIC%20DOWNLODER/app/static/index.html#L166-L174) |
| **HIGH-09** | Frontend / Network | ⚠️ **HIGH** | Infinite polling loop on HTTP 404/500 errors in fallback mode | [`app.js#L355-L381`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L355-L381) |
| **HIGH-10** | Testing / Isolation | ⚠️ **HIGH** | Test suite pollutes live production SQLite database (`data/auralis.db`) | [`test_api.py`](file:///e:/MUSIC%20DOWNLODER/tests/test_api.py), [`test_quota_enforcement.py`](file:///e:/MUSIC%20DOWNLODER/tests/test_quota_enforcement.py) |
| **HIGH-11** | Dependencies | ⚠️ **HIGH** | `yt-dlp==2024.9.27` is strictly pinned and outdated | [`requirements.txt#L8`](file:///e:/MUSIC%20DOWNLODER/requirements.txt#L8) |
| **HIGH-12** | OS / Compatibility | ⚠️ **HIGH** | Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`) not sanitized | [`sanitizer.py#L11-L47`](file:///e:/MUSIC%20DOWNLODER/app/engine/sanitizer.py#L11-L47) |
| **HIGH-13** | DevOps | ⚠️ **HIGH** | Zero CI/CD pipeline configuration in repository | Repository root (missing `.github/`) |
| **HIGH-14** | DevOps | ⚠️ **HIGH** | Zero Docker containerization (`Dockerfile`, `docker-compose.yml`) | Repository root |
| **MED-01** | Database / Perf | 🟡 **MEDIUM** | DDL schema scripts parsed and executed on every database connection open | [`database.py#L38-L43`](file:///e:/MUSIC%20DOWNLODER/app/db/database.py#L38-L43) |
| **MED-02** | Async / Perf | 🟡 **MEDIUM** | Synchronous SQLite queries block FastAPI async event loop in SSE | [`endpoints.py#L272-L289`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L272-L289) |
| **MED-03** | Concurrency / Perf | 🟡 **MEDIUM** | Synchronous `time.sleep()` in retry backoff starves worker pool | [`job_manager.py#L407-L409`](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py#L407-L409) |
| **MED-04** | Engine / DoS | 🟡 **MEDIUM** | Uncapped flat playlist metadata extraction causes memory exhaustion | [`ytdlp_engine.py#L243-L255`](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py#L243-L255) |
| **MED-05** | Engine / Reliability | 🟡 **MEDIUM** | Brittle track title slicing (`raw_stem[6:]`) corrupts non-conforming titles | [`job_manager.py#L506-L510`](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py#L506-L510) |
| **MED-06** | Tagging | 🟡 **MEDIUM** | WAV conversion supported, but `tag_audio_file()` silently skips `.wav` | [`audio_tagger.py#L141-L149`](file:///e:/MUSIC%20DOWNLODER/app/engine/audio_tagger.py#L141-L149) |
| **MED-07** | Tagging / Windows | 🟡 **MEDIUM** | MP3 tags written as ID3v2.4 (incompatible with Windows Explorer / WMP) | [`audio_tagger.py#L187`](file:///e:/MUSIC%20DOWNLODER/app/engine/audio_tagger.py#L187) |
| **MED-08** | Accessibility | 🟡 **MEDIUM** | Missing ARIA labels on `#url-input`, no live regions, no progressbar roles | [`index.html#L103, L142-L250`](file:///e:/MUSIC%20DOWNLODER/app/static/index.html) |
| **MED-09** | UI / Dark Mode | 🟡 **MEDIUM** | Dark mode shadows invisible (`0.05` opacity); missing `color-scheme` | [`styles.css#L17-L20`](file:///e:/MUSIC%20DOWNLODER/app/static/css/styles.css#L17-L20) |
| **MED-10** | Security / Headers | 🟡 **MEDIUM** | Manual `Content-Disposition` header formatting vulnerable to injection | [`endpoints.py#L362`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L362) |
| **MED-11** | Testing / Coverage | 🟡 **MEDIUM** | Severe test coverage voids in core engine and real Mutagen tagging | [`test_ytdlp_engine.py`](file:///e:/MUSIC%20DOWNLODER/tests/test_ytdlp_engine.py), [`test_audio_tagger.py`](file:///e:/MUSIC%20DOWNLODER/tests/test_audio_tagger.py) |
| **MED-12** | API / Standards | 🟡 **MEDIUM** | `PlaylistQuotaExceededException` returns wrong error code | [`endpoints.py#L146-L153`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L146-L153) |
| **MED-13** | Frontend / Perf | 🟡 **MEDIUM** | Unthrottled `window.scroll` handler causes layout thrashing | [`app.js#L511-L527`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L511-L527) |
| **MED-14** | Dev Tooling | 🟡 **MEDIUM** | No static type checking (`mypy`) or test coverage enforcement (`pytest-cov`) | [`pyproject.toml`](file:///e:/MUSIC%20DOWNLODER/pyproject.toml) |
| **MED-15** | Security / Port | 🟡 **MEDIUM** | `validate_url()` permits arbitrary ports (internal port scanning vector) | [`security.py#L198-L205`](file:///e:/MUSIC%20DOWNLODER/app/core/security.py#L198-L205) |
| **LOW-01** | Dead Code | 🔵 **LOW** | `convert_audio()` in `audio_tagger.py` is completely unused | [`audio_tagger.py#L23-L94`](file:///e:/MUSIC%20DOWNLODER/app/engine/audio_tagger.py#L23-L94) |
| **LOW-02** | Dead Code | 🔵 **LOW** | `list_jobs()`, `get_journal_mode()`, `get_db` alias are uncalled | [`repository.py#L205-L210`](file:///e:/MUSIC%20DOWNLODER/app/db/repository.py#L205-L210), [`database.py`](file:///e:/MUSIC%20DOWNLODER/app/db/database.py) |
| **LOW-03** | Branding | 🔵 **LOW** | "Auralis" naming remnants in `pyproject.toml`, `.env.example`, docstrings | Multiple files |
| **LOW-04** | Configuration | 🔵 **LOW** | Storage and database paths are relative to current working directory | [`config.py#L32-L44`](file:///e:/MUSIC%20DOWNLODER/app/core/config.py#L32-L44) |
| **LOW-05** | Frontend / Assets | 🔵 **LOW** | Missing `favicon.ico`, `apple-touch-icon`, and PWA manifest | [`index.html#L3-L15`](file:///e:/MUSIC%20DOWNLODER/app/static/index.html#L3-L15) |
| **LOW-06** | Documentation | 🔵 **LOW** | `REPORT.md` references non-existent test filenames | [`REPORT.md`](file:///e:/MUSIC%20DOWNLODER/REPORT.md) |
| **LOW-07** | Documentation | 🔵 **LOW** | `.env.example` omits critical runtime environment variables | [`.env.example`](file:///e:/MUSIC%20DOWNLODER/.env.example) |
| **LOW-08** | CSS / Print | 🔵 **LOW** | Missing print stylesheet and Windows high-contrast mode support | [`styles.css`](file:///e:/MUSIC%20DOWNLODER/app/static/css/styles.css) |
| **LOW-09** | Database / Integrity | 🔵 **LOW** | `tracks` table lacks `UNIQUE(job_id, track_index)` constraint | [`repository.py#L31-L39`](file:///e:/MUSIC%20DOWNLODER/app/db/repository.py#L31-L39) |
| **LOW-10** | CSS / Perf | 🔵 **LOW** | Animated `letter-spacing` in startup animation causes CPU layout reflow | [`styles.css#L197-L205`](file:///e:/MUSIC%20DOWNLODER/app/static/css/styles.css#L197-L205) |

---

## 3. Deep Technical Analysis: CRITICAL Findings

### CRIT-01 · SSE Stream Crashes on Every Real-Time Progress Event
- **Location:** [`app/api/v1/endpoints.py`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L259-L268)
- **Problem Statement:** In `stream_job_events()`, the SSE event listener attempts to unpack `ProgressEvent` using attribute names that do not exist:
  ```python
  event = await asyncio.wait_for(queue.get(), timeout=1.0)
  if event:
      event_data = {
          "job_id": event.job_id,
          "status": event.status,              # CRASH: ProgressEvent has `stage`, not `status`
          "speed": event.speed_bytes_per_sec,  # CRASH: ProgressEvent has `speed_bytes`
          "current_title": event.current_title,# CRASH: ProgressEvent has `current_track`
          "completed_tracks": event.completed_tracks, # CRASH: ProgressEvent has `track_index`
      }
      yield f"data: {json.dumps(event_data)}\n\n"
  ```
- **Consequence:** The moment the background worker emits a real-time progress update, an `AttributeError` is raised inside the async generator. The SSE stream terminates with an exception. The browser frontend’s `EventSource` catches this as an error and drops into its polling fallback. The listener-based real-time telemetry was never functioning in production!
- **Root Cause:** Failure to reference the dataclass definition in [`app/engine/ytdlp_engine.py`](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py#L28-L51), which already provides an exact `.to_dict()` helper.
- **Remediation:**
  ```python
  event = await asyncio.wait_for(queue.get(), timeout=1.0)
  if event:
      yield f"data: {json.dumps(event.to_dict())}\n\n"
  ```

---

### CRIT-02 · DOM-Based Cross-Site Scripting (XSS) in Playlist Rendering
- **Location:** [`app/static/js/app.js`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L244-L249)
- **Problem Statement:** In `renderPlaylistItems()`, untrusted track metadata is directly concatenated into DOM HTML:
  ```javascript
  item.innerHTML = `
    <input type="checkbox" class="track-checkbox" data-index="${track.index}" checked>
    <span class="track-num">${String(track.index).padStart(2, '0')}.</span>
    <span class="track-name" style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${track.title}</span>
    <span class="track-dur" style="color:var(--text-muted); font-size:0.8rem;">${formatDuration(track.duration_seconds)}</span>
  `;
  ```
- **Attack Vector:** An attacker publishes a public playlist on YouTube, SoundCloud, or Bandcamp with track titles containing payload strings such as:
  ```html
  <img src=x onerror="fetch('/api/v1/jobs').then(...)">
  ```
  When a SONORA user pastes the playlist URL to inspect or download, the backend returns the raw title, which is directly injected into the DOM via `item.innerHTML`. The malicious script executes in the victim's browser session.
- **Remediation:** Construct elements programmatically or sanitize via `textContent`:
  ```javascript
  const trackName = document.createElement('span');
  trackName.className = 'track-name';
  trackName.textContent = track.title; // Safe textContent assignment
  ```

---

### CRIT-03 · Worker Pool and Child Processes Abandoned on Server Shutdown
- **Location:** [`app/main.py`](file:///e:/MUSIC%20DOWNLODER/app/main.py#L28-L51)
- **Problem Statement:** The FastAPI `lifespan` context manager handles startup and shutdown:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
      ...
      janitor = JanitorDaemon(interval_seconds=300)
      janitor.start()
      app.state.janitor = janitor
      yield
      logger.info("Shutting down SONORA application background services...")
      janitor.stop()
  ```
- **Consequence:** `job_manager.shutdown()` is **never called**! When the server process receives `SIGTERM` or `SIGINT`:
  1. Active `ThreadPoolExecutor` worker threads continue running detached in the background.
  2. Child `ffmpeg.exe` and `yt-dlp` processes are left running, consuming CPU/memory.
  3. Partially written audio files and locked file descriptors remain open on Windows.
  4. `janitor.stop()` sets the event flag but never calls `janitor.join()`, risking process termination midway through a directory purge.
- **Remediation:**
  ```python
  yield
  logger.info("Shutting down SONORA background services...")
  get_job_manager().shutdown(wait=True)
  janitor.stop()
  janitor.join(timeout=5.0)
  ```

---

### CRIT-04 · `validate_redirect()` is Dead Code — yt-dlp Follows Redirects Unchecked
- **Location:** [`app/core/security.py`](file:///e:/MUSIC%20DOWNLODER/app/core/security.py#L209-L217)
- **Problem Statement:** `validate_redirect()` was implemented and tested in `test_security.py`, but it is **never invoked anywhere in the running application**.
- **Vulnerability:** `yt-dlp` utilizes its own internal HTTP transport to follow HTTP 301/302 redirects.
  1. An attacker submits a public URL: `http://attacker-controlled-server.com/song.mp3`.
  2. `validate_url()` resolves `attacker-controlled-server.com` to a public IP and allows job submission.
  3. When `yt-dlp` initiates the download, the server responds with:
     `HTTP 302 Found`  
     `Location: http://169.254.169.254/latest/meta-data/` (AWS/GCP metadata service) or `http://127.0.0.1:8000/internal`.
  4. `yt-dlp` follows the redirect directly into internal network targets, completely bypassing the pre-flight SSRF protection.
- **Remediation:** Configure a custom yt-dlp request opener or patch yt-dlp's redirect handler to validate every redirect target against `validate_redirect()`, or restrict egress networking via an egress proxy.

---

### CRIT-05 · Insecure CORS Configuration
- **Location:** [`app/main.py`](file:///e:/MUSIC%20DOWNLODER/app/main.py#L60-L66)
- **Problem Statement:**
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```
- **Consequence:** Per the W3C CORS specification and modern browser implementations, `Access-Control-Allow-Origin: *` cannot be combined with `Access-Control-Allow-Credentials: true`. Any browser following standard specs will reject credentialed requests. Furthermore, wildcard origins without restriction permit any malicious website open in the user's browser to submit download jobs or probe internal endpoints.
- **Remediation:** Remove `allow_credentials=True` when using wildcard origins, or restrict `allow_origins` to configurable origins via `settings.CORS_ORIGINS`.

---

### CRIT-06 · Known Security Vulnerabilities in Pinned Dependency
- **Location:** [`requirements.txt`](file:///e:/MUSIC%20DOWNLODER/requirements.txt#L10), [`pyproject.toml`](file:///e:/MUSIC%20DOWNLODER/pyproject.toml#L22)
- **Problem Statement:** `python-multipart==0.0.12` is pinned in production dependencies.
- **Vulnerabilities:**
  - **CVE-2024-53981:** Interpretation conflict in `parse_options_header` leading to potential header smuggling and security bypass.
  - **Unbounded Header Processing DoS:** Allows remote attackers to consume excessive CPU and memory via deeply nested or excessively large multipart headers.
- **Remediation:** Upgrade dependency specification to `python-multipart>=0.0.20` (or latest `0.0.32`).

---

### CRIT-07 · Permanent UI Deadlock in `INSPECTING` State
- **Location:** [`app/static/js/app.js`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L165-L188)
- **Problem Statement:** In `handleMetadataInspection(url)`:
  ```javascript
  async function handleMetadataInspection(url) {
    setState(States.INSPECTING);
    try {
      const response = await fetch('/api/v1/metadata', { ... });
      ...
    } catch (err) {
      showError('Network error connecting to SONORA backend service.');
    }
  }
  ```
  1. There is no timeout on `fetch()`.
  2. There is no `AbortController`.
  3. The `#state-inspecting` DOM container has no "Cancel" or "Go Back" button.
- **Consequence:** If the backend extractor hangs, blocks on a slow DNS lookup, or stalls upstream, the frontend UI is permanently locked in the loading spinner state. The user has no way to return to the input screen short of hard-refreshing the entire page.
- **Remediation:** Add an `AbortController` with a 15-second timeout, and add a `<button id="cancel-inspecting-btn">Cancel</button>` inside `#state-inspecting`.

---

## 4. Deep Technical Analysis: HIGH Findings

### HIGH-01 · SSRF TOCTOU (Time-of-Check to Time-of-Use) DNS Rebinding
- **Files:** [`app/core/security.py`](file:///e:/MUSIC%20DOWNLODER/app/core/security.py#L110-L150) → [`app/engine/ytdlp_engine.py`](file:///e:/MUSIC%20DOWNLODER/app/engine/ytdlp_engine.py#L209-L241)
- **Mechanism:** `validate_url()` executes pre-flight DNS resolution during initial job submission. If the domain resolves to a public IP, the job is queued in the database. Seconds or minutes later, when a worker thread in `ThreadPoolExecutor` picks up the job, `yt-dlp` performs an independent DNS resolution.
- **Exploitation:** A DNS server with a 0-second TTL can return a benign public IP on query 1 (validation), and `127.0.0.1` or `169.254.169.254` on query 2 (download). Pre-flight validation alone cannot prevent DNS rebinding without socket-level pinning.

### HIGH-02 · Arbitrary File Read in Download Endpoint
- **File:** [`app/api/v1/endpoints.py`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L305-L364)
- **Mechanism:** In `download_job_file(job_id)`:
  ```python
  file_path_str = job.get("file_path")
  file_path = Path(file_path_str)
  if not file_path.exists() or not file_path.is_file():
      raise HTTPException(...)
  return FileResponse(path=file_path, ...)
  ```
- **Vulnerability:** `file_path` is trusted directly from SQLite without verifying that its canonical resolved path resides within `settings.COMPLETED_DIR`. If a job record has an altered `file_path` (via SQL injection, database tampering, or directory traversal bug), `FileResponse` will serve any file from the host operating system (e.g. `C:\Windows\System32\drivers\etc\hosts` or server credentials).
- **Remediation:**
  ```python
  resolved_path = file_path.resolve()
  if not resolved_path.is_relative_to(settings.COMPLETED_DIR.resolve()):
      raise HTTPException(status_code=403, detail="Access denied")
  ```

### HIGH-03 · Dual `JobManager` Singleton Instances
- **Files:** [`app/api/v1/endpoints.py#L36-L45`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L36-L45) & [`app/services/job_manager.py#L658`](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py#L658)
- **Mechanism:** 
  - `endpoints.py` implements `get_job_manager()` which lazy-creates `_job_manager_instance`.
  - `job_manager.py` executes `job_manager = JobManager()` at the top-level module import.
- **Consequence:** Two independent thread pools are created, each running 4 worker threads (8 total). Each has its own separate `_active_jobs` dictionary. If an endpoint subscribes to events on `_job_manager_instance` while another service queries `job_manager`, active job contexts, cancellation tokens, and progress listeners are split across two disconnected registries.

### HIGH-04 · RateLimiter Memory Leak & Reverse Proxy DoS
- **Files:** [`app/services/job_manager.py#L67-L90`](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py#L67-L90), [`app/api/v1/endpoints.py#L118`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L118)
- **Mechanisms:**
  1. **Memory Leak:** `RateLimiter._history` stores `{client_id: [timestamps]}`. The dictionary never evicts expired keys. On a public service, unique client IPs accumulate indefinitely, leaking memory.
  2. **Proxy DoS:** In `endpoints.py`, `client_ip = request.client.host`. When deployed behind Nginx, Caddy, or Cloudflare, `request.client.host` is always `127.0.0.1` or the proxy IP. All users share the exact same 10 req/min limit. A single user submitting 10 requests locks out every other user globally.

### HIGH-05 · Playlist Quota Bypass When `selected_indices` is `None`
- **File:** [`app/services/job_manager.py#L194-L200`](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py#L194-L200)
- **Mechanism:**
  ```python
  if is_playlist and selected_indices and len(selected_indices) > settings.MAX_PLAYLIST_ITEMS:
      raise PlaylistQuotaExceededException(...)
  ```
  If a client submits `is_playlist=True` but omits `selected_indices` (indicating "download the entire playlist"), `selected_indices` is `None` (falsy). The safety check is skipped entirely, allowing jobs targeting playlists with 1,000+ tracks to be enqueued.

### HIGH-06 · Double Submission Race Condition in UI
- **File:** [`app/static/js/app.js#L156-L161, L280-L317`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js)
- **Mechanism:** Neither the "Inspect" button (`#submit-btn`) nor the "Start Download" button (`#start-download-btn`) is disabled upon user click. A double-click or rapid multi-click dispatches multiple concurrent `POST /api/v1/metadata` or `POST /api/v1/jobs` requests, spawning duplicate background tasks for the same media.

### HIGH-07 · CSS Syntax Error Corrupts Mobile Navigation
- **File:** [`app/static/css/styles.css#L790-L812`](file:///e:/MUSIC%20DOWNLODER/app/static/css/styles.css#L790-L812)
- **Mechanism:**
  ```css
  .feature-icon {
    width: 44px;
    height: 44px;
    background-color: var(--bg-primary);
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--accent-violet);
    margin-bottom: 1rem;
  .mobile-menu-btn {
    display: none;
    ...
  }
  ```
  The rule for `.feature-icon` is missing its closing `}` brace! In browsers that do not support CSS nesting, `.mobile-menu-btn` is completely ignored. In browsers supporting nesting, it is scoped under `.feature-icon`, failing to style the header mobile hamburger button.

### HIGH-08 · Zero CSS Rules for Playlist Checklist Container
- **Files:** [`app/static/css/styles.css`](file:///e:/MUSIC%20DOWNLODER/app/static/css/styles.css), [`app/static/index.html#L166-L174`](file:///e:/MUSIC%20DOWNLODER/app/static/index.html#L166-L174)
- **Mechanism:** There are **zero** CSS rules defined for `.playlist-checklist-container`, `.checklist-header`, `.playlist-items-list`, or `.playlist-item-row`.
- **Result:** The playlist tracklist has no `max-height` and no `overflow-y: auto`. When a user inspects a 50-track album, the card stretches downwards thousands of pixels, pushing the "Start Download" button completely out of sight.

### HIGH-09 · Infinite Polling Loop on HTTP 404/500
- **File:** [`app/static/js/app.js#L355-L381`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L355-L381)
- **Mechanism:** When SSE falls back to `startPollingFallback(jobId)`:
  ```javascript
  context.ssePollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/v1/jobs/${jobId}`);
      const json = await res.json();
      if (res.ok && json.data) {
        ...
      }
    } catch (err) { ... }
  }, 2000);
  ```
  If the server restarts or the job is purged (returning HTTP 404), or if the server crashes (returning HTTP 500), `res.ok` is `false`. The interval is **never cleared**. It continues firing HTTP requests every 2,000ms indefinitely, flooding the server.

### HIGH-10 · Test Suite Pollutes Live Production Database
- **Files:** [`tests/test_api.py`](file:///e:/MUSIC%20DOWNLODER/tests/test_api.py), [`tests/test_quota_enforcement.py`](file:///e:/MUSIC%20DOWNLODER/tests/test_quota_enforcement.py)
- **Mechanism:** In `test_api.py`, `client = TestClient(app)` is instantiated at the module level. `test_job_submission_and_status_retrieval` submits a job through FastAPI. Neither `test_api.py` nor `test_quota_enforcement.py` monkeypatches `settings.DB_PATH`.
- **Result:** Running `pytest` inserts 15+ real job records directly into the local production database (`data/auralis.db` / `data/sonora.db`). Tests do not maintain isolation from production state.

### HIGH-11 · `yt-dlp==2024.9.27` Outdated Extractor Engine
- **File:** [`requirements.txt#L8`](file:///e:/MUSIC%20DOWNLODER/requirements.txt#L8)
- **Mechanism:** `yt-dlp` is pinned to version `2024.9.27`. Streaming platforms (especially YouTube) continuously update player JavaScript, cipher algorithms, and bot challenges. Running an immutable 2024 release breaks extraction across YouTube, SoundCloud, and Vimeo.
- **Remediation:** Use `yt-dlp>=2024.9.27` and provide an automated updater routine or CLI update flag.

### HIGH-12 · Windows Reserved Device Names Not Sanitized
- **File:** [`app/engine/sanitizer.py#L11-L47`](file:///e:/MUSIC%20DOWNLODER/app/engine/sanitizer.py#L11-L47)
- **Discrepancy:** Both `REPAIR_REPORT.md` and `FINAL_REPAIR_VERIFICATION.md` reported that Windows reserved device names were stripped.
- **Reality:** In `sanitizer.py`, `sanitize_filename()` only strips `[<>:"/\\|?*\x00-\x1f]` and trailing spaces/dots. A track titled `"CON"`, `"PRN"`, `"AUX"`, or `"NUL"` causes Windows file operations to fail with `[WinError 87] The parameter is incorrect` or lock the thread.

### HIGH-13 & HIGH-14 · Missing CI/CD and Containerization
- **Absence:** No `.github/workflows/` directory, no Dockerfile, no docker-compose configuration.
- **Consequence:** Regressions in tests, linting, and formatting are not checked automatically on push or pull request. Deploying SONORA requires manual host environment setup.

---

## 5. Technical Analysis: MEDIUM & LOW Findings

### Concurrency & Performance
- **MED-01 (DDL on Every Connection):** In [`app/db/database.py#L41`](file:///e:/MUSIC%20DOWNLODER/app/db/database.py#L41), `create_connection()` invokes `init_db(conn)`, which parses and executes `SCHEMA_SQL` (7 DDL statements) and `PRAGMA table_info` on **every single read and write context opening**. This causes massive disk I/O and table locks under concurrent requests.
- **MED-02 (Async Event Loop Blocking):** In [`app/api/v1/endpoints.py#L272-L274`](file:///e:/MUSIC%20DOWNLODER/app/api/v1/endpoints.py#L272-L274), synchronous SQLite reads are called directly inside the async `event_generator()` without `run_in_threadpool`, blocking the FastAPI event loop for other concurrent users.
- **MED-03 (Worker Starvation in Retry Sleep):** In [`app/services/job_manager.py#L407-L409`](file:///e:/MUSIC%20DOWNLODER/app/services/job_manager.py#L407-L409), `time.sleep(sleep_duration)` blocks the worker thread synchronously. If 4 jobs fail concurrently, all 4 worker threads in the pool are frozen sleeping.
- **MED-13 (Scroll Event Layout Thrashing):** In [`app/static/js/app.js#L511-L527`](file:///e:/MUSIC%20DOWNLODER/app/static/js/app.js#L511-L527), `window.addEventListener('scroll')` queries `querySelectorAll` and checks `offsetTop` on every scroll frame without `requestAnimationFrame` or throttle.

### Media Tagging & Format Compat
- **MED-06 (WAV Metadata Skipped):** [`app/engine/audio_tagger.py#L141-L149`](file:///e:/MUSIC%20DOWNLODER/app/engine/audio_tagger.py#L141-L149) handles `.mp3`, `.m4a`, `.flac`, `.opus`, but silently ignores `.wav`. WAV files receive no metadata chunks or artwork.
- **MED-07 (ID3v2.4 Incompatibility on Windows):** Line 187 saves tags as `tags.save(v2_version=4)`. Windows Explorer and Windows Media Player cannot read ID3v2.4 tags; ID3v2.3 is required for native Windows compatibility.
- **MED-05 (Brittle Track Title Slicing):** Line 506 slices `raw_stem[6:]` assuming filenames strictly match `001 - Title`. If yt-dlp outputs `01. Title` or `1 - Title`, slicing `[6:]` chops off genuine track title characters.

### Accessibility & UX
- **MED-08 (Accessibility Gaps):**
  - `#url-input` has no `<label>` (WCAG 3.3.2).
  - Dynamic states lack `aria-live="polite"` live regions.
  - Progress bar has no `role="progressbar"`, `aria-valuenow`, or `aria-valuemax`.
  - Focus is dropped to `document.body` on state transitions when active containers receive `display: none`.
- **MED-09 (Dark Mode Shadows):** In `styles.css`, shadows use `rgba(0,0,0,0.05)`, which is invisible against `#121212`. Missing `color-scheme: dark` leaves form elements and native scrollbars stark white.
- **MED-12 (Error Code Mismatch):** Catches `PlaylistQuotaExceededException` but returns `STORAGE_LIMIT_EXCEEDED` instead of a quota error code.

### Code Hygiene & Documentation
- **LOW-01 & LOW-02 (Dead Code):** `convert_audio()` in `audio_tagger.py`, `validate_redirect()` in `security.py`, `list_jobs()` in `repository.py`, and `get_journal_mode()` in `database.py` are completely unused.
- **LOW-03 (Branding Remnants):** Package name `auralis` in `pyproject.toml`, headers in `requirements.txt`, `.env.example`, and log prefix strings remain from earlier branding.
- **LOW-09 (Database Constraint):** `tracks` table has no `UNIQUE(job_id, track_index)` constraint, allowing duplicate track rows if a playlist job retries.

---

## 6. Milestone-by-Milestone Verification & Status Matrix

| Milestone | Scope | Implemented | Auto-Tested | Real E2E Verified | Audit Status | Key Remediation Required |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| **M1** | Project Baseline & Tooling | ✅ | ✅ | ✅ | **VERIFIED** | Pinned deps have CVE (CRIT-06) |
| **M2** | Swiss Layout & Startup Animation | ✅ | ✅ | ✅ | **VERIFIED** | Anim letter-spacing reflow (LOW-10) |
| **M3** | Header Nav & Theme Engine | ✅ | ✅ | ✅ | **PARTIAL** | Mobile menu CSS syntax error (HIGH-07) |
| **M4** | URL Hero Card & Format Chips | ✅ | ✅ | ✅ | **PARTIAL** | Missing `<label>`, button double-click (HIGH-06) |
| **M5** | Metadata Inspect & State Machine | ✅ | ✅ | ✅ | **DEFECTIVE** | Deadlock on stall (CRIT-07), DoS (MED-04) |
| **M6** | Ready State & Playlist Checklist | ✅ | ✅ | ✅ | **DEFECTIVE** | DOM XSS (CRIT-02), no CSS styles (HIGH-08) |
| **M7** | Progress Telemetry & SSE Stream | ✅ | ❌ | ⚠️ (DB fallback only) | **CRITICAL BUG** | SSE listener crashes (CRIT-01), polling loop (HIGH-09) |
| **M8** | Completed State & Delivery | ✅ | ⚠️ (error path only) | ✅ | **PARTIAL** | Arbitrary file read risk (HIGH-02) |
| **M9** | Error & Cancellation States | ✅ | ✅ | ✅ | **VERIFIED** | Retry button clears user input |
| **M10** | Polish, Accessibility, Responsive | ✅ | ⚠️ (static HTML only) | ✅ | **PARTIAL** | WCAG 2.1 AA gaps, no live regions (MED-08) |

---

## 7. Recommended Phase 4 Roadmap & Execution Plan

### Sprint 1: Critical Security & Crash Fixes (Immediate)
1. **Fix SSE Attribute Names in `endpoints.py`:** Use `event.to_dict()` to eliminate the `AttributeError` crash on line 261.
2. **Patch DOM XSS in `app.js`:** Replace `item.innerHTML` with safe `textContent` node building in `renderPlaylistItems()`.
3. **Fix Server Lifespan Shutdown:** Call `job_manager.shutdown(wait=True)` and `janitor.join(timeout=5.0)` in `main.py`.
4. **Upgrade `python-multipart`:** Update to `>=0.0.20` in `requirements.txt` and `pyproject.toml` to patch CVE-2024-53981.
5. **Fix Insecure CORS Configuration:** Set explicit `CORS_ORIGINS` or remove `allow_credentials=True` with wildcard origins.
6. **Add Timeout & Abort to Metadata Inspection:** Equip `handleMetadataInspection()` with an `AbortController` (15s timeout) and an in-UI Cancel button.
7. **Enforce Directory Confinement on File Delivery:** Validate `file_path.resolve().is_relative_to(settings.COMPLETED_DIR.resolve())` in `download_job_file()`.

### Sprint 2: Core Reliability & Concurrency Hardening
8. **Consolidate JobManager Singleton:** Remove duplicate instantiation between `endpoints.py` and `job_manager.py`.
9. **Eliminate DDL on Every Connection:** Move `init_db(conn)` out of `create_connection()` and execute it strictly once during application startup.
10. **Fix CSS Syntax Error & Add Playlist Styles:** Fix unclosed `.feature-icon` brace in `styles.css` and implement complete scrolling playlist styling.
11. **Sanitize Windows Reserved Names:** Update `sanitize_filename()` in `sanitizer.py` to filter `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`.
12. **Enforce Playlist Quota on Full Downloads:** Enforce `MAX_PLAYLIST_ITEMS` in `submit_job()` even when `selected_indices` is `None`.
13. **Fix RateLimiter Memory & Reverse Proxy Support:** Add periodic timestamp eviction and trust configured `X-Forwarded-For` proxy headers.
14. **Bound SSE Fallback Polling:** Terminate polling on HTTP 404/500 and cap polling retries.

### Sprint 3: Audio Engine, Tagging & Test Isolation
15. **Isolate Test Databases:** Add an autouse pytest fixture monkeypatching `DB_PATH`, `TEMP_DIR`, and `COMPLETED_DIR` to `tmp_path`.
16. **Update yt-dlp & Add Auto-Updater:** Switch requirement to `yt-dlp>=2024.9.27` and add a background version checker.
17. **Save MP3 Tags as ID3v2.3:** Change `v2_version=4` to `v2_version=3` in `audio_tagger.py` for full Windows Explorer compatibility.
18. **Support WAV Metadata & Artwork:** Implement ID3 or INFO chunk tagging for `.wav` files.
19. **Expand Engine Test Coverage:** Add automated tests exercising real `execute_download()`, format selectors, and SSE streaming.

### Sprint 4: Accessibility, DevOps & Production Packaging
20. **Achieve WCAG 2.1 AA Compliance:** Add form labels, ARIA live regions, `role="progressbar"` attributes, and focus-management hooks.
21. **Set Up CI/CD Workflow:** Create `.github/workflows/ci.yml` running Ruff and Pytest on all PRs.
22. **Dockerize SONORA:** Create a multi-stage `Dockerfile` with FFmpeg, non-root user, and docker-compose deployment.
23. **Add Favicon and PWA Assets:** Place `favicon.ico`, `manifest.json`, and touch icons in `app/static/`.
24. **Standardize Branding:** Clean up legacy "Auralis" references across `pyproject.toml`, `.env.example`, and codebase docstrings.

---

*Report compiled and certified following deep codebase analysis.*
