"""Import seznamu ucastniku z event appky (Swapcard / Brella / Whova).

Vedome NEscrapujeme za loginem - je to proti ToS techto platforem
a technicky krehke. Export/copy-paste si udelas rucne a sem to nasypes jako CSV.

Ocekavane sloupce (case-insensitive, chybejici se toleruji):
  name, title, company, source, notes
"""
from __future__ import annotations

import csv
from pathlib import Path

from .models import EventRecon, Person

ALIASES = {
    "name": ["name", "full name", "jmeno", "attendee"],
    "title": ["title", "job title", "position", "role", "pozice"],
    "company": ["company", "organisation", "organization", "firma", "employer"],
    "source": ["source", "platform"],
    "notes": ["notes", "note", "poznamka"],
}


def _map_row(row: dict) -> dict:
    lower = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
    out = {}
    for field, names in ALIASES.items():
        out[field] = next((lower[n] for n in names if lower.get(n)), "")
    return out


def load(path: Path) -> list[Person]:
    with open(path, encoding="utf-8-sig") as fh:
        rows = [_map_row(r) for r in csv.DictReader(fh)]
    people = []
    for r in rows:
        if not r["name"]:
            continue
        people.append(
            Person(
                name=r["name"],
                title=r["title"] or None,
                company=r["company"] or None,
                event_role="attendee",
                source="attendee_list",
                field_origin={k: "confirmed" for k, v in
                              (("title", r["title"]), ("company", r["company"])) if v},
            )
        )
    return people


def merge(recon: EventRecon, attendees: list[Person]) -> EventRecon:
    """Prida ucastniky. Kdo uz je jako speaker, zustava speakerem (vyssi hodnota)."""
    known = {p.name.strip().lower() for p in recon.people}
    added = 0
    for a in attendees:
        if a.name.strip().lower() in known:
            continue
        recon.people.append(a)
        known.add(a.name.strip().lower())
        added += 1
    recon.warnings.append(f"Pridano {added} ucastniku z attendee listu.")
    return recon
