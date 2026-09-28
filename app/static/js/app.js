/**
 * SONORA — Modern Music Downloader Application Controller
 *
 * Implements state machine UI transitions, API communication,
 * Server-Sent Events (SSE) real-time streaming, playlist selection,
 * theme management, and startup animation lifecycle.
 */

(function () {
  'use strict';

  // State Enums
  const States = {
    IDLE: 'state-idle',
    INSPECTING: 'state-inspecting',
    READY: 'state-ready',
    DOWNLOADING: 'state-downloading',
    COMPLETED: 'state-completed',
    FAILED: 'state-failed',
    CANCELLED: 'state-cancelled',
  };

  // Application State Context
  const context = {
    currentState: States.IDLE,
    selectedProfile: 'standard',
    targetFormat: 'mp3_320',
    quality: '320',
    metadata: null,
    customArtwork: null,
    activePlaylistTrackIndex: 1,
    playlistTrackOverrides: {},
    selectedTrackIndices: [],
    currentJobId: null,
    eventSource: null,
    ssePollInterval: null,
    inspectAbortController: null,
    isInspecting: false,
    isSubmittingJob: false,
  };

  // DOM Elements Registry
  const elements = {};

  function initElements() {
    elements.overlay = document.getElementById('startup-overlay');
    elements.themeToggle = document.getElementById('theme-toggle');
    elements.mobileMenuBtn = document.getElementById('mobile-menu-btn');
    elements.siteNav = document.getElementById('site-nav');
    elements.navLinks = document.querySelectorAll('.site-nav .nav-link');

    elements.urlInput = document.getElementById('url-input');
    elements.clearBtn = document.getElementById('clear-btn');
    elements.submitBtn = document.getElementById('submit-btn');
    elements.cancelInspectingBtn = document.getElementById('cancel-inspecting-btn');
    elements.downloadForm = document.getElementById('download-form');
    elements.profileChips = document.querySelectorAll('.profile-chip');
    elements.profileNote = document.getElementById('profile-note');
    elements.formatChips = document.querySelectorAll('.format-chip');
    elements.qualityNote = document.getElementById('quality-note');

    elements.readyArtwork = document.getElementById('ready-artwork');
    elements.readyBadge = document.getElementById('ready-type-badge');
    elements.readyDuration = document.getElementById('ready-duration');
    elements.metaTitle = document.getElementById('meta-title');
    elements.metaArtist = document.getElementById('meta-artist');
    elements.metaAlbum = document.getElementById('meta-album');
    elements.metaYear = document.getElementById('meta-year');
    elements.revertMetaBtn = document.getElementById('revert-meta-btn');
    elements.artworkDropzone = document.getElementById('artwork-dropzone');
    elements.artworkDropOverlay = document.getElementById('artwork-drop-overlay');
    elements.artworkFileInput = document.getElementById('artwork-file-input');
    elements.uploadArtworkBtn = document.getElementById('upload-artwork-btn');
    elements.resetArtworkBtn = document.getElementById('reset-artwork-btn');
    elements.startDownloadBtn = document.getElementById('start-download-btn');
    elements.cancelInspectBtn = document.getElementById('cancel-inspect-btn');

    elements.playlistContainer = document.getElementById('playlist-checklist-container');
    elements.selectedCount = document.getElementById('selected-count');
    elements.totalCount = document.getElementById('total-count');
    elements.selectAllBtn = document.getElementById('select-all-btn');
    elements.playlistList = document.getElementById('playlist-items-list');

    elements.dlArtwork = document.getElementById('dl-artwork');
    elements.dlTitle = document.getElementById('dl-title');
    elements.dlStatusText = document.getElementById('dl-status-text');
    elements.progressBarFill = document.getElementById('progress-bar-fill');
    elements.progressPercent = document.getElementById('progress-percent');
    elements.dlSpeed = document.getElementById('dl-speed');
    elements.dlEta = document.getElementById('dl-eta');
    elements.cancelDownloadBtn = document.getElementById('cancel-download-btn');

    elements.completedTitle = document.getElementById('completed-title');
    elements.completedMeta = document.getElementById('completed-meta');
    elements.fileDownloadLink = document.getElementById('file-download-link');
    elements.resetBtn = document.getElementById('reset-btn');

    elements.errorMessage = document.getElementById('error-message');
    elements.errorRetryBtn = document.getElementById('error-retry-btn');
    elements.cancelledResetBtn = document.getElementById('cancelled-reset-btn');

    // Library & History elements
    elements.librarySearch = document.getElementById('library-search');
    elements.libraryClearSearch = document.getElementById('library-clear-search');
    elements.libraryStatusFilter = document.getElementById('library-status-filter');
    elements.libraryProfileFilter = document.getElementById('library-profile-filter');
    elements.libraryRefreshBtn = document.getElementById('library-refresh-btn');
    elements.libraryTable = document.getElementById('library-table');
    elements.libraryTbody = document.getElementById('library-tbody');
    elements.libraryLoading = document.getElementById('library-loading');
    elements.libraryEmpty = document.getElementById('library-empty');
    elements.paginationInfo = document.getElementById('pagination-info');
    elements.paginationPrev = document.getElementById('pagination-prev');
    elements.paginationNext = document.getElementById('pagination-next');
    elements.paginationCurrent = document.getElementById('pagination-current');
    elements.jobDetailsModal = document.getElementById('job-details-modal');
    elements.modalJobTitle = document.getElementById('modal-job-title');
    elements.modalJobBody = document.getElementById('modal-job-body');
    elements.modalCloseBtn = document.getElementById('modal-close-btn');
    elements.modalDismissBtn = document.getElementById('modal-dismiss-btn');
  }

  // State Machine Switcher
  function setState(targetState) {
    context.currentState = targetState;
    Object.values(States).forEach((stateId) => {
      const el = document.getElementById(stateId);
      if (el) {
        if (stateId === targetState) {
          el.classList.add('active');
        } else {
          el.classList.remove('active');
        }
      }
    });
  }

  // Theme Controller
  function initTheme() {
    const savedTheme = localStorage.getItem('sonora-theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);

    elements.themeToggle.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('sonora-theme', next);
    });
  }

  // Startup Animation Controller
  function initStartupAnimation() {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const duration = prefersReducedMotion ? 100 : 1000;

    setTimeout(() => {
      if (elements.overlay) {
        elements.overlay.classList.add('fade-out');
        setTimeout(() => {
          elements.overlay.style.display = 'none';
        }, 400);
      }
    }, duration);
  }

  // Download Profile Selection Panel Handler
  const profileNotes = {
    audiophile: 'Lossless FLAC extraction preserving original source acoustic quality.',
    standard: 'Universal compatibility MP3 transcode at 320 kbps CBR.',
    space_saver: 'Lightweight and efficient M4A/AAC audio transcode at 128 kbps.',
    raw_video: 'Preserves full video and audio stream in an MP4 container.',
  };

  function selectProfileChip(chip) {
    if (!elements.profileChips) return;
    elements.profileChips.forEach((c) => {
      c.classList.remove('active');
      c.setAttribute('aria-checked', 'false');
      c.setAttribute('tabindex', '-1');
    });
    chip.classList.add('active');
    chip.setAttribute('aria-checked', 'true');
    chip.setAttribute('tabindex', '0');

    const profile = chip.getAttribute('data-profile') || 'standard';
    context.selectedProfile = profile;

    if (elements.profileNote && profileNotes[profile]) {
      elements.profileNote.textContent = profileNotes[profile];
    }
  }

  function initProfileSelection() {
    if (!elements.profileChips || elements.profileChips.length === 0) return;
    const chips = Array.from(elements.profileChips);
    chips.forEach((chip, index) => {
      chip.addEventListener('click', () => {
        selectProfileChip(chip);
      });

      chip.addEventListener('keydown', (e) => {
        let nextIndex = null;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
          e.preventDefault();
          nextIndex = (index + 1) % chips.length;
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
          e.preventDefault();
          nextIndex = (index - 1 + chips.length) % chips.length;
        } else if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          selectProfileChip(chip);
          return;
        }
        if (nextIndex !== null) {
          chips[nextIndex].focus();
          selectProfileChip(chips[nextIndex]);
        }
      });
    });
  }

  // Format & Quality Selection Panel Handler (MED-07 Keyboard & Radio Semantics)
  function selectFormatChip(chip) {
    elements.formatChips.forEach((c) => {
      c.classList.remove('active');
      c.setAttribute('aria-checked', 'false');
      c.setAttribute('tabindex', '-1');
    });
    chip.classList.add('active');
    chip.setAttribute('aria-checked', 'true');
    chip.setAttribute('tabindex', '0');

    context.targetFormat = chip.getAttribute('data-format');
    context.quality = chip.getAttribute('data-quality');

    if (
      context.targetFormat.startsWith('native_') ||
      context.targetFormat === 'm4a' ||
      context.targetFormat === 'opus'
    ) {
      elements.qualityNote.textContent =
        'Direct Stream Copy preserves raw source audio without re-encoding loss.';
    } else if (context.targetFormat === 'flac') {
      elements.qualityNote.textContent =
        'Encapsulates source audio into a FLAC lossless container without upscaling.';
    } else {
      elements.qualityNote.textContent =
        'Transcodes audio to universal MP3 format for broad playback support.';
    }
  }

  function initFormatSelection() {
    const chips = Array.from(elements.formatChips);
    chips.forEach((chip, index) => {
      chip.addEventListener('click', () => {
        selectFormatChip(chip);
      });

      chip.addEventListener('keydown', (e) => {
        let nextIndex = null;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
          e.preventDefault();
          nextIndex = (index + 1) % chips.length;
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
          e.preventDefault();
          nextIndex = (index - 1 + chips.length) % chips.length;
        } else if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          selectFormatChip(chip);
          return;
        }
        if (nextIndex !== null) {
          chips[nextIndex].focus();
          selectFormatChip(chips[nextIndex]);
        }
      });
    });
  }

  // URL Input Handlers
  function initInputHandlers() {
    elements.clearBtn.addEventListener('click', () => {
      elements.urlInput.value = '';
      elements.urlInput.focus();
    });

    elements.downloadForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const url = elements.urlInput.value.trim();
      if (!url) return;
      await handleMetadataInspection(url);
    });
  }

  // Metadata Inspection Action with Bounded Timeout & AbortController (CRIT-07, HIGH-06)
  async function handleMetadataInspection(url) {
    if (context.isInspecting) return;
    context.isInspecting = true;

    // Guard UI against double submission
    if (elements.submitBtn) {
      elements.submitBtn.disabled = true;
      elements.submitBtn.textContent = 'Inspecting...';
    }
    if (elements.urlInput) {
      elements.urlInput.disabled = true;
    }

    const controller = new AbortController();
    context.inspectAbortController = controller;

    // 15-second bounded inspection timeout
    const timeoutId = setTimeout(() => {
      controller.abort('timeout');
    }, 15000);

    setState(States.INSPECTING);

    try {
      const response = await fetch('/api/v1/metadata', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, is_playlist: false }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      const json = await response.json();
      if (!response.ok) {
        const errorMsg = json.detail?.message || 'Failed to inspect link metadata.';
        showError(errorMsg);
        return;
      }

      context.metadata = json.data;
      renderReadyState();
      setState(States.READY);
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError' || controller.signal.aborted) {
        if (controller.signal.reason === 'user_cancelled') {
          resetToIdle();
          return;
        }
        showError('Metadata inspection timed out after 15 seconds. Please verify the URL and try again.');
      } else {
        showError('Network error connecting to SONORA backend service.');
      }
    } finally {
      clearTimeout(timeoutId);
      context.isInspecting = false;
      context.inspectAbortController = null;
      if (elements.submitBtn) {
        elements.submitBtn.disabled = false;
        elements.submitBtn.textContent = 'Inspect';
      }
      if (elements.urlInput) {
        elements.urlInput.disabled = false;
      }
    }
  }

  const FALLBACK_ARTWORK_SVG =
    'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" ' +
    'viewBox="0 0 24 24" fill="%231E1E1E" stroke="%236366F1" stroke-width="1.5">' +
    '<rect width="20" height="20" x="2" y="2" rx="3" fill="%23262626"/>' +
    '<circle cx="12" cy="12" r="4" stroke="%23818CF8"/>' +
    '<circle cx="12" cy="12" r="1.5" fill="%23818CF8"/></svg>';

  // Render Metadata Ready View & Populate Editor
  function renderReadyState() {
    const data = context.metadata;
    if (!data) return;

    context.customArtwork = null;
    context.activePlaylistTrackIndex = 1;
    context.playlistTrackOverrides = {};

    if (elements.resetArtworkBtn) {
      elements.resetArtworkBtn.style.display = 'none';
    }

    // Populate editor fields
    if (elements.metaTitle) {
      elements.metaTitle.value = data.title || '';
    }
    if (elements.metaArtist) {
      elements.metaArtist.value = data.uploader || '';
    }
    if (elements.metaAlbum) {
      elements.metaAlbum.value = data.is_playlist ? data.title || '' : '';
    }
    if (elements.metaYear) {
      elements.metaYear.value = '';
    }

    if (elements.readyDuration) {
      elements.readyDuration.textContent = formatDuration(data.duration_seconds || 0);
    }

    if (data.thumbnail_url) {
      elements.readyArtwork.src = data.thumbnail_url;
      elements.dlArtwork.src = data.thumbnail_url;
    } else {
      elements.readyArtwork.src = FALLBACK_ARTWORK_SVG;
      elements.dlArtwork.src = FALLBACK_ARTWORK_SVG;
    }

    elements.readyArtwork.onerror = function () {
      this.src = FALLBACK_ARTWORK_SVG;
    };
    elements.dlArtwork.onerror = function () {
      this.src = FALLBACK_ARTWORK_SVG;
    };

    if (data.is_playlist && data.tracks && data.tracks.length > 0) {
      elements.readyBadge.textContent = `Playlist (${data.tracks.length} tracks)`;
      elements.playlistContainer.style.display = 'block';
      renderPlaylistItems(data.tracks);
    } else {
      elements.readyBadge.textContent = 'Single Track';
      elements.playlistContainer.style.display = 'none';
      context.selectedTrackIndices = [1];
      if (elements.startDownloadBtn) {
        elements.startDownloadBtn.disabled = false;
        elements.startDownloadBtn.title = '';
      }
    }
  }

  // Playlist Checklist Renderer & Track Focus Switcher
  function renderPlaylistItems(tracks) {
    elements.playlistList.innerHTML = '';
    context.selectedTrackIndices = tracks.map((t) => t.index);

    elements.totalCount.textContent = tracks.length;
    elements.selectedCount.textContent = tracks.length;

    if (elements.startDownloadBtn) {
      elements.startDownloadBtn.disabled = tracks.length === 0;
      elements.startDownloadBtn.title =
        tracks.length === 0 ? 'Select at least one track to download' : '';
    }

    tracks.forEach((track) => {
      const item = document.createElement('label');
      item.className = 'playlist-item-row';
      item.setAttribute('data-track-index', String(track.index));
      if (track.index === context.activePlaylistTrackIndex) {
        item.classList.add('selected-active');
      }

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'track-checkbox';
      checkbox.setAttribute('data-index', String(track.index));
      checkbox.checked = true;

      const trackNum = document.createElement('span');
      trackNum.className = 'track-num';
      trackNum.textContent = `${String(track.index).padStart(2, '0')}.`;

      const trackName = document.createElement('span');
      trackName.className = 'track-name';
      trackName.style.cssText =
        'flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
      trackName.textContent = track.title || 'Untitled Track';

      const trackDur = document.createElement('span');
      trackDur.className = 'track-dur';
      trackDur.style.cssText = 'color:var(--text-muted); font-size:0.8rem;';
      trackDur.textContent = formatDuration(track.duration_seconds);

      item.appendChild(checkbox);
      item.appendChild(trackNum);
      item.appendChild(trackName);
      item.appendChild(trackDur);

      checkbox.addEventListener('change', () => {
        updateSelectedTrackIndices();
      });

      // Clicking row switches editor focus to this track
      item.addEventListener('click', (e) => {
        if (e.target === checkbox) return;
        switchActivePlaylistTrack(track.index);
      });

      elements.playlistList.appendChild(item);
    });

    elements.selectAllBtn.onclick = () => {
      const checkboxes = elements.playlistList.querySelectorAll('.track-checkbox');
      const allChecked = Array.from(checkboxes).every((cb) => cb.checked);
      checkboxes.forEach((cb) => (cb.checked = !allChecked));
      updateSelectedTrackIndices();
    };
  }

  function switchActivePlaylistTrack(trackIndex) {
    if (!context.metadata || !context.metadata.tracks) return;
    context.activePlaylistTrackIndex = trackIndex;

    // Highlight row
    const rows = elements.playlistList.querySelectorAll('.playlist-item-row');
    rows.forEach((r) => {
      if (r.getAttribute('data-track-index') === String(trackIndex)) {
        r.classList.add('selected-active');
      } else {
        r.classList.remove('selected-active');
      }
    });

    const track = context.metadata.tracks.find((t) => t.index === trackIndex);
    if (!track) return;

    const override = context.playlistTrackOverrides[trackIndex] || {};
    if (elements.metaTitle) {
      elements.metaTitle.value = override.title !== undefined ? override.title : track.title;
    }
    if (elements.metaArtist) {
      elements.metaArtist.value =
        override.artist !== undefined ? override.artist : context.metadata.uploader || '';
    }
  }

  function updateSelectedTrackIndices() {
    const checkboxes = elements.playlistList.querySelectorAll('.track-checkbox');
    const selected = [];
    checkboxes.forEach((cb) => {
      if (cb.checked) {
        selected.push(parseInt(cb.getAttribute('data-index'), 10));
      }
    });
    context.selectedTrackIndices = selected;
    elements.selectedCount.textContent = selected.length;

    // Disable download button when no tracks are selected
    if (elements.startDownloadBtn) {
      if (selected.length === 0) {
        elements.startDownloadBtn.disabled = true;
        elements.startDownloadBtn.title = 'Select at least one track to download';
      } else {
        elements.startDownloadBtn.disabled = false;
        elements.startDownloadBtn.title = '';
      }
    }
  }

  // Artwork Dropzone & File Upload Controller
  function initArtworkHandlers() {
    if (!elements.artworkFileInput || !elements.uploadArtworkBtn) return;

    elements.uploadArtworkBtn.addEventListener('click', () => {
      elements.artworkFileInput.click();
    });

    if (elements.artworkDropzone) {
      elements.artworkDropzone.addEventListener('click', (e) => {
        if (e.target !== elements.resetArtworkBtn) {
          elements.artworkFileInput.click();
        }
      });

      ['dragenter', 'dragover'].forEach((eventName) => {
        elements.artworkDropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          elements.artworkDropzone.classList.add('drag-over');
        });
      });

      ['dragleave', 'drop'].forEach((eventName) => {
        elements.artworkDropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          elements.artworkDropzone.classList.remove('drag-over');
        });
      });

      elements.artworkDropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        if (dt && dt.files && dt.files.length > 0) {
          handleArtworkFile(dt.files[0]);
        }
      });
    }

    elements.artworkFileInput.addEventListener('change', () => {
      if (elements.artworkFileInput.files && elements.artworkFileInput.files.length > 0) {
        handleArtworkFile(elements.artworkFileInput.files[0]);
      }
    });

    if (elements.resetArtworkBtn) {
      elements.resetArtworkBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        restoreOriginalArtwork();
      });
    }
  }

  function handleArtworkFile(file) {
    const validMimes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!validMimes.includes(file.type)) {
      alert('Unsupported image format. Please select a JPEG, PNG, or WEBP image.');
      return;
    }

    // 10 MB limit
    if (file.size > 10 * 1024 * 1024) {
      alert('Artwork image exceeds 10 MB maximum size limit.');
      return;
    }

    const reader = new FileReader();
    reader.onload = function (e) {
      const dataUrl = e.target.result;
      context.customArtwork = dataUrl;
      elements.readyArtwork.src = dataUrl;
      elements.dlArtwork.src = dataUrl;
      if (elements.resetArtworkBtn) {
        elements.resetArtworkBtn.style.display = 'inline-block';
      }
    };
    reader.readAsDataURL(file);
  }

  function restoreOriginalArtwork() {
    context.customArtwork = null;
    if (elements.artworkFileInput) {
      elements.artworkFileInput.value = '';
    }
    if (elements.resetArtworkBtn) {
      elements.resetArtworkBtn.style.display = 'none';
    }
    const orig = context.metadata?.thumbnail_url || FALLBACK_ARTWORK_SVG;
    elements.readyArtwork.src = orig;
    elements.dlArtwork.src = orig;
  }

  // Metadata Input Change & Revert Controller
  function initMetadataEditorHandlers() {
    if (elements.revertMetaBtn) {
      elements.revertMetaBtn.addEventListener('click', () => {
        if (!context.metadata) return;
        if (elements.metaTitle) {
          elements.metaTitle.value = context.metadata.title || '';
        }
        if (elements.metaArtist) {
          elements.metaArtist.value = context.metadata.uploader || '';
        }
        if (elements.metaAlbum) {
          elements.metaAlbum.value = context.metadata.is_playlist ? context.metadata.title || '' : '';
        }
        if (elements.metaYear) {
          elements.metaYear.value = '';
        }
        restoreOriginalArtwork();
        context.playlistTrackOverrides = {};
      });
    }

    // Dynamic field synchronization for playlist tracks
    const syncPlaylistFields = () => {
      if (!context.metadata || !context.metadata.is_playlist) return;
      const tIdx = context.activePlaylistTrackIndex;
      if (!context.playlistTrackOverrides[tIdx]) {
        context.playlistTrackOverrides[tIdx] = {};
      }
      if (elements.metaTitle) {
        context.playlistTrackOverrides[tIdx].title = elements.metaTitle.value.trim();
        // Update track title in checklist row DOM
        const row = elements.playlistList.querySelector(`[data-track-index="${tIdx}"] .track-name`);
        if (row) {
          row.textContent = elements.metaTitle.value.trim() || 'Untitled Track';
        }
      }
      if (elements.metaArtist) {
        context.playlistTrackOverrides[tIdx].artist = elements.metaArtist.value.trim();
      }
    };

    if (elements.metaTitle) {
      elements.metaTitle.addEventListener('input', syncPlaylistFields);
    }
    if (elements.metaArtist) {
      elements.metaArtist.addEventListener('input', syncPlaylistFields);
    }
  }

  // Start Download Action with Metadata & Artwork Overrides
  async function startDownload() {
    if (!context.metadata || context.isSubmittingJob) return;

    if (
      context.metadata.is_playlist &&
      (!context.selectedTrackIndices || context.selectedTrackIndices.length === 0)
    ) {
      showError('Please select at least one track from the playlist to download.');
      return;
    }

    context.isSubmittingJob = true;

    if (elements.startDownloadBtn) {
      elements.startDownloadBtn.disabled = true;
      elements.startDownloadBtn.textContent = 'Enqueuing...';
    }

    setState(States.DOWNLOADING);

    const overrides = {};
    const titleVal = elements.metaTitle ? elements.metaTitle.value.trim() : '';
    const artistVal = elements.metaArtist ? elements.metaArtist.value.trim() : '';
    const albumVal = elements.metaAlbum ? elements.metaAlbum.value.trim() : '';
    const yearVal = elements.metaYear ? elements.metaYear.value.trim() : '';

    if (titleVal) overrides.title = titleVal;
    if (artistVal) overrides.artist = artistVal;
    if (albumVal) overrides.album = albumVal;
    if (yearVal) {
      const parsedYear = parseInt(yearVal, 10);
      if (!isNaN(parsedYear) && parsedYear >= 1000 && parsedYear <= 2100) {
        overrides.year = parsedYear;
      }
    }
    if (context.customArtwork) {
      overrides.artwork = context.customArtwork;
    }

    const displayTitle = overrides.title || context.metadata.title;
    elements.dlTitle.textContent = displayTitle;
    elements.dlStatusText.textContent = 'Enqueuing job...';
    elements.progressBarFill.style.width = '0%';
    elements.progressPercent.textContent = '0%';

    try {
      const payload = {
        url: context.metadata.url,
        format: context.targetFormat,
        quality: context.quality,
        profile: context.selectedProfile || 'standard',
        is_playlist: context.metadata.is_playlist,
        selected_indices: context.selectedTrackIndices,
        title: displayTitle,
        metadata_overrides: Object.keys(overrides).length > 0 ? overrides : null,
        track_overrides:
          Object.keys(context.playlistTrackOverrides).length > 0
            ? context.playlistTrackOverrides
            : null,
      };

      const response = await fetch('/api/v1/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const json = await response.json();
      if (!response.ok) {
        const msg = json.detail?.message || 'Failed to submit download job.';
        showError(msg);
        return;
      }

      context.currentJobId = json.data.job_id;
      connectSSE(context.currentJobId);
    } catch (err) {
      showError('Failed to initiate job submission.');
    } finally {
      context.isSubmittingJob = false;
      if (elements.startDownloadBtn) {
        elements.startDownloadBtn.disabled = false;
        elements.startDownloadBtn.textContent = 'Confirm & Download';
      }
    }
  }

  // Real-Time SSE Listener
  function connectSSE(jobId) {
    if (context.eventSource) {
      context.eventSource.close();
    }

    const sseUrl = `/api/v1/jobs/${jobId}/events`;
    context.eventSource = new EventSource(sseUrl);

    context.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        updateProgressUI(data);

        if (data.status === 'completed') {
          closeSSE();
          renderCompletedState(data);
        } else if (data.status === 'failed') {
          closeSSE();
          showError(data.error_message || 'Download task failed.');
        } else if (data.status === 'cancelled') {
          closeSSE();
          setState(States.CANCELLED);
        }
      } catch (e) {
        console.error('Error parsing SSE event:', e);
      }
    };

    context.eventSource.onerror = () => {
      console.warn('SSE connection interrupted, falling back to polling...');
      closeSSE();
      startPollingFallback(jobId);
    };
  }

  // Maximum retry parameters for SSE polling fallback (CRIT-02)
  const MAX_POLL_FAILURES = 5;
  const MAX_POLL_404_RETRIES = 2;
  const MAX_POLL_ATTEMPTS = 180; // 6 minutes maximum polling duration
  const POLL_INTERVAL_MS = 2000;

  function startPollingFallback(jobId) {
    if (context.ssePollInterval) {
      clearInterval(context.ssePollInterval);
      context.ssePollInterval = null;
    }

    let consecutiveErrors = 0;
    let consecutive404s = 0;
    let pollAttempts = 0;

    context.ssePollInterval = setInterval(async () => {
      pollAttempts += 1;
      if (pollAttempts > MAX_POLL_ATTEMPTS) {
        closeSSE();
        showError('Download monitoring timed out. Please verify the download or retry.');
        return;
      }

      try {
        const res = await fetch(`/api/v1/jobs/${jobId}`);
        const json = await res.json();
        if (res.ok && json.data) {
          // Reset error counters on successful status response
          consecutiveErrors = 0;
          consecutive404s = 0;

          const data = json.data;
          updateProgressUI(data);

          if (data.status === 'completed') {
            closeSSE();
            renderCompletedState(data);
          } else if (data.status === 'failed') {
            closeSSE();
            showError(data.error_message || 'Download task failed.');
          } else if (data.status === 'cancelled') {
            closeSSE();
            setState(States.CANCELLED);
          }
        } else if (res.status === 404) {
          consecutive404s += 1;
          if (consecutive404s >= MAX_POLL_404_RETRIES) {
            closeSSE();
            showError('Download job was not found or has expired. Please try again.');
          }
        } else {
          consecutiveErrors += 1;
          if (consecutiveErrors >= MAX_POLL_FAILURES) {
            closeSSE();
            showError('Server error while checking download progress. Please try again later.');
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
        consecutiveErrors += 1;
        if (consecutiveErrors >= MAX_POLL_FAILURES) {
          closeSSE();
          showError('Lost network connection to server. Please check your connection.');
        }
      }
    }, POLL_INTERVAL_MS);
  }

  function closeSSE() {
    if (context.eventSource) {
      context.eventSource.close();
      context.eventSource = null;
    }
    if (context.ssePollInterval) {
      clearInterval(context.ssePollInterval);
      context.ssePollInterval = null;
    }
  }

  function updateProgressUI(data) {
    const progress = Math.min(100, Math.max(0, data.progress || 0));
    elements.progressBarFill.style.width = `${progress}%`;
    elements.progressPercent.textContent = `${Math.round(progress)}%`;

    if (data.current_title) {
      elements.dlTitle.textContent = data.current_title;
    }

    elements.dlStatusText.textContent = `Status: ${data.status || 'downloading'}`;

    if (data.speed) {
      const mbps = (data.speed / (1024 * 1024)).toFixed(1);
      elements.dlSpeed.textContent = `${mbps} MB/s`;
    }

    if (data.eta !== undefined) {
      elements.dlEta.textContent = `ETA: ${data.eta}s`;
    }
  }

  // Cancel Download Handler
  async function cancelDownload() {
    if (!context.currentJobId) return;

    try {
      await fetch(`/api/v1/jobs/${context.currentJobId}/cancel`, { method: 'POST' });
    } catch (err) {
      console.error('Cancellation error:', err);
    } finally {
      closeSSE();
      setState(States.CANCELLED);
    }
  }

  // Render Completed State
  function renderCompletedState(data) {
    setState(States.COMPLETED);
    elements.completedTitle.textContent = data.title || context.metadata?.title || 'Completed Audio File';
    elements.completedMeta.textContent = `Format: ${context.targetFormat.toUpperCase()} • Status: Ready`;

    const downloadUrl = `/api/v1/downloads/${context.currentJobId}/file`;
    elements.fileDownloadLink.href = downloadUrl;
  }

  // Error Helper
  function showError(msg) {
    setState(States.FAILED);
    elements.errorMessage.textContent = msg || 'An unexpected error occurred.';
  }

  // Reset to Idle
  function resetToIdle() {
    closeSSE();
    if (context.inspectAbortController) {
      context.inspectAbortController.abort('user_cancelled');
      context.inspectAbortController = null;
    }
    context.metadata = null;
    context.currentJobId = null;
    context.isInspecting = false;
    context.isSubmittingJob = false;
    restoreOriginalArtwork();
    context.playlistTrackOverrides = {};
    context.activePlaylistTrackIndex = 1;

    if (elements.metaTitle) elements.metaTitle.value = '';
    if (elements.metaArtist) elements.metaArtist.value = '';
    if (elements.metaAlbum) elements.metaAlbum.value = '';
    if (elements.metaYear) elements.metaYear.value = '';

    if (elements.submitBtn) {
      elements.submitBtn.disabled = false;
      elements.submitBtn.textContent = 'Inspect';
    }
    if (elements.urlInput) {
      elements.urlInput.disabled = false;
      elements.urlInput.value = '';
    }
    if (elements.startDownloadBtn) {
      elements.startDownloadBtn.disabled = false;
      elements.startDownloadBtn.textContent = 'Confirm & Download';
    }

    setState(States.IDLE);
  }

  // Helper Formatter
  function formatDuration(sec) {
    const s = parseInt(sec, 10) || 0;
    const hours = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    if (hours > 0) {
      return `${hours}:${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  }

  // Event Listeners Binding
  function bindActionListeners() {
    elements.cancelInspectBtn.addEventListener('click', resetToIdle);
    if (elements.cancelInspectingBtn) {
      elements.cancelInspectingBtn.addEventListener('click', () => {
        if (context.inspectAbortController) {
          context.inspectAbortController.abort('user_cancelled');
        }
        resetToIdle();
      });
    }
    elements.startDownloadBtn.addEventListener('click', startDownload);
    elements.cancelDownloadBtn.addEventListener('click', cancelDownload);
    elements.resetBtn.addEventListener('click', resetToIdle);
    elements.errorRetryBtn.addEventListener('click', resetToIdle);
    elements.cancelledResetBtn.addEventListener('click', resetToIdle);
  }

  // Navigation & Mobile Drawer Controller
  function initNavigation() {
    if (elements.mobileMenuBtn && elements.siteNav) {
      elements.mobileMenuBtn.addEventListener('click', () => {
        const isOpen = elements.siteNav.classList.toggle('open');
        elements.mobileMenuBtn.setAttribute('aria-expanded', String(isOpen));
        const menuIcon = elements.mobileMenuBtn.querySelector('.menu-icon');
        const closeIcon = elements.mobileMenuBtn.querySelector('.close-icon');
        if (menuIcon && closeIcon) {
          menuIcon.style.display = isOpen ? 'none' : 'block';
          closeIcon.style.display = isOpen ? 'block' : 'none';
        }
      });
    }

    elements.navLinks.forEach((link) => {
      link.addEventListener('click', () => {
        elements.navLinks.forEach((l) => l.classList.remove('active'));
        link.classList.add('active');
        if (elements.siteNav && elements.siteNav.classList.contains('open')) {
          elements.siteNav.classList.remove('open');
          if (elements.mobileMenuBtn) {
            elements.mobileMenuBtn.setAttribute('aria-expanded', 'false');
            const menuIcon = elements.mobileMenuBtn.querySelector('.menu-icon');
            const closeIcon = elements.mobileMenuBtn.querySelector('.close-icon');
            if (menuIcon && closeIcon) {
              menuIcon.style.display = 'block';
              closeIcon.style.display = 'none';
            }
          }
        }
      });
    });

    // Scrollspy for active nav link highlighting
    const sections = document.querySelectorAll('section[id]');
    window.addEventListener('scroll', () => {
      const scrollY = window.pageYOffset;
      sections.forEach((section) => {
        const sectionHeight = section.offsetHeight;
        const sectionTop = section.offsetTop - 120;
        const sectionId = section.getAttribute('id');
        if (scrollY > sectionTop && scrollY <= sectionTop + sectionHeight) {
          elements.navLinks.forEach((l) => {
            if (l.getAttribute('href') === `#${sectionId}`) {
              l.classList.add('active');
            } else {
              l.classList.remove('active');
            }
          });
        }
      });
    });
  }

  // =========================================================================
  // LIBRARY & HISTORY CONTROLLER
  // =========================================================================

  const libraryState = {
    page: 1,
    pageSize: 15,
    status: '',
    profile: '',
    searchQuery: '',
    totalItems: 0,
    totalPages: 1,
    isLoading: false,
    searchDebounceTimer: null,
    requestId: 0,
  };

  async function fetchLibraryJobs() {
    if (!elements.libraryTbody) return;

    const currentReqId = ++libraryState.requestId;
    libraryState.isLoading = true;

    if (elements.libraryLoading) elements.libraryLoading.style.display = 'flex';
    if (elements.libraryEmpty) elements.libraryEmpty.style.display = 'none';

    try {
      const params = new URLSearchParams({
        page: String(libraryState.page),
        page_size: String(libraryState.pageSize),
      });

      if (libraryState.status) params.append('status', libraryState.status);
      if (libraryState.profile) params.append('profile', libraryState.profile);
      if (libraryState.searchQuery) params.append('q', libraryState.searchQuery);

      const res = await fetch(`/api/v1/jobs?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();

      // Guard against out-of-order stale responses
      if (currentReqId !== libraryState.requestId) return;

      const data = json.data || {};
      const items = data.items || [];
      const pagination = data.pagination || {};

      libraryState.totalItems = pagination.total_items || 0;
      libraryState.totalPages = pagination.total_pages || 1;

      renderLibraryTable(items);
      updateLibraryPagination(pagination);
    } catch (err) {
      console.error('Failed to fetch library jobs:', err);
      if (currentReqId === libraryState.requestId && elements.libraryTbody) {
        elements.libraryTbody.innerHTML = `<tr><td colspan="6" class="text-center" style="padding: 2rem; color: #ef4444;">Failed to load library history. Please try refreshing.</td></tr>`;
      }
    } finally {
      if (currentReqId === libraryState.requestId) {
        libraryState.isLoading = false;
        if (elements.libraryLoading) elements.libraryLoading.style.display = 'none';
      }
    }
  }

  function renderLibraryTable(items) {
    if (!elements.libraryTbody) return;
    elements.libraryTbody.innerHTML = '';

    if (items.length === 0) {
      if (elements.libraryEmpty) elements.libraryEmpty.style.display = 'flex';
      return;
    }

    if (elements.libraryEmpty) elements.libraryEmpty.style.display = 'none';

    items.forEach((job) => {
      const tr = document.createElement('tr');

      const title = job.title || 'Untitled Audio';
      const shortId = (job.id || '').substring(0, 8);
      const isPlaylist = Boolean(job.is_playlist);
      const trackCount = job.track_count || (isPlaylist ? 'Multiple' : 1);
      const formattedDate = job.created_at
        ? new Date(job.created_at).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          })
        : '—';

      const statusBadgeClass = `status-${job.status || 'queued'}`;

      let actionsHtml = `<button type="button" class="btn btn-secondary btn-sm view-details-btn" data-id="${job.id}" title="View details and tracks">Details</button>`;

      if (job.file_available && job.download_url) {
        actionsHtml += ` <a href="${job.download_url}" class="btn btn-primary btn-sm" download title="Download file">Download</a>`;
      } else if (job.status === 'completed' && !job.file_available) {
        actionsHtml += ` <span class="status-badge status-expired" title="File was purged from storage by Janitor">Purged</span>`;
      }

      const activeStatuses = ['queued', 'fetching_metadata', 'downloading', 'converting', 'tagging'];
      if (!activeStatuses.includes(job.status)) {
        actionsHtml += ` <button type="button" class="btn btn-secondary btn-sm retry-job-btn" data-id="${job.id}" title="Retry job">Retry</button>`;
      }

      tr.innerHTML = `
        <td>
          <div class="job-title-cell">
            <a href="javascript:void(0)" class="job-title-text view-details-btn" data-id="${job.id}" title="${escapeHtml(title)}">${escapeHtml(title)}</a>
            <span class="job-meta-text">ID: ${shortId} • <a href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer" style="color:inherit;text-decoration:underline;">Source</a></span>
          </div>
        </td>
        <td>
          <div style="display:flex;flex-direction:column;gap:0.2rem;">
            <span style="font-weight:600;text-transform:capitalize;">${escapeHtml(job.profile || 'standard')}</span>
            <span style="font-size:0.75rem;color:var(--text-muted);">${escapeHtml((job.format || '').toUpperCase())}</span>
          </div>
        </td>
        <td>
          <span class="status-badge ${statusBadgeClass}">${escapeHtml(job.status || 'queued')}</span>
        </td>
        <td>
          <span style="font-size:0.85rem;">${isPlaylist ? `${trackCount} tracks` : '1 track'}</span>
        </td>
        <td>
          <span style="font-size:0.8rem;color:var(--text-muted);">${formattedDate}</span>
        </td>
        <td class="text-right">
          <div class="library-actions">${actionsHtml}</div>
        </td>
      `;

      elements.libraryTbody.appendChild(tr);
    });

    // Attach listeners for dynamic row action buttons
    elements.libraryTbody.querySelectorAll('.view-details-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const jobId = btn.getAttribute('data-id');
        if (jobId) showJobDetailsModal(jobId);
      });
    });

    elements.libraryTbody.querySelectorAll('.retry-job-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const jobId = btn.getAttribute('data-id');
        if (jobId) retryJob(jobId, btn);
      });
    });
  }

  function updateLibraryPagination(pagination) {
    if (!elements.paginationInfo) return;

    const total = pagination.total_items || 0;
    const page = pagination.page || 1;
    const pageSize = pagination.page_size || libraryState.pageSize;
    const totalPages = pagination.total_pages || 1;

    const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
    const end = Math.min(page * pageSize, total);

    elements.paginationInfo.textContent = `Showing ${start}–${end} of ${total} items`;
    if (elements.paginationCurrent) {
      elements.paginationCurrent.textContent = `Page ${page} of ${totalPages}`;
    }

    if (elements.paginationPrev) {
      elements.paginationPrev.disabled = !pagination.has_prev;
    }
    if (elements.paginationNext) {
      elements.paginationNext.disabled = !pagination.has_next;
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  async function showJobDetailsModal(jobId) {
    if (!elements.jobDetailsModal || !elements.modalJobBody) return;

    elements.jobDetailsModal.classList.add('active');
    elements.jobDetailsModal.setAttribute('aria-hidden', 'false');
    elements.modalJobTitle.textContent = 'Loading Job Details...';
    elements.modalJobBody.innerHTML = '<div style="padding:2rem;text-align:center;"><div class="spinner-sm"></div></div>';

    try {
      const res = await fetch(`/api/v1/jobs/${jobId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      const job = json.data;
      if (!job) throw new Error('No job data returned');

      elements.modalJobTitle.textContent = job.title || 'Job Details';

      const tracks = job.tracks || [];

      let tracklistHtml = '';
      if (tracks.length > 0) {
        tracklistHtml = `
          <div>
            <div style="font-size:0.8rem;font-weight:700;margin-bottom:0.4rem;color:var(--text-secondary);text-transform:uppercase;">Tracks (${tracks.length})</div>
            <div class="modal-tracklist">
              ${tracks.map((t) => `
                <div class="modal-track-row">
                  <span>${t.track_index}. ${escapeHtml(t.track_title)}</span>
                  <span class="status-badge status-${t.status || 'pending'}">${escapeHtml(t.status || 'pending')}</span>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }

      let errorHtml = '';
      if (job.error_message) {
        errorHtml = `
          <div style="padding:0.75rem;border-radius:var(--radius-sm);background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);color:#ef4444;font-size:0.82rem;">
            <strong>Error:</strong> ${escapeHtml(job.error_message)}
          </div>
        `;
      }

      let downloadActionHtml = '';
      if (job.file_available && job.download_url) {
        downloadActionHtml = `<a href="${job.download_url}" class="btn btn-primary" download>Download File</a>`;
      }

      elements.modalJobBody.innerHTML = `
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-item-label">Job ID</span>
            <span class="detail-item-value" style="font-family:monospace;font-size:0.75rem;">${escapeHtml(job.id)}</span>
          </div>
          <div class="detail-item">
            <span class="detail-item-label">Status</span>
            <span class="detail-item-value"><span class="status-badge status-${job.status}">${escapeHtml(job.status)}</span></span>
          </div>
          <div class="detail-item">
            <span class="detail-item-label">Profile</span>
            <span class="detail-item-value" style="text-transform:capitalize;">${escapeHtml(job.profile || 'standard')}</span>
          </div>
          <div class="detail-item">
            <span class="detail-item-label">Format / Quality</span>
            <span class="detail-item-value">${escapeHtml(job.format)} (${escapeHtml(job.quality)})</span>
          </div>
          <div class="detail-item">
            <span class="detail-item-label">Created At</span>
            <span class="detail-item-value">${job.created_at ? new Date(job.created_at).toLocaleString() : '—'}</span>
          </div>
          <div class="detail-item">
            <span class="detail-item-label">Completed At</span>
            <span class="detail-item-value">${job.completed_at ? new Date(job.completed_at).toLocaleString() : '—'}</span>
          </div>
          <div class="detail-item" style="grid-column:1/-1;">
            <span class="detail-item-label">Source URL</span>
            <span class="detail-item-value"><a href="${escapeHtml(job.url)}" target="_blank" rel="noopener noreferrer" style="color:var(--accent-violet);text-decoration:underline;">${escapeHtml(job.url)}</a></span>
          </div>
        </div>

        ${errorHtml}
        ${tracklistHtml}
      `;

      if (elements.modalJobFooter) {
        elements.modalJobFooter.innerHTML = '';
        if (downloadActionHtml) {
          elements.modalJobFooter.innerHTML += downloadActionHtml;
        }
        elements.modalJobFooter.innerHTML += '<button type="button" id="modal-dismiss-btn-dyn" class="btn btn-secondary">Close</button>';
        const dynClose = document.getElementById('modal-dismiss-btn-dyn');
        if (dynClose) dynClose.addEventListener('click', closeJobDetailsModal);
      }
    } catch (err) {
      console.error('Failed to load job details:', err);
      elements.modalJobBody.innerHTML = '<div style="color:#ef4444;padding:1rem;">Failed to load job details.</div>';
    }
  }

  function closeJobDetailsModal() {
    if (elements.jobDetailsModal) {
      elements.jobDetailsModal.classList.remove('active');
      elements.jobDetailsModal.setAttribute('aria-hidden', 'true');
    }
  }

  async function retryJob(jobId, btnEl) {
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.textContent = 'Retrying...';
    }

    try {
      const res = await fetch(`/api/v1/jobs/${jobId}/retry`, { method: 'POST' });
      const json = await res.json();
      if (!res.ok) {
        alert(json.detail?.message || 'Failed to retry job.');
        return;
      }

      const newJob = json.data;
      if (newJob && newJob.id) {
        // Refresh library table
        fetchLibraryJobs();
        // Switch to downloading state and start SSE for this newly submitted job
        context.currentJobId = newJob.id;
        setState(States.DOWNLOADING);
        elements.dlTitle.textContent = newJob.title || 'Processing Retry Download...';
        elements.progressBarFill.style.width = '0%';
        elements.progressPercent.textContent = '0%';
        initSSE(newJob.id);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } catch (err) {
      console.error('Error retrying job:', err);
      alert('An error occurred while retrying the download job.');
    } finally {
      if (btnEl) {
        btnEl.disabled = false;
        btnEl.textContent = 'Retry';
      }
    }
  }

  function initLibrary() {
    if (!elements.librarySearch) return;

    // Search input debounced handler
    elements.librarySearch.addEventListener('input', () => {
      const query = elements.librarySearch.value.trim();
      if (elements.libraryClearSearch) {
        elements.libraryClearSearch.style.display = query ? 'block' : 'none';
      }

      clearTimeout(libraryState.searchDebounceTimer);
      libraryState.searchDebounceTimer = setTimeout(() => {
        libraryState.searchQuery = query;
        libraryState.page = 1;
        fetchLibraryJobs();
      }, 300);
    });

    if (elements.libraryClearSearch) {
      elements.libraryClearSearch.addEventListener('click', () => {
        elements.librarySearch.value = '';
        elements.libraryClearSearch.style.display = 'none';
        libraryState.searchQuery = '';
        libraryState.page = 1;
        fetchLibraryJobs();
      });
    }

    // Status filter
    if (elements.libraryStatusFilter) {
      elements.libraryStatusFilter.addEventListener('change', () => {
        libraryState.status = elements.libraryStatusFilter.value;
        libraryState.page = 1;
        fetchLibraryJobs();
      });
    }

    // Profile filter
    if (elements.libraryProfileFilter) {
      elements.libraryProfileFilter.addEventListener('change', () => {
        libraryState.profile = elements.libraryProfileFilter.value;
        libraryState.page = 1;
        fetchLibraryJobs();
      });
    }

    // Refresh button
    if (elements.libraryRefreshBtn) {
      elements.libraryRefreshBtn.addEventListener('click', () => {
        fetchLibraryJobs();
      });
    }

    // Pagination handlers
    if (elements.paginationPrev) {
      elements.paginationPrev.addEventListener('click', () => {
        if (libraryState.page > 1) {
          libraryState.page -= 1;
          fetchLibraryJobs();
        }
      });
    }

    if (elements.paginationNext) {
      elements.paginationNext.addEventListener('click', () => {
        if (libraryState.page < libraryState.totalPages) {
          libraryState.page += 1;
          fetchLibraryJobs();
        }
      });
    }

    // Modal close listeners
    if (elements.modalCloseBtn) {
      elements.modalCloseBtn.addEventListener('click', closeJobDetailsModal);
    }
    if (elements.modalDismissBtn) {
      elements.modalDismissBtn.addEventListener('click', closeJobDetailsModal);
    }
    if (elements.jobDetailsModal) {
      elements.jobDetailsModal.addEventListener('click', (e) => {
        if (e.target === elements.jobDetailsModal) {
          closeJobDetailsModal();
        }
      });
    }

    // Initial load
    fetchLibraryJobs();
  }

  // =========================================================================
  // LEGAL & TRUST MODALS CONTROLLER
  // =========================================================================

  function initLegalModals() {
    function openModal(modalId) {
      const modal = document.getElementById(modalId);
      if (modal) {
        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
      }
    }

    function closeModal(modal) {
      if (modal) {
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
      }
    }

    const openPrivacyBtn = document.getElementById('open-privacy-btn');
    if (openPrivacyBtn) {
      openPrivacyBtn.addEventListener('click', () => openModal('privacy-modal'));
    }

    const openTermsBtn = document.getElementById('open-terms-btn');
    if (openTermsBtn) {
      openTermsBtn.addEventListener('click', () => openModal('terms-modal'));
    }

    const openDmcaBtn = document.getElementById('open-dmca-btn');
    if (openDmcaBtn) {
      openDmcaBtn.addEventListener('click', () => openModal('dmca-modal'));
    }

    // Generic data-close handler
    document.querySelectorAll('[data-close]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const modalId = btn.getAttribute('data-close');
        if (modalId) {
          closeModal(document.getElementById(modalId));
        }
      });
    });

    // Close on backdrop click
    document.querySelectorAll('.modal-backdrop').forEach((modal) => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          closeModal(modal);
        }
      });
    });

    // Escape key listener for any open modal
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-backdrop.active').forEach((modal) => {
          closeModal(modal);
        });
      }
    });
  }

  // Application Entrypoint Initialization
  document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initTheme();
    initStartupAnimation();
    initNavigation();
    initProfileSelection();
    initFormatSelection();
    initArtworkHandlers();
    initMetadataEditorHandlers();
    initInputHandlers();
    bindActionListeners();
    initLibrary();
    initLegalModals();
  });
})();
