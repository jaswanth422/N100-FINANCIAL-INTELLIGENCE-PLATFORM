import pytest

from nlp.parser import parse_analysis_records, parse_metric_text


def test_day_29_regex_extracts_period_and_percentage():
    assert parse_metric_text("10 Years: 21%") == [(10, 21.0)]
    assert parse_metric_text("  1 Year:     8.5%") == [(1, 8.5)]


def test_prescribed_regex_rejects_ttm_last_year_and_negative_values():
    assert parse_metric_text("TTM: 21%") == []
    assert parse_metric_text("Last Year: 21%") == []
    assert parse_metric_text("3 Years: -1%") == []


def test_parse_records_logs_regex_misses_and_cagr_divergence():
    records = [
        {
            "company_id": "ABC",
            "compounded_sales_growth": "5 Years: 20%",
            "compounded_profit_growth": "TTM: 4%",
            "stock_price_cagr": "5 Years: 9%",
            "roe": "5 Years: 18%",
        }
    ]
    references = {("ABC", "compounded_sales_growth", 5): 14.9}

    parsed, failures = parse_analysis_records(records, ratio_cagrs=references)

    assert len(parsed) == 3
    assert {failure.failure_type for failure in failures} == {
        "regex_no_match",
        "cagr_divergence",
    }
    divergence = next(
        failure for failure in failures if failure.failure_type == "cagr_divergence"
    )
    assert divergence.divergence_pct_points == pytest.approx(5.1)


def test_cagr_divergence_must_be_strictly_greater_than_five_points():
    records = [
        {
            "company_id": "ABC",
            "compounded_sales_growth": "5 Years: 20%",
        }
    ]
    references = {("ABC", "compounded_sales_growth", 5): 15.0}

    _, failures = parse_analysis_records(records, ratio_cagrs=references)

    assert failures == []

