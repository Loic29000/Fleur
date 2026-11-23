import pytest

from fleur import install


class FakeRunner:
    """Remplace PowerShell : crée un fichier .lnk factice et note la commande."""

    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        script = cmd[-1]
        link = script.split("CreateShortcut('", 1)[1].split("')", 1)[0].replace("''", "'")
        from pathlib import Path
        Path(link).write_text("lnk", encoding="utf-8")


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(install, "desktop_dir", lambda: tmp_path / "Desktop")
    dist = tmp_path / "dist"
    (dist / "FleurAnalyse").mkdir(parents=True)
    (dist / "Fleur.exe").write_text("exe")
    (dist / "FleurAnalyse" / "FleurAnalyse.exe").write_text("exe")
    monkeypatch.setattr(install, "program_paths", lambda: {
        "hud": dist / "Fleur.exe", "analysis": dist / "FleurAnalyse" / "FleurAnalyse.exe"})
    return tmp_path


def test_create_shortcuts(fake_env):
    runner = FakeRunner()
    made = install.create_shortcuts(runner=runner)
    names = sorted(p.name for p in made)
    assert names == ["Fleur Analyse.lnk", "Fleur Analyse.lnk", "Fleur HUD.lnk", "Fleur HUD.lnk"]
    assert (install.start_menu_dir() / "Fleur HUD.lnk").is_file()
    assert (fake_env / "Desktop" / "Fleur Analyse.lnk").is_file()
    assert "$s.Arguments = 'hud'" in runner.calls[0][-1]


def test_autostart_toggle(fake_env):
    runner = FakeRunner()
    assert not install.autostart_enabled()
    assert install.set_autostart(True, runner=runner) is True and install.autostart_enabled()
    assert install.set_autostart(False) is False and not install.autostart_enabled()


def test_quotes_are_escaped():
    assert install._ps_quote("C:\\Users\\l'ami\\x") == "'C:\\Users\\l''ami\\x'"
