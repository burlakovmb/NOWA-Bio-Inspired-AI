"""Synthetic completeness and summary-integrity tests for evaluation artifacts."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nowa_body.evaluation_contract import validate_evaluation


PROBES = {
    "old": [
        {"id": "old-a", "group": "unknown_budget", "expected_action": "wait", "context_tokens": ["synthetic:a"]},
        {"id": "old-b", "group": "ordinary", "expected_action": "place_order", "context_tokens": ["synthetic:b"]},
    ],
    "fresh": [
        {"id": "fresh-a", "group": "fresh_unknown", "expected_action": "wait", "context_tokens": ["synthetic:c"]},
        {"id": "fresh-b", "group": "ordinary", "expected_action": "wait", "context_tokens": ["synthetic:d"]},
    ],
}
SEEDS = [11, 29]
AGES = [0, 100]
UNKNOWN = {"old": ["unknown_budget"], "fresh": ["fresh_unknown"]}
ORDER_ACTION = "place_order"


def _build_artifact():
    rows = []
    for dataset, probes in PROBES.items():
        for probe in probes:
            for age in AGES:
                for seed in SEEDS:
                    identifier = probe["id"]
                    if identifier == "old-a":
                        chosen = "wait" if age == 0 and seed == 11 else "unfamiliar_action"
                    elif identifier == "fresh-a":
                        chosen = ORDER_ACTION
                    else:
                        chosen = probe["expected_action"]
                    rows.append({
                        "set": dataset, "id": identifier, "age_s": age, "seed": seed,
                        "group": probe["group"], "expected": probe["expected_action"],
                        "chosen": chosen, "correct": chosen == probe["expected_action"],
                    })
    summary = {
        "old": {
            "correct": 5, "total": 8, "unknown_budget_cases": 4,
            "unknown_budget_false_order_intentions": 0,
            "by_age": {"0": {"correct": 3, "total": 4}, "100": {"correct": 2, "total": 4}},
            "by_group": {"unknown_budget": {"correct": 1, "total": 4},
                         "ordinary": {"correct": 4, "total": 4}},
        },
        "fresh": {
            "correct": 4, "total": 8, "unknown_budget_cases": 4,
            "unknown_budget_false_order_intentions": 4,
            "by_age": {"0": {"correct": 2, "total": 4}, "100": {"correct": 2, "total": 4}},
            "by_group": {"fresh_unknown": {"correct": 0, "total": 4},
                         "ordinary": {"correct": 4, "total": 4}},
        },
    }
    return {"rows": rows, "summary": summary, "plan": {"synthetic": True}}


def _validate(artifact, *, probes=PROBES, seeds=SEEDS, ages=AGES, unknown=UNKNOWN):
    return validate_evaluation(
        artifact, probes_by_set=probes, seeds=seeds, ages=ages,
        unknown_budget_groups=unknown, order_action=ORDER_ACTION,
    )


def test_valid_artifact_recomputes_counts_and_counts_unfamiliar_actions_as_wrong():
    artifact = _build_artifact()
    rows_by_key, summary = _validate(artifact)

    assert len(rows_by_key) == 16
    assert rows_by_key[("old", "old-a", 100, 29)]["chosen"] == "unfamiliar_action"
    assert rows_by_key[("old", "old-a", 100, 29)]["correct"] is False
    assert summary == artifact["summary"]
    assert summary["fresh"]["unknown_budget_false_order_intentions"] == 4


def test_arbitrary_row_order_is_valid_and_returns_complete_key_map():
    artifact = _build_artifact()
    artifact["rows"].reverse()
    rows_by_key, summary = _validate(artifact)
    assert len(rows_by_key) == len(artifact["rows"])
    assert summary == artifact["summary"]


def test_same_row_total_with_old_rows_relabelled_as_fresh_is_rejected():
    artifact = _build_artifact()
    original_total = len(artifact["rows"])
    for row in artifact["rows"]:
        if row["set"] == "old":
            row["set"] = "fresh"
    assert len(artifact["rows"]) == original_total
    with pytest.raises(ValueError):
        _validate(artifact)


def test_missing_old_suffix_rows_is_rejected_even_if_other_rows_remain():
    artifact = _build_artifact()
    artifact["rows"] = [row for row in artifact["rows"] if row["id"] != "old-b"]
    with pytest.raises(ValueError):
        _validate(artifact)


def test_duplicate_replacing_a_row_is_rejected():
    artifact = _build_artifact()
    artifact["rows"][-1] = deepcopy(artifact["rows"][0])
    with pytest.raises(ValueError):
        _validate(artifact)


@pytest.mark.parametrize(("field", "value"), [
    ("set", "unknown"), ("age_s", 999), ("seed", 999),
    ("age_s", True), ("seed", False),
])
def test_unknown_set_age_seed_and_boolean_grid_values_are_rejected(field, value):
    artifact = _build_artifact()
    artifact["rows"][0][field] = value
    with pytest.raises(ValueError):
        _validate(artifact)


@pytest.mark.parametrize(("field", "value"), [
    ("group", "ordinary"), ("expected", "changed-action"), ("correct", False),
])
def test_metadata_and_correctness_tampering_are_rejected(field, value):
    artifact = _build_artifact()
    artifact["rows"][0][field] = value
    with pytest.raises(ValueError):
        _validate(artifact)


@pytest.mark.parametrize(("path", "value"), [
    (("old", "unknown_budget_cases"), 0),
    (("fresh", "total"), 7),
    (("old", "by_age", "0", "total"), 3),
    (("fresh", "by_group", "ordinary", "correct"), 3),
    (("fresh", "unknown_budget_false_order_intentions"), True),
    (("fresh", "unknown_budget_false_order_intentions"), 4.0),
    (("old", "by_age", "100", "correct"), False),
])
def test_dishonest_summary_counts_denominators_and_types_are_rejected(path, value):
    artifact = _build_artifact()
    target = artifact["summary"]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        _validate(artifact)


@pytest.mark.parametrize("summary_change", [
    "missing_dataset", "extra_field", "missing_age", "extra_group", "extra_nested_count",
])
def test_summary_shape_metadata_must_match_recomputed_grid(summary_change):
    artifact = _build_artifact()
    if summary_change == "missing_dataset":
        del artifact["summary"]["fresh"]
    elif summary_change == "extra_field":
        artifact["summary"]["old"]["reported_total"] = 8
    elif summary_change == "missing_age":
        del artifact["summary"]["old"]["by_age"]["100"]
    elif summary_change == "extra_group":
        artifact["summary"]["fresh"]["by_group"]["unknown"] = {"correct": 0, "total": 0}
    else:
        artifact["summary"]["fresh"]["by_group"]["ordinary"]["extra"] = 0
    with pytest.raises(ValueError):
        _validate(artifact)


@pytest.mark.parametrize("case", [
    "empty_sets", "empty_probe_list", "duplicate_probe_id", "empty_seeds", "duplicate_seeds",
    "boolean_seed", "empty_ages", "duplicate_ages", "negative_age", "boolean_age",
    "missing_unknown_set", "extra_unknown_set", "unknown_group", "duplicate_unknown_group",
    "empty_order_action",
])
def test_invalid_expected_contract_configuration_is_rejected(case):
    kwargs = {"probes": PROBES, "seeds": SEEDS, "ages": AGES, "unknown": UNKNOWN, "order": ORDER_ACTION}
    if case == "empty_sets":
        kwargs["probes"] = {}
    elif case == "empty_probe_list":
        kwargs["probes"] = {"old": [], "fresh": PROBES["fresh"]}
    elif case == "duplicate_probe_id":
        kwargs["probes"] = {"old": [PROBES["old"][0], dict(PROBES["old"][0])], "fresh": PROBES["fresh"]}
    elif case == "empty_seeds":
        kwargs["seeds"] = []
    elif case == "duplicate_seeds":
        kwargs["seeds"] = [11, 11]
    elif case == "boolean_seed":
        kwargs["seeds"] = [True]
    elif case == "empty_ages":
        kwargs["ages"] = []
    elif case == "duplicate_ages":
        kwargs["ages"] = [0, 0]
    elif case == "negative_age":
        kwargs["ages"] = [-1]
    elif case == "boolean_age":
        kwargs["ages"] = [False]
    elif case == "missing_unknown_set":
        kwargs["unknown"] = {"old": []}
    elif case == "extra_unknown_set":
        kwargs["unknown"] = {"old": [], "fresh": [], "extra": []}
    elif case == "unknown_group":
        kwargs["unknown"] = {"old": ["not-frozen"], "fresh": []}
    elif case == "duplicate_unknown_group":
        kwargs["unknown"] = {"old": ["unknown_budget", "unknown_budget"], "fresh": []}
    elif case == "empty_order_action":
        kwargs["order"] = " "

    with pytest.raises(ValueError):
        validate_evaluation(_build_artifact(), probes_by_set=kwargs["probes"],
                            seeds=kwargs["seeds"], ages=kwargs["ages"],
                            unknown_budget_groups=kwargs["unknown"], order_action=kwargs["order"])
