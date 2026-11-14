# Sleep consolidation (NOWA core)

Russian: [SLEEP.ru.md](SLEEP.ru.md)

Overview of tiers and the host contract: [Docs/architecture/two-tier-plasticity.en.md](../Docs/architecture/two-tier-plasticity.en.md).

`Agent.sleep(cycles=...)` is the **only** entry that opens `learning_allowed()` for stable-tier writers. Implementation: `src/agent.py` (`sleep`), `src/sleep.py` (`SleepManager.deep_sleep`, `_consolidate_two_tier_once`).

## One sleep, one pass per episode

At the start of `deep_sleep`, **before** the usual `sleep_cycle` loop:

1. Decay labile tags to the host clock at sleep onset.
2. Select pending episodes: known outcome and not yet closed (`consolidated` false, or `outcome_revision` changed after consolidation).
3. Order them by **spec replay priority** (see below) — this orders **only** the two-tier batch, not the capped EDPC score inside replay selection.
4. For each episode in that order, in one batch:
   - **Capture** κ of the remaining (decayed) labile Go/NoGo tag into stable weights (`κ = capture_kappa`, default **0.5**).
   - **Compensated channel step:** `η_eff = eta_channel_sleep − κ·η_labile_channel` (defaults **0.08 − 0.5×0.02 = 0.07**). Apply D1/D2-like updates on stable Go/NoGo with `g_DA = 1` (no encoding neuromodulator scale). An undecayed `+1` with empty tag still adds **+0.07** on Go; with a full waking tag, capture adds **+0.01** and the step **+0.07** → **+0.08** total (e.g. Go **0.5 → 0.58**).
   - **Habit EMA** on the channel: `habit_delta = 0.20 × affect_gain × (target − strength)` with `target ∈ {0,1}` from reward sign and `affect_gain = clamp(affect_gain_at_encoding, 0.25, 1.5)`; `intent_memory.apply_outcome` for context habits with the same gain.
   - Pop labile Q/channel contribution for the episode (Q is **not** captured into stable table).
5. Flush queued external learning hooks and replay **slow affective** statistics from waking buffers.
6. Transfer labile visit counters into stable visit counts and reset labile visits.

Then `cycles` iterations of `sleep_cycle()` run (replay TD on **stable Q only**, cortex clustering, SHY BG decay/normalize, temporal chains, forget unstable, `degrade_unused`, neuromodulator sleep dynamics, SAC, etc.). Replay budgets and variance gates from PR #35 still apply.

Each `sleep_cycle` advances canonical affect by one slice of simulated sleep time (`SleepManager._affective_cycle_dt()`): default **1800 s** per cycle, or an even share of `sleep_duration_seconds` across `deep_sleep` cycles. Calls use `AffectiveSpace.step(..., asleep=True)` so axis clearance and return of `baseline` toward `baseline_setpoint` run **4×** faster than wake (`SLEEP_RECOVERY_SCALE`). Details: [specs/issue-54-affect-simulated-time.en.md](specs/issue-54-affect-simulated-time.en.md).

After all cycles, episodes in the batch are marked `consolidated = True` with `consolidated_reward` and `consolidated_revision`. A **second** sleep with no new episodes must not change stable fingerprint fields (`value_layer`, `slow_affect`, `visit_counts`, `strategies`) except SHY/down-scale side effects when cycles &gt; 0.

`sleep(cycles=0)` runs the two-tier pass and marking **without** `sleep_cycle` (no SHY, no cortex multiply from cycles).

## Replay priority (ordering only)

`SleepManager.spec_replay_priority(exp)` with weights from `PlasticityConfig.replay_priority_weights` (default **1.0 |δ| + 0.5|r| + 0.25·novelty + 0.25·emotional_salience**), δ recomputed on **current stable** values. Ties break by `episode_id`. This does **not** add those terms inside `_compute_replay_priority` for EDPC-filtered replay.

## Q vs Go/NoGo vs habits

| Mechanism | What moves |
|-----------|------------|
| Labile waking tags | Fast bias; decay if not consolidated |
| Sleep replay (`_apply_replay_td_bg`) | **Stable Q** only (under guard opened by `deep_sleep`, not by replay itself) |
| Capture + `η_eff` step | **Stable Go/NoGo** |
| Habit EMA + `apply_outcome` | **Stable** habit traces and channel habit strength |

## Revisions and loss

- Rating changed **before** first consolidation: only the final labile contribution matters; one stable write on sleep.
- Rating changed **after** consolidation: treated as a **new** observation; previous stable write is **not** rolled back; next sleep applies the new reward again.
- Episode evicted from hippocampus before sleep: `lost_unconsolidated` increments; labile contribution dropped; no stable effect.

## Related parameters (`PlasticityConfig`)

| Field | Default | Role |
|-------|---------|------|
| `expected_wake_interval_s` | host should set; else 3600 s + warning | Sets τ_L via `tau_labile_ratio` |
| `capture_kappa` | 0.5 | Fraction of labile channel tag moved to stable |
| `eta_channel_sleep` | 0.08 | Stable Go step before κ compensation |
| `eta_labile_channel` | 0.02 | Waking tag size; enters `η_eff` |
| `replay_priority_weights` | (1.0, 0.5, 0.25, 0.25) | Batch ordering |

Full table: issue #13 spec §6.
