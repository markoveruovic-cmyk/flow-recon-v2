# Ruční seznam eventů

Nejspolehlivější zdroj pro UC1. Nezávisí na cizím HTML, takže se nerozbije,
když Luma nebo Eventbrite předělají web.

Workflow ho čte automaticky (`--from data/manual_events.json`).

## Jak přidat event

Otevři `data/manual_events.json` přes tužku na GitHubu a přidej položku.
Povinné jsou jen `name` a `url`, zbytek zlepšuje skóre:

```json
{
  "name": "Nordic Fintech Week 2026",
  "url": "https://example.dk/event",
  "date": "2026-09-18",
  "city": "Copenhagen",
  "organizer": "Kdo to pořádá",
  "format": "conference",
  "price": "free",
  "description": "Čím podrobnější popis, tím přesnější skóre — hledají se v něm klíčová slova."
}
```

`format`: conference, summit, meetup, workshop, webinar, demo_day
`price`: free, paid
`date`: YYYY-MM-DD

## Proč to má smysl i s funkčními scrapery

Luma a Eventbrite mají slabý poměr signálu k šumu. Lokální dánské weby
(Copenhagen Fintech, oborové asociace) často nemají ani API, ani použitelné HTML.
Pět ručně vložených eventů, o kterých víš, bývá cennějších než padesát
naškrábaných.
