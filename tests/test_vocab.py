"""Per-corpus vocabulary induction: the deterministic post-processor + the
install/active/domain accessors that make the engine corpus-agnostic. No model.
"""

# ruff: noqa: S101
from __future__ import annotations

import pytest

from house_harness.pipeline import attributes
from house_harness.pipeline.vocab import normalize_vocab


@pytest.fixture(autouse=True)
def _restore_vocab():
    """install_vocab mutates a module global — snapshot and restore so tests don't
    bleed into each other (or the rest of the suite)."""
    saved = attributes.domain_vocab()
    yield
    attributes.install_vocab(saved)


# ── deterministic normalization ───────────────────────────────────────────────


def test_normalize_snake_cases_and_dedupes_synonym_keys():
    raw = {"Revenue Quarter": "recognized rev", "revenue-quarter": "dup phrasing"}
    out = normalize_vocab(raw, kernel_keys=set())
    assert out == {"revenue_quarter": "recognized rev"}  # collapsed; first description wins


def test_normalize_drops_kernel_collisions_and_blanks():
    raw = {"reports_to": "manager", "nps": "score", "empty": "   "}
    out = normalize_vocab(raw, kernel_keys={"reports_to"})
    assert out == {"nps": "score"}  # kernel owns reports_to; blank description dropped


def test_normalize_output_is_sorted():
    out = normalize_vocab({"zeta": "z", "alpha": "a"}, kernel_keys=set())
    assert list(out) == ["alpha", "zeta"]


# ── install / active / domain ─────────────────────────────────────────────────


def test_install_replaces_domain_keeps_kernel():
    attributes.install_vocab({"mrr": "monthly recurring revenue"})
    active = attributes.active_vocab()
    assert "mrr" in active  # the induced key
    assert "reports_to" in active  # kernel always present
    assert "nps" not in active  # the bundled seed was replaced, not merged
    assert attributes.domain_vocab() == {"mrr": "monthly recurring revenue"}


def test_classify_grades_against_installed_vocab():
    attributes.install_vocab({"mrr": "monthly recurring revenue"})
    assert attributes.classify("mrr") == "known"
    assert attributes.classify("nps") == "violation"  # not in THIS corpus's namespace
    assert attributes.classify("new_attribute:foo") == "new"  # escape hatch survives


def test_default_vocab_is_the_bundled_seed():
    # Before any install, the active namespace is kernel + the bundled corpus's seed.
    assert "nps" in attributes.active_vocab()
    assert "reports_to" in attributes.active_vocab()
