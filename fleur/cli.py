"""Ligne de commande : python -m fleur [hud|import|stats|analyse|dashboard|fuites|sauvegarde|windows|config|diagnostic]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fleur.config import app_dir, config_path, database_path, load_config
from fleur import diagnostics
from fleur.db import Database
from fleur.stats import STAT_BY_KEY, STAT_DEFS, compute_all
from fleur.watcher import HistoryWatcher, find_history_dirs


def _history_dirs(cfg: dict, override: list[str] | None) -> list[Path]:
    if override:
        return [Path(p) for p in override]
    if cfg.get("history_dirs"):
        return [Path(p) for p in cfg["history_dirs"]]
    return find_history_dirs()


def make_watcher(db: Database, dirs: list[Path], diag, cfg: dict) -> HistoryWatcher:
    return HistoryWatcher(db, dirs, diag,
                          include_tournaments=cfg.get("include_tournaments", False),
                          include_play_money=cfg.get("include_play_money", False))


def cmd_import(db: Database, dirs: list[Path], cfg: dict | None = None) -> int:
    if not dirs:
        print("Aucun dossier d'historique trouvé. Indiquez-le avec --history "
              "ou dans la config (history_dirs).")
        return 1
    diag = diagnostics.get()
    watcher = make_watcher(db, dirs, diag, cfg or {})
    files = watcher.files()
    print(f"Import de {len(files)} fichier(s) depuis : " + ", ".join(map(str, dirs)))
    total = 0
    for i, path in enumerate(files, 1):
        n = len(watcher.read_file(path))
        total += n
        if n:
            print(f"  [{i}/{len(files)}] {path.name} : {n} main(s)")
    print(f"{total} nouvelle(s) main(s) importée(s). Total en base : {db.hand_count()}")
    if diag.problem_count or diag.unknown_patterns:
        print(f"Attention : {diag.parse_errors} main(s) illisible(s), {diag.inconsistent} main(s) incohérente(s), "
              f"{len(diag.unknown_patterns)} type(s) de ligne non reconnu(s).\n"
              f"Détails dans {diag.dir} — `python -m fleur diagnostic` crée un rapport à m'envoyer.")
    return 0


def cmd_stats(db: Database, players: list[str], list_keys: bool,
              seats: int | None = None, bb: float | None = None) -> int:
    if list_keys:
        for s in STAT_DEFS:
            print(f"{s.key:8} {s.label:7} {s.description}")
        return 0
    if not players:
        print("Joueurs les plus rencontrés :")
        for name, n in db.top_players(25):
            print(f"  {name:24} {n} mains")
        return 0
    filters = {"max_seats": seats, "bb": bb, "seats_mode": "same" if seats else "all",
               "stakes_mode": "same" if bb else "all"}
    for name, totals in db.totals(players, **filters).items():
        stats = compute_all(totals)
        print(f"\n== {name} ==")
        for key, sv in stats.items():
            sd = STAT_BY_KEY[key]
            sample = "" if sd.kind in ("count", "money", "bb100") else f"  ({int(sv.num)}/{int(sv.den)})"
            print(f"  {sd.label:7} {sv.format(sd.kind):>8}{sample}")
    return 0


def cmd_dashboard(db: Database, hero: str | None, open_it: bool) -> int:
    from fleur.dashboard import write_dashboard
    out = write_dashboard(db, app_dir() / "tableau_de_bord.html", hero)
    print(f"Tableau de bord : {out}")
    if open_it:
        import webbrowser
        webbrowser.open(out.as_uri())
    return 0


def cmd_leaks(db: Database, hero: str | None) -> int:
    from fleur.dashboard import main_hero
    from fleur.leaks import find_leaks
    hero = hero or main_hero(db)
    if not hero:
        print("Aucune main du héros en base.")
        return 1
    leaks = find_leaks(db.totals([hero])[hero], db.position_totals(hero))
    print(f"Fuites possibles pour {hero} (fourchettes indicatives cash game 6-max) :")
    for leak in leaks:
        print(f"  [{leak.severity:8}] {leak.message}")
    if not leaks:
        print("  aucune stat hors des fourchettes de référence")
    return 0


def cmd_analysis(db: Database, cfg: dict, dirs: list[Path], browser: bool = False, no_import: bool = False,
                 tab: str = "") -> int:
    from fleur.hud import win32
    if not browser:
        # Fenêtre Windows dédiée, qui importe aussi les nouvelles mains
        from fleur.gui.analysis_window import run_analysis_app
        path = db.path
        db.close()
        return run_analysis_app(path, cfg, [] if no_import else dirs, table_open=win32.winamax_table_open, tab=tab)
    from fleur.web.server import AnalysisServer
    server = AnalysisServer(db.path, cfg, table_open=win32.winamax_table_open).start()
    if sys.stdout is not None:
        print(f"Application d'analyse : {server.url}")
        print("Ctrl+C pour arrêter.")
    server.open(tab)
    try:
        server.thread.join()
    except KeyboardInterrupt:
        server.stop()
    return 0


def cmd_backup(db: Database) -> int:
    from fleur.backup import backup_database
    print(f"Base sauvegardée : {backup_database(db)}")
    return 0


def cmd_windows() -> int:
    from fleur.hud import win32
    if not win32.IS_WINDOWS:
        print("Disponible uniquement sous Windows.")
        return 1
    for w in win32.list_windows():
        print(f"{w.hwnd:>10}  {w.title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fleur", description="HUD de poker pour Winamax")
    parser.add_argument("--history", action="append", help="dossier d'historiques (répétable)")
    parser.add_argument("--db", help="chemin de la base SQLite")
    sub = parser.add_subparsers(dest="command")
    hud = sub.add_parser("hud", help="lance le HUD (par défaut)")
    hud.add_argument("--no-import", action="store_true", help="ne pas importer l'historique existant au démarrage")
    sub.add_parser("import", help="importe tout l'historique dans la base")
    st = sub.add_parser("stats", help="affiche les stats d'un ou plusieurs joueurs")
    st.add_argument("players", nargs="*")
    st.add_argument("--list", action="store_true", help="liste les stats disponibles")
    st.add_argument("--seats", type=int, help="seulement les tables de N sièges max (ex. 6)")
    st.add_argument("--bb", type=float, help="seulement cette big blind (ex. 0.05)")
    sub.add_parser("windows", help="liste les fenêtres ouvertes (diagnostic)")
    dash = sub.add_parser("dashboard", help="tableau de bord du héros (page HTML locale)")
    dash.add_argument("--hero", help="pseudo du héros (par défaut : le plus fréquent)")
    dash.add_argument("--no-open", action="store_true", help="ne pas ouvrir le navigateur")
    an = sub.add_parser("analyse", help="application d'analyse : tableau de bord, revue de mains, ranges...")
    an.add_argument("--navigateur", action="store_true", help="ouvrir dans le navigateur au lieu d'une fenêtre")
    an.add_argument("--sans-import", action="store_true", help="ne pas importer les mains (le HUD s'en charge)")
    an.add_argument("--onglet", default="", help="onglet à ouvrir (bord, mains, reglages...)")
    sub.add_parser("sauvegarde", help=r"sauvegarde la base dans Documents\Fleur\sauvegardes")
    lk = sub.add_parser("fuites", help="liste les fuites possibles du héros")
    lk.add_argument("--hero", help="pseudo du héros (par défaut : le plus fréquent)")
    sub.add_parser("config", help="affiche l'emplacement de la configuration")
    sub.add_parser("diagnostic", help="crée un rapport de diagnostic (zip) sur le bureau")
    args = parser.parse_args(argv)

    cfg = load_config()
    command = args.command or "hud"
    diagnostics.setup_logging(console=command == "hud")
    diagnostics.log.info("démarrage : commande %s", command)
    if command == "windows":
        return cmd_windows()
    if command == "config":
        print(f"Configuration : {config_path()}")
        print(f"Positions HUD : {app_dir() / 'layouts.json'}")
        print(f"Base          : {database_path(cfg)}")
        print("Historiques   : " + (", ".join(map(str, _history_dirs(cfg, args.history))) or "non trouvés"))
        return 0

    splash = None
    if sys.stdout is None:
        # Programme sans console (FleurAnalyse.exe, pythonw) : petite fenêtre
        # pour la mise à jour de la base, qui peut prendre une minute.
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication, QLabel
            _app = QApplication.instance() or QApplication([])
            splash = QLabel("Fleur : ouverture de la base…")
            splash.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
            splash.setStyleSheet("background:#1b1e23; color:#e8e8e8; padding:18px 26px; font-size:14px;"
                                 "border:1px solid #ff6fa8;")
        except Exception:
            splash = None

    def progress(text: str) -> None:
        diagnostics.log.info(text)
        if sys.stdout is not None:
            print(text, flush=True)
        elif splash is not None:
            from PySide6.QtWidgets import QApplication
            splash.setText(f"Fleur : {text}\n(une seule fois, après une mise à jour)")
            splash.adjustSize()
            splash.show()
            QApplication.processEvents()

    db = Database(args.db or database_path(cfg), on_progress=progress)
    if splash is not None:
        splash.close()
    dirs = _history_dirs(cfg, args.history)
    try:
        if command == "diagnostic":
            out = diagnostics.make_report(diagnostics.default_report_dir(), {
                "historiques": [str(d) for d in dirs],
                "mains_en_base": db.hand_count(),
            })
            print(f"Rapport créé : {out}")
            return 0
        if command == "import":
            return cmd_import(db, dirs, cfg)
        if command == "dashboard":
            return cmd_dashboard(db, args.hero, not args.no_open)
        if command == "analyse":
            return cmd_analysis(db, cfg, dirs, args.navigateur, args.sans_import, args.onglet)
        if command == "sauvegarde":
            return cmd_backup(db)
        if command == "fuites":
            return cmd_leaks(db, args.hero)
        if command == "stats":
            return cmd_stats(db, args.players, args.list, args.seats, args.bb)
        # hud
        if not dirs:
            message = ("Aucun dossier d'historique Winamax trouvé.\n"
                       "Vérifiez que l'enregistrement des historiques est activé dans le client Winamax,\n"
                       "puis indiquez le dossier avec --history \"C:\\...\\history\" "
                       "ou dans history_dirs de la configuration.")
            diagnostics.log.error(message.replace("\n", " "))
            if sys.stdout is None:  # lancé sans console (pythonw / exe fenêtré)
                from PySide6.QtWidgets import QApplication, QMessageBox
                _app = QApplication.instance() or QApplication([])
                QMessageBox.warning(None, "Fleur", message)
            else:
                print(message)
            return 1
        if not getattr(args, "no_import", False):
            cmd_import(db, dirs, cfg)
        from fleur.hud.overlay import run_hud
        return run_hud(db, make_watcher(db, dirs, diagnostics.get(), cfg), cfg,
                       app_dir() / "layouts.json", dirs)
    finally:
        db.close()
