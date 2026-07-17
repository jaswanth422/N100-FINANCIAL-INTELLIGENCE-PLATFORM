"""Populate the SQLite financial_ratios table from normalized statements."""

from __future__ import annotations

import argparse
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cagr import calculate_growth_cagrs
from .cashflow import (
    capex_intensity,
    cfo_quality_score,
    classify_capex_intensity,
    classify_capital_allocation,
    classify_cfo_quality,
    fcf_conversion_rate,
    free_cash_flow,
)
from .ratios import (
    asset_turnover,
    calculate_leverage_efficiency_ratios,
    calculate_profitability_ratios,
    net_profit_margin,
)


@dataclass(frozen=True)
class PopulationStats:
    rows: int
    companies: int
    inserted_rows: int


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def book_value_per_share(
    equity_capital: float | None,
    reserves: float | None,
    face_value: float | None,
) -> float | None:
    """Calculate book value per share from crore-denominated equity accounts."""
    equity = _number(equity_capital)
    retained = _number(reserves)
    face = _number(face_value)
    if equity is None or retained is None or face is None or equity == 0:
        return None
    return (equity + retained) * face / equity


def composite_quality_score(
    *,
    roe_pct: float | None,
    net_margin_pct: float | None,
    debt_to_equity_ratio: float | None,
    interest_coverage_ratio: float | None,
    cfo_pat_score: float | None,
) -> float | None:
    """Return an equal-weight 0-100 score from available quality dimensions.

    Full-credit reference points are ROE 20%, net margin 15%, D/E 0, interest
    coverage 3x, and five-year CFO/PAT 1x. D/E reaches zero credit at 2x.
    """
    components: list[float] = []

    def add_scaled(value: float | None, target: float) -> None:
        number = _number(value)
        if number is not None:
            components.append(min(100.0, max(0.0, number / target * 100)))

    add_scaled(roe_pct, 20.0)
    add_scaled(net_margin_pct, 15.0)
    leverage = _number(debt_to_equity_ratio)
    if leverage is not None:
        components.append(min(100.0, max(0.0, (2.0 - leverage) / 2.0 * 100)))
    add_scaled(interest_coverage_ratio, 3.0)
    add_scaled(cfo_pat_score, 1.0)
    return sum(components) / len(components) if components else None


def _ensure_schema(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(financial_ratios)")}
    if "composite_quality_score" not in columns:
        connection.execute("ALTER TABLE financial_ratios ADD COLUMN composite_quality_score REAL")


def _latest_statements(
    connection: sqlite3.Connection,
) -> dict[str, dict[tuple[str, int], dict[str, Any]]]:
    statements: dict[str, dict[tuple[str, int], dict[str, Any]]] = defaultdict(dict)
    rows = connection.execute(
        "SELECT * FROM financial_statements WHERE year IS NOT NULL ORDER BY id"
    )
    for raw_row in rows:
        row = dict(raw_row)
        statements[row["statement_type"]][(row["company_id"], int(row["year"]))] = row
    return statements


def _history(
    rows: dict[tuple[str, int], dict[str, Any]],
    field: str,
) -> dict[str, dict[int, float | None]]:
    result: dict[str, dict[int, float | None]] = defaultdict(dict)
    for (company_id, year), row in rows.items():
        result[company_id][year] = _number(row.get(field))
    return result


def _flag(value: object) -> str | None:
    return None if value is None else str(value)


def populate_financial_ratios(connection: sqlite3.Connection) -> PopulationStats:
    """Populate all computed KPI fields and return final coverage statistics."""
    connection.row_factory = sqlite3.Row
    _ensure_schema(connection)
    before = connection.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]

    connection.execute(
        """
        INSERT INTO financial_ratios (company_id, year)
        SELECT DISTINCT f.company_id, f.year
        FROM financial_statements f
        WHERE f.year IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM financial_ratios r
              WHERE r.company_id = f.company_id AND r.year = f.year
          )
        """
    )

    statements = _latest_statements(connection)
    pnl_rows = statements.get("profit_and_loss", {})
    balance_rows = statements.get("balance_sheet", {})
    cash_rows = statements.get("cash_flow", {})
    sales_history = _history(pnl_rows, "sales")
    pat_history = _history(pnl_rows, "net_profit")
    eps_history = _history(pnl_rows, "eps")
    cfo_history = _history(cash_rows, "operating_activity")

    companies = {
        row["id"]: dict(row)
        for row in connection.execute("SELECT id, face_value FROM companies")
    }
    sectors = {
        row["company_id"]: row["broad_sector"]
        for row in connection.execute("SELECT company_id, broad_sector FROM sectors")
    }

    update_columns = [
        "net_profit_margin_pct",
        "operating_profit_margin_pct",
        "return_on_equity_pct",
        "return_on_capital_employed_pct",
        "return_on_assets_pct",
        "debt_to_equity",
        "high_leverage_flag",
        "interest_coverage",
        "icr_label",
        "icr_warning_flag",
        "net_debt",
        "asset_turnover",
        "revenue_cagr_3yr",
        "revenue_cagr_3yr_flag",
        "revenue_cagr_5yr",
        "revenue_cagr_5yr_flag",
        "revenue_cagr_10yr",
        "revenue_cagr_10yr_flag",
        "pat_cagr_3yr",
        "pat_cagr_3yr_flag",
        "pat_cagr_5yr",
        "pat_cagr_5yr_flag",
        "pat_cagr_10yr",
        "pat_cagr_10yr_flag",
        "eps_cagr_3yr",
        "eps_cagr_3yr_flag",
        "eps_cagr_5yr",
        "eps_cagr_5yr_flag",
        "eps_cagr_10yr",
        "eps_cagr_10yr_flag",
        "free_cash_flow_cr",
        "cfo_quality_score",
        "cfo_quality_label",
        "capex_cr",
        "capex_intensity_pct",
        "capex_intensity_label",
        "fcf_conversion_rate_pct",
        "capital_allocation_pattern",
        "earnings_per_share",
        "book_value_per_share",
        "dividend_payout_ratio_pct",
        "total_debt_cr",
        "cash_from_operations_cr",
        "composite_quality_score",
    ]
    assignments = ", ".join(f'"{column}" = ?' for column in update_columns)
    update_sql = f"UPDATE financial_ratios SET {assignments} WHERE id = ?"

    ratio_rows = connection.execute(
        "SELECT id, company_id, year FROM financial_ratios WHERE year IS NOT NULL ORDER BY id"
    ).fetchall()
    for ratio_row in ratio_rows:
        company_id = ratio_row["company_id"]
        year = int(ratio_row["year"])
        key = (company_id, year)
        pnl = pnl_rows.get(key, {})
        balance = balance_rows.get(key, {})
        cash = cash_rows.get(key, {})

        operating_profit = _number(pnl.get("operating_profit"))
        other_income = _number(pnl.get("other_income"))
        ebit = (
            operating_profit + other_income
            if operating_profit is not None and other_income is not None
            else None
        )
        profitability = calculate_profitability_ratios(
            net_profit=_number(pnl.get("net_profit")),
            sales=_number(pnl.get("sales")),
            operating_profit=operating_profit,
            opm_percentage=_number(pnl.get("opm_percentage")),
            equity_capital=_number(balance.get("equity_capital")),
            reserves=_number(balance.get("reserves")),
            borrowings=_number(balance.get("borrowings")),
            ebit=ebit,
            total_assets=_number(balance.get("total_assets")),
            company_id=company_id,
            year=year,
        )
        leverage = calculate_leverage_efficiency_ratios(
            borrowings=_number(balance.get("borrowings")),
            equity_capital=_number(balance.get("equity_capital")),
            reserves=_number(balance.get("reserves")),
            broad_sector=sectors.get(company_id),
            operating_profit=operating_profit,
            other_income=other_income,
            interest=_number(pnl.get("interest")),
            investments=_number(balance.get("investments")),
            sales=_number(pnl.get("sales")),
            total_assets=_number(balance.get("total_assets")),
        )
        growth = calculate_growth_cagrs(
            revenue_history=sales_history.get(company_id, {}),
            pat_history=pat_history.get(company_id, {}),
            eps_history=eps_history.get(company_id, {}),
            end_year=year,
        )

        cfo = _number(cash.get("operating_activity"))
        cfi = _number(cash.get("investing_activity"))
        cff = _number(cash.get("financing_activity"))
        fcf = free_cash_flow(cfo, cfi)
        cfo_values = [
            cfo_history.get(company_id, {}).get(item) for item in range(year - 4, year + 1)
        ]
        pat_values = [
            pat_history.get(company_id, {}).get(item) for item in range(year - 4, year + 1)
        ]
        cfo_score = cfo_quality_score(cfo_values, pat_values)
        intensity = capex_intensity(cfi, _number(pnl.get("sales")))
        annual_cfo_pat = None
        pat = _number(pnl.get("net_profit"))
        if cfo is not None and pat not in (None, 0):
            annual_cfo_pat = cfo / pat
        allocation = classify_capital_allocation(cfo, cfi, cff, cfo_pat_ratio=annual_cfo_pat)
        margin = net_profit_margin(pat, _number(pnl.get("sales")))
        composite = composite_quality_score(
            roe_pct=profitability.return_on_equity_pct,
            net_margin_pct=margin,
            debt_to_equity_ratio=leverage.debt_to_equity,
            interest_coverage_ratio=leverage.interest_coverage,
            cfo_pat_score=cfo_score,
        )

        values = {
            "net_profit_margin_pct": profitability.net_profit_margin_pct,
            "operating_profit_margin_pct": profitability.operating_profit_margin_pct,
            "return_on_equity_pct": profitability.return_on_equity_pct,
            "return_on_capital_employed_pct": profitability.return_on_capital_employed_pct,
            "return_on_assets_pct": profitability.return_on_assets_pct,
            "debt_to_equity": leverage.debt_to_equity,
            "high_leverage_flag": int(leverage.high_leverage_flag),
            "interest_coverage": leverage.interest_coverage,
            "icr_label": leverage.icr_label,
            "icr_warning_flag": int(leverage.icr_warning_flag),
            "net_debt": leverage.net_debt,
            "asset_turnover": leverage.asset_turnover,
            "revenue_cagr_3yr": growth.revenue_cagr_3yr,
            "revenue_cagr_3yr_flag": _flag(growth.revenue_cagr_3yr_flag),
            "revenue_cagr_5yr": growth.revenue_cagr_5yr,
            "revenue_cagr_5yr_flag": _flag(growth.revenue_cagr_5yr_flag),
            "revenue_cagr_10yr": growth.revenue_cagr_10yr,
            "revenue_cagr_10yr_flag": _flag(growth.revenue_cagr_10yr_flag),
            "pat_cagr_3yr": growth.pat_cagr_3yr,
            "pat_cagr_3yr_flag": _flag(growth.pat_cagr_3yr_flag),
            "pat_cagr_5yr": growth.pat_cagr_5yr,
            "pat_cagr_5yr_flag": _flag(growth.pat_cagr_5yr_flag),
            "pat_cagr_10yr": growth.pat_cagr_10yr,
            "pat_cagr_10yr_flag": _flag(growth.pat_cagr_10yr_flag),
            "eps_cagr_3yr": growth.eps_cagr_3yr,
            "eps_cagr_3yr_flag": _flag(growth.eps_cagr_3yr_flag),
            "eps_cagr_5yr": growth.eps_cagr_5yr,
            "eps_cagr_5yr_flag": _flag(growth.eps_cagr_5yr_flag),
            "eps_cagr_10yr": growth.eps_cagr_10yr,
            "eps_cagr_10yr_flag": _flag(growth.eps_cagr_10yr_flag),
            "free_cash_flow_cr": fcf,
            "cfo_quality_score": cfo_score,
            "cfo_quality_label": classify_cfo_quality(cfo_score),
            "capex_cr": abs(cfi) if cfi is not None else None,
            "capex_intensity_pct": intensity,
            "capex_intensity_label": classify_capex_intensity(intensity),
            "fcf_conversion_rate_pct": fcf_conversion_rate(fcf, operating_profit),
            "capital_allocation_pattern": allocation,
            "earnings_per_share": _number(pnl.get("eps")),
            "book_value_per_share": book_value_per_share(
                _number(balance.get("equity_capital")),
                _number(balance.get("reserves")),
                _number(companies.get(company_id, {}).get("face_value")),
            ),
            "dividend_payout_ratio_pct": _number(pnl.get("dividend_payout")),
            "total_debt_cr": _number(balance.get("borrowings")),
            "cash_from_operations_cr": cfo,
            "composite_quality_score": composite,
        }
        connection.execute(
            update_sql,
            [values[column] for column in update_columns] + [ratio_row["id"]],
        )

    final = connection.execute(
        "SELECT COUNT(*), COUNT(DISTINCT company_id) FROM financial_ratios"
    ).fetchone()
    return PopulationStats(final[0], final[1], final[0] - before)


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate all financial ratio KPIs")
    parser.add_argument("--database", default="nifty100.db")
    args = parser.parse_args()
    connection = sqlite3.connect(Path(args.database))
    try:
        with connection:
            stats = populate_financial_ratios(connection)
    finally:
        connection.close()
    print(
        f"Populated {stats.rows:,} ratio rows across {stats.companies} companies "
        f"({stats.inserted_rows} rows inserted)"
    )


if __name__ == "__main__":
    main()
