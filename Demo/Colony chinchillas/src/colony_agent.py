"""Core colony agent with perception, social behavior and reproduction."""

from __future__ import annotations

import hashlib
import logging
import math
import random
import re
import sys
import time
import uuid
from pathlib import Path

ROOT_SRC_PATH = Path(__file__).resolve().parents[3] / "src"
if str(ROOT_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_SRC_PATH))

from agent import Agent
from agent_factory import AgentConfig, AgentFactory
from colony_behavior_profile import (
    ColonyBehaviorProfile,
    UnconditionedReflex,
    load_colony_behavior_profile,
)
from cortex import CortexMemory
from genome import GenomeVector
from hippocampus import NOWAHippocampus
from intent_memory import IntentMemory, IntentTrace
from labile_layer import PlasticityConfig
from learning_guard import initializing
from mortality import MortalitySystem
from reproduction import ReproductiveSystem
from selector import ActionSelector
from sleep import SleepManager
from wakefulness import WakefulnessState

from agent_knowledge import (
    HearsayItem,
    InteractionEpisode,
    KnownAgent,
    PerceivedOther,
    PublicState,
)
from config_colony import (
    COLONY_MAX_LIFESPAN_AGE_S,
    COLONY_MAX_LIFESPAN_STEPS,
    GESTATION_S,
    JUVENILE_BLOCKED_OFFERS,
    MATURITY_AGE_S,
    NAME_POOL,
    OFFER_COOLDOWNS,
    OFFER_TIMEOUT_S,
    PHYSIOLOGY_AS_POLICY,
    RESOURCE_CONSUMPTION_MULTIPLIER,
    UNMET_HUNGER_ENERGY_PER_S,
    UNMET_SLEEP_ENERGY_PER_S,
    UNMET_THIRST_ENERGY_PER_S,
)
from heat_cycle import HeatCycle
from colony_reproduction_helpers import (
    choose_litter_size,
    resource_blocks_reproduction,
)
from sensor_system import ADJACENT_ZONES, is_same_or_adjacent
from shared_resources import SharedResources
from social_layer import PendingOffer
from social_offers import SOCIAL_OFFER_TYPES, SocialOffer, SocialResponse


COLONY_BEHAVIOR_PROFILE = load_colony_behavior_profile()
COLONY_ACTIONS = list(COLONY_BEHAVIOR_PROFILE.base_abilities)

SLEEP_WAKEFULNESS_THRESHOLD = 0.7
SLEEP_HYSTERESIS = 0.7
SLEEP_CRITICAL_THRESHOLD = 0.9
# Historical per-tick floor. Not applied: a fixed physiological slice on
# every tick made short steps restore energy and Process S faster than a
# long step covering the same simulation second. Recovery is
# ``dt * SLEEP_RECOVERY_DURATION_FACTOR``.
SLEEP_MIN_RECOVERY_DURATION_S = 30.0
SLEEP_RECOVERY_DURATION_FACTOR = 22.0
SLEEP_CONSOLIDATION_INTERVAL_S = 900.0
SLEEP_MAX_CONSOLIDATION_CYCLES_PER_TICK = 2
WAKEFULNESS_ACCUMULATION_FACTOR = 30.0
# UI speed 1 uses this step (colony_gui.app.SIM_BASE_STEP_S). A faster
# setting stretches one decision over a longer dt. The body still
# integrates in these slices, so rest and cost stay on the 1x clock.
COLONY_BODY_STEP_S = 1.0 / 12.0
# Neonatal energy matches EnergySystem's rested start (1.0). A kit does not
# inherit the parents' current balance: that is metabolic state, not an allele.
NEWBORN_ENERGY = 1.0
STUCK_MOVE_TIMEOUT_S = 10.0
MIN_ACTION_MOVE_INTERVAL_S = 1.25
RESOURCE_BLOCK_FEEDBACK_COOLDOWN_S = 4.0
WHEEL_RUN_MAX_CONTINUOUS_S = 18.0
HUNGER_NEED_THRESHOLD = 0.6
HUNGER_CRITICAL_THRESHOLD = 0.85
THIRST_NEED_THRESHOLD = 0.58
THIRST_CRITICAL_THRESHOLD = 0.82
# Eat and drink relieve the need before the unmet-need penalty starts.
# Below availability there is still no relief (the portion rule).
HUNGER_AVAILABILITY_THRESHOLD = 0.50
THIRST_AVAILABILITY_THRESHOLD = 0.48
HUNGER_ACCUMULATION_PER_S = 0.0035
THIRST_ACCUMULATION_PER_S = 0.0045
EAT_RELIEF = 0.48
DRINK_RELIEF = 0.62
MOUNT_DISPLAY_INITIATOR_MIN_AFFINITY = 0.22
MOUNT_DISPLAY_ACCEPT_MIN_AFFINITY = 0.18
MOUNT_DISPLAY_ESTRUS_MIN_VALUE = 0.35
MOUNT_DISPLAY_MIN_DRIVE_SCORE = 0.20

# Energy penalties when resources are missing (per metabolism tick ~1s)
RESOURCE_MISSING_ENERGY_PENALTY_PER_S = 0.02
WATER_MISSING_ENERGY_PENALTY_PER_S = 0.015

logger = logging.getLogger(__name__)


def colony_expected_wake_interval_s() -> float:
    """Mean simulation seconds awake between one sleep bout and the next.

    Sleep starts at ``SLEEP_WAKEFULNESS_THRESHOLD`` and waking resumes at
    that level times ``SLEEP_HYSTERESIS``. Each simulation second contributes
    ``WAKEFULNESS_ACCUMULATION_FACTOR`` physiological seconds, and
    physiological sleep pressure climbs at ``WakefulnessState.ACCUMULATION_RATE``.
    The value uses the same seconds ``sim_step`` passes as ``dt``.
    """
    span = SLEEP_WAKEFULNESS_THRESHOLD * (1.0 - SLEEP_HYSTERESIS)
    per_sim_second = WAKEFULNESS_ACCUMULATION_FACTOR * float(WakefulnessState.ACCUMULATION_RATE)
    if per_sim_second <= 0.0:
        return 3600.0
    return span / per_sim_second


def _host_dt(dt: float) -> float:
    """Game seconds for one tick. Never omitted, so the core clock does not use the wall."""
    try:
        elapsed = float(dt)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(elapsed) or elapsed < 0.0:
        return 0.0
    return elapsed


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _coerce_finite(value: object, default: float = 0.0) -> float:
    try:
        casted = float(value)  # host state is untyped
    except (TypeError, ValueError):
        return default
    if not math.isfinite(casted):
        return default
    return casted


def _copy_genome(genome: GenomeVector | None) -> GenomeVector | None:
    """Independent copy of a genome frozen at one moment."""
    if genome is None:
        return None
    genes = getattr(genome, "genes", None)
    if not isinstance(genes, dict) or not genes:
        return None
    try:
        return GenomeVector(
            genes={str(key): float(value) for key, value in genes.items()},
            generation=max(0, int(getattr(genome, "generation", 0) or 0)),
            lineage_id=str(getattr(genome, "lineage_id", "") or ""),
        )
    except (TypeError, ValueError) as exc:
        logger.warning("failed to snapshot genome: %s", exc)
        return None


def _father_genome_for_birth(mother: object, father: object | None) -> GenomeVector | None:
    """Alleles stored at conception, otherwise the living father's genome."""
    snapshot = getattr(mother, "_conception_father_genome", None)
    if snapshot is not None:
        return snapshot
    if father is None:
        return None
    return getattr(father, "genome", None)


def _colony_max_lifespan_age_s(genome: GenomeVector | None) -> float:
    """Old-age cap in sim-seconds. A missing genome keeps the colony default.

    ``lt_max_lifespan_factor`` is a plain multiplier (registry range 0.5..2.0).
    """
    factor = 1.0
    if genome is not None:
        factor = float(
            (getattr(genome, "genes", {}) or {}).get("lt_max_lifespan_factor", 1.0)
        )
    return float(COLONY_MAX_LIFESPAN_AGE_S) * factor


def colony_scripted_old_age_s(agent: object) -> float:
    """Simulated age that meets this animal's own old-age cap.

    Media scripts pass the result as ``biological_age_s``. They do not
    write it back onto ``agent.age``.
    """
    system = getattr(agent, "mortality_system", None)
    cap = getattr(system, "max_lifespan_age_s", None)
    if cap is None:
        cap = _colony_max_lifespan_age_s(getattr(agent, "genome", None))
    return max(float(getattr(agent, "age", 0.0)), float(cap))


class ChinchillaAgent(Agent):
    """Chinchilla entity with full NOWA cognitive stack and colony behaviors."""

    _name_index = 0
    _generation_name_counters: dict[int, int] = {}
    _formatted_name_pattern = re.compile(
        r"^G(?P<generation>[0-9]+)A(?P<index>[0-9]+)(?:S(?P<sex>[MFU]))?$"
    )

    def __init__(
        self,
        *,
        sex: str,
        name: str | None = None,
        agent_id: str | None = None,
        age: float = 0.0,
        generation: int = 0,
        parents: tuple[str | None, str | None] = (None, None),
        colony: list["ChinchillaAgent"] | None = None,
        resources: SharedResources | None = None,
        is_mature: bool | None = None,
        position: str = "floor",
        rng: random.Random | None = None,
        rng_seed: int | None = None,
        physiology_as_policy: bool | None = None,
        hippocampus_capacity: int = 1024,
        cortex_capacity: int = 128,
        genome: GenomeVector | None = None,
    ) -> None:
        if sex not in {"M", "F"}:
            raise ValueError("sex must be M or F")

        self.behavior_profile: ColonyBehaviorProfile = load_colony_behavior_profile()
        self.base_abilities: tuple[str, ...] = self.behavior_profile.base_abilities
        hippocampus = NOWAHippocampus(
            max_experiences=max(1, int(hippocampus_capacity)),
            activation_similarity_threshold=0.6,
        )
        cortex = CortexMemory()
        try:
            setattr(cortex, "capacity", max(1, int(cortex_capacity)))
        except Exception:
            pass
        selector = ActionSelector(actions=list(self.base_abilities))
        intent_memory = IntentMemory()
        sleep_manager = SleepManager(hippocampus, cortex, intent_memory=intent_memory)

        super().__init__(
            hippocampus=hippocampus,
            cortex=cortex,
            selector=selector,
            sleep_manager=sleep_manager,
            intent_memory=intent_memory,
            rng_seed=rng_seed,
            plasticity_config=PlasticityConfig(
                expected_wake_interval_s=colony_expected_wake_interval_s(),
            ),
        )

        # Ensure neuromodulator baselines exist (guard against zeroing by factories/loaders)
        try:
            nm = getattr(self, "neuromodulators", None)
            if nm is None:
                try:
                    from neuromodulators import NeuromodulatorState

                    self.neuromodulators = NeuromodulatorState()
                except Exception:
                    pass
            else:
                try:
                    if float(getattr(nm, "dopamine", 0.0)) <= 1e-9:
                        nm.dopamine = float(getattr(nm, "BASELINE_DA", 0.1))
                    if float(getattr(nm, "serotonin", 0.0)) <= 1e-9:
                        nm.serotonin = float(getattr(nm, "BASELINE_HT", 0.1))
                    if hasattr(nm, "_clamp_all"):
                        nm._clamp_all()
                except Exception:
                    pass
        except Exception:
            pass

        self.sex: str = sex
        self.agent_id: str = agent_id or str(uuid.uuid4())
        self.name: str = name or self._next_generated_name(generation, sex)
        self.age: float = age
        self.generation: int = generation
        self.parents: tuple[str | None, str | None] = parents
        self.genome: GenomeVector | None = genome
        self.genome_inheritance_meta: dict[str, object] = {}
        self._observe_name_counter(self.name)
        if self.genome is not None:
            try:
                lineage_id = str(getattr(self.genome, "lineage_id", "") or "").strip()
                if not lineage_id:
                    # Seed founders with stable lineage labels so child lineage no longer collapses to "x".
                    self.genome = GenomeVector(
                        genes=dict(getattr(self.genome, "genes", {}) or {}),
                        generation=int(getattr(self.genome, "generation", self.generation)),
                        lineage_id=str(self.name).lower(),
                    )
                    lineage_id = str(getattr(self.genome, "lineage_id", "") or "").strip()
                self.genome_inheritance_meta = {
                    "mode": "founder",
                    "lineage_id": lineage_id,
                }
            except Exception:
                self.genome_inheritance_meta = {}

        self.colony: list[ChinchillaAgent] = colony or []
        self.resources: SharedResources | None = resources
        self.position: str = position

        self.knowledge: dict[str, KnownAgent] = {}
        self.perceived_others: list[PerceivedOther] = []

        self.is_mature: bool = (age >= MATURITY_AGE_S) if is_mature is None else is_mature
        self.heat_cycle: HeatCycle | None = HeatCycle() if sex == "F" and self.is_mature else None
        self.is_pregnant: bool = False
        self.gestation_timer: float = 0.0
        self.pending_offspring_list: list[ChinchillaAgent] = []
        self.own_offspring: list[str] = []
        self._current_mate_id: str | None = None
        self._conception_father_genome: GenomeVector | None = None
        self._conception_father_id: str | None = None
        self._conception_father_name: str = ""
        self._conception_father_generation: int = 0

        self.mortality_system: MortalitySystem = MortalitySystem(
            max_lifespan_steps=COLONY_MAX_LIFESPAN_STEPS,
            max_lifespan_age_s=_colony_max_lifespan_age_s(self.genome),
            senescence_start_fraction=0.75,
            senescence_vitality_loss_rate=0.00018,
            critical_energy_threshold=0.08,
        )
        self.reproductive_system: ReproductiveSystem = ReproductiveSystem(
            drive_threshold=0.55,
            drive_decay=0.006,
            drive_recovery_rate=0.075,
            cooldown_duration=36,
        )

        self.sim_time: float = 0.0
        self.current_action: str = "idle"
        self.is_sleeping: bool = False
        self.physiology_as_policy: bool = (
            bool(PHYSIOLOGY_AS_POLICY) if physiology_as_policy is None else bool(physiology_as_policy)
        )
        # Replaces the cognitive choice. None keeps the core. The ablation uses "rest".
        self.replaced_policy_action: str | None = None
        if rng is not None:
            self._rng = rng
        elif rng_seed is not None:
            self._rng = random.Random(int(rng_seed))
        else:
            self._rng = random.Random()
        self._food_source_preference: str = self._rng.choice(["food_pellets", "hay"])
        self.hunger: float = _clamp(0.2 + (self._rng.random() * 0.12), 0.0, 1.0)
        self.thirst: float = _clamp(0.18 + (self._rng.random() * 0.12), 0.0, 1.0)
        self.scent_signature: str = hashlib.sha1(self.agent_id.encode()).hexdigest()[:8]
        self._last_position_change_time: float = 0.0

        self.pending_offer: PendingOffer | None = None
        self._offer_cooldowns: dict[str, float] = {}
        self._resource_block_feedback_at: dict[str, float] = {}
        self._wheel_run_started_at: float | None = None
        self._exclusive_action_timer: float = 0.0
        self._metabolism_tick: float = 0.0
        self._body_step_carry: float = 0.0
        # Forced sleep continues only after a bout opened by real need
        # (Process S at onset). A voluntary nap must not trap the animal.
        self._sleep_entered_by_need: bool = False
        self._sleep_consolidation_accum_s: float = 0.0
        self.unconditioned_reflexes: tuple[UnconditionedReflex, ...] = (
            self.behavior_profile.unconditioned_reflexes
        )
        self._reflex_last_activation: dict[str, float] = {}
        self._seed_habit_bootstrap()

        self.frustration_events: list[str] = []
        self._last_social_was_positive: bool = False
        self._social_drive_override: float = 0.45
        self._energy_override: float = 1.0

        if genome is not None:
            try:
                with initializing():
                    AgentFactory(AgentConfig(actions=list(self.base_abilities)))._apply_genome_to_agent(
                        self, genome.to_agent_params()
                    )
            except Exception:
                pass

    @property
    def stress(self) -> float:
        return _clamp(float(self.affective_space.axes.get("stress", 0.0)), 0.0, 1.0)

    @property
    def arousal(self) -> float:
        return _clamp(float(self.affective_space.axes.get("arousal", 0.0)), 0.0, 1.0)

    @property
    def valence(self) -> float:
        return _clamp(float(self.affective_space.axes.get("valence", 0.0)), -1.0, 1.0)

    @property
    def dominance_level(self) -> float:
        return _clamp(float(self.affective_space.axes.get("dominance", 0.0)), 0.0, 1.0)

    @property
    def curiosity_level(self) -> float:
        return _clamp(float(self.affective_space.axes.get("curiosity", 0.0)), 0.0, 1.0)

    @property
    def attachment_level(self) -> float:
        return _clamp(float(self.affective_space.axes.get("attachment", 0.0)), 0.0, 1.0)

    @property
    def trust_level(self) -> float:
        return _clamp(float(self.affective_space.axes.get("trust", 0.0)), 0.0, 1.0)

    @property
    def boredom(self) -> float:
        return _clamp(1.0 - self.curiosity_level, 0.0, 1.0)

    @property
    def energy(self) -> float:
        runtime = getattr(self, "autonomous_runtime", None)
        if runtime is not None and hasattr(runtime, "energy_system"):
            return float(getattr(runtime.energy_system, "energy", self._energy_override))
        return float(self._energy_override)

    @energy.setter
    def energy(self, value: float) -> None:
        casted = _clamp(float(value), 0.0, 1.0)
        runtime = getattr(self, "autonomous_runtime", None)
        if runtime is not None and hasattr(runtime, "energy_system"):
            try:
                runtime.energy_system.energy = casted
            except Exception:
                pass
        self._energy_override = casted

    @property
    def social_drive(self) -> float:
        runtime = getattr(self, "autonomous_runtime", None)
        if runtime is not None and hasattr(runtime, "drive_system"):
            return float(runtime.drive_system.drives.get("social_drive", self._social_drive_override))
        return float(self._social_drive_override)

    @social_drive.setter
    def social_drive(self, value: float) -> None:
        casted = _clamp(float(value), 0.0, 1.0)
        runtime = getattr(self, "autonomous_runtime", None)
        if runtime is not None and hasattr(runtime, "drive_system"):
            try:
                runtime.drive_system.drives["social_drive"] = casted
            except Exception:
                pass
        self._social_drive_override = casted

    @classmethod
    def _next_name(cls) -> str:
        value = NAME_POOL[cls._name_index % len(NAME_POOL)]
        cls._name_index += 1
        return value

    @classmethod
    def _next_generated_name(cls, generation: int, sex: str) -> str:
        safe_generation = max(0, int(generation))
        next_index = cls._generation_name_counters.get(safe_generation, 0) + 1
        cls._generation_name_counters[safe_generation] = next_index
        normalized_sex = str(sex).upper()
        if normalized_sex not in {"M", "F"}:
            normalized_sex = "U"
        return f"G{safe_generation}A{next_index}S{normalized_sex}"

    @classmethod
    def _observe_name_counter(cls, name: str) -> None:
        matched = cls._formatted_name_pattern.match(str(name))
        if not matched:
            return
        generation = int(matched.group("generation"))
        index = int(matched.group("index"))
        cls._generation_name_counters[generation] = max(
            cls._generation_name_counters.get(generation, 0),
            index,
        )

    def _apply_affect_impulse(
        self,
        *,
        stress: float = 0.0,
        valence: float = 0.0,
        arousal: float = 0.0,
        attachment: float = 0.0,
        curiosity: float = 0.0,
        trust: float = 0.0,
        intensity: float = 0.5,
    ) -> None:
        """Apply affective impulse via NOWA AffectiveSpace."""
        try:
            scale = _clamp(float(intensity), 0.0, 2.0)
            inputs: dict[str, float] = {}
            if stress != 0.0:
                inputs["stress"] = _clamp(stress * scale, -1.0, 1.0)
            if valence != 0.0:
                inputs["valence"] = _clamp(valence * scale, -1.0, 1.0)
            if arousal != 0.0:
                inputs["arousal"] = _clamp(arousal * scale, -1.0, 1.0)
            if attachment != 0.0:
                inputs["attachment"] = _clamp(attachment * scale, -1.0, 1.0)
            if curiosity != 0.0:
                inputs["curiosity"] = _clamp(curiosity * scale, -1.0, 1.0)
            if trust != 0.0:
                inputs["trust"] = _clamp(trust * scale, -1.0, 1.0)
            if not inputs:
                return
            stress_signal = abs(inputs.get("stress", 0.0))
            self.affective_space.step(
                inputs=inputs,
                time_elapsed=1.0,
                wakefulness=self.wakefulness.wakefulness,
                uncertainty=stress_signal * 0.5,
                conflict=max(0.0, inputs.get("stress", 0.0)),
            )
        except Exception:
            pass

    def sim_step(self, dt: float) -> None:
        self.sim_time += dt
        self._tick_exclusive_action(dt)
        self._check_offer_timeout()
        # A need-bout yields once thirst or hunger enters the penalty band,
        # unless Process S itself is already in the critical band. The animal
        # has to be awake before this tick's decision, or drink stays impossible.
        if self._must_wake_to_drink_or_eat() and (
            self.is_sleeping or self._sleep_entered_by_need
        ):
            self._wake_from_sleep()

        self._perceive()
        if not self.is_sleeping:
            # Keep wakefulness dynamics on simulation time scale (not wall clock),
            # matching compressed sleep recovery used by this demo.
            try:
                wake_elapsed_s = max(0.0, float(dt)) * WAKEFULNESS_ACCUMULATION_FACTOR
                self.wakefulness.update_waking(elapsed_seconds=wake_elapsed_s)
            except Exception:
                pass
        context_events = self._build_context_events()
        novelty = self._compute_novelty()
        conflict = self._compute_conflict()
        intensity = self._compute_intensity()
        host_dt = _host_dt(dt)
        # One game dt per tick. step() moves the host clock; the paired
        # commit omits dt so the same tick is not counted twice. Ticks that
        # do not call step() advance the clock explicitly.
        advanced_by_step = False
        if self._should_continue_sleeping():
            # Mandatory recovery: the core is not asked, and the episode
            # records that the body kept sleep.
            decided_action = None
            executed = "sleep"
            overridden = True
            override_source = "homeostatic:sleep_recovery"
        elif self.replaced_policy_action:
            decided_action = str(self.replaced_policy_action)
            executed, overridden, override_source = self._resolve_executed_action(
                decided_action,
                context_events,
            )
        else:
            drive_bias = self._physiological_drive_bias()
            decided_action = self.step(
                context_events=context_events,
                reward=None,
                novelty=novelty,
                conflict=conflict,
                intensity=intensity,
                decision_only=True,
                physiological_bias=drive_bias or None,
                dt=host_dt,
            )
            advanced_by_step = True
            executed, overridden, override_source = self._resolve_executed_action(
                str(decided_action or "idle"),
                context_events,
            )
        before = self._physiology_snapshot()
        self._interpret_action(executed)
        self._social_step()
        self._apply_sleep_recovery(dt)
        reward = self._compute_reward(before=before, executed_action=executed)
        if not advanced_by_step:
            self.advance_time(host_dt)
        self.commit_executed_transition(
            action=executed,
            reward=reward,
            context_events=context_events,
            decided_action=None if decided_action is None else str(decided_action),
            overridden=overridden,
            override_source=override_source,
            novelty=novelty,
            conflict=conflict,
            intensity=intensity,
        )
        self._resource_metabolism_step(dt)
        self._apply_unmet_need_cost(dt)

        self._advance_autonomous_body(dt)

        self._age_step(dt)

    def _build_context_events(self) -> list[str]:
        events: list[str] = [f"zone:{self.position}"]

        if self.resources:
            food_level = self._food_availability()
            if food_level < 0.15:
                events.append("food_critical")
            elif food_level < 0.4:
                events.append("food_low")
            else:
                events.append("food_ok")

            if self.resources.water < 0.2:
                events.append("water_critical")

        contact_count = sum(1 for p in self.perceived_others if p.category == "contact")
        if contact_count > 0:
            events.append(f"social_contact:{min(contact_count, 3)}")

        nearby_unknown = any(p.category == "unknown_nearby" for p in self.perceived_others)
        if nearby_unknown:
            events.append("stranger_nearby")

        for perceived in self.perceived_others:
            if perceived.public_state.affect_tone == "fearful":
                events.append("alarm_call")
                break

        if self.is_pregnant:
            events.append("pregnant")
        if self.heat_cycle and self.heat_cycle.phase == "estrus":
            events.append("estrus")
        if not self.is_mature:
            events.append("juvenile")

        if self.stress > 0.6:
            events.append("high_stress")
        if self.boredom > 0.6:
            events.append("bored")

        hunger_value = _clamp(self.hunger, 0.0, 1.0)
        if hunger_value >= HUNGER_CRITICAL_THRESHOLD:
            events.append("hunger_critical")
        elif hunger_value >= HUNGER_NEED_THRESHOLD:
            events.append("hunger_high")

        thirst_value = _clamp(self.thirst, 0.0, 1.0)
        if thirst_value >= THIRST_CRITICAL_THRESHOLD:
            events.append("thirst_critical")
        elif thirst_value >= THIRST_NEED_THRESHOLD:
            events.append("thirst_high")

        wakefulness_value = _clamp(float(self.wakefulness.wakefulness), 0.0, 1.0)
        if wakefulness_value >= 0.9:
            events.append("wakefulness_critical")
        elif wakefulness_value >= SLEEP_WAKEFULNESS_THRESHOLD:
            events.append("wakefulness_high")

        if self.physiology_as_policy:
            events.append(f"hunger_bin:{int(hunger_value * 4)}")
            events.append(f"thirst_bin:{int(thirst_value * 4)}")
            events.append(f"wake_bin:{int(wakefulness_value * 4)}")
            if self._courtship_target() is not None:
                events.append("courtship_ready")

        return events

    def _physiology_snapshot(self) -> dict[str, float]:
        return {
            "hunger": _clamp(self.hunger, 0.0, 1.0),
            "thirst": _clamp(self.thirst, 0.0, 1.0),
            "wakefulness": _clamp(float(self.wakefulness.wakefulness), 0.0, 1.0),
        }

    def _compute_reward(
        self,
        before: dict[str, float] | None = None,
        executed_action: str | None = None,
    ) -> float:
        reward = 0.0

        if self.resources:
            food_level = self._food_availability()
            if food_level > 0.5:
                reward += 0.2
            elif food_level < 0.15:
                reward -= 0.4

        # Valence is updated from reward. Feeding it back here is a loop.
        reward -= self.stress * 0.3
        reward -= _clamp(self.hunger - 0.4, 0.0, 1.0) * 0.25
        reward -= _clamp(self.thirst - 0.35, 0.0, 1.0) * 0.35
        if before is not None:
            hunger_drop = float(before.get("hunger", self.hunger)) - _clamp(self.hunger, 0.0, 1.0)
            thirst_drop = float(before.get("thirst", self.thirst)) - _clamp(self.thirst, 0.0, 1.0)
            wake_drop = float(before.get("wakefulness", 0.0)) - _clamp(
                float(self.wakefulness.wakefulness), 0.0, 1.0
            )
            reward += _clamp(hunger_drop, -1.0, 1.0) * 0.8
            reward += _clamp(thirst_drop, -1.0, 1.0) * 0.8
            reward += _clamp(wake_drop, -1.0, 1.0) * 0.5
            action_name = str(executed_action or "")
            if (
                action_name == "eat"
                and hunger_drop <= 1e-9
                and float(before.get("hunger", 0.0)) >= HUNGER_NEED_THRESHOLD
            ):
                reward -= 0.2
            if (
                action_name == "drink"
                and thirst_drop <= 1e-9
                and float(before.get("thirst", 0.0)) >= THIRST_NEED_THRESHOLD
            ):
                reward -= 0.2
            if self.physiology_as_policy:
                reward += self._policy_need_alignment(
                    before,
                    hunger_drop=hunger_drop,
                    thirst_drop=thirst_drop,
                    wake_drop=wake_drop,
                )

        if self._last_social_was_positive:
            reward += 0.2
            self._last_social_was_positive = False

        return _clamp(reward, -1.0, 1.0)

    def _policy_need_alignment(
        self,
        before: dict[str, float],
        *,
        hunger_drop: float,
        thirst_drop: float,
        wake_drop: float,
    ) -> float:
        """Credit measured relief. Choosing eat or drink without a drop is not a success."""
        bonus = 0.0
        hunger = float(before.get("hunger", 0.0))
        thirst = float(before.get("thirst", 0.0))
        wake = float(before.get("wakefulness", 0.0))
        if hunger_drop > 1e-6:
            bonus += 0.35
        elif hunger >= HUNGER_NEED_THRESHOLD:
            bonus -= 0.15
        if thirst_drop > 1e-6:
            bonus += 0.35
        elif thirst >= THIRST_NEED_THRESHOLD:
            bonus -= 0.15
        if wake_drop > 1e-6:
            bonus += 0.35
        elif wake >= SLEEP_WAKEFULNESS_THRESHOLD:
            bonus -= 0.15
        return bonus

    def _physiological_drive_bias(self) -> dict[str, float]:
        """Soft policy input. It does not replace the selected action."""
        if not self.physiology_as_policy:
            return {}
        bias: dict[str, float] = {}
        hunger = _clamp(self.hunger, 0.0, 1.0)
        thirst = _clamp(self.thirst, 0.0, 1.0)
        wake = _clamp(float(self.wakefulness.wakefulness), 0.0, 1.0)
        if hunger > 0.4:
            bias["eat"] = (hunger - 0.4) * 1.8
        if thirst > 0.35:
            bias["drink"] = (thirst - 0.35) * 1.9
        if wake > 0.5:
            bias["sleep"] = (wake - 0.5) * 1.5
        social = self._social_policy_bias()
        if social > 0.0:
            bias["socialize"] = social
        return bias

    def _social_policy_bias(self) -> float:
        if not self.perceived_others:
            return 0.0
        bias = 0.2
        if any(item.category in {"contact", "nearby", "unknown_nearby"} for item in self.perceived_others):
            bias += 0.25
        if self._courtship_target() is not None:
            bias += 0.65
        return bias

    def _courtship_target(self) -> "ChinchillaAgent | None":
        if self.sex != "M" or not self.is_mature:
            return None
        for perceived in self.perceived_others:
            if perceived.public_state.sex != "F":
                continue
            if perceived.category not in {"contact", "nearby"}:
                continue
            candidate = self._find_agent_by_id(perceived.agent_id)
            if candidate is None or not candidate.is_mature or candidate.is_pregnant:
                continue
            heat = candidate.heat_cycle
            if heat is None or heat.phase != "estrus":
                continue
            return candidate
        return None

    def _apply_unmet_need_cost(self, dt: float) -> None:
        """Ignored hunger, thirst, and sleep spend energy when the policy owns them."""
        if not self.physiology_as_policy or self.mortality_system.is_dead():
            return
        safe_dt = max(0.0, float(dt))
        cost = 0.0
        if _clamp(self.hunger, 0.0, 1.0) >= HUNGER_NEED_THRESHOLD and self.current_action != "eat":
            cost += UNMET_HUNGER_ENERGY_PER_S * safe_dt
        if _clamp(self.thirst, 0.0, 1.0) >= THIRST_NEED_THRESHOLD and self.current_action != "drink":
            cost += UNMET_THIRST_ENERGY_PER_S * safe_dt
        if (
            self._needs_sleep_action()
            and self.current_action != "sleep"
            and not self.is_sleeping
        ):
            cost += UNMET_SLEEP_ENERGY_PER_S * safe_dt
        if cost > 0.0:
            self.energy = max(0.0, float(self.energy) - cost)

    def _resolve_executed_action(
        self,
        decided: str,
        context_events: list[str],
    ) -> tuple[str, bool, str | None]:
        """Apply reflex and homeostatic overrides to the core's choice."""
        action = str(decided or "idle")
        overridden = False
        source: str | None = None
        reflex_action, reflex_id = self._select_unconditioned_reflex_detail(context_events)
        if reflex_action is not None and reflex_action != action:
            action = reflex_action
            overridden = True
            source = f"reflex:{reflex_id}" if reflex_id else "reflex"
        if self.physiology_as_policy:
            gated = action
        else:
            gated = self._apply_homeostatic_action_policy(action)
        if gated != action:
            source = self._describe_homeostatic_override(action, gated)
            action = gated
            overridden = True
        return action, overridden, source

    def _describe_homeostatic_override(self, before: str, after: str) -> str:
        wakefulness_value = _clamp(float(self.wakefulness.wakefulness), 0.0, 1.0)
        hunger_value = _clamp(self.hunger, 0.0, 1.0)
        thirst_value = _clamp(self.thirst, 0.0, 1.0)
        wake_resume_threshold = SLEEP_WAKEFULNESS_THRESHOLD * SLEEP_HYSTERESIS
        if self.is_sleeping and wakefulness_value >= wake_resume_threshold:
            return "homeostatic:sleep_recovery"
        if wakefulness_value >= SLEEP_CRITICAL_THRESHOLD:
            return "homeostatic:critical_sleep"
        if thirst_value >= THIRST_CRITICAL_THRESHOLD:
            return "homeostatic:critical_thirst"
        if hunger_value >= HUNGER_CRITICAL_THRESHOLD:
            return "homeostatic:critical_hunger"
        if after in {"drink", "eat", "sleep"}:
            return f"homeostatic:urgent_{after}"
        if before == "sleep":
            return "homeostatic:blocked_sleep"
        if before == "eat":
            return "homeostatic:blocked_eat"
        if before == "drink":
            return "homeostatic:blocked_drink"
        return f"homeostatic:{after}"

    def _compute_novelty(self) -> float:
        novelty = 0.0
        if any(p.category == "unknown_nearby" for p in self.perceived_others):
            novelty += 0.4
        return min(1.0, novelty)

    def _compute_conflict(self) -> float:
        conflict = 0.0
        if any(p.public_state.affect_tone == "fearful" for p in self.perceived_others):
            conflict += 0.3
        if self.stress > 0.5:
            conflict += self.stress * 0.3
        return min(1.0, conflict)

    def _compute_intensity(self) -> float:
        return min(2.0, 0.5 + self.arousal + abs(self.valence) * 0.5)

    def _needs_sleep_action(self) -> bool:
        wakefulness_value = _clamp(float(self.wakefulness.wakefulness), 0.0, 1.0)
        if self.is_sleeping:
            return wakefulness_value >= (SLEEP_WAKEFULNESS_THRESHOLD * SLEEP_HYSTERESIS)
        return wakefulness_value >= SLEEP_WAKEFULNESS_THRESHOLD

    def _needs_eat_action(self) -> bool:
        threshold = HUNGER_AVAILABILITY_THRESHOLD
        if self.is_pregnant:
            threshold = max(0.0, threshold - 0.08)
        return _clamp(self.hunger, 0.0, 1.0) >= threshold

    def _needs_drink_action(self) -> bool:
        threshold = THIRST_AVAILABILITY_THRESHOLD
        if self.is_pregnant:
            threshold = max(0.0, threshold - 0.08)
        return _clamp(self.thirst, 0.0, 1.0) >= threshold

    def _food_availability(self) -> float:
        if self.resources is None:
            return 0.0
        pellets = _clamp(float(getattr(self.resources, "food_pellets", 0.0) or 0.0), 0.0, 1.0)
        hay = _clamp(float(getattr(self.resources, "hay", 0.0) or 0.0), 0.0, 1.0)
        return max(pellets, hay)

    def _food_primary_source(self) -> str | None:
        if self.resources is None:
            return None
        pellets = _clamp(float(getattr(self.resources, "food_pellets", 0.0) or 0.0), 0.0, 1.0)
        hay = _clamp(float(getattr(self.resources, "hay", 0.0) or 0.0), 0.0, 1.0)
        if pellets <= 0.0 and hay <= 0.0:
            return None
        if pellets <= 0.0:
            return "hay"
        if hay <= 0.0:
            return "food_pellets"
        preferred = str(getattr(self, "_food_source_preference", "food_pellets"))
        if preferred in {"food_pellets", "hay"}:
            return preferred
        return None

    def _apply_homeostatic_action_policy(self, action: str) -> str:
        normalized = str(action or "idle")

        wakefulness_value = _clamp(float(self.wakefulness.wakefulness), 0.0, 1.0)
        hunger_value = _clamp(self.hunger, 0.0, 1.0)
        thirst_value = _clamp(self.thirst, 0.0, 1.0)

        # Only a bout opened by real need keeps sleeping. Critical thirst
        # or hunger clears that bout in ``_should_continue_sleeping``.
        if self._should_continue_sleeping():
            return "sleep"

        # Critical sleep deprivation has absolute priority.
        if wakefulness_value >= SLEEP_CRITICAL_THRESHOLD:
            return "sleep"

        # Force urgent physiological actions when need is critical.
        if thirst_value >= THIRST_CRITICAL_THRESHOLD:
            return "drink"
        if hunger_value >= HUNGER_CRITICAL_THRESHOLD:
            return "eat"

        urgency_by_action = {
            "drink": thirst_value - THIRST_NEED_THRESHOLD,
            "eat": hunger_value - HUNGER_NEED_THRESHOLD,
            "sleep": wakefulness_value - SLEEP_WAKEFULNESS_THRESHOLD,
        }
        target_action, target_urgency = max(
            urgency_by_action.items(),
            key=lambda item: float(item[1]),
        )
        if target_urgency > 0.0 and normalized != target_action:
            return target_action

        if normalized == "sleep" and (not self._needs_sleep_action()):
            return "rest" if self.energy < 0.45 else "explore"
        if normalized == "eat" and (not self._needs_eat_action()):
            return "explore"
        if normalized == "drink" and (not self._needs_drink_action()):
            return "explore"
        return normalized

    def _must_wake_to_drink_or_eat(self) -> bool:
        """A penalty-band thirst or hunger ends a bout. Critical sleep still wins.

        The unmet-need cost stays on during sleep (an unmet need may be
        fatal). At 0.025 energy per second that cost reaches exhaustion
        before thirst or hunger hit the higher critical constants, so the
        bout yields when the penalty starts and the animal can drink or
        eat. Process S at the sleep-death threshold still keeps the night:
        waking there would skip recovery and die of sleep deprivation on
        the same tick.
        """
        thirst = _clamp(self.thirst, 0.0, 1.0)
        hunger = _clamp(self.hunger, 0.0, 1.0)
        if thirst < THIRST_NEED_THRESHOLD and hunger < HUNGER_NEED_THRESHOLD:
            return False
        wake = _clamp(float(self.wakefulness.wakefulness), 0.0, 1.0)
        return wake < SLEEP_CRITICAL_THRESHOLD

    def _wake_from_sleep(self) -> None:
        self.is_sleeping = False
        self._sleep_entered_by_need = False
        if self.current_action == "sleep":
            self.current_action = "rest"

    def _should_continue_sleeping(self) -> bool:
        if not self.is_sleeping or not self._sleep_entered_by_need:
            return False
        if self._must_wake_to_drink_or_eat():
            return False
        wakefulness_value = _clamp(float(self.wakefulness.wakefulness), 0.0, 1.0)
        wake_resume_threshold = SLEEP_WAKEFULNESS_THRESHOLD * SLEEP_HYSTERESIS
        return wakefulness_value >= wake_resume_threshold

    def _sleep_recovery_duration_s(self, dt: float) -> float:
        """Physiological seconds of this slice. Linear in ``dt``.

        ``SLEEP_MIN_RECOVERY_DURATION_S`` is not a per-tick floor. Short
        steps used to apply that floor on every call, so 1x restored energy
        and Process S several times faster than 10x over the same
        simulation second.
        """
        safe_dt = max(0.0, float(dt))
        return safe_dt * SLEEP_RECOVERY_DURATION_FACTOR

    def _advance_autonomous_body(self, dt: float) -> None:
        """Integrate the body in base steps so UI speed does not change metabolism.

        ``autonomous_tick`` spends cost in proportion to ``dt`` but rests once
        per call. Full slices of ``COLONY_BODY_STEP_S`` are applied and the
        remainder is carried. A short tail used to rest a full time, so the
        same simulation second restored more energy when it was split into
        uneven steps. While asleep the bout itself restores energy, and a
        waking tick must not run the body.
        """
        if self.is_sleeping or getattr(self, "autonomous_runtime", None) is None:
            return
        remaining = _host_dt(dt)
        if remaining <= 0.0:
            return
        self._body_step_carry += remaining
        step = COLONY_BODY_STEP_S
        guard = 0
        while self._body_step_carry + 1e-12 >= step:
            self.autonomous_tick(step)
            self._body_step_carry -= step
            guard += 1
            if guard >= 100000:
                break
        if self._body_step_carry < 1e-9:
            self._body_step_carry = 0.0

    def _apply_sleep_recovery(self, dt: float) -> None:
        # A chosen "sleep" before Process S reaches onset is quiet rest.
        # ``_interpret_action`` marks the animal asleep before this runs, so
        # the continue check cannot treat that mark as a real bout. Only
        # ``_sleep_entered_by_need`` keeps the night open. Critical thirst
        # or hunger wakes the animal on this tick.
        if self._must_wake_to_drink_or_eat():
            if self.is_sleeping or self.current_action == "sleep" or self._sleep_entered_by_need:
                self._wake_from_sleep()
            return

        wake = _clamp(float(self.wakefulness.wakefulness), 0.0, 1.0)
        at_onset = wake >= SLEEP_WAKEFULNESS_THRESHOLD
        if at_onset:
            self._sleep_entered_by_need = True

        in_need_bout = self._sleep_entered_by_need and (
            self.is_sleeping or self.current_action == "sleep" or at_onset
        )
        if not in_need_bout:
            if self.current_action == "sleep" or self.is_sleeping:
                self._wake_from_sleep()
            return

        self.is_sleeping = True
        sleep_duration_s = self._sleep_recovery_duration_s(dt)
        try:
            self.wakefulness.update_sleeping(elapsed_seconds=sleep_duration_s)
        except Exception:
            pass

        try:
            runtime = getattr(self, "autonomous_runtime", None)
            if runtime is not None and hasattr(runtime, "energy_system"):
                runtime.energy_system.recover(rest_time=max(0.0, sleep_duration_s) / 60.0)
        except Exception:
            pass

        # Consolidate memories periodically while sleeping to avoid expensive
        # deep-sleep calls every simulation tick.
        self._sleep_consolidation_accum_s += sleep_duration_s
        if self._sleep_consolidation_accum_s >= SLEEP_CONSOLIDATION_INTERVAL_S:
            cycles = int(self._sleep_consolidation_accum_s // SLEEP_CONSOLIDATION_INTERVAL_S)
            cycles = max(1, min(SLEEP_MAX_CONSOLIDATION_CYCLES_PER_TICK, cycles))
            self._sleep_consolidation_accum_s -= cycles * SLEEP_CONSOLIDATION_INTERVAL_S
            self.sleep(cycles=cycles, sleep_duration_seconds=0.0)

        if self._should_wake_now() or self._must_wake_to_drink_or_eat():
            self._wake_from_sleep()

    def _seed_habit_bootstrap(self) -> None:
        """Dataset priors are host seeding, not a waking habit update."""
        with initializing():
            self._write_habit_bootstrap()

    def _write_habit_bootstrap(self) -> None:
        intent_memory = getattr(self, "intent_memory", None)
        if intent_memory is None:
            return
        for habit in self.behavior_profile.habits:
            context = list(habit.context)
            features = tuple(intent_memory.canonical_context_features(context))
            context_signature = intent_memory._compute_context_signature(context)
            trace_key = f"{habit.action}:{context_signature}"
            strength = max(intent_memory.min_strength_for_trace, float(habit.strength))
            existing = intent_memory.traces.get(trace_key)
            if existing is not None:
                existing.strength = max(float(existing.strength), strength)
                existing.recency = max(float(existing.recency), 1.0)
                existing.timestamp = time.time()
                existing.context_features = features
                existing.match_subset = True
                continue
            intent_memory.traces[trace_key] = IntentTrace(
                intent_type=habit.action,
                context_signature=context_signature,
                strength=strength,
                recency=1.0,
                timestamp=time.time(),
                context_features=features,
                match_subset=True,
            )

    def _select_unconditioned_reflex(self, context_events: list[str]) -> str | None:
        action, _reflex_id = self._select_unconditioned_reflex_detail(context_events)
        return action

    def _select_unconditioned_reflex_detail(
        self,
        context_events: list[str],
    ) -> tuple[str | None, str | None]:
        if not self.unconditioned_reflexes:
            return None, None
        context_set = set(context_events)
        selected: UnconditionedReflex | None = None
        best_priority = float("-inf")
        for reflex in self.unconditioned_reflexes:
            if self._current_action_is_exclusive() and not reflex.override_exclusive:
                continue
            if reflex.trigger_any and context_set.isdisjoint(reflex.trigger_any):
                continue
            if reflex.trigger_all and not set(reflex.trigger_all).issubset(context_set):
                continue
            if reflex.cooldown_s > 0.0:
                last_time = self._reflex_last_activation.get(reflex.reflex_id)
                if last_time is not None and (self.sim_time - last_time) < reflex.cooldown_s:
                    continue
            if self.physiology_as_policy and reflex.action in {"eat", "drink", "sleep"}:
                continue
            if reflex.priority > best_priority:
                best_priority = reflex.priority
                selected = reflex

        if selected is None:
            return None, None
        self._reflex_last_activation[selected.reflex_id] = self.sim_time
        return selected.action, selected.reflex_id

    def _interpret_action(self, action: str) -> None:
        was_sleeping = self.is_sleeping
        self.current_action = action
        if action != "sleep":
            self.is_sleeping = False
        if action != "run_wheel":
            self._release_resource("wheel")
            self._wheel_run_started_at = None

        if action == "eat":
            self._try_acquire_resource("food_pellets")
            self._move_towards_any(["bowl_pellets", "bowl_hay"])
        elif action == "drink":
            self._try_acquire_resource("water")
            self._move_towards_any(["waterer", "bowl_hay"])
        elif action == "run_wheel":
            if self.position == "wheel" and self.resources and self.resources.wheel_lock == self.agent_id:
                if self._wheel_run_started_at is None:
                    self._wheel_run_started_at = float(self.sim_time)
                elif (self.sim_time - self._wheel_run_started_at) >= WHEEL_RUN_MAX_CONTINUOUS_S:
                    # Prevent one agent from monopolizing the wheel forever.
                    self._release_resource("wheel")
                    self._wheel_run_started_at = None
                    self._set_position("floor")
                    self._move_towards_any(
                        ["corner", "toy", "house"],
                        force=True,
                        allow_random_neighbor=True,
                        relocate_within_targets=True,
                    )
                    self.current_action = "explore"
                    self._unstick_position()
                    return
            acquired = self._try_acquire_resource("wheel")
            if acquired:
                if self._wheel_run_started_at is None:
                    self._wheel_run_started_at = float(self.sim_time)
                self._set_position("wheel")
            else:
                # Keep an active fallback motion while wheel is busy.
                moved = self._move_towards_any(
                    ["floor", "shelf_lower", "toy", "corner"],
                    allow_random_neighbor=True,
                    relocate_within_targets=True,
                )
                if not moved:
                    self._maybe_move_position()
        elif action == "hide":
            self._set_position("house")
        elif action == "explore":
            self._maybe_move_position()
        elif action == "sleep":
            self.is_sleeping = True
            if not was_sleeping:
                self._move_towards_any(["house", "shelf_lower", "shelf_mid"], force=True)
        elif action == "groom_self":
            self._apply_affect_impulse(stress=-0.05, valence=0.05, intensity=0.3)
            if self._rng.random() < 0.3:
                self._move_towards_any(
                    ["floor", "house", "dustbath"],
                    relocate_within_targets=True,
                )
        elif action == "socialize":
            self._move_towards_any(["floor", "corner", "toy"], relocate_within_targets=True)
        elif action == "mount_display":
            self.is_sleeping = False
            mate = self._find_agent_by_id(self._current_mate_id)
            if mate is not None:
                if self.position != mate.position:
                    moved = self._move_towards_any(
                        [mate.position],
                        force=True,
                        allow_random_neighbor=True,
                    )
                    if (not moved) and (self.position in ADJACENT_ZONES.get(mate.position, set())):
                        self._set_position(mate.position)
            else:
                self._move_towards_any(
                    ["house", "floor", "corner"],
                    relocate_within_targets=True,
                )
        elif action == "play":
            self._apply_affect_impulse(curiosity=0.1, arousal=0.1, intensity=0.3)
            self._move_towards_any(
                ["toy", "dustbath", "floor", "object"],
                relocate_within_targets=True,
            )
        elif action == "rest":
            self.is_sleeping = False
            self._apply_affect_impulse(stress=-0.03, intensity=0.2)
            if self._rng.random() < 0.25:
                self._move_towards_any(
                    ["floor", "house", "dustbath", "shelf_lower"],
                    relocate_within_targets=True,
                )

        self._unstick_position()

    def _should_sleep_now(self) -> bool:
        if self._must_wake_to_drink_or_eat():
            return False
        return (not self.is_sleeping) and self.wakefulness.wakefulness >= SLEEP_WAKEFULNESS_THRESHOLD

    def _should_wake_now(self) -> bool:
        wake_threshold = SLEEP_WAKEFULNESS_THRESHOLD * SLEEP_HYSTERESIS
        return self.is_sleeping and self.wakefulness.wakefulness < wake_threshold

    def get_public_state(self) -> PublicState:
        return PublicState(
            agent_id=self.agent_id,
            name=self.name,
            position=self.position,
            affect_tone=self._compute_affect_tone(),
            current_action=self.current_action,
            is_receptive=self._is_receptive(),
            sex=self.sex,
            age_category=self._age_category(),
            scent_signature=self.scent_signature,
        )

    def _compute_affect_tone(self) -> str:
        if self.is_sleeping:
            return "sleeping"
        if self.stress > 0.6:
            return "fearful"
        if self.arousal > 0.8 and self.dominance_level > 0.6:
            return "aggressive"
        if self.arousal > 0.6:
            return "excited"
        return "calm"

    def _age_category(self) -> str:
        if not self.is_mature:
            return "juvenile"
        if self.age > MATURITY_AGE_S * 4:
            return "elder"
        return "adult"

    def _is_receptive(self) -> bool:
        return (not self._current_action_is_exclusive()) and self.stress < 0.82

    def _perceive(self) -> None:
        self.perceived_others = []
        for other in self.colony:
            if other is self:
                continue
            public = other.get_public_state()
            known = self.knowledge.get(other.agent_id)
            if known is not None:
                if public.position == self.position:
                    category = "contact"
                    known.last_seen_position = public.position
                    known.last_seen_time = self.sim_time
                    known.position_confidence = 1.0
                elif is_same_or_adjacent(self.position, public.position):
                    category = "nearby"
                    known.last_seen_position = public.position
                    known.last_seen_time = self.sim_time
                    known.position_confidence = max(known.position_confidence, 0.85)
                else:
                    category = "distant"
                known.last_seen_affect = public.affect_tone
                self.perceived_others.append(PerceivedOther(other.agent_id, category, public, known))
            elif is_same_or_adjacent(self.position, public.position):
                self.perceived_others.append(
                    PerceivedOther(other.agent_id, "unknown_nearby", public, None)
                )
        self._perceive_alarm_calls()

    def _perceive_alarm_calls(self) -> None:
        for other in self.colony:
            if other is self or not other._is_emitting_alarm():
                continue
            impulse = 0.3 if other.agent_id in self.knowledge else 0.15
            self._apply_affect_impulse(stress=impulse, arousal=0.1, intensity=0.7)
            known = self.knowledge.get(other.agent_id)
            if known is not None:
                known.last_seen_position = other.position
                known.last_seen_affect = "fearful"

    def _is_emitting_alarm(self) -> bool:
        return self.stress > 0.7

    def _social_step(self) -> None:
        if self.physiology_as_policy and self.current_action not in {
            "socialize",
            "play",
            "mount_display",
            "allogroom",
            "sniff_greet",
            "play_invite",
        }:
            return
        if self.pending_offer is not None or not self.perceived_others:
            return
        offer_type, target = self._choose_social_offer()
        if offer_type and target is not None:
            self.send_social_offer(offer_type, target)

    def _reproductive_drive_score(self) -> float:
        drive = float(getattr(self.reproductive_system, "reproductive_drive", 0.0))
        energy_term = _clamp((self.energy - 0.3) / 0.7, 0.0, 1.0)
        calm_term = _clamp(1.0 - self.stress, 0.0, 1.0)
        social_term = _clamp(self.social_drive, 0.0, 1.0)
        return _clamp(
            (drive * 0.45) + (energy_term * 0.25) + (calm_term * 0.2) + (social_term * 0.1),
            0.0,
            1.0,
        )

    def _choose_social_offer(self) -> tuple[str | None, "ChinchillaAgent" | None]:
        unknowns = [p for p in self.perceived_others if p.category == "unknown_nearby"]
        if unknowns and self._is_offer_available("sniff_greet"):
            return "sniff_greet", self._find_agent_by_id(unknowns[0].agent_id)

        contacts = [p for p in self.perceived_others if p.category == "contact" and p.known is not None]
        if contacts and self._is_offer_available("sniff_greet"):
            # Keep building weak social ties: without this, pairs can stagnate on
            # low affinity and never reach mating/social thresholds naturally.
            reacquaint_candidates = [
                p
                for p in contacts
                if p.known is not None and (p.known.familiarity < 0.35 or p.known.affinity < 0.12)
            ]
            if reacquaint_candidates:
                reacquaint_candidates.sort(
                    key=lambda item: (
                        item.known.familiarity if item.known is not None else 1.0,
                        item.known.affinity if item.known is not None else 1.0,
                    )
                )
                return "sniff_greet", self._find_agent_by_id(reacquaint_candidates[0].agent_id)

        nearby_known = [
            p for p in self.perceived_others if p.category in {"contact", "nearby"} and p.known is not None
        ]
        if not nearby_known:
            return None, None

        if self.is_mature and self.sex == "M" and self._is_offer_available("mount_display"):
            mating_drive = self._reproductive_drive_score()
            if mating_drive >= MOUNT_DISPLAY_MIN_DRIVE_SCORE:
                affinity_gate = max(0.12, MOUNT_DISPLAY_INITIATOR_MIN_AFFINITY - (0.18 * mating_drive))
                scored_candidates: list[tuple[float, ChinchillaAgent]] = []
                for perceived in nearby_known:
                    if perceived.public_state.sex != "F":
                        continue
                    if perceived.known is None:
                        continue
                    if perceived.known.relationship_type == "kin":
                        continue
                    if perceived.known.affinity < affinity_gate:
                        continue
                    candidate = self._find_agent_by_id(perceived.agent_id)
                    if candidate is None:
                        continue
                    if candidate.sex != "F" or (not candidate.is_mature) or candidate.is_pregnant:
                        continue
                    heat = candidate.heat_cycle
                    if heat is None or heat.phase != "estrus":
                        continue
                    score = perceived.known.affinity + 0.32 + (0.22 * mating_drive) + (0.16 * heat.urgency())
                    if perceived.public_state.is_receptive:
                        score += 0.05
                    scored_candidates.append((score, candidate))
                if scored_candidates:
                    scored_candidates.sort(key=lambda item: item[0], reverse=True)
                    return "mount_display", scored_candidates[0][1]

        if not contacts:
            return None, None

        if self.social_drive > 0.5 and self._is_offer_available("allogroom"):
            candidates = [p for p in contacts if p.known and p.known.affinity > 0.12]
            if candidates:
                candidates.sort(key=lambda x: x.known.affinity if x.known else -1.0, reverse=True)
                return "allogroom", self._find_agent_by_id(candidates[0].agent_id)

        if self.boredom > 0.5 and self.arousal > 0.4:
            candidates = [p for p in contacts if p.known and p.known.affinity > 0.08]
            if candidates:
                return "play_invite", self._find_agent_by_id(candidates[0].agent_id)

        can_share_anything = any(
            known_id != contacts[0].agent_id and known.familiarity > 0.3
            for known_id, known in self.knowledge.items()
        )
        if self.social_drive > 0.3 and can_share_anything:
            return "share_knowledge", self._find_agent_by_id(contacts[0].agent_id)

        return None, None

    def send_social_offer(self, offer_type: str, target_agent: "ChinchillaAgent") -> SocialResponse | None:
        if not self._can_initiate_offer(offer_type, target_agent):
            response = SocialResponse(False, self.agent_id, "blocked")
            self._handle_social_outcome(target_agent.agent_id, offer_type, response)
            return response

        offer = SocialOffer(
            offer_type=offer_type,
            from_id=self.agent_id,
            from_public=self.get_public_state(),
            intensity=self._social_drive_intensity(),
        )
        response = target_agent.receive_social_offer(offer)
        self._activate_cooldown(offer_type)
        if response is None:
            self.pending_offer = PendingOffer(offer_type, target_agent.agent_id, self.sim_time)
            return None

        self._handle_social_outcome(target_agent.agent_id, offer_type, response)
        return response

    def receive_social_offer(self, offer: SocialOffer) -> SocialResponse | None:
        if self.is_sleeping and offer.offer_type != "sleep_together":
            return SocialResponse(False, self.agent_id, "sleeping")
        if self._current_action_is_exclusive():
            if offer.offer_type == "mount_display":
                return SocialResponse(False, self.agent_id, "busy")
            return None

        known = self.knowledge.get(offer.from_id)
        if known is None:
            if self.stress > 0.4:
                return SocialResponse(False, self.agent_id, "unknown_stranger_fearful")
            if offer.offer_type == "sniff_greet":
                self._initiate_meeting(offer.from_id, offer.from_public)
                self._apply_social_effects("sniff_greet", offer.from_id, initiator=False)
                self._record_interaction(offer.from_id, "sniff_greet", "other", "accepted", 0.05)
                return SocialResponse(True, self.agent_id, "greeting_unknown")
            return SocialResponse(False, self.agent_id, "unknown_stranger")

        if offer.offer_type in JUVENILE_BLOCKED_OFFERS and not self.is_mature:
            return SocialResponse(False, self.agent_id, "juvenile_restricted")

        if offer.offer_type == "allogroom":
            if known.affinity < -0.2:
                return SocialResponse(False, self.agent_id, "low_affinity")
            if self.stress > 0.7:
                return SocialResponse(False, self.agent_id, "too_stressed")

        elif offer.offer_type == "mount_display":
            if known.relationship_type == "kin":
                return SocialResponse(False, self.agent_id, "kin")
            if self.sex != "F":
                return SocialResponse(False, self.agent_id, "wrong_sex")
            if not self.is_mature:
                return SocialResponse(False, self.agent_id, "immature")
            estrus_urgency = 0.0
            estrus_gate = MOUNT_DISPLAY_ESTRUS_MIN_VALUE
            if self.heat_cycle is not None:
                estrus_urgency = _clamp(self.heat_cycle.urgency(), 0.0, 1.0)
                estrus_gate = max(0.25, MOUNT_DISPLAY_ESTRUS_MIN_VALUE - (0.2 * estrus_urgency))
            if (
                self.heat_cycle is None
                or self.heat_cycle.phase != "estrus"
                or self.heat_cycle.value < estrus_gate
            ):
                return SocialResponse(False, self.agent_id, "not_in_heat")
            affinity_gate = max(0.10, MOUNT_DISPLAY_ACCEPT_MIN_AFFINITY - (0.12 * estrus_urgency))
            if known.affinity < affinity_gate:
                return SocialResponse(False, self.agent_id, "insufficient_affinity")
            if self.stress >= 0.82:
                return SocialResponse(False, self.agent_id, "stress_too_high")
            if self.energy <= 0.30:
                return SocialResponse(False, self.agent_id, "low_energy")
            if self.is_pregnant:
                return SocialResponse(False, self.agent_id, "pregnant")
            if self.resources and resource_blocks_reproduction(self._food_availability()):
                return SocialResponse(False, self.agent_id, "resource_stress")
            self._start_pregnancy(offer.from_id)

        elif offer.offer_type == "chase":
            if known.dominance_felt < -0.3:
                self.current_action = "flee"

        self._apply_social_effects(offer.offer_type, offer.from_id, initiator=False)
        self._record_interaction(offer.from_id, offer.offer_type, "other", "accepted", 0.03)

        meta = SOCIAL_OFFER_TYPES.get(offer.offer_type)
        if meta and meta.exclusive:
            self.current_action = offer.offer_type
            self._exclusive_action_timer = max(self._exclusive_action_timer, meta.duration)

        return SocialResponse(True, self.agent_id, "accepted")

    def _can_initiate_offer(self, offer_type: str, target_agent: "ChinchillaAgent") -> bool:
        if offer_type in JUVENILE_BLOCKED_OFFERS and not self.is_mature:
            return False
        if offer_type != "mount_display":
            return True
        if not self.is_mature or self.sex != "M":
            return False
        if target_agent.sex != "F" or (not target_agent.is_mature) or target_agent.is_pregnant:
            return False
        known = self.knowledge.get(target_agent.agent_id)
        mating_drive = self._reproductive_drive_score()
        affinity_gate = max(0.12, MOUNT_DISPLAY_INITIATOR_MIN_AFFINITY - (0.18 * mating_drive))
        if (
            known is None
            or known.relationship_type == "kin"
            or known.affinity < affinity_gate
        ):
            return False
        if mating_drive < MOUNT_DISPLAY_MIN_DRIVE_SCORE:
            return False
        if self.energy <= max(0.25, 0.45 - (0.2 * mating_drive)):
            return False
        if self.stress >= min(0.92, 0.78 + (0.12 * mating_drive)):
            return False
        if not target_agent._is_receptive():
            return False
        if self.resources and resource_blocks_reproduction(self._food_availability()):
            return False
        return True

    def _social_drive_intensity(self) -> float:
        return _clamp(0.5 * self.social_drive + 0.3 * (1.0 - self.stress), 0.0, 1.0)

    def _handle_social_outcome(self, target_id: str, offer_type: str, response: SocialResponse) -> None:
        if response.accepted:
            self._last_social_was_positive = True
            if offer_type == "mount_display":
                self._current_mate_id = str(target_id)
            self._apply_social_effects(offer_type, target_id, initiator=True)
            self._record_interaction(target_id, offer_type, "self", "accepted", 0.05)
            target = self._find_agent_by_id(target_id)
            if target is not None:
                self._exchange_knowledge(target)
                target._exchange_knowledge(self)
        else:
            self._last_social_was_positive = False
            if offer_type == "mount_display":
                self._current_mate_id = None
            self._apply_social_effects("reject", target_id, initiator=True)
            self._record_interaction(target_id, offer_type, "self", "rejected", -0.05)

    def _apply_social_effects(self, offer_type: str, other_id: str, *, initiator: bool) -> None:
        other = self._find_agent_by_id(other_id)
        known = self._ensure_known(other_id, other.get_public_state() if other else None)

        if offer_type == "sniff_greet":
            known.familiarity = _clamp(known.familiarity + 0.2, 0.0, 1.0)
            known.affinity = _clamp(known.affinity + 0.07, -1.0, 1.0)
            known.relationship_type = "acquaintance"

        elif offer_type == "allogroom":
            known.affinity = _clamp(known.affinity + (0.05 if initiator else 0.08), -1.0, 1.0)
            known.familiarity = _clamp(known.familiarity + 0.06, 0.0, 1.0)
            self._apply_affect_impulse(stress=-0.1 if initiator else -0.15, intensity=0.7)

        elif offer_type == "play_invite":
            known.affinity = _clamp(known.affinity + 0.03, -1.0, 1.0)
            known.familiarity = _clamp(known.familiarity + 0.03, 0.0, 1.0)
            self._apply_affect_impulse(curiosity=0.2, arousal=0.1, intensity=0.6)

        elif offer_type == "chase":
            if initiator:
                known.dominance_felt = _clamp(known.dominance_felt + 0.1, -1.0, 1.0)
                self.energy = _clamp(self.energy - 0.05, 0.0, 1.0)
            else:
                self._apply_affect_impulse(stress=0.2, intensity=0.8)
                known.dominance_felt = _clamp(known.dominance_felt - 0.1, -1.0, 1.0)

        elif offer_type == "mount_display":
            known.is_mate = True
            known.relationship_type = "mate"
            known.affinity = _clamp(known.affinity + (0.11 if initiator else 0.14), -1.0, 1.0)
            known.familiarity = _clamp(known.familiarity + 0.08, 0.0, 1.0)
            self._apply_affect_impulse(valence=0.08, arousal=0.06, attachment=0.1, intensity=0.6)

        elif offer_type == "share_knowledge" and other is not None:
            self._exchange_knowledge(other)

        elif offer_type == "reject":
            self._apply_frustration("social_reject")
            known.affinity = _clamp(known.affinity - 0.02, -1.0, 1.0)

        known._recompute_relationship()

        meta = SOCIAL_OFFER_TYPES.get(offer_type)
        if meta and meta.exclusive:
            self.current_action = offer_type
            self._exclusive_action_timer = max(self._exclusive_action_timer, meta.duration)

    def _exchange_knowledge(self, other_agent: "ChinchillaAgent") -> None:
        for known_id, known in list(self.knowledge.items()):
            if known_id == other_agent.agent_id or known.familiarity <= 0.3:
                continue
            hearsay = HearsayItem(
                subject_id=known_id,
                source_id=self.agent_id,
                content=self._summarize_knowledge(known),
                time_heard=self.sim_time,
                confidence=_clamp(known.familiarity * 0.6, 0.05, 0.95),
                hops=1,
            )
            other_agent._receive_hearsay(hearsay)

    def _receive_hearsay(self, hearsay: HearsayItem) -> None:
        confidence = hearsay.confidence
        source = self.knowledge.get(hearsay.source_id)
        if source is not None and source.trust < 0.4:
            confidence *= 0.5
        if hearsay.hops > 1:
            confidence *= 0.3

        known = self.knowledge.get(hearsay.subject_id)
        if known is None:
            known = KnownAgent(
                agent_id=hearsay.subject_id,
                name=f"unknown-{hearsay.subject_id[:6]}",
                sex="U",
                last_seen_position="unknown",
                last_seen_time=self.sim_time,
                position_confidence=0.2,
                familiarity=0.12,
                memory_confidence=min(0.59, confidence),
                relationship_type="acquaintance",
            )
            self.knowledge[hearsay.subject_id] = known
        elif confidence > known.memory_confidence:
            known.memory_confidence = confidence

        known.add_hearsay(
            HearsayItem(
                subject_id=hearsay.subject_id,
                source_id=hearsay.source_id,
                content=hearsay.content,
                time_heard=self.sim_time,
                confidence=_clamp(confidence, 0.0, 1.0),
                hops=hearsay.hops + 1,
            )
        )

    def _summarize_knowledge(self, known: KnownAgent) -> str:
        return f"seen_at_{known.last_seen_position}|affect_{known.last_seen_affect}"

    def _record_interaction(
        self,
        target_id: str,
        interaction_type: str,
        initiated_by: str,
        outcome: str,
        affect_delta: float,
    ) -> None:
        known = self.knowledge.get(target_id)
        if known is None:
            target = self._find_agent_by_id(target_id)
            known = self._ensure_known(target_id, target.get_public_state() if target else None)
        known.record_episode(
            InteractionEpisode(
                time=self.sim_time,
                interaction_type=interaction_type,
                initiated_by=initiated_by,
                outcome=outcome,
                affect_delta=affect_delta,
                context=self.current_action,
            )
        )

    def _ensure_known(self, other_id: str, public: PublicState | None) -> KnownAgent:
        known = self.knowledge.get(other_id)
        if known is not None:
            return known
        if public is None:
            known = KnownAgent(
                agent_id=other_id,
                name=f"unknown-{other_id[:6]}",
                sex="U",
                last_seen_position="unknown",
                last_seen_time=self.sim_time,
                position_confidence=0.2,
                memory_confidence=0.5,
            )
        else:
            known = KnownAgent(
                agent_id=other_id,
                name=public.name,
                sex=public.sex,
                last_seen_position=public.position,
                last_seen_time=self.sim_time,
                position_confidence=1.0,
                memory_confidence=1.0,
            )
        self.knowledge[other_id] = known
        return known

    def _initiate_meeting(self, other_id: str, public: PublicState) -> None:
        known = self._ensure_known(other_id, public)
        known.familiarity = _clamp(max(known.familiarity, 0.2), 0.0, 1.0)
        known.affinity = _clamp(max(known.affinity, 0.14), -1.0, 1.0)
        known.last_seen_position = public.position
        known.last_seen_time = self.sim_time
        known.position_confidence = 1.0
        known.relationship_type = "acquaintance"

    def _is_offer_available(self, offer_type: str) -> bool:
        return self.sim_time >= self._offer_cooldowns.get(offer_type, -1.0)

    def _activate_cooldown(self, offer_type: str) -> None:
        cooldown = OFFER_COOLDOWNS.get(offer_type)
        if cooldown is not None:
            self._offer_cooldowns[offer_type] = self.sim_time + cooldown

    def _check_offer_timeout(self) -> None:
        if self.pending_offer is None:
            return
        if self.sim_time - self.pending_offer.started_at < OFFER_TIMEOUT_S:
            return
        self._apply_frustration("offer_timeout")
        self._record_interaction(
            self.pending_offer.target_id,
            self.pending_offer.offer_type,
            "self",
            "timeout",
            -0.1,
        )
        self.pending_offer = None

    def _current_action_is_exclusive(self) -> bool:
        return self._exclusive_action_timer > 0.0

    def _tick_exclusive_action(self, dt: float) -> None:
        if self._exclusive_action_timer <= 0.0:
            return
        self._exclusive_action_timer -= dt
        if self._exclusive_action_timer <= 0.0:
            self._exclusive_action_timer = 0.0
            self.current_action = "idle"

    def _resource_metabolism_step(self, dt: float) -> None:
        if self.resources is None:
            return
        try:
            elapsed = float(dt)
        except (TypeError, ValueError):
            return
        if not math.isfinite(elapsed) or elapsed <= 0.0:
            return
        # Keep the fractional second. Resetting the accumulator to 0 made
        # hunger and thirst advance once per tick instead of once per second.
        self._metabolism_tick += elapsed
        # 0.1 * 10 is just under 1 in binary floats. Without the slack a
        # 10 s run of 0.1 s steps grows one second less hunger than one
        # 2.5 s step repeated.
        while self._metabolism_tick >= 1.0 - 1e-9:
            self._metabolism_tick -= 1.0
            if self._metabolism_tick < 0.0:
                self._metabolism_tick = 0.0
            self._apply_metabolism_second()

    def _apply_metabolism_second(self) -> None:
        if self.resources is None:
            return
        self.hunger = _clamp(self.hunger + HUNGER_ACCUMULATION_PER_S, 0.0, 1.0)
        self.thirst = _clamp(self.thirst + THIRST_ACCUMULATION_PER_S, 0.0, 1.0)
        if self.hunger >= HUNGER_CRITICAL_THRESHOLD:
            self._apply_affect_impulse(stress=0.015, valence=-0.015, intensity=0.35)
        if self.thirst >= THIRST_CRITICAL_THRESHOLD:
            self._apply_affect_impulse(stress=0.018, valence=-0.02, intensity=0.4)

        if self.is_sleeping or self.current_action == "sleep":
            return

        if not self.resources.consume_food(
            0.0003 * RESOURCE_CONSUMPTION_MULTIPLIER,
            primary=self._food_primary_source(),
        ):
            self._apply_affect_impulse(stress=0.02, valence=-0.02, intensity=0.5)
            # Apply direct energy penalty when food is unavailable so that
            # resource scarcity affects physiology (can lead to death).
            try:
                penalty = RESOURCE_MISSING_ENERGY_PENALTY_PER_S * float(RESOURCE_CONSUMPTION_MULTIPLIER)
                self.energy = max(0.0, float(self.energy) - float(penalty))
            except Exception:
                pass

        self.resources.water = max(
            0.0,
            self.resources.water - (0.0001 * RESOURCE_CONSUMPTION_MULTIPLIER),
        )
        if self.resources.water <= 0.0:
            self._apply_affect_impulse(stress=0.02, intensity=0.4)
            try:
                penalty = WATER_MISSING_ENERGY_PENALTY_PER_S * float(RESOURCE_CONSUMPTION_MULTIPLIER)
                self.energy = max(0.0, float(self.energy) - float(penalty))
            except Exception:
                pass

    def _age_step(self, dt: float) -> None:
        self.age += dt
        if not self.is_mature and self.age >= MATURITY_AGE_S:
            self.is_mature = True
            if self.sex == "F" and self.heat_cycle is None:
                self.heat_cycle = HeatCycle()

        if self.sex == "F" and self.heat_cycle is not None and not self.is_pregnant:
            self.heat_cycle.update(dt)

        if self.is_pregnant:
            self.gestation_timer -= dt
            self.energy = _clamp(self.energy - 0.0005 * dt, 0.0, 1.0)
            self._apply_affect_impulse(stress=0.0008 * dt, intensity=0.2)
            if self.gestation_timer <= 0.0:
                self._give_birth()

        for known in self.knowledge.values():
            known.decay(self.sim_time, dt)

        self._apply_reproduction()
        self._apply_mortality(dt)

    def _apply_reproduction(self) -> None:
        """Advance reproductive drive. A failed update is logged and leaves drive as it was."""
        reproductive = getattr(self, "reproductive_system", None)
        update = getattr(reproductive, "update", None)
        if reproductive is None or not callable(update):
            logger.warning(
                "reproductive update skipped for agent %s: reproductive system is missing",
                getattr(self, "agent_id", ""),
            )
            return
        try:
            energy = _coerce_finite(self.energy)
            valence = _coerce_finite(self.valence)
            neuromod = getattr(self, "neuromodulators", None)
            cortisol = _coerce_finite(getattr(neuromod, "cortisol", 0.0))
            lived_steps = int(getattr(self, "lived_steps", 0) or 0)
            resource_share = _coerce_finite(self._food_availability())
        except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as exc:
            logger.warning(
                "reproductive update inputs unreadable for agent %s: %s",
                getattr(self, "agent_id", ""),
                exc,
            )
            return
        try:
            update(
                energy=energy,
                valence=valence,
                cortisol=cortisol,
                lived_steps=lived_steps,
                resource_share=resource_share,
            )
        except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as exc:
            logger.warning(
                "reproductive update failed for agent %s: %s",
                getattr(self, "agent_id", ""),
                exc,
                exc_info=True,
            )

    def _apply_mortality(self, dt: float) -> None:
        """Advance mortality. A failed update is logged and does not cancel death."""
        mortality = getattr(self, "mortality_system", None)
        update = getattr(mortality, "update", None)
        if mortality is None or not callable(update):
            logger.warning(
                "mortality update skipped for agent %s: mortality system is missing",
                getattr(self, "agent_id", ""),
            )
            return
        try:
            energy = _coerce_finite(self.energy)
        except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as exc:
            logger.warning(
                "mortality energy unreadable for agent %s: %s",
                getattr(self, "agent_id", ""),
                exc,
            )
            energy = _coerce_finite(getattr(self, "_energy_override", 1.0), 1.0)
        try:
            wake_obj = getattr(self, "wakefulness", None)
            wakefulness = _coerce_finite(getattr(wake_obj, "wakefulness", 0.0))
        except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as exc:
            logger.warning(
                "mortality wakefulness unreadable for agent %s: %s",
                getattr(self, "agent_id", ""),
                exc,
            )
            wakefulness = 0.0
        try:
            lived_steps = int(getattr(self, "lived_steps", 0) or 0)
        except (TypeError, ValueError):
            lived_steps = 0
        try:
            neuromod = getattr(self, "neuromodulators", None)
            cortisol = _coerce_finite(getattr(neuromod, "cortisol", 0.0))
        except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as exc:
            logger.warning(
                "mortality cortisol unreadable for agent %s: %s",
                getattr(self, "agent_id", ""),
                exc,
            )
            cortisol = 0.0
        age_s = _coerce_finite(getattr(self, "age", 0.0))
        dt_s = _coerce_finite(dt)
        if dt_s < 0.0:
            dt_s = 0.0
        is_dead = False
        try:
            is_dead = bool(
                update(
                    energy=energy,
                    wakefulness=wakefulness,
                    lived_steps=lived_steps,
                    cortisol_mean=cortisol,
                    biological_age_s=age_s,
                    dt_s=dt_s,
                )
            )
        except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as exc:
            logger.warning(
                "mortality update failed for agent %s; death check continues: %s",
                getattr(self, "agent_id", ""),
                exc,
                exc_info=True,
            )
            fallback = getattr(mortality, "apply_if_already_lethal", None)
            if callable(fallback):
                try:
                    is_dead = bool(
                        fallback(
                            energy=energy,
                            wakefulness=wakefulness,
                            lived_steps=lived_steps,
                            biological_age_s=age_s,
                        )
                    )
                except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as follow_exc:
                    logger.warning(
                        "mortality lethal fallback failed for agent %s: %s",
                        getattr(self, "agent_id", ""),
                        follow_exc,
                        exc_info=True,
                    )
        if not is_dead:
            is_dead_fn = getattr(mortality, "is_dead", None)
            if callable(is_dead_fn):
                try:
                    is_dead = bool(is_dead_fn())
                except (TypeError, ValueError, AttributeError, RuntimeError):
                    is_dead = False
        if is_dead:
            self.current_action = "dead"
            self.is_sleeping = True

    def _capture_conception_genome(self, male_id: str) -> None:
        """Keep the father's genome from the moment of conception."""
        father_id = str(male_id or "").strip() or None
        father = self._find_agent_by_id(father_id)
        self._conception_father_id = father_id
        self._conception_father_name = str(getattr(father, "name", "") or "") if father is not None else ""
        try:
            raw_generation = getattr(father, "generation", 0) if father is not None else 0
            self._conception_father_generation = int(raw_generation or 0)
        except (TypeError, ValueError):
            self._conception_father_generation = 0
        genome = getattr(father, "genome", None) if father is not None else None
        self._conception_father_genome = _copy_genome(genome)

    def _clear_conception_record(self) -> None:
        self._conception_father_genome = None
        self._conception_father_id = None
        self._conception_father_name = ""
        self._conception_father_generation = 0

    def _start_pregnancy(self, male_id: str) -> None:
        self.is_pregnant = True
        self.gestation_timer = GESTATION_S
        self._current_mate_id = male_id
        self._capture_conception_genome(male_id)
        known = self.knowledge.get(male_id)
        if known is not None:
            known.is_mate = True
            known.relationship_type = "mate"
        if self.heat_cycle is not None:
            self.heat_cycle.apply_mating()

    def _give_birth(self) -> None:
        father_id = str(self._current_mate_id or "").strip() or None
        father = self._find_agent_by_id(father_id) if father_id else None
        for _ in range(choose_litter_size(self._rng)):
            offspring = self._create_offspring(father, father_id_hint=father_id)
            self.pending_offspring_list.append(offspring)
            self.own_offspring.append(offspring.agent_id)
            if father is not None and offspring.agent_id not in getattr(father, "own_offspring", []):
                father.own_offspring.append(offspring.agent_id)
        self.is_pregnant = False
        self.gestation_timer = 0.0
        self._current_mate_id = None
        self._clear_conception_record()
        self._apply_affect_impulse(valence=0.5, attachment=0.8, intensity=0.7)
        try:
            self.reproductive_system.register_reproduction(self.lived_steps)
        except Exception:
            pass
        if father is not None:
            try:
                father.reproductive_system.register_reproduction(father.lived_steps)
            except Exception:
                pass

    def _create_offspring(
        self,
        father: "ChinchillaAgent" | None,
        *,
        father_id_hint: str | None = None,
    ) -> "ChinchillaAgent":
        father_id = father.agent_id if father is not None else (str(father_id_hint or "").strip() or None)
        # Child generation should be max(parent1.generation, parent2.generation) + 1
        try:
            mother_gen = int(getattr(self, "generation", 0) or 0)
        except Exception:
            mother_gen = 0
        if father is not None:
            raw_father_gen = getattr(father, "generation", 0)
        else:
            raw_father_gen = getattr(self, "_conception_father_generation", 0)
        try:
            father_gen = int(raw_father_gen or 0)
        except (TypeError, ValueError):
            father_gen = 0
        child_generation = max(mother_gen, father_gen) + 1

        offspring = ChinchillaAgent(
            sex=self._rng.choice(["M", "F"]),
            age=0.0,
            generation=child_generation,
            parents=(self.agent_id, father_id),
            colony=self.colony,
            resources=self.resources,
            is_mature=False,
            rng=self._rng,
            physiology_as_policy=bool(self.physiology_as_policy),
        )
        offspring._inherit_nowa_from(self, father)

        offspring.knowledge[self.agent_id] = KnownAgent(
            agent_id=self.agent_id,
            name=self.name,
            sex=self.sex,
            last_seen_position=self.position,
            last_seen_time=offspring.sim_time,
            affinity=0.9,
            dominance_felt=-0.8,
            relationship_type="kin",
            familiarity=0.9,
            memory_confidence=1.0,
            position_confidence=1.0,
        )
        if father is not None:
            offspring.knowledge[father.agent_id] = KnownAgent(
                agent_id=father.agent_id,
                name=father.name,
                sex=father.sex,
                last_seen_position=father.position,
                last_seen_time=offspring.sim_time,
                affinity=0.7,
                dominance_felt=-0.6,
                relationship_type="kin",
                familiarity=0.7,
                memory_confidence=1.0,
                position_confidence=1.0,
            )

        self.knowledge[offspring.agent_id] = KnownAgent(
            agent_id=offspring.agent_id,
            name=offspring.name,
            sex=offspring.sex,
            last_seen_position=self.position,
            last_seen_time=self.sim_time,
            affinity=0.9,
            relationship_type="kin",
            familiarity=0.9,
        )
        if father is not None:
            father.knowledge[offspring.agent_id] = KnownAgent(
                agent_id=offspring.agent_id,
                name=offspring.name,
                sex=offspring.sex,
                last_seen_position=father.position,
                last_seen_time=father.sim_time,
                affinity=0.8,
                relationship_type="kin",
                familiarity=0.8,
            )
        return offspring

    def _inherit_nowa_from(
        self,
        mother: "ChinchillaAgent",
        father: "ChinchillaAgent | None",
    ) -> None:
        """Mendelian genome plus the kit's own starting physiology.

        Each gene is copied whole from one parent (uniform crossover), then
        mutated. Momentary neuromodulator levels, affective decay, and the
        parents' current social drive are not copied: decay and drive
        baselines are written from the recombined genome, and levels stay at
        the constructor baselines. Energy is the rested neonatal start, not
        the mean of the parents' current balance.
        """
        paternal_genome = _father_genome_for_birth(mother, father)
        if mother.genome is not None and paternal_genome is not None:
            try:
                recombined, _ = mother.genome.crossover(
                    paternal_genome,
                    mode="uniform",
                    rng=self._rng,
                )
                pre_genes = dict(getattr(recombined, "genes", {}) or {})
                child_genome = recombined.mutate(rate=0.05, rng=self._rng)
                self.genome = child_genome
                self.mortality_system.max_lifespan_age_s = _colony_max_lifespan_age_s(self.genome)
                mother_id = str(getattr(mother, "agent_id", "") or "")
                father_id = str(
                    getattr(father, "agent_id", "")
                    or getattr(mother, "_conception_father_id", "")
                    or ""
                )
                mother_name = str(getattr(mother, "name", "") or mother_id)
                father_name = str(
                    getattr(father, "name", "")
                    or getattr(mother, "_conception_father_name", "")
                    or father_id
                )
                eps = 1e-9
                midpoint_abs_shift_sum = 0.0
                mother_weight_sum = 0.0
                father_weight_sum = 0.0
                reconstructed_genes = 0
                per_gene_shift: list[tuple[str, float]] = []
                mother_genes = getattr(mother.genome, "genes", {}) or {}
                father_genes = getattr(paternal_genome, "genes", {}) or {}
                for key, child_val in (getattr(child_genome, "genes", {}) or {}).items():
                    m_val = float(mother_genes.get(key, child_val))
                    f_val = float(father_genes.get(key, child_val))
                    c_val = float(child_val)
                    allele = float(pre_genes.get(key, c_val))
                    midpoint = (m_val + f_val) / 2.0
                    shift = c_val - midpoint
                    midpoint_abs_shift_sum += abs(shift)
                    per_gene_shift.append((str(key), shift))
                    span = f_val - m_val
                    if abs(span) <= eps:
                        continue
                    mother_weight = max(0.0, min(1.0, (f_val - allele) / span))
                    father_weight = 1.0 - mother_weight
                    mother_weight_sum += mother_weight
                    father_weight_sum += father_weight
                    reconstructed_genes += 1
                top_shifted = sorted(per_gene_shift, key=lambda item: abs(float(item[1])), reverse=True)[:8]
                mother_distance = float(child_genome.distance(mother.genome))
                father_distance = float(child_genome.distance(paternal_genome))
                self.genome_inheritance_meta = {
                    "mode": "recombined",
                    "mother_id": mother_id,
                    "father_id": father_id,
                    "mother_name": mother_name,
                    "father_name": father_name,
                    "lineage_id": str(getattr(child_genome, "lineage_id", "") or ""),
                    "crossover_mode": "uniform",
                    "mutation_rate": 0.05,
                    "gene_count": int(len((getattr(child_genome, "genes", {}) or {}))),
                    "reconstructed_genes": int(reconstructed_genes),
                    "mother_contrib_mean": (
                        float(mother_weight_sum / reconstructed_genes) if reconstructed_genes > 0 else 0.5
                    ),
                    "father_contrib_mean": (
                        float(father_weight_sum / reconstructed_genes) if reconstructed_genes > 0 else 0.5
                    ),
                    "mean_abs_midpoint_shift": (
                        float(midpoint_abs_shift_sum / max(1, len(per_gene_shift)))
                    ),
                    "distance_to_mother": mother_distance,
                    "distance_to_father": father_distance,
                    "top_shifted_genes": [
                        {"gene": key, "midpoint_shift": float(shift)}
                        for key, shift in top_shifted
                    ],
                }

                params = child_genome.to_agent_params()
                from agent_factory import AgentConfig as LocalAgentConfig
                from agent_factory import AgentFactory as LocalAgentFactory

                with initializing():
                    LocalAgentFactory(
                        LocalAgentConfig(actions=list(self.base_abilities))
                    )._apply_genome_to_agent(
                        self, params
                    )
            except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError) as exc:
                logger.warning(
                    "genome recombination failed for offspring of %s: %s",
                    getattr(mother, "agent_id", ""),
                    exc,
                    exc_info=True,
                )
        else:
            logger.warning(
                "offspring of %s born without a recombined genome "
                "(mother_genome=%s, father_genome=%s, father_id=%s)",
                getattr(mother, "agent_id", ""),
                getattr(mother, "genome", None) is not None,
                paternal_genome is not None,
                getattr(father, "agent_id", None) or getattr(mother, "_conception_father_id", None),
            )
        self.energy = NEWBORN_ENERGY

    def _inherit_from(self, mother: "ChinchillaAgent", father: "ChinchillaAgent" | None) -> None:
        """Backward-compatible alias for older colony code."""
        self._inherit_nowa_from(mother, father)

    def _find_agent_by_id(self, agent_id: str | None) -> "ChinchillaAgent" | None:
        if agent_id is None:
            return None
        for agent in self.colony:
            if agent.agent_id == agent_id:
                return agent
        return None

    def _apply_frustration(self, reason: str) -> None:
        self.frustration_events.append(reason)
        self._apply_affect_impulse(stress=0.1, arousal=0.1, intensity=0.8)

    def _try_acquire_resource(self, resource: str) -> bool:
        if self.resources is None:
            return False
        if (self.is_sleeping or self.current_action == "sleep") and resource in {"food_pellets", "water"}:
            return False
        if resource in {"wheel", "dustbath"}:
            acquired = self.resources.acquire_exclusive(resource, self.agent_id)
            if not acquired:
                last_feedback = float(self._resource_block_feedback_at.get(resource, -1e9))
                if (self.sim_time - last_feedback) >= RESOURCE_BLOCK_FEEDBACK_COOLDOWN_S:
                    self._apply_frustration(f"{resource}_blocked")
                    self._resource_block_feedback_at[resource] = float(self.sim_time)
            return acquired
        if resource == "food_pellets":
            # A full sip every tick empties the shared bowl when the step is
            # shorter than the need. Drink and eat only when there is a deficit.
            if self.physiology_as_policy and not self._needs_eat_action():
                return False
            if self._food_availability() > 0.05:
                self.resources.consume_food(
                    0.003 * RESOURCE_CONSUMPTION_MULTIPLIER,
                    primary=self._food_primary_source(),
                )
                self.hunger = _clamp(self.hunger - EAT_RELIEF, 0.0, 1.0)
                return True
            self._apply_affect_impulse(stress=0.2, valence=-0.3, intensity=0.8)
            return False
        if resource == "water":
            if self.physiology_as_policy and not self._needs_drink_action():
                return False
            if self.resources.water > 0.02:
                self.resources.water = max(
                    0.0,
                    self.resources.water - (0.003 * RESOURCE_CONSUMPTION_MULTIPLIER),
                )
                self.thirst = _clamp(self.thirst - DRINK_RELIEF, 0.0, 1.0)
                return True
            self._apply_affect_impulse(stress=0.1, valence=-0.1, intensity=0.6)
            return False
        return False

    def _release_resource(self, resource: str) -> None:
        if self.resources is not None:
            self.resources.release_exclusive(resource, self.agent_id)

    def _set_position(self, zone: str) -> None:
        zone_name = str(zone)
        if not zone_name or zone_name == self.position:
            return
        if self.position == "wheel" and zone_name != "wheel":
            self._release_resource("wheel")
        self.position = zone_name
        self._last_position_change_time = float(self.sim_time)

    def _move_towards_any(
        self,
        target_zones: list[str],
        *,
        force: bool = False,
        allow_random_neighbor: bool = False,
        relocate_within_targets: bool = False,
    ) -> bool:
        if not target_zones:
            return False
        if (not force) and (self.sim_time - self._last_position_change_time) < MIN_ACTION_MOVE_INTERVAL_S:
            return False
        normalized_targets = [str(zone) for zone in target_zones if str(zone)]
        if not normalized_targets:
            return False
        neighbors = list(ADJACENT_ZONES.get(self.position, set()))
        if self.position in normalized_targets:
            if not relocate_within_targets:
                return False
            normalized_targets = [zone for zone in normalized_targets if zone != self.position]
            if not normalized_targets:
                if allow_random_neighbor and neighbors:
                    self._set_position(self._rng.choice(neighbors))
                    return True
                return False
        if neighbors:
            next_hops = self._next_hops_towards_targets(
                source=self.position,
                target_zones=normalized_targets,
            )
            if next_hops:
                self._set_position(self._rng.choice(next_hops))
                return True
        if allow_random_neighbor and neighbors:
            self._set_position(self._rng.choice(neighbors))
            return True
        return False

    def _next_hops_towards_targets(self, source: str, target_zones: list[str]) -> list[str]:
        source_zone = str(source)
        if source_zone not in ADJACENT_ZONES:
            return []
        targets = {str(zone) for zone in target_zones if str(zone)}
        if not targets:
            return []

        direct_neighbors = list(ADJACENT_ZONES.get(source_zone, set()))
        direct_hits = [zone for zone in direct_neighbors if zone in targets]
        if direct_hits:
            return direct_hits

        distances: dict[str, int] = {}
        queue: list[str] = []
        for target in targets:
            if target in ADJACENT_ZONES:
                distances[target] = 0
                queue.append(target)

        cursor = 0
        while cursor < len(queue):
            zone = queue[cursor]
            cursor += 1
            zone_distance = distances[zone]
            for neighbor in ADJACENT_ZONES.get(zone, set()):
                if neighbor in distances:
                    continue
                distances[neighbor] = zone_distance + 1
                queue.append(neighbor)

        source_distance = distances.get(source_zone)
        if source_distance is None:
            return []
        return [
            neighbor
            for neighbor in direct_neighbors
            if distances.get(neighbor, source_distance + 10_000) < source_distance
        ]

    def _unstick_position(self) -> None:
        if self.is_sleeping or self.current_action in {"sleep", "dead", "mount_display", "allogroom", "nurse"}:
            return
        if self.current_action == "run_wheel":
            wheel_owner = None if self.resources is None else self.resources.wheel_lock
            if self.position == "wheel" and wheel_owner == self.agent_id:
                return
        if (self.sim_time - self._last_position_change_time) < STUCK_MOVE_TIMEOUT_S:
            return
        self._maybe_move_position(force=True)

    def _maybe_move_position(self, *, force: bool = False) -> None:
        if (not force) and (self.sim_time - self._last_position_change_time) < MIN_ACTION_MOVE_INTERVAL_S:
            return
        neighbors = list(ADJACENT_ZONES.get(self.position, set()))
        if neighbors:
            self._set_position(self._rng.choice(neighbors))
            return
        if ADJACENT_ZONES:
            self._set_position(self._rng.choice(list(ADJACENT_ZONES.keys())))
