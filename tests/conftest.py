"""Pytest Configuration and Shared Test Fixtures."""

import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest

from app.core.config import settings
from app.db.database import create_connection
from app.db.repository import init_db
from app.services.job_manager import job_manager


@pytest.fixture(autouse=True)
def isolate_test_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    """Ensures every test runs in an isolated scratchpad with no production DB/storage mutation."""
    test_db = tmp_path / "test_isolated.db"
    test_temp = tmp_path / "temp"
    test_completed = tmp_path / "completed"
    test_temp.mkdir(parents=True, exist_ok=True)
    test_completed.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "DB_PATH", test_db)
    monkeypatch.setattr(settings, "TEMP_DIR", test_temp)
    monkeypatch.setattr(settings, "COMPLETED_DIR", test_completed)

    yield

    with job_manager._registry_lock:
        active_contexts = list(job_manager._active_jobs.values())
        job_manager._active_jobs.clear()
    for ctx in active_contexts:
        ctx.cancel_event.set()


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Provides an isolated temporary database file path."""
    return tmp_path / "test_auralis.db"


@pytest.fixture
def test_db_conn(temp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Provides an initialized test database connection with WAL mode and schema."""
    conn = create_connection(temp_db_path)
    init_db(conn)
    yield conn
    conn.close()
