"""Profitability, leverage, and efficiency ratio calculations.

All percentage-returning functions return percentage points (for example, ``12.5``
rather than ``0.125``). Missing inputs and unusable denominators produce ``None``
so callers can persist SQL ``NULL`` instead of a misleading zero.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from numbers import Real

LOGGER = logging.getLogger(__name__)
OPM_MISMATCH_TOLERANCE_PCT = 1.0
FINANCIALS_SECTOR = "financials"
HIGH_LEVERAGE_THRESHOLD = 5.0
ICR_WARNING_THRESHOLD = 1.5
DEBT_FREE_LABEL = "Debt Free"


def _number(value: object) -> float | None:
    """Return a finite float, or ``None`` for missing/non-finite input."""
    if value is None or isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def net_profit_margin(net_profit: Real | None, sales: Real | None) -> float | None:
    """Calculate net profit / sales * 100; return ``None`` for zero sales."""
    profit = _number(net_profit)
    revenue = _number(sales)
    if profit is None or revenue is None or revenue == 0:
        return None
    return profit / revenue * 100


def operating_profit_margin(
    operating_profit: Real | None,
    sales: Real | None,
    opm_percentage: Real | None = None,
    *,
    company_id: str | None = None,
    year: int | None = None,
) -> float | None:
    """Calculate OPM and warn when the reported OPM differs by over one point.

    ``opm_percentage`` is a cross-check only: the value returned is always computed
    from operating profit and sales.
    """
    profit = _number(operating_profit)
    revenue = _number(sales)
    if profit is None or revenue is None or revenue == 0:
        return None

    computed = profit / revenue * 100
    reported = _number(opm_percentage)
    if reported is not None and abs(computed - reported) > OPM_MISMATCH_TOLERANCE_PCT:
        LOGGER.warning(
            "OPM cross-check mismatch company_id=%s year=%s computed=%.4f reported=%.4f "
            "difference=%.4f",
            company_id,
            year,
            computed,
            reported,
            abs(computed - reported),
        )
    return computed


def return_on_equity(
    net_profit: Real | None,
    equity_capital: Real | None,
    reserves: Real | None,
) -> float | None:
    """Calculate ROE; non-positive shareholder equity is not meaningful."""
    profit = _number(net_profit)
    equity = _number(equity_capital)
    retained = _number(reserves)
    if profit is None or equity is None or retained is None:
        return None
    shareholder_equity = equity + retained
    if shareholder_equity <= 0:
        return None
    return profit / shareholder_equity * 100


def return_on_capital_employed(
    ebit: Real | None,
    equity_capital: Real | None,
    reserves: Real | None,
    borrowings: Real | None,
) -> float | None:
    """Calculate EBIT / (equity capital + reserves + borrowings) * 100."""
    earnings = _number(ebit)
    equity = _number(equity_capital)
    retained = _number(reserves)
    debt = _number(borrowings)
    if earnings is None or equity is None or retained is None or debt is None:
        return None
    capital_employed = equity + retained + debt
    if capital_employed <= 0:
        return None
    return earnings / capital_employed * 100


def return_on_assets(net_profit: Real | None, total_assets: Real | None) -> float | None:
    """Calculate net profit / total assets * 100; return ``None`` for zero assets."""
    profit = _number(net_profit)
    assets = _number(total_assets)
    if profit is None or assets is None or assets == 0:
        return None
    return profit / assets * 100


def meets_roce_benchmark(
    roce_percentage: Real | None,
    broad_sector: str | None,
    *,
    absolute_threshold: float = 15.0,
    sector_relative_benchmark: Real | None = None,
) -> bool | None:
    """Evaluate ROCE using a sector benchmark for Financials.

    Financial companies cannot be fairly assessed with the general absolute ROCE
    threshold. For them, no verdict is returned until a sector-relative benchmark
    (for example the Financials median for that year) is supplied.
    """
    roce = _number(roce_percentage)
    if roce is None:
        return None

    is_financial = (broad_sector or "").strip().casefold() == FINANCIALS_SECTOR
    benchmark = _number(sector_relative_benchmark if is_financial else absolute_threshold)
    if benchmark is None:
        return None
    return roce >= benchmark


def debt_to_equity(
    borrowings: Real | None,
    equity_capital: Real | None,
    reserves: Real | None,
) -> float | None:
    """Calculate borrowings / shareholder equity.

    A company with zero borrowings has a ratio of zero even when its equity inputs
    would otherwise make the denominator unusable.
    """
    debt = _number(borrowings)
    if debt is None:
        return None
    if debt == 0:
        return 0.0

    equity = _number(equity_capital)
    retained = _number(reserves)
    if equity is None or retained is None:
        return None
    shareholder_equity = equity + retained
    if shareholder_equity <= 0:
        return None
    return debt / shareholder_equity


def is_high_leverage(
    debt_to_equity_ratio: Real | None,
    broad_sector: str | None,
) -> bool:
    """Flag D/E above 5, except for companies in the Financials sector."""
    ratio = _number(debt_to_equity_ratio)
    is_financial = (broad_sector or "").strip().casefold() == FINANCIALS_SECTOR
    return ratio is not None and ratio > HIGH_LEVERAGE_THRESHOLD and not is_financial


def interest_coverage_ratio(
    operating_profit: Real | None,
    other_income: Real | None,
    interest: Real | None,
) -> float | None:
    """Calculate (operating profit + other income) / interest.

    Zero interest represents a debt-free company and produces ``None`` rather than
    an infinite ratio.
    """
    profit = _number(operating_profit)
    income = _number(other_income)
    interest_expense = _number(interest)
    if profit is None or income is None or interest_expense is None or interest_expense == 0:
        return None
    return (profit + income) / interest_expense


def interest_coverage_label(interest_coverage: Real | None) -> str | None:
    """Return the display label used when an ICR value is absent."""
    return DEBT_FREE_LABEL if _number(interest_coverage) is None else None


def has_icr_warning(interest_coverage: Real | None) -> bool:
    """Flag companies whose ICR is below the 1.5 coverage threshold."""
    ratio = _number(interest_coverage)
    return ratio is not None and ratio < ICR_WARNING_THRESHOLD


def net_debt(borrowings: Real | None, investments: Real | None) -> float | None:
    """Calculate borrowings less investments, used as a liquid-asset proxy."""
    debt = _number(borrowings)
    liquid_assets = _number(investments)
    if debt is None or liquid_assets is None:
        return None
    return debt - liquid_assets


def asset_turnover(sales: Real | None, total_assets: Real | None) -> float | None:
    """Calculate sales / total assets; return ``None`` for zero assets."""
    revenue = _number(sales)
    assets = _number(total_assets)
    if revenue is None or assets is None or assets == 0:
        return None
    return revenue / assets


@dataclass(frozen=True)
class ProfitabilityRatios:
    """The five Day 08 profitability outputs for one company-year."""

    net_profit_margin_pct: float | None
    operating_profit_margin_pct: float | None
    return_on_equity_pct: float | None
    return_on_capital_employed_pct: float | None
    return_on_assets_pct: float | None


@dataclass(frozen=True)
class LeverageEfficiencyRatios:
    """The Day 09 leverage and efficiency outputs for one company-year."""

    debt_to_equity: float | None
    high_leverage_flag: bool
    interest_coverage: float | None
    icr_label: str | None
    icr_warning_flag: bool
    net_debt: float | None
    asset_turnover: float | None


def calculate_profitability_ratios(
    *,
    net_profit: Real | None,
    sales: Real | None,
    operating_profit: Real | None,
    opm_percentage: Real | None,
    equity_capital: Real | None,
    reserves: Real | None,
    borrowings: Real | None,
    ebit: Real | None,
    total_assets: Real | None,
    company_id: str | None = None,
    year: int | None = None,
) -> ProfitabilityRatios:
    """Calculate all Day 08 profitability ratios for one company-year."""
    return ProfitabilityRatios(
        net_profit_margin_pct=net_profit_margin(net_profit, sales),
        operating_profit_margin_pct=operating_profit_margin(
            operating_profit,
            sales,
            opm_percentage,
            company_id=company_id,
            year=year,
        ),
        return_on_equity_pct=return_on_equity(net_profit, equity_capital, reserves),
        return_on_capital_employed_pct=return_on_capital_employed(
            ebit, equity_capital, reserves, borrowings
        ),
        return_on_assets_pct=return_on_assets(net_profit, total_assets),
    )


def calculate_leverage_efficiency_ratios(
    *,
    borrowings: Real | None,
    equity_capital: Real | None,
    reserves: Real | None,
    broad_sector: str | None,
    operating_profit: Real | None,
    other_income: Real | None,
    interest: Real | None,
    investments: Real | None,
    sales: Real | None,
    total_assets: Real | None,
) -> LeverageEfficiencyRatios:
    """Calculate all Day 09 leverage and efficiency outputs."""
    leverage = debt_to_equity(borrowings, equity_capital, reserves)
    coverage = interest_coverage_ratio(operating_profit, other_income, interest)
    return LeverageEfficiencyRatios(
        debt_to_equity=leverage,
        high_leverage_flag=is_high_leverage(leverage, broad_sector),
        interest_coverage=coverage,
        icr_label=interest_coverage_label(coverage),
        icr_warning_flag=has_icr_warning(coverage),
        net_debt=net_debt(borrowings, investments),
        asset_turnover=asset_turnover(sales, total_assets),
    )
