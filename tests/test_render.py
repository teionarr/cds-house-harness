"""The <COMPANY>.md renderer — a pure projection of the typed harness."""

from __future__ import annotations

from house_harness.pipeline.harness import render_markdown
from house_harness.schema import (
    CompanyGraph,
    GraphEdge,
    Guardrail,
    HouseHarness,
    RelationKind,
    SourceSpan,
    Target,
)


def _harness() -> HouseHarness:
    return HouseHarness(
        company="HelixPay",
        charter="Mission: agent-native payments for SEA + Brasil.",
        taxonomy=CompanyGraph(
            nodes=["Sofia Almeida", "Sales"],
            edges=[GraphEdge(src="Sofia Almeida", dst="Sales", relation=RelationKind.owns)],
        ),
        targets=[
            Target(
                name="Q1 revenue",
                target="SGD 16M",
                current="SGD 14.2M",
                source=SourceSpan(artifact_id="q1-2026-results.pdf", start=0, end=10),
            )
        ],
        guardrails=[
            Guardrail(
                rule="Enterprise discounts require CRO approval.",
                authority="Sofia Almeida (CRO)",
                sources=[SourceSpan(artifact_id="org-chart.md", start=0, end=5)],
            )
        ],
    )


def test_render_includes_all_sections():
    md = render_markdown(_harness())
    assert md.startswith("# HelixPay — House Harness")
    assert "## Charter" in md and "agent-native payments" in md
    assert "## Targets" in md and "Q1 revenue" in md and "SGD 14.2M" in md
    assert "q1-2026-results.pdf" in md  # provenance rendered
    assert "## Guardrails & Authorities" in md
    assert "Sofia Almeida (CRO)" in md and "org-chart.md" in md
    assert "## Taxonomy" in md and "2 entities, 1 relations" in md


def test_render_empty_harness_is_honest():
    md = render_markdown(
        HouseHarness(company="Acme", charter="", taxonomy=CompanyGraph(nodes=[], edges=[]))
    )
    assert "# Acme — House Harness" in md
    assert "_(not yet distilled)_" in md  # empty charter is flagged, not faked
    assert "_(none captured)_" in md
