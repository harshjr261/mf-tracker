"""Second SIF probe: where can daily NAV history for SIFs come from?"""
import json, os, re, requests
H = {"User-Agent": "Mozilla/5.0 (fund-lens probe)", "Referer": "https://www.amfiindia.com/"}
base = "https://www.amfiindia.com"; out = {}
lat = requests.get(base + "/api/sif-latest-nav", headers=H, timeout=60).json()
schemes = [s for t in lat["data"] for c in t["categories"] for g in c["groups"] for s in g["schemes"]]
out["count"] = len(schemes); out["sample"] = schemes[:3]
out["fields"] = sorted(schemes[0].keys())
direct = [s for s in schemes if "direct" in (s.get("Plan") or "").lower() and "growth" in (s.get("Option") or "").lower()]
out["directGrowth"] = len(direct); out["sifs"] = sorted({s["SIFName"] for s in schemes})
# 1) every /api/ path used anywhere on the site's NAV pages
apis = set()
for p in ["/net-asset-value/nav-history", "/net-asset-value/nav-download", "/net-asset-value", "/sif/latest-nav", "/sif"]:
    try:
        html = requests.get(base + p, headers=H, timeout=40).text
        for js in set(re.findall(r"""(/_next/static/[^"']+?\.js)""", html)):
            t = requests.get(base + js, headers=H, timeout=40).text
            apis |= set(re.findall(r"""["'`](/api/[A-Za-z0-9_\-/]+)""", t))
    except Exception as e:  # noqa: BLE001
        out.setdefault("err", []).append(str(e)[:80])
out["apis"] = sorted(apis)
# 2) try likely history endpoints for one SIF
s0 = direct[0] if direct else schemes[0]
tries = {}
for a in [a for a in apis if "hist" in a.lower() or "sif" in a.lower()]:
    for q in [f"?sifId={s0['sifId']}&sdId={s0['Sd_Id']}&from_date=2025-10-01&to_date=2026-10-20", f"?sifid={s0['sifId']}", ""]:
        try:
            r = requests.get(base + a + q, headers=H, timeout=40); tries[a + q] = [r.status_code, r.text[:300]]
        except Exception as e:  # noqa: BLE001
            tries[a + q] = ["err", str(e)[:80]]
out["tries"] = tries
# 3) mfapi: are SIFs listed?
try:
    allmf = requests.get("https://api.mfapi.in/mf", timeout=60).json()
    out["mfapi_sif"] = [m for m in allmf if re.search(r"\bSIF\b|Long[- ]?Short|Altiva|qSIF|Magnum SIF|Arudha|Dynasif|Diviniti|Titanium|Apex SIF|iSIF", m["schemeName"], re.I)][:60]
except Exception as e:  # noqa: BLE001
    out["mfapi_err"] = str(e)[:80]
# 4) AMFI NAVAll.txt: do SIFs appear?
try:
    nav = requests.get("https://portal.amfiindia.com/spages/NAVAll.txt", headers=H, timeout=60).text
    out["navall_sif_lines"] = [l for l in nav.splitlines() if re.search(r"Long[- ]?Short|\bSIF\b", l, re.I)][:10]
except Exception as e:  # noqa: BLE001
    out["navall_err"] = str(e)[:80]
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "raw", "sif_probe2.json"), "w"), indent=1)
print(out["count"], "schemes;", out["directGrowth"], "direct growth;", len(out.get("mfapi_sif", [])), "on mfapi;", len(out.get("navall_sif_lines", [])), "in NAVAll")
