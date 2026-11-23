"""Configuration utilisateur (fichier JSON modifiable à la main)."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path


def app_dir() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    path = root / "Fleur"
    path.mkdir(parents=True, exist_ok=True)
    return path


B, G, Y, R = "#4fa3ff", "#7ddc6f", "#ffd84a", "#ff6b6b"  # bleu, vert, jaune, rouge

DEFAULT_CONFIG: dict = {
    # Dossiers d'historiques ; vide = détection automatique
    "history_dirs": [],
    # Base de données ; vide = %APPDATA%/Fleur/fleur.db
    "database": "",
    # Afficher aussi un panneau sur son propre siège
    "show_hero": False,
    # Placer le héros en bas de la table (comme le client Winamax par défaut)
    "hero_at_bottom": True,
    # Lignes du panneau : clés de stats (voir `python -m fleur stats --list`)
    "hud_lines": [
        ["vpip", "pfr", "3bet", "af", "hands"],
        ["f3bet", "steal", "fsteal", "cbet", "fcbet"],
        ["wtsd", "wsd", "wwsf", "bb100"],
    ],
    # Stats détaillées du popup (double-clic sur un panneau)
    "popup_stats": [
        "hands", "vpip", "pfr", "rfi", "limp", "cc", "3bet", "f3bet", "4bet", "sqz",
        "steal", "fsteal", "3bsteal", "cbet", "fcbet", "rcbet", "cbet_t", "fcbet_t",
        "donk", "xr", "af", "afq", "wtsd", "wsd", "wwsf", "bb100", "net",
    ],
    # Couleurs : [seuil max (exclu), couleur]. La dernière s'applique au-delà.
    # Code : bleu = serré/passif, vert = standard, jaune = large/agressif,
    # rouge = très large/très agressif. Pour les stats de fold, rouge = ne
    # lâche presque jamais, bleu = lâche beaucoup.
    "colors": {
        "vpip": [[15, B], [25, G], [35, Y], [999, R]],
        "pfr": [[10, B], [20, G], [28, Y], [999, R]],
        "3bet": [[4, B], [9, G], [13, Y], [999, R]],
        "4bet": [[1.5, B], [4, G], [7, Y], [999, R]],
        "rfi": [[15, B], [28, G], [38, Y], [999, R]],
        "limp": [[3, G], [10, Y], [999, R]],
        "cc": [[5, B], [12, G], [20, Y], [999, R]],
        "sqz": [[3, B], [8, G], [13, Y], [999, R]],
        "steal": [[25, B], [40, G], [55, Y], [999, R]],
        "3bsteal": [[5, B], [10, G], [16, Y], [999, R]],
        "cbet": [[45, B], [65, G], [80, Y], [999, R]],
        "cbet_t": [[35, B], [55, G], [70, Y], [999, R]],
        "rcbet": [[5, B], [12, G], [20, Y], [999, R]],
        "donk": [[5, G], [12, Y], [999, R]],
        "xr": [[5, B], [12, G], [20, Y], [999, R]],
        "af": [[1.5, B], [3, G], [4.5, Y], [999, R]],
        "afq": [[30, B], [45, G], [55, Y], [999, R]],
        "wtsd": [[22, B], [30, G], [36, Y], [999, R]],
        "wwsf": [[40, B], [50, G], [56, Y], [999, R]],
        "f3bet": [[40, R], [60, G], [999, B]],
        "fsteal": [[55, R], [75, G], [999, B]],
        "fcbet": [[35, R], [55, G], [999, B]],
        "fcbet_t": [[35, R], [55, G], [999, B]],
        "wsd": [[45, R], [55, G], [999, B]],
        "bb100": [[0, R], [999, G]],
    },
    # Étiquettes proposées au clic droit sur un panneau : clé -> [texte, couleur]
    "player_tags": {
        "fish": ["Fish", "#ff6b6b"],
        "reg": ["Reg", "#4fa3ff"],
        "nit": ["Nit", "#9aa5b1"],
        "lag": ["LAG", "#ffa94d"],
        "maniaque": ["Maniaque", "#d16bff"],
    },
    # Nombre de mains montrées à l'abattage listées dans le popup
    "shown_hands_count": 8,
    # Nombre minimum de mains avant de colorer les stats
    "min_hands_for_colors": 10,
    "font_size": 9,
    "opacity": 0.85,
    "poll_interval_ms": 1000,
    # Texte à chercher dans le titre de la fenêtre en plus du nom de la table
    "window_title_contains": "",
    # Importer aussi les mains de tournoi (jetons) : désactivé pour ne pas
    # fausser les stats et gains de cash game
    "include_tournaments": False,
    # Importer aussi les tables en jetons fictifs (play money)
    "include_play_money": False,
    # Proportions (largeur/hauteur) de la fenêtre de table Winamax quand la
    # table la remplit exactement ; 0 = positions relatives à toute la fenêtre
    "table_aspect_ratio": 1.327,
}


def config_path() -> Path:
    return app_dir() / "config.json"


def load_config(path: Path | None = None) -> dict:
    path = path or config_path()
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
            for key, value in user.items():
                # Dictionnaires (couleurs) : on complète avec les nouvelles
                # clés par défaut au lieu de les remplacer entièrement.
                if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                    cfg[key].update(value)
                else:
                    cfg[key] = value
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[fleur] config illisible ({exc}), valeurs par défaut utilisées")
    else:
        save_config(cfg, path)
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    path = path or config_path()
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def database_path(cfg: dict) -> Path:
    return Path(cfg["database"]) if cfg.get("database") else app_dir() / "fleur.db"
