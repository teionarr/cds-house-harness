"""Offline tests for the entailment judge — no real model calls.

`judge_entailment` is exercised with an injected fake `_judge` so the suite stays
fast and deterministic; the default LLM path is never reached here.
"""

from __future__ import annotations

from house_harness.schema import Claim
from house_harness.synthesis.verify import (
    _load_artifact_texts,
    _parse_span,
    judge_entailment,
)


def test_parse_span_with_range():
    assert _parse_span("doc#10-40") == ("doc", 10, 40)


def test_parse_span_without_range():
    assert _parse_span("doc") == ("doc", None, None)


def test_parse_span_malformed_range_falls_back_to_whole():
    # A `#` with a non-integer span -> treat as whole-artifact.
    assert _parse_span("doc#abc") == ("doc", None, None)


def test_judge_sets_verified_and_does_not_mutate(tmp_path):
    # Corpus with one artifact whose span [0:2] is "47". The artifact id is the
    # loader's path slug, so derive it from the corpus rather than guessing.
    (tmp_path / "weekly-review-2026-04-21.md").write_text("47 is the aggregate NPS")
    (artifact_id,) = _load_artifact_texts(str(tmp_path)).keys()

    supported = Claim(text="nps is 47", sources=[f"{artifact_id}#0-2"])
    unsupported = Claim(text="nps is 62", sources=[f"{artifact_id}#0-2"])

    # Fake judge: supported iff the span text appears in the claim text.
    fake = lambda span, claim: span in claim  # noqa: E731

    result = judge_entailment([supported, unsupported], corpus_dir=str(tmp_path), _judge=fake)

    assert result[0].verified is True
    assert result[1].verified is False
    # Inputs untouched (new objects returned).
    assert supported.verified is None
    assert unsupported.verified is None


def test_unknown_artifact_resolves_to_empty_span(tmp_path):
    seen: list[str] = []

    def fake(span: str, claim: str) -> bool:
        seen.append(span)
        return False

    claim = Claim(text="anything", sources=["does-not-exist#0-5"])
    result = judge_entailment([claim], corpus_dir=str(tmp_path), _judge=fake)

    assert result[0].verified is False
    assert seen == [""]  # unknown artifact -> span text ""


def test_missing_corpus_dir_does_not_crash(tmp_path):
    seen: list[str] = []

    def fake(span: str, claim: str) -> bool:
        seen.append(span)
        return False

    missing = tmp_path / "no-such-dir"
    claim = Claim(text="anything", sources=["whatever#0-5"])
    result = judge_entailment([claim], corpus_dir=str(missing), _judge=fake)

    assert result[0].verified is False
    assert seen == [""]
