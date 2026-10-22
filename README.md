# Fund Lens India

A screener for every open-ended Direct Growth mutual fund in India: returns, calendar years,
risk and capture ratios, rolling consistency, peer ranks and side-by-side comparison.

- **App:** `docs/index.html` (served by GitHub Pages from the `docs/` folder), reading `docs/data.json`.
- **Nightly refresh:** `.github/workflows/refresh.yml` runs Mon–Sat at 23:15 IST, or on demand
  from the Actions tab → *Nightly fund data refresh* → *Run workflow*.

## Data sources
| Data | Source |
|---|---|
| Scheme list, AMC, SEBI category, latest NAV | AMFI `NAVAll.txt` |
| Full NAV history | mfapi.in |
| Equity benchmarks (Total Return Indices) | niftyindices.com |

Debt, hybrid, FoF and solution-oriented funds are compared with the equal-weighted average of their
own category, because CRISIL's indices are not freely published.

## Method (same for every fund)
- Trailing returns: point to point; under 1 year absolute, 1 year and above CAGR.
- Calendar years: 31 Dec to 31 Dec; current year is year to date.
- Risk: 36 / 60 month-end returns, annualised; risk-free rate 6.0%.
- Capture ratios: geometric average in benchmark up / down months (Morningstar method).
- Rolling 3Y: CAGR for every daily start date.

## Layout
```
engine/metrics.py          one-fund analytics (returns, risk, capture, rolling, SIP XIRR)
engine/build_app_data.py   categorises funds, assigns benchmarks, writes docs/data.json
engine/screener.py         single-category Excel screener (optional)
pipeline/fetch_data.py     downloads raw data into raw/
docs/                      the web app
```

## Not yet included
TER, AUM, fund manager, holdings, and YTM / duration for debt funds.
