"""Requêtes d'analyse du héros pour l'application locale (revue de mains,
ranges, sessions...). Analyse a posteriori de l'historique uniquement."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fleur.db import Database

RANKS = "AKQJT98765432"
POSITIONS = ["UTG", "UTG+1", "UTG+2", "MP", "LJ", "HJ", "CO", "BTN", "SB", "BB"]


def main_hero(db: Database) -> str | None:
    row = db.conn.execute(
        "SELECT hero, COUNT(*) n FROM hands WHERE hero IS NOT NULL GROUP BY hero ORDER BY n DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


# --------------------------------------------------------------------------
# Revue de mains
# --------------------------------------------------------------------------

SORTS = {
    "date": "h.played_at DESC, h.hand_id DESC",
    "pot": "h.pot / h.bb DESC",
    "gain": "ph.net_bb DESC",
    "perte": "ph.net_bb ASC",
}


def hand_list(db: Database, hero: str, position: str = "", result: str = "", min_pot_bb: float = 0,
              bb: float = 0, showdown: str = "", cards: str = "", sort: str = "date",
              limit: int = 200, offset: int = 0, mark: str = "") -> dict:
    """Mains du héros filtrées. `result` : gagnée/perdue ; `showdown` : oui/non ;
    `cards` : classe de main de départ (AKs, 77...) ; `mark` : « * » pour toute main
    marquée, ou une étiquette précise."""
    where, params = ["ph.player = ?"], [hero]
    if position:
        where.append("ph.position = ?")
        params.append(position)
    if result == "gagnee":
        where.append("ph.net > 0")
    elif result == "perdue":
        where.append("ph.net < 0")
    if min_pot_bb:
        where.append("h.pot >= ? * h.bb")
        params.append(min_pot_bb)
    if bb:
        where.append("ABS(h.bb - ?) < 1e-6")
        params.append(bb)
    if showdown == "oui":
        where.append("ph.wtsd = 1")
    elif showdown == "non":
        where.append("ph.wtsd = 0")
    if mark == "*":
        where.append("m.hand_id IS NOT NULL")
    elif mark:
        where.append("(',' || m.tags || ',') LIKE ?")
        params.append(f"%,{mark},%")
    sql_where = " AND ".join(where)
    base = (f"FROM player_hands ph JOIN hands h ON h.hand_id = ph.hand_id "
            f"LEFT JOIN hand_marks m ON m.hand_id = h.hand_id WHERE {sql_where}")
    rows = db.conn.execute(
        f"SELECT h.hand_id, h.played_at, h.table_name, h.sb, h.bb, h.max_seats, h.pot, h.hero_cards, "
        f"ph.position, ph.net, ph.net_bb, ph.wtsd, ph.vpip, ph.pfr, m.tags, m.comment {base} ORDER BY {SORTS.get(sort, SORTS['date'])}",
        params,
    ).fetchall()
    if cards:
        rows = [r for r in rows if hand_class(r[7]) == cards]
    items = [{
        "hand_id": r[0], "played_at": r[1], "table": r[2], "stakes": f"{r[3]:g}/{r[4]:g}", "bb": r[4],
        "max_seats": r[5], "pot": r[6], "pot_bb": (r[6] or 0) / r[4] if r[4] else 0, "cards": r[7] or "",
        "position": r[8] or "", "net": r[9], "net_bb": r[10], "showdown": bool(r[11]),
        "tags": [t for t in (r[14] or "").split(",") if t], "comment": r[15] or "",
    } for r in rows]
    return {"total": len(items), "items": items[offset:offset + limit]}


# --------------------------------------------------------------------------
# Ranges : grille 13×13
# --------------------------------------------------------------------------

def hand_class(cards: str | None) -> str | None:
    """'Ah Kd' -> 'AKo', 'Qs Qc' -> 'QQ', 'Th 9h' -> 'T9s'. None si inconnu."""
    if not cards:
        return None
    parts = cards.split()
    if len(parts) != 2 or any(len(p) < 2 for p in parts):
        return None  # Omaha ou format inattendu
    (r1, s1), (r2, s2) = [(p[0].upper(), p[-1].lower()) for p in parts]
    if r1 not in RANKS or r2 not in RANKS:
        return None
    if RANKS.index(r1) > RANKS.index(r2):
        r1, s1, r2, s2 = r2, s2, r1, s1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ("s" if s1 == s2 else "o")


def grid_labels() -> list[list[str]]:
    """Grille classique : paires sur la diagonale, suitées au-dessus, offsuit en dessous."""
    out = []
    for i, a in enumerate(RANKS):
        row = []
        for j, b in enumerate(RANKS):
            row.append(a + b if i == j else (a + b + "s" if j > i else b + a + "o"))
        out.append(row)
    return out


def ranges(db: Database, hero: str, position: str = "", bb: float = 0) -> dict:
    where, params = ["ph.player = ?", "h.hero_cards IS NOT NULL"], [hero]
    if position:
        where.append("ph.position = ?")
        params.append(position)
    if bb:
        where.append("ABS(h.bb - ?) < 1e-6")
        params.append(bb)
    rows = db.conn.execute(
        f"SELECT h.hero_cards, ph.vpip, ph.pfr, ph.net, ph.net_bb FROM player_hands ph "
        f"JOIN hands h ON h.hand_id = ph.hand_id WHERE {' AND '.join(where)}", params,
    ).fetchall()
    cells: dict[str, dict] = defaultdict(lambda: {"n": 0, "vpip": 0, "pfr": 0, "net": 0.0, "net_bb": 0.0})
    for cards, vpip, pfr, net, net_bb in rows:
        cls = hand_class(cards)
        if not cls:
            continue
        c = cells[cls]
        c["n"] += 1
        c["vpip"] += vpip
        c["pfr"] += pfr
        c["net"] += net
        c["net_bb"] += net_bb
    out = {}
    for cls, c in cells.items():
        n = c["n"]
        out[cls] = {"n": n, "vpip": 100 * c["vpip"] / n, "pfr": 100 * c["pfr"] / n,
                    "net": round(c["net"], 2), "bb100": 100 * c["net_bb"] / n}
    return {"labels": grid_labels(), "cells": out, "hands": sum(c["n"] for c in out.values())}


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

def _local(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).astimezone()


def session_report(db: Database, hero: str, gap_minutes: int = 30) -> dict:
    rows = db.conn.execute(
        "SELECT h.played_at, h.table_name, h.bb, ph.net, ph.net_bb FROM player_hands ph "
        "JOIN hands h ON h.hand_id = ph.hand_id WHERE ph.player = ? AND h.played_at IS NOT NULL "
        "ORDER BY h.played_at", (hero,),
    ).fetchall()
    sessions: list[dict] = []
    by_table: dict[str, dict] = defaultdict(lambda: {"hands": 0, "net": 0.0, "net_bb": 0.0})
    by_hour: dict[int, dict] = defaultdict(lambda: {"hands": 0, "net": 0.0, "net_bb": 0.0})
    by_day: dict[int, dict] = defaultdict(lambda: {"hands": 0, "net": 0.0, "net_bb": 0.0})
    last = None
    for played_at, table, bb, net, net_bb in rows:
        when = _local(played_at)
        if last is None or (when - last).total_seconds() > gap_minutes * 60:
            sessions.append({"start": when, "end": when, "hands": 0, "net": 0.0, "net_bb": 0.0, "tables": set()})
        s = sessions[-1]
        s["end"] = when
        s["hands"] += 1
        s["net"] += net
        s["net_bb"] += net_bb
        s["tables"].add(table)
        last = when
        for bucket in (by_table[table], by_hour[when.hour], by_day[when.weekday()]):
            bucket["hands"] += 1
            bucket["net"] += net
            bucket["net_bb"] += net_bb

    def finish(d: dict) -> dict:
        n = d["hands"]
        return {**d, "net": round(d["net"], 2), "bb100": 100 * d["net_bb"] / n if n else 0.0}

    out_sessions = []
    total_minutes = 0.0
    for s in sessions:
        minutes = max((s["end"] - s["start"]).total_seconds() / 60, 1.0)
        total_minutes += minutes
        out_sessions.append(finish({
            "start": s["start"].isoformat(timespec="minutes"), "minutes": round(minutes),
            "hands": s["hands"], "net": s["net"], "net_bb": s["net_bb"], "tables": len(s["tables"]),
            "hands_per_hour": round(60 * s["hands"] / minutes),
        }))
    days = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    total_hands = sum(s["hands"] for s in out_sessions)
    return {
        "sessions": list(reversed(out_sessions)),
        "summary": {
            "sessions": len(out_sessions), "hours": round(total_minutes / 60, 1), "hands": total_hands,
            "hands_per_hour": round(60 * total_hands / total_minutes) if total_minutes else 0,
            "net": round(sum(s["net"] for s in out_sessions), 2),
            "winning_sessions": sum(1 for s in out_sessions if s["net"] > 0),
        },
        "by_table": sorted(({"table": t, **finish(d)} for t, d in by_table.items()), key=lambda r: -r["hands"]),
        "by_hour": [{"hour": h, **finish(by_hour[h])} for h in range(24) if h in by_hour],
        "by_day": [{"day": days[d], **finish(by_day[d])} for d in range(7) if d in by_day],
    }
