"""Build the web app's data file from raw NAV + benchmark data.

Usage: python3 build_app_data.py <mf_universe_nav.json.gz> <benchmarks_tri.json> <out_data.json>
"""
import gzip
import json
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd

from metrics import (calendar_returns, max_drawdown, risk_metrics, rolling_returns, sip_returns,
                     trailing_returns, value_on, period_return)

warnings.filterwarnings("ignore")

# ------------------------------------------------------------------ categories
def classify(raw_cat: str, name: str):
    """Map AMFI's mixed old/new labels to (asset class, sub-category)."""
    c = raw_cat.replace("â€™", "'").replace("’", "'")
    sub = c.split(" - ", 1)[1].strip() if " - " in c else c
    n = name.lower()
    if c.startswith("Equity Scheme"):
        if sub.startswith("ELSS"):
            return "Equity", "ELSS"
        if sub in ("Sectoral Fund", "Thematic Fund", "Sectoral/ Thematic"):
            return "Equity", "Sectoral / Thematic"
        return "Equity", {"Large & Mid Cap Fund": "Large & Mid Cap"}.get(sub, sub.replace(" Fund", ""))
    if c.startswith(("Debt Scheme", "Income/Debt")):
        m = {"Ultra Short Term Fund": "Ultra Short Duration", "Ultra Short Duration Fund": "Ultra Short Duration",
             "Ultra Short to Short Term Fund": "Low Duration", "Short Term Fund": "Short Duration",
             "Short Duration Fund": "Short Duration", "Medium Term Fund": "Medium Duration",
             "Medium Duration Fund": "Medium Duration", "Medium to Long Term Fund": "Medium to Long Duration",
             "Long Term Fund": "Long Duration", "Dynamic Term Fund": "Dynamic Bond", "Dynamic Bond": "Dynamic Bond",
             "Floating Interest Rates Fund": "Floater", "Banking and PSU Debt Fund": "Banking & PSU",
             "Banking and PSU Fund": "Banking & PSU", "10-year Constant Maturity Gilt Fund": "Gilt 10Y Constant",
             "Sectoral Fund": "Other Debt"}
        return "Debt", m.get(sub, sub.replace(" Fund", ""))
    if c.startswith("Hybrid Scheme"):
        if "Balanced Advantage" in sub or "Dynamic Asset" in sub:
            return "Hybrid", "Balanced Advantage / DAA"
        if sub.startswith("Multi Asset"):
            return "Hybrid", "Multi Asset"
        if sub.startswith("Equity Savings"):
            return "Hybrid", "Equity Savings"
        return "Hybrid", sub.replace(" Fund", "")
    if "Retirement" in c:
        return "Solution Oriented", "Retirement"
    if "Children" in c:
        return "Solution Oriented", "Children's"
    if c.startswith("Life Cycle"):
        return "Solution Oriented", "Life Cycle"
    if "ETF" in c or " etf" in n:
        if "Gold" in c or "gold" in n:
            return "Index Funds & ETFs", "Gold ETF"
        if "Silver" in c or "silver" in n:
            return "Index Funds & ETFs", "Silver ETF"
        if "Debt" in c or re.search(r"g-sec|gilt|bond|sdl|liquid|1d rate|psu bond|bharat bond|crisil|t-bill|money market", n):
            return "Index Funds & ETFs", "Debt ETF"
        return "Index Funds & ETFs", "Equity ETF"
    if "Index Funds" in c:
        if "Debt" in c or re.search(r"g-sec|gilt|sdl|bond|crisil|t-bill|psu|aaa|ibx|debt|liquid|maturity", n):
            return "Index Funds & ETFs", "Debt Index Fund"
        if "Hybrid" in c:
            return "Index Funds & ETFs", "Hybrid Index Fund"
        return "Index Funds & ETFs", "Equity Index Fund"
    if "Overseas" in c:
        return "Fund of Funds", "FoF Overseas"
    if "FoF" in c or "Fund of Funds" in c:
        return "Fund of Funds", "FoF Domestic"
    return "Other", sub


THEMES = [  # (regex on name, theme label, benchmark TRI)
    (r"bank|financial|finserv|bfsi", "Banking & Financial", "NIFTY FINANCIAL SERVICES"),
    (r"tech|digital|it fund|teck|innovation", "Technology", "NIFTY IT"),
    (r"pharma|health", "Pharma & Healthcare", "NIFTY PHARMA"),
    (r"infra|infrastructure|power|housing|real estate", "Infrastructure", "NIFTY INFRASTRUCTURE"),
    (r"consum|fmcg|retail|lifestyle", "Consumption", "NIFTY INDIA CONSUMPTION"),
    (r"psu|public sector|pse", "PSU", "NIFTY PSE"),
    (r"mnc", "MNC", "NIFTY MNC"),
    (r"manufactur|make in india", "Manufacturing", "NIFTY INDIA MANUFACTURING"),
    (r"energy|oil|natural resource|commodit", "Energy & Commodities", "NIFTY COMMODITIES"),
    (r"defen", "Defence", "NIFTY INDIA DEFENCE"),
    (r"auto|mobility|transport|logistic|ev ", "Auto & Mobility", "NIFTY AUTO"),
    (r"servic", "Services", "NIFTY SERVICES SECTOR"),
    (r"dividend yield|dividend", "Dividend Yield", "NIFTY DIVIDEND OPPORTUNITIES 50"),
    (r"global|international|us |nasdaq|world|overseas|china|japan|asia|emerging", "International", None),
    (r"esg|sustainab", "ESG", "NIFTY 500"),
    (r"business cycle|cycle", "Business Cycle", "NIFTY 500"),
    (r"momentum|quant|factor|alpha", "Quant & Momentum", "NIFTY 500"),
    (r"special situation|opportunit|innovative|emerging", "Special Situations", "NIFTY 500"),
]

EQUITY_BM = {"Large Cap": "NIFTY 100", "Mid Cap": "NIFTY MIDCAP 150", "Small Cap": "NIFTY SMALLCAP 250",
             "Large & Mid Cap": "NIFTY LARGEMIDCAP 250", "Multi Cap": "NIFTY500 MULTICAP 50:25:25",
             "Flexi Cap": "NIFTY 500", "Focused": "NIFTY 500", "ELSS": "NIFTY 500", "Value": "NIFTY 500",
             "Contra": "NIFTY 500", "Dividend Yield": "NIFTY DIVIDEND OPPORTUNITIES 50"}

INDEX_KEYS = [  # passive funds: tracked index from name -> (group label, TRI if available)
    (r"smallcap 250|small ?cap 250", "Nifty Smallcap 250", "NIFTY SMALLCAP 250"),
    (r"midcap 150|mid ?cap 150", "Nifty Midcap 150", "NIFTY MIDCAP 150"),
    (r"largemidcap 250|large ?mid ?cap 250", "Nifty LargeMidcap 250", "NIFTY LARGEMIDCAP 250"),
    (r"next 50", "Nifty Next 50", None),
    (r"nifty 100(?! low)|nifty100(?! low)", "Nifty 100", "NIFTY 100"),
    (r"nifty 500(?! value|momentum|multicap)|nifty500(?! value| momentum| multicap)", "Nifty 500", "NIFTY 500"),
    (r"total market", "Nifty Total Market", "NIFTY TOTAL MARKET"),
    (r"nifty bank|bank nifty|nifty private bank|psu bank", "Banking index", None),
    (r"nifty it|nifty tech", "Nifty IT / Tech", "NIFTY IT"),
    (r"sensex", "BSE Sensex", None),
    (r"nifty 50(?! value| equal| arbitrage| hybrid| low)|nifty50(?! value| equal| low)|nifty fifty", "Nifty 50", "NIFTY 50"),
]

# ------------------------------------------------------------------ loading
def parse_hist(s: str) -> pd.Series:
    if not s:
        return pd.Series(dtype=float)
    parts = [p.split(":") for p in s.split(" ")]
    idx = pd.to_datetime([p[0] for p in parts], format="%Y%m%d")
    v = pd.Series([float(p[1]) for p in parts], index=idx)
    v = v[(v > 0)]
    return v[~v.index.duplicated()].sort_index()


def clean_series(s: pd.Series) -> pd.Series:
    """Drop obvious data errors: single-day jumps >40% that fully reverse next day."""
    if len(s) < 3:
        return s
    r = s.pct_change()
    bad = (r.abs() > 0.4) & (r.shift(-1).abs() > 0.28) & (np.sign(r) != np.sign(r.shift(-1)))
    s = s[~bad]
    # unit splits / NAV rebases (common in ETFs): a one-day move beyond -50% / +100% that does not reverse
    r = s.pct_change()
    for d in r.index[(r < -0.5) | (r > 1.0)]:
        i = s.index.get_loc(d)
        ratio = s.iloc[i] / s.iloc[i - 1]
        s.iloc[:i] = s.iloc[:i] * ratio
    return s


def bm_label(k):
    words = {"NIFTY": "Nifty", "NIFTY500": "Nifty 500", "SMALLCAP": "Smallcap", "MIDCAP": "Midcap",
             "LARGEMIDCAP": "LargeMidcap", "MULTICAP": "Multicap", "INDIA": "India", "FINANCIAL": "Financial",
             "SERVICES": "Services", "CONSUMPTION": "Consumption", "INFRASTRUCTURE": "Infrastructure",
             "MANUFACTURING": "Manufacturing", "COMMODITIES": "Commodities", "DEFENCE": "Defence", "AUTO": "Auto",
             "BANK": "Bank", "PHARMA": "Pharma", "ENERGY": "Energy", "SECTOR": "Sector", "TOTAL": "Total",
             "MARKET": "Market", "DIVIDEND": "Dividend", "OPPORTUNITIES": "Opportunities", "VALUE": "Value"}
    return " ".join(words.get(w, w) for w in k.split()) + " TRI"


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def first_date(txt):
    """First date in a free-text 'managing since' field (24/05/2013, 01-Sep-2025, Since Jan 2017, May 16, 2022)."""
    if not txt:
        return None
    t = txt.lower()
    pats = [(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", lambda m: (int(m[3]), int(m[2]), int(m[1]))),
            (r"(\d{1,2})[\s-]*([a-z]{3})[a-z]*[\s,-]*(\d{4})", lambda m: (int(m[3]), MONTHS.get(m[2]), int(m[1]))),
            (r"([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", lambda m: (int(m[3]), MONTHS.get(m[1]), int(m[2]))),
            (r"([a-z]{3})[a-z]*[\s,'-]+(\d{4})", lambda m: (int(m[2]), MONTHS.get(m[1]), 1))]
    best = None
    for rx, f in pats:
        m = re.search(rx, t)
        if m:
            try:
                y, mo, d = f(m)
                if mo and 1990 < y < 2100 and 1 <= mo <= 12:
                    c = (m.start(), pd.Timestamp(y, mo, min(d, 28)))
                    best = c if best is None or c[0] < best[0] else best
            except (ValueError, TypeError):
                pass
    return best[1] if best else None


TITLE_RX = re.compile(r"^(?:mr|ms|mrs|dr|ca|shri|smt)\.?\s+", re.I)


def split_managers(fm):
    """'Mr. Rajeev Thakkar, Ms. Mansi Kariya and Mr Tejas Soman' -> ['Rajeev Thakkar', 'Mansi Kariya', 'Tejas Soman']"""
    if not fm:
        return []
    import html as _html
    fm = _html.unescape(_html.unescape(fm)).replace("\u2019", "'").replace('"', " ")
    fm = re.sub(r"Fund\s*Manager\s*\d+\s*[-:]", ",", fm, flags=re.I)          # 'Fund Manager 1 -'
    fm = re.sub(r"\s+-\s*(?:Primary|Secondary|Co-?\s*Fund\s*Manager|Co-?manager)\b.*?(?=,|$)", ",", fm, flags=re.I)
    fm = re.sub(r"\([^)]*\)?", ",", fm)                                     # '(w.e.f ...)', '(Assistant ...' 
    fm = re.sub(r"\bFor\s+[A-Za-z ]+?:", ",", fm, flags=re.I)                # 'For Equity :'
    fm = re.sub(r"\b(?:Equity|Debt|Arbitrage|Overseas|Gold|Commodit\w*)\s*[-:]\s*", ",", fm, flags=re.I)  # 'Equity - Mr. X; Debt - Mr. Y'
    fm = re.sub(r"FM\s*-?\s*\d+\s*[-:]?", ",", fm)                         # 'FM 1 -', 'FM-2', 'MattaFM-2'
    fm = re.sub(r"\b(?:Assistant\s+)?Fund\s*manager.*?(?=,|$)", ",", fm, flags=re.I)
    fm = re.sub(r"(?:^|,)\s*\d+\.\s*", ",", fm)                            # '1. Name , 2. Name'
    fm = re.sub(r"\bNot Applicable\b|\bN\.?A\.?\b", ",", fm, flags=re.I)
    fm = re.sub(r"\b(Mr|Ms|Mrs|Dr)\.(?=\S)", r"\1. ", fm)                  # 'Mr.Ihab' -> 'Mr. Ihab'
    parts = re.split(r",|;|\n|\band\b|&|/|\s{2,}|(?<=[a-z])\s+(?=(?:Mr|Ms|Mrs|Dr)\.?\s)", fm)
    out = []
    for p in parts:
        p = re.sub(r"\(.*?\)", "", p).strip(" .-:")
        p = TITLE_RX.sub("", p).strip(" .")
        p = re.sub(r"\s+", " ", p)
        if p.lower() in ("associate", "foreign", "dedicated", "overseas"):
            continue
        if 3 <= len(p) <= 40 and re.match(r"^[A-Za-z][A-Za-z .'-]+$", p) and len(p.split()) <= 5 and not re.search(r"\b(fund|manager|since|equity|debt|overseas|primary|co)\b", p, re.I):
            out.append(p.title())
    return list(dict.fromkeys(out))


def all_dates(t):
    """Every date in free text, in order of appearance: [(pos, Timestamp)]."""
    t = t.lower()
    t = re.sub(r"fm\s*-?\s*\d+", lambda m: " " * len(m.group(0)), t)  # hide 'FM 2' labels so '2' is never read as a day
    pats = [r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?!\d)", r"(\d{1,2})(?:st|nd|rd|th)?[\s-]*([a-z]{3})[a-z]*[\s,-]*(\d{4}|\d{2})(?!\d)(?!,?\s*\d{4})",
            r"([a-z]{3})[a-z]*\.?\s*(\d{1,2}),?\s*(\d{4})", r"([a-z]{3})[a-z]*[\s,'-]+(\d{4})"]
    found, taken = [], []
    for k, rx in enumerate(pats):
        for m in re.finditer(rx, t):
            if any(m.start() < e and m.end() > st for st, e in taken):
                continue
            try:
                if k == 0:
                    y, mo, d = int(m[3]), int(m[2]), int(m[1])
                elif k == 1:
                    y, mo, d = int(m[3]), MONTHS.get(m[2]), int(m[1])
                elif k == 2:
                    y, mo, d = int(m[3]), MONTHS.get(m[1]), int(m[2])
                else:
                    y, mo, d = int(m[2]), MONTHS.get(m[1]), 1
                if y < 100:
                    y += 2000 if y <= 40 else 1900
                if mo and 1990 < y < 2100:
                    found.append((m.start(), pd.Timestamp(y, mo, min(max(d, 1), 28))))
                    taken.append((m.start(), m.end()))
            except (ValueError, TypeError):
                pass
    return sorted(found)


def manager_since(name, fm_since, idx=0, count=1, inception=None):
    """Start date for one manager from AMFI's free-text 'managing since' field.
    Handles per-name dates, 'FM 1 / FM 2' positional labels, ordered date lists and 'since inception'."""
    if not fm_since:
        return None
    import html as _html
    t = _html.unescape(_html.unescape(fm_since))
    if re.fullmatch(r"\s*[3-5]\d{4}(?:\.0)?\s*", t):  # Excel serial date, e.g. '46020'
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(float(t)))
    t = re.sub(r"Fund\s*Manager\s*-?\s*(\d)", r"FM \1", t, flags=re.I)
    t = re.sub(r"FM\s*-?\s*(\d+)\s*(?:&|and|,)\s*(\d+)", r"FM \1 FM \2", t, flags=re.I)
    tl = t.lower()
    last = name.split()[-1].lower()
    i = tl.find(last)
    if i >= 0:
        seg = t[i:i + 90]
        if re.search(r"since\s+inception", seg, re.I) and inception is not None:
            return inception
        ds = all_dates(seg)
        if ds:
            return ds[0][1]
    if count == 1 and re.search(r"since\s+inception", t, re.I) and not all_dates(t) and inception is not None:
        return inception
    dates = all_dates(t)
    labels = [(m.start(), int(m.group(1))) for m in re.finditer(r"FM\s*-?\s*(\d+)", t, re.I)]
    if labels and not dates and re.search(r"inception", t, re.I) and inception is not None:
        return inception
    if labels and dates:
        label_first = labels[0][0] < dates[0][0]
        for j, (pos, k) in enumerate(labels):
            if k != idx + 1:
                continue
            if label_first:
                nxt = labels[j + 1][0] if j + 1 < len(labels) else len(t) + 1
                if re.search(r"inception", t[pos:nxt], re.I) and inception is not None:
                    return inception
                cand = [d for p_, d in dates if pos < p_ < nxt]
            else:
                cand = [d for p_, d in dates if p_ < pos][-1:]
            return cand[0] if cand else None
        return None
    if len(dates) == 1:
        return dates[0][1]
    if count > 1 and len(dates) == count:
        return dates[idx][1]
    return None


def base_name(n):
    n = n.replace(" (plan inferred: Direct)", "")
    n = re.split(r" - | -|- ", n)[0]
    return re.sub(r"[^a-z0-9]", "", n.lower().replace("fund", ""))


def main(nav_gz, bm_path, out, info_path=None):
    d = json.load(gzip.open(nav_gz))
    sinfo, sstats = {}, {}
    if info_path and os.path.exists(info_path):
        j = json.load(open(info_path))
        sinfo, sstats = j.get("info", {}), j.get("stats", {})
    bms_raw = json.load(open(bm_path))
    bms = {k: pd.Series([v for _, v in rows], index=pd.to_datetime([dd for dd, _ in rows], format="%d %b %Y"))
           .sort_index()[lambda x: ~x.index.duplicated()] for k, rows in bms_raw.items()}

    # ---- universe with de-duplication of inferred-plan rows
    meta = pd.DataFrame(d["meta"], columns=["code", "name", "amc", "rawcat", "isin"])
    meta["inferred"] = meta.name.str.contains(r"\(plan inferred")
    meta["key"] = meta.amc + "|" + meta.name.map(base_name)
    main_keys = set(meta[~meta.inferred].key)
    meta = meta[~(meta.inferred & meta.key.isin(main_keys))]
    meta = meta[~meta.name.str.contains("Segregat", case=False)]
    meta["is_etf"] = meta.rawcat.str.contains("ETF") | meta.name.str.contains(r"\bETF\b", case=False)
    meta["name"] = np.where(meta.inferred & meta.is_etf, meta.name.str.replace(" (plan inferred: Direct)", "", regex=False), meta.name)
    meta["name"] = meta.name.str.replace(" (plan inferred: Direct)", " ·plan inferred", regex=False)
    cls = meta.apply(lambda r: classify(r.rawcat, r["name"]), axis=1)
    meta["asset"] = [c[0] for c in cls]
    meta["cat"] = [c[1] for c in cls]

    navs = {}
    for c in meta.code:
        s = clean_series(parse_hist(d["hist"].get(str(c), "")))
        if len(s) >= 5:
            navs[c] = s
    meta = meta[meta.code.isin(navs)]
    latest = max(s.index[-1] for s in navs.values())
    meta = meta[[navs[c].index[-1] >= latest - pd.Timedelta(days=21) for c in meta.code]]  # active only
    as_of = latest

    # ---- drop pre-conversion history: a few schemes were debt-like funds before becoming equity funds
    # (e.g. Quant Small Cap before 2019). Equity returns and risk must not include that stretch.
    n500 = bms.get("NIFTY 500")
    if n500 is not None:
        bm_m = n500.resample("ME").last().pct_change()
        for c in meta[meta.asset == "Equity"].code:
            fm = navs[c].resample("ME").last().pct_change()
            j = pd.concat([fm, bm_m], axis=1, join="inner").dropna()
            if len(j) < 48:
                continue
            cut = None
            for t in range(24, len(j)):
                w = j.iloc[t - 24:t]
                if w.iloc[:, 0].corr(w.iloc[:, 1]) < 0.3 and w.iloc[:, 0].std() < 0.015:
                    cut = j.index[t - 1]
            if cut is not None:
                navs[c] = navs[c][navs[c].index > cut]
                print(f"trimmed pre-conversion history: {c} starts {navs[c].index[0].date()}")

    # ---- benchmark assignment
    def assign(r):
        n = r["name"].lower()
        if r.asset == "Equity":
            if r["cat"] == "Sectoral / Thematic":
                for rx, theme, bm in THEMES:
                    if re.search(rx, n):
                        return theme, bm
                return "Other Thematic", "NIFTY 500"
            return "", EQUITY_BM.get(r["cat"])
        if r.asset == "Index Funds & ETFs" and r["cat"] in ("Equity Index Fund", "Equity ETF"):
            for rx, grp, bm in INDEX_KEYS:
                if re.search(rx, n):
                    return grp, bm
            return "Other index", None
        return "", None
    a = meta.apply(assign, axis=1)
    meta["theme"] = [x[0] for x in a]
    meta["bm"] = [x[1] for x in a]

    # ---- category-average indices (equal-weight daily returns) for categories without a TRI
    def cat_index(codes):
        rets = pd.concat([navs[c].pct_change() for c in codes], axis=1)
        avg = rets.mean(axis=1, skipna=True).dropna()
        cnt = rets.notna().sum(axis=1).reindex(avg.index)
        avg = avg[cnt >= 2]
        return (1 + avg).cumprod() * 100 if len(avg) else None
    cat_idx = {}
    for (asset, cat), g in meta.groupby(["asset", "cat"]):
        idx = cat_index(list(g.code))
        if idx is not None:
            cat_idx[f"{asset}|{cat}"] = idx

    rows, series, mgr_book = [], {}, {}
    for _, r in meta.iterrows():
        s = navs[r.code]
        bml, bm = None, None
        if r.bm and r.bm in bms:
            bml, bm = bm_label(r.bm), bms[r.bm]
        elif f"{r.asset}|{r["cat"]}" in cat_idx:
            bml, bm = f"{r['cat']} category average", cat_idx[f"{r.asset}|{r["cat"]}"]
        d_last, nav_last = value_on(s, as_of)
        tr = trailing_returns(s, d_last)
        cal = {k: v for k, v in calendar_returns(s, d_last).items() if "partial" not in k and k >= "2016"}
        rec = dict(code=int(r.code), name=re.sub(r"\s+", " ", r["name"]).strip(), amc=r.amc, asset=r.asset,
                   cat=r["cat"], theme=r.theme, bm=bml, inferred=bool(r.inferred and not r.is_etf),
                   start=s.index[0].strftime("%Y-%m-%d"), age=round((d_last - s.index[0]).days / 365.25, 2),
                   nav=round(nav_last, 4), navDate=d_last.strftime("%Y-%m-%d"),
                   r={k: tr[k] for k in ["1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y", "Since inception"]},
                   cal=cal)
        si = sinfo.get(str(r.code))
        if si:
            ter = si.get("ter") or {}
            fm_since = first_date(si.get("fmSince"))
            rec["info"] = {k: v for k, v in dict(
                aum=(si.get("aum") or {}).get("cr"), aumP=(si.get("aum") or {}).get("period"),
                terD=ter.get("dBER"), terDt=ter.get("dTER"), terR=ter.get("rBER"), terRt=ter.get("rTER"), terDate=ter.get("date"),
                fm=si.get("fm"), fmSince=si.get("fmSince"),
                fmYrs=round((d_last - fm_since).days / 365.25, 1) if fm_since is not None and fm_since <= d_last else None,
                bm1=si.get("bm1"), exitLoad=si.get("exitLoad"), risk=si.get("risk"),
                sid=si.get("sid") if si.get("fm") or si.get("bm1") else None).items() if v not in (None, "", "NA", "N.A.")}
        mgrs = []
        names = split_managers((si or {}).get("fm"))
        for k_, nm in enumerate(names):
            since = manager_since(nm, (si or {}).get("fmSince"), k_, len(names), s.index[0])
            if since is None or since > d_last:
                mgrs.append({"n": nm}); continue
            start = max(since, s.index[0])
            yrs = (d_last - start).days / 365.25
            ann = yrs >= 1
            rec_m = {"n": nm, "since": since.strftime("%Y-%m-%d"), "yrs": round((d_last - since).days / 365.25, 1),
                     "f": period_return(s, start, d_last, ann), "ann": ann}
            if bm is not None:
                rec_m["b"] = period_return(bm, start, d_last, ann)
            ci = cat_idx.get(f"{r.asset}|{r['cat']}")
            if ci is not None:
                rec_m["c"] = period_return(ci, start, d_last, ann)
            mgrs.append(rec_m)
            mgr_book.setdefault(f"{nm}|{r.amc}", []).append(int(r.code))
        if mgrs:
            rec["mgr"] = mgrs
        dd = max_drawdown(s)
        rec["mdd"] = dd["max_drawdown"]
        rec["curDD"] = dd["current_drawdown"]
        if bm is not None:
            btr = trailing_returns(bm.loc[:as_of], d_last)
            rec["br"] = {k: btr[k] for k in ["1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y"]}
            rec["bcal"] = {k: period_return(bm, pd.Timestamp(int(k[:4]) - 1, 12, 31),
                                            min(pd.Timestamp(int(k[:4]), 12, 31), d_last), False) for k in cal}
            for yrs in (3, 5):
                rk = risk_metrics(s, bm, d_last, yrs)
                if "std_dev" in rk:
                    rec[f"k{yrs}"] = {k: rk[k] for k in ["std_dev", "sharpe", "sortino", "beta", "alpha", "r_squared",
                                                         "tracking_error", "information_ratio", "upside_capture",
                                                         "downside_capture", "max_drawdown", "pct_months_beat_bm"]}
            r3 = rolling_returns(s, bm, 3, d_last)
            if r3.get("observations", 0) >= 250:
                rec["roll3"] = {k: r3[k] for k in ["average", "median", "min", "max", "pct_beat_benchmark", "pct_negative"]}
        else:  # no benchmark at all: absolute risk only
            me = s.resample("ME").last().pct_change().dropna().iloc[-36:]
            if len(me) >= 35:
                vol = me.std() * np.sqrt(12)
                rec["k3"] = {"std_dev": vol, "sharpe": (me.mean() * 12 - 0.06) / vol if vol else None}
        for y in (3, 5):
            sp = sip_returns(s, d_last, y)
            if sp:
                rec[f"sip{y}"] = sp["xirr"]
        rows.append(rec)
        me = s.resample("ME").last().dropna()
        series[int(r.code)] = [me.index[0].strftime("%Y-%m"), [round(float(x), 4) for x in me.values]]

    bench_series = {}
    for k, b in list(bms.items()):
        lab = bm_label(k)
        me = b.resample("ME").last().dropna()
        bench_series[lab] = [me.index[0].strftime("%Y-%m"), [round(float(x), 2) for x in me.values]]
    for k, b in cat_idx.items():
        me = b.resample("ME").last().dropna()
        bench_series[f"{k.split('|')[1]} category average"] = [me.index[0].strftime("%Y-%m"), [round(float(x), 3) for x in me.values]]

    def rnd(o):
        if isinstance(o, dict):
            return {k: rnd(v) for k, v in o.items() if v is not None and not (isinstance(v, float) and np.isnan(v))}
        if isinstance(o, (float, np.floating)):
            return None if np.isnan(o) else round(float(o), 5)
        return o
    out_obj = dict(asOf=as_of.strftime("%Y-%m-%d"), rf=0.06, infoStats=sstats, funds=[rnd(x) for x in rows], managers={k: v for k, v in mgr_book.items()},
                   series=series, bench=bench_series,
                   sources=["AMFI NAVAll (scheme list, categories)", "mfapi.in (NAV history)",
                            "niftyindices.com (Total Return Indices)",
                            "AMFI TER disclosures, scheme AUM and SEBI Scheme Summary Documents"])
    json.dump(out_obj, open(out, "w"), separators=(",", ":"))
    print("funds", len(rows), "as_of", as_of.date())
    print(meta.groupby(["asset", "cat"]).size().to_string())


if __name__ == "__main__":
    try:
        main(*sys.argv[1:5])
    except Exception as e:
        import traceback
        tb = traceback.format_exc().strip().splitlines()
        print(f"::error title=build_app_data failed::{type(e).__name__}: {e} | " + " | ".join(tb[-4:]))
        raise
