"""Render docs/architecture-light.png and docs/architecture-dark.png with Graphviz.

    python docs/architecture.py docs

Needs `dot` (graphviz) and `rsvg-convert` (librsvg). The README picks the file that
matches the viewer's theme with a <picture> element.
"""
import pathlib, subprocess, sys

# GitHub's own palette, so the boxes sit flat on the page in either theme
THEMES = {
    "light": dict(fg="#1f2328", muted="#59636e", line="#d0d7de", edge="#6e7781",
                  box="#f6f8fa", accent="#0969da", green="#1a7f37"),
    "dark":  dict(fg="#e6edf3", muted="#9198a1", line="#3d444d", edge="#8b949e",
                  box="#161b22", accent="#58a6ff", green="#3fb950"),
}

TEMPLATE = r'''
digraph live_readme {
  graph [rankdir=TB, newrank=true, bgcolor="transparent", pad="0.1", nodesep="0.3", ranksep="0.45",
         fontname="Noto Sans", fontsize=14, fontcolor="{muted}"]
  node  [shape=box, style="rounded,filled", fillcolor="{box}", color="{line}", penwidth=1.2,
         fontname="Noto Sans", fontsize=14, fontcolor="{fg}", margin="0.2,0.1"]
  edge  [color="{edge}", fontname="Noto Sans Mono", fontsize=12, fontcolor="{muted}",
         arrowsize=0.8, penwidth=1.1]

  subgraph cluster_home {
    label="home server  ·  Docker"; labeljust=l; style="rounded,dashed"; color="{line}"; margin=12
    globe   [label=<<b>globe-service</b><br/><font face="Noto Sans Mono" point-size="12" color="{muted}">build_earth.py · globe_ctl.py</font>>]
    panels  [label=<<b>panels-service</b><br/><font face="Noto Sans Mono" point-size="12" color="{muted}">panels_ctl.py · panels.py</font>>]
    apache  [label=<<b>Apache :80</b><br/><font face="Noto Sans Mono" point-size="12" color="{muted}">/srv/http/globe</font>>]
  }

  subgraph cluster_cf {
    label="Cloudflare"; labeljust=l; style="rounded,dashed"; color="{line}"; margin=12
    counter [label=<<b>Durable Object</b><br/><font face="Noto Sans Mono" point-size="12" color="{muted}">cookies · pets · plays</font>>]
    worker  [label=<<b>Worker</b><br/><font face="Noto Sans Mono" point-size="12" color="{muted}">awsnap.dev/globe/*</font>>]
  }

  camo   [label=<<b>GitHub camo</b><br/><font point-size="12" color="{muted}">image proxy · re-fetches on every view</font>>]
  readme [label=<<b>README</b><br/><font face="Noto Sans Mono" point-size="12" color="{muted}">github.com/aw-snap</font>>, color="{accent}", penwidth=1.6]

  {rank=same; globe; panels; counter}
  {rank=same; apache; worker}

  globe   -> apache  [label=" globe.avif\l one slot per hour\l"]
  panels  -> apache  [label=" card.svg · music.svg\l every 10 s\l"]
  panels  -> worker  [label=" blip.json\l 30 s cache\l", color="{green}", fontcolor="{green}"]
  worker  -> counter [dir=both, label=" /treat /pet /play\l counter\l"]
  apache  -> camo    [label=" Cache-Control: no-store "]
  worker  -> camo    [label=" blip.svg · btn-*.svg "]
  camo    -> readme
  readme  -> worker  [label=" click ▶ 302 back ", style=dashed,
                      color="{accent}", fontcolor="{accent}", constraint=false]
}
'''

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "docs")
for name, colours in THEMES.items():
    src = TEMPLATE
    for key, value in colours.items():
        src = src.replace("{" + key + "}", value)
    svg = subprocess.run(["dot", "-Tsvg"], input=src.encode(), capture_output=True, check=True).stdout
    subprocess.run(["rsvg-convert", "-z", "2", "-o", str(out / f"architecture-{name}.png")], input=svg, check=True)
    print(f"wrote {out}/architecture-{name}.png")
