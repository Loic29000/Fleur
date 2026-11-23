import copy

import pytest
from conftest import FIXTURES

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database
from fleur.parser import iter_hands


@pytest.fixture(scope="module")
def db():
    db = Database(":memory:")
    for name in ("cash_6max.txt", "winamax_reelles.txt"):
        db.add_hands(iter_hands((FIXTURES / name).read_text(encoding="utf-8")))
    # une copie tête-à-tête d'une main 5-max, pour tester le filtre HU
    raw = (FIXTURES / "winamax_reelles.txt").read_text(encoding="utf-8").split("\n\n\n")[0]
    hu = raw.replace("#20625144-874", "#99999999-874").replace("5-max", "2-max")
    db.add_hands(iter_hands(hu))
    return db


def hands(db, player, **kw):
    return db.totals([player], **kw)[player]["hands"]


def test_no_filter_counts_everything(db):
    # Hero : 3 mains 6-max fictives + 8 réelles (dont 2 ESCAPE 6-max) + 1 copie HU
    assert hands(db, "Hero") == 12


def test_same_format(db):
    assert hands(db, "Hero", max_seats=6, seats_mode="same") == 5
    assert hands(db, "Hero", max_seats=5, seats_mode="same") == 6
    assert hands(db, "Hero", max_seats=2, seats_mode="same") == 1


def test_heads_up_apart(db):
    assert hands(db, "Hero", max_seats=2, seats_mode="hu_apart") == 1
    assert hands(db, "Hero", max_seats=6, seats_mode="hu_apart") == 11


def test_same_stakes(db):
    assert hands(db, "Hero", bb=0.05, stakes_mode="same") == 2
    assert hands(db, "Hero", bb=0.02, stakes_mode="same") == 10
    assert hands(db, "Hero", max_seats=5, bb=0.02, seats_mode="same", stakes_mode="same") == 4


def test_unknown_player_and_filter_args(db):
    from fleur.hud.overlay import stats_filter_args
    assert db.totals(["Personne"], max_seats=6, seats_mode="same")["Personne"]["hands"] == 0
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    hand = next(iter_hands((FIXTURES / "cash_6max.txt").read_text(encoding="utf-8")))
    assert stats_filter_args(cfg, hand) == {"max_seats": 6, "bb": 0.02, "seats_mode": "all", "stakes_mode": "all"}
    cfg["stats_filter"] = {"seats": "same", "stakes": "same"}
    assert stats_filter_args(cfg, hand)["seats_mode"] == "same"


def test_tray_filter_menu_saves_config(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("APPDATA", str(tmp_path))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from fleur.config import load_config
    from fleur.hud.overlay import HudManager
    from fleur.hud.tray import Tray
    from fleur.watcher import HistoryWatcher
    db = Database(":memory:")
    cfg = load_config()
    manager = HudManager(db, HistoryWatcher(db, []), cfg, tmp_path / "layouts.json")
    tray = Tray(app, manager, [])
    assert tray.filter_actions[("seats", "all")].isChecked()
    tray.filter_actions[("stakes", "same")].trigger()
    assert load_config()["stats_filter"] == {"seats": "all", "stakes": "same"}
    assert manager.cfg["stats_filter"]["stakes"] == "same"
    assert tray.filter_actions[("stakes", "same")].isChecked()
    tray.timer.stop()
    tray.icon.hide()
