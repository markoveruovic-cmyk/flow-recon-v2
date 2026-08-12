"""Scoring.

Zamerne HYBRID:
 1) deterministicka rubrika z config/icp.yaml  -> vysvetlitelne, zdarma, stabilni
 2) Claude jen doplni "angle" vetu a smi skore posunout o +/- llm_adjust_max

Diky tomu vzdy vidis, PROC ma nekdo 88 a ne 62, a muzes to ladit v YAMLu.
"""
from __future__ import annotations

import re
import sys

from .llm import Claude
from .models import EventRecon, Person

C_LEVEL = re.compile(r"\b(ceo|cto|cio|cdo|cpo|coo|cfo|cmo|chief|founder|co-founder|owner|managing director)\b", re.I)
VP = re.compile(r"\b(vp|vice president|svp|evp)\b", re.I)
HEAD_DIR = re.compile(r"\b(head of|director|direktor|chef)\b", re.I)
LEAD_MGR = re.compile(r"\b(lead|manager|principal|partner|senior manager)\b", re.I)

CORE_FN = re.compile(
    r"\b(digital|product|technolog|tech|data|ai|cx|customer experience|innovat|"
    r"e-?commerce|ecom|platform|engineering|it\b|transformation|mobile|ux|design)\b", re.I)
ADJACENT_FN = re.compile(r"\b(marketing|operations|strategy|growth|sales|business development|analytics)\b", re.I)
OFF_FN = re.compile(r"\b(hr|people|talent|recruit|legal|compliance|finance|accounting|facility|procurement)\b", re.I)


# ---------------------------------------------------------------- ICP
def match_icp(person: Person, company_industry: str | None, icp_cfg: dict) -> tuple[str | None, str]:
    """Vrati (icp_id, uroven shody) kde uroven je klic v rubric.icp_match."""
    company = (person.company or "").strip().lower()
    haystack = " ".join(filter(None, [company, company_industry or "", person.title or ""])).lower()

    for icp in icp_cfg["icps"]:
        for known in icp.get("known_companies", []):
            if known.lower() in company and company:
                return icp["id"], "exact_company"

    best: tuple[str | None, int] = (None, 0)
    for icp in icp_cfg["icps"]:
        hits = sum(1 for kw in icp.get("keywords", []) if kw.lower() in haystack)
        if hits > best[1]:
            best = (icp["id"], hits)

    icp_id, hits = best
    if hits >= 2:
        return icp_id, "strong_keyword"
    if hits == 1:
        return icp_id, "weak_keyword"
    if re.search(r"\b(consult|agency|software|saas|advisory|integrat)\b", haystack):
        return None, "adjacent"
    return None, "none"


def seniority_level(title: str | None) -> str:
    if not title:
        return "unknown"
    if C_LEVEL.search(title):
        return "c_level"
    if VP.search(title):
        return "vp"
    if HEAD_DIR.search(title):
        return "head_director"
    if LEAD_MGR.search(title):
        return "lead_manager"
    return "ic"


def function_level(title: str | None) -> str:
    if not title:
        return "adjacent"
    if OFF_FN.search(title) and not CORE_FN.search(title):
        return "off_topic"
    if CORE_FN.search(title):
        return "core"
    if ADJACENT_FN.search(title):
        return "adjacent"
    return "adjacent"


def is_excluded(person: Person, icp_cfg: dict) -> str | None:
    title = (person.title or "").lower()
    company = (person.company or "").lower()
    for bad in icp_cfg.get("exclude", {}).get("titles", []) or []:
        if bad.lower() in title:
            return f"vyloucena role: {bad}"
    for bad in icp_cfg.get("exclude", {}).get("companies", []) or []:
        if bad.lower() in company:
            return f"vyloucena firma: {bad}"
    if not person.company:
        return "chybi firma"
    return None


# ---------------------------------------------------------------- rubrika
def score_person(person: Person, recon: EventRecon, icp_cfg: dict) -> Person:
    rub = icp_cfg["rubric"]

    reason = is_excluded(person, icp_cfg)
    if reason:
        person.excluded_reason = reason
        person.score = 0
        return person

    industry = next(
        (c.industry for c in recon.companies
         if person.company and c.name.lower() in person.company.lower()),
        None,
    )
    icp_id, level = match_icp(person, industry, icp_cfg)
    sen = seniority_level(person.title)
    fn = function_level(person.title)
    size = "unknown"  # doplni enrich.py, az bude firemni databaze

    bd = {
        "icp_match": rub["icp_match"][level],
        "seniority": rub["seniority"][sen],
        "function_fit": rub["function_fit"][fn],
        "company_size": rub["company_size"][size],
        "event_role": rub["event_role"].get(person.event_role, 3),
    }
    if person.is_key_account:
        bd["key_account_bonus"] = icp_cfg.get("key_account_bonus", 0)

    person.icp_id = icp_id
    person.score_breakdown = bd
    person.score = min(100, sum(bd.values()))
    return person


def tag_company_icp(recon: EventRecon, icp_cfg: dict) -> EventRecon:
    """Partneri/sponzori taky potrebuji ICP tag - podle nej se pocita,
    kolik z nich je pro nas relevantnich."""
    for c in recon.companies:
        haystack = f"{c.name} {c.industry or ''}".lower()
        for icp in icp_cfg["icps"]:
            known = any(k.lower() in c.name.lower() for k in icp.get("known_companies", []))
            kw = any(k.lower() in haystack for k in icp.get("keywords", []))
            if known or kw:
                c.icp_id = icp["id"]
                break
    return recon


def score_all(recon: EventRecon, icp_cfg: dict) -> EventRecon:
    for p in recon.people:
        score_person(p, recon, icp_cfg)
    tag_company_icp(recon, icp_cfg)
    return recon


# ---------------------------------------------------------------- angles
ANGLE_SYSTEM = """Jsi SDR analytik. Ke kazdemu kontaktu napises JEDNU konkretni vetu,
o cem s nim na eventu zacit bavit - navazanou na jeho session, roli nebo firmu.

PRAVIDLA:
- Vracis VYHRADNE JSON pole, zadny text okolo.
- Zadne obecne fraze typu "probrat spolupraci" nebo "zjistit potreby".
- Vychazis jen z dodanych dat, nic si nedomyslis o jejich internich projektech.
- Cesky, max 20 slov na angle.
- adjust: cele cislo v rozsahu +/-{adjust_max}, jen kdyz mas duvod. Jinak 0.

SCHEMA: [{{"name": str, "angle": str, "adjust": int, "adjust_reason": str|null}}]"""

ANGLE_USER = """NASE POZICE:
{positioning}

EVENT: {event}

KONTAKTY:
{contacts}"""

MOCK_ANGLES: dict[str, str] = {}   # v mock rezimu zadne angle - vymyslet by bylo horsi nez nic


def add_angles(recon: EventRecon, icp_cfg: dict, claude: Claude, top_n: int = 15) -> EventRecon:
    top = recon.ranked(min_score=icp_cfg["thresholds"]["worth_talk"])[:top_n]
    if not top:
        return recon

    contacts = "\n".join(
        f"- {p.name} | {p.title or '?'} | {p.company or '?'} | "
        f"role: {p.event_role} | session: {p.session or '-'} | score: {p.score}"
        for p in top
    )
    raw = claude.json_call(
        ANGLE_SYSTEM.format(adjust_max=icp_cfg.get("llm_adjust_max", 10)),
        ANGLE_USER.format(
            positioning=icp_cfg.get("positioning", ""),
            event=f"{recon.name} | {recon.date} | {recon.location}",
            contacts=contacts,
        ),
        max_tokens=2000,
        mock_response=[
            {"name": p.name,
             "angle": MOCK_ANGLES.get(p.name) or "(mock režim — angle generuje až Claude API)",
             "adjust": 0, "adjust_reason": None}
            for p in top
        ],
    )

    by_name = {p.name: p for p in recon.people}
    cap = icp_cfg.get("llm_adjust_max", 10)
    for item in raw or []:
        p = by_name.get(item.get("name", ""))
        if not p:
            continue
        p.angle = item.get("angle")
        adj = max(-cap, min(cap, int(item.get("adjust") or 0)))
        if adj:
            p.score_breakdown["llm_adjust"] = adj
            p.score = max(0, min(100, p.score + adj))
    return recon


# ================================================================ UC1: eventy
CITY_MAP = {
    "copenhagen": "copenhagen", "københavn": "copenhagen", "kobenhavn": "copenhagen",
    "kodan": "copenhagen", "kodaň": "copenhagen", "frederiksberg": "copenhagen",
    "aarhus": "aarhus", "århus": "aarhus", "odense": "odense",
    "online": "online", "virtual": "online", "remote": "online",
}
DK_HINT = re.compile(r"\b(denmark|danmark|dansk|dk)\b", re.I)

FORMAT_MAP = {
    "conference": "conference", "konference": "conference", "summit": "summit",
    "delegation": "delegation", "demo day": "demo_day", "demoday": "demo_day",
    "meetup": "meetup", "meet-up": "meetup", "workshop": "workshop",
    "webinar": "webinar", "masterclass": "workshop", "panel": "conference",
}


def _location_bucket(event) -> str:
    blob = " ".join(filter(None, [event.city, event.name, event.description])).lower()
    for needle, bucket in CITY_MAP.items():
        if needle in blob:
            return bucket
    if DK_HINT.search(blob):
        return "denmark_other"
    return "abroad"


def _format_bucket(event) -> str:
    blob = " ".join(filter(None, [event.format, event.name])).lower()
    for needle, bucket in FORMAT_MAP.items():
        if needle in blob:
            return bucket
    return "unknown"


def score_event(event, icp_cfg: dict):
    """Oskoruje event 0-100 pro UC1 digest. Stejna filozofie jako u lidi:
    pevna rubrika, vysvetlitelna, laditelna v YAMLu."""
    rub = icp_cfg["event_rubric"]
    blob = " ".join(filter(None, [
        event.name, event.description, event.organizer, event.topic, event.city])).lower()

    # 1) ICP shoda - kolik ruznych signalu ukazuje na nas segment
    best_icp, best_hits = None, 0
    for icp in icp_cfg["icps"]:
        hits = sum(1 for kw in icp.get("keywords", []) if kw.lower() in blob)
        hits += sum(1 for c in icp.get("known_companies", []) if c.lower() in blob)
        if hits > best_hits:
            best_icp, best_hits = icp["id"], hits
    icp_level = ("strong" if best_hits >= 3 else "good" if best_hits == 2
                 else "weak" if best_hits == 1 else "none")

    # 2) oblast vyvoje, kterou delame (druha osa vedle oboru)
    svc_best, svc_hits = None, 0
    for area in icp_cfg.get("service_areas", []):
        hits = sum(1 for kw in area.get("keywords", []) if kw.lower() in blob)
        if hits > svc_hits:
            svc_best, svc_hits = area["id"], hits
    svc_level = "strong" if svc_hits >= 2 else "weak" if svc_hits == 1 else "none"

    # 3) nase temata
    kw_hits = sum(1 for kw in icp_cfg.get("watch_keywords", []) if kw.lower() in blob)
    kw_points = min(15, kw_hits * rub["keyword_match"]["per_hit"])

    # 4) misto, 5) format, 6) organizator
    loc = _location_bucket(event)
    fmt = _format_bucket(event)
    org_known = any(o.lower() in (event.organizer or "").lower()
                    for o in icp_cfg.get("organizer_watchlist", []))

    bd = {
        "icp_match": rub["icp_match"][icp_level],
        "service_match": rub["service_match"][svc_level],
        "keyword_match": kw_points,
        "location": rub["location"][loc],
        "format": rub["format"][fmt],
        "organizer": rub["organizer"]["known_relevant" if org_known else "unknown"],
    }
    event.icp_id = best_icp
    event.service_id = svc_best
    event.score_breakdown = bd
    event.score = min(100, sum(bd.values()))
    return event


EVENT_SUMMARY_SYSTEM = """Shrnujes eventy pro obchodni tym digitalni produktove agentury.

PRAVIDLA:
- Vracis VYHRADNE JSON pole, zadny text okolo.
- summary: 1-2 vety cesky, o cem event je a proc by nas mohl zajimat. Max 30 slov.
- Zadny marketingovy jazyk, zadne "skvela prilezitost". Vecne.
- Vychazis jen z dodaneho popisu. Co nevis, nepises.
- topic: jedno z fintech, retail, ecommerce, mobile, design, ai, general

SCHEMA: [{"uid": str, "summary": str, "topic": str}]"""


SUMMARY_BATCH = 12  # jedno volani na 30 eventu s dlouhymi popisy pretece max_tokens


def summarize_events(events: list, icp_cfg: dict, claude) -> list:
    """Doplni AI shrnuti k eventum. Davkove po SUMMARY_BATCH eventech - jedno
    volani na vsechny by pri delsich popisech preteklo max_tokens a JSON by se
    useknul. Selhani jedne davky nesmi shodit cely beh - jen vypis varovani."""
    todo = [e for e in events if not e.summary]
    if not todo:
        return events

    by_uid = {e.uid: e for e in todo}
    for start in range(0, len(todo), SUMMARY_BATCH):
        batch = todo[start:start + SUMMARY_BATCH]
        listing = "\n\n".join(
            f"uid: {e.uid}\nnazev: {e.name}\norganizator: {e.organizer or '?'}\n"
            f"misto: {e.city or '?'}\npopis: {(e.description or '')[:600]}"
            for e in batch
        )
        try:
            raw = claude.json_call(
                EVENT_SUMMARY_SYSTEM,
                f"NASE POZICE:\n{icp_cfg.get('positioning', '')}\n\nEVENTY:\n{listing}",
                max_tokens=4000,
                mock_response=[
                    {"uid": e.uid,
                     "summary": f"{e.name} — {(e.description or 'bez popisu')[:70]}",
                     "topic": e.topic or "general"}
                    for e in batch
                ],
            )
        except Exception as exc:
            print(f"  ! shrnuti davky {start // SUMMARY_BATCH + 1} selhalo: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            continue

        for item in raw or []:
            e = by_uid.get(item.get("uid", ""))
            if e:
                e.summary = item.get("summary")
                e.topic = item.get("topic") or e.topic
    return events
