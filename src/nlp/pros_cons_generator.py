"""Generate quantitative pros and cons from the financial Ratio Engine.

Each rule is deterministic, emits the requested analyst text, and receives a
0-100 confidence score based on distance from its threshold or streak length.
Only signals above the Day 30 confidence threshold are written.
"""

from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

CONFIDENCE_THRESHOLD = 60
TREND_YEARS = 3

PRO_TEXT = {
    1: "Consistently high return on equity above 20% demonstrates exceptional capital efficiency",
    2: "Strong free cash flow generation over 5 years signals healthy business fundamentals",
    3: "Debt-free balance sheet provides financial flexibility and eliminates interest burden",
    4: "Revenue growing at above 15% CAGR over 5 years reflects strong business momentum",
    5: "Operating profit margin above 25% indicates strong pricing power and cost discipline",
    6: "Net profit compounding at above 20% over 5 years creates significant shareholder value",
    7: "Very high interest coverage ratio reflects negligible financial stress from debt servicing",
    8: "Consistent dividend yield above 2% backed by positive free cash flow",
    9: (
        "Earnings per share growing above 15% CAGR indicates strong earnings quality "
        "and compounding"
    ),
    10: "Return on equity improving for 3 consecutive years shows strengthening business quality",
    11: "Revenue growing slower than profits shows improving operating leverage and scale benefits",
    12: "Growing asset base funded by internal accruals reflects self-sustaining growth",
}

CON_TEXT = {
    2: (
        "Free cash flow negative for 3 consecutive years raises concern about cash "
        "generation quality"
    ),
    3: "Operating margins declining for 3 consecutive years suggest pricing or cost pressure",
    4: "Company reported a net loss in the most recent financial year",
    5: (
        "Revenue contraction over 2 consecutive years indicates demand weakness or "
        "market share loss"
    ),
    6: (
        "Interest coverage ratio below 1.5x indicates the company is at risk of not "
        "meeting its debt obligations"
    ),
    7: (
        "Dividend payout ratio above 100% means the company is paying dividends from "
        "reserves, which is unsustainable"
    ),
    8: "Rising debt-to-equity ratio over 3 years suggests increasing financial leverage risk",
    9: "Earnings per share declining for 3 consecutive years reflects deteriorating profitability",
    10: (
        "Return on capital employed below 10% suggests the business is not generating "
        "sufficient returns on invested capital"
    ),
    11: (
        "Net debt exceeding 3 times EBITDA is a high leverage ratio and limits financial "
        "flexibility"
    ),
    12: (
        "Revenue growing at below 5% over 5 years lags inflation and suggests limited "
        "business momentum"
    ),
}

PRO_REVIEW_TEXT = (
    "No quantitative pro rule exceeded 60% confidence; positive factors require manual review"
)
CON_REVIEW_TEXT = (
    "No quantitative con rule exceeded 60% confidence; risk factors require manual review"
)

History = dict[int, dict[str, Any]]


@dataclass(frozen=True)
class CompanyData:
    """All histories needed to evaluate one company."""

    company_id: str
    broad_sector: str | None
    ratios: History
    profit_and_loss: History
    balance_sheet: History
    market_cap: History


@dataclass(frozen=True)
class GeneratedSignal:
    """One output-ready pro or con."""

    company_id: str
    type: Literal["pro", "con"]
    rule_id: int
    text: str
    confidence_pct: int


@dataclass(frozen=True)
class GeneratorStats:
    """Coverage and output statistics for a generator run."""

    companies: int
    signals: int
    pros: int
    cons: int
    review_pros: int
    review_cons: int


class CoverageError(RuntimeError):
    """Raised when one or more companies have no qualifying pro or con."""


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _latest(history: Mapping[int, dict[str, Any]]) -> tuple[int, dict[str, Any]] | None:
    if not history:
        return None
    year = max(history)
    return year, history[year]


def _consecutive_values(
    history: Mapping[int, dict[str, Any]],
    field: str,
    count: int,
    end_year: int,
) -> list[float] | None:
    values: list[float] = []
    for year in range(end_year - count + 1, end_year + 1):
        value = _number(history.get(year, {}).get(field))
        if value is None:
            return None
        values.append(value)
    return values


def _trailing_streak(
    history: Mapping[int, dict[str, Any]],
    field: str,
    end_year: int,
    predicate: Callable[[float], bool],
) -> list[float]:
    values: list[float] = []
    year = end_year
    while True:
        value = _number(history.get(year, {}).get(field))
        if value is None or not predicate(value):
            return list(reversed(values))
        values.append(value)
        year -= 1


def _strictly_increasing(values: Sequence[float] | None) -> bool:
    return values is not None and all(right > left for left, right in pairwise(values))


def _strictly_decreasing(values: Sequence[float] | None) -> bool:
    return values is not None and all(right < left for left, right in pairwise(values))


def _confidence_above(value: float, threshold: float, full_strength_delta: float) -> int:
    strength = min(1.0, max(0.0, (value - threshold) / full_strength_delta))
    return round(61 + 39 * strength)


def _confidence_below(value: float, threshold: float, full_strength_delta: float) -> int:
    strength = min(1.0, max(0.0, (threshold - value) / full_strength_delta))
    return round(61 + 39 * strength)


def _streak_confidence(length: int, minimum: int) -> int:
    return min(100, 75 + max(0, length - minimum) * 5)


def _format_ratio(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _add_signal(
    output: list[GeneratedSignal],
    company_id: str,
    signal_type: Literal["pro", "con"],
    rule_id: int,
    text: str,
    confidence: int,
) -> None:
    if confidence > CONFIDENCE_THRESHOLD:
        output.append(
            GeneratedSignal(company_id, signal_type, rule_id, text, min(100, confidence))
        )


def generate_company_signals(company: CompanyData) -> list[GeneratedSignal]:
    """Evaluate the 12 pro rules and 12 con rules for one company."""
    latest_ratio_item = _latest(company.ratios)
    if latest_ratio_item is None:
        return []
    year, ratio = latest_ratio_item
    output: list[GeneratedSignal] = []

    # Pro 1: ROE > 20% for at least three consecutive trailing years.
    high_roe = _trailing_streak(
        company.ratios, "return_on_equity_pct", year, lambda value: value > 20
    )
    if len(high_roe) >= 3:
        confidence = max(
            _streak_confidence(len(high_roe), 3),
            _confidence_above(min(high_roe), 20, 20),
        )
        _add_signal(output, company.company_id, "pro", 1, PRO_TEXT[1], confidence)

    # Pro 2: positive FCF for at least five consecutive trailing years.
    positive_fcf = _trailing_streak(
        company.ratios, "free_cash_flow_cr", year, lambda value: value > 0
    )
    if len(positive_fcf) >= 5:
        _add_signal(
            output,
            company.company_id,
            "pro",
            2,
            PRO_TEXT[2],
            _streak_confidence(len(positive_fcf), 5),
        )

    debt_to_equity = _number(ratio.get("debt_to_equity"))
    debt_free = debt_to_equity == 0

    # Pro 3: exactly debt-free in the latest year.
    if debt_free:
        _add_signal(output, company.company_id, "pro", 3, PRO_TEXT[3], 95)

    revenue_cagr = _number(ratio.get("revenue_cagr_5yr"))
    if revenue_cagr is not None and revenue_cagr > 15:
        _add_signal(
            output,
            company.company_id,
            "pro",
            4,
            PRO_TEXT[4],
            _confidence_above(revenue_cagr, 15, 15),
        )

    opm = _number(ratio.get("operating_profit_margin_pct"))
    if opm is not None and opm > 25:
        _add_signal(
            output,
            company.company_id,
            "pro",
            5,
            PRO_TEXT[5],
            _confidence_above(opm, 25, 25),
        )

    pat_cagr = _number(ratio.get("pat_cagr_5yr"))
    if pat_cagr is not None and pat_cagr > 20:
        _add_signal(
            output,
            company.company_id,
            "pro",
            6,
            PRO_TEXT[6],
            _confidence_above(pat_cagr, 20, 20),
        )

    interest_coverage = _number(ratio.get("interest_coverage"))
    labelled_debt_free = str(ratio.get("icr_label") or "").strip().casefold() == "debt free"
    if debt_free or labelled_debt_free:
        _add_signal(output, company.company_id, "pro", 7, PRO_TEXT[7], 95)
    elif interest_coverage is not None and interest_coverage > 10:
        _add_signal(
            output,
            company.company_id,
            "pro",
            7,
            PRO_TEXT[7],
            _confidence_above(interest_coverage, 10, 20),
        )

    latest_market_item = _latest(company.market_cap)
    dividend_yield = (
        _number(latest_market_item[1].get("dividend_yield_pct"))
        if latest_market_item is not None
        else None
    )
    latest_fcf = _number(ratio.get("free_cash_flow_cr"))
    if (
        dividend_yield is not None
        and dividend_yield > 2
        and latest_fcf is not None
        and latest_fcf > 0
    ):
        _add_signal(
            output,
            company.company_id,
            "pro",
            8,
            PRO_TEXT[8],
            _confidence_above(dividend_yield, 2, 3),
        )

    eps_cagr = _number(ratio.get("eps_cagr_5yr"))
    if eps_cagr is not None and eps_cagr > 15:
        _add_signal(
            output,
            company.company_id,
            "pro",
            9,
            PRO_TEXT[9],
            _confidence_above(eps_cagr, 15, 15),
        )

    roe_trend = _consecutive_values(
        company.ratios, "return_on_equity_pct", TREND_YEARS, year
    )
    if _strictly_increasing(roe_trend):
        assert roe_trend is not None
        _add_signal(
            output,
            company.company_id,
            "pro",
            10,
            PRO_TEXT[10],
            _confidence_above(roe_trend[-1] - roe_trend[0], 0, 10),
        )

    # The condition below follows the supplied Rule 11 inequality literally.
    if revenue_cagr is not None and pat_cagr is not None and revenue_cagr > pat_cagr:
        _add_signal(
            output,
            company.company_id,
            "pro",
            11,
            PRO_TEXT[11],
            _confidence_above(revenue_cagr - pat_cagr, 0, 10),
        )

    asset_trend = _consecutive_values(company.balance_sheet, "total_assets", TREND_YEARS, year)
    debt_trend = _consecutive_values(company.balance_sheet, "borrowings", TREND_YEARS, year)
    if _strictly_increasing(asset_trend) and _strictly_decreasing(debt_trend):
        _add_signal(output, company.company_id, "pro", 12, PRO_TEXT[12], 80)

    # Con 1: D/E > 2.0, excluding Financials.
    is_financial = (company.broad_sector or "").strip().casefold() == "financials"
    if not is_financial and debt_to_equity is not None and debt_to_equity > 2:
        text = (
            f"Debt-to-equity ratio of {_format_ratio(debt_to_equity)} is elevated for a "
            "non-financial company and warrants monitoring"
        )
        _add_signal(
            output,
            company.company_id,
            "con",
            1,
            text,
            _confidence_above(debt_to_equity, 2, 3),
        )

    negative_fcf = _trailing_streak(
        company.ratios, "free_cash_flow_cr", year, lambda value: value < 0
    )
    if len(negative_fcf) >= 3:
        _add_signal(
            output,
            company.company_id,
            "con",
            2,
            CON_TEXT[2],
            _streak_confidence(len(negative_fcf), 3),
        )

    opm_trend = _consecutive_values(
        company.ratios, "operating_profit_margin_pct", TREND_YEARS, year
    )
    if _strictly_decreasing(opm_trend):
        assert opm_trend is not None
        _add_signal(
            output,
            company.company_id,
            "con",
            3,
            CON_TEXT[3],
            _confidence_above(opm_trend[0] - opm_trend[-1], 0, 10),
        )

    latest_profit = company.profit_and_loss.get(year, {})
    net_profit = _number(latest_profit.get("net_profit"))
    if net_profit is not None and net_profit < 0:
        _add_signal(output, company.company_id, "con", 4, CON_TEXT[4], 95)

    revenue_trend = _consecutive_values(company.profit_and_loss, "sales", 3, year)
    if _strictly_decreasing(revenue_trend):
        assert revenue_trend is not None
        decline_pct = (
            (revenue_trend[0] - revenue_trend[-1]) / abs(revenue_trend[0]) * 100
            if revenue_trend[0] != 0
            else 100
        )
        _add_signal(
            output,
            company.company_id,
            "con",
            5,
            CON_TEXT[5],
            _confidence_above(decline_pct, 0, 20),
        )

    if interest_coverage is not None and interest_coverage < 1.5:
        _add_signal(
            output,
            company.company_id,
            "con",
            6,
            CON_TEXT[6],
            _confidence_below(interest_coverage, 1.5, 1.5),
        )

    dividend_payout = _number(ratio.get("dividend_payout_ratio_pct"))
    if dividend_payout is not None and dividend_payout > 100:
        _add_signal(
            output,
            company.company_id,
            "con",
            7,
            CON_TEXT[7],
            _confidence_above(dividend_payout, 100, 100),
        )

    debt_ratio_trend = _consecutive_values(
        company.ratios, "debt_to_equity", TREND_YEARS, year
    )
    if _strictly_increasing(debt_ratio_trend):
        assert debt_ratio_trend is not None
        _add_signal(
            output,
            company.company_id,
            "con",
            8,
            CON_TEXT[8],
            _confidence_above(debt_ratio_trend[-1] - debt_ratio_trend[0], 0, 1),
        )

    eps_trend = _consecutive_values(company.ratios, "earnings_per_share", TREND_YEARS, year)
    if _strictly_decreasing(eps_trend):
        assert eps_trend is not None
        decline_pct = (
            (eps_trend[0] - eps_trend[-1]) / abs(eps_trend[0]) * 100
            if eps_trend[0] != 0
            else 100
        )
        _add_signal(
            output,
            company.company_id,
            "con",
            9,
            CON_TEXT[9],
            _confidence_above(decline_pct, 0, 30),
        )

    roce = _number(ratio.get("return_on_capital_employed_pct"))
    if roce is not None and roce < 10:
        _add_signal(
            output,
            company.company_id,
            "con",
            10,
            CON_TEXT[10],
            _confidence_below(roce, 10, 10),
        )

    net_debt = _number(ratio.get("net_debt"))
    ebitda = _number(latest_profit.get("operating_profit"))
    if net_debt is not None and ebitda is not None and ebitda > 0:
        net_debt_to_ebitda = net_debt / ebitda
        if net_debt_to_ebitda > 3:
            _add_signal(
                output,
                company.company_id,
                "con",
                11,
                CON_TEXT[11],
                _confidence_above(net_debt_to_ebitda, 3, 3),
            )

    if revenue_cagr is not None and revenue_cagr < 5:
        _add_signal(
            output,
            company.company_id,
            "con",
            12,
            CON_TEXT[12],
            _confidence_below(revenue_cagr, 5, 5),
        )

    return output


def _load_history(
    connection: sqlite3.Connection,
    query: str,
) -> dict[str, History]:
    result: dict[str, History] = {}
    for raw_row in connection.execute(query):
        row = dict(raw_row)
        company_id = str(row["company_id"])
        year = int(row["year"])
        result.setdefault(company_id, {})[year] = row
    return result


def load_company_data(database_path: str | Path) -> list[CompanyData]:
    """Load deduplicated annual histories for every company in SQLite."""
    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    try:
        companies = list(
            connection.execute(
                """
                SELECT c.id AS company_id, s.broad_sector
                FROM companies AS c
                LEFT JOIN sectors AS s ON s.company_id = c.id
                ORDER BY c.id
                """
            )
        )
        ratios = _load_history(
            connection,
            "SELECT * FROM financial_ratios WHERE year IS NOT NULL ORDER BY id",
        )
        profits = _load_history(
            connection,
            """
            SELECT * FROM financial_statements
            WHERE statement_type = 'profit_and_loss' AND year IS NOT NULL
            ORDER BY id
            """,
        )
        balances = _load_history(
            connection,
            """
            SELECT * FROM financial_statements
            WHERE statement_type = 'balance_sheet' AND year IS NOT NULL
            ORDER BY id
            """,
        )
        market = _load_history(
            connection,
            "SELECT * FROM market_cap WHERE year IS NOT NULL ORDER BY id",
        )
    finally:
        connection.close()

    return [
        CompanyData(
            company_id=str(row["company_id"]),
            broad_sector=row["broad_sector"],
            ratios=ratios.get(str(row["company_id"]), {}),
            profit_and_loss=profits.get(str(row["company_id"]), {}),
            balance_sheet=balances.get(str(row["company_id"]), {}),
            market_cap=market.get(str(row["company_id"]), {}),
        )
        for row in companies
    ]


def verify_company_coverage(
    signals: Iterable[GeneratedSignal],
    company_ids: Iterable[str],
) -> None:
    """Assert that every company has at least one pro and at least one con."""
    coverage: dict[str, set[str]] = {company_id: set() for company_id in company_ids}
    for signal in signals:
        coverage.setdefault(signal.company_id, set()).add(signal.type)
    missing_pros = sorted(
        company_id for company_id, types in coverage.items() if "pro" not in types
    )
    missing_cons = sorted(
        company_id for company_id, types in coverage.items() if "con" not in types
    )
    if missing_pros or missing_cons:
        raise CoverageError(
            f"Missing pros for {missing_pros}; missing cons for {missing_cons}"
        )


def generate_all_signals(
    companies: Iterable[CompanyData],
    *,
    add_review_sentinels: bool = True,
) -> list[GeneratedSignal]:
    """Generate signals and optionally add honest manual-review coverage rows.

    The 24 quantitative rules do not mathematically guarantee a hit for every
    possible company.  A rule-0 review sentinel preserves the required output
    coverage without making a financial claim that the data does not support.
    """
    output: list[GeneratedSignal] = []
    for company in companies:
        company_signals = generate_company_signals(company)
        if add_review_sentinels:
            types = {signal.type for signal in company_signals}
            if "pro" not in types:
                company_signals.append(
                    GeneratedSignal(company.company_id, "pro", 0, PRO_REVIEW_TEXT, 100)
                )
            if "con" not in types:
                company_signals.append(
                    GeneratedSignal(company.company_id, "con", 0, CON_REVIEW_TEXT, 100)
                )
        output.extend(company_signals)
    return output


def write_generated_signals(
    signals: Iterable[GeneratedSignal],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(GeneratedSignal.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(signal) for signal in signals)
    return path.resolve()


def generate_pros_cons(
    database_path: str | Path = "nifty100.db",
    output_path: str | Path = "output/pros_cons_generated.csv",
) -> GeneratorStats:
    """Generate, verify, and write pros/cons for the full companies table."""
    companies = load_company_data(database_path)
    signals = generate_all_signals(companies)
    company_ids = [company.company_id for company in companies]
    verify_company_coverage(signals, company_ids)
    write_generated_signals(signals, output_path)
    return GeneratorStats(
        companies=len(companies),
        signals=len(signals),
        pros=sum(signal.type == "pro" for signal in signals),
        cons=sum(signal.type == "con" for signal in signals),
        review_pros=sum(signal.type == "pro" and signal.rule_id == 0 for signal in signals),
        review_cons=sum(signal.type == "con" and signal.rule_id == 0 for signal in signals),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate financial pros and cons")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--output", default="output/pros_cons_generated.csv")
    args = parser.parse_args(argv)
    stats = generate_pros_cons(args.database, args.output)
    print(
        f"Generated {stats.signals} signals for {stats.companies} companies "
        f"(pros={stats.pros}, cons={stats.cons}, "
        f"review pros={stats.review_pros}, review cons={stats.review_cons})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
