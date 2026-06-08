"""Global entity-surface canonicalization: collapse casing/slug fragments of one
entity (people AND products/accounts), while keeping anti-aliases distinct.
"""

# ruff: noqa: S101
from __future__ import annotations

import pytest

from house_harness.pipeline import harness, names


@pytest.fixture(autouse=True)
def _registry():
    saved = harness._REGISTRY
    harness._REGISTRY = names.build_registry(
        "Org chart: Daniel Tan, Maria Silva, Maria Santos, Sofia Almeida"
    )
    yield
    harness._REGISTRY = saved


def test_merges_casing_and_slug_fragments_via_roster():
    m = harness._subject_canon_map({"Daniel Tan", "daniel_tan", "daniel.tan", "daniel tan"})
    assert m["daniel_tan"] == "Daniel Tan"
    assert m["daniel.tan"] == "Daniel Tan"
    assert m["daniel tan"] == "Daniel Tan"


def test_non_person_picks_best_cased_existing_form():
    m = harness._subject_canon_map({"Cosmos Hotels", "cosmos_hotels", "cosmos hotels"})
    assert m["cosmos_hotels"] == "Cosmos Hotels"
    assert m["cosmos hotels"] == "Cosmos Hotels"
    assert "Cosmos Hotels" not in m  # the representative maps to itself -> omitted


def test_antialiases_never_merge():
    m = harness._subject_canon_map({"Maria Silva", "Maria Santos", "maria_silva", "maria_santos"})
    assert m["maria_silva"] == "Maria Silva"
    assert m["maria_santos"] == "Maria Santos"
    assert "Maria Silva" not in m and "Maria Santos" not in m  # not merged into each other


def test_lone_roster_slug_resolves_without_spaced_form_present():
    m = harness._subject_canon_map({"sofia_almeida"})
    assert m["sofia_almeida"] == "Sofia Almeida"
