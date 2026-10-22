"""Weekly pull of scheme facts from AMFI: actual TER, quarterly average AUM, fund managers, official benchmark.

Sources (all amfiindia.com):
  /api/populate-te-rdata-revised   daily TER per scheme: Base Expense Ratio + brokerage + transaction + levies
  /api/populate-mf, /api/populate-scheme   AMC and scheme ids
  /api/scheme-data?strOption=AUM   quarterly average AUM per plan (Rs lakh)
  portal.amfiindia.com/spages/SSD_<id>.xml   SEBI Scheme Summary Document (fund managers, benchmark, exit load)

Writes raw/scheme_info.json keyed by the AMFI code of each Direct Growth plan in raw/mf_universe_nav.json.gz.
"""
import concurrent.futures as cf
import datetime as dt
import gzip
import json
import os
import re
import time
import xml.etree.ElementTree as ET

import requests

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(ROOT, "raw")
API = "https://www.amfiindia.com/api"
H = {"User-Agent": "Mozilla/5.0 (fund-lens weekly refresh)", "Referer": "https://www.amfiindia.com/"}
S = requests.Session()


def get(url, as_json=True):
    for a in range(4):
        try:
            r = S.get(url, headers=H, timeout=60)
            r.raise_for_status()
            return r.json() if as_json else r.text
        except Exception:  # noqa: BLE001
            if a == 3:
                raise
            time.sleep(1.5 * (a + 1))


def norm(name: str) -> str:
    n = re.sub(r"\(.*?\)", " ", name or "")
    n = re.split(r"\s+-\s+|\s+-|-\s+", n)[0]
    n = re.sub(r"[^a-z0-9]", "", n.lower())
    return re.sub(r"fund$", "", n)


def norm_amc(a: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (a or "").lower().replace("mutual fund", ""))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ TER
def ter_rows():
    """Latest TER row per (MF_ID, scheme), from the current and previous month."""
    today = dt.date.today()
    months = [today.strftime("%m-%Y"), (today.replace(day=1) - dt.timedelta(days=1)).strftime("%m-%Y")]
    latest = {}
    for m in months:
        first = get(f"{API}/populate-te-rdata-revised?MF_ID=All&Month={m}&strCat=-1&strType=-1&page=1&pageSize=100")
        meta = first.get("meta") or {}
        pages = int(meta.get("pageCount") or 1)
        rows = list(first.get("data") or [])

        def page(p):
            return get(f"{API}/populate-te-rdata-revised?MF_ID=All&Month={m}&strCat=-1&strType=-1&page={p}&pageSize=100").get("data") or []
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            for chunk in ex.map(page, range(2, pages + 1)):
                rows.extend(chunk)
        for r in rows:
            k = (int(r["MF_ID"]), norm(r["Scheme_Name"]))
            if k not in latest or r["TER_Date"] > latest[k]["TER_Date"]:
                latest[k] = r
        print(f"TER {m}: {len(rows)} rows, {pages} pages")
        if len(latest) > 1200:  # current month already covers the universe
            break
    return latest


# ------------------------------------------------------------------ SSD + AUM
def text(root, tag):
    el = root.find(f".//{tag}")
    return re.sub(r"\s+", " ", el.text).strip() if el is not None and el.text else None


def ssd(sid):
    try:
        x = get(f"https://portal.amfiindia.com/spages/SSD_{sid}.xml", as_json=False)
        root = ET.fromstring(x.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return None
    codes = [int(c) for c in re.findall(r"\b(1\d{5})\b", text(root, "AMFI_Codes_To_be_phased_out") or "")]
    return dict(fm=text(root, "Fund_Manager_Name"), fmSince=text(root, "Fund_Manager_From_Date"),
                fmType=text(root, "Fund_Manager_Type_PrimaryComanageDescription"),
                bm1=text(root, "Benchmark_Tier_1"), bm2=text(root, "Benchmark_Tier_2"),
                exitLoad=text(root, "Exit_Load_if_applicable"), risk=text(root, "Riskometer_as_on_Date"),
                prc=text(root, "Potential_Risk_Class_as_on_date"), allot=text(root, "Allotment_Date"),
                sebi=text(root, "SEBI_Codes"), codes=codes)


def aum(mf, sid):
    try:
        rows = get(f"{API}/scheme-data?strMFId={mf}&strSDId={sid}&strOption=AUM")
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(rows, list) or not rows:
        return None
    tot = sum(fnum(r.get("Average_AUM_For_The_Quarter")) or 0 for r in rows)
    return dict(cr=round(tot / 100, 2), period=rows[0].get("As_At_The_End_Of"))


def main():
    t0 = time.time()
    d = json.load(gzip.open(os.path.join(RAW, "mf_universe_nav.json.gz")))
    uni = d["meta"]  # [code, name, amc, cat, isin]
    want = {}
    for code, name, amc, *_ in uni:
        want.setdefault((norm_amc(amc), norm(name.replace(" (plan inferred: Direct)", ""))), []).append(code)

    mfs = get(f"{API}/populate-mf")
    mf_by_norm = {norm_amc(m["mfName"]): int(m["mfId"]) for m in mfs}
    jobs = []  # (mf, sid, codes)
    for m in mfs:
        mf = int(m["mfId"])
        try:
            schemes = get(f"{API}/populate-scheme?MF_ID={mf}")
        except Exception:  # noqa: BLE001
            continue
        na = norm_amc(m["mfName"])
        for s in schemes:
            codes = want.get((na, norm(s["scheme_name"])))
            if codes:
                jobs.append((mf, s["scheme_id"], codes, s["scheme_name"]))
    print(f"Matched {len(jobs)} AMFI schemes to {sum(len(j[2]) for j in jobs)} of {len(uni)} funds")

    info = {}
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(lambda j: (j, ssd(j[1]), aum(j[0], j[1])), j): j for j in jobs}
        for f in cf.as_completed(futs):
            (mf, sid, codes, sname), sd, au = f.result()
            for c in codes:
                info[str(c)] = {"sid": sid, "mf": mf, "aum": au, **({k: v for k, v in (sd or {}).items() if k != "codes"})}

    ters = ter_rows()
    n_ter = 0
    for code, name, amc, *_ in uni:
        mf = mf_by_norm.get(norm_amc(amc))
        r = ters.get((mf, norm(name.replace(" (plan inferred: Direct)", "")))) if mf else None
        if r:
            n_ter += 1
            info.setdefault(str(code), {})["ter"] = {
                "date": r["TER_Date"][:10], "dBER": fnum(r.get("D_BER")), "dTER": fnum(r.get("D_TER")),
                "rBER": fnum(r.get("R_BER")), "rTER": fnum(r.get("R_TER"))}
    stats = dict(run=dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", funds=len(uni),
                 with_ssd=sum(1 for v in info.values() if v.get("fm")), with_aum=sum(1 for v in info.values() if v.get("aum")),
                 with_ter=n_ter, seconds=round(time.time() - t0))
    json.dump({"stats": stats, "info": info}, open(os.path.join(RAW, "scheme_info.json"), "w"), separators=(",", ":"))
    print(json.dumps(stats))
    print(f"::notice title=Scheme info::{json.dumps(stats)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc().strip().splitlines()
        print(f"::error title=fetch_scheme_info failed::{type(e).__name__}: {e} | " + " | ".join(tb[-4:]))
        raise
