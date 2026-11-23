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


def _appdata() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")


def start_menu_dir() -> Path:
    return _appdata() / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME


def startup_dir() -> Path:
    return _appdata() / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def desktop_dir() -> Path:
    return Path.home() / "Desktop"


def program_paths() -> dict[str, Path]:
    """Chemins de Fleur.exe et FleurAnalyse.exe (à côté de l'exe en cours)."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1] / "dist"
    if base.name.lower() == "fleuranalyse":  # lancé depuis dist\FleurAnalyse
        base = base.parent
    return {"hud": base / "Fleur.exe", "analysis": base / "FleurAnalyse" / "FleurAnalyse.exe"}


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
        "$s.Description = " + _ps_quote(description) + "; "
        "$s.Save()"
    )
    runner(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True,
           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return link


def create_shortcuts(desktop: bool = True, runner=subprocess.run) -> list[Path]:
    """Raccourcis vers le HUD et l'analyse dans le menu Démarrer (et sur le bureau)."""
    paths = program_paths()
    made = []
    entries = [("Fleur HUD", paths["hud"], "hud", "HUD de poker pour Winamax"),
               ("Fleur Analyse", paths["analysis"], "", "Tableau de bord et analyse de tes mains")]
    for name, target, args, desc in entries:
        if not target.is_file():
            continue
        made.append(make_shortcut(start_menu_dir() / f"{name}.lnk", target, args, desc, runner))
        if desktop:
            made.append(make_shortcut(desktop_dir() / f"{name}.lnk", target, args, desc, runner))
    return made


def autostart_link() -> Path:
    return startup_dir() / "Fleur HUD.lnk"


def autostart_enabled() -> bool:
    return autostart_link().is_file()


def set_autostart(enabled: bool, runner=subprocess.run) -> bool:
    """Lance (ou non) le HUD à l'ouverture de la session Windows."""
    link = autostart_link()
    if not enabled:
        link.unlink(missing_ok=True)
        return False
    target = program_paths()["hud"]
    if not target.is_file():
        raise FileNotFoundError(f"{target} introuvable : construis d'abord Fleur.exe")
    make_shortcut(link, target, "hud", "HUD de poker pour Winamax", runner)
    return True
