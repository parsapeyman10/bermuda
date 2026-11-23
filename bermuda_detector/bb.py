import numpy as np, pandas as pd, math, itertools, cv2
from scipy.signal import find_peaks
import matplotlib.cbook as cbook

def load_goog():
    d = cbook.get_sample_data('goog.npz')
    arr = d['price_data'] if hasattr(d,'files') else d
    df = pd.DataFrame({k: arr[k] for k in ['date','open','high','low','close']})
    df['date'] = pd.to_datetime(df['date'])
    return df.reset_index(drop=True)

def atr14(df):
    pc = df.close.shift(1)
    tr = pd.concat([df.high-df.low, (df.high-pc).abs(), (df.low-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(14).mean()

def ichimoku_upto(df, xc):
    d = df.iloc[:xc+1]
    hh = lambda n: d.high.rolling(n).max(); ll = lambda n: d.low.rolling(n).min()
    ten = (hh(9)+ll(9))/2; kij = (hh(26)+ll(26))/2
    sa = (ten+kij)/2; sb = (hh(52)+ll(52))/2
    n = len(d); SA = np.full(n+26, np.nan); SB = np.full(n+26, np.nan)
    SA[26:] = sa.values; SB[26:] = sb.values
    return SA, SB

def extremes(xs, ys, prom, dist=3):
    pk,_ = find_peaks(ys, prominence=prom, distance=dist)
    tr,_ = find_peaks(-ys, prominence=prom, distance=dist)
    ext = sorted([(float(xs[i]),'P',float(ys[i])) for i in pk] + [(float(xs[i]),'T',float(ys[i])) for i in tr])
    out=[]
    for e in ext:
        if out and out[-1][1]==e[1]:
            if (e[1]=='P' and e[2]>out[-1][2]) or (e[1]=='T' and e[2]<out[-1][2]): out[-1]=e
        else: out.append(e)
    return out

def stretches(xs, ys, eps_list=(0.05,0.1,0.2,0.4), min_dx=3, min_dy=0.5):
    pts = np.stack([xs, ys], 1).astype(np.float32).reshape(-1,1,2)
    out=[]
    for eps in eps_list:
        poly = cv2.approxPolyDP(pts, float(eps), False).reshape(-1,2)
        for a,b in zip(poly[:-1], poly[1:]):
            dx=float(b[0]-a[0]); dy=float(b[1]-a[1])
            if dx>=min_dx and abs(dy)>=min_dy:
                out.append((float(a[0]),float(a[1]),float(b[0]),float(b[1])))
    return out

def make_lines(ext, st):
    """lines: dict(x0,y0,m, owners:set(extreme idx), seg)"""
    lines=[]
    for k,e in enumerate(ext):
        lo = ext[k-1][0] if k>0 else -1e9
        hi = ext[k+1][0] if k+1<len(ext) else 1e9
        for (xa,ya,xb,yb) in st:
            m=(yb-ya)/(xb-xa)
            # left run: stretch inside (lo, e.x]; right run: inside [e.x, hi)
            left = (xa>=lo-2 and xb<=e[0]+2); right=(xa>=e[0]-2 and xb<=hi+2)
            if e[1]=='P': okL = left and m>0; okR = right and m<0
            else: okL = left and m<0; okR = right and m>0
            if okL or okR:
                lines.append({'x0':xa,'y0':ya,'m':m,'k':k,'side':'L' if okL else 'R','seg':(xa,ya,xb,yb)})
    # merge near-duplicate lines (same stretch seen from two extremes or at several scales)
    merged=[]
    for L in lines:
        for M in merged:
            if abs(L['m']-M['m'])<0.04*(1+abs(M['m'])) and abs((L['y0']+L['m']*(M['x0']-L['x0']))-M['y0'])<0.12:
                M['owners'].add(L['k']); break
        else:
            L=dict(L); L['owners']={L['k']}; merged.append(L)
    return merged

def inter(A,B):
    if abs(A['m']-B['m'])<1e-6: return None
    x=(B['y0']-A['y0']+A['m']*A['x0']-B['m']*B['x0'])/(A['m']-B['m'])
    y=A['y0']+A['m']*(x-A['x0'])
    return x,y

def zones(lines, xlo, xhi, ylo, yhi, amax=40.0, tol=0.35):
    n=len(lines); P={}
    for i in range(n):
        for j in range(i+1,n):
            q=inter(lines[i],lines[j])
            if q and xlo<=q[0]<=xhi and ylo<=q[1]<=yhi: P[(i,j)]=q
    res=[]
    for i in range(n):
        for j in range(i+1,n):
            if (i,j) not in P: continue
            for l in range(j+1,n):
                if (i,l) in P and (j,l) in P:
                    # need three distinct owner extremes
                    ok=False
                    for a in lines[i]['owners']:
                        for b in lines[j]['owners']:
                            for c in lines[l]['owners']:
                                if len({a,b,c})==3: ok=True
                    if not ok: continue
                    p1,p2,p3=P[(i,j)],P[(i,l)],P[(j,l)]
                    area=abs((p2[0]-p1[0])*(p3[1]-p1[1])-(p3[0]-p1[0])*(p2[1]-p1[1]))/2
                    if area<=amax:
                        cx=(p1[0]+p2[0]+p3[0])/3; cy=(p1[1]+p2[1]+p3[1])/3
                        conf=sum(1 for t in range(n) if abs(lines[t]['y0']+lines[t]['m']*(cx-lines[t]['x0'])-cy)<=tol)
                        res.append({'tri':(i,j,l),'pts':(p1,p2,p3),'area':area,'c':(cx,cy),'conf':conf})
    res.sort(key=lambda r:(r['area']-0.5*r['conf']))
    keep=[]
    for r in res:
        if all(math.hypot(r['c'][0]-k['c'][0],(r['c'][1]-k['c'][1])*2)>3 for k in keep): keep.append(r)
        if len(keep)>=4: break
    return keep

def analyse(df, xc, theta=0.6, L=130):
    a = atr14(df).iloc[xc]
    SA,SB = ichimoku_upto(df, xc)
    x = np.arange(len(SA)); ok=~np.isnan(SA)&(x>=xc-L)
    xs=x[ok].astype(float); ys=SA[ok]/a
    ext = extremes(xs, ys, theta)
    st = stretches(xs, ys)
    lines = make_lines(ext, st)
    last = df.close.iloc[xc]/a
    Z = zones(lines, xc-3, xc+52, last-6, last+6)
    return dict(a=a,SA=SA,SB=SB,xs=xs,ys=ys,ext=ext,st=st,lines=lines,zones=Z,last=last)
