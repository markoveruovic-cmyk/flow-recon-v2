"""Dansk Erhverv (Danish Chamber of Commerce) - kurzy a eventy.

Oborova asociace. Nejlepe strukturovany ze ctyr novych zdroju - karty nesou
schema.org microdata (itemprop), takze datum i cena jdou cist spolehlive.

OVERENO 14. 8. 2026 (kodem, ne rucne):
  - URL je https://www.danskerhverv.dk/kurser-og-events/  (POZOR: /arrangementer/
    dava 404). HTTP 200 s beznym browser UA, zadna blokace.
  - SERVER-RENDERED HTML obohacene o schema.org MICRODATA (ne JSON-LD).
    ~15 eventovych karet primo v HTML, prohlizec netreba.
  - Kazda karta nese itemprop:
      name        -> nazev
      startDate   -> na <time datetime="2026-06-08T08:00"> (ISO, spolehlive)
      location    -> vnorene schema.org/Place s adresou
      description -> popis
      offers      -> vnorene schema.org/Offer s price + priceCurrency
    Vnejsi kontejner ale NEMA itemtype="schema.org/Event", takze eventy
    seskupujeme pres <time itemprop=startDate> a vylezeme k jeho karte.
  - Odkaz na event: `a.stretched-link` (interni /kurser-og-events/YYYY/...).
  - ZADNY JSON-LD, RSS ani iCal.
  - Obsah je smes kurzu a eventu (kurser-og-events) - filtruje az scoring.
"""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from ..models import Event

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE = "https://www.danskerhverv.dk"
EVENTS_URL = f"{BASE}/kurser-og-events/"


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
    for t in soup.select("[itemprop=startDate]"):
        card = _climb_card(t)
        if not card:
            continue
        name_el = card.select_one("[itemprop=name]")
        link_el = card.select_one("a.stretched-link")
        if not name_el or not link_el:
            continue
        href = link_el.get("href") or ""
        if href.startswith("/"):
            href = BASE + href
        if href in seen:
            continue
        seen.add(href)

        loc = card.select_one("[itemprop=location]")
        desc = card.select_one("[itemprop=description]")
        price = card.select_one("[itemprop=price]")
        price_val = (price.get("content") or price.get_text(strip=True)) if price else None

        out.append(Event(
            name=name_el.get_text(" ", strip=True),
            url=href,
            source="dansk_erhverv",
            date=_iso_date(t),
            city=_city(loc),
            organizer="Dansk Erhverv",
            description=_clean(desc.get_text(" ", strip=True)) if desc else None,
            price="free" if _is_free(price_val) else None,
        ))
    return out


def _climb_card(node):
    """Od <time itemprop=startDate> nahoru ke kontejneru karty."""
    p = node
    for _ in range(10):
        p = p.parent
        if p is None:
            return None
        if p.select_one("a.stretched-link") and p.select_one("[itemprop=name]"):
            return p
    return None


def _iso_date(time_el) -> str | None:
    raw = (time_el.get("datetime") or time_el.get_text(strip=True) or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else None


def _city(loc) -> str | None:
    if not loc:
        return None
    addr = loc.select_one("[itemprop=addressLocality]")
    if addr:
        return addr.get_text(strip=True)
    text = loc.get_text(" ", strip=True)
    return text[:80] or None


def _is_free(price_val) -> bool:
    if price_val is None:
        return False
    return str(price_val).strip().replace(",", ".") in ("0", "0.0", "0.00")


def _clean(text: str | None) -> str | None:
    return re.sub(r"\s+", " ", text or "").strip()[:1500] or None
