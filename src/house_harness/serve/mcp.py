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
never diverge. Run with `house-harness mcp` (stdio transport — an agent spawns it).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from house_harness.pipeline import health, ontology
from house_harness.serve import app as _app

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
    return health.assess_harness(harness, dissents).model_dump(mode="json")


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


def run(transport: str = "stdio") -> None:
    """Start the MCP server (default stdio — the agent spawns it as a subprocess)."""
    mcp.run(transport=transport)
