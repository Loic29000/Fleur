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
        }

    @app.route("GET /api/hands")
    def hands(app, _id, query, _body):
        return "json", analysis.hand_list(
            app.db(), _hero(app, query), position=query.get("position", ""), result=query.get("result", ""),
            min_pot_bb=_float(query, "min_pot_bb"), bb=_float(query, "bb"), showdown=query.get("showdown", ""),
            cards=query.get("cards", ""), sort=query.get("sort", "date"),
            limit=int(query.get("limit") or 200), offset=int(query.get("offset") or 0))

    @app.route("GET /api/hand/*")
    def hand(app, hand_id, query, _body):
        raw = app.db().raw_hand(hand_id)
        if not raw:
            raise ApiError(HTTPStatus.NOT_FOUND, "main introuvable")
        return "json", replay(parse_hand(raw))

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

    @app.route("GET /api/backups")
    def backups(app, _id, query, _body):
        from fleur.backup import list_backups
        return "json", {"items": list_backups()}

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
