"""SIF section data -> docs/sif.json
Usage: python3 build_sif.py <raw/sif dir> <raw/benchmarks_tri.json> <docs/data.json> <out docs/sif.json>

AMFI publishes SIF latest NAV and daily TER but no NAV history. History therefore starts with our first
nightly snapshot; metrics that need history are computed only once enough of it exists."""
import datetime as dt, json, math, os, re, statistics, sys

BRAND_AMC = {"Altiva": "Edelweiss Mutual Fund", "Apex": "Aditya Birla Sun Life Mutual Fund", "Arthaya": "Union Mutual Fund",
             "Arudha": "Bandhan Mutual Fund", "Diviniti": "ITI Mutual Fund", "DynaSIF": "360 ONE Mutual Fund", "Infinity": "Kotak Mahindra Mutual Fund",
             "Magnum": "SBI Mutual Fund", "Platinum": "Mirae Asset Mutual Fund", "Prism": "Jio BlackRock Mutual Fund", "RedHex": "HSBC Mutual Fund",
             "SUMMIT": "Invesco Mutual Fund", "Sapphire": "Franklin Templeton Mutual Fund", "Titanium": "Tata Mutual Fund", "WSIF": "The Wealth Company Mutual Fund",
             "iSIF": "ICICI Prudential Mutual Fund", "qsif": "quant Mutual Fund", "Eminence": "AlphaGrep Mutual Fund", "MSIF": "Mahindra Manulife Mutual Fund",
             "Select": "Sundaram Mutual Fund"}
CAT_SHORT = {"Equity Long-Short Fund": "Equity Long-Short", "Equity Ex-Top 100 Long-Short Fund": "Equity Ex-Top 100 Long-Short",
             "Sector Rotation Long-Short Fund": "Sector Rotation Long-Short", "Hybrid Long-Short Fund": "Hybrid Long-Short",
             "Active Asset Allocator Long-Short Fund": "Active Asset Allocator Long-Short"}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("long - short", "longshort").replace("long-short", "longshort").replace("long short", "longshort"))


def brand_of(sif_name):
    b = sif_name.replace(" SIF", "").strip()
    return {"qsif": "qsif", "iSIF": "iSIF", "DynaSIF": "DynaSIF", "WSIF": "WSIF"}.get(b, b)


def tri(rows):
    s = sorted((dt.datetime.strptime(d, "%d %b %Y").date(), v) for d, v in rows)
    return s


def at(series, d):
    """Last value on or before date d."""
    v = None
    for x, y in series:
        if x > d:
            break
        v = y
    return v


def main(src, bm_path, data_path, out):
    L = json.load(open(os.path.join(src, "latest.json")))
    hist = json.load(open(os.path.join(src, "nav_history.json"))) if os.path.exists(os.path.join(src, "nav_history.json")) else {}
    launch = json.load(open(os.path.join(src, "launch.json"))) if os.path.exists(os.path.join(src, "launch.json")) else {}
    bms = json.load(open(bm_path)); n50, n500 = tri(bms["NIFTY 50"]), tri(bms["NIFTY 500"])
    D = json.load(open(data_path))
    arb = [f["r"]["1Y"] for f in D["funds"] if f["cat"] == "Arbitrage" and f.get("r", {}).get("1Y") is not None]
    flexi = [f for f in D["funds"] if f["cat"] == "Flexi Cap"]
    arb1y = statistics.median(arb) if arb else None
    # latest TER per scheme name
    ter = {}
    for t in L.get("ter", []):
        n = t.get("Scheme_Name"); d = (t.get("TER_Date") or "")[:10]
        if n and (n not in ter or d > ter[n]["date"]):
            f = lambda k: float(t[k]) if t.get(k) not in (None, "") else None
            ter[n] = {"date": d, "d": f("D_BER"), "dt": f("D_TER"), "r": f("R_BER"), "rt": f("R_TER")}
    # AMFI spells some names differently across days (case, "Ex-Top 100Long"); merge variants by normalised name
    ter_by_norm, launch_n = {}, {}
    for k, v in ter.items():
        n = norm(k)
        if n not in ter_by_norm or v["date"] > ter_by_norm[n][1]["date"]:
            ter_by_norm[n] = (n, v)
    for k, v in launch.items():
        n = norm(k)
        launch_n[n] = min(v, launch_n.get(n, v))
    out_rows = []
    for s in L["schemes"]:
        name = s.get("NavName") or ""
        low = (name + " " + (s.get("Plan") or "") + " " + (s.get("Option") or "")).lower()
        if "direct" not in low or "growth" not in low or "idcw" in low:
            continue
        cat_full = s.get("category") or ""
        cat = CAT_SHORT.get(cat_full.split(" - ")[-1].strip(), cat_full.split(" - ")[-1].strip())
        group = "Hybrid" if cat_full.lower().startswith("hybrid") else "Equity" if cat_full.lower().startswith("equity") else "Debt"
        try:
            nav = float(s["NetAssetValue"]); nd = dt.datetime.strptime(s["Date"], "%d-%b-%Y").date()
        except Exception:  # noqa: BLE001
            continue
        base = re.split(r"\s*-\s*(Direct|Growth)|\s+Direct|-Direct", name, flags=re.I)[0].strip()
        nb = norm(base)
        tk = next((v for k, v in ter_by_norm.items() if k == nb), None) or next((v for k, v in ter_by_norm.items() if nb.startswith(k) or k.startswith(nb)), None)
        tname, tr = tk if tk else (None, None)
        ld = launch_n.get(tname) if tname else None
        face = 1000.0 if nav >= 100 else 10.0
        rec = {"key": s.get("ISINPO") or s.get("Sd_Id"), "sd": s.get("Sd_Id"), "name": base, "nav": nav, "navDate": nd.isoformat(),
               "sif": s.get("SIFName"), "brand": brand_of(s.get("SIFName") or ""), "cat": cat, "group": group, "catFull": cat_full,
               "face": face, "ter": tr, "launch": ld}
        rec["amc"] = BRAND_AMC.get(rec["brand"], "")
        if ld:
            l0 = dt.date.fromisoformat(ld); days = (nd - l0).days
            rec["days"] = days
            rec["since"] = nav / face - 1
            b50, b500 = at(n50, l0), at(n500, l0); e50, e500 = at(n50, nd), at(n500, nd)
            rec["n50"] = e50 / b50 - 1 if b50 and e50 else None
            rec["n500"] = e500 / b500 - 1 if b500 and e500 else None
            rec["arb"] = (1 + arb1y) ** (days / 365.25) - 1 if arb1y is not None and days > 0 else None
            rec["benchAsOf"] = max(x for x, _ in n500 if x <= nd).isoformat() if n500 else None
        # history-based metrics, only when enough nightly snapshots exist
        h = hist.get(s.get("ISINPO") or f"{s['Sd_Id']}|{name}", {}).get("navs", {})
        pts = sorted((dt.date.fromisoformat(k), v) for k, v in h.items())
        rec["hist"] = [[d.isoformat(), v] for d, v in pts]
        if len(pts) >= 2:
            last_d, last_v = pts[-1]
            for lab, n in (("1M", 30), ("3M", 91), ("6M", 182), ("1Y", 365)):
                p0 = [v for d, v in pts if d <= last_d - dt.timedelta(days=n)]
                if p0 and (last_d - pts[0][0]).days >= n:
                    rec.setdefault("r", {})[lab] = last_v / p0[-1] - 1
        if len(pts) >= 60:  # ~3 months of trading days: daily risk vs Nifty 500
            fr, br = [], []
            for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
                a, b = at(n500, d0), at(n500, d1)
                if a and b and d1 > d0:
                    fr.append(v1 / v0 - 1); br.append(b / a - 1)
            if len(fr) >= 50:
                mf, mb = statistics.mean(fr), statistics.mean(br)
                cov = sum((x - mf) * (y - mb) for x, y in zip(fr, br)) / (len(fr) - 1)
                vb = statistics.variance(br)
                rec["risk"] = {"vol": statistics.stdev(fr) * math.sqrt(250), "beta": cov / vb if vb else None,
                               "corr": cov / (statistics.stdev(fr) * statistics.stdev(br)) if vb else None, "days": len(fr)}
                worst = sorted(range(len(br)), key=lambda i: br[i])[:10]
                rec["risk"]["badDays"] = {"sif": statistics.mean(fr[i] for i in worst), "n500": statistics.mean(br[i] for i in worst)}
                peak, mdd = -1e18, 0
                for _, v in pts:
                    peak = max(peak, v); mdd = min(mdd, v / peak - 1)
                rec["risk"]["mdd"] = mdd
        out_rows.append(rec)
    first = min((dt.date.fromisoformat(r["hist"][0][0]) for r in out_rows if r["hist"]), default=None)
    obj = {"asOf": max(r["navDate"] for r in out_rows), "historyFrom": first.isoformat() if first else None, "terMonth": L.get("terMonth"),
           "arb1y": arb1y, "flexi1y": statistics.median([f["r"]["1Y"] for f in flexi if f.get("r", {}).get("1Y") is not None]) if flexi else None,
           "strategies": sorted(out_rows, key=lambda r: (r["group"], r["cat"], r["name"])),
           "sources": ["AMFI SIF latest NAV (daily)", "AMFI TER of SIF (daily)", "niftyindices.com total return indices"]}
    json.dump(obj, open(out, "w"), separators=(",", ":"))
    print(f"sif: {len(out_rows)} Direct Growth strategies, {sum(1 for r in out_rows if r.get('launch'))} with launch date, {sum(1 for r in out_rows if r.get('ter'))} with TER, history from {obj['historyFrom']}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
