"""Download AMFI's monthly industry reports (category-wise flows, AUM, folios) for the last 20 months.
Files: raw/amfi_monthly/am<mon><yyyy>repo.xls — only missing ones are fetched."""
import datetime as dt, os, requests
OUT = os.path.join(os.path.dirname(__file__), "..", "raw", "amfi_monthly"); os.makedirs(OUT, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (fund-lens monthly)", "Referer": "https://www.amfiindia.com/"}
d = dt.date.today().replace(day=1); got = 0
for _ in range(20):
    d = (d - dt.timedelta(days=1)).replace(day=1)
    name = f"am{d.strftime('%b').lower()}{d.year}repo.xls"; path = os.path.join(OUT, name)
    if os.path.exists(path) and os.path.getsize(path) > 10000: continue
    r = requests.get(f"https://portal.amfiindia.com/spages/{name}", headers=H, timeout=60)
    if r.ok and len(r.content) > 10000 and not r.content[:200].lstrip().lower().startswith(b"<!doctype"):
        open(path, "wb").write(r.content); got += 1; print("saved", name, len(r.content))
    else:
        print("not available yet", name, r.status_code)
print(f"::notice title=AMFI monthly::{got} new report(s)")

# ---- AMC-wise quarterly average AUM (AMFI "Average AUM - fund-wise"), last 6 quarters
import json
API = "https://www.amfiindia.com/api/average-aum-fundwise"
out, years = [], requests.get(API, headers=H, timeout=60).json().get("data", [])
for fy in years[:3]:
    per = requests.get(f"{API}?fyId={fy['id']}", headers=H, timeout=60).json().get("data", {}).get("periods", [])
    for p in per:
        j = requests.get(f"{API}?fyId={fy['id']}&periodId={p['id']}", headers=H, timeout=60).json()
        rows = j.get("data") or []
        if rows:
            out.append({"fy": fy["financial_year"], "period": p["period"],
                        "amcs": {r["MutualFundName"]: round(sum(v or 0 for v in r["averageAUM"].values()) / 100, 2) for r in rows}})
    if len(out) >= 6:
        break
json.dump(out[:6], open(os.path.join(OUT, "amc_aaum_quarterly.json"), "w"), indent=0)
print(f"::notice title=AMC AAUM::{len(out[:6])} quarters, {len(out[0]['amcs']) if out else 0} AMCs (Rs crore)")
