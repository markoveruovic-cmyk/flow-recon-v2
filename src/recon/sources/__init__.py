"""Sberne adaptery pro UC1 discovery.

Kazdy zdroj vraci list[Event]. Deduplikaci resi Store podle Event.uid.
Pridani noveho zdroje = jeden soubor + zapis do REGISTRY.
"""
from __future__ import annotations

from . import (
    copenhagen_fintech,
    dansk_erhverv,
    dansk_industri,
    eventbrite,
    luma,
    manual,
    nordic_fintech,
)

REGISTRY = {
    "manual": manual.collect,
    "luma": luma.collect,
    "eventbrite": eventbrite.collect,
    # oborove zdroje, kde realne jsou nase ICP firmy (BFSI, retail, e-commerce)
    "copenhagen_fintech": copenhagen_fintech.collect,
    "dansk_erhverv": dansk_erhverv.collect,
    "dansk_industri": dansk_industri.collect,
    "nordic_fintech": nordic_fintech.collect,
}

# Vychozi kwargs pro jednotlive zdroje. Bez fetch_details Luma ani DI
# nevraci popisy eventu a vsechna skore spadnou pod 50.
DEFAULTS = {
    "luma": {"fetch_details": True},
    "dansk_industri": {"fetch_details": True},
}

# Zdroje, ktere se pousti automaticky (discover, `recon sources` bez --only).
# Eventbrite tu NENI schvalne: z CI ho blokuje IP (405) i pres prohlizec,
# obsah jsou hlavne placene kurzy a API cesta chce ID organizatoru, ktere
# nemame. Zustava v REGISTRY - jde spustit rucne pres --sources/--only.
DEFAULT_SOURCES = [
    "luma",
    "copenhagen_fintech",
    "dansk_erhverv",
    "dansk_industri",
    "nordic_fintech",
]


def collect(source: str, **kw):
    fn = REGISTRY.get(source)
    if not fn:
        raise ValueError(f"neznamy zdroj: {source}. Dostupne: {', '.join(REGISTRY)}")
    merged = {**DEFAULTS.get(source, {}), **kw}
    return fn(**merged)
