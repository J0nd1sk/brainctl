# Issue #116 — Architecture memo vs. brainctl v1.5.2 reality

**Paper:** *Thalamus, Basal Ganglia, and Cerebellum: Toward a Biologically Grounded Architecture for brainctl* (Claude + @crystalwizard, May 17 2026).
**Local copy:** `research/brainctl-brain-architecture-issue-116.md`
**Compared against:** `origin/main` @ v1.5.2 (commit `e63b828`).

---

## TL;DR

The memo is well-cited (most claims verified from primary sources), the gap analysis is broadly correct about what's missing, and the BG/cerebellum prescriptions are concrete enough to implement. **Two important caveats:**

1. The memo says "brainctl v2.7.0" throughout. The repo is on v1.5.2. The version string is wrong; the architectural assessment is still mostly correct because what they're describing as "present in v2.7.0" maps to subsystems that already exist in v1.5.2 (write gate, profiles, intent router, salience routing, consolidation, `retrieval_prediction_error` column). They acknowledge this in §7 limitation 1.
2. The memo **under-credits** several recent shipped subsystems that already implement, or partly implement, the feedback-loop machinery it asks for — most notably **D-MEM RPE routing (#54)**, the **three-phase dream cycle (#61)**, **memory immunity / quarantine**, **allostatic consolidation forecasts (#53)**, and `free_energy_check`. None of these appear in the memo's coverage tables.

---

## Section 1 — Paper summary

Three deep-brain systems mapped to a memory-system architecture:

- **Thalamus.** Driver vs. modulator inputs; tonic vs. burst relay modes; TRN as competitive lateral inhibition between relay channels. Architectural ask: distinguish content-writes from mode-control writes at the gate; categorical domain suppression *before* candidate assembly; query-atomic mode-locking between tonic retrieval and consolidation modes; split read-gate vs. write-gate with two-stage read gate (domain suppression → smooth sigmoid item threshold).
- **Basal ganglia.** Direct/indirect/hyperdirect pathway selection over options; dopamine reward-prediction-error teaching signal; habit formation. **Key refinement:** Möller-Manohar-Bogacz "scaled prediction error" [33] — per-strategy `(m, s)` mean + uncertainty, with `e = obs − m`, `δ = e/(s+ε)`, update `m` from `e`, update strategy weights from `δ`. Architectural ask: strategy-level selection (above the candidate reranker), hyperdirect fast-veto on incompatible strategies, motivational entry gating using the profile+intent infra already in brainctl, and the closed feedback loop from retrieval-outcome → strategy policy.
- **Cerebellum.** Granule-cell expansion + parallel-fiber/Purkinje LTD as supervised learning at the *pathway* level; forward models (predict-then-correct). Architectural ask: a retrieval forward model keyed on query-type signature that predicts which mode (FTS / vector / hybrid-RRF) and which tables will surface useful results; pathway-level error attribution distinct from BG strategy-level error; read-gate ↔ forward-model coupling (high prediction-error retrievals need higher item-level relevance scores to pass).
- **Closed loop synthesis.** All three converge on a *two-speed motif*: a fast feedforward prediction + a slower feedback correction. Memo's central thesis is that brainctl already has storage and partial gating, but the **loop isn't closed** because the system can't see downstream outcomes.

**Observability is the prerequisite for everything else.** Two paths offered: explicit caller callbacks (cleaner signal, integration friction) or internal proxy signals (zero friction, ambiguous). Either way: build a retrieval event ledger with pathway-fingerprint fields (mode, table distribution, RRF contribution ratio) from day one, because those can't be reconstructed retroactively.

**Suggested order:** (1) solve observability + build ledger, (2) close BG feedback loop with SPE, (3) TRN domain suppression *iff* separability assessment passes, (4) forward model, (5) pathway-level attribution, (6) driver/modulator write split, (7) temporal pre-staging (speculative).

**Citation quality.** All citations primary-source-verified except [14] (Ito 1989, paywalled — confirmed via secondary). [33] Möller et al. is the load-bearing computational paper for the SPE math and is open-access verified. The hyperdirect-pathway story is up-to-date (Chen 2020, Koketsu 2021). They explicitly removed three citations they couldn't verify rather than leave them in.

---

## Section 2 — How it lands against the v1.5.2 reality

### What the memo gets right about brainctl

| Memo claim | Repo state | Verdict |
|---|---|---|
| Write gate exists, partial thalamic-style gating | `src/agentmemory/_gates.py::run_write_gate` + `lib/write_decision.py` (W(m) worthiness gate) | ✅ Accurate |
| Salience routing exists, partial | `bin/salience_routing.py` + `mcp_tools_*` salience surfaces | ✅ Accurate |
| Consolidation cycles structurally analogous to offline replay | `dream.py` three-phase (#61), `mcp_tools_consolidation.py`, `mcp_tools_allostatic.py` | ✅ Accurate (and undercredited — see below) |
| Temporal context system present | temporal abstraction PR (#52): `abstract_summarize`, `zoom_out`, `zoom_in`, `temporal_map` | ✅ Accurate |
| Retrieval executive + listwise reranker exists as draft | PR #96 (Velamj) — confirmed DRAFT, 4165 additions, retrieval/operator/reranker code | ✅ Accurate |
| `retrieval_prediction_error` is a column already | `db/init_schema.sql:79` — `retrieval_prediction_error REAL DEFAULT NULL` | ✅ Verified |
| `_retrieval_practice_boost` mechanism reads it | confirmed in `mcp_tools_consolidation.py` reading the column on labile-window reclassification | ✅ Verified |
| Profile system + intent router as candidates for motivational entry gating | `profiles.py` + `bin/intent_classifier.py` | ✅ Accurate, and the proposed gate composes cleanly on top |
| No closed feedback loop from retrieval outcome → policy | No outcome-callback surface, no per-strategy `(m, s)`, no SPE update path | ✅ Real gap |
| No retrieval forward model | No pre-retrieval mode/table prediction; intent router does intent classification only, no learned per-cluster pathway-confidence table | ✅ Real gap |
| No TRN-style categorical domain suppression | Candidate assembly does not pre-mask domains; reranker downranks instead | ✅ Real gap |
| No hyperdirect fast veto | No early-abort on strategy-level incompatibility | ✅ Real gap |
| No driver/modulator distinction in writes | Write gate does not branch metadata-only updates from content-bearing inserts as separate gate policies | ✅ Real gap |

### Where the memo under-credits the repo

These belong on the coverage tables but aren't there. The memo's §7 limitation 1 hedges with "internal components not visible to us may partially address identified gaps" — this is the section they were hedging about.

1. **D-MEM RPE routing (PR #54, commit `21b16cc`) — `mcp_tools_dmem.py`.**
   A three-tier write gate (skip / construct / full) that routes incoming writes by reward-prediction-error magnitude. This is the **direct write-side analog of the SPE machinery** the memo proposes for the read side. The memo treats writes as un-RPE'd; the repo already RPE-routes writes. The argument the memo makes for SPE on retrieval applies just as well to the existing D-MEM machinery — and the data structures (per-tier histories) are already half of what an SPE-on-retrieval loop would need.

2. **Three-phase dream cycle (PR #61, commit `8552806`) + `brain.think()` + idle trigger + daemon mode.**
   The memo discusses tonic vs. consolidation modes as a recommendation for future work. The repo already has an explicit consolidation state machine with an idle trigger that flips it on. The memo's §1.4 mode-locking proposal can be implemented as policy on top of the existing dream-cycle state, not as a from-scratch build.

3. **Memory immunity system (PR #48, #51) — `quarantine_list`, `quarantine_review`, `quarantine_purge`.**
   Not the same as the read-gate, but functionally adjacent: it *categorically excludes* a class of memories from retrieval pending review. That is closer to the memo's TRN-style categorical suppression than the memo realizes — TRN suppression on a *trust* axis rather than a *domain* axis, but the mechanism (categorical mask before ranking) is the same.

4. **Allostatic scheduling (PR #53) — `consolidation_forecasts` + 3 tools.**
   The memo's "transition trigger" discussion in Step 1 (statistical test on accumulating ledger) is conceptually close to allostatic-forecast-driven mode-switching that the repo already exposes. Worth surfacing in the gap-analysis discussion.

5. **`free_energy_check` (PR #47) + `memory_calibration` + `attention_snapshot` (#46).**
   Free-energy-style predictive-processing tooling already exists. The memo's forward-model proposal can plug into this rather than be a parallel system.

6. **Schema resonance + compositional replay + cosine-divergence boundary detection (PR #33, #7, #34 → commit `5754211`).**
   The "cerebellum boundary marker" sentinel memory the orient call surfaces (memory 1974) is from this subsystem. Boundary-detection-as-cerebellar-event is already an active idiom in the repo. The memo's cerebellum section could lean on this rather than treat it as absent.

7. **Confidence alpha/beta migration (024, surfaced in 1.5.0 changelog).**
   The DB schema already has the `(α, β)` Beta-distribution columns that would back uncertainty-tracking. The memo proposes `(m, s)` per strategy. The repo's `(α, β)` per memory is a different scale (per-item not per-strategy) but the bookkeeping infrastructure for uncertainty-aware updates is already shipped.

### Where the memo is right that the gap is real

After accounting for the above:

- **No `retrieval_outcome` callback surface.** The observability prerequisite is unsolved. The MCP server returns retrieval results and never hears back. This is the load-bearing missing piece, and the memo is right to put it at Step 1.
- **No retrieval ledger with pathway fingerprints.** `access_log_annotate` exists but doesn't capture mode / table-distribution / RRF-contribution-ratio per retrieval. The memo's "build the ledger first" recommendation is correct and the schema additions are non-trivial.
- **No per-strategy `(m, s)` state.** Strategies (FTS, vector, hybrid-RRF, semantic expansion, episodic, etc.) are not first-class entities with their own utility tracking — they're routing branches inside `_impl.py::cmd_search`. The memo's "strategy identity prerequisite" warning in §2.2 applies: strategies need to become discrete addressable objects before SPE can be hung off them.
- **Forward model is genuinely absent.** Intent router classifies intent; it does not predict mode/table outcomes per query cluster and update predictions from observed retrieval surprise.

### Friction points / things I'd push back on

- **§1.4 "mode-locking at query boundaries"** is sensible, but the memo over-frames the gradual-vs-atomic argument. The dream cycle is already query-atomic in practice. This isn't a design fight, it's a one-line invariant to assert.
- **§2.4 "hyperdirect fast veto" trigger thresholds (0.85 cosine, 1.5× ratio)** are pulled out of the air. The memo says so explicitly but the numbers will read as load-bearing if not flagged when implementing. Treat as placeholders to be calibrated against the actual domain-centroid distribution in this brain.
- **§3.5 "granule cell expansion"** is openly hand-wavy — the memo flags this — and probably shouldn't be on a roadmap. The cerebellar geometry doesn't translate.
- **The "v2.7.0" framing** should be corrected in any follow-up. Pinning to a real version (v1.5.2) and explicitly listing the recent PRs reviewed would tighten the coverage tables and avoid the under-crediting noted above.
- The memo's repeated **"requires observability solution"** is correct as a hard prerequisite but it's a one-week problem dressed up as a multi-quarter problem. A `retrieval_outcome_observe(retrieval_id, outcome)` MCP tool + a `retrieval_ledger` table is a tractable first PR.

---

## Section 3 — Suggested first concrete action

If we want to act on this memo, the minimum-viable first PR is:

1. **`retrieval_ledger` table** with the pathway fingerprint fields the memo specifies (mode, top-K table distribution, RRF contribution ratio, query type signature, intent label, active profile, suppressed-by-domain list, suppressed-by-veto list). Write a row per retrieval inside `cmd_search`.
2. **`retrieval_outcome_observe` MCP tool** that callers (Claude Code plugin, Codex plugin, Hermes, etc.) invoke to report `(retrieval_id, outcome_signal, signal_kind)`. Stub `signal_kind` as `explicit` for now; proxy-signal inference can come later.
3. **No policy changes yet.** Observe first, learn second. The memo is right that this separation is the safer development posture.

Everything in Steps 2–7 of the memo hangs off (1) and (2) being in place. Until then, the SPE math, the forward model, and the TRN domain suppression are unfundable.

---

## Section 4 — Cross-cutting observations

- The memo is the highest-quality external architecture critique brainctl has received. The citation-quality bar (primary-source verification, explicit claim-type notation, removal of unverifiable references) is conspicuously above typical AI-generated architecture documents and matches what you'd expect from peer review.
- It does not address Hermes integration, federation, OpenClaw context profiles, or the multi-agent coordination layer — it's pitched at single-brain retrieval. Multi-agent extensions of the SPE / forward-model machinery are obvious follow-ups but out of scope here.
- The most underdeveloped section is §5 (AI memory systems convergent evidence) — Self-RAG / MemoryBank / HippoRAG are name-checked but not compared against brainctl in mechanism detail. The HippoRAG comparison in particular would be valuable because brainctl already has a hippocampus.py module and the formal analogy is closer than the memo acknowledges.
