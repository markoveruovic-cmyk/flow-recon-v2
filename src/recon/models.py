"""Datove modely pro vsechny tri use casy.

Klicova myslenka: Event (UC1) a Person (UC3) jsou dve urovne teze veci.
Oboji se skoruje proti stejnym ICP z config/icp.yaml.
Key account (UC2) neni treti entita - je to priznak na Eventu i Personovi.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any


# ============================================================ UC1
@dataclass
class Event:
    """Event z discovery vrstvy (Luma, Eventbrite, lokalni weby)."""
    name: str
    url: str
    source: str = "manual"           # luma | eventbrite | cph_fintech | manual
    date: str | None = None          # ISO YYYY-MM-DD
    city: str | None = None
    organizer: str | None = None
    description: str | None = None
    price: str | None = None         # "free" | "paid" | None
    topic: str | None = None         # fintech | retail | mobile | ai | general
    format: str | None = None        # meetup | conference | workshop | demo day

    # Rucne nastavena priorita 0-100. Kdyz je vyplnena, prebije vypoctene
    # skore - pro velke horizontalni konference (napr. TechBBQ), ktere nejsou
    # tematicky relevantni, ale chodi tam decision makeri, coz rubrika z popisu
    # nepozna. None = skore se pocita normalne z rubriky.
    priority: int | None = None

    # doplni scoring
    score: int = 0
    score_breakdown: dict[str, int] = field(default_factory=dict)
    icp_id: str | None = None
    service_id: str | None = None    # mobile | design | ai | web
    summary: str | None = None       # AI shrnuti, 2-3 vety

    # doplni watch (UC2)
    key_accounts: list[str] = field(default_factory=list)

    # doplni recon (UC3) - az kdyz si event vyberes
    has_recon: bool = False
    recon_file: str | None = None

    first_seen: str | None = None
    last_seen: str | None = None

    @property
    def uid(self) -> str:
        """Stabilni ID pro deduplikaci napric zdroji."""
        norm = re.sub(r"^https?://(www\.)?", "", (self.url or "").lower())
        norm = norm.split("?")[0].split("#")[0].rstrip("/")
        if norm:
            return hashlib.sha1(norm.encode()).hexdigest()[:16]
        seed = f"{(self.name or '').lower().strip()}|{self.date or ''}"
        return hashlib.sha1(seed.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["uid"] = self.uid
        return d


# ============================================================ UC3
@dataclass
class Company:
    name: str
    domain: str | None = None
    industry: str | None = None
    size: str | None = None
    role_at_event: str | None = None
    icp_id: str | None = None
    is_key_account: bool = False
    key_account_owner: str | None = None
    field_origin: dict[str, str] = field(default_factory=dict)


@dataclass
class Person:
    name: str
    title: str | None = None
    company: str | None = None
    event_role: str = "attendee"
    session: str | None = None
    source: str = "website"          # website | attendee_list | web_search
    linkedin_search_url: str | None = None
    linkedin_url: str | None = None

    # PUVOD DAT - kazde pole vime, odkud je a jak moc mu verit
    # "confirmed" = stalo to cerne na bilem na webu / v exportu
    # "inferred"  = odvodil AI z kontextu
    # "guessed"   = nejlepsi odhad, over rucne
    field_origin: dict[str, str] = field(default_factory=dict)

    score: int = 0
    score_breakdown: dict[str, int] = field(default_factory=dict)
    icp_id: str | None = None
    angle: str | None = None
    is_key_account: bool = False
    key_account_owner: str | None = None
    excluded_reason: str | None = None


    @property
    def confidence(self) -> str:
        """Jak moc verit tomuhle kontaktu jako celku."""
        origins = set(self.field_origin.values())
        if not origins:
            return "medium"
        if "guessed" in origins:
            return "low"
        if "inferred" in origins:
            return "medium"
        return "high"

    @property
    def confidence_label(self) -> str:
        return {"high": "ověřeno", "medium": "částečně odvozeno",
                "low": "odhad, ověř"}[self.confidence]


@dataclass
class SideEvent:
    name: str
    when: str | None = None
    host: str | None = None
    access: str | None = None
    url: str | None = None
    recommended: bool = False


@dataclass
class EventRecon:
    name: str
    date: str | None = None
    location: str | None = None
    url: str | None = None
    summary: str | None = None
    event_uid: str | None = None          # vazba na Event z UC1
    people: list[Person] = field(default_factory=list)
    companies: list[Company] = field(default_factory=list)
    side_events: list[SideEvent] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def ranked(self, min_score: int = 0) -> list[Person]:
        alive = [p for p in self.people if not p.excluded_reason and p.score >= min_score]
        return sorted(alive, key=lambda p: p.score, reverse=True)

    def key_account_hits(self) -> dict[str, list[Person]]:
        out: dict[str, list[Person]] = {}
        for p in self.people:
            if p.is_key_account and p.company:
                out.setdefault(p.company, []).append(p)
        return out


# ============================================================ UC2
@dataclass
class Alert:
    """Nalez key accountu. Vznika v UC1 discovery i v UC3 reconu."""
    company: str
    owner: str | None
    event_uid: str
    event_name: str
    event_date: str | None
    event_url: str | None
    kind: str            # speaker | partner | organizer | attendee | mention
    detail: str | None = None
    created_at: str | None = None
    notified: bool = False

    @property
    def uid(self) -> str:
        seed = f"{self.company}|{self.event_uid}|{self.kind}|{self.detail or ''}"
        return hashlib.sha1(seed.lower().encode()).hexdigest()[:16]
