"""Motivational entry gate — issue #116 Phase 1-B.

Composes the active profile (from `agentmemory.profiles`) and the
classified intent label (from `bin/intent_classifier.py`) into a
declarative suppression list of retrieval *strategies* that the memo
argues are categorically incompatible with the current task context.

The memo (issue #116 §2.4) frames this as the NAc-analog of motivational
entry gating: candidates incompatible with the current motivational
state are excluded from the strategy pool *before* scoring begins,
not downranked after.

Strategy taxonomy (mapped to brainctl's actual retrieval features):

- ``procedural_lookup``: search the `procedures` table (how-to content,
  workflow patterns). Suppressed for queries where step-by-step
  procedures have no bearing on the answer (most non-ops profiles,
  most non-procedural intents).
- ``episodic_association``: search the `events` table (the closest
  brainctl analog to "episodic memory" in the memo's sense —
  timestamped happenings, agent activity, decisions in flight).
  Suppressed for ops queries (where personal/agent history mostly
  doesn't matter) and procedural intents.
- ``temporal_chain_traversal``: apply `--temporal-expand-hours` to
  fetch temporal-neighbor memories around hits. Suppressed for
  research / writing profiles where temporal neighborhoods add noise.

Default mode is **shadow** — the gate computes which strategies would
be suppressed and logs them via the retrieval_pathway_log
(suppressed_strategies column) but does NOT alter retrieval behavior.
This matches the established convention in brainctl (thalamus shadow,
BG shadow, cerebellum shadow) and ensures we can validate the gate's
calibration against real outcomes before flipping enforcement.

Enforce mode flips on by setting ``BRAINCTL_MOTIVATIONAL_GATE_ENFORCE=1``.
When enforced, ``apply_suppressions`` returns a modified table list
and feature flags for the caller to use.

See also:
  - research/issue-116-audit-vs-origin-main.md — the audit memo that
    scoped this work.
  - research/brainctl-brain-architecture-issue-116.md §2.4 — the
    original memo's gate specification.
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

# Profile → suppressed strategies. Profiles missing from this map fall
# through to "no suppression" (full strategy pool).
#
# Adapted from memo §2.4 to brainctl's actual strategy taxonomy.
# Conservative defaults — when in doubt, do not suppress. Better to let
# a strategy through and learn it's noisy than to silently exclude a
# correct answer.
PROFILE_SUPPRESSIONS: dict[str, frozenset[str]] = {
    "writing": frozenset({"procedural_lookup", "temporal_chain_traversal"}),
    "research": frozenset({"procedural_lookup", "temporal_chain_traversal"}),
    "meeting": frozenset({"procedural_lookup"}),
    "ops": frozenset({"episodic_association"}),
    "networking": frozenset({"procedural_lookup"}),
}

# Intent → suppressed strategies. Used as a secondary signal when no
# explicit profile is passed. brainctl's intent classifier emits more
# labels than the memo proposed; mappings here are adapted from memo
# §2.4 plus extrapolation to brainctl's actual labels.
#
# Intents not in this map: gate does not fire from intent signal alone.
# That includes "general", "factual_lookup", "cross_reference",
# "research_concept", "orientation" — categories where the gate has no
# strong opinion and the full strategy pool is the safer default.
INTENT_SUPPRESSIONS: dict[str, frozenset[str]] = {
    "entity_lookup": frozenset({"procedural_lookup"}),
    "decision_rationale": frozenset({"procedural_lookup"}),
    "historical_timeline": frozenset({"procedural_lookup"}),
    "task_status": frozenset({"procedural_lookup"}),
    "how_to": frozenset({"episodic_association"}),  # procedural intent — events add noise
    "troubleshooting": frozenset({"episodic_association"}),
}


# Strategy → brainctl signal mapping. Used by apply_suppressions to
# translate abstract strategy names into concrete cmd_search inputs.
_STRATEGY_TO_TABLE: dict[str, str] = {
    "procedural_lookup": "procedures",
    "episodic_association": "events",
}

# Strategies that don't map to a table map to feature flags that
# cmd_search interprets separately. Currently only
# `temporal_chain_traversal` → `temporal_expand_hours`; encoded inline
# in apply_suppressions rather than a separate dict to keep the
# translation visible at the call site.

_FALSY = {"0", "false", "no", "off", ""}


def is_enforce_enabled() -> bool:
    """True iff BRAINCTL_MOTIVATIONAL_GATE_ENFORCE is set to a truthy value.

    Default is False — gate runs in shadow mode, logs decisions, but
    does not alter retrieval behavior.
    """
    raw = os.environ.get("BRAINCTL_MOTIVATIONAL_GATE_ENFORCE", "")
    return raw.strip().lower() not in _FALSY


def compute_suppressions(
    *,
    profile: Optional[str] = None,
    intent_label: Optional[str] = None,
) -> list[str]:
    """Compute the union of suppressed strategies for this (profile, intent).

    Returns a sorted list of strategy names. Empty list = no suppression
    (gate does not fire).

    Profile takes precedence in the sense that any profile suppression
    is included; intent adds additional suppressions on top. The two
    signals compose rather than override.
    """
    suppressed: set[str] = set()
    if profile and profile in PROFILE_SUPPRESSIONS:
        suppressed |= PROFILE_SUPPRESSIONS[profile]
    if intent_label and intent_label in INTENT_SUPPRESSIONS:
        suppressed |= INTENT_SUPPRESSIONS[intent_label]
    return sorted(suppressed)


def apply_suppressions(
    suppressed_strategies: Iterable[str],
    *,
    tables: list[str],
    temporal_expand_hours: Optional[int] = None,
) -> tuple[list[str], Optional[int]]:
    """Translate suppressed strategies into concrete cmd_search adjustments.

    Returns ``(filtered_tables, adjusted_temporal_expand_hours)``.

    No-op in shadow mode — callers gate this on ``is_enforce_enabled()``.
    When called, it WILL modify the inputs to remove suppressed tables
    and zero out suppressed feature flags.

    Conservative: never returns an empty tables list. If suppression
    would eliminate every table (shouldn't happen with the current
    mapping but kept as a safety net), the original tables list is
    returned unchanged. The gate should never starve retrieval of all
    candidates.
    """
    suppressed_set = set(suppressed_strategies)
    if not suppressed_set:
        return list(tables), temporal_expand_hours

    suppressed_tables = {
        _STRATEGY_TO_TABLE[s]
        for s in suppressed_set
        if s in _STRATEGY_TO_TABLE
    }
    filtered = [t for t in tables if t not in suppressed_tables]
    if not filtered:
        # Safety: never zero-out the table set.
        filtered = list(tables)

    adjusted_temporal = temporal_expand_hours
    if "temporal_chain_traversal" in suppressed_set:
        adjusted_temporal = 0

    return filtered, adjusted_temporal
