"""Track A — the ontology spine. Pure, no LLM, no DB.

Drives `ontology.upsert/resolve/query` against the structural fixture
`tests/fixtures/assertions_resolve.json`. The fixture's `_expect` notes encode
the five mechanics the spine must get right; each test below pins one.
"""

from __future__ import annotations

import json
from pathlib import Path

from house_harness.pipeline import ontology
from house_harness.schema import Assertion, SourceTier

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "assertions_resolve.json").read_text())


def _build(d: dict) -> Assertion:
    """Build an Assertion from a fixture dict, recomputing 'RECOMPUTE' ids via the
    real stable-id function (proves re-derivation is deterministic)."""
    d = dict(d)
    if d["id"] == "RECOMPUTE":
        d["id"] = ontology.assertion_id(
            d["subject"], d["attribute"], d.get("scope"), d["source"]["artifact_id"]
        )
    return Assertion.model_validate(d)


def _group(name: str) -> list[Assertion]:
    return [_build(a) for a in FIXTURE["groups"][name]["assertions"]]


def _store(assertions: list[Assertion]) -> dict[str, Assertion]:
    store: dict[str, Assertion] = {}
    for a in assertions:
        ontology.upsert(store, a)
    return store


# ── stable id ────────────────────────────────────────────────────────────────


def test_assertion_id_is_stable_and_scope_sensitive():
    a = ontology.assertion_id("helixpay", "nps", "aggregate", "weekly-review")
    assert a == ontology.assertion_id("helixpay", "nps", "aggregate", "weekly-review")
    # scope is part of the key — different scope => different id (no false merge)
    assert a != ontology.assertion_id("helixpay", "nps", "sea_enterprise", "weekly-review")
    assert len(a) == 16


# ── T2: different scope co-exists, no dissent ──────────────────────────────────


def test_scope_coexist_both_live_no_dissent():
    store = _store(_group("scope_coexist"))
    current, dissents = ontology.resolve(store)
    assert len(current) == 2  # both NPS values are current
    assert dissents == []  # different scope => not a conflict
    assert all(a.live for a in store.values())
    assert {a.value for a in current.values()} == {"62", "47"}


# ── T3: same-scope differing values across tiers => conflict, higher tier wins ─


def test_scope_conflict_tiebreak_board_outranks_official():
    store = _store(_group("scope_conflict_tiebreak"))
    current, dissents = ontology.resolve(store)
    assert len(current) == 1  # one current value for the group
    assert len(dissents) == 1  # the disagreement is surfaced
    winner = next(iter(current.values()))
    assert winner.reliability == SourceTier.board  # 4 > 3
    assert winner.source.artifact_id == "board-update-2026-04-22"
    # cross-tier conflict: both stay LIVE (conflicts are first-class, not collapsed)
    assert sum(a.live for a in store.values()) == 2


# ── T1: same-tier recency supersession (Confluence June -> Sep), no dissent ────


def test_recency_supersession_marks_older_not_live():
    june, sep = _group("recency_supersession")  # fixture order: june then sep
    store = _store([june, sep])
    assert store[june.id].live is False  # older superseded
    assert store[sep.id].live is True
    assert june.id in store[sep.id].supersedes
    current, dissents = ontology.resolve(store)
    assert len(current) == 1
    assert next(iter(current.values())).value == "2026-09-30"
    assert dissents == []  # temporal update, not a conflict


def test_supersession_is_order_independent():
    june, sep = _group("recency_supersession")
    store = _store([sep, june])  # reversed arrival
    assert store[june.id].live is False  # the older one still loses
    assert store[sep.id].live is True
    current, _ = ontology.resolve(store)
    assert next(iter(current.values())).value == "2026-09-30"


# ── idempotent re-ingest: same (subject, attribute, scope, source) => one row ──


def test_idempotent_reingest_no_duplicate():
    a, b = _group("idempotent_reingest")  # two identical assertions
    assert a.id == b.id  # stable id collapses them
    store = _store([a, b])
    assert len(store) == 1
    current, dissents = ontology.resolve(store)
    assert len(current) == 1
    assert dissents == []


# ── T12: a chat-tier "fact" never outranks an official one ─────────────────────


def test_reliability_noise_floor_chat_never_wins():
    store = _store(_group("reliability_noise_floor"))
    current, dissents = ontology.resolve(store)
    winner = next(iter(current.values()))
    assert winner.reliability == SourceTier.official  # 3 > chat 1
    assert winner.source.artifact_id == "weekly-review-2026-04-21"
    assert len(dissents) == 1  # the disagreement is still surfaced
    # the chat assertion is never the current value
    assert all(a.reliability != SourceTier.chat for a in current.values())


# ── query(): the ontology-first read ───────────────────────────────────────────


def test_query_wildcard_scope_returns_every_segment():
    store = _store(_group("scope_coexist"))
    assertions, dissents = ontology.query(store, subject="helixpay", attribute="nps")
    assert {a.scope for a in assertions} == {"aggregate", "sea_enterprise"}
    assert dissents == []


def test_query_specific_scope_filters():
    store = _store(_group("scope_coexist"))
    assertions, _ = ontology.query(
        store, subject="helixpay", attribute="nps", scope="sea_enterprise"
    )
    assert len(assertions) == 1
    assert assertions[0].value == "62"


def test_query_empty_for_out_of_coverage_subject():
    store = _store(_group("scope_coexist"))
    assertions, _ = ontology.query(store, subject="helixpay", attribute="churn.arr_total")
    assert assertions == []  # honest coverage gap -> caller abstains, never guesses
