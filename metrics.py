"""
metrics.py
==========
Pure functions that turn raw statement series into ratios.

Each helper accepts the *most-recent-first* convention used by data_pipeline:
- series[0] = latest reported year (t)
- series[1] = t-1
- series[2] = t-2
- series[3] = t-3   (needed for 3-year CAGR)

All helpers return `numpy.nan` when inputs are missing or invalid; callers
should treat NaN as "metric not computable for this row".

Convention notes baked into the formulas
----------------------------------------
- ROE: net_income_ttm / average equity (begin + end) / 2
- ROIC: NOPAT / average invested capital, where
      NOPAT = operating_income × (1 - effective tax rate)
      invested capital = total_debt + total_equity - cash
  This is the "operating ROIC" convention. Other conventions exist
  (e.g. invested capital excluding goodwill); choice documented in README.
- EBITDA margin: (operating_income + D&A) / revenue
  When D&A is unavailable we fall back to operating_margin and the caller
  flags `tags += ["da_missing"]`.
- FCF yield: (operating_cf - capex) / market_cap, where market_cap is in
  the same units as operating_cf (VND billions).
- 3-year CAGR: (X_t / X_{t-3}) ^ (1/3) - 1, undefined if either endpoint is
  zero or negative.
"""

from __future__ import annotations
from typing import List, Optional, Sequence
import math

import numpy as np


def _first(series: Sequence[Optional[float]]) -> Optional[float]:
    """Return the first non-None entry."""
    for v in series:
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            return float(v)
    return None


def _avg2(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Average two values, treating None as missing. Both required."""
    if a is None or b is None:
        return None
    return (a + b) / 2.0


# ---------------------------------------------------------------------------
def cagr_3y(series: Sequence[Optional[float]]) -> float:
    """3-year CAGR with edge cases. Series ordered most-recent first."""
    if not series or len(series) < 4:
        return np.nan
    a, _, _, b = series[0], series[1], series[2], series[3]
    if a is None or b is None:
        return np.nan
    if a <= 0 or b <= 0:
        return np.nan
    try:
        return (a / b) ** (1.0 / 3.0) - 1.0
    except (ZeroDivisionError, ValueError):
        return np.nan


# ---------------------------------------------------------------------------
def roe_avg(net_income: Sequence[Optional[float]],
            equity: Sequence[Optional[float]]) -> float:
    """ROE = NI_t / avg(equity_t, equity_{t-1}). NaN if equity ≤ 0."""
    ni = _first(net_income)
    if ni is None:
        return np.nan
    if not equity or len(equity) < 2:
        eq_avg = _first(equity)
    else:
        eq_avg = _avg2(equity[0], equity[1])
    if eq_avg is None or eq_avg <= 0:
        return np.nan
    return ni / eq_avg


# ---------------------------------------------------------------------------
def roic(op_income: Sequence[Optional[float]],
         tax_expense: Sequence[Optional[float]],
         total_debt: Sequence[Optional[float]],
         equity: Sequence[Optional[float]],
         cash: Sequence[Optional[float]]) -> float:
    """Operating ROIC = NOPAT / avg invested capital.

    Effective tax rate ≈ tax_expense / (op_income) clipped to [0, 0.4].
    """
    op = _first(op_income)
    if op is None or op <= 0:
        return np.nan
    tax = _first(tax_expense)
    if tax is None or op == 0:
        eff_t = 0.20  # flat fallback (Vietnamese statutory CIT)
    else:
        eff_t = max(0.0, min(0.40, abs(tax) / abs(op)))
    nopat = op * (1.0 - eff_t)

    debt_t = _first(total_debt) or 0.0
    equity_t = _first(equity) or 0.0
    cash_t = _first(cash) or 0.0
    invested_t = debt_t + equity_t - cash_t

    debt_t1 = (total_debt[1] if len(total_debt) > 1 and total_debt[1] is not None else debt_t)
    equity_t1 = (equity[1] if len(equity) > 1 and equity[1] is not None else equity_t)
    cash_t1 = (cash[1] if len(cash) > 1 and cash[1] is not None else cash_t)
    invested_t1 = debt_t1 + equity_t1 - cash_t1

    inv_avg = (invested_t + invested_t1) / 2.0
    if inv_avg <= 0:
        return np.nan
    return nopat / inv_avg


# ---------------------------------------------------------------------------
def ebitda_margin(op_income: Sequence[Optional[float]],
                  da: Sequence[Optional[float]],
                  revenue: Sequence[Optional[float]]) -> float:
    rev = _first(revenue)
    op = _first(op_income)
    if rev is None or rev <= 0 or op is None:
        return np.nan
    da_t = _first(da)
    if da_t is None:
        # Fall back to operating margin (caller responsible for flagging).
        return op / rev
    return (op + abs(da_t)) / rev


# ---------------------------------------------------------------------------
def fcf_yield(op_cf: Sequence[Optional[float]],
              capex: Sequence[Optional[float]],
              market_cap: Optional[float]) -> float:
    if market_cap is None or market_cap <= 0:
        return np.nan
    ocf = _first(op_cf)
    if ocf is None:
        return np.nan
    cx = _first(capex)
    if cx is None:
        # Fall back to op-CF yield (no FCF possible without capex).
        return ocf / market_cap
    fcf = ocf - abs(cx)
    return fcf / market_cap


# ---------------------------------------------------------------------------
def pe_ratio(market_cap: Optional[float],
             net_income: Sequence[Optional[float]]) -> float:
    ni = _first(net_income)
    if market_cap is None or ni is None or ni <= 0:
        return np.nan
    return market_cap / ni


# ---------------------------------------------------------------------------
def pb_ratio(market_cap: Optional[float],
             equity: Sequence[Optional[float]]) -> float:
    eq = _first(equity)
    if market_cap is None or eq is None or eq <= 0:
        return np.nan
    return market_cap / eq


# ---------------------------------------------------------------------------
def nim(nii: Sequence[Optional[float]],
        earning_assets: Sequence[Optional[float]]) -> float:
    n = _first(nii)
    a = _first(earning_assets)
    if n is None or a is None or a <= 0:
        return np.nan
    return n / a


# ---------------------------------------------------------------------------
def cost_to_income(op_expenses: Sequence[Optional[float]],
                   op_revenue: Sequence[Optional[float]]) -> float:
    e = _first(op_expenses)
    r = _first(op_revenue)
    if e is None or r is None or r <= 0:
        return np.nan
    return abs(e) / r
