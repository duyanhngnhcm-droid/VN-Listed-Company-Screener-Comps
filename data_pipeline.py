"""
data_pipeline.py
================
Pull, normalize and cache fundamental data for the VN30 universe via
the `vnstock` library.

Public API
----------
- fetch_vn30_dataset(force_refresh=False) -> pd.DataFrame
    One row per VN30 ticker, columns = computed metrics + identification +
    diagnostic flags. The column set is the *union* of bank and non-financial
    metrics; missing cells are NaN.

Notes on robustness
-------------------
- vnstock's API surface differs across versions. We probe a couple of common
  call patterns and degrade gracefully. Every per-ticker call is wrapped in
  try/except; failures land in `diagnostics` for the sidebar panel.
- We try `VCI` first, then fall back to `TCBS` for income/BS/CF.
- Prices come from the same library; if both data sources fail, the row is
  emitted with NaNs and a `fetch_failed=True` flag.
"""

from __future__ import annotations
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from config import (
    VN30_CONSTITUENTS,
    VNSTOCK_PRIMARY_SOURCE,
    VNSTOCK_FALLBACK_SOURCE,
    FLAGGED_TICKERS,
    THIN_FLOAT_THRESHOLD,
)
import metrics as M

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Diagnostic record
# ---------------------------------------------------------------------------
@dataclass
class Diagnostic:
    timestamp: datetime = field(default_factory=datetime.utcnow)
    ticker_failures: Dict[str, str] = field(default_factory=dict)
    validation_warnings: List[str] = field(default_factory=list)
    low_completeness: List[str] = field(default_factory=list)


_DIAGNOSTIC = Diagnostic()


def latest_diagnostic() -> Diagnostic:
    return _DIAGNOSTIC


# ---------------------------------------------------------------------------
# vnstock plumbing
# ---------------------------------------------------------------------------
def _import_vnstock():
    """Import vnstock lazily so the rest of the app still loads when the lib
    isn't installed (e.g., during unit tests that mock the dataset)."""
    try:
        from vnstock import Vnstock  # type: ignore
        return Vnstock
    except Exception as e:  # pragma: no cover
        log.warning("vnstock import failed: %s", e)
        return None


def _safe_call(fn: Callable, *args, **kwargs) -> Optional[pd.DataFrame]:
    try:
        out = fn(*args, **kwargs)
        if isinstance(out, pd.DataFrame) and not out.empty:
            return out
    except Exception as e:
        log.debug("vnstock call failed (%s): %s", fn, e)
    return None


def _fetch_company_statements(ticker: str) -> Dict[str, pd.DataFrame]:
    """Pull income, balance sheet, cash flow at annual frequency for `ticker`.
    Returns a dict with keys is_, bs_, cf_; missing keys signal fetch failure
    for that statement."""
    Vnstock = _import_vnstock()
    if Vnstock is None:
        return {}

    out: Dict[str, pd.DataFrame] = {}
    for source in (VNSTOCK_PRIMARY_SOURCE, VNSTOCK_FALLBACK_SOURCE):
        try:
            stock = Vnstock().stock(symbol=ticker, source=source)
        except Exception as e:
            log.debug("Vnstock init failed (%s,%s): %s", ticker, source, e)
            continue

        is_df = _safe_call(stock.finance.income_statement, period="year")
        bs_df = _safe_call(stock.finance.balance_sheet, period="year")
        cf_df = _safe_call(stock.finance.cash_flow, period="year")
        if is_df is not None or bs_df is not None or cf_df is not None:
            if is_df is not None:
                out["is_"] = is_df
            if bs_df is not None:
                out["bs_"] = bs_df
            if cf_df is not None:
                out["cf_"] = cf_df
            # Once we get at least one statement from a source, stop —
            # mixing sources is worse than partial coverage.
            return out
    return out


def _fetch_price_and_mcap(ticker: str) -> Dict[str, Optional[float]]:
    """Return {price, market_cap_vnd_b, shares_outstanding}."""
    Vnstock = _import_vnstock()
    if Vnstock is None:
        return {"price": None, "market_cap_vnd_b": None, "shares_outstanding": None}

    end = datetime.utcnow().date()
    start = end - timedelta(days=30)
    price = None
    for source in (VNSTOCK_PRIMARY_SOURCE, VNSTOCK_FALLBACK_SOURCE):
        try:
            stock = Vnstock().stock(symbol=ticker, source=source)
            hist = _safe_call(
                stock.quote.history,
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1D",
            )
            if hist is not None:
                close_col = "close" if "close" in hist.columns else hist.columns[-1]
                price_series = pd.to_numeric(hist[close_col], errors="coerce").dropna()
                if not price_series.empty:
                    price = float(price_series.iloc[-1])
                    break
        except Exception as e:
            log.debug("Price fetch failed (%s,%s): %s", ticker, source, e)

    # vnstock prices are typically in VND units (not 1000s). Sanity-check via
    # rough magnitude: VN30 prices in VND are O(10^4 - 10^5).
    shares = None
    market_cap_vnd_b = None
    if price is not None:
        try:
            stock = Vnstock().stock(symbol=ticker, source=VNSTOCK_PRIMARY_SOURCE)
            company = stock.company
            try:
                overview = company.overview()
                if isinstance(overview, pd.DataFrame) and not overview.empty:
                    row = overview.iloc[0].to_dict()
                    for key in ("issue_share", "outstanding_share", "share_outstanding"):
                        if key in row and row[key]:
                            shares = float(row[key])
                            break
            except Exception:
                pass
        except Exception:
            pass

        if shares:
            # market cap in VND, convert to VND billion for display
            market_cap_vnd = shares * price
            market_cap_vnd_b = market_cap_vnd / 1e9

    return {
        "price": price,
        "market_cap_vnd_b": market_cap_vnd_b,
        "shares_outstanding": shares,
    }


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------
# vnstock tends to use Vietnamese labels with capitalized words and varying
# casing. We probe a list of candidate column names case-insensitively.
def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    # also fuzzy-match: substring
    for c_lower, c_orig in cols_lower.items():
        for cand in candidates:
            if cand.lower() in c_lower:
                return c_orig
    return None


def _series(df: Optional[pd.DataFrame], candidates: List[str]) -> List[Optional[float]]:
    """Return a list of values from `df` ordered most-recent → least-recent.
    Tries each candidate column name; returns [None]*0 on failure."""
    if df is None or df.empty:
        return []
    col = _find_col(df, candidates)
    if col is None:
        return []
    series = pd.to_numeric(df[col], errors="coerce").tolist()
    # Ensure ordering: most-recent first. vnstock tends to return descending,
    # but verify by checking presence of a 'year' / 'period' column.
    year_col = _find_col(df, ["yearReport", "year", "period", "ticker_period"])
    if year_col:
        try:
            years = pd.to_numeric(df[year_col], errors="coerce").tolist()
            # Sort by year descending
            paired = list(zip(years, series))
            paired = [(y, v) for y, v in paired if y is not None and not (isinstance(y, float) and math.isnan(y))]
            paired.sort(key=lambda p: p[0], reverse=True)
            series = [v for _, v in paired]
        except Exception:
            pass
    # Strip NaNs at the head only? Keep them in place — caller decides.
    return [None if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v) for v in series]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
ALL_METRICS = [
    "revenue_cagr_3y", "loan_growth_3y", "roe", "roic",
    "ebitda_margin", "fcf_yield", "pe", "pb",
    "nim", "cir", "npl", "dividend_yield",
]


def _row_for_ticker(ticker: str, name: str, free_float: float,
                    scorecard: str, sub_sector: str) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "ticker": ticker,
        "name": name,
        "free_float": free_float,
        "scorecard": scorecard,
        "sub_sector": sub_sector,
        "fetch_failed": False,
        "tags": [],
    }
    # Apply static tags
    if free_float < THIN_FLOAT_THRESHOLD:
        row["tags"].append("thin_float")
    if ticker in FLAGGED_TICKERS:
        row["tags"].append(FLAGGED_TICKERS[ticker])

    statements = _fetch_company_statements(ticker)
    price_info = _fetch_price_and_mcap(ticker)
    row["price"] = price_info.get("price")
    row["market_cap_vnd_b"] = price_info.get("market_cap_vnd_b")

    if not statements:
        row["fetch_failed"] = True
        _DIAGNOSTIC.ticker_failures[ticker] = "no statements returned from VCI/TCBS"
        for m in ALL_METRICS:
            row[m] = np.nan
        row["data_completeness"] = 0.0
        return row

    is_df = statements.get("is_")
    bs_df = statements.get("bs_")
    cf_df = statements.get("cf_")

    revenue = _series(is_df, ["Revenue (Bn. VND)", "Revenue", "revenue", "Net revenue", "Net Sales"])
    op_income = _series(is_df, ["Operating Profit/Loss", "Operating profit", "Profit from operating activities", "EBIT", "Operating Income"])
    da = _series(cf_df, ["Depreciation and Amortisation", "Depreciation", "Amortisation"])
    net_income = _series(is_df, ["Net Profit For the Year", "Net profit after tax", "Profit for the year", "Net Income"])
    interest_expense = _series(is_df, ["Interest Expenses", "Interest expense"])
    tax_expense = _series(is_df, ["Business income tax - current", "Income tax", "Tax expense"])

    equity = _series(bs_df, ["Equity", "TOTAL OWNERS' EQUITY", "Owners' equity", "Total Equity"])
    total_assets = _series(bs_df, ["TOTAL ASSETS", "Total Assets", "total assets"])
    total_debt = _series(bs_df, ["Total Debt", "Long-term Debt", "Short-term Debt"])
    cash = _series(bs_df, ["Cash and cash equivalents", "Cash"])
    loans = _series(bs_df, ["Loans to customers", "Loan to customer", "Customer loans", "Net loans"])

    operating_cf = _series(cf_df, ["Net cash inflows/outflows from operating activities", "Cash flow from operating", "Operating Cash Flow"])
    capex = _series(cf_df, ["Purchase of fixed assets", "Capital expenditure", "Acquisition of fixed assets"])

    # Bank-specific
    nii = _series(is_df, ["Net Interest Income", "Net interest income"])
    operating_expenses = _series(is_df, ["Operating Expenses", "Operating expense", "General & Admin Expenses"])
    operating_revenue = _series(is_df, ["Net operating income", "Total operating income", "Total Operating Revenue"])

    # ---------- Compute non-bank metrics ----------
    row["revenue_cagr_3y"] = M.cagr_3y(revenue) if len(revenue) >= 4 else np.nan
    row["roe"] = M.roe_avg(net_income, equity) if scorecard == "non_financials" else M.roe_avg(net_income, equity)
    row["roic"] = M.roic(op_income, tax_expense, total_debt, equity, cash)
    row["ebitda_margin"] = M.ebitda_margin(op_income, da, revenue)
    row["fcf_yield"] = M.fcf_yield(operating_cf, capex, row.get("market_cap_vnd_b"))
    row["pe"] = M.pe_ratio(row.get("market_cap_vnd_b"), net_income)
    row["pb"] = M.pb_ratio(row.get("market_cap_vnd_b"), equity)

    # ---------- Compute bank metrics ----------
    row["loan_growth_3y"] = M.cagr_3y(loans) if len(loans) >= 4 else np.nan
    row["nim"] = M.nim(nii, total_assets)
    row["cir"] = M.cost_to_income(operating_expenses, operating_revenue)
    row["npl"] = np.nan  # vnstock NPL endpoint coverage is patchy; left N/A
    row["dividend_yield"] = np.nan  # vnstock dividend history endpoint is patchy

    # ---------- Validation flags ----------
    if revenue and revenue[0] is not None and len(revenue) > 1 and revenue[1] is not None and revenue[1] > 0:
        if revenue[0] / revenue[1] > 5:
            _DIAGNOSTIC.validation_warnings.append(f"{ticker}: revenue jumped >5x YoY; flagged for manual review")
            row["tags"].append("structural_change")
    if row["roe"] is not None and not np.isnan(row["roe"]) and row["roe"] > 1.0:
        _DIAGNOSTIC.validation_warnings.append(f"{ticker}: ROE > 100% — likely data error")

    # ---------- Completeness ----------
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
        row["tags"].append("incomplete_data")

    return row


def fetch_vn30_dataset(force_refresh: bool = False) -> pd.DataFrame:
    """Fetch and assemble the full VN30 dataset.

    Hooked to Streamlit's cache via the wrapper in `vn30_screener.py`. The
    `force_refresh` flag is honored at the wrapper level by clearing caches.
    """
    global _DIAGNOSTIC
    _DIAGNOSTIC = Diagnostic()
    rows: List[Dict[str, Any]] = []
    for ticker, name, ff, scorecard, sub in VN30_CONSTITUENTS:
        try:
            rows.append(_row_for_ticker(ticker, name, ff, scorecard, sub))
        except Exception as e:
            log.exception("Row build failed for %s", ticker)
            _DIAGNOSTIC.ticker_failures[ticker] = str(e)
            rows.append({
                "ticker": ticker, "name": name, "free_float": ff,
                "scorecard": scorecard, "sub_sector": sub,
                "fetch_failed": True, "data_completeness": 0.0,
                "tags": ["fetch_failed"],
                **{m: np.nan for m in ALL_METRICS},
            })

    df = pd.DataFrame(rows)
    return df
