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


def test_fit_table_keeps_winamax_proportions():
    from fleur.hud.overlay import fit_table
    # capture réelle : 1368x1031 -> table pleine fenêtre ; 1789x1027 -> bandes latérales
    assert all(abs(a - b) < 0.5 for a, b in zip(fit_table(0, 0, 1368, 1031, 1.327), (0, 0, 1368, 1031)))
    x, y, w, h = fit_table(0, 0, 1789, 1027, 1.327)
    assert (y, h) == (0, 1027) and abs(x - 213) < 2 and abs(w - 1363) < 2
    # pseudo BLV26 : x=371 sur la petite fenêtre, x=585 sur la grande
    assert abs(x + 371 / 1368 * w - 585) < 4
    x, y, w, h = fit_table(10, 20, 800, 1000, 1.327)
    assert (x, w) == (10, 800) and abs(h - 800 / 1.327) < 1 and y > 20
    assert fit_table(0, 0, 1789, 1027, 0) == (0, 0, 1789, 1027)
