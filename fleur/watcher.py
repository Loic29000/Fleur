"""Surveillance du dossier d'historiques Winamax.

On interroge le dossier à intervalle régulier (plus fiable que les
notifications système pour des fichiers ajoutés en continu) et on ne lit
que les octets nouveaux de chaque fichier. La position de lecture est
mémorisée en base : un redémarrage reprend là où on s'était arrêté.
"""

from __future__ import annotations

import os
import re
import time
from typing import TYPE_CHECKING
from pathlib import Path

from fleur.db import Database
from fleur.parser import Hand, iter_hands

if TYPE_CHECKING:
    from fleur.diagnostics import Diagnostics

# Délai après la dernière écriture à partir duquel la dernière main d'un
# fichier est considérée comme complète même sans ligne vide finale.
SETTLE_SECONDS = 2.0


def find_history_dirs() -> list[Path]:
    """Dossiers d'historiques Winamax probables sous Windows."""
    candidates: list[Path] = []
    home = Path.home()
    roots = [home / "Documents", home / "OneDrive" / "Documents", home / "OneDrive" / "Documenten"]
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        roots.append(Path(userprofile) / "Documents")
    # Anciennes versions : Documents\Winamax Poker\accounts ; client actuel :
    # %APPDATA%\winamax\documents\accounts (sans sous-dossier "Winamax Poker").
    account_roots = [root / "Winamax Poker" / "accounts" for root in roots]
    appdata = os.environ.get("APPDATA")
    if appdata:
        wina = Path(appdata) / "winamax" / "documents"
        account_roots += [wina / "accounts", wina / "Winamax Poker" / "accounts"]
    for accounts in account_roots:
        if accounts.is_dir():
            for acc in accounts.iterdir():
                hist = acc / "history"
                if hist.is_dir() and hist not in candidates:
                    candidates.append(hist)
    return candidates


def _is_history_file(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() == ".txt" and "summary" not in name


class HistoryWatcher:
    def __init__(self, db: Database, directories: list[Path], diagnostics: "Diagnostics | None" = None,
                 include_tournaments: bool = False):
        self.db = db
        self.directories = [Path(d) for d in directories]
        self.diagnostics = diagnostics
        # Les mains de tournoi sont en jetons : par défaut on ne les mélange
        # pas aux stats de cash game.
        self.include_tournaments = include_tournaments
        self._done_sizes: dict[str, int] = {}  # taille déjà entièrement lue, par fichier

    def files(self) -> list[Path]:
        out = []
        for d in self.directories:
            if d.is_dir():
                out.extend(p for p in d.rglob("*.txt") if _is_history_file(p))
        return sorted(out)

    def poll(self) -> list[Hand]:
        """Lit les nouvelles mains de tous les fichiers ; renvoie celles insérées."""
        new_hands: list[Hand] = []
        for path in self.files():
            new_hands.extend(self.read_file(path))
        return new_hands

    def read_file(self, path: Path) -> list[Hand]:
        key = str(path)
        try:
            stat = path.stat()
        except OSError:
            return []
        if self._done_sizes.get(key) == stat.st_size:
            return []  # rien de neuf : évite une requête par fichier à chaque tour
        offset = self.db.file_offset(key)
        if stat.st_size < offset:  # fichier réécrit / tronqué
            offset = 0
        if stat.st_size == offset:
            return []
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                data = f.read()
        except OSError:
            return []

        settled = (time.time() - stat.st_mtime) >= SETTLE_SECONDS
        consumed = complete_prefix_length(data, settled)
        if consumed == 0:
            return []
        text = data[:consumed].decode("utf-8-sig", errors="replace")
        on_error = self.diagnostics.parse_error if self.diagnostics else None
        hands = iter_hands(text, on_error=on_error)
        if not self.include_tournaments:
            hands = (h for h in hands if not h.is_tournament)
        inserted = self.db.add_hands(hands)
        self.db.set_file_offset(key, offset + consumed)
        if offset + consumed == stat.st_size:
            self._done_sizes[key] = stat.st_size
        if self.diagnostics:
            for hand in inserted:
                self.diagnostics.check_hand(hand)
        return inserted


_HEADER_BYTES = re.compile(rb"^(?:\xef\xbb\xbf)?Winamax Poker - .*HandId: #", re.MULTILINE)


def complete_prefix_length(data: bytes, settled: bool) -> int:
    """Nombre d'octets de `data` contenant uniquement des mains complètes."""
    starts = [m.start() for m in _HEADER_BYTES.finditer(data)]
    if not starts:
        return 0
    last = starts[-1]
    tail = data[last:]
    last_complete = b"*** SUMMARY ***" in tail and (
        settled or tail.endswith(b"\n\n") or tail.endswith(b"\r\n\r\n")
    )
    return len(data) if last_complete else last
