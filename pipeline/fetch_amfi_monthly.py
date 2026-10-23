"""Download AMFI's monthly industry reports (category-wise flows, AUM, folios) for the last 14 months.
Files: raw/amfi_monthly/am<mon><yyyy>repo.xls — only missing ones are fetched."""
import datetime as dt, os, requests
OUT = os.path.join(os.path.dirname(__file__), "..", "raw", "amfi_monthly"); os.makedirs(OUT, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (fund-lens monthly)", "Referer": "https://www.amfiindia.com/"}
d = dt.date.today().replace(day=1); got = 0
for _ in range(14):
    d = (d - dt.timedelta(days=1)).replace(day=1)
    name = f"am{d.strftime('%b').lower()}{d.year}repo.xls"; path = os.path.join(OUT, name)
    if os.path.exists(path) and os.path.getsize(path) > 10000: continue
    r = requests.get(f"https://portal.amfiindia.com/spages/{name}", headers=H, timeout=60)
    if r.ok and len(r.content) > 10000 and not r.content[:200].lstrip().lower().startswith(b"<!doctype"):
        open(path, "wb").write(r.content); got += 1; print("saved", name, len(r.content))
    else:
        print("not available yet", name, r.status_code)
print(f"::notice title=AMFI monthly::{got} new report(s)")
