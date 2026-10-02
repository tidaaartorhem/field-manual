"""Tests for the field-manual pipeline: curator, writer, compiler, CLI (v2 newsletter)."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import curator, writer
from services.compiler import compile_edition, validate_newsletter
from services.curator import filter_recent, item_date
from services.manual import build_parser


# ---------------------------------------------------------------- fixtures

def _item(url="https://techcrunch.com/2026/10/02/ai-agent-launch",
          title="Startup launches agentic AI product",
          desc="A startup launched an AI agent product for enterprise workflows.",
          shelf="signal"):
    return {"url": url, "title": title, "description": desc,
            "shelf": shelf, "queries": ["agentic AI news this week"]}


@pytest.fixture(autouse=True)
def _reset_writer():
    writer.reset_run_state()
    writer.set_llm_mode("off")  # default: deterministic templates unless a test opts in
    yield
    writer.reset_run_state()
    writer.set_llm_mode("off")


# ---------------------------------------------------------------- normalize_url / dedupe

def test_normalize_url_strips_tracking_params():
    a = "https://Example.COM/some/page/?utm_source=x&fbclid=abc&id=1"
    b = "https://example.com/some/page?id=1"
    assert curator.normalize_url(a) == curator.normalize_url(b)
    assert curator.normalize_url(a) == "https://example.com/some/page?id=1"


def test_normalize_url_tracking_variants():
    base = "https://example.com/p"
    variants = [
        "https://example.com/p?utm_medium=cpc&utm_campaign=q",
        "https://example.com/p?gclid=zzz",
        "https://example.com/p/",
        "https://www.example.com/p",
        "https://EXAMPLE.com/p#section",
    ]
    for v in variants:
        assert curator.normalize_url(v) == base, v


def test_dedupe_merges_queries():
    a = _item(url="https://example.com/x?a=1&utm_source=t")
    b = _item(url="https://example.com/x?a=1")
    b["queries"] = ["other query"]
    out = curator.dedupe([a, b])
    assert len(out) == 1
    assert set(out[0]["queries"]) == {"agentic AI news this week", "other query"}


def test_dedupe_drops_empty_urls():
    assert curator.dedupe([_item(url=""), _item(url="https://example.com/ok")]) \
        and len(curator.dedupe([_item(url=""), _item(url="https://example.com/ok")])) == 1


def test_score_item_ordering_sanity():
    good = _item(title="Agentic AI product launch: autonomous agents for enterprise",
                 desc="A major 2026 launch of agentic AI tooling for developers.")
    pr = _item(url="https://www.prweb.com/releases/agent_launch_2026",
               title="Company Announces New Product",
               desc="FOR IMMEDIATE RELEASE: a press release about a product launch.")
    assert curator.score_item(good, "signal") > curator.score_item(pr, "signal")
    assert 0.0 <= curator.score_item(pr, "signal") <= 1.0


def test_score_item_respects_section():
    startup = _item(url="https://techcrunch.com/2026/10/02/startup-raises",
                    title="AI startup raises seed round",
                    desc="A startup raised funding to build AI agents.")
    assert curator.score_item(startup, "startups") > curator.score_item(startup, "tech")


# ---------------------------------------------------------------- 48h filter

def test_item_date_from_scraped_markdown():
    item = {"url": "https://acquired.fm/ep", "title": "Ep", "description": "",
            "scraped_markdown": "Published October 1, 2026\nSome notes here."}
    assert item_date(item) == "2026-10-01"


def test_filter_recent_drops_old_items():
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    old = (now - timedelta(hours=100)).strftime("%Y-%m-%d")
    new = (now - timedelta(hours=5)).strftime("%Y-%m-%d")
    items = [
        {**_item(url="https://a.com/old"), "published": old},
        {**_item(url="https://a.com/new"), "published": new},
        _item(url="https://a.com/nodate"),  # no date: kept, flagged
    ]
    kept = filter_recent(items, hours=48, now=now)
    urls = [k["url"] for k in kept]
    assert "https://a.com/old" not in urls
    assert "https://a.com/new" in urls and "https://a.com/nodate" in urls
    nodate = next(k for k in kept if k["url"] == "https://a.com/nodate")
    assert nodate["date_verified"] is False
    fresh = next(k for k in kept if k["url"] == "https://a.com/new")
    assert fresh["date_verified"] is True


def test_filter_recent_boundary_day():
    # Date-only granularity: an item dated exactly at the window edge is kept.
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    edge = (now - timedelta(hours=48)).strftime("%Y-%m-%d")
    kept = filter_recent([{**_item(), "published": edge}], hours=48, now=now)
    assert len(kept) == 1


# ---------------------------------------------------------------- writer (templates)

def test_template_briefing_schema():
    b = writer.write_briefing({**_item(), "id": "signal-001"}, "signal")
    assert set(b) == {"lede", "what_happened", "why_it_matters", "steal_this"}
    assert all(isinstance(v, str) and v.strip() for v in b.values())
    t = writer.make_takeaways({**_item(), "id": "signal-001"}, "signal")
    assert 2 <= len(t) <= 4 and all(isinstance(x, str) and x.strip() for x in t)


def test_template_briefing_grounds_in_item():
    item = {**_item(title="Quantum Agents for Logistics"), "id": "signal-007"}
    b = writer.write_briefing(item, "signal")
    assert "Quantum Agents for Logistics" in b["lede"] or \
           "Quantum Agents for Logistics" in b["what_happened"]
    assert "TechCrunch" in b["lede"] or "TechCrunch" in b["what_happened"]


def test_template_briefing_varies_and_is_deterministic():
    b1 = writer.write_briefing({**_item(), "id": "signal-001"}, "signal")
    b2 = writer.write_briefing({**_item(), "id": "signal-002"}, "signal")
    assert b1 == writer.write_briefing({**_item(), "id": "signal-001"}, "signal")
    assert b1["lede"] != b2["lede"] or b1["why_it_matters"] != b2["why_it_matters"]


def test_template_section_narrative_and_lede():
    items = [{**_item(), "id": "signal-001"}]
    n = writer.write_section_narrative("signal", "The Signal", items)
    assert n["narrative"] and n["closing_take"]
    lede = writer.write_edition_lede([("The Signal", n["closing_take"])])
    assert isinstance(lede, str) and lede.strip()


# ---------------------------------------------------------------- writer (OpenAI fallback)

class _FailingDC:
    class DynamicCredentialError(Exception):
        pass

    def dynamic_credential_entry(self, *a, **k):
        raise self.DynamicCredentialError("no such credential")

    def add_surrogate_to_request(self, *a, **k):
        raise AssertionError("should not be called")

    def read_json_response(self, *a, **k):
        raise AssertionError("should not be called")


def test_writer_falls_back_when_credential_missing(monkeypatch):
    monkeypatch.setattr(writer, "_DC", _FailingDC())
    writer.set_llm_mode("auto")
    item = {**_item(), "id": "signal-001"}
    briefing, takeaways, source = writer._briefing_with_source(item, "signal")
    assert source == "template"
    assert set(briefing) == {"lede", "what_happened", "why_it_matters", "steal_this"}
    assert 2 <= len(takeaways) <= 4
    assert writer.briefing_source_stats() == {"openai": 0, "template": 1}


def test_writer_falls_back_when_probe_item_fails(monkeypatch):
    class _DCProbeOK:
        class DynamicCredentialError(Exception):
            pass

        def dynamic_credential_entry(self, name, entry_name="access_token", **k):
            return {"surrogate": "hsurr:test", "placement": "bearer_header"}

        def add_surrogate_to_request(self, request, *a, **k):
            pass

        def read_json_response(self, response):
            return {"choices": [{"message": {"content": "not json at all"}}]}

    monkeypatch.setattr(writer, "_DC", _DCProbeOK())
    monkeypatch.setattr(writer, "_openai_chat",
                        lambda payload: {"choices": [{"message": {"content": "nope"}}]})
    writer.set_llm_mode("auto")
    item = {**_item(), "id": "signal-001"}
    briefing, takeaways, source = writer._briefing_with_source(item, "signal")
    assert source == "template"  # probe item failed -> template for it, API stays on
    assert set(briefing) == {"lede", "what_happened", "why_it_matters", "steal_this"}


def test_writer_uses_api_when_probe_succeeds(monkeypatch):
    canned = {
        "lede": "Canned lede.",
        "what_happened": "Canned what happened, grounded and true.",
        "why_it_matters": "Canned opinionated take.",
        "steal_this": "Canned concrete idea.",
        "takeaways": ["Canned one", "Canned two", "Canned three"],
    }

    class _DCOK:
        class DynamicCredentialError(Exception):
            pass

        def dynamic_credential_entry(self, name, entry_name="access_token", **k):
            return {"surrogate": "hsurr:test", "placement": "bearer_header"}

    monkeypatch.setattr(writer, "_DC", _DCOK())
    monkeypatch.setattr(writer, "_openai_chat",
                        lambda payload: {"choices": [{"message": {"content": json.dumps(canned)}}]})
    writer.set_llm_mode("auto")
    item = {**_item(), "id": "signal-001"}
    briefing, takeaways, source = writer._briefing_with_source(item, "signal")
    assert source == "openai"
    assert briefing == {k: canned[k] for k in
                        ("lede", "what_happened", "why_it_matters", "steal_this")}
    assert takeaways == canned["takeaways"]
    # second item reuses the live path (exactly one mocked call each)
    item2 = {**_item(), "id": "signal-002"}
    _, _, source2 = writer._briefing_with_source(item2, "signal")
    assert source2 == "openai"
    assert writer.briefing_source_stats() == {"openai": 2, "template": 0}


def test_section_narrative_uses_api_when_available(monkeypatch):
    canned = {"narrative": "Canned narrative weaving the items.",
              "closing_take": "Canned closing take."}

    class _DCOK:
        class DynamicCredentialError(Exception):
            pass

        def dynamic_credential_entry(self, name, entry_name="access_token", **k):
            return {"surrogate": "hsurr:test", "placement": "bearer_header"}

    monkeypatch.setattr(writer, "_DC", _DCOK())
    monkeypatch.setattr(writer, "_openai_chat",
                        lambda payload: {"choices": [{"message": {"content": json.dumps(canned)}}]})
    writer.set_llm_mode("on")
    writer._LLM_STATE["available"] = True  # as if the item pass probed already
    n = writer.write_section_narrative("signal", "The Signal",
                                       [{**_item(), "id": "signal-001"}])
    assert n == canned


def test_section_narrative_falls_back_when_api_down(monkeypatch):
    monkeypatch.setattr(writer, "_DC", _FailingDC())
    writer.set_llm_mode("auto")
    # probe happens on the item pass; simulate a failed probe:
    writer._LLM_STATE.update({"probed": True, "available": False})
    n = writer.write_section_narrative("signal", "The Signal",
                                       [{**_item(), "id": "signal-001"}])
    assert n["narrative"] and n["closing_take"]


# ---------------------------------------------------------------- compiler

def _curated_fixture():
    def scored(shelf, n, base=0.9):
        return [{**_item(
            url=f"https://example.com/{shelf}/{i}",
            title=f"{shelf.title()} item {i}",
            desc=f"Description of {shelf} item {i} about agents and AI.",
            shelf=shelf),
            "score": base - i * 0.01} for i in range(n)]
    return {"signal": scored("signal", 3),
            "tech": scored("tech", 2),
            "startups": scored("startups", 2),
            "podcasts": scored("podcasts", 1)}


def test_compiler_newsletter_shape():
    letter = compile_edition(_curated_fixture(), edition_date="2026-10-02",
                             window_hours=48)
    validate_newsletter(letter)  # schema-shape assertion
    assert letter["edition"] == "2026-10-02"
    assert letter["window_hours"] == 48
    assert letter["lede"] and isinstance(letter["lede"], str)
    ids = [s["id"] for s in letter["sections"]]
    assert ids == ["signal", "tech", "startups", "podcasts", "worth"]
    for s in letter["sections"]:
        assert s["narrative"] and s["closing_take"] and s["title"] and s["kicker"]
    item_ids = [i["id"] for s in letter["sections"] for i in s["items"]]
    assert item_ids[:3] == ["signal-001", "signal-002", "signal-003"]
    assert letter["stats"]["sections"] == 5
    assert letter["stats"]["items"] == len(item_ids)
    # Worth Your Time re-picks the top items with worth- ids
    worth = next(s for s in letter["sections"] if s["id"] == "worth")
    assert [i["id"] for i in worth["items"]] == ["worth-001", "worth-002", "worth-003"]


def test_compiler_quiet_podcast_section():
    curated = _curated_fixture()
    curated["podcasts"] = []
    letter = compile_edition(curated, edition_date="2026-10-02")
    pod = next(s for s in letter["sections"] if s["id"] == "podcasts")
    assert pod["items"] == [] and "Quiet" in pod["narrative"]


def test_validate_newsletter_rejects_bad_url():
    letter = compile_edition(_curated_fixture())
    letter["sections"][0]["items"][0]["url"] = "not-a-url"
    with pytest.raises(ValueError):
        validate_newsletter(letter)


# ---------------------------------------------------------------- CLI

def test_cli_help():
    for argv in (["--help"], ["edition", "--help"], ["scan", "--help"]):
        proc = subprocess.run(
            [sys.executable, "-m", "services.manual", *argv],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr
        assert "usage" in proc.stdout.lower()


def test_cli_requires_subcommand():
    proc = subprocess.run(
        [sys.executable, "-m", "services.manual"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0


def test_cli_edition_arg_parsing():
    args = build_parser().parse_args(["edition", "--hours", "48"])
    assert args.cmd == "edition" and args.hours == 48
    assert args.min_per_section == 3 and args.max_per_section == 6


# ---------------------------------------------------------------- v3: RSS / tiers / dedupe / funding / charts

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test Feed</title>
<item><title>AI agents take over the enterprise</title>
<link>https://example.com/agents?utm_source=rss</link>
<description><p>Agents are <b>everywhere</b> now.</description>
<pubDate>Fri, 02 Oct 2026 12:00:00 GMT</pubDate></item>
<item><title>Old news from last month</title>
<link>https://example.com/old</link>
<description>Stale.</description>
<pubDate>Tue, 01 Sep 2026 12:00:00 GMT</pubDate></item>
<item><title>No date on this one</title>
<link>https://example.com/nodate</link>
<description>Undated but fresh.</description></item>
</channel></rss>"""


def test_rss_fetch_parses_entries_and_dates():
    import feedparser
    from services import rss as rss_module
    parsed = feedparser.parse(SAMPLE_RSS)
    assert len(parsed.entries) == 3
    # exercise the entry->item path via fetch_feed with a monkeypatched parse
    orig_parse = feedparser.parse
    feedparser.parse = lambda *a, **k: orig_parse(SAMPLE_RSS)
    try:
        items, err = rss_module.fetch_feed(
            "test-feed", "https://example.com/feed", "signal", hours=48,
            now=datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc), verbose=False)
    finally:
        feedparser.parse = orig_parse
    assert err is None
    urls = [i["url"] for i in items]
    assert "https://example.com/agents?utm_source=rss" in urls  # in window
    assert "https://example.com/old" not in urls  # too old
    assert "https://example.com/nodate" in urls  # no date: kept
    ag = next(i for i in items if "agents" in i["url"])
    assert ag["published"] == "2026-10-02"
    assert ag["from_rss"] is True
    assert "<b>" not in ag["description"]  # HTML stripped


def test_rss_prefers_feed_dates_in_filter_recent():
    from services import rss as rss_module
    import feedparser
    orig_parse = feedparser.parse
    feedparser.parse = lambda *a, **k: orig_parse(SAMPLE_RSS)
    try:
        items, _ = rss_module.fetch_feed(
            "test-feed", "https://example.com/feed", "tech", hours=48,
            now=datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc), verbose=False)
    finally:
        feedparser.parse = orig_parse
    kept = filter_recent(items, hours=48,
                         now=datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc))
    assert {i["url"] for i in kept} == {
        "https://example.com/agents?utm_source=rss", "https://example.com/nodate"}


def test_source_tiers():
    assert curator.source_tier("https://arxiv.org/abs/2601.1") == 1
    assert curator.source_tier("https://www.anthropic.com/news/x") == 1
    assert curator.source_tier("https://techcrunch.com/2026/01/01/x") == 2
    assert curator.source_tier("https://www.theverge.com/x") == 2
    assert curator.source_tier("https://medium.com/@x/y") == 3
    assert curator.source_tier("https://randomblog.xyz/x") == 3


def test_tier_weighting_moves_scores():
    base = _item(url="https://techcrunch.com/x", shelf="startups")
    t1 = dict(base, url="https://ycombinator.com/x")   # tier 1, primary for startups
    t3 = dict(base, url="https://randomblog.xyz/x")    # tier 3, not primary
    s2, s1, s3 = (curator.score_item(i, "startups") for i in (base, t1, t3))
    assert s1 > s2 > s3


def test_dedupe_title_similarity():
    items = [
        {"url": "https://a.com/1", "title": "OpenAI launches new agent framework",
         "description": "x", "queries": ["a"]},
        {"url": "https://b.com/2", "title": "OpenAI Launches New Agent Framework | TechCrunch",
         "description": "y", "queries": ["b"]},
        {"url": "https://c.com/3", "title": "Completely different story here",
         "description": "z", "queries": ["c"]},
    ]
    out = curator.dedupe(items)
    assert len(out) == 2
    merged = next(o for o in out if "TechCrunch" in o["title"] or "launches" in o["title"].lower())
    assert set(merged["queries"]) == {"a", "b"}


def test_extract_funding():
    f = curator.extract_funding({
        "title": "Acme raises $50 million Series A to build agents",
        "description": "Acme raises $50 million in a Series A round.",
        "url": "https://techcrunch.com/x"})
    assert f is not None
    assert f["company"] == "Acme"
    assert f["amount_usd"] == 50_000_000
    assert f["round"] == "Series A"

    f2 = curator.extract_funding({
        "title": "BetaCo secures $120M for AI infra",
        "description": "", "url": "https://x.com/1"})
    assert f2 is not None and f2["amount_usd"] == 120_000_000

    # no amount -> None (never invent figures)
    assert curator.extract_funding({
        "title": "Acme raises a big round", "description": "",
        "url": "https://x.com/1"}) is None
    # no company -> None
    assert curator.extract_funding({
        "title": "Startup funding hits $50M record", "description": "",
        "url": "https://x.com/1"}) is None


def _chart_items():
    return {
        "signal": [
            {"title": "Agent framework ships", "description": "Agents and LLMs everywhere.",
             "url": "https://openai.com/x", "shelf": "signal", "queries": ["r"],
             "score": 0.9, "published": "2026-10-02"},
            {"title": "LLM evals update", "description": "New benchmarks for agents.",
             "url": "https://anthropic.com/y", "shelf": "signal", "queries": ["r"],
             "score": 0.8, "published": "2026-10-01"},
        ],
        "tech": [
            {"title": "GPU demand surges", "description": "Chips and datacenters.",
             "url": "https://theverge.com/a", "shelf": "tech", "queries": ["r"],
             "score": 0.7, "published": "2026-10-02"},
        ],
        "startups": [
            {"title": "Acme raises $50 million Series A",
             "description": "Acme raises $50 million Series A.",
             "url": "https://techcrunch.com/1", "shelf": "startups",
             "queries": ["r"], "score": 0.85, "published": "2026-10-02"},
            {"title": "BetaCo secures $120M",
             "description": "BetaCo secures $120M seed.",
             "url": "https://techcrunch.com/2", "shelf": "startups",
             "queries": ["r"], "score": 0.8, "published": "2026-10-01"},
            {"title": "GammaCo raises $30M Series A",
             "description": "GammaCo raises $30M Series A for agents.",
             "url": "https://techcrunch.com/3", "shelf": "startups",
             "queries": ["r"], "score": 0.75, "published": "2026-10-02"},
        ],
        "podcasts": [],
    }


def test_charts_are_honest_aggregates():
    from services import charts
    specs = charts.build_charts(_chart_items())
    by_id = {s["id"]: s for s in specs}
    funding = by_id["funding"]
    assert funding["subtitle"] == "$200M raised across 3 rounds"
    assert [d["label"] for d in funding["data"]] == ["BetaCo", "Acme", "GammaCo"]
    assert funding["data"][0]["value"] == 120.0
    sources = by_id["sources"]
    assert sources["data"][0]["label"] == "TechCrunch"
    # every value traces to a real item
    assert all(d["value"] > 0 for s in specs for d in s["data"])


def test_charts_min_data_points():
    """Fewer than 3 data points -> no chart, never a one-bar decoration."""
    from services import charts
    two_raises = {"startups": [
        {"title": "Acme raises $50M Series A", "description": "Acme raises $50M.",
         "url": "https://techcrunch.com/1"},
        {"title": "BetaCo secures $120M", "description": "BetaCo secures $120M.",
         "url": "https://techcrunch.com/2"},
    ], "tech": []}
    assert charts.funding_chart(two_raises) is None

    two_topics = {"signal": [
        {"title": "Agent news", "description": "Agents everywhere.",
         "url": "https://a.com/1"},
        {"title": "More agents", "description": "LLM agents ship.",
         "url": "https://a.com/2"},
    ]}
    assert charts.momentum_chart(two_topics) is None

    two_sources = {"signal": [
        {"title": "T1", "description": "x", "url": "https://openai.com/1"},
        {"title": "T2", "description": "x", "url": "https://openai.com/2"},
        {"title": "T3", "description": "x", "url": "https://anthropic.com/1"},
    ]}
    # only 2 distinct outlets -> dropped
    assert charts.source_mix_chart(two_sources) is None


def test_volume_chart_removed():
    """The 'edition by section' filler chart is gone for good."""
    from services import charts
    assert not hasattr(charts, "volume_chart")
    ids = [s["id"] for s in charts.build_charts(_chart_items())]
    assert "volume" not in ids


def test_charts_omit_when_no_data():
    from services import charts
    assert charts.funding_chart({"startups": [], "tech": []}) is None
    assert charts.momentum_chart({"signal": []}) is None


def test_email_html_is_email_safe():
    from services import emailer
    letter = {
        "edition": "2026-10-02", "window_hours": 48,
        "lede": "Test lede with <bait> & quotes.",
        "sections": [{
            "id": "signal", "title": "The Signal", "kicker": "k",
            "narrative": "A narrative.",
            "closing_take": "Take.",
            "items": [{
                "id": "signal-001", "title": "Item <one>",
                "url": "https://example.com/1", "source": "Example",
                "published": "2026-10-02", "shelf": "signal", "score": 0.9,
                "briefing": {"lede": "Lede & co.", "what_happened": "Happened.",
                             "why_it_matters": "Matters.", "steal_this": "Steal."},
                "takeaways": ["t1"], "queries": ["q"],
            }],
        }],
        "stats": {"items": 1, "sections": 1, "sources": 1},
    }
    charts_specs = [{
        "id": "momentum", "title": "Momentum", "subtitle": "Sub", "kind": "bar",
        "unit": "mentions", "data": [{"label": "A", "value": 2}],
        "note": "Note.",
    }]
    out = emailer.render_email(letter, charts_specs, "2026-10-02")
    assert "<table" in out and 'style="' in out
    assert "flex" not in out and "grid-template" not in out
    assert "&lt;bait&gt;" in out and "&lt;one&gt;" in out  # escaped
    assert "https://aadit-field-manual.web.app/charts/2026-10-02/momentum.png" in out
    assert "Reply to this email to unsubscribe" in out
    assert "<script" not in out


def test_subscribers_doc_mapping():
    from services.subscribers import _doc_to_subscriber
    doc = {"fields": {"name": {"stringValue": "  Ada  "},
                      "email": {"stringValue": "ADA@Example.COM "}}}
    sub = _doc_to_subscriber(doc)
    assert sub == {"name": "Ada", "email": "ADA@Example.COM"}
    assert _doc_to_subscriber({"fields": {}}) == {"name": "", "email": ""}


# ---------------------------------------------------------------- chart editor

def _editor_specs():
    return [
        {"id": "momentum", "title": "What's spiking",
         "subtitle": "Topic mentions across every story in this edition",
         "kind": "hbar", "unit": "mentions",
         "data": [{"label": "AI agents", "value": 12, "detail": "12 stories"},
                  {"label": "LLMs", "value": 6, "detail": "6 stories"},
                  {"label": "Evals", "value": 6, "detail": "6 stories"}],
         "note": "Keyword hits."},
        {"id": "sources", "title": "Where the signal came from",
         "subtitle": "7 outlets · tier 1 = primary sources",
         "kind": "hbar", "unit": "stories",
         "data": [{"label": "TechCrunch", "value": 5, "detail": "tier 2", "tier": 2},
                  {"label": "arXiv", "value": 4, "detail": "tier 1", "tier": 1},
                  {"label": "The Verge", "value": 3, "detail": "tier 2", "tier": 2}],
         "note": "Tiered."},
    ]


def test_chart_editor_off_keeps_specs():
    from services import chart_editor
    chart_editor.set_editor_mode("off")
    try:
        specs = _editor_specs()
        assert chart_editor.edit_charts(specs) == specs
    finally:
        chart_editor.set_editor_mode("auto")


def test_chart_editor_fallback_on_error():
    from services import chart_editor
    specs = _editor_specs()

    def boom(s):
        raise RuntimeError("API down")

    assert chart_editor.edit_charts(specs, _chat_fn=boom) == specs


def test_chart_editor_rejects_unknown_ids():
    from services import chart_editor

    def bad(s):
        return {"charts": [{"id": "nope", "decision": "KEEP",
                            "title": "X", "subtitle": "Y", "kind": "hbar"}]}

    specs = _editor_specs()
    assert chart_editor.edit_charts(specs, _chat_fn=bad) == specs


def test_chart_editor_applies_decisions():
    from services import chart_editor

    def fake(s):
        return {"charts": [
            {"id": "momentum", "decision": "REDESIGN",
             "title": "Agents own the conversation this week",
             "subtitle": "12 of 24 stories mention agentic AI",
             "kind": "hbar"},
            {"id": "sources", "decision": "DROP",
             "title": "x", "subtitle": "y", "kind": "hbar"},
        ]}

    out = chart_editor.edit_charts(_editor_specs(), _chat_fn=fake)
    assert [c["id"] for c in out] == ["momentum"]
    assert out[0]["title"] == "Agents own the conversation this week"
    assert out[0]["subtitle"] == "12 of 24 stories mention agentic AI"
    # data is never touched by the editor
    assert out[0]["data"] == _editor_specs()[0]["data"]


def test_chart_editor_caps_at_four():
    from services import chart_editor

    def fake(s):
        return {"charts": [
            {"id": c["id"], "decision": "KEEP", "title": c["title"],
             "subtitle": c["subtitle"], "kind": c["kind"]}
            for c in s
        ]}

    specs = _editor_specs() + [
        {"id": f"extra-{i}", "title": f"Extra {i}", "subtitle": "Sub",
         "kind": "bar", "unit": "x",
         "data": [{"label": "a", "value": 1}, {"label": "b", "value": 2},
                  {"label": "c", "value": 3}],
         "note": ""}
        for i in range(4)
    ]
    out = chart_editor.edit_charts(specs, _chat_fn=fake)
    assert len(out) == 4


# ---------------------------------------------------------------- PNG layout

def test_render_header_no_overlap():
    """Title and subtitle can never collide, however long the title."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from services import charts

    fig = plt.figure(figsize=(7.2, 4.2), dpi=100)
    spec = {
        "title": ("Agents dominate the conversation this week and the "
                  "momentum keeps building across every section"),
        "subtitle": "Topic mentions across every story in this 48-hour edition",
    }
    t, s, header_bottom = charts._draw_header(fig, spec)
    # Place the axes exactly the way render_png does.
    axes_top = header_bottom - 0.03
    ax = fig.add_axes([0.30, 0.05, 0.66, axes_top - 0.05])
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    tb = t.get_window_extent(renderer=renderer)
    sb = s.get_window_extent(renderer=renderer)
    ab = ax.get_window_extent(renderer=renderer)
    assert tb.y0 >= sb.y1, "title overlaps subtitle"
    assert sb.y0 >= ab.y1, "subtitle overlaps the chart area"
    plt.close(fig)


def test_render_png_writes_file(tmp_path):
    from services import charts
    spec = _editor_specs()[0]
    out = charts.render_png(spec, tmp_path / "momentum.png")
    assert out.exists() and out.stat().st_size > 10_000
