"""Tenka vrstva nad Claude API.

Dulezite: `mock=True` vraci deterministicka data z fixtures, takze
cely pipeline jde spustit a ladit BEZ API klice. Az prijde klic od Entery,
staci ho hodit do .env a mock vypnout.
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import config


class LLMError(RuntimeError):
    pass


class Claude:
    def __init__(self, mock: bool = False, model: str | None = None):
        self.mock = mock
        self.model = model or config.model()
        self._client = None
        if not mock:
            key = config.api_key()
            if not key:
                raise LLMError(
                    "Chybi ANTHROPIC_API_KEY. Spust s --mock, nebo doplň klic do .env"
                )
            import anthropic  # lazy import, at mock rezim nepotrebuje SDK

            self._client = anthropic.Anthropic(api_key=key)

    # ---------------------------------------------------------------
    def json_call(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 4000,
        mock_response: Any = None,
    ) -> Any:
        """Zavola model a vrati naparsovany JSON."""
        if self.mock:
            if mock_response is None:
                raise LLMError("mock rezim: chybi mock_response")
            return mock_response

        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return _parse_json(text)


    # ---------------------------------------------------------------
    def research_call(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 4000,
        max_searches: int = 5,
        mock_response=None,
    ):
        """Jako json_call, ale Claude si smi behem odpovedi googlit.

        Tohle je nejvetsi pako na "vytahnout co nejvic info": misto psani
        scraperu na firemni databaze necham model dohledat si to sam.
        Kazdy hledani neco stoji, proto max_searches.
        """
        if self.mock:
            if mock_response is None:
                raise LLMError("mock rezim: chybi mock_response")
            return mock_response

        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_searches,
            }],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return _parse_json(text)

    # ---------------------------------------------------------------
    def usage_hint(self) -> str:
        return "mock (bez API klíče)" if self.mock else f"Claude API — {self.model}"


def _parse_json(text: str) -> Any:
    """Model obcas obali JSON do ```json fence nebo prida vetu navic."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # posledni pokus: najdi prvni { nebo [ a odpovidajici konec
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = text.find(opener), text.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
        raise LLMError(f"Nepodarilo se naparsovat JSON z odpovedi:\n{text[:500]}")
