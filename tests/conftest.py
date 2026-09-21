"""Pytest Configuration and Shared Test Fixtures."""

import sqlite3
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from app.db.database import create_connection
from app.db.repository import init_db


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Provides an isolated temporary database file path and cleans up afterwards."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_auralis.db"
        yield db_file


@pytest.fixture
def test_db_conn(temp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Provides an initialized test database connection with WAL mode and schema."""
    conn = create_connection(temp_db_path)
    init_db(conn)
    yield conn
    conn.close()
