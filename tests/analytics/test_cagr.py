import pytest

from analytics.cagr import (
    CAGRFlag,
    calculate_cagr,
    calculate_cagr_windows,
    calculate_growth_cagrs,
)


def _history(start: float, growth_rate: float) -> dict[int, float]:
    return {year: start * (1 + growth_rate) ** (year - 2015) for year in range(2015, 2026)}


def test_normal_cagr():
    result = calculate_cagr(100, 133.1, 3)
    assert result.value == pytest.approx(10.0)
    assert result.flag is None


def test_turnaround_flag():
    result = calculate_cagr(-100, 125, 3)
    assert result.value is None
    assert result.flag == CAGRFlag.TURNAROUND


def test_decline_to_loss_flag():
    result = calculate_cagr(100, -25, 3)
    assert result.value is None
    assert result.flag == CAGRFlag.DECLINE_TO_LOSS


def test_both_negative_flag():
    result = calculate_cagr(-100, -50, 3)
    assert result.value is None
    assert result.flag == CAGRFlag.BOTH_NEGATIVE


def test_zero_base_flag():
    result = calculate_cagr(0, 100, 3)
    assert result.value is None
    assert result.flag == CAGRFlag.ZERO_BASE


def test_insufficient_data_flag_for_unavailable_windows():
    results = calculate_cagr_windows({2023: 100, 2024: 110, 2025: 121})
    assert all(result.value is None for result in results.values())
    assert all(result.flag == CAGRFlag.INSUFFICIENT for result in results.values())


def test_revenue_cagr_for_3_5_and_10_year_windows():
    results = calculate_cagr_windows(_history(100, 0.10), end_year=2025)
    assert [results[window].value for window in (3, 5, 10)] == pytest.approx(
        [10.0, 10.0, 10.0]
    )


def test_pat_cagr_for_3_5_and_10_year_windows():
    results = calculate_cagr_windows(_history(50, 0.20), end_year=2025)
    assert [results[window].value for window in (3, 5, 10)] == pytest.approx(
        [20.0, 20.0, 20.0]
    )


def test_eps_cagr_for_3_5_and_10_year_windows():
    results = calculate_cagr_windows(_history(10, 0.05), end_year=2025)
    assert [results[window].value for window in (3, 5, 10)] == pytest.approx(
        [5.0, 5.0, 5.0]
    )


def test_all_growth_metrics_expose_separate_value_and_flag_fields():
    metrics = calculate_growth_cagrs(
        revenue_history=_history(100, 0.10),
        pat_history={2020: 20, 2025: -5},
        eps_history={2025: 12},
        end_year=2025,
    )

    assert metrics.revenue_cagr_5yr == pytest.approx(10.0)
    assert metrics.revenue_cagr_5yr_flag is None
    assert metrics.pat_cagr_5yr is None
    assert metrics.pat_cagr_5yr_flag == CAGRFlag.DECLINE_TO_LOSS
    assert metrics.eps_cagr_5yr is None
    assert metrics.eps_cagr_5yr_flag == CAGRFlag.INSUFFICIENT
