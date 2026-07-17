import csv

import pytest

from analytics.cashflow import (
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


def test_free_cash_flow_allows_negative_results():
    assert free_cash_flow(100, -60) == pytest.approx(40)
    assert free_cash_flow(100, -160) == pytest.approx(-60)


def test_free_cash_flow_rejects_missing_inputs():
    assert free_cash_flow(None, -60) is None


def test_five_year_cfo_quality_score_and_high_quality_label():
    score = cfo_quality_score([120, 110, 130, 125, 115], [100, 100, 100, 100, 100])
    assert score == pytest.approx(1.2)
    assert classify_cfo_quality(score) == "High Quality"


def test_cfo_quality_classification_boundaries():
    assert classify_cfo_quality(1.0) == "Moderate"
    assert classify_cfo_quality(0.5) == "Moderate"
    assert classify_cfo_quality(0.49) == "Accrual Risk"


def test_cfo_quality_returns_none_for_zero_pat_or_less_than_five_years():
    assert cfo_quality_score([1, 1, 1, 1, 1], [1, 1, 0, 1, 1]) is None
    assert cfo_quality_score([1, 1, 1, 1], [1, 1, 1, 1]) is None


def test_capex_intensity_and_labels():
    assert capex_intensity(-30, 1_000) == pytest.approx(3.0)
    assert classify_capex_intensity(2.99) == "Asset Light"
    assert classify_capex_intensity(3.0) == "Moderate"
    assert classify_capex_intensity(8.0) == "Moderate"
    assert classify_capex_intensity(8.01) == "Capital Intensive"


def test_capex_intensity_returns_none_for_zero_sales():
    assert capex_intensity(-30, 0) is None


def test_fcf_conversion_rate_and_zero_operating_profit():
    assert fcf_conversion_rate(40, 80) == pytest.approx(50.0)
    assert fcf_conversion_rate(-40, 80) == pytest.approx(-50.0)
    assert fcf_conversion_rate(40, 0) is None


@pytest.mark.parametrize(
    ("cash_flows", "expected"),
    [
        ((10, -5, -2), "Reinvestor"),
        ((10, 5, -2), "Liquidating Assets"),
        ((-10, 5, 2), "Distress Signal"),
        ((-10, -5, 2), "Growth Funded by Debt"),
        ((10, 5, 2), "Cash Accumulator"),
        ((-10, -5, -2), "Pre-Revenue"),
        ((10, -5, 2), "Mixed"),
        ((-10, 5, -2), "Mixed"),
    ],
)
def test_all_cash_flow_sign_patterns(cash_flows, expected):
    assert classify_capital_allocation(*cash_flows) == expected


def test_shareholder_returns_override_and_csv_schema(tmp_path):
    assert classify_capital_allocation(120, -40, -30, cfo_pat_ratio=1.2) == (
        "Shareholder Returns"
    )
    row = build_capital_allocation_row(
        company_id="ABC",
        year=2025,
        operating_activity=120,
        investing_activity=-40,
        financing_activity=-30,
        net_profit=100,
    )
    path = write_capital_allocation_csv([row], tmp_path / "capital_allocation.csv")
    with path.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    assert list(records[0]) == [
        "company_id",
        "year",
        "cfo_sign",
        "cfi_sign",
        "cff_sign",
        "pattern_label",
    ]
    assert records[0]["pattern_label"] == "Shareholder Returns"
