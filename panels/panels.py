#!/usr/bin/env python3
"""Live README panels as self-contained SVGs (pure stdlib, no deps).
- card_svg(d):  tequin@awsnap fastfetch card (hand-picked languages from languages.json).
- music_svg(d): "now playing" panel with Last.fm album art embedded as a data URI.
- pet_svg(d):   v1 Dabble Creature panel — still generated for the old README (reversibility);
                the live Blip panel is rendered by the Cloudflare Worker from blip.json.
Every panel sits inside the same window chrome (window(): rounded panel, title strip,
three traffic-light dots) so the README reads as a stack of terminal windows.
Deterministic given input; all network/state lives in panels_ctl.py.
NZ time (NZST/NZDT) and sun elevation computed here so glyphs/day-night stay honest."""
import html, math, datetime

FONT = "'JetBrains Mono','Fira Code','SF Mono',ui-monospace,Menlo,Consolas,monospace"
BG="#0d1117"; PANEL="#010409"; BORDER="#30363d"
GREEN="#3fb950"; CYAN="#39d0d8"; TXT="#c9d1d9"; DIM="#6e7681"
YEL="#d29922"; RED="#f85149"; PUR="#bc8cff"; ORANGE="#db6d28"; PINK="#f778ba"
LEADER="#2b3038"                                # dotted-leader / faint rule colour
TB=34                                            # titlebar height (window chrome)

# GitHub linguist colours (a few lightened so they read on the dark panel)
LANG_COLORS={"Python":"#3572A5","JavaScript":"#f1e05a","C++":"#f34b7d","C":"#9a9a9a","HTML":"#e34c26",
             "Lua":"#4f6bd6","GLSL":"#5686a5","TypeScript":"#3178c6","Prolog":"#c74a70","Hack":"#878787",
             "PHP":"#4F5D95","QML":"#44a51c","Jasmin":"#d03600","Lean":"#a38df5","PureBasic":"#5a6986",
             "Nix":"#7e7eff","Rust":"#dea584","Shell":"#89e051","CSS":"#663399","Java":"#b07219",
             "C#":"#7355dd","Go":"#00ADD8","Zig":"#ec915c","Haskell":"#5e5086","Kotlin":"#A97BFF",
             "Swift":"#F05138","Dart":"#00B4AB","Ruby":"#701516","Elixir":"#6e4a7e","OCaml":"#ef7a08",
             "Assembly":"#6E4C13","Godot":"#355570","GDScript":"#355570","Vim Script":"#199f4b","Markdown":"#8ab4f8"}
def lang_color(name): return LANG_COLORS.get(name, DIM)

# creature ASCII cat (verbatim from script.js L5-L10; preserve leading/trailing spaces exactly)
CAT       = "    ╱|、   \n  (˚ˎ 。7  \n   |、˜〵  \n  じしˍ,)ノ"
CAT_BLINK = "    ╱|、   \n  (-ˎ 。7  \n   |、˜〵  \n  じしˍ,)ノ"
CAT_FONT  = "'Roboto',sans-serif"          # cat's OWN proportional font (script.js:14) — NOT the monospace FONT

def esc(s): return html.escape(str(s), quote=True)
def tspan(t, fill, x=None, dy=None, extra=""):
    a=f' fill="{fill}"'
    if x is not None: a+=f' x="{x}"'
    if dy is not None: a+=f' dy="{dy}"'
    return f'<tspan{a}{extra}>{esc(t)}</tspan>'
def cut(s, n): s=str(s or ""); return s if len(s)<=n else s[:n-1]+"…"

def window(W, H, title):
    """Shared window chrome (same geometry in every panel, incl. the cookie Worker's JS port):
    rounded #0d1117 panel with a #30363d border, a darker 34px title strip whose bottom corners are
    squared off, three traffic-light dots at x=22/42/62, and a dim centred monospace title."""
    P=[f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="12" fill="{BG}" stroke="{BORDER}"/>',
       f'<rect x="1" y="1" width="{W-2}" height="{TB}" rx="12" fill="{PANEL}"/>',
       f'<rect x="1" y="20" width="{W-2}" height="{TB-19}" fill="{PANEL}"/>']
    for i,c in enumerate(["#ff5f56","#ffbd2e","#27c93f"]):
        P.append(f'<circle cx="{22+i*20}" cy="18" r="6" fill="{c}"/>')
    P.append(f'<text x="{W/2}" y="23" font-family="{FONT}" font-size="13" fill="{DIM}" text-anchor="middle">{esc(title)}</text>')
    return P

def svg(W, H, parts):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{FONT}">{"".join(parts)}</svg>')

# ---------------- NZ time + sun (no tzdata dependency) ----------------
NZ_LAT, NZ_LON = math.radians(-41.0), math.radians(174.0)
def _nth_sunday(year, month, n):     # n=1 first, n=-1 last
    if n>0:
        d=datetime.date(year,month,1); d+=datetime.timedelta((6-d.weekday())%7); return d+datetime.timedelta(7*(n-1))
    nm=datetime.date(year+(month==12), (month%12)+1, 1); d=nm-datetime.timedelta(1)
    return d-datetime.timedelta((d.weekday()-6)%7)
def nz_offset(utc):                  # -> (hours, "NZST"/"NZDT")
    y=utc.year
    start=datetime.datetime(y,9,_nth_sunday(y,9,-1).day,2,0,tzinfo=datetime.timezone.utc)-datetime.timedelta(hours=12)  # 02:00 NZST
    end  =datetime.datetime(y,4,_nth_sunday(y,4,1).day,3,0,tzinfo=datetime.timezone.utc)-datetime.timedelta(hours=13)   # 03:00 NZDT
    return (13,"NZDT") if (utc>=start or utc<end) else (12,"NZST")
def nz_now(utc=None):
    utc=utc or datetime.datetime.now(datetime.timezone.utc)
    off,ab=nz_offset(utc); loc=utc+datetime.timedelta(hours=off)
    return loc, ab
def nz_sun_elev(utc=None):           # solar elevation at NZ, degrees
    utc=utc or datetime.datetime.now(datetime.timezone.utc)
    doy=utc.timetuple().tm_yday; decl=math.radians(23.44)*math.sin(2*math.pi*(doy-81)/365.24)
    frac=utc.hour+utc.minute/60+utc.second/3600; lam=math.radians(15.0*(12.0-frac))
    S=(math.cos(decl)*math.cos(lam),math.cos(decl)*math.sin(lam),math.sin(decl))
    Nv=(math.cos(NZ_LAT)*math.cos(NZ_LON),math.cos(NZ_LAT)*math.sin(NZ_LON),math.sin(NZ_LAT))
    return math.degrees(math.asin(max(-1,min(1,sum(a*b for a,b in zip(S,Nv))))))

# =====================================================================
# PROTOTYPE 1 — tequin@awsnap fastfetch card
# =====================================================================

# =====================================================================
# SHOOTING STARS (spike, 2026-09-03) — one shared "sky" drawn through every window
# ---------------------------------------------------------------------
# The sky is the README's image stack in *displayed* pixels: origin at the card's top-left, 820 wide, the
# windows stacked with GitHub's paragraph gaps. Every window draws the same star list, offset by where it
# sits in the sky and scaled by its own viewBox/display ratio, so a star leaving one window enters the next
# on the same line. Off by default: languages.json {"stars": true} turns it on; the Worker gets its copy
# through blip.json and draws nothing when the key is absent.
# =====================================================================
SKY_W=820; SKY_GAP=20; SKY_BR=5                     # displayed width, gap between <p> images, <br/> gap
def sky_layout(card_h_vb, music_h_vb=TB+150, blip_h_vb=TB+230, btn_vb=(280,60), btn_disp=260):
    """Where every window sits in the sky -> {name:(ox,oy,k)}: ox/oy = window top-left in sky px,
    k = viewBox units per displayed px. Also the sky height."""
    k=900/SKY_W; kb=btn_vb[0]/btn_disp
    card_d=card_h_vb/k; music_d=music_h_vb/k; blip_d=blip_h_vb/k; btn_d=btn_vb[1]/kb
    y=0; win={"card":(0,y,k)}; y+=card_d+SKY_GAP
    win["music"]=(0,y,k); y+=music_d+SKY_GAP
    win["blip"]=(0,y,k); y+=blip_d+SKY_BR
    space=4.4                                       # one 16px-font space between the three buttons
    row_w=3*btn_disp+2*space; bx=(SKY_W-row_w)/2
    win["btn"]=[(bx+i*(btn_disp+space), y, kb) for i in range(3)]
    y+=btn_d
    return win, y

def make_stars(seed, sky_h, n=7):
    """A burst: n near-parallel streaks that cross the whole stack top-right -> bottom-left, staggered over
    ~2.5 s after the image loads. Deterministic per seed so every window agrees on the same sky."""
    import random
    rnd=random.Random(seed); stars=[]; t=0.6
    for i in range(n):
        phi=rnd.uniform(26,38)                      # tilt from straight-down, degrees (all roughly parallel)
        dx,dy=-math.sin(math.radians(phi)), math.cos(math.radians(phi))
        y0=-(70+rnd.uniform(0,90))                  # start above the card
        xc=rnd.uniform(230,SKY_W+60)                # where it crosses the card's top edge
        x0=xc+math.tan(math.radians(phi))*(-y0)
        v=rnd.uniform(650,950)                      # px/s: slow enough that a 0.1 s load skew is a small jump
        T=((sky_h+90)-y0)/(dy*v)
        stars.append(dict(x=round(x0,1), y=round(y0,1), a=round(90+phi,1), dx=round(dx,4), dy=round(dy,4),
                          v=round(v), L=round(rnd.uniform(90,170)), r=round(rnd.uniform(1.4,2.2),1),
                          b=round(t,2), T=round(T,2)))
        t+=rnd.uniform(0.12,0.45)
    return stars

def star_layer(stars, win, lag=0.0, t=None, col="#e8f1ff"):
    """SVG for one window: <g> mapping sky px -> this window's viewBox, one animated streak per star.
    t=None emits the SMIL animation (plays once on load); a number renders the frozen frame at that time
    (used by the local preview renderer only). lag shifts every begin, to absorb a window's typical
    load delay relative to the others."""
    ox,oy,k=win
    out=[f'<g transform="scale({k:.5f}) translate({-ox:.2f},{-oy:.2f})"><defs>']
    for i,s in enumerate(stars):
        out.append(f'<linearGradient id="sk{i}" gradientUnits="userSpaceOnUse" x1="{-s["L"]}" y1="0" x2="0" y2="0">'
                   f'<stop offset="0" stop-color="{col}" stop-opacity="0"/><stop offset="1" stop-color="{col}" stop-opacity="0.95"/></linearGradient>')
    out.append('</defs>')
    for i,s in enumerate(stars):
        x1=s["x"]+s["dx"]*s["v"]*s["T"]; y1=s["y"]+s["dy"]*s["v"]*s["T"]; b=s["b"]+lag
        body=(f'<g transform="rotate({s["a"]})"><line x1="{-s["L"]}" y1="0" x2="0" y2="0" stroke="url(#sk{i})" '
              f'stroke-width="2.2" stroke-linecap="round"/><circle r="{s["r"]*2.6:.1f}" fill="{col}" opacity="0.22"/>'
              f'<circle r="{s["r"]}" fill="#ffffff"/></g>')
        if t is None:
            out.append(f'<g opacity="0"><animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.06;0.9;1" '
                       f'begin="{b:.2f}s" dur="{s["T"]}s" fill="freeze"/>'
                       f'<animateTransform attributeName="transform" type="translate" from="{s["x"]} {s["y"]}" '
                       f'to="{x1:.1f} {y1:.1f}" begin="{b:.2f}s" dur="{s["T"]}s" fill="freeze"/>{body}</g>')
        else:                                        # frozen frame for previews
            u=(t-b)/s["T"]
            if 0<=u<=1:
                op=min(1,u/0.06) if u<0.06 else (1 if u<0.9 else (1-u)/0.1)
                px=s["x"]+s["dx"]*s["v"]*(t-b); py=s["y"]+s["dy"]*s["v"]*(t-b)
                out.append(f'<g opacity="{op:.2f}" transform="translate({px:.1f} {py:.1f})">{body}</g>')
    out.append('</g>')
    return "".join(out)

def card_svg(d, stars=None):
    """Expanded fastfetch card (v4): label left, value right-aligned, a dotted leader between; thin section
    rules for Languages / Hobbies / Contact. Content comes from languages.json (d["profile"]) so it is
    editable without touching code. Both ends of each row are anchored, only the leader flexes."""
    W=900; x=250; fs=15.5; lh=21.5; RIGHT=W-40
    CW=fs*0.6                                       # ~advance of one monospace cell (0.55-0.6em across the fallback fonts)
    pr=d.get("profile") or {}
    sysrows=pr.get("system") or {"OS":"Arch Linux","Host":"conduit","Shell":"bash · PipeWire","WM":"Hyprland","Editor":"Neovim"}
    def chips(names):                               # coloured ● chips -> (svg, width in cells)
        names=[str(n) for n in names]
        if not names: return tspan("—",DIM), 1
        parts=[]
        for i,nm in enumerate(names):
            if i: parts.append(tspan(", ",DIM))
            parts.append(tspan("● ",lang_color(nm))+tspan(nm,TXT))
        return "".join(parts), sum(len(nm)+2 for nm in names)+2*(len(names)-1)
    def row(label, value="", vcol=TXT, chips_=None):
        if chips_ is not None: right,vlen=chips(chips_)
        else: right,vlen=tspan(str(value),vcol),len(str(value))
        return ('r', tspan(label,GREEN)+tspan(":",DIM), right, len(label)+1, vlen)
    # static machine rows first, the two live values last; everything in plain text so the block reads calm
    rows=[row("OS",sysrows.get("OS","Arch Linux")), row("Host",sysrows.get("Host","conduit"))]
    for k in ("Shell","WM","Editor"):                 # optional rows: shown only if present in languages.json
        if sysrows.get(k): rows.append(row(k, sysrows[k]))
    rows+=[row("Local time",d["local"]), row("Server uptime",d["uptime"])]   # uptime is the home box that renders this, not conduit
    langs=[("Languages.Programming", pr.get("languages") or d.get("langs") or []),
           ("Languages.Other",       pr.get("other") or []),
           ("Languages.Dabbling",    pr.get("dabbling") or d.get("dabbling") or [])]
    rows+=[('gap',), ('s',"Languages")]+[row(k, chips_=v) for k,v in langs if v]
    if pr.get("hobbies"): rows+=[('gap',), ('s',"Hobbies")]+[row("Hobbies."+k, v) for k,v in pr["hobbies"].items() if v]
    if pr.get("contact"): rows+=[('gap',), ('s',"Contact")]+[row(k, v, CYAN) for k,v in pr["contact"].items() if v]

    out=[]
    # header exactly like fastfetch: "user@host" over a line of dashes the same length (same font, so they match)
    user="tequin"; host=str(sysrows.get("Host","conduit")); hy=TB+44
    out.append(f'<text x="{x}" y="{hy}" font-family="{FONT}" font-size="{fs}" font-weight="bold" xml:space="preserve">'
               +tspan(user, CYAN)+tspan("@", TXT)+tspan(host, CYAN)+'</text>')
    out.append(f'<text x="{x}" y="{hy+lh}" font-family="{FONT}" font-size="{fs}" fill="{TXT}" xml:space="preserve">{"-"*(len(user)+1+len(host))}</text>')
    cy=hy+2*lh
    for r in rows:
        if r[0]=='gap': cy+=8; continue
        if r[0]=='s':                               # "— Title ───────" section rule
            lx=x+(len(r[1])+3)*CW
            out.append(f'<text x="{x}" y="{cy}" font-family="{FONT}" font-size="{fs}" fill="{GREEN}">{esc("— "+r[1])}</text>'
                       f'<line x1="{lx:.1f}" y1="{cy-5}" x2="{RIGHT}" y2="{cy-5}" stroke="{LEADER}"/>')
            cy+=lh; continue
        _,left,right,llen,vlen=r
        x1=x+(llen+1)*CW; x2=RIGHT-(vlen+1)*CW          # one cell of air each side; the leader is round dots
        out.append(f'<text x="{x}" y="{cy}" font-family="{FONT}" font-size="{fs}" xml:space="preserve">{left}</text>')
        if x2-x1>2*CW:
            out.append(f'<line x1="{x1:.1f}" y1="{cy-4.5}" x2="{x2:.1f}" y2="{cy-4.5}" stroke="{LEADER}" stroke-width="2" '
                       f'stroke-linecap="round" stroke-dasharray="0 5"/>')
        out.append(f'<text x="{RIGHT}" y="{cy}" font-family="{FONT}" font-size="{fs}" text-anchor="end" xml:space="preserve">{right}</text>')
        cy+=lh
    H=int(round(cy-lh+34))
    # ASCII logo drawn as strokes: every / \ _ cell of the art becomes one line segment on a monospace-shaped
    # grid (cell 10.2x17), so the diagonals join into continuous lines in EVERY viewer font — as text, the
    # slashes never met and the logo rendered as broken dashes. Block is centred vertically on the card.
    art=[r"       /\ ",r"      /  \ ",r"     /\   \ ",r"    /  \   \ ",
         r"   /    \   \ ",r"  /  /\  \   \ ",r" /  /  \  \   \ ",r"/__/    \__\___\ "]
    cw,ch=10.2,17.0; n=len(art); x0=34; y0=(TB+H)/2-n*ch/2
    segs=[]
    for r,line in enumerate(art):
        for c,g in enumerate(line):
            gx=x0+c*cw; gy=y0+r*ch
            if   g=='/':  segs.append((gx,gy+ch,gx+cw,gy))
            elif g=='\\': segs.append((gx,gy,gx+cw,gy+ch))
            elif g=='_':  segs.append((gx,gy+ch,gx+cw,gy+ch))
    logo=(f'<g stroke="{GREEN}" stroke-width="1.8" stroke-linecap="round">'
          +"".join(f'<line x1="{a:.1f}" y1="{b:.1f}" x2="{c:.1f}" y2="{e:.1f}"/>' for a,b,c,e in segs)+'</g>')
    P=window(W,H,"fastfetch.svg")+[logo]+out
    if stars: P.append(stars)
    return svg(W,H,P)

# =====================================================================
# MUSIC — now playing / last played, with album art
# =====================================================================
def music_svg(d, stars=None):
    W,H=900,TB+150
    P=window(W,H,"now-playing.svg")
    ax,ay,asz=30,TB+20,110
    P.append(f'<defs><clipPath id="art"><rect x="{ax}" y="{ay}" width="{asz}" height="{asz}" rx="8"/></clipPath></defs>')
    if d.get("art"):
        P.append(f'<image xlink:href="{d["art"]}" href="{d["art"]}" x="{ax}" y="{ay}" width="{asz}" height="{asz}" '
                 f'preserveAspectRatio="xMidYMid slice" clip-path="url(#art)"/>')
    else:   # no cover on Last.fm -> a little record
        cx,cy=ax+asz/2,ay+asz/2
        P.append(f'<rect x="{ax}" y="{ay}" width="{asz}" height="{asz}" rx="8" fill="#161b22"/>')
        P.append(f'<circle cx="{cx}" cy="{cy}" r="46" fill="#0b0e13"/>')
        for r in (40,33,26): P.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1f2630" stroke-width="1"/>')
        P.append(f'<circle cx="{cx}" cy="{cy}" r="15" fill="{PUR}" opacity="0.85"/><circle cx="{cx}" cy="{cy}" r="3" fill="#0b0e13"/>')
    P.append(f'<rect x="{ax}" y="{ay}" width="{asz}" height="{asz}" rx="8" fill="none" stroke="{BORDER}"/>')
    tx=170; playing=bool(d.get("playing"))
    if d.get("title"):
        status=("▶  NOW PLAYING" if playing else f"♪  LAST PLAYED · {d.get('when','')}".rstrip(" ·"))
        P.append(f'<text x="{tx}" y="{TB+46}" font-family="{FONT}" font-size="12" letter-spacing="1" fill="{PUR if playing else DIM}">{esc(status)}</text>')
        P.append(f'<text x="{tx}" y="{TB+82}" font-family="{FONT}" font-size="26" font-weight="bold" fill="{TXT}">{esc(cut(d["title"],32))}</text>')
        P.append(f'<text x="{tx}" y="{TB+108}" font-family="{FONT}" font-size="16" fill="{DIM}">{esc(cut(d.get("artist",""),44))}</text>')
        if d.get("album") and d["album"].strip().lower()!=str(d["title"]).strip().lower(): P.append(f'<text x="{tx}" y="{TB+132}" font-family="{FONT}" font-size="13" fill="{DIM}" opacity="0.8">{esc(cut(d["album"],48))}</text>')
    else:
        P.append(f'<text x="{tx}" y="{TB+82}" font-family="{FONT}" font-size="20" fill="{DIM}">{esc(d.get("status") or "nothing scrobbled yet")}</text>')
    if playing:   # little equaliser, staggered so the bars bounce independently
        bx=W-40-5*14; base=TB+104
        for i,(dur,vals) in enumerate([(0.9,"8;26;12;30;8"),(1.1,"20;8;28;14;20"),(0.8,"12;30;10;24;12"),(1.0,"26;12;30;8;26"),(1.2,"10;22;8;28;10")]):
            ys=";".join(str(base-int(v)) for v in vals.split(";"))
            P.append(f'<rect x="{bx+i*14}" y="{base-8}" width="8" height="8" rx="2" fill="{PUR}">'
                     f'<animate attributeName="height" values="{vals}" dur="{dur}s" repeatCount="indefinite"/>'
                     f'<animate attributeName="y" values="{ys}" dur="{dur}s" repeatCount="indefinite"/></rect>')
    if stars: P.append(stars)
    return svg(W,H,P)

# =====================================================================
# PROTOTYPE 3 (v1) — Dabble Creature panel, kept for the old README
# =====================================================================
def pet_svg(d):
    W,H=900,210+TB
    P=window(W,H,"blip — dabble creature")
    # cat is drawn in its own PROPORTIONAL font — monospace spreads the kaomoji/CJK into fixed cells and wrecks it
    fx=46; y0=TB+58; fs=30.0; lh=fs*1.15       # bigger to fill the panel; cellH = fs * 1.15
    col=d["face_col"]
    # left eye: a subtle version (~20% of the earlier "big eye") — slightly larger, a touch down and right.
    # NB `˚` (U+02DA RING ABOVE) is drawn high above the baseline and scaling pushes it higher, so EYE_DY
    # has to both re-seat it (~4px at this scale) and add the small intended downward nudge.
    EYE="˚"; EYE_SCALE=1.18; EYE_DX=1.0; EYE_DY=8.0
    EYE_TAIL_DX=-1.5                           # pull the glyphs after the eye back so it doesn't spread the face
    def cat_text():                            # cat as one text run; the left eye is split out so only it is resized/offset
        out=[]
        for i,l in enumerate(d["face"].split("\n")):
            dy="0" if i==0 else f"{lh:.2f}"
            if i==1 and EYE in l:
                head,_,tail=l.partition(EYE)
                out.append(tspan(head, col, x=fx, dy=dy))
                out.append(f'<tspan fill="{col}" font-size="{fs*EYE_SCALE:.1f}" dx="{EYE_DX}" dy="{EYE_DY}">{esc(EYE)}</tspan>')
                out.append(f'<tspan fill="{col}" dx="{EYE_TAIL_DX}" dy="{-EYE_DY}">{esc(tail)}</tspan>')
            else:
                out.append(tspan(l, col, x=fx, dy=dy))
        return "".join(out)
    # smooth eased bob (spline, not the old linear triangle that snapped at the top/bottom)
    P.append(f'<g><animateTransform attributeName="transform" type="translate" '
             f'values="0 0;0 -7;0 0" keyTimes="0;0.5;1" calcMode="spline" '
             f'keySplines="0.42 0 0.58 1;0.42 0 0.58 1" dur="{d["bob"]}s" repeatCount="indefinite"/>')
    P.append(f'<text y="{y0}" font-family="{CAT_FONT}" font-size="{fs}" '
             f'xml:space="preserve" style="white-space:pre">{cat_text()}</text>')
    P.append(f'<text x="30" y="{y0+3*lh+30:.1f}" font-family="{FONT}" font-size="13" fill="{DIM}">Blip · Lv.{d["level"]}</text>')
    P.append('</g>')
    sx=280; sy=TB+64; bw=330                  # bar width leaves room for the longest note ("6d · getting peckish")
    def stat(y,label,pct,col,note):
        pct=max(0.0,min(1.0,pct))
        return (f'<text x="{sx}" y="{y}" font-family="{FONT}" font-size="14" fill="{TXT}">{esc(label)}</text>'
                f'<rect x="{sx+110}" y="{y-13}" width="{bw}" height="14" rx="7" fill="#161b22"/>'
                f'<rect x="{sx+110}" y="{y-13}" width="{int(bw*pct)}" height="14" rx="7" fill="{col}"/>'
                f'<text x="{sx+110+bw+12}" y="{y}" font-family="{FONT}" font-size="12" fill="{DIM}">{esc(note)}</text>')
    P.append(stat(sy,"Age",d["age_pct"],CYAN,d["age_note"]))
    P.append(stat(sy+34,"Hunger",d["hunger_pct"],d["hunger_col"],d["hunger_note"]))
    P.append(stat(sy+68,"Energy",d["energy_pct"],PUR,d["energy_note"]))
    P.append(f'<text x="{sx}" y="{sy+104}" font-family="{FONT}" font-size="13" fill="{GREEN}">→ feed me by committing</text>')
    P.append(f'<text x="{sx+230}" y="{sy+104}" font-family="{FONT}" font-size="13" fill="{DIM}">{esc(d["last_fed"])}</text>')
    return svg(W,H,P)
