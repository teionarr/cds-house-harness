"""SQLite persistence of record — round-trip + idempotency + the change manifest.

In-memory DB (`:memory:`) keeps it fast and DB-free for the working logic; the
spine (resolve/query) never touches this layer.
"""

from __future__ import annotations

from house_harness.pipeline import store
from house_harness.schema import (
    Assertion,
    CompanyGraph,
    HouseHarness,
    SourceSpan,
    SourceTier,
)


def _conn():
    return store.connect("sqlite://:memory:")


def _assertion(id_: str = "a1", value: str = "47") -> Assertion:
    return Assertion(
        id=id_,
        subject="helixpay",
        attribute="nps",
        value=value,
        scope="aggregate",
        as_of="2026-04-21",
        source=SourceSpan(artifact_id="weekly-review-2026-04-21", start=0, end=10),
        reliability=SourceTier.official,
    )


def test_db_path_parses_sqlite_urls():
    assert store.db_path("sqlite:///./data/x.db") == "./data/x.db"
    assert store.db_path("sqlite:////data/x.db") == "/data/x.db"
    assert store.db_path("sqlite://:memory:") == ":memory:"


def test_assertions_roundtrip_and_idempotent():
    conn = _conn()
    store.save_assertions(conn, [_assertion(), _assertion(id_="a2", value="62")])
    loaded = store.load_assertions(conn)
    assert set(loaded) == {"a1", "a2"}
    assert loaded["a1"].value == "47"
    # re-saving the same id replaces in place (no duplicate row)
    store.save_assertions(conn, [_assertion(value="48")])
    loaded = store.load_assertions(conn)
    assert len(loaded) == 2
    assert loaded["a1"].value == "48"


def test_harness_roundtrip():
    conn = _conn()
    assert store.load_harness(conn) is None
    h = HouseHarness(
        company="HelixPay",
        charter="agent-native payments",
        taxonomy=CompanyGraph(nodes=["a"], edges=[]),
    )
    store.save_harness(conn, h)
    got = store.load_harness(conn)
    assert got is not None and got.company == "HelixPay"
    assert got.charter == "agent-native payments"


def test_manifest_detects_changed_files():
    conn = _conn()
    store.save_manifest_entry(conn, "data/a.md", "hash1")
    store.save_manifest_entry(conn, "data/b.md", "hashB")
    current = {"data/a.md": "hash1", "data/b.md": "CHANGED", "data/c.md": "new"}
    changed = store.changed_files(conn, current)
    assert set(changed) == {"data/b.md", "data/c.md"}  # unchanged a.md is skipped
