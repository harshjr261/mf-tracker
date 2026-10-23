"""Industry money flows from AMFI monthly reports + SIP trend + AMC quarterly AUM -> docs/flows.json

Usage: python3 build_flows.py <raw/amfi_monthly dir> <out flows.json>
"""
import datetime as dt
import glob
import json
import os
import re
import sys

import xlrd

MON = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# AMFI moved to SEBI's revised categories from Aug 2026. Both layouts are mapped onto one continuous set;
# where the new layout splits an old row (Value vs Contra, Sectoral vs Thematic, Index/ETF sub-types) we add them back.
def canon(section, name):
    s, n = section.lower(), name.lower().replace("’", "'")
    if "debt" in s or "income" in s:
        g = "Debt"
        table = [("overnight", "Overnight"), ("liquid", "Liquid"), ("ultra short to short", "Low Duration"), ("ultra short", "Ultra Short Duration"),
                 ("low duration", "Low Duration"), ("money market", "Money Market"), ("medium to long", "Medium to Long Duration"),
                 ("short", "Short Duration"), ("medium", "Medium Duration"), ("long", "Long Duration"), ("dynamic", "Dynamic Bond"),
                 ("corporate", "Corporate Bond"), ("credit", "Credit Risk"), ("banking", "Banking & PSU"), ("10", "Gilt 10Y Constant"),
                 ("constant", "Gilt 10Y Constant"), ("gilt", "Gilt"), ("float", "Floater"), ("sectoral", "Debt Sectoral")]
    elif "equity" in s or "growth" in s:
        g = "Equity"
        table = [("multi", "Multi Cap"), ("large & mid", "Large & Mid Cap"), ("large", "Large Cap"), ("mid", "Mid Cap"), ("small", "Small Cap"),
                 ("flexi", "Flexi Cap"), ("dividend", "Dividend Yield"), ("value", "Value / Contra"), ("contra", "Value / Contra"),
                 ("focus", "Focused"), ("sector", "Sectoral / Thematic"), ("themat", "Sectoral / Thematic"), ("elss", "ELSS")]
    elif "hybrid" in s:
        g = "Hybrid"
        table = [("conservative", "Conservative Hybrid"), ("balanced advantage", "Balanced Advantage / DAA"), ("dynamic asset", "Balanced Advantage / DAA"),
                 ("balanced hybrid", "Aggressive / Balanced Hybrid"), ("aggressive", "Aggressive / Balanced Hybrid"), ("multi asset", "Multi Asset"),
                 ("arbitrage", "Arbitrage"), ("savings", "Equity Savings")]
    elif "life cycle" in s or "solution" in s:
        g = "Solution Oriented"
        table = [("life cycle", "Life Cycle"), ("retire", "Retirement"), ("child", "Children's")]
    else:
        g = "Passive & FoF"
        table = [("gold", "Gold ETF"), ("silver", "Other ETFs"), ("overseas", "FoF Overseas"), ("index", "Index Funds"), ("etf", "Other ETFs")]
        if "index" in s:
            return g, "Index Funds"
    for k, v in table:
        if k in n:
            return g, v
    return g, name


def parse_report(path):
    s = xlrd.open_workbook(path).sheet_by_index(0)
    section, closed, agg, totals, info = None, False, {}, {}, []
    for r in range(s.nrows):
        sr, name = str(s.cell_value(r, 0)).strip(), re.sub(r"\s+", " ", str(s.cell_value(r, 1))).strip()
        if sr == "B" or sr == "C":
            closed = True
        if name.lower().startswith("grand total"):
            totals["grand"] = [num(s.cell_value(r, c)) for c in range(2, 9)]
            continue
        if name.lower().startswith("fund of funds scheme (domestic)"):
            vals = [num(s.cell_value(r, c)) for c in range(2, 9)]
            if vals[4] is not None:  # shown by AMFI for information only, outside the grand total
                info.append(dict(group="Passive & FoF", cat="FoF Domestic", info=True, **dict(zip(("schemes", "folios", "inflow", "outflow", "net", "aum", "aaum"), [v or 0 for v in vals]))))
            continue
        if closed:
            continue
        if re.match(r"^[IVX]+$", sr):
            section = name
            continue
        if re.match(r"^[ivx]+$", sr) and section:
            vals = [num(s.cell_value(r, c)) for c in range(2, 9)]
            if vals[4] is None:
                continue
            g, label = canon(section, name)
            if "silver" in name.lower():  # separate from Aug 2026 only; old layouts fold silver into Other ETFs
                info.append(dict(group=g, cat="Silver ETF", info=True, **dict(zip(("schemes", "folios", "inflow", "outflow", "net", "aum", "aaum"), [v or 0 for v in vals]))))
            a = agg.setdefault((g, label), dict(group=g, cat=label, schemes=0, folios=0, inflow=0, outflow=0, net=0, aum=0, aaum=0))
            for k, v in zip(("schemes", "folios", "inflow", "outflow", "net", "aum", "aaum"), vals):
                a[k] += v or 0
    return list(agg.values()) + info, totals


def main(src, out):
    months = []
    for path in glob.glob(os.path.join(src, "am*repo.xls")):
        m = re.search(r"am([a-z]{3})(\d{4})repo", os.path.basename(path))
        if not m:
            continue
        rows, totals = parse_report(path)
        if rows:
            months.append((dt.date(int(m.group(2)), MON.index(m.group(1)) + 1, 1), rows, totals))
    months.sort(key=lambda x: x[0])
    months = months[-19:]  # 18 months shown + 1 for the opening AUM of the first
    cats = {}
    for d, rows, _ in months:
        key = d.strftime("%Y-%m")
        for r in rows:
            c = cats.setdefault(f"{r['group']}|{r['cat']}", {"group": r["group"], "cat": r["cat"], "m": {}, **({"info": True} if r.get("info") else {})})
            c["m"][key] = {k: (round(r[k], 2) if r[k] is not None else None) for k in ("net", "aum", "folios", "schemes", "inflow", "outflow")}
    groups = {}
    for d, rows, totals in months:
        key = d.strftime("%Y-%m")
        for r in [x for x in rows if not x.get("info")]:
            g = groups.setdefault(r["group"], {}).setdefault(key, {"net": 0.0, "aum": 0.0, "folios": 0.0})
            g["net"] += r["net"] or 0; g["aum"] += r["aum"] or 0; g["folios"] += r["folios"] or 0
    industry = {d.strftime("%Y-%m"): {"net": round(t["grand"][4], 2), "aum": round(t["grand"][5], 2), "folios": t["grand"][1]}
                for d, _, t in months if t.get("grand")}
    sip_path = os.path.join(src, "sip.json")
    sip = {}
    if os.path.exists(sip_path):
        for k, v in json.load(open(sip_path)).items():
            mo, yy = k.split("-")
            sip[f"20{yy}-{MON.index(mo.lower()) + 1:02d}"] = v
    aaum = json.load(open(os.path.join(src, "amc_aaum_quarterly.json"))) if os.path.exists(os.path.join(src, "amc_aaum_quarterly.json")) else []
    obj = dict(months=[d.strftime("%Y-%m") for d, _, _ in months], categories=list(cats.values()),
               groups={g: {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in m.items()} for g, m in groups.items()},
               industry=industry, sip=dict(sorted(sip.items())), amcQuarterly=aaum,
               sources=["AMFI Monthly Report (category-wise flows, AUM, folios)", "AMFI Monthly Note (SIP)", "AMFI Average AUM, fund-house wise (quarterly)"])
    json.dump(obj, open(out, "w"), separators=(",", ":"))
    print(f"flows: {len(obj['months'])} months ({obj['months'][0]} to {obj['months'][-1]}), {len(cats)} categories, SIP {len(sip)} months, AMC quarters {len(aaum)}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
