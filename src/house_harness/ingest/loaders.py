"""Multi-format loaders -> normalized Artifact records.

md/txt, pdf (pypdf), html (bs4), chat/email threads. Each loader stamps source
+ as-of date and runs text through the untrusted-content gate before storage.
Ingestion is failure-isolated: one bad file never kills the batch.

Re-ingest only on CHANGE (the moving-target requirement): `load_corpus` keeps a
manifest of {file_path -> content_hash} in the store (persisted on the volume).
On boot it ingests only files whose hash is new or changed and skips the rest, so
a cold start does NOT re-extract the whole corpus. Combined with idempotent
upsert (stable assertion_id), re-running ingestion is always safe and cheap; a
changed file supersedes its prior assertions, a removed file retires them.
"""

from __future__ import annotations

from collections.abc import Iterable

from house_harness.schema import Artifact, IngestFailure


def load_one(path: str) -> Iterable[Artifact]:
    """Dispatch by extension to the right loader. Images route to load_image
    (vision extraction). TODO: implement per-format."""
    raise NotImplementedError


def load_image(path: str) -> Artifact:
    """Extract a chart/figure via the vision model (config.llm seam), not OCR —
    charts are visual (axes, bars, legends), so a multimodal call reads them.

    Output is tagged vision-extracted + low confidence in metadata; on a tie with
    a text/PDF figure, the text source wins. Recovers facts that live only in
    images instead of leaving them as coverage gaps. TODO: send the image to a
    multimodal model and parse structured output via config/structured.py.
    """
    raise NotImplementedError


def load_corpus(paths: Iterable[str]) -> tuple[list[Artifact], list[IngestFailure]]:
    """Load a whole corpus with per-file isolation.

    A malformed PDF / bad encoding / unknown format is recorded as an
    IngestFailure and skipped — never propagated as a crash. Failures flow
    downstream as honest coverage gaps.
    """
    artifacts: list[Artifact] = []
    failures: list[IngestFailure] = []
    for path in paths:
        try:
            artifacts.extend(load_one(path))
        except Exception as exc:  # noqa: BLE001 — isolation is the point
            failures.append(IngestFailure(source=path, error=f"{type(exc).__name__}: {exc}"))
    return artifacts, failures
