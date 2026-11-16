# NOWA Cognitive Architecture: Scientific Description of the Software Complex

Russian version: [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md)

**Date of this account:** 27 September 2026  
**Subject:** the NOWA-Cognitive repository on branch `main`  
**Theoretical paper:** [arxiv_NOWA_ru.md](arxiv_NOWA_ru.md), [arxiv_NOWA_en.md](arxiv_NOWA_en.md)  
**Other language:** [Russian version](SCIENTIFIC_DESCRIPTION.ru.md).

### Abstract

This document is the current scientific description of the NOWA software complex. The architecture implements an autonomous agent in which the recording of episodic experience and the selection of action during waking are separated from the consolidation of slow memory, which is performed in the sleep cycle. Plasticity is regulated by a neuromodulatory field and by a local reward-prediction error; a global loss gradient is not computed. The canonical affective state is an eight-dimensional vector. At the population level, module parameters are encoded by a genome, and a bounded set of consolidated traces may be transmitted by an epigenome.

The complex comprises a cognitive core (`src/`) and four experimental platforms under `Demo/`: an ecological colony, an ethological agent with visualisation, a virtual organisation with a protocol body, and a validation of affective response against lexical norms. Formal derivations, equations, and the relation to the literature are given in the preprint. The present text records the composition of the complex, its invariants, the purpose of each platform, and the order in which the documentation is to be read.

### 1. Status of the documentation

Documents in the repository fall into three classes.

1. **Scientific exposition.** The present text, the preprint, and the scientific accounts of the experimental platforms in `Demo/*/Docs/`. Each language is a separate file. These documents state the subject, the method, and the limits of interpretation.
2. **Normative specifications.** The phase documents `Docs/spec_*.md`, `Docs/Phase_*.md`, `Docs/SPEC_*.md`, and the platform specifications fix module contracts, invariants, and acceptance criteria. Their identifiers (phase numbers, gene names, thresholds) belong to the software contract.
3. **Laboratory journals.** Phase-completion reports, checklists, and intermediate indexes preserve the history of development. They do not replace the scientific exposition and may contain outdated test summaries.

The reading index is [INDEX.en.md](INDEX.en.md).

### 2. Subject and principles of organisation

NOWA (in the preprint: Neural Networks with Reward-Based Learning and Evolutionary Architecture Growth) is a modular cognitive architecture for an agent. Behaviour arises from competition among pressures of memory, affect, habit, and action gating. The architecture contains no single differentiable loss through which all parameters would be updated.

The organisational principles are as follows.

First, waking and consolidation are separated. While awake the agent records episodes, writes a bounded labile layer on Q and Go/NoGo, and selects actions using effective (stable + labile) values. Stable memory and systemic channel-weight updates run in the sleep cycle.

Second, updates are local. The trace bound to a particular context, intention, or action channel is strengthened.

Third, plasticity is scaled by neuromodulators: dopamine, serotonin, norepinephrine, cortisol, and acetylcholine. Dopamine is coupled to the temporal-difference error.

Fourth, inheritable coefficients of the modules are collected in a genome. Consolidated traces transmitted to offspring separately from the genome constitute an epigenome.

Fifth, the cognitive core operates on context tokens, action channels, and affective state. The protocol of an external tool is not imported into the core. A write into an external system passes through the gating loop.

Sixth, autonomy is bounded by physiology: drives, energy, and hard limits on internal simulation.

### 3. Architectural layers

The system is organised in concentric layers. The direction of dependence is as follows: the population sets the parameters of individuals; the autonomous organism sets continuous time and drives; the cognitive core selects an action; the external interaction layer and the platform body embody that action in an environment of the corresponding type. The core does not call protocol tools.

#### 3.1. Cognitive core

The core is implemented in `src/`. Its subsystems are:

| Subsystem | Role |
|---|---|
| Hippocampus | Episodic memory, novelty, fuzzy recall. During waking it records and activates traces. |
| Cortex | Abstract patterns; update is confined to sleep. |
| Intent memory | Mapping from context to a habitual action, and pressure on the selector. |
| Selector | Summation of pressures; proposal of an action without execution. |
| Basal ganglia | Competition of Go and No-Go channels; thalamic stochastic selection. |
| Affective space | Canonical vector \(A(t)\in[-1,1]^8\). |
| Neuromodulators | Field of plasticity and of exploratory regime. |
| Value layer | State evaluation by TD(0), coupled to dopamine. |
| Prediction | Bounded expectation pressures. |
| Conflict arbitration | Control regime; it does not select the action. |
| Decision arbitration and planning | Uncertainty, deliberative mode, hippocampal imagination. |
| Wakefulness and sleep | Process S, circadian Process C, consolidation. |
| Genome, epigenome, agent factory | Inheritable parameters and assembly of an individual. |

The axes of \(A(t)\) are fixed: valence, arousal, dominance, stress, trust, curiosity, stability, attachment. External events change the vector by impulses. Direct assignment of components by a host is excluded by the target contract. The remaining affective modules—persistence, background field, semantic emotions, narratives, expectations, continuous regulation, and stability monitoring—read \(A(t)\) or diagnose it. The operational self-model reports measurable parameters.

The equations for the dynamics of \(A(t)\), the neuromodulatory field, Go/No-Go gating, the temporal-difference error, imagination, and the two-process regulation of sleep are given in the preprint, sections 3.4–3.9.

#### 3.2. Autonomous organism and external interaction layer

The autonomous-organism loop maintains a continuous life cycle in the absence of an external task tick: time, bounded drives, energy, internal simulation on copies of state, and a speech governor. Drives generate impulses into \(A(t)\) and do not replace the canonical vector.

The external interaction layer interprets observations, executes actions of a generic environment, and applies delayed feedback. The selector remains a proposer. Strategy updates are performed in logit space; hypotheses are revised by Bayes' rule. Final gating remains with the basal ganglia.

#### 3.3. Platform body

The platform body is a mode of embodiment orthogonal to the ecological simulation. Tools discovered on an external server become organs: a read is a sensor, a write is a muscle. The tool identifier is a basal-ganglia channel. Call parameters are assembled from the tool schema, the proprioceptive world state, and ranking weights derived from \(A(t)\). The gating loop is the sole point of writing. High-risk writes and irreversible operations require external confirmation and are not bypassed by the agent's decision.

The cognitive step of a protocol tick runs in decision mode: the episode is committed after the outcome is known and contains one action event. The sleep scheduler is invoked separately from selection.

The core implementation of this mode is in `src/mcp_body/`. The experimental harness of the virtual organisation is in `Demo/Virtual company/`.

#### 3.4. Population

The genome is a closed registry of real-valued genes with bounds and a mutation variance. The agent factory is the sole point at which subsystem configuration is assembled. The epigenome carries a limited number of cortical patterns, action traces, and value estimates, and it does not replace learning during sleep. The fitness evaluator computes a multi-criterion vector for offline analysis and does not govern reproduction in real time. The swarm environment synchronises individuals in space, propagates social signals, and applies ecological pressure. A global policy orchestrator is absent.

### 4. Experimental platforms

The platforms share the core and differ in body, observables, and the question a run is designed to answer.

#### 4.1. Colony

Directory: `Demo/Colony chinchillas/`. Scientific account: [COLONY_SPEC.en.md](../Demo/Colony%20chinchillas/Docs/COLONY_SPEC.en.md).

Each individual is a NOWA agent with homeostasis (hunger, thirst, fatigue), social behaviour, an oestrous cycle, pregnancy, and mortality. The environment is a cage with zones and normalised resources. The graphical interface reads state snapshots and takes no part in action selection. The population observer is passive. A death journal is retained for later analysis of causes.

The platform is a testbed for emergent demography: social ties, generational turnover, resource allocation, and extinction risk when reproductive windows narrow. A homeostatic gate may cancel a cognitively chosen action under critical need; the model is an organism, with a body that constrains the mind.

#### 4.2. Ethological agent

Directory: `Demo/Tamagochi Chinchilla/`. Scientific account: [SCIENTIFIC_DESCRIPTION.en.md](../Demo/Tamagochi%20Chinchilla/Docs/SCIENTIFIC_DESCRIPTION.en.md).

The platform studies the expressibility of the architecture in the behaviour of a single individual under continuous visualisation. Cognitive modules are imported from the core. A local layer supplies the ethological repertoire, behavioural chains, realisation of action in animation and sound, and session persistence. Documents of the early phases describe an intermediate preference memory and a need cycle; the current build binds those mechanisms to core modules.

#### 4.3. Virtual organisation

Directory: `Demo/Virtual company/`. Scientific account: [SCIENTIFIC_DESCRIPTION.en.md](../Demo/Virtual%20company/Docs/SCIENTIFIC_DESCRIPTION.en.md).

The platform contains two non-crossing contours. The procurement sandbox is a controlled market in which an agent learns a supply strategy before contact with an external system. The protocol body and the employee host embody the same scheme—organ, decision, gate, sleep—on the tools of an external server. A role is data. An employee is an instance of a mind to which a role has been issued. Monetary and organisational constraints lie in the body, outside the cognitive contour.

#### 4.4. Lexical validation

Directory: `Demo/Warriner Validation/`. Scientific account: [SCIENTIFIC_DESCRIPTION.en.md](../Demo/Warriner%20Validation/Docs/SCIENTIFIC_DESCRIPTION.en.md).

The platform compares the mean valence shift of a colony of sovereign agents with human norms of affective word meaning (Warriner, Kuperman, and Brysbaert, 2013). The measure of association is Spearman's rank correlation; Pearson's coefficient and concordance correlation are computed in addition. The environment delivers the stimulus and reads public state; a shared agent controller is absent.

### 5. Invariants common to the platforms

The following statements hold in every mode of embodiment, unless a platform's normative specification introduces an explicitly bounded extension.

1. Stable parameters consolidate only in sleep; waking writes a bounded labile layer (fast Q and Go/NoGo offsets).
2. The vector \(A(t)\) is the sole canonical affective state. Axes are not extended by an application platform.
3. The basal ganglia gate action. The selector and imagination do not execute action.
4. An episode, once committed, is not rewritten. In protocol mode the path contains one action event.
5. A write into the external world is performed by the gating loop.
6. Observers, graphical panels, and fitness reports do not alter the agent's policy.
7. Individuals in a population do not share memory and do not receive a command from a central dispatcher.

The colony's homeostatic gate and the protocol body's approval loop are constraints of the body. They cancel or delay execution; they do not rewrite a trace by bypassing sleep.

### 6. Reproduction

Regression checks of the core are launched from the repository root:

```bash
python -m pytest -q tests
```

Platform checks are launched from the corresponding `Demo/` directories and are described in the scientific texts of those platforms. Numerical summaries of passing tests recorded in documents of March 2026 are not repeated here: they describe the run of that date, not the current tree.

Core observation interface: `python src/gui.py`.

### 7. Limits of interpretation

The subject of the architecture is a long-lived agent in a changing environment, the stability of traces under selection during sleep, and the observability of behaviour. A language model does not participate in action selection or in the assembly of organ parameters. Quantitative conclusions about a business task of the protocol body, and about the magnitude of correlation with the Warriner norms, are produced by running the corresponding platforms and are not entered in the present text as established constants. Ethical constraints on autonomous systems trained by reward are discussed in the preprint.

### 8. Reading order

1. The present document.
2. The preprint [arxiv_NOWA_en.md](arxiv_NOWA_en.md) — formalisation and the colony analysis. The Russian text is [arxiv_NOWA_ru.md](arxiv_NOWA_ru.md).
3. The scientific account of the platform under study.
4. The normative specification of a module, when the implementation contract is required.
5. [API.md](API.en.md) and [TESTING.en.md](TESTING.en.md) — the programmatic interface and the core verification protocols.
