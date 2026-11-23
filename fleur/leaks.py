"""Détection de fuites : compare les stats du héros à des fourchettes de
référence de cash game 6-max et produit des alertes priorisées.

Analyse a posteriori de l'historique (hors jeu) : aucune recommandation
n'est faite pendant une main.
"""

from __future__ import annotations

from dataclasses import dataclass

from fleur.stats import STAT_BY_KEY, compute_all


@dataclass(frozen=True)
class Reference:
    stat: str
    low: float
    high: float
    weight: float  # importance de la stat dans le classement des alertes
    position: str | None = None  # None = toutes positions
    min_sample: int = 50  # opportunités minimales pour juger


# Fourchettes indicatives pour le cash game 6-max micro/basses limites.
REFERENCES: list[Reference] = [
    Reference("vpip", 21, 28, 2.0, min_sample=200),
    Reference("pfr", 17, 23, 2.0, min_sample=200),
    Reference("3bet", 6, 10, 2.0),
    Reference("f3bet", 45, 55, 3.0),
    Reference("4bet", 3, 8, 1.0),
    Reference("limp", 0, 3, 1.5),
    Reference("cc", 4, 10, 1.0),
    Reference("steal", 35, 45, 1.5),
    Reference("fsteal", 30, 45, 3.0, position="BB"),
    Reference("fsteal", 65, 80, 1.5, position="SB"),
    Reference("rfi", 13, 18, 1.5, position="UTG"),
    Reference("rfi", 17, 23, 1.5, position="HJ"),
    Reference("rfi", 25, 32, 2.0, position="CO"),
    Reference("rfi", 40, 52, 2.5, position="BTN"),
    Reference("rfi", 30, 45, 1.5, position="SB"),
    Reference("cbet", 50, 65, 2.0),
    Reference("fcbet", 40, 55, 2.0),
    Reference("cbet_t", 45, 60, 1.0),
    Reference("af", 2.0, 3.5, 1.5, min_sample=100),
    Reference("wtsd", 25, 31, 1.5, min_sample=200),
    Reference("wsd", 50, 57, 1.5, min_sample=100),
    Reference("wwsf", 45, 52, 1.5, min_sample=200),
]

_NAMES = {
    "vpip": "VPIP", "pfr": "PFR", "3bet": "3-bet", "f3bet": "fold au 3-bet", "4bet": "4-bet",
    "limp": "open limp", "cc": "cold call", "steal": "tentative de vol", "fsteal": "fold face au vol",
    "rfi": "ouverture (RFI)", "cbet": "c-bet flop", "fcbet": "fold face au c-bet flop",
    "cbet_t": "c-bet turn", "af": "facteur d'agression", "wtsd": "WTSD (va à l'abattage)",
    "wsd": "W$SD (gagne à l'abattage)", "wwsf": "WWSF (gagne après le flop)",
}


@dataclass
class Leak:
    ref: Reference
    value: float
    sample: int
    score: float

    @property
    def direction(self) -> str:
        return "trop élevé" if self.value > self.ref.high else "trop bas"

    @property
    def severity(self) -> str:
        return "forte" if self.score >= 3 else "moyenne" if self.score >= 1.5 else "faible"

    @property
    def message(self) -> str:
        name = _NAMES.get(self.ref.stat, self.ref.stat)
        where = f" en {self.ref.position}" if self.ref.position else ""
        fmt = (lambda v: f"{v:.2f}") if STAT_BY_KEY[self.ref.stat].kind == "ratio" else (lambda v: f"{v:.0f} %")
        rng = f"{fmt(self.ref.low)}–{fmt(self.ref.high)}".replace(" %–", "–")
        return (f"{name[0].upper()}{name[1:]}{where} {self.direction} : {fmt(self.value)} "
                f"contre {rng} ({self.sample} occasions)")


def find_leaks(totals: dict[str, float], by_position: dict[str, dict[str, float]] | None = None,
               references: list[Reference] | None = None) -> list[Leak]:
    """Alertes triées de la plus importante à la moins importante."""
    by_position = by_position or {}
    leaks: list[Leak] = []
    for ref in references or REFERENCES:
        source = by_position.get(ref.position) if ref.position else totals
        if not source:
            continue
        sv = compute_all(source)[ref.stat]
        sample = int(sv.den)
        if sv.value is None or sample < ref.min_sample:
            continue
        if ref.low <= sv.value <= ref.high:
            continue
        width = max(ref.high - ref.low, 1e-9)
        distance = (sv.value - ref.high) if sv.value > ref.high else (ref.low - sv.value)
        # l'écart compte en largeurs de fourchette ; les gros échantillons pèsent un peu plus
        confidence = min(1.0, sample / (4 * ref.min_sample)) * 0.5 + 0.5
        leaks.append(Leak(ref, sv.value, sample, ref.weight * distance / width * confidence))
    return sorted(leaks, key=lambda leak: leak.score, reverse=True)
