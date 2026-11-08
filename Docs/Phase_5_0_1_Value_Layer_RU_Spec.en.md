# Phase 5.0.1 --- Value Layer and TD Error (Engineering Version)

Russian version: [Phase_5_0_1_Value_Layer_RU_Spec.ru.md](Phase_5_0_1_Value_Layer_RU_Spec.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.


## 1. Purpose

Implement a full state-evaluation layer V(s) with learning through TD
error:

δ_t = r_t + γ V(s\_{t+1}) − V(s_t)

Added clarifications: - Formalization of state encoding - The policy for storing
value - A clear integration with dopamine - Constraints on reward -
Recommended hyperparameters - A set of test cases

------------------------------------------------------------------------

## 2. State Encoding

### 2.1 Requirements

StateEncoder must:

-   Be deterministic
-   Use only state_snapshot
-   NOT use the affective background
-   NOT use neuromodulator levels
-   NOT use the regulation state

### 2.2 Format

Recommended:

state_key = hash(normalized_state_representation)

where normalized_state_representation: - a dictionary with a fixed set of
features - sorting of keys is mandatory - values are rounded to a
fixed precision (for example 3 digits)

### 2.3 Constraints

-   The dimensionality of the state must be bounded
-   Noisy or high-frequency parameters must not be included

### 2.4 Semantic Vectorization of Textual Features (implemented)

For textual fields in `state_features/state_vector`, deterministic semantic hashing is used:

1. `tokenize(text)`:
   - conversion to lower case (`casefold`)
   - splitting on non-word characters and `_`
   - example: `eat_food -> ["eat", "food"]`
2. `word_vec(token)`:
   - a stable SHA-256 hash over `(token, index)`
   - projection into the range `[-1, 1]`
   - normalization to a unit vector
3. `semantic_vector(text)`:
   - averaging `mean(word_vec(t))` over tokens
   - final normalization
4. Similarity:
   - cosine similarity between state vectors

Properties:
- determinism across runs
- low cost without heavy embeddings
- robustness to separator variants (`eat_food` and `eat food`)

------------------------------------------------------------------------

## 3. Storage of Value

### 3.1 Model

V is stored as:

Dict\[state_key, float\]

### 3.2 Size Limit

-   max_states = 50_000 (recommended)
-   On overflow --- LRU eviction

### 3.3 Initialization

V(s) by default = 0.0

------------------------------------------------------------------------

## 4. TD Error

δ_t = r_t + γ V(s\_{t+1}) − V(s_t)

### 4.1 Constraints

-   δ_t clamp \[-1, 1\]
-   \|V(s)\| ≤ 1 / (1 − γ) for \|r\| ≤ 1; default γ = 0.95 → 20 (see [issue-18-minor-learning-fixes.en.md](specs/issue-18-minor-learning-fixes.en.md))
-   One update per tick

### 4.2 Recommended Parameters

alpha = 0.03 gamma = 0.95

------------------------------------------------------------------------

## 5. Integration with Dopamine

### 5.1 Rule

dopamine_delta = clamp(δ_t \* k, -0.1, 0.1)

where k = 0.5 (recommended)

### 5.2 Critical Constraint

-   The dopamine update is additive
-   It passes through the standard clamp of the neuromodulator layer
-   It does NOT affect the affective background directly
-   It does NOT affect reward

A break in the cycle is mandatory:

Value → dopamine → (regulation clamps) → NO direct feedback into reward

------------------------------------------------------------------------

## 6. Reward Constraint

Reward must:

-   Be computed BEFORE affective regulation
-   NOT depend on the current dopamine
-   NOT depend on the Value Layer

Reward may be: - external - task-based - environment-based

------------------------------------------------------------------------

## 7. Interface

update( state_snapshot, reward: float, next_state_snapshot, gamma: float
= 0.95, alpha: float = 0.03, timestamp: float ) -\> { "value": float,
"td_error": float, "state_key": str }

------------------------------------------------------------------------

## 8. Expected Dynamics

After 1000+ steps:

-   A distribution of V(s) appears
-   An asymmetry of preferences arises
-   A stable shift toward advantageous states appears

------------------------------------------------------------------------

# 9. Test Cases

## 9.1 Positive Surprise

Scenario: - V(s_t) = 0.2 - reward = 0.8 - V(s\_{t+1}) = 0.3

Expected: δ \> 0 dopamine_delta \> 0 V(s_t) increases

------------------------------------------------------------------------

## 9.2 Negative Surprise

Scenario: - V(s_t) = 0.6 - reward = 0.1 - V(s\_{t+1}) = 0.2

Expected: δ \< 0 dopamine_delta \< 0 V(s_t) decreases

------------------------------------------------------------------------

## 9.3 Zero Surprise

Scenario: - reward matches the expectation

Expected: δ ≈ 0 dopamine_delta ≈ 0 V(s_t) is stable

------------------------------------------------------------------------

## 9.4 Stability Stress Test

-   10_000 updates
-   Check:
    -   V stays within \|V\| ≤ 1 / (1 − γ) for the active γ and \|r\| ≤ 1
    -   There is no neuromodulator_drift
    -   Stability index \> 0.6

------------------------------------------------------------------------

## 9.5 Memory Load Test

-   max_states is exceeded
-   Check the correctness of LRU eviction

------------------------------------------------------------------------

## 9.6 Dopamine Isolation Test

-   Check that a change in δ does not change reward
-   Check the absence of cyclic amplification

------------------------------------------------------------------------

Phase 5.0.1 is considered successful if:

-   Value converges
-   δ is distributed symmetrically about 0
-   Stability (4.5) remains stable
-   There is no runaway amplification
