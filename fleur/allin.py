"""All-in EV : gains « à la régulière » du héros.

Pour chaque main où le héros est allé à tapis (ou a suivi un tapis) avant la
river et où toutes les cartes restantes ont été montrées, on remplace le gain
réel par l'espérance au moment où l'action s'est terminée :

    EV = équité × pot que le héros peut gagner (rake déduit au prorata)
         + mise non suivie rendue − mise du héros

Approximation pour les pots multiples à plusieurs joueurs : l'équité contre
tous les joueurs restants s'applique au pot que le héros peut gagner.
"""

from __future__ import annotations

import json
import zlib

from fleur.db import Database
from fleur.equity import equity
from fleur.parser import Hand, parse_hand
from fleur.stats import hand_counters, invested

_BOARD_AT = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
CACHE_VERSION = 1


def allin_situation(hand: Hand, hero: str) -> dict | None:
    """Données de l'all-in du héros, ou None si la main ne s'y prête pas."""
    if not any(a.allin for a in hand.actions):
        return None
    folded = {a.player for a in hand.actions if a.kind == "fold"}
    remaining = [p for p in hand.players if p not in folded]
    if hero not in remaining or len(remaining) < 2:
        return None
    cards: dict[str, list[str]] = {}
    for p in remaining:
        known = hand.shown.get(p) or (hand.hero_cards if p == hand.hero else None)
        if not known or len(known.split()) != 2:
            return None  # cartes inconnues (ou Omaha) : pas d'équité possible
        cards[p] = known.split()
    voluntary = [a for a in hand.actions if not a.is_post]
    if not voluntary:
        return None
    last_street = voluntary[-1].street
    board_at = hand.board[:_BOARD_AT[last_street]]
    if len(board_at) >= 5 or len(hand.board) < 5:
        return None  # tapis à la river (rien à lisser) ou board incomplet
    inv = invested(hand)
    hero_inv = inv.get(hero, 0.0)
    others = max(inv.get(p, 0.0) for p in remaining if p != hero)
    refund = max(0.0, hero_inv - others)
    eff = hero_inv - refund
    total = sum(inv.values()) + hand.added_money
    pot = sum(min(v, eff) for v in inv.values()) + hand.added_money
    pot_net = pot * (1 - hand.rake / total) if total else pot
    order = [hero] + [p for p in remaining if p != hero]
    return {"order": order, "cards": [cards[p] for p in order], "board": board_at,
            "pot": pot_net, "refund": refund, "hero_inv": hero_inv}


def allin_ev(hand: Hand, hero: str, trials: int = 3000) -> dict | None:
    sit = allin_situation(hand, hero)
    if not sit:
        return None
    seed = zlib.crc32(hand.hand_id.encode())  # même résultat d'un calcul à l'autre
    eq = equity(sit["cards"], sit["board"], trials=trials, seed=seed)["players"][0]["equity"]
    ev = eq * sit["pot"] + sit["refund"] - sit["hero_inv"]
    net = hand_counters(hand)[hero]["net"]
    return {"hand_id": hand.hand_id, "equity": eq, "ev": round(ev, 4), "net": net,
            "cards": " ".join(sit["cards"][0]), "opponents": [" ".join(c) for c in sit["cards"][1:]],
            "board": " ".join(sit["board"]),
            "played_at": hand.played_at.isoformat() if hand.played_at else None}


def _cache(db: Database) -> None:
    db.conn.execute("CREATE TABLE IF NOT EXISTS allin_cache (hand_id TEXT, player TEXT, version INTEGER, "
                    "data TEXT, PRIMARY KEY (hand_id, player))")


def hero_allin_report(db: Database, hero: str) -> dict:
    """Courbes réelle et EV du héros, et liste des all-in analysés (avec cache)."""
    _cache(db)
    cached = {r[0]: (json.loads(r[1]) if r[1] else None) for r in db.conn.execute(
        "SELECT hand_id, data FROM allin_cache WHERE player = ? AND version = ?", (hero, CACHE_VERSION))}
    rows = db.conn.execute(
        "SELECT h.hand_id, ph.net, h.raw LIKE '%all-in%' FROM player_hands ph JOIN hands h ON h.hand_id = ph.hand_id "
        "WHERE ph.player = ? ORDER BY h.played_at, h.hand_id", (hero,)).fetchall()
    new = []
    curve_actual, curve_ev, allins = [0.0], [0.0], []
    for hand_id, net, has_allin in rows:
        result = None
        if has_allin:
            if hand_id in cached:
                result = cached[hand_id]
            else:
                try:
                    result = allin_ev(parse_hand(db.raw_hand(hand_id)), hero)
                except Exception:
                    result = None
                new.append((hand_id, hero, CACHE_VERSION, json.dumps(result) if result else None))
        curve_actual.append(curve_actual[-1] + net)
        curve_ev.append(curve_ev[-1] + (result["ev"] if result else net))
        if result:
            allins.append(result)
    if new:
        with db.conn:
            db.conn.executemany("INSERT OR REPLACE INTO allin_cache VALUES (?,?,?,?)", new)
    return {"actual": round(curve_actual[-1], 2), "ev": round(curve_ev[-1], 2),
            "curve_actual": [round(v, 2) for v in curve_actual], "curve_ev": [round(v, 2) for v in curve_ev],
            "allins": allins}
