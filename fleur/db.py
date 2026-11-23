"""Stockage SQLite des mains et des compteurs de stats."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from fleur.parser import Hand
from fleur.stats import ALL_COUNTERS, FLOAT_COUNTERS, hand_counters

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS hands (
    hand_id   TEXT PRIMARY KEY,
    table_name TEXT,
    kind      TEXT,
    game      TEXT,
    played_at TEXT,
    sb        REAL,
    bb        REAL,
    max_seats INTEGER,
    hero      TEXT,
    raw       TEXT
);
CREATE TABLE IF NOT EXISTS player_hands (
    hand_id TEXT NOT NULL,
    player  TEXT NOT NULL,
    seat    INTEGER,
    {", ".join(f"{k} {'REAL' if k in FLOAT_COUNTERS else 'INTEGER'} NOT NULL DEFAULT 0" for k in ALL_COUNTERS)},
    PRIMARY KEY (hand_id, player)
);
CREATE INDEX IF NOT EXISTS idx_player_hands_player ON player_hands(player);
CREATE TABLE IF NOT EXISTS files (
    path   TEXT PRIMARY KEY,
    offset INTEGER NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # -- mains ---------------------------------------------------------------
    def has_hand(self, hand_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM hands WHERE hand_id=?", (hand_id,)).fetchone() is not None

    def add_hands(self, hands: Iterable[Hand]) -> list[Hand]:
        """Ajoute les mains nouvelles et renvoie celles réellement insérées."""
        inserted = []
        cols = ", ".join(["hand_id", "player", "seat", *ALL_COUNTERS])
        marks = ", ".join("?" * (3 + len(ALL_COUNTERS)))
        with self.conn:
            for hand in hands:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO hands VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        hand.hand_id, hand.table, hand.kind, hand.game,
                        hand.played_at.isoformat() if hand.played_at else None,
                        hand.sb, hand.bb, hand.max_seats, hand.hero, hand.raw,
                    ),
                )
                if cur.rowcount == 0:
                    continue
                for player, counters in hand_counters(hand).items():
                    self.conn.execute(
                        f"INSERT OR REPLACE INTO player_hands ({cols}) VALUES ({marks})",
                        (hand.hand_id, player, hand.seat_of(player), *(counters[k] for k in ALL_COUNTERS)),
                    )
                inserted.append(hand)
        return inserted

    def hand_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM hands").fetchone()[0]

    # -- stats ---------------------------------------------------------------
    def totals(self, players: Iterable[str]) -> dict[str, dict[str, float]]:
        players = list(players)
        if not players:
            return {}
        sums = ", ".join(f"SUM({k})" for k in ALL_COUNTERS)
        marks = ", ".join("?" * len(players))
        rows = self.conn.execute(
            f"SELECT player, {sums} FROM player_hands WHERE player IN ({marks}) GROUP BY player",
            players,
        ).fetchall()
        result = {p: {k: 0.0 for k in ALL_COUNTERS} for p in players}
        for row in rows:
            result[row[0]] = dict(zip(ALL_COUNTERS, (v or 0 for v in row[1:])))
        return result

    def top_players(self, limit: int = 20) -> list[tuple[str, int]]:
        return self.conn.execute(
            "SELECT player, COUNT(*) n FROM player_hands GROUP BY player ORDER BY n DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def heroes(self) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT hero FROM hands WHERE hero IS NOT NULL").fetchall()]

    # -- suivi des fichiers ----------------------------------------------------
    def file_offset(self, path: str) -> int:
        row = self.conn.execute("SELECT offset FROM files WHERE path=?", (path,)).fetchone()
        return row[0] if row else 0

    def set_file_offset(self, path: str, offset: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO files(path, offset) VALUES(?, ?) "
                "ON CONFLICT(path) DO UPDATE SET offset=excluded.offset",
                (path, offset),
            )
