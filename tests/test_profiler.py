"""Tests for the deterministic corpus profiler + the plan it feeds."""

# ruff: noqa: S101  — asserts are the test vocabulary here.
from __future__ import annotations

from house_harness.pipeline.profiler import plan_pipeline, profile_corpus
from house_harness.schema import Artifact, ArtifactType, ContextStrategy


def _artifacts() -> list[Artifact]:
    return [
        Artifact(
            id="a1",
            source="data/interviews/maria.md",
            type=ArtifactType.transcript,
            text="We grew a lot this quarter and shipped fast." * 10,
            metadata={"source_type": "interview", "as_of": "2026-04-15"},
        ),
        Artifact(
            id="a2",
            source="data/dashboards/april.html",
            type=ArtifactType.doc,
            text="NPS 47, churn 3%." * 10,
            metadata={"source_type": "dashboard", "as_of": "2026-04-21"},
        ),
        Artifact(
            id="a3",
            source="data/charts/funnel.jpeg",
            type=ArtifactType.doc,
            text="Funnel chart: top-of-funnel 1000, conversions 120.",
            metadata={"source_type": "chart", "vision_extracted": "true"},
        ),
    ]


def test_token_estimate_positive():
    profile = profile_corpus(_artifacts())
    assert profile.token_estimate > 0


def test_format_mix_counts():
    profile = profile_corpus(_artifacts())
    assert profile.format_mix == {"interview": 1, "dashboard": 1, "chart": 1}


def test_format_mix_falls_back_to_type():
    art = Artifact(id="x", source="s", type=ArtifactType.doc, text="hi", metadata={})
    profile = profile_corpus([art])
    assert profile.format_mix == {"doc": 1}


def test_entity_estimate_is_int():
    profile = profile_corpus(_artifacts())
    assert isinstance(profile.entity_estimate, int)
    assert profile.entity_estimate == 3


def test_has_images_true_with_vision_tag():
    profile = profile_corpus(_artifacts())
    assert profile.has_images is True


def test_has_images_false_without_vision():
    arts = [
        Artifact(
            id="a1",
            source="s",
            type=ArtifactType.transcript,
            text="text",
            metadata={"source_type": "interview"},
        )
    ]
    assert profile_corpus(arts).has_images is False


def test_date_span_days_computed():
    profile = profile_corpus(_artifacts())
    # 2026-04-15 .. 2026-04-21
    assert profile.date_span_days == 6


def test_date_span_none_with_fewer_than_two_dates():
    arts = [
        Artifact(
            id="a1",
            source="s",
            type=ArtifactType.doc,
            text="t",
            metadata={"as_of": "2026-04-15"},
        ),
        Artifact(id="a2", source="s2", type=ArtifactType.doc, text="t", metadata={}),
    ]
    assert profile_corpus(arts).date_span_days is None


def test_languages_default_en():
    assert profile_corpus(_artifacts()).languages == ["en"]


def test_languages_detects_portuguese():
    arts = [
        Artifact(
            id="a1",
            source="s",
            type=ArtifactType.chat,
            text="Eu não sei, obrigado.",
            metadata={},
        )
    ]
    assert "pt" in profile_corpus(arts).languages


def test_plan_pipeline_ontology_first_for_small_corpus():
    profile = profile_corpus(_artifacts())
    config = plan_pipeline(profile)
    assert config.context_strategy is ContextStrategy.ontology_first
