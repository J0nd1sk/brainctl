"""Regression tests for the v2 consolidated dispatcher.

These exist because PR #138 review surfaced concrete breakage:

* Several visible dispatchers (`lifecycle`, `reflexion`, `schedule`,
  `consolidation`, …) routed to handlers shaped as ``fn(args: dict)``
  but the dispatcher invoked them as ``fn(**args)``, producing
  argument-mismatch errors at call time.
* `vta_pathways` was hidden in `DEPRECATED_TOOL_NAMES` with no
  corresponding action wired into the `vta` subsystem dispatcher,
  violating the PR's "zero functionality loss" claim.

Both shapes (single-dict and **kwargs) are exercised here without a
DB connection so the test is hermetic.
"""
from __future__ import annotations

from agentmemory import mcp_tools_consolidated as mtc


# --------------------------------------------------------- _signature_kind probes


def test_single_dict_handler_is_detected():
    """Extension-module `_call_*` handlers shaped as fn(args: dict)
    must be classified as single_dict so the dispatcher passes a
    positional payload, not **kwargs."""
    def fake_handler(args: dict) -> dict:
        return {"echo": args}

    assert mtc._signature_kind(fake_handler) == "single_dict"


def test_kwargs_handler_is_detected():
    """`tool_*` functions in mcp_server.py use explicit kwargs."""
    def fake_handler(agent_id: str, query: str = "") -> dict:
        return {"agent_id": agent_id, "query": query}

    assert mtc._signature_kind(fake_handler) == "kwargs"


def test_zero_arg_handler_is_detected():
    """A handful of handlers (stats, weights, health) take no args."""
    def fake_handler() -> dict:
        return {"ok": True}

    assert mtc._signature_kind(fake_handler) == "zero"


# --------------------------------------------------------- _call_by_name routing


def test_call_by_name_routes_single_dict_handler(monkeypatch):
    """The exact bug from the PR #138 review: lifecycle(summary) calls
    a fn(args: dict) handler; the old dispatcher used fn(**args) and
    failed with argument mismatch."""
    captured: dict = {}

    def single_dict_handler(args: dict) -> dict:
        captured["args"] = args
        return {"ok": True, "shape": "single_dict"}

    monkeypatch.setattr(
        mtc, "_collect_dispatch",
        lambda: {"fake_lifecycle_summary": single_dict_handler},
    )
    # Clear the signature cache so re-running doesn't read a stale id.
    mtc._SIG_KIND_CACHE.clear()

    out = mtc._call_by_name(
        "fake_lifecycle_summary",
        {"agent_id": "test", "days": 7},
    )
    assert out == {"ok": True, "shape": "single_dict"}
    assert captured["args"] == {"agent_id": "test", "days": 7}


def test_call_by_name_routes_kwargs_handler(monkeypatch):
    captured: dict = {}

    def kwargs_handler(agent_id: str, content: str, **_kw) -> dict:
        captured["agent_id"] = agent_id
        captured["content"] = content
        return {"ok": True, "shape": "kwargs"}

    monkeypatch.setattr(
        mtc, "_collect_dispatch",
        lambda: {"fake_memory_add": kwargs_handler},
    )
    mtc._SIG_KIND_CACHE.clear()

    out = mtc._call_by_name(
        "fake_memory_add",
        {"agent_id": "test", "content": "hi"},
    )
    assert out == {"ok": True, "shape": "kwargs"}
    assert captured["agent_id"] == "test"
    assert captured["content"] == "hi"


def test_call_by_name_routes_zero_arg_handler(monkeypatch):
    def zero_handler() -> dict:
        return {"ok": True, "shape": "zero"}

    monkeypatch.setattr(
        mtc, "_collect_dispatch",
        lambda: {"fake_stats": zero_handler},
    )
    mtc._SIG_KIND_CACHE.clear()

    out = mtc._call_by_name("fake_stats", {})
    assert out == {"ok": True, "shape": "zero"}


def test_call_by_name_fallback_when_signature_misclassified(monkeypatch):
    """If a handler's signature is unusual enough to be misclassified
    (e.g. it accepts `args` as its only named kw but takes a dict),
    the dispatcher must still be able to call it via the other shape."""
    captured: dict = {}

    def odd_handler(**kwargs) -> dict:
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(
        mtc, "_collect_dispatch",
        lambda: {"fake_odd": odd_handler},
    )
    mtc._SIG_KIND_CACHE.clear()
    # Force the wrong classification, then prove the fallback rescues it.
    mtc._SIG_KIND_CACHE[id(odd_handler)] = "single_dict"

    out = mtc._call_by_name("fake_odd", {"a": 1, "b": 2})
    # `fn({"a": 1, "b": 2})` fails because **kwargs receives a single
    # positional. Fallback retries fn(**args) and succeeds.
    assert out == {"ok": True}
    assert captured == {"a": 1, "b": 2}


def test_call_by_name_missing_tool_returns_clean_error():
    out = mtc._call_by_name("definitely_not_a_real_tool_name", {})
    assert "error" in out
    assert "consolidated routing miss" in out["error"]


# --------------------------------------------------------- vta_pathways routing


def test_vta_pathways_action_is_routed():
    """PR #138 review P1: vta_pathways was hidden with no v2
    replacement. After the fix, ('vta', 'pathways') routes to the
    underlying vta_pathways tool."""
    assert ("vta", "pathways") in mtc._EMIT_ROUTE
    assert mtc._EMIT_ROUTE[("vta", "pathways")] == "vta_pathways"


def test_vta_dispatcher_exposes_pathways_in_actions():
    """`subsystem_list_actions(name='vta')` must include 'pathways'."""
    # The actions list comes from _EMIT_ROUTE keys filtered by subsystem.
    vta_actions = {
        action for (sub, action) in mtc._EMIT_ROUTE if sub == "vta"
    }
    assert "pathways" in vta_actions


# --------------------------------------------------------- DEPRECATED_TOOL_NAMES audit


def test_real_lifecycle_summary_handler_classifies_as_single_dict():
    """Integration check: the actual handler bound in the dispatch
    for `lifecycle_summary` must classify as single_dict — the
    pre-fix behaviour treated it as kwargs and produced
    TypeError at call time. This is the regression smoking gun."""
    mtc._SIG_KIND_CACHE.clear()
    disp = mtc._collect_dispatch()
    fn = disp.get("lifecycle_summary")
    assert fn is not None, "lifecycle_summary missing from dispatch"
    assert mtc._signature_kind(fn) == "single_dict"


def test_real_reflexion_list_handler_classifies_as_single_dict():
    mtc._SIG_KIND_CACHE.clear()
    disp = mtc._collect_dispatch()
    fn = disp.get("reflexion_list")
    assert fn is not None, "reflexion_list missing from dispatch"
    assert mtc._signature_kind(fn) == "single_dict"


def test_real_consolidation_events_handler_classifies_as_single_dict():
    mtc._SIG_KIND_CACHE.clear()
    disp = mtc._collect_dispatch()
    fn = disp.get("consolidation_events")
    assert fn is not None, "consolidation_events missing from dispatch"
    assert mtc._signature_kind(fn) == "single_dict"


def test_every_deprecated_v1_tool_has_a_v2_route():
    """For every name we hide from list_tools, at least one v2 route
    must point at it. Otherwise we ship a hidden-with-no-replacement
    bug (the exact class of bug PR #138 review caught for
    vta_pathways)."""
    routed_targets: set[str] = set()
    routed_targets.update(mtc._STATUS_ROUTE.values())
    routed_targets.update(mtc._EMIT_ROUTE.values())
    routed_targets.update(mtc._REGISTER_ROUTE.values())
    routed_targets.update(mtc._HISTORY_ROUTE.values())
    routed_targets.update(mtc._CONFIGURE_ROUTE.values())
    for table in mtc._TOPIC_ROUTES.values():
        routed_targets.update(table.values())

    orphans = mtc.DEPRECATED_TOOL_NAMES - routed_targets
    # We accept a curated list of pure-aliases / admin-only / removed
    # tools that intentionally have no v2 route. Anything else is a bug.
    accepted_orphans = getattr(mtc, "_ACCEPTED_HIDDEN_ORPHANS", frozenset())
    real_orphans = orphans - accepted_orphans
    assert not real_orphans, (
        f"Deprecated v1 tools have NO v2 route — they're unreachable: "
        f"{sorted(real_orphans)[:10]}"
        + (f" (and {len(real_orphans) - 10} more)" if len(real_orphans) > 10 else "")
    )
