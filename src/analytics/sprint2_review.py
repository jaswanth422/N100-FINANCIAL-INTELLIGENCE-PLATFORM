"""Generate Day 14 screener-preview and team-demo extracts."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


def _write_query(connection: sqlite3.Connection, query: str, output_path: Path) -> int:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(query).fetchall()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return len(rows)


def generate_review_outputs(
    connection: sqlite3.Connection,
    output_dir: str | Path,
) -> tuple[int, int]:
    root = Path(output_dir)
    ranked = """
        WITH ranked AS (
            SELECT r.*, ROW_NUMBER() OVER (
                PARTITION BY r.company_id ORDER BY r.year DESC, r.id DESC
            ) AS rank_no
            FROM financial_ratios r WHERE r.year IS NOT NULL
        )
    """
    screener_count = _write_query(
        connection,
        ranked
        + """
        SELECT r.company_id,
               REPLACE(REPLACE(c.company_name, char(10), ' '), char(13), ' ') AS company_name,
               r.year,
               ROUND(r.return_on_equity_pct, 2) AS roe_pct,
               ROUND(r.debt_to_equity, 2) AS debt_to_equity,
               ROUND(r.composite_quality_score, 2) AS composite_quality_score,
               CASE
                   WHEN ABS(r.return_on_equity_pct) > 200 THEN 'Review: documented source anomaly'
                   ELSE 'Passes mechanical filter; analyst review required'
               END AS review_note
        FROM ranked r JOIN companies c ON c.id = r.company_id
        WHERE r.rank_no = 1 AND r.return_on_equity_pct > 15 AND r.debt_to_equity < 1
        ORDER BY r.return_on_equity_pct DESC
        """,
        root / "screener_preview.csv",
    )
    demo_count = _write_query(
        connection,
        ranked
        + """
        SELECT r.*
        FROM ranked r
        WHERE r.rank_no = 1
          AND r.company_id IN ('RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ITC')
        ORDER BY r.company_id
        """,
        root / "financial_ratios_demo.csv",
    )
    return screener_count, demo_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Sprint 2 review outputs")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()
    connection = sqlite3.connect(args.database)
    try:
        screener_count, demo_count = generate_review_outputs(connection, args.output_dir)
    finally:
        connection.close()
    print(f"Screener rows={screener_count}; demo companies={demo_count}")


if __name__ == "__main__":
    main()
