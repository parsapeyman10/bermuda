import cv2, numpy as np, math, itertools, sys
sys.path.insert(0,'/home/claude/bb'); sys.path.insert(0,'/home/claude/zoom')
import bb, legcheck as LC
from wedge import Wedge, region, area, line_inter, clip_halfplane
import bb2

def wedges_px(lg, maxdx):
    W=[]
    for d in lg:
        e=d['e']
        for l in d['L']:
            for r in d['R']:
                ap=line_inter((l[0],l[1]),l[4],(r[0],r[1]),r[4])
                if ap is None: continue
                ok=(ap[1]<=e[2]+1e-6) if e[1]=='T' else (ap[1]>=e[2]-1e-6)
                if not ok or abs(ap[0]-e[0])>maxdx: continue
                w=Wedge(ap,l[4],r[4],tag=(d['k'],e[1])); w.l=l; w.r=r; w.e=e; W.append(w)
    return W

def zones_px(W, box, H, top=6):
    res=[]
    for typ in ('T','P'):
        by={}
        for w in W:
            if w.tag[1]==typ: by.setdefault(w.tag[0],[]).append(w)
        for trio in itertools.combinations(sorted(by),3):
            for var in itertools.product(*[by[k] for k in trio]):
                poly=region(list(var),box)
                if len(poly)<3: continue
                apex=min(poly,key=lambda p:p[1]) if typ=='T' else max(poly,key=lambda p:p[1])
                x0,x1,y0,y1=box
                if abs(apex[1]-(y0 if typ=='T' else y1))<1e-6: continue
                cut=clip_halfplane(poly,0,-1,apex[1]+H) if typ=='T' else clip_halfplane(poly,0,1,-(apex[1]-H))
                if len(cut)<3: continue
                cx=sum(p[0] for p in cut)/len(cut); cy=sum(p[1] for p in cut)/len(cut)
                cover=sum(1 for w in W if w.tag[1]==typ and all(a*cx+b*cy+c>=-1e-9 for a,b,c in w.halfplanes()))
                res.append({'type':typ,'apex':apex,'poly':cut,'area':area(cut),'cover':cover,'trio':trio,'var':var})
    res.sort(key=lambda r:(-r['cover'],r['area']))
    keep=[]
    for r in res:
        if all(math.hypot(r['apex'][0]-k['apex'][0],r['apex'][1]-k['apex'][1])>40 for k in keep): keep.append(r)
        if len(keep)>=top: break
    return keep

def run(xmax_view=None, tag='full'):
    im=cv2.imread('/home/claude/gt/p64_up.jpg'); sc=0.6
    roi=(150,2050,300,1000)
    curve=LC.track(im,roi)
    if xmax_view: curve=curve[curve[:,0]<=xmax_view/sc]
    xs=curve[:,0].astype(float); ys=-curve[:,1].astype(float)          # y up
    ext=bb.extremes(xs,ys,22,dist=30)
    st=bb.stretches(xs,ys,eps_list=(3,6,9,14),min_dx=15,min_dy=25)
    lg=bb2.legs(ext,st,mmin=0.5,nper=2); W=wedges_px(lg,maxdx=450)
    box=(xs.min(),xs.max()+300,-1500,-250)
    Z=zones_px(W,box,H=200)
    # instructor's black triangle
    g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY); mask=(g<95).astype(np.uint8)*255
    r=np.zeros_like(mask); r[int(590/sc):int(700/sc),int(700/sc):int(800/sc)]=1; mask*=r
    cs,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE); c=max(cs,key=cv2.contourArea)
    tri=cv2.approxPolyDP(c,8,True).reshape(-1,2); apex=tri[np.argmin(tri[:,1])]
    print(tag,'extremes',[(int(e[0]*sc),e[1]) for e in ext],'wedges',len(W),'zones',len(Z))
    print('  instructor triangle apex (view px):',(int(apex[0]*sc),int(apex[1]*sc)),'verts',[(int(x*sc),int(y*sc)) for x,y in tri])
    for z in Z[:4]:
        ap=(z['apex'][0]*sc, -z['apex'][1]*sc)
        d=math.hypot(ap[0]-apex[0]*sc, ap[1]-apex[1]*sc)
        print('  zone',z['type'],'cover',z['cover'],'apex(view)',(int(ap[0]),int(ap[1])),'dist to instructor apex (view px)',int(d))
    # overlay
    vis=im.copy()
    for p in curve.astype(int): cv2.circle(vis,tuple(p),1,(0,200,0),-1)
    for e in ext: cv2.circle(vis,(int(e[0]),int(-e[2])),14,(255,0,0),2)
    if Z:
        z=Z[0]
        for w in z['var']:
            for u,seg in ((w.uL,w.l),(w.uR,w.r)):
                p0=np.array(w.A); p1=p0+u*1500
                cv2.line(vis,(int(p0[0]),int(-p0[1])),(int(p1[0]),int(-p1[1])),(0,0,255),2)
                cv2.line(vis,(int(seg[0]),int(-seg[1])),(int(seg[2]),int(-seg[3])),(0,0,255),6)
        cv2.fillPoly(vis,[np.array([(int(x),int(-y)) for x,y in z['poly']])],(255,0,255))
    cv2.polylines(vis,[tri.reshape(-1,1,2)],True,(0,165,255),4)
    cv2.imwrite(f'/home/claude/gt/p64_zone_{tag}.jpg',cv2.resize(vis,None,fx=0.55,fy=0.55))
    return Z

run(None,'full'); run(800,'trunc800')
