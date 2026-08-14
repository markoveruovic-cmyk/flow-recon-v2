"""Napojeni na UC2 - detekce key accountu mezi lidmi a firmami na eventu."""
from __future__ import annotations

import difflib
import re

from .models import EventRecon

LEGAL = re.compile(r"\b(a/s|aps|as|ab|oy|plc|ltd|limited|gmbh|inc|corp|group|holding|s\.a\.)\b", re.I)


def normalize(name: str) -> str:
    name = LEGAL.sub("", (name or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def _token_contains(haystack: str, needle: str) -> bool:
    """Je `needle` v `haystack` jako cele slovo/slova? (ne uvnitr delsiho slova)

    Driv se hledalo pres raw podretezec, takze "Normal" se naslo v "Abnormal"
    a kazdy z "Abnormal Security" byl oznacen jako key account Normal.
    """
    return re.search(rf"\b{re.escape(needle)}\b", haystack) is not None


def match_company(candidate: str, accounts: list[dict], cutoff: float = 0.86) -> dict | None:
    cand = normalize(candidate)
    if not cand:
        return None
    for acc in accounts:
        acc_norm = normalize(acc.get("company", ""))
        if not acc_norm:
            continue
        if (cand == acc_norm or _token_contains(cand, acc_norm)
                or _token_contains(acc_norm, cand)):
            return acc
        if difflib.SequenceMatcher(None, cand, acc_norm).ratio() >= cutoff:
            return acc
    return None


def tag(recon: EventRecon, accounts: list[dict]) -> EventRecon:
    """Oznaci lidi i firmy, ktere patri pod key account."""
    if not accounts:
        return recon
    for p in recon.people:
        acc = match_company(p.company or "", accounts)
        if acc:
            p.is_key_account = True
            p.key_account_owner = acc.get("owner")
    for c in recon.companies:
        acc = match_company(c.name, accounts)
        if acc:
            c.is_key_account = True
            c.key_account_owner = acc.get("owner")
    return recon
