"""
config.py
=========
Static configuration for the VN30 Listed Company Screener.

Contents
--------
- VN30 constituent list (ticker, full name, free-float, scorecard).
  Update once per quarter after each HOSE rebalance (Jan/Apr/Jul/Oct).
- Default scorecard weights for the composite score.
- FX fallback dictionary used when yfinance live FX fetch fails.
- Misc constants (cache TTLs, thin-float threshold, etc.).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# VN30 constituents
# ---------------------------------------------------------------------------
# Format: (ticker, company_name, free_float_pct, scorecard, sub_sector)
# `scorecard` is one of: "banks", "non_financials"
# `sub_sector` is informational only (used for the heatmap / filter chips).
# Last reviewed: 2025-Q1 rebalance. Verify against HOSE before relying on this.
VN30_CONSTITUENTS = [
    # ----- Banks (14) -------------------------------------------------------
    ("ACB", "Asia Commercial Joint Stock Bank", 0.85, "banks", "Banks"),
    ("BID", "Joint Stock Commercial Bank For Investment And Development Of Vietnam", 0.04, "banks", "Banks"),
    ("CTG", "Viet Nam Joint Stock Commercial Bank For Industry And Trade", 0.15, "banks", "Banks"),
    ("HDB", "Ho Chi Minh City Development Joint Stock Commercial Bank", 0.75, "banks", "Banks"),
    ("LPB", "Lien Viet Post Joint Stock Commercial Bank", 0.95, "banks", "Banks"),
    ("MBB", "Military Commercial Joint Stock Bank", 0.50, "banks", "Banks"),
    ("SHB", "Sai Gon - Ha Noi Commercial Joint Stock Bank", 0.70, "banks", "Banks"),
    ("SSB", "Southeast Asia Commercial Joint Stock Bank", 0.55, "banks", "Banks"),
    ("STB", "Sai Gon Thuong Tin Commercial Joint Stock Bank", 0.95, "banks", "Banks"),
    ("TCB", "Vietnam Technological and Commercial Joint Stock Bank", 0.55, "banks", "Banks"),
    ("TPB", "Tien Phong Commercial Joint Stock Bank", 0.55, "banks", "Banks"),
    ("VCB", "Joint Stock Commercial Bank For Foreign Trade of Viet Nam", 0.11, "banks", "Banks"),
    ("VIB", "Vietnam International Commercial Joint Stock Bank", 0.60, "banks", "Banks"),
    ("VPB", "VietNam Prosperity Joint Stock Commercial Bank", 0.60, "banks", "Banks"),
    # ----- Non-financials (16) ---------------------------------------------
    ("BCM", "Becamex IDC Corporation", 0.05, "non_financials", "Industrial Real Estate"),
    ("BVH", "Bao Viet Holdings", 0.30, "non_financials", "Insurance"),  # flagged
    ("FPT", "FPT Corporation", 0.85, "non_financials", "Tech / Software"),
    ("GAS", "PetroVietnam Gas Joint Stock Corporation", 0.05, "non_financials", "Energy / Oil & Gas"),
    ("GVR", "Vietnam Rubber Group Joint Stock Company", 0.04, "non_financials", "Materials"),
    ("HPG", "Hoa Phat Group Joint Stock Company", 0.55, "non_financials", "Materials"),
    ("MSN", "Masan Group Corporation", 0.60, "non_financials", "Consumer Staples"),
    ("MWG", "Mobile World Investment Corporation", 0.75, "non_financials", "Consumer Retail"),
    ("PLX", "Petrolimex Vietnam National Petroleum Group", 0.10, "non_financials", "Energy / Oil & Gas"),
    ("SAB", "Saigon Beer Alcohol Beverage Corporation", 0.11, "non_financials", "Consumer Staples"),
    ("SSI", "SSI Securities Corporation", 0.70, "non_financials", "Brokerage"),  # flagged
    ("VHM", "Vinhomes Joint Stock Company", 0.30, "non_financials", "Real Estate Developer"),
    ("VIC", "Vingroup Joint Stock Company", 0.35, "non_financials", "Real Estate Developer"),
    ("VJC", "VietJet Aviation Joint Stock Company", 0.45, "non_financials", "Aviation / Transport"),
    ("VNM", "Viet Nam Dairy Products Joint Stock Company", 0.40, "non_financials", "Consumer Staples"),
    ("VRE", "Vincom Retail Joint Stock Company", 0.40, "non_financials", "Real Estate Developer"),
]

# ---------------------------------------------------------------------------
# Per-name analytical flags
# ---------------------------------------------------------------------------
# Tickers that should display caveat tags in the screener output.
FLAGGED_TICKERS = {
    "SSI": "brokerage",                      # asset-light financial, EBITDA/FCF noisy
    "BVH": "insurance",                      # combined ratio / EV not in vnstock
    "VHM": "developer",                      # project-cycle volatility
    "VIC": "developer",
    "VRE": "developer",
}

THIN_FLOAT_THRESHOLD = 0.20  # < 20 % flagged in UI

# ---------------------------------------------------------------------------
# Default composite weights
# ---------------------------------------------------------------------------
# Weights MUST sum to 1.0 within each scorecard.
# Methodology rationale lives in the in-app "Methodology" box and README.

DEFAULT_WEIGHTS_NON_FINANCIALS = {
    "revenue_cagr_3y": 0.25,
    "roe":             0.15,
    "roic":            0.10,
    "ebitda_margin":   0.10,
    "fcf_yield":       0.20,
    "pe":              0.10,
    "pb":              0.10,
}

DEFAULT_WEIGHTS_BANKS = {
    "loan_growth_3y":  0.20,
    "roe":             0.20,
    "nim":             0.10,
    "cir":             0.10,   # inverted (lower = better) inside scoring
    "npl":             0.20,   # inverted; redistributed if N/A across cohort
    "pb":              0.15,
    "dividend_yield":  0.05,
}

# Direction = "high" (higher is better) or "low" (lower is better).
# Used by the scoring engine to invert ranks / z-scores.
METRIC_DIRECTION_NON_FINANCIALS = {
    "revenue_cagr_3y": "high",
    "roe":             "high",
    "roic":            "high",
    "ebitda_margin":   "high",
    "fcf_yield":       "high",
    "pe":              "low",
    "pb":              "low",
}

METRIC_DIRECTION_BANKS = {
    "loan_growth_3y":  "high",
    "roe":             "high",
    "nim":             "high",
    "cir":             "low",
    "npl":             "low",
    "pb":              "low",
    "dividend_yield":  "high",
}

# Display labels for the UI / methodology box.
METRIC_LABELS = {
    "revenue_cagr_3y": "Revenue CAGR 3y",
    "loan_growth_3y":  "Loan Growth 3y",
    "roe":             "ROE",
    "roic":            "ROIC",
    "ebitda_margin":   "EBITDA Margin",
    "fcf_yield":       "FCF Yield",
    "pe":              "P/E",
    "pb":              "P/B",
    "nim":             "NIM",
    "cir":             "CIR",
    "npl":             "NPL",
    "dividend_yield":  "Dividend Yield",
}

# Format spec for displaying a metric in the table.
# 'pct' = ×100 with one decimal and "%"; 'mult' = bare number with one decimal.
METRIC_FORMAT = {
    "revenue_cagr_3y": "pct",
    "loan_growth_3y":  "pct",
    "roe":             "pct",
    "roic":            "pct",
    "ebitda_margin":   "pct",
    "fcf_yield":       "pct",
    "nim":             "pct",
    "cir":             "pct",
    "npl":             "pct",
    "dividend_yield":  "pct",
    "pe":              "mult",
    "pb":              "mult",
}

# ---------------------------------------------------------------------------
# Weight customization guard-rails
# ---------------------------------------------------------------------------
WEIGHT_MIN = 0.0
WEIGHT_MAX = 0.60   # >60 % collapses the screen toward a single-metric rank
WEIGHT_TOTAL_TOL = 0.001  # absolute tolerance vs. 1.0 before normalization

# ---------------------------------------------------------------------------
# Cache TTLs (seconds)
# ---------------------------------------------------------------------------
TTL_FUNDAMENTALS_S   = 24 * 3600
TTL_PRICES_S         = 1 * 3600
TTL_GLOBAL_PEER_S    = 24 * 3600
TTL_FX_S             = 24 * 3600

# ---------------------------------------------------------------------------
# Vnstock data source preference
# ---------------------------------------------------------------------------
VNSTOCK_PRIMARY_SOURCE  = "VCI"
VNSTOCK_FALLBACK_SOURCE = "TCBS"

# ---------------------------------------------------------------------------
# FX fallback dictionary (units = 1 USD in local currency)
# Used when yfinance pair fetch fails. Numbers are deliberately stale-tolerant
# - the FX banner will show last-fetch timestamp so the analyst knows.
# ---------------------------------------------------------------------------
FX_FALLBACK_PER_USD = {
    "USD": 1.0,
    "VND": 25_400.0,
    "THB": 36.5,
    "IDR": 16_200.0,
    "MYR": 4.7,
    "PHP": 58.0,
    "SGD": 1.35,
    "INR": 84.0,
    "CNY": 7.2,
    "HKD": 7.8,
    "TWD": 32.0,
    "KRW": 1_400.0,
    "JPY": 155.0,
    "AUD": 1.55,
    "EUR": 0.92,
    "GBP": 0.79,
    "CHF": 0.88,
    "AED": 3.67,
    "SAR": 3.75,
    "BRL": 5.5,
    "MXN": 17.0,
    "ZAR": 18.5,
    "ILS": 3.7,
}

# Minor-unit listing currencies whose price is reported in 1/100 of the major.
MINOR_UNIT_CURRENCIES = {
    "GBp": ("GBP", 100.0),  # London pence
    "ZAc": ("ZAR", 100.0),  # JSE cents
    "ILA": ("ILS", 100.0),  # TASE agorot
}

# ---------------------------------------------------------------------------
# Diagnostic / quality thresholds
# ---------------------------------------------------------------------------
DATA_COMPLETENESS_DROP_THRESHOLD = 0.50  # below this, drop from composite ranking
INTEREST_COVERAGE_DISTRESS_FLOOR = 1.5
LIQUIDITY_FLOOR_USD              = 1_000_000  # ADV
SIZE_BAND_SIGMA                  = 1.0   # log-space band for OPCM Tier 1
SIZE_BAND_RELAX_SIGMA            = 1.5
PERFORMANCE_SIMILARITY_K         = 2.0   # ≥k σ away ⇒ similarity 0
TIER_A_COUNTRIES = {"TH", "ID", "MY", "PH", "SG", "VN"}
TIER_B_COUNTRIES = {"IN", "CN", "HK", "TW", "KR"}
TIER_C_COUNTRIES = {"AE", "SA", "QA", "BR", "MX", "ZA"}
DEVELOPED_COUNTRIES = {"US", "GB", "DE", "FR", "JP", "AU", "CA", "CH", "NL", "SE", "IT", "ES"}
