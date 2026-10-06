#!/usr/bin/env python3
"""What the panel SHOULD show for a letterbox step: letterbox-card.c's card at
its source size, magnified (nearest neighbour) to the destination and placed on
a black 1280x720 panel. Compare operator photos against these. Runs on the host.

    letterbox-reference.py OUTDIR      # writes ref-*.png for the Phase 3 steps
"""
import numpy as np
from PIL import Image
RGB = {0:(110,110,110),1:(255,255,255),2:(0,0,0),3:(220,40,40),4:(60,180,40),5:(40,90,230),6:(220,210,40)}
def card(w,h):
    y,x=np.mgrid[0:h,0:w]
    m=min(w,h); r=m*2//5; rc=m//10
    c=np.zeros((h,w),int)
    def circ(cx,cy,R,t):
        d=(x-cx)**2+(y-cy)**2; return (d>=(R-t)**2)&(d<=R*R)
    lines=(abs(x*h-y*w)<w*3/2)|(abs((w-1-x)*h-y*w)<w*3/2)|(x==w//2)|(x==w//2-1)|(y==h//2)|(y==h//2-1)
    cir=circ(w//2,h//2,r,3)|circ(rc+100,rc+100,rc,2)|circ(w-rc-100,rc+100,rc,2)|circ(rc+100,h-rc-100,rc,2)|circ(w-rc-100,h-rc-100,rc,2)
    c[cir|lines]=1
    p1=(y>=40)&(y<88); p2=(y>=h-88)&(y<h-40); xa=(x>=40)&(x<88); xb=(x>=w-88)&(x<w-40)
    c[p2&xb]=6; c[p2&xa]=5; c[p1&xb]=4; c[p1&xa]=3
    tick=((x%64<2)&((y<28)|(y>=h-28)))|((x%16<2)&((y<14)|(y>=h-14)))|((y%64<2)&((x<28)|(x>=w-28)))|((y%16<2)&((x<14)|(x>=w-14)))
    c[tick]=1
    c[(x<4)|(y<4)|(x>=w-4)|(y>=h-4)]=2
    c[(x<2)|(y<2)|(x>=w-2)|(y>=h-2)]=1
    return c
def panel(name,w,h,ow,oh,dx,dy):
    c=card(w,h)
    yi=(np.arange(oh)*h)//oh; xi=(np.arange(ow)*w)//ow
    big=c[yi][:,xi]
    img=np.zeros((720,1280,3),np.uint8)
    lut=np.array([RGB[i] for i in range(7)],np.uint8)
    img[dy:dy+oh,dx:dx+ow]=lut[big]
    Image.fromarray(img).save(f"{name}.png")
import sys,os
os.chdir(sys.argv[1])
panel("ref-p1-s4",352,288,880,720,200,0)
panel("ref-q3-s3",720,576,960,720,160,0)
panel("ref-q5-s5",640,360,960,540,160,90)
panel("ref-q1-s1",640,360,1280,720,0,0)
