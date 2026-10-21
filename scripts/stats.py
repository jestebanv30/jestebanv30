#!/usr/bin/env python3
"""Generate the GitHub stats and top-languages cards (dark + light).

    GITHUB_TOKEN=... python scripts/stats.py

With a token it uses the GraphQL API (a personal access token also counts
private contributions). Without one it falls back to the public REST API and
the public contributions calendar, which is enough for a local preview.

Self-hosted on purpose: the shared github-readme-stats instances are often
rate limited, and a broken image is worse than slightly stale numbers.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

from svgkit import ASSETS, Svg, fmt, load_profile, measure, rounded_rect_perimeter

API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
CACHE = os.environ.get("STATS_CACHE")  # optional dir, only for local iteration

# Fallback colors when the REST API (which has no colors) is used
LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178C6", "JavaScript": "#F1E05A", "Java": "#B07219",
    "Dart": "#00B4AB", "C#": "#178600", "HTML": "#E34C26", "CSS": "#563D7C", "SCSS": "#C6538C",
    "Vue": "#41B883", "Go": "#00ADD8", "Rust": "#DEA584", "PHP": "#4F5D95", "Kotlin": "#A97BFF",
    "Swift": "#F05138", "C++": "#F34B7D", "C": "#555555", "Shell": "#89E051", "Jupyter Notebook": "#DA5B0B",
}


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def http(url: str, body: dict | None = None, accept: str = "application/vnd.github+json") -> str:
    key = hashlib.sha1((url + json.dumps(body, sort_keys=True)).encode()).hexdigest()
    if CACHE:
        hit = Path(CACHE) / key
        if hit.exists():
            return hit.read_text(encoding="utf-8")
    headers = {"Accept": accept, "User-Agent": "profile-stats"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=30) as res:
        text = res.read().decode("utf-8")
    if CACHE:
        Path(CACHE).mkdir(parents=True, exist_ok=True)
        (Path(CACHE) / key).write_text(text, encoding="utf-8")
    return text


def graphql(query: str, **variables) -> dict:
    out = json.loads(http(f"{API}/graphql", {"query": query, "variables": variables}))
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


def fetch_graphql(login: str) -> dict:
    user = graphql(
        """query($login: String!) {
          user(login: $login) {
            createdAt
            pullRequests { totalCount }
            repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
              totalCount
              nodes {
                stargazerCount
                languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
                  edges { size node { name color } }
                }
              }
            }
            contributionsCollection { contributionYears }
          }
        }""",
        login=login,
    )["user"]

    years = sorted(user["contributionsCollection"]["contributionYears"])
    fields = []
    for y in years:
        fields.append(
            f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") {{'
            " totalCommitContributions"
            " contributionCalendar { weeks { contributionDays { date contributionCount } } } }"
        )
    per_year = graphql(f"query($login: String!) {{ user(login: $login) {{ {' '.join(fields)} }} }}", login=login)["user"]

    days, commits = {}, 0
    for col in per_year.values():
        commits += col["totalCommitContributions"]
        for week in col["contributionCalendar"]["weeks"]:
            for d in week["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    langs: dict[str, list] = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            entry = langs.setdefault(name, [0, e["node"]["color"] or LANG_COLORS.get(name, "#8B949E")])
            entry[0] += e["size"]
    return {
        "days": days,
        "commits": commits,
        "prs": user["pullRequests"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in user["repositories"]["nodes"]),
        "languages": langs,
    }


def fetch_public(login: str) -> dict:
    profile = json.loads(http(f"{API}/users/{login}"))
    repos = [r for r in json.loads(http(f"{API}/users/{login}/repos?per_page=100&type=owner")) if not r["fork"]]

    langs: dict[str, list] = {}
    for r in repos:
        for name, size in json.loads(http(r["languages_url"])).items():
            entry = langs.setdefault(name, [0, LANG_COLORS.get(name, "#8B949E")])
            entry[0] += size

    days: dict[str, int] = {}
    first = int(profile["created_at"][:4])
    for year in range(first, dt.date.today().year + 1):
        page = http(
            f"https://github.com/users/{login}/contributions?from={year}-01-01&to={year}-12-31", accept="text/html"
        )
        ids = dict(re.findall(r'data-date="([\d-]+)"[^>]*?id="([\w-]+)"', page))
        ids = {v: k for k, v in ids.items()}
        for cell, text in re.findall(r'<tool-tip[^>]*for="([\w-]+)"[^>]*>([^<]*)</tool-tip>', page):
            if cell in ids:
                m = re.match(r"(\d[\d,]*) contribution", text)
                days[ids[cell]] = int(m.group(1).replace(",", "")) if m else 0

    def search(q: str) -> int:
        return json.loads(http(f"{API}/search/{q}"))["total_count"]

    return {
        "days": days,
        "commits": search(f"commits?q=author:{login}&per_page=1"),
        "prs": search(f"issues?q=author:{login}+type:pr&per_page=1"),
        "repos": len(repos),
        "stars": sum(r["stargazers_count"] for r in repos),
        "languages": langs,
    }


def streaks(days: dict[str, int]) -> tuple[int, int]:
    today = dt.date.today()
    dates = sorted(dt.date.fromisoformat(d) for d, c in days.items() if c > 0 and dt.date.fromisoformat(d) <= today)
    longest = run = 0
    prev = None
    for d in dates:
        run = run + 1 if prev and (d - prev).days == 1 else 1
        longest = max(longest, run)
        prev = d
    # A streak is still alive if the last contribution was today or yesterday
    current = run if prev and (today - prev).days <= 1 else 0
    return current, longest


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
CARD_CSS = (
    "@keyframes up{from{opacity:0;transform:translateY(12px)}}"
    ".up{animation:up .8s cubic-bezier(.2,.7,.2,1) both}"
)


def card(svg: Svg, title: str, note: str) -> None:
    t = svg.t
    W, H = svg.w, svg.h
    svg.css.append(CARD_CSS)
    glow = svg.radial("glow", t["a2"], 0.16 * t["glow"])
    svg.defs.append(f'<clipPath id="card"><rect width="{W}" height="{H}" rx="16"/></clipPath>')
    per = rounded_rect_perimeter(W - 1.5, H - 1.5, 15.25)
    beam = svg.linear("beam", [(0, t["a1"], 1), (0.5, t["a2"], 1), (1, t["a3"], 1)], 0, 0, 1, 1)
    svg.css.append(f"@keyframes run{{to{{stroke-dashoffset:-{fmt(per)}}}}}")
    svg.add(
        f'<rect width="{W}" height="{H}" rx="16" fill="{t["surface"]}"/>',
        f'<g clip-path="url(#card)"><circle cx="40" cy="0" r="220" fill="{glow}"/></g>',
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="15.5" stroke="{t["border"]}"/>',
        f'<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="15.25" stroke="{beam}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-dasharray="110 {fmt(per - 110)}" style="animation:run 8s linear infinite"/>',
        svg.text(24, 42, title, "sans", 700, 18, t["text"]),
        svg.text(W - 24, 41, note, "mono", 400, 11, t["faint"], anchor="end"),
    )


def odometer(svg: Svg, x: float, y: float, value: str, size: float, fill: str, delay: float) -> str:
    """Digits that roll into place, like a mechanical counter."""
    cw = measure("0", "mono", 700, size)
    lh = size * 1.25
    clip = svg.uid("odo")
    svg.defs.append(
        f'<clipPath id="{clip}"><rect x="{fmt(x - 2)}" y="{fmt(y - size)}" '
        f'width="{fmt(len(value) * cw + 4)}" height="{fmt(size * 1.3)}"/></clipPath>'
    )
    out = [f'<g clip-path="url(#{clip})">']
    for j, ch in enumerate(value):
        cx = x + j * cw
        if not ch.isdigit():
            out.append(svg.text(cx, y, ch, "mono", 700, size, fill))
            continue
        target = 10 + int(ch)  # roll through one full turn first
        name = f"roll{target}"
        if name not in "".join(svg.css):
            svg.css.append(
                f"@keyframes {name}{{from{{transform:translateY(0)}}to{{transform:translateY(-{fmt(target * lh)}px)}}}}"
            )
        column = "".join(svg.text(cx, y + k * lh, str(k % 10), "mono", 700, size, fill) for k in range(target + 1))
        d = delay + (len(value) - j) * 0.08
        out.append(
            f'<g style="transform:translateY(-{fmt(target * lh)}px);'
            f'animation:{name} 1.8s cubic-bezier(.15,.75,.25,1) {fmt(d)}s both">{column}</g>'
        )
    out.append("</g>")
    return "".join(out)


def stats_card(data: dict, theme: str, updated: str) -> Svg:
    W, H = 480, 250
    svg = Svg(W, H, theme, "GitHub activity", "Contributions, commits, pull requests and streaks")
    t = svg.t
    card(svg, "GitHub Activity", f"updated {updated}")

    current, longest = streaks(data["days"])
    year = dt.date.today().year
    this_year = sum(c for d, c in data["days"].items() if d.startswith(str(year)))
    tiles = [
        ("CONTRIBUTIONS", f"{sum(data['days'].values()):,}", "", t["a1"]),
        (f"IN {year}", f"{this_year:,}", "", t["a2"]),
        ("COMMITS", f"{data['commits']:,}", "", t["a3"]),
        ("PULL REQUESTS", f"{data['prs']:,}", "", t["gold"]),
        ("LONGEST STREAK", f"{longest:,}", "days", t["green"]),
        ("CURRENT STREAK", f"{current:,}", "days" if current != 1 else "day", t["rose"]),
    ]
    tw, th = 136, 78
    for i, (label, value, unit, col) in enumerate(tiles):
        x, y = 24 + (i % 3) * (tw + 8), 62 + (i // 3) * (th + 10)
        num = odometer(svg, x + 16, y + 58, value, 26, t["text"], 0.3 + i * 0.1)
        unit_svg = ""
        if unit:
            ux = x + 16 + measure(value, "mono", 700, 26) + 6
            unit_svg = svg.text(ux, y + 58, unit, "mono", 400, 11, t["muted"])
        svg.add(
            f'<g class="up" style="animation-delay:{fmt(0.1 + i * 0.08)}s">'
            f'<rect x="{x}" y="{y}" width="{tw}" height="{th}" rx="12" fill="{t["surface2"]}" stroke="{t["border"]}"/>'
            f'<rect x="{x + 16}" y="{y + 14}" width="14" height="3" rx="1.5" fill="{col}"/>'
            + svg.text(x + 16, y + 31, label, "mono", 400, 10, t["muted"], ls=0.6)
            + num
            + unit_svg
            + "</g>"
        )
    return svg


def languages_card(data: dict, theme: str, exclude: list[str], limit: int) -> Svg:
    W, H = 480, 250
    svg = Svg(W, H, theme, "Most used languages", "Share of code across public repositories")
    t = svg.t
    langs = sorted(((n, s, c) for n, (s, c) in data["languages"].items() if n not in exclude), key=lambda x: -x[1])
    total = sum(s for _, s, _ in langs) or 1
    top = langs[:limit]
    card(svg, "Most Used Languages", f"{len(langs)} languages")

    # Stacked bar that fills from the left, segment by segment
    bx, by, bw, bh = 24, 66, W - 48, 12
    svg.defs.append(f'<clipPath id="bar"><rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="6"/></clipPath>')
    svg.css.append(
        "@keyframes grow{from{transform:scaleX(0)}}"
        ".seg{transform-box:fill-box;transform-origin:left center;animation:grow .7s cubic-bezier(.3,.7,.3,1) both}"
    )
    segs, x = [], float(bx)
    shown = sum(s for _, s, _ in top)
    for i, (name, size, col) in enumerate(top):
        w = bw * size / shown
        segs.append(
            f'<rect class="seg" style="animation-delay:{fmt(0.3 + i * 0.18)}s" x="{fmt(x)}" y="{by}" '
            f'width="{fmt(w + 0.5)}" height="{bh}" fill="{col}"/>'
        )
        x += w
    svg.add(
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="6" fill="{t["surface2"]}"/>'
        f'<g clip-path="url(#bar)">{"".join(segs)}</g>'
    )

    # Legend: two columns
    for i, (name, size, col) in enumerate(top):
        cx, cy = 24 + (i % 2) * 222, 116 + (i // 2) * 42
        pct = 100 * size / total
        mini = 150 * size / top[0][1]
        svg.add(
            f'<g class="up" style="animation-delay:{fmt(0.4 + i * 0.1)}s">'
            f'<circle cx="{cx + 6}" cy="{cy - 5}" r="5" fill="{col}"/>'
            + svg.text(cx + 20, cy, name, "sans", 500, 15, t["text"])
            + svg.text(cx + 208, cy, f"{pct:.1f}%", "mono", 400, 12.5, t["muted"], anchor="end")
            + f'<rect x="{cx + 20}" y="{cy + 9}" width="188" height="3" rx="1.5" fill="{t["surface2"]}"/>'
            f'<rect class="seg" style="animation-delay:{fmt(0.6 + i * 0.12)}s" x="{cx + 20}" y="{cy + 9}" '
            f'width="{fmt(mini * 188 / 150)}" height="3" rx="1.5" fill="{col}"/>'
            + "</g>"
        )
    return svg


def main() -> None:
    p = load_profile()
    login = p["username"]
    data = None
    if TOKEN:
        try:
            data = fetch_graphql(login)
        except Exception as e:  # e.g. a token without GraphQL access
            print(f"GraphQL failed ({e}); falling back to public data")
    if data is None:
        data = fetch_public(login)
    updated = dt.date.today().isoformat()
    cfg = p.get("stats", {})
    for theme in ("dark", "light"):
        stats_card(data, theme, updated).save(ASSETS / f"stats-{theme}.svg")
        languages_card(data, theme, cfg.get("exclude_languages", []), cfg.get("max_languages", 6)).save(
            ASSETS / f"languages-{theme}.svg"
        )


if __name__ == "__main__":
    main()
