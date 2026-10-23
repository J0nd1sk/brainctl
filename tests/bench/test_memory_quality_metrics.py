"""Unit tests for the memory-quality bench metrics (tests.bench.memory_quality).

Pure-function tests on hand-built rows, plus fixture sanity checks and one
end-to-end smoke run of the (fast) abstention suite through the real
write + search path.
"""

from __future__ import annotations

import os

import pytest

from tests.bench import memory_fixtures as fx
from tests.bench import memory_quality as mq


# ---------------------------------------------------------------------------
# safe_rate / is_collapsed
# ---------------------------------------------------------------------------

def test_safe_rate_handles_zero_denominator():
    assert mq.safe_rate(1, 3) == 0.3333
    assert mq.safe_rate(0, 0) == 0.0
    assert mq.safe_rate(0, 0, empty=1.0) == 1.0


@pytest.mark.parametrize("first,second,collapsed", [
    (True, True, False),    # both kept -> separated
    (True, False, True),    # second merged / rejected
    (False, True, True),    # first superseded / retired
    (False, False, True),
])
def test_is_collapsed(first, second, collapsed):
    assert mq.is_collapsed(first, second) is collapsed


# ---------------------------------------------------------------------------
# dedup_metrics
# ---------------------------------------------------------------------------

def _pair(kind, collapsed, **extra):
    return {"kind": kind, "collapsed": collapsed, **extra}


def test_dedup_metrics_perfect_gate():
    rows = [_pair("exact", True), _pair("paraphrase", True),
            _pair("near_miss", False), _pair("near_miss", False)]
    o = mq.dedup_metrics(rows)["overall"]
    assert o["duplicate_suppression_rate"] == 1.0
    assert o["false_merge_rate"] == 0.0
    assert o["separation_accuracy"] == 1.0


def test_dedup_metrics_mixed_and_by_kind():
    rows = [
        _pair("exact", True), _pair("exact", True),
        _pair("surface", False),
        _pair("paraphrase", False),
        _pair("near_miss", True), _pair("near_miss", False),
        _pair("near_miss", False), _pair("near_miss", False),
    ]
    m = mq.dedup_metrics(rows)
    o = m["overall"]
    assert o["n_duplicates"] == 4 and o["n_near_miss"] == 4
    assert o["duplicate_suppression_rate"] == 0.5
    assert o["false_merge_rate"] == 0.25
    # 2 suppressed dupes + 3 separated near-misses out of 8
    assert o["separation_accuracy"] == 0.625
    assert m["by_kind"]["exact"] == {"count": 2, "collapse_rate": 1.0}
    assert m["by_kind"]["near_miss"]["collapse_rate"] == 0.25


def test_dedup_metrics_excludes_invalid_rows():
    rows = [_pair("exact", True), _pair("exact", False, invalid="first write rejected")]
    o = mq.dedup_metrics(rows)["overall"]
    assert o["n_pairs"] == 1 and o["n_invalid"] == 1
    assert o["duplicate_suppression_rate"] == 1.0


# ---------------------------------------------------------------------------
# temporal_query_metrics / temporal_metrics
# ---------------------------------------------------------------------------

def test_rank_of():
    assert mq.rank_of([5, 7, 9], 7) == 2
    assert mq.rank_of([5, 7, 9], 4) is None
    assert mq.rank_of([5, 7, 9], None) is None


def test_temporal_latest_first_no_intrusion():
    m = mq.temporal_query_metrics([30, 99, 98], latest_id=30, stale_ids=[10, 20], k=5)
    assert m["latest_at_1"] == 1.0 and m["latest_rr"] == 1.0
    assert m["stale_in_top_k"] == 0.0 and m["stale_above_latest"] == 0.0


def test_temporal_stale_ranked_above_latest():
    m = mq.temporal_query_metrics([10, 30, 20], latest_id=30, stale_ids=[10, 20], k=5)
    assert m["latest_rank"] == 2 and m["latest_at_1"] == 0.0
    assert m["latest_rr"] == 0.5
    assert m["stale_in_top_k"] == 1.0 and m["stale_above_latest"] == 1.0


def test_temporal_stale_below_latest_still_intrudes_top_k():
    m = mq.temporal_query_metrics([30, 10], latest_id=30, stale_ids=[10], k=5)
    assert m["latest_at_1"] == 1.0
    assert m["stale_in_top_k"] == 1.0
    assert m["stale_above_latest"] == 0.0


def test_temporal_stale_outside_window_is_not_top_k_intrusion():
    ranked = [30, 1, 2, 3, 4, 10]
    m = mq.temporal_query_metrics(ranked, latest_id=30, stale_ids=[10], k=5)
    assert m["stale_in_top_k"] == 0.0 and m["stale_above_latest"] == 0.0


def test_temporal_latest_missing_counts_stale_as_above():
    m = mq.temporal_query_metrics([10], latest_id=None, stale_ids=[10], k=5)
    assert m["latest_rank"] is None and m["latest_in_top_k"] == 0.0
    assert m["stale_above_latest"] == 1.0


def test_temporal_metrics_aggregate():
    rows = [
        mq.temporal_query_metrics([30], 30, [10]),
        mq.temporal_query_metrics([10, 30], 30, [10]),
    ]
    agg = mq.temporal_metrics(rows, n_updates=4, n_updates_lost=1)
    assert agg["n_queries"] == 2
    assert agg["latest_p_at_1"] == 0.5
    assert agg["latest_mrr"] == 0.75
    assert agg["stale_above_latest_rate"] == 0.5
    assert agg["update_write_lost_rate"] == 0.25


# ---------------------------------------------------------------------------
# score_summary / auroc
# ---------------------------------------------------------------------------

def test_score_summary_quantiles():
    s = mq.score_summary([4.0, 1.0, 3.0, 2.0, 5.0])
    assert s == {"n": 5, "mean": 3.0, "min": 1.0, "p25": 2.0,
                 "median": 3.0, "p75": 4.0, "max": 5.0}


def test_score_summary_empty_and_single():
    assert mq.score_summary([])["n"] == 0
    s = mq.score_summary([0.7])
    assert s["min"] == s["median"] == s["max"] == 0.7


def test_auroc_extremes_and_ties():
    assert mq.auroc([3, 4], [1, 2]) == 1.0
    assert mq.auroc([1, 2], [3, 4]) == 0.0
    assert mq.auroc([1.1, 1.1], [1.1, 1.1]) == 0.5   # constant score: no signal
    assert mq.auroc([2, 1], [1]) == 0.75
    assert mq.auroc([], [1]) == 0.5


# ---------------------------------------------------------------------------
# resolve_answerable / abstention_metrics
# ---------------------------------------------------------------------------

def test_resolve_answerable_top_level_field_wins():
    assert mq.resolve_answerable({"answerable": False}) == (False, "answerable_field")
    assert mq.resolve_answerable(
        {"answerable": True, "metacognition": {"answerability_score": 0.1, "abstained": True}}
    ) == (True, "answerable_field")


def test_resolve_answerable_metacognition_fallbacks():
    assert mq.resolve_answerable({"metacognition": {"answerable": False}}) == (
        False, "metacognition.answerable")
    assert mq.resolve_answerable(
        {"metacognition": {"answerability_score": 0.2, "abstained": True}}
    ) == (False, "metacognition.abstained")


def test_resolve_answerable_placeholder_when_no_signal():
    # cmd_search today: answerability_score is None and abstained False.
    payload = {"metacognition": {"answerability_score": None, "abstained": False}}
    assert mq.resolve_answerable(payload) == (True, "placeholder_all_answerable")
    assert mq.resolve_answerable({}) == (True, "placeholder_all_answerable")
    assert mq.resolve_answerable(None) == (True, "placeholder_all_answerable")


def _q(should, did):
    return {"should_abstain": should, "abstained": did}


def test_abstention_metrics_never_abstains_scores_zero():
    rows = [_q(True, False), _q(True, False), _q(False, False)]
    m = mq.abstention_metrics(rows)
    assert m == {"abstention_precision": 0.0, "abstention_recall": 0.0,
                 "abstention_f1": 0.0, "false_abstention_rate": 0.0}


def test_abstention_metrics_mixed():
    rows = [_q(True, True), _q(True, False), _q(False, True), _q(False, False)]
    m = mq.abstention_metrics(rows)
    assert m["abstention_precision"] == 0.5
    assert m["abstention_recall"] == 0.5
    assert m["abstention_f1"] == 0.5
    assert m["false_abstention_rate"] == 0.5


# ---------------------------------------------------------------------------
# compare_suite (direction-aware >2% gate)
# ---------------------------------------------------------------------------

_GATES = (("overall.good", "higher"), ("overall.bad", "lower"))


def test_compare_suite_within_tolerance_passes():
    base = {"overall": {"good": 0.50, "bad": 0.20}}
    cur = {"overall": {"good": 0.49, "bad": 0.21}}
    assert mq.compare_suite(cur, base, _GATES)["ok"] is True


def test_compare_suite_higher_is_better_drop_fails():
    base = {"overall": {"good": 0.50, "bad": 0.20}}
    cur = {"overall": {"good": 0.47, "bad": 0.20}}
    diff = mq.compare_suite(cur, base, _GATES)
    assert diff["ok"] is False
    assert [f["metric"] for f in diff["failing"]] == ["overall.good"]


def test_compare_suite_lower_is_better_rise_fails_and_drop_passes():
    base = {"overall": {"good": 0.50, "bad": 0.20}}
    assert mq.compare_suite({"overall": {"good": 0.5, "bad": 0.25}}, base, _GATES)["ok"] is False
    assert mq.compare_suite({"overall": {"good": 0.5, "bad": 0.0}}, base, _GATES)["ok"] is True


def test_compare_suite_missing_keys_are_informational():
    diff = mq.compare_suite({"overall": {"good": 0.1}}, {"overall": {}}, _GATES)
    assert diff["ok"] is True
    assert set(diff["missing"]) == {"overall.good", "overall.bad"}


def test_get_path():
    assert mq.get_path({"a": {"b": {"c": 3}}}, "a.b.c") == 3
    assert mq.get_path({"a": {}}, "a.b.c") is None


def test_every_gate_resolves_against_committed_baseline():
    for suite, gates in mq.GATES.items():
        base = mq.load_baseline(suite)
        assert base is not None, f"missing baseline for {suite}"
        for path, direction in gates:
            assert direction in ("higher", "lower")
            assert mq.get_path(base, path) is not None, f"{suite}: {path}"


# ---------------------------------------------------------------------------
# Fixture sanity
# ---------------------------------------------------------------------------

def test_dedup_fixture_shape():
    keys = [p.key for p in fx.DEDUP_PAIRS]
    assert len(keys) == len(set(keys))
    kinds = {p.kind for p in fx.DEDUP_PAIRS}
    assert kinds == set(fx.DUPLICATE_KINDS) | {fx.NEAR_MISS_KIND}
    for p in fx.DEDUP_PAIRS:
        if p.kind == "exact":
            assert p.first == p.second
        else:
            assert p.first != p.second


def test_temporal_fixture_shape():
    for f in fx.TEMPORAL_FACTS:
        assert len(f.versions) >= 2 and f.queries
        assert len(set(f.versions)) == len(f.versions)


def test_abstention_fixture_gold_keys_exist():
    corpus_keys = {k for k, _, _ in fx.ABSTENTION_CORPUS}
    for q in fx.ABSTENTION_QUERIES:
        if q.kind == "answerable":
            assert q.gold in corpus_keys
        else:
            assert q.gold is None


# ---------------------------------------------------------------------------
# End-to-end smoke (real memory add + cmd_search on a throwaway brain.db)
# ---------------------------------------------------------------------------

def test_abstention_suite_smoke_runs_and_restores_env():
    before = {k: os.environ.get(k) for k in ("BRAINCTL_DB", "BRAIN_DB", "BRAINCTL_OLLAMA_URL")}
    result = mq.run_abstention()
    after = {k: os.environ.get(k) for k in before}
    assert before == after
    o = result["overall"]
    assert o["n_queries"] == len(fx.ABSTENTION_QUERIES)
    assert 0.0 <= o["score_auroc"] <= 1.0
    assert o["answerability_source"]
