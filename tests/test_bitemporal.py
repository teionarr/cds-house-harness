"""Bitemporal stamping: validity (`as_of`) and recording (`recorded_at`) are
separate axes. The deterministic mapper, not the model, sets them — so this runs
without ANTHROPIC_API_KEY.
"""

# ruff: noqa: S101
from __future__ import annotations

from house_harness.pipeline.harness import RawAssertion, _map_raw_assertion
from house_harness.schema import SourceTier


def _map(as_of, doc_as_of):
    ra = RawAssertion(subject="helixpay", attribute="nps", value="47", as_of=as_of)
    return _map_raw_assertion(ra, "weekly-2026-04", "nps was 47", SourceTier.official, doc_as_of)


def test_stated_validity_and_recording_are_distinct():
    a = _map(as_of="2026-03-31", doc_as_of="2026-04-21")
    assert a is not None
    assert a.as_of == "2026-03-31"  # when the fact was true
    assert a.recorded_at == "2026-04-21"  # when the doc recorded it — a different axis


def test_validity_falls_back_to_recording_but_recording_is_always_the_doc_date():
    a = _map(as_of=None, doc_as_of="2026-04-21")
    assert a is not None
    assert a.as_of == "2026-04-21"  # no stated validity -> best estimate is the record date
    assert a.recorded_at == "2026-04-21"  # recording is unconditionally the doc date
