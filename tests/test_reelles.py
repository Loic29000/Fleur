"""Vraies mains Winamax (pseudos anonymisés) : format réel validé sur ~70 000 mains.

Particularités du format confirmées sur les historiques :
- pas de ligne "Uncalled bet" : la mise non suivie est incluse dans "collected" ;
- "Total pot" est net du rake ;
- "posts small/big blind X out of position" : blindes payées en arrivant,
  comptées par Winamax dans le total "raises X to Y" ;
- ESCAPE : "Escape to Pot: total X" ajoute de l'argent au pot.
"""

import pytest
from conftest import FIXTURES

from fleur.db import Database
from fleur.diagnostics import consistency_problems
from fleur.parser import iter_hands
from fleur.stats import hand_counters
from fleur.watcher import HistoryWatcher


@pytest.fixture(scope="module")
def hands():
    text = (FIXTURES / "winamax_reelles.txt").read_text(encoding="utf-8")
    return {h.hand_id.split("-")[1]: h for h in iter_hands(text)}


def nets(hand):
    return {p: c["net"] for p, c in hand_counters(hand).items()}


def test_all_clean(hands):
    assert len(hands) == 8
    for h in hands.values():
        assert h.unknown_lines == [], h.hand_id
        assert consistency_problems(h) == [], h.hand_id
        assert h.is_cash and not h.is_tournament


def test_allin_excess_included_in_collected(hands):
    h = hands["874"]
    assert h.uncalled == {}
    assert h.total_pot == pytest.approx(3.82) and h.rake == pytest.approx(0.23)
    n = nets(h)
    assert n["Hero"] == pytest.approx(-2.00)
    assert n["Joueur3"] == pytest.approx(1.79)  # 3.82 encaissés - 2.03 misés (0.03 non suivis inclus)
    c = hand_counters(h)
    assert c["Hero"]["did_3bet"] == 1 and c["Joueur3"]["call_3bet"] == 1
    assert c["Hero"]["did_cbet_f"] == c["Hero"]["did_cbet_t"] == 1
    assert c["Joueur3"]["opp_fcbet_t"] == 1 and c["Joueur3"]["fold_cbet_t"] == 0


def test_blinds_out_of_position(hands):
    h = hands["1046"]
    assert [a.kind for a in h.actions if a.player == "Joueur4"][:2] == ["post_other", "post_other"]
    n = nets(h)
    assert n["Joueur4"] == pytest.approx(-0.71)  # "to 0.17" inclut les 0.07 de blindes
    assert n["Hero"] == pytest.approx(0.68)
    assert hand_counters(h)["Joueur4"]["pfr"] == 1

    h = hands["160"]
    n = nets(h)
    assert n["Joueur3"] == pytest.approx(0.12)
    assert n["Joueur2"] == pytest.approx(-0.05)
    assert hand_counters(h)["Joueur2"]["vpip"] == 0  # blinde hors position puis check


def test_escape_added_money(hands):
    h = hands["48160"]
    assert h.added_money == pytest.approx(0.10)
    n = nets(h)
    assert n["Joueur3"] == pytest.approx(0.15)
    assert sum(n.values()) == pytest.approx(0.10)

    n = nets(hands["48056"])
    assert n["Joueur5"] == pytest.approx(0.10) and n["Joueur2"] == pytest.approx(-0.12)


def test_side_pot(hands):
    h = hands["949"]
    assert h.collected == {"Joueur4": pytest.approx(0.51), "Joueur3": pytest.approx(0.01)}
    n = nets(h)
    assert n["Joueur4"] == pytest.approx(0.24) and n["Joueur3"] == pytest.approx(-0.27)


def test_sitting_out_player_is_ignored(hands):
    h = hands["858"]
    assert "Joueur2" not in h.players and len(h.seats) == 5
    assert "Joueur2" not in hand_counters(h)
    assert nets(h)["Hero"] == pytest.approx(0.21)


def test_threebet_pot_showdown(hands):
    c = hand_counters(hands["962"])
    assert c["Joueur2"]["did_3bet"] == 1 and c["Joueur3"]["opp_f3bet"] == c["Joueur3"]["call_3bet"] == 1
    assert c["Joueur2"]["opp_cbet_f"] == 1 and c["Joueur2"]["did_cbet_f"] == 0
    assert c["Joueur2"]["wtsd"] == c["Joueur2"]["wsd"] == 1
    assert c["Joueur2"]["net"] == pytest.approx(2.61) and c["Joueur3"]["net"] == pytest.approx(-2.94)


TOURNAMENT_HAND = """Winamax Poker - Tournament "Expresso" buyIn: 0.92€ + 0.08€ level: 1 - HandId: #1-2-3 - Holdem no limit (10/20) - 2026/11/23 18:00:00 UTC
Table: 'Expresso(1)#0' 3-max (real money) Seat #1 is the button
Seat 1: A (500)
Seat 2: B (500)
Seat 3: C (500)
*** ANTE/BLINDS ***
B posts small blind 10
C posts big blind 20
*** PRE-FLOP ***
A folds
B folds
C collected 30 from pot
*** SUMMARY ***
Total pot 30 | No rake
Seat 3: C won 30

"""


def test_tournaments_skipped_by_default(tmp_path):
    (tmp_path / "t.txt").write_text(TOURNAMENT_HAND, encoding="utf-8")
    db = Database(":memory:")
    hand = next(iter_hands(TOURNAMENT_HAND))
    assert hand.is_tournament and not hand.is_cash
    assert HistoryWatcher(db, [tmp_path]).poll() == []
    db2 = Database(":memory:")
    assert len(HistoryWatcher(db2, [tmp_path], include_tournaments=True).poll()) == 1
