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
        "generated_at": "2026-10-02T00:00:00+00:00",
        "digest": "Test digest with <bait> & quotes. Read [Item <one>](https://example.com/1).",
        "word_count": 12, "digest_truncated": False,
        "sections": [{
            "id": "signal", "title": "The Signal", "kicker": "k",
            "items": [{
                "id": "signal-001", "title": "Item <one>",
                "url": "https://example.com/1", "source": "Example",
                "published": "2026-10-02",
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


# ------------------------------------------------- v4: digest + user sources

def _digest_item(i=1, shelf="signal", desc=None):
    return {
        "url": f"https://example.com/story-{i}",
        "title": f"Story {i}",
        "description": desc or f"This is the gist of story {i}. It says things worth knowing.",
        "shelf": shelf,
        "score": 0.9,
        "published": "2026-10-02",
        "queries": [],
    }


def _canned_digest_chat(text):
    def _chat(system, user, max_tokens):
        return {"digest": text}
    return _chat


def test_digest_word_count_guard_truncates():
    long_text = " ".join(f"Sentence {i} here." for i in range(300))  # 900 words
    digest, truncated = writer._enforce_word_limit(long_text, [], None)
    wc = len(digest.split())
    assert wc <= 700
    assert truncated is True
    assert "Trimmed" in digest


def test_digest_compression_pass_runs_once():
    long_text = " ".join(f"Sentence {i} here." for i in range(267))  # ~800 words
    short = " ".join(f"w{i}" for i in range(600))
    calls = []

    def _chat(system, user, max_tokens):
        calls.append(system)
        return {"digest": short}

    digest, truncated = writer._enforce_word_limit(long_text, [], _chat)
    assert len(digest.split()) == 600 and truncated is False and len(calls) == 1


def test_digest_rejects_invented_links():
    items = [_digest_item(1)]
    bad = {"digest": "See [Evil](https://evil.example.com/x) for details."}
    with pytest.raises(writer._LLMItemFailed):
        writer._validate_digest(bad, [it["url"] for it in items])


def test_digest_accepts_exact_links():
    items = [_digest_item(1)]
    good = {"digest": f"See [Story 1]({items[0]['url']}) for details."}
    assert writer._validate_digest(good, [it["url"] for it in items]).startswith("See")


def test_write_digest_template_fallback_within_budget():
    items = [_digest_item(i) for i in range(1, 25)]
    digest, wc, truncated = writer.write_digest([
        {**it, "gist": writer.gist(it), "source": "Example"} for it in items])
    assert wc <= 700
    assert isinstance(digest, str) and len(digest) > 0


def test_write_digest_api_path(monkeypatch):
    writer._LLM_STATE.update({"mode": "on", "probed": True, "available": True})
    items = [
        {**_digest_item(1), "gist": "Gist one.", "source": "Example"},
        {**_digest_item(2), "gist": "Gist two.", "source": "Example"},
    ]
    text = ("Intro sentence here. " +
            f"Read [Story 1]({items[0]['url']}) and [Story 2]({items[1]['url']}). " * 20)
    digest, wc, truncated = writer.write_digest(
        items, _chat_fn=_canned_digest_chat(text))
    assert wc <= 700 and truncated is False
    assert items[0]["url"] in digest and items[1]["url"] in digest


def test_compile_digest_edition_shape():
    from services.compiler import compile_digest_edition, validate_digest_edition
    curated = {
        "signal": [_digest_item(1, "signal"), _digest_item(2, "signal")],
        "tech": [_digest_item(3, "tech")],
        "startups": [],
        "podcasts": [],
    }
    letter = compile_digest_edition(curated, edition_date="2026-10-02")
    validate_digest_edition(letter)  # raises on mismatch
    assert letter["word_count"] <= 700
    assert letter["stats"]["items"] == 3
    assert {s["id"] for s in letter["sections"]} == {"signal", "tech"}
    for s in letter["sections"]:
        for it in s["items"]:
            assert it["url"].startswith("http")
            assert "briefing" not in it  # v4: no per-item briefings


def test_validate_digest_edition_rejects_long():
    from services.compiler import validate_digest_edition
    digest = " ".join(f"word{i}" for i in range(701))
    letter = {
        "edition": "2026-10-02", "window_hours": 48,
        "generated_at": "2026-10-02T00:00:00+00:00",
        "digest": digest, "word_count": 701, "digest_truncated": False,
        "sections": [{"id": "signal", "title": "The Signal", "kicker": "k",
                      "items": [{"id": "signal-001", "title": "T",
                                 "url": "https://example.com/x",
                                 "source": "Example", "published": None}]}],
        "stats": {"items": 1, "sections": 1, "sources": 1},
    }
    with pytest.raises(ValueError, match="700"):
        validate_digest_edition(letter)


def test_user_source_doc_parsing():
    from services import user_sources as us
    doc = {
        "name": "projects/x/databases/(default)/documents/user_sources/abc",
        "fields": {
            "email": {"stringValue": "A@X.com"},
            "url": {"stringValue": "https://example.com/p"},
            "title": {"stringValue": "T"},
            "summary": {"stringValue": "S"},
            "bullets": {"arrayValue": {"values": [{"stringValue": "b1"}]}},
            "status": {"stringValue": "scraped"},
            "error": {"stringValue": ""},
        },
    }
    src = us._doc_to_source(doc)
    assert src["email"] == "a@x.com"
    assert src["bullets"] == ["b1"]
    assert src["status"] == "scraped"


def test_slug_for_email():
    from services import user_sources as us
    assert us.slug_for_email("Ada@Example.com") == "ada-example-com"
    assert us.slug_for_email("a+b@x.io") == "a-b-x-io"


def _mini_letter():
    return {
        "edition": "2026-10-02", "window_hours": 48,
        "generated_at": "2026-10-02T00:00:00+00:00",
        "digest": "Short digest.", "word_count": 2, "digest_truncated": False,
        "sections": [],
        "stats": {"items": 0, "sections": 0, "sources": 0},
    }


def test_user_email_scoping(monkeypatch):
    """User A's URL must never appear in user B's email (and vice versa)."""
    from services import user_sources as us
    from services import emailer

    fake = [
        {"name": "a1", "email": "a@x.com", "url": "https://a.example/1",
         "title": "A story", "summary": "A summary.", "bullets": ["b1"],
         "status": "scraped", "error": ""},
        {"name": "b1", "email": "b@x.com", "url": "https://b.example/1",
         "title": "B story", "summary": "B summary.", "bullets": [],
         "status": "scraped", "error": ""},
        {"name": "a2", "email": "a@x.com", "url": "https://a.example/2",
         "title": "A two", "summary": "", "bullets": [],
         "status": "pending", "error": ""},
    ]
    monkeypatch.setattr(us, "list_all_sources", lambda: fake)
    grouped = us.list_scraped_by_email()
    assert set(grouped) == {"a@x.com", "b@x.com"}
    assert len(grouped["a@x.com"]) == 1  # pending doc excluded
    letter = _mini_letter()
    html_a = emailer.render_user_email(letter, [], "2026-10-02", "a@x.com",
                                       grouped["a@x.com"])
    html_b = emailer.render_user_email(letter, [], "2026-10-02", "b@x.com",
                                       grouped["b@x.com"])
    assert "https://a.example/1" in html_a
    assert "A story" in html_a
    assert "https://b.example/1" not in html_a
    assert "https://b.example/1" in html_b
    assert "https://a.example/1" not in html_b
    # Global email carries neither user's sources.
    html_g = emailer.render_email(letter, [], "2026-10-02")
    assert "a.example" not in html_g and "b.example" not in html_g


def test_md_to_email_html_escapes():
    from services import emailer
    out = emailer.md_to_email_html(
        "<script>alert(1)</script>\n\n**Bold** and [x](https://example.com)")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "<strong>Bold</strong>" in out
    assert 'href="https://example.com"' in out


# ---------------------------------------------------------------- 2026-11-17:
# template-fallback chrome stripping + Firecrawl 429 retry/backoff.
# The Nov 17 edition shipped gists that were pure site chrome
# ("Skip to content Image Credits: ... Share on FacebookShare on X ...")
# because gist() took the first sentences of raw scrape markdown.

_TC_SCRAPE = """[Skip to content](https://techcrunch.com/2026/11/16/x/#wp--skip-link--target)

![The US Department of Commerce building](https://techcrunch.com/wp-content/uploads/2026/11/us-commerce.jpg?w=564)**Image Credits:** [US Commerce Department (opens in a new window)](https://commons.wikimedia.org/wiki/File:Us_dept_of_commerce_building.jpg) / [Wikimedia Commons (opens in a new window)](http://commons.wikimedia.org/wiki/Main_Page)

[Government & Policy](https://techcrunch.com/category/government-policy/)

[Share on Facebook](https://www.facebook.com/sharer.php?u=x)[Share on X](https://twitter.com/intent/tweet?url=x)[Share on LinkedIn](https://www.linkedin.com/shareArticle?url=x)[Share on Reddit](https://www.reddit.com/submit?url=x)[Share over Email](mailto:?subject=x)[Copy Share Link](https://techcrunch.com/2026/11/16/x/)

# US tightens AI chip export controls to deter Chinese companies from accessing compute remotely

[Ram Iyer](https://techcrunch.com/author/ram-iyer/)

7:02 AM PST · November 16, 2026

[Share on Facebook](https://www.facebook.com/sharer.php?u=x)[Share on X](https://twitter.com/intent/tweet?url=x)

The Trump administration on Monday is preparing to roll out new export controls on AI chips. The rules target remote access to compute located in other countries.
"""

_ARXIV_SCRAPE = """[Skip to main content](https://arxiv.org/abs/2511.12345#content)

Search arXiv

Press Enter to search · [Advanced search](https://arxiv.org/search/advanced)

# Mathematics > Dynamical Systems

**arXiv:2511.12345** (math)

\\[Submitted on 15 Nov 2025\\]

# Title:Finiteness of measures of maximal entropy for smooth saddle surface endomorphisms

Authors: [Matéo Ghezal](https://arxiv.org/search/math?searchtype=author&query=Ghezal,+M)

View a PDF of the paper titled Finiteness of measures of maximal entropy for smooth saddle surface endomorphisms, by Mat\\'eo Ghezal

[View PDF](https://arxiv.org/pdf/2511.12345) [HTML (experimental)](https://arxiv.org/html/2511.12345v1)

> Abstract:We show that C∞ local diffeomorphisms of closed surfaces admit a finite number of ergodic measures of maximal entropy. To do this, we construct families of rectangles with a nice geometry.

|     |     |
| --- | --- |
| Comments: | 94 pages,10 figures |
| Subjects: | Dynamical Systems (math.DS) |
| Cite as: | [arXiv:2511.12345](https://arxiv.org/abs/2511.12345) \\[math.DS\\] |
"""

CHROME_STRINGS = ("Skip to content", "Skip to Main Content", "Image Credits:",
                  "Share on Facebook", "Share on X", "Share on LinkedIn",
                  "Share on Reddit", "Share over Email", "Copy Share Link",
                  "(opens in a new window)", "Search arXiv",
                  "Press Enter to search", "View PDF", "Cite as:",
                  "Submitted on", "Authors:", "Subjects:", "Comments:",
                  "נפתח בכרטיסייה חדשה")


def _assert_no_chrome(text):
    for s in CHROME_STRINGS:
        assert s not in text, f"chrome leaked: {s!r} in {text[:200]!r}"


def test_clean_text_strips_techcrunch_chrome():
    out = writer.clean_text(_TC_SCRAPE)
    _assert_no_chrome(out)
    assert "The Trump administration on Monday" in out


def test_clean_text_strips_arxiv_chrome():
    out = writer.clean_text(_ARXIV_SCRAPE)
    _assert_no_chrome(out)
    assert "We show that C∞ local diffeomorphisms" in out


def test_gist_techcrunch_starts_at_body():
    item = _item(title="US tightens AI chip export controls to deter "
                       "Chinese companies from accessing compute remotely",
                 desc="Under the interim rule, firms need licenses.")
    item["full_text"] = _TC_SCRAPE
    g = writer.gist(item)
    _assert_no_chrome(g)
    assert g.startswith("The Trump administration on Monday")
    assert "Ram Iyer" not in g


def test_gist_arxiv_returns_abstract():
    item = _item(url="https://arxiv.org/abs/2511.12345",
                 title="[2511.12345] Finiteness of measures of maximal "
                       "entropy for smooth saddle surface endomorphisms",
                 desc="arXiv abstract.")
    item["full_text"] = _ARXIV_SCRAPE
    g = writer.gist(item)
    _assert_no_chrome(g)
    assert g.startswith("We show that C∞ local diffeomorphisms")


def test_gist_falls_back_to_description_without_full_text():
    item = _item(desc="A startup launched an AI agent product for "
                      "enterprise workflows. It plugs into existing tools.")
    g = writer.gist(item)
    assert g.startswith("A startup launched an AI agent product")


def test_run_search_retries_on_429_then_succeeds(monkeypatch):
    from services import scanner
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(method, path, payload):
        calls["n"] += 1
        if calls["n"] < 3:
            raise SystemExit("Firecrawl HTTP 429: rate limit exceeded")
        return {"success": True,
                "data": {"web": [{"url": "https://example.com/a",
                                  "title": "A", "description": "d"}]}}

    monkeypatch.setattr(scanner, "_search_api", lambda: flaky)
    res = scanner.run_search("AI startup funding round announced")
    assert res["ok"] and len(res["results"]) == 1
    assert calls["n"] == 3


def test_run_search_gives_up_after_three_429s(monkeypatch):
    from services import scanner
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def always_429(method, path, payload):
        calls["n"] += 1
        raise SystemExit("Firecrawl HTTP 429: rate limit exceeded")

    monkeypatch.setattr(scanner, "_search_api", lambda: always_429)
    res = scanner.run_search("AI startup funding round announced")
    assert not res["ok"] and "429" in res["error"]
    assert calls["n"] == 3


def test_run_search_no_retry_on_auth_error(monkeypatch):
    from services import scanner
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def bad_key(method, path, payload):
        calls["n"] += 1
        raise SystemExit("Firecrawl HTTP 401: unauthorized")

    monkeypatch.setattr(scanner, "_search_api", lambda: bad_key)
    res = scanner.run_search("AI startup funding round announced")
    assert not res["ok"]
    assert calls["n"] == 1  # non-retryable: fail fast


def test_run_scrape_retries_on_429(monkeypatch):
    from services import scanner
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    class Proc:
        def __init__(self, rc, out, err=""):
            self.returncode = rc
            self.stdout = out
            self.stderr = err

    def flaky_run(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return Proc(1, "", "Firecrawl HTTP 429: rate limit exceeded")
        return Proc(0, json.dumps({"success": True,
                                   "data": {"markdown": "# Hi\n\nBody text.",
                                            "metadata": {"title": "Hi"}}}))

    monkeypatch.setattr(scanner.subprocess, "run", flaky_run)
    res = scanner.run_scrape("https://example.com/a")
    assert res["ok"] and "Body text." in res["markdown"]
    assert calls["n"] == 3


def test_discovery_skips_listing_urls(monkeypatch):
    from services import scanner
    results = [
        {"url": "https://www.ycombinator.com/companies/industry/generative-ai/san-francisco-bay-area/hiring",
         "title": "Generative AI Startups funded by Y Combinator (YC) in the ...",
         "description": "Browse 42 of the top Generative AI startups."},
        {"url": "https://www.ycombinator.com/jobs/role/ai-ml",
         "title": "Software Engineer jobs at Y Combinator startups",
         "description": "Many YC startups are hiring."},
        {"url": "https://example.com/startup-raises-seed",
         "title": "Startup raises $5M seed", "description": "A real story."},
    ]
    monkeypatch.setattr(scanner, "run_search",
                        lambda *a, **k: {"ok": True, "results": results})
    items, failures = scanner.scan_startup_discovery(limit_per_query=5,
                                                     verbose=False)
    # Same stubbed results come back for each of the 3 queries; the point is
    # no listing URL survives and the story URL does.
    assert {i["url"] for i in items} == {"https://example.com/startup-raises-seed"}
    assert failures == []
    assert scanner.is_listing_url(
        "https://www.ycombinator.com/companies/industry/generative-ai/x")
    assert scanner.is_listing_url("https://www.ycombinator.com/companies/")
    # A single company page is a story candidate, not a directory.
    assert not scanner.is_listing_url("https://www.ycombinator.com/companies/axiomat")


def test_firestore_retries_on_disconnect(monkeypatch):
    import http.client
    import io
    from services import user_sources as us
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(us, "access_token", lambda: "token")
    calls = {"n": 0}

    def flaky_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise http.client.RemoteDisconnected(
                "Remote end closed connection without response")
        return io.StringIO(json.dumps({"documents": []}))

    monkeypatch.setattr(us.urllib.request, "urlopen", flaky_urlopen)
    assert us.list_all_sources() == []
    assert calls["n"] == 2


_YNET_SCRAPE = """[Skip to content](https://www.ynetnews.com/business/article/x)

Updates Red Mail 18° Tel Aviv-Jaffa Search

Main Israel News Mideast & World News Tech & Digital

# Israeli AI cyber startup Corma hits $1 billion valuation after $125 million funding round

## $125 million funding round

Just three months after announcing a $60 million seed round, the Tel Aviv- and San Francisco-based company secures NEA-led funding as major enterprises turn to its autonomous AI systems to combat increasingly sophisticated cyber threats.

ynet Global\\ Yesterday \\ 13:05 Add a comment Print Find an error? Report us Related Topics Cybersecurity AI Startups
"""

_WSJ_SCRAPE = """[Skip to Main Content](https://www.wsj.com/pro/cybersecurity/x)

# Cyber Startup Corma Raises $125 Million for Defensive AI Agents

Agents

The year-old startup’s agents are custom-trained for defensive cybersecurity

By

[Angus Loten](https://www.wsj.com/news/author/angus-loten)

WSJ Pro

Nov. 16, 2026 7:00 am ET

Listen

(2 min)

![Alon Pluda, Corma’s chief executive, in center, with members of the startup’s founding team.](https://images.wsj.net/x.jpg)

Cybersecurity startup Corma raised $125 million to build automated agents that run on cyber-trained artificial-intelligence models.
"""

_CALCALIST_SCRAPE = """[![CTech logo](https://www.calcalistech.com/x.png)](https://www.calcalistech.com/)

- [24/7](https://www.calcalistech.com/ctechnews/category/5215)
- [Buzz](https://www.calcalistech.com/ctechnews/category/5216)
- [Startups](https://www.calcalistech.com/ctechnews/category/5214)
- [VC](https://www.calcalistech.com/ctechnews/category/5596)

# Cyber startup Corma goes from stealth to unicorn in just three months with $125 million Series A

## Founded in 2025, the Israeli startup has raised $185 million in total funding, including a $60 million Seed round announced in August.

NEA led the latest financing, which values the company at $1 billion.
"""


def test_clean_text_drops_leading_nav_list():
    out = writer.clean_text(_CALCALIST_SCRAPE)
    for nav in ("24/7", "Buzz", "Startups", "VC"):
        assert nav not in out.split("Cyber startup Corma")[0]
    assert "NEA led the latest financing" in out


def test_gist_ynet_strips_footer_furniture():
    item = _item(url="https://www.ynetnews.com/business/article/x",
                 title="Israeli AI cyber startup Corma hits $1 billion "
                       "valuation after ...",
                 desc="Ynet summary.")
    item["full_text"] = _YNET_SCRAPE
    g = writer.gist(item)
    for s in ("Add a comment", "Find an error?", "Related Topics",
              "Main Israel News", "Updates Red Mail"):
        assert s not in g, s
    assert g.startswith("$125 million funding round")


def test_gist_wsj_strips_kicker_byline_and_listen():
    item = _item(url="https://www.wsj.com/pro/cybersecurity/x",
                 title="Cyber Startup Corma Raises $125 Million for "
                       "Defensive AI ...",
                 desc="WSJ summary.")
    item["full_text"] = _WSJ_SCRAPE
    g = writer.gist(item)
    for s in ("Agents The year", "By Angus Loten", "7:00 am ET",
              "Listen (2 min)", "Skip to Main Content"):
        assert s not in g, s
    assert g.startswith("The year-old startup’s agents are custom-trained")


def test_gist_keeps_lead_starting_with_the():
    # The kicker-strip rule must never eat a real lead starting "The …".
    item = _item(title="US tightens AI chip export controls",
                 desc="Under the interim rule, firms need licenses.")
    item["full_text"] = _TC_SCRAPE
    g = writer.gist(item)
    assert g.startswith("The Trump administration on Monday")


def test_gist_truncated_title_drops_whole_headline():
    # The Calcalist item title ends "..." (feed-truncated); the gist must
    # start at the dek, not at the headline's leftover tail
    # ("months with $125 million Series A …").
    item = _item(url="https://www.calcalistech.com/ctechnews/article/x",
                 title="Cyber startup Corma goes from stealth to unicorn "
                       "in just three ...",
                 desc="Calcalist summary.")
    item["full_text"] = _CALCALIST_SCRAPE
    g = writer.gist(item)
    assert g.startswith("Founded in 2025, the Israeli startup has raised")
    assert "months with $125 million Series A" not in g
    for nav in ("24/7", "Buzz", "Startups", "VC"):
        assert nav not in g, nav


_NAV_ONLY_SCRAPE = """[![CTech logo](https://www.calcalistech.com/x.png)](https://www.calcalistech.com/)

- [24/7](https://www.calcalistech.com/ctechnews/category/5215)
- [Buzz](https://www.calcalistech.com/ctechnews/category/5216)
- [Startups](https://www.calcalistech.com/ctechnews/category/5214)

- [HR](https://www.calcalistech.com/x) - [The Next Leap](https://www.calcalistech.com/x) - [Projects](https://www.calcalistech.com/x) - Corporate About Newsletter Contact us Facebook Twitter ACCESSIBILITY
"""


def test_gist_falls_back_to_description_when_scrape_has_no_headline():
    # Degraded scrape (page shell / nav only): the snippet wins over nav.
    item = _item(url="https://www.calcalistech.com/ctechnews/article/x",
                 title="Cyber startup Corma goes from stealth to unicorn "
                       "in just three ...",
                 desc="# Cyber startup Corma goes from stealth to unicorn in just "
                      "three months with $125 million Series A\n## Founded in 2025, "
                      "the Israeli startup has raised $185 million in total funding.")
    item["full_text"] = _NAV_ONLY_SCRAPE
    g = writer.gist(item)
    assert g.startswith("Cyber startup Corma goes from stealth to unicorn")
    for nav in ("24/7", "Buzz", "The Next Leap", "ACCESSIBILITY"):
        assert nav not in g, nav
