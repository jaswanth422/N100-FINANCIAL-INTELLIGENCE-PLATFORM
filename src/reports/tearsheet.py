"""Generate polished two-page company tearsheets with ReportLab."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from .common import (
    BODY,
    GREEN,
    HEADER,
    LIGHT_BLUE,
    LIGHT_GRAY,
    LIGHT_GREEN,
    LIGHT_RED,
    MID_GRAY,
    NAVY,
    RED,
    SECTION,
    SLATE,
    SUBTITLE,
    WHITE,
    CompanyReportData,
    allocation_color,
    balance_sheet_chart,
    cashflow_waterfall_chart,
    figure_image,
    fmt,
    latest_allocation_label,
    latest_ratio,
    load_report_data,
    page_footer,
    paragraph,
    returns_chart,
    revenue_profit_chart,
    wordwrap_table,
)


@dataclass(frozen=True)
class TearsheetBatchStats:
    generated: int
    skipped: int
    output_dir: Path


def _header(data: CompanyReportData, page_label: str = "Company Tearsheet"):
    company_title_style = ParagraphStyle(
        "CompanyHeaderTitle",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=15.5,
        leading=18,
        textColor=WHITE,
        wordWrap="CJK",
    )
    ticker_style = ParagraphStyle(
        "CompanyHeaderTicker",
        parent=company_title_style,
        fontSize=13.5,
        leading=15,
        alignment=2,
    )
    title_block = [
        [
            Paragraph(escape(data.company_name), company_title_style),
            Paragraph(escape(data.company_id), ticker_style),
        ],
        [
            Paragraph(escape(data.sector or "Sector unavailable"), SUBTITLE),
            Paragraph(page_label, SUBTITLE),
        ],
    ]
    return wordwrap_table(
        title_block,
        col_widths=[5.35 * inch, 1.8 * inch],
        style_commands=[
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ],
    )


def _page_two_header(data: CompanyReportData):
    style = ParagraphStyle(
        "PageTwoHeader",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=WHITE,
        wordWrap="CJK",
    )
    return wordwrap_table(
        [
            [
                Paragraph(
                    escape(f"{data.company_name} ({data.company_id})"), style
                ),
                Paragraph("Cash Flow and Capital Allocation", style),
            ]
        ],
        col_widths=[4.4 * inch, 2.75 * inch],
        row_heights=[0.42 * inch],
        style_commands=[
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ],
    )


def _metric_tile(label: str, value: str):
    value_style = ParagraphStyle(
        f"TileValue-{label}",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=16,
        textColor=NAVY,
        alignment=1,
    )
    label_style = ParagraphStyle(
        f"TileLabel-{label}",
        parent=BODY,
        fontSize=7.2,
        leading=8.5,
        textColor=SLATE,
        alignment=1,
        wordWrap="CJK",
    )
    return wordwrap_table(
        [[Paragraph(escape(value), value_style)], [Paragraph(escape(label), label_style)]],
        col_widths=[2.27 * inch],
        row_heights=[0.32 * inch, 0.3 * inch],
        style_commands=[
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE),
            ("BOX", (0, 0), (-1, -1), 0.6, MID_GRAY),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ],
    )


def _kpi_grid(data: CompanyReportData):
    latest = latest_ratio(data)
    ratio = {} if latest is None else latest[1]
    items = [
        ("Revenue CAGR (5Y)", fmt(ratio.get("revenue_cagr_5yr"), suffix="%")),
        ("PAT CAGR (5Y)", fmt(ratio.get("pat_cagr_5yr"), suffix="%")),
        ("ROE", fmt(ratio.get("return_on_equity_pct"), suffix="%")),
        ("ROCE", fmt(ratio.get("return_on_capital_employed_pct"), suffix="%")),
        ("Debt / Equity", fmt(ratio.get("debt_to_equity"), suffix="x", decimals=2)),
        ("CFO Quality", fmt(ratio.get("cfo_quality_score"), suffix="x", decimals=2)),
    ]
    tiles = [_metric_tile(label, value) for label, value in items]
    return wordwrap_table(
        [tiles[:3], tiles[3:]],
        col_widths=[2.37 * inch] * 3,
        row_heights=[0.72 * inch, 0.72 * inch],
        style_commands=[
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ],
    )


def _signal_box(title: str, texts: tuple[str, ...], *, positive: bool):
    color = GREEN if positive else RED
    fill = LIGHT_GREEN if positive else LIGHT_RED
    bullet_rows: list[list[Any]] = [[Paragraph(title, ParagraphStyle(
        f"{title}Heading",
        parent=HEADER,
        textColor=WHITE,
        alignment=0,
        fontSize=9,
    ))]]
    selected = list(texts[:3]) or ["No signal available from the current dataset"]
    for text in selected:
        clipped = text if len(text) <= 155 else f"{text[:152].rstrip()}..."
        bullet_rows.append(
            [
                Paragraph(
                    f'<font color="{color.hexval()}">&#8226;</font> {escape(clipped)}',
                    ParagraphStyle(
                        f"{title}Bullet",
                        parent=BODY,
                        fontSize=7.4,
                        leading=9.1,
                        textColor=SLATE,
                        wordWrap="CJK",
                    ),
                )
            ]
        )
    return wordwrap_table(
        bullet_rows,
        col_widths=[3.5 * inch],
        style_commands=[
            ("BACKGROUND", (0, 0), (-1, 0), color),
            ("BACKGROUND", (0, 1), (-1, -1), fill),
            ("BOX", (0, 0), (-1, -1), 0.6, color),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ],
    )


def _capital_allocation_badge(data: CompanyReportData):
    label = latest_allocation_label(data)
    badge_style = ParagraphStyle(
        "AllocationBadge",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=13,
        textColor=WHITE,
        alignment=1,
        wordWrap="CJK",
    )
    return wordwrap_table(
        [[paragraph("CAPITAL ALLOCATION", SECTION), Paragraph(escape(label), badge_style)]],
        col_widths=[3.5 * inch, 3.5 * inch],
        row_heights=[0.48 * inch],
        style_commands=[
            ("BACKGROUND", (0, 0), (0, 0), LIGHT_GRAY),
            ("BACKGROUND", (1, 0), (1, 0), allocation_color(label)),
            ("BOX", (0, 0), (-1, -1), 0.6, MID_GRAY),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ],
    )


def generate_tearsheet(
    data: CompanyReportData,
    output_path: str | Path,
) -> Path:
    """Generate one exactly two-page company tearsheet."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=0.46 * inch,
        rightMargin=0.46 * inch,
        topMargin=0.38 * inch,
        bottomMargin=0.55 * inch,
        title=f"{data.company_name} ({data.company_id}) Tearsheet",
        author="N100 Financial Intelligence Platform",
        pageCompression=1,
    )
    content: list[Any] = [
        _header(data),
        Spacer(1, 0.11 * inch),
        _kpi_grid(data),
        Spacer(1, 0.1 * inch),
        paragraph("10-Year Financial Performance", SECTION),
        Spacer(1, 0.03 * inch),
        figure_image(revenue_profit_chart(data), 7.08 * inch, 2.08 * inch),
        Spacer(1, 0.07 * inch),
        paragraph("Returns and Capital Efficiency", SECTION),
        Spacer(1, 0.02 * inch),
        figure_image(returns_chart(data), 7.08 * inch, 2.02 * inch),
        PageBreak(),
        Spacer(1, 0.2 * inch),
        _page_two_header(data),
        Spacer(1, 0.08 * inch),
        figure_image(balance_sheet_chart(data), 7.08 * inch, 2.08 * inch),
        Spacer(1, 0.07 * inch),
        figure_image(cashflow_waterfall_chart(data), 7.08 * inch, 2.0 * inch),
        Spacer(1, 0.09 * inch),
        KeepTogether(
            [
                wordwrap_table(
                    [
                        [
                            _signal_box("PROS", data.pros, positive=True),
                            _signal_box("CONS", data.cons, positive=False),
                        ]
                    ],
                    col_widths=[3.56 * inch, 3.56 * inch],
                    style_commands=[
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ],
                ),
                Spacer(1, 0.12 * inch),
                _capital_allocation_badge(data),
            ]
        ),
    ]
    document.build(content, onFirstPage=page_footer, onLaterPages=page_footer)
    return path.resolve()


def _write_skipped(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["company_id", "company_name", "cashflow_years", "reason"]
        )
        writer.writeheader()
        writer.writerows(rows)


def generate_tearsheet_batch(
    database_path: str | Path = "nifty100.db",
    output_dir: str | Path = "reports/tearsheets",
    skipped_path: str | Path = "output/skipped_tearsheets.csv",
    pros_cons_path: str | Path = "output/pros_cons_generated.csv",
    company_ids: set[str] | None = None,
) -> TearsheetBatchStats:
    """Generate one tearsheet for every covered company.

    Companies with partial or unavailable cash-flow history retain their company
    report and show the explicitly labelled N/A cash-flow panel instead of being
    omitted from the 92-company deliverable.
    """
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    generated = 0
    skipped: list[dict[str, object]] = []
    for data in load_report_data(database_path, pros_cons_path):
        if company_ids is not None and data.company_id not in company_ids:
            continue
        generate_tearsheet(data, root / f"{data.company_id}_tearsheet.pdf")
        generated += 1
    _write_skipped(skipped, Path(skipped_path))
    return TearsheetBatchStats(generated, len(skipped), root.resolve())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate N100 company tearsheets")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--output-dir", default="reports/tearsheets")
    parser.add_argument("--skipped", default="output/skipped_tearsheets.csv")
    parser.add_argument("--pros-cons", default="output/pros_cons_generated.csv")
    parser.add_argument("--companies", nargs="*")
    args = parser.parse_args(argv)
    selected = {value.upper() for value in args.companies} if args.companies else None
    stats = generate_tearsheet_batch(
        args.database,
        args.output_dir,
        args.skipped,
        args.pros_cons,
        selected,
    )
    print(f"Generated {stats.generated} tearsheets; skipped {stats.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
