"""Testy sjednoceneho pipeline UC1 -> UC2 -> UC3."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from recon import config, score, watch
from recon.models import Alert, Event, EventRecon, Person
from recon.store import Store

ICP = config.load_icp()


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as d:
        s = Store(Path(d) / "t.sqlite")
        yield s
        s.close()


def ev(**kw):
    kw.setdefault("name", "Test Event")
    kw.setdefault("url", "https://example.dk/e1")
    return Event(**kw)


# ---------------------------------------------------------- UC1
def test_event_uid_ignores_tracking_params():
    a = ev(url="https://lu.ma/abc")
    b = ev(url="https://www.lu.ma/abc/?utm_source=slack")
    assert a.uid == b.uid


def test_event_scoring_prefers_dk_icp_events():
    good = ev(name="UKAZKA Fintech konference", city="Copenhagen",
              organizer="Copenhagen Fintech", format="summit",
              description="open banking, payments, digital banking")
    bad = ev(url="https://x.de/2", name="UKAZKA Zahranicni meetup", city="Berlin",
             format="meetup", description="crypto party")
    score.score_event(good, ICP)
    score.score_event(bad, ICP)
    assert good.score > bad.score
    assert good.score >= ICP["thresholds"]["event_top"]


def test_service_area_lifts_non_icp_event():
    """Mobile meetup nema oborove ICP, ale delame mobile - nesmi spadnout na nulu."""
    e = ev(name="UKAZKA Mobile meetup", city="Copenhagen", format="meetup",
           description="mobile app development, iOS, android, UX")
    score.score_event(e, ICP)
    assert e.service_id == "mobile"
    assert e.score >= ICP["thresholds"]["event_maybe"]


def test_store_dedupes_across_runs(store):
    e = ev()
    assert store.upsert_event(e) is True
    assert store.upsert_event(ev()) is False
    assert len(store.events()) == 1


def test_store_preserves_recon_link_on_rediscovery(store):
    e = ev()
    store.upsert_event(e)
    store.mark_recon(e.uid, "report.html")
    store.upsert_event(ev())          # UC1 ho najde znovu pristi tyden
    assert store.get_event(e.uid).has_recon
    assert store.get_event(e.uid).recon_file == "report.html"


# ---------------------------------------------------------- UC2
def test_watch_detects_organizer(store):
    e = ev(name="Danske Bank Tech Open House", organizer="Danske Bank",
           description="Hosted by Danske Bank, engineering culture")
    alerts = watch.scan_events([e], config.load_key_accounts(), store)
    assert any(a.company == "Danske Bank" and a.kind == "organizer" for a in alerts)
    assert "Danske Bank" in e.key_accounts


def test_watch_does_not_repeat_same_alert(store):
    e = ev(name="Fintech day", description="Nordea speaker on stage")
    accs = config.load_key_accounts()
    first = watch.scan_events([e], accs, store)
    second = watch.scan_events([e], accs, store)
    assert len(first) == 1 and second == []


def test_watch_ignores_unrelated_company(store):
    e = ev(name="Yoga retreat", description="Nothing to do with banking")
    assert watch.scan_events([e], config.load_key_accounts(), store) == []


# ---------------------------------------------------------- UC3 -> UC2
def test_recon_upgrades_alert_with_named_person(store):
    from recon import key_accounts
    r = EventRecon(name="UKAZKA Fintech konference", url="https://x.dk/nfs")
    r.people.append(Person(name="UKAZKA Osoba", title="Head of Digital",
                           company="Danske Bank", event_role="speaker"))
    key_accounts.tag(r, config.load_key_accounts())
    alerts = watch.scan_recon(r, "uid123", store)
    assert alerts and "UKAZKA Osoba" in alerts[0].detail


def test_alerts_survive_roundtrip(store):
    store.add_alert(Alert(company="Nordea", owner="Jan", event_uid="u1",
                          event_name="E", event_date="2026-09-01",
                          event_url="https://x", kind="speaker"))
    assert len(store.all_alerts()) == 1
    store.mark_notified([store.all_alerts()[0].uid])
    assert store.unnotified_alerts() == []


# ---------------------------------------------------------- web
def test_site_pages_render(store):
    from recon import render_html
    e = ev(name="UKAZKA Fintech konference", city="Copenhagen", date="2026-09-18",
           description="open banking and payments")
    score.score_event(e, ICP)
    store.upsert_event(e)
    events = store.events()
    html = render_html.html_event_list(events, ICP, {e.uid})
    assert "UKAZKA Fintech konference" in html and "nové" in html
    wl = render_html.html_watchlist(store.all_alerts(), config.load_key_accounts())
    assert "Danske Bank" in wl
    csv = render_html.events_csv(events)
    assert "UKAZKA Fintech konference" in csv and csv.startswith("score,")


# ---------------------------------------------------------- pojistka proti smysleným datům
def test_mock_never_writes_to_docs():
    """Ukazkova data se nesmi dostat do docs/, ktere se publikuji na Pages."""
    import argparse
    from recon import cli, config
    args = argparse.Namespace(mock=True, docs=None)
    assert cli.resolve_docs(args) == config.DEMO_DIR
    args.mock = False
    assert cli.resolve_docs(args) == config.DOCS_DIR


def test_mock_uses_separate_database():
    from recon import cli
    assert cli.db_path(mock=True) != cli.db_path(mock=False)


def test_demo_pages_carry_warning_banner():
    from recon import render_html
    e = ev(name="UKAZKA 1", city="Copenhagen", date="2099-09-18")
    score.score_event(e, ICP)
    html = render_html.html_event_list([e], ICP, mock=True)
    assert "neexistují" in html
    assert "Ukázková data" in html
    live = render_html.html_event_list([e], ICP, mock=False)
    assert "Ukázková data" not in live


def test_no_invented_events_in_shipped_config():
    """config/ nesmi obsahovat smyslena data - to je pro fixtures/."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for f in (root / "config").glob("*"):
        text = f.read_text(encoding="utf-8")
        assert "Nordic Fintech Summit" not in text, f"smyšlený event v {f.name}"
        assert "Jan Novak" not in text, f"smyšlené jméno v {f.name}"


# ---------------------------------------------------------- JS weby
def test_detects_js_rendered_page():
    """Vzorek odpovida tomu, co realne vraci techbbq.dk/speakers/."""
    from recon.fetch import looks_js_rendered
    techbbq = "Speakers 2026\nSpeakers\nEvent Room Speakers\nInvestor Speakers\nLoading…"
    assert looks_js_rendered(techbbq, html_len=80_000)

    normal = "Speakers\n" + "\n".join(f"Jane Doe {i} — CTO, Firma {i}" for i in range(40))
    assert not looks_js_rendered(normal, html_len=80_000)


def test_detects_empty_react_shell():
    from recon.fetch import looks_js_rendered
    assert looks_js_rendered("Menu Home About", html_len=200_000)
    assert not looks_js_rendered("Menu Home About", html_len=8_000)


def test_full_speaker_page_is_not_flagged():
    """Regrese: stranka se 40 speakery ma malo textu ve velkem HTML (fotky),
    ale prohlizec spoustet netreba."""
    from recon.fetch import looks_js_rendered
    full = "Speakers\n" + "\n".join(f"Jane Doe {i} — CTO, Firma {i}" for i in range(40))
    assert not looks_js_rendered(full, html_len=80_000)


def test_browser_missing_gives_actionable_error():
    """Kdyz Playwright chybi, musi to rict, co nainstalovat."""
    import sys
    from unittest.mock import patch
    from recon.fetch import BrowserUnavailable, fetch_html_browser
    with patch.dict(sys.modules, {"playwright.sync_api": None, "playwright": None}):
        try:
            fetch_html_browser("https://example.invalid")
            assert False, "melo vyhodit BrowserUnavailable"
        except BrowserUnavailable as exc:
            assert "playwright install" in str(exc)
