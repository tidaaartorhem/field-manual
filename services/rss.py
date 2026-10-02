#!/usr/bin/env python3
"""RSS ingestion backbone for the Field Manual.

RSS is the PRIMARY ingestion source: feeds give reliable pub dates and
canonical links, which Firecrawl search cannot. Firecrawl remains for what
RSS can't do — full-article text extraction and startup-news discovery
(see scanner.py).

Each feed is mapped to a newsletter section (shelf). Items carry:
    url, title, description, published (ISO date or None), shelf,
    source_feed, queries (provenance, e.g. ["rss:techcrunch-ai"]),
    from_rss=True

Only entries inside the caller's window are returned (checked against the
feed's own pub dates — the honest path). Entries without parseable dates
are kept but flagged date_verified=False downstream.
"""
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None


# (feed name, url, shelf). Order matters: higher-signal feeds first.
FEEDS = [
    # --- agentic AI signal: papers first ---
    ("arxiv-cs-ai", "https://export.arxiv.org/rss/cs.AI", "signal"),
    ("arxiv-cs-cl", "https://export.arxiv.org/rss/cs.CL", "signal"),
    # --- broader tech ---
    ("techcrunch-ai", "https://techcrunch.com/category/artificial-intelligence/feed/", "tech"),
    ("the-verge", "https://www.theverge.com/rss/index.xml", "tech"),
    ("hn-frontpage", "https://hnrss.org/frontpage", "tech"),
    # --- startups: launches + funding (HN frontpage doubles as launch radar) ---
    ("hn-frontpage", "https://hnrss.org/frontpage", "startups"),
    # --- the podcast circuit: real episode feeds, real dates ---
    ("all-in", "https://feeds.libsyn.com/254861/rss", "podcasts"),
    ("acquired", "https://feeds.transistor.fm/acquired", "podcasts"),
    ("hard-fork", "https://feeds.simplecast.com/l2i9YnTd", "podcasts"),
    ("twist", "https://anchor.fm/s/7c624c84/podcast/rss", "podcasts"),
    ("iltb", "https://feeds.megaphone.fm/investlikethebest", "podcasts"),
]

# HN frontpage is general tech: only AI/agent-relevant stories count for
# the signal/startups shelves (checked against the shelf keyword profile).
HN_SHELF_KEYWORDS = {
    "signal": ("ai", "llm", "agent", "gpt", "model", "openai", "anthropic",
               "gemini", "Muse", "copilot", "robot"),
    "startups": ("startup", "yc", "funding", "raised", "seed", "series",
                 "launch", "launches", "show hn"),
}

# arXiv dumps hundreds of papers; only agent-relevant ones survive.
ARXIV_SIGNAL_KEYWORDS = ("agent", "agentic", "multi-agent", "tool use",
                         "tool-use", "llm", "language model", "reasoning",
                         "planning", "memory", "orchestration", "rag",
                         "retrieval", "evaluation", "benchmark", "copilot",
                         "autonomous")

MAX_PER_FEED = 40


def _entry_datetime(entry):
    """Best-effort UTC datetime from a feedparser entry. None if unparseable."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _clean(text):
    """Strip HTML tags/entities from feed summaries."""
    t = unescape(text or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _hn_relevant(title, desc, shelf):
    blob = f"{title} {desc}".lower()
    return any(k in blob for k in HN_SHELF_KEYWORDS.get(shelf, ()))


def _arxiv_relevant(title, desc):
    blob = f"{title} {desc}".lower()
    return any(k in blob for k in ARXIV_SIGNAL_KEYWORDS)


def fetch_feed(name, url, shelf, hours=48, now=None, verbose=True):
    """Fetch one feed; return (items, error|None). Only in-window entries."""
    if feedparser is None:
        return [], f"feedparser not installed"
    now = now or datetime.now(timezone.utc)
    cutoff = now.timestamp() - hours * 3600
    try:
        parsed = feedparser.parse(url, agent="field-manual/1.0")
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"[:200]
    if getattr(parsed, "bozo", 0) and not parsed.entries:
        return [], f"parse failed: {str(getattr(parsed, 'bozo_exception', ''))[:160]}"

    items, skipped_old = [], 0
    for entry in parsed.entries[:MAX_PER_FEED]:
        link = (entry.get("link") or "").strip()
        title = _clean(entry.get("title", ""))[:300]
        if not link.startswith("http") or not title:
            continue
        dt = _entry_datetime(entry)
        if dt is not None and dt.timestamp() < cutoff:
            skipped_old += 1
            continue
        desc = _clean(entry.get("summary", entry.get("description", "")))[:1200]
        # Feed-specific relevance gates.
        if name.startswith("arxiv-") and not _arxiv_relevant(title, desc):
            continue
        if name == "hn-frontpage" and shelf in HN_SHELF_KEYWORDS \
                and not _hn_relevant(title, desc, shelf):
            continue
        items.append({
            "url": link,
            "title": title,
            "description": desc,
            "published": dt.date().isoformat() if dt else None,
            "shelf": shelf,
            "source_feed": name,
            "queries": [f"rss:{name}"],
            "from_rss": True,
            "podcast": _podcast_name(name),
        })
    if verbose:
        print(f"[rss] ok  {name:14s} -> {shelf:8s}  ({len(items)} in window, "
              f"{skipped_old} older)")
    return items, None


def _podcast_name(feed_name):
    return {
        "all-in": "All In", "acquired": "Acquired", "hard-fork": "Hard Fork",
        "twist": "This Week in Startups", "iltb": "Invest Like the Best",
    }.get(feed_name)


def fetch_all(hours=48, verbose=True):
    """Fetch every feed. Returns (items, failures)."""
    items, failures = [], []
    for name, url, shelf in FEEDS:
        got, err = fetch_feed(name, url, shelf, hours=hours, verbose=verbose)
        if err:
            failures.append({"feed": name, "error": err})
            if verbose:
                print(f"[rss] FAILED {name:14s} -> {err}", file=sys.stderr)
        items.extend(got)
    return items, failures


if __name__ == "__main__":
    got, errs = fetch_all(hours=int(sys.argv[1]) if len(sys.argv) > 1 else 48)
    print(f"{len(got)} items, {len(errs)} feed failures")
