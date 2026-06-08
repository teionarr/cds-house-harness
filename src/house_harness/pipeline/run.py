"""End-to-end pipeline orchestration: corpus dir -> ontology + harness on disk.

`run_pipeline` is the full build (CLI `house-harness run`): ingest -> extract ->
persist assertions + harness to SQLite -> emit `<COMPANY>.md` + `graph.json`.

`ingest_on_boot` is the moving-target path the server calls at startup: it hashes
the corpus and rebuilds ONLY when something changed (a cold boot on an unchanged
volume is a no-op), so the live service comes up fast and never double-counts.
True per-file incremental extraction is the documented next step; v1 rebuilds the
harness wholesale when any file changes (the charter/graph need the full set) and
skips entirely when nothing has.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from house_harness.ingest.loaders import load_corpus
from house_harness.pipeline import ontology
from house_harness.pipeline import store as _store
from house_harness.pipeline.harness import extract_harness, render_markdown
from house_harness.pipeline.health import assess_harness
from house_harness.schema import Assertion, HouseHarness

logger = logging.getLogger(__name__)


def _company() -> str:
    return os.environ.get("HOUSE_HARNESS_COMPANY", "HelixPay")


def _corpus_files(corpus_dir: str) -> list[str]:
    root = Path(corpus_dir)
    if not root.exists():
        return []
    return sorted(str(p) for p in root.rglob("*") if p.is_file())


def _hash(path: str) -> str:
    return hashlib.sha1(Path(path).read_bytes(), usedforsecurity=False).hexdigest()


def run_pipeline(corpus_dir: str = "data", out_dir: str = "out") -> dict:
    """Full build. Ingest -> extract -> persist -> emit artifacts. Returns a small
    summary (counts + output paths)."""
    if not logging.getLogger().handlers:  # surface progress when run from the CLI
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    paths = _corpus_files(corpus_dir)
    artifacts, failures = load_corpus(paths)
    logger.info(
        "ingested %d artifacts (%d failures) from %s", len(artifacts), len(failures), corpus_dir
    )

    harness, assertions = extract_harness(_company(), artifacts)

    conn = _store.connect()
    _store.save_assertions(conn, assertions.values())
    # Wholesale rebuild = `assertions` is the complete current ontology, so reconcile
    # the store to it: drop assertions + manifest rows from any RETRACTED source.
    pruned = _store.prune_assertions(conn, set(assertions))
    current_hashes = {p: _hash(p) for p in paths}
    _store.drop_manifest_entries(conn, _store.removed_files(conn, current_hashes))
    for p, h in current_hashes.items():
        _store.save_manifest_entry(conn, p, h)
    _store.save_harness(conn, harness)
    conn.close()
    if pruned:
        logger.info("pruned %d assertions from retracted sources", pruned)

    # The harness mirror: surface conflicts/blind-spots IN the artifact, routed to owners.
    _current, dissents = ontology.resolve(assertions)
    hh = assess_harness(harness, dissents, assertions)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"{harness.company.upper().replace(' ', '_')}.md"
    md_path.write_text(render_markdown(harness, hh))
    graph_path = out / "graph.json"
    graph_path.write_text(harness.taxonomy.model_dump_json(indent=2))

    summary = {
        "artifacts": len(artifacts),
        "failures": len(failures),
        "assertions": len(assertions),
        "targets": len(harness.targets),
        "guardrails": len(harness.guardrails),
        "entities": len(harness.taxonomy.nodes),
        "harness_md": str(md_path),
        "graph_json": str(graph_path),
    }
    logger.info("pipeline complete: %s", summary)
    return summary


def ingest_on_boot(corpus_dir: str = "data") -> bool:
    """Rebuild only if the corpus changed since the last run (or the store is empty).
    Returns True if it (re)built, False if it skipped. Safe to call every boot."""
    conn = _store.connect()
    have_data = bool(_store.load_harness(conn))
    current = {p: _hash(p) for p in _corpus_files(corpus_dir)}
    changed = _store.changed_files(conn, current)
    removed = _store.removed_files(conn, current)
    conn.close()
    if have_data and not changed and not removed:
        logger.info(
            "ingest-on-boot: no changes, %d files unchanged — skipping rebuild", len(current)
        )
        return False
    logger.info(
        "ingest-on-boot: %d changed/new, %d removed files — rebuilding harness",
        len(changed),
        len(removed),
    )
    run_pipeline(corpus_dir)
    return True


def load_serving_state() -> tuple[HouseHarness | None, dict[str, Assertion]]:
    """Load (harness, assertion_store) from SQLite for the query path. Returns
    (None, {}) if the ontology hasn't been built yet."""
    conn = _store.connect()
    harness = _store.load_harness(conn)
    assertions = _store.load_assertions(conn)
    conn.close()
    return harness, assertions
