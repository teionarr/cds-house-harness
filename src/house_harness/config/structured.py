"""The validate-at-the-boundary seam.

Every LLM call that feeds a downstream stage returns a Pydantic model, never
prose or a raw dict. Invalid output is the #1 LLM failure mode, so we validate,
repair once with the error, retry a bounded number of times, then give up
cleanly so the caller can mark the unit degraded/failed.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from house_harness.config.llm import get_model

T = TypeVar("T", bound=BaseModel)

MAX_ATTEMPTS = 3


def llm_json(prompt: str, schema: type[T], *, model: str | None = None) -> T:
    """Return a schema-valid instance of `schema`, or raise after MAX_ATTEMPTS.

    Uses the provider's structured-output binding (no regex parsing of prose).
    On a ValidationError, re-prompts once with the error before retrying.
    """
    llm = get_model(model).with_structured_output(schema)
    last_error: Exception | None = None
    msg = prompt
    for _ in range(MAX_ATTEMPTS):
        try:
            return llm.invoke(msg)  # type: ignore[return-value]
        except ValidationError as exc:
            last_error = exc
            msg = f"{prompt}\n\nYour previous output failed validation:\n{exc}\nReturn valid output."
    raise RuntimeError(f"llm_json: no valid {schema.__name__} after {MAX_ATTEMPTS} attempts") from last_error
