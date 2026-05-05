"""
ui_deep_dive.py
===============
Tab 2 — Top performers deep dive.

For each scorecard:
- Top 5 banks, Top 8 non-financials.
- Each card: rank, free-float flag, mini revenue/EBITDA bar chart, score
  breakdown by metric, 3-line key-metrics summary, "View global peers" button.

The score-breakdown chart is the most analytically useful element — it shows
WHICH metrics drove a composite rank. In an interview, this is what you'd
walk through.
"""

from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

import plotly.graph_objects as go

from config import (
    DEFAULT_WEIGHTS_BANKS,
    DEFAULT_WEIGHTS_NON_FINANCIALS,
    METRIC_FORMAT,
    METRIC_LABELS,
    THIN_FLOAT_THRESHOLD,
)
from scoring import apply_scoring
from weight_panel import get_active_weights


def _fmt(v: Optional[float], fmt: str) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if fmt == "pct":
        return f"{v*100:.1f}%"
    return f"{v:.1f}"


def _score_breakdown_chart(row: pd.Series, scorecard: str, method: str) -> go.Figure:
    if scorecard == "banks":
        weights = DEFAULT_WEIGHTS_BANKS
    else:
        weights = DEFAULT_WEIGHTS_NON_FINANCIALS

    metrics = list(weights.keys())
    if method == "zscore":
        col_prefix = "z__"
    else:
        col_prefix = "rank__"
    values = []
    labels = []
    for m in metrics:
        col = f"{col_prefix}{m}"
        v = row.get(col)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        labels.append(METRIC_LABELS.get(m, m))
        values.append(float(v))

    fig = go.Figure(go.Bar(x=values, y=labels, orientation="h",
                           marker_color="#4f46e5"))
    if method == "rank":
        fig.update_layout(title="Per-metric rank (lower = better)",
                          xaxis=dict(autorange="reversed"))
    else:
        fig.update_layout(title="Per-metric z-score (higher = better)")
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=40, b=20))
    return fig


def _render_card(row: pd.Series, scorecard: str, method: str, on_view_peers) -> None:
    rank = row.get("composite_rank")
    rank_str = f"#{int(rank)}" if rank and not pd.isna(rank) else "—"
    ff = row.get("free_float", 0)
    ff_flag = " 🚩" if ff < THIN_FLOAT_THRESHOLD else ""
    tags = row.get("tags", []) or []
    tag_str = " · ".join(f"`{t}`" for t in tags) if tags else ""

    with st.container(border=True):
        st.markdown(f"### {rank_str} — {row['ticker']} · {row['name']}")
        st.caption(f"{row['sub_sector']} · Free float {ff*100:.0f}%{ff_flag}{(' · ' + tag_str) if tag_str else ''}")

        # 3-line key metrics
        if scorecard == "banks":
            lines = [
                f"**ROE** {_fmt(row.get('roe'), 'pct')} · **NIM** {_fmt(row.get('nim'), 'pct')} · **CIR** {_fmt(row.get('cir'), 'pct')}",
                f"**Loan growth 3y** {_fmt(row.get('loan_growth_3y'), 'pct')} · **NPL** {_fmt(row.get('npl'), 'pct')}",
                f"**P/B** {_fmt(row.get('pb'), 'mult')} · **Div yield** {_fmt(row.get('dividend_yield'), 'pct')}",
            ]
        else:
            lines = [
                f"**ROE** {_fmt(row.get('roe'), 'pct')} · **ROIC** {_fmt(row.get('roic'), 'pct')} · **EBITDA margin** {_fmt(row.get('ebitda_margin'), 'pct')}",
                f"**Revenue CAGR 3y** {_fmt(row.get('revenue_cagr_3y'), 'pct')} · **FCF yield** {_fmt(row.get('fcf_yield'), 'pct')}",
                f"**P/E** {_fmt(row.get('pe'), 'mult')} · **P/B** {_fmt(row.get('pb'), 'mult')}",
            ]
        for line in lines:
            st.markdown(line)

        st.plotly_chart(_score_breakdown_chart(row, scorecard, method), use_container_width=True)

        if st.button("🌏 View global peers", key=f"peers:{row['ticker']}", use_container_width=True):
            on_view_peers(row["ticker"])


# ---------------------------------------------------------------------------
def render(df: pd.DataFrame, on_view_peers) -> None:
    st.markdown("### Top performers — deep dive")
    if df is None or df.empty:
        st.info("No data loaded yet.")
        return

    method = st.session_state.get("method_select", "rank")
    bank_weights = get_active_weights("banks")
    nonfin_weights = get_active_weights("non_financials")

    banks_scored = apply_scoring(df, bank_weights, "banks", method=method)
    nonfin_scored = apply_scoring(df, nonfin_weights, "non_financials", method=method)

    # Filter top performers
    top_banks = banks_scored.dropna(subset=["composite_rank"]).head(5)
    top_nonfin = nonfin_scored.dropna(subset=["composite_rank"]).head(8)

    st.markdown("#### Top 5 banks")
    cols = st.columns(3)
    for i, (_, row) in enumerate(top_banks.iterrows()):
        with cols[i % 3]:
            _render_card(row, "banks", method, on_view_peers)

    st.markdown("#### Top 8 non-financials")
    cols = st.columns(3)
    for i, (_, row) in enumerate(top_nonfin.iterrows()):
        with cols[i % 3]:
            _render_card(row, "non_financials", method, on_view_peers)
