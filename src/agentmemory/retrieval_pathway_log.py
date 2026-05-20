"""Retrieval pathway log — issue #116 Phase 1-A.

Sidecar observation log for cmd_search dispatches. Records the
pathway fingerprint (mode, table_distribution, intent, profile,
candidate counts, latency) per retrieval into the `retrieval_pathway_log`
table created by migration 066.

Design contract:
  - Emission is best-effort. Failures are logged at DEBUG and swallowed —
    a pathway-log write must never break a search.
  - Gated behind env var BRAINCTL_PATHWAY_LOG. When set to a falsy value
    (``0``, ``false``, ``no``, ``off``, empty string), emission is skipped.
  - No outcome signal required. This table is the observation surface;
    bg_td_events covers outcomes separately. A later linker can join the
    two by (agent_id, time window).

See also:
  - research/issue-116-audit-vs-origin-main.md — the audit that scoped this.
  - bg_shadow.py / cerebellum_shadow.py — the outcome side of the picture.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from typing import Any, Mapping, Optional, Sequence

from agentmemory.paths import get_db_path

logger = logging.getLogger(__name__)

_FALSY = {"0", "false", "no", "off", ""}


def _kill_switch_enabled() -> bool:
    """Return False iff BRAINCTL_PATHWAY_LOG is explicitly disabled."""
    raw = os.environ.get("BRAINCTL_PATHWAY_LOG")
    if raw is None:
        return True
    return raw.strip().lower() not in _FALSY


def _hash_query(query: Optional[str]) -> Optional[str]:
    if not query:
        return None
    norm = " ".join(query.lower().split())
    return hashlib.blake2b(norm.encode("utf-8"), digest_size=16).hexdigest()


def _to_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return None


def _connect(db_path: Optional[str] = None) -> Optional[sqlite3.Connection]:
    """Open a short-lived autocommit connection for one INSERT.

    Uses a 5s timeout + a PRAGMA busy_timeout so contention with a held
    writer (cmd_search's shared connection has a pending transaction at
    the hook site, even though cmd_search is read-only — Python's
    sqlite3 default isolation_level="" wraps reads-after-writes too) is
    survivable rather than instant-fail. isolation_level=None gives us
    autocommit so a single INSERT lands without needing an external
    commit() call.
    """
    try:
        path = db_path or str(get_db_path())
        conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        return conn
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("retrieval_pathway_log: cannot open db: %s", exc)
        return None


def emit_pathway_log(
    *,
    agent_id: Optional[str] = None,
    project: Optional[str] = None,
    query: Optional[str] = None,
    mode: Optional[str] = None,
    table_distribution: Optional[Mapping[str, int]] = None,
    tables_searched: Optional[Sequence[str]] = None,
    candidate_count_pre: Optional[int] = None,
    candidate_count_post: Optional[int] = None,
    rrf_contribution_ratio: Optional[float] = None,
    intent_label: Optional[str] = None,
    active_profile: Optional[str] = None,
    suppressed_strategies: Optional[Sequence[str]] = None,
    embedding_model_version: Optional[str] = None,
    latency_ms: Optional[int] = None,
    benchmark_mode: bool = False,
    db_path: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[int]:
    """Insert one row into retrieval_pathway_log. Returns the row id on
    success or None on any failure / kill-switch trip.

    Callers holding an open connection (e.g. cmd_search) should pass it
    via `conn` to avoid opening a competing writer — racing against a
    held write transaction triggers `database is locked` under SQLite's
    writer-exclusion model even in WAL mode. When `conn` is supplied,
    this function does not close it.

    Never raises. Never blocks.
    """
    if not _kill_switch_enabled():
        return None

    _owned_conn = False
    if conn is None:
        conn = _connect(db_path)
        if conn is None:
            return None
        _owned_conn = True

    try:
        cur = conn.execute(
            """
            INSERT INTO retrieval_pathway_log (
                agent_id, project, query, query_hash,
                mode, table_distribution, tables_searched,
                candidate_count_pre, candidate_count_post,
                rrf_contribution_ratio,
                intent_label, active_profile, suppressed_strategies,
                embedding_model_version, latency_ms, benchmark_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                project,
                query,
                _hash_query(query),
                mode,
                _to_json(dict(table_distribution) if table_distribution else None),
                _to_json(list(tables_searched) if tables_searched else None),
                candidate_count_pre,
                candidate_count_post,
                rrf_contribution_ratio,
                intent_label,
                active_profile,
                _to_json(list(suppressed_strategies) if suppressed_strategies else None),
                embedding_model_version,
                latency_ms,
                1 if benchmark_mode else 0,
            ),
        )
        return cur.lastrowid
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            logger.debug(
                "retrieval_pathway_log: table missing, migration 066 not applied; skipping"
            )
        else:
            logger.debug("retrieval_pathway_log: insert failed: %s", exc)
        return None
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("retrieval_pathway_log: unexpected error: %s", exc)
        return None
    finally:
        if _owned_conn:
            try:
                conn.close()
            except Exception:  # pragma: no cover
                pass


def table_distribution_from_results(
    results: Mapping[str, Sequence[Any]]
) -> dict[str, int]:
    """Compute table_distribution from cmd_search's `results` dict.

    `results` is shaped like {"memories": [...], "events": [...], ...}.
    Returns a {table_name: count} dict for tables that had at least one
    hit. Empty buckets are omitted to keep the json compact.
    """
    return {tbl: len(rows) for tbl, rows in results.items() if rows}
