"""The ontology spine — assertions, not settled values.

Every extracted fact is an `Assertion` (sourced, dated, scoped). This module is
the deterministic machinery around them: stable IDs (so re-ingestion upserts
instead of duplicating), a source-reliability table, idempotent upsert with
supersession, and scope-aware conflict resolution. The LLM's job is to *emit*
assertions during extraction (`pipeline/harness.py`); deciding which is current
and which conflict is rules, not an opinion.

Store model (resolves the dict-vs-SQLite question — they are NOT in conflict):
- **Persistence of record = SQLite** (`DATABASE_URL`, one row per `assertion_id`).
  It's what survives the ingestion↔query split, makes re-ingest idempotent, and
  lets the service answer without re-reading the corpus. The documented scale path
  (hybrid/pgvector) swaps only this layer.
- **`store: dict[str, Assertion]`** in these signatures is the in-memory *working
  view* (keyed by `assertion_id`) that a resolve/query pass operates over, loaded
  from SQLite. Keeping these functions pure over a plain mapping is deliberate: it
  makes the spine (Track A) unit-testable against fixtures with NO database. The
  thin persistence layer (load at boot / save on upsert) is the only SQLite-aware
  code; the resolution logic never touches the DB.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

from house_harness.schema import ArtifactType, Assertion, Dissent, SourceTier

# Source-type -> reliability tier. A board email outweighs a Slack joke.
RELIABILITY: dict[ArtifactType | str, SourceTier] = {
    "pdf_financial": SourceTier.filing,
    "board": SourceTier.board,
    "email": SourceTier.board,
    "all_hands": SourceTier.official,
    "review": SourceTier.official,
    "dashboard": SourceTier.official,
    "interview": SourceTier.interview,
    "chat": SourceTier.chat,
}


def assertion_id(subject: str, attribute: str, scope: str | None, source: str) -> str:
    """Stable ID = hash(subject, attribute, scope, source). Re-deriving the same
    fact from the same source yields the same ID -> upsert, never a duplicate."""
    key = "\u241f".join([subject, attribute, scope or "", source])
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:16]


def _group_key(a: Assertion) -> tuple[str, str, str | None]:
    return (a.subject, a.attribute, a.scope)


def _rank(a: Assertion) -> tuple[int, str]:
    """Resolution order: higher reliability first, then more recent. A missing
    `as_of` sorts oldest. ISO date strings compare correctly lexicographically."""
    return (int(a.reliability), a.as_of or "")


def upsert(store: dict[str, Assertion], a: Assertion) -> dict[str, Assertion]:
    """Idempotent write with same-tier recency supersession.

    - **Idempotent:** the assertion is keyed by its stable `id`
      (`assertion_id(subject, attribute, scope, source)`), so re-deriving the same
      fact from the same source replaces in place — never a duplicate.
    - **Supersession (a temporal update, NOT a standing conflict):** when the new
      assertion shares (subject, attribute, scope) and *reliability tier* with an
      existing live one but carries a different value, the older `as_of` loses —
      its `live` flips to False and the newer one's `supersedes` records it
      (Confluence June -> Sep). Order-independent: an out-of-order older arrival is
      itself marked superseded on the way in.
    - **Cross-tier disagreements are left LIVE on purpose** — they are real
      conflicts (board vs weekly, official vs chat) that `resolve()` surfaces as
      `Dissent` with the highest tier winning, rather than silently collapsing.
    """
    store[a.id] = a  # idempotent replace by stable id
    for other_id, b in list(store.items()):
        if other_id == a.id or not b.live:
            continue
        if _group_key(b) != _group_key(a) or b.reliability != a.reliability:
            continue  # cross-tier/other group -> a resolve() conflict, not supersession
        if b.value == a.value:
            continue  # corroborating duplicate from another source — both stay live
        if _rank(a) > _rank(b):  # a is fresher -> a supersedes b
            b.live = False
            if b.id not in a.supersedes:
                a.supersedes.append(b.id)
        elif _rank(a) < _rank(b):  # a arrived out of order, already stale
            a.live = False
            if a.id not in b.supersedes:
                b.supersedes.append(a.id)
        # equal rank + differing value -> genuine same-tier conflict: leave both live
    return store


# Dissent is meaningful for single-valued FACTS (a metric/date/system with two
# conflicting values is a real contradiction). It is just NOISE for free-text or
# multi-valued DESCRIPTIVE/relational attributes — a person legitimately has several
# role phrasings, owns several areas, has a solid + a dotted manager. Suppressing
# dissent there (a winner is still chosen) keeps contradiction-detection sharp on the
# numbers that matter. `new_attribute:` slugs are uncurated, so they never dissent.
_DESCRIPTIVE_ATTRS = frozenset(
    {
        "role",
        "location",
        "owns",
        "reports_to",
        "dotted_reports_to",
        "account.status",
        "account.churn_reason",
        "bug.status",
        "bug.impact",
        "hiring.status",
        "confluence.status",
        "ebitda_status",
    }
)


def _dissent_meaningful(attribute: str) -> bool:
    return attribute not in _DESCRIPTIVE_ATTRS and not attribute.startswith("new_attribute:")


def _resolve_assertions(assertions: list[Assertion]) -> tuple[list[Assertion], list[Dissent]]:
    """Project a set of LIVE assertions to one current value per
    (subject, attribute, scope) group, emitting a `Dissent` for any group of
    single-valued FACTS whose members disagree. Conflicts are surfaced, never
    collapsed; descriptive/relational attributes pick a winner without noise-dissent.
    Shared by `resolve` (whole store) and `query` (a filtered slice)."""
    groups: dict[tuple[str, str, str | None], list[Assertion]] = defaultdict(list)
    for a in assertions:
        if a.live:
            groups[_group_key(a)].append(a)
    winners: list[Assertion] = []
    dissents: list[Dissent] = []
    for (subject, attribute, scope), members in groups.items():
        winner = max(members, key=_rank)
        winners.append(winner)
        if _dissent_meaningful(attribute) and len({m.value for m in members}) > 1:
            where = f"{subject} · {attribute}" + (f" @{scope}" if scope else "")
            point = (
                f"{where}: sources disagree (current: {winner.value!r} from "
                f"{winner.source.artifact_id}, tier {winner.reliability.name})"
            )
            dissents.append(
                Dissent(point=point, sources_disagree=[m.source.artifact_id for m in members])
            )
    return winners, dissents


def resolve(store: dict[str, Assertion]) -> tuple[dict[str, Assertion], list[Dissent]]:
    """Group LIVE assertions by (subject, attribute, scope) into the current view.

    - Different scope on the same attribute -> co-exist, NOT a conflict
      (NPS@SEA-enterprise=62 and NPS@aggregate=47 are both true, no dissent).
    - Same (subject, attribute, scope) with differing values -> a real conflict:
      the highest (reliability, recency) is current and a `Dissent` names the
      disagreeing sources — never silently collapsed to one.

    Returns (current_view keyed by the winning assertion's id, dissents). Pure: it
    reads the store and does not mutate it (supersession already happened at upsert)."""
    winners, dissents = _resolve_assertions(list(store.values()))
    return {w.id: w for w in winners}, dissents


def query(
    store: dict[str, Assertion],
    subject: str | None = None,
    attribute: str | None = None,
    scope: str | None = None,
) -> tuple[list[Assertion], list[Dissent]]:
    """The QUERY-TIME READ and the primary answer source (ContextStrategy.ontology_first).

    Returns the LIVE resolved assertions matching the question's
    (subject, attribute, scope) — each already sourced, dated, scoped — plus any
    `Dissent` on them. Synthesis builds `Claim`s directly from these, so the model
    reasons over a small, already-resolved slice instead of the raw corpus. This is
    why staleness/conflict/alias/hierarchy stay correct at query time: they were
    decided here at ingest, deterministically, not re-litigated by a model staring
    at 55K tokens of contradictory text.

    `scope=None` is the wildcard: it returns one current value per scope for the
    (subject, attribute) — so "What's our NPS?" yields aggregate AND each segment,
    each carrying its own scope, rather than forcing a single number.

    Coverage is the abstain signal: an empty result for an in-scope question is an
    honest gap (abstain + escalate), NOT a reason to fall back to raw text and guess.
    Raw retrieval (retrieval/strategy.py) is the fallback ONLY for questions whose
    (subject, attribute) lie outside the controlled namespace."""
    matched = [
        a
        for a in store.values()
        if a.live
        and (subject is None or a.subject == subject)
        and (attribute is None or a.attribute == attribute)
        and (scope is None or a.scope == scope)
    ]
    return _resolve_assertions(matched)
