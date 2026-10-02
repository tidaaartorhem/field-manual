#!/usr/bin/env python3
"""Personal source adder: scrape user-submitted URLs, scoped per user.

Visitors add URLs via the site's "Add a source" form; each is stored in the
Firestore ``user_sources`` collection with status ``pending``. This module:

- scrapes pending docs with Firecrawl (``/v2/scrape`` with a ``json`` format:
  title + 2-3 sentence summary + 3 key bullets), updating each doc to
  ``scraped`` (or ``failed`` with the error). Pending docs are never
  re-scraped — only ``status == 'pending'`` is touched;
- groups scraped docs by email for the per-user email step.

PRIVACY RULE: a user-added URL is scraped and used ONLY for that user. It is
never merged into the global newsletter, the charts, or anyone else's email.

Auth: same Firestore REST + firebase-CLI OAuth pattern as subscribers.py.
Firecrawl uses the stored ``custom.firecrawl`` credential via the skill's
surrogate helper (never a hardcoded key).

CLI::

    .venv/bin/python -m services.user_sources scrape   # scrape all pending
    .venv/bin/python -m services.user_sources emails   # print "email<TAB>path" per subscriber
"""
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/hatch/workspace/skills/firecrawl/bin")
from _client import request as firecrawl_request  # noqa: E402

from .subscribers import access_token, PROJECT  # noqa: E402

COLLECTION = "user_sources"
FIRESTORE = (f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
             f"/databases/(default)/documents")

EXTRACT_PROMPT = (
    "Extract from this page: its title, a 2-3 sentence plain-language "
    "summary of what it says, and 3 key bullet points. Ground everything in "
    "the page content; if the page is thin or paywalled, say so in the "
    "summary instead of inventing details."
)
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "bullets"],
}


def _firestore(method, path, payload=None, params=""):
    token = access_token()
    url = f"{FIRESTORE}{path}{params}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"firestore {method} {path}: HTTP {exc.code}: {body}")


def _s(fields, key):
    return (fields.get(key, {}).get("stringValue") or "").strip()


def _doc_to_source(doc):
    fields = doc.get("fields", {})
    bullets = [v.get("stringValue", "")
               for v in fields.get("bullets", {}).get("arrayValue", {}).get("values", [])]
    return {
        "name": doc.get("name", ""),
        "email": _s(fields, "email").lower(),
        "url": _s(fields, "url"),
        "title": _s(fields, "title"),
        "summary": _s(fields, "summary"),
        "bullets": [b for b in bullets if b],
        "status": _s(fields, "status") or "pending",
        "error": _s(fields, "error"),
    }


def list_all_sources():
    """Every doc in user_sources (small collection; filtered in Python)."""
    payload = _firestore("GET", f"/{COLLECTION}", params="?pageSize=1000")
    return [_doc_to_source(d) for d in payload.get("documents", [])]


def list_pending():
    return [s for s in list_all_sources() if s["status"] == "pending"]


def list_scraped_by_email():
    """{email: [sources]} for successfully scraped docs only."""
    grouped = {}
    for s in list_all_sources():
        if s["status"] == "scraped" and s["email"]:
            grouped.setdefault(s["email"], []).append(s)
    return grouped


def _update_doc(doc_name, field_updates):
    """PATCH specific fields on a doc. field_updates: {name: (type, value)}."""
    fields = {}
    for key, (ftype, value) in field_updates.items():
        if ftype == "string":
            fields[key] = {"stringValue": value}
        elif ftype == "array":
            fields[key] = {"arrayValue": {"values": [{"stringValue": v} for v in value]}}
        elif ftype == "timestamp":
            fields[key] = {"timestampValue": value}
    masks = "&".join(f"updateMask.fieldPaths={k}" for k in fields)
    short = doc_name.split("/documents/")[-1]
    return _firestore("PATCH", f"/{short}", payload={"fields": fields},
                      params=f"?{masks}")


def _mark_scraped(doc_name, title, summary, bullets):
    now = datetime.now(timezone.utc).isoformat()
    _update_doc(doc_name, {
        "status": ("string", "scraped"),
        "title": ("string", title[:200]),
        "summary": ("string", summary[:600]),
        "bullets": ("array", bullets[:3]),
        "scrapedAt": ("timestamp", now),
        "error": ("string", ""),
    })


def _mark_failed(doc_name, error):
    _update_doc(doc_name, {
        "status": ("string", "failed"),
        "error": ("string", error[:300]),
    })


def scrape_url(url):
    """Firecrawl scrape with a json format. Returns (title, summary, bullets).

    Raises RuntimeError on any failure — the caller marks the doc 'failed',
    never fakes content.
    """
    payload = {
        "url": url,
        "formats": [{
            "type": "json",
            "prompt": EXTRACT_PROMPT,
            "schema": EXTRACT_SCHEMA,
        }],
    }
    try:
        resp = firecrawl_request("POST", "/scrape", payload)
    except Exception as exc:
        raise RuntimeError(f"firecrawl: {type(exc).__name__}: {exc}") from exc
    data = (resp or {}).get("data") or {}
    extracted = data.get("json") or {}
    title = str(extracted.get("title") or "").strip()
    summary = str(extracted.get("summary") or "").strip()
    bullets = [str(b).strip() for b in (extracted.get("bullets") or [])
               if str(b).strip()][:3]
    if not title or not summary:
        raise RuntimeError("firecrawl returned no usable content")
    return title, summary, bullets


def scrape_pending(verbose=True):
    """Scrape every pending doc exactly once. Returns (scraped, failed)."""
    pending = list_pending()
    if verbose:
        print(f"[user_sources] {len(pending)} pending doc(s)")
    scraped = failed = 0
    for src in pending:
        try:
            title, summary, bullets = scrape_url(src["url"])
        except RuntimeError as exc:
            _mark_failed(src["name"], str(exc))
            failed += 1
            if verbose:
                print(f"[user_sources] FAILED {src['url']}: {exc}")
            continue
        _mark_scraped(src["name"], title, summary, bullets)
        scraped += 1
        if verbose:
            print(f"[user_sources] scraped {src['url']} -> {title[:60]}")
    return scraped, failed


# ------------------------------------------------------------ email step

def slug_for_email(email):
    slug = re.sub(r"[^a-z0-9]+", "-", email.strip().lower()).strip("-")
    return slug or "unknown"


def write_user_emails(letter, charts, edition_id, out_dir=None):
    """Render one personalized HTML email per subscriber.

    Every subscriber gets the global digest + a "From your sources" section
    containing ONLY their own scraped URLs. Returns {email: path}.
    """
    from . import emailer
    from .subscribers import list_subscribers

    out_dir = Path(out_dir) if out_dir else (
        Path(__file__).resolve().parent.parent / "data" / "emails")
    out_dir.mkdir(parents=True, exist_ok=True)
    if "digest" not in letter:
        raise RuntimeError(
            "newsletter.json is not a v4 digest edition (no 'digest' key) — "
            "run 'services.manual edition' first")
    by_email = list_scraped_by_email()
    written = {}
    for sub in list_subscribers():
        email = sub["email"]
        mine = by_email.get(email, [])
        path = out_dir / f"{slug_for_email(email)}.html"
        path.write_text(
            emailer.render_user_email(letter, charts, edition_id, email, mine),
            encoding="utf-8")
        written[email] = str(path)
    return written


def main(argv=None):
    argv = argv or []
    if not argv or argv[0] == "scrape":
        try:
            scraped, failed = scrape_pending()
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"[user_sources] done: {scraped} scraped, {failed} failed")
        return 0
    if argv[0] == "emails":
        # Standalone: load the latest edition from data/ and render one
        # personalized HTML email per subscriber. Prints "email<TAB>path"
        # lines for the scheduled send step.
        root = Path(__file__).resolve().parent.parent
        letter_path = root / "data" / "newsletter.json"
        charts_path = root / "data" / "charts.json"
        if not letter_path.exists():
            print("emails failed: data/newsletter.json not found", file=sys.stderr)
            return 1
        letter = json.loads(letter_path.read_text(encoding="utf-8"))
        charts = []
        if charts_path.exists():
            charts = json.loads(charts_path.read_text(encoding="utf-8")).get("charts", [])
        try:
            written = write_user_emails(letter, charts, letter["edition"])
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for email, path in sorted(written.items()):
            print(f"{email}\t{path}")
        print(f"[user_sources] wrote {len(written)} personalized email(s)",
              file=sys.stderr)
        return 0
    print(f"unknown command: {argv[0]} (scrape|emails)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
