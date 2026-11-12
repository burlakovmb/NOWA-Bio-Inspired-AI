# QA issue #68 — sleep manager rebound to the restored labile layer

Branch: `team/68-sleep-manager-rebind`. Code: `959e191`, `17d50bc`. HEAD at run time: `17d50bc`.
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/70
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/68
Русский: [issue-68-sleep-manager-rebind.ru.md](issue-68-sleep-manager-rebind.ru.md).

Product code was not changed in this QA pass. No pull request was created or merged. The full `pytest` suite was not run locally.

Machine: Python 3.12.3, pytest 9.2.0. Targeted tests and probes ran with `NOWA_STRICT_LEARNING=1`. Tamagochi: `use_pygame=False`, `use_gui=False`, `SDL_VIDEODRIVER=dummy` (mixer unavailable; the agent still constructed).

## Verdict

**PASS** (`17d50bc`).

After restoring labile, `load_agent` calls `_bind_restored_two_tier`. The manager passed as an argument, and `agent.sleep_manager` when it is a different object, receive the `labile` and `plasticity` now on the agent. `_host_agent` changes only when it is missing or already this agent. The pickle format was not extended: a save still carries `labile_layer`. A file without `labile_layer`, `plasticity_config`, and `host_clock_s` loads as an empty layer, identity holds, and `deep_sleep` does not raise.

A direct `SleepManager.deep_sleep` after load, without `Agent.sleep`, consumes the restored tag: Go `0.50 → 0.5800000000000001`, the episode contribution is gone, and a sentinel on the previous layer object remains. `Agent.sleep` does the same once that layer already belongs to the sleeper.

Employee `load_mind` and sandbox `restore_agent` no longer call their helpers. Identity, lesson capture, and the `vc_intent_memory` / `sandbox_intent_memory` habits are in place. The repository has no calls to `_rebind_sleep_manager` or `_rebind_learning_components`.

Tamagochi: after `_do_load_session` the `nowa` host, the cage, and the manager share one restored layer, and `_host_agent` is `nowa`. `nowa.sleep()` and a direct `deep_sleep` keep that layer and consume the tag (channel `morning_awakening`, Go delta `0.07999999999999996`).

CI pytest on PR #70 was `pending` on the single read. The run was not waited on.

## Coverage

| # | Check | Result |
| --- | --- | --- |
| 1 | save with a non-empty labile → load into a fresh agent → `sleep_manager.labile is agent.labile`, same for `plasticity` → one sleep consumes the tag | Pass. Direct `deep_sleep(cycles=1)`: Go `0.5800000000000001`, contributions empty. The sentinel contribution stayed on the previous layer object |
| 2 | Legacy pickle without `labile_layer` (`plasticity_config` and `host_clock_s` removed as well): empty layer, identity, sleep does not raise | Pass. No contributions. `_host_agent` is the loaded agent. `deep_sleep` returns no error, Go `0.5700000000000001` (sleep-rate step without a tag) |
| 3 | Direct `deep_sleep` after load, without `Agent.sleep` | Pass. Same run as item 1. The targeted test also drives `Agent.sleep` and expects Go `0.58` |
| 4 | Employee `load_mind` and sandbox `restore_agent` without the demo helpers: identity, lesson capture, intent-extension habits | Pass. Employee: trace strength `0.2`, after `sleep(cycles=1)` the contribution is empty and the episode is `consolidated`. Sandbox: three persistence tests |
| 5 | Tamagochi `_do_load_session` / `_rewire_two_tier_host`: after load, one layer, and the host's sleep does not roll back to the old one | Pass. Below |
| 6 | A foreign `_host_agent` is not replaced | Pass. A foreign host stays. A missing `_host_agent` is set to the loaded agent. Two distinct managers receive the restored layer; the argument keeps its foreign host |
| 7 | No remaining calls of the deleted helpers | Pass. Search for `_rebind_sleep_manager` and `_rebind_learning_components`: 0 matches |
| 8 | CI on PR #70 | `pytest` **pending**. Run [43250793476](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/actions/runs/43250793476), job `131295708906`. One read, no wait |

Targeted pytest from the repository root, exit 0:

`python3 -m pytest -q --no-header -p no:warnings tests/test_issue13_two_tier.py::test_save_load_restores_labile_clock_and_config tests/test_issue13_two_tier.py::test_load_rebinds_sleep_manager_and_consolidates_restored_labile tests/test_issue13_two_tier.py::test_sleep_rebinds_manager_when_the_agent_layer_was_replaced tests/test_issue13_two_tier.py::test_load_keeps_a_foreign_sleep_manager_host "Demo/Virtual company/tests/test_employee_checkpoint_plasticity.py" "Demo/Virtual company/tests/test_sandbox_checkpoint.py::TestPersistence::test_resume_rebinds_custom_plasticity_and_pending_labile_tags" "Demo/Virtual company/tests/test_sandbox_checkpoint.py::TestPersistence::test_checkpoint_preserves_sleep_formed_habits_and_manager_reference" "Demo/Virtual company/tests/test_sandbox_checkpoint.py::TestPersistence::test_old_checkpoint_without_intent_extension_keeps_fresh_memory"`

**11 passed** in 0.27s.

Short probes (not in the repository): core (identity, direct `deep_sleep`, legacy, foreign and missing `_host_agent`, two managers), employee (`store_lesson` plus `apply_outcome` under `learning_allowed`, strength `0.2`), a live `ChinchillaAgent`.

Not run:

| # | Scenario | Why |
| --- | --- | --- |
| 1 | Full `pytest` | CI on PR #70 runs it |
| 2 | Many generations, seed sweeps | Outside this narrow checklist. One episode, fixed seeds in the probes |
| 3 | Interactive Tamagochi GUI | The contract was checked on `ChinchillaAgent(use_pygame=False, use_gui=False)` |

### Tamagochi

`_do_load_session` passes the cage (`agent=self`) and its `sleep_manager` to `load_agent`, then calls `_rewire_two_tier_host` on the next line. The demo has no other `load_agent` call. `_bind_two_tier_host` runs in the constructor before any load, so `nowa` already exists.

Before the save, `source.labile is source.nowa.labile is source.sleep_manager.labile`. Channel `morning_awakening` starts at Go `0.5805786188392569` (the cage weight after construction, not the core `0.5`). `nowa.commit_executed_transition` writes contribution `ep-1`, reward `1.0`, and does not move stable Go. The hippocampus has 11 experiences; only `ep-1` has `td_committed_reward`.

After `_do_load_session` on a fresh cage: `nowa.labile is labile is sleep_manager.labile`, the same for `plasticity`, `_host_agent is nowa`, the layer is not the object the host had before load, and `ep-1` is present.

`nowa.sleep(cycles=1)`: no error, the same restored layer, `_host_agent` still `nowa`, no contribution, Go `0.6605786188392568` (delta `0.07999999999999996`, one undecayed `+1` step). A second cage through direct `deep_sleep(cycles=1)` shows the same identity and the same delta.

Between `load_agent` and `_rewire_two_tier_host` the manager already points at the cage's restored layer, while `nowa.labile` is still the previous object and `_host_agent` stays `nowa`. Public `_do_load_session` closes that window before it returns. A separate core probe: the host's `Agent.sleep` inside that window points the manager back at the host's old layer, and the restored contribution is not captured. After `_rewire_two_tier_host` the window is closed and the contribution is still present.

## Defects

No defects against the DoD.

## Recommendations

`Agent.sleep` intentionally overwrites the manager's `labile`, `plasticity`, and `_host_agent` with the sleeper's objects. `test_sleep_rebinds_manager_when_the_agent_layer_was_replaced` locks that. Inside the window between `load_agent` and `_rewire_two_tier_host`, that sleep rolls the manager back to the host's old layer. `_do_load_session` currently has nothing between those two calls. Do not insert a sleep or a manager read there.

`deep_sleep` selects episodes from the manager's own hippocampus. Passing a manager whose hippocampus is not the object loaded by `load_agent` leaves the bound layer visible but does not capture the tag: the contribution remains, channel `go` stays at `0.5`, the foreign `_host_agent` is unchanged, the manager has `0` experiences, and the loaded agent has `1`. Employee, sandbox, and Tamagochi are not wired that way: the manager's hippocampus and the `load_agent` argument are one object.

`_bind_restored_two_tier` swallows any `setattr` exception. That did not happen on an ordinary `SleepManager`.

## Release readiness

The functional DoD holds on `17d50bc`. Release is not signed off until pytest CI on PR #70 is green: the single read was `pending`.
