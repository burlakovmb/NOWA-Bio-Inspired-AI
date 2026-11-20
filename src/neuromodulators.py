import math
import time
from typing import Dict, Optional, Tuple


class NeuromodulatorField:
    """
    Coupled interaction layer for DA/5HT/NE/ACh.

    Dynamics:
        dM/dt = base_signal + W * (M - baseline) - decay * (M - baseline)

    Baseline-centered dynamics keep resting state stable while adding
    pairwise interactions when levels deviate from baseline.
    """

    KEYS = ("dopamine", "serotonin", "norepinephrine", "acetylcholine")
    INTERACTION_MATRIX = (
        (0.0, -0.2, 0.1, -0.3),   # DA row
        (0.1, 0.0, -0.1, 0.0),    # 5HT row
        (0.2, -0.1, 0.0, 0.2),    # NE row
        (-0.3, 0.0, 0.2, 0.0),    # ACh row
    )

    def __init__(
        self,
        dopamine: float,
        serotonin: float,
        norepinephrine: float,
        acetylcholine: float,
        baselines: Optional[Dict[str, float]] = None,
        decay: float = 0.2,
        dt: float = 1.0,
    ):
        self.decay = max(0.0, float(decay))
        self.dt = max(0.0, float(dt))
        baselines = dict(baselines or {})
        self.baselines = {
            "dopamine": self._clamp(baselines.get("dopamine", 0.1)),
            "serotonin": self._clamp(baselines.get("serotonin", 0.1)),
            "norepinephrine": self._clamp(baselines.get("norepinephrine", 0.1)),
            "acetylcholine": self._clamp(baselines.get("acetylcholine", 0.1)),
        }
        self.levels = {
            "dopamine": self._clamp(dopamine),
            "serotonin": self._clamp(serotonin),
            "norepinephrine": self._clamp(norepinephrine),
            "acetylcholine": self._clamp(acetylcholine),
        }

    @staticmethod
    def _clamp(v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    def set_baselines(self, baselines: Dict[str, float]):
        for key in self.KEYS:
            if key in baselines:
                self.baselines[key] = self._clamp(baselines[key])

    def set_levels(
        self,
        dopamine: float,
        serotonin: float,
        norepinephrine: float,
        acetylcholine: float,
    ):
        self.levels["dopamine"] = self._clamp(dopamine)
        self.levels["serotonin"] = self._clamp(serotonin)
        self.levels["norepinephrine"] = self._clamp(norepinephrine)
        self.levels["acetylcholine"] = self._clamp(acetylcholine)

    def snapshot(self) -> Dict[str, float]:
        return dict(self.levels)

    def _minimum_stable_decay(self) -> float:
        """Decay that keeps one Euler step contractive for this matrix.

        Gershgorin: the off-diagonal mass of a row is a bound on how far an
        eigenvalue can sit from the diagonal. Decay has to clear that mass
        or a positive feedback mode walks the levels off baseline.
        """
        dt = max(float(self.dt), 1e-6)
        max_off = 0.0
        matrix = getattr(self, "INTERACTION_MATRIX", ()) or ()
        for row in matrix:
            try:
                off = sum(abs(float(weight)) for weight in row)
            except (TypeError, ValueError):
                continue
            if off > max_off:
                max_off = off
        return max_off + (0.25 / dt)

    def update(
        self,
        signals: Optional[Dict[str, float]] = None,
        dt: Optional[float] = None,
    ) -> Dict[str, float]:
        signal_values = dict(signals or {})
        dt_v = self.dt if dt is None else max(0.0, float(dt))
        if dt_v <= 0.0:
            return self.snapshot()
        needed = self._minimum_stable_decay()
        if self.decay < needed:
            self.decay = needed

        m = [self.levels[key] for key in self.KEYS]
        b = [self.baselines[key] for key in self.KEYS]
        centered = [m_v - b_v for m_v, b_v in zip(m, b)]
        s = [float(signal_values.get(key, 0.0)) for key in self.KEYS]

        interaction = []
        for row in self.INTERACTION_MATRIX:
            value = 0.0
            for idx, weight in enumerate(row):
                value += float(weight) * centered[idx]
            interaction.append(value)

        for idx, key in enumerate(self.KEYS):
            d_level = s[idx] + interaction[idx] - (self.decay * centered[idx])
            self.levels[key] = self._clamp(m[idx] + (dt_v * d_level))

        return self.snapshot()

    def reset(self):
        self.levels = dict(self.baselines)

    def to_dict(self) -> Dict[str, object]:
        return {
            "levels": self.snapshot(),
            "baselines": dict(self.baselines),
            "decay": float(self.decay),
            "dt": float(self.dt),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, object]]) -> "NeuromodulatorField":
        raw = dict(data or {})
        levels = dict(raw.get("levels") or {})
        baselines = dict(raw.get("baselines") or {})
        return cls(
            dopamine=float(levels.get("dopamine", baselines.get("dopamine", 0.1))),
            serotonin=float(levels.get("serotonin", baselines.get("serotonin", 0.1))),
            norepinephrine=float(levels.get("norepinephrine", baselines.get("norepinephrine", 0.1))),
            acetylcholine=float(levels.get("acetylcholine", baselines.get("acetylcholine", 0.1))),
            baselines={
                "dopamine": float(baselines.get("dopamine", 0.1)),
                "serotonin": float(baselines.get("serotonin", 0.1)),
                "norepinephrine": float(baselines.get("norepinephrine", 0.1)),
                "acetylcholine": float(baselines.get("acetylcholine", 0.1)),
            },
            decay=float(raw.get("decay", 0.2)),
            dt=float(raw.get("dt", 1.0)),
        )


class NeuromodulatorState:
    """
    Neuromodulator state - Phase 2 implementation.

    Biological motivation: Global regulators of:
    - learning rate
    - temporal horizon
    - stability/plasticity
    - reward, uncertainty, and conflict response

    Key principle: Neuromodulators modulate, they do NOT make decisions.

    Values normalized to [0.0, 1.0] range.
    Baseline: ~0.1 for each
    Time decay: half-life ~60-120 seconds
    """

    # Baseline (default) levels
    BASELINE_DA = 0.1
    BASELINE_HT = 0.1
    BASELINE_NE = 0.1
    BASELINE_CORT = 0.05
    BASELINE_ACH = 0.1

    # Time decay parameters
    DECAY_HALF_LIFE = 90.0  # seconds

    # Interaction layer parameters
    INTERACTION_DECAY = 0.85
    IMPULSE_LIMIT = 0.25
    INTERACTION_DT = 1.0

    # Update coefficients (from specification)
    DA_REWARD_POSITIVE = 0.25
    DA_REWARD_NEGATIVE = -0.10
    HT_REWARD = 0.05
    HT_STABLE_REPETITION = 0.01
    NE_NOVELTY = 0.30
    NE_CONFLICT = 0.15
    CORT_REWARD_NEGATIVE = 0.20
    CORT_CONFLICT = 0.25
    ACC_K_NE = 0.5
    ACC_K_CORT = 0.7
    ACC_GAIN_MIN = 0.5
    ACC_GAIN_MAX = 2.0
    ACC_K_HT_INHIBITION = 0.35
    ACC_INHIBITION_MIN = 0.6
    ACC_SOFT_NORM = 0.05
    ACC_COGNITIVE_WEIGHT = 0.6
    ACC_AFFECTIVE_WEIGHT = 0.4
    ACC_CONFLICT_TAU = 1.0
    ACC_NE_HOMEOSTATIC_DECAY = 0.25
    ACC_CORT_HOMEOSTATIC_DECAY = 0.4
    ACH_DECAY_RATE = 0.02
    ACH_NOVELTY_GAIN = 0.25
    ACH_REPETITION_PENALTY = 0.05
    ACH_NOVELTY_FILTER = 0.7
    ACH_ALPHA_GAIN = 0.4
    ACH_REPLAY_GAIN = 0.5

    def __init__(
        self,
        dopamine: float = None,
        norepinephrine: float = None,
        serotonin: float = None,
        cortisol: float = None,
        acetylcholine: float = None,
    ):
        """Initialize neuromodulator state with optional values."""
        self.dopamine = float(dopamine) if dopamine is not None else self.BASELINE_DA
        self.norepinephrine = float(norepinephrine) if norepinephrine is not None else self.BASELINE_NE
        self.serotonin = float(serotonin) if serotonin is not None else self.BASELINE_HT
        self.cortisol = float(cortisol) if cortisol is not None else self.BASELINE_CORT
        self.acetylcholine = float(acetylcholine) if acetylcholine is not None else self.BASELINE_ACH
        # Phase 6.1: acetylcholine regulates selectivity/plasticity, not reward.
        self.ach_baseline = float(self.BASELINE_ACH)
        self.ach_decay_rate = float(self.ACH_DECAY_RATE)
        self.ach_novelty_gain = float(self.ACH_NOVELTY_GAIN)
        self.ach_repetition_penalty = float(self.ACH_REPETITION_PENALTY)
        self.ach_novelty_filter = float(self.ACH_NOVELTY_FILTER)
        self.ach_novelty_trace = 0.0
        self.ach_alpha_gain = float(self.ACH_ALPHA_GAIN)
        self.ach_replay_gain = float(self.ACH_REPLAY_GAIN)
        self.ach_running_mean = float(self.ach_baseline)
        self.ach_mean_rate = 0.05
        self.interaction_field: Optional[NeuromodulatorField] = None
        self.timestamp = time.time()

        # Clamp to valid range and initialize interaction layer.
        self._clamp_all()
        # ACC conflict traces (temporal smoothing state).
        self._acc_combined_conflict_trace = 0.0
        self._acc_cognitive_conflict_trace = 0.0
        self._acc_affective_conflict_trace = 0.0

    def _clamp(self, v: float) -> float:
        """Clamp value to [0.0, 1.0]."""
        return max(0.0, min(1.0, float(v)))

    def _clamp_range(self, v: float, lo: float, hi: float) -> float:
        """Clamp value to an arbitrary numeric range."""
        low = float(min(lo, hi))
        high = float(max(lo, hi))
        return max(low, min(high, float(v)))

    def _compute_conflict_alpha(self, dt: float = 1.0) -> float:
        """Convert dt to low-pass alpha for ACC conflict dynamics."""
        dt_v = max(0.0, float(dt))
        if dt_v <= 0.0:
            return 0.0
        tau = max(1e-6, float(self.ACC_CONFLICT_TAU))
        return self._clamp(1.0 - math.exp(-dt_v / tau))

    def _bounded_delta(self, v: float) -> float:
        """Bound signed deltas to [-1, 1] while preserving sign and monotonicity."""
        value = float(v)
        return value / (1.0 + abs(value))

    def _compute_effective_conflict_from_state(
        self,
        conflict: float,
        norepinephrine: float,
        cortisol: float,
        serotonin: float,
    ) -> float:
        """Compute ACC-modulated conflict for an explicit neuromodulator snapshot."""
        conflict_v = self._clamp(conflict)
        norepinephrine_v = self._clamp(norepinephrine)
        cortisol_v = self._clamp(cortisol)
        serotonin_v = self._clamp(serotonin)

        arousal_delta = self._bounded_delta(norepinephrine_v - self.BASELINE_NE)
        arousal_gain = 1.0 + (self.ACC_K_NE * arousal_delta)
        arousal_gain = self._clamp_range(arousal_gain, self.ACC_GAIN_MIN, self.ACC_GAIN_MAX)

        stress_drive = max(0.0, self._bounded_delta(cortisol_v - self.BASELINE_CORT))
        stress_gain = 1.0 + (self.ACC_K_CORT * stress_drive)
        stress_gain = self._clamp_range(stress_gain, self.ACC_GAIN_MIN, self.ACC_GAIN_MAX)

        inhibition_gain = 1.0 - (self.ACC_K_HT_INHIBITION * max(0.0, serotonin_v - self.BASELINE_HT))
        inhibition_gain = self._clamp_range(inhibition_gain, self.ACC_INHIBITION_MIN, 1.0)

        modulated_conflict = conflict_v * arousal_gain * stress_gain * inhibition_gain
        # Soft normalization keeps gradient at high gain and avoids hard saturation spikes.
        effective_conflict = modulated_conflict / (1.0 + (self.ACC_SOFT_NORM * modulated_conflict))
        return self._clamp(effective_conflict)

    def _compute_effective_conflict(self, conflict: float) -> float:
        """Compute ACC-modulated conflict from the current neuromodulator state."""
        return self._compute_effective_conflict_from_state(
            conflict=conflict,
            norepinephrine=self.norepinephrine,
            cortisol=self.cortisol,
            serotonin=self.serotonin,
        )

    def _split_conflict_components(
        self,
        conflict: float,
        cognitive_conflict: Optional[float] = None,
        affective_conflict: Optional[float] = None,
    ) -> Tuple[float, float, float]:
        """Resolve scalar and optional conflict components into a consistent tuple."""
        scalar_conflict = self._clamp(conflict)
        if cognitive_conflict is None and affective_conflict is None:
            cognitive_v = scalar_conflict
            affective_v = scalar_conflict
        elif cognitive_conflict is None:
            affective_v = self._clamp(affective_conflict)
            cognitive_v = affective_v
        elif affective_conflict is None:
            cognitive_v = self._clamp(cognitive_conflict)
            affective_v = cognitive_v
        else:
            cognitive_v = self._clamp(cognitive_conflict)
            affective_v = self._clamp(affective_conflict)

        combined_v = self._clamp(
            (self.ACC_COGNITIVE_WEIGHT * cognitive_v)
            + (self.ACC_AFFECTIVE_WEIGHT * affective_v)
        )
        return combined_v, cognitive_v, affective_v

    def _interaction_baselines(self) -> Dict[str, float]:
        return {
            "dopamine": self._clamp(self.BASELINE_DA),
            "serotonin": self._clamp(self.BASELINE_HT),
            "norepinephrine": self._clamp(self.BASELINE_NE),
            "acetylcholine": self._clamp(self.ach_baseline),
        }

    def _sync_field_from_state(self):
        baselines = self._interaction_baselines()
        if self.interaction_field is None:
            self.interaction_field = NeuromodulatorField(
                dopamine=self.dopamine,
                serotonin=self.serotonin,
                norepinephrine=self.norepinephrine,
                acetylcholine=self.acetylcholine,
                baselines=baselines,
                decay=self.INTERACTION_DECAY,
                dt=self.INTERACTION_DT,
            )
            return
        self.interaction_field.set_baselines(baselines)
        self.interaction_field.set_levels(
            dopamine=self.dopamine,
            serotonin=self.serotonin,
            norepinephrine=self.norepinephrine,
            acetylcholine=self.acetylcholine,
        )

    def _sync_state_from_field(self):
        if self.interaction_field is None:
            return
        levels = self.interaction_field.snapshot()
        self.dopamine = self._clamp(levels.get("dopamine", self.dopamine))
        self.serotonin = self._clamp(levels.get("serotonin", self.serotonin))
        self.norepinephrine = self._clamp(levels.get("norepinephrine", self.norepinephrine))
        self.acetylcholine = self._clamp(levels.get("acetylcholine", self.acetylcholine))

    def _apply_interaction_dynamics(self, base_signal: Dict[str, float], dt: float = 1.0):
        self._sync_field_from_state()
        dt_v = max(0.0, float(dt))
        if dt_v <= 0.0:
            dt_v = self.INTERACTION_DT
        self.interaction_field.update(signals=base_signal, dt=dt_v)
        self._sync_state_from_field()

    def _compute_acetylcholine_delta(
        self,
        novelty: float = 0.0,
        stable_repetition: bool = False,
    ) -> Tuple[float, float]:
        novelty_v = self._clamp(novelty)
        novelty_filter = self._clamp(self.ach_novelty_filter)
        next_trace = (
            (1.0 - novelty_filter) * float(self.ach_novelty_trace)
        ) + (novelty_filter * novelty_v)
        effective_novelty = self._clamp(next_trace)

        delta = 0.0
        if effective_novelty > 0.5:
            delta += self.ach_novelty_gain * effective_novelty

        if stable_repetition:
            # Pull excess ACh down, but do not drive the fixed point under baseline.
            excess = max(0.0, float(self.acetylcholine) - float(self.ach_baseline))
            delta -= min(float(self.ach_repetition_penalty), excess)

        # Decay toward baseline.
        ach_after_signal = self.acetylcholine + delta
        delta += self.ach_decay_rate * (self.ach_baseline - ach_after_signal)

        final_ach = self._clamp(self.acetylcholine + delta)
        return (final_ach - self.acetylcholine), next_trace

    def _clamp_all(self):
        """Clamp all neuromodulator values to valid range."""
        self.dopamine = self._clamp(self.dopamine)
        self.norepinephrine = self._clamp(self.norepinephrine)
        self.serotonin = self._clamp(self.serotonin)
        self.cortisol = self._clamp(self.cortisol)
        self.acetylcholine = self._clamp(self.acetylcholine)
        self._sync_field_from_state()

    def decay_over_time(self, elapsed: float):
        """
        Apply exponential decay towards baseline values.

        Formula: X = X - (X - baseline) * decay_rate
        With exponential half-life model.

        Args:
            elapsed: Time in seconds since last update
        """
        if elapsed <= 0:
            return

        # Calculate decay factor using exponential decay model
        # decay_factor = 0.5^(elapsed / half_life)
        decay_factor = math.pow(0.5, elapsed / self.DECAY_HALF_LIFE)

        # Apply: X = X - (X - baseline) * (1 - decay_factor)
        # Which is equivalent to: X = baseline + (X - baseline) * decay_factor
        self.dopamine = self.BASELINE_DA + (self.dopamine - self.BASELINE_DA) * decay_factor
        self.norepinephrine = self.BASELINE_NE + (self.norepinephrine - self.BASELINE_NE) * decay_factor
        self.serotonin = self.BASELINE_HT + (self.serotonin - self.BASELINE_HT) * decay_factor
        self.cortisol = self.BASELINE_CORT + (self.cortisol - self.BASELINE_CORT) * decay_factor
        self.acetylcholine = self.ach_baseline + (self.acetylcholine - self.ach_baseline) * decay_factor

        self._clamp_all()
        self._track_ach_running_mean()
        self.timestamp = time.time()

    def _track_ach_running_mean(self) -> None:
        rate = max(0.0, min(1.0, float(getattr(self, "ach_mean_rate", 0.05))))
        current = self._clamp(self.acetylcholine)
        previous = self._clamp(getattr(self, "ach_running_mean", self.ach_baseline))
        self.ach_running_mean = self._clamp(previous + (rate * (current - previous)))

    def acetylcholine_reference(self) -> float:
        """Level ACh gating is measured against. A slow mean, not a fixed floor."""
        return self._clamp(getattr(self, "ach_running_mean", self.ach_baseline))

    def acetylcholine_gate(self) -> float:
        return max(0.0, self._clamp(self.acetylcholine) - self.acetylcholine_reference())

    def apply_impulses(self, impulses: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """Add bounded impulses. The field integrator relaxes them on its next step.

        Writers used to assign levels directly, so a large delta could pin a
        modulator on the clamp. Impulses are clipped, then stored on the same
        state the interaction field integrates.
        """
        payload = dict(impulses or {})
        limit = float(getattr(self, "IMPULSE_LIMIT", 0.25))
        before = {
            "dopamine": float(self.dopamine),
            "serotonin": float(self.serotonin),
            "norepinephrine": float(self.norepinephrine),
            "acetylcholine": float(self.acetylcholine),
            "cortisol": float(self.cortisol),
        }
        for key in ("dopamine", "serotonin", "norepinephrine", "acetylcholine"):
            if key not in payload:
                continue
            try:
                raw = float(payload[key])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(raw):
                continue
            bounded = max(-limit, min(limit, raw))
            setattr(self, key, self._clamp(float(getattr(self, key)) + bounded))
        if "cortisol" in payload:
            try:
                raw_cortisol = float(payload["cortisol"])
            except (TypeError, ValueError):
                raw_cortisol = 0.0
            if math.isfinite(raw_cortisol):
                bounded_cortisol = max(-limit, min(limit, raw_cortisol))
                self.cortisol = self._clamp(float(self.cortisol) + bounded_cortisol)
        self._sync_field_from_state()
        self._track_ach_running_mean()
        self.timestamp = time.time()
        return {
            key: float(getattr(self, key)) - before[key]
            for key in before
            if key in payload
        }

    def update_acetylcholine(self, novelty: float = 0.0, stable_repetition: bool = False):
        """
        Update acetylcholine using novelty/repetition and decay-to-baseline dynamics.

        ACh is a selectivity/plasticity regulator and does not encode reward.
        """
        delta, next_trace = self._compute_acetylcholine_delta(
            novelty=novelty,
            stable_repetition=stable_repetition,
        )
        self.ach_novelty_trace = next_trace
        self.acetylcholine = self._clamp(self.acetylcholine + delta)
        self._sync_field_from_state()
        self._track_ach_running_mean()

    def _integrate_cortisol(self, secretion: float, dt: float) -> None:
        """First-order HPA step. One second reproduces the legacy map.

        Clearance keeps a fraction ``(1 - ACC_CORT_HOMEOSTATIC_DECAY) ** dt``
        of the excess over baseline (0.6 ** dt with the phase-2 coefficient).
        ``secretion`` is the legacy one-second dose. Over ``dt`` the delivered
        dose is that amount times ``(1 - retain ** dt) / (1 - retain)``, the
        integral of a constant rate against the same clearance. At ``dt=1``
        this is exactly ``excess *= 0.6`` plus the full dose. The steady
        level ``baseline + secretion / pull`` does not depend on ``dt``,
        and one step of ``dt`` matches two steps of ``dt/2``.
        """
        try:
            dt_v = float(dt)
        except (TypeError, ValueError):
            dt_v = 0.0
        if not math.isfinite(dt_v) or dt_v <= 0.0:
            return
        try:
            secretion_v = float(secretion)
        except (TypeError, ValueError):
            secretion_v = 0.0
        if not math.isfinite(secretion_v):
            secretion_v = 0.0
        try:
            pull = float(self.ACC_CORT_HOMEOSTATIC_DECAY)
        except (TypeError, ValueError):
            pull = 0.0
        if not math.isfinite(pull) or pull < 0.0:
            pull = 0.0
        baseline = float(self.BASELINE_CORT)
        current = float(self.cortisol)
        if dt_v == 1.0:
            self.cortisol = current + (pull * (baseline - current)) + secretion_v
            return
        if pull == 0.0:
            self.cortisol = current + (secretion_v * dt_v)
            return
        retain = 1.0 - pull
        if retain <= 0.0:
            self.cortisol = current + ((pull * (baseline - current)) + secretion_v) * dt_v
            return
        kept = math.exp(dt_v * math.log(retain))
        delivered = (1.0 - kept) / pull
        self.cortisol = baseline + ((current - baseline) * kept) + (secretion_v * delivered)

    def update_from_signals(
        self,
        reward: float = 0.0,
        novelty: float = 0.0,
        conflict: float = 0.0,
        stable_repetition: bool = False,
        use_reward_for_dopamine: bool = True,
        cognitive_conflict: Optional[float] = None,
        affective_conflict: Optional[float] = None,
        dt: float = 1.0,
    ):
        """
        Update neuromodulators from environmental signals.

        Follows Phase 2 specification exactly.

        Args:
            reward: Outcome signal [-1.0 to +1.0]
            novelty: Unexpectedness [0.0 to 1.0]
            conflict: Legacy scalar conflict [0.0 to 1.0]
            stable_repetition: Whether experiencing stable repetition pattern
            cognitive_conflict: Optional ACC cognitive conflict channel [0.0 to 1.0]
            affective_conflict: Optional ACC affective conflict channel [0.0 to 1.0]
            dt: Simulated seconds. ACC smoothing and cortisol clearance
                both use it. At 1 the cortisol step is the legacy map.
        """
        combined_conflict_v, cognitive_conflict_v, affective_conflict_v = self._split_conflict_components(
            conflict=conflict,
            cognitive_conflict=cognitive_conflict,
            affective_conflict=affective_conflict,
        )

        # Compute phase: derive conflict modulation from a state snapshot.
        # This keeps ACC compute/apply phases separated inside one update step.
        ne_snapshot = self._clamp(self.norepinephrine)
        cort_snapshot = self._clamp(self.cortisol)
        ht_snapshot = self._clamp(self.serotonin)

        target_conflict_cognitive = self._compute_effective_conflict_from_state(
            conflict=cognitive_conflict_v,
            norepinephrine=ne_snapshot,
            cortisol=cort_snapshot,
            serotonin=ht_snapshot,
        )
        target_conflict_affective = self._compute_effective_conflict_from_state(
            conflict=affective_conflict_v,
            norepinephrine=ne_snapshot,
            cortisol=cort_snapshot,
            serotonin=ht_snapshot,
        )
        target_conflict_combined = self._compute_effective_conflict_from_state(
            conflict=combined_conflict_v,
            norepinephrine=ne_snapshot,
            cortisol=cort_snapshot,
            serotonin=ht_snapshot,
        )
        alpha = self._compute_conflict_alpha(dt)
        effective_conflict_cognitive = self._clamp(
            self._acc_cognitive_conflict_trace
            + (alpha * (target_conflict_cognitive - self._acc_cognitive_conflict_trace))
        )
        effective_conflict_affective = self._clamp(
            self._acc_affective_conflict_trace
            + (alpha * (target_conflict_affective - self._acc_affective_conflict_trace))
        )
        effective_conflict_combined = self._clamp(
            self._acc_combined_conflict_trace
            + (alpha * (target_conflict_combined - self._acc_combined_conflict_trace))
        )

        self._acc_cognitive_conflict_trace = effective_conflict_cognitive
        self._acc_affective_conflict_trace = effective_conflict_affective
        self._acc_combined_conflict_trace = effective_conflict_combined

        base_signal = {
            "dopamine": 0.0,
            "serotonin": 0.0,
            "norepinephrine": 0.0,
            "acetylcholine": 0.0,
        }

        # Dopamine: by default follows reward signal (legacy behavior).
        # In Phase 5+, Agent can disable this and drive dopamine from TD error.
        if use_reward_for_dopamine:
            if reward > 0:
                base_signal["dopamine"] += self.DA_REWARD_POSITIVE * reward
            elif reward < 0:
                base_signal["dopamine"] += self.DA_REWARD_NEGATIVE * abs(reward)

        # Serotonin: stability and temporal horizon
        if reward > 0 and effective_conflict_combined <= 0.0:
            base_signal["serotonin"] += self.HT_REWARD * reward

        if stable_repetition:
            base_signal["serotonin"] += self.HT_STABLE_REPETITION

        # Norepinephrine: uncertainty and cognitively modulated conflict signal.
        base_signal["norepinephrine"] += (
            self.ACC_NE_HOMEOSTATIC_DECAY * (self.BASELINE_NE - self.norepinephrine)
        )
        base_signal["norepinephrine"] += self.NE_NOVELTY * novelty
        base_signal["norepinephrine"] += self.NE_CONFLICT * effective_conflict_cognitive

        # Cortisol is a slower stress axis and is intentionally updated outside
        # the fast coupled interaction field (DA/5HT/NE/ACh).
        # Secretion is the legacy one-second dose. Clearance and the dose
        # are integrated together over dt (see _integrate_cortisol).
        secretion = self.CORT_CONFLICT * effective_conflict_affective
        if reward < 0:
            secretion += self.CORT_REWARD_NEGATIVE * abs(reward)
        self._integrate_cortisol(secretion, dt)

        # Acetylcholine: novelty/selectivity modulation (Phase 6.1).
        ach_delta, next_trace = self._compute_acetylcholine_delta(
            novelty=novelty,
            stable_repetition=stable_repetition,
        )
        self.ach_novelty_trace = next_trace
        base_signal["acetylcholine"] += ach_delta

        # Apply coupled interaction dynamics for DA/5HT/NE/ACh on the same
        # environment-step timescale as ACC smoothing (shared dt).
        self._apply_interaction_dynamics(base_signal, dt=dt)

        # Clamp all values
        self._clamp_all()
        self._track_ach_running_mean()
        self.timestamp = time.time()

    def apply_dopamine_delta(self, delta: float):
        """Apply a bounded dopamine impulse. The field relaxes it on the next step."""
        try:
            d = float(delta)
        except Exception:
            d = 0.0
        if not math.isfinite(d):
            d = 0.0
        self.apply_impulses({"dopamine": d})

    def get_learning_rate_modifier(self) -> float:
        """
        Get learning rate modifier.

        Dopamine increases learning rate.
        Serotonin decreases it.
        Cortisol under stress lowers plasticity.

        Range: [0.5 to 1.5] approximately
        """
        # High DA = more learning
        # High HT = less learning (consolidation over new patterns)
        # High CORT = consolidation threshold raises (less learning from noise)
        modifier = 1.0 + (self.dopamine - 0.1) * 0.5 + (self.cortisol - 0.05) * 0.3
        modifier -= (self.serotonin - 0.1) * 0.3
        return max(0.5, min(1.5, modifier))

    def get_consolidation_strength(self) -> float:
        """
        Get consolidation strength modifier.

        Dopamine enhances consolidation.
        Serotonin stabilizes consolidation.
        Cortisol determines threshold (in sleep).

        Range: [0.5 to 1.5]
        """
        # High DA enhances consolidation
        strength = 1.0 + (self.dopamine - 0.1) * 0.6 + (self.serotonin - 0.1) * 0.4
        # Stress (cortisol) can reduce consolidation quality
        strength -= (self.cortisol - 0.05) * 0.2
        return max(0.5, min(1.5, strength))

    def get_temporal_discount(self) -> float:
        """
        Get temporal discount factor for value.

        Serotonin increases future value (longer horizon).
        Dopamine creates urgency (shorter horizon in seeking).

        Range: [0.5 to 1.5] - multiplier for future value weight
        """
        # High HT = longer temporal horizon
        # High DA = more immediate reward focus
        discount = 1.0 + (self.serotonin - 0.1) * 0.5 - (self.dopamine - 0.1) * 0.3
        return max(0.5, min(1.5, discount))

    def get_exploration_level(self) -> float:
        """
        Get exploration tendency.

        Norepinephrine drives exploration.
        Cortisol under extreme stress prevents it.
        Dopamine can compete (exploitation).

        Range: [0.0 to 1.0]
        """
        # High NE = more exploration
        exploration = self.norepinephrine
        # Extreme stress prevents exploration
        exploration *= (1.0 - self.cortisol * 0.5)
        # High DA can reduce exploration (seek known rewards)
        exploration *= (1.0 - (self.dopamine - 0.1) * 0.3)
        return max(0.0, min(1.0, exploration))

    def get_temporal_chain_generation(self) -> float:
        """
        Get weight for temporal chain formation during sleep.

        Norepinephrine increases chain complexity.
        Serotonin stabilizes chains.

        Range: [0.0 to 1.0]
        """
        # NE creates more complex chains
        generation = self.norepinephrine
        # HT stabilizes them
        generation += (self.serotonin - 0.1) * 0.3
        return max(0.0, min(1.0, generation))

    def get_forgetting_rate(self) -> float:
        """
        Get forgetting/pruning rate during consolidation.

        Cortisol increases forgetting of weak traces.
        Dopamine consolidates (reduces forgetting).

        Range: [0.1 to 0.9] - fraction of traces to prune
        """
        # High CORT = more aggressive pruning
        forgetting = 0.3 + (self.cortisol - 0.05) * 0.5
        # High DA = less forgetting (consolidate more)
        forgetting -= (self.dopamine - 0.1) * 0.2
        return max(0.1, min(0.9, forgetting))

    def get_consolidation_threshold(self) -> float:
        """
        Get consolidation threshold (what counts as strong enough).

        Cortisol raises threshold (less gets consolidated).
        Dopamine lowers it (more gets consolidated).

        Range: [0.1 to 0.9]
        """
        # High CORT = higher threshold (stricter consolidation)
        threshold = 0.3 + (self.cortisol - 0.05) * 0.5
        # High DA = lower threshold
        threshold -= (self.dopamine - 0.1) * 0.3
        return max(0.1, min(0.9, threshold))

    def get_affective_arousal_modifier(self) -> float:
        """
        Get modifier for affect system arousal.

        Norepinephrine and dopamine increase arousal.
        Serotonin moderates it.

        Range: [0.5 to 1.5]
        """
        modifier = 1.0 + (self.norepinephrine - 0.1) * 0.4 + (self.dopamine - 0.1) * 0.3
        modifier -= (self.serotonin - 0.1) * 0.2
        return max(0.5, min(1.5, modifier))

    def to_dict(self) -> dict:
        """Return state as dictionary."""
        self._sync_field_from_state()
        return {
            "dopamine": self.dopamine,
            "norepinephrine": self.norepinephrine,
            "serotonin": self.serotonin,
            "cortisol": self.cortisol,
            "acetylcholine": self.acetylcholine,
            "ach_baseline": self.ach_baseline,
            "ach_decay_rate": self.ach_decay_rate,
            "ach_novelty_gain": self.ach_novelty_gain,
            "ach_repetition_penalty": self.ach_repetition_penalty,
            "ach_novelty_filter": self.ach_novelty_filter,
            "ach_novelty_trace": self.ach_novelty_trace,
            "ach_alpha_gain": self.ach_alpha_gain,
            "ach_replay_gain": self.ach_replay_gain,
            "ach_running_mean": float(getattr(self, "ach_running_mean", self.ach_baseline)),
            "ach_mean_rate": float(getattr(self, "ach_mean_rate", 0.05)),
            "acc_combined_conflict_trace": self._acc_combined_conflict_trace,
            "acc_cognitive_conflict_trace": self._acc_cognitive_conflict_trace,
            "acc_affective_conflict_trace": self._acc_affective_conflict_trace,
            "interaction_field": self.interaction_field.to_dict() if self.interaction_field else None,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NeuromodulatorState":
        """Create instance from dictionary."""
        inst = cls(
            dopamine=data.get("dopamine", cls.BASELINE_DA),
            norepinephrine=data.get("norepinephrine", cls.BASELINE_NE),
            serotonin=data.get("serotonin", cls.BASELINE_HT),
            cortisol=data.get("cortisol", cls.BASELINE_CORT),
            acetylcholine=data.get("acetylcholine", cls.BASELINE_ACH),
        )
        inst.ach_baseline = float(data.get("ach_baseline", cls.BASELINE_ACH))
        inst.ach_decay_rate = float(data.get("ach_decay_rate", cls.ACH_DECAY_RATE))
        inst.ach_novelty_gain = float(data.get("ach_novelty_gain", cls.ACH_NOVELTY_GAIN))
        inst.ach_repetition_penalty = float(data.get("ach_repetition_penalty", cls.ACH_REPETITION_PENALTY))
        inst.ach_novelty_filter = float(data.get("ach_novelty_filter", cls.ACH_NOVELTY_FILTER))
        inst.ach_novelty_trace = float(data.get("ach_novelty_trace", 0.0))
        inst.ach_alpha_gain = float(data.get("ach_alpha_gain", cls.ACH_ALPHA_GAIN))
        inst.ach_replay_gain = float(data.get("ach_replay_gain", cls.ACH_REPLAY_GAIN))
        inst.ach_running_mean = inst._clamp(float(data.get("ach_running_mean", inst.ach_baseline)))
        inst.ach_mean_rate = max(0.0, min(1.0, float(data.get("ach_mean_rate", 0.05))))
        legacy_conflict_trace = inst._clamp(float(data.get("acc_conflict_trace", 0.0)))
        inst._acc_combined_conflict_trace = inst._clamp(
            float(data.get("acc_combined_conflict_trace", legacy_conflict_trace))
        )
        inst._acc_cognitive_conflict_trace = inst._clamp(
            float(data.get("acc_cognitive_conflict_trace", legacy_conflict_trace))
        )
        inst._acc_affective_conflict_trace = inst._clamp(
            float(data.get("acc_affective_conflict_trace", legacy_conflict_trace))
        )
        raw_field = data.get("interaction_field")
        if isinstance(raw_field, dict):
            inst.interaction_field = NeuromodulatorField.from_dict(raw_field)
            inst.interaction_field.set_baselines(inst._interaction_baselines())
            inst._sync_state_from_field()
        else:
            inst._sync_field_from_state()
        inst.timestamp = float(data.get("timestamp", time.time()))
        inst._clamp_all()
        return inst

    def snapshot(self) -> dict:
        """Return immutable snapshot of current state."""
        return self.to_dict()

    def reset(self):
        """Reset to baseline state."""
        self.dopamine = self.BASELINE_DA
        self.norepinephrine = self.BASELINE_NE
        self.serotonin = self.BASELINE_HT
        self.cortisol = self.BASELINE_CORT
        self.acetylcholine = self.ach_baseline
        self.ach_running_mean = float(self.ach_baseline)
        self.ach_novelty_trace = 0.0
        self._acc_combined_conflict_trace = 0.0
        self._acc_cognitive_conflict_trace = 0.0
        self._acc_affective_conflict_trace = 0.0
        self._sync_field_from_state()
        if self.interaction_field is not None:
            self.interaction_field.reset()
            self._sync_state_from_field()
        self.timestamp = time.time()
