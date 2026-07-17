import logging

import pytest

from analytics.ratios import (
    asset_turnover,
    calculate_leverage_efficiency_ratios,
    calculate_profitability_ratios,
    debt_to_equity,
    has_icr_warning,
    interest_coverage_label,
    interest_coverage_ratio,
    is_high_leverage,
    meets_roce_benchmark,
    net_debt,
    net_profit_margin,
    operating_profit_margin,
    return_on_assets,
    return_on_capital_employed,
    return_on_equity,
)


def test_net_profit_margin_normal_case():
    assert net_profit_margin(25, 200) == pytest.approx(12.5)


def test_zero_sales_returns_none_for_both_margins():
    assert net_profit_margin(25, 0) is None
    assert operating_profit_margin(40, 0, 20) is None


def test_return_on_equity_normal_case():
    assert return_on_equity(30, 40, 60) == pytest.approx(30.0)


def test_return_on_equity_rejects_zero_and_negative_equity():
    assert return_on_equity(10, 20, -20) is None
    assert return_on_equity(10, 20, -30) is None


def test_roce_and_roa_normal_cases():
    assert return_on_capital_employed(24, 40, 40, 40) == pytest.approx(20.0)
    assert return_on_assets(18, 120) == pytest.approx(15.0)


def test_zero_roce_and_roa_denominators_return_none():
    assert return_on_capital_employed(20, 10, -5, -5) is None
    assert return_on_assets(20, 0) is None


def test_opm_mismatch_over_one_percentage_point_is_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="analytics.ratios"):
        result = operating_profit_margin(20, 100, 18, company_id="ABC", year=2025)

    assert result == pytest.approx(20.0)
    assert "OPM cross-check mismatch" in caplog.text
    assert "company_id=ABC" in caplog.text


def test_batch_calculation_and_financials_sector_benchmark():
    result = calculate_profitability_ratios(
        net_profit=20,
        sales=100,
        operating_profit=25,
        opm_percentage=25,
        equity_capital=20,
        reserves=30,
        borrowings=50,
        ebit=25,
        total_assets=200,
    )
    assert result.return_on_capital_employed_pct == pytest.approx(25.0)
    assert meets_roce_benchmark(14, "Industrials", absolute_threshold=15) is False
    assert meets_roce_benchmark(14, "Financials") is None
    assert meets_roce_benchmark(14, "Financials", sector_relative_benchmark=12) is True


def test_debt_to_equity_normal_case():
    assert debt_to_equity(300, 20, 30) == pytest.approx(6.0)


def test_debt_to_equity_debt_free_returns_zero():
    assert debt_to_equity(0, 0, 0) == 0


def test_high_debt_to_equity_flag_excludes_financials():
    assert is_high_leverage(5.01, "Industrials") is True
    assert is_high_leverage(5.01, " Financials ") is False
    assert is_high_leverage(5.0, "Industrials") is False


def test_interest_coverage_and_warning_threshold():
    assert interest_coverage_ratio(100, 20, 40) == pytest.approx(3.0)
    assert has_icr_warning(1.49) is True
    assert has_icr_warning(1.5) is False


def test_interest_coverage_zero_interest_returns_none():
    assert interest_coverage_ratio(100, 20, 0) is None


def test_missing_icr_uses_debt_free_label():
    assert interest_coverage_label(None) == "Debt Free"
    assert interest_coverage_label(2.0) is None


def test_net_debt_uses_investments_as_liquid_asset_proxy():
    assert net_debt(100, 35) == pytest.approx(65.0)


def test_asset_turnover_and_day_09_batch_calculation():
    assert asset_turnover(250, 500) == pytest.approx(0.5)
    assert asset_turnover(250, 0) is None

    result = calculate_leverage_efficiency_ratios(
        borrowings=0,
        equity_capital=20,
        reserves=30,
        broad_sector="Industrials",
        operating_profit=50,
        other_income=5,
        interest=0,
        investments=12,
        sales=250,
        total_assets=500,
    )
    assert result.debt_to_equity == 0
    assert result.icr_label == "Debt Free"
    assert result.icr_warning_flag is False
    assert result.net_debt == pytest.approx(-12.0)
