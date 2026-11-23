import pytest
from conftest import FIXTURES

from fleur.parser import iter_hands
from fleur.stats import compute_all, hand_counters


@pytest.fixture(scope="module")
def hands():
    return {h.hand_id.split("-")[1]: h
            for name in ("cash_6max.txt", "winamax_reelles.txt")
            for h in iter_hands((FIXTURES / name).read_text(encoding="utf-8"))}


def nz(counters, player, prefix=("opp_bet", "did_bet", "opp_vs", "fold_vs", "call_vs", "raise_vs", "n_")):
    return {k: v for k, v in counters[player].items() if v and k.startswith(prefix)}


def test_flop_and_turn_bets(hands):
    c = hand_counters(hands["1001"])
    # flop : Bob mise 0,08 dans 0,15 (53 % : moyenne), Charlie suit
    assert nz(c, "Bob") == {"opp_bet_f": 1, "did_bet_f": 1, "opp_bet_t": 1, "opp_vs_bet_t": 1,
                            "fold_vs_bet_t": 1, "opp_vs_small": 1, "fold_vs_small": 1, "n_bets": 1}
    # turn : Charlie mise 0,15 dans 0,31 (48 % : petite), Bob passe
    assert nz(c, "Charlie") == {"opp_vs_bet_f": 1, "call_vs_bet_f": 1, "opp_vs_med": 1,
                                "opp_bet_t": 1, "did_bet_t": 1, "n_bets": 1}


def test_check_raise_and_raise_sizes(hands):
    c = hand_counters(hands["1003"])
    assert c["Dave"]["raise_vs_bet_f"] == 1 and c["Dave"]["opp_vs_small"] == 1
    assert c["Eve"]["did_bet_f"] == 1 and c["Eve"]["call_vs_bet_f"] == 1
    assert c["Eve"]["call_vs_bet_t"] == 1 and c["Eve"]["opp_bet_t"] == 0
    assert c["Eve"]["opp_vs_small"] == 2  # relance au flop et tapis au turn : petites mises


def test_overbet_raise_on_river(hands):
    c = hand_counters(hands["48056"])
    # river : Joueur2 mise 0,05 dans 0,15, Joueur5 relance de 0,35 (1,4 pot) et Joueur2 passe
    assert c["Joueur2"]["opp_bet_r"] == 1 and c["Joueur2"]["did_bet_r"] == 1
    assert c["Joueur2"]["fold_vs_bet_r"] == 1 and c["Joueur2"]["opp_vs_big"] == c["Joueur2"]["fold_vs_big"] == 1
    assert c["Joueur5"]["raise_vs_bet_r"] == 1 and c["Joueur5"]["opp_vs_small"] == 1


def test_overbet_frequency():
    text = (FIXTURES / "cash_6max.txt").read_text(encoding="utf-8").split("\n\n\n")[0]
    # Bob mise 0,30 au flop dans un pot de 0,15 : overbet
    text = text.replace("Bob bets 0.08€\nCharlie calls 0.08€", "Bob bets 0.30€\nCharlie calls 0.30€")
    c = hand_counters(next(iter_hands(text)))
    assert c["Bob"]["n_overbets"] == 1 and c["Charlie"]["opp_vs_big"] == 1
    stats = compute_all(c["Bob"])
    assert stats["overbet"].value == 100 and stats["bet_f"].value == 100


def test_popup_street_section():
    from fleur.config import DEFAULT_CONFIG
    from fleur.hud.overlay import render_popup, render_streets
    totals = {"hands": 50, "opp_bet_f": 10, "did_bet_f": 6, "opp_vs_bet_r": 8, "fold_vs_bet_r": 2,
              "opp_vs_big": 4, "fold_vs_big": 3, "n_bets": 10, "n_overbets": 1}
    html = render_streets(totals, DEFAULT_CONFIG)
    for text in ("Par street", "Flop", "River", "60", "25", "Fold vs overbet", "75"):
        assert text in html, text
    assert "Par street" in render_popup("X", totals, DEFAULT_CONFIG)
    assert render_streets({"hands": 3}, DEFAULT_CONFIG) == ""
