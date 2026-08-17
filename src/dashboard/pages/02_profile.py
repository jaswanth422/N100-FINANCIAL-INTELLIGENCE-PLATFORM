"""Searchable company profile and financial history."""

from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dashboard.utils.db import (
    get_companies,
    get_company_profile,
    get_pl,
    get_pros_cons,
    get_ratios,
)


def _format_percent(value: float) -> str:
    return "N/A" if pd.isna(value) else f"{value:,.1f}%"


def _format_multiple(value: float) -> str:
    return "N/A" if pd.isna(value) else f"{value:,.2f}x"


def _format_crore(value: float) -> str:
    return "N/A" if pd.isna(value) else f"₹{value:,.0f} Cr"


st.title("Company Profile")
st.caption("Search by company name or NSE ticker to review financial quality and history.")

companies = get_companies()[["id", "company_name"]].copy()
search_text = st.text_input(
    "Search company or ticker",
    placeholder="Try HDFC Bank, HDFCBANK, Reliance…",
)

if not search_text.strip():
    st.info("Start typing a company name or ticker to view its profile.")
    st.stop()

needle = search_text.strip().casefold()
matches = companies[
    companies["id"].str.casefold().str.contains(needle, regex=False)
    | companies["company_name"].str.casefold().str.contains(needle, regex=False)
].copy()
matches["_match_priority"] = (
    companies.loc[matches.index, "id"].str.casefold().eq(needle).map({True: 0, False: 2})
)
matches.loc[
    companies.loc[matches.index, "company_name"].str.casefold().eq(needle),
    "_match_priority",
] = 1
matches = matches.sort_values(["_match_priority", "id"]).head(20)

if matches.empty:
    st.warning("Ticker not found — please try another")
    st.stop()

labels = {
    f"{row.id} — {row.company_name}": row.id
    for row in matches.itertuples(index=False)
}
selection = st.selectbox("Matching companies", list(labels))
ticker = labels[selection]

profile = get_company_profile(ticker)
if profile.empty:
    st.warning("Ticker not found — please try another")
    st.stop()

company = profile.iloc[0]

with st.container(border=True):
    name_column, ticker_column = st.columns([4, 1])
    name_column.subheader(company["company_name"])
    sector = company["broad_sector"] if pd.notna(company["broad_sector"]) else "Unclassified"
    sub_sector = company["sub_sector"] if pd.notna(company["sub_sector"]) else "Unclassified"
    name_column.caption(f"{sector} · {sub_sector}")
    ticker_column.metric("NSE Ticker", company["ticker"])
    description = company["about_company"]
    st.write(description if pd.notna(description) else "Company description is not available.")

ratios = get_ratios(ticker).drop_duplicates(subset=["year"], keep="first")
profit_and_loss = get_pl(ticker).drop_duplicates(subset=["year"], keep="first")

if ratios.empty:
    st.info("Financial ratios are not available for this company.")
    st.stop()

latest = ratios.iloc[0]
latest_year = int(latest["year"])

kpi_row = st.columns(6)
kpi_row[0].metric("ROE", _format_percent(latest["return_on_equity_pct"]))
kpi_row[1].metric("ROCE", _format_percent(latest["return_on_capital_employed_pct"]))
kpi_row[2].metric("Net Profit Margin", _format_percent(latest["net_profit_margin_pct"]))
kpi_row[3].metric("D/E", _format_multiple(latest["debt_to_equity"]))
kpi_row[4].metric("Revenue CAGR 5yr", _format_percent(latest["revenue_cagr_5yr"]))
kpi_row[5].metric("FCF", _format_crore(latest["free_cash_flow_cr"]))
st.caption(f"Latest reported financial year: {latest_year}")

st.divider()

financial_history = (
    profit_and_loss.dropna(subset=["year"])
    .sort_values("year")
    .tail(10)
)

if len(financial_history) < 10:
    st.info(
        f"{len(financial_history)} years of financial-statement data available for "
        f"{ticker}; the chart shows all available history."
    )

st.subheader("Revenue and Net Profit")
st.caption("Ten-year financial performance · ₹ crore")
bar_chart = go.Figure()
bar_chart.add_bar(
    x=financial_history["year"],
    y=financial_history["sales"],
    name="Revenue",
    marker_color="#2563EB",
    hovertemplate="FY %{x}<br>Revenue: ₹%{y:,.0f} Cr<extra></extra>",
)
bar_chart.add_bar(
    x=financial_history["year"],
    y=financial_history["net_profit"],
    name="Net Profit",
    marker_color="#14B8A6",
    hovertemplate="FY %{x}<br>Net Profit: ₹%{y:,.0f} Cr<extra></extra>",
)
bar_chart.update_layout(
    barmode="group",
    height=430,
    margin={"l": 10, "r": 10, "t": 20, "b": 10},
    legend={"orientation": "h", "y": 1.08},
    xaxis={"title": None, "dtick": 1},
    yaxis={"title": "₹ crore", "gridcolor": "rgba(128,128,128,0.15)"},
)
st.plotly_chart(bar_chart, width="stretch", config={"displayModeBar": False})

ratio_history = ratios.dropna(subset=["year"]).sort_values("year").tail(10)

if len(ratio_history) < 10:
    st.info(
        f"{len(ratio_history)} years of ratio data available for "
        f"{ticker}; the chart shows all available history."
    )

st.subheader("Return Ratios")
st.caption("ROE and ROCE over ten years")
return_chart = make_subplots(specs=[[{"secondary_y": True}]])
return_chart.add_trace(
    go.Scatter(
        x=ratio_history["year"],
        y=ratio_history["return_on_equity_pct"],
        name="ROE",
        mode="lines+markers",
        line={"color": "#7C3AED", "width": 3},
        hovertemplate="FY %{x}<br>ROE: %{y:.1f}%<extra></extra>",
    ),
    secondary_y=False,
)
return_chart.add_trace(
    go.Scatter(
        x=ratio_history["year"],
        y=ratio_history["return_on_capital_employed_pct"],
        name="ROCE",
        mode="lines+markers",
        line={"color": "#F97316", "width": 3},
        hovertemplate="FY %{x}<br>ROCE: %{y:.1f}%<extra></extra>",
    ),
    secondary_y=True,
)
return_chart.update_layout(
    height=430,
    margin={"l": 10, "r": 10, "t": 20, "b": 10},
    legend={"orientation": "h", "y": 1.08},
    xaxis={"title": None, "dtick": 1},
)
return_chart.update_yaxes(title_text="ROE (%)", ticksuffix="%", secondary_y=False)
return_chart.update_yaxes(title_text="ROCE (%)", ticksuffix="%", secondary_y=True)
st.plotly_chart(return_chart, width="stretch", config={"displayModeBar": False})

qualitative = get_pros_cons(ticker)
pros = [str(value).strip() for value in qualitative["pros"].dropna() if str(value).strip()]
cons = [str(value).strip() for value in qualitative["cons"].dropna() if str(value).strip()]

st.subheader("Pros and Cons")
pros_column, cons_column = st.columns(2, gap="large")

badge_css = """
<style>
.profile-badge {
    border-radius: 0.65rem;
    margin: 0.5rem 0;
    padding: 0.7rem 0.85rem;
    line-height: 1.4;
}
.profile-pro {
    background: rgba(22, 163, 74, 0.10);
    border: 1px solid rgba(22, 163, 74, 0.32);
}
.profile-con {
    background: rgba(220, 38, 38, 0.10);
    border: 1px solid rgba(220, 38, 38, 0.30);
}
</style>
"""
st.markdown(badge_css, unsafe_allow_html=True)

with pros_column:
    st.markdown("#### Strengths")
    if pros:
        for item in pros:
            st.markdown(
                f'<div class="profile-badge profile-pro">✅ {escape(item)}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No strengths have been recorded for this company.")

with cons_column:
    st.markdown("#### Watch-outs")
    if cons:
        for item in cons:
            st.markdown(
                f'<div class="profile-badge profile-con">❌ {escape(item)}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No watch-outs have been recorded for this company.")
