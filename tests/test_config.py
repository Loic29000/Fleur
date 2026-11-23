import json

from fleur.config import DEFAULT_CONFIG, load_config
from fleur.stats import compute_all


def test_old_config_gets_new_color_rules(tmp_path):
    path = tmp_path / "config.json"
    old = {"colors": {"vpip": [[50, "#000000"]]}, "show_hero": True}
    path.write_text(json.dumps(old), encoding="utf-8")
    cfg = load_config(path)
    assert cfg["colors"]["vpip"] == [[50, "#000000"]]  # réglage perso conservé
    assert cfg["colors"]["cbet"] == DEFAULT_CONFIG["colors"]["cbet"]  # nouvelle règle ajoutée
    assert cfg["show_hero"] is True and cfg["include_play_money"] is False


def test_every_hud_and_popup_stat_has_a_color():
    keys = {k for line in DEFAULT_CONFIG["hud_lines"] for k in line} | set(DEFAULT_CONFIG["popup_stats"])
    missing = keys - set(DEFAULT_CONFIG["colors"]) - {"hands", "net"}
    assert missing == set()


def test_color_for_thresholds():
    import copy
    from fleur.hud.overlay import color_for
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    stats = compute_all({"hands": 20, "vpip": 10, "pfr": 4})
    assert color_for("vpip", stats["vpip"], 20, cfg) == "#ff6b6b"  # 50 % : très large
    assert color_for("pfr", stats["pfr"], 20, cfg) == "#ffd84a"  # 20 % : seuil exclu -> jaune
    assert color_for("vpip", stats["vpip"], 5, cfg) == "#e8e8e8"  # trop peu de mains : neutre
