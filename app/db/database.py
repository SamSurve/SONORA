"""Auralis SQLite Database Connection & WAL Configuration.

Configures high-concurrency Write-Ahead-Logging (WAL), foreign key constraints,
and thread-safe connection handling.
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from app.core.config import settings


def create_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Creates a configured SQLite connection with WAL mode and foreign keys enabled."""
    target_path = db_path or settings.DB_PATH
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

    return conn


@contextmanager
def get_db(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for transactional database operations.

    Yields:
        sqlite3.Connection: Configured database connection.
    """
    conn = create_connection(db_path)
    try:
        conn.execute("BEGIN;")
        yield conn
        if conn.in_transaction:
            conn.execute("COMMIT;")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK;")
        raise
    finally:
        conn.close()


def get_journal_mode(conn: sqlite3.Connection) -> str:
    """Queries and returns the active SQLite journal mode."""
    cursor = conn.execute("PRAGMA journal_mode;")
    row = cursor.fetchone()
    return str(row[0]).lower() if row else "unknown"
