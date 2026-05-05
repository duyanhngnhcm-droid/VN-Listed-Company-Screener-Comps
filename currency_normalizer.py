"""
currency_normalizer.py
======================
Convert values from local trading / reporting currencies to USD.

Three currency concepts to keep distinct
----------------------------------------
1. Trading currency (`info["currency"]`):
   what `marketCap`, price and volume are quoted in.
2. Reporting currency (`info["financialCurrency"]`):
   what revenue, EBITDA, debt, equity are reported in. Often DIFFERENT
   from trading currency (e.g. HK-listed Chinese firms trade HKD, report CNY).
3. Minor units: GBp / ZAc / ILA. These are 1/100 of the major (GBP/ZAR/ILS).
   yfinance returns London `.L` prices in PENCE - dividing by 100 BEFORE FX
   conversion is mandatory.

Unitless ratios (P/E, P/B, ROE, margins, growth rates) are NEVER converted.
"""

from __future__ import annotations
from typing import Dict, Optional, Tuple
from datetime import datetime
import logging

from config import (
    FX_FALLBACK_PER_USD,
    MINOR_UNIT_CURRENCIES,
    TTL_FX_S,
)

log = logging.getLogger(__name__)

# Module-level FX cache. Streamlit's st.cache_data also wraps the public
# helpers; this in-process dict gives a cheap second tier within a request.
_FX_CACHE: Dict[str, Tuple[float, datetime]] = {}
_FX_FETCH_TIMESTAMP: Optional[datetime] = None


def _normalize_currency_code(code: Optional[str]) -> str:
    """Strip whitespace, uppercase. Pass-through for minor-unit codes which
    need their case (GBp, ZAc, ILA) preserved."""
    if not code:
        return "USD"
    stripped = code.strip()
    # Case-insensitive check for minor units
    for mu in MINOR_UNIT_CURRENCIES:
        if stripped.lower() == mu.lower():
            return mu
    return stripped.upper()


def resolve_minor_unit(code: str) -> Tuple[str, float]:
    """If `code` is a minor unit (GBp etc.), return (major_code, divisor).
    Otherwise return (code, 1.0)."""
    # Case-insensitive check for minor units
    for mu, (major, divisor) in MINOR_UNIT_CURRENCIES.items():
        if code.lower() == mu.lower():
            return major, divisor
    return code, 1.0


def _fetch_fx_yfinance(code: str) -> Optional[float]:
    """Try to fetch USD per 1 unit-of-`code` from yfinance.
    Returns None on failure (caller falls back to static dict)."""
    if code == "USD":
        return 1.0
    try:
        import yfinance as yf
        # yfinance pair convention: USD<CCY>=X gives <CCY> per 1 USD.
        pair = f"USD{code}=X"
        t = yf.Ticker(pair)
        # fast_info is faster + less likely to 404
        price = None
        try:
            price = t.fast_info.get("last_price") or t.fast_info.get("lastPrice")
        except Exception:
            price = None
        if price is None:
            hist = t.history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].dropna().iloc[-1])
        if price and price > 0:
            return float(price)
    except Exception as e:
        log.warning("FX fetch failed for %s: %s", code, e)
    return None


def get_fx_per_usd(code: str, force_refresh: bool = False) -> float:
    """Return units-of-`code` per 1 USD.

    Tries yfinance first; falls back to the static dict in `config.py`.
    Caches in-process for `TTL_FX_S` seconds.
    """
    global _FX_FETCH_TIMESTAMP
    code = _normalize_currency_code(code)
    # Resolve minor units to major first (FX is for the major).
    major, _ = resolve_minor_unit(code)

    if not force_refresh and major in _FX_CACHE:
        rate, ts = _FX_CACHE[major]
        if (datetime.utcnow() - ts).total_seconds() < TTL_FX_S:
            return rate

    rate = _fetch_fx_yfinance(major)
    if rate is None:
        rate = FX_FALLBACK_PER_USD.get(major)
        if rate is None:
            # Unknown currency - default to identity to avoid silently zeroing.
            log.warning("Unknown currency %s; treating as USD", major)
            rate = 1.0
    _FX_CACHE[major] = (rate, datetime.utcnow())
    _FX_FETCH_TIMESTAMP = datetime.utcnow()
    return rate


def fx_snapshot_timestamp() -> Optional[datetime]:
    """Last time any FX fetch ran (used in the UI banner)."""
    return _FX_FETCH_TIMESTAMP


def to_usd(value: Optional[float], code: Optional[str]) -> Optional[float]:
    """Convert a monetary value in `code` (possibly a minor unit) to USD.

    Returns None if value is None / NaN.
    Unitless ratios should never be passed in here.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None

    code = _normalize_currency_code(code)
    major, divisor = resolve_minor_unit(code)
    # Step 1: minor -> major. Step 2: major -> USD via inverse rate.
    in_major = v / divisor
    rate_per_usd = get_fx_per_usd(major)
    if rate_per_usd <= 0:
        return None
    return in_major / rate_per_usd


def derive_market_cap(info: dict) -> Optional[float]:
    """Some yfinance tickers omit `marketCap`. Derive from shares×price
    in the trading currency BEFORE FX conversion."""
    mc = info.get("marketCap")
    if mc:
        return float(mc)
    shares = info.get("sharesOutstanding")
    price = info.get("regularMarketPrice") or info.get("currentPrice")
    if shares and price:
        return float(shares) * float(price)
    return None
