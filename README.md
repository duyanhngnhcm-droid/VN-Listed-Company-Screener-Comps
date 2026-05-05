# VN30 Listed Company Screener

Working link: https://vn-listed-company-screener-comps-2z4tzgdb6d4oylunhudomu.streamlit.app/

A Streamlit web app that screens HOSE's **VN30 Index** constituents using two
sector-aware composite scorecards (banks vs. non-financials), and surfaces a
global peer set for any ranked name via the OPCM (Operation > Performance >
Credit > Market) cascade.

This is a **fundamentals research tool**, not a live trading dashboard. Data
is refreshed on demand via the Refresh button (cached 24h for fundamentals,
1h for prices).

---

## Quick start

```bash
pip install -r requirements.txt
streamlit run vn30_screener.py
```

The app opens on the **Screener** tab with the Non-financials scorecard
selected by default. Click "Refresh data" (top toolbar) on first load to
populate vnstock data. Subsequent loads use the 24h cache.

---

## Repository layout

```
vn30_screener.py          # Streamlit entry point — tab orchestration + cache wrapper
data_pipeline.py          # vnstock fetch logic, caching, validation, diagnostics
metrics.py                # CAGR, ROE, ROIC, EBITDA margin, FCF yield, NIM, CIR ratios
scoring.py                # rank-based + z-score composite, weight-aware, scorecard split
weight_panel.py           # sidebar UI for weight customization
ui_screener.py            # Tab 1: ranked screener
ui_deep_dive.py           # Tab 2: top performers cards w/ score breakdown
ui_global_peers.py        # Tab 3: OPCM peer comparison
peer_screener.py          # OPCM cascade implementation
peer_pools.py             # hand-curated candidate ticker pools by sector
sector_mapping.py         # VN30 ticker → internal sector bucket
currency_normalizer.py    # FX + minor-unit handling (GBp etc.)
config.py                 # VN30 list, default weights, FX fallback, constants
requirements.txt
README.md
```

---

## Methodology

### Universe
HOSE VN30 (30 names): 14 banks, 16 non-financials. The list is
**hardcoded in `config.py`** with the rebalance date in the header comment.
HOSE rebalances quarterly (Jan / Apr / Jul / Oct) — update the list each
cycle and bump the comment.

### Scorecards
Two separate cohorts. Cross-scorecard comparisons are **never displayed**:
ranking a bank against a non-financial is not analytically valid.

#### Non-financials (16 names) — default weights

| Pillar | Metric | Default |
|---|---|---|
| Growth | Revenue CAGR 3y | 25% |
| Profitability | ROE | 15% |
|  | ROIC | 10% |
|  | EBITDA margin | 10% |
| Cash & Value | FCF yield | 20% |
|  | P/E | 10% |
|  | P/B | 10% |

Quality and value weighted equally because either alone is incomplete (quality
without price = beauty contest; value without quality = value trap). Growth
weighted moderately because Vietnamese mid-cap growth is noisy. ROA omitted
to avoid collinearity with ROE.

#### Banks (14 names) — default weights

| Pillar | Metric | Default |
|---|---|---|
| Growth | Loan growth 3y | 20% |
| Profitability | ROE | 20% |
|  | NIM | 10% |
|  | CIR (inverted) | 10% |
| Asset Quality | NPL (inverted) | 20% |
| Value | P/B | 15% |
|  | Dividend yield | 5% |

ROE is the cleanest signal of bank franchise quality, so highest single-metric
weight. Asset quality (NPL) gets explicit pillar weight because a high-growth
bank with bad loans destroys value faster than a moderate-growth bank with
clean loans. P/B is the primary bank valuation multiple (P/E is distorted by
provisions).

### Scoring methods

- **Rank-based (default).** Each metric ranks 1..N within scorecard. Lower-
  is-better metrics (P/E, P/B, CIR, NPL) ranked ascending. Companies with
  N/A on a metric receive the **median rank** for that metric (avoids double-
  penalising missing data). Weighted sum = composite (lower is better).

- **Z-score (toggle).** Per-metric z = (value − cohort mean)/σ, winsorized
  at 5/95th percentile. Sign flipped for lower-is-better metrics. Missing →
  z = 0 (cohort mean). Composite = weighted sum (higher is better).

### Weight customization

Sidebar sliders override defaults per scorecard. Per-metric cap = 60% to
prevent the composite collapsing to a single-metric ranking. Setting all
weights to 0 disables the recompute button. Custom weights persist via
`st.session_state` for the session; full page reload restores defaults
(intentional — prevents "I changed weights three months ago and forgot").

### Edge cases (handled in code)

- Negative equity → ROE undefined → N/A
- Negative net income → P/E undefined → N/A
- Missing capex → fall back to operating-CF yield; tag the row
- Fewer than 3y of history → CAGR N/A; rank with available metrics
- Revenue jump > 5x YoY → flagged for manual review
- Real estate developers (VHM, VIC, VRE) → tagged for project-cycle volatility
- SSI (brokerage) and BVH (insurance) → flagged on the non-financials card
- Thin-float names (FF < 20%) → flagged in output

### OPCM (global peers)

A strict **Operation > Performance > Credit > Market** filter cascade:

1. **Operation** (hard gate): same internal sector bucket; geography tier
   (ASEAN-6 → broader Asia-EM → GCC/LatAm fallback); size band ±1σ in
   log market-cap (auto-relax to ±1.5σ if <5 survive).
2. **Performance** (rank, top 12): sector-aware profitability + growth
   z-score similarity. Composite = 0.6 × profitability + 0.4 × growth.
3. **Credit** (top 10, **skipped for banks**): interest-coverage distress
   floor 1.5×; D/E σ-band similarity. Banks skipped because yfinance lacks
   CET1/NPL for ASEAN — the framework's biggest weakness for VN30 (14/30
   are banks).
4. **Market** (hard filters): ADV ≥ $1M USD. Analyst coverage opt-in
   only (yfinance's `numberOfAnalystOpinions` is unreliable for ASEAN).

All monetary fields normalized to USD before comparison. **Trading currency
≠ reporting currency** is tracked explicitly (HK-listed Chinese firms trade
HKD, report CNY). Minor-unit listings (GBp/ZAc/ILA) divided by 100 BEFORE FX
conversion. Unitless ratios (P/E, P/B, ROE, margins) **never** converted.

The output is a target-highlighted comp table + **implied valuation range**
(25th–75th percentile of peer multiples). Never a single-point fair value.

---

## Quarterly maintenance

1. **Update VN30 list** in `config.py::VN30_CONSTITUENTS` after each HOSE
   rebalance (Jan, Apr, Jul, Oct). Keep the rebalance date current in the
   header comment.
2. **Verify peer pools** in `peer_pools.py` quarterly. yfinance occasionally
   renames ticker suffixes (`.SI` ↔ no-suffix is common); broken tickers
   show up in the Diagnostics panel.
3. **Refresh FX fallbacks** in `config.py::FX_FALLBACK_PER_USD` annually.
   Live FX is fetched first; the fallback only kicks in when yfinance fails.

---

## Troubleshooting

- **"vnstock import failed" on startup.** `pip install vnstock --upgrade`.
  vnstock relies on regional data endpoints that occasionally change schema.
- **Many tickers in the Fetch failures diagnostic panel.** Try VCI vs.
  TCBS source preference (the pipeline already alternates) or wait —
  rate limits are common.
- **Empty peer table.** yfinance is rate-limiting. Wait 10 minutes; the
  cache TTL is 24h so a successful fetch sticks.
- **Streamlit "scriptrunner" errors after editing weights.** Hard-reload
  the browser; `st.rerun()` doesn't always pick up state changes mid-script.

---

## Known limitations

1. **VN30 quarterly rebalances** — must be updated each Jan/Apr/Jul/Oct.
2. **Bank NPL coverage in vnstock is patchy.** Banks with missing NPL have
   the asset-quality pillar redistributed proportionally during scoring.
3. **OPCM banks gap.** yfinance lacks CET1/NPL/tier-1 ratios for ASEAN
   banks; Tier 3 (Credit) is skipped for banks. Largest framework weakness
   for VN30 since 14/30 names are banks.
4. **SSI flagged on non-financials.** Only brokerage in VN30. EBITDA
   margin and FCF yield are noisy for asset-light financials. Down-weight
   these in the customization panel when scoring SSI.
5. **BVH flagged on non-financials.** Only insurer in VN30. Combined ratio
   and embedded value are the analytically correct metrics; neither in
   vnstock. v1 uses standard metric set with caveat.
6. **Real estate developers** (VHM, VIC, VRE) have project-cycle revenue
   volatility that distorts EBITDA margin and FCF yield YoY.
7. **Thin-float names** (BID 4%, GVR 4%, BCM 5%, GAS 5%, PLX 10%, SAB 11%,
   VCB 11%, CTG 15%) — multiples may not reflect true supply-demand.
8. **vnstock VCI/TCBS coverage** is good for VN30 specifically (most-covered
   universe) but expect occasional N/A on smaller-cap or recently-listed names.
9. **ROIC formula** uses operating-ROIC convention (NOPAT / invested capital,
   IC = total debt + equity − cash). Other conventions exist (e.g., excluding
   goodwill); choice is documented inline in `metrics.py`.
10. **VND-denominated metrics** not adjusted for inflation (~3–4% Vietnam
    CPI). Nominal CAGR overstates real growth.
11. **No currency hedging in valuation.** Foreign investors face VND
    depreciation risk not captured. P/E and P/B are local-currency views.
12. **Composite scoring is opinionated.** Default weights reflect specific
    analytical choices documented above. The customization panel openly
    admits this dependency.
13. **Cross-scorecard comparisons are not valid.** A non-financial #1 and a
    bank #1 are two separate rankings, never combined.

---

## License & disclaimer

For research use. Not investment advice. Data quality depends on third-party
sources (vnstock, yfinance) and may be incorrect. Always verify against
primary filings before relying on any output.
