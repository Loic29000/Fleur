import json
import urllib.error
import urllib.request

import pytest
from conftest import FIXTURES

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database
from fleur.parser import iter_hands


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("web") / "fleur.db"
    db = Database(path)
    for name in ("cash_6max.txt", "winamax_reelles.txt"):
        db.add_hands(iter_hands((FIXTURES / name).read_text(encoding="utf-8")))
    db.close()
    return path


@pytest.fixture(scope="module")
def server(db_path):
    from fleur.web.server import AnalysisServer
    srv = AnalysisServer(db_path, dict(DEFAULT_CONFIG)).start()
    yield srv
    srv.stop()


def get(server, path, token=True, **params):
    from urllib.parse import urlencode
    base = server.url.split("?")[0].rstrip("/")
    if token:
        params["t"] = server.token
    with urllib.request.urlopen(f"{base}{path}?{urlencode(params)}", timeout=10) as r:
        body = r.read().decode("utf-8")
        return json.loads(body) if r.headers.get_content_type() == "application/json" else body


def post(server, path, data):
    base = server.url.split("?")[0].rstrip("/")
    req = urllib.request.Request(f"{base}{path}?t={server.token}", data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def test_page_and_token(server):
    assert "Fleur" in get(server, "/", token=False)
    with pytest.raises(urllib.error.HTTPError) as err:
        get(server, "/api/meta", token=False)
    assert err.value.code == 403
    assert server.url.startswith("http://127.0.0.1:")


def test_meta(server):
    meta = get(server, "/api/meta")
    assert meta["hero"] == "Hero" and meta["hands"] == 11 and 0.05 in meta["stakes"]


def test_hand_list_filters(server):
    all_ = get(server, "/api/hands")
    assert all_["total"] == 11
    lost = get(server, "/api/hands", result="perdue")
    assert lost["total"] >= 1 and all(h["net"] < 0 for h in lost["items"])
    big = get(server, "/api/hands", sort="pot", min_pot_bb=50)
    assert [h["hand_id"].split("-")[1] for h in big["items"]][:2] == ["48160", "962"]
    assert all(h["position"] == "BB" for h in get(server, "/api/hands", position="BB")["items"])
    assert get(server, "/api/hands", cards="AKo")["items"][0]["cards"] == "Ks Ac"


def test_replay(server):
    hand_id = next(h["hand_id"] for h in get(server, "/api/hands")["items"] if "-874-" in h["hand_id"])
    r = get(server, f"/api/hand/{hand_id}")
    texts = [s["text"] for s in r["steps"]]
    assert texts[0] == "Début de la main"
    assert "Hero relance à 0.24 € " not in texts and "Hero relance à 0.24 €" in texts
    assert "Joueur3 relance à 1.54 € (tapis)" in texts
    assert r["steps"][-1]["text"] == "Joueur3 gagne 3.82 €"
    # le pot juste avant la distribution = tout ce qui a été misé
    assert r["steps"][-2]["pot"] == pytest.approx(4.05)
    hero = next(p for p in r["players"] if p["hero"])
    assert hero["cards"] == ["Ks", "Ac"] and hero["net"] == pytest.approx(-2.0)


def test_text_export(server):
    hand_id = get(server, "/api/hands")["items"][0]["hand_id"]
    raw = get(server, f"/api/hand_text/{hand_id}")
    anon = get(server, f"/api/hand_text/{hand_id}", anon="1")
    assert raw.startswith("Winamax Poker") and "Heros" in anon and "Hero " not in anon


def test_ranges_and_sessions(server):
    g = get(server, "/api/ranges")
    assert g["labels"][0][0] == "AA" and g["cells"]["AKo"]["n"] == 1
    assert g["hands"] == 11
    s = get(server, "/api/sessions")
    assert s["summary"]["hands"] == 11 and s["summary"]["sessions"] >= 3
    assert sum(t["hands"] for t in s["by_table"]) == 11


def test_backup(server, tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    out = post(server, "/api/backup", {})
    assert out["path"].startswith(str(tmp_path)) and out["path"].endswith(".db")
    restored = Database(out["path"])
    assert restored.hand_count() == 11
    assert get(server, "/api/backups")["items"][0]["path"] == out["path"]


def test_hand_class_and_grid():
    from fleur.analysis import grid_labels, hand_class
    assert [hand_class(c) for c in ("Ah Kd", "Qs Qc", "9h Th", "2c Ad", None, "Ah Kd Qs Jc")] == \
        ["AKo", "QQ", "T9s", "A2o", None, None]
    labels = grid_labels()
    assert len(labels) == 13 and all(len(r) == 13 for r in labels)
    assert labels[0][1] == "AKs" and labels[1][0] == "AKo" and labels[12][12] == "22"
    assert len({c for r in labels for c in r}) == 169


def test_server_closes_connections_after_each_request(server):
    import gc
    import sqlite3
    for _ in range(20):
        get(server, "/api/meta")
    gc.collect()
    # la base peut être vidée de son journal : aucune connexion du serveur ne le retient
    conn = sqlite3.connect(server.app.db_path)
    busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    conn.close()
    assert busy == 0
