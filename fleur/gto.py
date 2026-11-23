"""Matériel d'étude « GTO » : ranges préflop et repères postflop simplifiés.

Ce sont des approximations de stratégies d'équilibre pour le cash game 6-max à
100 big blinds, du type de celles qu'on trouve dans les tableaux d'étude
publiés : elles servent à réviser HORS PARTIE. Elles ne viennent pas d'un
solveur exécuté par Fleur, et l'application refuse de les afficher tant
qu'une table Winamax est ouverte (règles Winamax : pas d'aide à la décision
pendant le jeu).
"""

from __future__ import annotations

import re

RANKS = "AKQJT98765432"
_R = {r: i for i, r in enumerate(RANKS)}  # 0 = As


# --------------------------------------------------------------------------
# Notation des ranges : "22+, A2s+, KTs-K8s, ATo+, AK, T9s:0.5"
# --------------------------------------------------------------------------

def all_classes() -> list[str]:
    out = []
    for i, a in enumerate(RANKS):
        for j, b in enumerate(RANKS):
            out.append(a + b if i == j else (a + b + "s" if j > i else b + a + "o"))
    return out


def _pair_range(lo: str, hi: str) -> list[str]:
    a, b = sorted((_R[lo], _R[hi]))
    return [RANKS[i] * 2 for i in range(a, b + 1)]


def _kicker_range(high: str, k1: str, k2: str, suit: str) -> list[str]:
    a, b = sorted((_R[k1], _R[k2]))
    return [high + RANKS[i] + suit for i in range(a, b + 1) if RANKS[i] != high and _R[high] < i]


def expand(token: str) -> list[str]:
    """Une entrée de range -> liste de classes de mains (AKs, 77, ATo...)."""
    t = token.strip()
    if not t:
        return []
    m = re.fullmatch(r"([AKQJT2-9])\1(\+)?(?:-([AKQJT2-9])\3)?", t)
    if m:  # paires : 77, 77+, 99-66
        if m[3]:
            return _pair_range(m[1], m[3])
        return _pair_range("A", m[1]) if m[2] else [m[1] * 2]
    m = re.fullmatch(r"([AKQJT2-9])([AKQJT2-9])([so]?)(\+)?(?:-([AKQJT2-9])([AKQJT2-9])([so]?))?", t)
    if not m or _R[m[1]] >= _R[m[2]]:
        raise ValueError(f"range illisible : {token!r}")
    high, kick, suit = m[1], m[2], m[3]
    suits = [suit] if suit else ["s", "o"]
    out = []
    for s in suits:
        if m[5]:  # KTs-K8s
            if m[5] != high:
                raise ValueError(f"range illisible : {token!r}")
            out += _kicker_range(high, kick, m[6], s)
        elif m[4]:  # ATs+ : du kicker donné jusqu'au kicker juste sous la haute carte
            out += _kicker_range(high, kick, RANKS[_R[high] + 1], s)
        else:
            out.append(high + kick + s)
    return out


def parse_range(text: str) -> dict[str, float]:
    """'AA, AKs, A5s:0.5' -> {'AA': 1.0, 'AKs': 1.0, 'A5s': 0.5}."""
    out: dict[str, float] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        weight = 1.0
        if ":" in part:
            part, w = part.split(":", 1)
            weight = float(w)
        for cls in expand(part):
            out[cls] = max(out.get(cls, 0.0), weight)
    return out


def combos(cls: str) -> int:
    return 6 if len(cls) == 2 else (4 if cls.endswith("s") else 12)


def range_percent(rng: dict[str, float]) -> float:
    return 100 * sum(combos(c) * w for c, w in rng.items()) / 1326


# --------------------------------------------------------------------------
# Situations préflop (6-max, 100 bb)
# --------------------------------------------------------------------------

ACTION_FR = {"raise": "Ouvrir (relance)", "3bet": "3-bet", "call": "Suivre", "4bet": "4-bet"}
ACTION_COLOR = {"raise": "#e0566b", "3bet": "#e0566b", "4bet": "#b03a8a", "call": "#3d8bd9"}

SPOTS: dict[str, dict] = {
    "rfi_utg": {"title": "Ouverture UTG (personne n'a joué)", "group": "Ouvrir", "position": "UTG",
                "actions": {"raise": "66+, A2s+, KTs+, QTs+, JTs, T9s, 98s:0.5, 87s:0.5, ATo+, KJo+, QJo:0.5"},
                "note": "Range serrée : 5 joueurs restent derrière. Relance de 2,5 bb."},
    "rfi_hj": {"title": "Ouverture HJ", "group": "Ouvrir", "position": "HJ",
               "actions": {"raise": "44+, A2s+, K8s+, Q9s+, J9s+, T8s+, 97s+, 86s+, 76s, 65s:0.5, ATo+, KTo+, "
                                    "QTo+, JTo:0.5"},
               "note": "En 5-max, la première position (UTG) joue à peu près cette range. Relance de 2,5 bb."},
    "rfi_co": {"title": "Ouverture CO", "group": "Ouvrir", "position": "CO",
               "actions": {"raise": "22+, A2s+, K5s+, Q7s+, J7s+, T7s+, 96s+, 85s+, 75s+, 64s+, 54s, A8o+, "
                                    "A5o:0.5, KTo+, QTo+, JTo, T9o:0.5"},
               "note": "Plus large : seuls BTN, SB et BB restent. Relance de 2,5 bb."},
    "rfi_btn": {"title": "Ouverture BTN", "group": "Ouvrir", "position": "BTN",
                "actions": {"raise": "22+, A2s+, K2s+, Q2s+, J5s+, T6s+, 96s+, 85s+, 74s+, 64s+, 53s+, 43s:0.5, A2o+, "
                                     "K8o+, Q9o+, J9o+, T8o+, 98o, 87o:0.5"},
                "note": "Range la plus large : position garantie après le flop. Relance de 2,5 bb."},
    "rfi_sb": {"title": "Ouverture SB (version relance ou passe)", "group": "Ouvrir", "position": "SB",
               "actions": {"raise": "22+, A2s+, K2s+, Q4s+, J6s+, T6s+, 96s+, 85s+, 75s+, 64s+, 54s, A2o+, K8o+, "
                                    "Q9o+, J9o+, T9o, 98o:0.5"},
               "note": "Relance de 3 bb hors de position contre la BB. Les stratégies avancées limpent aussi une partie."},
    "bb_vs_btn": {"title": "BB face à une ouverture du BTN", "group": "Défendre", "position": "BB",
                  "actions": {"3bet": "TT+, AJs+, KQs, A5s-A2s, K9s:0.5, Q9s:0.5, J9s:0.5, 76s:0.5, 65s:0.5, AQo+, "
                                      "KJo:0.5",
                              "call": "22-99, A6s-ATs, K2s-KJs, Q5s-QJs, J7s-JTs, T7s+, 96s+, 85s+, 74s+, 64s+, "
                                      "53s+, 43s, A2o-AJo, K8o-KQo, Q9o+, J9o+, T8o+, 98o, 87o"},
                  "note": "La BB défend très large : elle a déjà 1 bb dans le pot et paie un bon prix."},
    "bb_vs_co": {"title": "BB face à une ouverture du CO", "group": "Défendre", "position": "BB",
                 "actions": {"3bet": "JJ+, AQs+, KQs:0.5, A5s-A4s, AKo, AQo:0.5",
                             "call": "22-TT, A2s-AJs, K6s-KJs, Q8s+, J8s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s, A8o-AQo, "
                                     "KTo+, QTo+, JTo"},
                 "note": "Un peu plus serré que contre le BTN."},
    "bb_vs_utg": {"title": "BB face à une ouverture UTG", "group": "Défendre", "position": "BB",
                  "actions": {"3bet": "QQ+, AKs, A5s:0.5, AKo:0.5",
                              "call": "22-JJ, A2s-AQs, K9s+, QTs+, JTs, T9s, 98s, 87s, 76s, 65s, AJo+, KQo"},
                  "note": "La range UTG est forte : on défend surtout avec des mains qui jouent bien après le flop."},
    "sb_vs_btn": {"title": "SB face à une ouverture du BTN (3-bet ou passe)", "group": "Défendre", "position": "SB",
                  "actions": {"3bet": "66+, A2s+, K9s+, Q9s+, J9s+, T9s, 98s, 87s:0.5, ATo+, KJo+, QJo:0.5"},
                  "note": "Hors de position avec la BB derrière : on évite de suivre et on 3-bet à 11-12 bb."},
    "btn_vs_co": {"title": "BTN face à une ouverture du CO", "group": "Défendre", "position": "BTN",
                  "actions": {"3bet": "TT+, AJs+, KQs, A5s-A3s, K9s:0.5, 76s:0.5, AQo+",
                              "call": "22-99, A6s-ATs, KTs-KJs, QTs+, JTs, T9s, 98s, 87s, 76s:0.5, AJo, KQo"},
                  "note": "En position : on peut suivre une partie des mains. 3-bet à environ 8 bb."},
    "btn_vs_utg": {"title": "BTN face à une ouverture UTG", "group": "Défendre", "position": "BTN",
                   "actions": {"3bet": "QQ+, AKs, A5s:0.5, AKo",
                               "call": "22-JJ, ATs-AQs, KTs+, QTs+, JTs, T9s, 98s, AQo, KQo:0.5"},
                   "note": "Contre une range forte, on suit des mains qui touchent fort (paires, suitées)."},
    "co_vs_hj": {"title": "CO face à une ouverture HJ", "group": "Défendre", "position": "CO",
                 "actions": {"3bet": "TT+, AJs+, KQs, A5s-A4s, AQo+",
                             "call": "77-99:0.5, ATs:0.5, KJs:0.5, QJs:0.5, JTs:0.5"},
                 "note": "Le BTN et les blindes restent derrière : on 3-bet plus qu'on ne suit."},
    "btn_vs_bb3b": {"title": "BTN qui a ouvert, face au 3-bet de la BB", "group": "Face au 3-bet", "position": "BTN",
                    "actions": {"4bet": "QQ+, AKs, A5s-A4s:0.5, AKo",
                                "call": "22-JJ, A2s-AQs, K9s+, QTs+, J9s+, T9s, 98s, 87s, 76s, 65s, AJo+, KQo"},
                    "note": "En position avec une range d'ouverture large : on suit beaucoup. 4-bet à environ 22 bb."},
    "co_vs_btn3b": {"title": "CO qui a ouvert, face au 3-bet du BTN", "group": "Face au 3-bet", "position": "CO",
                    "actions": {"4bet": "QQ+, AKs, A5s:0.5, AKo",
                                "call": "66-JJ, ATs-AQs, KTs+, QTs+, JTs, T9s, 98s, AQo"},
                    "note": "Hors de position : on passe davantage que depuis le BTN."},
    "utg_vs_3b": {"title": "UTG qui a ouvert, face à un 3-bet", "group": "Face au 3-bet", "position": "UTG",
                  "actions": {"4bet": "KK+, AKs, AKo:0.5", "call": "88-QQ, AQs, AJs:0.5, KQs, AKo:0.5"},
                  "note": "La range UTG est forte : on continue souvent, mais on 4-bet surtout pour la valeur."},
}


def spot_grid(spot_id: str) -> dict:
    """Grille 13×13 : pour chaque main, la fréquence de chaque action."""
    spot = SPOTS[spot_id]
    ranges = {action: parse_range(text) for action, text in spot["actions"].items()}
    cells = {}
    for cls in all_classes():
        freqs = {a: r[cls] for a, r in ranges.items() if cls in r}
        total = sum(freqs.values())
        if total > 1:  # mains présentes dans deux actions : on répartit
            freqs = {a: f / total for a, f in freqs.items()}
        if freqs:
            cells[cls] = freqs
    return {
        "id": spot_id, "title": spot["title"], "position": spot["position"], "note": spot["note"],
        "cells": cells,
        "percent": {a: round(range_percent(r), 1) for a, r in ranges.items()},
        "actions": [{"key": a, "label": ACTION_FR[a], "color": ACTION_COLOR[a]} for a in spot["actions"]],
    }


def compare_rfi(spot_id: str, hero_cells: dict[str, dict]) -> dict:
    """Écarts entre les ouvertures du héros et la range de référence (spots d'ouverture)."""
    grid = spot_grid(spot_id)
    too_loose, too_tight = [], []
    for cls in all_classes():
        ref = grid["cells"].get(cls, {}).get("raise", 0.0)
        h = hero_cells.get(cls)
        if not h or h["opp"] < 3:
            continue
        freq = h["rfi"] / h["opp"]
        gap = freq - ref
        item = {"hand": cls, "hero": round(100 * freq), "ref": round(100 * ref), "sample": h["opp"]}
        if gap >= 0.35:
            too_loose.append(item)
        elif gap <= -0.35:
            too_tight.append(item)
    key = lambda i: -abs(i["hero"] - i["ref"]) * min(i["sample"], 30)
    return {"too_loose": sorted(too_loose, key=key)[:25], "too_tight": sorted(too_tight, key=key)[:25]}


# --------------------------------------------------------------------------
# Postflop : texture du board et repères
# --------------------------------------------------------------------------

def board_texture(cards: list[str]) -> dict:
    """Classe un flop (3 cartes) : hauteur, paire, couleurs, connexité."""
    if len(cards) < 3:
        raise ValueError("il faut au moins 3 cartes (le flop)")
    flop = cards[:3]
    ranks = sorted((_R[c[0].upper()] for c in flop))  # 0 = As
    suits = [c[1].lower() for c in flop]
    values = sorted((14 - r for r in ranks), reverse=True)  # As = 14
    paired = len(set(ranks)) < 3
    suited = len(set(suits))
    span = values[0] - values[-1]
    connected = not paired and span <= 4
    # As avec deux petites cartes (A-2-3, A-4-5...) : board « haut » mais tirages de roue
    wheel = not paired and values[0] == 14 and values[1] <= 5
    high = values[0]
    tags = []
    if paired:
        kind = "pairé"
    elif suited == 1:
        kind = "monotone"
    elif high >= 13 and not connected:
        kind = "haut sec"  # A ou K haut, peu de tirages
    elif high <= 9 and connected:
        kind = "bas connecté"
    elif connected:
        kind = "haut connecté"
    else:
        kind = "moyen sec"
    if suited == 2:
        tags.append("tirage couleur possible")
    if connected:
        tags.append("tirages quinte")
    elif wheel:
        tags.append("tirages quinte (roue)")
    return {"kind": kind, "tags": tags, "high": high, "paired": paired, "suits": suited,
            "connected": connected, "flop": flop}


# Repères simplifiés, par texture, pour l'agresseur préflop en pot simplement relancé
CBET_GUIDE = {
    "haut sec": {"ip": (75, "25-33 %"), "oop": (55, "33 %"),
                 "why": "Le relanceur a beaucoup plus de mains fortes (As, Rois) : on mise souvent et petit."},
    "moyen sec": {"ip": (60, "33 %"), "oop": (40, "33-50 %"),
                  "why": "Avantage moindre : mise moyenne avec les paires, les tirages et quelques bluffs."},
    "haut connecté": {"ip": (50, "50-66 %"), "oop": (35, "50-66 %"),
                      "why": "Beaucoup de tirages des deux côtés : on mise moins souvent, mais plus gros."},
    "bas connecté": {"ip": (40, "66-75 %"), "oop": (25, "66 %"),
                     "why": "Board favorable au défenseur : on checke souvent, on mise gros avec la valeur et les tirages."},
    "pairé": {"ip": (70, "25-33 %"), "oop": (50, "33 %"),
              "why": "Peu de combinaisons touchent : petite mise très fréquente."},
    "monotone": {"ip": (45, "25-33 %"), "oop": (30, "33 %"),
                 "why": "Couleur déjà possible : petites mises, on checke beaucoup de paires moyennes."},
}

GENERAL_RULES = [
    {"theme": "Pot 3-betté", "rule": "Ranges plus fortes et pot plus gros : c-bet fréquent et plus petit (20-33 %)."},
    {"theme": "Turn", "rule": "Continuer (2e barrel) quand la carte favorise ta range (carte haute, couleur "
                              "qui rentre pour toi) ; taille 50-75 %. Checker les mains moyennes."},
    {"theme": "River", "rule": "Jeu polarisé : mises de 66-125 % avec les très bonnes mains et des bluffs "
                               "choisis (tirages ratés avec bloqueurs) ; checker les mains moyennes."},
    {"theme": "Défense face au c-bet", "rule": "Défendre (suivre ou relancer) au moins 1 − mise/(pot + mise) : "
                                               "75 % contre 33 % du pot, 67 % contre 50 %, 57 % contre 75 %."},
    {"theme": "Check-raise", "rule": "Surtout sur les boards bas et connectés, avec les deux paires, brelans "
                                     "et gros tirages : environ 10-15 % des fois, à 3 fois la mise."},
    {"theme": "Overbet", "rule": "Réservé aux spots où ta range a les nuts et pas l'adversaire (turn ou river), "
                                 "avec une range très polarisée."},
]


def mdf(bet_fraction: float) -> float:
    """Fréquence minimale de défense face à une mise de `bet_fraction` du pot."""
    return 1 - bet_fraction / (1 + bet_fraction)


def postflop_advice(cards: list[str]) -> dict:
    tex = board_texture(cards)
    guide = CBET_GUIDE[tex["kind"]]
    return {
        "texture": tex,
        "cbet": [
            {"spot": "Relanceur préflop, en position (ex. BTN contre BB)", "frequency": guide["ip"][0],
             "sizing": guide["ip"][1]},
            {"spot": "Relanceur préflop, hors de position (ex. UTG contre BTN)", "frequency": guide["oop"][0],
             "sizing": guide["oop"][1]},
        ],
        "why": guide["why"],
        "defense": [{"bet": f"{p} % du pot", "mdf": round(100 * mdf(p / 100))} for p in (25, 33, 50, 75, 100, 150)],
        "rules": GENERAL_RULES,
    }
