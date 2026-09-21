# Phase 2 Implementation Report: Asynchronous Download Engine & Storage Lifecycle

**Date:** September 22, 2026  
**Status:** Complete & Verified  
**Target Milestone:** Phase 2 — Engine, Services, Storage Lifecycle & Processing Pipeline  
**Previous Baseline Commit:** `fce58b0d4ca2b393ea575809051a650be074031b`  

---

## 1. Executive Summary

Phase 2 of the production overhaul for the Auralis Music Downloader has been successfully implemented and verified. This phase establishes the core asynchronous media processing engine, format conversion pipeline, tagging system, storage lifecycle janitor, and central job manager service directly beneath the forthcoming Phase 3 FastAPI web layer.

All engine components operate strictly with `shell=False` for subprocess execution, enforce isolated per-job workspaces (`data/temp/{job_id}` and `data/completed/{job_id}`), feature path traversal defenses, support cooperative job cancellation via `threading.Event`, and adhere to strict audio format quality semantics (lossless FLAC/ALAC vs. lossy MP3/AAC/Opus without misleading quality assertions).

The test suite expanded from 35 tests to **64 total tests**, with **100% passing in 21.47s**. Ruff linting and code formatting pass with **zero warnings/errors across 29 files**. All legacy files (`app.py`, `music_fixer.py`, `templates/index.html`, `ffmpeg.exe`) remain **100% byte-for-byte identical**.

---

## 2. Implemented Architecture & Component Breakdown

### A. Media Sanitization & Security (`app/engine/sanitizer.py`)
- **`sanitize_filename(name: str, max_length: int = 120) -> str`**:
  - Strips illegal Windows characters (`< > : " / \ | ? *`) and control characters (`\x00` through `\x1f`).
  - Truncates whitespace and trailing periods/spaces that violate Windows filesystem conventions.
  - Enforces length bounding (max 120 characters) without breaking file extensions.
  - Provides a safe fallback name (`track`) if the resulting string is blank or non-string.
- **`format_track_filename(title: str, artist: str, track_num: int | None, ext: str) -> str`**:
  - Automatically structures track filenames as `{track_num:02d} - {artist} - {title}.{ext}` for playlist items or `{artist} - {title}.{ext}` for single tracks.
- **`safe_path_join(base_dir: Path, *paths: str | Path) -> Path`**:
  - Defends against path traversal attacks (`../`, absolute path injections) by resolving canonical paths and asserting that resolved child paths reside strictly within the expected `base_dir`.

### B. Audio Conversion & Metadata Tagging (`app/engine/audio_tagger.py`)
- **FFmpeg Transcoding Pipeline (`convert_audio`)**:
  - Invokes FFmpeg via `subprocess.run` with `shell=False` exclusively.
  - Dynamically discovers the verified binary using Phase 1's `get_ffmpeg_path()`.
  - Maps target formats accurately:
    - **MP3**: Libmp3lame with CBR/VBR configurations (`-q:a 0` or `-b:a 320k`).
    - **M4A / AAC**: AAC encoding (`-c:a aac -b:a 256k`).
    - **FLAC**: Lossless compression container (`-c:a flac`). Does not fabricate high-frequency data from lossy YouTube opus/m4a source streams.
    - **Opus**: Native libopus codec (`-c:a libopus -b:a 160k`).
    - **WAV**: Uncompressed PCM audio (`-c:a pcm_s16le`).
- **Mutagen Tagging System (`tag_audio_file`)**:
  - **ID3v2.4 (MP3)**: Writes `TIT2` (title), `TPE1` (artist), `TALB` (album), `TRCK` (track index/total), `TDRC` (year), and `APIC` (embedded JPEG/PNG artwork).
  - **MP4 / M4A**: Writes `\xa9nam`, `\xa9ART`, `\xa9alb`, `trkn`, `\xa9day`, and `covr` (MP4Cover).
  - **FLAC**: Employs `mutagen.flac.Picture` with type 3 (Cover Front) and Vorbis comments.
  - **Ogg / Opus**: Writes Vorbis comments and base64-encoded `METADATA_BLOCK_PICTURE`.
  - Non-fatal degradation: Tagging or artwork embedding errors log warnings and allow the converted audio file to complete safely rather than failing the user's download.

### C. Playlist Archive Packager (`app/engine/archive_packager.py`)
- **`create_playlist_zip(completed_dir: Path, zip_filename: str, progress_callback) -> Path`**:
  - Scans the completed job folder for valid audio tracks (`.mp3`, `.m4a`, `.flac`, `.opus`, `.wav`, `.aac`).
  - Excludes temporary artifacts (`.part`, `.ytdl`, `.tmp`) and hidden files.
  - Streams audio files into a compressed `zipfile.ZipFile` archive using `zipfile.ZIP_DEFLATED`.
  - Applies `safe_path_join` to prevent zip directory traversal and reports real-time packaging progress to subscribers.

### D. Storage Lifecycle & Janitor Daemon (`app/engine/janitor.py`)
- **Directory Isolation**:
  - `get_job_temp_dir(job_id)`: Generates `data/temp/{job_id}` for ephemeral chunk downloads and conversion scratch files.
  - `get_job_completed_dir(job_id)`: Generates `data/completed/{job_id}` for final converted tracks and zip archives.
- **Disk Threshold Enforcement (`check_disk_space`)**:
  - Uses `shutil.disk_usage` to verify available storage against `settings.DISK_FREE_THRESHOLD_MB` (default 500 MB).
  - Rejects new jobs if free space falls below threshold.
- **TTL Expiration Sweep (`run_janitor_cleanup`)**:
  - Queries database for jobs where `expires_at <= now` and status is non-active (`completed`, `failed`, `cancelled`).
  - Purges workspace directories (`data/temp/{job_id}` and `data/completed/{job_id}`) using `shutil.rmtree`.
  - Updates job status in SQLite repository to `expired` with `file_path = NULL`.
- **Background Daemon (`JanitorDaemon`)**:
  - Runs in a low-priority daemon thread with configurable sweep intervals (`settings.JANITOR_SWEEP_INTERVAL_SECONDS`, default 60s).
  - Provides thread-safe start, loop execution, and graceful termination.

### E. yt-dlp Download Engine (`app/engine/ytdlp_engine.py`)
- **`execute_download(job_id, url, target_format, is_playlist, temp_dir, cancel_event, progress_callback)`**:
  - Configures `yt_dlp.YoutubeDL` with secure, non-interactive options:
    - `noplaylist`: dynamically toggled based on request mode.
    - `extract_flat`: `False` for active downloads, handles playlist discovery.
    - `socket_timeout`: 20 seconds.
    - `nocheckcertificate`: `False` (strict SSL verification).
    - `ignoreerrors`: `True` for playlists (prevents a single geo-blocked or deleted video from killing a 100-track playlist).
  - **Cooperative Cancellation**:
    - Progress hooks inspect `cancel_event.is_set()` during download chunks and metadata extraction.
    - Raises `DownloadCancelledException` immediately to abort download without leaving orphaned subprocesses.
  - **Normalized Progress Tracking**:
    - Emits structured `ProgressEvent` instances (`status`, `percent`, `speed`, `eta`, `track_index`, `total_tracks`).
    - Accurately tracks composite progress for multi-track playlists.

### F. Job Coordinator & Lifecycle Manager (`app/services/job_manager.py`)
- **Central Concurrency Control**:
  - Configurable `concurrent.futures.ThreadPoolExecutor` bounded by `settings.MAX_CONCURRENT_WORKERS` (default 4 workers).
  - Thread-safe job registry (`JobRecord`) holding cancellation events and broadcast listeners.
- **Job Submission & Flow**:
  1. Validates URL against deep SSRF protection (`validate_url(url, resolve_dns=True)`).
  2. Asserts disk capacity (`check_disk_space()`).
  3. Generates UUID and persists initial job record into SQLite (`queued`).
  4. Submits asynchronous job worker task to thread pool.
- **Retry Mechanism**:
  - Automatically catches transient network exceptions (`yt_dlp.utils.DownloadError`, network timeouts) and retries up to `settings.MAX_JOB_RETRIES` (default 3) with exponential backoff (`RETRY_BACKOFF_FACTOR`).
  - Permanent failures, non-transient errors, and security violations fail immediately without wasteful retries.
- **Event Broadcasting**:
  - Thread-safe pub/sub engine allows API consumers to subscribe `Queue[dict]` listeners to any active job.
  - Seamlessly bridges worker thread progress events to real-time client notifications (ready for Phase 3 SSE).

### G. Persistence Layer Enhancements (`app/db/repository.py` & `app/db/database.py`)
- Added `update_track_status` for granular playlist item state transitions.
- Added `get_expired_jobs` with parameterized cutoff timestamps and active-job exclusion.
- Added `mark_job_expired` for atomic status transition upon file purge.
- Added `list_jobs` with pagination (`limit`, `offset`) ordered by creation timestamp.
- Updated `create_connection` to defensively handle both `Path` and `str` types.

---

## 3. Project File Tree (Post-Phase 2)

```text
E:\MUSIC DOWNLODER\
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── README.md
├── PROJECT_AUDIT_REPORT.md
├── ARCHITECTURE_PROPOSAL.md
├── IMPLEMENTATION_PLAN.md
├── PHASE_1_REPORT.md
├── PHASE_2_REPORT.md             # [NEW] This report
│
├── app.py                        # [PRESERVED] Legacy prototype (byte-for-byte identical)
├── music_fixer.py                # [PRESERVED] Legacy script (byte-for-byte identical)
├── ffmpeg.exe                    # [PRESERVED] Legacy FFmpeg binary (byte-for-byte identical)
├── downloads\                    # [PRESERVED] Legacy storage directory
├── templates\
│   └── index.html                # [PRESERVED] Legacy template (byte-for-byte identical)
│
├── app\                          # New Production Modular Architecture
│   ├── __init__.py
│   │
│   ├── core\                     # Core Foundation
│   │   ├── __init__.py
│   │   ├── config.py             # App settings (Pydantic Settings)
│   │   ├── constants.py          # Enums & Status Constants
│   │   ├── logging.py            # Structured logging
│   │   └── security.py           # Comprehensive SSRF & DNS rebinding protection
│   │
│   ├── db\                       # Persistence Layer
│   │   ├── __init__.py
│   │   ├── database.py           # SQLite WAL connection manager
│   │   └── repository.py         # Job/track schema DDL & CRUD operations
│   │
│   ├── engine\                   # Media & Utility Engine
│   │   ├── __init__.py
│   │   ├── archive_packager.py   # [NEW] Multi-track ZIP packager with traversal checks
│   │   ├── audio_tagger.py       # [NEW] FFmpeg converter & Mutagen metadata/artwork tagger
│   │   ├── ffmpeg_locator.py     # Dynamic FFmpeg resolution
│   │   ├── janitor.py            # [NEW] Storage isolation, disk check & TTL cleanup daemon
│   │   ├── sanitizer.py          # [NEW] Cross-platform filename sanitization & safe paths
│   │   └── ytdlp_engine.py       # [NEW] yt-dlp wrapper with progress & cancellation
│   │
│   └── services\                 # Application Services
│       ├── __init__.py
│       └── job_manager.py        # [NEW] Thread pool coordinator, retries, cancellation & pub/sub
│
└── tests\                        # Automated Test Suite (64 tests, 100% passing)
    ├── __init__.py
    ├── conftest.py               # Fixtures (temp_db_path, test_db_conn)
    ├── test_archive_packager.py  # [NEW] ZIP packaging & traversal tests (3 tests)
    ├── test_audio_tagger.py      # [NEW] FFmpeg args, format commands & Mutagen tagging tests (7 tests)
    ├── test_database.py          # WAL mode, schema DDL, rollback & CRUD (7 tests)
    ├── test_ffmpeg_locator.py    # FFmpeg discovery, custom paths & verification (6 tests)
    ├── test_janitor.py           # [NEW] Storage isolation, cleanup lifecycle & daemon tests (4 tests)
    ├── test_job_manager.py       # [NEW] Job lifecycle, playlist zip, cancel, retries & SSRF tests (9 tests)
    ├── test_preservation.py      # Legacy file cryptographic hashes & runnability (4 tests)
    ├── test_sanitizer.py         # [NEW] Windows forbidden chars, lengths & safe_path_join (6 tests)
    └── test_security.py          # SSRF CIDR blacklists, DNS rebinding & redirects (18 tests)
```

---

## 4. Verification & Validation Results

### A. Test Suite Status
All **64 automated tests** pass with zero failures:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.7, pytest-8.3.3, pluggy-1.6.0 -- .venv\Scripts\python.exe
plugins: anyio-4.15.1, asyncio-0.24.0
collected 64 items

tests/test_archive_packager.py::TestArchivePackager::test_package_valid_playlist PASSED [  1%]
tests/test_archive_packager.py::TestArchivePackager::test_no_audio_files_raises_error PASSED [  3%]
tests/test_archive_packager.py::TestArchivePackager::test_archive_excludes_temp_and_partial_files PASSED [  4%]
tests/test_audio_tagger.py::TestAudioConversionPipeline::test_missing_input_file_raises_error PASSED [  6%]
tests/test_audio_tagger.py::TestAudioConversionPipeline::test_ffmpeg_command_args_and_no_shell PASSED [  7%]
tests/test_audio_tagger.py::TestAudioConversionPipeline::test_flac_conversion_command PASSED [  9%]
tests/test_audio_tagger.py::TestAudioConversionPipeline::test_ffmpeg_failure_raises_runtime_error PASSED [ 10%]
tests/test_audio_tagger.py::TestMetadataAndArtworkTagging::test_tagging_missing_file_returns_false PASSED [ 12%]
tests/test_audio_tagger.py::TestMetadataAndArtworkTagging::test_tag_mp3_metadata_and_artwork PASSED [ 14%]
tests/test_audio_tagger.py::TestMetadataAndArtworkTagging::test_tag_flac_metadata PASSED [ 15%]
tests/test_database.py::TestDatabaseConnectionAndWAL::test_wal_journal_mode_enabled PASSED [ 17%]
tests/test_database.py::TestDatabaseConnectionAndWAL::test_context_manager_transaction_commit PASSED [ 18%]
tests/test_database.py::TestDatabaseConnectionAndWAL::test_context_manager_rollback_on_error PASSED [ 20%]
tests/test_database.py::TestRepositoryOperations::test_idempotent_schema_creation PASSED [ 21%]
tests/test_database.py::TestRepositoryOperations::test_create_and_retrieve_job PASSED [ 23%]
tests/test_database.py::TestRepositoryOperations::test_update_job_status_and_completion PASSED [ 25%]
tests/test_database.py::TestRepositoryOperations::test_tracks_cascade_deletion PASSED [ 26%]
tests/test_ffmpeg_locator.py::TestFFmpegVerification::test_verify_nonexistent_file PASSED [ 28%]
tests/test_ffmpeg_locator.py::TestFFmpegVerification::test_verify_non_ffmpeg_file PASSED [ 29%]
tests/test_ffmpeg_locator.py::TestFFmpegVerification::test_verify_existing_root_ffmpeg PASSED [ 31%]
tests/test_ffmpeg_locator.py::TestFFmpegResolutionOrder::test_successful_discovery PASSED [ 32%]
tests/test_ffmpeg_locator.py::TestFFmpegResolutionOrder::test_custom_path_precedence PASSED [ 34%]
tests/test_ffmpeg_locator.py::TestFFmpegResolutionOrder::test_missing_ffmpeg_raises_exception PASSED [ 35%]
tests/test_janitor.py::TestJobStorageIsolation::test_job_workspace_directories_are_isolated PASSED [ 37%]
tests/test_janitor.py::TestJanitorCleanupLifecycle::test_cleanup_expired_jobs_in_database PASSED [ 39%]
tests/test_janitor.py::TestJanitorCleanupLifecycle::test_check_disk_space_threshold PASSED [ 40%]
tests/test_janitor.py::TestJanitorCleanupLifecycle::test_janitor_daemon_start_and_stop PASSED [ 42%]
tests/test_job_manager.py::TestJobManagerLifecycle::test_single_track_job_success PASSED [ 43%]
tests/test_job_manager.py::TestJobManagerLifecycle::test_playlist_job_with_zip_packaging PASSED [ 45%]
tests/test_job_manager.py::TestCancellationAndRetries::test_cooperative_cancellation PASSED [ 46%]
tests/test_job_manager.py::TestCancellationAndRetries::test_retry_on_transient_error PASSED [ 48%]
tests/test_job_manager.py::TestCancellationAndRetries::test_exhausted_retries_marks_failed PASSED [ 50%]
tests/test_job_manager.py::TestSecurityAndConcurrencyEnforcement::test_ssrf_url_rejected_at_submission PASSED [ 51%]
tests/test_job_manager.py::TestSecurityAndConcurrencyEnforcement::test_insufficient_disk_space_rejected PASSED [ 53%]
tests/test_preservation.py::TestPrototypePreservation::test_legacy_files_exist PASSED [ 54%]
tests/test_preservation.py::TestPrototypePreservation::test_legacy_file_hashes_unmodified PASSED [ 56%]
tests/test_preservation.py::TestPrototypePreservation::test_legacy_downloads_dir_intact PASSED [ 57%]
tests/test_preservation.py::TestPrototypePreservation::test_legacy_app_is_runnable PASSED [ 59%]
tests/test_sanitizer.py::TestFilenameSanitization::test_strip_windows_forbidden_characters PASSED [ 60%]
tests/test_sanitizer.py::TestFilenameSanitization::test_strip_trailing_periods_and_spaces PASSED [ 62%]
tests/test_sanitizer.py::TestFilenameSanitization::test_empty_or_non_string_fallback PASSED [ 64%]
tests/test_sanitizer.py::TestFilenameSanitization::test_max_length_truncation PASSED [ 65%]
tests/test_sanitizer.py::TestFilenameSanitization::test_format_track_filename_single PASSED [ 67%]
tests/test_sanitizer.py::TestFilenameSanitization::test_format_track_filename_playlist PASSED [ 68%]
tests/test_sanitizer.py::TestPathTraversalDefense::test_safe_path_join_normal PASSED [ 70%]
tests/test_sanitizer.py::TestPathTraversalDefense::test_safe_path_join_strips_directory_components PASSED [ 71%]
tests/test_security.py::TestProtocolAndFormatValidation::test_empty_or_non_string_urls PASSED [ 73%]
tests/test_security.py::TestProtocolAndFormatValidation::test_unsupported_protocols PASSED [ 75%]
tests/test_security.py::TestMissingHostname::test_missing_hostname PASSED [ 76%]
tests/test_security.py::TestIPLiteralAndObfuscationRejection::test_ipv4_loopback_literals PASSED [ 78%]
tests/test_security.py::TestIPLiteralAndObfuscationRejection::test_ipv4_private_rfc1918_literals PASSED [ 79%]
tests/test_security.py::TestIPLiteralAndObfuscationRejection::test_ipv4_link_local_cloud_metadata PASSED [ 81%]
tests/test_security.py::TestIPLiteralAndObfuscationRejection::test_carrier_grade_nat_literals PASSED [ 82%]
tests/test_security.py::TestIPLiteralAndObfuscationRejection::test_ipv6_loopback_and_private PASSED [ 84%]
tests/test_security.py::TestIPLiteralAndObfuscationRejection::test_dword_ip_obfuscation PASSED [ 85%]
tests/test_security.py::TestIPLiteralAndObfuscationRejection::test_hex_ip_obfuscation PASSED [ 87%]
tests/test_security.py::TestIPLiteralAndObfuscationRejection::test_octal_ip_obfuscation PASSED [ 89%]
tests/test_security.py::TestInternalHostnames::test_localhost_variants PASSED [ 90%]
tests/test_security.py::TestDNSPreFlightAndRebinding::test_domain_resolving_to_private_ip PASSED [ 92%]
tests/test_security.py::TestDNSPreFlightAndRebinding::test_domain_resolving_to_mixed_ips_one_private PASSED [ 93%]
tests/test_security.py::TestDNSPreFlightAndRebinding::test_valid_public_domain PASSED [ 95%]
tests/test_security.py::TestRedirectValidation::test_benign_redirect PASSED [ 96%]
tests/test_security.py::TestRedirectValidation::test_redirect_to_internal_ip_aborts PASSED [ 98%]
tests/test_security.py::TestRedirectValidation::test_redirect_to_localhost_aborts PASSED [100%]

============================= 64 passed in 21.47s =============================
```

### B. Ruff Code Quality & Linting
- Linter output: `All checks passed!`
- Formatter check: `29 files already formatted.`
- Strict adherence to PEP 8, line length limitations (<= 100), and type annotations.

### C. Strict Prototype Preservation Verification
Cryptographic SHA256 hashes confirm zero modifications to legacy prototype files:

| File Path | Phase 1 SHA256 Hash | Post-Phase 2 SHA256 Hash | Status |
| :--- | :--- | :--- | :--- |
| `app.py` | `1F901CF48C6A250FF2294BA5A663046742410F45640DFA2DF888F9BA9F062D65` | `1F901CF48C6A250FF2294BA5A663046742410F45640DFA2DF888F9BA9F062D65` | ✅ **100% Identical** |
| `music_fixer.py` | `39D4B7FA9C4B8A07F4248659230F76A9EAFEF6ED72B4152DA2DF577E7A37F940` | `39D4B7FA9C4B8A07F4248659230F76A9EAFEF6ED72B4152DA2DF577E7A37F940` | ✅ **100% Identical** |
| `templates/index.html` | `4A3A6727CBE033AEBA3ED211560FEE30389E4E6A1F88EFE2E7A08A5788FF7EE9` | `4A3A6727CBE033AEBA3ED211560FEE30389E4E6A1F88EFE2E7A08A5788FF7EE9` | ✅ **100% Identical** |
| `ffmpeg.exe` | `BA242553F0FF60AD788069D5D376C1B4F7A2F3A3566416E0ED950CA7920DA5FA` | `BA242553F0FF60AD788069D5D376C1B4F7A2F3A3566416E0ED950CA7920DA5FA` | ✅ **100% Identical** |
| `downloads/` | Directory | Directory | ✅ **Intact** |

---

## 5. Next Phase Readiness

The engine and lifecycle layer are fully tested and ready to support:
- **Phase 3**: Modern FastAPI HTTP REST & SSE real-time API routes (`/api/v1/download`, `/api/v1/jobs/{id}/progress`, `/api/v1/jobs/{id}/cancel`, `/api/v1/download/file/{id}`), metadata extraction endpoints, and interactive UI integration.

**Current Working Tree State:**
- Uncommitted Phase 2 files and updates staged for review.
- No Git commit performed in adherence to instructions.
- Ready for inspection and subsequent phase authorization.
