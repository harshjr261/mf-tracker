import json, os, requests
H = {"User-Agent": "Mozilla/5.0 (fund-lens probe)", "Referer": "https://www.amfiindia.com/"}
A = "https://www.amfiindia.com/api/"; out = {}
for q in ["sif-populate-ter-month?year=2026-2027", "sif-populate-ter-month?year=2025-2026", "sif-populate-sub-category?type=1", "sif-populate-sub-category?type=-1",
          "sif-populate-te-rdata-revised?SIF_Id=-1&Month=October-2026&strCat=-1&strType=-1&page=1&pageSize=50",
          "sif-populate-te-rdata-revised?SIF_Id=-1&Month=Oct-2026&strCat=-1&strType=1&page=1&pageSize=50",
          "sif-populate-te-rdata-revised?SIF_Id=13&Month=-1&strCat=-1&strType=-1&page=1&pageSize=50"]:
    r = requests.get(A + q, headers=H, timeout=60); out[q] = [r.status_code, r.text[:700]]
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "raw", "sif_probe8.json"), "w"), indent=1)
