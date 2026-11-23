from urllib.parse import quote

import pytest
from conftest import FIXTURES

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database
from fleur.parser import iter_hands
from fleur.web.server import AnalysisApp, ApiError


@pytest.fixture
def app(tmp_path):
    db = Database(tmp_path / "fleur.db")
    db.add_hands(iter_hands((FIXTURES / "cash_6max.txt").read_text(encoding="utf-8")))
    db.close()
    return AnalysisApp(tmp_path / "fleur.db", dict(DEFAULT_CONFIG))


def test_opponents_list(app):
    _, d = app.handle("GET", "/api/opponents", {"min_hands": "1"}, None)
    by_name = {o["player"]: o for o in d["items"]}
    assert set(by_name) == {"Alice", "Bob", "Charlie", "Dave", "Eve"}
    assert all(o["together"] == 3 for o in d["items"])
    # le héros n'a jamais mis d'argent volontairement : aucun pot disputé
    assert all(o["contested"] == 0 and o["bb100_vs"] is None for o in d["items"])
    assert by_name["Charlie"]["vpip"] == pytest.approx(100.0)
    _, none = app.handle("GET", "/api/opponents", {"min_hands": "4"}, None)
    assert none["items"] == []


def test_player_sheet_and_note(app):
    _, p = app.handle("GET", "/api/player/" + quote("Charlie"), {}, None)
    assert p["player"] == "Charlie" and "Charlie" in p["popup"] and "fish" in p["tags"]
    app.handle("POST", "/api/note", {}, {"player": "Charlie", "tag": "reg", "note": "3-bet léger"})
    _, p = app.handle("GET", "/api/player/Charlie", {}, None)
    assert p["tag"] == "reg" and p["note"] == "3-bet léger" and "● Reg" in p["popup"]
    _, d = app.handle("GET", "/api/opponents", {"min_hands": "1"}, None)
    charlie = next(o for o in d["items"] if o["player"] == "Charlie")
    assert charlie["tag"] == "Reg" and charlie["note"] == "3-bet léger"
    with pytest.raises(ApiError):
        app.handle("GET", "/api/player/Personne", {}, None)


def test_contested_hands_filter(tmp_path):
    db = Database(tmp_path / "f.db")
    db.add_hands(iter_hands((FIXTURES / "winamax_reelles.txt").read_text(encoding="utf-8")))
    db.close()
    app = AnalysisApp(tmp_path / "f.db", dict(DEFAULT_CONFIG))
    _, h = app.handle("GET", "/api/hands", {"opponent": "Joueur3"}, None)
    # pots où le héros et Joueur3 ont tous deux mis de l'argent : 874, 858
    assert sorted(x["hand_id"].split("-")[1] for x in h["items"]) == ["858", "874"]
