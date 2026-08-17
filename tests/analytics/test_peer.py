from __future__ import annotations

import sqlite3

import pandas as pd
import pytest
from openpyxl import load_workbook

from analytics.peer import (
    BENCHMARK_FILL,
    HIGH_PERCENTILE_FILL,
    LOW_PERCENTILE_FILL,
    MID_PERCENTILE_FILL,
    NO_FILL,
    NO_PEER_GROUP_MESSAGE,
    PEER_METRICS,
    REPORT_METRICS,
    compute_peer_percentiles,
    get_company_peer_percentiles,
    percent_rank,
    write_peer_comparison_workbook,
)


def test_percent_rank_and_inverse_debt_rank() -> None:
    values = pd.Series([1.0, 2.0, 2.0, 4.0])

    assert percent_rank(values).tolist() == pytest.approx([0, 1 / 3, 1 / 3, 1])
    assert percent_rank(values, inverse=True).tolist() == pytest.approx([1, 2 / 3, 2 / 3, 0])


def test_compute_ten_metrics_per_company_and_inverts_debt() -> None:
    ratio_data: dict[str, object] = {
        "company_id": ["LOW_DEBT", "HIGH_DEBT"],
        "year": [2024, 2024],
    }
    for metric in PEER_METRICS:
        ratio_data[metric.column] = [1.0, 2.0]
    ratios = pd.DataFrame(ratio_data)
    peers = pd.DataFrame(
        {
            "company_id": ["LOW_DEBT", "HIGH_DEBT"],
            "peer_group_name": ["Test", "Test"],
        }
    )

    result = compute_peer_percentiles(ratios, peers)

    assert len(result) == 20
    debt = result[result["metric"].eq("D/E")].set_index("company_id")
    assert debt.loc["LOW_DEBT", "percentile_rank"] == 1
    assert debt.loc["HIGH_DEBT", "percentile_rank"] == 0


def test_unassigned_company_returns_message() -> None:
    connection = sqlite3.connect(":memory:")

    assert get_company_peer_percentiles(connection, "UNKNOWN") == NO_PEER_GROUP_MESSAGE


def test_peer_comparison_workbook_has_eleven_styled_sheets(tmp_path) -> None:
    output = tmp_path / "peer_comparison.xlsx"

    write_peer_comparison_workbook("nifty100.db", output)

    workbook = load_workbook(output)
    assert len(workbook.sheetnames) == 11
    expected_fills = {
        HIGH_PERCENTILE_FILL.fgColor.rgb,
        MID_PERCENTILE_FILL.fgColor.rgb,
        LOW_PERCENTILE_FILL.fgColor.rgb,
        NO_FILL.fgColor.rgb,
    }
    for worksheet in workbook.worksheets:
        headers = [cell.value for cell in worksheet[1]]
        assert worksheet.max_column == 2 + len(REPORT_METRICS) * 2
        assert worksheet.cell(worksheet.max_row, 2).value == "PEER GROUP MEDIAN"
        percentile_column = headers.index("ROE Percentile") + 1
        fills = {
            worksheet.cell(row, percentile_column).fill.fgColor.rgb
            for row in range(2, worksheet.max_row)
        }
        assert fills <= expected_fills
        assert fills
    benchmark_id = (
        pd.read_excel("supporting datasets/peer_groups.xlsx")
        .loc[lambda frame: frame["is_benchmark"].astype(bool), "company_id"]
        .iloc[0]
    )
    benchmark_sheet = workbook["Private Banks"]
    benchmark_row = next(
        row
        for row in range(2, benchmark_sheet.max_row)
        if benchmark_sheet.cell(row, 1).value == benchmark_id
    )
    assert benchmark_sheet.cell(benchmark_row, 1).fill.fgColor.rgb == BENCHMARK_FILL.fgColor.rgb
