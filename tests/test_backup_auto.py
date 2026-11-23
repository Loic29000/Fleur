import os
import time

from conftest import FIXTURES

from fleur.backup import auto_backup_due, last_backup_age_hours, list_backups, start_auto_backup
from fleur.db import Database
from fleur.parser import iter_hands


def make_db(tmp_path):
    path = tmp_path / "fleur.db"
    db = Database(path)
    db.add_hands(iter_hands((FIXTURES / "cash_6max.txt").read_text(encoding="utf-8")))
    db.close()
    return path


def test_auto_backup_runs_once_per_interval(tmp_path):
    db_path, dest = make_db(tmp_path), tmp_path / "sauvegardes"
    cfg = {"auto_backup": True, "backup_interval_hours": 24, "backup_keep": 3}
    assert auto_backup_due(cfg, dest) and last_backup_age_hours(dest) is None
    done = []
    start_auto_backup(db_path, cfg, lambda out, err: done.append((out, err)), dest).join(10)
    assert done and done[0][1] is None and Database(done[0][0]).hand_count() == 3
    assert not auto_backup_due(cfg, dest)
    assert start_auto_backup(db_path, cfg, dest=dest) is None  # déjà faite aujourd'hui
    # une sauvegarde vieille de deux jours : à refaire
    old = list_backups(dest)[0]["path"]
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))
    assert auto_backup_due(cfg, dest)
    assert not auto_backup_due({**cfg, "auto_backup": False}, dest)


def test_backup_keeps_only_the_latest(tmp_path):
    from fleur.backup import backup_file
    db_path, dest = make_db(tmp_path), tmp_path / "s"
    for _ in range(4):
        backup_file(db_path, dest, keep=2)
        time.sleep(1.1)  # noms horodatés à la seconde
    assert len(list_backups(dest)) == 2
