"""Static guard for firestore.rules: user_sources must be get-by-ID only.

The public-read hole (anyone could list every submitted URL + submitter
email) was closed 2026-11-20: clients may `get` a single doc by ID (the ID
is stored in the submitter's browser localStorage) but may NOT `list` the
collection. The pipeline reads server-side via the Firestore REST API with
an OAuth token, which bypasses rules, so it is unaffected.

These tests parse the rules file — they guard the shipped text, they do
not run a rules emulator.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RULES = (ROOT / "firestore.rules").read_text(encoding="utf-8")


def _match_block(collection_path: str) -> str:
    """Return the text of the `match <collection_path> { ... }` block."""
    start = RULES.index(f"match {collection_path} {{")
    lines = RULES[start:].splitlines()
    depth = 0
    block = []
    for line in lines:
        depth += line.count("{") - line.count("}")
        block.append(line)
        if depth == 0 and len(block) > 1:
            break
    return "\n".join(block)


def test_user_sources_allows_get_by_id():
    block = _match_block("/user_sources/{docId}")
    assert re.search(r"allow\s+get\s*:\s*if\s+true\s*;", block), block


def test_user_sources_denies_list():
    block = _match_block("/user_sources/{docId}")
    assert re.search(r"allow\s+list\s*:\s*if\s+false\s*;", block), block


def test_user_sources_has_no_blanket_read():
    block = _match_block("/user_sources/{docId}")
    assert "allow read" not in block


def test_user_sources_create_still_validated_and_pending_only():
    block = _match_block("/user_sources/{docId}")
    assert "allow create:" in block
    assert "request.resource.data.status == 'pending'" in block
    assert "allow update, delete: if false;" in block


def test_subscribers_still_create_only():
    block = _match_block("/subscribers/{docId}")
    assert "allow create:" in block
    assert re.search(r"allow\s+read,\s*update,\s*delete\s*:\s*if\s+false\s*;", block)


def test_default_deny_catch_all_present():
    assert re.search(r"match\s+/\{document=\*\*\}\s*\{\s*allow\s+read,\s*write\s*:\s*if\s+false\s*;",
                     RULES)
