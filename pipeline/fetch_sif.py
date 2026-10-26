"""SIF (Specialized Investment Fund) data from AMFI: every strategy's latest NAV and TER.
AMFI publishes no SIF NAV history, so this job appends each night's NAVs to raw/sif/nav_history.json,
building the history from the first run onwards. raw/sif/latest.json keeps the full scheme list and TER."""
import datetime as dt, json, os, requests
ROOT = os.path.join(os.path.dirname(__file__), "..", "raw", "sif"); os.makedirs(ROOT, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (fund-lens nightly)", "Referer": "https://www.amfiindia.com/"}
API = "https://www.amfiindia.com/api/"
lat = requests.get(API + "sif-latest-nav", headers=H, timeout=60).json()
schemes = [s for t in lat["data"] for c in t["categories"] for g in c["groups"] for s in g["schemes"]]
def _rows(j):
    if isinstance(j, list):
        j = j[0] if j and isinstance(j[0], dict) and "data" in j[0] else {"data": j}
    d = j.get("data") if isinstance(j, dict) else None
    if isinstance(d, dict):
        d = d.get("data")
    return d if isinstance(d, list) else []


def get_ter():
    """Latest month's TER for every SIF strategy. AMFI's TER page wants Month as MM-YYYY (MonthNumber)."""
    today = dt.date.today(); fy = today.year if today.month >= 4 else today.year - 1
    for y in (f"{fy}-{fy + 1}", f"{fy - 1}-{fy}"):
        try:
            mj = requests.get(API + f"sif-populate-ter-month?year={y}", headers=H, timeout=60).json()
        except Exception:  # noqa: BLE001
            continue
        months = mj if isinstance(mj, list) else _rows(mj)
        for m in months:  # newest first
            mv = m.get("MonthNumber") if isinstance(m, dict) else m
            rows = []
            for sid in sorted({x["sifId"] for x in schemes}):  # the API answers one SIF at a time
                try:
                    j = requests.get(API + "sif-populate-te-rdata-revised", headers=H, timeout=60,
                                     params={"SIF_Id": sid, "Month": mv, "strCat": "-1", "strType": "-1", "page": 1, "pageSize": 200}).json()
                    rows += _rows(j)
                except Exception:  # noqa: BLE001
                    pass
            if len({r.get("SIF_Id") for r in rows}) >= len({x["sifId"] for x in schemes}) // 2:
                return mv, rows
    return None, []


ter_month, ter = get_ter()
hist_p = os.path.join(ROOT, "nav_history.json")
hist = json.load(open(hist_p)) if os.path.exists(hist_p) else {}
added = 0
for s in schemes:
    key = s.get("ISINPO") or f"{s['Sd_Id']}|{s['NavName']}"
    try:
        d = dt.datetime.strptime(s["Date"], "%d-%b-%Y").strftime("%Y-%m-%d")
        v = float(s["NetAssetValue"])
    except Exception:  # noqa: BLE001
        continue
    h = hist.setdefault(key, {"name": s["NavName"], "sd": s["Sd_Id"], "navs": {}})
    if d not in h["navs"]:
        h["navs"][d] = v; added += 1
json.dump(hist, open(hist_p, "w"), separators=(",", ":"), sort_keys=True)
json.dump({"asOf": dt.date.today().isoformat(), "schemes": schemes, "terMonth": ter_month, "ter": ter}, open(os.path.join(ROOT, "latest.json"), "w"), separators=(",", ":"))
dg = [s for s in schemes if "direct" in (s.get("Plan") or "").lower() and "growth" in (s.get("Option") or "").lower()]
print(f"::notice title=SIF::{len(schemes)} scheme rows ({len(dg)} Direct Growth), {len({s['SIFName'] for s in schemes})} SIF brands, {len(ter)} TER rows ({ter_month}), {len({t.get("SIF_Id") for t in ter})} SIFs with TER, {added} new NAV points")
