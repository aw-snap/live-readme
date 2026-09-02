// awsnap-cookie — the clickable bits of the GitHub profile README, served from the edge.
//   GET /globe/treat | /globe/pet | /globe/play   -> interact with Blip (+1 to that counter), then 302 back to the profile
//   GET /globe/blip.svg                            -> the Blip panel (cat · blipfetch rows · scoreboard)
//   GET /globe/btn-cookie.svg | btn-pet.svg | btn-play.svg -> the three button images shown under the panel
//   GET /globe/count                               -> JSON {n, pets, plays, last}
//   GET /globe/click, /globe/cookie.svg            -> (v2 README) same cookie counter / the old cookie-jar panel
// All counters live in ONE Durable Object, so a click's write and camo's read hit the same instance
// and the number is right the instant you bounce back.
// NOTE: the Durable Object instance name below ("cookies-v2") IS the counter. Never change it —
// a new name starts a fresh instance at 0 and throws away everyone's clicks. Storage key "n" = cookies.

const KINDS = ["cookie", "pet", "play"];
const nzDate = ms => new Date(ms).toLocaleDateString("en-CA", { timeZone: "Pacific/Auckland" });   // YYYY-MM-DD, Blip's home time
const BORN = "2026-09-02";                                     // the day the counter (and Blip) went live

export class Counter {
  constructor(state) { this.state = state; }
  async fetch(request) {
    const u = new URL(request.url), st = this.state.storage, now = Date.now();
    const m = await st.get(["n", "pets", "plays", "last", "lastAt", "days", "pending"]);
    let n = m.get("n") || 0, pets = m.get("pets") || 0, plays = m.get("plays") || 0, last = m.get("last") || 0;
    let lastAt = m.get("lastAt") || {}, days = m.get("days") || {}, pending = m.get("pending") || null;
    if (u.pathname === "/inc") {
      const kind = KINDS.includes(u.searchParams.get("kind")) ? u.searchParams.get("kind") : "cookie";
      if (kind === "cookie") n += 1; else if (kind === "pet") pets += 1; else plays += 1;
      last = now; lastAt = { ...lastAt, [kind]: now };
      const day = nzDate(now); days = { ...days, [day]: (days[day] || 0) + 1 };
      for (const k of Object.keys(days).sort().slice(0, -60)) delete days[k];          // keep ~2 months of days
      pending = { kind, t: now, panel: false, btn: false };                              // the click nobody has been shown yet
      await st.put({ n, pets, plays, last, lastAt, days, pending });
    }
    let fed = null;
    // "take": a render claims the pending click ONCE per image (panel, and the matching button),
    // and only within 60 s of the click — i.e. the clicker's own page load. Refreshes show nothing.
    if (u.pathname === "/take" && pending && typeof pending === "object" && now - pending.t < 60000) {
      const who = u.searchParams.get("who") === "btn" ? "btn" : "panel", kind = u.searchParams.get("kind");
      if (!pending[who] && (who === "panel" || kind === pending.kind)) {
        fed = pending.kind; pending = { ...pending, [who]: true }; await st.put("pending", pending);
      }
    }
    return Response.json({ n, pets, plays, last, lastAt, days, fed });
  }
}

const NOCACHE = "no-store, no-cache, must-revalidate, max-age=0";
const PROFILE = "https://github.com/aw-snap";
const BLIP_STATE = "http://ssh.awsnap.dev/globe/blip.json";   // written every 10 s by panels-service (sleepy, bob, fav)

// Count only genuine human clicks: a user-activated top-level navigation.
// Rejects GitHub's link-scanner, browser prefetch/prerender, and bots/crawlers.
function isRealClick(req) {
  const h = req.headers;
  const purpose = (h.get("Sec-Purpose") || h.get("Purpose") || "").toLowerCase();
  if (purpose.includes("prefetch") || purpose.includes("prerender")) return false;
  if (h.get("Sec-Fetch-User") !== "?1") return false;                       // set only on user activation (a click)
  if ((h.get("Sec-Fetch-Mode") || "").toLowerCase() !== "navigate") return false;
  const ua = (h.get("User-Agent") || "").toLowerCase();
  if (!ua) return false;
  if (/bot|crawl|spider|slurp|scan|preview|curl|wget|python|go-http|node-fetch|libwww|httpclient|monitor|uptime|headless|facebookexternalhit|slackbot|twitterbot|discordbot|telegrambot|whatsapp|linkedinbot|embedly|camo|github/.test(ua)) return false;
  return true;
}

async function counter(stub, op) {
  try {
    const j = await (await stub.fetch("https://do/" + op)).json();
    return (j && typeof j === "object") ? j : { n: Number(j) || 0 };
  } catch (e) { return { n: 0 }; }
}

async function blipState() {
  try {
    const r = await fetch(BLIP_STATE, { cf: { cacheTtl: 30, cacheEverything: true } });
    if (r.ok) return await r.json();
  } catch (e) {}
  return {};
}

const svgResponse = body => new Response(body, { headers: { "Content-Type": "image/svg+xml; charset=utf-8", "Cache-Control": NOCACHE } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const stub = env.COUNTER.get(env.COUNTER.idFromName("cookies-v2"));   // NEVER rename (see top of file)
    const p = url.pathname.replace(/\/$/, "");

    const ACT = { "/globe/treat": "cookie", "/globe/click": "cookie", "/globe/pet": "pet", "/globe/play": "play" };
    if (ACT[p]) {
      if (isRealClick(request)) await counter(stub, "inc?kind=" + ACT[p]);   // skip prefetch / scanners / bots
      return new Response(null, { status: 302, headers: { Location: PROFILE, "Cache-Control": NOCACHE } });
    }
    if (p === "/globe/blip.svg") {
      const [c, s] = await Promise.all([counter(stub, "take?who=panel"), blipState()]);
      return svgResponse(blipSVG(s, c));
    }
    const b = /^\/globe\/btn-(cookie|pet|play)\.svg$/.exec(p);
    if (b) { const [c, s] = await Promise.all([counter(stub, `take?who=btn&kind=${b[1]}`), blipState()]); return svgResponse(buttonSVG(b[1], c, s)); }
    if (p === "/globe/cookie.svg") return svgResponse(cookieSVG((await counter(stub, "get")).n));
    if (p === "/globe/count") {
      const c = await counter(stub, "get");
      return Response.json({ n: c.n || 0, pets: c.pets || 0, plays: c.plays || 0, last: c.last || 0 }, { headers: { "Cache-Control": NOCACHE } });
    }
    return new Response("not found", { status: 404 });
  },
};

// ---------------------------------------------------------------------------------------------
// shared bits — 1:1 ports of panels.py (window chrome, palette, the cat)
const FONT = "'JetBrains Mono','Fira Code','SF Mono',ui-monospace,Menlo,Consolas,monospace";
const CAT_FONT = "'Roboto',sans-serif";
const BG = "#0d1117", PANEL = "#010409", BORDER = "#30363d", GREEN = "#3fb950", TXT = "#c9d1d9",
      DIM = "#6e7681", YEL = "#d29922", PUR = "#bc8cff", CAT_COL = "#8292a1", PINK = "#ff7b9c", BLUE = "#58a6ff";
const TB = 34;
const CAT = "    ╱|、   \n  (˚ˎ 。7  \n   |、˜〵  \n  じしˍ,)ノ";
const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function windowChrome(W, H, title) {
  const dots = ["#ff5f56", "#ffbd2e", "#27c93f"]
    .map((c, i) => `<circle cx="${22 + i * 20}" cy="18" r="6" fill="${c}"/>`).join("");
  return `<rect x="1" y="1" width="${W - 2}" height="${H - 2}" rx="12" fill="${BG}" stroke="${BORDER}"/>`
    + `<rect x="1" y="1" width="${W - 2}" height="${TB}" rx="12" fill="${PANEL}"/>`
    + `<rect x="1" y="20" width="${W - 2}" height="${TB - 19}" fill="${PANEL}"/>`
    + dots
    + `<text x="${W / 2}" y="23" font-size="13" fill="${DIM}" text-anchor="middle">${esc(title)}</text>`;
}

// the cat, exactly as panels.pet_svg draws it (own proportional font; left eye split out and gently enlarged)
function catText(fx, fs, lh) {
  const EYE = "˚", EYE_SCALE = 1.18, EYE_DX = 1.0, EYE_DY = 8.0, EYE_TAIL_DX = -1.5;
  return CAT.split("\n").map((l, i) => {
    const dy = i === 0 ? "0" : lh.toFixed(2);
    if (i === 1 && l.includes(EYE)) {
      const k = l.indexOf(EYE), head = l.slice(0, k), tail = l.slice(k + 1);
      return `<tspan fill="${CAT_COL}" x="${fx}" dy="${dy}">${esc(head)}</tspan>`
        + `<tspan fill="${CAT_COL}" font-size="${(fs * EYE_SCALE).toFixed(1)}" dx="${EYE_DX}" dy="${EYE_DY}">${esc(EYE)}</tspan>`
        + `<tspan fill="${CAT_COL}" dx="${EYE_TAIL_DX}" dy="${-EYE_DY}">${esc(tail)}</tspan>`;
    }
    return `<tspan fill="${CAT_COL}" x="${fx}" dy="${dy}">${esc(l)}</tspan>`;
  }).join("");
}

// a small cookie (same recipe as the big one): the cookie button, and by Blip's mouth after a treat
function miniCookie(cx, cy, r, id) {
  let seed = 11; const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
  const pts = []; for (let i = 0; i < 18; i++) { const a = i / 18 * Math.PI * 2, rr = r + (rnd() - 0.5) * r * 0.12; pts.push([cx + Math.cos(a) * rr, cy + Math.sin(a) * rr]); }
  const body = "M" + pts.map(p => p[0].toFixed(1) + " " + p[1].toFixed(1)).join("L") + "Z";
  const chips = [[-0.35,-0.3],[0.3,-0.4],[-0.05,0.1],[0.35,0.3],[-0.45,0.25],[0.05,0.5]].map(([dx,dy]) =>
    `<circle cx="${(cx + dx * r).toFixed(1)}" cy="${(cy + dy * r).toFixed(1)}" r="${(r * 0.14).toFixed(1)}" fill="#3a2210"/>`).join("");
  return `<g mask="url(#${id})"><path d="${body}" fill="url(#dough)" stroke="#7a4a1e" stroke-width="1.2" stroke-linejoin="round"/>${chips}</g>`;
}
const DEFS = (W, H) => `<defs>`
  + `<radialGradient id="dough" cx="38%" cy="32%" r="72%"><stop offset="0" stop-color="#e9bd72"/><stop offset="0.55" stop-color="#cf914a"/><stop offset="1" stop-color="#8e5622"/></radialGradient>`
  + `<mask id="bite1"><rect width="${W}" height="${H}" fill="#fff"/></mask><mask id="bite2"><rect x="-40" y="-40" width="80" height="80" fill="#fff"/></mask></defs>`;

// the three interaction icons (all vector, so they look the same in every viewer)
const iconCookie = (x, y) => miniCookie(x, y, 12, "bite1");
const iconHand = (x, y) => `<path transform="translate(${x - 9} ${y - 10}) scale(0.75)" d="M6 10 V4 a2 2 0 0 1 4 0 v6 M10 10 V2 a2 2 0 0 1 4 0 v8 M14 10 V4 a2 2 0 0 1 4 0 v6 M18 12 V8 a2 2 0 0 1 4 0 v8 c0 6 -4 10 -9 10 h-2 c-3 0 -5 -1 -7 -4 l-4 -6 a2 2 0 0 1 3 -2.5 l3 3" fill="none" stroke="${PINK}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`;
const iconYarn = (x, y) => `<circle cx="${x}" cy="${y}" r="11" fill="${BLUE}"/><path d="M${x - 8} ${y - 5} Q${x} ${y} ${x + 8} ${y - 5} M${x - 8} ${y + 5} Q${x} ${y} ${x + 8} ${y + 5} M${x - 5} ${y - 9} Q${x} ${y} ${x - 5} ${y + 9}" stroke="#0d1117" stroke-width="1.5" fill="none"/>`;
const SPEC = { cookie: ["give a cookie", iconCookie, GREEN, YEL], pet: ["pet Blip", iconHand, PINK, PINK], play: ["play with Blip", iconYarn, BLUE, BLUE] };

// "+1" badge: one-shot SMIL (repeatCount defaults to 1) — visible 5 s after the image loads, then fades and stays gone
const plus1 = (x, y, col) => `<g><animate attributeName="opacity" begin="5s" dur="0.4s" from="1" to="0" fill="freeze"/>`
  + `<rect x="${x}" y="${y - 16}" width="34" height="22" rx="11" fill="${col}"/><text x="${x + 17}" y="${y}" font-size="14" font-weight="bold" fill="#0d1117" text-anchor="middle">+1</text></g>`;

// ---- game rules ----
// level: each level costs 5 + L xp (Lv1->2 = 6, Lv2->3 = 7 ...): gently curved. 8 xp = Lv.2, 100 = Lv.10, 1000 = Lv.40.
function levelOf(xp) {
  let level = 1, need = 6;
  while (xp >= need) { xp -= need; level += 1; need = 5 + level; }
  return { level, into: xp, need };
}
// what Blip wants next = the kind it has had least recently (never = most wanted); ties fall to cookie
function wants(c) {
  const at = c.lastAt || {}; let best = "cookie", bt = Infinity;
  for (const k of KINDS) { const t = Number(at[k]) || 0; if (t < bt) { bt = t; best = k; } }
  return best;
}
function streakOf(days) {
  const d = days || {}; const day = new Date();
  let cur = nzDate(day.getTime()); if (!d[cur]) day.setTime(day.getTime() - 864e5), cur = nzDate(day.getTime());
  let s = 0; while (d[cur]) { s += 1; day.setTime(day.getTime() - 864e5); cur = nzDate(day.getTime()); }
  return s;
}
function ago(ms) {
  if (!ms) return "never";
  const s = (Date.now() - ms) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) { const m = Math.floor(s / 60); return `${m} min${m === 1 ? "" : "s"} ago`; }
  if (s < 86400) { const h = Math.floor(s / 3600); return `${h} hour${h === 1 ? "" : "s"} ago`; }
  const d = Math.floor(s / 86400); return `${d} day${d === 1 ? "" : "s"} ago`;
}
function ageDays() {
  const [y, mo, d] = BORN.split("-").map(Number), [ty, tm, td] = nzDate(Date.now()).split("-").map(Number);
  return Math.max(0, Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(y, mo - 1, d)) / 864e5));
}

// ---- the accessories Blip earns (drawn over the ASCII head) ----
const crown = (x, y) => `<path d="M${x} ${y + 12} L${x} ${y} L${x + 6} ${y + 6} L${x + 11} ${y - 2} L${x + 16} ${y + 6} L${x + 22} ${y} L${x + 22} ${y + 12} Z" fill="${YEL}" stroke="#8a6414" stroke-width="1"/>`;
const bow = (x, y) => `<path d="M${x} ${y} l-9 -6 v12 z M${x} ${y} l9 -6 v12 z" fill="${PINK}"/><circle cx="${x}" cy="${y}" r="2.4" fill="#ff9fb6"/>`;
const sparkle = (x, y, d) => `<path d="M${x} ${y - 5} L${x + 1.5} ${y - 1.5} L${x + 5} ${y} L${x + 1.5} ${y + 1.5} L${x} ${y + 5} L${x - 1.5} ${y + 1.5} L${x - 5} ${y} L${x - 1.5} ${y - 1.5} Z" fill="#fff3b0"><animate attributeName="opacity" values="0.2;1;0.2" dur="1.8s" begin="${d}s" repeatCount="indefinite"/></path>`;
function accessory(level) {
  if (level >= 20) return crown(90, TB + 30) + sparkle(80, TB + 24, 0) + sparkle(122, TB + 30, 0.9);   // Lv.20: crown + sparkles
  if (level >= 10) return crown(90, TB + 30);                                                          // Lv.10: crown
  if (level >= 5) return bow(120, TB + 44);                                                            // Lv.5: bow on the ear
  return "";
}

// fastfetch-style rows with dotted leaders (label left, value right-aligned; the leader is a dashed line)
function rows(x, y, w, items, fs = 14, lh = 24) {
  let o = "";
  items.forEach(([k, v, col], i) => {
    const yy = y + i * lh, x1 = x + k.length * 8.6 + 10, x2 = x + w - String(v).length * 8.6 - 10;
    o += `<text x="${x}" y="${yy}" font-size="${fs}" fill="${DIM}">${esc(k)}</text>`
      + (x2 > x1 + 8 ? `<line x1="${x1.toFixed(1)}" y1="${yy - 4}" x2="${x2.toFixed(1)}" y2="${yy - 4}" stroke="#30363d" stroke-width="1" stroke-dasharray="1 4"/>` : "")
      + `<text x="${x + w}" y="${yy}" font-size="${fs}" fill="${col || TXT}" text-anchor="end">${esc(v)}</text>`;
  });
  return o;
}

// ---------------------------------------------------------------------------------------------
// the Blip panel: cat (+ accessory, reaction) · Lv + xp bar · blipfetch rows · scoreboard
// ---- shooting stars (spike, 2026-09-03): the shared sky from blip.json {stars:{list,blip,btn,lag}}. Mirrors
// panels.star_layer so every window draws the identical streaks; nothing is drawn when the key is absent. ----
function starLayer(stars, win, lag = 0, col = "#e8f1ff") {
  if (!Array.isArray(stars) || !Array.isArray(win)) return "";
  const [ox, oy, k] = win;
  let out = `<g transform="scale(${Number(k).toFixed(5)}) translate(${(-ox).toFixed(2)},${(-oy).toFixed(2)})"><defs>`;
  stars.forEach((s, i) => {
    out += `<linearGradient id="sk${i}" gradientUnits="userSpaceOnUse" x1="${-s.L}" y1="0" x2="0" y2="0">`
      + `<stop offset="0" stop-color="${col}" stop-opacity="0"/><stop offset="1" stop-color="${col}" stop-opacity="0.95"/></linearGradient>`;
  });
  out += `</defs>`;
  stars.forEach((s, i) => {
    const x1 = s.x + s.dx * s.v * s.T, y1 = s.y + s.dy * s.v * s.T, b = (s.b + (Number(lag) || 0)).toFixed(2);
    out += `<g opacity="0"><animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.06;0.9;1" begin="${b}s" dur="${s.T}s" fill="freeze"/>`
      + `<animateTransform attributeName="transform" type="translate" from="${s.x} ${s.y}" to="${x1.toFixed(1)} ${y1.toFixed(1)}" begin="${b}s" dur="${s.T}s" fill="freeze"/>`
      + `<g transform="rotate(${s.a})"><line x1="${-s.L}" y1="0" x2="0" y2="0" stroke="url(#sk${i})" stroke-width="2.2" stroke-linecap="round"/>`
      + `<circle r="${(s.r * 2.6).toFixed(1)}" fill="${col}" opacity="0.22"/><circle r="${s.r}" fill="#ffffff"/></g></g>`;
  });
  return out + `</g>`;
}

export function blipSVG(s, c) {
  const W = 900, H = TB + 230;
  const n = Number(c.n) || 0, pets = Number(c.pets) || 0, plays = Number(c.plays) || 0, last = Number(c.last) || 0;
  const xp = n + pets + plays, lv = levelOf(xp);
  const fed = KINDS.includes(c.fed) ? c.fed : null;           // one-shot: only the clicker's own page load
  const sleepy = !!s.sleepy && !fed, want = wants(c), bob = Number(s.bob) || 2.4;
  const fx = 46, y0 = TB + 58, fs = 30, lh = fs * 1.15;
  let out = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" font-family="${FONT}">`
    + DEFS(W, H) + windowChrome(W, H, "blip.svg");
  // --- the cat (eased bob) with its reaction ---
  out += `<g><animateTransform attributeName="transform" type="translate" values="0 0;0 -7;0 0" keyTimes="0;0.5;1" `
    + `calcMode="spline" keySplines="0.42 0 0.58 1;0.42 0 0.58 1" dur="${bob}s" repeatCount="indefinite"/>`
    + `<text y="${y0}" font-family="${CAT_FONT}" font-size="${fs}" xml:space="preserve" style="white-space:pre">${catText(fx, fs, lh)}</text>`
    + accessory(lv.level);
  if (fed === "cookie") out += `<g transform="translate(150 ${TB + 118})">${miniCookie(0, 0, 11, "bite2")}</g>`;                 // a cookie by the mouth
  if (fed === "pet") [[150, TB + 60, 9, 0], [170, TB + 44, 12, 0.5], [138, TB + 36, 8, 1.0]].forEach(([x, y, r, b]) =>     // floating hearts
    out += `<path transform="translate(${x} ${y}) scale(${r / 10})" d="M0 6 C-10 -4 -6 -14 0 -8 C6 -14 10 -4 0 6Z" fill="${PINK}" opacity="0"><animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.2;0.7;1" dur="2.4s" begin="${b}s" repeatCount="indefinite"/></path>`);
  if (fed === "play") out += `<g transform="translate(176 ${TB + 126})"><g><animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="3s" repeatCount="indefinite"/>`   // a spinning yarn ball
    + `<circle r="10" fill="${BLUE}"/><path d="M-7 -5 Q0 0 7 -5 M-7 5 Q0 0 7 5 M-5 -8 Q0 0 -5 8" stroke="#0d1117" stroke-width="1.4" fill="none"/></g></g>`;
  if (sleepy) [[152, TB + 52, 11, 0], [166, TB + 38, 14, 0.7], [182, TB + 22, 17, 1.4]].forEach(([x, y, size, beg]) =>          // z z z
    out += `<text x="${x}" y="${y}" font-size="${size}" fill="${DIM}" opacity="0">z<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.25;0.6;1" dur="3s" begin="${beg}s" repeatCount="indefinite"/></text>`);
  out += `</g>`;
  // --- level + xp bar under the cat ---
  const capY = y0 + 3 * lh + 30, xpw = 200;
  out += `<text x="30" y="${capY.toFixed(1)}" font-size="13" fill="${DIM}">Blip · Lv.${lv.level}</text>`
    + `<text x="${30 + xpw}" y="${capY.toFixed(1)}" font-size="11" fill="${DIM}" text-anchor="end">${lv.into}/${lv.need} xp</text>`
    + `<rect x="30" y="${(capY + 7).toFixed(1)}" width="${xpw}" height="2" rx="1" fill="#21262d"/>`
    + `<rect x="30" y="${(capY + 7).toFixed(1)}" width="${(xpw * lv.into / lv.need).toFixed(1)}" height="2" rx="1" fill="${GREEN}"/>`;
  // --- blipfetch rows (every mood < 25 chars) ---
  const WANT = { cookie: "wants a cookie", pet: "wants pats", play: "wants to play" };
  let mood, moodCol = TXT;
  if (fed === "cookie") { mood = "nom nom · thanks :3"; moodCol = PUR; }
  else if (fed === "pet") { mood = "purring · ♥"; moodCol = PINK; }
  else if (fed === "play") { mood = "zoomies!!"; moodCol = BLUE; }
  else if (sleepy) mood = "zzz · asleep in NZ";
  else if (!last) mood = "waiting for a visitor";
  else { const h = (Date.now() - last) / 36e5; mood = `${h < 1 ? "purring" : h < 6 ? "content" : h < 24 ? "chill" : h < 72 ? "lonely" : "sad"} · ${WANT[want]}`; }
  const age = ageDays(), streak = streakOf(c.days);
  const fav = s.fav ? (String(s.fav).length > 20 ? String(s.fav).slice(0, 19) + "…" : String(s.fav)) + " ♪" : "cookies";
  out += rows(280, TB + 66, 290, [                              // rows end at x=570; scoreboard starts ~640
    ["mood", mood, moodCol],
    ["age", `${age} day${age === 1 ? "" : "s"}`],
    ["streak", streak ? `${streak} day${streak === 1 ? "" : "s"} of visitors` : "none yet"],
    ["favourite", fav],
    ["last visitor", ago(last)],
  ]);
  // --- scoreboard: the three counters ---
  const sx = 668, cols = [[n, "cookie", YEL, "cookie"], [pets, "pet", PINK, "pet"], [plays, "play", BLUE, "play"]];
  cols.forEach(([v, l, col, kind], i) => {
    const x = sx + i * 88, txt = v.toLocaleString("en-US"), size = txt.length > 4 ? 22 : txt.length > 2 ? 28 : 34;
    out += `<text x="${x}" y="${TB + 110}" font-size="${size}" font-weight="bold" fill="${col}" text-anchor="middle">${txt}</text>`
      + `<text x="${x}" y="${TB + 130}" font-size="12" fill="${DIM}" text-anchor="middle">${l}${v === 1 ? "" : "s"}</text>`;
    if (fed === kind) out += plus1(x - 17, TB + 78, col);                       // centred above the number
  });
  out += `<text x="${sx + 88}" y="${TB + 176}" font-size="12" fill="${DIM}" text-anchor="middle">click a button below ↓</text>`;
  if (s.stars) out += starLayer(s.stars.list, s.stars.blip, s.stars.lag && s.stars.lag.blip);
  return out + `</svg>`;
}

// one of the three buttons under the panel. Pulses when it is what Blip wants; "+1" for the clicker only.
export function buttonSVG(kind, c, s = {}) {
  const W = 280, H = 60, [label, icon, col] = SPEC[kind] || SPEC.cookie;
  const pulse = wants(c) === kind, fed = c.fed === kind;
  const x = 8, y = 8, w = W - 16, h = H - 16;
  let out = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" font-family="${FONT}">` + DEFS(W, H);
  if (pulse) out += `<rect x="${x - 4}" y="${y - 4}" width="${w + 8}" height="${h + 8}" rx="${h / 2 + 4}" fill="none" stroke="${col}" stroke-width="2.5"><animate attributeName="opacity" values="0.1;1;0.1" dur="1.6s" repeatCount="indefinite"/></rect>`;
  out += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${h / 2}" fill="#161b22" stroke="${col}" stroke-width="1.5"/>` + icon(x + 26, y + h / 2)
    + `<text x="${x + 48}" y="${y + h / 2 + 5}" font-size="15" font-weight="bold" fill="${col}">${esc(label)}</text>`;
  if (fed) out += plus1(W - 52, 24, col);
  if (s.stars && s.stars.btn) out += starLayer(s.stars.list, s.stars.btn[KINDS.indexOf(kind)], s.stars.lag && s.stars.lag.btn);
  return out + `</svg>`;
}

// ---------------------------------------------------------------------------------------------
// v2 README's standalone cookie jar (kept so the previous README keeps working)
export function cookieSVG(n) {
  const count = Number(n).toLocaleString("en-US");
  const W = 900, H = 150 + TB, cx = 96, cy = TB + 76, r = 48, my = TB + 75;   // my = vertical middle of the body
  let seed = 7; const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
  const pts = []; for (let i = 0; i < 28; i++) { const a = i / 28 * Math.PI * 2, rr = r + (rnd() - 0.5) * 5; pts.push([cx + Math.cos(a) * rr, cy + Math.sin(a) * rr]); }
  const body = "M" + pts.map(p => p[0].toFixed(1) + " " + p[1].toFixed(1)).join("L") + "Z";
  const chips = [[-18,-16,6,4.5,20],[12,-22,5,4,-30],[-4,4,6.5,5,60],[18,12,5.5,4.5,-15],[-24,12,5,4,35],[2,26,5.5,4,-50],[26,-6,4.5,4,10],[-8,-30,4,3.5,-40],[-30,-4,4,3.5,75]];
  const chipEls = chips.map(([dx,dy,rx,ry,rot]) =>
    `<ellipse cx="${cx+dx}" cy="${cy+dy}" rx="${rx}" ry="${ry}" transform="rotate(${rot} ${cx+dx} ${cy+dy})" fill="url(#chip)"/>`
    + `<ellipse cx="${cx+dx-1.5}" cy="${cy+dy-1.5}" rx="${rx*0.35}" ry="${ry*0.3}" transform="rotate(${rot} ${cx+dx} ${cy+dy})" fill="#7a4d27" opacity="0.7"/>`).join("");
  const crumbs = [[cx+50,cy-44,2.2],[cx+58,cy-34,1.6],[cx+44,cy-56,1.4]].map(([x,y,cr]) => `<circle cx="${x}" cy="${y}" r="${cr}" fill="#b07a3e"/>`).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" font-family="${FONT}">`
    + `<defs>`
    + `<radialGradient id="dough" cx="38%" cy="32%" r="72%"><stop offset="0" stop-color="#e9bd72"/><stop offset="0.55" stop-color="#cf914a"/><stop offset="1" stop-color="#8e5622"/></radialGradient>`
    + `<radialGradient id="chip" cx="35%" cy="30%" r="70%"><stop offset="0" stop-color="#6a4120"/><stop offset="1" stop-color="#2e1a0a"/></radialGradient>`
    + `<mask id="bite"><rect x="0" y="0" width="${W}" height="${H}" fill="#fff"/>`
    + `<circle cx="${cx+40}" cy="${cy-34}" r="21" fill="#000"/><circle cx="${cx+22}" cy="${cy-46}" r="11" fill="#000"/><circle cx="${cx+50}" cy="${cy-16}" r="9" fill="#000"/></mask>`
    + `<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#000" flood-opacity="0.55"/></filter>`
    + `</defs>`
    + windowChrome(W, H, "cookie jar — shared counter")
    + `<g transform-origin="${cx} ${cy}"><animateTransform attributeName="transform" type="rotate" `
    + `values="-3 ${cx} ${cy};3 ${cx} ${cy};-3 ${cx} ${cy}" dur="2.6s" repeatCount="indefinite"/>`
    + `<g filter="url(#shadow)"><g mask="url(#bite)">`
    + `<path d="${body}" fill="url(#dough)" stroke="#7a4a1e" stroke-width="2" stroke-linejoin="round"/>`
    + `<path d="${body}" fill="none" stroke="#f3d18e" stroke-width="1.5" opacity="0.35" transform="translate(-1.5 -1.5)"/>`
    + chipEls + `</g></g>` + crumbs + `</g>`
    + `<text x="190" y="${my-8}" font-size="44" font-weight="bold" fill="${YEL}">${count}</text>`
    + `<text x="192" y="${my+20}" font-size="16" fill="${TXT}">cookies baked</text>`
    + `<text x="192" y="${my+44}" font-size="12" fill="${DIM}">click the cookie to bake one</text>`
    + `</svg>`;
}
