"""Eventbrite.

STAV: skeleton. Eventbrite zrusil verejne search API (v3 /events/search/
je od 2020 mimo provoz pro tretí strany). Zbyvaji dve cesty:
  a) organizer/venue endpointy s private tokenem - funguje, ale jen pro
     organizatory, ktere si vypises rucne
  b) parsovani verejnych stranek mest - krehke

Implementovana je (a), protoze je stabilni. Seznam organizatoru patri
do config/sources.yaml.
"""
from __future__ import annotations

import os

import httpx

from ..models import Event

API = "https://www.eventbriteapi.com/v3"


def collect(organizer_ids: list[str] | None = None, token: str | None = None, **_) -> list[Event]:
    token = token or os.getenv("EVENTBRITE_TOKEN")
    if not token or not organizer_ids:
        return []

    out: list[Event] = []
    headers = {"Authorization": f"Bearer {token}"}
    for oid in organizer_ids:
        try:
            r = httpx.get(f"{API}/organizers/{oid}/events/",
                          headers=headers, params={"status": "live", "expand": "venue"},
                          timeout=20.0)
            r.raise_for_status()
            payload = r.json()
        except Exception:
            continue
        for node in payload.get("events", []):
            venue = node.get("venue") or {}
            address = venue.get("address") or {}
            out.append(Event(
                name=(node.get("name") or {}).get("text") or "",
                url=node.get("url") or "",
                source="eventbrite",
                date=(node.get("start") or {}).get("local", "")[:10] or None,
                city=address.get("city"),
                description=(node.get("description") or {}).get("text"),
                price="free" if node.get("is_free") else None,
            ))
    return [e for e in out if e.name]
