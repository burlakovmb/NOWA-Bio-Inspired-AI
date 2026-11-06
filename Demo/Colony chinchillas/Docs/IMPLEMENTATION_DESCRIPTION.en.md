# Chinchilla Colony: Implemented State

Russian version: [IMPLEMENTATION_DESCRIPTION.ru.md](IMPLEMENTATION_DESCRIPTION.ru.md)

This text records the implemented composition of the platform. It is aligned with the code in `Demo/Colony chinchillas/src`.

### 1. Individual

`ChinchillaAgent` is built on the NOWA agent and includes projections of `affective_space`, initial memory and intentions from a behaviour profile, social offers and relationship accounting, a reproductive cycle (`heat_cycle`, pregnancy, creation of offspring), and mortality through `MortalitySystem`.

The homeostatic layer introduces the needs `hunger` and `thirst` and the context events `hunger_high`, `hunger_critical`, `thirst_high`, `thirst_critical`, `wakefulness_high`, and `wakefulness_critical`. The gate `_apply_homeostatic_action_policy` forces urgent actions under critical need, blocks biologically inappropriate actions, and selects the most urgent need among sleep, eating, and drinking.

Movement follows the shortest transition on `ADJACENT_ZONES`. Actions other than sleep use unsticking logic. The wheel has a single owner through shared resources, a continuous-run limit `WHEEL_RUN_MAX_CONTINUOUS_S`, and a fallback movement when the wheel is occupied.

### 2. Population tick

`SimulationRunner.tick(dt)` performs: swarm synchronisation and signal update; shuffled calls of `agent.sim_step(dt)`; mortality checks and removal; reproduction checks and appearance of pending offspring; ecology update and periodic refill.

Deaths are appended to the runner memory and to the journal `logs/deaths.jsonl`. Each tick updates `births_this_step`, `deaths_this_step`, `total_births`, and `total_deaths`.

Refill is set by `REFILL_DAY_S` (600 s) and restores `food_pellets`, `hay`, and `water` to 1.0.

### 3. Swarm, interface, persistence, observer

`ColonySwarmBridge` synchronises zones with three-dimensional coordinates and occupancy offsets, carries social signals through `SwarmEnvironment`, checks pairs against a compatibility threshold when a factory is present, and updates the ecological share.

Interface: `src/gui.py` is the canonical launch; `src/colony_gui/app.py` is the pygame loop; `src/colony_gui/colony_gui.py` is the snapshot read-model. Display names are brought to the form with a sex suffix. The cage scene uses a background cache. Visual exclusivity of the wheel is aligned with the runtime lock. Sprite movement is smoothed between simulation ticks. Action sound is controlled by the key `M`. Mutual `mount_display` is accompanied by an overlay. A consolidated statistics panel is placed under the cage frame and shows time, abundance, mean age, mature females and males, females in estrus, pregnancy, births and deaths, social pairs, and bars for stress, energy, cohesion, extinction risk, and the levels of food, hay, and water. Panel text surfaces are cached.

`ColonyStorage` persists runner fields, shared resources together with locks, individual identity and state, including affect, reproduction, and knowledge, and nested pending-offspring state.

`ColonyPopulationObserver` follows `SPEC_ColonyPopulationObserver.md`: an immutable `ColonySnapshot`, scheduled and forced observation, trend and abundance peak, extinction risk and cohesion, export, and a history bound `MAX_HISTORY_LENGTH`. The observer remains passive. `ColonyGUI.get_render_state()` includes `population_stats`.

### 4. Behaviour profile and parameters

The profile is loaded by directory priority: `Demo/Colony chinchillas/datasets`, `Demo/Colony chinchillas/Datasets`, then the repository-root `datasets`. It contains base abilities, unconditioned reflexes, and homeostatic habits.

From `src/config_colony.py`: `MATURITY_AGE_S = 900.0`, `GESTATION_S = 300.0`, `HEAT_CYCLE_LENGTH_S = 600.0`, `ESTRUS_DURATION_S = 180.0`, `REFILL_DAY_S = 600.0`, `COLONY_MAX_LIFESPAN_AGE_S = 13500.0` (15 × maturity), `COLONY_MAX_LIFESPAN_STEPS = 20000` (snapshots and health-index normalisation only). Each `ChinchillaAgent` sets `MortalitySystem.max_lifespan_age_s` to `COLONY_MAX_LIFESPAN_AGE_S * genome.genes.get("lt_max_lifespan_factor", 1.0)` and passes `biological_age_s=self.age` into `MortalitySystem.update`. Death arises from physiology (`exhaustion`, `sleep_deprivation`) and from ageing dynamics (`old_age` at the individual age cap, `senescence`).

### 5. Limits on the interpretation of a run

The interface is not a source of decisions. At low remaining abundance, reproductive windows narrow. Successful mating requires male initiation and the availability of a female in estrus within the perception radius (the same zone or an adjacent one). High stress, high cortisol, and advanced age reduce effective reproductive opportunities before a senescent outcome. If an estrus window is spent on a low-contact route, mating probability falls while abundance remains positive.

Launch and verification commands are given in [COLONY_SPEC.en.md](COLONY_SPEC.en.md).
