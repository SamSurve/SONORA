"""Auralis Storage Lifecycle Management and Automated Janitor Daemon.

Manages isolated scratch/completed job directories, enforces disk space quotas,
and purges expired downloads via background TTL garbage collection.
"""

import logging
import shutil
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.db.repository import get_expired_jobs, mark_job_expired

logger = logging.getLogger(__name__)


def get_job_temp_dir(job_id: str) -> Path:
    """Returns and ensures creation of an isolated temporary scratchpad for a job."""
    temp_dir = settings.TEMP_DIR / job_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def get_job_completed_dir(job_id: str) -> Path:
    """Returns and ensures creation of an isolated directory for completed job files."""
    completed_dir = settings.COMPLETED_DIR / job_id
    completed_dir.mkdir(parents=True, exist_ok=True)
    return completed_dir


def cleanup_job_temp_dir(job_id: str) -> bool:
    """Safely and recursively removes a job's temporary scratch directory."""
    temp_dir = settings.TEMP_DIR / job_id
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug("Cleaned up temp directory for job '%s': %s", job_id, temp_dir)
            return True
        except Exception as e:
            logger.warning("Error removing temp directory for job '%s': %s", job_id, e)
            return False
    return True


def cleanup_job_completed_dir(job_id: str) -> bool:
    """Safely removes a job's completed files directory."""
    completed_dir = settings.COMPLETED_DIR / job_id
    if completed_dir.exists():
        try:
            shutil.rmtree(completed_dir, ignore_errors=True)
            logger.info("Cleaned up completed directory for job '%s': %s", job_id, completed_dir)
            return True
        except Exception as e:
            logger.warning("Error removing completed directory for job '%s': %s", job_id, e)
            return False
    return True


def check_disk_space(target_path: Path | None = None, min_free_mb: int | None = None) -> bool:
    """Checks if the filesystem hosting media storage has sufficient free space.

    Args:
        target_path: Path to inspect (defaults to settings.COMPLETED_DIR).
        min_free_mb: Required free space in MB (defaults to settings.DISK_FREE_THRESHOLD_MB).

    Returns:
        True if free space >= min_free_mb, False otherwise.
    """
    check_dir = target_path or settings.COMPLETED_DIR
    check_dir.mkdir(parents=True, exist_ok=True)

    threshold_mb = min_free_mb if min_free_mb is not None else settings.DISK_FREE_THRESHOLD_MB
    threshold_bytes = threshold_mb * 1024 * 1024

    try:
        usage = shutil.disk_usage(check_dir)
        is_sufficient = usage.free >= threshold_bytes
        if not is_sufficient:
            logger.warning(
                "Disk space threshold breached on '%s': %d MB free < %d MB required.",
                check_dir,
                usage.free // (1024 * 1024),
                threshold_mb,
            )
        return is_sufficient
    except Exception as e:
        logger.error("Failed to query disk usage on '%s': %s", check_dir, e)
        return True  # Fallback gracefully if OS permissions block disk_usage


def run_janitor_cleanup() -> int:
    """Executes a complete cleanup cycle for expired downloads and orphan temporary files.

    Performs filesystem deletions outside database transaction blocks.

    Returns:
        Number of expired jobs/directories purged.
    """
    purged_count = 0
    now_iso = datetime.now(UTC).isoformat()
    active_job_ids: set[str] = set()
    expired_jobs: list[dict[str, str]] = []

    # 1. Query expired jobs and active job IDs from database (Read-only context)
    try:
        from app.db.database import get_db_read
        from app.db.repository import get_active_job_ids

        with get_db_read() as conn:
            active_job_ids = get_active_job_ids(conn)
            expired_jobs = get_expired_jobs(conn, before_iso=now_iso)
    except Exception as e:
        logger.error("Janitor database scan encountered an error: %s", e)

    # 2. Perform filesystem deletions OUTSIDE database transaction blocks
    for job in expired_jobs:
        job_id = job["id"]
        cleanup_job_completed_dir(job_id)
        cleanup_job_temp_dir(job_id)

        # Update database status in a short write transaction
        try:
            from app.db.database import get_db_write

            with get_db_write() as conn:
                mark_job_expired(conn, job_id)
            purged_count += 1
            logger.info(
                "Janitor purged expired job '%s' (expired at %s)",
                job_id,
                job.get("expires_at"),
            )
        except Exception as e:
            logger.error("Failed to mark job '%s' as expired in database: %s", job_id, e)

    # 2. Purge orphaned scratch folders in data/temp older than 30 minutes (excluding active jobs)
    now_ts = time.time()
    temp_cutoff_ts = now_ts - 1800  # 30 minutes
    if settings.TEMP_DIR.exists():
        for item in settings.TEMP_DIR.iterdir():
            if item.is_dir():
                if item.name in active_job_ids:
                    continue  # Strictly protect actively running jobs
                try:
                    if item.stat().st_mtime < temp_cutoff_ts:
                        shutil.rmtree(item, ignore_errors=True)
                        logger.info("Janitor purged orphaned temp folder: %s", item)
                        purged_count += 1
                except Exception as e:
                    logger.debug("Could not inspect/remove temp folder '%s': %s", item, e)

    # 3. Purge orphaned completed folders older than TTL (excluding active jobs)
    completed_cutoff_ts = now_ts - (settings.JOB_TTL_MINUTES * 60)
    if settings.COMPLETED_DIR.exists():
        for item in settings.COMPLETED_DIR.iterdir():
            if item.is_dir():
                if item.name in active_job_ids:
                    continue  # Strictly protect actively running jobs
                try:
                    if item.stat().st_mtime < completed_cutoff_ts:
                        shutil.rmtree(item, ignore_errors=True)
                        logger.info("Janitor purged orphaned completed folder: %s", item)
                        purged_count += 1
                except Exception as e:
                    logger.debug("Could not inspect/remove completed folder '%s': %s", item, e)

    return purged_count


class JanitorDaemon(threading.Thread):
    """Background daemon thread that periodically triggers storage cleanup."""

    def __init__(self, interval_seconds: int = 300) -> None:
        super().__init__(name="AuralisJanitorDaemon", daemon=True)
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()

    def run(self) -> None:
        logger.info("Janitor daemon started with interval %ds.", self.interval_seconds)
        while not self._stop_event.is_set():
            try:
                run_janitor_cleanup()
            except Exception as e:
                logger.error("Unhandled exception in janitor cleanup cycle: %s", e)
            self._stop_event.wait(timeout=self.interval_seconds)
        logger.info("Janitor daemon stopped.")

    def stop(self) -> None:
        """Signals the daemon thread to terminate."""
        self._stop_event.set()
