"""API-level tests: Flask endpoints, JSON hygiene, OHLC invariants, sweep job flow."""
import json
import math
import time
import pytest
import server


@pytest.fixture(scope='module')
def client():
    server.app.config['TESTING'] = True
    with server.app.test_client() as c:
        yield c


def _strict_loads(resp):
    """Parse JSON rejecting NaN/Infinity (browsers' JSON.parse rejects them too)."""
    def bad(x):
        raise ValueError(f'non-strict JSON constant: {x}')
    return json.loads(resp.data.decode(), parse_constant=bad)


def test_datasets_endpoint(client):
    r = client.get('/api/datasets')
    assert r.status_code == 200
    ds = _strict_loads(r)
    ids = [d['id'] for d in ds]
    assert ids == ['goog', 'bull', 'bear', 'range', 'shock']
    assert all(d['bars'] > 100 for d in ds)


@pytest.mark.parametrize('ds', ['goog', 'bull', 'bear', 'range', 'shock'])
def test_data_ohlc_invariants(client, ds):
    r = client.get(f'/api/data?ds={ds}')
    assert r.status_code == 200
    d = _strict_loads(r)
    n = len(d['dates'])
    assert n == len(d['open']) == len(d['high']) == len(d['low']) == len(d['close'])
    assert d['open'][0] > 0 and d['close'][-1] > 0
    for i in range(n):
        o, h, l, c = d['open'][i], d['high'][i], d['low'][i], d['close'][i]
        assert h >= l - 1e-9, f'bar {i}: high<low'
        assert h >= max(o, c) - 1e-6, f'bar {i}: high<max(o,c)'
        assert l <= min(o, c) + 1e-6, f'bar {i}: low>min(o,c)'
    if ds == 'goog':
        assert d['dates'][0] == '2004-08-19'


def test_analyse_shock_golden(client):
    r = client.get('/api/analyse?ds=shock&xc=204')
    assert r.status_code == 200
    d = _strict_loads(r)
    assert d['xc'] == 204 and d['date'] == '2026-01-12'
    assert d['counts']['tris'] >= 3
    assert d['counts']['zones'] >= 1
    assert d['atr'] > 0
    # wedge_ids (used to highlight bounding wedges in the UI) must reference real wedges
    wedge_keys = {(w['k'], w['opens']) for w in d['wedges']}
    for z in d['zones']:
        assert len(z['poly']) >= 3
        for k, opens in z['wedge_ids']:
            assert (k, opens) in wedge_keys
    assert d['windows_active_at_cursor'] >= 1
    # JSON hygiene: every float must be finite (or null, but never NaN literal)
    raw = r.data.decode()
    assert 'NaN' not in raw and 'Infinity' not in raw


def test_analyse_param_clamping(client):
    r = client.get('/api/analyse?ds=bull&xc=200&deg=999&mincover=-3')
    assert r.status_code == 200           # clamps instead of erroring
    d = _strict_loads(r)
    assert 0.0 <= d['xc'] < 430


def test_sweep_job_lifecycle_and_cache(client):
    r = client.get('/api/sweep?ds=shock&step=8&from=120&to=400')
    d = _strict_loads(r)
    assert d['status'] in ('running', 'cached')
    if d['status'] == 'running':
        job = d['job']
        deadline = time.time() + 30
        while time.time() < deadline:
            s = client.get(f'/api/sweep/status/{job}')
            s = _strict_loads(s)
            if s['status'] == 'done':
                break
            time.sleep(0.1)
        else:
            pytest.fail('sweep job did not finish in 30s')
        assert s['total'] > 0 and s['done'] == s['total']
        assert s['errors'] == 0
        hits = s['hits']
    else:
        hits = d['hits']
    assert isinstance(hits, list)
    assert all(120 <= h['xc'] <= 400 and h['cover'] >= 3 for h in hits)
    # second call must be served from cache with identical content
    r2 = client.get('/api/sweep?ds=shock&step=8&from=120&to=400')
    d2 = _strict_loads(r2)
    assert d2['status'] == 'cached'
    assert d2['hits'] == hits


def test_sweep_status_unknown_job_404(client):
    assert client.get('/api/sweep/status/deadbeef0000').status_code == 404


def test_unknown_dataset_404(client):
    assert client.get('/api/data?ds=nope').status_code == 404


def test_index_and_static_served(client):
    assert client.get('/').status_code == 200
    assert b'Black Bermuda' in client.get('/').data
    assert client.get('/app.js').status_code == 200
    assert client.get('/style.css').status_code == 200
