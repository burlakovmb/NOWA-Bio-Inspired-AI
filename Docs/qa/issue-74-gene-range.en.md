# QA issue #74 — `af_baseline_adapt_rate` range

Branch: `team/issue-74-gene-range`. HEAD at run time: `79cee90`. PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/81
Russian: [issue-74-gene-range.ru.md](issue-74-gene-range.ru.md).

Product code was not changed in this pass. No new PR was opened and nothing was merged. CI was not awaited. The full pytest suite was not run.

Machine: Python 3.12.3, pytest 9.2.0. Probes used `PYTHONPATH=src`.

## Verdict

**PASS** (`79cee90`).

`af_baseline_adapt_rate` is [1/86400, 1/5400], default 1/21600 equals `affective_space.DEFAULT_BASELINE_ADAPT_RATE`. `GeneDescriptor` is valid. random, mutate (including `sigma_scale` above the cap of 5) and crossover `arithmetic` / `uniform` / `sbx` keep τ inside 1.5–24 h. Legacy 0.002 through `GenomeVector.from_dict` and through `AgentStorage.load_agent` (`.nowa`) clamps to max: one `RuntimeWarning`, no crash. An in-range value loads with no warning. A missing field falls back to the default, also with no warning. `storage` imports `GENE_REGISTRY` directly and does not cycle with `genome`. `AffectiveSpace.__post_init__` still clamps to [0, 0.2]. The `test_affective_space_save_load` change 0.015 → `1/(3*3600)` is justified. 300 s of `Agent.step` with no stressors leaves the stress baseline on the setpoint.

## Coverage

| # | Check | Result |
| --- | --- | --- |
| 1 | Range, default, `GeneDescriptor` | Pass. min `1.1574074074074073e-05`, max `0.00018518518518518518`, default `4.6296296296296294e-05` == `DEFAULT_BASELINE_ADAPT_RATE`. min < default < max, sigma > 0 |
| 2 | random / mutate / crossover and τ | Pass. Test: 1000 random, 200 mutate at scale 5 and 1, modes `sbx` and `arithmetic`. QA probe: same operators plus `uniform` and `sigma_scale=100`, 300 iterations, 0 violations |
| 3 | Legacy 0.002, fallback, in-range, import | Pass. `from_dict` and `load_agent`: 1 `RuntimeWarning`, value = max. `1/(3*3600)` → `9.259259259259259e-05` and max: 0 warnings. Key removed from `.nowa`: default, 0 warnings. Joint import succeeded; `genome.py` is stdlib only |
| 4 | clamp [0, 0.2] and the test edit | Pass. `affective_space.py` is outside the diff. Probe: 0.5 → 0.2, −0.1 → 0.0. 0.015 is above the new max, so the round-trip equality would fail; `1/(3*3600)` sits inside both the gene and [0, 0.2]. The legacy test still sees 0.002 in the file and max after load |
| 5 | 300 s, dt 0.25, live agent | Pass. `AgentFactory.spawn_random`, seed 74, 1200× `Agent.step([], reward=0, novelty=0, conflict=0, intensity=0, dt=0.25)`. rate `3.3656613124657915e-05` is inside the range. baseline = setpoint = 0, max \|Δ\| = 0, stress axis = 0. Cheap (20 steps 0.023 s, 1200 steps estimated 1.4 s) |
| 6 | `Demo/` and `Docs/` | Pass. `git diff --stat origin/main...HEAD`: `src/genome.py`, `src/storage.py`, `tests/test_affective_space_storage.py`, `tests/test_affective_time.py`, `tests/test_genome_vector.py` |
| 7 | Targeted tests and Demo grep | Pass. 62 passed, 26.09s, exit 0. `Demo/**/tests` has no matches for `_deserialize_genome` or `_genome_from_plain`, so no extra files were run. Both helpers in source call `GenomeVector.from_dict` |

```
python3 -m pytest -q --no-header -p no:warnings tests/test_genome_vector.py tests/test_agent_factory.py tests/test_affective_time.py tests/test_affective_space_storage.py tests/test_affective_core_phase4.py | tail -n 30
```

`62 passed in 26.09s`

## Defects

None.

## Recommendations

- The crossover test alternates `sbx` and `arithmetic` and does not call `uniform`. The clamp sits after the mode branch; the probe showed no violations.
- `test_fed_space_at_max_adapt_rate_keeps_stress_baseline_near_setpoint` starts at equilibrium (gap 0). That is enough for a no-stressor run: the live agent produced the same zero.

## Readiness

Checklist closed, ready for review. CI on PR #81 was not inspected.
