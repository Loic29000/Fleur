"""Raccourcis Windows (bureau, menu Démarrer) et lancement au démarrage de Windows.

Les raccourcis .lnk sont créés par l'objet COM WScript.Shell via PowerShell,
présent sur tous les Windows récents (aucune dépendance supplémentaire).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "Fleur"
OLD_SHORTCUTS = ("Fleur HUD.lnk", "Fleur Analyse.lnk")  # avant la fusion en une seule application


def _appdata() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")


def start_menu_dir() -> Path:
    return _appdata() / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME


def startup_dir() -> Path:
    return _appdata() / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def desktop_dir() -> Path:
    return Path.home() / "Desktop"


def program_path() -> Path:
    """Chemin de Fleur.exe (l'exe en cours, ou dist\\Fleur\\Fleur.exe en développement)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    return Path(__file__).resolve().parents[1] / "dist" / "Fleur" / "Fleur.exe"


def _ps_quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def make_shortcut(link: Path, target: Path, arguments: str = "", description: str = "",
                  runner=subprocess.run) -> Path:
    link.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + _ps_quote(link) + "); "
        "$s.TargetPath = " + _ps_quote(target) + "; "
        "$s.Arguments = " + _ps_quote(arguments) + "; "
        "$s.WorkingDirectory = " + _ps_quote(target.parent) + "; "
        "$s.IconLocation = " + _ps_quote(f"{target},0") + "; "
        "$s.Description = " + _ps_quote(description) + "; "
        "$s.Save()"
    )
    runner(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True,
           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return link


def create_shortcuts(desktop: bool = True, runner=subprocess.run) -> list[Path]:
    """Raccourci « Fleur » dans le menu Démarrer (et sur le bureau)."""
    target = program_path()
    if not target.is_file():
        raise FileNotFoundError(f"{target} introuvable : construis d'abord Fleur avec build_exe.bat")
    remove_old_shortcuts()
    desc = "Fleur : HUD, tableau de bord et analyse de tes mains Winamax"
    made = [make_shortcut(start_menu_dir() / "Fleur.lnk", target, "", desc, runner)]
    if desktop:
        made.append(make_shortcut(desktop_dir() / "Fleur.lnk", target, "", desc, runner))
    return made


def remove_old_shortcuts() -> list[Path]:
    removed = []
    for folder in (desktop_dir(), start_menu_dir()):
        for name in OLD_SHORTCUTS:
            link = folder / name
            if link.is_file():
                link.unlink()
                removed.append(link)
    return removed


def migrate_shortcuts(runner=subprocess.run) -> bool:
    """Remplace les anciens raccourcis « Fleur HUD » / « Fleur Analyse » par « Fleur »."""
    had_desktop = any((desktop_dir() / n).is_file() for n in OLD_SHORTCUTS)
    had_any = had_desktop or any((start_menu_dir() / n).is_file() for n in OLD_SHORTCUTS)
    if not had_any or not program_path().is_file():
        return False
    create_shortcuts(desktop=had_desktop, runner=runner)
    old_autostart = startup_dir() / "Fleur HUD.lnk"
    if old_autostart.is_file():
        old_autostart.unlink()
        set_autostart(True, runner)
    return True


def autostart_link() -> Path:
    return startup_dir() / "Fleur.lnk"


def autostart_enabled() -> bool:
    return autostart_link().is_file() or (startup_dir() / "Fleur HUD.lnk").is_file()


def set_autostart(enabled: bool, runner=subprocess.run) -> bool:
    """Lance (ou non) Fleur à l'ouverture de la session Windows, icône seule."""
    link = autostart_link()
    (startup_dir() / "Fleur HUD.lnk").unlink(missing_ok=True)
    if not enabled:
        link.unlink(missing_ok=True)
        return False
    target = program_path()
    if not target.is_file():
        raise FileNotFoundError(f"{target} introuvable : construis d'abord Fleur avec build_exe.bat")
    make_shortcut(link, target, "hud --sans-fenetre", "Fleur (HUD de poker)", runner)
    return True
