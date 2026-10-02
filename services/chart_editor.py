#!/usr/bin/env python3
"""Chart editor: one constrained OpenAI call per edition.

The deterministic pipeline (services/charts.py) computes candidate charts
from real aggregates under hard rules (min 3 data points, no filler).
The editor does presentation judgment only:

- KEEP / REDESIGN / DROP per candidate chart.
- Rewrite titles so they state the INSIGHT, not the metric.
- Suggest the right chart type for the data.

It never touches the data: validated decisions are re-applied to the
original specs, and unknown ids / bad shapes fall back to keeping the
computed charts unchanged. At most MAX_CHARTS survive.

Fallback: any failure (credential missing, API error, bad response)
returns the candidates unchanged.
"""
import json
import sys
import urllib.request

from .writer import (_dc, _OPENAI_CREDENTIAL, _OPENAI_HOSTS, _OPENAI_URL,
                     _OPENAI_MODEL, BANNED)

MAX_CHARTS = 4
_DECISIONS = ("KEEP", "REDESIGN", "DROP")
_KINDS = ("bar", "hbar")

_MODE = "auto"


def set_editor_mode(mode):
    """'auto' (default) or 'off' (keep computed charts, no API call)."""
    if mode not in ("auto", "off"):
        raise ValueError(f"bad editor mode: {mode}")
    global _MODE
    _MODE = mode


_SYSTEM_PROMPT = """You are the graphics editor of a tech magazine. You are \
given candidate charts computed from a 48-hour tech news edition. Each chart \
has an id, its current title/subtitle, its chart type, and its data \
(labels, values, value labels).

For each chart, decide:
- KEEP: the chart earns its place as-is.
- REDESIGN: the data is worth showing but the title should state the \
INSIGHT (the "so what"), not the metric, and/or a different chart type \
fits better.
- DROP: the chart does not earn its place. Drop flat data (all values \
nearly equal), drop anything with an obvious single outlier and nothing \
else, drop charts whose insight is trivial.

Rules:
- Keep at most 4 charts; 2-3 strong ones beat 4 mediocre ones.
- Titles state the insight ("Agents dominate the conversation"), never the \
metric ("Topic mentions across stories").
- Subtitles stay factual and short (what is counted, over what window).
- Chart type is "bar" (vertical) or "hbar" (horizontal). Prefer "hbar" \
when labels are long.
- You may not invent, change, or reorder data. You only edit \
title/subtitle/kind and make keep/drop decisions.

Respond with JSON only:
{"charts": [{"id": "<id>", "decision": "KEEP|REDESIGN|DROP", \
"title": "<rewritten or original title>", "subtitle": "<factual subtitle>", \
"kind": "bar|hbar"}]}"""


def _user_content(specs):
    lines = []
    for s in specs:
        data_lines = "\n".join(
            f"    - {d['label']}: {d['value']} ({d.get('detail') or 'no label'})"
            for d in s["data"])
        lines.append(
            f"Chart id: {s['id']}\n"
            f"  title: {s['title']}\n"
            f"  subtitle: {s['subtitle']}\n"
            f"  kind: {s['kind']}\n"
            f"  data:\n{data_lines}\n"
            f"  computed as: {s.get('note', '')}")
    return ("Candidate charts for this 48-hour edition:\n\n"
            + "\n\n".join(lines))


def _check_banned(text, where):
    low = text.lower()
    for banned in BANNED:
        if banned in low:
            raise ValueError(f"banned phrase in {where}")


def _validate(raw, specs):
    """Validate the editor's JSON. Returns the decisions list.

    Raises ValueError on anything unexpected — the caller falls back to
    the computed charts.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("charts"), list):
        raise ValueError("response is not {charts: [...]}")
    known = {s["id"] for s in specs}
    decisions = []
    for entry in raw["charts"]:
        if not isinstance(entry, dict):
            raise ValueError("chart entry is not an object")
        cid = entry.get("id")
        if cid not in known:
            raise ValueError(f"unknown chart id: {cid!r}")
        if entry.get("decision") not in _DECISIONS:
            raise ValueError(f"bad decision for {cid!r}")
        if entry.get("kind") not in _KINDS:
            raise ValueError(f"bad kind for {cid!r}")
        title = entry.get("title")
        subtitle = entry.get("subtitle")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"missing title for {cid!r}")
        if not isinstance(subtitle, str) or not subtitle.strip():
            raise ValueError(f"missing subtitle for {cid!r}")
        _check_banned(title, f"title of {cid}")
        _check_banned(subtitle, f"subtitle of {cid}")
        decisions.append({
            "id": cid,
            "decision": entry["decision"],
            "title": title.strip(),
            "subtitle": subtitle.strip(),
            "kind": entry["kind"],
        })
    return decisions


def _apply(specs, decisions):
    """Re-apply validated decisions onto the ORIGINAL specs (data untouched)."""
    by_id = {s["id"]: s for s in specs}
    out = []
    for d in decisions:
        if d["decision"] == "DROP":
            continue
        spec = dict(by_id[d["id"]])
        spec["title"] = d["title"]
        spec["subtitle"] = d["subtitle"]
        spec["kind"] = d["kind"]
        out.append(spec)
    return out[:MAX_CHARTS]


def _real_chat(specs):
    """One constrained JSON chat call via the surrogate credential."""
    dc = _dc()
    try:
        dc.dynamic_credential_entry(_OPENAI_CREDENTIAL)
    except Exception as exc:
        raise RuntimeError(f"custom.openai credential unavailable: {exc}") from exc
    payload = {
        "model": _OPENAI_MODEL,
        "temperature": 0.3,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_content(specs)},
        ],
    }
    req = urllib.request.Request(
        _OPENAI_URL, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    dc.add_surrogate_to_request(req, _OPENAI_CREDENTIAL,
                                allowed_hosts=_OPENAI_HOSTS)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = dc.read_json_response(resp)
    except Exception as exc:
        raise RuntimeError(f"API call failed: {type(exc).__name__}: {exc}") from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected API response shape: {exc}") from exc
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"response is not JSON: {exc}") from exc


def edit_charts(specs, _chat_fn=None):
    """Run the editor over candidate specs. Returns the final spec list.

    ``_chat_fn`` is an injectable stand-in for the API call (tests).
    Any failure keeps the computed charts unchanged.
    """
    if not specs or _MODE == "off":
        return specs
    try:
        chat = _chat_fn or _real_chat
        decisions = _validate(chat(specs), specs)
        edited = _apply(specs, decisions)
        dropped = len(specs) - len(edited)
        print(f"[chart-editor] {len(edited)} kept, {dropped} dropped.",
              file=sys.stderr)
        return edited
    except Exception as exc:
        print(f"[chart-editor] {exc}; keeping computed charts.",
              file=sys.stderr)
        return specs
