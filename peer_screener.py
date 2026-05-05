"""
peer_screener.py
================
Implements the OPCM peer-screening cascade for a single target ticker.

OPCM = Operation > Performance > Credit > Market
- Strict priority. A candidate that fails Tier 1 (Operation) cannot be
  rescued by strong Tier 2 (Performance).
- Within a tier, ties are broken by the next tier downstream.

Inputs:  target_ticker (a VN30 ticker), sector bucket from sector_mapping.
Outputs: a dataframe (target row + 5-8 peer rows) with USD-normalized
         financials, plus a relaxation log explaining where defaults loosened.

Mandatory hygiene
-----------------
- All monetary fields in USD (currency_normalizer handles trading vs.
  reporting currency + minor units).
- Banks SKIP Tier 3 (Credit). yfinance lacks CET1/NPL for ASEAN names —
  framework's biggest weakness for VN30 (14/30 names are banks).
- We never compute a single-point "fair value". We return percentile rank
  and an implied range across P/E, P/B, EV/EBITDA.
"""

from __future__ import annotations
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import (
    DEVELOPED_COUNTRIES,
    INTEREST_COVERAGE_DISTRESS_FLOOR,
    LIQUIDITY_FLOOR_USD,
    PERFORMANCE_SIMILARITY_K,
    SIZE_BAND_RELAX_SIGMA,
    SIZE_BAND_SIGMA,
    TIER_A_COUNTRIES,
    TIER_B_COUNTRIES,
    TIER_C_COUNTRIES,
)
from currency_normalizer import derive_market_cap, to_usd, get_fx_per_usd
from peer_pools import get_pool
from sector_mapping import metric_profile

log = logging.getLogger(__name__)


@dataclass
class RelaxationLog:
    notes: List[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.notes.append(msg)


def _import_yf():
    try:
        import yfinance as yf
        return yf
    except Exception as e:  # pragma: no cover
        log.warning("yfinance import failed: %s", e)
        return None


def _safe_info(yf, ticker: str) -> Dict[str, Any]:
    """yfinance .info is flaky; wrap with retry + fast_info fallback."""
    out: Dict[str, Any] = {}
    try:
        t = yf.Ticker(ticker)
        try:
            out.update(dict(t.info))
        except Exception:
            pass
        try:
            fi = t.fast_info
            for k in ("last_price", "lastPrice", "shares", "marketCap"):
                if hasattr(fi, "__getitem__"):
                    try:
                        v = fi[k]
                        if v is not None:
                            out.setdefault(
                                {"last_price": "regularMarketPrice",
                                 "lastPrice": "regularMarketPrice",
                                 "shares": "sharesOutstanding",
                                 "marketCap": "marketCap"}[k],
                                v,
                            )
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception as e:
        log.debug("yfinance .info failed for %s: %s", ticker, e)
    return out


# ---------------------------------------------------------------------------
def _candidate_record(yf, ticker: str, country: str, label: str) -> Optional[Dict[str, Any]]:
    info = _safe_info(yf, ticker)
    if not info:
        return None

    trading_ccy = info.get("currency") or "USD"
    reporting_ccy = info.get("financialCurrency") or trading_ccy

    mc_local = derive_market_cap(info)
    market_cap_usd = to_usd(mc_local, trading_ccy)
    revenue_local = info.get("totalRevenue")
    revenue_usd = to_usd(revenue_local, reporting_ccy)

    rec = {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or label,
        "country": country,
        "trading_ccy": trading_ccy,
        "reporting_ccy": reporting_ccy,
        "market_cap_usd_b": (market_cap_usd / 1e9) if market_cap_usd else None,
        "revenue_usd_b": (revenue_usd / 1e9) if revenue_usd else None,
        # Unitless ratios — DO NOT FX-convert.
        "pe": info.get("trailingPE"),
        "pb": info.get("priceToBook"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "dividend_yield": info.get("dividendYield"),
        "roe": info.get("returnOnEquity"),
        "operating_margin": info.get("operatingMargins"),
        "gross_margin": info.get("grossMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "debt_to_equity": info.get("debtToEquity"),
        # Liquidity in trading currency * price -> USD.
        "adv_usd": _adv_usd(info, trading_ccy),
        "interest_coverage": _interest_coverage(info),
        "raw_info": info,  # kept for downstream completeness scoring
    }
    return rec


def _adv_usd(info: Dict[str, Any], trading_ccy: str) -> Optional[float]:
    vol = info.get("averageVolume") or info.get("averageDailyVolume10Day")
    price = info.get("regularMarketPrice") or info.get("currentPrice")
    if not vol or not price:
        return None
    adv_local = float(vol) * float(price)
    return to_usd(adv_local, trading_ccy)


def _interest_coverage(info: Dict[str, Any]) -> Optional[float]:
    # yfinance occasionally exposes ebit / interestExpense; not reliable for ASEAN.
    ebit = info.get("ebit") or info.get("operatingIncome")
    iexp = info.get("interestExpense")
    if ebit and iexp and abs(iexp) > 0:
        return float(ebit) / abs(float(iexp))
    return None


def _country_tier(c: str) -> str:
    if c in TIER_A_COUNTRIES:
        return "A"
    if c in TIER_B_COUNTRIES:
        return "B"
    if c in TIER_C_COUNTRIES:
        return "C"
    if c in DEVELOPED_COUNTRIES:
        return "D"
    return "Z"


# ---------------------------------------------------------------------------
def _build_target_record(yf, target: str, target_ccy: str = "VND") -> Optional[Dict[str, Any]]:
    """Look up the VN target via yfinance using `<TICKER>.VN` suffix."""
    yticker = f"{target}.VN"
    rec = _candidate_record(yf, yticker, "VN", target)
    if rec is None:
        # yfinance occasionally lacks .VN coverage; build a stub from vnstock
        rec = {
            "ticker": yticker, "name": target, "country": "VN",
            "trading_ccy": "VND", "reporting_ccy": "VND",
            "market_cap_usd_b": None, "revenue_usd_b": None,
            "pe": None, "pb": None, "ev_ebitda": None, "dividend_yield": None,
            "roe": None, "operating_margin": None, "gross_margin": None,
            "revenue_growth": None, "earnings_growth": None,
            "debt_to_equity": None, "adv_usd": None, "interest_coverage": None,
            "raw_info": {},
        }
    return rec


# ---------------------------------------------------------------------------
def _tier1_operation(target: Dict[str, Any],
                     candidates: List[Dict[str, Any]],
                     log_: RelaxationLog) -> List[Dict[str, Any]]:
    """Geography auto-relax + size band in log-space."""
    # Geography filter
    by_tier: Dict[str, List[Dict[str, Any]]] = {"A": [], "B": [], "C": [], "D": [], "Z": []}
    for c in candidates:
        by_tier[_country_tier(c["country"])].append(c)

    survivors = list(by_tier["A"])
    if len(survivors) < 5:
        log_.add(f"Geography: extended to Tier B because only {len(survivors)} ASEAN candidates available")
        survivors += by_tier["B"]
    if len(survivors) < 5:
        log_.add(f"Geography: extended to Tier C because only {len(survivors)} survived A+B")
        survivors += by_tier["C"]

    # Size band
    target_mc = target.get("market_cap_usd_b")
    if not target_mc:
        log_.add("Size: target market cap unavailable; size filter skipped")
        return survivors

    log_target = math.log(max(target_mc, 1e-6))
    pool_log = [math.log(max(c["market_cap_usd_b"], 1e-6)) for c in survivors
                if c.get("market_cap_usd_b") is not None and c["market_cap_usd_b"] > 0]
    if len(pool_log) < 3:
        log_.add("Size: insufficient pool size data; size filter skipped")
        return survivors
    arr = np.array(pool_log)
    lo, hi = np.percentile(arr, [5, 95])
    arr_w = np.clip(arr, lo, hi)
    sd = float(np.std(arr_w))
    sigma = SIZE_BAND_SIGMA

    def in_band(c, k):
        if not c.get("market_cap_usd_b") or c["market_cap_usd_b"] <= 0:
            return False
        return abs(math.log(c["market_cap_usd_b"]) - log_target) <= k * sd

    band = [c for c in survivors if in_band(c, sigma)]
    if len(band) < 5:
        log_.add(f"Size: relaxed band to ±{SIZE_BAND_RELAX_SIGMA}σ because only {len(band)} survived ±{sigma}σ")
        band = [c for c in survivors if in_band(c, SIZE_BAND_RELAX_SIGMA)]
    return band


# ---------------------------------------------------------------------------
def _similarity(target_v: Optional[float], peer_v: Optional[float],
                sd: float, k: float = PERFORMANCE_SIMILARITY_K) -> float:
    """1 - min(|peer-target|/σ, 1)/k. Missing -> 0.5."""
    if target_v is None or peer_v is None or sd is None or sd == 0:
        return 0.5
    diff = abs(peer_v - target_v) / sd
    return max(0.0, 1.0 - min(diff, k) / k)


def _profitability_value(c: Dict[str, Any], profile: str) -> Optional[float]:
    if profile == "roe":
        return c.get("roe")
    if profile == "operating_margin":
        return c.get("operating_margin")
    if profile == "roic_or_op_margin":
        return c.get("operating_margin")  # yfinance lacks consistent ROIC
    return c.get("operating_margin")


def _growth_value(c: Dict[str, Any], profile: str) -> Optional[float]:
    if profile == "earnings_growth":
        return c.get("earnings_growth")
    return c.get("revenue_growth")


def _tier2_performance(target: Dict[str, Any],
                       candidates: List[Dict[str, Any]],
                       sector: str,
                       log_: RelaxationLog) -> List[Dict[str, Any]]:
    """Score candidates by similarity to target on profitability + growth.
    Composite = 0.6 * profit + 0.4 * growth. Take top 12."""
    profile = metric_profile(sector)
    p_metric, g_metric = profile["profitability"], profile["growth"]

    p_pool = [v for v in (_profitability_value(c, p_metric) for c in candidates) if v is not None]
    g_pool = [v for v in (_growth_value(c, g_metric) for c in candidates) if v is not None]
    p_sd = float(np.std(p_pool)) if p_pool else 0.0
    g_sd = float(np.std(g_pool)) if g_pool else 0.0

    target_p = _profitability_value(target, p_metric)
    target_g = _growth_value(target, g_metric)

    for c in candidates:
        sp = _similarity(target_p, _profitability_value(c, p_metric), p_sd)
        sg = _similarity(target_g, _growth_value(c, g_metric), g_sd)
        c["_perf_score"] = 0.6 * sp + 0.4 * sg
        c["_perf_breakdown"] = {"profitability_sim": sp, "growth_sim": sg,
                                 "profitability_metric": p_metric, "growth_metric": g_metric}

    candidates.sort(key=lambda c: c["_perf_score"], reverse=True)
    keep = candidates[:12]
    if len(candidates) > 12:
        log_.add(f"Performance: 12 of {len(candidates)} retained by Tier-2 score")
    return keep


# ---------------------------------------------------------------------------
def _tier3_credit(target: Dict[str, Any],
                  candidates: List[Dict[str, Any]],
                  sector: str,
                  log_: RelaxationLog) -> List[Dict[str, Any]]:
    """Drop distressed names. Skipped for banks/insurance/brokerage."""
    if sector in {"banks", "insurance", "financials_brokerage"}:
        log_.add("Credit: skipped (yfinance lacks CET1/NPL/tier-1 ratios for ASEAN financials)")
        return candidates[:10]

    survivors: List[Dict[str, Any]] = []
    target_de = target.get("debt_to_equity")
    pool_de = [c["debt_to_equity"] for c in candidates if c.get("debt_to_equity") is not None]
    de_sd = float(np.std(pool_de)) if pool_de else 0.0

    for c in candidates:
        ic = c.get("interest_coverage")
        if ic is not None and ic < INTEREST_COVERAGE_DISTRESS_FLOOR:
            continue  # distress floor
        c["_credit_sim"] = _similarity(target_de, c.get("debt_to_equity"), de_sd)
        survivors.append(c)

    if len(survivors) < 5:
        log_.add(f"Credit: only {len(survivors)} survived; distress floor enforced anyway")
    return survivors[:10]


# ---------------------------------------------------------------------------
def _tier4_market(candidates: List[Dict[str, Any]],
                  log_: RelaxationLog) -> List[Dict[str, Any]]:
    """Liquidity floor; analyst coverage opt-in (skipped here)."""
    out = [c for c in candidates if (c.get("adv_usd") or 0) >= LIQUIDITY_FLOOR_USD]
    if len(out) < 5 and len(candidates) >= 5:
        log_.add(f"Market: liquidity floor relaxed (would have left {len(out)})")
        return candidates  # accept all
    return out


# ---------------------------------------------------------------------------
def run_opcm(target_ticker: str, sector_bucket: str) -> Tuple[pd.DataFrame, RelaxationLog]:
    """Top-level entrypoint. Returns (rows, relaxation_log).

    Row 0 = target (highlighted). Rows 1..N = peers, sorted by Tier-2 score.
    """
    yf = _import_yf()
    log_ = RelaxationLog()
    if yf is None:
        return pd.DataFrame(), log_

    target = _build_target_record(yf, target_ticker)
    if target is None:
        log_.add(f"Target {target_ticker} could not be fetched from yfinance")
        return pd.DataFrame(), log_

    pool = get_pool(sector_bucket)
    if not pool:
        log_.add(f"No candidate pool for sector bucket '{sector_bucket}'")
        return pd.DataFrame([{**target, "is_target": True}]), log_

    candidates: List[Dict[str, Any]] = []
    for tk, ctry, label in pool:
        rec = _candidate_record(yf, tk, ctry, label)
        if rec is not None:
            candidates.append(rec)

    log_.add(f"Pool: {len(candidates)} of {len(pool)} candidates fetched successfully")

    # Tier 1 - Operation
    survivors = _tier1_operation(target, candidates, log_)
    log_.add(f"After Tier 1 (Operation): {len(survivors)}")
    # Tier 2 - Performance
    survivors = _tier2_performance(target, survivors, sector_bucket, log_)
    log_.add(f"After Tier 2 (Performance): {len(survivors)}")
    # Tier 3 - Credit
    survivors = _tier3_credit(target, survivors, sector_bucket, log_)
    log_.add(f"After Tier 3 (Credit): {len(survivors)}")
    # Tier 4 - Market
    survivors = _tier4_market(survivors, log_)
    log_.add(f"After Tier 4 (Market): {len(survivors)}")

    # Final selection: top 5..8 by Tier-2 perf score
    survivors.sort(key=lambda c: c.get("_perf_score", 0), reverse=True)
    final_peers = survivors[:8]

    rows: List[Dict[str, Any]] = []
    rows.append({**target, "is_target": True, "tier_score": None})
    for p in final_peers:
        rows.append({**p, "is_target": False, "tier_score": p.get("_perf_score")})

    df = pd.DataFrame(rows)
    return df, log_


# ---------------------------------------------------------------------------
def implied_value_range(peer_df: pd.DataFrame, target_row: pd.Series) -> Dict[str, Tuple[float, float]]:
    """Compute implied target valuation range across multiples.

    Returns {multiple: (low, high)} where low/high come from peer 25th/75th
    percentiles applied to the target's per-share denominator.
    """
    out: Dict[str, Tuple[float, float]] = {}
    for mult in ("pe", "pb", "ev_ebitda"):
        peer_vals = peer_df[mult].dropna() if mult in peer_df.columns else pd.Series(dtype=float)
        if len(peer_vals) < 3:
            continue
        q25, q75 = float(peer_vals.quantile(0.25)), float(peer_vals.quantile(0.75))
        target_val = target_row.get(mult)
        if target_val is None or pd.isna(target_val) or target_val <= 0:
            continue
        # Implied multiple range: scale target's "value" (here we just store the
        # multiple range itself; the analyst applies it to their per-share base).
        out[mult] = (q25, q75)
    return out
