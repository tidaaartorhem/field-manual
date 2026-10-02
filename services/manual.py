#!/usr/bin/env python3
"""CLI entry point.

Primary (headless, schedule-friendly)::

    python -m services.manual edition --hours 48

scans (time-bounded to the last ``--hours`` hours), filters, curates,
writes, and compiles one newsletter edition into
``data/newsletter.json`` + ``data/newsletter.md``.

Legacy two-step commands (``scan`` / ``build``) remain for debugging.

Run from the repo root (``~/workspace/github-repos/field-manual``).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import scanner, compiler
from services.curator import curate, filter_recent


def cmd_scan(args):
    path = scanner.scan(limit_per_query=args.limit, verbose=not args.quiet)
    if path is None:
        print("scan aborted: all Firecrawl queries failed", file=sys.stderr)
        return 2
    return 0


def cmd_build(args):
    raw_path = ROOT / "data" / "raw.json"
    if not raw_path.exists():
        print(f"build failed: {raw_path} not found — run 'scan' first", file=sys.stderr)
        return 2
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    items = raw.get("items", [])
    if not items:
        print("build failed: raw.json contains no items", file=sys.stderr)
        return 2
    curated = curate(items, target_min=args.min_per_shelf, target_max=args.max_per_shelf)
    total = sum(len(v) for v in curated.values())
    if total == 0:
        print("build failed: nothing survived curation", file=sys.stderr)
        return 2
    manual = compiler.compile_edition(curated)
    json_path, md_path = compiler.write_edition(manual)
    for shelf, shelf_items in curated.items():
        print(f"[build] {shelf:8s}: {len(shelf_items)} items")
    from services.writer import briefing_source_stats
    src_stats = briefing_source_stats()
    print(f"[build] briefings: {src_stats.get('openai', 0)} via OpenAI API, "
          f"{src_stats.get('template', 0)} via templates")
    print(f"[build] wrote {total} items -> {json_path} and {md_path}")
    return 0


def cmd_edition(args):
    """One headless run: scan -> 48h filter -> curate -> enrich -> write ->
    compile -> charts -> email HTML."""
    from services import charts as charts_mod, chart_editor, emailer

    hours = args.hours
    print(f"[edition] scanning (RSS backbone + discovery, last {hours}h)...")
    path = scanner.scan(limit_per_query=args.limit, hours=hours,
                        verbose=not args.quiet)
    if path is None:
        print("edition aborted: all sources failed", file=sys.stderr)
        return 2
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("items", [])
    recent = filter_recent(items, hours=hours)
    dropped = len(items) - len(recent)
    print(f"[edition] {len(items)} scanned -> {len(recent)} inside {hours}h "
          f"({dropped} too old)")
    if not recent:
        print("edition aborted: nothing inside the window", file=sys.stderr)
        return 2
    curated = curate(recent, target_min=args.min_per_section,
                     target_max=args.max_per_section)
    total = sum(len(v) for v in curated.values())
    if total == 0:
        print("edition aborted: nothing survived curation", file=sys.stderr)
        return 2
    # Full-text enrichment for the top items (briefings from real articles).
    flat = [i for items in curated.values() for i in items]
    scanner.enrich_items(flat, max_items=args.enrich_max,
                         verbose=not args.quiet)
    letter = compiler.compile_edition(curated, window_hours=hours)
    json_path, md_path = compiler.write_edition(letter)
    for shelf, shelf_items in curated.items():
        print(f"[edition] {shelf:8s}: {len(shelf_items)} items")

    # Charts: honest aggregates -> editor pass -> data/charts.json + PNGs.
    edition_id = letter["edition"]
    chart_specs = charts_mod.build_charts(curated)
    chart_specs = chart_editor.edit_charts(chart_specs)
    charts_json, png_paths = charts_mod.write_charts(chart_specs, edition_id)
    print(f"[edition] charts: {len(chart_specs)} computed -> {charts_json} "
          f"+ {len(png_paths)} PNGs")

    # Email-safe edition.
    email_path = emailer.write_email(letter, chart_specs, edition_id)
    print(f"[edition] email HTML -> {email_path}")

    from services.writer import briefing_source_stats
    src_stats = briefing_source_stats()
    print(f"[edition] briefings: {src_stats.get('openai', 0)} via OpenAI API, "
          f"{src_stats.get('template', 0)} via templates")
    print(f"[edition] wrote {total} items -> {json_path} and {md_path}")
    return 0


def cmd_charts(args):
    """Rebuild charts for the published edition without rescanning.

    Reconstructs the curated shelves by matching data/raw.json items
    against the URLs in data/newsletter.json, then runs the charts step
    (hard rules -> editor pass -> charts.json + PNGs). No Firecrawl calls.
    """
    from services import charts as charts_mod, chart_editor

    letter_path = ROOT / "data" / "newsletter.json"
    raw_path = ROOT / "data" / "raw.json"
    if not letter_path.exists() or not raw_path.exists():
        print("charts failed: need data/newsletter.json and data/raw.json",
              file=sys.stderr)
        return 2
    letter = json.loads(letter_path.read_text(encoding="utf-8"))
    raw_items = json.loads(raw_path.read_text(encoding="utf-8")).get("items", [])
    urls = {it["url"] for s in letter.get("sections", [])
            for it in s.get("items", [])}
    curated, seen = {}, set()
    for it in raw_items:
        url = it.get("url")
        if url in urls and url not in seen:
            seen.add(url)
            curated.setdefault(it.get("shelf", "signal"), []).append(it)
    total = sum(len(v) for v in curated.values())
    print(f"[charts] {total} edition items matched across "
          f"{len(curated)} shelves")
    specs = charts_mod.build_charts(curated)
    print(f"[charts] {len(specs)} candidates after hard rules: "
          f"{[s['id'] for s in specs]}")
    if args.no_editor:
        chart_editor.set_editor_mode("off")
    specs = chart_editor.edit_charts(specs)
    edition_id = letter["edition"]
    charts_json, png_paths = charts_mod.write_charts(specs, edition_id)
    print(f"[charts] wrote {len(specs)} charts -> {charts_json} "
          f"+ {len(png_paths)} PNGs")
    # Re-render the email HTML so it references the new chart set.
    from services import emailer
    email_path = emailer.write_email(letter, specs, edition_id)
    print(f"[charts] email HTML -> {email_path}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="services.manual",
        description="field-manual pipeline: scan the web, curate, and "
                    "compile a 48-hour newsletter edition.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ed = sub.add_parser("edition", help="headless run: scan -> newsletter")
    p_ed.add_argument("--hours", type=int, default=48,
                      help="recency window in hours (default: 48)")
    p_ed.add_argument("--limit", type=int, default=5,
                      help="results per query (default: 5)")
    p_ed.add_argument("--min-per-section", type=int, default=3,
                      help="minimum items kept per section (default: 3)")
    p_ed.add_argument("--max-per-section", type=int, default=6,
                      help="maximum items kept per section (default: 6)")
    p_ed.add_argument("--enrich-max", type=int, default=14,
                      help="top items to scrape for full text (default: 14)")
    p_ed.add_argument("--quiet", action="store_true",
                      help="only print summary lines")
    p_ed.set_defaults(func=cmd_edition)

    p_scan = sub.add_parser("scan", help="run scans -> data/raw.json (debug)")
    p_scan.add_argument("--limit", type=int, default=5,
                        help="results per query (default: 5)")
    p_scan.add_argument("--quiet", action="store_true",
                        help="only print the summary line")
    p_scan.set_defaults(func=cmd_scan)

    p_build = sub.add_parser("build", help="raw.json -> newsletter (debug)")
    p_build.add_argument("--min-per-shelf", type=int, default=3,
                         help="minimum items kept per section (default: 3)")
    p_build.add_argument("--max-per-shelf", type=int, default=6,
                         help="maximum items kept per section (default: 6)")
    p_build.set_defaults(func=cmd_build)

    p_ch = sub.add_parser("charts",
                          help="rebuild charts for the published edition (no rescan)")
    p_ch.add_argument("--no-editor", action="store_true",
                      help="skip the OpenAI editor pass (hard rules only)")
    p_ch.set_defaults(func=cmd_charts)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
