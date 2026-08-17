"""FastAPI application exposing the Nifty 100 financial intelligence database."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = Path(os.getenv("NIFTY100_DB_PATH", PROJECT_ROOT / "nifty100.db"))
TEARSHEET_DIRECTORY = PROJECT_ROOT / "reports" / "tearsheets"
STARTED_AT = time.monotonic()
LOGGER = logging.getLogger("nifty100.api")
SECTOR_ALIASES = {"it": "Information Technology", "financial": "Financials"}

app = FastAPI(title="Nifty 100 Financial Intelligence API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Any, call_next: Any) -> Any:
    """Log request method, path and elapsed time for every API request."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    LOGGER.info(
        "%s %s -> %s in %.1fms", request.method, request.url.path, response.status_code, elapsed_ms
    )
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
    return response


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a read-only SQLite connection returning rows as dictionaries."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def rows(query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Execute a parameterized query and return JSON-safe dictionaries."""
    with get_connection() as connection:
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]


def one(query: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    """Execute a parameterized query and return its first row if present."""
    result = rows(query, parameters)
    return result[0] if result else None


def latest_ratios_cte() -> str:
    """Return SQL selecting one latest ratio record per company."""
    return """
        WITH latest_ratios AS (
            SELECT * FROM (
                SELECT fr.*, ROW_NUMBER() OVER (
                    PARTITION BY company_id ORDER BY year DESC, id DESC
                ) AS row_number
                FROM financial_ratios fr
            ) WHERE row_number = 1
        ), latest_market AS (
            SELECT * FROM (
                SELECT m.*, ROW_NUMBER() OVER (
                    PARTITION BY company_id ORDER BY year DESC, id DESC
                ) AS row_number
                FROM market_cap m
            ) WHERE row_number = 1
        )
    """


def ticker_or_404(ticker: str) -> str:
    """Return a validated uppercase ticker or raise a 404 response."""
    value = ticker.strip().upper()
    if one("SELECT id FROM companies WHERE UPPER(id) = ?", (value,)) is None:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' was not found")
    return value


def normalize_sector(sector: str) -> str:
    """Resolve user-friendly sector aliases to stored sector labels."""
    return SECTOR_ALIASES.get(sector.strip().lower(), sector.strip())


def parse_year(value: str | None) -> int | None:
    """Parse an API year value in YYYY or YYYY-MM format."""
    if value is None:
        return None
    try:
        year = int(value[:4])
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=400, detail="Years must use YYYY or YYYY-MM format"
        ) from error
    if year < 1900 or year > 2100:
        raise HTTPException(status_code=400, detail="Year is outside the supported range")
    return year


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    """Return service status, database table counts, uptime and version."""
    with get_connection() as connection:
        table_names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in table_names
        }
    return {
        "status": "ok",
        "db_row_counts": counts,
        "uptime_seconds": round(time.monotonic() - STARTED_AT, 3),
        "version": app.version,
    }


@app.get("/api/v1/companies")
def companies(
    sector: str | None = None,
    market_cap_category: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """List companies, optionally filtering by sector, market-cap band or ticker/name search."""
    where: list[str] = []
    params: list[Any] = []
    if sector:
        where.append("LOWER(s.broad_sector) = LOWER(?)")
        params.append(normalize_sector(sector))
    if market_cap_category:
        where.append("LOWER(s.market_cap_category) = LOWER(?)")
        params.append(market_cap_category)
    if search:
        where.append("(LOWER(c.company_name) LIKE ? OR LOWER(c.id) LIKE ?)")
        params.extend([f"%{search.lower()}%", f"%{search.lower()}%"])
    filters = f"WHERE {' AND '.join(where)}" if where else ""
    return rows(
        latest_ratios_cte()
        + f"""
        SELECT c.id, c.company_name, s.broad_sector, s.sub_sector,
               r.return_on_equity_pct AS roe_pct, r.return_on_capital_employed_pct AS roce_pct
        FROM companies c LEFT JOIN sectors s ON s.company_id = c.id
        LEFT JOIN latest_ratios r ON r.company_id = c.id
        {filters} ORDER BY c.company_name
        """,
        tuple(params),
    )


@app.get("/api/v1/companies/{ticker}")
def company_profile(ticker: str) -> dict[str, Any]:
    """Return company identity, sector classification and its latest KPI record."""
    value = ticker_or_404(ticker)
    record = one(
        latest_ratios_cte()
        + """
        SELECT c.*, s.broad_sector, s.sub_sector, s.index_weight_pct, s.market_cap_category,
               r.*
        FROM companies c LEFT JOIN sectors s ON s.company_id = c.id
        LEFT JOIN latest_ratios r ON r.company_id = c.id WHERE c.id = ?
        """,
        (value,),
    )
    assert record is not None
    return record


def statement_history(
    ticker: str, statement_type: str, from_year: str | None, to_year: str | None
) -> list[dict[str, Any]]:
    """Return a filtered statement history for a validated company and statement type."""
    value = ticker_or_404(ticker)
    start, end = parse_year(from_year), parse_year(to_year)
    clauses = ["company_id = ?", "statement_type = ?"]
    params: list[Any] = [value, statement_type]
    if start is not None:
        clauses.append("year >= ?")
        params.append(start)
    if end is not None:
        clauses.append("year <= ?")
        params.append(end)
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=400, detail="from_year must not be later than to_year")
    return rows(
        f"SELECT * FROM financial_statements WHERE {' AND '.join(clauses)} ORDER BY year",
        tuple(params),
    )


@app.get("/api/v1/companies/{ticker}/pl")
def profit_and_loss(
    ticker: str, from_year: str | None = None, to_year: str | None = None
) -> list[dict[str, Any]]:
    """Return a company's profit-and-loss history."""
    return statement_history(ticker, "profit_and_loss", from_year, to_year)


@app.get("/api/v1/companies/{ticker}/bs")
def balance_sheet(
    ticker: str, from_year: str | None = None, to_year: str | None = None
) -> list[dict[str, Any]]:
    """Return a company's balance-sheet history."""
    return statement_history(ticker, "balance_sheet", from_year, to_year)


@app.get("/api/v1/companies/{ticker}/cashflow")
def cash_flow(
    ticker: str, from_year: str | None = None, to_year: str | None = None
) -> list[dict[str, Any]]:
    """Return a company's cash-flow history."""
    return statement_history(ticker, "cash_flow", from_year, to_year)


@app.get("/api/v1/companies/{ticker}/ratios")
def ratios(ticker: str, year: int | None = None) -> list[dict[str, Any]]:
    """Return all computed KPI records for a company, optionally for one year."""
    value = ticker_or_404(ticker)
    query = "SELECT * FROM financial_ratios WHERE company_id = ?"
    parameters: tuple[Any, ...] = (value,)
    if year is not None:
        query += " AND year = ?"
        parameters += (year,)
    return rows(query + " ORDER BY year", parameters)


@app.get("/api/v1/companies/{ticker}/tearsheet")
def tearsheet(ticker: str) -> FileResponse:
    """Download the pre-generated company tearsheet PDF."""
    value = ticker_or_404(ticker)
    path = TEARSHEET_DIRECTORY / f"{value}_tearsheet.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Tearsheet for '{value}' is unavailable")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.get("/api/v1/screener")
def screener(
    min_roe: float | None = None,
    max_de: float | None = None,
    min_fcf: float | None = None,
    sector: str | None = None,
    min_rev_cagr_5yr: float | None = None,
    min_pat_cagr_5yr: float | None = None,
    max_pe: float | None = None,
) -> list[dict[str, Any]]:
    """Screen latest company KPIs using financial threshold filters."""
    bounds = (
        ("min_roe", min_roe, -100, 200),
        ("max_de", max_de, 0, 100),
        ("min_rev_cagr_5yr", min_rev_cagr_5yr, -100, 500),
        ("min_pat_cagr_5yr", min_pat_cagr_5yr, -100, 500),
        ("max_pe", max_pe, 0.000001, 1000),
    )
    for name, value, lower, upper in bounds:
        if value is not None and not lower <= value <= upper:
            raise HTTPException(
                status_code=400, detail=f"{name} must be between {lower} and {upper}"
            )
    where: list[str] = []
    params: list[Any] = []
    for column, value, operator in (
        ("r.return_on_equity_pct", min_roe, ">="),
        ("r.debt_to_equity", max_de, "<="),
        ("r.free_cash_flow_cr", min_fcf, ">="),
        ("r.revenue_cagr_5yr", min_rev_cagr_5yr, ">="),
        ("r.pat_cagr_5yr", min_pat_cagr_5yr, ">="),
        ("m.pe_ratio", max_pe, "<="),
    ):
        if value is not None:
            where.append(f"{column} {operator} ?")
            params.append(value)
    if sector:
        where.append("LOWER(s.broad_sector) = LOWER(?)")
        params.append(normalize_sector(sector))
    filters = f"WHERE {' AND '.join(where)}" if where else ""
    return rows(
        latest_ratios_cte()
        + f"""
        SELECT c.id AS ticker, c.company_name, s.broad_sector, r.return_on_equity_pct AS roe_pct,
               r.debt_to_equity, r.free_cash_flow_cr, r.revenue_cagr_5yr, r.pat_cagr_5yr,
               r.operating_profit_margin_pct, m.pe_ratio, r.composite_quality_score
        FROM companies c JOIN latest_ratios r ON r.company_id = c.id
        LEFT JOIN latest_market m ON m.company_id = c.id LEFT JOIN sectors s ON s.company_id = c.id
        {filters} ORDER BY r.composite_quality_score DESC, r.return_on_equity_pct DESC
        """,
        tuple(params),
    )


@app.get("/api/v1/sectors")
def sectors() -> list[dict[str, Any]]:
    """Return sector-level company counts and latest KPI medians."""
    return rows(
        latest_ratios_cte()
        + """
        SELECT s.broad_sector AS sector, COUNT(*) AS company_count,
               ROUND(AVG(r.return_on_equity_pct), 4) AS median_roe,
               ROUND(AVG(m.pe_ratio), 4) AS median_pe, ROUND(AVG(r.debt_to_equity), 4) AS median_de
        FROM sectors s LEFT JOIN latest_ratios r ON r.company_id = s.company_id
        LEFT JOIN latest_market m ON m.company_id = s.company_id
        GROUP BY s.broad_sector ORDER BY s.broad_sector
        """
    )


@app.get("/api/v1/sectors/{sector}/companies")
def sector_companies(sector: str) -> list[dict[str, Any]]:
    """Return all companies and latest KPI values in a known broad sector."""
    resolved = normalize_sector(sector)
    results = rows(
        latest_ratios_cte()
        + """
        SELECT c.id AS ticker, c.company_name, s.broad_sector, s.sub_sector, r.*
        FROM sectors s JOIN companies c ON c.id = s.company_id
        LEFT JOIN latest_ratios r ON r.company_id = c.id
        WHERE LOWER(s.broad_sector) = LOWER(?) ORDER BY c.company_name
        """,
        (resolved,),
    )
    if not results:
        raise HTTPException(status_code=404, detail=f"Sector '{sector}' was not found")
    return results


@app.get("/api/v1/peers/{group_name}")
def peers(group_name: str) -> list[dict[str, Any]]:
    """Return peer members with all available percentile ranks."""
    results = rows(
        """
        SELECT pg.peer_group_name, pg.is_benchmark, c.id AS ticker, c.company_name,
               pp.metric, pp.value, pp.percentile_rank, pp.year
        FROM peer_groups pg JOIN companies c ON c.id = pg.company_id
        LEFT JOIN peer_percentiles pp ON pp.company_id = pg.company_id
            AND pp.peer_group_name = pg.peer_group_name
        WHERE LOWER(pg.peer_group_name) = LOWER(?)
        ORDER BY c.company_name, pp.metric
        """,
        (group_name,),
    )
    if not results:
        raise HTTPException(status_code=404, detail=f"Peer group '{group_name}' was not found")
    return results


@app.get("/api/v1/companies/{ticker}/peers/compare")
def peer_compare(ticker: str) -> dict[str, Any]:
    """Return eight-axis percentile radar data with peer and benchmark comparators."""
    value = ticker_or_404(ticker)
    membership = one("SELECT peer_group_name FROM peer_groups WHERE company_id = ?", (value,))
    if membership is None:
        raise HTTPException(status_code=404, detail=f"Company '{value}' has no peer group")
    group = membership["peer_group_name"]
    metrics = rows(
        """
        SELECT metric, percentile_rank FROM peer_percentiles
        WHERE company_id = ? AND peer_group_name = ? ORDER BY metric LIMIT 8
        """,
        (value, group),
    )
    peer_average = rows(
        """
        SELECT metric, AVG(percentile_rank) AS value FROM peer_percentiles
        WHERE peer_group_name = ? GROUP BY metric ORDER BY metric LIMIT 8
        """,
        (group,),
    )
    benchmark = one(
        "SELECT company_id FROM peer_groups WHERE peer_group_name = ? AND is_benchmark = 1",
        (group,),
    )
    benchmark_metrics = (
        rows(
            """SELECT metric, percentile_rank AS value FROM peer_percentiles
           WHERE company_id = ? AND peer_group_name = ? ORDER BY metric LIMIT 8""",
            (benchmark["company_id"], group),
        )
        if benchmark
        else []
    )
    return {
        "ticker": value,
        "peer_group": group,
        "company": metrics,
        "peer_average": peer_average,
        "benchmark": benchmark_metrics,
    }


@app.get("/api/v1/market-cap/{ticker}")
def market_cap(ticker: str) -> list[dict[str, Any]]:
    """Return historical valuation multiples for a company from 2019 to 2024."""
    value = ticker_or_404(ticker)
    return rows(
        """SELECT year, pe_ratio, pb_ratio, ev_ebitda, dividend_yield_pct FROM market_cap
                   WHERE company_id = ? AND year BETWEEN 2019 AND 2024 ORDER BY year""",
        (value,),
    )


@app.get("/api/v1/portfolio/stats")
def portfolio_stats() -> list[dict[str, Any]]:
    """Return the generated percentile table for ten core portfolio KPIs."""
    path = PROJECT_ROOT / "output" / "portfolio_stats.csv"
    if not path.is_file():
        from src.analytics.clustering import generate_clustering_artifacts

        generate_clustering_artifacts()
    import csv

    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@app.get("/api/v1/companies/{ticker}/documents")
def documents(ticker: str) -> list[dict[str, Any]]:
    """Return annual-report links and URL validity flags for a company."""
    value = ticker_or_404(ticker)
    results = rows(
        "SELECT year, annual_report FROM documents WHERE company_id = ? ORDER BY year DESC",
        (value,),
    )
    for record in results:
        parsed = urlparse(record["annual_report"] or "")
        record["is_url_valid"] = bool(parsed.scheme in {"http", "https"} and parsed.netloc)
    return results
