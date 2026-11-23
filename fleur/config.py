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
    "colors": {
        "vpip": [[15, "#4fa3ff"], [25, "#7ddc6f"], [35, "#ffd84a"], [999, "#ff6b6b"]],
        "pfr": [[10, "#4fa3ff"], [20, "#7ddc6f"], [28, "#ffd84a"], [999, "#ff6b6b"]],
        "3bet": [[4, "#4fa3ff"], [9, "#7ddc6f"], [13, "#ffd84a"], [999, "#ff6b6b"]],
        "af": [[1.5, "#4fa3ff"], [3, "#7ddc6f"], [4.5, "#ffd84a"], [999, "#ff6b6b"]],
        "f3bet": [[40, "#ff6b6b"], [60, "#7ddc6f"], [999, "#4fa3ff"]],
        "fcbet": [[35, "#ff6b6b"], [55, "#7ddc6f"], [999, "#4fa3ff"]],
    },
    # Nombre minimum de mains avant de colorer les stats
    "min_hands_for_colors": 30,
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
}


def config_path() -> Path:
    return app_dir() / "config.json"


def load_config(path: Path | None = None) -> dict:
    path = path or config_path()
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
            cfg.update(user)
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
