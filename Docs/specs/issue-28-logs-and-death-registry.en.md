# Issue #28 — bounded failure log and one death-registry write per tick

Russian: [issue-28-logs-and-death-registry.ru.md](issue-28-logs-and-death-registry.ru.md)

Branch `fix/issue-28-logs-and-death-registry`. Baseline: `0578c84` (main).

Code: `src/autonomous_organism.py`, `src/agent.py`, `Demo/Colony chinchillas/src/simulation_runner.py`, `Demo/Colony chinchillas/src/death_registry.py`. Tests: `tests/test_issue_28_failure_log.py`, `Demo/Colony chinchillas/tests/test_issue_28_death_batch.py`. Bench: `tools/bench_issue_28.py`.

This PR covers the parts of #28 that do not change behaviour. The O(n²) scans over the colony (perception, alarm checks, crowding, id lookups) are left for a separate change.

---

## 1. State of #28 at the baseline

| Item | At `0578c84` |
| --- | --- |
| `tick_history` appended every tick | Already bounded: `TICK_HISTORY_RETAIN = 1` (PR #55) |
| `failure_log` appended without bound | Still unbounded; this PR |
| Every death rebuilds the generation index map and rewrites the whole registry JSON | Still so; this PR |
| Invariant flags ignored | No longer: `_verify_invariants` records `invariant_violation` and re-raises `OrganismInvariantError` |
| Colony scans all agents per agent | Not in this PR |

---

## 2. Solution

### 2.1 `failure_log`

`FAILURE_LOG_RETAIN = 256`, next to `TICK_HISTORY_RETAIN`. `_record_failure` appends and then keeps the latest 256 entries (`_trim_failure_log`). `Agent.restore_autonomous_state` trims a restored log the same way, so an older save with a longer log comes back as its latest tail. The log is still exported under `failures`. Readers check for the presence of a recent failure mode, which the tail keeps.

### 2.2 Deaths of one tick

`SimulationRunner.tick` calls the new `_handle_agent_deaths(dead_ids)` instead of `_handle_agent_death` per id:

- the generation index map is built once for the tick; after each death the dead agent leaves the map and the positions after it in its generation move up by one, which is exactly what a rebuild without that agent gives;
- `DeathRegistry.register_death(..., autosave=False)` records each memorial, and the registry is written once at the end of the tick;
- the journal line per death (`_append_death_entry`, already append-only), the counters and the removal from `self.agents` are as before.

Memorials, journal lines and the final registry file are the same as handling the deaths one by one. `_handle_agent_death(agent_id)` stays and delegates to the batch. `register_death` keeps `autosave=True` by default, so other callers are unchanged.

---

## 3. Tests

- `tests/test_issue_28_failure_log.py` (3): the log keeps the latest `FAILURE_LOG_RETAIN` entries in order; a short log is kept whole; restoring a save with a longer log keeps its tail.
- `Demo/Colony chinchillas/tests/test_issue_28_death_batch.py` (4): four deaths in one tick, three of them in one generation, get the same generation indexes as the one-by-one rebuild; the registry is written once per tick and the journal lists the deaths in order; the single-death path is unchanged; an id listed twice counts twice and registers once, as before.

Colony tests need pygame; they ran on Python 3.12.
