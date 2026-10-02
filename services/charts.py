#!/usr/bin/env python3
"""Data-driven charts for the newsletter: honest aggregates only.

Every chart is computed from the curated items of the current edition —
no invented figures. If a chart can't be honestly computed (e.g. no
funding rounds found in the window), it is omitted entirely.

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
from pathlib import Path

from .curator import extract_funding, source_name, source_tier

# Editorial palette (matches the site's light theme).
PAPER = "#fbfaf7"
INK = "#1d1a16"
MUTED = "#6f675c"
ACCENT = "#b0511f"
ACCENT_SOFT = "#d99a6c"
LINE = "#e9e2d6"

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
    if not raises:
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
    if len(counts) < 2:
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
    if len(counts) < 2:
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


def volume_chart(curated):
    """Story volume per section."""
    titles = {"signal": "The Signal", "tech": "The Wider Current",
              "startups": "Startups", "podcasts": "Podcast Circuit"}
    data = [{"label": titles.get(s, s), "value": len(items),
             "detail": f"{len(items)} stories"}
            for s, items in curated.items() if items]
    if len(data) < 2:
        return None
    return {
        "id": "volume",
        "title": "The edition by section",
        "subtitle": "Story count per section",
        "kind": "bar",
        "unit": "stories",
        "data": data,
        "note": "Curated items per section in this edition.",
    }


def build_charts(curated):
    """Compute all honest charts. Returns the list of chart specs."""
    charts = []
    for fn in (funding_chart, momentum_chart, source_mix_chart, volume_chart):
        spec = fn(curated)
        if spec:
            charts.append(spec)
    return charts


# ---------------------------------------------------------------- PNG export

def render_png(spec, path, width_in=7.2):
    """Render one chart spec to PNG in the editorial palette."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [d["label"] for d in spec["data"]]
    values = [d["value"] for d in spec["data"]]
    n = len(labels)
    height_in = max(2.2, 0.62 * n + 1.4)

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=160)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)

    colors = []
    for d in spec["data"]:
        tier = d.get("tier")
        colors.append(ACCENT if tier in (None, 1) else
                      ACCENT_SOFT if tier == 2 else "#c9bfae")

    if spec["kind"] == "hbar":
        y = list(range(n))[::-1]
        ax.barh(y, values, height=0.55, color=colors, edgecolor="none")
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=10, color=INK,
                           fontfamily="serif")
        for yy, v, d in zip(y, values, spec["data"]):
            ax.text(v, yy, f"  {d.get('detail') or v}", va="center",
                    fontsize=9, color=MUTED)
        ax.set_ylim(-0.8, n - 0.2)
    else:
        x = list(range(n))
        bars = ax.bar(x, values, width=0.55, color=colors, edgecolor="none")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10, color=INK, fontfamily="serif",
                           rotation=0, ha="center")
        for b, v, d in zip(bars, values, spec["data"]):
            ax.text(b.get_x() + b.get_width() / 2, v,
                    f"{d.get('detail') or v}", ha="center", va="bottom",
                    fontsize=9, color=MUTED)

    ax.set_title(spec["title"], fontsize=14, color=INK, fontfamily="serif",
                 loc="left", pad=6)
    ax.text(0, 1.06, spec["subtitle"], transform=ax.transAxes, fontsize=9,
            color=MUTED, va="bottom", ha="left")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(left=False, bottom=False)
    ax.set_xticks([]) if spec["kind"] == "hbar" else ax.set_yticks([])
    ax.grid(False)
    fig.tight_layout(pad=1.2)
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
