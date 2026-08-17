"""Peer-group percentile rankings and SQLite persistence."""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PEER_GROUPS = PROJECT_ROOT / "supporting datasets" / "peer_groups.xlsx"
NO_PEER_GROUP_MESSAGE = "No peer group assigned"


@dataclass(frozen=True)
class PeerMetric:
    label: str
    column: str
    inverse: bool = False


PEER_METRICS: tuple[PeerMetric, ...] = (
    PeerMetric("ROE", "return_on_equity_pct"),
    PeerMetric("ROCE", "return_on_capital_employed_pct"),
    PeerMetric("Net Profit Margin", "net_profit_margin_pct"),
    PeerMetric("D/E", "debt_to_equity", inverse=True),
    PeerMetric("FCF", "free_cash_flow_cr"),
    PeerMetric("PAT CAGR 5yr", "pat_cagr_5yr"),
    PeerMetric("Revenue CAGR 5yr", "revenue_cagr_5yr"),
    PeerMetric("EPS CAGR 5yr", "eps_cagr_5yr"),
    PeerMetric("Interest Coverage", "interest_coverage"),
    PeerMetric("Asset Turnover", "asset_turnover"),
)

REPORT_METRICS: tuple[PeerMetric, ...] = (
    *PEER_METRICS,
    PeerMetric("Composite Score", "composite_quality_score"),
    PeerMetric("Operating Margin", "operating_profit_margin_pct"),
    PeerMetric("Revenue CAGR 3yr", "revenue_cagr_3yr"),
    PeerMetric("PAT CAGR 3yr", "pat_cagr_3yr"),
    PeerMetric("EPS CAGR 3yr", "eps_cagr_3yr"),
    PeerMetric("CFO/PAT Ratio", "cfo_quality_score"),
    PeerMetric("FCF CAGR 5yr", "fcf_cagr_5yr"),
    PeerMetric("FCF Conversion", "fcf_conversion_rate_pct"),
    PeerMetric("Dividend Payout", "dividend_payout_ratio_pct"),
    PeerMetric("Market Cap (Cr)", "market_cap_crore"),
)

HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E78")
BENCHMARK_FILL = PatternFill(fill_type="solid", fgColor="FFD966")
HIGH_PERCENTILE_FILL = PatternFill(fill_type="solid", fgColor="C6EFCE")
MID_PERCENTILE_FILL = PatternFill(fill_type="solid", fgColor="FFF2CC")
LOW_PERCENTILE_FILL = PatternFill(fill_type="solid", fgColor="FFC7CE")
NO_FILL = PatternFill(fill_type=None)
MEDIAN_FILL = PatternFill(fill_type="solid", fgColor="D9EAF7")
THIN_BLUE_BORDER = Border(bottom=Side(style="thin", color="5B9BD5"))


def load_peer_groups(path: str | Path = DEFAULT_PEER_GROUPS) -> pd.DataFrame:
    """Load and validate peer assignments from the Day 18 workbook."""
    frame = pd.read_excel(path)
    required = {"peer_group_name", "company_id"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Peer-group workbook is missing columns: {', '.join(missing)}")
    result = frame.copy()
    result["company_id"] = result["company_id"].astype("string").str.strip()
    result["peer_group_name"] = result["peer_group_name"].astype("string").str.strip()
    return result.dropna(subset=["company_id", "peer_group_name"]).drop_duplicates(
        ["peer_group_name", "company_id"]
    )


def percent_rank(values: pd.Series, *, inverse: bool = False) -> pd.Series:
    """Return SQL/Excel-style ``PERCENT_RANK`` values, preserving nulls."""
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    result = pd.Series(np.nan, index=values.index, dtype="float64")
    valid = numeric.dropna()
    count = len(valid)
    if count == 0:
        return result
    if count == 1:
        result.loc[valid.index] = 0.0
        return result
    ranks = valid.rank(method="min", ascending=True)
    ranked = (ranks - 1.0) / (count - 1.0)
    result.loc[valid.index] = 1.0 - ranked if inverse else ranked
    return result.clip(0.0, 1.0)


def load_ratio_universe(
    database: str | Path | sqlite3.Connection,
    *,
    year: int | None = None,
) -> pd.DataFrame:
    """Load one ratio row per company for ``year`` or each company's latest year."""
    owns_connection = not isinstance(database, sqlite3.Connection)
    connection = sqlite3.connect(str(database)) if owns_connection else database
    assert isinstance(connection, sqlite3.Connection)
    year_filter = "WHERE year = :year" if year is not None else "WHERE year IS NOT NULL"
    query = f"""
        WITH ranked AS (
            SELECT r.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY company_id ORDER BY year DESC, id DESC
                   ) AS latest_rank
            FROM financial_ratios r
            {year_filter}
        )
        SELECT company_id,
               year,
               return_on_equity_pct,
               return_on_capital_employed_pct,
               net_profit_margin_pct,
               debt_to_equity,
               free_cash_flow_cr,
               pat_cagr_5yr,
               revenue_cagr_5yr,
               eps_cagr_5yr,
               interest_coverage,
               asset_turnover,
               composite_quality_score
        FROM ranked
        WHERE latest_rank = 1
        ORDER BY company_id
    """
    try:
        return pd.read_sql_query(query, connection, params={"year": year})
    finally:
        if owns_connection:
            connection.close()


def compute_peer_percentiles(
    ratios: pd.DataFrame,
    peer_groups: pd.DataFrame,
) -> pd.DataFrame:
    """Compute all ten metric percentile ranks within each peer group."""
    required_ratio_columns = {"company_id", "year", *(item.column for item in PEER_METRICS)}
    missing = sorted(required_ratio_columns.difference(ratios.columns))
    if missing:
        raise ValueError(f"Ratio data is missing columns: {', '.join(missing)}")

    assignments = peer_groups[["peer_group_name", "company_id"]].drop_duplicates()
    joined = assignments.merge(ratios, on="company_id", how="left", validate="many_to_one")
    records: list[pd.DataFrame] = []
    for metric in PEER_METRICS:
        metric_frame = joined[["company_id", "peer_group_name", "year", metric.column]].copy()
        metric_frame = metric_frame.rename(columns={metric.column: "value"})
        metric_frame["metric"] = metric.label
        metric_frame["percentile_rank"] = metric_frame.groupby("peer_group_name", dropna=False)[
            "value"
        ].transform(lambda values, inverse=metric.inverse: percent_rank(values, inverse=inverse))
        records.append(metric_frame)

    result = pd.concat(records, ignore_index=True)
    return result[
        [
            "company_id",
            "peer_group_name",
            "metric",
            "value",
            "percentile_rank",
            "year",
        ]
    ].sort_values(["peer_group_name", "company_id", "metric"], ignore_index=True)


def load_peer_report_universe(
    database: str | Path | sqlite3.Connection,
    *,
    year: int | None = None,
) -> pd.DataFrame:
    """Load the latest company row containing all 20 peer-report metrics."""
    owns_connection = not isinstance(database, sqlite3.Connection)
    connection = sqlite3.connect(str(database)) if owns_connection else database
    assert isinstance(connection, sqlite3.Connection)
    year_filter = "WHERE r.year = :year" if year is not None else "WHERE r.year IS NOT NULL"
    query = f"""
        WITH ratios AS (
            SELECT r.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY company_id ORDER BY year DESC, id DESC
                   ) AS latest_rank
            FROM financial_ratios r
            {year_filter}
        ), market AS (
            SELECT m.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY company_id ORDER BY year DESC, id DESC
                   ) AS latest_rank
            FROM market_cap m
            WHERE m.year IS NOT NULL
        )
        SELECT r.company_id,
               REPLACE(REPLACE(c.company_name, char(10), ' '), char(13), ' ') AS company_name,
               r.year,
               r.return_on_equity_pct,
               r.return_on_capital_employed_pct,
               r.net_profit_margin_pct,
               r.debt_to_equity,
               r.free_cash_flow_cr,
               r.pat_cagr_5yr,
               r.revenue_cagr_5yr,
               r.eps_cagr_5yr,
               r.interest_coverage,
               r.asset_turnover,
               r.composite_quality_score,
               r.operating_profit_margin_pct,
               r.revenue_cagr_3yr,
               r.pat_cagr_3yr,
               r.eps_cagr_3yr,
               r.cfo_quality_score,
               r.fcf_cagr_5yr,
               r.fcf_conversion_rate_pct,
               r.dividend_payout_ratio_pct,
               m.market_cap_crore
        FROM ratios r
        JOIN companies c ON c.id = r.company_id
        LEFT JOIN market m ON m.company_id = r.company_id AND m.latest_rank = 1
        WHERE r.latest_rank = 1
        ORDER BY r.company_id
    """
    try:
        return pd.read_sql_query(query, connection, params={"year": year})
    finally:
        if owns_connection:
            connection.close()


def build_peer_comparison_frames(
    universe: pd.DataFrame,
    peer_groups: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Build one comparison frame per peer group with 20 values and 20 ranks."""
    required = {"company_id", "company_name", *(metric.column for metric in REPORT_METRICS)}
    missing = sorted(required.difference(universe.columns))
    if missing:
        raise ValueError(f"Peer report data is missing columns: {', '.join(missing)}")

    assignment_columns = ["peer_group_name", "company_id"]
    if "is_benchmark" in peer_groups:
        assignment_columns.append("is_benchmark")
    assignments = peer_groups[assignment_columns].drop_duplicates(["peer_group_name", "company_id"])
    if "is_benchmark" not in assignments:
        assignments["is_benchmark"] = False
    joined = assignments.merge(universe, on="company_id", how="left", validate="many_to_one")

    frames: dict[str, pd.DataFrame] = {}
    for group_name, group in joined.groupby("peer_group_name", sort=False, dropna=False):
        report = group.copy()
        for metric in REPORT_METRICS:
            report[metric.label] = pd.to_numeric(report[metric.column], errors="coerce")
            report[f"{metric.label} Percentile"] = percent_rank(
                report[metric.column], inverse=metric.inverse
            )
        report = report.sort_values(
            ["composite_quality_score", "company_id"],
            ascending=[False, True],
            na_position="last",
        ).reset_index(drop=True)
        columns = (
            ["company_id", "company_name"]
            + [metric.label for metric in REPORT_METRICS]
            + [f"{metric.label} Percentile" for metric in REPORT_METRICS]
            + ["is_benchmark"]
        )
        frames[str(group_name)] = report[columns]
    return frames


def _percentile_fill(value: object) -> PatternFill:
    if value in (None, "") or pd.isna(value):
        return NO_FILL
    percentile = float(value)
    if percentile >= 0.75:
        return HIGH_PERCENTILE_FILL
    if percentile <= 0.25:
        return LOW_PERCENTILE_FILL
    return MID_PERCENTILE_FILL


def write_peer_comparison_workbook(
    database: str | Path | sqlite3.Connection,
    output_path: str | Path,
    *,
    peer_groups_path: str | Path = DEFAULT_PEER_GROUPS,
    year: int | None = None,
) -> Path:
    """Generate the 11-sheet peer comparison workbook."""
    universe = load_peer_report_universe(database, year=year)
    assignments = load_peer_groups(peer_groups_path)
    frames = build_peer_comparison_frames(universe, assignments)
    if len(frames) != 11:
        raise ValueError(f"Expected 11 peer groups, found {len(frames)}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    metric_labels = [metric.label for metric in REPORT_METRICS]
    percentile_labels = [f"{label} Percentile" for label in metric_labels]

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for group_name, internal_frame in frames.items():
            benchmarks = internal_frame["is_benchmark"].fillna(False).astype(bool)
            frame = internal_frame.drop(columns="is_benchmark")
            median_row: dict[str, object] = {
                "company_id": "",
                "company_name": "PEER GROUP MEDIAN",
            }
            for column in metric_labels + percentile_labels:
                values = pd.to_numeric(frame[column], errors="coerce").dropna()
                median_row[column] = values.median() if not values.empty else pd.NA
            export_frame = pd.concat([frame, pd.DataFrame([median_row])], ignore_index=True)
            sheet_name = group_name[:31]
            export_frame.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = writer.book[sheet_name]
            worksheet.sheet_view.showGridLines = False
            worksheet.freeze_panes = "C2"
            worksheet.auto_filter.ref = f"A1:AP{len(frame) + 1}"
            worksheet.row_dimensions[1].height = 36

            headers = {cell.value: cell.column for cell in worksheet[1]}
            for cell in worksheet[1]:
                cell.fill = HEADER_FILL
                cell.font = Font(color="FFFFFF", bold=True, size=9)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = THIN_BLUE_BORDER

            for row_number, is_benchmark in enumerate(benchmarks, start=2):
                if is_benchmark:
                    for cell in worksheet[row_number]:
                        cell.fill = BENCHMARK_FILL
                        cell.font = Font(bold=True)
                for label in percentile_labels:
                    cell = worksheet.cell(row=row_number, column=headers[label])
                    cell.fill = _percentile_fill(cell.value)
                    cell.number_format = "0.0%"

            median_row_number = len(frame) + 2
            for cell in worksheet[median_row_number]:
                cell.fill = MEDIAN_FILL
                cell.font = Font(bold=True, color="1F1F1F")
                cell.border = Border(top=Side(style="double", color="1F4E78"))

            for label in percentile_labels:
                worksheet.cell(row=median_row_number, column=headers[label]).number_format = "0.0%"

            for cell in worksheet["A"]:
                cell.alignment = Alignment(horizontal="left")
            for cell in worksheet["B"]:
                cell.alignment = Alignment(horizontal="left")
            worksheet.column_dimensions["A"].width = 16
            worksheet.column_dimensions["B"].width = 38
            for label in metric_labels:
                column = worksheet.cell(row=1, column=headers[label]).column_letter
                worksheet.column_dimensions[column].width = 18
                number_format = (
                    "#,##0.00;[Red](#,##0.00);-"
                    if label in {"FCF", "Market Cap (Cr)"}
                    else "0.00;[Red](0.00);-"
                )
                for row_number in range(2, median_row_number + 1):
                    worksheet.cell(
                        row=row_number, column=headers[label]
                    ).number_format = number_format
            for label in percentile_labels:
                column = worksheet.cell(row=1, column=headers[label]).column_letter
                worksheet.column_dimensions[column].width = 17

    return output.resolve()


def _ensure_peer_percentiles_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS peer_percentiles (
            company_id TEXT NOT NULL REFERENCES companies(id),
            peer_group_name TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL,
            percentile_rank REAL,
            year INTEGER NOT NULL,
            PRIMARY KEY (company_id, peer_group_name, metric, year)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_peer_percentiles_company_year
        ON peer_percentiles(company_id, year)
        """
    )


def populate_peer_percentiles(
    database: str | Path | sqlite3.Connection,
    *,
    peer_groups_path: str | Path = DEFAULT_PEER_GROUPS,
    year: int | None = None,
) -> pd.DataFrame:
    """Compute and upsert peer percentiles into SQLite, returning inserted rows."""
    owns_connection = not isinstance(database, sqlite3.Connection)
    connection = sqlite3.connect(str(database)) if owns_connection else database
    assert isinstance(connection, sqlite3.Connection)
    try:
        ratios = load_ratio_universe(connection, year=year)
        assignments = load_peer_groups(peer_groups_path)
        result = compute_peer_percentiles(ratios, assignments)
        persisted = result.dropna(subset=["year"]).copy()
        with connection:
            _ensure_peer_percentiles_table(connection)
            connection.executemany(
                """
                INSERT INTO peer_percentiles (
                    company_id, peer_group_name, metric, value, percentile_rank, year
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_id, peer_group_name, metric, year) DO UPDATE SET
                    value = excluded.value,
                    percentile_rank = excluded.percentile_rank
                """,
                [
                    (
                        str(row.company_id),
                        str(row.peer_group_name),
                        str(row.metric),
                        None if pd.isna(row.value) else float(row.value),
                        None if pd.isna(row.percentile_rank) else float(row.percentile_rank),
                        int(row.year),
                    )
                    for row in persisted.itertuples(index=False)
                ],
            )
        return persisted.reset_index(drop=True)
    finally:
        if owns_connection:
            connection.close()


def get_company_peer_percentiles(
    database: str | Path | sqlite3.Connection,
    company_id: str,
    *,
    year: int | None = None,
) -> pd.DataFrame | str:
    """Return a company's peer rows or a friendly no-assignment message."""
    owns_connection = not isinstance(database, sqlite3.Connection)
    connection = sqlite3.connect(str(database)) if owns_connection else database
    assert isinstance(connection, sqlite3.Connection)
    try:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='peer_percentiles'"
        ).fetchone()
        if not table_exists:
            return NO_PEER_GROUP_MESSAGE
        year_clause = "AND year = ?" if year is not None else ""
        params: tuple[object, ...] = (company_id, year) if year is not None else (company_id,)
        result = pd.read_sql_query(
            f"""
            SELECT company_id, peer_group_name, metric, value, percentile_rank, year
            FROM peer_percentiles
            WHERE company_id = ? {year_clause}
            ORDER BY year DESC, metric
            """,
            connection,
            params=params,
        )
        return NO_PEER_GROUP_MESSAGE if result.empty else result
    finally:
        if owns_connection:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate peer metric percentile ranks")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--peer-groups", default=str(DEFAULT_PEER_GROUPS))
    parser.add_argument("--year", type=int)
    parser.add_argument("--output", default="output/peer_comparison.xlsx")
    args = parser.parse_args()
    result = populate_peer_percentiles(
        args.database,
        peer_groups_path=args.peer_groups,
        year=args.year,
    )
    groups = result["peer_group_name"].nunique()
    companies = result["company_id"].nunique()
    print(f"Populated {len(result):,} percentile rows for {companies} companies in {groups} groups")
    output = write_peer_comparison_workbook(
        args.database,
        args.output,
        peer_groups_path=args.peer_groups,
        year=args.year,
    )
    print(f"Peer comparison workbook: {output}")


if __name__ == "__main__":
    main()
