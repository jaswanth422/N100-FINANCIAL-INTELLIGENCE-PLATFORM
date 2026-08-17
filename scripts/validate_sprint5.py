"""Validate Sprint 5 output coverage and PDF structural quality."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validate(root: Path) -> int:
    tearsheets = sorted((root / "reports/tearsheets").glob("*_tearsheet.pdf"))
    sizes = [path.stat().st_size for path in tearsheets]
    bad_page_counts = []
    blank_pages = []
    for path in tearsheets:
        reader = PdfReader(path)
        if len(reader.pages) != 2:
            bad_page_counts.append(path.name)
        for number, page in enumerate(reader.pages, start=1):
            if not (page.extract_text() or "").strip():
                blank_pages.append(f"{path.name}:{number}")

    sector_paths = sorted((root / "reports/sector").glob("*_report.pdf"))
    sector_pages = {path.name: len(PdfReader(path).pages) for path in sector_paths}
    portfolio = root / "reports/portfolio/portfolio_summary.pdf"
    portfolio_reader = PdfReader(portfolio)
    portfolio_blank = sum(
        not (page.extract_text() or "").strip() for page in portfolio_reader.pages
    )

    print(
        "tearsheets",
        len(tearsheets),
        "min_bytes",
        min(sizes, default=0),
        "bad_page_counts",
        bad_page_counts,
        "blank_pages",
        blank_pages,
    )
    print("sectors", len(sector_paths), sector_pages)
    print(
        "portfolio",
        portfolio.stat().st_size,
        "pages",
        len(portfolio_reader.pages),
        "blank_pages",
        portfolio_blank,
    )

    csv_names = [
        "cashflow_intelligence.csv",
        "distress_alerts.csv",
        "capital_allocation.csv",
        "pattern_changes.csv",
        "capital_allocation_distribution.csv",
        "pros_cons_generated.csv",
        "analysis_parsed.csv",
        "skipped_tearsheets.csv",
    ]
    results = {}
    for name in csv_names:
        rows = csv_rows(root / "output" / name)
        results[name] = rows
        print(name, len(rows), list(rows[0]) if rows else [])

    coverage: dict[str, set[str]] = defaultdict(set)
    for row in results["pros_cons_generated.csv"]:
        coverage[row["company_id"]].add(row["type"])
    missing_signal_types = sum(
        signal_types != {"pro", "con"} for signal_types in coverage.values()
    )
    print("pros_cons_coverage", len(coverage), "incomplete", missing_signal_types)
    print("distribution", results["capital_allocation_distribution.csv"])

    failures = [
        len(tearsheets) != 92,
        not sizes or min(sizes) < 30_000,
        bool(bad_page_counts),
        bool(blank_pages),
        len(sector_paths) != 11,
        len(portfolio_reader.pages) != 92,
        portfolio_blank != 0,
        len(results["cashflow_intelligence.csv"]) != 92,
        len(coverage) != 92,
        missing_signal_types != 0,
    ]
    return 1 if any(failures) else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    return validate(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
