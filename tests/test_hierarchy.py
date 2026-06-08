"""Deterministic multi-hop hierarchy + the contradiction/stance routing guards.

Hierarchy is graph-WALKED (not LLM-guessed): the authoritative text org chart wins,
names canonicalize, so a wrong/casing-variant edge can't mislead the answer.
"""

from __future__ import annotations

from house_harness.schema import Assertion, SourceSpan, SourceTier
from house_harness.synthesis import respond


def _edge(subject: str, manager: str, artifact: str, tier=SourceTier.official) -> Assertion:
    return Assertion(
        id=f"{subject}-{manager}-{artifact}",
        subject=subject,
        attribute="reports_to",
        value=manager,
        source=SourceSpan(artifact_id=artifact, start=0, end=10),
        reliability=tier,
    )


def test_manager_prefers_text_org_chart_over_wrong_edge():
    # A wrong edge (interview) AND the right one (text org chart) coexist; the roster wins.
    store = {
        a.id: a
        for a in [
            _edge("Maria Silva (Head of Sales, Brasil)", "Daniel Tan", "data-interviews-x-md"),
            _edge("Maria Silva", "Sofia Almeida", "data-org-chart-md"),
        ]
    }
    mgr, _ = respond._manager_of(store, "Maria Silva")
    assert mgr == "Sofia Almeida"  # the authoritative roster, not the stray mention


def test_manager_canonicalizes_casing_variants():
    # 'sofia almeida' (lowercase) resolves to the canonical name via the registry.
    store = {a.id: a for a in [_edge("Aisha Yusof", "sofia almeida", "data-org-chart-md")]}
    mgr, _ = respond._manager_of(store, "Aisha Yusof")
    assert mgr == "Sofia Almeida"


def test_multi_hop_walks_two_levels():
    store = {
        a.id: a
        for a in [
            _edge("Maria Silva", "Sofia Almeida", "data-org-chart-md"),
            _edge("Sofia Almeida", "Wei Chen", "data-org-chart-md"),
        ]
    }
    assert respond._manager_of(store, "Maria Silva")[0] == "Sofia Almeida"
    assert respond._manager_of(store, "Sofia Almeida")[0] == "Wei Chen"


def test_registry_finds_the_person_in_a_query():
    assert respond._registry().find("Who does Maria Silva's manager report to?") == "Maria Silva"
    assert respond._registry().find("what's our revenue") is None


def test_routing_regexes():
    assert respond._CONTRADICTION.search("do the sources agree, and which is authoritative?")
    assert respond._CONTRADICTION.search("the revenue figures conflict — reconcile them")
    assert respond._STANCE.search("what is the CEO's position on reporting NPS externally")
    assert not respond._STANCE.search("what was Q1 2026 revenue")
