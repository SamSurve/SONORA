"""Tests for SQLite Concurrency under WAL Mode with get_db_write (BEGIN IMMEDIATE).

Verifies that concurrent worker threads reading and writing to SQLite under WAL mode
do not deadlock or raise 'sqlite3.OperationalError: database is locked'.
"""

import threading
import time
from pathlib import Path

from app.db.database import create_connection, get_db_read, get_db_write
from app.db.repository import create_job, get_job, update_job_status


def test_concurrent_10_workers_read_and_write(tmp_path: Path) -> None:
    """Spawns 12 concurrent worker threads performing rapid read-then-write updates.

    Asserts that all 12 worker threads complete successfully without any database locks.
    """
    db_file = tmp_path / "test_concurrency.db"
    conn = create_connection(db_file)

    # Populate 12 initial jobs in DB
    num_workers = 12
    with get_db_write(db_file) as w_conn:
        for i in range(num_workers):
            create_job(
                conn=w_conn,
                job_id=f"concurrent_job_{i}",
                url=f"https://music.youtube.com/watch?v=track_{i}",
                target_format="mp3",
                quality="320",
                title=f"Concurrent Track {i}",
            )

    conn.close()

    errors: list[Exception] = []
    successes: list[str] = []
    lock = threading.Lock()

    def worker_task(worker_index: int) -> None:
        job_id = f"concurrent_job_{worker_index}"
        try:
            # 1. Read job info using autocommit get_db_read
            with get_db_read(db_file) as r_conn:
                job_data = get_job(r_conn, job_id)
                assert job_data is not None

            # Simulate short processing delay
            time.sleep(0.01)

            # 2. Perform status and progress update using get_db_write (BEGIN IMMEDIATE)
            with get_db_write(db_file) as w_conn:
                updated = update_job_status(
                    w_conn,
                    job_id=job_id,
                    status="downloading",
                    progress=worker_index * 8,
                    speed=1024.0 * worker_index,
                )
                assert updated is True

            time.sleep(0.01)

            # 3. Finalize status to completed
            with get_db_write(db_file) as w_conn:
                update_job_status(
                    w_conn,
                    job_id=job_id,
                    status="completed",
                    progress=100,
                )

            with lock:
                successes.append(job_id)

        except Exception as e:
            with lock:
                errors.append(e)

    threads = [
        threading.Thread(target=worker_task, args=(i,), name=f"WorkerThread-{i}")
        for i in range(num_workers)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(errors) == 0, f"Encountered database concurrency errors: {errors}"
    assert len(successes) == num_workers


def test_fresh_database_auto_initialization(tmp_path: Path) -> None:
    """Verifies that a completely fresh database file auto-initializes table DDL on connection."""
    fresh_db_file = tmp_path / "fresh_auto_init.db"
    assert not fresh_db_file.exists()

    with get_db_write(fresh_db_file) as conn:
        job = create_job(
            conn=conn,
            job_id="auto_init_job",
            url="https://music.youtube.com/watch?v=auto_init",
            target_format="mp3",
            quality="320",
        )
        assert job["id"] == "auto_init_job"

    with get_db_read(fresh_db_file) as conn:
        retrieved = get_job(conn, "auto_init_job")
        assert retrieved is not None
        assert retrieved["status"] == "queued"
