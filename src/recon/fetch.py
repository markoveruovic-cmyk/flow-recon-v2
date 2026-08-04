"""Stazeni a ocisteni stranky eventu.

Zamerne NEpiseme parser per web. Stahneme HTML, oholime ho na text
a strukturu necha vytahnout Claude (extract.py). Diky tomu funguje
na libovolnem eventovem webu bez uprav kodu.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; EnteraReconBot/0.1; +internal research)"
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


def gather(url: str, *, crawl_subpages: bool = True, fixture: Path | None = None) -> str:
    """Vrati slepenec textu z hlavni stranky + relevantnich podstranek."""
    if fixture:
        return clean_text(fixture.read_text(encoding="utf-8"))

    root_html = fetch_html(url)
    chunks = [f"=== {url} ===\n{clean_text(root_html, limit=40_000)}"]

    if crawl_subpages:
        for sub in discover_subpages(root_html, url):
            try:
                chunks.append(f"=== {sub} ===\n{clean_text(fetch_html(sub), limit=25_000)}")
            except Exception as exc:  # jedna rozbita podstranka nesmi shodit recon
                chunks.append(f"=== {sub} === (nepodarilo se stahnout: {exc})")
    return "\n\n".join(chunks)
