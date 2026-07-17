"""Deterministic Day 06 manual-review sample and year-coverage report."""

from __future__ import annotations

import argparse
import csv
import random
import sqlite3
from pathlib import Path


def _coverage_rows(connection: sqlite3.Connection, tickers: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        years = [
            row[0]
            for row in connection.execute(
                """SELECT DISTINCT year FROM financial_statements
                   WHERE company_id = ? AND statement_type = 'profit_and_loss'
                     AND year IS NOT NULL ORDER BY year""",
                (ticker,),
            )
        ]
        rows.append(
            {
                "company_id": ticker,
                "first_year": min(years) if years else "",
                "last_year": max(years) if years else "",
                "years_covered": len(years),
                "less_than_5_years": len(years) < 5,
            }
        )
    return rows


def _write_rows(rows: list[dict[str, object]], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["company_id"])
        writer.writeheader()
        writer.writerows(rows)
    return path.resolve()


def run_review(database: str | Path, output: str | Path, seed: int = 100) -> Path:
    connection = sqlite3.connect(database)
    try:
        tickers = [row[0] for row in connection.execute("SELECT id FROM companies ORDER BY id")]
        sample = sorted(random.Random(seed).sample(tickers, min(5, len(tickers))))
        rows = _coverage_rows(connection, sample)
    finally:
        connection.close()
    return _write_rows(rows, output)


def run_year_coverage(database: str | Path, output: str | Path) -> Path:
    connection = sqlite3.connect(database)
    try:
        tickers = [row[0] for row in connection.execute("SELECT id FROM companies ORDER BY id")]
        rows = _coverage_rows(connection, tickers)
    finally:
        connection.close()
    return _write_rows(rows, output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review five reproducibly sampled companies")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--output", default="output/manual_review.csv")
    parser.add_argument("--coverage-output", default="output/year_coverage.csv")
    args = parser.parse_args()
    print(run_review(args.database, args.output))
    print(run_year_coverage(args.database, args.coverage_output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
