"""Adaptive ingestion — profile the corpus, then pick a pipeline config.

Deterministic and explainable: measurement plus a rule table, never an LLM
choosing the architecture. Choices come from a fixed menu of known-good shapes,
and `rationale` says why, so a human can audit the decision. Keep this module
small — a profiler and a lookup. If it ever wants to be cleverer, stop.
"""

from __future__ import annotations

import datetime
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
    """Measure volume, format mix, entity/date spread, languages — deterministic,
    no LLM. The result feeds plan_pipeline's rule table."""
    arts = list(artifacts)

    # ~4 chars/token is the standard rough proxy; exact count doesn't matter here.
    token_estimate = sum(len(a.text) // 4 for a in arts)

    format_mix: dict[str, int] = {}
    for a in arts:
        key = a.metadata.get("source_type") or a.type.value
        format_mix[key] = format_mix.get(key, 0) + 1

    # HEURISTIC: each interview ≈ one person; every other artifact ≈ one entity.
    # Only consumed by plan_pipeline's `>= 5` graph gate, so only the threshold
    # crossing matters, not the precise count.
    interviews = sum(1 for a in arts if a.metadata.get("source_type") == "interview")
    others = len(arts) - interviews
    entity_estimate = interviews + others

    has_images = any(
        a.metadata.get("vision_extracted") == "true"
        or a.metadata.get("source_type") in {"image", "chart"}
        for a in arts
    )

    dates: list[datetime.date] = []
    for a in arts:
        raw = a.metadata.get("as_of")
        if not raw:
            continue
        try:
            dates.append(datetime.date.fromisoformat(raw))
        except ValueError:
            continue
    date_span_days = (max(dates) - min(dates)).days if len(dates) >= 2 else None

    languages = ["en"]
    if any(" não " in a.text or " obrigado" in a.text for a in arts):
        languages.append("pt")

    return CorpusProfile(
        token_estimate=token_estimate,
        format_mix=format_mix,
        entity_estimate=entity_estimate,
        has_images=has_images,
        date_span_days=date_span_days,
        languages=languages,
    )


def plan_pipeline(profile: CorpusProfile) -> PipelineConfig:
    """Map a profile to a config via explicit rules — the fixed menu, fully
    deterministic. This is intentionally a lookup, not reasoning. The primary query
    path is always ontology-first; the strategy here is the fallback for questions
    outside the controlled namespace."""
    strategy = (
        ContextStrategy.ontology_first  # primary answer source, any size
        if profile.token_estimate <= CONTEXT_BUDGET_TOKENS
        else ContextStrategy.hybrid  # over budget: the fallback must use an index
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
