"""Tests for YAML-driven sandbox configuration."""

import pytest

from nowa_sandbox.procurement_fitness import (
    GRADUATION_THRESHOLDS,
    ProcurementFitnessEvaluator,
)
from nowa_sandbox.sandbox_config import DEFAULT_CONFIG_PATH, SandboxConfig


class TestDefaults:

    def test_load_without_path_returns_defaults(self):
        config = SandboxConfig.load(None)
        assert config.world.n_products == 10
        assert config.training.n_quarters == 30
        assert config.graduation_thresholds == GRADUATION_THRESHOLDS

    def test_shipped_default_yaml_exists_and_parses(self):
        assert DEFAULT_CONFIG_PATH.exists(), DEFAULT_CONFIG_PATH
        config = SandboxConfig.from_yaml(DEFAULT_CONFIG_PATH)
        assert config.world.days_per_quarter == 90
        assert config.world.n_suppliers == 5
        assert config.training.sleep_every_n_days == 7

    def test_shipped_defaults_match_specification_thresholds(self):
        config = SandboxConfig.from_yaml(DEFAULT_CONFIG_PATH)
        assert config.graduation_thresholds == GRADUATION_THRESHOLDS

    def test_stage_defaults_to_1a(self):
        assert SandboxConfig.load(None).training.stage == "1a"
        assert SandboxConfig.from_yaml(DEFAULT_CONFIG_PATH).training.stage == "1a"

    def test_statistical_minimums_are_respected(self):
        """Spec section 8.3: shipped defaults must meet S1-S5 minimums."""
        config = SandboxConfig.from_yaml(DEFAULT_CONFIG_PATH)
        assert config.training.n_quarters >= 20
        assert config.world.days_per_quarter >= 60
        assert config.world.n_products >= 5
        assert config.world.n_suppliers >= 3
        assert config.training.sleep_every_n_days >= 5


class TestOverrides:

    def test_partial_yaml_keeps_defaults_for_missing_keys(self, tmp_path):
        path = tmp_path / "partial.yaml"
        path.write_text("world:\n  n_products: 3\n", encoding="utf-8")
        config = SandboxConfig.from_yaml(path)
        assert config.world.n_products == 3
        assert config.world.n_suppliers == 5
        assert config.training.n_quarters == 30

    def test_stage_can_be_set_from_yaml(self, tmp_path):
        path = tmp_path / "stage.yaml"
        path.write_text("training:\n  stage: '1b'\n", encoding="utf-8")
        assert SandboxConfig.from_yaml(path).training.stage == "1b"

    def test_unknown_stage_falls_back_to_1a(self, tmp_path):
        """A typo must not silently gate on the wrong criteria."""
        path = tmp_path / "typo.yaml"
        path.write_text("training:\n  stage: 'stage-1b'\n", encoding="utf-8")
        assert SandboxConfig.from_yaml(path).training.stage == "1a"

    def test_stage_survives_a_to_dict_round_trip(self, tmp_path):
        path = tmp_path / "stage.yaml"
        path.write_text("training:\n  stage: '1b'\n", encoding="utf-8")
        config = SandboxConfig.from_yaml(path)
        assert config.to_dict()["training"]["stage"] == "1b"
        assert SandboxConfig.from_mapping(config.to_dict()).training.stage == "1b"

    def test_graduation_thresholds_are_overridable(self, tmp_path):
        path = tmp_path / "thresholds.yaml"
        path.write_text(
            "graduation_thresholds:\n  budget_discipline: 0.5\n", encoding="utf-8"
        )
        config = SandboxConfig.from_yaml(path)
        assert config.graduation_thresholds["budget_discipline"] == 0.5
        assert config.graduation_thresholds["cost_efficiency"] == 0.60

    def test_overridden_thresholds_reach_the_evaluator(self, tmp_path):
        path = tmp_path / "thresholds.yaml"
        path.write_text(
            "graduation_thresholds:\n  stockout_avoidance: 0.10\n", encoding="utf-8"
        )
        config = SandboxConfig.from_yaml(path)
        evaluator = ProcurementFitnessEvaluator(config.graduation_thresholds)
        assert evaluator.thresholds["stockout_avoidance"] == 0.10

    def test_out_of_range_thresholds_are_clamped(self, tmp_path):
        path = tmp_path / "wild.yaml"
        path.write_text(
            "graduation_thresholds:\n"
            "  cost_efficiency: 12.0\n"
            "  budget_discipline: -3.0\n",
            encoding="utf-8",
        )
        config = SandboxConfig.from_yaml(path)
        assert config.graduation_thresholds["cost_efficiency"] == 1.0
        assert config.graduation_thresholds["budget_discipline"] == 0.0

    def test_unknown_threshold_keys_are_dropped(self, tmp_path):
        path = tmp_path / "unknown.yaml"
        path.write_text(
            "graduation_thresholds:\n  telepathy: 0.9\n", encoding="utf-8"
        )
        config = SandboxConfig.from_yaml(path)
        assert "telepathy" not in config.graduation_thresholds

    def test_empty_yaml_yields_defaults(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        config = SandboxConfig.from_yaml(path)
        assert config.world.n_products == 10

    def test_non_mapping_yaml_is_rejected(self, tmp_path):
        path = tmp_path / "list.yaml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ValueError):
            SandboxConfig.from_yaml(path)

    def test_garbage_numbers_fall_back_to_defaults(self, tmp_path):
        path = tmp_path / "garbage.yaml"
        path.write_text(
            "world:\n  n_products: not_a_number\n  initial_budget: nonsense\n",
            encoding="utf-8",
        )
        config = SandboxConfig.from_yaml(path)
        assert config.world.n_products == 10
        assert config.world.initial_budget == 100_000.0


class TestRoundTrip:

    def test_to_dict_contains_all_sections(self):
        data = SandboxConfig.load(None).to_dict()
        assert set(data) == {
            "world", "training", "graduation_thresholds", "stage_baseline", "output",
        }

    def test_to_dict_round_trips_through_from_mapping(self):
        original = SandboxConfig.from_yaml(DEFAULT_CONFIG_PATH)
        restored = SandboxConfig.from_mapping(original.to_dict())
        assert restored.to_dict() == original.to_dict()


class TestCostVsChanceFloorDelta:

    def test_delta_is_read_from_config(self, tmp_path):
        shipped = SandboxConfig.from_yaml(DEFAULT_CONFIG_PATH)
        assert shipped.stage_baseline.cost_vs_chance_floor_delta == pytest.approx(0.03)

        path = tmp_path / "cfg.yaml"
        path.write_text(
            "stage_baseline:\n  cost_vs_chance_floor_delta: 0.04\n",
            encoding="utf-8",
        )
        loaded = SandboxConfig.from_yaml(path)
        assert loaded.stage_baseline.cost_vs_chance_floor_delta == pytest.approx(0.04)

        evaluator = ProcurementFitnessEvaluator(
            stage="1b",
            cost_vs_chance_floor_delta=loaded.stage_baseline.cost_vs_chance_floor_delta,
        )
        assert evaluator.cost_vs_chance_floor_delta == pytest.approx(0.04)

        low = tmp_path / "low.yaml"
        low.write_text(
            "stage_baseline:\n  cost_vs_chance_floor_delta: 0.01\n",
            encoding="utf-8",
        )
        high = tmp_path / "high.yaml"
        high.write_text(
            "stage_baseline:\n  cost_vs_chance_floor_delta: 0.2\n",
            encoding="utf-8",
        )
        assert SandboxConfig.from_yaml(low).stage_baseline.cost_vs_chance_floor_delta == (
            pytest.approx(0.02)
        )
        assert SandboxConfig.from_yaml(high).stage_baseline.cost_vs_chance_floor_delta == (
            pytest.approx(0.05)
        )
