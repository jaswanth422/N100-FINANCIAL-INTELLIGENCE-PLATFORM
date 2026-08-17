from __future__ import annotations

from pathlib import Path

import pandas as pd

from nifty100_etl.loader import ExcelSource
from nifty100_etl.validation import RULE_BY_ID, ValidationContext


def _source(name: str, table: str, **columns: list[object]) -> tuple[ExcelSource, pd.DataFrame]:
    return ExcelSource(Path(name), table), pd.DataFrame(columns)


def _context(*sources: tuple[ExcelSource, pd.DataFrame]) -> ValidationContext:
    return ValidationContext(tuple(sources))


def test_dq03_company_primary_key_not_null() -> None:
    context = _context(_source("companies.xlsx", "companies", id=[None]))
    assert len(RULE_BY_ID["DQ-03"].check(context)) == 1


def test_dq04_company_primary_key_unique() -> None:
    context = _context(_source("companies.xlsx", "companies", id=["A", "A"]))
    assert len(RULE_BY_ID["DQ-04"].check(context)) == 2


def test_dq05_company_foreign_key_not_null() -> None:
    context = _context(_source("documents.xlsx", "documents", id=[1], company_id=[None]))
    assert len(RULE_BY_ID["DQ-05"].check(context)) == 1


def test_dq06_company_foreign_key_exists() -> None:
    context = _context(
        _source("companies.xlsx", "companies", id=["A"]),
        _source("documents.xlsx", "documents", id=[1], company_id=["B"]),
    )
    assert len(RULE_BY_ID["DQ-06"].check(context)) == 1


def test_dq07_source_primary_key_not_null() -> None:
    context = _context(_source("documents.xlsx", "documents", id=[None]))
    assert len(RULE_BY_ID["DQ-07"].check(context)) == 1


def test_dq08_source_primary_key_unique() -> None:
    context = _context(_source("documents.xlsx", "documents", id=[1, 1]))
    assert len(RULE_BY_ID["DQ-08"].check(context)) == 2


def test_dq09_required_columns_exist() -> None:
    context = _context(_source("companies.xlsx", "companies", id=["A"]))
    failures = RULE_BY_ID["DQ-09"].check(context)
    assert [failure["column"] for failure in failures] == ["company_name"]


def test_dq10_year_supported_range() -> None:
    context = _context(_source("documents.xlsx", "documents", year=[2200]))
    assert len(RULE_BY_ID["DQ-10"].check(context)) == 1


def test_dq11_operating_margin_plausible() -> None:
    context = _context(_source("profitandloss.xlsx", "financial_statements", opm_percentage=[101]))
    assert len(RULE_BY_ID["DQ-11"].check(context)) == 1


def test_dq12_balance_sheet_balances() -> None:
    context = _context(
        _source(
            "balancesheet.xlsx",
            "financial_statements",
            total_assets=[100],
            total_liabilities=[80],
        )
    )
    assert len(RULE_BY_ID["DQ-12"].check(context)) == 1


def test_dq13_sales_non_negative() -> None:
    context = _context(_source("profitandloss.xlsx", "financial_statements", sales=[-1]))
    assert len(RULE_BY_ID["DQ-13"].check(context)) == 1


def test_dq14_ohlc_consistent() -> None:
    context = _context(
        _source(
            "stock_prices.xlsx",
            "stock_prices",
            open_price=[10],
            high_price=[9],
            low_price=[8],
            close_price=[11],
        )
    )
    assert len(RULE_BY_ID["DQ-14"].check(context)) == 1


def test_dq15_volume_non_negative() -> None:
    context = _context(_source("stock_prices.xlsx", "stock_prices", volume=[-1]))
    assert len(RULE_BY_ID["DQ-15"].check(context)) == 1


def test_dq16_url_well_formed() -> None:
    context = _context(_source("documents.xlsx", "documents", annual_report=["not-a-url"]))
    assert len(RULE_BY_ID["DQ-16"].check(context)) == 1
