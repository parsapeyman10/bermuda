/* Black Bermuda Simulator — client */
'use strict';
const $ = (s, p) => (p || document).querySelector(s);
const $$ = (s, p) => [...(p || document).querySelectorAll(s)];
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(d);

const FUTURE_PAD = 55;
const BASE_BARS_PER_SEC = 5;

const DEFAULT_PARAMS = { deg: 8, eps: 0.2, min_dy: 0.5, min_dx: 2.0, angle_max: 90, mincover: 3, H: 3.0 };   // angle_max: method rule 4.9
const PARAM_DEFS = [
  { k: 'deg',       label: 'زاویه‌ی پا',       sub: 'حداقل شیب leg (درجه)', min: 0,   max: 45,  step: 1,    fmt: v => v.toFixed(0) + '°' },
  { k: 'eps',       label: 'اپسیلون RDP',      sub: 'تلورانس ساده‌سازی (ATR)', min: 0.05, max: 1, step: 0.05, fmt: v => '±' + v.toFixed(2) },
  { k: 'min_dy',    label: 'حداقل حیق leg',    sub: 'نوسان عمودی (ATR)',    min: 0.1, max: 2.0, step: 0.1,  fmt: v => v.toFixed(1) + ' ATR' },
  { k: 'min_dx',    label: 'حداقل طول افقی',   sub: 'طول x leg (بار)',      min: 1,   max: 10,  step: 0.5,  fmt: v => v.toFixed(1) + ' بار' },
  { k: 'angle_max', label: 'حداکثر زاویه‌ی رأس', sub: 'قاعده‌ی 4.9 روش: ≤ ۹۰°', min: 30,  max: 180, step: 5,    fmt: v => v.toFixed(0) + '°' },
  { k: 'mincover',  label: 'حداقل پوشش',       sub: 'تعداد مثلث‌های پوشاننده‌ی zone', min: 2, max: 6, step: 1, fmt: v => '≥ ' + v.toFixed(0) + ' △' },
  { k: 'H',         label: 'ارتفاع برش zone',  sub: 'برش از سمت باریک (ATR)', min: 0.5, max: 8,  step: 0.5,  fmt: v => v.toFixed(1) + ' ATR' },
];
const LAYER_DEFS = [
  { k: 'candles', label: 'کندل‌ها' },
  { k: 'cloud',   label: 'ابر ایچیموکو' },
  { k: 'sa',      label: 'Senkou A' },
  { k: 'sb',      label: 'Senkou B' },
  { k: 'steeps',  label: 'پاهای steep' },
  { k: 'tris',    label: 'مثلث‌ها' },
  { k: 'wedges',  label: 'Wedgeها' },
  { k: 'zones',   label: 'Zoneها' },
  { k: 'windows', label: 'پنجره‌های زمانی' },
  { k: 'future',  label: 'محو آینده (نسبت به بار)' },
  { k: 'levels',  label: 'سطوح زمانی §8' },
  { k: 'fractal', label: 'Fractal (§7.2/7.3)' },
];

const state = {
  datasets: [],
  ds: 'shock',
  data: null,           // {dates, open, high, low, close, n}
  n: 0,
  analyse: null,
  cache: new Map(),
  xc: 0,
  playing: false,
  speed: 1,
  visibleBars: 150,
  mouse: null,          // {x, y} css px inside chart
  layers: Object.fromEntries(LAYER_DEFS.map(l => [l.k, l.k !== 'wedges' && l.k !== 'sb' && l.k !== 'fractal'])),   // §8 levels on by default; Fractal needs the button (synthetic sub-TF)
  params: { ...DEFAULT_PARAMS },
  setup: 'both',
  fractal: null,        // merged into draw when the fractal button is used
  sweep: { hits: [], running: false, job: null, total: 0, done: 0, seq: 0, autosought: false },
  userSeek: false,
  playheadFloat: 0,
  lastFrame: 0,
};

/* ============================== fetch helpers ============================== */
async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error('HTTP ' + r.status + ' · ' + path);
  return r.json();
}
const paramsQuery = () => {
  const q = new URLSearchParams();
  for (const k in state.params) q.set(k, state.params[k]);
  return q.toString();
};
const cacheKey = () => state.ds + '|' + state.xc + '|' + paramsQuery() + '|' + state.setup;

async function loadDatasets() {
  state.datasets = await api('/api/datasets');
  const sel = $('#dataset');
  sel.innerHTML = state.datasets.map(d =>
    `<option value="${d.id}">${d.label} — ${d.bars} بار</option>`).join('');
  sel.value = state.ds;
}

async function loadData(ds) {
  const d = await api('/api/data?ds=' + encodeURIComponent(ds));
  state.data = d;
  state.n = d.dates.length;
  state.xc = Math.floor(state.n * 0.62);
  state.playheadFloat = state.xc;
  $('#seek').max = String(state.n - 1);
  $('#seek').value = String(state.xc);
  $('#phTotal').textContent = String(state.n);
}

async function fetchAnalyse() {
  const key = cacheKey();
  const cached = state.cache.get(key);
  if (cached) { state.analyse = cached; return; }
  const d = await api(`/api/analyse?ds=${encodeURIComponent(state.ds)}&xc=${state.xc}&${paramsQuery()}&setup=${state.setup}`);
  state.analyse = d;
  state.cache.set(key, d);
  if (state.cache.size > 800) state.cache.delete(state.cache.keys().next().value);
}

/* ============================== sweep (zone map) ========================== */
let sweepPoll = null;
async function runSweep() {
  const seq = ++state.sweep.seq;
  clearInterval(sweepPoll);
  state.sweep.running = true;
  state.sweep.hits = [];
  setSweepStatus('در حال محاسبه‌ی zone map روی کل تاریخچه…', 0);
  try {
    const r = await api(`/api/sweep?ds=${encodeURIComponent(state.ds)}&${paramsQuery()}&step=2&setup=${state.setup}`);
    if (r.status === 'cached') { finishSweep(seq, r.hits, r.errors || 0); return; }
    if (r.status === 'running' && r.job) { pollSweep(seq, r.job, r.total || 0, r.done || 0); return; }
    finishSweep(seq, [], 0);
  } catch (e) { state.sweep.running = false; setSweepStatus('خطا در محاسبه‌ی zone map', null); console.error(e); }
}
function pollSweep(seq, job, total, done) {
  const t0 = Date.now();
  sweepPoll = setInterval(async () => {
    try {
      const s = await api('/api/sweep/status/' + job);
      if (seq !== state.sweep.seq) { clearInterval(sweepPoll); return; }
      const pct = s.total ? Math.round(100 * s.done / s.total) : 0;
      setSweepStatus(`محاسبه‌ی zone map… <b>${pct}%</b><div class="sweep-bar"><div style="width:${pct}%"></div></div>`, null);
      if (s.status === 'done') { clearInterval(sweepPoll); finishSweep(seq, s.hits || [], s.errors || 0); }
      else if (Date.now() - t0 > 120000) { clearInterval(sweepPoll); setSweepStatus('zone map: زمان بیش از حد شد؛ دوباره تلاش کنید', null); state.sweep.running = false; }
    } catch (e) { /* transient */ }
  }, 320);
}
function finishSweep(seq, hits, errors) {
  if (seq !== state.sweep.seq) return;
  state.sweep.running = false;
  state.sweep.hits = hits || [];
  const bars = new Set(state.sweep.hits.map(h => h.xc)).size;
  setSweepStatus(`zone map آماده: <b>${hits.length}</b> ناحیه در <b>${bars}</b> بار${errors ? ` · ${errors} خطا` : ''}`, 100);
  drawMinimap();
  if (!state.sweep.autosought && !state.userSeek && state.sweep.hits.length) {
    const first = state.sweep.hits.find(h => h.xc >= 140) || state.sweep.hits[0];
    if (first) { state.sweep.autosought = true; seek(first.xc, true); }
  }
}
function setSweepStatus(html, pct) {
  const el = $('#sweepStatus');
  el.innerHTML = html + (pct === null ? '' : '');
}

/* ============================== chart rendering =========================== */
const chart = $('#chart'), ctx = chart.getContext('2d');
const minimap = $('#minimap'), mctx = minimap.getContext('2d');
let dpr = Math.max(1, Math.min(2.5, window.devicePixelRatio || 1));

function fitCanvas(canvas, cx) {
  const r = canvas.getBoundingClientRect();
  const w = Math.max(50, Math.round(r.width * dpr));
  const h = Math.max(50, Math.round(r.height * dpr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { W: r.width, H: r.height };
}

function viewRange() {
  const x1 = state.xc + FUTURE_PAD;
  const x0 = x1 - state.visibleBars;
  return [x0, x1];
}

function yRangeOf(view) {
  const [x0, x1] = view, d = state.data;
  const lo = clamp(Math.floor(x0), 0, state.n - 1), hi = clamp(Math.ceil(x1), 0, state.n - 1);
  let mn = Infinity, mx = -Infinity;
  for (let i = lo; i <= hi; i++) { if (d.low[i] < mn) mn = d.low[i]; if (d.high[i] > mx) mx = d.high[i]; }
  const A = state.analyse;
  if (A) {
    const a = A.atr || 1;
    if (state.layers.zones) for (const z of A.zones || []) for (const p of z.poly) {
      const y = p[1] * a; if (y < mn) mn = y; if (y > mx) mx = y;
    }
    if (state.layers.levels && A.levels) for (const y of A.levels.levels) {
      const yy = y * a; if (yy < mn) mn = yy; if (yy > mx) mx = yy;
    }
    const fr = state.fractal;
    if (state.layers.fractal && fr) {
      if (fr.narrow_zone) for (const p of fr.narrow_zone) { const y = p[1] * a; if (y < mn) mn = y; if (y > mx) mx = y; }
      if (fr.box) { const y0 = fr.box.y0 * a, y1 = fr.box.y1 * a; mn = Math.min(mn, y0); mx = Math.max(mx, y1); }
    }
  }
  if (!isFinite(mn) || !isFinite(mx)) { mn = 0; mx = 1; }
  const pad = (mx - mn) * 0.09 || mx * 0.05 || 1;
  return [mn - pad, mx + pad];
}

const X = (x, view, W) => (x - view[0]) / (view[1] - view[0]) * W;
const Y = (y, yr, H) => H - (y - yr[0]) / (yr[1] - yr[0]) * H;

function niceTicks(mn, mx, count) {
  const span = mx - mn;
  if (!(span > 0) || !isFinite(span)) return [mn];
  const raw = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || mag;
  const ticks = [];
  for (let v = Math.ceil(mn / step) * step; v <= mx; v += step) ticks.push(v);
  return ticks;
}

function roundRect(c, x, y, w, h, r) {
  c.beginPath();
  c.moveTo(x + r, y);
  c.lineTo(x + w - r, y); c.quadraticCurveTo(x + w, y, x + w, y + r);
  c.lineTo(x + w, y + h - r); c.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  c.lineTo(x + r, y + h); c.quadraticCurveTo(x, y + h, x, y + h - r);
  c.lineTo(x, y + r); c.quadraticCurveTo(x, y, x + r, y);
  c.closePath();
}

function drawStar(c, cx, cy, r) {
  c.beginPath();
  for (let i = 0; i < 10; i++) {
    const rad = i % 2 === 0 ? r : r * 0.45;
    const a = -Math.PI / 2 + i * Math.PI / 5;
    const x = cx + Math.cos(a) * rad, y = cy + Math.sin(a) * rad;
    i === 0 ? c.moveTo(x, y) : c.lineTo(x, y);
  }
  c.closePath();
}

function draw() {
  if (!state.data) return;
  const { W, H } = fitCanvas(chart, ctx);
  const d = state.data, A = state.analyse;
  const view = viewRange();
  const yr = yRangeOf(view);
  const a = A ? A.atr : 1;
  const cw = W / (view[1] - view[0]);         // px per bar
  const bodyW = clamp(cw * 0.62, 1.2, 14);

  /* --- background */
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#0d1119';
  ctx.fillRect(0, 0, W, H);

  /* --- grid + y labels */
  ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
  ctx.textAlign = 'left';
  for (const t of niceTicks(yr[0], yr[1], 6)) {
    const y = Y(t, yr, H);
    ctx.strokeStyle = 'rgba(148,163,184,.07)';
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    ctx.fillStyle = '#69738f';
    ctx.fillText(t.toFixed(2), 8, y - 3);
  }
  /* --- x date ticks */
  const tickEvery = Math.max(1, Math.round(state.visibleBars / 6));
  const firstTick = Math.ceil(view[0] / tickEvery) * tickEvery;
  ctx.textAlign = 'center';
  for (let i = firstTick; i < Math.min(view[1], state.n); i += tickEvery) {
    if (i < 0) continue;
    const x = X(i, view, W);
    ctx.strokeStyle = 'rgba(148,163,184,.05)';
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    ctx.fillStyle = '#69738f';
    ctx.fillText(d.dates[clamp(i, 0, state.n - 1)].slice(5), x, H - 6);
  }

  /* --- future-projection divider (beyond last real bar) */
  const nEnd = state.n - 1;
  if (view[1] > nEnd) {
    const x = X(nEnd + 0.5, view, W);
    ctx.fillStyle = 'rgba(148,163,184,.05)';
    ctx.fillRect(x, 0, W - x, H);
    ctx.strokeStyle = 'rgba(148,163,184,.25)';
    ctx.setLineDash([3, 4]); ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#566078'; ctx.textAlign = 'left';
    ctx.fillText('آخرین بار واقعی ←', x + 6, 14);
  }

  /* --- time windows (behind everything price-ish) */
  if (A && state.layers.windows) {
    for (const [wa, wb] of A.windows) {
      if (wb < view[0] || wa > view[1]) continue;
      const xA = X(wa - 0.5, view, W), xB = X(wb + 0.5, view, W);
      ctx.fillStyle = 'rgba(255,159,28,.030)';
      ctx.fillRect(xA, 0, xB - xA, H);
      ctx.fillStyle = 'rgba(255,159,28,.8)';
      ctx.fillRect(xA, H - 6, xB - xA, 5);
    }
  }

  /* --- Ichimoku cloud (trapezoids) */
  if (A && state.layers.cloud) {
    const m0 = clamp(Math.floor(view[0]), 0, A.sa.length - 1);
    const m1 = clamp(Math.ceil(view[1]), 0, A.sa.length - 1);
    for (let i = m0; i < m1; i++) {
      const sa0 = A.sa[i], sb0 = A.sb[i], sa1 = A.sa[i + 1], sb1 = A.sb[i + 1];
      if (sa0 == null || sb0 == null || sa1 == null || sb1 == null) continue;
      const proj = i >= nEnd;
      const up0 = sa0 >= sb0, up1 = sa1 >= sb1;
      const col = (up0 && up1) ? '34,171,148' : (!up0 && !up1) ? '242,54,69' : '148,163,184';
      ctx.fillStyle = `rgba(${col},${proj ? 0.10 : 0.30})`;
      const x0p = X(i, view, W), x1p = X(i + 1, view, W);
      ctx.beginPath();
      ctx.moveTo(x0p, Y(sa0 * a, yr, H));
      ctx.lineTo(x1p, Y(sa1 * a, yr, H));
      ctx.lineTo(x1p, Y(sb1 * a, yr, H));
      ctx.lineTo(x0p, Y(sb0 * a, yr, H));
      ctx.closePath(); ctx.fill();
    }
  }

  /* --- candles */
  if (state.layers.candles) {
    const lo = clamp(Math.floor(view[0]), 0, state.n - 1), hi = clamp(Math.ceil(view[1]), 0, state.n - 1);
    for (let i = lo; i <= hi; i++) {
      const isFuture = i > state.xc;
      const alpha = isFuture ? 0.22 : 1;
      const up = d.close[i] >= d.open[i];
      const col = up ? `rgba(34,171,148,${alpha})` : `rgba(242,54,69,${alpha})`;
      const x = X(i, view, W);
      ctx.strokeStyle = col; ctx.lineWidth = Math.max(1, Math.min(1.6, cw * 0.12));
      ctx.beginPath(); ctx.moveTo(x, Y(d.high[i], yr, H)); ctx.lineTo(x, Y(d.low[i], yr, H)); ctx.stroke();
      const yo = Y(d.open[i], yr, H), yc = Y(d.close[i], yr, H);
      ctx.fillStyle = col;
      const top = Math.min(yo, yc), hgt = Math.max(1, Math.abs(yc - yo));
      ctx.fillRect(x - bodyW / 2, top, bodyW, hgt);
    }
    ctx.lineWidth = 1;
  }

  /* --- future veil relative to analysis bar */
  if (A && state.layers.future && state.xc < view[1]) {
    const x = X(state.xc + 0.5, view, W);
    ctx.fillStyle = 'rgba(6,9,15,.32)';
    if (x < W) ctx.fillRect(x, 0, W - x, H);
  }

  /* --- Senkou A / B lines */
  if (A && state.layers.sb) {
    ctx.strokeStyle = 'rgba(148,163,184,.75)'; ctx.lineWidth = 1; ctx.setLineDash([2, 3]);
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < A.sb.length; i++) {
      const v = A.sb[i]; if (v == null) { started = false; continue; }
      const x = X(i, view, W), y = Y(v * a, yr, H);
      started ? ctx.lineTo(x, y) : ctx.moveTo(x, y); started = true;
    }
    ctx.stroke(); ctx.setLineDash([]);
  }
  if (A && state.layers.sa) {
    ctx.strokeStyle = '#f5efdc'; ctx.lineWidth = 1.8;
    ctx.shadowColor = 'rgba(245,239,220,.35)'; ctx.shadowBlur = 5;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < A.sa.length; i++) {
      const v = A.sa[i]; if (v == null) { started = false; continue; }
      if (i < view[0] - 1 || i > view[1] + 1) { started = false; continue; }
      const x = X(i, view, W), y = Y(v * a, yr, H);
      started ? ctx.lineTo(x, y) : ctx.moveTo(x, y); started = true;
    }
    ctx.stroke(); ctx.shadowBlur = 0;
  }

  /* --- steep legs */
  if (A && state.layers.steeps) {
    for (const s of A.steeps) {
      const [x0, y0, x1, y1, cls] = s;
      ctx.strokeStyle = cls === 'U' ? 'rgba(52,211,153,.95)' : 'rgba(251,113,133,.95)';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(X(x0, view, W), Y(y0 * a, yr, H)); ctx.lineTo(X(x1, view, W), Y(y1 * a, yr, H)); ctx.stroke();
    }
    ctx.lineWidth = 1;
  }

  /* --- triangles (extended legs + apex) */
  const zoneWedgeKeys = new Set();
  if (A && state.layers.zones && A.zones.length) {
    for (const z of A.zones) for (const [k, opens] of (z.wedge_ids || [])) zoneWedgeKeys.add(k + ':' + opens);
  }
  if (A && state.layers.tris) {
    ctx.setLineDash([6, 5]);
    for (const t of A.tris) {
      const up = t.type === 'P';
      ctx.strokeStyle = 'rgba(229,185,92,.32)'; ctx.lineWidth = 1.1;
      const spanL = Math.min(t.A[0], t.B[0]);
      const spanR = Math.max(t.A[2], t.B[2]);
      const xA = spanL - 18, xB = spanR + 18;
      for (const leg of [t.A, t.B]) {
        const m = leg[5]; const p0 = [leg[0], leg[1]];
        const ext = x => p0[1] + m * (x - p0[0]);
        ctx.beginPath(); ctx.moveTo(X(xA, view, W), Y(ext(xA) * a, yr, H)); ctx.lineTo(X(xB, view, W), Y(ext(xB) * a, yr, H)); ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.strokeStyle = '#e5b95c'; ctx.lineWidth = 2.2;
      for (const leg of [t.A, t.B]) {
        ctx.beginPath(); ctx.moveTo(X(leg[0], view, W), Y(leg[1] * a, yr, H)); ctx.lineTo(X(leg[2], view, W), Y(leg[3] * a, yr, H)); ctx.stroke();
      }
      ctx.setLineDash([6, 5]);
      /* apex marker */
      const ax = X(t.apex[0], view, W), ay = Y(t.apex[1] * a, yr, H);
      ctx.fillStyle = '#e5b95c';
      ctx.beginPath(); ctx.arc(ax, ay, 3.4, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = '#231a05'; ctx.lineWidth = 1; ctx.stroke();
      /* cloud-colour dot at the triangle's mid */
      ctx.fillStyle = t.col === 1 ? '#f2a1c0' : t.col === -1 ? '#7bc67e' : '#8b94ad';
      ctx.beginPath(); ctx.arc(X(t.mid[0], view, W), Y(t.mid[1] * a, yr, H), 2.2, 0, Math.PI * 2); ctx.fill();
    }
    ctx.setLineDash([]);
  }

  /* --- wedges */
  if (A && state.layers.wedges) {
    for (const w of A.wedges) {
      const used = zoneWedgeKeys.has(w.k + ':' + w.opens);
      ctx.strokeStyle = used ? 'rgba(255,90,90,.9)' : 'rgba(226,232,255,.28)';
      ctx.lineWidth = used ? 1.8 : 1;
      ctx.setLineDash([4, 6]);
      const dirs = [[-1, -w.mL], [1, w.mR]];
      for (const [ux, uy] of dirs) {
        const len = Math.hypot(ux, uy); const L = 240;
        const ex = w.apex[0] + ux / len * L, ey = w.apex[1] + uy / len * L;
        ctx.beginPath(); ctx.moveTo(X(w.apex[0], view, W), Y(w.apex[1] * a, yr, H)); ctx.lineTo(X(ex, view, W), Y(ey * a, yr, H)); ctx.stroke();
      }
      ctx.setLineDash([]);
    }
  }

  /* --- fractal box (7.3) — under zones */
  if (A && state.layers.fractal && state.fractal && state.fractal.box) {
    const b = state.fractal.box;
    const x0 = X(b.x0, view, W), x1 = X(b.x1, view, W);
    const y0 = Y(b.y1 * a, yr, H), y1 = Y(b.y0 * a, yr, H);
    ctx.fillStyle = 'rgba(94,234,212,.06)';
    ctx.strokeStyle = 'rgba(94,234,212,.75)'; ctx.lineWidth = 1.4; ctx.setLineDash([5, 4]);
    ctx.fillRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
    ctx.strokeRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
    ctx.setLineDash([]);
  }

  /* --- zones */
  if (A && state.layers.zones) {
    A.zones.forEach((z, zi) => {
      const timed = (z.timed || []).length > 0;
      ctx.beginPath();
      z.poly.forEach((p, i) => {
        const x = X(p[0], view, W), y = Y(p[1] * a, yr, H);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.closePath();
      ctx.fillStyle = 'rgba(8,8,10,.78)';
      ctx.fill();
      ctx.strokeStyle = timed ? '#ff9f1c' : '#ff5a5a';
      ctx.lineWidth = 1.7;
      ctx.shadowColor = timed ? 'rgba(255,159,28,.55)' : 'rgba(255,90,90,.4)';
      ctx.shadowBlur = timed ? 12 : 6;
      ctx.stroke();
      ctx.shadowBlur = 0;
      /* apex star */
      const ax = X(z.apex[0], view, W), ay = Y(z.apex[1] * a, yr, H);
      drawStar(ctx, ax, ay, 6.2);
      ctx.fillStyle = '#ffd166'; ctx.fill();
      ctx.strokeStyle = '#6b4d10'; ctx.lineWidth = 1; ctx.stroke();
      /* label pill */
      const label = `Z${zi + 1} ${z.kind.toUpperCase()} · cover=${z.cover}`;
      ctx.font = 'bold 10px Tahoma';
      const tw = ctx.measureText(label).width + 14;
      const px = clamp(ax + 10 + zi * 7, 4, W - tw - 4), py = clamp(ay - 26 + zi * 18, 4, H - 18);
      roundRect(ctx, px, py, tw, 15, 7);
      ctx.fillStyle = timed ? 'rgba(64,38,4,.92)' : 'rgba(24,8,10,.92)';
      ctx.fill();
      ctx.strokeStyle = timed ? '#ff9f1c' : '#ff5a5a'; ctx.lineWidth = 0.8; ctx.stroke();
      ctx.fillStyle = timed ? '#ffd9a0' : '#ffc4c4';
      ctx.textAlign = 'left'; ctx.fillText(label, px + 7, py + 11);
      ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
    });
  }

  /* --- fractal narrow zone + time levels (8.x) */
  if (A && state.layers.fractal && state.fractal && state.fractal.narrow_zone) {
    ctx.beginPath();
    state.fractal.narrow_zone.forEach((p, i) => {
      const x = X(p[0], view, W), y = Y(p[1] * a, yr, H);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = 'rgba(94,234,212,.28)';
    ctx.fill();
    ctx.strokeStyle = '#5eead4'; ctx.lineWidth = 2; ctx.stroke();
  }
  if (A && state.layers.levels && A.levels) {
    const L = A.levels;
    const ay = Y(L.horizontal_y * a, yr, H);
    ctx.setLineDash([8, 6]);
    ctx.strokeStyle = 'rgba(229,185,92,.75)'; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(0, ay); ctx.lineTo(W, ay); ctx.stroke();
    ctx.setLineDash([2, 4]); ctx.strokeStyle = 'rgba(229,185,92,.4)';
    for (const vx of L.verticals) {
      const x = X(vx, view, W);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
    }
    ctx.setLineDash([7, 5]); ctx.strokeStyle = '#ffd166'; ctx.lineWidth = 1.5;
    for (const ly of L.levels) {
      const y = Y(ly * a, yr, H);
      ctx.beginPath(); ctx.moveTo(X(L.verticals[0], view, W), y); ctx.lineTo(W, y); ctx.stroke();
      ctx.fillStyle = '#ffd166'; ctx.font = 'bold 10px ui-monospace, monospace';
      ctx.textAlign = 'right'; ctx.fillText(fmt(ly * a), W - 8, y - 3);
    }
    ctx.setLineDash([]);
    ctx.font = '10px ui-monospace, monospace';
  }

  /* --- cursor at analysis bar */
  const cxp = X(state.xc, view, W);
  ctx.strokeStyle = 'rgba(229,185,92,.6)'; ctx.setLineDash([5, 5]); ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.moveTo(cxp, 0); ctx.lineTo(cxp, H); ctx.stroke(); ctx.setLineDash([]);
  if (A) {
    const cy = Y(d.close[state.xc], yr, H);
    ctx.fillStyle = '#e5b95c'; ctx.beginPath(); ctx.arc(cxp, cy, 3.2, 0, Math.PI * 2); ctx.fill();
  }

  /* --- crosshair + tooltip handled via DOM */
  if (state.mouse) {
    const { x, y } = state.mouse;
    ctx.strokeStyle = 'rgba(232,236,246,.28)'; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    ctx.setLineDash([]);
  }
}

function drawMinimap() {
  const { W, H } = fitCanvas(minimap, mctx);
  mctx.clearRect(0, 0, W, H);
  mctx.fillStyle = '#0d1119'; mctx.fillRect(0, 0, W, H);
  const d = state.data; if (!d) return;
  let mn = Infinity, mx = -Infinity;
  for (const v of d.close) { if (v < mn) mn = v; if (v > mx) mx = v; }
  const pad = (mx - mn) * 0.06 || 1; mn -= pad; mx += pad;
  const px = i => i / (state.n - 1) * (W - 10) + 5;
  const py = v => H - 8 - (v - mn) / (mx - mn) * (H - 18);
  /* price line */
  mctx.strokeStyle = 'rgba(148,163,184,.65)'; mctx.lineWidth = 1;
  mctx.beginPath();
  for (let i = 0; i < state.n; i++) { const x = px(i), y = py(d.close[i]); i === 0 ? mctx.moveTo(x, y) : mctx.lineTo(x, y); }
  mctx.stroke();
  /* zone hits */
  for (const h of state.sweep.hits) {
    mctx.strokeStyle = h.kind === 'support' ? 'rgba(96,165,250,.9)' : 'rgba(251,113,133,.9)';
    mctx.lineWidth = Math.min(3.4, 1.2 + h.cover * 0.5);
    mctx.beginPath(); mctx.moveTo(px(h.xc), H - 3); mctx.lineTo(px(h.xc), H - 6 - h.cover * 3.2); mctx.stroke();
  }
  /* cursor */
  const cx = px(state.xc);
  mctx.strokeStyle = '#e5b95c'; mctx.lineWidth = 1.6;
  mctx.beginPath(); mctx.moveTo(cx, 2); mctx.lineTo(cx, H - 2); mctx.stroke();
  mctx.fillStyle = '#e5b95c';
  mctx.beginPath(); mctx.moveTo(cx - 5, 0); mctx.lineTo(cx + 5, 0); mctx.lineTo(cx, 7); mctx.closePath(); mctx.fill();
}

/* ============================== side panel ================================ */
const el = id => document.getElementById(id);

function renderSide() {
  const A = state.analyse, d = state.data;
  if (!A || !d) return;
  const i = state.xc;
  el('statDate').textContent = A.date;
  el('oOpen').textContent = fmt(d.open[i]);
  el('oHigh').textContent = fmt(d.high[i]);
  el('oLow').textContent = fmt(d.low[i]);
  el('oClose').textContent = fmt(d.close[i]);
  const chg = i > 0 ? (d.close[i] / d.close[i - 1] - 1) * 100 : 0;
  const chgEl = el('oChg');
  chgEl.textContent = (chg >= 0 ? '+' : '') + chg.toFixed(2) + '%';
  chgEl.className = chg >= 0 ? 'up' : 'down';
  el('statAtr').textContent = fmt(A.atr);
  const sa = i < A.sa.length ? A.sa[i] : null, sb = i < A.sb.length ? A.sb[i] : null;
  el('statSA').textContent = sa === null ? '—' : fmt(sa * A.atr);
  el('statSB').textContent = sb === null ? '—' : fmt(sb * A.atr);
  const cl = el('statCloud');
  if (sa !== null && sb !== null) {
    cl.textContent = sa >= sb ? 'صعودی (SA ≥ SB)' : 'نزولی (SA < SB)';
    cl.className = sa >= sb ? 'up' : 'down';
  } else { cl.textContent = '—'; cl.className = ''; }

  /* triangles */
  el('triCount').textContent = String(A.tris.length);
  const tl = el('triList');
  if (!A.tris.length) tl.innerHTML = '<div class="empty">مثلثی در پنجره‌ی تحلیل نیست</div>';
  else tl.innerHTML = A.tris.slice(0, 8).map(t => {
    const colName = t.col === 1 ? 'صورتی' : t.col === -1 ? 'سبز' : 'نامشخص';
    const dot = t.col === 1 ? '#f2a1c0' : t.col === -1 ? '#7bc67e' : '#8b94ad';
    const type = t.type === 'P' ? 'مثلث قله (P)' : 'مثلث دره (T)';
    return `<div class="item"><span class="dot" style="background:${dot}"></span>
      <div class="grow"><b>${type}</b> · ابرِ ${colName}
        <small>apex: بار ${t.apex[0].toFixed(1)} · قیمت ${fmt(t.apex[1] * A.atr)}</small>
      </div></div>`;
  }).join('');

  /* zones */
  el('zoneCount').textContent = String(A.zones.length);
  const zl = el('zoneList');
  if (!A.zones.length) zl.innerHTML = '<div class="empty">Zoneای در این بار یافت نشد</div>';
  else zl.innerHTML = A.zones.map((z, i) => {
    const label = z.kind === 'support' ? 'Zone حمایت' : 'Zone مقاومت';
    const timed = (z.timed || []).length;
    const tChip = z.time_confirmed ? '<span class="mini-badge ok">Time ✔</span>' : '';
    const pChip = z.price_in_zone ? '<span class="mini-badge in">قیمت داخل zone</span>' : '';
    const dChip = (z.price_in_zone && z.chikou_in_zone) ? '<span class="mini-badge db">Double ✔</span>' : (z.chikou_in_zone ? '<span class="mini-badge chikou">Chikou ✔</span>' : '');
    return `<div class="item zone-card ${z.kind}${timed ? ' zone-timed' : ''}">
      <div class="grow"><b>Z${i + 1} · ${label}</b>${timed ? ` <span class="zone-badge">در پنجره‌ی زمانی ×${timed}</span>` : ''}${tChip}${pChip}${dChip}
        <small>apex: بار ${z.apex[0].toFixed(1)} · قیمت ${fmt(z.apex[1] * A.atr)} · پوشش ${z.cover}△ · مساحت ${z.area.toFixed(2)}</small>
      </div></div>`;
  }).join('');

  /* time windows */
  el('winCount').textContent = String(A.windows.length);
  el('winActive').textContent = String(A.windows_active_at_cursor || 0);
  const timedCount = A.zones.filter(z => (z.timed || []).length).length;
  const zt = el('zoneTimed');
  zt.textContent = A.zones.length ? (timedCount ? `${timedCount} zone داخل پنجره` : 'هم‌پوشانی ندارد') : '—';
  zt.className = timedCount ? 'up' : '';

  /* double bermuda badge */
  const db = el('doubleBermuda');
  if (db) db.classList.toggle('hidden', !A.double_bermuda);

  /* §8 time levels */
  const L = A.levels;
  el('levelsCount').textContent = L ? String((L.levels || []).length) : '0';
  el('lvHor').textContent = L ? fmt(L.horizontal_y * A.atr) : '—';
  el('lvLevels').textContent = L && L.levels && L.levels.length ? L.levels.map(v => fmt(v * A.atr)).join(' · ') : '—';
  el('lvAssumption').textContent = L ? (L.assumption || '') : 'سطحی قابل رسم نیست (مثلث نهایی/zone یافت نشد).';

  /* transport readouts */
  el('phDate').textContent = A.date;
  el('phBar').textContent = String(state.xc);
  el('seek').value = String(state.xc);
}

/* ============================== seek / play =============================== */
let fetchSeq = 0;
async function refresh() {
  const seq = ++fetchSeq;
  try {
    await fetchAnalyse();
    if (seq !== fetchSeq) return;
    draw(); drawMinimap(); renderSide();
  } catch (e) { console.error(e); }
}
function seek(i, silent) {
  state.xc = clamp(Math.round(i), 0, state.n - 1);
  state.playheadFloat = state.xc;
  if (!silent) state.userSeek = true;
  refresh();
}

const btnPlay = $('#btnPlay');
function setPlaying(p) {
  state.playing = p;
  btnPlay.textContent = p ? '⏸' : '▶';
  state.lastFrame = performance.now();
}
btnPlay.addEventListener('click', () => setPlaying(!state.playing));
$('#btnBack10').addEventListener('click', () => seek(state.xc - 10));
$('#btnFwd10').addEventListener('click', () => seek(state.xc + 10));
$('#btnBack1').addEventListener('click', () => seek(state.xc - 1));
$('#btnFwd1').addEventListener('click', () => seek(state.xc + 1));
$('#btnStart').addEventListener('click', () => seek(Math.min(130, state.n - 1)));
$('#btnEnd').addEventListener('click', () => seek(state.n - 1));
$('#speed').addEventListener('change', e => { state.speed = parseFloat(e.target.value); });
$('#seek').addEventListener('input', e => { state.userSeek = true; seek(parseInt(e.target.value, 10)); });
$('#dataset').addEventListener('change', async e => {
  setPlaying(false);
  state.ds = e.target.value;
  state.cache.clear();
  state.fractal = null;
  state.sweep = { hits: [], running: false, job: null, total: 0, done: 0, seq: 0, autosought: false };
  await loadData(state.ds);
  await refresh();
  runSweep();
});
$('#setupSel').addEventListener('change', e => {
  state.setup = e.target.value;
  state.cache.clear();
  state.fractal = null;
  refresh();
  runSweep();
});
$('#fractalBtn').addEventListener('click', async () => {
  const btn = $('#fractalBtn');
  btn.disabled = true; btn.textContent = '… در حال تحلیل';
  try {
    const url = `/api/analyse?ds=${encodeURIComponent(state.ds)}&xc=${state.xc}&${paramsQuery()}&setup=${state.setup}&fractal=box`;
    const d = await api(url);
    state.fractal = d.fractal || { note: 'نتیجه‌ای برنگشت', narrow_zone: null, box: null, kept: 0, final: 'classic' };
    refresh();
    const note = state.fractal.note || '';
    $('#sweepStatus').innerHTML = `Fractal: ${state.fractal.final === 'narrowed' ? 'zone باریک‌تر شد' : 'zone کلاسیک ماند'} · ${note}`;
  } catch (e) {
    console.error(e);
    $('#sweepStatus').textContent = 'Fractal: خطا — ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = '⧖ Fractal';
  }
});
$('#csvBtn').addEventListener('click', () => $('#csvInput').click());
$('#csvInput').addEventListener('change', async e => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch('/api/csv', { method: 'POST', body: fd });
    if (!r.ok) { const t = await r.text(); throw new Error('HTTP ' + r.status + ' · ' + t.slice(0, 140)); }
    const info = await r.json();
    await loadDatasets();
    const sel = $('#dataset');
    sel.value = info.id;
    state.ds = info.id;
    state.cache.clear();
    state.fractal = null;
    setPlaying(false);
    await loadData(info.id);
    await refresh();
    runSweep();
  } catch (err) {
    alert('CSV خوانده نشد: ' + err.message);
  } finally {
    e.target.value = '';
  }
});
$('#exportPng').addEventListener('click', () => {
  draw();
  chart.toBlob(b => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(b);
    a.download = `black-bermuda-${state.ds}-bar${state.xc}.png`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
});

/* play loop */
function frame(now) {
  if (state.playing) {
    const dt = (now - state.lastFrame) / 1000;
    state.lastFrame = now;
    state.playheadFloat = Math.min(state.n - 1, state.playheadFloat + dt * BASE_BARS_PER_SEC * state.speed);
    const whole = Math.floor(state.playheadFloat);
    if (whole !== state.xc) { state.xc = whole; refresh(); }
    if (state.xc >= state.n - 1) setPlaying(false);
  } else {
    state.lastFrame = now;
  }
  requestAnimationFrame(frame);
}

/* ============================== chart interactions ======================== */
chart.addEventListener('wheel', e => {
  e.preventDefault();
  const f = e.deltaY > 0 ? 1.12 : 1 / 1.12;
  state.visibleBars = clamp(state.visibleBars * f, 40, 300);
  draw();
}, { passive: false });

chart.addEventListener('mousemove', e => {
  const r = chart.getBoundingClientRect();
  state.mouse = { x: e.clientX - r.left, y: e.clientY - r.top };
  updateTooltip(e, r);
  draw();
});
chart.addEventListener('mouseleave', () => { state.mouse = null; $('#tooltip').classList.add('hidden'); draw(); });
chart.addEventListener('click', () => {
  if (!state.mouse) return;
  const [x0, x1] = viewRange();
  const bar = Math.round(x0 + state.mouse.x / chart.getBoundingClientRect().width * (x1 - x0));
  seek(clamp(bar, 0, state.n - 1));
});

function updateTooltip(e, rect) {
  const d = state.data; if (!d) return;
  const [x0, x1] = viewRange();
  const W = rect.width;
  const bar = clamp(Math.round(x0 + (e.clientX - rect.left) / W * (x1 - x0)), 0, state.n - 1);
  const tt = $('#tooltip');
  const chg = bar > 0 ? (d.close[bar] / d.close[bar - 1] - 1) * 100 : 0;
  tt.innerHTML = `<div class="tt-date">${d.dates[bar]} · بار ${bar}</div>
    باز <b>${fmt(d.open[bar])}</b> · بیشترین <b>${fmt(d.high[bar])}</b><br>
    کمترین <b>${fmt(d.low[bar])}</b> · بسته <b>${fmt(d.close[bar])}</b><br>
    تغییر <b class="${chg >= 0 ? 'up' : 'down'}">${(chg >= 0 ? '+' : '') + chg.toFixed(2)}%</b>`;
  tt.classList.remove('hidden');
  const wrap = $('#chartWrap').getBoundingClientRect();
  let tx = e.clientX - wrap.left + 16, ty = e.clientY - wrap.top + 14;
  tx = Math.min(tx, wrap.width - 190); ty = Math.min(ty, wrap.height - 110);
  tt.style.left = tx + 'px'; tt.style.top = ty + 'px';
}

/* minimap seek (click + drag) */
let minimapDragging = false;
function minimapSeek(e) {
  const r = minimap.getBoundingClientRect();
  const t = clamp((e.clientX - r.left - 5) / (r.width - 10), 0, 1);
  seek(Math.round(t * (state.n - 1)));
}
minimap.addEventListener('mousedown', e => { minimapDragging = true; minimapSeek(e); });
window.addEventListener('mousemove', e => { if (minimapDragging) minimapSeek(e); });
window.addEventListener('mouseup', () => { minimapDragging = false; });

/* keyboard */
window.addEventListener('keydown', e => {
  if (e.target.matches('input, select, textarea')) return;
  if (e.code === 'Space') { e.preventDefault(); setPlaying(!state.playing); }
  else if (e.code === 'ArrowLeft') { e.preventDefault(); e.shiftKey ? seek(state.xc - 10) : seek(state.xc - 1); }
  else if (e.code === 'ArrowRight') { e.preventDefault(); e.shiftKey ? seek(state.xc + 10) : seek(state.xc + 1); }
});

/* ============================== layers & params UI ======================== */
const layersBox = $('#layerToggles');
for (const l of LAYER_DEFS) {
  const lab = document.createElement('label');
  lab.className = 'toggle';
  lab.innerHTML = `<input type="checkbox" ${state.layers[l.k] ? 'checked' : ''} data-k="${l.k}"><span>${l.label}</span>`;
  layersBox.appendChild(lab);
}
layersBox.addEventListener('change', e => {
  const k = e.target.dataset.k; if (!k) return;
  state.layers[k] = e.target.checked;
  draw();
});

const paramsBox = $('#paramSliders');
for (const p of PARAM_DEFS) {
  const row = document.createElement('div');
  row.className = 'param';
  row.innerHTML = `<label for="p_${p.k}">${p.label}<small>${p.sub}</small></label>
    <input type="range" id="p_${p.k}" min="${p.min}" max="${p.max}" step="${p.step}" value="${state.params[p.k]}">
    <output id="o_${p.k}">${p.fmt(state.params[p.k])}</output>`;
  paramsBox.appendChild(row);
}
let paramDebounce = null;
paramsBox.addEventListener('input', e => {
  const k = e.target.id && e.target.id.slice(2);
  const def = PARAM_DEFS.find(p => p.k === k); if (!def) return;
  const v = parseFloat(e.target.value);
  state.params[k] = v;
  $('#o_' + k).textContent = def.fmt(v);
  clearTimeout(paramDebounce);
  paramDebounce = setTimeout(() => {
    state.cache.clear();
    state.fractal = null;
    refresh();
    runSweep();
  }, 260);
});
$('#resetParams').addEventListener('click', () => {
  state.params = { ...DEFAULT_PARAMS };
  for (const def of PARAM_DEFS) {
    $('#p_' + def.k).value = String(state.params[def.k]);
    $('#o_' + def.k).textContent = def.fmt(state.params[def.k]);
  }
  state.cache.clear();
  state.fractal = null;
  refresh();
  runSweep();
});

/* ============================== boot ====================================== */
const ro = new ResizeObserver(() => { draw(); drawMinimap(); });
ro.observe($('.chart-wrap'));
ro.observe(minimap);

(async function init() {
  try {
    await loadDatasets();
    await loadData(state.ds);
    await refresh();
    runSweep();
    requestAnimationFrame(frame);
  } catch (e) {
    console.error(e);
    $('#sweepStatus').textContent = 'خطا در بارگذاری: ' + e.message;
  }
})();
