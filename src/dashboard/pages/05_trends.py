"""Ten-year, multi-metric company trend analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.utils.db import get_companies, get_pl, get_ratios

METRICS: dict[str, str] = {
    "Revenue": "sales",
    "Net Profit": "net_profit",
    "ROE": "return_on_equity_pct",
    "ROCE": "return_on_capital_employed_pct",
    "Operating Margin": "operating_profit_margin_pct",
    "Net Profit Margin": "net_profit_margin_pct",
    "D/E": "debt_to_equity",
    "Free Cash Flow": "free_cash_flow_cr",
    "Revenue CAGR 5yr": "revenue_cagr_5yr",
    "PAT CAGR 5yr": "pat_cagr_5yr",
}
COLORS = ["#2563EB", "#14B8A6", "#F97316"]


def _yoy_labels(values: pd.Series) -> list[str]:
    numeric = pd.to_numeric(values, errors="coerce")
    changes = numeric.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan) * 100
    return ["—" if pd.isna(value) else f"{value:+.1f}%" for value in changes]


st.title("Financial Trends")
st.caption("Overlay up to three metrics and inspect the year-over-year movement at every point.")

companies = get_companies()[["id", "company_name"]].copy()
search_text = st.text_input(
    "Search company or ticker",
    placeholder="Try TCS, HDFC Bank, RELIANCE…",
)

if not search_text.strip():
    st.info("Start typing a company name or ticker to explore its trends.")
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

company_labels = {
    f"{row.id} — {row.company_name}": row.id
    for row in matches.itertuples(index=False)
}
selected_label = st.selectbox("Matching companies", list(company_labels))
ticker = company_labels[selected_label]

selected_metrics = st.multiselect(
    "Metrics",
    list(METRICS),
    default=["Revenue", "Net Profit"],
    max_selections=3,
    help="Select one to three metrics to overlay.",
)

if not selected_metrics:
    st.info("Choose at least one metric to draw the trend chart.")
    st.stop()

profit_and_loss = (
    get_pl(ticker)
    .drop_duplicates(subset=["year"], keep="first")
    [["year", "sales", "net_profit"]]
)
ratios = (
    get_ratios(ticker)
    .drop_duplicates(subset=["year"], keep="first")
    [
        [
            "year",
            "return_on_equity_pct",
            "return_on_capital_employed_pct",
            "operating_profit_margin_pct",
            "net_profit_margin_pct",
            "debt_to_equity",
            "free_cash_flow_cr",
            "revenue_cagr_5yr",
            "pat_cagr_5yr",
        ]
    ]
)
history = (
    profit_and_loss.merge(ratios, on="year", how="outer")
    .dropna(subset=["year"])
    .sort_values("year")
    .tail(10)
)

if len(history) < 10:
    st.info(
        f"{len(history)} years of data available for {ticker}; "
        "the chart shows all available history."
    )

chart = go.Figure()
for color, metric_name in zip(COLORS, selected_metrics, strict=False):
    column = METRICS[metric_name]
    labels = _yoy_labels(history[column])
    chart.add_trace(
        go.Scatter(
            x=history["year"],
            y=history[column],
            name=metric_name,
            mode="lines+markers+text",
            text=labels,
            textposition="top center",
            textfont={"size": 10, "color": color},
            line={"color": color, "width": 3},
            marker={"size": 8},
            customdata=labels,
            hovertemplate=(
                f"<b>{metric_name}</b><br>FY %{{x}}<br>"
                "Value: %{y:,.2f}<br>YoY: %{customdata}<extra></extra>"
            ),
        )
    )

chart.update_layout(
    height=560,
    margin={"l": 15, "r": 15, "t": 35, "b": 15},
    legend={"orientation": "h", "y": 1.1},
    hovermode="x unified",
    xaxis={"title": None, "dtick": 1},
    yaxis={"title": "Reported value", "gridcolor": "rgba(128,128,128,0.18)"},
)

st.subheader(f"{ticker} · Ten-Year Trend")
st.caption("Labels show year-over-year percentage change.")
st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})
