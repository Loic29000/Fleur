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
