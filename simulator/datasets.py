"""Dataset registry for the Black Bermuda simulator.

Sources:
  * 'goog'  : real GOOG daily OHLC bundled with matplotlib (cbook sample data), 2004-2008.
  * synthetic scenarios : deterministic procedural OHLC (seeded RNG) built locally,
                          designed to exhibit visible Ichimoku-cloud wave structure.
All arrays are float64 numpy; dates are pandas Timestamps.
"""
import functools
import numpy as np
import pandas as pd

SYNTHETIC = {
    'bull':  dict(label='Synthetic · Bull wave',     drift= 0.00095, amp=0.075, shocks=(),        seed=11, period=(21, 55, 89)),
    'bear':  dict(label='Synthetic · Bear wave',     drift=-0.00060, amp=0.160, shocks=(),        seed=7,  period=(13, 29)),
    'range': dict(label='Synthetic · Range chop',    drift= 0.00000, amp=0.130, shocks=(),        seed=59, period=(21, 34, 89)),
    'shock': dict(label='Synthetic · Shock cycle',   drift= 0.00030, amp=0.095, shocks=(140, 285), seed=53, period=(34, 89)),
}
SYN_BARS = 430

def _synthetic(key):
    s = SYNTHETIC[key]
    rng = np.random.default_rng(s['seed'])
    n = SYN_BARS
    t = np.arange(n)
    wave = sum(a * np.sin(2 * np.pi * t / p + rng.uniform(0, 2 * np.pi))
               for a, p in zip([1.0, 0.6, 0.4][:len(s['period'])], s['period']))
    wave /= max(abs(wave).max(), 1e-9)
    rets = s['drift'] + 0.006 * rng.standard_normal(n)
    rets += 0.0022 * np.gradient(wave) * 10.0
    price = 100.0 * np.exp(np.cumsum(rets)) * (1.0 + s['amp'] * wave)
    for sh in s['shocks']:  # one-day crashes followed by drift-recovery
        price[sh:] *= 0.82
        rets[sh] -= 0.20
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    open_ = np.empty(n); open_[0] = price[0] * 0.99
    open_[1:] = price[:-1] * (1.0 + 0.004 * rng.standard_normal(n - 1))
    high = np.maximum(open_, price) * (1.0 + np.abs(0.008 * rng.standard_normal(n)))
    low  = np.minimum(open_, price) * (1.0 - np.abs(0.008 * rng.standard_normal(n)))
    df = pd.DataFrame({'date': dates, 'open': open_, 'high': high, 'low': low, 'close': price})
    return df.reset_index(drop=True)

@functools.lru_cache(maxsize=8)
def load(ds):
    if ds == 'goog':
        import matplotlib.cbook as cbook
        d = cbook.get_sample_data('goog.npz')
        arr = d['price_data'] if hasattr(d, 'files') else d
        df = pd.DataFrame({k: arr[k] for k in ['date', 'open', 'high', 'low', 'close']})
        df['date'] = pd.to_datetime(df['date'])
        return df.reset_index(drop=True).astype({'open': 'float64', 'high': 'float64', 'low': 'float64', 'close': 'float64'})
    if ds in SYNTHETIC:
        return _synthetic(ds)
    raise KeyError(f'unknown dataset: {ds}')

def registry():
    out = [{'id': 'goog', 'label': 'GOOG · real daily (2004–2008)', 'bars': len(load('goog')),
             'desc': 'Real historical OHLC bundled with matplotlib (GOOG, daily).'}]
    for k, s in SYNTHETIC.items():
        out.append({'id': k, 'label': s['label'], 'bars': SYN_BARS,
                    'desc': 'Seeded procedural OHLC with visible cloud waves — tuned for studying triangle/zone formation.'})
    return out
