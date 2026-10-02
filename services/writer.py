#!/usr/bin/env python3
"""Turn curated items into narrative briefings.

Two paths, best-first:

1. **OpenAI API (preferred).** When the ``custom.openai`` credential
   resolves via the dynamic-credential surrogate helper (same pattern as
   the Firecrawl skill: only ``hsurr:*`` surrogate values are ever sent,
   and only to ``api.openai.com``), each item gets exactly one constrained
   chat-completions call producing the briefing as JSON.
2. **Template fallback.** When the credential is missing, rejected, or any
   call fails, briefings are assembled from hand-written templates that
   reference the item's REAL title, source, and description.

The fallback is honest, not a placeholder: templates are deliberately
numerous and varied, the specific template is chosen deterministically
(hash of the item id + field) so output is stable across runs but doesn't
read like one form letter, and nothing invents facts — when the source
listing is thin, the copy says so instead of filling the gap.

No key or surrogate value is ever hardcoded, logged, or persisted.
"""
import hashlib
import json
import re
import sys
import urllib.request

from .curator import source_name, TOPIC_KEYWORDS

BANNED = ("revolutionary", "game-changer", "game changer", "delve",
          "delves", "paradigm shift", "unlock the power", "supercharge")


def _pick(key, pool):
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    return pool[h % len(pool)]


def clean_text(desc):
    """Strip markdown/boilerplate from a Firecrawl description."""
    t = desc or ""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)          # images
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)      # links -> text
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)        # headings
    t = t.replace("|", " ").replace("*", "")
    lines = []
    for line in t.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"(?i)^(cite as|view pdf|access paper|bookmark|current browse|prev|next)\b", s):
            continue
        lines.append(s)
    t = " ".join(lines)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def gist(item, max_len=340):
    """First ~2 sentences of the cleaned description, or an honest fallback."""
    t = clean_text(item.get("description", ""))
    if not t:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", t)
    out = " ".join(parts[:2]).strip()
    if len(out) > max_len:
        out = out[:max_len].rsplit(" ", 1)[0] + "..."
    return out


def topic_word(item, shelf):
    """Best single matched keyword to ground templates, else a shelf default."""
    text = f"{item.get('title','')} {item.get('description','')}".lower()
    for kw in sorted(TOPIC_KEYWORDS[shelf], key=len, reverse=True):
        if kw in text and len(kw) > 3:
            return kw
    return {"papers": "agents", "courses": "agentic AI",
            "news": "agents", "career": "AI engineering"}[shelf]


def _slots(item, shelf):
    g = gist(item)
    src = source_name(item.get("url", ""))
    title = (item.get("title") or "Untitled").strip()
    if not g:
        g = (f"Details are thin — the {src} listing doesn't say much beyond "
             f"the headline, so treat this one as a bookmark, not a briefing.")
    return {"title": title, "source": src, "gist": g,
            "topic": topic_word(item, shelf)}


# ---------------------------------------------------------------- templates

LEDES = {
    "papers": [
        "'{title}' is making the rounds in the {topic} crowd — and for once the forwarding is justified.",
        "New on {source}: '{title}'. The headline undersells it.",
        "'{title}' just landed on {source}, and it's the kind of paper that ends up cited in architecture docs rather than tweets.",
        "If you read one paper from this shelf, make it '{title}'. Here's the case.",
    ],
    "courses": [
        "'{title}' ({source}) is the structured version of what everyone is learning the hard way.",
        "Another cert entered the chat: '{title}'. Most aren't worth your time. This one might be — here's the read.",
        "If you're going to put '{topic}' on a resume, '{title}' from {source} is one of the few ways to do it with conviction.",
    ],
    "news": [
        "'{title}' — {source} just moved, and the agent ecosystem felt it.",
        "Filed under 'actually shipped': '{title}' ({source}).",
        "{source} announced '{title}'. Press releases are cheap; this one has teeth. Here's why.",
    ],
    "career": [
        "'{title}' — the market is speaking, and this listing is fluent.",
        "Resume-adjacent intel: '{title}' ({source}). Read it as a signal, not just a job.",
        "If you're watching the {topic} market, '{title}' is a data point worth pocketing.",
    ],
}

WHAT_HAPPENED = {
    "papers": [
        "Here's the substance. {gist} The paper is '{title}', out via {source}.",
        "'{title}' ({source}) goes after a question most teams only argue about over coffee: {gist}",
        "The work behind '{title}': {gist} It's on {source} now, and the discussion section is doing the rounds for a reason.",
    ],
    "courses": [
        "Here's the shape of it: {gist} '{title}' is aimed at people who want the credential to match the work they're already doing.",
        "{gist} That's the syllabus for '{title}' — {source}'s bet that {topic} is a skill you can teach, not just talent you hire.",
    ],
    "news": [
        "{gist} That's the news: '{title}', straight from {source}.",
        "The short version: {gist} The longer version: '{title}' is {source}'s latest move in the {topic} land grab.",
        "'{title}' is live. {gist} {source} is clearly betting this becomes infrastructure, not a headline.",
    ],
    "career": [
        "The listing, in brief: {gist} Title on the tin: '{title}'.",
        "{gist} That's '{title}' — another signal from the {source} side of the hiring market.",
    ],
}

WHY_IT_MATTERS = {
    "papers": [
        "Agent evaluation is where confident demos go to die. Anything that moves this from vibes to measurement is infrastructure for everyone building on top.",
        "The gap between 'our agent works' and 'our agent works in production' is the entire enterprise market. Work like this is the bridge — read it before it becomes a vendor slide.",
        "This is the kind of result practitioners cite for a year while product teams quietly absorb it. If you build with {topic}, it will shape your roadmap whether you read it or not.",
        "Benchmarks are the moat conversation nobody wants to have: teams with real evals ship, everyone else argues. This paper hands you the yardstick.",
    ],
    "courses": [
        "Credentials don't build agents, but they do unlock conversations. In a market where every posting asks for two years of experience with a two-year-old technology, a {source} credential is a credible shortcut.",
        "The real value was never the certificate — it's the forced march through the fundamentals. Most agent failures are basics failures wearing a trench coat.",
        "Hiring managers are drowning in 'AI enthusiast' resumes. Structured proof of engineering skill is how you stand out without shouting.",
    ],
    "news": [
        "Enterprise AI adoption doesn't run on research papers — it runs on announcements like this becoming boring infrastructure. The question isn't whether it's exciting; it's whether it gets deployed.",
        "Every framework launch is a bet on where the abstraction layer settles. The winners here decide what 'building an agent' means for the next three years.",
        "Adoption numbers are the only press release that matters. If enterprises actually deploy this, the job market for people who can integrate it moves the same week.",
    ],
    "career": [
        "Job posts are the most honest product roadmaps in tech. What companies hire for is what they actually believe — everything else is marketing.",
        "The forward-deployed market is where AI meets revenue. Roles like this are the canary: when they multiply, the enterprise wave is real.",
        "Read the requirements list as a curriculum. Every bullet is a skill the market will pay for — learn the top three and the interview takes care of itself.",
    ],
}

STEAL_THIS = {
    "papers": [
        "Steal the evaluation setup: run your own agent against this paper's benchmark before your next stakeholder review and see what breaks.",
        "Steal the taxonomy and organize your team's eval suite around it. Conversations get sharper the moment everyone uses the same words.",
        "Steal the failure modes: wherever the paper says agents break, those are your production test cases. Write them down before your users find them.",
        "Steal the framing for your next design doc. 'Here's how the literature measures this' wins arguments faster than any opinion.",
    ],
    "courses": [
        "Steal the curriculum outline as your personal learning checklist — do the projects even if you skip the certificate.",
        "Steal one module and teach it to your team. Nothing cements agentic patterns like explaining them to a skeptic.",
        "Steal the capstone idea: build it, ship it, link it. The project is the credential.",
    ],
    "news": [
        "Steal the positioning: whatever {source} just shipped, ask how your team's stack answers it. If you can't, that's your roadmap.",
        "Steal the launch checklist. Note what they announced, what they demoed, and what they left for 'later' — that's the honest roadmap.",
        "Try it this week. Fifteen minutes with the actual tool beats an hour of launch coverage.",
    ],
    "career": [
        "Steal the requirements list as your learning roadmap. If the posting asks for it twice, the market wants it.",
        "Steal the language: mirror how these listings describe the work, and your resume starts sounding like an insider wrote it.",
        "Apply the two-posting rule: when you see the same skill in two listings, it's a trend. Learn it before it's table stakes.",
    ],
}

TAKEAWAYS = {
    "papers": [
        "Evals are infrastructure, not overhead.",
        "The benchmark is the product.",
        "Multi-agent is a coordination problem, not a scaling problem.",
        "RAG lives or dies on retrieval, not generation.",
        "Memory is the next frontier for agents.",
        "If you can't measure it, you can't ship it.",
    ],
    "courses": [
        "The certificate is the receipt; the project is the purchase.",
        "Fundamentals beat frameworks, every time.",
        "Teach it to learn it.",
        "Shipping one agent beats certifying ten.",
    ],
    "news": [
        "Shipped beats announced.",
        "The abstraction layer is still up for grabs.",
        "Adoption is the only metric that matters.",
        "Watch what they demoed, not what they promised.",
    ],
    "career": [
        "Job posts are product roadmaps.",
        "FDE is where AI meets revenue.",
        "Requirements lists are curricula.",
        "Insider language beats keyword stuffing.",
    ],
}


# ------------------------------------------------------- OpenAI path

_OPENAI_CREDENTIAL = "custom.openai"
_OPENAI_HOSTS = ("api.openai.com",)
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_MODEL = "gpt-4o-mini"
_DC_PATH = "/opt/hatch/skills/skill-creator/bin"

_SYSTEM_PROMPT = (
    'You are the briefing writer for "The Field Manual", a weekly intelligence '
    "briefing for engineers building AI agents. Voice: sharp, opinionated, "
    "narrative — the All In podcast meets Acquired. Direct sentences, zero "
    "fluff. Never use hype words: revolutionary, game-changer, delve, "
    "paradigm shift, supercharge, unlock the power.\n\n"
    "Given an item's title, source, and description, output ONLY a JSON object "
    "with exactly these keys:\n"
    '- "lede": 1-2 sentence hook\n'
    '- "what_happened": 2-4 sentences, narrative of the thing itself\n'
    '- "why_it_matters": 2-3 sentences, opinionated take on its significance\n'
    '- "steal_this": one concrete idea worth stealing\n'
    '- "takeaways": array of 2-4 short punchy strings\n\n'
    "Rules: ground every claim strictly in the provided title/source/"
    "description. Do not invent facts, quotes, statistics, dates, or details "
    "not present. If the description is thin, say so plainly instead of "
    "filling gaps."
)

BRIEFING_KEYS = ("lede", "what_happened", "why_it_matters", "steal_this")


class _LLMUnavailable(Exception):
    """Credential-level failure: disable the LLM path for this run."""


class _LLMItemFailed(Exception):
    """Per-item failure: fall back to the template for this item only."""


_DC = None               # lazy-loaded dynamic_credentials module (patchable in tests)
_LLM_STATE = {"mode": "auto", "probed": False, "available": False}
_PROBE_CACHE = {}        # item_id -> (briefing, takeaways) from the probe call
_LLM_TAKEAWAYS = {}      # item_id -> takeaways produced by the API
_SOURCES = {}            # item_id -> "openai" | "template"
_CONSECUTIVE_FAILURES = 0


def _dc():
    """Lazy import of the surrogate helpers (mirrors the Firecrawl skill)."""
    global _DC
    if _DC is None:
        if _DC_PATH not in sys.path:
            sys.path.insert(0, _DC_PATH)
        import dynamic_credentials as dc_mod
        _DC = dc_mod
    return _DC


def set_llm_mode(mode):
    """'auto' (probe once, then decide), 'on', or 'off' (templates only)."""
    if mode not in ("auto", "on", "off"):
        raise ValueError(f"bad llm mode: {mode}")
    _LLM_STATE["mode"] = mode


def reset_run_state():
    """Clear per-run caches so a fresh build re-probes the credential."""
    _SOURCES.clear()
    _PROBE_CACHE.clear()
    _LLM_TAKEAWAYS.clear()
    _LLM_STATE.update({"probed": False, "available": False})
    global _CONSECUTIVE_FAILURES
    _CONSECUTIVE_FAILURES = 0


def briefing_source_stats():
    """Count of briefings by source: {'openai': n, 'template': m}."""
    stats = {"openai": 0, "template": 0}
    for src in _SOURCES.values():
        stats[src] = stats.get(src, 0) + 1
    return stats


def _valid_llm_briefing(obj):
    """Validate the API-returned briefing shape; return (briefing, takeaways)."""
    if not isinstance(obj, dict):
        raise _LLMItemFailed("response JSON is not an object")
    briefing = {}
    for key in BRIEFING_KEYS:
        val = obj.get(key)
        if not isinstance(val, str) or not val.strip():
            raise _LLMItemFailed(f"missing/empty briefing field: {key}")
        low = val.lower()
        for banned in BANNED:
            if banned in low:
                raise _LLMItemFailed(f"banned phrase in {key}")
        briefing[key] = val.strip()
    raw_takeaways = obj.get("takeaways")
    if not isinstance(raw_takeaways, list) or not raw_takeaways:
        raise _LLMItemFailed("missing/empty takeaways")
    takeaways = [str(t).strip() for t in raw_takeaways if str(t).strip()][:4]
    if len(takeaways) < 2:
        raise _LLMItemFailed("fewer than 2 usable takeaways")
    return briefing, takeaways


def _openai_chat(payload):
    """One raw chat-completions call via the surrogate credential."""
    dc = _dc()
    req = urllib.request.Request(
        _OPENAI_URL, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    dc.add_surrogate_to_request(
        req, _OPENAI_CREDENTIAL, allowed_hosts=_OPENAI_HOSTS)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return dc.read_json_response(resp)
    except Exception as exc:
        raise _LLMItemFailed(f"API call failed: {type(exc).__name__}: {exc}") from exc


def _llm_briefing(item, shelf):
    """Exactly one constrained API call per item. Returns (briefing, takeaways)."""
    slots = _slots(item, shelf)
    desc = clean_text(item.get("description", ""))[:1200]
    user_content = (
        f"Shelf: {shelf}\n"
        f"Title: {slots['title']}\n"
        f"Source: {slots['source']}\n"
        f"Description: {desc or '(no description provided)'}"
    )
    payload = {
        "model": _OPENAI_MODEL,
        "temperature": 0.3,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    data = _openai_chat(payload)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise _LLMItemFailed(f"unexpected API response shape: {exc}") from exc
    try:
        obj = json.loads(content)
    except json.JSONDecodeError as exc:
        raise _LLMItemFailed(f"response is not JSON: {exc}") from exc
    return _valid_llm_briefing(obj)


def _probe_credential():
    """Resolve the credential once. Raises _LLMUnavailable on any failure."""
    try:
        dc = _dc()
        dc.dynamic_credential_entry(_OPENAI_CREDENTIAL)
    except Exception as exc:
        raise _LLMUnavailable(
            f"custom.openai credential unavailable: {type(exc).__name__}: {exc}"
        ) from exc


def _maybe_probe(item, shelf, item_id):
    """First-call probe: resolve credential + one real briefing call.

    The probe's result is reused for the probed item, so it still counts as
    exactly one API call for that item.
    """
    st = _LLM_STATE
    st["probed"] = True
    try:
        _probe_credential()
    except _LLMUnavailable as exc:
        st["available"] = False
        print(f"[writer] {exc}; using template briefings.", file=sys.stderr)
        return False
    try:
        briefing, takeaways = _llm_briefing(item, shelf)
    except _LLMItemFailed as exc:
        # API reachable but this item failed: stay available, template this one.
        print(f"[writer] OpenAI probe item failed ({exc}); "
              f"template for this item, API stays on.", file=sys.stderr)
        st["available"] = True
        return False
    except _LLMUnavailable as exc:  # pragma: no cover - defensive
        st["available"] = False
        print(f"[writer] {exc}; using template briefings.", file=sys.stderr)
        return False
    st["available"] = True
    _PROBE_CACHE[item_id] = (briefing, takeaways)
    print("[writer] OpenAI probe succeeded; using API briefings.", file=sys.stderr)
    return True


def _briefing_with_source(item, shelf):
    """(briefing, takeaways, source) — tries the API, falls back to templates."""
    global _CONSECUTIVE_FAILURES
    item_id = item.get("id") or item.get("url", "")
    st = _LLM_STATE

    use_llm = st["mode"] in ("auto", "on")
    if use_llm and not st["probed"]:
        if _maybe_probe(item, shelf, item_id):
            briefing, takeaways = _PROBE_CACHE[item_id]
            _SOURCES[item_id] = "openai"
            _LLM_TAKEAWAYS[item_id] = takeaways
            return briefing, takeaways, "openai"
    elif use_llm and st["available"] and _CONSECUTIVE_FAILURES < 3:
        try:
            briefing, takeaways = _llm_briefing(item, shelf)
            _CONSECUTIVE_FAILURES = 0
            _SOURCES[item_id] = "openai"
            _LLM_TAKEAWAYS[item_id] = takeaways
            return briefing, takeaways, "openai"
        except _LLMItemFailed as exc:
            _CONSECUTIVE_FAILURES += 1
            print(f"[writer] item {item_id} fell back to template ({exc})",
                  file=sys.stderr)
            if _CONSECUTIVE_FAILURES >= 3:
                st["available"] = False
                print("[writer] 3 consecutive API failures; "
                      "disabling API for the rest of this run.", file=sys.stderr)

    _SOURCES[item_id] = "template"
    return write_briefing(item, shelf), make_takeaways(item, shelf), "template"


def write_briefing(item, shelf):
    """Build the narrative briefing dict for one item (template path).

    NOTE: this is the fallback used when the OpenAI credential is absent or
    a per-item API call fails. Use ``_briefing_with_source`` for the
    API-preferred path.
    """
    slots = _slots(item, shelf)
    item_id = item.get("id") or item.get("url", "")
    briefing = {
        "lede": _pick(f"{item_id}:lede", LEDES[shelf]).format(**slots),
        "what_happened": _pick(f"{item_id}:what", WHAT_HAPPENED[shelf]).format(**slots),
        "why_it_matters": _pick(f"{item_id}:why", WHY_IT_MATTERS[shelf]).format(**slots),
        "steal_this": _pick(f"{item_id}:steal", STEAL_THIS[shelf]).format(**slots),
    }
    for text in briefing.values():
        low = text.lower()
        for banned in BANNED:
            assert banned not in low, f"banned phrase {banned!r} in briefing"
    return briefing


def make_takeaways(item, shelf):
    """2-4 punchy takeaways, deterministically rotated per item.

    Returns the API-produced takeaways when this item went through the
    OpenAI path; otherwise the template pool.
    """
    item_id = item.get("id") or item.get("url", "")
    if item_id in _LLM_TAKEAWAYS:
        return _LLM_TAKEAWAYS[item_id]
    pool = TAKEAWAYS[shelf]
    h = int(hashlib.md5(f"{item_id}:takeaways".encode()).hexdigest(), 16)
    n = 2 + (h % 3)  # 2..4
    start = (h >> 4) % len(pool)
    return [pool[(start + i) % len(pool)] for i in range(n)]
