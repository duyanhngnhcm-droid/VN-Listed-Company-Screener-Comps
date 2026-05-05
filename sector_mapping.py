"""
sector_mapping.py
=================
Maps each VN30 ticker to an internal *sector bucket*.

We do NOT trust yfinance / vnstock-provided industry classifications for
Vietnamese names — they're inconsistent and sometimes wrong. The bucket name
is the join key between a target and its candidate pool (`peer_pools.py`).

Buckets are intentionally coarse so peer pools across the region are large
enough to survive the OPCM cascade.
"""

from __future__ import annotations
from typing import Dict, Tuple

# bucket -> sector-aware metric choice for OPCM Tier 2
SECTOR_METRIC_PROFILES: Dict[str, Dict[str, str]] = {
    "banks":               {"profitability": "roe",            "growth": "earnings_growth"},
    "insurance":           {"profitability": "roe",            "growth": "earnings_growth"},
    "financials_brokerage":{"profitability": "roe",            "growth": "earnings_growth"},
    "real_estate_developer":{"profitability": "operating_margin","growth": "revenue_growth"},
    "consumer_retail":     {"profitability": "operating_margin","growth": "revenue_growth"},
    "consumer_staples":    {"profitability": "operating_margin","growth": "revenue_growth"},
    "materials":           {"profitability": "roic_or_op_margin","growth": "revenue_growth"},
    "energy_oil_gas":      {"profitability": "roic_or_op_margin","growth": "revenue_growth"},
    "tech_software":       {"profitability": "operating_margin","growth": "revenue_growth"},
    "aviation_transport":  {"profitability": "operating_margin","growth": "revenue_growth"},
    "industrials":         {"profitability": "roic_or_op_margin","growth": "revenue_growth"},
}

# Hard-coded VN30 -> sector bucket map. See spec Part 4.
VN_TICKER_TO_SECTOR: Dict[str, str] = {
    # Banks
    "VCB": "banks", "BID": "banks", "CTG": "banks", "TCB": "banks",
    "MBB": "banks", "ACB": "banks", "VPB": "banks", "HDB": "banks",
    "STB": "banks", "TPB": "banks", "VIB": "banks", "SHB": "banks",
    "LPB": "banks", "SSB": "banks",
    # Insurance
    "BVH": "insurance",
    # Real estate developers
    "VHM": "real_estate_developer",
    "VRE": "real_estate_developer",
    "VIC": "real_estate_developer",
    # Retail
    "MWG": "consumer_retail",
    # Staples
    "VNM": "consumer_staples",
    "SAB": "consumer_staples",
    "MSN": "consumer_staples",
    # Materials
    "HPG": "materials",
    "GVR": "materials",
    # Energy
    "GAS": "energy_oil_gas",
    "PLX": "energy_oil_gas",
    # Tech
    "FPT": "tech_software",
    # Aviation
    "VJC": "aviation_transport",
    # Industrials (BCM is industrial parks)
    "BCM": "industrials",
    # Brokerage
    "SSI": "financials_brokerage",
}


def lookup_sector(ticker: str) -> str:
    """Return internal sector bucket for a VN30 ticker."""
    if ticker not in VN_TICKER_TO_SECTOR:
        raise KeyError(f"{ticker} not in VN30 sector map; update sector_mapping.py")
    return VN_TICKER_TO_SECTOR[ticker]


def metric_profile(bucket: str) -> Dict[str, str]:
    """Return the OPCM Tier-2 metric choice for a sector bucket."""
    return SECTOR_METRIC_PROFILES.get(bucket, {"profitability": "operating_margin", "growth": "revenue_growth"})
