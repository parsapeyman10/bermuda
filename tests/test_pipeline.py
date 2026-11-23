"""Ground-truth tests for the v0.4 pipeline (bermuda_core).

Strategy: monkeypatch the Ichimoku inputs (atr14 / cloud) with a handcrafted zigzag
Senkou-A whose apex positions are known exactly, and construct wedges by hand for
find_zones. Also a golden regression test on the seeded synthetic OHLC ('shock').
"""
import math
import numpy as np
import pandas as pd
import pytest
import bermuda_core as C
import datasets as DS
from bb4 import wedges as bb4_wedges, apex_angle
from wedge import Wedge


# ------------------------------------------------------------------ helpers
def _fake_df(n=106, close=93.0):
    dates = pd.bdate_range('2026-01-01', periods=n)
    df = pd.DataFrame({
        'date': dates,
        'open': np.full(n, close), 'high': np.full(n, close + 2),
        'low': np.full(n, close - 2), 'close': np.full(n, close),
    })
    return df


def _zigzag_sa(n_total):
    """Triangular wave in ATR units: troughs y=86 at x≡0 (mod 12), peaks y=100 at x≡6 (mod 12).
    Legs are 6 bars long, |dy|=14 -> slope ±2.33 (>> tan(20°)); first 2 bars NaN like a warm-up."""
    x = np.arange(n_total)
    w = (x % 12) / 6.0
    tri = 1.0 - np.abs(w - 1.0)
    ys = 86.0 + 14.0 * tri
    ys[:2] = np.nan
    return ys


@pytest.fixture
def zigzag(monkeypatch):
    n = 106
    sa = _zigzag_sa(n)
    sb = sa - 50.0   # bullish sign everywhere -> col=1, no lab filtering
    monkeypatch.setattr(C, 'atr14', lambda df: pd.Series(np.ones(len(df))))
    monkeypatch.setattr(C, 'cloud', lambda df, xc: (sa.copy(), sb.copy()))
    df = _fake_df(n, close=93.0)
    return df


# -------------------------------------------------------------------- ATR
def test_atr14_constant_ranges():
    df = _fake_df(30)
    df['high'] = df['close'] + 1.0
    df['low'] = df['close'] - 1.0   # TR == 2 for every bar
    atr = C.atr14(df)
    assert atr.iloc[-1] == pytest.approx(2.0, abs=1e-12)


# ------------------------------------------------------------------ cloud
def test_cloud_constant_price_is_flat():
    df = _fake_df(120, close=50.0)
    df['high'] = 51.0; df['low'] = 49.0
    SA, SB = C.cloud(df, 119)
    assert SA[-1] == pytest.approx(50.0, abs=1e-9)
    assert SB[-1] == pytest.approx(50.0, abs=1e-9)
    assert np.isnan(SA[:51]).all()     # kij needs 26 bars, ten needs 9 -> SA live from x=51
    assert np.isnan(SB[:77]).all()     # Senkou B needs 52 bars -> live from x=77


# ------------------------------------------------------------ time_windows
def test_time_windows_constant_b_single_large_window():
    n = 120
    SB = np.full(n, 5.0)
    wins = C.time_windows(SB, xc=100, lead=26)
    assert wins, 'constant flat SB must produce windows'
    merged = wins[0]
    assert merged[0] == 26                       # first flat bar that also has flat[x-26]
    assert merged[1] == 120 + 26 - 1             # x-lead < n caps inclusion at n+lead-1 (into projection area)
    assert all(a <= b for a, b in wins)


def test_time_windows_strictly_increasing_b_none():
    SB = np.arange(120, dtype=float)             # never flat two bars in a row
    assert C.time_windows(SB, xc=100, lead=26) == []


def test_time_windows_two_flat_blocks():
    SB = np.full(200, np.nan)
    SB[10:60] = 7.0
    SB[120:170] = 7.0
    wins = C.time_windows(SB, xc=150, lead=26)
    # every reported window must consist of flat bars whose x-26 is also flat
    flat = np.zeros(200, bool)
    for x in range(1, 200):
        if SB[x] == SB[x - 1]:
            flat[x] = flat[x - 1] = True
    assert wins
    for a, b in wins:
        for x in range(a, b + 1):
            assert flat[x] and x - 26 >= 0 and flat[x - 26]


# ----------------------------------------------------------- triangles
def test_triangles_zigzag_ground_truth(zigzag):
    T = C.triangles(zigzag, 79, L=130, eps=0.5, deg=20.0, min_dy=2.0, min_dx=3.0, angle_max=180.0)
    apexes = sorted((t['type'], round(t['apex'][0], 1), round(t['apex'][1], 1)) for t in T['tris'])
    central = [(t_, x_, y_) for t_, x_, y_ in apexes if 10.0 <= x_ <= 95.0]
    expected = []
    for x in range(12, 96, 12):        # troughs (y=86) -> T  (12..84)
        expected.append(('T', float(x), 86.0))
    for x in range(18, 96, 12):        # peaks (y=100) -> P  (18..90)
        expected.append(('P', float(x), 100.0))
    expected.sort()
    assert len(central) == len(expected)
    for (t_, x_, y_), (te, xe, ye) in zip(central, expected):
        assert t_ == te
        assert x_ == pytest.approx(xe, abs=0.6)
        assert y_ == pytest.approx(ye, abs=0.5)
    assert all(t['col'] == 1 for t in T['tris'])   # SA always above SB -> one colour


def test_triangles_monotone_sa_detects_nothing(monkeypatch):
    n = 106
    sa = np.linspace(100, 150, n); sa[:2] = np.nan   # one steep direction only
    monkeypatch.setattr(C, 'atr14', lambda df: pd.Series(np.ones(len(df))))
    monkeypatch.setattr(C, 'cloud', lambda df, xc: (sa.copy(), (sa - 50).copy()))
    T = C.triangles(_fake_df(n), 79, L=130, eps=0.5, deg=20.0, min_dy=2.0, min_dx=3.0)
    assert T['tris'] == []
    assert T['steeps'] == [] or all(s[4] == 'U' for s in T['steeps'])


def test_triangle_wedge_angle_isotropic():
    w = Wedge((0, 0), -2.0, 2.0)   # symmetric slopes
    assert apex_angle(w) == pytest.approx(math.degrees(math.acos(3.0 / 5.0)), abs=1e-9)


# ------------------------------------------------------------ find_zones
def _apex_wedge(k, x, y, mL=-2.0, mR=2.0, opens='up', col=1):
    w = Wedge((x, y), mL, mR)
    w.k, w.col, w.opens = k, col, opens
    w.t = {'mid': (x, y)}
    return w


def test_find_zones_ground_truth_overlap():
    # three up-cones, apexes collinear near y=88..91, spaced 10 bars apart -> common area exists
    ws = [_apex_wedge(0, 10, 90), _apex_wedge(1, 20, 88), _apex_wedge(2, 30, 91)]
    zones = C.find_zones(ws, box=(0, 70, 80, 140), last=110.0, opens='up',
                         H=3.0, spacing=26, mincover=3, maxdist=30.0, top=3)
    assert zones, 'three overlapping same-colour wedges must form a zone'
    z = zones[0]
    # narrow end (apex of the zone) = the LOWEST vertex of the cut polygon
    ys = [p[1] for p in z['poly']]
    assert z['apex'][1] == pytest.approx(min(ys), abs=1e-6)
    assert z['apex'][0] == pytest.approx(20.25, abs=0.75)   # crossing of outer cones
    assert z['apex'][1] == pytest.approx(110.5, abs=1.0)
    assert z['cover'] >= 3
    # every vertex lies inside every bounding wedge (zone really is the intersection)
    for w in ws:
        for a, b, c in w.halfplanes():
            for p in z['poly']:
                assert a * p[0] + b * p[1] + c >= -1e-9
    # H-cut respected: nothing higher than apex + H
    assert max(ys) <= z['apex'][1] + 3.0 + 1e-9


def test_find_zones_spacing_filter_rejects_far_triangles():
    ws = [_apex_wedge(i, x, 90) for i, x in enumerate((0, 50, 100))]   # mids > 26 apart
    zones = C.find_zones(ws, box=(-10, 130, 80, 200), last=150.0, opens='up',
                         H=5.0, spacing=26, mincover=3, maxdist=100.0, top=3)
    assert zones == []


def test_find_zones_mincover_requires_enough_triangles():
    ws = [_apex_wedge(0, 10, 90), _apex_wedge(1, 20, 88), _apex_wedge(2, 30, 91)]
    zones = C.find_zones(ws, box=(0, 70, 80, 140), last=110.0, opens='up',
                         H=3.0, spacing=26, mincover=4, maxdist=30.0, top=3)
    assert zones == []


def test_find_zones_too_far_from_price_rejected():
    ws = [_apex_wedge(0, 10, 90), _apex_wedge(1, 20, 88), _apex_wedge(2, 30, 91)]
    zones = C.find_zones(ws, box=(0, 70, 80, 140), last=60.0, opens='up',
                         H=3.0, spacing=26, mincover=3, maxdist=8.0, top=3)
    assert zones == []


# ---------------------------------------------- golden regression (synthetic)
def test_shock_dataset_zone_bar_regression():
    df = DS.load('shock')          # seeded synthetic OHLC, 430 bars
    T = C.analyse(df, 204, deg=8, eps=0.2, min_dy=0.5, min_dx=2)
    # recorded on this branch: tris=5, zones=3 (2 support + 1 resistance), windows_active=1
    assert len(T['tris']) >= 3
    assert len(T['zones']) >= 1
    assert any(z['opens'] == 'down' for z in T['zones'])          # support-type zone present
    assert all(z['cover'] >= 3 for z in T['zones'])
    for z in T['zones']:
        assert z['apex'][1] * T['a'] > 0
        assert len(z['poly']) >= 3
    assert T['windows'], 'flat Senkou B windows must exist on this fixture'


def test_goog_pipeline_runs_and_is_sane():
    df = DS.load('goog')
    assert len(df) == 1047
    T = C.analyse(df, 850, deg=8, eps=0.2, min_dy=0.5, min_dx=2)
    assert T['SA'].shape == T['SB'].shape
    assert len(T['windows']) > 0          # windows exist at almost every bar on daily data
    assert T['last'] > 0 and T['a'] > 0


def test_pure_noise_does_not_crash_pipeline():
    rng = np.random.default_rng(2026)
    n = 400
    dates = pd.bdate_range('2024-01-01', periods=n)
    close = 100 * np.exp(np.cumsum(0.008 * rng.standard_normal(n)))
    df = pd.DataFrame({
        'date': dates,
        'open': close * (1 + 0.001 * rng.standard_normal(n)),
        'high': close * 1.006, 'low': close * 0.994, 'close': close,
    })
    zone_bars = 0
    for xc in range(120, n - 1, 8):
        T = C.analyse(df, xc, deg=8, eps=0.2, min_dy=0.5, min_dx=2)
        zone_bars += bool(T['zones'])
    assert zone_bars <= 25   # loose sanity bound; noise must not flood the detector
