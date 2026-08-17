"""Generate sector median and company-detail PDF reports."""

from __future__ import annotations

import argparse
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from .common import (
    BODY,
    HEADER,
    LIGHT_BLUE,
    LIGHT_GRAY,
    MID_GRAY,
    NAVY,
    SECTION,
    SLATE,
    WHITE,
    CompanyReportData,
    finite,
    fmt,
    latest_ratio,
    load_report_data,
    page_footer,
    paragraph,
    wordwrap_table,
)

METRICS = (
    ("Composite Score", "composite_quality_score", "", 1),
    ("Revenue CAGR 5Y", "revenue_cagr_5yr", "%", 1),
    ("PAT CAGR 5Y", "pat_cagr_5yr", "%", 1),
    ("ROE", "return_on_equity_pct", "%", 1),
    ("ROCE", "return_on_capital_employed_pct", "%", 1),
    ("Debt / Equity", "debt_to_equity", "x", 2),
    ("CFO Quality", "cfo_quality_score", "x", 2),
    ("FCF Conversion", "fcf_conversion_rate_pct", "%", 1),
)

UTILITY_SUBSECTORS = {
    "Gas Distribution",
    "Power & Utilities",
    "Power Transmission",
    "Renewable Energy",
}


def reporting_sector(data: CompanyReportData) -> str:
    """Restore Utilities as the eleventh report sector from source sub-sectors."""
    if data.sector == "Energy" and data.sub_sector in UTILITY_SUBSECTORS:
        return "Utilities"
    return data.sector or "Unclassified"


def _latest_values(data: CompanyReportData) -> dict[str, Any]:
    latest = latest_ratio(data)
    return {} if latest is None else latest[1]


def _median(companies: list[CompanyReportData], field: str) -> float | None:
    values = [
        number
        for company in companies
        if (number := finite(_latest_values(company).get(field))) is not None
    ]
    return statistics.median(values) if values else None


def _median_tiles(companies: list[CompanyReportData]):
    tile_style = ParagraphStyle(
        "SectorTileValue",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=15,
        textColor=NAVY,
        alignment=1,
    )
    label_style = ParagraphStyle(
        "SectorTileLabel",
        parent=BODY,
        fontSize=7.2,
        leading=8.4,
        textColor=SLATE,
        alignment=1,
        wordWrap="CJK",
    )
    tiles = []
    for label, field, suffix, decimals in METRICS:
        tiles.append(
            wordwrap_table(
                [
                    [
                        Paragraph(
                            fmt(
                                _median(companies, field),
                                suffix=suffix,
                                decimals=decimals,
                            ),
                            tile_style,
                        )
                    ],
                    [Paragraph(label, label_style)],
                ],
                col_widths=[2.15 * inch],
                row_heights=[0.34 * inch, 0.3 * inch],
                style_commands=[
                    ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
                    ("BOX", (0, 0), (-1, -1), 0.6, MID_GRAY),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ],
            )
        )
    return wordwrap_table(
        [tiles[:4], tiles[4:]],
        col_widths=[2.24 * inch] * 4,
        row_heights=[0.72 * inch, 0.72 * inch],
        style_commands=[
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ],
    )


def _title(sector: str, company_count: int):
    title_style = ParagraphStyle(
        "SectorTitle",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=22,
        textColor=WHITE,
    )
    return wordwrap_table(
        [
            [
                Paragraph(f"{sector} Sector Report", title_style),
                Paragraph(f"{company_count} companies", HEADER),
            ]
        ],
        col_widths=[7.1 * inch, 2 * inch],
        row_heights=[0.58 * inch],
        style_commands=[
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ],
    )


def generate_sector_report(
    sector: str,
    companies: list[CompanyReportData],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=0.42 * inch,
        rightMargin=0.42 * inch,
        topMargin=0.38 * inch,
        bottomMargin=0.55 * inch,
        title=f"{sector} Sector Report",
        author="N100 Financial Intelligence Platform",
        pageCompression=1,
    )
    roster = ", ".join(company.company_id for company in companies)
    content: list[Any] = [
        _title(sector, len(companies)),
        Spacer(1, 0.18 * inch),
        paragraph("Latest-Year Median KPIs", SECTION),
        Spacer(1, 0.08 * inch),
        _median_tiles(companies),
        Spacer(1, 0.22 * inch),
        paragraph("Sector Constituents", SECTION),
        Spacer(1, 0.08 * inch),
        wordwrap_table(
            [[roster or "No companies mapped to this sector"]],
            col_widths=[9.05 * inch],
            style_commands=[
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.6, MID_GRAY),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ],
        ),
        Spacer(1, 0.18 * inch),
        paragraph(
            "Utilities is restored as a reporting sector from Energy source rows whose "
            "sub-sector is gas distribution, power, transmission, or renewables.",
            BODY,
        ),
        PageBreak(),
        Spacer(1, 0.2 * inch),
        _title(sector, len(companies)),
        Spacer(1, 0.13 * inch),
        paragraph("Company KPI Detail", SECTION),
        Spacer(1, 0.06 * inch),
    ]
    headers = ["Ticker", "Company"] + [metric[0] for metric in METRICS]
    rows: list[list[object]] = [headers]
    for company in sorted(companies, key=lambda item: item.company_id):
        values = _latest_values(company)
        rows.append(
            [company.company_id, company.company_name]
            + [
                fmt(values.get(field), suffix=suffix, decimals=decimals)
                for _, field, suffix, decimals in METRICS
            ]
        )
    if len(rows) == 1:
        rows.append(["N/A", "No companies mapped"] + ["N/A"] * len(METRICS))
    content.append(
        wordwrap_table(
            rows,
            col_widths=[1.0 * inch, 2.1 * inch] + [0.9 * inch] * len(METRICS),
            repeat_rows=1,
            style_commands=[
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, MID_GRAY),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ],
        )
    )
    document.build(content, onFirstPage=page_footer, onLaterPages=page_footer)
    return path.resolve()


def generate_sector_batch(
    database_path: str | Path = "nifty100.db",
    output_dir: str | Path = "reports/sector",
    pros_cons_path: str | Path = "output/pros_cons_generated.csv",
) -> list[Path]:
    grouped: dict[str, list[CompanyReportData]] = defaultdict(list)
    for company in load_report_data(database_path, pros_cons_path):
        grouped[reporting_sector(company)].append(company)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for sector, companies in sorted(grouped.items()):
        slug = re.sub(r"[^a-z0-9]+", "_", sector.lower()).strip("_")
        paths.append(generate_sector_report(sector, companies, root / f"{slug}_report.pdf"))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate N100 sector reports")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--output-dir", default="reports/sector")
    parser.add_argument("--pros-cons", default="output/pros_cons_generated.csv")
    args = parser.parse_args(argv)
    paths = generate_sector_batch(args.database, args.output_dir, args.pros_cons)
    print(f"Generated {len(paths)} sector reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
