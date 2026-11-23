from pathlib import Path

import pytest

from fleur import install


class FakeRunner:
    """Remplace PowerShell : crée un fichier .lnk factice et note la commande."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        link = cmd[-1].split("CreateShortcut('", 1)[1].split("')", 1)[0].replace("''", "'")
        Path(link).write_text("lnk", encoding="utf-8")


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(install, "desktop_dir", lambda: tmp_path / "Desktop")
    exe = tmp_path / "dist" / "Fleur" / "Fleur.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("exe")
    monkeypatch.setattr(install, "program_path", lambda: exe)
    (tmp_path / "Desktop").mkdir()
    return tmp_path


def test_create_shortcuts(fake_env):
    runner = FakeRunner()
    made = install.create_shortcuts(runner=runner)
    assert sorted(p.name for p in made) == ["Fleur.lnk", "Fleur.lnk"]
    assert (install.start_menu_dir() / "Fleur.lnk").is_file() and (fake_env / "Desktop" / "Fleur.lnk").is_file()
    assert "IconLocation" in runner.calls[0][-1]


def test_autostart_toggle(fake_env):
    runner = FakeRunner()
    assert not install.autostart_enabled()
    assert install.set_autostart(True, runner=runner) is True and install.autostart_enabled()
    assert "$s.Arguments = 'hud --sans-fenetre'" in runner.calls[-1][-1]
    assert install.set_autostart(False) is False and not install.autostart_enabled()


def test_old_shortcuts_are_migrated(fake_env):
    runner = FakeRunner()
    desktop = fake_env / "Desktop"
    for name in install.OLD_SHORTCUTS:
        (desktop / name).write_text("old")
    install.startup_dir().mkdir(parents=True)
    (install.startup_dir() / "Fleur HUD.lnk").write_text("old")
    assert install.migrate_shortcuts(runner=runner) is True
    assert sorted(p.name for p in desktop.iterdir()) == ["Fleur.lnk"]
    assert (install.startup_dir() / "Fleur.lnk").is_file() and not (install.startup_dir() / "Fleur HUD.lnk").exists()
    assert install.migrate_shortcuts(runner=runner) is False  # plus rien à migrer


def test_quotes_are_escaped():
    assert install._ps_quote("C:\\Users\\l'ami\\x") == "'C:\\Users\\l''ami\\x'"
