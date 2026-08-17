"""Cash-flow intelligence and capital-allocation reporting.

The small formula helpers remain implemented in :mod:`analytics.cashflow` for
backwards compatibility.  This module adds the Sprint 5 company-level model,
distress/deleveraging signals, capital-allocation audits, and CSV outputs.
Workbook presentation is deliberately separated from the calculations so the
same records can be reused by PDF reports and spreadsheet renderers.
"""

from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd

from .cashflow import (
    CapitalAllocationRow,
    build_capital_allocation_row,
    capex_intensity,
    cfo_quality_score,
    classify_capex_intensity,
    classify_capital_allocation,
    classify_cfo_quality,
    fcf_conversion_rate,
    free_cash_flow,
    write_capital_allocation_csv,
)

REQUIRED_INTELLIGENCE_COLUMNS = (
    "company_id",
    "sector",
    "cfo_quality_score",
    "cfo_quality_label",
    "capex_intensity_pct",
    "capex_label",
    "fcf_cagr_5yr",
    "fcf_conversion_pct",
    "distress_flag",
    "deleveraging_flag",
    "capital_allocation_label",
)

CAPITAL_ALLOCATION_PATTERNS = (
    "Reinvestor",
    "Shareholder Returns",
    "Liquidating Assets",
    "Distress Signal",
    "Growth Funded by Debt",
    "Cash Accumulator",
    "Pre-Revenue",
    "Mixed",
)


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def distress_signal(
    operating_activity: Real | None,
    financing_activity: Real | None,
) -> bool:
    """Return true when operations burn cash while financing raises cash."""
    cfo = _number(operating_activity)
    cff = _number(financing_activity)
    return cfo is not None and cff is not None and cfo < 0 and cff > 0


def deleveraging_signal(
    financing_activity: Real | None,
    current_borrowings: Real | None,
    prior_borrowings: Real | None,
) -> bool:
    """Return true for negative CFF accompanied by a year-on-year debt decline."""
    cff = _number(financing_activity)
    current = _number(current_borrowings)
    prior = _number(prior_borrowings)
    return (
        cff is not None
        and current is not None
        and prior is not None
        and cff < 0
        and current < prior
    )


def calculate_fcf_cagr_5yr(
    annual_fcf: dict[int, Real | None],
    latest_year: int,
) -> float | None:
    """Calculate five-year FCF CAGR using the same-year-to-year interval.

    CAGR is not meaningful when either endpoint is zero or when the endpoints
    have different signs.  Negative-to-negative series are also excluded to
    avoid presenting shrinking losses as positive compounding.
    """
    start = _number(annual_fcf.get(latest_year - 5))
    end = _number(annual_fcf.get(latest_year))
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1 / 5) - 1) * 100


@dataclass(frozen=True)
class CashFlowIntelligenceRow:
    company_id: str
    sector: str | None
    cfo_quality_score: float | None
    cfo_quality_label: str | None
    capex_intensity_pct: float | None
    capex_label: str | None
    fcf_cagr_5yr: float | None
    fcf_conversion_pct: float | None
    distress_flag: bool
    deleveraging_flag: bool
    capital_allocation_label: str | None


@dataclass(frozen=True)
class DistressAlert:
    company_id: str
    sector: str | None
    year: int
    cfo_value: float
    cff_value: float
    latest_net_profit: float | None


@dataclass(frozen=True)
class PatternChange:
    company_id: str
    company_name: str
    sector: str | None
    year: int
    previous_pattern: str
    current_pattern: str
    change_description: str


@dataclass(frozen=True)
class CapitalAllocationValidation:
    roster_companies: int
    represented_companies: int
    company_year_rows: int
    missing_companies: tuple[str, ...]
    duplicate_company_years: int


@dataclass(frozen=True)
class CashFlowOutputStats:
    intelligence_rows: int
    distress_alerts: int
    capital_allocation_rows: int
    pattern_changes: int
    represented_companies: int
    missing_cashflow_companies: tuple[str, ...]


def _latest_rows(
    connection: sqlite3.Connection,
    statement_type: str,
) -> dict[str, dict[int, dict[str, Any]]]:
    """Return one row per company/year, retaining the greatest source id."""
    histories: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    query = """
        SELECT * FROM financial_statements
        WHERE statement_type = ? AND year IS NOT NULL
        ORDER BY company_id, year, id
    """
    for raw in connection.execute(query, (statement_type,)):
        row = dict(raw)
        histories[str(row["company_id"])][int(row["year"])] = row
    return histories


def _latest_ratio_rows(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for raw in connection.execute(
        "SELECT * FROM financial_ratios WHERE year IS NOT NULL ORDER BY company_id, year, id"
    ):
        rows[str(raw["company_id"])] = dict(raw)
    return rows


def _aligned_quality_score(
    cash_history: dict[int, dict[str, Any]],
    profit_history: dict[int, dict[str, Any]],
    latest_year: int,
) -> float | None:
    years = list(range(latest_year - 4, latest_year + 1))
    cfo = [cash_history.get(year, {}).get("operating_activity") for year in years]
    pat = [profit_history.get(year, {}).get("net_profit") for year in years]
    return cfo_quality_score(cfo, pat)


def build_cashflow_intelligence(
    database_path: str | Path = "nifty100.db",
) -> tuple[
    list[CashFlowIntelligenceRow],
    list[DistressAlert],
    list[CapitalAllocationRow],
    list[PatternChange],
    CapitalAllocationValidation,
]:
    """Build all Sprint 5 cash-flow and capital-allocation records from SQLite."""
    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    try:
        companies = [dict(row) for row in connection.execute(
            """
            SELECT c.id AS company_id, c.company_name, s.broad_sector AS sector
            FROM companies AS c
            LEFT JOIN sectors AS s ON s.company_id = c.id
            ORDER BY c.id
            """
        )]
        cash = _latest_rows(connection, "cash_flow")
        profits = _latest_rows(connection, "profit_and_loss")
        balances = _latest_rows(connection, "balance_sheet")
        latest_ratios = _latest_ratio_rows(connection)
    finally:
        connection.close()

    intelligence: list[CashFlowIntelligenceRow] = []
    alerts: list[DistressAlert] = []
    allocations: list[CapitalAllocationRow] = []
    changes: list[PatternChange] = []

    for company in companies:
        company_id = str(company["company_id"])
        company_name = str(company["company_name"])
        sector = company.get("sector")
        cash_history = cash.get(company_id, {})
        profit_history = profits.get(company_id, {})
        balance_history = balances.get(company_id, {})

        patterns: list[tuple[int, str]] = []
        for year, row in sorted(cash_history.items()):
            pnl = profit_history.get(year, {})
            required = [
                _number(row.get("operating_activity")),
                _number(row.get("investing_activity")),
                _number(row.get("financing_activity")),
            ]
            if any(value is None for value in required):
                continue
            allocation = build_capital_allocation_row(
                company_id=company_id,
                year=year,
                operating_activity=required[0],
                investing_activity=required[1],
                financing_activity=required[2],
                net_profit=_number(pnl.get("net_profit")),
            )
            allocations.append(allocation)
            patterns.append((year, allocation.pattern_label))

        for (prior_year, prior_pattern), (year, pattern) in zip(
            patterns, patterns[1:], strict=False
        ):
            if year == prior_year + 1 and pattern != prior_pattern:
                changes.append(
                    PatternChange(
                        company_id,
                        company_name,
                        sector,
                        year,
                        prior_pattern,
                        pattern,
                        f"{company_id} moved from {prior_pattern} to {pattern}",
                    )
                )

        if not cash_history:
            intelligence.append(
                CashFlowIntelligenceRow(
                    company_id,
                    sector,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    False,
                    False,
                    None,
                )
            )
            continue

        latest_year = max(cash_history)
        latest_cash = cash_history[latest_year]
        latest_profit = profit_history.get(latest_year, {})
        latest_balance = balance_history.get(latest_year, {})
        prior_balance = balance_history.get(latest_year - 1, {})

        cfo = _number(latest_cash.get("operating_activity"))
        cfi = _number(latest_cash.get("investing_activity"))
        cff = _number(latest_cash.get("financing_activity"))
        sales = _number(latest_profit.get("sales"))
        operating_profit = _number(latest_profit.get("operating_profit"))
        net_profit = _number(latest_profit.get("net_profit"))
        quality = _aligned_quality_score(
            cash_history, profit_history, latest_year
        )
        intensity = capex_intensity(cfi, sales)
        latest_fcf = free_cash_flow(cfo, cfi)
        ratio_row = latest_ratios.get(company_id, {})
        fcf_cagr = _number(ratio_row.get("fcf_cagr_5yr"))
        if fcf_cagr is None:
            fcf_by_year = {
                year: free_cash_flow(
                    row.get("operating_activity"), row.get("investing_activity")
                )
                for year, row in cash_history.items()
            }
            fcf_cagr = calculate_fcf_cagr_5yr(fcf_by_year, latest_year)

        is_distress = distress_signal(cfo, cff)
        is_deleveraging = deleveraging_signal(
            cff,
            latest_balance.get("borrowings"),
            prior_balance.get("borrowings"),
        )
        annual_ratio = None if cfo is None or net_profit in {None, 0} else cfo / net_profit
        allocation_label = classify_capital_allocation(
            cfo, cfi, cff, cfo_pat_ratio=annual_ratio
        )

        intelligence.append(
            CashFlowIntelligenceRow(
                company_id,
                sector,
                quality,
                classify_cfo_quality(quality),
                intensity,
                classify_capex_intensity(intensity),
                fcf_cagr,
                fcf_conversion_rate(latest_fcf, operating_profit),
                is_distress,
                is_deleveraging,
                allocation_label,
            )
        )
        if is_distress and cfo is not None and cff is not None:
            alerts.append(
                DistressAlert(
                    company_id, sector, latest_year, cfo, cff, net_profit
                )
            )

    keys = [(row.company_id, row.year) for row in allocations]
    represented = {row.company_id for row in allocations}
    roster = {str(row["company_id"]) for row in companies}
    validation = CapitalAllocationValidation(
        roster_companies=len(roster),
        represented_companies=len(represented),
        company_year_rows=len(allocations),
        missing_companies=tuple(sorted(roster - represented)),
        duplicate_company_years=len(keys) - len(set(keys)),
    )
    return intelligence, alerts, allocations, changes, validation


def _write_dataclass_csv(
    rows: Iterable[object],
    output_path: str | Path,
    fieldnames: Sequence[str],
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    return path.resolve()


def write_cashflow_intelligence_csv(
    rows: Iterable[CashFlowIntelligenceRow], output_path: str | Path
) -> Path:
    return _write_dataclass_csv(rows, output_path, REQUIRED_INTELLIGENCE_COLUMNS)


def write_cashflow_intelligence_workbook(
    rows: Iterable[CashFlowIntelligenceRow], output_path: str | Path
) -> Path:
    """Write the sign-off workbook version of the cash-flow intelligence output."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        (asdict(row) for row in rows), columns=REQUIRED_INTELLIGENCE_COLUMNS
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Cashflow Intelligence")
        sheet = writer.sheets["Cashflow Intelligence"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column_cells in sheet.columns:
            width = max(len(str(cell.value or "")) for cell in column_cells) + 2
            sheet.column_dimensions[column_cells[0].column_letter].width = min(width, 30)
    return path.resolve()


def write_distress_alerts(
    rows: Iterable[DistressAlert], output_path: str | Path
) -> Path:
    return _write_dataclass_csv(
        rows, output_path, list(DistressAlert.__dataclass_fields__)
    )


def write_pattern_changes(
    rows: Iterable[PatternChange], output_path: str | Path
) -> Path:
    return _write_dataclass_csv(
        rows, output_path, list(PatternChange.__dataclass_fields__)
    )


def write_pattern_distribution(
    allocation_rows: Iterable[CapitalAllocationRow], output_path: str | Path
) -> Path:
    rows = list(allocation_rows)
    latest_by_company: dict[str, CapitalAllocationRow] = {}
    for row in sorted(rows, key=lambda item: (item.company_id, item.year)):
        latest_by_company[row.company_id] = row
    counts = Counter(row.pattern_label for row in latest_by_company.values())
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["pattern_label", "company_count"])
        writer.writeheader()
        writer.writerows(
            {"pattern_label": pattern, "company_count": counts.get(pattern, 0)}
            for pattern in CAPITAL_ALLOCATION_PATTERNS
        )
    return path.resolve()


def generate_cashflow_outputs(
    database_path: str | Path = "nifty100.db",
    output_dir: str | Path = "output",
) -> CashFlowOutputStats:
    """Generate the CSV-backed intelligence and allocation audit outputs."""
    intelligence, alerts, allocations, changes, validation = build_cashflow_intelligence(
        database_path
    )
    root = Path(output_dir)
    write_cashflow_intelligence_csv(intelligence, root / "cashflow_intelligence.csv")
    write_cashflow_intelligence_workbook(intelligence, root / "cashflow_intelligence.xlsx")
    write_distress_alerts(alerts, root / "distress_alerts.csv")
    write_capital_allocation_csv(allocations, root / "capital_allocation.csv")
    write_pattern_changes(changes, root / "pattern_changes.csv")
    write_pattern_distribution(allocations, root / "capital_allocation_distribution.csv")
    return CashFlowOutputStats(
        intelligence_rows=len(intelligence),
        distress_alerts=len(alerts),
        capital_allocation_rows=len(allocations),
        pattern_changes=len(changes),
        represented_companies=validation.represented_companies,
        missing_cashflow_companies=validation.missing_companies,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate cash-flow intelligence outputs")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args(argv)
    stats = generate_cashflow_outputs(args.database, args.output_dir)
    print(
        f"Generated {stats.intelligence_rows} intelligence rows, "
        f"{stats.distress_alerts} distress alerts, "
        f"{stats.capital_allocation_rows} allocation rows, and "
        f"{stats.pattern_changes} pattern changes; "
        f"cash-flow coverage={stats.represented_companies}/92, "
        f"missing={list(stats.missing_cashflow_companies)}"
    )
    return 0


__all__ = [
    "CAPITAL_ALLOCATION_PATTERNS",
    "REQUIRED_INTELLIGENCE_COLUMNS",
    "CashFlowIntelligenceRow",
    "CapitalAllocationValidation",
    "DistressAlert",
    "PatternChange",
    "build_cashflow_intelligence",
    "calculate_fcf_cagr_5yr",
    "capex_intensity",
    "cfo_quality_score",
    "classify_capex_intensity",
    "classify_cfo_quality",
    "deleveraging_signal",
    "distress_signal",
    "fcf_conversion_rate",
    "free_cash_flow",
    "generate_cashflow_outputs",
    "write_cashflow_intelligence_csv",
    "write_cashflow_intelligence_workbook",
    "write_distress_alerts",
    "write_pattern_changes",
    "write_pattern_distribution",
]


if __name__ == "__main__":
    raise SystemExit(main())
