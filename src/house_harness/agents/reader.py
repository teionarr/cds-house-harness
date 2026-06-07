"""Reader pod — the only component that sees untrusted input.

Sees the user query + retrieved content, has NO tools and NO execution, and is
bound to structured output. The most an injection can produce is a bad draft or
a typed `PlanRequest` the executor will reject — never an action. The typed
`ReaderOutput` is the trust boundary.
"""

from __future__ import annotations

from house_harness.schema import ReaderOutput, RetrievedChunk


def read(query: str, context: list[RetrievedChunk]) -> ReaderOutput:
    """Structured-output call over untrusted input -> `ReaderOutput` (an answer
    draft + typed, allowlisted `PlanRequest`s). No tools, no side effects. TODO:
    one `llm_json` call bound to the ReaderOutput schema."""
    raise NotImplementedError
