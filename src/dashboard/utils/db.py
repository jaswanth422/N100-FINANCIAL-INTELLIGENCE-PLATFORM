"""Cached, read-only data access for the Nifty 100 dashboard."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "nifty100.db"


def _database_path() -> Path:
    """Return the configured database path and fail clearly when it is unavailable."""
    configured_path = os.getenv("NIFTY100_DB_PATH")
    path = Path(configured_path).expanduser() if configured_path else DEFAULT_DATABASE_PATH
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"Nifty 100 database not found at {path}. "
            "Set NIFTY100_DB_PATH or run `make db` from the project root."
        )
    return path


def _read_query(query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    """Execute a parameterized query against a short-lived SQLite connection."""
    with closing(sqlite3.connect(_database_path())) as connection:
        return pd.read_sql_query(query, connection, params=params)


@st.cache_data(ttl=600)
def get_companies() -> pd.DataFrame:
    """Return the complete company directory."""
    return _read_query("SELECT * FROM companies ORDER BY company_name")


@st.cache_data(ttl=600)
def get_ratios(ticker: str, year: int | None = None) -> pd.DataFrame:
    """Return ratio history for a ticker, optionally restricted to one year."""
    query = "SELECT * FROM financial_ratios WHERE company_id = ?"
    params: tuple[Any, ...] = (ticker,)
    if year is not None:
        query += " AND year = ?"
        params += (year,)
    query += " ORDER BY year DESC, id DESC"
    return _read_query(query, params)


@st.cache_data(ttl=600)
def get_pl(ticker: str) -> pd.DataFrame:
    """Return profit-and-loss history for a ticker."""
    return _read_query(
        """
        SELECT *
        FROM financial_statements
        WHERE company_id = ? AND statement_type = 'profit_and_loss'
        ORDER BY year DESC
        """,
        (ticker,),
    )


@st.cache_data(ttl=600)
def get_bs(ticker: str) -> pd.DataFrame:
    """Return balance-sheet history for a ticker."""
    return _read_query(
        """
        SELECT *
        FROM financial_statements
        WHERE company_id = ? AND statement_type = 'balance_sheet'
        ORDER BY year DESC
        """,
        (ticker,),
    )


@st.cache_data(ttl=600)
def get_cf(ticker: str) -> pd.DataFrame:
    """Return cash-flow history for a ticker."""
    return _read_query(
        """
        SELECT *
        FROM financial_statements
        WHERE company_id = ? AND statement_type = 'cash_flow'
        ORDER BY year DESC
        """,
        (ticker,),
    )


@st.cache_data(ttl=600)
def get_sectors() -> pd.DataFrame:
    """Return sector classifications with company names."""
    return _read_query(
        """
        SELECT s.*, c.company_name
        FROM sectors AS s
        JOIN companies AS c ON c.id = s.company_id
        ORDER BY s.broad_sector, s.sub_sector, c.company_name
        """
    )


@st.cache_data(ttl=600)
def get_peers(group_name: str) -> pd.DataFrame:
    """Return the members of a peer group with company names."""
    return _read_query(
        """
        SELECT pg.*, c.company_name
        FROM peer_groups AS pg
        JOIN companies AS c ON c.id = pg.company_id
        WHERE pg.peer_group_name = ?
        ORDER BY pg.is_benchmark DESC, c.company_name
        """,
        (group_name,),
    )


@st.cache_data(ttl=600)
def get_valuation(ticker: str) -> pd.DataFrame:
    """Return valuation history for a ticker."""
    return _read_query(
        "SELECT * FROM market_cap WHERE company_id = ? ORDER BY year DESC",
        (ticker,),
    )


@st.cache_data(ttl=600)
def get_home_snapshot(year: int) -> pd.DataFrame:
    """Return one deduplicated company row for the selected dashboard year."""
    return _read_query(
        """
        WITH selected_ratios AS (
            SELECT *
            FROM (
                SELECT
                    fr.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY fr.company_id, fr.year
                        ORDER BY fr.id DESC
                    ) AS row_number
                FROM financial_ratios AS fr
                WHERE fr.year = ?
            )
            WHERE row_number = 1
        )
        SELECT
            c.id AS ticker,
            c.company_name,
            s.broad_sector,
            s.sub_sector,
            r.return_on_equity_pct,
            r.debt_to_equity,
            r.revenue_cagr_5yr,
            r.composite_quality_score,
            m.pe_ratio
        FROM selected_ratios AS r
        JOIN companies AS c ON c.id = r.company_id
        LEFT JOIN sectors AS s ON s.company_id = r.company_id
        LEFT JOIN market_cap AS m
            ON m.company_id = r.company_id AND m.year = r.year
        ORDER BY c.company_name
        """,
        (year,),
    )


@st.cache_data(ttl=600)
def get_company_profile(ticker: str) -> pd.DataFrame:
    """Return company identity and sector details for a ticker."""
    return _read_query(
        """
        SELECT
            c.id AS ticker,
            c.company_name,
            c.about_company,
            c.website,
            s.broad_sector,
            s.sub_sector
        FROM companies AS c
        LEFT JOIN sectors AS s ON s.company_id = c.id
        WHERE c.id = ?
        """,
        (ticker,),
    )


@st.cache_data(ttl=600)
def get_pros_cons(ticker: str) -> pd.DataFrame:
    """Return qualitative pros and cons for a ticker."""
    return _read_query(
        """
        SELECT pros, cons
        FROM pros_and_cons
        WHERE company_id = ?
        ORDER BY id
        """,
        (ticker,),
    )


@st.cache_data(ttl=600)
def get_screener_universe() -> pd.DataFrame:
    """Return one latest-year row per company with all dashboard filter metrics."""
    return _read_query(
        """
        WITH latest_ratios AS (
            SELECT *
            FROM (
                SELECT
                    fr.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY fr.company_id
                        ORDER BY fr.year DESC, fr.id DESC
                    ) AS row_number
                FROM financial_ratios AS fr
                WHERE fr.year IS NOT NULL
            )
            WHERE row_number = 1
        ),
        latest_market AS (
            SELECT *
            FROM (
                SELECT
                    m.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY m.company_id
                        ORDER BY m.year DESC, m.id DESC
                    ) AS row_number
                FROM market_cap AS m
                WHERE m.year IS NOT NULL
            )
            WHERE row_number = 1
        )
        SELECT
            r.company_id,
            REPLACE(REPLACE(c.company_name, char(10), ' '), char(13), ' ')
                AS company_name,
            r.year,
            s.broad_sector,
            r.composite_quality_score,
            r.return_on_equity_pct,
            r.debt_to_equity,
            r.free_cash_flow_cr,
            r.revenue_cagr_5yr,
            r.pat_cagr_5yr,
            r.operating_profit_margin_pct,
            m.pe_ratio,
            m.pb_ratio,
            m.dividend_yield_pct,
            r.interest_coverage,
            r.icr_label
        FROM latest_ratios AS r
        JOIN companies AS c ON c.id = r.company_id
        LEFT JOIN sectors AS s ON s.company_id = r.company_id
        LEFT JOIN latest_market AS m ON m.company_id = r.company_id
        ORDER BY c.company_name
        """
    )


@st.cache_data(ttl=600)
def get_peer_group_names() -> pd.DataFrame:
    """Return every peer group name in display order."""
    return _read_query(
        """
        SELECT peer_group_name, COUNT(*) AS company_count
        FROM peer_groups
        GROUP BY peer_group_name
        ORDER BY peer_group_name
        """
    )


@st.cache_data(ttl=600)
def get_peer_comparison(group_name: str) -> pd.DataFrame:
    """Return latest raw comparison metrics for every company in a peer group."""
    return _read_query(
        """
        WITH latest_ratios AS (
            SELECT *
            FROM (
                SELECT
                    fr.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY fr.company_id
                        ORDER BY fr.year DESC, fr.id DESC
                    ) AS row_number
                FROM financial_ratios AS fr
                WHERE fr.year IS NOT NULL
            )
            WHERE row_number = 1
        )
        SELECT
            pg.peer_group_name,
            pg.company_id,
            REPLACE(REPLACE(c.company_name, char(10), ' '), char(13), ' ')
                AS company_name,
            pg.is_benchmark,
            r.year,
            r.return_on_equity_pct,
            r.return_on_capital_employed_pct,
            r.net_profit_margin_pct,
            r.debt_to_equity,
            r.free_cash_flow_cr,
            r.pat_cagr_5yr,
            r.revenue_cagr_5yr,
            r.eps_cagr_5yr
        FROM peer_groups AS pg
        JOIN companies AS c ON c.id = pg.company_id
        LEFT JOIN latest_ratios AS r ON r.company_id = pg.company_id
        WHERE pg.peer_group_name = ?
        ORDER BY pg.is_benchmark DESC, c.company_name
        """,
        (group_name,),
    )


@st.cache_data(ttl=600)
def get_sector_snapshot() -> pd.DataFrame:
    """Return latest company fundamentals for sector-level charts."""
    return _read_query(
        """
        WITH latest_ratios AS (
            SELECT *
            FROM (
                SELECT
                    fr.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY fr.company_id
                        ORDER BY fr.year DESC, fr.id DESC
                    ) AS row_number
                FROM financial_ratios AS fr
                WHERE fr.year IS NOT NULL
            )
            WHERE row_number = 1
        ),
        latest_pnl AS (
            SELECT *
            FROM (
                SELECT
                    fs.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY fs.company_id
                        ORDER BY fs.year DESC, fs.id DESC
                    ) AS row_number
                FROM financial_statements AS fs
                WHERE fs.statement_type = 'profit_and_loss'
                    AND fs.year IS NOT NULL
            )
            WHERE row_number = 1
        ),
        latest_market AS (
            SELECT *
            FROM (
                SELECT
                    m.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY m.company_id
                        ORDER BY m.year DESC, m.id DESC
                    ) AS row_number
                FROM market_cap AS m
                WHERE m.year IS NOT NULL
            )
            WHERE row_number = 1
        )
        SELECT
            c.id AS ticker,
            REPLACE(REPLACE(c.company_name, char(10), ' '), char(13), ' ')
                AS company_name,
            s.broad_sector,
            s.sub_sector,
            p.sales AS revenue,
            r.return_on_equity_pct,
            r.return_on_capital_employed_pct,
            r.net_profit_margin_pct,
            r.operating_profit_margin_pct,
            r.revenue_cagr_5yr,
            r.pat_cagr_5yr,
            m.market_cap_crore
        FROM companies AS c
        LEFT JOIN sectors AS s ON s.company_id = c.id
        LEFT JOIN latest_ratios AS r ON r.company_id = c.id
        LEFT JOIN latest_pnl AS p ON p.company_id = c.id
        LEFT JOIN latest_market AS m ON m.company_id = c.id
        ORDER BY c.company_name
        """
    )


@st.cache_data(ttl=600)
def get_capital_allocation() -> pd.DataFrame:
    """Return all companies grouped by their latest capital-allocation pattern."""
    return _read_query(
        """
        WITH latest_ratios AS (
            SELECT *
            FROM (
                SELECT
                    fr.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY fr.company_id
                        ORDER BY fr.year DESC, fr.id DESC
                    ) AS row_number
                FROM financial_ratios AS fr
                WHERE fr.year IS NOT NULL
            )
            WHERE row_number = 1
        ),
        latest_market AS (
            SELECT *
            FROM (
                SELECT
                    m.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY m.company_id
                        ORDER BY m.year DESC, m.id DESC
                    ) AS row_number
                FROM market_cap AS m
                WHERE m.year IS NOT NULL
            )
            WHERE row_number = 1
        )
        SELECT
            c.id AS ticker,
            REPLACE(REPLACE(c.company_name, char(10), ' '), char(13), ' ')
                AS company_name,
            COALESCE(
                NULLIF(TRIM(r.capital_allocation_pattern), ''),
                'Unclassified'
            ) AS capital_allocation_pattern,
            r.composite_quality_score,
            r.free_cash_flow_cr,
            m.market_cap_crore
        FROM companies AS c
        LEFT JOIN latest_ratios AS r ON r.company_id = c.id
        LEFT JOIN latest_market AS m ON m.company_id = c.id
        ORDER BY capital_allocation_pattern, c.company_name
        """
    )


@st.cache_data(ttl=600)
def get_reports(ticker: str) -> pd.DataFrame:
    """Return one annual-report record per available year for a ticker."""
    return _read_query(
        """
        SELECT year, annual_report
        FROM (
            SELECT
                d.*,
                ROW_NUMBER() OVER (
                    PARTITION BY d.company_id, d.year
                    ORDER BY d.id DESC
                ) AS row_number
            FROM documents AS d
            WHERE d.company_id = ?
        )
        WHERE row_number = 1
        ORDER BY year DESC
        """,
        (ticker,),
    )
