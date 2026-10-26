"""Find AMFI's SIF data endpoints: fetch the SIF pages, read their JS bundles, list every /api/ path, then try the SIF-looking ones."""
import json, os, re, requests
H = {"User-Agent": "Mozilla/5.0 (fund-lens probe)", "Referer": "https://www.amfiindia.com/"}
base = "https://www.amfiindia.com"
pages = ["/sif", "/sif/latest-nav", "/sif/nav-download", "/sif/nav-history", "/sif/ter-of-sif", "/sif/investment-strategy-details", "/sif/disclosure-of-risk-parameters"]
seen_js, apis, page_status = set(), set(), {}
for p in pages:
    try:
        r = requests.get(base + p, headers=H, timeout=40); page_status[p] = r.status_code
        html = r.text
        apis |= set(re.findall(r"""["'`](/api/[A-Za-z0-9_\-/]+)""", html))
        for js in re.findall(r"""(/_next/static/[^"']+?\.js)""", html):
            if js in seen_js: continue
            seen_js.add(js)
            t = requests.get(base + js, headers=H, timeout=40).text
            apis |= set(re.findall(r"""["'`](/api/[A-Za-z0-9_\-/]+)""", t))
            apis |= set(re.findall(r"""["'`](https://[a-z0-9.\-]*amfiindia\.com/[A-Za-z0-9_\-/]*(?:sif|SIF)[A-Za-z0-9_\-/.]*)""", t))
    except Exception as e:  # noqa: BLE001
        page_status[p] = str(e)[:100]
tries = {}
for a in sorted(apis):
    if "sif" in a.lower() or "strategy" in a.lower():
        try:
            r = requests.get(a if a.startswith("http") else base + a, headers=H, timeout=40)
            tries[a] = {"status": r.status_code, "head": r.text[:600]}
        except Exception as e:  # noqa: BLE001
            tries[a] = {"error": str(e)[:100]}
out = {"pages": page_status, "js": len(seen_js), "apis": sorted(apis), "tries": tries}
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "raw", "sif_probe.json"), "w"), indent=1)
print(json.dumps(page_status), len(apis), "apis;", sum(1 for v in tries.values() if v.get("status") == 200), "sif endpoints answered 200")
