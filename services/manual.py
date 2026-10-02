#!/usr/bin/env python3
"""CLI entry point: ``python -m services.manual scan`` or ``... build``.

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
from services.curator import curate


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


def build_parser():
    parser = argparse.ArgumentParser(
        prog="services.manual",
        description="field-manual pipeline: scan the web with Firecrawl, "
                    "then curate, write, and compile an edition.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="run Firecrawl searches -> data/raw.json")
    p_scan.add_argument("--limit", type=int, default=5,
                        help="results per query (default: 5)")
    p_scan.add_argument("--quiet", action="store_true",
                        help="only print the summary line")
    p_scan.set_defaults(func=cmd_scan)

    p_build = sub.add_parser("build", help="raw.json -> curate -> write -> compile")
    p_build.add_argument("--min-per-shelf", type=int, default=8,
                         help="minimum items kept per shelf (default: 8)")
    p_build.add_argument("--max-per-shelf", type=int, default=10,
                         help="maximum items kept per shelf (default: 10)")
    p_build.set_defaults(func=cmd_build)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
