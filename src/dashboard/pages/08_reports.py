"""Searchable BSE annual-report directory with link validation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
import streamlit as st

from dashboard.utils.db import get_companies, get_reports

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 Nifty100Analytics/1.0"}


def _is_missing_url(value: object) -> bool:
    if value is None or pd.isna(value):
        return True
    return str(value).strip().casefold() in {"", "null", "none", "nan"}


def _url_status(url: str) -> int | None:
    try:
        response = requests.head(
            url,
            allow_redirects=True,
            timeout=4,
            headers=REQUEST_HEADERS,
        )
        if response.status_code == 405:
            response = requests.get(
                url,
                allow_redirects=True,
                timeout=4,
                headers=REQUEST_HEADERS,
                stream=True,
            )
        return response.status_code
    except requests.RequestException:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _check_report_urls(urls: tuple[str, ...]) -> dict[str, int | None]:
    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = executor.map(_url_status, urls)
    return dict(zip(urls, statuses, strict=True))


st.title("Annual Reports")
st.caption("Search a company and open its available BSE annual-report PDFs.")

companies = get_companies()[["id", "company_name"]].copy()
search_text = st.text_input(
    "Search company or ticker",
    placeholder="Try INFY, TCS, HDFC Bank…",
)

if not search_text.strip():
    st.info("Start typing a company name or ticker to find its annual reports.")
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
reports = get_reports(ticker)

if reports.empty:
    st.info("No annual-report records are available for this company.")
    st.stop()

valid_urls = tuple(
    str(url).strip()
    for url in reports["annual_report"]
    if not _is_missing_url(url)
)
with st.spinner("Checking report availability…"):
    statuses = _check_report_urls(valid_urls)

st.subheader(f"{ticker} Annual Reports")
st.caption(f"{len(reports)} report years found")

for report in reports.itertuples(index=False):
    year_column, action_column = st.columns([1, 4], vertical_alignment="center")
    year_column.markdown(f"### {int(report.year)}")
    if _is_missing_url(report.annual_report):
        action_column.markdown(
            '<span style="display:inline-block;padding:.35rem .65rem;border-radius:.5rem;'
            'background:rgba(220,38,38,.12);color:#dc2626;font-weight:600;">'
            "Report unavailable</span>",
            unsafe_allow_html=True,
        )
        continue

    url = str(report.annual_report).strip()
    if statuses.get(url) == 404:
        action_column.markdown(
            '<span style="display:inline-block;padding:.35rem .65rem;border-radius:.5rem;'
            'background:rgba(220,38,38,.12);color:#dc2626;font-weight:600;">'
            "Report unavailable</span>",
            unsafe_allow_html=True,
        )
    else:
        action_column.link_button(
            "Open BSE PDF",
            url,
            icon=":material/picture_as_pdf:",
        )
