import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recon import config, key_accounts, score
from recon.models import EventRecon, Person

ICP = config.load_icp()


def _p(**kw):
    return Person(name=kw.pop("name", "Test Person"), **kw)


def test_c_level_bank_scores_high():
    r = EventRecon(name="X")
    p = _p(title="Chief Digital Officer", company="Danske Bank", event_role="keynote")
    score.score_person(p, r, ICP)
    assert p.score >= ICP["thresholds"]["must_meet"]
    assert p.icp_id == "bfsi"


def test_hr_role_is_downweighted():
    r = EventRecon(name="X")
    p = _p(title="HR Business Partner", company="Deloitte", event_role="moderator")
    score.score_person(p, r, ICP)
    assert p.score < ICP["thresholds"]["worth_talk"]


def test_student_excluded():
    r = EventRecon(name="X")
    p = _p(title="Student", company="Aarhus University")
    score.score_person(p, r, ICP)
    assert p.excluded_reason and p.score == 0


def test_key_account_bonus_applies():
    r = EventRecon(name="X", people=[_p(title="Product Lead", company="Nordea A/S")])  # noqa
    key_accounts.tag(r, config.load_key_accounts())
    score.score_all(r, ICP)
    assert r.people[0].is_key_account
    assert "key_account_bonus" in r.people[0].score_breakdown


def test_score_capped_at_100():
    r = EventRecon(name="X")
    p = _p(title="CEO", company="Danske Bank", event_role="keynote")
    p.is_key_account = True
    score.score_person(p, r, ICP)
    assert p.score <= 100


def test_fuzzy_company_match():
    """Pozor: bere firmy z realne config/key_accounts.csv, ne z fixture."""
    accs = config.load_key_accounts()
    assert key_accounts.match_company("Danske Bank A/S", accs)
    assert key_accounts.match_company("Nordea Bank Abp", accs)
    assert key_accounts.match_company("Totally Unrelated ApS", accs) is None


def test_fuzzy_match_handles_legal_suffixes_and_dots():
    """Pravni pripony (A/S, ApS) a tvary s teckou ('Alm. Brand') musi sednout."""
    accs = config.load_key_accounts()
    assert key_accounts.match_company("Pleo ApS", accs)["company"] == "Pleo"
    assert key_accounts.match_company("Alm. Brand A/S", accs)["company"] == "Alm. Brand"
    assert key_accounts.match_company("Saxo Bank A/S", accs)["company"] == "Saxo Bank"
    assert key_accounts.match_company("Coop Danmark A/S", accs)["company"] == "Coop Danmark"


def test_fuzzy_match_no_substring_false_positive():
    """Regrese: 'Normal' se nesmi najit uvnitr 'Abnormal'/'Normalise'."""
    accs = config.load_key_accounts()
    assert key_accounts.match_company("Abnormal Security A/S", accs) is None
    assert key_accounts.match_company("Normalise Data ApS", accs) is None


def test_html_report_renders():
    from recon import render_html
    r = EventRecon(name="Test Event", date="2026-06-18", location="Kodan")
    p = _p(name="UKAZKA Osoba", title="Head of Digital", company="Danske Bank",
           event_role="speaker", session="Open banking")
    r.people.append(p)
    key_accounts.tag(r, config.load_key_accounts())
    score.score_all(r, ICP)
    html = render_html.html_report(r, ICP)
    assert "<!doctype html>" in html
    assert "UKAZKA Osoba" in html
    assert "Proč tohle číslo?" in html
    assert str(p.score) in html


def test_html_escapes_injection():
    from recon import render_html
    r = EventRecon(name="X")
    r.people.append(_p(name="<script>alert(1)</script>", title="CEO", company="Danske Bank"))
    score.score_all(r, ICP)
    html = render_html.html_report(r, ICP)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
