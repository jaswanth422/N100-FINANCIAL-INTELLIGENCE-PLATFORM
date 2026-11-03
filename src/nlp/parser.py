"""Parse period/value percentages from the analyst text workbook.

The source workbook stores one human-readable metric per cell (for example,
``10 Years: 21%``).  This module deliberately uses the Day 29 regular
expression for extraction and writes non-matching text plus Ratio Engine CAGR
divergences to a review file.
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

METRIC_FIELDS = (
    "compounded_sales_growth",
    "compounded_profit_growth",
    "stock_price_cagr",
    "roe",
)
METRIC_PATTERN = re.compile(r"(\d+)\s*Years?:?\s*([\d.]+)%")
CAGR_DIVERGENCE_TOLERANCE_PCT_POINTS = 5.0

_CAGR_RATIO_PREFIX = {
    "compounded_sales_growth": "revenue_cagr",
    "compounded_profit_growth": "pat_cagr",
}
_CAGR_PERIODS = (3, 5, 10)
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(frozen=True)
class ParsedMetric:
    """One period/value pair extracted from an analysis text field."""

    company_id: str
    metric_type: str
    period_years: int
    value_pct: float


@dataclass(frozen=True)
class ParseFailure:
    """A regex miss or computed-CAGR divergence requiring review."""

    company_id: str
    metric_type: str
    raw_text: str
    failure_type: str
    period_years: int | None = None
    parsed_value_pct: float | None = None
    computed_value_pct: float | None = None
    divergence_pct_points: float | None = None


@dataclass(frozen=True)
class ParserStats:
    """Summary counts returned by :func:`generate_parsed_analysis`."""

    source_rows: int
    parsed_rows: int
    regex_failures: int
    cagr_divergences: int


def parse_metric_text(value: object) -> list[tuple[int, float]]:
    """Return every ``(period_years, value_pct)`` match in *value*.

    The regex intentionally does not accept a sign because the prescribed Day
    29 pattern uses ``[\d.]+``.  Negative percentages are therefore retained in
    the review file rather than silently parsed with different semantics.
    """
    if value is None:
        return []
    text = str(value)
    matches: list[tuple[int, float]] = []
    for match in METRIC_PATTERN.finditer(text):
        try:
            matches.append((int(match.group(1)), float(match.group(2))))
        except ValueError:
            # The regex permits inputs such as ``1..2``.  Treat malformed
            # numeric text as a non-match so it is surfaced for review.
            return []
    return matches


def _column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha())
    result = 0
    for character in letters.upper():
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(node.text or "" for node in item.findall(f".//{{{_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    ]


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    first_sheet = workbook.find(f".//{{{_MAIN_NS}}}sheet")
    if first_sheet is None:
        raise ValueError("Workbook contains no worksheets")
    relationship_id = first_sheet.attrib[f"{{{_REL_NS}}}id"]

    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relationship in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship"):
        if relationship.attrib.get("Id") == relationship_id:
            target = relationship.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise ValueError(f"Worksheet relationship not found: {relationship_id}")


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{{{_MAIN_NS}}}t"))

    value_node = cell.find(f"{{{_MAIN_NS}}}v")
    if value_node is None or value_node.text is None:
        return None
    value = value_node.text
    if cell_type == "s":
        return shared_strings[int(value)]
    if cell_type in {"str", "e"}:
        return value
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def read_analysis_rows(workbook_path: str | Path) -> list[dict[str, Any]]:
    """Read the first XLSX worksheet using the standard library.

    The project declares ``openpyxl`` for its general ETL pipeline, but the NLP
    parser only needs cell values.  Reading the small Open XML package directly
    keeps this command deterministic and read-only in minimal environments.
    """
    path = Path(workbook_path)
    with zipfile.ZipFile(path) as archive:
        shared_strings = _shared_strings(archive)
        sheet = ElementTree.fromstring(archive.read(_first_sheet_path(archive)))

    raw_rows: list[list[Any]] = []
    for row in sheet.findall(f".//{{{_MAIN_NS}}}sheetData/{{{_MAIN_NS}}}row"):
        values: dict[int, Any] = {}
        for cell in row.findall(f"{{{_MAIN_NS}}}c"):
            values[_column_index(cell.attrib["r"])] = _cell_value(cell, shared_strings)
        if values:
            width = max(values) + 1
            raw_rows.append([values.get(index) for index in range(width)])

    header_index = next(
        (
            index
            for index, row in enumerate(raw_rows)
            if "company_id" in {str(value).strip() for value in row if value is not None}
            and set(METRIC_FIELDS).issubset(
                {str(value).strip() for value in row if value is not None}
            )
        ),
        None,
    )
    if header_index is None:
        raise ValueError("Could not find analysis header row")

    headers = [str(value).strip() if value is not None else "" for value in raw_rows[header_index]]
    records: list[dict[str, Any]] = []
    for row in raw_rows[header_index + 1 :]:
        record = {
            header: row[index] if index < len(row) else None
            for index, header in enumerate(headers)
            if header
        }
        if any(value is not None and str(value).strip() for value in record.values()):
            records.append(record)
    return records


def load_ratio_engine_cagrs(
    database_path: str | Path,
) -> dict[tuple[str, str, int], float]:
    """Load latest 3/5/10-year revenue and PAT CAGR values from SQLite."""
    result: dict[tuple[str, str, int], float] = {}
    latest_rows: dict[str, sqlite3.Row] = {}
    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT *
            FROM financial_ratios
            WHERE year IS NOT NULL
            ORDER BY company_id, year, id
            """
        )
        for row in rows:
            latest_rows[str(row["company_id"])] = row
    finally:
        connection.close()

    for company_id, row in latest_rows.items():
        for metric_type, prefix in _CAGR_RATIO_PREFIX.items():
            for period in _CAGR_PERIODS:
                value = row[f"{prefix}_{period}yr"]
                if value is not None:
                    result[(company_id, metric_type, period)] = float(value)
    return result


def parse_analysis_records(
    records: Iterable[dict[str, Any]],
    *,
    ratio_cagrs: dict[tuple[str, str, int], float] | None = None,
    divergence_tolerance: float = CAGR_DIVERGENCE_TOLERANCE_PCT_POINTS,
) -> tuple[list[ParsedMetric], list[ParseFailure]]:
    """Parse workbook records and append direct CAGR cross-check failures."""
    parsed: list[ParsedMetric] = []
    failures: list[ParseFailure] = []
    references = ratio_cagrs or {}

    for record in records:
        raw_company_id = record.get("company_id")
        company_id = "" if raw_company_id is None else str(raw_company_id).strip().upper()
        for metric_type in METRIC_FIELDS:
            raw_value = record.get(metric_type)
            if raw_value is None or not str(raw_value).strip():
                continue
            raw_text = str(raw_value)
            matches = parse_metric_text(raw_text)
            if not matches:
                failures.append(
                    ParseFailure(
                        company_id=company_id,
                        metric_type=metric_type,
                        raw_text=raw_text,
                        failure_type="regex_no_match",
                    )
                )
                continue

            for period_years, value_pct in matches:
                metric = ParsedMetric(company_id, metric_type, period_years, value_pct)
                parsed.append(metric)
                computed = references.get((company_id, metric_type, period_years))
                if computed is None:
                    continue
                divergence = abs(value_pct - computed)
                if divergence > divergence_tolerance:
                    failures.append(
                        ParseFailure(
                            company_id=company_id,
                            metric_type=metric_type,
                            raw_text=raw_text,
                            failure_type="cagr_divergence",
                            period_years=period_years,
                            parsed_value_pct=value_pct,
                            computed_value_pct=computed,
                            divergence_pct_points=divergence,
                        )
                    )
    return parsed, failures


def _write_csv(rows: Iterable[object], output_path: str | Path, fieldnames: Sequence[str]) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    return path.resolve()


def generate_parsed_analysis(
    workbook_path: str | Path = "analysis.xlsx",
    database_path: str | Path = "nifty100.db",
    output_path: str | Path = "output/analysis_parsed.csv",
    failure_path: str | Path = "output/parse_failures.csv",
) -> ParserStats:
    """Parse ``analysis.xlsx``, cross-check CAGRs, and write both CSV files."""
    records = read_analysis_rows(workbook_path)
    references = load_ratio_engine_cagrs(database_path)
    parsed, failures = parse_analysis_records(records, ratio_cagrs=references)
    _write_csv(parsed, output_path, list(ParsedMetric.__dataclass_fields__))
    _write_csv(failures, failure_path, list(ParseFailure.__dataclass_fields__))
    return ParserStats(
        source_rows=len(records),
        parsed_rows=len(parsed),
        regex_failures=sum(failure.failure_type == "regex_no_match" for failure in failures),
        cagr_divergences=sum(
            failure.failure_type == "cagr_divergence" for failure in failures
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse analysis workbook text metrics")
    parser.add_argument("--workbook", default="analysis.xlsx")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--output", default="output/analysis_parsed.csv")
    parser.add_argument("--failures", default="output/parse_failures.csv")
    args = parser.parse_args(argv)
    stats = generate_parsed_analysis(
        args.workbook,
        args.database,
        args.output,
        args.failures,
    )
    print(
        f"Parsed {stats.parsed_rows} values from {stats.source_rows} rows; "
        f"regex failures={stats.regex_failures}, "
        f"CAGR divergences={stats.cagr_divergences}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
