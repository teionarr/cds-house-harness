"""Executor pod — privileged, but never sees raw untrusted text.

Consumes the reader's typed `ReaderOutput`, validates every `PlanRequest`
against a CLOSED vocabulary (`RequestKind`) + an ontology allowlist (no
URL/host/shell can cross), executes only the validated requests, and assembles
the `TrustEnvelope`. Typed boundary in, validated actions out — the security
property has a unit test, not a hope. In deployment the reader and executor run
as separate processes/containers; the typed boundary is the trust boundary
regardless of co-location.
"""

from __future__ import annotations

from house_harness.schema import (
    HouseHarness,
    PlanRequest,
    ReaderOutput,
    RequestKind,
    TrustEnvelope,
)

_ALLOWED_KINDS = (RequestKind.retrieve, RequestKind.escalate)


def validate(requests: list[PlanRequest], allowed_targets: set[str]) -> list[PlanRequest]:
    """The trust boundary: reject any request outside the closed vocabulary or
    off the ontology allowlist (and anything URL/host/shell-shaped). Pure +
    testable, so the security property has a unit test, not a hope."""
    for r in requests:
        if r.kind not in _ALLOWED_KINDS:
            raise PermissionError(f"action not permitted: {r.kind!r}")
        if r.target not in allowed_targets:
            raise PermissionError(f"target not allowlisted: {r.target!r}")
    return requests


def execute(
    reader_output: ReaderOutput,
    harness: HouseHarness,
    allowed_targets: set[str],
) -> TrustEnvelope:
    """validate -> execute validated requests -> assemble envelope. Never receives
    raw untrusted text — only the reader's typed output. TODO:
      1. validate(reader_output.requests, allowed_targets)
      2. execute (retrieve -> context; escalate -> owning authority)
      3. assemble the TrustEnvelope (cite-or-abstain; dissent; freshness; status)
    Runs under runner.run_capped; a cap breach -> status=degraded|failed.
    """
    raise NotImplementedError
