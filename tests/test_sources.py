"""Offline parser testy pro nove zdroje.

Cizi weby se meni - tyhle testy jistí, ze se parser nerozbije tise. Bezí
proti malym HTML/RSS vzorkum (bez site), ktere odpovidaji realne strukture
overene 14. 8. 2026.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recon import sources
from recon.sources import (
    copenhagen_fintech,
    dansk_erhverv,
    dansk_industri,
    nordic_fintech,
)


def test_registry_has_new_sources():
    for name in ("copenhagen_fintech", "dansk_erhverv", "dansk_industri", "nordic_fintech"):
        assert name in sources.REGISTRY
        assert callable(sources.REGISTRY[name])


def test_copenhagen_fintech_parses_card():
    html = """
    <div class="w-dyn-item">
      <div class="h2">September 21, 2026</div>
      <img alt="Nordic Fintech Week 2026">
      <a class="link-to-page" href="/events/nordic-fintech-week-2026">Read more</a>
    </div>"""
    evs = copenhagen_fintech._parse(html)
    assert len(evs) == 1
    e = evs[0]
    assert e.name == "Nordic Fintech Week 2026"
    assert e.date == "2026-09-21"
    assert e.city == "Copenhagen"
    assert e.url.endswith("/events/nordic-fintech-week-2026")
    assert e.source == "copenhagen_fintech"


def test_copenhagen_fintech_detects_city_from_name():
    """Mesto se bere z nazvu, na Kodan se pada jen jako fallback."""
    def city_of(name):
        html = f"""
        <div class="w-dyn-item">
          <div class="h2">March 18, 2026</div><img alt="{name}">
          <a class="link-to-page" href="/events/x-{hash(name) & 0xffff}">Read more</a>
        </div>"""
        return copenhagen_fintech._parse(html)[0].city

    assert city_of("Stockholm Fintech Week: Founders Breakfast") == "Stockholm"
    assert city_of("Delegation to Singapore Fintech Festival") == "Singapore"
    assert city_of("Slush 2026 Delegation") == "Helsinki"
    assert city_of("Nordic Fintech Week 2026") == "Copenhagen"      # fallback


def test_copenhagen_fintech_title_from_event_text_when_alt_empty():
    """Regrese: karty s prazdnym img[alt] driv dostaly osklivy nazev ze slugu
    URL (vc. query stringu). Nazev musi vzit z .event__text."""
    html = """
    <div class="w-dyn-item">
      <div class="h2">August 18, 2026</div>
      <img alt="">
      <div class="event__text">Who is Responsible When AI Makes Decisions?</div>
      <div class="event__text">University of Copenhagen</div>
      <div class="fs_accordion-1_paragraph-2">Women in Finance and Tech.</div>
      <a class="link-to-rsvp-url" href="https://eventsignup.ku.dk/x?_Cldee=GARBAGE">Read more</a>
    </div>"""
    e = copenhagen_fintech._parse(html)[0]
    assert e.name == "Who is Responsible When AI Makes Decisions?"
    assert e.organizer == "University of Copenhagen"
    assert e.description == "Women in Finance and Tech."
    assert "GARBAGE" not in e.name


def test_dansk_erhverv_reads_microdata():
    html = """
    <div class="card">
      <span itemprop="name">Pride Business Talk 2026</span>
      <time itemprop="startDate" datetime="2026-08-14T09:15">14. aug</time>
      <div itemprop="location"><span itemprop="addressLocality">København</span></div>
      <div itemprop="description">Om ledelse og handling.</div>
      <a class="stretched-link" href="/kurser-og-events/2026/august/pride/">x</a>
    </div>"""
    evs = dansk_erhverv._parse(html)
    assert len(evs) == 1
    e = evs[0]
    assert e.name == "Pride Business Talk 2026"
    assert e.date == "2026-08-14"
    assert e.city == "København"
    assert e.description == "Om ledelse og handling."
    assert e.url.endswith("/kurser-og-events/2026/august/pride/")


def test_dansk_industri_skips_tema_and_parses_danish_date():
    html = """
    <a class="kan-product-card" href="/brancher/di-digital/x/webinar/">
      <h5 class="kan-product-card__type">WEBINAR</h5>
      <div class="kan-product-card__details"><h4>AI som konkurrencefordel</h4></div>
      <div class="kan-product-card__info">Industriens Hus | 25. aug. 2026</div>
    </a>
    <a class="kan-product-card" href="/arrangementer/sog/tema/">
      <h5 class="kan-product-card__type">Tema</h5>
      <div class="kan-product-card__details"><h4>Digitalisering</h4></div>
    </a>"""
    evs = dansk_industri._parse(html)
    assert len(evs) == 1                       # Tema dlazdice preskocena
    e = evs[0]
    assert e.name == "AI som konkurrencefordel"
    assert e.date == "2026-08-25"
    assert e.city == "Industriens Hus"
    assert e.organizer == "DI Digital"         # podle /di-digital/ v URL


def test_nordic_fintech_parses_rss():
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Fintech Event 2026</title>
        <link>https://nordicfintechmagazine.com/a</link>
        <pubDate>Wed, 06 May 2026 12:53:25 +0000</pubDate>
        <description>&lt;p&gt;About payments and fintech.&lt;/p&gt;</description>
      </item>
    </channel></rss>"""
    import xml.etree.ElementTree as ET
    evs = nordic_fintech._parse(ET.fromstring(rss))
    assert len(evs) == 1
    e = evs[0]
    assert e.name == "Fintech Event 2026"
    assert e.date == "2026-05-06"
    assert e.description == "About payments and fintech."
    assert e.url == "https://nordicfintechmagazine.com/a"
