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
        "This server is the company's brain — a resolved, sourced ontology over its "
        "documents. USE IT whenever the user asks anything about the company or says "
        "'our' / names the company: metrics (NPS, revenue, runway), the org (who reports "
        "to whom, who owns what), policies and approval authority, product and launch "
        "status, customers and churn, pipeline, or any fact that spans documents. "
        "ask_company(query) answers a free-form question and returns a trust envelope "
        "(sourced claims, dissent, freshness, coverage gaps, authority escalation, "
        "confidence) — act on the envelope, not just the prose; it self-flags answer_path. "
        "For a menu of ready-made commands call list_commands, then run one with "
        "run_command(name, argument). get_harness / get_harness_health / get_entity expose "
        "the harness, its gaps, and a single entity directly."
    ),
)


# ── tool bodies, factored so run_command can reuse them ───────────────────────


def _ask(query: str) -> dict:
    return _app.answer(query).model_dump(mode="json")


def _harness() -> dict:
    harness, _store = _app._serving_state()
    if harness is None:
        return {"error": "ontology not built — run `house-harness run data/`"}
    return harness.model_dump(mode="json")


def _health() -> dict:
    harness, store = _app._serving_state()
    if harness is None:
        return {"error": "ontology not built — run `house-harness run data/`"}
    _current, dissents = ontology.resolve(store)
    return health.assess_harness(harness, dissents, store).model_dump(mode="json")


def _entity(name: str) -> dict:
    _harness_, store = _app._serving_state()
    needle = name.strip().lower()
    matches = [
        a.model_dump(mode="json") for a in store.values() if a.live and needle in a.subject.lower()
    ]
    return {"name": name, "assertions": matches, "count": len(matches)}


@mcp.tool()
def ask_company(query: str) -> dict:
    """Answer a deep question about the company (metrics, org, policy, status, risk —
    anything spanning the documents). Returns the full trust envelope. Use this for any
    free-form company question."""
    return _ask(query)


@mcp.tool()
def get_harness() -> dict:
    """Return the distilled House Harness (charter, targets, guardrails, taxonomy)."""
    return _harness()


@mcp.tool()
def get_harness_health() -> dict:
    """Return harness health: completeness + prioritized gaps with quick-win actions
    and owners (what the system sees about the company, and what to fix first)."""
    return _health()


@mcp.tool()
def get_entity(name: str) -> dict:
    """Return the resolved live assertions about one entity (fuzzy name match),
    each with its source and as-of date — distinct entities stay distinct."""
    return _entity(name)


# ── named commands: a discoverable menu (list_commands) the agent can run by name
# (run_command). Query-commands go through ask_company; the rest are direct reads. ─

_COMMANDS: dict[str, dict[str, str]] = {
    "exec_brief": {
        "title": "Executive brief",
        "description": "NPS by segment, revenue vs target, launch status, and top risks.",
        "query": "Give an executive brief: current NPS by segment, the latest quarter "
        "revenue versus target, the status and date of our major launches, and the top risks.",
    },
    "nps": {
        "title": "NPS by segment",
        "description": "Net Promoter Score, aggregate and per segment.",
        "query": "What is our NPS, aggregate and broken down by segment?",
    },
    "revenue": {
        "title": "Revenue vs target",
        "description": "Latest quarter revenue against plan.",
        "query": "What is our latest quarter revenue versus target?",
    },
    "launches": {
        "title": "Launch status",
        "description": "GA dates and schedule status of major projects/products.",
        "query": "What is the status and GA date of each of our major launches and projects?",
    },
    "risks": {
        "title": "Top risks",
        "description": "Current risks: churn, slipped dates, pipeline caveats.",
        "query": "What are our top risks right now — churn, slipped dates, and pipeline caveats?",
    },
    "pipeline": {
        "title": "Pipeline trust",
        "description": "Whether the CRM/pipeline figures can be trusted, by region.",
        "query": "Can I trust our sales pipeline figures, and how do they differ by region?",
    },
    "owner": {
        "title": "Owner of an area",
        "description": "Who owns / has authority over an area or system.",
        "argument": "area (e.g. 'merchant_id schema', 'pricing', 'discount approval')",
        "query": "Who owns {arg}, and who has authority to decide on it?",
    },
    "reports": {
        "title": "Reporting line",
        "description": "Who a person reports to, and who reports to them.",
        "argument": "person name",
        "query": "Who does {arg} report to, and who reports to {arg}?",
    },
    "entity": {
        "title": "Entity lookup",
        "description": "Resolved facts about one person/team/product, with sources.",
        "argument": "name",
        "kind": "entity",
    },
    "harness": {
        "title": "Company harness",
        "description": "The distilled charter, targets, guardrails, and taxonomy.",
        "kind": "harness",
    },
    "health": {
        "title": "Harness health",
        "description": "What's missing or off, with quick-win actions and owners.",
        "kind": "health",
    },
}


@mcp.tool()
def list_commands() -> dict:
    """List the named commands this server supports — a menu of ready-made company
    queries. Call this when the user asks what you can do / for the list of commands,
    then run one with run_command(name, argument). `argument` is null unless required."""
    return {
        "commands": [
            {
                "name": name,
                "title": c["title"],
                "description": c["description"],
                "argument": c.get("argument"),
            }
            for name, c in _COMMANDS.items()
        ]
    }


@mcp.tool()
def run_command(name: str, argument: str = "") -> dict:
    """Run a named command from list_commands. Pass `argument` for commands whose
    `argument` field is set (e.g. owner -> the area, reports/entity -> the name)."""
    cmd = _COMMANDS.get(name.strip().lower())
    if cmd is None:
        return {"error": f"unknown command {name!r}", "hint": "call list_commands for the menu"}
    if cmd.get("argument") and not argument.strip():
        return {"error": f"command {name!r} needs an argument: {cmd['argument']}"}
    kind = cmd.get("kind")
    if kind == "harness":
        return _harness()
    if kind == "health":
        return _health()
    if kind == "entity":
        return _entity(argument)
    return _ask(cmd["query"].replace("{arg}", argument.strip()))


# ── HTTP routes mounted on the SAME app as /mcp, so one hosted process serves the
# MCP endpoint plus the deploy probe and a REST fallback for non-MCP clients. ──────


@mcp.custom_route("/health", methods=["GET"])
async def _health_route(_request: Request) -> JSONResponse:
    """Open deploy probe — {status, mode}. Same contract as the legacy HTTP server."""
    return JSONResponse(_app.health())


@mcp.custom_route("/ask", methods=["POST"])
async def _ask_route(request: Request) -> JSONResponse:
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

    - `stdio` (default): an agent spawns it as a LOCAL subprocess; ingest blocks.
    - `streamable-http` / `sse`: a NETWORKED server an agent adds by URL. It binds and
      serves GET /health IMMEDIATELY; ingest-on-boot runs in a BACKGROUND thread so a
      slow first build never blocks the health check (a blocking on-boot extraction is
      reaped mid-build by the platform). The MCP tools report 'ontology not built' until
      the warm completes, then serve normally. The same app also serves POST /ask."""
    logger.info("tracing %s", "on" if _tracing.init_tracing() else "off (no LANGSMITH_API_KEY)")

    def _warm() -> None:
        if not ingest_on_boot or _app.serve_mode().value == "mock":
            return
        from house_harness.pipeline.run import ingest_on_boot as _ingest

        corpus_dir = corpus or os.environ.get("HOUSE_HARNESS_CORPUS_DIR", "data")
        try:
            if _ingest(corpus_dir):
                _app.reset_state()  # reload the freshly-built ontology
                logger.info("ingest-on-boot complete; ontology loaded")
        except Exception:  # noqa: BLE001 — a failed boot-ingest must not stop the server
            logger.exception("ingest-on-boot failed; serving with whatever is in the store")

    if transport == "stdio":
        _warm()  # local spawn: block until ready (no health check to satisfy)
    else:  # networked: serve /health immediately, warm the ontology in the background
        import threading

        from mcp.server.transport_security import TransportSecuritySettings

        threading.Thread(target=_warm, name="ingest-on-boot", daemon=True).start()
        mcp.settings.host = "0.0.0.0"  # noqa: S104 — container binds all interfaces
        mcp.settings.port = port or int(os.environ.get("APP_PORT", "8080"))
        # DNS-rebinding protection guards LOCALHOST servers from browser rebinding; the
        # default allowlist is localhost-only and 403s a public host. This is a
        # public-by-design URL reached directly by MCP clients, so accept any Host/Origin.
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        logger.info(
            "MCP serving on :%d%s (mode=%s); ontology warming in background",
            mcp.settings.port,
            mcp.settings.streamable_http_path,
            _app.serve_mode().value,
        )
    mcp.run(transport=cast('Literal["stdio", "sse", "streamable-http"]', transport))
