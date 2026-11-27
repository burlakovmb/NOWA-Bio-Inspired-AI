"""Issue 96 stage 4: a toy logistics domain runs on the generic sandbox layer."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from nowa_sandbox.decision_consistency import ConsistencyConfig, consistency_report
from nowa_sandbox.numeric_memory import (
    DEFAULT_BUCKET_Z,
    NumericMemory,
    band_token,
)
from nowa_sandbox.price_memory import PriceMemory
from nowa_sandbox.scenario import Scenario
from nowa_sandbox.scenario_trainer import ScenarioTrainer
from nowa_sandbox.stage_baseline import compute_stage_1a_baseline
from nowa_sandbox.stage_mechanics import check_non_regression, graduation_report

from logistics_scenario import (
    ACTIVE_ROUTE,
    LogisticsFitness,
    LogisticsScenario,
    LogisticsWorld,
)


_TESTS = Path(__file__).resolve().parent
_DEMO = _TESTS.parent
_REPO = _DEMO.parents[1]
_PROCUREMENT_CRITERIA = (
    "cost_efficiency",
    "stockout_avoidance",
    "budget_discipline",
    "supplier_diversification",
    "decision_consistency",
    "reaction_to_risk_events",
)


def _book(unit_cost: float, route_id: str = "R7") -> dict:
    return {
        "C1": {
            "quotes": {
                route_id: {"status": "ok", "unit_cost": unit_cost},
            },
        },
    }


def _cost_memory() -> NumericMemory:
    return NumericMemory(
        alpha=1.0,
        value_field="unit_cost",
        token_prefix="cost",
        entity_prefix="route",
        record_key="routes",
        nested_field="quotes",
    )


class TestCostMemory:
    def test_bands_use_the_cost_prefix_and_skip_price_memory(self):
        memory = _cost_memory()
        untouched = PriceMemory()
        memory.update("R7", [50.0])
        reference = memory.reference("R7")
        kwargs = dict(
            token_prefix="cost",
            value_field="unit_cost",
            nested_field="quotes",
        )
        assert band_token("R7", _book(200.0), reference, DEFAULT_BUCKET_Z, **kwargs) == "cost:R7:expensive"
        assert band_token("R7", _book(10.0), reference, DEFAULT_BUCKET_Z, **kwargs) == "cost:R7:cheap"
        assert band_token("R7", _book(50.0), reference, DEFAULT_BUCKET_Z, **kwargs) == "cost:R7:average"
        stored = memory.to_dict()
        assert "R7" in stored["routes"]
        assert "skus" not in stored
        assert untouched.to_dict()["skus"] == {}

    def test_encode_reads_the_reference_from_before_remember(self):
        """Today's fare must not classify today's token.

        Alpha is 1 and the remembered fare is 10, today's fare is 100.
        Remember-then-encode already emits ``average``. Encode-then-remember
        still emits ``expensive``, and the next day is ``average``.
        """
        remembered_first = LogisticsScenario(alpha=1.0)
        remembered_first.memory.update(ACTIVE_ROUTE, [10.0])
        world = LogisticsWorld()
        observation = remembered_first.observe(world)
        call = remembered_first.resolve("assign_reliable_carrier", observation, None)
        outcome = remembered_first.apply(world, call, observation)
        remembered_first.remember(["route:R7"], observation, call, outcome)
        leaked = remembered_first.encode(world, {}, remembered_first.observe(world))
        assert "cost:R7:average" in leaked

        ordered = LogisticsScenario(alpha=1.0)
        ordered.memory.update(ACTIVE_ROUTE, [10.0])
        world = LogisticsWorld()
        observation = ordered.observe(world)
        tokens = ordered.encode(world, {}, observation)
        assert tokens[:3] == ["route:R7", "status:delayed", "cost:R7:expensive"]
        call = ordered.resolve("assign_reliable_carrier", observation, None)
        outcome = ordered.apply(world, call, observation)
        ordered.store(tokens, call, outcome)
        ordered.note("assign_reliable_carrier", call, outcome)
        ordered.remember(tokens, observation, call, outcome)
        followed = ordered.encode(world, {}, ordered.observe(world))
        assert "cost:R7:average" in followed
        assert ordered.memory.reference(ACTIVE_ROUTE)[0] == 100.0


class TestStageMechanics:
    def test_logistics_criteria_drive_graduation_guard_and_baseline(self):
        quarters = [
            SimpleNamespace(
                quarter_index=index,
                fitness=LogisticsFitness(4, 4, 0.8, 0.8),
                graduation={"all_passed": True, "stage": "routes"},
                world_summary={},
            )
            for index in range(1, 16)
        ]
        payload = compute_stage_1a_baseline(
            quarters,
            criteria=["on_time_share", "carrier_stability"],
        )
        assert set(payload["stage_1a_baseline"]) == {"on_time_share", "carrier_stability"}
        assert payload["n_quarters_used"] == 15
        for name in _PROCUREMENT_CRITERIA:
            assert name not in payload["stage_1a_baseline"]

        high = LogisticsFitness(4, 4, 0.9, 0.9)
        report = graduation_report(
            high,
            {"on_time_share": 0.5, "carrier_stability": 0.5},
            "routes",
            ["on_time_share"],
        )
        assert report["stage"] == "routes"
        assert report["all_passed"] is True
        assert report["on_time_share"]["passed"] is True
        assert report["carrier_stability"]["gating"] is False
        assert report["n_days"] == 4
        assert report["n_orders"] == 4
        for name in _PROCUREMENT_CRITERIA:
            assert name not in report

        held = check_non_regression(
            high,
            ["on_time_share", "carrier_stability"],
            payload["stage_1a_baseline"],
            payload["stage_1a_spread_iqr"],
        )
        assert held == {"on_time_share": True, "carrier_stability": True}
        low = LogisticsFitness(1, 0, 0.0, 0.0)
        slipped = check_non_regression(
            low,
            ["on_time_share", "carrier_stability"],
            payload["stage_1a_baseline"],
            payload["stage_1a_spread_iqr"],
        )
        assert slipped == {"on_time_share": False, "carrier_stability": False}

        scenario = LogisticsScenario()
        summary = {
            "stage_1a_baseline": payload["stage_1a_baseline"],
            "stage_1a_spread_iqr": payload["stage_1a_spread_iqr"],
        }
        assert scenario.graduation_report(high)["stage"] == "routes"
        assert scenario.non_regression(high, summary)["carrier_stability"] is True
        assert scenario.non_regression(high, {}) is None


class TestRosterDefaults:
    def test_base_roster_hooks_are_empty_and_the_trainer_accepts_them(self):
        scenario = LogisticsScenario(days_per_period=1, with_roster=False)
        assert Scenario.has_roster(scenario) is False
        assert Scenario.roster_boundary(scenario, 2, 1) is False
        assert Scenario.drop_roster(scenario) is None
        assert Scenario.apply_roster(scenario, object()) is None
        assert Scenario.capture_roster(scenario, object()) is None

        trainer = ScenarioTrainer(SimpleNamespace(), scenario, sleep_every_n_days=7)
        result = trainer.run_quarters(
            n_quarters=1,
            stop_on_graduation=False,
            carry_roster=True,
        )
        assert len(result.quarters) == 1
        quarter = result.quarters[0]
        assert quarter.world_summary["carriers"] == ["C1", "C2"]
        assert quarter.world_summary["opened_carriers"] == ["C1", "C2"]
        assert quarter.non_regression is None
        assert scenario.has_roster() is False
        row = scenario.journal[0]
        assert row["route_id"] == "R7"
        assert row["carrier_id"] == "C1"
        assert row["action"] == "wait_and_monitor"
        assert "route:R7" in row["tokens"]
        assert "status:delayed" in row["tokens"]


def _python_argv() -> list:
    setarch = shutil.which("setarch")
    if not setarch:
        raise RuntimeError("setarch is required to freeze object-id order")
    return [setarch, os.uname().machine, "-R", sys.executable]


def _run_in_fresh_process(dump_path: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONPATH"] = os.pathsep.join((
        str(_TESTS),
        str(_DEMO / "src"),
        str(_REPO / "src"),
    ))
    env["LOGISTICS_DUMP"] = str(dump_path)
    proc = subprocess.run(
        _python_argv() + [
            "-c",
            "import os, logistics_scenario; "
            "logistics_scenario.run_journal(os.environ['LOGISTICS_DUMP'])",
        ],
        cwd=str(_TESTS),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    return json.loads(dump_path.read_text(encoding="utf-8"))


class TestLogisticsTrainer:
    def test_two_periods_with_a_real_agent_repeat_on_the_same_seed(self, tmp_path):
        first = _run_in_fresh_process(tmp_path / "first.json")
        second = _run_in_fresh_process(tmp_path / "second.json")
        assert first == second

        assert first["graduated"] is True
        assert first["graduated_at_quarter"] == 1
        assert len(first["quarters"]) == 2
        assert "on_time_share=" in first["summary"]
        assert "GRADUATED at quarter 1" in first["summary"]
        assert first["hooks"] == [
            "store", "note", "remember", "feedback",
            "store", "note", "remember", "feedback",
        ] * 2

        journal = first["journal"]
        assert [row["day"] for row in journal] == [0, 1, 0, 1]
        assert journal[0]["tokens"][:3] == [
            "route:R7", "status:delayed", "cost:R7:expensive",
        ]
        assert "route:R3" in journal[0]["tokens"]
        assert "status:on_time" in journal[0]["tokens"]
        for row in journal[1:]:
            assert "cost:R7:average" in row["tokens"]
        for row in journal:
            assert row["tool"] == "assign_carrier"
            assert row["route_id"] == "R7"
            assert row["entity"] == row["route_id"]
            assert row["choice"] == row["carrier_id"]
            assert row["carrier_id"] in {"C1", "C2"}
            assert row["result"]["status"] == "accepted"
            assert row["traffic"] == "delayed"
            assert row["unit_cost"] == 100.0
            assert not any(token.startswith("price:") for token in row["tokens"])

        config = ConsistencyConfig(
            entity_field="route_id",
            choice_field="carrier_id",
            attached_prefixes=("status:",),
            counted_statuses=("accepted",),
            min_decisions=3,
        )
        report = consistency_report(journal, config)
        assert report.situations_used == 1
        assert report.decisions_used == 3
        assert report.value >= 2.0 / 3.0
        average = next(row for row in journal if "cost:R7:average" in row["tokens"])
        assert average["situation"] == [
            "cost:R7:average", "route:R7", "status:delayed",
        ]

        memory = first["memory"]
        assert "skus" not in memory
        assert memory["routes"]["R7"]["ema"] == 100.0
        assert "price_memory" not in memory

        assert first["quarters"][0]["opened_carriers"] == ["C1", "C2"]
        assert first["quarters"][0]["carriers"] == ["C1", "C2"]
        assert first["quarters"][1]["opened_carriers"] == ["C9"]
        assert first["quarters"][1]["carriers"] == ["C1", "C2"]
        for quarter in first["quarters"]:
            graduation = quarter["graduation"]
            assert graduation["stage"] == "routes"
            assert graduation["all_passed"] is True
            assert graduation["n_days"] == 2
            assert graduation["n_orders"] == 2
            assert set(graduation) >= {"on_time_share", "carrier_stability", "stage"}
            for name in _PROCUREMENT_CRITERIA:
                assert name not in graduation
            assert quarter["fitness"]["on_time_share"] == 0.0
            assert quarter["non_regression"] is None
            assert sum(quarter["action_counts"].values()) == 2
