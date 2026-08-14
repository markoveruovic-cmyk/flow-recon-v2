"""Eventbrite.

OVERENO 4. 8. 2026 (rucne, ne kodem):
  - Verejne vypisove stranky /d/denmark--copenhagen/<kategorie>/ jsou
    server-rendered a jdou cist BEZ API klice. Puvodne jsem myslel,
    ze bude potreba token - neni.
  - KVALITA JE SLABA. Na tech/business vypisech Kodane prevazuji
    placene kurzy (ISTQB, AWS Basics), webinare typu "40X Your Business",
    stare eventy z 2024 a obcas i akce z USA. Pouzitelnych je odhadem
    kazdy paty.
  - Proto tady NEFILTRUJEME - od toho je scoring. Rubrika v icp.yaml
    kurzy a party odstreli sama (ma nizke skore).

OVERENO 14. 8. 2026 k blokaci "405 Not Allowed":
  - Z GitHub Actions (Azure datacentrove IP) vraci Eventbrite 405. NENI to
    o User-Agentu - z bezne IP projde i "bot" UA. Blokuji IP/otisk klienta.
  - Realisticke browser hlavicky (Chrome UA + Accept*) pomahaji jen castecne.
  - Spolehlive to obejde az realny Chromium pres Playwright (spravny TLS
    otisk). Proto: nejdriv httpx, a kdyz spadne, fallback na prohlizec.
    Playwright uz v projektu je (extras [browser], v CI se instaluje).

API cesta (organizers/<id>/events) je nechana jako volitelna pro pripad,
ze byste chteli sledovat konkretniho poradatele. Potrebuje EVENTBRITE_TOKEN.
"""
from __future__ import annotations

import json
import os
import re

import httpx
from bs4 import BeautifulSoup

from ..models import Event

# Realisticke hlavicky - snizi sanci na 405/403 z bezne IP.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BROWSE_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}
API = "https://www.eventbriteapi.com/v3"

# Verejne vypisy, ktere ma smysl prochazet
DEFAULT_BROWSE = [
    "https://www.eventbrite.com/d/denmark--copenhagen/business--conferences/",
    "https://www.eventbrite.com/d/denmark--copenhagen/tech/",
    "https://www.eventbrite.com/d/denmark--copenhagen/startup/",
    "https://www.eventbrite.com/d/denmark--aarhus/business--events/",
]

EVENT_URL = re.compile(r"https://www\.eventbrite\.[a-z.]+/e/[^?#\"']+")


def collect(browse_urls: list[str] | None = None, organizer_ids: list[str] | None = None,
            token: str | None = None, timeout: float = 20.0, **_) -> list[Event]:
    out: list[Event] = []
    seen: set[str] = set()

    for url in browse_urls or DEFAULT_BROWSE:
        try:
            html = _get(url, timeout)
        except Exception:
            html = _get_browser(url, timeout)     # 405/403 blokace -> zkus prohlizec
        if not html:
            continue
        for ev in _parse_browse(html, url):
            if ev.uid not in seen:
                seen.add(ev.uid)
                out.append(ev)

    token = token or os.getenv("EVENTBRITE_TOKEN")
    if token and organizer_ids:
        out.extend(_from_api(organizer_ids, token, timeout))
    return out


def _get(url: str, timeout: float) -> str:
    r = httpx.get(url, headers=BROWSE_HEADERS, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _get_browser(url: str, timeout: float) -> str:
    """Fallback pres realny Chromium, kdyz httpx narazi na 405/403 (viz docstring).
    Kdyz Playwright chybi nebo selze, vrati prazdno - zdroj se tim jen preskoci."""
    try:
        from ..fetch import fetch_html_browser
        return fetch_html_browser(url, timeout=timeout)
    except Exception:
        return ""


def _parse_browse(html: str, origin: str) -> list[Event]:
    """Eventbrite vklada na vypisy JSON-LD ItemList. Kdyz chybi,
    padame na odkazy /e/<slug>."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[Event] = []

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _walk(data):
            if not isinstance(node, dict) or node.get("@type") != "Event":
                continue
            loc = node.get("location") or {}
            addr = loc.get("address") if isinstance(loc, dict) else None
            out.append(Event(
                name=(node.get("name") or "").strip(),
                url=(node.get("url") or "").split("?")[0],
                source="eventbrite",
                date=(node.get("startDate") or "")[:10] or None,
                city=(addr or {}).get("addressLocality") if isinstance(addr, dict) else None,
                organizer=(node.get("organizer") or {}).get("name")
                          if isinstance(node.get("organizer"), dict) else None,
                description=re.sub(r"\s+", " ", node.get("description") or "")[:1500] or None,
            ))
    if out:
        return [e for e in out if e.name]

    for a in soup.find_all("a", href=True):
        m = EVENT_URL.match(a["href"])
        if not m:
            continue
        name = a.get("aria-label") or a.get_text(" ", strip=True)
        name = re.sub(r"^(Save|Share) this event:\s*", "", name or "").strip()
        if name and len(name) > 4:
            out.append(Event(name=name, url=m.group(0), source="eventbrite",
                             city=_city_from_url(origin)))
    return out


def _city_from_url(url: str) -> str | None:
    m = re.search(r"denmark--([a-z]+)", url)
    return m.group(1).capitalize() if m else None


def _from_api(organizer_ids: list[str], token: str, timeout: float) -> list[Event]:
    out: list[Event] = []
    headers = {"Authorization": f"Bearer {token}"}
    for oid in organizer_ids:
        try:
            r = httpx.get(f"{API}/organizers/{oid}/events/", headers=headers,
                          params={"status": "live", "expand": "venue"}, timeout=timeout)
            r.raise_for_status()
            payload = r.json()
        except Exception:
            continue
        for node in payload.get("events", []):
            venue = node.get("venue") or {}
            out.append(Event(
                name=(node.get("name") or {}).get("text") or "",
                url=node.get("url") or "",
                source="eventbrite",
                date=(node.get("start") or {}).get("local", "")[:10] or None,
                city=(venue.get("address") or {}).get("city"),
                description=(node.get("description") or {}).get("text"),
                price="free" if node.get("is_free") else None,
            ))
    return [e for e in out if e.name]


def _walk(node):
    if isinstance(node, list):
        for x in node:
            yield from _walk(x)
    elif isinstance(node, dict):
        yield node
        for v in node.values():
            if isinstance(v, (list, dict)):
                yield from _walk(v)
