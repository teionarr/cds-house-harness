"""SQLite persistence of record — the ONLY SQLite-aware code in the engine.

The resolution logic (`ontology.resolve/query`) stays pure over an in-memory
`dict[str, Assertion]` working view; this module is the thin layer that loads that
view at boot and saves it on upsert, so the service answers without re-reading the
corpus and re-ingestion is idempotent (one row per stable `assertion_id`). The
documented scale path (pgvector/Postgres) swaps only this layer — nothing above it
changes.

Four tables:
- `assertions(id, json)`     — the ontology spine, one row per assertion id.
- `harness(company, json)`   — the distilled House Harness (single logical row).
- `manifest(path, hash)`     — the re-ingest-on-change ledger: a cold boot ingests
                               only files whose content hash is new or changed.
- `vocab(key, description)`  — the per-corpus DOMAIN attribute namespace, induced at
                               extraction and pinned so re-ingests reuse it verbatim
                               and the serving process grades against the same keys.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from house_harness.schema import Assertion, HouseHarness

DEFAULT_DB = "sqlite:///./data/house_harness.db"


def db_path(database_url: str | None = None) -> str:
    """Parse a `sqlite://` URL into a filesystem path. Accepts the SQLAlchemy-style
    forms used in `.env`/`fly.toml`: `sqlite:///relative.db` and
    `sqlite:////abs/path.db`. A bare path is returned as-is."""
    url = database_url or os.environ.get("DATABASE_URL", DEFAULT_DB)
    if url.startswith("sqlite:////"):  # four slashes -> absolute
        return "/" + url[len("sqlite:////") :]
    if url.startswith("sqlite:///"):  # three slashes -> relative
        return url[len("sqlite:///") :]
    if url.startswith("sqlite://"):
        return url[len("sqlite://") :]
    return url


def connect(database_url: str | None = None) -> sqlite3.Connection:
    """Open (creating parent dirs + tables if needed) the assertion store."""
    path = db_path(database_url)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS assertions (id TEXT PRIMARY KEY, json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS harness    (company TEXT PRIMARY KEY, json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS manifest   (path TEXT PRIMARY KEY, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS vocab      (key TEXT PRIMARY KEY, description TEXT NOT NULL);
        """
    )
    return conn


# ── assertions ────────────────────────────────────────────────────────────────


def save_assertions(conn: sqlite3.Connection, assertions: Iterable[Assertion]) -> int:
    """Idempotent persist: INSERT OR REPLACE by stable id (mirrors the in-memory
    upsert). Returns the number of rows written."""
    rows = [(a.id, a.model_dump_json()) for a in assertions]
    conn.executemany("INSERT OR REPLACE INTO assertions (id, json) VALUES (?, ?)", rows)
    conn.commit()
    return len(rows)


def load_assertions(conn: sqlite3.Connection) -> dict[str, Assertion]:
    """Load the full working view keyed by id — what resolve/query operate over."""
    cur = conn.execute("SELECT json FROM assertions")
    return {a.id: a for a in (Assertion.model_validate_json(row[0]) for row in cur.fetchall())}


def prune_assertions(conn: sqlite3.Connection, keep_ids: set[str]) -> int:
    """Delete assertion rows whose id is NOT in keep_ids, and return how many.

    The wholesale rebuild re-extracts the COMPLETE ontology of the current corpus,
    so `keep_ids` is authoritative: anything else is an orphan from a RETRACTED
    source (a file pulled from the corpus). Without this, INSERT-OR-REPLACE leaves a
    removed source's assertions live forever — a silent moving-target hole."""
    stale = [row[0] for row in conn.execute("SELECT id FROM assertions") if row[0] not in keep_ids]
    conn.executemany("DELETE FROM assertions WHERE id = ?", [(i,) for i in stale])
    conn.commit()
    return len(stale)


# ── harness ─────────────────────────────────────────────────────────────────--


def save_harness(conn: sqlite3.Connection, harness: HouseHarness) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO harness (company, json) VALUES (?, ?)",
        (harness.company, harness.model_dump_json()),
    )
    conn.commit()


def load_harness(conn: sqlite3.Connection) -> HouseHarness | None:
    cur = conn.execute("SELECT json FROM harness LIMIT 1")
    row = cur.fetchone()
    return HouseHarness.model_validate_json(row[0]) if row else None


# ── pinned domain vocabulary ──────────────────────────────────────────────────


def save_vocab(conn: sqlite3.Connection, domain: dict[str, str]) -> None:
    """Pin the corpus's induced DOMAIN vocab (replace-all). Empty is valid — it means
    'kernel only', e.g. induction was skipped/failed."""
    conn.execute("DELETE FROM vocab")
    conn.executemany(
        "INSERT INTO vocab (key, description) VALUES (?, ?)", list(domain.items())
    )
    conn.commit()


def load_vocab(conn: sqlite3.Connection) -> dict[str, str]:
    """Load the pinned DOMAIN vocab; empty dict if none has been induced yet."""
    return {key: desc for key, desc in conn.execute("SELECT key, description FROM vocab")}


# ── re-ingest-on-change manifest (the moving-target requirement) ───────────────


def load_manifest(conn: sqlite3.Connection) -> dict[str, str]:
    return {path: h for path, h in conn.execute("SELECT path, hash FROM manifest")}


def save_manifest_entry(conn: sqlite3.Connection, path: str, content_hash: str) -> None:
    conn.execute("INSERT OR REPLACE INTO manifest (path, hash) VALUES (?, ?)", (path, content_hash))
    conn.commit()


def drop_manifest_entries(conn: sqlite3.Connection, paths: Iterable[str]) -> None:
    """Forget manifest rows for files that are gone — so the ledger tracks the corpus
    as it actually is and a re-added file is re-ingested rather than wrongly skipped."""
    conn.executemany("DELETE FROM manifest WHERE path = ?", [(p,) for p in paths])
    conn.commit()


def changed_files(conn: sqlite3.Connection, current: dict[str, str]) -> list[str]:
    """Given {path -> content_hash} for the corpus on disk, return the paths whose
    hash is new or changed vs the manifest — the only files a boot needs to ingest."""
    prior = load_manifest(conn)
    return [p for p, h in current.items() if prior.get(p) != h]


def removed_files(conn: sqlite3.Connection, current: dict[str, str]) -> list[str]:
    """Manifest paths no longer present on disk — a RETRACTED source. A deletion is a
    corpus change too: it must trigger a rebuild (so the source's facts stop being
    served) and prune the manifest, not just edits/additions via `changed_files`."""
    return [p for p in load_manifest(conn) if p not in current]
