"""Sprint 2 acceptance suite: exactly 20 KPI formula tests."""

import pytest

from analytics.cagr import CAGRFlag, calculate_cagr, calculate_cagr_windows
from analytics.cashflow_kpis import (
    capex_intensity,
    cfo_quality_score,
    fcf_conversion_rate,
    free_cash_flow,
)
from analytics.cashflow import classify_capital_allocation
from analytics.ratios import (
    asset_turnover,
    debt_to_equity,
    interest_coverage_ratio,
    is_high_leverage,
    net_debt,
    net_profit_margin,
    operating_profit_margin,
    return_on_assets,
    return_on_capital_employed,
    return_on_equity,
)


def test_01_net_profit_margin():
    assert net_profit_margin(25, 200) == pytest.approx(12.5)


def test_02_operating_profit_margin():
    assert operating_profit_margin(40, 200) == pytest.approx(20.0)


def test_03_return_on_equity():
    assert return_on_equity(30, 40, 60) == pytest.approx(30.0)


def test_04_return_on_capital_employed():
    assert return_on_capital_employed(24, 40, 40, 40) == pytest.approx(20.0)


def test_05_return_on_assets():
    assert return_on_assets(18, 120) == pytest.approx(15.0)


def test_06_debt_to_equity_and_debt_free_case():
    assert debt_to_equity(50, 20, 30) == pytest.approx(1.0)
    assert debt_to_equity(0, 0, 0) == 0


def test_07_financials_high_leverage_suppression():
    assert is_high_leverage(6, "Industrials") is True
    assert is_high_leverage(6, "Financials") is False


def test_08_interest_coverage():
    assert interest_coverage_ratio(100, 20, 40) == pytest.approx(3.0)
    assert interest_coverage_ratio(100, 20, 0) is None


def test_09_net_debt():
    assert net_debt(100, 35) == pytest.approx(65.0)


def test_10_asset_turnover():
    assert asset_turnover(250, 500) == pytest.approx(0.5)


def test_11_normal_cagr():
    result = calculate_cagr(100, 133.1, 3)
    assert result.value == pytest.approx(10.0)
    assert result.flag is None


def test_12_cagr_decline_to_loss():
    assert calculate_cagr(100, -10, 3).flag == CAGRFlag.DECLINE_TO_LOSS


def test_13_cagr_turnaround():
    assert calculate_cagr(-100, 10, 3).flag == CAGRFlag.TURNAROUND


def test_14_cagr_both_negative():
    assert calculate_cagr(-100, -10, 3).flag == CAGRFlag.BOTH_NEGATIVE


def test_15_cagr_zero_base():
    assert calculate_cagr(0, 10, 3).flag == CAGRFlag.ZERO_BASE


def test_16_cagr_insufficient_history():
    results = calculate_cagr_windows({2024: 100, 2025: 110})
    assert all(result.flag == CAGRFlag.INSUFFICIENT for result in results.values())


def test_17_free_cash_flow():
    assert free_cash_flow(100, -160) == pytest.approx(-60)


def test_18_five_year_cfo_quality():
    assert cfo_quality_score([120] * 5, [100] * 5) == pytest.approx(1.2)


def test_19_capex_intensity_and_fcf_conversion():
    assert capex_intensity(-30, 1_000) == pytest.approx(3.0)
    assert fcf_conversion_rate(40, 80) == pytest.approx(50.0)


def test_20_capital_allocation_classifier():
    assert classify_capital_allocation(120, -40, -30, cfo_pat_ratio=1.2) == (
        "Shareholder Returns"
    )
