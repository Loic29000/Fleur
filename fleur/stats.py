"""Calcul des statistiques façon PokerTracker 4.

Pour chaque main et chaque joueur, on produit des *compteurs* (opportunités
et réalisations). Les stats affichées sont des ratios de sommes de compteurs
sur toutes les mains stockées.
"""

from __future__ import annotations

from dataclasses import dataclass

from fleur.parser import Hand

# Compteurs entiers stockés par (main, joueur)
INT_COUNTERS = [
    "hands",
    "vpip",
    "pfr",
    "opp_unopened", "did_rfi", "did_limp",
    "opp_3bet", "did_3bet", "did_cold_call",
    "opp_squeeze", "did_squeeze",
    "opp_f3bet", "fold_3bet", "call_3bet",
    "opp_4bet", "did_4bet",
    "opp_steal", "did_steal",
    "opp_fsteal", "fold_steal", "threebet_steal",
    "opp_cbet_f", "did_cbet_f",
    "opp_fcbet_f", "fold_cbet_f", "raise_cbet_f",
    "opp_cbet_t", "did_cbet_t",
    "opp_fcbet_t", "fold_cbet_t",
    "opp_donk_f", "did_donk_f",
    "opp_xr_f", "did_xr_f",
    "post_br", "post_calls", "post_folds",
    "saw_flop", "wtsd", "wsd", "wwsf",
]
FLOAT_COUNTERS = ["net", "net_bb"]
ALL_COUNTERS = INT_COUNTERS + FLOAT_COUNTERS


@dataclass(frozen=True)
class StatDef:
    key: str
    label: str
    num: str
    den: str
    kind: str = "pct"  # pct | ratio | count | bb100
    description: str = ""


# Mêmes stats que le HUD par défaut de PokerTracker 4 (+ les plus courantes du popup)
STAT_DEFS: list[StatDef] = [
    StatDef("hands", "Mains", "hands", "", "count", "Nombre de mains"),
    StatDef("vpip", "VPIP", "vpip", "hands", "pct", "Met volontairement de l'argent préflop"),
    StatDef("pfr", "PFR", "pfr", "hands", "pct", "Relance préflop"),
    StatDef("3bet", "3Bet", "did_3bet", "opp_3bet", "pct", "3-bet préflop"),
    StatDef("f3bet", "F3B", "fold_3bet", "opp_f3bet", "pct", "Fold face à un 3-bet après avoir ouvert"),
    StatDef("4bet", "4Bet", "did_4bet", "opp_4bet", "pct", "4-bet préflop"),
    StatDef("rfi", "RFI", "did_rfi", "opp_unopened", "pct", "Ouverture en relance (raise first in)"),
    StatDef("limp", "Limp", "did_limp", "opp_unopened", "pct", "Limp (open limp)"),
    StatDef("cc", "CC", "did_cold_call", "opp_3bet", "pct", "Cold call d'une relance"),
    StatDef("sqz", "Sqz", "did_squeeze", "opp_squeeze", "pct", "Squeeze"),
    StatDef("steal", "ATS", "did_steal", "opp_steal", "pct", "Tentative de vol (CO/BTN/SB)"),
    StatDef("fsteal", "FvS", "fold_steal", "opp_fsteal", "pct", "Fold aux blindes face à un vol"),
    StatDef("3bsteal", "3BvS", "threebet_steal", "opp_fsteal", "pct", "3-bet aux blindes face à un vol"),
    StatDef("cbet", "CB", "did_cbet_f", "opp_cbet_f", "pct", "Continuation bet flop"),
    StatDef("fcbet", "FCB", "fold_cbet_f", "opp_fcbet_f", "pct", "Fold face au c-bet flop"),
    StatDef("rcbet", "RCB", "raise_cbet_f", "opp_fcbet_f", "pct", "Relance du c-bet flop"),
    StatDef("cbet_t", "CB T", "did_cbet_t", "opp_cbet_t", "pct", "Continuation bet turn"),
    StatDef("fcbet_t", "FCB T", "fold_cbet_t", "opp_fcbet_t", "pct", "Fold face au c-bet turn"),
    StatDef("donk", "Donk", "did_donk_f", "opp_donk_f", "pct", "Donk bet flop"),
    StatDef("xr", "XR", "did_xr_f", "opp_xr_f", "pct", "Check-raise flop"),
    StatDef("af", "AF", "post_br", "post_calls", "ratio", "Facteur d'agression postflop (mises+relances)/suivis"),
    StatDef("afq", "AFq", "post_br", "post_br+post_calls+post_folds", "pct", "Fréquence d'agression postflop"),
    StatDef("wtsd", "WTSD", "wtsd", "saw_flop", "pct", "Va à l'abattage après avoir vu le flop"),
    StatDef("wsd", "W$SD", "wsd", "wtsd", "pct", "Gagne à l'abattage"),
    StatDef("wwsf", "WWSF", "wwsf", "saw_flop", "pct", "Gagne la main après avoir vu le flop"),
    StatDef("bb100", "BB/100", "net_bb", "hands", "bb100", "Gains en big blinds pour 100 mains"),
    StatDef("net", "Gains", "net", "", "money", "Gains nets"),
]
STAT_BY_KEY = {s.key: s for s in STAT_DEFS}


@dataclass
class StatValue:
    value: float | None
    num: float
    den: float

    def format(self, kind: str) -> str:
        if kind == "count":
            return str(int(self.num))
        if kind == "money":
            return f"{self.num:+.2f}"
        if self.value is None:
            return "∞" if kind == "ratio" and self.num > 0 else "-"
        if kind == "ratio":
            return f"{self.value:.1f}"
        return f"{self.value:.0f}"


def compute_stat(totals: dict[str, float], stat: StatDef) -> StatValue:
    num = totals.get(stat.num, 0.0)
    den = sum(totals.get(part, 0.0) for part in stat.den.split("+")) if stat.den else 0.0
    if stat.kind in ("count", "money"):
        return StatValue(num, num, den)
    if not den:
        return StatValue(None, num, den)
    if stat.kind == "ratio":
        return StatValue(num / den, num, den)
    return StatValue(100.0 * num / den, num, den)


def compute_all(totals: dict[str, float]) -> dict[str, StatValue]:
    return {s.key: compute_stat(totals, s) for s in STAT_DEFS}


# --------------------------------------------------------------------------
# Positions
# --------------------------------------------------------------------------

def positions(hand: Hand) -> dict[str, str]:
    """Attribue BTN/SB/BB/CO/HJ/... aux joueurs de la main."""
    players = hand.players
    result: dict[str, str] = {}
    if not players:
        return result
    sb = next((a.player for a in hand.actions if a.kind == "post_sb"), None)
    bb = next((a.player for a in hand.actions if a.kind == "post_bb"), None)

    seat_order = sorted((hand.seat_of(p) or 0, p) for p in players)
    ordered = [p for _, p in seat_order]
    btn = None
    if hand.button_seat is not None:
        # le bouton, ou le premier joueur actif avant lui (bouton mort)
        before = [p for s, p in seat_order if s <= hand.button_seat]
        btn = before[-1] if before else ordered[-1]

    if len(players) == 2:
        if btn:
            result[btn] = "BTN"
        for p in players:
            if p != btn:
                result[p] = "BB"
        if sb and sb not in result:
            result[sb] = "SB"
        return result

    if sb:
        result[sb] = "SB"
    if bb:
        result[bb] = "BB"
    if btn and btn not in result:
        result[btn] = "BTN"
    if btn:
        i = ordered.index(btn)
        rotated = ordered[i + 1:] + ordered[: i + 1]  # commence après le bouton
    else:
        rotated = ordered
    middle = [p for p in rotated if p not in result]
    labels = ["CO", "HJ", "LJ", "MP", "UTG+2", "UTG+1"]
    for idx, p in enumerate(reversed(middle)):
        result[p] = labels[idx] if idx < len(labels) else "UTG"
    if middle and len(middle) > 1:
        result[middle[0]] = "UTG"
    return result


STEAL_POSITIONS = {"CO", "BTN", "SB"}


# --------------------------------------------------------------------------
# Compteurs par main
# --------------------------------------------------------------------------

def hand_counters(hand: Hand) -> dict[str, dict[str, float]]:
    players = hand.players
    c: dict[str, dict[str, float]] = {p: {k: 0 for k in ALL_COUNTERS} for p in players}
    if not players:
        return c
    pos = positions(hand)
    for p in players:
        c[p]["hands"] = 1

    pfa = _preflop(hand, c, pos)
    folded_pre = {a.player for a in hand.actions if a.street == "preflop" and a.kind == "fold"}
    flop_players = [p for p in players if p not in folded_pre] if len(hand.board) >= 3 else []
    for p in flop_players:
        c[p]["saw_flop"] = 1

    _postflop(hand, c, pfa, flop_players)

    folded = {a.player for a in hand.actions if a.kind == "fold"}
    remaining = [p for p in players if p not in folded]
    showdown = len(remaining) >= 2
    for p in players:
        won = hand.collected.get(p, 0.0) > 0
        if showdown and p in remaining and c[p]["saw_flop"]:
            c[p]["wtsd"] = 1
            if won:
                c[p]["wsd"] = 1
        if c[p]["saw_flop"] and won:
            c[p]["wwsf"] = 1

    for p, net in _net_results(hand).items():
        c[p]["net"] = round(net, 4)
        c[p]["net_bb"] = round(net / hand.bb, 4) if hand.bb else 0.0
    return c


def _preflop(hand: Hand, c, pos) -> str | None:
    raisers: list[str] = []
    callers_since_raise: list[str] = []
    limpers: list[str] = []
    acted: set[str] = set()
    steal_attempt = False  # dernière relance = vol depuis CO/BTN/SB sans suiveur
    flags: dict[str, set[str]] = {p: set() for p in c}

    def once(p: str, key: str):
        if key not in flags[p]:
            flags[p].add(key)
            c[p][key] = 1

    for a in hand.actions:
        if a.street != "preflop" or a.is_post:
            continue
        p = a.player
        if p not in c:
            continue
        rc = len(raisers)
        first_action = p not in acted
        acted.add(p)

        if rc == 0 and not limpers and first_action:
            once(p, "opp_unopened")
            if pos.get(p) in STEAL_POSITIONS:
                once(p, "opp_steal")
                if a.kind == "raise":
                    once(p, "did_steal")
            if a.kind == "raise":
                once(p, "did_rfi")
            elif a.kind == "call":
                once(p, "did_limp")
        elif rc == 0 and a.kind == "call" and first_action:
            once(p, "did_limp")

        if rc == 1 and p != raisers[0] and p not in raisers:
            if "opp_3bet" not in flags[p]:
                once(p, "opp_3bet")
                if a.kind == "raise":
                    once(p, "did_3bet")
                elif a.kind == "call" and p not in limpers:
                    once(p, "did_cold_call")
            if callers_since_raise and "opp_squeeze" not in flags[p] and p not in callers_since_raise:
                once(p, "opp_squeeze")
                if a.kind == "raise":
                    once(p, "did_squeeze")
            if steal_attempt and pos.get(p) in ("SB", "BB") and "opp_fsteal" not in flags[p]:
                once(p, "opp_fsteal")
                if a.kind == "fold":
                    once(p, "fold_steal")
                elif a.kind == "raise":
                    once(p, "threebet_steal")

        if rc == 2 and "opp_4bet" not in flags[p] and raisers[-1] != p:
            once(p, "opp_4bet")
            if a.kind == "raise":
                once(p, "did_4bet")
            if p == raisers[0]:
                once(p, "opp_f3bet")
                if a.kind == "fold":
                    once(p, "fold_3bet")
                elif a.kind == "call":
                    once(p, "call_3bet")

        if a.kind in ("call", "raise", "bet"):
            c[p]["vpip"] = 1
        if a.kind in ("raise", "bet"):
            c[p]["pfr"] = 1
            steal_attempt = (rc == 0 and not limpers and pos.get(p) in STEAL_POSITIONS)
            raisers.append(p)
            callers_since_raise = []
        elif a.kind == "call":
            if rc == 0:
                limpers.append(p)
            else:
                callers_since_raise.append(p)
                steal_attempt = False
    return raisers[-1] if raisers else None


def _postflop(hand: Hand, c, pfa: str | None, flop_players: list[str]) -> str | None:
    cbet_flop = False
    for street in ("flop", "turn", "river"):
        actions = [a for a in hand.actions if a.street == street and not a.is_post and a.player in c]
        bet_made = False
        cbet_active = False
        pfa_acted = False
        checked: set[str] = set()
        faced_cbet: set[str] = set()
        xr_opp: set[str] = set()
        cbet_this_street = False
        for a in actions:
            p = a.player
            # agression
            if a.kind in ("bet", "raise"):
                c[p]["post_br"] += 1
            elif a.kind == "call":
                c[p]["post_calls"] += 1
            elif a.kind == "fold":
                c[p]["post_folds"] += 1

            if street == "flop":
                if pfa and p == pfa and not pfa_acted:
                    pfa_acted = True
                    if not bet_made:
                        c[p]["opp_cbet_f"] = 1
                        if a.kind == "bet":
                            c[p]["did_cbet_f"] = 1
                            cbet_active = True
                            cbet_this_street = True
                elif pfa and p != pfa and not pfa_acted and not bet_made and pfa in flop_players:
                    if not c[p]["opp_donk_f"]:
                        c[p]["opp_donk_f"] = 1
                        if a.kind == "bet":
                            c[p]["did_donk_f"] = 1
                elif cbet_active and p != pfa and p not in faced_cbet:
                    faced_cbet.add(p)
                    c[p]["opp_fcbet_f"] = 1
                    if a.kind == "fold":
                        c[p]["fold_cbet_f"] = 1
                    elif a.kind == "raise":
                        c[p]["raise_cbet_f"] = 1
                # check-raise
                if p in checked and bet_made and p not in xr_opp:
                    xr_opp.add(p)
                    c[p]["opp_xr_f"] = 1
                    if a.kind == "raise":
                        c[p]["did_xr_f"] = 1

            elif street == "turn" and cbet_flop:
                if p == pfa and not pfa_acted:
                    pfa_acted = True
                    if not bet_made:
                        c[p]["opp_cbet_t"] = 1
                        if a.kind == "bet":
                            c[p]["did_cbet_t"] = 1
                            cbet_active = True
                elif cbet_active and p != pfa and p not in faced_cbet:
                    faced_cbet.add(p)
                    c[p]["opp_fcbet_t"] = 1
                    if a.kind == "fold":
                        c[p]["fold_cbet_t"] = 1

            if a.kind == "check":
                checked.add(p)
            if a.kind in ("bet", "raise"):
                if a.kind == "raise":
                    cbet_active = False
                bet_made = True
        if street == "flop":
            cbet_flop = cbet_this_street
    return pfa if cbet_flop else None


def _net_results(hand: Hand) -> dict[str, float]:
    """Gain net de chaque joueur : encaissé + mises rendues - investi."""
    invested: dict[str, float] = {p: 0.0 for p in hand.players}
    for street in ("preflop", "flop", "turn", "river"):
        street_put: dict[str, float] = {}
        for a in hand.actions:
            if a.street != street or a.player not in invested:
                continue
            if a.kind in ("post_ante", "post_dead"):
                invested[a.player] += a.amount
            elif a.kind in ("post_sb", "post_bb", "post_other", "call", "bet"):
                street_put[a.player] = street_put.get(a.player, 0.0) + a.amount
            elif a.kind == "raise":
                street_put[a.player] = max(street_put.get(a.player, 0.0), a.to)
        for p, v in street_put.items():
            invested[p] += v

    # Winamax n'écrit pas de ligne "Uncalled bet" : la mise non suivie est
    # incluse dans "collected" (vérifié sur de vraies mains, avec et sans rake).
    # On ne rembourse donc que ce qu'une ligne "Uncalled bet" annonce.
    refund = hand.uncalled
    return {
        p: hand.collected.get(p, 0.0) + refund.get(p, 0.0) - invested[p]
        for p in invested
    }
