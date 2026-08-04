"""Generovani webu. Vsechny stranky sdili design z theme.py (prevzaty z PoC)."""
from __future__ import annotations

import csv
import html
import io
import json
from datetime import date, datetime

from .theme import page, tabs, topbar

MONTHS = ["", "led", "úno", "bře", "dub", "kvě", "čvn",
          "čvc", "srp", "zář", "říj", "lis", "pro"]

LABELS = {
    "icp_match": "obor sedí na naše ICP",
    "service_match": "děláme přesně tohle",
    "keyword_match": "naše témata v popisu",
    "seniority": "seniorita",
    "function_fit": "má na starosti naše téma",
    "company_size": "velikost firmy",
    "event_role": "role na eventu",
    "location": "místo",
    "format": "formát",
    "organizer": "pořadatel",
    "key_account_bonus": "je to náš key account",
    "llm_adjust": "korekce od AI",
}

ORIGIN_LABEL = {
    "confirmed": ("high", "z webu eventu"),
    "inferred": ("", "odvozeno AI"),
    "guessed": ("low", "odhad, ověř"),
}


def _e(v) -> str:
    return html.escape(str(v)) if v not in (None, "") else ""


def _date_lead(iso: str | None) -> str:
    if not iso:
        return '<span class="mon">termín<br>neuveden</span>'
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return f'<span class="mon">{_e(iso)}</span>'
    delta = (d - date.today()).days
    rel = ""
    if 0 <= delta <= 60:
        cls = " soon" if delta <= 7 else ""
        txt = "DNES" if delta == 0 else ("ZÍTRA" if delta == 1 else f"ZA {delta} DNÍ")
        rel = f'<span class="relative{cls}">{txt}</span>'
    return (f'<span class="day">{d.day}</span>'
            f'<span class="mon">{MONTHS[d.month]} {str(d.year)[2:]}</span>{rel}')


def _why_panel(pid: str, breakdown: dict, maxes: dict, note: str) -> str:
    rows = []
    for key, val in breakdown.items():
        cap = maxes.get(key) or 25
        pct = max(0, min(100, round(abs(val) / cap * 100)))
        neg = ' class="neg"' if val < 0 else ""
        rows.append(f'<tr><td>{_e(LABELS.get(key, key))}</td>'
                    f'<td><span class="bar"{neg}><i style="width:{pct}%"></i></span></td>'
                    f'<td>{val:+d}</td></tr>')
    return (f'<div class="why" id="{pid}" data-open="0"><table>{"".join(rows)}</table>'
            f'<p class="foot">{note}</p></div>')


def _maxes(icp_cfg: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for block in ("rubric", "event_rubric"):
        for k, v in icp_cfg.get(block, {}).items():
            vals = [x for x in v.values() if isinstance(x, int)]
            out[k] = max(vals) if vals else 25
    out["keyword_match"] = 15
    out["key_account_bonus"] = icp_cfg.get("key_account_bonus", 10)
    out["llm_adjust"] = icp_cfg.get("llm_adjust_max", 10)
    return out


WHY_JS = """
document.querySelectorAll('[data-why]').forEach(function(b){
  b.addEventListener('click',function(){
    var p=document.getElementById(b.dataset.why),o=p.dataset.open==='1';
    p.dataset.open=o?'0':'1';b.setAttribute('aria-expanded',String(!o));
    b.textContent=o?'Proč tohle číslo?':'Skrýt rozpad';});});
"""


def _demo_banner(mock: bool) -> str:
    """V mock rezimu musi byt na kazde strance videt, ze data jsou smyslena."""
    if not mock:
        return ""
    return ('<div class="demo-banner"><b>Ukázková data</b>'
            "<span>Tyhle eventy a lidé <strong>neexistují</strong>. Jde o testovací "
            "data pro běh bez API klíče. Ostrá data se generují do <code>docs/</code>, "
            "tohle je <code>demo/</code>.</span></div>")


def _setup_warning(warnings) -> str:
    """Nevyplnena konfigurace se musi ukazat, ne schovat do logu."""
    if not warnings:
        return ""
    items = "".join(f"<li>{_e(w)}</li>" for w in warnings)
    return (f'<div class="callout amber"><b>Nedodělaná konfigurace</b>'
            f'<span><ul style="margin:4px 0 0;padding-left:18px">{items}</ul></span></div>')


def _engine_tag(mock: bool) -> str:
    return ('<span class="tag mock">MOCK — bez API klíče</span>' if mock
            else '<span class="tag live">Claude API aktivní</span>')


# ================================================================== UC1
LIST_JS = WHY_JS + """
(function(){
  var rows=[].slice.call(document.querySelectorAll('.row[data-search]'));
  var g=function(id){return document.getElementById(id)};
  var q=g('q'),topic=g('f-topic'),city=g('f-city'),fmt=g('f-format'),
      org=g('f-org'),when=g('f-when'),score=g('f-score');
  var pills=[].slice.call(document.querySelectorAll('.pill[data-flag]'));
  function horizon(n){var d=new Date();d.setDate(d.getDate()+n);return d.toISOString().slice(0,10);}
  function apply(){
    var t=(q.value||'').trim().toLowerCase(),min=parseInt(score.value||0,10);
    var lim=when.value?horizon(parseInt(when.value,10)):null;
    var today=new Date().toISOString().slice(0,10),n=0;
    var flags={};pills.forEach(function(p){if(p.classList.contains('active'))flags[p.dataset.flag]=1;});
    rows.forEach(function(r){
      var d=r.dataset,ok=true;
      if(t&&d.search.indexOf(t)<0)ok=false;
      if(topic.value&&d.topic!==topic.value)ok=false;
      if(city.value&&d.city!==city.value)ok=false;
      if(fmt.value&&d.format!==fmt.value)ok=false;
      if(org.value&&d.org!==org.value)ok=false;
      if(parseInt(d.score,10)<min)ok=false;
      if(flags.free&&d.price!=='free')ok=false;
      if(flags.ka&&d.ka!=='1')ok=false;
      if(flags.recon&&d.recon!=='1')ok=false;
      if(lim&&d.date&&(d.date<today||d.date>lim))ok=false;
      r.style.display=ok?'':'none';if(ok)n++;});
    g('shown').textContent=n;
    g('empty').style.display=n?'none':'block';
  }
  [q,topic,city,fmt,org,when].forEach(function(el){
    el.addEventListener(el.tagName==='INPUT'?'input':'change',apply);});
  score.addEventListener('input',function(){g('score-val').textContent=score.value;apply();});
  pills.forEach(function(p){p.addEventListener('click',function(){
    p.classList.toggle('active');apply();});});
  apply();
})();
"""


def _opts(values, label):
    return (f'<option value="">{label}</option>'
            + "".join(f'<option value="{_e(v)}">{_e(v)}</option>' for v in values))


def html_event_list(events, icp_cfg, new_uids=None, mock=True, cfg_warnings=None):
    top_t = icp_cfg["thresholds"]["event_top"]
    mid_t = icp_cfg["thresholds"]["event_maybe"]
    new_uids = new_uids or set()
    maxes = _maxes(icp_cfg)
    events = sorted(events, key=lambda e: (e.date or "9999", -e.score))

    hero = max(events, key=lambda e: e.score, default=None)
    if hero and hero.score < mid_t:
        hero = None

    def row(e, idx):
        num_cls = "high" if e.score >= top_t else ("low" if e.score < mid_t else "")
        search = " ".join(filter(None, [e.name, e.summary, e.description, e.organizer,
                                        e.city, " ".join(e.key_accounts)])).lower()
        badges = []
        if e.uid in new_uids:
            badges.append('<span class="badge badge-new">nové</span>')
        if e.format:
            badges.append(f'<span class="badge badge-format">{_e(e.format)}</span>')
        if e.topic:
            badges.append(f'<span class="badge badge-topic">{_e(e.topic)}</span>')
        for ka in e.key_accounts:
            badges.append(f'<span class="badge badge-key">{_e(ka)}</span>')

        meta = []
        if e.city:
            meta.append(f"<span>{_e(e.city)}</span>")
        if e.organizer:
            meta.append(f"<span>{_e(e.organizer)}</span>")
        if e.price == "free":
            meta.append('<span class="free">zdarma</span>')
        if e.source:
            meta.append(f'<span class="sep">·</span><span>{_e(e.source)}</span>')

        btn = (f'<a class="btn btn-primary btn-sm" href="{_e(e.recon_file)}">Recon →</a>'
               if e.has_recon and e.recon_file
               else '<span class="btn btn-sm" style="opacity:.4">Recon zatím ne</span>')
        pid = f"we{idx}"
        return f"""<article class="row" data-search="{_e(search)}" data-topic="{_e(e.topic)}"
  data-city="{_e(e.city)}" data-format="{_e(e.format)}" data-org="{_e(e.organizer)}"
  data-score="{e.score}" data-date="{_e(e.date)}" data-price="{_e(e.price)}"
  data-ka="{'1' if e.key_accounts else '0'}" data-recon="{'1' if e.has_recon else '0'}">
  <div class="row-lead">{_date_lead(e.date)}</div>
  <div class="row-main">
    <div class="row-badges">{"".join(badges)}</div>
    <a class="row-title" href="{_e(e.url)}" target="_blank" rel="noopener">{_e(e.name)}
      <span class="arrow">↗</span></a>
    <div class="row-meta">{"".join(meta)}</div>
    <p class="row-desc">{_e(e.summary) or _e((e.description or "")[:190])}</p>
    <div class="row-actions">{btn}
      <button class="btn btn-sm" type="button" data-why="{pid}" aria-expanded="false">Proč tohle číslo?</button>
    </div>
    {_why_panel(pid, e.score_breakdown, maxes,
                "Body počítá pevná tabulka v config/icp.yaml, ne AI.")}
  </div>
  <div class="row-side">
    <div class="row-lead" style="text-align:right">
      <span class="num {num_cls}">{e.score}</span><span class="lbl">skóre</span></div>
  </div>
</article>"""

    hero_html = ""
    if hero:
        hero_html = f"""<div class="hero-card">
  <div class="hero-main">
    <a class="row-title" href="{_e(hero.url)}" target="_blank" rel="noopener">{_e(hero.name)}</a>
    <div class="row-meta"><span>{_e(hero.date) or 'termín neuveden'}</span>
      <span class="sep">·</span><span>{_e(hero.city)}</span></div>
    <p class="row-desc" style="margin:0">{_e(hero.summary) or ''}</p>
  </div>
  <div class="hero-score"><span class="num">{hero.score}</span><span class="lbl">skóre</span></div>
</div>"""

    n_top = len([e for e in events if e.score >= top_t])
    n_mid = len([e for e in events if mid_t <= e.score < top_t])
    n_ka = len([e for e in events if e.key_accounts])
    n_recon = len([e for e in events if e.has_recon])

    setup = _demo_banner(mock) + _setup_warning(cfg_warnings)
    body = f"""{topbar(f'<span class="tag"><strong>{len(events)}</strong> eventů</span>'
                       f'<span class="tag"><strong>{len(new_uids)}</strong> nových</span>'
                       + _engine_tag(mock))}
<h1>Eventy, <span class="black">kam se vyplatí jít.</span></h1>
<p class="subtitle">Automatický přehled tech a business eventů v Dánsku — filtrováno podle
našich ICP, oskórováno podle relevance. U vybraných je připravený recon:
koho tam potkat a co mu říct.</p>
{tabs("events", {"events": len(events), "watch": n_ka})}
<div class="stats">
  <div class="stat-item"><span class="stat-num accent">{n_top}</span>
    <span class="stat-label">nenech si ujít</span></div>
  <div class="stat-item"><span class="stat-num">{n_mid}</span>
    <span class="stat-label">stojí za zvážení</span></div>
  <div class="stat-item"><span class="stat-num red">{n_ka}</span>
    <span class="stat-label">s key accountem</span></div>
  <div class="stat-item"><span class="stat-num">{n_recon}</span>
    <span class="stat-label">s reconem</span></div>
  <div class="stat-item"><span class="stat-num" id="shown">{len(events)}</span>
    <span class="stat-label">zobrazeno</span></div>
</div>
<div class="filter-group">
  <input id="q" type="search" placeholder="Hledat název, téma, firmu…">
  <span class="select-wrap"><select id="f-topic">
    {_opts(sorted({e.topic for e in events if e.topic}), "Všechna témata")}</select></span>
  <span class="select-wrap"><select id="f-city">
    {_opts(sorted({e.city for e in events if e.city}), "Všechna města")}</select></span>
  <span class="select-wrap"><select id="f-format">
    {_opts(sorted({e.format for e in events if e.format}), "Všechny formáty")}</select></span>
  <span class="select-wrap"><select id="f-org">
    {_opts(sorted({e.organizer for e in events if e.organizer}), "Všichni pořadatelé")}</select></span>
  <span class="select-wrap"><select id="f-when"><option value="">Kdykoli</option>
    <option value="7">Do 7 dnů</option><option value="14">Do 14 dnů</option>
    <option value="30">Do 30 dnů</option><option value="90">Do 90 dnů</option></select></span>
</div>
<div class="filter-group">
  <button class="pill" data-flag="free" type="button">Zdarma</button>
  <button class="pill" data-flag="ka" type="button">Jen s key accountem</button>
  <button class="pill" data-flag="recon" type="button">Jen s reconem</button>
  <span class="tag">Min. skóre <strong id="score-val">0</strong></span>
  <input id="f-score" type="range" min="0" max="100" value="0" step="5" style="width:150px">
  <span class="spacer"></span>
  <a class="btn btn-sm" href="events.csv" download>Stáhnout CSV</a>
  <button class="btn btn-sm" type="button" onclick="window.print()">Tisk</button>
</div>
{setup}{hero_html}
<div class="empty-state" id="empty" style="display:none">Žádný event neodpovídá filtrům.</div>
<div class="section-header"><h2 class="section-title"><span class="marker"></span>Všechny eventy</h2>
  <span class="section-count">seřazeno podle data</span></div>
{"".join(row(e, i) for i, e in enumerate(events))}
<footer><span>Aktualizováno {datetime.now():%d.%m.%Y %H:%M}</span>
  <span>Skóre 0–100 podle config/icp.yaml</span>
  <span>Zdroje: {", ".join(sorted({e.source for e in events if e.source})) or "—"}</span></footer>"""
    return page("Flow Event Recon — eventy", body, script=LIST_JS)


# ================================================================== UC3
def html_report(recon, icp_cfg, mock=True):
    must = icp_cfg["thresholds"]["must_meet"]
    talk = icp_cfg["thresholds"]["worth_talk"]
    maxes = _maxes(icp_cfg)
    ranked = recon.ranked()

    def person_row(p, idx):
        num_cls = "high" if p.score >= must else ("low" if p.score < talk else "")
        badges = []
        if p.is_key_account:
            badges.append('<span class="badge badge-key">key account</span>')
        if p.event_role and p.event_role != "attendee":
            badges.append(f'<span class="badge badge-format">{_e(p.event_role)}</span>')
        if p.source == "attendee_list":
            badges.append('<span class="badge badge-manual">z app exportu</span>')
        cls, lab = ORIGIN_LABEL.get(
            "confirmed" if p.confidence == "high" else
            ("guessed" if p.confidence == "low" else "inferred"), ("", ""))
        badges.append(f'<span class="chip-src {cls}">{_e(p.confidence_label)}</span>')

        meta = [f"<span>{_e(p.title) or 'pozice neuvedena'}</span>"]
        if p.company:
            meta.append(f'<span class="sep">·</span><span>{_e(p.company)}</span>')
        if (p.key_account_owner or "").strip():
            meta.append(f'<span class="sep">·</span><span>vlastní {_e(p.key_account_owner)}</span>')

        session = (f'<p class="row-desc">Mluví na: <strong style="color:var(--text)">'
                   f'„{_e(p.session)}"</strong></p>' if p.session else "")
        angle = (f'<div class="angle"><b>Řekni mu</b><span>{_e(p.angle)}</span></div>'
                 if p.angle else "")
        link = p.linkedin_url or p.linkedin_search_url
        pid = f"wp{idx}"
        return f"""<article class="row">
  <div class="row-lead"><span class="num {num_cls}">{p.score}</span>
    <span class="lbl">priorita</span></div>
  <div class="row-main">
    <div class="row-badges">{"".join(badges)}</div>
    <span class="row-title">{_e(p.name)}</span>
    <div class="row-meta">{"".join(meta)}</div>
    {session}{angle}
    <div class="row-actions">
      {f'<a class="btn btn-primary btn-sm" href="{_e(link)}" target="_blank" rel="noopener">Najít na LinkedInu</a>' if link else ''}
      <button class="btn btn-sm" type="button" data-why="{pid}" aria-expanded="false">Proč tohle číslo?</button>
    </div>
    {_why_panel(pid, p.score_breakdown, maxes,
                "Body dává pevná tabulka. AI smí výsledek posunout jen o ±"
                + str(icp_cfg.get("llm_adjust_max", 10)) + " a musí to zdůvodnit.")}
  </div>
  <div class="row-side"></div>
</article>"""

    idx = 0
    sections = []
    for title, note, cls, people in [
        ("Najdi tyhle", "Bez těchhle jsi tam byl zbytečně.", "",
         [p for p in ranked if p.score >= must]),
        ("Stojí za pokec", "Když bude čas nebo je potkáš u kávy.", "",
         [p for p in ranked if talk <= p.score < must]),
        ("Zbytek", "Nízká priorita.", "muted",
         [p for p in ranked if p.score < talk]),
    ]:
        if not people:
            continue
        rows = []
        for p in people:
            rows.append(person_row(p, idx))
            idx += 1
        sections.append(
            f'<div class="section-header"><h2 class="section-title {cls}">'
            f'<span class="marker"></span>{title}</h2>'
            f'<span class="section-count">{note} · {len(people)}</span></div>'
            + "".join(rows))

    alerts = "".join(
        f'<div class="callout red"><b>Key account</b><span><strong>{_e(c)}</strong> '
        f'tam má {len(ppl)} {"člověka" if len(ppl) == 1 else ("lidi" if len(ppl) < 5 else "lidí")}'
        f' — {_e(", ".join(x.name for x in ppl[:4]))}{f" · vlastní {_e(ppl[0].key_account_owner)}" if (ppl[0].key_account_owner or "").strip() else ""}'
        f'</span></div>'
        for c, ppl in recon.key_account_hits().items())

    comp_rows = "".join(
        f'<li><a href="#">{_e(c.name)}</a>'
        f'<span class="chip-speaker">{_e(c.role_at_event) or "partner"}</span>'
        f'{f"<span class=\"chip-company\">{_e(c.industry)}</span>" if c.industry else ""}'
        f'{"<span class=\"badge badge-key\">key account</span>" if c.is_key_account else ""}'
        f'</li>' for c in recon.companies)

    side_rows = "".join(
        f'<li><a href="{_e(s.url) or "#"}">{_e(s.name)}</a>'
        f'<span class="chip-speaker">{{"open":"otevřené","invite-only":"jen na pozvánku"}}'
        f'</span><time>{_e(s.when) or "—"}</time></li>'
        for s in recon.side_events)
    side_rows = "".join(
        f'<li><a href="{_e(s.url) or "#"}">{_e(s.name)}</a>'
        f'<span class="{"chip-company" if s.access == "open" else "chip-speaker"}">'
        f'{"otevřené" if s.access == "open" else ("jen na pozvánku" if s.access == "invite-only" else "neověřeno")}'
        f'</span>{f"<span style=\"color:var(--text-muted);font-size:13px\">{_e(s.host)}</span>" if s.host else ""}'
        f'<time>{_e(s.when) or "—"}</time></li>'
        for s in recon.side_events)

    extras = ""
    if recon.companies:
        extras += (f'<div class="wl" style="margin-top:24px"><header><h3>Partneři a sponzoři</h3>'
                   f'<span class="meta">{len(recon.companies)}</span></header>'
                   f'<ul>{comp_rows}</ul></div>')
    if recon.side_events:
        extras += (f'<div class="wl"><header><h3>Doprovodný program</h3>'
                   f'<span class="meta">{len(recon.side_events)}</span></header>'
                   f'<ul>{side_rows}</ul></div>')

    warn = ""
    if recon.warnings:
        warn = ('<div class="callout soft"><b>Poznámky běhu</b><span>'
                + " · ".join(_e(w) for w in recon.warnings) + "</span></div>")

    n_must = len([p for p in ranked if p.score >= must])
    body = f"""{topbar(_engine_tag(mock))}
{_demo_banner(mock)}<p class="crumb"><a href="index.html">← Všechny eventy</a></p>
<h1>{_e(recon.name)}</h1>
<p class="subtitle">{_e(recon.summary) or "Recon před eventem — koho potkat a co mu říct."}</p>
{tabs("events", {})}
<div class="stats">
  <div class="stat-item"><span class="stat-num accent">{n_must}</span>
    <span class="stat-label">najdi tyhle</span></div>
  <div class="stat-item"><span class="stat-num">{len(ranked)}</span>
    <span class="stat-label">kontaktů celkem</span></div>
  <div class="stat-item"><span class="stat-num red">{len(recon.key_account_hits())}</span>
    <span class="stat-label">key accountů</span></div>
  <div class="stat-item"><span class="stat-num">{len(recon.side_events)}</span>
    <span class="stat-label">side eventů</span></div>
  <div class="stat-item"><span class="stat-num">{_e(recon.date) or "—"}</span>
    <span class="stat-label">{_e(recon.location) or "místo neuvedeno"}</span></div>
</div>
<div class="filter-group">
  <a class="btn btn-sm" href="index.html">← Zpět na eventy</a>
  <button class="btn btn-sm" type="button" onclick="window.print()">Tisk / PDF</button>
  {f'<a class="btn btn-sm" href="{_e(recon.url)}" target="_blank" rel="noopener">Web eventu ↗</a>' if recon.url and recon.url.startswith("http") else ''}
</div>
{alerts}{warn}
{"".join(sections)}
{extras}
<footer><span>Vygenerováno {datetime.now():%d.%m.%Y %H:%M}</span>
  <span>Čísla ověř, než na ně vsadíš schůzku</span></footer>"""
    return page(f"{recon.name} — recon", body, script=WHY_JS)


# ================================================================== UC2
def html_watchlist(alerts, accounts, mock=True):
    from .watch import summary_by_company
    grouped = summary_by_company(alerts)
    KIND = {"speaker": "má speakera", "partner": "je partner", "organizer": "pořádá",
            "attendee": "má účastníky", "mention": "je zmíněna"}

    blocks = []
    for acc in accounts:
        items = grouped.get(acc["company"], [])
        lis = "".join(
            f'<li><span class="{"chip-company" if a.kind in ("speaker", "organizer") else "chip-speaker"}">'
            f'{KIND.get(a.kind, a.kind)}</span>'
            f'<a href="{_e(a.event_url) or "#"}" target="_blank" rel="noopener">{_e(a.event_name)}</a>'
            f'{f"<span style=\"color:var(--text-muted);font-size:13px\">{_e(a.detail)}</span>" if a.detail else ""}'
            f'<time>{_e(a.event_date) or "—"}</time></li>' for a in items
        ) or '<li><span class="empty-line">Zatím nikde nezachycena.</span></li>'
        blocks.append(f"""<div class="wl"><header>
  <h3>{_e(acc["company"])}</h3>
  <span class="chip-speaker">tier {_e(acc.get("tier")) or "—"}</span>
  <span class="meta">{f'vlastní {_e(acc.get("owner"))} · ' if (acc.get("owner") or "").strip() else ""}{len(items)} nálezů</span>
</header><ul>{lis}</ul></div>""")

    total = sum(len(v) for v in grouped.values())
    active = len([a for a in accounts if grouped.get(a["company"])])
    body = f"""{topbar(_engine_tag(mock))}
{_demo_banner(mock)}<h1>Kde jsou <span class="black">naše key accounts.</span></h1>
<p class="subtitle">Firmy ze sledovaného seznamu a eventy, kde se objevily — jako pořadatel,
partner, speaker nebo účastník. Přihlas se na stejný event a setkání působí přirozeně.</p>
{tabs("watch", {"watch": total})}
<div class="stats">
  <div class="stat-item"><span class="stat-num">{len(accounts)}</span>
    <span class="stat-label">sledovaných firem</span></div>
  <div class="stat-item"><span class="stat-num accent">{active}</span>
    <span class="stat-label">někde zachyceno</span></div>
  <div class="stat-item"><span class="stat-num red">{total}</span>
    <span class="stat-label">nálezů celkem</span></div>
</div>
{"".join(blocks)}
<footer><span>Aktualizováno {datetime.now():%d.%m.%Y %H:%M}</span>
  <span>Seznam firem v config/key_accounts.csv</span></footer>"""
    return page("Flow Event Recon — key accounts", body)


# ================================================================== Docs
def html_how_it_works(icp_cfg, stats: dict, mock=True, cfg_warnings=None):
    body = f"""{topbar(_engine_tag(mock))}
<h1>Jak to <span class="black">funguje.</span></h1>
<p class="subtitle">Co nástroj dělá, odkud bere data, čemu se dá věřit
a co je potřeba ověřit ručně.</p>
{tabs("how", {})}

{_demo_banner(mock)}{_setup_warning(cfg_warnings)}
<div class="prose">
<h2>Tři kroky, jeden nástroj</h2>
<div class="flow">
  <div class="flow-step"><div class="n">1</div><div>
    <h4>Discover — najdi eventy</h4>
    <p>Projde zdroje (Luma, Eventbrite, ruční seznam), oskóruje každý event 0–100
    podle našich ICP oborů a oblastí, které děláme. Claude doplní shrnutí.</p></div></div>
  <div class="flow-step"><div class="n">2</div><div>
    <h4>Watch — hlídej key accounts</h4>
    <p>Prohledá nalezené eventy proti seznamu sledovaných firem. Když se firma objeví
    jako pořadatel, partner nebo speaker, založí nález. Stejný nález se neohlásí dvakrát.</p></div></div>
  <div class="flow-step"><div class="n">3</div><div>
    <h4>Recon — připrav mě na event</h4>
    <p>K vybranému eventu stáhne web, Claude z něj vytáhne speakery, sponzory a side eventy.
    Každý člověk dostane prioritu 0–100 a jednu větu, o čem s ním mluvit.</p></div></div>
</div>

<h2>Čemu věřit a čemu ne</h2>
<p>U každého kontaktu je štítek s tím, jak spolehlivá ta informace je.
Nástroj to neskrývá — radši přizná odhad, než aby tvářil jistotu.</p>
<table>
  <tr><th>Štítek</th><th>Znamená</th><th>Spolehlivost</th></tr>
  <tr><td>ověřeno</td><td>Stálo to černé na bílém na webu eventu nebo v tvém exportu z app.</td>
      <td>Vysoká</td></tr>
  <tr><td>částečně odvozeno</td><td>Claude to dohledal nebo odvodil z kontextu.</td>
      <td>Střední — namátkou ověř</td></tr>
  <tr><td>odhad, ověř</td><td>Nejlepší odhad. Typicky LinkedIn: dostaneš vyhledávací
      odkaz, ne potvrzený profil.</td><td>Nízká</td></tr>
</table>

<h3>Co víme spolehlivě</h3>
<p><strong>Speakeři, sponzoři a program</strong> — je to na webu eventu, veřejné.
<strong>Účastníci</strong>, které sám vyexportuješ z event app. <strong>Termín, místo,
pořadatel.</strong></p>

<h3>Co je odhad</h3>
<p><strong>Velikost a obor firmy</strong> — Claude si to dohledá, ale u malých
dánských firem se plete. <strong>Skóre</strong> — je to naše rubrika, ne objektivní
pravda. <strong>Angle věta</strong> — návrh, ne scénář.</p>

<h3>Co nevíme vůbec</h3>
<p><strong>Kdo se reálně zaregistroval</strong>, pokud to organizátor nezveřejní.
Veřejné seznamy účastníků prakticky neexistují — proto se export z app dodává ručně.
<strong>Konkrétní LinkedIn profil</strong> — scraping je proti podmínkám LinkedInu,
takže dostaneš vyhledávací odkaz.</p>

<h2>Jak z toho vytáhnout co nejvíc</h2>
<table>
  <tr><th>Krok</th><th>Co to přidá</th></tr>
  <tr><td>Export z event app</td><td>Největší jednotlivý přínos. Web eventu ukáže
      speakery, app ukáže, kdo tam reálně bude. Bývá to 10× víc lidí.</td></tr>
  <tr><td><code>--deep</code></td><td>Claude si během běhu googlí a dohledá obor,
      velikost a sídlo firem. Stojí tokeny, ale zpřesní skóre.</td></tr>
  <tr><td>Doplnit key accounts</td><td>Čím delší seznam sledovaných firem,
      tím víc nálezů. Stačí název a doména.</td></tr>
  <tr><td>Ladit <code>config/icp.yaml</code></td><td>Klíčová slova a váhy.
      Po pár reálných eventech se skóre výrazně zpřesní.</td></tr>
  <tr><td>Přidat zdroje eventů</td><td>Každý zdroj = jeden soubor
      v <code>src/recon/sources/</code>.</td></tr>
</table>

<h2>Kde je Claude a kde není</h2>
<p>Skóre <strong>nedává AI</strong>. Dává ho pevná tabulka v <code>config/icp.yaml</code> —
proto je stejné mezi běhy a proto u každého čísla vidíš rozpad bodů. Claude dělá čtyři věci,
které tabulka neumí:</p>
<table>
  <tr><th>Úloha</th><th>Proč AI</th></tr>
  <tr><td>Extrakce z webu eventu</td><td>Každá konference má jiné HTML. Bez AI bychom
      psali parser na každou zvlášť.</td></tr>
  <tr><td>Shrnutí eventů</td><td>Aby se nemusel číst celý popis.</td></tr>
  <tr><td>Angle věta</td><td>Spojí session, roli a naše reference do jedné věty.</td></tr>
  <tr><td>Dohledání firem (<code>--deep</code>)</td><td>Claude umí web search přímo
      v API — nepotřebujeme vlastní scrapery.</td></tr>
</table>
<p>Claude smí posunout skóre jen o ±{icp_cfg.get("llm_adjust_max", 10)} bodů a musí to zdůvodnit.
Zbytek je rubrika.</p>

<h2>Aktuální nastavení</h2>
<table>
  <tr><th>Položka</th><th>Hodnota</th></tr>
  <tr><td>Režim</td><td>{"mock — bez API klíče, data jsou ukázková"
      if mock else "Claude API aktivní"}</td></tr>
  <tr><td>ICP obory</td><td>{", ".join(i["label"] for i in icp_cfg["icps"])}</td></tr>
  <tr><td>Oblasti, které děláme</td><td>{", ".join(
      a["id"] for a in icp_cfg.get("service_areas", []))}</td></tr>
  <tr><td>Sledovaná klíčová slova</td><td>{len(icp_cfg.get("watch_keywords", []))}</td></tr>
  <tr><td>Práh „nenech si ujít"</td><td>{icp_cfg["thresholds"]["event_top"]}</td></tr>
  <tr><td>Práh „najdi tyhle" (lidé)</td><td>{icp_cfg["thresholds"]["must_meet"]}</td></tr>
  <tr><td>Eventů v databázi</td><td>{stats.get("events", 0)}</td></tr>
  <tr><td>Key account nálezů</td><td>{stats.get("alerts", 0)}</td></tr>
</table>

<h2>Osobní údaje</h2>
<p>Zpracovávají se jména, pozice a zaměstnavatelé z veřejných zdrojů na základě
oprávněného zájmu. Exporty z event app obsahují osobní údaje a <strong>necommitují se
do repozitáře</strong>. Retention a evidenci je potřeba potvrdit interně, než to pojede ostře.</p>
</div>
<footer><span>Aktualizováno {datetime.now():%d.%m.%Y %H:%M}</span></footer>"""
    return page("Flow Event Recon — jak to funguje", body)


# ================================================================== CSV
def events_csv(events) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["score", "date", "name", "city", "organizer", "format", "price",
                "topic", "key_accounts", "has_recon", "url", "summary"])
    for e in sorted(events, key=lambda x: -x.score):
        w.writerow([e.score, e.date or "", e.name, e.city or "", e.organizer or "",
                    e.format or "", e.price or "", e.topic or "",
                    "; ".join(e.key_accounts), "yes" if e.has_recon else "",
                    e.url or "", e.summary or ""])
    return buf.getvalue()


def update_index(docs_dir, entry: dict):
    manifest = docs_dir / "_events.json"
    events = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    events = [e for e in events if e.get("file") != entry["file"]]
    events.append(entry)
    manifest.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    return events
