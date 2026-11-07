# Phase 5.0 — Value Layer and TD Error

Russian version: [Phase_5_0_Value_Layer_RU_Spec.ru.md](Phase_5_0_Value_Layer_RU_Spec.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.

## 1. Aim of the Layer

To introduce a full state-value layer (Value Layer) that implements learning through the temporal-difference error (TD error):

```text
δ_t = r_t + γ V(s_{t+1}) − V(s_t)
```

The layer must:
- form a long-term direction of behaviour
- update the value of states through prediction error
- encode δ_t through dopamine (without substituting value learning)
- remain architecturally isolated from the affective background

---

## 2. Architectural Position

Order of the layers:

```text
State → Emotional/Affective → Expectations → Regulation (4.4) → Stability (4.5)
                                                              ↓
                                                       Value Layer (5.0)
                                                              ↓
                                              Action Selection / Planning
```

The Value Layer:
- reads the state snapshot
- reads reward
- reads γ
- does NOT alter the affective background
- does NOT alter semantic emotions
- does NOT alter regulation

---

## 3. Principal Entities

### 3.1 Value Function

```text
|V(s)| ≤ 1 / (1 − γ)   for |r| ≤ 1; default γ = 0.95 → 20
```

(`δ_t` remains clamped to `[-1, 1]`; see [issue-18-minor-learning-fixes.en.md](specs/issue-18-minor-learning-fixes.en.md).)

The implementation admits:
- a tabular model (state_hash → value), or
- an approximation (a network or a linear model)

Initialisation: V(s) = 0.0

---

### 3.2 TD Error

```text
δ_t = r_t + γ V(s_{t+1}) − V(s_t)
```

Constraint: δ_t ∈ [-1, 1] (clamp)

---

### 3.3 Update

```text
V(s_t) ← V(s_t) + α * δ_t
```

Parameters:
- α (learning rate): 0.01–0.1
- γ (discount factor): 0.90–0.99

---

## 4. Integration with Dopamine

Dopamine encodes δ_t, not reward.

Rule:

```text
dopamine_delta = clamp(δ_t * k, -0.1, 0.1)
```

where k is a scaling coefficient.

Important:
- Dopamine does not update the affective background directly.
- Regulation (4.4) may smooth dopamine through its own constraints.
- Stability (4.5) monitors a possible neuromodulator_drift.

---

## 5. Isolation Constraints

The Value Layer has no right to:
- alter emotional state directly
- alter the background
- alter expectations
- invoke regulation
- alter memory consolidation

It only:
- updates V(s)
- returns δ_t
- returns the current estimate V(s)

---

## 6. Interface of the Layer

```text
update(
    state_snapshot,
    reward: float,
    next_state_snapshot,
    gamma: float,
    alpha: float,
    timestamp: float
) -> {
    "value": float,
    "td_error": float
}
```

---

## 7. Stability Constraints

- The L2-norm of value updates per tick must be bounded
- δ_t is clamped to [-1, 1]
- α may be reduced dynamically under instability
- A cascade update more than once per tick is not admitted

---

## 8. Extensions (Later Phases)

Possible:
- eligibility traces (TD(λ))
- multi-step bootstrapping
- a separate goal value versus state value
- coupling with motivational systems

---

## 9. Expected Effect

After introduction:
- the agent begins to correct expectations systematically
- a long-term vector of preferences appears
- reward becomes surprise
- behaviour becomes trajectorial rather than reactive

---

Phase 5.0 is regarded as complete when:
- the TD error is computed correctly
- V(s) learns stably
- there is no neuromodulator drift
- Stability (4.5) remains within admissible bounds
