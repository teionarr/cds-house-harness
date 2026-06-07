"""The closed loop — the system learns from what it didn't know.

When an escalation is resolved or a user corrects an answer, that `Feedback`
becomes three things, which is what turns a snapshot tool into something that
compounds:
  1. a new sourced `Artifact` (the correction enters the corpus, attributed to
     whoever provided it, superseding the sources it overrides),
  2. a new gold eval case (the system is now held to the corrected answer),
  3. a re-extract trigger (the next ingestion run reconciles it into the harness).

The cheap version (built): capture + queue; the next ingestion run consumes it.
Full auto re-extract on capture rides incremental ingestion (roadmap §8 #2).
"""

from __future__ import annotations

import hashlib

from house_harness.schema import Artifact, ArtifactType, Feedback


def _feedback_id(question: str, correct_answer: str, provided_by: str) -> str:
    """Stable id = hash(question, correct_answer, provided_by) — re-capturing the
    same correction yields the same id, so re-ingestion upserts, never duplicates.
    Mirrors the ontology assertion_id hashing style."""
    key = "␟".join([question, correct_answer, provided_by])
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:16]


def capture(fb: Feedback) -> Artifact:
    """Mint a sourced Artifact from a correction so it enters the corpus, attributed
    and superseding what it overrides. Returns the new Artifact.

    A human correction is authoritative, so it's tagged source_type="board" (high
    reliability) and carries the overridden source ids in `supersedes` so
    staleness/recency prefer it. The gold-eval-case append and the re-extract
    trigger (the other two arms of the loop) are out of scope here — this is just
    the sourced-artifact creation."""
    text = f"Q: {fb.question}\nA: {fb.correct_answer}\nProvided by: {fb.provided_by}"
    metadata = {
        "source_type": "board",  # human correction is authoritative
        "provided_by": fb.provided_by,
    }
    if fb.supersedes:
        metadata["supersedes"] = ",".join(fb.supersedes)

    return Artifact(
        id=_feedback_id(fb.question, fb.correct_answer, fb.provided_by),
        source=f"feedback:{fb.provided_by}",
        type=ArtifactType.doc,
        text=text,
        metadata=metadata,
    )
