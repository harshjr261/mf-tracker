import json, os, requests, itertools
H = {"User-Agent": "Mozilla/5.0 (fund-lens probe)", "Referer": "https://www.amfiindia.com/"}
A = "https://www.amfiindia.com/api/sif-populate-te-rdata-revised"; out = {}
for sid, cat, typ in itertools.product(["-1", "47", ""], ["-1", "Equity Oriented Investment Strategies", ""], ["-1", "1", ""]):
    p = {"SIF_Id": sid, "Month": "10-2026", "strCat": cat, "strType": typ, "page": 1, "pageSize": 100}
    r = requests.get(A, headers=H, params=p, timeout=60); out[f"{sid}|{cat}|{typ}"] = [r.status_code, r.text[:300]]
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "raw", "sif_probe9.json"), "w"), indent=1)
