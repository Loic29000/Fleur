"""Résumé lisible d'une main pour un joueur (mains montrées à l'abattage).

Exemple : « 3-bet préflop, c-bet flop, check-call turn, check river ».
Information historique uniquement : rien ici ne conseille d'action.
"""

from __future__ import annotations

from dataclasses import dataclass

from fleur.parser import Hand
from fleur.stats import hand_counters

_STREET_FR = {"preflop": "préflop", "flop": "flop", "turn": "turn", "river": "river"}


def _preflop_words(hand: Hand, player: str) -> list[str]:
    raises = 0
    limpers = False
    words: list[str] = []
    for a in hand.actions:
        if a.street != "preflop" or a.is_post:
            continue
        if a.player == player:
            if a.kind == "raise":
                if raises == 0:
                    words.append("iso" if limpers else "open")
                else:
                    words.append(f"{raises + 2}-bet" if raises < 3 else "5-bet+")
            elif a.kind == "call":
                if raises == 0:
                    words.append("limp")
                elif raises == 1:
                    words.append("call")
                else:
                    words.append(f"call {raises + 1}-bet")
            elif a.kind in ("check", "fold"):
                words.append(a.kind)
            if a.allin and words:
                words[-1] += " (tapis)"
        if a.kind == "raise":
            raises += 1
        elif a.kind == "call" and raises == 0:
            limpers = True
    return words


def _last_aggressor(hand: Hand, street: str) -> str | None:
    last = None
    for a in hand.actions:
        if a.street == street and a.kind in ("bet", "raise"):
            last = a.player
    return last


def _street_words(hand: Hand, player: str, street: str, cbettor: str | None) -> list[str]:
    """`cbettor` : joueur qui peut faire un c-bet sur cette street (agresseur
    préflop resté agresseur sur les streets précédentes)."""
    words: list[str] = []
    bet_made = False
    for a in hand.actions:
        if a.street != street:
            continue
        if a.player == player:
            word = None
            if a.kind == "bet":
                word = "c-bet" if player == cbettor and not bet_made else "bet"
            elif a.kind == "raise":
                if words and words[-1] == "check":
                    words.pop()
                    word = "check-raise"
                else:
                    word = "raise"
            elif a.kind in ("call", "check", "fold"):
                word = a.kind
            if word:
                words.append(word + (" (tapis)" if a.allin else ""))
        if a.kind in ("bet", "raise"):
            bet_made = True
    return words


def action_line(hand: Hand, player: str) -> str:
    """Ligne d'action résumée d'un joueur sur toute la main."""
    parts: list[str] = []
    cbettor = None
    for street in ("preflop", "flop", "turn", "river"):
        words = _preflop_words(hand, player) if street == "preflop" else \
            _street_words(hand, player, street, cbettor)
        if words:
            parts.append(f"{'-'.join(words)} {_STREET_FR[street]}")
        # le c-bet reste possible tant que l'agresseur préflop mène l'action
        last = _last_aggressor(hand, street)
        cbettor = last if street == "preflop" else (cbettor if last == cbettor else None)
    return ", ".join(parts)


@dataclass
class ShownHand:
    hand_id: str
    player: str
    played_at: str | None
    cards: str
    board: str
    line: str
    net: float
    net_bb: float
    bb: float


def shown_hands(hand: Hand) -> list[ShownHand]:
    """Une entrée par joueur ayant montré ses cartes dans la main."""
    if not hand.shown:
        return []
    counters = hand_counters(hand)
    out = []
    for player, cards in hand.shown.items():
        c = counters.get(player, {})
        out.append(ShownHand(
            hand_id=hand.hand_id,
            player=player,
            played_at=hand.played_at.isoformat() if hand.played_at else None,
            cards=cards,
            board=" ".join(hand.board),
            line=action_line(hand, player),
            net=float(c.get("net", 0.0)),
            net_bb=float(c.get("net_bb", 0.0)),
            bb=hand.bb,
        ))
    return out
