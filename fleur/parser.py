"""Lecture des historiques de mains Winamax.

Un fichier d'historique Winamax contient une suite de mains, chacune
commençant par une ligne du type :

    Winamax Poker - CashGame - HandId: #123-45-678 - Holdem no limit (0.01€/0.02€) - 2026/11/23 20:30:45 UTC

Le lecteur est volontairement tolérant (symboles monétaires, virgules,
noms avec espaces) pour encaisser les petites variations de format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterator

HEADER_RE = re.compile(r"^Winamax Poker - .*HandId: #", re.MULTILINE)

_HEADER_PARSE = re.compile(
    r"^Winamax Poker - (?P<kind>.+?) - HandId: #(?P<id>[\w-]+) - "
    r"(?P<game>.+?) \((?P<stakes>[^)]*)\) - (?P<date>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"
)
_TABLE_RE = re.compile(
    r"^Table: '(?P<name>.+)' (?P<max>\d+)-max.*?(?:Seat #(?P<button>\d+) is the button)?\s*$"
)
_SEAT_RE = re.compile(r"^Seat (?P<seat>\d+): (?P<name>.+) \((?P<stack>[^,)]+)[^)]*\)\s*$")
_DEALT_RE = re.compile(r"^Dealt to (?P<name>.+?) \[(?P<cards>[^\]]+)\]")
_STREET_RE = re.compile(r"^\*\*\* (?P<street>[A-Z /-]+?) \*\*\*(?P<rest>.*)$")
_ACTION_RE = re.compile(
    r"^(?P<name>.+?) (?P<verb>folds|checks|calls|bets|raises|"
    r"posts small blind|posts big blind|posts ante|posts straddle|posts dead blind)"
    r"(?: (?P<amt>[^\s]+))?(?: to (?P<to>[^\s]+))?(?P<allin> and is all-in)?"
    r"(?P<oop> out of position)?\s*$"
)
# ESCAPE : argent ajouté au pot par Winamax avant la main
_ADDED_RE = re.compile(r"^Escape to Pot: total (?P<amt>\S+)\s*$")
_COLLECT_RE = re.compile(r"^(?P<name>.+?) collected (?P<amt>[^\s]+) from")
_SHOWS_RE = re.compile(r"^(?P<name>.+?) shows \[(?P<cards>[^\]]+)\]")
_UNCALLED_RE = re.compile(r"^Uncalled bet \((?P<amt>[^)]+)\) returned to (?P<name>.+?)\s*$")
_SUMMARY_WON_RE = re.compile(r"^Seat \d+: (?P<name>.+?)(?: \([^)]*\))? (?:showed \[[^\]]*\] and )?won (?P<amt>[^\s]+)")
_CARDS_RE = re.compile(r"\[([^\]]+)\]")
_POT_RE = re.compile(r"^Total pot (?P<pot>\S+)(?: \| (?:Rake (?P<rake>\S+)|No rake))?")
# Sections dont les lignes non reconnues sont sans conséquence pour les stats
_IGNORED_SECTIONS = {"summary", "showdown"}

STREETS = ("preflop", "flop", "turn", "river")
_STREET_NAMES = {
    "PRE-FLOP": "preflop",
    "PREFLOP": "preflop",
    "FLOP": "flop",
    "TURN": "turn",
    "RIVER": "river",
    "SHOW DOWN": "showdown",
    "SHOWDOWN": "showdown",
    "SUMMARY": "summary",
    "ANTE/BLINDS": "blinds",
}


def parse_amount(text: str | None) -> float:
    """Convertit '1,234.50€', '€0.02', '0,02 €' ou '2€' en float."""
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d.,]", "", text)
    if not cleaned:
        return 0.0
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")  # séparateur de milliers
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


@dataclass
class Action:
    street: str  # preflop, flop, turn, river
    player: str
    # fold, check, call, bet, raise, post_sb, post_bb, post_ante,
    # post_other (blinde vivante hors position, straddle), post_dead (blinde morte)
    kind: str
    amount: float = 0.0  # montant ajouté (call/bet) ou relance (raise "X to Y" -> X)
    to: float = 0.0  # pour raise : total de la mise sur la street
    allin: bool = False

    @property
    def is_post(self) -> bool:
        return self.kind.startswith("post_")


@dataclass
class Hand:
    hand_id: str
    kind: str = ""
    game: str = ""
    table: str = ""
    max_seats: int = 6
    button_seat: int | None = None
    sb: float = 0.0
    bb: float = 0.0
    played_at: datetime | None = None
    seats: dict[int, tuple[str, float]] = field(default_factory=dict)
    hero: str | None = None
    hero_cards: str | None = None
    actions: list[Action] = field(default_factory=list)
    board: list[str] = field(default_factory=list)
    collected: dict[str, float] = field(default_factory=dict)
    shown: dict[str, str] = field(default_factory=dict)
    uncalled: dict[str, float] = field(default_factory=dict)
    # Chez Winamax, "Total pot" est net du rake et inclut les mises non suivies
    total_pot: float | None = None
    rake: float = 0.0
    added_money: float = 0.0  # "Escape to Pot" (ESCAPE)
    play_money: bool = False  # "Table: '...' 5-max (play money)"
    unknown_lines: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def is_cash(self) -> bool:
        """Cash game classique ou ESCAPE (cash game « fast fold » de Winamax)."""
        kind = self.kind.lower().replace(" ", "")
        return "cashgame" in kind or kind.startswith("escape")

    @property
    def is_tournament(self) -> bool:
        return self.kind.lower().startswith("tournament")

    @property
    def players(self) -> list[str]:
        """Joueurs ayant participé à la main, dans l'ordre des sièges."""
        acting = {a.player for a in self.actions}
        return [name for _, (name, _) in sorted(self.seats.items()) if name in acting]

    def seat_of(self, player: str) -> int | None:
        for seat, (name, _) in self.seats.items():
            if name == player:
                return seat
        return None

    def streets_seen(self) -> set[str]:
        streets = {"preflop"}
        if len(self.board) >= 3:
            streets.add("flop")
        if len(self.board) >= 4:
            streets.add("turn")
        if len(self.board) >= 5:
            streets.add("river")
        return streets


class ParseError(ValueError):
    pass


def split_hands(text: str) -> list[str]:
    """Découpe le contenu d'un fichier en blocs de texte, un par main."""
    text = text.replace("\ufeff", "")
    starts = [m.start() for m in HEADER_RE.finditer(text)]
    chunks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunks.append(text[start:end].strip())
    return [c for c in chunks if c]


def _resolve_name(raw_name: str, known: list[str]) -> str:
    return raw_name if raw_name in known or not known else _closest(raw_name, known)


def _closest(raw_name: str, known: list[str]) -> str:
    # Les noms sont repris tels quels dans les actions ; on garde ce filet
    # de sécurité pour les espaces en trop éventuels.
    stripped = raw_name.strip()
    for name in known:
        if name.strip() == stripped:
            return name
    return raw_name


def parse_hand(text: str) -> Hand:
    lines = [line.rstrip("\r") for line in text.strip().splitlines()]
    if not lines:
        raise ParseError("main vide")
    header = _HEADER_PARSE.match(lines[0].lstrip("﻿"))
    if not header:
        raise ParseError(f"en-tête non reconnu : {lines[0][:80]!r}")

    hand = Hand(hand_id=header["id"], kind=header["kind"], game=header["game"], raw=text.strip())
    stakes = [parse_amount(s) for s in header["stakes"].split("/") if s.strip()]
    if len(stakes) >= 2:
        hand.sb, hand.bb = stakes[-2], stakes[-1]
    elif stakes:
        hand.bb = stakes[0]
        hand.sb = stakes[0] / 2
    try:
        hand.played_at = datetime.strptime(header["date"], "%Y/%m/%d %H:%M:%S")
    except ValueError:
        hand.played_at = None

    section = "header"
    known: list[str] = []
    summary_won: dict[str, float] = {}

    for line in lines[1:]:
        if not line.strip():
            continue
        street_m = _STREET_RE.match(line)
        if street_m:
            section = _STREET_NAMES.get(street_m["street"].strip(), street_m["street"].strip().lower())
            if section in ("flop", "turn", "river"):
                groups = _CARDS_RE.findall(street_m["rest"])
                cards = " ".join(groups).split()
                if len(cards) > len(hand.board):
                    hand.board = cards
            continue

        if section == "header":
            table_m = _TABLE_RE.match(line)
            if table_m:
                hand.table = table_m["name"]
                hand.max_seats = int(table_m["max"])
                hand.play_money = "(play money)" in line
                if table_m["button"]:
                    hand.button_seat = int(table_m["button"])
                continue
            seat_m = _SEAT_RE.match(line)
            if seat_m:
                name = seat_m["name"]
                hand.seats[int(seat_m["seat"])] = (name, parse_amount(seat_m["stack"]))
                known.append(name)
                continue
            added_m = _ADDED_RE.match(line)
            if added_m:
                hand.added_money += parse_amount(added_m["amt"])
                continue

        if section == "summary":
            won_m = _SUMMARY_WON_RE.match(line)
            if won_m:
                name = _resolve_name(won_m["name"], known)
                summary_won[name] = summary_won.get(name, 0.0) + parse_amount(won_m["amt"])
            board_m = re.match(r"^Board: \[([^\]]+)\]", line)
            if board_m and not hand.board:
                hand.board = board_m.group(1).split()
            pot_m = _POT_RE.match(line)
            if pot_m:
                hand.total_pot = parse_amount(pot_m["pot"])
                hand.rake = parse_amount(pot_m["rake"])
            continue

        dealt_m = _DEALT_RE.match(line)
        if dealt_m:
            hand.hero = _resolve_name(dealt_m["name"], known)
            hand.hero_cards = dealt_m["cards"]
            continue

        collect_m = _COLLECT_RE.match(line)
        if collect_m:
            name = _resolve_name(collect_m["name"], known)
            hand.collected[name] = hand.collected.get(name, 0.0) + parse_amount(collect_m["amt"])
            continue

        shows_m = _SHOWS_RE.match(line)
        if shows_m:
            hand.shown[_resolve_name(shows_m["name"], known)] = shows_m["cards"]
            continue

        uncalled_m = _UNCALLED_RE.match(line)
        if uncalled_m:
            name = _resolve_name(uncalled_m["name"], known)
            hand.uncalled[name] = hand.uncalled.get(name, 0.0) + parse_amount(uncalled_m["amt"])
            continue

        action_m = _ACTION_RE.match(line)
        if action_m:
            street = section if section in STREETS else "preflop"
            hand.actions.append(_make_action(street, action_m, known))
            continue

        if section not in _IGNORED_SECTIONS:
            hand.unknown_lines.append(line)

    if not hand.collected and summary_won:
        hand.collected = summary_won
    if not hand.table:
        raise ParseError(f"main {hand.hand_id} : ligne 'Table:' introuvable")
    return hand


def _make_action(street: str, m: re.Match, known: list[str]) -> Action:
    verb = m["verb"]
    player = _resolve_name(m["name"], known)
    amount = parse_amount(m["amt"])
    to = parse_amount(m["to"])
    kind = {
        "folds": "fold",
        "checks": "check",
        "calls": "call",
        "bets": "bet",
        "raises": "raise",
        "posts small blind": "post_sb",
        "posts big blind": "post_bb",
        "posts ante": "post_ante",
        "posts straddle": "post_other",
        "posts dead blind": "post_other",
    }[verb]
    if m["oop"]:
        # Blindes payées en arrivant à la table ("out of position"). Winamax
        # compte les deux dans le total "raises X to Y" du joueur : on les
        # cumule donc dans sa mise de la street, comme une blinde vivante.
        kind = "post_other"
    if kind == "raise" and not to:
        to = amount
    return Action(street=street, player=player, kind=kind, amount=amount, to=to, allin=bool(m["allin"]))


def iter_hands(text: str, on_error: Callable[[str, Exception], None] | None = None) -> Iterator[Hand]:
    """Parse toutes les mains d'un texte. Les mains illisibles sont ignorées
    et signalées à `on_error(texte, erreur)`."""
    for chunk in split_hands(text):
        try:
            yield parse_hand(chunk)
        except Exception as exc:  # une main corrompue ne doit rien bloquer
            if on_error:
                on_error(chunk, exc)
