# Issue #28 item 5 — one colony snapshot per tick through a zone adjacency matrix

Russian: [issue-28-zone-matrix.ru.md](issue-28-zone-matrix.ru.md)

Branch `fix/issue-28-zone-matrix`. Baseline: `6113250` (main).

Code (Colony demo only, `src/` untouched): `Demo/Colony chinchillas/src/sensor_system.py`, `zone_snapshot.py` (new), `colony_agent.py`, `simulation_runner.py`. Test: `Demo/Colony chinchillas/tests/test_issue_28_zone_matrix.py`. Bench: `tools/bench_issue_28_colony.py`. Results: [QA report](../qa/issue-28-zone-matrix.en.md).

---

## 1. Problem

In `SimulationRunner._tick_once` the animals stepped one after another in an order from the global `random.shuffle`. Each animal scanned the whole colony as it was at that moment, in five places: perception, alarm hearing, crowding at a bowl, the social buffer of an alarm, and lookup by id. Three consequences:

- what an animal perceived depended on whether a neighbour had already stepped in this tick (an alarm given early in the tick was heard by the later half of the colony at once and by the earlier half on the next tick);
- the turn order came from the module-level generator, not from the colony;
- the scans grew with the square of the colony size. They are a small part of a tick, which the NOWA core inside each animal dominates: the snapshot makes a tick of 60 animals about 9 % cheaper (QA report).

Besides that, the zone adjacency had three one-way links: `house → litter`, `shelf_lower → floor`, `mineral → floor`. One side saw the other, the other did not.

Accepted in the issue: a synchronous tick through a snapshot, demo only; contests for a resource settled by "who is already there", then dominance from experience, then seeded noise; the adjacency made symmetric.

---

## 2. Solution

### 2.1 Symmetric adjacency and the matrix A

`sensor_system.ADJACENT_ZONES` gets the reverse links: `floor` sees `shelf_lower` and `mineral`, `litter` sees `house`. Next to it:

- `ZONES` — the 16 zones, sorted; `ZONE_INDEX` — zone → row;
- `ADJACENCY` — matrix A, 16×16, `A[i][j] = 1` when zone j is zone i or a neighbour of it (the diagonal is 1);
- `NEIGHBOURS` — the same neighbours as sorted tuples. The movement code picks a random neighbour from them instead of from a set, whose order depends on `PYTHONHASHSEED` (issue #14); with a seed the walk is now the same in every process.

A different range (for example "sees farther from above") would be a separate matrix next to A; it is not part of this change.

### 2.2 The tick snapshot Z

`zone_snapshot.ZoneSnapshot` is built once per tick before anyone steps. For every animal it records the zone (Z: animal × zone), the public state, "eats now", and whether it is giving an alarm call with its event id; it groups the animals by zone and keeps an id → animal dict. `near(zone)` returns the animals in the zone and its neighbours: the zone's row of A applied to the groups, in colony order, cached per zone.

The runner hands the snapshot to every animal (`agent._zone_snapshot`) for the time of the steps and clears it afterwards, also on an exception. Without a snapshot (an animal stepped on its own, as in unit tests) the old scan of the colony is used, so the agent works outside the runner unchanged.

### 2.3 What reads the snapshot

| Place | Before | Now |
|---|---|---|
| `_perceive` | every animal, its state at this moment | the zone's row of A plus every known animal, with the state from the start of the tick |
| `_perceive_alarm_calls` | every animal, "calls now" | callers in the zone's row of A as of the start of the tick (`_audible_alarm_calls`) |
| `_alarm_social_buffer` | every animal, zone check | the zone's row of A (`_animals_near`) |
| `_bowl_crowd_conflict` | every animal, "eats in this bowl" | eaters in this bowl as of the start of the tick; the animal's own action as it is now |
| `_find_agent_by_id` | scan | the dict; a scan for one born during the tick |

The categories of perception (`contact`, `nearby`, `distant`, `unknown_nearby`) and what is updated in `KnownAgent` are the same as before. An alarm given during a tick is heard on the next tick by every neighbour alike. Building the snapshot asks every animal `_is_emitting_alarm()` once per tick, which also samples its stress for the alarm-rise window once per tick, for every animal.

### 2.4 Turn order and contests

`SimulationRunner._turn_order(snapshot)` sorts the animals by the key:

1. **already at the resource**: animals standing in a contested zone (`bowl_pellets`, `bowl_hay`, `waterer`, `wheel`, `dustbath`) go first;
2. **dominance**, higher first: the animal's dominance axis (`dominance_level`) plus the mean `dominance_felt` towards the known animals in the same zone. Both come from experience: the axis from the affective dynamics, `dominance_felt` from chases won and lost. There is no fixed rank;
3. **noise** from the colony's generator.

Resources are still taken in a step (the last food in a bowl, the wheel lock, the dust bath), so the first in the order gets them. The loser gets the events it got before: `wheel_blocked` / `dustbath_blocked` frustration, the "no food" impulse at an empty bowl. They feed experience as before.

### 2.5 The colony's generator

`SimulationRunner(seed=...)` creates `self._rng`; the swarm bridge gets its own generator seeded from it. Without a seed the colony's generator is seeded from the module-level `random`, so a caller that seeds only the module (as tests did with the old shuffle) still gets a repeatable run. The global `random.shuffle` is gone from the tick.

The NOWA core inside each animal still samples actions from the module-level `random` (issue #14, `src/`); that is outside this change. A repeatable run therefore seeds the module as well as the runner, as the bench and the tests do.

---

## 3. What stays as is

- `src/` (the core) — not touched.
- The agent's own step order, the reward, the needs, reproduction, the swarm.
- Save format: the snapshot is not saved.
- The GUI and the host.

---

## 4. Acceptance

- **Determinism per seed**: the same seed gives the same trajectory, stress included, in the same process and in two processes with different `PYTHONHASHSEED` (`test_same_seed_same_trajectory`, `test_seeded_run_repeats_in_other_processes`, the bench digest). The core reads the wall clock (affect decay in `src/affective_space.py` and others), so on a loaded machine two runs drift apart even on main; the tests and the bench (`--sim-clock`) tie `time.time()` to the simulated time. On main a run with the simulated clock still depends on `PYTHONHASHSEED`, because the walk picked neighbours from sets (§2.1).
- **Comparison with main** on N seeds by deaths, mean stress, food intake, reaction to a scare, and the length of the alarm cascade: `tools/bench_issue_28_colony.py` on both trees, results in the QA report. The colony has no predator, so the bench scares one awake animal every 60 s (a stress impulse of 0.8) and measures from that moment.
- Tests: symmetry and the matrix; a run repeated in another process; snapshot rows against a scan; an alarm given during a tick is heard on the next; a relayed alarm moves one zone per tick in either turn order; two colonies stepping in opposite orders see the same animals in the same zones; the turn order does not depend on the module-level generator; an animal at a contested resource steps first; the snapshot is cleared after the tick.
