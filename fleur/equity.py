"""Évaluation de mains de Hold'em et calcul d'équité.

Utilisé uniquement pour l'analyse après coup (all-in EV, calculateur hors
partie) : jamais pendant une main.
"""

from __future__ import annotations

import random
from itertools import combinations
from math import comb

RANKS = "23456789TJQKA"
SUITS = "shdc"
FULL_DECK = [r + s for r in RANKS for s in SUITS]
_RANK_VALUE = {r: i + 2 for i, r in enumerate(RANKS)}

# Catégories (plus grand = meilleur)
HIGH, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL, QUADS, STRAIGHT_FLUSH = range(9)
CATEGORY_FR = ["hauteur", "paire", "double paire", "brelan", "quinte", "couleur", "full", "carré", "quinte flush"]


def parse_cards(text: str) -> list[str]:
    """'Ah Kd', 'AhKd', 'ah,kd' -> ['Ah', 'Kd'] ; '10h' accepté. Erreur si invalide."""
    t = text.replace(",", " ").replace("10", "T").strip()
    if not t:
        return []
    tokens = t.split() if " " in t else [t[i:i + 2] for i in range(0, len(t), 2)]
    out = []
    for tok in tokens:
        if len(tok) != 2 or tok[0].upper() not in RANKS or tok[1].lower() not in SUITS:
            raise ValueError(f"carte invalide : {tok!r}")
        out.append(tok[0].upper() + tok[1].lower())
    if len(set(out)) != len(out):
        raise ValueError("carte en double")
    return out


def _straight_high(mask: int) -> int:
    """Hauteur de la meilleure quinte dans un masque de rangs (bit r pour le rang r), 0 sinon."""
    if mask & (1 << 14):  # l'as compte aussi pour 1 (quinte A-2-3-4-5)
        mask |= 1 << 1
    for high in range(14, 4, -1):
        need = 0b11111 << (high - 4)
        if mask & need == need:
            return high
    return 0


def evaluate(cards: list[str]) -> tuple:
    """Valeur comparable de la meilleure main de 5 cartes parmi 5 à 7 cartes."""
    ranks = [_RANK_VALUE[c[0]] for c in cards]
    suits = [c[1] for c in cards]
    counts: dict[int, int] = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    by_suit: dict[str, list[int]] = {}
    for r, s in zip(ranks, suits):
        by_suit.setdefault(s, []).append(r)
    flush_ranks = next((rs for rs in by_suit.values() if len(rs) >= 5), None)
    if flush_ranks:
        mask = 0
        for r in flush_ranks:
            mask |= 1 << r
        sf = _straight_high(mask)
        if sf:
            return (STRAIGHT_FLUSH, sf)
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    if groups[0][1] == 4:
        quad = groups[0][0]
        kicker = max(r for r in counts if r != quad)
        return (QUADS, quad, kicker)
    if groups[0][1] == 3 and len(groups) > 1 and groups[1][1] >= 2:
        trips = groups[0][0]
        pair = max(r for r, n in counts.items() if n >= 2 and r != trips)
        return (FULL, trips, pair)
    if flush_ranks:
        return (FLUSH, *sorted(flush_ranks, reverse=True)[:5])
    mask = 0
    for r in counts:
        mask |= 1 << r
    st = _straight_high(mask)
    if st:
        return (STRAIGHT, st)
    if groups[0][1] == 3:
        trips = groups[0][0]
        kickers = sorted((r for r in counts if r != trips), reverse=True)[:2]
        return (TRIPS, trips, *kickers)
    pairs = sorted((r for r, n in counts.items() if n == 2), reverse=True)
    if len(pairs) >= 2:
        kicker = max(r for r in counts if r not in pairs[:2])
        return (TWO_PAIR, pairs[0], pairs[1], kicker)
    if pairs:
        kickers = sorted((r for r in counts if r != pairs[0]), reverse=True)[:3]
        return (PAIR, pairs[0], *kickers)
    return (HIGH, *sorted(counts, reverse=True)[:5])


def describe(cards: list[str]) -> str:
    return CATEGORY_FR[evaluate(cards)[0]]


def equity(hands: list[list[str] | None], board: list[str] | None = None, dead: list[str] | None = None,
           trials: int = 20000, exact_limit: int = 60000, seed: int | None = None) -> dict:
    """Équité de chaque main. `None` dans `hands` = main aléatoire.

    Énumération exacte si le nombre de boards à tirer est raisonnable et
    qu'aucune main n'est aléatoire, sinon simulation de `trials` tirages.
    """
    board = list(board or [])
    if not 2 <= len(hands) <= 9:
        raise ValueError("il faut de 2 à 9 joueurs")
    if len(board) > 5:
        raise ValueError("le board a au plus 5 cartes")
    known = [c for h in hands if h for c in h] + board + list(dead or [])
    if len(set(known)) != len(known):
        raise ValueError("une carte apparaît deux fois")
    for h in hands:
        if h is not None and len(h) != 2:
            raise ValueError("chaque main doit avoir 2 cartes")
    deck = [c for c in FULL_DECK if c not in set(known)]
    missing = 5 - len(board)
    n = len(hands)
    wins = [0.0] * n
    ties = [0.0] * n
    shares = [0.0] * n

    def score(full_hands: list[list[str]], full_board: list[str]) -> None:
        values = [evaluate(h + full_board) for h in full_hands]
        best = max(values)
        winners = [i for i, v in enumerate(values) if v == best]
        for i in winners:
            if len(winners) == 1:
                wins[i] += 1
            else:
                ties[i] += 1
            shares[i] += 1 / len(winners)

    randoms = [i for i, h in enumerate(hands) if h is None]
    if not randoms and comb(len(deck), missing) <= exact_limit:
        boards = 0
        for extra in combinations(deck, missing):
            score(hands, board + list(extra))  # type: ignore[arg-type]
            boards += 1
        method = "exact"
    else:
        rng = random.Random(seed)
        need = missing + 2 * len(randoms)
        for _ in range(trials):
            drawn = rng.sample(deck, need)
            full = [list(h) if h else None for h in hands]
            for k, i in enumerate(randoms):
                full[i] = drawn[missing + 2 * k: missing + 2 * k + 2]
            score(full, board + drawn[:missing])  # type: ignore[arg-type]
        boards = trials
        method = "simulation"
    return {
        "method": method, "boards": boards, "trials": boards,
        "players": [{"win": wins[i] / boards, "tie": ties[i] / boards, "equity": shares[i] / boards}
                    for i in range(n)],
    }


_NAMES = {14: "as", 13: "rois", 12: "dames", 11: "valets", 10: "dix", 9: "neuf", 8: "huit", 7: "sept",
          6: "six", 5: "cinq", 4: "quatre", 3: "trois", 2: "deux"}
_HIGH = {14: "as", 13: "roi", 12: "dame", 11: "valet", 10: "dix", 9: "neuf", 8: "huit", 7: "sept",
         6: "six", 5: "cinq", 4: "quatre", 3: "trois", 2: "deux"}


def _de(rank: int) -> str:
    name = _NAMES[rank]
    return f"d'{name}" if name[0] in "aeiou" else f"de {name}"


def describe_full(cards: list[str]) -> str:
    """'paire de dames', 'full aux rois par les neuf', 'couleur hauteur as'..."""
    v = evaluate(cards)
    cat = v[0]
    if cat == STRAIGHT_FLUSH:
        return "quinte flush royale" if v[1] == 14 else f"quinte flush hauteur {_HIGH[v[1]]}"
    if cat == QUADS:
        return f"carré {_de(v[1])}"
    if cat == FULL:
        return f"full aux {_NAMES[v[1]]} par les {_NAMES[v[2]]}"
    if cat == FLUSH:
        return f"couleur hauteur {_HIGH[v[1]]}"
    if cat == STRAIGHT:
        return f"quinte hauteur {_HIGH[v[1]]}"
    if cat == TRIPS:
        return f"brelan {_de(v[1])}"
    if cat == TWO_PAIR:
        return f"double paire {_NAMES[v[1]]} et {_NAMES[v[2]]}"
    if cat == PAIR:
        return f"paire {_de(v[1])}"
    return f"hauteur {_HIGH[v[1]]}"
