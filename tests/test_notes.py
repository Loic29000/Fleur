import os

import pytest

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database, PlayerNote


def test_notes_crud():
    db = Database(":memory:")
    assert db.note("Alice") == PlayerNote("Alice")
    db.save_note(PlayerNote("Alice", "fish", "Fish", "#ff6b6b", "limpe tout"))
    db.save_note(PlayerNote("Bob", None, None, None, "  "))  # vide : rien enregistré
    notes = db.notes(["Alice", "Bob", "Carole"])
    assert list(notes) == ["Alice"]
    assert notes["Alice"].tag == "fish" and notes["Alice"].note == "limpe tout"
    db.save_note(PlayerNote("Alice", "reg", "Reg", "#4fa3ff", "limpe tout"))  # mise à jour
    assert db.note("Alice").label == "Reg"
    db.save_note(PlayerNote("Alice"))  # tout effacé : ligne supprimée
    assert db.notes(["Alice"]) == {}


def test_render_badge_and_lines():
    from fleur.hud.overlay import render_lines, render_popup
    cfg = DEFAULT_CONFIG
    plain = render_lines("Alice", {}, cfg)
    assert "●" not in plain and "✎" not in plain
    note = PlayerNote("Alice", "lag", "LAG", "#ffa94d", "3-bet <light>")
    text = render_lines("Alice", {}, cfg, note)
    assert "#ffa94d" in text and "● LAG" in text and "✎" in text
    popup = render_popup("Alice", {}, cfg, note)
    assert "3-bet &lt;light&gt;" in popup  # texte échappé


def test_apply_tag_uses_config_colors():
    from fleur.hud.notes_dialog import apply_tag, tag_choices
    note = apply_tag(PlayerNote("Alice", note="x"), "nit", DEFAULT_CONFIG)
    assert (note.tag, note.label, note.color) == ("nit", "Nit", "#9aa5b1")
    assert apply_tag(note, None, DEFAULT_CONFIG).tag is None and note.note == "x"
    keys = [k for k, _, _ in tag_choices(DEFAULT_CONFIG)]
    assert keys == [None, "fish", "reg", "nit", "lag", "maniaque", "perso"]


@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_note_dialog_perso(qapp):
    from fleur.hud.notes_dialog import NoteDialog
    dlg = NoteDialog(PlayerNote("Alice", "fish", "Fish", "#ff6b6b", "ancienne"), DEFAULT_CONFIG)
    assert dlg.combo.currentData() == "fish"
    dlg.combo.setCurrentIndex(dlg.combo.findData("perso"))
    dlg.label_edit.setText("Shove 10bb")
    dlg.text.setPlainText("  nouvelle note ")
    note = dlg.result_note()
    assert (note.tag, note.label, note.note) == ("perso", "Shove 10bb", "nouvelle note")
    assert note.color


def test_manager_save_note_refreshes_panels(qapp, tmp_path):
    import copy
    from conftest import FIXTURES
    from fleur.hud.overlay import HudManager, TableHud
    from fleur.parser import iter_hands
    from fleur.watcher import HistoryWatcher

    db = Database(":memory:")
    hands = list(iter_hands((FIXTURES / "cash_6max.txt").read_text(encoding="utf-8")))
    db.add_hands(hands)
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    manager = HudManager(db, HistoryWatcher(db, []), cfg, tmp_path / "layouts.json")
    hud = TableHud(manager, hands[0].table, 6)
    manager.tables[hud.table] = hud
    hud.update(hands[0])
    bob = next(p for p in hud.panels.values() if p.player == "Bob")
    manager.save_note(PlayerNote("Bob", "fish", "Fish", "#ff6b6b", "call trop"))
    assert "● Fish" in bob.label.text() and "✎" in bob.label.text()
    assert bob.toolTip() == "call trop"
    hud.close()
