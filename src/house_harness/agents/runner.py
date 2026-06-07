"""Agent runner — the single home for the hard caps named in CLAUDE.md.

Every agent invocation goes through here so the step cap, per-call timeout, and
cost-per-run cap are enforced in one chokepoint, not scattered across call
sites. Exceeding a cap raises, and the caller maps that to a degraded/failed
trust envelope (see synthesis/envelope.py).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Caps:
    max_steps: int = 12        # hard step cap per agent loop
    timeout_s: float = 60.0    # per-call wall-clock budget
    max_cost_usd: float = 0.50 # cost-per-run budget


DEFAULT_CAPS = Caps()


def run_capped(agent, prompt: str, caps: Caps = DEFAULT_CAPS):
    """Invoke `agent` under `caps`. TODO: wire step/timeout/cost guards around
    the LangChain create_agent invocation; raise on breach so the caller can
    emit status=degraded|failed rather than hang or overspend."""
    raise NotImplementedError
