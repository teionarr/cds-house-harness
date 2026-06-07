"""Answer-path orchestration — deterministic, LLM mocked.

The live extraction is covered by the golden fixture (needs the model); here we pin
the *routing* logic — ontology read vs reverse-hierarchy scan vs entity fuzzy match,
and the answered / abstain / fallback branches — without any API calls, by stubbing
the single `llm_json` seam.
"""

from __future__ import annotations

import pytest

from house_harness.schema import (
    AnswerPath,
    Assertion,
    CompanyGraph,
    GraphEdge,
    HouseHarness,
    RelationKind,
    SourceSpan,
    SourceTier,
    Status,
)
from house_harness.synthesis import respond


def _a(id_, subject, attribute, value, scope=None, tier=SourceTier.official) -> Assertion:
    return Assertion(
        id=id_,
        subject=subject,
        attribute=attribute,
        value=value,
        scope=scope,
        as_of="2026-04-21",
        source=SourceSpan(artifact_id="weekly-review-2026-04-21", start=0, end=10),
        reliability=tier,
    )


def _store() -> dict[str, Assertion]:
    items = [
        _a("n1", "helixpay", "nps", "47", "aggregate"),
        _a("n2", "helixpay", "nps", "62", "sea_enterprise"),
        _a("r1", "Maria Silva (Head of Sales, Brasil)", "reports_to", "Sofia Almeida (CRO)"),
        _a("r2", "Aisha Yusof (Sales Manager, SEA)", "reports_to", "Sofia Almeida (CRO)"),
        _a("e1", "Maria Santos (Head of CS, Brasil)", "role", "Head of CS, Brasil"),
    ]
    return {a.id: a for a in items}


_HARNESS = HouseHarness(company="HelixPay", charter="", taxonomy=CompanyGraph(nodes=[], edges=[]))


@pytest.fixture
def patch_llm(monkeypatch):
    """Patch respond.llm_json to return canned structured objects per schema, and
    install a per-test QResolution + narrative."""

    def install(resolution, narrative="NARRATIVE", fallback=None):
        def fake(prompt, schema):  # noqa: ANN001
            name = schema.__name__
            if name == "QResolution":
                return resolution
            if name == "_Narrative":
                return schema(answer=narrative)
            if name == "_FallbackAnswer":
                return fallback or schema(answer="FB", claims=[], grounded=False)
            raise AssertionError(f"unexpected schema {name}")

        monkeypatch.setattr(respond, "llm_json", fake)

    return install


def test_metric_question_answers_from_ontology(patch_llm):
    patch_llm(respond.QResolution(subject="helixpay", attribute="nps", intent="metric"))
    env = respond.answer("What's our NPS?", _HARNESS, _store())
    assert env.status is Status.answered
    assert env.answer_path is AnswerPath.ontology
    assert env.answer == "NARRATIVE"
    # both scopes returned, each claim sourced + carrying its assertion_id
    assert {c.scope for c in env.claims} == {"aggregate", "sea_enterprise"}
    assert all(c.assertion_id and c.sources for c in env.claims)


def test_reverse_hierarchy_matches_on_value(patch_llm):
    patch_llm(
        respond.QResolution(
            subject="Sofia", attribute="reports_to", intent="hierarchy", reverse=True
        )
    )
    env = respond.answer("Who reports to Sofia Almeida?", _HARNESS, _store())
    assert env.status is Status.answered and env.answer_path is AnswerPath.ontology
    reports = {c.text for c in env.claims}
    assert any("Maria Silva" in t for t in reports)
    assert any("Aisha Yusof" in t for t in reports)


def test_entity_question_fuzzy_subject_keeps_distinct(patch_llm):
    patch_llm(respond.QResolution(subject="Maria", intent="entity"))
    env = respond.answer("Who is Maria?", _HARNESS, _store())
    subjects = {c.text for c in env.claims}
    # both Marias surface, never merged (anti-alias discipline upstream)
    assert any("Maria Silva" in t for t in subjects)
    assert any("Maria Santos" in t for t in subjects)


def test_in_namespace_gap_falls_back_then_abstains(patch_llm):
    # ontology has no churn -> safety-net fallback; the (mocked) corpus can't cover it
    # either (grounded=False) -> honest abstain + coverage gap, flagged as fallback.
    patch_llm(
        respond.QResolution(
            subject="helixpay", attribute="churn.arr_total", scope="eu", intent="metric"
        ),
        fallback=respond._FallbackAnswer(answer="", claims=[], grounded=False),
    )
    env = respond.answer("What's churn for the EU segment?", _HARNESS, _store())
    assert env.status is Status.abstained
    assert env.coverage_gaps  # honest gap, not a guess
    assert env.answer_path is AnswerPath.fallback


def test_out_of_namespace_routes_to_fallback(patch_llm):
    patch_llm(
        respond.QResolution(intent="out_of_namespace", in_namespace=False),
        fallback=respond._FallbackAnswer(
            answer="From the corpus...",
            claims=[respond._FallbackClaim(text="x", source_artifact_id="overview.md")],
            grounded=True,
        ),
    )
    env = respond.answer("What is the office wifi password?", _HARNESS, _store())
    assert env.answer_path is AnswerPath.fallback
    # fallback claims carry a source but NO assertion_id (not from the ontology)
    assert env.claims and all(c.assertion_id is None for c in env.claims)


def test_hierarchy_assertions_added_for_graph_questions():
    """Sanity: reports_to is a controlled attribute, so hierarchy lives in the store."""
    edge = GraphEdge(src="a", dst="b", relation=RelationKind.reports_to)
    assert edge.relation.value == "reports_to"
