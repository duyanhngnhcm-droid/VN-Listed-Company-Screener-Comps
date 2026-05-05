"""
ui_global_peers.py
==================
Tab 3 — Global peers (OPCM).

Renders:
- Banner caveats (yfinance coverage, automated selection)
- Ticker selector (defaults from "View global peers" click in Tab 2)
- Peer table (target highlighted, peers below) in USD
- Per-multiple peer median, target percentile rank
- Implied valuation RANGE (never a single point)
- OPCM relaxation log
"""

from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

from config import VN30_CONSTITUENTS
from currency_normalizer import fx_snapshot_timestamp
from peer_screener import implied_value_range, run_opcm
from sector_mapping import lookup_sector


def _fmt_money_b(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"${v:,.2f} B"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v*100:.1f}%"


def _fmt_mult(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.1f}"


def _format_peer_table(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["Ticker"] = df["ticker"]
    out["Name"] = df["name"]
    out["Country"] = df["country"]
    out["Trading ccy"] = df["trading_ccy"]
    out["Mkt cap (USD B)"] = df["market_cap_usd_b"].apply(_fmt_money_b)
    out["Revenue (USD B)"] = df["revenue_usd_b"].apply(_fmt_money_b)
    out["Rev growth"] = df["revenue_growth"].apply(_fmt_pct)
    out["ROE"] = df["roe"].apply(_fmt_pct)
    out["Op margin"] = df["operating_margin"].apply(_fmt_pct)
    out["D/E"] = df["debt_to_equity"].apply(_fmt_mult)
    out["P/E"] = df["pe"].apply(_fmt_mult)
    out["P/B"] = df["pb"].apply(_fmt_mult)
    out["EV/EBITDA"] = df["ev_ebitda"].apply(_fmt_mult)
    out["Div yield"] = df["dividend_yield"].apply(_fmt_pct)
    return out


def render(default_ticker: Optional[str] = None) -> None:
    st.markdown("### Global peers (OPCM)")

    # Mandatory banners
    st.warning(
        "Peer data sourced from yfinance. Coverage outside the US is incomplete; "
        "some metrics may be missing. Use as **first-draft screen**, not definitive analysis."
    )
    st.info(
        "Peer selection is automated. **Sanity-check before relying on these comparables.** "
        "OPCM = Operation > Performance > Credit > Market (strict priority cascade)."
    )

    fx_ts = fx_snapshot_timestamp()
    if fx_ts:
        st.caption(f"FX snapshot: {fx_ts.strftime('%Y-%m-%d %H:%M UTC')}")

    # ---- Ticker selector ----
    tickers = [t for t, *_ in VN30_CONSTITUENTS]
    if default_ticker is None:
        default_ticker = st.session_state.get("global_peers_target", tickers[0])
    if default_ticker not in tickers:
        default_ticker = tickers[0]
    selected = st.selectbox(
        "VN30 target",
        options=tickers,
        index=tickers.index(default_ticker),
        key="global_peers_select",
    )
    st.session_state["global_peers_target"] = selected

    if not st.button("Run OPCM cascade", type="primary"):
        st.caption("Click **Run OPCM cascade** to fetch peers from yfinance.")
        return

    sector = lookup_sector(selected)
    st.caption(f"Sector bucket: **{sector}**")
    with st.spinner(f"Running OPCM cascade for {selected}..."):
        peer_df, log_ = run_opcm(selected, sector)

    if peer_df.empty:
        st.error("No peer data returned. yfinance may be rate-limiting or this sector pool may be empty.")
        return

    # Highlight target row (row 0)
    target_row = peer_df.iloc[0]
    peers_only = peer_df.iloc[1:]

    table = _format_peer_table(peer_df)
    def _highlight_target(row):
        return ["background-color:#fef3c7" if row.name == 0 else "" for _ in row]
    styler = table.style.apply(_highlight_target, axis=1)
    st.dataframe(styler, use_container_width=True, hide_index=True)

    # ---- Peer median + target percentile ----
    st.markdown("#### Peer multiples")
    multiples = ["pe", "pb", "ev_ebitda", "dividend_yield", "roe", "operating_margin"]
    rows = []
    for m in multiples:
        if m not in peers_only.columns:
            continue
        peer_vals = peers_only[m].dropna()
        if peer_vals.empty:
            continue
        median = float(peer_vals.median())
        target_v = target_row.get(m)
        pct_rank = None
        if target_v is not None and not (isinstance(target_v, float) and np.isnan(target_v)):
            pct_rank = float((peer_vals < target_v).mean()) * 100
        rows.append({
            "Multiple": m.replace("_", " ").upper(),
            "Target": (f"{target_v:.2f}" if target_v is not None and not pd.isna(target_v) else "—"),
            "Peer median": f"{median:.2f}",
            "Target percentile": (f"{pct_rank:.0f}%" if pct_rank is not None else "—"),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ---- Implied valuation range (NEVER a point estimate) ----
    st.markdown("#### Implied valuation range")
    st.caption("Range = peer 25th–75th percentile of each multiple. Apply to the target's "
               "earnings/book/EBITDA per share to get a value band. Never a point estimate.")
    ranges = implied_value_range(peers_only, target_row)
    if not ranges:
        st.caption("(insufficient peer multiples to compute a range)")
    else:
        rdf = pd.DataFrame([
            {"Multiple": k.upper().replace("_", "/"),
             "Low (P25)": f"{lo:.2f}",
             "High (P75)": f"{hi:.2f}"}
            for k, (lo, hi) in ranges.items()
        ])
        st.dataframe(rdf, use_container_width=True, hide_index=True)

    # ---- OPCM relaxation log ----
    with st.expander("📜 OPCM relaxation log", expanded=True):
        if not log_.notes:
            st.caption("(no relaxations recorded)")
        for note in log_.notes:
            st.caption(f"• {note}")
