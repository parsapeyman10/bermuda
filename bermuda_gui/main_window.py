"""Main window: transport bar + chart/minimap + side panel. Thin UI layer —
all heavy lifting lives in data.AnalyseService and chart.*."""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QShortcut, QKeySequence
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QPushButton, QLabel, QComboBox, QSlider, QCheckBox, QScrollArea,
                             QFrame, QStatusBar, QFileDialog, QProgressBar, QSizePolicy,
                             QSplitter, QMessageBox)

import bermuda_gui.paths  # noqa: F401  (sys.path bootstrap)
from bermuda_gui.data import AnalyseService, PARAM_SPECS, LAYER_SPECS, DEFAULT_PARAMS, DEFAULT_LAYERS
from bermuda_gui.chart import ChartWidget, MinimapWidget
import bermuda_gui.theme as T

MIN_XC = 60
BASE_BARS_PER_SEC = 5.0


class SweepWorker(QThread):
    progress = pyqtSignal(int, int)
    finished_hits = pyqtSignal(list)

    def __init__(self, service: AnalyseService, ds: str, params: dict, step: int = 2,
                 setup: str = 'both'):
        super().__init__()
        self._service, self._ds, self._params, self._step, self._setup = service, ds, dict(params), step, setup

    def run(self):  # pragma: no cover - exercised via offscreen smoke test
        hits = self._service.sweep(self._ds, self._params, self._step,
                                   progress=lambda i, total: self.progress.emit(i, total),
                                   setup=self._setup)
        self.finished_hits.emit(hits)


def card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName('Card')
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(6)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName('CardTitle')
        lay.addWidget(lbl)
    return frame, lay


def kv_row(parent_layout, label: str) -> QLabel:
    row = QHBoxLayout()
    k = QLabel(label); k.setObjectName('Muted')
    v = QLabel('—')
    v.setAlignment(Qt.AlignmentFlag.AlignLeft)
    row.addWidget(k); row.addStretch(1); row.addWidget(v)
    parent_layout.addLayout(row)
    return v


class MainWindow(QMainWindow):
    def __init__(self, service: Optional[AnalyseService] = None):
        super().__init__()
        self.setWindowTitle('Black Bermuda — شبیه‌ساز دسکتاپی')
        self.setDockNestingEnabled(False)

        self.service = service or AnalyseService()
        self.params = dict(DEFAULT_PARAMS)
        self.layers = dict(DEFAULT_LAYERS)
        self.data: Optional[dict] = None
        self.n = 0
        self.xc = MIN_XC
        self.ds = 'shock'
        self.setup = 'both'
        self.fractal: Optional[dict] = None
        self.hits: list[dict] = []
        self._sweep_worker: Optional[SweepWorker] = None
        self._autosought = False
        self._user_seek = False
        self._param_timer = QTimer(self, singleShot=True)
        self._param_timer.setInterval(260)
        self._param_timer.timeout.connect(self._on_params_committed)

        self._build_ui()
        self._connect()
        self.set_dataset(self.ds)

    # ================================================================ UI build
    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)

        root.addWidget(self._build_transport())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)
        splitter.addWidget(self._build_chart_column())
        splitter.addWidget(self._build_side_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1080, 360])
        root.addWidget(splitter, 1)

        self.setCentralWidget(central)
        status = QStatusBar(self)
        status.showMessage('پژوهش / آموزش — هیچ edge معاملاتی ادعا نمی‌شود  |  GOOG واقعی + سناریوهای seeded  |  بدون lookahead در محاسبه')
        self.setStatusBar(status)
        self.resize(1500, 920)
        self.setMinimumSize(1150, 700)

    def _build_transport(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName('Card')
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        # dataset picker
        ds_label = QLabel('داده:')
        ds_label.setObjectName('Muted')
        self.dataset_combo = QComboBox()
        self._populate_datasets('shock')
        lay.addWidget(ds_label); lay.addWidget(self.dataset_combo)
        self.btn_csv = QPushButton('＋ CSV'); self.btn_csv.setObjectName('Ghost')
        self.btn_csv.setToolTip('بارگذاری CSV با ستون‌های date,open,high,low,close (حداقل ۲۰۰ بار) — فقط همین دستگاه')
        lay.addWidget(self.btn_csv)
        lay.addSpacing(6)

        # setup selector (5.2/5.3)
        setup_label = QLabel('ستاپ:'); setup_label.setObjectName('Muted')
        self.setup_combo = QComboBox(); self.setup_combo.setMinimumWidth(110)
        self.setup_combo.addItem('هر دو', 'both')
        self.setup_combo.addItem('فروش ↑ مقاومت', 'sell')
        self.setup_combo.addItem('خرید ↓ حمایت', 'buy')
        self.setup_combo.setToolTip('جهت setup (روش 5.2/5.3): هر دو · فقط فروش · فقط خرید')
        lay.addWidget(setup_label); lay.addWidget(self.setup_combo)
        lay.addSpacing(6)

        # transport buttons
        self.btn_start = QPushButton('⏮'); self.btn_start.setToolTip('اول تاریخچه')
        self.btn_back10 = QPushButton('−10')
        self.btn_back1 = QPushButton('◀')
        self.btn_play = QPushButton('▶'); self.btn_play.setObjectName('PlayButton'); self.btn_play.setToolTip('پخش / توقف (Space)')
        self.btn_fwd1 = QPushButton('▶'); self.btn_fwd1.setToolTip('یک بار جلو')
        self.btn_fwd10 = QPushButton('+10')
        self.btn_end = QPushButton('⏭'); self.btn_end.setToolTip('آخر تاریخچه')
        for b in (self.btn_start, self.btn_back10, self.btn_back1, self.btn_play,
                  self.btn_fwd1, self.btn_fwd10, self.btn_end):
            b.setFixedHeight(38); lay.addWidget(b)
        lay.addSpacing(4)

        # speed
        speed_label = QLabel('سرعت:'); speed_label.setObjectName('Muted')
        self.speed_combo = QComboBox(); self.speed_combo.setMinimumWidth(70)
        for v, t in ((0.5, '0.5×'), (1, '1×'), (2, '2×'), (4, '4×'), (8, '8×')):
            self.speed_combo.addItem(t, v)
        self.speed_combo.setCurrentIndex(1)
        lay.addWidget(speed_label); lay.addWidget(self.speed_combo)

        # seek slider
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(MIN_XC, 100)
        self.seek_slider.setMinimumWidth(160)
        lay.addWidget(self.seek_slider, 1)

        # playhead readout
        ph = QVBoxLayout(); ph.setSpacing(0)
        self.ph_date = QLabel('—'); self.ph_date.setObjectName('DateGold')
        self.ph_bar = QLabel(''); self.ph_bar.setObjectName('MutedSmall')
        ph.addWidget(self.ph_date); ph.addWidget(self.ph_bar)
        lay.addLayout(ph)

        self.btn_fractal = QPushButton('⧖ Fractal'); self.btn_fractal.setObjectName('Ghost')
        self.btn_fractal.setToolTip('تحلیل Fractal (بخش 7.2/7.3): زیر-تایم‌فریم synthetic قطعی — '
                                    'دموی هندسی آموزشی، نه داده‌ی واقعی intraday. برای تمرین واقعی CSV واقعی را بارگذاری کنید.')
        lay.addWidget(self.btn_fractal)
        self.btn_export = QPushButton('⬇ PNG'); self.btn_export.setObjectName('Ghost')
        lay.addWidget(self.btn_export)
        return bar

    def _build_chart_column(self) -> QWidget:
        col = QFrame()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(6)

        self.chart = ChartWidget()
        self.chart.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self.chart, 1)

        cap = QHBoxLayout()
        lbl = QLabel('Zone map — کل تاریخچه (کلیک برای جهش)')
        lbl.setObjectName('MutedSmall')
        cap.addWidget(lbl); cap.addStretch(1)
        self.sweep_status = QLabel('')
        self.sweep_status.setObjectName('MutedSmall')
        cap.addWidget(self.sweep_status)
        lay.addLayout(cap)

        self.minimap = MinimapWidget()
        lay.addWidget(self.minimap)
        return col

    def _build_side_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(330)
        scroll.setMaximumWidth(430)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(4, 2, 4, 4)
        lay.setSpacing(10)

        # ---- status card
        frame, lay1 = card('وضعیت این بار')
        head = QHBoxLayout()
        self.stat_date = QLabel('—'); self.stat_date.setObjectName('DateGold')
        head.addWidget(self.stat_date); head.addStretch(1)
        lay1.addLayout(head)
        grid = QGridLayout(); grid.setSpacing(6)
        self.ohlc_labels = {}
        for i, (k, label) in enumerate((('open', 'باز'), ('high', 'بیشترین'), ('low', 'کمترین'),
                                        ('close', 'بسته'), ('chg', 'تغییر'))):
            cell = QVBoxLayout(); cell.setSpacing(0)
            t = QLabel(label); t.setObjectName('MutedSmall'); t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v = QLabel('—'); v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.setFont(QFont('Consolas', 9, QFont.Weight.Bold))
            cell.addWidget(t); cell.addWidget(v)
            grid.addLayout(cell, 0, i)
            self.ohlc_labels[k] = v
        lay1.addLayout(grid)
        self.v_atr = kv_row(lay1, 'ATR(14)')
        self.v_sa = kv_row(lay1, 'Senkou A (+26)')
        self.v_sb = kv_row(lay1, 'Senkou B (+26)')
        self.v_cloud = kv_row(lay1, 'وضعیت ابر')
        self.v_double = QLabel('✳ Double Bermuda — قیمت + Chikou هر دو داخل zone')
        self.v_double.setObjectName('DoubleBermuda')
        self.v_double.setWordWrap(True)
        self.v_double.setVisible(False)
        lay1.addWidget(self.v_double)
        lay.addWidget(frame)

        # ---- triangles card
        frame, lay2 = card('')
        row = QHBoxLayout()
        t = QLabel('مثلث‌ها'); t.setObjectName('CardTitle'); row.addWidget(t)
        self.tri_count = QLabel('0'); self.tri_count.setObjectName('Count'); row.addStretch(1); row.addWidget(self.tri_count)
        lay2.addLayout(row)
        self.tri_list = QLabel('—'); self.tri_list.setWordWrap(True)
        self.tri_list.setTextFormat(Qt.TextFormat.RichText)
        self.tri_list.setObjectName('Muted')
        lay2.addWidget(self.tri_list)
        lay.addWidget(frame)

        # ---- zones card
        frame, lay3 = card('')
        row = QHBoxLayout()
        t = QLabel('Zoneها'); t.setObjectName('CardTitle'); row.addWidget(t)
        self.zone_count = QLabel('0'); self.zone_count.setObjectName('Count'); row.addStretch(1); row.addWidget(self.zone_count)
        lay3.addLayout(row)
        self.zone_list = QLabel('—'); self.zone_list.setWordWrap(True)
        self.zone_list.setTextFormat(Qt.TextFormat.RichText)
        self.zone_list.setObjectName('Muted')
        lay3.addWidget(self.zone_list)
        lay.addWidget(frame)

        # ---- time windows card
        frame, lay4 = card('پنجره‌های زمانی')
        self.v_win_active = kv_row(lay4, 'فعال روی این بار')
        self.v_win_zone = kv_row(lay4, 'Zone ∩ پنجره')
        self.v_win_total = kv_row(lay4, 'کل پنجره‌ها (این تحلیل)')
        self.v_sb_flats = kv_row(lay4, 'سگمنت‌های تخت Senkou B')
        hint = QLabel('Senkou B باید تخت باشد (بلوک) و ۲۶ بار قبل‌تر هم تخت (چک x−26).')
        hint.setObjectName('MutedSmall'); hint.setWordWrap(True)
        lay4.addWidget(hint)
        lay.addWidget(frame)

        # ---- §8 levels card
        frame, layL = card('سطوح زمانی §8')
        self.v_lv_hor = kv_row(layL, 'افقی (رأس مثلث نهایی)')
        self.v_lv_levels = kv_row(layL, 'سطوح قیمت (تلاقی پاها)')
        self.v_lv_note = QLabel('—')
        self.v_lv_note.setObjectName('MutedSmall')
        self.v_lv_note.setWordWrap(True)
        layL.addWidget(self.v_lv_note)
        lay.addWidget(frame)

        # ---- layers card
        frame, lay5 = card('لایه‌ها')
        grid = QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(4)
        self.layer_checks: dict[str, QCheckBox] = {}
        for i, (key, label) in enumerate(LAYER_SPECS):
            cb = QCheckBox(label)
            cb.setChecked(self.layers.get(key, True))
            cb.stateChanged.connect(lambda _s, k=key: self._layer_toggled(k))
            self.layer_checks[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        lay5.addLayout(grid)
        lay.addWidget(frame)

        # ---- params card
        frame, lay6 = card('')
        row = QHBoxLayout()
        t = QLabel('پارامترهای آشکارساز'); t.setObjectName('CardTitle'); row.addWidget(t)
        self.btn_reset = QPushButton('بازنشانی'); self.btn_reset.setObjectName('Tiny')
        row.addStretch(1); row.addWidget(self.btn_reset)
        lay6.addLayout(row)
        self.param_rows: dict[str, tuple[QSlider, QLabel]] = {}
        for spec in PARAM_SPECS:
            row = QHBoxLayout(); row.setSpacing(8)
            name = QLabel(spec.label); name.setToolTip(spec.hint)
            name.setFixedWidth(118)
            slider = QSlider(Qt.Orientation.Horizontal)
            steps = int(round((spec.hi - spec.lo) / spec.step))
            slider.setRange(0, steps)
            slider.setValue(int(round((spec.default - spec.lo) / spec.step)))
            value = QLabel(spec.fmt.format(spec.default))
            value.setFixedWidth(56)
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setFont(QFont('Consolas', 8, QFont.Weight.Bold))
            slider.valueChanged.connect(lambda v, s=spec, val=value: self._param_changed(s, v, val))
            row.addWidget(name); row.addWidget(slider, 1); row.addWidget(value)
            lay6.addLayout(row)
            self.param_rows[spec.key] = (slider, value)
        hint = QLabel('پیش‌فرض روزانه: deg=۸ · eps=۰٫۲ · min_dy=۰٫۵ · min_dx=۲ (README v0.4)')
        hint.setObjectName('MutedSmall'); hint.setWordWrap(True); lay6.addWidget(hint)
        self.sweep_bar = QProgressBar(); self.sweep_bar.setRange(0, 100); self.sweep_bar.setValue(0)
        lay6.addWidget(self.sweep_bar)
        lay.addWidget(frame)

        lay.addStretch(1)
        scroll.setWidget(host)
        return scroll

    # ============================================================= signals
    def _connect(self):
        self.dataset_combo.currentIndexChanged.connect(lambda _i: self.set_dataset(self.dataset_combo.currentData()))
        self.btn_csv.clicked.connect(self.open_csv)
        self.setup_combo.currentIndexChanged.connect(lambda _i: self._on_setup_changed())
        self.btn_fractal.clicked.connect(self.run_fractal)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_back10.clicked.connect(lambda: self.seek(self.xc - 10))
        self.btn_back1.clicked.connect(lambda: self.seek(self.xc - 1))
        self.btn_fwd1.clicked.connect(lambda: self.seek(self.xc + 1))
        self.btn_fwd10.clicked.connect(lambda: self.seek(self.xc + 10))
        self.btn_start.clicked.connect(lambda: self.seek(MIN_XC))
        self.btn_end.clicked.connect(lambda: self.seek(self.n - 1))
        self.seek_slider.valueChanged.connect(self._seek_slider_changed)
        self.btn_export.clicked.connect(self.export_png)
        self.btn_reset.clicked.connect(self.reset_params)
        self.chart.seek_requested.connect(lambda i: self.seek(i))
        self.minimap.seek_requested.connect(lambda i: self.seek(i))

        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._play_tick)

        shortcut_map = [
            ('Space', self.toggle_play),
            ('Left', lambda: self._arrow(-1)),
            ('Right', lambda: self._arrow(+1)),
            ('Shift+Left', lambda: self.seek(self.xc - 10)),
            ('Shift+Right', lambda: self.seek(self.xc + 10)),
            ('Home', lambda: self.seek(MIN_XC)),
            ('End', lambda: self.seek(self.n - 1)),
        ]
        for seq, slot in shortcut_map:
            QShortcut(QKeySequence(seq), self).activated.connect(slot)

    # =============================================================== helpers
    def _populate_datasets(self, select_id: str):
        icons = {'shock': '⚡', 'bull': '🐂', 'bear': '🐻', 'range': '↔', 'goog': '📈'}
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        for d in self.service.datasets():
            icon = icons.get(d['id'], '📄' if str(d['id']).startswith('csv:') else '•')
            self.dataset_combo.addItem(f'{icon}  {d["label"]} ({d["bars"]})', d['id'])
        idx = self.dataset_combo.findData(select_id)
        self.dataset_combo.setCurrentIndex(max(0, idx))
        self.dataset_combo.blockSignals(False)

    def _clear_fractal(self):
        self.fractal = None
        self.chart.set_fractal(None)

    # =============================================================== logic
    def set_dataset(self, ds: str):
        self.ds = ds
        self._clear_fractal()
        self.data = self.service.load_data(ds)
        self.n = self.data['n']
        self.xc = max(MIN_XC, int(self.n * 0.62))
        self.autosought_reset()
        self.chart.set_data(self.data)
        self.minimap.set_data(self.data)
        self.seek_slider.setRange(MIN_XC, self.n - 1)
        self.seek_slider.setValue(self.xc)
        self.ph_bar.setText(f'/ {self.n} بار')
        self._refresh_analysis()
        self._start_sweep()

    def autosought_reset(self):
        self._autosought = False
        self._user_seek = False

    def seek(self, i: int):
        i = max(MIN_XC, min(self.n - 1, int(i)))
        self._clear_fractal()
        self.xc = i
        if not getattr(self, '_internal_seek', False):
            self._user_seek = True
        self._internal_seek = True
        self.seek_slider.setValue(i)
        self._internal_seek = False
        self.chart.set_xc(i)
        self.minimap.set_xc(i)
        self._refresh_analysis()

    def _seek_slider_changed(self, value: int):
        if getattr(self, '_internal_seek', False):
            return
        self.seek(value)

    def _arrow(self, direction: int):
        self.seek(self.xc + direction)

    # ---- playback
    def toggle_play(self):
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.btn_play.setText('▶')
            return
        speed = self.speed_combo.currentData() or 1.0
        interval = max(20, int(1000 / (BASE_BARS_PER_SEC * speed)))
        self.play_timer.start(interval)
        self.btn_play.setText('⏸')

    def _play_tick(self):
        if self.xc >= self.n - 1:
            self.toggle_play()
            return
        self.seek(self.xc + 1)

    # ---- analysis refresh
    def _refresh_analysis(self):
        an = self.service.analyse(self.ds, self.xc, self.params, setup=self.setup)
        self.chart.set_analysis(an)
        self._render_side(an)

    def _render_side(self, an: dict):
        d = self.data
        i = self.xc
        self.stat_date.setText(an['date'])
        self.ph_date.setText(an['date'])
        self.ph_bar.setText(f'بار {i} / {self.n}')
        for k in ('open', 'high', 'low', 'close'):
            self.ohlc_labels[k].setText(f"{d[k][i]:.2f}")
        chg = (d['close'][i] / d['close'][i - 1] - 1) * 100 if i > 0 else 0.0
        chg_lbl = self.ohlc_labels['chg']
        chg_lbl.setText(f"{'+' if chg >= 0 else ''}{chg:.2f}%")
        chg_lbl.setStyleSheet(f"color: {'#22ab94' if chg >= 0 else '#f23645'}; font-weight:700;")
        self.v_atr.setText(f"{an['atr']:.2f}")
        sa, sb = (an['sa'][i] if i < len(an['sa']) else None), (an['sb'][i] if i < len(an['sb']) else None)
        atr = an['atr']
        self.v_sa.setText('—' if sa is None else f'{sa * atr:.2f}')
        self.v_sb.setText('—' if sb is None else f'{sb * atr:.2f}')
        if sa is not None and sb is not None:
            bull = sa >= sb
            self.v_cloud.setText('صعودی (SA ≥ SB)' if bull else 'نزولی (SA < SB)')
            self.v_cloud.setStyleSheet(f"color: {'#22ab94' if bull else '#f23645'}; font-weight:700;")
        else:
            self.v_cloud.setText('—'); self.v_cloud.setStyleSheet('')

        # triangles
        tris = an['tris']
        self.tri_count.setText(str(len(tris)))
        if not tris:
            self.tri_list.setText('<span style="color:#5d667f">مثلثی در پنجره‌ی تحلیل نیست</span>')
        else:
            rows = []
            for t in tris[:8]:
                dot = '#f2a1c0' if t['col'] == 1 else ('#7bc67e' if t['col'] == -1 else '#8b94ad')
                col_name = 'صورتی' if t['col'] == 1 else ('سبز' if t['col'] == -1 else 'نامشخص')
                kind = 'قله (P)' if t['type'] == 'P' else 'دره (T)'
                rows.append(
                    f'<span style="color:{dot}">●</span> مثلث {kind} · ابر {col_name}<br>'
                    f'<span style="color:#5d667f;font-size:9px">apex: بار {t["apex"][0]:.1f} · '
                    f'قیمت {t["apex"][1] * atr:.2f}</span>')
            self.tri_list.setText('<br>'.join(rows))

        # zones
        zones = an['zones']
        self.zone_count.setText(str(len(zones)))
        if not zones:
            self.zone_list.setText('<span style="color:#5d667f">Zoneای در این بار یافت نشد</span>')
        else:
            rows = []
            for zi, z in enumerate(zones):
                edge = '#60a5fa' if z['kind'] == 'support' else '#fb7185'
                name = 'حمایت' if z['kind'] == 'support' else 'مقاومت'
                timed = len(z.get('timed') or [])
                badge = f' &nbsp;<span style="background:#ff9f1c;color:#221a08;border-radius:4px;padding:0 4px">در پنجره ×{timed}</span>' if timed else ''
                if z.get('time_confirmed'):
                    badge += ' &nbsp;<span style="background:#123b33;color:#5eead4;border-radius:4px;padding:0 4px">Time ✔</span>'
                if z.get('price_in_zone'):
                    badge += ' &nbsp;<span style="background:#1f2c4a;color:#93c5fd;border-radius:4px;padding:0 4px">قیمت داخل zone</span>'
                if z.get('chikou_in_zone'):
                    badge += (' &nbsp;<span style="background:#3a2b07;color:#ffd166;border-radius:4px;padding:0 4px">Double ✔</span>'
                              if z.get('price_in_zone') else
                              ' &nbsp;<span style="background:#2a2138;color:#d8b4fe;border-radius:4px;padding:0 4px">Chikou ✔</span>')
                rows.append(
                    f'<span style="color:{edge}">■</span> <b>Z{zi + 1} · {name}</b>{badge}<br>'
                    f'<span style="color:#5d667f;font-size:9px">apex: بار {z["apex"][0]:.1f} · '
                    f'قیمت {z["apex"][1] * atr:.2f} · پوشش {z["cover"]}△ · مساحت {z["area"]:.2f}</span>')
            self.zone_list.setText('<br><br>'.join(rows))

        # windows
        self.v_win_total.setText(str(an['windows'] and len(an['windows']) or 0))
        self.v_win_active.setText(str(an.get('windows_active_at_cursor', 0)))
        timed_n = sum(1 for z in zones if z.get('timed'))
        self.v_win_zone.setText(f'{timed_n} zone داخل پنجره' if timed_n else 'هم‌پوشانی ندارد')
        self.v_sb_flats.setText(str(len(an.get('sb_flats') or [])))
        self.v_double.setVisible(bool(an.get('double_bermuda')))
        L = an.get('levels')
        if L:
            self.v_lv_hor.setText(f"{L['horizontal_y'] * atr:.2f}")
            self.v_lv_levels.setText(' · '.join(f'{y * atr:.2f}' for y in (L.get('levels') or [])) or '—')
            self.v_lv_note.setText(L.get('assumption') or '')
        else:
            self.v_lv_hor.setText('—'); self.v_lv_levels.setText('—')
            self.v_lv_note.setText('سطحی قابل رسم نیست (مثلث نهایی/zone یافت نشد).')

    # ---- setup / csv / fractal
    def _on_setup_changed(self):
        setup = self.setup_combo.currentData() or 'both'
        if setup == self.setup:
            return
        self.setup = setup
        self._clear_fractal()
        self._refresh_analysis()
        self._start_sweep()

    def open_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, 'بارگذاری داده‌ی OHLC (CSV)', '',
                                              'CSV (*.csv);;همه‌ی فایل‌ها (*)')
        if not path:
            return
        try:
            ds_id, label, bars = self.service.load_csv_file(path)
        except Exception as e:
            QMessageBox.warning(self, 'CSV نامعتبر', f'فایل بارگذاری نشد:\n{e}')
            return
        self._populate_datasets(ds_id)
        self.set_dataset(ds_id)
        self.statusBar().showMessage(f'{label} — {bars} بار بارگذاری شد', 8000)

    def run_fractal(self):
        try:
            result = self.service.fractal(self.ds, self.xc, self.params, self.setup, mode='box')
        except Exception as e:
            self.statusBar().showMessage(f'Fractal: خطا — {e}', 8000)
            return
        self.fractal = result
        self.chart.set_fractal(result)
        cb = self.layer_checks.get('fractal')
        if cb is not None and not cb.isChecked():
            cb.setChecked(True)   # triggers _layer_toggled → chart repaint
        outcome = 'zone باریک‌تر شد' if result.get('final') == 'narrowed' else 'zone کلاسیک ماند'
        note = result.get('note') or ''
        self.sweep_status.setText(f'Fractal: {outcome} · {note}')

    # ---- layers & params
    def _layer_toggled(self, key: str):
        self.layers[key] = self.layer_checks[key].isChecked()
        self.chart.set_layers(self.layers)

    def _param_changed(self, spec, slider_value: int, out: QLabel):
        value = spec.lo + slider_value * spec.step
        self.params[spec.key] = value
        out.setText(spec.fmt.format(value))
        self._param_timer.start()

    def _on_params_committed(self):
        self._clear_fractal()
        self._refresh_analysis()
        self._start_sweep()

    def reset_params(self):
        for spec in PARAM_SPECS:
            self.params[spec.key] = spec.default
            slider, out = self.param_rows[spec.key]
            slider.blockSignals(True)
            slider.setValue(int(round((spec.default - spec.lo) / spec.step)))
            slider.blockSignals(False)
            out.setText(spec.fmt.format(spec.default))
        self._on_params_committed()

    # ---- sweep (zone map)
    def _start_sweep(self):
        if self._sweep_worker is not None and self._sweep_worker.isRunning():
            self._sweep_worker.finished_hits.disconnect(self._on_sweep_done)
            self._sweep_worker.quit(); self._sweep_worker.wait(200)
        worker = SweepWorker(self.service, self.ds, self.params, step=2, setup=self.setup)
        worker.progress.connect(self._on_sweep_progress)
        worker.finished_hits.connect(self._on_sweep_done)
        self._sweep_worker = worker
        self.sweep_bar.setValue(0)
        self.minimap.set_sweep_progress(0, 100)
        self.sweep_status.setText('در حال محاسبه‌ی zone map…')
        worker.start()

    def _on_sweep_progress(self, done: int, total: int):
        pct = int(100 * done / max(total, 1))
        self.sweep_bar.setValue(pct)
        self.minimap.set_sweep_progress(done, total)
        self.sweep_status.setText(f'zone map… {pct}%')

    def _on_sweep_done(self, hits: list):
        self.hits = hits
        self.minimap.set_hits(hits)
        self.minimap.clear_sweep_progress()
        self.sweep_bar.setValue(100)
        bars = len({h['xc'] for h in hits})
        self.sweep_status.setText(f'zone map آماده: {len(hits)} ناحیه در {bars} بار')
        if not self._autosought and not self._user_seek and hits:
            first = next((h for h in hits if h['xc'] >= 140), hits[0])
            self._autosought = True
            self._internal_seek = True
            self.xc = first['xc']
            self.seek_slider.setValue(first['xc'])
            self._internal_seek = False
            self.chart.set_xc(first['xc'])
            self.minimap.set_xc(first['xc'])
            self._refresh_analysis()

    # ---- export
    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, 'ذخیره‌ی تصویر نمودار',
                                              f'black-bermuda-{self.ds}-bar{self.xc}.png',
                                              'PNG Image (*.png)')
        if path:
            self.chart.grab().save(path, 'PNG')

    def closeEvent(self, event):
        # Stop the background sweep cleanly so the QThread is not destroyed
        # while running (which aborts the process).
        worker = self._sweep_worker
        if worker is not None and worker.isRunning():
            try:
                worker.finished_hits.disconnect(self._on_sweep_done)
                worker.progress.disconnect(self._on_sweep_progress)
            except TypeError:
                pass
            worker.quit()
            worker.wait(3000)
        super().closeEvent(event)
