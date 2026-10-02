#!/usr/bin/env python3
"""Scan the web for the newsletter: 48-hour news + the podcast circuit.

Two scan modes, both via Firecrawl:

1. **News scans** — curated query sets per section (signal / tech / startups)
   run through the Firecrawl search API with ``tbs`` (time-based search)
   bounding results to the last 48 hours (``qdr:d2``). Recency is enforced
   at the source, not just filtered afterwards.

2. **Podcast circuit** — for each show (All In, Acquired, Invest Like the
   Best, Hard Fork, This Week in Startups), search for the latest episode,
   then scrape the episode page for real show notes. Episode titles and
   descriptions come only from scraped pages — never invented. Episodes
   older than the window are dropped after scraping.

Failure policy: a failed query/episode is logged and skipped. If ALL
queries fail, the scan aborts without writing placeholder data.
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SEARCH_CLI = Path.home() / "workspace" / "skills" / "firecrawl" / "bin" / "search.py"
SCRAPE_CLI = Path.home() / "workspace" / "skills" / "firecrawl" / "bin" / "scrape.py"

# tbs values are Google-style time bounds understood by Firecrawl search.
TBS_48H = "qdr:d2"

QUERY_SETS = {
    "signal": [  # agentic AI trends
        "agentic AI news this week",
        "AI agents launch announcement",
        "LLM agent framework update",
    ],
    "tech": [  # broader technology trends
        "tech news AI this week",
        "artificial intelligence industry news",
        "AI model release announcement",
    ],
    "startups": [  # what startups are saying and doing
        "AI startup funding round",
        "startup launches AI agent product",
        "YC AI startup launch",
    ],
}

PODCASTS = [
    {"name": "All In", "site": "allin.com",
     "query": "All In podcast latest episode"},
    {"name": "Acquired", "site": "acquired.fm",
     "query": "Acquired podcast latest episode"},
    {"name": "Invest Like the Best", "site": "investlikethebest.com",
     "query": "Invest Like the Best podcast latest episode"},
    {"name": "Hard Fork", "site": "nytimes.com",
     "query": "Hard Fork podcast latest episode"},
    {"name": "This Week in Startups", "site": "thisweekinstartups.com",
     "query": "This Week in Startups latest episode"},
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


def scan_news(limit_per_query=5, verbose=True):
    """Run the news query sets. Returns (items, failures)."""
    items, failures = [], []
    for section, queries in QUERY_SETS.items():
        for query in queries:
            res = run_search(query, limit_per_query, tbs=TBS_48H)
            if not res["ok"]:
                failures.append({"section": section, "query": query, "error": res["error"]})
                if verbose:
                    print(f"[scan] FAILED  {section:8s} :: {query}\n         -> {res['error']}",
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
                    "shelf": section,
                    "queries": [query],
                    "position": r.get("position"),
                })
                got += 1
            if verbose:
                print(f"[scan] ok      {section:8s} :: {query}  ({got} items)")
    return items, failures


def scan_podcasts(verbose=True):
    """Find the latest episode per show and scrape its show notes.

    Returns (items, failures). Each item carries the real episode title,
    show-note excerpt, and the scraped markdown for date extraction.
    """
    items, failures = [], []
    for pod in PODCASTS:
        name, site = pod["name"], pod["site"]
        res = run_search(f"site:{site} {pod['query']}", 5, tbs="qdr:w")
        if not res["ok"]:
            res = run_search(pod["query"], 5, tbs="qdr:w")
        if not res["ok"]:
            failures.append({"section": "podcasts", "query": pod["query"],
                             "error": res["error"]})
            if verbose:
                print(f"[scan] FAILED  podcasts :: {name} -> {res['error']}",
                      file=sys.stderr)
            continue
        # Prefer results on the show's own domain; take the first two.
        ranked = sorted(
            res["results"],
            key=lambda r: (site not in (r.get("url") or ""), r.get("position") or 99),
        )[:2]
        got = 0
        for r in ranked:
            url = (r.get("url") or "").strip()
            if not url.startswith("http"):
                continue
            time.sleep(1)  # be polite to show sites
            sc = run_scrape(url)
            if not sc["ok"]:
                if verbose:
                    print(f"[scan] scrape FAILED podcasts :: {name} {url} -> {sc['error']}",
                          file=sys.stderr)
                continue
            md = sc["markdown"]
            # Show-note excerpt: first substantive paragraphs.
            paras = [p.strip() for p in md.split("\n\n") if len(p.strip()) > 60]
            notes = " ".join(paras[:3])[:1200]
            title = sc["page_title"].strip() or (r.get("title") or "").strip()
            items.append({
                "url": url,
                "title": title,
                "description": notes,
                "shelf": "podcasts",
                "queries": [pod["query"]],
                "podcast": name,
                "scraped_markdown": md[:4000],
            })
            got += 1
        if verbose:
            print(f"[scan] ok      podcasts :: {name}  ({got} episodes)")
        if got == 0:
            failures.append({"section": "podcasts", "query": pod["query"],
                             "error": "no scrapable episode pages"})
    return items, failures


def scan(limit_per_query=5, out_path=None, verbose=True):
    """Full scan: news + podcast circuit. Writes data/raw.json."""
    out_path = Path(out_path) if out_path else (
        Path(__file__).resolve().parent.parent / "data" / "raw.json"
    )
    news_items, news_fail = scan_news(limit_per_query, verbose)
    pod_items, pod_fail = scan_podcasts(verbose)
    items = news_items + pod_items
    failures = news_fail + pod_fail

    if not items:
        print("[scan] ALL scans failed. Not writing data; not inventing items.",
              file=sys.stderr)
        return None

    payload = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "window": "48h",
        "queries": {s: list(qs) for s, qs in QUERY_SETS.items()},
        "podcasts": [p["name"] for p in PODCASTS],
        "items": items,
        "failures": failures,
        "stats": {
            "queries_run": sum(len(qs) for qs in QUERY_SETS.values()) + len(PODCASTS) - len(failures),
            "queries_failed": len(failures),
            "items": len(items),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"[scan] wrote {len(items)} raw items to {out_path} "
          f"({len(failures)} failures)")
    return out_path


if __name__ == "__main__":
    sys.exit(0 if scan() else 1)
