"""Main entry point for the Nifty 100 Analytics Streamlit application."""

import sys
from pathlib import Path

import streamlit as st

DASHBOARD_DIR = Path(__file__).resolve().parent
SRC_DIR = DASHBOARD_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

st.set_page_config(
    page_title="Nifty 100 Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGES_DIR = DASHBOARD_DIR / "pages"

pages = [
    st.Page(PAGES_DIR / "01_home.py", title="Home", icon=":material/home:", default=True),
    st.Page(PAGES_DIR / "02_profile.py", title="Company Profile", icon=":material/domain:"),
    st.Page(PAGES_DIR / "03_screener.py", title="Stock Screener", icon=":material/filter_alt:"),
    st.Page(PAGES_DIR / "04_peers.py", title="Peer Comparison", icon=":material/compare_arrows:"),
    st.Page(PAGES_DIR / "05_trends.py", title="Financial Trends", icon=":material/show_chart:"),
    st.Page(PAGES_DIR / "06_sectors.py", title="Sector Analytics", icon=":material/pie_chart:"),
    st.Page(
        PAGES_DIR / "07_capital.py",
        title="Capital Allocation",
        icon=":material/account_balance:",
    ),
    st.Page(PAGES_DIR / "08_reports.py", title="Reports", icon=":material/description:"),
]

navigation = st.navigation(pages, position="sidebar")
navigation.run()
