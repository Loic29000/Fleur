import json

from fleur.hud.layouts import DEFAULT_LAYOUTS, Layouts, visual_index


def test_only_modified_formats_are_saved(tmp_path):
    path = tmp_path / "layouts.json"
    lay = Layouts(path)
    lay.set_position(6, 2, 0.5, 0.5)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert list(saved) == ["6"]
    # les autres formats suivent les valeurs par défaut du code
    assert Layouts(path).position(5, 1) == tuple(DEFAULT_LAYOUTS["5"][1])
    assert Layouts(path).position(6, 2) == (0.5, 0.5)


def test_hero_at_bottom_clockwise():
    # héros au siège 4 d'une 5-max : siège 5 à sa gauche (visuel 1), siège 3 à sa droite (visuel 4)
    assert visual_index(4, 4, 5, True) == 0
    assert visual_index(5, 4, 5, True) == 1
    assert visual_index(1, 4, 5, True) == 2
    assert visual_index(3, 4, 5, True) == 4
