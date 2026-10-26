import json, os, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept": "text/html,*/*"}
urls = {"Altiva (Edelweiss)": ["https://www.edelweissmf.com/altivaSIF", "https://www.edelweissmf.com/altivaSIF/docs/ALTIVA_SAI%2007112025.pdf"],
        "RedHex (HSBC)": ["https://www.assetmanagement.hsbc.co.in/en/sif", "https://www.assetmanagement.hsbc.co.in/"],
        "Arthaya (Union)": ["https://www.unionmf.com/", "https://www.unionmf.com/sif"],
        "Titanium (Tata)": ["https://www.tatamutualfund.com/sif"]}
out = {}
for k, us in urls.items():
    for u in us:
        try:
            r = requests.get(u, headers=H, timeout=40); out[u] = [k, r.status_code, len(r.content)]
        except Exception as e:  # noqa: BLE001
            out[u] = [k, "error", str(e)[:120]]
        print(out[u], u)
json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "raw", "sif_probe5.json"), "w"), indent=1)
