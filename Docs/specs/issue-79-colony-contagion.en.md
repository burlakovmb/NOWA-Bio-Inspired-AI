# Issue #79 — local fear contagion in the Colony demo

Russian: [issue-79-colony-contagion.ru.md](issue-79-colony-contagion.ru.md)

PR #84, branch `team/issue-79-colony-contagion`. Closes the Colony side of [issue #79](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/79). Builds on alarm and simulated-second affect ([issue-54-affect-simulated-time.en.md](issue-54-affect-simulated-time.en.md), [issue-78-affect-time.en.md](issue-78-affect-time.en.md)).

Code (demo only): `Demo/Colony chinchillas/src/colony_agent.py`. Tests: `Demo/Colony chinchillas/tests/test_issue_79_contagion.py`. **`src/` is unchanged** — no core retuning for the demo.

---

## 1. Problem

Before this change, `ChinchillaAgent` in the Colony host spread emotional pressure globally and fed it back into learning:

1. **Global `fearful` in conflict:** any colony member with `affect_tone == "fearful"` added conflict, regardless of zone or acquaintance — one stressed animal could keep the whole colony in appraisal conflict.
2. **Stress → conflict loop:** `conflict += stress * 0.3` raised conflict from the listener’s own stress, which then increased stress again via appraisal (`_derive_affective_space_inputs`).
3. **Bowl-level reward:** reward included a term from shared bowl fill instead of only the animal’s own hunger/thirst dynamics.
4. **Double stress in reward:** `reward -= stress * 0.3` penalised stress that was already represented on the affect axis.
5. **`alarm_call` context:** the `alarm_call` event could appear whenever a neighbour looked fearful, not only on the tick a bark was first heard (see issue #54 alarm bout logic).
6. **No habituation** on repeated same-zone fearful tone from a known neighbour.
7. **No explicit crowding** at a food bowl beyond generic social contact.

---

## 2. Solution (host only)

All behaviour lives in `colony_agent.py`. Symbols below are module-level constants unless noted.

### 2.1 Local fearful tone in conflict

`_compute_conflict(host_dt)` adds fear contagion only when:

| Condition | Required |
| --- | --- |
| Perception category | `contact` (same zone as listener; see `_perceive`) |
| Acquaintance | `other_id` in `knowledge` (strangers in-zone are `unknown_nearby`, not `contact`) |
| Tone | `public_state.affect_tone == "fearful"` |

Contribution per neighbour (once per tick): `FEAR_CONTAGION_CONFLICT * gain`, with `gain` from `_fear_contagion_gain`. Fresh exposure at `dt = 0` gives `gain = 1.0` → **+0.1** conflict before the cap at 1.0.

**Removed:** scanning the whole colony for any fearful agent; **removed:** conflict from strangers in the same zone (novelty in `_compute_novelty` still handles unknowns).

### 2.2 Habituation and recovery (`fear_contagion`)

Per known neighbour id, the host keeps `self._fear_contagion[other_id] = (sensitivity, stamp)`.

| Constant | Value | Role |
| --- | ---: | --- |
| `FEAR_CONTAGION_CONFLICT` | 0.1 | Max conflict multiplier at full sensitivity |
| `FEAR_CONTAGION_FLOOR` | 0.3 | Sensitivity floor after long exposure |
| `FEAR_CONTAGION_EXPOSURE_TAU_S` | 120.0 | τ while neighbour is fearful in contact |
| `FEAR_CONTAGION_RECOVERY_TAU_S` | 120.0 | τ while neighbour is absent from conflict exposure |

`_fear_contagion_gain(other_id, host_dt, exposed=True/False)`:

- **Exposed:** sensitivity drifts toward the floor:  
  `sens ← FLOOR + (sens − FLOOR) × exp(−dt / τ_exposure)`.
- **Not exposed** (id still in map but not fearful-in-contact this tick): sensitivity recovers toward 1.0 with τ_recovery.

Integration uses **host simulated seconds** (`host_dt` passed from `sim_step`), so splitting 120 s into many ticks matches one long step (see tests).

### 2.3 `alarm_call` context event

`_build_context_events` appends `alarm_call` only when `self._alarm_heard_this_tick` is true.

`_perceive_alarm_calls` clears the flag at the start of perception, then sets it when this tick is the **first** hearing of a caller’s current `event_id` (same/adjacent zone, `_is_emitting_alarm()`). Later ticks of the same bout do not set the flag even while the 2 s audible window is open (`ALARM_CALL_AUDIBLE_S`).

This replaces tying `alarm_call` to merely seeing a fearful tone (issue #54 §7.2 note is superseded for this tag).

### 2.4 No stress self-loop in conflict

**Removed:** `stress * 0.3` from `_compute_conflict`. High own stress alone yields **zero** conflict from that term (`test_stress_alone_does_not_create_conflict`).

### 2.5 Reward from own physiology only

`_compute_reward`:

- **Removed:** adjustment from shared bowl level when the animal is sated.
- **Removed:** `reward -= stress * 0.3`.
- **Kept:** hunger/thirst offsets and deltas, failed eat/drink penalties, social bonus, `physiology_as_policy` alignment — including **negative** reward when hungry/thirsty or when eat/drink fails, which still drives stress through the core appraisal path (expected biology, not double-counting on the reward scalar).

Sated agents (`hunger`/`thirst` low) get **0** reward whether the bowl is full or empty and regardless of stress level.

### 2.6 Bowl crowding

`_bowl_crowd_conflict()` adds `BOWL_CROWD_CONFLICT = 0.15` for **each extra** animal with `current_action == "eat"` in the listener’s zone when that zone is in `FOOD_BOWL_ZONES` (`bowl_pellets`, `bowl_hay`). Hay and pellets are separate zones; the observer must stand in the bowl zone to feel crowding.

### 2.7 Persistence — `runtime.alarm.fear_contagion`

`_export_alarm_state` / `_restore_alarm_state` round-trip `fear_contagion` as `{caller_id: [sensitivity, stamp]}` alongside existing alarm fields (`heard`, `habituation`, …).

| Load case | Behaviour |
| --- | --- |
| Key missing | Empty map; next new contact uses sensitivity 1.0 |
| Malformed / non-numeric sensitivity | `_coerce_finite` → default 1.0; then clamp to `[FEAR_CONTAGION_FLOOR, 1.0]` |
| Missing entire `runtime.alarm` | Empty map; `_anchor_alarm_stress` path unchanged |

Alarm habituation save format is unchanged; only the new sibling key was added.

---

## 3. Tests

`Demo/Colony chinchillas/tests/test_issue_79_contagion.py`:

| Test | Covers |
| --- | --- |
| `test_fearful_tone_conflicts_only_in_the_same_zone` | Zone + acquaintance gating |
| `test_constant_fearful_neighbour_habituates_with_host_time` | dt invariance, floor, recovery |
| `test_stress_alone_does_not_create_conflict` | No stress loop |
| `test_bowl_crowding_counts_extra_eaters_in_that_zone` | Crowding |
| `test_alarm_call_label_only_when_a_call_is_heard_this_tick` | `alarm_call` tick |
| `test_reward_ignores_bowl_level_and_stress` | Reward |
| `test_fear_contagion_save_roundtrip_and_legacy_default` | Save/load |

Regression neighbours (QA): `test_issue_54_alarm.py`, `test_knowledge.py::test_tc08_alarm_call_affects_known_stronger_than_unknown`, `test_storage.py`.

---

## 4. QA

Report: [issue-79-colony-contagion.ru.md](../qa/issue-79-colony-contagion.ru.md) — **PASS** at `068edce`. `git diff main...HEAD -- src/` empty.

---

## 5. Observable effect (headless run, tech lead)

Colony run **1500 s simulated**, **seed 1**, **16 agents** (same scenario as issue acceptance notes). Compare **main** vs **PR #84** branch:

| Metric | main | PR |
| --- | ---: | ---: |
| Mean stress | 0.695 | 0.719 |
| Fraction of time with stress ≥ 0.45 | 0.819 | 0.849 |
| Mean cortisol | 0.716 | 0.488 |

**Ablation (counterfactuals on the same run setup):**

| Change removed | Effect on stress rise | Effect on cortisol |
| --- | --- | --- |
| Bowl-level reward bonus only (§2.5 bowl term) | Explains the **increase** in mean stress vs main | — |
| `stress * 0.3` in conflict and `stress * 0.3` in reward (§2.4, §2.5) | — | Explains **lower** cortisol vs main |

Mean stress and time above 0.45 remain high on PR because **real hunger** dominates: 16 animals drain shared bowls in ~300 s while refill is every `REFILL_DAY_S = 600` s (`Demo/Colony chinchillas/src/config_colony.py`, `simulation_runner.py`). Tuning bowl cadence or population vs resources is **demo environment** work, not issue #79.

Issue criterion “no stress ≥ 0.45 lock **from contagion alone**” is addressed by removing global fearful and stress loops; chronic elevation from hunger is expected and out of scope here (see [issue-78-affect-time.en.md](issue-78-affect-time.en.md) §5 demo plateau cross-ref).

---

## 6. Design principle

Strict biological fidelity in `src/`: only the Colony **host** (`colony_agent.py`) changed. Alarm bout impulses (issue #54), dt-correct affect (issues #54, #78), and genome constants are untouched.