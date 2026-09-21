"""Auralis Database Schema DDL & Repository Functions.

Defines the jobs and tracks tables, creates performance indexes, and provides
core CRUD operations for Phase 1 and subsequent phases.
"""

import sqlite3
from datetime import UTC, datetime
from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    format TEXT NOT NULL,
    quality TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    speed REAL NOT NULL DEFAULT 0.0,
    eta INTEGER NOT NULL DEFAULT 0,
    file_path TEXT,
    file_size INTEGER,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    track_index INTEGER NOT NULL,
    track_title TEXT NOT NULL,
    duration INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_expires_at ON jobs(expires_at);
CREATE INDEX IF NOT EXISTS idx_tracks_job_id ON tracks(job_id);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Idempotently executes table creation and index setup."""
    conn.executescript(SCHEMA_SQL)


def create_job(
    conn: sqlite3.Connection,
    job_id: str,
    url: str,
    target_format: str,
    quality: str,
    title: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Inserts a new job record."""
    now = datetime.now(UTC).isoformat()
    expires_str = expires_at.isoformat() if expires_at else None

    query = """
    INSERT INTO jobs (id, url, title, format, quality, status, progress, created_at, expires_at)
    VALUES (?, ?, ?, ?, ?, 'queued', 0, ?, ?)
    """
    conn.execute(query, (job_id, url, title, target_format, quality, now, expires_str))
    return get_job(conn, job_id)  # type: ignore[return-value]


def get_job(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    """Retrieves a single job by its UUID."""
    cursor = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def update_job_status(
    conn: sqlite3.Connection,
    job_id: str,
    status: str,
    progress: int | None = None,
    speed: float | None = None,
    eta: int | None = None,
    file_path: str | None = None,
    file_size: int | None = None,
    error_message: str | None = None,
) -> bool:
    """Updates job progress and status attributes."""
    fields = ["status = ?"]
    params: list[Any] = [status]

    if progress is not None:
        fields.append("progress = ?")
        params.append(progress)
    if speed is not None:
        fields.append("speed = ?")
        params.append(speed)
    if eta is not None:
        fields.append("eta = ?")
        params.append(eta)
    if file_path is not None:
        fields.append("file_path = ?")
        params.append(file_path)
    if file_size is not None:
        fields.append("file_size = ?")
        params.append(file_size)
    if error_message is not None:
        fields.append("error_message = ?")
        params.append(error_message)

    if status == "completed":
        fields.append("completed_at = ?")
        params.append(datetime.now(UTC).isoformat())

    params.append(job_id)
    query = f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?"  # noqa: S608
    cursor = conn.execute(query, tuple(params))
    return cursor.rowcount > 0


def add_track_to_job(
    conn: sqlite3.Connection,
    job_id: str,
    track_index: int,
    track_title: str,
    duration: int = 0,
) -> int:
    """Inserts an individual track entry linked to a playlist job."""
    query = """
    INSERT INTO tracks (job_id, track_index, track_title, duration, status)
    VALUES (?, ?, ?, ?, 'pending')
    """
    cursor = conn.execute(query, (job_id, track_index, track_title, duration))
    return cursor.lastrowid or 0


def get_tracks_for_job(conn: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    """Retrieves all tracks for a job ordered by track_index."""
    cursor = conn.execute(
        "SELECT * FROM tracks WHERE job_id = ? ORDER BY track_index ASC", (job_id,)
    )
    return [dict(row) for row in cursor.fetchall()]
