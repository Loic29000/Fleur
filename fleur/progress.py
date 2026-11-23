"""Objectifs de progression et comparaison de périodes (analyse après coup)."""

from __future__ import annotations

from fleur.db import Database
from fleur.leaks import find_leaks
from fleur.stats import STAT_BY_KEY, STAT_DEFS, compute_stat

MIN_WEEK_SAMPLE = 10  # occasions minimales pour afficher une semaine


def _value(totals: dict[str, float], stat: str) -> tuple[float | None, float]:
    sd = STAT_BY_KEY[stat]
    sv = compute_stat(totals, sd)
    sample = sv.den if sd.den else totals.get("hands", 0)
    return sv.value, sample


def _status(value: float | None, low: float | None, high: float | None) -> str:
    if value is None:
        return "pas assez de mains"
    if low is not None and value < low:
        return "trop bas"
    if high is not None and value > high:
        return "trop élevé"
    return "atteint"


def goals_report(db: Database, hero: str, weeks: int = 26) -> list[dict]:
    out = []
    for g in db.goals():
        if g["stat"] not in STAT_BY_KEY:
            continue
        sd = STAT_BY_KEY[g["stat"]]
        overall, sample = _value(db.period_totals(hero, position=g["position"]), g["stat"])
        series = []
        weekly = db.weekly_totals(hero, g["position"])
        for week, totals in weekly[-weeks:]:
            v, n = _value(totals, g["stat"])
            series.append({"week": week, "value": v if n >= MIN_WEEK_SAMPLE else None, "sample": n})
        # 4 dernières semaines regroupées, pour juger la tendance récente
        recent = {}
        for _, totals in weekly[-4:]:
            for k, v in totals.items():
                recent[k] = recent.get(k, 0) + v
        recent_value, recent_n = _value(recent, g["stat"]) if recent else (None, 0)
        if recent_n < MIN_WEEK_SAMPLE:
            recent_value = None
        out.append({
            **g, "label": sd.label, "description": sd.description, "kind": sd.kind,
            "value": overall, "sample": sample, "recent": recent_value, "recent_sample": recent_n,
            "status": _status(recent_value if recent_value is not None else overall, g["low"], g["high"]),
            "series": series,
        })
    return out


def suggest_goals(db: Database, hero: str) -> list[dict]:
    """Objectifs proposés à partir des fuites détectées."""
    leaks = find_leaks(db.period_totals(hero), db.position_totals(hero))
    return [{"stat": l.ref.stat, "position": l.ref.position or "", "low": l.ref.low, "high": l.ref.high,
             "reason": l.message} for l in leaks]


def compare_periods(db: Database, hero: str, a: tuple[str | None, str | None],
                    b: tuple[str | None, str | None]) -> dict:
    ta, tb = db.period_totals(hero, *a), db.period_totals(hero, *b)
    rows = []
    for sd in STAT_DEFS:
        va, vb = compute_stat(ta, sd), compute_stat(tb, sd)
        delta = None
        if sd.kind in ("pct", "ratio", "bb100") and va.value is not None and vb.value is not None:
            delta = vb.value - va.value
        elif sd.kind in ("count", "money"):
            delta = vb.num - va.num
        rows.append({"key": sd.key, "label": sd.label, "description": sd.description, "kind": sd.kind,
                     "a": va.format(sd.kind), "b": vb.format(sd.kind),
                     "a_sample": va.den, "b_sample": vb.den, "delta": None if delta is None else round(delta, 2)})
    return {"a": {"hands": ta.get("hands", 0), "net": round(ta.get("net", 0), 2)},
            "b": {"hands": tb.get("hands", 0), "net": round(tb.get("net", 0), 2)}, "rows": rows}
