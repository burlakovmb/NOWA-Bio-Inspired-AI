"""Hippocampus 2.0: fuzzy episodic memory with novelty signaling."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import sys
import time
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from experience import (
    Event,
    EventType,
    Experience,
    Path,
    _intern_token_collection,
    _pickle_state_dict,
)


@dataclass(slots=True)
class SignatureTrace:
    """One hippocampal trace. Biological fields compare; scan caches do not.

    Masks and novelty runners are the same numbers a fresh scan would
    produce. They are stored on the trace so a decision does not rebuild them,
    and they are not part of equality.
    """

    feature_set: Set[str]
    drive_vector: Tuple[float, float, float]
    context_vector: Tuple[float, float, float]
    timestamp: float
    context_tokens: Tuple[str, ...] = ()
    activation_weight: float = 1.0
    repetition_count: int = 1
    reward_signal: float = 0.0
    source_experience: Optional[Experience] = None
    last_decay_ts: float = field(default_factory=time.time)
    feature_mask: int = field(default=0, compare=False, repr=False)
    feature_count: int = field(default=0, compare=False, repr=False)
    token_mask: int = field(default=0, compare=False, repr=False)
    token_count: int = field(default=0, compare=False, repr=False)
    _mask_ready: bool = field(default=False, compare=False, repr=False)
    _activate_drive_sim: float = field(default=0.0, compare=False, repr=False)
    _fs_key: Optional[int] = field(default=None, compare=False, repr=False)
    _fs_val: float = field(default=0.0, compare=False, repr=False)
    _nov_ready: bool = field(default=False, compare=False, repr=False)
    _nov_max: float = field(default=0.0, compare=False, repr=False)
    _nov_arg: int = field(default=0, compare=False, repr=False)
    _nov_max2: float = field(default=0.0, compare=False, repr=False)
    _nov_arg2: int = field(default=0, compare=False, repr=False)

    def __getstate__(self):
        state = {}
        for name in self.__slots__:
            try:
                state[name] = getattr(self, name)
            except AttributeError:
                continue
        return state

    def __setstate__(self, state):
        """Accept a main dataclass ``__dict__`` or a slotted payload.

        Scan caches did not exist on main. Missing ones take the empty
        defaults and the next recall rebuilds the masks.
        """
        payload = _pickle_state_dict(state)
        defaults = {
            "context_tokens": (),
            "activation_weight": 1.0,
            "repetition_count": 1,
            "reward_signal": 0.0,
            "source_experience": None,
            "last_decay_ts": 0.0,
            "feature_mask": 0,
            "feature_count": 0,
            "token_mask": 0,
            "token_count": 0,
            "_mask_ready": False,
            "_activate_drive_sim": 0.0,
            "_fs_key": None,
            "_fs_val": 0.0,
            "_nov_ready": False,
            "_nov_max": 0.0,
            "_nov_arg": 0,
            "_nov_max2": 0.0,
            "_nov_arg2": 0,
            "feature_set": set(),
            "drive_vector": (0.0, 0.0, 0.0),
            "context_vector": (0.0, 0.0, 0.0),
            "timestamp": 0.0,
        }
        for name in self.__slots__:
            if name in payload:
                value = payload[name]
            elif name in defaults:
                value = defaults[name]
                if isinstance(value, set):
                    value = set(value)
            else:
                continue
            if name in {"feature_set", "context_tokens"}:
                value = _intern_token_collection(value)
            if name == "feature_set" and not isinstance(value, set):
                value = set(value or ())
            elif name == "context_tokens" and not isinstance(value, tuple):
                value = tuple(value or ())
            elif name in {"drive_vector", "context_vector"}:
                try:
                    value = tuple(float(item) for item in value)
                except (TypeError, ValueError):
                    value = (0.0, 0.0, 0.0)
                if len(value) != 3:
                    value = (0.0, 0.0, 0.0)
            object.__setattr__(self, name, value)


class NOWAHippocampus:
    """Hippocampal episodic memory with spec 2.0 extensions."""

    def __init__(
        self,
        max_experiences: int = 1000,
        activation_decay_half_life: float = 3600.0,
        decay_rate: float = 0.015,
        activation_threshold: float = 0.03,
        max_features: int = 12,
        top_k_recall: int = 5,
        novelty_window: int = 25,
        cycle_length: int = 24,
        context_history_size: int = 12,
        activation_similarity_threshold: float = 0.20,
        reinforce_similarity_threshold: float = 0.85,
        consolidation_min_probability: float = 0.0,
        novelty_capacity_bias: float = 0.55,
    ):
        self.experiences: List[Experience] = []
        self.signatures: List[SignatureTrace] = []

        self.max_experiences = max(1, int(max_experiences))
        self.activation_decay_half_life = max(1e-6, float(activation_decay_half_life))
        self.decay_rate = max(0.0, min(0.99, float(decay_rate)))
        self.activation_threshold = max(0.0, min(1.0, float(activation_threshold)))
        self.max_features = max(1, int(max_features))
        self.top_k_recall = max(1, int(top_k_recall))
        self.novelty_window = max(1, int(novelty_window))
        self.cycle_length = max(1, int(cycle_length))
        self.context_history_size = max(1, int(context_history_size))
        self.activation_similarity_threshold = max(0.0, min(1.0, float(activation_similarity_threshold)))
        self.reinforce_similarity_threshold = max(0.0, min(1.0, float(reinforce_similarity_threshold)))
        self.consolidation_min_probability = max(0.0, min(1.0, float(consolidation_min_probability)))
        self.novelty_capacity_bias = max(0.0, min(1.0, float(novelty_capacity_bias)))
        self.novelty_sensitivity_scale = 1.0

        self._recent_event_window: List[str] = []
        self._novelty_history: List[float] = []
        self._episode_seq = 0
        self._episode_seq_ready = False
        self._episodes_by_id: Dict[str, Experience] = {}
        # Stable bit per feature / context token. Jaccard then is a popcount,
        # identical to the set formula, without building a set per comparison.
        self._feature_bits: Dict[str, int] = {}
        self._token_bits: Dict[str, int] = {}
        self._nov_ids: Tuple[int, ...] = ()
        self._nov_valid = False

    def __getstate__(self):
        return dict(self.__dict__)

    def __setstate__(self, state):
        """Accept the ``__dict__`` main wrote and a slotted ``(dict, slots)`` pair.

        The hippocampus itself has no slots. Nested episodes and traces do,
        and their own ``__setstate__`` runs before this one.
        """
        payload = _pickle_state_dict(state)
        self.__dict__.clear()
        self.__dict__.update(payload)

    def export_persistent_state(self) -> dict:
        """Snapshot the trace store that recall, novelty and decay read.

        Experiences stay with the caller. Signatures keep their object link
        to those experiences, including ``last_decay_ts`` and context fields.
        """
        return {
            "signatures": list(self.signatures),
            "recent_event_window": list(self._recent_event_window),
            "novelty_history": [float(value) for value in self._novelty_history],
            "feature_bits": {str(key): int(value) for key, value in self._feature_bits.items()},
            "token_bits": {str(key): int(value) for key, value in self._token_bits.items()},
            "nov_ids": tuple(int(value) for value in self._nov_ids),
            "nov_valid": bool(self._nov_valid),
            "novelty_sensitivity_scale": float(self.novelty_sensitivity_scale),
            "episode_seq_ready": bool(self._episode_seq_ready),
        }

    def import_persistent_state(self, data: dict) -> None:
        """Restore a snapshot from ``export_persistent_state``.

        Experiences must already be the saved objects. Signatures are relinked
        by position and are not rebuilt, so decay anchors and context tokens
        stay the ones that were saved.
        """
        if not isinstance(data, dict):
            raise TypeError("hippocampus decision state must be a dict")
        signatures = data.get("signatures", [])
        if not isinstance(signatures, list):
            raise TypeError("hippocampus signatures must be a list")
        if len(signatures) == len(self.experiences):
            for experience, signature in zip(self.experiences, signatures):
                if signature is not None:
                    signature.source_experience = experience
        self.signatures = list(signatures)
        window = data.get("recent_event_window") or []
        self._recent_event_window = [str(item) for item in list(window)]
        history = []
        for item in list(data.get("novelty_history") or []):
            try:
                history.append(float(item))
            except (TypeError, ValueError):
                continue
        self._novelty_history = history
        self._feature_bits = {
            str(key): int(value)
            for key, value in dict(data.get("feature_bits") or {}).items()
        }
        self._token_bits = {
            str(key): int(value)
            for key, value in dict(data.get("token_bits") or {}).items()
        }
        self._nov_ids = tuple(int(item) for item in tuple(data.get("nov_ids") or ()))
        self._nov_valid = bool(data.get("nov_valid", False))
        try:
            scale = float(data.get("novelty_sensitivity_scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        self.novelty_sensitivity_scale = self._clamp(scale, 0.5, 2.0)
        self._episode_seq_ready = bool(data.get("episode_seq_ready", False))
        self._sync_episode_index()

    @staticmethod
    def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, float(value)))

    @staticmethod
    def _safe_float(value, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def set_novelty_sensitivity_scale(self, scale: float) -> float:
        """Set external novelty scaling factor (CER integration)."""
        self.novelty_sensitivity_scale = self._clamp(self._safe_float(scale, 1.0), 0.5, 2.0)
        return self.novelty_sensitivity_scale

    def get_novelty_sensitivity_scale(self) -> float:
        return self._clamp(self._safe_float(self.novelty_sensitivity_scale, 1.0), 0.5, 2.0)

    def _to_path(self, path_like) -> Path:
        if isinstance(path_like, Path):
            return path_like

        if isinstance(path_like, (set, tuple, list)):
            path = Path()
            for token in path_like:
                if token is None:
                    continue
                path = path.add_event(Event(str(token), EventType.CONTEXT))
            return path

        if isinstance(path_like, str):
            path = Path()
            return path.add_event(Event(path_like, EventType.CONTEXT))

        if hasattr(path_like, "signature"):
            try:
                signature_items = list(path_like.signature())
            except Exception:
                signature_items = []
            path = Path()
            for token in signature_items:
                path = path.add_event(Event(str(token), EventType.CONTEXT))
            return path

        raise TypeError("path must be Path, iterable of feature strings, or signature-like object")

    def _sanitize_features(self, features: Iterable[str]) -> Set[str]:
        out: Set[str] = set()
        intern = sys.intern
        for feature in features or []:
            token = str(feature).strip()
            if token:
                # One shared str per token. The bit table already retains the
                # vocabulary for the life of the hippocampus.
                out.add(intern(token) if len(token) <= 80 else token)
        return out

    def _extract_features_from_path(self, path: Path, consequence=None) -> Set[str]:
        features = self._sanitize_features(path.signature())
        if consequence is not None and getattr(consequence, "name", None):
            features.add(f"consequence:{consequence.name}")
        return features

    def _feature_frequency(self, feature: str) -> int:
        count = 0
        for sig in self.signatures:
            if feature in sig.feature_set:
                count += 1
        return count

    def _salience_score(self, feature: str) -> float:
        freq = self._feature_frequency(feature)
        rarity = 1.0 / (1.0 + float(freq))
        structural = 0.05
        if ":" in feature:
            structural += 0.15
        if feature.startswith("action:"):
            structural += 0.20
        if feature.startswith("consequence:"):
            structural += 0.12
        return rarity + structural

    def _sparsify_features(self, feature_set: Set[str]) -> Set[str]:
        features = self._sanitize_features(feature_set)
        if len(features) <= self.max_features:
            return features
        ranked = sorted(features, key=lambda f: (-self._salience_score(f), f))
        return set(ranked[: self.max_features])

    def _build_drive_vector(
        self,
        intensity: float,
        reward: float = 0.0,
        encoding_strength: Optional[float] = None,
        drive_state=None,
    ) -> Tuple[float, float, float]:
        if isinstance(drive_state, dict):
            ordered = sorted((str(k), self._safe_float(v)) for k, v in drive_state.items())
            vals = [v for _, v in ordered[:3]]
            while len(vals) < 3:
                vals.append(0.0)
            return tuple(vals[:3])

        if isinstance(drive_state, (tuple, list)):
            vals = [self._safe_float(v) for v in list(drive_state)[:3]]
            while len(vals) < 3:
                vals.append(0.0)
            return tuple(vals)

        enc = self._safe_float(
            encoding_strength if encoding_strength is not None else intensity,
            default=self._safe_float(intensity, 0.0),
        )
        return (
            self._safe_float(intensity, 0.0),
            self._safe_float(reward, 0.0),
            enc,
        )

    def _rolling_hash(self, tokens: Sequence[str]) -> int:
        payload = "|".join(str(t) for t in list(tokens or [])[-self.context_history_size :])
        digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()
        return int(digest, 16)

    def _build_context_tokens(self, features: Set[str]) -> Tuple[str, ...]:
        tokens = list(self._recent_event_window[-self.context_history_size :]) + sorted(list(features))
        if len(tokens) > self.context_history_size:
            tokens = tokens[-self.context_history_size :]
        return tuple(tokens)

    def _discretize_drive(self, drive_vector: Tuple[float, float, float]) -> float:
        total = 0.0
        for value in drive_vector:
            parsed = self._safe_float(value, 0.0)
            if not math.isfinite(parsed):
                parsed = 0.0
            total += abs(parsed)
        mean_drive = total / 3.0
        if not math.isfinite(mean_drive):
            mean_drive = 0.0
        bucket = int(round(mean_drive * 3.0))
        return float(min(9, max(0, bucket)))

    def _encode_context_vector(
        self,
        features: Set[str],
        drive_vector: Tuple[float, float, float],
        timestamp: float,
        context_tokens: Optional[Sequence[str]] = None,
    ) -> Tuple[float, float, float]:
        time_bucket = float(int(timestamp) % self.cycle_length)
        tokens = list(context_tokens or self._build_context_tokens(features))
        rolling_hash = self._rolling_hash(tokens)
        drive_bucket = self._discretize_drive(drive_vector)
        return (time_bucket, float(rolling_hash), drive_bucket)

    def _vector_similarity(
        self, left: Tuple[float, float, float], right: Tuple[float, float, float]
    ) -> float:
        distance = math.sqrt(sum((self._safe_float(a) - self._safe_float(b)) ** 2 for a, b in zip(left, right)))
        return self._clamp(1.0 / (1.0 + distance))

    @staticmethod
    def _jaccard_similarity(left: Set[str], right: Set[str]) -> float:
        if not left and not right:
            return 1.0
        union = left | right
        if not union:
            return 0.0
        return float(len(left & right)) / float(len(union))

    @staticmethod
    def _mask_jaccard(left: int, left_count: int, right: int, right_count: int) -> float:
        """Set Jaccard for bitmasks whose bits were assigned one-to-one with tokens."""
        if left == 0 and right == 0:
            return 1.0
        inter = (left & right).bit_count()
        if inter == 0:
            return 0.0
        return inter / float(left_count + right_count - inter)

    def _bits_for(self, values, table: Dict[str, int]) -> Tuple[int, int]:
        mask = 0
        for value in values:
            bit = table.get(value)
            if bit is None:
                bit = 1 << len(table)
                table[value] = bit
            mask |= bit
        if mask == 0:
            return 0, 0
        return mask, mask.bit_count()

    def _stamp_signature(self, sig: SignatureTrace) -> None:
        """Cache feature and token bitmasks. Re-stamping is exact, not approximate."""
        features = sig.feature_set or set()
        sig.feature_mask, sig.feature_count = self._bits_for(features, self._feature_bits)
        tokens = sig.context_tokens or ()
        if not isinstance(tokens, tuple):
            tokens = tuple(str(token) for token in tokens)
            sig.context_tokens = tokens
        sig.token_mask, sig.token_count = self._bits_for(tokens, self._token_bits)
        sig._mask_ready = True
        # activate() always queries drive (1, 0, 1). Cache that half of the blend.
        drive = sig.drive_vector
        dist = math.sqrt((1.0 - drive[0]) ** 2 + drive[1] ** 2 + (1.0 - drive[2]) ** 2)
        sig._activate_drive_sim = 1.0 / (1.0 + dist)
        sig._fs_key = None
        sig._fs_val = 0.0
        sig._nov_ready = False

    def _ensure_masks(self) -> None:
        for sig in self.signatures:
            if not getattr(sig, "_mask_ready", False):
                self._stamp_signature(sig)

    def _fast_similarity(
        self,
        query_mask: int,
        query_count: int,
        query_drive: Tuple[float, float, float],
        query_context: Tuple[float, float, float],
        query_tokens: Sequence[str],
        query_token_mask: int,
        query_token_count: int,
        sig: SignatureTrace,
    ) -> float:
        """Same weights as ``_composite_similarity``, without per-pair allocations."""
        if not getattr(sig, "_mask_ready", False):
            self._stamp_signature(sig)
        feature_sim = self._mask_jaccard(query_mask, query_count, sig.feature_mask, sig.feature_count)
        drive = sig.drive_vector
        dist = math.sqrt(
            (query_drive[0] - drive[0]) ** 2
            + (query_drive[1] - drive[1]) ** 2
            + (query_drive[2] - drive[2]) ** 2
        )
        drive_sim = 1.0 / (1.0 + dist)
        stored_tokens = sig.context_tokens or ()
        if not query_tokens or not stored_tokens:
            window_sim = 0.0
        else:
            set_sim = self._mask_jaccard(
                query_token_mask, query_token_count, sig.token_mask, sig.token_count
            )
            limit = len(query_tokens) if len(query_tokens) < len(stored_tokens) else len(stored_tokens)
            positional = 0.0
            for idx in range(limit):
                if query_tokens[idx] == stored_tokens[idx]:
                    positional += 1.0
            max_len = len(query_tokens) if len(query_tokens) > len(stored_tokens) else len(stored_tokens)
            window_sim = (0.75 * set_sim) + (0.25 * (positional / float(max_len or 1)))
            if window_sim < 0.0:
                window_sim = 0.0
            elif window_sim > 1.0:
                window_sim = 1.0
        q_ctx = query_context
        s_ctx = sig.context_vector
        time_delta = abs(q_ctx[0] - s_ctx[0])
        cyc = float(self.cycle_length if self.cycle_length > 1 else 1)
        time_sim = 1.0 - min(time_delta, cyc) / cyc
        hash_sim = 1.0 - (abs(q_ctx[1] - s_ctx[1]) / float((1 << 64) - 1))
        if hash_sim < 0.0:
            hash_sim = 0.0
        elif hash_sim > 1.0:
            hash_sim = 1.0
        ctx_drive = 1.0 - (abs(q_ctx[2] - s_ctx[2]) / 9.0)
        if ctx_drive < 0.0:
            ctx_drive = 0.0
        elif ctx_drive > 1.0:
            ctx_drive = 1.0
        context_sim = (0.30 * time_sim) + (0.15 * hash_sim) + (0.20 * ctx_drive) + (0.35 * window_sim)
        blended = (0.80 * feature_sim) + (0.15 * drive_sim) + (0.05 * context_sim)
        if blended < 0.0:
            return 0.0
        if blended > 1.0:
            return 1.0
        return blended

    def _context_window_similarity(
        self,
        query_tokens: Sequence[str],
        stored_tokens: Sequence[str],
    ) -> float:
        left = [str(x) for x in list(query_tokens or [])]
        right = [str(x) for x in list(stored_tokens or [])]
        if not left or not right:
            return 0.0

        left_set = set(left)
        right_set = set(right)
        set_sim = self._jaccard_similarity(left_set, right_set)
        max_len = max(len(left), len(right), 1)
        positional = 0.0
        for idx in range(min(len(left), len(right))):
            if left[idx] == right[idx]:
                positional += 1.0
        positional_sim = positional / float(max_len)
        return self._clamp(0.75 * set_sim + 0.25 * positional_sim)

    def _context_similarity(
        self,
        q_ctx: Tuple[float, float, float],
        s_ctx: Tuple[float, float, float],
        q_tokens: Sequence[str],
        s_tokens: Sequence[str],
    ) -> float:
        if q_ctx is None or s_ctx is None:
            return 0.0
        time_delta = abs(self._safe_float(q_ctx[0]) - self._safe_float(s_ctx[0]))
        cyc = float(max(1, self.cycle_length))
        time_sim = self._clamp(1.0 - min(time_delta, cyc) / cyc)
        max_hash = float((1 << 64) - 1)
        hash_delta = abs(self._safe_float(q_ctx[1]) - self._safe_float(s_ctx[1])) / max_hash
        hash_sim = self._clamp(1.0 - hash_delta)
        drive_delta = abs(self._safe_float(q_ctx[2]) - self._safe_float(s_ctx[2]))
        drive_sim = self._clamp(1.0 - (drive_delta / 9.0))
        window_sim = self._context_window_similarity(q_tokens, s_tokens)
        return 0.30 * time_sim + 0.15 * hash_sim + 0.20 * drive_sim + 0.35 * window_sim

    def _composite_similarity(
        self,
        query_features: Set[str],
        query_drive: Tuple[float, float, float],
        query_context: Tuple[float, float, float],
        query_context_tokens: Sequence[str],
        stored: SignatureTrace,
    ) -> float:
        query_mask, query_count = self._bits_for(query_features, self._feature_bits)
        if not isinstance(query_context_tokens, tuple):
            query_context_tokens = tuple(str(token) for token in (query_context_tokens or ()))
        token_mask, token_count = self._bits_for(query_context_tokens, self._token_bits)
        return self._fast_similarity(
            query_mask,
            query_count,
            query_drive,
            query_context,
            query_context_tokens,
            token_mask,
            token_count,
            stored,
        )
    def _append_recent_events(self, ordered_tokens: Sequence[str]) -> None:
        for token in ordered_tokens or []:
            txt = str(token).strip()
            if not txt:
                continue
            self._recent_event_window.append(txt)
            if len(self._recent_event_window) > self.context_history_size:
                self._recent_event_window = self._recent_event_window[-self.context_history_size :]

    def _ensure_signature_store(self) -> None:
        if not self.experiences:
            if self.signatures:
                self.signatures = []
                self._nov_valid = False
            return

        # store/decay/enforce keep the two lists paired. Rebuilding them on
        # every recall walks the whole memory and allocates a new list.
        if len(self.signatures) == len(self.experiences):
            aligned = True
            for exp, sig in zip(self.experiences, self.signatures):
                if sig.source_experience is not exp:
                    aligned = False
                    break
            if aligned:
                return

        existing_by_experience = {}
        for sig in self.signatures:
            if sig.source_experience is not None:
                existing_by_experience[id(sig.source_experience)] = sig

        rebuilt: List[SignatureTrace] = []
        for exp in self.experiences:
            found = existing_by_experience.get(id(exp))
            if found is None:
                features = self._sparsify_features(self._extract_features_from_path(exp.path, exp.consequence))
                drive_vector = self._build_drive_vector(
                    intensity=getattr(exp, "intensity", 0.0),
                    reward=getattr(exp, "reward", 0.0),
                    encoding_strength=getattr(exp, "encoding_strength", None),
                )
                timestamp = self._safe_float(getattr(exp, "timestamp", time.time()), time.time())
                context_tokens = self._build_context_tokens(features)
                context_vector = self._encode_context_vector(
                    features,
                    drive_vector,
                    timestamp,
                    context_tokens=context_tokens,
                )
                found = SignatureTrace(
                    feature_set=features,
                    drive_vector=drive_vector,
                    context_vector=context_vector,
                    context_tokens=context_tokens,
                    timestamp=timestamp,
                    activation_weight=self._clamp(self._safe_float(getattr(exp, "activation_energy", 1.0), 1.0)),
                    repetition_count=max(1, int(getattr(exp, "reinforcement_count", 1))),
                    reward_signal=self._safe_float(getattr(exp, "reward", 0.0), 0.0),
                    source_experience=exp,
                    last_decay_ts=self._safe_float(getattr(exp, "last_activated", time.time()), time.time()),
                )
            else:
                found.repetition_count = max(1, int(getattr(exp, "reinforcement_count", found.repetition_count)))
                found.activation_weight = self._clamp(
                    self._safe_float(getattr(exp, "activation_energy", found.activation_weight), found.activation_weight)
                )
                found.source_experience = exp
                if not found.feature_set:
                    found.feature_set = self._sparsify_features(
                        self._extract_features_from_path(exp.path, getattr(exp, "consequence", None))
                    )
                if not getattr(found, "context_tokens", None):
                    found.context_tokens = self._build_context_tokens(found.feature_set)
            rebuilt.append(found)
            self._stamp_signature(found)
        self.signatures = rebuilt
        self._nov_valid = False

    def _decay_factor_for(self, elapsed: float) -> float:
        """Multiplicative retention after ``elapsed`` seconds. One factor per stamp."""
        if elapsed <= 0.0:
            return 1.0
        decay_steps = elapsed / self.activation_decay_half_life
        half_life_factor = 0.5 ** decay_steps
        decay_rate = self.decay_rate
        # Half-life remains the primary decay dynamic.
        # decay_rate is a soft regularizer so collapse is not only the half-life.
        if decay_rate > 0.0:
            retention_bias = (1.0 - decay_rate) ** decay_steps
            decay_factor = (0.90 * half_life_factor) + (0.10 * retention_bias)
        else:
            decay_factor = half_life_factor if half_life_factor <= 1.0 else 1.0
        if decay_factor < 0.0:
            return 0.0
        if decay_factor > 1.0:
            return 1.0
        return decay_factor

    def _apply_decay(self) -> None:
        if not self.signatures:
            return

        now = time.time()
        # One closed-form factor per distinct timestamp. Sharing the factor
        # does not skip a gap and does not quantize time: weight * factor(elapsed)
        # is the same number the per-episode formula produces.
        anchor = self.signatures[0].last_decay_ts
        factors: Dict[float, float] = {}
        elapsed_anchor = now - anchor
        if elapsed_anchor > 0.0:
            factors[anchor] = self._decay_factor_for(elapsed_anchor)
        min_weight = 1.0
        any_elapsed = False
        for sig in self.signatures:
            ts = sig.last_decay_ts
            elapsed = now - ts
            if elapsed <= 0.0:
                weight = sig.activation_weight
                if weight < min_weight:
                    min_weight = weight
                continue
            any_elapsed = True
            decay_factor = factors.get(ts)
            if decay_factor is None:
                decay_factor = self._decay_factor_for(elapsed)
                factors[ts] = decay_factor
            weight = sig.activation_weight * decay_factor
            if weight < 0.0:
                weight = 0.0
            elif weight > 1.0:
                weight = 1.0
            sig.activation_weight = weight

            exp = sig.source_experience
            if exp is not None:
                energy = exp.activation_energy * decay_factor
                if energy < 0.0:
                    energy = 0.0
                elif energy > 1.0:
                    energy = 1.0
                exp.activation_energy = energy
            sig.last_decay_ts = now
            if weight < min_weight:
                min_weight = weight

        # A second recall in the same instant used to rebuild both lists anyway.
        if not any_elapsed or min_weight >= self.activation_threshold:
            return

        threshold = self.activation_threshold
        for exp, sig in zip(self.experiences, self.signatures):
            if sig.activation_weight >= threshold:
                continue
            if int(getattr(exp, "reinforcement_count", 1)) >= 2:
                continue
            if self._safe_float(getattr(exp, "stability", 0.0), 0.0) >= 1.0:
                continue
            break
        else:
            return

        keep_exps: List[Experience] = []
        keep_sigs: List[SignatureTrace] = []
        for exp, sig in zip(self.experiences, self.signatures):
            strong_enough = sig.activation_weight >= threshold
            repeated = int(getattr(exp, "reinforcement_count", 1)) >= 2
            stable = self._safe_float(getattr(exp, "stability", 0.0), 0.0) >= 1.0
            if strong_enough or repeated or stable:
                keep_exps.append(exp)
                keep_sigs.append(sig)

        self.experiences = keep_exps
        self.signatures = keep_sigs
        self._nov_valid = False
        self._sync_episode_index()

    def _ids_in_use(self) -> Set[str]:
        used: Set[str] = set()
        for exp in self.experiences:
            episode_id = getattr(exp, "episode_id", None)
            if episode_id:
                used.add(str(episode_id))
        for episode_id in self._episodes_by_id.keys():
            used.add(str(episode_id))
        return used

    def _highest_episode_seq(self) -> int:
        highest = 0
        for episode_id in self._ids_in_use():
            if not str(episode_id).startswith("ep-"):
                continue
            try:
                highest = max(highest, int(str(episode_id)[3:]))
            except ValueError:
                continue
        return highest

    def _assign_episode_id(self, exp: Experience) -> str:
        """Give an experience a stable id that does not depend on list order.

        Never reuse an id that already belongs to a stored episode, even if
        the counter was reset by a reload.
        """
        existing = getattr(exp, "episode_id", None)
        if existing:
            key = str(existing)
            owner = self._episodes_by_id.get(key)
            if owner is None or owner is exp:
                # A reload can leave the counter behind the ids already stored.
                if key.startswith("ep-"):
                    try:
                        self._episode_seq = max(self._episode_seq, int(key[3:]))
                    except ValueError:
                        pass
                self._episodes_by_id[key] = exp
                return key
        stored_ids = sum(1 for exp in self.experiences if getattr(exp, "episode_id", None))
        # A reload can zero the counter and drop the index while the episodes
        # are still in the list. The fast path is only valid when every stored
        # id is still indexed; otherwise scan, same as a cold hippocampus.
        if (not self._episode_seq_ready) or stored_ids != len(self._episodes_by_id):
            self._episode_seq = max(int(self._episode_seq), self._highest_episode_seq())
            self._sync_episode_index()
            self._episode_seq_ready = True
        self._episode_seq += 1
        episode_id = f"ep-{self._episode_seq}"
        while episode_id in self._episodes_by_id:
            self._episode_seq += 1
            episode_id = f"ep-{self._episode_seq}"
        exp.episode_id = episode_id
        self._episodes_by_id[episode_id] = exp
        return episode_id

    def _sync_episode_index(self) -> None:
        """Rebuild the id index from the episodes that are still stored.

        The first resident with an id keeps it. A later duplicate does not
        steal the identity of the earlier episode.
        """
        index: Dict[str, Experience] = {}
        for exp in self.experiences:
            episode_id = getattr(exp, "episode_id", None)
            if not episode_id:
                continue
            key = str(episode_id)
            if key not in index:
                index[key] = exp
        self._episodes_by_id = index

    def get_experience(self, episode_id: str):
        """Return the stored episode with this id, regardless of list position."""
        if episode_id is None:
            return None
        key = str(episode_id)
        resident = self._episodes_by_id.get(key)
        if resident is not None and any(item is resident for item in self.experiences):
            return resident
        self._sync_episode_index()
        return self._episodes_by_id.get(key)

    def _current_novelty_window(self) -> List[SignatureTrace]:
        if not self.signatures:
            return []
        width = self.novelty_window
        if len(self.signatures) <= width:
            return self.signatures
        return self.signatures[-width:]

    def _novelty_recompute_one(self, sig: SignatureTrace, window: Sequence[SignatureTrace]) -> None:
        max_sim = 0.0
        arg = 0
        second = 0.0
        arg2 = 0
        left = sig.feature_mask
        left_count = sig.feature_count
        jaccard = self._mask_jaccard
        for other in window:
            if other is sig:
                continue
            sim = jaccard(left, left_count, other.feature_mask, other.feature_count)
            other_id = id(other)
            if sim > max_sim:
                second = max_sim
                arg2 = arg
                max_sim = sim
                arg = other_id
            elif sim > second:
                second = sim
                arg2 = other_id
        sig._nov_max = max_sim
        sig._nov_arg = arg
        sig._nov_max2 = second
        sig._nov_arg2 = arg2
        sig._nov_ready = True

    def _novelty_note_pair(self, sig: SignatureTrace, sim: float, other_id: int) -> None:
        """Fold one still-resident comparison into the cached maximum."""
        if sim > sig._nov_max:
            sig._nov_max2 = sig._nov_max
            sig._nov_arg2 = sig._nov_arg
            sig._nov_max = sim
            sig._nov_arg = other_id
        elif sim > sig._nov_max2:
            sig._nov_max2 = sim
            sig._nov_arg2 = other_id

    def _novelty_note_added(self, added: SignatureTrace, window: Sequence[SignatureTrace]) -> None:
        added_mask = added.feature_mask
        added_count = added.feature_count
        added_id = id(added)
        jaccard = self._mask_jaccard
        for sig in self.signatures:
            if sig is added or not getattr(sig, "_nov_ready", False):
                self._novelty_recompute_one(sig, window)
                continue
            sim = jaccard(sig.feature_mask, sig.feature_count, added_mask, added_count)
            self._novelty_note_pair(sig, sim, added_id)

    def _sync_novelty_cache(self) -> None:
        """Keep per-episode max Jaccard against the last N signatures.

        The window is the tail of the chronological list (spec: last N
        episodes). Appending one episode slides that tail by one, so each
        stored episode needs one new comparison, not a fresh pass over N.
        """
        self._ensure_masks()
        window = self._current_novelty_window()
        new_ids = tuple(id(sig) for sig in window)
        old_ids = self._nov_ids
        if self._nov_valid and new_ids == old_ids:
            return
        if self._nov_valid and old_ids and new_ids == old_ids + (new_ids[-1],):
            self._novelty_note_added(window[-1], window)
            self._nov_ids = new_ids
            return
        if (
            self._nov_valid
            and old_ids
            and len(new_ids) == len(old_ids)
            and new_ids[:-1] == old_ids[1:]
        ):
            dropped_id = old_ids[0]
            added = window[-1]
            added_id = id(added)
            added_mask = added.feature_mask
            added_count = added.feature_count
            jaccard = self._mask_jaccard
            signatures = self.signatures
            # One comparison per stored episode. Inlined so the capacity slide
            # is not a Python call per episode. Ties promote the next episode
            # with the same similarity, which is the one a fresh scan would pick.
            for sig in signatures:
                if sig is added or not sig._nov_ready:
                    self._novelty_recompute_one(sig, window)
                    continue
                if sig._nov_arg == dropped_id:
                    if sig._nov_arg2 and sig._nov_max2 == sig._nov_max and sig._nov_arg2 != dropped_id:
                        sig._nov_arg = sig._nov_arg2
                        sig._nov_arg2 = 0
                        sig._nov_max2 = 0.0
                    else:
                        self._novelty_recompute_one(sig, window)
                        continue
                sim = jaccard(sig.feature_mask, sig.feature_count, added_mask, added_count)
                current = sig._nov_max
                if sim > current:
                    sig._nov_max2 = current
                    sig._nov_arg2 = sig._nov_arg
                    sig._nov_max = sim
                    sig._nov_arg = added_id
                elif sim > sig._nov_max2:
                    sig._nov_max2 = sim
                    sig._nov_arg2 = added_id
            self._nov_ids = new_ids
            self._nov_valid = True
            return
        for sig in self.signatures:
            self._novelty_recompute_one(sig, window)
        self._nov_ids = new_ids
        self._nov_valid = True

    def _novelty_from_cached(self, sig: SignatureTrace, scale: float) -> float:
        base = 1.0 - float(getattr(sig, "_nov_max", 0.0))
        scaled = base * scale
        if scaled < 0.0:
            return 0.0
        if scaled > 1.0:
            return 1.0
        return scaled

    def _enforce_capacity(self, protect_id: Optional[str] = None) -> None:
        if len(self.experiences) <= self.max_experiences:
            self.last_evicted = []
            return

        # Drop the lowest scores in place. Rewriting the list in score order
        # made the next "last N" window the low-score tail instead of the
        # latest episodes, and forced a full novelty pass on every store.
        self._sync_novelty_cache()
        bias = self.novelty_capacity_bias
        keep_bias = 1.0 - bias
        overflow = len(self.experiences) - self.max_experiences
        protected = str(protect_id) if protect_id else ""
        scale = self.novelty_sensitivity_scale
        if scale < 0.5:
            scale = 0.5
        elif scale > 2.0:
            scale = 2.0
        # Higher tuple is kept. Equal scores keep the earlier episode, matching
        # a stable descending sort. One store overflows by one, so the victim
        # is a linear minimum rather than a full sort of the memory.
        def _rank_key(index: int, exp: Experience, sig: SignatureTrace):
            novelty = self._novelty_from_cached(sig, scale)
            activation = sig.activation_weight
            novelty_blend = (keep_bias * activation) + (bias * novelty)
            return (
                novelty_blend,
                novelty,
                int(getattr(exp, "reinforcement_count", 1)),
                float(getattr(exp, "last_activated", 0.0) or 0.0),
                -index,
            )

        drop_indexes = set()
        if overflow == 1:
            experiences = self.experiences
            signatures = self.signatures
            worst_key = None
            worst_index = -1
            spare_key = None
            spare_index = -1
            count = len(experiences)
            for index in range(count):
                exp = experiences[index]
                sig = signatures[index]
                base = 1.0 - sig._nov_max
                novelty = base * scale
                if novelty < 0.0:
                    novelty = 0.0
                elif novelty > 1.0:
                    novelty = 1.0
                blend = (keep_bias * sig.activation_weight) + (bias * novelty)
                key = (
                    blend,
                    novelty,
                    exp.reinforcement_count,
                    exp.last_activated,
                    -index,
                )
                if protected and exp.episode_id == protected:
                    if spare_key is None or key < spare_key:
                        spare_key = key
                        spare_index = index
                    continue
                if worst_key is None or key < worst_key:
                    worst_key = key
                    worst_index = index
            if worst_index >= 0:
                drop_indexes.add(worst_index)
            elif spare_index >= 0:
                drop_indexes.add(spare_index)
        else:
            ranked = []
            for index, (exp, sig) in enumerate(zip(self.experiences, self.signatures)):
                ranked.append((_rank_key(index, exp, sig), index, exp))
            ranked.sort(reverse=True)
            for item in reversed(ranked):
                if len(drop_indexes) >= overflow:
                    break
                exp = item[2]
                if protected and str(getattr(exp, "episode_id", "")) == protected:
                    continue
                drop_indexes.add(item[1])
            if len(drop_indexes) < overflow:
                for item in reversed(ranked):
                    if len(drop_indexes) >= overflow:
                        break
                    drop_indexes.add(item[1])
        self.last_evicted = []
        if len(drop_indexes) == 1:
            index = next(iter(drop_indexes))
            exp = self.experiences[index]
            self.last_evicted.append(exp)
            episode_id = getattr(exp, "episode_id", None)
            if episode_id and self._episodes_by_id.get(str(episode_id)) is exp:
                del self._episodes_by_id[str(episode_id)]
            del self.experiences[index]
            del self.signatures[index]
        else:
            keep_exps = []
            keep_sigs = []
            for index, (exp, sig) in enumerate(zip(self.experiences, self.signatures)):
                if index in drop_indexes:
                    self.last_evicted.append(exp)
                    episode_id = getattr(exp, "episode_id", None)
                    if episode_id and self._episodes_by_id.get(str(episode_id)) is exp:
                        del self._episodes_by_id[str(episode_id)]
                    continue
                keep_exps.append(exp)
                keep_sigs.append(sig)
            self.experiences = keep_exps
            self.signatures = keep_sigs
        # Cache still describes the pre-removal tail. Resync slides it when
        # the dropped episode was inside the window, and is a no-op otherwise.
        self._sync_novelty_cache()

    def _build_query_signature(
        self, current_signature, consequence=None, intensity: float = 1.0
    ) -> Tuple[Set[str], Tuple[float, float, float], Tuple[float, float, float], float, Tuple[str, ...]]:
        now = time.time()

        if isinstance(current_signature, dict):
            raw_features = current_signature.get("features", current_signature.get("feature_set", []))
            features = self._sparsify_features(self._sanitize_features(raw_features))
            drive_vector = self._build_drive_vector(
                intensity=current_signature.get("intensity", intensity),
                reward=current_signature.get("reward", 0.0),
                encoding_strength=current_signature.get("encoding_strength", current_signature.get("drive_state", None)),
                drive_state=current_signature.get("drive_vector", current_signature.get("drive_state", None)),
            )
            timestamp = self._safe_float(current_signature.get("timestamp", now), now)
            supplied_context = current_signature.get("context_vector")
            supplied_tokens = current_signature.get("context_tokens")
            if isinstance(supplied_tokens, (tuple, list)):
                context_tokens = tuple(str(x) for x in list(supplied_tokens)[-self.context_history_size :])
            else:
                context_tokens = self._build_context_tokens(features)
            if isinstance(supplied_context, (list, tuple)) and len(supplied_context) >= 3:
                context_vector = (
                    self._safe_float(supplied_context[0]),
                    self._safe_float(supplied_context[1]),
                    self._safe_float(supplied_context[2]),
                )
            else:
                context_vector = self._encode_context_vector(
                    features,
                    drive_vector,
                    timestamp,
                    context_tokens=context_tokens,
                )
            return features, drive_vector, context_vector, timestamp, context_tokens

        path = self._to_path(current_signature)
        features = self._sparsify_features(self._extract_features_from_path(path, consequence))
        drive_vector = self._build_drive_vector(intensity=intensity)
        context_tokens = self._build_context_tokens(features)
        context_vector = self._encode_context_vector(
            features,
            drive_vector,
            now,
            context_tokens=context_tokens,
        )
        return features, drive_vector, context_vector, now, context_tokens

    def store(
        self,
        path,
        consequence=None,
        intensity: float = 1.0,
        reward: float = 0.0,
        encoding_strength: float = None,
    ) -> Experience:
        self._ensure_signature_store()
        self._apply_decay()

        signature_input = path if isinstance(path, dict) else None
        if signature_input is not None and ("features" in signature_input or "feature_set" in signature_input):
            features, drive_vector, context_vector, timestamp, context_tokens = self._build_query_signature(
                signature_input, consequence=consequence, intensity=intensity
            )
            path_obj = self._to_path(sorted(features))
        else:
            path_obj = self._to_path(path)
            features = self._sparsify_features(self._extract_features_from_path(path_obj, consequence))
            drive_vector = self._build_drive_vector(
                intensity=intensity,
                reward=reward,
                encoding_strength=encoding_strength,
            )
            timestamp = time.time()
            context_tokens = self._build_context_tokens(features)
            context_vector = self._encode_context_vector(
                features,
                drive_vector,
                timestamp,
                context_tokens=context_tokens,
            )

        exp = Experience(
            path_obj,
            consequence=consequence,
            intensity=intensity,
            reward=reward,
            encoding_strength=encoding_strength,
        )
        if signature_input is not None and "timestamp" in signature_input:
            ts = self._safe_float(signature_input.get("timestamp", time.time()), time.time())
            exp.timestamp = ts
            exp.first_seen = ts
            exp.last_activated = ts

        self._assign_episode_id(exp)
        self.experiences.append(exp)
        sig = SignatureTrace(
            feature_set=features,
            drive_vector=drive_vector,
            context_vector=context_vector,
            context_tokens=context_tokens,
            timestamp=self._safe_float(getattr(exp, "timestamp", timestamp), timestamp),
            activation_weight=self._safe_float(getattr(exp, "activation_energy", 1.0), 1.0),
            repetition_count=max(1, int(getattr(exp, "reinforcement_count", 1))),
            reward_signal=self._safe_float(reward, 0.0),
            source_experience=exp,
            last_decay_ts=time.time(),
        )
        self._stamp_signature(sig)
        self.signatures.append(sig)
        self._append_recent_events(path_obj.signature())
        self._enforce_capacity(protect_id=str(getattr(exp, "episode_id", "") or ""))
        return exp
    def reinforce(self, path, consequence=None, intensity: float = 1.0):
        self._ensure_signature_store()
        self._apply_decay()

        query_features, query_drive, query_context, _, query_tokens = self._build_query_signature(
            path, consequence=consequence, intensity=intensity
        )

        best_similarity = -1.0
        best_sig: Optional[SignatureTrace] = None
        query_mask, query_count = self._bits_for(query_features, self._feature_bits)
        if not isinstance(query_tokens, tuple):
            query_tokens = tuple(str(token) for token in (query_tokens or ()))
        token_mask, token_count = self._bits_for(query_tokens, self._token_bits)
        for sig in self.signatures:
            sim = self._fast_similarity(
                query_mask,
                query_count,
                query_drive,
                query_context,
                query_tokens,
                token_mask,
                token_count,
                sig,
            )
            if sim > best_similarity:
                best_similarity = sim
                best_sig = sig

        if best_sig is not None and best_similarity >= self.reinforce_similarity_threshold:
            exp = best_sig.source_experience
            if exp is None:
                return self.store(path, consequence=consequence, intensity=intensity)

            exp.reinforcement_count += 1
            exp.last_activated = time.time()
            exp.activation_energy = self._clamp(
                max(self._safe_float(getattr(exp, "activation_energy", 1.0), 1.0), best_similarity)
            )
            exp.intensity = max(self._safe_float(getattr(exp, "intensity", 0.0), 0.0), float(intensity))

            best_sig.feature_set = self._sparsify_features(set(best_sig.feature_set) | set(query_features))
            best_sig.repetition_count = int(getattr(exp, "reinforcement_count", best_sig.repetition_count))
            best_sig.activation_weight = self._safe_float(getattr(exp, "activation_energy", best_sig.activation_weight))
            blend_n = max(1.0, float(best_sig.repetition_count))
            best_sig.drive_vector = tuple(
                ((a * (blend_n - 1.0)) + b) / blend_n for a, b in zip(best_sig.drive_vector, query_drive)
            )
            best_sig.context_vector = self._encode_context_vector(best_sig.feature_set, best_sig.drive_vector, time.time())
            best_sig.context_tokens = self._build_context_tokens(best_sig.feature_set)
            self._stamp_signature(best_sig)
            self._nov_valid = False
            self._append_recent_events(list(query_features))
            return exp

        return self.store(path, consequence=consequence, intensity=intensity)

    def activate(self, context_events: list) -> list:
        self._ensure_signature_store()
        self._apply_decay()

        if not self.experiences:
            return []

        context_features = self._sanitize_features(context_events or [])
        now = time.time()

        if not context_features:
            activated_all = []
            for exp, sig in zip(self.experiences, self.signatures):
                exp.last_activated = now
                exp.activation_energy = self._clamp(max(self._safe_float(exp.activation_energy, 0.0), sig.activation_weight))
                sig.activation_weight = self._safe_float(exp.activation_energy, sig.activation_weight)
                activated_all.append(exp)
            return activated_all

        query_drive = self._build_drive_vector(intensity=1.0)
        query_tokens = self._build_context_tokens(context_features)
        query_context = self._encode_context_vector(
            context_features,
            query_drive,
            now,
            context_tokens=query_tokens,
        )
        query_mask, query_count = self._bits_for(context_features, self._feature_bits)
        token_mask, token_count = self._bits_for(query_tokens, self._token_bits)
        threshold = self.activation_similarity_threshold
        self._ensure_masks()

        # Same blend as _fast_similarity. Context similarity is at most 1, so a
        # feature+drive upper bound below the threshold cannot be a match.
        # The bound stays off the per-pair call so the scan is one Python loop.
        qd0, qd1, qd2 = query_drive
        qc0, qc1, qc2 = query_context
        qlen = len(query_tokens)
        cyc = float(self.cycle_length if self.cycle_length > 1 else 1)
        hash_span = float((1 << 64) - 1)
        jaccard = self._mask_jaccard
        sqrt = math.sqrt
        early_limit = threshold - 1e-12
        use_cached_drive = qd0 == 1.0 and qd1 == 0.0 and qd2 == 1.0
        matches = []
        for exp, sig in zip(self.experiences, self.signatures):
            if sig._fs_key == query_mask:
                feature_sim = sig._fs_val
            else:
                feature_sim = jaccard(query_mask, query_count, sig.feature_mask, sig.feature_count)
                sig._fs_key = query_mask
                sig._fs_val = feature_sim
            if use_cached_drive:
                drive_sim = sig._activate_drive_sim
            else:
                drive = sig.drive_vector
                dist = sqrt(
                    (qd0 - drive[0]) ** 2 + (qd1 - drive[1]) ** 2 + (qd2 - drive[2]) ** 2
                )
                drive_sim = 1.0 / (1.0 + dist)
            if (0.80 * feature_sim) + (0.15 * drive_sim) + 0.05 < early_limit:
                continue
            stored_tokens = sig.context_tokens or ()
            if not query_tokens or not stored_tokens:
                window_sim = 0.0
            else:
                set_sim = jaccard(token_mask, token_count, sig.token_mask, sig.token_count)
                slen = len(stored_tokens)
                limit = qlen if qlen < slen else slen
                positional = 0.0
                for idx in range(limit):
                    if query_tokens[idx] == stored_tokens[idx]:
                        positional += 1.0
                max_len = qlen if qlen > slen else slen
                window_sim = (0.75 * set_sim) + (0.25 * (positional / float(max_len or 1)))
                if window_sim < 0.0:
                    window_sim = 0.0
                elif window_sim > 1.0:
                    window_sim = 1.0
            s_ctx = sig.context_vector
            time_delta = qc0 - s_ctx[0]
            if time_delta < 0.0:
                time_delta = -time_delta
            time_sim = 1.0 - (time_delta if time_delta < cyc else cyc) / cyc
            hash_delta = qc1 - s_ctx[1]
            if hash_delta < 0.0:
                hash_delta = -hash_delta
            hash_sim = 1.0 - (hash_delta / hash_span)
            if hash_sim < 0.0:
                hash_sim = 0.0
            elif hash_sim > 1.0:
                hash_sim = 1.0
            ctx_delta = qc2 - s_ctx[2]
            if ctx_delta < 0.0:
                ctx_delta = -ctx_delta
            ctx_drive = 1.0 - (ctx_delta / 9.0)
            if ctx_drive < 0.0:
                ctx_drive = 0.0
            elif ctx_drive > 1.0:
                ctx_drive = 1.0
            context_sim = (0.30 * time_sim) + (0.15 * hash_sim) + (0.20 * ctx_drive) + (0.35 * window_sim)
            similarity = (0.80 * feature_sim) + (0.15 * drive_sim) + (0.05 * context_sim)
            if similarity < 0.0:
                similarity = 0.0
            elif similarity > 1.0:
                similarity = 1.0
            if similarity >= threshold:
                exp.last_activated = now
                energy = exp.activation_energy
                if similarity > energy:
                    energy = similarity
                if energy < 0.0:
                    energy = 0.0
                elif energy > 1.0:
                    energy = 1.0
                exp.activation_energy = energy
                sig.activation_weight = energy
                matches.append((similarity, exp))

        if not matches:
            ranked = []
            for exp, sig in zip(self.experiences, self.signatures):
                if not getattr(sig, "_mask_ready", False):
                    self._stamp_signature(sig)
                ranked.append(
                    (
                        self._mask_jaccard(query_mask, query_count, sig.feature_mask, sig.feature_count),
                        exp,
                        sig,
                    )
                )
            ranked.sort(key=lambda item: item[0], reverse=True)
            for similarity, exp, sig in ranked:
                if similarity <= 0.0:
                    break
                exp.last_activated = now
                energy = exp.activation_energy
                if similarity > energy:
                    energy = similarity
                if energy < 0.0:
                    energy = 0.0
                elif energy > 1.0:
                    energy = 1.0
                exp.activation_energy = energy
                sig.activation_weight = energy
                matches.append((similarity, exp))
                if len(matches) >= self.top_k_recall:
                    break

        matches.sort(key=lambda item: item[0], reverse=True)
        return [exp for _, exp in matches]

    def _novelty_from_recent(
        self,
        query_features: Set[str],
        exclude_signature: Optional[SignatureTrace] = None,
    ) -> float:
        recent = self.signatures[-self.novelty_window :]
        if not recent:
            return 1.0
        query_mask, query_count = self._bits_for(query_features, self._feature_bits)
        max_similarity = 0.0
        any_compared = False
        for sig in recent:
            if exclude_signature is not None and sig is exclude_signature:
                continue
            if not getattr(sig, "_mask_ready", False):
                self._stamp_signature(sig)
            any_compared = True
            similarity = self._mask_jaccard(query_mask, query_count, sig.feature_mask, sig.feature_count)
            if similarity > max_similarity:
                max_similarity = similarity
        if not any_compared:
            base = 1.0
        else:
            base = self._clamp(1.0 - max_similarity)
        scaled = base * self.get_novelty_sensitivity_scale()
        return self._clamp(scaled)

    def _reconstruct_features(self, top_k_entries: List[Tuple[float, SignatureTrace]]) -> Set[str]:
        if not top_k_entries:
            return set()

        total = sum(max(0.0, sim) for sim, _ in top_k_entries)
        if total <= 0.0:
            return set()

        weighted_scores: Dict[str, float] = {}
        for similarity, sig in top_k_entries:
            weight = max(0.0, similarity) / total
            for feature in sig.feature_set:
                weighted_scores[feature] = weighted_scores.get(feature, 0.0) + weight

        if not weighted_scores:
            return set()

        max_score = max(weighted_scores.values())
        adaptive_threshold = self._clamp(0.50 * max_score, 0.05, 0.45)
        reconstructed = {feature for feature, score in weighted_scores.items() if score >= adaptive_threshold}
        if reconstructed:
            return reconstructed

        best_feature = max(weighted_scores.items(), key=lambda item: item[1])[0]
        return {best_feature}

    def classify_novelty(self, novelty_score: float) -> str:
        score = self._clamp(novelty_score)
        if score < 0.2:
            return "familiar"
        if score <= 0.6:
            return "partial_match"
        if score <= 0.85:
            return "novel"
        return "high_novelty"

    def recall_signature(self, current_signature) -> dict:
        self._ensure_signature_store()
        self._apply_decay()

        query_features, query_drive, query_context, _, query_tokens = self._build_query_signature(current_signature)
        query_mask, query_count = self._bits_for(query_features, self._feature_bits)
        if not isinstance(query_tokens, tuple):
            query_tokens = tuple(str(token) for token in (query_tokens or ()))
        token_mask, token_count = self._bits_for(query_tokens, self._token_bits)
        similarity_entries: List[Tuple[float, SignatureTrace]] = []
        for sig in self.signatures:
            sim = self._fast_similarity(
                query_mask,
                query_count,
                query_drive,
                query_context,
                query_tokens,
                token_mask,
                token_count,
                sig,
            )
            if sim > 0.0:
                similarity_entries.append((sim, sig))

        similarity_entries.sort(key=lambda item: item[0], reverse=True)
        top_k = similarity_entries[: self.top_k_recall]
        reconstructed = self._reconstruct_features(top_k)
        novelty = self._novelty_from_recent(query_features)

        self._novelty_history.append(novelty)
        if len(self._novelty_history) > 500:
            self._novelty_history = self._novelty_history[-500:]

        similarity_payload = []
        for similarity, sig in top_k:
            similarity_payload.append(
                {
                    "similarity": float(similarity),
                    "features": set(sig.feature_set),
                    "timestamp": float(sig.timestamp),
                    "repetition_count": int(sig.repetition_count),
                }
            )

        return {
            "reconstructed_features": reconstructed,
            "novelty_score": float(novelty),
            "novelty_class": self.classify_novelty(novelty),
            "similarity_top_k": similarity_payload,
        }

    def recall_recent(self, limit: Optional[int] = None) -> list:
        self._ensure_signature_store()
        self._apply_decay()
        k = max(1, int(limit or self.top_k_recall))
        return list(self.experiences)[-k:]

    def recall(self, current_signature=None, *, active_drive=None, limit: Optional[int] = None):
        """
        Backward-compatible dispatcher.

        Preferred explicit APIs:
        - recall_signature(signature_query)
        - recall_recent(limit)
        - recall_by_drive(active_drive, limit)
        """
        if isinstance(current_signature, int) and active_drive is None and limit is None:
            return self.recall_recent(limit=int(current_signature))

        if active_drive is not None and current_signature is None:
            return self.recall_by_drive(active_drive=active_drive, limit=int(limit or self.top_k_recall))

        if current_signature is None:
            return self.recall_recent(limit=limit)

        return self.recall_signature(current_signature)

    def recall_by_drive(self, active_drive: str, limit: int = 6) -> list:
        self._ensure_signature_store()
        self._apply_decay()

        token = str(active_drive or "").strip()
        k = max(1, int(limit))
        if not token:
            return list(self.experiences)[-k:]

        scored = []
        for exp, sig in zip(self.experiences, self.signatures):
            score = 1.0 if any(token in feature for feature in sig.feature_set) else 0.0
            if score <= 0.0:
                score = self._jaccard_similarity({token}, sig.feature_set)
            if score > 0.0:
                scored.append((score, exp))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [exp for _, exp in scored[:k]]

    def consolidation_probability(
        self, novelty_score: float, repetition_count: int, reward_signal: float = 0.0
    ) -> float:
        novelty = self._clamp(novelty_score)
        repetition_factor = self._clamp(float(max(0, int(repetition_count))) / 5.0)
        reward_norm = self._clamp((self._safe_float(reward_signal, 0.0) + 1.0) / 2.0)
        reward_weight = 0.4 + (0.6 * reward_norm)
        probability = (novelty * reward_weight) + (0.35 * repetition_factor)
        return self._clamp(probability)

    def get_candidates_for_sleep(self, min_reinforcement: int = 2) -> list:
        self._ensure_signature_store()
        self._apply_decay()

        candidates = []
        for exp, sig in zip(self.experiences, self.signatures):
            reinforcement = int(getattr(exp, "reinforcement_count", 1))
            activation = self._safe_float(getattr(exp, "activation_energy", 0.0), 0.0)
            stability = self._safe_float(getattr(exp, "stability", 0.0), 0.0)
            novelty = self._novelty_from_recent(sig.feature_set, exclude_signature=sig)
            probability = self.consolidation_probability(
                novelty_score=novelty,
                repetition_count=reinforcement,
                reward_signal=self._safe_float(getattr(exp, "reward", 0.0), 0.0),
            )
            exp.novelty_score = novelty
            exp.consolidation_probability = probability

            if (
                reinforcement >= int(min_reinforcement)
                and activation > 0.5
                and stability < 1.0
                and probability >= self.consolidation_min_probability
            ):
                candidates.append((reinforcement, activation, probability, exp))

        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return [item[3] for item in candidates]

    def get_statistics(self) -> dict:
        self._ensure_signature_store()
        self._apply_decay()

        if not self.experiences:
            return {
                "total_experiences": 0,
                "avg_reinforcement": 0,
                "avg_activation": 0,
                "avg_stability": 0,
                "total_signatures": 0,
                "avg_novelty_recent": 0,
                "familiar_ratio": 0,
                "partial_match_ratio": 0,
                "novel_ratio": 0,
                "high_novelty_ratio": 0,
            }

        total = len(self.experiences)
        novelties = [
            self._novelty_from_recent(sig.feature_set, exclude_signature=sig)
            for sig in self.signatures[-self.novelty_window :]
        ]
        if not novelties:
            novelties = [0.0]

        familiar = 0
        partial = 0
        novel = 0
        high_novel = 0
        for score in novelties:
            label = self.classify_novelty(score)
            if label == "familiar":
                familiar += 1
            elif label == "partial_match":
                partial += 1
            elif label == "novel":
                novel += 1
            else:
                high_novel += 1

        denom = float(len(novelties))
        return {
            "total_experiences": total,
            "avg_reinforcement": sum(e.reinforcement_count for e in self.experiences) / total,
            "avg_activation": sum(self._safe_float(e.activation_energy, 0.0) for e in self.experiences) / total,
            "avg_stability": sum(self._safe_float(e.stability, 0.0) for e in self.experiences) / total,
            "total_signatures": len(self.signatures),
            "avg_novelty_recent": sum(novelties) / denom,
            "familiar_ratio": familiar / denom,
            "partial_match_ratio": partial / denom,
            "novel_ratio": novel / denom,
            "high_novelty_ratio": high_novel / denom,
        }
