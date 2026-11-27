"""Issue 96 stages 1–3: generic layer stays domain-neutral, config stays optional."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from nowa_sandbox.sandbox_config import SandboxConfig
from nowa_sandbox.scenario import Observation, Scenario
from nowa_sandbox.scenario_trainer import ScenarioTrainer
from nowa_sandbox.stage_mechanics import graduation_report


GENERIC_MODULES = (
    "numeric_memory.py",
    "stage_mechanics.py",
    "scenario.py",
    "scenario_trainer.py",
)

FORBIDDEN = re.compile(
    r"\b(place_order|supplier|product|stock|price|sku|procurement)\b",
    flags=re.IGNORECASE,
)

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "nowa_sandbox"


class _World:
    def __init__(self):
        self.day = 0
        self.bankrupt = False
        self.history = []

    def tick(self):
        self.day += 1

    def summary(self):
        return {"day": self.day, "marker": "stub"}


class _StubScenario(Scenario):
    """Neutral stand-in. Not a second domain; it only exercises the loop."""

    def observe(self, world):
        return Observation(payload={"seen": True})

    def encode(self, world, tick_result, observation):
        return ["entity:a", "status:steady"]

    def action_label(self, intent):
        return "hold"

    def resolve(self, action, observation, agent):
        return None

    def evaluate(self, world, decision_log):
        return SimpleNamespace(
            n_days=len(decision_log),
            n_orders=0,
            score=1.0,
            as_dict=lambda: {"score": 1.0},
        )

    def graduation_report(self, fitness):
        return graduation_report(fitness, {"score": 0.5}, "alpha", ["score"])

    def config_for_step(self, world_config, period_index):
        return SimpleNamespace(days_per_quarter=2)

    def open_period(self, config, period_index):
        return _World(), {"label": period_index}

    def row(self, *, day, action, call, outcome, tokens):
        return {"day": day, "action": action, "result": None, "tokens": list(tokens)}

    def stage_name(self):
        return "alpha"


class TestLexiconGuard:

    @pytest.mark.parametrize("name", GENERIC_MODULES)
    def test_generic_layer_has_no_buyer_words(self, name):
        source = (PACKAGE / name).read_text(encoding="utf-8")
        match = FORBIDDEN.search(source)
        assert match is None, f"{name} contains {match.group(0)!r}"


class TestScenarioConfig:

    def test_absent_section_keeps_buyer_defaults_and_to_dict_keys(self, tmp_path):
        path = tmp_path / "plain.yaml"
        path.write_text(
            "graduation_thresholds:\n  telepathy: 0.9\n",
            encoding="utf-8",
        )
        config = SandboxConfig.from_yaml(path)
        assert config.scenario is None
        assert "telepathy" not in config.graduation_thresholds
        assert "cost_efficiency" in config.graduation_thresholds
        assert set(SandboxConfig.load(None).to_dict()) == {
            "world", "training", "graduation_thresholds", "stage_baseline",
            "consistency", "output",
        }

    def test_other_name_keeps_arbitrary_thresholds(self, tmp_path):
        path = tmp_path / "other.yaml"
        path.write_text(
            "scenario:\n"
            "  name: dispatch\n"
            "  memory:\n"
            "    value_field: fare\n"
            "    token_prefix: fare\n"
            "    entity_prefix: route\n"
            "training:\n"
            "  stage: beta\n"
            "graduation_thresholds:\n"
            "  on_time: 0.8\n"
            "  telepathy: 1.2\n",
            encoding="utf-8",
        )
        config = SandboxConfig.from_yaml(path)
        assert config.scenario is not None
        assert config.scenario.name == "dispatch"
        assert config.scenario.value_field == "fare"
        assert config.scenario.token_prefix == "fare"
        assert config.scenario.entity_prefix == "route"
        assert config.training.stage == "beta"
        assert config.graduation_thresholds == {"on_time": 0.8, "telepathy": 1.0}
        assert "cost_efficiency" not in config.graduation_thresholds
        restored = SandboxConfig.from_mapping(config.to_dict())
        assert restored.to_dict()["scenario"]["name"] == "dispatch"
        assert set(restored.graduation_thresholds) == {"on_time", "telepathy"}

    def test_named_buyer_still_drops_unknown_thresholds(self, tmp_path):
        path = tmp_path / "named.yaml"
        path.write_text(
            "scenario:\n  name: procurement\n"
            "graduation_thresholds:\n  telepathy: 0.4\n",
            encoding="utf-8",
        )
        config = SandboxConfig.from_yaml(path)
        assert config.scenario.name == "procurement"
        assert "telepathy" not in config.graduation_thresholds
        assert config.scenario.value_field == "unit_price"


class TestScenarioTrainerLoop:

    def test_stub_scenario_runs_without_a_buyer_world(self):
        trainer = ScenarioTrainer(agent=SimpleNamespace(), scenario=_StubScenario())
        result = trainer.run_quarters(n_quarters=1, stop_on_graduation=False)
        assert len(result.quarters) == 1
        quarter = result.quarters[0]
        assert quarter.world_summary["marker"] == "stub"
        assert quarter.world_summary["label"] == 1
        assert quarter.graduation["stage"] == "alpha"
        assert quarter.graduation["all_passed"] is True
        assert quarter.fitness.score == 1.0
        text = result.summary()
        assert "score=1.00" in text
        assert "GRADUATED at quarter 1" in text
        assert trainer.last_decision_log == [
            {"day": 0, "action": "hold", "result": None, "tokens": ["entity:a", "status:steady"]},
            {"day": 1, "action": "hold", "result": None, "tokens": ["entity:a", "status:steady"]},
        ]
