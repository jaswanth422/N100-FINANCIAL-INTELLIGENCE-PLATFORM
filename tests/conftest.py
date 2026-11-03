"""Session-scoped fixture: build nifty100.db (schema + ratios) on a fresh clone.

Many tests under ``tests/`` assume ``nifty100.db`` exists at the repo root. On a
fresh clone it does not, so the suite would fail with sqlite "no such table"
errors before the first assertion. This fixture bridges that gap: it builds the
database once per pytest session using the same code paths as ``make db`` and
``make ratios``.

Running the full ETL on every test session is intentional — it keeps the test
database in lock-step with the current ETL code (so schema or sanitizer changes
can't silently stale against a cached DB).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "nifty100.db"
DEFAULT_SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"
DEFAULT_AUDIT_PATH = REPO_ROOT / "output" / "load_audit.csv"
REQUIRED_WORKBOOKS = (
    REPO_ROOT / "companies.xlsx",
    REPO_ROOT / "profitandloss.xlsx",
    REPO_ROOT / "balancesheet.xlsx",
    REPO_ROOT / "cashflow.xlsx",
)


def _sources_available() -> bool:
    return all(path.is_file() for path in REQUIRED_WORKBOOKS)


def _db_is_populated(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        connection = sqlite3.connect(path)
    except sqlite3.Error:
        return False
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('companies', 'financial_statements', 'financial_ratios')"
        ).fetchall()
        return len(rows) == 3
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def _build_database() -> None:
    # Imported lazily so tests that don't need the DB don't pay the import cost.
    from etl.loader import load_database  # noqa: PLC0415

    DEFAULT_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    load_database(
        source_dir=REPO_ROOT,
        database_path=DEFAULT_DB_PATH,
        schema_path=DEFAULT_SCHEMA_PATH,
        audit_path=DEFAULT_AUDIT_PATH,
    )


def _populate_ratios() -> None:
    from analytics.populate_ratios import populate_financial_ratios  # noqa: PLC0415

    connection = sqlite3.connect(DEFAULT_DB_PATH)
    try:
        with connection:
            populate_financial_ratios(connection)
    finally:
        connection.close()


@pytest.fixture(scope="session")
def nifty100_db() -> Path:
    """Return the path to a populated ``nifty100.db``, building it if missing.

    Skips the whole session when source workbooks aren't available (lightweight
    CI jobs that only run unit tests on code without data can still execute).
    """
    if _db_is_populated(DEFAULT_DB_PATH):
        return DEFAULT_DB_PATH

    if not _sources_available():
        pytest.skip(
            "Source workbooks missing from repo root; cannot build nifty100.db. "
            "Expected: " + ", ".join(path.name for path in REQUIRED_WORKBOOKS)
        )

    _build_database()
    _populate_ratios()

    if not _db_is_populated(DEFAULT_DB_PATH):
        raise RuntimeError("nifty100.db build completed but required tables are missing")

    return DEFAULT_DB_PATH


@pytest.fixture(autouse=True, scope="session")
def _ensure_nifty100_db(nifty100_db: Path) -> Path:
    """Autouse wrapper so tests that assume nifty100.db exists see it built."""
    return nifty100_db
