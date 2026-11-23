"""Fenêtre Windows de l'application d'analyse (Qt WebEngine).

Elle affiche l'application locale (tableau de bord, revue de mains, ranges...)
dans une vraie fenêtre, sans navigateur. Lancée seule (FleurAnalyse.exe), elle
importe aussi les nouvelles mains en continu pour que tout se mette à jour.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar

from fleur.web.server import AnalysisServer

log = logging.getLogger("fleur")

try:  # Qt WebEngine est fourni par PySide6-Addons
    from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except Exception:  # pragma: no cover - dépend de l'installation
    HAS_WEBENGINE = False


def downloads_dir() -> Path:
    path = Path.home() / "Downloads"
    return path if path.is_dir() else Path.home()


class AnalysisWindow(QMainWindow):
    def __init__(self, server: AnalysisServer, tab: str = "", hide_on_close: bool = False):
        super().__init__()
        from fleur.hud.tray import app_icon
        self.server = server
        # Dans le programme complet, fermer la fenêtre la cache : le HUD continue
        # dans la barre des tâches (Quitter depuis le menu de l'icône).
        self.hide_on_close = hide_on_close
        self.setWindowTitle("Fleur")
        self.setWindowIcon(app_icon())
        self.resize(1360, 900)
        self.view = QWebEngineView(self)
        self.setCentralWidget(self.view)
        self.setStatusBar(QStatusBar(self))
        profile = self.view.page().profile()
        profile.downloadRequested.connect(self._download)
        self.view.setUrl(QUrl(server.url + (f"#{tab}" if tab else "")))

    def show_tab(self, tab: str) -> None:
        self.view.page().runJavaScript(f"typeof show === 'function' && show({tab!r})")

    def closeEvent(self, event):
        if self.hide_on_close:
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)

    def _download(self, request: "QWebEngineDownloadRequest") -> None:
        """Exports (texte, image) enregistrés dans le dossier Téléchargements."""
        folder = downloads_dir()
        request.setDownloadDirectory(str(folder))
        name = request.suggestedFileName() or request.downloadFileName()
        request.accept()
        self.statusBar().showMessage(f"Enregistré : {folder / name}", 8000)
        log.info("export enregistré : %s", folder / name)


class _Importer(threading.Thread):
    """Importe les nouvelles mains toutes les quelques secondes (fenêtre lancée seule)."""

    def __init__(self, db_path: str, dirs: list[Path], cfg: dict, interval: float = 5.0):
        super().__init__(name="fleur-import", daemon=True)
        self.db_path, self.dirs, self.cfg, self.interval = db_path, dirs, cfg, interval
        self.stop_event = threading.Event()

    def run(self) -> None:
        from fleur import diagnostics
        from fleur.db import Database
        from fleur.watcher import HistoryWatcher
        db = Database(self.db_path)
        watcher = HistoryWatcher(db, self.dirs, diagnostics.get(),
                                 include_tournaments=self.cfg.get("include_tournaments", False),
                                 include_play_money=self.cfg.get("include_play_money", False))
        rounds = 0
        while not self.stop_event.is_set():
            rounds += 1
            if rounds % 120 == 0:  # toutes les 10 minutes environ
                db.checkpoint()
            try:
                n = len(watcher.poll())
                if n:
                    log.info("analyse : %d nouvelle(s) main(s) importée(s)", n)
            except Exception:
                log.exception("import impossible")
            self.stop_event.wait(self.interval)
        db.close()


def open_window(server: AnalysisServer, tab: str = "", hide_on_close: bool = False) -> "AnalysisWindow | None":
    """Ouvre la fenêtre (ou le navigateur si Qt WebEngine manque)."""
    if not HAS_WEBENGINE:
        server.open(tab)
        return None
    window = AnalysisWindow(server, tab, hide_on_close)
    window.show()
    window.raise_()
    window.activateWindow()
    return window


def run_analysis_app(db_path: str, cfg: dict, history_dirs: list[Path], table_open=None, tab: str = "") -> int:
    """Application autonome : serveur local + fenêtre + import continu des mains."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Fleur analyse")
    server = AnalysisServer(db_path, cfg, table_open=table_open).start()
    importer = None
    if history_dirs:
        importer = _Importer(str(db_path), history_dirs, cfg)
        importer.start()
    window = open_window(server, tab)
    if window is None:  # navigateur : on garde le serveur jusqu'à Ctrl+C
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        code = 0
    else:
        code = app.exec()
    if importer:
        importer.stop_event.set()
    server.stop()
    return code
