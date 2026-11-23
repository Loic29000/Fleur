"""Positions des panneaux autour de la table.

Les positions sont relatives à la zone cliente de la table (0..1) et
indexées par *siège visuel* : 0 = en bas au centre (le héros), puis dans
le sens des aiguilles d'une montre.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

DEFAULT_LAYOUTS: dict[str, list[list[float]]] = {
    "2": [[0.42, 0.74], [0.42, 0.06]],
    "3": [[0.42, 0.74], [0.05, 0.25], [0.78, 0.25]],
    "4": [[0.42, 0.74], [0.04, 0.42], [0.42, 0.06], [0.80, 0.42]],
    "5": [[0.42, 0.74], [0.04, 0.55], [0.18, 0.08], [0.66, 0.08], [0.80, 0.55]],
    "6": [[0.42, 0.74], [0.04, 0.58], [0.06, 0.16], [0.42, 0.04], [0.78, 0.16], [0.80, 0.58]],
    "8": [[0.42, 0.76], [0.10, 0.68], [0.02, 0.36], [0.16, 0.06], [0.42, 0.03],
          [0.68, 0.06], [0.82, 0.36], [0.74, 0.68]],
    "9": [[0.42, 0.76], [0.14, 0.70], [0.02, 0.44], [0.08, 0.14], [0.32, 0.03],
          [0.56, 0.03], [0.80, 0.14], [0.84, 0.44], [0.72, 0.70]],
    "10": [[0.46, 0.76], [0.22, 0.74], [0.03, 0.54], [0.03, 0.22], [0.24, 0.03],
           [0.48, 0.03], [0.72, 0.03], [0.84, 0.22], [0.84, 0.54], [0.68, 0.74]],
}


class Layouts:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, list[list[float]]] = {k: [list(p) for p in v] for k, v in DEFAULT_LAYOUTS.items()}
        if path.exists():
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                for key, positions in saved.items():
                    self.data[key] = positions
            except (OSError, json.JSONDecodeError):
                pass

    def position(self, max_seats: int, visual_index: int) -> tuple[float, float]:
        layout = self.data.get(str(max_seats)) or self._fallback(max_seats)
        x, y = layout[visual_index % len(layout)]
        return x, y

    def set_position(self, max_seats: int, visual_index: int, x: float, y: float) -> None:
        key = str(max_seats)
        layout = self.data.get(key) or self._fallback(max_seats)
        while len(layout) < max_seats:
            layout.append([0.42, 0.42])
        layout[visual_index % max_seats] = [round(x, 4), round(y, 4)]
        self.data[key] = layout
        self.save()

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    @staticmethod
    def _fallback(max_seats: int) -> list[list[float]]:
        out = []
        for i in range(max_seats):
            t = 2 * math.pi * i / max_seats  # départ en bas, sens horaire à l'écran
            out.append([round(0.42 - 0.40 * math.sin(t), 4), round(0.40 + 0.36 * math.cos(t), 4)])
        return out


def visual_index(seat: int, hero_seat: int | None, max_seats: int, hero_at_bottom: bool) -> int:
    """Siège Winamax (1..N) -> siège visuel (0 = bas)."""
    if hero_at_bottom and hero_seat is not None:
        return (seat - hero_seat) % max_seats
    return (seat - 1) % max_seats
