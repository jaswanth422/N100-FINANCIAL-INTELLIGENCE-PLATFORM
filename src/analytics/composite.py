"""Sector-relative composite quality scoring.

Every continuous input is winsorised at its sector's 10th and 90th
percentiles and then mapped to a 0-100 score.  This keeps a single outlier from
dominating the result and makes comparisons meaningful across different
business models.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MetricSpec:
    """Configuration for one weighted composite-score input."""

    name: str
    column: str
    weight: float
    inverse: bool = False


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("roe", "return_on_equity_pct", 0.15),
    MetricSpec("roce", "return_on_capital_employed_pct", 0.10),
    MetricSpec("net_profit_margin", "net_profit_margin_pct", 0.10),
    MetricSpec("fcf_cagr_5yr", "fcf_cagr_5yr", 0.15),
    MetricSpec("cfo_pat_ratio", "cfo_quality_score", 0.10),
    MetricSpec("fcf_positive", "fcf_positive_flag", 0.05),
    MetricSpec("revenue_cagr_5yr", "revenue_cagr_5yr", 0.10),
    MetricSpec("pat_cagr_5yr", "pat_cagr_5yr", 0.10),
    MetricSpec("debt_to_equity", "debt_to_equity", 0.10, inverse=True),
    MetricSpec("interest_coverage", "interest_coverage", 0.05),
)

TOTAL_WEIGHT = sum(spec.weight for spec in METRIC_SPECS)
if not np.isclose(TOTAL_WEIGHT, 1.0):  # pragma: no cover - guards configuration edits
    raise RuntimeError(f"Composite metric weights total {TOTAL_WEIGHT}, expected 1.0")


def winsorised_scale(
    values: pd.Series,
    *,
    inverse: bool = False,
    lower_quantile: float = 0.10,
    upper_quantile: float = 0.90,
) -> pd.Series:
    """Winsorise a series at P10/P90 and scale valid values to 0-100.

    A peer set with no dispersion has no relative winner, so every valid value
    receives the neutral score of 50. Missing and infinite values remain
    missing and are handled transparently by the composite coverage calculation.
    """
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    valid = numeric.dropna()
    result = pd.Series(np.nan, index=values.index, dtype="float64")
    if valid.empty:
        return result

    p10 = float(valid.quantile(lower_quantile))
    p90 = float(valid.quantile(upper_quantile))
    if np.isclose(p10, p90):
        result.loc[valid.index] = 50.0
        return result

    capped = numeric.clip(lower=p10, upper=p90)
    scaled = (capped - p10) / (p90 - p10) * 100.0
    result = 100.0 - scaled if inverse else scaled
    return result.clip(0.0, 100.0)


def compute_composite_scores(
    frame: pd.DataFrame,
    *,
    sector_column: str = "broad_sector",
    include_components: bool = False,
) -> pd.DataFrame:
    """Return ``frame`` with a sector-relative composite score on a 0-100 scale.

    Missing inputs are not silently treated as poor performance. The weighted
    score is divided by the weight of available components, and
    ``composite_score_coverage_pct`` records how much of the requested model was
    observed. A missing sector is grouped with other unclassified companies.
    """
    result = frame.copy()
    if sector_column not in result:
        result[sector_column] = "Unclassified"
    sectors = result[sector_column].astype("string").fillna("Unclassified")

    fcf_column = "free_cash_flow_cr"
    if "fcf_positive_flag" not in result:
        fcf_source = (
            result[fcf_column]
            if fcf_column in result
            else pd.Series(np.nan, index=result.index, dtype="float64")
        )
        fcf = pd.to_numeric(fcf_source, errors="coerce")
        result["fcf_positive_flag"] = fcf.gt(0).where(fcf.notna()).astype("Float64")

    weighted_total = pd.Series(0.0, index=result.index)
    available_weight = pd.Series(0.0, index=result.index)
    component_columns: list[str] = []

    for spec in METRIC_SPECS:
        raw = (
            result[spec.column]
            if spec.column in result
            else pd.Series(np.nan, index=result.index, dtype="float64")
        )
        component = raw.groupby(sectors, dropna=False).transform(
            lambda group, inverse=spec.inverse: winsorised_scale(group, inverse=inverse)
        )
        component_column = f"{spec.name}_score"
        result[component_column] = component
        component_columns.append(component_column)
        present = component.notna()
        weighted_total = weighted_total.add(component.fillna(0.0) * spec.weight)
        available_weight = available_weight.add(present.astype(float) * spec.weight)

    result["composite_quality_score"] = weighted_total.div(
        available_weight.where(available_weight.gt(0))
    ).clip(0.0, 100.0)
    result["composite_score_coverage_pct"] = available_weight * 100.0

    if not include_components:
        result = result.drop(columns=component_columns)
    return result


__all__ = [
    "METRIC_SPECS",
    "MetricSpec",
    "compute_composite_scores",
    "winsorised_scale",
]
