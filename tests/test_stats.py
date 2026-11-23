import pytest
from conftest import FIXTURES

from fleur.db import Database
from fleur.parser import iter_hands
from fleur.stats import compute_all, hand_counters, positions


@pytest.fixture
def hands():
    return list(iter_hands((FIXTURES / "cash_6max.txt").read_text(encoding="utf-8")))


def test_positions(hands):
    pos = positions(hands[0])
    assert pos == {"Dave": "SB", "Eve": "BB", "Charlie": "BTN", "Bob": "CO", "Alice": "HJ", "Hero": "UTG"}


def test_hand1_steal_cbet(hands):
    c = hand_counters(hands[0])
    assert c["Bob"]["opp_steal"] == c["Bob"]["did_steal"] == 1
    assert c["Bob"]["did_rfi"] == 1 and c["Bob"]["pfr"] == 1 and c["Bob"]["vpip"] == 1
    assert c["Charlie"]["opp_3bet"] == 1 and c["Charlie"]["did_cold_call"] == 1 and c["Charlie"]["did_3bet"] == 0
    # le vol a été suivi : pas d'opportunité "fold to steal" pour les blindes
    assert c["Dave"]["opp_fsteal"] == 0
    assert c["Bob"]["opp_cbet_f"] == c["Bob"]["did_cbet_f"] == 1
    assert c["Charlie"]["opp_fcbet_f"] == 1 and c["Charlie"]["fold_cbet_f"] == 0
    assert c["Bob"]["opp_cbet_t"] == 1 and c["Bob"]["did_cbet_t"] == 0
    assert c["Charlie"]["wwsf"] == 1 and c["Bob"]["wwsf"] == 0
    assert c["Hero"]["hands"] == 1 and c["Hero"]["vpip"] == 0
    assert c["Charlie"]["net"] == pytest.approx(0.16)
    assert c["Bob"]["net"] == pytest.approx(-0.14)
    assert c["Eve"]["net_bb"] == pytest.approx(-1.0)


def test_hand2_three_bet(hands):
    c = hand_counters(hands[1])
    assert c["Alice"]["did_rfi"] == 1
    assert c["Charlie"]["did_3bet"] == 1
    assert c["Alice"]["opp_f3bet"] == 1 and c["Alice"]["fold_3bet"] == 1
    assert c["Dave"]["opp_4bet"] == 1 and c["Dave"]["did_4bet"] == 0
    assert c["Charlie"]["net"] == pytest.approx(0.09)
    assert c["Alice"]["net"] == pytest.approx(-0.06)
    assert c["Hero"]["net"] == pytest.approx(-0.02)


def test_hand3_squeeze_checkraise_showdown(hands):
    c = hand_counters(hands[2])
    assert c["Bob"]["did_limp"] == 1 and c["Bob"]["did_rfi"] == 0
    assert c["Charlie"]["opp_unopened"] == 0
    assert c["Dave"]["did_cold_call"] == 1
    assert c["Eve"]["opp_squeeze"] == c["Eve"]["did_squeeze"] == c["Eve"]["did_3bet"] == 1
    assert c["Charlie"]["opp_f3bet"] == c["Charlie"]["fold_3bet"] == 1
    assert c["Dave"]["opp_donk_f"] == 1 and c["Dave"]["did_donk_f"] == 0
    assert c["Eve"]["did_cbet_f"] == 1
    assert c["Dave"]["opp_fcbet_f"] == c["Dave"]["raise_cbet_f"] == 1
    assert c["Dave"]["opp_xr_f"] == c["Dave"]["did_xr_f"] == 1
    assert c["Dave"]["post_br"] == 2 and c["Eve"]["post_calls"] == 2 and c["Eve"]["post_br"] == 1
    for p in ("Dave", "Eve"):
        assert c[p]["saw_flop"] == c[p]["wtsd"] == 1
    assert c["Dave"]["wsd"] == 1 and c["Eve"]["wsd"] == 0
    assert c["Dave"]["net"] == pytest.approx(1.93)
    assert c["Eve"]["net"] == pytest.approx(-2.00)


def test_db_aggregation_and_dedup(hands):
    db = Database(":memory:")
    assert len(db.add_hands(hands)) == 3
    assert db.add_hands(hands) == []  # doublons ignorés
    totals = db.totals(["Charlie", "Inconnu"])
    stats = compute_all(totals["Charlie"])
    assert stats["hands"].num == 3
    assert stats["vpip"].value == pytest.approx(100.0)
    assert stats["pfr"].value == pytest.approx(200 / 3)
    assert stats["3bet"].value == pytest.approx(50.0)  # cold call main 1, 3-bet main 2
    assert compute_all(totals["Inconnu"])["vpip"].value is None
