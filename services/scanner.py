#!/usr/bin/env python3
"""Scan the web for the newsletter: RSS backbone + Firecrawl enrichment.

Ingestion order (quality-first):

1. **RSS backbone** (primary) — Hacker News, TechCrunch AI, The Verge,
   arXiv cs.AI + cs.CL, and the real podcast RSS feeds (All In, Acquired,
   Invest Like the Best, Hard Fork, This Week in Startups). RSS gives
   reliable pub dates and canonical links.
2. **Firecrawl startup discovery** (secondary) — funding rounds and
   launches RSS misses, via time-bounded search (``tbs=qdr:d2``).
3. **Firecrawl full-text extraction** — after curation, the top items are
   scraped for full article text so briefings are written from the real
   article, not the snippet.

Failure policy: a failed feed/query is logged and skipped. If ALL sources
fail, the scan aborts without writing placeholder data.
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import rss as rss_module

SEARCH_CLI = Path.home() / "workspace" / "skills" / "firecrawl" / "bin" / "search.py"
SCRAPE_CLI = Path.home() / "workspace" / "skills" / "firecrawl" / "bin" / "scrape.py"

# tbs values are Google-style time bounds understood by Firecrawl search.
TBS_48H = "qdr:d2"

# Firecrawl discovery is for startup news RSS undercovers.
DISCOVERY_QUERIES = [
    "AI startup funding round announced",
    "startup raises seed Series A AI",
    "YC startup launches AI product",
]


def _search_api():
    sys.path.insert(0, str(SEARCH_CLI.parent))
    from _client import request  # noqa: E402
    return request


def run_search(query, limit=5, tbs=TBS_48H):
    """Firecrawl search with a time bound. Returns {'ok': bool, ...}."""
    try:
        payload = {"query": query, "limit": limit}
        if tbs:
            payload["tbs"] = tbs
        result = _search_api()("POST", "/search", payload)
    except SystemExit as exc:
        return {"ok": False, "error": str(exc)[:300]}
    except Exception as exc:  # network / authd failure
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    if not result.get("success"):
        return {"ok": False, "error": str(result.get("error") or "success:false")[:300]}
    results = result.get("data", {}).get("web", []) or []
    return {"ok": True, "results": results}


def run_scrape(url, timeout=120):
    """Scrape one URL to markdown via the Firecrawl scrape CLI."""
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRAPE_CLI), url, "markdown"],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "error": str(exc)[:200]}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr.strip() or f"exit {proc.returncode}")[:200]}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"bad JSON: {exc}"}
    if not payload.get("success"):
        return {"ok": False, "error": str(payload.get("error") or "success:false")[:200]}
    md = (payload.get("data") or {}).get("markdown") or ""
    title = (payload.get("data") or {}).get("metadata", {}).get("title") or ""
    return {"ok": True, "markdown": md, "page_title": title}



def scan_rss(hours=48, verbose=True):
    """Primary ingestion: the RSS backbone. Returns (items, failures)."""
    return rss_module.fetch_all(hours=hours, verbose=verbose)


def scan_startup_discovery(limit_per_query=5, verbose=True):
    """Firecrawl discovery for startup news RSS undercovers.

    Returns (items, failures). Time-bounded at the source (tbs=qdr:d2).
    """
    items, failures = [], []
    for query in DISCOVERY_QUERIES:
        res = run_search(query, limit_per_query, tbs=TBS_48H)
        if not res["ok"]:
            failures.append({"section": "startups", "query": query,
                             "error": res["error"]})
            if verbose:
                print(f"[scan] FAILED  startups :: {query}\n         -> {res['error']}",
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
                "shelf": "startups",
                "queries": [query],
                "position": r.get("position"),
            })
            got += 1
        if verbose:
            print(f"[scan] ok      startups :: {query}  ({got} items)")
    return items, failures


def enrich_items(items, max_items=14, verbose=True):
    """Scrape full article text for the top-scored items.

    Attaches ``full_text`` (markdown, truncated) so briefings are written
    from the real article, not the snippet. Items are chosen by score;
    failures are silent (the snippet stands in).
    """
    ranked = sorted(items, key=lambda i: -i.get("score", 0))[:max_items]
    enriched = 0
    for item in ranked:
        url = item.get("url", "")
        if not url or item.get("podcast"):
            continue  # episodes already carry show notes
        time.sleep(1)  # be polite
        sc = run_scrape(url)
        if sc["ok"] and len(sc["markdown"]) > 400:
            item["full_text"] = sc["markdown"][:6000]
            enriched += 1
        elif verbose:
            print(f"[enrich] skip {url[:70]} -> {sc.get('error', '')[:80]}",
                  file=sys.stderr)
    if verbose:
        print(f"[enrich] {enriched}/{len(ranked)} items enriched with full text")
    return items


def scan(limit_per_query=5, hours=48, out_path=None, verbose=True):
    """Full scan: RSS backbone + Firecrawl startup discovery. Writes data/raw.json."""
    out_path = Path(out_path) if out_path else (
        Path(__file__).resolve().parent.parent / "data" / "raw.json"
    )
    rss_items, rss_fail = scan_rss(hours=hours, verbose=verbose)
    disc_items, disc_fail = scan_startup_discovery(limit_per_query, verbose)
    items = rss_items + disc_items
    failures = ([{"source": "rss", **f} for f in rss_fail]
                + [{"source": "firecrawl", **f} for f in disc_fail])

    if not items:
        print("[scan] ALL sources failed. Not writing data; not inventing items.",
              file=sys.stderr)
        return None

    payload = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "window": f"{hours}h",
        "feeds": [{"name": n, "shelf": s} for n, _, s in rss_module.FEEDS],
        "discovery_queries": DISCOVERY_QUERIES,
        "items": items,
        "failures": failures,
        "stats": {
            "rss_items": len(rss_items),
            "discovery_items": len(disc_items),
            "failures": len(failures),
            "items": len(items),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"[scan] wrote {len(items)} raw items to {out_path} "
          f"({len(rss_items)} rss, {len(disc_items)} discovery, "
          f"{len(failures)} failures)")
    return out_path


if __name__ == "__main__":
    sys.exit(0 if scan() else 1)
