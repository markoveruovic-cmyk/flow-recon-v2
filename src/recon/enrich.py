"""Obohaceni kontaktu a firem.

Dve urovne:
  1) enrich()      - zdarma, offline. LinkedIn vyhledavaci odkazy, odhad velikosti.
  2) deep_enrich() - stoji tokeny. Claude si behem odpovedi googli a dohleda
                     obor, velikost a sidlo firmy. Tohle je to, co z reconu
                     dela realny recon a ne jen prepis webu.

Kazde pole si nese `field_origin`, takze v UI vidis, co je overene
a co model odhadl.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from .llm import Claude
from .models import EventRecon, Person

SIZE_HINTS = {
    "enterprise": ["bank", "group", "a/s", "koncern", "plc", "insurance"],
    "small": ["studio", "startup", "aps", "consulting"],
}


# ------------------------------------------------------------ zdarma
def linkedin_search_url(person: Person) -> str:
    parts = [person.name]
    if person.company:
        parts.append(person.company)
    return ("https://www.linkedin.com/search/results/people/?keywords="
            + quote_plus(" ".join(parts)))


def enrich(recon: EventRecon) -> EventRecon:
    """Offline vrstva. Nic nevymysli, jen pripravi odkazy."""
    for p in recon.people:
        if not p.linkedin_url:
            p.linkedin_search_url = linkedin_search_url(p)
            # POZOR: tohle NENI profil, jen hledani. Proto "guessed".
            p.field_origin.setdefault("linkedin", "guessed")
        if p.title:
            p.field_origin.setdefault("title", "confirmed")
        if p.company:
            p.field_origin.setdefault("company", "confirmed")
    return recon


# ------------------------------------------------------------ s Claude API
RESEARCH_SYSTEM = """Dohledavas firemni kontext pro obchodni tym digitalni agentury.
Mas k dispozici webove vyhledavani - pouzij ho.

PRAVIDLA:
- Vracis VYHRADNE JSON pole, zadny text okolo, zadne markdown fence.
- Kde si nejsi jisty, das null. RADSI NULL NEZ VYMYSLENA HODNOTA.
- size: enterprise (1000+ zamestnancu) | mid (200-999) | small (<200) | null
- industry: kratky vecny popis oboru, cesky nebo anglicky, max 5 slov
- hq: mesto a zeme sidla
- confidence: "confirmed" pokud jsi to nasel na webu firmy nebo v duveryhodnem
  zdroji, "inferred" pokud jsi to odvodil z nepriimych indicii

SCHEMA: [{"company": str, "industry": str|null, "size": str|null,
          "hq": str|null, "domain": str|null, "confidence": str,
          "note": str|null}]"""


def deep_enrich(recon: EventRecon, claude: Claude, max_companies: int = 12) -> EventRecon:
    """Necha Claude dohledat firmy pres webove vyhledavani.

    Bezi jen na firmach, ktere maji sanci byt zajimave - kazde hledani stoji.
    """
    names: list[str] = []
    for p in recon.ranked():
        if p.company and p.company not in names:
            names.append(p.company)
    for c in recon.companies:
        if c.name not in names:
            names.append(c.name)
    names = names[:max_companies]
    if not names:
        return recon

    # Web search obcas skonci bez textoveho bloku (utne se po hledani) nebo
    # vrati neparsovatelny JSON. Deep enrich je volitelny - jeho selhani nesmi
    # shodit cely recon, ktery uz ma lidi i skore. Degradujeme na offline data.
    try:
        raw = claude.research_call(
            RESEARCH_SYSTEM,
            "Dohledej kontext k temto firmam:\n" + "\n".join(f"- {n}" for n in names),
            max_tokens=4096,
            max_searches=min(8, len(names)),
            mock_response=[
                {"company": n, "industry": None, "size": None, "hq": None,
                 "domain": None, "confidence": "inferred",
                 "note": "mock režim — nic se nedohledávalo"}
                for n in names
            ],
        )
    except Exception as exc:
        recon.warnings.append(
            f"Hlubší rekognoskace přes web selhala ({type(exc).__name__}), "
            "pokračuji bez ní.")
        return recon

    by_name = {item.get("company", "").lower(): item for item in (raw or [])}
    recon.warnings.append(
        f"Dohledáno {len([i for i in (raw or []) if i.get('industry')])} "
        f"z {len(names)} firem přes webové vyhledávání."
    )

    for c in recon.companies:
        item = by_name.get(c.name.lower())
        if not item:
            continue
        origin = item.get("confidence") or "inferred"
        if item.get("industry") and not c.industry:
            c.industry = item["industry"]
            c.field_origin["industry"] = origin
        if item.get("size"):
            c.size = item["size"]
            c.field_origin["size"] = origin
        if item.get("domain") and not c.domain:
            c.domain = item["domain"]
            c.field_origin["domain"] = origin

    known = {c.name.lower(): c for c in recon.companies}
    for p in recon.people:
        item = by_name.get((p.company or "").lower())
        if item and item.get("size"):
            p.field_origin["company_size"] = item.get("confidence") or "inferred"
        comp = known.get((p.company or "").lower())
        if comp and comp.size:
            p.field_origin.setdefault("company_size", "inferred")
    return recon


def apply_company_size(recon: EventRecon) -> dict[str, str]:
    """Mapa firma -> velikost, aby ji scoring mohl pouzit."""
    return {c.name.lower(): c.size for c in recon.companies if c.size}
