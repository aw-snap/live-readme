#!/usr/bin/env python3
"""Photoreal rotating Earth, v6 — physically-proper shading + window chrome.
- Gamma-correct LINEAR lighting; day is Lambert-shaded, city lights are ADDITIVE (no double-darkening).
- Soft twilight terminator (TWI): the day->night edge fades over ~±10° like real atmospheric scattering,
  instead of the hard Lambert cut that read as a sharp line at README size.
- Frame is composited into the same window chrome as the SVG panels (title strip + three dots), env FRAME=0 to disable.
- Clouds (lit), water sun-glint, atmosphere; marker composited at SSAA res INSIDE each motion-blur subframe (AA + no jitter).
- Lighting locked to the real subsolar point. Transparent animated AVIF (+webp fallback).
Env: N (frames), MB (motion-blur subframes), SS (supersample), Q (avif quality), TWI (twilight width), FRAME, TITLE."""
import numpy as np, math, datetime, os
from PIL import Image, ImageDraw, ImageFont
Image.MAX_IMAGE_PIXELS = None

N   = int(os.environ.get("N","240")); MB=int(os.environ.get("MB","2"))
SS  = int(os.environ.get("SS","2"));  Q =int(os.environ.get("Q","56"))
W=int(os.environ.get("Wpx","380")); DUR=36.0; TILT=math.radians(-23.5)
AMB=0.035         # ambient / earthshine (linear)
NLIT=2.9          # city-light gain (linear)
CSTR=0.36         # cloud opacity (a bit more transparent)
GSTR=3.8          # sun-glint strength (linear)
ROUGH=0.24        # ocean roughness for GGX glint (larger = broader, softer glare)
TWI=float(os.environ.get("TWI","0.14"))   # twilight softness (sin of ~8°): softplus knee width of the sun term
GAMMA=2.2
NZ_LAT,NZ_LON=math.radians(-41.0),math.radians(174.0)

now=datetime.datetime.now(datetime.timezone.utc)
doy=now.timetuple().tm_yday
# subsolar longitude from a target UTC hour (env HOUR) for precomputed slots, else "now"; declination always from today's date
frac=float(os.environ["HOUR"]) if os.environ.get("HOUR","")!="" else now.hour+now.minute/60+now.second/3600
decl=math.radians(23.44)*math.sin(2*math.pi*(doy-81)/365.24)
lam_s=math.radians(15.0*(12.0-frac))
S=np.array([math.cos(decl)*math.cos(lam_s),math.cos(decl)*math.sin(lam_s),math.sin(decl)])
nz_local=(now+datetime.timedelta(hours=12)).strftime("%H:%M")
Wnz=np.array([math.cos(NZ_LAT)*math.cos(NZ_LON),math.cos(NZ_LAT)*math.sin(NZ_LON),math.sin(NZ_LAT)])
print(f"N={N} MB={MB} SS={SS} | UTC {now:%H:%M} subsolar lat{math.degrees(decl):+.0f} lon{math.degrees(lam_s):+.0f} | NZ {nz_local}")

def loadtex(p): return np.asarray(Image.open(p).convert("RGB").resize((2048,1024),Image.LANCZOS),np.float32)
DAY,NIGHT,CLOUD=loadtex("earth_clean.bin"),loadtex("earth_night.bin"),loadtex("clouds.bin")
TH,TW,_=DAY.shape
lum=DAY.mean(2)
WATER=np.clip((DAY[:,:,2]-np.maximum(DAY[:,:,0],DAY[:,:,1]))/18,0,1)*np.clip((135-lum)/70,0,1)
CLOUDD=np.clip((CLOUD.mean(2)-28)/180,0,1)
DAY_L=(DAY/255.0)**GAMMA; NIGHT_L=(NIGHT/255.0)**GAMMA        # linear-light textures (precomputed)

def bil(t,u,v):
    fu=(u%1.0)*TW-0.5; fv=np.clip(v,0,1)*(TH-1)
    x0=np.floor(fu).astype(int); y0=np.floor(fv).astype(int)
    x1=(x0+1)%TW; y1=np.clip(y0+1,0,TH-1); x0%=TW
    dx=fu-np.floor(fu); dy=fv-np.floor(fv)
    if t.ndim==3: dx=dx[...,None]; dy=dy[...,None]
    return t[y0,x0]*(1-dx)*(1-dy)+t[y0,x1]*dx*(1-dy)+t[y1,x0]*(1-dx)*dy+t[y1,x1]*dx*dy
def sm(a,b,x): tt=np.clip((x-a)/(b-a),0,1); return tt*tt*(3-2*tt)

GAM=math.pi/2-TILT; cg,sg=math.cos(GAM),math.sin(GAM)
BET=-math.pi/2+TILT; cb,sb=math.cos(BET),math.sin(BET)
Sp=W*SS; R=Sp*0.40; cx=cy=Sp/2.0   # 0.40 leaves room so the atmosphere halo isn't clipped
yy,xx=np.mgrid[0:Sp,0:Sp].astype(float) if False else np.mgrid[0:Sp,0:Sp]
yy=yy.astype(float); xx=xx.astype(float)
NX=(xx+0.5-cx)/R; NY=(cy-(yy+0.5))/R; R2=NX*NX+NY*NY; RR=np.sqrt(R2); NZ=np.sqrt(np.clip(1-R2,0,None))
UX=NX; UY=NY*cg-NZ*sg; UZ=NY*sg+NZ*cg
DISC=np.clip((1.0-RR)/(1.7/R),0,1)
OUTER=(RR>1.0)&(RR<1.22); GLOW=np.clip((1.22-RR)/0.22,0,1)
MCORE=np.array([1.0,0.10,0.05]); MRING=np.array([1.0,0.24,0.13])   # linear marker colors
DITH=np.random.RandomState(7).uniform(-1.3,1.3,(W,W,3))            # fixed dither to kill gradient banding

def subframe(a):
    ca,sa=math.cos(a),math.sin(a)
    Wx=UX*ca+UY*sa; Wy=-UX*sa+UY*ca; Wz=UZ
    lat=np.arcsin(np.clip(Wz,-1,1)); lon=np.arctan2(Wy,Wx)
    u=lon/(2*math.pi)+0.5; v=0.5-lat/math.pi
    dayL=bil(DAY_L,u,v); nightL=bil(NIGHT_L,u,v); cd=bil(CLOUDD,u,v); wat=bil(WATER,u,v)
    diff=Wx*S[0]+Wy*S[1]+Wz*S[2]
    # soft terminator: softplus(diff) ~= Lambert on the day side, exponential twilight tail into the night
    sun=np.clip(TWI*np.logaddexp(0.0,diff/TWI),0,1)
    # --- linear-light surface: Lambert day + ADDITIVE city lights ---
    surf=dayL*(AMB+sun)[...,None]
    nightfac=sm(0.10,-0.22,diff)                          # 1 on night, 0 on day (fades in across the twilight band)
    surf=surf+nightL*(nightfac*NLIT)[...,None]
    # sun-glint on water: GGX microfacet + Fresnel + Smith-G (broad glare, brightens toward the terminator)
    sz1x=S[0]*ca-S[1]*sa; sz1y=S[0]*sa+S[1]*ca; sz1z=S[2]
    Lvx=sz1x; Lvy=sz1y*cb-sz1z*sb; Lvz=sz1y*sb+sz1z*cb          # sun dir in view space (unit)
    hx,hy,hz=Lvx,Lvy,Lvz+1.0; hn=np.sqrt(hx*hx+hy*hy+hz*hz); hx=hx/hn; hy=hy/hn; hz=hz/hn
    NdotH=np.clip(NX*hx+NY*hy+NZ*hz,0,1); VdotH=np.clip(hz,0,1)
    NdotV=np.clip(NZ,1e-3,1.0); NdotL=np.clip(diff,1e-3,1.0)
    a2=ROUGH*ROUGH
    D=a2/(math.pi*((NdotH*NdotH*(a2-1.0)+1.0)**2)+1e-7)         # GGX normal distribution
    F=0.03+0.97*(1.0-VdotH)**5                                  # Fresnel, water F0~0.03
    kk=a2*0.5; G=(NdotV/(NdotV*(1-kk)+kk))*(NdotL/(NdotL*(1-kk)+kk))  # Smith geometry
    glint=np.clip(D*F*G/(4.0*NdotV),0,14.0)*wat*(1-cd)*sm(-0.01,0.12,diff)
    surf=surf+(glint*GSTR)[...,None]*np.array([1.0,0.96,0.88])
    # clouds (lit by sun; dark at night -> obscure lights)
    ca_=(cd*CSTR)[...,None]; surf=surf*(1-ca_)+(np.array([0.92,0.94,0.97])*(AMB+sun)[...,None])*ca_
    # atmosphere: inner blue limb (day-weighted) + subtle warm terminator
    rim=sm(0.62,1.0,R2)*(0.2+0.8*sun)
    surf=surf+rim[...,None]*np.array([0.05,0.13,0.32])
    term=np.exp(-((diff/(0.07+TWI*0.5))**2))*sm(0.5,1.0,R2)   # warm band widens with the twilight
    surf=surf+(term*0.10)[...,None]*np.array([0.55,0.32,0.14])
    # --- NZ marker: AA + composited here so motion blur & downscale smooth it ---
    r1x=Wnz[0]*ca-Wnz[1]*sa; r1y=Wnz[0]*sa+Wnz[1]*ca; r1z=Wnz[2]
    Vz=r1y*sb+r1z*cb; fade=float(np.clip((Vz+0.02)/0.14,0,1))
    if fade>0:
        Vx=r1x; Vy=r1y*cb-r1z*sb; mx=cx+Vx*R; my=cy-Vy*R
        dist=np.sqrt((xx-mx)**2+(yy-my)**2)
        coreR=3.0*SS; ringR=7.5*SS
        core=sm(coreR+1.0*SS,coreR-0.8*SS,dist)
        ring=np.exp(-((dist-ringR)/(1.2*SS))**2)*0.8
        mA=np.clip(np.maximum(core,ring)*fade,0,1)*DISC
        mC=(MCORE*core[...,None]+MRING*(ring*(1-core))[...,None])*fade*DISC[...,None]
        surf=surf*(1-mA[...,None])+mC
    # linear -> sRGB
    col=np.clip(surf,0,1)**(1/GAMMA)*255
    # alpha + day-tinted outer atmosphere glow
    alpha=DISC.copy()
    gl=math.hypot(Lvx,Lvy)+1e-6; gdx,gdy=Lvx/gl,Lvy/gl
    dayfac=np.clip(0.5+0.5*((NX/(RR+1e-6))*gdx+(NY/(RR+1e-6))*gdy),0,1)
    alpha=np.maximum(alpha,(GLOW**1.7)*0.42*(0.3+0.7*dayfac)*(RR>1.0))
    gcol=np.array([60.,120,225])*(0.5+0.5*dayfac[...,None])
    col=np.where(OUTER[...,None],col*(1-GLOW[...,None])+gcol*GLOW[...,None],col)
    return col,alpha

# ---- window chrome: a raster twin of panels.window() so the globe matches the SVG panels when shown at width=300 ----
FRAME=os.environ.get("FRAME","1")=="1"
TITLE=os.environ.get("TITLE","earth.avif")
K=W/(300.0*900/820)                     # raster px per SVG-viewBox px (SVG panels: 900 viewBox shown at 820; globe shown at 300)
TBH=int(round(34*K)) if FRAME else 0    # title strip height
FOOT=[l.strip() for l in os.environ.get("FOOT","rendered hourly for live lighting").split("|") if l.strip()]
# footer caption sits just under the disc (inside the globe square, over the faint halo margin); the band below only
# has to hold the gap under the last line.  FOOT_Y = centre of line 0.
FOOT_Y=int(round(34*K + 0.9*W + 36*K))                                      # title strip + disc bottom (0.5W+0.4W) + 36px
FBH=max(0, int(round(FOOT_Y + 30*K*(len(FOOT)-1) + 17*K)) - int(round(34*K)) - W) if (FRAME and FOOT) else 0
def chrome():
    s=4; Wc,Hc=W*s,(W+TBH+FBH)*s; k=K*s
    im=Image.new("RGBA",(Wc,Hc),(0,0,0,0)); dr=ImageDraw.Draw(im)
    body=[k,k,Wc-k-1,Hc-k-1]; rx=12*k
    dr.rounded_rectangle(body, radius=rx, fill=(13,17,23,255))                     # BG  #0d1117
    dr.rounded_rectangle([k,k,Wc-k-1,34*k], radius=rx, fill=(1,4,9,255))            # PANEL #010409 title strip
    dr.rectangle([k,20*k,Wc-k-1,34*k], fill=(1,4,9,255))                            # square off its bottom corners
    dr.rounded_rectangle(body, radius=rx, outline=(48,54,61,255), width=max(1,int(round(k))))   # BORDER #30363d
    for i,c in enumerate([(255,95,86),(255,189,46),(39,201,63)]):
        cxp,cyp,r=(22+20*i)*k,18*k,6*k
        dr.ellipse([cxp-r,cyp-r,cxp+r,cyp+r], fill=c+(255,))
    im=im.resize((W,W+TBH+FBH),Image.LANCZOS)
    fp=os.path.join(os.path.dirname(os.path.abspath(__file__)),"mono.ttf")
    def fnt(px):
        try: return ImageFont.truetype(fp, int(round(px)))
        except Exception: return ImageFont.load_default(int(round(px)))
    dr=ImageDraw.Draw(im)
    dr.text((W/2.0, 18*K), TITLE, font=fnt(13*K), fill=(110,118,129,255), anchor="mm")   # DIM #6e7681 (13px at README scale, like the SVG panels)
    for i,line in enumerate(FOOT):                                                       # caption line(s) in the footer band, same size as the title
        dr.text((W/2.0, FOOT_Y+30*i*K), line, font=fnt(15*K), fill=(110,118,129,255), anchor="mm")
    return im
CHROME=chrome() if FRAME else None
ALPHA=CHROME.getchannel("A") if FRAME else None     # the only transparency is the static rounded corners

def frame(i):
    a0=2*math.pi*i/N; step=2*math.pi/N
    acc=np.zeros((Sp,Sp,3)); aacc=np.zeros((Sp,Sp))
    for m in range(MB):
        a=a0+step*(m/MB) if MB>1 else a0
        col,al=subframe(a); acc+=col*al[...,None]; aacc+=al
    rgb=acc/np.maximum(aacc[...,None],1e-6); al=aacc/MB
    im=Image.fromarray(np.dstack([np.clip(rgb,0,255),al*255]).astype(np.uint8),"RGBA").resize((W,W),Image.LANCZOS)
    arr=np.asarray(im).astype(np.float32); arr[...,:3]=np.clip(arr[...,:3]+DITH,0,255)   # dither
    im=Image.fromarray(arr.astype(np.uint8),"RGBA")
    if FRAME:                                   # globe (with its soft halo) over the opaque window body, below the title strip
        canvas=CHROME.copy(); canvas.alpha_composite(im,(0,TBH)); im=canvas.convert("RGB")   # RGB in memory (25% smaller); alpha re-attached at save
    return im
def with_alpha(f):
    if not FRAME: return f
    x=f.convert("RGBA"); x.putalpha(ALPHA); return x

import time;t0=time.time()
OUT=os.environ.get("OUT","globe_earth.avif"); EXTRA=os.environ.get("EXTRA","1")=="1"
print("rendering",N,"frames x",MB,"MB ...")
frames=[frame(i) for i in range(N)]
print(f"render {time.time()-t0:.0f}s")
dur=max(1,int(DUR*1000/N))
tmp=OUT+".tmp"
first=with_alpha(frames[0])
try:    first.save(tmp,format="AVIF",save_all=True,append_images=(with_alpha(f) for f in frames[1:]),duration=dur,loop=0,quality=Q)   # lazy: one RGBA frame at a time
except TypeError:
        first.save(tmp,format="AVIF",save_all=True,append_images=[with_alpha(f) for f in frames[1:]],duration=dur,loop=0,quality=Q)
os.replace(tmp,OUT)   # atomic swap so the web server never serves a half-written file
print(f"avif {round(os.path.getsize(OUT)/1024)} kB -> {OUT} | total {time.time()-t0:.0f}s")
if EXTRA:
    with_alpha(frames[0]).save("frame_a.png"); with_alpha(frames[N//3]).save("frame_b.png"); with_alpha(frames[2*N//3]).save("frame_c.png")
    with_alpha(frames[0]).save("globe_earth.webp",save_all=True,append_images=[with_alpha(f) for f in frames[1:]],duration=dur,loop=0,quality=64,method=4,exact=True,disposal=2)
    print("webp",round(os.path.getsize('globe_earth.webp')/1024),"kB")
