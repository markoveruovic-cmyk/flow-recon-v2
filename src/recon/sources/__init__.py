"""Sberne adaptery pro UC1 discovery.

Kazdy zdroj vraci list[Event]. Deduplikaci resi Store podle Event.uid.
Pridani noveho zdroje = jeden soubor + zapis do REGISTRY.
"""
from __future__ import annotations

from . import eventbrite, luma, manual

REGISTRY = {
    "manual": manual.collect,
    "luma": luma.collect,
    "eventbrite": eventbrite.collect,
}


def collect(source: str, **kw):
    fn = REGISTRY.get(source)
    if not fn:
        raise ValueError(f"neznamy zdroj: {source}. Dostupne: {', '.join(REGISTRY)}")
    return fn(**kw)
