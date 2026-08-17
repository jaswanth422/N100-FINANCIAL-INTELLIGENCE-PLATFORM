"""Shared data, formatting, and chart helpers for Sprint 5 PDFs."""

from __future__ import annotations

import csv
import io
import math
import os
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

_matplotlib_cache = Path(tempfile.gettempdir()) / "n100-matplotlib"
_matplotlib_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_matplotlib_cache))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import Paragraph, Table, TableStyle  # noqa: E402

NAVY = colors.HexColor("#0B1F3A")
BLUE = colors.HexColor("#2563EB")
TEAL = colors.HexColor("#0F766E")
GREEN = colors.HexColor("#15803D")
RED = colors.HexColor("#B91C1C")
AMBER = colors.HexColor("#B45309")
SLATE = colors.HexColor("#475569")
LIGHT_BLUE = colors.HexColor("#E8F0FA")
LIGHT_GREEN = colors.HexColor("#EAF7EE")
LIGHT_RED = colors.HexColor("#FDECEC")
LIGHT_GRAY = colors.HexColor("#F4F6F8")
MID_GRAY = colors.HexColor("#D8DEE7")
WHITE = colors.white


@dataclass(frozen=True)
class CompanyReportData:
    company_id: str
    company_name: str
    sector: str | None
    sub_sector: str | None
    ratios: dict[int, dict[str, Any]]
    profit_loss: dict[int, dict[str, Any]]
    balance_sheet: dict[int, dict[str, Any]]
    cash_flow: dict[int, dict[str, Any]]
    pros: tuple[str, ...]
    cons: tuple[str, ...]


def finite(value: object) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def fmt(value: object, *, suffix: str = "", decimals: int = 1) -> str:
    number = finite(value)
    if number is None:
        return "N/A"
    return f"{number:,.{decimals}f}{suffix}"


def load_report_data(
    database_path: str | Path = "nifty100.db",
    pros_cons_path: str | Path = "output/pros_cons_generated.csv",
) -> list[CompanyReportData]:
    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    try:
        companies = [dict(row) for row in connection.execute(
            """
            SELECT c.id AS company_id, c.company_name, s.broad_sector AS sector,
                   s.sub_sector
            FROM companies AS c
            LEFT JOIN sectors AS s ON s.company_id = c.id
            ORDER BY c.id
            """
        )]
        ratio_rows = [dict(row) for row in connection.execute(
            "SELECT * FROM financial_ratios WHERE year IS NOT NULL ORDER BY id"
        )]
        statement_rows = [dict(row) for row in connection.execute(
            "SELECT * FROM financial_statements WHERE year IS NOT NULL ORDER BY id"
        )]
    finally:
        connection.close()

    ratios: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    statements: dict[str, dict[str, dict[int, dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for row in ratio_rows:
        ratios[str(row["company_id"])][int(row["year"])] = row
    for row in statement_rows:
        statements[str(row["company_id"])][str(row["statement_type"])][
            int(row["year"])
        ] = row

    signals: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"pro": [], "con": []}
    )
    path = Path(pros_cons_path)
    if path.exists():
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                signal_type = str(row.get("type", "")).strip().lower()
                if signal_type in {"pro", "con"}:
                    signals[str(row.get("company_id", ""))][signal_type].append(
                        str(row.get("text", "")).strip()
                    )

    return [
        CompanyReportData(
            company_id=str(company["company_id"]),
            company_name=str(company["company_name"]),
            sector=company.get("sector"),
            sub_sector=company.get("sub_sector"),
            ratios=ratios.get(str(company["company_id"]), {}),
            profit_loss=statements[str(company["company_id"])].get(
                "profit_and_loss", {}
            ),
            balance_sheet=statements[str(company["company_id"])].get(
                "balance_sheet", {}
            ),
            cash_flow=statements[str(company["company_id"])].get("cash_flow", {}),
            pros=tuple(signals[str(company["company_id"])]["pro"]),
            cons=tuple(signals[str(company["company_id"])]["con"]),
        )
        for company in companies
    ]


_styles = getSampleStyleSheet()
BODY = ParagraphStyle(
    "N100Body",
    parent=_styles["BodyText"],
    fontName="Helvetica",
    fontSize=8.2,
    leading=10.2,
    textColor=SLATE,
    wordWrap="CJK",
    splitLongWords=True,
)
SMALL = ParagraphStyle(
    "N100Small",
    parent=BODY,
    fontSize=7,
    leading=8.4,
)
HEADER = ParagraphStyle(
    "N100Header",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=8,
    leading=9.5,
    textColor=WHITE,
    alignment=TA_CENTER,
)
SECTION = ParagraphStyle(
    "N100Section",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=13,
    textColor=NAVY,
)
TITLE = ParagraphStyle(
    "N100Title",
    parent=BODY,
    fontName="Helvetica-Bold",
    fontSize=17,
    leading=20,
    textColor=WHITE,
)
SUBTITLE = ParagraphStyle(
    "N100Subtitle",
    parent=BODY,
    fontSize=8,
    leading=10,
    textColor=colors.HexColor("#C8D7EA"),
)
CENTER = ParagraphStyle("N100Center", parent=BODY, alignment=TA_CENTER)
LEFT = ParagraphStyle("N100Left", parent=BODY, alignment=TA_LEFT)


def paragraph(value: object, style: ParagraphStyle = BODY) -> Paragraph:
    text = "" if value is None else str(value)
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def wordwrap_table(
    data: list[list[object]],
    *,
    col_widths: list[float] | None = None,
    row_heights: list[float] | None = None,
    style_commands: list[tuple] | None = None,
    repeat_rows: int = 0,
) -> Table:
    """Create a table whose every textual cell is a word-wrapped Paragraph."""
    wrapped: list[list[object]] = []
    for row_index, row in enumerate(data):
        wrapped.append(
            [
                cell
                if hasattr(cell, "wrap")
                else paragraph(cell, HEADER if row_index < repeat_rows else BODY)
                for cell in row
            ]
        )
    table = Table(
        wrapped,
        colWidths=col_widths,
        rowHeights=row_heights,
        repeatRows=repeat_rows,
        hAlign="LEFT",
        splitByRow=1,
    )
    commands: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    commands.extend(style_commands or [])
    table.setStyle(TableStyle(commands))
    return table


def figure_image(fig: Any, width: float, height: float):
    from reportlab.platypus import Image

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buffer.seek(0)
    image = Image(buffer, width=width, height=height)
    image._n100_buffer = buffer
    return image


def latest_ratio(data: CompanyReportData) -> tuple[int, dict[str, Any]] | None:
    if not data.ratios:
        return None
    year = max(data.ratios)
    return year, data.ratios[year]


def trend_direction(current: object, prior: object, *, lower_is_better: bool = False) -> str:
    current_value = finite(current)
    prior_value = finite(prior)
    if current_value is None or prior_value is None:
        return "flat"
    denominator = max(abs(prior_value), 1e-9)
    change = (current_value - prior_value) / denominator
    if abs(change) <= 0.02:
        return "flat"
    improved = change < 0 if lower_is_better else change > 0
    return "up" if improved else "down"


def chart_style(axis: Any) -> None:
    axis.grid(axis="y", alpha=0.18, linewidth=0.6)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.tick_params(labelsize=7, colors="#475569", length=0)
    axis.title.set_color("#0B1F3A")


def revenue_profit_chart(data: CompanyReportData):
    years = sorted(data.profit_loss)[-10:]
    revenue = [finite(data.profit_loss[y].get("sales")) or 0 for y in years]
    profit = [finite(data.profit_loss[y].get("net_profit")) or 0 for y in years]
    fig, axes = plt.subplots(1, 2, figsize=(7.3, 2.15), constrained_layout=True)
    for axis, values, title, color in (
        (axes[0], revenue, "Revenue (Cr)", "#2563EB"),
        (axes[1], profit, "Net Profit (Cr)", "#0F766E"),
    ):
        axis.bar([str(year) for year in years], values, color=color, width=0.72)
        axis.set_title(title, fontsize=9, fontweight="bold", loc="left")
        axis.tick_params(axis="x", rotation=45)
        chart_style(axis)
    return fig


def returns_chart(data: CompanyReportData):
    years = sorted(data.ratios)[-10:]
    roe = [finite(data.ratios[y].get("return_on_equity_pct")) for y in years]
    roce = [finite(data.ratios[y].get("return_on_capital_employed_pct")) for y in years]
    fig, left = plt.subplots(figsize=(7.3, 2.1), constrained_layout=True)
    right = left.twinx()
    left.plot(years, roe, color="#2563EB", marker="o", markersize=3, label="ROE")
    right.plot(years, roce, color="#F59E0B", marker="s", markersize=3, label="ROCE")
    left.set_title("Return Profile", fontsize=9, fontweight="bold", loc="left")
    left.set_ylabel("ROE %", color="#2563EB", fontsize=7)
    right.set_ylabel("ROCE %", color="#B45309", fontsize=7)
    chart_style(left)
    right.spines[["top", "left"]].set_visible(False)
    right.tick_params(labelsize=7, colors="#B45309", length=0)
    lines = left.lines + right.lines
    left.legend(lines, [line.get_label() for line in lines], fontsize=7, frameon=False, loc="best")
    return fig


def balance_sheet_chart(data: CompanyReportData):
    years = sorted(data.balance_sheet)[-10:]
    equity = []
    borrowings = []
    other = []
    for year in years:
        row = data.balance_sheet[year]
        equity.append((finite(row.get("equity_capital")) or 0) + (finite(row.get("reserves")) or 0))
        borrowings.append(finite(row.get("borrowings")) or 0)
        other.append(finite(row.get("other_liabilities")) or 0)
    fig, axis = plt.subplots(figsize=(7.3, 2.15), constrained_layout=True)
    axis.bar(years, equity, label="Equity", color="#2563EB")
    axis.bar(years, borrowings, bottom=equity, label="Borrowings", color="#F59E0B")
    bottoms = [
        left + middle for left, middle in zip(equity, borrowings, strict=True)
    ]
    axis.bar(years, other, bottom=bottoms, label="Other Liabilities", color="#94A3B8")
    axis.set_title("Balance Sheet Composition (Cr)", fontsize=9, fontweight="bold", loc="left")
    axis.legend(ncols=3, fontsize=7, frameon=False, loc="upper left")
    chart_style(axis)
    return fig


def cashflow_waterfall_chart(data: CompanyReportData):
    if data.cash_flow:
        year = max(data.cash_flow)
        row = data.cash_flow[year]
    else:
        year = 0
        row = {}
    values = [
        finite(row.get("operating_activity")) or 0,
        finite(row.get("investing_activity")) or 0,
        finite(row.get("financing_activity")) or 0,
    ]
    net = finite(row.get("net_cash_flow"))
    net = sum(values) if net is None else net
    starts = [0, values[0], values[0] + values[1], 0]
    heights = [values[0], values[1], values[2], net]
    palette = ["#15803D" if value >= 0 else "#B91C1C" for value in heights]
    fig, axis = plt.subplots(figsize=(7.3, 2.1), constrained_layout=True)
    axis.bar(["CFO", "CFI", "CFF", "Net Cash"], heights, bottom=starts, color=palette, width=0.62)
    for index, (start, value) in enumerate(zip(starts, heights, strict=True)):
        if value >= 0:
            y_position = start + value
            vertical_alignment = "bottom"
            text_color = "#334155"
        else:
            y_position = start + value / 2
            vertical_alignment = "center"
            text_color = "white"
        axis.text(
            index,
            y_position,
            f"{value:,.0f}",
            ha="center",
            va=vertical_alignment,
            fontsize=7,
            color=text_color,
            fontweight="bold" if value < 0 else "normal",
        )
    axis.axhline(0, color="#475569", linewidth=0.8)
    axis.set_title(
        f"Cash Flow Waterfall - {year or 'N/A'} (Cr)",
        fontsize=9,
        fontweight="bold",
        loc="left",
    )
    chart_style(axis)
    return fig


def latest_allocation_label(data: CompanyReportData) -> str:
    from analytics.cashflow import classify_capital_allocation

    if not data.cash_flow:
        return "N/A"
    year = max(data.cash_flow)
    cash = data.cash_flow[year]
    profit = data.profit_loss.get(year, {})
    cfo = finite(cash.get("operating_activity"))
    pat = finite(profit.get("net_profit"))
    ratio = None if cfo is None or pat in {None, 0} else cfo / pat
    return classify_capital_allocation(
        cash.get("operating_activity"),
        cash.get("investing_activity"),
        cash.get("financing_activity"),
        cfo_pat_ratio=ratio,
    ) or "N/A"


def allocation_color(label: str):
    if label in {"Shareholder Returns", "Reinvestor", "Cash Accumulator"}:
        return GREEN
    if label in {"Distress Signal", "Pre-Revenue"}:
        return RED
    if label in {"Growth Funded by Debt", "Liquidating Assets"}:
        return AMBER
    return SLATE


def page_footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setStrokeColor(MID_GRAY)
    canvas.line(
        document.leftMargin,
        0.42 * inch,
        document.pagesize[0] - document.rightMargin,
        0.42 * inch,
    )
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(SLATE)
    canvas.drawString(document.leftMargin, 0.25 * inch, "N100 Financial Intelligence Platform")
    canvas.drawRightString(
        document.pagesize[0] - document.rightMargin,
        0.25 * inch,
        f"Page {document.page}",
    )
    canvas.restoreState()
