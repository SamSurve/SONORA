"""SONORA API v1 Endpoint Router.

Provides REST and SSE endpoints for metadata inspection, download job submission,
real-time progress event streaming, cancellation, and completed file delivery.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.constants import ErrorCode, JobStatus
from app.core.security import InvalidURLException, SSRFSecurityException
from app.db.database import get_db_read
from app.db.repository import get_job, get_tracks_for_job
from app.engine.ytdlp_engine import ProgressEvent
from app.services.job_manager import (
    JobManager,
    PlaylistQuotaExceededException,
    RateLimitExceededException,
    StorageLimitExceededException,
)
from app.services.metadata_service import extract_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["SONORA Core API"])


# Global JobManager instance (initialized during app startup)
_job_manager_instance: JobManager | None = None


def get_job_manager() -> JobManager:
    """Retrieves the active global JobManager instance."""
    global _job_manager_instance
    if _job_manager_instance is None:
        _job_manager_instance = JobManager()
    return _job_manager_instance


class MetadataRequest(BaseModel):
    """Payload for pre-download metadata inspection."""

    url: str = Field(..., description="Target media URL to inspect")
    is_playlist: bool = Field(default=False, description="Hint whether URL target is a playlist")


class JobSubmitRequest(BaseModel):
    """Payload for submitting a new download job."""

    url: str = Field(..., description="Target media URL")
    format: str = Field(default="mp3_320", description="Selected audio format code")
    quality: str = Field(default="320", description="Quality selection string")
    is_playlist: bool = Field(default=False, description="Whether job is a playlist")
    selected_indices: list[int] | None = Field(
        default=None, description="Selected playlist track indices"
    )
    title: str | None = Field(default=None, description="Optional custom title override")


def _sanitize_error_message(msg: str) -> str:
    """Strips internal system file paths and tracebacks from error strings."""
    if not msg:
        return "An internal processing error occurred."
    import re

    # Replace Windows and Linux file paths
    cleaned = re.sub(r"[A-Za-z]:\\[^:\n\r]+", "[path]", msg)
    cleaned = re.sub(r"/[^\s:\n\r]+", "[path]", cleaned)
    # Truncate raw python tracebacks
    if "Traceback (most recent call last):" in cleaned:
        cleaned = cleaned.split("Traceback (most recent call last):")[0].strip()
    return cleaned or "Download processing failed."


@router.post("/metadata")
async def inspect_metadata(payload: MetadataRequest) -> dict[str, Any]:
    """Inspects a media URL and returns normalized tracklist metadata."""
    try:
        # Run blocking metadata extraction in threadpool to keep event loop responsive
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, extract_metadata, payload.url, payload.is_playlist
        )
        return {"status": "success", "data": result}
    except (InvalidURLException, SSRFSecurityException) as e:
        logger.warning("SSRF / Invalid URL rejected in metadata extraction: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.SSRF_VIOLATION.value
                if isinstance(e, SSRFSecurityException)
                else ErrorCode.INVALID_URL.value,
                "message": str(e),
            },
        ) from e
    except Exception as e:
        logger.error("Metadata extraction error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": ErrorCode.EXTRACTION_FAILED.value,
                "message": _sanitize_error_message(str(e)),
            },
        ) from e


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def create_download_job(payload: JobSubmitRequest, request: Request) -> dict[str, Any]:
    """Submits a new single-track or playlist download job."""
    client_ip = request.client.host if request.client else "unknown"
    manager = get_job_manager()

    try:
        job_id = manager.submit_job(
            url=payload.url,
            target_format=payload.format,
            quality=payload.quality,
            is_playlist=payload.is_playlist,
            selected_indices=payload.selected_indices,
            title=payload.title,
            client_id=client_ip,
        )
        return {
            "status": "success",
            "data": {
                "job_id": job_id,
                "status": JobStatus.QUEUED.value,
            },
        }
    except RateLimitExceededException as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": ErrorCode.RATE_LIMIT_EXCEEDED.value,
                "message": "Submission rate limit exceeded. Please wait a minute before retrying.",
            },
        ) from e
    except PlaylistQuotaExceededException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.STORAGE_LIMIT_EXCEEDED.value,
                "message": str(e),
            },
        ) from e
    except StorageLimitExceededException as e:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail={
                "code": ErrorCode.STORAGE_LIMIT_EXCEEDED.value,
                "message": str(e),
            },
        ) from e
    except (InvalidURLException, SSRFSecurityException) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.SSRF_VIOLATION.value
                if isinstance(e, SSRFSecurityException)
                else ErrorCode.INVALID_URL.value,
                "message": str(e),
            },
        ) from e
    except Exception as e:
        logger.error("Failed to submit download job: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": _sanitize_error_message(str(e)),
            },
        ) from e


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> dict[str, Any]:
    """Retrieves current job status, progress, speed, ETA, and track details."""
    with get_db_read() as conn:
        job = get_job(conn, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": ErrorCode.JOB_NOT_FOUND.value, "message": "Job not found"},
            )
        tracks = get_tracks_for_job(conn, job_id)

    # Sanitize error message if present
    if job.get("error_message"):
        job["error_message"] = _sanitize_error_message(job["error_message"])

    job["tracks"] = tracks
    return {"status": "success", "data": job}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job_execution(job_id: str) -> dict[str, Any]:
    """Cancels a queued or actively downloading job."""
    manager = get_job_manager()
    success = manager.cancel_job(job_id)
    if not success:
        # Check if job exists in DB
        with get_db_read() as conn:
            job = get_job(conn, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": ErrorCode.JOB_NOT_FOUND.value, "message": "Job not found"},
            )
    return {
        "status": "success",
        "data": {
            "job_id": job_id,
            "status": JobStatus.CANCELLED.value,
        },
    }


@router.get("/jobs/{job_id}/events")
async def stream_job_events(job_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events (SSE) streaming progress and status events."""
    manager = get_job_manager()
    context = manager.get_active_context(job_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_event(event: ProgressEvent) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        if context:
            context.add_listener(on_event)

        terminal_states = {
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
            JobStatus.EXPIRED.value,
        }

        try:
            while True:
                if await request.is_disconnected():
                    logger.debug("SSE client disconnected for job '%s'", job_id)
                    break

                try:
                    # Wait for event with timeout to periodically poll DB status
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    if event:
                        event_data = {
                            "job_id": event.job_id,
                            "status": event.status,
                            "progress": event.percent,
                            "speed": event.speed_bytes_per_sec,
                            "eta": event.eta_seconds,
                            "current_title": event.current_title,
                            "total_tracks": event.total_tracks,
                            "completed_tracks": event.completed_tracks,
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                except TimeoutError:
                    # Check DB status periodically
                    with get_db_read() as conn:
                        job = get_job(conn, job_id)
                    if job:
                        current_status = job.get("status")
                        db_event = {
                            "job_id": job_id,
                            "status": current_status,
                            "progress": job.get("progress", 0),
                            "speed": job.get("speed", 0.0),
                            "eta": job.get("eta", 0),
                            "title": job.get("title"),
                            "error_message": _sanitize_error_message(job.get("error_message", "")),
                        }
                        yield f"data: {json.dumps(db_event)}\n\n"
                        if current_status in terminal_states:
                            break
                    else:
                        break
        finally:
            if context:
                context.remove_listener(on_event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/downloads/{job_id}/file")
async def download_job_file(job_id: str) -> Response:
    """Delivers the completed audio track or playlist ZIP archive to the browser."""
    with get_db_read() as conn:
        job = get_job(conn, job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": ErrorCode.JOB_NOT_FOUND.value, "message": "Job not found"},
        )

    if job.get("status") != JobStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": f"Job is not completed yet (current status: {job.get('status')})",
            },
        )

    file_path_str = job.get("file_path")
    if not file_path_str:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ErrorCode.JOB_NOT_FOUND.value,
                "message": "Completed file path missing",
            },
        )

    file_path = Path(file_path_str)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ErrorCode.JOB_NOT_FOUND.value,
                "message": "Completed file no longer exists on storage",
            },
        )

    # Determine media type & clean attachment filename
    filename = file_path.name
    media_type = "application/zip" if filename.endswith(".zip") else "audio/mpeg"
    if filename.endswith(".m4a"):
        media_type = "audio/mp4"
    elif filename.endswith(".opus") or filename.endswith(".webm"):
        media_type = "audio/opus"
    elif filename.endswith(".flac"):
        media_type = "audio/flac"
    elif filename.endswith(".wav"):
        media_type = "audio/wav"

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
