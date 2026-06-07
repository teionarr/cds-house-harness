"""Untrusted-content gate: ingested documents are data, never instructions.

Neutralizes embedded directives before artifact text reaches any prompt. This is
a real prompt-injection surface — the corpus is adversarial by design.
"""

from __future__ import annotations

import re

# Phrases that look like attempts to steer the agent from inside a document.
_INJECTION = re.compile(
    r"(?i)\b(ignore (the )?(previous|above) instructions|"
    r"you are now|system prompt|disregard .* rules)\b"
)


def neutralize(text: str) -> str:
    """Defang directive-looking spans so retrieved text stays inert as data."""
    return _INJECTION.sub("[neutralized-directive]", text)
