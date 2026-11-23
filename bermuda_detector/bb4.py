import numpy as np, math, itertools, cv2
from wedge import Wedge, region, area, line_inter, clip_halfplane

def steep_triangles(xs, ys, eps=6.0, deg=40.0, min_dy=18.0, min_dx=6.0, lab=None, maxdx=600):
    m_leg=math.tan(math.radians(deg))
    pts=np.stack([xs,ys],1).astype(np.float32).reshape(-1,1,2)
    poly=cv2.approxPolyDP(pts,float(eps),False).reshape(-1,2)
    segs=[]
    for a,b in zip(poly[:-1],poly[1:]):
        dx=float(b[0]-a[0]); dy=float(b[1]-a[1]); m=dy/dx if dx!=0 else 1e9
        cls='U' if m>=m_leg else ('D' if m<=-m_leg else 'F')
        segs.append([float(a[0]),float(a[1]),float(b[0]),float(b[1]),cls,m])
    merged=[]
    for s in segs:
        if merged and merged[-1][4]==s[4] and s[4] in 'UD' and abs(math.degrees(math.atan(merged[-1][5]))-math.degrees(math.atan(s[5])))<15:
            q=merged[-1]; q[2]=s[2]; q[3]=s[3]; q[5]=(q[3]-q[1])/(q[2]-q[0])
        else: merged.append(s)
    steeps=[s for s in merged if s[4] in 'UD' and abs(s[3]-s[1])>=min_dy and (s[2]-s[0])>=min_dx]
    tris=[]
    for A,B in zip(steeps[:-1],steeps[1:]):
        if A[4]==B[4]: continue
        typ='P' if A[4]=='U' else 'T'
        ap=line_inter((A[0],A[1]),A[5],(B[0],B[1]),B[5])
        if ap is None or abs(ap[0]-(A[2]+B[0])/2)>maxdx: continue
        ok=(ap[1]>=max(A[3],B[1])-1e-6) if typ=='P' else (ap[1]<=min(A[3],B[1])+1e-6)
        if not ok: continue
        col=0
        if lab is not None:
            lx,ll=lab
            def lb(x): return int(ll[int(np.argmin(abs(lx-x)))])
            labs={lb(A[0]),lb(A[2]),lb(B[0]),lb(B[2])}
            if len(labs)!=1 or 0 in labs: continue
            col=labs.pop()
        tris.append({'A':A,'B':B,'type':typ,'apex':ap,'col':col,'mid':((A[2]+B[0])/2,(A[3]+B[1])/2)})
    return steeps,tris

def wedges(tris):
    W=[]
    for k,t in enumerate(tris):
        A,B=t['A'],t['B']; mL,mR=(A[5],B[5]) if A[2]<=B[0] else (B[5],A[5])
        nat=Wedge(t['apex'],mL,mR); cont=Wedge(t['apex'],mR,mL)
        for w,opens,kind in ((nat,'down' if t['type']=='P' else 'up','natural'),(cont,'up' if t['type']=='P' else 'down','continued')):
            w.k=k; w.t=t; w.opens=opens; w.kind=kind; w.col=t['col']; W.append(w)
    return W

def apex_angle(w): return math.degrees(math.acos(float(np.clip(np.dot(w.uL,w.uR),-1,1))))
