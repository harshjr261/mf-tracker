"""Nightly data pull: AMFI scheme list + NAV history (mfapi.in) + Nifty Total Return Indices.

Writes:
  raw/mf_universe_nav.json.gz   {"meta": [[code, name, amc, amfi_category, isin], ...],
                                 "hist": {code: "YYYYMMDD:nav YYYYMMDD:nav ..."}}
  raw/benchmarks_tri.json       {index_name: [["DD Mon YYYY", value], ...]}

If a benchmark download fails, the previous file is kept so the build still runs.
"""
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import os
import re
import sys
import time

import requests

RAW = os.path.join(os.path.dirname(__file__), "..", "raw")
os.makedirs(RAW, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (fund-lens nightly refresh)"}

TRI_NAMES = ["NIFTY 50", "NIFTY 100", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250", "NIFTY LARGEMIDCAP 250", "NIFTY 500",
             "NIFTY500 MULTICAP 50:25:25", "NIFTY BANK", "NIFTY FINANCIAL SERVICES", "NIFTY IT", "NIFTY PHARMA",
             "NIFTY INDIA CONSUMPTION", "NIFTY INFRASTRUCTURE", "NIFTY MNC", "NIFTY PSE", "NIFTY ENERGY", "NIFTY AUTO",
             "NIFTY FMCG", "NIFTY DIVIDEND OPPORTUNITIES 50", "NIFTY500 VALUE 50", "NIFTY TOTAL MARKET",
             "NIFTY INDIA MANUFACTURING", "NIFTY INDIA DEFENCE", "NIFTY COMMODITIES", "NIFTY SERVICES SECTOR"]


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def get(url, **kw):
    for attempt in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=60, **kw)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


# ------------------------------------------------------------------ AMFI universe
def amfi_universe():
    txt = get("https://portal.amfiindia.com/spages/NAVAll.txt").text
    typ = cat = amc = None
    rows = []
    for line in txt.splitlines():
        l = line.strip()
        if not l:
            continue
        m = re.match(r"^(Open Ended|Close Ended|Interval Fund) Schemes\s*\((.+)\)$", l)
        if m:
            typ, cat = m.group(1), re.sub(r"\s+", " ", m.group(2).strip())
            continue
        p = l.split(";")
        if l.startswith("Scheme Code"):
            continue
        if len(p) < 8 or not p[0].strip().isdigit():
            if not l.startswith("Scheme Code"):
                amc = l
            continue
        rows.append(dict(code=int(p[0]), g=p[1], r=p[2], name=p[3], plan=p[4], opt=p[5], nav=p[6], date=p[7],
                         type=typ, cat=cat, amc=amc))
    cutoff = dt.date.today() - dt.timedelta(days=30)

    def recent(x):
        try:
            return dt.datetime.strptime(x["date"], "%d-%b-%Y").date() >= cutoff
        except ValueError:
            return False

    def is_direct(x):
        return bool(re.search("direct", x["plan"], re.I) or re.search("direct", x["name"], re.I))

    def is_growth(x):
        g = re.search("growth", x["opt"], re.I) or re.search("growth", x["name"], re.I) or (not x["opt"] and x["r"] == "-")
        return bool(g) and not re.search("idcw|dividend|bonus|payout|reinvest", x["opt"] + " " + x["name"], re.I)

    uni = [x for x in rows if x["type"] == "Open Ended" and is_direct(x) and is_growth(x) and recent(x)]
    meta = [[x["code"], x["name"], x["amc"], x["cat"], x["g"]] for x in uni]
    have = {x["code"] for x in uni}
    # rows with no plan label (e.g. HSBC, ETFs): keep the highest-NAV growth row per scheme as Direct
    best = {}
    for x in rows:
        if (x["type"] == "Open Ended" and not x["plan"] and not x["opt"] and x["r"] == "-"
                and not re.search("direct|regular", x["name"], re.I) and recent(x)):
            if x["name"] not in best or fnum(x["nav"]) > fnum(best[x["name"]]["nav"]):
                best[x["name"]] = x
    for x in best.values():
        if x["code"] not in have:
            meta.append([x["code"], x["name"] + " (plan inferred: Direct)", x["amc"], x["cat"], x["g"]])
    return meta


# ------------------------------------------------------------------ NAV history
def history(code):
    d = get(f"https://api.mfapi.in/mf/{code}").json()
    out = []
    for x in reversed(d.get("data", [])):
        dd, mm, yy = x["date"].split("-")
        v = fnum(x["nav"])
        if v > 0:
            out.append(f"{yy}{mm}{dd}:{v}")
    return code, " ".join(out)


# ------------------------------------------------------------------ Nifty TRI
def tri(session, name, start="01-Jan-2013"):
    end = dt.date.today().strftime("%d-%b-%Y")
    cinfo = json.dumps({"name": name, "startDate": start, "endDate": end, "indexName": name}).replace('"', "'")
    r = session.post("https://www.niftyindices.com/Backpage/getTotalReturnIndexString",
                     json={"cinfo": cinfo}, timeout=60,
                     headers={**UA, "Content-Type": "application/json; charset=utf-8",
                              "Origin": "https://www.niftyindices.com",
                              "Referer": "https://www.niftyindices.com/reports/historical-data"})
    j = r.json()
    if isinstance(j, dict) and "d" in j:
        j = json.loads(j["d"]) if isinstance(j["d"], str) else j["d"]
    return [[x["Date"], float(x["TotalReturnsIndex"])] for x in j]


def main():
    t0 = time.time()
    meta = amfi_universe()
    print(f"AMFI universe: {len(meta)} schemes")
    hist, failed = {}, []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(history, m[0]): m[0] for m in meta}
        for f in cf.as_completed(futs):
            try:
                c, h = f.result()
                hist[str(c)] = h
            except Exception:  # noqa: BLE001
                failed.append(futs[f])
    print(f"NAV histories: {len(hist)} ok, {len(failed)} failed")
    if len(hist) < 0.9 * len(meta):
        print(f"::error title=NAV downloads::{len(failed)} of {len(meta)} failed")
        sys.exit("Too many NAV downloads failed; keeping yesterday's data.")
    with gzip.open(os.path.join(RAW, "mf_universe_nav.json.gz"), "wt") as fh:
        json.dump({"meta": meta, "hist": hist}, fh, separators=(",", ":"))

    bm_path = os.path.join(RAW, "benchmarks_tri.json")
    old = json.load(open(bm_path)) if os.path.exists(bm_path) else {}
    s = requests.Session()
    try:
        s.get("https://www.niftyindices.com/reports/historical-data", headers=UA, timeout=60)
    except Exception:  # noqa: BLE001
        pass
    new, misses = {}, []
    for n in TRI_NAMES:
        try:
            rows = tri(s, n)
            if rows:
                new[n] = rows
                continue
        except Exception:  # noqa: BLE001
            pass
        misses.append(n)
        if n in old:
            new[n] = old[n]
    json.dump(new, open(bm_path, "w"), separators=(",", ":"))
    print(f"Benchmarks: {len(new) - len([m for m in misses if m in old])} fresh, {len(misses)} kept from last run"
          f"{' (' + ', '.join(misses) + ')' if misses else ''}")
    print(f"Done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # surface the reason as a GitHub annotation
        import traceback
        tb = traceback.format_exc().strip().splitlines()
        print(f"::error title=fetch_data failed::{type(e).__name__}: {e} | " + " | ".join(tb[-4:]))
        raise
