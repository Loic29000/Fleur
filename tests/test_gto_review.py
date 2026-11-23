import pytest
from conftest import FIXTURES

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database
from fleur.gto_review import build_reviews, review_hand, summary
from fleur.parser import iter_hands
from fleur.web.server import AnalysisApp, ApiError


@pytest.fixture(scope="module")
def hands():
    return {h.hand_id.split("-")[1]: h
            for name in ("cash_6max.txt", "winamax_reelles.txt")
            for h in iter_hands((FIXTURES / name).read_text(encoding="utf-8"))}


def verdicts(r):
    return [(d["spot"], d["action"], d["verdict"]) for d in r["decisions"]]


def test_preflop_verdicts(hands):
    # SB qui suit A5o face au vol : la référence 3-bet ou passe -> trop large
    r = review_hand(hands["1046"], "Hero")
    assert verdicts(r) == [("sb_vs_btn", "call", "trop large")] and r["status"] == "trop large"
    # BB qui défend KJo contre le bouton : conforme
    assert verdicts(review_hand(hands["858"], "Hero"))[0] == ("bb_vs_btn", "call", "conforme")
    # fold de 72o UTG : conforme ; situations non couvertes (3-bet devant soi) : rien
    assert verdicts(review_hand(hands["1001"], "Hero")) == [("rfi_utg", "fold", "conforme")]
    assert review_hand(hands["1002"], "Hero")["decisions"] == []


def test_cbet_review(hands):
    r = review_hand(hands["874"], "Hero")
    assert r["decisions"][0]["verdict"] == "conforme"  # 3-bet AKo depuis la SB
    cbet = r["decisions"][1]
    assert cbet["spot"] == "cbet" and cbet["texture"] == "haut sec" and cbet["action"] == "mise 50 %"
    assert cbet["verdict"] == "conforme"


def test_too_tight_open():
    text = (FIXTURES / "cash_6max.txt").read_text(encoding="utf-8").split("\n\n\n")[0]
    hand = next(iter_hands(text.replace("Dealt to Hero [7h 2d]", "Dealt to Hero [Ah Ad]")))
    r = review_hand(hand, "Hero")
    assert r["decisions"][0]["verdict"] == "trop serré" and r["decisions"][0]["reference"]["raise"] == 100


def test_summary_and_filters(tmp_path):
    db = Database(tmp_path / "f.db")
    for name in ("cash_6max.txt", "winamax_reelles.txt"):
        db.add_hands(iter_hands((FIXTURES / name).read_text(encoding="utf-8")))
    assert build_reviews(db, "Hero") == 11 and build_reviews(db, "Hero") == 0  # en cache
    s = summary(db, "Hero")
    assert s["totals"]["decisions"] >= 7 and s["totals"]["trop large"] == 1
    sb = next(x for x in s["spots"] if x["title"].startswith("SB face"))
    assert sb["top_deviations"][0] == {"hand": "A5o", "count": 1, "verdict": "trop large"}
    db.close()
    app = AnalysisApp(tmp_path / "f.db", dict(DEFAULT_CONFIG))
    _, h = app.handle("GET", "/api/hands", {"gto": "ecart"}, None)
    assert [x["hand_id"].split("-")[1] for x in h["items"]] == ["1046"] and h["items"][0]["gto"] == "trop large"
    _, all_ = app.handle("GET", "/api/hands", {}, None)
    assert any(x["gto"] == "conforme" for x in all_["items"])
    blocked = AnalysisApp(tmp_path / "f.db", dict(DEFAULT_CONFIG), table_open=lambda: True)
    _, during = blocked.handle("GET", "/api/hands", {}, None)
    assert all(x["gto"] is None for x in during["items"])  # aucun verdict pendant le jeu
    for path, q in (("/api/hands", {"gto": "ecart"}), ("/api/gto/review_summary", {})):
        with pytest.raises(ApiError):
            blocked.handle("GET", path, q, None)
