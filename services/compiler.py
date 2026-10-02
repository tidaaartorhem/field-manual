#!/usr/bin/env python3
"""Assemble a newsletter edition: lede, section narratives, item briefings.

Reads curated items, builds the ``data/newsletter.json`` shape (see
SCHEMA.md), validates it, and renders a readable ``data/newsletter.md``.

Edition shape::

    {
      "edition": "2026-10-02",
      "window_hours": 48,
      "generated_at": "...",
      "lede": "...",
      "sections": [
        {"id": "signal", "title": "The Signal", "kicker": "...",
         "narrative": "...", "closing_take": "...",
         "items": [ {id, title, url, source, published, date_verified,
                     score, briefing, takeaways, queries} ]},
        ...
      ],
      "stats": {"items": n, "sections": m, "sources": k}
    }

Pipeline order inside ``compile_edition`` matters: item briefings run
first (so the OpenAI probe happens on a real item), then section
narratives, then the edition lede.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

SECTION_ORDER = ["signal", "tech", "startups", "podcasts"]

SECTION_META = {
    "signal": {
        "title": "The Signal",
        "kicker": "Agentic AI, last 48 hours — what moved and why it matters.",
    },
    "tech": {
        "title": "The Wider Current",
        "kicker": "The broader tech world, through an AI builder's lens.",
    },
    "startups": {
        "title": "Startups",
        "kicker": "Launches, raises, pivots, and hot takes — where the energy went.",
    },
    "podcasts": {
        "title": "The Podcast Circuit",
        "kicker": "What the operators said out loud this week.",
    },
}

WORTH_ID = "worth"


def validate_newsletter(letter):
    """Raise ValueError if the edition doesn't match the SCHEMA.md shape."""
    for key in ("edition", "window_hours", "generated_at", "lede",
                "sections", "stats"):
        if key not in letter:
            raise ValueError(f"missing top-level key: {key}")
    if not isinstance(letter["sections"], list) or not letter["sections"]:
        raise ValueError("sections must be a non-empty list")
    seen_ids = set()
    for section in letter["sections"]:
        for key in ("id", "title", "kicker", "narrative", "closing_take",
                    "items"):
            if key not in section:
                raise ValueError(f"section missing key: {key}")
        for item in section["items"]:
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
    stats = letter["stats"]
    n = sum(len(s["items"]) for s in letter["sections"])
    if stats.get("items") != n or stats.get("sections") != len(letter["sections"]):
        raise ValueError("stats inconsistent with content")


def _build_item(item, shelf, item_id, writer):
    from .curator import source_name
    url = item.get("url", "")
    briefing, takeaways, _src = writer._briefing_with_source(
        {**item, "id": item_id}, shelf)
    return {
        "id": item_id,
        "title": (item.get("title") or "Untitled").strip(),
        "url": url,
        "source": source_name(url),
        "published": item.get("published"),
        "date_verified": bool(item.get("date_verified")),
        "shelf": shelf,
        "score": round(float(item.get("score", 0)), 2),
        "briefing": briefing,
        "takeaways": takeaways,
        "queries": list(item.get("queries", [])),
    }


def compile_edition(curated, edition_date=None, window_hours=48):
    """Assemble + validate the newsletter dict.

    ``curated`` is {section_id: [items]}. Sections with no items are
    skipped, except podcasts which renders an honest "quiet week" section.
    """
    from . import writer

    writer.reset_run_state()
    edition_date = edition_date or datetime.now(timezone.utc).date().isoformat()
    sections = []
    sources = set()
    all_items = []

    for shelf in SECTION_ORDER:
        items = sorted(curated.get(shelf, []),
                       key=lambda i: (-i.get("score", 0), i.get("title", "")))
        out_items = []
        for idx, item in enumerate(items, 1):
            item_id = f"{shelf}-{idx:03d}"
            out = _build_item(item, shelf, item_id, writer)
            sources.add(out["source"])
            out_items.append(out)
            all_items.append(out)
        if not out_items and shelf != "podcasts":
            continue
        meta = SECTION_META[shelf]
        if out_items:
            narr = writer.write_section_narrative(shelf, meta["title"], out_items)
        else:
            narr = {
                "narrative": ("Quiet on the podcast circuit this week — no new "
                              "episodes from the tracked shows landed inside "
                              "the 48-hour window. The back catalog is always "
                              "there; this week's signal came from elsewhere."),
                "closing_take": "No new episodes; the news carried this edition.",
            }
        sections.append({
            "id": shelf,
            "title": meta["title"],
            "kicker": meta["kicker"],
            "narrative": narr["narrative"],
            "closing_take": narr["closing_take"],
            "items": out_items,
        })

    # Worth Your Time: the 3 highest-scored items across the edition.
    worth = sorted(all_items, key=lambda i: (-i["score"], i["title"]))[:3]
    if worth:
        sections.append({
            "id": WORTH_ID,
            "title": "Worth Your Time",
            "kicker": "If you read three things, read these.",
            "narrative": ("Three picks, no filler. These scored highest across "
                          "every section — the densest signal in this edition."),
            "closing_take": "Start here if you're short on time.",
            "items": [
                {**it, "id": f"worth-{n:03d}"}
                for n, it in enumerate(worth, 1)
            ],
        })

    lede = writer.write_edition_lede(
        [(s["title"], s["closing_take"]) for s in sections])

    letter = {
        "edition": edition_date,
        "window_hours": window_hours,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lede": lede,
        "sections": sections,
        "stats": {
            "items": sum(len(s["items"]) for s in sections),
            "sections": len(sections),
            "sources": len(sources),
        },
    }
    validate_newsletter(letter)
    return letter


def render_markdown(letter):
    """Readable companion: lede + sections with narratives and briefings."""
    lines = [
        f"# The Field Manual — Edition {letter['edition']}",
        "",
        f"*The last {letter['window_hours']} hours, woven into one story.*",
        "",
        letter["lede"],
        "",
    ]
    for section in letter["sections"]:
        lines += [f"## {section['title']}", "", f"*{section['kicker']}*", "",
                  section["narrative"], "",
                  f"**So what?** {section['closing_take']}", ""]
        for it in section["items"]:
            b = it["briefing"]
            pub = f" · {it['published']}" if it.get("published") else ""
            lines += [
                f"### {it['title']}",
                "",
                f"*{it['source']}{pub}* · [link]({it['url']})",
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
        f"*{letter['stats']['items']} items · "
        f"{letter['stats']['sources']} sources · "
        f"generated {letter['generated_at']}*",
        "",
    ]
    return "\n".join(lines)


def write_edition(letter, out_dir=None):
    out_dir = Path(out_dir) if out_dir else Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "newsletter.json"
    md_path = out_dir / "newsletter.md"
    json_path.write_text(json.dumps(letter, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    md_path.write_text(render_markdown(letter), encoding="utf-8")
    return json_path, md_path
