"""Vystupy: Slack zprava (format z UC3) + plny markdown report."""
from __future__ import annotations

import json

import httpx

from .models import EventRecon


def _plural_people(n: int) -> str:
    if n == 1:
        return "1 člověka"
    if 2 <= n <= 4:
        return f"{n} lidi"
    return f"{n} lidí"


def _header(recon: EventRecon) -> str:
    bits = [recon.name]
    if recon.date:
        bits.append(recon.date)
    if recon.location:
        bits.append(recon.location)
    return " · ".join(bits)


# ------------------------------------------------------------------ Slack
def slack_text(recon: EventRecon, icp_cfg: dict) -> str:
    must = icp_cfg["thresholds"]["must_meet"]
    talk = icp_cfg["thresholds"]["worth_talk"]
    ranked = recon.ranked()

    lines = [f"*{_header(recon)}*"]

    top = [p for p in ranked if p.score >= must]
    if top:
        lines.append(f"\n*MUSÍŠ POTKAT (score {must}+)*")
        for p in top:
            head = f"• *{p.title or '?'} · {p.company or '?'}*"
            if p.session:
                head += f" | session „{p.session}“"
            head += f" | Score: {p.score}"
            lines.append(head)
            lines.append(f"   {p.name} · <{p.linkedin_search_url}|LinkedIn>")
            if p.angle:
                lines.append(f"   → Angle: {p.angle}")

    mid = [p for p in ranked if talk <= p.score < must]
    if mid:
        lines.append(f"\n*STOJÍ ZA TALK (score {talk}–{must - 1})*")
        for p in mid:
            row = f"• {p.title or '?'} · {p.company or '?'} | Score: {p.score}"
            if p.angle:
                row += f" → {p.angle}"
            lines.append(row)

    if recon.companies:
        rel = [c for c in recon.companies if c.is_key_account or c.icp_id]
        names = " · ".join(c.name for c in recon.companies)
        lines.append(f"\n*PARTNEŘI & SPONZOŘI:* {names} ({len(rel)} relevantních pro nás)")

    if recon.side_events:
        se = []
        for s in recon.side_events:
            label = s.name
            if s.access == "invite-only":
                label += " (invite-only)"
            elif s.access == "open":
                label += " (otevřené)"
            se.append(label)
        lines.append(f"*SIDE EVENTY:* {' · '.join(se)}")

    hits = recon.key_account_hits()
    for company, people in hits.items():
        owner = people[0].key_account_owner or "—"
        lines.append(
            f"\n:warning: *KEY ACCOUNT ALERT:* {company} má na eventu "
            f"{_plural_people(len(people))} (owner: {owner})"
        )

    return "\n".join(lines)


def post_to_slack(text: str, webhook_url: str) -> int:
    r = httpx.post(webhook_url, json={"text": text}, timeout=15.0)
    r.raise_for_status()
    return r.status_code


# ------------------------------------------------------------------ Markdown
def markdown_report(recon: EventRecon, icp_cfg: dict) -> str:
    must = icp_cfg["thresholds"]["must_meet"]
    talk = icp_cfg["thresholds"]["worth_talk"]

    out = [f"# Recon: {_header(recon)}", ""]
    if recon.url:
        out.append(f"Zdroj: {recon.url}")
    if recon.summary:
        out += ["", recon.summary]

    def table(people, title):
        if not people:
            return
        out.extend(["", f"## {title}", "",
                    "| Score | Jméno | Role | Firma | Session | Angle | LinkedIn |",
                    "|---|---|---|---|---|---|---|"])
        for p in people:
            ka = " 🔑" if p.is_key_account else ""
            out.append(
                f"| {p.score} | {p.name}{ka} | {p.title or ''} | {p.company or ''} | "
                f"{p.session or ''} | {p.angle or ''} | [hledat]({p.linkedin_search_url}) |"
            )

    ranked = recon.ranked()
    table([p for p in ranked if p.score >= must], f"Musíš potkat ({must}+)")
    table([p for p in ranked if talk <= p.score < must], f"Stojí za talk ({talk}–{must - 1})")
    table([p for p in ranked if p.score < talk], "Zbytek")

    if recon.companies:
        out.extend(["", "## Partneři, sponzoři, organizátoři", "",
                    "| Firma | Role | Obor | Key account |", "|---|---|---|---|"])
        for c in recon.companies:
            out.append(f"| {c.name} | {c.role_at_event or ''} | {c.industry or ''} | "
                       f"{'ano (' + (c.key_account_owner or '') + ')' if c.is_key_account else ''} |")

    if recon.side_events:
        out.extend(["", "## Side eventy", ""])
        for s in recon.side_events:
            out.append(f"- **{s.name}** — {s.when or '?'} · host: {s.host or '?'} · přístup: {s.access}")

    excluded = [p for p in recon.people if p.excluded_reason]
    if excluded:
        out.extend(["", "## Vyfiltrováno", ""])
        for p in excluded:
            out.append(f"- {p.name} ({p.company or '?'}) — {p.excluded_reason}")

    if recon.warnings:
        out.extend(["", "## Poznámky běhu", ""] + [f"- {w}" for w in recon.warnings])

    out.extend(["", "---", "",
                "<details><summary>Rozpad skóre (debug)</summary>", ""])
    for p in ranked:
        out.append(f"- **{p.name}** {p.score} = {json.dumps(p.score_breakdown, ensure_ascii=False)}")
    out.extend(["", "</details>"])

    return "\n".join(out)
