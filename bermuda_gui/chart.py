"""Chart canvas (QPainter): candles + Ichimoku cloud + triangles + zones + time windows.

Rendering mirrors the web simulator (simulator/static/app.js) one-to-one.
Coordinates: x = bar index (float), y = price; analysis arrays arrive ATR-normalised
and are multiplied by atr on the way to screen.
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (QPainter, QPen, QColor, QFont, QPainterPath, QPolygonF,
                         QBrush, QFontMetrics)
from PyQt6.QtWidgets import QWidget

import bermuda_gui.theme as T
from bermuda_gui.data import DEFAULT_LAYERS

FUTURE_PAD = 55
MONO = 'Consolas'


def _col(rgb, alpha: int = 255) -> QColor:
    if isinstance(rgb, str):
        c = QColor(rgb)
        c.setAlpha(alpha)
        return c
    return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), alpha)


class ChartWidget(QWidget):
    seek_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(430)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.data: Optional[dict] = None
        self.an: Optional[dict] = None          # analyse payload
        self.xc: int = 0
        self.visible_bars: float = 150.0
        self.layers: dict = dict(DEFAULT_LAYERS)
        self._mouse: Optional[QPointF] = None

    # ------------------------------------------------------------- wiring
    def set_layers(self, layers: dict):
        self.layers.update(layers)
        self.update()

    def set_data(self, data: dict):
        self.data = data
        self.update()

    def set_analysis(self, payload: dict):
        self.an = payload
        self.update()

    def set_xc(self, xc: int):
        self.xc = int(xc)
        self.update()

    # -------------------------------------------------------------- math
    @property
    def view(self):
        x1 = self.xc + FUTURE_PAD
        return (x1 - self.visible_bars, x1)

    def _y_range(self, view):
        d = self.data
        v0, v1 = view
        lo = max(0, int(math.floor(v0))); hi = min(d['n'] - 1, int(math.ceil(v1)))
        mn, mx = float('inf'), float('-inf')
        for i in range(lo, hi + 1):
            if d['low'][i] < mn: mn = d['low'][i]
            if d['high'][i] > mx: mx = d['high'][i]
        if self.an and self.layers.get('zones'):
            a = self.an['atr'] or 1.0
            for z in self.an['zones']:
                for p in z['poly']:
                    y = p[1] * a
                    mn = min(mn, y); mx = max(mx, y)
        if not math.isfinite(mn) or not math.isfinite(mx):
            mn, mx = 0.0, 1.0
        pad = (mx - mn) * 0.09 or mx * 0.05 or 1.0
        return mn - pad, mx + pad

    def _x(self, x, view, W):
        return (x - view[0]) / (view[1] - view[0]) * W

    def _y(self, y, yr, H):
        return H - (y - yr[0]) / (yr[1] - yr[0]) * H

    @staticmethod
    def _nice_ticks(mn, mx, count=6):
        span = mx - mn
        if not (span > 0) or not math.isfinite(span):
            return [mn]
        raw = span / count
        mag = 10 ** math.floor(math.log10(raw))
        step = next((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), mag)
        ticks, v = [], math.ceil(mn / step) * step
        while v <= mx:
            ticks.append(v); v += step
        return ticks

    # ---------------------------------------------------------- painting
    def paintEvent(self, _ev):
        if self.data is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        W, H = self.width(), self.height()
        d, an = self.data, self.an
        view = self.view
        yr = self._y_range(view)
        atr = (an['atr'] if an else 1.0) or 1.0
        n = d['n']

        # background
        p.fillRect(0, 0, W, H, QColor('#0d1119'))

        # grid + y labels
        p.setFont(QFont(MONO, 8))
        fm = QFontMetrics(p.font())
        for t in self._nice_ticks(yr[0], yr[1], 6):
            y = self._y(t, yr, H)
            p.setPen(QPen(_col(T.GRID[:3], 26), 1))
            p.drawLine(0, int(y), W, int(y))
            p.setPen(QColor(T.GRID_TEXT))
            p.drawText(6, int(y) - 3, f'{t:.2f}')

        # x date ticks
        tick_every = max(1, int(round(self.visible_bars / 6)))
        first = int(math.ceil(view[0] / tick_every) * tick_every)
        i = first
        while i < min(view[1], n):
            if i >= 0:
                x = self._x(i, view, W)
                p.setPen(QPen(_col(T.GRID[:3], 16), 1)); p.drawLine(int(x), 0, int(x), H)
                p.setPen(QColor(T.GRID_TEXT))
                p.drawText(QRectF(x - 30, H - 16, 60, 14), Qt.AlignmentFlag.AlignCenter, d['dates'][i][5:])
            i += tick_every

        # future-projection divider (beyond last real bar)
        n_end = n - 1
        if view[1] > n_end:
            x = self._x(n_end + 0.5, view, W)
            p.fillRect(QRectF(x, 0, W - x, H), _col((148, 163, 184), 13))
            pen = QPen(_col((148, 163, 184), 90), 1, Qt.PenStyle.DashLine)
            p.setPen(pen); p.drawLine(int(x), 0, int(x), H)
            p.setPen(_col((120, 128, 152), 200))
            p.drawText(int(x) + 6, 14, 'last real bar →')

        # time windows (behind everything)
        if an and self.layers.get('windows'):
            for wa, wb in an['windows']:
                if wb < view[0] or wa > view[1]:
                    continue
                xA = self._x(wa - 0.5, view, W); xB = self._x(wb + 0.5, view, W)
                p.fillRect(QRectF(xA, 0, xB - xA, H), _col(T.WINDOW_C, 8))
                p.fillRect(QRectF(xA, H - 6, xB - xA, 5), _col(T.WINDOW_C, 200))

        # Ichimoku cloud (trapezoids)
        if an and self.layers.get('cloud'):
            sa, sb = an['sa'], an['sb']
            m0 = max(0, int(math.floor(view[0]))); m1 = min(len(sa) - 1, int(math.ceil(view[1])))
            for i in range(m0, m1):
                sa0, sb0, sa1, sb1 = sa[i], sb[i], sa[i + 1], sb[i + 1]
                if None in (sa0, sb0, sa1, sb1):
                    continue
                proj = i >= n_end
                up = sa0 >= sb0 and sa1 >= sb1
                dn = sa0 < sb0 and sa1 < sb1
                rgb = T.CLOUD_UP if up else (T.CLOUD_DOWN if dn else (148, 163, 184))
                alpha = 26 if proj else 77
                poly = QPolygonF([
                    QPointF(self._x(i, view, W), self._y(sa0 * atr, yr, H)),
                    QPointF(self._x(i + 1, view, W), self._y(sa1 * atr, yr, H)),
                    QPointF(self._x(i + 1, view, W), self._y(sb1 * atr, yr, H)),
                    QPointF(self._x(i, view, W), self._y(sb0 * atr, yr, H)),
                ])
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_col(rgb, alpha))
                p.drawPolygon(poly)

        # candles
        if self.layers.get('candles'):
            cw = W / (view[1] - view[0])
            body_w = min(14.0, max(1.2, cw * 0.62))
            lo = max(0, int(math.floor(view[0]))); hi = min(n - 1, int(math.ceil(view[1])))
            for i in range(lo, hi + 1):
                future = i > self.xc
                up = d['close'][i] >= d['open'][i]
                col = _col(T.UP if up else T.DOWN, int(255 * (0.22 if future else 1.0)))
                x = self._x(i, view, W)
                p.setPen(QPen(col, max(1.0, min(1.6, cw * 0.12))))
                p.drawLine(QPointF(x, self._y(d['high'][i], yr, H)), QPointF(x, self._y(d['low'][i], yr, H)))
                yo, yc = self._y(d['open'][i], yr, H), self._y(d['close'][i], yr, H)
                p.fillRect(QRectF(x - body_w / 2, min(yo, yc), body_w, max(1.0, abs(yc - yo))), col)

        # future veil relative to analysis bar
        if an and self.layers.get('future') and self.xc < view[1]:
            x = self._x(self.xc + 0.5, view, W)
            if x < W:
                p.fillRect(QRectF(x, 0, W - x, H), _col((6, 9, 15), 82))

        # Senkou B (dotted)
        if an and self.layers.get('sb'):
            p.setPen(QPen(_col((148, 163, 184), 190), 1, Qt.PenStyle.DotLine))
            self._polyline(p, an['sb'], view, yr, H, W, atr, skip_out_of_view=True)

        # Senkou A (ivory, glowed)
        if an and self.layers.get('sa'):
            pen = QPen(QColor('#f5efdc'), 1.8)
            p.setPen(pen)
            self._polyline(p, an['sa'], view, yr, H, W, atr, skip_out_of_view=True)

        # steep legs (U teal / D rose)
        if an and self.layers.get('steeps'):
            for s in an['steeps']:
                x0, y0, x1, y1, cls = s
                p.setPen(QPen(_col((52, 211, 153) if cls == 'U' else (251, 113, 133), 240), 2))
                p.drawLine(QPointF(self._x(x0, view, W), self._y(y0 * atr, yr, H)),
                           QPointF(self._x(x1, view, W), self._y(y1 * atr, yr, H)))

        # triangles: local extended dashed legs + solid legs + apex dots
        if an and self.layers.get('tris'):
            p.setFont(QFont(MONO, 7, QFont.Weight.Bold))
            for t in an['tris']:
                span_l, span_r = min(t['A'][0], t['B'][0]), max(t['A'][2], t['B'][2])
                xA, xB = span_l - 18, span_r + 18
                p.setPen(QPen(_col((229, 185, 92), 82), 1.1, Qt.PenStyle.DashLine))
                for leg in (t['A'], t['B']):
                    m = leg[5]; px = leg[0]; py = leg[1]
                    ext = lambda x: py + m * (x - px)
                    p.drawLine(QPointF(self._x(xA, view, W), self._y(ext(xA) * atr, yr, H)),
                               QPointF(self._x(xB, view, W), self._y(ext(xB) * atr, yr, H)))
                p.setPen(QPen(QColor(T.GOLD), 2.2))
                for leg in (t['A'], t['B']):
                    p.drawLine(QPointF(self._x(leg[0], view, W), self._y(leg[1] * atr, yr, H)),
                               QPointF(self._x(leg[2], view, W), self._y(leg[3] * atr, yr, H)))
                ax, ay = self._x(t['apex'][0], view, W), self._y(t['apex'][1] * atr, yr, H)
                p.setPen(QPen(QColor('#231a05'), 1)); p.setBrush(QColor(T.GOLD))
                p.drawEllipse(QPointF(ax, ay), 3.4, 3.4)
                dot = '#f2a1c0' if t['col'] == 1 else ('#7bc67e' if t['col'] == -1 else '#8b94ad')
                p.setBrush(QColor(dot)); p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(self._x(t['mid'][0], view, W), self._y(t['mid'][1] * atr, yr, H)), 2.2, 2.2)

        # wedges (optional; bounding wedges of zones glow red)
        zone_ws = set()
        if an and self.layers.get('zones'):
            for z in an['zones']:
                for k, opens in (z.get('wedge_ids') or []):
                    zone_ws.add((k, opens))
        if an and self.layers.get('wedges'):
            for w in an['wedges']:
                used = (w['k'], w['opens']) in zone_ws
                pen = QPen(_col((255, 90, 90) if used else (226, 232, 255), 230 if used else 70),
                           1.8 if used else 1, Qt.PenStyle.DashLine)
                p.setPen(pen)
                apex = w['apex']
                for ux, uy in ((-1.0, -w['mL']), (1.0, w['mR'])):
                    length = math.hypot(ux, uy); L = 240.0
                    ex, ey = apex[0] + ux / length * L, apex[1] + uy / length * L
                    p.drawLine(QPointF(self._x(apex[0], view, W), self._y(apex[1] * atr, yr, H)),
                               QPointF(self._x(ex, view, W), self._y(ey * atr, yr, H)))

        # zones (black fill + red/orange edge + apex star + cascade pill labels)
        if an and self.layers.get('zones'):
            p.setFont(QFont('Tahoma', 8, QFont.Weight.Bold))
            pending: list[tuple] = []
            for zi, z in enumerate(an['zones']):
                timed = bool(z.get('timed'))
                path = QPainterPath()
                for i, pt in enumerate(z['poly']):
                    x = self._x(pt[0], view, W); y = self._y(pt[1] * atr, yr, H)
                    path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
                path.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(_col((8, 8, 10), 200))
                p.drawPath(path)
                edge = QColor(T.ZONE_TIMED if timed else T.ZONE_EDGE)
                p.setPen(QPen(edge, 1.7)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
                self._star(p, self._x(z['apex'][0], view, W), self._y(z['apex'][1] * atr, yr, H),
                           6.2, QColor('#ffd166'), QColor('#6b4d10'))
                label = f"Z{zi + 1} {z['kind'].upper()} · cover={z['cover']}"
                tfm = QFontMetrics(p.font())
                tw = tfm.horizontalAdvance(label) + 14
                ax = self._x(z['apex'][0], view, W); ay = self._y(z['apex'][1] * atr, yr, H)
                pending.append((label, tw, ax, ay, edge, timed))

            if pending:  # de-overlap pills vertically, top-to-bottom
                pending.sort(key=lambda t: t[3])
                placed: list[tuple[float, float]] = []
                for label, tw, ax, ay, edge, timed in pending:
                    px = min(max(ax + 10, 4), W - tw - 4)
                    py = ay - 26
                    for prev_py, prev_h in placed:
                        if py < prev_py + prev_h + 3 and py + 15 > prev_py:
                            py = prev_py + prev_h + 3
                    py = min(max(py, 2), H - 18)
                    placed.append((py, 15))
                    rect = QRectF(px, py, tw, 15)
                    p.setPen(QPen(edge, 0.8)); p.setBrush(_col((64, 38, 4) if timed else (26, 9, 11), 235))
                    p.drawRoundedRect(rect, 7, 7)
                    p.setPen(QColor('#ffd9a0' if timed else '#ffc4c4'))
                    p.drawText(QRectF(px + 7, py, tw - 10, 15), Qt.AlignmentFlag.AlignVCenter, label)

        # cursor at analysis bar
        cx = self._x(self.xc, view, W)
        pen = QPen(_col((229, 185, 92), 150), 1.2, Qt.PenStyle.DashLine)
        p.setPen(pen); p.drawLine(int(cx), 0, int(cx), H)
        p.setBrush(QColor(T.GOLD)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, self._y(d['close'][self.xc], yr, H)), 3.2, 3.2)

        # crosshair + info box
        if self._mouse is not None:
            m = self._mouse
            p.setPen(QPen(_col((232, 236, 246), 80), 1, Qt.PenStyle.DashLine))
            p.drawLine(int(m.x()), 0, int(m.x()), H)
            p.drawLine(0, int(m.y()), W, int(m.y()))
            self._draw_crosshair_info(p, m, view, W, H)

        p.end()

    # ------------------------------------------------------------ helpers
    def _polyline(self, p, arr, view, yr, H, W, atr, skip_out_of_view=False):
        started = False
        path = QPainterPath()
        for i, v in enumerate(arr):
            if v is None:
                started = False
                continue
            x = self._x(i, view, W)
            if skip_out_of_view and (i < view[0] - 1 or i > view[1] + 1):
                started = False
                continue
            y = self._y(v * atr, yr, H)
            if started:
                path.lineTo(x, y)
            else:
                path.moveTo(x, y); started = True
        p.drawPath(path)

    @staticmethod
    def _star(p: QPainter, cx: float, cy: float, r: float, fill: QColor, stroke: QColor):
        path = QPainterPath()
        for i in range(10):
            rad = r if i % 2 == 0 else r * 0.45
            ang = -math.pi / 2 + i * math.pi / 5
            x, y = cx + math.cos(ang) * rad, cy + math.sin(ang) * rad
            path.lineTo(x, y) if i else path.moveTo(x, y)
        path.closeSubpath()
        p.setPen(QPen(stroke, 1)); p.setBrush(fill)
        p.drawPath(path)

    def _draw_crosshair_info(self, p, m, view, W, H):
        d = self.data
        v0, v1 = view
        bar = int(round(v0 + m.x() / max(1, W) * (v1 - v0)))
        bar = max(0, min(d['n'] - 1, bar))
        chg = (d['close'][bar] / d['close'][bar - 1] - 1) * 100 if bar > 0 else 0.0
        up = chg >= 0
        lines = [(d['dates'][bar], T.GOLD),
                 (f"O {d['open'][bar]:.2f}   H {d['high'][bar]:.2f}", T.TEXT),
                 (f"L {d['low'][bar]:.2f}   C {d['close'][bar]:.2f}", T.TEXT),
                 (f"CHG {'+' if up else ''}{chg:.2f}%", T.UP if up else T.DOWN)]
        p.setFont(QFont(MONO, 8))
        fm = QFontMetrics(p.font())
        bw = max(fm.horizontalAdvance(t[0]) for t in lines) + 18
        bh = len(lines) * 16 + 10
        bx = min(max(m.x() + 14, 4), W - bw - 4)
        by = min(max(m.y() + 12, 4), H - bh - 4)
        p.setPen(QPen(QColor(T.LINE), 1)); p.setBrush(_col((13, 17, 25), 242))
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 7, 7)
        for j, (text, color) in enumerate(lines):
            p.setPen(QColor(color) if isinstance(color, str) else QColor(*color))
            p.drawText(QRectF(bx + 9, by + 5 + j * 16, bw - 12, 16), Qt.AlignmentFlag.AlignVCenter, text)

    # ------------------------------------------------------------ events
    def wheelEvent(self, ev):
        factor = 1.12 if ev.angleDelta().y() < 0 else 1 / 1.12
        self.visible_bars = min(300.0, max(40.0, self.visible_bars * factor))
        self.update()

    def mouseMoveEvent(self, ev):
        self._mouse = QPointF(ev.position())
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton or self.data is None:
            return
        v0, v1 = self.view
        bar = round(v0 + ev.position().x() / max(1, self.width()) * (v1 - v0))
        self.seek_requested.emit(max(0, min(self.data['n'] - 1, bar)))

    def leaveEvent(self, _ev):
        self._mouse = None
        self.update()


class MinimapWidget(QWidget):
    """Full-history overview: close line + zone-hit ticks + cursor; click/drag to seek."""

    seek_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.data: Optional[dict] = None
        self.xc = 0
        self.hits: list[dict] = []
        self.sweep_progress: Optional[tuple[int, int]] = None   # (done, total)
        self._dragging = False

    def set_data(self, data): self.data = data; self.update()
    def set_xc(self, xc): self.xc = int(xc); self.update()
    def set_hits(self, hits): self.hits = list(hits or []); self.update()
    def set_sweep_progress(self, done, total): self.sweep_progress = (done, total); self.update()
    def clear_sweep_progress(self): self.sweep_progress = None; self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        W, H = self.width(), self.height()
        p.fillRect(0, 0, W, H, QColor('#0d1119'))
        p.setPen(QPen(QColor(T.LINE_SOFT), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 9, 9)
        d = self.data
        if d is None:
            p.end(); return
        closes = d['close']; n = d['n']
        mn, mx = float(closes.min()), float(closes.max())
        pad = (mx - mn) * 0.06 or 1.0
        mn -= pad; mx += pad

        def px(i): return i / (n - 1) * (W - 10) + 5
        def py(v): return H - 8 - (v - mn) / (mx - mn) * (H - 18)

        path = QPainterPath()
        for i in range(n):
            x, y = px(i), py(closes[i])
            path.lineTo(x, y) if i else path.moveTo(x, y)
        p.setPen(QPen(_col((148, 163, 184), 165), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        for h in self.hits:
            col = _col(T.SUPPORT if h['kind'] == 'support' else T.RESISTANCE, 230)
            p.setPen(QPen(col, min(3.4, 1.2 + h['cover'] * 0.5)))
            x = px(h['xc'])
            p.drawLine(QPointF(x, H - 3), QPointF(x, H - 6 - h['cover'] * 3.2))

        cx = px(self.xc)
        p.setPen(QPen(QColor(T.GOLD), 1.6)); p.drawLine(int(cx), 2, int(cx), H - 2)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(T.GOLD))
        tri = QPolygonF([QPointF(cx - 5, 0), QPointF(cx + 5, 0), QPointF(cx, 7)])
        p.drawPolygon(tri)

        if self.sweep_progress:
            done, total = self.sweep_progress
            frac = (done / total) if total else 0.0
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(_col((229, 185, 92), 90))
            p.drawRoundedRect(QRectF(5, 2, (W - 10) * frac, 3), 1.5, 1.5)
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.data is not None:
            self._dragging = True
            self._seek(ev.position().x())

    def mouseMoveEvent(self, ev):
        if self._dragging and self.data is not None:
            self._seek(ev.position().x())

    def mouseReleaseEvent(self, _ev):
        self._dragging = False

    def _seek(self, x):
        t = min(1.0, max(0.0, (x - 5) / max(1, self.width() - 10)))
        self.seek_requested.emit(round(t * (self.data['n'] - 1)))
