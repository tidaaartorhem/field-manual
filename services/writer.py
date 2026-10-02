#!/usr/bin/env python3
"""Turn curated items into a story-like newsletter edition.

Voice rules live in ``VOICE.md``: Acquired's narrative machinery (the long
arc, the mechanism breakdown, "why does this win") aimed at All In's news
cycle (operator skepticism, "here's what nobody is saying").

Two LLM jobs, both constrained:

1. **Per-item briefings** — one API call per item producing lede /
   what_happened / why_it_matters / steal_this + takeaways.
2. **Section narratives** — one API call per section weaving that section's
   items into a story-like narrative with a closing take.
3. **Edition lede** — one API call for the opening paragraph.

Fallback policy: when the ``custom.openai`` credential is missing,
rejected, or any call fails, hand-written templates take over. Templates
reference only REAL titles, sources, and descriptions. The circuit breaker
disables the API for the run after 3 consecutive failures. No key or
surrogate value is ever hardcoded, logged, or persisted.
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
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)       # headings
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
    """First ~2 sentences of the cleaned text, or an honest fallback.

    Prefers ``full_text`` (scraped article body) when the item was
    enriched — briefings are then written from the real article, not the
    snippet.
    """
    t = clean_text(item.get("full_text") or item.get("description", ""))
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
    return {"signal": "agents", "tech": "AI", "startups": "startups",
            "podcasts": "the episode"}[shelf]


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
    "signal": [
        "'{title}' is making the rounds in the {topic} crowd — and for once the forwarding is justified.",
        "New on {source}: '{title}'. The headline undersells it.",
        "'{title}' just landed, and it's the kind of story that ends up in architecture docs rather than tweets.",
    ],
    "tech": [
        "'{title}' — {source} moved this week, and the ripples are worth tracking.",
        "Filed under 'actually matters': '{title}' ({source}).",
    ],
    "startups": [
        "'{title}' — another data point in where startup energy is flowing.",
        "{source} reports: '{title}'. Here's the read beneath the announcement.",
    ],
    "podcasts": [
        "On {source}: '{title}'. Worth an hour of your ears — here's why.",
        "This week's listen: '{title}' ({source}). The conversation worth catching.",
    ],
}

WHAT_HAPPENED = {
    "signal": [
        "Here's the substance. {gist} The story is '{title}', via {source}.",
        "The short version: {gist} The longer version is '{title}' — {source}'s latest move in the {topic} land grab.",
    ],
    "tech": [
        "{gist} That's the news: '{title}', straight from {source}.",
        "Here's what happened: {gist} '{title}' is {source}'s read on where things stand.",
    ],
    "startups": [
        "{gist} That's '{title}' — the startup world, in one headline.",
        "The deal, in brief: {gist} '{title}' via {source}.",
    ],
    "podcasts": [
        "{gist} That's the shape of '{title}' — this week's {source} conversation.",
        "On the show: {gist} '{title}' ({source}) goes there.",
    ],
}

WHY_IT_MATTERS = {
    "signal": [
        "Enterprise AI doesn't run on research papers — it runs on announcements like this becoming boring infrastructure. The question isn't whether it's exciting; it's whether it gets deployed.",
        "Every agent launch is a bet on where the abstraction layer settles. The winners here decide what 'building an agent' means for the next three years.",
        "Watch what they shipped, not what they promised. Adoption numbers are the only press release that matters.",
    ],
    "tech": [
        "Tech narratives move in weeks now, not quarters. The winners aren't the ones with the best announcement — they're the ones whose thing becomes infrastructure while everyone else is still writing hot takes.",
        "Follow the mechanism, not the headline. Whatever {source} is describing, ask who it displaces and who collects the rent.",
    ],
    "startups": [
        "Startup announcements are the most honest leading indicators in tech. Where the money and talent flow this week is where the market will be in eighteen months.",
        "Every funding round is a bet on a thesis. Read the thesis, not the valuation — the valuation is marketing, the thesis is the product.",
    ],
    "podcasts": [
        "The best operator thinking never makes it into blog posts — it leaks out in long conversations. This is where the unguarded takes live.",
        "Podcasts are where narratives get stress-tested before they harden. Listen for what the guests argue about, not what they agree on.",
    ],
}

STEAL_THIS = {
    "signal": [
        "Steal the positioning: whatever just shipped, ask how your stack answers it. If you can't, that's your roadmap.",
        "Try it this week. Fifteen minutes with the actual tool beats an hour of coverage.",
    ],
    "tech": [
        "Steal the framing for your next design doc: 'here's how the industry is moving' wins arguments faster than any opinion.",
        "Ask the displacement question: who loses if this wins? That's usually the more interesting trade.",
    ],
    "startups": [
        "Steal the thesis, not the company. If the bet is right, there's room for a second player who executes better.",
        "Note what they announced versus what they demoed. The gap is the honest roadmap.",
    ],
    "podcasts": [
        "Steal one argument and pressure-test it against your own work this week.",
        "Listen at 1.5x, but pause when they disagree with each other — that's the good stuff.",
    ],
}

TAKEAWAYS = {
    "signal": [
        "Shipped beats announced.",
        "The abstraction layer is still up for grabs.",
        "Adoption is the only metric that matters.",
        "Watch the demo, not the press release.",
    ],
    "tech": [
        "Infrastructure eats announcements.",
        "Follow the mechanism, not the headline.",
        "Narratives move in weeks now.",
    ],
    "startups": [
        "Funding is a thesis, not a trophy.",
        "Talent flow is the leading indicator.",
        "Read the announcement; bet on the execution.",
    ],
    "podcasts": [
        "Unguarded takes beat polished posts.",
        "Arguments are more informative than agreements.",
        "Operators leak the real story in long conversations.",
    ],
}

SECTION_NARRATIVE_TEMPLATES = [
    ("This section is about {topic_word}. {item_beats} The thread connecting "
     "them: everyone's placing bets on the same question, and the answers "
     "are starting to diverge — which is exactly when it gets interesting.",
     "The take: watch what ships, not what trends."),
    ("A lot happened in {topic_word} this week. {item_beats} Read together, "
     "they tell one story: the gap between announcement and deployment is "
     "where all the real action is.",
     "The take: the winners will be decided by who deploys, not who announces."),
    ("{item_beats} That's {topic_word}, this week. The press releases say one "
     "thing; the incentives say another — and the incentives are usually right.",
     "The take: follow the incentives, not the headlines."),
]

LEDE_TEMPLATES = [
    "Forty-eight hours in AI is a long time. This edition stitches the week into one story: {section_beats}",
    "A lot can happen in two days. Here's the last 48 hours, woven into something you can actually think with: {section_beats}",
]


# ------------------------------------------------------- OpenAI path

_OPENAI_CREDENTIAL = "custom.openai"
_OPENAI_HOSTS = ("api.openai.com",)
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_MODEL = "gpt-4o-mini"
_DC_PATH = "/opt/hatch/skills/skill-creator/bin"

_SYSTEM_PROMPT = (
    'You are the briefing writer for "The Field Manual", a 48-hour newsletter '
    "for engineers building AI agents. Voice: Acquired's narrative machinery "
    "(the long arc, the mechanism breakdown, receipts, 'why does this win') "
    "aimed at All In's news cycle (operator skepticism, 'here's what nobody "
    "is saying'). Direct sentences, zero fluff. Never use hype words: "
    "revolutionary, game-changer, delve, paradigm shift, supercharge, unlock "
    "the power.\n\n"
    "Given an item's title, source, and description, output ONLY a JSON object "
    "with exactly these keys:\n"
    '- "lede": 1-2 sentence hook\n'
    '- "what_happened": 2-4 sentences, narrative of the thing itself\n'
    '- "why_it_matters": 2-3 sentences, opinionated take with the mechanism\n'
    '- "steal_this": one concrete idea worth stealing\n'
    '- "takeaways": array of 2-4 short punchy strings\n\n'
    "Rules: ground every claim strictly in the provided title/source/"
    "description. Do not invent facts, quotes, statistics, dates, or details "
    "not present. If the description is thin, say so plainly instead of "
    "filling gaps."
)

_SECTION_SYSTEM_PROMPT = (
    'You are the section editor for "The Field Manual", a 48-hour newsletter. '
    "Voice: Acquired meets All In — narrative arc, mechanism over "
    "announcement, operator skepticism, 'here's what nobody is saying'. "
    "Never use hype words: revolutionary, game-changer, delve, paradigm "
    "shift, supercharge, unlock the power.\n\n"
    "Given a section's items (title, source, one-line gist each), output ONLY "
    "a JSON object with exactly these keys:\n"
    '- "narrative": 4-7 sentences weaving the items into ONE story-like '
    "narrative. Name the arc: where this started, the inflection this week, "
    "what winning looks like from here. Include one skeptical beat — decode "
    "incentives, don't repeat press releases.\n"
    '- "closing_take": one sharp closing line, the thing you would say to a '
    "smart friend who asked 'so what?'\n\n"
    "Rules: every claim must trace to the provided items. Do not invent "
    "facts, quotes, or details. If an item's gist is thin, don't lean on it."
)

_LEDE_SYSTEM_PROMPT = (
    'You are the editor of "The Field Manual", a 48-hour newsletter for '
    "engineers building AI agents. Voice: Acquired meets All In — story-like, "
    "sharp, opinionated, zero fluff. Never use hype words: revolutionary, "
    "game-changer, delve, paradigm shift, supercharge, unlock the power.\n\n"
    "Given one-line summaries of each section, output ONLY a JSON object with "
    'exactly one key: "lede" — 3-5 sentences opening the edition like a '
    "story, telling the reader why these 48 hours mattered and what to read "
    "first. No invented facts."
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


def _check_banned(text, where):
    low = text.lower()
    for banned in BANNED:
        if banned in low:
            raise _LLMItemFailed(f"banned phrase in {where}")


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


def _chat_json(system_prompt, user_content, max_tokens):
    """One constrained JSON chat call. Returns the parsed object."""
    payload = {
        "model": _OPENAI_MODEL,
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    }
    data = _openai_chat(payload)
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise _LLMItemFailed(f"unexpected API response shape: {exc}") from exc
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise _LLMItemFailed(f"response is not JSON: {exc}") from exc


def _valid_llm_briefing(obj):
    """Validate the API-returned briefing shape; return (briefing, takeaways)."""
    if not isinstance(obj, dict):
        raise _LLMItemFailed("response JSON is not an object")
    briefing = {}
    for key in BRIEFING_KEYS:
        val = obj.get(key)
        if not isinstance(val, str) or not val.strip():
            raise _LLMItemFailed(f"missing/empty briefing field: {key}")
        _check_banned(val, key)
        briefing[key] = val.strip()
    raw_takeaways = obj.get("takeaways")
    if not isinstance(raw_takeaways, list) or not raw_takeaways:
        raise _LLMItemFailed("missing/empty takeaways")
    takeaways = [str(t).strip() for t in raw_takeaways if str(t).strip()][:4]
    if len(takeaways) < 2:
        raise _LLMItemFailed("fewer than 2 usable takeaways")
    return briefing, takeaways


def _llm_briefing(item, shelf):
    """Exactly one constrained API call per item. Returns (briefing, takeaways)."""
    slots = _slots(item, shelf)
    desc = clean_text(item.get("description", ""))[:1200]
    user_content = (
        f"Section: {shelf}\n"
        f"Title: {slots['title']}\n"
        f"Source: {slots['source']}\n"
        f"Description: {desc or '(no description provided)'}"
    )
    return _valid_llm_briefing(
        _chat_json(_SYSTEM_PROMPT, user_content, max_tokens=500))


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
        _check_banned_text(text)
    return briefing


def _check_banned_text(text):
    low = text.lower()
    for banned in BANNED:
        assert banned not in low, f"banned phrase {banned!r} in briefing"


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


def brief_item(item, shelf):
    """Public entry: (briefing dict, takeaways list) for one item."""
    briefing, takeaways, _ = _briefing_with_source(item, shelf)
    return briefing, takeaways


# ------------------------------------------------- section narratives

def _template_section_narrative(section_id, section_title, items):
    """Connective editorial copy when the API is unavailable."""
    key = f"section:{section_id}"
    beats = []
    for it in items[:4]:
        beats.append(f"'{it.get('title', 'Untitled')}' ({source_name(it.get('url', ''))})")
    item_beats = "; ".join(beats) + "." if beats else "a quiet stretch."
    topic = {"signal": "agentic AI", "tech": "the wider tech world",
             "startups": "startup land",
             "podcasts": "the podcast circuit"}.get(section_id, section_id)
    narrative_t, take_t = _pick(key, SECTION_NARRATIVE_TEMPLATES)
    return {
        "narrative": narrative_t.format(topic_word=topic, item_beats=item_beats),
        "closing_take": take_t,
    }


def write_section_narrative(section_id, section_title, items):
    """Weave a section's items into one story-like narrative.

    One constrained API call; template fallback on any failure.
    Returns {'narrative': str, 'closing_take': str}.
    """
    st = _LLM_STATE
    item_lines = []
    for it in items:
        g = gist(it) or "(details thin)"
        item_lines.append(f"- {it.get('title', 'Untitled')} "
                          f"[{source_name(it.get('url', ''))}]: {g[:220]}")
    user_content = (f"Section: {section_title}\nItems:\n" + "\n".join(item_lines))

    # The item-briefing pass runs first, so by now the probe has resolved:
    # st["available"] is authoritative. Never probe on a synthetic item.
    use_llm = st["mode"] in ("auto", "on") and st["available"]
    if use_llm:
        try:
            obj = _chat_json(_SECTION_SYSTEM_PROMPT, user_content,
                             max_tokens=600)
            narrative = obj.get("narrative", "")
            closing = obj.get("closing_take", "")
            if (isinstance(narrative, str) and narrative.strip()
                    and isinstance(closing, str) and closing.strip()):
                _check_banned(narrative, "narrative")
                _check_banned(closing, "closing_take")
                return {"narrative": narrative.strip(),
                        "closing_take": closing.strip()}
            raise _LLMItemFailed("missing/empty narrative fields")
        except (_LLMItemFailed, _LLMUnavailable) as exc:
            print(f"[writer] section {section_id} narrative fell back "
                  f"to template ({exc})", file=sys.stderr)
    return _template_section_narrative(section_id, section_title, items)


def _template_lede(section_titles):
    beats = "; ".join(t for t in section_titles if t)
    tmpl = _pick("lede", LEDE_TEMPLATES)
    return tmpl.format(section_beats=beats + "." if beats else "the last two days, distilled.")


def write_edition_lede(section_summaries):
    """One constrained API call for the edition's opening paragraph.

    ``section_summaries``: list of (section_title, closing_take).
    Falls back to a template on any failure.
    """
    st = _LLM_STATE
    lines = [f"- {title}: {take}" for title, take in section_summaries]
    user_content = "Sections this edition:\n" + "\n".join(lines)
    use_llm = st["mode"] in ("auto", "on") and st["available"]
    if use_llm:
        try:
            obj = _chat_json(_LEDE_SYSTEM_PROMPT, user_content, max_tokens=300)
            lede = obj.get("lede", "")
            if isinstance(lede, str) and lede.strip():
                _check_banned(lede, "lede")
                return lede.strip()
            raise _LLMItemFailed("missing/empty lede")
        except (_LLMItemFailed, _LLMUnavailable) as exc:
            print(f"[writer] edition lede fell back to template ({exc})",
                  file=sys.stderr)
    return _template_lede([t for t, _ in section_summaries])


# ------------------------------------------------- 500-700 word digest

DIGEST_WORD_TARGET = (500, 700)

_DIGEST_SYSTEM_PROMPT = (
    'You are the editor of "The Field Manual", a 48-hour newsletter for '
    "engineers building AI agents. Voice: Acquired meets All In — story-like, "
    "sharp, opinionated, zero fluff. Never use hype words: revolutionary, "
    "game-changer, delve, paradigm shift, supercharge, unlock the power.\n\n"
    "Given this edition's items (title, source, gist, url each), write a "
    "500-700 word digest as markdown:\n"
    "- Open with 2-3 sentences on why these 48 hours mattered.\n"
    "- Then short punchy takes under bold subheads (e.g. **Agents**, "
    "**Startups**, **The wider current**). Weave items into a story; do not "
    "just list them.\n"
    "- Reference EVERY item at least once as an inline markdown link "
    "[title](url) using the EXACT url provided for that item.\n"
    "- Close with one sharp 'so what' line.\n"
    "- Do NOT include a title or H1 heading — start directly with the "
    "opening sentences; use **bold** subheads for sections.\n\n"
    "Rules: use only the urls provided — never invent links, facts, quotes, "
    "statistics, or details not present in the gists. If a gist is thin, "
    "say so plainly instead of filling gaps.\n\n"
    'Output ONLY a JSON object with exactly one key: "digest" (the markdown '
    "string)."
)

_DIGEST_COMPRESS_PROMPT = (
    "Compress the following newsletter digest to under 650 words. Keep every "
    "markdown link EXACTLY as written ([title](url) pairs must be preserved "
    "verbatim). Keep the voice and the closing line. Output ONLY a JSON "
    'object with exactly one key: "digest".'
)


def _digest_user_content(items, notes=()):
    lines = []
    for it in items:
        g = (it.get("gist") or "(details thin)").strip()[:300]
        lines.append(
            f"- {it.get('title', 'Untitled')} "
            f"[{it.get('source', 'web')}]: {g}\n"
            f"  url: {it.get('url', '')}")
    content = "This edition's items:\n" + "\n".join(lines)
    if notes:
        content += "\n\nEditor notes:\n" + "\n".join(f"- {n}" for n in notes)
    return content


def _extract_md_links(md):
    """All http(s) URLs referenced as markdown links."""
    return re.findall(r"\[[^\]]+\]\((https?://[^)\s]+)\)", md)


def _word_count(text):
    return len(text.split())


def _normalize_url(u):
    return (u or "").strip().rstrip("/").lower()


def _validate_digest(obj, urls, where="digest"):
    """Validate the digest shape; reject invented links. Returns markdown."""
    if not isinstance(obj, dict):
        raise _LLMItemFailed(f"{where}: response JSON is not an object")
    digest = obj.get("digest")
    if not isinstance(digest, str) or not digest.strip():
        raise _LLMItemFailed(f"{where}: missing/empty digest")
    digest = digest.strip()
    _check_banned(digest, where)
    known = {_normalize_url(u) for u in urls}
    for link in _extract_md_links(digest):
        if _normalize_url(link) not in known:
            raise _LLMItemFailed(
                f"{where}: link to unknown URL (invented?): {link[:80]}")
    return digest


def _truncate_to_words(text, limit):
    """Hard-truncate at a sentence boundary to <= limit words."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    out, count = [], 0
    for p in parts:
        w = len(p.split())
        if out and count + w > limit:
            break
        out.append(p)
        count += w
    return " ".join(out).strip()


def _enforce_word_limit(digest, urls, chat):
    """Guard the 500-700 word budget.

    Over 700 words: one compression pass via the API (when available), then
    a hard truncate at a sentence boundary, marked. Returns (digest, truncated).
    """
    if _word_count(digest) <= DIGEST_WORD_TARGET[1]:
        return digest, False
    if chat is not None:
        try:
            obj = chat(_DIGEST_COMPRESS_PROMPT, digest, 1600)
            compressed = _validate_digest(obj, urls, where="digest-compress")
            if _word_count(compressed) <= DIGEST_WORD_TARGET[1]:
                return compressed, False
            digest = compressed
        except _LLMItemFailed as exc:
            print(f"[writer] digest compression failed ({exc}); truncating.",
                  file=sys.stderr)
    truncated = _truncate_to_words(digest, DIGEST_WORD_TARGET[1])
    marker = "\n\n*Trimmed to fit the 700-word digest.*"
    # Reserve room for the marker so the final text still fits the budget.
    room = DIGEST_WORD_TARGET[1] - len(marker.split()) - 1
    truncated = _truncate_to_words(digest, room)
    return truncated + marker, True


def _template_digest(items):
    """Honest fallback digest when the API is unavailable.

    Linked titles grouped by shelf with one gist sentence each — no invented
    takes, no hype.
    """
    by_shelf = {}
    for it in items:
        by_shelf.setdefault(it.get("shelf", "signal"), []).append(it)
    shelf_heads = {"signal": "Agents", "tech": "The wider current",
                   "startups": "Startups", "podcasts": "The podcast circuit"}
    parts = ["The last 48 hours, distilled the old-fashioned way — "
             "no model was available for this edition, so here are the "
             "stories, straight."]
    for shelf, shelf_items in by_shelf.items():
        parts.append(f"\n**{shelf_heads.get(shelf, shelf)}**")
        for it in shelf_items:
            g = (it.get("gist") or "").strip()
            first = re.split(r"(?<=[.!?])\s+", g)[0] if g else "Details thin."
            parts.append(f"[{it.get('title', 'Untitled')}]({it.get('url', '')}) — {first}")
    parts.append("\nSo what? Read the links; the stories are the digest this time.")
    return "\n\n".join(parts)


def write_digest(items, notes=(), _chat_fn=None):
    """One constrained call -> a 500-700 word story digest with inline links.

    ``items``: [{title, url, source, gist, shelf}]. ``notes``: extra editor
    notes (e.g. quiet podcast circuit). Returns (markdown, word_count,
    truncated). The digest API call doubles as the credential probe.
    """
    chat = _chat_fn or _chat_json
    st = _LLM_STATE
    urls = [it.get("url", "") for it in items if it.get("url", "")]
    use_llm = st["mode"] in ("auto", "on")
    digest = None
    if use_llm and not st["probed"]:
        # Light probe: resolve the credential only. The digest call itself
        # is the real probe — no wasted call.
        try:
            _probe_credential()
            st["probed"] = True
            st["available"] = True
        except _LLMUnavailable as exc:
            st["probed"] = True
            st["available"] = False
            print(f"[writer] {exc}; template digest.", file=sys.stderr)
    if use_llm and st["available"]:
        try:
            obj = chat(_DIGEST_SYSTEM_PROMPT,
                       _digest_user_content(items, notes), 1600)
            digest = _validate_digest(obj, urls)
        except _LLMItemFailed as exc:
            print(f"[writer] digest fell back to template ({exc})",
                  file=sys.stderr)
    if digest is None:
        digest = _template_digest(items)
    api_chat = chat if (use_llm and st["available"]) else None
    digest, truncated = _enforce_word_limit(digest, urls, api_chat)
    return digest, _word_count(digest), truncated
