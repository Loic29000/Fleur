from datetime import date

import pytest
from conftest import FIXTURES

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database
from fleur.parser import iter_hands
from fleur.web.server import AnalysisApp, ApiError


@pytest.fixture
def app(tmp_path):
    db = Database(tmp_path / "fleur.db")
    for name in ("cash_6max.txt", "winamax_reelles.txt"):
        db.add_hands(iter_hands((FIXTURES / name).read_text(encoding="utf-8")))
    db.close()
    return AnalysisApp(tmp_path / "fleur.db", dict(DEFAULT_CONFIG))


def test_period_and_weekly_totals(app):
    db = app.db()
    assert db.period_totals("Hero")["hands"] == 11
    # mains réelles : février 2025 et juin 2026 ; mains fictives : novembre 2026
    assert db.period_totals("Hero", "2025-01-01", "2026-01-01")["hands"] == 6
    assert db.period_totals("Hero", "2026-11-01", None)["hands"] == 3
    assert db.period_totals("Hero", position="BB")["hands"] >= 1
    weeks = db.weekly_totals("Hero")
    assert sum(t["hands"] for _, t in weeks) == 11
    assert [w for w, _ in weeks] == sorted(w for w, _ in weeks)
    assert all(date.fromisoformat(w).weekday() == 0 for w, _ in weeks)  # semaines du lundi


def test_goals_flow(app):
    app.handle("POST", "/api/goals/add", {}, {"stat": "vpip", "low": "20", "high": "28"})
    app.handle("POST", "/api/goals/add", {}, {"stat": "vpip", "low": 22, "high": 28})  # remplace
    _, d = app.handle("GET", "/api/goals", {}, None)
    assert len(d["goals"]) == 1 and d["goals"][0]["low"] == 22
    g = d["goals"][0]
    assert g["label"] == "VPIP" and g["series"]
    assert g["status"] in ("atteint", "trop bas", "trop élevé", "pas assez de mains")
    assert any(s["key"] == "fvb_r" for s in d["stats"])
    with pytest.raises(ApiError):
        app.handle("POST", "/api/goals/add", {}, {"stat": "vpip"})
    with pytest.raises(ApiError):
        app.handle("POST", "/api/goals/add", {}, {"stat": "vpip", "low": 30, "high": 20})
    app.handle("POST", "/api/goals/delete", {}, {"id": g["id"]})
    assert app.handle("GET", "/api/goals", {}, None)[1]["goals"] == []


def test_goal_status_logic():
    from fleur.progress import _status
    assert _status(None, 1, 2) == "pas assez de mains"
    assert _status(10, 20, 30) == "trop bas" and _status(40, 20, 30) == "trop élevé"
    assert _status(25, 20, 30) == "atteint" and _status(25, None, 30) == "atteint"


def test_compare_periods(app):
    _, d = app.handle("GET", "/api/compare", {"a_start": "2025-01-01", "a_end": "2026-01-01",
                                              "b_start": "2026-01-01", "b_end": ""}, None)
    assert d["a"]["hands"] == 6 and d["b"]["hands"] == 5
    vpip = next(r for r in d["rows"] if r["key"] == "vpip")
    assert vpip["a_sample"] == 6 and vpip["b_sample"] == 5 and vpip["delta"] is not None
