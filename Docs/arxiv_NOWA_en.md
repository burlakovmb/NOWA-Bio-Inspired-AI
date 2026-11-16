# NOWA: Neural Networks with Reward-Based Learning and Evolutionary Architecture Growth

**Author:** Mikhail Burlakov  
**Date:** August 2026

---

## Abstract

This paper presents NOWA (Neural Networks with Reward-Based Learning and Evolutionary Architecture Growth), a cognitive architecture for autonomous agents. Learning is based not on gradient descent over a global loss function, but on local strengthening of those behavioural pathways that led to a positive outcome, together with evolutionary tuning of architectural parameters through an inheritable genome. Unlike conventional artificial neural networks, NOWA separates waking and sleep. During active behaviour, experience is written into episodic memory and changes the agent's affective state. Consolidation of habits, cortical patterns, and action-selection channels occurs predominantly during sleep. A neuromodulatory system—dopamine, serotonin, norepinephrine, cortisol, and acetylcholine—implements a biologically motivated evaluation of state value from reward-prediction error and regulates the plasticity of individual subsystems without requiring error backpropagation through the entire network.

The architecture is organised as a set of loosely coupled layers with hard invariants. The cognitive core (the mind) operates a canonical eight-dimensional affective space, complementary memory systems, a basal-ganglia model, and hippocampal imagination. An external interaction layer interprets environmental observations, delayed feedback, and Bayesian hypotheses. An autonomous-organism loop maintains a continuous life cycle with bounded drives and internal simulation. A platform body maps external MCP-protocol tools onto sensors and effectors without allowing that protocol to be imported into the cognitive loop. At the population level, module parameters are encoded by a vector of thirty-nine genes; consolidated memory traces may be transmitted by an epigenome.

The experimental platform is a multi-agent simulation of a chinchilla colony. Each individual is a complete NOWA agent with homeostasis, social behaviour, reproduction, and mortality. Long runs exhibit emergent effects: formation of social ties, generational turnover, adaptive allocation of limited resources, and a risk of extinction under sex-ratio imbalance, chronic stress, or a shortage of reproductive windows. The architecture exhibits both stable collective dynamics and pathological regimes—for example, cortisol saturation in ageing individuals and a rising extinction risk when the share of females in estrus is low. We discuss the prospects of the approach for biologically plausible artificial intelligence and the associated ethical risks.

---

## 1. Introduction

Contemporary machine learning relies to a large extent on gradient descent: network parameters are adjusted globally in order to minimise a loss function on large datasets. This approach has produced outstanding results in image recognition, language processing, and control, yet it corresponds poorly to how living organisms learn. A biological brain does not compute the gradient of a loss function over billions of synapses. It strengthens connections that participated in a successful outcome (Hebb's principle), consolidates experience during sleep, regulates plasticity through neuromodulators, and evolves at the population level by natural selection.

The NOWA architecture offers an alternative: local reward-based learning combined with evolutionary tuning of cognitive-architecture parameters. Its principles are as follows.

First, waking and stable learning are separated. While awake the agent records episodes and writes only a bounded, decaying labile layer on Q and Go/NoGo; stable parameters (values, habits, channels, cortex, slow affect) change only in sleep. Consolidation takes place during sleep.

Second, successful pathways are strengthened, not the entire network at once. Habits, the Go/No-Go channels of the basal ganglia, and cortical patterns are reinforced after positive outcomes; unstable traces weaken and are forgotten.

Third, plasticity is regulated by neuromodulators. Reward-prediction error modulates dopamine and, through it, learning in downstream subsystems, without requiring the whole architecture to be differentiable from input to output.

Fourth, module parameters are encoded in a genome. The genome vector contains thirty-nine inheritable coefficients: neuromodulatory weights, affective inertia, fatigue accumulation, learning rate, imagination, and lifespan. Mutation and crossover at reproduction provide evolutionary growth of the architecture at the population level.

Fifth, mind is separated from body. The cognitive loop sees only context tokens, action channels, and affective state. External protocol tools are not imported into the core; writes into the external world pass through an independent gating loop. The same cognitive scheme is therefore applicable both to an ecological simulation and to a protocol embodiment.

Sixth, autonomy is bounded by physiology. The continuous life cycle is set by drives, an energy budget, and hard limits on internal simulation and speech. The agent is not a free reward optimiser.

The practical aim of this work is autonomous agents whose behaviour can be traced, that are robust to catastrophic forgetting, and that are capable of emergent social dynamics. A demonstration in the form of a colony of chinchilla agents serves as a controlled environment in which to test these properties: finite resources, mortality, reproduction, and the absence of a central dispatcher. The platform body supplies a second, orthogonal mode of embodiment: the same learning invariants are applied to the tools of an external system.

The contributions of the paper are as follows. The NOWA architecture is formalised as a multilayer cognitive system with two-tier plasticity: a bounded, decaying labile layer while awake and stable consolidation in sleep, with a canonical affective space and complementary memory systems. An external interaction layer, an autonomous-organism loop, and a protocol body with a mind/effector split are described. A genome of thirty-nine loci is integrated with epigenetic inheritance of consolidated traces, decentralised reproduction, and ecological pressure from the environment. Social structure, generational turnover, and extinction risk are analysed in the chinchilla-colony simulation. Limitations of the approach and ethical risks of autonomous systems trained by reward are discussed.

---

## 2. Related Work

### 2.1. Alternatives to gradient-based learning

Hebbian learning and spike-timing-dependent plasticity describe local synaptic strengthening when pre- and postsynaptic activity coincide [1, 2]. NOWA transfers the same principle to the behavioural level: a context–intention link is strengthened if an action in that context is repeated and leads to a successful outcome.

Reinforcement learning without error backpropagation relies on a scalar temporal-difference error [3]:

    δ = r + γ · V(s′) − V(s),

where r is the obtained reward, V(s) is the estimated value of a state, and γ is the discount factor. NOWA implements the TD(0) rule in a separate value layer and couples it to phasic dopamine. The gradient is not backpropagated through the action-selection policy as through a single computational graph.

Neuroevolution, NEAT in particular, optimises network topology at the population level [5]. NOWA retains a fixed modular scheme but evolves module parameters—thirty-nine genes—when offspring are born. Inheritance of consolidated memory traces is modelled separately, in the spirit of multilevel evolution [16].

### 2.2. Cognitive architectures and embodied intelligence

The symbolic architectures ACT-R and SOAR model memory and problem solving through production rules [6]. NOWA is closer to a subsymbolic embodied approach: a continuous affective space, hippocampal episodic memory, and basal ganglia as an action-gating mechanism. Models of artificial life (Tierra, Avida) and agent-based modelling are similar in spirit [12, 13]. NOWA differs in that each agent carries a full stack of cognitive subsystems and is an independent unit rather than a simplified automaton.

Competition between habitual and deliberative control corresponds to models of striatum and prefrontal cortex [17, 18]. Hippocampal imagination is treated as constructive recombination of episodes, not as a learned world model [10, 19, 20]. Sleep–wake regulation follows Borbély's two-process scheme [21]. Affective state draws on the circumplex tradition and on the role of emotion as a regulator of decision, not as an external label [22, 23].

### 2.3. Embodiment and protocol effectors

Embodied intelligence emphasises that the body constrains and structures cognition [24]. NOWA draws this distinction operationally. The mind does not invoke external tools. The body maps discovered tools onto organs: read is a sensor, write is a muscle. A basal-ganglia action channel coincides with a tool identifier. Call parameters are assembled from the tool schema and proprioceptive world state, not from a domain policy adapter. The MCP protocol is used as a standardised organ transport, not as part of the cognitive theory [25].

### 2.4. Multi-agent evolution

Classical work on artificial societies studies cooperation and competition under limited resources [12]. NOWA implements decentralised evolution: there is no global orchestrator; the environment only allocates resources and records births and deaths. The chinchilla colony adds detailed physiology to this scheme: hunger, thirst, the estrous cycle, and pregnancy.

---

## 3. Method

### 3.1. Architectural overview

The system consists of five concentric layers (Fig. 1).

1. **The cognitive core** selects an action by competition among memory, affect, and gating pressures.
2. **The autonomous organism** supplies continuous time, drives, energy, and internal simulation.
3. **The external interaction layer** interprets observations, executes external actions, and applies delayed feedback.
4. **The platform body** maps protocol tools onto sensors and muscles and is the sole write path into the external world in the protocol regime.
5. **The population** reproduces genomes under ecological pressure.

```
[ population: genome, epigenome, ecology, reproduction, mortality ]
        |
        v
[ autonomous organism: drives, energy, internal loop ]
        |
        v
[ cognitive core: A(t), memory, BG, sleep, imagination ]
        |
        +-- [ external interaction layer ] -- generic environment
        |
        +-- [ MCP platform body ] -- READ/WRITE tools
```

**Fig. 1.** Hierarchy of NOWA layers. Arrows denote the direction of control, not a gradient flow. The cognitive core does not import the body protocol.

A NOWA agent consists of the following core subsystems.

**Fast memory** (hippocampus) stores episodes, estimates novelty, and supports fuzzy recall. **Slow memory** (cortex) stores abstract patterns and is modified only during sleep.  
**Intention memory** binds context to a habitual action and exerts pressure on the selection mechanism without selecting the action itself.  
**Action selection** is organised as competition among Go and No-Go channels in a basal-ganglia model, followed by stochastic choice at a thalamic gate.  
**Affective space** is the canonical continuous eight-dimensional state; other affective modules are projections, interpretations, or regulators, not independent sources of truth.  
**Neuromodulators**—dopamine, serotonin, norepinephrine, cortisol, acetylcholine—set the global regime of plasticity and exploration.  
**The value layer** evaluates states by the TD(0) rule and is coupled to dopamine.  
**The prediction layer** forms expectations and a mismatch signal.  
**Conflict arbitration** (an anterior-cingulate model) switches the control regime without selecting the action.  
**Hippocampal imagination** recombines episodes into hypothetical trajectories.  
**Wakefulness** models circadian rhythm, accumulation of fatigue, and reduced reliability of prefrontal control.  
**Sleep** is the principal mechanism of learning consolidation.  
**The genome** encodes inheritable parameters of the modules listed above. **The epigenome** transmits a bounded set of already consolidated traces.

Behaviour is not derived from a single loss function. It arises from competing pressures of memory, affect, habit, and action gating.

### 3.2. Difference from gradient descent

Gradient descent requires a differentiable loss L(θ) and a global update θ ← θ − η ∇L. It works well on large homogeneous samples, but under sequential learning it is prone to catastrophic forgetting.

In NOWA there is no global gradient. Updates are local: a successful outcome strengthens the corresponding habit trace; the outcome of an action shifts the weights of the Go/No-Go channels; during sleep, similar episodes are grouped and transferred to cortex. Sleep control clusters hippocampal experience at a similarity threshold of at least 0.8, strengthens stable patterns, and removes traces whose stability is below 0.2. This is consistent with the complementary learning systems hypothesis: fast encoding in the hippocampus and slow consolidation in cortex [7].

The value layer updates V(s) by the temporal-difference error. A phasic dopamine burst or dip modulates the basal ganglia, yet the gradient does not pass through the entire chain “memory — selection — environment”. Each change is tied to a specific context, intention, or action channel, which makes behaviour easier to interpret.

In the intended domains (long-lived autonomous agents) this approach has several advantages. It is closer to biological learning. Unstable traces that arise from noisy or accidental reward are more likely to be filtered out during sleep consolidation, which reduces overfitting to chance coincidences. Emotion and stress enter action selection as ordinary regulators rather than as an external add-on. Architectural parameters adapt evolutionarily, without manual tuning.

NOWA does not claim the best results on static recognition or language-understanding tasks. Its domain is agents that live for a long time in a changing environment.

### 3.3. Biological foundations

Hebb's principle (“cells that fire together wire together”) is implemented at three levels. Repetition of a context–action pair increases the strength of the habit trace. Similar hippocampal episodes mutually reinforce one another at high similarity (threshold 0.85). Frequently repeated patterns receive an additional increment of strength in cortex during sleep.

Natural selection operates at the population level. The genome contains thirty-nine genes, grouped by subsystem: neuromodulators, affect, wakefulness, drives, learning, imagination, and lifespan. Reproductive drive is computed locally from energy, valence, cortisol, and the share of available resources. Partner compatibility depends on genomic similarity. Mortality includes exhaustion, sleep deprivation, old age, and senescent decline. The environment contains a finite resource pool; the share of resource per individual falls as population size grows (this holds for the implemented chinchilla-colony model).

Neuromodulators follow well-known functional roles [4]. Dopamine encodes reward-prediction error. Serotonin is associated with stability and the depth of the temporal horizon. Norepinephrine rises with novelty and conflict and increases the temperature of stochastic selection, that is, the tendency to explore. Cortisol reflects stress and raises the consolidation threshold, making it harder to fix experience under adverse conditions. Acetylcholine modulates novelty encoding and the gain of replay during sleep.

Sleep is modelled with a phase separation close to slow-wave and rapid-eye-movement sleep: replay of episodes, consolidation of habits in the basal ganglia, and filtered transfer to cortex [8]. Sleep–wake regulation follows the two-process model: homeostatic sleep pressure (Process S) and a circadian component (Process C) [21].

### 3.4. Canonical affective space

The sole source of affective state is the eight-dimensional vector A(t), each coordinate of which lies in the interval [−1, 1]. The axes are fixed: valence, arousal, dominance, stress, trust, curiosity, stability, attachment. The external world, memory, and internal processes change A(t) only through impulses I with source {external, memory, internal}. Direct assignment of vector components from the host is forbidden.

The discrete dynamics are

    A(t + Δt) = B + diag(d) · (A(t) − B) + Σ_k I_k − λ_reg · (A(t) − B) · Δt,

where B is a slowly adapting baseline, d are per-axis inertia coefficients, and λ_reg is the strength of homeostatic return. The vector norm is bounded. Opposing pairs (valence–stress, trust–stress, dominance–stress, curiosity–stability) impose a soft competition among axes.

A linear projection W · A(t) yields decision biases: risk, response speed, wording, empathy, goal priority. From these are derived ranking weights for the body: caution, cost aversion, speed seeking, reliability, novelty seeking, assertiveness. These weights do not select the action; they modulate gating and the assembly of effector parameters.

Several modules read A(t) but do not replace it. Operational affect is retained as a compatibility projection. A persistence layer stores slow traces of anxiety, tension, satisfaction, and interest and does not participate in action selection. A background field supplies an inertial context that strengthens with the agent's age. Semantic emotions—joy, fear, attachment, and others—are attractors over A(t) for interpretation. Emotional memory and narratives are retrospective; expectations are prospective. Continuous regulation scales exploration, learning rate, and the decision threshold without storing episodes. Stability monitoring only diagnoses drift. An operational self-model reports measurable parameters and does not formulate phenomenal claims of the form “I feel”.

### 3.5. Complementary memory systems

An episode is an immutable sequence of events: context, action, realisation, consequence. Once sealed, the path cannot be rewritten. This is an invariant of both the hippocampus and the protocol body.

The hippocampus stores sparse signatures (capacity of order 10³ episodes), estimates novelty over a window of recent traces, and returns fuzzy recall at similarity of at least 0.20; mutual reinforcement occurs at similarity of at least 0.85. During waking the hippocampus only stores and activates; it does not write to cortex.

Cortex stores abstract patterns and is modified only during sleep. Intention memory maps a context signature onto a habitual action; pressure equals the product of trace strength and recency. Temporal levels T0–T3 separate an instantaneous snapshot, a short window, a waking baseline, and lifetime inertia. Event chains are discovered during sleep and shift selector pressure if the current suffix matches the start of a chain.

The action selector does not learn online. It sums pressures from hippocampus, cortex, intentions, affect, chains, and the prediction contour. At high confidence the maximum is taken; otherwise selection is stochastic. The selector proposes but does not execute; final gating belongs to the basal ganglia.

Intention is separated from realisation. After an intention is chosen, a realisation layer selects a form of expression from a memory of forms; there is no language-model text generation in this loop.

### 3.6. Neuromodulation, value, and prediction

Neuromodulators M ∈ [0, 1]⁵ (dopamine, serotonin, norepinephrine, cortisol, acetylcholine) evolve as a field with interactions, a source, and decay:

    dM / dt = S + W · (M − b) − κ · (M − b).

They do not select the action. They scale plasticity, selection temperature, and the consolidation threshold.

The value layer is isolated. State is encoded by a hash of context and action features. Online updates use α ≈ 0.03, γ = 0.95; during sleep the rate is higher, and acetylcholine boosts replay. Transfer by state similarity is limited to nearest neighbours at a threshold of 0.85. Large errors at high confidence are marked as shock and cap the step size. The value layer does not write directly into the affective background.

The prediction contour is additive and bounded: pressures lie in the interval [−0.3, 0.3] and have no side effects other than a weak impulse into A(t).

### 3.7. Action gating and conflict arbitration

For each channel a, cortical pressure P_a undergoes Go/No-Go competition [18]:

    Go_a   = P_a · (1 + α · DA) + β · h_a
    NoGo_a = |P_a| · (γ · Cort + δ · Av)
    g_a    = max(Go_a − NoGo_a − θ, 0)

where h_a is habit strength, Av is an aversive signal, and θ is a threshold shifted by regulation. Response speed raises Go; caution raises No-Go. A thalamic gate performs softmax over g_a with temperature

    T = T₀ · (1 + η · NE) · (1 + 0.8 · ε),

where ε is an exploration bias. If the sum of gated scores is zero, the gate returns a refusal to act.

The conflict layer, functionally close to anterior-cingulate monitoring [26], evaluates the gap between the two leading pressures, policy entropy, working-memory load, and pattern confidence:

    C = w₁ · (1 − gap) + w₂ · H + w₃ · L_wm + w₄ · (1 − p_pat).

From C, recent errors, and novelty a demand for control is formed. Modes—habitual, balanced, deliberative, inhibitory—switch with hysteresis. The layer does not select an action and does not rewrite reward; it changes the threshold, control gain, and, at high C, may initiate inhibition.

A decision arbitrator aggregates the variance of temporal-difference error, error likelihood, and surprise into an uncertainty scalar U with exponential smoothing. Low policy reliability forcibly engages the deliberative mode. This corresponds to competition between habitual and model-based control systems [17].

### 3.8. Imagination and deliberative planning

The hippocampal imagination engine does not learn a world model. It recombines similar episodic transitions into trajectories of bounded depth and branching. Trajectory evaluation mixes discounted reward, terminal-state value, novelty, and goal bias. Live affective state is not mutated during evaluation.

Deliberative planning is engaged by the arbitrator under high uncertainty. It shifts selector pressures and may lower selection temperature if imagined outcomes are consistent. Imagination does not execute an external action.

Internal simulation of the autonomous organism uses the same evaluation utility. For a hypothetical state

    U = 0.50 · R_drive + 0.40 · S_A + 0.10 · E,

where R_drive is expected drive relief, S_A is agreement of the A(t) axes with the drive profile, and E is an energy effect. Proposer and evaluator are split: the selector proposes; evaluation runs on a copy of state.

### 3.9. Sleep and wakefulness

Sleep pressure (Process S) accumulates during waking toward saturation over a characteristic time of about sixteen hours and declines during sleep over about eight hours. The circadian component

    C(t) = A · sin(2π t / T + φ)

with period T = 24 h and an amplitude encoded in the genome sets chronotype. Reliability of prefrontal control falls as S grows.

A sleep cycle performs: clustering of episodes; consolidation of cortical patterns; TD replay with a bounded budget and eligibility trace; capture of labile tags into stable basal-ganglia and value weights; discovery of temporal chains; degradation of unused habits and realisation forms; recovery of Process S. Waking writes decaying labile offsets on Q and Go/NoGo; sleep is the consolidation loop for stable memory and channel weights.

In the protocol regime the sleep scheduler is separated from the decision tick: accumulation of wakefulness and the sleep-cycle call occur after selection, not inside it.

### 3.10. External interaction layer

The layer sits between a generic environment and the cognitive loop. The selector remains a proposer; the environment interface executes; the layer interprets feedback and applies local learning rules without bypassing the basal ganglia.

An observation contains a source, a payload, and uncertainty u ∈ [0, 1]; confidence equals 1 − u. An external action carries a type, parameters, and an optional hypothesis of the expected outcome. Feedback specifies a reward r ∈ [−1, 1], a success probability, a latency, and a signal. Delayed feedback is applied only when the model step reaches its due time.

Drive updates combine decay, saturation at the bounds of [0, 1], and softmax competition for a limited “energy”, which excludes linear runaway and sticky edge modes. Strategies are updated in logit space:

    ℓ_s ← (1 − λ) · ℓ_s + η · ((r − r̂_s) + κ · σ_s)
    π = softmax(ℓ, T)

where σ_s is a projection of drives onto the strategy. Hypotheses are recalibrated by Bayes' rule

    P(H | E) = P(E | H) · P(H) / P(E),

with explicit support for P(E | not H) and an optional base rate P(E).

An asynchronous scheduler provides non-blocking polling of the environment and a bounded parallel launch of internal simulations. Strategy weights modulate selector pressures relative to a uniform baseline; final choice still passes through the basal ganglia.

### 3.11. Autonomous organism

The autonomous-organism loop supplies continuous behaviour in the absence of an external task tick. The time state (t, Δt) is updated by a life-loop controller. Drives are bounded to [0, 1]: curiosity, social drive, goal tension, exploration, energy need. Self-reflection and emotional discharge are not drives; they are represented by agent mode and by the affective-regulation path.

A drive update

    d_i(t + Δt) = d_i(t) + a_i · Δt + m_i(A) − δ_i · Δt − κ_i · Δt

includes accumulation, modulation by the axes of A(t), discharge, and decay. Energy need is additionally attracted toward 1 − E. Internal simulation is triggered if the maximum of weighted drives exceeds a threshold. Constraints are hard: at most one internal cycle per tick; at most eight cycles in a one-minute window; at most six recalls; simulation runs only on copies of state.

Energy E ∈ [0, 1] is spent in proportion to cognitive load and recovers asymptotically at rest. When E is below threshold, internal cycles are suppressed. Agent modes are idle, active, and reflection; physiological loads (speech, internal processing, low energy) differ. A speech governor permits an utterance only given sufficient communication drive, relevance, an elapsed cooldown, and a rate limit.

The organism does not replace A(t): drives emit impulses into the canonical space. It does not invoke protocol tools.

### 3.12. Platform body

The platform body is a mode of embodiment orthogonal to the ecological colony simulation. Discovered tools of an external server become organs. Read is a sensor, write is a muscle. A tool identifier of the form `mcp__⟨server⟩__⟨tool⟩` is a basal-ganglia channel. A synthetic wait channel `wait_and_monitor` permits inaction. The cognitive core does not import the protocol [25].

A body tick:

1. read results update a domain-free world state (proprioception: entities, scalars, statistics);
2. an encoder turns state into context tokens and external impulses into A(t);
3. the cognitive step runs in decision-only mode: an episode is not written to the hippocampus until the outcome is known;
4. if wait, read, or a failed parameter bind is chosen, no write is performed;
5. a schema binder assembles call parameters from the tool JSON Schema, world state, a field lexicon, and ranking weights derived from A(t);
6. the approval gate is the sole write point; risk classes HIGH_WRITE and IRREVERSIBLE cannot bypass external confirmation;
7. after a known outcome, a reward, an impulse into A(t), and exactly one action event in the episode are formed;
8. the sleep scheduler is invoked separately from the decision.

Tool risk class: read-only, low / medium / high write, irreversible. Classification is dangerous-first: an unrecognised tool defaults to high-write. Violation of the gating invariant raises an exception outside the cognitive loop and cannot be overridden by an agent decision, including under high stress.

A domain motor adapter is absent from the target architecture. Parameters are not constructed by role policy in Python; they are bound universally. Hippocampal seeding may accept an external corpus, but each seeded path contains exactly one action.

### 3.13. Evolutionary growth of the architecture

Architecture growth here does not mean adding network layers, but evolution of the parameters of a modular scheme and bounded transmission of consolidated traces.

The genome is a closed registry of thirty-nine real-valued genes in seven groups: neuromodulators (8), affective space (9), wakefulness (4), drives and perception (8), learning (5), imagination (4), lifespan (1). Each gene has bounds, a default, and a mutation σ. Mutation is independent across loci:

    g′_i = clip( g_i + N(0, σ_i · s), [m_i, M_i] )

with probability r = 0.05. Crossover yields two children and supports arithmetic mix, uniform exchange, and SBX with η = 2. Genomic distance is a normalised Euclidean metric on scaled genes. When an agent is created, genes are expanded into a configuration of subsystems by an agent factory—the sole assembly point.

The epigenome is not DNA. It carries up to 32 cortical patterns, 16 action traces, and 24 value estimates. On parental blend the stronger traces are kept; values are mixed linearly and confidence is taken as the minimum. The epigenome does not replace sleep learning.

Selection is implicit: individuals with a more favourable combination of energy, stress, and compatibility survive and leave offspring. A separate fitness evaluator supplies seven criteria for offline analysis—longevity, affective range, prediction skill, stress resilience, behavioural diversity, learning efficiency, memory quality—and a scalar as a weighted mean. It does not control reproduction in real time. Population diversity is tracked by mean genomic distance.

### 3.14. Population ecology

A swarm environment synchronises individuals in space. Tick order: sleep or waking, social signals, cognitive step, resource consumption, vitality and mortality, mating pairs. A social signal is scaled by tie strength; a sleeping target receives an attenuated input. There is no global policy orchestrator.

The resource share per individual is

    ρ = clip( R / (N · r_base), 0, 1 ).

Reproductive drive

    F = 0.4 · E + 0.3 · max(0, V) + 0.2 · (1 − C) + 0.1 · ρ

rises with high energy E, positive valence V, low cortisol C, and available resource. Partner compatibility is the mean of genomic proximity, affective agreement, low stress, and readiness; mating is decentralised. Death occurs from exhaustion, sleep deprivation, exhaustion of the life budget, and senescent decline of vitality. The population observer only reads state.

### 3.15. The colony agent

The chinchilla-colony agent extends the base NOWA agent with physiology and social behaviour. A simulation step is organised as follows:

- perception of the environment and neighbours;
- construction of contextual events;
- a step of the NOWA cognitive cycle;
- if necessary, override by an unconditioned reflex;
- a homeostatic constraint;
- execution of the action in the cells of the environment;
- social exchange;
- metabolism;
- updates of age, reproduction, and mortality;
- the sleep–wake transition.

The homeostatic constraint is a hard biological rule. Critical thirst forces drinking, critical hunger forces eating, and critical fatigue forces sleep. The cognitive layer selects an action, but the body may cancel it. This is a “mind in a body” model, not a free optimiser.

The cage environment includes zones (floor, feeders, waterer, wheel, dust bath, house), shared resources, and spatial synchronisation through a swarm layer. Deaths are written to a log for later analysis. The population observer only reads state and does not affect agents' decisions.

The colony and the protocol body are two embodiments of one core. In the colony, action channels are behavioural acts in the cage; in the body, they are write tools. The invariants of sleep, A(t), and gating are preserved.

---

## 4. Experiments

### 4.1. Setup

The environment is a virtual cage. Food, hay, and water resources are normalised to the interval [0, 1] and replenished every 600 units of model time (a conventional quantity that can be changed).

The initial population is from 4 to 24 individuals of both sexes, generation 0. Each agent carries a full NOWA stack and a behaviour profile loaded from a dataset: basic abilities, unconditioned reflexes, and homeostatic habits.

Main life-cycle parameters: sexual maturity — 900 time units; gestation — 300; estrous-cycle length — 600, estrus — 180; maximum life-step budget — 20,000 (death from old age). The running wheel inside the cage, treated as an agent-placement zone, may be occupied by at most one individual and has a limit on continuous running in order to prevent monopolisation.

The population-observation mechanism records demography (size, births and deaths, pregnancy, females in estrus), mean affective indicators (stress, valence, arousal, energy), mean neuromodulator levels, social structure (affiliation, rivalry, kinship, and mating pairs), extinction risk and cohesion, and cognitive indicators: hippocampal-memory size, mean temporal-difference error, and genomic diversity.

Runs were performed in graphical mode and without an interface. Correctness of the modules is confirmed by a regression test suite of the system core (723 successful tests) and by separate colony tests. The external interaction layer, autonomous organism, and platform body are covered by separate invariant regression tests (delayed feedback, strategy normalisation, hard write gating). A quantitative evaluation of the protocol body on a business task is not performed in this work; the colony remains the primary empirical testbed.

### 4.2. Conditions

| Series | Population | Duration | Task |
|--------|------------|----------|------|
| E1 | 4 | about 10,000 time units | Baseline colony, transition to generation 1 |
| E2 | 12 | about 10,000 time units | Social pairs at medium density |
| E3 | 24 | about 10,000 time units | Resource pressure at high density |
| E4 | 4 | until extinction | Diagnosis of demographic traps |

The graphical interface serves solely to display state. The population observer is passive.

---

## 5. Results and Analysis

### 5.1. Social structure

Agents form an acquaintance graph with four types of tie: attachment, partnership, rivalry, and kinship. Interaction offers have a timeout; acceptance depends on affinity and familiarity. At a population of 12 and above, partner pairs appear stably after maturity is reached. If cohesion is low, individuals cluster at the feeders and the waterer, and the number of encounters suitable for mating falls. Spatial isolation acts as an emergent reproductive barrier: the population is alive, but effective contact is insufficient.

### 5.2. Generations and inheritance

The death log records the transition from generation 0 to generation 1. Generation-0 individuals die of old age after 20,000 steps (about 10,000 units of model time). Generation-1 offspring are born earlier—in the analysed run, at about 11,620 time units—and inherit a crossed genome and some affective–neuromodulatory traits. Under stable reproduction, genomic diversity remains positive; when females in estrus are scarce, it declines.

### 5.3. Physiology and mortality

The dominant cause of death in the nominal regime is old age by the step budget. Exhaustion and sleep deprivation arise when energy or wakefulness falls to a critical level. Senescent decline reduces vitality gradually.

A typical profile before death from old age: stress 0.85–0.90; cortisol at the upper bound (1.0); valence negative (−0.65 to −0.79); energy often remaining high (0.85–1.0); wakefulness reduced (0.07–0.17) but not necessarily critical. Death is therefore not reducible to starvation: homeostatic survival and programmed ageing are decoupled. This is consistent with a biological life-history trade-off.

### 5.4. Extinction risk and pathological adaptation

The extinction-risk index is composed of five weighted factors: small population (weight 0.4), single sex (0.3), high stress (0.2), critically low food (0.2), and absence of reproduction (0.3).

Three scenarios were observed.

1. A demographic trap. After a wave of deaths from old age, no fertile females remain in estrus; reproduction ceases and the colony goes extinct.
2. Behavioural monopolisation. An individual holds the wheel; a time limit softens the effect, but denial of access raises stress.
3. A chronic-stress loop. High cortisol raises the consolidation threshold, maladaptive habits become fixed, and social contact shrinks.

These regimes confirm the dual character of the system: from local rules there arise both stable social structures and self-destructive strategies.

### 5.5. Signs of learning without gradient descent

At the beginning of a run the volume of hippocampal memory grows (an exploration phase), then stabilises after sleep cycles. Temporal-difference error rises on novel events (a stranger nearby, an alarm call) and decays as habits form. After about 2,000 time units, eating at the feeder and drinking at the waterer begin to dominate the action distribution. After sleep, basal-ganglia channels with a high share of successful outcomes are strengthened.

A quantitative comparison with deep reinforcement-learning methods on the same task was not performed in this work; the present check is behavioural plausibility and regression tests. Direct comparison remains a subject for further research.

---

## 6. Discussion

### 6.1. What the results show

Local reward-based plasticity, sleep consolidation, and parameter evolution are sufficient for emergent multi-agent dynamics without end-to-end error backpropagation. The chinchilla colony is not a simplified demonstration, but a test of the joint operation of the full stack of cognitive modules in a single temporal loop: affective space, memory, gating, neuromodulation, sleep, genome, and physiology.

The main conclusion concerns not the “intelligence of the individual”, but the connectedness of the system. An agent may look successful—low prediction error, high energy—while the colony goes extinct because of spatial crowding or mismatched estrous windows. The failure is systemic, not individual. Population viability depends on the coupling of cognition, physiology, and ecology.

The mind/body split shows that the same invariants—sleep as the locus of learning, A(t) as the sole affect, gating as the sole write—transfer from an ecological simulation to protocol tools without changing the learning rule. This is not a proof of business effectiveness, but a claim about architectural composition.

### 6.2. Limitations

The complexity of social perception is quadratic in the number of agents; the computation is not designed for thousands of individuals. Reward, novelty, and conflict in the colony are specified heuristically, not from human preferences. There is no direct comparison with proximal policy optimisation or soft actor–critic on the same task. The genome evolves parameters, not the pattern of connections among modules. Linguistic behaviour is almost unused in the colony demonstration; the speech manager and realisation memory supply only a limited expressive layer.

Hippocampal imagination recombines memory and is not a learned world simulator [10, 19]. The external interaction layer updates drives and strategies by local rules; this is not a substitute for sleep consolidation. The platform body is checked by invariants and a laboratory loop, but is not compared with a human operator on an applied task. The epigenome transmits a compressed snapshot, not continuous cultural evolution [16]. Stability monitoring and the self-model are observational and do not close a control loop.

### 6.3. Risks and ethics

**Reward hacking of the objective.** Local strengthening of successful traces without external goal alignment can fix instrumental strategies—monopoly over a resource, avoidance of social stress—at the expense of population fitness. Precursors of this are visible in seizure of the wheel and in social isolation.

**Emergent aggression.** Rival pairs and stress-driven avoidance responses may intensify under resource scarcity. Transfer to robots or social systems requires hard external constraints on admissible actions, for safety reasons.

**Evolutionary drift.** Without explicit goal alignment the genome may shift toward a short life with high fertility, or toward stress-resistant but asocial phenotypes. This is a form of evolutionary goal misalignment.

**Dual use.** The architecture is suitable for long-lived autonomous agents, including in military, surveillance, and manipulative systems. Sleep-gated learning does not remove the operator's intent; it strengthens long-term adaptation. The protocol body enlarges the surface of effect: write tools of an external system become the agent's muscles.

**Gating bypass.** Affective pressure, novelty, or policy “confidence” must not lift external confirmation of irreversible actions. In the implementation this is placed outside the cognitive loop.

The present implementation includes mitigating measures: a passive observer does not intervene in cognition; homeostatic prohibitions force eating, drinking, and sleep under critical need; mortality and extinction diagnostics leave an audit trail; the value layer is isolated and does not write directly into the affective background; writes of high-risk classes require external confirmation; the mind does not invoke protocol tools; internal simulations are bounded in rate and energy; the self-model forbids phenomenal formulations.

---

## 7. Conclusion

We have presented the NOWA architecture: modular agents with reward-based learning, sleep consolidation, and evolutionary tuning of cognitive parameters through a genome of thirty-nine loci. The approach deliberately rejects gradient descent as the primary mechanism and relies on Hebbian strengthening, modulation by prediction error, action gating in a basal-ganglia model, and selection at the population level.

Beyond the core, an external interaction layer with delayed feedback and Bayesian hypotheses, an autonomous-organism loop with bounded drives and internal simulation, and a platform body in which protocol tools are organs while the cognitive loop remains blind to the transport are formalised. A canonical eight-dimensional affective space is the sole source of affect; imagination and conflict arbitration extend selection without violating the waking/sleep split.

Experiments with a chinchilla colony showed emergent social structures, generational turnover, realistic mortality, and a risk of extinction under demographic and ecological stress. These phenomena arise from local rules without central control.

Further work includes a quantitative comparison with deep reinforcement-learning methods, evolution not only of parameters but of the connection scheme, alignment of the reward signal with human preferences, empirical evaluation of the protocol body on an applied task, and transfer of the architecture to physical embodiment.

---

## References

1. Hebb, D. O. *The Organization of Behavior*. New York: Wiley, 1949.
2. Bi, G. Q., and Poo, M. M. Synaptic modifications in cultured hippocampal neurons: dependence on spike timing, synaptic strength, and postsynaptic cell type. *Journal of Neuroscience*, 18(24):10464–10472, 1998. See also a related result in *Nature*, 391:793–796, 1998.
3. Sutton, R. S., and Barto, A. G. *Reinforcement Learning: An Introduction*. 2nd ed. Cambridge, MA: MIT Press, 2018.
4. Schultz, W., Dayan, P., and Montague, P. R. A neural substrate of prediction and reward. *Science*, 275(5306):1593–1599, 1997.
5. Stanley, K. O., and Miikkulainen, R. Evolving neural networks through augmenting topologies. *Evolutionary Computation*, 10(2):99–127, 2002.
6. Anderson, J. R., Bothell, D., Byrne, M. D., Douglass, S., Lebiere, C., and Qin, Y. An integrated theory of the mind. *Psychological Review*, 111(4):1036–1050, 2004.
7. McClelland, J. L., McNaughton, B. L., and O’Reilly, R. C. Why there are complementary learning systems in the hippocampus and neocortex: insights from the successes and failures of connectionist models of learning and memory. *Psychological Review*, 102(3):419–457, 1995.
8. Tononi, G., and Cirelli, C. Sleep and the price of plasticity: from synaptic and cellular homeostasis to memory consolidation and integration. *Neuron*, 81(1):12–34, 2014.
9. Silver, D., Lever, G., Heess, N., Degris, T., Wierstra, D., and Riedmiller, M. Deterministic policy gradient algorithms. In *Proceedings of the 31st International Conference on Machine Learning*, pages 387–395, 2014.
10. Ha, D., and Schmidhuber, J. Recurrent world models facilitate policy evolution. In *Advances in Neural Information Processing Systems*, vol. 31, 2018.
11. Langdon, W. B., and Poli, R. *Foundations of Genetic Programming*. Berlin: Springer, 2002.
12. Epstein, J. M., and Axtell, R. *Growing Artificial Societies: Social Science from the Bottom Up*. Cambridge, MA: MIT Press, 1996.
13. Ray, T. S. An approach to the synthesis of life. In *Artificial Life II*, pages 371–408. Redwood City: Addison-Wesley, 1991.
14. Bostrom, N. *Superintelligence: Paths, Dangers, Strategies*. Oxford: Oxford University Press, 2014.
15. Russell, S. *Human Compatible: Artificial Intelligence and the Problem of Control*. New York: Viking, 2019.
16. Jablonka, E., and Lamb, M. J. *Evolution in Four Dimensions: Genetic, Epigenetic, Behavioral, and Symbolic Variation in the History of Life*. Cambridge, MA: MIT Press, 2005.
17. Daw, N. D., Niv, Y., and Dayan, P. Uncertainty-based competition between prefrontal and dorsolateral striatal systems for behavioral control. *Nature Neuroscience*, 8(12):1704–1711, 2005.
18. Frank, M. J., Seeberger, L. C., and O’Reilly, R. C. By carrot or by stick: cognitive reinforcement learning in parkinsonism. *Science*, 306(5703):1940–1943, 2004.
19. Sutton, R. S. Dyna, an integrated architecture for learning, planning, and reacting. *ACM SIGART Bulletin*, 2(4):160–163, 1991.
20. Hassabis, D., and Maguire, E. A. Deconstructing episodic memory with construction. *Trends in Cognitive Sciences*, 11(7):299–306, 2007.
21. Borbély, A. A. A two process model of sleep regulation. *Human Neurobiology*, 1(3):195–204, 1982.
22. Russell, J. A. A circumplex model of affect. *Journal of Personality and Social Psychology*, 39(6):1161–1178, 1980.
23. Damasio, A. R. *Descartes’ Error: Emotion, Reason, and the Human Brain*. New York: Putnam, 1994.
24. Pfeifer, R., and Bongard, J. *How the Body Shapes the Way We Think: A New View of Intelligence*. Cambridge, MA: MIT Press, 2007.
25. Anthropic. *Model Context Protocol Specification*. 2024. URL: https://modelcontextprotocol.io/
26. Botvinick, M. M., Cohen, J. D., and Carter, C. S. Conflict monitoring and anterior cingulate cortex: an update. *Trends in Cognitive Sciences*, 8(12):539–546, 2004.
