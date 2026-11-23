"""Black Bermuda Simulator — backend.

Serves the interactive replay UI and a JSON API that runs the v0.4 pipeline
(bermuda_core.analyse) live for any bar / parameter set, plus a background
"zone map" sweep over the whole history.

Run:  .venv/bin/python simulator/server.py   (or: flask --app simulator/server.py run)
No external network access is used; GOOG data ships inside matplotlib.
"""
import os, sys, json, math, threading, uuid, time
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory, abort

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, '..', 'bermuda_detector'))
sys.path.insert(0, ROOT)

import bermuda_core as C
import bb4
import datasets as DS

app = Flask(__name__, static_folder=os.path.join(ROOT, 'static'), static_url_path='')

# ------------------------------------------------------------- params utils
PARAM_SPEC = {  # name -> (min, max, default)
    'deg':       (0.0, 45.0, 8.0),
    'eps':       (0.05, 1.0, 0.2),
    'min_dy':    (0.1, 2.0, 0.5),
    'min_dx':    (1.0, 10.0, 2.0),
    'angle_max': (30.0, 180.0, 180.0),
    'mincover':  (2, 6, 3),
    'H':         (0.5, 8.0, 3.0),
}

def parse_params(args):
    p = {}
    for k, (lo, hi, dflt) in PARAM_SPEC.items():
        try:
            v = float(args.get(k, dflt))
        except (TypeError, ValueError):
            v = dflt
        v = min(max(v, lo), hi)
        p[k] = int(v) if k == 'mincover' else v
    return p

def param_key(ds, p, step):
    return (ds, tuple(round(p[k], 4) for k in sorted(p)), int(step))

def sanitize(o):
    if isinstance(o, dict):
        return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    if isinstance(o, np.ndarray):
        return sanitize(o.tolist())
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        o = o.item()
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o

# ------------------------------------------------------------------ datasets
@app.get('/api/datasets')
def api_datasets():
    return jsonify(DS.registry())

@app.get('/api/data')
def api_data():
    ds = request.args.get('ds', 'goog')
    if ds not in {d['id'] for d in DS.registry()}:
        abort(404, 'unknown dataset')
    df = DS.load(ds)
    return jsonify(sanitize({
        'ds': ds,
        'dates': [d.strftime('%Y-%m-%d') for d in df.date],
        'open': df.open.tolist(), 'high': df.high.tolist(),
        'low': df.low.tolist(),   'close': df.close.tolist(),
    }))

# ------------------------------------------------------------------ analysis
def analyse_payload(ds, xc, p):
    df = DS.load(ds)
    n = len(df)
    xc = int(min(max(xc, 60), n - 1))   # ATR(14) needs >=14 bars; 60 keeps the analysis meaningful
    T = C.analyse(df, xc, deg=p['deg'], eps=p['eps'], min_dy=p['min_dy'],
                  min_dx=p['min_dx'], angle_max=p['angle_max'],
                  mincover=int(p['mincover']), H=p['H'])
    sa = T['SA']; sb = T['SB']
    tris = []
    for t in T['tris']:
        tris.append({'A': t['A'], 'B': t['B'], 'type': t['type'], 'col': int(t['col']),
                     'apex': list(t['apex']), 'mid': list(t['mid'])})
    wedges = []
    for w in T['W']:
        wedges.append({'k': int(w.k), 'col': int(w.col), 'opens': w.opens, 'kind': w.kind,
                       'mL': float(w.mL), 'mR': float(w.mR), 'apex': [float(w.A[0]), float(w.A[1])],
                       'angle': float(bb4.apex_angle(w))})
    zones = []
    for z in T['zones']:
        timed = [{'a': int(a), 'b': int(b), 'poly': poly} for (a, b), poly in z.get('timed', [])]
        zones.append({'opens': z['opens'], 'col': int(z['col']), 'apex': list(z['apex']),
                      'poly': z['poly'], 'area': float(z['area']), 'cover': int(z['cover']),
                      'kind': 'support' if z['opens'] == 'down' else 'resistance', 'timed': timed,
                      'wedge_ids': [[int(w.k), w.opens] for w in z.get('var', [])]})
    wins = [[int(a), int(b)] for (a, b) in T['windows']]
    active_win = sum(1 for a, b in wins if a <= xc <= b)
    return sanitize({
        'ds': ds, 'xc': xc, 'date': df.date.iloc[xc].strftime('%Y-%m-%d'),
        'n': n, 'atr': float(T['a']), 'last': float(T['last']),
        'sa': sa.tolist(), 'sb': sb.tolist(),
        'steeps': [[float(st[0]), float(st[1]), float(st[2]), float(st[3]), st[4]] for st in T['steeps']],
        'xs': T['xs'].tolist(), 'ys': T['ys'].tolist(),
        'tris': tris, 'wedges': wedges, 'zones': zones, 'windows': wins,
        'counts': {'steeps': len(T['steeps']), 'tris': len(tris), 'wedges': len(wedges), 'zones': len(zones)},
        'windows_active_at_cursor': active_win,
    })

@app.get('/api/analyse')
def api_analyse():
    ds = request.args.get('ds', 'goog')
    try:
        xc = int(request.args.get('xc', '0'))
    except ValueError:
        abort(400, 'bad xc')
    p = parse_params(request.args)
    try:
        return jsonify(analyse_payload(ds, xc, p))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --------------------------------------------------------------- sweep jobs
_jobs = {}
_cache = {}
_lock = threading.Lock()
_MAX_JOBS = 8

def _sweep_worker(job_id, ds, p, step, x0, x1):
    df = DS.load(ds)
    hits = []
    errors = 0
    total = len(range(x0, x1 + 1, step))
    i = 0
    for xc in range(x0, x1 + 1, step):
        try:
            T = C.analyse(df, xc, deg=p['deg'], eps=p['eps'], min_dy=p['min_dy'],
                          min_dx=p['min_dx'], angle_max=p['angle_max'],
                          mincover=int(p['mincover']), H=p['H'])
            if T['zones']:
                best = max(T['zones'], key=lambda z: z['cover'])
                hits.append({'xc': int(xc), 'n': len(T['zones']), 'opens': best['opens'],
                             'cover': int(best['cover']),
                             'kind': 'support' if best['opens'] == 'down' else 'resistance'})
        except Exception:
            errors += 1
        i += 1
        with _lock:
            _jobs[job_id]['done'] = i
    key = param_key(ds, p, step)
    with _lock:
        _cache[key] = {'hits': hits, 'errors': errors, 'total': total}
        _jobs[job_id].update(status='done', done=i, total=total, hits=hits, errors=errors)

@app.get('/api/sweep')
def api_sweep():
    ds = request.args.get('ds', 'goog')
    p = parse_params(request.args)
    try:
        step = max(1, min(10, int(request.args.get('step', '2'))))
    except ValueError:
        step = 2
    df = DS.load(ds)
    x0 = int(request.args.get('from', min(100, len(df) // 4)))
    x1 = int(request.args.get('to', len(df) - 1))
    key = param_key(ds, p, step)
    with _lock:
        cached = _cache.get(key)
        if cached:
            return jsonify({'status': 'cached', **cached})
        for jid, job in _jobs.items():
            if job.get('key') == key and job['status'] == 'running':
                return jsonify({'status': 'running', 'job': jid, 'done': job['done'], 'total': job['total']})
    job_id = uuid.uuid4().hex[:12]
    total = len(range(x0, x1 + 1, step))
    with _lock:
        if len(_jobs) >= _MAX_JOBS:
            old = sorted(_jobs.items(), key=lambda kv: kv[1].get('created', 0))
            for jid, _ in old[: len(_jobs) - _MAX_JOBS + 1]:
                _jobs.pop(jid, None)
        _jobs[job_id] = {'status': 'running', 'done': 0, 'total': total, 'hits': [],
                         'errors': 0, 'key': key, 'created': time.time()}
    threading.Thread(target=_sweep_worker, args=(job_id, ds, p, step, x0, x1), daemon=True).start()
    return jsonify({'status': 'running', 'job': job_id, 'done': 0, 'total': total})

@app.get('/api/sweep/status/<job_id>')
def api_sweep_status(job_id):
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            abort(404, 'no such job')
        return jsonify(sanitize({k: v for k, v in job.items() if k != 'key'}))

# -------------------------------------------------------------------- static
@app.get('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    if path.startswith('api/'):
        abort(404)
    return send_from_directory(app.static_folder, path)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8778'))
    print(f'Black Bermuda Simulator on http://0.0.0.0:{port}')
    app.run(host='0.0.0.0', port=port, threaded=True)
