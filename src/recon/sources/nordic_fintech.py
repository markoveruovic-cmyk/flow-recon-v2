"""Nordic Fintech Magazine - RSS kategorie "fintech events".

Nordicky fintech magazin. Kalendarova stranka sama zadna strukturovana data
nema (jen rucne kuratorovany rozcestnik), zato je to WordPress a ma RSS.

OVERENO 14. 8. 2026 (kodem, ne rucne):
  - Kalendar https://nordicfintechmagazine.com/fintech-event-calendar/ nema
    v HTML zadny datovany seznam eventu (jen odkazy v menu), takze se necte.
  - POUZITELNA cesta je WordPress RSS kategorie:
      https://nordicfintechmagazine.com/category/fintech-events/feed/
    HTTP 200, content-type application/rss+xml, ~10 <item>.
  - POZOR: jsou to CLANKY/novinky o eventech, NE schema.org/Event zaznamy.
    Nemaji strukturovane startDate ani location - date bereme z <pubDate>
    (datum vydani clanku, ne konani eventu). Scoring pak resi relevanci
    podle nazvu a popisu.
  - Parsujeme standardni knihovnou (xml.etree), zadny lxml navic netreba.
  - Vlastni porádané eventy NFM jedou pres Eventbrite (samostatny zdroj).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from ..models import Event

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
FEED_URL = "https://nordicfintechmagazine.com/category/fintech-events/feed/"


def collect(url: str | None = None, timeout: float = 20.0, **_) -> list[Event]:
    try:
        r = httpx.get(url or FEED_URL, headers={"User-Agent": UA},
                      timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception:
        return []
    return _parse(root)


def _parse(root) -> list[Event]:
    out: list[Event] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        name = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not name or not link or link in seen:
            continue
        seen.add(link)
        desc = item.findtext("description") or ""
        out.append(Event(
            name=name,
            url=link,
            source="nordic_fintech",
            date=_iso_date(item.findtext("pubDate")),
            organizer="Nordic Fintech Magazine",
            description=_clean(desc),
        ))
    return out


def _iso_date(pub: str | None) -> str | None:
    if not pub:
        return None
    try:
        return parsedate_to_datetime(pub).date().isoformat()
    except (TypeError, ValueError):
        return None


def _clean(text: str) -> str | None:
    text = re.sub(r"<[^>]+>", " ", text or "")      # RSS description byva HTML
    return re.sub(r"\s+", " ", text).strip()[:1500] or None
