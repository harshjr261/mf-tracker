"""List every spreadsheet link that looks like a monthly portfolio, per AMC page that serves links in its HTML."""
import json, os, re, urllib.parse, requests
ROOT = os.path.join(os.path.dirname(__file__), "..")
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
probe = json.load(open(os.path.join(ROOT, "raw", "holdings_probe.json")))
out = {}
for amc, r in probe.items():
    if not r.get("files"):
        continue
    try:
        html = requests.get(r["url"], headers=H, timeout=40).text.replace("\\/", "/")
    except Exception as e:  # noqa: BLE001
        out[amc] = {"error": str(e)[:100]}; continue
    files = re.findall(r"""["'(]([^"'()\s]+?\.(?:xlsx|xls|zip))(?:\?[^"'()\s]*)?["')]""", html, re.I)
    files = list(dict.fromkeys(urllib.parse.urljoin(r["url"], f) for f in files))
    port = [f for f in files if re.search(r"portfolio|portfolios|holding", urllib.parse.unquote(f), re.I) and not re.search(r"debt|fortnight|half|overlap|isin-debt|risk", urllib.parse.unquote(f), re.I)]
    out[amc] = {"n": len(files), "portfolio": port[:25]}
json.dump(out, open(os.path.join(ROOT, "raw", "holdings_probe2.json"), "w"), indent=1)
