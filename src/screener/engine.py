"""Threshold-based financial screener and the six Sprint 3 presets."""

from __future__ import annotations

import argparse
import operator
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import yaml  # type: ignore[import-untyped]
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

from analytics.composite import compute_composite_scores
from analytics.populate_ratios import composite_quality_score

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "screener_config.yaml"

# Public filter names map to the normalized universe columns.  The aliases keep
# custom screens convenient while accepting names already used by the database.
METRIC_COLUMNS: dict[str, tuple[str, ...]] = {
    "roe": ("return_on_equity_pct", "roe_pct", "roe"),
    "net_profit_margin": ("net_profit_margin_pct", "net_margin_pct"),
    "debt_to_equity": ("debt_to_equity", "de_ratio", "d/e"),
    "free_cash_flow": ("free_cash_flow_cr", "fcf", "free_cash_flow"),
    "revenue_cagr_3yr": ("revenue_cagr_3yr",),
    "revenue_cagr_5yr": ("revenue_cagr_5yr",),
    "pat_cagr_5yr": ("pat_cagr_5yr",),
    "operating_margin": ("operating_profit_margin_pct", "opm_pct", "opm"),
    "pe": ("pe_ratio", "pe"),
    "pb": ("pb_ratio", "pb"),
    "dividend_yield": ("dividend_yield_pct", "dividend_yield"),
    "dividend_payout": ("dividend_payout_ratio_pct", "dividend_payout"),
    "interest_coverage": ("interest_coverage", "icr"),
    "cfo_quality": ("cfo_quality_score", "cfo_pat_score"),
    "market_cap": ("market_cap_crore", "market_cap"),
    "net_profit": ("net_profit_cr", "net_profit"),
    "eps_cagr_5yr": ("eps_cagr_5yr", "eps_cagr"),
    "asset_turnover": ("asset_turnover",),
    "sales": ("sales_cr", "sales", "revenue"),
    "previous_debt_to_equity": ("previous_debt_to_equity",),
}

EXPORT_ID_COLUMNS = ["company_id", "company_name", "year", "broad_sector", "sub_sector"]
EXPORT_KPI_COLUMNS = [
    "composite_quality_score",
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "debt_to_equity",
    "previous_debt_to_equity",
    "interest_coverage",
    "free_cash_flow_cr",
    "fcf_cagr_5yr",
    "cfo_quality_score",
    "revenue_cagr_3yr",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "eps_cagr_5yr",
    "pe_ratio",
    "pb_ratio",
    "dividend_yield_pct",
    "dividend_payout_ratio_pct",
    "sales_cr",
]

GREEN_FILL = PatternFill(fill_type="solid", fgColor="C6EFCE")
RED_FILL = PatternFill(fill_type="solid", fgColor="FFC7CE")
HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E78")

FILTER_KEY_MAP: dict[str, tuple[str, str]] = {
    "roe_min": ("roe", "gte"),
    "de_max": ("debt_to_equity", "lte"),
    "fcf_min": ("free_cash_flow", "gte"),
    "revenue_cagr_5yr_min": ("revenue_cagr_5yr", "gte"),
    "pat_cagr_5yr_min": ("pat_cagr_5yr", "gte"),
    "opm_min": ("operating_margin", "gte"),
    "pe_max": ("pe", "lte"),
    "pb_max": ("pb", "lte"),
    "dividend_yield_min": ("dividend_yield", "gte"),
    "icr_min": ("interest_coverage", "gte"),
    "market_cap_min": ("market_cap", "gte"),
    "net_profit_min": ("net_profit", "gte"),
    "eps_cagr_min": ("eps_cagr_5yr", "gte"),
    "eps_cagr_5yr_min": ("eps_cagr_5yr", "gte"),
    "asset_turnover_min": ("asset_turnover", "gte"),
    "sales_min": ("sales", "gte"),
}

COMPARATORS = {
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "eq": operator.eq,
}


def load_screener_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load and minimally validate ``screener_config.yaml``."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or not isinstance(config.get("presets"), dict):
        raise ValueError(f"Invalid screener config at {config_path}: 'presets' must be a mapping")
    return config


def _column_for(frame: pd.DataFrame, metric: str) -> str:
    candidates = METRIC_COLUMNS.get(metric, (metric,))
    try:
        return next(column for column in candidates if column in frame.columns)
    except StopIteration as exc:
        raise KeyError(
            f"Metric '{metric}' requires one of these columns: {', '.join(candidates)}"
        ) from exc


def _sector_column(frame: pd.DataFrame) -> str | None:
    return next(
        (name for name in ("broad_sector", "sector") if name in frame.columns),
        None,
    )


def _normalise_custom_filters(
    filters: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(filters, Mapping):
        conditions: list[dict[str, Any]] = []
        for key, value in filters.items():
            if value is None:
                continue
            if key not in FILTER_KEY_MAP:
                supported = ", ".join(sorted(FILTER_KEY_MAP))
                raise KeyError(f"Unknown filter '{key}'. Supported custom filters: {supported}")
            metric, comparison = FILTER_KEY_MAP[key]
            conditions.append({"metric": metric, "operator": comparison, "value": value})
        return conditions
    return [dict(condition) for condition in filters]


def _add_quality_score(frame: pd.DataFrame) -> pd.DataFrame:
    if "composite_quality_score" in frame.columns:
        return frame

    def optional_metric(metric: str) -> pd.Series:
        candidates = METRIC_COLUMNS.get(metric, (metric,))
        column = next((name for name in candidates if name in frame.columns), None)
        if column is None:
            return pd.Series(float("nan"), index=frame.index)
        return pd.to_numeric(frame[column], errors="coerce")

    roe = optional_metric("roe")
    debt = optional_metric("debt_to_equity")
    net_margin = optional_metric("net_profit_margin")
    interest_coverage = optional_metric("interest_coverage")
    cfo_quality = optional_metric("cfo_quality")
    frame["composite_quality_score"] = [
        composite_quality_score(
            roe_pct=roe_value,
            net_margin_pct=margin_value,
            debt_to_equity_ratio=debt_value,
            interest_coverage_ratio=coverage_value,
            cfo_pat_score=cfo_value,
        )
        for roe_value, margin_value, debt_value, coverage_value, cfo_value in zip(
            roe, net_margin, debt, interest_coverage, cfo_quality, strict=True
        )
    ]
    return frame


def _condition_mask(frame: pd.DataFrame, condition: Mapping[str, Any]) -> pd.Series:
    """Evaluate one normalized preset condition against every row."""
    metric = str(condition["metric"])
    comparison = str(condition.get("operator", "gte")).lower()
    column = _column_for(frame, metric)
    left = pd.to_numeric(frame[column], errors="coerce")

    if metric == "interest_coverage":
        label_column = next(
            (name for name in ("icr_label", "interest_coverage_label") if name in frame),
            None,
        )
        if label_column:
            normalised_labels = (
                frame[label_column]
                .astype("string")
                .str.strip()
                .str.casefold()
                .str.replace("-", " ", regex=False)
                .str.replace(r"\s+", " ", regex=True)
            )
            debt_free = normalised_labels.eq("debt free").fillna(False)
            left = left.mask(debt_free, float("inf"))

    if comparison == "declining":
        other_metric = str(condition.get("compare_to", "previous_debt_to_equity"))
        right = pd.to_numeric(frame[_column_for(frame, other_metric)], errors="coerce")
        condition_mask = left.lt(right)
    else:
        if comparison not in COMPARATORS:
            raise ValueError(f"Unsupported operator '{comparison}' for metric '{metric}'")
        if "value" not in condition:
            raise ValueError(f"Filter for metric '{metric}' is missing 'value'")
        condition_mask = COMPARATORS[comparison](left, float(condition["value"]))

    financials_exempt = bool(condition.get("financials_exempt", True))
    if metric == "debt_to_equity" and comparison in {"lt", "lte"} and financials_exempt:
        sector_column = _sector_column(frame)
        if sector_column:
            is_financial = (
                frame[sector_column].astype("string").str.strip().str.casefold().eq("financials")
            )
            condition_mask = condition_mask | is_financial
    return condition_mask.fillna(False)


def apply_filters(
    financial_ratios: pd.DataFrame,
    filters: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    """Apply custom thresholds and return quality-score-ranked matching rows.

    Missing values fail a condition. Financial-sector rows automatically pass
    only D/E *upper-bound* filters. A ``Debt Free`` ICR label is evaluated as
    positive infinity.
    """
    frame = _add_quality_score(financial_ratios.copy())
    conditions = _normalise_custom_filters(filters)
    mask = pd.Series(True, index=frame.index, dtype=bool)

    for condition in conditions:
        mask &= _condition_mask(frame, condition)

    result = frame.loc[mask].copy()
    sort_columns = ["composite_quality_score"]
    ascending = [False]
    for candidate in ("company_name", "company_id"):
        if candidate in result.columns:
            sort_columns.append(candidate)
            ascending.append(True)
            break
    return result.sort_values(sort_columns, ascending=ascending, na_position="last").reset_index(
        drop=True
    )


class ScreenerEngine:
    """Run configured presets or caller-provided custom thresholds."""

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG) -> None:
        self.config = load_screener_config(config_path)

    @property
    def presets(self) -> tuple[str, ...]:
        return tuple(self.config["presets"])

    def run_preset(self, financial_ratios: pd.DataFrame, preset: str) -> pd.DataFrame:
        try:
            filters = self.config["presets"][preset]["filters"]
        except KeyError as exc:
            message = f"Unknown preset '{preset}'. Available: {', '.join(self.presets)}"
            raise KeyError(message) from exc
        return apply_filters(financial_ratios, filters)

    def run_custom(
        self, financial_ratios: pd.DataFrame, **thresholds: float | None
    ) -> pd.DataFrame:
        return apply_filters(financial_ratios, thresholds)


def load_latest_universe(database: str | Path | sqlite3.Connection) -> pd.DataFrame:
    """Build one latest-year screener row per company from the normalized DB."""
    if isinstance(database, sqlite3.Connection):
        connection = database
        owns_connection = False
    else:
        connection = sqlite3.connect(str(database))
        owns_connection = True
    ratio_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(financial_ratios)").fetchall()
    }
    fcf_cagr_expression = (
        "r.fcf_cagr_5yr" if "fcf_cagr_5yr" in ratio_columns else "NULL AS fcf_cagr_5yr"
    )
    coverage_expression = (
        "r.composite_score_coverage_pct"
        if "composite_score_coverage_pct" in ratio_columns
        else "NULL AS composite_score_coverage_pct"
    )
    query = f"""
        WITH ratios AS (
            SELECT r.*, ROW_NUMBER() OVER (
                PARTITION BY company_id ORDER BY year DESC, id DESC
            ) AS latest_rank
            FROM financial_ratios r WHERE year IS NOT NULL
        ), market AS (
            SELECT m.*, ROW_NUMBER() OVER (
                PARTITION BY company_id ORDER BY year DESC, id DESC
            ) AS latest_rank
            FROM market_cap m WHERE year IS NOT NULL
        ), pnl AS (
            SELECT f.*, ROW_NUMBER() OVER (
                PARTITION BY company_id ORDER BY year DESC, id DESC
            ) AS latest_rank
            FROM financial_statements f
            WHERE statement_type = 'profit_and_loss' AND year IS NOT NULL
        )
        SELECT r.company_id,
               REPLACE(REPLACE(c.company_name, char(10), ' '), char(13), ' ') AS company_name,
               r.year,
               s.broad_sector,
               s.sub_sector,
               r.return_on_equity_pct,
               r.return_on_capital_employed_pct,
               r.net_profit_margin_pct,
               r.debt_to_equity,
               previous.debt_to_equity AS previous_debt_to_equity,
               r.free_cash_flow_cr,
               {fcf_cagr_expression},
               r.cfo_quality_score,
               r.revenue_cagr_3yr,
               r.revenue_cagr_5yr,
               r.pat_cagr_5yr,
               r.operating_profit_margin_pct,
               r.interest_coverage,
               r.icr_label,
               r.eps_cagr_5yr,
               r.asset_turnover,
               r.dividend_payout_ratio_pct,
               r.composite_quality_score,
               {coverage_expression},
               m.market_cap_crore,
               m.pe_ratio,
               m.pb_ratio,
               m.dividend_yield_pct,
               f.net_profit AS net_profit_cr,
               f.sales AS sales_cr
        FROM ratios r
        JOIN companies c ON c.id = r.company_id
        LEFT JOIN ratios previous
               ON previous.company_id = r.company_id AND previous.latest_rank = 2
        LEFT JOIN sectors s ON s.company_id = r.company_id
        LEFT JOIN market m ON m.company_id = r.company_id AND m.latest_rank = 1
        LEFT JOIN pnl f ON f.company_id = r.company_id AND f.latest_rank = 1
        WHERE r.latest_rank = 1
        ORDER BY r.company_id
    """
    try:
        universe = pd.read_sql_query(query, connection)
        return compute_composite_scores(universe)
    finally:
        if owns_connection:
            connection.close()


def _condition_description(condition: Mapping[str, Any]) -> str:
    operator_name = str(condition.get("operator", "gte")).lower()
    if operator_name == "declining":
        return f"Pass: lower than {condition.get('compare_to', 'previous_debt_to_equity')}"
    symbols = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}
    return f"Pass: {symbols.get(operator_name, operator_name)} {condition.get('value')}"


def _format_preset_sheet(worksheet: Any) -> None:
    """Apply readable widths and numeric formats without changing cell values."""
    widths = {
        "company_id": 16,
        "company_name": 38,
        "year": 10,
        "broad_sector": 24,
        "sub_sector": 24,
    }
    percent_columns = {
        "composite_quality_score",
        "return_on_equity_pct",
        "return_on_capital_employed_pct",
        "net_profit_margin_pct",
        "operating_profit_margin_pct",
        "fcf_cagr_5yr",
        "revenue_cagr_3yr",
        "revenue_cagr_5yr",
        "pat_cagr_5yr",
        "eps_cagr_5yr",
        "dividend_yield_pct",
        "dividend_payout_ratio_pct",
    }
    currency_columns = {"free_cash_flow_cr", "sales_cr"}
    for cell in worksheet[1]:
        name = str(cell.value)
        worksheet.column_dimensions[cell.column_letter].width = widths.get(name, 18)
        for data_cell in worksheet.iter_cols(
            min_col=cell.column, max_col=cell.column, min_row=2, max_row=worksheet.max_row
        ):
            for item in data_cell:
                if name in percent_columns:
                    item.number_format = "0.00"
                elif name in currency_columns:
                    item.number_format = "#,##0.00"
                elif name not in EXPORT_ID_COLUMNS:
                    item.number_format = "0.00"


def write_preset_workbook(
    universe: pd.DataFrame,
    output_path: str | Path,
    engine: ScreenerEngine | None = None,
) -> pd.DataFrame:
    """Write one score-ranked, threshold-coloured sheet per screener preset.

    Every preset sheet contains the full universe so both passing (green) and
    failing (red) threshold cells remain visible. The returned summary records
    match counts without adding a seventh workbook sheet.
    """
    active_engine = engine or ScreenerEngine()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    scored_universe = compute_composite_scores(universe)
    ranked_universe = scored_universe.sort_values(
        ["composite_quality_score", "company_id"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)
    missing_export_columns = [
        column for column in EXPORT_ID_COLUMNS + EXPORT_KPI_COLUMNS if column not in ranked_universe
    ]
    for column in missing_export_columns:
        ranked_universe[column] = pd.NA
    export_frame = ranked_universe[EXPORT_ID_COLUMNS + EXPORT_KPI_COLUMNS]

    summaries: list[dict[str, Any]] = []
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for preset in active_engine.presets:
            details = active_engine.config["presets"][preset]
            result = active_engine.run_preset(universe, preset)
            count = len(result)
            summaries.append(
                {
                    "preset": details["name"],
                    "company_count": count,
                    "target_min": 5,
                    "target_max": 50,
                    "acceptance_status": "PASS" if 5 <= count <= 50 else "REVIEW",
                }
            )
            sheet_name = preset[:31]
            export_frame.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = writer.book[sheet_name]
            worksheet.freeze_panes = "F2"
            worksheet.auto_filter.ref = worksheet.dimensions
            worksheet.row_dimensions[1].height = 30
            for cell in worksheet[1]:
                cell.fill = HEADER_FILL
                cell.font = Font(color="FFFFFF", bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            header_positions = {cell.value: cell.column for cell in worksheet[1]}
            conditions = _normalise_custom_filters(details["filters"])
            for condition in conditions:
                metric_column = _column_for(ranked_universe, str(condition["metric"]))
                if metric_column not in header_positions:
                    continue
                passes = _condition_mask(ranked_universe, condition)
                excel_column = header_positions[metric_column]
                description = _condition_description(condition)
                worksheet.cell(row=1, column=excel_column).comment = Comment(description, "Codex")
                for row_number, passed in enumerate(passes, start=2):
                    worksheet.cell(row=row_number, column=excel_column).fill = (
                        GREEN_FILL if passed else RED_FILL
                    )

            _format_preset_sheet(worksheet)
    return pd.DataFrame(summaries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the six configured financial screeners")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", default="output/screener_output.xlsx")
    args = parser.parse_args()
    universe = load_latest_universe(args.database)
    summary = write_preset_workbook(universe, args.output, ScreenerEngine(args.config))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
