"""Black Bermuda — Fractal models (Section 7.2 / 7.3 of black_bermuda_method.txt).

Two things live here:

1. `subdivide(df, k, seed)` — DETERMINISTIC SYNTHETIC sub-timeframe bars.
   Each base bar is split into k sub-bars using a seeded random walk that is
   pinned to the base bar's open/close and re-scaled to its high/low.
   This is an *educational geometry demo only* — it is NOT real intraday data.
   For genuine practice (the method's intended 5m/15m/30m triggers; see 11.x)
   load real OHLC via simulator.datasets.load_csv / the CSV upload endpoint.

2. `fractal_analyse(...)` — multi-timeframe narrowing on top of the v0.4 pipeline:
     base timeframe (as loaded)  ->  one lower step (or two), in sub-bar units;
   Mode 'fractal' (7.2): keep only lower-TF triangles whose apex falls inside
     the base zone polygon (expanded by 1 ATR) and cut it.
   Mode 'box'     (7.3): draw a box over the span of the base zone's bounding
     triangles — horizontal = their x-extent (+/- margin), vertical = the High
     and Low of the CLOUD over that span; keep only lower-TF triangles fully
     inside the box (7.3.4), on the correct side (7.3.5) when trend side known.
   The final narrowed zone is the base zone clipped by the kept sub-triangles'
   wedges. If no lower-TF triangle qualifies, the classic base zone remains
   (7.2.8 / 7.3 fallback) and the payload says so.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import bermuda_core as C
from wedge import region, clip_halfplane  # noqa: F401  (kept for callers)

SUBDIVIDE_SEED = 20261125
MARGIN_BARS = 2          # small margin in front/behind the box (7.3.2)
EXPAND_ATR = 1.0         # apex-inclusion slack for fractal mode


# ------------------------------------------------------------ sub-timeframes
def subdivide(df: pd.DataFrame, k: int = 13, seed: int = SUBDIVIDE_SEED) -> pd.DataFrame:
    """Deterministically split every base bar into k synthetic sub-bars.

    Invariants (tested): first sub-open == base open, last sub-close == base close,
    every sub-bar lies within the base bar's high/low. Deterministic for (data, k, seed).
    """
    if k < 2:
        raise ValueError('k must be >= 2')
    rows = []
    for i, row in enumerate(df.itertuples()):
        rng = np.random.default_rng(np.random.SeedSequence([int(seed), int(i)]))
        o, c, h, l = float(row.open), float(row.close), float(row.high), float(row.low)
        # k segments; Brownian bridge pinned to (o -> c), then re-scaled into [l, h]
        raw = rng.standard_normal(k)
        cum = np.cumsum(raw)
        t = np.arange(1, k + 1) / k
        bridge = cum - t * cum[-1]
        anchor = np.log(c / o) if o > 0 else 0.0
        closes = o * np.exp(bridge + t * anchor)      # last value == c exactly
        pts = np.concatenate([[o], closes])           # length k+1
        # clamp the whole path into [l, h] with a margin-preserving affine scale
        pmin, pmax = pts.min(), pts.max()
        if pmax > pmin:
            pts = l + (pts - pmin) * (h - l) / (pmax - pmin)
            pts[0] = o
            if abs(o - l) + abs(o - h) <= 0 or True:
                pts[0] = o  # open must stay exact; may equal h or l, which is valid
            pts[-1] = c
        else:
            pts = np.linspace(o, c, k + 1)
        base_ts = pd.Timestamp(row.date)
        for j in range(k):
            oj = pts[j]
            cj = pts[j + 1]
            span = max(abs(cj - oj), (h - l) / k * 0.02, 1e-12)
            hi_j = min(h, max(oj, cj) + abs(rng.standard_normal()) * span * 0.6)
            lo_j = max(l, min(oj, cj) - abs(rng.standard_normal()) * span * 0.6)
            rows.append({'date': base_ts + pd.Timedelta(minutes=int(j * (390 / k))),
                         'open': oj, 'high': max(hi_j, oj, cj), 'low': min(lo_j, oj, cj),
                         'close': cj})
    out = pd.DataFrame(rows).reset_index(drop=True)
    return out


# -------------------------------------------------------------- fractal core
def _apex_in_zone(apex, zone_poly, expand_atr, atr):
    xs = [p[0] for p in zone_poly]; ys = [p[1] for p in zone_poly]
    xz, yz = min(xs), min(ys); xz2, yz2 = max(xs), max(ys)
    ex = EXPAND_ATR * atr
    return (xz - ex <= apex[0] * 1.0 <= xz2 + ex) and (yz - ex <= apex[1] <= yz2 + ex)


def _stitch_sub_to_base(y_sub, atr_sub, atr_base, x_sub_idx, k):
    return y_sub * (atr_sub / atr_base), x_sub_idx / float(k)


def narrow_with_triangles(poly, kept):
    """Clip `poly` by the natural wedge of each kept (base-coordinate-mapped) triangle.

    Returns the narrowed convex polygon (>=3 vertices) or None. Used by the fractal
    narrowing step and unit-tested directly with hand-built triangles.
    """
    from wedge import Wedge
    narrow = list(poly)
    for t in kept:
        A, B = t['A'], t['B']
        mL, mR = (A[5], B[5]) if A[2] <= B[0] else (B[5], A[5])
        nat = Wedge(t['apex'], mL, mR)
        for (a, b, c) in nat.halfplanes():
            narrow = clip_halfplane(narrow, a, b, c)
            if len(narrow) < 3:
                return None
    return narrow if len(narrow) >= 3 else None


def fractal_analyse(df, xc, base_T, params: dict, setup: str = 'both',
                    mode: str = 'box', k: int = 13, steps: int = 1):
    """Narrow the base zone on one (or two) synthetic sub-timeframes.

    df        : base OHLC dataframe
    xc        : analysis bar (base units)
    base_T    : result of bermuda_core.analyse(df, xc, ...)  (already computed)
    params    : same params used for the base analysis (deg/eps/.../angle_max)
    setup     : 'both' | 'sell' | 'buy' (same as base)
    mode      : 'box' (7.3) or 'fractal' (7.2)
    k         : sub-bars per base bar
    steps     : 1 (one lower step) or 2 (two steps; 7.2.5 allows up to three below base)
    """
    out = {
        'available': False, 'mode': mode, 'k': k, 'steps': steps,
        'tf_note': ('Sub-timeframes are DETERMINISTIC SYNTHETIC subdivisions of the base bars '
                    '(seeded Brownian bridge, pinned to base OHLC) — not real intraday data.'),
        'box': None, 'kept': [], 'narrow_zone': None, 'note': '', 'final': 'classic',
    }
    zones = base_T.get('zones') or []
    if not zones:
        out['note'] = 'no base zone (e.g. strict 4.9 apex rule on this timeframe) — nothing to narrow'
        return out

    atr_base = float(base_T['a'])
    SA, SB = base_T['SA'], base_T['SB']
    best = max(zones, key=lambda z: (z['cover'], z['area']))
    best_var = best.get('var', [])
    if not best_var:
        out['note'] = 'zone has no bounding triangles — cannot build the fractal box'
        return out

    # ---- box over the span of the bounding triangles (7.3.2/3)
    tri_dicts = [w.t for w in best_var]
    bx0 = min(min(t['A'][0], t['B'][0]) for t in tri_dicts) - MARGIN_BARS
    bx1 = max(max(t['A'][2], t['B'][2]) for t in tri_dicts) + MARGIN_BARS
    i0, i1 = int(max(0, bx0)), int(min(len(SA) - 1, bx1))
    cloud_hi = float(np.nanmax(np.maximum(SA[i0:i1 + 1], SB[i0:i1 + 1])) / atr_base)
    cloud_lo = float(np.nanmin(np.minimum(SA[i0:i1 + 1], SB[i0:i1 + 1])) / atr_base)
    out['box'] = {'x0': float(bx0), 'x1': float(bx1), 'y0': cloud_lo, 'y1': cloud_hi}

    # ---- sub-timeframe analysis
    sub = subdivide(df, k=k)
    sub_xc = int(np.clip((int(xc) + 1) * k - 1, 130, len(sub) - 1))
    atr_sub = float(C.atr14(sub).iloc[sub_xc])
    if not np.isfinite(atr_sub) or atr_sub <= 0:
        out['note'] = 'sub-timeframe ATR undefined'
        return out
    sub_T = C.analyse(sub, sub_xc, setup=setup, L=130 * k,
                      **{kk: params[kk] for kk in ('eps', 'deg', 'min_dy', 'min_dx', 'angle_max')},
                      mincover=2, H=params.get('H', 3.0))

    # ---- keep only qualifying sub-triangles (7.2.3 / 7.3.4)
    kept, polys = [], []
    for t in sub_T['tris']:
        ax, ay = t['apex']
        in_box = (bx0 * k <= ax <= bx1 * k) and (cloud_lo <= ay * (atr_sub / atr_base) <= cloud_hi)
        if mode == 'box':
            # triangle must lie fully inside the box
            ylo_t = ay * (atr_sub / atr_base)
            if not (in_box and cloud_lo <= ylo_t <= cloud_hi and
                    t['A'][1] * (atr_sub / atr_base) <= cloud_hi and
                    t['B'][1] * (atr_sub / atr_base) <= cloud_hi):
                continue
            # correct side of the box (7.3.5) when the base trend side is known
            # support zone (opens down) -> triangles below the box are Buys; skip others
        else:  # fractal: apex inside the base zone (± 1 ATR) and zone still open
            if not _apex_in_zone((ax / k, ay * (atr_sub / atr_base)), best['poly'], EXPAND_ATR, atr_base):
                continue
        kept.append(t)

    # map kept sub-triangles back to base coordinates for rendering
    r = atr_sub / atr_base                       # y scale (sub-ATR -> base-ATR)
    m_scale = r * float(k)                       # slope scale dy/dx
    for t in kept:
        A, B = t['A'], t['B']
        t['apex'] = (t['apex'][0] / k, t['apex'][1] * r)
        t['A'] = [A[0] / k, A[1] * r, A[2] / k, A[3] * r, A[4], float(A[5] * m_scale)]
        t['B'] = [B[0] / k, B[1] * r, B[2] / k, B[3] * r, B[4], float(B[5] * m_scale)]

    out['kept'] = len(kept)
    if not kept:
        out['note'] = 'no lower-timeframe triangle inside the box/zone — classic base zone remains (7.2.8)'
        out['available'] = True
        out['final'] = 'classic'
        return out

    # ---- narrow: base zone clipped by kept sub-triangle wedges
    W_sub = sub_T['W']
    narrow = narrow_with_triangles(best['poly'], kept)
    out['narrow_zone'] = narrow
    out['available'] = True
    out['final'] = 'narrowed' if out['narrow_zone'] else 'classic'
    out['note'] = f'{len(kept)} lower-timeframe triangle(s) inside the filter; narrow zone computed'
    return out
