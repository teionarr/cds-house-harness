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
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def upsert(store: dict[str, Assertion], a: Assertion) -> dict[str, Assertion]:
    """Idempotent write: same ID replaces in place; a fresher/higher-tier
    assertion on the same (subject, attribute, scope) supersedes the prior one
    (prior.live = False, new.supersedes += [prior.id]). TODO: implement the
    recency+reliability comparison; key by (subject, attribute, scope)."""
    raise NotImplementedError


def resolve(store: dict[str, Assertion]) -> tuple[dict[str, Assertion], list[Dissent]]:
    """Group LIVE assertions by (subject, attribute, scope).

    - Different scope on the same attribute -> co-exist, NOT a conflict
      (NPS@SEA-enterprise=62 and NPS@aggregate=47 are both true).
    - Same (subject, attribute, scope) with differing values -> a real conflict:
      keep the highest (reliability, recency) as current and emit a `Dissent`
      naming the disagreeing sources — never silently collapse to one.
    TODO: implement grouping + the tie-break; return (current_view, dissents)."""
    raise NotImplementedError


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

    Coverage is the abstain signal: an empty result for an in-scope question is an
    honest gap (abstain + escalate), NOT a reason to fall back to raw text and guess.
    Raw retrieval (retrieval/strategy.py) is the fallback ONLY for questions whose
    (subject, attribute) lie outside the controlled namespace. TODO: implement the
    match (exact subject/attribute, scope-aware) over the resolved current view."""
    raise NotImplementedError
