"""Adaptive ingestion — profile the corpus, then pick a pipeline config.

Deterministic and explainable: measurement plus a rule table, never an LLM
choosing the architecture. Choices come from a fixed menu of known-good shapes,
and `rationale` says why, so a human can audit the decision. Keep this module
small — a profiler and a lookup. If it ever wants to be cleverer, stop.
"""

from __future__ import annotations

from collections.abc import Iterable

from house_harness.schema import (
    Artifact,
    ContextStrategy,
    CorpusProfile,
    PipelineConfig,
)

# Above this estimate, whole-corpus no longer fits comfortably -> hybrid index.
CONTEXT_BUDGET_TOKENS = 120_000

# MEASURED on the real corpus (2026-06-07): md+html ≈ 54.5K tokens, +2 PDFs +4
# charts — well under budget. The query path is ONTOLOGY-FIRST regardless of size:
# answers come from the resolved ontology slice, so per-query cost is O(slice), not
# O(corpus), and stays flat as a live corpus grows. The token budget only decides
# the FALLBACK for out-of-ontology questions: in-budget -> raw whole_corpus,
# over-budget -> hybrid index. profiler/plan_pipeline stay types + the documented
# rule so the moving-target case is a config flip, not a rewrite.


def profile_corpus(artifacts: Iterable[Artifact]) -> CorpusProfile:
    """Measure volume, format mix, entity/date spread, languages. TODO: implement
    (token count, type histogram, distinct-entity estimate, min/max as-of dates)."""
    raise NotImplementedError


def plan_pipeline(profile: CorpusProfile) -> PipelineConfig:
    """Map a profile to a config via explicit rules — the fixed menu, fully
    deterministic. This is intentionally a lookup, not reasoning. The primary query
    path is always ontology-first; the strategy here is the fallback for questions
    outside the controlled namespace."""
    strategy = (
        ContextStrategy.ontology_first  # primary answer source, any size
        if profile.token_estimate <= CONTEXT_BUDGET_TOKENS
        else ContextStrategy.hybrid     # over budget: the fallback must use an index
    )
    return PipelineConfig(
        context_strategy=strategy,
        vision_extraction=profile.has_images,
        build_graph=profile.entity_estimate >= 5,
        rerank=strategy is ContextStrategy.hybrid,
        rationale=(
            f"{profile.token_estimate} tok across {sum(profile.format_mix.values())} files; "
            f"images={profile.has_images}; entities~{profile.entity_estimate} "
            f"-> ontology-first (fallback {strategy.value})"
            + (", vision extraction on" if profile.has_images else "")
        ),
    )
