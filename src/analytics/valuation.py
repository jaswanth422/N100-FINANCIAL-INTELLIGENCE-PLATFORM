"""Build the latest-year Nifty 100 valuation summary and exception flags."""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MARKET_CAP = PROJECT_ROOT / "supporting datasets" / "market_cap.xlsx"
DEFAULT_FINANCIAL_RATIOS = PROJECT_ROOT / "supporting datasets" / "financial_ratios.xlsx"
DEFAULT_COMPANIES = PROJECT_ROOT / "companies.xlsx"
DEFAULT_SECTORS = PROJECT_ROOT / "supporting datasets" / "sectors.xlsx"
DEFAULT_DATABASE = PROJECT_ROOT / "nifty100.db"
DEFAULT_WORKBOOK_OUTPUT = PROJECT_ROOT / "output" / "valuation_summary.xlsx"
DEFAULT_FLAGS_OUTPUT = PROJECT_ROOT / "output" / "valuation_flags.csv"

SUMMARY_COLUMNS = [
    "company_id",
    "company_name",
    "sector",
    "P/E",
    "P/B",
    "EV/EBITDA",
    "FCF_yield_pct",
    "5yr_median_PE",
    "PE_vs_sector_median_pct",
    "flag",
]

HEADER_FILL = PatternFill(fill_type="solid", fgColor="17365D")
CAUTION_FILL = PatternFill(fill_type="solid", fgColor="F4CCCC")
DISCOUNT_FILL = PatternFill(fill_type="solid", fgColor="D9EAD3")
FAIR_FILL = PatternFill(fill_type="solid", fgColor="FFF2CC")


def _normalise_year(values: pd.Series) -> pd.Series:
    """Extract a four-digit fiscal year from numeric or labelled source values."""
    extracted = values.astype("string").str.extract(r"(\d{4})", expand=False)
    return pd.to_numeric(extracted, errors="coerce").astype("Int64")


def load_valuation_sources(
    market_cap_path: str | Path = DEFAULT_MARKET_CAP,
    financial_ratios_path: str | Path = DEFAULT_FINANCIAL_RATIOS,
    companies_path: str | Path = DEFAULT_COMPANIES,
    sectors_path: str | Path = DEFAULT_SECTORS,
    database_path: str | Path | None = DEFAULT_DATABASE,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the four source workbooks required for the valuation analysis."""
    market_cap = pd.read_excel(market_cap_path, engine="openpyxl")
    financial_ratios = pd.read_excel(financial_ratios_path, engine="openpyxl")
    financial_ratios["_source_priority"] = 0
    if database_path is not None and Path(database_path).is_file():
        with closing(sqlite3.connect(database_path)) as connection:
            database_ratios = pd.read_sql_query(
                """
                SELECT id, company_id, year, free_cash_flow_cr
                FROM financial_ratios
                """,
                connection,
            )
        database_ratios["_source_priority"] = 1
        financial_ratios = pd.concat(
            [financial_ratios, database_ratios],
            ignore_index=True,
            sort=False,
        )
    companies = pd.read_excel(companies_path, header=1, engine="openpyxl")
    sectors = pd.read_excel(sectors_path, engine="openpyxl")
    return market_cap, financial_ratios, companies, sectors


def build_valuation_summary(
    market_cap: pd.DataFrame,
    financial_ratios: pd.DataFrame,
    companies: pd.DataFrame,
    sectors: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute latest valuation metrics, five-year medians, and relative flags."""
    market = market_cap.copy()
    ratios = financial_ratios.copy()
    company_directory = companies.copy()
    sector_directory = sectors.copy()

    market["year"] = _normalise_year(market["year"])
    ratios["year"] = _normalise_year(ratios["year"])
    ratios["_source_priority"] = ratios.get("_source_priority", 0)
    latest_year = int(market["year"].max())

    market = market.sort_values("id").drop_duplicates(["company_id", "year"], keep="last")
    ratios = ratios.sort_values(["_source_priority", "id"]).drop_duplicates(
        ["company_id", "year"],
        keep="last",
    )

    latest_market = market.loc[market["year"].eq(latest_year)].copy()
    latest_ratios = ratios.loc[ratios["year"].eq(latest_year), ["company_id", "free_cash_flow_cr"]]

    five_year_start = latest_year - 4
    five_year_medians = (
        market.loc[market["year"].between(five_year_start, latest_year)]
        .groupby("company_id", as_index=False)["pe_ratio"]
        .median()
        .rename(columns={"pe_ratio": "5yr_median_PE"})
    )

    company_directory["company_name"] = (
        company_directory["company_name"]
        .astype("string")
        .str.replace(r"[\r\n]+", " ", regex=True)
        .str.strip()
    )
    company_names = company_directory[["id", "company_name"]].rename(
        columns={"id": "company_id"}
    )
    sector_names = sector_directory[["company_id", "broad_sector"]].rename(
        columns={"broad_sector": "sector"}
    )

    valuation = (
        latest_market.merge(latest_ratios, on="company_id", how="left", validate="one_to_one")
        .merge(five_year_medians, on="company_id", how="left", validate="one_to_one")
        .merge(company_names, on="company_id", how="left", validate="one_to_one")
        .merge(sector_names, on="company_id", how="left", validate="one_to_one")
    )

    valuation["FCF_yield_pct"] = np.where(
        pd.to_numeric(valuation["market_cap_crore"], errors="coerce").ne(0),
        pd.to_numeric(valuation["free_cash_flow_cr"], errors="coerce")
        / pd.to_numeric(valuation["market_cap_crore"], errors="coerce")
        * 100.0,
        np.nan,
    )

    sector_medians = (
        valuation.groupby("sector", as_index=False)["pe_ratio"]
        .median()
        .rename(columns={"pe_ratio": "sector_median_PE"})
        .sort_values("sector")
        .reset_index(drop=True)
    )
    valuation = valuation.merge(
        sector_medians,
        on="sector",
        how="left",
        validate="many_to_one",
    )
    valuation["PE_vs_sector_median_pct"] = (
        valuation["pe_ratio"] / valuation["sector_median_PE"] - 1.0
    ) * 100.0

    valid_pe = valuation["pe_ratio"].notna() & valuation["sector_median_PE"].notna()
    valuation["flag"] = pd.Series("N/A", index=valuation.index, dtype="string")
    valuation.loc[valid_pe, "flag"] = "Fair"
    valuation.loc[
        valid_pe & valuation["pe_ratio"].gt(valuation["sector_median_PE"] * 1.5),
        "flag",
    ] = "Caution"
    valuation.loc[
        valid_pe & valuation["pe_ratio"].lt(valuation["sector_median_PE"] * 0.7),
        "flag",
    ] = "Discount"

    summary = valuation.rename(
        columns={
            "pe_ratio": "P/E",
            "pb_ratio": "P/B",
            "ev_ebitda": "EV/EBITDA",
        }
    )[SUMMARY_COLUMNS].sort_values("company_id", ignore_index=True)

    sector_medians.insert(0, "year", latest_year)
    sector_medians["company_count"] = sector_medians["sector"].map(
        valuation.groupby("sector")["company_id"].nunique()
    )
    return summary, sector_medians


def _format_summary_workbook(
    writer: pd.ExcelWriter,
    summary: pd.DataFrame,
    sector_medians: pd.DataFrame,
) -> None:
    workbook = writer.book
    summary_sheet = writer.sheets["Valuation Summary"]
    sector_sheet = writer.sheets["Sector Medians"]

    for sheet in (summary_sheet, sector_sheet):
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 28
        for cell in sheet[1]:
            cell.fill = HEADER_FILL
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")

    summary_widths = [16, 38, 26, 12, 12, 14, 16, 17, 25, 14]
    for column_index, width in enumerate(summary_widths, start=1):
        summary_sheet.column_dimensions[get_column_letter(column_index)].width = width

    for column in ("D", "E", "F", "H"):
        for cell in summary_sheet[column][1:]:
            cell.number_format = '0.00x;[Red](0.00x);-'
    for column in ("G", "I"):
        for cell in summary_sheet[column][1:]:
            cell.number_format = "0.00\\%"
    for row in range(2, len(summary) + 2):
        summary_sheet.row_dimensions[row].height = 28
        summary_sheet.cell(row=row, column=2).alignment = Alignment(
            vertical="center",
            wrap_text=True,
        )
        flag_cell = summary_sheet.cell(row=row, column=10)
        if flag_cell.value == "Caution":
            flag_cell.fill = CAUTION_FILL
        elif flag_cell.value == "Discount":
            flag_cell.fill = DISCOUNT_FILL
        elif flag_cell.value == "Fair":
            flag_cell.fill = FAIR_FILL
    summary_sheet.auto_filter.ref = f"A1:J{len(summary) + 1}"

    flag_range = f"J2:J{len(summary) + 1}"
    summary_sheet.conditional_formatting.add(
        flag_range,
        FormulaRule(formula=['J2="Caution"'], fill=CAUTION_FILL),
    )
    summary_sheet.conditional_formatting.add(
        flag_range,
        FormulaRule(formula=['J2="Discount"'], fill=DISCOUNT_FILL),
    )
    summary_sheet.conditional_formatting.add(
        flag_range,
        FormulaRule(formula=['J2="Fair"'], fill=FAIR_FILL),
    )

    sector_widths = [8, 22, 14]
    for column_index, width in enumerate(sector_widths, start=1):
        sector_sheet.column_dimensions[get_column_letter(column_index)].width = width
    for cell in sector_sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for cell in sector_sheet["C"][1:]:
        cell.number_format = '0.00x;[Red](0.00x);-'
    sector_sheet.auto_filter.ref = f"A1:C{len(sector_medians) + 1}"

    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True


def write_valuation_outputs(
    summary: pd.DataFrame,
    sector_medians: pd.DataFrame,
    workbook_path: str | Path = DEFAULT_WORKBOOK_OUTPUT,
    flags_path: str | Path = DEFAULT_FLAGS_OUTPUT,
) -> tuple[Path, Path]:
    """Write the formatted summary workbook and non-fair flags CSV."""
    workbook_output = Path(workbook_path)
    flags_output = Path(flags_path)
    workbook_output.parent.mkdir(parents=True, exist_ok=True)
    flags_output.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(workbook_output, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Valuation Summary", index=False)
        sector_medians[["year", "sector", "sector_median_PE"]].rename(
            columns={
                "year": "Year",
                "sector": "Sector",
                "sector_median_PE": "Median P/E",
            }
        ).to_excel(writer, sheet_name="Sector Medians", index=False)
        _format_summary_workbook(writer, summary, sector_medians)

    flags = summary.loc[summary["flag"].isin(["Caution", "Discount"])].copy()
    flags = flags.merge(
        sector_medians[["sector", "sector_median_PE"]],
        on="sector",
        how="left",
        validate="many_to_one",
    )
    flags.to_csv(flags_output, index=False, lineterminator="\n")
    return workbook_output.resolve(), flags_output.resolve()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Nifty 100 valuation summary")
    parser.add_argument("--market-cap", default=str(DEFAULT_MARKET_CAP))
    parser.add_argument("--financial-ratios", default=str(DEFAULT_FINANCIAL_RATIOS))
    parser.add_argument("--companies", default=str(DEFAULT_COMPANIES))
    parser.add_argument("--sectors", default=str(DEFAULT_SECTORS))
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    parser.add_argument("--workbook-output", default=str(DEFAULT_WORKBOOK_OUTPUT))
    parser.add_argument("--flags-output", default=str(DEFAULT_FLAGS_OUTPUT))
    args = parser.parse_args(argv)

    sources = load_valuation_sources(
        args.market_cap,
        args.financial_ratios,
        args.companies,
        args.sectors,
        args.database,
    )
    summary, sector_medians = build_valuation_summary(*sources)
    workbook_path, flags_path = write_valuation_outputs(
        summary,
        sector_medians,
        args.workbook_output,
        args.flags_output,
    )
    print(f"Wrote {len(summary)} company valuations to {workbook_path}")
    print(f"Wrote {(summary['flag'] != 'Fair').sum()} valuation flags to {flags_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
