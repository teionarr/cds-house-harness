"""Context strategy seam — the FALLBACK path for query-time context.

The primary answer source is the resolved ontology (`pipeline/ontology.py::query`,
`ContextStrategy.ontology_first`): the deep, graded questions (staleness, conflict,
alias, hierarchy, attribution) are answered from the slice resolved at ingest, not
by re-reading raw text at query time. This module covers the long tail only —
questions whose (subject, attribute) fall OUTSIDE the controlled namespace, where
raw-text reasoning legitimately wins.

WholeCorpus (corpus fits in context: load raw docs, no index) vs Hybrid (the scale
path). Both satisfy the same ContextProvider protocol and return the same
RetrievedChunk contract, so the fallback can scale without touching anything
downstream. Whole-corpus-over-raw is deliberately NOT the default: fitting in the
context budget is a capacity fact, not a correctness one — a model over 55K tokens
of contradictory text reproduces exactly the failures the ontology prevents.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from house_harness.schema import Artifact, ContextStrategy, PipelineConfig, RetrievedChunk


class ContextProvider(Protocol):
    def gather(self, query: str) -> list[RetrievedChunk]: ...


class WholeCorpus:
    """Fallback: loads the raw documents into context — global recall, no index.
    Used only when the ontology has no in-scope coverage for the question. Chart
    facts and other low-tier content stay provisional.

    Whole-corpus mode does NOT rank: it returns one chunk per artifact (everything)
    and lets the consuming LLM do relevance over the full set. `artifacts` may be
    injected (tests / a pre-loaded corpus) or left None to lazily load the corpus
    from disk on first `gather`."""

    def __init__(self, artifacts: list[Artifact] | None = None) -> None:
        self.artifacts = artifacts

    def _load(self) -> list[Artifact]:
        """Lazily load + cache the corpus once. A missing dir yields an empty list,
        not a crash (an empty fallback is an honest no-coverage signal)."""
        if self.artifacts is None:
            from house_harness.ingest.loaders import load_corpus

            corpus_dir = Path(os.environ.get("HOUSE_HARNESS_CORPUS_DIR", "data"))
            if corpus_dir.is_dir():
                files = [str(p) for p in corpus_dir.rglob("*") if p.is_file()]
                artifacts, _failures = load_corpus(files)
                self.artifacts = artifacts
            else:
                self.artifacts = []
        return self.artifacts

    def gather(self, query: str) -> list[RetrievedChunk]:
        # query is part of the ContextProvider protocol but intentionally unused:
        # whole-corpus mode returns everything (global recall) and the LLM ranks.
        _ = query
        return [
            RetrievedChunk(
                artifact_id=a.id,
                text=a.text,
                score=1.0,
                as_of=a.metadata.get("as_of"),
                retriever="whole_corpus",
            )
            for a in self._load()
        ]


def provider_for(config: PipelineConfig) -> ContextProvider:
    """Pick the FALLBACK provider the planner chose. The default query path is
    ontology-first and does not come through here; this is reached only when a
    question falls outside the controlled namespace and raw context is needed."""
    if config.context_strategy in (ContextStrategy.ontology_first, ContextStrategy.whole_corpus):
        return WholeCorpus()
    raise NotImplementedError("hybrid scale path — see retrieval/hybrid.py")
