import json, os, re, requests
H = {"User-Agent": "Mozilla/5.0 (fund-lens probe)", "Referer": "https://www.amfiindia.com/"}
base = "https://www.amfiindia.com"; out = {}
html = requests.get(base + "/sif", headers=H, timeout=40).text
paths = sorted(set(re.findall(r'href="(/sif[^"#?]*)"', html)) | set(re.findall(r'"(/sif/[a-z0-9\-/]+)"', html)))
out["paths"] = paths
apis, seen = set(), set()
for p in paths:
    try:
        r = requests.get(base + p, headers=H, timeout=40); out.setdefault("status", {})[p] = r.status_code
        for js in set(re.findall(r"""(/_next/static/[^"']+?\.js)""", r.text)) - seen:
            seen.add(js); t = requests.get(base + js, headers=H, timeout=40).text
            apis |= set(re.findall(r"""["'`](/api/[A-Za-z0-9_\-/]+)""", t))
    except Exception as e:  # noqa: BLE001
        out.setdefault("status", {})[p] = str(e)[:80]
out["apis"] = sorted(a for a in apis if "sif" in a.lower() or "nfo" in a.lower() or "aum" in a.lower())
tries = {}
for a in out["apis"]:
    try:
        r = requests.get(base + a, headers=H, timeout=40); tries[a] = [r.status_code, r.text[:500]]
    except Exception as e:  # noqa: BLE001
        tries[a] = ["err", str(e)[:80]]
for u in ["https://portal.amfiindia.com/spages/SSD_SIF-120.xml", "https://portal.amfiindia.com/spages/SSD_SIF-120.pdf", "https://portal.amfiindia.com/spages/SIF-120.pdf", "https://portal.amfiindia.com/spages/SSD_120.xml"]:
    try:
        r = requests.get(u, headers=H, timeout=40); tries[u] = [r.status_code, r.content[:300].decode("utf-8", "replace")]
    except Exception as e:  # noqa: BLE001
        tries[u] = ["err", str(e)[:80]]
out["tries"] = tries
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "raw", "sif_probe6.json"), "w"), indent=1)
