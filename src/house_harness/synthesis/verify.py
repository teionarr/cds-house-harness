"""Entailment verification — an OFFLINE eval-time judge, not a runtime pass.

Grounded is not correct, but a second LLM call *per claim per query* is the
biggest hidden cost multiplier in the system and a poor runtime trade. So v1
splits it:

  - RUNTIME (hot path): cite-or-abstain only. Every claim must carry a non-empty
    cited span or the answer abstains (synthesis/envelope.py). `Claim.verified`
    is left None at runtime — we don't pretend a per-claim entailment check ran.

  - OFFLINE (eval harness): this judge runs over the gold set, checking that each
    cited span actually *supports* the claim, and reports an entailment score
    (and calibration). That's where "grounded != correct" is measured and where
    regressions are caught — cheaply, in batch, not on every user query.

Promote to a runtime pass later only for high-stakes answers, behind a flag.
"""

from __future__ import annotations

from house_harness.schema import Claim


def judge_entailment(claims: list[Claim]) -> list[Claim]:
    """Eval-time: set `verified` per claim by checking the cited span supports it
    (NLI / strict LLM judge requiring quoted evidence). Called by the eval
    harness over gold answers, not per user query. TODO: implement."""
    raise NotImplementedError
