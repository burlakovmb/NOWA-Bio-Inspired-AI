# Issue #74 — `af_baseline_adapt_rate` gene range

Russian: [issue-74-gene-range.ru.md](issue-74-gene-range.ru.md)

PR #81 on branch `team/issue-74-gene-range`. Code: `src/genome.py`, `src/storage.py`.

---

## Problem

Gene bounds were `[0, 0.01]` per simulated second. Uniform random sampling gave a **median τ ≈ 200 s** toward the lived axis — far too fast for allostatic baseline drift, which should operate on **hour** scales (see issue #54 simulated-second model).

## Biological rationale

Chronic stress and allostatic load in the affective core should shift `baseline` over hours (default τ ≈ 6 h), not minutes. Evolution and mutation must explore only biologically plausible adaptation speeds (about 1.5–24 h for the primary adapt rate).

## New behaviour

| Item | Value |
| --- | --- |
| Gene min / max | `1/86400` … `1/5400` (τ ≈ 24 h … 1.5 h) |
| Default | `1/21600` unchanged (τ ≈ 6 h) |
| Sigma | `0.5/21600` unchanged |
| After random / mutate / crossover | Values clamped to gene bounds; τ stays in 1.5–24 h |

`AffectiveSpace` constructed directly (tests) still clamps `baseline_adapt_rate` to `[0, 0.2]` in `__post_init__` — unchanged.

## Legacy saves and genomes

Values outside the gene range (e.g. pre-#54 rate `0.002` in `.nowa` or plain genome dicts) load via `GenomeVector.from_dict` and `AgentStorage.load_agent`: **one `RuntimeWarning`**, value clamped to `[min, max]` (e.g. `0.002` → `1/5400`). In-range values and missing keys (registry default) load without warning. This supersedes issue #54’s “read 0.002 as-is (τ ≈ 8 min)” policy for loads after #74.

## QA

Independent verification: [issue-74-gene-range.en.md](../qa/issue-74-gene-range.en.md) — **PASS**.