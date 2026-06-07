"""Entailment verification — an OFFLINE eval-time judge, not a runtime pass.

Grounded is not correct, but a second LLM call *per claim per query* is the
biggest hidden cost multiplier in the system and a poor runtime trade. So v1
splits it:

  - RUNTIME (hot path): cite-or-abstain only. Every claim must carry a non-empty
    cited span or the answer abstains (synthesis/envelope.py). `Claim.verified`
    is left None at runtime — we don't pretend a per-claim entailment check ran.

  - OFFLINE (eval harness): this judge runs over the gold set, checking that each
    cited span actually *supports* the claim, and reports an entailment score
    (and calibration). That's where "grounded != correct" is measured and where
    regressions are caught — cheaply, in batch, not on every user query.

Promote to a runtime pass later only for high-stakes answers, behind a flag.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from house_harness.ingest.loaders import load_corpus
from house_harness.schema import Claim

# Default corpus location when neither an explicit dir nor the env var is set.
_DEFAULT_CORPUS_DIR = "data"
_CORPUS_DIR_ENV = "HOUSE_HARNESS_CORPUS_DIR"


class EntailmentVerdict(BaseModel):
    """The strict-judge output: a span supports a claim only with quoted evidence."""

    supported: bool
    evidence: str


def _parse_span(ref: str) -> tuple[str, int | None, int | None]:
    """Parse a citation id `"<artifact_id>#<start>-<end>"` into its parts.

    Tolerant by design: a missing or malformed `#start-end` yields
    `(artifact_id, None, None)` so the caller falls back to the whole artifact
    text rather than crashing on a citation it didn't expect. Pure + unit-tested.
    """
    artifact_id, sep, span = ref.partition("#")
    if not sep:
        return artifact_id, None, None
    start_str, dash, end_str = span.partition("-")
    if not dash:
        return artifact_id, None, None
    try:
        return artifact_id, int(start_str), int(end_str)
    except ValueError:
        # Span present but not two integers — treat as "whole artifact".
        return artifact_id, None, None


def _load_artifact_texts(corpus_dir: str | None) -> dict[str, str]:
    """Load the corpus once into an `artifact_id -> text` map.

    Resolves the directory from `corpus_dir`, then the env var, then the default.
    A missing directory is not an error here (the eval may run before ingestion):
    it resolves to an empty map and every claim's span text becomes "".
    """
    base = corpus_dir or os.environ.get(_CORPUS_DIR_ENV) or _DEFAULT_CORPUS_DIR
    root = Path(base)
    if not root.is_dir():
        return {}
    files = [str(p) for p in root.rglob("*") if p.is_file()]
    artifacts, _failures = load_corpus(files)
    return {a.id: a.text for a in artifacts}


def _default_judge(span_text: str, claim_text: str) -> bool:
    """The production judge: a strict, evidence-quoting LLM entailment check.

    Routed through `llm_json` (the only provider seam) so the call is validated at
    the boundary. This is the path the eval harness uses; tests inject a fake
    `_judge` instead so they stay offline.
    """
    from house_harness.config.structured import llm_json

    prompt = (
        "Does the SOURCE SPAN support the CLAIM? Answer supported=true ONLY if the "
        "span contains evidence for the claim; quote it in `evidence`. If the span "
        "is empty or unrelated, supported=false.\n\n"
        f"SOURCE SPAN:\n{span_text}\n\n"
        f"CLAIM:\n{claim_text}"
    )
    return llm_json(prompt, EntailmentVerdict).supported


def judge_entailment(
    claims: list[Claim],
    *,
    corpus_dir: str | None = None,
    _judge: Callable[[str, str], bool] | None = None,
) -> list[Claim]:
    """Eval-time: set `verified` per claim by checking the cited span supports it.

    For each claim we fetch the exact cited span text (parsed from `claim.sources[0]`,
    the `"<artifact_id>#<start>-<end>"` id minted by `respond._span_id`) and ask the
    judge whether that span supports the claim. Returns NEW Claim objects with
    `verified` set; inputs are never mutated.

    `_judge(span_text, claim_text) -> bool` is injectable so tests run offline; the
    default is the strict LLM judge. Called by the eval harness over the gold set,
    never per user query (see module docstring).
    """
    judge = _judge or _default_judge
    texts = _load_artifact_texts(corpus_dir)

    out: list[Claim] = []
    for claim in claims:
        # Cite-or-abstain guarantees a source, but stay defensive about an empty list.
        ref = claim.sources[0] if claim.sources else ""
        artifact_id, start, end = _parse_span(ref)
        text = texts.get(artifact_id, "")

        if start is None or end is None:
            # No usable span -> judge against the whole artifact text (possibly "").
            span_text = text
        else:
            # Clamp to valid bounds so a stale/oversized span can't IndexError.
            lo = max(0, min(start, len(text)))
            hi = max(lo, min(end, len(text)))
            span_text = text[lo:hi]

        verified = judge(span_text, claim.text)
        out.append(claim.model_copy(update={"verified": verified}))
    return out
