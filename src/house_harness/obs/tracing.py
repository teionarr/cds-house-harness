"""Observability seam. LangSmith is the only tracing backend named here, behind
this module — swap it without touching pipeline or retrieval code.

LangSmith is in the LangChain family, so LangChain/LangGraph runs auto-trace when
the LANGSMITH_* env vars are set (LANGSMITH_TRACING=true, LANGSMITH_API_KEY,
LANGSMITH_PROJECT). This seam exposes a client only for the things that aren't
auto-captured: custom spans and pushing/pulling eval datasets + runs.

Privacy: LangSmith Cloud is the zero-infra default. For sensitive corpora, point
LANGSMITH_ENDPOINT at a self-hosted/VPC LangSmith and send minimal sourced spans
— the same swappable-route stance as the model seam (config/llm.py).
"""

from __future__ import annotations

import os
from functools import lru_cache


def init_tracing() -> bool:
    """Call once at startup. Tracing is ON only if LANGSMITH_API_KEY is set; with no
    key we force LANGSMITH_TRACING=false so LangChain never tries to emit (and warn).
    Graceful by design — no key, no crash, no tracing. Returns whether it's on."""
    if os.environ.get("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        return True
    os.environ["LANGSMITH_TRACING"] = "false"
    return False


@lru_cache(maxsize=1)
def get_tracer():
    """Return a configured LangSmith client (or None if unconfigured in dev).

    Tracing of LangChain runs is driven by env (LANGSMITH_TRACING=true); this
    client is for custom spans and eval-dataset operations.
    """
    if not os.environ.get("LANGSMITH_API_KEY"):
        return None
    from langsmith import Client

    return Client()
