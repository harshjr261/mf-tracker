"""SIP trend from AMFI Monthly Notes: contribution (Rs crore), contributing accounts (crore), SIP AUM (Rs lakh crore),
SIP share of industry AUM. Each note carries ~7 months; reading the latest notes gives 12+ months.
Writes raw/amfi_monthly/sip.json"""
import io, json, os, re, requests, pdfplumber
OUT = os.path.join(os.path.dirname(__file__), "..", "raw", "amfi_monthly"); os.makedirs(OUT, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (fund-lens monthly)", "Referer": "https://www.amfiindia.com/"}
page = requests.get("https://www.amfiindia.com/otherdata/amfi-monthlynote", headers=H, timeout=60).text
links = list(dict.fromkeys(re.findall(r"https://www\.amfiindia\.com/uploads/AMFI_Monthly_Note_[A-Za-z0-9_\-]+\.pdf", page.replace("\\/", "/"))))
path = os.path.join(OUT, "sip.json")
sip = json.load(open(path)) if os.path.exists(path) else {}
ROWS = {"accounts_cr": r"contributing SIP accounts", "contribution_cr": r"SIP monthly contribution",
        "aum_lakh_cr": r"SIP assets \(Rs", "share_pct": r"SIP assets as a percentage"}
read = 0
for url in links[:8]:
    try:
        pdf = pdfplumber.open(io.BytesIO(requests.get(url, headers=H, timeout=60).content))
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as e:  # noqa: BLE001
        print("skip", url, e); continue
    head = re.search(r"Contribution\s+((?:[A-Z][a-z]{2}-\d{2}\s*){4,})", text)
    if not head:
        continue
    months = re.findall(r"[A-Z][a-z]{2}-\d{2}", head.group(1))
    for key, rx in ROWS.items():
        m = re.search(rx + r"[^\n]*?((?:\s+[\d,]+(?:\.\d+)?){%d})\s*$" % len(months), text, re.M)
        if not m:
            continue
        vals = [float(v.replace(",", "")) for v in m.group(1).split()]
        for mo, v in zip(months, vals):
            sip.setdefault(mo, {}).setdefault(key, v)  # newest note wins (read first)
    read += 1
order = sorted(sip, key=lambda k: (int(k[4:]), ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"].index(k[:3])))
sip = {k: sip[k] for k in order}
json.dump(sip, open(path, "w"), indent=0)
print(f"::notice title=SIP::{read} notes read, {len(sip)} months ({order[0] if order else '-'} to {order[-1] if order else '-'})")
