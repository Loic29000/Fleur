from datetime import timedelta

import pytest
from conftest import FIXTURES

from fleur.db import Database
from fleur.leaks import REFERENCES, Reference, find_leaks
from fleur.parser import iter_hands


@pytest.fixture(scope="module")
def db():
    db = Database(":memory:")
    for name in ("cash_6max.txt", "winamax_reelles.txt"):
        db.add_hands(iter_hands((FIXTURES / name).read_text(encoding="utf-8")))
    return db


def test_leaks_ranked_and_worded():
    totals = {"hands": 1000, "vpip": 250, "pfr": 200, "opp_f3bet": 200, "fold_3bet": 136,
              "opp_3bet": 400, "did_3bet": 32, "did_cold_call": 28}
    by_pos = {"BB": {"hands": 400, "opp_fsteal": 200, "fold_steal": 140}}
    leaks = find_leaks(totals, by_pos)
    assert [l.ref.stat for l in leaks] == ["fsteal", "f3bet"]  # 3-bet 8 % : dans la fourchette
    assert leaks[0].message == "Fold face au vol en BB trop élevé : 70 % contre 30–45 % (200 occasions)"
    assert leaks[1].message == "Fold au 3-bet trop élevé : 68 % contre 45–55 % (200 occasions)"
    assert leaks[0].severity == "forte"


def test_leaks_need_a_sample():
    assert find_leaks({"hands": 10, "vpip": 9}) == []
    refs = [Reference("vpip", 20, 30, 1.0, min_sample=5)]
    assert find_leaks({"hands": 10, "vpip": 1}, references=refs)[0].direction == "trop bas"
    assert all(r.low < r.high for r in REFERENCES)


def test_dashboard_html(db):
    from fleur.dashboard import build_html, main_hero, sessions
    assert main_hero(db) == "Hero"
    page = build_html(db)
    for text in ("Tableau de bord", "Courbe de gains (€)", "Courbe de gains (big blinds)", "Par position",
                 "Par limite", "0,02 / 0,05 €", "Par format", "Sessions récentes", "<polyline", "Fuites possibles"):
        assert text in page, text
    # mains des 11, 13 février et 4, 8 juin 2025/2026 + fixtures fictives : plusieurs sessions
    s = sessions(db, "Hero")
    assert len(s) >= 3 and sum(x.group.hands for x in s) == 11
    assert all(b.start - a.end > timedelta(minutes=30) for a, b in zip(s, s[1:]))


def test_dashboard_without_hero():
    from fleur.dashboard import build_html
    assert "Aucune main" in build_html(Database(":memory:"))
