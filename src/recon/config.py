"""Nacteni konfigurace (ICP, rubrika, key accounts) + env."""
from __future__ import annotations

import csv
import os
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv je nice-to-have
    pass

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"
DOCS_DIR = ROOT / "docs"   # GitHub Pages servíruje tuhle složku — jen OSTRÁ data
DEMO_DIR = ROOT / "demo"   # mock režim píše sem, je v .gitignore


def load_icp(path: Path | None = None) -> dict:
    path = path or CONFIG_DIR / "icp.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_key_accounts(path: Path | None = None) -> list[dict]:
    path = path or CONFIG_DIR / "key_accounts.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def api_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY")


def model() -> str:
    return os.getenv("RECON_MODEL", "claude-sonnet-5")


def slack_webhook() -> str | None:
    return os.getenv("SLACK_WEBHOOK_URL")


# ---------------------------------------------------------------- kontrola
PLACEHOLDER = "TODO"


def validate(icp_cfg: dict, accounts: list[dict]) -> list[str]:
    """Vraci varovani o nevyplnene konfiguraci.

    Existuje proto, ze demo hodnoty vypadaji jako realna data. Radsi at to
    nastroj hlasi nahlas, nez aby obchodnik dostal vymyslenou referenci.
    """
    warn = []
    pos = (icp_cfg.get("positioning") or "").strip()
    if not pos or PLACEHOLDER in pos:
        warn.append(
            "config/icp.yaml → positioning není vyplněné. Claude z něj generuje "
            "angle věty, takže budou obecné nebo nepřesné."
        )
    if not accounts:
        warn.append("config/key_accounts.csv je prázdný — UC2 nic nenajde.")
    if accounts and not any((a.get("owner") or "").strip() for a in accounts):
        warn.append(
            "V key_accounts.csv není u žádné firmy vyplněný sloupec owner. "
            "Je nepovinný — slouží k tomu, aby alert věděl, komu ho poslat."
        )
    return warn
