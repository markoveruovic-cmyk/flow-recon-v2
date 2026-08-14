"""Dansk Industri / DI (vcetne DI Digital) - arrangementer.

Nejvetsi danska prumyslova asociace. DI Digital je jejich digitalni vetev;
jeji akce jsou soucasti spolecneho seznamu /arrangementer/.

OVERENO 14. 8. 2026 (kodem, ne rucne):
  - URL je https://www.danskindustri.dk/arrangementer/  HTTP 200, bez blokace
    (Cloudflare pred webem, ale scrapery necha projit).
  - SERVER-RENDERED HTML (Optimizely/EPiServer + "kan-" komponenty).
    POZOR na tag: eventy jsou `<a class="kan-product-card">` (~63 karet),
    NE `div.kan-product-card` - tech je jen 18 a jsou to navigacni dlazdice
    typu "Tema" (kategorie), ktere preskakujeme.
  - ZADNY JSON-LD, microdata, RSS ani iCal - cist se musi text karty.
  - Struktura karty (`a.kan-product-card`):
      typ    -> `.kan-product-card__type` / `h5`  (WEBINAR|KURSUS|NETVÆRK|
                ARRANGEMENT|TEMA)  -> "TEMA" = navigace, preskocit
      nazev  -> `h4` uvnitr `.kan-product-card__details`
      info   -> `.kan-product-card__info` text: misto a/nebo datum,
                datum dansky "25. aug. 2026" (bez strojoveho datetime)
      odkaz  -> href karty (interni)
  - DI Digital eventy poznat podle URL /brancher/di-digital/... - jinak je
    seznam spolecny pro celou asociaci; scoring si nase temata vytahne sam.
"""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from ..models import Event

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://www.danskindustri.dk"
EVENTS_URL = f"{BASE}/arrangementer/"

# Danska zkratka mesice -> cislo. Web pise "25. aug. 2026", "31. maj 2026".
DK_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}
DK_DATE_RE = re.compile(r"(\d{1,2})\.?\s*([a-zæøå]{3})[a-zæøå.]*\s*(\d{4})", re.I)


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
    for card in soup.select("a.kan-product-card"):
        typ_el = card.select_one(".kan-product-card__type")
        typ = (typ_el.get_text(strip=True) if typ_el else "").lower()
        if typ in ("", "tema"):
            continue                      # navigacni dlazdice, ne event

        title_el = card.select_one(".kan-product-card__details h4") or card.find("h4")
        name = title_el.get_text(" ", strip=True) if title_el else ""
        if not name or len(name) < 4:
            continue

        href = card.get("href") or ""
        if href.startswith("/"):
            href = BASE + href
        key = href or name.lower()
        if key in seen:
            continue
        seen.add(key)

        info_el = card.select_one(".kan-product-card__info")
        info = info_el.get_text(" ", strip=True) if info_el else ""

        out.append(Event(
            name=name,
            url=href,
            source="dansk_industri",
            date=_iso_date(info),
            city=_city(info),
            organizer="DI Digital" if "/di-digital/" in href else "Dansk Industri",
            format=_format(typ),
        ))
    return out


def _iso_date(info: str) -> str | None:
    m = DK_DATE_RE.search(info or "")
    if not m:
        return None
    mon = DK_MONTHS.get(m.group(2).lower()[:3])
    if not mon:
        return None
    return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(1)):02d}"


def _city(info: str) -> str | None:
    """Misto byva pred datem, oddelene. Datum utneme, zbytek je lokalita."""
    if not info:
        return None
    without_date = DK_DATE_RE.sub("", info).strip(" |·,-")
    return without_date[:80] or None


def _format(typ: str) -> str | None:
    return {"webinar": "webinar", "kursus": "workshop", "arrangement": "conference",
            "netværk": "meetup", "konference": "conference"}.get(typ)
