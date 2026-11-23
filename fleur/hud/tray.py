"""Icône et menu dans la barre des tâches (zone de notification)."""

from __future__ import annotations

import logging
import math
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from fleur import __version__
from fleur.config import app_dir, load_config, save_config

SEATS_CHOICES = [("all", "Tous les formats de table"), ("same", "Même format que la table"),
                 ("hu_apart", "Tête-à-tête à part")]
STAKES_CHOICES = [("all", "Toutes les limites"), ("same", "Même limite que la table")]

log = logging.getLogger("fleur")


def flower_icon(paused: bool = False) -> QIcon:
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    petal = QColor("#8a8a8a") if paused else QColor("#ff6fa8")
    p.setBrush(petal)
    c = size / 2
    for i in range(5):
        a = 2 * math.pi * i / 5 - math.pi / 2
        p.drawEllipse(QPointF(c + 15 * math.cos(a), c + 15 * math.sin(a)), 12, 12)
    p.setBrush(QColor("#ffd84a"))
    p.drawEllipse(QPointF(c, c), 10, 10)
    p.end()
    return QIcon(pm)


def open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class Tray:
    def __init__(self, app: QApplication, manager, history_dirs: list[Path]):
        self.app = app
        self.manager = manager
        self.history_dirs = history_dirs
        self._warned_problems = 0
        self._warned_windows: set[str] = set()

        self.icon = QSystemTrayIcon(flower_icon(), app)
        self.menu = QMenu()
        self.status = QAction("", self.menu)
        self.status.setEnabled(False)
        self.menu.addAction(self.status)
        self.menu.addSeparator()

        self.toggle = QAction("Masquer le HUD", self.menu)
        self.toggle.triggered.connect(self.toggle_hidden)
        self.menu.addAction(self.toggle)
        self._add("Recharger la configuration", self.reload_config)
        self._add("Réinitialiser la position des panneaux", self.manager.reset_layouts)
        self._build_filter_menu()
        self.menu.addSeparator()
        self._add("Ouvrir le dossier de configuration", lambda: open_folder(app_dir()))
        self._add("Ouvrir le dossier des historiques", self.open_history)
        self._add("Créer un rapport de diagnostic", self.create_report)
        self.menu.addSeparator()
        self._add("Quitter Fleur", self.quit)

        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)
        self.menu.aboutToShow.connect(self.refresh_status)
        self.refresh_status()

        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        if self.available:
            self.icon.show()
            self.notify("Fleur est lancé", "Ouvrez une table Winamax : le HUD apparaîtra après la première main.")
        else:
            log.info("zone de notification indisponible : pas d'icône")

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_problems)
        self.timer.start(5000)

    def _build_filter_menu(self) -> None:
        sub = self.menu.addMenu("Filtre des stats")
        self.filter_actions: dict[tuple[str, str], QAction] = {}
        for field, choices in (("seats", SEATS_CHOICES), ("stakes", STAKES_CHOICES)):
            group = QActionGroup(sub)
            group.setExclusive(True)
            for value, label in choices:
                action = QAction(label, sub, checkable=True)
                action.triggered.connect(lambda _=False, f=field, v=value: self.set_filter(f, v))
                group.addAction(action)
                sub.addAction(action)
                self.filter_actions[(field, value)] = action
            sub.addSeparator()
        self._sync_filter_menu()

    def _sync_filter_menu(self) -> None:
        filt = self.manager.cfg.get("stats_filter") or {}
        for (field, value), action in self.filter_actions.items():
            action.setChecked(filt.get(field, "all") == value)

    def set_filter(self, field: str, value: str) -> None:
        """Change un filtre, l'enregistre dans la config et rafraîchit les panneaux."""
        cfg = load_config()
        filt = dict(cfg.get("stats_filter") or {})
        filt[field] = value
        cfg["stats_filter"] = filt
        try:
            save_config(cfg)
        except OSError as exc:
            log.warning("config non enregistrée : %s", exc)
        self.manager.cfg["stats_filter"] = filt
        self.manager.refresh_all()
        self._sync_filter_menu()
        log.info("filtre des stats : %s", filt)

    def _add(self, label: str, slot) -> QAction:
        action = QAction(label, self.menu)
        action.triggered.connect(slot)
        self.menu.addAction(action)
        return action

    def notify(self, title: str, message: str, warning: bool = False) -> None:
        if self.available:
            icon = QSystemTrayIcon.MessageIcon.Warning if warning else QSystemTrayIcon.MessageIcon.Information
            self.icon.showMessage(title, message, icon, 6000)

    # -- état ----------------------------------------------------------------
    def status_text(self) -> str:
        m = self.manager
        n_tables = len(m.tables)
        text = (f"Fleur {__version__} — {n_tables} table(s), "
                f"{m.session_hands} main(s) cette session")
        if m.hidden:
            text += " — HUD masqué"
        problems = m.diagnostics.problem_count
        if problems:
            text += f" — {problems} problème(s) de lecture"
        return text

    def refresh_status(self) -> None:
        text = self.status_text()
        self.status.setText(text)
        self.icon.setToolTip(text[:120])

    def check_problems(self) -> None:
        self.refresh_status()
        d = self.manager.diagnostics
        if d.problem_count > self._warned_problems:
            if self._warned_problems == 0:
                self.notify("Fleur : mains mal lues",
                            "Certaines mains n'ont pas été comprises. Clic droit sur l'icône → "
                            "« Créer un rapport de diagnostic » pour me l'envoyer.", warning=True)
            self._warned_problems = d.problem_count
        for table, hud in self.manager.tables.items():
            if hud.window_missing_since and table not in self._warned_windows:
                self._warned_windows.add(table)
                self.notify("Fleur : table introuvable",
                            f"Je ne trouve pas la fenêtre de la table « {table} ». "
                            "Le HUD reste flottant ; un rapport de diagnostic m'aidera à corriger.",
                            warning=True)

    # -- actions ---------------------------------------------------------------
    def toggle_hidden(self) -> None:
        hidden = not self.manager.hidden
        self.manager.set_hidden(hidden)
        self.toggle.setText("Afficher le HUD" if hidden else "Masquer le HUD")
        self.icon.setIcon(flower_icon(paused=hidden))
        self.refresh_status()

    def reload_config(self) -> None:
        self.manager.reload_config(load_config())
        self._sync_filter_menu()
        self.notify("Fleur", "Configuration rechargée.")

    def open_history(self) -> None:
        for d in self.history_dirs:
            if d.is_dir():
                open_folder(d)
                return
        self.notify("Fleur", "Aucun dossier d'historique trouvé.", warning=True)

    def create_report(self) -> None:
        from fleur.diagnostics import default_report_dir, make_report
        try:
            out = make_report(default_report_dir(), self.report_extra())
        except Exception as exc:
            log.exception("rapport de diagnostic impossible")
            self.notify("Fleur", f"Rapport impossible : {exc}", warning=True)
            return
        self.notify("Rapport de diagnostic créé", str(out))
        open_folder(out.parent)

    def report_extra(self) -> dict:
        m = self.manager
        return {
            "historiques": [str(d) for d in self.history_dirs],
            "mains_en_base": m.db.hand_count(),
            "mains_session": m.session_hands,
            "tables": {t: {"max": h.max_seats, "fenetre_trouvee": bool(h.hwnd)} for t, h in m.tables.items()},
            "mains_illisibles": m.diagnostics.parse_errors,
            "mains_incoherentes": m.diagnostics.inconsistent,
        }

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_hidden()

    def quit(self) -> None:
        log.info("arrêt demandé depuis le menu")
        self.icon.hide()
        self.app.quit()
