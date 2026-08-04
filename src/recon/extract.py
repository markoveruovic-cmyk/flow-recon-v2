"""Claude prevede text eventoveho webu na strukturu (speakeri, sponzori, side eventy)."""
from __future__ import annotations

import json

from .llm import Claude
from .models import Company, EventRecon, Person, SideEvent

SYSTEM = """Jsi extrakcni engine. Ze syroveho textu webu konference vytahnes strukturovana data.

PRAVIDLA:
- Vracis VYHRADNE validni JSON, zadny text okolo, zadne markdown fence.
- Nic si nevymyslis. Co v textu neni, das null nebo vynechas ze seznamu.
- Jmena lidi ber jen tam, kde je jasne, ze jde o speakera/panelistu/moderatora/organizatora.
- Navigacni prvky, cookie listy a patickove odkazy ignorujes.
- event_role je jedno z: keynote, speaker, panelist, moderator, organizer, sponsor_contact.
- U firem role_at_event je jedno z: sponsor, partner, organizer, exhibitor.

SCHEMA:
{
  "name": str,
  "date": str|null,
  "location": str|null,
  "summary": str|null,          // 1-2 vety o cem event je
  "people": [{"name": str, "title": str|null, "company": str|null,
              "event_role": str, "session": str|null}],
  "companies": [{"name": str, "role_at_event": str, "industry": str|null}],
  "side_events": [{"name": str, "when": str|null, "host": str|null,
                   "access": "open"|"invite-only"|"unknown", "url": str|null}]
}"""

USER_TMPL = """Zdrojova URL: {url}

Vytahni strukturu tohoto eventu z nasledujiciho textu.

--- TEXT ZACATEK ---
{text}
--- TEXT KONEC ---"""


# POZOR: smyslena data. Slouzi jen k tomu, aby pipeline slo spustit bez API klice.
# Zadny z techto lidi ani eventu neexistuje.
MOCK = {
    "name": "UKAZKA — smyslena fintech konference",
    "date": "2099-09-18",
    "location": "Copenhagen, DK",
    "summary": "SMYSLENY EVENT pro test bez API klice. Open banking, platby a AI ve financnich sluzbach.",
    "people": [
        {"name": "UKAZKA Osoba Jedna", "title": "Chief Digital Officer", "company": "Salling Group",
         "event_role": "keynote", "session": "Retail meets embedded finance"},
        {"name": "UKAZKA Osoba Dva", "title": "Head of Digital Channels", "company": "Danske Bank",
         "event_role": "speaker", "session": "Open banking in practice"},
        {"name": "UKAZKA Osoba Tri", "title": "VP Product", "company": "Nordea",
         "event_role": "panelist", "session": "AI in customer experience"},
        {"name": "UKAZKA Osoba Ctyri", "title": "Product Lead", "company": "Lunar",
         "event_role": "speaker", "session": "Scaling mobile"},
        {"name": "UKAZKA Osoba Pet", "title": "Partner", "company": "Smyslena VC",
         "event_role": "panelist", "session": "Where fintech capital goes next"},
        {"name": "UKAZKA Osoba Sest", "title": "HR Business Partner", "company": "Smyslene Consulting",
         "event_role": "moderator", "session": "Talent in fintech"},
    ],
    "companies": [
        {"name": "Danske Bank", "role_at_event": "partner", "industry": "banking"},
        {"name": "Smyslena Instituce", "role_at_event": "sponsor", "industry": "public fund"},
        {"name": "Smyslene Consulting", "role_at_event": "sponsor", "industry": "consulting"},
    ],
    "side_events": [
        {"name": "Smysleny Investor Dinner", "when": "17.9. vecer", "host": "Smyslena Instituce",
         "access": "invite-only", "url": None},
        {"name": "Smysleny Pre-Event", "when": "18.9. 08:30", "host": None,
         "access": "open", "url": None},
        {"name": "Smyslena Afterparty", "when": "18.9. 20:00", "host": None,
         "access": "open", "url": None},
    ],
}


def extract_event(text: str, url: str, claude: Claude) -> EventRecon:
    raw = claude.json_call(
        SYSTEM,
        USER_TMPL.format(url=url, text=text),
        max_tokens=8000,
        mock_response=MOCK,
    )
    return _to_recon(raw, url)


def _to_recon(raw: dict, url: str) -> EventRecon:
    recon = EventRecon(
        name=raw.get("name") or "Neznamy event",
        date=raw.get("date"),
        location=raw.get("location"),
        url=url,
        summary=raw.get("summary"),
    )
    for p in raw.get("people") or []:
        if not p.get("name"):
            continue
        recon.people.append(
            Person(
                name=p["name"],
                title=p.get("title"),
                company=p.get("company"),
                event_role=p.get("event_role") or "attendee",
                session=p.get("session"),
                source="website",
                field_origin={"name": "confirmed", "title": "confirmed",
                              "company": "confirmed", "session": "confirmed"}
                if p.get("title") and p.get("company") else {"name": "confirmed"},
            )
        )
    for c in raw.get("companies") or []:
        if not c.get("name"):
            continue
        recon.companies.append(
            Company(
                name=c["name"],
                role_at_event=c.get("role_at_event"),
                industry=c.get("industry"),
                field_origin={"industry": "confirmed"} if c.get("industry") else {},
            )
        )
    for s in raw.get("side_events") or []:
        if not s.get("name"):
            continue
        recon.side_events.append(
            SideEvent(
                name=s["name"], when=s.get("when"), host=s.get("host"),
                access=s.get("access") or "unknown", url=s.get("url"),
            )
        )
    return recon


def dump(recon: EventRecon) -> str:
    return json.dumps(recon.to_dict(), ensure_ascii=False, indent=2)
