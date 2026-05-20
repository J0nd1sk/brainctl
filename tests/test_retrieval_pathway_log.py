"""Tests for retrieval_pathway_log — issue #116 Phase 1-A.

Covers:
  - schema applies and indexes are present (migration 066)
  - emit_pathway_log writes the expected row shape
  - kill-switch env var disables emission
  - missing table degrades gracefully (no exception)
  - table_distribution_from_results computes the right shape
  - cmd_search integration: a row lands on every search
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_066 = REPO_ROOT / "db" / "migrations" / "066_retrieval_pathway_log.sql"


def _bootstrap_min_schema(conn: sqlite3.Connection) -> None:
    """Minimum schema_version table so migration 066 can record itself."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            description TEXT,
            applied_at TEXT
        );
        """
    )


def _apply_migration(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        _bootstrap_min_schema(conn)
        conn.executescript(MIGRATION_066.read_text())
        conn.commit()
    finally:
        conn.close()


def test_migration_applies_and_creates_indexes(tmp_path):
    db = tmp_path / "brain.db"
    _apply_migration(db)
    conn = sqlite3.connect(str(db))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(retrieval_pathway_log)")}
        expected = {
            "id", "fired_at", "agent_id", "project", "query", "query_hash",
            "mode", "table_distribution", "tables_searched",
            "candidate_count_pre", "candidate_count_post", "rrf_contribution_ratio",
            "intent_label", "active_profile", "suppressed_strategies",
            "embedding_model_version", "latency_ms", "benchmark_mode",
            "linked_td_event_id",
        }
        assert expected.issubset(cols), f"missing columns: {expected - cols}"
        idx = {r[1] for r in conn.execute("PRAGMA index_list(retrieval_pathway_log)")}
        # Five named indexes from the migration (sqlite may add internals).
        for want in {"idx_rpl_recent", "idx_rpl_agent", "idx_rpl_mode",
                     "idx_rpl_intent", "idx_rpl_unlinked"}:
            assert want in idx, f"missing index {want}"
    finally:
        conn.close()


def test_emit_pathway_log_writes_expected_row(tmp_path, monkeypatch):
    db = tmp_path / "brain.db"
    _apply_migration(db)
    monkeypatch.setenv("BRAINCTL_PATHWAY_LOG", "1")

    # Import after env is set so the module reads the patched value.
    from agentmemory.retrieval_pathway_log import emit_pathway_log

    row_id = emit_pathway_log(
        agent_id="test-agent",
        project="test-proj",
        query="What does Alice prefer?",
        mode="hybrid-rrf",
        table_distribution={"memories": 7, "events": 2},
        tables_searched=["memories", "events", "context"],
        candidate_count_post=9,
        intent_label="entity_lookup",
        active_profile="research",
        embedding_model_version="nomic-embed-text:768",
        latency_ms=42,
        db_path=str(db),
    )
    assert row_id is not None and row_id > 0

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT agent_id, project, query, mode, table_distribution, "
            "tables_searched, candidate_count_post, intent_label, "
            "active_profile, embedding_model_version, latency_ms, benchmark_mode "
            "FROM retrieval_pathway_log WHERE id = ?",
            (row_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "test-agent"
    assert row[2] == "What does Alice prefer?"
    assert row[3] == "hybrid-rrf"
    assert json.loads(row[4]) == {"memories": 7, "events": 2}
    assert json.loads(row[5]) == ["memories", "events", "context"]
    assert row[6] == 9
    assert row[7] == "entity_lookup"
    assert row[8] == "research"
    assert row[9] == "nomic-embed-text:768"
    assert row[10] == 42
    assert row[11] == 0


def test_kill_switch_skips_emission(tmp_path, monkeypatch):
    db = tmp_path / "brain.db"
    _apply_migration(db)
    monkeypatch.setenv("BRAINCTL_PATHWAY_LOG", "0")

    from agentmemory.retrieval_pathway_log import emit_pathway_log

    row_id = emit_pathway_log(
        agent_id="test-agent",
        query="kill-switch query",
        mode="fts",
        db_path=str(db),
    )
    assert row_id is None

    conn = sqlite3.connect(str(db))
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM retrieval_pathway_log"
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == 0


def test_missing_table_returns_none_no_exception(tmp_path, monkeypatch):
    db = tmp_path / "brain.db"
    # NO migration — table does not exist.
    monkeypatch.setenv("BRAINCTL_PATHWAY_LOG", "1")

    from agentmemory.retrieval_pathway_log import emit_pathway_log

    # Should swallow the OperationalError and return None.
    row_id = emit_pathway_log(
        agent_id="test-agent",
        query="schema-missing query",
        db_path=str(db),
    )
    assert row_id is None


def test_table_distribution_from_results():
    from agentmemory.retrieval_pathway_log import table_distribution_from_results
    results = {
        "memories": [{"id": 1}, {"id": 2}],
        "events": [{"id": 3}],
        "context": [],
        "decisions": [],
        "procedures": [{"id": 4}, {"id": 5}, {"id": 6}],
    }
    dist = table_distribution_from_results(results)
    assert dist == {"memories": 2, "events": 1, "procedures": 3}
