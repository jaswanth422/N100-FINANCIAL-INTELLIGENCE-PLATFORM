"""Generate an alphabetical one-page-per-company portfolio summary."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from .common import (
    BODY,
    GREEN,
    LIGHT_BLUE,
    LIGHT_GRAY,
    MID_GRAY,
    NAVY,
    RED,
    SECTION,
    SLATE,
    WHITE,
    CompanyReportData,
    fmt,
    latest_ratio,
    load_report_data,
    page_footer,
    paragraph,
    trend_direction,
    wordwrap_table,
)

PORTFOLIO_METRICS = (
    ("Revenue CAGR 5Y", "revenue_cagr_5yr", "%", 1, False),
    ("PAT CAGR 5Y", "pat_cagr_5yr", "%", 1, False),
    ("ROE", "return_on_equity_pct", "%", 1, False),
    ("ROCE", "return_on_capital_employed_pct", "%", 1, False),
    ("Debt / Equity", "debt_to_equity", "x", 2, True),
    ("CFO Quality", "cfo_quality_score", "x", 2, False),
)


class TrendArrow(Flowable):
    """Small vector arrow that does not depend on a Unicode font glyph."""

    def __init__(self, direction: str):
        super().__init__()
        self.direction = direction
        self.width = 18
        self.height = 18

    def draw(self) -> None:
        canvas = self.canv
        if self.direction == "up":
            color = GREEN
            canvas.setStrokeColor(color)
            canvas.setLineWidth(2)
            canvas.line(9, 3, 9, 15)
            canvas.line(9, 15, 4, 10)
            canvas.line(9, 15, 14, 10)
        elif self.direction == "down":
            color = RED
            canvas.setStrokeColor(color)
            canvas.setLineWidth(2)
            canvas.line(9, 3, 9, 15)
            canvas.line(9, 3, 4, 8)
            canvas.line(9, 3, 14, 8)
        else:
            color = SLATE
            canvas.setStrokeColor(color)
            canvas.setFillColor(color)
            canvas.setLineWidth(2)
            canvas.line(3, 9, 14, 9)
            canvas.line(11, 13, 15, 9)
            canvas.line(11, 5, 15, 9)


def _company_page(data: CompanyReportData) -> list[Any]:
    title_style = ParagraphStyle(
        "PortfolioTitle",
        parent=BODY,
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=20,
        textColor=WHITE,
        wordWrap="CJK",
    )
    ticker_style = ParagraphStyle(
        "PortfolioTicker",
        parent=title_style,
        fontSize=12,
        leading=14,
        alignment=2,
    )
    subtitle_style = ParagraphStyle(
        "PortfolioSubtitle",
        parent=BODY,
        fontSize=8,
        leading=10,
        textColor=WHITE,
        alignment=0,
        wordWrap="CJK",
    )
    latest = latest_ratio(data)
    year = None if latest is None else latest[0]
    values = {} if latest is None else latest[1]
    prior = data.ratios.get(year - 1, {}) if year is not None else {}
    header = wordwrap_table(
        [
            [
                Paragraph(escape(data.company_name), title_style),
                Paragraph(escape(data.company_id), ticker_style),
            ],
            [
                paragraph(data.sector or "Sector unavailable", subtitle_style),
                paragraph(f"Latest FY: {year or 'N/A'}", subtitle_style),
            ],
        ],
        col_widths=[5.35 * inch, 1.8 * inch],
        style_commands=[
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("TEXTCOLOR", (0, 1), (-1, 1), WHITE),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ],
    )
    metric_rows: list[list[object]] = [["Metric", "Latest", "Trend", "Interpretation"]]
    for label, field, suffix, decimals, lower_is_better in PORTFOLIO_METRICS:
        direction = trend_direction(
            values.get(field), prior.get(field), lower_is_better=lower_is_better
        )
        interpretation = {
            "up": "Improved versus prior year",
            "down": "Declined versus prior year",
            "flat": "Flat within 2% or insufficient comparison data",
        }[direction]
        metric_rows.append(
            [
                label,
                fmt(values.get(field), suffix=suffix, decimals=decimals),
                TrendArrow(direction),
                interpretation,
            ]
        )
    metric_table = wordwrap_table(
        metric_rows,
        col_widths=[2.05 * inch, 1.35 * inch, 0.65 * inch, 3.05 * inch],
        row_heights=[0.42 * inch] + [0.7 * inch] * len(PORTFOLIO_METRICS),
        repeat_rows=1,
        style_commands=[
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT_BLUE, LIGHT_GRAY]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, MID_GRAY),
            ("ALIGN", (1, 1), (2, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ],
    )
    return [
        header,
        Spacer(1, 0.25 * inch),
        paragraph("Top 6 KPIs and Latest-Year Direction", SECTION),
        Spacer(1, 0.1 * inch),
        metric_table,
        Spacer(1, 0.22 * inch),
        paragraph(
            "Trend convention: improvement is based on the latest annual observation "
            "versus the prior year. Movement within 2% is flat; lower debt-to-equity "
            "is treated as improvement.",
            BODY,
        ),
    ]


def generate_portfolio_summary(
    database_path: str | Path = "nifty100.db",
    output_path: str | Path = "reports/portfolio/portfolio_summary.pdf",
    pros_cons_path: str | Path = "output/pros_cons_generated.csv",
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=0.46 * inch,
        rightMargin=0.46 * inch,
        topMargin=0.42 * inch,
        bottomMargin=0.58 * inch,
        title="N100 Portfolio Summary",
        author="N100 Financial Intelligence Platform",
        pageCompression=1,
    )
    companies = sorted(
        load_report_data(database_path, pros_cons_path), key=lambda item: item.company_id
    )
    content: list[Any] = []
    for index, company in enumerate(companies):
        content.extend(_company_page(company))
        if index < len(companies) - 1:
            content.append(PageBreak())
            content.append(Spacer(1, 0.2 * inch))
    document.build(content, onFirstPage=page_footer, onLaterPages=page_footer)
    return path.resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate N100 portfolio summary PDF")
    parser.add_argument("--database", default="nifty100.db")
    parser.add_argument("--output", default="reports/portfolio/portfolio_summary.pdf")
    parser.add_argument("--pros-cons", default="output/pros_cons_generated.csv")
    args = parser.parse_args(argv)
    path = generate_portfolio_summary(args.database, args.output, args.pros_cons)
    print(f"Generated portfolio summary at {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
