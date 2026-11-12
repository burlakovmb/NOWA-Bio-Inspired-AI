# Issue #58: procurement sandbox on two-tier plasticity

Russian: [issue-58-sandbox-two-tier-plasticity.ru.md](issue-58-sandbox-two-tier-plasticity.ru.md)

## Problem and scope

[Issue #58](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/58) concerns
`Demo/Virtual company/src/nowa_sandbox`, a separate host from the employee and
laboratory hosts adapted in PR #51. Before this change, sandbox decisions used
wall-clock time, direct `sleep_cycle()` skipped the one-per-sleep capture pass,
and the expected waking interval remained unset.

At the initial check on `2026-11-07`, core `src/` was identical at local
`a8d7503` and upstream `bd699d5`. That statement does not cover the newer
`039fd0a` / PR #63 learning changes. The correction belongs to Virtual company,
not to core learning parameters. Development agents and numerical diagnostics
do not call an external LLM from NOWA's runtime.

## Host contract

- A sandbox decision and `world.tick()` represent one day: `86400` seconds.
  Every real core step receives that explicit `dt`. A wrapper with only
  `**kwargs` does not establish `dt` forwarding; use `advance_time(dt)` when
  needed, without advancing twice or retrying internal `TypeError` failures.
- After spawn or restore, the trainer sets
  `expected_wake_interval_s = sleep_every_n_days * 86400`. Preserve explicit
  tau, ratios, learning rates, clamps, and capture parameters.
- Sleep enters through `Agent.sleep(cycles=1)`. This preserves the former one
  replay-cycle schedule while enabling decay, capture, habit updates, visit
  transfer, and episode closure. A legacy stub may use its manager only when
  no callable agent sleep API exists.
- Concrete orders retain their existing reward policy (`0.4` / `-0.3`), action,
  context, and consequence. A known outcome must also be registered through
  `_record_known_outcome`; plain hippocampal storage is not enough for labile
  tags and two-tier capture. Do not silently swallow a real core learning error.
- After restore, [`AgentStorage.load_agent`](../../src/storage.py) ([issue
  #68](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/68)) calls
  `_bind_restored_two_tier`: once `agent.labile` and `agent.plasticity` are
  restored, each distinct `sleep_manager` (the `sleep_manager` argument and
  `agent.sleep_manager` when present) receives those same object references.
  `_host_agent` is set only when missing or already this agent. [`Agent.sleep()`](../../src/agent.py)
  reapplies the same `labile`, `plasticity`, and `_host_agent` wiring before
  consolidation. Pickle layout is unchanged; legacy saves without `labile_layer`
  install a new empty layer the manager must share. Demo adapters no longer
  ship `_rebind_sleep_manager` or `_rebind_learning_components`.
- Sandbox checkpoints must retain learned `IntentMemory` when present via demo
  extension `sandbox_intent_memory`
  (`Demo/Virtual company/src/nowa_sandbox/sandbox_checkpoint.py`); core does
  not serialize `intent_memory`. On load, the adapter relinks
  `agent.intent_memory` and the manager. Employee checkpoints use
  `vc_intent_memory` the same way. Older files without the extension key remain
  loadable.
  Extend the agent file through a temporary sibling and atomic replacement.
  Invalid optional habit data must not abort a successful base restore: keep
  existing habits and report a warning. This does not make the whole metadata
  and agent-file pair a transaction or repair a corrupt base checkpoint.

Waking plasticity is bounded, decaying labile activity. Stable learning remains
inside sleep. The Maintainer's microconsolidation analogy does not authorize
stable-tier writes during ordinary waking steps.

## Acceptance and evidence

Real-agent strict-mode tests must verify explicit time, waking stable freeze,
actual order outcomes entering labile, and sleep capture/closure exactly once.
Detect even swallowed `WakingLearningError`. Check restored custom capture
parameters, live component identity, persistence, stub compatibility, and no
hidden retries of failing core calls. Existing employee learning tests must
continue to pass.

Recheck Stage 1a/1b without changing thresholds, rewards, genome, or legacy
results to obtain a pass. Distinguish short diagnostics using a historical
baseline from a full five-seed qualification. Preserve existing employee minds;
evaluate retained tags on copies and do not silently repair or retrain them.

The public [checkpoint report](../qa/vc-onboarding-snapshot-2026-11-08.en.md)
records version limits and verification. Private employee corpora, checkpoints,
local development settings and session protocols are not repository deliverables.
