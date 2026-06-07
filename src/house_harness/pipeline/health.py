"""Harness health — what's missing or off, and the quick win to fix it.

A mirror the company can read: compare the populated harness against its
expected shape and the conflict/staleness signals already computed, then map
each gap to a templated action and (where known) an owner from the harness
authorities. Detection is deterministic — rules over the harness object + graph,
not an LLM opinion. Runs once after extraction. Upgrades the blind-spots map
(roadmap §8 #1) into something actionable.
"""

from __future__ import annotations

from house_harness.schema import Dissent, GapKind, HarnessHealth, HouseHarness

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
    """
    raise NotImplementedError
