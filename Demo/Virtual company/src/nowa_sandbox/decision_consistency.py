"""Domain-neutral consistency of a repeated choice in a repeated situation.

A situation is the set of context tokens that belong to one entity. Which
parameter names, which token prefixes, and which result statuses count is
entirely a :class:`ConsistencyConfig`. This module does not know any host
domain.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ConsistencyConfig:
    """How a host names an entity, a choice, and the tokens tied to them."""

    entity_field: str = "entity"
    choice_field: str = "choice"
    attached_prefixes: Tuple[str, ...] = ()
    counted_statuses: Tuple[str, ...] = ("accepted",)
    min_decisions: int = 3
    neutral: float = 0.5


@dataclass
class ConsistencyReport:
    """Score plus the counts behind it, and the previous by-entity formula."""

    value: float
    situations_used: int
    decisions_used: int
    by_entity_legacy: float


def situation_tokens(
    context_events,
    entity_id,
    attached_prefixes=(),
) -> Tuple[str, ...]:
    """Sorted unique context tokens that belong to ``entity_id``.

    A token belongs to entity ``E`` when ``str(E)`` equals one of the fields
    after the first ``:``-separated field. The first field is the token type
    and is not compared. A token that starts with one of ``attached_prefixes``
    belongs to ``E`` when the nearest previous token that does not start with
    an attached prefix belongs to ``E``. Any other non-attached token between
    them breaks that link.

    ``entity_id is None``, an empty context, or an entity with no matching
    token yields an empty tuple.
    """
    if entity_id is None or not context_events:
        return ()
    entity = str(entity_id)
    prefixes = tuple(attached_prefixes or ())
    try:
        events = [str(token) for token in context_events]
    except TypeError:
        return ()

    found = set()
    anchor_matches = False
    for token in events:
        if _starts_with_attached_prefix(token, prefixes):
            if anchor_matches:
                found.add(token)
            continue
        anchor_matches = _token_names_entity(token, entity)
        if anchor_matches:
            found.add(token)
    return tuple(sorted(found))


def decision_fields(call_params, tool, context_events, config) -> dict:
    """Fields to store beside a call. Never raises.

    ``call_params is None`` means no call was made.
    """
    empty = {"tool": None, "entity": None, "choice": None, "situation": []}
    if call_params is None:
        return empty
    try:
        entity = _read_field(call_params, config.entity_field)
        choice = _read_field(call_params, config.choice_field)
        situation = list(
            situation_tokens(
                context_events, entity, config.attached_prefixes
            )
        )
    except Exception:
        return empty
    return {
        "tool": tool,
        "entity": entity,
        "choice": choice,
        "situation": situation,
    }


def consistency_report(decision_log, config: ConsistencyConfig) -> ConsistencyReport:
    """Weighted share of the dominant choice inside repeated situations.

    A row counts when ``result`` is a mapping and ``result["status"]`` is one
    of ``config.counted_statuses``. Rows with a missing entity or a missing
    choice are skipped. Groups are ``(entity, situation)``; only groups with
    at least ``config.min_decisions`` rows contribute. ``value`` is the sum of
    each such group's dominant-choice count divided by the sum of their sizes.
    No such group yields ``config.neutral``.

    ``by_entity_legacy`` is the previous formula in these same neutral terms:
    fewer than four counted rows yields ``neutral``; rows are grouped by
    entity only; entities with at least two rows contribute the share of their
    dominant choice; the result is the unweighted mean of those shares.
    """
    counted = _counted_rows(decision_log, config)
    groups = defaultdict(list)
    for entry in counted:
        entity = _entity_of(entry, config)
        choice = _choice_of(entry, config)
        if entity is None or choice is None:
            continue
        situation = tuple(entry.get("situation") or ())
        groups[(entity, situation)].append((entry.get("tool"), choice))

    dominant = 0
    total = 0
    used = 0
    for choices in groups.values():
        size = len(choices)
        if size < config.min_decisions:
            continue
        dominant += Counter(choices).most_common(1)[0][1]
        total += size
        used += 1

    if used == 0:
        value = config.neutral
    else:
        value = _clamp01(dominant / total)
    return ConsistencyReport(
        value=value,
        situations_used=used,
        decisions_used=total,
        by_entity_legacy=_by_entity_legacy(counted, config),
    )


def _starts_with_attached_prefix(token: str, prefixes: Tuple[str, ...]) -> bool:
    for prefix in prefixes:
        if token.startswith(prefix):
            return True
    return False


def _token_names_entity(token: str, entity: str) -> bool:
    parts = token.split(":")
    if len(parts) < 2:
        return False
    return entity in parts[1:]


def _read_field(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _counted_rows(decision_log, config: ConsistencyConfig) -> list:
    rows = []
    if not decision_log:
        return rows
    try:
        entries = list(decision_log)
    except TypeError:
        return rows
    allowed = config.counted_statuses
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        result = entry.get("result")
        if not isinstance(result, Mapping):
            continue
        if result.get("status") not in allowed:
            continue
        rows.append(entry)
    return rows


def _entity_of(entry: Mapping, config: ConsistencyConfig) -> Any:
    if "entity" in entry:
        return entry.get("entity")
    return entry.get(config.entity_field)


def _choice_of(entry: Mapping, config: ConsistencyConfig) -> Any:
    if "choice" in entry:
        return entry.get("choice")
    return entry.get(config.choice_field)


def _by_entity_legacy(counted: list, config: ConsistencyConfig) -> float:
    """Previous by-entity concentration, expressed with config field names.

    Fewer than four counted rows, or no entity with at least two rows, yields
    ``config.neutral``.
    """
    if len(counted) < 4:
        return config.neutral
    by_entity = defaultdict(list)
    for entry in counted:
        by_entity[_entity_of(entry, config)].append(_choice_of(entry, config))
    scores = []
    for choices in by_entity.values():
        if len(choices) < 2:
            continue
        scores.append(Counter(choices).most_common(1)[0][1] / len(choices))
    if not scores:
        return config.neutral
    return _clamp01(sum(scores) / len(scores))


def _clamp01(value: float) -> float:
    number = float(value)
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return number


__all__ = [
    "ConsistencyConfig",
    "ConsistencyReport",
    "consistency_report",
    "decision_fields",
    "situation_tokens",
]
