"""Jeden nastroj, tri prikazy.

  discover  UC1  posbira eventy ze zdroju, oskoruje, shrne, publikuje seznam
  watch     UC2  projde ulozene eventy a nahlasi key accounts
  recon     UC3  k jednomu eventu udela detailni recon (kdo tam bude, co rict)
  site           jen prekresli web z databaze, nic nesbira

Priklady:
  PYTHONPATH=src python -m recon.cli discover --mock --from fixtures/demo_events.json
  PYTHONPATH=src python -m recon.cli watch
  PYTHONPATH=src python -m recon.cli recon --mock --fixture fixtures/sample_event.html \
      --attendees data/attendees_example.csv
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from . import config, extract, render, render_html, score, sources, watch
from .llm import Claude
from .pipeline import run as run_recon
from .store import Store


def slugify(text: str, limit: int = 60) -> str:
    out = "".join(ch if ch.isalnum() else "-" for ch in text.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:limit] or "event"


def warn_config(icp_cfg: dict, accounts: list[dict]) -> list[str]:
    """Vypise varovani o nevyplnene konfiguraci. Vraci je i pro web."""
    warnings = config.validate(icp_cfg, accounts)
    for w in warnings:
        print(f"  ! {w}", file=sys.stderr)
    return warnings


def db_path(mock: bool = False) -> Path:
    """Mock data maji vlastni databazi, aby se nemichala s ostrymi."""
    return config.DATA_DIR / ("recon-demo.sqlite" if mock else "recon.sqlite")


def resolve_docs(args) -> Path:
    """POJISTKA: mock rezim nikdy nepise do docs/, ktere se publikuji.

    Bez tohohle by se smyslena ukazkova data dostala na GitHub Pages
    a vypadala by jako realne eventy.
    """
    explicit = getattr(args, "docs", None)
    if explicit:
        return Path(explicit)
    return config.DEMO_DIR if getattr(args, "mock", False) else config.DOCS_DIR


# ------------------------------------------------------------------ site
def build_site(store: Store, icp_cfg: dict, docs: Path, new_uids=None,
               mock: bool = True) -> None:
    docs.mkdir(parents=True, exist_ok=True)
    accounts = config.load_key_accounts()
    cfg_warnings = config.validate(icp_cfg, accounts)
    events = watch.tag_event_key_accounts(store.events(), accounts)
    alerts = store.all_alerts()

    (docs / "index.html").write_text(
        render_html.html_event_list(events, icp_cfg, new_uids or set(), mock=mock,
                                    cfg_warnings=cfg_warnings),
        encoding="utf-8")
    (docs / "watchlist.html").write_text(
        render_html.html_watchlist(alerts, accounts, mock=mock), encoding="utf-8")
    (docs / "jak-to-funguje.html").write_text(
        render_html.html_how_it_works(
            icp_cfg, {"events": len(events), "alerts": len(alerts)}, mock=mock,
            cfg_warnings=cfg_warnings),
        encoding="utf-8")
    (docs / "events.csv").write_text(render_html.events_csv(events), encoding="utf-8")


# ------------------------------------------------------------------ UC1
def cmd_discover(args) -> int:
    docs = resolve_docs(args)
    icp_cfg = config.load_icp()
    accounts = config.load_key_accounts()
    claude = Claude(mock=args.mock)

    warn_config(icp_cfg, accounts)

    collected = []
    if args.source_file:
        collected += sources.collect("manual", path=args.source_file)
    for src in args.sources or []:
        if src == "manual":
            continue
        try:
            found = sources.collect(src)
        except Exception as exc:
            print(f"  ! zdroj {src} selhal: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        print(f"  {src}: {len(found)} eventů")
        collected += found

    if not collected:
        print("Žádné eventy. Zadej --from soubor.json nebo --sources luma", file=sys.stderr)
        return 1

    for ev in collected:
        score.score_event(ev, icp_cfg)
    score.summarize_events(collected, icp_cfg, claude)

    with Store(db_path(args.mock)) as store:
        new_uids = {ev.uid for ev in collected if store.upsert_event(ev)}
        alerts = watch.scan_events(collected, accounts, store)
        for ev in collected:
            store.upsert_event(ev)          # ulozit i doplnene key_accounts
        store.log_run("discover", len(collected), len(new_uids), len(alerts))
        build_site(store, icp_cfg, docs, new_uids, mock=args.mock)
        top = [e for e in collected if e.score >= icp_cfg["thresholds"]["event_top"]]

    print(f"Posbíráno {len(collected)} eventů, z toho {len(new_uids)} nových.")
    print(f"Nenech si ujít (80+): {len(top)}")
    for e in sorted(top, key=lambda x: -x.score)[:8]:
        print(f"  {e.score:3d}  [{e.date or '?'}] {e.name} · {e.city or '?'}")
    if alerts:
        print(f"\nNové key account nálezy: {len(alerts)}")
        for a in alerts:
            print(f"  {a.company} — {a.kind} — {a.event_name}")
    print(f"\nWeb: {docs / 'index.html'}")
    return 0


# ------------------------------------------------------------------ UC2
def cmd_watch(args) -> int:
    docs = resolve_docs(args)
    args.mock = not config.api_key()
    icp_cfg = config.load_icp()
    accounts = config.load_key_accounts()
    with Store(db_path(args.mock)) as store:
        events = store.events()
        alerts = watch.scan_events(events, accounts, store)
        for ev in events:
            store.upsert_event(ev)
        store.log_run("watch", len(events), 0, len(alerts))
        pending = store.unnotified_alerts()
        build_site(store, icp_cfg, docs, mock=not config.api_key())

    print(f"Prohledáno {len(events)} eventů proti {len(accounts)} key accountům.")
    print(f"Nové nálezy: {len(alerts)} · celkem neohlášených: {len(pending)}")
    for a in pending[:15]:
        print(f"  {a.company:18s} {a.kind:10s} {a.event_name} ({a.event_date or '?'})")
    print(f"\nWatchlist: {docs / 'watchlist.html'}")
    return 0


# ------------------------------------------------------------------ UC3
def cmd_recon(args) -> int:
    docs = resolve_docs(args)
    if not args.url and not args.fixture:
        print("zadej --url nebo --fixture", file=sys.stderr)
        return 1

    url = args.url or f"file://{args.fixture}"
    recon, icp_cfg = run_recon(
        url, mock=args.mock, attendees_csv=args.attendees,
        fixture=args.fixture, crawl_subpages=not args.no_subpages, deep=args.deep,
        browser=args.browser)

    warn_config(icp_cfg, config.load_key_accounts())

    slug = slugify(recon.name)
    filename = f"{slug}.html"
    docs.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (docs / filename).write_text(
        render_html.html_report(recon, icp_cfg, mock=args.mock), encoding="utf-8")
    (config.OUTPUT_DIR / f"{slug}.json").write_text(extract.dump(recon), encoding="utf-8")
    (config.OUTPUT_DIR / f"{slug}.md").write_text(
        render.markdown_report(recon, icp_cfg), encoding="utf-8")

    with Store(db_path(args.mock)) as store:
        existing = store.find_event_by_url(url) if args.url else None
        if existing:
            uid = existing.uid
            recon.event_uid = uid
            store.mark_recon(uid, filename)
        else:
            from .models import Event
            ev = Event(name=recon.name, url=url, source="recon",
                       date=recon.date, city=recon.location)
            score.score_event(ev, icp_cfg)
            ev.summary = recon.summary
            ev.has_recon, ev.recon_file = True, filename
            store.upsert_event(ev)
            uid = ev.uid
        alerts = watch.scan_recon(recon, uid, store)
        store.log_run("recon", 1, 0, len(alerts))
        build_site(store, icp_cfg, docs, mock=args.mock)

    must = icp_cfg["thresholds"]["must_meet"]
    ranked = recon.ranked()
    print(f"{recon.name} — {len(ranked)} kontaktů, "
          f"{len([p for p in ranked if p.score >= must])} v kategorii „najdi tyhle“")
    if alerts:
        print(f"Key account nálezy: {', '.join(a.company for a in alerts)}")
    print(f"Recon: {docs / filename}")
    if args.open:
        webbrowser.open((docs / filename).resolve().as_uri())
    return 0


def _dump_raw(url: str, outdir: Path) -> str | None:
    """Ulozi syrove HTML, aby slo poslat na opravu parseru.

    Duvod: parsery pro Lumu a Eventbrite jsou napsane podle toho, jak ty
    stranky vypadaji v prohlizeci - ne podle skutecneho HTML. Kdyz nic
    nevrati, tenhle soubor je jedina vec, kterou je potreba k oprave.
    """
    import re as _re
    import httpx
    try:
        r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; FlowReconBot/0.1)"},
                      timeout=25.0, follow_redirects=True)
        r.raise_for_status()
    except Exception as exc:
        print(f"    nepodařilo se stáhnout: {exc}")
        return None

    outdir.mkdir(parents=True, exist_ok=True)
    name = _re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[:70] + ".html"
    path = outdir / name
    path.write_text(r.text, encoding="utf-8")

    has_ldjson = 'application/ld+json' in r.text
    n_events = r.text.count('"@type": "Event"') + r.text.count('"@type":"Event"')
    print(f"    uloženo: {path.name}  ({len(r.text) // 1024} kB)")
    print(f"    JSON-LD na stránce: {'ANO' if has_ldjson else 'NE'}"
          f"{f', schema.org Event × {n_events}' if n_events else ''}")
    return str(path)


def cmd_sources(args) -> int:
    """Diagnostika zdroju. Rekne, co ktery zdroj REALNE vraci.

    Existuje proto, ze zdroje se rozbijeji tise - kdyz se zmeni cizi web,
    vratí se prazdny seznam a vypada to, ze se zadne eventy nekonaji.
    """
    icp_cfg = config.load_icp()
    which = args.only or list(sources.REGISTRY)
    total_ok = 0

    if args.dump:
        from .sources import eventbrite as _eb
        from .sources import luma as _lu
        print("=== STAHUJI SYROVÉ HTML pro diagnostiku ===")
        outdir = config.DATA_DIR / "raw"
        targets = []
        if "luma" in which:
            targets += _lu.DEFAULT_CALENDARS[:2]
        if "eventbrite" in which:
            targets += _eb.DEFAULT_BROWSE[:2]
        for url in targets:
            print(f"  {url}")
            _dump_raw(url, outdir)
        print(f"\nSoubory jsou v {outdir}")
        print("Když níže vyjde 0 eventů, pošli je — podle nich se parser opraví.\n")

    for name in which:
        if name == "manual":
            continue
        print(f"\n=== {name} " + "=" * (50 - len(name)))
        try:
            found = sources.collect(name)
        except Exception as exc:
            print(f"  SELHALO: {type(exc).__name__}: {exc}")
            continue

        if not found:
            print("  0 eventů — zdroj nic nevrátil.")
            print("  Buď se změnil cizí web, nebo tam opravdu nic není.")
            continue

        for ev in found:
            score.score_event(ev, icp_cfg)
        found.sort(key=lambda e: -e.score)

        s_date = len([e for e in found if e.date])
        s_desc = len([e for e in found if e.description])
        good = [e for e in found if e.score >= icp_cfg["thresholds"]["event_maybe"]]
        total_ok += len(found)

        print(f"  {len(found)} eventů · datum u {s_date} · popis u {s_desc}")
        print(f"  nad prahem {icp_cfg['thresholds']['event_maybe']}: {len(good)}"
              f"  ({round(100 * len(good) / len(found))}% použitelných)")
        print("  nejlepší:")
        for e in found[:5]:
            print(f"    {e.score:3d}  {(e.date or '?????'):10s} {e.name[:52]}")
        if len(found) > 5:
            print("  nejhorší:")
            for e in found[-2:]:
                print(f"    {e.score:3d}  {(e.date or '?????'):10s} {e.name[:52]}")

    print(f"\nCelkem {total_ok} eventů ze všech zdrojů.")
    if not total_ok:
        print("Žádný zdroj nic nevrátil — zkontroluj připojení nebo jestli"
              " se necizí weby nezměnily.")
    return 0


def cmd_site(args) -> int:
    args.mock = not config.api_key()
    docs = resolve_docs(args)
    icp_cfg = config.load_icp()
    with Store(db_path(args.mock)) as store:
        build_site(store, icp_cfg, docs, mock=not config.api_key())
        n = len(store.events())
    print(f"Web přegenerován z databáze ({n} eventů): {docs / 'index.html'}")
    return 0


# ------------------------------------------------------------------ parser
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="recon", description="Flow Event Recon — UC1+UC2+UC3")
    ap.add_argument("--docs", type=Path, default=None,
                    help="Složka pro web. Výchozí: docs/ ostře, demo/ v mock režimu")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_docs(sp):
        """--docs jde uvest pred i za podprikazem. SUPPRESS zajisti, ze
        neuvedena hodnota neprepise tu globalni."""
        sp.add_argument("--docs", type=Path, default=argparse.SUPPRESS,
                        help="Složka pro web. Výchozí: docs/ ostře, demo/ v mock režimu")

    d = sub.add_parser("discover", help="UC1 — posbírat a oskórovat eventy")
    d.add_argument("--from", dest="source_file", type=Path, help="JSON/CSV se seznamem eventů")
    d.add_argument("--sources", nargs="*", choices=list(sources.REGISTRY),
                   help="Které online zdroje projít")
    d.add_argument("--mock", action="store_true")
    add_docs(d)
    d.set_defaults(func=cmd_discover)

    w = sub.add_parser("watch", help="UC2 — najít key accounts v uložených eventech")
    add_docs(w)
    w.set_defaults(func=cmd_watch)

    r = sub.add_parser("recon", help="UC3 — detailní recon jednoho eventu")
    r.add_argument("--url")
    r.add_argument("--fixture", type=Path)
    r.add_argument("--attendees", type=Path)
    r.add_argument("--mock", action="store_true")
    r.add_argument("--no-subpages", action="store_true")
    r.add_argument("--browser", choices=["auto", "on", "off"], default="auto",
                   help="Prohlížeč pro weby v JavaScriptu. auto = zkusit bez něj, "
                        "a když přijde prázdno, zopakovat s ním")
    r.add_argument("--deep", action="store_true",
                   help="Claude si dohledá firmy přes webové vyhledávání (stojí tokeny)")
    r.add_argument("--open", action="store_true")
    add_docs(r)
    r.set_defaults(func=cmd_recon)

    src = sub.add_parser("sources", help="Diagnostika — co který zdroj reálně vrací")
    src.add_argument("--only", nargs="*", choices=list(sources.REGISTRY),
                     help="Otestovat jen vybrané zdroje")
    src.add_argument("--dump", action="store_true",
                     help="Uložit syrové HTML do data/raw/ (na opravu parseru)")
    src.set_defaults(func=cmd_sources, mock=False)

    s = sub.add_parser("site", help="Jen přegenerovat web z databáze")
    add_docs(s)
    s.set_defaults(func=cmd_site)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # bezne pri `... | head`; nechceme traceback
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise SystemExit(0)
