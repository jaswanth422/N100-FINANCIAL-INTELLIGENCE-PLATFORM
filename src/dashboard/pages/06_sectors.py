"""Sector-level company positioning and median KPIs."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.utils.db import get_sector_snapshot

MEDIAN_METRICS: dict[str, str] = {
    "ROE": "return_on_equity_pct",
    "ROCE": "return_on_capital_employed_pct",
    "Net Profit Margin": "net_profit_margin_pct",
    "Operating Margin": "operating_profit_margin_pct",
    "Revenue CAGR 5yr": "revenue_cagr_5yr",
    "PAT CAGR 5yr": "pat_cagr_5yr",
}

st.title("Sector Analytics")
st.caption("Compare scale and profitability, then review the selected sector's median KPIs.")

snapshot = get_sector_snapshot()
snapshot["sector"] = snapshot["broad_sector"].fillna("Unclassified")
snapshot.loc[snapshot["sub_sector"].eq("Power & Utilities"), "sector"] = "Utilities"

sector_names = sorted(snapshot["sector"].unique())
selected_sector = st.selectbox("Sector", sector_names)
sector_data = snapshot[snapshot["sector"].eq(selected_sector)].copy()

bubble_data = sector_data.dropna(
    subset=["revenue", "return_on_equity_pct", "market_cap_crore"]
)
bubble_data = bubble_data[bubble_data["market_cap_crore"].gt(0)]

st.subheader(f"{selected_sector} Company Map")
st.caption("Revenue vs ROE · bubble size represents market capitalisation")

if bubble_data.empty:
    st.info("No complete revenue, ROE, and market-cap data is available for this sector.")
else:
    bubble = px.scatter(
        bubble_data,
        x="revenue",
        y="return_on_equity_pct",
        size="market_cap_crore",
        color="sub_sector",
        text="ticker",
        hover_name="company_name",
        hover_data={
            "revenue": ":,.0f",
            "return_on_equity_pct": ":.1f",
            "market_cap_crore": ":,.0f",
            "sub_sector": True,
            "ticker": False,
        },
        labels={
            "revenue": "Revenue (₹ Cr)",
            "return_on_equity_pct": "ROE (%)",
            "market_cap_crore": "Market Cap (₹ Cr)",
            "sub_sector": "Sub-sector",
        },
        size_max=65,
    )
    bubble.update_traces(textposition="top center", marker={"opacity": 0.78})
    bubble.update_layout(
        height=560,
        margin={"l": 15, "r": 15, "t": 25, "b": 15},
        legend={"orientation": "h", "y": -0.15},
        xaxis={"gridcolor": "rgba(128,128,128,0.15)"},
        yaxis={"gridcolor": "rgba(128,128,128,0.15)"},
    )
    st.plotly_chart(bubble, width="stretch", config={"displayModeBar": False})

st.subheader("Sector Median KPIs")
median_values = {
    label: pd.to_numeric(sector_data[column], errors="coerce").median()
    for label, column in MEDIAN_METRICS.items()
}
median_frame = pd.DataFrame(
    {"Metric": list(median_values), "Median": list(median_values.values())}
).dropna()

median_chart = go.Figure(
    go.Bar(
        x=median_frame["Median"],
        y=median_frame["Metric"],
        orientation="h",
        marker={
            "color": median_frame["Median"],
            "colorscale": "Blues",
            "showscale": False,
        },
        text=[f"{value:.1f}%" for value in median_frame["Median"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Median: %{x:.1f}%<extra></extra>",
    )
)
median_chart.update_layout(
    height=400,
    margin={"l": 15, "r": 55, "t": 20, "b": 15},
    xaxis={"title": "Median (%)", "gridcolor": "rgba(128,128,128,0.15)"},
    yaxis={"title": None, "autorange": "reversed"},
)
st.plotly_chart(median_chart, width="stretch", config={"displayModeBar": False})
