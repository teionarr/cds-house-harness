"""Harness health — what's missing or off, and the quick win to fix it.

A mirror the company can read: compare the populated harness against its
expected shape and the conflict/staleness signals already computed, then map
each gap to a templated action and (where known) an owner from the harness
authorities. Detection is deterministic — rules over the harness object + graph,
not an LLM opinion. Runs once after extraction. Upgrades the blind-spots map
(roadmap §8 #1) into something actionable.
"""

from __future__ import annotations

import re

from house_harness.schema import (
    Dissent,
    GapKind,
    HarnessGap,
    HarnessHealth,
    HouseHarness,
    RelationKind,
)

# Domain -> the function accountable for it, so a conflict/gap routes to the RIGHT
# owner instead of a single catch-all. Tried only after the org graph + guardrail
# authorities; a generic area beats a misleading "Board of Directors" on everything.
_DOMAIN_OWNER: list[tuple[str, str]] = [
    (r"revenue|ebitda|runway|burn|arr|margin|cash|forecast|target", "Finance (CFO)"),
    (r"\bnps\b|churn|csat|retention|loyalty", "Customer Success"),
    (r"hiring|headcount|people|recruit|backfill", "People / HR"),
    (
        r"confluence|migration|platform|reconcil|schema|attach|\btap\b|bug|engineering",
        "Engineering (CTO)",
    ),
    (
        r"pipeline|crm|discount|pricing|sales|hubspot|pipedrive|merchant|quota",
        "Revenue / Sales (CRO)",
    ),
]


def _owner_for(text: str, harness: HouseHarness) -> str | None:
    """Route a gap to an accountable owner: an explicit `owns` edge first, then a
    guardrail authority on the same topic, then the domain function — never a blind
    default. Returns None rather than a misleading owner when nothing matches."""
    t = text.lower()
    toks = set(re.findall(r"[a-z]{4,}", t))
    for e in harness.taxonomy.edges:  # explicit ownership of the area (e.g. owns nps)
        if e.relation is RelationKind.owns and re.search(rf"\b{re.escape(e.dst.lower())}\b", t):
            return e.src
    for g in harness.guardrails:
        if g.authority and toks & set(re.findall(r"[a-z]{4,}", g.rule.lower())):
            return g.authority
    for pattern, owner in _DOMAIN_OWNER:
        if re.search(pattern, t):
            return owner
    return None


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
                    owner=_owner_for(section, harness),
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

    # 3. unresolved_conflict: one gap per dissent signal. `where` = the clean
    # subject·attribute (drop the verbose "sources disagree (...)" tail).
    for d in dissent:
        where = d.point.split(":")[0].strip() or d.point[:60]
        gaps.append(
            HarnessGap(
                kind=GapKind.unresolved_conflict,
                where=where,
                detail=f"Sources disagree: {', '.join(d.sources_disagree)}.",
                severity=4,
                suggested_action=ACTIONS[GapKind.unresolved_conflict].format(where=where),
                owner=_owner_for(d.point, harness),
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
                owner=_owner_for("targets", harness),
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
                        owner=None,
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
