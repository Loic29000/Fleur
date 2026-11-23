"""Stockage SQLite des mains et des compteurs de stats."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from fleur.parser import Hand
from fleur.stats import ALL_COUNTERS, FLOAT_COUNTERS, hand_counters, positions
from fleur.summary import ShownHand, shown_hands

# Version du schéma : on complète les données des anciennes bases à l'ouverture
SCHEMA_VERSION = 3

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
    position TEXT,
    {", ".join(f"{k} {'REAL' if k in FLOAT_COUNTERS else 'INTEGER'} NOT NULL DEFAULT 0" for k in ALL_COUNTERS)},
    PRIMARY KEY (hand_id, player)
);
CREATE INDEX IF NOT EXISTS idx_player_hands_player ON player_hands(player);
CREATE INDEX IF NOT EXISTS idx_hands_format ON hands(max_seats, bb);
CREATE TABLE IF NOT EXISTS player_notes (
    player     TEXT PRIMARY KEY,
    tag        TEXT,
    label      TEXT,
    color      TEXT,
    note       TEXT NOT NULL DEFAULT '',
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS shown_hands (
    hand_id   TEXT NOT NULL,
    player    TEXT NOT NULL,
    played_at TEXT,
    cards     TEXT,
    board     TEXT,
    line      TEXT,
    net       REAL,
    net_bb    REAL,
    bb        REAL,
    PRIMARY KEY (hand_id, player)
);
CREATE INDEX IF NOT EXISTS idx_shown_player ON shown_hands(player, played_at);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS files (
    path   TEXT PRIMARY KEY,
    offset INTEGER NOT NULL
);
"""


@dataclass
class PlayerNote:
    player: str
    tag: str | None = None  # clé d'étiquette (fish, reg, ...) ou "perso"
    label: str | None = None  # texte affiché de l'étiquette
    color: str | None = None
    note: str = ""

    @property
    def empty(self) -> bool:
        return not self.tag and not self.note.strip()


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(_SCHEMA)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(player_hands)")}
        if "position" not in cols:  # base créée avant la version 3
            self.conn.execute("ALTER TABLE player_hands ADD COLUMN position TEXT")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_player_hands_pos ON player_hands(player, position)")
        self._migrate()

    def _migrate(self) -> None:
        row = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        version = int(row[0]) if row else 1
        if version < 2:
            self.backfill_shown_hands()
        if version < 3:
            self.backfill_positions()
        if version != SCHEMA_VERSION:
            with self.conn:
                self.conn.execute("INSERT OR REPLACE INTO meta VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))

    def backfill_shown_hands(self) -> int:
        """Remplit shown_hands à partir des mains déjà en base (bases antérieures)."""
        from fleur.parser import parse_hand
        count = 0
        cur = self.conn.execute("SELECT raw FROM hands WHERE raw LIKE '%shows [%'")
        with self.conn:
            for (raw,) in cur.fetchall():
                try:
                    count += self._insert_shown(parse_hand(raw))
                except Exception:  # une main bizarre ne bloque pas la migration
                    continue
        return count

    def backfill_positions(self) -> int:
        """Calcule la position des joueurs pour les mains déjà en base."""
        from fleur.parser import parse_hand
        from fleur.stats import positions
        count = 0
        cur = self.conn.execute("SELECT raw FROM hands")
        with self.conn:
            for (raw,) in cur.fetchall():
                try:
                    hand = parse_hand(raw)
                    rows = [(pos, hand.hand_id, p) for p, pos in positions(hand).items()]
                except Exception:
                    continue
                self.conn.executemany("UPDATE player_hands SET position=? WHERE hand_id=? AND player=?", rows)
                count += 1
        return count

    def _insert_shown(self, hand: Hand) -> int:
        rows = shown_hands(hand)
        for sh in rows:
            self.conn.execute(
                "INSERT OR REPLACE INTO shown_hands VALUES (?,?,?,?,?,?,?,?,?)",
                (sh.hand_id, sh.player, sh.played_at, sh.cards, sh.board, sh.line, sh.net, sh.net_bb, sh.bb),
            )
        return len(rows)

    def close(self) -> None:
        self.conn.close()

    # -- mains ---------------------------------------------------------------
    def has_hand(self, hand_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM hands WHERE hand_id=?", (hand_id,)).fetchone() is not None

    def add_hands(self, hands: Iterable[Hand]) -> list[Hand]:
        """Ajoute les mains nouvelles et renvoie celles réellement insérées."""
        inserted = []
        cols = ", ".join(["hand_id", "player", "seat", "position", *ALL_COUNTERS])
        marks = ", ".join("?" * (4 + len(ALL_COUNTERS)))
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
                pos = positions(hand)
                for player, counters in hand_counters(hand).items():
                    self.conn.execute(
                        f"INSERT OR REPLACE INTO player_hands ({cols}) VALUES ({marks})",
                        (hand.hand_id, player, hand.seat_of(player), pos.get(player),
                         *(counters[k] for k in ALL_COUNTERS)),
                    )
                self._insert_shown(hand)
                inserted.append(hand)
        return inserted

    def last_shown(self, player: str, limit: int = 8) -> list[ShownHand]:
        rows = self.conn.execute(
            "SELECT hand_id, player, played_at, cards, board, line, net, net_bb, bb FROM shown_hands "
            "WHERE player=? ORDER BY played_at DESC, hand_id DESC LIMIT ?", (player, limit),
        ).fetchall()
        return [ShownHand(*r) for r in rows]

    def hand_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM hands").fetchone()[0]

    # -- stats ---------------------------------------------------------------
    def totals(self, players: Iterable[str], max_seats: int | None = None, bb: float | None = None,
               seats_mode: str = "all", stakes_mode: str = "all") -> dict[str, dict[str, float]]:
        """Sommes des compteurs par joueur.

        Filtres (contexte = table en cours) :
        - seats_mode "all" : tous formats ; "same" : même nombre de sièges que
          `max_seats` ; "hu_apart" : tête-à-tête d'un côté, tables à 3+ de l'autre ;
        - stakes_mode "all" : toutes limites ; "same" : même big blind que `bb`.
        """
        players = list(players)
        if not players:
            return {}
        rows = self._grouped(players, "ph.player", max_seats, bb, seats_mode, stakes_mode)
        result = {p: {k: 0.0 for k in ALL_COUNTERS} for p in players}
        for row in rows:
            result[row[0]] = dict(zip(ALL_COUNTERS, (v or 0 for v in row[1:])))
        return result

    def position_totals(self, player: str, max_seats: int | None = None, bb: float | None = None,
                        seats_mode: str = "all", stakes_mode: str = "all") -> dict[str, dict[str, float]]:
        """Compteurs d'un joueur par position (UTG, HJ, CO, BTN, SB, BB...)."""
        rows = self._grouped([player], "ph.position", max_seats, bb, seats_mode, stakes_mode)
        return {r[0]: dict(zip(ALL_COUNTERS, (v or 0 for v in r[1:]))) for r in rows if r[0]}

    def _grouped(self, players: list[str], group: str, max_seats, bb, seats_mode, stakes_mode) -> list:
        sums = ", ".join(f"SUM(ph.{k})" for k in ALL_COUNTERS)
        marks = ", ".join("?" * len(players))
        where, params = [f"ph.player IN ({marks})"], list(players)
        if seats_mode == "same" and max_seats:
            where.append("h.max_seats = ?")
            params.append(max_seats)
        elif seats_mode == "hu_apart" and max_seats:
            where.append("h.max_seats <= 2" if max_seats <= 2 else "h.max_seats > 2")
        if stakes_mode == "same" and bb:
            where.append("ABS(h.bb - ?) < 1e-6")
            params.append(bb)
        join = " JOIN hands h ON h.hand_id = ph.hand_id" if len(where) > 1 else ""
        return self.conn.execute(
            f"SELECT {group}, {sums} FROM player_hands ph{join} WHERE {' AND '.join(where)} GROUP BY {group}",
            params,
        ).fetchall()

    def top_players(self, limit: int = 20) -> list[tuple[str, int]]:
        return self.conn.execute(
            "SELECT player, COUNT(*) n FROM player_hands GROUP BY player ORDER BY n DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def heroes(self) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT hero FROM hands WHERE hero IS NOT NULL").fetchall()]

    # -- notes et étiquettes -------------------------------------------------
    def notes(self, players: Iterable[str]) -> dict[str, PlayerNote]:
        players = list(players)
        if not players:
            return {}
        marks = ", ".join("?" * len(players))
        rows = self.conn.execute(
            f"SELECT player, tag, label, color, note FROM player_notes WHERE player IN ({marks})", players
        ).fetchall()
        return {r[0]: PlayerNote(r[0], r[1], r[2], r[3], r[4] or "") for r in rows}

    def note(self, player: str) -> PlayerNote:
        return self.notes([player]).get(player) or PlayerNote(player)

    def save_note(self, note: PlayerNote) -> None:
        with self.conn:
            if note.empty:
                self.conn.execute("DELETE FROM player_notes WHERE player=?", (note.player,))
                return
            self.conn.execute(
                "INSERT INTO player_notes(player, tag, label, color, note, updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(player) DO UPDATE SET tag=excluded.tag, label=excluded.label, "
                "color=excluded.color, note=excluded.note, updated_at=excluded.updated_at",
                (note.player, note.tag, note.label, note.color, note.note,
                 datetime.now().isoformat(timespec="seconds")),
            )

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
