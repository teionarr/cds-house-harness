"""Synthesis — the pure, runtime parts: claim projection + gap routing + envelope.

No LLM here. `respond.claims_from_assertions` and `envelope._route` are
deterministic; the natural-language `answer()` narrative (LLM) is tested via the
eval suite, not unit tests.
"""

from __future__ import annotations

from house_harness.schema import (
    Assertion,
    CompanyGraph,
    Confidence,
    GraphEdge,
    Guardrail,
    HouseHarness,
    RelationKind,
    SourceSpan,
    SourceTier,
    Status,
)
from house_harness.synthesis import envelope, respond


def _assertion(**kw) -> Assertion:
    base = dict(
        id="a1",
        subject="helixpay",
        attribute="nps",
        value="47",
        scope="aggregate",
        as_of="2026-04-21",
        source=SourceSpan(artifact_id="weekly-review-2026-04-21", start=120, end=160),
        reliability=SourceTier.official,
    )
    base.update(kw)
    return Assertion(**base)


def _harness(**kw) -> HouseHarness:
    base = dict(
        company="HelixPay",
        charter="Mission: agent-native payments.",
        taxonomy=CompanyGraph(nodes=[], edges=[]),
        targets=[],
        guardrails=[],
        playbooks=[],
    )
    base.update(kw)
    return HouseHarness(**base)


# ── claims_from_assertions: the cite-or-abstain guarantee ──────────────────────


def test_claims_carry_assertion_id_and_span_source():
    claims = respond.claims_from_assertions(
        [_assertion(), _assertion(id="a2", value="62", scope="sea_enterprise")]
    )
    assert len(claims) == 2
    for c in claims:
        assert c.assertion_id is not None
        assert c.sources and c.sources[0].startswith("weekly-review-2026-04-21#")  # never empty
        assert c.verified is None  # entailment is offline
    # scope + value are faithfully rendered into the claim text
    assert any("@aggregate" in c.text and "47" in c.text for c in claims)
    assert any("@sea_enterprise" in c.text and "62" in c.text for c in claims)


# ── _route: a gap finds its owner, or honestly says it can't ───────────────────


def test_route_via_guardrail_authority():
    h = _harness(
        guardrails=[
            Guardrail(
                rule="Enterprise discount approvals require the CRO.",
                authority="Sofia Almeida (CRO)",
                sources=[SourceSpan(artifact_id="org-chart.md", start=0, end=10)],
            )
        ]
    )
    esc = envelope._route("Who can approve a discount?", h)
    assert esc.owner == "Sofia Almeida (CRO)"
    assert "org-chart.md" in esc.evidence


def test_route_via_owns_edge():
    h = _harness(
        taxonomy=CompanyGraph(
            nodes=["Dana Levin", "churn"],
            edges=[GraphEdge(src="Dana Levin", dst="churn", relation=RelationKind.owns)],
        )
    )
    esc = envelope._route("What is churn for the EU segment?", h)
    assert esc.owner == "Dana Levin"


def test_route_unresolved_when_no_match():
    esc = envelope._route("something nobody owns", _harness())
    assert esc.owner == "unresolved"


# ── build_envelope: abstain on no coverage, route the gap ──────────────────────


def test_envelope_abstains_and_routes_coverage_gap():
    h = _harness(
        taxonomy=CompanyGraph(
            nodes=["Dana Levin", "churn"],
            edges=[GraphEdge(src="Dana Levin", dst="churn", relation=RelationKind.owns)],
        )
    )
    env = envelope.build_envelope(
        answer="",
        claims=[],
        dissent=[],
        coverage_gaps=["no source addresses churn for the EU segment"],
        coverage=0.0,
        harness=h,
    )
    assert env.confidence is Confidence.abstain
    assert env.status is Status.abstained
    assert env.escalate_to and env.escalate_to[0].owner == "Dana Levin"


def test_envelope_answers_with_coverage():
    env = envelope.build_envelope(
        answer="NPS is 47 aggregate.",
        claims=respond.claims_from_assertions([_assertion()]),
        dissent=[],
        coverage_gaps=[],
        coverage=1.0,
        harness=_harness(),
    )
    assert env.status is Status.answered
    assert env.confidence is Confidence.high
    assert env.freshness == "newest supporting source: 2026-04-21"
