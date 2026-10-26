import json, os, requests
H = {"User-Agent": "Mozilla/5.0 (fund-lens probe)", "Referer": "https://www.amfiindia.com/"}
b = "https://www.amfiindia.com/api/nav-history?query_type="
out = {}
for q in ["historical_period&from_date=2025-10-01&to_date=2026-10-20&sd_id=120",
          "historical_period&from_date=2025-10-01&to_date=2026-10-20&sd_id=SIF120",
          "all_for_date&from_date=2026-10-23"]:
    r = requests.get(b + q, headers=H, timeout=60); t = r.text
    out[q] = [r.status_code, len(t), t[:500], ("Long-Short" in t or "Long - Short" in t), t[t.find("Altiva") - 300: t.find("Altiva") + 300] if "Altiva" in t else ""]
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "raw", "sif_probe4.json"), "w"), indent=1)
