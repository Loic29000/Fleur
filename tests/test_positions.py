import sqlite3

from conftest import FIXTURES

from fleur.config import DEFAULT_CONFIG
from fleur.db import Database
from fleur.parser import iter_hands


def load(db):
    for name in ("cash_6max.txt", "winamax_reelles.txt"):
        db.add_hands(iter_hands((FIXTURES / name).read_text(encoding="utf-8")))


def test_position_totals():
    db = Database(":memory:")
    load(db)
    bob = db.position_totals("Bob")
    assert set(bob) == {"CO", "HJ", "UTG"}  # mains 1, 2, 3 du fichier 6-max
    assert bob["CO"]["did_rfi"] == 1 and bob["CO"]["did_steal"] == 1
    charlie = db.position_totals("Charlie")
    assert charlie["CO"]["did_3bet"] == 1  # 3-bet de la main 2
    # filtre : seulement les tables 5-max -> Bob n'y joue pas
    assert db.position_totals("Bob", max_seats=5, seats_mode="same") == {}


def test_old_database_gets_positions(tmp_path):
    path = tmp_path / "old.db"
    db = Database(path)
    load(db)
    db.conn.execute("UPDATE player_hands SET position=NULL")
    db.conn.execute("UPDATE meta SET value='2'")
    db.conn.commit()
    db.close()
    db = Database(path)
    assert db.position_totals("Bob")["CO"]["hands"] == 1
    assert sqlite3.connect(path).execute("SELECT COUNT(*) FROM player_hands WHERE position IS NULL").fetchone()[0] == 0


def test_render_positions():
    from fleur.hud.overlay import render_popup, render_positions
    db = Database(":memory:")
    load(db)
    html = render_positions(db.position_totals("Hero"), DEFAULT_CONFIG)
    assert "Par position" in html and "BB" in html and html.index("UTG") < html.index("BB")
    assert render_positions({}, DEFAULT_CONFIG) == ""
    assert "Par position" in render_popup("Hero", {}, DEFAULT_CONFIG, by_pos=db.position_totals("Hero"))
