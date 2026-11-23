from conftest import FIXTURES

from fleur.parser import iter_hands, parse_amount, split_hands


def load():
    return list(iter_hands((FIXTURES / "cash_6max.txt").read_text(encoding="utf-8")))


def test_parse_amount():
    assert parse_amount("0.02€") == 0.02
    assert parse_amount("€1,234.50") == 1234.5
    assert parse_amount("0,25 €") == 0.25
    assert parse_amount("2€") == 2.0
    assert parse_amount(None) == 0.0


def test_split_and_header():
    text = (FIXTURES / "cash_6max.txt").read_text(encoding="utf-8")
    assert len(split_hands(text)) == 3
    h = load()[0]
    assert h.hand_id == "18334871-1001-1700000001"
    assert h.is_cash
    assert h.table == "Nice 05"
    assert h.max_seats == 6
    assert h.button_seat == 3
    assert (h.sb, h.bb) == (0.01, 0.02)
    assert h.hero == "Hero"
    assert h.hero_cards == "7h 2d"
    assert h.seats[2] == ("Bob", 1.85)


def test_actions_board_collected():
    h1, h2, h3 = load()
    assert h1.board == ["7c", "8d", "2s", "Jh"]
    raise_ = [a for a in h1.actions if a.kind == "raise"][0]
    assert (raise_.player, raise_.amount, raise_.to) == ("Bob", 0.04, 0.06)
    assert h1.collected == {"Charlie": 0.45}
    assert h3.board == ["Ah", "9c", "4d", "2c", "Ks"]
    allin = [a for a in h3.actions if a.allin]
    assert allin and allin[0].player == "Dave" and allin[0].amount == 0.44
    assert h3.shown == {"Dave": "9d 9h", "Eve": "Ad Kd"}


def test_player_names_with_spaces_and_bom():
    text = "﻿" + (FIXTURES / "cash_6max.txt").read_text(encoding="utf-8").replace("Bob", "Le Gros Bob")
    hands = list(iter_hands(text))
    assert len(hands) == 3
    assert any(a.player == "Le Gros Bob" and a.kind == "raise" for a in hands[0].actions)
