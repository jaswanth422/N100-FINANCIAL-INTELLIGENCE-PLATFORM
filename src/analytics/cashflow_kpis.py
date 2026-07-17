"""Public Day 11 cash-flow KPI API.

The implementation remains in :mod:`analytics.cashflow` for backwards
compatibility; this module provides the Sprint 2 deliverable path.
"""

from .cashflow import (
    capex_intensity,
    cfo_quality_score,
    classify_capex_intensity,
    classify_cfo_quality,
    fcf_conversion_rate,
    free_cash_flow,
)

__all__ = [
    "capex_intensity",
    "cfo_quality_score",
    "classify_capex_intensity",
    "classify_cfo_quality",
    "fcf_conversion_rate",
    "free_cash_flow",
]
