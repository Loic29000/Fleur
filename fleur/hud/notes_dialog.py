"""Petite fenêtre d'édition de l'étiquette et de la note d'un joueur."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit,
    QPlainTextEdit, QPushButton, QWidget,
)

from fleur.db import PlayerNote

PERSO = "perso"
DEFAULT_PERSO_COLOR = "#7ddc6f"


def tag_choices(cfg: dict) -> list[tuple[str | None, str, str | None]]:
    """(clé, texte, couleur) des étiquettes proposées, « aucune » en premier."""
    out: list[tuple[str | None, str, str | None]] = [(None, "Aucune", None)]
    for key, (label, color) in cfg.get("player_tags", {}).items():
        out.append((key, label, color))
    out.append((PERSO, "Perso…", None))
    return out


def apply_tag(note: PlayerNote, key: str | None, cfg: dict) -> PlayerNote:
    """Pose l'étiquette prédéfinie `key` (ou l'enlève si None)."""
    if key is None:
        note.tag = note.label = note.color = None
        return note
    label, color = cfg.get("player_tags", {}).get(key, (key, DEFAULT_PERSO_COLOR))
    note.tag, note.label, note.color = key, label, color
    return note


class NoteDialog(QDialog):
    def __init__(self, note: PlayerNote, cfg: dict, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(f"Fleur — {note.player}")
        self.note = PlayerNote(note.player, note.tag, note.label, note.color, note.note)
        self.cfg = cfg
        self._color = note.color or DEFAULT_PERSO_COLOR

        form = QFormLayout(self)
        self.combo = QComboBox(self)
        self.choices = tag_choices(cfg)
        for key, label, color in self.choices:
            self.combo.addItem(f"● {label}" if color else label, key)
            if color:
                self.combo.setItemData(self.combo.count() - 1, QColor(color), Qt.ItemDataRole.ForegroundRole)
        keys = [c[0] for c in self.choices]
        self.combo.setCurrentIndex(keys.index(note.tag) if note.tag in keys else 0)
        form.addRow("Étiquette", self.combo)

        row = QHBoxLayout()
        self.label_edit = QLineEdit(note.label if note.tag == PERSO else "", self)
        self.label_edit.setPlaceholderText("texte de l'étiquette perso")
        self.color_btn = QPushButton("Couleur", self)
        self.color_btn.clicked.connect(self.pick_color)
        row.addWidget(self.label_edit)
        row.addWidget(self.color_btn)
        self.perso_row = QWidget(self)
        self.perso_row.setLayout(row)
        form.addRow("Perso", self.perso_row)

        self.text = QPlainTextEdit(note.note, self)
        self.text.setPlaceholderText("Note libre sur ce joueur")
        self.text.setMinimumSize(320, 120)
        form.addRow("Note", self.text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
                                   parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.combo.currentIndexChanged.connect(self._update_perso)
        self._update_perso()

    def _update_perso(self) -> None:
        perso = self.combo.currentData() == PERSO
        self.perso_row.setEnabled(perso)
        self.color_btn.setStyleSheet(f"background:{self._color}; color:#111;" if perso else "")

    def pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, "Couleur de l'étiquette")
        if color.isValid():
            self._color = color.name()
            self._update_perso()

    def result_note(self) -> PlayerNote:
        key = self.combo.currentData()
        note = self.note
        if key == PERSO:
            note.tag, note.label, note.color = PERSO, self.label_edit.text().strip() or "Perso", self._color
        else:
            apply_tag(note, key, self.cfg)
        note.note = self.text.toPlainText().strip()
        return note
