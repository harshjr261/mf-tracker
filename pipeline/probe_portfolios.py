"""Feasibility probe: can every AMC's monthly portfolio file be reached by a script?
For each AMC's official portfolio page (docs/amc_factsheets.json) record HTTP status and the spreadsheet links found in the raw HTML.
Writes raw/holdings_probe.json. A page with 0 links is either JS-rendered (needs its API found) or blocked."""
import json, os, re, time, urllib.parse, requests
ROOT = os.path.join(os.path.dirname(__file__), "..")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-IN,en;q=0.9"}
links = json.load(open(os.path.join(ROOT, "docs", "amc_factsheets.json")))
out = {}
for amc, v in sorted(links.items()):
    url = v.get("portfolio")
    rec = {"url": url}
    if not url:
        rec["status"] = "no page"; out[amc] = rec; continue
    try:
        r = requests.get(url, headers=H, timeout=40)
        rec["status"] = r.status_code; rec["bytes"] = len(r.content)
        html = r.text.replace("\\/", "/")
        files = re.findall(r"""["'(]([^"'()\s]+?\.(?:xlsx|xls|zip|csv))(?:\?[^"'()\s]*)?["')]""", html, re.I)
        files = list(dict.fromkeys(urllib.parse.urljoin(url, f) for f in files))
        rec["files"] = len(files); rec["sample"] = files[:5]
        rec["apiHints"] = list(dict.fromkeys(re.findall(r"""["'](/?api/[^"']{3,80}|https?://[^"']*api[^"']{3,80})["']""", html)))[:6]
        if files:  # try downloading the first file
            f = requests.get(files[0], headers={**H, "Referer": url}, timeout=60)
            rec["fileStatus"] = f.status_code; rec["fileBytes"] = len(f.content); rec["fileMagic"] = f.content[:4].hex()
    except Exception as e:  # noqa: BLE001
        rec["status"] = "error"; rec["error"] = str(e)[:160]
    out[amc] = rec
    print(amc, rec.get("status"), rec.get("files"), rec.get("fileStatus"))
    time.sleep(1)
json.dump(out, open(os.path.join(ROOT, "raw", "holdings_probe.json"), "w"), indent=1)
ok = sum(1 for r in out.values() if r.get("fileStatus") == 200 and r.get("fileBytes", 0) > 5000)
print(f"::notice title=Holdings probe::{ok}/{len(out)} AMCs gave a downloadable spreadsheet from the raw page")
