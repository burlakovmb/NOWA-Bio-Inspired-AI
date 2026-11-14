# AFFECTIVE CORE + PHASE 4

Russian version: [affective_core_phase4_spec.ru.md](affective_core_phase4_spec.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.

## Strict specification
**Version:** 2.0
**Status:** conflict-resolved model

---

## Implementation Alignment (2026-02-19)

This section documents the behavior currently implemented in `src/affective_space.py`
and integration paths in `src/agent.py` / `src/storage.py`.

### 1. Canonical source of truth

- Runtime source of truth: `AffectiveSpace.axes`.
- `affect_state` is a compatibility projection from canonical state.
- Basal ganglia selection consumes canonical `affective_space`.

### 2. Legacy additive dynamics are optional

- Legacy additive term (`compat_delta`) is controlled by `legacy_compat_weight`.
- Default value is `0.0`, so legacy additive dynamics are disabled by default.
- This prevents accidental double contribution of inertia/noise.

### 3. Dynamic norm-cap behavior

- Runtime norm cap is dynamic (`dynamic_norm_cap`) with parameters:
  - `norm_cap_base`
  - `norm_cap_max`
  - `norm_cap_adapt_rate`
  - `norm_cap_release_rate`
  - `norm_cap_global_release_rate`
- Growth slows down near `norm_cap_max` via headroom attenuation.
- Slow global release prevents long-term sticking near cap maximum.

### 4. Dynamic baseline

- Baseline adapts in **simulated seconds** via `baseline_adapt_rate` (default ≈ `1/(6×3600)` per second) toward the lived axis; it relaxes toward fixed `baseline_setpoint` (`b0`) at one quarter of that rate.
- Drift is bounded and clamped per axis.
- Full rules: [specs/issue-54-affect-simulated-time.en.md](specs/issue-54-affect-simulated-time.en.md).

### 5. Save/load coverage

`AffectiveSpace.to_dict()/from_dict()` and `AgentStorage.load_agent(...)` include:

- `baseline_adapt_rate`
- `baseline_setpoint`
- `norm_cap_global_release_rate`
- `legacy_compat_weight`
- `axis_decay` (with alias `affective_decay`)

### 6. Tests that validate these rules

- `tests/test_affective_core_phase4.py`
  - `test_phase4_legacy_compat_delta_disabled_by_default`
  - `test_phase4_legacy_compat_delta_can_be_opted_in`
  - `test_phase4_norm_cap_global_release_prevents_sticky_max`
  - `test_phase4_baseline_is_dynamic_under_sustained_state`
- `tests/test_affective_space.py`
  - `test_affective_space_default_axis_decay_bias`
  - `test_affective_space_affective_decay_alias_with_legacy_keys`
  - `test_affective_space_from_dict_supports_affective_decay_alias`
- `tests/test_affective_space_storage.py` validates persistence for new fields.

### 7. Simulated-second dynamics (2026-11, issue #54 part 1)

- Retention per axis: `clamp(axis_decay − lambda_reg, 0, 0.999) ** time_elapsed`.
- Split API: `apply_impulses` / `time_elapsed=0` (impulses only), `advance(dt)` (time only), combined `step` (time then impulses).
- Sleep: `asleep=True`, `SLEEP_RECOVERY_SCALE=4`, cycle dt from `SleepManager` (`SECONDS_PER_SLEEP_CYCLE=1800` when duration omitted).

---

## 1. Architectural principle

### 1.1 The single source of emotional state

There is only one object of the current emotional state:

```
A(t) ∈ ℝ^N
```

It is:

- continuous
- dynamic
- normalised
- read by the Decision Layer

> No parallel state containers are permitted.

---

## 2. Ontology of emotion

Emotion is defined as a process of three phases:

1. Emergence of an impulse
2. Integration into the state
3. Decay

---

## 3. Data structures

### 3.1 Affective State

```
A(t): float[N]
range per axis: [-1, 1]
```

**Dimensionality N:** 8–16

**Minimal basis:**

| Axis       | Description           |
|------------|-----------------------|
| Valence    | valence               |
| Arousal    | arousal               |
| Dominance  | dominance             |
| Stress     | stress                |
| Trust      | trust                 |
| Curiosity  | curiosity             |
| Stability  | stability             |
| Attachment | attachment            |

### 3.2 Emotional Impulse

A temporary operator of state change.

```
EmotionImpulse {
    vector:    ℝ^N
    intensity: [0, 1]
    source:    { external, memory, internal }
}
```

> The impulse **is not stored** as state.

### 3.3 Emotional Trace (memory)

```
EmotionalTrace {
    snapshot_vector: ℝ^N
    intensity:       [0, 1]
    timestamp
    decay_rate
}
```

> A trace does not participate directly in `A(t)`. It **may generate a new impulse**.

---

## 4. State update

### 4.1 Principal equation

> **Implementation (issue #54):** the live integrator uses per-second retention raised to `time_elapsed`, a moving baseline with `baseline_setpoint`, and impulses at the end of the interval. See [specs/issue-54-affect-simulated-time.en.md](specs/issue-54-affect-simulated-time.en.md). The discrete formula below is the `dt=1` special case of the pre-#54 contract text.

```
A_axis(t+1) = Baseline_axis
            + axis_decay[axis] * (A_axis(t) - Baseline_axis)
            + Σ ExternalImpulses_axis
            + Σ RecallImpulses_axis
            + Σ InternalImpulses_axis
            - λ * (A_axis(t) - Baseline_axis)
```

**Parameters:**

| Parameter | Range         | Role |
|----------|---------------|------|
| `axis_decay[axis]` | [0.0, 0.999] | per-axis inertia |
| `α` (`alpha`) | [0.7, 0.95] | legacy fallback for axes without an explicit `axis_decay` |
| `λ` (`lambda_reg`) | [0.01, 0.1] | return regulator |
| `Baseline` | personality base vector | personality base vector |

Default values of `axis_decay`:

- `valence=0.92`
- `arousal=0.80`
- `dominance=0.97`
- `stress=0.75`
- `curiosity=0.78`
- `trust=0.95`

### 4.2 Constraints

```
||A(t)|| ≤ 1.5
No axis leaves [-1, 1]
RecallImpulse ≤ 0.3 * mean(ExternalImpulse)
ΣRecall ≤ 40% of the total effect
```

---

## 5. Closed loop of influence

### 5.1 Decision Layer

The Decision Layer reads **only** `A(t)` and forms:

```
DecisionBias = W * A(t)
```

**W** is the matrix of the influence of emotions on:

- risk
- response speed
- word choice
- degree of empathy
- priority of goals

### 5.2 Behaviour influences emotion

After an action:

1. an event is created
2. the event generates a new impulse
3. the cycle continues

> The loop is closed.

---

## 6. Memory and reactivation

On recall:

```
Recall(E_i) → generate EmotionalImpulse E'_i
where: E'_i = k * snapshot_vector
     k ∈ [0.1, 0.4]
```

> This is **not an overwrite** of the state, but a **new impulse**.

---

## 7. Stability invariants

- There is no second emotional container
- The Decision Layer does not read impulses
- Impulses are not saved as state
- Memory does not modify `A(t)` directly
- In the absence of stimuli, `A(t) → Baseline`

---

## 8. Test cases

### Test 1 — Neutral environment
**Condition:** no impulses
**Expected:** `A(t)` converges exponentially to `Baseline`

### Test 2 — Strong positive stimulus
**Condition:** one `ExternalImpulse` of high intensity
**Expected:**
- Valence rises
- Arousal rises
- Gradual decay

### Test 3 — Recall of traumatic memory
**Condition:** a `RecallImpulse` is created
**Expected:**
- A shift of `A(t)`
- It does not exceed 30% of the mean external impulse
- There is no runaway growth

### Test 4 — Conflict of past and present
**Condition:** a positive stimulus plus a negative recall
**Expected:**
- The resulting state is a vector sum
- The present dominates

### Test 5 — Prolonged pressure
**Condition:** many small `stress` impulses
**Expected:**
- A slow drift of the `Stress` axis
- After the pressure ceases, a return to `Baseline`

---

## 9. Absence of conflict with Phase 4

**Phase 4** is redefined as:

- a generator of `EmotionalImpulses`
- a generator of `EmotionalTraces`

**Affective Core:**

- integrator
- regulator
- the source of state for decisions

> There is no duplication. There are not two states. There are not two sources of truth.

---

## 10. Behavioural consequence

Emotions now:

- influence decision making
- influence response style
- influence strategy
- may be strengthened through repetition
- may decay
- may create inertia

**And the principal point:**

> The agent exists between events.

---

## 11. Architectural result

What was obtained:

| Property                                 | Status |
|------------------------------------------|--------|
| Continuous emotional dynamics            | yes    |
| A closed regulatory loop                 | yes    |
| A limited influence of memory            | yes    |
| Absence of conflict with Phase 4         | yes    |
| A single source of the current state     | yes    |
| Extensibility without refactoring        | yes    |
