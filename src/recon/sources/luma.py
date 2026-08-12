"""Luma.

OVERENO 4. 8. 2026 (rucne, ne kodem):
  - Domena je luma.com. Stare lu.ma redirectuje, ale pouzivame novou.
  - Stranky JSOU server-rendered: nazvy eventu, poradatele i mista jsou
    primo v HTML. Na rozdil od TechBBQ nepotrebujeme prohlizec.
  - DATUM se ve vypisu ani na detailu neobjevuje v textu. Bud je v JSON-LD,
    nebo v atributu. Proto ctem obojí a kdyz datum nenajdeme, event si
    ulozime bez nej (a ve webu se zobrazi jako "termin neuveden").
  - Obecny mestsky kalendar /copenhagen je z 5/6 spolecenske akce
    (bezecke skupiny, party, kvizy). Pro nase ICP je to sum.
    Proto radeji KURATOROVANE kalendare nize.
"""
from __future__ import annotations

import json
import re

import httpx
from bs4 import BeautifulSoup

from ..models import Event

UA = "Mozilla/5.0 (compatible; FlowReconBot/0.1)"
BASE = "https://luma.com"

# Kuratorovane kalendare misto obecneho mestskeho.
# Doplnuj sem, co najdes - je to jen seznam URL.
DEFAULT_CALENDARS = [
    "https://luma.com/copenhagen",      # obecny, hodne sumu, ale obcas i tech
    "https://luma.com/tech-europe",     # evropsky tech, filtrujeme si mesto sami
]

EVENT_HREF = re.compile(r"^/([a-z0-9][a-z0-9-]{3,})$", re.I)
SKIP_SLUGS = {"discover", "pricing", "help", "signin", "app", "ai", "tech"}


def collect(calendars: list[str] | None = None, timeout: float = 20.0,
            fetch_details: bool = False, **_) -> list[Event]:
    """Posbira eventy z kalendaru.

    fetch_details=True stahne i detail kazdeho eventu (kvuli datu a popisu).
    Je to pomalejsi - jeden request na event - proto vychozi False.
    """
    out: list[Event] = []
    seen: set[str] = set()

    for cal in calendars or DEFAULT_CALENDARS:
        try:
            html = _get(cal, timeout)
        except Exception:
            continue

        found = _parse_jsonld(html, cal) or _parse_calendar_html(html, cal)
        for ev in found:
            if ev.uid in seen:
                continue
            seen.add(ev.uid)
            out.append(ev)

    if fetch_details:
        for ev in out:
            try:
                _enrich_from_detail(ev, timeout)
            except Exception:
                pass
    return out


def _get(url: str, timeout: float) -> str:
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.text


# ---------------------------------------------------------------- parsovani
def _parse_jsonld(html: str, origin: str) -> list[Event]:
    """Preferovana cesta - kdyz tam schema.org/Event je, ma i datum."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[Event] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk(data):
            if not isinstance(node, dict):
                continue
            if node.get("@type") not in ("Event", "SocialEvent", "BusinessEvent"):
                continue
            out.append(Event(
                name=(node.get("name") or "").strip(),
                url=node.get("url") or origin,
                source="luma",
                date=(node.get("startDate") or "")[:10] or None,
                city=_city(node.get("location")),
                organizer=_organizer(node.get("organizer")),
                description=_clean(node.get("description")),
                price="free" if _is_free(node) else None,
            ))
    return [e for e in out if e.name]


def _parse_calendar_html(html: str, origin: str) -> list[Event]:
    """Zaloha, kdyz JSON-LD chybi. Luma dava kazdy event do <a href="/slug">
    a nazev do nadpisu uvnitr. Datum takhle NEZISKAME."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[Event] = []
    for a in soup.find_all("a", href=True):
        m = EVENT_HREF.match(a["href"].split("?")[0])
        if not m or m.group(1).lower() in SKIP_SLUGS:
            continue
        heading = a.find(["h1", "h2", "h3", "h4"])
        name = (heading.get_text(" ", strip=True) if heading
                else a.get("aria-label") or "").strip()
        if not name or len(name) < 4:
            continue
        block = a.get_text(" ", strip=True)
        org = None
        if "By " in block:
            org = block.split("By ", 1)[1].split("  ")[0].strip()[:120] or None
        out.append(Event(
            name=name, url=f"{BASE}{m.group(0)}", source="luma",
            organizer=org, city="Copenhagen" if "copenhagen" in origin else None,
        ))
    return out


def _enrich_from_detail(ev: Event, timeout: float) -> None:
    """Detail eventu ma popis a casto i JSON-LD s datem."""
    html = _get(ev.url, timeout)
    detailed = _parse_jsonld(html, ev.url)
    if detailed:
        d = detailed[0]
        ev.date = ev.date or d.date
        ev.description = ev.description or d.description
        ev.city = ev.city or d.city
        ev.organizer = ev.organizer or d.organizer
        return
    soup = BeautifulSoup(html, "html.parser")

    if not ev.description:
        ev.description = _detail_description(soup)
    if not ev.date:
        ev.date = _detail_date(soup)


def _detail_description(soup) -> str | None:
    """Popis: meta description, og:description, twitter:description a jako
    posledni zaloha nejdelsi textovy blok na strance."""
    for attrs in (
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"},
    ):
        meta = soup.find("meta", attrs=attrs)
        if meta and meta.get("content", "").strip():
            return _clean(meta["content"])

    longest = ""
    for tag in soup.find_all(["p", "div", "section", "article"]):
        text = tag.get_text(" ", strip=True)
        if len(text) > len(longest):
            longest = text
    return _clean(longest) if longest else None


def _detail_date(soup) -> str | None:
    """Datum z <time datetime="...">. Bereme prvni parsovatelne."""
    for t in soup.find_all("time"):
        dt = (t.get("datetime") or "").strip()
        if dt:
            return dt[:10]
    return None


# ---------------------------------------------------------------- pomocne
def _walk(node):
    if isinstance(node, list):
        for x in node:
            yield from _walk(x)
    elif isinstance(node, dict):
        yield node
        for v in node.values():
            if isinstance(v, (list, dict)):
                yield from _walk(v)


def _city(loc):
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            return addr.get("addressLocality")
        return loc.get("name")
    return None


def _organizer(org):
    if isinstance(org, dict):
        return org.get("name")
    if isinstance(org, list) and org and isinstance(org[0], dict):
        return org[0].get("name")
    return None


def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip()[:1500] or None


def _is_free(node) -> bool:
    offers = node.get("offers")
    offers = offers if isinstance(offers, list) else ([offers] if offers else [])
    return any(str(o.get("price", "")).strip() in ("0", "0.0", "0.00")
               for o in offers if isinstance(o, dict))
