import numpy as np, math, itertools

def clip_halfplane(poly, a, b, c):
    """keep points with a*x + b*y + c >= 0 (Sutherland-Hodgman on a convex polygon)"""
    out=[]
    n=len(poly)
    for i in range(n):
        p,q=poly[i],poly[(i+1)%n]
        fp=a*p[0]+b*p[1]+c; fq=a*q[0]+b*q[1]+c
        if fp>=0: out.append(p)
        if (fp>=0)!=(fq>=0):
            t=fp/(fp-fq); out.append((p[0]+t*(q[0]-p[0]), p[1]+t*(q[1]-p[1])))
    return out

def area(poly):
    if len(poly)<3: return 0.0
    s=0.0
    for i in range(len(poly)):
        x1,y1=poly[i]; x2,y2=poly[(i+1)%len(poly)]; s+=x1*y2-x2*y1
    return abs(s)/2

def line_inter(P1,m1,P2,m2):
    """lines y = P.y + m (x - P.x)  (y up)"""
    if abs(m1-m2)<1e-9: return None
    x=(P2[1]-P1[1]+m1*P1[0]-m2*P2[0])/(m1-m2)
    return (x, P1[1]+m1*(x-P1[0]))

class Wedge:
    """open wedge with apex A and outward directions uL=(-1,-mL), uR=(1,mR)  (y up)"""
    def __init__(self, apex, mL, mR, tag=None):
        self.A=apex; self.mL=mL; self.mR=mR; self.tag=tag
        uL=np.array([-1.0,-mL]); uR=np.array([1.0,mR]); self.uL=uL/np.linalg.norm(uL); self.uR=uR/np.linalg.norm(uR)
    def halfplanes(self):
        """two half-planes (a,b,c) whose intersection is the wedge"""
        A=np.array(self.A); res=[]
        for u,v in ((self.uL,self.uR),(self.uR,self.uL)):
            # points p with cross(u, p-A) having the same sign as cross(u, v)
            s=np.sign(u[0]*v[1]-u[1]*v[0])
            # cross(u,p-A)=u0*(py-Ay)-u1*(px-Ax)
            a=-u[1]*s; b=u[0]*s; c=-(a*A[0]+b*A[1])
            res.append((a,b,c))
        return res

def region(wedges, box):
    """convex intersection of wedges inside box=(x0,x1,y0,y1) (y up)"""
    x0,x1,y0,y1=box
    poly=[(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
    for w in wedges:
        for (a,b,c) in w.halfplanes():
            poly=clip_halfplane(poly,a,b,c)
            if len(poly)<3: return []
    return poly
