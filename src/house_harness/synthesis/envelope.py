"""Build the trust envelope for an answer.

Answers are synthesized from the resolved ontology slice (`ontology.query`), so
the envelope's signals — sources, as-of dates, dissent — are projected straight
off the assertions, not re-derived from raw text. The abstain signal is ontology
**coverage** (did the question's (subject, attribute, scope) have live resolved
assertions?), NOT retrieval similarity: a citation proves a claim wasn't invented,
similarity measures relevance — neither measures truth. An in-scope question with
no covering assertion is an honest gap (abstain + escalate), never a fall-back-and-
guess over raw text.
"""

from __future__ import annotations

from house_harness.schema import (
    AnswerPath,
    Claim,
    Confidence,
    Dissent,
    Escalation,
    HouseHarness,
    RelationKind,
    Status,
    TrustEnvelope,
)

# Below this ontology coverage, we abstain rather than confabulate (tune on evals).
ABSTAIN_THRESHOLD = 0.35


def build_envelope(
    answer: str,
    claims: list[Claim],
    dissent: list[Dissent],
    coverage_gaps: list[str],
    coverage: float,
    harness: HouseHarness,
    answer_path: AnswerPath = AnswerPath.ontology,
    errors: list[str] | None = None,
) -> TrustEnvelope:
    """Assemble the envelope, separating operational failure from honest abstention.

    `coverage` ∈ [0,1] is how well the resolved ontology covers the question's
    (subject, attribute, scope) — the primary path. On the out-of-ontology fallback
    it degrades to raw-retrieval confidence, which caps envelope confidence lower by
    design (relevance is not truth). `answer_path` records which path produced this:
    `ontology` claims carry `assertion_id`s; `fallback` claims do not."""
    errors = errors or []
    confidence = _confidence(claims, coverage)
    status = _status(errors, answer, confidence)
    return TrustEnvelope(
        answer=answer if status in (Status.answered, Status.degraded) else "",
        status=status,
        answer_path=answer_path,
        claims=claims,
        freshness=_freshness(claims),
        dissent=dissent,
        coverage_gaps=coverage_gaps,
        escalate_to=[_route(gap, harness) for gap in coverage_gaps],
        errors=errors,
        confidence=confidence,
    )


def _status(errors: list[str], answer: str, confidence: Confidence) -> Status:
    if errors and not answer:
        return Status.failed  # could not complete — agent retries/alerts
    if errors:
        return Status.degraded  # partial — answer exists but a stage failed
    if confidence is Confidence.abstain:
        return Status.abstained  # no source covers it — agent escalates/fetches
    return Status.answered


def _confidence(claims: list[Claim], coverage: float) -> Confidence:
    if not claims or coverage < ABSTAIN_THRESHOLD:
        return Confidence.abstain
    if coverage < 0.55:
        return Confidence.low
    if coverage < 0.75:
        return Confidence.medium
    return Confidence.high


def _freshness(claims: list[Claim]) -> str | None:
    dates = [c.as_of for c in claims if c.as_of]
    return f"newest supporting source: {max(dates)}" if dates else None


def _tokens(text: str) -> set[str]:
    """Content tokens (length > 3, lowercased) for keyword matching."""
    return {w.lower().strip(".,:;!?\"'()") for w in text.split() if len(w) > 3}


def _route(gap: str, harness: HouseHarness) -> Escalation:
    """Resolve a coverage gap to the owning authority already in the harness — the
    line between a search box that admits ignorance and a decision engine that
    knows who holds the answer. Deterministic keyword routing, two sources:

    1. **Guardrails** — a guardrail whose `rule` shares a content word with the gap
       routes to its `authority` (e.g. a pricing gap -> the pricing authority).
    2. **Taxonomy `owns` edges** — failing that, an `owns` edge whose target matches
       a gap word routes to the owner node (e.g. a metric -> its metric owner).

    No match -> an honest unrouted escalation (`owner="unresolved"`), never a guess."""
    gap_tokens = _tokens(gap)
    for g in harness.guardrails:
        if g.authority and gap_tokens & _tokens(g.rule):
            return Escalation(
                gap=gap, owner=g.authority, evidence=[s.artifact_id for s in g.sources]
            )
    for edge in harness.taxonomy.edges:
        if edge.relation is RelationKind.owns and gap_tokens & _tokens(edge.dst):
            return Escalation(gap=gap, owner=edge.src, evidence=[])
    return Escalation(gap=gap, owner="unresolved", evidence=[])
