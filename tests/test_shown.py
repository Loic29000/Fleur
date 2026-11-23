import sqlite3

import pytest
from conftest import FIXTURES

from fleur.db import Database
from fleur.parser import iter_hands
from fleur.summary import action_line


@pytest.fixture(scope="module")
def hands():
    out = {}
    for name in ("cash_6max.txt", "winamax_reelles.txt"):
        for h in iter_hands((FIXTURES / name).read_text(encoding="utf-8")):
            out[h.hand_id.split("-")[1]] = h
    return out


@pytest.mark.parametrize("hand, player, expected", [
    ("1003", "Eve", "3-bet préflop, c-bet-call flop, call turn"),
    ("1003", "Dave", "call-call 3-bet préflop, check-raise flop, bet (tapis) turn"),
    ("874", "Hero", "3-bet préflop, c-bet flop, c-bet-call (tapis) turn"),
    ("1046", "Joueur4", "open préflop, c-bet flop, c-bet turn, check river"),
    ("858", "Hero", "call préflop, check-call flop, check turn, bet river"),
    ("962", "Joueur2", "3-bet préflop, check-call flop, check-call turn, check-raise (tapis) river"),
    ("962", "Joueur3", "open-call 3-bet préflop, bet flop, bet turn, bet-call river"),
    ("1002", "Hero", "fold préflop"),
])
def test_action_line(hands, hand, player, expected):
    assert action_line(hands[hand], player) == expected


def test_last_shown_in_db(hands):
    db = Database(":memory:")
    db.add_hands(hands.values())
    shown = db.last_shown("Joueur3", 10)
    assert sorted(s.hand_id.split("-")[1] for s in shown) == ["858", "874", "949", "962"]
    by_hand = {s.hand_id.split("-")[1]: s for s in shown}
    sh = by_hand["874"]
    assert sh.cards == "9s 9d" and sh.board == "4s Ad 9c Ts 3c"
    assert sh.net == pytest.approx(1.79) and sh.net_bb == pytest.approx(89.5)
    assert sh.line == "open-call 3-bet préflop, call flop, raise (tapis) turn"
    # du plus récent au plus ancien, limité
    dates = [s.played_at for s in shown]
    assert dates == sorted(dates, reverse=True)
    assert len(db.last_shown("Joueur3", 2)) == 2
    assert db.last_shown("Personne") == []


def test_old_database_is_backfilled(tmp_path, hands):
    path = tmp_path / "old.db"
    db = Database(path)
    db.add_hands(hands.values())
    # simule une base d'avant la version 2 : pas de mains montrées ni de version
    db.conn.execute("DELETE FROM shown_hands")
    db.conn.execute("DELETE FROM meta")
    db.conn.commit()
    db.close()
    db = Database(path)
    assert db.last_shown("Eve")[0].cards == "Ad Kd"
    assert sqlite3.connect(path).execute("SELECT value FROM meta").fetchone()[0] == "3"


def test_popup_lists_shown_hands(hands):
    from fleur.config import DEFAULT_CONFIG
    from fleur.hud.overlay import render_cards, render_popup
    db = Database(":memory:")
    db.add_hands(hands.values())
    html = render_popup("Joueur3", db.totals(["Joueur3"])["Joueur3"], DEFAULT_CONFIG,
                        shown=db.last_shown("Joueur3"))
    assert "Mains montrées" in html and "raise (tapis) turn" in html and "+1.79" in html
    assert "♥" in render_cards("Ah") and "#4fa3ff" in render_cards("Kd")
    assert "Mains montrées" not in render_popup("X", {}, DEFAULT_CONFIG)
