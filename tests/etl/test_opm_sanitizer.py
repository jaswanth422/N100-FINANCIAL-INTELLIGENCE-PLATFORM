"""Regression test: INDIGO OPM cross-check mismatch (₹ crore in opm_percentage)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from nifty100_etl.loader import (
    OPM_PERCENTAGE_MAX,
    OPM_PERCENTAGE_MIN,
    ExcelSource,
    load_excel,
    sanitize_opm_percentage,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFIT_LOSS_XLSX = REPO_ROOT / "profitandloss.xlsx"


def test_in_range_values_are_preserved() -> None:
    frame = pd.DataFrame({"opm_percentage": [29.0, 8.0, -5.0, 100.0, -100.0, None]})
    nulled = sanitize_opm_percentage(frame)
    assert nulled == 0
    assert frame["opm_percentage"].tolist()[:5] == [29.0, 8.0, -5.0, 100.0, -100.0]
    assert pd.isna(frame["opm_percentage"].iloc[5])


def test_out_of_range_values_are_nulled() -> None:
    frame = pd.DataFrame(
        {"opm_percentage": [29.0, 855.0, -200.0, 101.0, OPM_PERCENTAGE_MAX + 0.01]}
    )
    nulled = sanitize_opm_percentage(frame)
    assert nulled == 4
    assert frame["opm_percentage"].iloc[0] == 29.0
    assert frame["opm_percentage"].iloc[1:].isna().all()


def test_missing_column_is_no_op() -> None:
    frame = pd.DataFrame({"sales": [100, 200]})
    nulled = sanitize_opm_percentage(frame)
    assert nulled == 0


def test_non_numeric_entries_are_left_alone() -> None:
    frame = pd.DataFrame({"opm_percentage": ["", "n/a", None, 25.0]})
    nulled = sanitize_opm_percentage(frame)
    assert nulled == 0
    assert frame["opm_percentage"].iloc[3] == 25.0


def test_boundary_values_are_preserved() -> None:
    frame = pd.DataFrame({"opm_percentage": [OPM_PERCENTAGE_MIN, OPM_PERCENTAGE_MAX]})
    nulled = sanitize_opm_percentage(frame)
    assert nulled == 0


@pytest.mark.skipif(
    not PROFIT_LOSS_XLSX.is_file(),
    reason="profitandloss.xlsx not present in repo root",
)
def test_indigo_opm_nulled_after_load() -> None:
    """End-to-end: loading profitandloss.xlsx must null INDIGO's bad OPM cells.

    Prior to the fix, INDIGO's opm_percentage column held ₹-crore operating
    profit (e.g. 855 for FY2013), which triggered a misleading OPM cross-check
    warning and leaked a nonsensical "reported" value into the dashboard.
    After sanitation, every INDIGO opm_percentage cell should be null.
    """
    source = ExcelSource(PROFIT_LOSS_XLSX, "financial_statements", "profit_and_loss")
    frame = load_excel(source)

    indigo = frame.loc[frame["company_id"] == "INDIGO"]
    assert len(indigo) > 0, "INDIGO rows missing from profitandloss.xlsx fixture"

    opm = pd.to_numeric(indigo["opm_percentage"], errors="coerce")
    out_of_range = opm.notna() & ~opm.between(OPM_PERCENTAGE_MIN, OPM_PERCENTAGE_MAX)
    assert not out_of_range.any(), (
        "No INDIGO opm_percentage should remain outside "
        f"[{OPM_PERCENTAGE_MIN}, {OPM_PERCENTAGE_MAX}] after sanitation; "
        f"got {indigo.loc[out_of_range, 'opm_percentage'].tolist()}"
    )
    # The known-bad historical rows (FY2013-FY2020, each > 100) must be nulled.
    assert opm.isna().sum() >= 8, (
        "At least the eight pre-fix INDIGO rows should be nulled; "
        f"only {opm.isna().sum()} are null"
    )

    tcs = frame.loc[frame["company_id"] == "TCS"]
    assert tcs["opm_percentage"].between(OPM_PERCENTAGE_MIN, OPM_PERCENTAGE_MAX).all(), (
        "TCS opm_percentage should remain unchanged after sanitation"
    )
