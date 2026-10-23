"""Last-12-month headlines for every AMC and every fund manager, from Google News RSS search.
Merges with the previous docs/news.json so items older than the RSS window are kept until they turn 12 months old.
Writes docs/news.json: {"asOf", "amc": {amc: [items]}, "mgr": {"name|amc": [items]}}; item = {t, s, u, d}"""
import datetime as dt, email.utils, json, os, re, sys, time, urllib.parse
import xml.etree.ElementTree as ET
import requests

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "docs", "news.json")
H = {"User-Agent": "Mozilla/5.0 (fund-lens news)"}
CUT = dt.datetime.utcnow() - dt.timedelta(days=365)
PER = 25
# fund-tracker SEO pages, not news
JUNK = re.compile(r"Review 20\d\d|NAV,? Returns|NAV Today|Should You Invest|NAV & |Direct (Plan|Growth)( - Growth)?$|Fund Details|Portfolio & S|SIP Calculator", re.I)


def short_amc(a):
    s = re.sub(r"\s+mutual fund$", "", a, flags=re.I).strip()
    return {"ICICI Prudential": "ICICI Prudential", "Aditya Birla Sun Life": "Aditya Birla", "Kotak Mahindra": "Kotak",
            "Franklin Templeton": "Franklin Templeton", "Nippon India": "Nippon India", "PPFAS": "PPFAS"}.get(s, s)


def search(q):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:1y", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})
    for attempt in range(3):
        try:
            r = requests.get(url, headers=H, timeout=30)
            if r.status_code == 200:
                break
            time.sleep(5 * (attempt + 1))
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
    else:
        return None
    items = []
    for it in ET.fromstring(r.content).iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        try:
            d = email.utils.parsedate_to_datetime(it.findtext("pubDate")).replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            continue
        if d < CUT or not title:
            continue
        items.append({"t": title, "s": src, "u": it.findtext("link"), "d": d.strftime("%Y-%m-%d")})
    return items


def merge(old, new):
    seen, out = set(), []
    for it in sorted((new or []) + (old or []), key=lambda x: x["d"], reverse=True):
        k = re.sub(r"\W+", "", it["t"].lower())[:80]
        if k in seen or it["d"] < CUT.strftime("%Y-%m-%d") or JUNK.search(it["t"]):
            continue
        seen.add(k); out.append(it)
    return out[:PER]


def main():
    data = json.load(open(os.path.join(ROOT, "docs", "data.json")))
    amcs = sorted({f["amc"] for f in data["funds"]})
    mgrs = sorted(data.get("managers", {}))
    prev = json.load(open(OUT)) if os.path.exists(OUT) else {"amc": {}, "mgr": {}}
    res = {"asOf": dt.date.today().isoformat(), "amc": {}, "mgr": {}, "failed": 0}
    for a in amcs:
        got = search(f'"{a}"')
        res["failed"] += got is None
        res["amc"][a] = merge(prev["amc"].get(a), got)
        time.sleep(1.2)
    for k in mgrs:
        name, amc = k.split("|", 1)
        got = search(f'"{name}" "{short_amc(amc)}"')
        res["failed"] += got is None
        res["mgr"][k] = merge(prev["mgr"].get(k), got)
        time.sleep(1.2)
    json.dump(res, open(OUT, "w"), separators=(",", ":"), ensure_ascii=False)
    n_a = sum(bool(v) for v in res["amc"].values()); n_m = sum(bool(v) for v in res["mgr"].values())
    print(f"::notice title=News::{len(amcs)} AMCs searched ({n_a} with news), {len(mgrs)} managers searched ({n_m} with news), {res['failed']} failed queries")
    if res["failed"] > (len(amcs) + len(mgrs)) // 2:
        sys.exit("Most news queries failed")


if __name__ == "__main__":
    main()
