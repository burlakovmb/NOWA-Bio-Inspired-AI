"""
Sleep Consolidation - The ONLY mechanism for learning and generalization.

During sleep:
1. Recent experiences are clustered and abstracted
2. Patterns are consolidated to cortex (slow memory)
3. Noisy/unstable experiences degrade
4. No learning happens outside of sleep
"""

import time
import math
import random
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple
from experience import Path, Event, EventType
from temporal_chains import ChainMemory
from value_layer import (
    derived_alpha_sleep,
    discounted_value_bound,
    effective_alpha_sleep,
    state_similarity,
)


class CorticalPattern:
    """Consolidated pattern in cortex - abstract experience representation"""
    
    def __init__(self, signature: tuple, source_experiences: int = 1):
        """
        Initialize pattern
        
        Args:
            signature: Tuple of event names
            source_experiences: How many experiences were consolidated into this
        """
        self.signature = signature
        self.strength = 1.0
        self.created_at = time.time()
        self.last_activated = time.time()
        self.source_experiences = source_experiences
        self.activation_count = 0
    
    def activate(self):
        """Mark this pattern as activated"""
        self.activation_count += 1
        self.last_activated = time.time()
    
    def decay_strength(self, decay_rate: float = 0.001):
        """Slow degradation of pattern over time"""
        time_since_creation = time.time() - self.created_at
        # Exponential decay with very long half-life
        self.strength = math.exp(-decay_rate * time_since_creation)
    
    def __repr__(self):
        return f"CorticalPattern({len(self.signature)} events, strength={self.strength:.2f})"


class CortexMemory:
    """
    Slow cortical memory - only modified during sleep.
    
    Stores abstract patterns consolidated from hippocampal experiences.
    NOT updated during waking activity.
    """
    
    def __init__(self):
        self.patterns = []
        self.consolidation_history = []
    
    def store_pattern(self, signature: tuple, source_experiences: int = 1) -> CorticalPattern:
        """
        Store consolidated pattern.
        
        Reinforces existing pattern if seen before, else creates new.
        
        Args:
            signature: Tuple of event names
            source_experiences: Number of experiences consolidated
        
        Returns:
            CorticalPattern object
        """
        # Check if pattern exists
        for p in self.patterns:
            if p.signature == signature:
                p.strength += 0.1
                p.source_experiences += source_experiences
                return p
        
        # New pattern
        pattern = CorticalPattern(signature, source_experiences)
        self.patterns.append(pattern)
        return pattern

    # Backward-compatibility wrapper
    def store(self, events: list):
        """Compatibility: accept list of event names and store as pattern."""
        signature = tuple(events)
        return self.store_pattern(signature)
    
    def activate(self, context: list) -> list:
        """Get patterns matching context during waking"""
        activated = []
        for p in self.patterns:
            if all(c in p.signature for c in context):
                p.activate()
                activated.append(p)
        return activated
    
    def get_statistics(self) -> dict:
        """Statistics about cortical state"""
        if not self.patterns:
            return {"total_patterns": 0, "avg_strength": 0}
        
        return {
            "total_patterns": len(self.patterns),
            "avg_strength": sum(p.strength for p in self.patterns) / len(self.patterns),
            "total_consolidated_experiences": sum(p.source_experiences for p in self.patterns)
        }


class SleepManager:
    """
    Sleep consolidation — the only writer of the stable tier.
    
    Process:
    1. Select experiences from hippocampus
    2. Cluster similar experiences
    3. Abstract into patterns
    4. Store in cortex
    5. Forget unstable hippocampal traces
    """
    
    def __init__(self, hippocampus, cortex, intent_memory=None,
                 clustering_similarity_threshold: float = 0.8,
                 forget_stability_threshold: float = 0.2):
        """
        Initialize sleep manager
        
        Args:
            hippocampus: NOWAHippocampus instance
            cortex: CortexMemory instance
            intent_memory: IntentMemory instance (optional)
            clustering_similarity_threshold: How similar experiences need to be to cluster
            forget_stability_threshold: Below this, experiences are forgotten
        """
        self.hippocampus = hippocampus
        self.cortex = cortex
        self.intent_memory = intent_memory
        # ChainMemory for Plan B temporal chains
        self.chain_memory = ChainMemory()
        self.clustering_similarity_threshold = clustering_similarity_threshold
        self.forget_stability_threshold = forget_stability_threshold
        self.consolidation_cycles = 0
        # Phase 5.A.1/6.2 replay-driven TD consolidation safeguards.
        self.replay_priority_weights: Tuple[float, float, float] = (0.6, 0.25, 0.15)
        self.replay_budget_per_sleep: int = 32
        self.max_replay_per_episode: int = 3
        self.replay_priority_min: float = 1e-6
        self.replay_temperature_decay: float = 0.95
        self.instability_variance_threshold: float = 0.25
        # Uncertainty of one state's reward estimate. This is not the spread
        # of V across states (instability_variance_threshold).
        self.state_estimate_variance_threshold: float = 0.5
        self.td_clip_sleep: float = 1.0
        # Spec-011A: credit assignment stabilization.
        self.credit_window: int = 6
        self.eligibility_lambda: float = 0.85
        self.credit_decay_tau: float = 3.0
        self.credit_weight_min: float = 0.05
        self.causality_threshold: float = 0.15
        self.replay_stability_threshold: float = 0.25
        self.max_replay_per_state: int = 3
        self.reward_anchor_threshold: float = 0.1
        self.td_anchor_threshold: float = 0.12
        self.delta_value_max_per_sleep: float = 0.025
        self.value_total_cap: float = 0.3
        # Legacy field. _resolved_value_cap widens a unit clamp to 1/(1-γ).
        self.value_cap: float = 1.0
        self.alpha_sleep_ratio: float = 0.25
        self.dopamine_sleep_scale: float = 0.3
        self.ach_replay_gain: float = 0.5
        self.replay_priority_cap: float = 3.0
        self.edpc_priority_enabled: bool = True
        self.edpc_consolidation_blend: float = 0.5
        self.shock_priority_gain: float = 1.0
        # EDPC <-> SAC synchronization parameters.
        self.edpc_sac_ema_alpha: float = 0.1
        self.edpc_sac_stability_k1: float = 0.01
        self.edpc_sac_td_stability_gain: float = 0.03
        self.edpc_sac_energy_budget: float = float(self.replay_budget_per_sleep)
        self.edpc_sac_conflict_threshold: float = 0.3
        # Sleep BG steps must be able to beat one cycle of decay toward the prior.
        self.beta_sleep: float = 0.05
        self.delta_weight_max_per_sleep: float = 0.05
        self.weight_total_cap: float = 0.6
        self.decay_rate_sleep: float = 0.02
        self.weight_norm_cap: float = 6.0
        # Phase 6.2 / 6.2.1 filtered consolidation criteria.
        self.td_threshold: float = 0.12
        self.td_variance_cap: float = 0.25
        self.salience_threshold: float = 0.10
        self.min_reinforcement_for_consolidation: int = 1
        self.variance_gate_threshold: float = 1.0
        self.ach_min_for_consolidation: float = 0.0
        self.stability_index_threshold: float = 0.5
        self.consolidation_cap: float = 1.0
        self.w_td: float = 0.45
        self.w_salience: float = 0.20
        self.w_importance: float = 0.20
        self.w_ach: float = 0.10
        self.w_encoding: float = 0.05
        # Phase 6.2.1 update caps (aliases are kept for backward compatibility).
        self.sleep_alpha_cap: float = 0.2
        self.per_update_cap: float = self.delta_value_max_per_sleep
        self.max_l2_update_per_cycle: float = 0.25
        self.global_sleep_update_budget: float = self.value_total_cap
        # Semantic Action Consolidation (SAC): slow semantic updates from replay.
        self.sac_theta_conf: float = 0.6
        self.sac_theta_stab: float = 0.5
        self.sac_theta_shock: float = 0.4
        self.sac_theta_cons: float = 0.5
        self.sac_theta_min_weight: float = 0.05
        self.sac_alpha_slow: float = 0.01
        self.sac_epsilon_divergence: float = 0.08
        self.sac_epsilon_var: float = 0.01
        self.sac_sigma_floor: float = 0.01
        self.sac_replay_min_count: int = 3
        self.sac_shock_block_threshold: float = 0.6
        self.sac_shock_variance_threshold: float = 0.3
        self.sac_high_stability_threshold: float = 0.8
        self.sac_stability_variance_discount: float = 0.05
        self.sac_success_threshold: float = 0.0
        # SWS / REM phase separation controls (Spec: spec_sws_rem_phase_separation.md).
        self.local_phase_mode: bool = False
        self.sac_theta_arousal_low: float = 0.35
        self.sac_theta_arousal_high: float = 0.65
        self.sac_theta_shock_low: float = 0.20
        self.sac_theta_shock_high: float = 0.40
        self.sac_theta_conf_high: float = self.sac_theta_conf
        self.sac_theta_cons_high: float = self.sac_theta_cons
        self.sac_theta_stability_high: float = self.sac_theta_stab
        self.sac_alpha_base: float = self.sac_alpha_slow
        self.sac_alpha_sigma: float = self.sac_alpha_slow
        self.sac_sigma_decay_sws: float = self.sac_stability_variance_discount
        self.sac_epsilon_var_rem: float = self.sac_epsilon_var
        self.sac_beta_stability_sws: float = 0.03
        self.sac_delta_rem: float = 0.08
        self.sac_stability_floor_rem: float = 0.2
        self.sac_lambda_sws: float = 0.20
        self.sac_lambda_rem: float = 0.08
        self.sac_semantic_confidence_step_cap: float = 0.05
        self.sac_theta_structural: float = 0.80
        self.sac_structural_alert_reset_cycles: int = 3
        self._rng = random.Random()
        self.last_sleep_replay_stats: Dict[str, float] = {}
        self.last_sac_stats: Dict[str, float] = {}

    def _resolved_alpha_sleep(self, value_layer, stability_gate: float) -> float:
        """Sleep step size: alpha_online * alpha_sleep_ratio, never above the spec.

        A stored ``alpha_sleep_default`` may only make the rate smaller.
        """
        alpha_online = float(
            getattr(
                value_layer,
                "alpha_online_default",
                getattr(value_layer, "alpha_default", 0.03),
            )
        )
        ratio = getattr(self, "alpha_sleep_ratio", 0.25)
        stored = getattr(value_layer, "alpha_sleep_default", None)
        alpha_sleep = effective_alpha_sleep(alpha_online, stored, ratio)
        try:
            gate = float(stability_gate)
        except (TypeError, ValueError):
            gate = 1.0
        if not math.isfinite(gate):
            gate = 1.0
        gate = max(0.0, min(1.0, gate))
        try:
            sleep_alpha_cap = float(getattr(self, "sleep_alpha_cap", 0.2))
        except (TypeError, ValueError):
            sleep_alpha_cap = 0.2
        if not math.isfinite(sleep_alpha_cap) or sleep_alpha_cap < 0.0:
            sleep_alpha_cap = 0.2
        effective = min(sleep_alpha_cap, alpha_sleep * gate)
        return min(max(0.0, effective), derived_alpha_sleep(alpha_online, ratio))

    def _resolved_value_cap(self) -> float:
        """V range at least 1/(1-γ) for a unit reward.

        A configured ``value_cap`` may be wider. It cannot stay at the legacy
        unit clamp, which cannot hold the discounted return.
        """
        layer = getattr(self, "value_layer", None)
        gamma = 0.95
        if layer is not None:
            gamma = getattr(layer, "gamma_default", 0.95)
        needed = discounted_value_bound(gamma, 1.0)
        try:
            configured = float(getattr(self, "value_cap", needed))
        except (TypeError, ValueError):
            return needed
        if not math.isfinite(configured) or configured <= 0.0:
            return needed
        return max(configured, needed)
    
    def sleep_cycle(self) -> dict:
        """
        Execute one sleep cycle.

        Consolidates hippocampal experiences to cortex and refreshes
        intent_memory. Capture, habit EMA and episode Go/NoGo run once
        per ``deep_sleep``, not once per cycle. Replay may revisit a
        transition inside that same sleep.
        """
        from learning_guard import learning_allowed

        with learning_allowed():
            return self._sleep_cycle_impl()

    def _sleep_cycle_impl(self) -> dict:
        """Body of ``sleep_cycle``. Callers use ``sleep_cycle``."""
        sleep_timestamp = time.time()
        stats = {
            "candidates": 0,
            "clusters": 0,
            "patterns_consolidated": 0,
            "experiences_forgotten": 0,
            "replays": 0,
            "replay_selected": 0,
            "replay_blocked": False,
            "replay_budget": int(self.replay_budget_per_sleep),
            "replay_diversity_index": 0.0,
            "shock_replays": 0,
            "shock_frequency": 0.0,
            "replay_confidence_mean": 0.0,
            "replay_stability_mean": 0.0,
            "eligibility_trace_mean": 0.0,
            "credit_window_usage": 0.0,
            "replay_causality_mean": 0.0,
            "value_variance": 0.0,
            "value_delta_total": 0.0,
            "weight_delta_total": 0.0,
            "total_value_delta_sleep": 0.0,
            "total_bg_delta_sleep": 0.0,
            "sleep_update_count": 0,
            "decay_applied": False,
            "normalization_applied": False,
            "mean_ach_during_cycle": 0.0,
            "mean_ach_above_baseline": 0.0,
            "value_variance_ratio": 0.0,
            "variance_ratio": 0.0,
            "total_episodes_examined": 0,
            "total_episodes_consolidated": 0,
            "rejected_due_to_td_threshold": 0,
            "rejected_due_to_td_variance": 0,
            "rejected_due_to_salience": 0,
            "rejected_due_to_reinforcement": 0,
            "rejected_due_to_variance_gate": 0,
            "rejected_due_to_ach": 0,
            "rejected_due_to_stability": 0,
            "mean_consolidation_score": 0.0,
            "sleep_update_l2_total": 0.0,
            "consolidation_ratio": 0.0,
            "sac_episodes_gated": 0,
            "sac_actions_considered": 0,
            "sac_actions_updated": 0,
            "sac_actions_skipped": 0,
            "sac_rejected_confidence": 0,
            "sac_rejected_stability": 0,
            "sac_rejected_shock": 0,
            "sac_rejected_consolidation_probability": 0,
            "sac_rejected_replay_count": 0,
            "sac_rejected_min_weight": 0,
            "sac_rejected_shock_mean": 0,
            "sac_rejected_divergence": 0,
            "sac_rejected_missing_signal": 0,
            "semantic_drift_rate": 0.0,
            "stability_growth_rate": 0.0,
            "divergence_reduction_index": 0.0,
            "overconfidence_index": 0.0,
            "sac_phase": "TRANSITIONAL",
            "phase_distribution": {"SWS": 0, "REM": 0, "TRANSITIONAL": 0},
            "sac_phase_sws": 0,
            "sac_phase_rem": 0,
            "sac_phase_transitional": 0,
            "mean_sigma_change": 0.0,
            "mean_stability_change": 0.0,
            "structural_alert_count": 0,
            "edpc_sac_sync_enabled": False,
            "edpc_sac_sync_phase": "TRANSITIONAL",
            "edpc_sac_sync_updates": 0,
            "edpc_sac_sync_conflicts": 0,
            "edpc_sac_sync_energy_used": 0.0,
            "edpc_sac_sync_skipped": 0,
            "intent_degraded": False,
            "intent_stats": {}
        }

        # Clear conflict flags at the start of each sleep cycle to avoid stale states.
        self._reset_conflict_flags()
        
        # 1. Get candidates for consolidation
        min_reinforcement = max(1, int(getattr(self, "min_reinforcement_for_consolidation", 1)))
        candidates = self.hippocampus.get_candidates_for_sleep(min_reinforcement=min_reinforcement)
        # An episode already consolidated (and not revised since) is not
        # replayed again. The sleep that consolidates it has not marked it
        # yet, so the cycles of that sleep still see it.
        candidates = [exp for exp in list(candidates or []) if not self._consolidation_closed(exp)]
        stats["candidates"] = len(candidates)
        stats["total_episodes_examined"] = len(candidates)
        stats["mean_ach_during_cycle"] = float(self._estimate_mean_ach(candidates))
        stats["mean_ach_above_baseline"] = float(self._estimate_mean_ach_above_baseline(candidates))

        # 2. Phase 6.2.1 filtered consolidation (sleep-only).
        value_variance = self._compute_value_variance()
        stats["value_variance"] = value_variance
        variance_threshold = max(1e-9, float(self.instability_variance_threshold))
        value_variance_ratio = float(value_variance) / variance_threshold
        stats["value_variance_ratio"] = value_variance_ratio
        stats["variance_ratio"] = value_variance_ratio
        replay_sample: List = []
        filtered_candidates: List = []

        if candidates:
            # value_variance_ratio is the spread of V across states. It stays
            # in the stats, and it does not gate replay: a well-separated
            # table still replays. Per-state estimate variance gates below.
            filtered_candidates, rejection_counts = self._filter_candidates_for_consolidation(
                candidates=candidates,
                value_variance_ratio=value_variance_ratio,
            )
            for key, value in rejection_counts.items():
                if key in stats:
                    stats[key] += int(value)

            replay_sample = self._select_replay_sample(
                filtered_candidates,
                value_variance=value_variance,
            )
            stats["replay_selected"] = len(replay_sample)
            if replay_sample:
                unique_episodes = len({id(exp) for exp in replay_sample})
                stats["replay_diversity_index"] = float(unique_episodes) / float(len(replay_sample))
                shock_replays = sum(1 for exp in replay_sample if self._episode_prediction_shock_flag(exp))
                stats["shock_replays"] = int(shock_replays)
                stats["shock_frequency"] = float(shock_replays) / float(len(replay_sample))
                confidence_values = [self._episode_confidence_score(exp) for exp in replay_sample]
                stability_values = [self._episode_expectation_stability(exp) for exp in replay_sample]
                if confidence_values:
                    stats["replay_confidence_mean"] = float(sum(confidence_values) / float(len(confidence_values)))
                if stability_values:
                    stats["replay_stability_mean"] = float(sum(stability_values) / float(len(stability_values)))
            replay_stats = self._apply_replay_td_bg(
                replay_sample,
                value_variance=value_variance,
            )
            replay_applied = int(replay_stats.get("replays_applied", 0))
            stats["replays"] = replay_applied
            stats["total_episodes_consolidated"] = replay_applied
            if replay_applied > 0:
                self._replay_experiences(replay_sample[:replay_applied])
            stats["value_delta_total"] = float(replay_stats.get("value_delta_total", 0.0))
            stats["weight_delta_total"] = float(replay_stats.get("weight_delta_total", 0.0))
            stats["total_value_delta_sleep"] = float(replay_stats.get("total_value_delta_sleep", 0.0))
            stats["total_bg_delta_sleep"] = float(replay_stats.get("total_bg_delta_sleep", 0.0))
            stats["sleep_update_count"] = int(replay_stats.get("sleep_update_count", 0))
            stats["sleep_update_l2_total"] = float(replay_stats.get("sleep_update_l2_total", 0.0))
            stats["mean_consolidation_score"] = float(replay_stats.get("mean_consolidation_score", 0.0))
            stats["eligibility_trace_mean"] = float(
                replay_stats.get("eligibility_trace_mean", 0.0)
            )
            stats["credit_window_usage"] = float(
                replay_stats.get("credit_window_usage", 0.0)
            )
            stats["replay_causality_mean"] = float(
                replay_stats.get("replay_causality_mean", 0.0)
            )
            stats["replay_blocked"] = bool(
                stats.get("replay_blocked", False) or replay_stats.get("replay_blocked", False)
            )
            sac_stats = self._apply_semantic_action_consolidation(
                replay_sample,
                sleep_state=True,
            )
            for key, value in sac_stats.items():
                if key in stats:
                    stats[key] = value
            sync_stats = self._sync_edpc_sac(
                replay_sample,
                sleep_phase=str(stats.get("sac_phase", "TRANSITIONAL")),
                sleep_state=True,
                sleep_timestamp=sleep_timestamp,
            )
            for key, value in sync_stats.items():
                stats[key] = value
            if stats["total_episodes_examined"] > 0:
                stats["consolidation_ratio"] = (
                    float(stats["total_episodes_consolidated"]) / float(stats["total_episodes_examined"])
                )

        # 3. Mandatory anti-runaway post-processing for BG weights.
        stats["decay_applied"] = self._apply_bg_decay()
        stats["normalization_applied"] = self._normalize_bg_weights()

        if filtered_candidates:
            # 4. Cluster similar experiences
            clusters = self._cluster_experiences(filtered_candidates)
            stats["clusters"] = len(clusters)

            # 5. Consolidate clusters to cortex
            for cluster in clusters:
                self._consolidate_cluster(cluster)
                stats["patterns_consolidated"] += 1

        # 4.5 Form temporal chains from recent experiences (Plan B)
        try:
            formed = self._form_chains_from_recent()
            stats["chains_formed"] = formed
        except Exception:
            stats["chains_formed"] = 0
        
        # 5. Clean up - forget unstable experiences
        forgotten = self._forget_unstable()
        stats["experiences_forgotten"] = forgotten
        
        # 6. Process intent_memory - degrade unused, keep strong
        if self.intent_memory:
            self.intent_memory.degrade_unused(decay_factor=0.8)
            stats["intent_degraded"] = True
            stats["intent_stats"] = self.intent_memory.get_stats()
        
        self.consolidation_cycles += 1
        # Apply neuromodulatory effects during/after sleep if available
        try:
            if hasattr(self, 'neuromodulators') and self.neuromodulators is not None:
                self._apply_neuromodulators_during_sleep()
        except Exception:
            pass

        self.last_sleep_replay_stats = {
            "replay_blocked": bool(stats.get("replay_blocked", False)),
            "replay_selected": int(stats.get("replay_selected", 0)),
            "replays": int(stats.get("replays", 0)),
            "replay_diversity_index": float(stats.get("replay_diversity_index", 0.0)),
            "shock_replays": int(stats.get("shock_replays", 0)),
            "shock_frequency": float(stats.get("shock_frequency", 0.0)),
            "replay_confidence_mean": float(stats.get("replay_confidence_mean", 0.0)),
            "replay_stability_mean": float(stats.get("replay_stability_mean", 0.0)),
            "eligibility_trace_mean": float(stats.get("eligibility_trace_mean", 0.0)),
            "credit_window_usage": float(stats.get("credit_window_usage", 0.0)),
            "replay_causality_mean": float(stats.get("replay_causality_mean", 0.0)),
            "value_variance": float(stats.get("value_variance", 0.0)),
            "value_delta_total": float(stats.get("value_delta_total", 0.0)),
            "weight_delta_total": float(stats.get("weight_delta_total", 0.0)),
            "total_value_delta_sleep": float(stats.get("total_value_delta_sleep", 0.0)),
            "total_bg_delta_sleep": float(stats.get("total_bg_delta_sleep", 0.0)),
            "sleep_update_count": int(stats.get("sleep_update_count", 0)),
            "decay_applied": bool(stats.get("decay_applied", False)),
            "normalization_applied": bool(stats.get("normalization_applied", False)),
            "mean_ach_during_cycle": float(stats.get("mean_ach_during_cycle", 0.0)),
            "mean_ach_above_baseline": float(stats.get("mean_ach_above_baseline", 0.0)),
            "value_variance_ratio": float(stats.get("value_variance_ratio", 0.0)),
            "variance_ratio": float(stats.get("variance_ratio", 0.0)),
            "total_episodes_examined": int(stats.get("total_episodes_examined", 0)),
            "total_episodes_consolidated": int(stats.get("total_episodes_consolidated", 0)),
            "rejected_due_to_td_threshold": int(stats.get("rejected_due_to_td_threshold", 0)),
            "rejected_due_to_td_variance": int(stats.get("rejected_due_to_td_variance", 0)),
            "rejected_due_to_salience": int(stats.get("rejected_due_to_salience", 0)),
            "rejected_due_to_reinforcement": int(stats.get("rejected_due_to_reinforcement", 0)),
            "rejected_due_to_variance_gate": int(stats.get("rejected_due_to_variance_gate", 0)),
            "rejected_due_to_ach": int(stats.get("rejected_due_to_ach", 0)),
            "rejected_due_to_stability": int(stats.get("rejected_due_to_stability", 0)),
            "mean_consolidation_score": float(stats.get("mean_consolidation_score", 0.0)),
            "sleep_update_l2_total": float(stats.get("sleep_update_l2_total", 0.0)),
            "consolidation_ratio": float(stats.get("consolidation_ratio", 0.0)),
            "sac_episodes_gated": int(stats.get("sac_episodes_gated", 0)),
            "sac_actions_considered": int(stats.get("sac_actions_considered", 0)),
            "sac_actions_updated": int(stats.get("sac_actions_updated", 0)),
            "sac_actions_skipped": int(stats.get("sac_actions_skipped", 0)),
            "sac_rejected_confidence": int(stats.get("sac_rejected_confidence", 0)),
            "sac_rejected_stability": int(stats.get("sac_rejected_stability", 0)),
            "sac_rejected_shock": int(stats.get("sac_rejected_shock", 0)),
            "sac_rejected_consolidation_probability": int(stats.get("sac_rejected_consolidation_probability", 0)),
            "sac_rejected_replay_count": int(stats.get("sac_rejected_replay_count", 0)),
            "sac_rejected_min_weight": int(stats.get("sac_rejected_min_weight", 0)),
            "sac_rejected_shock_mean": int(stats.get("sac_rejected_shock_mean", 0)),
            "sac_rejected_divergence": int(stats.get("sac_rejected_divergence", 0)),
            "sac_rejected_missing_signal": int(stats.get("sac_rejected_missing_signal", 0)),
            "semantic_drift_rate": float(stats.get("semantic_drift_rate", 0.0)),
            "stability_growth_rate": float(stats.get("stability_growth_rate", 0.0)),
            "divergence_reduction_index": float(stats.get("divergence_reduction_index", 0.0)),
            "overconfidence_index": float(stats.get("overconfidence_index", 0.0)),
            "sac_phase": str(stats.get("sac_phase", "TRANSITIONAL")),
            "phase_distribution": dict(stats.get("phase_distribution", {"SWS": 0, "REM": 0, "TRANSITIONAL": 0})),
            "sac_phase_sws": int(stats.get("sac_phase_sws", 0)),
            "sac_phase_rem": int(stats.get("sac_phase_rem", 0)),
            "sac_phase_transitional": int(stats.get("sac_phase_transitional", 0)),
            "mean_sigma_change": float(stats.get("mean_sigma_change", 0.0)),
            "mean_stability_change": float(stats.get("mean_stability_change", 0.0)),
            "structural_alert_count": int(stats.get("structural_alert_count", 0)),
        }
        self.last_sac_stats = {
            "sac_episodes_gated": int(stats.get("sac_episodes_gated", 0)),
            "sac_actions_considered": int(stats.get("sac_actions_considered", 0)),
            "sac_actions_updated": int(stats.get("sac_actions_updated", 0)),
            "sac_actions_skipped": int(stats.get("sac_actions_skipped", 0)),
            "sac_rejected_confidence": int(stats.get("sac_rejected_confidence", 0)),
            "sac_rejected_stability": int(stats.get("sac_rejected_stability", 0)),
            "sac_rejected_shock": int(stats.get("sac_rejected_shock", 0)),
            "sac_rejected_consolidation_probability": int(stats.get("sac_rejected_consolidation_probability", 0)),
            "sac_rejected_replay_count": int(stats.get("sac_rejected_replay_count", 0)),
            "sac_rejected_min_weight": int(stats.get("sac_rejected_min_weight", 0)),
            "sac_rejected_shock_mean": int(stats.get("sac_rejected_shock_mean", 0)),
            "sac_rejected_divergence": int(stats.get("sac_rejected_divergence", 0)),
            "sac_rejected_missing_signal": int(stats.get("sac_rejected_missing_signal", 0)),
            "semantic_drift_rate": float(stats.get("semantic_drift_rate", 0.0)),
            "stability_growth_rate": float(stats.get("stability_growth_rate", 0.0)),
            "divergence_reduction_index": float(stats.get("divergence_reduction_index", 0.0)),
            "overconfidence_index": float(stats.get("overconfidence_index", 0.0)),
            "sac_phase": str(stats.get("sac_phase", "TRANSITIONAL")),
            "phase_distribution": dict(stats.get("phase_distribution", {"SWS": 0, "REM": 0, "TRANSITIONAL": 0})),
            "sac_phase_sws": int(stats.get("sac_phase_sws", 0)),
            "sac_phase_rem": int(stats.get("sac_phase_rem", 0)),
            "sac_phase_transitional": int(stats.get("sac_phase_transitional", 0)),
            "mean_sigma_change": float(stats.get("mean_sigma_change", 0.0)),
            "mean_stability_change": float(stats.get("mean_stability_change", 0.0)),
            "structural_alert_count": int(stats.get("structural_alert_count", 0)),
        }

        try:
            space = getattr(self, "affective_space", None)
            if space is not None and hasattr(space, "step"):
                replay_impulses = []
                recall = getattr(space, "recall_trace", None)
                if callable(recall):
                    hippo = getattr(self, "hippocampus", None)
                    for exp in list(getattr(hippo, "experiences", []) or [])[-8:]:
                        trace = getattr(exp, "emotional_trace", None)
                        if trace is None:
                            continue
                        try:
                            replay_impulses.append(recall(trace, k=0.15))
                        except Exception:
                            continue
                bg = getattr(self, "affective_background", None)
                background = {}
                snap = getattr(bg, "snapshot", None)
                if callable(snap):
                    try:
                        background = dict(snap() or {})
                    except Exception:
                        background = {}
                axes = dict(getattr(space, "axes", {}) or {})
                space.step(
                    external_impulses=[],
                    recall_impulses=replay_impulses,
                    internal_impulses=[
                        {
                            "vector": {
                                "arousal": -0.2 * max(0.0, float(axes.get("arousal", 0.0))),
                                "stress": -0.25 * max(0.0, float(axes.get("stress", 0.0))),
                                "stability": 0.15,
                            },
                            "intensity": 0.3,
                            "source": "internal",
                        }
                    ],
                    time_elapsed=8.0,
                    wakefulness=0.0,
                    background=background,
                )
        except Exception:
            pass

        return stats

    def _apply_neuromodulators_during_sleep(self):
        """Apply indirect, global effects of neuromodulators on consolidation.

        Effects are intentionally simple and non-decisional:
        - Dopamine: modestly strengthen cortical patterns
        - Cortisol: increase forgetting of low-stability hippocampal traces
        - Norepinephrine: promote additional chain formation
        - Serotonin: slightly stabilize existing patterns
        """
        nm = self.neuromodulators
        # Dopamine: boost cortical pattern strengths slightly
        try:
            da = getattr(nm, 'dopamine', 0.0)
            if da > 0.05 and hasattr(self.cortex, 'patterns'):
                factor = 1.0 + (da * 0.05)
                for p in getattr(self.cortex, 'patterns', []):
                    try:
                        p.strength = p.strength * factor
                    except Exception:
                        pass
        except Exception:
            pass

        # Serotonin: slow stabilizing effect (increase stability of recent experiences)
        try:
            se = getattr(nm, 'serotonin', 0.0)
            if se > 0.1:
                for exp in list(self.hippocampus.experiences[-50:]):
                    try:
                        exp.stability = min(1.0, exp.stability + se * 0.01)
                    except Exception:
                        pass
        except Exception:
            pass

        # Cortisol: promote forgetting of low-stability traces
        try:
            co = getattr(nm, 'cortisol', 0.0)
            if co > 0.4:
                threshold = self.forget_stability_threshold + (co * 0.2)
                before = len(self.hippocampus.experiences)
                kept = [exp for exp in self.hippocampus.experiences if exp.stability >= threshold or exp.reinforcement_count >= 2]
                self.hippocampus.experiences = kept
        except Exception:
            pass

        # Norepinephrine: increase chance of forming temporal chains
        try:
            ne = getattr(nm, 'norepinephrine', 0.0)
            if ne > 0.4 and hasattr(self, '_form_chains_from_recent'):
                # run one additional pass with slightly larger max_len
                try:
                    self._form_chains_from_recent(max_len=9)
                except Exception:
                    pass
        except Exception:
            pass
    
    def _replay_experiences(self, experiences: List) -> int:
        """
        Replay experiences to strengthen them.
        
        During replay, activation energy increases slightly.
        
        Args:
            experiences: List of experiences to replay
        
        Returns:
            Number of replays done
        """
        for exp in experiences:
            # Strengthening through replay
            exp.reinforcement_count += 1
            # Stability increases with each replay cycle
            exp.stability = min(1.0, exp.stability + 0.05)
            try:
                exp.replay_count_sleep = int(getattr(exp, "replay_count_sleep", 0)) + 1
            except Exception:
                pass
        
        return len(experiences)

    def _compute_value_variance(self) -> float:
        value_layer = getattr(self, "value_layer", None)
        if value_layer is None:
            return 0.0
        values = list(getattr(value_layer, "values", {}).values())
        if len(values) < 2:
            return 0.0
        try:
            mean_v = sum(float(v) for v in values) / float(len(values))
            return sum((float(v) - mean_v) ** 2 for v in values) / float(len(values))
        except Exception:
            return 0.0

    def _get_global_stability_index(self) -> float:
        try:
            monitor = getattr(self, "stability_monitor", None)
            if monitor is not None and hasattr(monitor, "snapshot"):
                snapshot = monitor.snapshot()
                return max(0.0, min(1.0, float(snapshot.get("stability_index", 1.0))))
        except Exception:
            pass
        return 1.0

    def _episode_stability_flag(self, exp) -> bool:
        explicit = getattr(exp, "stability_flag", None)
        if explicit is not None:
            return bool(explicit)
        threshold = max(0.0, min(1.0, float(getattr(self, "stability_index_threshold", 0.5))))
        return bool(self._get_global_stability_index() >= threshold)

    def _episode_td_mean(self, exp) -> float:
        history = getattr(exp, "td_history_snapshot", None)
        td_error_snapshot = None
        if hasattr(exp, "td_error_snapshot"):
            try:
                td_error_snapshot = float(getattr(exp, "td_error_snapshot"))
            except Exception:
                td_error_snapshot = None
        if isinstance(history, list) and history:
            try:
                values = [float(value) for value in history]
                if td_error_snapshot is not None and not math.isclose(
                    values[-1], td_error_snapshot, rel_tol=0.0, abs_tol=1e-12
                ):
                    return td_error_snapshot
                return sum(values) / float(len(values))
            except Exception:
                pass
        if hasattr(exp, "td_mean_snapshot"):
            try:
                return float(getattr(exp, "td_mean_snapshot"))
            except Exception:
                pass
        if td_error_snapshot is not None:
            return td_error_snapshot
        return 0.0

    def _replay_signed_td(self, exp) -> float:
        """TD error against the current table. Stored snapshots are not the update."""
        if getattr(self, "value_layer", None) is not None:
            try:
                return float(self._compute_offline_td_error(exp))
            except Exception:
                pass
        return float(self._episode_td_mean(exp))

    def _state_estimate_variance(self, exp) -> float:
        """Variance of the value estimate for this state, not the spread across states."""
        override = getattr(exp, "state_estimate_variance", None)
        if override is not None:
            try:
                return max(0.0, float(override))
            except (TypeError, ValueError):
                pass
        value_layer = getattr(self, "value_layer", None)
        if value_layer is None:
            return 0.0
        state_key = str(getattr(exp, "value_state_key", "") or "").strip()
        snapshot = getattr(exp, "value_state_snapshot", None)
        if not state_key and isinstance(snapshot, dict):
            try:
                state_key = str(value_layer.encoder.encode(snapshot))
            except Exception:
                state_key = ""
        memory = getattr(value_layer, "expectation_memory", None)
        if state_key and isinstance(memory, dict):
            profile = memory.get(state_key)
            if isinstance(profile, dict):
                try:
                    return max(0.0, float(profile.get("expected_reward_var", 0.0)))
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    def _per_state_variance_gate(self, exp) -> float:
        variance = self._state_estimate_variance(exp)
        threshold = max(1e-9, float(getattr(self, "state_estimate_variance_threshold", 0.5)))
        if variance >= threshold:
            return 0.0
        return max(0.0, min(1.0, 1.0 - (variance / threshold)))

    def _trajectory_group_key(self, exp) -> str:
        raw = getattr(exp, "trajectory_id", None)
        if raw:
            return str(raw)
        return ""

    def _trajectory_position(self, exp, ordinal: int) -> float:
        for name in ("episode_step", "step_index", "trajectory_step"):
            raw = getattr(exp, name, None)
            if raw is None:
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
        try:
            timestamp = float(getattr(exp, "timestamp", ordinal))
        except (TypeError, ValueError):
            return float(ordinal)
        # Fixture sequences store the step in timestamp (0, 1, 2, ...).
        # Wall-clock timestamps are not step distances.
        if math.isfinite(timestamp) and 0.0 <= timestamp <= 100_000.0 and abs(timestamp - round(timestamp)) <= 1e-6:
            return float(round(timestamp))
        return float(ordinal)

    def _episode_td_variance(self, exp) -> float:
        history = getattr(exp, "td_history_snapshot", None)
        if isinstance(history, list) and len(history) > 1:
            try:
                values = [float(value) for value in history]
                td_error_snapshot = getattr(exp, "td_error_snapshot", None)
                if td_error_snapshot is not None and not math.isclose(
                    values[-1], float(td_error_snapshot), rel_tol=0.0, abs_tol=1e-12
                ):
                    # Snapshot changed externally; keep explicit variance snapshot until history syncs.
                    raise ValueError("stale_td_history")
                mean_v = sum(values) / float(len(values))
                variance_v = sum((value - mean_v) ** 2 for value in values) / float(len(values))
                return max(0.0, variance_v)
            except Exception:
                pass
        if hasattr(exp, "td_variance_snapshot"):
            try:
                return max(0.0, float(getattr(exp, "td_variance_snapshot")))
            except Exception:
                pass
        return 0.0

    def _episode_salience(self, exp) -> float:
        try:
            value = float(getattr(exp, "replay_salience", abs(float(getattr(exp, "reward", 0.0)))))
        except Exception:
            value = 0.0
        return max(0.0, min(1.0, value))

    def _episode_importance(self, exp) -> float:
        try:
            value = float(getattr(exp, "replay_importance", 0.0))
        except Exception:
            value = 0.0
        return max(0.0, min(1.0, value))

    def _episode_confidence_score(self, exp) -> float:
        try:
            value = float(
                getattr(
                    exp,
                    "expectation_confidence_score",
                    getattr(exp, "confidence_score", 0.0),
                )
            )
        except Exception:
            value = 0.0
        return max(0.0, min(1.0, value))

    def _episode_expectation_stability(self, exp) -> float:
        try:
            value = float(
                getattr(
                    exp,
                    "expectation_stability_score",
                    getattr(exp, "stability", 0.0),
                )
            )
        except Exception:
            value = 0.0
        return max(0.0, min(1.0, value))

    def _episode_prediction_shock_flag(self, exp) -> bool:
        try:
            return bool(getattr(exp, "prediction_shock_flag", False))
        except Exception:
            return False

    def _episode_prediction_shock_score(self, exp) -> float:
        if hasattr(exp, "prediction_shock_score"):
            try:
                return max(0.0, min(1.0, float(getattr(exp, "prediction_shock_score"))))
            except Exception:
                pass
        if hasattr(exp, "surprise"):
            try:
                return max(0.0, min(1.0, float(getattr(exp, "surprise"))))
            except Exception:
                pass
        return 1.0 if self._episode_prediction_shock_flag(exp) else 0.0

    def _episode_state_distance(self, exp) -> float:
        override = getattr(exp, "state_distance", None)
        if override is None:
            override = getattr(exp, "normalized_state_delta", None)
        if override is not None:
            return max(0.0, min(1.0, float(override)))

        value_layer = getattr(self, "value_layer", None)
        if value_layer is None:
            return 0.0
        state_snapshot = getattr(exp, "value_state_snapshot", None)
        next_snapshot = getattr(exp, "value_next_state_snapshot", None)
        if isinstance(state_snapshot, dict) and isinstance(next_snapshot, dict):
            try:
                similarity = state_similarity(state_snapshot, next_snapshot, encoder=value_layer.encoder)
                return max(0.0, min(1.0, 1.0 - float(similarity)))
            except Exception:
                return 0.0
        return 0.0

    def _episode_action_stability(self, exp) -> float:
        override = getattr(exp, "action_stability", None)
        if override is None:
            override = getattr(exp, "action_stability_score", None)
        if override is not None:
            return max(0.0, min(1.0, float(override)))

        selector = getattr(self, "selector", None)
        action_id = self._extract_action_id(exp)
        if selector is not None and action_id and hasattr(selector, "get_action_metadata"):
            try:
                meta = selector.get_action_metadata(action_id)
                if isinstance(meta, dict):
                    stability = float(meta.get("stability_score", meta.get("stability", 0.0)))
                    if not bool(meta.get("consolidated", meta.get("consolidation_flag", False))) and stability <= 0.0:
                        return 1.0
                    return max(0.0, min(1.0, stability))
            except Exception:
                pass
        return 1.0

    def _compute_causality_score(self, exp) -> float:
        reward_mag = abs(float(getattr(exp, "reward", 0.0)))
        if reward_mag <= 1e-12:
            reward_mag = abs(float(self._episode_td_mean(exp)))
        state_distance = self._episode_state_distance(exp)
        action_stability = self._episode_action_stability(exp)
        score = reward_mag * (1.0 - state_distance) * action_stability
        return max(0.0, min(1.0, float(score)))

    def _replay_stability_gate(self, exp) -> bool:
        stability_score = self._episode_expectation_stability(exp)
        shock_score = self._episode_prediction_shock_score(exp)
        if shock_score > 0.7:
            return True
        explicit_stability = getattr(exp, "expectation_stability_score", None)
        if explicit_stability is None and not hasattr(exp, "stability_snapshot"):
            return True
        if stability_score < 0.05 and abs(self._episode_td_mean(exp)) > 1e-6:
            return True
        return stability_score > float(getattr(self, "replay_stability_threshold", 0.25))

    def _eligibility_trace_for_depth(self, depth: int) -> float:
        decay = max(0.0, min(1.0, float(getattr(self, "eligibility_lambda", 0.85))))
        trace = decay ** max(0, int(depth))
        return max(0.0, min(1.0, float(trace)))

    def _credit_weight_for_depth(self, depth: int) -> float:
        tau = max(1e-6, float(getattr(self, "credit_decay_tau", 3.0)))
        weight = math.exp(-float(depth) / tau)
        return max(float(getattr(self, "credit_weight_min", 0.05)), float(weight))

    def _assign_reward_anchored_causal_depth(
        self,
        replay_sequence: List,
        credit_window: int,
    ) -> Dict[int, int]:
        """Eligibility depth is the step distance inside one trajectory.

        Sample index is not a substitute: a replay subsample can skip steps
        and can mix trajectories. Within a trajectory the anchor is still the
        strongest reward, then the strongest stored TD or shock.
        """
        if not replay_sequence:
            return {}

        reward_threshold = max(0.0, float(getattr(self, "reward_anchor_threshold", 0.1)))
        td_threshold = max(
            0.0,
            float(getattr(self, "td_anchor_threshold", getattr(self, "td_threshold", 0.12))),
        )
        window = max(0, int(credit_window))
        groups: Dict[str, List[Tuple[int, object]]] = {}
        for idx, exp in enumerate(replay_sequence):
            groups.setdefault(self._trajectory_group_key(exp), []).append((idx, exp))

        depth_by_exp: Dict[int, int] = {}
        for members in groups.values():
            positioned = [
                (self._trajectory_position(exp, idx), idx, exp) for idx, exp in members
            ]
            positioned.sort(key=lambda item: (item[0], item[1]))
            explicit_reward_anchor = None
            explicit_reward_mag = -1.0
            td_anchor_pos = None
            td_anchor_mag = -1.0
            for pos, _idx, exp in positioned:
                reward_mag = abs(float(getattr(exp, "reward", 0.0)))
                if reward_mag >= reward_threshold:
                    if reward_mag >= explicit_reward_mag:
                        explicit_reward_mag = reward_mag
                        explicit_reward_anchor = pos
                    continue
                td_mag = abs(float(self._episode_td_mean(exp)))
                shock_flag = bool(self._episode_prediction_shock_flag(exp))
                if td_mag >= td_threshold or shock_flag:
                    anchor_mag = max(td_mag, 1.0 if shock_flag else 0.0)
                    if anchor_mag >= td_anchor_mag:
                        td_anchor_mag = anchor_mag
                        td_anchor_pos = pos

            if explicit_reward_anchor is not None:
                reward_anchor_pos = explicit_reward_anchor
            elif td_anchor_pos is not None:
                reward_anchor_pos = td_anchor_pos
            else:
                reward_anchor_pos = positioned[len(positioned) // 2][0]

            for pos, _idx, exp in positioned:
                distance = abs(float(pos) - float(reward_anchor_pos))
                depth = int(min(max(0, int(round(distance))), window))
                depth_by_exp[id(exp)] = depth
        return depth_by_exp

    def _replay_state_key(self, exp) -> str:
        state_key = str(getattr(exp, "value_state_key", "")).strip()
        if not state_key:
            state_snapshot = getattr(exp, "value_state_snapshot", None)
            value_layer = getattr(self, "value_layer", None)
            if value_layer is not None and isinstance(state_snapshot, dict):
                try:
                    state_key = value_layer.encoder.encode(state_snapshot)
                except Exception:
                    state_key = ""
        action_id = self._extract_action_id(exp)
        return f"{state_key}|{action_id}".strip("|")

    def _episode_arousal_score(self, exp) -> Optional[float]:
        arousal_raw: Optional[float] = None
        if hasattr(exp, "arousal"):
            try:
                arousal_raw = float(getattr(exp, "arousal"))
            except Exception:
                arousal_raw = None
        if arousal_raw is None and hasattr(exp, "stability_snapshot"):
            try:
                snapshot = getattr(exp, "stability_snapshot")
                if isinstance(snapshot, dict):
                    emotional_state = snapshot.get("emotional_state", {})
                    if isinstance(emotional_state, dict) and "arousal" in emotional_state:
                        arousal_raw = float(emotional_state.get("arousal", 0.0))
                    elif "arousal" in snapshot:
                        arousal_raw = float(snapshot.get("arousal", 0.0))
            except Exception:
                arousal_raw = None
        if arousal_raw is None and hasattr(exp, "intensity"):
            try:
                # Intensity is stored in [0, 2], convert to normalized arousal [0, 1].
                arousal_raw = float(getattr(exp, "intensity")) / 2.0
            except Exception:
                arousal_raw = None
        if arousal_raw is None:
            return None
        return max(0.0, min(1.0, arousal_raw))

    def _episode_consolidation_probability(self, exp) -> Optional[float]:
        if not hasattr(exp, "consolidation_probability"):
            return None
        try:
            value = float(getattr(exp, "consolidation_probability"))
        except Exception:
            return None
        return max(0.0, min(1.0, value))

    def _episode_replay_priority(self, exp) -> Optional[float]:
        if hasattr(exp, "replay_priority"):
            try:
                return max(0.0, float(getattr(exp, "replay_priority")))
            except Exception:
                pass
        if hasattr(exp, "td_abs_snapshot"):
            try:
                return max(0.0, float(getattr(exp, "td_abs_snapshot")))
            except Exception:
                pass
        if hasattr(exp, "td_error_snapshot"):
            try:
                return max(0.0, abs(float(getattr(exp, "td_error_snapshot"))))
            except Exception:
                pass
        return None

    def _compute_phase_aggregates(self, rows: List[Dict[str, float]], theta_shock_high: float) -> Dict[str, float]:
        if not rows:
            return {
                "count": 0.0,
                "mean_confidence": 0.0,
                "mean_stability": 0.0,
                "mean_shock": 0.0,
                "mean_arousal": 0.0,
                "mean_consolidation_prob": 0.0,
                "shock_fraction_high": 0.0,
            }
        count = float(len(rows))
        mean_confidence = sum(float(row["confidence"]) for row in rows) / count
        mean_stability = sum(float(row["stability"]) for row in rows) / count
        mean_shock = sum(float(row["shock"]) for row in rows) / count
        mean_arousal = sum(float(row["arousal"]) for row in rows) / count
        mean_consolidation_prob = sum(float(row["consolidation_probability"]) for row in rows) / count
        shock_fraction_high = (
            sum(1.0 for row in rows if float(row["shock"]) > float(theta_shock_high)) / count
        )
        return {
            "count": count,
            "mean_confidence": max(0.0, min(1.0, mean_confidence)),
            "mean_stability": max(0.0, min(1.0, mean_stability)),
            "mean_shock": max(0.0, mean_shock),
            "mean_arousal": max(0.0, min(1.0, mean_arousal)),
            "mean_consolidation_prob": max(0.0, min(1.0, mean_consolidation_prob)),
            "shock_fraction_high": max(0.0, min(1.0, shock_fraction_high)),
        }

    def _validate_phase_thresholds(self, thresholds: Dict[str, float]) -> None:
        if float(thresholds["theta_arousal_low"]) >= float(thresholds["theta_arousal_high"]):
            raise ValueError("Hard Constraint violation: theta_arousal_low must be < theta_arousal_high")
        if float(thresholds["theta_shock_low"]) >= float(thresholds["theta_shock_high"]):
            raise ValueError("Hard Constraint violation: theta_shock_low must be < theta_shock_high")

    def _classify_sleep_phase(self, aggregates: Dict[str, float], thresholds: Dict[str, float]) -> str:
        if float(aggregates.get("count", 0.0)) <= 0.0:
            return "TRANSITIONAL"

        is_sws = (
            float(aggregates["mean_arousal"]) < float(thresholds["theta_arousal_low"])
            and float(aggregates["mean_shock"]) < float(thresholds["theta_shock_low"])
            and float(aggregates["mean_confidence"]) > float(thresholds["theta_conf_high"])
            and float(aggregates["mean_consolidation_prob"]) > float(thresholds["theta_cons_high"])
        )
        if is_sws:
            return "SWS"

        is_rem = (
            float(aggregates["mean_arousal"]) > float(thresholds["theta_arousal_high"])
            or float(aggregates["mean_shock"]) > float(thresholds["theta_shock_high"])
            or float(aggregates["shock_fraction_high"]) > 0.25
        )
        if is_rem:
            return "REM"
        return "TRANSITIONAL"

    def _episode_observed_outcome(self, exp) -> float:
        if hasattr(exp, "feedback_rating"):
            try:
                # ratings are in [-2, 2], normalize to [-1, 1]
                return max(-1.0, min(1.0, float(getattr(exp, "feedback_rating")) / 2.0))
            except Exception:
                pass
        try:
            return max(-1.0, min(1.0, float(getattr(exp, "reward", 0.0))))
        except Exception:
            return 0.0

    def _episode_predicted_outcome(self, exp) -> float:
        if hasattr(exp, "expected_reward_mean"):
            try:
                return max(-1.0, min(1.0, float(getattr(exp, "expected_reward_mean"))))
            except Exception:
                pass
        return 0.0

    def _episode_ach_effective(self, exp) -> float:
        try:
            ach_snapshot = max(0.0, min(1.0, float(getattr(exp, "acetylcholine_snapshot", 0.0))))
        except Exception:
            ach_snapshot = 0.0
        reference = getattr(exp, "acetylcholine_mean_snapshot", None)
        if reference is None:
            reference = getattr(getattr(self, "neuromodulators", None), "ach_baseline", 0.1)
        try:
            ach_reference = max(0.0, min(1.0, float(reference)))
        except (TypeError, ValueError):
            ach_reference = 0.1
        return max(0.0, min(1.0, ach_snapshot - ach_reference))

    def _episode_encoding_strength(self, exp) -> float:
        try:
            encoding_strength = float(getattr(exp, "encoding_strength", getattr(exp, "intensity", 0.0)))
        except Exception:
            encoding_strength = 0.0
        return max(0.0, min(3.0, encoding_strength))

    def _compute_consolidation_score(self, exp) -> float:
        td_abs = abs(float(self._episode_td_mean(exp)))
        salience = self._episode_salience(exp)
        importance = self._episode_importance(exp)
        ach_effective = self._episode_ach_effective(exp)
        # Normalize to 0..1 for scoring.
        encoding_norm = min(1.0, self._episode_encoding_strength(exp) / 3.0)
        score = (
            (float(getattr(self, "w_td", 0.45)) * td_abs)
            + (float(getattr(self, "w_salience", 0.20)) * salience)
            + (float(getattr(self, "w_importance", 0.20)) * importance)
            + (float(getattr(self, "w_ach", 0.10)) * ach_effective)
            + (float(getattr(self, "w_encoding", 0.05)) * encoding_norm)
        )
        # EDPC: confidence/stability produce a separate consolidation weight.
        # Blend it with the legacy weighted score for backward compatibility.
        consolidation_weight = max(
            0.0,
            min(1.0, float(getattr(exp, "consolidation_weight", 0.0))),
        )
        blend = max(0.0, min(1.0, float(getattr(self, "edpc_consolidation_blend", 0.5))))
        score = ((1.0 - blend) * score) + (blend * consolidation_weight)
        consolidation_cap = max(0.05, float(getattr(self, "consolidation_cap", 1.0)))
        return max(0.0, min(score, consolidation_cap))

    def _filter_candidates_for_consolidation(
        self,
        candidates: List,
        value_variance_ratio: float,
    ) -> Tuple[List, Dict[str, int]]:
        filtered: List = []
        rejection_counts: Dict[str, int] = {
            "rejected_due_to_td_threshold": 0,
            "rejected_due_to_td_variance": 0,
            "rejected_due_to_salience": 0,
            "rejected_due_to_reinforcement": 0,
            "rejected_due_to_variance_gate": 0,
            "rejected_due_to_ach": 0,
            "rejected_due_to_stability": 0,
        }

        td_threshold = max(0.0, float(getattr(self, "td_threshold", 0.12)))
        td_variance_cap = max(0.0, float(getattr(self, "td_variance_cap", 0.25)))
        salience_threshold = max(0.0, min(1.0, float(getattr(self, "salience_threshold", 0.10))))
        min_reinforcement = max(1, int(getattr(self, "min_reinforcement_for_consolidation", 1)))
        ach_min = max(0.0, min(1.0, float(getattr(self, "ach_min_for_consolidation", 0.0))))

        for exp in list(candidates or []):
            td_mean = self._replay_signed_td(exp)
            if abs(td_mean) < td_threshold:
                rejection_counts["rejected_due_to_td_threshold"] += 1
                continue

            td_variance = self._episode_td_variance(exp)
            # A rating changed after consolidation is a fresh observation.
            # The stored TD history still holds the previous reward, so its
            # variance is not the noise of this correction.
            revision_correction = bool(getattr(exp, "consolidated", False)) and not self._consolidation_closed(exp)
            if td_variance > td_variance_cap and not revision_correction:
                rejection_counts["rejected_due_to_td_variance"] += 1
                continue

            salience = self._episode_salience(exp)
            if salience < salience_threshold:
                rejection_counts["rejected_due_to_salience"] += 1
                continue

            reinforcement_count = int(getattr(exp, "reinforcement_count", 0))
            if reinforcement_count < min_reinforcement:
                rejection_counts["rejected_due_to_reinforcement"] += 1
                continue

            # Per-state estimate variance. The cross-state spread in
            # value_variance_ratio is not a rejection reason.
            if self._per_state_variance_gate(exp) <= 0.0:
                rejection_counts["rejected_due_to_variance_gate"] += 1
                continue

            if self._episode_ach_effective(exp) < ach_min:
                rejection_counts["rejected_due_to_ach"] += 1
                continue

            if not self._episode_stability_flag(exp):
                rejection_counts["rejected_due_to_stability"] += 1
                continue

            score = self._compute_consolidation_score(exp)
            exp._sleep_consolidation_score = float(score)
            exp._sleep_variance_gate = float(self._per_state_variance_gate(exp))
            filtered.append(exp)

        return filtered, rejection_counts

    def _select_replay_sample(self, experiences: List, value_variance: Optional[float] = None) -> List:
        if not experiences:
            return []

        budget = max(0, int(self.replay_budget_per_sleep))
        if budget <= 0:
            return []

        variance_snapshot = (
            float(value_variance) if value_variance is not None else float(self._compute_value_variance())
        )
        weighted: List[Tuple[object, float]] = []
        fallback_weighted: List[Tuple[object, float]] = []
        for exp in experiences:
            if not self._replay_stability_gate(exp):
                continue
            causality_score = self._compute_causality_score(exp)
            try:
                exp.causality_score = float(causality_score)
            except Exception:
                pass
            priority = self._compute_replay_priority(exp, value_variance=variance_snapshot)
            if priority > float(self.replay_priority_min):
                if causality_score >= float(getattr(self, "causality_threshold", 0.15)):
                    weighted.append((exp, priority))
                else:
                    replay_priority_override = float(getattr(exp, "replay_priority", 0.0))
                    if replay_priority_override >= 0.9:
                        weighted.append((exp, priority))
                    else:
                        fallback_weighted.append((exp, priority))
        if not weighted:
            if fallback_weighted:
                weighted = fallback_weighted
            else:
                return []

        sample: List = []
        replay_counts: Dict[int, int] = {}
        state_replay_counts: Dict[str, int] = {}
        max_per_episode = max(1, int(self.max_replay_per_episode))
        max_per_state = max(1, int(getattr(self, "max_replay_per_state", 3)))
        replay_temperature = 1.0
        temp_decay = max(0.5, min(0.999, float(getattr(self, "replay_temperature_decay", 0.95))))
        while len(sample) < budget:
            eligible = []
            weights = []
            for exp, priority in weighted:
                key = id(exp)
                if replay_counts.get(key, 0) >= max_per_episode:
                    continue
                state_key = self._replay_state_key(exp)
                if state_key and state_replay_counts.get(state_key, 0) >= max_per_state:
                    continue
                effective_priority = float(priority) * replay_temperature
                if effective_priority <= float(self.replay_priority_min):
                    continue
                eligible.append(exp)
                weights.append(effective_priority)
            if not eligible:
                break
            chosen = self._rng.choices(eligible, weights=weights, k=1)[0]
            sample.append(chosen)
            chosen_key = id(chosen)
            replay_counts[chosen_key] = replay_counts.get(chosen_key, 0) + 1
            chosen_state_key = self._replay_state_key(chosen)
            if chosen_state_key:
                state_replay_counts[chosen_state_key] = state_replay_counts.get(chosen_state_key, 0) + 1
            replay_temperature *= temp_decay
        return sample

    def _compute_replay_priority(self, exp, value_variance: Optional[float] = None) -> float:
        td_snapshot = abs(float(self._replay_signed_td(exp)))
        stability_score = self._episode_expectation_stability(exp)
        shock_flag = 1.0 if self._episode_prediction_shock_flag(exp) else 0.0
        shock_gain = max(0.0, float(getattr(self, "shock_priority_gain", 1.0)))
        shock_multiplier = 1.0 + (shock_flag * shock_gain)
        # Spec priority:
        # abs(delta) * (1 + shock_flag) * (1 - stability_score)
        # with configurable shock gain (default keeps (1 + shock_flag)).
        priority = td_snapshot * shock_multiplier * (1.0 - stability_score)
        # Allow direct EDPC priority snapshot from online phase to influence replay.
        priority = max(priority, max(0.0, float(getattr(exp, "replay_priority", 0.0))))
        if not bool(getattr(self, "edpc_priority_enabled", True)):
            # Backward compatibility for legacy behavior.
            if hasattr(exp, "_sleep_consolidation_score"):
                score = float(getattr(exp, "_sleep_consolidation_score", 0.0))
                priority = max(0.0, score)
            else:
                w1, w2, w3 = self.replay_priority_weights
                salience = self._episode_salience(exp)
                importance = self._episode_importance(exp)
                priority = (float(w1) * td_snapshot) + (float(w2) * salience) + (float(w3) * importance)
        elif hasattr(exp, "_sleep_consolidation_score"):
            score = max(0.0, float(getattr(exp, "_sleep_consolidation_score", 0.0)))
            priority *= (0.5 + (0.5 * min(1.0, score)))
        ach_effective = self._episode_ach_effective(exp)

        # value_variance is the cross-state spread. Priority follows the
        # uncertainty of this state's own estimate instead.
        _ = value_variance
        variance_gate = self._per_state_variance_gate(exp)

        ach_gain = max(0.0, min(2.0, float(getattr(self, "ach_replay_gain", 0.5))))
        priority *= (1.0 + (ach_gain * ach_effective * variance_gate))

        priority_cap = max(float(self.replay_priority_min), float(getattr(self, "replay_priority_cap", 3.0)))
        capped = min(priority, priority_cap)
        # Decision 15 extends this score. The four-term priority is the
        # consolidation order. It is not folded into the capped return:
        # ACh and shock comparisons sit near the cap, and adding |δ| again
        # would flatten them. ``consolidation_order`` reads the spec term.
        try:
            exp.two_tier_replay_priority = float(self.spec_replay_priority(exp))
        except Exception:
            pass
        return capped

    def _apply_replay_td_bg(self, replay_sample: List, value_variance: Optional[float] = None) -> Dict[str, float]:
        """Replay stable Q only. Does not open the learning guard.

        ``Agent.sleep`` / ``sleep_cycle`` already hold the guard. A daytime
        call raises in strict mode and skips the write in production.
        Go/NoGo and habit-channel weights are not updated here (decision 13):
        those move only in the once-per-sleep capture plus compensated step.
        """
        from learning_guard import assert_learning_allowed

        if not assert_learning_allowed("SleepManager._apply_replay_td_bg"):
            return {
                "value_delta_total": 0.0,
                "weight_delta_total": 0.0,
                "total_value_delta_sleep": 0.0,
                "total_bg_delta_sleep": 0.0,
                "sleep_update_count": 0,
                "replay_blocked": False,
                "replays_applied": 0,
                "sleep_update_l2_total": 0.0,
                "mean_consolidation_score": 0.0,
                "eligibility_trace_mean": 0.0,
                "credit_window_usage": 0.0,
                "replay_causality_mean": 0.0,
            }
        return self._apply_replay_td_bg_unlocked(replay_sample, value_variance)

    def _apply_replay_td_bg_unlocked(self, replay_sample: List, value_variance: Optional[float] = None) -> Dict[str, float]:
        value_layer = getattr(self, "value_layer", None)
        if value_layer is None:
            return {
                "value_delta_total": 0.0,
                "weight_delta_total": 0.0,
                "total_value_delta_sleep": 0.0,
                "total_bg_delta_sleep": 0.0,
                "sleep_update_count": 0,
                "replay_blocked": False,
                "replays_applied": 0,
                "sleep_update_l2_total": 0.0,
                "mean_consolidation_score": 0.0,
            }

        stability_index = self._get_global_stability_index()
        stability_gate = max(0.3, min(1.0, float(stability_index)))
        alpha_sleep_effective = self._resolved_alpha_sleep(value_layer, stability_gate)
        td_clip = min(1.0, float(self.td_clip_sleep))
        dopamine_sleep_scale = max(0.0, min(1.0, float(getattr(self, "dopamine_sleep_scale", 0.3))))
        per_update_cap_cfg = float(getattr(self, "per_update_cap", self.delta_value_max_per_sleep))
        per_update_cap_legacy = float(getattr(self, "delta_value_max_per_sleep", per_update_cap_cfg))
        per_update_cap = max(1e-9, min(abs(per_update_cap_cfg), abs(per_update_cap_legacy)))
        global_budget_cfg = float(getattr(self, "global_sleep_update_budget", self.value_total_cap))
        global_budget_legacy = float(getattr(self, "value_total_cap", global_budget_cfg))
        global_sleep_update_budget = max(1e-9, min(abs(global_budget_cfg), abs(global_budget_legacy)))
        max_l2_update_per_cycle = max(
            1e-9, float(getattr(self, "max_l2_update_per_cycle", global_sleep_update_budget))
        )
        # value_variance is retained for callers. Replay no longer scales
        # updates by the spread of V across states.
        _ = value_variance

        value_delta_total = 0.0
        value_delta_sq_total = 0.0
        weight_delta_total = 0.0
        replay_blocked = False
        replays_applied = 0
        consolidation_score_total = 0.0
        initial_sleep_updates = int(getattr(value_layer, "sleep_update_count", 0))

        replay_sequence = list(replay_sample or [])
        replay_sequence.sort(key=lambda item: float(getattr(item, "timestamp", 0.0)))
        credit_window = max(1, int(getattr(self, "credit_window", 6)))
        depth_by_exp = self._assign_reward_anchored_causal_depth(
            replay_sequence=replay_sequence,
            credit_window=credit_window,
        )
        eligibility_map: Dict[int, float] = {}
        credit_weight_map: Dict[int, float] = {}
        for exp in replay_sequence:
            depth = int(depth_by_exp.get(id(exp), credit_window))
            try:
                exp.causal_depth = int(min(depth, credit_window))
            except Exception:
                pass
            if depth >= credit_window:
                continue
            eligibility_map[id(exp)] = float(self._eligibility_trace_for_depth(depth))
            credit_weight_map[id(exp)] = float(self._credit_weight_for_depth(depth))

        eligibility_trace_sum = 0.0
        eligibility_trace_count = 0
        credit_window_hits = 0
        credit_window_total = len(replay_sequence)
        causality_sum = 0.0
        causality_count = 0

        for exp in replay_sequence:
            depth = int(getattr(exp, "causal_depth", credit_window))
            if depth >= credit_window:
                continue
            remaining_value_budget = max(0.0, global_sleep_update_budget - value_delta_total)
            remaining_l2_sq = max(0.0, (max_l2_update_per_cycle ** 2) - value_delta_sq_total)
            if remaining_value_budget <= 0.0:
                replay_blocked = True
                break
            if remaining_l2_sq <= 0.0:
                replay_blocked = True
                break
            td_now = float(self._replay_signed_td(exp))
            if abs(td_now) <= 1e-12:
                continue
            td_error = max(-td_clip, min(td_clip, td_now))

            consolidation_score = float(
                max(0.0, getattr(exp, "_sleep_consolidation_score", self._compute_consolidation_score(exp)))
            )
            stamped_gate = getattr(exp, "_sleep_variance_gate", None)
            if stamped_gate is None:
                variance_gate = self._per_state_variance_gate(exp)
            else:
                variance_gate = max(0.0, min(1.0, float(stamped_gate)))
            eligibility_trace = float(eligibility_map.get(id(exp), 0.0))
            credit_weight = float(credit_weight_map.get(id(exp), 0.0))
            # δ is recomputed above. The step follows that error, scaled by
            # eligibility along the real episode order and the per-state gate.
            delta_v = alpha_sleep_effective * td_error
            delta_v *= eligibility_trace * credit_weight
            delta_v *= variance_gate
            if abs(delta_v) > per_update_cap:
                delta_v = math.copysign(per_update_cap, delta_v)
            if abs(delta_v) > remaining_value_budget:
                delta_v = math.copysign(remaining_value_budget, delta_v)
            remaining_l2 = math.sqrt(remaining_l2_sq)
            if abs(delta_v) > remaining_l2:
                delta_v = math.copysign(remaining_l2, delta_v)
            if abs(delta_v) <= 1e-12:
                continue

            # Build replay snapshots and execute sleep-mode bounded value update.
            state_snapshot = getattr(exp, "value_state_snapshot", None)
            if not isinstance(state_snapshot, dict) or not state_snapshot:
                state_snapshot = {"context_signature": "|".join(exp.path.signature())}

            state_key = str(getattr(exp, "value_state_key", "")).strip()
            if not state_key:
                state_key = value_layer.encoder.encode(state_snapshot)
            current_v = float(value_layer.get_value(state_snapshot))
            value_cap = self._resolved_value_cap()
            new_v = max(-value_cap, min(value_cap, current_v + delta_v))
            value_layer._set_value(state_key, new_v)
            applied_delta = new_v - current_v
            if abs(applied_delta) <= 1e-12:
                continue

            value_delta_total += abs(applied_delta)
            value_delta_sq_total += applied_delta * applied_delta
            consolidation_score_total += consolidation_score
            eligibility_trace_sum += eligibility_trace
            eligibility_trace_count += 1
            credit_window_hits += 1
            try:
                causality_score = float(getattr(exp, "causality_score", 0.0))
            except Exception:
                causality_score = 0.0
            causality_sum += max(0.0, causality_score)
            causality_count += 1
            value_layer.last_state_key = state_key
            value_layer.last_td_error = max(-td_clip, min(td_clip, td_error))
            value_layer.last_reward_raw = 0.0
            value_layer.last_reward_scaled = 0.0
            value_layer.last_delta_raw = float(td_error)
            value_layer.last_delta_modulated = float(value_layer.last_td_error)
            value_layer.last_delta_clipped = float(value_layer.last_td_error)
            value_layer.last_td_was_clipped = False
            value_layer.last_td_clip_value_used = float(td_clip)
            value_layer.last_abs_delta = abs(float(value_layer.last_td_error))
            value_layer.last_delta_sign = int(
                1 if value_layer.last_td_error > 1e-12 else (-1 if value_layer.last_td_error < -1e-12 else 0)
            )
            value_layer.last_tonic_level = float(
                getattr(getattr(value_layer, "td_layer", None), "tonic_level", getattr(value_layer, "last_tonic_level", 0.1))
            )
            try:
                value_layer.last_exploration_delta = float(
                    value_layer.compute_exploration_coupling(
                        td_error=value_layer.last_td_error,
                        baseline_exploration=0.1,
                    )
                )
            except Exception:
                value_layer.last_exploration_delta = 0.0
            value_layer.last_value = new_v
            value_layer.last_dopamine_delta = value_layer.compute_dopamine_delta(value_layer.last_td_error)
            value_layer.last_update_ts = time.time()
            try:
                value_layer._increment_update_counters("sleep")
            except Exception:
                try:
                    value_layer.sleep_update_count = int(getattr(value_layer, "sleep_update_count", 0)) + 1
                    value_layer.update_count = int(getattr(value_layer, "update_count", 0)) + 1
                except Exception:
                    pass
            replays_applied += 1

            # Weak dopamine correction during sleep replay (Phase 5.A.2).
            try:
                neuromodulators = getattr(self, "neuromodulators", None)
                if neuromodulators is not None and hasattr(neuromodulators, "apply_dopamine_delta"):
                    dopamine_delta_sleep = value_layer.compute_dopamine_delta(value_layer.last_td_error) * dopamine_sleep_scale
                    neuromodulators.apply_dopamine_delta(dopamine_delta_sleep)
            except Exception:
                pass

            # Channel Go/NoGo and habit weights are not part of replay.
            # They move once per episode in the capture + compensated step.
            if value_delta_total >= global_sleep_update_budget - 1e-12:
                replay_blocked = True
                break

        value_layer.last_td_error = max(-td_clip, min(td_clip, float(getattr(value_layer, "last_td_error", 0.0))))
        value_layer.last_delta_clipped = float(value_layer.last_td_error)
        value_layer.last_td_was_clipped = False
        value_layer.last_td_clip_value_used = float(td_clip)
        value_layer.last_abs_delta = abs(float(value_layer.last_td_error))
        value_layer.last_delta_sign = int(
            1 if value_layer.last_td_error > 1e-12 else (-1 if value_layer.last_td_error < -1e-12 else 0)
        )
        value_cap = self._resolved_value_cap()
        value_layer.last_value = max(-value_cap, min(value_cap, float(getattr(value_layer, "last_value", 0.0))))
        sleep_updates_after = int(getattr(value_layer, "sleep_update_count", 0))
        if value_delta_total >= global_sleep_update_budget - 1e-12:
            replay_blocked = True
        mean_consolidation_score = (
            float(consolidation_score_total) / float(replays_applied) if replays_applied > 0 else 0.0
        )
        sleep_update_l2_total = math.sqrt(max(0.0, float(value_delta_sq_total)))
        eligibility_trace_mean = (
            float(eligibility_trace_sum) / float(eligibility_trace_count)
            if eligibility_trace_count > 0
            else 0.0
        )
        credit_window_usage = (
            float(credit_window_hits) / float(credit_window_total)
            if credit_window_total > 0
            else 0.0
        )
        replay_causality_mean = (
            float(causality_sum) / float(causality_count) if causality_count > 0 else 0.0
        )
        return {
            "value_delta_total": value_delta_total,
            "weight_delta_total": weight_delta_total,
            "total_value_delta_sleep": value_delta_total,
            "total_bg_delta_sleep": weight_delta_total,
            "sleep_update_count": max(0, sleep_updates_after - initial_sleep_updates),
            "replay_blocked": replay_blocked,
            "replays_applied": replays_applied,
            "sleep_update_l2_total": sleep_update_l2_total,
            "mean_consolidation_score": mean_consolidation_score,
            "eligibility_trace_mean": eligibility_trace_mean,
            "credit_window_usage": credit_window_usage,
            "replay_causality_mean": replay_causality_mean,
        }

    def _offline_reward(self, exp) -> float:
        committed = getattr(exp, "td_committed_reward", None)
        if committed is not None:
            try:
                reward = float(committed)
                if math.isfinite(reward):
                    return max(-1.0, min(1.0, reward))
            except (TypeError, ValueError):
                pass
        try:
            reward = float(getattr(exp, "reward", 0.0))
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(reward):
            return 0.0
        return max(-1.0, min(1.0, reward))

    def _offline_current_value(self, exp) -> float:
        value_layer = getattr(self, "value_layer", None)
        if value_layer is None:
            return 0.0
        snapshot = getattr(exp, "value_state_snapshot", None)
        if isinstance(snapshot, dict) and snapshot:
            try:
                return float(value_layer.get_value(snapshot))
            except Exception:
                pass
        state_key = str(getattr(exp, "value_state_key", "") or "").strip()
        if state_key:
            try:
                return float(value_layer._get_value(state_key))
            except Exception:
                return 0.0
        return 0.0

    def _offline_successor_value(self, exp) -> float:
        """Bootstrap V(s'). Terminal transitions use 0; otherwise max_a Q(s', a)."""
        if bool(getattr(exp, "value_terminal", False)):
            return 0.0
        value_layer = getattr(self, "value_layer", None)
        if value_layer is None:
            return 0.0
        next_snapshot = getattr(exp, "value_next_state_snapshot", None)
        if not isinstance(next_snapshot, dict) or not next_snapshot:
            next_snapshot = getattr(exp, "value_state_snapshot", None)
        if not isinstance(next_snapshot, dict) or not next_snapshot:
            return 0.0

        actions: List[str] = []
        selector = getattr(self, "selector", None)
        if selector is not None:
            try:
                actions = [str(action) for action in list(getattr(selector, "actions", []) or [])]
            except Exception:
                actions = []
        own_action = self._extract_action_id(exp)
        if own_action and own_action not in actions:
            actions.append(str(own_action))

        best = None
        if actions:
            for action in actions:
                snap = dict(next_snapshot)
                snap["action"] = action
                try:
                    value = float(value_layer.get_value(snap))
                except Exception:
                    continue
                if best is None or value > best:
                    best = value
        if best is not None:
            return float(best)
        try:
            return float(value_layer.get_value(next_snapshot))
        except Exception:
            return 0.0

    def _compute_offline_td_error(self, exp) -> float:
        """δ = r + γ V(s') − Q(s, a) on the current table.

        The encoding-time td_error_snapshot is not returned. Q(s, a) is the
        value of the stored state snapshot (it includes the action). V(s') is
        0 on a terminal transition and max_a Q(s', a) otherwise.
        """
        value_layer = getattr(self, "value_layer", None)
        if value_layer is None:
            return 0.0
        try:
            reward = float(self._offline_reward(exp))
            gamma = float(getattr(value_layer, "gamma_default", 0.95))
            current_q = float(self._offline_current_value(exp))
            successor = float(self._offline_successor_value(exp))
        except Exception:
            return 0.0
        if not math.isfinite(gamma):
            gamma = 0.95
        gamma = max(0.0, min(0.999, gamma))
        if bool(getattr(exp, "value_terminal", False)):
            successor = 0.0
        delta = reward + (gamma * successor) - current_q
        if not math.isfinite(delta):
            return 0.0
        return float(delta)

    def _extract_action_id(self, exp) -> Optional[str]:
        replay_action = str(getattr(exp, "replay_action_id", "")).strip()
        if replay_action:
            return replay_action
        try:
            for event_name in exp.path.signature():
                if str(event_name).startswith("action:"):
                    return str(event_name).split(":", 1)[1]
        except Exception:
            return None
        return None

    def _apply_semantic_action_consolidation(
        self,
        replay_sample: List,
        *,
        sleep_state: bool = False,
    ) -> Dict[str, Any]:
        base_stats: Dict[str, Any] = {
            "sac_episodes_gated": 0,
            "sac_actions_considered": 0,
            "sac_actions_updated": 0,
            "sac_actions_skipped": 0,
            "sac_rejected_confidence": 0,
            "sac_rejected_stability": 0,
            "sac_rejected_shock": 0,
            "sac_rejected_consolidation_probability": 0,
            "sac_rejected_replay_count": 0,
            "sac_rejected_min_weight": 0,
            "sac_rejected_shock_mean": 0,
            "sac_rejected_divergence": 0,
            "sac_rejected_missing_signal": 0,
            "semantic_drift_rate": 0.0,
            "stability_growth_rate": 0.0,
            "divergence_reduction_index": 0.0,
            "overconfidence_index": 0.0,
            "sac_phase": "TRANSITIONAL",
            "phase_distribution": {"SWS": 0, "REM": 0, "TRANSITIONAL": 0},
            "sac_phase_sws": 0,
            "sac_phase_rem": 0,
            "sac_phase_transitional": 0,
            "mean_sigma_change": 0.0,
            "mean_stability_change": 0.0,
            "structural_alert_count": 0,
        }
        if not sleep_state:
            raise RuntimeError("Semantic Action Consolidation is sleep-only.")

        alpha_slow = float(getattr(self, "sac_alpha_slow", 0.01))
        if alpha_slow > 0.01 + 1e-12:
            raise ValueError("Hard Constraint violation: sac_alpha_slow must be <= 0.01")

        selector = getattr(self, "selector", None)
        if selector is None:
            self.last_sac_stats = dict(base_stats)
            return dict(base_stats)

        alpha_base_raw = float(getattr(self, "sac_alpha_base", alpha_slow))
        if alpha_base_raw > 0.01 + 1e-12:
            raise ValueError("Hard Constraint violation: sac_alpha_base must be <= 0.01")
        alpha_base = max(0.001, alpha_base_raw)
        alpha_sigma = max(0.0, float(getattr(self, "sac_alpha_sigma", alpha_base)))
        theta_conf = max(0.0, min(1.0, float(getattr(self, "sac_theta_conf", 0.6))))
        theta_stab = max(0.0, min(1.0, float(getattr(self, "sac_theta_stab", 0.5))))
        theta_shock = max(0.0, min(1.0, float(getattr(self, "sac_theta_shock", 0.4))))
        theta_cons = max(0.0, min(1.0, float(getattr(self, "sac_theta_cons", 0.5))))
        theta_min_weight = max(0.0, float(getattr(self, "sac_theta_min_weight", 0.05)))
        min_count = max(1, int(getattr(self, "sac_replay_min_count", 3)))
        sigma_floor = max(0.0, float(getattr(self, "sac_sigma_floor", 0.01)))
        sigma_decay_sws = max(0.0, min(0.99, float(getattr(self, "sac_sigma_decay_sws", 0.05))))
        epsilon_var_rem = max(0.0, float(getattr(self, "sac_epsilon_var_rem", 0.01)))
        epsilon_div = max(0.0, float(getattr(self, "sac_epsilon_divergence", 0.08)))
        beta_stability_sws = max(0.0, min(1.0, float(getattr(self, "sac_beta_stability_sws", 0.03))))
        delta_rem = max(0.0, min(1.0, float(getattr(self, "sac_delta_rem", 0.08))))
        stability_floor_rem = max(0.0, min(1.0, float(getattr(self, "sac_stability_floor_rem", 0.2))))
        lambda_sws = max(0.0, min(1.0, float(getattr(self, "sac_lambda_sws", 0.20))))
        lambda_rem = max(0.0, min(1.0, float(getattr(self, "sac_lambda_rem", 0.08))))
        if lambda_sws <= lambda_rem:
            raise ValueError("Hard Constraint violation: sac_lambda_sws must be > sac_lambda_rem")
        semantic_conf_step_cap = max(
            0.0,
            min(1.0, float(getattr(self, "sac_semantic_confidence_step_cap", 0.05))),
        )
        structural_alert_reset_cycles = max(
            1,
            int(getattr(self, "sac_structural_alert_reset_cycles", 3)),
        )
        shock_block_threshold = max(0.0, min(1.0, float(getattr(self, "sac_shock_block_threshold", 0.6))))
        success_threshold = float(getattr(self, "sac_success_threshold", 0.0))
        theta_structural = max(0.0, min(1.0, float(getattr(self, "sac_theta_structural", 0.80))))
        local_phase_mode = bool(getattr(self, "local_phase_mode", False))

        phase_thresholds = {
            "theta_arousal_low": max(0.0, min(1.0, float(getattr(self, "sac_theta_arousal_low", 0.35)))),
            "theta_arousal_high": max(0.0, min(1.0, float(getattr(self, "sac_theta_arousal_high", 0.65)))),
            "theta_shock_low": max(0.0, float(getattr(self, "sac_theta_shock_low", 0.20))),
            "theta_shock_high": max(0.0, float(getattr(self, "sac_theta_shock_high", 0.40))),
            "theta_conf_high": max(0.0, min(1.0, float(getattr(self, "sac_theta_conf_high", 0.60)))),
            "theta_cons_high": max(0.0, min(1.0, float(getattr(self, "sac_theta_cons_high", 0.50)))),
            "theta_stability_high": max(0.0, min(1.0, float(getattr(self, "sac_theta_stability_high", 0.50)))),
        }
        self._validate_phase_thresholds(phase_thresholds)

        grouped: Dict[str, List[Dict[str, float]]] = {}

        for exp in list(replay_sample or []):
            action_id = self._extract_action_id(exp)
            if not action_id:
                continue

            confidence = self._episode_confidence_score(exp)
            stability = self._episode_expectation_stability(exp)
            shock_score = self._episode_prediction_shock_score(exp)
            arousal = self._episode_arousal_score(exp)
            consolidation_probability = self._episode_consolidation_probability(exp)
            replay_priority = self._episode_replay_priority(exp)

            if arousal is None or consolidation_probability is None or replay_priority is None:
                base_stats["sac_rejected_missing_signal"] += 1
                continue
            if confidence <= theta_conf:
                base_stats["sac_rejected_confidence"] += 1
                continue
            if stability <= theta_stab:
                base_stats["sac_rejected_stability"] += 1
                continue
            if shock_score >= theta_shock:
                base_stats["sac_rejected_shock"] += 1
                continue
            if consolidation_probability <= theta_cons:
                base_stats["sac_rejected_consolidation_probability"] += 1
                continue

            quality_weight = max(0.0, confidence * stability * (1.0 - shock_score))
            weight = max(0.0, float(replay_priority)) * quality_weight
            if weight <= 0.0:
                base_stats["sac_rejected_min_weight"] += 1
                continue

            observed_outcome = self._episode_observed_outcome(exp)
            predicted_outcome = self._episode_predicted_outcome(exp)
            td_error = float(self._episode_td_mean(exp))
            success_flag = 1.0 if observed_outcome >= success_threshold else 0.0

            row = {
                "weight": weight,
                "confidence": confidence,
                "stability": stability,
                "shock": shock_score,
                "arousal": arousal,
                "consolidation_probability": consolidation_probability,
                "td_error": td_error,
                "observed": observed_outcome,
                "predicted": predicted_outcome,
                "success": success_flag,
            }
            grouped.setdefault(str(action_id), []).append(row)
            base_stats["sac_episodes_gated"] += 1

        phase_rows: List[Dict[str, float]] = []
        for action_id, rows in grouped.items():
            replay_count = len(rows)
            if replay_count < min_count:
                continue
            weight_sum = sum(float(row["weight"]) for row in rows)
            if weight_sum < theta_min_weight:
                continue

            mean_shock = sum(float(row["shock"]) * float(row["weight"]) for row in rows) / float(weight_sum)
            if mean_shock > shock_block_threshold:
                continue

            mu_observed = sum(float(row["observed"]) * float(row["weight"]) for row in rows) / float(weight_sum)
            existing = getattr(selector, "action_metadata", {})
            if isinstance(existing, dict) and action_id in existing:
                meta_probe = dict(existing.get(action_id, {}))
            elif hasattr(selector, "get_action_metadata"):
                meta_probe = dict(selector.get_action_metadata(action_id))
            else:
                meta_probe = {}
            mu_old = float(meta_probe.get("expected_effect_mean", 0.0))
            if abs(mu_old - mu_observed) <= epsilon_div:
                continue
            phase_rows.extend(rows)

        global_aggregates = self._compute_phase_aggregates(
            phase_rows,
            phase_thresholds["theta_shock_high"],
        )
        global_phase = self._classify_sleep_phase(global_aggregates, phase_thresholds)
        base_stats["sac_phase"] = global_phase

        drift_sum = 0.0
        stability_growth_sum = 0.0
        divergence_before_sum = 0.0
        divergence_after_sum = 0.0
        overconfidence_sum = 0.0
        sigma_change_sum = 0.0
        stability_change_sum = 0.0
        structural_alert_count = 0

        for action_id, rows in grouped.items():
            base_stats["sac_actions_considered"] += 1
            replay_count = len(rows)
            if replay_count < min_count:
                base_stats["sac_rejected_replay_count"] += 1
                continue

            weights = [float(row["weight"]) for row in rows]
            weight_sum = sum(weights)
            if weight_sum < theta_min_weight:
                base_stats["sac_rejected_min_weight"] += 1
                continue

            def _wmean(key: str) -> float:
                return sum(float(row[key]) * float(row["weight"]) for row in rows) / float(weight_sum)

            def _wvar(key: str, mean_value: float) -> float:
                return sum(
                    float(row["weight"]) * ((float(row[key]) - mean_value) ** 2)
                    for row in rows
                ) / float(weight_sum)

            local_aggregates = self._compute_phase_aggregates(rows, phase_thresholds["theta_shock_high"])
            phase = self._classify_sleep_phase(local_aggregates, phase_thresholds) if local_phase_mode else global_phase

            phase_flags = (
                phase == "SWS",
                phase == "REM",
                phase == "TRANSITIONAL",
            )
            if sum(1 for flag in phase_flags if flag) != 1:
                raise RuntimeError("Hard Constraint violation: exactly one sleep phase rule per action")

            mu_observed = _wmean("observed")
            sigma_observed = max(0.0, _wvar("observed", mu_observed))
            mean_confidence = max(0.0, min(1.0, _wmean("confidence")))
            mean_stability = max(0.0, min(1.0, _wmean("stability")))
            mean_shock = max(0.0, _wmean("shock"))
            mean_cons = max(0.0, min(1.0, _wmean("consolidation_probability")))

            if mean_shock > shock_block_threshold:
                base_stats["sac_rejected_shock_mean"] += 1
                continue

            weighted_successes = max(0.0, sum(float(row["weight"]) * float(row["success"]) for row in rows))
            weighted_failures = max(0.0, weight_sum - weighted_successes)
            td_semantic = _wmean("td_error")
            td_variance = _wvar("td_error", td_semantic)

            existing = getattr(selector, "action_metadata", {})
            if isinstance(existing, dict) and action_id in existing:
                meta = dict(existing.get(action_id, {}))
            elif hasattr(selector, "get_action_metadata"):
                meta = dict(selector.get_action_metadata(action_id))
            else:
                meta = {}

            mu_old = float(meta.get("expected_effect_mean", 0.0))
            if abs(mu_old - mu_observed) <= epsilon_div:
                base_stats["sac_rejected_divergence"] += 1
                continue

            sigma_old = max(0.0, float(meta.get("expected_effect_variance", 0.25)))
            success_alpha_old = max(1e-6, float(meta.get("success_alpha", 1.0)))
            success_beta_old = max(1e-6, float(meta.get("success_beta", 1.0)))
            semantic_conf_old = max(0.0, min(1.0, float(meta.get("semantic_confidence", 0.0))))
            stability_old = max(
                0.0,
                min(1.0, float(meta.get("stability_score", semantic_conf_old))),
            )

            base_stats["phase_distribution"][phase] += 1
            alpha_mu = alpha_base
            if phase == "SWS":
                alpha_mu = alpha_base * 0.5
            elif phase == "REM":
                alpha_mu = alpha_base * 1.5

            mu_new = mu_old + (alpha_mu * (mu_observed - mu_old))
            sigma_new = sigma_old + (alpha_sigma * (sigma_observed - sigma_old))
            if phase == "SWS":
                sigma_new *= (1.0 - sigma_decay_sws)
                if mean_shock <= phase_thresholds["theta_shock_low"] and sigma_new > sigma_old:
                    sigma_new = sigma_old
            elif phase == "REM":
                sigma_new += epsilon_var_rem
                if mean_shock >= phase_thresholds["theta_shock_high"] and sigma_new < sigma_old:
                    sigma_new = sigma_old
            sigma_new = max(sigma_floor, sigma_new)

            if phase == "SWS":
                stability_new = min(1.0, stability_old + beta_stability_sws)
                stability_new = max(stability_new, stability_old)
            elif phase == "REM":
                stability_new = max(stability_floor_rem, stability_old * (1.0 - delta_rem))
                stability_new = min(stability_new, stability_old)
            else:
                stability_new = stability_old

            success_alpha_new = max(1e-6, success_alpha_old + (alpha_base * weighted_successes))
            success_beta_new = max(1e-6, success_beta_old + (alpha_base * weighted_failures))
            failure_probability = success_beta_new / max(1e-6, success_alpha_new + success_beta_new)
            risk_estimate_new = max(0.0, min(1.0, sigma_new * failure_probability))

            semantic_signal = max(
                0.0,
                min(
                    1.0,
                    (0.4 * mean_confidence)
                    + (0.2 * mean_stability)
                    + (0.2 * mean_cons)
                    + (0.2 * min(1.0, float(replay_count) / 10.0)),
                ),
            )
            if phase == "SWS":
                lambda_phase = lambda_sws
            elif phase == "REM":
                lambda_phase = lambda_rem
            else:
                lambda_phase = 0.5 * (lambda_sws + lambda_rem)
            semantic_conf_delta = lambda_phase * (semantic_signal - semantic_conf_old)
            if semantic_conf_step_cap > 0.0:
                semantic_conf_delta = max(
                    -semantic_conf_step_cap,
                    min(semantic_conf_step_cap, semantic_conf_delta),
                )
            semantic_conf_new = max(
                0.0,
                min(1.0, semantic_conf_old + semantic_conf_delta),
            )

            meta["expected_effect_mean"] = float(mu_new)
            meta["expected_effect_variance"] = float(sigma_new)
            meta["success_alpha"] = float(success_alpha_new)
            meta["success_beta"] = float(success_beta_new)
            meta["risk_estimate"] = float(risk_estimate_new)
            meta["semantic_confidence"] = float(semantic_conf_new)
            meta["stability_score"] = float(stability_new)
            meta["td_semantic"] = float(td_semantic)
            meta["td_mean"] = float(td_semantic)
            meta["td_variance"] = float(td_variance)
            meta["observed_outcome_mean"] = float(mu_observed)
            meta["predicted_outcome_mean"] = float(_wmean("predicted"))
            meta["confidence"] = float(max(0.0, min(1.0, semantic_conf_new)))
            meta["stability"] = float(max(0.0, min(1.0, stability_new)))
            meta["consolidated"] = True
            meta["consolidation_flag"] = True
            meta["sac_phase"] = str(phase)
            meta["applied_sws_rule"] = bool(phase == "SWS")
            meta["applied_rem_rule"] = bool(phase == "REM")
            meta["applied_transitional_rule"] = bool(phase == "TRANSITIONAL")

            has_structural_shock = bool(
                phase == "REM" and any(float(row["shock"]) > theta_structural for row in rows)
            )
            if has_structural_shock:
                meta["structural_alert"] = True
                meta["structural_alert_calm_streak"] = 0
                structural_alert_count += 1
            else:
                was_alert = bool(meta.get("structural_alert", False))
                if was_alert:
                    calm_streak = max(0, int(meta.get("structural_alert_calm_streak", 0))) + 1
                    if calm_streak >= structural_alert_reset_cycles:
                        meta["structural_alert"] = False
                        meta["structural_alert_calm_streak"] = 0
                    else:
                        meta["structural_alert"] = True
                        meta["structural_alert_calm_streak"] = int(calm_streak)
                else:
                    meta["structural_alert"] = False
                    meta["structural_alert_calm_streak"] = 0

            if hasattr(selector, "set_action_metadata"):
                selector.set_action_metadata(action_id, meta)
            else:
                if not hasattr(selector, "action_metadata") or not isinstance(selector.action_metadata, dict):
                    selector.action_metadata = {}
                selector.action_metadata[str(action_id)] = dict(meta)

            base_stats["sac_actions_updated"] += 1
            drift_sum += abs(mu_new - mu_old)
            stability_growth_sum += (semantic_conf_new - semantic_conf_old)
            divergence_before_sum += abs(mu_old - mu_observed)
            divergence_after_sum += abs(mu_new - mu_observed)
            overconfidence_sum += max(0.0, semantic_conf_new - (1.0 - risk_estimate_new))
            sigma_change_sum += (sigma_new - sigma_old)
            stability_change_sum += (stability_new - stability_old)

        considered = max(1, int(base_stats["sac_actions_considered"]))
        updated = max(1, int(base_stats["sac_actions_updated"]))
        base_stats["sac_actions_skipped"] = int(base_stats["sac_actions_considered"] - base_stats["sac_actions_updated"])
        base_stats["semantic_drift_rate"] = float(drift_sum) / float(updated)
        base_stats["stability_growth_rate"] = float(stability_growth_sum) / float(updated)
        base_stats["mean_sigma_change"] = float(sigma_change_sum) / float(updated)
        base_stats["mean_stability_change"] = float(stability_change_sum) / float(updated)
        base_stats["structural_alert_count"] = int(structural_alert_count)
        base_stats["sac_phase_sws"] = int(base_stats["phase_distribution"]["SWS"])
        base_stats["sac_phase_rem"] = int(base_stats["phase_distribution"]["REM"])
        base_stats["sac_phase_transitional"] = int(base_stats["phase_distribution"]["TRANSITIONAL"])

        if divergence_before_sum > 1e-12:
            base_stats["divergence_reduction_index"] = max(
                -1.0,
                min(1.0, (divergence_before_sum - divergence_after_sum) / divergence_before_sum),
            )
        base_stats["overconfidence_index"] = float(overconfidence_sum) / float(considered)

        if local_phase_mode and sum(base_stats["phase_distribution"].values()) > 0:
            dominant_phase = max(
                base_stats["phase_distribution"],
                key=lambda phase_name: int(base_stats["phase_distribution"][phase_name]),
            )
            base_stats["sac_phase"] = str(dominant_phase)

        self.last_sac_stats = dict(base_stats)
        return dict(base_stats)

    def _sync_edpc_sac(
        self,
        replay_sample: List,
        *,
        sleep_phase: Optional[str] = None,
        sleep_state: bool = False,
        sleep_timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "edpc_sac_sync_enabled": False,
            "edpc_sac_sync_phase": "TRANSITIONAL",
            "edpc_sac_sync_updates": 0,
            "edpc_sac_sync_conflicts": 0,
            "edpc_sac_sync_energy_used": 0.0,
            "edpc_sac_sync_skipped": 0,
        }
        if not sleep_state:
            return dict(stats)

        phase = str(sleep_phase or getattr(self, "last_sac_stats", {}).get("sac_phase", "TRANSITIONAL")).upper()
        stats["edpc_sac_sync_phase"] = phase
        if phase not in {"SWS", "REM"}:
            return dict(stats)

        selector = getattr(self, "selector", None)
        value_layer = getattr(self, "value_layer", None)
        if selector is None or value_layer is None:
            return dict(stats)

        stats["edpc_sac_sync_enabled"] = True
        energy_budget = max(0.0, float(getattr(self, "edpc_sac_energy_budget", 0.0)))
        if energy_budget <= 0.0:
            return dict(stats)

        ema_alpha = max(0.0, min(0.1, float(getattr(self, "edpc_sac_ema_alpha", 0.1))))
        k1 = max(0.0, min(0.03, float(getattr(self, "edpc_sac_stability_k1", 0.01))))
        td_gain = max(0.0, min(0.03, float(getattr(self, "edpc_sac_td_stability_gain", 0.03))))
        conflict_threshold = max(0.0, float(getattr(self, "edpc_sac_conflict_threshold", 0.3)))
        stability_cap = 0.05
        confidence_cap = 0.03
        processed_energy = 0.0
        sleep_ts = float(sleep_timestamp if sleep_timestamp is not None else time.time())

        initial_action_conf: Dict[str, float] = {}
        initial_action_stab: Dict[str, float] = {}
        initial_state_stab: Dict[str, float] = {}
        processed_ids: set = set()

        def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
            if value < lo:
                return lo
            if value > hi:
                return hi
            return value

        def _cap_relative(initial: float, proposed: float, cap: float) -> float:
            delta = proposed - initial
            if delta > cap:
                return initial + cap
            if delta < -cap:
                return initial - cap
            return proposed

        for exp in list(replay_sample or []):
            if processed_energy >= energy_budget:
                break

            exp_id = id(exp)
            if exp_id in processed_ids:
                continue

            replay_priority = self._episode_replay_priority(exp)
            if replay_priority is None:
                stats["edpc_sac_sync_skipped"] += 1
                continue

            priority = max(0.0, float(replay_priority))
            energy_cost = max(0.0, min(1.0, priority))
            if processed_energy + energy_cost > energy_budget:
                stats["edpc_sac_sync_skipped"] += 1
                continue

            exp_ts = getattr(exp, "timestamp", None)
            if exp_ts is not None:
                try:
                    if float(exp_ts) >= sleep_ts:
                        stats["edpc_sac_sync_skipped"] += 1
                        continue
                except Exception:
                    pass

            action_id = self._extract_action_id(exp)
            if not action_id:
                stats["edpc_sac_sync_skipped"] += 1
                continue

            state_key = str(getattr(exp, "value_state_key", "")).strip()
            if not state_key:
                state_snapshot = getattr(exp, "value_state_snapshot", None)
                if state_snapshot is not None:
                    try:
                        state_key = value_layer.encoder.encode(state_snapshot)
                    except Exception:
                        state_key = ""
            if not state_key:
                stats["edpc_sac_sync_skipped"] += 1
                continue

            expectation_memory = getattr(value_layer, "expectation_memory", None)
            if isinstance(expectation_memory, dict) and not isinstance(expectation_memory, OrderedDict):
                expectation_memory = OrderedDict(expectation_memory)
                value_layer.expectation_memory = expectation_memory
            if not isinstance(expectation_memory, dict) or state_key not in expectation_memory:
                stats["edpc_sac_sync_skipped"] += 1
                continue

            expectation_profile = dict(value_layer._get_expectation_profile(state_key))
            existing_meta = getattr(selector, "action_metadata", {})
            if isinstance(existing_meta, dict) and str(action_id) in existing_meta:
                action_meta = dict(existing_meta.get(str(action_id), {}))
            elif hasattr(selector, "get_action_metadata"):
                action_meta = dict(selector.get_action_metadata(action_id))
            else:
                action_meta = {}

            edpc_stability = _clamp(float(expectation_profile.get("stability_score", 0.0)))
            sac_stability = _clamp(
                float(action_meta.get("stability", action_meta.get("stability_score", 0.0)))
            )

            if state_key not in initial_state_stab:
                initial_state_stab[state_key] = edpc_stability
            if action_id not in initial_action_conf:
                initial_action_conf[action_id] = _clamp(
                    float(action_meta.get("confidence", action_meta.get("semantic_confidence", 0.0)))
                )
            if action_id not in initial_action_stab:
                initial_action_stab[action_id] = sac_stability

            shock_score = _clamp(float(self._episode_prediction_shock_score(exp)))
            existing_shock = _clamp(float(expectation_profile.get("prediction_shock", 0.0)))
            if phase == "SWS":
                shock_score = min(existing_shock, shock_score)
            else:
                shock_score = max(existing_shock, shock_score)
            shock_score = _clamp(shock_score)
            expectation_profile["prediction_shock"] = float(shock_score)
            expectation_profile["prediction_shock_flag"] = bool(shock_score >= 0.5)

            error_old = _clamp(float(expectation_profile.get("error_likelihood", 0.0)))
            error_new = _clamp((error_old * 0.95) + (shock_score * 0.05))
            if phase == "SWS" and error_new > error_old:
                error_new = error_old
            expectation_profile["error_likelihood"] = float(error_new)

            conf_in = _clamp(float(expectation_profile.get("confidence_score", 0.0)))
            stab_in = edpc_stability
            should_update_edpc_to_sac = bool(shock_score < 0.2 and conf_in > 0.6)
            should_update_sac_to_edpc = bool(
                action_meta.get("consolidated", action_meta.get("consolidation_flag", False))
            ) and shock_score < 0.5
            conflict = abs(sac_stability - edpc_stability) > conflict_threshold and (
                should_update_edpc_to_sac or should_update_sac_to_edpc
            )
            if conflict:
                action_meta["conflict_flag"] = True
                if hasattr(selector, "set_action_metadata"):
                    selector.set_action_metadata(action_id, action_meta)
                else:
                    if not hasattr(selector, "action_metadata") or not isinstance(selector.action_metadata, dict):
                        selector.action_metadata = {}
                    selector.action_metadata[str(action_id)] = dict(action_meta)
                stats["edpc_sac_sync_conflicts"] += 1
                processed_energy += energy_cost
                processed_ids.add(exp_id)
                continue
            action_meta["conflict_flag"] = False

            if should_update_edpc_to_sac:
                old_conf = _clamp(float(action_meta.get("confidence", action_meta.get("semantic_confidence", 0.0))))
                old_stab = _clamp(float(action_meta.get("stability", action_meta.get("stability_score", 0.0))))
                new_conf = ((1.0 - ema_alpha) * old_conf) + (ema_alpha * conf_in)
                new_stab = ((1.0 - ema_alpha) * old_stab) + (ema_alpha * stab_in)
                new_conf = _cap_relative(initial_action_conf[action_id], new_conf, confidence_cap)
                new_stab = _cap_relative(initial_action_stab[action_id], new_stab, stability_cap)
                new_conf = _clamp(new_conf)
                new_stab = _clamp(new_stab)
                if phase == "SWS" and new_stab < old_stab:
                    new_stab = old_stab
                action_meta["confidence"] = float(new_conf)
                action_meta["stability"] = float(new_stab)

            if phase == "REM" and shock_score >= 0.5:
                old_conf = _clamp(float(action_meta.get("confidence", action_meta.get("semantic_confidence", 0.0))))
                conf_drop = min(confidence_cap, 0.01 + (0.02 * shock_score))
                new_conf = _cap_relative(initial_action_conf[action_id], old_conf - conf_drop, confidence_cap)
                new_conf = _clamp(new_conf)
                if new_conf < old_conf:
                    action_meta["confidence"] = float(new_conf)

            if phase == "REM":
                td_var = max(0.0, float(action_meta.get("td_variance", 0.0)))
                td_var = td_var + min(0.05, 0.01 + (0.02 * shock_score))
                action_meta["td_variance"] = float(max(0.0, min(1.0, td_var)))

            if should_update_sac_to_edpc:
                td_mean = float(action_meta.get("td_mean", self._episode_td_mean(exp)))
                td_variance = max(0.0, float(action_meta.get("td_variance", self._episode_td_variance(exp))))
                delta_primary = k1 * (td_mean / (1.0 + td_variance)) if k1 > 0.0 else 0.0
                delta_td = td_gain * math.tanh(td_mean) * max(0.0, (1.0 - td_variance)) if td_gain > 0.0 else 0.0
                delta = delta_primary + delta_td
                if phase == "SWS":
                    delta = max(0.0, delta)
                if shock_score >= 0.5:
                    delta = min(0.0, delta)
                proposed = edpc_stability + delta
                proposed = _cap_relative(initial_state_stab[state_key], proposed, stability_cap)
                expectation_profile["stability_score"] = float(_clamp(proposed))

            try:
                last_step = int(float(expectation_profile.get("last_updated_step", 0.0)))
            except Exception:
                last_step = 0
            if last_step > 1_000_000_000:
                expectation_profile["last_updated_step"] = int(sleep_ts)
            elif last_step > 0:
                expectation_profile["last_updated_step"] = int(last_step + 1)
            else:
                expectation_profile["last_updated_step"] = int(getattr(value_layer, "update_count", 0) + 1)
            expectation_memory[state_key] = dict(expectation_profile)
            try:
                expectation_memory.move_to_end(state_key)
            except Exception:
                pass

            action_meta["last_state_key"] = str(state_key)
            if hasattr(selector, "set_action_metadata"):
                selector.set_action_metadata(action_id, action_meta)
            else:
                if not hasattr(selector, "action_metadata") or not isinstance(selector.action_metadata, dict):
                    selector.action_metadata = {}
                selector.action_metadata[str(action_id)] = dict(action_meta)

            processed_energy += energy_cost
            processed_ids.add(exp_id)
            stats["edpc_sac_sync_updates"] += 1

        stats["edpc_sac_sync_energy_used"] = float(processed_energy)
        return dict(stats)

    def _reset_conflict_flags(self) -> None:
        selector = getattr(self, "selector", None)
        if selector is None:
            return
        meta_store = getattr(selector, "action_metadata", None)
        if not isinstance(meta_store, dict):
            return
        for action_id, meta in list(meta_store.items()):
            if isinstance(meta, dict):
                meta["conflict_flag"] = False
            else:
                try:
                    selector.set_action_metadata(action_id, {"conflict_flag": False})
                except Exception:
                    pass

    def _channel_prior(self, channel, prior_name: str, weight_name: str) -> float:
        prior = getattr(channel, prior_name, None)
        if prior is None:
            prior = getattr(channel, weight_name, 0.0)
        try:
            value = float(prior)
        except (TypeError, ValueError):
            value = float(getattr(channel, weight_name, 0.0))
        if not math.isfinite(value):
            value = 0.0
        return max(0.0, min(1.0, value))

    def _relax_channel_weight(self, channel, weight_name: str, prior_name: str, keep: float) -> None:
        current = float(getattr(channel, weight_name, 0.0))
        prior = self._channel_prior(channel, prior_name, weight_name)
        updated = prior + (current - prior) * float(keep)
        setattr(channel, weight_name, max(0.0, min(1.0, updated)))

    def _apply_bg_decay(self) -> bool:
        bg_channels = getattr(self, "bg_action_channels", None)
        if not isinstance(bg_channels, dict) or not bg_channels:
            return False
        decay = max(0.0, min(0.2, float(self.decay_rate_sleep)))
        if decay <= 0.0:
            return False
        keep = 1.0 - decay
        for channel in bg_channels.values():
            self._relax_channel_weight(channel, "go_weight", "prior_go", keep)
            self._relax_channel_weight(channel, "nogo_weight", "prior_nogo", keep)
            self._relax_channel_weight(channel, "habit_strength", "prior_habit", keep)
        return True

    def _channel_l1(self, channel) -> float:
        return (
            abs(float(getattr(channel, "go_weight", 0.0)))
            + abs(float(getattr(channel, "nogo_weight", 0.0)))
            + abs(float(getattr(channel, "habit_strength", 0.0)))
        )

    def _normalize_bg_weights(self) -> bool:
        """Scale a channel whose own L1 exceeds the cap. Other channels stay put."""
        bg_channels = getattr(self, "bg_action_channels", None)
        if not isinstance(bg_channels, dict) or not bg_channels:
            return False
        cap = max(0.1, float(self.weight_norm_cap))
        applied = False
        for channel in bg_channels.values():
            current_sum = self._channel_l1(channel)
            if current_sum <= cap or current_sum <= 0.0:
                continue
            scale = cap / current_sum
            channel.go_weight = max(0.0, min(1.0, channel.go_weight * scale))
            channel.nogo_weight = max(0.0, min(1.0, channel.nogo_weight * scale))
            channel.habit_strength = max(0.0, min(1.0, channel.habit_strength * scale))
            applied = True
        return applied

    def _copy_bg_weights(self, channels: Dict, updated) -> None:
        for channel in list(updated or []):
            live = channels.get(getattr(channel, "action_id", None))
            if live is None:
                continue
            live.go_weight = max(0.0, min(1.0, float(channel.go_weight)))
            live.nogo_weight = max(0.0, min(1.0, float(channel.nogo_weight)))
            live.habit_strength = max(0.0, min(1.0, float(channel.habit_strength)))

    def _consolidate_bg_outcome_cache(self) -> None:
        """Legacy cache writer. ``deep_sleep`` does not call this.

        Outcomes come from episodes (decision 5). The method does not open
        the learning guard; a waking call does not change stable weights.
        """
        from learning_guard import learning_is_open

        if not learning_is_open():
            return None

        # apply_sleep_learning(..., forget_rate>0) still shrinks toward 0
        # for direct callers. The sleep path passes forget_rate=0 and lets
        # _apply_bg_decay relax toward each channel's prior.
        channels = getattr(self, "bg_action_channels", None)
        learning = getattr(self, "bg_learning", None)
        if not isinstance(channels, dict) or not channels or learning is None:
            return
        memories = getattr(self, "bg_sleep_memories", None)
        usable: Dict[str, List] = {}
        if isinstance(memories, dict):
            for action_id, items in memories.items():
                kept = []
                for item in list(items or []):
                    try:
                        outcome = float(item[0])
                    except (TypeError, ValueError, IndexError):
                        continue
                    if not math.isfinite(outcome) or abs(outcome) <= 1e-12:
                        continue
                    kept.append(item)
                if kept:
                    usable[str(action_id)] = kept
        if usable and hasattr(learning, "apply_sleep_learning"):
            updated = learning.apply_sleep_learning(
                list(channels.values()),
                usable,
                getattr(self, "neuromodulators", None),
                forget_rate=0.0,
            )
            self._copy_bg_weights(channels, updated)
        if hasattr(learning, "consolidate_habits"):
            raw_serotonin = getattr(getattr(self, "neuromodulators", None), "serotonin", 0.1)
            try:
                serotonin = float(raw_serotonin)
            except (TypeError, ValueError):
                serotonin = 0.1
            if not math.isfinite(serotonin):
                serotonin = 0.1
            updated = learning.consolidate_habits(list(channels.values()), serotonin=serotonin)
            self._copy_bg_weights(channels, updated)
    
    def _cluster_experiences(self, experiences: List) -> List[List]:
        """
        Cluster similar experiences together.
        
        Similarity based on shared events in path.
        
        Args:
            experiences: List of experiences
        
        Returns:
            List of clusters (each cluster is list of experiences)
        """
        if not experiences:
            return []
        
        clusters = []
        used = set()
        
        for i, exp1 in enumerate(experiences):
            if i in used:
                continue
            
            cluster = [exp1]
            used.add(i)
            
            # Find similar experiences
            for j, exp2 in enumerate(experiences[i+1:], start=i+1):
                if j in used:
                    continue
                
                if self._similarity(exp1, exp2) > self.clustering_similarity_threshold:
                    cluster.append(exp2)
                    used.add(j)
            
            clusters.append(cluster)
        
        return clusters
    
    def _similarity(self, exp1, exp2) -> float:
        """
        Calculate similarity between two experiences.
        
        Simple: Jaccard similarity of event names.
        
        Args:
            exp1, exp2: Experience objects
        
        Returns:
            Similarity score [0, 1]
        """
        sig1 = set(exp1.path.signature())
        sig2 = set(exp2.path.signature())
        
        if not sig1 and not sig2:
            return 1.0
        if not sig1 or not sig2:
            return 0.0
        
        intersection = len(sig1 & sig2)
        union = len(sig1 | sig2)
        
        return intersection / union if union > 0 else 0.0
    
    def _consolidate_cluster(self, cluster: List) -> CorticalPattern:
        """
        Consolidate a cluster of experiences into abstract pattern.
        
        Takes common elements across cluster.
        
        Args:
            cluster: List of similar experiences
        
        Returns:
            Created CorticalPattern
        """
        if not cluster:
            return None
        
        # Find common events
        if len(cluster) == 1:
            signature = cluster[0].path.signature()
        else:
            # Intersection of all event names
            common = set(cluster[0].path.signature())
            for exp in cluster[1:]:
                common &= set(exp.path.signature())
            
            signature = tuple(sorted(common))
        
        # Store pattern in cortex
        pattern = self.cortex.store_pattern(signature, source_experiences=len(cluster))
        
        # Update stability of experiences (mark as consolidated)
        for exp in cluster:
            exp.stability = min(1.0, exp.stability + 0.2)
        
        return pattern
    
    def _forget_unstable(self) -> int:
        """
        Forget experiences with low stability and low reinforcement.
        
        Keeps only:
        - Highly reinforced experiences
        - Recently activated
        - Or already consolidated (stability > threshold)
        
        Returns:
            Number of experiences forgotten
        """
        before = len(self.hippocampus.experiences)
        
        # Keep experiences if they meet criteria
        kept = [
            exp for exp in self.hippocampus.experiences
            if (exp.stability >= self.forget_stability_threshold or
                exp.reinforcement_count >= 3 or
                exp.activation_energy > 0.7)
        ]
        
        self.hippocampus.experiences = kept
        
        return before - len(kept)
    
    def _consolidation_closed(self, exp) -> bool:
        if not bool(getattr(exp, "consolidated", False)):
            return False
        try:
            revision = int(getattr(exp, "outcome_revision", 0) or 0)
        except (TypeError, ValueError):
            revision = 0
        done = getattr(exp, "consolidated_revision", None)
        if done is None:
            return True
        try:
            return int(done) == revision
        except (TypeError, ValueError):
            return True

    def _episode_reward_known(self, exp) -> bool:
        if not bool(getattr(exp, "td_outcome_committed", False)):
            return False
        raw = getattr(exp, "td_committed_reward", None)
        if raw is None:
            return False
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return False
        return math.isfinite(value)

    def _spec_priority_weights(self) -> Tuple[float, float, float, float]:
        host = getattr(self, "_host_agent", None)
        plasticity = getattr(self, "plasticity", None)
        if plasticity is None and host is not None:
            plasticity = getattr(host, "plasticity", None)
        raw = getattr(plasticity, "replay_priority_weights", None)
        try:
            weights = tuple(float(item) for item in tuple(raw))
        except (TypeError, ValueError):
            weights = (1.0, 0.5, 0.25, 0.25)
        if len(weights) != 4:
            return (1.0, 0.5, 0.25, 0.25)
        return weights  # type: ignore[return-value]

    def spec_replay_priority(self, exp) -> float:
        """wδ·|δ_now| + wr·|r| + wn·novelty + we·emotional_salience.

        δ_now is recomputed on the current stable table. Equal scores are
        broken by episode_id in ``consolidation_order``.
        """
        w_delta, w_reward, w_novelty, w_emotion = self._spec_priority_weights()
        delta = abs(float(self._replay_signed_td(exp)))
        reward = abs(float(self._offline_reward(exp)))
        try:
            novelty = float(getattr(exp, "novelty", 0.0) or 0.0)
        except (TypeError, ValueError):
            novelty = 0.0
        try:
            emotion = float(getattr(exp, "emotional_salience", 0.0) or 0.0)
        except (TypeError, ValueError):
            emotion = 0.0
        if not math.isfinite(novelty):
            novelty = 0.0
        if not math.isfinite(emotion):
            emotion = 0.0
        novelty = max(0.0, min(1.0, novelty))
        emotion = max(0.0, min(1.0, emotion))
        score = (w_delta * delta) + (w_reward * reward) + (w_novelty * novelty) + (w_emotion * emotion)
        if not math.isfinite(score):
            return 0.0
        return float(score)

    def consolidation_order(self, episodes: List) -> List:
        """Highest spec priority first. Ties break by episode_id."""

        def _key(exp):
            try:
                priority = float(self.spec_replay_priority(exp))
            except Exception:
                priority = 0.0
            return (-priority, str(getattr(exp, "episode_id", "") or ""))

        return sorted(list(episodes or []), key=_key)

    def _select_two_tier_batch(self) -> List:
        experiences = list(getattr(getattr(self, "hippocampus", None), "experiences", []) or [])
        pending = [
            exp
            for exp in experiences
            if self._episode_reward_known(exp) and not self._consolidation_closed(exp)
        ]
        return self.consolidation_order(pending)

    def _episode_context_events(self, exp) -> List[str]:
        stored = getattr(exp, "context_events", None)
        if isinstance(stored, (list, tuple)) and stored:
            return [str(item) for item in stored]
        events = []
        for event in list(getattr(getattr(exp, "path", None), "events", []) or []):
            name = str(getattr(event, "name", "") or "")
            if name and not name.startswith("action:"):
                events.append(name)
        return events

    def _host_now(self) -> float:
        host = getattr(self, "_host_agent", None)
        try:
            return float(getattr(host, "_host_clock_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _bounded_affect_gain(self, exp) -> float:
        try:
            gain = float(getattr(exp, "affect_gain_at_encoding", 1.0))
        except (TypeError, ValueError):
            gain = 1.0
        if not math.isfinite(gain):
            gain = 1.0
        return max(0.25, min(1.5, gain))

    def _apply_episode_channel_and_habit(self, exp) -> None:
        """Capture κ of the channel tag, then the compensated Go/NoGo step and habit EMA.

        Q is cleared with the tag and is not copied into the stable table.
        The sleep rate is η_c_sleep − κ·η_Lc so an undecayed tag plus this
        step totals η_c_sleep. g_DA stays 1: the step is not scaled by dopamine.
        """
        try:
            reward = float(getattr(exp, "td_committed_reward", 0.0))
        except (TypeError, ValueError):
            return
        if not math.isfinite(reward):
            return
        action_id = self._extract_action_id(exp)
        host = getattr(self, "_host_agent", None)
        plasticity = getattr(self, "plasticity", None)
        if plasticity is None and host is not None:
            plasticity = getattr(host, "plasticity", None)
        kappa = 0.5
        eta_sleep = 0.08
        eta_labile = 0.02
        if plasticity is not None:
            try:
                kappa = float(getattr(plasticity, "capture_kappa", 0.5))
                eta_sleep = float(getattr(plasticity, "eta_channel_sleep", 0.08))
                eta_labile = float(getattr(plasticity, "eta_labile_channel", 0.02))
            except (TypeError, ValueError):
                kappa, eta_sleep, eta_labile = 0.5, 0.08, 0.02
        if not math.isfinite(kappa):
            kappa = 0.5
        kappa = max(0.0, min(1.0, kappa))
        eta_eff = eta_sleep - (kappa * eta_labile)
        if not math.isfinite(eta_eff) or eta_eff < 0.0:
            eta_eff = 0.0

        labile = getattr(self, "labile", None)
        if labile is None and host is not None:
            labile = getattr(host, "labile", None)
        now = self._host_now()
        go_tag = 0.0
        nogo_tag = 0.0
        episode_id = str(getattr(exp, "episode_id", "") or "")
        if labile is not None and episode_id and hasattr(labile, "remaining_channel"):
            try:
                go_tag, nogo_tag = labile.remaining_channel(episode_id, now)
            except Exception:
                go_tag, nogo_tag = 0.0, 0.0
            try:
                labile.pop_contribution(episode_id, now)
            except Exception:
                pass

        channels = getattr(self, "bg_action_channels", None)
        channel = channels.get(str(action_id)) if isinstance(channels, dict) and action_id else None
        if channel is not None and hasattr(channel, "update_weights"):
            if abs(float(go_tag)) > 0.0 or abs(float(nogo_tag)) > 0.0:
                channel.update_weights(
                    go_delta=kappa * float(go_tag),
                    nogo_delta=kappa * float(nogo_tag),
                )
            if reward > 1e-12:
                channel.update_weights(
                    go_delta=eta_eff * reward,
                    nogo_delta=-0.5 * eta_eff * reward,
                )
            elif reward < -1e-12:
                magnitude = abs(reward)
                channel.update_weights(
                    go_delta=-0.5 * eta_eff * magnitude,
                    nogo_delta=eta_eff * magnitude,
                )
            if abs(reward) >= 1e-12:
                gain = self._bounded_affect_gain(exp)
                target = 1.0 if reward > 0.0 else 0.0
                current = float(getattr(channel, "habit_strength", 0.0))
                channel.update_weights(habit_delta=(0.20 * gain) * (target - current))

        memory = getattr(self, "intent_memory", None)
        if memory is not None and hasattr(memory, "apply_outcome") and action_id and abs(reward) >= 1e-12:
            memory.apply_outcome(
                self._episode_context_events(exp),
                str(action_id),
                float(reward),
                affect_gain=self._bounded_affect_gain(exp),
            )

    def _transfer_labile_visits(self) -> None:
        """Move waking visit counters into the stable counts and reset them."""
        host = getattr(self, "_host_agent", None)
        if host is None:
            return
        labile = getattr(host, "labile", None)
        counts = getattr(host, "_action_visit_counts", None)
        if labile is None or not hasattr(labile, "take_visits") or not isinstance(counts, dict):
            return
        for key, count in labile.take_visits().items():
            if not isinstance(key, tuple) or len(key) != 2:
                continue
            try:
                add = int(math.floor(float(count) + 1e-9))
            except (TypeError, ValueError):
                continue
            if add <= 0:
                continue
            token = (str(key[0]), str(key[1]))
            counts[token] = int(counts.get(token, 0)) + add

    def _consolidate_two_tier_once(self) -> None:
        """One pass per sleep: capture, habits, Go/NoGo, slow stats, visits.

        REM affect reduction is off (core decision 10). Q is learned only by
        the replay that follows this pass. The legacy ``bg_sleep_memories``
        cache is not read.
        """
        host = getattr(self, "_host_agent", None)
        labile = getattr(self, "labile", None)
        if labile is None and host is not None:
            labile = getattr(host, "labile", None)
        if labile is not None and hasattr(labile, "decay_to"):
            try:
                labile.decay_to(self._host_now())
            except Exception:
                pass
        batch = self._select_two_tier_batch()
        self._two_tier_batch = list(batch)
        for exp in batch:
            self._apply_episode_channel_and_habit(exp)
        if host is not None and hasattr(host, "_flush_external_learning"):
            host._flush_external_learning()
        if host is not None and hasattr(host, "_replay_slow_affect"):
            host._replay_slow_affect()
        self._transfer_labile_visits()

    def _mark_two_tier_batch(self) -> int:
        batch = list(getattr(self, "_two_tier_batch", []) or [])
        self._two_tier_batch = []
        marked = 0
        for exp in batch:
            try:
                reward = float(getattr(exp, "td_committed_reward", 0.0))
            except (TypeError, ValueError):
                reward = 0.0
            if not math.isfinite(reward):
                reward = 0.0
            try:
                revision = int(getattr(exp, "outcome_revision", 0) or 0)
            except (TypeError, ValueError):
                revision = 0
            exp.consolidated = True
            exp.consolidated_reward = float(reward)
            exp.consolidated_revision = int(revision)
            marked += 1
        self._two_tier_marked = marked
        return marked

    def deep_sleep(self, cycles: int = 3) -> dict:
        """
        Extended sleep with multiple consolidation cycles.
        
        Args:
            cycles: Number of sleep cycles to run
        
        Returns:
            Aggregated statistics
        """
        total_stats = {
            "cycles": cycles,
            "total_candidates": 0,
            "total_clusters": 0,
            "total_patterns": 0,
            "total_forgotten": 0,
            "total_replays": 0,
            "total_replay_selected": 0,
            "total_replay_blocked": 0,
            "total_shock_replays": 0,
            "mean_replay_diversity_index": 0.0,
            "mean_replay_confidence": 0.0,
            "mean_replay_stability": 0.0,
            "shock_frequency": 0.0,
            "total_value_delta": 0.0,
            "total_weight_delta": 0.0,
            "total_value_delta_sleep": 0.0,
            "total_bg_delta_sleep": 0.0,
            "sleep_update_count": 0,
            "decay_applied_cycles": 0,
            "normalization_applied_cycles": 0,
            "mean_ach_during_cycle": 0.0,
            "mean_ach_above_baseline": 0.0,
            "value_variance_ratio": 0.0,
            "variance_ratio": 0.0,
            "total_episodes_examined": 0,
            "total_episodes_consolidated": 0,
            "rejected_due_to_td_threshold": 0,
            "rejected_due_to_td_variance": 0,
            "rejected_due_to_salience": 0,
            "rejected_due_to_reinforcement": 0,
            "rejected_due_to_variance_gate": 0,
            "rejected_due_to_ach": 0,
            "rejected_due_to_stability": 0,
            "mean_consolidation_score": 0.0,
            "sleep_update_l2_total": 0.0,
            "consolidation_ratio": 0.0,
            "sac_episodes_gated": 0,
            "sac_actions_considered": 0,
            "sac_actions_updated": 0,
            "sac_actions_skipped": 0,
            "sac_rejected_confidence": 0,
            "sac_rejected_stability": 0,
            "sac_rejected_shock": 0,
            "sac_rejected_consolidation_probability": 0,
            "sac_rejected_replay_count": 0,
            "sac_rejected_min_weight": 0,
            "sac_rejected_shock_mean": 0,
            "sac_rejected_divergence": 0,
            "sac_rejected_missing_signal": 0,
            "semantic_drift_rate": 0.0,
            "stability_growth_rate": 0.0,
            "divergence_reduction_index": 0.0,
            "overconfidence_index": 0.0,
            "sac_phase": "TRANSITIONAL",
            "phase_distribution": {"SWS": 0, "REM": 0, "TRANSITIONAL": 0},
            "sac_phase_sws": 0,
            "sac_phase_rem": 0,
            "sac_phase_transitional": 0,
            "mean_sigma_change": 0.0,
            "mean_stability_change": 0.0,
            "structural_alert_count": 0,
            "last_value_variance": 0.0,
            "replay_blocked": False,
            "intent_degraded": False,
            "intent_stats": {}
        }
        consolidation_score_weighted_sum = 0.0
        
        # Once per sleep, before the cycles replay Q and down-scale.
        # Steps 5–7 of the two-tier order run here; replay inside the
        # cycles may still revisit the same transitions. The batch is
        # marked consolidated after the cycles so this night can replay
        # and the next night cannot.
        from learning_guard import learning_allowed

        with learning_allowed():
            self._consolidate_two_tier_once()

        for _ in range(cycles):
            stats = self.sleep_cycle()
            total_stats["total_candidates"] += stats["candidates"]
            total_stats["total_clusters"] += stats["clusters"]
            total_stats["total_patterns"] += stats["patterns_consolidated"]
            total_stats["total_forgotten"] += stats["experiences_forgotten"]
            total_stats["total_replays"] += stats["replays"]
            total_stats["total_replay_selected"] += int(stats.get("replay_selected", 0))
            total_stats["total_replay_blocked"] += int(bool(stats.get("replay_blocked", False)))
            total_stats["total_shock_replays"] += int(stats.get("shock_replays", 0))
            total_stats["mean_replay_diversity_index"] += float(stats.get("replay_diversity_index", 0.0))
            total_stats["mean_replay_confidence"] += float(stats.get("replay_confidence_mean", 0.0))
            total_stats["mean_replay_stability"] += float(stats.get("replay_stability_mean", 0.0))
            total_stats["total_value_delta"] += float(stats.get("value_delta_total", 0.0))
            total_stats["total_weight_delta"] += float(stats.get("weight_delta_total", 0.0))
            total_stats["total_value_delta_sleep"] += float(
                stats.get("total_value_delta_sleep", stats.get("value_delta_total", 0.0))
            )
            total_stats["total_bg_delta_sleep"] += float(
                stats.get("total_bg_delta_sleep", stats.get("weight_delta_total", 0.0))
            )
            total_stats["sleep_update_count"] += int(stats.get("sleep_update_count", 0))
            total_stats["decay_applied_cycles"] += int(bool(stats.get("decay_applied", False)))
            total_stats["normalization_applied_cycles"] += int(bool(stats.get("normalization_applied", False)))
            total_stats["mean_ach_during_cycle"] += float(stats.get("mean_ach_during_cycle", 0.0))
            total_stats["mean_ach_above_baseline"] += float(stats.get("mean_ach_above_baseline", 0.0))
            total_stats["value_variance_ratio"] += float(stats.get("value_variance_ratio", 0.0))
            total_stats["variance_ratio"] += float(stats.get("variance_ratio", stats.get("value_variance_ratio", 0.0)))
            total_stats["total_episodes_examined"] += int(stats.get("total_episodes_examined", 0))
            total_stats["total_episodes_consolidated"] += int(stats.get("total_episodes_consolidated", 0))
            total_stats["rejected_due_to_td_threshold"] += int(stats.get("rejected_due_to_td_threshold", 0))
            total_stats["rejected_due_to_td_variance"] += int(stats.get("rejected_due_to_td_variance", 0))
            total_stats["rejected_due_to_salience"] += int(stats.get("rejected_due_to_salience", 0))
            total_stats["rejected_due_to_reinforcement"] += int(stats.get("rejected_due_to_reinforcement", 0))
            total_stats["rejected_due_to_variance_gate"] += int(stats.get("rejected_due_to_variance_gate", 0))
            total_stats["rejected_due_to_ach"] += int(stats.get("rejected_due_to_ach", 0))
            total_stats["rejected_due_to_stability"] += int(stats.get("rejected_due_to_stability", 0))
            total_stats["sleep_update_l2_total"] += float(stats.get("sleep_update_l2_total", 0.0))
            total_stats["sac_episodes_gated"] += int(stats.get("sac_episodes_gated", 0))
            total_stats["sac_actions_considered"] += int(stats.get("sac_actions_considered", 0))
            total_stats["sac_actions_updated"] += int(stats.get("sac_actions_updated", 0))
            total_stats["sac_actions_skipped"] += int(stats.get("sac_actions_skipped", 0))
            total_stats["sac_rejected_confidence"] += int(stats.get("sac_rejected_confidence", 0))
            total_stats["sac_rejected_stability"] += int(stats.get("sac_rejected_stability", 0))
            total_stats["sac_rejected_shock"] += int(stats.get("sac_rejected_shock", 0))
            total_stats["sac_rejected_consolidation_probability"] += int(
                stats.get("sac_rejected_consolidation_probability", 0)
            )
            total_stats["sac_rejected_replay_count"] += int(stats.get("sac_rejected_replay_count", 0))
            total_stats["sac_rejected_min_weight"] += int(stats.get("sac_rejected_min_weight", 0))
            total_stats["sac_rejected_shock_mean"] += int(stats.get("sac_rejected_shock_mean", 0))
            total_stats["sac_rejected_divergence"] += int(stats.get("sac_rejected_divergence", 0))
            total_stats["sac_rejected_missing_signal"] += int(stats.get("sac_rejected_missing_signal", 0))
            total_stats["semantic_drift_rate"] += float(stats.get("semantic_drift_rate", 0.0))
            total_stats["stability_growth_rate"] += float(stats.get("stability_growth_rate", 0.0))
            total_stats["divergence_reduction_index"] += float(stats.get("divergence_reduction_index", 0.0))
            total_stats["overconfidence_index"] += float(stats.get("overconfidence_index", 0.0))
            total_stats["sac_phase_sws"] += int(stats.get("sac_phase_sws", 0))
            total_stats["sac_phase_rem"] += int(stats.get("sac_phase_rem", 0))
            total_stats["sac_phase_transitional"] += int(stats.get("sac_phase_transitional", 0))
            total_stats["mean_sigma_change"] += float(stats.get("mean_sigma_change", 0.0))
            total_stats["mean_stability_change"] += float(stats.get("mean_stability_change", 0.0))
            total_stats["structural_alert_count"] += int(stats.get("structural_alert_count", 0))
            phase_distribution = stats.get("phase_distribution", {})
            if isinstance(phase_distribution, dict):
                for phase_name in ("SWS", "REM", "TRANSITIONAL"):
                    total_stats["phase_distribution"][phase_name] += int(phase_distribution.get(phase_name, 0))
            consolidated_in_cycle = int(stats.get("total_episodes_consolidated", 0))
            consolidation_score_weighted_sum += float(stats.get("mean_consolidation_score", 0.0)) * float(
                consolidated_in_cycle
            )
            total_stats["last_value_variance"] = float(stats.get("value_variance", 0.0))
            total_stats["replay_blocked"] = bool(total_stats["replay_blocked"] or stats.get("replay_blocked", False))
            
            # Track intent memory stats from last cycle
            if stats.get("intent_degraded"):
                total_stats["intent_degraded"] = True
            if stats.get("intent_stats"):
                total_stats["intent_stats"] = stats["intent_stats"]
        
        # Note: individual sleep_cycle() calls already increment
        # `self.consolidation_cycles`, so do not increment again here.
        if cycles > 0:
            total_stats["mean_ach_during_cycle"] = float(total_stats["mean_ach_during_cycle"]) / float(cycles)
            total_stats["mean_ach_above_baseline"] = float(total_stats["mean_ach_above_baseline"]) / float(cycles)
            total_stats["value_variance_ratio"] = float(total_stats["value_variance_ratio"]) / float(cycles)
            total_stats["variance_ratio"] = float(total_stats["variance_ratio"]) / float(cycles)
            total_stats["mean_replay_diversity_index"] = float(total_stats["mean_replay_diversity_index"]) / float(cycles)
            total_stats["mean_replay_confidence"] = float(total_stats["mean_replay_confidence"]) / float(cycles)
            total_stats["mean_replay_stability"] = float(total_stats["mean_replay_stability"]) / float(cycles)
            total_stats["semantic_drift_rate"] = float(total_stats["semantic_drift_rate"]) / float(cycles)
            total_stats["stability_growth_rate"] = float(total_stats["stability_growth_rate"]) / float(cycles)
            total_stats["divergence_reduction_index"] = float(total_stats["divergence_reduction_index"]) / float(cycles)
            total_stats["overconfidence_index"] = float(total_stats["overconfidence_index"]) / float(cycles)
            total_stats["mean_sigma_change"] = float(total_stats["mean_sigma_change"]) / float(cycles)
            total_stats["mean_stability_change"] = float(total_stats["mean_stability_change"]) / float(cycles)
        total_replay_selected = int(total_stats.get("total_replay_selected", 0))
        if total_replay_selected > 0:
            total_stats["shock_frequency"] = float(total_stats["total_shock_replays"]) / float(total_replay_selected)
        if total_stats["total_episodes_consolidated"] > 0:
            total_stats["mean_consolidation_score"] = float(consolidation_score_weighted_sum) / float(
                total_stats["total_episodes_consolidated"]
            )
        if total_stats["total_episodes_examined"] > 0:
            total_stats["consolidation_ratio"] = float(total_stats["total_episodes_consolidated"]) / float(
                total_stats["total_episodes_examined"]
            )
        if sum(total_stats["phase_distribution"].values()) > 0:
            total_stats["sac_phase"] = max(
                total_stats["phase_distribution"],
                key=lambda phase_name: int(total_stats["phase_distribution"][phase_name]),
            )

        marked = self._mark_two_tier_batch()
        total_stats["two_tier_consolidated"] = int(marked)
        return total_stats

    def _estimate_mean_ach(self, experiences: Optional[List] = None) -> float:
        ach_values: List[float] = []
        for exp in list(experiences or []):
            if hasattr(exp, "acetylcholine_snapshot"):
                try:
                    ach_values.append(float(getattr(exp, "acetylcholine_snapshot", 0.0)))
                except Exception:
                    pass
        if not ach_values:
            try:
                current_ach = float(getattr(getattr(self, "neuromodulators", None), "acetylcholine", 0.0))
                ach_values.append(current_ach)
            except Exception:
                ach_values.append(0.0)
        mean_ach = sum(ach_values) / float(len(ach_values))
        return max(0.0, min(1.0, mean_ach))

    def _estimate_mean_ach_above_baseline(self, experiences: Optional[List] = None) -> float:
        mean_ach = float(self._estimate_mean_ach(experiences))
        baseline = float(getattr(getattr(self, "neuromodulators", None), "ach_baseline", 0.1))
        return max(0.0, min(1.0, mean_ach - max(0.0, min(1.0, baseline))))

    def _form_chains_from_recent(self, max_recent: int = 50, min_len: int = 2, max_len: int = 7) -> int:
        """Create/update TemporalChains from recent hippocampal experiences.

        Extract short subsequences (including action events) from recent
        experiences and aggregate a simple net_affect to add or update chains.
        Returns number of updated/created chains.
        """
        if not hasattr(self, 'chain_memory') or self.chain_memory is None:
            return 0

        recent = self.hippocampus.experiences[-max_recent:]
        updated = 0

        # Build a flat sequence of event names from recent experiences
        flat_events = []
        for exp in recent:
            flat_events.extend(list(exp.path.signature()))

        # DEBUG: If no events found, try building from path more carefully
        if not flat_events:
            # Try alternative: maybe path has structure we're missing
            for exp in recent:
                if hasattr(exp.path, 'events'):
                    for event in exp.path.events:
                        flat_events.append(event.name)
        
        if not flat_events:
            return 0

        # For each possible subsequence window length, create chains
        for L in range(min_len, max_len + 1):
            for i in range(0, max(0, len(flat_events) - L + 1)):
                subseq = tuple(flat_events[i:i+L])
                # Compute a crude net_affect: use consequence if present else intensity
                # If consequence looks like 'feedback:X' derive numeric reward
                net = 0.0
                # try to find consequence in the experiences that contributed
                # we approximate by checking events in subseq for consequence tokens
                # otherwise fall back to mean intensity of recent experiences
                for exp in recent:
                    if any(e in subseq for e in exp.path.signature()):
                        if getattr(exp, 'consequence', None) and exp.consequence is not None:
                            name = getattr(exp.consequence, 'name', '')
                            if name.startswith('feedback:'):
                                try:
                                    val = float(name.split(':', 1)[1])
                                    net += val
                                except Exception:
                                    pass
                        else:
                            net += exp.intensity * 0.1

                # normalize net by number of contributing exps
                net = net / max(1.0, len(recent))

                self.chain_memory.add_or_update(subseq, net)
                updated += 1

        return updated
