"""
ui_screener.py
==============
Tab 1 — primary screener view.

Renders:
- Top toolbar: scorecard toggle, scoring-method toggle, refresh, weight-set label
- Sidebar filters: sub-sector, market-cap range, completeness gate, thin-float toggle
- Main table: ranked composite output with color-coded cells + tags
- Sub-sector heatmap (avg composite rank by sub-sector)
- Methodology box (collapsible)
- Diagnostic panel (sidebar)
"""

from __future__ import annotations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

from config import (
    DEFAULT_WEIGHTS_BANKS,
    DEFAULT_WEIGHTS_NON_FINANCIALS,
    METRIC_FORMAT,
    METRIC_LABELS,
    FLAGGED_TICKERS,
    THIN_FLOAT_THRESHOLD,
)
from scoring import apply_scoring
from weight_panel import get_active_weights, is_default, render_weight_panel


# ---------------------------------------------------------------------------
def _fmt_metric(value: Optional[float], fmt: str) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    if fmt == "pct":
        return f"{value*100:.1f}%"
    return f"{value:.1f}"


def _format_table(scored: pd.DataFrame, scorecard: str) -> pd.DataFrame:
    """Convert raw numeric metrics into display strings + ordered columns."""
    if scorecard == "banks":
        metric_cols = list(DEFAULT_WEIGHTS_BANKS.keys())
    else:
        metric_cols = list(DEFAULT_WEIGHTS_NON_FINANCIALS.keys())

    out = pd.DataFrame()
    out["#"] = scored["composite_rank"].apply(
        lambda v: int(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else "—"
    )
    out["Ticker"] = scored["ticker"]
    out["Name"] = scored["name"]
    out["Sub-sector"] = scored["sub_sector"]
    out["Mkt cap (VND B)"] = scored["market_cap_vnd_b"].apply(
        lambda v: f"{v:,.0f}" if v is not None and not (isinstance(v, float) and np.isnan(v)) else "—"
    )
    out["Free float"] = scored.apply(
        lambda r: f"{r['free_float']*100:.0f}%" + (" 🚩" if r["free_float"] < THIN_FLOAT_THRESHOLD else ""),
        axis=1,
    )
    for m in metric_cols:
        out[METRIC_LABELS.get(m, m)] = scored[m].apply(lambda v, fmt=METRIC_FORMAT.get(m, "mult"): _fmt_metric(v, fmt))

    out["Composite"] = scored["composite_score"].apply(
        lambda v: f"{v:.2f}" if v is not None and not (isinstance(v, float) and np.isnan(v)) else "—"
    )
    out["Completeness"] = scored["data_completeness"].apply(lambda v: f"{v*100:.0f}%")
    out["Tags"] = scored["tags"].apply(lambda lst: ", ".join(lst) if isinstance(lst, list) else "")
    return out


def _style_metric_columns(styler, scored: pd.DataFrame, scorecard: str):
    """Apply diverging green->red colormap on numeric metric columns."""
    if scorecard == "banks":
        numeric_metrics = list(DEFAULT_WEIGHTS_BANKS.keys())
    else:
        numeric_metrics = list(DEFAULT_WEIGHTS_NON_FINANCIALS.keys())

    # We applied formatting to strings already; can't colormap on strings,
    # so we color by quantile of the underlying numeric series instead.
    for m in numeric_metrics:
        col_label = METRIC_LABELS.get(m, m)
        if col_label not in styler.columns:
            continue
        series = scored[m].astype(float)
        if series.dropna().empty:
            continue
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        # Direction: lower-is-better metrics flip green/red.
        lower_better = m in {"pe", "pb", "cir", "npl"}

        def _color(val_str, q1=q1, q3=q3, lower_better=lower_better):
            try:
                if val_str.endswith("%"):
                    val = float(val_str.replace("%", "")) / 100.0
                elif val_str == "—":
                    return ""
                else:
                    val = float(val_str)
            except Exception:
                return ""
            if lower_better:
                if val <= q1:
                    return "background-color:#dcfce7;color:#166534;"
                if val >= q3:
                    return "background-color:#fee2e2;color:#991b1b;"
            else:
                if val >= q3:
                    return "background-color:#dcfce7;color:#166534;"
                if val <= q1:
                    return "background-color:#fee2e2;color:#991b1b;"
            return ""
        styler = styler.map(_color, subset=[col_label])
    return styler


# ---------------------------------------------------------------------------
def render(df: pd.DataFrame, on_refresh) -> None:
    st.markdown("### VN30 Screener")
    if df is None or df.empty:
        st.warning("No data loaded yet. Click **Refresh data** to fetch from vnstock.")
        if st.button("Refresh data", type="primary"):
            on_refresh()
        return

    # ---- Top bar ----
    c1, c2, c3, c4 = st.columns([1.5, 1.5, 1, 2])
    with c1:
        scorecard = st.radio(
            "Scorecard",
            options=["non_financials", "banks"],
            format_func=lambda v: "Non-financials (16)" if v == "non_financials" else "Banks (14)",
            horizontal=True,
            key="scorecard_select",
        )
    with c2:
        method = st.radio(
            "Scoring method",
            options=["rank", "zscore"],
            format_func=lambda v: "Rank-based" if v == "rank" else "Z-score",
            horizontal=True,
            key="method_select",
        )
    with c3:
        if st.button("🔄 Refresh data", use_container_width=True):
            on_refresh()
    with c4:
        st.caption("Data source: vnstock (VCI primary, TCBS fallback). Cache 24h.")

    # ---- Sidebar: weight panel + filters + diagnostics ----
    weights, can_score = render_weight_panel(scorecard)
    using_default = is_default(scorecard)
    weight_label = "default weights" if using_default else "custom weights — see sidebar"
    st.markdown(
        f"<div style='padding:6px 10px; background:#eef2ff; border-radius:6px; font-size:0.9em;'>"
        f"Scoring with: <b>{weight_label}</b></div>",
        unsafe_allow_html=True,
    )

    # Sidebar filters
    with st.sidebar.expander("🔎 Filters", expanded=True):
        scoped = df[df["scorecard"] == scorecard]
        sub_sectors = sorted(scoped["sub_sector"].dropna().unique().tolist())
        sel_subs = st.multiselect("Sub-sector", sub_sectors, default=sub_sectors, key=f"subs:{scorecard}")
        if scoped["market_cap_vnd_b"].dropna().empty:
            mc_min, mc_max = 0.0, 1e6
        else:
            mc_min = float(scoped["market_cap_vnd_b"].min(skipna=True) or 0)
            mc_max = float(scoped["market_cap_vnd_b"].max(skipna=True) or 1)
        mc_range = st.slider(
            "Market cap (VND B)",
            min_value=0.0, max_value=max(mc_max, 1.0),
            value=(0.0, max(mc_max, 1.0)),
            key=f"mcap:{scorecard}",
        )
        hide_low = st.checkbox("Hide rows with >2 N/A metrics", value=False, key=f"hidena:{scorecard}")
        hide_thin = st.checkbox("Hide thin-float names (FF < 20%)", value=False, key=f"hideff:{scorecard}")

    # ---- Compute scoring ----
    if not can_score:
        st.error("All weights are zero — cannot compute composite. Adjust sliders in the sidebar.")
        return
    scored = apply_scoring(df, weights, scorecard, method=method)

    # Apply filters
    scored = scored[scored["sub_sector"].isin(sel_subs)]
    scored = scored[
        (scored["market_cap_vnd_b"].fillna(0) >= mc_range[0])
        & (scored["market_cap_vnd_b"].fillna(0) <= mc_range[1])
    ]
    if hide_low:
        scored = scored[scored["data_completeness"] >= 0.7]
    if hide_thin:
        scored = scored[scored["free_float"] >= THIN_FLOAT_THRESHOLD]

    # ---- Render main table ----
    table = _format_table(scored, scorecard)
    styler = table.style
    styler = _style_metric_columns(styler, scored, scorecard)
    st.dataframe(styler, use_container_width=True, height=600, hide_index=True)

    # ---- Sub-sector heatmap ----
    st.markdown("#### Average composite rank by sub-sector")
    if not scored.empty:
        agg = (
            scored.dropna(subset=["composite_rank"])
            .groupby("sub_sector")["composite_rank"]
            .mean()
            .sort_values()
            .round(2)
        )
        if not agg.empty:
            heat = agg.to_frame(name="Avg rank")
            st.dataframe(heat.style.background_gradient(cmap="RdYlGn_r"), use_container_width=True)

    # ---- Methodology box ----
    with st.expander("📐 Methodology", expanded=False):
        st.markdown(_methodology_md(scorecard, weights, method))

    # ---- Diagnostic panel ----
    from data_pipeline import latest_diagnostic
    diag = latest_diagnostic()
    with st.sidebar.expander("🩺 Diagnostics", expanded=False):
        st.write(f"Last build: {diag.timestamp.strftime('%Y-%m-%d %H:%M UTC')}")
        if diag.ticker_failures:
            st.write("**Fetch failures:**")
            for t, msg in diag.ticker_failures.items():
                st.caption(f"• {t}: {msg}")
        else:
            st.caption("No fetch failures.")
        if diag.low_completeness:
            st.write("**Low completeness:** " + ", ".join(diag.low_completeness))
        if diag.validation_warnings:
            st.write("**Validation warnings:**")
            for w in diag.validation_warnings:
                st.caption(f"• {w}")


# ---------------------------------------------------------------------------
def _methodology_md(scorecard: str, weights: Dict[str, float], method: str) -> str:
    if scorecard == "banks":
        defaults = DEFAULT_WEIGHTS_BANKS
        rationale = (
            "**Banks rationale.** ROE is the cleanest single signal of franchise quality — "
            "highest single-metric weight. Asset quality (NPL) gets explicit pillar weight "
            "because a high-growth bank with bad loans destroys value faster than a moderate-"
            "growth bank with clean loans. P/B is the primary bank valuation multiple "
            "(P/E is distorted by provisions). Dividend yield small because Vietnamese "
            "banks pay irregularly."
        )
    else:
        defaults = DEFAULT_WEIGHTS_NON_FINANCIALS
        rationale = (
            "**Non-financials rationale.** Quality and value weighted equally because either "
            "alone is incomplete (quality without price = beauty contest; value without quality "
            "= value trap). Growth weighted moderately because Vietnamese mid-cap growth is noisy. "
            "Profitability split into three lenses (shareholder returns, capital efficiency, operating "
            "leverage) to avoid double-counting via correlated metrics. ROA omitted to avoid "
            "collinearity with ROE."
        )

    rows = []
    for k, w in defaults.items():
        rows.append(f"| {METRIC_LABELS.get(k, k)} | {w*100:.0f}% | {weights.get(k, 0)*100:.1f}% |")
    table = "| Metric | Default | Active |\n|---|---|---|\n" + "\n".join(rows)

    method_md = ("**Rank-based** (default): each metric ranks 1..N within scorecard; weighted sum; "
                 "lower composite = better. **Missing values get the median rank** to avoid "
                 "double-penalising N/A. Lower-is-better metrics (P/E, P/B, CIR, NPL) ranked ascending."
                 if method == "rank"
                 else "**Z-score**: per-metric z = (value − mean) / σ, winsorized 5/95th. "
                 "Sign flipped for lower-is-better metrics. Missing → z = 0 (cohort mean).")

    flagged = ", ".join(f"{k} ({v})" for k, v in FLAGGED_TICKERS.items())

    return (
        f"#### Scoring method\n{method_md}\n\n"
        f"#### Active weights ({scorecard})\n{table}\n\n"
        f"{rationale}\n\n"
        f"#### Cohort & ranking rules\n"
        f"- Companies are ranked **only against others in their scorecard** (banks vs banks; non-financials vs non-financials). "
        f"Cross-scorecard comparisons are not valid and not displayed.\n"
        f"- Companies with `data_completeness < 50%` are kept in the table but excluded from the composite ranking "
        f"(rank = N/A) with a `incomplete_data` tag.\n"
        f"- Thin-float names (free float < 20%) are flagged because their multiples may not reflect true supply/demand.\n\n"
        f"#### Flagged names\n{flagged or '(none)'}\n\n"
        f"**Real estate developers** (VHM, VIC, VRE) are flagged for project-cycle volatility "
        f"that distorts EBITDA margin and FCF yield YoY.\n\n"
        f"#### Data sources\n"
        f"Vietnamese fundamentals: `vnstock` (VCI primary, TCBS fallback), 24h cache. "
        f"Global peers: `yfinance` with USD normalization (24h cache). "
        f"FX rates: yfinance pairs with hard-coded fallback in `config.py`."
    )
