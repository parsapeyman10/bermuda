"""Qt-free tests for the GUI service layer (bermuda_gui.data).

These run headless — AnalyseService never imports PyQt6.
"""
import pytest

from bermuda_gui import paths  # noqa: F401  (sys.path bootstrap)
from bermuda_gui.data import AnalyseService, DATASET_IDS, DEFAULT_PARAMS


def test_datasets_returns_all_five_in_demo_order():
    svc = AnalyseService()
    ids = [d['id'] for d in svc.datasets()]
    assert ids == list(DATASET_IDS)
    assert ids[0] == 'shock'
    for d in svc.datasets():
        assert d.get('label') or d.get('name') or d['id']


def test_load_data_shapes():
    svc = AnalyseService()
    for ds in DATASET_IDS:
        data = svc.load_data(ds)
        assert data['n'] == len(data['dates']) == len(data['close'])
        assert data['n'] > 60
        assert (data['high'] >= data['low']).all()


def test_analyse_payload_keys_and_cache(tmp_path):
    svc = AnalyseService()
    p1 = svc.analyse('shock', 204, dict(DEFAULT_PARAMS))
    for key in ('ds', 'xc', 'n', 'date', 'atr', 'sa', 'sb',
                'tris', 'zones', 'windows', 'counts', 'last', 'xs', 'ys'):
        assert key in p1, key
    # same arguments -> cached identical object
    p2 = svc.analyse('shock', 204, dict(DEFAULT_PARAMS))
    assert p2 is p1


def test_analyse_param_override_changes_cache_key():
    svc = AnalyseService()
    base = svc.analyse('shock', 204, dict(DEFAULT_PARAMS))
    tuned = dict(DEFAULT_PARAMS)
    tuned['deg'] = 12.0
    other = svc.analyse('shock', 204, tuned)
    assert other is not base


def test_sweep_bounds_and_progress_callback():
    svc = AnalyseService()
    seen = []
    hits = svc.sweep('range', dict(DEFAULT_PARAMS), step=50,
                     progress=lambda i, total: seen.append((i, total)))
    assert isinstance(hits, list)
    for h in hits:
        assert 100 <= h['xc'] < 430
        assert h['kind'] in ('support', 'resistance')
        assert h['cover'] >= 0
    assert seen, 'progress callback must fire at least once'
    assert seen[-1][0] == seen[-1][1]  # final call reports completion


def test_sweep_deterministic_across_calls():
    svc = AnalyseService()
    a = svc.sweep('shock', dict(DEFAULT_PARAMS), step=25)
    b = svc.sweep('shock', dict(DEFAULT_PARAMS), step=25)
    assert [h['xc'] for h in a] == [h['xc'] for h in b]
