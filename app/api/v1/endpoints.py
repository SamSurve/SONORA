"""SONORA API v1 Endpoint Router.

Provides REST and SSE endpoints for metadata inspection, download job submission,
real-time progress event streaming, cancellation, and completed file delivery.
"""

import asyncio
import json
import logging
import math
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.constants import (
    PROFILE_TAXONOMY,
    DownloadProfile,
    ErrorCode,
    JobStatus,
)
from app.core.security import InvalidURLException, SSRFSecurityException
from app.db.database import get_db_read
from app.db.repository import get_job, get_tracks_for_job, list_jobs_paginated
from app.engine.ytdlp_engine import ProgressEvent
from app.models.metadata import MetadataOverride
from app.services.job_manager import (
    JobManager,
    PlaylistQuotaExceededException,
    RateLimitExceededException,
    StorageLimitExceededException,
    job_manager,
)
from app.services.metadata_service import extract_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["SONORA Core API"])


def get_job_manager() -> JobManager:
    """Retrieves the active global JobManager instance."""
    return job_manager


def extract_client_ip(request: Request) -> str:
    """Extracts client IP address respecting trusted reverse proxies (HIGH-07).

    If connecting host is listed in settings.TRUSTED_PROXIES, inspects the
    X-Forwarded-For or X-Real-IP headers to determine the originating client IP.
    Otherwise, returns the direct socket peer address.
    """
    peer_ip = request.client.host if request.client else "unknown"
    if peer_ip in settings.TRUSTED_PROXIES:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_candidate = forwarded_for.split(",")[0].strip()
            if client_candidate:
                return client_candidate
        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip and x_real_ip.strip():
            return x_real_ip.strip()

    return peer_ip


class MetadataRequest(BaseModel):
    """Payload for pre-download metadata inspection."""

    url: str = Field(..., description="Target media URL to inspect")
    is_playlist: bool = Field(default=False, description="Hint whether URL target is a playlist")


class JobSubmitRequest(BaseModel):
    """Payload for submitting a new download job."""

    url: str = Field(..., description="Target media URL")
    format: str = Field(default="mp3_320", description="Selected audio format code")
    quality: str = Field(default="320", description="Quality selection string")
    profile: DownloadProfile | str = Field(
        default=DownloadProfile.STANDARD,
        description="Download profile (audiophile, standard, space_saver, raw_video)",
    )
    is_playlist: bool = Field(default=False, description="Whether job is a playlist")
    selected_indices: list[int] | None = Field(
        default=None, description="Selected playlist track indices"
    )
    title: str | None = Field(default=None, description="Optional custom title override")
    metadata_overrides: MetadataOverride | None = Field(
        default=None,
        description="Custom metadata and artwork overrides for media item",
    )
    track_overrides: dict[int, MetadataOverride] | None = Field(
        default=None,
        description="Optional per-track metadata overrides for playlist items",
    )

    @field_validator("track_overrides", mode="before")
    @classmethod
    def validate_track_overrides(cls, v: Any) -> dict[int, Any] | None:
        if not v:
            return None
        if isinstance(v, dict):
            res: dict[int, Any] = {}
            for k, val in v.items():
                try:
                    int_k = int(k)
                    res[int_k] = val
                except (ValueError, TypeError):
                    raise ValueError(f"Track index key '{k}' must be an integer.") from None
            return res
        return v

    @field_validator("profile", mode="before")
    @classmethod
    def validate_profile(cls, v: Any) -> DownloadProfile:
        if isinstance(v, DownloadProfile):
            return v
        if isinstance(v, str):
            val = v.strip().lower()
            try:
                return DownloadProfile(val)
            except ValueError:
                valid_names = ", ".join(p.value for p in DownloadProfile)
                msg = f"Unsupported profile '{v}'. Must be one of: {valid_names}."
                raise ValueError(msg) from None
        return DownloadProfile.STANDARD


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


def _check_file_availability(file_path_str: str | None) -> bool:
    """Verifies that a completed file exists on storage and is confined to COMPLETED_DIR."""
    if not file_path_str:
        return False
    try:
        resolved_file = Path(file_path_str).resolve()
        resolved_dir = settings.COMPLETED_DIR.resolve()
        return (
            resolved_file.is_relative_to(resolved_dir)
            and resolved_file.exists()
            and resolved_file.is_file()
        )
    except Exception:
        return False


def _format_job_response(job: dict[str, Any]) -> dict[str, Any]:
    """Formats a database job record into an API-safe response dictionary."""
    file_path_str = job.get("file_path")
    file_available = _check_file_availability(file_path_str)

    res = dict(job)
    res.pop("file_path", None)
    res["file_available"] = file_available
    res["download_url"] = f"/api/v1/downloads/{job['id']}/file" if file_available else None
    if res.get("error_message"):
        res["error_message"] = _sanitize_error_message(res["error_message"])
    return res



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
    # HIGH-03: Reject empty playlist selections
    if (
        payload.is_playlist
        and payload.selected_indices is not None
        and len(payload.selected_indices) == 0
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.INVALID_URL.value,
                "message": "At least one track must be selected for playlist downloads.",
            },
        )

    client_ip = extract_client_ip(request)
    manager = get_job_manager()

    try:
        job_id = manager.submit_job(
            url=payload.url,
            target_format=payload.format,
            quality=payload.quality,
            profile=payload.profile,
            is_playlist=payload.is_playlist,
            selected_indices=payload.selected_indices,
            title=payload.title,
            client_id=client_ip,
            metadata_overrides=payload.metadata_overrides,
            track_overrides=payload.track_overrides,
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


@router.get("/jobs")
async def list_download_jobs(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    profile: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """Returns a paginated list of download jobs with optional status, profile, and search filters."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    elif page_size > 100:
        page_size = 100

    offset = (page - 1) * page_size

    with get_db_read() as conn:
        items, total_count = list_jobs_paginated(
            conn,
            limit=page_size,
            offset=offset,
            status=status,
            profile=profile,
            search_query=q,
        )

    formatted_items = [_format_job_response(item) for item in items]
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1

    return {
        "status": "success",
        "data": {
            "items": formatted_items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_count,
                "total_pages": total_pages,
                "has_next": page * page_size < total_count,
                "has_prev": page > 1,
            },
        },
    }


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

    formatted_job = _format_job_response(job)
    formatted_job["tracks"] = tracks
    return {"status": "success", "data": formatted_job}


@router.post("/jobs/{job_id}/retry")
async def retry_job_execution(job_id: str, request: Request) -> dict[str, Any]:
    """Requeues a failed, cancelled, or completed job with its original parameters."""
    with get_db_read() as conn:
        job = get_job(conn, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": ErrorCode.JOB_NOT_FOUND.value, "message": "Job not found"},
            )
        tracks = get_tracks_for_job(conn, job_id)

    active_statuses = {
        JobStatus.QUEUED.value,
        JobStatus.FETCHING_METADATA.value,
        JobStatus.DOWNLOADING.value,
        JobStatus.CONVERTING.value,
        JobStatus.TAGGING.value,
    }
    if job.get("status") in active_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "Cannot retry a job that is currently active or in progress",
            },
        )

    client_ip = extract_client_ip(request)
    manager = get_job_manager()

    selected_indices = (
        [t["track_index"] for t in tracks]
        if (job.get("is_playlist") and tracks)
        else None
    )

    try:
        new_job = manager.submit_job(
            url=job["url"],
            target_format=job["format"],
            quality=job["quality"],
            profile=job.get("profile", DownloadProfile.STANDARD.value),
            is_playlist=bool(job.get("is_playlist", 0)),
            selected_indices=selected_indices,
            title=job.get("title"),
            client_ip=client_ip,
        )
        return {"status": "success", "data": new_job}
    except RateLimitExceededException as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": ErrorCode.RATE_LIMIT_EXCEEDED.value, "message": str(e)},
        ) from e
    except PlaylistQuotaExceededException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ErrorCode.PLAYLIST_TOO_LARGE.value, "message": str(e)},
        ) from e
    except StorageLimitExceededException as e:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail={"code": ErrorCode.STORAGE_LIMIT_EXCEEDED.value, "message": str(e)},
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
        logger.error("Failed to retry download job '%s': %s", job_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": _sanitize_error_message(str(e)),
            },
        ) from e



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

        # If no active in-memory context exists, check DB immediately
        if not context:
            with get_db_read() as conn:
                job = get_job(conn, job_id)
            if not job:
                return
            current_status = job.get("status")
            db_event = {
                "job_id": job_id,
                "status": current_status,
                "stage": current_status,
                "progress": job.get("progress", 0),
                "speed": job.get("speed", 0.0),
                "eta": job.get("eta", 0),
                "title": job.get("title"),
                "current_title": job.get("title"),
                "current_track": job.get("title"),
                "total_tracks": None,
                "completed_tracks": None,
                "track_index": None,
                "error_message": _sanitize_error_message(job.get("error_message", "")),
            }
            yield f"data: {json.dumps(db_event)}\n\n"
            if current_status in terminal_states:
                return

        try:
            while True:
                try:
                    # Wait for event with timeout to periodically poll DB status
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    if event:
                        event_data = {
                            "job_id": event.job_id,
                            "status": event.stage,
                            "stage": event.stage,
                            "progress": event.percent,
                            "speed": event.speed_bytes,
                            "eta": event.eta_seconds,
                            "current_title": event.current_track,
                            "current_track": event.current_track,
                            "total_tracks": event.total_tracks,
                            "completed_tracks": event.track_index,
                            "track_index": event.track_index,
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                        if event.stage in terminal_states:
                            break
                except TimeoutError:
                    # Check DB status periodically
                    with get_db_read() as conn:
                        job = get_job(conn, job_id)
                    if job:
                        current_status = job.get("status")
                        db_event = {
                            "job_id": job_id,
                            "status": current_status,
                            "stage": current_status,
                            "progress": job.get("progress", 0),
                            "speed": job.get("speed", 0.0),
                            "eta": job.get("eta", 0),
                            "title": job.get("title"),
                            "current_title": job.get("title"),
                            "current_track": job.get("title"),
                            "total_tracks": None,
                            "completed_tracks": None,
                            "track_index": None,
                            "error_message": _sanitize_error_message(job.get("error_message", "")),
                        }
                        yield f"data: {json.dumps(db_event)}\n\n"
                        if current_status in terminal_states:
                            break
                    else:
                        break
        except asyncio.CancelledError:
            logger.debug("SSE client disconnected for job '%s'", job_id)
            raise
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
    # Security: Verify that the resolved file path is strictly confined to settings.COMPLETED_DIR
    try:
        resolved_file = file_path.resolve()
        resolved_completed_dir = settings.COMPLETED_DIR.resolve()
        if not resolved_file.is_relative_to(resolved_completed_dir):
            logger.warning(
                "Directory traversal attempt detected in download delivery: '%s' not in '%s'",
                resolved_file,
                resolved_completed_dir,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": ErrorCode.JOB_NOT_FOUND.value, "message": "Access denied."},
            )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": ErrorCode.JOB_NOT_FOUND.value, "message": "Invalid file path."},
        ) from e

    if not resolved_file.exists() or not resolved_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": ErrorCode.JOB_NOT_FOUND.value,
                "message": "Completed file no longer exists on storage",
            },
        )

    # Determine media type & clean attachment filename
    filename = resolved_file.name
    media_type = "application/zip" if filename.endswith(".zip") else "audio/mpeg"
    if filename.endswith(".m4a"):
        media_type = "audio/mp4"
    elif filename.endswith(".opus") or filename.endswith(".webm"):
        media_type = "audio/opus"
    elif filename.endswith(".flac"):
        media_type = "audio/flac"
    elif filename.endswith(".wav"):
        media_type = "audio/wav"
    elif filename.endswith(".mp4"):
        media_type = "video/mp4"
    elif filename.endswith(".mkv"):
        media_type = "video/x-matroska"

    return FileResponse(
        path=resolved_file,
        filename=filename,
        media_type=media_type,
    )


@router.get("/profiles")
async def list_download_profiles() -> dict[str, Any]:
    """Returns available download profiles with descriptive metadata."""
    profiles = [
        {
            "id": p.value,
            "display_name": sem.display_name,
            "description": sem.description,
            "extension": sem.extension,
            "is_video": sem.is_video,
            "bitrate_kbps": sem.bitrate_kbps,
        }
        for p, sem in PROFILE_TAXONOMY.items()
    ]
    return {"status": "success", "data": profiles}
