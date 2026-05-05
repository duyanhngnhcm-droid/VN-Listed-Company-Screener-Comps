"""
data_pipeline.py
================
Pull, normalize and cache fundamental data for the VN30 universe via
**yfinance** (replacing the previous `vnstock`-based implementation).

Public API (UNCHANGED — every other module relies on this surface)
-----------------------------------------------------------------
- `Diagnostic`      dataclass
- `latest_diagnostic() -> Diagnostic`
- `ALL_METRICS`     list of metric column names
- `fetch_vn30_dataset(force_refresh: bool = False) -> pd.DataFrame`

Why we switched
---------------
vnstock calls VCI/TCBS endpoints that are blocked or time out from
Streamlit Community Cloud. yfinance is reachable from any cloud host and
exposes annual income / balance / cash-flow statements for HOSE tickers
under the `.VN` suffix (e.g. `VCB.VN`, `HPG.VN`).

Important conventions preserved
-------------------------------
- Per-ticker `row` dict matches the previous schema exactly (fields,
  tags, completeness, etc.) so `metrics.py`, `scoring.py`, and the UI
  modules need no edits.
- Vietnamese financials remain expressed in **VND billions**. yfinance
  returns raw VND; we divide by 1e9 before storing.
- Most-recent-first ordering of statement series is preserved (the rule
  expected by `metrics.py`).
"""

from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from config import (
    VN30_CONSTITUENTS,
    FLAGGED_TICKERS,
    THIN_FLOAT_THRESHOLD,
)
import metrics as M

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Diagnostic record (unchanged shape — adds an extra category accessed
# via `.ticker_failures` so existing UI code still works)
# ---------------------------------------------------------------------------
@dataclass
class Diagnostic:
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ticker_failures: Dict[str, str] = field(default_factory=dict)
    validation_warnings: List[str] = field(default_factory=list)
    low_completeness: List[str] = field(default_factory=list)
    yfinance_empty: List[str] = field(default_factory=list)


_DIAGNOSTIC = Diagnostic()


def latest_diagnostic() -> Diagnostic:
    return _DIAGNOSTIC


# ---------------------------------------------------------------------------
# Public column-name list — preserved from the vnstock implementation.
# ---------------------------------------------------------------------------
ALL_METRICS = [
    "revenue_cagr_3y", "loan_growth_3y", "roe", "roic",
    "ebitda_margin", "fcf_yield", "pe", "pb",
    "nim", "cir", "npl", "dividend_yield",
]


# ---------------------------------------------------------------------------
# yfinance plumbing
# ---------------------------------------------------------------------------
_RETRY_BACKOFF_S = 2.0
_MAX_WORKERS = 8  # if rate-limited, drop to 4 (documented in README patch)


def _import_yf():
    """Lazy import; lets the rest of the app load if yfinance is missing."""
    try:
        import yfinance as yf  # type: ignore
        return yf
    except Exception as e:  # pragma: no cover
        log.warning("yfinance import failed: %s", e)
        return None


def _yf_ticker(yf, vn_ticker: str):
    """Build a yfinance Ticker handle with the `.VN` suffix convention."""
    return yf.Ticker(f"{vn_ticker}.VN")


def _safe_df(getter, retries: int = 1) -> Optional[pd.DataFrame]:
    """Call a yfinance attribute that returns a DataFrame; retry once with
    a 2s backoff on empty/exception (yfinance occasionally returns empty on
    the first hit then succeeds on retry)."""
    attempt = 0
    while attempt <= retries:
        try:
            df = getter()
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception as e:
            log.debug("yfinance getter failed (attempt %d): %s", attempt, e)
        attempt += 1
        if attempt <= retries:
            time.sleep(_RETRY_BACKOFF_S)
    return None


def _safe_info(yfticker, retries: int = 1) -> Dict[str, Any]:
    attempt = 0
    while attempt <= retries:
        try:
            info = dict(yfticker.info or {})
            if info:
                return info
        except Exception as e:
            log.debug("yfinance .info failed (attempt %d): %s", attempt, e)
        attempt += 1
        if attempt <= retries:
            time.sleep(_RETRY_BACKOFF_S)
    return {}


# ---------------------------------------------------------------------------
# yfinance row-label resolver
# ---------------------------------------------------------------------------
# yfinance row labels drift between releases (e.g. "EBIT" vs "Operating Income"
# vs "Operating Income Loss"). We do an exact-match-first probe, then case-
# insensitive substring fallback. Returns `None` when no candidate matches.
def _find_index(df: Optional[pd.DataFrame], candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    idx = list(df.index)
    idx_lower = {str(s).lower(): s for s in idx}

    # 1) exact match (case-insensitive)
    for cand in candidates:
        if cand.lower() in idx_lower:
            return idx_lower[cand.lower()]
    # 2) substring fallback
    for cand in candidates:
        cand_l = cand.lower()
        for s_lower, s_orig in idx_lower.items():
            if cand_l in s_lower:
                return s_orig
    return None


def _series_recent_first(df: Optional[pd.DataFrame], candidates: List[str]) -> List[Optional[float]]:
    """Return numeric values for a row, sorted most-recent first.

    yfinance statement DataFrames have date columns. Newest date first
    is the convention `metrics.py` expects.
    """
    if df is None or df.empty:
        return []
    label = _find_index(df, candidates)
    if label is None:
        return []
    try:
        row = df.loc[label]
    except Exception:
        return []
    # Sort by column (date) descending. yfinance often already does this,
    # but enforce explicitly so the `metrics.py` t/t-3 indexing is correct.
    try:
        cols_sorted = sorted(row.index, key=lambda c: pd.to_datetime(c, errors="coerce"), reverse=True)
        row = row.reindex(cols_sorted)
    except Exception:
        pass
    out: List[Optional[float]] = []
    for v in row.tolist():
        if v is None:
            out.append(None)
            continue
        try:
            f = float(v)
            if math.isnan(f):
                out.append(None)
            else:
                # Convert raw VND to VND billions for fundamentals.
                out.append(f / 1e9)
        except (TypeError, ValueError):
            out.append(None)
    return out


# ---------------------------------------------------------------------------
# Per-ticker fetch
# ---------------------------------------------------------------------------
def _fetch_ticker_payload(yf, ticker: str) -> Dict[str, Any]:
    """Fetch the raw data payload for one VN ticker. All network I/O for
    one ticker happens here; the caller assembles a row from this."""
    payload: Dict[str, Any] = {
        "is_": None, "bs_": None, "cf_": None, "info": {},
        "yfinance_empty": False,
    }
    yt = _yf_ticker(yf, ticker)

    # Statements
    payload["is_"] = _safe_df(lambda: yt.financials, retries=1)
    payload["bs_"] = _safe_df(lambda: yt.balance_sheet, retries=1)
    payload["cf_"] = _safe_df(lambda: yt.cashflow, retries=1)
    payload["info"] = _safe_info(yt, retries=1)

    if payload["is_"] is None and payload["bs_"] is None and payload["cf_"] is None:
        payload["yfinance_empty"] = True
    return payload


def _row_from_payload(ticker: str, name: str, free_float: float,
                      scorecard: str, sub_sector: str,
                      payload: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "ticker": ticker, "name": name, "free_float": free_float,
        "scorecard": scorecard, "sub_sector": sub_sector,
        "fetch_failed": False, "tags": [],
    }

    # Static tags (preserved from the vnstock implementation)
    if free_float < THIN_FLOAT_THRESHOLD:
        row["tags"].append("thin_float")
    if ticker in FLAGGED_TICKERS:
        row["tags"].append(FLAGGED_TICKERS[ticker])

    is_df: Optional[pd.DataFrame] = payload.get("is_")
    bs_df: Optional[pd.DataFrame] = payload.get("bs_")
    cf_df: Optional[pd.DataFrame] = payload.get("cf_")
    info: Dict[str, Any] = payload.get("info") or {}

    # ---------------- price + market cap ----------------
    price = info.get("regularMarketPrice") or info.get("currentPrice")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    row["price"] = price

    market_cap_vnd = info.get("marketCap")
    market_cap_vnd_b: Optional[float] = None
    if market_cap_vnd:
        try:
            market_cap_vnd_b = float(market_cap_vnd) / 1e9
        except (TypeError, ValueError):
            market_cap_vnd_b = None
    if market_cap_vnd_b is None:
        # Derive from shares × price
        shares = info.get("sharesOutstanding")
        if shares and price:
            try:
                market_cap_vnd_b = (float(shares) * float(price)) / 1e9
            except (TypeError, ValueError):
                market_cap_vnd_b = None
    row["market_cap_vnd_b"] = market_cap_vnd_b

    # ---------------- early-out: nothing to compute ----------------
    if payload.get("yfinance_empty"):
        row["fetch_failed"] = True
        _DIAGNOSTIC.yfinance_empty.append(ticker)
        _DIAGNOSTIC.ticker_failures[ticker] = "yfinance returned empty for all statements"
        for m in ALL_METRICS:
            row[m] = np.nan
        row["data_completeness"] = 0.0
        return row

    # ---------------- statement series ----------------
    revenue = _series_recent_first(is_df, [
        "Total Revenue", "TotalRevenue", "Revenue", "Net Sales",
    ])
    op_income = _series_recent_first(is_df, [
        "Operating Income", "OperatingIncome", "EBIT",
        "Operating Income Loss", "Operating Profit",
    ])
    da = _series_recent_first(cf_df, [
        "Depreciation And Amortization", "Depreciation Amortization Depletion",
        "Reconciled Depreciation", "Depreciation",
    ])
    if not da:
        # yfinance occasionally puts D&A on the income statement
        da = _series_recent_first(is_df, [
            "Reconciled Depreciation", "Depreciation And Amortization",
        ])
    net_income = _series_recent_first(is_df, [
        "Net Income", "Net Income Common Stockholders",
        "Net Income From Continuing Operations",
    ])
    interest_expense = _series_recent_first(is_df, [
        "Interest Expense", "Interest Expense Non Operating",
    ])
    tax_expense = _series_recent_first(is_df, [
        "Tax Provision", "Income Tax Expense", "Provision For Income Taxes",
    ])
    pretax_income = _series_recent_first(is_df, ["Pretax Income"])

    # EBITDA: prefer reported value if available (otherwise metrics.ebitda_margin
    # falls back to operating_income + D&A on its own).
    ebitda = _series_recent_first(is_df, ["Normalized EBITDA", "EBITDA"])

    equity = _series_recent_first(bs_df, [
        "Stockholders Equity", "Total Equity Gross Minority Interest",
        "Common Stock Equity", "Total Stockholders Equity",
    ])
    total_assets = _series_recent_first(bs_df, ["Total Assets"])
    total_debt = _series_recent_first(bs_df, [
        "Total Debt", "Net Debt",
    ])
    cash = _series_recent_first(bs_df, [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash Financial",
    ])
    # NOTE: yfinance does not expose a true loan book for ASEAN banks.
    # Use Net Receivables as a documented proxy (flagged in tags below).
    loans = _series_recent_first(bs_df, [
        "Net Receivables", "Receivables", "Accounts Receivable",
    ])

    operating_cf = _series_recent_first(cf_df, [
        "Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
        "Cash Flowsfromusedin Operating Activities Direct",
    ])
    # yfinance returns capex as a NEGATIVE number — metrics.fcf_yield uses
    # abs() internally, but we pass through unchanged so ordering is preserved.
    capex = _series_recent_first(cf_df, [
        "Capital Expenditure", "Capital Expenditures",
        "Purchase Of PPE", "Net PPE Purchase And Sale",
    ])

    # Bank-specific (best-effort under yfinance)
    nii = _series_recent_first(is_df, ["Net Interest Income"])
    operating_expenses = _series_recent_first(is_df, [
        "Operating Expense", "Operating Expenses", "Total Operating Expenses",
    ])
    # CIR denominator: NII + non-interest income. yfinance doesn't expose
    # that cleanly, so we approximate with Total Revenue per the patch spec.
    operating_revenue = _series_recent_first(is_df, [
        "Total Revenue", "Net Interest Income",
    ])

    # ---------------- compute non-bank metrics ----------------
    row["revenue_cagr_3y"] = M.cagr_3y(revenue) if len(revenue) >= 4 else np.nan
    row["roe"] = M.roe_avg(net_income, equity)
    row["roic"] = M.roic(op_income, tax_expense, total_debt, equity, cash)

    # EBITDA margin: prefer reported EBITDA, else fall back to operating + D&A.
    if ebitda and ebitda[0] is not None and revenue and revenue[0] not in (None, 0):
        try:
            row["ebitda_margin"] = float(ebitda[0]) / float(revenue[0])
        except (TypeError, ValueError, ZeroDivisionError):
            row["ebitda_margin"] = np.nan
    else:
        row["ebitda_margin"] = M.ebitda_margin(op_income, da, revenue)

    row["fcf_yield"] = M.fcf_yield(operating_cf, capex, row.get("market_cap_vnd_b"))
    row["pe"] = M.pe_ratio(row.get("market_cap_vnd_b"), net_income)
    row["pb"] = M.pb_ratio(row.get("market_cap_vnd_b"), equity)

    # ---------------- compute bank metrics ----------------
    # Loan growth uses the receivables proxy; tag it for the analyst.
    if scorecard == "banks" and loans:
        row["tags"].append("loans_proxied_by_receivables")
    row["loan_growth_3y"] = M.cagr_3y(loans) if len(loans) >= 4 else np.nan
    row["nim"] = M.nim(nii, total_assets) if nii and total_assets else np.nan
    row["cir"] = M.cost_to_income(operating_expenses, operating_revenue)
    row["npl"] = np.nan  # not available via yfinance
    if scorecard == "banks":
        # Surface NPL gap once per bank in diagnostics so the message
        # appears in the sidebar exactly as documented.
        _DIAGNOSTIC.validation_warnings.append(
            f"{ticker}: NPL not available via yfinance; bank asset-quality pillar weight redistributed"
        )

    # Dividend yield from `info.dividendYield` (already a fraction).
    dy = info.get("dividendYield")
    try:
        row["dividend_yield"] = float(dy) if dy is not None else np.nan
    except (TypeError, ValueError):
        row["dividend_yield"] = np.nan
    # yfinance occasionally returns dividend yield as percent (e.g. 4.2 for 4.2%).
    # Heuristic: anything > 1 is treated as a percent and divided by 100.
    if isinstance(row["dividend_yield"], float) and row["dividend_yield"] > 1.0:
        row["dividend_yield"] = row["dividend_yield"] / 100.0

    # ---------------- validation flags ----------------
    if revenue and revenue[0] is not None and len(revenue) > 1 and revenue[1] is not None and revenue[1] > 0:
        if revenue[0] / revenue[1] > 5:
            _DIAGNOSTIC.validation_warnings.append(
                f"{ticker}: revenue jumped >5x YoY; flagged for manual review"
            )
            row["tags"].append("structural_change")
    if row["roe"] is not None and not (isinstance(row["roe"], float) and np.isnan(row["roe"])) and row["roe"] > 1.0:
        _DIAGNOSTIC.validation_warnings.append(f"{ticker}: ROE > 100% — likely data error")

    # Insufficient history flag
    if len(revenue) < 4 and scorecard == "non_financials":
        row["tags"].append("incomplete_history")
    if len(loans) < 4 and scorecard == "banks":
        row["tags"].append("incomplete_history")

    # ---------------- completeness ----------------
    metrics_for_card = (
        ["revenue_cagr_3y", "roe", "roic", "ebitda_margin", "fcf_yield", "pe", "pb"]
        if scorecard == "non_financials"
        else ["loan_growth_3y", "roe", "nim", "cir", "npl", "pb", "dividend_yield"]
    )
    populated = sum(
        1 for m in metrics_for_card
        if row.get(m) is not None and not (isinstance(row[m], float) and np.isnan(row[m]))
    )
    row["data_completeness"] = populated / len(metrics_for_card)
    if row["data_completeness"] < 0.50:
        _DIAGNOSTIC.low_completeness.append(ticker)
        if "incomplete_data" not in row["tags"]:
            row["tags"].append("incomplete_data")

    return row


# ---------------------------------------------------------------------------
# Public API: parallel fetch over the VN30 universe
# ---------------------------------------------------------------------------
def fetch_vn30_dataset(force_refresh: bool = False) -> pd.DataFrame:
    """Fetch and assemble the full VN30 dataset (one row per ticker).

    Parallelism: ThreadPoolExecutor(max_workers=8). yfinance is I/O bound,
    so concurrent fetches reduce total load time from minutes to seconds.

    `force_refresh` is honored at the cache-wrapper level (in
    `vn30_screener.py`); inside this function it's a no-op.
    """
    global _DIAGNOSTIC
    _DIAGNOSTIC = Diagnostic()

    yf = _import_yf()
    if yf is None:
        # Hard-fail every row but don't crash. The UI will show NaNs.
        rows = []
        for ticker, name, ff, scorecard, sub in VN30_CONSTITUENTS:
            _DIAGNOSTIC.ticker_failures[ticker] = "yfinance not installed"
            rows.append({
                "ticker": ticker, "name": name, "free_float": ff,
                "scorecard": scorecard, "sub_sector": sub,
                "fetch_failed": True, "data_completeness": 0.0,
                "tags": ["fetch_failed"],
                "price": None, "market_cap_vnd_b": None,
                **{m: np.nan for m in ALL_METRICS},
            })
        return pd.DataFrame(rows)

    # Step 1: parallel network fetch
    payloads: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        future_to_ticker = {
            ex.submit(_fetch_ticker_payload, yf, ticker): ticker
            for ticker, *_ in VN30_CONSTITUENTS
        }
        for fut in as_completed(future_to_ticker):
            t = future_to_ticker[fut]
            try:
                payloads[t] = fut.result()
            except Exception as e:
                log.exception("Fetch failed for %s", t)
                payloads[t] = {
                    "is_": None, "bs_": None, "cf_": None, "info": {},
                    "yfinance_empty": True, "_error": str(e),
                }

    # Step 2: assemble rows in the canonical VN30 order
    rows: List[Dict[str, Any]] = []
    for ticker, name, ff, scorecard, sub in VN30_CONSTITUENTS:
        payload = payloads.get(ticker, {"is_": None, "bs_": None, "cf_": None,
                                       "info": {}, "yfinance_empty": True})
        try:
            rows.append(_row_from_payload(ticker, name, ff, scorecard, sub, payload))
        except Exception as e:
            log.exception("Row build failed for %s", ticker)
            _DIAGNOSTIC.ticker_failures[ticker] = str(e)
            rows.append({
                "ticker": ticker, "name": name, "free_float": ff,
                "scorecard": scorecard, "sub_sector": sub,
                "fetch_failed": True, "data_completeness": 0.0,
                "tags": ["fetch_failed"],
                "price": None, "market_cap_vnd_b": None,
                **{m: np.nan for m in ALL_METRICS},
            })

    return pd.DataFrame(rows)
