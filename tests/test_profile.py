import copy

import pytest

from fleur.config import DEFAULT_CONFIG
from fleur.profile import classify, classify_values


@pytest.mark.parametrize("vpip, pfr, af, expected", [
    (55, 40, 3.0, "maniaque"),
    (38, 30, 6.0, "maniaque"),
    (32, 25, 3.0, "lag"),
    (45, 12, 1.0, "fish"),
    (30, 10, 2.5, "fish"),
    (42, 30, 2.0, "lag"),  # très large mais relance beaucoup
    (48, 20, 2.0, "fish"),  # très large, relance peu
    (12, 10, 2.0, "nit"),
    (22, 18, 2.5, "tag"),
    (24, 8, 1.0, "fish"),  # passif
    (17, 7, 1.2, "nit"),  # serré passif
])
def test_rules(vpip, pfr, af, expected):
    assert classify_values(vpip, pfr, af) == expected


def totals(hands, vpip, pfr, br=20, calls=10):
    return {"hands": hands, "vpip": vpip, "pfr": pfr, "post_br": br, "post_calls": calls}


def test_min_hands_threshold_and_config_labels():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    assert classify(totals(49, 10, 8), cfg) is None
    p = classify(totals(100, 22, 18), cfg)
    assert (p.key, p.label, p.color) == ("tag", "TAG", "#4fa3ff")
    cfg["profile_min_hands"] = 20
    cfg["profiles"]["tag"] = ["Régulier", "#123456"]
    assert classify(totals(30, 7, 6), cfg).label == "Régulier"


def test_badge_on_panel():
    from fleur.hud.overlay import render_lines
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    assert "Fish" in render_lines("X", totals(200, 90, 10), cfg)
    assert "Fish" not in render_lines("X", totals(20, 18, 2), cfg)
    cfg["show_profile"] = False
    assert "Fish" not in render_lines("X", totals(200, 90, 10), cfg)
