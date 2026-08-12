"""Stazeni a ocisteni stranky eventu.

Zamerne NEpiseme parser per web. Stahneme HTML, oholime ho na text
a strukturu necha vytahnout Claude (extract.py). Diky tomu funguje
na libovolnem eventovem webu bez uprav kodu.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; FlowReconBot/0.1; +internal research)"

# Znaky toho, ze stranku dokresluje az JavaScript.
# Overeno na techbbq.dk/speakers/ - v HTML je doslova "Loading..."
JS_MARKERS = re.compile(
    r"(loading[\u2026.]{0,3}\s*$)|(^\s*loading\b)|(please enable javascript)"
    r"|(you need to enable javascript)", re.I | re.M)
DROP_TAGS = ["script", "style", "noscript", "svg", "iframe", "form"]

# stranky, kde na eventovych webech obvykle sedi to, co nas zajima
SUBPAGE_HINTS = [
    "speaker", "talere", "program", "agenda", "schedule", "sessions",
    "partner", "sponsor", "exhibitor", "about",
]


def fetch_html(url: str, timeout: float = 20.0) -> str:
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.text


def clean_text(html: str, limit: int = 60_000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(DROP_TAGS):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [ln for ln in (l.strip() for l in text.splitlines()) if ln]
    return "\n".join(lines)[:limit]


def discover_subpages(html: str, base_url: str, max_pages: int = 6) -> list[str]:
    """Najde odkazy typu /speakers, /program, /partners na stejne domene."""
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#")[0].rstrip("/")
        if urlparse(href).netloc != base_host or href in found or href == base_url.rstrip("/"):
            continue
        blob = (href + " " + a.get_text(" ", strip=True)).lower()
        if any(h in blob for h in SUBPAGE_HINTS):
            found.append(href)
        if len(found) >= max_pages:
            break
    return found


# ------------------------------------------------------------------ browser
class BrowserUnavailable(RuntimeError):
    pass


def fetch_html_browser(url: str, timeout: float = 30.0, wait_ms: int = 2500) -> str:
    """Otevre stranku v prohlizeci na pozadi a vrati HTML PO dobehnuti JS.

    Pro weby jako TechBBQ, ktere seznam speakeru dopisuji az v prohlizeci.
    Vyzaduje:  pip install "flow-event-recon[browser]" && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserUnavailable(
            "Playwright neni nainstalovany. Spust:\n"
            '  pip install "flow-event-recon[browser]"\n'
            "  playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(user_agent=UA)
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=timeout * 1000)
            except Exception:
                pass          # networkidle nekdy nenastane, obsah uz ale byva
            page.wait_for_timeout(wait_ms)
            return page.content()
        finally:
            browser.close()


def looks_js_rendered(text: str, html_len: int) -> bool:
    """Odhad, jestli stranka bez prohlizece prisla prazdna.

    Spolehlivy signal je doslovne "Loading" v textu (tak to ma TechBBQ).
    Velikostni pomer je jen zaloha a je schvalne PRISNY: stranka se 40 speakery
    ma klidne jen ~1 kB textu v 80 kB HTML (fotky, karty), takze vyssi prah
    by oznacil za prazdne i plne stranky. Radsi nechame prohlizec nespustit
    a uzivatel si vynuti --browser on, nez ho poustet zbytecne na kazdou stranku.
    """
    if JS_MARKERS.search(text):
        return True
    return html_len > 60_000 and len(text) < 400


def gather(url: str, *, crawl_subpages: bool = True, fixture: Path | None = None,
           browser: str = "auto") -> tuple[str, list[str]]:
    """Vrati (text, poznamky).

    browser="auto"  zkusi bez prohlizece, a kdyz to vypada prazdne, zopakuje s nim
    browser="on"    rovnou prohlizec
    browser="off"   nikdy prohlizec
    """
    notes: list[str] = []
    if fixture:
        return clean_text(fixture.read_text(encoding="utf-8")), notes

    def grab(u: str, limit: int) -> str:
        """Stahne jednu stranku, v rezimu auto pripadne pres prohlizec."""
        if browser == "on":
            return clean_text(fetch_html_browser(u), limit=limit)
        raw = fetch_html(u)
        text = clean_text(raw, limit=limit)
        if browser == "auto" and looks_js_rendered(text, len(raw)):
            try:
                text = clean_text(fetch_html_browser(u), limit=limit)
                notes.append(f"{u}: stránka je v JavaScriptu, načteno přes prohlížeč")
            except BrowserUnavailable:
                notes.append(
                    f"{u}: stránka je v JavaScriptu a chybí prohlížeč — "
                    'obsah se nenačetl. pip install "flow-event-recon[browser]"'
                )
        return text

    root_html = fetch_html(url) if browser != "on" else fetch_html_browser(url)
    chunks = [f"=== {url} ===\n{clean_text(root_html, limit=40_000)}"]

    if crawl_subpages:
        for sub in discover_subpages(root_html, url):
            try:
                chunks.append(f"=== {sub} ===\n{grab(sub, 25_000)}")
            except Exception as exc:
                chunks.append(f"=== {sub} === (nepodarilo se stahnout: {exc})")
                notes.append(f"{sub}: nepodařilo se stáhnout ({exc})")
    return "\n\n".join(chunks), notes
