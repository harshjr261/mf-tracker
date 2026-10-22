"""Fund analytics engine.

Every fund is measured the same way, so comparisons across AMCs are fair.

Conventions (chosen to match how Indian factsheets / Value Research report):
- Trailing returns: point-to-point on the last NAV on or before each date.
  Periods under 1 year are absolute; 1 year and longer are CAGR.
- Calendar-year returns: last NAV of the previous year to last NAV of the year.
- Risk ratios: monthly (month-end) returns over a trailing window (default 3 years),
  annualised (mean x 12, std x sqrt 12).
- Risk-free rate: a single setting (RF_ANNUAL), applied to every fund.
- Capture ratios: Morningstar method, geometric average of fund vs benchmark
  returns in the months the benchmark rose (up) or fell (down).
- Rolling returns: daily-start rolling CAGR over 3Y / 5Y windows.
- SIP returns: XIRR of a fixed monthly SIP on the first NAV date of each month.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

RF_ANNUAL = 0.06  # risk-free rate, ~91-day T-bill; one setting for every fund


# ---------------------------------------------------------------- loading
def load_nav_csv(path: str) -> pd.Series:
    """mfapi.in style: date (dd-mm-yyyy), nav."""
    df = pd.read_csv(path)
    s = pd.Series(df["nav"].astype(float).values, index=pd.to_datetime(df["date"], format="%d-%m-%Y"))
    return s.sort_index()[lambda x: ~x.index.duplicated()]


def load_tri_csv(path: str) -> pd.Series:
    """niftyindices style: date (dd Mon yyyy), tri."""
    df = pd.read_csv(path)
    s = pd.Series(df["tri"].astype(float).values, index=pd.to_datetime(df["date"], format="%d %b %Y"))
    return s.sort_index()[lambda x: ~x.index.duplicated()]


# ---------------------------------------------------------------- helpers
def value_on(s: pd.Series, d: pd.Timestamp):
    """Last value on or before date d (None if series starts after d)."""
    sub = s.loc[:d]
    return (sub.index[-1], sub.iloc[-1]) if len(sub) else (None, None)


def period_return(s: pd.Series, start: pd.Timestamp, end: pd.Timestamp, annualise: bool):
    d0, v0 = value_on(s, start)
    d1, v1 = value_on(s, end)
    if v0 is None or d0 < start - pd.Timedelta(days=7):  # not enough history
        return None
    r = v1 / v0
    if annualise:
        yrs = (d1 - d0).days / 365.25
        return r ** (1 / yrs) - 1
    return r - 1


def month_end_returns(s: pd.Series) -> pd.Series:
    me = s.resample("ME").last().dropna()
    return me.pct_change().dropna()


# ---------------------------------------------------------------- returns
TRAILING = [("1M", pd.DateOffset(months=1), False), ("3M", pd.DateOffset(months=3), False),
            ("6M", pd.DateOffset(months=6), False), ("1Y", pd.DateOffset(years=1), True),
            ("3Y", pd.DateOffset(years=3), True), ("5Y", pd.DateOffset(years=5), True),
            ("7Y", pd.DateOffset(years=7), True), ("10Y", pd.DateOffset(years=10), True)]


def trailing_returns(s: pd.Series, as_of: pd.Timestamp) -> dict:
    out = {}
    for label, off, ann in TRAILING:
        out[label] = period_return(s, as_of - off, as_of, ann)
    d0, v0 = s.index[0], s.iloc[0]
    d1, v1 = value_on(s, as_of)
    yrs = (d1 - d0).days / 365.25
    out["Since inception"] = (v1 / v0) ** (1 / yrs) - 1 if yrs >= 1 else v1 / v0 - 1
    return out


def calendar_returns(s: pd.Series, as_of: pd.Timestamp) -> dict:
    out = {}
    s = s.loc[:as_of]
    for y in range(s.index[0].year, as_of.year + 1):
        start = pd.Timestamp(y - 1, 12, 31)
        end = min(pd.Timestamp(y, 12, 31), as_of)
        d0, v0 = value_on(s, start)
        if v0 is None:  # first (partial) year: from first NAV
            d0, v0 = s.index[0], s.iloc[0]
        _, v1 = value_on(s, end)
        label = f"{y} YTD" if end == as_of and end.month != 12 else str(y)
        if d0.year < y or (d0.year == y and d0.month == 1 and d0.day <= 7):
            out[label] = v1 / v0 - 1
        else:
            out[f"{y} (partial)"] = v1 / v0 - 1
    return out


def rolling_returns(s: pd.Series, bm: pd.Series, years: int, as_of: pd.Timestamp) -> dict:
    s = s.loc[:as_of]
    bm = bm.reindex(s.index, method="ffill")
    n = int(round(years * 365.25))
    starts = s.index[s.index <= as_of - pd.Timedelta(days=n)]
    if len(starts) < 20:
        return {}
    ends = starts + pd.Timedelta(days=n)
    f0 = s.loc[starts].values
    f1 = s.reindex(ends, method="ffill").values
    b0 = bm.loc[starts].values
    b1 = bm.reindex(ends, method="ffill").values
    fr = (f1 / f0) ** (1 / years) - 1
    br = (b1 / b0) ** (1 / years) - 1
    ok = ~np.isnan(fr) & ~np.isnan(br)
    fr, br = fr[ok], br[ok]
    return dict(observations=int(ok.sum()), average=fr.mean(), median=float(np.median(fr)), min=fr.min(),
                max=fr.max(), pct_beat_benchmark=(fr > br).mean(), pct_negative=(fr < 0).mean(),
                pct_above_12=(fr > 0.12).mean(), bm_average=br.mean())


# ---------------------------------------------------------------- risk
def _geo_ann(r: pd.Series) -> float:
    return (np.prod(1 + r)) ** (12 / len(r)) - 1


def risk_metrics(s: pd.Series, bm: pd.Series, as_of: pd.Timestamp, years: int = 3,
                 rf: float = RF_ANNUAL) -> dict:
    end = pd.Timestamp(as_of) + pd.offsets.MonthEnd(0) if as_of.is_month_end else as_of - pd.offsets.MonthEnd(1)
    start = end - pd.DateOffset(years=years)
    fr = month_end_returns(s.loc[:end]).loc[start + pd.Timedelta(days=1):end]
    br = month_end_returns(bm.loc[:end]).reindex(fr.index)
    df = pd.concat([fr, br], axis=1, keys=["f", "b"]).dropna()
    if len(df) < years * 12 - 1:
        return {"window": f"{years}Y", "months": len(df), "note": "insufficient history"}
    f, b = df.f, df.b
    rf_m = (1 + rf) ** (1 / 12) - 1
    ann = lambda x: x.mean() * 12
    vol = f.std(ddof=1) * math.sqrt(12)
    bvol = b.std(ddof=1) * math.sqrt(12)
    downside = np.sqrt(np.mean(np.minimum(f - rf_m, 0) ** 2)) * math.sqrt(12)
    beta = np.cov(f, b, ddof=1)[0, 1] / b.var(ddof=1)
    alpha = ann(f - rf_m) - beta * ann(b - rf_m)
    active = f - b
    te = active.std(ddof=1) * math.sqrt(12)
    up, dn = b > 0, b < 0
    # drawdown on daily data inside the window
    d = s.loc[start:end]
    dd = d / d.cummax() - 1
    trough = dd.idxmin()
    peak = d.loc[:trough].idxmax()
    rec = d.loc[trough:][d.loc[trough:] >= d.loc[peak]]
    bd = bm.loc[start:end]
    return dict(
        window=f"{years}Y to {end:%d-%b-%Y}", months=len(df),
        std_dev=vol, bm_std_dev=bvol,
        sharpe=(ann(f) - rf) / vol if vol else None,
        sortino=(ann(f) - rf) / downside if downside else None,
        beta=beta, alpha=alpha,
        r_squared=np.corrcoef(f, b)[0, 1] ** 2,
        tracking_error=te,
        information_ratio=ann(active) / te if te else None,
        treynor=(ann(f) - rf) / beta if beta else None,
        upside_capture=_geo_ann(f[up]) / _geo_ann(b[up]) if up.any() else None,
        downside_capture=_geo_ann(f[dn]) / _geo_ann(b[dn]) if dn.any() else None,
        up_months=int(up.sum()), down_months=int(dn.sum()),
        pct_months_beat_bm=(f > b).mean(),
        max_drawdown=dd.min(), mdd_peak=peak, mdd_trough=trough,
        mdd_recovered=rec.index[0] if len(rec) else None,
        bm_max_drawdown=(bd / bd.cummax() - 1).min(),
    )


def max_drawdown(s: pd.Series) -> dict:
    dd = s / s.cummax() - 1
    t = dd.idxmin()
    p = s.loc[:t].idxmax()
    rec = s.loc[t:][s.loc[t:] >= s.loc[p]]
    return dict(max_drawdown=dd.min(), peak=p, trough=t, recovered=rec.index[0] if len(rec) else None,
                current_drawdown=dd.iloc[-1])


# ---------------------------------------------------------------- SIP
def xirr(cashflows: list[tuple[pd.Timestamp, float]]) -> float:
    t0 = cashflows[0][0]
    ts = np.array([(d - t0).days / 365.0 for d, _ in cashflows])
    cf = np.array([c for _, c in cashflows])
    f = lambda r: np.sum(cf / (1 + r) ** ts)
    lo, hi = -0.99, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def sip_returns(s: pd.Series, as_of: pd.Timestamp, years: int, amount: float = 10_000) -> dict | None:
    s = s.loc[:as_of]
    start = as_of - pd.DateOffset(years=years)
    if s.index[0] > start + pd.Timedelta(days=7):
        return None
    months = pd.date_range(start + pd.offsets.MonthBegin(0), as_of, freq="MS")
    units, flows = 0.0, []
    for m in months:
        nxt = s.loc[m:]
        if not len(nxt) or nxt.index[0] > as_of:
            continue
        d, nav = nxt.index[0], nxt.iloc[0]
        units += amount / nav
        flows.append((d, -amount))
    _, last = value_on(s, as_of)
    value = units * last
    flows.append((as_of, value))
    invested = -sum(c for _, c in flows[:-1])
    return dict(instalments=len(flows) - 1, invested=invested, value=value, xirr=xirr(flows))


# ---------------------------------------------------------------- one-call report
@dataclass
class FundReport:
    name: str
    as_of: pd.Timestamp
    trailing: pd.DataFrame
    calendar: pd.DataFrame
    risk: pd.DataFrame
    rolling: pd.DataFrame
    sip: pd.DataFrame
    drawdown: dict


def analyse(name: str, nav: pd.Series, bm: pd.Series, bm_name: str, as_of=None, rf=RF_ANNUAL) -> FundReport:
    as_of = pd.Timestamp(as_of) if as_of is not None else nav.index[-1]
    as_of = value_on(nav, as_of)[0]
    tr = pd.DataFrame({name: trailing_returns(nav, as_of),
                       bm_name: trailing_returns(bm.loc[nav.index[0] - pd.Timedelta(days=5):], as_of)})
    tr.loc["Since inception", bm_name] = period_return(bm, nav.index[0], as_of, True)
    tr["Excess"] = tr[name] - tr[bm_name]
    cal = pd.DataFrame({name: calendar_returns(nav, as_of)})
    bcal = {}
    for k in cal.index:
        y = int(k[:4])
        s0 = pd.Timestamp(y - 1, 12, 31) if "partial" not in k else nav.index[0]
        r = period_return(bm, s0, min(pd.Timestamp(y, 12, 31), as_of), False)
        if r is None and y == nav.index[0].year:  # benchmark history starts inside the first year
            r = period_return(bm, nav.index[0], min(pd.Timestamp(y, 12, 31), as_of), False)
        bcal[k] = r
    cal[bm_name] = pd.Series(bcal)
    cal["Excess"] = cal[name] - cal[bm_name]
    risk = pd.DataFrame({f"{y}Y": risk_metrics(nav, bm, as_of, y, rf) for y in (3, 5)})
    roll = pd.DataFrame({f"{y}Y rolling": rolling_returns(nav, bm, y, as_of) for y in (1, 3, 5)})
    sip = pd.DataFrame({f"{y}Y": sip_returns(nav, as_of, y) for y in (1, 3, 5, 10)
                        if sip_returns(nav, as_of, y)}).T
    bsip = {f"{y}Y": (sip_returns(bm, as_of, y) or {}).get("xirr") for y in (1, 3, 5, 10)}
    sip["bm_xirr"] = pd.Series(bsip)
    return FundReport(name, as_of, tr, cal, risk, roll, sip, max_drawdown(nav.loc[:as_of]))
