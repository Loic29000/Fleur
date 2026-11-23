"""Sauvegarde de la base SQLite (copie cohérente même pendant que le HUD écrit)."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path

from fleur.db import Database

KEEP = 10  # nombre de sauvegardes conservées


def backup_dir() -> Path:
    """Documents\\Fleur\\sauvegardes (hors d'AppData, facile à retrouver et à copier)."""
    docs = Path.home() / "Documents"
    path = (docs if docs.is_dir() else Path.home()) / "Fleur" / "sauvegardes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_database(db: Database, dest: Path | None = None, keep: int = KEEP) -> Path:
    dest = dest or backup_dir()
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"fleur_{time.strftime('%Y%m%d_%H%M%S')}.db"
    target = sqlite3.connect(out)
    try:
        db.conn.backup(target)  # API de sauvegarde SQLite : copie cohérente
    finally:
        target.close()
    for old in list_backups(dest)[keep:]:
        try:
            Path(old["path"]).unlink()
        except OSError:
            pass
    return out


def list_backups(dest: Path | None = None) -> list[dict]:
    dest = dest or backup_dir()
    files = sorted(dest.glob("fleur_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "path": str(p), "size": p.stat().st_size,
             "date": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")} for p in files]


def backup_file(db_path: str | Path, dest: Path | None = None, keep: int = KEEP) -> Path:
    """Sauvegarde à partir du chemin de la base, avec une connexion dédiée
    (utilisable depuis un fil d'exécution en arrière-plan)."""
    db = Database(db_path)
    try:
        return backup_database(db, dest, keep)
    finally:
        db.close()


def last_backup_age_hours(dest: Path | None = None) -> float | None:
    items = list_backups(dest)
    if not items:
        return None
    return (time.time() - Path(items[0]["path"]).stat().st_mtime) / 3600


def auto_backup_due(cfg: dict, dest: Path | None = None) -> bool:
    if not cfg.get("auto_backup", True):
        return False
    age = last_backup_age_hours(dest)
    return age is None or age >= cfg.get("backup_interval_hours", 24)


def start_auto_backup(db_path: str | Path, cfg: dict, on_done=None, dest: Path | None = None):
    """Lance une sauvegarde en arrière-plan si la dernière date de plus de
    `backup_interval_hours`. Renvoie le fil lancé, ou None si rien à faire."""
    import logging
    import threading
    log = logging.getLogger("fleur")
    if not auto_backup_due(cfg, dest):
        return None

    def run():
        try:
            out = backup_file(db_path, dest, cfg.get("backup_keep", KEEP))
            log.info("sauvegarde automatique : %s", out)
            if on_done:
                on_done(out, None)
        except Exception as exc:
            log.exception("sauvegarde automatique impossible")
            if on_done:
                on_done(None, exc)

    thread = threading.Thread(target=run, name="fleur-backup", daemon=True)
    thread.start()
    return thread
