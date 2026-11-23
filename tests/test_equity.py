import pytest
from conftest import FIXTURES

from fleur.equity import describe, equity, evaluate, parse_cards


def p(text):
    return parse_cards(text)


@pytest.mark.parametrize("cards, name", [
    ("Ah 2d 3c 4s 5h 9d Kc", "quinte"),
    ("Ah Kh Qh Jh Th 2c 3d", "quinte flush"),
    ("As Ad Ah Kd Kc 2c 2d", "full"),
    ("As Ad Ah Ac Kc 2c 2d", "carré"),
    ("2h 5h 9h Jh Kh Ac Ad", "couleur"),
    ("Ah Ad Kc Kd 2s 7c 9d", "double paire"),
    ("Ah Kd 7c 5s 2h", "hauteur"),
])
def test_categories(cards, name):
    assert describe(p(cards)) == name


def test_ordering():
    assert evaluate(p("Ah 2d 3c 4s 5h")) < evaluate(p("2h 3d 4c 5s 6h"))  # la roue est la plus petite quinte
    assert evaluate(p("Ah Ad Kc Kd 2s")) > evaluate(p("Ah Ad Qc Qd Ks"))
    assert evaluate(p("Ah Ad Kc Qd Js")) > evaluate(p("Ah Ad Kc Qd Ts"))  # kicker
    assert evaluate(p("Ah Kh Qh Jh 9h")) == evaluate(p("As Ks Qs Js 9s"))  # couleurs identiques


def test_parse_cards():
    assert p("AhKd") == ["Ah", "Kd"] and p("ah, kd") == ["Ah", "Kd"] and p("10h 9c") == ["Th", "9c"]
    with pytest.raises(ValueError):
        p("Ah Ah")
    with pytest.raises(ValueError):
        p("Zz")


def test_equity_known_values():
    r = equity([p("Ah As"), p("Kd Kc")], trials=20000, seed=1)
    assert r["method"] == "simulation" and r["players"][0]["equity"] == pytest.approx(0.82, abs=0.012)
    r = equity([p("Ah As"), p("Kd Kc")], board=p("2c 7d 9s"))
    assert r["method"] == "exact" and r["boards"] == 990
    # KK gagne avec un roi sans as (2 x 43 + 1 cas K-K) parmi 990 boards
    assert r["players"][1]["win"] == pytest.approx(83 / 990)
    r = equity([p("Ah Kh"), p("Ad Kd")], board=p("2c 7s 9c"))
    assert r["players"][0]["tie"] > 0.9 and r["players"][0]["equity"] == pytest.approx(0.5, abs=0.03)
    with pytest.raises(ValueError):
        equity([p("Ah As")])
    with pytest.raises(ValueError):
        equity([p("Ah As"), p("Ah Kd")])


def test_allin_ev_on_real_hands():
    from fleur.allin import allin_ev, allin_situation
    from fleur.parser import iter_hands
    hands = {h.hand_id.split("-")[1]: h
             for name in ("cash_6max.txt", "winamax_reelles.txt")
             for h in iter_hands((FIXTURES / name).read_text(encoding="utf-8"))}
    # AK contre un brelan au turn : aucune chance, EV = résultat réel
    r = allin_ev(hands["874"], "Hero")
    assert r["equity"] == 0 and r["ev"] == pytest.approx(-2.0) and r["opponents"] == ["9s 9d"]
    # brelan contre AK au turn, vu depuis le gagnant : EV = gain réel, rake au prorata
    r = allin_ev(hands["1003"], "Dave")
    assert r["equity"] == 1 and r["ev"] == pytest.approx(1.93, abs=0.01)
    # tapis à la river ou cartes inconnues : pas d'all-in EV
    assert allin_situation(hands["962"], "Joueur3") is None
    assert allin_situation(hands["1001"], "Bob") is None


def test_report_curves():
    from fleur.allin import hero_allin_report
    from fleur.db import Database
    from fleur.parser import iter_hands
    db = Database(":memory:")
    for name in ("cash_6max.txt", "winamax_reelles.txt"):
        db.add_hands(iter_hands((FIXTURES / name).read_text(encoding="utf-8")))
    r = hero_allin_report(db, "Hero")
    assert len(r["curve_actual"]) == len(r["curve_ev"]) == 12
    assert r["actual"] == pytest.approx(r["curve_actual"][-1])
    assert [a["hand_id"].split("-")[1] for a in r["allins"]] == ["874"]
    assert hero_allin_report(db, "Hero") == r  # deuxième appel servi par le cache
