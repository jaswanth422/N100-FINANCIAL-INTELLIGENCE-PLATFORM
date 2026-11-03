"""Excel discovery and loading primitives for the NIFTY 100 sources."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .normalize import normalize_ticker, normalize_year

LOGGER = logging.getLogger(__name__)

OPM_PERCENTAGE_MIN = -100.0
OPM_PERCENTAGE_MAX = 100.0


def sanitize_opm_percentage(frame: pd.DataFrame) -> int:
    """Null out ``opm_percentage`` cells outside the valid percentage range.

    The source profit-and-loss workbook occasionally contains ₹-crore amounts
    (e.g. operating profit) in the ``opm_percentage`` column — notably for
    INDIGO rows. Any such row is already flagged by DQ-11, but the ratio
    cross-check still fires a misleading warning and the dashboard surfaces
    the corrupt value. Treating out-of-range cross-check references as missing
    is the correct ETL behaviour: the computed OPM remains the source of
    truth, and no downstream caller sees a nonsensical "reported" value.

    Returns the number of cells that were nulled.
    """
    if "opm_percentage" not in frame.columns:
        return 0
    values = pd.to_numeric(frame["opm_percentage"], errors="coerce")
    out_of_range = values.notna() & ~values.between(OPM_PERCENTAGE_MIN, OPM_PERCENTAGE_MAX)
    count = int(out_of_range.sum())
    if count:
        frame.loc[out_of_range, "opm_percentage"] = None
        LOGGER.warning(
            "sanitize_opm_percentage: nulled %d opm_percentage value(s) outside [%s, %s]",
            count,
            OPM_PERCENTAGE_MIN,
            OPM_PERCENTAGE_MAX,
        )
    return count


SOURCE_TABLES = {
    "companies.xlsx": "companies",
    "documents.xlsx": "documents",
    "analysis.xlsx": "analysis",
    "prosandcons.xlsx": "pros_and_cons",
    "profitandloss.xlsx": "financial_statements",
    "balancesheet.xlsx": "financial_statements",
    "cashflow.xlsx": "financial_statements",
    "supporting datasets/financial_ratios.xlsx": "financial_ratios",
    "supporting datasets/stock_prices.xlsx": "stock_prices",
    "supporting datasets/market_cap.xlsx": "market_cap",
    "supporting datasets/sectors.xlsx": "sectors",
    "supporting datasets/peer_groups.xlsx": "peer_groups",
}

STATEMENT_TYPES = {
    "profitandloss.xlsx": "profit_and_loss",
    "balancesheet.xlsx": "balance_sheet",
    "cashflow.xlsx": "cash_flow",
}


@dataclass(frozen=True)
class ExcelSource:
    path: Path
    table: str
    statement_type: str | None = None


def discover_sources(source_dir: str | Path) -> list[ExcelSource]:
    """Validate and return all 12 expected sources in deterministic order."""
    root = Path(source_dir).expanduser().resolve()
    sources: list[ExcelSource] = []
    missing: list[str] = []
    for relative_name, table in SOURCE_TABLES.items():
        path = root / relative_name
        if not path.is_file():
            missing.append(relative_name)
            continue
        sources.append(ExcelSource(path, table, STATEMENT_TYPES.get(path.name)))
    if missing:
        raise FileNotFoundError("Missing source workbooks: " + ", ".join(missing))
    return sources


def normalize_column_name(value: object) -> str:
    """Convert a source heading to a stable snake_case identifier."""
    text = str(value).strip().lower()
    chars = [character if character.isalnum() else "_" for character in text]
    return "_".join(filter(None, "".join(chars).split("_")))


def load_excel(source: ExcelSource) -> pd.DataFrame:
    """Load the first worksheet, remove empty rows/columns, and normalize headings."""
    preview = pd.read_excel(source.path, sheet_name=0, header=None, nrows=2, engine="openpyxl")
    first_row_values = int(preview.iloc[0].notna().sum())
    second_row_values = int(preview.iloc[1].notna().sum()) if len(preview) > 1 else 0
    header_row = 1 if first_row_values == 1 and second_row_values > 1 else 0
    frame = pd.read_excel(source.path, sheet_name=0, header=header_row, engine="openpyxl")
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
    frame.columns = [normalize_column_name(column) for column in frame.columns]
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError(f"Duplicate columns after normalization: {source.path}")
    frame.insert(0, "source_file", source.path.name)
    if source.statement_type:
        frame.insert(1, "statement_type", source.statement_type)
    if "company_id" in frame.columns:
        frame["company_id"] = frame["company_id"].map(normalize_ticker)
    if source.table == "companies" and "id" in frame.columns:
        frame["id"] = frame["id"].map(normalize_ticker)
    if "year" in frame.columns:
        frame["year"] = frame["year"].map(normalize_year).astype("Int64")
    if source.statement_type == "profit_and_loss":
        sanitize_opm_percentage(frame)
    return frame


def iter_loaded_sources(source_dir: str | Path) -> Iterator[tuple[ExcelSource, pd.DataFrame]]:
    for source in discover_sources(source_dir):
        yield source, load_excel(source)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect NIFTY 100 Excel sources")
    parser.add_argument("--source-dir", default=".")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for source, frame in iter_loaded_sources(args.source_dir):
        LOGGER.info("%-22s -> %-22s rows=%d cols=%d", source.path.name, source.table, *frame.shape)


if __name__ == "__main__":
    main()
