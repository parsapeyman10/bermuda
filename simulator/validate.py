"""Validation report for the Black Bermuda pipeline, driven by synthetic test data.

Two kinds of checks:
  * INVARIANTS (hard): every zone polygon (a) has >=3 vertices, (b) lies fully inside the
    half-planes of its bounding wedges, (c) respects the H-atr cut from its narrow end,
    (d) reports cover >= mincover. Pipeline exceptions count as failures.
  * DESCRIPTIVE (soft): zone frequency per scenario vs pure noise, and how often price
    trades into a zone within the next 5/10 bars ('touch rate'). No edge is claimed —
    numbers are printed for inspection, not as evidence of a trading edge.

Usage:  .venv/bin/python simulator/validate.py [--step 2] [--seeds 12]
Exit code 1 if any invariant fails.
"""
import argparse
import sys
import os
import math
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ('bermuda_detector', 'simulator'):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import bermuda_core as C
import datasets as DS


def synth_bull(seed, n=430):
    """Same recipe as datasets.SYNTHETIC['bull'] but arbitrary seed."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    periods = (21, 55, 89)
    amps = [1.0, 0.6, 0.4]
    wave = sum(a * np.sin(2 * np.pi * t / p + rng.uniform(0, 2 * np.pi)) for a, p in zip(amps, periods))
    wave /= max(abs(wave).max(), 1e-9)
    rets = 0.0009 + 0.006 * rng.standard_normal(n) + 0.0022 * np.gradient(wave) * 10.0
    price = 100.0 * np.exp(np.cumsum(rets)) * (1.0 + 0.075 * wave)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    op = np.empty(n); op[0] = price[0] * 0.99
    op[1:] = price[:-1] * (1.0 + 0.004 * rng.standard_normal(n - 1))
    hi = np.maximum(op, price) * (1.0 + np.abs(0.008 * rng.standard_normal(n)))
    lo = np.minimum(op, price) * (1.0 - np.abs(0.008 * rng.standard_normal(n)))
    return pd.DataFrame({'date': dates, 'open': op, 'high': hi, 'low': lo, 'close': price})


def noise_walk(seed, n=430):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    close = 100.0 * np.exp(np.cumsum(0.008 * rng.standard_normal(n)))
    return pd.DataFrame({'date': dates,
                         'open': close * (1 + 0.001 * rng.standard_normal(n)),
                         'high': close * 1.006, 'low': close * 0.994, 'close': close})


def check_zone_invariants(T, mincover=3, H=3.0):
    errs = []
    for z in T['zones']:
        poly, apex = z['poly'], z['apex']
        if len(poly) < 3:
            errs.append('zone polygon < 3 vertices')
            continue
        if z['cover'] < mincover:
            errs.append(f'cover {z["cover"]} < {mincover}')
        ys = [p[1] for p in poly]
        if z['opens'] == 'up':
            if abs(apex[1] - min(ys)) > 1e-6: errs.append('up-zone apex != min y of polygon')
            if max(ys) > apex[1] + H + 1e-9: errs.append('up-zone exceeds H cut')
        else:
            if abs(apex[1] - max(ys)) > 1e-6: errs.append('down-zone apex != max y of polygon')
            if min(ys) < apex[1] - H - 1e-9: errs.append('down-zone exceeds H cut')
        for p in poly:
            for w in z['var']:
                for a, b, c in w.halfplanes():
                    if a * p[0] + b * p[1] + c < -1e-6:
                        errs.append('polygon vertex outside a bounding wedge half-plane')
                        break
    return errs


def touch_stats(df, T, zones, horizons=(5, 10)):
    """For each zone: did price trade into its band within the next h bars? (descriptive)"""
    out = {h: [] for h in horizons}
    for z in zones:
        a = T['a']
        band = [min(p[1] for p in z['poly']) * a, max(p[1] for p in z['poly']) * a]
        x0 = int(round(z['apex'][0]))
        for h in horizons:
            end = min(len(df), x0 + 1 + h)
            hit = any(df.low.iloc[j] <= band[1] and df.high.iloc[j] >= band[0]
                      for j in range(x0 + 1, end))
            out[h].append(hit)
    return {h: (sum(v) / len(v) if v else float('nan'), len(v)) for h, v in out.items()}


def scan(name, df, step):
    total = zone_bars = err_count = 0
    support = resistance = 0
    touch5, touch10, ntouch = [], [], 0
    for xc in range(120, len(df) - 1, step):
        try:
            T = C.analyse(df, xc, deg=8, eps=0.2, min_dy=0.5, min_dx=2)
        except Exception as e:
            err_count += 1
            print(f'  !! exception at bar {xc}: {e}')
            continue
        total += 1
        errs = check_zone_invariants(T, mincover=3, H=3.0)
        err_count += len(errs)
        for e in errs[:3]:
            print(f'  !! bar {xc}: {e}')
        if T['zones']:
            zone_bars += 1
            for z in T['zones']:
                if z['opens'] == 'down': support += 1
                else: resistance += 1
            ts = touch_stats(df, T, T['zones'])
            for h, (rate, cnt) in ts.items():
                if cnt and not math.isnan(rate):
                    (touch5 if h == 5 else touch10).append(rate)
    pct = 100.0 * zone_bars / max(total, 1)
    print(f'{name:28s} bars={total:4d}  zone-bars={zone_bars:3d} ({pct:5.1f}%)  '
          f'zones sup={support} res={resistance}  invariant-errors={err_count}')
    return zone_bars, total, err_count, touch5, touch10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--step', type=int, default=2)
    ap.add_argument('--seeds', type=int, default=8)
    args = ap.parse_args()

    print('=== Black Bermuda pipeline validation (deg=8, eps=0.2, min_dy=0.5, min_dx=2) ===\n')
    failures = 0
    all_t5, all_t10 = [], []

    print('-- built-in datasets')
    for ds in ('goog', 'bull', 'bear', 'range', 'shock'):
        _, _, errs, t5, t10 = scan(ds, DS.load(ds), args.step)
        failures += errs; all_t5 += t5; all_t10 += t10

    print('\n-- seeded synthetic bull-wave variants (ground-truth-ish: designed to show waves)')
    synth_hits = synth_bars = 0
    for seed in range(1, args.seeds + 1):
        zb, tot, errs, t5, t10 = scan(f'bull-wave seed={seed}', synth_bull(seed), args.step)
        failures += errs; synth_hits += zb; synth_bars += tot; all_t5 += t5; all_t10 += t10
    print(f'   synthetic bull aggregate: {100.0 * synth_hits / max(synth_bars, 1):.1f}% zone-bars')

    print('\n-- pure noise control (expected: rare zones)')
    noise_hits = noise_bars = 0
    for seed in range(101, 101 + 5):
        zb, tot, errs, _, _ = scan(f'noise seed={seed}', noise_walk(seed), args.step)
        failures += errs; noise_hits += zb; noise_bars += tot
    print(f'   noise aggregate: {100.0 * noise_hits / max(noise_bars, 1):.1f}% zone-bars')

    if all_t5:
        print(f'\ndescriptive touch rate (price enters zone band within horizon):')
        print(f'   within 5 bars : {100.0 * np.nanmean(all_t5):.1f}%  (n={len(all_t5)} zone instances)')
        print(f'   within 10 bars: {100.0 * np.nanmean(all_t10):.1f}%  (n={len(all_t10)} zone instances)')
        print('   (descriptive only — NOT evidence of a trading edge)')

    print(f'\ninvariant failures: {failures}')
    if failures:
        sys.exit(1)
    print('ALL INVARIANT CHECKS PASSED')


if __name__ == '__main__':
    main()
