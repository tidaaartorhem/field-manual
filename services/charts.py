#!/usr/bin/env python3
"""Data-driven charts for the newsletter: honest aggregates only.

Every chart is computed from the curated items of the current edition —
no invented figures. If a chart can't be honestly computed (e.g. no
funding rounds found in the window), it is omitted entirely.

Hard rules:
- MIN_DATA_POINTS: a chart with fewer than 3 data points is never
  emitted. A one-bar chart says nothing.
- No filler charts: nothing here may chart the pipeline's own config
  (e.g. "edition by section" curation targets) — signal only.

Two outputs:
1. ``data/charts.json`` — chart specs the React frontend renders as SVG.
2. ``web/public/charts/<edition-id>/<chart-id>.png`` — matplotlib renders
   of the same specs, hosted on the live site for the email edition.

Chart spec shape::

    {"id": "funding", "title": "...", "subtitle": "...",
     "kind": "bar" | "hbar", "unit": "$M" | "stories" | "mentions",
     "data": [{"label": str, "value": number, "detail": str|None}],
     "note": "how this was computed"}
"""
import json
import textwrap
from pathlib import Path

from .curator import extract_funding, source_name, source_tier

# Editorial palette (matches the site's light theme).
PAPER = "#fbfaf7"
INK = "#1d1a16"
MUTED = "#6f675c"
ACCENT = "#b0511f"
ACCENT_SOFT = "#d99a6c"
LINE = "#e9e2d6"

# A chart with fewer points than this is decoration, not information.
MIN_DATA_POINTS = 3

MOMENTUM_KEYWORDS = [
    ("AI agents", ("agent", "agents", "agentic")),
    ("LLMs", ("llm", "large language model", "gpt", "Muse", "gemini")),
    ("Funding", ("funding", "raised", "raise", "series", "seed round")),
    ("Launches", ("launch", "launches", "launched", "debut", "unveil")),
    ("Open source", ("open source", "open-source", "open weights")),
    ("Evals", ("eval", "benchmark", "leaderboard")),
    ("Chips & infra", ("chip", "gpu", "datacenter", "semiconductor", "nvidia")),
    ("Regulation", ("regulation", "antitrust", "lawsuit", "copyright")),
    ("Robotics", ("robot", "humanoid", "embodied")),
    ("Enterprise AI", ("enterprise", "copilot", "workflow", "b2b")),
]


def _all_items(curated):
    for items in curated.values():
        yield from items


def funding_chart(curated):
    """Bar chart of raises found in the startups section + total."""
    raises = []
    for item in curated.get("startups", []):
        f = extract_funding(item)
        if f:
            raises.append(f)
    # Also scan other shelves: funding news sometimes lands in tech.
    for item in curated.get("tech", []):
        f = extract_funding(item)
        if f and all(r["source_url"] != f["source_url"] for r in raises):
            raises.append(f)
    if len(raises) < MIN_DATA_POINTS:
        return None
    raises.sort(key=lambda r: -r["amount_usd"])
    top = raises[:8]
    total = sum(r["amount_usd"] for r in raises)
    data = [{
        "label": r["company"][:28],
        "value": round(r["amount_usd"] / 1e6, 1),
        "detail": f"${r['amount_usd']/1e6:.0f}M" + (f" · {r['round']}" if r["round"] else ""),
    } for r in top]
    noun = "round" if len(raises) == 1 else "rounds"
    return {
        "id": "funding",
        "title": "Startup money in the window",
        "subtitle": f"${total/1e6:,.0f}M raised across {len(raises)} {noun}",
        "kind": "hbar",
        "unit": "$M",
        "data": data,
        "note": f"Parsed from {len(raises)} raise announcements in this edition.",
    }


def momentum_chart(curated):
    """Which topics spiked: keyword mentions across all items."""
    counts = []
    for label, keys in MOMENTUM_KEYWORDS:
        n = 0
        for item in _all_items(curated):
            blob = f"{item.get('title','')} {item.get('description','')}".lower()
            if any(k in blob for k in keys):
                n += 1
        if n >= 2:
            counts.append({"label": label, "value": n, "detail": f"{n} stories"})
    if len(counts) < MIN_DATA_POINTS:
        return None
    counts.sort(key=lambda c: -c["value"])
    return {
        "id": "momentum",
        "title": "What's spiking",
        "subtitle": "Topic mentions across every story in this edition",
        "kind": "hbar",
        "unit": "mentions",
        "data": counts[:8],
        "note": "Keyword hits across titles and descriptions; not sentiment.",
    }


def source_mix_chart(curated):
    """Stories per outlet, tinted by reliability tier."""
    from collections import Counter
    counts = Counter()
    tiers = {}
    for item in _all_items(curated):
        src = source_name(item.get("url", ""))
        counts[src] += 1
        tiers[src] = source_tier(item.get("url", ""))
    if len(counts) < MIN_DATA_POINTS:
        return None
    data = [{"label": s[:26], "value": n, "detail": f"tier {tiers[s]}",
             "tier": tiers[s]}
            for s, n in counts.most_common(8)]
    return {
        "id": "sources",
        "title": "Where the signal came from",
        "subtitle": f"{len(counts)} outlets · tier 1 = primary sources",
        "kind": "hbar",
        "unit": "stories",
        "data": data,
        "note": "Tier 1: official announcements/papers. Tier 2: newsrooms. Tier 3: blogs/wires.",
    }


def build_charts(curated):
    """Compute all honest charts. Returns the list of chart specs."""
    charts = []
    for fn in (funding_chart, momentum_chart, source_mix_chart):
        spec = fn(curated)
        if spec:
            charts.append(spec)
    return charts


# ---------------------------------------------------------------- PNG export

def _draw_header(fig, spec):
    """Title + subtitle as separate figure-coordinate text artists.

    The subtitle is positioned by *measuring* the rendered title: after an
    initial draw, the subtitle is placed a fixed gap below the title's
    bounding box, then the header's bottom edge is measured again. The
    caller places the axes below that edge. The title can never render on
    top of the subtitle, regardless of length (long titles wrap).
    Returns (title_artist, subtitle_artist, header_bottom_fig_y).
    """
    title = "\n".join(textwrap.wrap(spec["title"], width=58))
    subtitle = "\n".join(textwrap.wrap(spec["subtitle"], width=88))
    t = fig.text(0.07, 0.96, title, fontsize=15, color=INK,
                 fontfamily="serif", ha="left", va="top", linespacing=1.3)
    # Temporary spot; repositioned after the title is measured.
    s = fig.text(0.07, 0.5, subtitle, fontsize=10.5, color=MUTED,
                 ha="left", va="top", linespacing=1.25)

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    title_bb = t.get_window_extent(renderer=renderer)
    fig_h_pt = fig.get_figheight() * 72
    inv = fig.transFigure.inverted()
    _, title_bottom = inv.transform((0, title_bb.y0))
    gap = 12 / fig_h_pt
    s.set_position((0.07, title_bottom - gap))

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    sub_bb = s.get_window_extent(renderer=renderer)
    _, sub_bottom = inv.transform((0, sub_bb.y0))
    header_bottom = sub_bottom - 10 / fig_h_pt
    return t, s, header_bottom


def render_png(spec, path, width_in=7.2):
    """Render one chart spec to PNG in the editorial palette.

    The header (title/subtitle) is drawn first and measured; the axes are
    placed below the measured header bottom. No tight_layout, no
    transAxes guessing — the two text blocks can never overlap or clip.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [d["label"] for d in spec["data"]]
    values = [d["value"] for d in spec["data"]]
    n = len(labels)
    hbar = spec["kind"] == "hbar"

    height_in = max(3.4, 0.72 * n + 2.0) if hbar else 4.2
    fig = plt.figure(figsize=(width_in, height_in), dpi=160)
    fig.patch.set_facecolor(PAPER)

    _, _, header_bottom = _draw_header(fig, spec)
    axes_top = header_bottom - 0.03
    if hbar:
        # Left gutter sized for serif category labels.
        ax = fig.add_axes([0.30, 0.05, 0.66, axes_top - 0.05])
    else:
        ax = fig.add_axes([0.08, 0.12, 0.88, axes_top - 0.12])
    ax.set_facecolor(PAPER)

    colors = []
    for d in spec["data"]:
        tier = d.get("tier")
        colors.append(ACCENT if tier in (None, 1) else
                      ACCENT_SOFT if tier == 2 else "#c9bfae")

    if hbar:
        y = list(range(n))[::-1]
        ax.barh(y, values, height=0.52, color=colors, edgecolor="none")
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=11, color=INK,
                           fontfamily="serif")
        # Headroom so value labels never run off the right edge.
        ax.set_xlim(0, max(values) * 1.32)
        for yy, v, d in zip(y, values, spec["data"]):
            ax.text(v, yy, f"  {d.get('detail') or v}", va="center",
                    fontsize=10, color=MUTED)
        ax.set_ylim(-0.9, n - 0.1)
        ax.set_xticks([])
        ax.tick_params(left=False)
    else:
        x = list(range(n))
        bars = ax.bar(x, values, width=0.55, color=colors, edgecolor="none")
        ax.set_xticks(x)
        rot = 25 if n > 5 else 0
        ax.set_xticklabels(labels, fontsize=11, color=INK, fontfamily="serif",
                           rotation=rot, ha="right" if rot else "center")
        ax.set_ylim(0, max(values) * 1.25)
        for b, v, d in zip(bars, values, spec["data"]):
            ax.text(b.get_x() + b.get_width() / 2, v,
                    f"{d.get('detail') or v}", ha="center", va="bottom",
                    fontsize=10, color=MUTED)
        ax.set_yticks([])
        ax.tick_params(bottom=False)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=PAPER)
    plt.close(fig)
    return path


def write_charts(charts, edition_id, data_dir=None, public_dir=None):
    """Write data/charts.json + PNGs to web/public/charts/<edition>/. Returns paths."""
    root = Path(__file__).resolve().parent.parent
    data_dir = Path(data_dir) if data_dir else root / "data"
    public_dir = (Path(public_dir) if public_dir
                  else root / "web" / "public" / "charts" / edition_id)
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {"edition": edition_id, "charts": charts}
    json_path = data_dir / "charts.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    png_paths = []
    for spec in charts:
        png_paths.append(render_png(spec, public_dir / f"{spec['id']}.png"))
    return json_path, png_paths
