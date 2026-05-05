"""
weight_panel.py
===============
Sidebar UI that lets the user override default composite weights for the
currently-selected scorecard.

Behavior contract (matches Part 3 of the spec)
----------------------------------------------
- One slider per metric, range 0..MAX (default DEFAULT_WEIGHT[metric]).
- A live "Total weight: X%" badge — green if ~100%, red otherwise.
- Buttons: "Auto-normalize", "Reset to defaults".
- Weights are NORMALIZED to sum=1 inside scoring; the panel just shows raw values.
- Custom weights live in `st.session_state["weights:<scorecard>"]`. They reset
  on full page reload (intentional).
- Scoring isn't recomputed live; the user clicks "Recompute scores" in the
  main bar.
- Guard-rails: per-metric max = WEIGHT_MAX; if user sets ALL weights to 0,
  the recompute button is disabled by the caller.
"""

from __future__ import annotations
from typing import Dict, Tuple

import streamlit as st

from config import (
    DEFAULT_WEIGHTS_BANKS,
    DEFAULT_WEIGHTS_NON_FINANCIALS,
    METRIC_LABELS,
    WEIGHT_MAX,
    WEIGHT_MIN,
    WEIGHT_TOTAL_TOL,
)


def _default_weights_for(scorecard: str) -> Dict[str, float]:
    return dict(DEFAULT_WEIGHTS_BANKS) if scorecard == "banks" else dict(DEFAULT_WEIGHTS_NON_FINANCIALS)


def _state_key(scorecard: str) -> str:
    return f"weights:{scorecard}"


def get_active_weights(scorecard: str) -> Dict[str, float]:
    """Return the current (possibly customized) weights for `scorecard`.
    Initializes session-state with the defaults on first call."""
    key = _state_key(scorecard)
    if key not in st.session_state:
        st.session_state[key] = _default_weights_for(scorecard)
    return dict(st.session_state[key])


def is_default(scorecard: str) -> bool:
    active = get_active_weights(scorecard)
    default = _default_weights_for(scorecard)
    return all(abs(active.get(k, 0) - default.get(k, 0)) < 1e-6 for k in default)


def render_weight_panel(scorecard: str) -> Tuple[Dict[str, float], bool]:
    """Render sliders + buttons in the sidebar; return (weights, can_score).

    `can_score` is False when total weight is zero (caller disables recompute).
    """
    key = _state_key(scorecard)
    if key not in st.session_state:
        st.session_state[key] = _default_weights_for(scorecard)

    defaults = _default_weights_for(scorecard)

    with st.sidebar.expander("⚖️ Composite weights", expanded=True):
        st.caption(
            f"Adjust weights for the **{scorecard.replace('_', '-')}** scorecard. "
            "Weights normalize to 100% before scoring. "
            "Customizations apply for this session only and reset on page reload."
        )
        new_weights: Dict[str, float] = {}
        for metric in defaults.keys():
            label = METRIC_LABELS.get(metric, metric)
            current = float(st.session_state[key].get(metric, defaults[metric]))
            slider_help = None
            if current >= WEIGHT_MAX - 1e-9:
                slider_help = (
                    "60% cap: keeps the composite multi-factor. "
                    "Zero-out other metrics if you want this one to dominate."
                )
            new_weights[metric] = st.slider(
                label,
                min_value=float(WEIGHT_MIN),
                max_value=float(WEIGHT_MAX),
                value=current,
                step=0.01,
                format="%.2f",
                key=f"slider:{scorecard}:{metric}",
                help=slider_help,
            )
        st.session_state[key] = new_weights

        total = sum(new_weights.values())
        is_full = abs(total - 1.0) < WEIGHT_TOTAL_TOL
        color = "#16a34a" if is_full else ("#dc2626" if total <= 0 else "#d97706")
        st.markdown(
            f"<div style='font-weight:600; color:{color};'>"
            f"Total weight: {total*100:.1f}%</div>",
            unsafe_allow_html=True,
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Auto-normalize", key=f"normalize:{scorecard}",
                         use_container_width=True):
                if total > 0:
                    st.session_state[key] = {k: v / total for k, v in new_weights.items()}
                    st.rerun()
        with col_b:
            if st.button("Reset to defaults", key=f"reset:{scorecard}",
                         use_container_width=True):
                st.session_state[key] = _default_weights_for(scorecard)
                st.rerun()

    can_score = total > 0
    if not can_score:
        st.sidebar.warning("All weights are 0 — composite cannot be computed.")
    return st.session_state[key], can_score
