from pathlib import Path

import pandas as pd

from nifty100_etl.loader import ExcelSource
from nifty100_etl.validation import (
    CRITICAL,
    RULE_BY_ID,
    RULES,
    ValidationContext,
    critical_failure_count,
    write_validation_failures,
)


def source(name: str, table: str, frame: pd.DataFrame) -> tuple[ExcelSource, pd.DataFrame]:
    return ExcelSource(Path(name), table), frame


def test_exactly_sixteen_rules_with_stable_ids():
    assert [rule.id for rule in RULES] == [f"DQ-{number:02d}" for number in range(1, 17)]


def test_company_primary_key_rules():
    frame = pd.DataFrame({"id": ["AAA", None, "AAA"]})
    context = ValidationContext((source("companies.xlsx", "companies", frame),))
    assert len(RULE_BY_ID["DQ-03"].check(context)) == 1
    assert len(RULE_BY_ID["DQ-04"].check(context)) == 2


def test_foreign_key_rule_reports_orphan():
    companies = source("companies.xlsx", "companies", pd.DataFrame({"id": ["AAA"]}))
    documents = source(
        "documents.xlsx", "documents", pd.DataFrame({"id": [1], "company_id": ["BBB"]})
    )
    failures = RULE_BY_ID["DQ-06"].check(ValidationContext((companies, documents)))
    assert failures[0]["value"] == "BBB"
    assert failures[0]["severity"] == CRITICAL


def test_balance_rule_uses_one_percent_tolerance():
    good = source(
        "balancesheet.xlsx",
        "financial_statements",
        pd.DataFrame({"total_assets": [100, 100], "total_liabilities": [100.5, 80]}),
    )
    failures = RULE_BY_ID["DQ-12"].check(ValidationContext((good,)))
    assert len(failures) == 1
    assert failures[0]["row_number"] == 3


def test_ohlc_rule_reports_invalid_high():
    prices = source(
        "stock_prices.xlsx",
        "stock_prices",
        pd.DataFrame(
            {"open_price": [10], "high_price": [9], "low_price": [8], "close_price": [11]}
        ),
    )
    assert len(RULE_BY_ID["DQ-14"].check(ValidationContext((prices,)))) == 1


def test_url_rule_accepts_blank_and_rejects_malformed():
    documents = source(
        "documents.xlsx",
        "documents",
        pd.DataFrame({"annual_report": [None, "https://example.com/a.pdf", "not-a-url"]}),
    )
    failures = RULE_BY_ID["DQ-16"].check(ValidationContext((documents,)))
    assert len(failures) == 1
    assert failures[0]["value"] == "not-a-url"


def test_write_report_and_count_critical(tmp_path: Path):
    failures = pd.DataFrame(
        [{"severity": CRITICAL, "dq_rule": "DQ-01"}],
    )
    output = write_validation_failures(failures, tmp_path / "validation_failures.csv")
    assert output.is_file()
    assert critical_failure_count(failures) == 1
