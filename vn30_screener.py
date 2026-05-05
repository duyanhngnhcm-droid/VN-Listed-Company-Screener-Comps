"""
vn30_screener.py
================
Streamlit entry point.

Run with:
    streamlit run vn30_screener.py
"""

from __future__ import annotations
from datetime import datetime

import pandas as pd
import streamlit as st

from config import TTL_FUNDAMENTALS_S
from data_pipeline import fetch_vn30_dataset
import ui_screener
import ui_deep_dive
import ui_global_peers


st.set_page_config(
    page_title="VN30 Listed Company Screener",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=TTL_FUNDAMENTALS_S, show_spinner="Fetching VN30 fundamentals from yfinance...")
def _cached_fetch() -> pd.DataFrame:
    return fetch_vn30_dataset()


def _refresh_dataset() -> None:
    """Force-refresh: clears caches, re-runs fetch, and stamps timestamp."""
    _cached_fetch.clear()
    st.session_state["last_refresh"] = datetime.utcnow()
    st.rerun()


def _switch_to_global_peers(ticker: str) -> None:
    st.session_state["global_peers_target"] = ticker
    st.session_state["active_tab"] = "global_peers"
    st.rerun()


def _header_banner() -> None:
    st.markdown(
        "<h2 style='margin-bottom:4px;'>VN30 Listed Company Screener</h2>"
        "<div style='color:#475569; font-size:0.95em; margin-bottom:12px;'>"
        "Composite scoring with two sector-aware scorecards (banks · non-financials), "
        "with OPCM-based global peer screen.</div>",
        unsafe_allow_html=True,
    )
    last = st.session_state.get("last_refresh")
    if last:
        st.caption(f"Last data refresh: {last.strftime('%Y-%m-%d %H:%M UTC')}")
    st.info(
        "Vietnamese financials sourced from **yfinance** (using the `.VN` ticker suffix). "
        "Global peer data also from **yfinance** with known coverage gaps for ASEAN names. "
        "Use as a research tool, not as trading recommendations.",
        icon="ℹ️",
    )


def main() -> None:
    _header_banner()

    if "last_refresh" not in st.session_state:
        st.session_state["last_refresh"] = datetime.utcnow()

    df = _cached_fetch()

    # Tabs
    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = "screener"

    tab_labels = ["📊 Screener", "🌟 Top performers", "🌏 Global peers"]
    tab1, tab2, tab3 = st.tabs(tab_labels)

    with tab1:
        ui_screener.render(df, on_refresh=_refresh_dataset)
    with tab2:
        ui_deep_dive.render(df, on_view_peers=_switch_to_global_peers)
    with tab3:
        ui_global_peers.render(default_ticker=st.session_state.get("global_peers_target"))


if __name__ == "__main__":
    main()
