"""Revue « GTO » des mains jouées : compare les décisions du héros aux repères
d'étude de fleur.gto (ranges préflop simplifiées, c-bet selon la texture).

Analyse après coup uniquement (bloquée quand une table Winamax est ouverte).
Les verdicts préflop sont nets quand la référence est claire ; en postflop,
l'optimal mélange souvent les actions : on parle d'« écart de tendance ».
"""

from __future__ import annotations

import json

from fleur.analysis import hand_class
from fleur.db import Database
from fleur.gto import CBET_GUIDE, board_texture, spot_grid
from fleur.parser import Hand, parse_hand
from fleur.stats import invested, positions

REVIEW_VERSION = 1
_GRIDS: dict[str, dict] = {}

CONFORME, TROP_LARGE, TROP_SERRE, AUTRE, TENDANCE = (
    "conforme", "trop large", "trop serré", "action différente", "écart de tendance")


def _grid(spot_id: str) -> dict:
    if spot_id not in _GRIDS:
        _GRIDS[spot_id] = spot_grid(spot_id)
    return _GRIDS[spot_id]


def _six_max(pos: str, max_seats: int) -> str:
    """Positions 5-max -> équivalent 6-max (la première position joue comme HJ)."""
    if max_seats == 5 and pos == "UTG":
        return "HJ"
    return pos


# Situation « face à une ouverture » : (position du héros, position de l'ouvreur) -> spot
def _vs_open_spot(hero: str, opener: str) -> str | None:
    if hero == "BB":
        return {"UTG": "bb_vs_utg", "HJ": "bb_vs_utg", "CO": "bb_vs_co", "BTN": "bb_vs_btn", "SB": "bb_vs_btn"}.get(opener)
    if hero == "SB":
        return "sb_vs_btn" if opener in ("BTN", "CO") else None
    if hero == "BTN":
        return {"UTG": "btn_vs_utg", "HJ": "btn_vs_co", "CO": "btn_vs_co"}.get(opener)
    if hero == "CO":
        return "co_vs_hj" if opener in ("HJ", "UTG") else None
    return None


def _vs_3bet_spot(hero: str) -> str | None:
    return {"BTN": "btn_vs_bb3b", "CO": "co_vs_btn3b", "UTG": "utg_vs_3b", "HJ": "utg_vs_3b"}.get(hero)


def _verdict(spot_id: str, cls: str, action: str) -> dict:
    """Compare l'action du héros (raise/3bet/4bet/call/fold) à la référence."""
    freqs = _grid(spot_id)["cells"].get(cls, {})
    played = sum(freqs.values())
    ref_fold = max(0.0, 1 - played)
    chosen = ref_fold if action == "fold" else freqs.get(action, 0.0)
    if chosen >= 0.25:
        verdict = CONFORME
    elif action == "fold":
        verdict = TROP_SERRE
    elif ref_fold >= 0.75:
        verdict = TROP_LARGE
    else:
        verdict = AUTRE
    ref = {a: round(100 * f) for a, f in freqs.items()}
    ref["fold"] = round(100 * ref_fold)
    return {"spot": spot_id, "title": _grid(spot_id)["title"], "action": action, "verdict": verdict,
            "reference": ref}


def review_preflop(hand: Hand, hero: str) -> list[dict]:
    cls = hand_class(hand.hero_cards) if hero == hand.hero else None
    if not cls:
        return []
    pos_map = positions(hand)
    hero_pos = _six_max(pos_map.get(hero, ""), hand.max_seats)
    raisers: list[str] = []
    limpers = 0
    out = []
    for a in hand.actions:
        if a.street != "preflop" or a.is_post:
            continue
        if a.player == hero:
            act = {"raise": "raise", "call": "call", "fold": "fold"}.get(a.kind)
            if act is None:  # check en BB : rien à juger
                break
            if not raisers and not limpers:
                if hero_pos in ("UTG", "HJ", "CO", "BTN", "SB"):
                    if act == "call":
                        out.append({"spot": None, "title": f"Ouverture {hero_pos}", "action": "limp",
                                    "verdict": AUTRE, "reference": {}, "note": "la référence ouvre en relance ou passe"})
                    else:
                        out.append(_verdict(f"rfi_{hero_pos.lower()}", cls, act))
            elif len(raisers) == 1 and raisers[0] != hero and not limpers:
                opener = _six_max(pos_map.get(raisers[0], ""), hand.max_seats)
                spot = _vs_open_spot(hero_pos, opener)
                if spot:
                    out.append(_verdict(spot, cls, "3bet" if act == "raise" else act))
            elif len(raisers) == 2 and raisers[0] == hero:
                spot = _vs_3bet_spot(hero_pos)
                if spot:
                    out.append(_verdict(spot, cls, "4bet" if act == "raise" else act))
            if act == "fold":
                break
        if a.kind == "raise":
            raisers.append(a.player)
        elif a.kind == "call" and not raisers:
            limpers += 1
    return out


def _sizing_bounds(text: str) -> tuple[float, float]:
    nums = [float(x) for x in text.replace("%", "").replace(" ", "").split("-")]
    return nums[0], nums[-1]


def review_cbet(hand: Hand, hero: str) -> dict | None:
    """C-bet au flop du relanceur préflop, en tête-à-tête."""
    if len(hand.board) < 3:
        return None
    pre = [a for a in hand.actions if a.street == "preflop" and a.kind == "raise"]
    if not pre or pre[-1].player != hero:
        return None
    folded_pre = {a.player for a in hand.actions if a.street == "preflop" and a.kind == "fold"}
    in_flop = [p for p in hand.players if p not in folded_pre]
    if len(in_flop) != 2 or hero not in in_flop:
        return None  # pots à plusieurs : non couvert
    flop = [a for a in hand.actions if a.street == "flop"]
    first_bet_index = next((i for i, a in enumerate(flop) if a.kind in ("bet", "raise")), len(flop))
    hero_first = next((i for i, a in enumerate(flop) if a.player == hero), None)
    if hero_first is None or hero_first > first_bet_index:
        return None  # l'adversaire a misé avant : pas d'occasion de c-bet
    in_position = flop[0].player != hero
    pot = sum(invested(hand, "preflop").values()) + hand.added_money
    tex = board_texture(hand.board[:3])
    guide = CBET_GUIDE[tex["kind"]]
    freq, sizing = guide["ip" if in_position else "oop"]
    low, high = _sizing_bounds(sizing)
    action = flop[hero_first]
    out = {"spot": "cbet", "title": f"C-bet flop {'en position' if in_position else 'hors de position'} "
                                    f"(board {tex['kind']})",
           "texture": tex["kind"], "reference": {"frequence": freq, "taille": sizing}}
    if action.kind == "bet":
        size = round(100 * action.amount / pot) if pot else 0
        out["action"] = f"mise {size} %"
        if low - 10 <= size <= high + 20:
            out["verdict"] = CONFORME
        else:
            out["verdict"] = TENDANCE
            out["note"] = f"taille de {size} % du pot, la référence mise {sizing}"
        if freq < 35:
            out["note"] = (out.get("note", "") + " ; ici la référence checke le plus souvent").lstrip(" ;")
    else:
        out["action"] = "check"
        if freq >= 65:
            out["verdict"] = TENDANCE
            out["note"] = f"la référence mise environ {freq} % du temps ici, petit ({sizing})"
        else:
            out["verdict"] = CONFORME
    return out


def review_hand(hand: Hand, hero: str) -> dict:
    decisions = review_preflop(hand, hero)
    cbet = review_cbet(hand, hero)
    if cbet:
        decisions.append(cbet)
    worst = next((d["verdict"] for d in decisions if d["verdict"] in (TROP_LARGE, TROP_SERRE, AUTRE)), None)
    if worst is None and any(d["verdict"] == TENDANCE for d in decisions):
        worst = TENDANCE
    return {"hand_id": hand.hand_id, "cards": hand.hero_cards, "decisions": decisions,
            "status": worst or (CONFORME if decisions else None)}


# --------------------------------------------------------------------------
# Cache en base et bilan
# --------------------------------------------------------------------------

def _ensure_table(db: Database) -> None:
    db.conn.execute("CREATE TABLE IF NOT EXISTS gto_review (hand_id TEXT PRIMARY KEY, version INTEGER, "
                    "status TEXT, data TEXT)")


def build_reviews(db: Database, hero: str, on_progress=None) -> int:
    """Calcule (une fois) la revue de toutes les mains du héros. Renvoie le nombre de nouvelles."""
    _ensure_table(db)
    rows = db.conn.execute(
        "SELECT h.hand_id, h.raw FROM hands h LEFT JOIN gto_review g ON g.hand_id = h.hand_id "
        "AND g.version = ? WHERE h.hero = ? AND g.hand_id IS NULL", (REVIEW_VERSION, hero)).fetchall()
    batch = []
    for i, (hand_id, raw) in enumerate(rows, 1):
        try:
            r = review_hand(parse_hand(raw), hero)
        except Exception:
            r = {"hand_id": hand_id, "decisions": [], "status": None}
        batch.append((hand_id, REVIEW_VERSION, r["status"], json.dumps(r, ensure_ascii=False)))
        if len(batch) >= 2000:
            with db.conn:
                db.conn.executemany("INSERT OR REPLACE INTO gto_review VALUES (?,?,?,?)", batch)
            batch = []
            if on_progress:
                on_progress(i, len(rows))
    if batch:
        with db.conn:
            db.conn.executemany("INSERT OR REPLACE INTO gto_review VALUES (?,?,?,?)", batch)
    return len(rows)


def summary(db: Database, hero: str) -> dict:
    build_reviews(db, hero)
    by_spot: dict[str, dict] = {}
    deviations: dict[str, dict[str, int]] = {}
    totals = {"decisions": 0, CONFORME: 0, TROP_LARGE: 0, TROP_SERRE: 0, AUTRE: 0, TENDANCE: 0}
    for (data,) in db.conn.execute("SELECT g.data FROM gto_review g JOIN hands h ON h.hand_id = g.hand_id "
                                   "WHERE h.hero = ? AND g.status IS NOT NULL", (hero,)):
        r = json.loads(data)
        cls = hand_class(r.get("cards"))
        for d in r["decisions"]:
            title = d["title"]
            s = by_spot.setdefault(title, {"title": title, "decisions": 0, CONFORME: 0, TROP_LARGE: 0,
                                           TROP_SERRE: 0, AUTRE: 0, TENDANCE: 0})
            s["decisions"] += 1
            s[d["verdict"]] += 1
            totals["decisions"] += 1
            totals[d["verdict"]] += 1
            if d["verdict"] in (TROP_LARGE, TROP_SERRE) and cls:
                key = f"{title}|{d['verdict']}"
                deviations.setdefault(key, {})
                deviations[key][cls] = deviations[key].get(cls, 0) + 1
    spots = sorted(by_spot.values(), key=lambda s: -s["decisions"])
    for s in spots:
        s["conforme_pct"] = round(100 * s[CONFORME] / s["decisions"]) if s["decisions"] else None
        top = []
        for verdict in (TROP_LARGE, TROP_SERRE):
            hands = deviations.get(f"{s['title']}|{verdict}", {})
            top += [{"hand": h, "count": n, "verdict": verdict}
                    for h, n in sorted(hands.items(), key=lambda kv: -kv[1])[:6]]
        s["top_deviations"] = top
    pre = totals["decisions"] - totals[TENDANCE]
    return {"totals": totals, "conforme_pct": round(100 * totals[CONFORME] / totals["decisions"])
            if totals["decisions"] else None, "spots": spots, "preflop_decisions": pre}
