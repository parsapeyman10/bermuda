import sys; sys.path.insert(0,'/home/claude/work')
import numpy as np, bb, bermuda_core as C
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
PARAMS=dict(deg=8,eps=0.2,min_dy=0.5,min_dx=2)
def analyse(df,xc,mincover=3):
    T=C.triangles(df,xc,**PARAMS); last=df.close.iloc[xc]/T['a']; box=(xc-3,xc+52,last-9,last+9)
    Z=[]
    for o in ('down','up'): Z+=C.find_zones(T['W'],box,last,o,mincover=mincover)
    win=C.time_windows(T['SB'],xc)
    for z in Z: z['timed']=C.cut_by_windows(z['poly'],win)
    T.update(zones=Z,windows=win,last=last,box=box); return T
def draw(df,xc,fn,mincover=3):
    r=analyse(df,xc,mincover); a=r['a']; SA,SB=r['SA'],r['SB']; x0,x1=xc-110,xc+62
    fig,ax=plt.subplots(figsize=(13,7.2),dpi=110)
    for i in range(max(0,x0),min(len(df),x1)):
        o,h,l,c=df.open[i],df.high[i],df.low[i],df.close[i]; col='#2e8b57' if c>=o else '#c0392b'; al=0.16 if i<=xc else 0.85
        ax.plot([i,i],[l,h],color=col,alpha=al,lw=0.8); ax.add_patch(Rectangle((i-0.3,min(o,c)),0.6,max(abs(c-o),1e-9),color=col,alpha=al,lw=0))
    xx=np.arange(len(SA)); m=xx>=x0; up=SA>=SB
    ax.fill_between(xx[m],SA[m],SB[m],where=(up&m&~np.isnan(SA)&~np.isnan(SB))[m],color='#7bc67e',alpha=0.4,lw=0)
    ax.fill_between(xx[m],SA[m],SB[m],where=((~up)&m&~np.isnan(SA)&~np.isnan(SB))[m],color='#f2a1c0',alpha=0.4,lw=0)
    ax.plot(xx[m],SA[m],'k',lw=1.6); ax.axvline(xc,color='gray',ls=':')
    ylo=df.low[max(0,x0):xc+1].min()*0.9; yhi=df.high[max(0,x0):min(len(df),x1)].max()*1.08
    for (wa,wb) in r['windows']:
        if wb>=xc-3 and wa<=x1: ax.axvspan(wa-0.5,wb+0.5,ymin=0,ymax=0.06,color='orange',alpha=0.8)
    used=set()
    for z in r['zones'][:1]: used={id(w) for w in z['var']}
    for w in r['W']:
        sel=id(w) in used
        for u in (w.uL,w.uR):
            p0=np.array(w.A); p1=p0+u*300
            ax.plot([p0[0],p1[0]],[p0[1]*a,p1[1]*a],color='crimson' if sel else '0.7',lw=1.6 if sel else 0.5,ls='--',alpha=0.95 if sel else 0.5)
        if sel: ax.plot(w.A[0],w.A[1]*a,'v' if w.opens=='down' else '^',color='crimson',ms=9)
    for z in r['zones'][:1]:
        ax.add_patch(Polygon([(p[0],p[1]*a) for p in z['poly']],closed=True,fc='black',ec='red',alpha=0.5,lw=1.5))
        for (win,p) in z['timed']:
            ax.add_patch(Polygon([(q[0],q[1]*a) for q in p],closed=True,fc='orange',ec='black',alpha=0.95,lw=1.2))
        ax.annotate(f"zone ({'support' if z['opens']=='down' else 'resistance'}), cover={z['cover']}; orange = zone AND time window",(z['apex'][0],z['apex'][1]*a),xytext=(z['apex'][0]-45,z['apex'][1]*a+ (yhi-ylo)*0.1),color='darkred',fontsize=9,arrowprops=dict(arrowstyle='->',color='darkred'))
    ax.set_xlim(x0,x1); ax.set_ylim(ylo,yhi)
    ax.set_title(f"v0.4  GOOG daily bar {xc} ({df.date[xc].date()}):  triangles={len(r['tris'])}  zones={len(r['zones'])}  orange strip at bottom = time windows (flat Senkou B + 26-bar check)",fontsize=10)
    fig.tight_layout(); fig.savefig(fn); plt.close(fig); return r
if __name__=='__main__':
    df=bb.load_goog(); hits=[]
    for xc in range(160,len(df)-60,2):
        if analyse(df,xc)['zones']: hits.append(xc)
    print('bars with a zone (step 2):',hits)
    if hits:
        xc=hits[len(hits)//2]; r=draw(df,xc,'/home/claude/work/core_example.png'); z=r['zones'][0]
        print('example bar',xc,'zone',z['opens'],'apex',(round(z['apex'][0],1),round(z['apex'][1]*r['a'],1)),'cover',z['cover'],'timed pieces',len(z['timed']))
