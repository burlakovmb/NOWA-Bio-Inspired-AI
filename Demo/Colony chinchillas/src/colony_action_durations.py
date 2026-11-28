"""Dataset durations for colony actions.

Reads ``output.duration`` from the realization files listed in
``scenario_datasets``. Several realizations of one action contribute the
union of their ranges. Social offers prefer
``chinchilla_realizations_colony_social.json``. A missing file or an
action with no realization falls back to ``(10, 30)`` and logs one warning.
"""

from __future__ import annotations

import json
import logging
import random
from functools import lru_cache
from pathlib import Path
from typing import Any

from config_colony import ACTION_HOLD, ACTION_HOLD_INTERRUPT_THRESHOLD

logger = logging.getLogger(__name__)

FALLBACK_DURATION_S: tuple[float, float] = (10.0, 30.0)

SOCIAL_DATASET_NAME = "chinchilla_realizations_colony_social.json"

# Abstract colony actions -> dataset intent_type ids. The union of those
# realizations is the hold range. Social offer ids are read as themselves.
ACTION_REALIZATIONS: dict[str, tuple[str, ...]] = {
    "eat": ("eat_pellets", "eat_hay"),
    "drink": ("drink_water",),
    "sleep": ("sleep_house",),
    "groom_self": ("groom_body", "groom_face", "groom_paws", "groom_tail"),
    "run_wheel": ("run_wheel",),
    "hide": ("hide_house",),
    "explore": ("explore_corner", "patrol_floor"),
    "socialize": ("approach_peer", "sniff_peer"),
    "play": ("play_toy", "jump_hop_play"),
    "rest": ("rest_loaf",),
    "flee": ("flee_corner", "flee_rival"),
    "mount_display": ("mount_display",),
}

SOCIAL_ACTIONS: frozenset[str] = frozenset(
    {
        "sniff_greet",
        "allogroom",
        "play_invite",
        "sleep_together",
        "chase",
        "mount_display",
        "nurse",
        "share_knowledge",
    }
)

DEFAULT_DATASET_NAMES: tuple[str, ...] = (
    "chinchilla_realizations_basic.json",
    "chinchilla_realizations_extended.json",
    "chinchilla_realizations_advanced.json",
    SOCIAL_DATASET_NAME,
)


def realizations_for(action: str) -> tuple[str, ...]:
    """Dataset intent ids that realize one colony action."""
    return ACTION_REALIZATIONS.get(str(action or ""), ())


def _dataset_dirs() -> tuple[Path, ...]:
    demo_dir = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[3]
    return (
        demo_dir / "Datasets",
        demo_dir / "datasets",
        repo_root / "datasets",
    )


def _parse_duration(value: Any) -> tuple[tuple[float, float] | None, str | None]:
    """``(range, note)``. Note is ``swap`` or ``non_positive``.

    Non-positive bounds are dropped. ``min > max`` is swapped and kept.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None, None
    try:
        low = float(value[0])
        high = float(value[1])
    except (TypeError, ValueError):
        return None, None
    if not (low == low and high == high):
        return None, None
    if low in (float("inf"), float("-inf")) or high in (float("inf"), float("-inf")):
        return None, None
    if low <= 0.0 or high <= 0.0:
        return None, "non_positive"
    if high < low:
        return (high, low), "swap"
    return (low, high), None


def _union(ranges: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not ranges:
        return None
    return (min(item[0] for item in ranges), max(item[1] for item in ranges))


class ActionDurationTable:
    """Hold ranges keyed by colony action and by raw intent id."""

    def __init__(
        self,
        intent_ranges: dict[str, tuple[float, float]],
        social_ranges: dict[str, tuple[float, float]],
        *,
        missing_files: tuple[str, ...] = (),
        notes: tuple[str, ...] = (),
    ) -> None:
        self.intent_ranges = dict(intent_ranges)
        self.social_ranges = dict(social_ranges)
        self.missing_files = tuple(missing_files)
        self._warned_fallback = False
        self._warned_swap = False
        if missing_files:
            self._warn_fallback(
                "action duration dataset missing (%s); fallback (10, 30) s"
                % ", ".join(missing_files)
            )
        if "non_positive" in notes:
            self._warn_fallback(
                "non-positive action duration ignored; fallback (10, 30) s"
            )
        if "swap" in notes:
            self._warn_swap()

    def _warn_fallback(self, message: str) -> None:
        if self._warned_fallback:
            return
        self._warned_fallback = True
        logger.warning(message)

    def _warn_swap(self) -> None:
        if self._warned_swap:
            return
        self._warned_swap = True
        logger.warning("action duration min>max swapped")

    def range_for(self, action: str) -> tuple[float, float]:
        """``(min, max)`` seconds. Fallback ``(10, 30)`` logs one warning."""
        name = str(action or "").strip()
        if name in SOCIAL_ACTIONS and name in self.social_ranges:
            return self.social_ranges[name]
        mapped = realizations_for(name)
        if mapped:
            union = _union(
                [self.intent_ranges[item] for item in mapped if item in self.intent_ranges]
            )
            if union is not None:
                return union
        if name in self.intent_ranges:
            return self.intent_ranges[name]
        self._warn_fallback(
            "no dataset duration for action %r; fallback (10, 30) s" % (name or "?",)
        )
        return FALLBACK_DURATION_S

    def sample(self, action: str, rng: random.Random) -> float:
        low, high = self.range_for(action)
        if high <= low:
            return float(low)
        return float(rng.uniform(low, high))


def _read_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _accumulate(
    rows: list[dict[str, Any]],
    into: dict[str, list[tuple[float, float]]],
    notes: set[str],
) -> None:
    for row in rows:
        intent = str(row.get("intent_type") or "").strip()
        if not intent:
            continue
        output = row.get("output")
        if not isinstance(output, dict):
            output = row
        parsed, note = _parse_duration(output.get("duration"))
        if note:
            notes.add(note)
        if parsed is None:
            continue
        into.setdefault(intent, []).append(parsed)


def _profile_payload(dataset_dir: Path | None) -> dict[str, Any]:
    directories = (dataset_dir,) if dataset_dir is not None else _dataset_dirs()
    for directory in directories:
        if directory is None or not directory.exists():
            continue
        for name in ("colony_agent_profile.json", "colony_behavior_profile.json"):
            path = directory / name
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload
    return {}


def load_action_durations(
    dataset_dir: Path | None = None,
    filenames: tuple[str, ...] | None = None,
) -> ActionDurationTable:
    """Load duration ranges. ``dataset_dir`` overrides the demo Datasets folder."""
    profile = _profile_payload(dataset_dir)
    names = filenames
    if names is None:
        raw = profile.get("scenario_datasets")
        if isinstance(raw, (list, tuple)) and raw:
            names = tuple(str(item) for item in raw if str(item).strip())
        else:
            names = DEFAULT_DATASET_NAMES
    directories = (dataset_dir,) if dataset_dir is not None else _dataset_dirs()
    search_dirs = [path for path in directories if path is not None and path.exists()]
    intent_bucket: dict[str, list[tuple[float, float]]] = {}
    social_bucket: dict[str, list[tuple[float, float]]] = {}
    missing: list[str] = []
    notes: set[str] = set()
    for name in names:
        found: Path | None = None
        for directory in search_dirs:
            candidate = directory / name
            if candidate.exists():
                found = candidate
                break
        if found is None:
            missing.append(name)
            continue
        try:
            rows = _read_json(found)
        except (OSError, json.JSONDecodeError):
            missing.append(name)
            continue
        _accumulate(rows, intent_bucket, notes)
        if Path(name).name == SOCIAL_DATASET_NAME:
            _accumulate(rows, social_bucket, notes)
    intent_ranges = {
        key: union
        for key, values in intent_bucket.items()
        if (union := _union(values)) is not None
    }
    social_ranges = {
        key: union
        for key, values in social_bucket.items()
        if (union := _union(values)) is not None
    }
    return ActionDurationTable(
        intent_ranges,
        social_ranges,
        missing_files=tuple(missing),
        notes=tuple(sorted(notes)),
    )


@lru_cache(maxsize=1)
def get_duration_table() -> ActionDurationTable:
    return load_action_durations()


def sample_action_duration(action: str, rng: random.Random) -> float:
    return get_duration_table().sample(action, rng)


@lru_cache(maxsize=1)
def _profile_hold_keys() -> tuple[bool, float, bool, bool]:
    """``(enabled, threshold, saw_enabled, saw_threshold)`` from the profile."""
    payload = _profile_payload(None)
    saw_enabled = "action_hold" in payload
    saw_threshold = "action_hold_interrupt_threshold" in payload
    enabled = bool(payload.get("action_hold", ACTION_HOLD))
    try:
        threshold = float(payload.get("action_hold_interrupt_threshold", ACTION_HOLD_INTERRUPT_THRESHOLD))
    except (TypeError, ValueError):
        threshold = float(ACTION_HOLD_INTERRUPT_THRESHOLD)
    if threshold != threshold or threshold in (float("inf"), float("-inf")):
        threshold = float(ACTION_HOLD_INTERRUPT_THRESHOLD)
    return enabled, threshold, saw_enabled, saw_threshold


def resolve_action_hold(
    enabled: bool | None,
    threshold: float | None,
) -> tuple[bool, float]:
    """Constructor overrides the profile key, which overrides ``config_colony``."""
    file_enabled, file_threshold, saw_enabled, saw_threshold = _profile_hold_keys()
    if enabled is None:
        enabled = file_enabled if saw_enabled else bool(ACTION_HOLD)
    if threshold is None:
        threshold = file_threshold if saw_threshold else float(ACTION_HOLD_INTERRUPT_THRESHOLD)
    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError):
        threshold_value = float(ACTION_HOLD_INTERRUPT_THRESHOLD)
    if threshold_value != threshold_value or threshold_value < 0.0:
        threshold_value = float(ACTION_HOLD_INTERRUPT_THRESHOLD)
    return bool(enabled), threshold_value
