from __future__ import annotations

import pandas as pd
import pytest
from openpyxl import load_workbook

from screener.engine import (
    EXPORT_ID_COLUMNS,
    EXPORT_KPI_COLUMNS,
    ScreenerEngine,
    apply_filters,
    load_latest_universe,
    write_preset_workbook,
)


def test_custom_filters_cover_sector_and_icr_edge_cases() -> None:
    frame = pd.DataFrame(
        {
            "company_id": ["BANK", "INDUSTRIAL", "DEBT_FREE", "WEAK"],
            "broad_sector": ["Financials", "Industrials", "Industrials", "Industrials"],
            "debt_to_equity": [8.0, 0.5, 0.0, 0.5],
            "interest_coverage": [0.2, 4.0, None, 1.0],
            "icr_label": [None, None, "Debt Free", None],
            "return_on_equity_pct": [20.0, 18.0, 16.0, 14.0],
            "composite_quality_score": [70.0, 90.0, 80.0, 60.0],
        }
    )

    result = apply_filters(frame, {"de_max": 1.0, "icr_min": 3.0, "roe_min": 15.0})

    assert result["company_id"].tolist() == ["INDUSTRIAL", "DEBT_FREE"]


def test_all_fifteen_custom_metric_thresholds_are_supported() -> None:
    row = pd.DataFrame(
        {
            "return_on_equity_pct": [16],
            "debt_to_equity": [0.5],
            "free_cash_flow_cr": [1],
            "revenue_cagr_5yr": [11],
            "pat_cagr_5yr": [12],
            "operating_profit_margin_pct": [13],
            "pe_ratio": [14],
            "pb_ratio": [2],
            "dividend_yield_pct": [3],
            "interest_coverage": [4],
            "market_cap_crore": [5001],
            "net_profit_cr": [101],
            "eps_cagr_5yr": [10],
            "asset_turnover": [1.2],
            "sales_cr": [1001],
        }
    )
    thresholds = {
        "roe_min": 15,
        "de_max": 1,
        "fcf_min": 0,
        "revenue_cagr_5yr_min": 10,
        "pat_cagr_5yr_min": 10,
        "opm_min": 10,
        "pe_max": 20,
        "pb_max": 3,
        "dividend_yield_min": 2,
        "icr_min": 3,
        "market_cap_min": 5000,
        "net_profit_min": 100,
        "eps_cagr_min": 9,
        "asset_turnover_min": 1,
        "sales_min": 1000,
    }

    assert len(apply_filters(row, thresholds)) == 1


def test_presets_use_strict_business_thresholds() -> None:
    frame = pd.DataFrame(
        {
            "company_id": ["ON_BOUNDARY", "PASS"],
            "broad_sector": ["Industrials", "Industrials"],
            "return_on_equity_pct": [15, 16],
            "debt_to_equity": [0.5, 0.5],
            "free_cash_flow_cr": [1, 1],
            "revenue_cagr_5yr": [11, 11],
            "composite_quality_score": [90, 80],
        }
    )

    result = ScreenerEngine().run_preset(frame, "quality_compounder")

    assert result["company_id"].tolist() == ["PASS"]


def test_unknown_custom_filter_is_rejected() -> None:
    with pytest.raises(KeyError, match="Unknown filter"):
        apply_filters(pd.DataFrame({"x": [1]}), {"not_a_metric": 1})


def test_latest_database_universe_has_one_row_per_company() -> None:
    universe = load_latest_universe("nifty100.db")

    assert len(universe) == 92
    assert universe["company_id"].is_unique


def test_workbook_has_twenty_kpis_and_green_red_threshold_cells(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "company_id": ["PASS", "FAIL"],
            "company_name": ["Pass Ltd", "Fail Ltd"],
            "year": [2024, 2024],
            "broad_sector": ["Industrials", "Industrials"],
            "sub_sector": ["Test", "Test"],
            "return_on_equity_pct": [20.0, 10.0],
            "debt_to_equity": [0.5, 2.0],
            "free_cash_flow_cr": [100.0, -10.0],
            "revenue_cagr_5yr": [15.0, 5.0],
            "composite_quality_score": [80.0, 20.0],
        }
    )
    for column in EXPORT_ID_COLUMNS + EXPORT_KPI_COLUMNS:
        if column not in frame:
            frame[column] = pd.NA
    output = tmp_path / "screener.xlsx"

    write_preset_workbook(frame, output)

    workbook = load_workbook(output)
    assert len(workbook.sheetnames) == 6
    sheet = workbook["quality_compounder"]
    headers = [cell.value for cell in sheet[1]]
    roe_column = headers.index("return_on_equity_pct") + 1
    assert len(EXPORT_ID_COLUMNS) == 5
    assert len(EXPORT_KPI_COLUMNS) == 20
    assert sheet.max_column == 25
    assert sheet.cell(2, roe_column).fill.fgColor.rgb == "00C6EFCE"
    assert sheet.cell(3, roe_column).fill.fgColor.rgb == "00FFC7CE"
