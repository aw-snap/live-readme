# live-readme

The code behind [github.com/aw-snap](https://github.com/aw-snap): a GitHub profile rendered live by my home server and a Cloudflare Worker.

This is the profile live, straight from the servers. Every image is fetched fresh each reload, and buttons work (they redirect you to the profile afterwards).

<br/>

<p align="center">
  <img src="http://ssh.awsnap.dev/globe/globe.avif" width="300" alt="a live-rendered globe, lit for NZ's current time of day — rendered hourly on my own server"/>
</p>

<p align="center">
  <img src="http://ssh.awsnap.dev/globe/card.svg" width="820" alt="live fastfetch-style card: my setup, languages, hobbies"/>
</p>

<p align="center">
  <img src="http://ssh.awsnap.dev/globe/music.svg" width="820" alt="what I'm listening to atm"/>
</p>

<p align="center">
  <a href="https://awsnap.dev/globe/pet"><img src="https://awsnap.dev/globe/blip.svg" width="820" alt="Blip, my profile's cat with levels interaction from visitors. Click the cat to pet it :)"/></a>
  <br/>
  <a href="https://awsnap.dev/globe/treat"><img src="https://awsnap.dev/globe/btn-cookie.svg" width="260" alt="give Blip a cookie"/></a> <a href="https://awsnap.dev/globe/pet"><img src="https://awsnap.dev/globe/btn-pet.svg" width="260" alt="pet Blip"/></a> <a href="https://awsnap.dev/globe/play"><img src="https://awsnap.dev/globe/btn-play.svg" width="260" alt="play with Blip"/></a>
</p>

<br/>

| panel | what it shows | rendered by |
|---|---|---|
| globe | Earth lit for the real time of day as an animated AVIF | `globe/`, one pre-rendered slot per hour |
| fastfetch | time, server uptime, languages, hobbies and contact | `panels/`, every 10 s |
| now-playing | the current or last music track with its album art | `panels/`, every 10 s |
| Blip | a cat that levels up from visitor interactions | `worker/` on Cloudflare, per request |

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/architecture-dark.png">
  <img src="docs/architecture-light.png" alt="architecture: globe-service and panels-service in Docker write globe.avif, card.svg, music.svg and blip.json to Apache on port 80; a Cloudflare Worker reads blip.json and a Durable Object counter to serve blip.svg and the buttons; GitHub camo proxies all of it into the README, and a button click goes to the Worker and 302s back to the profile"/>
</picture>

GitHub proxies every README image through camo (its image proxy) and forbids scripts, so the whole design rests on two facts:

- **camo honours `Cache-Control: no-store`.** The card, the music panel and Blip send it, so camo fetches them again on every page view. The globe is ~800 KB and is cached for five minutes instead.
- **An SVG inside `<img>` can't run JavaScript or load anything external, but SMIL animation works.** So everything is inlined: the viewer's own font, album art as a data URI, icons as paths, animations in the markup.

### The globe

- `build_earth.py` is a numpy renderer: shaded day map, city lights, twilight terminator, lit clouds, sun glint on water, atmosphere rim and a marker on New Zealand. The sun sits where it really is for the chosen UTC hour. Frames are supersampled, motion-blurred and encoded as an animated AVIF.
- A render takes about half an hour, so nothing renders on demand. `globe_ctl.py` keeps hour slots pre-rendered, hourly around NZ dawn and dusk and two-hourly otherwise. Each tick copies the nearest slot to `globe.avif`; every few hours it re-renders the stalest one.
- Textures, sources and licences: [globe/TEXTURES.md](globe/TEXTURES.md).

### The card and the music panel

- `panels_ctl.py` runs every 10 s. It reads `languages.json` for the card, `/proc/uptime`, and Last.fm for recent tracks and the top artist of the week (Blip's "favourite"). Missing album art comes from Deezer, then iTunes. It writes `card.svg`, `music.svg` and `blip.json` atomically.
- `panels.py` builds the SVGs with the standard library only. Text has to line up in whatever font the viewer has, so the dotted leaders are SVG lines rather than runs of dots, and the Arch logo is line segments, because ASCII slashes never join up across fonts.

### Blip

- The Worker serves `blip.svg` and the three buttons, and handles `/treat`, `/pet` and `/play` by bumping a Durable Object and redirecting back to the profile. Not KV: it is eventually consistent, and camo reads from a different edge than the one the clicker hit.
- **Only real clicks count.** Prefetches, link previews and bots are dropped by `Sec-Fetch-User`, `Sec-Fetch-Mode` and a user-agent blocklist.
- **Reactions are one-shot.** A click sets a pending flag that the next render within 60 s consumes, so only the clicker, whose browser reloads after the redirect, sees the cookie by Blip's mouth and the "+1" badge.
- **Levels.** XP is cookies + pets + plays, and each level costs `5 + level` XP. A bow at 5, a crown at 10, sparkles at 20.
- **Wants.** Blip wants whichever interaction it has had least recently, and that button pulses.
- **Streak** counts consecutive NZ days with a visitor.
- The counter has never been reset and never will be: the Durable Object instance name and its migration are fixed.

### Things that were a little bit of a pain in the a##

- Two SVG documents in one page share nothing. A star flying from one panel into the next has to be drawn in both, and each image starts its animation clock when first painted, so the join is only as good as the load-time skew. Still in the code behind `"stars": true` in `languages.json`, off by default.
- Fonts: assume nothing. Every viewer, both GitHub themes and camo's own "view image" page differ. Design in cells of `0.6em` and anchor both ends of every row.
- Test clicks count. `curl` with the right headers is a real click as far as the Worker knows, and the tally is permanent.

## Run your own

You need a Linux box with Docker and a web server on port 80, a Cloudflare zone for the Worker, a GitHub profile repo, and optionally a Last.fm API key for the music panel.

**1. Build the shared image** (python:3.13-slim + numpy + pillow):

```bash
docker build -t globe-deps globe/
```

**2. Start the globe renderer:**

```bash
docker run -d --name globe-service --restart unless-stopped --user 1000:1000 \
  -e REGEN_HOURS=3 \
  -v "$PWD/globe:/app" \
  -v /srv/http/globe:/web \
  globe-deps python /app/globe_ctl.py loop
```

**3. Start the panels.** Copy `panels/lastfm.example.json` to `panels/lastfm.json` and fill in your key and username first:

```bash
docker run -d --name panels-service --restart unless-stopped --user 1000:1000 \
  -e WEB=/web -e GH_USER=you -e LOOP=10 \
  -v "$PWD/panels:/app" \
  -v /srv/http/globe:/web \
  globe-deps python /app/panels_ctl.py loop
```

**4. Set the cache headers.** Apache needs `AllowOverride FileInfo` on that directory:

```bash
cp webroot/.htaccess /srv/http/globe/
```

**5. Deploy the Worker.** Set the routes for your zone in `wrangler.toml`, and `PROFILE` and `BLIP_STATE` at the top of `src/index.js`:

```bash
cd worker
npm install
npx wrangler deploy
```

**6. Point your profile README at the images.** [profile/README.md](profile/README.md) is the one in use. Edit `panels/languages.json` for the card's content; it is re-read every tick, no restart needed.

## History

| version | Blip |
|---|---|
| v1 | a pet that levelled up with my commit count |
| v2 | a cookie jar visitors could fill |
| v3 | the cat, with a commit heartbeat and a single cookie button |
| v4 | commits gone; levels come only from visitors' cookies, pets and plays |

## Licence

MIT for the code. The day and night maps are NASA imagery (public domain); the cloud map is Solar System Scope's, CC BY 4.0. See `globe/TEXTURES.md`.
