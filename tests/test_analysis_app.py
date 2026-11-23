import time

import pytest
from conftest import FIXTURES

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database
from fleur.parser import iter_hands
from fleur.web.server import AnalysisApp


@pytest.fixture
def app(tmp_path):
    db = Database(tmp_path / "fleur.db")
    for name in ("cash_6max.txt", "winamax_reelles.txt"):
        db.add_hands(iter_hands((FIXTURES / name).read_text(encoding="utf-8")))
    db.close()
    return AnalysisApp(tmp_path / "fleur.db", dict(DEFAULT_CONFIG))


def test_dashboard_payload(app):
    _, d = app.handle("GET", "/api/dashboard", {}, None)
    assert d["hero"] == "Hero" and d["kpis"]["hands"] == 11
    assert d["kpis"]["net"] == pytest.approx(d["curves"]["money"]["total"][-1], abs=0.01)
    keys = {s["key"] for s in d["stats"]}
    assert {"vpip", "pfr", "3bet", "fvb_r", "overbet", "bb100"} <= keys
    assert {r["name"] for r in d["by_format"]} == {"6-max", "5-max"}
    assert sum(r["hands"] for r in d["by_position"]) == 11
    assert d["kpis"]["last_session"]["hands"] >= 1


def test_meta_reports_last_hand(app):
    _, m = app.handle("GET", "/api/meta", {}, None)
    assert m["last_hand"].startswith("2026-")


def test_importer_thread_adds_new_hands(tmp_path):
    from fleur.gui.analysis_window import _Importer
    hist = tmp_path / "history"
    hist.mkdir()
    (hist / "20260101_Table_real_holdem_no-limit.txt").write_text(
        (FIXTURES / "winamax_reelles.txt").read_text(encoding="utf-8"), encoding="utf-8")
    db_path = tmp_path / "import.db"
    Database(db_path).close()
    imp = _Importer(str(db_path), [hist], dict(DEFAULT_CONFIG), interval=0.2)
    imp.start()
    deadline = time.time() + 15
    count = 0
    while time.time() < deadline:
        db = Database(db_path)
        count = db.hand_count()
        db.close()
        if count == 8:
            break
        time.sleep(0.3)
    imp.stop_event.set()
    imp.join(5)
    assert count == 8
