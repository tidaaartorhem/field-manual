"""Tests for the field-manual pipeline: curator, writer, compiler, CLI."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services import curator, writer
from services.compiler import compile_edition, validate_manual
from services.manual import build_parser


# ---------------------------------------------------------------- fixtures

def _item(url="https://arxiv.org/abs/2601.12560", title="Agentic AI: A Survey",
          desc="A survey of LLM agent architectures and evaluation.", shelf="papers"):
    return {"url": url, "title": title, "description": desc,
            "shelf": shelf, "queries": ["agentic AI arxiv 2026"]}


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


def test_normalize_url_arxiv_version_suffix():
    assert (curator.normalize_url("https://arxiv.org/abs/2601.12560v2")
            == "https://arxiv.org/abs/2601.12560")


def test_dedupe_merges_queries():
    items = [
        _item(url="https://example.com/p?utm_source=a"),
        _item(url="https://example.com/p?fbclid=b",
              desc="A much longer description of the same page with more words.",
              ),
    ]
    items[1]["queries"] = ["other query"]
    out = curator.dedupe(items)
    assert len(out) == 1
    assert set(out[0]["queries"]) == {"agentic AI arxiv 2026", "other query"}
    assert "much longer description" in out[0]["description"]


def test_dedupe_drops_empty_urls():
    items = [_item(url=""), _item(url="   "), _item()]
    assert len(curator.dedupe(items)) == 1


# ---------------------------------------------------------------- score_item

def test_score_item_ordering_sanity():
    good = _item(title="Agentic AI: Architectures, Taxonomies, and Evaluation of LLM Agents",
                 desc="A 2026 arXiv survey of agentic AI evaluation benchmarks.")
    pr = _item(url="https://www.prweb.com/releases/agent_launch_2026",
               title="Company Announces New Product",
               desc="FOR IMMEDIATE RELEASE: a press release about a product launch.")
    assert curator.score_item(good, "papers") > curator.score_item(pr, "papers")
    assert 0.0 <= curator.score_item(pr, "papers") <= 1.0


def test_score_item_respects_shelf():
    course = _item(url="https://www.coursera.org/learn/agentic-ai",
                   title="Agentic AI Engineering Certification",
                   desc="A 2026 certification course on building LLM agents.")
    assert curator.score_item(course, "courses") > curator.score_item(course, "papers")


# ---------------------------------------------------------------- writer (templates)

def test_template_briefing_schema():
    b = writer.write_briefing({**_item(), "id": "papers-001"}, "papers")
    assert set(b) == {"lede", "what_happened", "why_it_matters", "steal_this"}
    assert all(isinstance(v, str) and v.strip() for v in b.values())
    t = writer.make_takeaways({**_item(), "id": "papers-001"}, "papers")
    assert 2 <= len(t) <= 4 and all(isinstance(x, str) and x.strip() for x in t)


def test_template_briefing_grounds_in_item():
    item = {**_item(title="Quantum Agents for Logistics"), "id": "papers-007"}
    b = writer.write_briefing(item, "papers")
    assert "Quantum Agents for Logistics" in b["lede"] or \
           "Quantum Agents for Logistics" in b["what_happened"]
    assert "arXiv" in b["lede"] or "arXiv" in b["what_happened"]


def test_template_briefing_varies_and_is_deterministic():
    b1 = writer.write_briefing({**_item(), "id": "papers-001"}, "papers")
    b2 = writer.write_briefing({**_item(), "id": "papers-002"}, "papers")
    assert b1 == writer.write_briefing({**_item(), "id": "papers-001"}, "papers")
    assert b1["lede"] != b2["lede"] or b1["why_it_matters"] != b2["why_it_matters"]


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
    item = {**_item(), "id": "papers-001"}
    briefing, takeaways, source = writer._briefing_with_source(item, "papers")
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
    item = {**_item(), "id": "papers-001"}
    briefing, takeaways, source = writer._briefing_with_source(item, "papers")
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
    item = {**_item(), "id": "papers-001"}
    briefing, takeaways, source = writer._briefing_with_source(item, "papers")
    assert source == "openai"
    assert briefing == {k: canned[k] for k in
                        ("lede", "what_happened", "why_it_matters", "steal_this")}
    assert takeaways == canned["takeaways"]
    # second item reuses the live path (exactly one mocked call each)
    item2 = {**_item(), "id": "papers-002"}
    _, _, source2 = writer._briefing_with_source(item2, "papers")
    assert source2 == "openai"
    assert writer.briefing_source_stats() == {"openai": 2, "template": 0}


# ---------------------------------------------------------------- compiler

def _curated_fixture():
    def scored(shelf, n, base=0.9):
        return [{**_item(
            url=f"https://example.com/{shelf}/{i}",
            title=f"{shelf.title()} item {i}",
            desc=f"Description of {shelf} item {i} about agents and AI.",
            shelf=shelf),
            "score": base - i * 0.01} for i in range(n)]
    return {"papers": scored("papers", 3),
            "courses": scored("courses", 2),
            "news": scored("news", 2),
            "career": scored("career", 1)}


def test_compiler_id_assignment_and_start_here():
    manual = compile_edition(_curated_fixture(), edition_date="2026-10-02")
    validate_manual(manual)  # schema-shape assertion
    ids = [i["id"] for s in manual["shelves"] for i in s["items"]]
    assert ids == ["papers-001", "papers-002", "papers-003",
                   "courses-001", "courses-002",
                   "news-001", "news-002",
                   "career-001"]
    # top 2 papers + top news + top course
    assert manual["start_here"] == ["papers-001", "papers-002",
                                   "news-001", "courses-001"]
    assert manual["stats"] == {"items": 8, "shelves": 4, "sources": 1}
    assert manual["edition"] == "2026-10-02"


def test_validate_manual_rejects_bad_url():
    manual = compile_edition(_curated_fixture())
    manual["shelves"][0]["items"][0]["url"] = "not-a-url"
    with pytest.raises(ValueError):
        validate_manual(manual)


# ---------------------------------------------------------------- CLI

def test_cli_help():
    for argv in (["--help"], ["scan", "--help"], ["build", "--help"]):
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


def test_cli_arg_parsing():
    args = build_parser().parse_args(["scan", "--limit", "3"])
    assert args.cmd == "scan" and args.limit == 3
    args = build_parser().parse_args(["build", "--max-per-shelf", "7"])
    assert args.cmd == "build" and args.max_per_shelf == 7
