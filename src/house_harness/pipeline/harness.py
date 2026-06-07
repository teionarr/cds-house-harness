"""The extraction engine: arbitrary documents -> House Harness.

Automated audit (entity/alias resolution, contradiction + staleness detection)
-> taxonomy + ontology graph, then distills charter, targets, and guardrails/
authorities. Emits HELIXPAY.md / <COMPANY>.md and graph.json.

CONTRACT (the spine depends on it): every assertion this emits must map its
`attribute` into the controlled namespace. Before upsert, run
`attributes.nonconformant([a.attribute for a in assertions])`; any 'violation'
is a silent synonym that disables resolve()'s grouping — drop + log it, never
store it. Out-of-vocab facts that are real get an explicit `new_attribute:<slug>`
flag for human review, not a guessed synonym. The extraction eval gates on this
(zero unflagged violations) and is regression-tested against
`tests/fixtures/extraction_golden.json`.
"""

from __future__ import annotations

from collections.abc import Iterable

from house_harness.schema import Artifact, HouseHarness


def extract_harness(company: str, artifacts: Iterable[Artifact]) -> HouseHarness:
    """Distill the defining-artifact library from a corpus. Emit assertions whose
    attributes are namespace-conformant (`attributes.nonconformant` must return
    empty), or `new_attribute:`-flagged. TODO: implement."""
    raise NotImplementedError
