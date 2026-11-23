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


_LABELS = {
    "fold": "Passe", "check": "Check", "call": "Suit", "bet": "Mise", "raise": "Relance",
    "post_sb": "Petite blinde", "post_bb": "Grosse blinde", "post_ante": "Ante",
    "post_other": "Blinde", "post_dead": "Blinde morte",
}
_STREET_FR = {"preflop": "Préflop", "flop": "Flop", "turn": "Turn", "river": "River"}


def replay(hand: Hand) -> dict:
    """Étapes de rejeu. À chaque étape :
    - `pot` : le pot central (mises des streets précédentes, ramassées) ;
    - `bets` : ce que chaque joueur a misé sur la street en cours (devant lui) ;
    - `stacks` : tapis restants ; `folded` : joueurs couchés ;
    - `revealed` : joueurs dont les cartes sont visibles (héros toujours, les
      autres à l'abattage) ; `winners` : gains à la dernière étape."""
    from fleur.equity import describe_full as describe
    pos = positions(hand)
    counters = hand_counters(hand)
    stacks = {name: stack for _, (name, stack) in hand.seats.items()}
    players = []
    for seat, (name, stack) in sorted(hand.seats.items()):
        cards = hand.shown.get(name) or (hand.hero_cards if name == hand.hero else None)
        players.append({
            "seat": seat, "name": name, "stack": stack, "position": pos.get(name, ""),
            "cards": cards.split() if cards else [], "hero": name == hand.hero,
            "button": seat == hand.button_seat, "net": round(counters.get(name, {}).get("net", 0.0), 2),
            "sitting_out": name not in counters,
        })

    pot = hand.added_money
    bets: dict[str, float] = {}
    folded: list[str] = []
    revealed = [hand.hero] if hand.hero else []
    steps: list[dict] = []

    def add(kind: str, street: str, text: str, player: str | None = None, label: str = "",
            amount: float = 0.0, board: int = 0, **extra) -> None:
        steps.append({
            "kind": kind, "street": street, "text": text, "player": player, "label": label,
            "amount": round(amount, 2), "pot": round(pot, 2),
            "bets": {k: round(v, 2) for k, v in bets.items() if v > 0},
            "stacks": {k: round(v, 2) for k, v in stacks.items()},
            "folded": list(folded), "revealed": list(revealed), "board": board, **extra,
        })

    add("start", "preflop", f"Début de la main — {hand.table}, {hand.sb:g}/{hand.bb:g} €")
    board_n = 0
    for street in ("preflop", "flop", "turn", "river"):
        acts = [a for a in hand.actions if a.street == street]
        if street != "preflop":
            if len(hand.board) < _BOARD_AT[street]:
                break
            # les mises de la street précédente rejoignent le pot central
            pot += sum(bets.values())
            bets = {}
            board_n = _BOARD_AT[street]
            new_cards = hand.board[_BOARD_AT[street] - (3 if street == "flop" else 1):board_n]
            add("street", street, f"{_STREET_FR[street]} : {' '.join(new_cards)}", board=board_n)
        for a in acts:
            before = bets.get(a.player, 0.0)
            if a.kind == "raise":
                put = max(a.to - before, 0.0)
            elif a.kind in ("call", "bet", "post_sb", "post_bb", "post_other", "post_ante", "post_dead"):
                put = a.amount
            else:
                put = 0.0
            if a.kind in ("post_ante", "post_dead"):
                pot += put  # argent mort : directement au pot
            else:
                bets[a.player] = before + put
            stacks[a.player] = stacks.get(a.player, 0.0) - put
            if a.kind == "fold":
                folded.append(a.player)
            label = _LABELS.get(a.kind, a.kind)
            shown_amount = a.to if a.kind == "raise" else a.amount
            if a.kind == "raise":
                label = f"Relance à {shown_amount:.2f} €"
            elif shown_amount and a.kind not in ("fold", "check"):
                label = f"{label} {shown_amount:.2f} €"
            if a.allin:
                label += " (tapis)"
            add("post" if a.is_post else "action", street, f"{a.player} : {label}", a.player, label,
                put, board_n, action=a.kind, allin=a.allin)

    pot += sum(bets.values())
    bets = {}
    remaining = [p["name"] for p in players if not p["sitting_out"] and p["name"] not in folded]
    showdown = [n for n in remaining if n in hand.shown]
    if len(showdown) >= 2:
        revealed = sorted(set(revealed) | set(showdown))
        full = hand.board if len(hand.board) == 5 else None
        hands_desc = {n: describe(hand.shown[n].split() + full) for n in showdown} if full else {}
        add("showdown", "showdown", "Abattage : " + ", ".join(
            f"{n} montre {hand.shown[n]}" + (f" ({hands_desc[n]})" if n in hands_desc else "") for n in showdown),
            board=len(hand.board), descriptions=hands_desc)
    winners = {n: round(v, 2) for n, v in hand.collected.items()}
    final = dict(stacks)
    for name, amount in winners.items():
        final[name] = final.get(name, 0.0) + amount
    pot_before = pot
    pot = 0.0
    stacks = final
    text = ", ".join(f"{n} gagne {v:.2f} €" for n, v in winners.items()) or "Fin de la main"
    if hand.rake:
        text += f" (rake {hand.rake:.2f} €)"
    add("win", "fin", text, board=len(hand.board), winners=winners, pot_won=round(pot_before, 2))
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
