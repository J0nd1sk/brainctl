"""Interference control: superseded facts stop intruding, the latest value wins.

Covers migration 087 (valid_from / valid_to), the supersede write path,
retrieval-time suppression in cmd_search, and the recency tie-break.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import agentmemory._impl as _impl
from agentmemory.lib import validity
from tests.bench.memory_quality import bench_brain

REPO_ROOT = Path(__file__).resolve().parent.parent
INIT_SCHEMA = REPO_ROOT / "src" / "agentmemory" / "db" / "init_schema.sql"
MIGRATION_087 = REPO_ROOT / "db" / "migrations" / "087_memory_validity.sql"


def _iso(days_ago: float = 0.0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


@pytest.fixture
def db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "brain.db"))
    conn.row_factory = sqlite3.Row
    conn.executescript(INIT_SCHEMA.read_text())
    conn.execute("INSERT INTO agents (id, display_name, agent_type) VALUES ('a', 'a', 'test')")
    conn.commit()
    yield conn
    conn.close()


def _add(conn, content, *, days_ago=0.0, supersedes=None, retired=False):
    ts = _iso(days_ago)
    cur = conn.execute(
        "INSERT INTO memories (agent_id, category, content, supersedes_id, created_at, updated_at, retired_at) "
        "VALUES ('a', 'environment', ?, ?, ?, ?, ?)",
        (content, supersedes, ts, ts, ts if retired else None),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_init_schema_has_validity_columns(db):
    assert validity.has_validity_columns(db)
    idx = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"idx_memories_supersedes", "idx_memories_valid_to"} <= idx


def test_migration_087_backfills_legacy_links(tmp_path):
    """A pre-087 DB: the link exists, the old row is active, valid_to is set from the successor."""
    conn = sqlite3.connect(str(tmp_path / "old.db"))
    conn.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY, content TEXT, supersedes_id INTEGER, "
                 "created_at TEXT, retired_at TEXT)")
    conn.execute("INSERT INTO memories VALUES (1, 'MySQL', NULL, '2026-01-01T00:00:00Z', NULL)")
    conn.execute("INSERT INTO memories VALUES (2, 'Postgres', 1, '2026-02-01T00:00:00Z', NULL)")
    conn.execute("INSERT INTO memories VALUES (3, 'orphan', NULL, '2026-01-01T00:00:00Z', NULL)")
    # successor retired: predecessor is not backfilled
    conn.execute("INSERT INTO memories VALUES (4, 'x', NULL, '2026-01-01T00:00:00Z', NULL)")
    conn.execute("INSERT INTO memories VALUES (5, 'y', 4, '2026-03-01T00:00:00Z', '2026-03-02T00:00:00Z')")
    conn.executescript(MIGRATION_087.read_text())
    rows = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT id, valid_to, retired_at FROM memories")}
    assert rows[1] == ("2026-02-01T00:00:00Z", None)   # interval closed, not retired
    assert rows[2][0] is None and rows[3][0] is None and rows[4][0] is None
    conn.close()


# ---------------------------------------------------------------------------
# Write side
# ---------------------------------------------------------------------------

def test_close_superseded_sets_valid_to_and_retires(db):
    old = _add(db, "The API deploy target is Heroku", days_ago=30)
    new = _add(db, "The API deploy target is Render", supersedes=old)
    out = validity.close_superseded(db, old, new)
    db.commit()
    assert out["closed"] and out["retired"] and out["valid_to"]
    row = db.execute("SELECT valid_to, retired_at FROM memories WHERE id=?", (old,)).fetchone()
    assert row["valid_to"] == out["valid_to"] and row["retired_at"] == out["valid_to"]
    # Idempotent: a second close keeps the first timestamps.
    validity.close_superseded(db, old, new, now="2099-01-01T00:00:00Z")
    row2 = db.execute("SELECT valid_to, retired_at FROM memories WHERE id=?", (old,)).fetchone()
    assert tuple(row2) == tuple(row)


def test_close_superseded_ignores_self_and_missing(db):
    mid = _add(db, "fact")
    assert validity.close_superseded(db, mid, mid)["closed"] is False
    assert validity.close_superseded(db, None, mid)["closed"] is False
    assert validity.close_superseded(db, 999999, mid)["closed"] is False
    assert db.execute("SELECT retired_at FROM memories WHERE id=?", (mid,)).fetchone()[0] is None


def test_version_chain_walks_both_directions(db):
    a = _add(db, "v1", days_ago=60)
    b = _add(db, "v2", days_ago=30, supersedes=a)
    c = _add(db, "v3", supersedes=b)
    validity.close_superseded(db, a, b)
    validity.close_superseded(db, b, c)
    db.commit()
    for start in (a, b, c):
        chain = validity.version_chain(db, start)
        assert [v["id"] for v in chain] == [a, b, c]
        assert [v["current"] for v in chain] == [False, False, True]


# ---------------------------------------------------------------------------
# Read side: suppression
# ---------------------------------------------------------------------------

def test_superseded_among_rules(db):
    legacy_old = _add(db, "legacy old", days_ago=10)
    _add(db, "legacy new", supersedes=legacy_old)                 # rule 2: active successor
    expired = _add(db, "expired")
    db.execute("UPDATE memories SET valid_to=? WHERE id=?", (_iso(1), expired))       # rule 1
    future = _add(db, "valid until next week")
    db.execute("UPDATE memories SET valid_to=? WHERE id=?", (_iso(-7), future))
    agm_loser = _add(db, "agm loser")
    agm_winner = _add(db, "agm winner")
    db.execute("INSERT INTO knowledge_edges (source_table, source_id, target_table, target_id, relation_type) "
               "VALUES ('memories', ?, 'memories', ?, 'supersedes')", (agm_winner, agm_loser))  # rule 3
    revived = _add(db, "successor was retired", days_ago=5)
    _add(db, "retired successor", supersedes=revived, retired=True)
    plain = _add(db, "unrelated")
    db.commit()
    got = validity.superseded_among(db, [legacy_old, expired, future, agm_loser, agm_winner, revived, plain])
    assert got == {legacy_old, expired, agm_loser}


def test_supersede_cli_path_retires_and_search_returns_latest():
    with bench_brain() as brain:
        old = brain.add_cli("The primary datastore is MySQL", "decision")["memory_id"]
        brain.backdate(old, 30)
        resp = brain.add_cli("The primary datastore is Postgres", "decision", supersedes=old)
        new = resp["memory_id"]
        assert resp["superseded"]["id"] == old and resp["superseded"]["retired"] is True
        assert brain.active_ids([old, new]) == {old: False, new: True}
        ranked = [r["id"] for r in brain.ranked_memories(brain.search("What is the primary datastore?"))]
        assert ranked[0] == new and old not in ranked


def test_search_drops_legacy_superseded_candidate_unless_asked():
    """A supersedes link with the old row still active (pre-087 data) is suppressed at search time."""
    with bench_brain() as brain:
        old = brain.add_cli("Continuous integration runs on Travis", "environment")["memory_id"]
        new = brain.add_cli("Continuous integration runs on Buildkite", "environment")["memory_id"]
        brain.backdate(old, 30)
        conn = brain._conn()
        conn.execute("UPDATE memories SET supersedes_id=? WHERE id=?", (old, new))
        conn.commit()
        conn.close()
        payload = brain.search("Which continuous integration system do we use?")
        ids = [r["id"] for r in brain.ranked_memories(payload)]
        assert new in ids and old not in ids

        import types
        args = types.SimpleNamespace(
            query="Which continuous integration system do we use?", limit=10, tables="memories",
            no_recency=False, no_graph=True, budget=None, min_salience=None, mmr=False,
            mmr_lambda=0.7, explore=False, profile=None, pagerank_boost=0.0, quantum=False,
            benchmark=False, agent="bench-agent", format="json", oneline=False, verbose=False,
            output="return", include_superseded=True,
        )
        out = _impl.cmd_search(args)
        assert old in [r["id"] for r in out["memories"]]


def test_memory_replace_closes_validity_interval():
    with bench_brain() as brain:
        old = brain.add_cli("Application logs are retained for 14 days", "environment")["memory_id"]
        brain.replace_cli(old, "Application logs are retained for 30 days", "environment")
        conn = brain._conn()
        row = conn.execute("SELECT valid_to, retired_at FROM memories WHERE id=?", (old,)).fetchone()
        conn.close()
        assert row["valid_to"] is not None and row["retired_at"] is not None


# ---------------------------------------------------------------------------
# Tie-break and keyword-only scoring
# ---------------------------------------------------------------------------

def test_sort_ranked_breaks_exact_ties_by_recency():
    rows = [
        {"id": 1, "final_score": 0.5, "created_at": _iso(60)},
        {"id": 2, "final_score": 0.9, "created_at": _iso(90)},
        {"id": 3, "final_score": 0.5, "created_at": _iso(1)},
    ]
    assert [r["id"] for r in _impl._sort_ranked(rows)] == [2, 3, 1]


def test_sort_ranked_keeps_order_when_timestamps_uniform():
    """A burst-ingested corpus (seconds apart) keeps insertion order on ties."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [{"id": i, "final_score": 0.5,
             "created_at": (base + timedelta(seconds=i)).isoformat().replace("+00:00", "Z")}
            for i in range(1, 5)]
    assert [r["id"] for r in _impl._sort_ranked(rows)] == [1, 2, 3, 4]


def test_rrf_fuse_tie_prefers_newer():
    old = {"id": 1, "created_at": _iso(60)}
    new = {"id": 2, "created_at": _iso(1)}
    # Same rank in different lists -> identical RRF scores.
    fused = _impl._rrf_fuse([old], [new])
    assert [r["id"] for r in fused] == [2, 1]


def test_keyword_only_scores_preserve_bm25_order_and_ties():
    rows = [{"id": 1, "fts_rank": -8.0}, {"id": 2, "fts_rank": -4.0}, {"id": 3, "fts_rank": -4.0}]
    scored = _impl._keyword_only_scores(rows)
    assert [r["rrf_score"] for r in scored] == [8.0, 4.0, 4.0]
    assert [r["keyword_similarity"] for r in scored] == [1.0, 0.5, 0.5]
    assert all(r["source"] == "keyword" for r in scored)
    assert _impl._keyword_only_scores([{"id": 9}])[0]["rrf_score"] == 1.0


def test_naive_readd_latest_wins_on_exact_bm25_tie():
    """No supersede link: identical-shape versions tie on BM25; the newer one ranks first."""
    with bench_brain() as brain:
        old = brain.add_cli("The backend runs on Python 3.9", "environment")["memory_id"]
        new = brain.add_cli("The backend runs on Python 3.12", "environment")["memory_id"]
        brain.backdate(old, 60)
        brain.backdate(new, 1)
        ranked = brain.ranked_memories(brain.search("What Python version does the backend run on?"))
        assert ranked[0]["id"] == new
