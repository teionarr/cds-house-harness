"""Golden regression test for the extraction PROMPT (the make-or-break step).

Runs the REAL extractor (`harness.extract_doc`) on the verbatim excerpts in
`tests/fixtures/extraction_golden.json` and checks the invariants the fixture
encodes: the staleness double-emit (real value + scoped public value), the
`new_attribute:` escape hatch, the chat-tier reliability floor, signal-vs-noise,
and the hard namespace-conformance gate. Needs the model, so it SKIPS without
ANTHROPIC_API_KEY (CI runs it where the key is injected).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from house_harness.pipeline import attributes
from house_harness.pipeline.harness import extract_doc
from house_harness.schema import Assertion

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="extraction needs the model (ANTHROPIC_API_KEY)"
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "extraction_golden.json").read_text()
)
CASES = {c["id"]: c for c in FIXTURE["cases"]}


def _extract(case: dict) -> list[Assertion]:
    return extract_doc(
        artifact_id=case["artifact_id"],
        text=case["input_text"],
        source_type=case["source_tier"],
        doc_as_of=case["as_of"],
    )


def _lower_values(assertions: list[Assertion]) -> str:
    return " ".join(f"{a.subject} {a.attribute} {a.value} {a.scope}" for a in assertions).lower()


def test_namespace_conformance_hard_gate():
    """The non-negotiable invariant for BOTH cases: every emitted attribute is a
    controlled key or an explicit new_attribute: flag — zero silent synonyms."""
    for case in CASES.values():
        emitted = _extract(case)
        assert attributes.nonconformant([a.attribute for a in emitted]) == []


def test_daniel_tan_confluence_staleness_and_escape_hatch():
    emitted = _extract(CASES["daniel_tan_confluence"])
    ga = [a for a in emitted if a.attribute == "confluence.ga_date"]
    # the real, re-baselined date is current (scope None) and lands in Q3 (Sep)
    real = [a for a in ga if a.scope is None]
    assert any("09" in a.value or "sep" in a.value.lower() for a in real), [a.value for a in ga]
    # the public/superseded June date is captured WITH a scope qualifier, not dropped
    junes = [a for a in ga if ("06" in a.value or "june" in a.value.lower())]
    assert junes, "must not drop the public June date"
    assert all(a.scope is not None for a in junes), "the June date must carry a scope (not current)"
    # the escape hatch fired for the out-of-vocab mismatch rate
    assert any(a.attribute.startswith(attributes.NEW_ATTRIBUTE_PREFIX) for a in emitted)


def test_exec_huddle_signal_vs_noise():
    emitted = _extract(CASES["exec_huddle_signal_vs_noise"])
    blob = _lower_values(emitted)
    # T12: pure social chatter is never an assertion
    for noise in ("f1", "verstappen", "lap 41", "overtake", "p7"):
        assert noise not in blob, f"social chatter leaked: {noise}"
    # chat-tier reliability floor — nothing emitted from chat outranks official tiers
    from house_harness.schema import SourceTier

    assert all(a.reliability == SourceTier.chat for a in emitted)
