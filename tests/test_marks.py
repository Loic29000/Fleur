from conftest import FIXTURES

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database
from fleur.parser import iter_hands
from fleur.web.server import AnalysisApp


def make_app(tmp_path):
    db = Database(tmp_path / "fleur.db")
    db.add_hands(iter_hands((FIXTURES / "winamax_reelles.txt").read_text(encoding="utf-8")))
    db.close()
    return AnalysisApp(tmp_path / "fleur.db", dict(DEFAULT_CONFIG))


def test_mark_lifecycle_and_filters(tmp_path):
    app = make_app(tmp_path)
    _, hands = app.handle("GET", "/api/hands", {}, None)
    first, second = hands["items"][0]["hand_id"], hands["items"][1]["hand_id"]
    _, m = app.handle("POST", "/api/mark", {}, {"hand_id": first, "tags": ["erreur", "à revoir", "erreur"],
                                                 "comment": "  trop large en BB  "})
    assert sorted(m["tags"]) == ["erreur", "à revoir"]
    assert m["comment"] == "trop large en BB"
    app.handle("POST", "/api/mark", {}, {"hand_id": second, "tags": ["bluff"], "comment": ""})
    _, marked = app.handle("GET", "/api/hands", {"mark": "*"}, None)
    assert {h["hand_id"] for h in marked["items"]} == {first, second}
    _, err = app.handle("GET", "/api/hands", {"mark": "erreur"}, None)
    assert [h["hand_id"] for h in err["items"]] == [first] and err["items"][0]["comment"] == "trop large en BB"
    _, tags = app.handle("GET", "/api/mark_tags", {}, None)
    assert tags["counts"] == {"erreur": 1, "à revoir": 1, "bluff": 1} and tags["tags"][0] == "à revoir"
    # tout retirer supprime la marque
    _, m = app.handle("POST", "/api/mark", {}, {"hand_id": second, "tags": [], "comment": ""})
    assert m["tags"] == [] and app.handle("GET", "/api/hands", {"mark": "bluff"}, None)[1]["total"] == 0


def test_mark_unknown_hand(tmp_path):
    import pytest
    from fleur.web.server import ApiError
    app = make_app(tmp_path)
    with pytest.raises(ApiError):
        app.handle("POST", "/api/mark", {}, {"hand_id": "nope", "tags": ["x"]})
