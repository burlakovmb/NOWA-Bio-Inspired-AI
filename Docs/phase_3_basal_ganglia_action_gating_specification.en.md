# Phase 3: Basal Ganglia / Action Gating (BG-AG)

Russian version: [phase_3_basal_ganglia_action_gating_specification.ru.md](phase_3_basal_ganglia_action_gating_specification.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.

## Aim of the phase

Create a **biologically plausible mechanism of action selection**, in which:

- decisions are not taken by a single module;
- alternatives compete (Go / NoGo);
- neuromodulators **modulate** the probability of selection and do not dictate it;
- PFC / Prediction Layer remain **advisory**;
- habits can be strengthened and can be suppressed.

Phase 3 introduces the **basal ganglia** as the central *gate* of action taking.

---

## Architectural principles

1. **Decision ≠ Generation**
   The basal ganglia select an *action intention*, not text or a realisation.

2. **Competition, not scoring**
   Actions compete through Go / NoGo channels.

3. **Neuromodulators modulate**
   Dopamine, serotonin, norepinephrine, and cortisol change the *weights of the channels*, but do not select the action.

4. **PFC = advisory**
   Prediction / Plan C / PFC may only:
   - strengthen
   - weaken
   - add noise

5. **Two-tier plasticity**
   Waking outcomes write **labile** Go/NoGo offsets; **stable** channel weights consolidate in sleep.

---

## New components

### 1. ActionChannel

The minimal unit of action selection.

**State:**

```python
ActionChannel:
  action_id: str
  go_weight: float        # [0.0 .. 1.0]
  nogo_weight: float      # [0.0 .. 1.0]
  habit_strength: float   # [0.0 .. 1.0]
```

**Invariants:**

- go_weight and nogo_weight are not required to sum to 1
- a channel does not know about other channels

---

### 2. BasalGangliaGate

The central module of selection.

**Inputs:**

- action candidates (ActionChannels)
- affective pressure
- neuromodulators
- wakefulness
- PFC advisory pressures

**Output:**

- the selected action_id

**Interface:**

```python
class BasalGangliaGate:
    def choose(self,
               channels: List[ActionChannel],
               affect: AffectiveState,
               neuromodulators: NeuromodulatorState,
               wakefulness: WakefulnessState,
               pfc_pressure: Dict[str, float] = None
    ) -> str
```

---

## Mechanics of Go / NoGo

### Basic formulae

For each channel `i`:

```text
Go_i   = go_weight_i   * DA_modifier * affect_modifier
NoGo_i = nogo_weight_i * CORT_modifier

Net_i = Go_i - NoGo_i
```

Where:

- `DA_modifier = f(dopamine)`
- `CORT_modifier = f(cortisol)`
- `affect_modifier` is taken from AffectiveState

### Influence of the neuromodulators

| Modulator | Effect |
|---------|-------|
| Dopamine | strengthens Go, reduces NoGo |
| Serotonin | raises stability, reduces fluctuations |
| Norepinephrine | raises noise and exploration |
| Cortisol | strengthens NoGo, raises the selection threshold |

---

## Integration of PFC / Prediction Layer

PFC **cannot**:

- select an action directly
- cancel the basal ganglia

PFC **can**:

```text
Net_i += pfc_pressure_i * wakefulness_modifier
```

Where:

- `wakefulness_modifier` decreases under fatigue
- high noise makes the pressure less precise

---

## Stochastic selection

After `Net_i` has been computed:

1. Actions below the threshold are cut off:

```text
Net_i < threshold → reject
```

2. From those that remain:

- softmax with a temperature that depends on NE

```text
P(action_i) = softmax(Net_i / temperature)
```

---

## Learning (two-tier: labile wake, stable sleep)

### Sleep BG plasticity

During `SleepManager.deep_sleep()`:

#### Positive outcome:

```text
go_weight += DA * learning_rate
nogo_weight -= DA * learning_rate
```

#### Negative outcome:

```text
go_weight -= CORT * learning_rate
nogo_weight += CORT * learning_rate
```

#### Habit reinforcement:

```text
habit_strength += repetition * serotonin
```

Every update is:

- clamped
- subject to the forgetting_rate from the neuromodulators

---

## Differences from the previous Selector

| Old Selector | Basal ganglia |
|---------------|---------------|
| linear pressure | competition of channels |
| selection of the maximum | stochastic selection |
| habits as a bias | habits as a channel |
| no NoGo | an explicit NoGo |

---

## Antipatterns (critical)

- The basal ganglia take a decision without affect
- PFC overrides the result
- The basal ganglia learn during waking
- A single global scoring
- Absence of noise when NE is high

---

## Test cases

### TC1: Dopamine bias

- DA increases
- expected: Go channels are selected more often

### TC2: Cortisol inhibition

- CORT increases
- expected: NoGo dominates

### TC3: Habit dominance

- habit_strength = 0.9
- expected: a stable choice under neutral conditions

### TC4: PFC advisory ignored under fatigue

- wakefulness > 0.7
- PFC pressure high
- expected: a weak influence of PFC

### TC5: Exploration under NE

- NE increases
- expected: the entropy of selection rises

### TC6: Sleep learning

- a positive outcome is repeated
- sleep
- go_weight increases

---

## Criteria of a successful implementation

- The basal ganglia select actions without the Selector
- PFC has no veto
- Behaviour degrades under fatigue
- Sleep improves stability
- "Errors" are possible, but they are statistically explainable

---

## Status of the phase

Phase 3 is considered complete when:

- ActionSelector becomes a thin wrapper over the basal ganglia
- Behaviour demonstrates the trade-off:
  exploration / exploitation / inhibition

---

## Further steps

- Phase 4: Forward Models / Prediction Error
- Phase 5: Embodiment
- Phase 6: Social & Hierarchical
