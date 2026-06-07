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

from house_harness.schema import Artifact, Feedback


def capture(fb: Feedback) -> Artifact:
    """Mint a sourced Artifact from the correction, append a gold eval case to
    evals/evals.json, and flag re-extraction. Returns the new Artifact.

    TODO:
      - Artifact(source=fb.provided_by, type=doc, text=correction, metadata={kind: correction})
      - mark fb.supersedes so staleness/recency prefer this over the overridden sources
      - append {prompt: fb.question, expected_output: fb.correct_answer, sources:[new id]}
      - enqueue re-extract (next ingest run, or trigger if incremental ingestion is on)
    """
    raise NotImplementedError
