"""Generate the Sprint 6 analyst guide PDF."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "analyst_guide.pdf"

PAGES = [
    (
        "Nifty 100 Financial Intelligence Platform",
        [
            "Analyst guide - Sprint 6",
            "This guide explains the Streamlit dashboard, financial screener, PDF tearsheets, and REST API.",
            "Data coverage: 92 Nifty 100 companies, 2012-2024 financial statements and latest computed KPIs.",
            "Use this guide alongside README.md for installation and command-line setup.",
        ],
    ),
    (
        "1. Start the platform",
        [
            "Create or activate the project Python environment and install requirements.",
            "Build or refresh the database with make db when raw workbooks change.",
            "Start the dashboard: PYTHONPATH=src streamlit run src/dashboard/app.py.",
            "Start the API: PYTHONPATH=src uvicorn api.main:app --port 8000.",
            "The dashboard normally uses nifty100.db directly; the API is available at /api/v1 and documentation at /docs.",
        ],
    ),
    (
        "2. Use the Streamlit screener",
        [
            "Open the Screener page from the sidebar. It presents one latest KPI row for each company.",
            "Choose a sector, quality, valuation, leverage, free-cash-flow, or five-year growth threshold.",
            "A company is included only when it satisfies every populated filter.",
            "Sort by composite quality score or return on equity to focus the investment review.",
            "Use the page download control to save a CSV. Blank metrics are not treated as passing a threshold.",
        ],
    ),
    (
        "3. Navigate the company profile",
        [
            "Use the Company Profile page and select a ticker or search by company name.",
            "Review identity, sector classification, latest KPIs, business description, pros and cons, and annual report links.",
            "Use Trends for multi-year profit and loss, balance sheet, cash-flow, and ratio histories.",
            "Use Capital Allocation to assess cash generation, capex intensity, and allocation patterns.",
            "Treat calculated metrics as decision support and check annual reports before acting on an investment conclusion.",
        ],
    ),
    (
        "4. Compare peers and sectors",
        [
            "The Peers screen groups comparable companies and shows relative percentile ranks across ten core metrics.",
            "The radar view uses company data, peer-group average, and the designated benchmark where present.",
            "The Sectors screen aggregates coverage by broad sector and supports drilling into constituent companies.",
            "A higher percentile is favorable except for debt-to-equity, where a lower value ranks better.",
            "Peer comparisons are strongest within the same business model; avoid mixing banks with non-financial companies.",
        ],
    ),
    (
        "5. Read valuation and report views",
        [
            "The Valuation or market-cap view presents P/E, P/B, EV/EBITDA, dividend yield, and historical market-cap data.",
            "Use the Reports page for sector reports, portfolio summary material, and generated tearsheets.",
            "The portfolio statistics artifact provides P10, P25, median, P75, P90, mean, and standard deviation for core KPIs.",
            "Cluster labels classify each company into one of five financial archetypes; they are descriptive, not ratings.",
        ],
    ),
    (
        "6. Generate and retrieve PDF tearsheets",
        [
            "Tearsheets are generated under reports/tearsheets using the report-generation workflow.",
            "A tear sheet combines key financials, KPI trends, peer context, capital allocation, and risk flags for one company.",
            "Download from the dashboard Reports page or call GET /api/v1/companies/{ticker}/tearsheet.",
            "The API replies with application/pdf and a file-download name such as TCS_tearsheet.pdf.",
            "If a tear sheet is missing, rerun its report task and confirm the ticker uses the database identifier.",
        ],
    ),
    (
        "7. Call the REST API",
        [
            "The base URL is http://127.0.0.1:8000/api/v1. Interactive OpenAPI docs are available at http://127.0.0.1:8000/docs.",
            "Health check: curl http://127.0.0.1:8000/api/v1/health",
            "Directory search: curl 'http://127.0.0.1:8000/api/v1/companies?search=tcs'",
            "Screener: curl 'http://127.0.0.1:8000/api/v1/screener?min_roe=15&max_pe=40'",
            "History: curl 'http://127.0.0.1:8000/api/v1/companies/TCS/ratios?year=2024'",
            "API responses are JSON except the tearsheet route, which streams a PDF download.",
        ],
    ),
    (
        "8. Interpret API filters and errors",
        [
            "Company listing filters: sector, market_cap_category, and search (partial company name or ticker).",
            "Screener filters: min_roe, max_de, min_fcf, sector, min_rev_cagr_5yr, min_pat_cagr_5yr, and max_pe.",
            "Dates in statement history support YYYY and YYYY-MM input, for example from_year=2019-03.",
            "Unknown tickers, sectors, or peer groups return HTTP 404. Invalid screener bounds return HTTP 400.",
            "Do not build SQL strings from user input: API parameters are bound safely by the service.",
        ],
    ),
    (
        "9. Troubleshooting and quality checks",
        [
            "Database unavailable: check NIFTY100_DB_PATH or run make db from the project root.",
            "Port already in use: choose a different port for uvicorn or Streamlit, then update the address you open.",
            "No screener results: relax one filter at a time and review whether missing values are excluding companies.",
            "Missing or stale report: regenerate the corresponding analytical artifact, then refresh the browser.",
            "Before release, run PYTHONPATH=src pytest tests -v and review reports/pytest_report.html.",
            "For a reproducible end-to-end check, start both services, call /health, run a screener query, and open a profile.",
        ],
    ),
]


def footer(canvas: object, document: object) -> None:
    """Draw a consistent footer with page number on every guide page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#6B7280"))
    canvas.drawString(
        0.65 * inch, 0.42 * inch, "Nifty 100 Financial Intelligence Platform - Analyst Guide"
    )
    canvas.drawRightString(A4[0] - 0.65 * inch, 0.42 * inch, f"Page {document.page}")
    canvas.restoreState()


def generate() -> None:
    """Build the polished ten-page analyst guide PDF."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = styles["Title"]
    title.textColor = HexColor("#123B63")
    heading = styles["Heading1"]
    heading.textColor = HexColor("#123B63")
    body = styles["BodyText"]
    body.leading = 18
    body.spaceAfter = 12
    story = []
    for page_number, (heading_text, paragraphs) in enumerate(PAGES):
        story.append(Paragraph(heading_text, title if page_number == 0 else heading))
        story.append(Spacer(1, 0.24 * inch))
        for paragraph in paragraphs:
            story.append(Paragraph(paragraph, body))
        if page_number < len(PAGES) - 1:
            story.append(PageBreak())
    SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.7 * inch,
    ).build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    generate()
