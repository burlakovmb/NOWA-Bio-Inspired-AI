"""
Agent - The core NOWA cognitive system.

Behavior emerges from:
1. Recent experience (hippocampus) - influenced by context
2. Consolidated patterns (cortex) - biasing toward stable behaviors
3. Intent habits (intent_memory) - preferred actions for contexts
4. Affective regulators - operational parameters for adaptation
5. Conflict resolution (selector) - confidence-based choice

While awake, a known reward writes a labile offset on Q and on that
action's Go/NoGo channel. Habit strength does not change. Sleep is the
only writer of the stable tier; it still replays episodes into stable Q
and the basal-ganglia outcome cache.
"""

import hashlib
import math
import random
import time
from typing import Any, Mapping, Optional
from experience import Event, Path, EventType
from affect import AffectiveState
from temporal import TemporalLevels
from affective_persistence import AffectivePersistenceLayer
from affective_background import AffectiveBackgroundField
from affective_space import AffectiveSpace
from semantic_emotions import SemanticEmotionsLayer
from emotional_memory_narratives import EmotionalMemoryNarrativesLayer
from emotional_expectations import EmotionalExpectationsLayer
from emotional_regulation import EmotionalRegulationLayer
from conflict_arbitration import ConflictArbitrationLayer
from stability_monitoring import StabilityMonitoringLayer
from neuromodulators import NeuromodulatorState
from wakefulness import WakefulnessState
from basal_ganglia import BasalGangliaGate, ActionChannel, BasalGangliaLearning, ThalamicGate, NO_ACTION
from value_layer import ValueLayer, state_similarity
from labile_layer import LabileLayer, PlasticityConfig
import logging as _nowa_logging
from hippocampal_imagine_engine import HippocampalImagineEngine, quantile
from decision_arbitrator import DecisionArbitrator
from external_interaction_layer import (
    AsyncInteractionScheduler,
    ExternalAction,
    ExternalInteractionLayer,
    Feedback,
    Hypothesis,
    Observation,
)
try:
    from autonomous_organism import (
        AutonomousOrganismAgent as _AutonomousOrganismAgent,
        DriveSystem as _DriveSystem,
        EnergySystem as _EnergySystem,
        OrganismHardLimits as _OrganismHardLimits,
        InternalSimulationLoop as _InternalSimulationLoop,
        SpeechGovernor as _SpeechGovernor,
    )
except Exception:
    _AutonomousOrganismAgent = None
    _DriveSystem = None
    _EnergySystem = None
    _OrganismHardLimits = None
    _InternalSimulationLoop = None
    _SpeechGovernor = None


class Agent:
    """
    NOWA Agent.

    During waking:
    - Experiences are stored and addressed by episode id
    - Behavior emerges from memory, habits, and effective action values
      (stable + labile)
    - A known reward writes a labile Q tag and a labile Go/NoGo tag
    - Habit strength is unchanged; an empty strength-0 trace may be noted
    - An unknown reward waits for apply_feedback_to_last_experience

    During sleep:
    - Experiences are consolidated to patterns
    - Memories are organized and abstracted
    - Unstable traces fade
    """
    
    def __init__(
        self,
        hippocampus,
        cortex,
        selector,
        sleep_manager=None,
        intent_memory=None,
        affect_state=None,
        prediction_layer=None,
        environment_interface=None,
        external_interaction_layer=None,
        rng_seed: Optional[int] = None,
        plasticity_config: Optional[PlasticityConfig] = None,
    ):
        """
        Initialize agent
        
        Args:
            hippocampus: NOWAHippocampus instance
            cortex: CortexMemory instance
            selector: ActionSelector instance
            sleep_manager: SleepManager instance (optional)
            intent_memory: IntentMemory instance (optional)
            affect_state: AffectiveState instance (optional, created if None)
        """
        self.hippocampus = hippocampus
        self.cortex = cortex
        self.selector = selector
        self.sleep_manager = sleep_manager
        self.intent_memory = intent_memory
        self.affect_state = affect_state or AffectiveState()
        # Phase 3.5: Affective persistence layer (durable traces)
        self.affective_persistence = AffectivePersistenceLayer()
        # Phase 3.75: Affective background field (slow inertial background)
        self.affective_background = AffectiveBackgroundField()
        # Phase 4 (pre): Affective Space (continuous multidimensional state)
        self.affective_space = AffectiveSpace()
        # Phase 4.1: Semantic emotions (interpretation of affective space)
        self.semantic_emotions = SemanticEmotionsLayer()
        # Phase 4.2: Emotional memory & narratives (retrospective only)
        self.emotional_memory = EmotionalMemoryNarrativesLayer()
        # Phase 4.3: Emotional expectations (prospective only)
        self.emotional_expectations = EmotionalExpectationsLayer()
        # Phase 4.4: Regulation based on emotional expectations (stabilization only)
        self.emotional_regulation = EmotionalRegulationLayer()
        # Phase 4.6: ACC-like conflict arbitration (control regime only)
        self.conflict_arbitration = ConflictArbitrationLayer()
        # Phase 4.5: Read-only stability monitoring & drift diagnostics
        self.stability_monitor = StabilityMonitoringLayer()
        # Phase 5.0: Value layer (TD learning over state value)
        self.value_layer = ValueLayer()
        # Spec-011: Decision arbitration layer.
        self.decision_arbitrator = DecisionArbitrator()
        # Neuromodulators state (slow-changing global modulators)
        self.neuromodulators = NeuromodulatorState()
        # Wakefulness state (physiological sleep-wake regulation)
        self.wakefulness = WakefulnessState()
        # Temporal levels manager (T0/T1/T2/T3)
        self.temporal = TemporalLevels()
        # Phase 3: Basal Ganglia gate (action choice mechanism)
        self.basal_ganglia = BasalGangliaGate(temperature=1.0, threshold=0.0)
        self.thalamic_gate = ThalamicGate(base_temperature=0.35, min_temperature=0.03, ne_gain=0.8)
        self.bg_learning = BasalGangliaLearning(learning_rate=0.05)
        self.bg_action_channels: dict = {}  # {action_id: ActionChannel}
        self.organ_risks: dict = {}  # tool_id -> risk string; mind does not import MCP
        self.bg_sleep_memories: dict = {}  # {action_id: [(outcome, da, cort, serotonin), ...]} for learning
        selector_actions = getattr(self.selector, "actions", [])
        try:
            action_iterable = list(selector_actions) if isinstance(selector_actions, (list, tuple, set)) else []
        except Exception:
            action_iterable = []
        for action_name in action_iterable:
            self.register_action_channel(str(action_name))
        # If sleep manager provided, attach temporal and affect_state for consolidation
        if self.sleep_manager is not None:
            try:
                setattr(self.sleep_manager, "temporal", self.temporal)
                setattr(self.sleep_manager, "affect_state", self.affect_state)
                # Attach neuromodulators for indirect influence during sleep
                setattr(self.sleep_manager, "neuromodulators", self.neuromodulators)
                # Phase 5.A.1 replay consolidation inputs
                setattr(self.sleep_manager, "value_layer", self.value_layer)
                setattr(self.sleep_manager, "stability_monitor", self.stability_monitor)
                setattr(self.sleep_manager, "selector", self.selector)
                setattr(self.sleep_manager, "bg_action_channels", self.bg_action_channels)
                setattr(self.sleep_manager, "bg_learning", self.bg_learning)
                setattr(self.sleep_manager, "affective_space", self.affective_space)
                setattr(self.sleep_manager, "affective_background", self.affective_background)
                setattr(self.sleep_manager, "_host_agent", self)
            except Exception:
                pass
        for slow_layer in (
            self.affective_background,
            self.semantic_emotions,
            self.emotional_memory,
            self.emotional_expectations,
            self.conflict_arbitration,
        ):
            try:
                setattr(slow_layer, "_stable_owner", self)
            except Exception:
                pass
        self._last_step_time = None
        # Last action chosen by the decision pipeline, for diagnostics and for
        # hosts that call step(decision_only=True) and read the choice back.
        self.last_action: str = ""
        # Id of the episode stored by the latest step(). Feedback addresses
        # this id; hippocampal list order is not episode identity.
        self.last_episode_id: Optional[str] = None
        # Trajectory identity is separate from episode_id. episode_id addresses
        # one stored transition. A trajectory is the sequence of transitions
        # between terminal steps, and episode_step is the index inside it.
        self._trajectory_seq: int = 0
        self._trajectory_step: int = 0
        self._trajectory_id: Optional[str] = None
        self._trajectory_closed: bool = True
        # Seeded RNG for tie-breaks. Independent of PYTHONHASHSEED.
        # An explicit rng_seed also drives the thalamic softmax. Without one,
        # the gate keeps using the global random module so random.seed()
        # still reproduces older callers.
        self._rng_controls_thalamic = rng_seed is not None
        self._rng = random.Random(rng_seed) if rng_seed is not None else random.Random()
        self._action_visit_counts: dict = {}
        self._bg_outcome_slots: dict = {}
        self._pending_external_learning: list = []
        self._host_clock_s: float = 0.0
        self._dt_warning_sent: bool = False
        plasticity = plasticity_config if plasticity_config is not None else PlasticityConfig()
        if plasticity.eta_labile_q is None:
            plasticity.alpha_reference = float(getattr(self.value_layer, "alpha_default", 0.03))
        self.plasticity = plasticity
        self.labile = LabileLayer(plasticity)
        self.lost_unconsolidated = 0
        self._pending_slow_affect = []
        if self.sleep_manager is not None:
            setattr(self.sleep_manager, "labile", self.labile)
            setattr(self.sleep_manager, "plasticity", self.plasticity)
            setattr(self.sleep_manager, "_host_agent", self)
        if plasticity.expected_wake_interval_s is None:
            plasticity.warn_unset_wake_interval(_nowa_logging.getLogger("nowa.plasticity"))
        # Creation timestamp for lifetime reporting
        self.created_ts = time.time()
        # Lifetime progress for background dynamics (steps-based)
        self.lived_steps = 0
        self.expected_lifetime_steps = 10000
        # Rolling histories used by fitness evaluation diagnostics.
        self.affective_history: list[dict] = []
        self.td_error_history: list[float] = []
        self.cortisol_history: list[float] = []
        self._fitness_history_limit: int = 256
        # Optional prediction layer instance (advisory prediction contour)
        self.prediction_layer = prediction_layer
        # Track simulated sleep duration (since deep_sleep is simulated)
        self._simulated_sleep_seconds = 0.0
        # Optional autonomous-organism runtime (Spec v1), initialized lazily.
        self.autonomous_runtime = None
        self._autonomous_tick_count_offset = 0
        # External Interaction Layer: environment-facing observations/actions/feedback.
        self.environment_interface = environment_interface
        self.external_interaction_layer = (
            external_interaction_layer
            if external_interaction_layer is not None
            else ExternalInteractionLayer()
        )
        self.external_scheduler = AsyncInteractionScheduler(
            layer=self.external_interaction_layer,
            environment_interface=self.environment_interface,
        )
        self._last_conflict_arbitration_output = {}
        self._last_decision_arbitration_output: dict = {}
        self.deliberative_planning_enabled: bool = True
        self.planning_memory_scan: int = 256
        self.planning_similarity_threshold: float = 0.7
        self.planning_gain: float = 0.2
        self.planning_temperature_relief_gain: float = 0.3
        self.planning_rollout_depth: int = 3
        self.planning_rollout_samples: int = 6
        self.planning_uncertainty_depth_gain: float = 2.0
        self.planning_exploration_gain: float = 0.15
        self.planning_min_confidence: float = 0.2
        self.planning_rollout_quantile: float = 0.75
        self.planning_rollout_risk_penalty: float = 0.15
        self.planning_rollout_reward_stop_threshold: float = -2.0
        self.planning_rollout_min_discount: float = 0.03
        # HIE-002: structured hippocampal imagination controls for planning.
        self.imagination_enabled: bool = True
        self.imagination_samples: int = 8
        self.imagination_depth: int = 4
        self.imagination_branching: int = 3
        self.imagination_similarity_threshold: float = 0.6
        self.imagination_reward_decay: float = 0.9
        self.imagination_novelty_bonus: float = 0.05
        self.imagination_goal_bias: float = 0.35
        self.imagination_confidence_decay: float = 0.9
        self.imagination_state_novelty_weight: float = 0.4
        self.imagination_value_blend: float = 0.6
        self.imagination_enable_action_sequences: bool = True
        self.imagination_action_branching: int = 3
        self.imagination_max_tree_nodes: int = 128
        self.imagination_action_temperature: float = 0.7
        self.imagination_value_backup: float = 0.8
        self.imagination_max_nodes: int = 96
        self.imagination_max_graph_nodes: int = 96
        self.imagination_max_graph_edges: int = 192
        self.imagination_engine = HippocampalImagineEngine(
            samples=self.imagination_samples,
            depth=self.imagination_depth,
            branching=self.imagination_branching,
            similarity_threshold=self.imagination_similarity_threshold,
            reward_decay=self.imagination_reward_decay,
            novelty_bonus=self.imagination_novelty_bonus,
            goal_bias=self.imagination_goal_bias,
            confidence_decay=self.imagination_confidence_decay,
            state_novelty_weight=self.imagination_state_novelty_weight,
            max_nodes=self.imagination_max_nodes,
            max_graph_nodes=self.imagination_max_graph_nodes,
            max_graph_edges=self.imagination_max_graph_edges,
            max_tree_nodes=self.imagination_max_tree_nodes,
            action_temperature=self.imagination_action_temperature,
            value_backup=self.imagination_value_backup,
            rng=random.Random(0),
        )
        self._last_imagination_stats: dict = {
            "nodes_visited": 0,
            "edges_visited": 0,
            "max_depth_reached": 0,
            "novelty_hits": 0,
            "action_values_count": 0,
            "values_count": 0,
            "trajectory_count": 0,
            "confidence_mean": 0.0,
            "novelty_mean": 0.0,
        }
    
    def step(self, context_events: list, consequence: Event = None,
             intensity: float = 1.0, reward: Optional[float] = None, novelty: float = 0.0,
             conflict: float = 0.0, affective_inputs: dict = None,
             decision_only: bool = False, terminal: bool = False,
             physiological_bias: dict = None, dt: Optional[float] = None) -> str:
        """
        Execute one behavioral step.

        Stores the episode and returns the action. When ``reward`` is known,
        this step writes a labile Q offset and a labile Go/NoGo offset.
        Habit strength is not changed. ``reward=None`` leaves the labile
        write to apply_feedback_to_last_experience. Affect is updated either
        way. ``dt`` is elapsed host time in seconds. Without it, the host
        clock falls back to the wall clock once per agent and logs a warning.
        
        Decision pipeline:
        1. Check intent_memory for habits (preferred actions for context)
        2. Activate hippocampus and cortex
        3. Apply affective state modifiers to action selection
        4. Let selector choose action with intent pressure guidance
        5. Update affective state based on signals
        
        Args:
            context_events: List of context event names
            consequence: Optional consequence event
            intensity: Emotional intensity of this experience (0-2)
            reward: Outcome signal (-1.0 to +1.0). None means the outcome is
                not known yet; the labile update then waits for feedback.
            dt: Elapsed host seconds since the previous waking tick. When
                omitted, wall-clock time is used and a one-time warning is logged.
            terminal: This transition ends the episode, so the bootstrap is 0.
            novelty: Unexpectedness signal (0.0 to 1.0) for curiosity
            conflict: Conflict detection (0.0 to 1.0) for threat
            affective_inputs: Optional dict of inputs for Phase 4 affective space
            decision_only: Run the decision pipeline and return the action
                without any of the post-decision waking side effects (habit
                traces, hippocampal storage, value-layer update, affective and
                regulation updates). For embodied hosts that record the episode
                and the affective consequence themselves from the *realized*
                outcome, so that letting step() also record would duplicate the
                episode and label it with an outcome that has not happened yet.
                Defaults to False: every existing caller keeps the full step.
            physiological_bias: Optional action->pressure added before the gate.
                Embodied hosts pass drive urgency here so it is an input to the
                choice, not a replacement of it. None leaves the vector unchanged.
        
        Returns:
            Action name chosen by selector
        """
        import time
        reward, outcome_known = self._coerce_step_reward(reward)
        self._transition_terminal = bool(terminal)
        self.lived_steps += 1
        try:
            if hasattr(self, "external_interaction_layer") and self.external_interaction_layer is not None:
                self.external_interaction_layer.current_step = int(self.lived_steps)
        except Exception:
            pass
        
        # Decay affect and the labile tier on host time.
        step_elapsed = 1.0
        time_elapsed = self._advance_host_clock(dt, wall_fallback=dt is None)
        
        # Update wakefulness during waking period
        self.wakefulness.update_waking()
        
        # Get intent pressure (habits from intent_memory)
        intent_pressure = {}
        if self.intent_memory:
            intent_pressure = self.intent_memory.activate_by_context(context_events)
        
        # Get active experiences and patterns
        hip_exps = self.hippocampus.activate(context_events)
        ctx_patterns = self.cortex.activate(context_events)
        if decision_only:
            try:
                recall_vector = self.affective_space.constrained_recall_from_experiences(hip_exps)
                if recall_vector:
                    self.affective_space.step(
                        recall_vector=recall_vector,
                        time_elapsed=max(0.05, float(step_elapsed or 1.0)),
                        wakefulness=getattr(self.wakefulness, "wakefulness", 0.0),
                    )
                    self._project_legacy_affect_from_affective_space(blend=1.0)
                else:
                    self._pending_recall_impulses = []
            except Exception:
                pass
        else:
            pending_recall = self._recall_impulses_from_experiences(hip_exps)
            self._pending_recall_impulses = pending_recall
        stable_repetition = any(
            int(getattr(exp, "reinforcement_count", 0)) >= 2 for exp in list(hip_exps or [])
        )
        
        # Legacy affect_state is a compatibility projection from canonical core.
        self._project_legacy_affect_from_affective_space(blend=1.0)

        # Decision layer reads only A(t) from affective core.
        affect_modifier = self._compute_affective_space_modifier()

        cer_modulation = {
            "exploration_bias": 0.0,
            "learning_rate_scale": 1.0,
            "novelty_sensitivity_scale": 1.0,
            "decision_threshold_shift": 0.0,
            "habit_gain_scale": 1.0,
        }
        try:
            reg_snapshot_pre = (
                self.emotional_regulation.snapshot()
                if hasattr(self, "emotional_regulation") and self.emotional_regulation is not None
                else {}
            )
            cer_modulation = dict(reg_snapshot_pre.get("modulation_factors", {}) or cer_modulation)
        except Exception:
            pass
        try:
            if hasattr(self.hippocampus, "set_novelty_sensitivity_scale"):
                self.hippocampus.set_novelty_sensitivity_scale(
                    float(cer_modulation.get("novelty_sensitivity_scale", 1.0))
                )
        except Exception:
            pass

        # Compute temporal chains bias if available
        chain_bias = None
        try:
            if hasattr(self, 'sleep_manager') and getattr(self.sleep_manager, 'chain_memory', None):
                # Build recent flat sequence of event names from hippocampus
                recent = self.hippocampus.experiences[-50:]
                flat = []
                for exp in recent:
                    flat.extend(list(exp.path.signature()))
                chain_bias = self.sleep_manager.chain_memory.match_bias(flat)
        except Exception:
            chain_bias = None

        # Compute Plan C advisory pressures (read-only inputs)
        prediction_pressure = None
        try:
            if self.prediction_layer is not None:
                # recent flat sequence used for prediction layer as well
                recent = getattr(self.hippocampus, 'experiences', [])[-50:]
                flat = []
                for exp in recent:
                    flat.extend(list(exp.path.signature()))

                # Build minimal context dict for prediction layer
                context_dict = {"context_events": context_events}
                temporal_levels = getattr(self, 'temporal', None)
                prediction_pressure = self.prediction_layer.predict(
                    context=context_dict,
                    recent_events=flat,
                    affect_state=self.affect_state,
                    neuromodulators=self.neuromodulators,
                    temporal_levels=(temporal_levels.get_levels() if temporal_levels is not None else None)
                )
        except Exception:
            prediction_pressure = None

        # Mandatory decision pipeline:
        # ActionSelector.compute_pressures -> BG.process -> ThalamicGate.select.
        pressure_vector = self._extract_selector_pressures(
            hip_exps=hip_exps,
            ctx_patterns=ctx_patterns,
            intent_pressure=intent_pressure,
            affect_modifier=affect_modifier,
            chain_bias=chain_bias,
            prediction_pressure=prediction_pressure,
        )
        # Bootstrap weak context-conditioned pressure when cognitive evidence
        # is absent. This keeps behavior responsive to context while still
        # allowing NO_ACTION in fully neutral/no-input states.
        if (
            isinstance(pressure_vector, dict)
            and pressure_vector
            and not any(abs(float(v)) > 1e-12 for v in pressure_vector.values())
            and list(context_events or [])
        ):
            selector_actions = getattr(self.selector, "actions", [])
            try:
                action_candidates = list(selector_actions) if isinstance(selector_actions, (list, tuple, set)) else []
            except Exception:
                action_candidates = []
            if action_candidates:
                # Equal optimistic prior plus a stable, seeded tie-break.
                # Built-in hash() is salted per process (PYTHONHASHSEED) and
                # then locked in by later frequency pressure.
                key = "|".join(str(x) for x in list(context_events or []))
                ordered = sorted(
                    str(action_name)
                    for action_name in action_candidates
                    if str(action_name) in pressure_vector
                )
                for action_name in ordered:
                    pressure_vector[action_name] = self._stable_bootstrap_prior(key, action_name)
        pressure_vector = self._modulate_pressures_for_organs(pressure_vector)
        effective_modulation = dict(cer_modulation or {})
        acc_output = {}
        cer_stress_level = 0.0
        try:
            policy_metrics_pre = self._compute_policy_metrics_from_pressure(pressure_vector)
            pattern_completion_confidence = self._estimate_pattern_completion_confidence(
                context_events=context_events,
                hip_exps=hip_exps,
            )
            wm_load = self._estimate_working_memory_load(
                context_events=context_events,
                hip_exps=hip_exps,
                ctx_patterns=ctx_patterns,
                pressure_vector=pressure_vector,
            )
            task_complexity = max(
                0.0,
                min(
                    1.0,
                    (0.55 * wm_load)
                    + (0.25 * float(policy_metrics_pre.get("policy_entropy", 0.0)))
                    + (0.20 * max(0.0, min(1.0, float(novelty or 0.0)))),
                ),
            )
            td_error_pre = 0.0
            try:
                value_snapshot_pre = (
                    self.value_layer.snapshot()
                    if hasattr(self, "value_layer") and self.value_layer is not None
                    else {}
                )
                td_error_pre = float(value_snapshot_pre.get("last_td_error", 0.0))
            except Exception:
                td_error_pre = 0.0

            reg_arousal = 0.0
            reg_valence = 0.0
            try:
                axes_now = dict(getattr(self.affective_space, "axes", {}) or {})
                reg_valence = float(axes_now.get("valence", 0.0))
                reg_arousal = max(0.0, min(1.0, (float(axes_now.get("arousal", 0.0)) + 1.0) / 2.0))
            except Exception:
                try:
                    reg_arousal = float(reg_snapshot_pre.get("arousal", 0.0))
                    reg_valence = float(reg_snapshot_pre.get("valence", 0.0))
                except Exception:
                    reg_arousal = 0.0
                    reg_valence = 0.0

            cer_stress_level = float(self._compute_bg_aversive_signal())
            acc_output = self.conflict_arbitration.arbitrate(
                go_signals=list((pressure_vector or {}).values()),
                top2_gap=float(policy_metrics_pre.get("top2_gap", 0.0)),
                policy_entropy=float(policy_metrics_pre.get("policy_entropy", 0.0)),
                decision_latency=float(policy_metrics_pre.get("decision_latency", 0.0)),
                threshold_current=float(getattr(self.basal_ganglia, "threshold", 0.0))
                + float(cer_modulation.get("decision_threshold_shift", 0.0)),
                arousal=reg_arousal,
                stress_level=cer_stress_level,
                valence=reg_valence,
                novelty_score=float(max(0.0, min(1.0, novelty))),
                pattern_completion_confidence=float(pattern_completion_confidence),
                prediction_error=float(td_error_pre),
                working_memory_load=float(wm_load),
                task_complexity=float(task_complexity),
            )

            cer_threshold_shift = max(-0.5, min(0.8, float(cer_modulation.get("decision_threshold_shift", 0.0))))
            combined_threshold_shift_raw = cer_threshold_shift + float(acc_output.get("threshold_delta", 0.0))
            # Prevent CER+ACC resonance from over-suppressing action gating.
            threshold_shift = max(-0.35, min(0.60, combined_threshold_shift_raw))

            mode = str(acc_output.get("control_mode", "balanced"))
            exploration_bias = float(cer_modulation.get("exploration_bias", 0.0))
            if bool(acc_output.get("exploration_override", False)):
                exploration_bias = max(exploration_bias, 0.95)
            if mode == "inhibit":
                exploration_bias = min(exploration_bias, 0.20)
            exploration_before_td = max(0.0, exploration_bias)
            td_exploration_delta = 0.0
            try:
                if hasattr(self, "value_layer") and self.value_layer is not None:
                    td_exploration_delta = float(
                        self.value_layer.compute_exploration_coupling(
                            td_error=td_error_pre,
                            baseline_exploration=exploration_before_td,
                        )
                    )
            except Exception:
                td_exploration_delta = 0.0

            # Guardrail against rapid collapse from stacked ACC/CER/TD modulation.
            td_step_limit = max(0.02, 0.5 * max(0.05, exploration_before_td))
            td_exploration_delta = max(-td_step_limit, min(td_step_limit, td_exploration_delta))
            exploration_bias = exploration_before_td + td_exploration_delta
            if mode == "inhibit":
                exploration_bias = max(0.05, min(0.20, exploration_bias))
            else:
                exploration_bias = max(0.0, min(1.5, exploration_bias))

            habit_gain_scale = float(cer_modulation.get("habit_gain_scale", 1.0))
            if mode == "habitual":
                habit_gain_scale *= 1.10
            elif mode == "deliberative":
                habit_gain_scale *= 0.88
            elif mode == "inhibit":
                habit_gain_scale *= 0.78
            habit_gain_scale = max(0.7, min(1.6, habit_gain_scale))

            acc_control_gain = float(acc_output.get("control_gain_multiplier", 1.0))
            metrics = dict(acc_output.get("metrics", {}) or {})
            acc_error_likelihood = max(0.0, min(1.0, float(metrics.get("error_likelihood", 0.0))))
            if acc_error_likelihood <= 0.35:
                acc_learning_boost = 1.0
            else:
                acc_learning_boost = 1.0 + (0.45 * ((acc_error_likelihood - 0.35) / 0.65))
            cer_stress_alpha_scale = max(0.2, 1.0 - (0.5 * max(0.0, min(1.0, cer_stress_level))))
            learning_rate_scale = float(cer_modulation.get("learning_rate_scale", 1.0)) * acc_learning_boost
            learning_rate_scale = max(0.5, min(2.0, learning_rate_scale))

            effective_modulation.update(
                {
                    "exploration_bias": float(exploration_bias),
                    "td_exploration_delta": float(td_exploration_delta),
                    "exploration_before_td": float(exploration_before_td),
                    "td_exploration_step_limit": float(td_step_limit),
                    "decision_threshold_shift": float(threshold_shift),
                    "habit_gain_scale": float(habit_gain_scale),
                    "learning_rate_scale": float(learning_rate_scale),
                    "control_mode": mode,
                    "wm_boost_flag": bool(acc_output.get("wm_boost_flag", False)),
                    "control_gain_multiplier": float(acc_control_gain),
                    "acc_error_likelihood": float(acc_error_likelihood),
                    "acc_learning_boost": float(acc_learning_boost),
                    "cer_stress_level": float(cer_stress_level),
                    "cer_stress_alpha_scale": float(cer_stress_alpha_scale),
                    "threshold_shift_combined_raw": float(combined_threshold_shift_raw),
                    "request_additional_evaluation": bool(
                        acc_output.get("request_additional_evaluation", False)
                    ),
                }
            )
        except Exception:
            acc_output = {}

        self._last_conflict_arbitration_output = dict(acc_output or {})
        decision_state = {}
        try:
            value_snapshot_pre = (
                self.value_layer.snapshot()
                if hasattr(self, "value_layer") and self.value_layer is not None
                else {}
            )
            decision_state = {
                "expected_reward_mean": float(value_snapshot_pre.get("last_expected_reward_mean", 0.0)),
                "edpc_predictions": value_snapshot_pre.get("edpc_predictions"),
            }
        except Exception:
            decision_state = {}

        action_stability_values = []
        try:
            for action_id in list((pressure_vector or {}).keys()):
                meta = (
                    self.selector.get_action_metadata(action_id)
                    if hasattr(self.selector, "get_action_metadata")
                    else {}
                )
                if not isinstance(meta, Mapping):
                    continue
                if not bool(meta.get("consolidated", meta.get("consolidation_flag", False))):
                    continue
                action_stability_values.append(
                    float(meta.get("stability_score", meta.get("stability", 0.0)))
                )
        except Exception:
            action_stability_values = []

        causality_mean = None
        try:
            if self.sleep_manager is not None:
                last_stats = getattr(self.sleep_manager, "last_sleep_replay_stats", {}) or {}
                if "replay_causality_mean" in last_stats:
                    causality_mean = float(last_stats.get("replay_causality_mean", 0.0))
        except Exception:
            causality_mean = None

        action_stability_mean = None
        if action_stability_values:
            action_stability_mean = sum(action_stability_values) / float(len(action_stability_values))

        decision_output = {}
        try:
            decision_output = self.decision_arbitrator.arbitrate(
                pressure_vector=pressure_vector,
                action_metadata=getattr(self.selector, "action_metadata", {}),
                error_likelihood=float(getattr(self.value_layer, "last_error_likelihood", 0.5)),
                surprise=float(getattr(self.value_layer, "last_surprise", 0.0)),
                stress_level=float(cer_stress_level),
                action_stability_mean=action_stability_mean,
                causality_mean=causality_mean,
            )
        except Exception:
            decision_output = {}

        decision_mode = str(decision_output.get("decision_mode", "HABITUAL"))
        policy_temperature = float(
            decision_output.get(
                "policy_temperature",
                getattr(self.thalamic_gate, "base_temperature", 0.35),
            )
        )
        try:
            axes_plan = dict(getattr(self.affective_space, "axes", {}) or {})
            curiosity = float(axes_plan.get("curiosity", 0.0))
            stress = float(axes_plan.get("stress", 0.0))
            policy_temperature = max(
                0.05,
                min(2.5, policy_temperature * (1.0 + 0.35 * max(0.0, curiosity) - 0.25 * max(0.0, stress))),
            )
        except Exception:
            pass
        global_uncertainty = float(decision_output.get("global_uncertainty", 0.0))
        global_uncertainty_raw = float(decision_output.get("global_uncertainty_raw", global_uncertainty))
        uncertainty_ema = float(decision_output.get("uncertainty_ema", global_uncertainty))
        policy_reliability = float(decision_output.get("policy_reliability", 1.0))
        if isinstance(decision_state, dict):
            decision_state["global_uncertainty"] = float(global_uncertainty)
            decision_state["uncertainty_ema"] = float(uncertainty_ema)
        planning_metadata: Mapping[str, Any] = {
            "planning_bias_applied": False,
            "supported_actions": 0,
            "support_mean": 0.0,
            "rollout_depth": 0,
            "rollout_samples": 0,
            "rollout_used": 0,
            "exploration_bonus_mean": 0.0,
            "imagination_enabled": bool(getattr(self, "imagination_enabled", True)),
            "imagination_samples": int(max(1, min(8, int(getattr(self, "imagination_samples", 8))))),
            "imagination_depth": int(max(1, min(5, int(getattr(self, "imagination_depth", 4))))),
            "imagination_action_sequences_enabled": bool(
                getattr(self, "imagination_enable_action_sequences", True)
            ),
            "imagination_branching": int(
                max(1, min(4, int(getattr(self, "imagination_action_branching", 3))))
            ),
            "imagined_rollouts_used": 0,
            "imagined_value_mean": 0.0,
            "imagined_value_max": 0.0,
            "imagined_trajectory_count": 0,
            "imagined_confidence_mean": 0.0,
            "imagined_novelty_mean": 0.0,
            "imagination_novelty_hits": 0,
            "imagination_tree_nodes": 0,
            "imagination_tree_edges": 0,
            "imagination_action_count": 0,
        }
        try:
            if str(decision_mode).upper() == "DELIBERATIVE":
                pressure_vector, planning_metadata = self._apply_deliberative_planning(
                    pressure_vector=pressure_vector,
                    context_events=context_events,
                    intensity=float(intensity),
                    novelty=float(novelty),
                    conflict=float(conflict),
                    decision_state=decision_state,
                )
        except Exception:
            planning_metadata = {
                "planning_bias_applied": False,
                "supported_actions": 0,
                "support_mean": 0.0,
                "rollout_depth": 0,
                "rollout_samples": 0,
                "rollout_used": 0,
                "exploration_bonus_mean": 0.0,
                "imagination_enabled": bool(getattr(self, "imagination_enabled", True)),
                "imagination_samples": int(max(1, min(8, int(getattr(self, "imagination_samples", 8))))),
                "imagination_depth": int(max(1, min(5, int(getattr(self, "imagination_depth", 4))))),
                "imagination_action_sequences_enabled": bool(
                    getattr(self, "imagination_enable_action_sequences", True)
                ),
                "imagination_branching": int(
                    max(1, min(4, int(getattr(self, "imagination_action_branching", 3))))
                ),
                "imagined_rollouts_used": 0,
                "imagined_value_mean": 0.0,
                "imagined_value_max": 0.0,
                "imagined_trajectory_count": 0,
                "imagined_confidence_mean": 0.0,
                "imagined_novelty_mean": 0.0,
                "imagination_novelty_hits": 0,
                "imagination_tree_nodes": 0,
                "imagination_tree_edges": 0,
                "imagination_action_count": 0,
            }

        planning_temp_factor = 1.0

        try:
            if str(decision_mode).upper() == "DELIBERATIVE":
                self.thalamic_gate.base_temperature = float(policy_temperature)
        except Exception:
            pass

        similar_state_count = 0
        try:
            similar_state_count = int(
                getattr(self.value_layer, "last_similar_state_count", 0)
            )
        except Exception:
            similar_state_count = 0
        self._last_decision_arbitration_output = {
            "decision_mode": decision_mode,
            "global_uncertainty": global_uncertainty,
            "global_uncertainty_raw": global_uncertainty_raw,
            "uncertainty_ema": uncertainty_ema,
            "policy_temperature": policy_temperature,
            "policy_reliability": policy_reliability,
            "similar_state_count": similar_state_count,
            "planning_bias_applied": bool(planning_metadata.get("planning_bias_applied", False)),
            "planning_supported_actions": int(planning_metadata.get("supported_actions", 0)),
            "planning_support_mean": float(planning_metadata.get("support_mean", 0.0)),
            "planning_rollout_depth": int(planning_metadata.get("rollout_depth", 0)),
            "planning_rollout_samples": int(planning_metadata.get("rollout_samples", 0)),
            "planning_rollout_used": int(planning_metadata.get("rollout_used", 0)),
            "planning_exploration_bonus_mean": float(
                planning_metadata.get("exploration_bonus_mean", 0.0)
            ),
            "planning_imagination_enabled": bool(
                planning_metadata.get("imagination_enabled", False)
            ),
            "planning_imagination_samples": int(
                planning_metadata.get("imagination_samples", 0)
            ),
            "planning_imagination_depth": int(
                planning_metadata.get("imagination_depth", 0)
            ),
            "planning_imagined_rollouts_used": int(
                planning_metadata.get("imagined_rollouts_used", 0)
            ),
            "planning_imagined_value_mean": float(
                planning_metadata.get("imagined_value_mean", 0.0)
            ),
            "planning_imagined_value_max": float(
                planning_metadata.get("imagined_value_max", 0.0)
            ),
            "planning_imagined_trajectory_count": int(
                planning_metadata.get("imagined_trajectory_count", 0)
            ),
            "planning_imagined_confidence_mean": float(
                planning_metadata.get("imagined_confidence_mean", 0.0)
            ),
            "planning_imagined_novelty_mean": float(
                planning_metadata.get("imagined_novelty_mean", 0.0)
            ),
            "planning_imagination_novelty_hits": int(
                planning_metadata.get("imagination_novelty_hits", 0)
            ),
            "planning_imagination_tree_nodes": int(
                planning_metadata.get("imagination_tree_nodes", 0)
            ),
            "planning_imagination_tree_edges": int(
                planning_metadata.get("imagination_tree_edges", 0)
            ),
            "planning_imagination_action_count": int(
                planning_metadata.get("imagination_action_count", 0)
            ),
            "planning_imagination_branching": int(
                planning_metadata.get("imagination_branching", 0)
            ),
            "planning_temperature_factor": float(planning_temp_factor),
        }
        pressure_vector = self._blend_learned_action_values(
            pressure_vector,
            context_events=context_events,
            intensity=float(intensity),
            novelty=float(novelty),
            conflict=float(conflict),
        )
        if physiological_bias:
            for bias_key, bias_value in dict(physiological_bias).items():
                bias_name = str(bias_key)
                if bias_name not in pressure_vector:
                    continue
                try:
                    bias_delta = float(bias_value)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(bias_delta):
                    continue
                pressure_vector[bias_name] = float(pressure_vector.get(bias_name, 0.0)) + bias_delta
        # Stash counts on self so monkeypatched pipeline wrappers keep their
        # original signature. The real pipeline reads this attribute.
        self._pending_visit_counts = self._visit_counts_for(
            context_events,
            list(pressure_vector or {}),
        )
        action = self._select_action_via_basal_ganglia_pipeline(
            pressure_vector,
            cer_modulation_factors=effective_modulation,
        )
        # NO_ACTION is the gate's answer. Do not replace it with argmax(pressure).

        self.last_action = action
        self._record_action_visit(context_events, action)
        self._pending_commit_context = {
            "stable_repetition": stable_repetition,
            "effective_modulation": effective_modulation,
            "step_elapsed": step_elapsed,
            "time_elapsed": time_elapsed,
        }
        if decision_only:
            return action

        path = Path()
        for item in context_events:
            path = path.add_event(Event(item, event_type=EventType.CONTEXT))
        return self._commit_waking_transition(
            action=action,
            context_events=context_events,
            consequence=consequence,
            intensity=intensity,
            reward=reward,
            outcome_known=outcome_known,
            novelty=novelty,
            conflict=conflict,
            affective_inputs=affective_inputs,
            step_elapsed=step_elapsed,
            time_elapsed=time_elapsed,
            stable_repetition=stable_repetition,
            path=path,
            effective_modulation=effective_modulation,
            decided_action=action,
            overridden=False,
            override_source=None,
        )

    def _coerce_step_reward(self, reward):
        """Return (reward, outcome_known).

        Shared non-finite rule with feedback: ``None``, non-numeric values
        and NaN are unknown (no labile tag, no episode outcome). ±inf is ±1.
        Finite rewards are kept on the host's scale. Feedback then maps a
        finite value through the rating scale [-2, 2] / 2, keeping fractions.
        """
        if reward is None or isinstance(reward, bool):
            return 0.0, False
        try:
            reward = float(reward)
        except (TypeError, ValueError):
            return 0.0, False
        if math.isnan(reward):
            return 0.0, False
        if not math.isfinite(reward):
            return (1.0 if reward > 0.0 else -1.0), True
        return reward, True

    def _coerce_feedback_rating(self, feedback_rating):
        """Return (rating, reward_signal) or None when the rating is unknown.

        NaN and non-numeric ratings are unknown: the episode is left as it
        was. ±inf becomes reward ±1 (rating ±2). A finite number is kept
        as a float, clamped to [-2, 2], and the reward is rating/2.
        """
        if feedback_rating is None or isinstance(feedback_rating, bool):
            return None
        try:
            numeric = float(feedback_rating)
        except (TypeError, ValueError):
            return None
        if math.isnan(numeric):
            return None
        if math.isinf(numeric):
            rating = 2.0 if numeric > 0.0 else -2.0
            return rating, (1.0 if numeric > 0.0 else -1.0)
        rating = max(-2.0, min(2.0, numeric))
        reward_signal = rating / 2.0
        return rating, reward_signal

    def commit_executed_transition(
        self,
        action: str,
        reward: Optional[float] = None,
        *,
        context_events=None,
        decided_action: str = None,
        overridden: bool = False,
        override_source: str = None,
        novelty: float = 0.0,
        conflict: float = 0.0,
        intensity: float = 1.0,
        consequence: Event = None,
        affective_inputs: dict = None,
        terminal: bool = False,
        effective_modulation: dict = None,
        dt: Optional[float] = None,
    ) -> Optional[str]:
        """Store the executed action and, when the reward is known, tag it.

        ``step(..., decision_only=True)`` chooses without writing an episode.
        This records one episode for the executed action, including an
        ``overridden`` flag, and applies the same labile Q / channel update
        as a waking step whose reward is already known. Habit strength is
        not changed. A later feedback call with the same reward is a no-op,
        addressed by episode id. ``dt`` advances the host clock; omitted
        ``dt`` does not read the wall clock (the paired ``step`` already did).
        """
        if dt is not None:
            self._advance_host_clock(dt, wall_fallback=False)
        reward, outcome_known = self._coerce_step_reward(reward)
        self._transition_terminal = bool(terminal)
        context_events = list(context_events or [])
        path = Path()
        for item in context_events:
            path = path.add_event(Event(item, event_type=EventType.CONTEXT))
        pending = getattr(self, "_pending_commit_context", None)
        if not isinstance(pending, dict):
            pending = {}
        if effective_modulation is None:
            effective_modulation = pending.get("effective_modulation") or {}
        self._commit_waking_transition(
            action=str(action or ""),
            context_events=context_events,
            consequence=consequence,
            intensity=intensity,
            reward=reward,
            outcome_known=outcome_known,
            novelty=novelty,
            conflict=conflict,
            affective_inputs=affective_inputs,
            step_elapsed=float(pending.get("step_elapsed", 1.0) or 1.0),
            time_elapsed=float(pending.get("time_elapsed", 1.0) or 1.0),
            stable_repetition=bool(pending.get("stable_repetition", False)),
            path=path,
            effective_modulation=dict(effective_modulation or {}),
            decided_action=decided_action,
            overridden=bool(overridden),
            override_source=override_source,
        )
        return getattr(self, "last_episode_id", None)

    def _commit_waking_transition(
        self,
        *,
        action,
        context_events,
        consequence,
        intensity,
        reward,
        outcome_known,
        novelty,
        conflict,
        affective_inputs,
        step_elapsed,
        time_elapsed,
        stable_repetition,
        path,
        effective_modulation,
        decided_action,
        overridden,
        override_source,
    ) -> str:
        if (
            decided_action is not None
            and str(action or "") != str(decided_action)
            and str(action or "") != "NO_ACTION"
        ):
            self._record_action_visit(context_events, action)
        self.last_executed_action = str(action or "")
        self.last_override = {
            "overridden": bool(overridden),
            "source": None if not overridden or override_source is None else str(override_source),
            "decided_action": None if decided_action is None else str(decided_action),
            "executed_action": str(action or ""),
        }

        policy_entropy = 0.0
        try:
            probs = dict(getattr(getattr(self, "thalamic_gate", None), "last_probabilities", {}) or {})
            if probs:
                policy_entropy = -sum(
                    max(0.0, float(p)) * math.log(max(1e-12, float(p)))
                    for p in probs.values()
                    if float(p) > 0.0
                )
                max_entropy = math.log(float(max(2, len(probs))))
                if max_entropy > 0.0:
                    policy_entropy = max(0.0, min(1.0, policy_entropy / max_entropy))
                else:
                    policy_entropy = 0.0
        except Exception:
            policy_entropy = 0.0

        # Record the trace in intent_memory for habit formation
        # Include affective context for habit learning
        if self.intent_memory and action != NO_ACTION:
            # Selection is not evidence. Strength moves only when the outcome
            # is known (see apply_feedback_to_last_experience).
            if hasattr(self.intent_memory, "note_selection"):
                self.intent_memory.note_selection(context_events, action)
        
        # Add action to path
        path = path.add_event(Event(f"action:{action}", event_type=EventType.ACTION))

        # Build value-layer snapshots from task/environment state only.
        value_state_snapshot = self._build_value_state_snapshot(
            context_events=context_events,
            action=action,
            consequence=None,
            intensity=intensity,
            novelty=novelty,
            conflict=conflict,
        )
        next_context_events = list(context_events)
        if consequence is not None:
            try:
                next_context_events.append(f"consequence:{consequence.name}")
            except Exception:
                pass
        value_next_state_snapshot = self._build_value_state_snapshot(
            context_events=next_context_events,
            action="",
            consequence=consequence,
            intensity=intensity,
            novelty=novelty,
            conflict=conflict,
        )

        # Update non-reward neuromodulator dynamics before online TD update so that
        # current ACh can gate online alpha in this same step.
        ach_snapshot_for_step = float(
            getattr(getattr(self, "neuromodulators", None), "acetylcholine", 0.0)
        )
        try:
            if hasattr(self, "neuromodulators") and self.neuromodulators is not None:
                self.neuromodulators.update_from_signals(
                    reward=reward,
                    novelty=novelty,
                    conflict=conflict,
                    stable_repetition=stable_repetition,
                    use_reward_for_dopamine=False,
                )
                ach_snapshot_for_step = float(getattr(self.neuromodulators, "acetylcholine", 0.0))
        except Exception:
            ach_snapshot_for_step = float(
                getattr(getattr(self, "neuromodulators", None), "acetylcholine", 0.0)
            )
        
        # Store experience (immutable)
        base_encoding_strength = max(0.0, min(2.0, float(intensity)))
        encoding_strength = base_encoding_strength * (1.0 + (0.5 * max(0.0, min(1.0, ach_snapshot_for_step))))
        try:
            stored_experience = self.hippocampus.store(
                path,
                consequence=consequence,
                intensity=intensity,
                reward=reward,
                encoding_strength=encoding_strength,
            )
        except TypeError:
            try:
                stored_experience = self.hippocampus.store(
                    path,
                    consequence=consequence,
                    intensity=intensity,
                    reward=reward,
                )
            except TypeError:
                stored_experience = self.hippocampus.store(
                    path,
                    consequence=consequence,
                    intensity=intensity,
                )
        try:
            if stored_experience is not None:
                stored_experience.encoding_strength = float(encoding_strength)
        except Exception:
            pass
        self._note_evicted_episodes()
        if stored_experience is not None:
            self._annotate_episode_encoding(
                stored_experience,
                context_events=list(context_events or []),
                novelty=float(novelty),
                intensity=float(intensity),
            )
            self.last_episode_id = getattr(stored_experience, "episode_id", None)
            stored_experience.overridden = bool(overridden)
            stored_experience.override_source = (
                None if not overridden or override_source is None else str(override_source)
            )
            stored_experience.decided_action = str(
                action if decided_action is None else decided_action
            )
            stored_experience.executed_action = str(action)
            self._mark_transition_trajectory(
                stored_experience,
                terminal=bool(getattr(self, "_transition_terminal", False)),
            )
        try:
            if stored_experience is not None and hasattr(self, "affective_space") and self.affective_space is not None:
                create_trace = getattr(self.affective_space, "create_trace", None)
                if callable(create_trace):
                    stored_experience.emotional_trace = create_trace(
                        intensity=max(0.0, min(1.0, abs(float(reward))))
                    )
        except Exception:
            pass

        # Labile tags only. Stable Q is written later, by sleep replay.
        value_update = None
        try:
            if outcome_known:
                transition_terminal = bool(getattr(self, "_transition_terminal", False))
                value_update = self._record_known_outcome(
                    context_events=list(context_events or []),
                    action_id=str(action or ""),
                    outcome=float(reward),
                    episode=stored_experience,
                    state_snapshot=value_state_snapshot,
                    next_state_snapshot=value_next_state_snapshot,
                    next_context_events=list(next_context_events),
                    terminal=transition_terminal,
                    intensity=float(intensity),
                    novelty=float(novelty),
                    conflict=float(conflict),
                )
        except Exception:
            value_update = None
        if stored_experience is not None and not outcome_known:
            stored_experience.td_outcome_committed = False
            stored_experience.value_terminal = bool(getattr(self, "_transition_terminal", False))
            stored_experience.value_next_context_events = list(next_context_events)

        # Save replay metadata for Phase 5.A.1 sleep replay (affect-independent).
        try:
            if stored_experience is not None:
                td_snapshot = float(value_update.get("td_error", 0.0)) if value_update is not None else 0.0
                reward_snapshot = float(reward)
                salience = max(0.0, min(1.0, abs(reward_snapshot)))
                importance = max(0.0, min(1.0, abs(td_snapshot) * 0.7 + salience * 0.3))
                replay_priority = max(
                    0.0,
                    float(value_update.get("replay_priority", abs(td_snapshot))) if value_update is not None else abs(td_snapshot),
                )
                consolidation_weight = max(
                    0.0,
                    min(
                        1.0,
                        float(value_update.get("consolidation_weight", importance)) if value_update is not None else importance,
                    ),
                )
                salience = max(salience, min(1.0, replay_priority))
                importance = max(importance, consolidation_weight)
                confidence_score = max(
                    0.0,
                    min(
                        1.0,
                        float(value_update.get("confidence_score", 0.0)) if value_update is not None else 0.0,
                    ),
                )
                stability_score = max(
                    0.0,
                    min(
                        1.0,
                        float(value_update.get("stability_score", 0.0)) if value_update is not None else 0.0,
                    ),
                )
                prediction_shock = bool(value_update.get("prediction_shock", False)) if value_update is not None else False
                stored_experience.value_state_snapshot = dict(value_state_snapshot or {})
                stored_experience.value_next_state_snapshot = dict(value_next_state_snapshot or {})
                stored_experience.value_state_key = (
                    str(value_update.get("state_key", "")) if value_update is not None else ""
                )
                self._update_experience_td_statistics(stored_experience, td_snapshot)
                stored_experience.replay_salience = salience
                stored_experience.replay_importance = importance
                stored_experience.replay_priority = replay_priority
                stored_experience.consolidation_weight = consolidation_weight
                stored_experience.replay_action_id = str(action)
                stored_experience.replay_count_sleep = 0
                stored_experience.acetylcholine_snapshot = float(ach_snapshot_for_step)
                stored_experience.acetylcholine_mean_snapshot = self._acetylcholine_gate_reference()
                stored_experience.expected_reward_mean = (
                    float(value_update.get("expected_reward_mean", 0.0)) if value_update is not None else 0.0
                )
                stored_experience.expected_reward_var = (
                    float(value_update.get("expected_reward_var", 0.0)) if value_update is not None else 0.0
                )
                stored_experience.confirmation_count = (
                    float(value_update.get("confirmation_count", 0.0)) if value_update is not None else 0.0
                )
                stored_experience.expectation_confidence_score = confidence_score
                stored_experience.expectation_stability_score = stability_score
                stored_experience.prediction_shock_flag = prediction_shock
                stored_experience.prediction_shock_score = float(
                    value_update.get(
                        "prediction_shock_score",
                        1.0 if prediction_shock else 0.0,
                    )
                ) if value_update is not None else (1.0 if prediction_shock else 0.0)
                stored_experience.error_likelihood = float(
                    value_update.get("error_likelihood", 0.0)
                ) if value_update is not None else 0.0
                stored_experience.shock_replay_boost = (
                    float(value_update.get("shock_replay_boost", 1.0)) if value_update is not None else 1.0
                )
                stability_snapshot = (
                    self.stability_monitor.snapshot()
                    if hasattr(self, "stability_monitor") and self.stability_monitor is not None
                    else {}
                )
                stability_index_snapshot = float(stability_snapshot.get("stability_index", 1.0))
                threshold = float(
                    getattr(getattr(self, "sleep_manager", None), "stability_index_threshold", 0.5)
                )
                stored_experience.stability_flag = bool(stability_index_snapshot >= threshold)
        except Exception:
            pass
        
        # TD dopamine and wakefulness share one bounded impulse into the field.
        try:
            if hasattr(self, "neuromodulators") and self.neuromodulators is not None:
                impulses = {}
                if value_update is not None:
                    td_error = float(value_update.get("td_error", 0.0))
                    dopamine_delta = float(
                        self.value_layer.compute_dopamine_delta(td_error)
                        if hasattr(self, "value_layer") and self.value_layer is not None
                        else 0.0
                    )
                    impulses["dopamine"] = dopamine_delta
                    if bool(value_update.get("prediction_shock", False)):
                        impulses["cortisol"] = max(
                            0.0,
                            min(
                                0.25,
                                float(value_update.get("confidence_score", 0.0)) * 0.08,
                            ),
                        )
                if hasattr(self, "wakefulness"):
                    deltas = self.wakefulness.get_neuromodulator_deltas()
                    for key in ("dopamine", "cortisol", "norepinephrine", "serotonin"):
                        impulses[key] = float(impulses.get(key, 0.0)) + float(deltas.get(key, 0.0))
                if impulses and hasattr(self.neuromodulators, "apply_impulses"):
                    self.neuromodulators.apply_impulses(impulses)
        except Exception:
            pass

        # Log current affective snapshot to temporal levels (T0/T1)
        try:
            space_snap = {}
            try:
                space_snap = dict(getattr(self.affective_space, "snapshot", lambda: {})() or {})
            except Exception:
                space_snap = {}
            axes = dict(space_snap.get("axes") or getattr(self.affective_space, "axes", {}) or {})
            legacy = {}
            try:
                legacy = dict(self.affect_state.snapshot() or {})
            except Exception:
                legacy = {}
            payload = dict(legacy)
            payload.update(axes)
            self.temporal.log(payload)
            # Update affect_state aggregates from temporal levels
            self.affect_state.affect_trend = self.temporal.trend()
            self.affect_state.affect_baseline = self.temporal.get_levels().get("T2_baseline", {})
        except Exception:
            pass

        # Update affective persistence traces (Phase 3.5)
        try:
            self.affective_persistence.update(
                affect_state=self.affect_state,
                neuromodulators=self.neuromodulators,
                temporal_levels=self.temporal.get_levels(),
                time_elapsed=step_elapsed,
            )
        except Exception:
            pass

        # Affective background, semantic emotions, emotional memory and
        # expectations are stable. The day's inputs are queued and applied
        # in sleep. The fast affective space still steps now.

        # Update affective space (Phase 4 pre) - no action influence
        try:
            space_inputs = affective_inputs
            if space_inputs is None:
                space_inputs = self._derive_affective_space_inputs(
                    reward=reward,
                    novelty=novelty,
                    conflict=conflict,
                    intensity=intensity,
                )
            self.affective_space.step(
                inputs=space_inputs,
                recall_impulses=getattr(self, "_pending_recall_impulses", None) or [],
                time_elapsed=time_elapsed if time_elapsed is not None else step_elapsed,
                wakefulness=self.wakefulness.wakefulness,
                uncertainty=novelty,
                conflict=conflict,
                background=getattr(self.affective_background, "snapshot", lambda: {})(),
            )
            self._pending_recall_impulses = []
            self._project_legacy_affect_from_affective_space(blend=1.0)
            try:
                if hasattr(self, "emotional_regulation") and self.emotional_regulation is not None:
                    self.emotional_regulation.sync_from_canonical(self.affective_space.axes)
            except Exception:
                pass
        except Exception:
            pass

        # Update emotional regulation (CER) - compute modulation factors only
        try:
            if hasattr(self, "emotional_regulation") and self.emotional_regulation is not None:
                prediction_error = float(value_update.get("td_error", 0.0)) if value_update is not None else 0.0
                resolution_success = max(0.0, min(1.0, float(reward)))
                if consequence is not None and reward >= 0.0:
                    resolution_success = max(resolution_success, 0.5)
                regulation = self.emotional_regulation.update(
                    reward_signal=reward,
                    prediction_error=prediction_error,
                    novelty_score=novelty,
                    policy_entropy=policy_entropy,
                    resolution_success=resolution_success,
                    time_delta=time_elapsed if time_elapsed is not None else step_elapsed,
                    timestamp=time.time(),
                )
                try:
                    factors = dict(regulation.get("modulation_factors", {}) or {})
                    if hasattr(self.hippocampus, "set_novelty_sensitivity_scale"):
                        self.hippocampus.set_novelty_sensitivity_scale(
                            float(factors.get("novelty_sensitivity_scale", 1.0))
                        )
                except Exception:
                    pass
                try:
                    if hasattr(self.emotional_regulation, "apply_neuromodulator_guidance"):
                        self.emotional_regulation.apply_neuromodulator_guidance(
                            self.neuromodulators,
                            guidance=regulation.get("neuromodulator_guidance"),
                            gain=0.5,
                        )
                except Exception:
                    pass
                try:
                    if hasattr(self, "emotional_regulation") and self.emotional_regulation is not None:
                        self.emotional_regulation.sync_from_canonical(
                            getattr(self.affective_space, "axes", {}) or {}
                        )
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, "stability_monitor") and self.stability_monitor is not None:
                exp_snapshot = getattr(self.emotional_expectations, "snapshot", lambda: {})()
                reg_snapshot = getattr(self.emotional_regulation, "snapshot", lambda: {})()
                bg_snapshot = getattr(self.affective_background, "snapshot", lambda: {})()
                nm_snapshot = getattr(self.neuromodulators, "snapshot", lambda: {})()
                sem_snapshot = getattr(self.semantic_emotions, "snapshot", lambda: [])()
                affect_snapshot = getattr(self.affect_state, "snapshot", lambda: {})()

                trigger_event = None
                try:
                    top_expectations = list(exp_snapshot.get("expectations", []) or [])
                    if top_expectations:
                        top = top_expectations[0]
                        trigger_event = (
                            str(top.get("trend", "stable")) == "increasing"
                            and float(top.get("probability", 0.0)) >= 0.6
                        )
                except Exception:
                    trigger_event = None

                self.stability_monitor.update(
                    emotional_state_snapshot=affect_snapshot,
                    affective_background_snapshot=bg_snapshot,
                    neuromodulators_snapshot=nm_snapshot,
                    expectations_snapshot=exp_snapshot,
                    regulation_snapshot=reg_snapshot,
                    semantic_emotions_snapshot=sem_snapshot,
                    trigger_event=trigger_event,
                    timestamp=time.time(),
                )
        except Exception:
            pass

        # Slow affective statistics and ACC outcome windows wait for sleep.
        try:
            td_for_acc = (
                float(value_update.get("phasic_delta", value_update.get("td_error", 0.0)))
                if value_update is not None
                else 0.0
            )
            self._queue_slow_affect(
                reward=float(reward),
                td_error=td_for_acc,
                step_elapsed=float(step_elapsed),
            )
        except Exception:
            pass

        # Keep short rolling histories for multi-criteria fitness evaluation.
        try:
            history_limit = max(1, int(getattr(self, "_fitness_history_limit", 256)))
        except Exception:
            history_limit = 256

        try:
            affective_axes = dict(getattr(getattr(self, "affective_space", None), "axes", {}) or {})
            affective_snapshot = {}
            for axis_name, axis_value in affective_axes.items():
                try:
                    affective_snapshot[str(axis_name)] = float(axis_value)
                except Exception:
                    continue
            if affective_snapshot:
                if not isinstance(getattr(self, "affective_history", None), list):
                    self.affective_history = []
                self.affective_history.append(affective_snapshot)
                if len(self.affective_history) > history_limit:
                    del self.affective_history[:-history_limit]
        except Exception:
            pass

        try:
            if not isinstance(getattr(self, "td_error_history", None), list):
                self.td_error_history = []
            td_error = None
            if isinstance(value_update, dict):
                td_error = value_update.get("td_error")
            if td_error is None and hasattr(self, "value_layer") and self.value_layer is not None:
                snapshot = getattr(self.value_layer, "snapshot", lambda: {})() or {}
                td_error = snapshot.get("last_td_error")
            if td_error is not None:
                self.td_error_history.append(float(td_error))
                if len(self.td_error_history) > history_limit:
                    del self.td_error_history[:-history_limit]
        except Exception:
            pass

        try:
            if not isinstance(getattr(self, "cortisol_history", None), list):
                self.cortisol_history = []
            cortisol = getattr(getattr(self, "neuromodulators", None), "cortisol", None)
            if cortisol is not None:
                cortisol_value = max(0.0, min(1.0, float(cortisol)))
                self.cortisol_history.append(cortisol_value)
                if len(self.cortisol_history) > history_limit:
                    del self.cortisol_history[:-history_limit]
        except Exception:
            pass
        
        return action

    def get_lifetime(self) -> float:
        """Return agent lifetime in seconds since creation."""
        try:
            # Include simulated sleep seconds (deep_sleep is simulated and does not advance wall-clock)
            wall = time.time() - self.created_ts
            return wall + getattr(self, '_simulated_sleep_seconds', 0.0)
        except Exception:
            return 0.0

    def get_lifetime_progress(self) -> float:
        """Return lifetime progress in [0..1] based on lived steps."""
        try:
            expected = float(self.expected_lifetime_steps or 1.0)
            progress = float(self.lived_steps) / expected
            if progress < 0.0:
                return 0.0
            if progress > 1.0:
                return 1.0
            return progress
        except Exception:
            return 0.0

    def _ensure_bg_channels(self, actions: list) -> None:
        for action_name in list(actions or []):
            aid = str(action_name)
            if aid and aid not in self.bg_action_channels:
                self.register_action_channel(aid)

    def _compute_bg_aversive_signal(self) -> float:
        stress = 0.0
        try:
            if hasattr(self.affective_space, "axes"):
                stress = float((self.affective_space.axes or {}).get("stress", 0.0))
        except Exception:
            stress = 0.0
        if stress == 0.0:
            try:
                stress = float(getattr(self.affect_state, "threat", 0.0))
            except Exception:
                stress = 0.0
        return max(0.0, min(1.0, stress))

    def _compute_policy_metrics_from_pressure(self, pressure_vector: dict) -> dict:
        values = [max(0.0, float(v)) for v in dict(pressure_vector or {}).values()]
        if not values:
            return {"top2_gap": 0.0, "policy_entropy": 1.0, "decision_latency": 1.0}

        total = sum(values)
        if total <= 1e-12:
            n = max(1, len(values))
            probs = [1.0 / float(n)] * n
        else:
            probs = [v / total for v in values]
        probs_sorted = sorted(probs, reverse=True)
        top = probs_sorted[0] if probs_sorted else 0.0
        second = probs_sorted[1] if len(probs_sorted) > 1 else 0.0
        top2_gap = max(0.0, min(1.0, top - second))

        policy_entropy = 0.0
        try:
            import math

            policy_entropy = -sum(
                max(0.0, float(p)) * math.log(max(1e-12, float(p)))
                for p in probs
                if float(p) > 0.0
            )
            max_entropy = math.log(float(max(2, len(probs))))
            policy_entropy = (policy_entropy / max_entropy) if max_entropy > 0.0 else 0.0
        except Exception:
            policy_entropy = 0.0
        policy_entropy = max(0.0, min(1.0, policy_entropy))
        decision_latency = max(0.0, min(1.0, 0.15 + (0.85 * policy_entropy)))
        return {
            "top2_gap": float(top2_gap),
            "policy_entropy": float(policy_entropy),
            "decision_latency": float(decision_latency),
        }

    def _estimate_pattern_completion_confidence(self, context_events: list, hip_exps: list) -> float:
        confidence = 0.0
        try:
            energies = [
                max(0.0, min(1.0, float(getattr(exp, "activation_energy", 0.0))))
                for exp in list(hip_exps or [])
            ]
            if energies:
                confidence = max(energies)
        except Exception:
            confidence = 0.0

        if confidence > 1e-9:
            return float(max(0.0, min(1.0, confidence)))

        try:
            if hasattr(self.hippocampus, "recall_signature"):
                recall = self.hippocampus.recall_signature({"features": set(context_events or [])})
                top_k = list(recall.get("similarity_top_k", []) or [])
                if top_k:
                    confidence = float(top_k[0].get("similarity", 0.0))
        except Exception:
            confidence = 0.0
        return float(max(0.0, min(1.0, confidence)))

    def _estimate_working_memory_load(
        self,
        context_events: list,
        hip_exps: list,
        ctx_patterns: list,
        pressure_vector: dict,
    ) -> float:
        context_load = min(1.0, len(list(context_events or [])) / 8.0)
        hip_load = min(1.0, len(list(hip_exps or [])) / 6.0)
        pattern_load = min(1.0, len(list(ctx_patterns or [])) / 6.0)
        action_load = min(1.0, len(list(dict(pressure_vector or {}).keys())) / 6.0)
        wm_load = (
            0.35 * context_load
            + 0.25 * hip_load
            + 0.20 * pattern_load
            + 0.20 * action_load
        )
        return float(max(0.0, min(1.0, wm_load)))

    def _extract_selector_pressures(
        self,
        hip_exps,
        ctx_patterns,
        intent_pressure: dict,
        affect_modifier: float,
        chain_bias: dict,
        prediction_pressure: dict,
    ) -> dict:
        selector = self.selector
        if hasattr(selector, "compute_pressures"):
            try:
                pressures_out = selector.compute_pressures(
                    hip_exps,
                    ctx_patterns,
                    intent_pressure=intent_pressure,
                    affect_modifier=affect_modifier,
                    temporal_chains_bias=chain_bias,
                    prediction_pressure=prediction_pressure,
                )
                if isinstance(pressures_out, Mapping):
                    return dict(pressures_out or {})
            except Exception:
                pass

        # Backward compatibility: if selector lacks compute_pressures, use choose()
        # only as proposer and still pass through mandatory BG+Thalamic pipeline.
        action_hint = ""
        try:
            action_hint = str(
                selector.choose(
                    hip_exps,
                    ctx_patterns,
                    intent_pressure=intent_pressure,
                    affect_modifier=affect_modifier,
                    temporal_chains_bias=chain_bias,
                    prediction_pressure=prediction_pressure,
                )
            ).strip()
        except TypeError:
            try:
                action_hint = str(
                    selector.choose(
                        hip_exps,
                        ctx_patterns,
                        intent_pressure=intent_pressure,
                        affect_modifier=affect_modifier,
                        temporal_chains_bias=chain_bias,
                    )
                ).strip()
            except TypeError:
                action_hint = str(
                    selector.choose(
                        hip_exps,
                        ctx_patterns,
                        intent_pressure=intent_pressure,
                        affect_modifier=affect_modifier,
                    )
                ).strip()
        actions_attr = getattr(selector, "actions", [])
        try:
            action_keys = list(actions_attr) if isinstance(actions_attr, (list, tuple, set)) else []
        except Exception:
            action_keys = []
        pressure = {str(a): 0.0 for a in action_keys}
        if action_hint:
            pressure[action_hint] = max(pressure.get(action_hint, 0.0), 1.0)
        return pressure

    def _extract_action_id_from_experience(self, exp) -> str:
        replay_action = str(getattr(exp, "replay_action_id", "")).strip()
        if replay_action:
            return replay_action
        try:
            signature = getattr(getattr(exp, "path", None), "signature", lambda: ())()
            for event_name in signature:
                token = str(event_name)
                if token.startswith("action:"):
                    return token.split(":", 1)[1]
        except Exception:
            return ""
        return ""

    def _estimate_action_reward_from_memory(
        self,
        action_id: str,
        action_snapshot: Mapping[str, Any],
        action_experiences: list,
    ) -> tuple:
        if not action_experiences:
            return 0.0, 0.0
        value_layer = getattr(self, "value_layer", None)
        similarity_threshold = max(0.0, min(1.0, float(getattr(self, "planning_similarity_threshold", 0.7))))
        weighted_reward = 0.0
        weight_total = 0.0
        for exp in list(action_experiences):
            exp_state = getattr(exp, "value_state_snapshot", None)
            if not isinstance(exp_state, Mapping):
                continue
            try:
                if value_layer is not None:
                    sim = float(state_similarity(action_snapshot, exp_state, encoder=value_layer.encoder))
                else:
                    sim = 0.0
            except Exception:
                sim = 0.0
            if sim < similarity_threshold:
                continue
            reward_v = float(getattr(exp, "reward", 0.0))
            reinforcement = max(1.0, float(getattr(exp, "reinforcement_count", 1.0)))
            weight = max(0.0, sim) * min(3.0, 1.0 + ((reinforcement - 1.0) * 0.25))
            weighted_reward += reward_v * weight
            weight_total += weight
        if weight_total <= 1e-12:
            return 0.0, 0.0
        reward_mean = weighted_reward / weight_total
        support = max(0.0, min(1.0, weight_total / 3.0))
        return float(reward_mean), float(support)

    def _filter_similar_action_experiences(
        self,
        action_snapshot: Mapping[str, Any],
        action_experiences: list,
        value_layer: Optional[ValueLayer] = None,
    ) -> list:
        if not action_experiences:
            return []
        layer = value_layer if value_layer is not None else getattr(self, "value_layer", None)
        similarity_threshold = max(
            0.0,
            min(1.0, float(getattr(self, "planning_similarity_threshold", 0.7))),
        )
        similar_experiences = []
        for exp in list(action_experiences):
            exp_state = getattr(exp, "value_state_snapshot", None)
            if not isinstance(exp_state, Mapping):
                continue
            try:
                sim = float(
                    state_similarity(
                        action_snapshot,
                        exp_state,
                        encoder=getattr(layer, "encoder", None),
                    )
                )
            except Exception:
                sim = 0.0
            if sim < similarity_threshold:
                continue
            similar_experiences.append(exp)
        return similar_experiences

    def _estimate_rollout_value(
        self,
        start_action: str,
        experiences: list,
        depth: int,
        gamma: float,
    ) -> float:
        if not experiences:
            return 0.0
        sample_limit = max(
            1,
            min(8, int(getattr(self, "planning_rollout_samples", 6))),
        )
        depth_limit = max(1, min(6, int(depth)))
        gamma_v = max(0.0, min(0.999, float(gamma)))
        start_action_id = str(start_action)
        rollout_values = []

        for exp in list(experiences)[:sample_limit]:
            try:
                exp_action = str(self._extract_action_id_from_experience(exp))
            except Exception:
                exp_action = ""
            if exp_action and exp_action != start_action_id:
                continue

            total = 0.0
            discount = 1.0
            steps = 0
            current = exp
            seen_nodes = set()

            while current is not None and steps < depth_limit:
                node_id = id(current)
                if node_id in seen_nodes:
                    break
                seen_nodes.add(node_id)
                reward = float(getattr(current, "reward", 0.0))
                total += discount * reward
                next_exp = getattr(current, "next_experience", None)
                discount *= gamma_v
                current = next_exp
                steps += 1

            rollout_values.append(float(total))

        if not rollout_values:
            return 0.0
        return float(max(rollout_values))

    def _generate_structured_imagination(
        self,
        start_state: Mapping[str, Any],
        action_id: str,
        experiences: list,
        depth: int,
    ) -> dict:
        empty_result = {
            "trajectories": [],
            "values": [],
            "action_values": {},
            "nodes_visited": 0,
            "edges_visited": 0,
            "novelty_hits": 0,
        }
        if not bool(getattr(self, "imagination_enabled", True)):
            self._last_imagination_stats = {
                "nodes_visited": 0,
                "edges_visited": 0,
                "max_depth_reached": 0,
                "novelty_hits": 0,
                "action_values_count": 0,
                "values_count": 0,
                "trajectory_count": 0,
                "confidence_mean": 0.0,
                "novelty_mean": 0.0,
            }
            return dict(empty_result)
        if not experiences:
            self._last_imagination_stats = {
                "nodes_visited": 0,
                "edges_visited": 0,
                "max_depth_reached": 0,
                "novelty_hits": 0,
                "action_values_count": 0,
                "values_count": 0,
                "trajectory_count": 0,
                "confidence_mean": 0.0,
                "novelty_mean": 0.0,
            }
            return dict(empty_result)

        engine = getattr(self, "imagination_engine", None)
        if not isinstance(engine, HippocampalImagineEngine):
            engine = HippocampalImagineEngine()
            self.imagination_engine = engine

        engine.samples = max(1, min(8, int(getattr(self, "imagination_samples", 8))))
        engine.depth = max(1, min(5, int(getattr(self, "imagination_depth", 4))))
        engine.branching = max(1, min(4, int(getattr(self, "imagination_branching", 3))))
        engine.similarity_threshold = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_similarity_threshold", 0.6))),
        )
        engine.reward_decay = max(
            0.1,
            min(1.0, float(getattr(self, "imagination_reward_decay", 0.9))),
        )
        engine.novelty_bonus = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_novelty_bonus", 0.05))),
        )
        engine.goal_bias = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_goal_bias", 0.35))),
        )
        engine.confidence_decay = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_confidence_decay", 0.9))),
        )
        engine.state_novelty_weight = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_state_novelty_weight", 0.4))),
        )
        self.imagination_value_blend = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_value_blend", 0.6))),
        )
        self.imagination_value_backup = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_value_backup", 0.8))),
        )
        engine.value_backup = float(self.imagination_value_backup)
        engine.max_graph_nodes = max(
            1,
            min(96, int(getattr(self, "imagination_max_graph_nodes", 96))),
        )
        engine.max_nodes = max(
            1,
            min(96, int(getattr(self, "imagination_max_nodes", engine.max_graph_nodes))),
        )
        engine.max_graph_nodes = min(engine.max_graph_nodes, engine.max_nodes)
        engine.max_graph_edges = max(
            1,
            min(192, int(getattr(self, "imagination_max_graph_edges", 192))),
        )
        engine.max_tree_nodes = max(
            1,
            min(128, int(getattr(self, "imagination_max_tree_nodes", 128))),
        )
        engine.action_temperature = max(
            0.05,
            min(5.0, float(getattr(self, "imagination_action_temperature", 0.7))),
        )
        engine.__post_init__()

        value_layer = getattr(self, "value_layer", None)
        gamma = 0.95
        if value_layer is not None:
            try:
                gamma = float(getattr(value_layer, "gamma_default", 0.95))
            except Exception:
                gamma = 0.95
        result = engine.generate_structured_imagination(
            start_state=dict(start_state or {}),
            action_id=str(action_id or ""),
            experiences=list(experiences or []),
            depth=max(1, min(5, int(depth))),
            gamma=gamma,
            value_layer=value_layer if isinstance(value_layer, ValueLayer) else None,
        )
        values = [float(v) for v in list(result.get("values", []) or [])]
        trajectories = list(result.get("trajectories", []) or [])
        raw_action_values = dict(result.get("action_values", {}) or {})
        action_values = {}
        for key, value in raw_action_values.items():
            try:
                action_values[str(key)] = float(value)
            except Exception:
                continue
        max_depth_reached = 0
        confidence_values = []
        novelty_values = []
        for trajectory in trajectories:
            try:
                max_depth_reached = max(max_depth_reached, int(getattr(trajectory, "depth", 0)))
            except Exception:
                pass
            try:
                confidence_values.append(float(getattr(trajectory, "confidence", 0.0)))
            except Exception:
                pass
            try:
                novelty_values.append(float(getattr(trajectory, "novelty_score", 0.0)))
            except Exception:
                pass

        confidence_mean = (
            float(sum(confidence_values) / float(len(confidence_values)))
            if confidence_values
            else 0.0
        )
        novelty_mean = (
            float(sum(novelty_values) / float(len(novelty_values)))
            if novelty_values
            else 0.0
        )
        self._last_imagination_stats = {
            "nodes_visited": int(result.get("nodes_visited", 0)),
            "edges_visited": int(result.get("edges_visited", 0)),
            "max_depth_reached": int(max_depth_reached),
            "novelty_hits": int(result.get("novelty_hits", 0)),
            "action_values_count": int(len(action_values)),
            "values_count": int(len(values)),
            "trajectory_count": int(len(trajectories)),
            "confidence_mean": float(confidence_mean),
            "novelty_mean": float(novelty_mean),
        }
        return {
            "trajectories": list(trajectories),
            "values": list(values),
            "action_values": dict(action_values),
            "nodes_visited": int(result.get("nodes_visited", 0)),
            "edges_visited": int(result.get("edges_visited", 0)),
            "novelty_hits": int(result.get("novelty_hits", 0)),
        }

    def _generate_action_tree_imagination(
        self,
        start_state: Mapping[str, Any],
        candidate_actions: list,
        experiences: list,
        depth: int,
    ) -> dict:
        empty_result = {
            "trajectories": [],
            "values": [],
            "action_values": {},
            "nodes_visited": 0,
            "edges_visited": 0,
            "novelty_hits": 0,
        }
        if not bool(getattr(self, "imagination_enabled", True)):
            self._last_imagination_stats = {
                "nodes_visited": 0,
                "edges_visited": 0,
                "max_depth_reached": 0,
                "novelty_hits": 0,
                "action_values_count": 0,
                "values_count": 0,
                "trajectory_count": 0,
                "confidence_mean": 0.0,
                "novelty_mean": 0.0,
            }
            return dict(empty_result)
        if not experiences:
            self._last_imagination_stats = {
                "nodes_visited": 0,
                "edges_visited": 0,
                "max_depth_reached": 0,
                "novelty_hits": 0,
                "action_values_count": 0,
                "values_count": 0,
                "trajectory_count": 0,
                "confidence_mean": 0.0,
                "novelty_mean": 0.0,
            }
            return dict(empty_result)

        action_tokens = []
        seen_tokens = set()
        for action in list(candidate_actions or []):
            token = str(action or "").strip()
            if not token or token in seen_tokens:
                continue
            seen_tokens.add(token)
            action_tokens.append(token)
        if not action_tokens:
            self._last_imagination_stats = {
                "nodes_visited": 0,
                "edges_visited": 0,
                "max_depth_reached": 0,
                "novelty_hits": 0,
                "action_values_count": 0,
                "values_count": 0,
                "trajectory_count": 0,
                "confidence_mean": 0.0,
                "novelty_mean": 0.0,
            }
            return dict(empty_result)

        engine = getattr(self, "imagination_engine", None)
        if not isinstance(engine, HippocampalImagineEngine):
            engine = HippocampalImagineEngine()
            self.imagination_engine = engine

        engine.samples = max(1, min(8, int(getattr(self, "imagination_samples", 8))))
        engine.depth = max(1, min(5, int(getattr(self, "imagination_depth", 4))))
        engine.branching = max(1, min(4, int(getattr(self, "imagination_action_branching", 3))))
        engine.similarity_threshold = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_similarity_threshold", 0.6))),
        )
        engine.reward_decay = max(
            0.1,
            min(1.0, float(getattr(self, "imagination_reward_decay", 0.9))),
        )
        engine.novelty_bonus = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_novelty_bonus", 0.05))),
        )
        engine.goal_bias = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_goal_bias", 0.35))),
        )
        engine.confidence_decay = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_confidence_decay", 0.9))),
        )
        engine.state_novelty_weight = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_state_novelty_weight", 0.4))),
        )
        self.imagination_value_blend = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_value_blend", 0.6))),
        )
        self.imagination_value_backup = max(
            0.0,
            min(1.0, float(getattr(self, "imagination_value_backup", 0.8))),
        )
        engine.value_backup = float(self.imagination_value_backup)
        engine.max_graph_nodes = max(
            1,
            min(96, int(getattr(self, "imagination_max_graph_nodes", 96))),
        )
        engine.max_nodes = max(
            1,
            min(96, int(getattr(self, "imagination_max_nodes", engine.max_graph_nodes))),
        )
        engine.max_graph_nodes = min(engine.max_graph_nodes, engine.max_nodes)
        engine.max_graph_edges = max(
            1,
            min(192, int(getattr(self, "imagination_max_graph_edges", 192))),
        )
        self.imagination_max_tree_nodes = max(
            1,
            min(128, int(getattr(self, "imagination_max_tree_nodes", 128))),
        )
        engine.max_tree_nodes = int(self.imagination_max_tree_nodes)
        self.imagination_action_temperature = max(
            0.05,
            min(5.0, float(getattr(self, "imagination_action_temperature", 0.7))),
        )
        engine.action_temperature = float(self.imagination_action_temperature)
        engine.__post_init__()

        value_layer = getattr(self, "value_layer", None)
        gamma = 0.95
        if value_layer is not None:
            try:
                gamma = float(getattr(value_layer, "gamma_default", 0.95))
            except Exception:
                gamma = 0.95

        result = engine.generate_action_tree_imagination(
            start_state=dict(start_state or {}),
            candidate_actions=list(action_tokens),
            experiences=list(experiences or []),
            depth=max(1, min(5, int(depth))),
            gamma=gamma,
            value_layer=value_layer if isinstance(value_layer, ValueLayer) else None,
        )

        values = [float(v) for v in list(result.get("values", []) or [])]
        trajectories = list(result.get("trajectories", []) or [])
        raw_action_values = dict(result.get("action_values", {}) or {})
        action_values = {}
        for key, value in raw_action_values.items():
            try:
                action_values[str(key)] = float(value)
            except Exception:
                continue

        max_depth_reached = 0
        confidence_values = []
        novelty_values = []
        for trajectory in trajectories:
            try:
                max_depth_reached = max(max_depth_reached, int(getattr(trajectory, "depth", 0)))
            except Exception:
                pass
            try:
                confidence_values.append(float(getattr(trajectory, "confidence", 0.0)))
            except Exception:
                pass
            try:
                novelty_values.append(float(getattr(trajectory, "novelty_score", 0.0)))
            except Exception:
                pass

        confidence_mean = (
            float(sum(confidence_values) / float(len(confidence_values)))
            if confidence_values
            else 0.0
        )
        novelty_mean = (
            float(sum(novelty_values) / float(len(novelty_values)))
            if novelty_values
            else 0.0
        )
        self._last_imagination_stats = {
            "nodes_visited": int(result.get("nodes_visited", 0)),
            "edges_visited": int(result.get("edges_visited", 0)),
            "max_depth_reached": int(max_depth_reached),
            "novelty_hits": int(result.get("novelty_hits", 0)),
            "action_values_count": int(len(action_values)),
            "values_count": int(len(values)),
            "trajectory_count": int(len(trajectories)),
            "confidence_mean": float(confidence_mean),
            "novelty_mean": float(novelty_mean),
        }
        return {
            "trajectories": list(trajectories),
            "values": list(values),
            "action_values": dict(action_values),
            "nodes_visited": int(result.get("nodes_visited", 0)),
            "edges_visited": int(result.get("edges_visited", 0)),
            "novelty_hits": int(result.get("novelty_hits", 0)),
        }

    def _generate_imagined_rollouts(
        self,
        start_state: Mapping[str, Any],
        action_id: str,
        experiences: list,
        depth: int,
    ) -> list[float]:
        result = self._generate_structured_imagination(
            start_state=start_state,
            action_id=action_id,
            experiences=experiences,
            depth=depth,
        )
        return [float(v) for v in list(result.get("values", []) or [])]

    def _apply_deliberative_planning(
        self,
        pressure_vector: Mapping[str, float],
        context_events: list,
        intensity: float,
        novelty: float,
        conflict: float,
        decision_state: Optional[Mapping[str, Any]] = None,
    ) -> tuple:
        def _planning_meta(
            *,
            applied: bool,
            supported_actions: int = 0,
            support_mean: float = 0.0,
            rollout_depth: int = 0,
            rollout_samples: int = 0,
            rollout_used: int = 0,
            exploration_bonus_mean: float = 0.0,
            imagination_enabled: bool = bool(getattr(self, "imagination_enabled", True)),
            imagination_samples: int = int(max(1, min(8, int(getattr(self, "imagination_samples", 8))))),
            imagination_depth: int = int(max(1, min(5, int(getattr(self, "imagination_depth", 4))))),
            imagination_action_sequences_enabled: bool = bool(
                getattr(self, "imagination_enable_action_sequences", True)
            ),
            imagination_branching: int = int(
                max(1, min(4, int(getattr(self, "imagination_action_branching", 3))))
            ),
            imagined_rollouts_used: int = 0,
            imagined_value_mean: float = 0.0,
            imagined_value_max: float = 0.0,
            imagined_trajectory_count: int = 0,
            imagined_confidence_mean: float = 0.0,
            imagined_novelty_mean: float = 0.0,
            imagination_novelty_hits: int = 0,
            imagination_tree_nodes: int = 0,
            imagination_tree_edges: int = 0,
            imagination_action_count: int = 0,
        ) -> dict:
            return {
                "planning_bias_applied": bool(applied),
                "supported_actions": int(max(0, supported_actions)),
                "support_mean": float(max(0.0, min(1.0, support_mean))),
                "rollout_depth": int(max(0, rollout_depth)),
                "rollout_samples": int(max(0, rollout_samples)),
                "rollout_used": int(max(0, rollout_used)),
                "exploration_bonus_mean": float(max(0.0, exploration_bonus_mean)),
                "imagination_enabled": bool(imagination_enabled),
                "imagination_samples": int(max(0, imagination_samples)),
                "imagination_depth": int(max(0, imagination_depth)),
                "imagination_action_sequences_enabled": bool(imagination_action_sequences_enabled),
                "imagination_branching": int(max(1, min(4, imagination_branching))),
                "imagined_rollouts_used": int(max(0, imagined_rollouts_used)),
                "imagined_value_mean": float(imagined_value_mean),
                "imagined_value_max": float(imagined_value_max),
                "imagined_trajectory_count": int(max(0, imagined_trajectory_count)),
                "imagined_confidence_mean": float(max(0.0, min(1.0, imagined_confidence_mean))),
                "imagined_novelty_mean": float(max(0.0, imagined_novelty_mean)),
                "imagination_novelty_hits": int(max(0, imagination_novelty_hits)),
                "imagination_tree_nodes": int(max(0, imagination_tree_nodes)),
                "imagination_tree_edges": int(max(0, imagination_tree_edges)),
                "imagination_action_count": int(max(0, imagination_action_count)),
            }

        pressures = {str(action): float(value) for action, value in dict(pressure_vector or {}).items()}
        if not pressures:
            return {}, _planning_meta(applied=False)
        if not bool(getattr(self, "deliberative_planning_enabled", True)):
            return pressures, _planning_meta(applied=False)

        value_layer = getattr(self, "value_layer", None)
        if value_layer is None:
            return pressures, _planning_meta(applied=False)

        try:
            all_experiences = list(getattr(getattr(self, "hippocampus", None), "experiences", []) or [])
        except Exception:
            all_experiences = []
        scan_limit = max(16, int(getattr(self, "planning_memory_scan", 256)))
        recent_experiences = all_experiences[-scan_limit:]
        if not recent_experiences:
            return pressures, _planning_meta(applied=False)

        action_items = list(pressures.items())
        max_actions = 32
        if len(action_items) > max_actions:
            ranked_actions = sorted(
                action_items,
                key=lambda item: (float(item[1]), str(item[0])),
                reverse=True,
            )
            planning_action_ids = [str(action_id) for action_id, _ in ranked_actions[:max_actions]]
        else:
            planning_action_ids = [str(action_id) for action_id, _ in action_items]

        action_index = {str(action_id): [] for action_id in planning_action_ids}
        for exp in recent_experiences:
            exp_action = str(self._extract_action_id_from_experience(exp))
            if exp_action in action_index:
                action_index[exp_action].append(exp)

        gamma = max(0.0, min(0.999, float(getattr(value_layer, "gamma_default", 0.95))))
        gain = max(0.0, min(0.6, float(getattr(self, "planning_gain", 0.2))))
        uncertainty = 0.0
        if isinstance(decision_state, Mapping):
            try:
                uncertainty = float(decision_state.get("global_uncertainty", 0.0))
            except Exception:
                uncertainty = 0.0
        uncertainty = max(0.0, min(1.0, uncertainty))
        base_depth = max(1, min(6, int(getattr(self, "planning_rollout_depth", 3))))
        depth_gain = max(0.0, float(getattr(self, "planning_uncertainty_depth_gain", 2.0)))
        rollout_depth = max(1, min(6, int(base_depth + (uncertainty * depth_gain))))
        rollout_samples = max(
            1,
            min(8, int(getattr(self, "planning_rollout_samples", 6))),
        )
        imagination_enabled = bool(getattr(self, "imagination_enabled", True))
        imagination_samples = max(1, min(8, int(getattr(self, "imagination_samples", 8))))
        imagination_depth = max(
            1,
            min(
                5,
                int(
                    min(
                        rollout_depth,
                        int(getattr(self, "imagination_depth", 4)),
                    )
                ),
            ),
        )
        imagination_sequences_enabled = bool(
            getattr(self, "imagination_enable_action_sequences", True)
        )
        imagination_branching = max(
            1,
            min(4, int(getattr(self, "imagination_action_branching", 3))),
        )
        exploration_gain = max(0.0, min(0.6, float(getattr(self, "planning_exploration_gain", 0.15))))
        confidence_floor = max(0.0, min(1.0, float(getattr(self, "planning_min_confidence", 0.2))))
        blend = max(0.0, min(1.0, float(getattr(self, "imagination_value_blend", 0.6))))
        predictions = {}
        if isinstance(decision_state, Mapping):
            pred_raw = decision_state.get("edpc_predictions")
            if isinstance(pred_raw, Mapping):
                predictions = dict(pred_raw)

        q_values = {}
        supports = {}
        exploration_bonuses = []
        rollout_used = 0
        imagined_values_all = []
        imagined_trajectory_count = 0
        imagined_confidence_all = []
        imagined_novelty_all = []
        imagination_novelty_hits = 0
        imagination_tree_nodes = 0
        imagination_tree_edges = 0
        imagination_action_count = 0
        shared_action_values = {}

        if imagination_enabled and imagination_sequences_enabled:
            planning_start_state = self._build_value_state_snapshot(
                context_events=context_events,
                action="",
                consequence=None,
                intensity=float(intensity),
                novelty=float(novelty),
                conflict=float(conflict),
            )
            imagination_result = self._generate_action_tree_imagination(
                start_state=planning_start_state,
                candidate_actions=list(planning_action_ids),
                experiences=recent_experiences,
                depth=imagination_depth,
            )
            shared_action_values = {
                str(action_id): float(value)
                for action_id, value in dict(imagination_result.get("action_values", {}) or {}).items()
            }
            imagination_action_count = int(len(shared_action_values))
            imagination_tree_nodes = int(imagination_result.get("nodes_visited", 0))
            imagination_tree_edges = int(imagination_result.get("edges_visited", 0))
            imagination_novelty_hits += int(imagination_result.get("novelty_hits", 0))
            tree_values = [float(v) for v in list(imagination_result.get("values", []) or [])]
            imagined_values_all.extend(tree_values)
            trajectories = list(imagination_result.get("trajectories", []) or [])
            imagined_trajectory_count += int(len(trajectories))
            for trajectory in trajectories:
                try:
                    imagined_confidence_all.append(float(getattr(trajectory, "confidence", 0.0)))
                except Exception:
                    pass
                try:
                    imagined_novelty_all.append(float(getattr(trajectory, "novelty_score", 0.0)))
                except Exception:
                    pass

        for action_id in planning_action_ids:
            base_pressure = float(pressures.get(action_id, 0.0))
            action_state = self._build_value_state_snapshot(
                context_events=context_events,
                action=action_id,
                consequence=None,
                intensity=float(intensity),
                novelty=float(novelty),
                conflict=float(conflict),
            )
            try:
                model_value = float(self.effective_action_value(action_state, action_id))
            except Exception:
                model_value = 0.0
            action_experiences = self._filter_similar_action_experiences(
                action_snapshot=action_state,
                action_experiences=action_index.get(str(action_id), []),
                value_layer=value_layer,
            )
            reward_mean, support = self._estimate_action_reward_from_memory(
                action_id=action_id,
                action_snapshot=action_state,
                action_experiences=action_experiences,
            )
            edpc_bias = 0.0
            if action_id in predictions:
                try:
                    edpc_bias = float(predictions.get(action_id, 0.0))
                except Exception:
                    edpc_bias = 0.0
            support_clamped = max(0.0, min(1.0, float(support)))
            if support_clamped < 0.05:
                continue
            memory_rollout_value = self._estimate_rollout_value(
                start_action=action_id,
                experiences=action_experiences,
                depth=rollout_depth,
                gamma=gamma,
            )

            imagined_value = 0.0
            if imagination_enabled:
                if imagination_sequences_enabled:
                    imagined_value = float(shared_action_values.get(str(action_id), 0.0))
                else:
                    imagination_result = self._generate_structured_imagination(
                        start_state=action_state,
                        action_id=action_id,
                        experiences=recent_experiences,
                        depth=imagination_depth,
                    )
                    imagined_rollouts = [
                        float(v)
                        for v in list(imagination_result.get("values", []) or [])
                    ]
                    if imagined_rollouts:
                        imagination_action_count += 1
                    imagined_value = quantile(imagined_rollouts, 0.7) if imagined_rollouts else 0.0
                    imagined_values_all.extend(float(v) for v in list(imagined_rollouts or []))
                    trajectories = list(imagination_result.get("trajectories", []) or [])
                    imagined_trajectory_count += int(len(trajectories))
                    for trajectory in trajectories:
                        try:
                            imagined_confidence_all.append(float(getattr(trajectory, "confidence", 0.0)))
                        except Exception:
                            pass
                        try:
                            imagined_novelty_all.append(float(getattr(trajectory, "novelty_score", 0.0)))
                        except Exception:
                            pass
                    imagination_novelty_hits += int(imagination_result.get("novelty_hits", 0))
                    imagination_tree_nodes += int(imagination_result.get("nodes_visited", 0))
                    imagination_tree_edges += int(imagination_result.get("edges_visited", 0))

            if imagination_enabled:
                rollout_value = float(
                    ((1.0 - blend) * memory_rollout_value)
                    + (blend * imagined_value)
                )
            else:
                rollout_value = float(memory_rollout_value)
            confidence = 0.0
            confidence_values = []
            for exp in action_experiences:
                try:
                    exp_confidence = float(getattr(exp, "expectation_confidence_score", 0.0))
                except Exception:
                    exp_confidence = 0.0
                if exp_confidence <= 1e-12:
                    try:
                        exp_var = max(0.0, float(getattr(exp, "expected_reward_var", 0.0)))
                    except Exception:
                        exp_var = 0.0
                    exp_confidence = max(0.0, min(1.0, 1.0 - exp_var))
                if exp_confidence > 1e-12:
                    confidence_values.append(max(0.0, min(1.0, exp_confidence)))
            if confidence_values:
                confidence_mean = float(sum(confidence_values) / float(len(confidence_values)))
                confidence_var = float(
                    sum((val - confidence_mean) ** 2 for val in confidence_values)
                    / float(len(confidence_values))
                )
                confidence = float(confidence_mean / (1.0 + confidence_var))
            else:
                try:
                    confidence = float(getattr(value_layer, "last_confidence_score", 0.0))
                except Exception:
                    confidence = 0.0
                if confidence <= 1e-12:
                    try:
                        reward_var = max(0.0, float(getattr(value_layer, "last_expected_reward_var", 0.0)))
                    except Exception:
                        reward_var = 0.0
                    confidence = max(0.0, min(1.0, 1.0 - reward_var))
            confidence = max(0.0, min(1.0, confidence))
            if confidence < confidence_floor:
                continue
            exploration_bonus = exploration_gain * max(0.0, (1.0 - confidence))
            q_val = float(
                reward_mean
                + (gamma * max(model_value, rollout_value))
                + edpc_bias
                + exploration_bonus
            )
            try:
                cost_aversion = float((self.affective_space.rank_weights() or {}).get("cost_aversion", 0.5))
                q_val -= float(getattr(self, "planning_rollout_risk_penalty", 0.15)) * max(0.0, cost_aversion)
            except Exception:
                pass
            q_values[action_id] = q_val
            supports[action_id] = support_clamped
            exploration_bonuses.append(float(exploration_bonus))
            rollout_used += 1

        if not q_values:
            return pressures, _planning_meta(
                applied=False,
                rollout_depth=rollout_depth,
                rollout_samples=rollout_samples,
                rollout_used=rollout_used,
                imagination_enabled=imagination_enabled,
                imagination_samples=imagination_samples,
                imagination_depth=imagination_depth,
                imagination_action_sequences_enabled=imagination_sequences_enabled,
                imagination_branching=imagination_branching,
                imagined_rollouts_used=len(imagined_values_all),
                imagined_value_mean=(
                    float(sum(imagined_values_all) / float(len(imagined_values_all)))
                    if imagined_values_all
                    else 0.0
                ),
                imagined_value_max=float(max(imagined_values_all)) if imagined_values_all else 0.0,
                imagined_trajectory_count=imagined_trajectory_count,
                imagined_confidence_mean=(
                    float(sum(imagined_confidence_all) / float(len(imagined_confidence_all)))
                    if imagined_confidence_all
                    else 0.0
                ),
                imagined_novelty_mean=(
                    float(sum(imagined_novelty_all) / float(len(imagined_novelty_all)))
                    if imagined_novelty_all
                    else 0.0
                ),
                imagination_novelty_hits=imagination_novelty_hits,
                imagination_tree_nodes=imagination_tree_nodes,
                imagination_tree_edges=imagination_tree_edges,
                imagination_action_count=imagination_action_count,
            )

        q_min = min(q_values.values())
        q_max = max(q_values.values())
        q_span = q_max - q_min
        planned_pressures = dict(pressures)
        total_support = 0.0
        for action_id in planning_action_ids:
            if action_id not in q_values:
                continue
            if q_span > 1e-12:
                q_norm = ((q_values[action_id] - q_min) / q_span) * 2.0 - 1.0
            else:
                q_norm = 0.0
            support = float(supports.get(action_id, 0.0))
            total_support += support
            planned_pressures[action_id] = max(
                0.0,
                float(pressures.get(action_id, 0.0)) + (gain * q_norm * support),
            )

        exploration_bonus_mean = (
            float(sum(exploration_bonuses) / float(len(exploration_bonuses)))
            if exploration_bonuses
            else 0.0
        )
        imagined_value_mean = (
            float(sum(imagined_values_all) / float(len(imagined_values_all)))
            if imagined_values_all
            else 0.0
        )
        imagined_value_max = float(max(imagined_values_all)) if imagined_values_all else 0.0
        imagined_confidence_mean = (
            float(sum(imagined_confidence_all) / float(len(imagined_confidence_all)))
            if imagined_confidence_all
            else 0.0
        )
        imagined_novelty_mean = (
            float(sum(imagined_novelty_all) / float(len(imagined_novelty_all)))
            if imagined_novelty_all
            else 0.0
        )
        return planned_pressures, _planning_meta(
            applied=True,
            supported_actions=len(q_values),
            support_mean=float(total_support / float(max(1, len(q_values)))),
            rollout_depth=rollout_depth,
            rollout_samples=rollout_samples,
            rollout_used=rollout_used,
            exploration_bonus_mean=exploration_bonus_mean,
            imagination_enabled=imagination_enabled,
            imagination_samples=imagination_samples,
            imagination_depth=imagination_depth,
            imagination_action_sequences_enabled=imagination_sequences_enabled,
            imagination_branching=imagination_branching,
            imagined_rollouts_used=len(imagined_values_all),
            imagined_value_mean=imagined_value_mean,
            imagined_value_max=imagined_value_max,
            imagined_trajectory_count=imagined_trajectory_count,
            imagined_confidence_mean=imagined_confidence_mean,
            imagined_novelty_mean=imagined_novelty_mean,
            imagination_novelty_hits=imagination_novelty_hits,
            imagination_tree_nodes=imagination_tree_nodes,
            imagination_tree_edges=imagination_tree_edges,
            imagination_action_count=imagination_action_count,
        )

    def _select_action_via_basal_ganglia_pipeline(
        self,
        pressure_vector: dict,
        cer_modulation_factors: Optional[Mapping[str, Any]] = None,
        visit_counts: Optional[Mapping[str, int]] = None,
    ) -> str:
        if visit_counts is None:
            visit_counts = getattr(self, "_pending_visit_counts", None)
        pressures = dict(pressure_vector or {})
        if not pressures:
            actions_attr = getattr(self.selector, "actions", [])
            try:
                action_keys = list(actions_attr) if isinstance(actions_attr, (list, tuple, set)) else []
            except Exception:
                action_keys = []
            pressures = {str(a): 0.0 for a in action_keys}

        self._ensure_bg_channels(list(pressures.keys()))
        habit_strengths = {
            aid: float(getattr(self.bg_action_channels.get(aid), "habit_strength", 0.0))
            for aid in pressures.keys()
        }
        channel_modulators = {}
        for aid in pressures.keys():
            channel = self.bg_action_channels.get(aid)
            if channel is not None:
                go_stable = float(getattr(channel, "go_weight", 1.0))
                nogo_stable = float(getattr(channel, "nogo_weight", 1.0))
                go_eff, nogo_eff = self.labile.effective_channel(
                    str(aid),
                    go_stable,
                    nogo_stable,
                    float(getattr(self, "_host_clock_s", 0.0)),
                )
                channel_modulators[aid] = {
                    "go_weight": go_eff,
                    "nogo_weight": nogo_eff,
                }
        cer = dict(cer_modulation_factors or {})
        exploration_bias = max(0.0, min(1.5, float(cer.get("exploration_bias", 0.0))))
        decision_threshold_shift = max(-0.5, min(0.8, float(cer.get("decision_threshold_shift", 0.0))))
        habit_gain_scale = max(0.7, min(1.6, float(cer.get("habit_gain_scale", 1.0))))

        try:
            weights = dict(getattr(self.affective_space, "rank_weights", lambda: {})() or {})
            bias = dict(getattr(self.affective_space, "decision_bias", lambda: {})() or {})
        except Exception:
            weights, bias = {}, {}
        response_speed = float(bias.get("response_speed", 0.0) or 0.0)
        caution = float(weights.get("caution", 0.0) or 0.0)
        novelty_seek = float(weights.get("novelty_seek", 0.5) or 0.5)
        exploration_bias = max(
            0.0,
            min(1.5, exploration_bias + 0.2 * (novelty_seek - 0.5)),
        )

        try:
            gated = self.basal_ganglia.process(
                pressure_vector=pressures,
                dopamine_level=float(getattr(self.neuromodulators, "dopamine", 0.0)),
                cortisol_level=float(getattr(self.neuromodulators, "cortisol", 0.0)),
                norepinephrine_level=float(getattr(self.neuromodulators, "norepinephrine", 0.0)),
                habit_strengths=habit_strengths,
                aversive_signal=self._compute_bg_aversive_signal(),
                channel_modulators=channel_modulators,
                exploration_bias=exploration_bias,
                decision_threshold_shift=decision_threshold_shift,
                habit_gain_scale=habit_gain_scale,
                response_speed=response_speed,
                caution=caution,
                visit_counts=None if visit_counts is None else dict(visit_counts),
            )
        except TypeError:
            # Backward compatibility for monkeypatched/custom process implementations.
            gated = self.basal_ganglia.process(
                pressure_vector=pressures,
                dopamine_level=float(getattr(self.neuromodulators, "dopamine", 0.0)),
                cortisol_level=float(getattr(self.neuromodulators, "cortisol", 0.0)),
                norepinephrine_level=float(getattr(self.neuromodulators, "norepinephrine", 0.0)),
                habit_strengths=habit_strengths,
                aversive_signal=self._compute_bg_aversive_signal(),
                channel_modulators=channel_modulators,
            )
        selected_action = self.thalamic_gate.select(
            gated_scores=gated,
            norepinephrine_level=float(getattr(self.neuromodulators, "norepinephrine", 0.0)),
            exploration_bias=exploration_bias,
            stability=float((getattr(self.affective_space, "axes", {}) or {}).get("stability", 1.0)),
            rng=self._rng if getattr(self, "_rng_controls_thalamic", False) else None,
        )
        self.basal_ganglia.selection_history.append(
            (selected_action, self.basal_ganglia.last_nets.get(selected_action, 0.0))
        )
        self._last_bg_selection = (selected_action, self.basal_ganglia.last_nets.get(selected_action, 0.0))
        return selected_action
    
    def register_action_channel(self, action_id: str, go_weight: float = 0.5, nogo_weight: float = 0.5, habit_strength: float = 0.0):
        """Register an action channel. This is host seeding, not waking learning.

        The write runs under ``initializing()``. A later direct assignment to
        ``go_weight`` / ``nogo_weight`` / ``habit_strength`` does not.
        """
        from learning_guard import initializing

        with initializing():
            self.bg_action_channels[action_id] = ActionChannel(
                action_id=action_id,
                go_weight=go_weight,
                nogo_weight=nogo_weight,
                habit_strength=habit_strength,
            )

    def set_organ_risk(self, tool_id: str, risk_level: str) -> None:
        """Record a WRITE organ's risk class without importing MCP types."""
        if not hasattr(self, "organ_risks") or self.organ_risks is None:
            self.organ_risks = {}
        label = str(tool_id or "").strip()
        if label:
            self.organ_risks[label] = str(risk_level or "").strip().lower()

    def _recall_impulses_from_experiences(self, experiences) -> list:
        impulses = []
        recall = getattr(getattr(self, "affective_space", None), "recall_trace", None)
        if not callable(recall):
            return impulses
        if not isinstance(experiences, (list, tuple)):
            return impulses
        for exp in list(experiences):
            trace = getattr(exp, "emotional_trace", None)
            if trace is None:
                continue
            try:
                impulse = recall(trace)
            except Exception:
                continue
            if impulse is not None:
                impulses.append(impulse)
        return impulses

    def _organ_novelty(self, tool_id: str) -> float:
        """1.0 if this tool_id has never appeared as an ACTION in hippocampus."""
        needle = str(tool_id or "").strip()
        if not needle:
            return 1.0
        experiences = getattr(getattr(self, "hippocampus", None), "experiences", None)
        if not isinstance(experiences, (list, tuple)):
            return 1.0
        marker = f"action:{needle}"
        for exp in experiences:
            path = getattr(exp, "path", None)
            events = getattr(path, "events", None) or []
            for event in events:
                name = str(getattr(event, "name", event) or "")
                if name == marker or name == needle or name.endswith(needle):
                    return 0.0
        return 1.0

    def _modulate_pressures_for_organs(self, pressures: dict) -> dict:
        """Per-channel affective scale (spec §7.2). Does not import MCP."""
        if not isinstance(pressures, dict) or not pressures:
            return pressures
        risks = getattr(self, "organ_risks", None) or {}
        if not risks:
            return pressures
        try:
            weights = dict(getattr(self.affective_space, "rank_weights", lambda: {})() or {})
        except Exception:
            weights = {}
        caution = max(0.0, min(1.0, float(weights.get("caution", 0.0) or 0.0)))
        novelty_seek = max(0.0, min(1.0, float(weights.get("novelty_seek", 0.0) or 0.0)))
        out = {}
        for tool_id, pressure in pressures.items():
            try:
                value = float(pressure)
            except Exception:
                value = 0.0
            risk = str(risks.get(tool_id, "")).lower()
            if not risk:
                out[tool_id] = value
                continue
            if risk in ("high_write", "irreversible"):
                value *= (1.0 - 0.5 * caution)
            value *= (1.0 + 0.2 * novelty_seek * self._organ_novelty(str(tool_id)))
            out[tool_id] = value
        return out

    def choose_action_via_basal_ganglia(self, available_actions: list = None, pfc_pressure: dict = None) -> str:
        """
        Выбрать действие через базальные ганглии (Go/NoGo конкуренция).

        Args:
            available_actions: список доступных action_ids. Если None, используются зарегистрированные
            pfc_pressure: опциональное давление от PFC {action_id: pressure}

        Returns:
            выбранный action_id
        """
        if available_actions is None:
            selector_actions = getattr(self.selector, "actions", [])
            try:
                selector_actions_list = list(selector_actions) if isinstance(selector_actions, (list, tuple, set)) else []
            except Exception:
                selector_actions_list = []
            available_actions = list(self.bg_action_channels.keys()) or selector_actions_list

        if not available_actions:
            raise ValueError("No action channels registered for BG selection")

        self._ensure_bg_channels(available_actions)
        pressure_vector = {}
        now = float(getattr(self, "_host_clock_s", 0.0))
        for action_name in available_actions:
            aid = str(action_name)
            channel = self.bg_action_channels.get(aid)
            if channel is None:
                pressure_vector[aid] = 0.0
                continue
            go_stable = float(getattr(channel, "go_weight", 0.0))
            nogo_stable = float(getattr(channel, "nogo_weight", 0.0))
            go_eff, _nogo_eff = self.labile.effective_channel(aid, go_stable, nogo_stable, now)
            pressure_vector[aid] = go_eff
        if isinstance(pfc_pressure, dict):
            for aid, pressure in pfc_pressure.items():
                if aid in pressure_vector:
                    pressure_vector[aid] += float(pressure)

        cer_modulation = {}
        try:
            if hasattr(self, "emotional_regulation") and self.emotional_regulation is not None:
                cer_modulation = dict(
                    (self.emotional_regulation.snapshot() or {}).get("modulation_factors", {}) or {}
                )
        except Exception:
            cer_modulation = {}

        self._pending_visit_counts = None
        return self._select_action_via_basal_ganglia_pipeline(
            pressure_vector,
            cer_modulation_factors=cer_modulation,
        )

    def record_action_outcome(self, action_id: str, outcome: float):
        """
        Р—Р°РїРёСЃР°С‚СЊ СЂРµР·СѓР»СЊС‚Р°С‚ РІС‹Р±СЂР°РЅРЅРѕРіРѕ РґРµР№СЃС‚РІРёСЏ РґР»СЏ РѕР±СѓС‡РµРЅРёСЏ РІРѕ СЃРЅРµ.
        
        Args:
            action_id: РєР°РєРѕРµ РґРµР№СЃС‚РІРёРµ Р±С‹Р»Рѕ РІС‹РїРѕР»РЅРµРЅРѕ
            outcome: РїРѕР»РѕР¶РёС‚РµР»СЊРЅРѕРµ (СѓСЃРїРµС…) РёР»Рё РѕС‚СЂРёС†Р°С‚РµР»СЊРЅРѕРµ (РѕС€РёР±РєР°) Р·РЅР°С‡РµРЅРёРµ
        """
        if action_id in self.bg_action_channels:
            self.bg_action_channels[action_id].record_outcome(outcome)
        # Outcomes for sleep come from hippocampal episodes (decision 5).
        # ``bg_sleep_memories`` is no longer a learning source.

    def _record_known_outcome(
        self,
        context_events,
        action_id: str,
        outcome: float,
        episode=None,
        state_snapshot=None,
        next_state_snapshot=None,
        next_context_events=None,
        terminal: bool = False,
        intensity: float = 1.0,
        novelty: float = 0.0,
        conflict: float = 0.0,
    ) -> dict:
        """Write one known outcome into the labile tier and the sleep log.

        Stable Q, Go/NoGo and habit strength are not touched. A second call
        for the same episode replaces that episode's labile contribution.
        """
        action_name = str(action_id or "")
        if not isinstance(state_snapshot, dict):
            state_snapshot = self._build_value_state_snapshot(
                context_events=list(context_events or []),
                action=action_name,
                consequence=None,
                intensity=float(intensity),
                novelty=float(novelty),
                conflict=float(conflict),
            )
        if not isinstance(next_context_events, list):
            next_context_events = list(context_events or [])
        now = float(getattr(self, "_host_clock_s", 0.0))
        episode_id = str(getattr(episode, "episode_id", "") or "")
        if not episode_id:
            episode_id = str(getattr(self, "last_episode_id", "") or "")
        if episode_id and getattr(self, "labile", None) is not None:
            self.labile.pop_contribution(episode_id, now)
        state_key = ""
        stable_q = 0.0
        try:
            if getattr(self, "value_layer", None) is not None:
                state_key = str(self.value_layer.encoder.encode(state_snapshot or {}))
                stable_q = float(self.value_layer.get_value(state_snapshot))
        except Exception:
            state_key = ""
            stable_q = 0.0
        q_offset = 0.0
        if getattr(self, "labile", None) is not None:
            q_offset = float(self.labile.q_offset(state_key, action_name, now))
        q_eff = stable_q + q_offset
        gamma = float(getattr(getattr(self, "value_layer", None), "gamma_default", 0.95))
        if not math.isfinite(gamma):
            gamma = 0.95
        if terminal:
            bootstrap = 0.0
        else:
            bootstrap = self._successor_bootstrap(
                next_context_events=next_context_events,
                intensity=float(intensity),
                novelty=float(novelty),
                conflict=float(conflict),
                terminal=False,
            )
        td_error = float(outcome) + (gamma * float(bootstrap)) - q_eff
        if not math.isfinite(td_error):
            td_error = 0.0
        applied = {}
        if getattr(self, "labile", None) is not None and episode_id:
            applied = self.labile.apply_outcome(
                episode_id=episode_id,
                state_key=state_key,
                action=action_name,
                reward=float(outcome),
                td_error=float(td_error),
                now=now,
                g_da=1.0,
            )
        if episode is not None:
            try:
                episode.labile_contribution = dict(applied)
                episode.encoded_at = float(now)
                if not hasattr(episode, "consolidated"):
                    episode.consolidated = False
                previous_reward = getattr(episode, "td_committed_reward", None)
                already = bool(getattr(episode, "td_outcome_committed", False))
                changed = (
                    not already
                    or previous_reward is None
                    or abs(float(previous_reward) - float(outcome)) > 1e-9
                )
                if changed:
                    episode.outcome_revision = int(getattr(episode, "outcome_revision", 0) or 0) + 1
                episode.td_outcome_committed = True
                episode.td_committed_reward = float(outcome)
                episode.td_prior_value = float(q_eff)
                episode.td_applied_delta = float(applied.get("q_delta", 0.0))
                episode.value_terminal = bool(terminal)
                episode.value_next_context_events = list(next_context_events)
                episode.value_state_snapshot = dict(state_snapshot or {})
                if isinstance(next_state_snapshot, dict):
                    episode.value_next_state_snapshot = dict(next_state_snapshot)
                episode.value_state_key = state_key
                episode.td_error_snapshot = float(td_error)
            except Exception:
                pass
        # Diagnostics only. The Q table itself is not written while awake.
        # g_DA stays 1 (owner decision after PR A): the labile step is not
        # scaled by the current dopamine level.
        # The next step's exploration coupling reads last_td_error.
        layer = getattr(self, "value_layer", None)
        if layer is not None:
            try:
                layer.last_td_error = float(td_error)
                layer.last_reward_raw = float(outcome)
                layer.last_dopamine_delta = float(layer.compute_dopamine_delta(td_error))
            except Exception:
                pass
        return {
            "td_error": float(td_error),
            "state_key": state_key,
            "replay_priority": abs(float(td_error)),
            "consolidation_weight": max(0.0, min(1.0, abs(float(td_error)))),
            "confidence_score": 0.0,
            "stability_score": 0.0,
            "prediction_shock": False,
            "expected_reward_mean": 0.0,
            "expected_reward_var": 0.0,
            "confirmation_count": 0.0,
            "prediction_shock_score": 0.0,
            "error_likelihood": 0.0,
            "shock_replay_boost": 1.0,
            "value": float(q_eff) + float(applied.get("q_delta", 0.0)),
            "q_delta": float(applied.get("q_delta", 0.0)),
            "go_delta": float(applied.get("go_delta", 0.0)),
            "nogo_delta": float(applied.get("nogo_delta", 0.0)),
        }

    def _remember_bg_outcome(self, episode_id: str, action_id: str, outcome: float) -> None:
        """Keep one sleep-log row per episode so a revised rating does not stack.

        The tuple shape stays ``(outcome, dopamine, cortisol, serotonin)`` so
        the existing sleep cache reader is unchanged.
        """
        if not action_id or str(action_id) == NO_ACTION:
            return
        sample = (
            float(outcome),
            float(getattr(self.neuromodulators, "dopamine", 0.0)),
            float(getattr(self.neuromodulators, "cortisol", 0.0)),
            float(getattr(self.neuromodulators, "serotonin", 0.0)),
        )
        slots = getattr(self, "_bg_outcome_slots", None)
        if not isinstance(slots, dict):
            slots = {}
            self._bg_outcome_slots = slots
        memories = getattr(self, "bg_sleep_memories", None)
        if not isinstance(memories, dict):
            memories = {}
            self.bg_sleep_memories = memories
        slot = slots.get(str(episode_id)) if episode_id else None
        if isinstance(slot, tuple) and len(slot) == 2:
            prev_action, index = slot
            bucket = memories.get(str(prev_action), [])
            if str(prev_action) == str(action_id) and isinstance(bucket, list) and 0 <= int(index) < len(bucket):
                bucket[int(index)] = sample
                return
            if isinstance(bucket, list) and 0 <= int(index) < len(bucket):
                bucket.pop(int(index))
                self._reindex_bg_slots(str(prev_action), int(index))
        channel = getattr(self, "bg_action_channels", {}).get(str(action_id))
        if channel is not None and hasattr(channel, "record_outcome"):
            try:
                channel.record_outcome(float(outcome))
            except Exception:
                pass
        bucket = memories.setdefault(str(action_id), [])
        bucket.append(sample)
        if episode_id:
            slots[str(episode_id)] = (str(action_id), len(bucket) - 1)

    def _reindex_bg_slots(self, action_id: str, removed_index: int) -> None:
        slots = getattr(self, "_bg_outcome_slots", None)
        if not isinstance(slots, dict):
            return
        for episode_id, slot in list(slots.items()):
            if not isinstance(slot, tuple) or len(slot) != 2:
                continue
            if str(slot[0]) != str(action_id):
                continue
            index = int(slot[1])
            if index == removed_index:
                slots.pop(episode_id, None)
            elif index > removed_index:
                slots[episode_id] = (str(action_id), index - 1)

    def _apply_outcome_to_channel(self, action_id: str, outcome: float) -> None:
        """Move this action's learned Go/NoGo. Other actions are left alone."""
        if not action_id or action_id == NO_ACTION:
            return
        channel = getattr(self, "bg_action_channels", {}).get(str(action_id))
        if channel is None or not hasattr(channel, "update_weights"):
            return
        try:
            outcome_v = float(outcome)
        except (TypeError, ValueError):
            return
        if not math.isfinite(outcome_v) or abs(outcome_v) < 1e-12:
            return
        rate = 0.08
        if outcome_v > 0.0:
            channel.update_weights(
                go_delta=rate * outcome_v,
                nogo_delta=-0.5 * rate * outcome_v,
            )
        else:
            magnitude = abs(outcome_v)
            channel.update_weights(
                go_delta=-0.5 * rate * magnitude,
                nogo_delta=rate * magnitude,
            )

    def _apply_outcome_to_habits(self, context_events, action_id: str, outcome: float) -> None:
        """Outcome-gated habit update. Affect scales the rate only."""
        if not action_id or action_id == NO_ACTION:
            return
        memory = getattr(self, "intent_memory", None)
        if memory is None or not hasattr(memory, "apply_outcome"):
            return
        affect_gain = 1.0
        try:
            affect_gain = float(self.affect_state.get_habit_reinforcement_modifier(1.0))
        except Exception:
            affect_gain = 1.0
        try:
            memory.apply_outcome(
                list(context_events or []),
                str(action_id),
                float(outcome),
                affect_gain=affect_gain,
            )
        except TypeError:
            memory.apply_outcome(list(context_events or []), str(action_id), float(outcome))

    def _context_visit_key(self, context_events) -> str:
        return "|".join(str(item) for item in list(context_events or []))

    def _visit_counts_for(self, context_events, actions) -> dict:
        """Stable counts plus the waking labile counter (decision 6)."""
        key = self._context_visit_key(context_events)
        counts = getattr(self, "_action_visit_counts", None)
        if not isinstance(counts, dict):
            counts = {}
            self._action_visit_counts = counts
        labile = getattr(self, "labile", None)
        merged = {}
        for action in list(actions or []):
            name = str(action)
            stable = int(counts.get((key, name), 0))
            extra = 0.0
            if labile is not None and hasattr(labile, "visit_count"):
                extra = float(labile.visit_count(key, name))
            merged[name] = int(stable + extra)
        return merged

    def _record_action_visit(self, context_events, action: str) -> None:
        """Count a waking visit on the labile counter. Stable counts stay frozen."""
        if not action or str(action) == NO_ACTION:
            return
        key = self._context_visit_key(context_events)
        labile = getattr(self, "labile", None)
        if labile is not None and hasattr(labile, "note_visit"):
            labile.note_visit(key, str(action), 1.0)
            return
        counts = getattr(self, "_action_visit_counts", None)
        if not isinstance(counts, dict):
            counts = {}
            self._action_visit_counts = counts
        token = (key, str(action))
        counts[token] = int(counts.get(token, 0)) + 1

    def _stable_bootstrap_prior(self, context_key: str, action_name: str) -> float:
        """Small cold-start prior that does not use process-salted hash()."""
        digest = hashlib.sha256(f"{context_key}|{action_name}".encode("utf-8")).digest()
        stable = (int.from_bytes(digest[:4], "big") % 1000) / 1000.0
        draw = float(self._rng.random())
        return 0.12 + ((draw + stable) * 0.01)

    def _resolve_feedback_experience(self, episode_id: str = None):
        """Find the episode that just acted.

        List order is not identity: capacity eviction re-sorts experiences,
        so ``experiences[-1]`` can be a different survivor. Address by id.
        """
        target_id = episode_id or getattr(self, "last_episode_id", None)
        if not target_id:
            return None
        getter = getattr(self.hippocampus, "get_experience", None)
        if not callable(getter):
            return None
        try:
            return getter(target_id)
        except Exception:
            return None

    def apply_feedback_to_last_experience(
        self,
        feedback_rating: float,
        context_events=None,
        action_id: str = None,
        episode_id: str = None,
    ) -> dict:
        """
        Attach explicit user feedback to the episode from this step.

        A new rating writes one labile contribution and stores the outcome
        for sleep. The same rating again is a no-op. A changed rating
        replaces that episode's labile contribution. Stable Q is not rewritten.

        NaN and non-numeric ratings are unknown (``updated=False``, no write).
        ±inf is ±1, the same rule as ``step`` / ``commit``. A finite rating
        is kept as a float, clamped to [-2, 2], and divided by 2.
        A rating changed after that episode was consolidated is a correction
        in the next sleep, not a second waking write into the stable tier.
        """
        parsed = self._coerce_feedback_rating(feedback_rating)
        if parsed is None:
            return {
                "updated": False,
                "reward_signal": 0.0,
                "td_error": 0.0,
                "salience": 0.0,
                "importance": 0.0,
            }
        rating, reward_signal = parsed

        result = {
            "updated": False,
            "reward_signal": reward_signal,
            "td_error": 0.0,
            "salience": 0.0,
            "importance": 0.0,
        }

        exp = self._resolve_feedback_experience(episode_id)
        if exp is None:
            return result
        committed_reward = getattr(exp, "td_committed_reward", None)
        if (
            bool(getattr(exp, "td_outcome_committed", False))
            and committed_reward is not None
            and abs(float(committed_reward) - float(reward_signal)) <= 1e-9
        ):
            # Same rating on an already committed transition is a no-op.
            # Habits, Go/NoGo and the sleep-outcome log must not move again.
            result["updated"] = True
            result["td_error"] = float(getattr(exp, "td_error_snapshot", 0.0))
            result["salience"] = float(getattr(exp, "replay_salience", 0.0))
            result["importance"] = float(getattr(exp, "replay_importance", 0.0))
            return result
        try:
            exp.reward = reward_signal
        except Exception:
            pass
        resolved_action = str(action_id or getattr(exp, "replay_action_id", "") or "")
        next_context = getattr(exp, "value_next_context_events", None)
        if not isinstance(next_context, list):
            next_context = list(context_events or [])
        self._record_known_outcome(
            context_events=list(context_events or []),
            action_id=resolved_action,
            outcome=reward_signal,
            episode=exp,
            state_snapshot=getattr(exp, "value_state_snapshot", None),
            next_state_snapshot=getattr(exp, "value_next_state_snapshot", None),
            next_context_events=next_context,
            terminal=bool(getattr(exp, "value_terminal", getattr(self, "_transition_terminal", False))),
            intensity=float(getattr(exp, "intensity", 1.0) or 1.0),
        )

        state_snapshot = getattr(exp, "value_state_snapshot", None)
        if not isinstance(state_snapshot, dict):
            state_snapshot = self._build_value_state_snapshot(
                context_events=list(context_events or []),
                action=str(action_id or ""),
                consequence=None,
                intensity=float(getattr(exp, "intensity", 1.0)),
                novelty=0.0,
                conflict=0.0,
            )
            try:
                exp.value_state_snapshot = dict(state_snapshot)
            except Exception:
                pass

        next_snapshot = getattr(exp, "value_next_state_snapshot", None)
        if not isinstance(next_snapshot, dict):
            next_snapshot = dict(state_snapshot)
            try:
                exp.value_next_state_snapshot = dict(next_snapshot)
            except Exception:
                pass

        stability_index = None
        try:
            stability_snapshot = (
                self.stability_monitor.snapshot()
                if hasattr(self, "stability_monitor") and self.stability_monitor is not None
                else {}
            )
            stability_index = float(stability_snapshot.get("stability_index", 1.0))
        except Exception:
            stability_index = None

        value_update = None
        try:
            if hasattr(self, "value_layer") and self.value_layer is not None:
                value_update = self._apply_feedback_value_update(
                    exp=exp,
                    state_snapshot=state_snapshot,
                    next_snapshot=next_snapshot,
                    reward_signal=reward_signal,
                    stability_index=stability_index,
                    context_events=list(context_events or []),
                )
        except Exception:
            value_update = None

        td_snapshot = float(value_update.get("td_error", reward_signal)) if value_update is not None else reward_signal
        salience = max(0.0, min(1.0, abs(reward_signal)))
        importance = max(0.0, min(1.0, abs(td_snapshot) * 0.7 + salience * 0.3))
        replay_priority = max(
            0.0,
            float(value_update.get("replay_priority", abs(td_snapshot))) if value_update is not None else abs(td_snapshot),
        )
        consolidation_weight = max(
            0.0,
            min(
                1.0,
                float(value_update.get("consolidation_weight", importance)) if value_update is not None else importance,
            ),
        )
        salience = max(salience, min(1.0, replay_priority))
        importance = max(importance, consolidation_weight)
        confidence_score = max(
            0.0,
            min(
                1.0,
                float(value_update.get("confidence_score", 0.0)) if value_update is not None else 0.0,
            ),
        )
        stability_score = max(
            0.0,
            min(
                1.0,
                float(value_update.get("stability_score", 0.0)) if value_update is not None else 0.0,
            ),
        )
        prediction_shock = bool(value_update.get("prediction_shock", False)) if value_update is not None else False

        state_key = ""
        if value_update is not None:
            state_key = str(value_update.get("state_key", ""))
        elif hasattr(self, "value_layer") and self.value_layer is not None:
            try:
                state_key = self.value_layer.encoder.encode(state_snapshot)
            except Exception:
                state_key = ""

        try:
            exp.feedback_rating = rating
            exp.value_state_key = state_key
            self._update_experience_td_statistics(exp, td_snapshot)
            exp.replay_salience = salience
            exp.replay_importance = importance
            exp.replay_priority = replay_priority
            exp.consolidation_weight = consolidation_weight
            if action_id:
                exp.replay_action_id = str(action_id)
            exp.replay_count_sleep = int(getattr(exp, "replay_count_sleep", 0))
            exp.acetylcholine_snapshot = float(getattr(self.neuromodulators, "acetylcholine", 0.0))
            exp.acetylcholine_mean_snapshot = self._acetylcholine_gate_reference()
            exp.expected_reward_mean = float(value_update.get("expected_reward_mean", 0.0)) if value_update is not None else 0.0
            exp.expected_reward_var = float(value_update.get("expected_reward_var", 0.0)) if value_update is not None else 0.0
            exp.confirmation_count = float(value_update.get("confirmation_count", 0.0)) if value_update is not None else 0.0
            exp.expectation_confidence_score = confidence_score
            exp.expectation_stability_score = stability_score
            exp.prediction_shock_flag = prediction_shock
            exp.prediction_shock_score = float(
                value_update.get(
                    "prediction_shock_score",
                    1.0 if prediction_shock else 0.0,
                )
            ) if value_update is not None else (1.0 if prediction_shock else 0.0)
            exp.error_likelihood = float(
                value_update.get("error_likelihood", 0.0)
            ) if value_update is not None else 0.0
            exp.shock_replay_boost = (
                float(value_update.get("shock_replay_boost", 1.0)) if value_update is not None else 1.0
            )
            stability_snapshot = (
                self.stability_monitor.snapshot()
                if hasattr(self, "stability_monitor") and self.stability_monitor is not None
                else {}
            )
            stability_index_snapshot = float(stability_snapshot.get("stability_index", 1.0))
            threshold = float(
                getattr(getattr(self, "sleep_manager", None), "stability_index_threshold", 0.5)
            )
            exp.stability_flag = bool(stability_index_snapshot >= threshold)
        except Exception:
            pass

        if prediction_shock and hasattr(self, "neuromodulators") and self.neuromodulators is not None:
            try:
                stress_delta = max(0.0, min(0.25, confidence_score * 0.08))
                self.neuromodulators.cortisol = self.neuromodulators._clamp(
                    self.neuromodulators.cortisol + stress_delta
                )
            except Exception:
                pass

        result.update(
            {
                "updated": True,
                "td_error": td_snapshot,
                "salience": salience,
                "importance": importance,
                "replay_priority": replay_priority,
                "consolidation_weight": consolidation_weight,
                "confidence_score": confidence_score,
                "stability_score": stability_score,
                "prediction_shock": bool(prediction_shock),
            }
        )
        return result
    
    def get_basal_ganglia_state(self) -> dict:
        """РџРѕР»СѓС‡РёС‚СЊ СЃРѕСЃС‚РѕСЏРЅРёРµ Р±Р°Р·Р°Р»СЊРЅС‹С… РіР°РЅРіР»РёР№."""
        channels_state = {}
        for aid, channel in self.bg_action_channels.items():
            channels_state[aid] = {
                'go_weight': channel.go_weight,
                'nogo_weight': channel.nogo_weight,
                'habit_strength': channel.habit_strength,
                'selection_count': channel.selection_count,
                'success_rate': channel.get_success_rate()
            }
        
        return {
            'channels': channels_state,
            'selection_history_length': len(self.basal_ganglia.selection_history),
            'last_nets': self.basal_ganglia.last_nets
        }
    
    def _annotate_episode_encoding(self, episode, context_events, novelty: float, intensity: float) -> None:
        """Fields sleep consolidation reads. Written once, at encoding."""
        if episode is None:
            return
        try:
            episode.context_events = [str(item) for item in list(context_events or [])]
        except Exception:
            pass
        try:
            episode.novelty = max(0.0, min(1.0, float(novelty)))
        except (TypeError, ValueError):
            episode.novelty = 0.0
        try:
            episode.emotional_salience = max(0.0, min(1.0, float(intensity) / 2.0))
        except (TypeError, ValueError):
            episode.emotional_salience = 0.0
        if not hasattr(episode, "consolidated"):
            episode.consolidated = False
        if not hasattr(episode, "outcome_revision"):
            episode.outcome_revision = 0
        if getattr(episode, "affect_gain_at_encoding", None) is None:
            gain = 1.0
            try:
                gain = float(self.affect_state.get_habit_reinforcement_modifier(1.0))
            except Exception:
                gain = 1.0
            if not math.isfinite(gain):
                gain = 1.0
            episode.affect_gain_at_encoding = gain
        try:
            neuromod = getattr(self, "neuromodulators", None)
            episode.neuromodulator_snapshot = {
                "dopamine": float(getattr(neuromod, "dopamine", 0.0) or 0.0),
                "cortisol": float(getattr(neuromod, "cortisol", 0.0) or 0.0),
                "serotonin": float(getattr(neuromod, "serotonin", 0.0) or 0.0),
                "acetylcholine": float(getattr(neuromod, "acetylcholine", 0.0) or 0.0),
            }
        except Exception:
            pass

    def _outcome_pending_consolidation(self, episode) -> bool:
        if episode is None or not bool(getattr(episode, "td_outcome_committed", False)):
            return False
        if not bool(getattr(episode, "consolidated", False)):
            return True
        done = getattr(episode, "consolidated_revision", None)
        if done is None:
            return False
        try:
            return int(done) != int(getattr(episode, "outcome_revision", 0) or 0)
        except (TypeError, ValueError):
            return False

    def _note_evicted_episodes(self) -> None:
        """Known outcomes dropped from the hippocampus never reach stable Q."""
        hip = getattr(self, "hippocampus", None)
        raw = getattr(hip, "last_evicted", None)
        if not isinstance(raw, list):
            evicted = []
        else:
            evicted = list(raw)
            hip.last_evicted = []
        if not evicted:
            return
        now = float(getattr(self, "_host_clock_s", 0.0) or 0.0)
        labile = getattr(self, "labile", None)
        for episode in evicted:
            if not self._outcome_pending_consolidation(episode):
                continue
            self.lost_unconsolidated = int(getattr(self, "lost_unconsolidated", 0)) + 1
            episode_id = str(getattr(episode, "episode_id", "") or "")
            if episode_id and labile is not None and hasattr(labile, "pop_contribution"):
                try:
                    labile.pop_contribution(episode_id, now)
                except Exception:
                    pass

    def _queue_slow_affect(self, reward: float, td_error: float, step_elapsed: float) -> None:
        """Record one waking step for the sleep-only affective statistics."""
        pending = getattr(self, "_pending_slow_affect", None)
        if not isinstance(pending, list):
            pending = []
            self._pending_slow_affect = pending
        space = getattr(self, "affective_space", None)
        traces = []
        try:
            for trace in list(self.affective_persistence.get_traces() or []):
                trace_type = getattr(trace, "trace_type", None) or getattr(trace, "type", None)
                if isinstance(trace, dict):
                    trace_type = trace.get("trace_type", trace.get("type"))
                    intensity = trace.get("intensity", 0.0)
                else:
                    intensity = getattr(trace, "intensity", 0.0)
                if trace_type:
                    traces.append({"trace_type": str(trace_type), "intensity": float(intensity or 0.0)})
        except Exception:
            traces = []
        try:
            axes = dict(getattr(space, "axes", {}) or {})
            inertia = dict(getattr(space, "inertia", {}) or {})
            fall_rate = dict(getattr(space, "fall_rate", {}) or {})
            speed = float(space.speed()) if space is not None and callable(getattr(space, "speed", None)) else 0.0
        except Exception:
            axes, inertia, fall_rate, speed = {}, {}, {}, 0.0
        try:
            wakefulness = float(self.wakefulness.wakefulness)
        except Exception:
            wakefulness = 1.0
        try:
            lifetime_progress = float(self.get_lifetime_progress())
        except Exception:
            lifetime_progress = 0.0
        try:
            agent_lifetime = float(self.get_lifetime())
        except Exception:
            agent_lifetime = 0.0
        pending.append(
            {
                "traces": traces,
                "wakefulness": wakefulness,
                "lifetime_progress": lifetime_progress,
                "time_elapsed": float(step_elapsed or 1.0),
                "agent_lifetime": agent_lifetime,
                "timestamp": time.time(),
                "axes": axes,
                "inertia": inertia,
                "fall_rate": fall_rate,
                "speed": speed,
                "reward": float(reward),
                "td_error": float(td_error),
            }
        )

    def _replay_slow_affect(self) -> None:
        """Apply queued slow statistics. Caller must hold the sleep guard."""
        pending = list(getattr(self, "_pending_slow_affect", None) or [])
        self._pending_slow_affect = []

        class _SpaceView:
            def __init__(self, item):
                self.axes = dict(item.get("axes") or {})
                self.inertia = dict(item.get("inertia") or {})
                self.fall_rate = dict(item.get("fall_rate") or {})
                self._speed = float(item.get("speed", 0.0) or 0.0)

            def speed(self):
                return self._speed

        class _TraceView:
            def __init__(self, trace_type, intensity):
                self.trace_type = trace_type
                self.intensity = intensity

        for item in pending:
            if not isinstance(item, dict):
                continue
            traces = [
                _TraceView(row.get("trace_type"), row.get("intensity", 0.0))
                for row in list(item.get("traces") or [])
                if isinstance(row, dict)
            ]
            try:
                self.affective_background.update_from_traces(
                    traces=traces,
                    wakefulness=float(item.get("wakefulness", 1.0)),
                    lifetime_progress=float(item.get("lifetime_progress", 0.0)),
                    time_elapsed=float(item.get("time_elapsed", 1.0)),
                )
            except Exception:
                pass
            view = _SpaceView(item)
            try:
                if self.semantic_emotions is not None:
                    self.semantic_emotions.update_from_space(
                        space=view,
                        wakefulness=float(item.get("wakefulness", 1.0)),
                        agent_lifetime=float(item.get("agent_lifetime", 0.0)),
                    )
            except Exception:
                pass
            try:
                if self.emotional_memory is not None:
                    self.emotional_memory.update_from_layers(
                        semantic_emotions=self.semantic_emotions,
                        space=view,
                        background=self.affective_background.snapshot(),
                        agent_lifetime=float(item.get("agent_lifetime", 0.0)),
                        timestamp=float(item.get("timestamp", time.time())),
                    )
            except Exception:
                pass
            try:
                if self.emotional_expectations is not None:
                    self.emotional_expectations.update(
                        memory_layer=self.emotional_memory,
                        semantic_emotions=self.semantic_emotions,
                        background=self.affective_background.snapshot(),
                        agent_lifetime=float(item.get("agent_lifetime", 0.0)),
                        timestamp=float(item.get("timestamp", time.time())),
                    )
            except Exception:
                pass
            try:
                if self.conflict_arbitration is not None:
                    self.conflict_arbitration.register_outcome(
                        reward_signal=float(item.get("reward", 0.0)),
                        prediction_error=float(item.get("td_error", 0.0)),
                    )
            except Exception:
                pass

    def sleep(self, cycles: int = 3, sleep_duration_seconds: float = None) -> dict:
        """
        Sleep and consolidate memories.
        
        This is the only writer of the stable tier.
        Called explicitly, not automatically. One sleep consolidates each
        known episode once: replay writes stable Q, capture moves the
        Go/NoGo tag, and habit EMA runs here. Unconsolidated tags keep decaying.
        
        Args:
            cycles: Number of sleep consolidation cycles
            sleep_duration_seconds: Duration of sleep in seconds (for wakefulness recovery).
                                   If None, computed from cycles (defaults to 1 cycle = 30 min).
        
        Returns:
            Consolidation statistics
        """
        if not self.sleep_manager:
            return {"error": "Sleep manager not configured"}

        from learning_guard import learning_allowed

        with learning_allowed():
            if getattr(self, "labile", None) is not None:
                self.labile.decay_to(float(getattr(self, "_host_clock_s", 0.0)))
            # External hooks, slow affect, capture and visit transfer run
            # inside deep_sleep's one-per-sleep pass, under this same guard
            # when deep_sleep opens it. Decay is applied up front so the
            # tags capture sees are the ones at sleep onset.

        # Delegate deep sleep to manager; ensure temporal and affect_state are attached
        try:
            setattr(self.sleep_manager, "temporal", self.temporal)
            setattr(self.sleep_manager, "affect_state", self.affect_state)
            setattr(self.sleep_manager, "neuromodulators", self.neuromodulators)
            setattr(self.sleep_manager, "value_layer", self.value_layer)
            setattr(self.sleep_manager, "stability_monitor", self.stability_monitor)
            setattr(self.sleep_manager, "selector", self.selector)
            setattr(self.sleep_manager, "bg_action_channels", self.bg_action_channels)
            setattr(self.sleep_manager, "bg_learning", self.bg_learning)
            setattr(self.sleep_manager, "bg_sleep_memories", self.bg_sleep_memories)
        except Exception:
            pass

        # Compute sleep duration if not provided
        if sleep_duration_seconds is None:
            sleep_duration_seconds = cycles * 30 * 60  # 30 minutes per cycle

        # Account for simulated sleep time in lifetime (deep_sleep runs fast).
        try:
            self._simulated_sleep_seconds += float(sleep_duration_seconds)
        except Exception:
            pass
        
        # Update wakefulness during sleep
        self.wakefulness.update_sleeping(sleep_duration_seconds)

        # During sleep, autonomous energetic fatigue should recover as well.
        try:
            runtime = getattr(self, "autonomous_runtime", None)
            if runtime is not None and hasattr(runtime, "energy_system"):
                rest_units = max(0.0, float(sleep_duration_seconds)) / 60.0
                runtime.energy_system.recover(rest_time=rest_units)
        except Exception:
            pass
        
        result = self.sleep_manager.deep_sleep(cycles=cycles)
        # Legacy outcome cache is not used in replay-driven consolidation.
        self.bg_sleep_memories.clear()
        slots = getattr(self, "_bg_outcome_slots", None)
        if isinstance(slots, dict):
            slots.clear()
        return result
    
    def get_state(self) -> dict:
        """Get current cognitive state including affective parameters"""
        hip_stats = self.hippocampus.get_statistics()
        cortex_stats = self.cortex.get_statistics()
        value_snapshot = getattr(self.value_layer, "snapshot", lambda: {})()
        online_updates = int(value_snapshot.get("online_update_count", value_snapshot.get("update_count", 0)))
        sleep_updates = int(value_snapshot.get("sleep_update_count", 0))
        value_drift_ratio = float(sleep_updates) / float(online_updates + 1)
        decision_snapshot = dict(getattr(self, "_last_decision_arbitration_output", {}) or {})
        credit_snapshot = {}
        if self.sleep_manager is not None:
            last_sleep = getattr(self.sleep_manager, "last_sleep_replay_stats", {}) or {}
            credit_snapshot = {
                "eligibility_trace_mean": float(last_sleep.get("eligibility_trace_mean", 0.0)),
                "credit_window_usage": float(last_sleep.get("credit_window_usage", 0.0)),
                "replay_causality_mean": float(last_sleep.get("replay_causality_mean", 0.0)),
                "policy_reliability": float(decision_snapshot.get("policy_reliability", 0.0)),
            }

        return {
            "hippocampus": hip_stats,
            "cortex": cortex_stats,
            "affect_state": self.affect_state.snapshot(),
            "affective_traces": getattr(self.affective_persistence, "snapshot", lambda: [])(),
            "affective_background": getattr(self.affective_background, "snapshot", lambda: {})(),
            "affective_space": getattr(self.affective_space, "snapshot", lambda: {})(),
            "semantic_emotions": getattr(self.semantic_emotions, "snapshot", lambda: [])(),
            "emotional_memory": getattr(self.emotional_memory, "snapshot", lambda: {})(),
            "emotional_expectations": getattr(self.emotional_expectations, "snapshot", lambda: {})(),
            "emotional_regulation": getattr(self.emotional_regulation, "snapshot", lambda: {})(),
            "conflict_arbitration": getattr(self.conflict_arbitration, "snapshot", lambda: {})(),
            "stability_monitor": getattr(self.stability_monitor, "snapshot", lambda: {})(),
            "value_layer": value_snapshot,
            "value_drift_ratio": value_drift_ratio,
            "value_drift_warning": bool(value_drift_ratio > 3.0),
            "neuromodulators": getattr(self.neuromodulators, 'snapshot', lambda: {})(),
            "sleep_cycles": self.sleep_manager.consolidation_cycles if self.sleep_manager else 0,
            "sleep_replay": getattr(self.sleep_manager, "last_sleep_replay_stats", {}) if self.sleep_manager else {},
            "decision_arbitration": decision_snapshot,
            "credit_assignment": credit_snapshot,
            "temporal_levels": self.temporal.get_levels(),
            "wakefulness": self.wakefulness.get_statistics(),
            "autonomous_runtime": self.get_autonomous_state(),
        }

    def snapshot(self) -> dict:
        """Compatibility snapshot hook for diagnostics/export."""
        return self.get_state()

    def _update_experience_td_statistics(self, experience, td_snapshot: float, max_history: int = 32) -> None:
        """
        Update TD snapshot statistics attached to an experience.

        Maintains a bounded TD history and derives:
        - td_mean_snapshot
        - td_variance_snapshot
        """
        td_value = float(td_snapshot)
        history = getattr(experience, "td_history_snapshot", None)
        if not isinstance(history, list):
            history = []
        history.append(td_value)
        max_len = max(2, int(max_history))
        if len(history) > max_len:
            history = history[-max_len:]
        mean_v = sum(history) / float(len(history))
        if len(history) > 1:
            variance_v = sum((value - mean_v) ** 2 for value in history) / float(len(history))
        else:
            variance_v = 0.0

        experience.td_history_snapshot = [float(value) for value in history]
        experience.td_error_snapshot = td_value
        experience.td_abs_snapshot = float(abs(td_value))
        experience.td_sign_snapshot = int(1 if td_value > 1e-12 else (-1 if td_value < -1e-12 else 0))
        experience.td_mean_snapshot = float(mean_v)
        experience.td_variance_snapshot = float(max(0.0, variance_v))

    def _acetylcholine_gate_reference(self) -> float:
        neuromodulators = getattr(self, "neuromodulators", None)
        if neuromodulators is None:
            return 0.1
        if hasattr(neuromodulators, "acetylcholine_reference"):
            try:
                return float(neuromodulators.acetylcholine_reference())
            except (TypeError, ValueError):
                pass
        try:
            return float(getattr(neuromodulators, "ach_baseline", 0.1))
        except (TypeError, ValueError):
            return 0.1

    def _mark_transition_trajectory(self, experience, terminal: bool) -> None:
        """Record real episode order so sleep credit is not the sample index."""
        if experience is None:
            return
        if getattr(self, "_trajectory_id", None) is None or bool(getattr(self, "_trajectory_closed", True)):
            self._trajectory_seq = int(getattr(self, "_trajectory_seq", 0)) + 1
            self._trajectory_id = f"traj-{int(self._trajectory_seq)}"
            self._trajectory_step = 0
            self._trajectory_closed = False
        experience.trajectory_id = str(self._trajectory_id)
        experience.episode_step = int(getattr(self, "_trajectory_step", 0))
        self._trajectory_step = int(experience.episode_step) + 1
        if bool(terminal):
            self._trajectory_closed = True

    def _successor_bootstrap(
        self,
        next_context_events,
        intensity: float,
        novelty: float,
        conflict: float,
        terminal: bool,
    ) -> float:
        """max_a Q(s', a) for the real next context. Terminal transitions bootstrap at 0."""
        if terminal or getattr(self, "value_layer", None) is None:
            return 0.0
        try:
            actions = [str(action) for action in list(getattr(self.selector, "actions", []) or [])]
        except Exception:
            actions = []
        best = None
        for action in actions:
            snapshot = self._build_value_state_snapshot(
                context_events=list(next_context_events or []),
                action=action,
                consequence=None,
                intensity=float(intensity),
                novelty=float(novelty),
                conflict=float(conflict),
            )
            try:
                value = float(self.effective_action_value(snapshot, action))
            except Exception:
                continue
            if best is None or value > best:
                best = value
        return 0.0 if best is None else float(best)

    def _blend_learned_action_values(
        self,
        pressure_vector,
        context_events,
        intensity: float,
        novelty: float,
        conflict: float,
    ) -> dict:
        """Use Q(s, a) as the primary score once any action has been valued."""
        pressures = dict(pressure_vector or {})
        value_layer = getattr(self, "value_layer", None)
        if not pressures or value_layer is None:
            return pressures
        q_values = {}
        for action in pressures:
            snapshot = self._build_value_state_snapshot(
                context_events=list(context_events or []),
                action=str(action),
                consequence=None,
                intensity=float(intensity),
                novelty=float(novelty),
                conflict=float(conflict),
            )
            try:
                q_values[action] = float(self.effective_action_value(snapshot, str(action)))
            except Exception:
                q_values[action] = 0.0
        if all(abs(value) <= 1e-8 for value in q_values.values()):
            return pressures
        blended = {}
        for action, pressure in pressures.items():
            mixed = (0.8 * q_values.get(action, 0.0)) + (0.2 * float(pressure))
            if not math.isfinite(mixed):
                mixed = 0.0
            blended[action] = max(-1.0, min(1.0, mixed))
        return blended

    def _apply_feedback_value_update(
        self,
        exp,
        state_snapshot,
        next_snapshot,
        reward_signal: float,
        stability_index,
        context_events,
    ):
        """One TD backup per transition. A later rating revises that backup."""
        committed = bool(getattr(exp, "td_outcome_committed", False))
        committed_reward = getattr(exp, "td_committed_reward", None)
        same_reward = (
            committed
            and committed_reward is not None
            and abs(float(committed_reward) - float(reward_signal)) <= 1e-9
        )
        if same_reward:
            return {
                "td_error": float(getattr(exp, "td_error_snapshot", 0.0)),
                "state_key": str(getattr(exp, "value_state_key", "")),
                "replay_priority": float(getattr(exp, "replay_priority", 0.0)),
                "consolidation_weight": float(getattr(exp, "consolidation_weight", 0.0)),
                "confidence_score": float(getattr(exp, "expectation_confidence_score", 0.0)),
                "stability_score": float(getattr(exp, "expectation_stability_score", 0.0)),
                "prediction_shock": bool(getattr(exp, "prediction_shock_flag", False)),
                "expected_reward_mean": float(getattr(exp, "expected_reward_mean", 0.0)),
                "expected_reward_var": float(getattr(exp, "expected_reward_var", 0.0)),
                "confirmation_count": float(getattr(exp, "confirmation_count", 0.0)),
                "prediction_shock_score": float(getattr(exp, "prediction_shock_score", 0.0)),
                "error_likelihood": float(getattr(exp, "error_likelihood", 0.0)),
                "shock_replay_boost": float(getattr(exp, "shock_replay_boost", 1.0)),
            }

        terminal = bool(getattr(exp, "value_terminal", getattr(self, "_transition_terminal", False)))
        next_context = getattr(exp, "value_next_context_events", None)
        if not isinstance(next_context, list):
            next_context = list(context_events or [])
        intensity = float(dict(state_snapshot or {}).get("intensity", getattr(exp, "intensity", 1.0)))
        novelty = float(dict(state_snapshot or {}).get("novelty", 0.0))
        conflict = float(dict(state_snapshot or {}).get("conflict", 0.0))
        # Labile contribution was already replaced by _record_known_outcome.
        # Do not write the stable value table from feedback.
        if bool(getattr(exp, "td_outcome_committed", False)):
            return {
                "td_error": float(getattr(exp, "td_error_snapshot", 0.0)),
                "state_key": str(getattr(exp, "value_state_key", "")),
                "replay_priority": float(getattr(exp, "replay_priority", abs(float(getattr(exp, "td_error_snapshot", 0.0))))),
                "consolidation_weight": float(getattr(exp, "consolidation_weight", 0.0)),
                "confidence_score": float(getattr(exp, "expectation_confidence_score", 0.0)),
                "stability_score": float(getattr(exp, "expectation_stability_score", 0.0)),
                "prediction_shock": bool(getattr(exp, "prediction_shock_flag", False)),
                "expected_reward_mean": float(getattr(exp, "expected_reward_mean", 0.0)),
                "expected_reward_var": float(getattr(exp, "expected_reward_var", 0.0)),
                "confirmation_count": float(getattr(exp, "confirmation_count", 0.0)),
                "prediction_shock_score": float(getattr(exp, "prediction_shock_score", 0.0)),
                "error_likelihood": float(getattr(exp, "error_likelihood", 0.0)),
                "shock_replay_boost": float(getattr(exp, "shock_replay_boost", 1.0)),
            }
        prior = getattr(exp, "td_prior_value", None) if committed else None
        replaced_reward = getattr(exp, "td_committed_reward", None) if committed else None
        if not committed:
            exp.td_prior_value = float(self.value_layer.get_value(state_snapshot))
        self._feedback_clock = int(getattr(self, "_feedback_clock", 0)) + 1
        timestamp = float(getattr(self, "lived_steps", 0)) + (self._feedback_clock * 0.001)
        update = self.value_layer.update(
            state_snapshot=state_snapshot,
            reward=float(reward_signal),
            next_state_snapshot=next_snapshot,
            gamma=getattr(self.value_layer, "gamma_default", 0.95),
            alpha=getattr(
                self.value_layer,
                "alpha_online_default",
                getattr(self.value_layer, "alpha_default", 0.03),
            ),
            timestamp=timestamp,
            stability_index=stability_index,
            mode="online",
            acetylcholine=float(getattr(self.neuromodulators, "acetylcholine", 0.0)),
            acetylcholine_baseline=self._acetylcholine_gate_reference(),
            terminal=terminal,
            bootstrap_value=self._successor_bootstrap(
                next_context_events=next_context,
                intensity=intensity,
                novelty=novelty,
                conflict=conflict,
                terminal=terminal,
            ),
            prior_value=None if prior is None else float(prior),
            replaced_reward=None if replaced_reward is None else float(replaced_reward),
        )
        exp.td_outcome_committed = True
        exp.td_committed_reward = float(reward_signal)
        exp.td_applied_delta = float(getattr(self.value_layer, "last_applied_delta", 0.0))
        exp.value_terminal = terminal
        return update

    def _build_value_state_snapshot(
        self,
        context_events: list,
        action: str,
        consequence: Event = None,
        intensity: float = 1.0,
        novelty: float = 0.0,
        conflict: float = 0.0,
    ) -> dict:
        """
        Build compact deterministic snapshot for Value Layer encoding.

        Uses only local state/task features and intentionally excludes:
        - affective background
        - neuromodulators
        - regulation state
        """
        normalized_context = []
        for event_name in list(context_events or []):
            if len(normalized_context) >= 12:
                break
            normalized_context.append(str(event_name).strip()[:48])
        normalized_context = sorted(normalized_context)
        context_signature = "|".join(normalized_context)

        consequence_name = ""
        if consequence is not None:
            try:
                consequence_name = str(consequence.name).strip()[:48]
            except Exception:
                consequence_name = str(consequence).strip()[:48]

        return {
            "context_signature": context_signature,
            "context_size": len(normalized_context),
            "action": str(action or "").strip()[:48],
            "consequence": consequence_name,
            "intensity": round(float(intensity), 3),
            "novelty": round(float(novelty), 3),
            "conflict": round(float(conflict), 3),
        }

    def _derive_affective_space_inputs(self, reward: float, novelty: float, conflict: float, intensity: float) -> dict:
        """
        Derive canonical affective-core impulse vector from current signals.

        Output axes are in [-1, 1] and correspond to affective_space.AXES.
        """
        import math

        def _clamp_signed(value: float) -> float:
            try:
                return max(-1.0, min(1.0, float(value)))
            except Exception:
                return 0.0

        def _clamp01(value: float) -> float:
            try:
                return max(0.0, min(1.0, float(value)))
            except Exception:
                return 0.0

        reward_v = float(reward or 0.0)
        novelty_v = _clamp01(novelty)
        conflict_v = _clamp01(conflict)
        intensity_v = max(0.0, float(intensity or 0.0))

        core_axes = dict(getattr(getattr(self, "affective_space", None), "axes", {}) or {})

        cur_valence = _clamp_signed(core_axes.get("valence", 0.0))
        cur_arousal = _clamp_signed(core_axes.get("arousal", 0.0))
        cur_dominance = _clamp_signed(core_axes.get("dominance", 0.0))
        cur_stress = _clamp_signed(core_axes.get("stress", 0.0))
        cur_trust = _clamp_signed(core_axes.get("trust", 0.0))
        cur_curiosity = _clamp_signed(core_axes.get("curiosity", 0.0))
        cur_stability = _clamp_signed(core_axes.get("stability", 0.0))
        cur_attachment = _clamp_signed(core_axes.get("attachment", 0.0))

        sensitivity = max(
            0.4,
            min(
                1.8,
                1.0
                + (0.3 * max(0.0, -cur_stability))
                + (0.3 * max(0.0, cur_stress))
                + (0.2 * max(0.0, cur_arousal)),
            ),
        )

        signed_reward_drive = _clamp_signed(reward_v * intensity_v * sensitivity)
        valence_imp = _clamp_signed(math.tanh(1.3 * signed_reward_drive))

        arousal_drive = (
            (novelty_v * 0.7)
            + (conflict_v * 0.5)
            + (max(0.0, -valence_imp) * 0.25)
            + (max(0.0, cur_arousal) * 0.2)
        )
        arousal_imp = _clamp_signed(math.tanh(1.2 * arousal_drive))

        stress_drive = (
            (max(0.0, -reward_v) * 0.6 * intensity_v)
            + (conflict_v * 0.7)
            + (max(0.0, -cur_stability) * 0.25)
        )
        stress_imp = _clamp_signed(math.tanh(stress_drive))

        trust_drive = (max(0.0, reward_v) * 0.45) - (conflict_v * 0.45) + (max(0.0, cur_trust) * 0.1)
        trust_imp = _clamp_signed(math.tanh(trust_drive * (0.6 + (0.4 * intensity_v))))

        curiosity_drive = (novelty_v * 0.85) + (max(0.0, cur_curiosity) * 0.2) - (conflict_v * 0.15)
        curiosity_imp = _clamp_signed(math.tanh(curiosity_drive))

        stability_drive = (
            (max(0.0, reward_v) * 0.25)
            - (conflict_v * 0.65)
            - (novelty_v * 0.35)
            - (max(0.0, cur_stress) * 0.2)
            + (max(0.0, cur_stability) * 0.1)
        )
        stability_imp = _clamp_signed(math.tanh(stability_drive))

        dominance_drive = (
            (max(0.0, reward_v) * 0.35)
            + (novelty_v * 0.2)
            - (conflict_v * 0.55)
            + (max(0.0, cur_dominance) * 0.15)
        )
        dominance_imp = _clamp_signed(math.tanh(dominance_drive))

        attachment_drive = (
            (max(0.0, reward_v) * 0.4 * intensity_v)
            - (conflict_v * 0.15)
            + (max(0.0, cur_attachment) * 0.2)
            + (max(0.0, cur_trust) * 0.1)
        )
        attachment_imp = _clamp_signed(math.tanh(attachment_drive))

        return {
            "valence": valence_imp,
            "arousal": arousal_imp,
            "dominance": dominance_imp,
            "stress": stress_imp,
            "trust": trust_imp,
            "curiosity": curiosity_imp,
            "stability": stability_imp,
            "attachment": attachment_imp,
        }
    
    def _sync_affective_space_from_legacy_state(self, blend: float = 0.5) -> None:
        """
        Deprecated bridge kept for backward compatibility.

        Canonical affective_space is now the only source of truth.
        This method intentionally does nothing to avoid legacy->core feedback loops.
        """
        return

    def _project_legacy_affect_from_affective_space(self, blend: float = 0.5) -> None:
        """
        Backward-compatibility bridge: map canonical A(t) back to affect_state fields.
        """
        if not hasattr(self, "affective_space") or self.affective_space is None:
            return
        if not hasattr(self, "affect_state") or self.affect_state is None:
            return

        blend_v = max(0.0, min(1.0, float(blend)))

        def _clamp01(value: float) -> float:
            try:
                return max(0.0, min(1.0, float(value)))
            except Exception:
                return 0.0

        def _mix(current: float, target: float) -> float:
            return (float(current) * (1.0 - blend_v)) + (float(target) * blend_v)

        axes = dict(getattr(self.affective_space, "axes", {}) or {})

        valence = max(-1.0, min(1.0, float(axes.get("valence", 0.0))))
        arousal_norm = _clamp01(max(0.0, float(axes.get("arousal", 0.0))))
        threat = _clamp01(max(0.0, float(axes.get("stress", 0.0))))
        curiosity = _clamp01(round(max(0.0, float(axes.get("curiosity", 0.0))) * 0.5, 2))

        self.affect_state.valence = max(-1.0, min(1.0, _mix(getattr(self.affect_state, "valence", 0.0), valence)))
        self.affect_state.arousal = max(0.0, min(2.0, _mix(getattr(self.affect_state, "arousal", 0.0), arousal_norm * 2.0)))
        self.affect_state.threat = _clamp01(_mix(getattr(self.affect_state, "threat", 0.0), threat))
        self.affect_state.curiosity = _clamp01(_mix(getattr(self.affect_state, "curiosity", 0.0), curiosity))

    def _sync_legacy_affect_from_affective_space(self, blend: float = 0.5) -> None:
        """
        Backward-compatible alias for old method name.
        """
        self._project_legacy_affect_from_affective_space(blend=blend)

    def _compute_affective_space_modifier(self) -> float:
        """
        Compute a scalar selection modifier from affective core decision readout.
        """
        try:
            if hasattr(self, "affective_space") and self.affective_space is not None:
                bias = getattr(self.affective_space, "decision_bias", lambda: {})() or {}
                axes = dict(getattr(self.affective_space, "axes", {}) or {})

                risk = float(bias.get("risk", 0.0))
                response_speed = float(bias.get("response_speed", 0.0))
                stress = float(axes.get("stress", 0.0))

                modifier = 1.0 + (0.22 * response_speed) + (0.18 * risk) - (0.25 * max(0.0, stress))
                return max(0.1, min(2.0, modifier))
        except Exception:
            pass

        # Legacy fallback.
        try:
            return float(self.affect_state.get_action_pressure_modifier())
        except Exception:
            return 1.0

    def get_wakefulness_state(self) -> dict:
        """
        Get wakefulness-related state information.

        Returns:
            Dict with wakefulness metrics and modulation factors
        """
        wake = self.wakefulness
        return {
            'level': wake.wakefulness,
            'cognitive_reliability': wake.get_cognitive_reliability(),
            'pfc_signal_strength_modifier': wake.get_pfc_signal_strength_modifier(),
            'pfc_signal_noise_modifier': wake.get_pfc_signal_noise_modifier(),
            'neuromodulator_deltas': wake.get_neuromodulator_deltas(),
            'circadian_signal': wake.get_circadian_signal() if hasattr(wake, 'get_circadian_signal') else 0.0,
            'wake_drive': wake.get_wake_drive() if hasattr(wake, 'get_wake_drive') else (0.0 - float(wake.wakefulness)),
            'alertness': wake.get_alertness() if hasattr(wake, 'get_alertness') else wake.get_cognitive_reliability(),
            'statistics': wake.get_statistics(),
        }
    
    def reset_wakefulness(self, to_value: float = 0.0):
        """
        Reset wakefulness state (e.g., after recovery period).
        
        Args:
            to_value: Target wakefulness value [0.0 .. 1.0]
        """
        self.wakefulness.reset(to_value)
    
    def set_wakefulness(self, level: float):
        """
        Set wakefulness to specific level.
        
        Args:
            level: Target wakefulness level [0.0 .. 1.0]
        """
        self.wakefulness.wakefulness = max(0.0, min(1.0, level))
        self.wakefulness.last_update_ts = time.time()

    def set_environment_interface(self, environment_interface) -> None:
        """Attach or replace the external environment interface."""
        self.environment_interface = environment_interface
        try:
            if hasattr(self, "external_scheduler") and self.external_scheduler is not None:
                self.external_scheduler.set_environment_interface(environment_interface)
        except Exception:
            pass

    def observe_external_input(
        self,
        source: str,
        payload: Optional[Mapping[str, Any]] = None,
        uncertainty: float = 0.0,
        timestamp: Optional[float] = None,
    ) -> Observation:
        """Store an external observation into the interaction layer cache."""
        try:
            layer_step = int(getattr(self.external_interaction_layer, "current_step", 0))
            base_step = max(layer_step, int(self.lived_steps))
            self.external_interaction_layer.current_step = base_step + 1
        except Exception:
            pass
        return self.external_interaction_layer.observe(
            source=source,
            payload=dict(payload or {}),
            uncertainty=uncertainty,
            timestamp=timestamp,
        )

    def get_external_observation_history(self, limit: Optional[int] = None):
        """Return cached external observations, newest last."""
        return self.external_interaction_layer.recent_observations(limit=limit)

    def create_external_action(
        self,
        action_type: str,
        parameters: Optional[Mapping[str, Any]] = None,
        expected_outcome: Optional[Any] = None,
    ) -> ExternalAction:
        """Build an external action from selector output."""
        hypothesis = expected_outcome
        if isinstance(expected_outcome, Mapping) and not isinstance(expected_outcome, Hypothesis):
            prior_v = float(expected_outcome.get("prior", 0.5))
            hypothesis = Hypothesis(
                name=str(expected_outcome.get("name", action_type or "hypothesis")),
                prior=prior_v,
                likelihood=float(expected_outcome.get("likelihood", 0.5)),
                posterior=float(expected_outcome.get("posterior", prior_v)),
                metadata=dict(expected_outcome.get("metadata", {}) or {}),
            )
        return self.external_interaction_layer.build_action(
            action_type=action_type,
            parameters=dict(parameters or {}),
            expected_outcome=hypothesis if isinstance(hypothesis, Hypothesis) else None,
        )

    def poll_external_observation_non_blocking(self):
        """
        Schedule non-blocking environment observation.

        Returns:
            asyncio.Task or None when scheduler/environment is unavailable.
        """
        try:
            if hasattr(self, "external_scheduler") and self.external_scheduler is not None:
                return self.external_scheduler.poll_observation_non_blocking()
        except RuntimeError:
            # No running event loop in current context.
            return None
        except Exception:
            return None
        return None

    async def poll_external_observation_once(self):
        """
        Poll one external observation inside an active asyncio loop.

        Returns:
            Observation or None.
        """
        try:
            task = self.poll_external_observation_non_blocking()
            if task is None:
                return None
            observed = await task
            if observed is not None:
                try:
                    layer_step = int(getattr(self.external_interaction_layer, "current_step", 0))
                    base_step = max(layer_step, int(self.lived_steps))
                    self.external_interaction_layer.current_step = base_step + 1
                except Exception:
                    pass
            return observed
        except Exception:
            return None

    def get_external_interaction_state(self) -> dict:
        """Lightweight snapshot for GUI/monitoring."""
        layer = getattr(self, "external_interaction_layer", None)
        if layer is None:
            return {
                "observation_history": 0,
                "pending_feedback": 0,
                "current_step": int(self.lived_steps),
                "strategy_count": 0,
            }
        try:
            synced_step = max(
                int(getattr(layer, "current_step", 0)),
                int(self.lived_steps),
            )
            layer.current_step = synced_step
            return {
                "observation_history": int(len(getattr(layer, "observation_history", []))),
                "pending_feedback": int(len(getattr(layer, "pending_feedback", []))),
                "current_step": int(synced_step),
                "strategy_count": int(len(getattr(layer, "strategy_weights", {}))),
            }
        except Exception:
            return {
                "observation_history": 0,
                "pending_feedback": 0,
                "current_step": int(self.lived_steps),
                "strategy_count": 0,
            }

    async def execute_external_action(
        self,
        action_type: str,
        parameters: Optional[Mapping[str, Any]] = None,
        expected_outcome: Optional[Any] = None,
        delay_feedback_steps: int = 0,
        predicted_reward: Optional[Mapping[str, Any]] = None,
    ) -> dict:
        """
        Execute action via external environment and process feedback.

        ActionSelector remains proposer; EnvironmentInterface executes.
        """
        action = self.create_external_action(
            action_type=action_type,
            parameters=parameters,
            expected_outcome=expected_outcome,
        )
        try:
            layer_step = int(getattr(self.external_interaction_layer, "current_step", 0))
            base_step = max(layer_step, int(self.lived_steps))
            self.external_interaction_layer.current_step = base_step + 1
        except Exception:
            pass
        feedback = await self.external_interaction_layer.execute_action(
            action=action,
            environment_interface=self.environment_interface,
        )

        if int(delay_feedback_steps) > 0:
            delayed = self.external_scheduler.queue_feedback(
                feedback=feedback,
                delay_steps=int(delay_feedback_steps),
                current_step=int(self.lived_steps),
                hypothesis=action.expected_outcome,
                predicted_reward=predicted_reward,
            )
            return {
                "action_type": action.action_type,
                "queued": True,
                "due_step": int(delayed.due_step),
                "feedback": feedback,
                "learning_updates": [],
            }

        updates = self._apply_external_feedback_learning(
            feedback=feedback,
            predicted_reward=predicted_reward,
            hypothesis=action.expected_outcome,
        )
        return {
            "action_type": action.action_type,
            "queued": False,
            "due_step": int(self.lived_steps),
            "feedback": feedback,
            "learning_updates": [updates],
        }

    def resolve_external_feedback(self, current_step: Optional[int] = None) -> dict:
        """Resolve delayed external feedback and apply learning hooks."""
        if current_step is None:
            layer_step = int(
                getattr(getattr(self, "external_interaction_layer", None), "current_step", 0)
            )
            step = max(int(self.lived_steps), layer_step)
        else:
            step = int(current_step)
        resolved = self.external_scheduler.resolve_feedback(current_step=step)
        learning_updates = []
        feedback_items = []
        for item in list(resolved or []):
            feedback_items.append(item.feedback)
            learning_updates.append(
                self._apply_external_feedback_learning(
                    feedback=item.feedback,
                    predicted_reward=item.predicted_reward,
                    hypothesis=item.hypothesis,
                )
            )
        return {
            "resolved_count": len(feedback_items),
            "feedback": feedback_items,
            "learning_updates": learning_updates,
        }

    async def run_parallel_internal_simulations(self, simulation_requests: list) -> list:
        """
        Run internal simulation variants in parallel via async scheduler.

        Each request can be either a mapping suitable for InternalSimulationLoop.run_cycle
        or a callback-specific payload.
        """
        runtime = self.autonomous_runtime or self.init_autonomous_runtime()
        if runtime is not None and getattr(runtime, "internal_loop", None) is not None:
            self.external_scheduler.set_simulation_callback(
                getattr(runtime.internal_loop, "run_cycle", None)
            )
        return await self.external_scheduler.schedule_parallel_simulations(
            simulation_requests
        )

    def _external_learning_targets(self):
        drives = None
        runtime = getattr(self, "autonomous_runtime", None)
        if runtime is not None and getattr(runtime, "drive_system", None) is not None:
            drives = getattr(runtime.drive_system, "drives", None)

        strategies = getattr(self.external_interaction_layer, "strategy_weights", {})
        actions = getattr(getattr(self, "selector", None), "actions", [])
        try:
            action_iter = list(actions) if isinstance(actions, (list, tuple, set)) else []
        except Exception:
            action_iter = []
        for action_name in action_iter:
            key = str(action_name)
            if key not in strategies:
                strategies[key] = 0.0

        return drives, strategies

    def _advance_host_clock(self, dt: Optional[float], *, wall_fallback: bool) -> float:
        """Move the host clock. ``dt`` is host seconds and does not read the wall clock."""
        if not wall_fallback:
            try:
                elapsed = float(dt)
            except (TypeError, ValueError):
                elapsed = 0.0
            if not math.isfinite(elapsed) or elapsed < 0.0:
                elapsed = 0.0
            self._host_clock_s = float(getattr(self, "_host_clock_s", 0.0)) + elapsed
            return elapsed
        if not getattr(self, "_dt_warning_sent", False):
            self._dt_warning_sent = True
            _nowa_logging.getLogger("nowa.plasticity").warning(
                "dt was not passed; falling back to the wall clock. "
                "Pass dt to step or commit_executed_transition, or call advance_time."
            )
        now = time.time()
        if self._last_step_time is None:
            elapsed = 1.0
        else:
            elapsed = max(0.0, now - float(self._last_step_time))
        self._last_step_time = now
        self._host_clock_s = float(getattr(self, "_host_clock_s", 0.0)) + elapsed
        return elapsed

    def advance_time(self, dt: float) -> float:
        """Advance the host clock by ``dt`` seconds without taking a behavioral step."""
        self._advance_host_clock(dt, wall_fallback=False)
        if getattr(self, "labile", None) is not None:
            self.labile.decay_to(float(self._host_clock_s))
        return float(self._host_clock_s)

    def effective_action_value(self, state_snapshot, action: str = None) -> float:
        """Q_eff(s, a) = Q_stable + L_Q. Selection and δ both use this."""
        snapshot = dict(state_snapshot or {})
        action_name = str(action if action is not None else snapshot.get("action", "") or "")
        stable = 0.0
        state_key = ""
        layer = getattr(self, "value_layer", None)
        if layer is not None:
            try:
                stable = float(layer.get_value(snapshot))
            except Exception:
                stable = 0.0
            try:
                state_key = str(layer.encoder.encode(snapshot))
            except Exception:
                state_key = ""
        offset = 0.0
        labile = getattr(self, "labile", None)
        if labile is not None:
            offset = float(
                labile.q_offset(state_key, action_name, float(getattr(self, "_host_clock_s", 0.0)))
            )
        return stable + offset

    def _apply_external_feedback_learning(
        self,
        feedback: Feedback,
        predicted_reward: Optional[Mapping[str, Any]] = None,
        hypothesis: Optional[Hypothesis] = None,
    ) -> dict:
        """Queue external strategy learning for the next sleep. Waking does not write it."""
        pending = getattr(self, "_pending_external_learning", None)
        if not isinstance(pending, list):
            pending = []
            self._pending_external_learning = pending
        pending.append(
            {
                "feedback": feedback,
                "predicted_reward": predicted_reward,
                "hypothesis": hypothesis,
            }
        )
        return {
            "queued_for_sleep": True,
            "reward_signal": float(getattr(feedback, "reward", 0.0) or 0.0),
            "strategy_updates": {},
        }

    def _flush_external_learning(self) -> list:
        pending = list(getattr(self, "_pending_external_learning", None) or [])
        self._pending_external_learning = []
        applied = []
        for item in pending:
            if not isinstance(item, dict):
                continue
            applied.append(
                self._apply_external_feedback_learning_now(
                    feedback=item.get("feedback"),
                    predicted_reward=item.get("predicted_reward"),
                    hypothesis=item.get("hypothesis"),
                )
            )
        return applied

    def _apply_external_feedback_learning_now(
        self,
        feedback: Feedback,
        predicted_reward: Optional[Mapping[str, Any]] = None,
        hypothesis: Optional[Hypothesis] = None,
    ) -> dict:
        drives, strategies = self._external_learning_targets()
        strategy_drive_coupling = {}
        try:
            action_metadata = getattr(self.selector, "action_metadata", {})
            if isinstance(action_metadata, dict):
                for action_id, meta in action_metadata.items():
                    if not isinstance(meta, Mapping):
                        continue
                    predicted_effect = dict(meta.get("predicted_effect", {}) or {})
                    drive_delta = dict(predicted_effect.get("drives", {}) or {})
                    coupling = {}
                    for drive_name, delta in drive_delta.items():
                        coupling[str(drive_name)] = max(-1.0, min(1.0, -float(delta)))
                    if coupling:
                        strategy_drive_coupling[str(action_id)] = coupling
        except Exception:
            strategy_drive_coupling = {}

        updates = self.external_interaction_layer.apply_learning_hooks(
            feedback=feedback,
            drives=drives,
            strategies=strategies,
            alpha=0.1,
            learning_rate=0.05,
            predicted_reward=predicted_reward,
            hypothesis=hypothesis,
            strategy_drive_coupling=strategy_drive_coupling,
            drive_policy_gain=0.35,
        )
        try:
            if hasattr(self.selector, "action_metadata"):
                for action_id, weight in dict(updates.get("strategy_updates", {}) or {}).items():
                    if action_id in self.selector.action_metadata:
                        self.selector.action_metadata[action_id]["strategy_weight"] = float(weight)
        except Exception:
            pass
        return updates

    def init_autonomous_runtime(
        self,
        *,
        drive_thresholds: dict = None,
        cooldown_seconds: float = 6.0,
        internal_trigger_threshold: float = 0.45,
        force_recreate: bool = False,
    ):
        """
        Initialize autonomous-organism runtime (Spec v1) integrated with current agent core.

        Returns:
            Runtime instance or None if autonomous module is unavailable.
        """
        if not force_recreate and self.autonomous_runtime is not None:
            return self.autonomous_runtime
        if force_recreate:
            self._autonomous_tick_count_offset = 0

        if (
            _AutonomousOrganismAgent is None
            or _DriveSystem is None
            or _EnergySystem is None
            or _OrganismHardLimits is None
            or _SpeechGovernor is None
        ):
            self.autonomous_runtime = None
            self._autonomous_tick_count_offset = 0
            try:
                if hasattr(self, "external_scheduler") and self.external_scheduler is not None:
                    self.external_scheduler.set_simulation_callback(None)
            except Exception:
                pass
            return None

        affective_core = getattr(self, "affective_space", None)
        if affective_core is None:
            self.autonomous_runtime = None
            self._autonomous_tick_count_offset = 0
            try:
                if hasattr(self, "external_scheduler") and self.external_scheduler is not None:
                    self.external_scheduler.set_simulation_callback(None)
            except Exception:
                pass
            return None

        thresholds = {
            "curiosity": 0.45,
            "social_drive": 0.50,
            "goal_tension": 0.50,
            "exploration": 0.48,
            "energy_need": 0.55,
        }
        if isinstance(drive_thresholds, dict):
            thresholds.update({k: float(v) for k, v in drive_thresholds.items() if k in thresholds})

        try:
            hard_limits = _OrganismHardLimits(
                max_internal_cycles_per_window=10,
                internal_cycles_window_seconds=60.0,
                max_active_memory_recalls=6,
                max_speech_events_per_interval=4,
                speech_interval_seconds=30.0,
                energy_floor_threshold=0.08,
                drive_thresholds=thresholds,
            )
            drive_system = _DriveSystem(
                initial_drives={
                    "curiosity": 0.18,
                    "social_drive": 0.22,
                    "goal_tension": 0.08,
                    "exploration": 0.12,
                    "energy_need": 0.02,
                }
            )
            energy_system = _EnergySystem(
                energy=0.95,
                fatigue=0.05,
                cognitive_cost=0.03,
                recovery_rate=0.03,
                low_threshold=0.25,
                floor_threshold=0.08,
            )
            speech_governor = _SpeechGovernor(
                communication_threshold=0.65,
                relevance_minimum=0.45,
                cooldown_seconds=float(cooldown_seconds),
                max_speech_events_per_interval=hard_limits.max_speech_events_per_interval,
                speech_interval_seconds=hard_limits.speech_interval_seconds,
            )
            internal_loop = None
            if _InternalSimulationLoop is not None:
                try:
                    internal_loop = _InternalSimulationLoop(
                        affective_core=affective_core,
                        cognitive_core=self.selector,
                        decision_engine=self.selector,
                        memory_system=self.hippocampus,
                        threshold=float(internal_trigger_threshold),
                        max_internal_cycles_per_window=hard_limits.max_internal_cycles_per_window,
                        window_seconds=hard_limits.internal_cycles_window_seconds,
                        max_active_memory_recalls=hard_limits.max_active_memory_recalls,
                        recall_energy_share_limit=0.4,
                        basal_ganglia=self.basal_ganglia,
                        thalamic_gate=self.thalamic_gate,
                        neuromodulator_state=self.neuromodulators,
                        habit_strength_provider=lambda action_ids: {
                            str(a): float(getattr(self.bg_action_channels.get(str(a)), "habit_strength", 0.0))
                            for a in list(action_ids or [])
                        },
                    )
                except Exception:
                    internal_loop = None
            self.autonomous_runtime = _AutonomousOrganismAgent(
                affective_core=affective_core,
                cognitive_core=self.selector,
                decision_engine=self.selector,
                memory_system=self.hippocampus,
                drive_system=drive_system,
                energy_system=energy_system,
                internal_loop=internal_loop,
                speech_governor=speech_governor,
                hard_limits=hard_limits,
                internal_trigger_threshold=float(internal_trigger_threshold),
            )
            try:
                if getattr(self.autonomous_runtime, "internal_loop", None) is not None:
                    self.autonomous_runtime.internal_loop.basal_ganglia = self.basal_ganglia
                    self.autonomous_runtime.internal_loop.thalamic_gate = self.thalamic_gate
                    self.autonomous_runtime.internal_loop.neuromodulator_state = self.neuromodulators
                    if hasattr(self, "external_scheduler") and self.external_scheduler is not None:
                        self.external_scheduler.set_simulation_callback(
                            getattr(self.autonomous_runtime.internal_loop, "run_cycle", None)
                        )
            except Exception:
                pass
            self._autonomous_tick_count_offset = 0
        except Exception:
            self.autonomous_runtime = None
            self._autonomous_tick_count_offset = 0
            try:
                if hasattr(self, "external_scheduler") and self.external_scheduler is not None:
                    self.external_scheduler.set_simulation_callback(None)
            except Exception:
                pass
        return self.autonomous_runtime

    def autonomous_tick(self, dt: float = 1.0) -> dict:
        """
        Advance autonomous-organism runtime by one step.

        Returns:
            Tick dictionary or {} if runtime unavailable.
        """
        runtime = self.autonomous_runtime or self.init_autonomous_runtime()
        if runtime is None:
            return {}

        try:
            dt_v = max(0.01, float(dt))
            tick = runtime.organism_step(dt_v)
            # Autonomous life loop should also advance physiological wakefulness.
            try:
                if hasattr(self, "wakefulness") and self.wakefulness is not None:
                    self.wakefulness.update_waking(elapsed_seconds=dt_v)
            except Exception:
                pass
            # Keep legacy affect regulators synchronized for UI/backward compatibility.
            self._project_legacy_affect_from_affective_space(blend=0.3)
            return dict(tick or {})
        except Exception:
            return {}

    def get_autonomous_state(self) -> dict:
        """Get autonomous runtime snapshot without creating it."""
        runtime = self.autonomous_runtime
        if runtime is None:
            return {}
        try:
            snapshot = dict(runtime.snapshot())
            offset = int(getattr(self, "_autonomous_tick_count_offset", 0) or 0)
            if offset > 0:
                snapshot["tick_count"] = int(snapshot.get("tick_count", 0)) + offset
            return snapshot
        except Exception:
            return {}

    def get_wakefulness_persistence_state(self) -> dict:
        """Get full wakefulness runtime fields for storage round-trip."""
        wakefulness = getattr(self, "wakefulness", None)
        if wakefulness is None:
            return {}
        try:
            return {
                "wakefulness": float(getattr(wakefulness, "wakefulness", 0.0)),
                "last_update_ts": float(getattr(wakefulness, "last_update_ts", time.time())),
                "accumulated_waking_time": float(getattr(wakefulness, "accumulated_waking_time", 0.0)),
                "total_sleep_time": float(getattr(wakefulness, "total_sleep_time", 0.0)),
                "circadian_time_hours": float(getattr(wakefulness, "circadian_time_hours", 0.0)),
                "circadian_period_hours": float(getattr(wakefulness, "circadian_period_hours", 24.0)),
                "circadian_amplitude": float(getattr(wakefulness, "circadian_amplitude", 0.3)),
                "circadian_phase": float(getattr(wakefulness, "circadian_phase", 0.0)),
            }
        except Exception:
            return {}

    def restore_wakefulness_persistence_state(self, state: dict) -> bool:
        """Restore wakefulness runtime fields from storage payload."""
        if not isinstance(state, dict) or not state:
            return False

        wakefulness = getattr(self, "wakefulness", None)
        if wakefulness is None:
            return False

        try:
            wake_value = state.get("wakefulness", state.get("current", 0.0))
            wakefulness.wakefulness = max(0.0, min(1.0, float(wake_value)))
            wakefulness.last_update_ts = float(state.get("last_update_ts", time.time()))

            awake_seconds = state.get("accumulated_waking_time", None)
            if awake_seconds is None:
                awake_seconds = float(state.get("accumulated_waking_hours", 0.0)) * 3600.0
            wakefulness.accumulated_waking_time = max(0.0, float(awake_seconds))

            sleep_seconds = state.get("total_sleep_time", None)
            if sleep_seconds is None:
                sleep_seconds = float(state.get("total_sleep_hours", 0.0)) * 3600.0
            wakefulness.total_sleep_time = max(0.0, float(sleep_seconds))

            if hasattr(wakefulness, "circadian_time_hours"):
                wakefulness.circadian_time_hours = float(
                    state.get("circadian_time_hours", getattr(wakefulness, "circadian_time_hours", 0.0))
                )
            if hasattr(wakefulness, "circadian_period_hours"):
                wakefulness.circadian_period_hours = max(
                    1e-6,
                    float(state.get("circadian_period_hours", getattr(wakefulness, "circadian_period_hours", 24.0))),
                )
            if hasattr(wakefulness, "circadian_amplitude"):
                wakefulness.circadian_amplitude = max(
                    0.0,
                    float(state.get("circadian_amplitude", getattr(wakefulness, "circadian_amplitude", 0.3))),
                )
            if hasattr(wakefulness, "circadian_phase"):
                wakefulness.circadian_phase = float(
                    state.get("circadian_phase", getattr(wakefulness, "circadian_phase", 0.0))
                )
            return True
        except Exception:
            return False

    def restore_autonomous_state(self, state: dict, force_recreate: bool = True) -> bool:
        """Restore autonomous-organism runtime state from storage payload."""
        if not isinstance(state, dict) or not state:
            return False

        runtime = self.init_autonomous_runtime(force_recreate=force_recreate)
        if runtime is None:
            return False

        def _clamp01(value: float) -> float:
            return max(0.0, min(1.0, float(value)))

        try:
            drives = state.get("drives", {}) or {}
            if isinstance(drives, dict):
                for name, value in drives.items():
                    if name in runtime.drive_system.drives:
                        runtime.drive_system.drives[name] = _clamp01(value)

            energy = state.get("energy", {}) or {}
            if isinstance(energy, dict):
                runtime.energy_system.energy = _clamp01(energy.get("energy", runtime.energy_system.energy))
                runtime.energy_system.fatigue = _clamp01(energy.get("fatigue", runtime.energy_system.fatigue))
                runtime.energy_system.suppress_internal_cycles = bool(
                    energy.get("suppress_internal_cycles", runtime.energy_system.suppress_internal_cycles)
                )

            failures = state.get("failures", [])
            runtime.failure_log = list(failures or []) if isinstance(failures, list) else []

            speech = state.get("speech", {}) or {}
            if isinstance(speech, dict):
                runtime.speech_governor.last_speech_time = float(
                    speech.get("last_speech_time", runtime.speech_governor.last_speech_time)
                )

            tick_count = max(0, int(state.get("tick_count", 0) or 0))
            self._autonomous_tick_count_offset = tick_count
            runtime.tick_history = []
            # Saved count lives in the offset. The retained tail starts empty.
            runtime._completed_ticks = 0
            return True
        except Exception:
            return False

