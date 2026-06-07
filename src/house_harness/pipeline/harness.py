"""The extraction engine: arbitrary documents -> House Harness.

Automated audit (entity/alias resolution, contradiction + staleness detection)
-> taxonomy + ontology graph, then distills charter, targets, and guardrails/
authorities. Emits HELIXPAY.md / <COMPANY>.md and graph.json.

CONTRACT (the spine depends on it): every assertion this emits must map its
`attribute` into the controlled namespace. Before upsert, run
`attributes.nonconformant([a.attribute for a in assertions])`; any 'violation'
is a silent synonym that disables resolve()'s grouping — drop + log it, never
store it. Out-of-vocab facts that are real get an explicit `new_attribute:<slug>`
flag for human review, not a guessed synonym. The extraction eval gates on this
(zero unflagged violations) and is regression-tested against
`tests/fixtures/extraction_golden.json`.
"""

from __future__ import annotations

from collections.abc import Iterable

from house_harness.schema import Artifact, HouseHarness


def extract_harness(company: str, artifacts: Iterable[Artifact]) -> HouseHarness:
    """Distill the defining-artifact library from a corpus. Emit assertions whose
    attributes are namespace-conformant (`attributes.nonconformant` must return
    empty), or `new_attribute:`-flagged. TODO: implement."""
    raise NotImplementedError


def render_markdown(harness: HouseHarness) -> str:
    """Render the House Harness to `<COMPANY>.md` — the AI-native artifact a person
    or agent reads to operate the company. Pure projection of the typed harness;
    every target/guardrail carries its source span (provenance is non-negotiable —
    an unsourced line should never have reached the harness)."""
    h = harness
    lines: list[str] = [f"# {h.company} — House Harness", ""]

    lines += ["## Charter", "", h.charter.strip() or "_(not yet distilled)_", ""]

    lines += ["## Targets", ""]
    if h.targets:
        lines += ["| Metric | Target | Current | Source |", "|---|---|---|---|"]
        for t in h.targets:
            current = t.current or "—"
            lines.append(f"| {t.name} | {t.target} | {current} | `{t.source.artifact_id}` |")
    else:
        lines.append("_(none captured)_")
    lines.append("")

    lines += ["## Guardrails & Authorities", ""]
    if h.guardrails:
        for g in h.guardrails:
            owner = f" — **authority:** {g.authority}" if g.authority else ""
            srcs = ", ".join(f"`{s.artifact_id}`" for s in g.sources) or "_unsourced_"
            lines.append(f"- {g.rule}{owner}  \n  _sources: {srcs}_")
    else:
        lines.append("_(none captured)_")
    lines.append("")

    lines += ["## Playbooks", ""]
    if h.playbooks:
        for p in h.playbooks:
            lines.append(f"### {p.name}")
            lines.append(f"_{p.description}_")
            for step in p.steps:
                lines.append(f"1. {step.text} (`{step.source.artifact_id}`)")
            lines.append("")
    else:
        lines += ["_(none captured)_", ""]

    nodes, edges = h.taxonomy.nodes, h.taxonomy.edges
    lines += ["## Taxonomy", "", f"{len(nodes)} entities, {len(edges)} relations.", ""]

    return "\n".join(lines).rstrip() + "\n"
