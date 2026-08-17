"""Capital-allocation treemap and pattern drill-down."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.utils.db import get_capital_allocation

st.title("Capital Allocation Map")
st.caption("Explore all companies by their latest cash-flow-based capital-allocation pattern.")

allocation = get_capital_allocation()
allocation["treemap_size"] = (
    pd.to_numeric(allocation["market_cap_crore"], errors="coerce")
    .clip(lower=0)
    .fillna(0)
    .add(1)
)
patterns = allocation["capital_allocation_pattern"].drop_duplicates().tolist()

treemap = px.treemap(
    allocation,
    path=["capital_allocation_pattern", "ticker"],
    values="treemap_size",
    color="composite_quality_score",
    color_continuous_scale="RdYlGn",
    color_continuous_midpoint=50,
    custom_data=[
        "capital_allocation_pattern",
        "company_name",
        "market_cap_crore",
        "free_cash_flow_cr",
    ],
)
treemap.update_traces(
    root_color="rgba(128,128,128,0.08)",
    hovertemplate=(
        "<b>%{label}</b><br>"
        "Pattern: %{customdata[0]}<br>"
        "Company: %{customdata[1]}<br>"
        "Market Cap: ₹%{customdata[2]:,.0f} Cr<br>"
        "FCF: ₹%{customdata[3]:,.0f} Cr<extra></extra>"
    ),
)
treemap.update_layout(
    height=650,
    margin={"l": 5, "r": 5, "t": 25, "b": 5},
    coloraxis_colorbar={"title": "Quality<br>Score"},
    clickmode="event+select",
)

event = st.plotly_chart(
    treemap,
    width="stretch",
    key="capital_allocation_treemap",
    on_select="rerun",
    selection_mode="points",
)

selected_from_chart: str | None = None
if event.selection.points:
    selected_point = event.selection.points[-1]
    point_label = selected_point.get("label")
    custom_data = selected_point.get("customdata") or []
    if point_label in patterns:
        selected_from_chart = point_label
    elif custom_data and custom_data[0] in patterns:
        selected_from_chart = custom_data[0]

if selected_from_chart:
    st.session_state["capital_selected_pattern"] = selected_from_chart

st.session_state.setdefault("capital_selected_pattern", patterns[0])
selected_pattern = st.selectbox(
    "Selected pattern",
    patterns,
    key="capital_selected_pattern",
    help="Click a treemap tile or choose a pattern to inspect its companies.",
)

selected_companies = allocation[
    allocation["capital_allocation_pattern"].eq(selected_pattern)
].copy()
selected_companies = selected_companies.sort_values(
    ["composite_quality_score", "company_name"],
    ascending=[False, True],
    na_position="last",
)

st.subheader(f"{selected_pattern} · {len(selected_companies)} companies")
display_companies = selected_companies[
    [
        "ticker",
        "company_name",
        "composite_quality_score",
        "free_cash_flow_cr",
        "market_cap_crore",
    ]
].rename(
    columns={
        "ticker": "Ticker",
        "company_name": "Company",
        "composite_quality_score": "Quality Score",
        "free_cash_flow_cr": "FCF",
        "market_cap_crore": "Market Cap",
    }
)
styled_companies = display_companies.style.format(
    {
        "Quality Score": "{:.1f}",
        "FCF": "₹{:,.0f} Cr",
        "Market Cap": "₹{:,.0f} Cr",
    },
    na_rep="N/A",
)
st.dataframe(
    styled_companies,
    hide_index=True,
    width="stretch",
)
