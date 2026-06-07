"""Harness health — what's missing or off, and the quick win to fix it.

A mirror the company can read: compare the populated harness against its
expected shape and the conflict/staleness signals already computed, then map
each gap to a templated action and (where known) an owner from the harness
authorities. Detection is deterministic — rules over the harness object + graph,
not an LLM opinion. Runs once after extraction. Upgrades the blind-spots map
(roadmap §8 #1) into something actionable.
"""

from __future__ import annotations

from house_harness.schema import (
    Dissent,
    GapKind,
    HarnessGap,
    HarnessHealth,
    HouseHarness,
)

# gap kind -> templated quick-win phrasing (deterministic; an LLM may polish copy).
ACTIONS: dict[GapKind, str] = {
    GapKind.missing_section: "Document {where} — it's absent or too thin to rely on.",
    GapKind.unowned: "Assign an owner for {where}; no authority is named.",
    GapKind.unresolved_conflict: "Pick a source of record for {where}; sources disagree.",
    GapKind.stale: "Refresh {where}; the newest source is well behind the snapshot.",
    GapKind.coverage_gap: "Capture {where}; nothing in the corpus addresses it.",
    GapKind.orphan: "Define {where}; it's referenced but never described.",
}

# Expected harness sections — emptiness here is a missing_section gap.
EXPECTED_SECTIONS = ("charter", "targets", "guardrails", "playbooks")


def assess_harness(harness: HouseHarness, dissent: list[Dissent]) -> HarnessHealth:
    """Deterministic checks over the harness + signals -> prioritized gaps.

    Checks (TODO: implement each as a rule):
      - missing/thin sections   (empty charter / targets / guardrails / playbooks)
      - unowned                 (Target/Guardrail whose authority is None)
      - unresolved_conflict     (a Dissent with no chosen source of record)
      - stale                   (as-of dates far behind the snapshot)
      - coverage_gap            (cared-about topics with no source)
      - orphan                  (graph: entity referenced but never defined)
    Each gap -> ACTIONS[kind].format(where=...) + owner from harness authorities,
    severity by kind (missing core section > unowned guardrail > stale > orphan).
    `completeness` = populated EXPECTED_SECTIONS / total.

    `stale` and `coverage_gap` are kept intentionally minimal: stale is a no-op
    (no reliable snapshot date to compare against without fabricating one), and
    coverage_gap only fires on the trivially-derivable zero-targets case.
    """

    def _populated(section: str) -> bool:
        value = getattr(harness, section)
        return bool(value.strip()) if isinstance(value, str) else bool(value)

    gaps: list[HarnessGap] = []

    # A default owner to suggest where the harness names an authority anywhere.
    default_owner = next((g.authority for g in harness.guardrails if g.authority), None)

    # 1. missing_section: an expected element is empty/thin.
    for section in EXPECTED_SECTIONS:
        if not _populated(section):
            gaps.append(
                HarnessGap(
                    kind=GapKind.missing_section,
                    where=section,
                    detail=f"{section} is empty or too thin to rely on.",
                    severity=5 if section == "charter" else 4,
                    suggested_action=ACTIONS[GapKind.missing_section].format(where=section),
                    owner=default_owner,
                )
            )

    # 2. unowned: a Guardrail with no named authority. (Targets have no authority.)
    for g in harness.guardrails:
        if g.authority is None:
            gaps.append(
                HarnessGap(
                    kind=GapKind.unowned,
                    where=g.rule,
                    detail="Guardrail has no named authority.",
                    severity=3,
                    suggested_action=ACTIONS[GapKind.unowned].format(where=g.rule),
                    owner=None,
                )
            )

    # 3. unresolved_conflict: one gap per dissent signal.
    for d in dissent:
        where = d.point if len(d.point) <= 80 else d.point[:77] + "..."
        gaps.append(
            HarnessGap(
                kind=GapKind.unresolved_conflict,
                where=where,
                detail=f"Sources disagree: {', '.join(d.sources_disagree)}.",
                severity=4,
                suggested_action=ACTIONS[GapKind.unresolved_conflict].format(where=where),
                owner=default_owner,
            )
        )

    # 4. coverage_gap: minimal — only the trivially-derivable zero-targets case.
    if not harness.targets:
        gaps.append(
            HarnessGap(
                kind=GapKind.coverage_gap,
                where="targets",
                detail="No targets are defined for the company.",
                severity=3,
                suggested_action=ACTIONS[GapKind.coverage_gap].format(where="targets"),
                owner=default_owner,
            )
        )

    # 5. orphan: a node referenced by an edge but absent from the node set.
    defined = set(harness.taxonomy.nodes)
    seen: set[str] = set()
    for edge in harness.taxonomy.edges:
        for node in (edge.src, edge.dst):
            if node not in defined and node not in seen:
                seen.add(node)
                gaps.append(
                    HarnessGap(
                        kind=GapKind.orphan,
                        where=node,
                        detail="Referenced by an edge but never defined as a node.",
                        severity=2,
                        suggested_action=ACTIONS[GapKind.orphan].format(where=node),
                        owner=default_owner,
                    )
                )

    # stale: no-op — no snapshot date to compare against without fabricating one.

    populated = sum(1 for s in EXPECTED_SECTIONS if _populated(s))
    completeness = populated / len(EXPECTED_SECTIONS)

    gaps.sort(key=lambda g: g.severity, reverse=True)

    return HarnessHealth(
        completeness=completeness,
        gaps=gaps,
        summary=f"{completeness:.0%} complete, {len(gaps)} gaps",
    )
