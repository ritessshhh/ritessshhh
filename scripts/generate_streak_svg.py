#!/usr/bin/env python3
"""Generate an animated GitHub contribution heatmap SVG (squares light up one by
one, then the current row keeps a soft glow).

Reads the calendar from data/stats.json (produced by fetch_stats.py) so PRIVATE
contributions are included when a token was used. Falls back to the public
jogruber mirror if stats.json is missing, so it still works standalone.

Usage: python generate_streak_svg.py [username] [output.svg]
"""
import datetime
import json
import os
import sys
import urllib.request

USER = sys.argv[1] if len(sys.argv) > 1 else "ritessshhh"
OUT = sys.argv[2] if len(sys.argv) > 2 else "contrib-heatmap.svg"
HERE = os.path.dirname(os.path.abspath(__file__))
STATS = os.path.join(HERE, "..", "data", "stats.json")


def get_days():
    if os.path.exists(STATS):
        cal = json.load(open(STATS)).get("calendar")
        if cal and cal.get("days"):
            return cal["days"], cal.get("total", sum(d["count"] for d in cal["days"]))
    url = f"https://github-contributions-api.jogruber.de/v4/{USER}?y=last"
    with urllib.request.urlopen(url, timeout=25) as r:
        d = json.loads(r.read().decode())
    return d["contributions"], d["total"]["lastYear"]


days, total = get_days()

# ---- layout ----
CELL, GAP, RAD, LEFT, TOP = 13, 3, 2.5, 34, 24
COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
GRAY = "#7d8590"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

n = len(days)
NW = (n + 6) // 7
W = LEFT + NW * (CELL + GAP) + 6
H = TOP + 7 * (CELL + GAP) + 22

# timing (seconds)
REVEAL, DUR = 3.6, 0.55
maxorder = (NW - 1) + 6 * 0.55

rects, labels = [], []
sd = datetime.date.fromisoformat(days[0]["date"])
last_m = None
for wk in range(NW):
    d = sd + datetime.timedelta(days=wk * 7)
    if d.month != last_m:
        last_m = d.month
        labels.append(f'<text class="lbl" x="{LEFT+wk*(CELL+GAP)}" y="{TOP-8}">{MONTHS[d.month-1]}</text>')
for name, r in [("Mon", 1), ("Wed", 3), ("Fri", 5)]:
    labels.append(f'<text class="lbl" x="2" y="{TOP+r*(CELL+GAP)+CELL-2}">{name}</text>')

for i, c in enumerate(days):
    wk, row, lvl = i // 7, i % 7, c["level"]
    x = LEFT + wk * (CELL + GAP)
    y = TOP + row * (CELL + GAP)
    delay = round((wk + row * 0.55) / maxorder * REVEAL, 3)
    cls = "c g" if lvl >= 1 else "c e"
    rects.append(
        f'<rect class="{cls}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="{RAD}" '
        f'fill="{COLORS[lvl]}" style="animation-delay:{delay}s"/>'
    )

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">
<style>
  text.lbl {{ fill:{GRAY}; font-size:13px; font-weight:600; }}
  text.total {{ fill:#e6edf3; font-size:15px; font-weight:700; }}
  .c {{ transform-box:fill-box; transform-origin:center; opacity:0; animation:pop {DUR}s ease-out both; }}
  .g {{ animation:pop {DUR}s ease-out both, flash {DUR+0.15}s ease-out both; }}
  @keyframes pop {{ 0%{{opacity:0;transform:scale(.2)}} 60%{{opacity:1;transform:scale(1.1)}} 100%{{opacity:1;transform:scale(1)}} }}
  @keyframes flash {{ 0%{{filter:brightness(2.4)}} 45%{{filter:brightness(2.4)}} 100%{{filter:brightness(1)}} }}
  @media (prefers-reduced-motion: reduce) {{ .c {{ opacity:1 !important; animation:none !important; }} }}
</style>
<rect width="{W}" height="{H}" fill="none"/>
{''.join(labels)}
{''.join(rects)}
<text class="total" x="{LEFT}" y="{H-6}">{total:,} contributions in the last year</text>
</svg>'''

open(OUT, "w").write(svg)
print(f"Wrote {OUT}: {n} days, {total:,} contributions, {len(svg)//1024} KB")
