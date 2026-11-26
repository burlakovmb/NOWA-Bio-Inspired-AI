# QA issue #28 — bounded failure log and one death-registry write per tick

Branch: `fix/issue-28-logs-and-death-registry`. Baseline: `0578c84` (main). Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/28.
Russian: [issue-28-logs-and-death-registry.ru.md](issue-28-logs-and-death-registry.ru.md). Spec: [issue-28-logs-and-death-registry.en.md](../specs/issue-28-logs-and-death-registry.en.md).

Machine: Windows. Core, Virtual company and Tamagochi on Python 3.14.7; Colony on Python 3.12 (pygame has no build for 3.14). pytest 9.2.0, `NOWA_STRICT_LEARNING=1` from `tests/conftest.py`. Baseline runs used a clean checkout of `0578c84` with `tools/bench_issue_28.py` copied in.

## Verdict

**PASS.**

`failure_log` keeps the latest 256 entries. The deaths of a tick write the registry once instead of once per death; memorials, journal lines and the final registry file are the same as before. With 400 memorials in the registry and 48 animals, a tick with 4 deaths takes 23 ms instead of 87 ms, with 8 deaths 24 ms instead of 157 ms; a single death costs the same.

## Coverage

| # | Check | Result |
| --- | --- | --- |
| 1 | `failure_log` keeps the latest `FAILURE_LOG_RETAIN` entries in order; a short log is whole | Pass |
| 2 | Restoring a save with a longer log keeps its tail | Pass |
| 3 | Four deaths in one tick, three in one generation: generation indexes equal the one-by-one rebuild (`g1-b` 2, `g1-d` 3, `g2-a` 1, `g1-a` 1) | Pass |
| 4 | Registry written once per tick; the journal lists the deaths in order | Pass |
| 5 | Single-death path (`_handle_agent_death`) unchanged; an id listed twice counts twice and registers once, as before | Pass |
| 6 | Cost of recording the deaths of one tick | Pass, table below |
| 7 | Core, Colony, Virtual company, Tamagochi suites | Pass, see below |

New tests on the baseline fail: `FAILURE_LOG_RETAIN` and `_handle_agent_deaths` do not exist there.

## Bench (`python tools/bench_issue_28.py`)

48 animals, a registry already holding 400 memorials and saving to a temporary folder; each tick kills N animals and records them as `SimulationRunner.tick` does, then refills the population. Median of 30 ticks (8 deaths: 5 ticks; the bench records deaths without the swarm's mortality step, so the swarm keeps counting the dead and longer runs reach its population limit of 256). The registry is filled in memory before timing, the same way on both trees.

| Deaths per tick | Before, ms | After, ms | Registry writes per tick, before / after |
| --- | --- | --- | --- |
| 1 | 19.7 | 19.1 | 1 / 1 |
| 4 | 87.1 | 23.0 | 4 / 1 |
| 8 | 157.1 | 23.8 | 8 / 1 |

Almost all of the time is the registry JSON write (`json.dump` of every memorial); the map rebuild is small at this size. A first version of the bench filled the registry through 400 saves on the baseline (its `register_death` cannot skip the write) and made the baseline's later writes about twice as slow; the fill is now done in memory on both trees.

## Suites

| Suite | Branch | Baseline `0578c84` |
| --- | --- | --- |
| `python -m pytest -q tests` | `973 passed, 4 skipped` | 970 + the 3 new tests |
| Colony (`Demo/Colony chinchillas/tests`, Python 3.12) | `306 passed` | `302 passed` (+ the 4 new tests) |
| Virtual company | `955 passed, 1 skipped` | |
| Tamagochi | `27 passed` | |

The Tamagochi tests rewrite the tracked `Demo/Tamagochi Chinchilla/saves/*.json`; restored, not part of the change. The colony tests leave the tree clean.
