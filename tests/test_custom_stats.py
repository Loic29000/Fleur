import json

import pytest

from fleur.formulas import FormulaError, compile_formula, evaluate
from fleur.stats import ALL_COUNTERS, STAT_BY_KEY, compute_all, make_custom_stat, set_custom_stats

KNOWN = frozenset(ALL_COUNTERS)


@pytest.fixture(autouse=True)
def reset_custom():
    yield
    set_custom_stats([])


def test_formula_evaluation():
    values = {"vpip": 30, "pfr": 20, "hands": 100}
    assert evaluate("vpip - pfr", values, KNOWN) == 10
    assert evaluate("(vpip + pfr) / 2", values, KNOWN) == 25
    assert evaluate("-pfr * 2 + 100", values, KNOWN) == 60
    assert evaluate("vpip / opp_3bet", values, KNOWN) == 0  # division par zéro -> 0


@pytest.mark.parametrize("expr, message", [
    ("__import__('os')", "non autorisé"),
    ("vpip.real", "non autorisé"),
    ("open('x')", "non autorisé"),
    ("vpip ** 2", "non autorisé"),
    ("toto + vpip", "inconnu"),
    ("vpip +", "illisible"),
    ("", "vide"),
])
def test_formula_rejects_anything_else(expr, message):
    with pytest.raises(FormulaError, match=message):
        compile_formula(expr, KNOWN)


def test_custom_stat_lifecycle():
    errors = set_custom_stats([
        {"key": "vmp", "label": "V-P", "num": "vpip - pfr", "den": "hands", "kind": "pct"},
        {"key": "vpip", "num": "vpip", "den": "hands"},  # clé déjà prise
        {"key": "bad", "num": "nimporte", "den": "hands"},
    ])
    assert len(errors) == 2 and "vmp" in STAT_BY_KEY
    stats = compute_all({"hands": 200, "vpip": 50, "pfr": 30})
    assert stats["vmp"].value == pytest.approx(10.0) and stats["vmp"].format("pct") == "10"
    set_custom_stats([])
    assert "vmp" not in STAT_BY_KEY and "vmp" not in compute_all({})


def test_make_custom_stat_validation():
    with pytest.raises(FormulaError, match="dénominateur"):
        make_custom_stat({"key": "x", "num": "vpip", "kind": "pct"})
    assert make_custom_stat({"key": "nb", "num": "did_3bet", "kind": "count"}).den == ""
    with pytest.raises(FormulaError, match="clé invalide"):
        make_custom_stat({"key": "Mauvaise clé", "num": "vpip", "den": "hands"})


def test_config_loads_custom_stats(tmp_path):
    from fleur.config import load_config
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"custom_stats": [
        {"key": "fvr", "label": "FvR", "num": "fold_vs_bet_r", "den": "opp_vs_bet_r", "kind": "pct"}]}),
        encoding="utf-8")
    load_config(path)
    assert compute_all({"opp_vs_bet_r": 4, "fold_vs_bet_r": 1})["fvr"].value == 25


def test_editor_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from fleur.config import DEFAULT_CONFIG, load_config
    from fleur.web.server import AnalysisApp, ApiError
    app = AnalysisApp(tmp_path / "fleur.db", dict(DEFAULT_CONFIG))
    spec = {"key": "fvr", "label": "FvR", "num": "fold_vs_bet_r", "den": "opp_vs_bet_r", "kind": "pct"}
    _, r = app.handle("POST", "/api/custom_stats/test", {}, spec)
    assert r["value"] == "-"  # base vide
    app.handle("POST", "/api/custom_stats/save", {}, spec)
    assert load_config()["custom_stats"][0]["key"] == "fvr"
    _, listing = app.handle("GET", "/api/custom_stats", {}, None)
    assert listing["stats"][0]["key"] == "fvr" and any(c["key"] == "fold_vs_bet_r" for c in listing["counters"])
    with pytest.raises(ApiError):
        app.handle("POST", "/api/custom_stats/save", {}, {**spec, "num": "import os"})
    app.handle("POST", "/api/custom_stats/delete", {}, {"key": "fvr"})
    assert load_config()["custom_stats"] == [] and "fvr" not in STAT_BY_KEY
