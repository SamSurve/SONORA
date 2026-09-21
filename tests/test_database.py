"""Automated Tests for SQLite Database WAL, Schema & Repository."""

import sqlite3
from pathlib import Path

from app.db.database import create_connection, get_db, get_journal_mode
from app.db.repository import (
    add_track_to_job,
    create_job,
    get_job,
    get_tracks_for_job,
    init_db,
    update_job_status,
)


class TestDatabaseConnectionAndWAL:
    """Tests for SQLite connection setup and Write-Ahead Logging mode."""

    def test_wal_journal_mode_enabled(self, temp_db_path: Path) -> None:
        conn = create_connection(temp_db_path)
        try:
            mode = get_journal_mode(conn)
            assert mode == "wal", f"Expected WAL mode, got: {mode}"
        finally:
            conn.close()

    def test_context_manager_transaction_commit(self, temp_db_path: Path) -> None:
        with get_db(temp_db_path) as conn:
            init_db(conn)
            create_job(
                conn,
                job_id="test-tx-1",
                url="https://youtube.com/watch?v=tx1",
                target_format="mp3_320",
                quality="320",
            )

        # Reopen in new connection to verify persistence
        conn2 = create_connection(temp_db_path)
        try:
            job = get_job(conn2, "test-tx-1")
            assert job is not None
            assert job["id"] == "test-tx-1"
        finally:
            conn2.close()

    def test_context_manager_rollback_on_error(self, temp_db_path: Path) -> None:
        with get_db(temp_db_path) as conn:
            init_db(conn)

        try:
            with get_db(temp_db_path) as conn:
                create_job(
                    conn,
                    job_id="test-rollback",
                    url="https://youtube.com/watch?v=rb",
                    target_format="mp3_320",
                    quality="320",
                )
                raise RuntimeError("Simulated transaction failure")
        except RuntimeError:
            pass

        conn2 = create_connection(temp_db_path)
        try:
            job = get_job(conn2, "test-rollback")
            assert job is None, "Job should have been rolled back"
        finally:
            conn2.close()


class TestRepositoryOperations:
    """Tests for job and track schema CRUD operations."""

    def test_idempotent_schema_creation(self, test_db_conn: sqlite3.Connection) -> None:
        # Running init_db multiple times must not fail
        init_db(test_db_conn)
        init_db(test_db_conn)

    def test_create_and_retrieve_job(self, test_db_conn: sqlite3.Connection) -> None:
        job = create_job(
            test_db_conn,
            job_id="uuid-test-1",
            url="https://music.youtube.com/watch?v=123",
            target_format="opus",
            quality="original",
            title="Solaris Chill",
        )
        assert job["id"] == "uuid-test-1"
        assert job["status"] == "queued"
        assert job["progress"] == 0
        assert job["title"] == "Solaris Chill"

        fetched = get_job(test_db_conn, "uuid-test-1")
        assert fetched is not None
        assert fetched["url"] == "https://music.youtube.com/watch?v=123"

    def test_update_job_status_and_completion(self, test_db_conn: sqlite3.Connection) -> None:
        create_job(
            test_db_conn,
            job_id="uuid-test-update",
            url="https://music.youtube.com/watch?v=update",
            target_format="mp3_320",
            quality="320",
        )

        # Progress update
        success = update_job_status(
            test_db_conn,
            job_id="uuid-test-update",
            status="downloading",
            progress=55,
            speed=3145728.0,
            eta=12,
        )
        assert success is True

        job = get_job(test_db_conn, "uuid-test-update")
        assert job["status"] == "downloading"
        assert job["progress"] == 55
        assert job["speed"] == 3145728.0
        assert job["eta"] == 12

        # Completion update
        update_job_status(
            test_db_conn,
            job_id="uuid-test-update",
            status="completed",
            progress=100,
            file_path="data/completed/uuid-test-update/track.mp3",
            file_size=9450000,
        )

        completed_job = get_job(test_db_conn, "uuid-test-update")
        assert completed_job["status"] == "completed"
        assert completed_job["completed_at"] is not None

    def test_tracks_cascade_deletion(self, test_db_conn: sqlite3.Connection) -> None:
        job_id = "playlist-uuid-1"
        create_job(
            test_db_conn,
            job_id=job_id,
            url="https://music.youtube.com/playlist?list=PL123",
            target_format="mp3_320",
            quality="320",
        )

        add_track_to_job(test_db_conn, job_id, 1, "Track 1", duration=180)
        add_track_to_job(test_db_conn, job_id, 2, "Track 2", duration=210)

        tracks = get_tracks_for_job(test_db_conn, job_id)
        assert len(tracks) == 2
        assert tracks[0]["track_index"] == 1
        assert tracks[1]["track_index"] == 2

        # Cascade delete when parent job is deleted
        test_db_conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        orphaned_tracks = get_tracks_for_job(test_db_conn, job_id)
        assert len(orphaned_tracks) == 0, "Tracks should be cascaded on parent job deletion"
