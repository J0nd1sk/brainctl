# Issue #116 — Memo gaps re-audited against origin/main reality

**Date:** 2026-05-19T22:00 EDT
**Repo state:** `origin/main` @ `646c33c` ("final brain batch"), brainctl v2.7.0.
**Audit driver:** claude-code-brainctl-architecture-review (correcting my own prior stale-checkout error)
**Supersedes:** the "What's actually missing" section in `research/issue-116-comparison.md`. That memo's v1.5.2 framing is wrong; this file is the corrected reading.

---

## The correction in one paragraph

My local checkout was on `2.2.4/gemini-plugin` with a `main` that hadn't been refreshed since v1.5.2. Origin/main is at **v2.7.0 + a "final brain batch" of six additional subsystems** (ACC, DMN, drives, insula, PFC slots, entorhinal grid) shipped on top, plus BG (054/055), cerebellum (056/057), and Velamj's procedural memory layer (052 / v2.7.0). The issue #116 memo's "v2.7.0" framing was correct all along. My earlier "the paper has the wrong version" finding was wrong.

The substantive consequence: **most of what the memo says is missing is already shipped, learning from real outcomes today, gated behind a Phase 4 enforcement flip.**

---

## Reality check on each of the memo's 8 gaps

Status legend: **SHIPPED** = schema + wiring + active learning. **SCHEMA** = tables exist, wiring still TBD. **GAP** = real, still missing.

### Gap 1 — Closed feedback loop from retrieval outcome → policy: **SHIPPED**

- **Schema** (migrations 054, 055):
  - `bg_actions` — registered action catalog, 44 rows seeded
  - `bg_striatal_weights` — opponent Go/NoGo + **5-expectile distributional value** (q10/q30/q50/q70/q90 — more sophisticated than the memo's proposed `(m, s)`)
  - `bg_eligibility_traces` — credit assignment over delays
  - `bg_td_events` — TD-error broadcast bus, `δ = utility + γ·V(s') − V(s)`
  - `bg_holds` — hyperdirect halt log
  - `bg_modulators` — single row, three independent knobs (tonic DA / LC-NE / serotonin)
  - `bg_shadow_decisions` — audit log of would-be decisions
- **Wiring** (`bg_shadow.py`, `mcp_server.py:3265-3295`):
  - Every MCP dispatch is wrapped: `consult_for_dispatch` deposits an eligibility trace
  - `outcome_annotate` triggers `broadcast_td_error`, which consumes active eligibility traces and updates striatal weights via opponent three-factor learning:
    - `δ > 0`: `w_go += lr·trace·δ` (D1 LTP), `w_nogo -= lr·trace·δ/2` (D2 LTD weaker)
    - `δ < 0`: `w_nogo += lr·trace·|δ|` (D2 LTP), `w_go -= lr·trace·|δ|/2` (D1 LTD weaker)
- **Retrieval registration:** `memory_search` is a `bg_action` in the `oculomotor` loop. Commit `32c466e` seeded 44 actions live.
- **Enforcement:** still shadow (bg_shadow.py header: "weights move from real outcomes, but the gate doesn't act on them yet. That flip is Phase 4").

> **The memo's central thesis — "brainctl's retrieval policy is permanently static" — is false as of v2.7.0+.** The policy is actively learning from real outcomes today. The only thing not happening yet is enforcement.

### Gap 2 — Retrieval forward model: **SHIPPED**

- **Schema** (migration 056): `cerebellum_modules`, `cerebellum_weights`, `cerebellum_predictions` (`predicted_value`, `observed_value`, `delta_forward`), `cerebellum_traces`, `cerebellum_boundaries`.
- **The retrieval-specific module exists by name:** `oculomotor_partner` — "predicts retrieval relevance" per the migration header.
- **Wiring** (`cerebellum_shadow.py`):
  - Three predictions fired per dispatch: `success_probability`, `expected_latency_ms`, `expected_outcome_class`
  - Predictions auto-observed after dispatch with measured latency + success/error
  - LTD-analog weight updates at learning rate 0.05, trace decay 0.95
  - Boundary markers fired when `|delta_forward| > 0.5` (the cerebellum-system sentinel memory referenced in agent_orient is from this path)
- Performance-optimized: cached registration lookups, batched-transaction writes.

> **The memo's "no retrieval forward model" claim is false.** The forward model exists, runs on every memory_search, and updates its weights from prediction error.

### Gap 3 — TRN-style competitive domain suppression: **SHIPPED at write path; GAP at read path**

- Thalamus Phase 1 + Phase 2 (migrations 050, 053). Sector classifier in `thalamus_shadow.py`. Hookpoint in `_gates.py::run_write_gate` records would-be downgrades.
- Live smoke during the May 15 cookoff showed PII-sensitive content down-weighted by sector gain (`integrated=0.511 vs 0.569`).
- **Read-path domain suppression is residual.** The memo specifically wants suppression *before candidate assembly* at retrieval time. Thalamus shadow is currently write-path only.

### Gap 4 — Strategy-level selection with active suppression: **PARTIAL**

- `bg_actions` catalog includes the *tool-level* strategies: `memory_search`, `vsearch`, `entity_search`, `event_search`, `search_patterns`, `push`, `agent_orient`, `context_search`, `handoff_latest`, `entity_get` — 10 in the oculomotor loop.
- bg_striatal_weights track Go/NoGo per (action, context_hash). Opponent suppression is possible because D2/NoGo is a first-class weight.
- **What's not done:** the *intra-search* strategies (`mode=fts|vector|hybrid_rrf`, `pagerank_boost`, `multi_pass`, `temporal_expand_hours`) are arguments inside `memory_search`, not first-class `bg_actions`. The BG can learn "use vsearch instead of memory_search for X" but can't yet learn "use hybrid_rrf mode of memory_search instead of FTS mode for X" — unless those distinctions surface in `context_hash`.

### Gap 5 — Driver/modulator distinction in writes: **DIFFERENT CUT shipped, memo's specific cut still GAP**

- **Shipped:** D-MEM tiered writes (migration 031, three-tier skip/construct/full) routes writes by surprise/RPE. Thalamus Phase 2 shadow consult at the write gate. Free-energy + memory_calibration + attention_snapshot.
- **Not shipped:** the memo's specific INSERT-vs-UPDATE / category-in-(identity,preference) classification. The shipped cut is RPE-driven (arguably more powerful); the memo's cut is operation-and-category-driven (more declarative). They're complementary, not equivalent.
- **Verdict:** the memo's recommendation could ship as a small addition. Worth deciding whether D-MEM's RPE routing already captures the same value before duplicating the gate.

### Gap 6 — Motivational entry gating using profile + intent: **REAL GAP**

- Infrastructure exists: `profiles.py` (ops/research/writing/meeting/networking) + `bin/intent_classifier.py`.
- Not yet composed into a pre-dispatch strategy-suppression filter on the read path.
- The memo's §2.4 implementation (with the profile-to-excluded-strategy and intent-to-excluded-strategy mappings) is implementable as-is on top of shipped infra.

### Gap 7 — Hyperdirect fast veto: **SCHEMA-ONLY**

- `bg_holds` table with `reason CHECK IN ('conflict','surprise','explicit_stop')` exists.
- Wiring into dispatch decision is **Phase 4 enforcement** territory — gated behind the same flip that turns on BG action selection.

### Gap 8 — Temporal pre-staging (memo flagged as speculative): **NOT ADDRESSED**, precursor present

- `cerebellum_boundaries` fire workspace_broadcasts at high prediction-error transitions. That's the anticipatory-signaling precursor.
- Pre-staging itself remains future work as the memo predicted.

---

## What's actually missing — the residual gap list

After subtracting what's shipped from what the memo asked for, the **real** residual work is:

1. **Pathway-fingerprint indexability.** The BG learns at `(action, context_hash)` granularity. For the BG to differentiate `mode=fts` from `mode=vector` from `mode=hybrid_rrf` from `pagerank_boost>0` from `multi_pass=true` from `temporal_expand_hours>0`, those distinctions need to surface either in `context_hash` or in a parallel light pathway log keyed by `td_event_id`. Estimated: ~100-200 LoC + small migration.

2. **Motivational entry gate composition.** Compose `profiles` + `intent_classifier` into a pre-`memory_search` strategy-suppression filter per memo §2.4. Estimated: ~150-300 LoC, no migration.

3. **Smooth sigmoid read-gate threshold.** Hard cutoffs likely remain. Implement memo §1.4 Stage 2 smooth threshold with learnable slope/midpoint. Estimated: ~200-400 LoC.

4. **Domain separability assessment** (research, prerequisite for memo §3 read-path TRN suppression). Empirical question — do brainctl's memory domains cluster cleanly in embedding space? Estimated: a 1-day Explore-agent task, deliverable is a silhouette score + 2D UMAP + recommendation.

5. **Driver/modulator INSERT-vs-UPDATE write split** (memo §6.3 Step 6). Decide first whether D-MEM tiers already capture this value. If yes, drop; if no, ~300-500 LoC refactor of `_gates.py`.

6. **Phase 4 enforcement flip** (brainctl's own roadmap, not a memo gap, but the gating step). Without this, none of the shipped learning influences live retrieval. The memo's value-add to retrieval policy is downstream of this flip happening.

---

## Implications for the Phase 1 plan

The plan at `~/Documents/Agent Memory/_shared-brain/plans/plan-20260519-213200-brainctl-issue-116-feedback-loop-c1c0de/plan.md` is **mostly obsolete**.

Specifically:
- **No new `retrieval_ledger` table.** `bg_td_events JOIN cerebellum_predictions` IS the ledger. They just need the pathway-fingerprint columns or a sidecar.
- **No new `retrieval_outcome_observe` MCP tool.** `outcome_annotate` is the existing surface and is already wired to `broadcast_td_error`.
- **No new `cmd_search` hookpoint.** Dispatch already hooks at `mcp_server.py:3265`. The BG and cerebellum already see every search.
- **No "strategy identity refactor" Phase 2.** `bg_actions` already discriminates between tool-level strategies. Intra-search sub-strategy registration is a small extension, not a refactor.
- **Migration 054 is taken (BG). Next free is whatever follows 065** — would need to be ~066 if a new migration is needed at all, but most of the residual work needs no new tables.

**Corrected Phase 1 scope** (smallest meaningful slice that earns its keep):

| Track | Scope | LoC est | Migration? |
|---|---|---|---|
| A — pathway-fingerprint surface | Add `mode`, `table_distribution`, `rrf_contribution_ratio`, `intent_label`, `active_profile` columns to `bg_td_events` OR new sidecar `bg_retrieval_pathway_log(td_event_id, ...)` | 100-200 | 1 small migration |
| B — emit pathway fingerprint | Wire `memory_search` to populate the fields when `outcome_annotate` fires `broadcast_td_error` | 50-150 | none |
| C — motivational entry gate | Compose `profiles.resolve_profile()` + `intent_classifier.classify()` into a pre-search strategy-suppression filter | 150-300 | none |
| D — tests + docs | Standard | 100-200 | none |

**Total:** ~400-850 LoC, one migration, no new MCP tool, no refactor. Solo-able in 1-2 sessions. Codex orchestration is **overkill for this size** — the value of orchestration was for the larger original Phase 1, which turns out to already be shipped.

---

## Staffing — revised

| Phase | Original staffing | Revised staffing | Reason |
|---|---|---|---|
| Phase 1 (corrected scope above) | claude-code solo | **claude-code solo** | Smaller than original; ~1-2 sessions, no codex needed |
| Phase 2 (strategy refactor) | codex | **N/A — already shipped as `bg_actions`** | Refactor was a misread of shipped state |
| Phase 3 (TRN domain suppression) | subagent assessment + impl | **subagent assessment first** | Still valid; precondition unmet |
| Phase 4 (driver/modulator) | claude-code solo | **decide if D-MEM already covers it** | Possibly redundant |
| Phase 5+ (forward model) | premature | **already shipped, just collect data** | Forward model lives; data accumulates |

**Net:** codex orchestration is no longer the right move for the corrected scope. The post-audit plan is small enough for me solo. Codex was the right call against the original (stale-checkout-based) plan; against reality, it's not.

---

## Action items

1. ~~Re-audit issue #116 gap analysis against current origin/main (v2.7.0)~~ — **complete (this file)**
2. Correct `research/issue-116-comparison.md` to reflect this audit's findings — next
3. Replace the Phase 1 plan with the corrected scope above
4. Decide with user: does the corrected Phase 1 (pathway fingerprint + motivational gate + sigmoid read gate) get built now, or is the value proposition too thin given the BG/cerebellum loops are already operational and the bigger question is the Phase 4 enforcement flip?
