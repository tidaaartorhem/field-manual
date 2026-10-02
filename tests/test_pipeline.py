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
