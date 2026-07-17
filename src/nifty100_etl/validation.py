"""Sixteen deterministic data-quality rules for the Sprint 1 sources."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from .loader import SOURCE_TABLES, ExcelSource, iter_loaded_sources

CRITICAL = "CRITICAL"
WARNING = "WARNING"
FAILURE_COLUMNS = [
    "dq_rule",
    "severity",
    "table",
    "source_file",
    "row_number",
    "column",
    "value",
    "message",
]

REQUIRED_COLUMNS: dict[str, set[str]] = {
    "companies.xlsx": {"id", "company_name"},
    "documents.xlsx": {"id", "company_id", "year", "annual_report"},
    "analysis.xlsx": {"id", "company_id"},
    "prosandcons.xlsx": {"id", "company_id", "pros", "cons"},
    "profitandloss.xlsx": {"id", "company_id", "year", "sales", "operating_profit"},
    "balancesheet.xlsx": {"id", "company_id", "year", "total_liabilities", "total_assets"},
    "cashflow.xlsx": {"id", "company_id", "year", "net_cash_flow"},
    "financial_ratios.xlsx": {"id", "company_id", "year"},
    "stock_prices.xlsx": {"id", "company_id", "date", "close_price", "volume"},
    "market_cap.xlsx": {"id", "company_id", "year", "market_cap_crore"},
    "sectors.xlsx": {"id", "company_id", "broad_sector"},
    "peer_groups.xlsx": {"id", "company_id", "peer_group_name"},
}


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    description: str
    check: Callable[[ValidationContext], list[dict[str, Any]]]


@dataclass(frozen=True)
class ValidationContext:
    sources: tuple[tuple[ExcelSource, pd.DataFrame], ...]

    @property
    def company_ids(self) -> set[str]:
        for source, frame in self.sources:
            if source.table == "companies":
                return set(frame["id"].dropna().astype(str))
        return set()


def _failure(
    rule: Rule,
    table: str,
    source_file: str,
    message: str,
    *,
    row_number: int | None = None,
    column: str = "",
    value: Any = "",
) -> dict[str, Any]:
    return {
        "dq_rule": rule.id,
        "severity": rule.severity,
        "table": table,
        "source_file": source_file,
        "row_number": row_number,
        "column": column,
        "value": value,
        "message": message,
    }


def _row_failures(
    rule: Rule,
    source: ExcelSource,
    frame: pd.DataFrame,
    mask: pd.Series,
    column: str,
    message: str,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for index in frame.index[mask.fillna(False)]:
        value = frame.at[index, column] if column in frame else ""
        failures.append(
            _failure(
                rule,
                source.table,
                source.path.name,
                message,
                row_number=int(index) + 2,
                column=column,
                value=value,
            )
        )
    return failures


def _dq01(context: ValidationContext) -> list[dict[str, Any]]:
    rule = RULE_BY_ID["DQ-01"]
    found = {source.path.name for source, _ in context.sources}
    expected = {Path(name).name for name in SOURCE_TABLES}
    return [
        _failure(rule, "pipeline", name, "Expected source workbook was not loaded")
        for name in sorted(expected - found)
    ]


def _dq02(context: ValidationContext) -> list[dict[str, Any]]:
    rule = RULE_BY_ID["DQ-02"]
    tables = {source.table for source, _ in context.sources}
    expected = set(SOURCE_TABLES.values())
    if tables == expected and len(tables) == 10:
        return []
    return [_failure(rule, "pipeline", "", f"Expected 10 logical tables; found {len(tables)}")]


def _company_frame(context: ValidationContext) -> tuple[ExcelSource, pd.DataFrame] | None:
    return next(
        ((source, frame) for source, frame in context.sources if source.table == "companies"), None
    )


def _dq03(context: ValidationContext) -> list[dict[str, Any]]:
    pair = _company_frame(context)
    if pair is None or "id" not in pair[1]:
        return []
    source, frame = pair
    return _row_failures(
        RULE_BY_ID["DQ-03"], source, frame, frame["id"].isna(), "id", "Company PK is null"
    )


def _dq04(context: ValidationContext) -> list[dict[str, Any]]:
    pair = _company_frame(context)
    if pair is None or "id" not in pair[1]:
        return []
    source, frame = pair
    mask = frame["id"].notna() & frame["id"].duplicated(keep=False)
    return _row_failures(RULE_BY_ID["DQ-04"], source, frame, mask, "id", "Company PK is duplicated")


def _dq05(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        if "company_id" in frame:
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-05"],
                    source,
                    frame,
                    frame["company_id"].isna(),
                    "company_id",
                    "Company FK is null",
                )
            )
    return failures


def _dq06(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    company_ids = context.company_ids
    for source, frame in context.sources:
        if "company_id" in frame:
            mask = frame["company_id"].notna() & ~frame["company_id"].isin(company_ids)
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-06"],
                    source,
                    frame,
                    mask,
                    "company_id",
                    "Company FK does not exist in companies.id",
                )
            )
    return failures


def _dq07(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        if "id" in frame:
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-07"], source, frame, frame["id"].isna(), "id", "Row PK is null"
                )
            )
    return failures


def _dq08(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        if "id" in frame:
            mask = frame["id"].notna() & frame["id"].duplicated(keep=False)
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-08"],
                    source,
                    frame,
                    mask,
                    "id",
                    "Row PK is duplicated within source",
                )
            )
    return failures


def _dq09(context: ValidationContext) -> list[dict[str, Any]]:
    rule = RULE_BY_ID["DQ-09"]
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        missing = REQUIRED_COLUMNS.get(source.path.name, set()) - set(frame.columns)
        failures.extend(
            _failure(
                rule, source.table, source.path.name, "Required column is missing", column=column
            )
            for column in sorted(missing)
        )
    return failures


def _dq10(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        if "year" in frame:
            mask = frame["year"].notna() & ~frame["year"].between(1900, 2100)
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-10"], source, frame, mask, "year", "Year is outside 1900-2100"
                )
            )
    return failures


def _dq11(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        if "opm_percentage" in frame:
            values = pd.to_numeric(frame["opm_percentage"], errors="coerce")
            mask = values.notna() & ~values.between(-100, 100)
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-11"],
                    source,
                    frame,
                    mask,
                    "opm_percentage",
                    "OPM is outside -100% to 100%",
                )
            )
    return failures


def _dq12(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        if {"total_assets", "total_liabilities"} <= set(frame):
            assets = pd.to_numeric(frame["total_assets"], errors="coerce")
            liabilities = pd.to_numeric(frame["total_liabilities"], errors="coerce")
            tolerance = pd.concat([assets.abs(), liabilities.abs()], axis=1).max(axis=1) * 0.01
            mask = (
                assets.notna()
                & liabilities.notna()
                & ((assets - liabilities).abs() > tolerance.clip(lower=1))
            )
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-12"],
                    source,
                    frame,
                    mask,
                    "total_assets",
                    "Balance sheet does not balance within 1%",
                )
            )
    return failures


def _dq13(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        if "sales" in frame:
            sales = pd.to_numeric(frame["sales"], errors="coerce")
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-13"], source, frame, sales < 0, "sales", "Sales is negative"
                )
            )
    return failures


def _dq14(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        price_columns = {"open_price", "high_price", "low_price", "close_price"}
        if price_columns <= set(frame):
            prices = frame[list(price_columns)].apply(pd.to_numeric, errors="coerce")
            mask = (
                (
                    prices["high_price"]
                    < prices[["open_price", "close_price", "low_price"]].max(axis=1)
                )
                | (
                    prices["low_price"]
                    > prices[["open_price", "close_price", "high_price"]].min(axis=1)
                )
                | (prices <= 0).any(axis=1)
            )
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-14"],
                    source,
                    frame,
                    mask,
                    "close_price",
                    "OHLC prices are inconsistent or non-positive",
                )
            )
    return failures


def _dq15(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for source, frame in context.sources:
        if "volume" in frame:
            volume = pd.to_numeric(frame["volume"], errors="coerce")
            failures.extend(
                _row_failures(
                    RULE_BY_ID["DQ-15"],
                    source,
                    frame,
                    volume < 0,
                    "volume",
                    "Trading volume is negative",
                )
            )
    return failures


def _is_bad_url(value: Any) -> bool:
    if pd.isna(value) or str(value).strip() == "":
        return False
    parsed = urlparse(str(value).strip())
    return parsed.scheme not in {"http", "https"} or not parsed.netloc


def _dq16(context: ValidationContext) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    url_columns = {
        "annual_report",
        "website",
        "chart_link",
        "nse_profile",
        "bse_profile",
        "company_logo",
    }
    for source, frame in context.sources:
        for column in sorted(url_columns & set(frame.columns)):
            mask = frame[column].map(_is_bad_url)
            failures.extend(
                _row_failures(RULE_BY_ID["DQ-16"], source, frame, mask, column, "URL is malformed")
            )
    return failures


RULES: tuple[Rule, ...] = (
    Rule("DQ-01", CRITICAL, "All 12 source workbooks are loaded", _dq01),
    Rule("DQ-02", CRITICAL, "Exactly 10 logical tables are defined", _dq02),
    Rule("DQ-03", CRITICAL, "Company primary keys are not null", _dq03),
    Rule("DQ-04", CRITICAL, "Company primary keys are unique", _dq04),
    Rule("DQ-05", CRITICAL, "Company foreign keys are not null", _dq05),
    Rule("DQ-06", CRITICAL, "Company foreign keys exist in the company master", _dq06),
    Rule("DQ-07", CRITICAL, "Source row primary keys are not null", _dq07),
    Rule("DQ-08", CRITICAL, "Source row primary keys are unique", _dq08),
    Rule("DQ-09", CRITICAL, "Required source columns exist", _dq09),
    Rule("DQ-10", WARNING, "Years are within the supported range", _dq10),
    Rule("DQ-11", WARNING, "Operating margin percentage is plausible", _dq11),
    Rule("DQ-12", WARNING, "Balance sheet assets equal liabilities", _dq12),
    Rule("DQ-13", WARNING, "Sales values are non-negative", _dq13),
    Rule("DQ-14", WARNING, "OHLC prices are internally consistent", _dq14),
    Rule("DQ-15", WARNING, "Trading volumes are non-negative", _dq15),
    Rule("DQ-16", WARNING, "HTTP/HTTPS URLs are well formed", _dq16),
)
RULE_BY_ID = {rule.id: rule for rule in RULES}


def validate_sources(source_dir: str | Path = ".") -> pd.DataFrame:
    """Run DQ-01 through DQ-16 and return one row per failure."""
    context = ValidationContext(tuple(iter_loaded_sources(source_dir)))
    failures = [failure for rule in RULES for failure in rule.check(context)]
    return pd.DataFrame(failures, columns=FAILURE_COLUMNS)


def write_validation_failures(failures: pd.DataFrame, output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    failures.to_csv(path, index=False)
    return path.resolve()


def critical_failure_count(failures: pd.DataFrame) -> int:
    return int((failures["severity"] == CRITICAL).sum()) if not failures.empty else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run all 16 NIFTY 100 data-quality rules")
    parser.add_argument("--source-dir", default=".")
    parser.add_argument("--output", default="validation_failures.csv")
    parser.add_argument("--fail-on-critical", action="store_true")
    args = parser.parse_args(argv)
    failures = validate_sources(args.source_dir)
    output = write_validation_failures(failures, args.output)
    critical = critical_failure_count(failures)
    warning = int((failures["severity"] == WARNING).sum()) if not failures.empty else 0
    print(f"16 rules executed; failures={len(failures)} critical={critical} warning={warning}")
    print(f"Report: {output}")
    return 1 if args.fail_on_critical and critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
