import zipfile

import pytest
from conftest import FIXTURES

from fleur.parser import iter_hands


@pytest.fixture
def diag(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from fleur.diagnostics import Diagnostics
    return Diagnostics(tmp_path / "Fleur" / "diagnostic")


def fixture_text():
    return (FIXTURES / "cash_6max.txt").read_text(encoding="utf-8")


def test_fixture_hands_are_clean(diag):
    from fleur.diagnostics import consistency_problems
    for hand in iter_hands(fixture_text()):
        assert hand.unknown_lines == []
        assert consistency_problems(hand) == [], hand.hand_id
        diag.check_hand(hand)
    assert diag.problem_count == 0
    assert list(iter_hands(fixture_text()))[2].rake == pytest.approx(0.20)


def test_unknown_lines_and_inconsistencies_are_recorded(diag):
    text = fixture_text()
    # une action dans un format inattendu -> ligne inconnue + gains faux
    text = text.replace("Bob bets 0.08€", "Bob leads 0.08€", 1)
    hands = list(iter_hands(text))
    for hand in hands:
        diag.check_hand(hand)
    assert hands[0].unknown_lines == ["Bob leads 0.08€"]
    assert diag.inconsistent == 1
    report = (diag.dir / "lignes_inconnues.txt").read_text(encoding="utf-8")
    assert "Bob leads #" in report
    assert "18334871-1001" in (diag.dir / "incoherences.txt").read_text(encoding="utf-8")


def test_parse_errors_and_report(diag, tmp_path):
    broken = "Winamax Poker - CashGame - HandId: #1-2-3 - format bizarre\nblabla\n"
    hands = list(iter_hands(broken + "\n\n" + fixture_text(), on_error=diag.parse_error))
    assert len(hands) == 3
    assert diag.parse_errors == 1
    assert "format bizarre" in (diag.dir / "mains_illisibles.txt").read_text(encoding="utf-8")

    from fleur.diagnostics import make_report
    out = make_report(tmp_path, {"test": True})
    names = zipfile.ZipFile(out).namelist()
    assert "infos.json" in names and "diagnostic/mains_illisibles.txt" in names
