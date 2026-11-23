"""Classement automatique des joueurs (fish, nit, TAG, LAG, maniaque).

Calculé uniquement à partir des stats passées (VPIP, PFR, AF, nombre de
mains) : c'est une étiquette descriptive, pas un conseil de jeu.
"""

from __future__ import annotations

from dataclasses import dataclass

from fleur.stats import compute_all

# Couleurs par défaut des badges (modifiables via la clé de config "profiles")
DEFAULT_PROFILES = {
    "maniaque": ["Maniaque", "#d16bff"],
    "lag": ["LAG", "#ffa94d"],
    "fish": ["Fish", "#ff6b6b"],
    "nit": ["Nit", "#9aa5b1"],
    "tag": ["TAG", "#4fa3ff"],
}


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    color: str


def classify_values(vpip: float, pfr: float, af: float | None) -> str:
    """Règles simples pour le cash game 6-max (pourcentages, AF en ratio)."""
    ratio = pfr / vpip if vpip else 0.0
    if vpip >= 45 and pfr >= 30 or vpip >= 35 and pfr >= 25 and af is not None and af >= 5:
        return "maniaque"
    if vpip >= 28 and pfr >= 20 and ratio >= 0.6:
        return "lag"
    if vpip >= 28 and ratio < 0.6 or vpip >= 40:
        return "fish"
    if vpip < 15:
        return "nit"
    if ratio < 0.5:
        # 15-28 % de VPIP mais très peu de relances : passif. Assez large,
        # c'est un fish ; plutôt serré, un nit.
        return "fish" if vpip >= 22 else "nit"
    return "tag"


def classify(totals: dict[str, float], cfg: dict) -> Profile | None:
    """Profil du joueur, ou None si l'échantillon est trop petit."""
    hands = totals.get("hands", 0)
    if hands < cfg.get("profile_min_hands", 50):
        return None
    stats = compute_all(totals)
    vpip = stats["vpip"].value or 0.0
    pfr = stats["pfr"].value or 0.0
    af = stats["af"].value if stats["af"].den else None
    key = classify_values(vpip, pfr, af)
    label, color = (cfg.get("profiles") or {}).get(key) or DEFAULT_PROFILES[key]
    return Profile(key, label, color)
