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

# Vychozi kwargs pro jednotlive zdroje. Bez fetch_details Luma nevraci
# popisy eventu a vsechna skore spadnou pod 50.
DEFAULTS = {"luma": {"fetch_details": True}}


def collect(source: str, **kw):
    fn = REGISTRY.get(source)
    if not fn:
        raise ValueError(f"neznamy zdroj: {source}. Dostupne: {', '.join(REGISTRY)}")
    merged = {**DEFAULTS.get(source, {}), **kw}
    return fn(**merged)
