"""Interactive financial screener."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.utils.db import get_screener_universe

FILTER_DEFAULTS: dict[str, float] = {
    "roe_min": -100.0,
    "de_max": 15.0,
    "fcf_min": -110_000.0,
    "revenue_cagr_min": -25.0,
    "pat_cagr_min": -50.0,
    "opm_min": -25.0,
    "pe_max": 100.0,
    "pb_max": 20.0,
    "dividend_yield_min": 0.0,
    "icr_min": 0.0,
}

PRESETS: dict[str, dict[str, float]] = {
    "Quality": {
        **FILTER_DEFAULTS,
        "roe_min": 15.0,
        "de_max": 1.0,
        "fcf_min": 0.0,
        "revenue_cagr_min": 10.0,
    },
    "Value": {
        **FILTER_DEFAULTS,
        "de_max": 2.0,
        "pe_max": 20.0,
        "pb_max": 5.0,
        "dividend_yield_min": 1.0,
    },
    "Growth": {
        **FILTER_DEFAULTS,
        "de_max": 2.0,
        "revenue_cagr_min": 15.0,
        "pat_cagr_min": 20.0,
    },
    "Dividend": {
        **FILTER_DEFAULTS,
        "fcf_min": 0.0,
        "dividend_yield_min": 2.0,
    },
    "Debt-Free": {
        **FILTER_DEFAULTS,
        "roe_min": 12.0,
        "de_max": 0.02,
    },
    "Turnaround": {
        **FILTER_DEFAULTS,
        "fcf_min": 0.0,
        "revenue_cagr_min": 10.0,
    },
}

SLIDER_KEYS = {
    name: f"screener_{name}"
    for name in FILTER_DEFAULTS
}


def _apply_preset(name: str) -> None:
    for filter_name, value in PRESETS[name].items():
        st.session_state[SLIDER_KEYS[filter_name]] = value
    st.session_state["screener_active_preset"] = name


def _filter_universe(universe: pd.DataFrame, filters: dict[str, float]) -> pd.DataFrame:
    numeric_filters: tuple[tuple[str, str, str], ...] = (
        ("return_on_equity_pct", "roe_min", "min"),
        ("debt_to_equity", "de_max", "max"),
        ("free_cash_flow_cr", "fcf_min", "min"),
        ("revenue_cagr_5yr", "revenue_cagr_min", "min"),
        ("pat_cagr_5yr", "pat_cagr_min", "min"),
        ("operating_profit_margin_pct", "opm_min", "min"),
        ("pe_ratio", "pe_max", "max"),
        ("pb_ratio", "pb_max", "max"),
        ("dividend_yield_pct", "dividend_yield_min", "min"),
    )
    mask = pd.Series(True, index=universe.index)
    for column, filter_name, direction in numeric_filters:
        values = pd.to_numeric(universe[column], errors="coerce")
        threshold = filters[filter_name]
        mask &= values.ge(threshold) if direction == "min" else values.le(threshold)

    coverage = pd.to_numeric(universe["interest_coverage"], errors="coerce")
    debt_free = (
        universe["icr_label"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .eq("debt free")
        .fillna(False)
    )
    coverage = coverage.mask(debt_free, float("inf"))
    mask &= coverage.ge(filters["icr_min"])

    return universe.loc[mask].sort_values(
        ["composite_quality_score", "company_name"],
        ascending=[False, True],
        na_position="last",
    )


st.title("Stock Screener")
st.caption("Filter the latest available financial year across ten quality and valuation metrics.")

for filter_name, default in FILTER_DEFAULTS.items():
    st.session_state.setdefault(SLIDER_KEYS[filter_name], default)

with st.sidebar:
    st.subheader("Screener Filters")
    roe_min = st.slider(
        "ROE minimum (%)",
        -100.0,
        100.0,
        step=1.0,
        key=SLIDER_KEYS["roe_min"],
    )
    de_max = st.slider(
        "D/E maximum (x)",
        0.0,
        15.0,
        step=0.05,
        key=SLIDER_KEYS["de_max"],
    )
    fcf_min = st.slider(
        "FCF minimum (₹ Cr)",
        -110_000.0,
        50_000.0,
        step=500.0,
        key=SLIDER_KEYS["fcf_min"],
    )
    revenue_cagr_min = st.slider(
        "Revenue CAGR 5yr minimum (%)",
        -25.0,
        50.0,
        step=1.0,
        key=SLIDER_KEYS["revenue_cagr_min"],
    )
    pat_cagr_min = st.slider(
        "PAT CAGR 5yr minimum (%)",
        -50.0,
        150.0,
        step=1.0,
        key=SLIDER_KEYS["pat_cagr_min"],
    )
    opm_min = st.slider(
        "OPM minimum (%)",
        -25.0,
        110.0,
        step=1.0,
        key=SLIDER_KEYS["opm_min"],
    )
    pe_max = st.slider(
        "P/E maximum (x)",
        0.0,
        100.0,
        step=1.0,
        key=SLIDER_KEYS["pe_max"],
    )
    pb_max = st.slider(
        "P/B maximum (x)",
        0.0,
        20.0,
        step=0.5,
        key=SLIDER_KEYS["pb_max"],
    )
    dividend_yield_min = st.slider(
        "Dividend Yield minimum (%)",
        0.0,
        10.0,
        step=0.1,
        key=SLIDER_KEYS["dividend_yield_min"],
    )
    icr_min = st.slider(
        "ICR minimum (x)",
        0.0,
        100.0,
        step=0.5,
        key=SLIDER_KEYS["icr_min"],
    )

filters = {
    "roe_min": roe_min,
    "de_max": de_max,
    "fcf_min": fcf_min,
    "revenue_cagr_min": revenue_cagr_min,
    "pat_cagr_min": pat_cagr_min,
    "opm_min": opm_min,
    "pe_max": pe_max,
    "pb_max": pb_max,
    "dividend_yield_min": dividend_yield_min,
    "icr_min": icr_min,
}

st.subheader("Quick Presets")
preset_columns = st.columns(6)
for column, preset_name in zip(preset_columns, PRESETS, strict=True):
    column.button(
        preset_name,
        key=f"preset_{preset_name.casefold().replace('-', '_')}",
        on_click=_apply_preset,
        args=(preset_name,),
        width="stretch",
    )

active_preset = st.session_state.get("screener_active_preset")
if active_preset:
    st.caption(f"Active preset: {active_preset}")

universe = get_screener_universe()
results = _filter_universe(universe, filters)

visible_columns = {
    "company_id": "Ticker",
    "company_name": "Company",
    "broad_sector": "Sector",
    "composite_quality_score": "Composite Score",
    "return_on_equity_pct": "ROE",
    "debt_to_equity": "D/E",
    "free_cash_flow_cr": "FCF",
    "revenue_cagr_5yr": "Revenue CAGR 5yr",
    "pat_cagr_5yr": "PAT CAGR 5yr",
    "operating_profit_margin_pct": "OPM",
    "pe_ratio": "P/E",
    "pb_ratio": "P/B",
    "dividend_yield_pct": "Dividend Yield",
    "interest_coverage": "ICR",
}
display_results = (
    results[list(visible_columns)]
    .rename(columns=visible_columns)
    .reset_index(drop=True)
)

st.subheader(f"{len(display_results)} companies match your filters")

st.dataframe(
    display_results,
    hide_index=True,
    width="stretch",
    column_config={
        "Composite Score": st.column_config.NumberColumn(format="%.1f"),
        "ROE": st.column_config.NumberColumn(format="%.1f%%"),
        "D/E": st.column_config.NumberColumn(format="%.2fx"),
        "FCF": st.column_config.NumberColumn(format="₹%,.0f Cr"),
        "Revenue CAGR 5yr": st.column_config.NumberColumn(format="%.1f%%"),
        "PAT CAGR 5yr": st.column_config.NumberColumn(format="%.1f%%"),
        "OPM": st.column_config.NumberColumn(format="%.1f%%"),
        "P/E": st.column_config.NumberColumn(format="%.2fx"),
        "P/B": st.column_config.NumberColumn(format="%.2fx"),
        "Dividend Yield": st.column_config.NumberColumn(format="%.2f%%"),
        "ICR": st.column_config.NumberColumn(format="%.2fx"),
    },
)

csv_data = display_results.to_csv(index=False, lineterminator="\n").encode("utf-8")
st.download_button(
    "Download results as CSV",
    data=csv_data,
    file_name="nifty100_screener_results.csv",
    mime="text/csv",
    disabled=display_results.empty,
)
