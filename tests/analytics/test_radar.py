from __future__ import annotations

import sqlite3

import pandas as pd

from analytics.peer import PEER_METRICS
from analytics.radar import generate_radar_charts


def test_generate_peer_radar_and_unassigned_fallback(tmp_path) -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE companies (id TEXT PRIMARY KEY, company_name TEXT)")
    metric_definitions = ", ".join(f'"{metric.column}" REAL' for metric in PEER_METRICS)
    connection.execute(
        f"""
        CREATE TABLE financial_ratios (
            id INTEGER PRIMARY KEY,
            company_id TEXT,
            year INTEGER,
            {metric_definitions},
            composite_quality_score REAL
        )
        """
    )
    companies = [("A", "Alpha Ltd"), ("B", "Beta Ltd"), ("C", "No Peer Ltd")]
    connection.executemany("INSERT INTO companies VALUES (?, ?)", companies)
    metric_columns = [metric.column for metric in PEER_METRICS]
    placeholders = ", ".join("?" for _ in range(4 + len(metric_columns)))
    rows = [
        (index, company_id, 2024, *([float(index)] * len(metric_columns)), 40 + index * 10)
        for index, company_id in enumerate(["A", "B", "C"], start=1)
    ]
    connection.executemany(
        f"""
        INSERT INTO financial_ratios (
            id, company_id, year, {", ".join(metric_columns)}, composite_quality_score
        ) VALUES ({placeholders})
        """,
        rows,
    )
    peer_path = tmp_path / "peer_groups.xlsx"
    pd.DataFrame({"peer_group_name": ["Test", "Test"], "company_id": ["A", "B"]}).to_excel(
        peer_path, index=False
    )

    manifest = generate_radar_charts(
        connection,
        peer_groups_path=peer_path,
        output_dir=tmp_path / "charts",
    )

    assert manifest["chart_type"].value_counts().to_dict() == {"radar": 2, "standalone": 1}
    assert all(
        (tmp_path / "charts" / f"{company_id}_radar.png").stat().st_size > 10_000
        for company_id in "ABC"
    )
