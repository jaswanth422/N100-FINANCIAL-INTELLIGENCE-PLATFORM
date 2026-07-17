"""Compound annual growth rate calculations for financial histories."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real

CAGR_WINDOWS = (3, 5, 10)


class CAGRFlag(StrEnum):
    """Reasons why a CAGR value could not be calculated."""

    DECLINE_TO_LOSS = "DECLINE_TO_LOSS"
    TURNAROUND = "TURNAROUND"
    BOTH_NEGATIVE = "BOTH_NEGATIVE"
    ZERO_BASE = "ZERO_BASE"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class CAGRResult:
    """A CAGR percentage and its optional exception flag."""

    value: float | None
    flag: CAGRFlag | None = None


@dataclass(frozen=True)
class GrowthCAGRs:
    """Revenue, PAT, and EPS CAGR values ready for persistence."""

    revenue_cagr_3yr: float | None
    revenue_cagr_3yr_flag: CAGRFlag | None
    revenue_cagr_5yr: float | None
    revenue_cagr_5yr_flag: CAGRFlag | None
    revenue_cagr_10yr: float | None
    revenue_cagr_10yr_flag: CAGRFlag | None
    pat_cagr_3yr: float | None
    pat_cagr_3yr_flag: CAGRFlag | None
    pat_cagr_5yr: float | None
    pat_cagr_5yr_flag: CAGRFlag | None
    pat_cagr_10yr: float | None
    pat_cagr_10yr_flag: CAGRFlag | None
    eps_cagr_3yr: float | None
    eps_cagr_3yr_flag: CAGRFlag | None
    eps_cagr_5yr: float | None
    eps_cagr_5yr_flag: CAGRFlag | None
    eps_cagr_10yr: float | None
    eps_cagr_10yr_flag: CAGRFlag | None


def _number(value: object) -> float | None:
    """Return a finite number while rejecting booleans and missing values."""
    if value is None or isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def calculate_cagr(
    start_value: Real | None,
    end_value: Real | None,
    years: int,
) -> CAGRResult:
    """Calculate ``((end / start) ** (1 / years) - 1) * 100``.

    CAGR is intentionally not calculated across a sign change or when both
    endpoints are negative because those results are economically misleading.
    """
    if isinstance(years, bool) or not isinstance(years, int) or years <= 0:
        raise ValueError("years must be a positive integer")

    start = _number(start_value)
    end = _number(end_value)
    if start is None or end is None:
        return CAGRResult(None, CAGRFlag.INSUFFICIENT)
    if start == 0:
        return CAGRResult(None, CAGRFlag.ZERO_BASE)
    if start > 0 and end < 0:
        return CAGRResult(None, CAGRFlag.DECLINE_TO_LOSS)
    if start < 0 and end > 0:
        return CAGRResult(None, CAGRFlag.TURNAROUND)
    if start < 0 and end < 0:
        return CAGRResult(None, CAGRFlag.BOTH_NEGATIVE)
    if start < 0 and end == 0:
        return CAGRResult(None, CAGRFlag.TURNAROUND)

    return CAGRResult(((end / start) ** (1 / years) - 1) * 100)


def calculate_cagr_windows(
    history: Mapping[int, Real | None],
    *,
    end_year: int | None = None,
) -> dict[int, CAGRResult]:
    """Calculate 3-, 5-, and 10-year CAGR from an annual value history.

    A window is insufficient unless both its exact start-year and end-year values
    are present. Intermediate values are not required by the CAGR formula.
    """
    if end_year is None:
        if not history:
            return {
                window: CAGRResult(None, CAGRFlag.INSUFFICIENT)
                for window in CAGR_WINDOWS
            }
        end_year = max(history)

    end_value = history.get(end_year)
    results: dict[int, CAGRResult] = {}
    for window in CAGR_WINDOWS:
        start_year = end_year - window
        if start_year not in history or end_year not in history:
            results[window] = CAGRResult(None, CAGRFlag.INSUFFICIENT)
        else:
            results[window] = calculate_cagr(history[start_year], end_value, window)
    return results


def calculate_growth_cagrs(
    *,
    revenue_history: Mapping[int, Real | None],
    pat_history: Mapping[int, Real | None],
    eps_history: Mapping[int, Real | None],
    end_year: int | None = None,
) -> GrowthCAGRs:
    """Calculate every Day 10 CAGR value and flag for a company."""
    if end_year is None:
        available_years = set(revenue_history) | set(pat_history) | set(eps_history)
        end_year = max(available_years) if available_years else 0

    revenue = calculate_cagr_windows(revenue_history, end_year=end_year)
    pat = calculate_cagr_windows(pat_history, end_year=end_year)
    eps = calculate_cagr_windows(eps_history, end_year=end_year)

    return GrowthCAGRs(
        revenue_cagr_3yr=revenue[3].value,
        revenue_cagr_3yr_flag=revenue[3].flag,
        revenue_cagr_5yr=revenue[5].value,
        revenue_cagr_5yr_flag=revenue[5].flag,
        revenue_cagr_10yr=revenue[10].value,
        revenue_cagr_10yr_flag=revenue[10].flag,
        pat_cagr_3yr=pat[3].value,
        pat_cagr_3yr_flag=pat[3].flag,
        pat_cagr_5yr=pat[5].value,
        pat_cagr_5yr_flag=pat[5].flag,
        pat_cagr_10yr=pat[10].value,
        pat_cagr_10yr_flag=pat[10].flag,
        eps_cagr_3yr=eps[3].value,
        eps_cagr_3yr_flag=eps[3].flag,
        eps_cagr_5yr=eps[5].value,
        eps_cagr_5yr_flag=eps[5].flag,
        eps_cagr_10yr=eps[10].value,
        eps_cagr_10yr_flag=eps[10].flag,
    )
