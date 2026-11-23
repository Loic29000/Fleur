"""Journal et rapport de diagnostic.

Tout ce qui peut indiquer un souci de lecture est consigné dans
%APPDATA%\\Fleur\\diagnostic :

- mains_illisibles.txt  : mains que le lecteur n'a pas pu interpréter ;
- lignes_inconnues.txt  : lignes non reconnues (une par motif, avec exemple) ;
- incoherences.txt      : mains dont les gains ne tombent pas juste
                          (signe qu'une action a été mal lue) ;
- fenetres.txt          : titres de fenêtres vus en cherchant les tables.

`make_report()` réunit le tout (avec le journal fleur.log et la config)
dans un zip à envoyer pour analyse.
"""

from __future__ import annotations

import json
import logging
import platform
import re
import sys
import time
import zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fleur import __version__
from fleur.config import app_dir
from fleur.parser import Hand

log = logging.getLogger("fleur")

MAX_FILE_BYTES = 2_000_000
MAX_EXAMPLES_PER_PATTERN = 3


def setup_logging(console: bool = True) -> Path:
    path = app_dir() / "fleur.log"
    log.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in log.handlers):
        fh = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(fh)
    if console and sys.stderr and not any(type(h) is logging.StreamHandler for h in log.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("[fleur] %(message)s"))
        log.addHandler(sh)
    return path


def _pattern(line: str) -> str:
    """Motif d'une ligne : montants et cartes remplacés, pour regrouper."""
    line = re.sub(r"\[[^\]]*\]", "[cartes]", line)
    line = re.sub(r"[\d.,]+\s*[€$£]?", "#", line)
    return line


class Diagnostics:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or (app_dir() / "diagnostic")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.parse_errors = 0
        self.inconsistent = 0
        self.unknown_patterns: dict[str, dict] = {}
        self._windows_logged: set[str] = set()
        self._load_patterns()

    # -- fichiers --------------------------------------------------------
    def _append(self, name: str, text: str) -> None:
        path = self.dir / name
        try:
            if path.exists() and path.stat().st_size > MAX_FILE_BYTES:
                return
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
        except OSError as exc:
            log.warning("écriture diagnostic impossible (%s) : %s", name, exc)

    def _load_patterns(self) -> None:
        path = self.dir / "lignes_inconnues.json"
        if path.exists():
            try:
                self.unknown_patterns = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.unknown_patterns = {}

    def _save_patterns(self) -> None:
        data = sorted(self.unknown_patterns.items(), key=lambda kv: -kv[1]["count"])
        try:
            (self.dir / "lignes_inconnues.json").write_text(
                json.dumps(dict(data), indent=1, ensure_ascii=False), encoding="utf-8")
            lines = [f"{v['count']:>6}x  {k}\n" + "".join(f"         ex. {e}\n" for e in v["examples"])
                     for k, v in data]
            (self.dir / "lignes_inconnues.txt").write_text("".join(lines), encoding="utf-8")
        except OSError:
            pass

    # -- événements --------------------------------------------------------
    def parse_error(self, chunk: str, error: Exception) -> None:
        self.parse_errors += 1
        first = chunk.splitlines()[0][:120] if chunk else ""
        log.warning("main illisible (%s) : %s", error, first)
        self._append("mains_illisibles.txt", f"### {type(error).__name__}: {error}\n{chunk}\n\n")

    def check_hand(self, hand: Hand) -> None:
        """Contrôles de cohérence sur une main lue sans erreur."""
        if hand.unknown_lines:
            for line in hand.unknown_lines:
                pat = _pattern(line)
                entry = self.unknown_patterns.setdefault(pat, {"count": 0, "examples": []})
                entry["count"] += 1
                if len(entry["examples"]) < MAX_EXAMPLES_PER_PATTERN:
                    entry["examples"].append(f"{line}   (main {hand.hand_id})")
                    if entry["count"] == 1:
                        log.info("ligne non reconnue : %s", line)
            self._save_patterns()

        problems = consistency_problems(hand)
        if problems:
            self.inconsistent += 1
            log.warning("main %s incohérente : %s", hand.hand_id, "; ".join(problems))
            self._append("incoherences.txt", f"### {hand.hand_id} : {'; '.join(problems)}\n{hand.raw}\n\n")

    def window_search(self, table: str, matched: str | None, titles: list[str]) -> None:
        key = f"{table}|{matched}"
        if key in self._windows_logged:
            return
        self._windows_logged.add(key)
        if matched:
            log.info("table '%s' -> fenêtre '%s'", table, matched)
        else:
            log.warning("fenêtre introuvable pour la table '%s'", table)
        listing = "".join(f"    {t}\n" for t in titles)
        self._append("fenetres.txt", f"[{time.strftime('%H:%M:%S')}] table '{table}' -> "
                                     f"{matched or 'INTROUVABLE'}\n{listing}\n")

    @property
    def problem_count(self) -> int:
        return self.parse_errors + self.inconsistent


def consistency_problems(hand: Hand) -> list[str]:
    from fleur.stats import _net_results  # import local : évite un cycle

    problems = []
    acting = {a.player for a in hand.actions}
    seated = {name for name, _ in hand.seats.values()}
    strangers = acting - seated
    if strangers:
        problems.append(f"joueurs absents des sièges : {sorted(strangers)}")
    if hand.seats and not any(a.kind == "post_bb" for a in hand.actions) and hand.is_cash:
        problems.append("aucune big blind trouvée")
    if hand.button_seat is None:
        problems.append("bouton introuvable")
    if not hand.collected:
        problems.append("aucun gagnant trouvé")
    else:
        # Somme des gains = argent ajouté (ESCAPE) - rake
        total = sum(_net_results(hand).values())
        tolerance = max(0.011, (hand.bb or 0) * 0.01)
        if abs(total + hand.rake - hand.added_money) > tolerance:
            problems.append(f"gains incohérents (somme {total:+.2f}, rake {hand.rake:.2f})")
        elif hand.total_pot is not None:
            # "Total pot" Winamax = tout ce qui a été misé + ajouté, rake déduit
            invested = sum(hand.collected.values()) - total + sum(hand.uncalled.values())
            pot = invested + hand.added_money - hand.rake
            if abs(pot - hand.total_pot) > tolerance:
                problems.append(f"pot recalculé {pot:.2f} au lieu de {hand.total_pot:.2f}")
    return problems


def make_report(destination: Path, extra: dict | None = None) -> Path:
    """Crée un zip avec journal, fichiers de diagnostic, config et infos système."""
    root = app_dir()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = destination / f"fleur_diagnostic_{stamp}.zip"
    info = {
        "version": __version__,
        "python": sys.version,
        "systeme": platform.platform(),
        **(extra or {}),
    }
    try:
        from PySide6 import __version__ as qt_version
        info["pyside6"] = qt_version
    except Exception:
        pass
    try:
        from fleur.hud import win32
        info["fenetres_visibles"] = [w.title for w in win32.list_windows()]
    except Exception as exc:
        info["fenetres_visibles"] = f"erreur : {exc}"

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("infos.json", json.dumps(info, indent=2, ensure_ascii=False, default=str))
        for name in ("fleur.log", "fleur.log.1", "config.json", "layouts.json"):
            p = root / name
            if p.exists():
                zf.write(p, name)
        diag = root / "diagnostic"
        if diag.is_dir():
            for p in diag.iterdir():
                if p.is_file():
                    zf.write(p, f"diagnostic/{p.name}")
    log.info("rapport de diagnostic créé : %s", out)
    return out


def default_report_dir() -> Path:
    desktop = Path.home() / "Desktop"
    if desktop.is_dir():
        return desktop
    return app_dir()


_instance: Diagnostics | None = None


def get() -> Diagnostics:
    global _instance
    if _instance is None:
        _instance = Diagnostics()
    return _instance
