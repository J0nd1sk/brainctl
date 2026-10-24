"""Bi-temporal validity for memories: interference control (migration 087).

``created_at`` / ``retired_at`` are *transaction* time: when brainctl stored
a row and when it stopped treating it as active. ``valid_from`` /
``valid_to`` are *valid* time: when the fact itself held. ``valid_from`` NULL
means "since created_at" and ``valid_to`` NULL means "still true".

Two halves:

* **Write side.** :func:`close_superseded` runs when a new memory supersedes
  an old one. It closes the old row's validity interval and soft-retires it.
  Retiring takes it out of FTS and out of every ``retired_at IS NULL`` read
  path. The row, its supersedes_id link and its interval stay on disk, so
  :func:`version_chain` (``brainctl memory history``) can show the full
  timeline for audit.

  ``memory replace`` (an explicit user override) always closes. ``memory add
  --supersedes`` and MCP ``memory_add(supersedes_id=)`` close only when the
  PII recency gate rates the incumbent below ENTRENCHED
  (:func:`incumbent_protected`). An ENTRENCHED / CRYSTALLIZED incumbent stays
  active and searchable. The new memory carries the supersedes link, a
  ``valid_from`` and the gate's symmetric Beta(alpha_floor, alpha_floor)
  prior, so it has to win the recall competition before it outranks the
  incumbent. That is the memory-poisoning defence: one injected
  "correction" cannot erase a crystallized fact.

* **Read side.** :func:`superseded_among` lets ``cmd_search`` drop
  candidates that are no longer valid even though they were never retired:
  a ``valid_to`` that has passed, or a supersedes link / AGM ``supersedes``
  edge from an active memory (links written before migration 087). The
  caller passes ``protect`` so link-based suppression follows the same PII
  rule as the write side.

Every helper works on a DB that predates migration 087 (it falls back to
the supersedes link alone) and never raises into the caller's write or
search path.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

__all__ = [
    "PII_PROTECT_THRESHOLD",
    "PROTECTED_TIERS",
    "now_iso",
    "has_validity_columns",
    "incumbent_protected",
    "close_superseded",
    "mark_valid_from",
    "superseded_among",
    "version_chain",
]

#: PII at or above which a superseded incumbent is NOT retired or suppressed.
#: The ENTRENCHED tier boundary of ``_impl._PII_TIERS`` (0.70 CRYSTALLIZED,
#: 0.40 ENTRENCHED, 0.20 ESTABLISHED, 0.00 OPEN).
PII_PROTECT_THRESHOLD = 0.40
PROTECTED_TIERS = ("ENTRENCHED", "CRYSTALLIZED")

# Upper bound on IN (...) list size per query, under SQLite's default
# SQLITE_MAX_VARIABLE_NUMBER of 999.
_CHUNK = 500


def now_iso() -> str:
    """UTC timestamp in the same shape ``_impl._now_ts`` writes."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def has_validity_columns(db: sqlite3.Connection) -> bool:
    """True when ``memories`` carries valid_from / valid_to (migration 087)."""
    try:
        cols = {row[1] for row in db.execute("PRAGMA table_info(memories)").fetchall()}
    except sqlite3.Error:
        return False
    return "valid_to" in cols and "valid_from" in cols


def incumbent_protected(pii: Optional[float]) -> bool:
    """True when an incumbent this entrenched must stay in competition."""
    try:
        return float(pii or 0.0) >= PII_PROTECT_THRESHOLD
    except (TypeError, ValueError):
        return False


def mark_valid_from(db: sqlite3.Connection, memory_id: Optional[int], *, now: Optional[str] = None) -> bool:
    """Stamp ``valid_from`` on a superseding memory (no-op before 087 / if set)."""
    if not memory_id or not has_validity_columns(db):
        return False
    try:
        cur = db.execute(
            "UPDATE memories SET valid_from = COALESCE(valid_from, ?) WHERE id = ?",
            (now or now_iso(), int(memory_id)),
        )
    except (sqlite3.Error, TypeError, ValueError):
        return False
    return bool(cur.rowcount)


def close_superseded(
    db: sqlite3.Connection,
    old_id: Optional[int],
    new_id: Optional[int] = None,
    *,
    now: Optional[str] = None,
    retire: bool = True,
) -> Dict[str, Any]:
    """Close ``old_id``'s validity interval because ``new_id`` replaces it.

    Sets ``valid_to`` (when the column exists and is still NULL) and, with
    ``retire=True``, ``retired_at``. An already-closed interval or
    retirement timestamp is left alone, so re-running this is a no-op. The
    caller owns the transaction (nothing is committed here).

    Returns ``{"closed": bool, "retired": bool, "valid_to": str|None}``.
    """
    out: Dict[str, Any] = {"closed": False, "retired": False, "valid_to": None}
    try:
        old_id = int(old_id) if old_id is not None else None
    except (TypeError, ValueError):
        return out
    if not old_id or (new_id is not None and int(new_id) == old_id):
        return out
    ts = now or now_iso()
    sets: List[str] = []
    params: List[Any] = []
    if has_validity_columns(db):
        sets.append("valid_to = COALESCE(valid_to, ?)")
        params.append(ts)
    if retire:
        sets.append("retired_at = COALESCE(retired_at, ?)")
        params.append(ts)
    if not sets:
        return out
    sets.append("updated_at = ?")
    params.append(ts)
    try:
        cur = db.execute(
            f"UPDATE memories SET {', '.join(sets)} WHERE id = ?",
            params + [old_id],
        )
    except sqlite3.Error:
        return out
    if cur.rowcount:
        out["closed"] = True
        out["retired"] = bool(retire)
        out["valid_to"] = ts
    return out


def _chunks(ids: List[int]) -> Iterable[List[int]]:
    for i in range(0, len(ids), _CHUNK):
        yield ids[i:i + _CHUNK]


def superseded_among(
    db: sqlite3.Connection,
    candidate_ids: Iterable[Any],
    *,
    now: Optional[str] = None,
    protect: Optional[Callable[[int], bool]] = None,
) -> Set[int]:
    """Return the subset of ``candidate_ids`` that is no longer valid.

    A memory X counts as superseded when any of these holds:

    1. ``X.valid_to`` is set and is not in the future;
    2. an active memory S (not retired, interval still open) has
       ``S.supersedes_id = X``;
    3. an active memory S has a ``supersedes`` edge to X in knowledge_edges
       (the edge the AGM conflict resolver writes).

    ``protect(X)`` returning True exempts X from rules 2 and 3 (an
    entrenched incumbent the write side deliberately left in competition).
    Rule 1 is a recorded decision and is never exempted.

    The caller decides whether to drop or down-weight these. Missing
    columns or tables (an older schema) skip that rule; nothing raises.
    """
    ids: List[int] = []
    for cid in candidate_ids:
        try:
            ids.append(int(cid))
        except (TypeError, ValueError):
            continue
    ids = sorted(set(ids))
    if not ids:
        return set()
    ts = now or now_iso()
    has_cols = has_validity_columns(db)
    # S must itself be valid, or a closed version would still suppress its
    # predecessor after the successor was in turn superseded.
    s_open = "AND (s.valid_to IS NULL OR julianday(s.valid_to) > julianday(?))" if has_cols else ""
    out: Set[int] = set()
    linked: Set[int] = set()
    for chunk in _chunks(ids):
        ph = ",".join("?" * len(chunk))
        queries = []
        if has_cols:
            queries.append((
                f"SELECT id FROM memories WHERE id IN ({ph}) "
                f"AND valid_to IS NOT NULL AND julianday(valid_to) <= julianday(?)",
                list(chunk) + [ts],
            ))
        queries.append((
            f"SELECT DISTINCT s.supersedes_id FROM memories s "
            f"WHERE s.supersedes_id IN ({ph}) AND s.retired_at IS NULL "
            f"AND s.id != s.supersedes_id {s_open}",
            list(chunk) + ([ts] if has_cols else []),
        ))
        queries.append((
            f"SELECT DISTINCT ke.target_id FROM knowledge_edges ke "
            f"JOIN memories s ON s.id = ke.source_id "
            f"WHERE ke.relation_type = 'supersedes' "
            f"AND ke.source_table = 'memories' AND ke.target_table = 'memories' "
            f"AND ke.target_id IN ({ph}) AND ke.source_id != ke.target_id "
            f"AND s.retired_at IS NULL {s_open}",
            list(chunk) + ([ts] if has_cols else []),
        ))
        for n, (sql, params) in enumerate(queries):
            closed_rule = has_cols and n == 0
            try:
                for row in db.execute(sql, params).fetchall():
                    if row[0] is not None:
                        (out if closed_rule else linked).add(int(row[0]))
            except sqlite3.Error:
                continue
    for mid in sorted(linked - out):
        try:
            if protect is not None and protect(mid):
                continue
        except Exception:
            continue  # unknown protection status: keep the candidate
        out.add(mid)
    return out


def version_chain(db: sqlite3.Connection, memory_id: int, *, max_hops: int = 50) -> List[Dict[str, Any]]:
    """Every version of ``memory_id``'s fact, oldest first, retired rows included.

    Walks ``supersedes_id`` back to the root and then forward through each
    successor. Each entry carries the transaction-time and valid-time
    columns, plus ``current`` (active with an open interval).
    """
    has_cols = has_validity_columns(db)
    cols = ("id, agent_id, category, scope, content, supersedes_id, created_at, "
            "retired_at" + (", valid_from, valid_to" if has_cols else ""))

    def _row(mid):
        r = db.execute(f"SELECT {cols} FROM memories WHERE id = ?", (mid,)).fetchone()
        return dict(zip([c.strip() for c in cols.split(",")], r)) if r else None

    start = _row(memory_id)
    if start is None:
        return []
    # Back to the root.
    root = start
    seen = {root["id"]}
    for _ in range(max_hops):
        prev_id = root.get("supersedes_id")
        if not prev_id or prev_id in seen:
            break
        prev = _row(prev_id)
        if prev is None:
            break
        seen.add(prev["id"])
        root = prev
    # Forward, breadth-first: a version can have more than one successor.
    chain: List[Dict[str, Any]] = []
    frontier = [root]
    visited: Set[int] = set()
    while frontier and len(chain) < max_hops:
        node = frontier.pop(0)
        if node["id"] in visited:
            continue
        visited.add(node["id"])
        chain.append(node)
        for (nxt,) in db.execute(
            "SELECT id FROM memories WHERE supersedes_id = ? AND id != ? ORDER BY created_at, id",
            (node["id"], node["id"]),
        ).fetchall():
            if nxt not in visited:
                child = _row(nxt)
                if child is not None:
                    frontier.append(child)
    ts = now_iso()
    for node in chain:
        if not has_cols:
            node["valid_from"] = None
            node["valid_to"] = None
        if node["valid_from"] is None:
            node["valid_from"] = node["created_at"]
        vt = node.get("valid_to")
        node["current"] = node["retired_at"] is None and (vt is None or str(vt) > ts)
    return chain
