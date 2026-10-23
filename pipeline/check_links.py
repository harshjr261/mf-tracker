"""Check every AMC factsheet link: HTTP status, final URL, page title, and whether the page mentions factsheets."""
import concurrent.futures as cf, json, os, re, requests
ROOT = os.path.join(os.path.dirname(__file__), "..")
links = json.load(open(os.path.join(ROOT, "docs", "amc_factsheets.json")))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "en-IN,en;q=0.9"}
def check(item):
    amc, url = item
    try:
        r = requests.get(url, headers=UA, timeout=30, allow_redirects=True)
        t = r.text[:400000]
        title = re.search(r"<title[^>]*>(.*?)</title>", t, re.S | re.I)
        return amc, dict(url=url, status=r.status_code, final=r.url, title=(title.group(1).strip()[:120] if title else ""),
                         mentions=bool(re.search(r"fact\s*-?sheet", t, re.I)), bytes=len(r.content))
    except Exception as e:
        return amc, dict(url=url, status=None, error=f"{type(e).__name__}: {str(e)[:120]}")
with cf.ThreadPoolExecutor(8) as ex:
    res = dict(ex.map(check, links.items()))
json.dump(res, open(os.path.join(ROOT, "raw", "link_check.json"), "w"), indent=1)
ok = sum(1 for v in res.values() if v.get("status") == 200 and v.get("mentions"))
print(f"::notice title=Link check::{ok}/{len(res)} return 200 and mention factsheets")
