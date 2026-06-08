"""MCP server — the primary, agent-native surface.

The consumer is an AI agent, so the keystone interface is MCP, not a search box.
Exposes four tools over the resolved ontology + House Harness:

- `ask_company(query)`      -> the full trust envelope (answer + claims + sources +
                               dissent + freshness + coverage gaps + escalation +
                               confidence + status). Returns the envelope, never a
                               bare string — that return shape is what makes it
                               agent-native (an agent can act on it, not just read it).
- `get_harness()`           -> the distilled House Harness (charter, targets,
                               guardrails/authorities, taxonomy).
- `get_harness_health()`    -> the mirror: what's missing/off + quick-win actions.
- `get_entity(name)`        -> the resolved assertions about one entity, with sources.

`ask_company` routes through `serve.app.answer` (same single entrypoint as HTTP —
ontology-first, egress-redacted, mode-guarded), so the MCP and HTTP surfaces can
never diverge.

Two ways to run it:
- `house-harness mcp` — stdio, spawned locally by an agent as a subprocess.
- `house-harness mcp --transport streamable-http` — a NETWORKED server at
  `http://<host>:<port>/mcp`, which an agent adds by URL with one command
  (`claude mcp add --transport http <name> https://<host>/mcp`). The same app also
  serves GET /health (open) and POST /ask (token-gated).
"""

from __future__ import annotations

import logging
import os
from typing import Literal, cast

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from house_harness.obs import tracing as _tracing
from house_harness.pipeline import health, ontology
from house_harness.serve import app as _app

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "house-harness",
    instructions=(
        "Query the company's resolved ontology. ask_company returns a trust envelope "
        "(sourced claims, dissent, freshness, coverage gaps, authority-routed escalation, "
        "confidence) — act on the envelope, not just the prose. Answers are ontology-first; "
        "out-of-namespace questions fall back to raw corpus and self-flag (answer_path)."
    ),
)


@mcp.tool()
def ask_company(query: str) -> dict:
    """Answer a deep question about the company. Returns the full trust envelope."""
    return _app.answer(query).model_dump(mode="json")


@mcp.tool()
def get_harness() -> dict:
    """Return the distilled House Harness (charter, targets, guardrails, taxonomy)."""
    harness, _store = _app._serving_state()
    if harness is None:
        return {"error": "ontology not built — run `house-harness run data/`"}
    return harness.model_dump(mode="json")


@mcp.tool()
def get_harness_health() -> dict:
    """Return harness health: completeness + prioritized gaps with quick-win actions
    and owners (what the system sees about the company, and what to fix first)."""
    harness, store = _app._serving_state()
    if harness is None:
        return {"error": "ontology not built — run `house-harness run data/`"}
    _current, dissents = ontology.resolve(store)
    return health.assess_harness(harness, dissents, store).model_dump(mode="json")


@mcp.tool()
def get_entity(name: str) -> dict:
    """Return the resolved live assertions about one entity (fuzzy name match),
    each with its source and as-of date — distinct entities stay distinct."""
    _harness, store = _app._serving_state()
    needle = name.strip().lower()
    matches = [
        a.model_dump(mode="json") for a in store.values() if a.live and needle in a.subject.lower()
    ]
    return {"name": name, "assertions": matches, "count": len(matches)}


# ── HTTP routes mounted on the SAME app as /mcp, so one hosted process serves the
# MCP endpoint plus the deploy probe and a REST fallback for non-MCP clients. ──────


@mcp.custom_route("/health", methods=["GET"])
async def _health(_request: Request) -> JSONResponse:
    """Open deploy probe — {status, mode}. Same contract as the legacy HTTP server."""
    return JSONResponse(_app.health())


@mcp.custom_route("/ask", methods=["POST"])
async def _ask(request: Request) -> JSONResponse:
    """Token-gated REST fallback for non-MCP clients: {"q": "..."} -> trust envelope."""
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip() or None
    try:
        _app.require_token(token)
    except PermissionError:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — malformed request body
        return JSONResponse({"error": "invalid json"}, status_code=400)
    try:
        env = _app.answer((body or {}).get("q", ""))
    except NotImplementedError as exc:
        return JSONResponse({"error": str(exc)}, status_code=501)  # live pipeline unwired
    return JSONResponse(env.model_dump(mode="json"))


def run(
    transport: str = "stdio",
    ingest_on_boot: bool = False,
    corpus: str | None = None,
    port: int | None = None,
) -> None:
    """Start the MCP server.

    - `stdio` (default): an agent spawns it as a LOCAL subprocess.
    - `streamable-http` / `sse`: a NETWORKED server an agent adds by URL, e.g.
      `claude mcp add --transport http house-harness https://<host>/mcp`. The same
      app also serves GET /health (open) and POST /ask (token-gated)."""
    logger.info("tracing %s", "on" if _tracing.init_tracing() else "off (no LANGSMITH_API_KEY)")
    if ingest_on_boot and _app.serve_mode().value != "mock":
        from house_harness.pipeline.run import ingest_on_boot as _ingest

        corpus_dir = corpus or os.environ.get("HOUSE_HARNESS_CORPUS_DIR", "data")
        try:
            if _ingest(corpus_dir):
                _app.reset_state()  # reload the freshly-built ontology
        except Exception:  # noqa: BLE001 — a failed boot-ingest must not stop the server
            logger.exception("ingest-on-boot failed; serving with whatever is in the store")
    if transport != "stdio":  # networked: bind all interfaces on the container port
        from mcp.server.transport_security import TransportSecuritySettings

        mcp.settings.host = "0.0.0.0"  # noqa: S104 — container binds all interfaces
        mcp.settings.port = port or int(os.environ.get("APP_PORT", "8080"))
        # DNS-rebinding protection guards LOCALHOST servers from browser rebinding; the
        # default allowlist is localhost-only and 403s a public host ("Invalid Host
        # header"). This is a public-by-design URL reached directly by MCP clients, so
        # that threat model does not apply — accept any Host/Origin.
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        logger.info(
            "MCP serving on :%d%s (mode=%s)",
            mcp.settings.port,
            mcp.settings.streamable_http_path,
            _app.serve_mode().value,
        )
    mcp.run(transport=cast('Literal["stdio", "sse", "streamable-http"]', transport))
