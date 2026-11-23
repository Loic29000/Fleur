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


def test_popup_always_fits_on_screen():
    from fleur.hud.overlay import fit_popup
    screen = (0, 0, 1366, 1040)  # zone utile de l'écran (barre des tâches exclue)
    # panneau en bas de l'écran (cas de la capture) : le popup passe au-dessus
    x, y, w, h = fit_popup((765, 770, 140, 60), (300, 500), screen)
    assert (w, h) == (300, 500) and y == 770 - 500 - 2
    # place suffisante en dessous : le popup reste sous le panneau
    x, y, w, h = fit_popup((765, 100, 140, 60), (300, 600), screen)
    assert y == 162 and y + h <= 1040
    # trop haut pour l'écran : réduit (il défilera) et collé en haut
    x, y, w, h = fit_popup((100, 300, 140, 60), (300, 2000), screen)
    assert y == 4 and h == 1040 - 8
    # bord droit : décalé vers la gauche pour rester visible
    x, y, w, h = fit_popup((1300, 100, 140, 60), (300, 200), screen)
    assert x + w <= 1366 - 4
