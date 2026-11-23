import sys, math, itertools, numpy as np, cv2
sys.path.insert(0,'/home/claude/gt')
import legcheck as LC, bb4
from wedge import region, clip_halfplane
from scipy.ndimage import median_filter
sc=0.55; PXB=16.06
im=cv2.imread('/home/claude/gt/p66_up.jpg')
curve=LC.track(im,(80,2150,380,1200)); X=curve[:,0].astype(float); Y=-curve[:,1].astype(float)
rgb=im[:,:,::-1].astype(float)
def side(x,y,a,b):
    return rgb[max(0,int(y)+a):max(1,int(y)+b), max(0,int(x)-4):int(x)+5].reshape(-1,3).mean(axis=0)
lab=[]
for x,y in zip(X,-Y):
    def score(c):
        r,g,b=c; return (r-g)+0.5*(b-g)*(r>g)-((g-r)+0.5*(g-b))*(g>r)
    su,sd=score(side(x,y,-22,-8)),score(side(x,y,8,22)); s=su if abs(su)>abs(sd) else sd
    lab.append(0 if abs(s)<9 else (1 if s>0 else -1))
lab=median_filter(np.array(lab),size=61); lab_t=(X,lab)
runs=[];st=0
for i in range(1,len(lab)+1):
    if i==len(lab) or lab[i]!=lab[st]:
        runs.append((int(X[st]*sc),int(X[i-1]*sc),{1:'pink',-1:'green',0:'none'}[lab[st]])); st=i
print('colour runs (display px):',[r for r in runs if r[1]-r[0]>25])
# instructor's two black triangles: sample the colour inside each, then find the apex
def tri_apex(cx,cy,r=70):
    c=np.median(im[cy-5:cy+5,cx-5:cx+5].reshape(-1,3),axis=0)
    m=(np.abs(im.astype(int)-c.astype(int)).sum(axis=2)<60).astype(np.uint8)*255
    roi=np.zeros_like(m); roi[cy-int(r/sc):cy+int(r/sc),cx-int(r/sc):cx+int(r/sc)]=1; m*=roi
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
    cs,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE); c_=max(cs,key=cv2.contourArea)
    hull=cv2.convexHull(c_).reshape(-1,2); apex=hull[np.argmin(hull[:,1])]
    return (int(apex[0]),int(apex[1])), int(cv2.contourArea(c_)*sc*sc)
targets={'A':tri_apex(int(548/sc),int(530/sc),r=150),'B':tri_apex(int(918/sc),int(745/sc))}
print("instructor triangles apex (full-res px) and area(display px^2):",targets)
def auto(xc_disp, target, spacing=26, deg=40, eps=6, pair=True):
    xc=xc_disp/sc; end=xc+26*PXB
    m=X<=end; xs,ys=X[m],Y[m]
    steeps,tris=bb4.steep_triangles(xs,ys,eps=eps,deg=deg,lab=lab_t)
    W=[w for w in bb4.wedges(tris) if bb4.apex_angle(w)<90]
    box=(xc-3*PXB,xc+52*PXB,-1500,-300)
    best=None
    by={}
    for w in W:
        if w.opens=='down': by.setdefault((w.col,w.k),[]).append(w)
    for col in set(c for c,_ in by):
        ks=sorted(k for c,k in by if c==col)
        for trio in itertools.combinations(ks,2 if pair else 3):
            var=[by[(col,k)][0] for k in trio]
            mids=[w.t['mid'][0] for w in var]
            if max(mids)-min(mids)>spacing*PXB: continue
            poly=region(var,box)
            if len(poly)<3: continue
            apex=max(poly,key=lambda p:p[1])
            if abs(apex[1]-box[3])<1e-6 or apex[0]<box[0]: continue
            if apex[1]>np.interp(xc,xs,ys)-100: continue
            cut=clip_halfplane(poly,0,1,-(apex[1]-130))
            if len(cut)<3: continue
            A_=abs(sum(cut[i][0]*cut[(i+1)%len(cut)][1]-cut[(i+1)%len(cut)][0]*cut[i][1] for i in range(len(cut))))/2
            cx=sum(p[0] for p in cut)/len(cut); cy=sum(p[1] for p in cut)/len(cut)
            cover=len({w2.k for w2 in W if w2.opens=='down' and w2.col==col and all(a*cx+b*cy+c>=-1e-9 for a,b,c in w2.halfplanes())})
            if cover<3: continue
            if best is None or A_<best[0]: best=(A_,apex,[(w.t['type'],w.kind,int(w.t['mid'][0]*sc),'cover%d'%cover) for w in var])
    return len(tris),len(W),best
for name,xcs in (('A',(440,470,500,520)),('B',(800,840,870,890))):
    tgt=targets[name][0]
    for xc in xcs:
        nt,nw,b=auto(xc,tgt)
        if not b: print(name,'x_c',xc,'| triangles',nt,'wedges',nw,'| no zone'); continue
        err=math.hypot(b[1][0]-tgt[0],b[1][1]+tgt[1])
        print(name,'x_c',xc,'| triangles',nt,'wedges',nw,'| zone apex(display)',(int(b[1][0]*sc),int(-b[1][1]*sc)),'| error',int(err),'px =',round(100*err/2200,1),'% |',b[2])
