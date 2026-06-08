"""Tests for the deterministic harness-health assessment."""

# ruff: noqa: S101  — asserts are the test vocabulary here.
from __future__ import annotations

from house_harness.pipeline.health import assess_harness
from house_harness.schema import (
    Assertion,
    CompanyGraph,
    Dissent,
    GapKind,
    GraphEdge,
    Guardrail,
    HouseHarness,
    Playbook,
    PlaybookStep,
    RelationKind,
    SourceSpan,
    SourceTier,
    Target,
)


def _empty_harness() -> HouseHarness:
    return HouseHarness(
        company="HelixPay",
        charter="",
        taxonomy=CompanyGraph(nodes=[], edges=[]),
    )


def _full_harness(**overrides) -> HouseHarness:
    span = SourceSpan(artifact_id="a1", start=0, end=10)
    base = dict(
        company="HelixPay",
        charter="Mission: power commerce.",
        taxonomy=CompanyGraph(nodes=["ceo", "cfo"], edges=[]),
        targets=[Target(name="NPS", target="60", current="47", source=span)],
        guardrails=[Guardrail(rule="No PII in logs", authority="Security", sources=[span])],
        playbooks=[
            Playbook(
                name="Onboard",
                description="when a new merchant signs",
                steps=[PlaybookStep(text="verify KYC", source=span)],
            )
        ],
    )
    base.update(overrides)
    return HouseHarness(**base)


def test_empty_harness_low_completeness_and_missing_sections():
    health = assess_harness(_empty_harness(), [])
    assert health.completeness == 0.0
    kinds = [g.kind for g in health.gaps]
    assert kinds.count(GapKind.missing_section) == 4
    # charter missing is the most severe.
    charter_gap = next(g for g in health.gaps if g.where == "charter")
    assert charter_gap.severity == 5


def test_full_harness_high_completeness_no_missing_sections():
    health = assess_harness(_full_harness(), [])
    assert health.completeness == 1.0
    assert not any(g.kind == GapKind.missing_section for g in health.gaps)


def test_unowned_guardrail_flagged():
    span = SourceSpan(artifact_id="a1", start=0, end=10)
    harness = _full_harness(
        guardrails=[Guardrail(rule="No PII in logs", authority=None, sources=[span])]
    )
    health = assess_harness(harness, [])
    unowned = [g for g in health.gaps if g.kind == GapKind.unowned]
    assert len(unowned) == 1
    assert unowned[0].where == "No PII in logs"


def test_owner_routed_by_topic_to_a_guardrail_authority():
    # A conflict routes to the authority of an ON-TOPIC guardrail (not a blind catch-all).
    span = SourceSpan(artifact_id="a1", start=0, end=10)
    harness = _full_harness(
        guardrails=[
            Guardrail(
                rule="Revenue target revisions need CFO sign-off",
                authority="Lim (CFO)",
                sources=[span],
            )
        ],
    )
    d = Dissent(
        point="helixpay · revenue.quarter_actual @sea: disagree", sources_disagree=["a", "b"]
    )
    health = assess_harness(harness, [d])
    conflict = next(g for g in health.gaps if g.kind == GapKind.unresolved_conflict)
    assert conflict.owner == "Lim (CFO)"  # routed via the on-topic (revenue) guardrail


def test_dissent_becomes_unresolved_conflict():
    dissent = [Dissent(point="Is NPS 47 or 62?", sources_disagree=["a1", "a2"])]
    health = assess_harness(_full_harness(), dissent)
    conflicts = [g for g in health.gaps if g.kind == GapKind.unresolved_conflict]
    assert len(conflicts) == 1
    assert conflicts[0].where == "Is NPS 47 or 62?"
    assert conflicts[0].severity == 4


def test_orphan_node_in_edge_flagged():
    harness = _full_harness(
        taxonomy=CompanyGraph(
            nodes=["ceo"],
            edges=[GraphEdge(src="ceo", dst="ghost", relation=RelationKind.owns)],
        )
    )
    health = assess_harness(harness, [])
    orphans = [g for g in health.gaps if g.kind == GapKind.orphan]
    assert len(orphans) == 1
    assert orphans[0].where == "ghost"
    assert orphans[0].severity == 2


def test_gaps_sorted_by_severity_descending():
    dissent = [Dissent(point="conflict", sources_disagree=["a1", "a2"])]
    health = assess_harness(_empty_harness(), dissent)
    severities = [g.severity for g in health.gaps]
    assert severities == sorted(severities, reverse=True)


def test_summary_format():
    health = assess_harness(_full_harness(), [])
    assert "complete" in health.summary
    assert "gaps" in health.summary


def _metric(attr: str, value: str, recorded_at: str | None, scope: str | None = None) -> Assertion:
    return Assertion(
        id=f"{attr}-{recorded_at}-{scope}",
        subject="helixpay",
        attribute=attr,
        value=value,
        scope=scope,
        recorded_at=recorded_at,
        source=SourceSpan(artifact_id="a1", start=0, end=5),
        reliability=SourceTier.official,
    )


def test_stale_metric_flagged_by_transaction_time():
    # nps last RECORDED 2025-01; another metric records the 2026-04 snapshot horizon.
    store = {
        a.id: a
        for a in [
            _metric("nps", "47", "2025-01-15"),
            _metric("revenue.quarter_actual", "16M", "2026-04-20"),
        ]
    }
    health = assess_harness(_full_harness(), [], store)
    stale = [g for g in health.gaps if g.kind == GapKind.stale]
    assert len(stale) == 1
    assert "nps" in stale[0].where  # the cold metric, not the fresh one


def test_stale_is_noop_without_recorded_at():
    # Pre-bitemporal store (no recorded_at) -> staleness stays silent, as before.
    store = {a.id: a for a in [_metric("nps", "47", None)]}
    health = assess_harness(_full_harness(), [], store)
    assert not any(g.kind == GapKind.stale for g in health.gaps)
