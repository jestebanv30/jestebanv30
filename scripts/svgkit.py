"""Shared building blocks for the profile SVGs: themes, embedded fonts, icons.

Every SVG embeds a subset of its fonts as base64 woff2, so the text renders the
same on every OS (GitHub serves README images through a proxy that blocks
external font requests). Text is measured with the real glyph advances, which
is what lets the generators lay out chips, typing cursors and wrapped text.
"""

from __future__ import annotations

import base64
import io
import json
import math
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
FONTS = Path(__file__).resolve().parent / "fonts"
ICONS = Path(__file__).resolve().parent / "icons"

THEMES = {
    "dark": {
        "bg": "#0B1020",
        "bg2": "#0E1529",
        "surface": "#0F1729",
        "surface2": "#141D33",
        "chip": "#121A2F",
        "border": "#1E293B",
        "border2": "#2C3A55",
        "text": "#E6EDF3",
        "muted": "#97A3B6",
        "faint": "#56637B",
        "a1": "#22D3EE",
        "a2": "#818CF8",
        "a3": "#C084FC",
        "gold": "#FBBF24",
        "green": "#34D399",
        "rose": "#FB7185",
        "tile": "#242938",
        "glow": 1.0,
    },
    "light": {
        "bg": "#FFFFFF",
        "bg2": "#F4F7FB",
        "surface": "#FFFFFF",
        "surface2": "#F6F8FA",
        "chip": "#FFFFFF",
        "border": "#D8DEE4",
        "border2": "#C2CCD6",
        "text": "#1F2328",
        "muted": "#57606A",
        "faint": "#8C959F",
        "a1": "#0891B2",
        "a2": "#4F46E5",
        "a3": "#9333EA",
        "gold": "#B45309",
        "green": "#059669",
        "rose": "#E11D48",
        "tile": "#F4F2ED",
        "glow": 0.55,
    },
}

# CSS alias, file prefix, fallback stack
FAMILIES = {
    "mono": ("JBM", "JetBrainsMono", "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"),
    "sans": ("SG", "SpaceGrotesk", "ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif"),
}

# Glyph-only icons (not in skillicons) drawn on a skillicons-style tile.
SIMPLE_ICON_COLORS = {
    "pandas": {"dark": "#E70488", "light": "#150458"},
    "numpy": {"dark": "#4DABCF", "light": "#013243"},
    "plotly": {"dark": "#7A76FF", "light": "#3F4F75"},
    "pytest": {"dark": "#0A9EDC", "light": "#0A9EDC"},
}


def load_profile() -> dict:
    return json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
def _font_path(kind: str, weight: int) -> Path:
    return FONTS / f"{FAMILIES[kind][1]}-{weight}.woff2"


@lru_cache(maxsize=None)
def _metrics(kind: str, weight: int) -> tuple[dict[int, int], int]:
    font = TTFont(_font_path(kind, weight))
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    return {cp: hmtx[name][0] for cp, name in cmap.items()}, font["head"].unitsPerEm


def measure(s: str, kind: str = "sans", weight: int = 400, size: float = 16, ls: float = 0) -> float:
    """Advance width of `s` in px (kerning is disabled in the SVG CSS)."""
    adv, upem = _metrics(kind, weight)
    units = sum(adv.get(ord(ch), upem * 0.6) for ch in s)
    return units * size / upem + ls * len(s)


def wrap(s: str, width: float, **font) -> list[str]:
    lines, line = [], ""
    for word in s.split():
        cand = f"{line} {word}".strip()
        if line and measure(cand, **font) > width:
            lines.append(line)
            line = word
        else:
            line = cand
    if line:
        lines.append(line)
    return lines


@lru_cache(maxsize=None)
def _subset_b64(kind: str, weight: int, chars: str) -> str:
    font = TTFont(_font_path(kind, weight))
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "calt"]
    sub = subset.Subsetter(opts)
    sub.populate(text=chars + " ")
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


# --------------------------------------------------------------------------- #
# Icons
# --------------------------------------------------------------------------- #
_ID_RE = re.compile(r'id="([^"]+)"')


@lru_cache(maxsize=None)
def icon_body(name: str, theme: str) -> str:
    """Inner markup of a 256x256 icon tile, with ids namespaced per icon."""
    if name in SIMPLE_ICON_COLORS:
        raw = (ICONS / f"si-{name}.svg").read_text(encoding="utf-8")
        d = re.search(r'<path d="([^"]+)"', raw).group(1)
        color = SIMPLE_ICON_COLORS[name][theme]
        return (
            f'<rect width="256" height="256" rx="60" fill="{THEMES[theme]["tile"]}"/>'
            f'<path transform="translate(50 50) scale(6.5)" fill="{color}" d="{d}"/>'
        )
    raw = (ICONS / f"{name}-{theme}.svg").read_text(encoding="utf-8")
    inner = re.search(r'<g transform="translate\(0, 0\)">\s*<svg[^>]*>(.*)</svg>\s*</g>', raw, re.S)
    body = inner.group(1)
    for old in set(_ID_RE.findall(body)):
        new = f"{name}-{theme}-{old}"
        body = body.replace(f'id="{old}"', f'id="{new}"')
        body = body.replace(f"url(#{old})", f"url(#{new})")
        body = body.replace(f'href="#{old}"', f'href="#{new}"')
    return body


# --------------------------------------------------------------------------- #
# Document
# --------------------------------------------------------------------------- #
BASE_CSS = """
text{font-kerning:none}
.m{font-family:JBM,%s}
.s{font-family:SG,%s}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
""" % (FAMILIES["mono"][2], FAMILIES["sans"][2])


def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


class Svg:
    def __init__(self, w: int, h: int, theme: str, title: str, desc: str = ""):
        self.w, self.h, self.theme = w, h, theme
        self.t = THEMES[theme]
        self.title, self.desc = title, desc
        self.defs: list[str] = []
        self.css: list[str] = []
        self.parts: list[str] = []
        self.used: dict[tuple[str, int], set[str]] = defaultdict(set)
        self.icons: set[str] = set()
        self._n = 0

    def uid(self, prefix: str = "u") -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def add(self, *markup: str) -> None:
        self.parts.extend(markup)

    def text(
        self,
        x: float,
        y: float,
        s: str,
        kind: str = "sans",
        weight: int = 400,
        size: float = 16,
        fill: str | None = None,
        anchor: str | None = None,
        ls: float | None = None,
        cls: str = "",
        attrs: str = "",
    ) -> str:
        return self.runs(x, y, [(s, fill, weight)], kind, size, anchor, ls, cls, attrs, base_weight=weight)

    def runs(
        self,
        x: float,
        y: float,
        runs: list[tuple[str, str | None, int]],
        kind: str = "mono",
        size: float = 16,
        anchor: str | None = None,
        ls: float | None = None,
        cls: str = "",
        attrs: str = "",
        base_weight: int = 400,
    ) -> str:
        """One <text> made of differently styled runs: (text, fill, weight)."""
        spans = []
        for s, fill, weight in runs:
            self.used[(kind, weight)].update(s)
            a = []
            if fill:
                a.append(f'fill="{fill}"')
            if weight != base_weight:
                a.append(f'font-weight="{weight}"')
            spans.append(f"<tspan {' '.join(a)}>{escape(s)}</tspan>" if a else escape(s))
        a = [f'x="{fmt(x)}"', f'y="{fmt(y)}"', f'class="{(("m" if kind == "mono" else "s") + " " + cls).strip()}"']
        a.append(f'font-size="{fmt(size)}"')
        if base_weight != 400:
            a.append(f'font-weight="{base_weight}"')
        if anchor:
            a.append(f'text-anchor="{anchor}"')
        if ls:
            a.append(f'letter-spacing="{fmt(ls)}"')
        if len(runs) == 1 and runs[0][1]:
            a.append(f'fill="{runs[0][1]}"')
            body = escape(runs[0][0])
        else:
            body = "".join(spans)
        if attrs:
            a.append(attrs)
        return f"<text {' '.join(a)}>{body}</text>"

    def icon(self, name: str, x: float, y: float, size: float, attrs: str = "") -> str:
        self.icons.add(name)
        return (
            f'<use href="#ic-{name}" x="{fmt(x)}" y="{fmt(y)}" '
            f'width="{fmt(size)}" height="{fmt(size)}" {attrs}/>'
        )

    def linear(self, gid: str, stops: list[tuple[float, str, float]], x1=0, y1=0, x2=1, y2=0, extra: str = "", inner: str = "") -> str:
        st = "".join(
            f'<stop offset="{fmt(o)}" stop-color="{c}"' + (f' stop-opacity="{fmt(op)}"' if op != 1 else "") + "/>"
            for o, c, op in stops
        )
        self.defs.append(
            f'<linearGradient id="{gid}" x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" {extra}>{st}{inner}</linearGradient>'
        )
        return f"url(#{gid})"

    def radial(self, gid: str, color: str, opacity: float) -> str:
        self.defs.append(
            f'<radialGradient id="{gid}"><stop offset="0" stop-color="{color}" stop-opacity="{fmt(opacity)}"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>'
        )
        return f"url(#{gid})"

    def render(self) -> str:
        fonts = []
        for (kind, weight), chars in sorted(self.used.items()):
            chars_s = "".join(sorted(chars))
            if not chars_s.strip():
                continue
            b64 = _subset_b64(kind, weight, chars_s)
            fonts.append(
                f"@font-face{{font-family:{FAMILIES[kind][0]};font-weight:{weight};"
                f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
            )
        symbols = "".join(
            f'<symbol id="ic-{n}" viewBox="0 0 256 256">{icon_body(n, self.theme)}</symbol>' for n in sorted(self.icons)
        )
        css = "".join(fonts) + BASE_CSS + "\n".join(self.css)
        desc = f"<desc>{escape(self.desc)}</desc>" if self.desc else ""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" fill="none" role="img">'
            f"<title>{escape(self.title)}</title>{desc}"
            f"<style>{css}</style><defs>{''.join(self.defs)}{symbols}</defs>"
            + "".join(self.parts)
            + "</svg>\n"
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")
        print(f"  {path.relative_to(ROOT)}  {path.stat().st_size / 1024:.0f} KB")


# --------------------------------------------------------------------------- #
# Small shared pieces
# --------------------------------------------------------------------------- #
def rounded_rect_perimeter(w: float, h: float, r: float) -> float:
    return 2 * (w + h) - (8 - 2 * math.pi) * r


def colombia_flag(svg: Svg, cx: float, cy: float, r: float) -> str:
    cid = svg.uid("flag")
    svg.defs.append(f'<clipPath id="{cid}"><circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}"/></clipPath>')
    x, y, d = cx - r, cy - r, 2 * r
    return (
        f'<g clip-path="url(#{cid})">'
        f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(d)}" height="{fmt(r)}" fill="#FCD116"/>'
        f'<rect x="{fmt(x)}" y="{fmt(cy)}" width="{fmt(d)}" height="{fmt(r / 2)}" fill="#003893"/>'
        f'<rect x="{fmt(x)}" y="{fmt(cy + r / 2)}" width="{fmt(d)}" height="{fmt(r / 2)}" fill="#CE1126"/>'
        f"</g>"
        f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r - 0.5)}" stroke="#000" stroke-opacity=".15"/>'
    )


def pulse_dot(svg: Svg, cx: float, cy: float, r: float, color: str, delay: float = 0) -> str:
    if "pulse" not in "".join(svg.css):
        svg.css.append(
            "@keyframes pulse{0%{transform:scale(1);opacity:.6}80%,100%{transform:scale(2.8);opacity:0}}"
            ".pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.2s ease-out infinite}"
        )
    return (
        f'<circle class="pulse" style="animation-delay:{fmt(delay)}s" cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" fill="{color}"/>'
        f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" fill="{color}"/>'
    )
