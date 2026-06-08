"""The validate-at-the-boundary seam.

Every LLM call that feeds a downstream stage returns a Pydantic model, never
prose or a raw dict. Invalid output is the #1 LLM failure mode, so we validate,
repair once with the error, retry a bounded number of times, then give up
cleanly so the caller can mark the unit degraded/failed.

Two cross-cutting concerns live here because this is the one place every
structured call funnels through:
- **Usage accounting** — token + latency per call are accumulated so the eval can
  report cost per arm (the harness's ontology slice vs the baseline's whole-corpus
  stuff). Drain it with `drain_usage()`.
- **Prompt caching** — a large, reused prefix (the whole corpus) is marked
  `cache_control=ephemeral` so it is billed once per ~5 min window instead of on
  every call. This is the difference between a baseline that re-pays for 53K tokens
  every query and one that doesn't.
"""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ValidationError

from house_harness.config.llm import get_model

MAX_ATTEMPTS = 3

# ── usage accounting (drained by the eval harness, per arm) ───────────────────
_USAGE: list[dict] = []


def reset_usage() -> None:
    _USAGE.clear()


def drain_usage() -> dict:
    """Return aggregate usage since the last reset and clear it."""
    calls = len(_USAGE)
    agg = {
        "calls": calls,
        "input_tokens": sum(u["input_tokens"] for u in _USAGE),
        "output_tokens": sum(u["output_tokens"] for u in _USAGE),
        "cache_read_tokens": sum(u["cache_read_tokens"] for u in _USAGE),
        "duration_ms": round(sum(u["duration_ms"] for u in _USAGE)),
    }
    _USAGE.clear()
    return agg


def _record(raw, duration_ms: float) -> None:
    um = getattr(raw, "usage_metadata", None) or {}
    details = um.get("input_token_details") or {}
    _USAGE.append(
        {
            "input_tokens": um.get("input_tokens", 0),
            "output_tokens": um.get("output_tokens", 0),
            "cache_read_tokens": details.get("cache_read", 0),
            "duration_ms": duration_ms,
        }
    )


def _message(prompt: str, cached_prefix: str | None):
    """A plain string, or a two-block message whose large prefix is cache-marked."""
    if not cached_prefix:
        return prompt
    return [
        HumanMessage(
            content=[
                {"type": "text", "text": cached_prefix, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": prompt},
            ]
        )
    ]


def llm_json[T: BaseModel](
    prompt: str, schema: type[T], *, model: str | None = None, cached_prefix: str | None = None
) -> T:
    """Return a schema-valid instance of `schema`, or raise after MAX_ATTEMPTS.

    Uses the provider's structured-output binding (no regex parsing of prose) with
    `include_raw` so token usage is captured. On a validation error, re-prompts once
    with the error before retrying. `cached_prefix` (e.g. the whole corpus) is sent
    as a cache-marked block so it is billed once, not per call.
    """
    llm = get_model(model).with_structured_output(schema, include_raw=True)
    last_error: Exception | None = None
    suffix = prompt
    for _ in range(MAX_ATTEMPTS):
        started = time.perf_counter()
        result = llm.invoke(_message(suffix, cached_prefix))
        _record(result.get("raw"), (time.perf_counter() - started) * 1000)
        parsed, err = result.get("parsed"), result.get("parsing_error")
        if parsed is not None and err is None:
            return parsed  # type: ignore[return-value]
        last_error = err or ValidationError.from_exception_data(schema.__name__, [])
        suffix = f"{prompt}\n\nYour previous output failed validation:\n{err}\nReturn valid output."
    raise RuntimeError(
        f"llm_json: no valid {schema.__name__} after {MAX_ATTEMPTS} attempts"
    ) from last_error
