"""Mock TrustEnvelope factory — the parallel-build unlock (from the consulting
CTO bundle, aligned to our plan: entailment is OFFLINE, so runtime claims are
`verified=None`; the degraded case blames a runtime stage, not entailment).

Tracks for serve (MCP/HTTP), synthesis, and the eval runner build against this
frozen shape while the real pipeline is written. This is a THROWAWAY stand-in:
REPLACE it, don't extend it. The real path is `synthesis/respond.answer` (reached
via `serve.answer()` in live mode); this module is reached only when
`HOUSE_HARNESS_SERVE_MODE=mock` (Phase-1 skeleton). Every mock envelope is stamped
`mode=mock` so it can't be graded or shipped. Covers all four Status values — a
serve/runner that only handles `answered` is not done.
"""

from __future__ import annotations

from house_harness.schema import (
    Claim,
    Confidence,
    Escalation,
    ServeMode,
    Status,
    TrustEnvelope,
)


def _answered() -> TrustEnvelope:
    """Grounded answer, a surfaced conflict, full provenance. `verified` is None
    at runtime — entailment is scored offline (§4.12), not per query."""
    return TrustEnvelope(
        answer=(
            "Pricing/discount approval sits with Sofia Almeida (CRO); the org chart "
            "doesn't name a pricing owner."
        ),
        status=Status.answered,
        claims=[
            Claim(
                text="Sofia Almeida (CRO) approved the discount on the Lazada SG deal.",
                sources=["interviews/customer_success/Tom_Holloway.md#L40"],
                as_of="2026-04-15",
                scope=None,
                assertion_id="a_pricing_authority",
                verified=None,
            ),
        ],
        freshness="newest supporting source: 2026-04-15",
        dissent=[],
        coverage_gaps=[],
        escalate_to=[],
        errors=[],
        confidence=Confidence.medium,
    )


def _abstain() -> TrustEnvelope:
    """No source covers it -> coverage gap + routed escalation, NOT a guess."""
    return TrustEnvelope(
        answer="No source addresses HelixPay's 2027 headcount plan.",
        status=Status.abstained,
        claims=[],
        freshness=None,
        dissent=[],
        coverage_gaps=["no source addresses 2027 headcount"],
        escalate_to=[
            Escalation(
                gap="2027 headcount", owner="Sarah Ng (VP People)", evidence=["org-chart.md"]
            )
        ],
        errors=[],
        confidence=Confidence.abstain,
    )


def _degraded() -> TrustEnvelope:
    """A runtime stage failed; answer is partial. `errors` set, status degraded,
    confidence drops — the agent routes this differently from an honest gap.
    (Runtime stages are retrieval/synthesis; entailment is offline, not here.)"""
    return TrustEnvelope(
        answer="Partial answer: the harness loaded, but graph expansion for hierarchy timed out.",
        status=Status.degraded,
        claims=[
            Claim(
                text="<PARTIAL CLAIM>",
                sources=["weekly-review-2026-04-21.md#L80"],
                as_of="2026-04-21",
                verified=None,
            )
        ],
        freshness="newest supporting source: 2026-04-21",
        dissent=[],
        coverage_gaps=[],
        escalate_to=[],
        errors=["graph.expand: timeout after 2 retries"],
        confidence=Confidence.low,
    )


def _failed() -> TrustEnvelope:
    """System could not complete — agent retries/alerts, never treats as answer."""
    return TrustEnvelope(
        answer="",
        status=Status.failed,
        claims=[],
        errors=["retrieval: datastore unreachable"],
        confidence=Confidence.abstain,
    )


_KINDS = {"answered": _answered, "abstain": _abstain, "degraded": _degraded, "failed": _failed}


def get_mock_envelope(kind: str = "answered") -> TrustEnvelope:
    """Fully-populated mock envelope, stamped `mode=mock` so it can never be
    mistaken for a real answer. kind in {answered, abstain, degraded, failed}."""
    try:
        env = _KINDS[kind]()
    except KeyError:
        raise ValueError(f"unknown kind {kind!r}; expected one of {sorted(_KINDS)}") from None
    env.mode = ServeMode.mock
    return env


def answer(query: str) -> TrustEnvelope:  # noqa: ARG001 - mock ignores the query
    """Drop-in stand-in for the real synthesis entrypoint; swap the real pipeline
    in behind the same signature."""
    return get_mock_envelope("answered")
