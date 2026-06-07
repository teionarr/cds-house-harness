"""The query-time pipeline — ontology-first by construction.

This module encodes the call graph so the implementer fills bodies but cannot
quietly wire the RAG-reflex path (retrieve raw text -> stuff -> generate), which
would silently revert us to the search box ontology-first exists to replace:

    answer(query)
      -> resolve_question(query)            # text -> (subject, attribute, scope)
      -> ontology.query(...)                # the resolved slice (assertions + dissent)
      -> if assertions: claims_from_assertions(...) -> build_envelope(ONTOLOGY)
         else (out-of-namespace): _fallback(query) -> build_envelope(FALLBACK)

The structural guard: `claims_from_assertions` is the ONLY way an answered claim
is built on the primary path, and it stamps every claim with the source
`assertion_id` it projects. So an ontology answer literally cannot lack provenance,
and the eval can assert `answer_path == ontology` + every claim has an
`assertion_id` for in-namespace questions (a graded trap answered via `_fallback`
is a bug). Raw retrieval lives in `retrieval/strategy.py` and is reached ONLY here,
through `_fallback`, never as the default.
"""

from __future__ import annotations

from house_harness.pipeline import ontology
from house_harness.schema import (
    AnswerPath,
    Assertion,
    Claim,
    HouseHarness,
    TrustEnvelope,
)
from house_harness.synthesis.envelope import build_envelope


def resolve_question(query: str) -> tuple[str | None, str | None, str | None]:
    """Map a natural-language question to (subject, attribute, scope) over the
    controlled namespace (pipeline/attributes.py). TODO: implement (LLM-assisted
    classification into the vocab, or `new_attribute` when it's out-of-namespace)."""
    raise NotImplementedError


def _span_id(a: Assertion) -> str:
    """A citation id for a claim: the source artifact plus its character span, so
    the offline entailment judge (synthesis/verify.py) can fetch the exact text."""
    return f"{a.source.artifact_id}#{a.source.start}-{a.source.end}"


def claims_from_assertions(assertions: list[Assertion]) -> list[Claim]:
    """Project resolved assertions into Claims — the ONLY claim builder on the
    primary path. Every claim carries the `assertion_id` it came from, plus the
    assertion's source span, as_of, and scope. `verified` stays None at runtime
    (entailment is offline). This is the structural guarantee that an ontology
    answer is fully sourced (cite-or-abstain): a claim cannot exist without the
    assertion id and source span it projects.

    The claim text is a faithful, deterministic rendering of the resolved fact
    (subject · attribute [@scope] = value); the natural-language narrative is
    composed separately in `answer()` over these sourced claims."""
    claims: list[Claim] = []
    for a in assertions:
        scope = f" @{a.scope}" if a.scope else ""
        claims.append(
            Claim(
                text=f"{a.subject} · {a.attribute}{scope} = {a.value}",
                sources=[_span_id(a)],
                as_of=a.as_of,
                scope=a.scope,
                assertion_id=a.id,
                verified=None,  # entailment is offline (§4.12); never asserted at runtime
            )
        )
    return claims


def answer(query: str, harness: HouseHarness) -> TrustEnvelope:
    """Ontology-first entrypoint (serve.answer() calls this in live mode).

    Resolve the question, read the resolved ontology slice, and synthesize over it.
    Empty in-namespace result -> honest abstain (coverage gap + escalate), NOT a
    fall-back-and-guess. `_fallback` is reached only for genuinely out-of-namespace
    questions. TODO: implement the orchestration below.
    """
    subject, attribute, scope = resolve_question(query)
    assertions, dissent = ontology.query({}, subject, attribute, scope)  # store injected at wire-up
    if assertions:
        claims = claims_from_assertions(assertions)
        # coverage derived from the resolved slice (not retrieval similarity)
        return build_envelope(
            answer="",  # TODO: compose the natural-language answer from the claims
            claims=claims,
            dissent=dissent,
            coverage_gaps=[],
            coverage=1.0,
            harness=harness,
            answer_path=AnswerPath.ontology,
        )
    # No in-namespace coverage. If the question is out-of-namespace, fall back to raw
    # retrieval; otherwise abstain. TODO: distinguish the two (resolve_question result).
    return _fallback(query, harness)


def _fallback(query: str, harness: HouseHarness) -> TrustEnvelope:
    """Out-of-namespace ONLY: raw retrieval over the corpus (retrieval/strategy.py),
    flagged `answer_path=fallback` with capped confidence. Never the default; never
    reached for the graded trap classes. TODO: implement (gather -> claims w/o
    assertion_id -> build_envelope(FALLBACK))."""
    raise NotImplementedError
