# Flow Event Recon

Jeden nástroj pro všechny tři use casy. Etnetera Flow.

| | Use case | Příkaz | Výstup |
|---|---|---|---|
| **UC1** | Najdi mi zajímavé eventy | `discover` | seznam eventů se skóre |
| **UC2** | Sleduj key accounts | `watch` | kde se objevily naše firmy |
| **UC3** | Připrav mě na event | `recon` | koho potkat a co mu říct |

Výstup je propojený statický web: seznam eventů → klik → recon.

**Návod na nasazení a testování: [TUTORIAL.md](TUTORIAL.md)**
Design převzatý 1:1 z PoC (Montserrat, zelená `#3DBE7A`) — tokeny jsou v `src/recon/theme.py`,
takže se to dá kdykoli slít do jednoho webu.

**Stav:** funkční kostra. Celý řetěz běží end-to-end bez API klíče v `--mock` režimu.
Až přijde Claude API klíč, hodíš ho do `.env` a mock vypneš.

> ### Žádná smyšlená data v ostrém provozu
> Ukázková data v `fixtures/` jsou **smyšlená** — eventy ani lidé neexistují,
> proto se jmenují `UKAZKA` a mají rok 2099.
>
> Mock režim **fyzicky nemůže** zapsat do `docs/`, které se publikují na GitHub
> Pages — píše do `demo/`, které je v `.gitignore`. Každá stránka vygenerovaná
> v mock režimu má navíc červený pruh „tyhle eventy neexistují".
> Hlídají to testy `test_mock_never_writes_to_docs`
> a `test_no_invented_events_in_shipped_config`.

---

## Rychlý start

```bash
pip install -r requirements.txt

# UC1 — posbírat a oskórovat eventy
PYTHONPATH=src python -m recon.cli discover --mock --from fixtures/demo_events.json

# UC3 — recon jednoho z nich
PYTHONPATH=src python -m recon.cli recon --mock \
  --url https://nordicfintechsummit.dk/2026 \
  --fixture fixtures/sample_event.html \
  --attendees data/attendees_example.csv

# UC3 s hlubší rekognoskací — Claude si dohledá firmy přes web search
PYTHONPATH=src python -m recon.cli recon --url https://... --deep

# UC2 — co se chytlo na key accounts
PYTHONPATH=src python -m recon.cli watch

# otevři docs/index.html
```

Testy: `PYTHONPATH=src pytest -q`

---

## Proč to jde spojit do jednoho nástroje

Tři use casy vypadají jako tři projekty, ale jsou to **tři úrovně přiblížení na jednu věc**:

```
UC1  který event?    →  skóruje EVENTY   0–100
UC3  kdo na něm?     →  skóruje LIDI     0–100
UC2                  →  není třetí obrazovka, je to filtr přes obojí
```

To poslední je klíč. Key accounts nejsou samostatný pipeline — je to **příznak**,
který se přilepí na event (UC1) i na člověka (UC3). Proto v UI nemá vlastní workflow,
jen vlastní záložku a odznak u záznamů.

Díky tomu sdílí všechny tři jednu páteř:

- **jeden `config/icp.yaml`** — stejné ICP obory skórují eventy i lidi
- **jeden `store.py`** (SQLite) — paměť mezi běhy, deduplikace, „co je nové"
- **jeden matcher** key accountů — používá ho UC1 i UC3
- **jeden web** — seznam, watchlist a recony jsou provázané stránky

### Co z toho vypadlo navíc

UC2 najde v popisu eventu jen `Nordea — zmínka`. Když pak na ten samý event
pustíš UC3, alert se sám přepíše na `Nordea — konkrétní jméno (VP Product)`.
Alert se zpřesní, protože obojí sedí nad stejnými daty. Odděleně bys tohle nedostal.

---

## Architektura

```
                   config/icp.yaml          ← jediné místo, kde se ladí
                          │
   ┌──────────────────────┼──────────────────────┐
   │                      │                      │
 UC1 discover          UC2 watch            UC3 recon
 sources/*.py          watch.py             fetch → extract → score
 score_event()         key_accounts.py      → angles od Claude
   │                      │                      │
   └──────────────► store.py (SQLite) ◄──────────┘
                          │
                   render_html.py
                          │
              docs/  →  GitHub Pages
       index.html · watchlist.html · <event>.html · events.csv
```

### Kde je Claude a kde není

Záměrně **ne** na skórování. Body dává pevná rubrika v YAMLu — vysvětlitelná,
stabilní mezi běhy, zdarma. Claude dělá tři věci, které rubrika neumí:

1. **Extrakce** — z textu webu eventu vytáhne speakery, sponzory a side eventy.
   Tohle je ten největší přínos: žádný parser na každou konferenci zvlášť.
2. **Shrnutí** eventů pro digest (dávkově, jedno volání na všechny).
3. **Angle** — jedna věta, o čem s daným člověkem mluvit. Smí posunout skóre o ±10,
   ale musí to zdůvodnit.

U každého čísla na webu je tlačítko **„Proč tohle číslo?"** s rozpadem bodů.

### Původ dat

Každé pole si nese `field_origin`: `confirmed` (stálo to na webu / v tvém exportu),
`inferred` (Claude odvodil), `guessed` (odhad — typicky LinkedIn search odkaz).
Z toho se počítá štítek u kontaktu: **ověřeno / částečně odvozeno / odhad, ověř**.
Nástroj radši přizná odhad, než aby tvářil jistotu. Celé vysvětlení má vlastní
stránku `jak-to-funguje.html`.

---

## Vztah k PoC

[PoC](https://markoveruovic-cmyk.github.io/flow-event-recon/) (v0.3, 31 eventů)
řeší UC1 a řeší ho dobře — filtry, shortlist, poznámky, CSV, localStorage.

**Nezahazuje se.** PoC už teď čte data z `events.csv`. Tenhle repozitář ten CSV
generuje. Rozdělení práce:

- Python pipeline = **producent dat** (sběr, skóre, shrnutí, key accounts)
- statický web = **konzument** (filtry, uložené položky, tisk)

Před sloučením je potřeba vyjasnit jedno: jestli PoC bereme jako frontend
a jen ho napojíme na tenhle `events.csv`, nebo jestli jeho featury (shortlist,
poznámky) přeneseme sem. To je rozhodnutí, ne technická překážka.

---

## Zdroje eventů

| Zdroj | Stav | Poznámka |
|---|---|---|
| `manual` | hotovo | JSON/CSV. Nejspolehlivější, nezávisí na cizím HTML. |
| `luma` | skeleton | Parsuje JSON-LD z veřejných kalendářů. Nemá stabilní API. |
| `eventbrite` | skeleton | Veřejné search API zrušili 2020. Jde jen přes organizer endpointy s tokenem. |
| Copenhagen Fintech | chybí | PoC ho už používá — přenést. |
| LinkedIn Events | nebude | Scraping proti ToS, technicky nespolehlivé. |

Přidání zdroje = jeden soubor v `src/recon/sources/` + zápis do `REGISTRY`.
Zbytek pipeline se nemění.

---

## Co se musí doladit

| Věc | Stav |
|---|---|
| Kalibrace obou rubrik | Můj odhad. Tvůj digest dává mobile meetupu 72, moje rubrika 51. |
| Velikost firmy (UC3) | Chybí. Všichni „unknown". Chce to firemní databázi. |
| Side eventy mimo web eventu | Chybí. Teď jen ty na stránce. |
| Notifikace | Alerty se zakládají, ale nikam se neposílají (Slack vypnutý záměrně). |

---

## Reálné limity

**LinkedIn.** Scraping profilů je proti ToS a technicky křehký. Agent proto generuje
vyhledávací odkaz, ne profilovou URL. Plná automatika jen přes placené people-data API
(Proxycurl, Apollo, Clay) — rozhodnutí o rozpočtu a GDPR.

**Event appky (Swapcard, Brella, Whova).** Za loginem, scraping proti ToS.
Řešíme podle tvého zadání: seznam vyexportuješ ručně a nasypeš jako CSV.

**Veřejné attendee listy prakticky neexistují.** UC2 spolehlivě detekuje firmu jako
speakera, partnera nebo organizátora. „Kdo se zaregistroval" je mimo dosah, pokud to
organizátor sám nezveřejní.

**JavaScriptové weby.** Když konference renderuje speakery až JS, `httpx` je nevidí.
Řešení až to nastane: Playwright jako druhý fetch backend.

**GDPR.** Zpracováváš jména, pozice a zaměstnavatele na základě oprávněného zájmu.
Data jsou veřejná, ale evidenci a retention si v Etnetera Flow ověřte dřív, než to
pojede na ostro. Attendee CSV jsou proto v `.gitignore`.

---

## Struktura

```
config/icp.yaml           ← ICP obory, oblasti vývoje, obě rubriky, prahy
config/key_accounts.csv   ← sledované firmy (UC2)
data/recon.sqlite         ← paměť mezi běhy (COMMITUJE se)
data/attendees_*.csv      ← exporty z event appek (gitignored — osobní údaje)
docs/                     ← web pro GitHub Pages (COMMITUJE se)
fixtures/                 ← demo data pro offline běh
src/recon/sources/        ← adaptéry zdrojů eventů
src/recon/theme.py        ← design tokeny z PoC (jedno místo)
demo/                     ← výstup mock režimu (gitignored, smyšlená data)
tests/                    ← 23 testů
```

## Nasazení

Podrobně v **[TUTORIAL.md](TUTORIAL.md)**. Ve zkratce:

```bash
pip install -e ".[dev]"     # dá ti příkaz `recon`
./demo.sh                   # ukázka bez API klíče
```

1. Repo jako **Public** (Pages jsou na Free plánu jen ve veřejných repozitářích)
2. Settings → Secrets → `ANTHROPIC_API_KEY`
3. Settings → Actions → General → **Read and write permissions** (jinak Actions nemůže pushnout)
4. Actions → *1. Discover eventy* / *2. Recon jednoho eventu*
5. Settings → Pages → branch `main`, složka `/docs` → dostaneš veřejný odkaz

Rychlá cesta k odkazu: `./publish-demo.sh` vygeneruje ukázkový web do `docs/`,
commitneš, zapneš Pages a máš co poslat kolegům.

