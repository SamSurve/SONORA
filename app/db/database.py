"""Auralis SQLite Database Connection & WAL Configuration.

Configures high-concurrency Write-Ahead-Logging (WAL), foreign key constraints,
and thread-safe connection handling.
"""

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from app.core.config import settings
from app.db import repository

# Thread-safe registry of database paths whose schemas have been initialized
_INITIALIZED_DATABASES: set[str] = set()
_init_lock = threading.Lock()


def create_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Creates a configured SQLite connection with WAL mode and foreign keys enabled.

    Auto-initializes table schema and indexes on clean database targets strictly once
    per database path.
    """
    target_path = Path(db_path or settings.DB_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        timeout=10.0,
        check_same_thread=False,
        isolation_level=None,  # Autocommit mode; explicit transactions managed in context
    )

    conn.row_factory = sqlite3.Row

    # Performance & Concurrency PRAGMAs
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")

    # Idempotently ensure database schema exists strictly on first access
    canonical_path = str(target_path.resolve())
    if canonical_path not in _INITIALIZED_DATABASES:
        with _init_lock:
            if canonical_path not in _INITIALIZED_DATABASES:
                repository.init_db(conn)
                _INITIALIZED_DATABASES.add(canonical_path)

    return conn


def ensure_db_initialized(db_path: Path | str | None = None) -> None:
    """Explicitly initializes the database schema upfront during application boot."""
    target_path = Path(db_path or settings.DB_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path = str(target_path.resolve())
    with _init_lock:
        if canonical_path not in _INITIALIZED_DATABASES:
            conn = create_connection(target_path)
            conn.close()


def reset_db_initialization_cache() -> None:
    """Clears the initialized database tracking cache (used for test isolation)."""
    with _init_lock:
        _INITIALIZED_DATABASES.clear()


@contextmanager
def get_db_read(
    db_path: Path | str | None = None,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for read-only database operations under autocommit mode.

    Does not acquire write locks or write reservations, allowing non-blocking concurrent reads.
    """
    conn = create_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_write(
    db_path: Path | str | None = None,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for mutation/write operations acquiring write reservations.

    Executes 'BEGIN IMMEDIATE;' to acquire a reserved write lock at transaction start,
    preventing read-to-write lock upgrade deadlocks under concurrent execution.
    """
    conn = create_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        yield conn
        if conn.in_transaction:
            conn.execute("COMMIT;")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()


# Backward compatibility alias: default get_db context manager executes write transactions
get_db = get_db_write


def get_journal_mode(conn: sqlite3.Connection) -> str:
    """Queries and returns the active SQLite journal mode."""
    cursor = conn.execute("PRAGMA journal_mode;")
    row = cursor.fetchone()
    return str(row[0]).lower() if row else "unknown"
