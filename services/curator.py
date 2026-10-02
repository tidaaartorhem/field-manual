#!/usr/bin/env python3
"""Curate raw scan results: dedupe, score, rank, and cut per shelf.

Pure functions (no I/O): ``normalize_url``, ``dedupe``, ``score_item``,
``curate``. The only impure helpers are date/source extraction, which are
also dependency-free.
"""
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Marketing / tracking params that create duplicate URLs of the same page.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "gclsrc", "igshid", "mc_cid", "mc_eid",
    "ref", "source", "__hsfp", "__hssc", "__hstc", "_hsenc", "hsctatracking",
    "srsltid", "vero_id", "vero_conv", "yclid", "msclkid", "dclid",
    "wbraid", "gbraid", "gad_source", "aff_id", "affid", "partner",
}

# Press-release mills and aggregator farms: real but low-signal.
PRESS_MILLS = {
    "prweb.com", "prnewswire.com", "einpresswire.com", "globenewswire.com",
    "businesswire.com", "24-7pressrelease.com", "newswire.com",
    "openpr.com", "pressrelease.com", "issuewire.com", "accessnewswire.com",
}

# Social/aggregator hosts: often relevant but usually second-hand.
SECOND_HAND = {
    "reddit.com", "www.reddit.com", "twitter.com", "x.com", "facebook.com",
    "linkedin.com", "www.linkedin.com", "medium.com", "substack.com",
    "news.ycombinator.com", "youtube.com", "www.youtube.com",
    "tiktok.com", "instagram.com",
}

# Hosts whose content is typically primary and high-signal per section.
PRIMARY_HOSTS = {
    "signal": {"anthropic.com", "openai.com", "nvidia.com", "googleblog.com",
               "microsoft.com", "aws.amazon.com", "langchain.com",
               "langchain.dev", "crewai.com", "docs.anthropic.com",
               "huggingface.co", "github.blog"},
    "tech": {"theverge.com", "arstechnica.com", "techcrunch.com",
             "wired.com", "theinformation.com", "bloomberg.com",
             "reuters.com", "nytimes.com"},
    "startups": {"techcrunch.com", "ycombinator.com", "wellfound.com",
                 "producthunt.com", "saastr.com"},
    "podcasts": {"allin.com", "acquired.fm", "investlikethebest.com",
                 "nytimes.com", "thisweekinstartups.com"},
}

TOPIC_KEYWORDS = {
    "signal": {
        "agent", "agents", "agentic", "llm", "large language model",
        "tool use", "tool-use", "planning", "reasoning", "memory",
        "orchestration", "autonomous", "framework", "sdk", "api",
        "copilot", "evaluation", "benchmark", "multi-agent", "rag",
    },
    "tech": {
        "ai", "artificial intelligence", "model", "models", "chip",
        "chips", "semiconductor", "datacenter", "cloud", "launch",
        "release", "announcement", "breakthrough", "open source",
    },
    "startups": {
        "startup", "startups", "funding", "raised", "raise", "series",
        "seed", "launch", "launches", "launched", "yc", "y combinator",
        "pivot", "acquired", "acquisition", "valuation", "founder",
    },
    "podcasts": {
        "episode", "podcast", "interview", "conversation", "all-in",
        "acquired", "transcript", "show notes",
    },
}

MONTHS = ("january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december")


def normalize_url(url):
    """Normalize a URL for dedupe: fold host case, drop tracking params,
    strip trailing slash, remove fragment, collapse arXiv version suffixes."""
    url = (url or "").strip()
    if not url:
        return ""
    p = urlparse(url)
    scheme = (p.scheme or "https").lower()
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    # arXiv version suffixes: /abs/2601.12560v2 -> /abs/2601.12560
    if host == "arxiv.org":
        path = re.sub(r"^(/abs/\d{4}\.\d+?)v\d+$", r"\1", path)
    kept = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
            if k.lower() not in TRACKING_PARAMS]
    query = urlencode(sorted(kept))
    return urlunparse((scheme, host, path, "", query, ""))


def dedupe(items):
    """Dedupe raw items by normalized URL.

    Keeps the first occurrence's title/description/shelf; merges the
    ``queries`` provenance lists across duplicates.
    """
    seen = {}
    for item in items:
        key = normalize_url(item.get("url", ""))
        if not key:
            continue
        if key in seen:
            existing = seen[key]
            for q in item.get("queries", []):
                if q not in existing["queries"]:
                    existing["queries"].append(q)
            if len(item.get("description", "")) > len(existing.get("description", "")):
                existing["description"] = item["description"]
            continue
        merged = dict(item)
        merged["queries"] = list(item.get("queries", []))
        merged["_norm"] = key
        seen[key] = merged
    return list(seen.values())


def extract_published(text, url=""):
    """Best-effort ISO date guess from text and URL. Returns 'YYYY-MM-DD' or None."""
    blob = f"{text or ''} {url or ''}"
    # explicit ISO-ish dates
    m = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", blob)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # arXiv ids: [2601.12560] or /abs/2605.14830 -> 2026-01 / 2026-05
    m = re.search(r"(?:\[|/abs/)(2[0-5])(\d{2})\.\d+", blob)
    if m:
        yy = int(m.group(1))
        return f"20{yy:02d}-{m.group(2)}-01"
    # "January 2026" style
    m = re.search(r"(?i)\b(" + "|".join(MONTHS) + r")\s+(20\d{2})\b", blob)
    if m:
        mi = MONTHS.index(m.group(1).lower()) + 1
        return f"{m.group(2)}-{mi:02d}-01"
    # "Oct 2, 2026" / "October 2, 2026" style (show notes, article bylines)
    m = re.search(r"(?i)\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(20\d{2})\b", blob)
    if m:
        mi = MONTHS.index(m.group(1).lower()) + 1
        return f"{m.group(3)}-{mi:02d}-{int(m.group(2)):02d}"
    # Abbreviated "Oct 2, 2026" style (podcast listings)
    abbrev = {mth[:3]: mth for mth in MONTHS}
    m = re.search(r"(?i)\b(" + "|".join(abbrev) + r")\.?\s+(\d{1,2}),?\s+(20\d{2})\b", blob)
    if m:
        mi = MONTHS.index(abbrev[m.group(1).lower()]) + 1
        return f"{m.group(3)}-{mi:02d}-{int(m.group(2)):02d}"
    return None


def item_date(item):
    """Best-effort published date for an item, checking scraped markdown too."""
    pub = (item.get("published") or "").strip()
    if re.match(r"^20\d{2}-\d{2}-\d{2}$", pub):
        return pub
    return (extract_published(f"{item.get('title')} {item.get('description')}",
                              item.get("url", ""))
            or extract_published(item.get("scraped_markdown", ""), ""))


def filter_recent(items, hours=48, now=None):
    """Keep only items inside the last ``hours`` hours.

    Items with a provably older published date are dropped. Items with no
    detectable date are kept — they arrived through a time-bounded search
    (tbs), so absence of a date is not evidence of staleness — but flagged
    ``date_verified=False`` for honesty downstream.
    """
    from datetime import datetime, timedelta, timezone
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    kept = []
    for item in items:
        item = dict(item)
        pub = item_date(item)
        item["published"] = pub
        if pub:
            try:
                dt = datetime(int(pub[:4]), int(pub[5:7]), int(pub[8:10]),
                              tzinfo=timezone.utc)
            except ValueError:
                dt = None
            if dt is not None and dt < cutoff.replace(hour=0, minute=0,
                                                      second=0, microsecond=0):
                continue  # provably older than the window
            item["date_verified"] = True
        else:
            item["date_verified"] = False
        kept.append(item)
    return kept


def source_name(url):
    """Human-readable publisher name from a URL."""
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    pretty = {
        "arxiv.org": "arXiv", "openreview.net": "OpenReview",
        "paperswithcode.com": "Papers with Code",
        "deeplearning.ai": "DeepLearning.AI", "learn.deeplearning.ai": "DeepLearning.AI",
        "fast.ai": "fast.ai", "coursera.org": "Coursera", "udacity.com": "Udacity",
        "edx.org": "edX", "anthropic.com": "Anthropic", "openai.com": "OpenAI",
        "nvidia.com": "NVIDIA", "microsoft.com": "Microsoft",
        "techcrunch.com": "TechCrunch", "theverge.com": "The Verge",
        "arstechnica.com": "Ars Technica", "venturebeat.com": "VentureBeat",
        "langchain.com": "LangChain", "github.blog": "GitHub Blog",
        "huggingface.co": "Hugging Face", "linkedin.com": "LinkedIn",
        "greenhouse.io": "Greenhouse", "lever.co": "Lever", "ashbyhq.com": "Ashby",
        "wellfound.com": "Wellfound", "reddit.com": "Reddit",
        "news.ycombinator.com": "Hacker News", "medium.com": "Medium",
        "substack.com": "Substack",
    }
    if host in pretty:
        return pretty[host]
    base = host.rsplit(".", 1)[0] if "." in host else host
    base = base.split(".")[-1]
    return base.replace("-", " ").title() or "Web"


def score_item(item, shelf):
    """Relevance score in [0, 1] for an item against a shelf profile.

    Keyword coverage + title hits + primary-source/recency boosts,
    minus penalties for press-release mills and second-hand aggregators.
    """
    keywords = TOPIC_KEYWORDS[shelf]
    title = (item.get("title") or "").lower()
    desc = (item.get("description") or "").lower()
    url = item.get("url") or ""
    text = f"{title} {desc} {url.lower()}"
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    hits = sum(1 for k in keywords if k in text)
    title_hits = sum(1 for k in keywords if k in title)
    score = 0.30 + 0.055 * hits + 0.04 * title_hits

    if host in PRIMARY_HOSTS.get(shelf, set()):
        score += 0.12
    if host in PRESS_MILLS:
        score -= 0.25
    if host in SECOND_HAND:
        score -= 0.10

    published = extract_published(f"{item.get('title')} {item.get('description')}", url)
    if published:
        year = int(published[:4])
        if year >= 2026:
            score += 0.08
        elif year == 2025:
            score += 0.04
        else:
            score -= 0.05

    if not item.get("title") or not item.get("description"):
        score -= 0.08  # thin metadata
    return round(max(0.0, min(1.0, score)), 3)


def curate(items, target_min=8, target_max=10):
    """Dedupe, score, rank per shelf; keep top ``target_max`` per shelf.

    Returns {shelf: [items...]} with ``score`` attached, shelves present in
    canonical order.
    """
    order = ["signal", "tech", "startups", "podcasts"]
    deduped = dedupe(items)
    by_shelf = {s: [] for s in order}
    for item in deduped:
        shelf = item.get("shelf")
        if shelf not in by_shelf:
            continue
        item = dict(item)
        item.pop("_norm", None)
        item["score"] = score_item(item, shelf)
        by_shelf[shelf].append(item)
    curated = {}
    for shelf in order:
        ranked = sorted(by_shelf[shelf], key=lambda i: (-i["score"], i.get("title", "")))
        keep = ranked[:target_max]
        if len(keep) < target_min:
            keep = ranked[:max(target_min, len(ranked))]  # take what's there
        curated[shelf] = keep
    return curated
