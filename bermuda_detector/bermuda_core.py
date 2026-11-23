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

def triangles(df, xc, L=130, eps=0.25, deg=20.0, min_dy=1.0, min_dx=3.0, angle_max=180.0, spacing=26):
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

def analyse(df, xc, **kw):
    T=triangles(df,xc,**{k:v for k,v in kw.items() if k in ('L','eps','deg','min_dy','min_dx','angle_max')})
    last=df.close.iloc[xc]/T['a']; box=(xc-3,xc+52,last-9,last+9)
    H=kw.get('H',3.0); mincover=kw.get('mincover',3)
    zones=[]
    for opens in ('down','up'): zones+=find_zones(T['W'],box,last,opens,H=H,mincover=mincover)
    win=time_windows(T['SB'],xc)
    for z in zones: z['timed']=cut_by_windows(z['poly'],win)
    T.update(zones=zones,windows=win,last=last,box=box); return T
