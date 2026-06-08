"""Harness distillation + the blind-spots mirror + domain owner-routing.

These are the difference between a queryable DATA COPY and a distilled, actionable
harness — all deterministic, no LLM.
"""

from __future__ import annotations

from house_harness.pipeline import health
from house_harness.pipeline.harness import _distill_guardrails, render_markdown
from house_harness.schema import (
    Assertion,
    CompanyGraph,
    Dissent,
    GraphEdge,
    Guardrail,
    HouseHarness,
    RelationKind,
    SourceSpan,
    SourceTier,
)
from house_harness.synthesis.respond import _corpus_horizon


def _g(rule: str, authority: str | None = None) -> Guardrail:
    return Guardrail(rule=rule, authority=authority, sources=[])


def _harness(**kw) -> HouseHarness:
    base = dict(company="HelixPay", charter="m", taxonomy=CompanyGraph(nodes=[], edges=[]))
    base.update(kw)
    return HouseHarness(**base)


# ── distillation: essence, not a dump ──────────────────────────────────────────


def test_distill_dedups_caps_and_prefers_authority():
    raw = [_g(f"Filler observation number {i}.") for i in range(40)]
    raw += [_g("Enterprise discount approvals require the CRO sign-off.", "Sofia Almeida (CRO)")]
    raw += [
        _g("Enterprise discount approvals require the CRO sign off too.", None)
    ]  # near-dup, weaker
    out = _distill_guardrails(raw)
    assert len(out) <= 20  # capped — not a dump
    # the near-duplicate collapsed to the authority-bearing, policy-language one
    discount = [g for g in out if "discount" in g.rule.lower()]
    assert len(discount) == 1 and discount[0].authority == "Sofia Almeida (CRO)"


# ── domain owner-routing: not a single catch-all ───────────────────────────────


def test_owner_routing_by_domain():
    h = _harness(
        guardrails=[_g("Revenue target revisions require board sign-off.", "Board")],
        taxonomy=CompanyGraph(
            nodes=["Maria Santos", "nps"],
            edges=[GraphEdge(src="Maria Santos", dst="nps", relation=RelationKind.owns)],
        ),
    )
    # owns-edge wins for NPS; domain map covers hiring with no explicit owner
    assert health._owner_for("helixpay · nps @aggregate", h) == "Maria Santos"
    assert "People" in (health._owner_for("2026 hiring plan for engineering", h) or "")
    # different domains get different owners (not one catch-all)
    rev = health._owner_for("helixpay · revenue.quarter_actual @sea", h)
    assert rev and rev != health._owner_for("churn root cause", h)


def test_owner_for_returns_none_not_misleading_default():
    assert health._owner_for("the office wifi password", _harness()) is None


# ── the blind-spots mirror renders into <COMPANY>.md ───────────────────────────


def test_render_includes_needs_clarification_when_health_given():
    h = _harness(guardrails=[_g("Discounts need CRO sign-off.", "Sofia")])
    hh = health.assess_harness(
        h, [Dissent(point="helixpay · revenue @sea: sources disagree", sources_disagree=["a", "b"])]
    )
    md = render_markdown(h, hh)
    assert "## ⚠️ Needs Clarification" in md
    assert "unresolved_conflict" in md and "revenue" in md
    # without health, the section is absent (back-compat)
    assert "## ⚠️ Needs Clarification" not in render_markdown(h)


# ── corpus horizon is DERIVED, not hardcoded ───────────────────────────────────


def _a(as_of: str) -> Assertion:
    return Assertion(
        id=as_of,
        subject="x",
        attribute="y",
        value="v",
        as_of=as_of,
        source=SourceSpan(artifact_id="d", start=0, end=1),
        reliability=SourceTier.official,
    )


def test_corpus_horizon_is_the_data_max_year():
    store = {a.id: a for a in [_a("2025-12-31"), _a("2026-03-31")]}
    assert _corpus_horizon(store) == 2026  # not a hardcoded 2027
    assert _corpus_horizon({}) == 9999  # empty -> no horizon (never spuriously abstains)
