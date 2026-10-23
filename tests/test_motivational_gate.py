"""Tests for motivational_gate — issue #116 Phase 1-B.

Covers:
  - compute_suppressions: profile mapping
  - compute_suppressions: intent mapping
  - compute_suppressions: composition (profile + intent union)
  - compute_suppressions: empty case (no profile, no intent, unknown)
  - apply_suppressions: removes tables and zeros temporal expansion
  - apply_suppressions: safety floor (never empty tables)
  - is_enforce_enabled: env var parsing
"""
from __future__ import annotations

from agentmemory.motivational_gate import (
    PROFILE_SUPPRESSIONS,
    INTENT_SUPPRESSIONS,
    apply_suppressions,
    compute_suppressions,
    is_enforce_enabled,
)


def test_compute_suppressions_profile_only():
    # writing profile suppresses procedural_lookup + temporal_chain_traversal
    suppressed = compute_suppressions(profile="writing", intent_label=None)
    assert set(suppressed) == {"procedural_lookup", "temporal_chain_traversal"}
    assert suppressed == sorted(suppressed)


def test_compute_suppressions_intent_only():
    # entity_lookup intent suppresses procedural_lookup
    suppressed = compute_suppressions(profile=None, intent_label="entity_lookup")
    assert set(suppressed) == {"procedural_lookup"}


def test_compute_suppressions_composes_profile_and_intent():
    # ops (suppresses episodic_association) + how_to (suppresses
    # episodic_association) → union is just episodic_association
    suppressed = compute_suppressions(profile="ops", intent_label="how_to")
    assert set(suppressed) == {"episodic_association"}

    # writing + how_to → procedural + temporal + episodic
    suppressed = compute_suppressions(profile="writing", intent_label="how_to")
    assert set(suppressed) == {
        "procedural_lookup",
        "temporal_chain_traversal",
        "episodic_association",
    }


def test_compute_suppressions_empty_and_unknown():
    assert compute_suppressions(profile=None, intent_label=None) == []
    assert compute_suppressions(profile=None, intent_label="general") == []
    assert compute_suppressions(profile="unknown-profile", intent_label="factual_lookup") == []


def test_apply_suppressions_removes_procedures_table():
    tables = ["memories", "events", "decisions", "procedures"]
    filtered, temp = apply_suppressions(
        ["procedural_lookup"], tables=tables, temporal_expand_hours=24
    )
    assert "procedures" not in filtered
    assert set(filtered) == {"memories", "events", "decisions"}
    assert temp == 24  # not affected


def test_apply_suppressions_zeros_temporal_expansion():
    tables = ["memories", "events"]
    filtered, temp = apply_suppressions(
        ["temporal_chain_traversal"], tables=tables, temporal_expand_hours=48
    )
    assert filtered == tables
    assert temp == 0


def test_apply_suppressions_safety_never_empties_tables():
    # If only `procedures` was requested and procedural_lookup is
    # suppressed, the safety floor returns the original list.
    tables = ["procedures"]
    filtered, _ = apply_suppressions(
        ["procedural_lookup"], tables=tables, temporal_expand_hours=None
    )
    assert filtered == ["procedures"]  # safety: don't zero-out


def test_apply_suppressions_noop_when_no_suppressions():
    tables = ["memories", "events", "procedures"]
    filtered, temp = apply_suppressions(
        [], tables=tables, temporal_expand_hours=12
    )
    assert filtered == tables
    assert temp == 12


def test_is_enforce_enabled_default_off(monkeypatch):
    monkeypatch.delenv("BRAINCTL_MOTIVATIONAL_GATE_ENFORCE", raising=False)
    assert is_enforce_enabled() is False
    monkeypatch.setenv("BRAINCTL_MOTIVATIONAL_GATE_ENFORCE", "0")
    assert is_enforce_enabled() is False
    monkeypatch.setenv("BRAINCTL_MOTIVATIONAL_GATE_ENFORCE", "false")
    assert is_enforce_enabled() is False


def test_is_enforce_enabled_truthy_values(monkeypatch):
    for val in ("1", "true", "yes", "on", "TRUE"):
        monkeypatch.setenv("BRAINCTL_MOTIVATIONAL_GATE_ENFORCE", val)
        assert is_enforce_enabled() is True, f"expected truthy for {val!r}"


def test_mapping_tables_are_in_sync():
    # Every value in PROFILE_SUPPRESSIONS / INTENT_SUPPRESSIONS must be a
    # known strategy that apply_suppressions can act on. This catches
    # typos when adding a new mapping.
    KNOWN_STRATEGIES = {
        "procedural_lookup", "episodic_association", "temporal_chain_traversal",
    }
    for profile, suppressed in PROFILE_SUPPRESSIONS.items():
        unknown = suppressed - KNOWN_STRATEGIES
        assert not unknown, f"profile {profile}: unknown strategies {unknown}"
    for intent, suppressed in INTENT_SUPPRESSIONS.items():
        unknown = suppressed - KNOWN_STRATEGIES
        assert not unknown, f"intent {intent}: unknown strategies {unknown}"
