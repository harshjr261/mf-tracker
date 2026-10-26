import json, os, re, requests
H = {"User-Agent": "Mozilla/5.0 (fund-lens probe)", "Referer": "https://www.amfiindia.com/"}
base = "https://www.amfiindia.com"; out = {"ctx": []}
html = requests.get(base + "/sif/ter-of-sif", headers=H, timeout=40).text
for js in set(re.findall(r"""(/_next/static/[^"']+?\.js)""", html)):
    t = requests.get(base + js, headers=H, timeout=40).text
    for m in re.finditer(r"sif-populate-te", t):
        out["ctx"].append(t[max(0, m.start() - 600): m.end() + 600])
lat = requests.get(base + "/api/sif-latest-nav", headers=H, timeout=60).json()
ids = sorted({s["sifId"] for t in lat["data"] for c in t["categories"] for g in c["groups"] for s in g["schemes"]})
out["ids"] = ids
tries = {}
for q in ["", "?sifId=47", "?sif_id=47", "?SIF_Id=47", "?month=2026-10", "?year=2026-2027", "?finYear=2026-2027&month=10"]:
    r = requests.get(base + "/api/sif-populate-te-rdata-revised" + q, headers=H, timeout=40)
    try: j = r.json(); tries[q] = [r.status_code, len(j.get("data", [])) if isinstance(j, dict) else len(j), sorted({d.get("SIF_Id") for d in j.get("data", [])}) if isinstance(j, dict) else None]
    except Exception: tries[q] = [r.status_code, r.text[:200]]
out["tries"] = tries
r = requests.get(base + "/api/sif-populate-ter-month", headers=H, timeout=40); out["months"] = r.text[:300]
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "raw", "sif_probe7.json"), "w"), indent=1)
