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


def test_migration_087_adds_columns_without_touching_rows(tmp_path):
    """A pre-087 DB with a legacy link: columns appear, nothing is closed or retired.

    Whether a legacy predecessor may be suppressed depends on its PII, so
    that decision is left to search time (see test_search_* below).
    """
    conn = sqlite3.connect(str(tmp_path / "old.db"))
    conn.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY, content TEXT, supersedes_id INTEGER, "
                 "created_at TEXT, retired_at TEXT)")
    conn.execute("INSERT INTO memories VALUES (1, 'MySQL', NULL, '2026-01-01T00:00:00Z', NULL)")
    conn.execute("INSERT INTO memories VALUES (2, 'Postgres', 1, '2026-02-01T00:00:00Z', NULL)")
    conn.executescript(MIGRATION_087.read_text())
    rows = conn.execute("SELECT id, valid_from, valid_to, retired_at FROM memories ORDER BY id").fetchall()
    assert rows == [(1, None, None, None), (2, None, None, None)]
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


# ---------------------------------------------------------------------------
# PII-tier-aware supersede (memory-poisoning defence)
# ---------------------------------------------------------------------------

def _entrench(brain, memory_id, temporal_class="medium"):
    """Make a memory ENTRENCHED (medium) or CRYSTALLIZED (long): strong Beta, max recalls, old."""
    brain.backdate(memory_id, 120)
    conn = brain._conn()
    conn.execute("UPDATE memories SET alpha=30, beta=1, recalled_count=50, temporal_class=? WHERE id=?",
                 (temporal_class, memory_id))
    conn.commit()
    conn.close()


def _row(brain, memory_id):
    conn = brain._conn()
    try:
        return dict(conn.execute(
            "SELECT retired_at, valid_from, valid_to, supersedes_id FROM memories WHERE id=?",
            (memory_id,)).fetchone())
    finally:
        conn.close()


def test_supersede_low_pii_incumbent_is_retired():
    with bench_brain() as brain:
        old = brain.add_cli("The default git branch is master", "convention")["memory_id"]
        resp = brain.add_cli("The default git branch is main", "convention", supersedes=old)
        assert resp["pii_gate"]["incumbent_tier"] in ("OPEN", "ESTABLISHED")
        assert resp["pii_gate"]["incumbent_retired"] is True
        assert resp["superseded"]["protected"] is False
        assert _row(brain, old)["retired_at"] is not None
        assert _row(brain, resp["memory_id"])["valid_from"] is not None


@pytest.mark.parametrize("temporal_class,tier", [("medium", "ENTRENCHED"), ("long", "CRYSTALLIZED")])
def test_supersede_entrenched_incumbent_stays_active_and_searchable(temporal_class, tier):
    """One "correction" must not erase a crystallized fact: it stays in competition."""
    with bench_brain() as brain:
        old = brain.add_cli("The primary datastore is MySQL", "decision")["memory_id"]
        _entrench(brain, old, temporal_class)
        resp = brain.add_cli("The primary datastore is Postgres", "decision", supersedes=old)
        new = resp["memory_id"]
        assert resp["pii_gate"]["incumbent_tier"] == tier
        assert resp["pii_gate"]["incumbent_retired"] is False
        assert resp["pii_gate"]["alpha_floor"] > 1          # symmetric prior still applied
        assert resp["superseded"] == {"id": old, "retired": False, "valid_to": None,
                                      "protected": True, "incumbent_tier": tier}
        old_row, new_row = _row(brain, old), _row(brain, new)
        assert old_row["retired_at"] is None and old_row["valid_to"] is None
        assert new_row["supersedes_id"] == old and new_row["valid_from"] is not None
        ids = [r["id"] for r in brain.ranked_memories(brain.search("What is the primary datastore?"))]
        assert old in ids and new in ids


def test_mcp_supersede_is_tier_aware():
    with bench_brain(with_mcp=True) as brain:
        weak = brain.add_mcp("The team offsite will be held in Lisbon", "project")["memory_id"]
        r1 = brain.add_mcp("The team offsite will be held in Porto", "project", supersedes=weak)
        assert r1["pii_gate"]["incumbent_retired"] is True
        assert _row(brain, weak)["retired_at"] is not None

        strong = brain.add_mcp("Dana prefers Slack for urgent questions", "preference")["memory_id"]
        _entrench(brain, strong)
        r2 = brain.add_mcp("Dana prefers phone calls for urgent questions", "preference", supersedes=strong)
        assert r2["pii_gate"]["incumbent_tier"] == "ENTRENCHED"
        assert r2["pii_gate"]["incumbent_retired"] is False
        assert r2["superseded"]["protected"] is True
        assert _row(brain, strong)["retired_at"] is None
        assert _row(brain, r2["memory_id"])["valid_from"] is not None


def test_memory_replace_retires_even_a_high_pii_incumbent():
    """`memory replace` is an explicit user override, not subject to the PII tier rule."""
    with bench_brain() as brain:
        old = brain.add_cli("The public API rate limit is 60 requests per minute", "integration")["memory_id"]
        _entrench(brain, old, "long")
        brain.replace_cli(old, "The public API rate limit is 120 requests per minute", "integration")
        row = _row(brain, old)
        assert row["retired_at"] is not None and row["valid_to"] is not None


def test_search_does_not_suppress_entrenched_legacy_link():
    """Search-time rule matches the write rule: a link alone never hides an ENTRENCHED memory."""
    with bench_brain() as brain:
        old = brain.add_cli("Continuous integration runs on Travis", "environment")["memory_id"]
        new = brain.add_cli("Continuous integration runs on Buildkite", "environment")["memory_id"]
        _entrench(brain, old)
        conn = brain._conn()
        conn.execute("UPDATE memories SET supersedes_id=? WHERE id=?", (old, new))
        conn.commit()
        conn.close()
        ids = [r["id"] for r in brain.ranked_memories(
            brain.search("Which continuous integration system do we use?"))]
        assert old in ids and new in ids


def test_superseded_among_protect_exempts_links_but_not_closed_intervals(db):
    linked = _add(db, "linked", days_ago=10)
    _add(db, "successor", supersedes=linked)
    closed = _add(db, "closed")
    db.execute("UPDATE memories SET valid_to=? WHERE id=?", (_iso(1), closed))
    db.commit()
    assert validity.superseded_among(db, [linked, closed]) == {linked, closed}
    assert validity.superseded_among(db, [linked, closed], protect=lambda _mid: True) == {closed}


def test_incumbent_protected_threshold():
    assert validity.incumbent_protected(0.40) and validity.incumbent_protected(0.9)
    assert not validity.incumbent_protected(0.399) and not validity.incumbent_protected(None)
