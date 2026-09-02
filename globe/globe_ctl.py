#!/usr/bin/env python3
"""Globe service orchestrator (runs inside the Docker container).
- Adaptive slot set: hourly near NZ dawn/dusk (|sun elevation|<15 deg), every 2h otherwise (self-adjusts by date).
- loop: keep the currently-needed slot rendered, swap it to the web path, and slowly regen the most-stale slot.
Paths: /app = code+textures (bind mount), /app/hours = rendered slots, /web/globe.avif = exposed file.
Subcommands: slots | swap | regen | render <hour> | loop  (default loop)."""
import os, sys, math, time, glob, subprocess, datetime, shutil

APP="/app"; HRS=os.path.join(APP,"hours"); WEB="/web/globe.avif"
os.makedirs(HRS, exist_ok=True)
NZ_LAT, NZ_LON = math.radians(-41.0), math.radians(174.0)
SETTINGS = dict(N="1080", MB="1", SS="2", Wpx="440", Q="56", EXTRA="0")
REGEN_EVERY = float(os.environ.get("REGEN_HOURS","3"))*3600
DAWN_DUSK_DEG = 15.0

def log(m): print(f"[{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC] {m}", flush=True)
def decl(now): d=now.timetuple().tm_yday; return math.radians(23.44)*math.sin(2*math.pi*(d-81)/365.24)
def nz_elev(h,d):
    lam=math.radians(15.0*(12.0-h))
    S=(math.cos(d)*math.cos(lam),math.cos(d)*math.sin(lam),math.sin(d))
    N=(math.cos(NZ_LAT)*math.cos(NZ_LON),math.cos(NZ_LAT)*math.sin(NZ_LON),math.sin(NZ_LAT))
    return math.degrees(math.asin(max(-1,min(1,sum(a*b for a,b in zip(S,N))))))
def slots(now):
    d=decl(now); return sorted({h for h in range(24) if abs(nz_elev(h,d))<DAWN_DUSK_DEG or h%2==0})
def slot_file(h): return os.path.join(HRS, f"globe_{h:02d}.avif")
def nearest(now, hrs):
    f=now.hour+now.minute/60.0
    return min(hrs, key=lambda h: min((f-h)%24,(h-f)%24))

def render(h):
    env=dict(os.environ); env.update(SETTINGS); env["HOUR"]=str(h); env["OUT"]=slot_file(h)
    for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS","VECLIB_MAXIMUM_THREADS"): env[k]="2"
    log(f"render slot {h:02d} ..."); t=time.time()
    r=subprocess.run(["nice","-n","19","python",os.path.join(APP,"build_earth.py")],
                     env=env, cwd=APP, capture_output=True, text=True)
    ok=r.returncode==0 and os.path.exists(slot_file(h))
    log(f"  slot {h:02d} {'done' if ok else 'FAILED'} in {int(time.time()-t)}s"
        + (f" ({os.path.getsize(slot_file(h))//1024}kB)" if ok else f" rc={r.returncode}: {(r.stderr or '')[-180:]}"))
    return ok

def rendered_hours():
    return sorted(int(os.path.basename(f)[6:8]) for f in glob.glob(os.path.join(HRS,"globe_*.avif")))

def swap(now):
    avail=rendered_hours()
    if not avail: log("swap: nothing rendered yet"); return
    h=nearest(now, avail); tmp=WEB+".tmp"
    shutil.copyfile(slot_file(h), tmp); os.replace(tmp, WEB)
    log(f"swap -> slot {h:02d}  (now {now:%H:%M} UTC)")

def most_stale(sl):
    missing=[h for h in sl if not os.path.exists(slot_file(h))]
    if missing: return missing[0]
    return min(sl, key=lambda h: os.path.getmtime(slot_file(h)))

def loop():
    log(f"loop start; today's slots = {slots(datetime.datetime.now(datetime.timezone.utc))}")
    last=0.0
    while True:
        now=datetime.datetime.now(datetime.timezone.utc); sl=slots(now); cur=nearest(now, sl)
        f=now.hour+now.minute/60.0
        missing=sorted((h for h in sl if not os.path.exists(slot_file(h))), key=lambda h: min((f-h)%24,(h-f)%24))
        if not os.path.exists(slot_file(cur)):      # currently-needed slot first
            render(cur)
        elif missing:                                # refill an incomplete set back-to-back, nearest hours first
            render(missing[0])                       # (e.g. after a renderer change wiped the old slots)
        elif time.time()-last>=REGEN_EVERY:          # else slowly refresh the stalest
            render(most_stale(sl)); last=time.time()
        swap(now)
        time.sleep(60 if missing else 1200)          # 20 min when the set is complete

if __name__=="__main__":
    cmd=sys.argv[1] if len(sys.argv)>1 else "loop"
    now=datetime.datetime.now(datetime.timezone.utc)
    if   cmd=="slots":  print(slots(now))
    elif cmd=="swap":   swap(now)
    elif cmd=="regen":  render(most_stale(slots(now)))
    elif cmd=="render": render(int(sys.argv[2]))
    else:               loop()
