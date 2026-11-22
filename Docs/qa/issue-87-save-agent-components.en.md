# QA issue #87 — `save_agent` / `load_agent` with `agent=`

Branch: `fix/issue-87-save-agent-components`. HEAD at run time: `b698959`. Baseline: `89c10a0` (main). Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/87.
Russian: [issue-87-save-agent-components.ru.md](issue-87-save-agent-components.ru.md). Spec: [issue-87-save-agent-components.en.md](../specs/issue-87-save-agent-components.en.md).

Machine: Windows, Python 3.14.7, pytest 9.2.0, `NOWA_STRICT_LEARNING=1` from `tests/conftest.py`. The baseline runs used a copy of `src/` with `src/storage.py` from `89c10a0`; the rest of `src/` is the branch tree (no other `src/` file differs).

## Verdict

**PASS** (`b698959`).

A trained agent saved and loaded with `agent=` alone keeps all 8 `stable_payload` sections and all 9 affect components; on the baseline 2 sections and 9 components were lost. An `agent=` load equals a load with every component passed explicitly. The neuromodulator object stays shared between the agent and its sleep manager. Core, Virtual company and Tamagochi suites pass.

## Coverage

| # | Check | Result |
| --- | --- | --- |
| 1 | Training is not vacuous | Pass. 300 decisions at `dt = 1.5`, sleeps after 150 and 300: 128 episodes, 483 temporal chains, 5 `slow_affect` rows |
| 2 | `agent=` round trip vs source, `stable_payload` | Pass. Branch: 0 of 8 sections differ. Baseline: 2 of 8 (`temporal_chains`, `slow_affect`) |
| 3 | `agent=` round trip vs source, affect components | Pass. Branch: 0 of 9 differ. Baseline: 9 of 9 (`neuromodulators`, `affective_persistence`, `affective_background`, `affective_space`, `semantic_emotions`, `emotional_memory`, `emotional_expectations`, `emotional_regulation`, `stability_monitor`). `affect_state` is reprojected from `affective_space` on load by design and is checked in #4 |
| 4 | `agent=` load vs explicit load | Pass. Branch: 0 sections and 0 of 10 components differ, `affect_state` included. Saved files: all 15 component keys present and equal |
| 5 | Explicit load on the baseline | `stable_payload` 0 of 8 differ; `stability_monitor` differs (`history.baseline_buffer` empty after load). Branch: 0. Fixed by the two added restore attributes |
| 6 | Shared neuromodulators | Pass. Branch: `sleep_manager.neuromodulators is agent.neuromodulators` after both loads. Baseline: `False` after the explicit load (the object was replaced with a copy) |
| 7 | Explicit argument wins | Pass. `affective_space=` passed with `agent=`: the file holds the explicit object; on load the explicit target gets the data (stress `0.75`) and the agent's own `affective_space` is unchanged |
| 8 | Callers | `src/gui.py` and Tamagochi pass every component: unchanged. Virtual company passes a subset with `agent=`: now saves and restores the rest; its suite passes |

New test on the baseline `storage.py`: 5 failed, 2 passed (training precondition and explicit-wins pass). On the branch: 7 passed, three runs in a row.

```
python -m pytest -q tests/test_issue_87_save_agent_components.py
```

`7 passed in 1.30s`

```
python -m pytest -q tests
```

Branch: `958 passed, 4 skipped, 1 warning in 564.90s`. Baseline `89c10a0`: `951 passed, 4 skipped, 1 warning in 511.24s`.

```
python -m pytest -q "Demo/Virtual company/tests"
python -m pytest -q "Demo/Tamagochi Chinchilla/tests"
```

`955 passed, 1 skipped, 10 warnings in 224.15s`; `27 passed, 14 warnings in 1.04s`. The Tamagochi run rewrites the tracked `Demo/Tamagochi Chinchilla/saves/memory.json` and `nowa_state.json`; they were restored with `git checkout` and are not part of this change.

## Not run

- `Demo/Colony chinchillas/tests` and the full `python -m pytest -q`: pygame has no build for Python 3.14 on this machine. Colony does not call `save_agent` / `load_agent`.
- `Demo/Warriner Validation`: separate requirements, does not use the storage API.

## Defects

None.

## Questions

`emotional_regulation.last_inputs` is not restored by `EmotionalRegulationLayer.from_dict` (`last_time_delta` reads back as `1.0`). Those fields are written every step and read by nothing, so it is not filed; the test leaves them out of the comparison.

## Release readiness

Ready on this checklist. CI was not awaited.
