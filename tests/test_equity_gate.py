import pytest

from fleur.config import DEFAULT_CONFIG
from fleur.web.server import AnalysisApp, ApiError


def app_with(table_open: bool, tmp_path) -> AnalysisApp:
    return AnalysisApp(tmp_path / "fleur.db", dict(DEFAULT_CONFIG), table_open=lambda: table_open)


def test_equity_blocked_while_a_table_is_open(tmp_path):
    app = app_with(True, tmp_path)
    with pytest.raises(ApiError) as err:
        app.handle("POST", "/api/equity", {}, {"hands": ["Ah As", "Kd Kc"], "board": ""})
    assert err.value.status == 423 and "table Winamax est ouverte" in str(err.value)


def test_equity_available_when_no_table(tmp_path):
    app = app_with(False, tmp_path)
    kind, r = app.handle("POST", "/api/equity", {}, {"hands": ["AhAs", "Kd Kc"], "board": "2c 7d 9s"})
    assert kind == "json" and r["method"] == "exact"
    assert r["players"][0]["equity"] == pytest.approx(0.916, abs=0.002)
    # main vide = aléatoire -> simulation
    kind, r = app.handle("POST", "/api/equity", {}, {"hands": ["Ah Kh", ""], "board": ""})
    assert r["method"] == "simulation" and 0.6 < r["players"][0]["equity"] < 0.73


def test_equity_rejects_bad_cards(tmp_path):
    app = app_with(False, tmp_path)
    with pytest.raises(ApiError) as err:
        app.handle("POST", "/api/equity", {}, {"hands": ["Ah Ah", "Kd Kc"]})
    assert err.value.status == 400


def test_table_open_detection(monkeypatch):
    from fleur.hud import win32
    W = win32.WindowInfo if hasattr(win32, "WindowInfo") else None
    monkeypatch.setattr(win32, "IS_WINDOWS", True)
    monkeypatch.setattr(win32, "list_windows", lambda: [W(1, "Winamax")] if W else [])
    assert win32.winamax_table_open() is False  # le lobby seul ne bloque pas
    monkeypatch.setattr(win32, "list_windows", lambda: [W(1, "Winamax"), W(2, "Winamax Aalen 17")])
    assert win32.winamax_table_open() is True
