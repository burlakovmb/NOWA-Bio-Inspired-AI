# QA — issue #28 item 5: one colony snapshot per tick through a zone adjacency matrix

Russian: [issue-28-zone-matrix.ru.md](issue-28-zone-matrix.ru.md)

Spec: [issue-28-zone-matrix.en.md](../specs/issue-28-zone-matrix.en.md). Branch `fix/issue-28-zone-matrix`, baseline `c9db269` (main). Python 3.12, Windows 11, i7-12700H.

---

## 1. Tests

| Suite | Result |
|---|---|
| `Demo/Colony chinchillas/tests` | 316 passed (306 before + 10 new) |
| `tests` (core, Python 3.14) | 970 passed, 4 skipped (same as main) |

New tests in `Demo/Colony chinchillas/tests/test_issue_28_zone_matrix.py`:

| Test | Checks |
|---|---|
| `test_adjacency_is_symmetric_and_matches_the_matrix` | every link has its reverse; A has 1 on the diagonal and matches `ADJACENT_ZONES`; `NEIGHBOURS` are sorted |
| `test_snapshot_rows_match_a_scan_of_the_colony` | `near(zone)` equals a scan of the colony for all 16 zones |
| `test_an_alarm_given_during_a_tick_is_heard_on_the_next` | a call that opens after the snapshot is not heard in this tick, is heard in the next |
| `test_alarm_moves_one_zone_per_tick_whatever_the_turn_order` | door – bars – litter: the listener hears the relay in tick 2 in both orders (without the snapshot: tick 1 or tick 2 depending on the order) |
| `test_perception_does_not_depend_on_turn_order` | two identical colonies stepping in opposite orders see the same animals in the same zones (without the snapshot: different for 8 of 8 animals) |
| `test_turn_order_uses_the_colony_generator_not_the_module_one` | the order does not change when the module-level `random` is reseeded |
| `test_animal_at_a_contested_resource_steps_first` | the animal at the bowl steps first |
| `test_same_seed_same_trajectory` | same seed, same process: identical zones, actions and stress for 150 ticks |
| `test_seeded_run_repeats_in_other_processes` | same seed, `PYTHONHASHSEED` 0 and 7: the same digest, stress included |
| `test_snapshot_is_cleared_after_the_tick` | no animal keeps the snapshot after a tick |

The determinism tests tie `time.time()` to the simulated time. The core reads the wall clock (by design, issue #14), and on a loaded machine two runs with the same seed drift apart in actions, not only in the last digits of stress; the old in-process comparison with a tolerance failed this way while the bench ran in parallel.

---

## 2. Determinism per seed

`tools/bench_issue_28_colony.py --sim-clock`, 10 animals, digest of every animal's zone and action on every tick.

| Tree | `PYTHONHASHSEED=0` | `PYTHONHASHSEED=1` / `7` |
|---|---|---|
| main, seed 4, 1.5 min | `ce7f62b31013ea85` | `f46f1a9930fbeca4` — differs |
| branch, seed 4, 1.5 min | `76298c84838e5e9d` | `76298c84838e5e9d` — same |
| branch, seeds 1–3, 5 min | `5a8227ed…`, `5a0cefc3…`, `183d4de9…` | identical for all three |

On main a run with a frozen clock still depends on the hash seed: the walk picked neighbours from sets. Without `--sim-clock` both trees differ between two runs of the same seed.

---

## 3. Colony dynamics, main vs branch

`--sim-clock --seeds 12 --animals 10 --minutes 15`, the same seeds on both trees. The colony has no predator (PR #34: fear comes from a neighbour's alarm call), so every 60 s one awake animal, chosen by the seed, is scared with a stress impulse of 0.8; 14 scares per run.

| Metric (mean over 12 seeds) | main | branch |
|---|---|---|
| Deaths, total | 1 | 0 |
| Births | 0 | 0 |
| Mean stress | 0.442 ± 0.191 | 0.434 ± 0.195 |
| Food intake (drop of the bowls) | 0.391 ± 0.012 | 0.395 ± 0.009 |
| Scares heard by another animal | 59.5 % | 60.7 % |
| Reaction: first other animal hears the call | 1 tick (0.1 s) | 1 tick (0.1 s) |
| Reaction: a neighbour of the scared animal hides or flees | 1 tick; 167 of 168 scares | 1 tick; 168 of 168 |
| Alarm cascade: other animals calling within 20 s | 0.042 | 0.047 |

Per run the trajectories diverge, so a seed-by-seed pairing is not meaningful; the distributions are compared. They match. The reaction metrics have the resolution of one tick and are one tick on both trees: a direct call is heard at once in both. The snapshot changes only a relayed call (one zone per tick, §1), and relays are rare (cascade ≈ 0.05).

### 3.1 Two stress regimes (also on main)

The runs split into calm and tense ones, equally on both trees:

| | main | branch |
|---|---|---|
| Tense runs (mean stress > 0.5) | 5 of 12, stress 0.666, scares heard 8 % | 5 of 12, stress 0.664, scares heard 11 % |
| Calm runs | 7 of 12, stress 0.281, scares heard 96 % | 7 of 12, stress 0.270, scares heard 96 % |

This is not caused by this change; it is reported in a separate comment. In short (seed 3): without scares the colony stays at 0.14–0.21; with them, two scares lift the whole colony to 0.66–0.75 by minute 3 and it stays there, mostly hiding. A fearful tone (stress > 0.6) of a known neighbour in the same zone adds conflict (`FEAR_CONTAGION_CONFLICT`, PR #84), which keeps the stress above 0.6. With that constant set to 0 the same scared run returns to 0.24 by minute 6.

---

## 4. Tick cost

Median of 60 ticks after 20 warm-up ticks, `--sim-clock`, one process at a time.

| Animals | main | branch |
|---|---|---|
| 10 | 19.8 ms | 18.2 ms |
| 30 | 69.0 ms | 66.9 ms |
| 60 | 166.6 ms | 152.2 ms (−9 %) |

The NOWA core inside each animal takes most of a tick; the scans the snapshot replaces were a small part of it.

---

## 5. Not covered

- Social offers are still resolved in the initiator's step: a target can get to know the initiator within the same tick, so "unknown_nearby" vs "nearby" can still depend on the order (the zones do not). Issue #25 covers offers.
- Newborn ids (uuid4) and host-side social timestamps (`time.time()`) from issue #14 are not part of this change.
- The bench runs 15 simulated minutes; reproduction and old age are outside that window.

---

## 6. How to repeat

```
cd "Demo/Colony chinchillas" && python -m pytest -q tests
python -m pytest -q tests
python tools/bench_issue_28_colony.py --sim-clock --seeds 12 --animals 10 --minutes 15 --json out.json
```

For main, check out `6113250` into a separate worktree and run the same bench file there (it detects whether the runner takes `seed`).
