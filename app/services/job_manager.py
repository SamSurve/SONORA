"""Auralis Job Management Service.

Coordinates background execution via ThreadPoolExecutor, persists lifecycle state in
SQLite, enforces cooperative cancellation tokens, manages retries, enforces quotas and rate limits,
and broadcasts progress events.
"""

import logging
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.constants import AudioFormat, JobStatus
from app.core.security import (
    InvalidURLException,
    SSRFSecurityException,
    validate_url,
)
from app.db.database import get_db_read, get_db_write
from app.db.repository import (
    add_track_to_job,
    create_job,
    get_active_job_ids,
    get_job,
    update_job_status,
    update_track_status,
)
from app.engine.archive_packager import create_playlist_zip
from app.engine.audio_tagger import tag_audio_file
from app.engine.janitor import (
    check_disk_space,
    cleanup_job_completed_dir,
    cleanup_job_temp_dir,
    get_job_completed_dir,
    get_job_temp_dir,
)
from app.engine.sanitizer import format_track_filename, safe_path_join, sanitize_filename
from app.engine.ytdlp_engine import (
    DownloadCancelledException,
    ProgressEvent,
    execute_download,
)

logger = logging.getLogger(__name__)


class StorageLimitExceededException(Exception):
    """Raised when server disk free space is below the safety threshold."""


class PlaylistQuotaExceededException(Exception):
    """Raised when a playlist job exceeds maximum allowed track items."""


class RateLimitExceededException(Exception):
    """Raised when a client identity breaches submission rate limits."""


class RateLimiter:
    """Thread-safe rolling window rate limiter per client identity."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._history: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_id: str | None) -> bool:
        if not client_id:
            return True
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = self._history.get(client_id, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]
            if len(valid_timestamps) >= self.max_requests:
                self._history[client_id] = valid_timestamps
                return False
            valid_timestamps.append(now)
            self._history[client_id] = valid_timestamps
            return True


class JobContext:
    """Thread-safe context tracking an active background job."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.cancel_event = threading.Event()
        self.future: Future[Any] | None = None
        self.listeners: list[Callable[[ProgressEvent], None]] = []
        self._lock = threading.Lock()

    def add_listener(self, callback: Callable[[ProgressEvent], None]) -> None:
        with self._lock:
            if callback not in self.listeners:
                self.listeners.append(callback)

    def remove_listener(self, callback: Callable[[ProgressEvent], None]) -> None:
        with self._lock:
            if callback in self.listeners:
                self.listeners.remove(callback)

    def emit(self, event: ProgressEvent) -> None:
        with self._lock:
            current_listeners = list(self.listeners)
        for listener in current_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.debug("Listener callback exception for job '%s': %s", self.job_id, e)


class JobManager:
    """Manages background download jobs, concurrency limits, and persistence."""

    def __init__(self, max_workers: int | None = None) -> None:
        self.max_workers = max_workers or settings.MAX_CONCURRENT_WORKERS
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="auralis-worker",
        )
        self._active_jobs: dict[str, JobContext] = {}
        self._registry_lock = threading.Lock()
        self.rate_limiter = RateLimiter(
            max_requests=settings.RATE_LIMIT_PER_MINUTE,
            window_seconds=60,
        )
        logger.info("JobManager initialized with %d worker threads.", self.max_workers)

        # Reconcile orphaned active jobs from previous process execution
        self.reconcile_startup_jobs()

    def reconcile_startup_jobs(self) -> int:
        """Reconciles non-terminal active jobs on server boot.

        Marks orphaned active jobs as FAILED and cleans up scratchpads.
        """
        reconciled_count = 0
        try:
            orphaned_ids: set[str] = set()
            with get_db_read() as conn:
                orphaned_ids = get_active_job_ids(conn)

            for job_id in orphaned_ids:
                try:
                    with get_db_write() as conn:
                        update_job_status(
                            conn,
                            job_id=job_id,
                            status=JobStatus.FAILED.value,
                            error_message="Job interrupted by server restart",
                        )
                    cleanup_job_temp_dir(job_id)
                    cleanup_job_completed_dir(job_id)
                    reconciled_count += 1
                    logger.info("Reconciled orphaned startup job '%s' -> FAILED.", job_id)
                except Exception as e:
                    logger.error("Error reconciling startup job '%s': %s", job_id, e)
        except Exception as e:
            logger.error("Failed to query orphaned startup jobs: %s", e)
        return reconciled_count

    def submit_job(
        self,
        url: str,
        target_format: AudioFormat | str = AudioFormat.MP3_320,
        quality: str = "320",
        is_playlist: bool = False,
        selected_indices: list[int] | None = None,
        title: str | None = None,
        client_id: str | None = None,
    ) -> str:
        """Submits a new download job for execution.

        1. Enforces client-level rate limits (if client_id is provided) and job quotas.
        2. Validates URL against deep SSRF rules.
        3. Enforces storage disk thresholds.
        4. Initializes job and track state in SQLite.
        5. Dispatches task to worker pool.

        Returns:
            job_id: Generated UUID string for tracking.
        """
        # Quota enforcement
        if is_playlist and selected_indices and len(selected_indices) > settings.MAX_PLAYLIST_ITEMS:
            msg = (
                f"Selected playlist items ({len(selected_indices)}) exceed maximum "
                f"allowed limit of {settings.MAX_PLAYLIST_ITEMS}."
            )
            raise PlaylistQuotaExceededException(msg)

        if client_id and not self.rate_limiter.is_allowed(client_id):
            msg = (
                f"Rate limit exceeded for client '{client_id}'. "
                f"Maximum {settings.RATE_LIMIT_PER_MINUTE} requests/min."
            )
            raise RateLimitExceededException(msg)

        # Step 1: Strict URL & SSRF Validation (Inherits Phase 1 security)
        validate_url(url, resolve_dns=True)

        if not check_disk_space():
            msg = (
                f"Storage threshold breached. "
                f"Minimum {settings.DISK_FREE_THRESHOLD_MB} MB required."
            )
            raise StorageLimitExceededException(msg)

        job_id = str(uuid.uuid4())
        format_str = (
            target_format.value if isinstance(target_format, AudioFormat) else str(target_format)
        )
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.JOB_TTL_MINUTES)

        # Step 3: Persist Initial State in SQLite using write lock context manager
        with get_db_write() as conn:
            create_job(
                conn=conn,
                job_id=job_id,
                url=url,
                target_format=format_str,
                quality=quality,
                is_playlist=is_playlist,
                title=title or "Preparing download...",
                expires_at=expires_at,
            )

        # Step 4: Register Context & Dispatch Worker
        context = JobContext(job_id)
        with self._registry_lock:
            self._active_jobs[job_id] = context

        future = self._executor.submit(
            self._run_job_with_retries,
            job_id=job_id,
            url=url,
            target_format=format_str,
            quality=quality,
            is_playlist=is_playlist,
            selected_indices=selected_indices,
            context=context,
        )
        context.future = future

        logger.info("Enqueued job '%s' for URL: %s", job_id, url)
        return job_id

    def cancel_job(self, job_id: str) -> bool:
        """Cooperatively signals an active job to cancel and updates its state."""
        with self._registry_lock:
            context = self._active_jobs.get(job_id)

        if not context:
            # Check if job exists in DB in queued/running state
            with get_db_read() as conn:
                job = get_job(conn, job_id)
            if job and job["status"] in (
                JobStatus.QUEUED.value,
                JobStatus.DOWNLOADING.value,
                JobStatus.FETCHING_METADATA.value,
                JobStatus.CONVERTING.value,
                JobStatus.TAGGING.value,
            ):
                with get_db_write() as conn:
                    update_job_status(
                        conn,
                        job_id=job_id,
                        status=JobStatus.CANCELLED.value,
                        error_message="Job was cancelled by user.",
                    )
                cleanup_job_temp_dir(job_id)
                cleanup_job_completed_dir(job_id)
                return True
            return False

        logger.info("Signaling cancellation for job '%s'.", job_id)
        context.cancel_event.set()

        # Update DB status
        with get_db_write() as conn:
            update_job_status(
                conn,
                job_id=job_id,
                status=JobStatus.CANCELLED.value,
                error_message="Job was cancelled by user.",
            )

        # Note: We do NOT perform immediate rmtree here while worker thread holds open file handles.
        # Worker thread will exit cooperatively via DownloadCancelledException and clean up.

        context.emit(
            ProgressEvent(
                job_id=job_id,
                stage="cancelled",
                percent=0.0,
                speed_bytes=0.0,
                eta_seconds=0,
                current_track="Cancelled",
            )
        )
        return True

    def subscribe(self, job_id: str, callback: Callable[[ProgressEvent], None]) -> None:
        """Registers a subscriber callback for real-time progress events."""
        with self._registry_lock:
            context = self._active_jobs.get(job_id)
        if context:
            context.add_listener(callback)

    def unsubscribe(self, job_id: str, callback: Callable[[ProgressEvent], None]) -> None:
        """Removes a subscriber callback."""
        with self._registry_lock:
            context = self._active_jobs.get(job_id)
        if context:
            context.remove_listener(callback)

    def get_active_context(self, job_id: str) -> JobContext | None:
        """Retrieves active JobContext for a given job ID if registered."""
        with self._registry_lock:
            return self._active_jobs.get(job_id)

    def _run_job_with_retries(
        self,
        job_id: str,
        url: str,
        target_format: str,
        quality: str,
        is_playlist: bool,
        selected_indices: list[int] | None,
        context: JobContext,
    ) -> None:
        """Worker wrapper implementing bounded retries with exponential backoff."""
        max_retries = 3
        backoff_base_sec = 1.0

        for attempt in range(1, max_retries + 1):
            if context.cancel_event.is_set():
                logger.info("Job '%s' cancelled prior to attempt %d.", job_id, attempt)
                self._record_final_state(job_id, JobStatus.CANCELLED, "Job was cancelled by user.")
                return

            try:
                self._execute_job_pipeline(
                    job_id=job_id,
                    url=url,
                    target_format=target_format,
                    quality=quality,
                    is_playlist=is_playlist,
                    selected_indices=selected_indices,
                    context=context,
                )
                # Succeeded
                return

            except DownloadCancelledException:
                logger.info("Job '%s' terminated via cooperative cancellation.", job_id)
                self._record_final_state(job_id, JobStatus.CANCELLED, "Job was cancelled by user.")
                return

            except (SSRFSecurityException, InvalidURLException) as sec_err:
                # Permanent security violations are NEVER retried
                logger.error("Permanent security failure in job '%s': %s", job_id, sec_err)
                self._record_final_state(
                    job_id, JobStatus.FAILED, f"Security violation: {sec_err}"
                )
                return

            except Exception as exc:
                if context.cancel_event.is_set():
                    logger.info("Job '%s' interrupted by cancellation: %s", job_id, exc)
                    self._record_final_state(
                        job_id, JobStatus.CANCELLED, "Job was cancelled by user."
                    )
                    return

                logger.error(
                    "Job '%s' attempt %d/%d failed with error: %s",
                    job_id,
                    attempt,
                    max_retries,
                    exc,
                    exc_info=True,
                )
                if attempt == max_retries:
                    logger.error("Job '%s' exhausted all %d retry attempts.", job_id, max_retries)
                    # Include error summary while stripping internal local filesystem paths
                    raw_err = str(exc)
                    clean_err = re.sub(r"[A-Za-z]:\\[^\s]+", "[path]", raw_err)
                    safe_error = f"Download failed after {max_retries} attempts: {clean_err}"
                    self._record_final_state(
                        job_id,
                        JobStatus.FAILED,
                        safe_error,
                    )
                    return

                # Bounded backoff
                sleep_duration = backoff_base_sec * (2 ** (attempt - 1))
                time.sleep(sleep_duration)

    def _execute_job_pipeline(
        self,
        job_id: str,
        url: str,
        target_format: str,
        quality: str,
        is_playlist: bool,
        selected_indices: list[int] | None,
        context: JobContext,
    ) -> None:
        """Executes the full media lifecycle: download -> tag -> package -> complete."""
        temp_dir = get_job_temp_dir(job_id)
        completed_dir = get_job_completed_dir(job_id)

        # Update status to DOWNLOADING
        with get_db_write() as conn:
            update_job_status(conn, job_id=job_id, status=JobStatus.DOWNLOADING.value, progress=0)

        # Throttle DB updates from high-frequency yt-dlp progress hooks
        last_db_update = [0.0]

        def _progress_bridge(event: ProgressEvent) -> None:
            context.emit(event)
            now = time.time()
            if now - last_db_update[0] >= 1.0:  # Update DB at most once per second
                last_db_update[0] = now
                try:
                    with get_db_write() as conn:
                        update_job_status(
                            conn,
                            job_id=job_id,
                            status=JobStatus.DOWNLOADING.value,
                            progress=int(event.percent),
                            speed=event.speed_bytes,
                            eta=event.eta_seconds,
                        )
                except Exception as e:
                    logger.debug("Progress DB update error: %s", e)

        # Step 1: Run yt-dlp inside isolated scratchpad
        info = execute_download(
            job_id=job_id,
            url=url,
            temp_dir=temp_dir,
            target_format=target_format,
            is_playlist=is_playlist,
            selected_indices=selected_indices,
            progress_callback=_progress_bridge,
            cancel_event=context.cancel_event,
        )

        if context.cancel_event.is_set():
            raise DownloadCancelledException("Cancelled after download.")

        # Step 2: Media Processing & Metadata Tagging
        context.emit(
            ProgressEvent(
                job_id=job_id,
                stage="tagging",
                percent=95.0,
                speed_bytes=0.0,
                eta_seconds=0,
                current_track="Embedding metadata & artwork...",
            )
        )

        # Locate fallback artwork if downloaded
        default_artwork_path: Path | None = None
        for img_ext in (".jpg", ".jpeg", ".png"):
            for candidate in temp_dir.glob(f"*{img_ext}"):
                default_artwork_path = candidate
                break
            if default_artwork_path:
                break

        # Discover audio files produced in scratchpad
        audio_extensions = {".mp3", ".m4a", ".opus", ".flac", ".wav"}
        downloaded_audio_files = [
            f for f in temp_dir.iterdir() if f.is_file() and f.suffix.lower() in audio_extensions
        ]

        if not downloaded_audio_files:
            raise FileNotFoundError(
                f"No audio files found in scratchpad '{temp_dir}' after download."
            )

        # Process each audio file, tag, and move to completed directory
        final_files: list[Path] = []
        album_name = info.get("title") or "Unknown Album"
        uploader = info.get("uploader") or info.get("channel") or "Unknown Artist"

        for idx, src_file in enumerate(sorted(downloaded_audio_files), start=1):
            if context.cancel_event.is_set():
                raise DownloadCancelledException("Cancelled during tagging.")

            raw_stem = src_file.stem
            clean_track_title = (
                raw_stem[6:]
                if is_playlist and len(raw_stem) > 5 and raw_stem[:3].isdigit()
                else raw_stem
            )
            clean_track_title = sanitize_filename(clean_track_title)

            # Match artwork per track by stem or fall back to general artwork
            track_artwork: Path | None = None
            for img_ext in (".jpg", ".jpeg", ".png"):
                candidate = src_file.with_suffix(img_ext)
                if candidate.exists():
                    track_artwork = candidate
                    break
            if not track_artwork:
                track_artwork = default_artwork_path

            # Tag audio file
            tag_audio_file(
                file_path=src_file,
                title=clean_track_title,
                artist=uploader,
                album=album_name if is_playlist else None,
                track_number=idx if is_playlist else None,
                artwork_path=track_artwork,
            )

            # Structure clean, safe destination filename
            safe_dest_name = format_track_filename(
                title=clean_track_title,
                extension=src_file.suffix,
                track_index=idx if is_playlist else None,
            )
            dest_file = safe_path_join(completed_dir, safe_dest_name)
            shutil.move(src_file, dest_file)
            final_files.append(dest_file)

            # Register track in DB
            if is_playlist:
                with get_db_write() as conn:
                    add_track_to_job(
                        conn=conn,
                        job_id=job_id,
                        track_index=idx,
                        track_title=clean_track_title,
                    )
                    update_track_status(conn, job_id=job_id, track_index=idx, status="completed")

        # Step 3: Archive packaging if playlist (Always package ZIP for playlists)
        final_delivery_path: Path
        if is_playlist:
            zip_path, zip_size = create_playlist_zip(
                job_id=job_id,
                job_completed_dir=completed_dir,
                playlist_title=album_name,
            )
            final_delivery_path = zip_path
            total_size = zip_size
        else:
            final_delivery_path = final_files[0]
            total_size = final_delivery_path.stat().st_size

        # Step 4: Scratchpad Cleanup
        cleanup_job_temp_dir(job_id)

        if context.cancel_event.is_set():
            raise DownloadCancelledException("Cancelled before completion.")

        # Step 5: Mark Job Completed in SQLite
        media_title = info.get("title") or final_delivery_path.stem
        with get_db_write() as conn:
            update_job_status(
                conn=conn,
                job_id=job_id,
                status=JobStatus.COMPLETED.value,
                progress=100,
                speed=0.0,
                eta=0,
                file_path=str(final_delivery_path),
                file_size=total_size,
            )

        context.emit(
            ProgressEvent(
                job_id=job_id,
                stage="completed",
                percent=100.0,
                speed_bytes=0.0,
                eta_seconds=0,
                current_track=media_title,
            )
        )
        logger.info(
            "Job '%s' completed successfully: %s (%d bytes)",
            job_id,
            final_delivery_path,
            total_size,
        )

        with self._registry_lock:
            self._active_jobs.pop(job_id, None)

    def _record_final_state(
        self, job_id: str, status: JobStatus, error_msg: str | None = None
    ) -> None:
        """Updates terminal state in SQLite and cleans up temp and completed directories."""
        cleanup_job_temp_dir(job_id)
        if status in (JobStatus.CANCELLED, JobStatus.FAILED):
            cleanup_job_completed_dir(job_id)

        try:
            with get_db_write() as conn:
                update_job_status(
                    conn,
                    job_id=job_id,
                    status=status.value,
                    error_message=error_msg,
                )
        except Exception as e:
            logger.error("Failed to record terminal state for job '%s': %s", job_id, e)

        with self._registry_lock:
            context = self._active_jobs.pop(job_id, None)

        if context:
            context.emit(
                ProgressEvent(
                    job_id=job_id,
                    stage=status.value,
                    percent=0.0,
                    speed_bytes=0.0,
                    eta_seconds=0,
                    current_track=error_msg or status.value,
                )
            )

    def get_job_info(self, job_id: str) -> dict[str, Any] | None:
        """Retrieves current job status from SQLite database using read-only context."""
        with get_db_read() as conn:
            return get_job(conn, job_id)

    def shutdown(self, wait: bool = True) -> None:
        """Gracefully terminates the worker thread pool."""
        logger.info("Shutting down JobManager worker pool...")
        with self._registry_lock:
            active_contexts = list(self._active_jobs.values())
        for ctx in active_contexts:
            ctx.cancel_event.set()
        self._executor.shutdown(wait=wait, cancel_futures=True)


# Singleton instance for application-wide service usage
job_manager = JobManager()
