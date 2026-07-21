"""
Build the neofetch-style info card SVG that sits to the RIGHT of the ASCII
portrait: a hand-authored resume (research, highlights) fused with LIVE GitHub
stats read from data/stats.json (contributions, active days, uptime, a
top-languages bar, and a real lines-of-code figure).

The resume prose leads; the live numbers are texture. Rows fade/slide in on a
short stagger so the panel prints alongside the portrait. STATIC=1 emits the
frozen state for Quick Look previews. Regenerated daily by the workflow so the
live values stay fresh.
"""
import html
import json
import os

from theme import get_theme

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "info-card.svg")
STATS_PATH = os.path.join(HERE, "..", "data", "stats.json")
LOC_PATH = os.path.join(HERE, "..", "get-loc", "loc.json")
STATIC = bool(os.environ.get("STATIC"))

W = 480
PAD = 20
TITLEBAR_H = 30
KEY_X = PAD
VAL_X = PAD + 78
LINE_H = 20.5

T = get_theme()
BG = T["bg"]
BG2 = T["bg2"]
FRAME = T["frame"]
MUTED = T["muted"]
INK = T["ink"]
KEY = T["key"]          # kv keys
SECTION = T["section"]  # section headers
GREEN = T["bullet"]     # bullet dots
ACCENT = T["host"]      # "github" in the host line
USER_C = T["user"]      # handle in the host line
AT_C = T["at"]          # the "@"
DOTS = T["dots"]        # traffic-light dots

HANDLE = "ritessshhh"

# GitHub linguist-ish colors for the language bar; unknown -> palette fallback.
LANG_COLORS = {
    "Python": "#3572A5", "Swift": "#F05138", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "C": "#555555", "C++": "#f34b7d", "C#": "#178600",
    "Java": "#b07219", "Kotlin": "#A97BFF", "Go": "#00ADD8", "Ruby": "#701516",
    "Rust": "#dea584", "ShaderLab": "#4b6f8c", "Scala": "#c22d40", "OCaml": "#ef7a08",
    "Shell": "#89e051",
}
FALLBACK = ["#58a6ff", "#3fb950", "#ffa657", "#f778ba", "#a5d6ff", "#d2a8ff"]
ABBREV = {"JavaScript": "JS", "TypeScript": "TS", "Jupyter Notebook": "Notebook"}


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def n(x):
    try:
        return f"{int(x):,}"
    except (TypeError, ValueError):
        return "-"


S = load_json(STATS_PATH)
LOC = load_json(LOC_PATH)          # get-loc/loc.json (run get-loc/get-loc.py)
cal = S.get("calendar") or {}
streaks = S.get("streaks") or {}
best = S.get("best_day") or {}
prof = S.get("profile") or {}
act = S.get("activity") or {}

# LOC total from cloc (get-loc.py), datasets already excluded -> the big number.
code_lines = LOC.get("total_code")

# language bar uses GitHub Linguist's byte data (stats.json): linguist already
# drops VENDORED/generated code, so a repo's bundled TypeScript doesn't swamp
# the bar -> an honest polyglot spread with Python on top. (The cloc total above
# still counts everything, per "exclude in langs but keep in loc".)
langs = (S.get("languages") or [])[:6]

age = (prof.get("account_age") or {}).get("text", "—")
total = cal.get("total", 0)
active = S.get("active_days", 0)
best_c = best.get("count", 0)

# ---- content model --------------------------------------------------------
# ("host",)                 -> handle + rule
# ("kv", key, value)        -> orange key + light value
# ("sec", title)            -> blue "— title —" rule
# ("bul", text)             -> green dot + light text
# ("langbar",)              -> stacked language bar + legend (uses live data)
# ("gap",)                  -> vertical space
ROWS = [
    ("host",),
    ("kv", "whoami", "Ritesh Chavan · CS @ Stony Brook '25"),
    ("kv", "Focus", "ML · LLMs · Multimodal AI · Security"),
    ("kv", "Uptime", f"{age} on GitHub · {n(active)} active days/yr"),
    ("langbar",),
    ("gap",),
    ("sec", "Research"),
    ("bul", "Stanford — AirBlender · LayoutVLM"),
    ("bul", "Berkeley — MFCL multimodal function-calling"),
    ("bul", "Stony Brook — SciBERT discourse classifier"),
    ("gap",),
    ("sec", "Highlights"),
    ("bul", "4 publications · AAAI'26 · NeurIPS'25 · CLEF'25"),
    ("bul", "3× hackathon winner · Ex-President, SBCS"),
    ("gap",),
    ("sec", "Activity (live)"),
    ("bul", f"{n(total)} contribs/yr · peak {n(best_c)} · \U0001f525 {n(active)} active days"),
]
# lines-of-code line: the real cloc total from get-loc/loc.json (datasets
# excluded). If get-loc.py hasn't run / loc.json isn't committed, fall back to
# the commits/PRs/reviews breakdown -- NEVER the misleading additions/deletions
# churn, which counts vendored code and reads in the millions.
if code_lines:
    ROWS.append(("bul", f"{n(code_lines)} lines of code written"))
elif act.get("commits"):
    ROWS.append(("bul", f"{n(act['commits'])} commits · {n(act.get('prs'))} PRs · {n(act.get('reviews'))} reviews"))


def esc(s):
    # ASCII-only output: turn ·, —, ×, emoji, etc. into numeric character
    # references so the SVG is immune to whatever encoding the CI runner writes
    # with (a UTF-8 mismatch on the runner is what produced "Â·" / "ð¥").
    return html.escape(str(s)).encode("ascii", "xmlcharrefreplace").decode("ascii")


def rise(inner, i):
    if STATIC:
        return f"<g>{inner}</g>"
    delay = 0.15 + i * 0.055
    return (f'<g opacity="0" transform="translate(0,5)">{inner}'
            f'<animate attributeName="opacity" from="0" to="1" begin="{delay:.2f}s" dur="0.4s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" from="0 5" to="0 0" '
            f'begin="{delay:.2f}s" dur="0.4s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1"/></g>')


def lang_color(name, i):
    return LANG_COLORS.get(name, FALLBACK[i % len(FALLBACK)])


def render_langbar(y):
    """Stacked proportional bar (line 1) + a compact legend (line 2)."""
    if not langs:
        inner = (f'<text x="{KEY_X}" y="{y:.1f}" fill="{KEY}" font-size="12.5" font-weight="700">Langs</text>'
                 f'<text x="{VAL_X}" y="{y:.1f}" fill="{MUTED}" font-size="12.5">updates on deploy</text>')
        return inner, 1
    bx, bw, bh = VAL_X, (W - PAD) - VAL_X, 9
    by = y - 10
    tot = sum(l["pct"] for l in langs) or 1
    segs, cx = [], bx
    for i, l in enumerate(langs):
        w = bw * l["pct"] / tot
        segs.append(f'<rect x="{cx:.1f}" y="{by:.1f}" width="{w:.1f}" height="{bh}" fill="{lang_color(l["name"], i)}"/>')
        cx += w
    bar = (f'<clipPath id="lb"><rect x="{bx}" y="{by:.1f}" width="{bw}" height="{bh}" rx="4.5"/></clipPath>'
           f'<g clip-path="url(#lb)">{"".join(segs)}</g>')
    label = f'<text x="{KEY_X}" y="{y:.1f}" fill="{KEY}" font-size="12.5" font-weight="700">Langs</text>'
    # legend line
    lx, ly = KEY_X, y + LINE_H - 4
    legend = []
    for i, l in enumerate(langs):
        nm = ABBREV.get(l["name"], l["name"])
        legend.append(f'<rect x="{lx:.1f}" y="{ly-8:.1f}" width="8" height="8" rx="2" fill="{lang_color(l["name"], i)}"/>')
        legend.append(f'<text x="{lx+12:.1f}" y="{ly:.1f}" fill="{INK}" font-size="11">{esc(nm)}</text>')
        lx += 12 + len(nm) * 6.6 + 12
    return label + bar + "".join(legend), 2


# ---- assemble -------------------------------------------------------------
body = []
y = TITLEBAR_H + 30
i = 0
for row in ROWS:
    kind = row[0]
    if kind == "gap":
        y += LINE_H * 0.5
        continue
    if kind == "host":
        inner = (f'<text x="{KEY_X}" y="{y:.1f}" font-size="14" font-weight="700">'
                 f'<tspan fill="{USER_C}">{HANDLE}</tspan><tspan fill="{AT_C}">@</tspan>'
                 f'<tspan fill="{ACCENT}">github</tspan></text>'
                 f'<line x1="{KEY_X+len(HANDLE)*8+58}" y1="{y-4:.1f}" x2="{W-PAD}" y2="{y-4:.1f}" '
                 f'stroke="{FRAME}" stroke-opacity="0.8"/>')
        rows_used = 1
    elif kind == "langbar":
        inner, rows_used = render_langbar(y)
    elif kind == "sec":
        title = esc(row[1])
        inner = (f'<text x="{KEY_X}" y="{y:.1f}" fill="{SECTION}" font-size="12.5" font-weight="700">'
                 f'&#8212; {title}</text>'
                 f'<line x1="{KEY_X + 14 + len(row[1])*7.2:.0f}" y1="{y-4:.1f}" x2="{W-PAD}" y2="{y-4:.1f}" '
                 f'stroke="{FRAME}" stroke-opacity="0.8"/>')
        rows_used = 1
    elif kind == "kv":
        inner = (f'<text x="{KEY_X}" y="{y:.1f}" fill="{KEY}" font-size="12.5" font-weight="700">{esc(row[1])}</text>'
                 f'<text x="{VAL_X}" y="{y:.1f}" fill="{INK}" font-size="12.5">{esc(row[2])}</text>')
        rows_used = 1
    elif kind == "bul":
        inner = (f'<circle cx="{KEY_X+3}" cy="{y-4:.1f}" r="2.5" fill="{GREEN}"/>'
                 f'<text x="{KEY_X+14}" y="{y:.1f}" fill="{INK}" font-size="12.5">{esc(row[1])}</text>')
        rows_used = 1
    else:
        continue
    body.append(rise(inner, i))
    y += LINE_H * rows_used
    i += 1

H = int(y + PAD - LINE_H * 0.3)

head = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
    f'font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
    '<defs>'
    f'<linearGradient id="ibg" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/></linearGradient></defs>',
    f'<rect width="{W}" height="{H}" rx="12" fill="url(#ibg)"/>',
    f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="12" fill="none" stroke="{FRAME}"/>',
    f'<line x1="0" y1="{TITLEBAR_H}" x2="{W}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>',
]
for k, dotcol in enumerate(DOTS):
    head.append(f'<circle cx="{PAD + k*16}" cy="{TITLEBAR_H/2}" r="5" fill="{dotcol}"/>')
head.append(f'<text x="{W/2}" y="{TITLEBAR_H/2 + 4}" fill="{MUTED}" font-size="12" '
            f'text-anchor="middle">{HANDLE}@github: ~$ neofetch</text>')

svg = "".join(head + body + ["</svg>"])
with open(OUT, "w", encoding="utf-8") as f:
    f.write(svg)
print("wrote", OUT, len(svg), "bytes;", W, "x", H)
