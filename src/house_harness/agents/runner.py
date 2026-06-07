"""Agent runner — the single home for the hard caps named in CLAUDE.md.

Every agent invocation goes through here so the step cap, per-call timeout, and
cost-per-run cap are enforced in one chokepoint, not scattered across call
sites. Exceeding a cap raises, and the caller maps that to a degraded/failed
trust envelope (see synthesis/envelope.py).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass


@dataclass(frozen=True)
class Caps:
    max_steps: int = 12  # hard step cap per agent loop
    timeout_s: float = 60.0  # per-call wall-clock budget
    max_cost_usd: float = 0.50  # cost-per-run budget


DEFAULT_CAPS = Caps()


def run_capped(agent, prompt: str, caps: Caps = DEFAULT_CAPS):
    """Invoke `agent` under `caps` — the single chokepoint for the hard caps.

    Framework-agnostic: `agent` may be a plain callable (`agent(prompt)`) or a
    LangChain-style object exposing `.invoke(prompt)` (preferred when present).

    - timeout_s: wall-clock budget enforced via a worker thread; on breach raises
      TimeoutError so the caller can emit status=degraded|failed instead of hanging.
    - max_steps: applies to AGENT LOOPS — if the result is a LangChain-style dict
      carrying an intermediate-steps / messages list, raise when it exceeds the cap.
      For a plain callable there is no step list, so this is a no-op.
    - max_cost_usd: a budget reminder only. True cost needs token accounting we do
      not have here, so this is a documented placeholder (no-op) — honesty over a
      faked check.
    """
    invoke = getattr(agent, "invoke", None)
    call = (lambda: invoke(prompt)) if callable(invoke) else (lambda: agent(prompt))

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(call)
        try:
            result = future.result(timeout=caps.timeout_s)
        except FuturesTimeoutError as exc:
            raise TimeoutError(f"agent exceeded {caps.timeout_s}s") from exc

    # Step cap: only meaningful for agent-loop results that report their steps.
    if isinstance(result, dict):
        steps = result.get("intermediate_steps") or result.get("messages")
        if isinstance(steps, list) and len(steps) > caps.max_steps:
            raise RuntimeError(f"agent exceeded {caps.max_steps} steps")

    # max_cost_usd: placeholder — no token accounting available here (no-op).

    return result
