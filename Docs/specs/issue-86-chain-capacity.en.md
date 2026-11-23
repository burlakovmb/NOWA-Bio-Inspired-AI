# Issue #86 — finite capacity with forgetting for temporal chains and visit counts

Russian: [issue-86-chain-capacity.ru.md](issue-86-chain-capacity.ru.md)

Branch `fix/issue-86-chain-capacity`. Baseline: `b8e73f9` (main).

Code: `src/temporal_chains.py`, `src/sleep.py`. Test: `tests/test_issue_86_chain_capacity.py`. Bench: `tools/bench_issue_86.py`.

---

## 1. Problem

With a fixed hippocampus capacity the cost of a decision still grows for the whole life of an agent:

- `ChainMemory.chains` had no capacity, pruning or eviction. Sleep forms chains from every subsequence of the recent episodes in every cycle, and `match_bias` scans all of them on every decision.
- `Agent._action_visit_counts` (stable visit counts, one row per context and action) also only grew.

On the bench's diverse stream (§4) the median decision went from 3.7 ms at 1 000 decisions to 14.2 ms at 12 000, with 14 720 chains, 11 141 visit rows and an 8 MB save.

The author's direction in the issue: unbounded growth within one lifespan is not intended; prune weak chains during sleep, add a hard capacity as a safety net, and give visit counts a slow decay and a cap.

---

## 2. Solution

### 2.1 Recency in nights

Recency is counted in **nights**, not wall-clock seconds, so forgetting does not depend on how fast a host runs time. `ChainMemory.sleep_index` counts closed nights. Every chain records `last_seen_sleep`, the night in which sleep last formed it (new or again, in `add_or_update`). The wall-clock `created_at` / `last_updated` stamps are unchanged and still unused for structure.

### 2.2 End of night

`SleepManager.deep_sleep` calls the new `SleepManager._close_night()` once per night, after the cycles and inside `learning_allowed()`, because it rewrites stable memory. Its counters join the night's statistics: `chains_pruned`, `chains_evicted`, `chains_kept`, `visit_rows_dropped`.

### 2.3 Temporal chains: `ChainMemory.close_night()`

1. **Prune.** A chain is removed when it stayed weak (`usage_count < min_support`) and was not formed again for `stale_sleeps` nights. A chain formed again keeps its place; a well-supported chain is not pruned for staleness alone.
2. **Capacity.** If more than `capacity` chains remain, those with the least retention are evicted: `usage_count * recency_weight ** (nights since last formed)`, then least `stability`; the signature breaks ties, so the result is deterministic. With `recency_weight = 0.5` a chain formed tonight keeps its full support, so it is not evicted before an old, stronger chain that has not been formed for a few nights; `1.0` ranks by support alone.
3. `sleep_index` advances by one.

Defaults: `capacity = 2048`, `min_support = 6`, `stale_sleeps = 8`, `recency_weight = 0.5`. A sequence present in the recent episodes is formed once per cycle (three per night by default), so `min_support = 6` means "reinforced on about two nights or fewer". The capacity bounds the `match_bias` scan.

### 2.4 Visit counts

Two attributes on `SleepManager`:

- `visit_halving_sleeps = 8`: every 8th night the counts of contexts **not visited for the last 8 nights** are halved (integer division); a count that reaches 0 is removed. A context the agent stopped visiting slowly becomes novel again for the visit-count exploration bonus in `basal_ganglia`, and one-off contexts disappear. A context in use keeps its counts.
- `visit_capacity = 4096`: if more rows remain, the rows with the least retention go first: `count * visit_recency_weight ** (nights since the context was last visited)`, `visit_recency_weight = 0.5`; the key breaks ties. A place visited just before sleep keeps its full count and is not the first to go.

0 turns either one off.

The night a context was last visited is recorded when the waking visits move into the stable counts (`_transfer_labile_visits`), in `SleepManager._visit_context_night`. It is bookkeeping and is not saved: after a load every context counts as visited at the first night it is checked, so nothing fades early.

Why only stale contexts: the first version halved every count. On the long learning bench (§4, 30 nights) that lowered the learned share from 0.772 to 0.722 (worse on 11 of 12 seeds), because halving the counts of a context the agent keeps visiting raises its exploration bonus again and pulls it away from what it learned. With fading turned off the share stays at 0.771; with fading of stale contexts only it is 0.770. Details in the QA report.

### 2.5 Save and load

`ChainMemory.to_dict` also writes `sleep_index` and each chain's `last_seen_sleep`; `from_dict` reads them. A save made before this change has no night stamps: its chains are counted as seen at the loaded night, so the first night after loading an old save does not prune them all. `learning_guard.stable_payload` is unchanged (night stamps are bookkeeping, like the wall-clock stamps it already leaves out).

### 2.6 What stays as is

- `ChainMemory()` with no arguments, as `SleepManager` and the tests construct it, gets the defaults.
- `sleep_cycle()` called directly, without `deep_sleep` (the Tamagochi demo in one place, the Virtual company training loop), does not close a night: those paths form chains as before and do not forget them. `Agent.sleep()` always goes through `deep_sleep`.
- How chains are formed and how `match_bias` weighs them is unchanged.

---

## 3. Test

`tests/test_issue_86_chain_capacity.py`, 12 tests:

- a weak chain survives two stale nights and is pruned on the third; a chain formed again every night survives; a well-supported chain survives staleness;
- the capacity evicts the weakest; a chain formed tonight outlasts an old, stronger one; a context visited tonight outlasts an old, frequent one; `visit_recency_weight = 1.0` ranks by count alone;
- `to_dict` / `from_dict` keep the night stamps; a pre-#86 save is not pruned at the next night;
- counts of a stale context halve on schedule and drop at 0; counts of a context in use do not fade; the cap drops the smallest counts;
- an agent living through 600 diverse decisions and 6 nights under `NOWA_STRICT_LEARNING=1` stays within a chain capacity of 60, and an `agent=` save/load keeps its night counter.

On `b8e73f9` the tests fail: `ChainMemory` has no capacity or night counter.

---

## 4. Bench

`tools/bench_issue_86.py`, standard library only:

- `cost`: one agent, 8 actions, context of 7 features × 3 levels drawn uniformly each decision (a deliberately diverse stream), `dt = 1.5 s`, `sleep(cycles=3)` every 800 decisions, hippocampus 256, wake interval 1200 s. Per 1000 decisions: median and p90 decision time (step + commit, sleep excluded), chains, visit rows, saved agent size.
- `learning`: the #85 contingency task, 12 seeds, `sleep(cycles=3)` every 200; per seed the evasive share in danger, mean of the last three blocks. 1500 decisions (7 nights) by default; `--learn-decisions 6000` (30 nights) is long enough for pruning and fading to act. `--no-visit-decay` is the ablation without visit fading.

Results before and after are in the QA report.
