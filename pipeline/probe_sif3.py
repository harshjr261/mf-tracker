"""Third SIF probe: how the site calls its NAV-history APIs, and whether they return SIF history."""
import json, os, re, requests
H = {"User-Agent": "Mozilla/5.0 (fund-lens probe)", "Referer": "https://www.amfiindia.com/"}
base = "https://www.amfiindia.com"; out = {"ctx": {}}
for p in ["/net-asset-value/nav-history", "/sif", "/sif/latest-nav"]:
    html = requests.get(base + p, headers=H, timeout=40).text
    for js in set(re.findall(r"""(/_next/static/[^"']+?\.js)""", html)):
        t = requests.get(base + js, headers=H, timeout=40).text
        for key in ["nav-history", "get-nav-history", "sif-latest-nav", "SD_Id", "sdId", "Sd_Id"]:
            for m in re.finditer(re.escape(key), t):
                out["ctx"].setdefault(key, []).append(t[max(0, m.start() - 350): m.end() + 350])
for k in out["ctx"]:
    out["ctx"][k] = list(dict.fromkeys(out["ctx"][k]))[:4]
lat = requests.get(base + "/api/sif-latest-nav", headers=H, timeout=60).json()
s0 = [s for t in lat["data"] for c in t["categories"] for g in c["groups"] for s in g["schemes"]][0]
tries = {}
for path in ["/api/nav-history", "/api/get-nav-history/navs"]:
    for q in [f"?query_type=historical_period&from_date=2025-10-01&to_date=2026-10-20&sd_id={s0['Sd_Id']}",
              f"?query_type=historical_period&from_date=2025-10-01&to_date=2026-10-20&sdId={s0['Sd_Id']}",
              f"?sd_id={s0['Sd_Id']}&from_date=2025-10-01&to_date=2026-10-20",
              f"?mfId={s0['sifId']}&from_date=2025-10-01&to_date=2026-10-20&isSif=true",
              f"?sifId={s0['sifId']}&sdId={s0['Sd_Id']}&from_date=2025-10-01&to_date=2026-10-20"]:
        try:
            r = requests.get(base + path + q, headers=H, timeout=40); tries[path + q] = [r.status_code, r.text[:400]]
        except Exception as e:  # noqa: BLE001
            tries[path + q] = ["err", str(e)[:80]]
out["tries"] = tries; out["s0"] = s0
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "raw", "sif_probe3.json"), "w"), indent=1)
print("done")
