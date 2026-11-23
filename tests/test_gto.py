import pytest
from conftest import FIXTURES

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database
from fleur.gto import (SPOTS, all_classes, board_texture, compare_rfi, expand, mdf, parse_range,
                       postflop_advice, range_percent, spot_grid)
from fleur.parser import iter_hands
from fleur.web.server import AnalysisApp, ApiError


def test_range_notation():
    assert expand("77+") == ["AA", "KK", "QQ", "JJ", "TT", "99", "88", "77"]
    assert expand("99-66") == ["99", "88", "77", "66"]
    assert expand("ATs+") == ["AKs", "AQs", "AJs", "ATs"]
    assert expand("KTs-K8s") == ["KTs", "K9s", "K8s"]
    assert expand("AK") == ["AKs", "AKo"]
    assert expand("T9o+") == ["T9o"]
    with pytest.raises(ValueError):
        expand("KAs")
    r = parse_range("AA, A5s:0.5, A5s")
    assert r == {"AA": 1.0, "A5s": 1.0}
    assert range_percent(parse_range("22+, A2s+, K2s+, Q2s+, J2s+, T2s+, 92s+, 82s+, 72s+, 62s+, 52s+, 42s+, 32s, "
                                     "A2o+, K2o+, Q2o+, J2o+, T2o+, 92o+, 82o+, 72o+, 62o+, 52o+, 42o+, 32o")) == 100
    assert len(all_classes()) == 169


def test_spots_are_valid_and_sensible():
    widths = {}
    for spot_id in SPOTS:
        g = spot_grid(spot_id)  # lève une erreur si une range est mal écrite
        assert g["cells"] and all(0 < sum(f.values()) <= 1.0001 for f in g["cells"].values())
        widths[spot_id] = sum(g["percent"].values())
    # les ouvertures s'élargissent vers le bouton
    assert widths["rfi_utg"] < widths["rfi_hj"] < widths["rfi_co"] < widths["rfi_btn"]
    assert 12 < widths["rfi_utg"] < 20 and 40 < widths["rfi_btn"] < 52
    assert widths["bb_vs_btn"] > widths["bb_vs_utg"]
    assert spot_grid("rfi_utg")["cells"]["AA"] == {"raise": 1.0} and "72o" not in spot_grid("rfi_btn")["cells"]


@pytest.mark.parametrize("board, kind", [
    ("Ah 7d 2c", "haut sec"), ("8h 7d 6c", "bas connecté"), ("Ks Kd 4c", "pairé"),
    ("Js Ts 9d", "haut connecté"), ("Qh 8h 3h", "monotone"), ("As 2d 3h", "haut sec"), ("Qc 8d 3s", "moyen sec"),
])
def test_board_texture(board, kind):
    assert board_texture(board.split())["kind"] == kind


def test_postflop_advice_and_mdf():
    a = postflop_advice("Ah 7d 2c".split())
    assert a["cbet"][0]["frequency"] > a["cbet"][1]["frequency"]  # plus souvent en position
    assert a["cbet"][0]["sizing"] == "25-33 %"
    assert mdf(0.5) == pytest.approx(2 / 3) and {"bet": "33 % du pot", "mdf": 75} in a["defense"]
    with pytest.raises(ValueError):
        postflop_advice(["Ah", "Kd"])


def test_compare_rfi():
    hero = {"72o": {"opp": 10, "rfi": 8}, "AA": {"opp": 5, "rfi": 5}, "A5s": {"opp": 6, "rfi": 0},
            "K2o": {"opp": 1, "rfi": 1}}
    r = compare_rfi("rfi_utg", hero)
    assert [i["hand"] for i in r["too_loose"]] == ["72o"]  # K2o : échantillon trop petit
    assert [i["hand"] for i in r["too_tight"]] == ["A5s"]


@pytest.fixture
def app(tmp_path):
    db = Database(tmp_path / "f.db")
    db.add_hands(iter_hands((FIXTURES / "winamax_reelles.txt").read_text(encoding="utf-8")))
    db.close()
    return AnalysisApp(tmp_path / "f.db", dict(DEFAULT_CONFIG))


def test_gto_routes(app):
    _, spots = app.handle("GET", "/api/gto/spots", {}, None)
    assert {s["group"] for s in spots["spots"]} == {"Ouvrir", "Défendre", "Face au 3-bet"}
    _, g = app.handle("GET", "/api/gto/spot", {"id": "rfi_hj", "format": "5"}, None)
    assert g["hero"]["position"] == "UTG" and g["hero"]["format"] == 5
    _, g = app.handle("GET", "/api/gto/spot", {"id": "bb_vs_btn"}, None)
    assert "hero" not in g and g["percent"]["call"] > g["percent"]["3bet"]
    _, p = app.handle("GET", "/api/gto/postflop", {"board": "8h7d6c"}, None)
    assert p["texture"]["kind"] == "bas connecté"


def test_study_blocked_while_table_open(tmp_path):
    app = AnalysisApp(tmp_path / "f.db", dict(DEFAULT_CONFIG), table_open=lambda: True)
    for path, q in (("/api/gto/spots", {}), ("/api/gto/spot", {"id": "rfi_utg"}), ("/api/gto/postflop", {"board": "AhKd2c"})):
        with pytest.raises(ApiError) as err:
            app.handle("GET", path, q, None)
        assert err.value.status == 423
