"""Self-contained HTML company report (v1.0).

The report is a single file with inline CSS and no external resources, so it
can be archived alongside a dataset release, opened offline, or printed to
PDF from a browser. Every figure shows its source date, method and
confidence class.
"""
from __future__ import annotations

import html
from pathlib import Path

from . import __version__
from .intelligence import company_profile, timeline
from .timeutil import utcnow

METRIC_LABELS = {
    "revenue": "Revenue 营业收入", "net_profit": "Net profit 净利润",
    "net_profit_parent": "Net profit, parent 归母净利润", "total_assets": "Total assets 资产总计",
    "total_liabilities": "Total liabilities 负债合计", "equity": "Equity 所有者权益",
    "operating_cash_flow": "Operating cash flow 经营现金流", "rd_expense": "R&D expense 研发费用",
    "employees": "Employees 员工人数",
}

CSS = """
:root{--fg:#1d1d1f;--muted:#6e6e73;--line:#e5e5ea;--bg:#fff;--accent:#9c1c24;--soft:#f5f5f7}
@media (prefers-color-scheme:dark){:root{--fg:#f5f5f7;--muted:#a1a1a6;--line:#38383a;--bg:#1c1c1e;--soft:#2c2c2e;--accent:#ff6b6b}}
body{font:14px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:var(--fg);background:var(--bg);margin:0}
main{max-width:980px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:17px;margin:36px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.sub{color:var(--muted);margin:0 0 20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.card{background:var(--soft);border-radius:10px;padding:12px 14px}.card b{display:block;font-size:18px}
.card span{color:var(--muted);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11px;background:var(--soft);color:var(--muted)}
.HIGH{color:#1a7f37}.MEDIUM{color:#9a6700}.LOW{color:#cf222e}.UNVALIDATED{color:var(--muted)}
.note{color:var(--muted);font-size:12px}footer{margin-top:40px;color:var(--muted);font-size:12px}
.wrap{overflow-x:auto}.chart{margin:12px 0;overflow-x:auto}.chart svg{max-width:100%;height:auto}td:first-child{white-space:nowrap}
"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def _num(x, digits=0) -> str:
    if x is None:
        return "–"
    if isinstance(x, float) and abs(x) >= 1e8:
        return f"{x / 1e8:,.2f} 亿"
    if isinstance(x, (int, float)):
        return f"{x:,.{digits}f}"
    return _e(x)


def _charts():
    from .charts import builders
    return builders


def _chart(build, min_points: int = 1) -> str:
    """An inline SVG chart (v1.5); empty when there is too little to plot."""
    from .charts.svg import render_svg
    try:
        spec = build()
    except Exception:
        return ""
    if sum(1 for s in spec.series for p in s.points if p.y is not None) < min_points:
        return ""
    spec.width = 720
    svg = render_svg(spec).replace(' xmlns="http://www.w3.org/2000/svg"', "")  # inline SVG needs no namespace
    return f"<div class='chart'>{svg}</div>"


def render_profile_html(code: str, as_of: str | None = None) -> str:
    p = company_profile(code, as_of)
    if "error" in p:
        raise ValueError(p["error"])
    ident = p["identity"]
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>{_e(ident['short_name_cn'] or ident['code'])} company report</title><style>{CSS}</style></head><body><main>"]
    parts.append(f"<h1>{_e(ident['short_name_cn'] or '')} {_e(ident['code'])}</h1>")
    parts.append(f"<p class='sub'>{_e(ident['legal_name_cn'])} · {_e(ident['exchange'])} {_e(ident['board'])}"
                 f" · information published up to <b>{_e(as_of or 'the latest available date')}</b></p>")

    reg = p["regulatory"]
    human = lambda x: x.replace("_", " ").capitalize() if x and x.isupper() else x
    cards = [("Listing status", human(reg["listing_status"].split(" (")[0]) + (" (" + reg["listing_status"].split(" (")[1] if " (" in reg["listing_status"] else "")),
             ("Trading status", human(reg["trading_status"].split(" (")[0]))]
    if p["capital"]:
        cards.append((f"Total shares ({p['capital']['date']})", _num(p["capital"]["total_shares"])))
    if p["market_last"]:
        cards.append((f"Last close ({p['market_last']['date']})", _num(p["market_last"]["close"], 2)))
    cards.append(("Validation flags", sum(p["validation_flags"].values()) if p["validation_flags"] else 0))
    parts.append("<div class='grid'>" + "".join(f"<div class='card'><span>{_e(k)}</span><b>{_e(v)}</b></div>"
                                                 for k, v in cards) + "</div>")

    # Financials
    parts.append("<h2>Financial history (fiscal years)</h2>")
    fin = p["financials_fy"]
    if fin:
        parts.append(_chart(lambda: _charts().financial_chart(code, ["revenue", "net_profit_parent"], as_of=as_of)))
        periods = sorted({pt["period"] for s in fin.values() for pt in s})
        parts.append("<div class='wrap'><table><tr><th>Metric</th>" + "".join(f"<th>{_e(x[:4])}</th>" for x in periods) + "</tr>")
        for m, s in fin.items():
            byp = {pt["period"]: pt for pt in s}
            cells = []
            for per in periods:
                pt = byp.get(per)
                if not pt:
                    cells.append("<td class='n'>–</td>")
                    continue
                mark = " ↻" if pt["restated"] else ""
                cells.append(f"<td class='n' title='{_e(pt['method'])}, published {_e(pt['published'])}, "
                             f"{pt['vintages']} vintage(s)'><span class='{pt['confidence_class']}'>{_num(pt['value'])}</span>{mark}</td>")
            parts.append(f"<tr><td>{_e(METRIC_LABELS.get(m, m))}</td>{''.join(cells)}</tr>")
        parts.append("</table></div><p class='note'>Colour shows confidence class "
                     "(<span class='HIGH'>high</span>, <span class='MEDIUM'>medium</span>, <span class='LOW'>low</span>). "
                     "↻ marks a period whose value differs between documents (restatement or extraction difference). "
                     "Hover a value for its method and publication date.</p>")
    else:
        parts.append("<p class='note'>No financial facts extracted yet.</p>")

    # Industry (v1.1)
    if p.get("industry"):
        parts.append("<h2>Industry</h2><table><tr><th>Scheme</th><th>Level 1</th><th>Level 2</th><th>Since</th><th>Source</th></tr>")
        for sch, v in p["industry"].items():
            parts.append(f"<tr><td>{_e(sch)}</td><td>{_e(v['level1'])}</td><td>{_e(v['level2'])}</td>"
                         f"<td>{_e(v['since'])}</td><td>{_e(v['source'])}</td></tr>")
        parts.append("</table>")

    # Board and management (v1.1)
    g = p.get("governance")
    if g:
        parts.append("<h2>Board and management</h2>")
        ratio = f"{g['independence_ratio']:.0%}" if g.get("independence_ratio") is not None else "–"
        cards = [("Board size", g["board_size"]), ("Independent directors", f"{g['independent_directors']} ({ratio})"),
                 ("Chair", "、".join(g["chair"]) or "–"), ("General manager", "、".join(g["general_manager"]) or "–"),
                 ("CEO duality", {True: "Yes", False: "No", None: "–"}[g["ceo_duality"]]),
                 ("Key-role departures, 12 months", sum(g["key_role_departures_12m"].values()))]
        parts.append("<div class='grid'>" + "".join(f"<div class='card'><span>{_e(k)}</span><b>{_e(v)}</b></div>"
                                                     for k, v in cards) + "</div>")
        parts.append("<table style='margin-top:12px'><tr><th>Check</th><th>Result</th><th>Reference</th></tr>" +
                     "".join(f"<tr><td>{_e(ch['rule'])}</td><td>{_e(ch['result'])}</td><td>{_e(ch['reference'])}</td></tr>"
                             for ch in g["legal_reference_checks"]) + "</table>")
        parts.append(f"<p class='note'>Roster as reported on {_e(g['base_roster_date'] or 'no roster date')}, updated by "
                     "later appointment and resignation announcements. Checks are screening aids, not legal conclusions.</p>")

    # Segments (v1.2)
    seg = p.get("segments")
    if seg:
        parts.append(f"<h2>Business segments ({_e(seg['period'])})</h2>")
        if "PRODUCT" in (seg.get("dimensions") or {}):
            parts.append(_chart(lambda: _charts().segment_chart(code, "PRODUCT", seg["period"], as_of)))
        labels = {"INDUSTRY": "By industry", "PRODUCT": "By product", "REGION": "By region",
                  "SALES_MODEL": "By sales model", "REPORTABLE_SEGMENT": "Reportable segments"}
        for dim, v in seg["dimensions"].items():
            extra = ""
            if v.get("regional"):
                extra = f" · overseas share {v['regional']['overseas_share']:.1%}"
            hhi = f" · HHI {v['hhi']:.2f}" if v.get("hhi") is not None else ""
            parts.append(f"<p class='note'><b>{_e(labels.get(dim, dim))}</b>{hhi}{extra}</p><table>"
                         "<tr><th>Segment</th><th>Revenue</th><th>Share</th><th>Growth</th><th>Gross margin</th></tr>")
            for sgm in v["segments"]:
                pct = lambda x: f"{x:.1%}" if x is not None else "–"
                parts.append(f"<tr><td>{_e(sgm['name'])}</td><td class='n'>{_num(sgm['revenue'])}</td>"
                             f"<td class='n'>{pct(sgm['share'])}</td><td class='n'>{pct(sgm['yoy'])}</td>"
                             f"<td class='n'>{pct(sgm['gross_margin'])}</td></tr>")
            parts.append("</table>")

    # Group structure (v1.2)
    grp = p.get("group")
    if grp:
        sm = grp["summary"]
        parts.append(f"<h2>Group structure ({_e(grp['date'])})</h2>")
        cards = [("Subsidiaries", sm["subsidiaries"]), ("Wholly owned", sm["wholly_owned"]),
                 ("Associates and JVs", sm["associates_and_jvs"]), ("Offshore entities", len(sm["offshore_entities"]))]
        parts.append("<div class='grid'>" + "".join(f"<div class='card'><span>{_e(k)}</span><b>{_e(v)}</b></div>"
                                                     for k, v in cards) + "</div>")
        parts.append("<p class='note'>Subsidiaries by jurisdiction: " +
                     ", ".join(f"{_e(k.replace('_', ' ').lower())} {v}" for k, v in sm["by_jurisdiction"].items()) + ".")
        if sm["offshore_entities"]:
            parts.append(" Offshore: " + _e("、".join(sm["offshore_entities"])) + ".")
        if sm["consolidated_below_50pct"]:
            parts.append(" Consolidated with 50% or less (control by other means, for review): " +
                         _e("、".join(sm["consolidated_below_50pct"])) + ".")
        parts.append("</p>")

    # R&D and people (v1.3)
    hcp = p.get("human_capital")
    if hcp:
        v, dv = hcp["values"], hcp["derived"]
        pct = lambda x: f"{x:.1%}" if x is not None else "–"
        parts.append(f"<h2>R&amp;D and people ({_e(hcp['period'])})</h2>")
        parts.append(_chart(lambda: _charts().history_chart(code, ["rd_investment"]), min_points=2))
        cards = [("R&D investment", _num(v.get("rd_investment"))), ("R&D intensity", pct(dv.get("rd_intensity_reported") or dv.get("rd_intensity_computed"))),
                 ("Capitalised share of R&D", pct(dv.get("rd_capitalisation_share"))), ("Employees", _num(v.get("employees_total"))),
                 ("R&D staff share", pct(dv.get("rd_staff_share"))), ("Postgraduate share", pct(dv.get("postgraduate_share"))),
                 ("Patents granted (cumulative)", _num(v.get("patents_granted_cum")))]
        parts.append("<div class='grid'>" + "".join(f"<div class='card'><span>{_e(k)}</span><b>{_e(x)}</b></div>"
                                                     for k, x in cards if x not in ("–",)) + "</div>")

    # ESG (v1.3)
    esg = p.get("esg")
    if esg:
        parts.append(f"<h2>ESG ({_e(esg['year'])})</h2><table><tr><th>Pillar</th><th>Item</th><th>Value</th></tr>")
        names = {"key_pollutant_discharge_unit": "Key pollutant-discharge unit", "emission_cod": "COD emissions (t)",
                 "emission_ammonia_nitrogen": "Ammonia nitrogen (t)", "emission_so2": "SO₂ (t)", "emission_nox": "NOₓ (t)",
                 "emission_particulates": "Particulates (t)", "ghg_emissions": "Greenhouse gases (tCO₂e)",
                 "ghg_reduction": "GHG reduction (tCO₂e)", "environmental_investment": "Environmental investment",
                 "donations": "Donations", "rural_revitalisation": "Rural revitalisation"}
        for pillar, key in (("E", "environmental"), ("S", "social")):
            for item, x in esg[key].items():
                if isinstance(x, dict) and "value" in x:
                    val = ("Yes" if x["value"] else "No") if item == "key_pollutant_discharge_unit" else _num(x["value"])
                    parts.append(f"<tr><td>{pillar}</td><td>{_e(names.get(item, item))}</td><td class='n'>{_e(val)}</td></tr>")
        envr = esg["environmental"]["environmental_regulatory_actions"]
        parts.append(f"<tr><td>E</td><td>Environmental regulatory actions</td><td class='n'>{len(envr)}</td></tr>")
        g = esg["governance"]
        if g.get("independence_ratio") is not None:
            parts.append(f"<tr><td>G</td><td>Board independence</td><td class='n'>{g['independence_ratio']:.0%}</td></tr>")
        parts.append(f"<tr><td>G</td><td>Securities regulatory actions in year</td><td class='n'>{g['securities_regulatory_actions']}</td></tr>")
        rep_ = esg["reporting"]
        parts.append(f"<tr><td>–</td><td>Sustainability report</td><td class='n'>{'Published' if rep_['sustainability_report_published'] else 'Not observed'}</td></tr>")
        for prov, r in esg["ratings"].items():
            parts.append(f"<tr><td>–</td><td>Rating: {_e(prov)} ({_e(r['date'])})</td><td class='n'>{_e(r['rating'] or r['score'])}</td></tr>")
        parts.append("</table><p class='note'>Disclosed data only; no composite ESG score is computed.</p>")

    # Ownership
    parts.append("<h2>Shareholders and capital</h2>")
    if p["capital"]:
        c = p["capital"]
        parts.append(f"<p>Total {_num(c['total_shares'])} · tradable {_num(c['tradable_shares'])} · restricted "
                     f"{_num(c['restricted_shares'])} · treasury {_num(c['treasury_shares'])} "
                     f"<span class='tag'>{_e(c['source'])}, {_e(c['date'])}</span></p>")
    if p["top_shareholders"]:
        t = p["top_shareholders"]
        parts.append(f"<p class='note'>Top shareholders at {_e(t['date'])}</p><div class='wrap'><table>"
                     "<tr><th>#</th><th>Shareholder</th><th>Shares</th><th>%</th><th>Pledged</th><th></th></tr>")
        for h in t["holders"]:
            role = "controlling" if h["controlling"] else ("actual controller" if h["actual_controller"] else "")
            parts.append(f"<tr><td>{_e(h['rank'])}</td><td>{_e(h['shareholder'])}</td><td class='n'>{_num(h['shares'])}</td>"
                         f"<td class='n'>{_num(h['pct'], 2)}</td><td class='n'>{_num(h['pledged'])}</td><td>{_e(role)}</td></tr>")
        parts.append("</table></div>")
    if not p["capital"] and not p["top_shareholders"]:
        parts.append("<p class='note'>No ownership or capital observations imported.</p>")

    # Regulatory
    parts.append("<h2>Regulatory and legal</h2>")
    rows = []
    for inv in reg["investigations"]:
        rows.append((inv["date"], "Investigation", inv["state"].replace("_", " ").lower(), inv["authority"]))
    for pen in reg["penalties"]:
        rows.append((pen["date"], f"Penalty ({pen['status'].lower()})", f"{_num(pen['fine_total'])} total fines",
                     pen["document_number"]))
    for a in reg["non_standard_audit_opinions"]:
        rows.append((a["date"], "Audit opinion", a["opinion"].replace("_", " ").lower(), ""))
    for l in reg["litigation_open"]:
        rows.append((l["date"], l["type"].title() + " (open)", f"{_num(l['amount'])} in dispute", l["role"] or ""))
    if rows:
        parts.append("<table><tr><th>Date</th><th>Matter</th><th>State</th><th>Detail</th></tr>" +
                     "".join(f"<tr><td>{_e(d)}</td><td>{_e(m)}</td><td>{_e(s)}</td><td>{_e(x)}</td></tr>"
                             for d, m, s, x in sorted(rows, key=lambda r: r[0] or "")) + "</table>")
        parts.append("<p class='note'>'Possibly open' means no later decision or closure has been observed; "
                     "it is not a finding that the matter is open.</p>")
    else:
        parts.append("<p class='note'>No regulatory or legal events recorded.</p>")

    # Timeline
    parts.append("<h2>Timeline</h2>")
    items = [i for i in timeline(code, until=as_of) if i["layer"] in ("corporate_action", "regulatory", "reconciliation")]
    if items:
        parts.append("<div class='wrap'><table><tr><th>Date</th><th>Layer</th><th>Event</th><th>Status</th><th>Detail</th></tr>")
        for i in items[-60:]:
            detail = ", ".join(f"{k}: {_num(v, 4) if isinstance(v, float) and abs(v) < 1000 else _num(v)}"
                               for k, v in i["detail"].items())
            parts.append(f"<tr><td>{_e(i['date'])}</td><td>{_e(i['layer'].replace('_', ' '))}</td>"
                         f"<td>{_e(i['type'].replace('_', ' ').lower())}</td><td>{_e((i['status'] or '').lower())}</td>"
                         f"<td>{_e(detail)}</td></tr>")
        parts.append("</table></div>")
    else:
        parts.append("<p class='note'>No events recorded.</p>")

    if p["validation_flags"]:
        parts.append("<h2>Validation flags</h2><table><tr><th>Flag</th><th>Count</th></tr>" +
                     "".join(f"<tr><td>{_e(k)}</td><td class='n'>{v}</td></tr>" for k, v in sorted(p["validation_flags"].items())) +
                     "</table><p class='note'>Flags never change the data; see <code>show-flags</code> for details.</p>")
    parts.append(f"<footer>Generated {utcnow().isoformat(timespec='seconds')} UTC by A-share Company Intelligence "
                 f"v{__version__}. Sources: CNINFO disclosures and the datasets imported into this database. "
                 f"Public market feeds are not exchange-authoritative.</footer></main></body></html>")
    return "".join(parts)


def write_profile_report(code: str, out: str | None = None, as_of: str | None = None) -> str:
    html_text = render_profile_html(code, as_of)
    path = Path(out or f"reports/{str(code).zfill(6)}{'_' + as_of if as_of else ''}.html")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    return str(path)
