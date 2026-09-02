#!/usr/bin/env python3
"""Live panels orchestrator (runs in the panels-service container).
Every LOOP seconds: pull Last.fm now-playing (+ album art, + my top artist this week), GitHub's
latest push (for the card's "Currently" row), compute state, and render card.svg / music.svg /
pet.svg (v1) plus blip.json (sleepy / bob / favourite — consumed by the Cloudflare Worker that draws
the clickable Blip panel; Blip's level and mood come from visitor clicks, not from here) atomically into /web. Every fetch degrades to the last known-good value
(state.json) so a network blip never blanks a panel.
Optional files next to this script (re-read every tick, no restart needed):
  lastfm.json    {"user": ..., "key": ...}
  languages.json {"languages", "other", "dabbling": [...], "system", "hobbies", "contact": {...}}   the card's content
Subcommands: once | loop (default loop)."""
import os, sys, re, json, time, base64, datetime, html as htmlmod, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panels

APP=os.path.dirname(os.path.abspath(__file__))
WEB=os.environ.get("WEB","/web")
STATE=os.path.join(APP,"state.json")
GH_USER=os.environ.get("GH_USER","aw-snap")
BIRTH=datetime.date(2026,8,31)                 # the creature's hatch day (v1 pet panel)
LOOP=int(os.environ.get("LOOP","60"))
UA={"User-Agent":"awsnap-panels/1.0 (+https://github.com/aw-snap)"}
LASTFM_PLACEHOLDER="2a96cbd8b46e442fc41c2b86b821562f"   # Last.fm's "no cover" image hash
DEFAULT_LANGS={"languages":["Python","JavaScript","C++","C"],
               "dabbling":["Lua","GLSL","TypeScript","Prolog","Lean","Nix"]}

def log(m): print(f"[{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {m}", flush=True)
def load_state():
    try: return json.load(open(STATE))
    except Exception: return {}
def save_state(s):
    try: json.dump(s, open(STATE+".tmp","w")); os.replace(STATE+".tmp", STATE)
    except Exception as e: log(f"state save failed: {e}")
def getjson(url, timeout=10, headers=None):
    h=dict(UA); h.update(headers or {})
    req=urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)
def readjson(name, default=None):
    try: return json.load(open(os.path.join(APP,name)))
    except Exception: return default

def lastfm_cfg():
    c=readjson("lastfm.json")
    if c: return c.get("user"), c.get("key")
    return os.environ.get("LASTFM_USER"), os.environ.get("LASTFM_KEY")

def ago(secs):
    if secs<60: return "just now"
    if secs<3600: return f"{int(secs//60)} min ago"
    if secs<86400: return f"{int(secs//3600)}h ago"
    return f"{int(secs//86400)}d ago"

def art_lookup(artist, title, lastfm_url):
    """Find a real cover for the track: Deezer (exact artist+track search) -> iTunes -> Last.fm's own image."""
    a=artist.replace('"',""); t=title.replace('"',"")
    try:
        q=urllib.parse.urlencode(dict(q=f'artist:"{a}" track:"{t}"', limit=3))
        for r in getjson("https://api.deezer.com/search?"+q, timeout=8).get("data",[]):
            u=(r.get("album") or {}).get("cover_medium")
            if u: return u, "deezer"
    except Exception as e: log(f"deezer fail: {e}")
    try:
        q=urllib.parse.urlencode(dict(term=f"{a} {t}", entity="song", limit=5))
        rs=getjson("https://itunes.apple.com/search?"+q, timeout=8).get("results",[]); tl=t.lower()
        hit=(next((x for x in rs if x.get("trackName","").lower()==tl), None)
             or next((x for x in rs if tl in x.get("trackName","").lower()), None) or (rs[0] if rs else None))
        if hit and hit.get("artworkUrl100"): return hit["artworkUrl100"].replace("100x100bb","200x200bb"), "itunes"
    except Exception as e: log(f"itunes fail: {e}")
    return (lastfm_url, "lastfm") if lastfm_url else ("", "")

def fetch_art(st, artist, title, lastfm_url):
    """Resolve + download the cover once per track (cached in state, negative results retried hourly);
    returns a data URI or ''."""
    if not title: return ""
    key=f"{artist}\x1f{title}".lower(); art=st.get("art",{})
    if art.get("key")!=key or (not art.get("b64") and time.time()-art.get("ts",0)>3600):
        art={"key":key,"ts":time.time(),"b64":"","src":""}
        url,src=art_lookup(artist, title, lastfm_url)
        if url:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8) as r: data=r.read()
                if 0<len(data)<400_000:
                    art.update(url=url, src=src, mime=("image/png" if data[:4]==b"\x89PNG" else "image/jpeg"),
                               b64=base64.b64encode(data).decode())
                    log(f"cover for {title} — {artist}: {src} ({len(data)//1024} kB)")
            except Exception as e: log(f"art download fail ({src}): {e}")
        st["art"]=art
    return f"data:{art['mime']};base64,{art['b64']}" if art.get("b64") else ""

def fetch_lastfm(st):
    user,key=lastfm_cfg()
    if not user or not key:
        return {"now_playing":"— set up Last.fm —","np_icon":"■","np_color":panels.DIM,"status":"— set up Last.fm —"}
    try:
        q=urllib.parse.urlencode(dict(method="user.getrecenttracks",user=user,api_key=key,format="json",limit=1))
        d=getjson("https://ws.audioscrobbler.com/2.0/?"+q, timeout=8)
        t=d["recenttracks"]["track"]
        if isinstance(t,list):
            if not t:            # valid account, but nothing scrobbled yet
                r={"now_playing":"nothing scrobbled yet","np_icon":"♪","np_color":panels.DIM,"status":"nothing scrobbled yet"}
                st["lastfm"]=r; return r
            t=t[0]
        artist=t["artist"].get("#text") or t["artist"].get("name","")
        name=t.get("name",""); album=(t.get("album") or {}).get("#text","")
        nowp=str(t.get("@attr",{}).get("nowplaying","")).lower()=="true"
        uts=int((t.get("date") or {}).get("uts") or 0)
        imgs={i.get("size"):i.get("#text","") for i in t.get("image",[])}
        art_url=imgs.get("large") or imgs.get("extralarge") or imgs.get("medium") or ""
        if LASTFM_PLACEHOLDER in art_url: art_url=""
        pre="" if nowp else "last · "
        room=42-len(pre); n2=name; a2=artist
        if len(n2)>room-6: n2=n2[:room-7]+"…"
        if a2 and len(n2)+3+len(a2)>room: a2=a2[:max(0,room-len(n2)-4)]+"…"
        r={"now_playing":pre+n2+(" — "+a2 if a2 else ""),"np_prefix":pre,"np_title":n2,"np_artist":a2,
           "np_icon":"▶" if nowp else "♪","np_color":panels.PUR if nowp else panels.TXT,
           "title":name,"artist":artist,"album":album,"playing":nowp,"uts":uts,"art_url":art_url}
        st["lastfm"]=r; return r
    except Exception as e:
        log(f"lastfm fail: {e}")
        return st.get("lastfm", {"now_playing":"— offline —","np_icon":"■","np_color":panels.DIM,"status":"— offline —"})

def fetch_top_artist(st):
    """Blip's 'favourite' = my most-played artist this week (Last.fm), refreshed hourly; keeps the last value on failure."""
    user,key=lastfm_cfg(); now=time.time()
    if not user or not key or now-st.get("_fav_ts",0)<3600: return st.get("fav","")
    try:
        q=urllib.parse.urlencode(dict(method="user.gettopartists",user=user,api_key=key,format="json",period="7day",limit=1))
        a=getjson("https://ws.audioscrobbler.com/2.0/?"+q, timeout=8)["topartists"]["artist"]
        a=a[0] if isinstance(a,list) and a else (a if isinstance(a,dict) else {})
        st["fav"]=a.get("name",""); st["_fav_ts"]=now
    except Exception as e:
        log(f"lastfm top artist fail: {e}"); st["_fav_ts"]=now-3000        # retry in 10 min
    return st.get("fav","")

def fetch_calendar(g, now):
    """Public contributions calendar (no auth): per-day contribution counts for the last ~3 weeks."""
    if now-g.get("_cal_ts",0)<1200: return
    try:
        req=urllib.request.Request(f"https://github.com/users/{GH_USER}/contributions", headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r: page=r.read().decode("utf-8","replace")
        ids={}
        for m in re.finditer(r"<td\b[^>]*>", page):
            tag=m.group(0); dm=re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag); im=re.search(r'\bid="([^"]+)"', tag)
            if dm and im: ids[im.group(1)]=dm.group(1)
        days={}
        for m in re.finditer(r"<tool-tip\b[^>]*\bfor=\"([^\"]+)\"[^>]*>([^<]*)</tool-tip>", page):
            dte=ids.get(m.group(1))
            if not dte: continue
            txt=htmlmod.unescape(m.group(2)).strip()
            mm=re.match(r"(\d[\d,]*)", txt)
            days[dte]=0 if txt.startswith("No ") or not mm else int(mm.group(1).replace(",",""))
        if days:
            keep=sorted(days)[-28:]
            g["cal"]={k:days[k] for k in keep}; g["_cal_ts"]=now
    except Exception as e:
        log(f"calendar fail: {e}")

def fetch_github(st):
    now=time.time(); g=st.get("gh",{})
    try:
        if now-g.get("_events_ts",0)>300:                # latest PushEvent (repo + when)
            ev=getjson(f"https://api.github.com/users/{GH_USER}/events/public")
            push=next((e for e in ev if e.get("type")=="PushEvent"), None)
            if push:
                g["last_repo"]=push["repo"]["name"].split("/")[-1]
                g["last_push_iso"]=push.get("created_at")
            g["_events_ts"]=now
    except Exception as e:
        log(f"github events fail: {e}")
    st["gh"]=g
    return g

def days_since(iso):
    if not iso: return None
    try:
        dt=datetime.datetime.strptime(iso,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc)-dt).total_seconds()/86400
    except Exception: return None

def host_uptime():                       # awsnap-public real uptime (/proc is the host's, visible from the container)
    try:
        with open("/proc/uptime") as f: secs=float(f.read().split()[0])
    except Exception: return "—"
    dys=int(secs//86400); hrs=int(secs%86400//3600); mins=int(secs%3600//60)
    parts=[]
    if dys: parts.append(f"{dys} day"+("" if dys==1 else "s"))
    if hrs: parts.append(f"{hrs} hour"+("" if hrs==1 else "s"))
    if mins and not dys: parts.append(f"{mins} min"+("" if mins==1 else "s"))
    return ", ".join(parts) if parts else "just booted"

def build(st):
    utc=datetime.datetime.now(datetime.timezone.utc)
    loc,ab=panels.nz_now(utc); elev=panels.nz_sun_elev(utc)
    lf=fetch_lastfm(st); gh=fetch_github(st)
    langs=readjson("languages.json") or DEFAULT_LANGS
    # ---- card ----
    repo=gh.get("last_repo",""); dpush=days_since(gh.get("last_push_iso"))
    card=dict(uptime=host_uptime(), local=f"{loc:%H:%M} {ab}",
              currently=(f"hacking on {repo}" if repo else "dabbling"), profile=langs,
              langs=langs.get("languages",[]), dabbling=langs.get("dabbling",[]),
              now_playing=lf["now_playing"], np_icon=lf["np_icon"], np_color=lf["np_color"],
              np_prefix=lf.get("np_prefix",""), np_title=lf.get("np_title",""), np_artist=lf.get("np_artist",""))
    # ---- music ----
    music=dict(title=lf.get("title",""), artist=lf.get("artist",""), album=lf.get("album",""),
               playing=bool(lf.get("playing")), status=lf.get("status") or lf.get("now_playing",""),
               when=ago(max(0,time.time()-lf["uts"])) if lf.get("uts") else "",
               art=fetch_art(st, lf.get("artist",""), lf.get("title",""), lf.get("art_url","")))
    # ---- blip (v4: the Worker owns level/mood/counters; we only say whether it's night in NZ + the favourite) ----
    sleepy=elev<-6
    blip=dict(sleepy=sleepy, bob=3.6 if sleepy else 2.4, fav=fetch_top_artist(st),
              local=f"{loc:%H:%M} {ab}", updated=int(time.time()))
    # ---- pet v1 (old README; its level still comes from the seeded commit count) ----
    level=max(1, int(gh.get("commits",0))//150)
    age_days=(loc.date()-BIRTH).days
    age_pct=(age_days%15)/15.0; age_note=f"{age_days} days"
    d=dpush if dpush is not None else 6.0
    hunger_pct=min(1.0, d/10.0)
    if d<1: hunger_note="just fed! full :3"; hunger_col=panels.GREEN
    elif d<3: hunger_note=f"{round(d)}d · content"; hunger_col=panels.CYAN
    elif d<7: hunger_note=f"{round(d)}d · getting peckish"; hunger_col=panels.ORANGE
    else: hunger_note=f"{round(d)}d · starving!"; hunger_col=panels.RED
    energy_pct=max(0.05,min(1.0,(elev+8)/46.0))
    if elev>3: energy_note="awake ☀ NZ day"
    elif elev>-6: energy_note=("waking · dusk" if 6<=loc.hour<12 else "fading · dusk")
    else: energy_note="sleepy ☾ NZ night"
    last_fed = "just fed :3 ("+repo+")" if d<1 else f"last fed {round(d)}d ago ({repo})"
    pet=dict(level=level, bob=blip["bob"], face=panels.CAT, face_blink=panels.CAT_BLINK, face_col="#8292a1",
             age_pct=age_pct, age_note=age_note, hunger_pct=hunger_pct, hunger_col=hunger_col, hunger_note=hunger_note,
             energy_pct=energy_pct, energy_note=energy_note, last_fed=last_fed)
    return card, music, blip, pet

def write_atomic(name, data):
    p=os.path.join(WEB,name); tmp=p+".tmp"
    open(tmp,"w").write(data); os.replace(tmp,p)

def once():
    st=load_state()
    card,music,blip,pet=build(st)
    # ---- shooting stars (spike): languages.json {"stars": true} turns the shared sky on; absent/false = off ----
    prof=card.get("profile") or {}                           # = languages.json as read this tick
    if prof.get("stars"):
        import re
        lag=prof.get("stars_lag") or {}                      # per-window begin offsets (s) to absorb typical load skew
        plain=panels.card_svg(card)                          # first pass only to learn the card's height
        card_h=int(re.search(r'height="(\d+)"', plain).group(1))
        win,sky_h=panels.sky_layout(card_h)
        stars=panels.make_stars(int(time.time()//600), sky_h) # a new burst every 10 min, same one in every window
        card_stars=panels.star_layer(stars, win["card"], lag.get("card",0))
        music_stars=panels.star_layer(stars, win["music"], lag.get("music",0))
        blip["stars"]=dict(list=stars, blip=win["blip"], btn=win["btn"],
                           lag=dict(blip=lag.get("blip",0), btn=lag.get("btn",0)))
    else:
        card_stars=music_stars=None
    write_atomic("card.svg",  panels.card_svg(card, card_stars))
    write_atomic("music.svg", panels.music_svg(music, music_stars))
    write_atomic("blip.json", json.dumps(blip))
    write_atomic("pet.svg",   panels.pet_svg(pet))
    save_state(st)
    log(f"wrote card/music/pet.svg + blip.json | Now {card['np_icon']} {card['now_playing']} | fav {blip['fav']!r} sleepy={blip['sleepy']} | {card['currently']} | local {card['local']}")

def loop():
    log(f"panels loop start; user={GH_USER} loop={LOOP}s web={WEB}")
    while True:
        try: once()
        except Exception as e: log(f"tick error: {e}")
        time.sleep(LOOP)

if __name__=="__main__":
    (loop if (len(sys.argv)<2 or sys.argv[1]=="loop") else once)()
