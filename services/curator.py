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

# Source tiers: reliability weighting for scoring and charts.
# Tier 1 — primary sources: official announcements, papers, the shows themselves.
# Tier 2 — reputable press: real newsrooms with editors.
# Tier 3 — everything else: blogs, opinion, aggregators, wire mills.
TIER_1_HOSTS = {
    "arxiv.org", "openreview.net", "paperswithcode.com",
    "anthropic.com", "openai.com", "googleblog.com", "deepmind.google",
    "microsoft.com", "nvidia.com", "aws.amazon.com",
    "huggingface.co", "github.blog", "langchain.com", "langchain.dev",
    "crewai.com", "docs.anthropic.com", "ycombinator.com",
    "allin.com", "acquired.fm", "investlikethebest.com", "nytimes.com",
    "thisweekinstartups.com",
}
TIER_2_HOSTS = {
    "techcrunch.com", "theverge.com", "arstechnica.com", "wired.com",
    "theinformation.com", "bloomberg.com", "reuters.com", "nytimes.com",
    "venturebeat.com", "news.ycombinator.com", "producthunt.com",
    "wellfound.com", "saastr.com", "theguardian.com", "ft.com",
    "wsj.com", "forbes.com", "fastcompany.com",
}
TIER_MULTIPLIER = {1: 1.15, 2: 1.0, 3: 0.8}


def source_tier(url):
    """Reliability tier (1/2/3) for a URL's host."""
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in TIER_1_HOSTS:
        return 1
    if host in TIER_2_HOSTS:
        return 2
    return 3

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
    """Dedupe raw items by normalized URL, then by title similarity.

    Pass 1: exact normalized-URL dedupe (merges ``queries`` provenance).
    Pass 2: near-duplicate titles (SequenceMatcher ratio >= 0.88 on
    normalized titles) are merged as the same story told by two outlets —
    keeps the higher-scored item, merges provenance and descriptions.
    """
    from difflib import SequenceMatcher

    seen = {}
    for item in items:
        key = normalize_url(item.get("url", ""))
        if not key:
            continue
        if key in seen:
            _merge_into(seen[key], item)
            continue
        merged = dict(item)
        merged["queries"] = list(item.get("queries", []))
        merged["_norm"] = key
        seen[key] = merged

    deduped = list(seen.values())
    # Pass 2: title similarity.
    kept = []
    for item in deduped:
        title = _title_key(item.get("title", ""))
        dup_of = None
        for other in kept:
            if SequenceMatcher(None, title,
                                _title_key(other.get("title", ""))).ratio() >= 0.88:
                dup_of = other
                break
        if dup_of is not None:
            _merge_into(dup_of, item)
        else:
            kept.append(item)
    return kept


def _title_key(title):
    """Normalize a title for similarity comparison: lowercase, strip
    punctuation, drop trailing source suffixes ("| TechCrunch")."""
    t = (title or "").lower()
    t = re.sub(r"\s*[|\-–—:]\s*[a-z0-9 .&']+$", "", t).strip()
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _merge_into(existing, item):
    for q in item.get("queries", []):
        if q not in existing["queries"]:
            existing["queries"].append(q)
    if len(item.get("description", "")) > len(existing.get("description", "")):
        existing["description"] = item["description"]
    # Prefer the item with a verified RSS pub date.
    if item.get("from_rss") and item.get("published") and not existing.get("published"):
        existing["published"] = item["published"]
        existing["from_rss"] = True


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
        "substack.com": "Substack", "ycombinator.com": "Y Combinator",
        "nytimes.com": "New York Times", "youtube.com": "YouTube",
        "youtu.be": "YouTube", "fundraiseinsider.com": "Fundraise Insider",
        "libsyn.com": "Libsyn", "allin.com": "All In",
        "investlikethebest.com": "Invest Like the Best",
    }
    if host in pretty:
        return pretty[host]
    base = host.rsplit(".", 1)[0] if "." in host else host
    base = base.split(".")[-1]
    return base.replace("-", " ").title() or "Web"


def score_item(item, shelf):
    """Relevance score in [0, 1] for an item against a shelf profile.

    Keyword coverage + title hits + primary-source/recency boosts,
    multiplied by the source reliability tier (1: 1.15x, 2: 1.0x, 3: 0.8x).
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

    published = item.get("published") or extract_published(
        f"{item.get('title')} {item.get('description')}", url)
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

    # Reliability weighting: primary sources up, wire mills/blogs down.
    score *= TIER_MULTIPLIER[source_tier(url)]
    return round(max(0.0, min(1.0, score)), 3)


FUNDING_AMOUNT_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million|[bm])\b", re.I)
ROUND_RE = re.compile(
    r"\b(pre-seed|preseed|seed|series [a-f]|bridge|growth)\b", re.I)
COMPANY_RE = re.compile(
    r"^(.{2,60}?)\s+(raises|raised|secures|secured|lands|landed|closes|closed|"
    r"announces|announced|banks|nabs|scores)\b", re.I)


def extract_funding(item):
    """Best-effort funding-raise extraction from title + description.

    Returns {"company", "amount_usd", "round", "source_url"} or None.
    Only returns when BOTH a company and a dollar amount are found —
    charts must never show invented figures.
    """
    text = f"{item.get('title', '')} {item.get('description', '')}"
    m_amt = FUNDING_AMOUNT_RE.search(text)
    if not m_amt:
        return None
    raw, unit = m_amt.group(1).replace(",", ""), m_amt.group(2).lower()
    try:
        value = float(raw)
    except ValueError:
        return None
    mult = 1_000_000_000 if unit.startswith("b") else 1_000_000
    amount = value * mult
    if amount <= 0 or amount > 100_000_000_000:
        return None  # sanity: no $0 or $1T "raises"
    m_co = COMPANY_RE.search((item.get("title", "") or "").strip())
    if not m_co:
        return None
    company = re.sub(r"\s+", " ", m_co.group(1)).strip(" ,.:;-'\"")
    if len(company) < 2:
        return None
    m_round = ROUND_RE.search(text)
    rnd = m_round.group(1).lower().replace("preseed", "pre-seed") if m_round else None
    if rnd == "series a":
        rnd = "Series A"
    elif rnd:
        rnd = rnd.title() if rnd != "pre-seed" else "Pre-seed"
    return {"company": company, "amount_usd": amount, "round": rnd,
            "source_url": item.get("url", "")}


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
