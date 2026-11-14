# QA issues #16 and #31 — safe versioned agent state

Branch: `team/issue-16-31-safe-storage`. Code under test: `1c50cd1`.
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/71
Issues: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16, https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/31
Русский: [issue-16-31-safe-storage.ru.md](issue-16-31-safe-storage.ru.md).

Product code was not changed. No pull request was created or merged. The full `pytest` suite was not run locally. The task states that CI pytest on `1c50cd1` is green; this run did not re-read Actions.

Machine: Python 3.12.3, pytest 9.2.0. Probes and tests used `NOWA_STRICT_LEARNING=1`. Tamagochi: `use_pygame=False`, `use_gui=False`, `SDL_VIDEODRIVER=dummy`.

Owner decision applied here: old pickle saves are not supported, there is no migration, and the legacy `last_decay_ts` fallback checkbox is closed by rejection rather than by conversion.

## Verdict

**PASS** (`1c50cd1`).

`load_agent`, `load_checkpoint`, and `load_mind` reject pickle and unknown JSON before any object from the file is called. A `__reduce__` payload aimed at `os.system` (`touch` of `/tmp/nowa-qa-16-31-marker`), including protocol 0 (`cposix`) and a raw `cos\nsystem` GLOBAL, did not create the marker.

The hippocampal repro from #16 no longer double-decays. After one hour the energy is `0.5485`. A save/load at that same clock leaves `0.5485`. A second `_apply_decay()` at the same clock leaves `0.5485` on both the continuous instance and the reloaded one (the old reloaded value was `0.30085225`). `last_decay_ts` comes back as `1790003600.0` and `last_activated` stays `1790000000.0`.

One minor remains: a schema-1 document whose episode list and cortex patterns are strings is applied and `load_agent` returns. That is not code execution and does not fail the #16 / #31 acceptance checks.

## Coverage

**9 passed / 1 failed / 3 not run.**

| # | Check | Result |
| --- | --- | --- |
| 1 | Malicious pickle, schema 99, wrong format, broken JSON, unknown closed-list type on `load_agent`, `load_checkpoint`, `load_mind` | Pass. Marker file absent. Protocol 4: `StateFormatError` / `CheckpointError` `Old pickle saves are not supported and cannot be loaded.` Protocol 0 and the raw GLOBAL: `Unrecognized save format; expected a JSON … document.` Schema 99: `Unsupported schema version 99` (agent/mind read version 1, checkpoint reads version 2). Unknown `os.system` object: `unknown stored type 'os.system'`. `call` tag: `unknown state tag 'call'`. Enum name `os.system`: `unknown stored enum`. `decode_tree` rejects `subprocess.Popen` the same way |
| 2 | `pickle.load` / `pickle.loads` / `allow_pickle=True` / `eval(` / `exec(` on agent-state load paths | Pass. Repository `*.py` search: those calls are absent. `pickle.dumps` appears only in `tests/test_safe_agent_state.py` and `Demo/Virtual company/tests/test_sandbox_checkpoint.py`. `src/`, `Demo/Virtual company/src`, and `Demo/Tamagochi Chinchilla` have no `pickle.load`. `ast.literal_eval` in `gui_configurator_controller.py` is outside this load path |
| 3 | Episodes, habit, arbitrator, labile layer: save, load into a new instance, same pressures and winner | Pass. Context `["bin", "north"]`: `go` `0.6653165402701486`, `stop` `0.0`, winner `go` on both. Intent dict and arbitration snapshot match. Two intent traces, mode `habitual` |
| 4 | `last_decay_ts`, two save/load at one clock, next equal interval plus one `_apply_decay()` | Pass. Energy after the first hour and after two save/load cycles: `0.5485` (weight `0.5485`). Same-clock second decay: both `0.5485`. Next 3600s and one decay: both `0.30085225`, same `last_decay_ts` |
| 5 | `_bind_restored_two_tier`, rebind in `Agent.sleep`, file without `labile_layer` | Pass. A live contribution `ep-1` is still on the same layer object after a file with `labile_layer` removed. Pytest: `test_save_load_restores_labile_clock_and_config`, `test_load_rebinds_sleep_manager_and_consolidates_restored_labile`, `test_sleep_rebinds_manager_when_the_agent_layer_was_replaced` |
| 6 | Sandbox `--resume-from`: quarter, RNG, genome, stage 1b suppliers, habits | Pass. `test_sandbox_checkpoint.py` (genome, RNG, habits, foreign pickle, schema). `test_resume_extends_the_run` (quarters `1,2,3,4`). `test_checkpoint_carries_suppliers_across_a_resume` (reliability map unchanged). `test_resume_from_missing_checkpoint_raises` |
| 7 | Employee `mind.nowa`, sleep after load, onboarding `baseline.nowa` / `cycle-001.nowa` | Pass. `test_employee_checkpoint_plasticity.py` (includes sleep after load matching in-process sleep). `test_real_core_sleep_checkpoint_and_reload` writes `cycle-001.nowa`, records the baseline event, and `evaluate` loads `training/baseline.nowa` and `mind.nowa`. `test_legacy_mind_without_intent_extension_still_loads` |
| 8 | GUI save/load at code and unit level | Pass. `save_state` / `load_state` pass `conflict_arbitration`, `intent_memory`, and `neuromodulators`. After the three steps, `to_dict` matches on the loaded object: dopamine `0.20119146386152442`, cortisol `0.12385272848128315`, no other key mismatch except the comparison ignored `timestamp`. `get_save_files` still lists `.pkl`. `load_agent` on that file raises `StateFormatError` with `Old pickle saves are not supported and cannot be loaded.` `load_selected` catches `Exception` and puts `str(e)` in the error dialog. The Tk dialog was not clicked. Tamagochi `test_session_persists_runtime_counters` passed (`total_sim_time` `123.4`, `tick_count` `321`) |
| 9 | Storage regression, sample of existing tests | Pass. `test_save_load_affect.py`, `test_chains_save_load.py`, `test_conflict_arbitration_storage.py`, `test_agent_lifetime_save_load.py`, plus `test_safe_agent_state.py`. Whole targeted pytest: **41 passed** in 2.07s |
| 10 | Schema-1 document with string episode list and string cortex patterns | Fail. See the defect |

Not run:

| # | Scenario | Why |
| --- | --- | --- |
| 1 | Full `pytest` | CI on `1c50cd1` is stated green. Not repeated here |
| 2 | Re-read of the Actions run | The task said not to wait on CI |
| 3 | Clicking the Tk save/load dialog | Checked at unit level and by reading `load_selected` |

Targeted command, exit 0:

`SDL_VIDEODRIVER=dummy python -m pytest -q --no-header -p no:warnings tests/test_safe_agent_state.py tests/test_issue13_two_tier.py::test_save_load_restores_labile_clock_and_config tests/test_issue13_two_tier.py::test_load_rebinds_sleep_manager_and_consolidates_restored_labile tests/test_issue13_two_tier.py::test_sleep_rebinds_manager_when_the_agent_layer_was_replaced tests/test_save_load_affect.py tests/test_chains_save_load.py tests/test_conflict_arbitration_storage.py tests/test_agent_lifetime_save_load.py "Demo/Virtual company/tests/test_sandbox_checkpoint.py" "Demo/Virtual company/tests/test_employee_checkpoint_plasticity.py" "Demo/Virtual company/tests/test_onboarding.py::test_legacy_mind_without_intent_extension_still_loads" "Demo/Virtual company/tests/test_onboarding.py::test_real_core_sleep_checkpoint_and_reload" "Demo/Virtual company/tests/test_run_sandbox.py::TestCheckpointing::test_resume_extends_the_run" "Demo/Virtual company/tests/test_run_sandbox.py::TestCheckpointing::test_resume_from_missing_checkpoint_raises" "Demo/Virtual company/tests/test_run_sandbox.py::TestStage1bCli::test_checkpoint_carries_suppliers_across_a_resume" "Demo/Tamagochi Chinchilla/tests/test_session_persistence.py"`

## Defects

### [MINOR] Schema-1 document with a string episode list is applied and reported as success

- Steps: write UTF-8 JSON `format` `nowa-agent-state`, `schema_version` `1`, `state.hippocampus_experiences` = `"not-a-list"`, `state.cortex_patterns` = `"not-a-dict"`. Call `AgentStorage.load_agent` with a live `NOWAHippocampus` and `CortexMemory`.
- Expected: `StateFormatError`. The live episode list, signatures, and patterns stay as they were.
- Actual: the call returned `None`. `experiences` became the string `not-a-list`, `signatures` became `[]`, `patterns` became the string `not-a-dict`. No exception, so `GUI.load_state` treats the load as success. No code ran.
- Where: `src/storage.py`, `AgentStorage.load_agent`, the assignments to `hippocampus.experiences` and `cortex.patterns`.
- Severity: minor.

## Recommendations

- Reject a document before assignment when `hippocampus_experiences` is not a list or `cortex_patterns` is not a dict. Cover it in `tests/test_safe_agent_state.py`.
- Add one side-effect test: protocol 0 `__reduce__` to `os.system` and a raw `cos\nsystem` GLOBAL, fed to `load_agent`, `load_checkpoint`, and `load_mind`. Assert the marker file is absent. Today's test pickles a dict with the default protocol and checks `load_agent` only.
- The same test file does not cover broken JSON, an unknown `__nowa_type__`, or a neuromodulator `to_dict` round-trip. Checkpoint tests cover pickle and schema 99 for `load_checkpoint` only.
- Protocol 0 is rejected as generic unrecognized JSON. The bytes are not unpickled. Extending `_looks_like_pickle` would only change the message to the pickle sentence.
- `load_agent` still swallows restore errors for several subsystems, including intent and arbitration (`except Exception: pass`). A corrupt dict on an otherwise valid file was not fed in this run. Worth a test that a broken `intent_memory` does not return success with an empty habit store.
- The new round-trip test checks that continuous and reloaded decay match. It does not pin the historical `0.5485` / `0.30085225` pair. The probe did.

## Release readiness

Ready for #16 and #31. The minor does not restore pickle execution and does not bring back the double decay. Old `.pkl` files stay unloadable, which matches the owner decision.
