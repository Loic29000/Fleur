"""Panneaux du HUD (PySide6) posés sur les tables Winamax."""

from __future__ import annotations

import html
import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget

from fleur.db import Database, PlayerNote
from fleur.hud import win32
from fleur.hud.layouts import Layouts, visual_index
from fleur.parser import Hand
from fleur.profile import classify
from fleur.stats import STAT_BY_KEY, StatValue, compute_all
from fleur.watcher import HistoryWatcher

log = logging.getLogger("fleur")

# Une table sans nouvelle main ni fenêtre depuis ce délai est retirée
TABLE_TIMEOUT_S = 15 * 60
WINDOW_GONE_GRACE_S = 10
WINDOW_SEARCH_INTERVAL_S = 1.0


def stats_filter_args(cfg: dict, hand: Hand) -> dict:
    """Paramètres de filtre de Database.totals pour la table de `hand`."""
    filt = cfg.get("stats_filter") or {}
    return {"max_seats": hand.max_seats, "bb": hand.bb,
            "seats_mode": filt.get("seats", "all"), "stakes_mode": filt.get("stakes", "all")}


def color_for(key: str, sv: StatValue, hands: float, cfg: dict) -> str:
    rules = cfg.get("colors", {}).get(key)
    if not rules or sv.value is None or hands < cfg.get("min_hands_for_colors", 0):
        return "#e8e8e8"
    for threshold, color in rules:
        if sv.value < threshold:
            return color
    return rules[-1][1]


def render_badge(note: PlayerNote | None) -> str:
    """Pastille de couleur + étiquette, et ✎ si une note existe."""
    if not note or note.empty:
        return ""
    out = ""
    if note.tag:
        color = html.escape(note.color or "#e8e8e8")
        out += f"<span style='color:{color}'>● {html.escape((note.label or '')[:10])}</span> "
    if note.note.strip():
        out += "<span style='color:#ffd84a'>✎</span> "
    return out


def render_profile(totals: dict[str, float], cfg: dict) -> str:
    """Badge de profil automatique, au-delà du seuil de mains configuré."""
    if not cfg.get("show_profile", True):
        return ""
    profile = classify(totals, cfg)
    if not profile:
        return ""
    color = html.escape(profile.color)
    return f"<span style='color:#111; background:{color}'>&nbsp;{html.escape(profile.label)}&nbsp;</span> "


def render_lines(player: str, totals: dict[str, float], cfg: dict, note: PlayerNote | None = None) -> str:
    stats = compute_all(totals)
    hands = totals.get("hands", 0)
    rows = [render_profile(totals, cfg) + render_badge(note)
            + f"<span style='color:#bbbbbb'>{html.escape(player[:16])}</span>"]
    for line in cfg["hud_lines"]:
        parts = []
        for key in line:
            sd = STAT_BY_KEY.get(key)
            if not sd:
                continue
            sv = stats[key]
            text = sv.format(sd.kind)
            if sd.kind == "count":
                text = f"({text})"
            parts.append(f"<span style='color:{color_for(key, sv, hands, cfg)}'>{text}</span>")
        rows.append("<span style='color:#777'>/</span>".join(parts))
    return "<br>".join(rows)


_SUITS = {"s": ("♠", "#e8e8e8"), "h": ("♥", "#ff6b6b"), "d": ("♦", "#4fa3ff"), "c": ("♣", "#7ddc6f")}


def render_cards(cards: str) -> str:
    """'Ah Kd' -> cartes avec symboles colorés (4 couleurs, comme Winamax)."""
    out = []
    for card in cards.split():
        rank, suit = card[:-1], card[-1:].lower()
        symbol, color = _SUITS.get(suit, (suit, "#e8e8e8"))
        out.append(f"<span style='color:{color}'>{html.escape(rank)}{symbol}</span>")
    return " ".join(out)


def render_shown(shown: list) -> str:
    """Lignes du popup pour les dernières mains montrées à l'abattage."""
    if not shown:
        return ""
    rows = ["<tr><td colspan=3 style='color:#bbbbbb'><br><b>Mains montrées</b></td></tr>"]
    for sh in shown:
        color = "#7ddc6f" if sh.net > 0 else "#ff6b6b" if sh.net < 0 else "#e8e8e8"
        result = f"{sh.net:+.2f} ({sh.net_bb:+.1f} bb)"
        board = render_cards(sh.board) if sh.board else "<span style='color:#888'>pas de flop</span>"
        rows.append(
            f"<tr><td colspan=3><b>{render_cards(sh.cards)}</b>&nbsp; {board}"
            f"&nbsp; <span style='color:{color}'>{result}</span><br>"
            f"<span style='color:#aaaaaa'>&nbsp;&nbsp;{html.escape(sh.line)}</span></td></tr>"
        )
    return "".join(rows)


POSITION_ORDER = ["UTG", "UTG+1", "UTG+2", "MP", "LJ", "HJ", "CO", "BTN", "SB", "BB"]
POSITION_STATS = [("rfi", "RFI"), ("3bet", "3B"), ("fsteal", "FvS")]


def render_positions(by_pos: dict[str, dict[str, float]], cfg: dict) -> str:
    """Tableau RFI / 3-bet / fold face au vol par position."""
    if not by_pos:
        return ""
    head = "".join(f"<td align=right><b>{label}</b></td>" for _, label in POSITION_STATS)
    rows = ["<tr><td colspan=3 style='color:#bbbbbb'><br><b>Par position</b></td></tr>",
            f"<tr><td colspan=3><table cellspacing=0 cellpadding=1><tr><td></td><td align=right>Mains</td>{head}</tr>"]
    for pos in sorted(by_pos, key=lambda p: POSITION_ORDER.index(p) if p in POSITION_ORDER else 99):
        totals = by_pos[pos]
        stats = compute_all(totals)
        cells = []
        for key, _ in POSITION_STATS:
            sv = stats[key]
            if key == "fsteal" and pos not in ("SB", "BB"):
                cells.append("<td></td>")
                continue
            sample = f"<span style='color:#777'>({int(sv.den)})</span>" if sv.den else ""
            color = color_for(key, sv, totals.get("hands", 0), cfg)
            cells.append(f"<td align=right>&nbsp;<span style='color:{color}'>{sv.format('pct')}</span>{sample}</td>")
        rows.append(f"<tr><td>{pos}</td><td align=right>{int(totals.get('hands', 0))}</td>{''.join(cells)}</tr>")
    rows.append("</table></td></tr>")
    return "".join(rows)


def render_popup(player: str, totals: dict[str, float], cfg: dict, note: PlayerNote | None = None,
                 shown: list | None = None, by_pos: dict | None = None) -> str:
    stats = compute_all(totals)
    hands = totals.get("hands", 0)
    rows = [f"<tr><td colspan=3>{render_profile(totals, cfg)}{render_badge(note)}"
            f"<b>{html.escape(player)}</b></td></tr>"]
    if note and note.note.strip():
        text = html.escape(note.note).replace("\n", "<br>")
        rows.append(f"<tr><td colspan=3 style='color:#ffd84a'>{text}</td></tr>")
    for key in cfg["popup_stats"]:
        sd = STAT_BY_KEY.get(key)
        if not sd:
            continue
        sv = stats[key]
        sample = "" if sd.kind in ("count", "money", "bb100") else f"{int(sv.num)}/{int(sv.den)}"
        rows.append(
            f"<tr><td>{sd.label}</td><td align=right style='color:{color_for(key, sv, hands, cfg)}'>"
            f"<b>{sv.format(sd.kind)}</b></td>"
            f"<td style='color:#888'>&nbsp;{sample}</td></tr>"
        )
    rows.append(render_streets(totals, cfg))
    rows.append(render_positions(by_pos or {}, cfg))
    rows.append(render_shown(shown or []))
    return f"<table cellspacing=0 cellpadding=1>{''.join(rows)}</table>"


def _pct_cell(sv, key: str, totals: dict, cfg: dict) -> str:
    if not sv.den:
        return "<td align=right style='color:#555'>-</td>"
    color = color_for(key, sv, totals.get("hands", 0), cfg)
    return (f"<td align=right>&nbsp;<span style='color:{color}'>{sv.value:.0f}</span>"
            f"<span style='color:#777'>({int(sv.den)})</span></td>")


def render_streets(totals: dict[str, float], cfg: dict) -> str:
    """Mise / fold / relance face à une mise par street, et fold selon la taille de mise."""
    stats = compute_all(totals)
    if not any(totals.get(k) for k in ("opp_bet_f", "opp_vs_bet_f", "opp_bet_t", "opp_vs_bet_t",
                                       "opp_bet_r", "opp_vs_bet_r")):
        return ""
    rows = ["<tr><td colspan=3 style='color:#bbbbbb'><br><b>Par street</b></td></tr>",
            "<tr><td colspan=3><table cellspacing=0 cellpadding=1><tr><td></td><td align=right>Mise</td>"
            "<td align=right>Fold vs mise</td><td align=right>Relance</td></tr>"]
    for s, name in (("f", "Flop"), ("t", "Turn"), ("r", "River")):
        cells = "".join(_pct_cell(stats[k], k, totals, cfg) for k in (f"bet_{s}", f"fvb_{s}", f"rvb_{s}"))
        rows.append(f"<tr><td>{name}</td>{cells}</tr>")
    rows.append("</table></td></tr>")
    for key, label in (("fv_small", "Fold vs petite mise (&lt; ½ pot)"), ("fv_med", "Fold vs mise ½ à 1 pot"),
                       ("fv_big", "Fold vs overbet"), ("overbet", "Overbets (part des mises)")):
        rows.append(f"<tr><td>{label}</td>{_pct_cell(stats[key], key, totals, cfg)}<td></td></tr>")
    return "".join(rows)


class HudPanel(QWidget):
    def __init__(self, table: "TableHud", visual: int, cfg: dict):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.table = table
        self.visual = visual
        self.cfg = cfg
        self.player = ""
        self.totals: dict[str, float] = {}
        self.note: PlayerNote | None = None
        self._drag_from: QPoint | None = None
        self._moved = False
        self._popup: QLabel | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(cfg.get("opacity", 0.85))
        self.setStyleSheet("background:#151515; border:1px solid #333;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 1, 3, 1)
        self.label = QLabel(self)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setStyleSheet("border:none;")
        # Le texte riche d'un QLabel capte les clics : on les laisse au panneau
        # pour pouvoir le déplacer et l'ouvrir au double-clic.
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        font = QFont("Consolas")
        font.setPointSize(cfg.get("font_size", 9))
        self.label.setFont(font)
        layout.addWidget(self.label)
        self.setWindowTitle("Fleur HUD")

    def set_player(self, player: str, totals: dict[str, float], note: PlayerNote | None = None) -> None:
        self.player = player
        self.totals = totals
        self.note = note
        self.label.setText(render_lines(player, totals, self.cfg, note))
        self.setToolTip(html.escape(note.note) if note and note.note.strip() else "")
        self.adjustSize()
        if self._popup and self._popup.isVisible():
            self._popup.setText(self.popup_html())
            self._popup.adjustSize()

    def popup_html(self) -> str:
        db = self.table.manager.db
        shown, by_pos = [], {}
        try:
            shown = db.last_shown(self.player, self.cfg.get("shown_hands_count", 8))
            hand = self.table.last_hand
            filters = stats_filter_args(self.cfg, hand) if hand else {}
            by_pos = db.position_totals(self.player, **filters)
        except Exception:
            log.exception("lecture des détails du popup impossible")
        return render_popup(self.player, self.totals, self.cfg, self.note, shown, by_pos)

    # -- étiquettes et notes (clic droit) ----------------------------------
    def contextMenuEvent(self, event):
        if not self.player:
            return
        from fleur.hud.notes_dialog import apply_tag, tag_choices
        menu = QMenu(self)
        menu.addSection(self.player)
        current = self.note.tag if self.note else None
        for key, label, color in tag_choices(self.cfg):
            if key == "perso":
                continue
            action = menu.addAction(f"● {label}" if color else "Aucune étiquette")
            action.setCheckable(True)
            action.setChecked(key == current)
            action.triggered.connect(lambda _=False, k=key: self._set_tag(k, apply_tag))
        menu.addSeparator()
        menu.addAction("Étiquette perso et note…", self.edit_note)
        menu.exec(event.globalPos())

    def _set_tag(self, key, apply_tag) -> None:
        db = self.table.manager.db
        note = apply_tag(db.note(self.player), key, self.cfg)
        self.table.manager.save_note(note)

    def edit_note(self) -> None:
        from fleur.hud.notes_dialog import NoteDialog
        dialog = NoteDialog(self.table.manager.db.note(self.player), self.cfg)
        dialog.move(self.frameGeometry().bottomLeft() + QPoint(0, 4))
        if dialog.exec():
            self.table.manager.save_note(dialog.result_note())

    # -- déplacement à la souris ------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved = False

    def mouseMoveEvent(self, event):
        if self._drag_from is not None:
            self.move(event.globalPosition().toPoint() - self._drag_from)
            self._moved = True

    def mouseReleaseEvent(self, event):
        if self._drag_from is not None and self._moved:
            self.table.panel_moved(self)
        self._drag_from = None

    def mouseDoubleClickEvent(self, event):
        self.toggle_popup()

    def toggle_popup(self) -> None:
        if self._popup and self._popup.isVisible():
            self._popup.hide()
            return
        if not self._popup:
            self._popup = QLabel(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                                 | Qt.WindowType.WindowStaysOnTopHint)
            self._popup.setTextFormat(Qt.TextFormat.RichText)
            self._popup.setStyleSheet("background:#1d1d1d; color:#e8e8e8; border:1px solid #555; padding:4px;")
            self._popup.mousePressEvent = lambda _e: self._popup.hide()
        self._popup.setText(self.popup_html())
        self._popup.adjustSize()
        self._popup.move(self.frameGeometry().bottomLeft() + QPoint(0, 2))
        self._popup.show()

    def close_all(self) -> None:
        if self._popup:
            self._popup.close()
        self.close()


class TableHud:
    def __init__(self, manager: "HudManager", table: str, max_seats: int):
        self.manager = manager
        self.cfg = manager.cfg
        self.table = table
        self.max_seats = max_seats
        self.hwnd: int | None = None
        self.panels: dict[int, HudPanel] = {}  # siège Winamax -> panneau
        self.hero_seat: int | None = None
        self.last_hand_at = time.time()
        self.window_missing_since: float | None = None
        self.last_hand: Hand | None = None
        self._last_search = 0.0
        self._free_origin = QPoint(60 + 40 * (len(manager.tables) % 5), 60 + 40 * (len(manager.tables) % 5))

    # -- données ---------------------------------------------------------
    def update(self, hand: Hand) -> None:
        self.last_hand_at = time.time()
        self.last_hand = hand
        self.max_seats = hand.max_seats or self.max_seats
        if hand.hero:
            self.hero_seat = hand.seat_of(hand.hero)
        seated = {seat: name for seat, (name, _) in hand.seats.items()}
        if not self.cfg.get("show_hero") and hand.hero:
            seated = {s: n for s, n in seated.items() if n != hand.hero}
        totals = self.manager.db.totals(seated.values(), **stats_filter_args(self.cfg, hand))
        notes = self.manager.db.notes(seated.values())

        for seat in list(self.panels):
            if seat not in seated:
                self.panels.pop(seat).close_all()
        for seat, name in seated.items():
            panel = self.panels.get(seat)
            vis = visual_index(seat, self.hero_seat, self.max_seats, self.cfg.get("hero_at_bottom", True))
            if panel is None:
                panel = HudPanel(self, vis, self.cfg)
                self.panels[seat] = panel
            panel.visual = vis
            panel.set_player(name, totals.get(name, {}), notes.get(name))
        self.attach_window()
        self.reposition(force=True)

    # -- fenêtre de la table --------------------------------------------------
    def attach_window(self) -> None:
        if not win32.IS_WINDOWS:
            return
        if self.hwnd and win32.is_window(self.hwnd):
            return
        now = time.time()
        if now - self._last_search < WINDOW_SEARCH_INTERVAL_S:
            return
        self._last_search = now
        info = win32.find_table_window(self.table, self.cfg.get("window_title_contains", ""))
        self.hwnd = info.hwnd if info else None
        titles = [w.title for w in win32.list_windows()
                  if "winamax" in w.title.lower() or self.table.lower() in w.title.lower()]
        self.manager.diagnostics.window_search(self.table, info.title if info else None, titles)
        if self.hwnd:
            for panel in self.panels.values():
                win32.set_owner(int(panel.winId()), self.hwnd)

    def table_area(self) -> tuple[float, float, float, float] | None:
        """(x, y, largeur, hauteur) de la table en coordonnées Qt."""
        if not self.hwnd:
            return None
        rect = win32.client_rect(self.hwnd)
        if not rect or rect.width <= 0:
            return None
        area = _physical_to_logical(rect.x, rect.y, rect.width, rect.height)
        return fit_table(*area, self.cfg.get("table_aspect_ratio", 0))

    def reposition(self, force: bool = False) -> None:
        if self.manager.hidden:
            for p in self.panels.values():
                if p.isVisible():
                    p.hide()
            return
        if win32.IS_WINDOWS:
            if self.hwnd and not win32.is_window(self.hwnd):
                self.hwnd = None
            if not self.hwnd:
                self.attach_window()
            if self.hwnd and win32.is_minimized(self.hwnd):
                for p in self.panels.values():
                    p.hide()
                return
            self.window_missing_since = None if self.hwnd else (self.window_missing_since or time.time())

        area = self.table_area()
        if area is None:
            # Pas de fenêtre trouvée : HUD flottant que l'on peut déplacer
            if not force:
                return
            x0, y0, w, h = self._free_origin.x(), self._free_origin.y(), 800, 560
        else:
            x0, y0, w, h = area
        for panel in self.panels.values():
            if panel._drag_from is not None:
                continue
            rx, ry = self.manager.layouts.position(self.max_seats, panel.visual)
            target = QPoint(int(x0 + rx * w), int(y0 + ry * h))
            if panel.pos() != target:
                panel.move(target)
            if not panel.isVisible():
                panel.show()
                if self.hwnd:
                    win32.set_owner(int(panel.winId()), self.hwnd)

    def panel_moved(self, panel: HudPanel) -> None:
        area = self.table_area()
        if area is None:
            x0, y0, w, h = self._free_origin.x(), self._free_origin.y(), 800, 560
        else:
            x0, y0, w, h = area
        pos = panel.pos()
        self.manager.layouts.set_position(
            self.max_seats, panel.visual, (pos.x() - x0) / w, (pos.y() - y0) / h
        )
        self.manager.reposition_all(force=True)

    def expired(self) -> bool:
        if self.window_missing_since and time.time() - self.window_missing_since > WINDOW_GONE_GRACE_S \
                and time.time() - self.last_hand_at > WINDOW_GONE_GRACE_S:
            return True
        return time.time() - self.last_hand_at > TABLE_TIMEOUT_S and not self.hwnd

    def close(self) -> None:
        for p in self.panels.values():
            p.close_all()
        self.panels.clear()


def fit_table(x: float, y: float, w: float, h: float, ratio: float) -> tuple[float, float, float, float]:
    """Zone où la table est dessinée. Winamax garde les proportions de la
    table quand on élargit (ou rétrécit) la fenêtre et la centre : les
    positions des panneaux sont relatives à cette zone, pas à toute la fenêtre."""
    if not ratio or w <= 0 or h <= 0:
        return x, y, w, h
    if w / h > ratio:  # fenêtre trop large : bandes à gauche et à droite
        tw = h * ratio
        return x + (w - tw) / 2, y, tw, h
    th = w / ratio  # fenêtre trop haute : bandes en haut et en bas
    return x, y + (h - th) / 2, w, th


def _physical_to_logical(x: int, y: int, w: int, h: int) -> tuple[float, float, float, float]:
    """Convertit des pixels physiques Win32 en coordonnées Qt (écrans à 125 %, 150 %...)."""
    for screen in QGuiApplication.screens():
        geo = screen.geometry()
        dpr = screen.devicePixelRatio()
        native_w, native_h = geo.width() * dpr, geo.height() * dpr
        if geo.x() <= x < geo.x() + native_w and geo.y() <= y < geo.y() + native_h:
            return geo.x() + (x - geo.x()) / dpr, geo.y() + (y - geo.y()) / dpr, w / dpr, h / dpr
    dpr = QGuiApplication.primaryScreen().devicePixelRatio()
    return x / dpr, y / dpr, w / dpr, h / dpr


class HudManager(QObject):
    def __init__(self, db: Database, watcher: HistoryWatcher, cfg: dict, layouts_path: Path,
                 diagnostics=None):
        super().__init__()
        from fleur.diagnostics import Diagnostics
        self.db = db
        self.watcher = watcher
        self.cfg = cfg
        self.layouts_path = layouts_path
        self.layouts = Layouts(layouts_path)
        self.tables: dict[str, TableHud] = {}
        self.diagnostics = diagnostics or watcher.diagnostics or Diagnostics()
        self.hidden = False
        self.session_hands = 0

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll)
        self.poll_timer.start(cfg.get("poll_interval_ms", 1000))

        self.follow_timer = QTimer(self)
        self.follow_timer.timeout.connect(self.reposition_all)
        self.follow_timer.start(150)

    def poll(self) -> None:
        try:
            hands = self.watcher.poll()
        except Exception:  # ne jamais faire planter le HUD
            log.exception("erreur de lecture des historiques")
            return
        latest: dict[str, Hand] = {}
        for hand in hands:
            latest[hand.table] = hand
        for table, hand in latest.items():
            hud = self.tables.get(table)
            if hud is None:
                hud = TableHud(self, table, hand.max_seats)
                self.tables[table] = hud
                log.info("nouvelle table : %s (%s-max)", table, hand.max_seats)
            try:
                hud.update(hand)
            except Exception:
                log.exception("erreur d'affichage sur la table %s", table)
        if hands:
            self.session_hands += len(hands)
            log.info("%d nouvelle(s) main(s)", len(hands))
        for table in [t for t, h in self.tables.items() if h.expired()]:
            self.tables.pop(table).close()
            log.info("table fermée : %s", table)

    # -- actions du menu ----------------------------------------------------
    def set_hidden(self, hidden: bool) -> None:
        self.hidden = hidden
        if not hidden:
            self.reposition_all(force=True)

    def reload_config(self, cfg: dict) -> None:
        self.cfg.clear()
        self.cfg.update(cfg)
        self.refresh_all()
        log.info("configuration rechargée")

    def reset_layouts(self) -> None:
        try:
            self.layouts_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.layouts = Layouts(self.layouts_path)
        self.reposition_all(force=True)
        log.info("positions des panneaux réinitialisées")

    def refresh_all(self) -> None:
        for hud in self.tables.values():
            for panel in hud.panels.values():
                panel.close_all()
            hud.panels.clear()
            if hud.last_hand:
                hud.update(hud.last_hand)

    def save_note(self, note: PlayerNote) -> None:
        """Enregistre et met à jour tous les panneaux de ce joueur (multi-tables)."""
        try:
            self.db.save_note(note)
        except Exception:
            log.exception("enregistrement de la note impossible (%s)", note.player)
            return
        saved = self.db.note(note.player)
        for hud in self.tables.values():
            for panel in hud.panels.values():
                if panel.player == note.player:
                    panel.set_player(panel.player, panel.totals, saved)

    def reposition_all(self, force: bool = False) -> None:
        for hud in self.tables.values():
            hud.reposition(force=force)


def run_hud(db: Database, watcher: HistoryWatcher, cfg: dict, layouts_path: Path,
            history_dirs: list[Path] | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    manager = HudManager(db, watcher, cfg, layouts_path)
    from fleur.hud.tray import Tray
    tray = Tray(app, manager, history_dirs or [])
    app._fleur_refs = (manager, tray)  # garde les objets en vie
    log.info("HUD lancé. Ouvrez une table Winamax ; menu dans la barre des tâches, Ctrl+C pour quitter.")
    # Laisse Ctrl+C fonctionner dans la console
    import signal
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(300)
    return app.exec()


__all__ = ["run_hud", "render_lines", "render_popup"]
