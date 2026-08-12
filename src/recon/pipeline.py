"""Orchestrace celeho reconu."""
from __future__ import annotations

from pathlib import Path

from . import attendees as attendees_mod
from . import config, enrich, extract, key_accounts, render, score
from .llm import Claude
from .models import EventRecon


def run(
    url: str,
    *,
    mock: bool = False,
    attendees_csv: Path | None = None,
    fixture: Path | None = None,
    crawl_subpages: bool = True,
    deep: bool = False,
    browser: str = "auto",
) -> tuple[EventRecon, dict]:
    icp_cfg = config.load_icp()
    accounts = config.load_key_accounts()
    claude = Claude(mock=mock)

    # 1) web eventu -> text
    from .fetch import gather
    text, fetch_notes = gather(url, crawl_subpages=crawl_subpages,
                               fixture=fixture, browser=browser)

    # 2) text -> struktura (Claude)
    recon = extract.extract_event(text, url, claude)
    recon.warnings.extend(fetch_notes)

    # 3) attendee list z event appky (dodany rucne)
    if attendees_csv:
        recon = attendees_mod.merge(recon, attendees_mod.load(attendees_csv))

    # 4) key accounts (UC2) - PRED scoringem, kvuli bonusu
    recon = key_accounts.tag(recon, accounts)

    # 5) rubrika
    recon = score.score_all(recon, icp_cfg)

    # 6) LinkedIn search odkazy (zdarma)
    recon = enrich.enrich(recon)

    # 6b) hlubsi rekognoskace pres Claude + webove vyhledavani (stoji tokeny)
    if deep:
        recon = enrich.deep_enrich(recon, claude)
        recon = score.score_all(recon, icp_cfg)   # velikost firmy zmenila skore

    # 7) angles od Claude (jen pro top kontakty - setri tokeny)
    recon = score.add_angles(recon, icp_cfg, claude)

    return recon, icp_cfg
