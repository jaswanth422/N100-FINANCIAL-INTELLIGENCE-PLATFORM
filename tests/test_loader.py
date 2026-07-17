from pathlib import Path

import pandas as pd
import pytest

from nifty100_etl.loader import ExcelSource, discover_sources, load_excel, normalize_column_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Company Name", "company_name"),
        ("ROE (%)", "roe"),
        ("  Fiscal-Year  ", "fiscal_year"),
        ("Market.Cap", "market_cap"),
        ("Ticker", "ticker"),
    ],
)
def test_normalize_column_name(raw, expected):
    assert normalize_column_name(raw) == expected


def test_discover_sources_reports_all_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="companies.xlsx"):
        discover_sources(tmp_path)


def test_load_excel_normalizes_frame(monkeypatch, tmp_path: Path):
    path = tmp_path / "companies.xlsx"
    path.touch()
    raw = pd.DataFrame({"Company Name": ["A", None], "Empty": [None, None]})
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: raw)
    result = load_excel(ExcelSource(path, "companies"))
    assert list(result.columns) == ["source_file", "company_name"]
    assert result.to_dict("records") == [{"source_file": "companies.xlsx", "company_name": "A"}]


def test_load_excel_adds_statement_type(monkeypatch, tmp_path: Path):
    path = tmp_path / "cashflow.xlsx"
    path.touch()
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: pd.DataFrame({"Year": [2024]}))
    result = load_excel(ExcelSource(path, "financial_statements", "cash_flow"))
    assert result.loc[0, "statement_type"] == "cash_flow"


def test_load_excel_rejects_duplicate_normalized_columns(monkeypatch, tmp_path: Path):
    path = tmp_path / "companies.xlsx"
    path.touch()
    raw = pd.DataFrame([[1, 2]], columns=["Company Name", "Company-Name"])
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: raw)
    with pytest.raises(ValueError, match="Duplicate columns"):
        load_excel(ExcelSource(path, "companies"))


def test_load_excel_detects_title_row_and_normalizes_values(monkeypatch, tmp_path: Path):
    path = tmp_path / "documents.xlsx"
    path.touch()
    preview = pd.DataFrame([["Dataset title", None, None], ["id", "company_id", "Year"]])
    data = pd.DataFrame({"id": [1], "company_id": [" nse:infy.ns "], "Year": ["FY 2024"]})

    def fake_read_excel(*args, **kwargs):
        return preview if kwargs.get("header") is None else data

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    result = load_excel(ExcelSource(path, "documents"))
    assert result.loc[0, "company_id"] == "INFY"
    assert result.loc[0, "year"] == 2024
