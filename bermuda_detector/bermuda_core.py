"""Black Bermuda core (v0.4): Senkou-A triangles -> zone (common area of wedges) -> time windows (flat Senkou B, 26-bar check).
Coordinates: x = bar index, y = price / ATR14 (at the analysis bar). No lookahead: only data <= xc is used."""
import numpy as np, pandas as pd, math, itertools
from wedge import region, clip_halfplane, area
import bb4

def atr14(df):
    pc=df.close.shift(1)
    tr=pd.concat([df.high-df.low,(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(14).mean()

def cloud(df, xc):
    d=df.iloc[:xc+1]; hh=lambda n:d.high.rolling(n).max(); ll=lambda n:d.low.rolling(n).min()
    ten=(hh(9)+ll(9))/2; kij=(hh(26)+ll(26))/2; sa=(ten+kij)/2; sb=(hh(52)+ll(52))/2
    n=len(d); SA=np.full(n+26,np.nan); SB=np.full(n+26,np.nan); SA[26:]=sa.values; SB[26:]=sb.values
    return SA,SB

def time_windows(SB, xc, lead=26):
    """x is a reversal-time candidate if Senkou B is flat at x (box) AND flat at x-26 (Chikou on a flat).
    Beyond the plotted cloud (x > xc+26) only the x-26 condition can be checked."""
    ok=np.isfinite(SB); n=len(SB)
    flat=np.zeros(n,bool)
    for x in range(1,n):
        if ok[x] and ok[x-1] and SB[x]==SB[x-1]: flat[x]=flat[x-1]=True
    cand=[x for x in range(n) if flat[x] and x-lead>=0 and flat[x-lead]]
    cand+=[x for x in range(n,xc+2*lead+1) if x-lead<n and flat[x-lead]]
    out=[]
    for x in sorted(set(cand)):
        if out and x==out[-1][1]+1: out[-1][1]=x
        else: out.append([x,x])
    return [(a,b) for a,b in out]

def triangles(df, xc, L=130, eps=0.25, deg=20.0, min_dy=1.0, min_dx=3.0, angle_max=90.0, spacing=26):
    a=atr14(df).iloc[xc]; SA,SB=cloud(df,xc)
    x=np.arange(len(SA)); m=np.isfinite(SA)&np.isfinite(SB)&(x>=xc-L)
    xs=x[m].astype(float); ys=SA[m]/a; lab=np.sign(SA[m]-SB[m]).astype(int)
    steeps,tris=bb4.steep_triangles(xs,ys,eps=eps,deg=deg,min_dy=min_dy,min_dx=min_dx,lab=(xs,lab),maxdx=40)
    W=[w for w in bb4.wedges(tris) if bb4.apex_angle(w)<angle_max]
    return dict(a=a,SA=SA,SB=SB,xs=xs,ys=ys,steeps=steeps,tris=tris,W=W)

def find_zones(W, box, last, opens, H=3.0, spacing=26, mincover=3, maxdist=8.0, top=3):
    """zone = region bounded by two wedges (distinct triangles, same colour, < spacing bars apart),
    covered by >= mincover triangles at its centre. Cut H ATR from the narrow end."""
    res=[]; by={}
    for w in W:
        if w.opens==opens: by.setdefault((w.col,w.k),[]).append(w)
    for col in set(c for c,_ in by):
        ks=sorted(k for c,k in by if c==col)
        for pair in itertools.combinations(ks,2):
            var=[by[(col,k)][0] for k in pair]
            if abs(var[0].t['mid'][0]-var[1].t['mid'][0])>spacing: continue
            poly=region(var,box)
            if len(poly)<3: continue
            apex=max(poly,key=lambda p:p[1]) if opens=='down' else min(poly,key=lambda p:p[1])
            if abs(apex[1]-(box[3] if opens=='down' else box[2]))<1e-6 or abs(apex[1]-last)>maxdist: continue
            cut=clip_halfplane(poly,0,1,-(apex[1]-H)) if opens=='down' else clip_halfplane(poly,0,-1,apex[1]+H)
            if len(cut)<3: continue
            cx=sum(p[0] for p in cut)/len(cut); cy=sum(p[1] for p in cut)/len(cut)
            cover=len({w2.k for w2 in W if w2.opens==opens and w2.col==col and all(a*cx+b*cy+c>=-1e-9 for a,b,c in w2.halfplanes())})
            if cover<mincover: continue
            res.append({'opens':opens,'col':col,'apex':apex,'poly':cut,'area':area(cut),'cover':cover,'var':var})
    res.sort(key=lambda r:(r['area']-0.3*r['cover']))
    keep=[]
    for r in res:
        if all(math.hypot(r['apex'][0]-k['apex'][0],(r['apex'][1]-k['apex'][1])*3)>3 for k in keep): keep.append(r)
        if len(keep)>=top: break
    return keep

def cut_by_windows(poly, windows):
    out=[]
    for a,b in windows:
        p=clip_halfplane(poly,1,0,-(a-0.5)); p=clip_halfplane(p,-1,0,b+0.5) if len(p)>=3 else []
        if len(p)>=3: out.append(((a,b),p))
    return out

def analyse(df, xc, setup='both', **kw):
    T=triangles(df,xc,**{k:v for k,v in kw.items() if k in ('L','eps','deg','min_dy','min_dx','angle_max')})
    last=df.close.iloc[xc]/T['a']; box=(xc-3,xc+52,last-9,last+9)
    H=kw.get('H',3.0); mincover=kw.get('mincover',3)
    zones=[]
    for opens in ('down','up'): zones+=find_zones(T['W'],box,last,opens,H=H,mincover=mincover)
    if setup == 'sell':   zones = [z for z in zones if z['opens'] == 'up']    # resistance above price (5.2/5.3)
    elif setup == 'buy':  zones = [z for z in zones if z['opens'] == 'down']  # support below price
    win=time_windows(T['SB'],xc)
    for z in zones: z['timed']=cut_by_windows(z['poly'],win)
    T.update(zones=zones,windows=win,last=last,box=box,setup=setup)
    enrich_zones(T, df, xc)
    T['levels'] = time_levels(T, zones)
    return T

# ======================================================================
# Black Bermuda method — completion pieces (v1.1)
# Implements: flat-Senkou-B segments (7.4.1/2), time-equilibrium confirmation
# of a zone (7.4.4 "Use 1"), Chikou / Double Bermuda (6.13), and the
# time-based price levels of section 8 (with a documented assumption,
# since 12.4 says the exact copy geometry is only in the course video).
# ======================================================================
def flat_sb_segments(SB):
    """Maximal runs (x0, x1, y) of exactly-equal Senkou B values (any length, even 2)."""
    ok = np.isfinite(SB); n = len(SB); segs = []; i = 0
    while i < n - 1:
        if ok[i] and ok[i + 1] and SB[i] == SB[i + 1]:
            j = i
            while j + 1 < n and ok[j + 1] and SB[j + 1] == SB[i]:
                j += 1
            segs.append((i, j, float(SB[i])))
            i = j + 1
        else:
            i += 1
    return segs

def point_in_poly(poly, x, y):
    n = len(poly); inside = False; j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside

def enrich_zones(T, df, xc):
    """Per-zone time confirmation (7.4.4), price-in-zone and Chikou-in-zone (6.13)."""
    atr = T['a']; last = T['last']
    chikou = (xc - 26, float(df.close.iloc[xc] / atr)) if xc >= 26 else None
    sb_segs = flat_sb_segments(T['SB'])
    for z in T['zones']:
        ys = [p[1] for p in z['poly']]
        top, bot = max(ys), min(ys)
        z['time_confirmed'] = any(s[2] >= top or s[2] <= bot for s in sb_segs)
        z['price_in_zone'] = point_in_poly(z['poly'], xc, last)
        z['chikou_in_zone'] = bool(chikou) and point_in_poly(z['poly'], chikou[0], chikou[1])
    T['double_bermuda'] = any(z['price_in_zone'] and z['chikou_in_zone'] for z in T['zones'])
    T['sb_flats'] = sb_segs
    T['chikou'] = chikou
    return T

def time_levels(T, zones):
    """
    Section 8 — horizontal + vertical lines through the final triangle's apex,
    then vertical lines 9 / 17 / 26 candles ahead, then "three price levels".

    ASSUMPTION (method 12.4: exact copy geometry is unspecified, video-only):
    the final triangle is re-drawn at each vertical line by horizontal translation
    (same slopes, apex on the line, apex price unchanged). The three reported
    levels are the crossing points of the ORIGINAL outer leg with the COPIED
    outer leg of the triangle translated by k candles (k = 9, 17, 26):
        u     = m1*k / (m1 - m2)          (offset along the outer leg)
        y_lvl = ay + m2 * u
    For peak triangles the levels fall below the apex (toward price); for dip
    triangles they fall above it. All raw leg values are returned per horizon so
    the user can inspect/adjust. Validate visually before trading.
    """
    cand = [w.t for z in zones for w in z.get('var', [])]
    if not cand:
        return None
    final = max(cand, key=lambda t: t['apex'][0])
    ax, ay = float(final['apex'][0]), float(final['apex'][1])
    m1, m2 = float(final['A'][5]), float(final['B'][5])
    if abs(m1 - m2) < 1e-9:
        return None
    details, levels = [], []
    for k in (9, 17, 26):
        yv1 = ay + m1 * k          # leg 1 value at vertical x = ax + k (8.2)
        yv2 = ay + m2 * k          # leg 2 value at vertical x = ax + k
        u = m1 * k / (m1 - m2)
        y_copy = ay + m2 * u       # crossing with the k-translated copy (assumption)
        levels.append(float(y_copy))
        details.append({'offset': k, 'vertical_x': float(ax + k),
                        'y_leg1': float(yv1), 'y_leg2': float(yv2),
                        'y_copy_cross': float(y_copy)})
    return {
        'final_triangle': {'type': final['type'], 'col': int(final['col']),
                           'apex': [ax, ay]},
        'horizontal_y': ay,
        'verticals': [float(ax), float(ax + 9), float(ax + 17), float(ax + 26)],
        'levels': [float(y) for y in levels],
        'details': details,
        'assumption': ('Section 8 copy geometry is unspecified by the course (12.4). '
                       'Reported levels = crossing of the original outer leg with the '
                       'outer leg of the same triangle translated +k candles horizontally. '
                       'Verify visually; not a guarantee of reversal.'),
    }
