"""Tableau de bord du héros : page HTML locale, autonome (aucune ressource en ligne).

Contenu : courbes de gains (€ et big blinds, avec et sans abattage), BB/100
par position, par limite et par format, résultats par session et alertes de
fuites. Analyse après coup de l'historique uniquement.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fleur.db import Database
from fleur.leaks import find_leaks

SESSION_GAP = timedelta(minutes=30)
MAX_POINTS = 1500
POSITION_ORDER = ["UTG", "UTG+1", "UTG+2", "MP", "LJ", "HJ", "CO", "BTN", "SB", "BB"]


@dataclass
class HeroHand:
    played_at: datetime | None
    bb: float
    max_seats: int
    net: float
    net_bb: float
    showdown: bool
    position: str | None
    sb: float = 0.0


@dataclass
class Group:
    hands: int = 0
    net: float = 0.0
    net_bb: float = 0.0

    def add(self, h: HeroHand) -> None:
        self.hands += 1
        self.net += h.net
        self.net_bb += h.net_bb

    @property
    def bb100(self) -> float:
        return 100 * self.net_bb / self.hands if self.hands else 0.0


@dataclass
class Session:
    start: datetime
    end: datetime
    tables: set = field(default_factory=set)
    group: Group = field(default_factory=Group)


def main_hero(db: Database) -> str | None:
    row = db.conn.execute(
        "SELECT hero, COUNT(*) n FROM hands WHERE hero IS NOT NULL GROUP BY hero ORDER BY n DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def hero_hands(db: Database, hero: str) -> list[HeroHand]:
    rows = db.conn.execute(
        "SELECT h.played_at, h.bb, h.max_seats, ph.net, ph.net_bb, ph.wtsd, ph.position, h.sb "
        "FROM player_hands ph JOIN hands h ON h.hand_id = ph.hand_id "
        "WHERE ph.player = ? ORDER BY h.played_at, h.hand_id", (hero,),
    ).fetchall()
    out = []
    for played_at, bb, seats, net, net_bb, wtsd, pos, sb in rows:
        when = datetime.fromisoformat(played_at).replace(tzinfo=timezone.utc) if played_at else None
        out.append(HeroHand(when, bb or 0.0, seats or 0, net or 0.0, net_bb or 0.0, bool(wtsd), pos, sb or 0.0))
    return out


def sessions(db: Database, hero: str, gap: timedelta = SESSION_GAP) -> list[Session]:
    rows = db.conn.execute(
        "SELECT h.played_at, h.table_name, ph.net, ph.net_bb FROM player_hands ph "
        "JOIN hands h ON h.hand_id = ph.hand_id WHERE ph.player = ? AND h.played_at IS NOT NULL "
        "ORDER BY h.played_at", (hero,),
    ).fetchall()
    out: list[Session] = []
    for played_at, table, net, net_bb in rows:
        when = datetime.fromisoformat(played_at).replace(tzinfo=timezone.utc)
        if not out or when - out[-1].end > gap:
            out.append(Session(when, when))
        s = out[-1]
        s.end = when
        s.tables.add(table)
        s.group.add(HeroHand(when, 0, 0, net or 0.0, net_bb or 0.0, False, None))
    return out


def cumulative(hands: list[HeroHand], attr: str) -> dict[str, list[float]]:
    total, sd, nsd = [0.0], [0.0], [0.0]
    for h in hands:
        v = getattr(h, attr)
        total.append(total[-1] + v)
        sd.append(sd[-1] + (v if h.showdown else 0.0))
        nsd.append(nsd[-1] + (0.0 if h.showdown else v))
    return {"total": total, "sd": sd, "nsd": nsd}


def _downsample(values: list[float], n: int = MAX_POINTS) -> list[tuple[int, float]]:
    if len(values) <= n:
        return list(enumerate(values))
    step = (len(values) - 1) / (n - 1)
    return [(round(i * step), values[round(i * step)]) for i in range(n)]


def svg_chart(series: dict[str, list[float]], unit: str, width: int = 900, height: int = 280) -> str:
    colors = {"total": "#7ddc6f", "sd": "#4fa3ff", "nsd": "#ff6b6b"}
    labels = {"total": "Gains", "sd": "Avec abattage", "nsd": "Sans abattage"}
    all_values = [v for s in series.values() for v in s] or [0.0]
    lo, hi = min(all_values + [0.0]), max(all_values + [0.0])
    if hi - lo < 1e-9:
        hi = lo + 1
    n = max(len(s) for s in series.values()) - 1 or 1
    pad_l, pad_r, pad_t, pad_b = 60, 10, 10, 28

    def xy(i: int, v: float) -> tuple[float, float]:
        x = pad_l + (width - pad_l - pad_r) * i / n
        y = pad_t + (height - pad_t - pad_b) * (hi - v) / (hi - lo)
        return x, y

    parts = [f"<svg viewBox='0 0 {width} {height}' class='chart' role='img'>"]
    for k in range(5):  # graduations
        v = lo + (hi - lo) * k / 4
        _, y = xy(0, v)
        parts.append(f"<line x1='{pad_l}' x2='{width - pad_r}' y1='{y:.1f}' y2='{y:.1f}' class='grid'/>")
        parts.append(f"<text x='{pad_l - 6}' y='{y + 4:.1f}' text-anchor='end' class='tick'>{v:,.1f}</text>")
    _, y0 = xy(0, 0)
    parts.append(f"<line x1='{pad_l}' x2='{width - pad_r}' y1='{y0:.1f}' y2='{y0:.1f}' class='zero'/>")
    parts.append(f"<text x='{width - pad_r}' y='{height - 8}' text-anchor='end' class='tick'>{n} mains</text>")
    for key in ("nsd", "sd", "total"):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in _downsample(series[key])))
        parts.append(f"<polyline points='{pts}' fill='none' stroke='{colors[key]}' "
                     f"stroke-width='{2 if key == 'total' else 1.3}'/>")
    parts.append("</svg>")
    legend = " ".join(
        f"<span class='lg'><i style='background:{colors[k]}'></i>{labels[k]} "
        f"<b>{series[k][-1]:+,.2f} {unit}</b></span>" for k in ("total", "sd", "nsd"))
    return f"<div class='legend'>{legend}</div>" + "".join(parts)


def _group_table(title: str, groups: dict[str, Group], order: list[str] | None = None) -> str:
    keys = sorted(groups, key=lambda k: order.index(k) if order and k in order else 99) if order else list(groups)
    rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td class='n'>{g.hands}</td>"
        f"<td class='n {'pos' if g.net >= 0 else 'neg'}'>{g.net:+.2f} €</td>"
        f"<td class='n {'pos' if g.bb100 >= 0 else 'neg'}'>{g.bb100:+.1f}</td></tr>" for k in keys for g in [groups[k]])
    return (f"<section><h2>{title}</h2><table><thead><tr><th></th><th class='n'>Mains</th><th class='n'>Gains</th>"
            f"<th class='n'>BB/100</th></tr></thead><tbody>{rows}</tbody></table></section>")


def _fmt_stake(sb: float, bb: float) -> str:
    return f"{sb:g} / {bb:g} €".replace(".", ",") if bb else "?"


def build_html(db: Database, hero: str | None = None, now: datetime | None = None) -> str:
    hero = hero or main_hero(db)
    if not hero:
        return _page("Fleur — tableau de bord", "<p>Aucune main du héros en base pour l'instant.</p>")
    hands = hero_hands(db, hero)
    by_pos: dict[str, Group] = {}
    by_stake: dict[str, Group] = {}
    by_format: dict[str, Group] = {}
    total = Group()
    for h in hands:
        total.add(h)
        by_pos.setdefault(h.position or "?", Group()).add(h)
        by_stake.setdefault(_fmt_stake(h.sb, h.bb), Group()).add(h)
        by_format.setdefault(f"{h.max_seats}-max", Group()).add(h)

    money, bbs = cumulative(hands, "net"), cumulative(hands, "net_bb")
    sess = sessions(db, hero)
    sess_rows = "".join(
        f"<tr><td>{s.start.astimezone():%d/%m/%Y %H:%M}</td>"
        f"<td class='n'>{int((s.end - s.start).total_seconds() // 60)} min</td>"
        f"<td class='n'>{len(s.tables)}</td><td class='n'>{s.group.hands}</td>"
        f"<td class='n {'pos' if s.group.net >= 0 else 'neg'}'>{s.group.net:+.2f} €</td>"
        f"<td class='n {'pos' if s.group.bb100 >= 0 else 'neg'}'>{s.group.bb100:+.1f}</td></tr>"
        for s in reversed(sess[-40:]))

    leaks = find_leaks(db.totals([hero])[hero], db.position_totals(hero))
    leak_items = "".join(
        f"<li class='sev-{l.severity}'><span class='badge'>{l.severity}</span>{html.escape(l.message)}</li>"
        for l in leaks) or "<li>Aucune stat hors des fourchettes de référence.</li>"

    sd = money["sd"][-1]
    body = f"""
<header><h1>Tableau de bord</h1>
<p class='sub'>{html.escape(hero)} · {total.hands} mains · généré le {(now or datetime.now()):%d/%m/%Y à %H:%M}</p></header>
<div class='kpis'>
  <div><span>Gains</span><b class='{'pos' if total.net >= 0 else 'neg'}'>{total.net:+.2f} €</b></div>
  <div><span>BB/100</span><b class='{'pos' if total.bb100 >= 0 else 'neg'}'>{total.bb100:+.1f}</b></div>
  <div><span>Avec abattage</span><b class='{'pos' if sd >= 0 else 'neg'}'>{sd:+.2f} €</b></div>
  <div><span>Sans abattage</span><b class='{'pos' if money['nsd'][-1] >= 0 else 'neg'}'>{money['nsd'][-1]:+.2f} €</b></div>
  <div><span>Sessions</span><b>{len(sess)}</b></div>
</div>
<section><h2>Courbe de gains (€)</h2>{svg_chart(money, '€')}</section>
<section><h2>Courbe de gains (big blinds)</h2>{svg_chart(bbs, 'bb')}</section>
<section><h2>Fuites possibles</h2>
<p class='note'>Comparaison de tes stats à des fourchettes indicatives de cash game 6-max, de la plus
importante à la moins importante. À lire comme des pistes de révision, pas comme des règles.</p>
<ul class='leaks'>{leak_items}</ul></section>
<div class='grid3'>
{_group_table('Par position', by_pos, POSITION_ORDER)}
{_group_table('Par limite', by_stake)}
{_group_table('Par format', by_format)}
</div>
<section><h2>Sessions récentes</h2><p class='note'>Une session s'arrête après 30 minutes sans main.</p>
<table><thead><tr><th>Début</th><th class='n'>Durée</th><th class='n'>Tables</th><th class='n'>Mains</th><th class='n'>Gains</th><th class='n'>BB/100</th></tr></thead>
<tbody>{sess_rows}</tbody></table></section>
"""
    return _page("Fleur — tableau de bord", body)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --bg:#121417; --panel:#1b1e23; --line:#2b3038; --text:#e8e8e8; --muted:#9aa5b1;
        --pos:#7ddc6f; --neg:#ff6b6b; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.45 "Segoe UI", system-ui, sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ margin:0; font-size:24px; }} h2 {{ font-size:16px; margin:0 0 10px; color:var(--muted); font-weight:600; }}
.sub, .note {{ color:var(--muted); margin:4px 0 0; }} .note {{ font-size:12.5px; margin:0 0 10px; }}
section {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; margin-top:16px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-top:16px; }}
.kpis div {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; }}
.kpis span {{ display:block; color:var(--muted); font-size:12px; }} .kpis b {{ font-size:22px; }}
.grid3 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:0 16px; }}
table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }}
th, td {{ padding:5px 8px; border-bottom:1px solid var(--line); text-align:left; }}
th {{ color:var(--muted); font-weight:600; font-size:12px; }} .n {{ text-align:right; }}
.pos {{ color:var(--pos); }} .neg {{ color:var(--neg); }}
.chart {{ width:100%; height:auto; display:block; }}
.chart .grid {{ stroke:var(--line); }} .chart .zero {{ stroke:var(--muted); stroke-dasharray:4 4; }}
.chart .tick {{ fill:var(--muted); font-size:11px; }}
.legend {{ display:flex; flex-wrap:wrap; gap:16px; margin-bottom:6px; font-size:13px; }}
.lg i {{ display:inline-block; width:12px; height:3px; margin-right:6px; vertical-align:middle; }}
.leaks {{ list-style:none; padding:0; margin:0; }}
.leaks li {{ padding:7px 0; border-bottom:1px solid var(--line); }}
.badge {{ display:inline-block; min-width:70px; font-size:11px; text-transform:uppercase; letter-spacing:.04em;
          padding:2px 8px; border-radius:20px; margin-right:10px; text-align:center; color:#111; }}
.sev-forte .badge {{ background:var(--neg); }} .sev-moyenne .badge {{ background:#ffd84a; }}
.sev-faible .badge {{ background:#9aa5b1; }}
</style></head><body><main>{body}</main></body></html>"""


def write_dashboard(db: Database, path: Path, hero: str | None = None) -> Path:
    path.write_text(build_html(db, hero), encoding="utf-8")
    return path
