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
    targetFormat: 'mp3_320',
    quality: '320',
    metadata: null,
    selectedTrackIndices: [],
    currentJobId: null,
    eventSource: null,
    ssePollInterval: null,
  };

  // DOM Elements Registry
  const elements = {};

  function initElements() {
    elements.overlay = document.getElementById('startup-overlay');
    elements.themeToggle = document.getElementById('theme-toggle');

    elements.urlInput = document.getElementById('url-input');
    elements.clearBtn = document.getElementById('clear-btn');
    elements.downloadForm = document.getElementById('download-form');
    elements.formatChips = document.querySelectorAll('.format-chip');
    elements.qualityNote = document.getElementById('quality-note');

    elements.readyArtwork = document.getElementById('ready-artwork');
    elements.readyBadge = document.getElementById('ready-type-badge');
    elements.readyTitle = document.getElementById('ready-title');
    elements.readyArtist = document.getElementById('ready-artist');
    elements.readyDuration = document.getElementById('ready-duration');
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

  // Format & Quality Selection Panel Handler
  function initFormatSelection() {
    elements.formatChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        elements.formatChips.forEach((c) => c.classList.remove('active'));
        chip.classList.add('active');

        context.targetFormat = chip.getAttribute('data-format');
        context.quality = chip.getAttribute('data-quality');

        const desc = chip.querySelector('.chip-desc')?.textContent || '';
        if (context.targetFormat.startsWith('native_') || context.targetFormat === 'm4a' || context.targetFormat === 'opus') {
          elements.qualityNote.textContent = 'Direct Stream Copy preserves raw source audio without re-encoding loss.';
        } else if (context.targetFormat === 'flac') {
          elements.qualityNote.textContent = 'Encapsulates source audio into a FLAC lossless container without upscaling.';
        } else {
          elements.qualityNote.textContent = 'Transcodes audio to universal MP3 format for broad playback support.';
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

  // Metadata Inspection Action
  async function handleMetadataInspection(url) {
    setState(States.INSPECTING);

    try {
      const response = await fetch('/api/v1/metadata', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, is_playlist: false }),
      });

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
      showError('Network error connecting to SONORA backend service.');
    }
  }

  // Render Metadata Ready View
  function renderReadyState() {
    const data = context.metadata;
    if (!data) return;

    elements.readyTitle.textContent = data.title || 'Unknown Media';
    elements.readyArtist.textContent = data.uploader || 'Unknown Artist';
    elements.readyDuration.textContent = formatDuration(data.duration_seconds || 0);

    if (data.thumbnail_url) {
      elements.readyArtwork.src = data.thumbnail_url;
      elements.dlArtwork.src = data.thumbnail_url;
    } else {
      elements.readyArtwork.src = '/static/img/fallback-artwork.png';
      elements.dlArtwork.src = '/static/img/fallback-artwork.png';
    }

    if (data.is_playlist && data.tracks && data.tracks.length > 0) {
      elements.readyBadge.textContent = `Playlist (${data.tracks.length} tracks)`;
      elements.playlistContainer.style.display = 'block';
      renderPlaylistItems(data.tracks);
    } else {
      elements.readyBadge.textContent = 'Single Track';
      elements.playlistContainer.style.display = 'none';
      context.selectedTrackIndices = [1];
    }
  }

  // Playlist Checklist Renderer
  function renderPlaylistItems(tracks) {
    elements.playlistList.innerHTML = '';
    context.selectedTrackIndices = tracks.map((t) => t.index);

    elements.totalCount.textContent = tracks.length;
    elements.selectedCount.textContent = tracks.length;

    tracks.forEach((track) => {
      const item = document.createElement('label');
      item.className = 'playlist-item-row';
      item.style.display = 'flex';
      item.style.alignItems = 'center';
      item.style.gap = '0.75rem';
      item.style.padding = '0.4rem 0';
      item.style.cursor = 'pointer';

      item.innerHTML = `
        <input type="checkbox" class="track-checkbox" data-index="${track.index}" checked>
        <span class="track-num">${String(track.index).padStart(2, '0')}.</span>
        <span class="track-name" style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${track.title}</span>
        <span class="track-dur" style="color:var(--text-muted); font-size:0.8rem;">${formatDuration(track.duration_seconds)}</span>
      `;

      const checkbox = item.querySelector('.track-checkbox');
      checkbox.addEventListener('change', () => {
        updateSelectedTrackIndices();
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
  }

  // Start Download Action
  async function startDownload() {
    if (!context.metadata) return;

    setState(States.DOWNLOADING);
    elements.dlTitle.textContent = context.metadata.title;
    elements.dlStatusText.textContent = 'Enqueuing job...';
    elements.progressBarFill.style.width = '0%';
    elements.progressPercent.textContent = '0%';

    try {
      const payload = {
        url: context.metadata.url,
        format: context.targetFormat,
        quality: context.quality,
        is_playlist: context.metadata.is_playlist,
        selected_indices: context.selectedTrackIndices,
        title: context.metadata.title,
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

  function startPollingFallback(jobId) {
    if (context.ssePollInterval) clearInterval(context.ssePollInterval);

    context.ssePollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/v1/jobs/${jobId}`);
        const json = await res.json();
        if (res.ok && json.data) {
          const data = json.data;
          updateProgressUI(data);

          if (data.status === 'completed') {
            clearInterval(context.ssePollInterval);
            renderCompletedState(data);
          } else if (data.status === 'failed') {
            clearInterval(context.ssePollInterval);
            showError(data.error_message || 'Download task failed.');
          } else if (data.status === 'cancelled') {
            clearInterval(context.ssePollInterval);
            setState(States.CANCELLED);
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 2000);
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
      closeSSE();
      setState(States.CANCELLED);
    } catch (err) {
      console.error('Cancellation error:', err);
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
    context.metadata = null;
    context.currentJobId = null;
    elements.urlInput.value = '';
    setState(States.IDLE);
  }

  // Helper Formatter
  function formatDuration(sec) {
    const s = parseInt(sec, 10) || 0;
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  }

  // Event Listeners Binding
  function bindActionListeners() {
    elements.cancelInspectBtn.addEventListener('click', resetToIdle);
    elements.startDownloadBtn.addEventListener('click', startDownload);
    elements.cancelDownloadBtn.addEventListener('click', cancelDownload);
    elements.resetBtn.addEventListener('click', resetToIdle);
    elements.errorRetryBtn.addEventListener('click', resetToIdle);
    elements.cancelledResetBtn.addEventListener('click', resetToIdle);
  }

  // Application Entrypoint Initialization
  document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initTheme();
    initStartupAnimation();
    initFormatSelection();
    initInputHandlers();
    bindActionListeners();
  });
})();
