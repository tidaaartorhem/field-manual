#!/usr/bin/env python3
"""Assemble an edition: ids, start_here, TOC, taglines, stats.

Reads curated items, builds the exact ``data/manual.json`` shape from
SCHEMA.md, validates it, and renders a readable ``data/manual.md``.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

SHELF_ORDER = ["papers", "courses", "news", "career"]

SHELF_META = {
    "papers": {
        "title": "Papers",
        "tagline": "The research that decides what the rest of the industry argues about next year.",
    },
    "courses": {
        "title": "Courses & Certifications",
        "tagline": "Structured paths to put 'agentic AI' on your resume with conviction.",
    },
    "news": {
        "title": "News",
        "tagline": "Shipped, launched, and adopted — what the agent ecosystem actually did lately.",
    },
    "career": {
        "title": "Resume-adjacent",
        "tagline": "The market for people who make AI work inside real companies, decoded from the listings.",
    },
}


def validate_manual(manual):
    """Raise ValueError if the edition doesn't match the SCHEMA.md shape."""
    for key in ("edition", "generated_at", "shelves", "start_here", "stats"):
        if key not in manual:
            raise ValueError(f"missing top-level key: {key}")
    if not isinstance(manual["shelves"], list) or not manual["shelves"]:
        raise ValueError("shelves must be a non-empty list")
    seen_ids = set()
    for shelf in manual["shelves"]:
        for key in ("id", "title", "tagline", "items"):
            if key not in shelf:
                raise ValueError(f"shelf missing key: {key}")
        for item in shelf["items"]:
            for key in ("id", "title", "url", "source", "published", "shelf",
                        "score", "briefing", "takeaways", "queries"):
                if key not in item:
                    raise ValueError(f"item missing key: {key} ({item.get('id')})")
            if item["id"] in seen_ids:
                raise ValueError(f"duplicate item id: {item['id']}")
            seen_ids.add(item["id"])
            if not isinstance(item["url"], str) or not item["url"].startswith("http"):
                raise ValueError(f"bad url on {item['id']}: {item['url']!r}")
            if not (0.0 <= item["score"] <= 1.0):
                raise ValueError(f"score out of range on {item['id']}")
            for key in ("lede", "what_happened", "why_it_matters", "steal_this"):
                if key not in item["briefing"] or not item["briefing"][key]:
                    raise ValueError(f"briefing missing {key} on {item['id']}")
            if not isinstance(item["takeaways"], list) or not item["takeaways"]:
                raise ValueError(f"takeaways empty on {item['id']}")
            if not isinstance(item["queries"], list) or not item["queries"]:
                raise ValueError(f"queries empty on {item['id']}")
    for sid in manual["start_here"]:
        if sid not in seen_ids:
            raise ValueError(f"start_here references unknown id: {sid}")
    stats = manual["stats"]
    n = sum(len(s["items"]) for s in manual["shelves"])
    if stats.get("items") != n or stats.get("shelves") != len(manual["shelves"]):
        raise ValueError("stats inconsistent with content")


def compile_edition(curated, edition_date=None):
    """Assemble + validate the edition dict. ``curated`` is {shelf: [items]}."""
    from . import writer
    from .curator import source_name, extract_published

    writer.reset_run_state()
    edition_date = edition_date or datetime.now(timezone.utc).date().isoformat()
    shelves = []
    sources = set()

    for shelf in SHELF_ORDER:
        items = list(curated.get(shelf, []))
        items.sort(key=lambda i: (-i.get("score", 0), i.get("title", "")))
        out_items = []
        for idx, item in enumerate(items, 1):
            item_id = f"{shelf}-{idx:03d}"
            url = item.get("url", "")
            briefing, takeaways, _src = writer._briefing_with_source(
                {**item, "id": item_id}, shelf)
            out = {
                "id": item_id,
                "title": (item.get("title") or "Untitled").strip(),
                "url": url,
                "source": source_name(url),
                "published": extract_published(
                    f"{item.get('title','')} {item.get('description','')}", url),
                "shelf": shelf,
                "score": round(float(item.get("score", 0)), 2),
                "briefing": briefing,
                "takeaways": takeaways,
                "queries": list(item.get("queries", [])),
            }
            sources.add(out["source"])
            out_items.append(out)
        shelves.append({
            "id": shelf,
            "title": SHELF_META[shelf]["title"],
            "tagline": SHELF_META[shelf]["tagline"],
            "items": out_items,
        })

    # start_here: top 2 papers + top news + top course, in shelf order.
    by_shelf = {s["id"]: s["items"] for s in shelves}
    start_here = []
    for sid in by_shelf.get("papers", [])[:2]:
        start_here.append(sid["id"])
    for shelf in ("news", "courses"):
        if by_shelf.get(shelf):
            start_here.append(by_shelf[shelf][0]["id"])

    manual = {
        "edition": edition_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "shelves": shelves,
        "start_here": start_here,
        "stats": {
            "items": sum(len(s["items"]) for s in shelves),
            "shelves": len(shelves),
            "sources": len(sources),
        },
    }
    validate_manual(manual)
    return manual


def render_markdown(manual):
    """Readable companion: TOC + per-item briefings."""
    lines = [
        f"# The Field Manual — Edition {manual['edition']}",
        "",
        "A weekly briefing for people building with AI agents: the papers, "
        "courses, launches, and job-market signals that actually matter.",
        "",
        "## Start here",
        "",
    ]
    lookup = {i["id"]: i for s in manual["shelves"] for i in s["items"]}
    for sid in manual["start_here"]:
        it = lookup[sid]
        lines.append(f"- **[{it['title']}]({it['url']})** ({it['source']}) — {it['id']}")
    lines += ["", "## Contents", ""]
    for shelf in manual["shelves"]:
        lines.append(f"- **{shelf['title']}** — {shelf['tagline']} ({len(shelf['items'])} items)")
        for it in shelf["items"]:
            lines.append(f"  - [{it['title']}]({it['url']})")
    lines.append("")
    for shelf in manual["shelves"]:
        lines += [f"## {shelf['title']}", "", f"*{shelf['tagline']}*", ""]
        for it in shelf["items"]:
            b = it["briefing"]
            pub = f" · {it['published']}" if it.get("published") else ""
            lines += [
                f"### {it['id']}: {it['title']}",
                "",
                f"*{it['source']}{pub}* · score {it['score']} · [link]({it['url']})",
                "",
                f"**{b['lede']}**",
                "",
                b["what_happened"],
                "",
                f"*Why it matters:* {b['why_it_matters']}",
                "",
                f"*Steal this:* {b['steal_this']}",
                "",
                "Takeaways: " + " / ".join(it["takeaways"]),
                "",
            ]
    lines += [
        "---",
        f"*Stats: {manual['stats']['items']} items · "
        f"{manual['stats']['sources']} sources · generated {manual['generated_at']}*",
        "",
    ]
    return "\n".join(lines)


def write_edition(manual, out_dir=None):
    out_dir = Path(out_dir) if out_dir else Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "manual.json"
    md_path = out_dir / "manual.md"
    json_path.write_text(json.dumps(manual, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    md_path.write_text(render_markdown(manual), encoding="utf-8")
    return json_path, md_path
