"""Rucni zdroj: JSON nebo CSV se seznamem eventu.

Nejspolehlivejsi zdroj, protoze nezavisi na cizim HTML.
Hodi se pro lokalni DK weby, ktere nemaji API, a jako fallback,
kdyz se nekterym scraperum rozbije parsovani.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..models import Event

FIELDS = ("name", "url", "date", "city", "organizer", "description",
          "price", "topic", "format")


def collect(path: Path | str | None = None, **_) -> list[Event]:
    if not path:
        return []
    path = Path(path)
    if not path.exists():
        return []

    rows: list[dict]
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
    else:
        with open(path, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))

    out = []
    for r in rows:
        r = {(k or "").strip().lower(): (v or "").strip() if isinstance(v, str) else v
             for k, v in r.items()}
        if not r.get("name"):
            continue
        out.append(Event(
            name=r["name"],
            url=r.get("url") or "",
            source=r.get("source") or "manual",
            priority=_priority(r.get("priority")),
            **{f: (r.get(f) or None) for f in FIELDS if f not in ("name", "url")},
        ))
    return out


def _priority(val) -> int | None:
    """Volitelna rucni priorita 0-100. Prazdno/nesmysl -> None (pocita se skore)."""
    if val in (None, ""):
        return None
    try:
        return max(0, min(100, int(float(val))))
    except (TypeError, ValueError):
        return None
