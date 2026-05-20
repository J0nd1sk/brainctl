# Thalamus, Basal Ganglia, and Cerebellum: Toward a Biologically Grounded Architecture for brainctl

*Prepared by Claude (Anthropic), in collaboration with Kelly Christiansen (@crystalwizard)*
*For Terrance Schonleber (@omnivaughn)*
*May 17, 2026*

---

## Table of Contents

1. [The Thalamus](#1-the-thalamus)
   - 1.1 Drivers and Modulators
   - 1.2 Two Operational Modes
   - 1.3 Key Nuclei
   - 1.4 Architectural Translation for brainctl
   - 1.5 brainctl Coverage Assessment
2. [The Basal Ganglia](#2-the-basal-ganglia)
   - 2.1 Selection Architecture
   - 2.2 Dopamine and Prediction Error
   - 2.3 Habit Formation
   - 2.4 Architectural Translation for brainctl
   - 2.5 brainctl Coverage Assessment
3. [The Cerebellum](#3-the-cerebellum)
   - 3.1 Architecture
   - 3.2 The Marr-Albus-Ito Learning Rule
   - 3.3 The Forward Model Framework
   - 3.4 The Cognitive Cerebellum
   - 3.5 Architectural Translation for brainctl
   - 3.6 brainctl Coverage Assessment
4. [The Closed Loop: Cross-Structural Synthesis](#4-the-closed-loop-cross-structural-synthesis)
5. [Convergent Evidence from AI Memory Systems](#5-convergent-evidence-from-ai-memory-systems)
6. [Gap Analysis and Development Direction](#6-gap-analysis-and-development-direction)
   - 6.1 What Is Solid in brainctl v2.7.0
   - 6.2 Identified Gaps
   - 6.3 Suggested Development Order
7. [Limitations](#7-limitations)
8. [References](#references)

---

## Abstract

We examine three deep brain structures — the thalamus, basal ganglia, and cerebellum — with the aim of mapping their functional architecture to the brainctl memory system. For each structure we describe the established neuroscience, identify the leading computational interpretation where multiple interpretations are consistent with the data, flag contested or provisional claims explicitly, and derive candidate architectural components. We then assess brainctl v2.7.0 against these components and identify gaps. We close with recent AI memory systems literature that independently converges on several of the same architectural motifs.

Our central assessment, based on the architecture and source available to us, is that brainctl has solid coverage of memory storage across episodic, semantic, and procedural types, and partial coverage of attentional gating and strategy selection, but lacks the feedback mechanisms that make the biological systems self-calibrating: prediction error signals at the strategy level (basal ganglia) and at the pathway level (cerebellum). Without these, brainctl's retrieval policy cannot improve from operational experience. We also identify the observability problem — brainctl as a memory service typically cannot see downstream outcomes — as the prerequisite constraint that must be solved before feedback loops can close. This document provides both a biological reference and a concrete, prioritized set of architectural recommendations for closing the major remaining gaps in brainctl's memory and retrieval systems.

**Claim type notation used throughout:**
- *(Established)* — supported by multiple independent lines of evidence, not significantly contested
- *(Canonical model)* — widely used as an organizing or teaching model; broadly accepted but known to be simplified or incomplete in detail
- *(Leading interpretation)* — leading computational or theoretical interpretation of the biology, well-supported but not uniquely determined by data
- *(Recommendation)* — our architectural suggestions for brainctl; not descriptions of biology or of brainctl's current state

---

## 1. The Thalamus

### 1.1 Drivers and Modulators *(Established)*

Sherman and Guillery established a fundamental distinction between two classes of afferents (input connections from other neurons) to thalamic relay cells [1, 2]: **drivers**, which carry the primary information content, and **modulators**, which adjust gain, threshold, and mode without substantially altering information content.

The critical and counterintuitive finding is about the relationship between numerical abundance and functional role. Thalamocortical driver inputs — the primary information-carrying projections from thalamus to cortex — represent only approximately 5–10% of all synaptic inputs onto cortical layer 4 cells [1], as demonstrated quantitatively in the lateral geniculate nucleus (LGN) and somatosensory relay systems (Ahmed et al. 1994; Latawiec et al. 2000, both cited in [1]). The great majority of cortical synaptic inputs arise from other cortical areas. Conversely, at the thalamic level, the majority of synapses onto relay cells are made by modulators, primarily corticothalamic layer 6 axons.

The Sherman-Guillery framework argues explicitly against treating numerical dominance as the measure of functional importance. The 5–10% of thalamocortical synapses are the functionally critical driver inputs; the numerically dominant corticothalamic inputs modulate relay mode without constituting its primary information content.

**Important refinement from subsequent work:** Bickford [17] demonstrated that the driver/modulator framework, while robust as an organizing principle, requires expansion to accommodate a variety of non-canonical circuit types that fit neither classic category — for example, tectothalamic inputs from the superior colliculus that are structurally intermediate between drivers and modulators. Their terminals are medium-sized, contain round vesicles, and innervate proximal dendrites — morphologically driver-like — but arrive from a source that is neither first-order sensory nor higher-order cortical. Some thalamic nuclei therefore receive combinations of convergent first-order, higher-order, and driver-like subcortical inputs that do not conform to the original binary scheme.

A concrete example is the posterior nucleus (Po), a typical higher-order nucleus in mice. Casas-Torremocha et al. [37] mapped all extrinsic inputs to Po and found a complex mosaic of partly overlapping input domains: Layer 5 cortical afferents from somatosensory and motor cortex converge with excitatory drives from the trigeminal complex, dorsal column nuclei, spinal cord, and superior colliculus, plus spatially segregated inhibitory inputs from zona incerta and the anterior pretectal nucleus — each concentrated in specific Po subregions. The same Po neurons can receive cortical L5 inputs from multiple areas simultaneously, enabling cross-area integration the original first-order/higher-order (FO/HO) framework did not anticipate. Casas-Torremocha et al. [37] conclude that Po neurons perform "input-output computations in a region-specific manner," suggesting the classical first-order/higher-order distinction significantly undersimplifies thalamic organization.

**The transthalamic pathway**: Sherman and Guillery proposed that higher-order thalamic nuclei (pulvinar, mediodorsal, lateral posterior, posterior medial) receive Layer 5 driver inputs from one cortical area and relay them to another cortical area, constituting a parallel corticocortical communication channel distinct from direct white-matter corticocortical connections [1, 2]. Mease and Gonzalez [19] review the functional roles of these corticothalamic Layer 5 pathways, including their involvement in learning, plasticity, and dynamic cortical coupling. Sherman and Usrey [21] argue this transthalamic route is not redundant with direct connections but carries qualitatively distinct information, with the transthalamic pathway providing a parallel route that has unique processing properties not available via direct corticocortical connections. In 2024, Mo et al. [20] provided the first in vivo causal demonstration using optogenetic silencing of a specific transthalamic synapse (primary somatosensory cortex → posterior medial thalamic nucleus (POm) → secondary somatosensory cortex) in awake, task-performing mice: behavioral performance on a texture discrimination task degraded when this specific pathway was silenced while direct corticocortical connections remained intact, establishing that the transthalamic route is functionally necessary for correct perception. *(Both papers [20, 21] verified from primary source.)*

### 1.2 Two Operational Modes *(Established)*

Thalamic relay neurons operate in two distinct states driven by membrane potential:

- **Tonic (relay) mode**: faithful graded transmission of driver input signals. Standard awake, attentive state.
- **Burst mode**: following sustained hyperpolarization, T-type calcium channels (I_T) recover from inactivation. Subsequent depolarization triggers a high-frequency calcium spike burst largely decoupled from the input — an alerting/detection mode with degraded signal fidelity [1]. Associated with drowsiness and slow-wave sleep; participates in large-scale oscillatory dynamics during which consolidation-relevant memory reactivation occurs in hippocampus and cortex (biological replay during sleep — not experience replay in the RL sense). Burst mode is the low-fidelity gate state, not the consolidation mechanism itself.

Mode switching is controlled by modulatory inputs: corticothalamic and brainstem afferents alter membrane potential, and the thalamic reticular nucleus (TRN, described below) can switch relay cells toward burst mode via GABAergic hyperpolarization.

### 1.3 Key Nuclei *(Established)*

*Dorsomedial nucleus (MD)*: Dense projections to prefrontal cortex. Involved in working memory, executive function, and temporal ordering. Damage produces frontal-type deficits — planning failures, impaired working memory, poor temporal ordering.

*Anterior thalamic nuclei (ATN)*: Core component of the Papez circuit — the brain's primary episodic memory loop (mammillary bodies → ATN → cingulate → hippocampus → fornix → mammillary bodies). Critical for episodic memory encoding. Head direction cells are present in ATN; Taube [3] demonstrated this in awake, naturally behaving rats — a necessary condition since head direction cells only update as the animal actually moves and turns — and the ATN is now a confirmed hub in the head direction network. Anterior thalamic — not mediodorsal — pathology is more closely associated with the amnesia of Korsakoff syndrome.

*Pulvinar*: The largest human thalamic nucleus. Dense reciprocal connections with parietal, temporal, and occipital cortex. Modulates spatial attention, salience, and cross-regional coordination across posterior cortex [4, 5].

*Reticular nucleus (TRN)*: A sheet of GABAergic neurons enclosing the thalamus. Projects exclusively to other thalamic nuclei — not to cortex. Receives collateral input from both thalamocortical and corticothalamic axons. Function: competitive lateral inhibition between thalamic relay channels. When one relay is active, TRN neurons suppress competing relays. The TRN executes attentional selections determined by basal ganglia, prefrontal cortex, and brainstem — it does not compute them.

### 1.4 Architectural Translation for brainctl

*(Recommendations throughout)*

**Driver/modulator distinction in writes**: brainctl's write gate currently controls what enters memory without distinguishing between two types of writes: content-bearing writes that update what is stored, and mode-adjusting writes that change how retrieval behaves without altering stored content. In the thalamic framework, these correspond to driver and modulator inputs respectively. A thalamic-analog architecture handles them differently at the gate level.

**TRN competitive domain suppression**: the TRN suppresses entire relay channels categorically — not downranking but excluding entire domains before competition begins. In a memory system: when the current query matches strongly with domain A, domains B and C are excluded from retrieval before any candidates are assembled. This is qualitatively different from reranking across a full candidate set. *Prerequisite: memory domains must be sufficiently separable in brainctl's embedding space to support domain-level suppression masks. This should be assessed before implementation.*

**Read and Write Gates** *(Recommendation)*: the write gate and read gate are different functions, not mirror images, and should not share learned parameters.

The write gate operates at write time. It must answer:

1. Does this incoming content meet the threshold for storage?
2. Is the source reliable enough to trust?
3. Is this a content-bearing write that updates what is stored, or a mode-adjusting write that changes retrieval behavior?
4. Is this content novel enough to store as a new entry? Novelty here means more than just "not an exact duplicate" — it means the content covers territory not already well-represented in memory, comes from a context or time that adds something new, or fills a gap that existing entries don't address.
5. Is this content redundant with what is already stored? If so, the right action may not be to store a new entry but to increase the weighting of what is already there.

Its feedback signal is retrospective: was this content later retrieved, and when it was, did it serve the query?

The read gate operates at retrieval time. It must answer:

1. Of what retrieval returned, what is sufficiently relevant to surface into working context for this query?
2. Does the forward model's prediction support or adjust the relevance threshold for these items?
3. Is this item from an expected cluster (low prediction error) or a surprise (high prediction error)? A surprising item needs a higher relevance score to pass — it must demonstrate genuine relevance, not just unexpectedness.

Its feedback signal is retrospective: did the content surfaced into working context actually serve the query?

Both retrieval decisions — what to retrieve and what to surface — have concrete proposals in this section: retrieval is addressed through strategy selection and domain suppression below; surfacing is addressed through the forward model coupling and item-level threshold below. These are separately learnable functions. Whether they need distinct architectures depends on the empirical distribution of brainctl's relevance scores and domain structure — an engineering question the data should answer, not first principles.

The read gate should operate in two stages:

**Stage 1 — Domain suppression**: Before assembling a candidate set, use the current query context — the query embedding, active session topic, and any explicit domain signals — to identify which memory domains are relevant to this query. Domains that don't match are excluded entirely before item-level comparison begins.

This is categorical exclusion, not downranking. The distinction matters. A ranker assigns scores to all candidates and returns the top results — it can and will return high-scoring items from non-matching domains because semantic similarity in embedding space does not always track domain membership. For example, a query about software architecture might have high cosine similarity to memories about biological neural architecture simply because they share vocabulary. A domain suppression layer catches this before the ranker ever sees those candidates.

Categorical exclusion is also more efficient: the ranker operates on a smaller, pre-filtered candidate pool rather than the full index. For large indexes the efficiency gain is significant.

The mechanism: compute the distance from the query embedding to each domain's centroid or cluster representation. Domains beyond a tunable threshold are excluded. The threshold should start conservative — it is better to let some off-domain candidates through than to risk excluding correct answers.

*Prerequisite: this requires memory domains to be sufficiently distinct in brainctl's embedding space to support reliable identification. If domains are not well-separated, the suppression mask will be unreliable and may exclude correct answers. Assess domain separability empirically before implementing this stage.*

**Stage 2 — Item-level threshold**: Among the items that pass domain suppression, a learned threshold determines which ones get surfaced into working context. This is not a fixed cutoff — it is a function that learns over time, adjusting its slope and midpoint based on how well the items surfaced into working context served the queries they were retrieved for.

The threshold should be smooth rather than hard. A hard cutoff sets a line: items above it pass, items below it don't. This creates two problems. First, noise sensitivity: a relevance score that fluctuates slightly around the cutoff will flip items in and out unpredictably, even though their actual usefulness hasn't changed. Second, non-learnability: a hard cutoff has zero gradient at the boundary, which means gradient-based learning has no signal to adjust it. The threshold can't improve itself from feedback because it doesn't know which way to move.

A smooth function — a sigmoid is the natural choice — assigns high confidence to clearly relevant items, low confidence to clearly irrelevant items, and a gradient in between. Items near the boundary receive partial weight rather than binary in/out decisions. The slope controls how sharp the distinction is, and the midpoint controls where the boundary sits. Both should be learned from the feedback signal described above.

The right slope and midpoint depend on the actual distribution of relevance scores in brainctl. If scores cluster at the extremes — high and low, few in between — the exact shape matters less. If scores are spread more evenly, the slope and midpoint need to be calibrated carefully from operational data. Start with a shallow slope and a conservative midpoint, then tighten as data accumulates.

**Mode-dependent retrieval** *(Recommendation)*: brainctl should operate in two modes: a tonic retrieval mode for normal operation, and a consolidation mode for periods when the index needs reorganization. The distinction matters because retrieval quality degrades when the index is stale and the system needs a way to detect that and respond. The detection mechanism and transition strategy are where the implementation decisions are non-obvious.

Query rate seems like a natural signal for mode detection, with few queries indicating an idle state, and many queries indicating an active state. But query volume is the wrong measure. What matters is whether the index is healthy, not how busy it is. A system under heavy query load may still need consolidation if retrieval confidence is low. A quiet system with a current index does not. A better first signal is retrieval confidence: track a rolling average of recent top-ranked relevance scores. When this degrades, the index is failing to match queries well — that is the signal consolidation is needed. When it recovers, tonic mode can resume.

Mode transition should use mode-locking — holding the current mode fixed for the duration of a query — at query boundaries, not gradual parameter shifting. In practice this means: when a query arrives, record the current mode, execute the full retrieval using that mode's parameters, return the result, then check the mode-detection signal to determine whether a transition is needed before the next query begins.

What changes between modes matters. In tonic mode, the gate thresholds are tuned for retrieval quality — the system is optimized to surface the most relevant items for incoming queries. In consolidation mode, the gate thresholds shift to favor reorganization — the system reduces retrieval throughput and prioritizes index maintenance, decay processing, and reinforcement of high-utility memories over immediate query response.

The alternative — gradual parameter shifting — is tempting because biological systems transition that way. A sleeping brain doesn't snap instantly into full wakefulness; it moves through stages, with gate parameters adjusting progressively as arousal increases. This feels like the right pattern to follow.

But biological systems process a continuous stream of sensory input. brainctl processes discrete, bounded queries. That difference makes gradual shifting the wrong approach. A biological neuron can shift mid-process because its "process" is continuous and self-correcting. A brainctl query has a defined start and end. It is either being processed or it isn't.

The specific failure mode: if the mode-detection signal fires while a query is in flight, the gate operates under two different configurations for the same retrieval. The first half of candidate evaluation runs under tonic parameters — optimized for relevance. The second half runs under consolidation parameters — optimized for reorganization. The final result is assembled from decisions made under incompatible assumptions. The caller receives a response with no indication that this happened. The inconsistency is invisible, which makes it difficult to detect and impossible to reason about.

Mode-locking eliminates this by treating each query as an atomic unit: one mode in, one mode out, transition only at the boundary. A query that begins in tonic mode finishes in tonic mode. A query that begins in consolidation mode finishes in consolidation mode. The result is always coherent.

This requires that the mode-detection logic run only between queries — not continuously during execution. In practice: after a query completes and before the next one begins, evaluate the rolling average of recent relevance scores. If a transition is warranted, update the mode. The next query runs under the new mode from start to finish. During a query, the detection signal is not evaluated at all. This is a deliberate design constraint, not a limitation: by defining exactly when transitions can occur, you make the system's behavior predictable and auditable.

### 1.5 brainctl Coverage Assessment

| Thalamic Function | brainctl Component | Assessment |
|---|---|---|
| Write gating | Write gate (v2.7.0) | Present, partial |
| Driver/modulator distinction in writes | Not identified | Gap |
| Salience amplification | Salience routing | Present, partial |
| Offline consolidation state | Consolidation cycles | Structurally analogous |
| Read gate (retrieval into working context) | Not identified | Gap |
| TRN competitive domain suppression | Not identified | Gap |
| Mode-dependent retrieval behavior | Not identified | Gap |

*All gaps identified above have corresponding recommendations in §1.4.*

---

## 2. The Basal Ganglia

### 2.1 Selection Architecture *(Established)*

The basal ganglia select among competing options and suppress alternatives [34, 35]. While originally characterized in terms of motor program control, the same circuit architecture — organized into functionally distinct parallel loops — is now understood to operate across motor, cognitive, and limbic (emotional and motivational) domains [35, 36].

**Direct pathway** [34, 35] (D1 medium spiny neurons (MSNs) → substantia nigra pars reticulata (SNr)/globus pallidus interna (GPi) → thalamus): direct pathway neurons express D1-family dopamine receptors [35]. D1 MSNs inhibit SNr/GPi — tonically active inhibitory nuclei — releasing the thalamus from suppression. With that suppression removed, the thalamus is free to activate cortex: the "go" signal [35].

**Indirect pathway** [34, 35] (D2 MSNs → globus pallidus externa (GPe) → subthalamic nucleus (STN) → SNr/GPi → thalamus): indirect pathway neurons express D2-family dopamine receptors [35]. D2 MSNs disinhibit STN, which excites SNr/GPi, increasing thalamic suppression — active inhibition of competing options [35].

**Hyperdirect pathway** (cortex → STN directly): cortex projects to STN bypassing striatum, reaching SNr/GPi faster than either direct or indirect pathway. Nambu et al. [6] characterized the anatomy in non-human primates. Aron and Poldrack [7] provided fMRI evidence for right inferior frontal cortex (IFC)-STN activation in human stop-signal inhibition and tentatively proposed the hyperdirect pathway as the mechanism, calling explicitly for future research to confirm the direct IFC-STN anatomical connection.

That confirmation has since arrived. Chen et al. [22] recorded simultaneously from the inferior frontal gyrus and STN in 21 humans with chronically implanted electrodes during a stop-signal task. They demonstrated monosynaptic connectivity via STN stimulation producing cortical evoked potentials with a mean latency of ~2 ms — consistent with monosynaptic transmission. During the task, cortical potentials preceded STN activity by a median lag of ~61–71 ms, and IFG-STN synchronization predicted stopping speed. This provides the first direct human local field potential (LFP) evidence that the inferior frontal gyrus (IFG)-STN pathway mediates motor inhibition. *(Verified from PubMed abstract.)* Causal work in rodents using photodynamic tract elimination confirmed that selective elimination of the motor cortex-to-STN projection produces locomotor hyperactivity, establishing that this pathway tonically suppresses movement [23]. *(Paper [23] verified from primary source.)*

Frank [8] provided the computational framing: the STN implements a "hold your horses" mechanism — rapid broad suppression that pauses commitment to any option while slower deliberative processes complete.

### 2.2 Dopamine and Prediction Error *(Established, with important refinement)*

Schultz, Dayan, and Montague [9] demonstrated that dopaminergic neurons in substantia nigra pars compacta (SNc) and ventral tegmental area (VTA) encode reward prediction error (RPE): firing above baseline for better-than-predicted outcomes, at baseline for predicted outcomes, and suppressed for worse-than-predicted outcomes. This signal modulates corticostriatal synaptic strength, selectively strengthening pathways that led to better-than-expected outcomes.

**On the relationship between dopamine RPE and reinforcement learning:** temporal difference (TD) learning was developed by Sutton and Barto in the 1980s, prior to Schultz's recordings. Schultz et al. 1997 showed that dopamine neuron activity is consistent with TD model predictions — the biology confirmed a pre-existing computational framework. Dayan and Montague, as co-authors, drew this comparison explicitly in the paper. The influence has run in both directions across different timeframes.

**Important refinement — uncertainty-scaled prediction errors:** the basic RPE account treats all prediction errors equally regardless of the variability of the outcome signal. Möller, Manohar, and Bogacz [33] propose a refinement, arguing that the basic RPE account is incomplete under conditions of varying reward uncertainty. They model dopaminergic neurons as broadcasting a prediction error normalized by current reward uncertainty:

δ = (r − m) / s

where r is the observed reward, m is the tracked mean reward, and s is the tracked standard deviation of reward. Both statistics are maintained and updated from each observation. In their model, the biological implementation is distributed across the two striatal pathways: the **difference** between direct (Go, D1) and indirect (NoGo, D2) pathway synaptic connection strengths (biological, not NN weights) encodes reward mean; their **sum** encodes reward uncertainty. Dopamine modulation has asymmetric effects on D1 and D2 receptors — at baseline dopamine levels, D1 receptors are mostly unoccupied (so additional dopamine strongly affects the direct pathway) while D2 receptors are nearly saturated (so additional dopamine has little further effect on the indirect pathway). This asymmetry implements the nonlinear transformation required for uncertainty scaling.

The SPE model explains experimental observations that the standard Rescorla-Wagner/RPE (RW/RPE) model cannot account for. Tobler and Fiorillo found that dopamine responses do not scale linearly with reward magnitude — they are normalized by the uncertainty of the reward distribution [cited in 33]. Rothenhoefer and Hong confirmed that identical deviations from expected value produce stronger dopamine responses when reward variance is smaller [cited in 33]: the signal is scaled by standard deviation, not by range.

This paper is open access and was read directly from primary source. *(Verified from primary source.)*

**Architectural implication** *(Recommendation)*: The SPE model has direct consequences for how brainctl should implement its retrieval strategy feedback loop. The following describes the mechanism, implementation methods, and where it can go wrong.

**Prerequisite — strategy identity**: The SPE mechanism attaches to discrete, identifiable strategies. If brainctl's retrieval strategies are not discrete — if they are continuous parameter mixtures rather than named selectable options — the mechanism has nothing to track m and s against. Strategy identity must be resolved before anything below can be implemented.

**Data structure**: Each retrieval strategy maintains a state object with two values: mean utility (m) and utility standard deviation (s). Initialization of m is a choice with consequences. Starting at 0.5 (neutral, on a 0–1 scale) treats all strategies as equally unknown. Starting low (pessimistic) encourages the system to discover good strategies through use. Starting high (optimistic) encourages early exploration of strategies that haven't yet proven themselves. Choose based on whether you want the system to default to caution or exploration in its early operation. Initialize s to its maximum value regardless — full uncertainty is the correct starting state.

**Update rules**: When an outcome observation arrives:

- e = observed_utility − m  *(raw prediction error, in utility units)*
- δ = e / (s + ε)  *(normalized prediction error, for uncertainty-scaled credit assignment)*
- m ← m + α_m × e  *(update mean from raw error, not normalized error)*
- s ← s + α_s × (δ² − 1)  *(update uncertainty estimate)*
- Enforce s > s_min after every update (floor or clip — see gotchas below)

The distinction between e and δ matters: m is updated from the raw prediction error e (in the same units as utility), not from the dimensionless δ. δ is used for uncertainty-scaled credit assignment to strategy selection weights. Mixing them produces a dimensionally inconsistent update. Utility must be on a consistent normalized scale (0 to 1) for these equations to be coherent; m initialization defaults (0.5 = neutral) assume this normalization.

Use separate learning rates. α_m controls how fast the mean tracks observed utility; if too large, it chases individual noisy observations rather than building a stable estimate. α_s controls how fast uncertainty estimates change; it should generally be smaller than α_m to prevent oscillation. The right ratio also depends on signal noise: in high-noise environments both rates should be small and the ratio matters less; in low-noise environments the ratio matters more. Start conservative on both and adjust from operational data. The value of ε must be set empirically from the actual noise floor of your utility signal — not arbitrarily.

**Utility signal**: Whatever signal you use as observed_utility must be on a consistent scale across all strategies and all time. Note that binary signals (used/not used, mapped to 0 or 1) substantially reduce variance information — s updates will have low resolution and may be unreliable without sufficient observations. If binary is the only signal available, the uncertainty-scaling benefit of the SPE model will be substantially reduced. Graded signals (0.0–1.0 representing quality) are strongly preferred.

**Strategy suppression**: Low-utility strategies should not merely receive low selection probability — they should be actively suppressed below a threshold, analogous to tonic inhibition in the indirect pathway. A reasonable starting threshold: suppress any strategy whose m falls more than one standard deviation below the mean of all active strategy utilities. Review suppressed strategies periodically — if the query distribution shifts, a previously poor strategy may become relevant again. Re-activate suppressed strategies when the overall strategy pool shrinks below a minimum viable count, or when a significant shift in query type is detected.

**Gotchas:**

1. *s near zero*: A well-characterized strategy with low s will have a near-zero denominator in the δ formula. Without ε, a single noisy observation causes a catastrophically large δ. ε is not optional. As a starting point, set ε equal to your minimum expected utility variance across a representative sample of observations, then adjust. Too small gives unstable updates; too large blunts sensitivity to genuine utility differences.

2. *s going negative*: The s update can drive s below zero when δ² < 1 repeatedly — which happens when a strategy performs consistently close to its mean. Enforce a floor: s = max(s, s_min), where s_min is a small positive constant. s < 0 breaks the formula and has no meaningful interpretation.

3. *Early burn-in*: Early observations are under-sampled — the estimates of m and s are statistically unreliable regardless of update magnitude. (High s in the denominator actually reduces update magnitude, not increases it.) Consider holding strategy weights fixed until each strategy has accumulated a minimum number of outcome observations — ten is a reasonable starting point, adjusted based on the stability of early signals. End burn-in per strategy individually, not globally: a frequently-used strategy may exit burn-in quickly while a rarely-used one remains in it longer.

4. *Mixed signal types*: If explicit callbacks and proxy signals are treated identically, you are mixing signals with different reliability levels. Start with proxy signals weighted at 0.3 relative to explicit callbacks (weight 1.0) as a conservative default, and calibrate from data as both signal types accumulate. If only proxy signals are available, track them separately and note that utility estimates are proxy-derived until explicit callbacks become available — do not treat proxy-derived estimates with the same confidence as callback-derived ones.

5. *Utility decay*: Strategy utility estimates should decay toward neutral if a strategy goes unused for an extended period relative to its typical usage frequency. Without decay, stale high-confidence estimates will dominate selection. A simple approach: after any period of non-use equal to twice the strategy's average inter-use interval, begin decaying m toward 0.5 and s toward s_max at a slow rate. This keeps dormant strategies from locking in estimates that may no longer reflect current conditions.

*For the full brainctl implementation context, see 'Uncertainty-scaling of the feedback signal' in §2.4.*

### 2.3 Habit Formation *(Established)*

With overtraining, behavioral control shifts from goal-directed (action-outcome associations, sensitive to outcome devaluation — meaning behavior stops when the reward is made undesirable — prefrontal cortex (PFC)/hippocampus-dependent) to habitual/stimulus-response (insensitive to outcome devaluation, dorsolateral striatum-dependent) [10, 11]. The basal ganglia implement this shift by chunking learned sequences into compressed automatic routines — transferring computational load from deliberate to automatic execution.

**Architectural implication** *(Recommendation)*:

**Prerequisite**: This mechanism depends on the SPE utility tracking from §2.2 being implemented. Habit formation uses the m and s values accumulated through the SPE update rules. If SPE is not in place, the promotion and demotion criteria below have no data to operate on.

**The case for both modes**: Goal-directed retrieval evaluates all options, selects by utility, and updates estimates from outcomes. It is adaptive but computationally expensive on every query. Habitual retrieval executes a known pattern directly, bypassing strategy selection. It is fast but resistant to change. Both should coexist: routine queries with a strong track record execute cheaply through habit; novel queries and edge cases go through full evaluation. The system adapts through the goal-directed path and exploits known-good patterns through the habitual path.

**What a habitual pattern is**: A stored record of three things: a query type signature (the defining characteristics of a class of similar queries), a strategy identity (which retrieval strategy has proven effective for this type), and execution parameters (any configuration specific to this pattern). When an incoming query matches a pattern's signature above the recognition threshold, the stored strategy executes directly without going through selection.

**Pattern recognition**: A query matches a habitual pattern when its embedding similarity to the pattern's defining query cluster exceeds a threshold. Set this threshold conservatively — the cost of executing the wrong habit is higher than the cost of falling back to goal-directed evaluation unnecessarily. The specific threshold value depends on how tightly clustered your query types are in embedding space. Measure your query distribution before setting it.

**Promotion condition**: A pattern becomes a candidate for promotion when it has demonstrated consistently high mean utility and consistently low variance over enough observations to trust both estimates. The specific threshold values for m and s must come from your operational data — they depend on the distribution of utility scores in brainctl and what "high" and "consistent" mean in that context. Do not set them before you have enough data to see that distribution. On instance count: a variance estimate based on fewer than 30 observations is statistically unreliable. Use 30 as a hard floor for the minimum observation count before promotion, regardless of how good the early results look. *(Note: this is distinct from the ten-observation burn-in floor in §2.2. That threshold governs when the mean utility estimate m becomes minimally reliable for selection purposes -- mean estimates stabilize relatively quickly. This threshold governs when the variance estimate s is statistically sound enough to base a promotion decision on. Variance estimates are inherently noisier than mean estimates: a single outlier in a small sample can swing s dramatically, and fewer than 30 observations is not enough to distinguish genuinely consistent performance from a run of similar queries. Different purposes, different statistical requirements.)*

**Promotion and demotion thresholds must be asymmetric.** This is not a calibration question — it is a structural requirement. If the demotion threshold equals the promotion threshold, any pattern performing near the boundary will oscillate between habitual and goal-directed execution as utility fluctuates normally. The gap between promotion and demotion thresholds must be wide enough that normal performance variance does not cause oscillation. How wide depends on the variance of your utility signal; the point is that the gap must exist and must be intentional.

**Execution**: When a query is recognized as matching a habitual pattern, the stored strategy executes directly, bypassing strategy selection.

**The inflexibility risk**: Habitual execution does not feed into the main strategy selection feedback loop because selection was bypassed. If conditions change, the habitual pattern may continue executing without the main feedback loop detecting degradation. This requires a separate monitoring channel.

**Separate monitoring channel**: Track habitual pattern performance independently from the main strategy utility estimates. For each habitual pattern, maintain its own rolling window of recent observed utility values. The window size is a tradeoff: too small and the monitor is sensitive to short-term noise; too large and it responds slowly to genuine degradation. The right size depends on how frequently the pattern executes and how fast conditions in your deployment typically change. Calibrate from operational data.

**Habit breaking**: When the monitoring channel shows the pattern's utility has degraded below the demotion threshold, return it to goal-directed evaluation promptly. Do not continue executing a degrading habit while deliberating — each habitual execution under degraded conditions is a missed opportunity for the feedback loop to update estimates correctly.

**Gotchas:**

1. *Pattern recognition errors*: A misclassified query executes the wrong strategy without evaluation. Log habitual executions that produce unusually poor utility and treat them as potential misclassifications. Audit the pattern signature if this happens repeatedly.

2. *Feedback blind spots*: The main SPE loop does not see habitual executions unless habitual outcomes are explicitly logged back into the utility system. The separate monitoring channel is not optional — if outcomes are not logged back, it is the only mechanism that catches habitual degradation.

3. *Starving the goal-directed path*: If too many patterns are promoted, the goal-directed path receives too little traffic to maintain accurate utility estimates. It is the primary adaptive mechanism. Monitor the ratio of habitual to goal-directed executions and resist over-promotion.

4. *Premature promotion*: A cluster of similar queries in an unusual period can meet the observation count threshold without being representative of normal operation. Promotion based on clustered observations should be treated with additional caution. If your query distribution is normally stable, an unusual cluster is a signal to wait, not to promote.

### 2.4 Architectural Translation for brainctl

*(Recommendations throughout)*

**Strategy selection vs. candidate reranking**: the retrieval executive (PR #96) reranks candidates from a single retrieval pass. The BG-analog selects among retrieval strategies — embedding search, semantic expansion, temporal chain traversal, procedural lookup, episodic association — with active suppression of non-selected strategies and policy learning from outcome. This is a higher-level selection; both levels would operate together.

*Caveat: requires retrieval strategies to be discrete and selectable, not continuous parameter sets.*

**Hyperdirect fast veto**: when query context is clearly in one domain, suppress incompatible strategies before full selection computation completes — a fast, broad early abort.

The veto fires when two conditions are both met: (1) the query embedding has high cosine similarity to one domain centroid (suggested starting threshold: 0.85), and (2) that domain's similarity score is significantly higher than the next-closest domain (suggested starting ratio: 1.5x or greater). The dual condition matters — a query that scores high for one domain but is still meaningfully close to another is ambiguous and should go through full strategy selection. The veto is for unambiguous cases only.

Each domain carries a static list of incompatible strategies — strategies that operate on memory types that domain doesn't use. Example mapping (adjust to match brainctl's actual strategy taxonomy):

- Procedural domain → incompatible: episodic association, temporal chain traversal
- Episodic domain → incompatible: procedural lookup
- Semantic domain → incompatible: episodic association, procedural lookup

General strategies (embedding search, semantic expansion) are compatible with all domains and are never suppressed by the veto.

**Implementation sequence**: at query receipt, compute cosine similarity from query embedding to all domain centroids; check both trigger conditions; if both met, remove incompatible strategies from the candidate pool; pass the reduced pool to SPE selection. The SPE loop runs only on the remaining strategies. The veto does not update utility estimates — it is a filter, not a learning mechanism.

The incompatible-strategy mapping is a static configuration, not a learned parameter. It reflects the logical structure of brainctl's strategy taxonomy — which strategies can retrieve from which memory types. Define it once at deployment and treat it as architectural fact.

**Failure mode**: if the similarity threshold is set too low, the veto fires on ambiguous queries and silently excludes useful strategies. Log every veto event — which domain triggered it, which strategies were excluded — and cross-reference with outcome signals from the ledger to calibrate the thresholds over time.

**Motivational entry gating (NAc-analog)**: categorical exclusion from retrieval competition based on motivational relevance, prior to scalar ranking.

brainctl already has two partial analogs of this mechanism: the intent router (classifies query intent and routes to relevant tables) and the profile system (caller-passed task mode that scopes search to specific categories and tables -- "ops", "research", "writing", "meeting", "networking"). What is proposed here builds directly on that infrastructure rather than replacing it.

**Defining motivational state**: motivational state in brainctl is the active profile -- explicit if the caller passed one, inferred from the intent classifier's result if not. The profile already encodes what the caller cares about: which memory categories, which tables, which entity types. That is the operational definition of what the system is motivated to retrieve for this query.

**The gate**: before strategy selection, each candidate strategy is checked against the active motivational state. Strategies that are incompatible with the current profile or inferred intent are removed from the candidate pool before scoring begins -- not downranked after.

Two general strategies -- embedding search and semantic expansion -- are domain-agnostic and are never excluded by this gate. The three specific strategies are the candidates for exclusion: temporal chain traversal (follows event chains over time), procedural lookup (retrieves how-to content from procedural memory), and episodic association (retrieves personal history and preferences).

**Profile-to-excluded-strategy mapping** (adjust to match brainctl's actual strategy taxonomy):

- writing → exclude: temporal chain traversal, procedural lookup
- meeting → exclude: procedural lookup
- research → exclude: temporal chain traversal, procedural lookup
- ops → exclude: episodic association
- networking → exclude: procedural lookup

Reasoning: writing and research queries are about what is known, not sequences of events -- temporal chain traversal adds noise. Ops is the only profile where procedures are directly relevant (runbooks, deployment); episodic association (personal preferences) has no bearing on operational work. Meeting and networking queries involve relationship and contact history where episodic association is useful and should remain.

**Intent-to-excluded-strategy mapping** (used when no profile is passed):

- entity_lookup → exclude: procedural lookup
- event_lookup → exclude: procedural lookup
- procedural → exclude: episodic association
- decision_lookup → exclude: procedural lookup
- graph_traversal → exclude: procedural lookup
- general → gate does not fire

Reasoning: procedural lookup is specific to how-to content and is irrelevant to almost every other intent type. Episodic association is irrelevant specifically to procedural queries, where personal history and preferences have no bearing on step-by-step instructions. Temporal chain traversal is useful enough across all intents that it is never excluded by the intent gate alone.

**Fallback**: if no profile is passed and intent classification returns "general" (confidence 0.5, the classifier's default when no pattern matched), the gate does not fire and full strategy selection runs. No gating is better than wrong gating.

**The prediction error feedback loop — and the observability problem**: the BG's power comes from the dopamine teaching signal closing a loop from outcome to selection policy. brainctl currently has no equivalent. When retrieval proves useful downstream, that signal should propagate back to increase the utility estimate for the strategy that produced it.

The prerequisite problem: brainctl is a memory service. Downstream agents use retrieved memories and produce results, but brainctl does not automatically observe those results. Closing this loop requires either (a) a callback interface for downstream agents to report retrieval quality, or (b) an internal proxy signal brainctl can measure itself. This must be solved before Gap 1 can be addressed.

**Uncertainty-scaling of the feedback signal** *(Recommendation, informed by [33])*: the feedback signal should not be a raw scalar "good/bad" rating. The SPE model [33] shows that tracking both mean utility and variance — rather than mean alone as in the standard Rescorla-Wagner approach — is both more biologically accurate and more robust under noisy conditions. The architectural consequence: per-strategy state in the BG-analog should encode two values (mean utility m, utility standard deviation s), not one, and scale updates by the current uncertainty estimate. This maps directly to the SPE update rules:

- m ← m + α_m × e (update mean from raw prediction error, where e = observed_utility − m)
- s ← s + α_s × (δ² − 1) (update uncertainty, where δ = e / (s + ε))

*Implementation note: s must be kept positive. Near-zero or negative s causes division instability in the update rule. Use a floor, clip, or log-space parameterization to enforce s > 0.*

This is a concrete and implementable refinement that makes the feedback loop robust to noisy outcome signals — a practical requirement given that retrieval quality signals from downstream agents will vary in reliability, timing, and specificity.

### 2.5 brainctl Coverage Assessment

| Basal Ganglia Function | brainctl Component | Assessment |
|---|---|---|
| Procedural sequence chunking | Procedural memory layer (v2.7.0) | Present — storage level |
| Post-retrieval candidate reranking | Retrieval executive + reranker (PR #96) | Present (draft) |
| Strategy-level selection with active suppression | Not identified | Gap |
| Salience-weighted gating | Salience routing | Present, partial |
| Motivational entry gating | Not identified | Gap |
| Hyperdirect fast veto | Not identified | Gap |
| RPE feedback loop from retrieval outcome | Not identified | Gap — requires observability solution |

*All gaps identified above have corresponding recommendations in §2.4.*

---

## 3. The Cerebellum

### 3.1 Architecture *(Established)*

*Granule cells*: approximately 50–80 billion in humans (70 billion commonly cited), the most numerous neurons in the human brain. Their axons bifurcate into parallel fibers running perpendicular to Purkinje cell dendritic trees.

*Parallel fibers → Purkinje cells*: each Purkinje cell receives input from approximately 100,000–200,000 parallel fiber synapses (range across studies and species). This massive fan-in represents a large high-dimensional sparse expansion of the input.

*Climbing fibers*: one per Purkinje cell in adults. From the inferior olive on the opposite side of the brain (contralateral). Fires at approximately 1 Hz. Signals error: the mismatch between expected and actual outcome.

*Purkinje cells*: tonically active, GABAergic, sole output of cerebellar cortex. Inhibit the deep cerebellar nuclei (DCN). When inhibited, DCN drive output to thalamus and brainstem.

### 3.2 The Marr-Albus-Ito Learning Rule *(Established, with important refinement)*

When a parallel fiber synapse is active simultaneously with climbing fiber firing — the conjunction — that parallel fiber connection undergoes long-term depression (LTD): the synapse is weakened [12, 13, 14]. This is the cerebellar implementation of supervised learning: connections active during error are specifically weakened, identifying and reducing the contribution of pathways responsible for the mistake.

**Important refinement:** Hull and Regehr [25] established in their comprehensive 2022 review that granule cell (GrC)-to-Purkinje cell (PC) LTD is not always required for learning — chronic impairment of GrC-to-PC LTD, or a lack of climbing fiber (CF) activity, does not disrupt some forms of cerebellum-dependent learning. Multiple distributed sites and forms of long-term plasticity have been identified across the cerebellar cortex, including long-term potentiation (LTP) at GrC-to-PC synapses, plasticity at mossy fiber (MF)-granule cell synapses, MF-to-Golgi cell (GoC) and GrC-to-GoC synapses, and output synapses onto cerebellar nuclei neurons. The Marr-Albus-Ito framework captures the core supervised learning logic, but as Hull and Regehr conclude, "these new discoveries require major revisions of cerebellar circuit models." *(Verified from primary source.)*

### 3.3 The Forward Model Framework *(Leading interpretation)*

Wolpert, Miall, and Kawato [15] proposed that the cerebellum learns forward internal models: given a command, predict the sensory consequences before they arrive, enabling anticipatory corrections that bypass sensorimotor feedback delays. This is the leading computational interpretation of cerebellar function, well-supported by motor adaptation paradigms, lesion studies, and computational modeling.

This framework is a computational interpretation — the forward model concept is not a directly observed property of individual cerebellar neurons. It has been substantially extended since 1998 to encompass cognitive sequences. Schmahmann et al. [26] formalized the "dysmetria of thought" hypothesis: the cerebellum applies the same error-based predictive regulation to cognition and affect that it applies to motor control. This is now a well-developed theoretical framework with extensive empirical support.

**Timing** *(Established)*: the cerebellum is a sub-second temporal prediction organ, learning the precise interval between events and generating error signals when expectations are violated.

### 3.4 The Cognitive Cerebellum *(Established)*

Schmahmann and Sherman [16] described the cerebellar cognitive affective syndrome (CCAS): posterior cerebellar lobe lesions (particularly lobules VI–VII) and deep nuclei produce deficits in executive function, spatial cognition, language, and affective regulation. This is now well-established and clinically formalized.

**Functional topography:** Guell et al. [27] mapped the full functional gradient of the human cerebellum using resting-state fMRI on the Human Connectome Project dataset (n=1003). Two principal gradients were found: a primary gradient running from sensorimotor to transmodal (default mode network) processing, and a secondary gradient from task-unfocused to task-focused processing. The posterior cerebellum (Crus I/II, lobule VIIB, lobules IX/X) co-activates with transmodal association cortex networks. This gradient atlas is now a standard reference for lobule-function assignments. *(Verified from primary source.)*

**Clinical formalization:** Argyropoulos et al. [28] — an international task force — provided an up-to-date overview of CCAS, substantiated the concept with evidence from diverse scientific angles, promoted awareness of CCAS as a clinical entity, and identified topics of divergence and outstanding questions for further research. The paper confirms that cognitive and affective deficits from cerebellar damage constitute a reproducible and rigorously characterized clinical syndrome across diverse cerebellar diseases. *(Verified from primary source.)*

### 3.5 Architectural Translation for brainctl

*(Recommendations throughout)*

**Retrieval forward model**: given current query context, predict which memory clusters and pathway types will be most useful — before running full retrieval. Run full retrieval. Compare prediction to result. Update the prediction model specifically at pathway connections active during error (LTD-analog: targeted update of the specific pathway that erred, not a global adjustment).

**What the pathways are**: brainctl's retrieval operates across three modes -- FTS (full-text search, exact and keyword matching), vector/embedding (semantic similarity via cosine distance), and hybrid RRF (reciprocal rank fusion of both). These are the pathways the forward model tracks. The reranker chain (q_value, confidence, trust, salience, temporal weighting) runs after candidate assembly and is a separate signal, not a pathway.

**What the model predicts**: for a given query, the forward model predicts (1) which retrieval mode is most likely to surface useful results -- FTS, vector, or hybrid -- and (2) which memory tables are most likely to contain the answer -- memories, events, decisions, procedures. These two predictions together define the expected retrieval pathway.

**Data structure**: the forward model maintains a lightweight lookup indexed by query type signature -- a small feature vector representing the query's intent label, embedding cluster assignment, and any active profile. Each entry stores the historically most useful retrieval mode and table set for that query type, with an associated confidence score. On first encounter, the entry is initialized with the current intent-based defaults brainctl already uses (the intent router's mode and table selection). The forward model starts as a learned refinement of what the intent router already does, not a replacement.

**Prediction error**: after retrieval completes, compare the predicted pathway to what actually performed well. Retrieval surprise -- how different the actual top results were from the predicted cluster -- is computable immediately inside brainctl from the RRF scores and table distribution of returned candidates. This does not require the downstream observability solution from Step 1; it requires only the retrieval ledger. Task utility (did the retrieved content actually help) requires the downstream signal and feeds the BG feedback loop separately.

**Forward model update**: when prediction error is high for a specific pathway component -- the mode was wrong, or the wrong table dominated -- update the confidence for that component in the query type's entry. Do not adjust entries for other query types. This is the pathway-level specificity: a wrong prediction on a "how to deploy" query updates the procedural query cluster's pathway weights, not the weights for entity lookup queries.

**Cold start**: on first deployment the forward model has no entries. It runs in pass-through mode: predictions default to the intent router's output, prediction error is logged but no updates are made until a minimum number of retrievals per query type cluster have accumulated -- ten is a reasonable floor, matching the SPE burn-in threshold from Step 2.

**Granule cell expansion** *(analogous at computational level, not equivalent in mechanism)*: the massive parallel fiber fan-in represents a high-dimensional sparse expansion enabling detection of subtle combinatorial patterns. In retrieval terms, this is analogous to a learned expansion of query embeddings that creates higher-dimensional features enabling finer discrimination between query types that appear similar in the original embedding space. The biological geometry and temporal coding are not captured by a simple embedding layer.

**Pathway-level vs. strategy-level error**: the BG dopamine signal operates at the strategy level. The cerebellar climbing fiber operates at the pathway level — the specific connection active during error is weakened. A brainctl implementation would track which retrieval sub-pathways were active, then update those specifically. This is more surgically precise than global retrieval quality feedback.

**What a sub-pathway is in brainctl**: a sub-pathway is one identifiable component of a retrieval that contributed candidates to the final result set. brainctl's current retrieval has three: the FTS sub-pathway (BM25 full-text matching via the memories_fts index), the vector sub-pathway (cosine distance search via vec_memories), and the table sub-pathway (which table -- memories, events, decisions, procedures -- the winning candidates came from). In hybrid-RRF mode, both FTS and vector are active simultaneously; in FTS-only mode, only FTS runs. Each retrieval has a record of which sub-pathways were active and what proportion of the top-K results each contributed.

**What to track**: for each retrieval logged to the ledger, record (1) which mode was active -- FTS, vector, or hybrid -- (2) the table distribution of the top-K results, and (3) the RRF contribution ratio when in hybrid mode (what fraction of top results came primarily from FTS vs. vector rank). These three fields constitute the pathway fingerprint for that retrieval.

**Targeted update**: when prediction error is computed for a retrieval -- comparing predicted pathway to actual pathway, or comparing retrieval surprise to task utility once downstream signal arrives -- update the pathway weights only for the query type cluster that generated this retrieval. If a hybrid retrieval's top results came overwhelmingly from the FTS component and the retrieval still had high error, that is evidence the FTS sub-pathway is misfiring for this query type. Reduce confidence in FTS for that cluster. Do not adjust FTS confidence for other query type clusters. The vector sub-pathway confidence for that cluster is unchanged -- it was not the active component.

**Connection to existing infrastructure**: `retrieval_prediction_error` is already a column on the memories table and is already read during retrieval. The forward model populates this value per-memory based on pathway-level error rather than leaving it as a global signal. A memory that was retrieved via the FTS path and turned out to be a false positive gets its `retrieval_prediction_error` updated to reflect that -- which then feeds the `_retrieval_practice_boost` mechanism that already uses it to modulate confidence updates on subsequent recalls.

**Timescale gap (acknowledged assumption)**: the cerebellum's native timing is milliseconds to sub-seconds. We apply the forward model principle at seconds-to-minutes. We treat this as scale-independent but acknowledge it is an assumption, not a derived consequence of the neuroscience.

**Temporal pre-staging** *(depends on Step 4 forward model)*: learned anticipation of future retrieval needs based on task trajectory. Feasibility depends on task trajectories being predictable and on brainctl representing current task state. We include this as a direction, not a concrete proposal.

**Read gate and forward model coupling** *(Recommendation)*: the read gate should receive the forward model's prediction error as one of its inputs, alongside item-level relevance score. The design reasoning is as follows.

When the forward model predicted that a given memory cluster would be relevant and retrieval returned items from that cluster, prediction error is low — the result was expected. The gate should require a lower item-level relevance score to amplify these items, because the forward model's current confidence in the context is high and the retrieved items are consistent with that model.

When the forward model predicted one cluster but retrieval returned items from another — a surprise — prediction error is high. Two outcomes are possible: the surprise is genuine (the forward model was wrong, the retrieved items really are relevant to a novel query) or the surprise is noise (retrieval failed and returned irrelevant items). The gate cannot distinguish these cases by prediction error alone.

The resolution: when prediction error is high, require a higher item-level relevance score to amplify. A surprising item with high item-level relevance passes — it is both unexpected and demonstrably relevant, indicating a genuine surprise. A surprising item with low item-level relevance is suppressed — unexpected and not clearly relevant, indicating noise. Prediction error calibrates the item-level threshold rather than making a binary gate decision.

Critically, the prediction error signal reaches both the gate and the forward model independently. The gate uses it to set the amplification threshold for this retrieval; the forward model uses it to update its predictions for future retrievals. Neither path blocks the other. This means the gate participates in the system's self-calibration without being part of the learning mechanism itself.

**Cold start**: the retrieval forward model requires retrieval history. A warm-start strategy or graceful degradation to reactive retrieval is needed for new deployments.

### 3.6 brainctl Coverage Assessment

| Cerebellar Function | brainctl Component | Assessment |
|---|---|---|
| Chunked sequence storage | Procedural memory layer (v2.7.0) | Storage level; forward model computation is separate |
| Offline consolidation replay | Consolidation cycles | Structurally analogous |
| Temporal context tracking | Temporal context system | Present, partial |
| Retrieval forward model | Not identified | Gap |
| Pathway-level error signal and update | Not identified | Gap |
| Temporal pre-staging | Not identified | Gap (speculative) |

*All gaps identified above have corresponding recommendations in §3.5.*

---

## 4. The Closed Loop: Cross-Structural Synthesis

These three systems form a recurrently connected loop — not a sequential pipeline. The diagram below shows information dependencies; the biological systems run concurrently with continuous mutual modulation. An implementation should be a recurrently connected set of modules.

```
Query context
  → BG-analog: select retrieval strategy
               fast veto on incompatible strategies (hyperdirect-analog)
               motivational entry gating (NAc-analog)
  → Thalamus-analog: gate context amplification
                     suppress competing domains (TRN-analog)
                     distinguish content writes from mode-control writes
  → Cerebellum-analog: run forward model prediction
                       bias retrieval toward predicted clusters
  → Retrieval executes
  → Cerebellum-analog: compare prediction to result
                       update pathway-level prediction (LTD-analog)
                       [immediate signal: retrieval surprise, available now]
  → Result enters working context / downstream caller
  → Downstream outcome observed (callback or proxy signal)
  → BG-analog: update strategy utility estimates (RPE-analog)
               [delayed signal: downstream utility, available after use]
```

**The essential property: the loop is closed.** In the target architecture, every retrieval generates feedback signals — at the strategy level (BG-analog) and the pathway level (cerebellum-analog) — that update future behavior. The system learns from operational feedback rather than offline hand-labeling.

All three biological structures converge on the same two-speed motif: a fast feedforward prediction pathway (hyperdirect, transthalamic driver, cerebellar forward model) that preemptively signals expected outcomes, plus a slower modulatory feedback loop that corrects errors. This architecture recurs across independent evolutionary contexts and at multiple scales — it is likely not accidental.

---

## 5. Convergent Evidence from AI Memory Systems

Recent work on memory-augmented AI systems has independently converged on several of the same motifs, providing existence proofs that biologically-motivated architectural principles can be implemented in production systems.

**Self-RAG** [30] trains a single model to decide on-demand whether to retrieve, and then to evaluate retrieved evidence quality and its own output quality using special reflection tokens — looping back to re-retrieve if generation is unsupported. This is the closest existing AI analog to closed-loop retrieval with outcome feedback: the model uses its own generation quality as an internal calibration signal. The retrieval-quality self-evaluation is a software analog of closed-loop retrieval calibration, though its mechanism differs from the cerebellar forward model: Self-RAG evaluates generation quality after the fact, where the cerebellum predicts before execution and updates at the pathway level.

**MemoryBank** [31] implements long-term episodic memory with Ebbinghaus-inspired forgetting and reinforcement: memories decay over time and are reinforced by retrieval, with salience modulating persistence. Demonstrates that biologically-inspired forgetting and consolidation schedules can be implemented in production AI memory systems.

**HippoRAG** [32] implements retrieval modeled on hippocampal indexing theory: an LLM acts as neocortex encoding semantic content, a knowledge graph acts as hippocampal index, and Personalized PageRank implements pattern-completion retrieval. Outperforms standard RAG on multi-hop QA by up to 20%. The hippocampal indexing model is among the closest formal analogs to complementary learning systems theory — the neuroscientific framework holding that the hippocampus rapidly encodes specific episodes while the neocortex slowly consolidates generalizable knowledge across many experiences.

None of these systems fully implements the closed-loop architecture described in §4, but their existence demonstrates that the individual components — self-calibrating retrieval, biologically-inspired consolidation, neurobiologically-grounded indexing — are implementable and beneficial in current AI systems.

---

## 6. Gap Analysis and Development Direction

### 6.1 What Is Solid in brainctl v2.7.0

- Episodic, semantic, and procedural memory storage
- Write gate — partial thalamic write gating
- Salience routing — partial amplification analog
- Consolidation cycles — offline processing analog
- Temporal context system
- Retrieval executive + listwise reranker (PR #96, draft) — candidate-level selection

### 6.2 Identified Gaps

**Gap 1: No closed feedback loop from retrieval outcome to policy** — *highest architectural impact*
Both BG (RPE) and cerebellum (LTD) generate error signals enabling learning from experience. Without this, brainctl's retrieval policy is permanently static. Per [33], the feedback signal should be uncertainty-scaled: each strategy tracks both mean utility (m) and utility standard deviation (s); the update separates raw prediction error e = (observed − m) from normalized error δ = e / (s + ε); m is updated from e, strategy selection weights from δ, making the loop robust to noisy outcomes.
*Prerequisite*: solve observability — define how brainctl receives outcome signals from downstream callers.
*See §2.2 and §2.4 for the SPE mechanism and data structures; §6.3 Step 2 for the development path.*

**Gap 2: No retrieval forward model**
Reactive retrieval only responds to queries as they arrive — it cannot pre-position useful memories, adjust strategy proactively, or detect when a query falls outside its learned experience. A forward model predicts likely retrieval outcomes before executing retrieval, enabling all three. Building one requires accumulated retrieval history (cold start problem) and the observability solution from Gap 1.
*See §3.5 for the forward model implementation and pathway tracking; §6.3 Step 4 for the development path.*

**Gap 3: No competitive domain suppression (TRN-analog)**
Categorical suppression of entire domains before retrieval competition. Requires domain separability assessment.
*See §1.4 Stage 1 for implementation detail; §6.3 Step 3 for the development path.*

**Gap 4: No strategy-level selection with active suppression**
The retrieval executive operates on candidates; BG-analog behavior operates on strategies.
*See §2.4 for strategy selection recommendations; §6.3 Step 2 for the development path.*

**Gap 5: No driver/modulator distinction in writes**
Content-bearing and mode-adjusting writes are not distinguished at the gate level.
*See §1.4 for the write gate questions and driver/modulator distinction; §6.3 Step 6.*

**Gap 6: No motivational entry gating**
Categorical competition exclusion based on motivational relevance, prior to scalar ranking.
*See §2.4 for the motivational entry gating implementation, including profile and intent mappings.*

**Gap 7: No hyperdirect fast veto**
Early-stage abort when query context is clearly domain-specific, before full strategy computation.
*See §2.4 for the hyperdirect fast veto implementation, including trigger conditions and domain mappings.*

**Gap 8: No temporal pre-staging** *(speculative)*
Anticipatory pre-loading of likely future retrievals based on task trajectory.
*See §3.5 and §6.3 Step 7.*

### 6.3 Suggested Development Order

*Everything in this section is a recommendation, not a prescription. You know brainctl's internals better than we do. Our gap analysis is based on the public architecture and PR history through v2.7.0; there may be components we cannot see that already address some of these. Take what is useful, discard what doesn't fit, and reorder as your judgment dictates.*

---

**Step 1 — Solve observability first.**

Gaps 1 and 2 cannot close without outcome signals. This is the prerequisite for everything that follows.

Two paths are available. Neither is clearly superior; the right choice depends on brainctl's deployment context.

*Option A — Explicit callback interface.* Downstream callers report retrieval outcome back to brainctl after use. This gives a cleaner and more direct signal than a proxy, though caller feedback can still be noisy, delayed, or underspecified. The engineering cost is friction for callers: they must emit the callback, and not all integration patterns will support it. A minimal callback could be as simple as a boolean (was the retrieved material used?) or as rich as a structured outcome object.

*Option B — Internal proxy signal.* brainctl infers outcome from observable query-stream patterns — e.g., whether the caller reformulated immediately after retrieval, whether the session continued productively, whether subsequent queries were topically related. These signals are available without caller cooperation. The tradeoff is ambiguity: the same observable pattern can indicate retrieval success or failure depending on context the proxy cannot see. Any proxy used to drive weight updates should be validated against known-good and known-bad retrievals before being trusted.

*Suggested first step regardless of which option is chosen:* build a retrieval event ledger before building the feedback loop. Record what was queried, which strategy and pathway were used, what was suppressed, what was returned, and what signal — if any — later indicated usefulness. This gives you something to replay, audit, and test against before allowing any signal to alter live retrieval policy. It also separates observation from action, which is a safer development posture. When designing the ledger schema, include pathway fingerprint fields from the start: which retrieval mode ran (FTS, vector, or hybrid-RRF), the table distribution of top-K results, and the RRF contribution ratio in hybrid mode. These fields are required for Step 5 (pathway-level error attribution) and cannot be reconstructed retroactively if omitted.

Cold start note: during early operation before the ledger has accumulated meaningful history, the system should degrade gracefully to reactive retrieval — no forward model, no strategy weighting, standard candidate assembly. Define explicitly what this mode looks like and what triggers the transition to learning mode.

*Success criteria for Step 1:* the observability solution is working when the ledger is capturing outcome signals consistently, those signals are correlated with downstream utility (not random noise), and replay of logged events produces strategy utility estimates that are stable across runs. If outcome signals arrive rarely, are uncorrelated with retrieval quality, or produce wildly different utility estimates on replay, the signal source needs revision before the feedback loop is built on top of it.

*Transition trigger:* the transition from reactive to learning mode is triggered not by a fixed observation count but by a correlation test: run a statistical test periodically against the accumulating ledger to determine whether outcome signals are showing genuine correlation with retrieval quality, or whether the relationship could be explained by chance. When the test achieves statistical significance, enable the feedback loop. The appropriate significance threshold depends on the cost of acting on a false signal in your deployment environment -- a spurious correlation that triggers learning mode could degrade retrieval quality before detection, so be conservative. Run the test on a regular cadence rather than once; a signal that was real can become unreliable as query patterns evolve, and the feedback loop should be paused if the signal degrades.

---

**Step 2 — Close the BG feedback loop.**

Once outcome signals are available, implement the RPE-analog: each retrieval strategy tracks a mean utility estimate (m) and a utility standard deviation (s). When an outcome observation arrives, the update is:

e = observed − m
δ = e / (s + ε)
m ← m + α_m × e
s ← s + α_s × (δ² − 1)

where e is the raw prediction error in utility units, δ is the normalized error used for uncertainty-scaled credit assignment, and ε is a small stability constant (prevent division by near-zero s for well-learned strategies). Update m from the raw error e, not from δ -- see §2.2 for the reasoning. Use separate learning rates: α_m controls how fast the mean tracks observed utility, α_s controls how fast uncertainty estimates change and should generally be smaller than α_m. Both values should be set empirically from your signal's noise characteristics -- see §2.2 for full guidance on learning rate selection, gotchas, and the burn-in period before allowing updates.

This is uncertainty-scaled learning per [33]: strategies with high variance in their outcomes update more cautiously; well-characterized strategies update quickly. The value of ε should be set empirically from the noise floor of your actual utility signal, not arbitrarily — too small provides inadequate stability, too large blunts sensitivity to genuine utility differences.

The direct pathway analog in this framework: strategies with consistently high utility receive increasing selection weight. The indirect pathway analog: strategies with consistently low utility receive active suppression, not just low weight. Active suppression prevents low-utility strategies from consuming computation during candidate assembly.

Note: the BG feedback loop updates strategy selection, not individual candidate quality. This is a distinct level from the retrieval executive and reranker, which operate on candidates after strategy execution. Both levels are useful; they are not redundant.

**Motivational entry gating (implement alongside this step):** once strategy identity is resolved and the selection mechanism is in place, add the motivational gate as a pre-selection filter. The gate runs before SPE scoring and removes strategies that are incompatible with the active profile or inferred intent -- SPE scoring then runs only on the strategies that survive. The gate uses infrastructure already in brainctl (the profile system and intent router) and requires no additional observability solution. See §2.4 for the full implementation, including profile-to-excluded-strategy and intent-to-excluded-strategy mappings.

---

**Step 3 — TRN-analog domain suppression.**

Before implementing this, assess domain separability in brainctl's embedding space. If episodic and semantic memories cluster cleanly in the index, categorical domain suppression can substantially reduce the candidate set before ranking begins. If they do not cluster cleanly, suppression built on poor structure will silently exclude correct answers — the ranker will return its best result from the remaining candidates with no indication that the right answer was blocked.

If separability is confirmed, a possible implementation path: represent the active query context as a vector, compute similarity to domain centroids, and suppress domains whose centroids are sufficiently distant from the query vector before candidate assembly. The suppression threshold should be tunable; a hard cutoff is riskier than a soft exclusion with an exploration lane for edge cases.

If separability is poor, the path forward is probably different indexing structure rather than suppression on the existing index. This is worth knowing before building.

The false-negative risk deserves explicit attention in any implementation: if domain suppression is too aggressive, cross-domain retrievals that would have been relevant are never seen by the ranker. Consider an offline audit mechanism or a low-rate exploration lane that occasionally bypasses suppression and compares results.

---

**Step 4 — Retrieval forward model.**

A lightweight model that predicts, from query context, which retrieval cluster or pathway is most likely to be useful — before executing retrieval. This enables anticipatory behavior: the system can pre-stage likely retrievals, adjust strategy weights proactively rather than reactively, and detect when a query is likely to fall outside its learned distribution.

Implementation note: this model requires retrieval history to train, which is why the ledger in Step 1 comes first. Cold start is the main risk. Warm-starting from a prior distribution over query types is one mitigation; another is operating in reactive mode until sufficient history is available.

Distinguish retrieval surprise (prediction vs. actual result, computable immediately inside brainctl) from task utility (did the retrieved material help, requires downstream signal). The forward model can train on retrieval surprise immediately; task utility training requires the observability solution from Step 1. Both signals are useful and they are not the same thing.

*See §3.5 for the full forward model data structure and pathway tracking mechanism.*

---

**Step 5 — Pathway-level error attribution.**

Once the global feedback loop (Step 2) is working, extend prediction error attribution to the pathway level: track and update not just which strategy was selected but which specific retrieval sub-pathway within that strategy produced useful or useless results. This is the cerebellar specificity analog — credit and error propagate to the precise component that contributed, not just to the strategy as a whole. See §3.5 for the full mechanism, sub-pathway definitions, and targeted update logic.

This step is worth deferring until Steps 1-4 have operational data. Pathway-level attribution requires enough retrieval history to distinguish genuine pathway performance differences from noise. However, the preparation for Step 5 begins in Step 1 — the ledger schema must include pathway fingerprint fields from the start (see Step 1 above).

**What to build when Steps 1-4 are operational:** using the accumulated ledger, build a pathway confidence lookup indexed by query type cluster. For each cluster, maintain separate confidence scores for the FTS sub-pathway, the vector sub-pathway, and each table sub-pathway. When prediction error is high for a retrieval, update the confidence score only for the sub-pathway that dominated that retrieval — do not adjust confidence for sub-pathways that were inactive. The `retrieval_prediction_error` column already exists on the memories table and is already read during retrieval; this step populates it with pathway-specific values rather than a global signal.

**When to start:** when the forward model from Step 4 is producing meaningful predictions and the ledger has enough history per query type cluster to distinguish pathway performance differences from noise. The same ten-observation floor used for SPE burn-in is a reasonable starting threshold.

---

**Step 6 — Driver/modulator distinction in writes.**

Distinguish content-bearing writes (new episodic events, corrected semantic facts, learned procedural steps — analog to thalamic driver inputs) from mode-adjusting writes (salience adjustments, domain confidence updates, decay and reinforcement metadata — analog to thalamic modulator inputs) at the write gate level.

This distinction matters for gate policy: content-bearing writes may warrant different validation, persistence, and indexing behavior than mode-adjusting writes. A salience adjustment that is wrong is recoverable; a content write that is wrong may propagate through retrieval in hard-to-trace ways.

**How to classify a write**: the classification uses two signals together.

First, operation type: UPDATE operations targeting metadata fields (salience, confidence, trust_score, replay_priority, decay flags) are always mode-adjusting. They change how existing memories behave in retrieval, not what is stored.

Second, category for INSERT operations: inserts with category "identity" or "preference" are mode-adjusting even though they add new content -- their purpose is to alter retrieval behavior for a specific agent or user. All other insert categories (project, decision, lesson, environment, convention, integration, user) are content-bearing.

**Gate policy for content-bearing writes**: apply the full worthiness gate -- novelty check, redundancy check, surprise score, source confidence. A content write that fails the worthiness gate is logged as a rejected observation event (this already happens in the current write path).

**Gate policy for mode-adjusting writes**: skip the novelty and redundancy checks -- a salience adjustment doesn't need to be novel. Instead, validate the adjustment itself: is the delta within reasonable bounds, is the source agent trusted enough to make this kind of adjustment, and is the target memory in a state that accepts this type of update. Log every mode-adjusting write with the delta applied and the source agent, so drift can be audited.

Note that a single write can sometimes be both -- a preference insert that is also genuinely novel information about a user. Where the classification is ambiguous, default to content-bearing gate policy. Stricter is safer.

---

**Step 7 — Temporal pre-staging.**

Anticipatory pre-loading of likely future retrievals based on task trajectory. This step depends on the forward model from Step 4 -- without a working predictive model, pre-staging has no basis for what to load. The biological analogy suggests it may be useful; the Step 4 data will tell you whether it is.

**What to instrument during Step 4 to inform this decision**: after each retrieval, the forward model predicts the current query's cluster. Extend that to also predict the next likely query type based on the recent query sequence. Log both the prediction and what actually arrived next. Track the prediction accuracy over time. If the next-query prediction is frequently correct, pre-staging is worth building. If queries are essentially unpredictable from context, skip this step.

**The mechanism if Step 4 data supports it**: after each retrieval completes, use the next-query prediction to pre-fetch the top-K memories for the predicted incoming query type and hold them in a short-lived cache. When the next query arrives, if it matches the prediction, serve from cache or merge cache with fresh retrieval. If it does not match, discard the cache and retrieve normally. Cache TTL should reflect typical query cadence in your deployment -- too long wastes memory on stale pre-fetches, too short provides no benefit.

**What to measure to confirm it is working**: cache hit rate (what fraction of pre-staged fetches are actually used), latency delta (how much faster is a cache-hit retrieval versus fresh retrieval), and quality delta (are pre-staged results as useful as fresh ones). If hit rate is low, the query sequence is not predictable enough. If latency delta is negligible, the benefit does not justify the complexity.

---

## 7. Limitations

1. **Incomplete access to brainctl internals.** Gap analysis is based on our review of the public-facing architecture, source code at v2.7.0, and PR #96. Source files reviewed: `_impl.py` (retrieval pipeline, cmd_search, intent router), `_gates.py` (write gate), `profiles.py` (profile system), `brain.py` (Brain.search). Specific claims about `retrieval_prediction_error`, `_retrieval_practice_boost`, and the profile/intent infrastructure are based on this review. Internal components not visible to us may partially address identified gaps; where we cite brainctl current state, treat it as "based on the architecture available to us" rather than a verified ground truth.

2. **Mappings are analogies, not equivalences.** This paper does not claim that brainctl should replicate thalamus, basal ganglia, or cerebellum literally. The biological systems are used as sources of architectural motifs — gating, active suppression, prediction error, uncertainty tracking, and pathway-specific update. The proposed software mechanisms are analogs, not homologies; the analogy operates at the computational level, not the mechanistic level. Where the paper says "LTD-analog" or "TRN-analog," it means: a software mechanism that serves an analogous computational role, not a mechanism derived from or equivalent to the biological one.

3. **Timescale differences unresolved.** Cerebellar timing is milliseconds to sub-seconds; we apply its principles at seconds to minutes. Treated as scale-independent; acknowledged as an assumption.

4. **Wetware-to-software translation gap.** Biological systems are continuous, massively parallel, and operate under tight energy constraints across timescales from milliseconds to years. brainctl is discrete, sequential, and operates in software. The architectural principles derived here are intended to be scale- and substrate-independent, but that independence is assumed, not demonstrated. Specific mechanisms — learning rates, suppression thresholds, consolidation triggers — will need empirical calibration in the actual deployment environment rather than derivation from biology.

5. **Citation verification.** All citations in this document have been verified from primary sources with the exception of [14] Ito 1989, for which Annual Review access was restricted and the citation was confirmed via secondary sources. [33] Möller et al. 2022 was open access and verified directly. Three papers originally cited — Sherman 2016 (Nature Neuroscience), Hannah & Aron 2021 (Nature Reviews Neuroscience), and Van Overwalle et al. 2024 (Nature Reviews Neuroscience) — were inaccessible and have been removed from the document. Claims they supported have been either replaced with verified alternative citations or removed.

---

## References

[1] Guillery, R.W., and Sherman, S.M. "Thalamic Relay Functions and Their Role in Corticocortical Communication: Generalizations from the Visual System." *Neuron* 33, no. 2 (2002): 163–175. DOI: 10.1016/S0896-6273(01)00582-7
*Verified from primary source. Key claims: driver/modulator distinction; thalamocortical driver inputs = ~5–10% of cortical layer 4 synapses; numerical minority does not imply functional insignificance; the paper argues against using synapse counts as the primary measure.*

[2] Sherman, S.M., and Guillery, R.W. "On the Actions That One Nerve Cell Can Have on Another: Distinguishing 'Drivers' from 'Modulators'." *Proceedings of the National Academy of Sciences USA* 95, no. 12 (1998): 7121–7126. DOI: 10.1073/pnas.95.12.7121

[3] Taube, J.S. "Head Direction Cells Recorded in the Anterior Thalamic Nuclei of Freely Moving Rats." *Journal of Neuroscience* 15, no. 1 (1995): 70–86. DOI: 10.1523/JNEUROSCI.15-01-00070.1995

[4] Shipp, S. "The Functional Logic of Cortico-Pulvinar Connections." *Philosophical Transactions of the Royal Society of London B: Biological Sciences* 358, no. 1438 (2003): 1605–1624. DOI: 10.1098/rstb.2002.1213

[5] Robinson, D.L., and Petersen, S.E. "The Pulvinar and Visual Salience." *Trends in Neurosciences* 15, no. 4 (1992): 127–132. DOI: 10.1016/0166-2236(92)90354-B

[6] Nambu, A., Tokuno, H., and Takada, M. "Functional Significance of the Cortico-Subthalamo-Pallidal 'Hyperdirect' Pathway." *Neuroscience Research* 43, no. 2 (2002): 111–117. DOI: 10.1016/S0168-0102(02)00027-5

[7] Aron, A.R., and Poldrack, R.A. "Cortical and Subcortical Contributions to Stop Signal Response Inhibition: Role of the Subthalamic Nucleus." *Journal of Neuroscience* 26, no. 9 (2006): 2424–2433. DOI: 10.1523/JNEUROSCI.4682-05.2006
*Verified from primary source. Key claims: fMRI evidence for IFC-STN activation during stopping; STN activation correlated with stopping speed; hyperdirect pathway proposed tentatively as mechanism; authors explicitly call for future research to confirm direct IFC-STN anatomical connection.*

[8] Frank, M.J. "Hold Your Horses: A Dynamic Computational Role for the Subthalamic Nucleus in Decision Making." *Neural Networks* 19, no. 8 (2006): 1120–1136. DOI: 10.1016/j.neunet.2006.03.006

[9] Schultz, W., Dayan, P., and Montague, P.R. "A Neural Substrate of Prediction and Reward." *Science* 275, no. 5306 (1997): 1593–1599. DOI: 10.1126/science.275.5306.1593
*Verified from primary source. Key claims: dopamine neurons encode RPE; paper explicitly compares dopamine activity to TD model predictions; TD learning (Sutton & Barto, 1980s) preceded this work; the paper confirmed that biology instantiates a pre-existing computational framework.*

[10] Balleine, B.W., and Dickinson, A. "Goal-Directed Instrumental Action: Contingency and Incentive Learning and Their Cortical Substrates." *Neuropharmacology* 37, no. 4–5 (1998): 407–419. DOI: 10.1016/S0028-3908(98)00033-1

[11] Packard, M.G., and Knowlton, B.J. "Learning and Memory Functions of the Basal Ganglia." *Annual Review of Neuroscience* 25 (2002): 563–593. DOI: 10.1146/annurev.neuro.25.112701.142937

[12] Marr, D. "A Theory of Cerebellar Cortex." *The Journal of Physiology* 202, no. 2 (1969): 437–470. DOI: 10.1113/jphysiol.1969.sp008820

[13] Albus, J.S. "A Theory of Cerebellar Function." *Mathematical Biosciences* 10, no. 1–2 (1971): 25–61. DOI: 10.1016/0025-5564(71)90051-4
*Verified from primary source (physical reprint). DOI not independently confirmed but bibliographic data (journal, volume, year) verified.*

[14] Ito, M. "Long-Term Depression." *Annual Review of Neuroscience* 12 (1989): 85–102. DOI: 10.1146/annurev.ne.12.030189.000505

[15] Wolpert, D.M., Miall, R.C., and Kawato, M. "Internal Models in the Cerebellum." *Trends in Cognitive Sciences* 2, no. 9 (1998): 338–347. DOI: 10.1016/S1364-6613(98)01221-2

[16] Schmahmann, J.D., and Sherman, J.C. "The Cerebellar Cognitive Affective Syndrome." *Brain* 121, no. 4 (1998): 561–579. DOI: 10.1093/brain/121.4.561

[17] Bickford, M.E. "Thalamic Circuit Diversity: Modulation of the Driver/Modulator Framework." *Frontiers in Neural Circuits* 9 (2016): 86. DOI: 10.3389/fncir.2015.00086
*Verified from primary source (open access). Key claims: driver/modulator framework requires expansion to include non-canonical circuit types; some thalamic nuclei receive inputs structurally intermediate between classic drivers and modulators.*

[19] Mease, R.A., and Gonzalez, A.J. "Corticothalamic Pathways From Layer 5: Emerging Roles in Computation and Pathology." *Frontiers in Neural Circuits* 15 (2021): 730211. DOI: 10.3389/fncir.2021.730211
*Verified from primary source (open access). Confirms L5-HO thalamus networks participate in diverse functions including selective thalamic-driven modulation, dynamic cortical coupling, and roles in learning and plasticity.*

[20] Mo, C., McKinnon, C., and Sherman, S.M. "A Transthalamic Pathway Crucial for Perception." *Nature Communications* 15 (2024): 6300. DOI: 10.1038/s41467-024-50163-w
*Verified from primary source. Key claim: optogenetic silencing of the S1-to-POm-to-S2 transthalamic synapse in behaving mice severely impaired texture discrimination despite intact direct corticocortical connections.*

[21] Sherman, S.M., and Usrey, W.M. "Transthalamic Pathways for Cortical Function." *Journal of Neuroscience* 44, no. 35 (2024): e0909242024. DOI: 10.1523/JNEUROSCI.0909-24.2024
*Verified from primary source. Key claim: transthalamic pathways provide a parallel route for corticocortical communication carrying qualitatively distinct information from direct connections.*

[22] Chen, W., de Hemptinne, C., Miller, A.M., Leibbrand, M., Little, S.J., Lim, D.A., Larson, P.S., and Starr, P.A. "Prefrontal-Subthalamic Hyperdirect Pathway Modulates Movement Inhibition in Humans." *Neuron* 106, no. 4 (2020): 579–588.e3. DOI: 10.1016/j.neuron.2020.02.012
*Verified from PubMed abstract. Key claims: STN stimulation produced cortical evoked potentials with mean latency ~2 ms (monosynaptic transmission evidence); during stop-signal task, cortical potentials preceded STN activity by median lag ~61–71 ms; IFG-STN synchronization predicted stopping speed.*

[23] Koketsu, D., Chiken, S., Hisatsune, T., Miyachi, S., and Nambu, A. "Elimination of the Cortico-Subthalamic Hyperdirect Pathway Induces Motor Hyperactivity in Mice." *Journal of Neuroscience* 41, no. 25 (2021): 5502–5510. DOI: 10.1523/JNEUROSCI.1330-20.2021
*Verified from primary source. Key claim: photodynamic elimination of the cortico-STN projection produced locomotor hyperactivity, establishing that this pathway tonically suppresses movement.*

[25] Hull, C., and Regehr, W.G. "The Cerebellar Cortex." *Annual Review of Neuroscience* 45 (2022): 151–175. DOI: 10.1146/annurev-neuro-091421-125115
*Verified from primary source. Key claims: GrC-to-PC LTD is not always required for learning; multiple distributed sites and forms of long-term plasticity exist in cerebellar cortex; "these new discoveries require major revisions of cerebellar circuit models."*

[26] Schmahmann, J.D., Guell, X., Stoodley, C.J., and Halko, M.A. "The Theory and Neuroscience of Cerebellar Cognition." *Annual Review of Neuroscience* 42 (2019): 337–364. DOI: 10.1146/annurev-neuro-070918-050258
*Verified from primary source. Key claims: dysmetria of thought hypothesis; posterior lobe cognitive-emotional representations distinct from anterior sensorimotor; posterior lobe lesions produce cerebellar cognitive affective syndrome.*

[27] Guell, X., Schmahmann, J.D., Gabrieli, J.D.E., and Ghosh, S.S. "Functional Gradients of the Cerebellum." *eLife* 7 (2018): e36652. DOI: 10.7554/eLife.36652
*Verified from primary source (open access). Key claims: two principal functional gradients in human cerebellum (n=1003, Human Connectome Project); primary gradient from sensorimotor to transmodal (default mode network); posterior cerebellum (Crus I/II, VIIB, IX/X) associates with transmodal networks.*

[28] Argyropoulos, G.P.D., et al. "The Cerebellar Cognitive Affective/Schmahmann Syndrome: A Task Force Paper." *The Cerebellum* 19, no. 1 (2020): 102–125. DOI: 10.1007/s12311-019-01068-8
*Verified from primary source. Key claims: international task force overview of cerebellar cognitive affective syndrome; confirms deficits in executive function, visuospatial cognition, emotion-affect, and language across diverse cerebellar diseases.*

[30] Asai, A., Wu, Z., Wang, Y., Sil, A., and Hajishirzi, H. "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection." arXiv:2310.11511 (2023).
*Verified from primary source. Key claims: single LM trained to adaptively retrieve on demand and critique retrieved passages using reflection tokens; outperforms ChatGPT on open-domain QA and fact verification.*

[31] Zhong, W., Guo, L., Gao, Q., Ye, H., and Wang, Y. "MemoryBank: Enhancing Large Language Models with Long-Term Memory." *Proceedings of the AAAI Conference on Artificial Intelligence* 38, no. 17 (2024): 19724–19731. DOI: 10.1609/aaai.v38i17.29946
*Verified from primary source. Key claims: Ebbinghaus Forgetting Curve-inspired memory update mechanism; memories decay and are reinforced based on time elapsed and significance.*

[32] Jiménez Gutiérrez, B., Shu, Y., Gu, Y., Yasunaga, M., and Su, Y. "HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models." *Advances in Neural Information Processing Systems* 37 (NeurIPS 2024). arXiv:2405.14831
*Verified from primary source. Key claims: LLMs, knowledge graphs, and Personalized PageRank mimic neocortex, hippocampal index, and pattern-completion retrieval; outperforms state-of-the-art RAG methods on multi-hop QA by up to 20%.*

[34] Albin, R.L., Young, A.B., and Penney, J.B. "The Functional Anatomy of Basal Ganglia Disorders." *Trends in Neurosciences* 12, no. 10 (1989): 366–375. DOI: 10.1016/0166-2236(89)90074-X
*Verified from primary source. Key claims: original anatomical model distinguishing direct striatal projection to SNr/medial globus pallidus from indirect pathway via lateral globus pallidus and STN; two distinct striatal projection neuron populations with different targets; foundational model subsequently confirmed and refined.*

[35] DeLong, M., and Wichmann, T. "Update on Models of Basal Ganglia Function and Dysfunction." *Parkinsonism & Related Disorders* 15, Supplement 3 (2009): S237–S240. DOI: 10.1016/S1353-8020(09)70822-3
*Verified from primary source (NIH-PA author manuscript). Key claims: direct pathway neurons express D1-family dopamine receptors, indirect pathway neurons express D2-family receptors; direct pathway activation disinhibits thalamocortical projections (go signal), indirect pathway activation increases thalamic inhibition (suppresses competing options); basal ganglia "now viewed as essential for higher level behavioral control, for instance in the regulation of habit learning or action selection."*

[36] Rocha, G.S., Freire, M.A.M., Britto, A.M., Paiva, K.M., Oliveira, R.F., Fonseca, I.A.T., Araújo, D.P., Oliveira, L.C., Guzen, F.P., Morais, P.L.A.G., and Cavalcanti, J.R.L.P. "Basal Ganglia for Beginners: The Basic Concepts You Need to Know and Their Role in Movement Control." *Frontiers in Systems Neuroscience* 17 (2023): 1242929. DOI: 10.3389/fnsys.2023.1242929
*Verified from primary source (open access). Corroborating review confirming basal ganglia involvement in reward, emotional, and motor circuits through shared circuit architecture.*

[33] Möller, M., Manohar, S., and Bogacz, R. "Uncertainty-Guided Learning with Scaled Prediction Errors in the Basal Ganglia." *PLOS Computational Biology* 18, no. 5 (2022): e1009816. DOI: 10.1371/journal.pcbi.1009816
*Verified from primary source (open access). Key claims: dopaminergic prediction errors are uncertainty-scaled (δ = (r − m) / s); D1/D2 pathway weight difference encodes reward mean, their sum encodes reward uncertainty; SPE model outperforms standard Rescorla-Wagner model under noisy conditions; consistent with Tobler-Fiorillo and Rothenhoefer-Hong experimental data.*

[37] Casas-Torremocha, D., Rubio-Teves, M., Hoerder-Suabedissen, A., Hayashi, S., Prensa, L., Molnár, Z., Porrero, C., and Clascá, F. "A Combinatorial Input Landscape in the 'Higher-Order Relay' Posterior Thalamic Nucleus." *Journal of Neuroscience* 42, no. 41 (2022): 7757–7781. DOI: 10.1523/JNEUROSCI.0562-22.2022
*Verified from PMC full text (open access). Key claims: the posterior nucleus (Po) receives convergent L5 cortical inputs from multiple areas simultaneously alongside subcortical excitatory drives (trigeminal, dorsal column, spinal cord, superior colliculus) and spatially segregated inhibitory inputs — a complex mosaic that does not conform to the first-order/higher-order binary. Po neurons perform "input-output computations in a region-specific manner." The classical FO/HO distinction significantly undersimplifies thalamic organization in this nucleus.*
