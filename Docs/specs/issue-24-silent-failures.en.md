# Issue #24 — Silent failures: conception genome, mortality, population cap

Russian: [issue-24-silent-failures.ru.md](issue-24-silent-failures.ru.md)

Closes #24. PR #62. Related: #15 (broad exception handlers).

Touches the cognitive **core** (`src/mortality.py`, `src/swarm.py`) and the **Colony chinchillas** demo host (`colony_agent.py`, `simulation_runner.py`, `colony_swarm_bridge.py`). Implementation commit: `f80a28a`.

---

## 1. Problem

Three silent failure modes were confirmed by static code review (issue #24, audit commit `3c70385`):

| Failure | Symptom |
| --- | --- |
| **Birth without father in the living colony** | `_give_birth` looked up the father among living agents; if he had died, genome crossover was skipped and offspring had `genome is None`. |
| **Bare `except` on mortality update** | Any exception in `MortalitySystem.update` was swallowed; the agent could stay alive indefinitely. |
| **Non-transactional `add_agent`** | After `self.agents.append(...)`, a failed swarm `add_agent` led the runner fallback to append again → duplicates only in the colony list, not in the swarm, invisible to mortality cleanup. |

---

## 2. Decision and rationale

**Decision:** Fix all three paths with explicit logging, a conception-time father genome snapshot, narrowed exception handling, and swarm-first admission.

**Rationale:** Reproduction and mortality must remain observable and consistent with evolution semantics (inheritance even when the father dies before parturition). Population cap `MAX_POPULATION_SIZE = 256` must be enforced before any slot or colony-list entry is published.

---

## 3. Behaviour

### 3.1 Conception snapshot and birth recombination

On pregnancy start (`_start_pregnancy` → `_capture_conception_genome`):

- Mother stores an independent copy of the father’s genome in `_conception_father_genome` (via `_copy_genome`), plus `_conception_father_id`, `_conception_father_name`, `_conception_father_generation`.
- The snapshot is not the live `father.genome` object; mutating or removing the father’s genome later does not erase the snapshot.

At birth (`_inherit_nowa_from` → `_father_genome_for_birth`):

- Paternal alleles for crossover prefer `_conception_father_genome`; only if the snapshot is missing does the code use the living father’s `genome`.
- **Generation** of the child: `max(mother.generation, father_generation) + 1`, where `father_generation` comes from the living father or from `_conception_father_generation` on the snapshot path.
- **Phenotype / scalar inheritance** (energy, social drive, affective decay, etc.) still reads the **living** father when present; a dead father contributes only via the genome snapshot.
- After `_give_birth`, `_clear_conception_record` resets snapshot fields.

**Logging / outcomes:**

| Condition | Result |
| --- | --- |
| Both mother genome and paternal genome (snapshot or live) available | Crossover + mutate; `genome_inheritance_meta["mode"] == "recombined"` |
| Crossover / apply raises | Warning `genome recombination failed for offspring of …` |
| Missing mother and/or paternal genome | `offspring.genome is None`; warning `offspring of … born without a recombined genome (mother_genome=…, father_genome=…, father_id=…)` |

### 3.2 Mortality: narrowed exceptions and lethal fallback

**Core** (`MortalitySystem`):

- New `apply_if_already_lethal(energy, wakefulness, lived_steps, biological_age_s)` — evaluates `_lethal_cause` without advancing senescence (bookkeeping failure must not erase an already lethal state).
- `_lethal_cause` unifies: `exhaustion` (energy ≤ critical), `sleep_deprivation` (wakefulness ≥ critical), `old_age` (steps or `max_lifespan_age_s`), `senescence` (vitality ≤ 0).

**Swarm** (`SwarmEnvironment._update_agent_vitality`) and **colony** (`ChinchillaAgent._apply_mortality`):

- `mortality.update(...)` wrapped in `except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError)` with warning `mortality update failed for agent …; death check continues: …`.
- Then call `apply_if_already_lethal` with the same energy / wakefulness / steps / age inputs.
- Colony path: unreadable energy falls back to `_energy_override` or **1.0**; unreadable wakefulness → **0.0**.

### 3.3 Transactional population admission

**Swarm** (`SwarmEnvironment.add_agent`):

- Check `len(self._slots) >= MAX_POPULATION_SIZE` **before** creating a slot.
- Run placement (`_find_free_position`); on failure, raise **before** any slot exists.

**Runner** (`SimulationRunner.add_agent`):

- Call `self.swarm.add_agent(agent)` first; append to `self.agents` only on success.
- Removed the duplicate append fallback on swarm failure.

**Spawning** (`_spawn_pending_offspring`):

- Each offspring goes through `add_agent`; on `ValueError` / `RuntimeError`, warning `offspring … was not admitted to the colony: …`.
- `births_this_step` and `total_births` increment only for admitted agents; a child rejected at the cap is discarded (not queued).

---

## 4. Verification

**Issue regressions**

| Suite | File | Focus |
| --- | --- | --- |
| Core swarm | `tests/test_issue24_silent_failures.py` | Cap before publish; placement rollback; mortality exception + lethal removal; fed agent not killed on transient update error |
| Colony host | `Demo/Colony chinchillas/tests/test_issue24_silent_failures.py` | Dead father + snapshot crossover; birth without genomes logged; mortality exception paths; cap / placement duplicates; spawn at cap |

**Reported test runs (senior dev, commit `f80a28a`):**

| Scope | Result |
| --- | --- |
| Touched modules / issue regressions | **73 passed** |
| Full repository | **1148 passed**, **5 skipped** |

---

## 5. Consequences

- Offspring of fathers who die during gestation receive a recombined genome when the conception snapshot exists.
- Mortality bookkeeping errors are visible in logs; agents already in a lethal state can still die via `apply_if_already_lethal`.
- Colony list and swarm slot sets stay aligned at the population cap; birth counters match admitted agents only.
- At exactly `MAX_POPULATION_SIZE`, newborns are dropped with a log line rather than duplicated or partially admitted.

---

## 6. Open points

| Topic | Notes |
| --- | --- |
| **Colony save/load** | `ColonyStorage` does not persist `genome` or `_conception_father_genome` — not addressed in this fix. |
| **Offspring at cap (256)** | Current behaviour: reject and discard. Product choice: keep waiting for a slot vs hard delete. |
| **`reproductive_system.update` / `register_reproduction`** | Broad `except Exception: pass` around `register_reproduction` in `_give_birth` unchanged (see #15). |
