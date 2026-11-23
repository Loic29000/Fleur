import json

import pytest
from PySide6.QtWidgets import QApplication

from fleur.config import DEFAULT_CONFIG
from fleur.stats import compute_all
from fleur.web.routes import validate_settings


def test_validate_settings_cleans_input():
    out = validate_settings({
        "hud_lines": [["vpip", "inconnue", "pfr"], [], ["3bet"]],
        "popup_stats": ["vpip", "bidon", "fvb_r"],
        "colors": {"vpip": [[25, "#7ddc6f"], [15, "#4fa3ff"], ["x", "#000000"], [5, "rouge"]], "bidon": [[1, "#000000"]]},
        "font_size": "40", "opacity": "0.1", "hud_theme": "clair", "show_hero": 1, "min_hands_for_colors": "12",
    })
    assert out["hud_lines"] == [["vpip", "pfr"], ["3bet"]]
    assert out["popup_stats"] == ["vpip", "fvb_r"]
    assert out["colors"] == {"vpip": [[15.0, "#4fa3ff"], [25.0, "#7ddc6f"]]}  # triées, invalides retirées
    assert out["font_size"] == 20 and out["opacity"] == 0.3 and out["show_hero"] is True
    assert out["min_hands_for_colors"] == 12
    with pytest.raises(ValueError):
        validate_settings({"database": "x"})  # réglage non modifiable depuis la page
    with pytest.raises(ValueError):
        validate_settings({"hud_theme": "fluo"})


def test_settings_route_writes_config(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from fleur.config import config_path, load_config
    from fleur.web.server import AnalysisApp
    app = AnalysisApp(tmp_path / "f.db", dict(DEFAULT_CONFIG))
    _, d = app.handle("GET", "/api/settings", {}, None)
    assert d["settings"]["hud_lines"] == DEFAULT_CONFIG["hud_lines"] and any(s["key"] == "vpip" for s in d["stats"])
    app.handle("POST", "/api/settings", {}, {"hud_lines": [["vpip", "pfr"]], "ui_theme": "clair"})
    saved = json.loads(config_path().read_text(encoding="utf-8"))
    assert saved["hud_lines"] == [["vpip", "pfr"]] and load_config()["ui_theme"] == "clair"
    _, meta = app.handle("GET", "/api/meta", {}, None)
    assert meta["ui_theme"] == "clair"


def test_light_theme_colors():
    import copy
    from fleur.hud.overlay import color_for, panel_style, render_lines
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    sv = compute_all({"hands": 100, "vpip": 50})["vpip"]
    assert color_for("vpip", sv, 100, cfg) == "#ff6b6b"
    cfg["hud_theme"] = "clair"
    assert color_for("vpip", sv, 100, cfg) == "#d03030" and "#f4f4f4" in panel_style(cfg)
    assert "#555555" in render_lines("X", {"hands": 1}, cfg)


def test_hud_reloads_when_config_file_changes(tmp_path, monkeypatch):
    import os
    import time
    monkeypatch.setenv("APPDATA", str(tmp_path))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication.instance() or QApplication([])
    from fleur.config import load_config, save_config
    from fleur.db import Database
    from fleur.hud.overlay import HudManager
    from fleur.watcher import HistoryWatcher
    cfg = load_config()
    db = Database(":memory:")
    manager = HudManager(db, HistoryWatcher(db, []), cfg, tmp_path / "layouts.json")
    time.sleep(0.05)
    changed = load_config()
    changed["font_size"] = 14
    save_config(changed)
    os.utime(tmp_path / "Fleur" / "config.json", (time.time() + 5, time.time() + 5))
    manager.check_config_file()
    assert manager.cfg["font_size"] == 14
