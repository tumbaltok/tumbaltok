#!/usr/bin/env python3
"""Self-hosted futuristic Bento HUD SVG generator for tumbaltok's GitHub Profile.

Generates zero-downtime, GitHub-sanitizer-safe animated SVGs in ./assets/ using
live GitHub GraphQL/REST metrics when available, with deterministic baseline
fallback for offline/initial execution.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import sys
import textwrap
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"

USERNAME = os.getenv("GITHUB_REPOSITORY_OWNER") or os.getenv("GH_USERNAME") or "tumbaltok"
TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or ""

FONT_MONO = "'JetBrains Mono', 'Fira Code', 'Cascadia Code', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
FONT_SANS = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

PALETTE = {
    "bg_deep": "#05080E",
    "bg_card": "#0A1019",
    "bg_panel": "#0F1724",
    "bg_chip": "#121D2D",
    "border": "#1C2B3D",
    "border_bright": "#27415C",
    "green": "#00FF88",
    "green_dim": "#003D22",
    "cyan": "#00E5FF",
    "violet": "#A855F7",
    "amber": "#FFB800",
    "blue": "#38BDF8",
    "emerald": "#10B981",
    "rose": "#F43F5E",
    "text": "#F0F6FC",
    "text_sub": "#C9D1D9",
    "muted": "#8B949E",
    "dim": "#484F58",
}

LANG_COLORS = {
    "Python": "#3572A5",
    "PHP": "#4F5D95",
    "Blade": "#F7523F",
    "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A",
    "HTML": "#E34C26",
    "CSS": "#563D7C",
    "Shell": "#89E051",
    "Rust": "#DEA584",
    "Go": "#00ADD8",
    "C++": "#F34B7D",
    "C": "#555555",
    "Dockerfile": "#384D54",
    "HCL": "#844FBA",
}

FEATURED_FALLBACK = [
    {
        "name": "NDOK-Scada",
        "code": "PAYLOAD // 01",
        "description": "Industrial SCADA data acquisition, real-time sensor telemetry pipeline & Python automation engine.",
        "language": "Python",
        "stars": 1,
        "forks": 0,
        "accent": "#00FF88",
        "tag": "OT / TELEMETRY",
    },
    {
        "name": "Umbulan",
        "code": "PAYLOAD // 02",
        "description": "Full-stack web architecture & system integration platform powered by Laravel Blade & REST APIs.",
        "language": "Blade",
        "stars": 1,
        "forks": 0,
        "accent": "#00E5FF",
        "tag": "LARAVEL STACK",
    },
    {
        "name": "ShordLink",
        "code": "PAYLOAD // 03",
        "description": "High-speed link routing utility, smart redirect gateway & compact analytics web service.",
        "language": "PHP",
        "stars": 1,
        "forks": 0,
        "accent": "#A855F7",
        "tag": "EDGE ROUTING",
    },
    {
        "name": "TehTawa",
        "code": "PAYLOAD // 04",
        "description": "Modern interactive frontend experience crafted with responsive HTML5/CSS3 & clean UI motion.",
        "language": "HTML",
        "stars": 1,
        "forks": 0,
        "accent": "#FFB800",
        "tag": "INTERACTIVE UI",
    },
]


def esc(val: Any) -> str:
    return html.escape(str(val), quote=True)


def fmt_num(n: int) -> str:
    if n >= 1000:
        return f"{n:,}"
    return str(n)


def api_request(url: str, method: str = "GET", payload: dict | None = None) -> Any:
    headers = {
        "User-Agent": "tumbaltok-hud-generator/2.0",
        "Accept": "application/vnd.github+json",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compute_streaks(weeks: list[list[dict[str, Any]]]) -> tuple[int, int]:
    days = [day for week in weeks for day in week]
    if not days:
        return 0, 0
    longest = 0
    running = 0
    for d in days:
        if d.get("contributionCount", 0) > 0:
            running += 1
            if running > longest:
                longest = running
        else:
            running = 0

    current = 0
    # Allow today (last item) to be 0 if day hasn't had a commit yet, checking backwards from yesterday.
    idx = len(days) - 1
    if idx >= 0 and days[idx].get("contributionCount", 0) == 0:
        idx -= 1
    while idx >= 0 and days[idx].get("contributionCount", 0) > 0:
        current += 1
        idx -= 1
    return current, longest


def baseline_weeks() -> list[list[dict[str, Any]]]:
    """Deterministic 52x7 baseline matrix when offline or API unavailable."""
    today = dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=52 * 7 - 1)
    weeks: list[list[dict[str, Any]]] = []
    for w in range(52):
        col = []
        for d in range(7):
            day_date = start + dt.timedelta(days=w * 7 + d)
            # Deterministic wave pattern weighted higher towards recent weeks
            recency_boost = 1 if w > 36 else 0
            wave = (math.sin(w * 0.45 + d * 0.8) + math.cos(w * 0.22 - d * 0.5) + 2.0) / 4.0
            if w == 51 and d >= 4:
                count = 4 + (d % 3)
            elif wave > 0.72:
                count = 5 + recency_boost * 2
            elif wave > 0.52:
                count = 3 + recency_boost
            elif wave > 0.34:
                count = 1 + recency_boost
            else:
                count = 0 if w < 44 else 1
            col.append({"date": day_date.isoformat(), "contributionCount": count})
        weeks.append(col)
    return weeks


def fetch_github_telemetry() -> dict[str, Any]:
    now_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data: dict[str, Any] = {
        "username": USERNAME,
        "synced_at": now_str,
        "source": "BASELINE SPEC",
        "followers": 12,
        "repos": 9,
        "stars": 4,
        "forks": 1,
        "commits": 148,
        "prs": 14,
        "issues": 6,
        "total_contributions": 284,
        "current_streak": 7,
        "longest_streak": 19,
        "languages": [
            {"name": "Python", "pct": 38.4, "color": LANG_COLORS["Python"]},
            {"name": "PHP", "pct": 24.6, "color": LANG_COLORS["PHP"]},
            {"name": "TypeScript", "pct": 14.2, "color": LANG_COLORS["TypeScript"]},
            {"name": "Blade", "pct": 10.5, "color": LANG_COLORS["Blade"]},
            {"name": "HTML", "pct": 7.1, "color": LANG_COLORS["HTML"]},
            {"name": "Shell", "pct": 5.2, "color": LANG_COLORS["Shell"]},
        ],
        "weeks": baseline_weeks(),
        "featured": [dict(item) for item in FEATURED_FALLBACK],
    }

    if TOKEN:
        try:
            query = """
            query($login: String!) {
              user(login: $login) {
                followers { totalCount }
                repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
                  totalCount
                  nodes {
                    name
                    description
                    stargazerCount
                    forkCount
                    primaryLanguage { name color }
                    languages(first: 8, orderBy: {field: SIZE, direction: DESC}) {
                      edges {
                        size
                        node { name color }
                      }
                    }
                  }
                }
                contributionsCollection {
                  totalCommitContributions
                  restrictedContributionsCount
                  totalPullRequestContributions
                  totalIssueContributions
                  contributionCalendar {
                    totalContributions
                    weeks {
                      contributionDays {
                        date
                        contributionCount
                      }
                    }
                  }
                }
              }
            }
            """
            res = api_request(
                "https://api.github.com/graphql",
                method="POST",
                payload={"query": query, "variables": {"login": USERNAME}},
            )
            user = res.get("data", {}).get("user")
            if user:
                repos_nodes = user["repositories"]["nodes"] or []
                total_stars = sum(r.get("stargazerCount", 0) for r in repos_nodes)
                total_forks = sum(r.get("forkCount", 0) for r in repos_nodes)

                lang_totals: dict[str, dict[str, Any]] = {}
                repo_map: dict[str, dict[str, Any]] = {}
                for r in repos_nodes:
                    repo_map[r["name"].lower()] = r
                    for edge in r.get("languages", {}).get("edges", []):
                        lname = edge["node"]["name"]
                        lcolor = edge["node"].get("color") or LANG_COLORS.get(lname, PALETTE["green"])
                        lsize = edge["size"]
                        if lname not in lang_totals:
                            lang_totals[lname] = {"size": 0, "color": lcolor}
                        lang_totals[lname]["size"] += lsize

                total_bytes = sum(v["size"] for v in lang_totals.values()) or 1
                sorted_langs = sorted(lang_totals.items(), key=lambda kv: kv[1]["size"], reverse=True)[:6]
                if sorted_langs:
                    data["languages"] = [
                        {
                            "name": name,
                            "pct": round(info["size"] * 100.0 / total_bytes, 1),
                            "color": info["color"],
                        }
                        for name, info in sorted_langs
                    ]

                contrib = user["contributionsCollection"]
                cal = contrib["contributionCalendar"]
                raw_weeks = [w["contributionDays"] for w in cal["weeks"][-52:]]
                cur_streak, max_streak = compute_streaks(raw_weeks)

                data.update(
                    {
                        "source": "GITHUB GRAPHQL LIVE",
                        "followers": user["followers"]["totalCount"],
                        "repos": user["repositories"]["totalCount"],
                        "stars": total_stars,
                        "forks": total_forks,
                        "commits": contrib["totalCommitContributions"] + contrib["restrictedContributionsCount"],
                        "prs": contrib["totalPullRequestContributions"],
                        "issues": contrib["totalIssueContributions"],
                        "total_contributions": cal["totalContributions"],
                        "current_streak": cur_streak,
                        "longest_streak": max_streak,
                        "weeks": raw_weeks if raw_weeks else data["weeks"],
                    }
                )

                for item in data["featured"]:
                    live = repo_map.get(item["name"].lower())
                    if live:
                        item["stars"] = live.get("stargazerCount", item["stars"])
                        item["forks"] = live.get("forkCount", item["forks"])
                        if live.get("description"):
                            item["description"] = live["description"]
                        if live.get("primaryLanguage"):
                            item["language"] = live["primaryLanguage"]["name"]
                return data
        except Exception as exc:
            print(f"[warn] GraphQL fetch skipped ({exc}), trying REST fallback...", file=sys.stderr)

    # REST fallback if offline/rate-limited check allows public access
    if os.getenv("ALLOW_PUBLIC_API", "0") == "1" or TOKEN:
        try:
            u = api_request(f"https://api.github.com/users/{USERNAME}")
            repos = api_request(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&sort=updated")
            if isinstance(u, dict) and isinstance(repos, list):
                own_repos = [r for r in repos if not r.get("fork")]
                data["source"] = "GITHUB REST LIVE"
                data["followers"] = u.get("followers", data["followers"])
                data["repos"] = u.get("public_repos", len(own_repos))
                data["stars"] = sum(r.get("stargazers_count", 0) for r in own_repos)
                data["forks"] = sum(r.get("forks_count", 0) for r in own_repos)
                repo_map = {r["name"].lower(): r for r in own_repos}
                lang_counts: dict[str, int] = {}
                for r in own_repos:
                    lang = r.get("language")
                    if lang:
                        lang_counts[lang] = lang_counts.get(lang, 0) + max(1, r.get("size", 1))
                if lang_counts:
                    tot = sum(lang_counts.values())
                    data["languages"] = [
                        {
                            "name": k,
                            "pct": round(v * 100.0 / tot, 1),
                            "color": LANG_COLORS.get(k, PALETTE["cyan"]),
                        }
                        for k, v in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:6]
                    ]
                for item in data["featured"]:
                    live = repo_map.get(item["name"].lower())
                    if live:
                        item["stars"] = live.get("stargazers_count", item["stars"])
                        item["forks"] = live.get("forks_count", item["forks"])
                        if live.get("description"):
                            item["description"] = live["description"]
                        if live.get("language"):
                            item["language"] = live["language"]
        except Exception as exc:
            print(f"[warn] REST fetch skipped ({exc}), using baseline data.", file=sys.stderr)

    return data


def hud_corners(w: int, h: int, color: str = PALETTE["green"], size: int = 14) -> str:
    m = 10
    return (
        f'<path d="M {m} {m + size} L {m} {m} L {m + size} {m}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>'
        f'<path d="M {w - m - size} {m} L {w - m} {m} L {w - m} {m + size}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>'
        f'<path d="M {m} {h - m - size} L {m} {h - m} L {m + size} {h - m}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>'
        f'<path d="M {w - m - size} {h - m} L {w - m} {h - m} L {w - m} {h - m - size}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>'
    )


def calc_rank(data: dict[str, Any]) -> tuple[str, int, str]:
    score = (
        data["commits"] * 0.45
        + data["stars"] * 12
        + data["repos"] * 4
        + data["prs"] * 5
        + data["followers"] * 3
    )
    if score >= 450:
        return "S+", 96, "OMEGA ELITE"
    if score >= 240:
        return "S", 91, "CYBER ARCHITECT"
    if score >= 140:
        return "A++", 86, "APEX BUILDER"
    return "A+", 82, "ACTIVE OPERATOR"


def build_hero_svg(data: dict[str, Any]) -> str:
    w, h = 1200, 330
    grid_lines = []
    for gx in range(40, w, 40):
        grid_lines.append(f'<line x1="{gx}" y1="0" x2="{gx}" y2="{h}" stroke="#0F1C2A" stroke-width="1"/>')
    for gy in range(40, h, 40):
        grid_lines.append(f'<line x1="0" y1="{gy}" x2="{w}" y2="{gy}" stroke="#0F1C2A" stroke-width="1"/>')

    # Bottom spectrum bars
    eq_bars = []
    heights = [8, 16, 12, 22, 14, 24, 18, 10, 20, 15, 22, 11, 17, 9, 19, 13]
    for i, bh in enumerate(heights):
        bx = 28 + i * 10
        by = 304 - bh
        delay = (i * 0.11) % 1.4
        eq_bars.append(
            f'<rect x="{bx}" y="{by}" width="5" height="{bh}" rx="2" fill="{PALETTE["green"]}" opacity="0.85">'
            f'<animate attributeName="height" values="{max(4, bh // 2)};{bh};{max(5, bh // 3)};{bh}" dur="{1.2 + (i % 4) * 0.25:.2f}s" begin="{delay:.2f}s" repeatCount="indefinite"/>'
            f'<animate attributeName="y" values="{304 - max(4, bh // 2)};{by};{304 - max(5, bh // 3)};{by}" dur="{1.2 + (i % 4) * 0.25:.2f}s" begin="{delay:.2f}s" repeatCount="indefinite"/>'
            f"</rect>"
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="TUMBALTOK Neural Cyber Command Deck">
  <defs>
    <linearGradient id="heroBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#05080F"/>
      <stop offset="55%" stop-color="#09131E"/>
      <stop offset="100%" stop-color="#061414"/>
    </linearGradient>
    <linearGradient id="heroTitleGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="55%" stop-color="#00FF88"/>
      <stop offset="100%" stop-color="#00E5FF"/>
    </linearGradient>
    <linearGradient id="scanGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#00FF88" stop-opacity="0"/>
      <stop offset="50%" stop-color="#00FF88" stop-opacity="0.16"/>
      <stop offset="100%" stop-color="#00E5FF" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#00FF88" stop-opacity="0.35"/>
      <stop offset="65%" stop-color="#00E5FF" stop-opacity="0.10"/>
      <stop offset="100%" stop-color="#00FF88" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="heroClip">
      <rect x="2" y="2" width="{w - 4}" height="{h - 4}" rx="16"/>
    </clipPath>
    <style>
      .mono {{ font-family: {FONT_MONO}; }}
      .sans {{ font-family: {FONT_SANS}; }}
      .cmd1 {{ animation: swap1 12s infinite; }}
      .cmd2 {{ animation: swap2 12s infinite; }}
      .cmd3 {{ animation: swap3 12s infinite; }}
      .blink {{ animation: blinkCur 1s steps(2, start) infinite; }}
      @keyframes swap1 {{
        0%, 30% {{ opacity: 1; }}
        33%, 97% {{ opacity: 0; }}
        100% {{ opacity: 1; }}
      }}
      @keyframes swap2 {{
        0%, 33% {{ opacity: 0; }}
        36%, 63% {{ opacity: 1; }}
        66%, 100% {{ opacity: 0; }}
      }}
      @keyframes swap3 {{
        0%, 66% {{ opacity: 0; }}
        69%, 97% {{ opacity: 1; }}
        100% {{ opacity: 0; }}
      }}
      @keyframes blinkCur {{
        to {{ opacity: 0; }}
      }}
    </style>
  </defs>

  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16" fill="url(#heroBg)" stroke="{PALETTE['border']}" stroke-width="1.5"/>

  <g clip-path="url(#heroClip)">
    {''.join(grid_lines)}
    <circle cx="135" cy="166" r="125" fill="url(#coreGlow)"/>
    <circle cx="1050" cy="70" r="160" fill="url(#coreGlow)" opacity="0.45"/>
    <rect x="0" y="-45" width="{w}" height="45" fill="url(#scanGrad)">
      <animate attributeName="y" values="-45;{h + 10}" dur="5.8s" repeatCount="indefinite"/>
    </rect>
  </g>

  {hud_corners(w, h, PALETTE["green"], 16)}

  <!-- Top Telemetry Header -->
  <circle cx="34" cy="30" r="4" fill="{PALETTE['green']}">
    <animate attributeName="r" values="3.5;5.5;3.5" dur="2s" repeatCount="indefinite"/>
    <animate attributeName="opacity" values="1;0.45;1" dur="2s" repeatCount="indefinite"/>
  </circle>
  <text x="48" y="34" class="mono" font-size="11.5" font-weight="700" fill="{PALETTE['green']}" letter-spacing="1.2">NODE // 0xTUMBALTOK</text>

  <rect x="445" y="17" width="310" height="24" rx="12" fill="#0B1623" stroke="#1E354D" stroke-width="1"/>
  <text x="600" y="33" text-anchor="middle" class="mono" font-size="11" fill="{PALETTE['cyan']}" letter-spacing="1.4">OMNI-ARCHITECT HUD // v4.2026</text>

  <rect x="945" y="17" width="225" height="24" rx="12" fill="#091B18" stroke="#14533C" stroke-width="1"/>
  <text x="1057" y="33" text-anchor="middle" class="mono" font-size="11" fill="{PALETTE['green']}" letter-spacing="0.8">ONLINE • PORT 443 • TLS 1.3</text>

  <line x1="26" y1="52" x2="{w - 26}" y2="52" stroke="#152436" stroke-width="1"/>

  <!-- Orbital Hex Reactor Emblem -->
  <g transform="translate(0, 0)">
    <circle cx="135" cy="168" r="78" fill="none" stroke="#193347" stroke-width="1.2" stroke-dasharray="6 6">
      <animateTransform attributeName="transform" type="rotate" from="0 135 168" to="360 135 168" dur="26s" repeatCount="indefinite"/>
    </circle>
    <circle cx="135" cy="168" r="64" fill="none" stroke="{PALETTE['cyan']}" stroke-width="1.6" stroke-dasharray="28 14 8 14" opacity="0.75">
      <animateTransform attributeName="transform" type="rotate" from="360 135 168" to="0 135 168" dur="14s" repeatCount="indefinite"/>
    </circle>
    <circle cx="135" cy="168" r="50" fill="#07101A" stroke="{PALETTE['green']}" stroke-width="1.5" opacity="0.95"/>
    <polygon points="135,128 170,148 170,188 135,208 100,188 100,148" fill="#081C18" stroke="{PALETTE['green']}" stroke-width="2">
      <animate attributeName="stroke-opacity" values="0.6;1;0.6" dur="2.5s" repeatCount="indefinite"/>
    </polygon>
    <polygon points="135,142 157,155 157,181 135,194 113,181 113,155" fill="none" stroke="{PALETTE['cyan']}" stroke-width="1.3" opacity="0.9"/>
    <text x="135" y="174" text-anchor="middle" class="mono" font-size="16" font-weight="800" fill="{PALETTE['green']}" letter-spacing="1">0xT</text>
  </g>

  <!-- Main Display Title & Subtitle -->
  <text x="245" y="100" class="mono" font-size="12" font-weight="600" fill="{PALETTE['cyan']}" letter-spacing="2.8">// CLASSIFIED ENGINEERING &amp; CYBER COMMAND DECK</text>

  <text x="245" y="156" class="sans" font-size="54" font-weight="900" fill="url(#heroTitleGrad)" letter-spacing="3">TUMBALTOK</text>

  <rect x="615" y="118" width="145" height="28" rx="6" fill="#0A1E17" stroke="{PALETTE['green']}" stroke-width="1.1"/>
  <text x="687" y="136" text-anchor="middle" class="mono" font-size="12" font-weight="700" fill="{PALETTE['green']}" letter-spacing="1">ROOT // ALL-SKILLS</text>

  <rect x="772" y="118" width="166" height="28" rx="6" fill="#161028" stroke="{PALETTE['violet']}" stroke-width="1.1"/>
  <text x="855" y="136" text-anchor="middle" class="mono" font-size="12" font-weight="700" fill="#D8B4FE" letter-spacing="0.8">CLEARANCE: OMEGA</text>

  <text x="245" y="189" class="sans" font-size="15" font-weight="500" fill="{PALETTE['text_sub']}" letter-spacing="0.4">Offensive Security  •  Full-Stack Architecture  •  AI &amp; Autonomous Agents  •  Cloud/K8s  •  SCADA / OT</text>

  <!-- Interactive Animated Terminal Strip -->
  <rect x="245" y="208" width="925" height="48" rx="10" fill="#050911" stroke="#1B3044" stroke-width="1.2"/>
  <circle cx="266" cy="232" r="5" fill="{PALETTE['green']}"/>
  <text x="282" y="237" class="mono cmd1" font-size="13.5" fill="{PALETTE['text']}" font-weight="600">root@tumbaltok:~# ./boot_omni_core.sh --skills=ALL --zero-trust --telemetry=live</text>
  <text x="282" y="237" class="mono cmd2" font-size="13.5" fill="{PALETTE['cyan']}" font-weight="600">[+] Loaded: OffSec • Rust/Go/C++ • TypeScript/Next/Laravel • PyTorch/LLM • K8s • SCADA</text>
  <text x="282" y="237" class="mono cmd3" font-size="13.5" fill="{PALETTE['green']}" font-weight="600">[OK] Self-hosted Bento HUD online — {esc(fmt_num(data['commits']))}+ commits • {esc(str(data['repos']))} active payloads</text>
  <rect x="1144" y="223" width="9" height="17" rx="1.5" fill="{PALETTE['green']}" class="blink"/>

  <!-- Bottom Telemetry Footer Strip -->
  <line x1="26" y1="274" x2="{w - 26}" y2="274" stroke="#152436" stroke-width="1"/>
  {''.join(eq_bars)}
  <text x="198" y="301" class="mono" font-size="11" fill="{PALETTE['muted']}" letter-spacing="1">NEURAL SIGNAL: OPTIMAL</text>

  <text x="1170" y="301" text-anchor="end" class="mono" font-size="11" fill="{PALETTE['muted']}" letter-spacing="0.8">SYNC: {esc(data['synced_at'])}  |  ZERO-DOWNTIME SVG ENGINE</text>
</svg>
"""


def build_identity_svg(data: dict[str, Any]) -> str:
    w, h = 600, 340
    rows = [
        ("ALIAS", "tumbaltok (0xTumbaltok)", PALETTE["green"]),
        ("OS KERNEL", "Kali GNU/Linux Rolling • x86_64", PALETTE["text"]),
        ("CLASS", "Full-Spectrum Polyglot & Sec Architect", PALETTE["cyan"]),
        ("SPECIALTY", "OffSec • AI Agents • Web • Cloud • SCADA", PALETTE["text_sub"]),
        ("ARSENAL", "Rust, Go, C++, Python, TS, PHP/Laravel", "#D8B4FE"),
        ("STATUS", "ONLINE // LISTENING ON PORT 443", PALETTE["green"]),
    ]

    row_xml = []
    for idx, (label, val, col) in enumerate(rows):
        ry = 98 + idx * 32
        row_xml.append(
            f'<rect x="26" y="{ry - 18}" width="548" height="26" rx="6" fill="#0B131E" opacity="0.85"/>'
            f'<text x="38" y="{ry}" class="mono" font-size="11.5" font-weight="700" fill="{PALETTE["muted"]}">{esc(label)}</text>'
            f'<text x="138" y="{ry}" class="mono" font-size="11.5" fill="{PALETTE["dim"]}">::</text>'
            f'<text x="160" y="{ry}" class="mono" font-size="12" font-weight="600" fill="{col}">{esc(val)}</text>'
        )

    meters = [
        ("OFFSEC", 100, PALETTE["green"], 28),
        ("FULL-STACK", 99, PALETTE["cyan"], 166),
        ("AI / LLM", 98, PALETTE["violet"], 304),
        ("SCADA / OT", 98, PALETTE["amber"], 442),
    ]
    meter_xml = []
    for label, pct, col, mx in meters:
        meter_xml.append(
            f'<rect x="{mx}" y="286" width="130" height="36" rx="8" fill="#070D15" stroke="#182739" stroke-width="1"/>'
            f'<text x="{mx + 10}" y="302" class="mono" font-size="10" font-weight="700" fill="{PALETTE["muted"]}">{esc(label)}</text>'
            f'<text x="{mx + 120}" y="302" text-anchor="end" class="mono" font-size="10" font-weight="700" fill="{col}">{pct}%</text>'
            f'<rect x="{mx + 10}" y="310" width="110" height="5" rx="2.5" fill="#142030"/>'
            f'<rect x="{mx + 10}" y="310" width="{round(1.1 * pct)}" height="5" rx="2.5" fill="{col}"/>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="System Identity Card">
  <defs>
    <linearGradient id="idBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070C14"/>
      <stop offset="100%" stop-color="#0B141F"/>
    </linearGradient>
    <style>
      .mono {{ font-family: {FONT_MONO}; }}
      .sans {{ font-family: {FONT_SANS}; }}
      .led {{ animation: ledBlink 2.2s ease-in-out infinite; }}
      @keyframes ledBlink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}
    </style>
  </defs>

  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16" fill="url(#idBg)" stroke="{PALETTE['border']}" stroke-width="1.5"/>
  {hud_corners(w, h, PALETTE["green"], 12)}

  <!-- Card Header -->
  <circle cx="32" cy="30" r="4.5" fill="{PALETTE['green']}" class="led"/>
  <text x="46" y="34" class="mono" font-size="12.5" font-weight="700" fill="{PALETTE['text']}" letter-spacing="1">01 // SYSTEM IDENTITY</text>
  <rect x="434" y="18" width="140" height="22" rx="11" fill="#091B18" stroke="#155E42" stroke-width="1"/>
  <text x="504" y="33" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{PALETTE['green']}">neofetch --omni</text>
  <line x1="24" y1="54" x2="{w - 24}" y2="54" stroke="#152436" stroke-width="1"/>

  {''.join(row_xml)}
  {''.join(meter_xml)}
</svg>
"""


def build_radar_svg() -> str:
    w, h = 600, 340
    cx, cy, max_r = 186, 192, 92

    axes = [
        ("OFFSEC", 1.00, PALETTE["green"]),
        ("FULL-STACK", 0.99, PALETTE["cyan"]),
        ("AI / AGENTS", 0.98, PALETTE["violet"]),
        ("CLOUD / K8S", 0.97, PALETTE["blue"]),
        ("SCADA / OT", 0.98, PALETTE["emerald"]),
        ("SYSTEMS", 0.96, PALETTE["amber"]),
    ]

    rings_xml = []
    for scale in (0.25, 0.50, 0.75, 1.00):
        pts = []
        for i in range(6):
            ang = math.radians(-90 + i * 60)
            px = cx + math.cos(ang) * max_r * scale
            py = cy + math.sin(ang) * max_r * scale
            pts.append(f"{px:.1f},{py:.1f}")
        rings_xml.append(
            f'<polygon points="{" ".join(pts)}" fill="none" stroke="#1A2D42" stroke-width="1" stroke-dasharray="{"4 3" if scale < 1 else "none"}"/>'
        )

    spokes_xml = []
    poly_pts = []
    dots_xml = []
    labels_xml = []
    for i, (name, score, col) in enumerate(axes):
        ang = math.radians(-90 + i * 60)
        ex = cx + math.cos(ang) * max_r
        ey = cy + math.sin(ang) * max_r
        spokes_xml.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#1B3046" stroke-width="1"/>')

        vx = cx + math.cos(ang) * max_r * score
        vy = cy + math.sin(ang) * max_r * score
        poly_pts.append(f"{vx:.1f},{vy:.1f}")
        dots_xml.append(
            f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="4.5" fill="{col}" stroke="#060B12" stroke-width="1.5">'
            f'<animate attributeName="r" values="3.8;5.4;3.8" dur="2.2s" begin="{i * 0.3:.1f}s" repeatCount="indefinite"/>'
            f"</circle>"
        )

        lx = cx + math.cos(ang) * (max_r + 18)
        ly = cy + math.sin(ang) * (max_r + 18)
        anchor = "middle"
        if math.cos(ang) > 0.25:
            anchor = "start"
        elif math.cos(ang) < -0.25:
            anchor = "end"
        if i == 0:
            ly -= 2
        elif i == 3:
            ly += 10
        else:
            ly += 4
        labels_xml.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" class="mono" font-size="10" font-weight="700" fill="{PALETTE["text_sub"]}">{esc(name)}</text>'
        )

    # Legend on the right side
    legend_xml = []
    for i, (name, score, col) in enumerate(axes):
        ly = 88 + i * 40
        pct = int(round(score * 100))
        bar_w = int(round(192 * score))
        legend_xml.append(
            f'<text x="368" y="{ly}" class="mono" font-size="11" font-weight="700" fill="{PALETTE["text"]}">{esc(name)}</text>'
            f'<text x="570" y="{ly}" text-anchor="end" class="mono" font-size="11" font-weight="700" fill="{col}">{pct}%</text>'
            f'<rect x="368" y="{ly + 8}" width="202" height="7" rx="3.5" fill="#132030"/>'
            f'<rect x="368" y="{ly + 8}" width="{bar_w}" height="7" rx="3.5" fill="{col}"/>'
        )

    # Sweep wedge geometry (35 deg arc from center)
    sweep_ang = math.radians(-35)
    sx = cx + math.cos(sweep_ang) * max_r
    sy = cy + math.sin(sweep_ang) * max_r

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Omni-Skill Capability Radar">
  <defs>
    <linearGradient id="radBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070C14"/>
      <stop offset="100%" stop-color="#0C1322"/>
    </linearGradient>
    <linearGradient id="sweepGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00FF88" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#00E5FF" stop-opacity="0.02"/>
    </linearGradient>
    <style>
      .mono {{ font-family: {FONT_MONO}; }}
    </style>
  </defs>

  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16" fill="url(#radBg)" stroke="{PALETTE['border']}" stroke-width="1.5"/>
  {hud_corners(w, h, PALETTE["cyan"], 12)}

  <circle cx="32" cy="30" r="4.5" fill="{PALETTE['cyan']}"/>
  <text x="46" y="34" class="mono" font-size="12.5" font-weight="700" fill="{PALETTE['text']}" letter-spacing="1">02 // OMNI-SKILL RADAR</text>
  <rect x="424" y="18" width="150" height="22" rx="11" fill="#0B1829" stroke="#1E4163" stroke-width="1"/>
  <text x="499" y="33" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{PALETTE['cyan']}">ALL MODULES: 98%</text>
  <line x1="24" y1="54" x2="{w - 24}" y2="54" stroke="#152436" stroke-width="1"/>

  {''.join(rings_xml)}
  {''.join(spokes_xml)}

  <!-- Radar Rotating Sweep -->
  <path d="M {cx} {cy} L {cx} {cy - max_r} A {max_r} {max_r} 0 0 1 {sx:.1f} {sy:.1f} Z" fill="url(#sweepGrad)">
    <animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" to="360 {cx} {cy}" dur="5.5s" repeatCount="indefinite"/>
  </path>

  <!-- Active Coverage Polygon -->
  <polygon points="{' '.join(poly_pts)}" fill="{PALETTE['green']}" fill-opacity="0.16" stroke="{PALETTE['green']}" stroke-width="2" stroke-linejoin="round"/>
  {''.join(dots_xml)}
  {''.join(labels_xml)}

  <!-- Right Divider & Mastery Breakdown -->
  <line x1="346" y1="74" x2="346" y2="318" stroke="#152436" stroke-width="1" stroke-dasharray="3 3"/>
  {''.join(legend_xml)}
</svg>
"""


def build_arsenal_svg() -> str:
    w, h = 1200, 390
    pods = [
        {
            "code": "0x01",
            "title": "OFFENSIVE & DEFENSIVE SEC",
            "color": PALETTE["green"],
            "pct": 100,
            "chips": ["Kali Linux", "Burp Suite", "Metasploit", "Ghidra", "Wireshark", "OWASP", "Zero-Trust"],
        },
        {
            "code": "0x02",
            "title": "AI, ML & AUTONOMOUS AGENTS",
            "color": PALETTE["violet"],
            "pct": 98,
            "chips": ["PyTorch", "TensorFlow", "LangChain", "RAG / VectorDB", "LLM Agents", "Vision", "MLOps"],
        },
        {
            "code": "0x03",
            "title": "FULL-STACK & API SYSTEMS",
            "color": PALETTE["cyan"],
            "pct": 99,
            "chips": ["TypeScript", "React / Next.js", "Node.js", "FastAPI", "PHP / Laravel", "GraphQL", "Tailwind"],
        },
        {
            "code": "0x04",
            "title": "SYSTEMS, KERNEL & CRYPTO",
            "color": PALETTE["amber"],
            "pct": 96,
            "chips": ["Rust", "Go", "C / C++", "x86 / ARM ASM", "WebAssembly", "eBPF", "Bash / Zsh"],
        },
        {
            "code": "0x05",
            "title": "CLOUD, INFRA & DEVSECOPS",
            "color": PALETTE["blue"],
            "pct": 97,
            "chips": ["Kubernetes", "Docker", "Terraform", "AWS / GCP", "CI/CD Actions", "Nginx", "Grafana"],
        },
        {
            "code": "0x06",
            "title": "SCADA, OT & DATA PIPELINES",
            "color": PALETTE["emerald"],
            "pct": 98,
            "chips": ["Modbus / OPC-UA", "PLC / MQTT", "PostgreSQL", "Redis", "MySQL", "Kafka", "TimescaleDB"],
        },
    ]

    pods_xml = []
    pod_w, pod_h = 372, 138
    for idx, pod in enumerate(pods):
        col_i = idx % 3
        row_i = idx // 3
        px = 24 + col_i * (pod_w + 18)
        py = 74 + row_i * (pod_h + 18)
        accent = pod["color"]

        # Flow chips across 2 rows inside pod_w - 32 (340px)
        chips_xml = []
        cx_cursor = px + 16
        cy_cursor = py + 52
        row_num = 0
        for chip in pod["chips"]:
            cw = int(len(chip) * 6.8 + 18)
            if cx_cursor + cw > px + pod_w - 14:
                row_num += 1
                if row_num >= 2:
                    break
                cx_cursor = px + 16
                cy_cursor += 28
            chips_xml.append(
                f'<rect x="{cx_cursor}" y="{cy_cursor}" width="{cw}" height="22" rx="6" fill="#0B131F" stroke="#1E3146" stroke-width="1"/>'
                f'<text x="{cx_cursor + cw / 2:.1f}" y="{cy_cursor + 14.5}" text-anchor="middle" class="mono" font-size="10.5" fill="{PALETTE["text_sub"]}">{esc(chip)}</text>'
            )
            cx_cursor += cw + 7

        bar_total = pod_w - 86
        bar_fill = int(round(bar_total * pod["pct"] / 100.0))

        pods_xml.append(
            f'<rect x="{px}" y="{py}" width="{pod_w}" height="{pod_h}" rx="12" fill="#080E17" stroke="#1B2C40" stroke-width="1.2"/>'
            f'<rect x="{px}" y="{py + 12}" width="3.5" height="24" rx="1.75" fill="{accent}"/>'
            f'<text x="{px + 16}" y="{py + 29}" class="mono" font-size="11.5" font-weight="700" fill="{PALETTE["text"]}">{esc(pod["code"])} // {esc(pod["title"])}</text>'
            f'<circle cx="{px + pod_w - 18}" cy="{py + 24}" r="3.5" fill="{accent}"/>'
            f'{"".join(chips_xml)}'
            f'<rect x="{px + 16}" y="{py + 118}" width="{bar_total}" height="6" rx="3" fill="#132030"/>'
            f'<rect x="{px + 16}" y="{py + 118}" width="{bar_fill}" height="6" rx="3" fill="{accent}"/>'
            f'<text x="{px + pod_w - 16}" y="{py + 124}" text-anchor="end" class="mono" font-size="10.5" font-weight="700" fill="{accent}">{pod["pct"]}%</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Full-Spectrum Polyglot Arsenal Matrix">
  <defs>
    <linearGradient id="arsBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#060A11"/>
      <stop offset="100%" stop-color="#0A121D"/>
    </linearGradient>
    <style>
      .mono {{ font-family: {FONT_MONO}; }}
    </style>
  </defs>

  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16" fill="url(#arsBg)" stroke="{PALETTE['border']}" stroke-width="1.5"/>
  {hud_corners(w, h, PALETTE["green"], 14)}

  <circle cx="32" cy="30" r="4.5" fill="{PALETTE['green']}"/>
  <text x="46" y="34" class="mono" font-size="13" font-weight="700" fill="{PALETTE['text']}" letter-spacing="1">03 // POLYGLOT ARSENAL MATRIX — ALL DOMAINS UNLOCKED</text>
  <rect x="975" y="18" width="198" height="22" rx="11" fill="#091B18" stroke="#155E42" stroke-width="1"/>
  <text x="1074" y="33" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{PALETTE['green']}">6 CLUSTERS • 42+ STACKS</text>
  <line x1="24" y1="54" x2="{w - 24}" y2="54" stroke="#152436" stroke-width="1"/>

  {''.join(pods_xml)}
</svg>
"""


def build_telemetry_stats_svg(data: dict[str, Any]) -> str:
    w, h = 600, 290
    rank, pct, tier = calc_rank(data)
    r = 56
    circ = 2 * math.pi * r
    dash_filled = circ * (pct / 100.0)
    dash_offset = circ - dash_filled

    stats = [
        ("Total Stars Earned", fmt_num(data["stars"]), PALETTE["amber"]),
        ("Yearly Commits", fmt_num(data["commits"]), PALETTE["green"]),
        ("Active Repositories", fmt_num(data["repos"]), PALETTE["cyan"]),
        ("Pull Requests & Issues", f'{fmt_num(data["prs"])} / {fmt_num(data["issues"])}', PALETTE["violet"]),
        ("Followers / Forks", f'{fmt_num(data["followers"])} / {fmt_num(data["forks"])}', PALETTE["blue"]),
    ]

    rows_xml = []
    for idx, (label, val, col) in enumerate(stats):
        ry = 94 + idx * 32
        rows_xml.append(
            f'<rect x="26" y="{ry - 17}" width="340" height="25" rx="6" fill="#0B131E"/>'
            f'<circle cx="40" cy="{ry - 4.5}" r="3.5" fill="{col}"/>'
            f'<text x="54" y="{ry}" class="sans" font-size="12.5" font-weight="500" fill="{PALETTE["text_sub"]}">{esc(label)}</text>'
            f'<text x="352" y="{ry}" text-anchor="end" class="mono" font-size="13" font-weight="700" fill="{col}">{esc(val)}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="GitHub Live Telemetry Stats">
  <defs>
    <linearGradient id="stBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070C14"/>
      <stop offset="100%" stop-color="#0A141E"/>
    </linearGradient>
    <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00FF88"/>
      <stop offset="100%" stop-color="#00E5FF"/>
    </linearGradient>
    <style>
      .mono {{ font-family: {FONT_MONO}; }}
      .sans {{ font-family: {FONT_SANS}; }}
      .ringAnim {{
        stroke-dasharray: {circ:.1f};
        stroke-dashoffset: {dash_offset:.1f};
        animation: ringGrow 1.4s ease-out forwards;
      }}
      @keyframes ringGrow {{
        from {{ stroke-dashoffset: {circ:.1f}; }}
        to {{ stroke-dashoffset: {dash_offset:.1f}; }}
      }}
    </style>
  </defs>

  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16" fill="url(#stBg)" stroke="{PALETTE['border']}" stroke-width="1.5"/>
  {hud_corners(w, h, PALETTE["green"], 12)}

  <circle cx="32" cy="30" r="4.5" fill="{PALETTE['green']}"/>
  <text x="46" y="34" class="mono" font-size="12.5" font-weight="700" fill="{PALETTE['text']}" letter-spacing="1">04 // GITHUB TELEMETRY</text>
  <rect x="412" y="18" width="162" height="22" rx="11" fill="#091B18" stroke="#155E42" stroke-width="1"/>
  <text x="493" y="33" text-anchor="middle" class="mono" font-size="10" font-weight="700" fill="{PALETTE['green']}">{esc(data['source'])}</text>
  <line x1="24" y1="54" x2="{w - 24}" y2="54" stroke="#152436" stroke-width="1"/>

  {''.join(rows_xml)}

  <!-- Right Rank Gauge -->
  <rect x="386" y="74" width="188" height="172" rx="12" fill="#080E17" stroke="#192A3D" stroke-width="1"/>
  <circle cx="480" cy="146" r="{r}" fill="none" stroke="#152334" stroke-width="8"/>
  <circle cx="480" cy="146" r="{r}" fill="none" stroke="url(#ringGrad)" stroke-width="8" stroke-linecap="round" transform="rotate(-90 480 146)" class="ringAnim"/>
  <text x="480" y="149" text-anchor="middle" class="sans" font-size="30" font-weight="900" fill="{PALETTE['green']}">{esc(rank)}</text>
  <text x="480" y="168" text-anchor="middle" class="mono" font-size="10" font-weight="700" fill="{PALETTE['cyan']}">{pct}th PCT</text>
  <text x="480" y="228" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{PALETTE['text_sub']}" letter-spacing="0.8">{esc(tier)}</text>

  <text x="28" y="271" class="mono" font-size="10" fill="{PALETTE['muted']}">LAST SYNC: {esc(data['synced_at'])}  •  AUTO-UPDATED VIA GITHUB ACTIONS</text>
</svg>
"""


def build_languages_svg(data: dict[str, Any]) -> str:
    w, h = 600, 290
    langs = data["languages"][:6]
    bar_x, bar_y, bar_w, bar_h = 26, 78, 548, 14

    segments_xml = []
    cur_x = float(bar_x)
    total_pct = sum(item["pct"] for item in langs) or 100.0
    for idx, item in enumerate(langs):
        seg_w = (item["pct"] / total_pct) * bar_w
        if idx == len(langs) - 1:
            seg_w = (bar_x + bar_w) - cur_x
        segments_xml.append(
            f'<rect x="{cur_x:.2f}" y="{bar_y}" width="{max(2.0, seg_w):.2f}" height="{bar_h}" fill="{esc(item["color"])}"/>'
        )
        cur_x += seg_w

    items_xml = []
    for idx, item in enumerate(langs):
        col_i = idx % 2
        row_i = idx // 2
        ix = 26 + col_i * 282
        iy = 122 + row_i * 44
        fill_w = int(round(244 * min(100.0, item["pct"]) / 100.0))
        items_xml.append(
            f'<rect x="{ix}" y="{iy - 10}" width="266" height="36" rx="8" fill="#0B131E"/>'
            f'<circle cx="{ix + 14}" cy="{iy + 3}" r="4.5" fill="{esc(item["color"])}"/>'
            f'<text x="{ix + 26}" y="{iy + 7}" class="mono" font-size="12" font-weight="700" fill="{PALETTE["text"]}">{esc(item["name"])}</text>'
            f'<text x="{ix + 254}" y="{iy + 7}" text-anchor="end" class="mono" font-size="12" font-weight="700" fill="{PALETTE["cyan"]}">{item["pct"]:.1f}%</text>'
            f'<rect x="{ix + 12}" y="{iy + 16}" width="242" height="4" rx="2" fill="#152334"/>'
            f'<rect x="{ix + 12}" y="{iy + 16}" width="{max(8, fill_w)}" height="4" rx="2" fill="{esc(item["color"])}"/>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Runtime Language Distribution">
  <defs>
    <linearGradient id="lgBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070C14"/>
      <stop offset="100%" stop-color="#0C1322"/>
    </linearGradient>
    <clipPath id="barClip">
      <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="7"/>
    </clipPath>
    <style>
      .mono {{ font-family: {FONT_MONO}; }}
    </style>
  </defs>

  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16" fill="url(#lgBg)" stroke="{PALETTE['border']}" stroke-width="1.5"/>
  {hud_corners(w, h, PALETTE["cyan"], 12)}

  <circle cx="32" cy="30" r="4.5" fill="{PALETTE['cyan']}"/>
  <text x="46" y="34" class="mono" font-size="12.5" font-weight="700" fill="{PALETTE['text']}" letter-spacing="1">05 // RUNTIME LANGUAGES</text>
  <rect x="434" y="18" width="140" height="22" rx="11" fill="#0B1829" stroke="#1E4163" stroke-width="1"/>
  <text x="504" y="33" text-anchor="middle" class="mono" font-size="10" font-weight="700" fill="{PALETTE['cyan']}">CODEBASE RATIO</text>
  <line x1="24" y1="54" x2="{w - 24}" y2="54" stroke="#152436" stroke-width="1"/>

  <g clip-path="url(#barClip)">
    {''.join(segments_xml)}
  </g>

  {''.join(items_xml)}

  <text x="28" y="271" class="mono" font-size="10" fill="{PALETTE['muted']}">WEIGHTED BY REPOSITORY BYTEFOOTPRINT + POLYGLOT TOOLING</text>
</svg>
"""


def build_contribution_pulse_svg(data: dict[str, Any]) -> str:
    w, h = 1200, 255
    weeks = data["weeks"][-52:]

    def cell_color(cnt: int) -> str:
        if cnt <= 0:
            return "#101A26"
        if cnt <= 2:
            return "#094D30"
        if cnt <= 4:
            return "#009955"
        if cnt <= 6:
            return "#00D474"
        return "#00FF88"

    cells_xml = []
    weekly_totals = []
    for wi, week in enumerate(weeks):
        tot = 0
        for di, day in enumerate(week[:7]):
            cnt = int(day.get("contributionCount", 0))
            tot += cnt
            cx = 28 + wi * 12
            cy = 92 + di * 15
            cells_xml.append(
                f'<rect x="{cx}" y="{cy}" width="9.5" height="11.5" rx="2.5" fill="{cell_color(cnt)}"/>'
            )
        weekly_totals.append(tot)

    # Smooth SVG activity wave on the right panel (x: 682..1168, y: 92..210)
    wx0, wx1 = 684, 1166
    wy_base, wy_amp = 204, 88
    max_tot = max(weekly_totals) if weekly_totals else 1
    max_tot = max(max_tot, 1)
    sample = weekly_totals if weekly_totals else [0]
    pts = []
    for i, val in enumerate(sample):
        px = wx0 + (i / max(1, len(sample) - 1)) * (wx1 - wx0)
        py = wy_base - (val / max_tot) * wy_amp
        pts.append((px, py))

    # Build smooth cubic spline path
    if len(pts) >= 2:
        d_parts = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
        for i in range(1, len(pts)):
            p0 = pts[i - 1]
            p1 = pts[i]
            mx = (p0[0] + p1[0]) / 2.0
            d_parts.append(f"C {mx:.1f} {p0[1]:.1f}, {mx:.1f} {p1[1]:.1f}, {p1[0]:.1f} {p1[1]:.1f}")
        wave_d = " ".join(d_parts)
        area_d = f"{wave_d} L {pts[-1][0]:.1f} {wy_base + 8} L {pts[0][0]:.1f} {wy_base + 8} Z"
    else:
        wave_d = f"M {wx0} {wy_base} L {wx1} {wy_base}"
        area_d = f"{wave_d} L {wx1} {wy_base + 8} L {wx0} {wy_base + 8} Z"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Neural Contribution Matrix and Wave">
  <defs>
    <linearGradient id="cpBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#060A11"/>
      <stop offset="100%" stop-color="#0A131E"/>
    </linearGradient>
    <linearGradient id="waveArea" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#00FF88" stop-opacity="0.32"/>
      <stop offset="100%" stop-color="#00FF88" stop-opacity="0.01"/>
    </linearGradient>
    <style>
      .mono {{ font-family: {FONT_MONO}; }}
      .laserTrace {{
        stroke-dasharray: 65 900;
        animation: tracePulse 3.4s linear infinite;
      }}
      @keyframes tracePulse {{
        from {{ stroke-dashoffset: 965; }}
        to {{ stroke-dashoffset: 0; }}
      }}
    </style>
  </defs>

  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16" fill="url(#cpBg)" stroke="{PALETTE['border']}" stroke-width="1.5"/>
  {hud_corners(w, h, PALETTE["green"], 14)}

  <circle cx="32" cy="30" r="4.5" fill="{PALETTE['green']}"/>
  <text x="46" y="34" class="mono" font-size="13" font-weight="700" fill="{PALETTE['text']}" letter-spacing="1">06 // NEURAL CONTRIBUTION MATRIX &amp; PULSE</text>

  <!-- Summary KPI Chips -->
  <rect x="598" y="17" width="184" height="24" rx="12" fill="#0A1B16" stroke="#155E42" stroke-width="1"/>
  <text x="690" y="33" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{PALETTE['green']}">365D: {esc(fmt_num(data['total_contributions']))} EVENTS</text>

  <rect x="794" y="17" width="182" height="24" rx="12" fill="#1A1508" stroke="#664B10" stroke-width="1"/>
  <text x="885" y="33" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{PALETTE['amber']}">STREAK: {data['current_streak']} DAYS</text>

  <rect x="988" y="17" width="186" height="24" rx="12" fill="#0B1829" stroke="#1E4163" stroke-width="1"/>
  <text x="1081" y="33" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{PALETTE['cyan']}">BEST: {data['longest_streak']} DAYS</text>

  <line x1="24" y1="54" x2="{w - 24}" y2="54" stroke="#152436" stroke-width="1"/>

  <text x="28" y="78" class="mono" font-size="10.5" font-weight="700" fill="{PALETTE['muted']}">52-WEEK ACTIVITY MATRIX</text>
  <text x="684" y="78" class="mono" font-size="10.5" font-weight="700" fill="{PALETTE['muted']}">52-WEEK COMMIT VELOCITY SPLINE</text>

  {''.join(cells_xml)}

  <!-- Heatmap Legend -->
  <text x="28" y="226" class="mono" font-size="10" fill="{PALETTE['muted']}">INTENSITY: LOW</text>
  <rect x="122" y="217" width="10" height="10" rx="2" fill="#101A26"/>
  <rect x="136" y="217" width="10" height="10" rx="2" fill="#094D30"/>
  <rect x="150" y="217" width="10" height="10" rx="2" fill="#009955"/>
  <rect x="164" y="217" width="10" height="10" rx="2" fill="#00D474"/>
  <rect x="178" y="217" width="10" height="10" rx="2" fill="#00FF88"/>
  <text x="194" y="226" class="mono" font-size="10" fill="{PALETTE['muted']}">PEAK</text>

  <!-- Right Wave Box -->
  <rect x="674" y="90" width="502" height="136" rx="10" fill="#080F18" stroke="#16283C" stroke-width="1"/>
  <line x1="684" y1="135" x2="1166" y2="135" stroke="#132234" stroke-width="1" stroke-dasharray="3 4"/>
  <line x1="684" y1="175" x2="1166" y2="175" stroke="#132234" stroke-width="1" stroke-dasharray="3 4"/>
  <path d="{area_d}" fill="url(#waveArea)"/>
  <path d="{wave_d}" fill="none" stroke="#00663A" stroke-width="2.2" stroke-linecap="round"/>
  <path d="{wave_d}" fill="none" stroke="{PALETTE['green']}" stroke-width="2.8" stroke-linecap="round" class="laserTrace"/>
  <circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="4.5" fill="{PALETTE['cyan']}" stroke="#060A11" stroke-width="1.5"/>
</svg>
"""


def build_repo_card_svg(repo: dict[str, Any]) -> str:
    w, h = 590, 180
    accent = repo["accent"]
    lang = repo["language"]
    lcolor = LANG_COLORS.get(lang, accent)
    wrapped = textwrap.wrap(repo["description"], width=62)[:2]
    line1 = wrapped[0] if wrapped else ""
    line2 = wrapped[1] if len(wrapped) > 1 else ""
    if len(textwrap.wrap(repo["description"], width=62)) > 2 and len(line2) > 3:
        line2 = line2[:-3].rstrip() + "..."

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Repository {esc(repo['name'])}">
  <defs>
    <linearGradient id="rpBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070C14"/>
      <stop offset="100%" stop-color="#0C1420"/>
    </linearGradient>
    <style>
      .mono {{ font-family: {FONT_MONO}; }}
      .sans {{ font-family: {FONT_SANS}; }}
    </style>
  </defs>

  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="14" fill="url(#rpBg)" stroke="{PALETTE['border']}" stroke-width="1.5"/>
  <rect x="1" y="16" width="3.5" height="{h - 32}" rx="1.75" fill="{accent}"/>

  <!-- Header -->
  <text x="24" y="34" class="mono" font-size="10.5" font-weight="700" fill="{accent}" letter-spacing="1">{esc(repo['code'])}</text>
  <rect x="448" y="18" width="120" height="22" rx="11" fill="#0B131F" stroke="#1E3348" stroke-width="1"/>
  <text x="508" y="33" text-anchor="middle" class="mono" font-size="10" font-weight="700" fill="{PALETTE['cyan']}">{esc(repo['tag'])}</text>

  <!-- Repo Title -->
  <text x="24" y="66" class="sans" font-size="21" font-weight="800" fill="{PALETTE['text']}">{esc(repo['name'])}</text>

  <!-- Description -->
  <text x="24" y="96" class="sans" font-size="13" fill="{PALETTE['text_sub']}">{esc(line1)}</text>
  <text x="24" y="116" class="sans" font-size="13" fill="{PALETTE['text_sub']}">{esc(line2)}</text>

  <!-- Footer Strip -->
  <line x1="24" y1="136" x2="{w - 24}" y2="136" stroke="#152436" stroke-width="1"/>
  <circle cx="30" cy="157" r="5" fill="{esc(lcolor)}"/>
  <text x="42" y="161" class="mono" font-size="11.5" font-weight="600" fill="{PALETTE['text']}">{esc(lang)}</text>

  <!-- Vector Star Icon -->
  <polygon points="160,150 162,154.5 167,155 163.3,158.2 164.4,163 160,160.4 155.6,163 156.7,158.2 153,155 158,154.5" fill="{PALETTE['amber']}"/>
  <text x="172" y="161" class="mono" font-size="11.5" fill="{PALETTE['amber']}">{repo['stars']}</text>

  <!-- Vector Fork Icon -->
  <g stroke="{PALETTE['muted']}" stroke-width="1.4" fill="none" stroke-linecap="round">
    <circle cx="218" cy="152" r="2"/>
    <circle cx="226" cy="152" r="2"/>
    <circle cx="222" cy="162" r="2"/>
    <path d="M 218 154 C 218 158, 222 157, 222 160 M 226 154 C 226 158, 222 157, 222 160"/>
  </g>
  <text x="234" y="161" class="mono" font-size="11.5" fill="{PALETTE['muted']}">{repo['forks']}</text>

  <circle cx="430" cy="157" r="3.5" fill="{PALETTE['green']}"/>
  <text x="440" y="161" class="mono" font-size="11" font-weight="700" fill="{PALETTE['green']}">INSPECT PAYLOAD</text>
  <path d="M 552 160 L 560 152 M 554 152 L 560 152 L 560 158" fill="none" stroke="{PALETTE['green']}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


def build_footer_svg() -> str:
    w, h = 1200, 130
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Terminal Session Footer">
  <defs>
    <linearGradient id="ftBg" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#05080F"/>
      <stop offset="50%" stop-color="#08151B"/>
      <stop offset="100%" stop-color="#05080F"/>
    </linearGradient>
    <linearGradient id="waveLine" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#00FF88" stop-opacity="0.15"/>
      <stop offset="50%" stop-color="#00E5FF" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="#00FF88" stop-opacity="0.15"/>
    </linearGradient>
    <clipPath id="ftClip">
      <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16"/>
    </clipPath>
    <style>
      .mono {{ font-family: {FONT_MONO}; }}
    </style>
  </defs>

  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16" fill="url(#ftBg)" stroke="{PALETTE['border']}" stroke-width="1.5"/>
  <g clip-path="url(#ftClip)">
    <path d="M 0 92 Q 150 56 300 92 T 600 92 T 900 92 T 1200 92 L 1200 130 L 0 130 Z" fill="#00FF88" fill-opacity="0.06">
      <animate attributeName="d"
        values="M 0 92 Q 150 56 300 92 T 600 92 T 900 92 T 1200 92 L 1200 130 L 0 130 Z;
                M 0 88 Q 150 118 300 88 T 600 88 T 900 88 T 1200 88 L 1200 130 L 0 130 Z;
                M 0 92 Q 150 56 300 92 T 600 92 T 900 92 T 1200 92 L 1200 130 L 0 130 Z"
        dur="7s" repeatCount="indefinite"/>
    </path>
    <path d="M 0 82 Q 200 108 400 82 T 800 82 T 1200 82" fill="none" stroke="url(#waveLine)" stroke-width="1.6"/>
  </g>
  {hud_corners(w, h, PALETTE["green"], 12)}

  <text x="600" y="48" text-anchor="middle" class="mono" font-size="13" font-weight="700" fill="{PALETTE['green']}" letter-spacing="1.2">root@tumbaltok:~# history -c &amp;&amp; echo "SESSION TERMINATED SAFELY // ZERO TRACES LEFT BEHIND"</text>
  <text x="600" y="74" text-anchor="middle" class="mono" font-size="11" fill="{PALETTE['muted']}" letter-spacing="1.8">0xTUMBALTOK • SECURITY • SYSTEMS • AI • FULL-STACK • SCADA/OT</text>
</svg>
"""


def write_and_validate(filename: str, svg_content: str) -> None:
    # Validate strict XML syntax before writing
    ET.fromstring(svg_content.encode("utf-8"))
    out_path = ASSETS_DIR / filename
    out_path.write_text(svg_content, encoding="utf-8")
    print(f"[ok] generated & validated {out_path.relative_to(ROOT_DIR)}")


def main() -> int:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    data = fetch_github_telemetry()

    outputs = {
        "hero-command-deck.svg": build_hero_svg(data),
        "bento-identity.svg": build_identity_svg(data),
        "bento-radar.svg": build_radar_svg(),
        "arsenal-matrix.svg": build_arsenal_svg(),
        "telemetry-stats.svg": build_telemetry_stats_svg(data),
        "telemetry-languages.svg": build_languages_svg(data),
        "contribution-pulse.svg": build_contribution_pulse_svg(data),
        "footer-wave.svg": build_footer_svg(),
    }

    slug_map = {
        "ndok-scada": "repo-ndok-scada.svg",
        "umbulan": "repo-umbulan.svg",
        "shordlink": "repo-shordlink.svg",
        "tehtawa": "repo-tehtawa.svg",
    }
    for repo in data["featured"]:
        key = repo["name"].lower()
        fname = slug_map.get(key, f"repo-{key}.svg")
        outputs[fname] = build_repo_card_svg(repo)

    for fname, content in outputs.items():
        write_and_validate(fname, content)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
