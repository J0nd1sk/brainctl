"""Memory-quality suites: dedup, temporal update, abstention.

The search-quality bench (``tests.bench.eval``) scores static retrieval
over a corpus it seeds directly with SQL. These three suites measure how
the brain behaves as it is *written to*, so every memory goes through the
real write path (``_impl.cmd_memory_add``, i.e. ``brainctl memory add``; the
dedup suite also runs the MCP ``memory_add`` tool) and every query goes
through the real ``_impl.cmd_search`` pipeline.

Suites
------
``dedup``      Pattern separation in the write gate. Writes the first half
               of each ``DEDUP_PAIRS`` pair, then the second half, and checks
               how many of the two are still active afterwards.
               ``duplicate_suppression_rate``: true duplicates that did not
               leave a second active memory. ``false_merge_rate``: near-miss
               pairs (different facts) where one side was merged, rejected
               or superseded.
``temporal``   Knowledge update. Each ``TEMPORAL_FACTS`` fact is written and
               then updated, oldest version first, with ``created_at``
               backdated so versions are 30 days apart. Three update modes:
               ``supersedes`` (``memory add --supersedes <prev>``, the
               PII-gated path, reported as ``overall``), ``naive`` (plain
               ``memory add``, no link to the old value) and ``replace``
               (``memory replace``, which retires the old row; a harness
               sanity check). Reports latest-value P@1 and stale-value
               intrusion (a stale version in the top-k, or ranked above the
               current one).
``abstention`` Queries that the corpus can answer mixed with ones it cannot.
               Records the top-1 score distribution for each group plus
               abstention precision/recall from an optional hook: when the
               search payload carries an ``answerable`` flag (or a populated
               ``metacognition.answerability_score``), that decides; otherwise
               every query counts as answerable (the current behaviour).

Embeddings
----------
Like the search-quality bench these suites need no Ollama: with no embedder
the vector leg of cmd_search and the W(m) embedding gate quietly drop out
and everything runs on FTS5. Unlike that bench, they make it explicit:
the Ollama URL is pointed at a closed local port so a developer machine
running Ollama gets the same numbers as CI. Set
``BRAINCTL_BENCH_ALLOW_EMBED=1`` to keep the real endpoint (numbers will
then differ from the committed baselines).

Each suite runs against its own throwaway brain.db, never the user's.
"""

from __future__ import annotations

import contextlib
import gc
import io
import json
import os
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from tests.bench.memory_fixtures import (  # noqa: E402
    ABSTENTION_CORPUS,
    ABSTENTION_QUERIES,
    DEDUP_PAIRS,
    DUPLICATE_KINDS,
    NEAR_MISS_KIND,
    TEMPORAL_DISTRACTORS,
    TEMPORAL_FACTS,
)

AGENT_ID = "bench-agent"
SUITES = ("dedup", "temporal", "abstention")
TOP_K = 5                 # window for "present in top-k" style metrics
SEARCH_LIMIT = 10         # results requested from cmd_search
REGRESSION_TOLERANCE = 0.02
BASELINES_DIR = Path(__file__).resolve().parent / "baselines"
DEAD_EMBED_URL = "http://127.0.0.1:9/api/embed"  # discard port: always refused

DEDUP_WRITE_PATHS = ("cli", "mcp")
TEMPORAL_MODES = ("supersedes", "naive", "replace")
TEMPORAL_PRIMARY_MODE = "supersedes"
TEMPORAL_SPACING_DAYS = 30

# (dotted metric path, direction). "higher" = a drop is a regression,
# "lower" = a rise is a regression. Missing keys in the baseline are
# reported but never fail the gate, mirroring tests.bench.gate.
GATES: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "dedup": (
        ("overall.duplicate_suppression_rate", "higher"),
        ("overall.false_merge_rate", "lower"),
        ("by_write_path.mcp.duplicate_suppression_rate", "higher"),
        ("by_write_path.mcp.false_merge_rate", "lower"),
    ),
    "temporal": (
        ("overall.latest_p_at_1", "higher"),
        ("overall.stale_above_latest_rate", "lower"),
        ("overall.stale_in_top_k_rate", "lower"),
        ("by_mode.naive.latest_p_at_1", "higher"),
        ("by_mode.naive.stale_above_latest_rate", "lower"),
        ("by_mode.replace.latest_p_at_1", "higher"),
    ),
    "abstention": (
        ("overall.answerable_p_at_1", "higher"),
        ("overall.score_auroc", "higher"),
        ("overall.raw_score_auroc", "higher"),
        ("overall.abstention_precision", "higher"),
        ("overall.abstention_recall", "higher"),
        ("overall.false_abstention_rate", "lower"),
    ),
}


# ---------------------------------------------------------------------------
# Metric primitives (pure, no DB)
# ---------------------------------------------------------------------------

def safe_rate(numerator: float, denominator: float, empty: float = 0.0) -> float:
    """``numerator / denominator`` rounded to 4 places; ``empty`` when den == 0."""
    if not denominator:
        return empty
    return round(numerator / denominator, 4)


def is_collapsed(first_active: bool, second_active: bool) -> bool:
    """A pair is collapsed when fewer than two of its memories stay active.

    Covers every way a write gate can fold two writes into one: the second
    write merged into (reinforced) the first, the second was rejected, or
    the second superseded/retired the first.
    """
    return (int(bool(first_active)) + int(bool(second_active))) < 2


def dedup_metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-pair rows (``kind``, ``collapsed``) into suite metrics.

    Duplicates should collapse; near-misses should not.
    """
    valid = [r for r in rows if not r.get("invalid")]
    dupes = [r for r in valid if r["kind"] in DUPLICATE_KINDS]
    near = [r for r in valid if r["kind"] == NEAR_MISS_KIND]
    suppressed = sum(1 for r in dupes if r["collapsed"])
    merged = sum(1 for r in near if r["collapsed"])
    correct = suppressed + (len(near) - merged)
    overall = {
        "n_pairs": len(valid),
        "n_invalid": len(rows) - len(valid),
        "n_duplicates": len(dupes),
        "n_near_miss": len(near),
        "duplicate_suppression_rate": safe_rate(suppressed, len(dupes)),
        "false_merge_rate": safe_rate(merged, len(near)),
        "separation_accuracy": safe_rate(correct, len(valid)),
    }
    by_kind: Dict[str, Dict[str, Any]] = {}
    for kind in (*DUPLICATE_KINDS, NEAR_MISS_KIND):
        bucket = [r for r in valid if r["kind"] == kind]
        if not bucket:
            continue
        by_kind[kind] = {
            "count": len(bucket),
            "collapse_rate": safe_rate(sum(1 for r in bucket if r["collapsed"]), len(bucket)),
        }
    return {"overall": overall, "by_kind": by_kind}


def rank_of(ranked_ids: Sequence[Any], target: Any) -> Optional[int]:
    """1-based rank of ``target`` in ``ranked_ids``; None when absent/None."""
    if target is None:
        return None
    for i, rid in enumerate(ranked_ids, start=1):
        if rid == target:
            return i
    return None


def temporal_query_metrics(
    ranked_ids: Sequence[Any],
    latest_id: Any,
    stale_ids: Iterable[Any],
    k: int = TOP_K,
) -> Dict[str, Any]:
    """Score one knowledge-update query.

    ``stale_above_latest`` is true when any stale version outranks the current
    one anywhere in the returned list, or a stale version is returned while
    the current one is not.
    """
    stale = set(stale_ids)
    latest_rank = rank_of(ranked_ids, latest_id)
    stale_ranks = [i for i, rid in enumerate(ranked_ids, start=1) if rid in stale]
    best_stale = min(stale_ranks) if stale_ranks else None
    if best_stale is None:
        stale_above = False
    elif latest_rank is None:
        stale_above = True
    else:
        stale_above = best_stale < latest_rank
    return {
        "latest_rank": latest_rank,
        "latest_at_1": 1.0 if latest_rank == 1 else 0.0,
        "latest_in_top_k": 1.0 if latest_rank is not None and latest_rank <= k else 0.0,
        "latest_rr": (1.0 / latest_rank) if latest_rank else 0.0,
        "stale_in_top_k": 1.0 if any(r <= k for r in stale_ranks) else 0.0,
        "stale_above_latest": 1.0 if stale_above else 0.0,
    }


def temporal_metrics(rows: Sequence[Dict[str, Any]], n_updates: int = 0,
                     n_updates_lost: int = 0) -> Dict[str, Any]:
    def mean(key):
        xs = [r[key] for r in rows]
        return round(statistics.mean(xs), 4) if xs else 0.0

    return {
        "n_queries": len(rows),
        "latest_p_at_1": mean("latest_at_1"),
        "latest_recall_at_k": mean("latest_in_top_k"),
        "latest_mrr": mean("latest_rr"),
        "stale_in_top_k_rate": mean("stale_in_top_k"),
        "stale_above_latest_rate": mean("stale_above_latest"),
        "n_updates": n_updates,
        # update writes that did not leave a new active memory (e.g. the
        # write gate folded the new value into the stale one)
        "update_write_lost_rate": safe_rate(n_updates_lost, n_updates),
    }


def _quantile(sorted_xs: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile of an already sorted list."""
    if not sorted_xs:
        return 0.0
    if len(sorted_xs) == 1:
        return float(sorted_xs[0])
    pos = (len(sorted_xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_xs) - 1)
    frac = pos - lo
    return float(sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * frac)


def score_summary(scores: Iterable[float]) -> Dict[str, float]:
    xs = sorted(float(s) for s in scores)
    if not xs:
        return {"n": 0, "mean": 0.0, "min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0}
    r = lambda v: round(v, 6)  # noqa: E731
    return {
        "n": len(xs),
        "mean": r(statistics.mean(xs)),
        "min": r(xs[0]),
        "p25": r(_quantile(xs, 0.25)),
        "median": r(_quantile(xs, 0.5)),
        "p75": r(_quantile(xs, 0.75)),
        "max": r(xs[-1]),
    }


def auroc(positive: Sequence[float], negative: Sequence[float]) -> float:
    """P(score of a random positive > score of a random negative), ties = 0.5.

    1.0 means some score threshold separates the groups perfectly; 0.5 means
    the score carries no signal. Returns 0.5 when either group is empty.
    """
    if not positive or not negative:
        return 0.5
    wins = 0.0
    for p in positive:
        for n in negative:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return round(wins / (len(positive) * len(negative)), 4)


def resolve_answerable(payload: Any) -> Tuple[bool, str]:
    """Optional abstention hook over a cmd_search payload.

    Precedence: a top-level ``answerable`` bool, then
    ``metacognition.answerable``, then ``metacognition.abstained`` when an
    answerability score was actually computed. Otherwise the placeholder:
    everything is answerable (search has no abstention today).
    """
    if isinstance(payload, dict):
        if isinstance(payload.get("answerable"), bool):
            return payload["answerable"], "answerable_field"
        meta = payload.get("metacognition")
        if isinstance(meta, dict):
            if isinstance(meta.get("answerable"), bool):
                return meta["answerable"], "metacognition.answerable"
            if meta.get("answerability_score") is not None:
                return (not bool(meta.get("abstained"))), "metacognition.abstained"
    return True, "placeholder_all_answerable"


def abstention_metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    """Binary abstention scores. Positive class = "should abstain".

    Each row needs ``should_abstain`` (gold) and ``abstained`` (predicted).
    Precision/recall/F1 are 0.0 when undefined (no predicted or no gold
    abstentions) so a system that never abstains scores 0, not 1.
    """
    tp = sum(1 for r in rows if r["should_abstain"] and r["abstained"])
    fp = sum(1 for r in rows if not r["should_abstain"] and r["abstained"])
    fn = sum(1 for r in rows if r["should_abstain"] and not r["abstained"])
    n_answerable = sum(1 for r in rows if not r["should_abstain"])
    precision = safe_rate(tp, tp + fp)
    recall = safe_rate(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0
    return {
        "abstention_precision": precision,
        "abstention_recall": recall,
        "abstention_f1": f1,
        "false_abstention_rate": safe_rate(fp, n_answerable),
    }


# ---------------------------------------------------------------------------
# Baseline gate
# ---------------------------------------------------------------------------

def get_path(d: Any, dotted: str) -> Any:
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def compare_suite(
    current: Dict[str, Any],
    baseline: Dict[str, Any],
    gates: Sequence[Tuple[str, str]],
    tolerance: float = REGRESSION_TOLERANCE,
) -> Dict[str, Any]:
    """Direction-aware version of the >2% legacy gate in tests.bench.run."""
    deltas: Dict[str, Dict[str, Any]] = {}
    failing: List[Dict[str, Any]] = []
    missing: List[str] = []
    for path, direction in gates:
        cur_v = get_path(current, path)
        base_v = get_path(baseline, path)
        if base_v is None or cur_v is None:
            missing.append(path)
            continue
        cur_v, base_v = float(cur_v), float(base_v)
        delta = round(cur_v - base_v, 4)
        deltas[path] = {"current": cur_v, "baseline": base_v, "delta": delta,
                        "direction": direction}
        regressed = delta < -tolerance if direction == "higher" else delta > tolerance
        if regressed:
            failing.append({"metric": path, "current": cur_v, "baseline": base_v,
                            "direction": direction})
    return {"ok": not failing, "tolerance": tolerance, "deltas": deltas,
            "failing": failing, "missing": missing}


def baseline_path(suite: str) -> Path:
    return BASELINES_DIR / f"memory_{suite}.json"


def trim_for_baseline(result: Dict[str, Any]) -> Dict[str, Any]:
    drop = {"rows", "elapsed_s", "db_path"}
    return {k: v for k, v in result.items() if k not in drop}


def load_baseline(suite: str) -> Optional[Dict[str, Any]]:
    path = baseline_path(suite)
    if not path.exists():
        return None
    with path.open() as fh:
        return json.load(fh)


def save_baseline(suite: str, result: Dict[str, Any]) -> Path:
    path = baseline_path(suite)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(trim_for_baseline(result), fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


# ---------------------------------------------------------------------------
# Throwaway brain driven through the real write / search entry points
# ---------------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class BenchBrain:
    """Thin driver over ``_impl`` CLI handlers bound to one temp brain.db."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        import agentmemory._impl as _impl
        self._impl = _impl

    # -- plumbing ----------------------------------------------------------
    def _call(self, fn, args) -> Dict[str, Any]:
        """Run a CLI handler, capturing its json_out payload."""
        impl = self._impl
        captured: List[Any] = []

        def _capture(data, compact=False):
            captured.append(data)

        saved = (impl.json_out, impl.oneline_out)
        impl.json_out = _capture
        impl.oneline_out = _capture
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                fn(args)
        except SystemExit as exc:
            return {"ok": False, "error": f"exit:{exc.code}"}
        finally:
            impl.json_out, impl.oneline_out = saved
            gc.collect()  # release the handler's sqlite connection
        payload = captured[-1] if captured else {}
        return payload if isinstance(payload, dict) else {"payload": payload}

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # -- writes --------------------------------------------------------------
    def add_cli(self, content: str, category: str,
                supersedes: Optional[int] = None) -> Dict[str, Any]:
        """``brainctl memory add`` (optionally ``--supersedes``)."""
        args = types.SimpleNamespace(
            content=content, category=category, scope="global",
            confidence=None, tags=None, source_event=None, type="episodic",
            reflexion=False, attribute=False, force=False,
            dry_run_worthiness=False, supersedes=supersedes,
            file_path=None, file_line=None, agent=AGENT_ID,
        )
        return self._call(self._impl.cmd_memory_add, args)

    def replace_cli(self, old_id: int, content: str, category: str) -> Dict[str, Any]:
        """``brainctl memory replace`` (retires ``old_id``)."""
        args = types.SimpleNamespace(
            old_id=old_id, content=content, category=category, scope="global",
            confidence=None, tags=None, agent=AGENT_ID,
        )
        return self._call(self._impl.cmd_memory_replace, args)

    def add_mcp(self, content: str, category: str,
                supersedes: Optional[int] = None) -> Dict[str, Any]:
        """MCP ``memory_add`` tool (``mcp_server.tool_memory_add``)."""
        from agentmemory import mcp_server
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                return mcp_server.tool_memory_add(
                    agent_id=AGENT_ID, content=content, category=category,
                    supersedes_id=supersedes,
                )
        finally:
            gc.collect()

    def add(self, write_path: str, content: str, category: str) -> Dict[str, Any]:
        if write_path == "mcp":
            return self.add_mcp(content, category)
        return self.add_cli(content, category)

    # -- search --------------------------------------------------------------
    def search(self, query: str, limit: int = SEARCH_LIMIT) -> Dict[str, Any]:
        """Full ``cmd_search`` pipeline over the memories table."""
        args = types.SimpleNamespace(
            query=query, limit=limit, tables="memories", no_recency=False,
            no_graph=True, budget=None, min_salience=None, mmr=False,
            mmr_lambda=0.7, explore=False, profile=None, pagerank_boost=0.0,
            quantum=False, benchmark=False, agent=AGENT_ID, format="json",
            oneline=False, verbose=False, output="return",
        )
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                payload = self._impl.cmd_search(args)
        finally:
            gc.collect()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def ranked_memories(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows = list(payload.get("memories") or [])
        rows.sort(key=lambda r: r.get("final_score", 0.0) or 0.0, reverse=True)
        return rows

    # -- state ---------------------------------------------------------------
    def active_ids(self, ids: Iterable[Optional[int]]) -> Dict[int, bool]:
        ids = [i for i in ids if i is not None]
        if not ids:
            return {}
        conn = self._conn()
        try:
            ph = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT id, retired_at FROM memories WHERE id IN ({ph})", ids
            ).fetchall()
        finally:
            conn.close()
        found = {r["id"]: r["retired_at"] is None for r in rows}
        return {i: found.get(i, False) for i in ids}

    def active_count(self) -> int:
        conn = self._conn()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM memories WHERE retired_at IS NULL"
            ).fetchone()[0]
        finally:
            conn.close()

    def backdate(self, memory_id: int, days_ago: float) -> None:
        """Simulate the passage of time between writes."""
        ts = _iso(datetime.now(timezone.utc) - timedelta(days=days_ago))
        conn = self._conn()
        try:
            conn.execute("UPDATE memories SET created_at=?, updated_at=? WHERE id=?",
                         (ts, ts, memory_id))
            conn.commit()
        finally:
            conn.close()


@contextlib.contextmanager
def bench_brain(with_mcp: bool = False):
    """Fresh brain.db wired into ``_impl`` (and optionally ``mcp_server``).

    Restores every env var / module attribute it touches on exit.
    """
    from tests.bench.eval import init_bench_schema

    tmp_dir = Path(tempfile.mkdtemp(prefix="brainctl-memq-"))
    db_path = tmp_dir / "brain.db"
    conn = sqlite3.connect(str(db_path))
    try:
        init_bench_schema(conn, AGENT_ID)
        conn.commit()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
    finally:
        conn.close()

    allow_embed = os.environ.get("BRAINCTL_BENCH_ALLOW_EMBED", "").strip() in ("1", "true", "yes")
    env = {
        "BRAINCTL_DB": str(db_path),
        "BRAIN_DB": str(db_path),
        "BRAINCTL_SILENT_MIGRATIONS": "1",
    }
    if not allow_embed:
        env.update({"BRAINCTL_OLLAMA_URL": DEAD_EMBED_URL, "BRAINCTL_EMBED_TIMEOUT": "1"})
    saved_env = {k: os.environ.get(k) for k in env}
    os.environ.update(env)

    import agentmemory._impl as _impl
    patches: List[Tuple[Any, str, Any]] = [(_impl, "DB_PATH", db_path)]
    if not allow_embed:
        patches.append((_impl, "OLLAMA_EMBED_URL", DEAD_EMBED_URL))
    if with_mcp:
        from agentmemory import mcp_server
        patches.append((mcp_server, "DB_PATH", db_path))
        if not allow_embed:
            patches.append((mcp_server, "OLLAMA_EMBED_URL", DEAD_EMBED_URL))
    saved_attrs = [(mod, name, getattr(mod, name)) for mod, name, _ in patches]
    for mod, name, value in patches:
        setattr(mod, name, value)
    try:
        yield BenchBrain(db_path)
    finally:
        for mod, name, value in saved_attrs:
            setattr(mod, name, value)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        gc.collect()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _write_outcome(resp: Dict[str, Any]) -> str:
    if resp.get("rejected"):
        return "rejected"
    if resp.get("deduplicated"):
        return "merged"
    if resp.get("memory_id") or resp.get("new_id"):
        return "stored"
    return "error"


# ---------------------------------------------------------------------------
# Suite runners
# ---------------------------------------------------------------------------

def _run_dedup_path(write_path: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    with bench_brain(with_mcp=(write_path == "mcp")) as brain:
        first_ids: Dict[str, Optional[int]] = {}
        first_outcomes: Dict[str, str] = {}
        # All first writes land before any second write: the corpus exists,
        # then the duplicates / near-misses arrive.
        for pair in DEDUP_PAIRS:
            resp = brain.add(write_path, pair.first, pair.category)
            first_ids[pair.key] = resp.get("memory_id")
            first_outcomes[pair.key] = _write_outcome(resp)
        for pair in DEDUP_PAIRS:
            first_id = first_ids[pair.key]
            resp = brain.add(write_path, pair.second, pair.category)
            second_id = resp.get("memory_id")
            state = brain.active_ids([first_id, second_id])
            first_active = state.get(first_id, False) if first_id else False
            second_active = state.get(second_id, False) if second_id else False
            row = {
                "key": pair.key,
                "kind": pair.kind,
                "first_id": first_id,
                "second_id": second_id,
                "second_outcome": _write_outcome(resp),
                "merged_into": resp.get("reinforced_memory_id"),
                "first_active": first_active,
                "second_active": second_active,
                "collapsed": is_collapsed(first_active, second_active),
            }
            if first_outcomes[pair.key] != "stored":
                row["invalid"] = f"first write {first_outcomes[pair.key]}"
            rows.append(row)
        active = brain.active_count()
    metrics = dedup_metrics(rows)
    metrics["overall"]["active_memories_after"] = active
    return metrics, rows


def run_dedup(write_paths: Sequence[str] = DEDUP_WRITE_PATHS) -> Dict[str, Any]:
    t0 = time.monotonic()
    by_path: Dict[str, Dict[str, Any]] = {}
    by_kind: Dict[str, Dict[str, Any]] = {}
    rows: Dict[str, List[Dict[str, Any]]] = {}
    for wp in write_paths:
        metrics, wp_rows = _run_dedup_path(wp)
        by_path[wp] = metrics["overall"]
        by_kind[wp] = metrics["by_kind"]
        rows[wp] = wp_rows
    primary = write_paths[0]
    return {
        "suite": "dedup",
        "primary_write_path": primary,
        "overall": by_path[primary],
        "by_kind": by_kind[primary],
        "by_write_path": by_path,
        "by_write_path_kind": by_kind,
        "rows": rows,
        "elapsed_s": round(time.monotonic() - t0, 3),
    }


def _run_temporal_mode(mode: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    n_rounds = max(len(f.versions) for f in TEMPORAL_FACTS)

    def days_ago(round_idx: int) -> float:
        return (n_rounds - 1 - round_idx) * TEMPORAL_SPACING_DAYS + 7

    rows: List[Dict[str, Any]] = []
    with bench_brain() as brain:
        for category, content in TEMPORAL_DISTRACTORS:
            resp = brain.add_cli(content, category)
            if resp.get("memory_id"):
                brain.backdate(resp["memory_id"], days_ago(0))

        # versions[fact] = list of (version_index, memory_id) actually stored
        versions: Dict[str, List[Tuple[int, int]]] = {f.key: [] for f in TEMPORAL_FACTS}
        touched: Dict[str, set] = {f.key: set() for f in TEMPORAL_FACTS}
        n_updates = n_lost = 0
        for r in range(n_rounds):
            for fact in TEMPORAL_FACTS:
                if r >= len(fact.versions):
                    continue
                content = fact.versions[r]
                prev = versions[fact.key][-1][1] if versions[fact.key] else None
                if r == 0 or prev is None:
                    resp = brain.add_cli(content, fact.category)
                elif mode == "naive":
                    resp = brain.add_cli(content, fact.category)
                elif mode == "supersedes":
                    resp = brain.add_cli(content, fact.category, supersedes=prev)
                elif mode == "replace":
                    resp = brain.replace_cli(prev, content, fact.category)
                else:
                    raise ValueError(f"unknown temporal mode {mode!r}")
                new_id = resp.get("memory_id") or resp.get("new_id")
                if r > 0:
                    n_updates += 1
                if resp.get("reinforced_memory_id"):
                    touched[fact.key].add(resp["reinforced_memory_id"])
                if new_id:
                    versions[fact.key].append((r, new_id))
                    brain.backdate(new_id, days_ago(r))
                elif r > 0:
                    n_lost += 1

        for fact in TEMPORAL_FACTS:
            stored = versions[fact.key]
            last_idx = len(fact.versions) - 1
            latest_id = next((mid for idx, mid in stored if idx == last_idx), None)
            stale_ids = {mid for idx, mid in stored if idx != last_idx} | touched[fact.key]
            stale_ids.discard(latest_id)
            for q in fact.queries:
                ranked = [r_["id"] for r_ in brain.ranked_memories(brain.search(q))]
                m = temporal_query_metrics(ranked, latest_id, stale_ids, k=TOP_K)
                rows.append({"fact": fact.key, "query": q, "latest_id": latest_id,
                             "stale_ids": sorted(stale_ids), "ranked_ids": ranked[:TOP_K], **m})
    return temporal_metrics(rows, n_updates=n_updates, n_updates_lost=n_lost), rows


def run_temporal(modes: Sequence[str] = TEMPORAL_MODES) -> Dict[str, Any]:
    t0 = time.monotonic()
    by_mode: Dict[str, Dict[str, Any]] = {}
    rows: Dict[str, List[Dict[str, Any]]] = {}
    for mode in modes:
        by_mode[mode], rows[mode] = _run_temporal_mode(mode)
    primary = TEMPORAL_PRIMARY_MODE if TEMPORAL_PRIMARY_MODE in by_mode else modes[0]
    return {
        "suite": "temporal",
        "primary_mode": primary,
        "k": TOP_K,
        "n_facts": len(TEMPORAL_FACTS),
        "overall": by_mode[primary],
        "by_mode": by_mode,
        "rows": rows,
        "elapsed_s": round(time.monotonic() - t0, 3),
    }


def run_abstention() -> Dict[str, Any]:
    t0 = time.monotonic()
    rows: List[Dict[str, Any]] = []
    with bench_brain() as brain:
        key_to_id: Dict[str, Optional[int]] = {}
        for key, category, content in ABSTENTION_CORPUS:
            key_to_id[key] = brain.add_cli(content, category).get("memory_id")
        for q in ABSTENTION_QUERIES:
            payload = brain.search(q.text)
            ranked = brain.ranked_memories(payload)
            ids = [r["id"] for r in ranked]
            answerable, source = resolve_answerable(payload)
            gold_id = key_to_id.get(q.gold) if q.gold else None
            top = ranked[0] if ranked else {}
            rank = rank_of(ids, gold_id)
            rows.append({
                "query": q.text,
                "kind": q.kind,
                "should_abstain": q.gold is None,
                "abstained": not answerable,
                "answerability_source": source,
                "n_results": len(ranked),
                "top_score": float(top.get("final_score") or 0.0),
                # BM25 strength of the top hit before cmd_search's per-bucket
                # max-normalisation (fts_rank is negative; more negative = better)
                "top_raw_score": round(-float(top.get("fts_rank") or 0.0), 8) or 0.0,
                "top_id": top.get("id"),
                "gold_rank": rank,
                "tier": (payload.get("metacognition") or {}).get("tier"),
            })

    answerable_rows = [r for r in rows if not r["should_abstain"]]
    unanswerable_rows = [r for r in rows if r["should_abstain"]]

    def answered_at(r, k):
        return (not r["abstained"]) and r["gold_rank"] is not None and r["gold_rank"] <= k

    sources = sorted({r["answerability_source"] for r in rows})
    overall: Dict[str, Any] = {
        "n_queries": len(rows),
        "n_answerable": len(answerable_rows),
        "n_unanswerable": len(unanswerable_rows),
        "answerability_source": sources[0] if len(sources) == 1 else ",".join(sources),
        "answerable_p_at_1": safe_rate(sum(answered_at(r, 1) for r in answerable_rows), len(answerable_rows)),
        "answerable_recall_at_k": safe_rate(sum(answered_at(r, TOP_K) for r in answerable_rows), len(answerable_rows)),
        "score_auroc": auroc([r["top_score"] for r in answerable_rows],
                             [r["top_score"] for r in unanswerable_rows]),
        "raw_score_auroc": auroc([r["top_raw_score"] for r in answerable_rows],
                                 [r["top_raw_score"] for r in unanswerable_rows]),
        "unanswerable_nonempty_rate": safe_rate(sum(1 for r in unanswerable_rows if r["n_results"]),
                                                len(unanswerable_rows)),
        **abstention_metrics(rows),
    }
    # "Empty result set" is the only implicit not-in-memory signal search has
    # today (metacognition tier 4). Informational, not gated.
    implicit = abstention_metrics([{**r, "abstained": r["n_results"] == 0} for r in rows])
    by_kind: Dict[str, Any] = {}
    for kind in ("answerable", "near_topic", "off_topic"):
        bucket = [r for r in rows if r["kind"] == kind]
        if not bucket:
            continue
        tiers: Dict[str, int] = {}
        for r in bucket:
            tiers[str(r["tier"])] = tiers.get(str(r["tier"]), 0) + 1
        by_kind[kind] = {
            "count": len(bucket),
            "top_score": score_summary(r["top_score"] for r in bucket),
            "top_raw_score": score_summary(r["top_raw_score"] for r in bucket),
            "empty_result_rate": safe_rate(sum(1 for r in bucket if r["n_results"] == 0), len(bucket)),
            "metacognition_tiers": tiers,
        }
    return {
        "suite": "abstention",
        "k": TOP_K,
        "overall": overall,
        "top_score": {
            "answerable": score_summary(r["top_score"] for r in answerable_rows),
            "unanswerable": score_summary(r["top_score"] for r in unanswerable_rows),
        },
        "top_raw_score": {
            "answerable": score_summary(r["top_raw_score"] for r in answerable_rows),
            "unanswerable": score_summary(r["top_raw_score"] for r in unanswerable_rows),
        },
        "implicit_empty_result_abstention": implicit,
        "by_kind": by_kind,
        "rows": rows,
        "elapsed_s": round(time.monotonic() - t0, 3),
    }


RUNNERS = {
    "dedup": run_dedup,
    "temporal": run_temporal,
    "abstention": run_abstention,
}


def run_suite(name: str) -> Dict[str, Any]:
    if name not in RUNNERS:
        raise ValueError(f"unknown memory-quality suite {name!r}; options: {list(RUNNERS)}")
    return RUNNERS[name]()
