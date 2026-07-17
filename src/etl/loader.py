"""Load all 12 source workbooks into the 10-table SQLite database."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nifty100_etl.loader import iter_loaded_sources

LOAD_ORDER = (
    "companies",
    "documents",
    "analysis",
    "pros_and_cons",
    "financial_statements",
    "financial_ratios",
    "stock_prices",
    "market_cap",
    "sectors",
    "peer_groups",
)


@dataclass(frozen=True)
class AuditRow:
    source_file: str
    table_name: str
    source_rows: int
    loaded_rows: int
    rejected_rows: int
    rejection_reason: str


def connect_database(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path))
    connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise RuntimeError("SQLite foreign-key enforcement could not be enabled")
    return connection


def create_schema(connection: sqlite3.Connection, schema_path: str | Path) -> None:
    connection.executescript(Path(schema_path).read_text(encoding="utf-8"))


def _sqlite_value(value: Any) -> Any:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return int(value)
    return value


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]


def insert_frame(connection: sqlite3.Connection, table: str, frame: pd.DataFrame) -> int:
    allowed = _table_columns(connection, table)
    columns = [column for column in allowed if column in frame.columns]
    if not columns:
        raise ValueError(f"No compatible columns found for table {table}")
    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    sql = f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})'
    records = [
        tuple(_sqlite_value(value) for value in row)
        for row in frame[columns].itertuples(index=False, name=None)
    ]
    connection.executemany(sql, records)
    return len(records)


def _reject_orphans(frame: pd.DataFrame, company_ids: set[str]) -> tuple[pd.DataFrame, int]:
    if "company_id" not in frame:
        return frame, 0
    valid = frame["company_id"].notna() & frame["company_id"].isin(company_ids)
    return frame.loc[valid].copy(), int((~valid).sum())


def write_load_audit(rows: Iterable[AuditRow], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(AuditRow.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(row.__dict__ for row in rows)
    return path.resolve()


def foreign_key_violations(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return list(connection.execute("PRAGMA foreign_key_check"))


def load_database(
    source_dir: str | Path,
    database_path: str | Path,
    schema_path: str | Path,
    audit_path: str | Path,
) -> list[AuditRow]:
    sources = list(iter_loaded_sources(source_dir))
    sources.sort(key=lambda item: LOAD_ORDER.index(item[0].table))
    database = Path(database_path)
    if database.exists():
        database.unlink()
    connection = connect_database(database)
    audit: list[AuditRow] = []
    try:
        create_schema(connection, schema_path)
        company_ids: set[str] = set()
        with connection:
            for source, frame in sources:
                clean = frame.drop(columns=["source_file"], errors="ignore")
                rejected = 0
                reason = ""
                if source.table == "companies":
                    company_ids = set(clean["id"].dropna().astype(str))
                else:
                    clean, rejected = _reject_orphans(clean, company_ids)
                    if rejected:
                        reason = "company_id absent from companies.id"
                loaded = insert_frame(connection, source.table, clean)
                audit.append(
                    AuditRow(source.path.name, source.table, len(frame), loaded, rejected, reason)
                )
        violations = foreign_key_violations(connection)
        if violations:
            raise RuntimeError(f"Foreign-key validation failed: {violations[:5]}")
    finally:
        connection.close()
    write_load_audit(audit, audit_path)
    return audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build nifty100.db from all 12 workbooks")
    parser.add_argument("--source-dir", default=".")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--schema", default="db/schema.sql")
    parser.add_argument("--audit", default="output/load_audit.csv")
    args = parser.parse_args(argv)
    audit = load_database(args.source_dir, args.database, args.schema, args.audit)
    print(f"Loaded {sum(row.loaded_rows for row in audit):,} rows from {len(audit)} files")
    print(f"Rejected {sum(row.rejected_rows for row in audit):,} rows with invalid FKs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
