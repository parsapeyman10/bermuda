"""Service layer: datasets, LRU-cached analysis, background sweep.

UI never touches bermuda_core directly — everything goes through AnalyseService,
so the GUI and the web app share the exact same payloads (server.analyse_payload).
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from typing import Callable

import bermuda_gui.paths  # noqa: F401  (sys.path bootstrap)
import datasets as DS                  # simulator/datasets.py
import server as API                   # simulator/server.py (payload builder reused)
import bermuda_core as C


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str          # short Persian label
    hint: str
    lo: float
    hi: float
    default: float
    step: float = 1.0
    fmt: str = '{:.0f}'


PARAM_SPECS = [
    ParamSpec('deg',       'زاویه‌ی پا',        'حداقل شیب leg (درجه)',   0,    45,  8.0,   1.0,  '{:.0f}°'),
    ParamSpec('eps',       'اپسیلون RDP',       'تلورانس ساده‌سازی (ATR)', 0.05, 1.0, 0.2,   0.05, '±{:.2f}'),
    ParamSpec('min_dy',    'حداقل حیق leg',     'نوسان عمودی (ATR)',      0.1,  2.0, 0.5,   0.1,  '{:.1f}'),
    ParamSpec('min_dx',    'حداقل طول leg',     'طول افقی (بار)',         1.0, 10.0, 2.0,   0.5,  '{:.1f}'),
    ParamSpec('angle_max', 'حداکثر زاویه‌ی رأس', 'قاعده‌ی 4.9 روش: ≤ ۹۰°',     30,   180, 90.0, 5.0,  '{:.0f}°'),
    ParamSpec('mincover',  'حداقل پوشش zone',   'مثلث‌های پوشاننده',       2,    6,   3.0,   1.0,  '≥ {:.0f} △'),
    ParamSpec('H',         'ارتفاع برش zone',   'برش از سمت باریک (ATR)', 0.5,  8.0, 3.0,   0.5,  '{:.1f}'),
]
DEFAULT_PARAMS = {p.key: p.default for p in PARAM_SPECS}

LAYER_SPECS = [   # key, Persian label
    ('candles', 'کندل‌ها'),
    ('cloud',   'ابر ایچیموکو'),
    ('sa',      'Senkou A'),
    ('sb',      'Senkou B'),
    ('steeps',  'پاهای steep'),
    ('tris',    'مثلث‌ها'),
    ('wedges',  'Wedgeها'),
    ('zones',   'Zoneها'),
    ('windows', 'پنجره‌های زمانی'),
    ('future',  'محو آینده'),
    ('levels',  'سطوح زمانی §8'),
    ('fractal', 'Fractal (۷٫۲/۷٫۳)'),
]
DEFAULT_LAYERS = {k: (k not in ('wedges', 'sb', 'fractal')) for k, _ in LAYER_SPECS}

DATASET_IDS = ('shock', 'bull', 'bear', 'range', 'goog')   # shock first: best for demos


class AnalyseService:
    """Stateless facade with a small LRU cache (analysis is CPU-cheap, ~20 ms)."""

    def __init__(self, cache_size: int = 320):
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._cache_size = cache_size

    # ---------- data ----------
    def datasets(self):
        reg = {d['id']: d for d in DS.registry()}
        out = [reg[i] for i in DATASET_IDS if i in reg]
        out += [d for d in DS.registry() if str(d['id']).startswith('csv:')]
        return out

    def load_csv_file(self, path: str) -> tuple[str, str, int]:
        """Validate + register a user OHLC CSV (see datasets.load_csv). Returns (id, label, bars)."""
        df = DS.load_csv(path)
        label = path.rsplit('/', 1)[-1].rsplit('\\', 1)[-1].rsplit('.', 1)[0][:48] or 'upload'
        return DS.register_csv(label, df), f'CSV · {label}', len(df)

    def load_data(self, ds: str) -> dict:
        df = DS.load(ds)
        import numpy as np
        return {
            'ds': ds,
            'dates': [d.strftime('%Y-%m-%d') for d in df.date],
            'open': np.asarray(df.open, dtype=float),
            'high': np.asarray(df.high, dtype=float),
            'low': np.asarray(df.low, dtype=float),
            'close': np.asarray(df.close, dtype=float),
            'n': len(df),
        }

    # ---------- analysis (cached) ----------
    def analyse(self, ds: str, xc: int, params: dict, setup: str = 'both') -> dict:
        key = f'{ds}|{xc}|{sorted(params.items())}|{setup}'
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        p = dict(DEFAULT_PARAMS)
        p.update(params)
        server_params = API.parse_params({k: str(v) for k, v in p.items()})
        if setup not in ('both', 'sell', 'buy'):
            setup = 'both'
        payload = API.analyse_payload(ds, int(xc), server_params, setup=setup)
        self._cache[key] = payload
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return payload

    # ---------- fractal (7.2/7.3; cached like analyse) ----------
    def fractal(self, ds: str, xc: int, params: dict, setup: str = 'both',
                mode: str = 'box') -> dict:
        """On-demand fractal narrowing. Sub-timeframes are DETERMINISTIC SYNTHETIC
        subdivisions of the base bars (seeded Brownian bridge pinned to base OHLC) —
        a geometric teaching demo, not real intraday data."""
        key = f'fractal|{ds}|{xc}|{sorted(params.items())}|{setup}|{mode}'
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        import fractal as FR
        p = dict(DEFAULT_PARAMS)
        p.update(params)
        if setup not in ('both', 'sell', 'buy'):
            setup = 'both'
        df = DS.load(ds)
        T = C.analyse(df, int(xc), setup=setup, deg=p['deg'], eps=p['eps'], min_dy=p['min_dy'],
                      min_dx=p['min_dx'], angle_max=p['angle_max'],
                      mincover=int(p['mincover']), H=p['H'])
        payload = FR.fractal_analyse(df, int(xc), T, p, setup=setup, mode=mode)
        self._cache[key] = payload
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return payload

    # ---------- sweep (called from a worker thread) ----------
    def sweep(self, ds: str, params: dict, step: int = 2,
              progress: Callable[[int, int], None] | None = None,
              setup: str = 'both') -> list[dict]:
        df = DS.load(ds)
        p = dict(DEFAULT_PARAMS)
        p.update(params)
        hits = []
        rng = list(range(100, len(df) - 1, step))
        for i, xc in enumerate(rng):
            try:
                T = C.analyse(df, xc, setup=setup, deg=p['deg'], eps=p['eps'], min_dy=p['min_dy'],
                              min_dx=p['min_dx'], angle_max=p['angle_max'],
                              mincover=int(p['mincover']), H=p['H'])
                if T['zones']:
                    best = max(T['zones'], key=lambda z: z['cover'])
                    hits.append({'xc': int(xc), 'n': len(T['zones']), 'opens': best['opens'],
                                 'cover': int(best['cover']),
                                 'kind': 'support' if best['opens'] == 'down' else 'resistance'})
            except Exception:
                pass   # individual bar failures must not kill the sweep
            if progress and (i % 10 == 0 or i == len(rng) - 1):
                progress(i + 1, len(rng))
        return hits
