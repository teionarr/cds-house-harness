"""WholeCorpus fallback provider — whole-corpus, no ranking.

Pins the contract: one RetrievedChunk per artifact, retriever="whole_corpus",
artifact_ids/text carried through; and that the planner's provider_for returns a
WholeCorpus for the ontology_first / whole_corpus strategies.
"""

from __future__ import annotations

from house_harness.retrieval.strategy import WholeCorpus, provider_for
from house_harness.schema import (
    Artifact,
    ArtifactType,
    ContextStrategy,
    PipelineConfig,
)


def _artifact(id_: str, text: str, as_of: str | None = None) -> Artifact:
    metadata = {"as_of": as_of} if as_of else {}
    return Artifact(id=id_, source="test", type=ArtifactType.doc, text=text, metadata=metadata)


def test_gather_returns_one_chunk_per_artifact():
    a1 = _artifact("a1", "first text", as_of="2026-01-01")
    a2 = _artifact("a2", "second text")
    chunks = WholeCorpus([a1, a2]).gather("anything")

    assert len(chunks) == 2
    assert [c.artifact_id for c in chunks] == ["a1", "a2"]
    assert [c.text for c in chunks] == ["first text", "second text"]
    assert all(c.retriever == "whole_corpus" for c in chunks)
    assert all(c.score == 1.0 for c in chunks)
    assert chunks[0].as_of == "2026-01-01"
    assert chunks[1].as_of is None


def test_provider_for_returns_whole_corpus():
    for strategy in (ContextStrategy.ontology_first, ContextStrategy.whole_corpus):
        config = PipelineConfig(context_strategy=strategy)
        assert isinstance(provider_for(config), WholeCorpus)
