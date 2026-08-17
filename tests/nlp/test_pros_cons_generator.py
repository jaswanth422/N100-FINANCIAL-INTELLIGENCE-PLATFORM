import pytest

from nlp.pros_cons_generator import (
    CompanyData,
    CoverageError,
    generate_all_signals,
    generate_company_signals,
    verify_company_coverage,
)


def _row(**values):
    return values


def test_all_twelve_pro_rules_trigger_on_strong_company():
    ratios = {
        year: _row(
            return_on_equity_pct=21 + (year - 2019),
            free_cash_flow_cr=100,
            debt_to_equity=0,
            revenue_cagr_5yr=30,
            operating_profit_margin_pct=30,
            pat_cagr_5yr=25,
            interest_coverage=20,
            icr_label=None,
            eps_cagr_5yr=20,
            earnings_per_share=10 + year - 2019,
            return_on_capital_employed_pct=25,
            net_debt=-10,
            dividend_payout_ratio_pct=30,
        )
        for year in range(2019, 2025)
    }
    balances = {
        2022: _row(total_assets=100, borrowings=30),
        2023: _row(total_assets=110, borrowings=20),
        2024: _row(total_assets=120, borrowings=10),
    }
    company = CompanyData(
        "PRO",
        "Industrials",
        ratios,
        {2024: _row(sales=100, net_profit=20, operating_profit=30)},
        balances,
        {2024: _row(dividend_yield_pct=3)},
    )

    signals = generate_company_signals(company)

    assert {signal.rule_id for signal in signals if signal.type == "pro"} == set(range(1, 13))
    assert all(signal.confidence_pct > 60 for signal in signals)


def test_all_twelve_con_rules_trigger_on_weak_company():
    ratios = {
        2022: _row(
            free_cash_flow_cr=-10,
            operating_profit_margin_pct=20,
            debt_to_equity=2.1,
            earnings_per_share=10,
        ),
        2023: _row(
            free_cash_flow_cr=-20,
            operating_profit_margin_pct=15,
            debt_to_equity=2.5,
            earnings_per_share=8,
        ),
        2024: _row(
            return_on_equity_pct=5,
            free_cash_flow_cr=-30,
            debt_to_equity=3,
            revenue_cagr_5yr=2,
            operating_profit_margin_pct=10,
            pat_cagr_5yr=-5,
            interest_coverage=1,
            icr_label=None,
            eps_cagr_5yr=-5,
            earnings_per_share=5,
            return_on_capital_employed_pct=5,
            net_debt=400,
            dividend_payout_ratio_pct=150,
        ),
    }
    profits = {
        2022: _row(sales=120),
        2023: _row(sales=110),
        2024: _row(sales=100, net_profit=-10, operating_profit=100),
    }
    company = CompanyData("CON", "Industrials", ratios, profits, {}, {})

    signals = generate_company_signals(company)

    assert {signal.rule_id for signal in signals if signal.type == "con"} == set(range(1, 13))
    assert "3" in next(signal.text for signal in signals if signal.rule_id == 1)
    assert all(signal.confidence_pct > 60 for signal in signals)


def test_rule_zero_review_sentinels_guarantee_complete_coverage():
    company = CompanyData("EMPTY", "Industrials", {}, {}, {}, {})

    signals = generate_all_signals([company])

    verify_company_coverage(signals, ["EMPTY"])
    assert {(signal.type, signal.rule_id) for signal in signals} == {
        ("pro", 0),
        ("con", 0),
    }


def test_coverage_verification_reports_missing_sides():
    with pytest.raises(CoverageError):
        verify_company_coverage([], ["ABC"])

