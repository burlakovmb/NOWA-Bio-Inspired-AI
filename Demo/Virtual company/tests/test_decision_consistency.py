"""Domain-neutral decision consistency, exercised on a toy logistics host."""

import re
from dataclasses import dataclass
from pathlib import Path

import nowa_sandbox.decision_consistency as decision_consistency
from nowa_sandbox.decision_consistency import (
    ConsistencyConfig,
    consistency_report,
    decision_fields,
    situation_tokens,
)


LOGISTICS_CONTEXT = [
    "event:quiet_day",
    "route:R7",
    "status:delayed",
    "cost:R7:high",
    "route:R9",
    "status:on_time",
    "budget:critical",
    "status:stale",
]


def _logistics_config(**overrides):
    params = dict(
        entity_field="route_id",
        choice_field="carrier_id",
        counted_statuses=("delivered",),
    )
    params.update(overrides)
    return ConsistencyConfig(**params)


def _row(route, carrier, situation=(), status="delivered", tool="dispatch", **extra):
    entry = {
        "tool": tool,
        "entity": route,
        "choice": carrier,
        "situation": list(situation),
        "result": {"status": status},
    }
    entry.update(extra)
    return entry


class TestSituationTokens:

    def test_attached_status_follows_its_route_only(self):
        prefixes = ("status:",)
        assert situation_tokens(LOGISTICS_CONTEXT, "R7", prefixes) == (
            "cost:R7:high",
            "route:R7",
            "status:delayed",
        )
        assert situation_tokens(LOGISTICS_CONTEXT, "R9", prefixes) == (
            "route:R9",
            "status:on_time",
        )
        assert situation_tokens(LOGISTICS_CONTEXT, "R5", prefixes) == ()
        assert situation_tokens(LOGISTICS_CONTEXT, None, prefixes) == ()
        assert situation_tokens([], "R7", prefixes) == ()

    def test_field_match_is_exact_and_ignores_the_token_type(self):
        assert situation_tokens(
            ["route:R10", "status:delayed"], "R1", ("status:",)
        ) == ()
        assert situation_tokens(["route:R7"], "route", ()) == ()
        assert situation_tokens(["route:R7"], "R7", ()) == ("route:R7",)
        assert situation_tokens(LOGISTICS_CONTEXT, "R7", ()) == (
            "cost:R7:high",
            "route:R7",
        )

    def test_attached_run_follows_the_nearest_non_attached_token(self):
        assert situation_tokens(
            ["route:R7", "status:delayed", "status:held"],
            "R7",
            ("status:",),
        ) == ("route:R7", "status:delayed", "status:held")
        assert situation_tokens(
            ["route:R7", "event:quiet_day", "status:delayed"],
            "R7",
            ("status:",),
        ) == ("route:R7",)


class TestConsistencyReport:

    def test_two_situations_on_one_route_can_score_perfect(self):
        config = _logistics_config()
        delayed = ["cost:R7:high", "route:R7", "status:delayed"]
        on_time = ["route:R7", "status:on_time"]
        log = (
            [_row("R7", "C1", delayed) for _ in range(3)]
            + [_row("R7", "C2", on_time) for _ in range(3)]
        )
        report = consistency_report(log, config)
        assert report.value == 1.0
        assert report.by_entity_legacy < 1.0
        assert report.situations_used == 2
        assert report.decisions_used == 6

    def test_weighted_mean_ignores_short_groups_and_uses_neutral(self):
        config = _logistics_config(neutral=0.25)
        log = (
            [_row("A", "X") for _ in range(3)]
            + [_row("B", "X"), _row("B", "X"), _row("B", "Y"), _row("B", "Y")]
            + [_row("C", "Z"), _row("C", "Z")]
        )
        report = consistency_report(log, config)
        assert report.value == 5 / 7
        assert report.situations_used == 2
        assert report.decisions_used == 7

        short = consistency_report([_row("A", "X"), _row("A", "X")], config)
        assert short.value == 0.25
        assert short.situations_used == 0
        assert short.decisions_used == 0

        empty = consistency_report([], config)
        assert empty.value == 0.25
        assert empty.by_entity_legacy == 0.25

    def test_rows_outside_the_counted_set_are_skipped(self):
        config = _logistics_config()
        log = [
            _row("R7", "C1"),
            _row("R7", "C2", status="lost"),
            _row(None, "C1"),
            _row("R7", None),
            {"entity": None, "choice": "C1", "route_id": "R7",
             "result": {"status": "delivered"}},
            {"entity": "R7", "choice": None, "carrier_id": "C1",
             "result": {"status": "delivered"}},
            {"entity": "R7", "choice": "C9", "result": "delivered"},
            _row("R7", "C1"),
            _row("R7", "C1"),
        ]
        report = consistency_report(log, config)
        assert report.value == 1.0
        assert report.decisions_used == 3

    def test_old_rows_use_configured_fields_and_an_empty_situation(self):
        config = _logistics_config()
        log = [
            {"route_id": "R7", "carrier_id": "C1",
             "result": {"status": "delivered"}},
            {"route_id": "R7", "carrier_id": "C1", "situation": [],
             "result": {"status": "delivered"}},
            {"route_id": "R7", "carrier_id": "C1", "situation": (),
             "result": {"status": "delivered"}},
        ]
        report = consistency_report(log, config)
        assert report.value == 1.0
        assert report.situations_used == 1
        assert report.decisions_used == 3

    def test_by_entity_legacy_matches_the_previous_formula(self):
        config = _logistics_config()

        # Three counted rows: the previous formula returns neutral (< 4).
        three = [_row("R1", "C1") for _ in range(3)]
        early = consistency_report(three, config)
        assert early.value == 1.0
        assert early.by_entity_legacy == 0.5

        # One entity, choices split 3/3: dominant share 3/6 = 0.5.
        split = [_row("R1", carrier) for carrier in ("C1", "C1", "C1", "C2", "C2", "C2")]
        assert consistency_report(split, config).by_entity_legacy == 0.5

        # R1: 3/4 = 0.75. R2: 2/2 = 1.0. A singleton entity is ignored.
        # Unweighted mean (0.75 + 1.0) / 2 = 0.875.
        mixed = (
            [_row("R1", "C1"), _row("R1", "C1"), _row("R1", "C1"), _row("R1", "C2")]
            + [_row("R2", "C3"), _row("R2", "C3")]
            + [_row("R3", "C4")]
        )
        assert consistency_report(mixed, config).by_entity_legacy == 0.875


class TestDecisionFields:

    def test_reads_a_dataclass_a_mapping_and_a_missing_call(self):
        @dataclass
        class _Call:
            route_id: str
            carrier_id: str

        config = ConsistencyConfig(
            entity_field="route_id",
            choice_field="carrier_id",
            attached_prefixes=("status:",),
        )
        from_object = decision_fields(
            _Call("R7", "C9"), "dispatch", LOGISTICS_CONTEXT, config
        )
        assert from_object == {
            "tool": "dispatch",
            "entity": "R7",
            "choice": "C9",
            "situation": ["cost:R7:high", "route:R7", "status:delayed"],
        }

        from_mapping = decision_fields(
            {"route_id": "R9", "carrier_id": "C2"},
            "dispatch",
            LOGISTICS_CONTEXT,
            config,
        )
        assert from_mapping["entity"] == "R9"
        assert from_mapping["choice"] == "C2"
        assert from_mapping["situation"] == ["route:R9", "status:on_time"]

        assert decision_fields(None, "dispatch", LOGISTICS_CONTEXT, config) == {
            "tool": None,
            "entity": None,
            "choice": None,
            "situation": [],
        }


class TestLexiconGuard:

    def test_module_source_has_no_host_domain_words(self):
        source = Path(decision_consistency.__file__).read_text(encoding="utf-8")
        match = re.search(
            r"\b(product|supplier|price|stock|procurement|purchase)\b",
            source,
            flags=re.IGNORECASE,
        )
        assert match is None
