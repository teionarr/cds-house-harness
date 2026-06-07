"""capture — a correction becomes a sourced, attributed, superseding Artifact.

Pins: the correction text is encoded, source_type is "board" (authoritative),
the id is deterministic, and supersedes is carried through.
"""

from __future__ import annotations

from house_harness.pipeline.feedback import capture
from house_harness.schema import ArtifactType, Feedback


def _feedback() -> Feedback:
    return Feedback(
        question="What is our current NPS?",
        correct_answer="62 for SEA-enterprise",
        provided_by="Maria Santos",
        supersedes=["old-source-1", "old-source-2"],
    )


def test_capture_encodes_correction():
    art = capture(_feedback())

    assert art.type is ArtifactType.doc
    assert "What is our current NPS?" in art.text
    assert "62 for SEA-enterprise" in art.text
    assert "Maria Santos" in art.text
    assert art.metadata["source_type"] == "board"
    assert art.metadata["provided_by"] == "Maria Santos"
    assert art.metadata["supersedes"] == "old-source-1,old-source-2"


def test_capture_id_is_deterministic():
    assert capture(_feedback()).id == capture(_feedback()).id


def test_capture_id_changes_with_input():
    other = Feedback(
        question="A different question?",
        correct_answer="62 for SEA-enterprise",
        provided_by="Maria Santos",
    )
    assert capture(_feedback()).id != capture(other).id
