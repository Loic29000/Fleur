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
        }

    @app.route("GET /api/dashboard")
    def dashboard(app, _id, query, _body):
        return "json", _dashboard(app, _hero(app, query))

    @app.route("GET /api/hands")
    def hands(app, _id, query, _body):
        return "json", analysis.hand_list(
            app.db(), _hero(app, query), position=query.get("position", ""), result=query.get("result", ""),
            min_pot_bb=_float(query, "min_pot_bb"), bb=_float(query, "bb"), showdown=query.get("showdown", ""),
            cards=query.get("cards", ""), sort=query.get("sort", "date"),
            limit=int(query.get("limit") or 200), offset=int(query.get("offset") or 0),
            mark=query.get("mark", ""))

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
