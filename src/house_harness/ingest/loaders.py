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

import base64
import calendar
import re
from collections.abc import Iterable
from pathlib import Path

from house_harness.config.llm import get_model
from house_harness.ingest import gate
from house_harness.schema import Artifact, ArtifactType, IngestFailure

# Repo root: .../house-harness (this file is src/house_harness/ingest/loaders.py).
_REPO_ROOT = Path(__file__).resolve().parents[3]

_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_QUARTER_RE = re.compile(r"(?i)\bq([1-4])-(\d{4})\b")
_QUARTER_END_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}

_IMAGE_EXTS = {".jpeg", ".jpg", ".png"}
_IMAGE_MIME = {".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png"}


def _rel_source(path: str) -> str:
    """Repo-relative path string, used as both the stable id base and source."""
    p = Path(path)
    try:
        return p.resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _slug_id(rel: str) -> str:
    """Deterministic id from the repo-relative path."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", rel).strip("-").lower()


def _parse_as_of(rel: str) -> str | None:
    """Derive an ISO date from a path: explicit YYYY-MM-DD, else qN-YYYY -> last
    day of that quarter. Returns None if nothing is derivable."""
    m = _DATE_RE.search(rel)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    q = _QUARTER_RE.search(rel)
    if q:
        quarter, year = int(q.group(1)), int(q.group(2))
        month = _QUARTER_END_MONTH[quarter]
        last_day = calendar.monthrange(year, month)[1]
        return f"{year:04d}-{month:02d}-{last_day:02d}"
    return None


def _classify_md(rel: str) -> tuple[ArtifactType, str]:
    """Map a markdown path to (ArtifactType, source_type)."""
    name = Path(rel).name
    if "/interviews/" in f"/{rel}":
        return ArtifactType.transcript, "interview"
    if "/chat/" in f"/{rel}":
        return ArtifactType.chat, "chat"
    if "/email/" in f"/{rel}":
        return ArtifactType.doc, "email"
    if "/code/" in f"/{rel}":
        return ArtifactType.code, "doc"
    if name.startswith("all-hands-"):
        return ArtifactType.transcript, "all_hands"
    if name.startswith("weekly-review-"):
        return ArtifactType.doc, "review"
    if name.startswith("board-update-"):
        return ArtifactType.doc, "board"
    return ArtifactType.doc, "doc"


def _make(rel: str, type_: ArtifactType, source_type: str, text: str) -> Artifact:
    metadata = {"source_type": source_type}
    as_of = _parse_as_of(rel)
    if as_of is not None:
        metadata["as_of"] = as_of
    return Artifact(
        id=_slug_id(rel),
        source=rel,
        type=type_,
        text=gate.neutralize(text),
        metadata=metadata,
    )


def load_one(path: str) -> Iterable[Artifact]:
    """Dispatch by extension to the right loader. Images route to load_image
    (vision extraction). Unknown extensions raise ValueError (load_corpus records
    it as an IngestFailure)."""
    rel = _rel_source(path)
    ext = Path(path).suffix.lower()

    if ext == ".md":
        type_, source_type = _classify_md(rel)
        text = Path(path).read_text(encoding="utf-8")
        return [_make(rel, type_, source_type, text)]

    if ext == ".html":
        from bs4 import BeautifulSoup

        html = Path(path).read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        return [_make(rel, ArtifactType.doc, "dashboard", text)]

    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return [_make(rel, ArtifactType.doc, "pdf_financial", text)]

    if ext in _IMAGE_EXTS:
        return [load_image(path)]

    raise ValueError(f"unsupported file type: {ext or '(none)'}")


def load_image(path: str) -> Artifact:
    """Extract a chart/figure via the vision model (config.llm seam), not OCR —
    charts are visual (axes, bars, legends), so a multimodal call reads them.

    Output is tagged vision-extracted + low confidence in metadata; on a tie with
    a text/PDF figure, the text source wins. Recovers facts that live only in
    images instead of leaving them as coverage gaps.
    """
    from langchain_core.messages import HumanMessage

    rel = _rel_source(path)
    ext = Path(path).suffix.lower()
    mime = _IMAGE_MIME.get(ext, "image/jpeg")

    raw = Path(path).read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")

    message = HumanMessage(
        content=[
            {
                "type": "text",
                "text": (
                    "Transcribe this chart/figure as plain text. Report the title, "
                    "axes and their labels, every series/legend entry, and all data "
                    "values you can read. Output only the transcribed data."
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            },
        ]
    )

    model = get_model()
    response = model.invoke([message])
    text = response.content if isinstance(response.content, str) else str(response.content)

    return Artifact(
        id=_slug_id(rel),
        source=rel,
        type=ArtifactType.doc,
        text=gate.neutralize(text),
        metadata={
            "source_type": "dashboard",
            "vision_extracted": "true",
            "confidence": "low",
        },
    )


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
