import numpy as np, cv2, math, subprocess, sys
from scipy.signal import find_peaks

def load(pdf, pg, tag):
    subprocess.run(['pdftoppm','-r','200','-f',str(pg),'-l',str(pg),'-jpeg',pdf,f'/home/claude/zoom/{tag}'],check=True)
    import glob
    f = glob.glob(f'/home/claude/zoom/{tag}-*.jpg')[0]
    return cv2.rotate(cv2.imread(f), cv2.ROTATE_90_CLOCKWISE)

def track(im, roi, lam=5.0, maxjump=45):
    x0,x1,y0,y1 = roi
    g = cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32),(3,3),0)
    sub = 255.0 - g[y0:y1, x0:x1]
    H,W = sub.shape; ar = np.arange(H)
    cost = np.zeros((H,W),np.float32); back = np.zeros((H,W),np.int32); cost[:,0] = -sub[:,0]
    for x in range(1,W):
        prev = cost[:,x-1]; best = np.full(H,1e9,np.float32); arg = np.zeros(H,np.int32)
        for dy in range(-maxjump,maxjump+1):
            sh = np.full(H,1e9,np.float32)
            if dy>0: sh[dy:] = prev[:H-dy]
            elif dy<0: sh[:dy] = prev[-dy:]
            else: sh = prev.copy()
            c = sh + lam*abs(dy); m = c<best; best[m]=c[m]; arg[m]=(ar-dy)[m]
        cost[:,x] = best - sub[:,x]; back[:,x] = arg
    y = np.zeros(W,int); y[-1] = int(np.argmin(cost[:,-1]))
    for x in range(W-1,0,-1): y[x-1] = back[y[x],x]
    return np.stack([np.arange(W)+x0, y+y0],1).astype(np.float32)

def ang_of(a,b):
    return math.degrees(math.atan2(-(b[1]-a[1]), b[0]-a[0])) % 180

def analyze(pdf, pg, tag, roi, eps=2.5, prom=14, smin=35):
    im = load(pdf, pg, tag)
    curve = track(im, roi)
    poly = cv2.approxPolyDP(curve.reshape(-1,1,2), eps, False).reshape(-1,2)
    # extremes of the tracked curve
    yy = curve[:,1]
    pk,_ = find_peaks(-yy, prominence=prom, distance=8)   # peaks (small y)
    tr,_ = find_peaks(yy,  prominence=prom, distance=8)   # troughs
    ext = sorted([(int(curve[i,0]),'P',int(i)) for i in pk]+[(int(curve[i,0]),'T',int(i)) for i in tr])
    clean=[]
    for e in ext:
        if clean and clean[-1][1]==e[1]:
            a=clean[-1]; 
            if (e[1]=='P' and yy[e[2]]<yy[a[2]]) or (e[1]=='T' and yy[e[2]]>yy[a[2]]): clean[-1]=e
        else: clean.append(e)
    # dashed lines: mask the curve neighbourhood then Hough
    g = cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY),(3,3),0)
    mask = (g<105).astype(np.uint8)*255
    for p in curve.astype(int): cv2.circle(mask, tuple(p), 6, 0, -1)
    x0,x1,y0,y1 = roi; m2 = np.zeros_like(mask); m2[y0-150:y1+250, x0:x1]=mask[y0-150:y1+250, x0:x1]
    hl = cv2.HoughLinesP(m2,1,np.pi/360,threshold=30,minLineLength=70,maxLineGap=30)
    H=[]
    if hl is not None:
        for l in hl[:,0]:
            a,b=(l[0],l[1]),(l[2],l[3]); an=ang_of(a,b)
            if min(abs(an-0),abs(an-90),abs(an-180))<3: continue
            H.append((a,b,an))
    # predicted legs: dominant straight stretch on each side of each extreme
    preds=[]
    segs=[(poly[i],poly[i+1]) for i in range(len(poly)-1)]
    for k,e in enumerate(clean):
        xe=e[0]
        left_x0 = clean[k-1][0] if k>0 else x0
        right_x1 = clean[k+1][0] if k+1<len(clean) else x1
        for side,(xa,xb) in (('L',(left_x0,xe)),('R',(xe,right_x1))):
            cand=[(a,b) for a,b in segs if a[0]>=xa-3 and b[0]<=xb+3 and abs(b[1]-a[1])>=6 and 90<=0 or (a[0]>=xa-3 and b[0]<=xb+3 and abs(b[1]-a[1])>=6)]
            cand=[(a,b) for a,b in cand if 35<=min(ang_of(a,b),180-ang_of(a,b))<=89.9]
            if not cand: continue
            a,b=max(cand,key=lambda s:abs(s[1][1]-s[0][1]))
            preds.append((e,side,a,b,ang_of(a,b)))
    def dist_pt_line(p,a,b):
        (x1_,y1_),(x2_,y2_)=a,b; return abs((y2_-y1_)*p[0]-(x2_-x1_)*p[1]+x2_*y1_-y2_*x1_)/math.hypot(x2_-x1_,y2_-y1_)
    hits=0; rows=[]
    for e,side,a,b,an in preds:
        best=None
        for ha,hb,han in H:
            d=max(dist_pt_line(a,ha,hb),dist_pt_line(b,ha,hb)); da=abs((an-han+90)%180-90)
            if da<=6 and d<=7:
                if best is None or d<best[0]: best=(round(d,1),round(da,1))
        rows.append((e[1],e[0],side,round(an,1),best)); hits+= best is not None
    vis=im.copy()
    for ha,hb,han in H: cv2.line(vis,tuple(map(int,ha)),tuple(map(int,hb)),(255,0,0),2)
    for e,side,a,b,an in preds:
        dx,dy=(b[0]-a[0]),(b[1]-a[1]); n=math.hypot(dx,dy); ux,uy=dx/n,dy/n
        p1=(int(a[0]-ux*400),int(a[1]-uy*400)); p2=(int(b[0]+ux*400),int(b[1]+uy*400))
        cv2.line(vis,p1,p2,(0,0,255),1)
    for p in curve.astype(int): cv2.circle(vis,tuple(p),1,(0,200,0),-1)
    return im,curve,clean,H,rows,hits,len(preds),vis

if __name__=='__main__':
    U='/mnt/user-data/uploads'
    jobs=[('p57',f'{U}/41-60.pdf',17,(640,1500,380,1080)),
          ('p58',f'{U}/41-60.pdf',18,(640,1500,380,1080))]
    for tag,pdf,pg,roi in jobs:
        im,curve,ext,H,rows,hits,n,vis=analyze(pdf,pg,tag,roi)
        print(tag,'extremes',len(ext),'dashed lines',len(H),'pred legs',n,'matched',hits)
        for r in rows: print('  ',r)
        cv2.imwrite(f'/home/claude/zoom/{tag}_legs.jpg', cv2.resize(vis[380:1250,640:1500],None,fx=1.2,fy=1.2))
