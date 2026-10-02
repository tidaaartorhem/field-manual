#!/usr/bin/env python3
"""Scan the web via the Firecrawl search CLI for field-manual shelves.

Runs curated query sets per shelf through
``~/workspace/skills/firecrawl/bin/search.py`` and persists the raw,
unfiltered results (with per-item query provenance) to ``data/raw.json``.

Failure policy: a single failed query is logged and skipped. If ALL
queries fail (auth rejected, API down), the scan aborts without writing
placeholder data — invented items/URLs are never an option.
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SEARCH_CLI = Path.home() / "workspace" / "skills" / "firecrawl" / "bin" / "search.py"

QUERY_SETS = {
    "papers": [
        "agentic AI arxiv 2026",
        "LLM agent evaluation benchmark paper 2026",
        "multi-agent LLM systems research 2026",
        "retrieval augmented generation research arxiv 2026",
    ],
    "courses": [
        "agentic AI certification course 2026",
        "AI agent engineering course 2026",
        "LLM application certification program",
    ],
    "news": [
        "AI agent framework launch 2026",
        "enterprise AI agents adoption 2026",
        "AI coding agent announcement 2026",
    ],
    "career": [
        "forward deployed engineer AI hiring",
        "solutions engineer LLM integration role",
        "AI engineer job market 2026",
    ],
}


def run_search(query, limit=5, timeout=120):
    """Run one Firecrawl search. Returns {'ok': bool, ...}."""
    try:
        proc = subprocess.run(
            [sys.executable, str(SEARCH_CLI), query, str(limit)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except OSError as exc:
        return {"ok": False, "error": f"spawn failed: {exc}"}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr.strip() or f"exit {proc.returncode}")[:300]}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"bad JSON from CLI: {exc}"}
    if not payload.get("success"):
        return {"ok": False, "error": str(payload.get("error") or "success:false")[:300]}
    results = payload.get("data", {}).get("web", []) or []
    return {"ok": True, "results": results}


def scan(limit_per_query=5, out_path=None, verbose=True):
    """Run every query set; write raw.json. Returns path, or None on total failure."""
    out_path = Path(out_path) if out_path else (
        Path(__file__).resolve().parent.parent / "data" / "raw.json"
    )
    items, failures = [], []
    total_calls = sum(len(qs) for qs in QUERY_SETS.values())

    for shelf, queries in QUERY_SETS.items():
        for query in queries:
            res = run_search(query, limit_per_query)
            if not res["ok"]:
                failures.append({"shelf": shelf, "query": query, "error": res["error"]})
                if verbose:
                    print(f"[scan] FAILED  {shelf:8s} :: {query}\n         -> {res['error']}",
                          file=sys.stderr)
                continue
            got = 0
            for r in res["results"]:
                url = (r.get("url") or "").strip()
                if not url or not url.startswith("http"):
                    continue
                items.append({
                    "url": url,
                    "title": (r.get("title") or "").strip(),
                    "description": (r.get("description") or "").strip(),
                    "shelf": shelf,
                    "queries": [query],
                    "position": r.get("position"),
                })
                got += 1
            if verbose:
                print(f"[scan] ok      {shelf:8s} :: {query}  ({got} items)")

    if total_calls and len(failures) == total_calls:
        print("[scan] ALL Firecrawl scans failed (auth rejected or API down). "
              "Not writing data; not inventing items.", file=sys.stderr)
        return None

    payload = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "queries": {s: list(qs) for s, qs in QUERY_SETS.items()},
        "items": items,
        "failures": failures,
        "stats": {
            "queries_run": total_calls - len(failures),
            "queries_failed": len(failures),
            "items": len(items),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    print(f"[scan] wrote {len(items)} raw items to {out_path} "
          f"({len(failures)} query failures)")
    return out_path


if __name__ == "__main__":
    sys.exit(0 if scan() else 1)
