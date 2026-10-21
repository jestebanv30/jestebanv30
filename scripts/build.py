#!/usr/bin/env python3
"""Generate the static, animated profile SVGs from profile.json.

Run from anywhere:
    python scripts/build.py

Writes dark and light variants of: header, about, stack, projects and footer.
The GitHub stats cards are generated separately by scripts/stats.py.
"""

from __future__ import annotations

import math
import re

from svgkit import (
    ASSETS,
    Svg,
    colombia_flag,
    fmt,
    load_profile,
    measure,
    pulse_dot,
    rounded_rect_perimeter,
    wrap,
)

THEMES = ("dark", "light")

INTRO_CSS = (
    "@keyframes up{from{opacity:0;transform:translateY(14px)}}"
    ".up{animation:up .9s cubic-bezier(.2,.7,.2,1) both}"
    "@keyframes pop{from{opacity:0;transform:scale(.8)}}"
    ".pop{transform-box:fill-box;transform-origin:center;animation:pop .9s cubic-bezier(.2,.8,.2,1.2) both}"
    "@keyframes blink{50%{opacity:0}}"
    ".blink{animation:blink 1s step-end infinite}"
    "@keyframes fl{to{transform:translateY(-3px)}}"
    ".fl{animation:fl 3.2s ease-in-out infinite alternate}"
)


def color(t: dict, value: str) -> str:
    """profile.json colors are either theme keys (a1, gold, text...) or hex."""
    return t.get(value, value) if not value.startswith("#") else value


def rotate(cx: float, cy: float, dur: float, reverse: bool = False) -> str:
    a, b = (360, 0) if reverse else (0, 360)
    return (
        f'<animateTransform attributeName="transform" type="rotate" from="{a} {fmt(cx)} {fmt(cy)}" '
        f'to="{b} {fmt(cx)} {fmt(cy)}" dur="{dur}s" repeatCount="indefinite"/>'
    )


def discrete(attr: str, events: list[tuple[float, str]], total: float, repeat: bool, kind: str = "animate") -> str:
    """A step animation from (time, value) events, used for typing effects."""
    keys, vals = [], []
    for time, value in events:
        k = round(time / total, 5)
        if keys and k <= keys[-1]:
            vals[-1] = value  # same instant: keep the newest value
            continue
        if not keys and k > 0:
            keys.append(0.0)
            vals.append(events[0][1])
        keys.append(k)
        vals.append(value)
    tag = "animateTransform" if kind == "translate" else "animate"
    typ = ' type="translate"' if kind == "translate" else ""
    rep = 'repeatCount="indefinite"' if repeat else 'fill="freeze"'
    return (
        f'<{tag} attributeName="{attr}"{typ} calcMode="discrete" dur="{fmt(total)}s" {rep} '
        f'keyTimes="{";".join(fmt(k) if k else "0" for k in keys)}" values="{";".join(vals)}"/>'
    )


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
def header(p: dict, theme: str) -> Svg:
    W, H = 1200, 420
    svg = Svg(W, H, theme, f"{p['name']} · {p['roles'][0]}", "Animated profile banner")
    t, g = svg.t, svg.t["glow"]
    svg.css.append(INTRO_CSS)

    bg = svg.linear("bg", [(0, t["bg"], 1), (1, t["bg2"], 1)], 0, 0, 1, 1)
    svg.defs.append(f'<clipPath id="card"><rect width="{W}" height="{H}" rx="22"/></clipPath>')
    svg.add(f'<rect width="{W}" height="{H}" rx="22" fill="{bg}"/>', '<g clip-path="url(#card)">')

    # Aurora blobs drifting behind everything
    svg.css.append(
        "@keyframes d1{to{transform:translate(110px,50px)}}"
        "@keyframes d2{to{transform:translate(-130px,-40px)}}"
        "@keyframes d3{to{transform:translate(-70px,60px)}}"
    )
    for i, (cx, cy, r, c, op, anim) in enumerate(
        [
            (150, 30, 380, t["a2"], 0.30, "d1 21s"),
            (1080, 410, 400, t["a1"], 0.20, "d2 25s"),
            (700, -40, 300, t["a3"], 0.18, "d3 18s"),
        ]
    ):
        fill = svg.radial(f"blob{i}", c, op * g)
        svg.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" style="animation:{anim} ease-in-out infinite alternate"/>')

    # Dot grid, fading out towards the text
    svg.defs.append(
        f'<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">'
        f'<circle cx="2" cy="2" r="1" fill="{t["faint"]}"/></pattern>'
        '<radialGradient id="fade" cx=".8" cy=".5" r=".55"><stop offset="0" stop-color="#fff" stop-opacity=".9"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="gridmask"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>'
    )
    svg.add(f'<rect width="{W}" height="{H}" fill="url(#dots)" mask="url(#gridmask)" opacity=".6"/>')

    # Shooting stars
    svg.css.append(
        "@keyframes shoot{0%{transform:translate(0,0);opacity:0}2%{opacity:1}"
        "10%{transform:translate(420px,150px);opacity:0}100%{transform:translate(420px,150px);opacity:0}}"
    )
    star = svg.linear("star", [(0, t["text"], 0), (1, t["text"], 0.9)])
    for x, y, delay in [(560, 24, 3), (240, 300, 9.5)]:
        svg.add(
            f'<g style="animation:shoot 13s linear {delay}s infinite both">'
            f'<line x1="{x - 90}" y1="{y - 32}" x2="{x}" y2="{y}" stroke="{star}" stroke-width="1.6" stroke-linecap="round"/></g>'
        )

    # ---- Left column: greeting, name, typing roles, chips -------------------
    x0 = 84
    svg.add(
        f'<g class="up" style="animation-delay:.1s">'
        f'<line x1="{x0}" y1="113" x2="{x0 + 34}" y2="113" stroke="{t["a1"]}" stroke-width="2" stroke-linecap="round"/>'
        + svg.text(x0 + 46, 118.5, p["greeting"], "mono", 700, 15, t["a1"], ls=3)
        + "</g>"
    )

    size = 66.0
    while measure(p["name"], "sans", 700, size, -1) > 650:
        size -= 1
    name_w = measure(p["name"], "sans", 700, size, -1)
    svg.linear(
        "gname",
        [(0, t["text"], 1), (0.35, t["text"], 1), (0.62, t["a1"], 1), (0.82, t["a2"], 1), (1, t["a3"], 1)],
        x0,
        0,
        x0 + name_w,
        0,
        'gradientUnits="userSpaceOnUse" spreadMethod="reflect"',
        f'<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="{fmt(2 * name_w)} 0" '
        f'dur="16s" repeatCount="indefinite"/>',
    )
    svg.add(
        '<g class="up" style="animation-delay:.25s">'
        + svg.text(x0 - 3, 192, p["name"], "sans", 700, size, "url(#gname)", ls=-1)
        + "</g>"
    )

    # Typing roles: one clip per role, widths stepped by SMIL
    fs, ty = 24, 252
    cw = measure("a", "mono", 400, fs)
    tx = x0 + 32
    events, now = [], 0.0
    for i, role in enumerate(p["roles"]):
        n = len(role)
        for c in range(n + 1):
            events.append((now, i, c))
            now += 0.055 if c < n else 0
        now += 2.0
        for c in range(n - 1, -1, -1):
            now += 0.024
            events.append((now, i, c))
        now += 0.4
    total = now

    role_markup = []
    for i, role in enumerate(p["roles"]):
        evs = [(0.0, "0")] + [(tm, fmt(c * cw + 3) if c else "0") for tm, r, c in events if r == i]
        full = len(role) * cw + 3
        anim = discrete("width", evs, total, repeat=True)
        svg.defs.append(
            f'<clipPath id="role{i}"><rect x="{fmt(tx - 2)}" y="{ty - 30}" height="44" '
            f'width="{fmt(full if i == 0 else 0)}">{anim}</rect></clipPath>'
        )
        role_markup.append(svg.text(tx, ty, role, "mono", 400, fs, t["text"], attrs=f'clip-path="url(#role{i})"'))
    cursor_events = [(tm, f"{fmt(c * cw)} 0") for tm, _, c in events]
    first_w = len(p["roles"][0]) * cw
    svg.add(
        '<g class="up" style="animation-delay:.45s">'
        + svg.text(x0, ty, "❯", "mono", 700, fs, t["a2"])
        + "".join(role_markup)
        + f'<g transform="translate({fmt(first_w)} 0)">'
        + discrete("transform", cursor_events, total, repeat=True, kind="translate")
        + f'<rect class="blink" x="{fmt(tx + 2)}" y="{ty - 22}" width="3" height="28" rx="1.5" fill="{t["a1"]}"/></g>'
        + "</g>"
    )

    # Chips
    cx, cy, ch = x0, 292, 38
    for k, chip in enumerate(p["chips"]):
        tw = measure(chip["text"], "mono", 400, 14)
        if chip["icon"] == "code":
            iw = measure("</>", "mono", 700, 13)
        else:
            iw = 16
        w = 14 + iw + 10 + tw + 16
        ic_x, mid = cx + 14, cy + ch / 2
        if chip["icon"] == "pulse":
            icon = pulse_dot(svg, ic_x + 8, mid, 4.5, t["green"])
        elif chip["icon"] == "flag":
            icon = colombia_flag(svg, ic_x + 8, mid, 8)
        else:
            icon = svg.text(ic_x, mid + 4.5, "</>", "mono", 700, 13, t["a3"])
        svg.add(
            f'<g class="up" style="animation-delay:{fmt(0.65 + k * 0.1)}s">'
            f'<rect x="{fmt(cx)}" y="{cy}" width="{fmt(w)}" height="{ch}" rx="{ch / 2}" fill="{t["chip"]}" '
            f'fill-opacity=".75" stroke="{t["border2"]}"/>'
            + icon
            + svg.text(ic_x + iw + 10, mid + 5, chip["text"], "mono", 400, 14, t["text"])
            + "</g>"
        )
        cx += w + 12

    # ---- Right column: orbit system ------------------------------------------
    ox, oy, r1, r2 = 968, 212, 100, 168
    svg.css.append(
        "@keyframes breathe{to{transform:scale(1.08);opacity:.75}}"
        ".breathe{transform-box:fill-box;transform-origin:center;animation:breathe 5s ease-in-out infinite alternate}"
    )
    svg.linear("garc", [(0, t["a1"], 1), (0.5, t["a2"], 1), (1, t["a3"], 0)], 0, 0, 1, 1)
    svg.linear("gmono", [(0, t["a1"], 1), (0.55, t["a2"], 1), (1, t["a3"], 1)], 0, 0, 1, 1)
    halo = svg.radial("halo", t["a2"], 0.38 * g)
    orbit = [f'<circle class="breathe" cx="{ox}" cy="{oy}" r="160" fill="{halo}"/>']

    # Outer ring, counter-clockwise
    outer = [
        f'<circle cx="{ox}" cy="{oy}" r="{r2}" stroke="{t["border2"]}" stroke-opacity=".9" stroke-dasharray="1 7" stroke-linecap="round"/>'
    ]
    n = len(p["orbit"]["outer"])
    for i, name in enumerate(p["orbit"]["outer"]):
        a = math.radians(-90 + i * 360 / n)
        ix, iy = ox + r2 * math.cos(a), oy + r2 * math.sin(a)
        outer.append(f"<g>{rotate(ix, iy, 70)}{svg.icon(name, ix - 23, iy - 23, 46)}</g>")
        a2 = a + math.radians(180 / n)
        dot = (t["a1"], t["a2"], t["a3"])[i % 3]
        outer.append(
            f'<circle cx="{fmt(ox + r2 * math.cos(a2))}" cy="{fmt(oy + r2 * math.sin(a2))}" r="2.6" fill="{dot}"/>'
        )
    orbit.append(f"<g>{rotate(ox, oy, 70, reverse=True)}{''.join(outer)}</g>")

    # Inner ring, clockwise
    inner = [
        f'<circle cx="{ox}" cy="{oy}" r="{r1}" stroke="{t["border2"]}" stroke-dasharray="3 6" stroke-linecap="round"/>'
    ]
    n = len(p["orbit"]["inner"])
    for i, name in enumerate(p["orbit"]["inner"]):
        a = math.radians(-45 + i * 360 / n)
        ix, iy = ox + r1 * math.cos(a), oy + r1 * math.sin(a)
        inner.append(f"<g>{rotate(ix, iy, 44, reverse=True)}{svg.icon(name, ix - 21, iy - 21, 42)}</g>")
    orbit.append(f"<g>{rotate(ox, oy, 44)}{''.join(inner)}</g>")

    # Core: spinning arc + monogram
    orbit.append(
        f'<circle cx="{ox}" cy="{oy}" r="58" fill="{t["surface2"]}" stroke="{t["border2"]}"/>'
        f'<circle cx="{ox}" cy="{oy}" r="68" stroke="url(#garc)" stroke-width="2.2" stroke-linecap="round" '
        f'stroke-dasharray="130 297.3">{rotate(ox, oy, 7)}</circle>'
        + svg.text(ox, oy + 14, p["monogram"], "sans", 700, 40, "url(#gmono)", anchor="middle", ls=1)
    )
    svg.add(f'<g class="pop" style="animation-delay:.3s">{"".join(orbit)}</g>')

    # Bottom accent line
    svg.linear(
        "gline",
        [(0, t["a1"], 1), (0.33, t["a2"], 1), (0.66, t["a3"], 1), (1, t["a1"], 1)],
        0,
        0,
        W,
        0,
        'gradientUnits="userSpaceOnUse" spreadMethod="repeat"',
        f'<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="{W} 0" dur="10s" repeatCount="indefinite"/>',
    )
    svg.add(f'<rect y="{H - 3}" width="{W}" height="3" fill="url(#gline)"/>', "</g>")
    svg.add(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="21.5" stroke="{t["border"]}"/>')
    return svg


# --------------------------------------------------------------------------- #
# About: animated code editor
# --------------------------------------------------------------------------- #
SYNTAX = {
    "dark": {"kw": "#C084FC", "cls": "#22D3EE", "fn": "#818CF8", "str": "#86EFAC", "doc": "#7D8DA8",
             "com": "#5F6E87", "num": "#FBBF24", "op": "#8B98AD", "self": "#FB7185", "id": "#E6EDF3"},
    "light": {"kw": "#CF222E", "cls": "#953800", "fn": "#8250DF", "str": "#0A3069", "doc": "#57606A",
              "com": "#6E7781", "num": "#0550AE", "op": "#57606A", "self": "#0550AE", "id": "#1F2328"},
}
KEYWORDS = {"from", "import", "class", "def", "return", "if", "else", "for", "in", "None", "True", "False", "lambda"}
TOKEN = re.compile(
    r'(?P<doc>""".*?""")|(?P<str>"[^"]*")|(?P<com>#.*$)|(?P<word>[A-Za-z_][A-Za-z0-9_]*)|(?P<num>\d+)|(?P<ws>\s+)|(?P<op>.)'
)


def highlight(line: str, theme: str) -> list[tuple[str, str]]:
    c = SYNTAX[theme]
    out, prev = [], ""
    for m in TOKEN.finditer(line):
        kind, s = m.lastgroup, m.group()
        if kind == "word":
            if s in KEYWORDS:
                col = c["kw"]
            elif prev == "class" or s[0].isupper() or s in {"str", "int", "list"}:
                col = c["cls"]
            elif prev == "def":
                col = c["fn"]
            elif s == "self":
                col = c["self"]
            else:
                col = c["id"]
            prev = s
        else:
            col = {"doc": c["doc"], "str": c["str"], "com": c["com"], "num": c["num"], "ws": c["id"], "op": c["op"]}[kind]
        if out and out[-1][1] == col:
            out[-1] = (out[-1][0] + s, col)
        else:
            out.append((s, col))
    return out


def about(p: dict, theme: str) -> Svg:
    lines = p["about"]["code"]
    fs, lh = 16, 27
    cw = measure("a", "mono", 400, fs)
    W = 920
    bar, pad_t, pad_b, status = 46, 22, 18, 30
    H = bar + pad_t + len(lines) * lh + pad_b + status
    svg = Svg(W, H, theme, "about_me.py", "Animated code editor describing Juan Esteban")
    t = svg.t
    editor = "#0D1322" if theme == "dark" else "#FFFFFF"
    svg.css.append(INTRO_CSS + ".code{white-space:pre}")

    svg.defs.append(f'<clipPath id="win"><rect width="{W}" height="{H}" rx="14"/></clipPath>')
    parts = [f'<rect width="{W}" height="{H}" rx="14" fill="{editor}"/>', '<g clip-path="url(#win)">']

    # Title bar with traffic lights and the active tab
    parts.append(f'<rect width="{W}" height="{bar}" fill="{t["surface2"]}"/>')
    parts.append(f'<line x1="0" y1="{bar - 0.5}" x2="{W}" y2="{bar - 0.5}" stroke="{t["border"]}"/>')
    for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
        parts.append(f'<circle cx="{22 + i * 20}" cy="23" r="6" fill="{c}"/>')
    tab_x = 92
    label = p["about"]["file"]
    tab_w = 16 + 16 + 8 + measure(label, "mono", 400, 13) + 28
    parts.append(
        f'<path d="M{tab_x} {bar}V18a8 8 0 0 1 8-8h{fmt(tab_w - 16)}a8 8 0 0 1 8 8V{bar}z" fill="{editor}" stroke="{t["border"]}"/>'
        f'<rect x="{tab_x}" y="{bar - 1}" width="{fmt(tab_w)}" height="2" fill="{editor}"/>'
        f'<path d="M{tab_x + 8} 10.5h{fmt(tab_w - 16)}" stroke="{t["a1"]}" stroke-width="2" stroke-linecap="round"/>'
        + svg.icon("python", tab_x + 14, 20, 16)
        + svg.text(tab_x + 38, 32.5, label, "mono", 400, 13, t["text"])
        + svg.text(tab_x + tab_w - 18, 32.5, "×", "mono", 400, 14, t["faint"])
    )
    parts.append(svg.text(W - 20, 32.5, f"~/{p['username']}", "mono", 400, 12, t["faint"], anchor="end"))

    # Code, line numbers and the typing overlays
    code_x, num_x = 84, 54
    top = bar + pad_t
    start, schedule, overlays = 0.7, [], []
    for i, line in enumerate(lines):
        y = top + i * lh
        base = y + lh / 2 + fs * 0.36
        parts.append(svg.text(num_x, base, str(i + 1), "mono", 400, 13.5, t["faint"], anchor="end"))
        runs = [(s, col, 400) for s, col in highlight(line, theme)]
        if runs:
            parts.append(svg.runs(code_x, base, runs, "mono", fs, cls="code", attrs='xml:space="preserve"'))
        indent = len(line) - len(line.lstrip(" "))
        n = len(line) - indent
        dur = n * 0.012 if n else 0
        schedule.append((start, dur, indent, n, y))
        if n:
            ox = code_x + indent * cw
            ow = W - ox
            tw = n * cw
            overlays.append(
                f'<rect x="{fmt(ox)}" y="{y}" width="{fmt(ow)}" height="{lh}" fill="{editor}" '
                f'style="transform:translateX({fmt(ow)}px);animation:t{i} {fmt(dur)}s steps({n + 1},end) {fmt(start)}s both"/>'
            )
            # One extra step: Chrome can stop a step short at the end of a steps() animation
            svg.css.append(f"@keyframes t{i}{{from{{transform:translateX(0)}}to{{transform:translateX({fmt(tw + cw)}px)}}}}")
        start += dur + (0.1 if n else 0.06)
    parts.extend(overlays)

    # One cursor and current-line band that follow the typing
    events, band = [], []
    for s, dur, indent, n, y in schedule:
        x = code_x + indent * cw
        events.append((s, f"{fmt(x)} {y}"))
        band.append((s, f"0 {y}"))
        for k in range(1, n + 1):
            events.append((s + k * dur / (n + 1), f"{fmt(x + k * cw)} {y}"))
    total = start
    s, dur, indent, n, y = schedule[-1]
    end_x = code_x + (indent + n) * cw
    parts.append(
        f'<g transform="translate(0 {y})">{discrete("transform", band, total, False, "translate")}'
        f'<rect width="{W}" height="{lh}" fill="{t["a2"]}" fill-opacity=".07"/>'
        f'<rect width="2" height="{lh}" fill="{t["a2"]}" fill-opacity=".8"/></g>'
        f'<g transform="translate({fmt(end_x)} {y})">{discrete("transform", events, total, False, "translate")}'
        f'<rect class="blink" x="1" y="4" width="2.5" height="{lh - 8}" rx="1" fill="{t["a1"]}"/></g>'
    )

    # Status bar
    sy = H - status
    branch_w = 96
    parts.append(
        f'<rect y="{sy}" width="{W}" height="{status}" fill="{t["surface2"]}"/>'
        f'<line x1="0" y1="{sy + 0.5}" x2="{W}" y2="{sy + 0.5}" stroke="{t["border"]}"/>'
        f'<rect y="{sy}" width="{branch_w}" height="{status}" fill="{t["a2"]}"/>'
        # git branch glyph
        f'<g stroke="#fff" stroke-width="1.6" fill="none" stroke-linecap="round">'
        f'<circle cx="20" cy="{sy + 9}" r="2.2"/><circle cx="20" cy="{sy + 21}" r="2.2"/>'
        f'<circle cx="30" cy="{sy + 11}" r="2.2"/><path d="M20 {sy + 11.2}v7.6M30 {sy + 13.2}c0 4-10 2-10 5.6"/></g>'
        + svg.text(40, sy + 19.5, "main", "mono", 700, 12, "#FFFFFF")
        + svg.text(branch_w + 16, sy + 19.5, f"Ln {len(lines)}, Col {len(lines[-1]) + 1}", "mono", 400, 12, t["muted"])
        + svg.text(W - 18, sy + 19.5, "Python 3.12 · UTF-8 · LF · Spaces: 4", "mono", 400, 12, t["muted"], anchor="end")
    )
    parts.append("</g>")
    parts.append(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="13.5" stroke="{t["border2"]}"/>')
    svg.add(f'<g class="up">{"".join(parts)}</g>')
    return svg


# --------------------------------------------------------------------------- #
# Tech stack
# --------------------------------------------------------------------------- #
def stack(p: dict, theme: str) -> Svg:
    cats = p["stack"]
    W, pw, ph, gx, gy = 1000, 488, 168, 24, 20
    rows = math.ceil(len(cats) / 2)
    H = rows * ph + (rows - 1) * gy + 2
    svg = Svg(W, H, theme, "Tech stack", "Languages, frameworks and tools Juan Esteban works with")
    t = svg.t
    svg.css.append(INTRO_CSS + "@keyframes sweep{to{transform:translateX(330px)}}")
    slot, size = 76, 50
    for i, cat in enumerate(cats):
        x, y = 1 + (i % 2) * (pw + gx), 1 + (i // 2) * (ph + gy)
        col = color(t, cat["color"])
        shine = svg.linear(f"sh{i}", [(0, col, 0), (0.5, col, 1), (1, col, 0)])
        d0 = 0.1 + i * 0.1
        items = []
        for j, (icon, label) in enumerate(cat["items"]):
            sx = x + 22 + j * slot
            items.append(
                f'<g class="pop" style="animation-delay:{fmt(d0 + 0.25 + j * 0.07)}s">'
                f'<g class="fl" style="animation-delay:-{fmt((i * 7 + j * 3) % 11 * 0.37)}s">'
                + svg.icon(icon, sx + (slot - size) / 2, y + 60, size)
                + "</g>"
                + svg.text(sx + slot / 2, y + 60 + size + 22, label, "mono", 400, 11, t["muted"], anchor="middle")
                + "</g>"
            )
        svg.add(
            f'<g class="up" style="animation-delay:{fmt(d0)}s">'
            f'<rect x="{x}" y="{y}" width="{pw}" height="{ph}" rx="16" fill="{t["surface"]}" stroke="{t["border"]}"/>'
            f'<rect x="{x + 40}" y="{y - 0.75}" width="90" height="1.5" fill="{shine}" '
            f'style="animation:sweep 5s ease-in-out {fmt(i * 0.8)}s infinite alternate"/>'
            f'<circle cx="{x + 28}" cy="{y + 34}" r="4" fill="{col}"/>'
            f'<circle cx="{x + 28}" cy="{y + 34}" r="8" fill="{col}" fill-opacity=".18"/>'
            + svg.text(x + 44, y + 40, cat["title"], "sans", 700, 17, t["text"])
            + svg.text(x + pw - 24, y + 39, f"{i + 1:02d}", "mono", 400, 12, t["faint"], anchor="end")
            + "".join(items)
            + "</g>"
        )
    return svg


# --------------------------------------------------------------------------- #
# Project cards
# --------------------------------------------------------------------------- #
def art(svg: Svg, kind: str, cx: float, cy: float, c: str) -> str:
    t = svg.t
    if kind == "planet":
        pg = svg.linear("planet", [(0, t["a1"], 1), (1, c, 1)], 0, 0, 1, 1)
        orbit_path = f"M{cx - 38} {cy}a38 11 0 1 0 76 0a38 11 0 1 0 -76 0"
        svg.css.append("@keyframes tw{50%{opacity:.15}}")
        stars = "".join(
            f'<circle cx="{cx + dx}" cy="{cy + dy}" r="{r}" fill="{t["text"]}" style="animation:tw {d}s ease-in-out infinite"/>'
            for dx, dy, r, d in [(-34, -26, 1.3, 2.6), (30, -30, 1, 3.4), (36, 24, 1.2, 2.2), (-26, 28, 0.9, 3.1)]
        )
        return (
            stars
            + f'<g transform="rotate(-18 {cx} {cy})">'
            f'<path d="M{cx - 38} {cy}a38 11 0 0 1 76 0" stroke="{c}" stroke-opacity=".55" stroke-width="2"/>'
            f'<circle cx="{cx}" cy="{cy}" r="20" fill="{pg}"/>'
            f'<path d="M{cx - 38} {cy}a38 11 0 0 0 76 0" stroke="{c}" stroke-width="2"/>'
            f'<circle r="4" fill="{t["text"]}"><animateMotion dur="7s" repeatCount="indefinite" path="{orbit_path}"/></circle>'
            "</g>"
        )
    if kind == "scan":
        svg.css.append(
            "@keyframes scan{from{transform:translateY(0)}to{transform:translateY(60px)}}"
            "@keyframes mark{0%,30%{opacity:0}45%,100%{opacity:1}}"
        )
        x0, y0 = cx - 24, cy - 28
        bubbles = []
        filled = {(0, 1), (1, 3), (2, 0), (3, 2), (4, 1)}
        for row in range(5):
            for col in range(4):
                bx, by = x0 + col * 16, y0 + row * 14
                bubbles.append(f'<circle cx="{bx}" cy="{by}" r="4.6" stroke="{t["faint"]}" stroke-width="1.2"/>')
                if (row, col) in filled:
                    bubbles.append(
                        f'<circle cx="{bx}" cy="{by}" r="3.6" fill="{c}" '
                        f'style="animation:mark 4.8s linear {fmt(row * 0.35)}s infinite"/>'
                    )
        corners = "".join(
            f'<path d="M{fmt(px)} {fmt(py + 9 * sy)}V{fmt(py)}H{fmt(px + 9 * sx)}" stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
            for px, py, sx, sy in [
                (cx - 36, cy - 40, 1, 1),
                (cx + 36, cy - 40, -1, 1),
                (cx - 36, cy + 40, 1, -1),
                (cx + 36, cy + 40, -1, -1),
            ]
        )
        beam = svg.linear("beam", [(0, c, 0), (0.5, c, 1), (1, c, 0)])
        return (
            "".join(bubbles)
            + corners
            + f'<g style="animation:scan 2.4s ease-in-out infinite alternate">'
            f'<rect x="{cx - 34}" y="{cy - 31}" width="68" height="2" rx="1" fill="{beam}"/></g>'
        )
    if kind == "bars":
        svg.css.append(
            "@keyframes grow{from{transform:scaleY(.35)}}"
            ".bar{transform-box:fill-box;transform-origin:50% 100%;animation:grow 1.6s ease-in-out infinite alternate}"
        )
        heights = [26, 40, 32, 54, 46]
        base = cy + 30
        bars = "".join(
            f'<rect class="bar" style="animation-delay:-{fmt(i * 0.45)}s" x="{cx - 36 + i * 15}" y="{base - h}" '
            f'width="10" height="{h}" rx="2.5" fill="{c}" fill-opacity="{fmt(0.45 + i * 0.12)}"/>'
            for i, h in enumerate(heights)
        )
        spark = (
            f'<path class="breathe2" d="M{cx + 30} {cy - 40}l3 7 7 3-7 3-3 7-3-7-7-3 7-3z" fill="{t["text"]}"/>'
        )
        svg.css.append(
            "@keyframes twinkle{50%{transform:scale(.5) rotate(45deg);opacity:.4}}"
            ".breathe2{transform-box:fill-box;transform-origin:center;animation:twinkle 2.6s ease-in-out infinite}"
        )
        return f'<line x1="{cx - 40}" y1="{base + 0.5}" x2="{cx + 40}" y2="{base + 0.5}" stroke="{t["faint"]}"/>' + bars + spark
    if kind == "hexagon":
        def hexagon(r: float) -> tuple[str, list[tuple[float, float]]]:
            pts = [(cx + r * math.cos(math.radians(60 * k - 90)), cy + r * math.sin(math.radians(60 * k - 90))) for k in range(6)]
            return "M" + "L".join(f"{fmt(x)} {fmt(y)}" for x, y in pts) + "Z", pts

        outer_d, pts = hexagon(36)
        inner_d, _ = hexagon(20)
        svg.css.append(
            "@keyframes port{0%,100%{opacity:.35}50%{opacity:1}}"
        )
        nodes = "".join(
            f'<circle cx="{fmt(x)}" cy="{fmt(y)}" r="4" fill="{c}" style="animation:port 3s ease-in-out {fmt(k * 0.5)}s infinite"/>'
            for k, (x, y) in enumerate(pts)
        )
        return (
            f'<path d="{outer_d}" stroke="{c}" stroke-opacity=".6" stroke-width="1.6"/>'
            f'<path d="{inner_d}" stroke="{t["muted"]}" stroke-dasharray="4 4" stroke-width="1.4">{rotate(cx, cy, 14)}</path>'
            f'<circle cx="{cx}" cy="{cy}" r="7" fill="{c}"/>' + nodes
        )
    return ""


REPO_ICON = (
    "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7"
    ".75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1"
    " .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z"
)


def project_card(p: dict, proj: dict, theme: str) -> Svg:
    W, H = 480, 250
    svg = Svg(W, H, theme, proj["title"], proj["description"])
    t, g = svg.t, svg.t["glow"]
    c = color(t, proj["color"])
    svg.css.append(INTRO_CSS)
    svg.defs.append(f'<clipPath id="card"><rect width="{W}" height="{H}" rx="16"/></clipPath>')
    glow = svg.radial("glow", c, 0.22 * g)
    svg.add(
        f'<rect width="{W}" height="{H}" rx="16" fill="{t["surface"]}"/>',
        f'<g clip-path="url(#card)"><circle cx="{W - 40}" cy="40" r="200" fill="{glow}"/></g>',
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="15.5" stroke="{t["border"]}"/>',
    )
    # A light beam running around the border
    per = rounded_rect_perimeter(W - 1.5, H - 1.5, 15.25)
    beam = svg.linear("beam_b", [(0, t["a1"], 1), (0.5, c, 1), (1, t["a3"], 1)], 0, 0, 1, 1)
    svg.css.append(f"@keyframes run{{to{{stroke-dashoffset:-{fmt(per)}}}}}")
    svg.add(
        f'<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="15.25" stroke="{beam}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-dasharray="110 {fmt(per - 110)}" style="animation:run 7s linear infinite"/>'
    )

    body = []
    repo = f"{p['username']}/{proj['repo']}"
    body.append(
        f'<path transform="translate(24 24)" fill="{t["muted"]}" d="{REPO_ICON}"/>'
        + svg.text(48, 37, repo, "mono", 400, 12.5, t["muted"])
    )
    if proj.get("demo"):
        badge, bcol = "LIVE DEMO", t["green"]
    else:
        badge, bcol = proj.get("badge", "OPEN SOURCE"), c
    bw = measure(badge, "mono", 700, 10.5, 1) + 34
    bx = W - 24 - bw
    body.append(
        f'<rect x="{fmt(bx)}" y="20" width="{fmt(bw)}" height="24" rx="12" fill="{bcol}" fill-opacity=".1" stroke="{bcol}" stroke-opacity=".35"/>'
        + pulse_dot(svg, bx + 14, 32, 3.5, bcol)
        + svg.text(bx + 24, 36, badge, "mono", 700, 10.5, bcol, ls=1)
    )

    size = 24.0
    while measure(proj["title"], "sans", 700, size) > 350:
        size -= 0.5
    body.append(svg.text(24, 86, proj["title"], "sans", 700, size, t["text"]))
    lines = wrap(proj["description"], 328, kind="sans", weight=400, size=15)
    if len(lines) > 3:
        print(f"  ! {proj['slug']}: description needs {len(lines)} lines, only 3 fit; shorten it")
    for k, line in enumerate(lines[:3]):
        body.append(svg.text(24, 118 + k * 22, line, "sans", 400, 15, t["muted"]))

    x = 24.0
    for k, (tag, tcol) in enumerate(proj["tags"]):
        tw = measure(tag, "mono", 400, 11.5)
        w = 10 + 7 + 6 + tw + 11
        if x + w > W - 24:
            break
        body.append(
            f'<g class="up" style="animation-delay:{fmt(0.3 + k * 0.08)}s">'
            f'<rect x="{fmt(x)}" y="196" width="{fmt(w)}" height="28" rx="14" fill="{t["surface2"]}" stroke="{t["border"]}"/>'
            f'<circle cx="{fmt(x + 13.5)}" cy="210" r="3.5" fill="{color(t, tcol)}"/>'
            + svg.text(x + 23, 214, tag, "mono", 400, 11.5, t["text"])
            + "</g>"
        )
        x += w + 8
    svg.add(f'<g class="up">{"".join(body)}</g>')
    svg.add(f'<g class="pop" style="animation-delay:.2s">{art(svg, proj["art"], W - 64, 112, c)}</g>')
    return svg


# --------------------------------------------------------------------------- #
# Footer
# --------------------------------------------------------------------------- #
def footer(p: dict, theme: str) -> Svg:
    W, H = 1200, 170
    svg = Svg(W, H, theme, p["footer"]["title"], p["footer"]["subtitle"])
    t = svg.t
    svg.css.append(INTRO_CSS)

    def wave(length: float, amp: float, y: float) -> str:
        d = f"M{-length} {y}q{length / 4} {-amp} {length / 2} 0"
        x = -length / 2
        while x < W + length:
            d += f"t{length / 2} 0"
            x += length / 2
        return d

    waves = []
    for k, (length, amp, y, sw, op, dur) in enumerate(
        [(300, 14, 122, 2, 0.9, 9), (420, 20, 128, 1.5, 0.55, 13), (220, 9, 134, 1.2, 0.35, 7)]
    ):
        svg.css.append(f"@keyframes w{k}{{to{{transform:translateX({length}px)}}}}")
        waves.append(
            f'<path d="{wave(length, amp, y)}" stroke="#fff" stroke-opacity="{op}" stroke-width="{sw}" '
            f'style="animation:w{k} {dur}s linear infinite"/>'
        )
    grad = svg.linear("gw", [(0, t["a1"], 0), (0.2, t["a1"], 1), (0.5, t["a2"], 1), (0.8, t["a3"], 1), (1, t["a3"], 0)])
    svg.defs.append(f'<mask id="wm" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">{"".join(waves)}</mask>')
    svg.add(f'<rect width="{W}" height="{H}" fill="{grad}" mask="url(#wm)"/>')
    svg.add(
        '<g class="up">'
        + svg.text(W / 2, 56, p["footer"]["title"], "sans", 700, 26, t["text"], anchor="middle")
        + svg.text(W / 2, 88, p["footer"]["subtitle"], "mono", 400, 16, t["muted"], anchor="middle")
        + "</g>"
    )
    return svg


def main() -> None:
    p = load_profile()
    for theme in THEMES:
        print(f"[{theme}]")
        header(p, theme).save(ASSETS / f"header-{theme}.svg")
        about(p, theme).save(ASSETS / f"about-{theme}.svg")
        stack(p, theme).save(ASSETS / f"stack-{theme}.svg")
        for proj in p["projects"]:
            project_card(p, proj, theme).save(ASSETS / "projects" / f"{proj['slug']}-{theme}.svg")
        footer(p, theme).save(ASSETS / f"footer-{theme}.svg")


if __name__ == "__main__":
    main()
