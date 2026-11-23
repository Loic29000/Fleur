"""Routes de l'API de l'application d'analyse."""

from __future__ import annotations

from http import HTTPStatus

from fleur import analysis
from fleur.parser import parse_hand
from fleur.replay import anonymize, replay
from fleur.web.server import AnalysisApp, ApiError


def _counter_help() -> dict[str, str]:
    """Aide de chaque compteur, tirée des stats intégrées qui l'utilisent."""
    from fleur.stats import STAT_DEFS
    out: dict[str, str] = {"hands": "nombre de mains", "net": "gains en €", "net_bb": "gains en big blinds",
                           "n_bets": "mises postflop", "n_overbets": "mises postflop de plus d'un pot"}
    for sd in STAT_DEFS:
        out.setdefault(sd.num, f"réalisé — {sd.label} : {sd.description}")
        if sd.den and "+" not in sd.den:
            out.setdefault(sd.den, f"occasions — {sd.label} : {sd.description}")
    return out


_COUNTER_HELP = _counter_help()


def _hero(app: AnalysisApp, query: dict) -> str:
    hero = query.get("hero") or analysis.main_hero(app.db())
    if not hero:
        raise ApiError(HTTPStatus.NOT_FOUND, "aucune main du héros en base")
    return hero


def _float(query: dict, key: str) -> float:
    try:
        return float(query.get(key) or 0)
    except ValueError:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{key} invalide")


def _downsample(values: list[float], n: int = 1200) -> list[float]:
    if len(values) <= n:
        return [round(v, 2) for v in values]
    step = (len(values) - 1) / (n - 1)
    return [round(values[round(i * step)], 2) for i in range(n)]


def _dashboard(app: AnalysisApp, hero: str) -> dict:
    """Toutes les stats du héros : chiffres clés, courbes, regroupements, fuites."""
    from fleur.dashboard import POSITION_ORDER, Group, _fmt_stake, cumulative, hero_hands, sessions
    from fleur.hud.overlay import color_for
    from fleur.leaks import find_leaks
    from fleur.stats import STAT_DEFS, compute_all
    db = app.db()
    hands = hero_hands(db, hero)
    groups: dict[str, dict[str, Group]] = {"position": {}, "limite": {}, "format": {}}
    total = Group()
    for h in hands:
        total.add(h)
        groups["position"].setdefault(h.position or "?", Group()).add(h)
        groups["limite"].setdefault(_fmt_stake(h.sb, h.bb), Group()).add(h)
        groups["format"].setdefault(f"{h.max_seats}-max", Group()).add(h)
    money, bbs = cumulative(hands, "net"), cumulative(hands, "net_bb")
    sess = sessions(db, hero)
    last = sess[-1] if sess else None
    totals = db.totals([hero])[hero]
    stats = compute_all(totals)
    stat_rows = []
    for sd in STAT_DEFS:
        sv = stats[sd.key]
        stat_rows.append({"key": sd.key, "label": sd.label, "description": sd.description,
                          "value": sv.format(sd.kind), "num": round(sv.num, 2), "den": round(sv.den, 2),
                          "kind": sd.kind, "color": color_for(sd.key, sv, totals.get("hands", 0), app.cfg)})

    def table(name: str, order: list[str] | None = None) -> list[dict]:
        items = groups[name]
        keys = sorted(items, key=lambda k: order.index(k) if k in order else 99) if order else list(items)
        return [{"name": k, "hands": items[k].hands, "net": round(items[k].net, 2),
                 "bb100": round(items[k].bb100, 1)} for k in keys]

    return {
        "hero": hero,
        "kpis": {"hands": total.hands, "net": round(total.net, 2), "bb100": round(total.bb100, 2),
                 "sd": round(money["sd"][-1], 2), "nsd": round(money["nsd"][-1], 2), "sessions": len(sess),
                 "last_session": {"start": last.start.astimezone().isoformat(timespec="minutes"),
                                  "hands": last.group.hands, "net": round(last.group.net, 2),
                                  "bb100": round(last.group.bb100, 1)} if last else None},
        "curves": {"money": {k: _downsample(v) for k, v in money.items()},
                   "bb": {k: _downsample(v) for k, v in bbs.items()}},
        "by_position": table("position", POSITION_ORDER), "by_stake": table("limite"),
        "by_format": table("format"),
        "stats": stat_rows,
        "leaks": [{"severity": l.severity, "message": l.message}
                  for l in find_leaks(totals, db.position_totals(hero))],
    }


SETTINGS_KEYS = ("hud_lines", "popup_stats", "colors", "font_size", "opacity", "hud_theme", "ui_theme",
                 "show_hero", "show_profile", "min_hands_for_colors", "profile_min_hands", "shown_hands_count")


def validate_settings(body: dict) -> dict:
    """Vérifie les réglages envoyés par la page avant de les écrire dans la config."""
    from fleur.stats import STAT_BY_KEY
    out = {}
    for key, value in body.items():
        if key not in SETTINGS_KEYS:
            raise ValueError(f"réglage inconnu : {key}")
        if key == "hud_lines":
            if not isinstance(value, list) or not 1 <= len(value) <= 6:
                raise ValueError("de 1 à 6 lignes de panneau")
            lines = [[k for k in line if k in STAT_BY_KEY][:8] for line in value if isinstance(line, list)]
            value = [line for line in lines if line] or [["vpip", "pfr", "hands"]]
        elif key == "popup_stats":
            value = [k for k in value if k in STAT_BY_KEY][:60]
        elif key == "colors":
            clean = {}
            for stat, rules in (value or {}).items():
                if stat not in STAT_BY_KEY or not isinstance(rules, list):
                    continue
                good = []
                for rule in rules:
                    try:
                        threshold, color = float(rule[0]), str(rule[1])
                    except (TypeError, ValueError, IndexError):
                        continue
                    if len(color) == 7 and color.startswith("#"):
                        good.append([threshold, color])
                if good:
                    clean[stat] = sorted(good, key=lambda r: r[0])
            value = clean
        elif key == "font_size":
            value = max(6, min(20, int(value)))
        elif key == "opacity":
            value = max(0.3, min(1.0, float(value)))
        elif key in ("hud_theme", "ui_theme"):
            if value not in ("sombre", "clair"):
                raise ValueError("thème : sombre ou clair")
        elif key in ("show_hero", "show_profile"):
            value = bool(value)
        else:  # nombres entiers
            value = max(0, min(10000, int(value)))
        out[key] = value
    return out


def _study_allowed(app: AnalysisApp) -> None:
    if app.table_open():
        raise ApiError(HTTPStatus.LOCKED,
                       "Une table Winamax est ouverte : le matériel d'étude (GTO, équité) est désactivé "
                       "pendant le jeu, conformément aux règles Winamax. Ferme tes tables pour réviser.")


def install(app: AnalysisApp) -> None:
    if app.routes:
        return

    @app.route("GET /api/meta")
    def meta(app, _id, query, _body):
        db = app.db()
        hero = analysis.main_hero(db)
        stakes = [r[0] for r in db.conn.execute(
            "SELECT DISTINCT bb FROM hands WHERE hero = ? ORDER BY bb", (hero,)).fetchall()] if hero else []
        return "json", {
            "hero": hero, "hands": db.hand_count(), "stakes": stakes,
            "positions": [p for p in analysis.POSITIONS if db.conn.execute(
                "SELECT 1 FROM player_hands WHERE player = ? AND position = ? LIMIT 1", (hero, p)).fetchone()],
            "table_open": bool(app.table_open()),
            "last_hand": db.conn.execute("SELECT MAX(played_at) FROM hands").fetchone()[0],
            "ui_theme": app.cfg.get("ui_theme", "sombre"),
        }

    @app.route("GET /api/dashboard")
    def dashboard(app, _id, query, _body):
        return "json", _dashboard(app, _hero(app, query))

    @app.route("GET /api/hands")
    def hands(app, _id, query, _body):
        from fleur.gto_review import _ensure_table, build_reviews
        gto = query.get("gto", "")
        if gto:
            _study_allowed(app)
        include_gto = not app.table_open()  # pas de verdict GTO pendant le jeu
        hero = _hero(app, query)
        _ensure_table(app.db())
        if gto:
            build_reviews(app.db(), hero)
        return "json", analysis.hand_list(
            app.db(), _hero(app, query), position=query.get("position", ""), result=query.get("result", ""),
            min_pot_bb=_float(query, "min_pot_bb"), bb=_float(query, "bb"), showdown=query.get("showdown", ""),
            cards=query.get("cards", ""), sort=query.get("sort", "date"),
            limit=int(query.get("limit") or 200), offset=int(query.get("offset") or 0),
            mark=query.get("mark", ""), opponent=query.get("opponent", ""), gto=gto, include_gto=include_gto)

    @app.route("GET /api/hand/*")
    def hand(app, hand_id, query, _body):
        raw = app.db().raw_hand(hand_id)
        if not raw:
            raise ApiError(HTTPStatus.NOT_FOUND, "main introuvable")
        return "json", replay(parse_hand(raw))

    @app.route("GET /api/mark/*")
    def get_mark(app, hand_id, query, _body):
        return "json", app.db().mark(hand_id)

    @app.route("POST /api/mark")
    def save_mark(app, _id, query, body):
        body = body or {}
        if not body.get("hand_id") or not app.db().has_hand(body["hand_id"]):
            raise ApiError(HTTPStatus.NOT_FOUND, "main introuvable")
        return "json", app.db().save_mark(body["hand_id"], list(body.get("tags") or []), body.get("comment", ""))

    @app.route("GET /api/mark_tags")
    def mark_tags(app, _id, query, _body):
        default = app.cfg.get("hand_mark_tags") or []
        used = app.db().mark_tags()
        return "json", {"tags": list(dict.fromkeys(default + sorted(used))), "counts": used}

    @app.route("GET /api/goals")
    def goals(app, _id, query, _body):
        from fleur.progress import goals_report, suggest_goals
        from fleur.stats import STAT_DEFS
        hero = _hero(app, query)
        return "json", {"goals": goals_report(app.db(), hero), "suggestions": suggest_goals(app.db(), hero),
                        "stats": [{"key": s.key, "label": s.label, "description": s.description}
                                  for s in STAT_DEFS if s.kind in ("pct", "ratio", "bb100")]}

    @app.route("POST /api/goals/add")
    def goal_add(app, _id, query, body):
        from fleur.stats import STAT_BY_KEY
        body = body or {}
        if body.get("stat") not in STAT_BY_KEY:
            raise ApiError(HTTPStatus.BAD_REQUEST, "stat inconnue")

        def num(key):
            v = body.get(key)
            return None if v in (None, "") else float(v)
        low, high = num("low"), num("high")
        if low is None and high is None:
            raise ApiError(HTTPStatus.BAD_REQUEST, "indique un minimum et/ou un maximum")
        if low is not None and high is not None and low > high:
            raise ApiError(HTTPStatus.BAD_REQUEST, "le minimum dépasse le maximum")
        return "json", {"id": app.db().add_goal(body["stat"], low, high, body.get("position") or "")}

    @app.route("POST /api/goals/delete")
    def goal_delete(app, _id, query, body):
        app.db().delete_goal(int((body or {}).get("id", 0)))
        return "json", {"ok": True}

    @app.route("GET /api/compare")
    def compare(app, _id, query, _body):
        from fleur.progress import compare_periods
        q = lambda k: query.get(k) or None
        return "json", compare_periods(app.db(), _hero(app, query), (q("a_start"), q("a_end")),
                                       (q("b_start"), q("b_end")))

    @app.route("GET /api/opponents")
    def opponents(app, _id, query, _body):
        return "json", {"items": analysis.opponents(app.db(), _hero(app, query),
                                                    min_hands=int(query.get("min_hands") or 50))}

    @app.route("GET /api/player/*")
    def player(app, name, query, _body):
        from urllib.parse import unquote
        from fleur.hud.overlay import render_popup
        name = unquote(name)
        db = app.db()
        totals = db.totals([name])[name]
        if not totals.get("hands"):
            raise ApiError(HTTPStatus.NOT_FOUND, "joueur inconnu")
        note = db.note(name)
        html = render_popup(name, totals, app.cfg, note, db.last_shown(name, 10), db.position_totals(name))
        return "json", {"player": name, "popup": html, "note": note.note, "tag": note.tag, "label": note.label,
                        "color": note.color, "tags": app.cfg.get("player_tags", {})}

    @app.route("POST /api/note")
    def save_note(app, _id, query, body):
        from fleur.db import PlayerNote
        from fleur.hud.notes_dialog import apply_tag
        body = body or {}
        name = body.get("player")
        if not name:
            raise ApiError(HTTPStatus.BAD_REQUEST, "joueur manquant")
        note = app.db().note(name)
        if "tag" in body:
            apply_tag(note, body.get("tag") or None, app.cfg)
        if "note" in body:
            note.note = (body.get("note") or "").strip()[:2000]
        app.db().save_note(note)
        return "json", {"ok": True}

    @app.route("GET /api/settings")
    def get_settings(app, _id, query, _body):
        from fleur.config import load_config
        from fleur.stats import STAT_DEFS
        cfg = load_config()
        return "json", {"settings": {k: cfg.get(k) for k in SETTINGS_KEYS},
                        "stats": [{"key": s.key, "label": s.label, "description": s.description, "kind": s.kind}
                                  for s in STAT_DEFS]}

    @app.route("POST /api/settings")
    def post_settings(app, _id, query, body):
        from fleur.config import load_config, save_config
        try:
            changes = validate_settings(body or {})
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))
        cfg = load_config()
        cfg.update(changes)
        save_config(cfg)
        app.cfg.update(changes)
        return "json", {"saved": sorted(changes)}

    @app.route("GET /api/gto/spots")
    def gto_spots(app, _id, query, _body):
        from fleur.gto import SPOTS
        _study_allowed(app)
        return "json", {"spots": [{"id": k, "title": v["title"], "group": v["group"], "position": v["position"]}
                                  for k, v in SPOTS.items()]}

    @app.route("GET /api/gto/spot")
    def gto_spot(app, _id, query, _body):
        from fleur.gto import SPOTS, compare_rfi, spot_grid
        _study_allowed(app)
        spot_id = query.get("id", "")
        if spot_id not in SPOTS:
            raise ApiError(HTTPStatus.NOT_FOUND, "situation inconnue")
        out = spot_grid(spot_id)
        if spot_id.startswith("rfi_"):
            fmt = int(query.get("format") or 6)
            # en 5-max, la première position (UTG) correspond au HJ du 6-max
            hero_pos = {6: out["position"], 5: {"HJ": "UTG", "UTG": None}.get(out["position"], out["position"])}[
                5 if fmt == 5 else 6]
            hero = analysis.main_hero(app.db())
            if hero and hero_pos:
                cells = analysis.hero_rfi_cells(app.db(), hero, hero_pos, fmt)
                out["hero"] = {"position": hero_pos, "format": fmt,
                               "cells": {k: round(100 * v["rfi"] / v["opp"]) for k, v in cells.items() if v["opp"]},
                               "samples": {k: v["opp"] for k, v in cells.items()},
                               "open_percent": round(100 * sum(v["rfi"] for v in cells.values())
                                                     / max(1, sum(v["opp"] for v in cells.values())), 1),
                               **compare_rfi(spot_id, cells)}
        return "json", out

    @app.route("GET /api/gto/hand/*")
    def gto_hand(app, hand_id, query, _body):
        from fleur.gto_review import review_hand
        _study_allowed(app)
        raw = app.db().raw_hand(hand_id)
        if not raw:
            raise ApiError(HTTPStatus.NOT_FOUND, "main introuvable")
        return "json", review_hand(parse_hand(raw), _hero(app, query))

    @app.route("GET /api/gto/review_summary")
    def gto_review_summary(app, _id, query, _body):
        from fleur.gto_review import summary
        _study_allowed(app)
        return "json", summary(app.db(), _hero(app, query))

    @app.route("GET /api/gto/postflop")
    def gto_postflop(app, _id, query, _body):
        from fleur.equity import parse_cards
        from fleur.gto import postflop_advice
        _study_allowed(app)
        try:
            return "json", postflop_advice(parse_cards(query.get("board", "")))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))

    @app.route("GET /api/ranges")
    def ranges(app, _id, query, _body):
        return "json", analysis.ranges(app.db(), _hero(app, query), query.get("position", ""), _float(query, "bb"))

    @app.route("GET /api/sessions")
    def sessions(app, _id, query, _body):
        return "json", analysis.session_report(app.db(), _hero(app, query))

    @app.route("GET /api/hand_text/*")
    def hand_text(app, hand_id, query, _body):
        raw = app.db().raw_hand(hand_id)
        if not raw:
            raise ApiError(HTTPStatus.NOT_FOUND, "main introuvable")
        return "text", (anonymize(parse_hand(raw)) if query.get("anon") else raw) + "\n"

    @app.route("POST /api/backup")
    def backup(app, _id, query, _body):
        from fleur.backup import backup_database
        return "json", {"path": str(backup_database(app.db()))}

    @app.route("POST /api/report")
    def report(app, _id, query, _body):
        from fleur import diagnostics
        out = diagnostics.make_report(diagnostics.default_report_dir(), {
            "mains_en_base": app.db().hand_count(), "origine": "application d'analyse"})
        return "json", {"path": str(out)}

    @app.route("GET /api/backups")
    def backups(app, _id, query, _body):
        from fleur.backup import list_backups
        from fleur.backup import last_backup_age_hours
        age = last_backup_age_hours()
        return "json", {"items": list_backups(), "auto": bool(app.cfg.get("auto_backup", True)),
                        "interval": app.cfg.get("backup_interval_hours", 24),
                        "age_hours": round(age, 1) if age is not None else None}

    @app.route("GET /api/allin_ev")
    def allin_ev(app, _id, query, _body):
        from fleur.allin import hero_allin_report
        return "json", hero_allin_report(app.db(), _hero(app, query))

    @app.route("GET /api/custom_stats")
    def custom_stats(app, _id, query, _body):
        from fleur.stats import ALL_COUNTERS, STAT_BY_KEY, compute_stat
        specs = app.cfg.get("custom_stats") or []
        hero = analysis.main_hero(app.db())
        totals = app.db().totals([hero])[hero] if hero else {}
        out = []
        for spec in specs:
            sd = STAT_BY_KEY.get(spec.get("key"))
            value = compute_stat(totals, sd).format(sd.kind) if sd else "invalide"
            out.append({**spec, "hero_value": value})
        return "json", {"stats": out, "counters": [{"key": k, "description": _COUNTER_HELP.get(k, "")}
                                                    for k in ALL_COUNTERS]}

    @app.route("POST /api/custom_stats/test")
    def custom_test(app, _id, query, body):
        from fleur.stats import compute_stat, make_custom_stat
        try:
            sd = make_custom_stat(body or {})
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))
        hero = analysis.main_hero(app.db())
        totals = app.db().totals([hero])[hero] if hero else {}
        sv = compute_stat(totals, sd)
        return "json", {"value": sv.format(sd.kind), "num": round(sv.num, 2), "den": round(sv.den, 2)}

    @app.route("POST /api/custom_stats/save")
    def custom_save(app, _id, query, body):
        from fleur.config import load_config, save_config
        from fleur.stats import make_custom_stat, set_custom_stats
        try:
            sd = make_custom_stat(body or {})
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))
        spec = {"key": sd.key, "label": sd.label, "num": sd.num, "den": sd.den, "kind": sd.kind,
                "description": sd.description}
        cfg = load_config()
        specs = [s for s in cfg.get("custom_stats") or [] if s.get("key") != sd.key] + [spec]
        cfg["custom_stats"] = specs
        save_config(cfg)
        app.cfg["custom_stats"] = specs
        set_custom_stats(specs)
        return "json", spec

    @app.route("POST /api/custom_stats/delete")
    def custom_delete(app, _id, query, body):
        from fleur.config import load_config, save_config
        from fleur.stats import set_custom_stats
        key = (body or {}).get("key")
        cfg = load_config()
        specs = [s for s in cfg.get("custom_stats") or [] if s.get("key") != key]
        cfg["custom_stats"] = specs
        save_config(cfg)
        app.cfg["custom_stats"] = specs
        set_custom_stats(specs)
        return "json", {"deleted": key}

    @app.route("POST /api/equity")
    def equity_calc(app, _id, query, body):
        """Calculateur d'équité : refusé tant qu'une table Winamax est ouverte
        (pas d'aide à la décision pendant une partie, règles Winamax)."""
        from fleur.equity import equity, parse_cards
        if app.table_open():
            raise ApiError(HTTPStatus.LOCKED,
                           "Une table Winamax est ouverte : le calculateur est désactivé pendant le jeu. "
                           "Ferme tes tables puis réessaie.")
        body = body or {}
        try:
            hands = [parse_cards(h) or None for h in body.get("hands", [])]
            board = parse_cards(body.get("board", ""))
            return "json", equity(hands, board, trials=20000)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, str(exc))
