# SONORA — SPRINT 5 FEATURE 2 EXECUTION REPORT
## Pre-Download Metadata & Artwork Editor

**Date:** 2026-09-28  
**Feature:** Phase 5 Feature 2 — Pre-Download Metadata & Artwork Editor  
**Status:** COMPLETE & FULLY VERIFIED  
**Baseline Commit:** `d4e3cd9` (`feat: add download profiles`)  

---

### 1. Executive Summary

Phase 5 Feature 2 enhances SONORA's media ingestion lifecycle by adding an interactive, pre-download **Metadata Review & Artwork Editor**. Instead of immediately triggering background downloads upon URL inspection, the user is presented with editable metadata fields (Title, Artist, Album, Year) and a custom album artwork dropzone/uploader. The download is initiated only after user review and confirmation.

All user overrides are validated against strict security policies, encapsulated into the job execution context, and injected into the target audio files during the tagging stage with strict precedence over scraped yt-dlp metadata.

---

### 2. Architecture & Design

```
+-------------------------------------------------------------------------------+
|                                 USER BROWSER                                  |
|   1. URL Input -> 2. Inspect -> 3. Metadata Review / Edit -> 4. Confirm & DL  |
+-------------------------------------------------------------------------------+
                                      |
                       POST /api/v1/jobs (JSON Payload)
                                      |
                                      v
+-------------------------------------------------------------------------------+
|                              FASTAPI ENDPOINT                                 |
|               JobSubmitRequest (with MetadataOverride payload)                |
|           - Validates metadata lengths, control chars, year 1000..2100        |
|           - Decodes base64/data-URL artwork & checks magic bytes (JPEG/PNG)   |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
|                                 JOB MANAGER                                   |
|   - Saves decoded artwork into job-isolated scratchpad (temp/{job_id}/)       |
|   - Initializes SQLite job record with user-overridden title                  |
|   - Dispatches worker thread with JobMetadataConfig context                   |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
|                            EXECUTION WORKER PIPELINE                          |
|   1. Execute yt-dlp download in scratchpad                                    |
|   2. Precedence Resolution:                                                   |
|      User Override > Scraped yt-dlp Metadata > Default Fallback               |
|   3. Audio Tagging Engine (Mutagen MP3 / M4A / FLAC / Opus / WAV):            |
|      - Injects final Title, Artist, Album, Track Number, Year, and Artwork    |
|   4. Move tagged file to completed/ & clean up isolated scratchpad            |
+-------------------------------------------------------------------------------+
```

---

### 3. Key Components Implemented

#### A. Metadata Override Model (`app/models/metadata.py`)
- **Strong Pydantic Schema:** Implemented `MetadataOverride` with optional `title`, `artist`, `album`, `year`, and `artwork`.
- **Sanitization & Security:**
  - Strips non-printable ASCII control characters (`\x00-\x1f`, `\x7f`) while preserving international Unicode song titles (e.g. Japanese, Cyrillic, accented characters, emojis).
  - Validates `year` strictly in the range `1000..2100`.
  - Enforces `max_length=500` on string fields.
  - Validates base64 data URLs, limits binary payload size to 10MB, and verifies image magic bytes (`JPEG`, `PNG`, `WEBP`).
  - Confines uploaded artwork files strictly to `temp/{job_id}/` scratchpads.

#### B. Audio Tagging Engine Expansion (`app/engine/audio_tagger.py`)
- **Release Year Embedding:** Added `year` parameter support across:
  - **MP3:** ID3v2.3 `TYER` and `TDRC` frames.
  - **M4A / AAC / MP4:** QuickTime `©day` tag.
  - **FLAC:** Vorbis `date` comment.
  - **Ogg Opus:** Vorbis `date` comment.
  - **WAV:** RIFF/ID3 `TYER` frame.

#### C. Job Pipeline Integration (`app/services/job_manager.py`)
- **Metadata Precedence:**
  - Single tracks: `User Title > Scraped Title > Fallback`.
  - Artists/Albums: `User Override > Scraped Uploader / Album > Fallback`.
  - Artworks: `User Custom Artwork > Scraped yt-dlp Thumbnail > Default Fallback`.
  - Playlists: Supports per-track overrides (`track_overrides`) indexed by track number, ensuring user edits are bound to the exact selected track.
- **Scratchpad Lifecycle:** Decoded custom artwork is saved in the job's temporary directory and purged automatically upon job completion, failure, or cancellation.

#### D. API Request Contract (`app/api/v1/endpoints.py`)
- Extended `JobSubmitRequest` with optional `metadata_overrides` and `track_overrides`.
- Backward compatibility: Legacy job submissions without overrides continue functioning identically.

#### E. Frontend Review & Editor UI (`index.html`, `styles.css`, `app.js`)
- **Interactive Review Card:** Replaced direct auto-download with a review layout.
- **Form Inputs:** Input controls for Title, Artist, Album, and Year with visual focus states and keyboard navigation.
- **Artwork Dropzone:** Drag-and-drop cover uploader, click-to-browse file input, live preview, and "Restore Original Artwork" toggle.
- **Playlist Switching:** Clicking any track in the playlist checklist highlights the track and loads its title/artist into the editor.
- **XSS Protection:** All dynamic strings are rendered via `textContent` or text-based DOM attributes.

---

### 4. Verification & Testing

- **New Test Suite:** `tests/test_metadata_editor.py` covering:
  1. Valid metadata override acceptance.
  2. Partial overrides preserving unspecified fields.
  3. Year range boundary validation (`1000..2100`) and rejection of invalid values.
  4. Oversized metadata and base64 payloads rejection.
  5. Control character stripping with Unicode retention.
  6. Image magic-byte validation (JPEG, PNG, WEBP).
  7. Artwork isolated temporary storage and cleanup.
  8. MP3 ID3v2.3 title, artist, album, year, and artwork embedding.
  9. FLAC Vorbis comments, year, and Picture embedding.
  10. API job submission with metadata overrides and database record persistence.
  11. Backward compatibility for legacy requests without overrides.
  12. Static HTML markup and accessible form controls.
- **Protected Legacy Files:** Byte-for-byte unchanged:
  - `app.py`
  - `music_fixer.py`
  - `templates/index.html`
  - `ffmpeg.exe`

---

### 5. Summary of Modified & Created Files

| File | Status | Description |
| :--- | :--- | :--- |
| `app/models/metadata.py` | **CREATED** | MetadataOverride Pydantic model, artwork validation, isolated storage helper |
| `app/models/__init__.py` | **CREATED** | Models package init |
| `app/engine/audio_tagger.py` | **MODIFIED** | Added year tagging support for MP3, M4A, FLAC, Opus, WAV |
| `app/services/job_manager.py` | **MODIFIED** | Integrated metadata overrides, custom artwork storage, and tagging precedence |
| `app/api/v1/endpoints.py` | **MODIFIED** | Extended JobSubmitRequest with metadata_overrides and track_overrides |
| `app/static/index.html` | **MODIFIED** | Added pre-download metadata editor and artwork dropzone UI |
| `app/static/css/styles.css` | **MODIFIED** | Added styles for metadata editor layout, artwork dropzone, and responsive forms |
| `app/static/js/app.js` | **MODIFIED** | Implemented review state, artwork upload/drag-drop, playlist switching, and override payload assembly |
| `tests/test_metadata_editor.py` | **CREATED** | Comprehensive unit, integration, and security test suite |
| `STATE.md` | **MODIFIED** | Updated state matrix and baseline commit |
| `CHANGELOG.md` | **MODIFIED** | Documented Phase 5 Feature 2 additions |
| `SPRINT_5_FEATURE_2_REPORT.md` | **CREATED** | Comprehensive technical execution report |
