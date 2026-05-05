"""
scoring.py
==========
Composite scoring engine.

Two methods exposed:
- `rank_composite`  : per-metric ordinal rank, weighted sum (LOWER = better).
- `zscore_composite`: per-metric winsorized z-score, weighted sum (HIGHER = better).

Important rules
---------------
- Companies with a missing (NaN) value on a metric receive the *median rank*
  (or z = 0) for that metric. This avoids double-penalising missing data
  ("N/A in cell + worst rank in composite"). Documented in the methodology box.
- For "lower is better" metrics (P/E, P/B, CIR, NPL) we INVERT direction:
  rank ascending instead of descending; z-score sign flipped.
- Weights normalize to sum=1.0 BEFORE scoring.
- Companies whose `data_completeness < 0.50` are excluded from the ranking
  (composite = NaN, rank = N/A) but kept in the output frame.
"""

from __future__ import annotations
from typing import Dict, Tuple
import numpy as np
import pandas as pd

from config import (
    DATA_COMPLETENESS_DROP_THRESHOLD,
    METRIC_DIRECTION_BANKS,
    METRIC_DIRECTION_NON_FINANCIALS,
)


def _direction_map(scorecard: str) -> Dict[str, str]:
    return METRIC_DIRECTION_BANKS if scorecard == "banks" else METRIC_DIRECTION_NON_FINANCIALS


def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """Scale weights so they sum to 1.0. Empty/zero -> identity dict."""
    total = sum(max(0.0, w) for w in weights.values())
    if total <= 0:
        return {k: 0.0 for k in weights}
    return {k: max(0.0, v) / total for k, v in weights.items()}


def _winsorize(series: pd.Series, lower: float = 0.05, upper: float = 0.95) -> pd.Series:
    if series.dropna().empty:
        return series
    lo = series.quantile(lower)
    hi = series.quantile(upper)
    return series.clip(lower=lo, upper=hi)


def rank_composite(df: pd.DataFrame,
                   weights: Dict[str, float],
                   scorecard: str) -> pd.DataFrame:
    """Compute per-metric rank, weighted composite score, and final rank.

    Returns the dataframe with added columns:
      - rank__<metric>   integer rank within scorecard
      - composite_score  weighted-sum of ranks (LOWER = better)
      - composite_rank   integer rank by composite_score (1 = best)
    Missing-data rows (data_completeness < threshold) get composite=NaN.
    """
    out = df.copy()
    direction = _direction_map(scorecard)
    weights = normalize_weights(weights)

    eligible_mask = out["data_completeness"] >= DATA_COMPLETENESS_DROP_THRESHOLD
    eligible = out[eligible_mask].copy()
    if eligible.empty:
        out["composite_score"] = np.nan
        out["composite_rank"] = np.nan
        return out

    composite = pd.Series(0.0, index=eligible.index)

    for metric, w in weights.items():
        if metric not in eligible.columns:
            continue
        col = eligible[metric].astype(float)
        # Median-rank fill for NaN
        ascending = direction.get(metric) == "low"  # lower-is-better -> ascending rank
        ranks = col.rank(method="average", ascending=ascending, na_option="keep")
        median_rank = ranks.median(skipna=True)
        if pd.isna(median_rank):
            median_rank = (len(eligible) + 1) / 2.0
        ranks = ranks.fillna(median_rank)
        out.loc[eligible.index, f"rank__{metric}"] = ranks
        composite = composite + w * ranks

    # Place composite back into the parent frame, NaN for ineligibles
    out.loc[eligible.index, "composite_score"] = composite
    out.loc[~eligible_mask, "composite_score"] = np.nan

    # Final rank: lower composite = better -> ascending
    out["composite_rank"] = out["composite_score"].rank(method="min", ascending=True, na_option="keep")
    return out


def zscore_composite(df: pd.DataFrame,
                     weights: Dict[str, float],
                     scorecard: str) -> pd.DataFrame:
    """Per-metric winsorized z-score, signed by direction; weighted sum is
    HIGHER-IS-BETTER. Missing values get z=0 (cohort mean)."""
    out = df.copy()
    direction = _direction_map(scorecard)
    weights = normalize_weights(weights)

    eligible_mask = out["data_completeness"] >= DATA_COMPLETENESS_DROP_THRESHOLD
    eligible = out[eligible_mask].copy()
    if eligible.empty:
        out["composite_score"] = np.nan
        out["composite_rank"] = np.nan
        return out

    composite = pd.Series(0.0, index=eligible.index)

    for metric, w in weights.items():
        if metric not in eligible.columns:
            continue
        col = _winsorize(eligible[metric].astype(float))
        mu, sd = col.mean(skipna=True), col.std(skipna=True, ddof=0)
        if not sd or pd.isna(sd) or sd == 0:
            z = pd.Series(0.0, index=col.index)
        else:
            z = (col - mu) / sd
        if direction.get(metric) == "low":
            z = -z  # higher z = better after sign-flip
        z = z.fillna(0.0)  # missing -> cohort mean
        out.loc[eligible.index, f"z__{metric}"] = z
        composite = composite + w * z

    out.loc[eligible.index, "composite_score"] = composite
    out.loc[~eligible_mask, "composite_score"] = np.nan
    # Higher z-score = better, so descending rank
    out["composite_rank"] = out["composite_score"].rank(method="min", ascending=False, na_option="keep")
    return out


def apply_scoring(df: pd.DataFrame,
                  weights: Dict[str, float],
                  scorecard: str,
                  method: str = "rank") -> pd.DataFrame:
    """Dispatch to the chosen method and split-by-scorecard."""
    sub = df[df["scorecard"] == scorecard].copy()
    if method == "zscore":
        scored = zscore_composite(sub, weights, scorecard)
    else:
        scored = rank_composite(sub, weights, scorecard)
    return scored.sort_values("composite_rank", na_position="last")
