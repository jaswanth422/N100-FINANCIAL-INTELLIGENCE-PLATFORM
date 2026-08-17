"""Peer-group radar and KPI comparison."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.utils.db import get_peer_comparison, get_peer_group_names

RADAR_METRICS: tuple[tuple[str, str, bool], ...] = (
    ("ROE", "return_on_equity_pct", False),
    ("ROCE", "return_on_capital_employed_pct", False),
    ("Net Margin", "net_profit_margin_pct", False),
    ("D/E", "debt_to_equity", True),
    ("FCF", "free_cash_flow_cr", False),
    ("PAT CAGR 5yr", "pat_cagr_5yr", False),
    ("Revenue CAGR 5yr", "revenue_cagr_5yr", False),
    ("EPS CAGR 5yr", "eps_cagr_5yr", False),
)


def _percent_rank(values: pd.Series, *, inverse: bool = False) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    result = pd.Series(np.nan, index=values.index, dtype="float64")
    valid = numeric.dropna()
    if len(valid) == 1:
        result.loc[valid.index] = 50.0
    elif len(valid) > 1:
        ranks = valid.rank(method="min", ascending=True)
        percentiles = (ranks - 1.0) / (len(valid) - 1.0) * 100.0
        result.loc[valid.index] = 100.0 - percentiles if inverse else percentiles
    return result


def _highlight_benchmark(row: pd.Series, benchmark_rows: set[int]) -> list[str]:
    color = "background-color: rgba(245, 158, 11, 0.22); font-weight: 600"
    return [color if row.name in benchmark_rows else "" for _ in row]


st.title("Peer Comparison")
st.caption("Compare a company with its closest listed peers using the latest available year.")

group_names = get_peer_group_names()["peer_group_name"].tolist()
selected_group = st.selectbox("Peer group", group_names)
peers = get_peer_comparison(selected_group)

if peers.empty:
    st.warning("No companies are assigned to this peer group.")
    st.stop()

company_labels = {
    f"{row.company_id} — {row.company_name}": row.company_id
    for row in peers.itertuples(index=False)
}
selected_company_label = st.selectbox("Company", list(company_labels))
selected_ticker = company_labels[selected_company_label]
selected_index = peers.index[peers["company_id"].eq(selected_ticker)][0]

metric_labels: list[str] = []
selected_scores: list[float] = []
peer_average_scores: list[float] = []

for label, column, inverse in RADAR_METRICS:
    scores = _percent_rank(peers[column], inverse=inverse)
    metric_labels.append(label)
    selected_scores.append(float(scores.loc[selected_index]))
    peer_average_scores.append(float(scores.mean()))

radar = go.Figure()
radar.add_trace(
    go.Scatterpolar(
        r=selected_scores,
        theta=metric_labels,
        fill="toself",
        name=selected_ticker,
        line={"color": "#2563EB", "width": 3},
        fillcolor="rgba(37, 99, 235, 0.18)",
        hovertemplate="<b>%{theta}</b><br>Percentile: %{r:.0f}<extra></extra>",
    )
)
radar.add_trace(
    go.Scatterpolar(
        r=peer_average_scores,
        theta=metric_labels,
        fill="toself",
        name="Peer group average",
        line={"color": "#F97316", "width": 2, "dash": "dash"},
        fillcolor="rgba(249, 115, 22, 0.08)",
        hovertemplate="<b>%{theta}</b><br>Average percentile: %{r:.0f}<extra></extra>",
    )
)
radar.update_layout(
    height=570,
    margin={"l": 60, "r": 60, "t": 35, "b": 35},
    polar={
        "radialaxis": {
            "visible": True,
            "range": [0, 100],
            "tickvals": [0, 25, 50, 75, 100],
            "ticksuffix": "%",
            "gridcolor": "rgba(128,128,128,0.20)",
        }
    },
    legend={"orientation": "h", "x": 0.5, "xanchor": "center", "y": -0.08},
)

st.subheader(f"{selected_ticker} vs {selected_group}")
st.caption("Eight-metric within-group percentile comparison; a higher score is better.")
st.plotly_chart(radar, width="stretch", config={"displayModeBar": False})

st.subheader("Peer KPI Table")
st.caption("The benchmark company is highlighted in amber.")

comparison = peers[
    [
        "company_id",
        "company_name",
        "return_on_equity_pct",
        "return_on_capital_employed_pct",
        "net_profit_margin_pct",
        "debt_to_equity",
        "free_cash_flow_cr",
        "pat_cagr_5yr",
        "revenue_cagr_5yr",
        "eps_cagr_5yr",
    ]
].rename(
    columns={
        "company_id": "Ticker",
        "company_name": "Company",
        "return_on_equity_pct": "ROE",
        "return_on_capital_employed_pct": "ROCE",
        "net_profit_margin_pct": "Net Margin",
        "debt_to_equity": "D/E",
        "free_cash_flow_cr": "FCF",
        "pat_cagr_5yr": "PAT CAGR 5yr",
        "revenue_cagr_5yr": "Revenue CAGR 5yr",
        "eps_cagr_5yr": "EPS CAGR 5yr",
    }
)
benchmark_rows = set(peers.index[peers["is_benchmark"].eq(1)])
styled_comparison = comparison.style.apply(
    _highlight_benchmark,
    axis=1,
    benchmark_rows=benchmark_rows,
).format(
    {
        "ROE": "{:.1f}%",
        "ROCE": "{:.1f}%",
        "Net Margin": "{:.1f}%",
        "D/E": "{:.2f}x",
        "FCF": "₹{:,.0f} Cr",
        "PAT CAGR 5yr": "{:.1f}%",
        "Revenue CAGR 5yr": "{:.1f}%",
        "EPS CAGR 5yr": "{:.1f}%",
    },
    na_rep="N/A",
)
st.dataframe(styled_comparison, hide_index=True, width="stretch")
