"""Pure validation and summary reconstruction for offline evaluation artifacts.

This module deliberately has no file, network, employee, or core dependencies.
Callers are responsible for authenticating the frozen inputs and artifacts.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from typing import Any


_ROW_FIELDS = frozenset({
    "set", "id", "age_s", "seed", "group", "expected", "chosen", "correct",
})
_SUMMARY_FIELDS = frozenset({
    "correct", "total", "unknown_budget_cases", "unknown_budget_false_order_intentions",
    "by_age", "by_group",
})
_COUNT_FIELDS = frozenset({"correct", "total"})


def _invalid(message: str) -> None:
    """Raise a bounded error that never echoes artifact or business data."""
    raise ValueError(message)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _integer_sequence(value: Any, name: str, *, nonnegative: bool) -> list[int]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence) or not value:
        _invalid(f"{name} must be a nonempty sequence of unique integers")
    result: list[int] = []
    seen: set[int] = set()
    for item in value:
        if type(item) is not int or (nonnegative and item < 0) or item in seen:
            _invalid(f"{name} must contain unique valid integers")
        seen.add(item)
        result.append(item)
    return result


def _prepare_contract(probes_by_set: Any, seeds: Any, ages: Any,
                      unknown_budget_groups: Any, order_action: Any):
    if not isinstance(probes_by_set, Mapping) or not probes_by_set:
        _invalid("probes_by_set must be a nonempty mapping")
    datasets: dict[str, dict[str, dict[str, str]]] = {}
    group_names: dict[str, list[str]] = {}
    for dataset, probes in probes_by_set.items():
        if not _nonempty_string(dataset):
            _invalid("dataset names must be nonempty strings")
        if isinstance(probes, (str, bytes, bytearray)) or not isinstance(probes, Sequence) or not probes:
            _invalid("each dataset must have a nonempty probe sequence")
        by_id: dict[str, dict[str, str]] = {}
        ordered_groups: list[str] = []
        for probe in probes:
            if not isinstance(probe, Mapping):
                _invalid("each frozen probe must be a mapping")
            identifier = probe.get("id")
            group = probe.get("group")
            expected = probe.get("expected_action")
            if not _nonempty_string(identifier) or not _nonempty_string(group) or not _nonempty_string(expected):
                _invalid("frozen probe id, group, and expected_action must be nonempty strings")
            if identifier in by_id:
                _invalid("probe identifiers must be unique within each dataset")
            by_id[identifier] = {"group": group, "expected": expected}
            if group not in ordered_groups:
                ordered_groups.append(group)
        datasets[dataset] = by_id
        group_names[dataset] = ordered_groups

    seed_values = _integer_sequence(seeds, "seeds", nonnegative=False)
    age_values = _integer_sequence(ages, "ages", nonnegative=True)
    if not _nonempty_string(order_action):
        _invalid("order_action must be a nonempty string")

    if not isinstance(unknown_budget_groups, Mapping):
        _invalid("unknown_budget_groups must be a mapping")
    if set(unknown_budget_groups) != set(datasets) or len(unknown_budget_groups) != len(datasets):
        _invalid("unknown_budget_groups must name exactly the configured datasets")
    unknown_by_set: dict[str, set[str]] = {}
    for dataset, groups in unknown_budget_groups.items():
        if isinstance(groups, (str, bytes, bytearray)) or not isinstance(groups, (Sequence, Set)):
            _invalid("unknown budget groups must be a sequence or set")
        group_set: set[str] = set()
        for group in groups:
            if not _nonempty_string(group) or group in group_set:
                _invalid("unknown budget groups must be unique nonempty strings")
            group_set.add(group)
        if not group_set.issubset(set(group_names[dataset])):
            _invalid("unknown budget groups must exist in that dataset's frozen probes")
        unknown_by_set[dataset] = group_set
    return datasets, group_names, seed_values, age_values, unknown_by_set, order_action


def _typed_equal(actual: Any, expected: Any) -> bool:
    """Recursive equality that distinguishes bool/int and int/float values."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        if len(actual) != len(expected):
            return False
        for key, value in actual.items():
            if type(key) is not str or key not in expected or not _typed_equal(value, expected[key]):
                return False
        return True
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _typed_equal(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def _recompute(rows_by_key: dict[tuple[str, str, int, int], dict[str, Any]],
               datasets: dict[str, dict[str, dict[str, str]]], group_names: dict[str, list[str]],
               seeds: list[int], ages: list[int], unknown_by_set: dict[str, set[str]],
               order_action: str) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for dataset, probes in datasets.items():
        relevant = [row for key, row in rows_by_key.items() if key[0] == dataset]
        by_age: dict[str, dict[str, int]] = {}
        for age in ages:
            age_rows = [row for row in relevant if row["age_s"] == age]
            by_age[str(age)] = {
                "correct": sum(row["correct"] is True for row in age_rows),
                "total": len(age_rows),
            }
        by_group: dict[str, dict[str, int]] = {}
        for group in group_names[dataset]:
            group_rows = [row for row in relevant if row["group"] == group]
            by_group[group] = {
                "correct": sum(row["correct"] is True for row in group_rows),
                "total": len(group_rows),
            }
        unknown_rows = [row for row in relevant if row["group"] in unknown_by_set[dataset]]
        summary[dataset] = {
            "correct": sum(row["correct"] is True for row in relevant),
            "total": len(relevant),
            "unknown_budget_cases": len(unknown_rows),
            "unknown_budget_false_order_intentions": sum(row["chosen"] == order_action for row in unknown_rows),
            "by_age": by_age,
            "by_group": by_group,
        }
    return summary


def _valid_summary_shape(summary: Any, expected: dict[str, dict[str, Any]]) -> bool:
    if not isinstance(summary, Mapping) or set(summary) != set(expected) or len(summary) != len(expected):
        return False
    for dataset, expected_set_summary in expected.items():
        supplied = summary.get(dataset)
        if not isinstance(supplied, Mapping) or set(supplied) != _SUMMARY_FIELDS or len(supplied) != len(_SUMMARY_FIELDS):
            return False
        # Require plain mappings at every level; then strict recursive type equality
        # rejects booleans/floats in place of integer counters.
        normalized = dict(supplied)
        for field in ("by_age", "by_group"):
            nested = normalized[field]
            if not isinstance(nested, Mapping):
                return False
            nested_normalized = {}
            for key, counts in nested.items():
                if not isinstance(key, str) or not isinstance(counts, Mapping):
                    return False
                if set(counts) != _COUNT_FIELDS or len(counts) != 2:
                    return False
                nested_normalized[key] = dict(counts)
            normalized[field] = nested_normalized
        if not _typed_equal(normalized, expected_set_summary):
            return False
    return True


def validate_evaluation(evaluation, *, probes_by_set, seeds, ages,
                        unknown_budget_groups, order_action):
    """Validate an evaluation artifact and recompute its per-set summary.

    Returns ``(rows_by_key, recomputed_summary)``. The row map contains fresh
    dictionaries keyed by ``(set, id, age_s, seed)``. Any invalidity raises
    ``ValueError`` without returning a partial result.
    """
    datasets, group_names, seed_values, age_values, unknown_by_set, order_action = _prepare_contract(
        probes_by_set, seeds, ages, unknown_budget_groups, order_action
    )
    if not isinstance(evaluation, Mapping) or "rows" not in evaluation or "summary" not in evaluation:
        _invalid("evaluation must contain rows and summary")
    rows = evaluation["rows"]
    if not isinstance(rows, list):
        _invalid("evaluation rows must be a list")
    expected_keys = {
        (dataset, identifier, age, seed)
        for dataset, probes in datasets.items()
        for identifier in probes
        for age in age_values
        for seed in seed_values
    }
    rows_by_key: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != _ROW_FIELDS or len(row) != len(_ROW_FIELDS):
            _invalid("each result row must contain exactly the eight contract fields")
        dataset, identifier = row["set"], row["id"]
        age, seed = row["age_s"], row["seed"]
        group, expected, chosen, correct = row["group"], row["expected"], row["chosen"], row["correct"]
        if not _nonempty_string(dataset) or not _nonempty_string(identifier):
            _invalid("row set and id must be nonempty strings")
        if type(age) is not int or type(seed) is not int:
            _invalid("row age_s and seed must be integers, not booleans")
        if not _nonempty_string(group) or not _nonempty_string(expected) or not _nonempty_string(chosen):
            _invalid("row group, expected, and chosen values must be nonempty strings")
        if type(correct) is not bool:
            _invalid("row correct value must be a boolean")
        if dataset not in datasets or identifier not in datasets[dataset]:
            _invalid("row does not bind to a configured frozen probe")
        frozen = datasets[dataset][identifier]
        if group != frozen["group"] or expected != frozen["expected"]:
            _invalid("row probe metadata differs from frozen probe metadata")
        if age not in age_values or seed not in seed_values:
            _invalid("row age or seed is outside the configured grid")
        if correct is not (chosen == expected):
            _invalid("row correctness flag disagrees with expected and chosen actions")
        key = (dataset, identifier, age, seed)
        if key in rows_by_key:
            _invalid("duplicate evaluation row key")
        rows_by_key[key] = {
            "set": dataset, "id": identifier, "age_s": age, "seed": seed,
            "group": group, "expected": expected, "chosen": chosen, "correct": correct,
        }
    if set(rows_by_key) != expected_keys or len(rows_by_key) != len(expected_keys):
        _invalid("evaluation rows do not cover the complete configured Cartesian product")
    recomputed = _recompute(rows_by_key, datasets, group_names, seed_values, age_values,
                            unknown_by_set, order_action)
    if not _valid_summary_shape(evaluation["summary"], recomputed):
        _invalid("supplied summary differs from recomputed rows or has invalid count types")
    return rows_by_key, recomputed


__all__ = ["validate_evaluation"]
