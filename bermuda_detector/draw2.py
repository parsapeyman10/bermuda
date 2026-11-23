import sys; sys.path.insert(0,'/home/claude/bb')
import bb, bb2, numpy as np, math
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle

def draw(df, xc, fn, **kw):
    r=bb2.analyse2(df,xc,**kw); a=r['a']; SA,SB=r['SA'],r['SB']
    x0,x1=xc-110,xc+62
    fig,ax=plt.subplots(figsize=(13,7.2),dpi=110)
    for i in range(max(0,x0),min(len(df),x1)):
        o,h,l,c=df.open[i],df.high[i],df.low[i],df.close[i]; col='#2e8b57' if c>=o else '#c0392b'; al=0.16 if i<=xc else 0.85
        ax.plot([i,i],[l,h],color=col,alpha=al,lw=0.8); ax.add_patch(Rectangle((i-0.3,min(o,c)),0.6,max(abs(c-o),1e-9),color=col,alpha=al,lw=0))
    xx=np.arange(len(SA)); m=xx>=x0; up=SA>=SB
    ax.fill_between(xx[m],SA[m],SB[m],where=(up&m&~np.isnan(SA)&~np.isnan(SB))[m],color='#7bc67e',alpha=0.4,lw=0)
    ax.fill_between(xx[m],SA[m],SB[m],where=((~up)&m&~np.isnan(SA)&~np.isnan(SB))[m],color='#f2a1c0',alpha=0.4,lw=0)
    ax.plot(xx[m],SA[m],'k',lw=1.6); ax.axvline(xc,color='gray',ls=':')
    for (ex,t,ey) in r['ext']: ax.plot(ex,ey*a,'o',mfc='none',mec='navy',ms=10,mew=1.5)
    used=set()
    for z in r['zones'][:1]:
        for w in z['var']: used.add(id(w))
    L=400.0
    for w in r['W']:
        sel=id(w) in used
        for u,mm,seg in ((w.uL,w.mL,w.l),(w.uR,w.mR,w.r)):
            p0=np.array(w.A); p1=p0+u*L
            ax.plot([p0[0],p1[0]],[p0[1]*a,p1[1]*a],color='crimson' if sel else '0.6',lw=1.5 if sel else 0.6,ls='--',alpha=0.95 if sel else 0.5)
            if sel: ax.plot([seg[0],seg[2]],[seg[1]*a,seg[3]*a],color='crimson',lw=3.4)
        if sel: ax.plot(w.A[0],w.A[1]*a,'^' if w.tag[1]=='P' else 'v',color='crimson',ms=8)
    for zi,z in enumerate(r['zones'][:2]):
        ax.add_patch(Polygon([(p[0],p[1]*a) for p in z['poly']],closed=True,fc='black',ec='red',alpha=0.8,lw=1.5))
        ax.annotate(f"zone{zi+1} {'support' if z['type']=='P' else 'resistance'} cover={z['cover']}",(z['apex'][0],z['apex'][1]*a),xytext=(z['apex'][0]-30,z['apex'][1]*a+30),color='darkred',fontsize=9,arrowprops=dict(arrowstyle='->',color='darkred'))
    ylo=df.low[max(0,x0):xc+1].min()*0.92; yhi=df.high[max(0,x0):min(len(df),x1)].max()*1.06
    ax.set_xlim(x0,x1); ax.set_ylim(ylo,yhi)
    ax.set_title(f"v0.2 wedge zones  bar {xc} ({df.date[xc].date()})  extremes={len(r['ext'])} wedges={len(r['W'])} zones={len(r['zones'])}  (solid = outcome)")
    fig.tight_layout(); fig.savefig(fn); plt.close(fig); return r

if __name__=='__main__':
    df=bb.load_goog()
    for xc in (884,848):
        r=draw(df,xc,f'/home/claude/bb/w_{xc}.png'); print(xc,[(z['type'],z['cover'],round(z['area'],1)) for z in r['zones']])
