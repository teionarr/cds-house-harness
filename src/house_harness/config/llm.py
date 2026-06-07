"""The single seam where the model vendor lives.

RULE (CLAUDE.md): no provider SDK is imported anywhere else in the codebase.
Swapping providers is a one-line env change, not a refactor.

Provider-leakage controls live here because this is the only place data leaves
to a model:
- The provider account MUST be configured for zero-data-retention / no-training
  (REQUIRE_ZDR gates startup as a reminder; actual ZDR is an account setting).
- For sensitive deployments, point HOUSE_HARNESS_MODEL at a self-hosted / VPC
  model — the seam makes that a config change, keeping data in the customer's
  boundary. Send minimal context (sourced spans, not whole documents).
"""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model

# e.g. "anthropic:claude-sonnet-4-6", "openai:gpt-5", or a self-hosted endpoint.
_DEFAULT = os.environ.get("HOUSE_HARNESS_MODEL", "anthropic:claude-sonnet-4-6")

# Reminder flag: sensitive corpora require a ZDR/no-train provider agreement.
REQUIRE_ZDR = os.environ.get("REQUIRE_ZDR", "true").lower() == "true"


def get_model(model: str | None = None, **kwargs):
    """Return a chat model behind LangChain's universal interface.

    Callers never know or care which vendor is underneath.
    """
    return init_chat_model(model or _DEFAULT, **kwargs)
