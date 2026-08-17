"""Nifty 100 market overview."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.utils.db import get_home_snapshot

YEARS = list(range(2019, 2025))
CHART_COLORS = [
    "#2563EB",
    "#0891B2",
    "#0D9488",
    "#16A34A",
    "#65A30D",
    "#CA8A04",
    "#EA580C",
    "#DC2626",
    "#DB2777",
    "#9333EA",
    "#4F46E5",
]


def _format_percent(value: float) -> str:
    return "N/A" if pd.isna(value) else f"{value:,.1f}%"


def _format_multiple(value: float) -> str:
    return "N/A" if pd.isna(value) else f"{value:,.2f}x"


st.title("Nifty 100 Analytics")
st.caption("A year-by-year view of quality, growth, leverage, and valuation.")

selected_year = st.sidebar.selectbox(
    "Financial year",
    YEARS,
    index=len(YEARS) - 1,
    key="home_year",
)

snapshot = get_home_snapshot(selected_year)

if snapshot.empty:
    st.warning(f"No company data is available for {selected_year}.")
    st.stop()

average_roe = snapshot["return_on_equity_pct"].mean()
median_pe = snapshot["pe_ratio"].median()
median_de = snapshot["debt_to_equity"].median()
median_revenue_cagr = snapshot["revenue_cagr_5yr"].median()
debt_free_count = int(snapshot["debt_to_equity"].le(0).sum())

first_row = st.columns(3)
second_row = st.columns(3)

first_row[0].metric("Average ROE", _format_percent(average_roe))
first_row[1].metric("Median P/E", _format_multiple(median_pe))
first_row[2].metric("Median D/E", _format_multiple(median_de))
second_row[0].metric("Total Companies", f"{len(snapshot):,}")
second_row[1].metric("Median Revenue CAGR 5yr", _format_percent(median_revenue_cagr))
second_row[2].metric("Debt-Free Companies", f"{debt_free_count:,}")

st.divider()

sector_data = snapshot[["broad_sector", "sub_sector"]].copy()
sector_data["sector"] = sector_data["broad_sector"].fillna("Unclassified")
utilities = sector_data["sub_sector"].eq("Power & Utilities")
sector_data.loc[utilities, "sector"] = "Utilities"
sector_counts = (
    sector_data.groupby("sector", as_index=False)
    .size()
    .rename(columns={"size": "company_count"})
    .sort_values("company_count", ascending=False)
)

breakdown_column, ranking_column = st.columns([1, 1.25], gap="large")

with breakdown_column:
    st.subheader("Sector Breakdown")
    st.caption(f"Company count by sector · FY {selected_year}")
    donut = go.Figure(
        go.Pie(
            labels=sector_counts["sector"],
            values=sector_counts["company_count"],
            hole=0.62,
            sort=False,
            textinfo="label+value",
            hovertemplate="<b>%{label}</b><br>%{value} companies<extra></extra>",
            marker={"colors": CHART_COLORS},
        )
    )
    donut.update_layout(
        height=500,
        margin={"l": 10, "r": 10, "t": 25, "b": 10},
        legend={"orientation": "h", "yanchor": "top", "y": -0.08},
        annotations=[
            {
                "text": f"<b>{len(sector_counts)}</b><br>sectors",
                "showarrow": False,
                "font": {"size": 17},
            }
        ],
    )
    st.plotly_chart(donut, width="stretch", config={"displayModeBar": False})

with ranking_column:
    st.subheader("Top Quality Companies")
    st.caption(f"Top five by composite quality score · FY {selected_year}")
    top_companies = (
        snapshot.dropna(subset=["composite_quality_score"])
        .nlargest(5, "composite_quality_score")
        .reset_index(drop=True)
    )
    top_companies.index += 1
    top_companies.index.name = "Rank"
    top_table = top_companies[
        [
            "ticker",
            "company_name",
            "broad_sector",
            "composite_quality_score",
            "return_on_equity_pct",
        ]
    ].rename(
        columns={
            "ticker": "Ticker",
            "company_name": "Company",
            "broad_sector": "Sector",
            "composite_quality_score": "Quality Score",
            "return_on_equity_pct": "ROE",
        }
    )
    st.dataframe(
        top_table,
        width="stretch",
        column_config={
            "Quality Score": st.column_config.NumberColumn(format="%.1f"),
            "ROE": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
