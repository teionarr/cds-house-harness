"""Hybrid retrieval over one owned Postgres.

Dense (pgvector) + sparse (FTS/BM25) + graph traversal, fused with RRF, reranked
(LLM reranker over top-k), recency-weighted. For contradiction questions, return
all variants of a fact, not just top-1, so conflicts stay visible to the reasoner.
"""

from __future__ import annotations

from house_harness.schema import RetrievedChunk


def retrieve(query: str, k: int = 12) -> list[RetrievedChunk]:
    """Return fused, reranked, recency-weighted hits. Raises on backend failure;
    the caller maps that to a `failed`/`degraded` envelope. TODO: implement."""
    raise NotImplementedError
