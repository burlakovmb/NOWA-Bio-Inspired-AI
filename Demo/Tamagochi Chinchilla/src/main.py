"""
Chinchilla Agent - Main organism implementation.
Integrates pygame rendering with behavioral chain execution.

FIXES vs original:
- step() no longer calls _execute_random_action() while action_cooldown > 0
  (this was the main cause of flickering: a new random action queued EVERY tick)
- action_cooldown is now tracked in REAL SECONDS, not in ticks
  (so duration values from config are respected)
- TIME_SCALE removed from ActionRealizer path — durations in config are
  already in seconds; we just use them directly
- Engine is now ticked at 60fps for smooth rendering, but simulation
  logic runs at a configurable sim_fps (default 20fps = 0.05s per sim tick)
- Debug overlay shows current state (press D in game)
"""

import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import random
import time

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
def _get_base_dir() -> Path:
    """Resolve runtime base dir for resources (works for Nuitka onefile)."""
    try:
        import __compiled__  # type: ignore

        base = getattr(__compiled__, "containing_dir", None)
        if base:
            return Path(base)
    except Exception:
        pass
    return Path(__file__).resolve().parent.parent


def _add_to_syspath(path: Path) -> None:
    p = str(path)
    if p not in sys.path:
        sys.path.insert(0, p)


def _get_run_dir() -> Path:
    """Resolve directory of the launched exe for user data (saves)."""
    try:
        import __compiled__  # type: ignore

        original = getattr(__compiled__, "original_argv0", None)
        if original:
            return Path(original).resolve().parent
    except Exception:
        pass
    try:
        return Path(sys.argv[0]).resolve().parent
    except Exception:
        return Path.cwd()


BASE_DIR = _get_base_dir()
RUN_DIR = _get_run_dir()

# If onefile extracts into program dir, prefer that for resources.
RESOURCE_DIR = BASE_DIR
_onefile_dir = RUN_DIR / "_onefile"
if (_onefile_dir / "Datasets").exists() or (_onefile_dir / "sprites").exists() or (_onefile_dir / "sfx").exists():
    RESOURCE_DIR = _onefile_dir

# Prefer bundled NOWA sources when packaged (onefile/standalone)
NOWA_SRC = BASE_DIR / "nowa_src"
if NOWA_SRC.exists():
    _add_to_syspath(NOWA_SRC)
else:
    # Dev fallback: repo root /src
    DEV_NOWA_SRC = BASE_DIR.parent.parent / "src"
    if DEV_NOWA_SRC.exists():
        _add_to_syspath(DEV_NOWA_SRC)

from config import ACTION_LIBRARY, BEHAVIORAL_CHAINS
from dataset_loader import DatasetLoader
from demo_action_realizer import ActionRealizer
from behavioral_chains import BehavioralChainExecutor
from behavioral_chains import (
    register_dynamic_chain,
    is_dynamic_chain,
    DYNAMIC_CHAINS,
    DYNAMIC_CHAIN_STABILITY_THRESHOLD,
    DYNAMIC_CHAIN_USAGE_THRESHOLD,
    DYNAMIC_CHAIN_AFFECT_THRESHOLD,
)
from external_interaction_layer import ExternalInteractionLayer, Feedback as EILFeedback
from pygame_engine import create_pygame_engine

# ── Gap components ───────────────────────────────────────────────────────────
from value_layer       import DopaminergicTDLayer, ValueLayer
from scheduling_system import SchedulingSystem
from intent_memory     import IntentMemory
from self_model        import SelfModel
from memory_system     import MemorySystem
from storage           import AgentStorage
from decision_arbitrator import DecisionArbitrator
from hippocampal_imagine_engine import HippocampalImagineEngine
from stability_monitoring import StabilityMonitoringLayer

from audio_system import AudioSystem

# NOWA integration (spec)
from affective_space import AffectiveSpace, EmotionalImpulse
from autonomous_organism import DriveSystem, DriveRule, EnergySystem
from basal_ganglia import BasalGangliaGate, ActionChannel, BasalGangliaLearning, NO_ACTION
from conflict_arbitration import ConflictArbitrationLayer
from emotional_regulation import EmotionalRegulationLayer
from experience import Event, Path as ExperiencePath, EventType
from hippocampus import NOWAHippocampus
from neuromodulators import NeuromodulatorState
from sleep import SleepManager, CortexMemory
from wakefulness import WakefulnessState
from affective_persistence import AffectivePersistenceLayer
from affective_background import AffectiveBackgroundField
from semantic_emotions import SemanticEmotionsLayer
from emotional_memory_narratives import EmotionalMemoryNarrativesLayer
from emotional_expectations import EmotionalExpectationsLayer
from temporal import TemporalLevels


class _AffectProxy:
    """
    Backward-compatibility shim for chain executor/context code that expects
    `self.affect.state` and `self.affect.get_chain_context()`.
    """

    def __init__(self, space: AffectiveSpace, drives: DriveSystem, wakefulness: WakefulnessState):
        snap = dict(getattr(space, "axes", {}) or {})
        d = drives.snapshot()
        self.state = {
            **snap,
            # SchedulingSystem legacy keys
            "hunger": d.get("energy_need", 0.0),
            "tiredness": wakefulness.wakefulness,
            "boredom": 1.0 - d.get("curiosity", 0.5),
        }

    def get_state(self) -> Dict[str, float]:
        return dict(self.state)

    def get_chain_context(self) -> Dict[str, Any]:
        s = self.state
        return {
            "affect": s,
            "is_daytime": s.get("arousal", 0.5) > 0.3,
            "is_nighttime": s.get("arousal", 0.5) < 0.2,
            **s,
        }


# ============================================================================
# SELF-MODEL ADAPTER
# ============================================================================

class _SMAffectProxy:
    """Translates ChinchillaAgent.affect_space into AffectiveState-like interface for SelfModel."""
    def __init__(self, agent: "ChinchillaAgent") -> None:
        self._a = agent

    def _ax(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self._a.affect_space.snapshot().get("axes", {}).get(key, default))
        except Exception:
            return default

    @property
    def valence(self)  -> float: return self._ax("valence", 0.0)
    @property
    def arousal(self)  -> float: return self._ax("arousal", 0.5)
    @property
    def threat(self)   -> float: return self._ax("stress",  0.0)
    @property
    def curiosity(self)-> float: return self._ax("curiosity", 0.5)

    def snapshot(self) -> Dict[str, Any]:
        axes = self._a.affect_space.snapshot().get("axes", {})
        return {**axes, "timestamp": time.time(),
                "valence": self.valence, "arousal": self.arousal,
                "threat": self.threat, "curiosity": self.curiosity}

    def conflict_severity(self) -> float:
        try: return float(self._a.affect_space.axis_conflict())
        except Exception: return 0.0

    def adaptation_readiness(self) -> float:
        v = (self.valence + 1.0) / 2.0
        return max(0.0, min(1.0, v * (1.0 - self.threat)))


@dataclass
class _AffectiveScalarView:
    """Normalized affect scalars for non-decisional layers."""
    valence: float
    arousal: float
    threat: float
    curiosity: float


class _SelfModelAgent:
    """Thin wrapper so SelfModel(agent).get_state() + .affect_state work."""
    def __init__(self, agent: "ChinchillaAgent") -> None:
        self._a = agent
        self.affect_state = _SMAffectProxy(agent)

    def get_state(self) -> Dict[str, Any]:
        return {
            "hippocampus": {"size": len(getattr(self._a.hippocampus, "experiences", []) or [])},
            "cortex":      {"patterns": len(getattr(self._a.cortex, "patterns", []) or [])},
        }


class _ChainSelectorAdapter:
    """
    Minimal selector-like adapter so sleep/planning layers can exchange
    semantic action metadata over chain IDs.
    """

    def __init__(self, actions: Optional[List[str]] = None):
        self.actions: List[str] = list(actions or [])
        self.action_metadata: Dict[str, Dict[str, Any]] = {}
        self.confidence_threshold: float = 0.5

    def _ensure_actions_list(self) -> None:
        if isinstance(self.actions, list):
            return
        if isinstance(self.actions, dict):
            self.actions = [str(k) for k in self.actions.keys()]
            return
        if isinstance(self.actions, (set, tuple)):
            self.actions = [str(v) for v in self.actions]
            return
        if self.actions is None:
            self.actions = []
            return
        try:
            self.actions = [str(v) for v in list(self.actions)]
        except Exception:
            self.actions = [str(self.actions)]

    def _ensure_metadata_dict(self) -> None:
        if isinstance(self.action_metadata, dict):
            return
        self.action_metadata = {}

    def register_action(self, action_id: str) -> None:
        self._ensure_actions_list()
        a = str(action_id or "").strip()
        if a and a not in self.actions:
            self.actions.append(a)

    def get_action_metadata(self, action_id: str) -> Dict[str, Any]:
        self._ensure_metadata_dict()
        return dict(self.action_metadata.get(str(action_id), {}))

    def set_action_metadata(self, action_id: str, metadata: Dict[str, Any]) -> None:
        self._ensure_metadata_dict()
        self.action_metadata[str(action_id)] = dict(metadata or {})


# Bedtime preference in ``_build_candidate_chains`` once sleep pressure
# exceeds this level. Pressure 0 is full rest.
_SLEEP_ONSET_PRESSURE = 0.7
# Demo wakefulness: full deprivation after 4 host hours. Same units as ``sim_step(dt)``.
_WAKE_PRESSURE_RATE = 1.0 / (4.0 * 60.0 * 60.0)


def tamagochi_expected_wake_interval_s() -> float:
    """Host seconds from full rest to the bedtime preference.

    ``sim_step`` advances sleep pressure by ``dt / (4 h)`` while the
    chinchilla is not in a sleep behavior. Bedtime is boosted once that
    pressure exceeds 0.7. The configured wake is that climb from pressure
    0, i.e. ``0.7 * 4 * 3600 = 10080`` seconds. The first session starts
    at 0.1, so its first climb is shorter. The 1200 s circadian tint only
    biases suggestions; it does not open the stable writer. The core
    fallback of 3600 s is not used.
    """
    if _WAKE_PRESSURE_RATE <= 0.0:
        return 3600.0
    return _SLEEP_ONSET_PRESSURE / _WAKE_PRESSURE_RATE


def _host_dt(dt: float) -> float:
    """Elapsed host seconds. Non-finite or negative input is an explicit 0."""
    try:
        value = float(dt)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value) or value < 0.0:
        return 0.0
    return value


# ============================================================================
# CHINCHILLA AGENT
# ============================================================================

class ChinchillaAgent:
    """
    Cognitive Tamagotchi Chinchilla — autonomous organism.

    Timing model
    ────────────
    The render loop runs at RENDER_FPS (60) for smooth visuals.
    Simulation logic (chain/action selection) runs at SIM_FPS (10).
    Each simulation tick advances the organism by SIM_DT seconds.
    That same ``dt`` is the host clock of the core agent (``self.nowa``):
    one ``advance_time(dt)`` per tick, never the wall clock.

    action_remaining_s  — seconds left before the current action is done.
                          Decremented by the same sim ``dt``. Durations in
                          config (e.g. eat_pellets: 10-30 s) are in those
                          seconds. The loop feeds wall time through a
                          fixed ``SIM_DT`` accumulator, so one realtime
                          second is one host second while the loop keeps up.
    """

    RENDER_FPS = 60       # Hz — only affects display smoothness
    SIM_FPS    = 10       # Hz — how often behavior logic runs
    SIM_DT     = 1.0 / SIM_FPS   # seconds per sim tick

    # DURATION_SCALE: config durations are already in seconds. Keep at 1.0.
    DURATION_SCALE = 1.0

    # Gap between end of one chain and start of next.
    # 2-5s idle gap feels natural — chinchilla pauses, looks around, then acts.
    CHAIN_COOLDOWN_MIN_S = 2.0
    CHAIN_COOLDOWN_MAX_S = 5.0

    # Kept for compat but replaced by CHAIN_COOLDOWN_MIN/MAX
    CHAIN_COOLDOWN_S = 3.0

    def __init__(self, demo_dir: Optional[str] = None,
                 use_pygame: bool = True, use_gui: bool = True,
                 demo_training_mode: bool = False,
                 session_filename: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        self.demo_dir = Path(demo_dir) if demo_dir else self._find_demo_dir()
        self.logger.info(f"Initializing ChinchillaAgent from {self.demo_dir}")

        # ── Core components ────────────────────────────────────────────
        self.dataset_loader = DatasetLoader(self.demo_dir / "Datasets")
        self.dataset_loader.load_all()

        self.action_realizer  = ActionRealizer(self.dataset_loader, self.logger)
        self.chain_executor   = BehavioralChainExecutor(self.action_realizer, self.logger)
        self.chain_selector   = _ChainSelectorAdapter(actions=list(BEHAVIORAL_CHAINS.keys()))
        self.audio            = AudioSystem(self.demo_dir / "sfx", self.logger)
        self.audio.enabled    = True  # Enable audio by default

        # ── ExternalInteractionLayer — owner feedback / training ───────
        # EIL provides the channel from the outside world (owner button press)
        # into NOWA's drive + strategy learning system.
        self.eil = ExternalInteractionLayer(history_limit=256)
        # Pre-register all behavioral chain names as learnable strategies
        for _cname in BEHAVIORAL_CHAINS:
            self.eil.register_strategy(_cname, initial_weight=0.0)
        self._training_feedback_count: int = 0

        # ── DopaminergicTDLayer ───────────────────────────────────────
        self.td_layer = DopaminergicTDLayer()
        self._last_td_result: Dict[str, float] = {}
        # Phase 5/011 decision stack (demo-integrated)
        self.value_layer = ValueLayer()
        self.decision_arbitrator = DecisionArbitrator()
        # Use shorter windows in demo so diagnostics become visible quickly.
        self.stability_monitor = StabilityMonitoringLayer(window_size=120, hysteresis_windows=1)
        self.imagination_engine = HippocampalImagineEngine(
            samples=6,
            depth=3,
            branching=3,
            rng=random.Random(0),
        )
        self.deliberative_planning_enabled: bool = True
        self.chain_planning_gain: float = 0.18
        self.chain_planning_candidate_limit: int = 6
        self._last_value_update: Dict[str, Any] = {}
        self._last_decision_arbitration_output: Dict[str, Any] = {}
        self._last_planning_stats: Dict[str, Any] = {}
        self._last_stability_snapshot: Dict[str, Any] = {}
        self._chain_value_state_before: Dict[str, Any] = {}
        self._chain_value_stats: Dict[str, Dict[str, float]] = {}

        # ── SchedulingSystem ─────────────────────────────────────────
        self.scheduling = SchedulingSystem(self.logger)

        # ── IntentMemory ──────────────────────────────────────────────
        self.intent_memory = IntentMemory(
            context_signature_window=1,
            recency_half_life=1800.0,
            min_strength_for_trace=0.08,
        )
        self._intent_context: List[str] = []   # rolling 1-element context window

        # ── SelfModel ─────────────────────────────────────────────────
        self._sm_agent = _SelfModelAgent(self)
        self.self_model = SelfModel(self._sm_agent)
        self._self_model_report: Dict[str, Any] = {}
        self._self_model_timer: float = 0.0    # introspect every 30 sim-s

        # ── MemorySystem ──────────────────────────────────────────────
        # Keep all persisted artifacts in one location.
        self.saves_dir = self._resolve_saves_dir()
        self.memory_system = MemorySystem(
            memory_file=self.saves_dir / "memory.json",
            logger=self.logger,
        )
        self._memory_save_timer: float = 0.0   # save every 120 sim-s
        self._chain_affect_before: Dict[str, float] = {}

        # ── AgentStorage ──────────────────────────────────────────────
        self.agent_storage = AgentStorage(save_dir=str(self.saves_dir))
        self._session_save_filename = session_filename or "agent_save.nowa"
        self._session_save_path = self.saves_dir / self._session_save_filename
        self._auto_save_timer: float = 0.0     # full save every 300 sim-s

        # ── NOWA layers (spec) ─────────────────────────────────────────
        self.neuromod = NeuromodulatorState()
        # For the demo, use accelerated wakefulness rates so changes are
        # visible during interactive sessions (overrides default production rates).
        self.wakefulness = WakefulnessState(
            initial_wakefulness=0.1,
            accumulation_rate=(1.0 / (4.0 * 60.0 * 60.0)),
            recovery_rate=(1.0 / (2.0 * 60.0 * 60.0)),
        )

        self.affect_space = AffectiveSpace(
            axes={
                "valence": 0.3,
                "arousal": 0.5,
                "dominance": 0.4,
                "stress": 0.0,
                "trust": 0.5,
                "curiosity": 0.6,
                "stability": 0.5,
                "attachment": 0.3,
            },
            decay={
                "valence": 0.98,
                "arousal": 0.97,
                "dominance": 0.99,
                "stress": 0.96,
                "trust": 0.995,
                "curiosity": 0.97,
                "stability": 0.995,
                "attachment": 0.998,
            },
        )

        # ── Additional NOWA layers (non-decisional) ───────────────────
        self.temporal_levels = TemporalLevels(window_size=12)
        self.affective_persistence = AffectivePersistenceLayer()
        self.affective_background = AffectiveBackgroundField()
        self.semantic_emotions = SemanticEmotionsLayer()
        self.emotional_memory = EmotionalMemoryNarrativesLayer()
        self.emotional_expectations = EmotionalExpectationsLayer()
        self._last_temporal_levels: Dict[str, Any] = {}
        self._last_persistence_snapshot: Dict[str, Any] = {}
        self._last_background_snapshot: Dict[str, float] = {}
        self._last_semantic_snapshot: List[Dict[str, Any]] = []
        self._last_emotional_memory_snapshot: Dict[str, Any] = {}
        self._last_emotional_expectations_snapshot: Dict[str, Any] = {}
        self._lifetime_horizon_s: float = 3600.0

        self.drives = DriveSystem(
            rules={
                "energy_need": DriveRule(
                    accumulation_rate=0.006,
                    discharge_rate=0.001,
                    decay_rate=0.001,
                    affect_weights={"stress": 0.010, "arousal": 0.004},
                ),
                "exploration": DriveRule(
                    accumulation_rate=0.011,
                    discharge_rate=0.0012,
                    decay_rate=0.0012,
                    affect_weights={"curiosity": 0.020, "dominance": 0.008, "stress": -0.005},
                ),
                "social_drive": DriveRule(
                    accumulation_rate=0.008,
                    discharge_rate=0.0015,
                    decay_rate=0.0010,
                    affect_weights={"trust": 0.020, "attachment": 0.014, "stress": -0.010},
                ),
                "curiosity": DriveRule(
                    accumulation_rate=0.018,
                    discharge_rate=0.001,
                    decay_rate=0.001,
                    affect_weights={"curiosity": 0.025, "stress": -0.005, "stability": 0.004},
                ),
                "goal_tension": DriveRule(
                    accumulation_rate=0.010,
                    discharge_rate=0.0010,
                    decay_rate=0.0015,
                    affect_weights={"dominance": 0.018, "stability": 0.006, "stress": 0.008},
                ),
            }
        )
        self.energy = EnergySystem()
        self._last_drive_snapshot: Dict[str, float] = self.drives.snapshot()

        self.bg_channels: Dict[str, ActionChannel] = {
            chain_name: ActionChannel(action_id=chain_name) for chain_name in BEHAVIORAL_CHAINS
        }
        self.bg_gate = BasalGangliaGate(
            temperature=0.8,
            threshold=0.0,
            go_gain_alpha=0.9,
            habit_gain_beta=0.6,
            cortisol_gain_gamma=1.2,
            aversion_gain_delta=0.8,
        )
        self.bg_learning = BasalGangliaLearning(learning_rate=0.05)

        self.cer = EmotionalRegulationLayer()
        self.conflict_arb = ConflictArbitrationLayer()

        self.hippocampus = NOWAHippocampus(max_experiences=500)
        self.cortex = CortexMemory()
        self.sleep_manager = SleepManager(
            hippocampus=self.hippocampus,
            cortex=self.cortex,
            intent_memory=self.intent_memory,
            clustering_similarity_threshold=0.7,
            forget_stability_threshold=0.15,
        )
        # Wire optional replay/consolidation channels so demo exposes full NOWA stack.
        setattr(self.sleep_manager, "selector", self.chain_selector)
        setattr(self.sleep_manager, "value_layer", self.value_layer)
        setattr(self.sleep_manager, "stability_monitor", self.stability_monitor)
        setattr(self.sleep_manager, "bg_action_channels", self.bg_channels)
        setattr(self.sleep_manager, "bg_learning", self.bg_learning)
        self._sleep_consolidation_pending: bool = False

        # Kept for callers. Waking ticks do not write stable BG weights;
        # a finished chain tags the core labile tier instead.
        self.demo_training_mode = bool(demo_training_mode)
        self._pending_owner_feedback: List[Dict[str, Any]] = []
        self.nowa = None

        # modulation caches (set each tick)
        self._last_chain_reward: float = 0.0
        # Rolling expected reward per chain (EMA α=0.3) — used for real PE = |actual - expected|
        self._expected_reward_by_chain: Dict[str, float] = {}
        # AffectiveSpace trace captured at chain start — replayed as recall_impulse at chain end
        self._chain_start_trace = None          # EmotionalTrace | None
        # Snapshot of affect_space at chain start — used for distance_to drift metric
        self._chain_start_affect_space = None   # AffectiveSpace | None
        # Last measured affect drift distance (chain start → end); used for ACh update
        self._last_chain_drift: float = 0.0
        self._cer_exploration_bias: float = 0.0
        self._cer_decision_threshold_shift: float = 0.0
        self._cer_habit_gain_scale: float = 1.0
        self._arb_exploration_bias: float = 0.0
        self._arb_decision_threshold_shift: float = 0.0
        self._last_arb_mode: str = "—"
        self._arb_inhibited: bool = False

        # ── Pygame ────────────────────────────────────────────────────
        self.pygame_engine = create_pygame_engine(fps=self.RENDER_FPS) if use_pygame else None
        if self.pygame_engine:
            if hasattr(self.pygame_engine, "set_audio_enabled"):
                self.pygame_engine.set_audio_enabled(getattr(self.audio, "enabled", False))
            self._preload_animations()

        # ── Timing state ───────────────────────────────────────────────
        self.running              = False
        self.paused               = False
        self.tick_count           = 0        # sim ticks
        self.total_sim_time       = 0.0      # seconds of sim time elapsed

        # How many real seconds remain before current action expires
        self.action_remaining_s: float = 0.0

        # Real seconds remaining before we may start a new chain
        self.chain_cooldown_s: float = 0.0
        self._last_nowa_save: float = 0.0
        self._postural_timer: float = 0.0
        self._micro_timer: float = random.uniform(2.0, 5.0)
        self._wellbeing_timer: float = 0.0

        self.current_action: Optional[Dict[str, Any]] = None
        self.last_chain_name: Optional[str]       = None
        self.chain_start_affect: Optional[Dict]   = None

        # ── Dynamic chain support ──────────────────────────────────────
        # Rolling window of recent action_ids — fed to ChainMemory.match_bias()
        # for temporal sequence prediction at each chain selection tick.
        self._recent_action_seq: List[str] = []
        self._MAX_RECENT_SEQ = 20

        # ── Stats ─────────────────────────────────────────────────────
        self.stats = {"actions_executed": 0, "chains_completed": 0}

        # Load persisted NOWA state if present (lightweight)
        self.load_nowa_state()
        # Load full session if present (overrides NOWA state)
        self._load_session_if_exists()
        # After load, so the host points at the restored Q table and channels.
        self._bind_two_tier_host()

        self.logger.info("ChinchillaAgent ready")

    @property
    def affect(self) -> _AffectProxy:
        return _AffectProxy(self.affect_space, self.drives, self.wakefulness)

    def _axes8(self) -> Dict[str, float]:
        """Return canonical 8D axes snapshot (valence/arousal/... keys)."""
        return dict(getattr(self.affect_space, "axes", {}) or {})

    @staticmethod
    def _axis_to_unit(value: float) -> float:
        """Map [-1, 1] affect axis to [0, 1] for non-decisional layers."""
        try:
            v = float(value)
        except Exception:
            v = 0.0
        return max(0.0, min(1.0, (v + 1.0) / 2.0))

    def _lifetime_progress(self) -> float:
        horizon = max(1.0, float(self._lifetime_horizon_s or 3600.0))
        return max(0.0, min(1.0, float(self.total_sim_time) / horizon))

    def _collect_chain_state_snapshot(self, chain_name: Optional[str] = None) -> Dict[str, Any]:
        """Compact state snapshot for value/planning layers."""
        axes = self._axes8()
        drives = dict(self._last_drive_snapshot or {})
        chain_v = str(chain_name or self.chain_executor.current_chain or "idle")
        return {
            "context_signature": f"{self._affect_label()}|{chain_v}|t{int(self.total_sim_time // 30)}",
            "chain": chain_v,
            "time_bucket": int(self.total_sim_time // 30),
            "affect": {
                "valence": float(axes.get("valence", 0.0)),
                "arousal": float(axes.get("arousal", 0.0)),
                "stress": float(axes.get("stress", 0.0)),
                "curiosity": float(axes.get("curiosity", 0.0)),
                "stability": float(axes.get("stability", 0.0)),
            },
            "drives": {
                "energy_need": float(drives.get("energy_need", 0.0)),
                "exploration": float(drives.get("exploration", 0.0)),
                "social_drive": float(drives.get("social_drive", 0.0)),
                "curiosity": float(drives.get("curiosity", 0.0)),
                "goal_tension": float(drives.get("goal_tension", 0.0)),
            },
            "wakefulness": float(self.wakefulness.wakefulness),
            "neuromodulators": {
                "dopamine": float(self.neuromod.dopamine),
                "serotonin": float(self.neuromod.serotonin),
                "norepinephrine": float(self.neuromod.norepinephrine),
                "cortisol": float(self.neuromod.cortisol),
                "acetylcholine": float(self.neuromod.acetylcholine),
            },
        }

    def _update_chain_value_statistics(
        self,
        chain_name: str,
        reward: float,
        value_update: Optional[Dict[str, Any]],
    ) -> None:
        """Maintain lightweight per-chain reward/TD statistics."""
        key = str(chain_name or "")
        if not key:
            return
        stats = dict(self._chain_value_stats.get(key, {}))
        count = int(stats.get("count", 0)) + 1
        mean_reward = float(stats.get("mean_reward", 0.0))
        reward_var_acc = float(stats.get("reward_var_acc", 0.0))
        reward_v = float(reward)
        delta_r = reward_v - mean_reward
        mean_reward = mean_reward + (delta_r / float(max(1, count)))
        reward_var_acc = reward_var_acc + (delta_r * (reward_v - mean_reward))
        td_err = float((value_update or {}).get("td_error", 0.0))
        td_mean = float(stats.get("td_mean", 0.0))
        td_var_acc = float(stats.get("td_var_acc", 0.0))
        delta_td = td_err - td_mean
        td_mean = td_mean + (delta_td / float(max(1, count)))
        td_var_acc = td_var_acc + (delta_td * (td_err - td_mean))
        success_rate = float(stats.get("success_rate", 0.5))
        if reward_v > 0.0:
            success_rate = (0.9 * success_rate) + 0.1
        else:
            success_rate = 0.9 * success_rate
        stats.update(
            {
                "count": int(count),
                "mean_reward": float(mean_reward),
                "reward_variance": float(max(0.0, reward_var_acc / float(max(1, count)))),
                "reward_var_acc": float(reward_var_acc),
                "td_mean": float(td_mean),
                "td_error_variance": float(max(0.0, td_var_acc / float(max(1, count)))),
                "td_var_acc": float(td_var_acc),
                "success_rate": float(max(0.0, min(1.0, success_rate))),
                "last_td_error": float(td_err),
                "last_confidence_score": float((value_update or {}).get("confidence_score", 0.0)),
                "last_stability_score": float((value_update or {}).get("stability_score", 0.0)),
                "last_updated_time": float(self.total_sim_time),
            }
        )
        self._chain_value_stats[key] = stats

    def _build_chain_action_metadata(
        self,
        pressure_vector: Optional[Dict[str, float]] = None,
        persist: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """Build selector-like metadata for chain IDs."""
        metadata: Dict[str, Dict[str, Any]] = {}
        pressure = dict(pressure_vector or {})
        for chain_name, channel in (self.bg_channels or {}).items():
            if persist:
                self.chain_selector.register_action(chain_name)
            stats = dict(self._chain_value_stats.get(chain_name, {}))
            selection_count = max(0, int(getattr(channel, "selection_count", 0) or 0))
            success_rate = float(getattr(channel, "get_success_rate", lambda: 0.5)())
            td_var = float(stats.get("td_error_variance", 0.0))
            if td_var <= 1e-9:
                td_var = (1.0 - success_rate) * 0.25 + (0.20 / float(max(1, selection_count + 1)))
            stability_score = max(
                0.0,
                min(
                    1.0,
                    0.55 * float(getattr(channel, "habit_strength", 0.0))
                    + 0.45 * success_rate,
                ),
            )
            confidence_score = max(
                0.0,
                min(
                    1.0,
                    0.5 * min(1.0, selection_count / 12.0)
                    + 0.5 * float(stats.get("last_confidence_score", 0.0)),
                ),
            )
            metadata[chain_name] = {
                "td_variance": float(max(0.0, td_var)),
                "stability_score": float(stability_score),
                "confidence_score": float(confidence_score),
                "consolidated": bool(selection_count >= 3),
                "last_outcome": float(getattr(channel, "last_outcome", 0.0) or 0.0),
                "pressure_hint": float(pressure.get(chain_name, 0.0)),
            }
            if persist:
                self.chain_selector.set_action_metadata(chain_name, metadata[chain_name])
        return metadata

    def _apply_deliberative_chain_planning(
        self,
        pressure_vector: Dict[str, float],
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """Apply HIE-based value lookahead to chain pressures."""
        pressures = dict(pressure_vector or {})
        experiences = list(getattr(self.hippocampus, "experiences", []) or [])
        if not experiences:
            return pressures, {
                "planning_bias_applied": False,
                "supported_actions": 0,
                "support_mean": 0.0,
                "rollout_depth": 0,
                "rollout_samples": 0,
                "rollout_used": 0,
            }

        ranked = sorted(pressures.items(), key=lambda kv: float(kv[1]), reverse=True)
        candidate_actions = [name for name, _ in ranked[: max(1, int(self.chain_planning_candidate_limit))]]
        if not candidate_actions:
            return pressures, {
                "planning_bias_applied": False,
                "supported_actions": 0,
                "support_mean": 0.0,
                "rollout_depth": 0,
                "rollout_samples": 0,
                "rollout_used": 0,
            }

        result = self.imagination_engine.generate_action_tree_imagination(
            start_state=self._collect_chain_state_snapshot(chain_name=self.chain_executor.current_chain),
            candidate_actions=candidate_actions,
            experiences=experiences,
            depth=int(getattr(self.imagination_engine, "depth", 3)),
            gamma=float(getattr(self.value_layer, "gamma_default", 0.95)),
            value_layer=self.value_layer,
        )
        action_values = dict(result.get("action_values", {}) or {})
        if not action_values:
            return pressures, {
                "planning_bias_applied": False,
                "supported_actions": 0,
                "support_mean": 0.0,
                "rollout_depth": int(result.get("max_depth_reached", 0)),
                "rollout_samples": int(getattr(self.imagination_engine, "samples", 0)),
                "rollout_used": int(result.get("trajectory_count", 0)),
            }

        gain = max(0.0, float(getattr(self, "chain_planning_gain", 0.18)))
        for chain_name, imagined_value in action_values.items():
            if chain_name in pressures:
                pressures[chain_name] = float(pressures[chain_name]) + gain * float(imagined_value)

        support_values = [float(v) for v in action_values.values()]
        return pressures, {
            "planning_bias_applied": True,
            "supported_actions": int(len(action_values)),
            "support_mean": float(sum(support_values) / float(max(1, len(support_values)))),
            "rollout_depth": int(result.get("max_depth_reached", 0)),
            "rollout_samples": int(getattr(self.imagination_engine, "samples", 0)),
            "rollout_used": int(result.get("trajectory_count", 0)),
            "nodes_visited": int(result.get("nodes_visited", 0)),
            "edges_visited": int(result.get("edges_visited", 0)),
            "novelty_hits": int(result.get("novelty_hits", 0)),
        }

    def _update_additional_nowa_layers(self, dt: float) -> None:
        """Update non-decisional NOWA layers (persistence, semantics, narratives)."""
        axes = self._axes8()
        scalar_view = _AffectiveScalarView(
            valence=self._axis_to_unit(axes.get("valence", 0.0)),
            arousal=self._axis_to_unit(axes.get("arousal", 0.0)),
            threat=self._axis_to_unit(axes.get("stress", 0.0)),
            curiosity=self._axis_to_unit(axes.get("curiosity", 0.0)),
        )

        # Temporal levels (T0/T1/T2/T3)
        try:
            self.temporal_levels.log(
                {
                    "valence": scalar_view.valence,
                    "arousal": scalar_view.arousal,
                    "threat": scalar_view.threat,
                    "curiosity": scalar_view.curiosity,
                }
            )
            self._last_temporal_levels = self.temporal_levels.get_levels()
        except Exception:
            pass

        # Affective persistence traces
        try:
            self.affective_persistence.update(
                affect_state=scalar_view,
                neuromodulators=self.neuromod,
                temporal_levels=self._last_temporal_levels,
                time_elapsed=dt,
            )
            self._last_persistence_snapshot = {
                "traces": self.affective_persistence.snapshot(),
            }
        except Exception:
            pass

        # Background field from persistence traces
        try:
            self._last_background_snapshot = self.affective_background.update_from_traces(
                self.affective_persistence.get_traces(),
                wakefulness=self.wakefulness.wakefulness,
                lifetime_progress=self._lifetime_progress(),
                time_elapsed=dt,
            )
        except Exception:
            pass

        # Semantic emotions
        try:
            self.semantic_emotions.update_from_space(
                self.affect_space,
                wakefulness=self.wakefulness.wakefulness,
                agent_lifetime=self.total_sim_time,
            )
            self._last_semantic_snapshot = self.semantic_emotions.snapshot()
        except Exception:
            pass

        # Emotional memory narratives
        try:
            self.emotional_memory.update_from_layers(
                self.semantic_emotions,
                space=self.affect_space,
                background=self._last_background_snapshot,
                agent_lifetime=self.total_sim_time,
                timestamp=self.total_sim_time,
            )
            self._last_emotional_memory_snapshot = self.emotional_memory.snapshot()
        except Exception:
            pass

        # Emotional expectations (forecasting)
        try:
            self.emotional_expectations.update(
                self.emotional_memory,
                self.semantic_emotions,
                background=self._last_background_snapshot,
                agent_lifetime=self.total_sim_time,
                timestamp=self.total_sim_time,
            )
            self._last_emotional_expectations_snapshot = self.emotional_expectations.snapshot()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # SETUP
    # ------------------------------------------------------------------

    def _find_demo_dir(self) -> Path:
        # First try runtime base dir (onefile/standalone) or dev root.
        if (RESOURCE_DIR / "Datasets").exists():
            return RESOURCE_DIR
        current = Path(__file__).resolve().parent.parent
        if (current / "Datasets").exists():
            return current
        parent = current.parent
        if (parent / "Datasets").exists():
            return parent
        raise RuntimeError("Could not find Demo/Tamagochi Chinchilla directory")

    def _resolve_saves_dir(self) -> Path:
        """
        Resolve writable saves directory.

        Preference order:
        1) <demo_dir>/saves (project-local)
        2) <run_dir>/saves  (fallback for packaged environments)
        """
        candidates: List[Path] = []
        if getattr(self, "demo_dir", None) is not None:
            candidates.append(Path(self.demo_dir) / "saves")
        candidates.append(RUN_DIR / "saves")

        seen: set = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                return candidate
            except Exception:
                continue

        # Last-resort fallback: propagate if this also fails.
        fallback = RUN_DIR / "saves"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _preload_animations(self) -> None:
        sprites_dir = self.demo_dir / "sprites"
        if not sprites_dir.exists():
            self.logger.warning(f"Sprites directory not found: {sprites_dir}")
            return
        count = 0
        for sprite_file in sorted(sprites_dir.glob("*.png")):
            if self.pygame_engine.load_animation(sprite_file.stem, sprite_file):
                count += 1
        self.logger.info(f"Preloaded {count} animations")

    def _bind_two_tier_host(self) -> None:
        """Attach a core ``Agent`` as the plasticity host.

        The cage keeps its own value table, channels, hippocampus and
        sleep manager. The core agent shares those objects and owns the
        labile tier plus the host clock. Daytime outcomes go through
        ``Agent._record_known_outcome``. ``Agent.sleep`` is not the cage
        loop; ``SleepManager.deep_sleep`` reads this host.
        """
        from agent import Agent
        from labile_layer import PlasticityConfig

        interval = tamagochi_expected_wake_interval_s()
        host = Agent(
            hippocampus=self.hippocampus,
            cortex=self.cortex,
            selector=self.chain_selector,
            sleep_manager=None,
            intent_memory=self.intent_memory,
            external_interaction_layer=self.eil,
            plasticity_config=PlasticityConfig(expected_wake_interval_s=interval),
        )
        self.nowa = host
        self._rewire_two_tier_host()

    def _rewire_two_tier_host(self) -> None:
        """Point the core host at the cage's stable objects after load."""
        host = getattr(self, "nowa", None)
        if host is None:
            return

        # Old session pickles stored ``bg_action_channels`` as {} because the
        # cage used ``bg_channels``. An empty table is not a restore.
        loaded_channels = getattr(self, "bg_action_channels", None)
        if (
            isinstance(loaded_channels, dict)
            and loaded_channels
            and loaded_channels is not self.bg_channels
        ):
            self.bg_channels = loaded_channels
        host.bg_action_channels = self.bg_channels
        self.bg_action_channels = self.bg_channels

        host.value_layer = self.value_layer
        host.bg_learning = self.bg_learning
        host.neuromodulators = self.neuromod
        host.intent_memory = self.intent_memory
        host.external_interaction_layer = self.eil
        host.selector = self.chain_selector
        host.hippocampus = self.hippocampus
        host.cortex = self.cortex
        host.sleep_manager = self.sleep_manager

        plasticity = getattr(self, "plasticity", None)
        if plasticity is None:
            plasticity = host.plasticity
        if getattr(plasticity, "expected_wake_interval_s", None) is None:
            plasticity.expected_wake_interval_s = tamagochi_expected_wake_interval_s()
        host.plasticity = plasticity
        self.plasticity = plasticity

        labile = getattr(self, "labile", None)
        if labile is None:
            labile = host.labile
        try:
            labile.config = plasticity
        except Exception:
            pass
        host.labile = labile
        self.labile = labile

        if "_host_clock_s" in self.__dict__:
            try:
                host._host_clock_s = float(self.__dict__["_host_clock_s"])
            except (TypeError, ValueError):
                pass
            del self.__dict__["_host_clock_s"]

        sleep_manager = self.sleep_manager
        setattr(sleep_manager, "value_layer", self.value_layer)
        setattr(sleep_manager, "stability_monitor", self.stability_monitor)
        setattr(sleep_manager, "selector", self.chain_selector)
        setattr(sleep_manager, "bg_action_channels", self.bg_channels)
        setattr(sleep_manager, "bg_learning", self.bg_learning)
        setattr(sleep_manager, "neuromodulators", self.neuromod)
        setattr(sleep_manager, "labile", host.labile)
        setattr(sleep_manager, "plasticity", host.plasticity)
        setattr(sleep_manager, "_host_agent", host)
        # Capture reads the manager, not the host, for habit EMA.
        setattr(sleep_manager, "intent_memory", self.intent_memory)

    def _commit_waking_chain_outcome(
        self,
        chain_name: str,
        reward: float,
        state_before: Dict[str, Any],
        state_after: Dict[str, Any],
        episode: Any = None,
    ) -> Dict[str, Any]:
        """Tag one finished chain on the core labile tier.

        Stable Q, Go/NoGo and habit strength are not written. Sleep
        capture reads ``replay_action_id`` and the committed reward.
        """
        host = getattr(self, "nowa", None)
        if host is None or not hasattr(host, "_record_known_outcome"):
            return {}
        action = str(chain_name or "")
        if episode is not None:
            try:
                episode.replay_action_id = action
                # Same context note_selection used, so sleep apply_outcome
                # updates that trace instead of a second key.
                context = list(getattr(self, "_chain_intent_context", None) or ["idle"])
                episode.context_events = [str(item) for item in context]
            except Exception:
                pass
        try:
            result = host._record_known_outcome(
                context_events=[action],
                action_id=action,
                outcome=float(reward),
                episode=episode,
                state_snapshot=dict(state_before or {}),
                next_state_snapshot=dict(state_after or {}),
                next_context_events=[action],
                terminal=True,
            )
        except Exception:
            return {}
        return dict(result or {})

    # ------------------------------------------------------------------
    # SIMULATION STEP
    # ------------------------------------------------------------------

    def sim_step(self, dt: float) -> None:
        """
        One simulation tick.  dt is the sim tick duration in seconds
        (normally SIM_DT = 0.1 s).

        Rule: we only select a new action / chain when action_remaining_s
        has counted down to 0.  We never queue a new action while the
        current one is still in progress.  This eliminates flickering.
        """
        if not self.running or self.paused:
            return

        self.tick_count      += 1
        self.total_sim_time  += dt
        # One game dt per tick. The core clock does not read the wall.
        host = getattr(self, "nowa", None)
        if host is not None and hasattr(host, "advance_time"):
            host.advance_time(_host_dt(dt))

        # ── Timers ────────────────────────────────────────────────────
        self.action_remaining_s = max(0.0, self.action_remaining_s - dt)
        self.chain_cooldown_s   = max(0.0, self.chain_cooldown_s   - dt)

        # ── Wakefulness (sleep/wake physiology) ───────────────────────
        sleeping_chains = {"bedtime_routine", "extreme_fear"}
        sleeping_actions = {"sleep_house", "doze_shelf", "hide_house"}
        is_sleeping = (
            self.chain_executor.current_chain in sleeping_chains
            or (self.current_action or {}).get("action_id", "") in sleeping_actions
        )
        if is_sleeping:
            self.wakefulness.update_sleeping(elapsed_seconds=dt)
        else:
            self.wakefulness.update_waking(elapsed_seconds=dt)

        # ── Neuromodulators ───────────────────────────────────────────
        self.neuromod.decay_over_time(elapsed=dt)
        wake_deltas = self.wakefulness.get_neuromodulator_deltas()
        self.neuromod.cortisol += wake_deltas["cortisol"] * dt
        # FIX: NE injection from wakefulness is BLOCKED during sleep.
        # During waking, wakefulness drives NE release (LC-NE system).
        # During sleep, LC-NE activity drops to near-zero — if we keep
        # injecting NE at wakefulness*0.02/s it saturates to 1.0 within
        # 60s and arousal never drops (NE half-life=90s can't clear it fast
        # enough). Gate: no NE injection during sleep, allow natural decay.
        if not is_sleeping:
            self.neuromod.norepinephrine += wake_deltas["norepinephrine"] * dt
        self.neuromod.serotonin += wake_deltas["serotonin"] * dt
        self.neuromod._clamp_all()

        # ── DopaminergicTDLayer: tonic DA from CER stress level ───────
        # High cortisol → depressed tonic DA baseline → motivation floor drops.
        try:
            _tonic = self.td_layer.update_tonic_from_cer(self.neuromod.cortisol)
            # Gently raise DA toward tonic floor when stress-suppressed
            if self.neuromod.dopamine < _tonic:
                self.neuromod.dopamine = min(
                    self.neuromod.dopamine + _tonic * 0.005 * dt, _tonic
                )
                self.neuromod._clamp_all()
        except Exception:
            pass

        # ── SchedulingSystem: tick circadian cycles ───────────────────
        try:
            _cur_chain = self.chain_executor.current_chain or ""
            self.scheduling.update(dt, {_cur_chain: 1} if _cur_chain else {})
            # Trigger satiation helpers when relevant chain is running
            if _cur_chain in ("eating_and_grooming", "morning_awakening"):
                self.scheduling.trigger_eating()
            elif _cur_chain in ("bedtime_routine", "nesting"):
                self.scheduling.trigger_sleeping()
            elif _cur_chain in ("activity_burst", "exploration", "dust_bathing"):
                self.scheduling.trigger_playing()
        except Exception:
            pass

        # ── SelfModel: periodic introspection (every 30 sim-s) ────────
        self._self_model_timer += dt
        if self._self_model_timer >= 30.0:
            self._self_model_timer = 0.0
            try:
                self._self_model_report = self.self_model.introspect()
            except Exception:
                pass

        # ── MemorySystem / AgentStorage: auto-save timers ─────────────
        self._memory_save_timer += dt
        if self._memory_save_timer >= 120.0:
            self._memory_save_timer = 0.0
            try:
                self.memory_system.save_memory()
            except Exception:
                pass

        chain = self.chain_executor.current_chain
        if chain == "hyperactivity":
            self.neuromod.update_from_signals(novelty=0.6, reward=0.1)
        elif chain == "chronic_stress":
            self.neuromod.update_from_signals(conflict=0.7, reward=-0.3)
        elif chain in ("eating_and_grooming", "full_grooming", "dust_bathing"):
            self.neuromod.update_from_signals(reward=0.3, stable_repetition=True)
        elif chain in ("activity_burst", "exploration"):
            self.neuromod.update_from_signals(novelty=0.4, reward=0.15)
        elif chain == "social_contact":
            self.neuromod.update_from_signals(reward=0.2, stable_repetition=False)

        # ── Affect (8D) ───────────────────────────────────────────────
        # FIX: scale down NM→affect impulse during sleep.
        # During sleep NE stays high (WakefulnessState still injects it) but
        # the waking arousal pathway should be suppressed — just as in real
        # neuroscience (LC-NE activity drops during NREM).
        # Gate: intensity = 0.4 when awake, 0.05 during sleep.
        _sleep_gate = 0.05 if is_sleeping else 1.0
        nm_impulse = EmotionalImpulse(
            vector={
                "valence": self.neuromod.dopamine * 0.3 - self.neuromod.cortisol * 0.4,
                "arousal": self.neuromod.norepinephrine * 0.5 + self.neuromod.dopamine * 0.2,
                "stress": self.neuromod.cortisol * 0.6,
                "curiosity": self.neuromod.acetylcholine * 0.4,
                "stability": self.neuromod.serotonin * 0.3 - self.neuromod.cortisol * 0.2,
            },
            intensity=0.4 * _sleep_gate,
            source="neuromodulators",
        )

        # FIX: active arousal suppression during sleep.
        # Without explicit negative impulse the inertia (α≈0.97) keeps
        # arousal frozen at its pre-sleep level for many minutes.
        # Biological reference: SWS is characterised by low arousal + high stability.
        _sleep_impulses = [nm_impulse]
        if is_sleeping:
            _sleep_suppress = EmotionalImpulse(
                vector={
                    # FIX: was -0.25 intensity=0.6 → -0.15/s → arousal → -0.78 (too deep).
                    # AffectiveSpace has no floor clamp: arousal can go strongly negative,
                    # then recovery is slow when waking (wakefulness=0, NE at baseline).
                    # Gentle push: -0.05 * 0.3 = -0.015/s — enough to bring arousal from
                    # 0.7→~0.1 within a normal sleep cycle, but won't overshoot into negatives.
                    "arousal":   -0.05,
                    "stability": +0.10,
                    "stress":    -0.03,
                },
                intensity=0.3,
                source="sleep_suppression",
            )
            _sleep_impulses.append(_sleep_suppress)
        # ── FIX: get_background_modifiers — let NM state tune affect dynamics ─
        # background_modifiers(background) returns (decay_mult, inertia_mult, noise_mult)
        # based on mean background level. We use cortisol+stress as background field
        # so high-stress state makes affect more inert and noisy — realistic.
        _bg_field = {
            "stress":   float(self.neuromod.cortisol),
            "arousal":  float(self.neuromod.norepinephrine),
        }
        try:
            _bg_decay, _bg_inertia, _bg_noise = self.affect_space.get_background_modifiers(_bg_field)
        except Exception:
            _bg_decay, _bg_inertia, _bg_noise = 1.0, 1.0, 1.0

        # ── FIX: get_affective_arousal_modifier → NM-driven arousal scaling ─
        # [0.5, 1.5] multiplier from NE+DA−HT. Feed as `uncertainty` to step()
        # so high NE+DA state amplifies arousal axis dynamics directly.
        try:
            _arousal_mod = self.neuromod.get_affective_arousal_modifier()  # [0.5, 1.5]
            _arousal_uncertainty = max(0.0, (_arousal_mod - 1.0) * 0.5)   # [0, 0.25]
        except Exception:
            _arousal_uncertainty = 0.0

        self.affect_space.step(
            external_impulses=_sleep_impulses,
            time_elapsed=dt,
            wakefulness=self.wakefulness.wakefulness,
            background=_bg_field,
            uncertainty=_arousal_uncertainty,
        )

        # ── Additional NOWA layers (non-decisional) ───────────────────
        self._update_additional_nowa_layers(dt)
        try:
            regulation_snapshot = self.cer.snapshot() if hasattr(self.cer, "snapshot") else {}
            background_snapshot = dict(self._last_background_snapshot or {})
            background_snapshot.setdefault(
                "background_anxiety",
                max(0.0, float(self._axes8().get("stress", 0.0))),
            )
            self._last_stability_snapshot = self.stability_monitor.update(
                emotional_state_snapshot=self._axes8(),
                affective_background_snapshot=background_snapshot,
                neuromodulators_snapshot=(
                    self.neuromod.to_dict() if hasattr(self.neuromod, "to_dict") else {}
                ),
                expectations_snapshot=dict(self._last_emotional_expectations_snapshot or {}),
                regulation_snapshot=regulation_snapshot,
                semantic_emotions_snapshot=list(self._last_semantic_snapshot or []),
                trigger_event=False,
                timestamp=self.total_sim_time,
            )
        except Exception:
            pass


        # ── Drives + energy ───────────────────────────────────────────
        affect_snapshot = self._axes8()
        discharge_overrides: Dict[str, float] = {}
        current_chain = self.chain_executor.current_chain
        if current_chain in ("eating_and_grooming", "morning_awakening", "bedtime_routine"):
            discharge_overrides["energy_need"] = 0.08
        if current_chain in ("exploration", "territorial_patrol", "nesting"):
            discharge_overrides["exploration"] = 0.06
        if current_chain == "social_contact":
            discharge_overrides["social_drive"] = 0.07
        if current_chain in ("activity_burst", "hyperactivity"):
            discharge_overrides["curiosity"] = 0.05

        self._last_drive_snapshot = self.drives.update(
            dt=dt,
            affect_snapshot={"axes": affect_snapshot},
            discharge_overrides=discharge_overrides,
            energy_level=self.energy.snapshot().get("energy", 1.0),
        )

        # ── Task B: EnergySystem — context-aware cognitive load ──────
        active_chain = self.chain_executor.current_chain
        cognitive_load = (
            0.6 if active_chain in ("activity_burst", "hyperactivity", "territorial_patrol")
            else 0.1 if is_sleeping
            else 0.2
        )
        rest_time = 1.0 if is_sleeping else 0.0
        self.energy.update(dt=dt, cognitive_load=cognitive_load, rest_time=rest_time)

        # Pass fatigue → movement speed (fatigue=0 → 1.0×, fatigue=1 → 0.4×)
        if self.pygame_engine:
            energy_snap_b = self.energy.snapshot()
            fatigue_b = float(energy_snap_b.get("fatigue", 0.0))
            if hasattr(self.pygame_engine, "movement"):
                self.pygame_engine.movement.speed = max(0.4, 1.0 - fatigue_b * 0.6)

        # ── CER (affect self-regulation) ───────────────────────────────
        axes = self._axes8()
        cer_result = self.cer.update(
            reward_signal=self._last_chain_reward,
            prediction_error=abs(self._last_chain_reward),
            novelty_score=self.neuromod.get_exploration_level(),
            resolution_success=1.0 if not self.chain_executor.can_continue_chain() else 0.0,
            time_delta=dt,
        )
        _mf = (cer_result or {}).get("modulation_factors") or {}
        self._cer_exploration_bias = float(_mf.get("exploration_bias", 0.0) or 0.0)
        self._cer_decision_threshold_shift = float(_mf.get("decision_threshold_shift", 0.0) or 0.0)
        self._cer_habit_gain_scale = float(_mf.get("habit_gain_scale", 1.0) or 1.0)

        # ── FIX: CER → NM guidance (slow feedback loop) ──────────────
        # apply_neuromodulator_guidance pushes small NM deltas based on
        # CER's internal regulation state — completing the NM↔CER loop.
        # CER.neuromodulator_guidance is recomputed each update() call.
        try:
            self.cer.apply_neuromodulator_guidance(self.neuromod, gain=0.5)
        except Exception:
            pass

        # ── FIX: set_novelty_sensitivity_scale via CER uncertainty ────
        # uncertainty_tension high → agent is anxious/uncertain → reduce
        # hippocampal novelty sensitivity (novelty is threatening).
        # recovery_mode → raise sensitivity (safe to explore again).
        try:
            _unc = float(getattr(self.cer, 'uncertainty_tension', 0.0))
            _rec = bool(getattr(self.cer, 'recovery_mode', False))
            if _rec:
                _ns = 1.3
            elif _unc > 0.5:
                _ns = max(0.5, 1.0 - (_unc - 0.5) * 1.0)  # [0.5, 1.0]
            else:
                _ns = 1.0
            self.hippocampus.set_novelty_sensitivity_scale(_ns)
        except Exception:
            pass

        if axes.get("stress", 0.0) > 0.6:
            reg_impulse = EmotionalImpulse(
                vector={"stress": -float(cer_result.get("valence", 0.0) if isinstance(cer_result, dict) else 0.0) * 0.15, "stability": 0.05},
                intensity=0.3,
                source="cer_regulation",
            )
            self.affect_space.step(
                external_impulses=[reg_impulse],
                time_elapsed=1e-6,
                wakefulness=self.wakefulness.wakefulness,
            )

        # Update postural layer
        self._postural_timer -= dt
        if self._postural_timer <= 0:
            self._update_postural_layer()
            self._postural_timer = 1.0

        # Update micro actions
        self._micro_timer -= dt
        if self._micro_timer <= 0:
            self._dispatch_micro_action()
            self._micro_timer = random.uniform(3.0, 8.0)

        # Update wellbeing indicator
        self._wellbeing_timer -= dt
        if self._wellbeing_timer <= 0 and self.pygame_engine:
            s = self._axes8()
            pathological = self.chain_executor.current_chain == 'chronic_stress'
            self.pygame_engine.set_wellbeing(
                stress=s.get('stress', 0.0),
                valence=s.get('valence', 0.0),
                arousal=s.get('arousal', 0.5),
                pathological_chain=pathological,
                is_sleeping=is_sleeping,
            )
            self._wellbeing_timer = 1.0

        # Circadian background: re-use arousal as a proxy phase for demo visuals
        if self.pygame_engine and hasattr(self.pygame_engine, "set_circadian_phase"):
            # FIX: was using arousal axis as proxy — but arousal is frozen during
            # sleep (pre-fix bug), so the display was always stuck at "day".
            # Use scheduling.circadian_phase directly: it's the true time-of-day signal.
            self.pygame_engine.set_circadian_phase(self.scheduling.circadian_phase)

        # ── Audio ─────────────────────────────────────────────────────
        if self.chain_executor.current_chain:
            self.audio.play_behavior_sound(self.chain_executor.current_chain)

        # ── Completed chain: reward + hippocampus trace + BG outcome ───
        chain_just_finished = bool(self.last_chain_name and not self.chain_executor.can_continue_chain())
        if chain_just_finished and self.last_chain_name:
            prev_chain = self.last_chain_name
            self._last_chain_reward = self._calculate_chain_reward(prev_chain)
            value_state_before = dict(
                self._chain_value_state_before
                or self._collect_chain_state_snapshot(chain_name=prev_chain)
            )
            value_state_after = self._collect_chain_state_snapshot(chain_name=prev_chain)
            stored_experience = None

            events = [
                Event(name=prev_chain, event_type=EventType.ACTION)
            ]
            try:
                before_count = len(getattr(self.hippocampus, 'experiences', []) or [])
                stored_experience = self.hippocampus.store(
                    path=ExperiencePath(events=events),
                    consequence=None,
                    reward=self._last_chain_reward,
                    intensity=abs(self._last_chain_reward) + 0.1,
                )
                after_count = len(getattr(self.hippocampus, 'experiences', []) or [])
                self.logger.debug(f"Hippocampus.store called for {prev_chain}: before={before_count} after={after_count} reward={self._last_chain_reward}")
            except Exception as e:
                self.logger.exception(f"hippocampus.store failed: {e}")

            # Waking outcome tags the core labile tier. ValueLayer.update(mode="online")
            # is a stable writer and is skipped (or raises) while awake.
            try:
                self._last_value_update = self._commit_waking_chain_outcome(
                    chain_name=prev_chain,
                    reward=float(self._last_chain_reward),
                    state_before=value_state_before,
                    state_after=value_state_after,
                    episode=stored_experience,
                )
                self._update_chain_value_statistics(
                    chain_name=prev_chain,
                    reward=float(self._last_chain_reward),
                    value_update=self._last_value_update,
                )
            except Exception:
                self._last_value_update = {}

            # ── FIX: apply_dopamine_delta — DA spike on strong reward ─
            # update_from_signals() adjusts DA via EMA — slow.
            # apply_dopamine_delta() fires an immediate additive spike
            # for salient outcomes (|reward| > 0.3), mimicking phasic DA.
            # Positive reward → DA burst; negative → DA dip (via −delta).
            try:
                if abs(self._last_chain_reward) > 0.3:
                    _da_delta = self._last_chain_reward * 0.15  # max ±0.15
                    self.neuromod.apply_dopamine_delta(_da_delta)
            except Exception:
                pass

            if prev_chain in self.bg_channels:
                self.bg_channels[prev_chain].record_outcome(self._last_chain_reward)

            # Record outcome on BG gate (so gate-level APIs see it)
            try:
                if hasattr(self, 'bg_gate') and callable(getattr(self.bg_gate, 'record_outcome', None)):
                    self.bg_gate.record_outcome(prev_chain, float(self._last_chain_reward))
            except Exception:
                pass

            # ── FIX: Hippocampus.reinforce — strengthen existing memory trace ──
            # On repeated chain completions reinforce() updates the existing
            # signature rather than creating a duplicate entry.
            try:
                events_for_reinforce = [Event(name=prev_chain, event_type=EventType.ACTION)]
                self.hippocampus.reinforce(
                    path=ExperiencePath(events=events_for_reinforce),
                    consequence=None,
                    intensity=abs(self._last_chain_reward) + 0.1,
                )
            except Exception:
                pass

            # ── DopaminergicTDLayer: proper TD error + ConflictArb ────
            try:
                _alpha = 0.3
                _prev_expected = self._expected_reward_by_chain.get(prev_chain, 0.0)
                # compute_td_error: δ = r + γ·V(s') − V(s)
                # V(s)=rolling expected; V(s')=0.0 (terminal step)
                self._last_td_result = self.td_layer.compute_td_error(
                    reward=self._last_chain_reward,
                    value_current=_prev_expected,
                    value_next=0.0,
                    gamma=0.95,
                    cer_stress_level=self.neuromod.cortisol,
                )
                _real_pe = abs(self._last_td_result["delta_clipped"])
                # EMA update of V(s) for next call
                self._expected_reward_by_chain[prev_chain] = (
                    _alpha * self._last_chain_reward + (1.0 - _alpha) * _prev_expected
                )
                self.conflict_arb.register_outcome(
                    reward_signal=float(self._last_chain_reward),
                    prediction_error=float(_real_pe),
                )
                # Phasic DA burst/dip from clipped δ
                _phasic = self._last_td_result.get("phasic_burst", 0.0)
                if abs(_phasic) > 0.05:
                    try:
                        self.neuromod.apply_dopamine_delta(_phasic * 0.12)
                    except Exception:
                        pass
                self.logger.debug(
                    f"[TD] chain={prev_chain} δ={self._last_td_result['delta']:.3f} "
                    f"clipped={self._last_td_result['delta_clipped']:.3f} "
                    f"tonic={self._last_td_result['tonic_level']:.3f}"
                )
            except Exception:
                pass

            # Annotate episodic trace for HIE / replay value-guided consolidation.
            try:
                if stored_experience is not None:
                    stored_experience.value_state_snapshot = dict(value_state_before)
                    stored_experience.value_next_state_snapshot = dict(value_state_after)
                    stored_experience.replay_action_id = str(prev_chain)
                    if self._last_value_update:
                        stored_experience.value_state_key = str(
                            self._last_value_update.get("state_key", "")
                        )
                        stored_experience.replay_priority = float(
                            self._last_value_update.get(
                                "replay_priority",
                                abs(float(self._last_value_update.get("td_error", 0.0))),
                            )
                        )
                        stored_experience.consolidation_weight = float(
                            self._last_value_update.get("consolidation_weight", 0.0)
                        )
                        stored_experience.expected_reward_mean = float(
                            self._last_value_update.get("expected_reward_mean", 0.0)
                        )
                        stored_experience.expected_reward_var = float(
                            self._last_value_update.get("expected_reward_var", 0.0)
                        )
                        stored_experience.expectation_confidence_score = float(
                            self._last_value_update.get("confidence_score", 0.0)
                        )
                        stored_experience.expectation_stability_score = float(
                            self._last_value_update.get("stability_score", 0.0)
                        )
            except Exception:
                pass

            # Same context as chain start. Strength stays 0 until sleep.
            if hasattr(self.intent_memory, "note_selection"):
                self.intent_memory.note_selection(
                    list(getattr(self, "_chain_intent_context", None) or ["idle"]),
                    prev_chain,
                )

            # ── MemorySystem: record chain interaction ─────────────────
            try:
                self.memory_system.record_interaction(
                    chain_name=prev_chain,
                    affect_before=self._chain_affect_before or {},
                    affect_after=self.affect.get_state(),
                    interaction_type=None,
                    current_time=self.total_sim_time,
                )
            except Exception:
                pass

            # Propagate reward to neuromodulators for immediate effect (DA/HT/CORT/ACh)
            try:
                novelty = float(self.neuromod.get_exploration_level()) * 0.3
                stable_rep = bool(self._last_chain_reward > 0.05)
                self.neuromod.update_from_signals(
                    reward=float(self._last_chain_reward),
                    novelty=novelty,
                    conflict=0.0,
                    stable_repetition=stable_rep,
                )
            except Exception:
                pass

            self.last_chain_name = None
            self.chain_start_affect = None
            self._chain_value_state_before = {}

            # ── FIX: recall_trace → replay start-of-chain emotional context ──
            # Converts the saved EmotionalTrace back into an impulse and injects
            # it into affect_space as recall_impulse — "emotional memory" of how
            # the agent felt when this chain began. Fades naturally with decay.
            try:
                if self._chain_start_trace is not None:
                    recall_imp = self.affect_space.recall_trace(
                        self._chain_start_trace, k=0.20
                    )
                    if recall_imp.intensity > 0.01:
                        self.affect_space.step(
                            recall_impulses=[recall_imp],
                            time_elapsed=1e-6,
                            wakefulness=self.wakefulness.wakefulness,
                        )
            except Exception:
                pass

            # ── FIX: distance_to → affect drift novelty signal ────────
            # Measures how much affect changed over the chain's duration.
            # Large drift = unexpected emotional journey → novelty for NM.
            try:
                if self._chain_start_affect_space is not None:
                    _drift = self.affect_space.distance_to(self._chain_start_affect_space)
                    self._last_chain_drift = _drift   # stored for update_acetylcholine below
                    # distance_to raw is ~0–2; normalise to ~0–0.3 novelty range
                    _drift_novelty = min(0.4, _drift * 0.15)
                    if _drift_novelty > 0.05:
                        self.neuromod.update_from_signals(
                            reward=0.0, novelty=_drift_novelty,
                            conflict=0.0, stable_repetition=False,
                        )
            except Exception:
                pass

            self._chain_start_trace = None
            self._chain_start_affect_space = None

            # ── FIX: update_acetylcholine — novelty/repetition → ACh ──
            # ACh gates sleep consolidation (rejected_due_to_ach filter).
            # Drift novelty raises ACh (plasticity up); stable low-drift
            # repetition with positive reward lowers ACh toward baseline.
            try:
                _drift_for_ach = getattr(self, '_last_chain_drift', 0.0)
                _stable = (_drift_for_ach < 0.3 and self._last_chain_reward > 0.05)
                self.neuromod.update_acetylcholine(
                    novelty=min(1.0, _drift_for_ach * 0.5),
                    stable_repetition=_stable,
                )
            except Exception:
                pass
            # Update visible stats immediately when a chain finishes so the UI
            # reflects completed chains (was previously only updated at chain
            # start, which could show 0 until a new chain began).
            try:
                self.stats["chains_completed"] = (
                    self.chain_executor.get_chain_stats().get("total_chains_completed", 0)
                )
            except Exception:
                pass

        # ── Only schedule new action when current one finished ─────────
        if self.action_remaining_s > 0:
            return   # Still executing — do nothing, no flickering

        # ── Continue active chain ─────────────────────────────────────
        if self.chain_executor.can_continue_chain():
            self._dispatch_next_chain_action()
            return

        # ── Start new chain (if cooldown elapsed) ─────────────────────
        if self.chain_cooldown_s <= 0:
            self._try_start_chain()

        # Sleep consolidation occurs during any sleeping state when sufficiently
        # deep (low wakefulness). Previously only `sleep_house` triggered
        # consolidation which skipped other sleeping actions (e.g. hide_house).
        is_deep_sleep  = is_sleeping and (self.wakefulness.wakefulness < 0.3)
        is_light_sleep = is_sleeping and (0.3 <= self.wakefulness.wakefulness < 0.5)

        if is_deep_sleep and not self._sleep_consolidation_pending:
            self._sleep_consolidation_pending = True
            self._run_sleep_consolidation()
        elif is_light_sleep and not self._sleep_consolidation_pending:
            # ── FIX: SleepManager.sleep_cycle — shallow single-cycle replay ──
            # At wakefulness 0.3–0.5 (light sleep) run one sleep_cycle() for
            # TD-filtered replay + BG decay/normalisation — lighter than deep_sleep.
            self._sleep_consolidation_pending = True
            try:
                setattr(self.sleep_manager, "neuromodulators", self.neuromod)
                from learning_guard import learning_allowed

                with learning_allowed():
                    self._flush_owner_feedback()
                _sc_stats = self.sleep_manager.sleep_cycle()
                self.logger.debug(
                    f"[SLEEP/light] sleep_cycle: "
                    f"candidates={_sc_stats.get('candidates',0)} "
                    f"consolidated={_sc_stats.get('total_episodes_consolidated',0)} "
                    f"decay={_sc_stats.get('decay_applied',False)}"
                )
            except Exception as _e:
                self.logger.debug(f"[SLEEP/light] sleep_cycle failed: {_e}")

        if not is_deep_sleep and not is_light_sleep:
            self._sleep_consolidation_pending = False

        # Periodic NOWA persistence
        if self.total_sim_time - self._last_nowa_save >= 120.0:
            self.save_nowa_state()
            self._last_nowa_save = self.total_sim_time

    def _dispatch_next_chain_action(self) -> None:
        """Execute the next action in the current chain."""
        cmd = self.chain_executor.get_next_action_in_chain()
        if cmd:
            self._send_command(cmd)

    def _try_start_chain(self) -> None:
        """Select and start a new behavioral chain, or fall back to idle."""
        drive_suggest = dict(self._last_drive_snapshot or {})

        # Conflict arbitration uses last BG gated scores to modulate exploration/threshold
        gated = dict(getattr(self.bg_gate, "last_gated", {}) or {})
        if gated:
            import math
            scores = list(gated.values())
            total = sum(scores) + 1e-9
            entropy = -sum((s / total) * math.log(s / total + 1e-9) for s in scores)
            sorted_s = sorted(scores, reverse=True)
            top2_gap = (sorted_s[0] - sorted_s[1]) / (sorted_s[0] + 1e-9) if len(sorted_s) > 1 else 1.0

            axes = self._axes8()

            # ── FIX 1b: use real PE from rolling expected reward per chain ─
            # _expected_reward_by_chain is updated each time a chain finishes;
            # at selection time the last-selected chain's PE is the most relevant.
            _arb_pe = abs(self._last_chain_reward or 0.0)  # fallback
            if self.last_chain_name and self.last_chain_name in self._expected_reward_by_chain:
                _expected = self._expected_reward_by_chain[self.last_chain_name]
                _arb_pe = abs(self._last_chain_reward - _expected)

            # ── FIX 1b: axis_conflict feeds as supplementary conflict signal ─
            _affect_conflict = 0.0
            try:
                _affect_conflict = float(self.affect_space.axis_conflict())
            except Exception:
                pass

            arb_result = self.conflict_arb.arbitrate(
                go_signals=scores,
                top2_gap=top2_gap,
                policy_entropy=entropy,
                decision_latency=max(0.0, float(self.chain_cooldown_s)),
                threshold_current=float(self.bg_gate.last_effective_threshold),
                arousal=float(axes.get("arousal", 0.0)),
                stress_level=float(axes.get("stress", 0.0)),
                valence=float(axes.get("valence", 0.0)),
                novelty_score=float(self.neuromod.get_exploration_level()),
                prediction_error=max(_arb_pe, _affect_conflict * 0.5),
                recent_failure_rate=self._recent_failure_rate(),
                working_memory_load=len(gated) / 14.0,
                task_complexity=len(gated) / 14.0,
            )
            self._arb_exploration_bias = float(
                arb_result.get("exploration_override", False)
            ) or 0.0
            self._arb_decision_threshold_shift = float(arb_result.get("threshold_delta", 0.0) or 0.0)

            # ── Task D: inhibit_action — ACC refractory tick ──────────
            # When top-2 chain scores are near-equal, ACC signals ambiguity:
            # agent freezes for 0.5–1.5 s, letting competition resolve itself.
            self._last_arb_mode = str(arb_result.get("control_mode", "—"))
            self._arb_inhibited = bool(arb_result.get("inhibit_action"))
            if arb_result.get("inhibit_action"):
                self.logger.debug(
                    f"[NOWA/ARB] inhibit_action: "
                    f"control_mode={arb_result.get('control_mode')} "
                    f"entropy={entropy:.3f} top2_gap={top2_gap:.3f}"
                )
                self._dispatch_idle_action()
                # Extend cooldown so competition decays before next selection
                self.chain_cooldown_s = max(
                    self.chain_cooldown_s, random.uniform(0.5, 1.5)
                )
                return  # skip chain selection this tick

        candidates = self._build_candidate_chains(drive_suggest)
        chain = candidates[0] if candidates else None

        if chain:
            cmd = self.chain_executor.start_chain(chain)
            if cmd:
                self._send_command(cmd)
                self.stats["chains_completed"] = (
                    self.chain_executor.get_chain_stats()["total_chains_completed"]
                )
                self.chain_cooldown_s   = random.uniform(
                    self.CHAIN_COOLDOWN_MIN_S, self.CHAIN_COOLDOWN_MAX_S
                )
                self.last_chain_name    = chain
                self.chain_start_affect = self.affect.get_state()
                self._chain_value_state_before = self._collect_chain_state_snapshot(chain_name=chain)

                # Selection only. record_trace would write stable strength.
                context = list(self._intent_context) or ["idle"]
                self._chain_intent_context = list(context)
                self.intent_memory.note_selection(context, chain)
                self._intent_context = [chain]

                # ── MemorySystem: snapshot affect before chain ─────────
                try:
                    self._chain_affect_before = self.affect.get_state()
                except Exception:
                    self._chain_affect_before = {}
                # ── FIX: AffectiveSpace.create_trace — emotional imprint at chain start ──
                # Stores a decaying snapshot of affect so at chain completion
                # we can replay it as a recall_impulse ("how I felt starting this").
                try:
                    import copy
                    _start_intensity = min(1.0, 0.5 + abs(self._last_chain_reward) * 0.5)
                    self._chain_start_trace = self.affect_space.create_trace(
                        intensity=_start_intensity, decay_rate=0.015
                    )
                    # Shallow copy of axes dict for distance_to drift metric
                    self._chain_start_affect_space = copy.copy(self.affect_space)
                except Exception:
                    self._chain_start_trace = None
                    self._chain_start_affect_space = None
                return

        # No chain selected → quiet idle
        self._dispatch_idle_action()
        self.chain_cooldown_s = random.uniform(
            self.CHAIN_COOLDOWN_MIN_S, self.CHAIN_COOLDOWN_MAX_S
        )

    def _dispatch_idle_action(self) -> None:
        """
        Pick a calm idle action.
        Uses action_realizer so the correct anim name from the dataset is used.
        """
        idle_pool = [
            "rest_loaf", "doze_shelf", "groom_face", "groom_body",
            "groom_paws", "groom_tail", "stretch_body", "sniff_air",
            "nose_twitch", "whisker_twitch", "ear_forward", "yawn",
        ]
        available = [a for a in idle_pool if a in ACTION_LIBRARY]
        if not available:
            available = ["rest_loaf", "doze_shelf"]

        action_id = random.choice(available)
        cmd = self.action_realizer.realize_action(
            action_id, pressure=0.4,
            context={
                "current_position": self.action_realizer.previous_position,
                "previous_action":  self.action_realizer.previous_action,
            }
        )
        if cmd:
            self._send_command(cmd)
        else:
            # Hard fallback: send loaf_idle directly if realizer returns nothing
            self._send_command({
                "action_id": "rest_loaf",
                "anim":      "loaf_idle",
                "sfx":       None,
                "position":  "floor",
                "duration":  [8, 15],
                "subtitle":  "отдыхает",
                "loop":      True,
                "layer":     "action",
            })


    # ──────────────────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────
    # SESSION SAVE / LOAD
    # ──────────────────────────────────────────────────────────────────────

    def _do_save_session(self, filename: Optional[str] = None) -> None:
        """Save full agent state via AgentStorage + MemorySystem."""
        try:
            self.agent_storage.save_agent(
                hippocampus=self.hippocampus,
                cortex=self.cortex,
                selector=self.chain_selector,
                sleep_manager=self.sleep_manager,
                neuromodulators=self.neuromod,
                temporal=self.temporal_levels,
                affective_persistence=self.affective_persistence,
                affective_background=self.affective_background,
                affective_space=self.affect_space,
                semantic_emotions=self.semantic_emotions,
                emotional_memory=self.emotional_memory,
                emotional_expectations=self.emotional_expectations,
                emotional_regulation=self.cer,
                emotional_stability=self.stability_monitor,
                value_layer=self.value_layer,
                conflict_arbitration=self.conflict_arb,
                intent_memory=self.intent_memory,
                agent=self,
                filename=filename or self._session_save_filename,
            )
            self.memory_system.save_memory()
            self.logger.info("[SAVE] session saved OK")
        except Exception as _e:
            self.logger.warning(f"[SAVE] failed: {_e}")

    def _do_load_session(self, filepath: str) -> None:
        """Restore agent state from a save file."""
        try:
            self.agent_storage.load_agent(
                hippocampus=self.hippocampus,
                cortex=self.cortex,
                selector=self.chain_selector,
                filepath=filepath,
                sleep_manager=self.sleep_manager,
                temporal=self.temporal_levels,
                neuromodulators=self.neuromod,
                affective_persistence=self.affective_persistence,
                affective_background=self.affective_background,
                affective_space=self.affect_space,
                semantic_emotions=self.semantic_emotions,
                emotional_memory=self.emotional_memory,
                emotional_expectations=self.emotional_expectations,
                emotional_regulation=self.cer,
                emotional_stability=self.stability_monitor,
                value_layer=self.value_layer,
                conflict_arbitration=self.conflict_arb,
                intent_memory=self.intent_memory,
                agent=self,
            )
            self._rewire_two_tier_host()
            self.logger.info(f"[LOAD] session loaded from {filepath}")
        except Exception as _e:
            self.logger.warning(f"[LOAD] failed: {_e}")

    def _load_session_if_exists(self) -> None:
        """Load full session on startup if the save file exists."""
        try:
            if self._session_save_path.exists():
                self._do_load_session(str(self._session_save_path))
                return
            # Fallback: load the most recent legacy save if present
            legacy = self.agent_storage.get_save_files()
            if legacy:
                newest = legacy[0].get("path")
                if newest:
                    self._do_load_session(str(newest))
        except Exception as _e:
            self.logger.warning(f"[LOAD] startup session load failed: {_e}")

    # ──────────────────────────────────────────────────────────────────────
    # TRAINING FEEDBACK  (owner rating -> NOWA learning)
    # ──────────────────────────────────────────────────────────────────────

    _RATING_REWARD = {1: -1.0, 2: -0.45, 3: 0.0, 4: 0.50, 5: 1.0}

    def _apply_training_feedback(self, rating: int) -> None:
        """
        Convert a 1-5 owner rating into a NOWA learning event.

        Strategy weights are stable. ``apply_learning_hooks`` runs on the
        next sleep, from the queued rating. Dopamine, the hippocampal
        trace, outcome counts and fast affect still move immediately.
        """
        reward = self._RATING_REWARD.get(rating, 0.0)
        self._training_feedback_count += 1

        # 1. EIL: ingest_observation + interpret → context-aware logging
        try:
            from external_interaction_layer import Observation
            _obs = self.eil.ingest_observation(Observation(
                timestamp=__import__('time').time(),
                source="owner_rating",
                payload={"rating": rating, "chain": self.last_chain_name or "",
                         "dopamine": round(self.neuromod.dopamine, 3)},
                uncertainty=0.0,
            ))
            _interp = self.eil.interpret_observation(_obs)
            self.logger.debug(f"[TRAIN] obs confidence={_interp['confidence']:.2f}")
        except Exception:
            pass

        # 2. EIL: build_action for the feedback event (records intent)
        try:
            self.eil.build_action(
                action_type="owner_feedback",
                parameters={"rating": rating, "reward": reward},
            )
        except Exception:
            pass

        # 3. EIL: queue_feedback → resolve immediately (delayed=0)
        # This path exercises the delayed-feedback queue — useful when the
        # learning effect should be deferred by N sim steps (currently 0).
        try:
            _qfb = self.eil.queue_feedback(
                EILFeedback(reward=reward, success_probability=max(0.0, reward)),
                delay_steps=0,
                current_step=self._training_feedback_count,
            )
            _resolved = self.eil.resolve_feedback(
                current_step=self._training_feedback_count, max_items=4
            )
        except Exception:
            pass

        # Strategy weights wait for sleep. The rating itself is state.
        pending = getattr(self, "_pending_owner_feedback", None)
        if not isinstance(pending, list):
            pending = []
            self._pending_owner_feedback = pending
        pending.append(
            {
                "rating": int(rating),
                "reward": float(reward),
                "chain": str(self.last_chain_name or ""),
            }
        )
        self.logger.info(
            f"[TRAIN] rating={rating} reward={reward:+.2f} "
            f"chain='{self.last_chain_name or ''}' queued for sleep"
        )

    def _flush_owner_feedback(self) -> None:
        """Apply queued owner ratings. Caller holds the sleep guard."""
        pending = list(getattr(self, "_pending_owner_feedback", None) or [])
        self._pending_owner_feedback = []
        if not pending:
            return
        for _dname in DYNAMIC_CHAINS:
            if _dname not in self.eil.strategy_logits:
                self.eil.register_strategy(_dname, 0.0)
        _drives_dict = {
            name: {
                "current": self.drives.drives.get(name, 0.0),
                "set": lambda v, n=name: self.drives.set_drive(n, v),
            }
            for name in list(self.drives.drives.keys())
        }
        _strategies_dict = {
            name: {
                "logit": self.eil.strategy_logits.get(name, 0.0),
                "set_weight": None,
                "set_logit": None,
            }
            for name in list(self.eil.strategy_logits.keys())
        }
        for item in pending:
            if not isinstance(item, dict):
                continue
            try:
                reward = float(item.get("reward", 0.0))
            except (TypeError, ValueError):
                reward = 0.0
            fb = EILFeedback(
                reward=reward,
                success_probability=max(0.0, reward),
                signal={
                    "rating": item.get("rating"),
                    "chain": str(item.get("chain", "") or ""),
                },
            )
            try:
                self.eil.apply_learning_hooks(
                    fb,
                    drives=_drives_dict,
                    strategies=_strategies_dict,
                    alpha=0.15,
                    learning_rate=0.08,
                    strategy_temperature=0.8,
                    strategy_weight_decay=0.005,
                )
            except Exception as _e:
                self.logger.debug(f"[TRAIN] sleep EIL error: {_e}")

        # 2. Phasic DA spike
        try:
            self.neuromod.apply_dopamine_delta(reward * 0.25)
        except Exception:
            pass

        # 3. Hippocampus reinforce last episode
        try:
            _recent = self.hippocampus.recall_recent(limit=1)
            if _recent:
                self.hippocampus.reinforce(_recent[0], reward=reward)
        except Exception:
            pass

        # 4. BG record_outcome
        try:
            if self.last_chain_name:
                if self.last_chain_name in self.bg_channels:
                    self.bg_channels[self.last_chain_name].record_outcome(reward)
                self.bg_gate.record_outcome(self.last_chain_name, reward)
        except Exception:
            pass

        # 5. AffectiveSpace impulse
        try:
            self.affect_space.step(
                background={"valence": reward * 0.30, "arousal": abs(reward) * 0.18},
            )
        except Exception:
            pass

    def _send_command(self, cmd: Dict[str, Any]) -> None:
        """
        Send command to pygame engine and update action timer.

        Duration from the command is in SECONDS (config values already are).
        action_remaining_s is set to a random value in [min, max].
        """
        self.current_action = cmd

        # Track action sequence for ChainMemory.match_bias()
        _aid = cmd.get("action_id", "")
        if _aid:
            self._recent_action_seq.append(_aid)
            if len(self._recent_action_seq) > self._MAX_RECENT_SEQ:
                self._recent_action_seq.pop(0)

        if self.pygame_engine:
            # Warn early if the anim name won't be found in the engine
            anim_id = cmd.get("anim", "")
            if hasattr(self.pygame_engine, "clips") and anim_id and anim_id not in self.pygame_engine.clips:
                self.logger.warning(
                    f"Anim '{anim_id}' not in loaded clips — sprite won't show. "
                    f"Available: {list(self.pygame_engine.clips.keys())[:5]}..."
                )
            self.pygame_engine.queue_action(cmd)

        # Duration: list [min_s, max_s]
        dur = cmd.get("duration", [5, 15])
        min_s = float(dur[0]) * self.DURATION_SCALE
        max_s = float(dur[1]) * self.DURATION_SCALE
        self.action_remaining_s = random.uniform(min_s, max_s)

        self.stats["actions_executed"] += 1

        self.logger.debug(
            f"Dispatched {cmd.get('action_id','?')} "
            f"dur={self.action_remaining_s:.1f}s "
            f"anim={cmd.get('anim','?')} pos={cmd.get('position','?')}"
        )

    def _update_postural_layer(self) -> None:
        """Отправляет постуральную анимацию на основе текущего affect.state."""
        s = self.affect.state
        stress    = s.get('stress', 0.0)
        curiosity = s.get('curiosity', 0.5)
        arousal   = s.get('arousal', 0.5)
        tiredness = s.get('tiredness', 0.0)

        if stress > 0.6:
            anim = 'ears_flat_hold'
        elif tiredness > 0.7:
            anim = 'eyes_droop_hold'
        elif curiosity > 0.65:
            anim = 'ears_forward_hold'
        elif arousal > 0.75:
            anim = 'tail_up_hold'
        else:
            return  # нейтральная поза — не перекрывать action

        if self.pygame_engine:
            self.pygame_engine.queue_action({
                'action_id': f'postural_{anim}',
                'anim':      anim,
                'sfx':       None,
                'position':  'current',
                'duration':  [8, 20],
                'subtitle':  '',
                'loop':      True,
                'layer':     'postural',
            })

    def _dispatch_micro_action(self) -> None:
        """Проигрывает короткую микро-анимацию на micro-слое, не прерывая action."""
        micro_pool = ['whisker_loop', 'nose_twitch_loop', 'head_track_loop']
        anim = random.choice(micro_pool)
        if self.pygame_engine and hasattr(self.pygame_engine, 'clips'):
            if anim not in self.pygame_engine.clips:
                return
        if self.pygame_engine:
            self.pygame_engine.queue_action({
                'action_id': f'micro_{anim}',
                'anim':      anim,
                'sfx':       None,
                'position':  'current',
                'duration':  [2, 4],
                'subtitle':  '',
                'loop':      False,
                'layer':     'micro',
            })

    def step(self, dt: Optional[float] = None) -> None:
        """Backward-compatible single-step API."""
        if dt is None:
            dt_v = self.SIM_DT
        else:
            try:
                dt_v = max(0.0, float(dt))
            except Exception:
                dt_v = self.SIM_DT
        self.sim_step(dt_v)

    # ------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------

    def run(self, max_duration: Optional[float] = None) -> None:
        """Run the main game loop."""
        if not self.pygame_engine:
            self.logger.error("Cannot run without pygame engine")
            return

        self.running = True
        self.pygame_engine.start_loop()

        # Dispatch an immediate idle so the sprite appears before first sim tick
        self._dispatch_idle_action()
        self.pygame_engine.process_actions()

        # Sim accumulator: we run sim at SIM_FPS regardless of render fps
        sim_accumulator = 0.0
        last_wall = time.perf_counter()

        self.logger.info("Main loop started")

        try:
            import pygame
        except ImportError:
            pygame = None

        try:
            while self.running:
                # ── Wall-clock delta ──────────────────────────────────
                now      = time.perf_counter()
                wall_dt  = now - last_wall
                last_wall = now

                # Guard against huge deltas (e.g. after focus loss)
                wall_dt = min(wall_dt, 0.2)

                # ── Events ───────────────────────────────────────────
                if pygame:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            self.running = False
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_ESCAPE:
                                self.running = False
                            elif event.key == pygame.K_d:
                                self.pygame_engine.toggle_debug()
                            elif (event.key == pygame.K_s
                                  and (pygame.key.get_mods() & pygame.KMOD_CTRL)):
                                self._do_save_session()
                            # Forward arrow keys to engine scroll
                            elif (event.key in (pygame.K_UP, pygame.K_DOWN)
                                  and getattr(self.pygame_engine, "show_state_window", False)):
                                delta = -1 if event.key == pygame.K_UP else 1
                                eng = self.pygame_engine
                                eng._state_scroll = max(0, eng._state_scroll + delta)
                        # Mousewheel scroll for state window
                        elif event.type == pygame.MOUSEWHEEL:
                            if getattr(self.pygame_engine, "show_state_window", False):
                                eng = self.pygame_engine
                                eng._state_scroll = max(0, eng._state_scroll - event.y)
                        elif event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1:
                                ui_action = self.pygame_engine.handle_mouse_click(event.pos)
                                if ui_action == "toggle_audio":
                                    new_state = not getattr(self.audio, "enabled", False)
                                    if hasattr(self.audio, "set_enabled"):
                                        self.audio.set_enabled(new_state)
                                    else:
                                        self.audio.enabled = new_state
                                    if hasattr(self.pygame_engine, "set_audio_enabled"):
                                        self.pygame_engine.set_audio_enabled(getattr(self.audio, "enabled", False))
                                    self.logger.info(
                                        f"Audio {'enabled' if getattr(self.audio, 'enabled', False) else 'disabled'} via UI"
                                    )
                                # ── Training rating ───────────────────
                                elif ui_action and ui_action.startswith("training:"):
                                    try:
                                        _rating = int(ui_action.split(":")[1])
                                        self._apply_training_feedback(_rating)
                                    except Exception as _e:
                                        self.logger.debug(f"Training feedback error: {_e}")

                # ── Sim ticks (fixed timestep) ────────────────────────
                sim_accumulator += wall_dt
                while sim_accumulator >= self.SIM_DT:
                    self.sim_step(self.SIM_DT)
                    sim_accumulator -= self.SIM_DT

                # ── Render (uncapped / capped at RENDER_FPS) ──────────
                self.pygame_engine.process_actions()
                self.pygame_engine.update(dt=wall_dt)

                # Debug overlay
                self.pygame_engine.set_debug_lines(self._build_debug_lines())
                self.pygame_engine.set_state_snapshot(self.get_state_snapshot())

                self.pygame_engine.render()

                # NOWA HUD snapshot (spec)
                if getattr(self.pygame_engine, "show_debug", False) and hasattr(self.pygame_engine, "set_nowa_state"):
                    bg_top3 = sorted(
                        (getattr(self.bg_gate, "last_gated", {}) or {}).items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )[:3]
                    self.pygame_engine.set_nowa_state(
                        {
                            "dopamine": self.neuromod.dopamine,
                            "serotonin": self.neuromod.serotonin,
                            "norepinephrine": self.neuromod.norepinephrine,
                            "cortisol": self.neuromod.cortisol,
                            "acetylcholine": self.neuromod.acetylcholine,
                            **self.drives.snapshot(),
                            **self._axes8(),
                            "wakefulness": self.wakefulness.wakefulness,
                            "cognitive_reliability": self.wakefulness.get_cognitive_reliability(),
                            "bg_top3": bg_top3,
                            "cer_exploration": float(self._cer_exploration_bias),
                            "semantic_top": list(self._last_semantic_snapshot or [])[:2],
                            "expectation_top": str(
                                self._last_emotional_expectations_snapshot.get("dominant_forecast", "")
                            ),
                            "expectation_outlook": str(
                                self._last_emotional_expectations_snapshot.get("global_outlook", "")
                            ),
                        }
                    )

                # Duration limit
                if max_duration and self.total_sim_time >= max_duration:
                    self.logger.info(f"Max duration {max_duration}s reached")
                    self.running = False

                # Cap render framerate
                if pygame:
                    self.pygame_engine.clock.tick(self.RENDER_FPS)

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
            import traceback; traceback.print_exc()
        finally:
            self.cleanup()

    def _build_debug_lines(self) -> List[str]:
        s = self._axes8()
        drives = self.drives.snapshot()
        chain = self.chain_executor.current_chain or "—"
        action = (self.current_action or {}).get("action_id", "—")
        anim   = (self.current_action or {}).get("anim", "—")
        remaining = self.action_remaining_s
        return [
            f"Sim time:  {self.total_sim_time:.1f}s   ticks: {self.tick_count}",
            f"Chain:     {chain}",
            f"Action:    {action}  anim={anim}",
            f"Remaining: {remaining:.1f}s   cooldown: {self.chain_cooldown_s:.1f}s",
            f"Valence:   {float(s.get('valence', 0.0)):+.2f}   "
            f"Arousal: {float(s.get('arousal', 0.0)):+.2f}   "
            f"Stress: {float(s.get('stress', 0.0)):+.2f}",
            f"Drives:    energy_need={drives.get('energy_need',0.0):.2f}  "
            f"curiosity={drives.get('curiosity',0.0):.2f}  "
            f"social={drives.get('social_drive',0.0):.2f}",
            f"Wakefulness: {self.wakefulness.wakefulness:.2f}  "
            f"reliability={self.wakefulness.get_cognitive_reliability():.2f}",
            # Task B: energy/fatigue
            (lambda es: (
                f"Energy: {float(es.get('energy',1.0)):.2f}  "
                f"Fatigue: {float(es.get('fatigue',0.0)):.2f}"
                + ("  ⚠ SUPPRESS" if es.get("suppress_internal_cycles") else "")
            ))(self.energy.snapshot()),
            # Task D: arbitration
            f"ARB: mode={getattr(self,'_last_arb_mode','—')}  "
            f"{'⚠ INHIBITED' if getattr(self,'_arb_inhibited',False) else 'ok'}",
            f"DEC: mode={str((self._last_decision_arbitration_output or {}).get('decision_mode', 'HABITUAL'))}  "
            f"unc={float((self._last_decision_arbitration_output or {}).get('global_uncertainty', 0.0)):.2f}",
            f"VAL: td={float((self._last_value_update or {}).get('td_error', 0.0)):+.3f}  "
            f"states={int((self.value_layer.snapshot() if hasattr(self.value_layer, 'snapshot') else {}).get('state_count', 0))}",
            f"STM: idx={float((self._last_stability_snapshot or {}).get('stability_index', 1.0)):.2f}  "
            f"rec={(self._last_stability_snapshot or {}).get('recommendation', 'none')}",
        ]

    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        self._do_save_session()
        self.save_nowa_state()
        self.audio.cleanup()
        if self.pygame_engine:
            self.pygame_engine.cleanup()
        self.logger.info("Cleanup complete")

    def _action_label_ru(self, action_id: str) -> str:
        meta = ACTION_LIBRARY.get(action_id)
        if not meta:
            return action_id
        return meta.subtitle_ru or action_id

    def _chain_preview(self, chain_name: str) -> str:
        from tama_i18n import chain_label

        return chain_label(chain_name)

    def _build_candidate_chains(
        self,
        drive_suggestions: Dict[str, float],
        update_runtime: bool = True,
    ) -> List[str]:
        """BG Go/NoGo competition over chain channels."""
        DRIVE_TO_CHAINS = {
            "energy_need": ["eating_and_grooming", "morning_awakening", "bedtime_routine"],
            "exploration": ["exploration", "territorial_patrol", "nesting"],
            "social_drive": ["social_contact"],
            "curiosity": ["activity_burst", "hyperactivity", "exploration"],
            "goal_tension": ["territorial_patrol", "nesting", "full_grooming"],
        }

        pressure_vector: Dict[str, float] = {}
        for drive, chains in DRIVE_TO_CHAINS.items():
            drive_val = float(drive_suggestions.get(drive, 0.0) or 0.0)
            for chain in chains:
                pressure_vector[chain] = pressure_vector.get(chain, 0.0) + drive_val * 0.5

        for chain in BEHAVIORAL_CHAINS:
            pressure_vector.setdefault(chain, 0.05)

        # ── Dynamic chains: ensure bg_channels + pressure entries exist ─
        for dname in DYNAMIC_CHAINS:
            pressure_vector.setdefault(dname, 0.05)
            if dname not in self.bg_channels:
                host = getattr(self, "nowa", None)
                if host is not None and hasattr(host, "register_action_channel"):
                    host.register_action_channel(dname)
                else:
                    from basal_ganglia import ActionChannel
                    from learning_guard import initializing

                    with initializing():
                        self.bg_channels[dname] = ActionChannel(action_id=dname)
                self.logger.info(f"[DYN] registered new BG channel: {dname}")
            if update_runtime:
                self.chain_selector.register_action(dname)

        # ── IntentMemory: habit-context pressure boost ────────────────
        # Adds a small pressure nudge for chains this context has predicted in the past.
        try:
            _intent_p = self.intent_memory.activate_by_context(
                list(self._intent_context) or ["idle"]
            )
            for _ichain, _ip in _intent_p.items():
                if _ichain in pressure_vector:
                    pressure_vector[_ichain] += min(0.12, _ip * 0.05)
        except Exception:
            pass

        # ── SchedulingSystem: circadian drive suggestions ─────────────
        _sched_chain_map = {
            "eating":          "eating_and_grooming",
            "bedtime_routine": "bedtime_routine",
            "rest":            "nesting",
            "play":            "activity_burst",
            "exploration":     "exploration",
            "social_contact":  "social_contact",
        }
        try:
            _sugg = self.scheduling.get_drive_suggestions()
            for _sk, _cn in _sched_chain_map.items():
                _urg = _sugg.get(_sk, 0.0)
                if _urg > 0.15 and _cn in pressure_vector:
                    pressure_vector[_cn] += _urg * 0.10
        except Exception:
            pass

        try:
            _circ = self.scheduling.get_circadian_state()
            _act  = float(_circ.get("activity_level", 0.5))
            if _circ.get("is_day", 1.0) < 0.5:   # night phase → push sleep/groom
                for _ch in ("bedtime_routine", "nesting", "full_grooming"):
                    if _ch in pressure_vector:
                        pressure_vector[_ch] += (1.0 - _act) * 0.05
            else:                                  # day phase → push activity
                for _ch in ("activity_burst", "exploration", "morning_awakening"):
                    if _ch in pressure_vector:
                        pressure_vector[_ch] += _act * 0.03
        except Exception:
            pass

        # ── MemorySystem: learned preference weights ───────────────────
        # get_chain_weight returns float [0.5, 1.5]; multiply existing pressure.
        try:
            for _mch in list(pressure_vector.keys()):
                _w = self.memory_system.get_chain_weight(_mch)
                if _w != 1.0:
                    pressure_vector[_mch] *= max(0.5, min(1.5, float(_w)))
        except Exception:
            pass

        # ── DopaminergicTDLayer: exploration delta from last TD result ─
        # Positive phasic burst → reduce exploration pressure.
        # Negative dip → increase exploration pressure.
        try:
            if self._last_td_result:
                _expl_d = self.td_layer.compute_exploration_delta(
                    delta_sign=int(self._last_td_result.get("delta_sign", 0)),
                    baseline_exploration=float(pressure_vector.get("exploration", 0.1)),
                )
                if "exploration" in pressure_vector:
                    pressure_vector["exploration"] = max(
                        0.0, pressure_vector["exploration"] + _expl_d
                    )
        except Exception:
            pass

        # ── ChainMemory.match_bias — temporal sequence prediction ──────
        try:
            _cm = getattr(self.sleep_manager, 'chain_memory', None)
            if _cm is not None and self._recent_action_seq:
                _prefixed_seq = [f"action:{a}" for a in self._recent_action_seq]
                _bias = _cm.match_bias(_prefixed_seq)
                for action_id, bias_weight in _bias.items():
                    for cname, steps in {**BEHAVIORAL_CHAINS, **DYNAMIC_CHAINS}.items():
                        if steps:
                            last_step = steps[-1]
                            last_action = last_step[0] if isinstance(last_step, tuple) else last_step
                            if last_action == action_id and cname in pressure_vector:
                                _scaled = max(-0.10, min(0.10, bias_weight * 0.08))
                                pressure_vector[cname] += _scaled
        except Exception:
            pass

        habit_strengths = {chain: ch.habit_strength for chain, ch in self.bg_channels.items()}

        # ── FIX: temporal_discount → horizon bias in pressure_vector ─
        # high HT/low DA → temporal_discount > 1.0 → prefer long-horizon chains
        # high DA/low HT → temporal_discount < 1.0 → prefer immediate chains
        try:
            _td = self.neuromod.get_temporal_discount()   # [0.5, 1.5]
            _td_bias = (_td - 1.0) * 0.10               # [-0.05, +0.05]
            _long_chains  = ("nesting", "full_grooming", "bedtime_routine", "territorial_patrol")
            _short_chains = ("activity_burst", "eating_and_grooming", "morning_awakening")
            for ch in _long_chains:
                if ch in pressure_vector:
                    pressure_vector[ch] += _td_bias
            for ch in _short_chains:
                if ch in pressure_vector:
                    pressure_vector[ch] -= _td_bias
        except Exception:
            pass

        wake = self.wakefulness.wakefulness
        if wake > 0.7:
            pressure_vector["bedtime_routine"] = pressure_vector.get("bedtime_routine", 0.1) + wake * 0.5
            pressure_vector["full_grooming"] = pressure_vector.get("full_grooming", 0.1) + wake * 0.2

        # ── Task B: EnergySystem → bedtime pressure ───────────────────
        energy_snap = self.energy.snapshot()
        fatigue  = float(energy_snap.get("fatigue", 0.0))
        suppress = bool(energy_snap.get("suppress_internal_cycles", False))
        if suppress:
            # Critical exhaustion → override everything with sleep
            pressure_vector["bedtime_routine"] = max(
                pressure_vector.get("bedtime_routine", 0.1), 0.8
            )
            for chain in ("activity_burst", "hyperactivity", "territorial_patrol"):
                pressure_vector[chain] = min(pressure_vector.get(chain, 0.05), 0.02)
        elif fatigue > 0.6:
            pressure_vector["bedtime_routine"] = (
                pressure_vector.get("bedtime_routine", 0.1) + fatigue * 0.3
            )
            pressure_vector["full_grooming"] = (
                pressure_vector.get("full_grooming", 0.1) + fatigue * 0.15
            )

        # ── Task A: Hippocampal memory nudge (±0.15) ──────────────────
        mem_pressure = self._memory_pressure(limit=8)
        for chain, delta in mem_pressure.items():
            if chain in pressure_vector:
                pressure_vector[chain] = pressure_vector[chain] + delta

        # ── FIX: obsessiveness_map → detect affect-axis looping risk ──
        # obsessiveness(axis) = high inertia + low fall_rate + high focus.
        # High stress-obsessiveness → agent is "stuck" in stress loop →
        # strongly boost self-regulation chains (bedtime, grooming).
        # High curiosity-obsessiveness → engaged exploration, light boost.
        try:
            _obs = self.affect_space.obsessiveness_map()
            _stress_obs = float(_obs.get("stress", 0.0))
            _curiosity_obs = float(_obs.get("curiosity", 0.0))
            if _stress_obs > 0.65:
                _obs_scale = (_stress_obs - 0.65) * 0.40   # up to +0.14
                pressure_vector["bedtime_routine"] = (
                    pressure_vector.get("bedtime_routine", 0.1) + _obs_scale
                )
                pressure_vector["full_grooming"] = (
                    pressure_vector.get("full_grooming", 0.1) + _obs_scale * 0.6
                )
                self.logger.debug(
                    f"[OBS] stress_obsessiveness={_stress_obs:.3f} "
                    f"→ bedtime+{_obs_scale:.3f}"
                )
            if _curiosity_obs > 0.6:
                _obs_scale = (_curiosity_obs - 0.6) * 0.20
                pressure_vector["exploration"] = (
                    pressure_vector.get("exploration", 0.1) + _obs_scale
                )
        except Exception:
            pass

        # ── FIX A2: recall_by_drive — drive-targeted hippocampal recall ──
        # Instead of only recent experiences, pull memories specifically
        # associated with the most active drive. This biases BG toward
        # chains that previously resolved this drive, not just recent ones.
        try:
            if self._last_drive_snapshot:
                dominant_drive = max(
                    self._last_drive_snapshot.items(),
                    key=lambda kv: float(kv[1] or 0),
                )
                if float(dominant_drive[1] or 0) > 0.2:
                    drive_exps = self.hippocampus.recall_by_drive(
                        active_drive=dominant_drive[0], limit=6
                    )
                    for exp in drive_exps:
                        if exp.path and exp.path.events and exp.reward > 0:
                            name = exp.path.events[0].name
                            if name in pressure_vector:
                                boost = exp.reward * exp.encoding_strength * 0.10
                                pressure_vector[name] = pressure_vector[name] + boost
        except Exception:
            pass

        # ── FIX: recall_signature — semantic memory search in conflict ──
        # When opposing affects co-activate (axis_conflict high), the agent
        # is in ambiguous territory. recall_signature queries hippocampus
        # with current affect+drive features and finds the most similar past
        # experiences by signature — their chains get a targeted boost.
        # This is richer than recall_by_drive: context+drive+feature match.
        try:
            _ac = self.affect_space.axis_conflict()
            if _ac > 0.35:
                _affect_label = self._affect_label()
                _query = {
                    "features": [_affect_label] + [
                        f"drive_{k}" for k, v in (self._last_drive_snapshot or {}).items()
                        if float(v or 0) > 0.4
                    ],
                    "intensity": min(1.0, _ac + 0.3),
                    "reward": 0.0,
                }
                _sig_result = self.hippocampus.recall_signature(_query)
                _novelty_class = _sig_result.get("novelty_class", "familiar")
                # familiar → exploit known good chains; novel → boost exploration
                if _novelty_class == "familiar":
                    for entry in _sig_result.get("similarity_top_k", [])[:3]:
                        for feat in entry.get("features", set()):
                            if feat in pressure_vector:
                                pressure_vector[feat] += entry["similarity"] * 0.08
                else:
                    # novel conflict state → push exploration
                    pressure_vector["exploration"] = (
                        pressure_vector.get("exploration", 0.1) + _ac * 0.10
                    )
                self.logger.debug(
                    f"[SIG] axis_conflict={_ac:.3f} novelty={_novelty_class} "
                    f"novel_score={_sig_result.get('novelty_score', 0):.3f}"
                )
        except Exception:
            pass

        # ── Task A: Cortex pattern activation ─────────────────────────
        # Patterns consolidated during sleep bias chains matching current affect
        affect_label = self._affect_label()
        activated_patterns = self.cortex.activate([affect_label])
        for pattern in activated_patterns:
            for token in pattern.signature:
                if token in pressure_vector:
                    boost = pattern.strength * pattern.source_experiences * 0.04
                    pressure_vector[token] = pressure_vector.get(token, 0.05) + boost

        # ── FIX 1: AffectiveSpace.decision_bias() → pressure modulation ─
        # decision_bias() returns scores on: risk, response_speed, word_choice,
        # empathy, goal_priority. These map to behavioral chain categories:
        # goal_priority → goal-directed active chains
        # risk          → approach/avoidance balance
        # response_speed → urgency-driven chains
        # empathy        → social chains
        try:
            d_bias = self.affect_space.decision_bias()
            goal_prio    = float(d_bias.get("goal_priority",    0.0))
            risk         = float(d_bias.get("risk",             0.0))
            resp_speed   = float(d_bias.get("response_speed",   0.0))
            empathy      = float(d_bias.get("empathy",          0.0))
            _bias_scale  = 0.12  # conservative scale to not dominate drives
            # goal_priority: boost directed, persistent chains
            for chain in ("exploration", "territorial_patrol", "nesting", "full_grooming"):
                if chain in pressure_vector:
                    pressure_vector[chain] += goal_prio * _bias_scale
            # risk > 0 → bold/exploratory; risk < 0 → defensive/hiding
            for chain in ("activity_burst", "hyperactivity"):
                if chain in pressure_vector:
                    pressure_vector[chain] += max(0.0, risk) * _bias_scale
            for chain in ("bedtime_routine", "dust_bathing"):
                if chain in pressure_vector:
                    pressure_vector[chain] += max(0.0, -risk) * _bias_scale * 0.5
            # response_speed: boost fast/active chains when high
            for chain in ("activity_burst", "morning_awakening"):
                if chain in pressure_vector:
                    pressure_vector[chain] += max(0.0, resp_speed) * _bias_scale * 0.8
            # empathy: social drive
            if "social_contact" in pressure_vector:
                pressure_vector["social_contact"] += empathy * _bias_scale
        except Exception:
            pass

        # ── FIX 1b: AffectiveSpace.axis_conflict() → conflict_arb input ─
        # axis_conflict() returns [0, 1] — higher means opposing affects
        # co-activated (e.g. high curiosity + high stability).
        # Feed this as the conflict signal into the arbitration entropy calc,
        # and also as additional NE spike (conflict → arousal → norepinephrine).
        try:
            _affect_conflict = self.affect_space.axis_conflict()
            if _affect_conflict > 0.3:
                # Spike NE proportionally — conflict is alerting
                self.neuromod.norepinephrine = min(
                    1.0,
                    self.neuromod.norepinephrine + _affect_conflict * 0.04,
                )
                self.neuromod._clamp_all()
        except Exception:
            pass

        action_metadata = self._build_chain_action_metadata(
            pressure_vector,
            persist=update_runtime,
        )
        value_snapshot = {}
        try:
            value_snapshot = self.value_layer.snapshot()
        except Exception:
            value_snapshot = {}
        action_stability_values = [
            float(meta.get("stability_score", 0.0))
            for meta in (action_metadata or {}).values()
            if isinstance(meta, dict)
        ]
        action_stability_mean = (
            float(sum(action_stability_values) / float(max(1, len(action_stability_values))))
            if action_stability_values
            else None
        )
        causality_mean = None
        try:
            sleep_stats = dict(getattr(self.sleep_manager, "last_sleep_replay_stats", {}) or {})
            if "replay_causality_mean" in sleep_stats:
                causality_mean = float(sleep_stats.get("replay_causality_mean", 0.0))
        except Exception:
            causality_mean = None

        decision_output: Dict[str, Any] = {}
        if update_runtime:
            try:
                decision_output = self.decision_arbitrator.arbitrate(
                    pressure_vector=pressure_vector,
                    action_metadata=action_metadata,
                    error_likelihood=float(value_snapshot.get("last_error_likelihood", 0.0)),
                    surprise=float(value_snapshot.get("last_prediction_shock_score", 0.0)),
                    stress_level=float(self._axes8().get("stress", 0.0)),
                    action_stability_mean=action_stability_mean,
                    causality_mean=causality_mean,
                )
            except Exception:
                decision_output = {}
        else:
            decision_output = dict(self._last_decision_arbitration_output or {})

        decision_mode = str(
            decision_output.get(
                "decision_mode",
                (self._last_decision_arbitration_output or {}).get("decision_mode", "HABITUAL"),
            )
        ).upper()
        policy_temperature = float(
            decision_output.get(
                "policy_temperature",
                getattr(self.bg_gate.thalamic_gate, "base_temperature", 0.35),
            )
        )
        uncertainty = float(
            decision_output.get(
                "global_uncertainty",
                (self._last_decision_arbitration_output or {}).get("global_uncertainty", 0.0),
            )
        )
        if update_runtime:
            self._last_decision_arbitration_output = {
                "decision_mode": decision_mode,
                "global_uncertainty": uncertainty,
                "global_uncertainty_raw": float(decision_output.get("global_uncertainty_raw", uncertainty)),
                "uncertainty_ema": float(decision_output.get("uncertainty_ema", uncertainty)),
                "policy_temperature": policy_temperature,
                "policy_reliability": float(decision_output.get("policy_reliability", 1.0)),
                "effective_threshold": float(decision_output.get("effective_threshold", 0.0)),
                "normalized_td_variance": float(decision_output.get("normalized_td_variance", 0.0)),
            }

        if update_runtime and decision_mode == "DELIBERATIVE" and self.deliberative_planning_enabled:
            pressure_vector, self._last_planning_stats = self._apply_deliberative_chain_planning(
                pressure_vector=pressure_vector,
            )
        elif update_runtime:
            self._last_planning_stats = {
                "planning_bias_applied": False,
                "supported_actions": 0,
                "support_mean": 0.0,
                "rollout_depth": 0,
                "rollout_samples": 0,
                "rollout_used": 0,
            }

        exploration_bias = self.neuromod.get_exploration_level()
        exploration_bias += self._cer_exploration_bias + self._arb_exploration_bias
        exploration_bias += uncertainty * 0.20
        decision_shift = self._cer_decision_threshold_shift + self._arb_decision_threshold_shift
        habit_scale = self._cer_habit_gain_scale

        # ── FIX: PFC wakefulness modifiers → BG selection quality ────
        # get_pfc_signal_noise_modifier: [1.0..1.7] — tired = noisy = more random
        #   → higher noise → higher exploration_bias (less deterministic BG)
        # get_pfc_weight_modifier(conflict): [0..1] — tired+conflict → weaker PFC
        #   → scales decision_threshold_shift down (reduced cognitive control)
        # get_pfc_signal_strength_modifier: always 1.0 per spec (noise, not weakness)
        try:
            _pfc_noise    = self.wakefulness.get_pfc_signal_noise_modifier()   # [1.0, 1.7]
            _affect_conf  = 0.0
            try:
                _affect_conf = float(self.affect_space.axis_conflict())
            except Exception:
                pass
            _pfc_weight   = self.wakefulness.get_pfc_weight_modifier(conflict=_affect_conf)  # [0, 1]
            # noise → randomness in exploration: (noise-1) maps [0..0.7] → [0..0.21] additive
            exploration_bias += (_pfc_noise - 1.0) * 0.30
            # reduced PFC weight → attenuate cognitive decision modulations
            decision_shift  *= _pfc_weight
            habit_scale     = max(0.5, habit_scale * _pfc_weight)
        except Exception:
            pass

        try:
            if update_runtime and policy_temperature > 0.0:
                self.bg_gate.thalamic_gate.base_temperature = max(
                    float(getattr(self.bg_gate.thalamic_gate, "min_temperature", 0.03)),
                    float(policy_temperature),
                )
        except Exception:
            pass

        gated_scores = self.bg_gate.process(
            pressure_vector=pressure_vector,
            dopamine_level=self.neuromod.dopamine,
            cortisol_level=self.neuromod.cortisol,
            norepinephrine_level=self.neuromod.norepinephrine,
            habit_strengths=habit_strengths,
            aversive_signal=self._axes8().get("stress", 0.0),
            exploration_bias=exploration_bias,
            decision_threshold_shift=decision_shift,
            habit_gain_scale=habit_scale,
        )

        sorted_chains = sorted(gated_scores.items(), key=lambda x: x[1], reverse=True)
        if not update_runtime:
            return [c for c, _ in sorted_chains[:3]]

        selected = self.bg_gate.thalamic_gate.select(
            gated_scores=gated_scores,
            norepinephrine_level=self.neuromod.norepinephrine,
            exploration_bias=exploration_bias,
        )

        if selected == NO_ACTION:
            return []

        candidates = [selected] + [c for c, _ in sorted_chains if c != selected][:2]
        return candidates

    def get_state_snapshot(self) -> Dict[str, Any]:
        chain_stats = self.chain_executor.get_chain_stats()
        drives = self.drives.snapshot()
        affect = self._axes8()
        cycles: Dict[str, Any] = {}
        try:
            circadian = dict(self.scheduling.get_circadian_state() or {})
        except Exception:
            circadian = {}
        if "phase" not in circadian:
            circadian["phase"] = max(0.0, min(1.0, affect.get("arousal", 0.5)))

        current_chain = chain_stats.get("current_chain")
        current_progress = int(chain_stats.get("current_progress", 0))
        chain_actions = BEHAVIORAL_CHAINS.get(current_chain, []) if current_chain else []
        # Extract action IDs from tuples or strings
        next_action_ids = []
        for step in chain_actions[current_progress:current_progress + 3]:
            if isinstance(step, tuple):
                action_id, _ = step
            else:
                action_id = step
            next_action_ids.append(action_id)

        current_action = self.current_action or {}
        current_action_id = current_action.get("action_id", "")

        candidate_chains = self._build_candidate_chains(drives, update_runtime=False)
        gated = dict(getattr(self.bg_gate, "last_gated", {}) or {})
        top_bg = sorted(gated.items(), key=lambda x: x[1], reverse=True)[:3]

        return {
            "tick":           self.tick_count,
            "time":           self.total_sim_time,
            "running":        self.running,
            "paused":         self.paused,
            "current_action": current_action,
            "action_remaining_s": self.action_remaining_s,
            "chain_cooldown_s": self.chain_cooldown_s,
            "stats":          self.stats.copy(),
            "chain_stats":    chain_stats,
            "affect":         affect,
            "cycles":         cycles,
            "drives":         drives,
            "audio_enabled":  bool(getattr(self.audio, "enabled", False)),
            "circadian":      circadian,
            "nowa": {
                "neuromodulators": self.neuromod.to_dict() if hasattr(self.neuromod, "to_dict") else {},
                "wakefulness": self.wakefulness.wakefulness,
                "cognitive_reliability": self.wakefulness.get_cognitive_reliability(),
                "value_layer": (lambda s: {
                    "state_count": int(s.get("state_count", 0)),
                    "last_td_error": float(s.get("last_td_error", 0.0)),
                    "last_delta_clipped": float(s.get("last_delta_clipped", 0.0)),
                    "last_error_likelihood": float(s.get("last_error_likelihood", 0.0)),
                    "last_prediction_shock_score": float(s.get("last_prediction_shock_score", 0.0)),
                    "last_confidence_score": float(s.get("last_confidence_score", 0.0)),
                    "last_stability_score": float(s.get("last_stability_score", 0.0)),
                    "online_update_count": int(s.get("online_update_count", 0)),
                    "sleep_update_count": int(s.get("sleep_update_count", 0)),
                })(self.value_layer.snapshot() if hasattr(self.value_layer, "snapshot") else {}),
                "decision_arbitration": dict(self._last_decision_arbitration_output or {}),
                "deliberative_planning": dict(self._last_planning_stats or {}),
                "stability_monitoring": dict(
                    self._last_stability_snapshot
                    or (self.stability_monitor.snapshot() if hasattr(self.stability_monitor, "snapshot") else {})
                ),
                "bg_top3": top_bg,
                # ── FIX: BG.get_action_stats per chain — selection frequency ──
                "bg_action_stats": (lambda: {
                    chain: self.bg_gate.get_action_stats(chain)
                    for chain in sorted(
                        (self.bg_gate.selection_history and
                         {aid for aid, _ in self.bg_gate.selection_history} or set()),
                    )
                } if getattr(self.bg_gate, 'selection_history', None) else {})(),
                # ── FIX: obsessiveness_map — axis looping risk snapshot ────
                "affect_obsessiveness": (lambda: {
                    k: round(v, 3)
                    for k, v in (self.affect_space.obsessiveness_map() or {}).items()
                    if v > 0.3
                } if hasattr(self.affect_space, 'obsessiveness_map') else {})(),
                # ── FIX: CER.describe_brief — regulation state string ─────
                "cer_state": (lambda: self.cer.describe_brief(max_lines=1)
                              if hasattr(self.cer, 'describe_brief') else "")(),
                # ── FIX: hippocampus novelty_sensitivity_scale ────────────
                "hippocampus_novelty_scale": (lambda: round(
                    self.hippocampus.get_novelty_sensitivity_scale(), 3)
                    if hasattr(self.hippocampus, 'get_novelty_sensitivity_scale') else 1.0)(),
                # ── FIX: classify_novelty — current novelty class label ───
                # Converts the last recall_signature novelty_score float to a
                # human-readable class for HUD: familiar/partial_match/novel/high_novelty
                "hippocampus_novelty_class": (lambda: (
                    self.hippocampus.classify_novelty(
                        getattr(self.hippocampus, '_novelty_history', [0.0])[-1]
                        if getattr(self.hippocampus, '_novelty_history', None)
                        else 0.0
                    )
                ) if hasattr(self.hippocampus, 'classify_novelty') else "unknown")(),
                # ── Additional NOWA layers ────────────────────────────
                "temporal_levels": dict(self._last_temporal_levels or {}),
                "affective_persistence": {
                    "trace_count": len(getattr(self.affective_persistence, "get_traces", lambda: [])()),
                    "top_traces": (lambda traces: [
                        {"type": str(t.get("type", "")), "intensity": float(t.get("intensity", 0.0))}
                        for t in traces
                    ])(sorted(
                        (self.affective_persistence.snapshot() or []),
                        key=lambda x: float(x.get("intensity", 0.0)),
                        reverse=True
                    )[:3]) if hasattr(self.affective_persistence, "snapshot") else [],
                },
                "affective_background": dict(self._last_background_snapshot or {}),
                "semantic_emotions": [
                    {
                        "emotion": str(item.get("emotion", "")),
                        "activation": float(item.get("activation", 0.0)),
                        "obsessive": bool(item.get("obsessive", False)),
                    }
                    for item in (self._last_semantic_snapshot or [])
                ][:3],
                "emotional_memory": {
                    "episodes": len(self._last_emotional_memory_snapshot.get("episodes", []) or []),
                    "patterns": len(self._last_emotional_memory_snapshot.get("patterns", []) or []),
                    "traits": list(self._last_emotional_memory_snapshot.get("character_traits", []) or [])[:3],
                },
                "emotional_expectations": {
                    "dominant_forecast": str(self._last_emotional_expectations_snapshot.get("dominant_forecast", "")),
                    "global_outlook": str(self._last_emotional_expectations_snapshot.get("global_outlook", "")),
                },
            },
            "mind": {
                "current_chain": current_chain,
                "current_chain_ru": self._chain_preview(current_chain) if current_chain else "-",
                "chain_progress": current_progress,
                "chain_length": len(chain_actions),
                "next_actions": next_action_ids,
                "next_actions_ru": [self._action_label_ru(aid) for aid in next_action_ids],
                "candidate_chains": candidate_chains,
                "candidate_chains_ru": [self._chain_preview(name) for name in candidate_chains],
                "current_action_ru": self._action_label_ru(current_action_id) if current_action_id else "-",
                "dynamic_chains":        list(DYNAMIC_CHAINS.keys()),
                "dynamic_chains_count":  len(DYNAMIC_CHAINS),
                # ── Training / EIL stats ──────────────────────────────
                "training_feedback_count": self._training_feedback_count,
                "eil_strategy_weights": dict(sorted(
                    self.eil.strategy_weights.items(),
                    key=lambda x: -x[1]
                )[:5]) if self.eil.strategy_weights else {},
                # ── Gap components ─────────────────────────────────────
                "td_delta":        round(self._last_td_result.get("delta_clipped", 0.0), 4),
                "td_tonic_da":     round(self._last_td_result.get("tonic_level",
                                         getattr(self.td_layer, "tonic_level", 0.1)), 3),
                "circadian_phase": round(getattr(self.scheduling, "circadian_phase", 0.0), 3),
                "circadian_is_day": (lambda c: c.get("is_day", 1.0))(
                    self.scheduling.get_circadian_state()
                ),
                "intent_traces":   len(self.intent_memory.traces),
                "memory_entries":  len(self.memory_system.entries),
                "self_model_state": self._self_model_report.get(
                    "operational_description", ""),
                "self_model_limiting": list(
                    self._self_model_report.get("limiting_factors", {}).keys()
                )[:3],
            },
            "memory_summary": (lambda: {
                "hippocampus_size": len(getattr(self.hippocampus, "experiences", []) or []),
                "cortex_patterns": len(getattr(self.cortex, "patterns", []) or []),
                "total_entries": sum(int(getattr(ch, 'selection_count', 0) or 0) for ch in (self.bg_channels or {}).values()),
                "success_rate": (
                    (sum(int(getattr(ch, 'success_count', 0) or 0) for ch in (self.bg_channels or {}).values()) ) /
                    max(1, sum(int(getattr(ch, 'selection_count', 0) or 0) for ch in (self.bg_channels or {}).values()))
                ),
                "average_reward": (
                    sum(float(getattr(ch, 'last_outcome', 0.0) or 0.0) for ch in (self.bg_channels or {}).values()) /
                    max(1, len(self.bg_channels or {}))
                ),
                "top_chains": sorted(
                    [
                        {"chain": name, "weight": float(getattr(ch, 'go_weight', 0.0))}
                        for name, ch in (self.bg_channels or {}).items() if int(getattr(ch, 'selection_count', 0) or 0) > 0
                    ],
                    key=lambda x: x['weight'], reverse=True
                )[:3],
            })(),
        }

    # ------------------------------------------------------------------
    # NOWA helpers: reward / sleep / persistence
    # ------------------------------------------------------------------

    def _calculate_chain_reward(self, chain_name: str) -> float:
        """
        Lightweight reward signal for BG learning & sleep consolidation.
        Uses affect deltas + chain-specific heuristics.
        """
        before = dict(self.chain_start_affect or {})
        after = self.affect.get_state()
        reward = 0.0

        # Global: stress down good, valence up good
        stress_b = float(before.get("stress", 0.0) or 0.0)
        stress_a = float(after.get("stress", 0.0) or 0.0)
        val_b = float(before.get("valence", 0.0) or 0.0)
        val_a = float(after.get("valence", 0.0) or 0.0)
        reward += max(0.0, stress_b - stress_a) * 0.25
        reward += max(0.0, val_a - val_b) * 0.15

        # Drive-aligned: hunger/tiredness/boredom down good
        h_b = float(before.get("hunger", 0.0) or 0.0)
        h_a = float(after.get("hunger", 0.0) or 0.0)
        t_b = float(before.get("tiredness", 0.0) or 0.0)
        t_a = float(after.get("tiredness", 0.0) or 0.0)
        b_b = float(before.get("boredom", 0.0) or 0.0)
        b_a = float(after.get("boredom", 0.0) or 0.0)
        reward += max(0.0, h_b - h_a) * 0.20
        reward += max(0.0, t_b - t_a) * 0.15
        reward += max(0.0, b_b - b_a) * 0.15

        if chain_name == "chronic_stress":
            reward -= 0.4

        return max(-1.0, min(1.0, reward))

    def _affect_label(self) -> str:
        """Affect-and-drive label for hippocampal context tagging."""
        axes = self._axes8()
        stress = float(axes.get("stress", 0.0) or 0.0)
        val    = float(axes.get("valence", 0.0) or 0.0)
        drives = self._last_drive_snapshot or {}

        # Drive-based label takes priority — most specific memory context
        if drives:
            dominant = max(drives.items(), key=lambda x: float(x[1] or 0))
            if float(dominant[1] or 0) > 0.6:
                return f"drive_{dominant[0]}"  # e.g. "drive_energy_need"

        if stress > 0.7:            return "stress_high"
        if val   < -0.2:            return "valence_low"
        if val   > 0.5 and stress < 0.3: return "positive_calm"
        return "neutral"

    def _memory_pressure(self, limit: int = 8) -> Dict[str, float]:
        """
        Task A — Hippocampal recall → BG pressure deltas.

        Reads last `limit` experiences, aggregates reward×encoding_strength
        per chain name, scales to ±0.15 nudge on the pressure_vector.
        Negative reward (e.g. from chronic_stress) → negative delta → BG nogo.
        """
        from collections import defaultdict
        recent = self.hippocampus.recall_recent(limit=limit)
        accum: Dict[str, list] = defaultdict(list)
        for exp in recent:
            if exp.path and exp.path.events:
                name = exp.path.events[0].name
                accum[name].append(exp.reward * exp.encoding_strength)
        result: Dict[str, float] = {}
        for chain, vals in accum.items():
            avg = sum(vals) / len(vals)
            result[chain] = max(-0.15, min(0.15, avg * 0.25))
        return result

    def _recent_failure_rate(self) -> float:
        # Use BG channel history as a simple failure metric.
        # Higher failure_count/selection_count -> higher failure rate.
        total_sel = sum(ch.selection_count for ch in self.bg_channels.values())
        if total_sel <= 0:
            return 0.0
        total_fail = sum(ch.failure_count for ch in self.bg_channels.values())
        return max(0.0, min(1.0, total_fail / float(total_sel)))

    def _run_sleep_consolidation(self) -> None:
        """NOWA: learning happens only during sleep.

        The SleepManager API exposes `deep_sleep()`; it reads
        `neuromodulators` via getattr on the manager, so set the
        attribute and call `deep_sleep()`.
        """
        # Ensure SleepManager sees current neuromodulators
        setattr(self.sleep_manager, "neuromodulators", self.neuromod)
        try:
            # run a couple of consolidation cycles
            self.logger.debug(f"Sleep: starting deep_sleep; hippocampus_size={len(getattr(self.hippocampus,'experiences',[]) or [])}")
            _ds_stats = self.sleep_manager.deep_sleep(cycles=2)
            self.logger.debug(
                f"Sleep: deep_sleep finished: "
                f"consolidated={_ds_stats.get('total_episodes_consolidated',0)} "
                f"forgotten={_ds_stats.get('total_forgotten',0)} "
                f"bg_delta={_ds_stats.get('total_bg_delta_sleep',0.0):.4f} "
                f"consolidation_ratio={_ds_stats.get('consolidation_ratio',0.0):.3f}"
            )
            # ── FIX: BG.reset_history after sleep ─────────────────────
            # sleep_cycle() does TD-replay which updates BG weights — the
            # pre-sleep selection_history is now stale. Reset so get_action_stats
            # and thalamic novelty calculations start fresh after each sleep.
            try:
                self.bg_gate.reset_history()
                self.logger.debug("[SLEEP] BG.reset_history() done")
            except Exception:
                pass

            # ── FIX: get_temporal_chain_generation → chain depth in sleep ─
            # NE increases chain complexity; HT stabilizes. Pass the weight
            # to SleepManager's chain_memory max_len parameter so high-NE
            # sleep produces longer associative chains in cortex.
            try:
                _tcg = self.neuromod.get_temporal_chain_generation()  # [0, 1]
                # Map to max_len: [2, 7] matching _form_chains_from_recent defaults
                _chain_max_len = max(2, min(7, int(2 + _tcg * 5)))
                if hasattr(self.sleep_manager, '_form_chains_from_recent'):
                    self.sleep_manager._form_chains_from_recent(
                        max_recent=50, min_len=2, max_len=_chain_max_len
                    )
                    self.logger.debug(
                        f"[SLEEP] temporal_chain_generation={_tcg:.3f} "
                        f"→ chain_max_len={_chain_max_len}"
                    )
            except Exception:
                pass

            # ── DYNAMIC CHAIN PROMOTION ────────────────────────────────
            # After _form_chains_from_recent() builds TemporalChain objects,
            # scan chain_memory for sequences that meet promotion thresholds
            # and register them as executable DYNAMIC_CHAINS.
            # Threshold: stability≥0.55, usage≥3, |net_affect|≥0.04.
            # Steps are built as (action_id, 1.0) tuples — all steps mandatory
            # since the sequence was observed reliably.
            try:
                _cm = getattr(self.sleep_manager, 'chain_memory', None)
                if _cm is not None:
                    _promoted = 0
                    for sig, tc in list(_cm.chains.items()):
                        if (tc.stability   >= DYNAMIC_CHAIN_STABILITY_THRESHOLD and
                                tc.usage_count >= DYNAMIC_CHAIN_USAGE_THRESHOLD and
                                abs(tc.net_affect) >= DYNAMIC_CHAIN_AFFECT_THRESHOLD):
                            # Build a sanitised chain name from the signature
                            _safe = "_".join(
                                str(s).replace("action:", "").replace(":", "_")[:12]
                                for s in tc.signature
                            )
                            _dname = f"dyn_{_safe}"[:40]
                            # Steps: filter to known ACTION_LIBRARY action_ids
                            _steps = []
                            for token in tc.signature:
                                # _form_chains_from_recent stores raw names;
                                # add_or_update via test may store "action:X" — handle both
                                _aid = str(token).removeprefix("action:")
                                if _aid in ACTION_LIBRARY:
                                    _steps.append((_aid, 1.0))
                            if len(_steps) >= 2:
                                registered = register_dynamic_chain(_dname, _steps)
                                if registered:
                                    _promoted += 1
                                    self.logger.info(
                                        f"[DYN] promoted chain '{_dname}' "
                                        f"steps={len(_steps)} "
                                        f"stability={tc.stability:.3f} "
                                        f"net_affect={tc.net_affect:.4f}"
                                    )
                    if _promoted:
                        self.logger.info(f"[DYN] total promoted this sleep: {_promoted} "
                                         f"(total dynamic: {len(DYNAMIC_CHAINS)})")
            except Exception as _e:
                self.logger.debug(f"[DYN] promotion error: {_e}")
        except Exception:
            # Fallback for older managers that might provide consolidate()
            if hasattr(self.sleep_manager, "consolidate"):
                try:
                    self.logger.debug("Sleep: using fallback consolidate()")
                    self.sleep_manager.consolidate(neuromodulators=self.neuromod, max_patterns=20)
                except Exception:
                    self.logger.exception("Sleep consolidation failed")

        # ── IntentMemory: habit-affect modulation during sleep ────────
        # Applies affect-based multipliers then decays weak traces.
        try:
            _affect_proxy = self._sm_agent.affect_state
            _hab_mod = self.intent_memory.get_habit_affect_modulation(_affect_proxy)
            from learning_guard import learning_allowed

            with learning_allowed():
                self.intent_memory.apply_habit_affect_modulation(_hab_mod)
                self.intent_memory.degrade_unused(decay_factor=0.85)
            self.logger.debug(
                f"[INTENT] sleep: modulated {len(_hab_mod)} traces, "
                f"remaining {len(self.intent_memory.traces)}"
            )
        except Exception as _e:
            self.logger.debug(f"[INTENT] sleep modulation error: {_e}")

        # ── MemorySystem: sleep consolidation ─────────────────────────
        try:
            self.memory_system.consolidate_memory(current_time=self.total_sim_time)
            self.logger.debug("[MEM] memory_system.consolidate_memory done")
        except Exception as _e:
            self.logger.debug(f"[MEM] consolidation error: {_e}")

        # ── Task A: Cortex pattern consolidation ─────────────────────
        # FIX: use get_candidates_for_sleep() as the primary source —
        # it filters by reinforcement_count≥2, activation>0.5, and
        # consolidation_probability, giving priority to well-rehearsed
        # traces over just "most recent" ones.
        # Fall back to recall_recent if no candidates qualify.
        try:
            _sleep_candidates = self.hippocampus.get_candidates_for_sleep(min_reinforcement=2)
        except Exception:
            _sleep_candidates = []
        if _sleep_candidates:
            recent_exps = _sleep_candidates
            self.logger.debug(
                f"[SLEEP] get_candidates_for_sleep: {len(recent_exps)} priority candidates"
            )
        else:
            recent_exps = self.hippocampus.recall_recent(limit=10)
            self.logger.debug(
                f"[SLEEP] no priority candidates, falling back to recall_recent: {len(recent_exps)}"
            )
        from collections import Counter
        chain_counts: Counter = Counter()
        for exp in recent_exps:
            if exp.path and exp.path.events and exp.reward > 0.1:
                name = exp.path.events[0].name
                chain_counts[name] += 1
        affect_label = self._affect_label()
        for chain_name_c, count in chain_counts.most_common(3):
            self.cortex.store_pattern(
                (chain_name_c, affect_label),
                source_experiences=count,
            )

        # Go/NoGo and habit strength are written once, inside deep_sleep.
        # A second apply_sleep_learning would clone those channels and step
        # them again. Owner ratings still need the sleep guard.
        from learning_guard import learning_allowed

        with learning_allowed():
            self._flush_owner_feedback()

        self.logger.info(
            f"[NOWA] Sleep: "
            f"DA={self.neuromod.dopamine:.2f} 5HT={self.neuromod.serotonin:.2f} "
            f"CORT={self.neuromod.cortisol:.2f}  "
            f"cortex_patterns={len(self.cortex.patterns)}"
        )

    def save_nowa_state(self) -> None:
        import json

        saves_dir = self.saves_dir
        saves_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "neuromodulators": self.neuromod.to_dict() if hasattr(self.neuromod, "to_dict") else {},
            "drives": self.drives.snapshot(),
            "wakefulness": self.wakefulness.get_statistics(),
            "bg_channels": {
                name: {
                    "go_weight": float(getattr(ch, "go_weight", 0.0)),
                    "nogo_weight": float(getattr(ch, "nogo_weight", 0.0)),
                    "habit_strength": float(getattr(ch, "habit_strength", 0.0)),
                    "selection_count": int(getattr(ch, "selection_count", 0)),
                    "success_count": int(getattr(ch, "success_count", 0)),
                    "failure_count": int(getattr(ch, "failure_count", 0)),
                    "last_outcome": float(getattr(ch, "last_outcome", 0.0) or 0.0),
                }
                for name, ch in self.bg_channels.items()
            },
            "value_layer": (
                self.value_layer.to_dict()
                if hasattr(self.value_layer, "to_dict")
                else {}
            ),
            "stability_monitor": (
                self.stability_monitor.to_dict()
                if hasattr(self.stability_monitor, "to_dict")
                else {}
            ),
            "decision_arbitrator": {
                "enabled": bool(getattr(self.decision_arbitrator, "enabled", True)),
                "w_td": float(getattr(self.decision_arbitrator, "w_td", 0.40)),
                "w_error": float(getattr(self.decision_arbitrator, "w_error", 0.35)),
                "w_surprise": float(getattr(self.decision_arbitrator, "w_surprise", 0.25)),
                "base_threshold": float(getattr(self.decision_arbitrator, "base_threshold", 0.55)),
                "stress_gain": float(getattr(self.decision_arbitrator, "stress_gain", 0.25)),
                "base_temp": float(getattr(self.decision_arbitrator, "base_temp", 0.6)),
                "uncertainty_gain": float(getattr(self.decision_arbitrator, "uncertainty_gain", 0.8)),
                "temp_min": float(getattr(self.decision_arbitrator, "temp_min", 0.4)),
                "temp_max": float(getattr(self.decision_arbitrator, "temp_max", 1.5)),
                "reliability_threshold": float(getattr(self.decision_arbitrator, "reliability_threshold", 0.35)),
                "uncertainty_ema_beta": float(getattr(self.decision_arbitrator, "uncertainty_ema_beta", 0.2)),
                "hysteresis_margin": float(getattr(self.decision_arbitrator, "hysteresis_margin", 0.05)),
                "deliberative_release_multiplier": float(
                    getattr(self.decision_arbitrator, "deliberative_release_multiplier", 2.0)
                ),
                "_uncertainty_ema": float(getattr(self.decision_arbitrator, "_uncertainty_ema", 0.0)),
                "_last_decision_mode": str(getattr(self.decision_arbitrator, "_last_decision_mode", "HABITUAL")),
            },
            "chain_value_stats": dict(self._chain_value_stats or {}),
            "selector_action_metadata": dict(getattr(self.chain_selector, "action_metadata", {}) or {}),
            "planning": {
                "enabled": bool(self.deliberative_planning_enabled),
                "gain": float(self.chain_planning_gain),
                "candidate_limit": int(self.chain_planning_candidate_limit),
                "last": dict(self._last_planning_stats or {}),
            },
            "cortex_patterns": len(getattr(self.cortex, "patterns", []) or []),
            "hippocampus_size": len(getattr(self.hippocampus, "experiences", []) or []),
            "total_sim_time": self.total_sim_time,
            "tick_count": self.tick_count,
            "plasticity": (
                self.plasticity.to_dict()
                if hasattr(getattr(self, "plasticity", None), "to_dict")
                else {}
            ),
            "labile": (
                self.labile.to_dict()
                if hasattr(getattr(self, "labile", None), "to_dict")
                else {}
            ),
            "host_clock_s": float(getattr(getattr(self, "nowa", None), "_host_clock_s", 0.0) or 0.0),
            "pending_owner_feedback": [
                {
                    "rating": int(item.get("rating", 0)),
                    "reward": float(item.get("reward", 0.0)),
                    "chain": str(item.get("chain", "") or ""),
                }
                for item in list(getattr(self, "_pending_owner_feedback", []) or [])
                if isinstance(item, dict)
            ],
        }
        with open(saves_dir / "nowa_state.json", "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        self.logger.info("[NOWA] State saved")

    def load_nowa_state(self) -> bool:
        import json

        path = self.saves_dir / "nowa_state.json"
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            if "neuromodulators" in state and hasattr(NeuromodulatorState, "from_dict"):
                self.neuromod = NeuromodulatorState.from_dict(state["neuromodulators"])
            drives_state = state.get("drives")
            if isinstance(drives_state, dict):
                for name, value in drives_state.items():
                    try:
                        if hasattr(self.drives, "set_drive"):
                            self.drives.set_drive(str(name), float(value))
                        elif hasattr(self.drives, "drives") and str(name) in self.drives.drives:
                            self.drives.drives[str(name)] = max(0.0, min(1.0, float(value)))
                    except Exception:
                        continue
                self._last_drive_snapshot = self.drives.snapshot()
            wake_state = state.get("wakefulness")
            if isinstance(wake_state, dict):
                try:
                    if "current" in wake_state:
                        self.wakefulness.wakefulness = float(wake_state["current"])
                    if "accumulated_waking_hours" in wake_state:
                        self.wakefulness.accumulated_waking_time = max(
                            0.0, float(wake_state["accumulated_waking_hours"])
                        ) * 3600.0
                    if "total_sleep_hours" in wake_state:
                        self.wakefulness.total_sleep_time = max(
                            0.0, float(wake_state["total_sleep_hours"])
                        ) * 3600.0
                    if "circadian_time_hours" in wake_state:
                        self.wakefulness.circadian_time_hours = float(wake_state["circadian_time_hours"])
                except Exception:
                    pass
            elif wake_state is not None:
                try:
                    self.wakefulness.wakefulness = float(wake_state)
                except Exception:
                    pass
            if "total_sim_time" in state:
                try:
                    self.total_sim_time = float(state.get("total_sim_time", self.total_sim_time))
                except Exception:
                    pass
            if "tick_count" in state:
                try:
                    self.tick_count = int(state.get("tick_count", self.tick_count))
                except Exception:
                    pass
            from learning_guard import initializing

            with initializing():
                for name, vals in (state.get("bg_channels") or {}).items():
                    if name in self.bg_channels:
                        ch = self.bg_channels[name]
                        ch.go_weight = float(vals.get("go_weight", 0.5))
                        ch.nogo_weight = float(vals.get("nogo_weight", 0.5))
                        ch.habit_strength = float(vals.get("habit_strength", 0.0))
                        ch.selection_count = int(vals.get("selection_count", 0))
                        ch.success_count = int(vals.get("success_count", 0))
                        ch.failure_count = int(vals.get("failure_count", getattr(ch, "failure_count", 0)))
                        if "last_outcome" in vals:
                            try:
                                ch.last_outcome = float(vals.get("last_outcome", 0.0))
                            except Exception:
                                pass
            vl_data = state.get("value_layer")
            if isinstance(vl_data, dict) and hasattr(ValueLayer, "from_dict"):
                try:
                    self.value_layer = ValueLayer.from_dict(vl_data)
                    setattr(self.sleep_manager, "value_layer", self.value_layer)
                except Exception:
                    pass
            sm_data = state.get("stability_monitor")
            if isinstance(sm_data, dict) and hasattr(StabilityMonitoringLayer, "from_dict"):
                try:
                    self.stability_monitor = StabilityMonitoringLayer.from_dict(sm_data)
                    setattr(self.sleep_manager, "stability_monitor", self.stability_monitor)
                    self._last_stability_snapshot = self.stability_monitor.snapshot()
                except Exception:
                    pass
            da_data = state.get("decision_arbitrator")
            if isinstance(da_data, dict):
                for attr in (
                    "enabled",
                    "w_td",
                    "w_error",
                    "w_surprise",
                    "base_threshold",
                    "stress_gain",
                    "base_temp",
                    "uncertainty_gain",
                    "temp_min",
                    "temp_max",
                    "reliability_threshold",
                    "uncertainty_ema_beta",
                    "hysteresis_margin",
                    "deliberative_release_multiplier",
                ):
                    if attr in da_data:
                        try:
                            setattr(self.decision_arbitrator, attr, da_data[attr])
                        except Exception:
                            pass
                if "_uncertainty_ema" in da_data:
                    try:
                        self.decision_arbitrator._uncertainty_ema = float(da_data.get("_uncertainty_ema", 0.0))
                        self.decision_arbitrator._ema_initialized = True
                    except Exception:
                        pass
                if "_last_decision_mode" in da_data:
                    try:
                        self.decision_arbitrator._last_decision_mode = str(da_data.get("_last_decision_mode", "HABITUAL"))
                    except Exception:
                        pass
            cv_stats = state.get("chain_value_stats")
            if isinstance(cv_stats, dict):
                try:
                    self._chain_value_stats = {
                        str(k): {str(kk): float(vv) if isinstance(vv, (int, float)) else vv for kk, vv in dict(v).items()}
                        for k, v in cv_stats.items()
                        if isinstance(v, dict)
                    }
                except Exception:
                    pass
            selector_meta = state.get("selector_action_metadata")
            if isinstance(selector_meta, dict):
                try:
                    self.chain_selector.action_metadata = {
                        str(k): dict(v) for k, v in selector_meta.items() if isinstance(v, dict)
                    }
                    for action_id in self.chain_selector.action_metadata.keys():
                        self.chain_selector.register_action(action_id)
                except Exception:
                    pass
            planning_data = state.get("planning")
            if isinstance(planning_data, dict):
                try:
                    self.deliberative_planning_enabled = bool(planning_data.get("enabled", self.deliberative_planning_enabled))
                    self.chain_planning_gain = float(planning_data.get("gain", self.chain_planning_gain))
                    self.chain_planning_candidate_limit = int(planning_data.get("candidate_limit", self.chain_planning_candidate_limit))
                    self._last_planning_stats = dict(planning_data.get("last", self._last_planning_stats) or {})
                except Exception:
                    pass
            from labile_layer import LabileLayer, PlasticityConfig

            plasticity_data = state.get("plasticity")
            if isinstance(plasticity_data, dict) and plasticity_data:
                try:
                    self.plasticity = PlasticityConfig.from_dict(plasticity_data)
                except Exception:
                    pass
            labile_data = state.get("labile")
            if isinstance(labile_data, dict) and labile_data:
                try:
                    self.labile = LabileLayer.from_dict(labile_data)
                except Exception:
                    pass
            if "host_clock_s" in state:
                try:
                    self._host_clock_s = float(state.get("host_clock_s", 0.0))
                except (TypeError, ValueError):
                    pass
            pending = state.get("pending_owner_feedback")
            if isinstance(pending, list):
                restored_pending = []
                for item in pending:
                    if not isinstance(item, dict):
                        continue
                    try:
                        restored_pending.append(
                            {
                                "rating": int(item.get("rating", 0)),
                                "reward": float(item.get("reward", 0.0)),
                                "chain": str(item.get("chain", "") or ""),
                            }
                        )
                    except (TypeError, ValueError):
                        continue
                self._pending_owner_feedback = restored_pending
            self._rewire_two_tier_host()
            self.logger.info("[NOWA] State loaded")
            return True
        except Exception as e:
            self.logger.error(f"[NOWA] Load failed: {e}")
            return False


# ============================================================================
# ENTRY POINT
# ============================================================================

def _consume_lang_flag(argv: list[str]) -> tuple[str | None, list[str]]:
    """Pull ``--lang en|ru`` out of argv before the agent starts."""

    lang = None
    kept: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--lang" and index + 1 < len(argv):
            lang = argv[index + 1]
            index += 2
            continue
        if item.startswith("--lang="):
            lang = item.split("=", 1)[1]
            index += 1
            continue
        kept.append(item)
        index += 1
    return lang, kept


if __name__ == "__main__":
    import sys

    from tama_i18n import set_language

    chosen_lang, remaining = _consume_lang_flag(sys.argv[1:])
    sys.argv = [sys.argv[0], *remaining]
    if chosen_lang in ("en", "ru"):
        set_language(chosen_lang)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    demo_dir = RESOURCE_DIR  # Resource root (onefile extract or dev dir)

    agent = ChinchillaAgent(
        demo_dir=str(demo_dir),
        use_pygame=True,
        use_gui=False,
    )

    try:
        agent.run(max_duration=None)
    except Exception as e:
        logging.error(f"Fatal: {e}")
        import traceback; traceback.print_exc()
