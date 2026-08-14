"""Testy retry logiky nad Claude API."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recon import llm


class _Block:
    type = "text"
    text = '[{"uid": "x", "summary": "s", "topic": "ai"}]'


class _Msg:
    content = [_Block()]


class _Overloaded(Exception):
    status_code = 529


class _Messages:
    def __init__(self, fail_times):
        self.calls = 0
        self.fail_times = fail_times

    def create(self, **kw):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise _Overloaded("Overloaded")
        return _Msg()


class _Client:
    def __init__(self, fail_times):
        self.messages = _Messages(fail_times)


def _claude_with(fail_times):
    c = llm.Claude(mock=True)     # neni potreba API klic
    c.mock = False                # ale chceme jit realnou cestou
    c._client = _Client(fail_times)
    return c


def test_json_call_retries_after_529(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda *a: None)   # zadne cekani v testu
    c = _claude_with(fail_times=1)                            # spadne jednou, pak OK
    out = c.json_call("system", "user")
    assert out == [{"uid": "x", "summary": "s", "topic": "ai"}]
    assert c._client.messages.calls == 2                     # opravdu se zkusilo znovu


def test_json_call_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda *a: None)
    c = _claude_with(fail_times=99)                           # padá pořád
    try:
        c.json_call("system", "user")
        assert False, "melo propagovat chybu po vycerpani pokusu"
    except _Overloaded:
        pass
    assert c._client.messages.calls == len(llm.RETRY_DELAYS) + 1   # 1 + 3 opakovani
