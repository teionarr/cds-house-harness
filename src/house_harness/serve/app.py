"""Agent-facing surfaces. MCP server (primary) + thin HTTP (/ask, /health).

ask_company returns a TrustEnvelope (not a bare string). All outbound content
passes through guards.redact before leaving the process.

Auth: the live endpoint requires a bearer token (HOUSE_HARNESS_API_TOKEN). The
agent presents it; /health is unauthenticated for deploy probes. Reject with 401
on missing/bad token before any work — the executor pod still gates actions
regardless (defense in depth).

Serve mode (anti-"ship-the-mock" guard): every surface calls the single `answer()`
entrypoint below. `live` is the DEFAULT — if the real pipeline isn't wired,
`answer()` raises rather than silently serving canned data. `mock` is an explicit,
logged opt-in used ONLY for the Phase-1 deploy skeleton; mock envelopes stamp
themselves `mode=mock`, /health echoes the mode, and `make validate` FAILs on any
graded answer with `mode != live`. So a mock cannot masquerade as a real answer.
"""

from __future__ import annotations

import logging
import os

from house_harness.schema import ServeMode, TrustEnvelope

logger = logging.getLogger(__name__)


def require_token(presented: str | None) -> None:
    """401 unless `presented` matches HOUSE_HARNESS_API_TOKEN. TODO: wire as MCP/HTTP
    middleware on every tool/route except /health."""
    expected = os.environ.get("HOUSE_HARNESS_API_TOKEN")
    if not expected or presented != expected:
        raise PermissionError("unauthorized")


def serve_mode() -> ServeMode:
    """Resolve the serve mode. DEFAULT is live; mock requires explicit opt-in via
    HOUSE_HARNESS_SERVE_MODE=mock. Anything other than 'mock' is treated as live."""
    return ServeMode.mock if os.environ.get("HOUSE_HARNESS_SERVE_MODE", "live").lower() == "mock" else ServeMode.live


def health() -> dict:
    """Open probe. Echoes the serve mode so a live URL can never hide that it's
    answering from the mock."""
    return {"status": "ok", "mode": serve_mode().value}


def answer(query: str) -> TrustEnvelope:
    """The single entrypoint every surface (MCP tools, HTTP /ask) calls.

    - mode=mock (explicit, Phase-1 skeleton): returns a self-identifying mock
      envelope (mode=mock) and logs a loud banner so no one forgets it's on.
    - mode=live (default): the real pipeline — ontology.query -> claims ->
      synthesis.build_envelope. Until that lands it RAISES; we refuse to silently
      serve canned data in live mode.
    """
    if serve_mode() is ServeMode.mock:
        logger.warning(
            "SERVING MOCK ENVELOPES (HOUSE_HARNESS_SERVE_MODE=mock) — the real "
            "pipeline is not wired; do not grade or ship from this mode."
        )
        from house_harness.synthesis import _mock

        return _mock.answer(query)  # stamped mode=mock
    # live: real pipeline — ontology-first. Load the harness, then call the single
    # orchestrator that encodes the call graph (resolve_question -> ontology.query ->
    # claims_from_assertions -> build_envelope, answer_path=ontology). Raw retrieval
    # is reached only inside respond._fallback, never as the default.
    # TODO (Phase 3): from house_harness.synthesis import respond; return respond.answer(query, harness)
    raise NotImplementedError("live synthesis pipeline not wired yet — wire synthesis.respond.answer (PLAN.md Phase 3)")


# TODO: wire MCP tools (ask_company, get_entity, get_harness, get_harness_health)
# and HTTP routes (/ask authed -> answer(); /health open -> health()) behind
# require_token, with guards.redact on egress.
