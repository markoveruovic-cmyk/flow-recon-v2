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


# Vychozi volby pro jednotlive zdroje.
# fetch_details u Lumy: kalendar vraci jen nazev a poradatele, POPIS NE.
# Bez popisu nema scoring v cem hledat klicova slova a vsechno spadne pod 50.
# Overeno 12. 8. 2026 na ostrych datech - 27 eventu, vsechna skore 8-43.
DEFAULTS = {
    "luma": {"fetch_details": True},
}


def collect(source: str, **kw):
    fn = REGISTRY.get(source)
    if not fn:
        raise ValueError(f"neznamy zdroj: {source}. Dostupne: {', '.join(REGISTRY)}")
    opts = {**DEFAULTS.get(source, {}), **kw}
    return fn(**opts)
