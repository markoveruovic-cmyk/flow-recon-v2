"""Luma (lu.ma).

STAV: skeleton. Luma ma verejne stranky mist (lu.ma/copenhagen) a JSON-LD
v HTML, ale nema stabilni verejne API. Parsovani se obcas rozbije - proto
kazdy beh loguje warning misto tichem selhani.

Az to budeme ladit na ostro, tady se to dela. Zbytek pipeline se nemeni.
"""
from __future__ import annotations

import json
import re

import httpx
from bs4 import BeautifulSoup

from ..models import Event

UA = "Mozilla/5.0 (compatible; FlowReconBot/0.1)"
DEFAULT_CALENDARS = ["https://lu.ma/copenhagen"]


def collect(calendars: list[str] | None = None, timeout: float = 20.0, **_) -> list[Event]:
    out: list[Event] = []
    for cal in calendars or DEFAULT_CALENDARS:
        try:
            html = httpx.get(cal, headers={"User-Agent": UA}, timeout=timeout,
                             follow_redirects=True).text
        except Exception:
            continue
        out.extend(_parse_jsonld(html, cal))
    return out


def _parse_jsonld(html: str, origin: str) -> list[Event]:
    """Luma vklada schema.org/Event jako JSON-LD. Zatim nejstabilnejsi cesta."""
    soup = BeautifulSoup(html, "html.parser")
    events: list[Event] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except json.JSONDecodeError:
            continue
        for node in (data if isinstance(data, list) else [data]):
            if not isinstance(node, dict) or node.get("@type") not in ("Event", "SocialEvent"):
                continue
            loc = node.get("location") or {}
            city = None
            if isinstance(loc, dict):
                addr = loc.get("address")
                city = (addr.get("addressLocality") if isinstance(addr, dict)
                        else loc.get("name"))
            events.append(Event(
                name=node.get("name") or "",
                url=node.get("url") or origin,
                source="luma",
                date=(node.get("startDate") or "")[:10] or None,
                city=city,
                organizer=(node.get("organizer") or {}).get("name")
                          if isinstance(node.get("organizer"), dict) else None,
                description=re.sub(r"\s+", " ", node.get("description") or "")[:1500] or None,
                price="free" if _is_free(node) else None,
            ))
    return [e for e in events if e.name]


def _is_free(node: dict) -> bool:
    offers = node.get("offers")
    offers = offers if isinstance(offers, list) else [offers] if offers else []
    return any(str(o.get("price", "")).strip() in ("0", "0.0", "0.00")
               for o in offers if isinstance(o, dict))
