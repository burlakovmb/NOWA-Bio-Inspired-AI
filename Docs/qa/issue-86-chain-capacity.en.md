# QA issue #86 — finite capacity with forgetting for temporal chains and visit counts

Branch: `fix/issue-86-chain-capacity`. Baseline: `b8e73f9` (main). Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/86.
Russian: [issue-86-chain-capacity.ru.md](issue-86-chain-capacity.ru.md). Spec: [issue-86-chain-capacity.en.md](../specs/issue-86-chain-capacity.en.md).

Machine: Windows, Python 3.14.7, pytest 9.2.0, `NOWA_STRICT_LEARNING=1` from `tests/conftest.py`. Baseline runs used a clean checkout of `b8e73f9` with `tools/bench_issue_86.py` copied in. Before and after benches ran under the same conditions (the two benches of a pair in parallel).

## Verdict

**PASS.**

On the diverse stream the median decision stays at 6.0–6.5 ms from 2 000 to 12 000 decisions instead of growing to 14.2 ms, with at most 2 048 chains, at most 4 096 visit rows and a 2.8 MB save instead of 8.0 MB. Learning quality is unchanged on both learning benches, including the long one where pruning and fading act. A first version that faded every visit count lowered learning (0.772 → 0.722); the shipped rule fades only contexts not visited for 8 nights (0.770).

## Coverage

| # | Check | Result |
| --- | --- | --- |
| 1 | Weak, stale chain is pruned; reconfirmed and well-supported chains stay | Pass (unit tests) |
| 2 | Capacity evicts the weakest and least recent, deterministically | Pass |
| 3 | Night stamps survive `to_dict` / `from_dict`; a pre-#86 save is not pruned at the next night | Pass |
| 4 | Stale visit counts halve on schedule and drop at 0; counts of a context in use do not fade; the cap drops the smallest | Pass |
| 5 | Whole agent, 600 diverse decisions, 6 nights, strict learning: within a chain capacity of 60; `agent=` save/load keeps the night counter | Pass |
| 6 | Decision cost, memory, save size as the agent ages | Pass, table 1 |
| 7 | Learning quality, short (7 nights) and long (30 nights) | Pass, tables 2 and 3 |
| 8 | Full core suite | Pass, see below |

New test on the baseline: 9 failed (`ChainMemory` has no capacity or night counter). On the branch: 9 passed, three runs in a row.

## Table 1 — cost bench (`python tools/bench_issue_86.py cost`)

One agent, diverse stream of 7 features × 3 levels, sleep every 800 decisions, hippocampus 256.

| Decisions | Median ms before | after | Chains before | after | Visit rows before | after | Save KB before | after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 000 | 3.66 | 3.77 | 1 846 | 1 846 | 800 | 800 | 2 592 | 2 628 |
| 2 000 | 5.39 | 6.35 | 3 223 | 2 048 | 1 596 | 1 596 | 3 257 | 2 885 |
| 6 000 | 9.91 | 6.25 | 8 455 | 2 048 | 5 518 | 4 096 | 5 461 | 3 091 |
| 8 000 | 12.46 | 6.13 | 11 109 | 2 048 | 7 787 | 4 096 | 6 372 | 2 844 |
| 12 000 | 14.18 | 6.05 | 14 720 | 2 048 | 11 141 | 4 096 | 7 978 | 2 842 |

The early "after" point at 2 000 decisions is slower than "before" within noise of a parallel run; from there on the cost is flat.

## Table 2 — short learning bench (`python tools/bench_issue_86.py learning`)

12 seeds, 1 500 decisions, 7 nights. Evasive share in danger, mean of the last three blocks.

| | Mean | Median |
| --- | --- | --- |
| Before | 0.816 | 0.827 |
| After | 0.819 | 0.831 |

Per seed the difference is within ±0.025; 6 seeds identical. In 7 nights neither the capacity (about 1 000 chains per agent) nor staleness (8 nights) acts yet, so this run mainly shows that nothing else changed.

## Table 3 — long learning bench (`--learn-decisions 6000`), 30 nights

| Variant | Mean | Median | Per seed vs before |
| --- | --- | --- | --- |
| Before (`b8e73f9`) | 0.772 | 0.768 | — |
| First version: every visit count halved every 8 nights | 0.722 | 0.727 | worse on 11 of 12, median −0.044 |
| Ablation: visit fading off (`--no-visit-decay`), chain pruning on | 0.771 | 0.771 | 2 better, 4 worse, 6 equal |
| **Shipped: only contexts not visited for 8 nights fade** | **0.770** | **0.769** | 4 better, 3 worse, 5 equal, median 0.000 |

Halving the counts of contexts the agent keeps visiting raises their exploration bonus again (`basal_ganglia`, visit-count optimism) and pulls the agent off what it has learned. Chain pruning alone does not change learning.

## Suites

```
python -m pytest -q tests
```

Branch: `967 passed, 4 skipped, 1 warning in 356.89s`. Baseline `b8e73f9` collects 962 tests; the branch adds the 9 new ones. One earlier run of the suite stopped part-way while other pytest processes were running in the same folder; run alone it passed.

Virtual company and Tamagochi: Tamagochi `27 passed`, Virtual company `955 passed, 1 skipped` (the Tamagochi tests rewrite the tracked `Demo/Tamagochi Chinchilla/saves/*.json`; restored, not part of the change). Colony: not run (no pygame build for Python 3.14).
