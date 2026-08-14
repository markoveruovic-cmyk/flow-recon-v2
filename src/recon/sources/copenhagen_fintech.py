"""Copenhagen Fintech - kalendar.

Nejrelevantnejsi zdroj pro nase BFSI ICP: dansky fintech hub, na jehoz
akce chodi banky, pojistovny a platebni firmy.

OVERENO 14. 8. 2026 (kodem, ne rucne):
  - URL je https://www.copenhagenfintech.dk/events (ne /calendar ani
    /news-events). HTTP 200 s beznym browser UA, zadna blokace.
  - Stranka je SERVER-RENDERED (Webflow CMS) - vsechny karty jsou primo
    v HTML, prohlizec netreba.
  - JSON-LD JE na strance, ale jen `CollectionPage`/`ItemList` s nazvy
    kategorii ("Community Events", "Demo Days"...), BEZ nazvu/data/URL
    jednotlivych eventu. Detailni stranky eventu JSON-LD nemaji vubec.
    Proto NEparsujeme JSON-LD, ale HTML karty.
  - ZADNY RSS ani iCal feed (/feed, /events/rss.xml -> 404).
  - Struktura karty: repeating `div.w-dyn-item`, uvnitr:
      datum   -> `div.h2`  (anglicky, napr. "September 21, 2026")
      nazev   -> `img[alt]`, a kdyz je alt prazdny, prvni `.event__text`
      poradatel-> druhy `.event__text` za popiskem "Event hosted by:"
      popis   -> `.fs_accordion-1_paragraph-2`
      odkaz   -> `a.link-to-page`  (interni /events/<slug>)  NEBO
                 `a.link-to-rsvp-url` (externi, casto Eventbrite/nfweek)
  - Cast eventu ma jen externi RSVP odkaz (bez interni stranky).
"""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from ..models import Event

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://www.copenhagenfintech.dk"
EVENTS_URL = f"{BASE}/events"

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
DATE_RE = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})")

# Poradatel je z Kodane, ale cast akci jsou delegace/warm-upy jinde. Mesto
# proto bereme z nazvu/popisu a na Kodan padame jen jako fallback - jinak by
# Nordic scoring nefungovalo (vsechno by bylo "copenhagen"). Nordic mesta
# nechavame, at je pozna score._location_bucket; mimo-Nordic padnou do abroad.
_CITY_HINTS = [
    "Stockholm", "Oslo", "Gothenburg", "Göteborg", "Helsinki", "Malmö", "Malmo",
    "Aarhus", "Odense",
    "Singapore", "London", "Berlin", "Barcelona", "Amsterdam", "Paris",
    "New York", "Dubai", "Lisbon", "Madrid",
]
# nektere akce poznat podle jmena, ne mesta:
_EVENT_CITY_HINTS = {"slush": "Helsinki"}   # Slush se kona v Helsinkach


def collect(url: str | None = None, timeout: float = 20.0, **_) -> list[Event]:
    try:
        html = _get(url or EVENTS_URL, timeout)
    except Exception:
        return []
    return _parse(html)


def _get(url: str, timeout: float) -> str:
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _parse(html: str) -> list[Event]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Event] = []
    seen: set[str] = set()
    for card in soup.select("div.w-dyn-item"):
        date_el = card.select_one("div.h2")
        img = card.find("img")
        texts = [t.get_text(" ", strip=True) for t in card.select(".event__text")
                 if t.get_text(strip=True)]

        name = (img.get("alt").strip() if img and img.get("alt") else "")
        if not name and texts:
            name = texts[0]

        internal = card.select_one("a.link-to-page")
        rsvp = card.select_one("a.link-to-rsvp-url")
        href = ""
        if internal and internal.get("href"):
            href = internal["href"]
            if href.startswith("/"):
                href = BASE + href
        elif rsvp and rsvp.get("href"):
            href = rsvp["href"]

        if not name and href:
            name = _slug_to_name(href)
        if not name or len(name) < 4:
            continue

        key = href or name.lower()
        if key in seen:
            continue
        seen.add(key)

        # poradatel: druhy .event__text je host ("Event hosted by: <host>")
        organizer = texts[1] if len(texts) > 1 else "Copenhagen Fintech"
        desc_el = card.select_one(".fs_accordion-1_paragraph-2")
        desc = _clean(desc_el.get_text(" ", strip=True)) if desc_el else None

        out.append(Event(
            name=name,
            url=href,
            source="copenhagen_fintech",
            date=_iso_date(date_el.get_text(strip=True) if date_el else None),
            city=_detect_city(f"{name} {desc or ''}"),
            organizer=organizer,
            description=desc,
        ))
    return out


def _detect_city(text: str) -> str:
    """Mesto z nazvu/popisu; Kodan jen jako fallback."""
    low = text.lower()
    for city in _CITY_HINTS:
        if re.search(rf"\b{re.escape(city.lower())}\b", low):
            return city
    for hint, city in _EVENT_CITY_HINTS.items():
        if hint in low:
            return city
    return "Copenhagen"


def _clean(text: str | None) -> str | None:
    return re.sub(r"\s+", " ", text or "").strip()[:1500] or None


def _iso_date(text: str | None) -> str | None:
    if not text:
        return None
    m = DATE_RE.search(text)
    if not m:
        return None
    mon = MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}"


def _slug_to_name(href: str) -> str:
    slug = href.split("?")[0].split("#")[0].rstrip("/").split("/")[-1]
    return slug.replace("-", " ").replace("_", " ").strip().title()
