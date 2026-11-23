import sys; sys.path.insert(0,'/home/claude/bb')
import numpy as np, math, itertools
import bb
from wedge import Wedge, region, area, line_inter, clip_halfplane

def legs(ext, st, mmin=0.12, nper=2):
    out=[]
    for k,e in enumerate(ext):
        lo=ext[k-1][0] if k>0 else -1e9; hi=ext[k+1][0] if k+1<len(ext) else 1e9
        Ls=[];Rs=[]
        for (xa,ya,xb,yb) in st:
            m=(yb-ya)/(xb-xa)
            if abs(m)<mmin: continue
            left=(xa>=lo-2 and xb<=e[0]+2); right=(xa>=e[0]-2 and xb<=hi+2)
            if e[1]=='P': okL=left and m>0; okR=right and m<0
            else: okL=left and m<0; okR=right and m>0
            if okL: Ls.append((xa,ya,xb,yb,m))
            if okR: Rs.append((xa,ya,xb,yb,m))
        def pick(S, near):
            S=sorted(set(S),key=lambda s:-abs(s[3]-s[1]))
            keep=S[:nper]
            if S:
                adj=min(S,key=lambda s:abs(near(s)-e[0]))
                if adj not in keep: keep.append(adj)
            return keep
        out.append({'k':k,'e':e,'L':pick(Ls,lambda s:s[2]),'R':pick(Rs,lambda s:s[0])})
    return out

def wedges(L):
    W=[]
    for d in L:
        e=d['e']
        for l in d['L']:
            for r in d['R']:
                ap=line_inter((l[0],l[1]),l[4],(r[0],r[1]),r[4])
                if ap is None: continue
                ok=(ap[1]<=e[2]+1e-6) if e[1]=='T' else (ap[1]>=e[2]-1e-6)
                if not ok or abs(ap[0]-e[0])>25: continue
                w=Wedge(ap,l[4],r[4],tag=(d['k'],e[1])); w.l=l; w.r=r; w.e=e
                W.append(w)
    return W

def find_zones(W, box, last, H=3.0, maxdist=6.0, top=4):
    res=[]
    for typ in ('T','P'):
        by={}
        for w in W:
            if w.tag[1]==typ: by.setdefault(w.tag[0],[]).append(w)
        ks=sorted(by)
        for trio in itertools.combinations(ks,3):
            for var in itertools.product(*[by[k] for k in trio]):
                poly=region(list(var),box)
                if len(poly)<3: continue
                ys=[p[1] for p in poly]
                apex=min(poly,key=lambda p:p[1]) if typ=='T' else max(poly,key=lambda p:p[1])
                x0,x1,y0,y1=box
                if abs(apex[1]-(y0 if typ=='T' else y1))<1e-6: continue          # no narrow end inside the box
                if abs(apex[1]-last)>maxdist or not (x0<=apex[0]<=x1): continue
                # cut the open wedge-intersection at H ATR from its narrow end
                if typ=='T': cut=clip_halfplane(poly,0,-1,apex[1]+H)
                else: cut=clip_halfplane(poly,0,1,-(apex[1]-H))
                if len(cut)<3: continue
                cx=sum(p[0] for p in cut)/len(cut); cy=sum(p[1] for p in cut)/len(cut)
                cover=0
                for w in W:
                    if w.tag[1]!=typ: continue
                    inside=all(a*cx+b*cy+c>=-1e-9 for a,b,c in w.halfplanes())
                    cover+=inside
                res.append({'type':typ,'apex':apex,'poly':cut,'area':area(cut),'cover':cover,'trio':trio,'var':var})
    res.sort(key=lambda r:(-r['cover'],r['area']))
    keep=[]
    for r in res:
        if all(math.hypot(r['apex'][0]-k['apex'][0],(r['apex'][1]-k['apex'][1])*2)>3 for k in keep): keep.append(r)
        if len(keep)>=top: break
    return keep

def analyse2(df, xc, theta=0.8, Lb=130, H=3.0):
    a=bb.atr14(df).iloc[xc]; SA,SB=bb.ichimoku_upto(df,xc)
    x=np.arange(len(SA)); ok=~np.isnan(SA)&(x>=xc-Lb)
    xs=x[ok].astype(float); ys=SA[ok]/a
    ext=bb.extremes(xs,ys,theta); st=bb.stretches(xs,ys)
    lg=legs(ext,st); W=wedges(lg)
    last=df.close.iloc[xc]/a
    box=(xc-3,xc+52,last-9,last+9)
    Z=find_zones(W,box,last,H=H)
    return dict(a=a,SA=SA,SB=SB,xs=xs,ys=ys,ext=ext,legs=lg,W=W,zones=Z,last=last,box=box)
