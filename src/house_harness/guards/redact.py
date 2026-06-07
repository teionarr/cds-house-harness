"""Egress redaction — a PII/secret pass before content goes to the model or
out the MCP. Pattern-level for now (cards, emails, tokens); a real DLP is §8.
"""

from __future__ import annotations

import re

_PATTERNS = {
    "card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "token": re.compile(r"\b(sk|pk|ghp|xox[baprs])[-_][A-Za-z0-9]{10,}\b"),
}


def redact(text: str) -> str:
    """Mask sensitive spans. Conservative: prefer over-masking to leakage."""
    for label, pattern in _PATTERNS.items():
        text = pattern.sub(f"[redacted:{label}]", text)
    return text
