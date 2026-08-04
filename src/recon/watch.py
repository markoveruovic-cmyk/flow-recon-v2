"""UC2 - sledovani key accountu.

Zamerne to NENI samostatny pipeline. Je to vrstva, ktera se dotazuje
na uz posbirana data:
  - nad eventy z UC1  -> "Danske Bank porada / sponzoruje / je zminena"
  - nad lidmi z UC3   -> "Danske Bank ma na eventu 3 lidi"

Diky Store.add_alert() se stejny nalez neohlasi dvakrat.
"""
from __future__ import annotations

import re

from .key_accounts import match_company, normalize
from .models import Alert, Event, EventRecon
from .store import Store

DOMAIN_RE = re.compile(r"\b[\w.+-]+@([\w-]+\.[\w.-]+)\b")


def _mentions(text: str, account: dict) -> str | None:
    """Vrati typ zminky, nebo None. Poradi = od nejsilnejsiho signalu."""
    if not text:
        return None
    low = text.lower()
    name = normalize(account.get("company", ""))
    domain = (account.get("domain") or "").lower()

    hit_name = bool(name) and name in normalize(text)
    hit_domain = bool(domain) and domain in low

    if not (hit_name or hit_domain):
        return None

    window = low
    if re.search(r"\b(host|hosted by|organiz|arranger)\w*\b", window) and hit_name:
        return "organizer"
    if re.search(r"\b(sponsor|partner|supported by)\w*\b", window) and hit_name:
        return "partner"
    if re.search(r"\b(speaker|keynote|panel|talk|present)\w*\b", window) and hit_name:
        return "speaker"
    return "mention"


# ------------------------------------------------------------- UC1 vrstva
def scan_events(events: list[Event], accounts: list[dict], store: Store) -> list[Alert]:
    """Projde nove eventy a hleda v nich key accounts."""
    new_alerts: list[Alert] = []
    for ev in events:
        blob = " ".join(filter(None, [ev.name, ev.description, ev.organizer]))
        hits: list[str] = []
        for acc in accounts:
            kind = _mentions(blob, acc)
            if not kind:
                continue
            hits.append(acc["company"])
            alert = Alert(
                company=acc["company"], owner=acc.get("owner"),
                event_uid=ev.uid, event_name=ev.name, event_date=ev.date,
                event_url=ev.url, kind=kind,
                detail=f"nalezeno v popisu eventu ({ev.source})",
            )
            if store.add_alert(alert):
                new_alerts.append(alert)
        ev.key_accounts = sorted(set(hits))
    return new_alerts


# ------------------------------------------------------------- UC3 vrstva
def scan_recon(recon: EventRecon, event_uid: str, store: Store) -> list[Alert]:
    """Po reconu ohlasi konkretni lidi z key accountu - to je silnejsi
    signal nez zminka v popisu, protoze mas jmeno a roli."""
    new_alerts: list[Alert] = []
    for company, people in recon.key_account_hits().items():
        who = ", ".join(f"{p.name} ({p.title})" if p.title else p.name for p in people[:4])
        alert = Alert(
            company=company, owner=people[0].key_account_owner,
            event_uid=event_uid, event_name=recon.name, event_date=recon.date,
            event_url=recon.url,
            kind="attendee" if all(p.event_role == "attendee" for p in people) else "speaker",
            detail=f"{len(people)}× na eventu: {who}",
        )
        if store.add_alert(alert):
            new_alerts.append(alert)
    return new_alerts


def tag_event_key_accounts(events: list[Event], accounts: list[dict]) -> list[Event]:
    """Jen oznaci, bez zakladani alertu. Pro prekresleni webu."""
    for ev in events:
        blob = " ".join(filter(None, [ev.name, ev.description, ev.organizer]))
        ev.key_accounts = sorted({
            acc["company"] for acc in accounts if _mentions(blob, acc)
        })
    return events


def summary_by_company(alerts: list[Alert]) -> dict[str, list[Alert]]:
    out: dict[str, list[Alert]] = {}
    for a in alerts:
        out.setdefault(a.company, []).append(a)
    return dict(sorted(out.items(), key=lambda kv: -len(kv[1])))
