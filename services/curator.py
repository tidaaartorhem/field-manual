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

# Hosts whose content is typically primary and high-signal per shelf.
PRIMARY_HOSTS = {
    "papers": {"arxiv.org", "openreview.net", "paperswithcode.com",
               "proceedings.mlr.press", "aclanthology.org", "distill.pub"},
    "courses": {"coursera.org", "deeplearning.ai", "udacity.com", "edx.org",
                "fast.ai", "stanford.edu", "mit.edu", "huggingface.co",
                "learn.deeplearning.ai", "maven.com", "udemy.com"},
    "news": {"anthropic.com", "openai.com", "nvidia.com", "googleblog.com",
             "microsoft.com", "aws.amazon.com", "techcrunch.com",
             "theverge.com", "arstechnica.com", "venturebeat.com",
             "langchain.com", "langchain.dev", "crewai.com",
             "docs.anthropic.com", "github.blog"},
    "career": {"linkedin.com", "www.linkedin.com", "indeed.com",
               "greenhouse.io", "lever.co", "ashbyhq.com", "workday.com",
               "wellfound.com", "ycombinator.com", "levels.fyi"},
}

TOPIC_KEYWORDS = {
    "papers": {
        "agent", "agents", "agentic", "llm", "large language model",
        "evaluation", "benchmark", "multi-agent", "rag",
        "retrieval augmented", "retrieval-augmented", "tool use",
        "tool-use", "planning", "reasoning", "memory", "orchestration",
        "autonomous", "arxiv", "survey", "framework", "prompt",
    },
    "courses": {
        "course", "certification", "certified", "certificate", "bootcamp",
        "curriculum", "learn", "training", "agentic", "agent", "llm",
        "engineering", "academy", "nanodegree", "specialization",
        "masterclass", "program",
    },
    "news": {
        "launch", "launches", "announces", "announcement", "release",
        "released", "agent", "agents", "agentic", "enterprise", "adoption",
        "framework", "sdk", "api", "coding", "copilot", "startup",
        "funding", "partnership", "ga ", "generally available",
    },
    "career": {
        "forward deployed", "forward-deployed", "solutions engineer",
        "solution engineer", "ai engineer", "llm", "hiring", "job",
        "jobs", "career", "role", "salary", "interview", "resume",
        "integration", "customer", "deployment", "deploy",
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
    return None


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
    order = ["papers", "courses", "news", "career"]
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
