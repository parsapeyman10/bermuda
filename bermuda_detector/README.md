# Black Bermuda detector v0.2 (prototype)

Rules (verified on the course slides):
1. Senkou A (plotted +26) -> extremes (peaks/troughs) -> straight stretches (multi-scale RDP).
2. Leg = extension of a straight stretch of Senkou A beside an extreme (checked on slides 57-59: few px / <4 deg).
3. Triangle = two legs (left+right) meeting at an apex outside the cloud; legs are rays from the apex through Senkou A and beyond. Nothing is drawn behind the apex.
4. Zone = common area of >=3 open wedges of the same type (troughs -> V -> resistance above, peaks -> inverted V -> support below);
   its narrow end is the crossing of two legs of different triangles (slide 28: apex within ~3% of the instructor's black triangle).

Files: bb.py (data, Ichimoku, extremes, stretches) - wedge.py (half-plane clipping) - bb2.py (wedges, zones) - draw2.py (plots)
Run: python3 draw2.py   (uses matplotlib's offline GOOG sample data; replace load_goog() with your OHLC CSV loader)

Not validated yet: selection policy on FX 1h data, thresholds (theta, mmin, nper, H), the time part (flat Senkou B).

## v0.3 additions
- bb4.py: steep stretches (>=40 deg) -> consecutive opposite-direction steep stretches = one triangle; wedges (natural + continued); apex angle.
- slide66b.py: digitizes Senkou A from slide 66, colour runs, instructor's two black triangles, automatic zone (one colour, apex<90, spacing<26 bars, no lookahead, pair-bounded zone covered by >=3 triangles).
- Result: slide 64 hand-picked best 3.1%, automatic ~10%; slide 66 automatic 8-13% (triangle B) and none (triangle A) -> triangle SELECTION policy still open.
- Scripts expect /home/claude/gt (rasterized slides via pdftoppm -r 200, rotate 90 clockwise).

## v0.4 additions
- bermuda_core.py: clean pipeline (Ichimoku -> steep-stretch triangles -> wedges -> zone as common area of >=2 bounding triangles covered by >=3 -> flat Senkou B time windows with the 26-bar check -> zone AND windows). No lookahead.
- draw4.py: picture of triangles, zone and windows.  Suggested daily-data parameters: deg=8, eps=0.2 ATR, min_dy=0.5 ATR, min_dx=2.
- Findings: with these rules zones are rare on daily GOOG (about 4% of bars); time windows (flat B + 26-bar check) exist at almost every bar on daily data, so they do not filter much there. No edge is claimed.

## v1.1 additions (method completion vs black_bermuda_method.txt)
- §4.9 is a hard default in `analyse()`: apex angle **≤ 90°** (`angle_max=90`; pass `angle_max=180` only for legacy daily-corpus comparability, as the tests do). §4.2 same-colour requirement is enforced at zone level (zones are built only from wedges of same-colour triangles).
- `setup='both'|'sell'|'buy'` filter (§5.2/5.3): sell → only resistance zones above price; buy → only support zones below it.
- §8 time-based price levels: horizontal through the final triangle's apex, verticals at apex/+9/+17/+26 bars, three price levels = crossing of the original outer leg with the same leg translated +k. The copy geometry is **not specified by the course** (§12.4); the implementation documents its assumption in the payload (`levels.assumption`) — verify visually, no reversal is guaranteed.
- §6.13 double Bermuda: per-zone flags `price_in_zone` / `chikou_in_zone` / `time_confirmed`, and `double_bermuda` = any zone with price AND chikou inside.
- §6.6/7 time part: `sb_flats` (flat Senkou B segments) exposed alongside the time windows.
- §7 fractal models live in `simulator/fractal.py`: deterministic synthetic sub-timeframe subdivision (seeded Brownian bridge pinned to base OHLC — a geometric teaching demo, **not** real intraday data), §7.2/§7.3 filtering, base-zone narrowing via half-plane clip. On the daily shock corpus the strict rule finds no base zone, so the fractal step honestly reports "zone کلاسیک ماند / classic remains".
- §9 trade rules / §11 settings: documented only — no order placement, no edge claim.
