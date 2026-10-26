"""SIF (Specialized Investment Fund) data from AMFI: every strategy's latest NAV and TER.
AMFI publishes no SIF NAV history, so this job appends each night's NAVs to raw/sif/nav_history.json,
building the history from the first run onwards. raw/sif/latest.json keeps the full scheme list and TER."""
import datetime as dt, json, os, requests
ROOT = os.path.join(os.path.dirname(__file__), "..", "raw", "sif"); os.makedirs(ROOT, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (fund-lens nightly)", "Referer": "https://www.amfiindia.com/"}
API = "https://www.amfiindia.com/api/"
lat = requests.get(API + "sif-latest-nav", headers=H, timeout=60).json()
schemes = [s for t in lat["data"] for c in t["categories"] for g in c["groups"] for s in g["schemes"]]
def get_ter():
    """Latest month's TER for every SIF strategy (AMFI's TER page: SIF_Id/Month/strCat/strType, paged)."""
    today = dt.date.today(); fy = today.year if today.month >= 4 else today.year - 1
    for y in (f"{fy}-{fy + 1}", f"{fy - 1}-{fy}"):
        try:
            mj = requests.get(API + f"sif-populate-ter-month?year={y}", headers=H, timeout=60).json()
            months = (mj[0].get("data") if isinstance(mj, list) and mj else mj.get("data")) or []
        except Exception:  # noqa: BLE001
            months = []
        for m in reversed(months):
            mv = m.get("MonthYear") if isinstance(m, dict) else m
            rows = []
            for typ in ("-1", "1", "2"):
                try:
                    j = requests.get(API + "sif-populate-te-rdata-revised", headers=H, timeout=60,
                                     params={"SIF_Id": "-1", "Month": mv, "strCat": "-1", "strType": typ, "page": 1, "pageSize": 1000}).json()
                    d = j[0]["data"] if isinstance(j, list) else j.get("data")
                    rows = d.get("data", []) if isinstance(d, dict) else (d or [])
                except Exception:  # noqa: BLE001
                    rows = []
                if rows:
                    return mv, rows
    return None, requests.get(API + "sif-populate-te-rdata-revised", headers=H, timeout=60).json().get("data", [])


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
