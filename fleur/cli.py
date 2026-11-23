"""Ligne de commande : python -m fleur [hud|import|stats|windows]."""

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


def cmd_stats(db: Database, players: list[str], list_keys: bool) -> int:
    if list_keys:
        for s in STAT_DEFS:
            print(f"{s.key:8} {s.label:7} {s.description}")
        return 0
    if not players:
        print("Joueurs les plus rencontrés :")
        for name, n in db.top_players(25):
            print(f"  {name:24} {n} mains")
        return 0
    for name, totals in db.totals(players).items():
        stats = compute_all(totals)
        print(f"\n== {name} ==")
        for key, sv in stats.items():
            sd = STAT_BY_KEY[key]
            sample = "" if sd.kind in ("count", "money", "bb100") else f"  ({int(sv.num)}/{int(sv.den)})"
            print(f"  {sd.label:7} {sv.format(sd.kind):>8}{sample}")
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
    sub.add_parser("windows", help="liste les fenêtres ouvertes (diagnostic)")
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

    db = Database(args.db or database_path(cfg))
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
        if command == "stats":
            return cmd_stats(db, args.players, args.list)
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
