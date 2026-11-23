"""Données de rejeu d'une main (revue de mains), étape par étape.

Chaque étape donne le pot, le tapis restant et la mise en cours de chaque
joueur après l'action, pour que la page de revue puisse les dessiner.
"""

from __future__ import annotations

import re

from fleur.parser import Hand
from fleur.stats import hand_counters, positions

_VERBS = {
    "fold": "passe", "check": "check", "call": "suit", "bet": "mise", "raise": "relance à",
    "post_sb": "petite blinde", "post_bb": "grosse blinde", "post_ante": "ante",
    "post_other": "blinde", "post_dead": "blinde morte",
}
_BOARD_AT = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}


def replay(hand: Hand) -> dict:
    pos = positions(hand)
    counters = hand_counters(hand)
    stacks = {name: stack for _, (name, stack) in hand.seats.items()}
    players = []
    for seat, (name, stack) in sorted(hand.seats.items()):
        cards = hand.shown.get(name) or (hand.hero_cards if name == hand.hero else None)
        players.append({
            "seat": seat, "name": name, "stack": stack, "position": pos.get(name, ""),
            "cards": cards.split() if cards else [], "hero": name == hand.hero,
            "button": seat == hand.button_seat, "net": counters.get(name, {}).get("net", 0.0),
            "sitting_out": name not in counters,
        })

    pot = hand.added_money
    steps = [{"street": "preflop", "text": "Début de la main", "pot": round(pot, 2),
              "stacks": dict(stacks), "bets": {}, "board": 0, "player": None}]
    for street in ("preflop", "flop", "turn", "river"):
        bets: dict[str, float] = {}
        acts = [a for a in hand.actions if a.street == street]
        if street != "preflop" and len(hand.board) >= _BOARD_AT[street]:
            shown = hand.board[:_BOARD_AT[street]]
            steps.append({"street": street, "text": f"{street.capitalize()} : {' '.join(shown)}",
                          "pot": round(pot, 2), "stacks": dict(stacks), "bets": {},
                          "board": _BOARD_AT[street], "player": None})
        for a in acts:
            before = bets.get(a.player, 0.0)
            if a.kind == "raise":
                put = max(a.to - before, 0.0)
            elif a.kind in ("call", "bet", "post_sb", "post_bb", "post_other", "post_ante", "post_dead"):
                put = a.amount
            else:
                put = 0.0
            if a.kind not in ("post_ante", "post_dead"):
                bets[a.player] = before + put
            pot += put
            stacks[a.player] = stacks.get(a.player, 0.0) - put
            verb = _VERBS.get(a.kind, a.kind)
            amount = a.to if a.kind == "raise" else a.amount
            text = f"{a.player} {verb}" + (f" {amount:.2f} €" if amount and a.kind not in ("fold", "check") else "")
            if a.allin:
                text += " (tapis)"
            steps.append({"street": street, "text": text, "pot": round(pot, 2),
                          "stacks": {k: round(v, 2) for k, v in stacks.items()},
                          "bets": {k: round(v, 2) for k, v in bets.items()},
                          "board": _BOARD_AT[street] if street != "preflop" else 0, "player": a.player})

    final = dict(stacks)
    for name, amount in hand.collected.items():
        final[name] = final.get(name, 0.0) + amount
    winners = ", ".join(f"{n} gagne {v:.2f} €" for n, v in hand.collected.items())
    steps.append({"street": "showdown", "text": winners or "Fin de la main", "pot": 0.0,
                  "stacks": {k: round(v, 2) for k, v in final.items()}, "bets": {},
                  "board": len(hand.board), "player": None, "reveal": True})
    return {
        "hand_id": hand.hand_id, "table": hand.table, "max_seats": hand.max_seats,
        "stakes": f"{hand.sb:g}/{hand.bb:g} €", "bb": hand.bb,
        "played_at": hand.played_at.isoformat() if hand.played_at else None,
        "board": hand.board, "players": players, "steps": steps,
        "total_pot": hand.total_pot, "rake": hand.rake, "hero": hand.hero,
    }


def anonymize(hand: Hand) -> str:
    """Texte de la main avec les pseudos remplacés (Héros, Joueur1, Joueur2...)."""
    names = [name for _, (name, _) in sorted(hand.seats.items())]
    mapping, k = {}, 1
    for name in names:
        if name == hand.hero:
            mapping[name] = "Heros"
        else:
            mapping[name] = f"Joueur{k}"
            k += 1
    text = hand.raw
    for name in sorted(names, key=len, reverse=True):
        text = re.sub(rf"(?<![\w.]){re.escape(name)}(?![\w])", mapping[name], text)
    return text
