"""Tests for the sandbox CLI."""

import json

import pytest

from nowa_sandbox import run_sandbox
from nowa_sandbox.sandbox_checkpoint import load_checkpoint


FAST_ARGS = [
    "--quarters", "2",
    "--days-per-quarter", "10",
    "--budget", "10000",
    "--products", "2",
    "--suppliers", "2",
    "--sleep-every", "5",
    "--seed", "3",
    "--no-stop-on-graduation",
    "--quiet",
]


class TestArgumentResolution:

    def test_cli_overrides_yaml(self, tmp_path):
        config_path = tmp_path / "cfg.yaml"
        config_path.write_text(
            "world:\n  n_products: 7\n  n_suppliers: 4\n"
            "training:\n  n_quarters: 11\n",
            encoding="utf-8",
        )
        args = run_sandbox.build_parser().parse_args(
            ["--config", str(config_path), "--products", "2"]
        )
        config = run_sandbox.resolve_config(args)
        assert config.world.n_products == 2       # CLI wins
        assert config.world.n_suppliers == 4      # YAML preserved
        assert config.training.n_quarters == 11   # YAML preserved

    def test_defaults_apply_without_config(self):
        args = run_sandbox.build_parser().parse_args([])
        config = run_sandbox.resolve_config(args)
        assert config.training.n_quarters == 30
        assert config.world.days_per_quarter == 90

    def test_seed_flag_sets_world_and_training_seed(self):
        args = run_sandbox.build_parser().parse_args(["--seed", "17"])
        config = run_sandbox.resolve_config(args)
        assert config.world.seed == 17
        assert config.training.seed == 17

    def test_no_stop_on_graduation_flag(self):
        args = run_sandbox.build_parser().parse_args(["--no-stop-on-graduation"])
        assert run_sandbox.resolve_config(args).training.stop_on_graduation is False

    def test_no_seed_intuition_flag(self):
        args = run_sandbox.build_parser().parse_args(["--no-seed-intuition"])
        assert run_sandbox.resolve_config(args).training.seed_intuition is False

    def test_no_price_perception_flag(self):
        args = run_sandbox.build_parser().parse_args(["--no-price-perception"])
        assert run_sandbox.resolve_config(args).training.price_perception is False

    def test_price_perception_stays_on_without_the_flag(self):
        args = run_sandbox.build_parser().parse_args([])
        assert run_sandbox.resolve_config(args).training.price_perception is True

    def test_verbose_pipeline_flag(self):
        args = run_sandbox.build_parser().parse_args(["--verbose-pipeline"])
        assert args.verbose_pipeline is True

    def test_verbose_pipeline_defaults_off(self):
        args = run_sandbox.build_parser().parse_args([])
        assert args.verbose_pipeline is False


class TestStageFlag:

    def test_stage_defaults_to_1a(self):
        args = run_sandbox.build_parser().parse_args([])
        assert run_sandbox.resolve_config(args).training.stage == "1a"

    def test_stage_flag_selects_1b(self):
        args = run_sandbox.build_parser().parse_args(["--stage", "1b"])
        assert run_sandbox.resolve_config(args).training.stage == "1b"

    def test_stage_flag_overrides_yaml(self, tmp_path):
        path = tmp_path / "cfg.yaml"
        path.write_text("training:\n  stage: '1b'\n", encoding="utf-8")
        args = run_sandbox.build_parser().parse_args(
            ["--config", str(path), "--stage", "1a"]
        )
        assert run_sandbox.resolve_config(args).training.stage == "1a"

    def test_yaml_stage_survives_when_flag_is_absent(self, tmp_path):
        path = tmp_path / "cfg.yaml"
        path.write_text("training:\n  stage: '1b'\n", encoding="utf-8")
        args = run_sandbox.build_parser().parse_args(["--config", str(path)])
        assert run_sandbox.resolve_config(args).training.stage == "1b"

    def test_invalid_stage_is_rejected_by_the_parser(self):
        with pytest.raises(SystemExit):
            run_sandbox.build_parser().parse_args(["--stage", "2"])


class TestConfigPathResolution:
    """``--config configs/...`` must work regardless of the working directory."""

    def test_relative_config_falls_back_to_demo_root(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        resolved = run_sandbox.resolve_config_path("configs/default_world.yaml")
        assert resolved == str(run_sandbox.DEMO_ROOT / "configs/default_world.yaml")

        config = run_sandbox.resolve_config(
            run_sandbox.build_parser().parse_args(
                ["--config", "configs/default_world.yaml"]
            )
        )
        assert config.training.n_quarters == 30

    def test_cwd_relative_path_wins_over_demo_root(self, monkeypatch, tmp_path):
        (tmp_path / "configs").mkdir()
        (tmp_path / "configs" / "default_world.yaml").write_text(
            "training:\n  n_quarters: 3\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        assert (
            run_sandbox.resolve_config_path("configs/default_world.yaml")
            == "configs/default_world.yaml"
        )

    def test_missing_config_keeps_original_path_for_the_error_message(self, tmp_path):
        assert run_sandbox.resolve_config_path("nope/absent.yaml") == "nope/absent.yaml"
        with pytest.raises(FileNotFoundError):
            run_sandbox.resolve_config(
                run_sandbox.build_parser().parse_args(["--config", "nope/absent.yaml"])
            )

    def test_none_stays_none(self):
        assert run_sandbox.resolve_config_path(None) is None


class TestStage1bCli:

    BASELINE = {
        "cost_efficiency": 0.75,
        "stockout_avoidance": 0.95,
        "budget_discipline": 1.0,
        "reaction_to_risk_events": 0.79,
    }

    def _baseline_file(self, tmp_path):
        path = tmp_path / "baseline.json"
        path.write_text(
            json.dumps({"stage_1a_baseline": self.BASELINE}), encoding="utf-8"
        )
        return str(path)

    def test_stage_1b_without_a_baseline_is_refused(self, tmp_path):
        """Running the guard-less would silently defeat the point of Stage 1b."""
        with pytest.raises(SystemExit, match="requires --baseline-from"):
            run_sandbox.main(
                FAST_ARGS
                + ["--stage", "1b", "--output", str(tmp_path / "out.json")]
            )

    def test_stage_1b_runs_with_a_baseline(self, tmp_path):
        output = tmp_path / "run1b.json"
        exit_code = run_sandbox.main(
            FAST_ARGS
            + [
                "--stage", "1b",
                "--baseline-from", self._baseline_file(tmp_path),
                "--output", str(output),
            ]
        )
        assert exit_code == 0

        data = json.loads(output.read_text(encoding="utf-8"))
        assert data[0]["graduation"]["stage"] == "1b"
        assert set(data[0]["non_regression"]) == set(self.BASELINE)

    def test_stage_1a_records_no_guard_in_the_output(self, tmp_path):
        output = tmp_path / "run1a.json"
        run_sandbox.main(FAST_ARGS + ["--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data[0]["graduation"]["stage"] == "1a"
        assert data[0]["non_regression"] is None

    def test_baseline_can_come_from_a_raw_stage_1a_result(self, tmp_path):
        """A graduated Stage 1a results list is accepted as --baseline-from.

        The list must contain at least one all_passed quarter (v1.1.1) and at
        least MIN_QUARTERS_FOR_BASELINE samples for a median_all guard (v1.2).
        """
        from nowa_sandbox.stage_baseline import MIN_QUARTERS_FOR_BASELINE

        stage1a_output = tmp_path / "stage1a.json"
        stage1a_output.write_text(
            json.dumps([
                {
                    "quarter_index": i,
                    "fitness": dict(self.BASELINE),
                    "graduation": {"all_passed": True, "stage": "1a"},
                }
                for i in range(1, MIN_QUARTERS_FOR_BASELINE + 1)
            ]),
            encoding="utf-8",
        )

        output = tmp_path / "run1b.json"
        exit_code = run_sandbox.main(
            FAST_ARGS
            + [
                "--stage", "1b",
                "--baseline-from", str(stage1a_output),
                "--output", str(output),
            ]
        )
        assert exit_code == 0

    def test_baseline_from_never_graduated_run_is_refused(self, tmp_path):
        failed = tmp_path / "never.json"
        failed.write_text(
            json.dumps([
                {
                    "quarter_index": 1,
                    "fitness": {k: 0.1 for k in self.BASELINE},
                    "graduation": {"all_passed": False},
                }
            ]),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="no graduated Stage 1a quarters"):
            run_sandbox.main(
                FAST_ARGS
                + [
                    "--stage", "1b",
                    "--baseline-from", str(failed),
                    "--output", str(tmp_path / "out.json"),
                ]
            )

    def _graduated_stage1a_checkpoint(self, tmp_path):
        """A Stage 1a checkpoint that definitely graduated.

        Built by hand rather than by training: whether a short live run happens
        to graduate is not reproducible (see the wall-clock decay limitation),
        and this test is about the resume logic, not the agent.
        """
        import random

        from nowa_sandbox.procurement_fitness import ProcurementFitnessVector
        from nowa_sandbox.sandbox_agent_factory import create_procurement_agent
        from nowa_sandbox.sandbox_checkpoint import save_checkpoint
        from nowa_sandbox.training_loop import QuarterResult, SandboxTrainingResult

        result = SandboxTrainingResult(graduated=True, graduated_at_quarter=1)
        result.quarters.append(QuarterResult(
            quarter_index=1,
            fitness=ProcurementFitnessVector(
                1.0, 1.0, 1.0, 1.0, 1.0, 1.0, n_days=10, n_orders=5
            ),
            graduation={"all_passed": True, "stage": "1a"},
            world_summary={},
            processing_time_s=0.0,
        ))

        checkpoint = tmp_path / "stage1a.ckpt"
        save_checkpoint(
            checkpoint,
            create_procurement_agent("stage1a", rng=random.Random(1)),
            result,
        )
        return checkpoint

    def test_switching_stage_resets_inherited_graduation(self, tmp_path, capsys):
        """A Stage 1a pass must not be reported, or acted on, as a Stage 1b pass."""
        checkpoint = self._graduated_stage1a_checkpoint(tmp_path)
        output = tmp_path / "b.json"

        # stop_on_graduation deliberately left ON: the inherited flag would
        # otherwise end Stage 1b before its first quarter even ran.
        run_sandbox.main([
            "--quarters", "2", "--days-per-quarter", "10", "--budget", "10000",
            "--products", "2", "--suppliers", "2", "--sleep-every", "5",
            "--seed", "3",
            "--stage", "1b",
            "--baseline-from", self._baseline_file(tmp_path),
            "--resume-from", str(checkpoint),
            "--output", str(output),
        ])
        assert "stage 1a -> 1b" in capsys.readouterr().out

        data = json.loads(output.read_text(encoding="utf-8"))
        assert [row["quarter_index"] for row in data] == [1, 2, 3]
        assert data[-1]["graduation"]["stage"] == "1b"

    def test_stage_of_reads_the_last_quarter(self):
        from nowa_sandbox.training_loop import SandboxTrainingResult

        assert run_sandbox._stage_of(None) is None
        assert run_sandbox._stage_of(SandboxTrainingResult()) is None

    def test_resuming_within_the_same_stage_keeps_the_warning(self, tmp_path, capsys):
        checkpoint = tmp_path / "same.ckpt"
        run_sandbox.main(
            FAST_ARGS + ["--output", str(tmp_path / "a.json"),
                         "--checkpoint", str(checkpoint)]
        )
        run_sandbox.main(
            [a for a in FAST_ARGS if a != "--quiet"]
            + ["--output", str(tmp_path / "b.json"),
               "--resume-from", str(checkpoint)]
        )
        out = capsys.readouterr().out
        assert "stage 1a -> " not in out

    def test_checkpoint_carries_suppliers_across_a_resume(self, tmp_path):
        """Without this, resuming Stage 1b would quietly revert to Stage 1a."""
        args = FAST_ARGS + [
            "--stage", "1b",
            "--baseline-from", self._baseline_file(tmp_path),
        ]
        checkpoint = tmp_path / "ckpt1b.pkl"
        run_sandbox.main(
            args + ["--output", str(tmp_path / "a.json"), "--checkpoint", str(checkpoint)]
        )

        carried = load_checkpoint(checkpoint).metadata["carried_suppliers"]
        assert carried and all(
            hasattr(s, "reliability") for s in carried.values()
        )

        run_sandbox.main(
            args
            + [
                "--output", str(tmp_path / "b.json"),
                "--checkpoint", str(checkpoint),
                "--resume-from", str(checkpoint),
            ]
        )
        resumed = load_checkpoint(checkpoint).metadata["carried_suppliers"]
        assert {sid: s.reliability for sid, s in resumed.items()} == {
            sid: s.reliability for sid, s in carried.items()
        }


class TestEndToEndRun:

    def test_run_writes_valid_json(self, tmp_path):
        output = tmp_path / "run.json"
        exit_code = run_sandbox.main(FAST_ARGS + ["--output", str(output)])
        assert exit_code == 0

        data = json.loads(output.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert "fitness" in data[0]
        assert "graduation" in data[0]

    def test_run_prints_summary(self, tmp_path, capsys):
        output = tmp_path / "run.json"
        run_sandbox.main(
            [a for a in FAST_ARGS if a != "--quiet"] + ["--output", str(output)]
        )
        captured = capsys.readouterr().out
        assert "Sandbox Training Summary" in captured
        assert "Quarter 1" in captured

    def test_quiet_mode_prints_nothing(self, tmp_path, capsys):
        output = tmp_path / "run.json"
        run_sandbox.main(FAST_ARGS + ["--output", str(output)])
        assert capsys.readouterr().out == ""

    def test_zero_quarters_produces_empty_output(self, tmp_path):
        output = tmp_path / "empty.json"
        run_sandbox.main(["--quarters", "0", "--quiet", "--output", str(output)])
        assert json.loads(output.read_text(encoding="utf-8")) == []


class TestCheckpointing:

    def test_checkpoint_written_after_each_quarter(self, tmp_path):
        output = tmp_path / "run.json"
        checkpoint = tmp_path / "ckpt.pkl"
        run_sandbox.main(
            FAST_ARGS + ["--output", str(output), "--checkpoint", str(checkpoint)]
        )
        assert checkpoint.exists()
        assert load_checkpoint(checkpoint).last_quarter == 2

    def test_resume_extends_the_run(self, tmp_path):
        output = tmp_path / "run.json"
        checkpoint = tmp_path / "ckpt.pkl"
        run_sandbox.main(
            FAST_ARGS + ["--output", str(output), "--checkpoint", str(checkpoint)]
        )

        resumed_output = tmp_path / "resumed.json"
        run_sandbox.main(
            FAST_ARGS
            + [
                "--output", str(resumed_output),
                "--checkpoint", str(checkpoint),
                "--resume-from", str(checkpoint),
            ]
        )
        data = json.loads(resumed_output.read_text(encoding="utf-8"))
        assert len(data) == 4
        assert [row["quarter_index"] for row in data] == [1, 2, 3, 4]

    def test_resuming_graduated_agent_warns(self, tmp_path, capsys):
        from nowa_sandbox.sandbox_agent_factory import create_procurement_agent
        from nowa_sandbox.sandbox_checkpoint import save_checkpoint
        from nowa_sandbox.training_loop import SandboxTrainingResult
        import random

        agent = create_procurement_agent("graduated", rng=random.Random(1))
        checkpoint = tmp_path / "grad.pkl"
        save_checkpoint(
            checkpoint,
            agent,
            SandboxTrainingResult(graduated=True, graduated_at_quarter=2),
        )

        run_sandbox.main(
            [a for a in FAST_ARGS if a != "--quiet"]
            + [
                "--quarters", "1",
                "--output", str(tmp_path / "out.json"),
                "--resume-from", str(checkpoint),
            ]
        )
        captured = capsys.readouterr().out
        assert "already graduated" in captured

    def test_resume_from_missing_checkpoint_raises(self, tmp_path):
        from nowa_sandbox.sandbox_checkpoint import CheckpointError

        with pytest.raises(CheckpointError):
            run_sandbox.main(
                FAST_ARGS
                + [
                    "--output", str(tmp_path / "out.json"),
                    "--resume-from", str(tmp_path / "absent.pkl"),
                ]
            )

    def test_resume_does_not_preseed_when_restore_succeeds(self, tmp_path, monkeypatch):
        """Restored hippocampus already holds the original seed corpus."""
        checkpoint = tmp_path / "ckpt.pkl"
        run_sandbox.main(
            FAST_ARGS + ["--output", str(tmp_path / "a.json"), "--checkpoint", str(checkpoint)]
        )

        flags = []
        real_create = run_sandbox.create_procurement_agent

        def capturing_create(*args, **kwargs):
            flags.append(kwargs.get("seed_intuition"))
            return real_create(*args, **kwargs)

        seed_calls = []
        monkeypatch.setattr(run_sandbox, "create_procurement_agent", capturing_create)
        monkeypatch.setattr(
            run_sandbox,
            "seed_professional_intuition",
            lambda *a, **k: seed_calls.append(1) or 0,
        )

        exit_code = run_sandbox.main(
            FAST_ARGS
            + [
                "--output", str(tmp_path / "b.json"),
                "--resume-from", str(checkpoint),
            ]
        )
        assert exit_code == 0
        assert flags == [False]
        assert seed_calls == []

    def test_resume_reseeds_when_restore_fails(self, tmp_path, monkeypatch, capsys):
        checkpoint = tmp_path / "ckpt.pkl"
        run_sandbox.main(
            FAST_ARGS + ["--output", str(tmp_path / "a.json"), "--checkpoint", str(checkpoint)]
        )

        seeded = []
        real_seed = run_sandbox.seed_professional_intuition

        def tracking_seed(agent, repeats=1):
            added = real_seed(agent, repeats=repeats)
            seeded.append(added)
            return added

        monkeypatch.setattr(run_sandbox, "restore_agent", lambda *a, **k: False)
        monkeypatch.setattr(run_sandbox, "seed_professional_intuition", tracking_seed)

        run_sandbox.main(
            [arg for arg in FAST_ARGS if arg != "--quiet"]
            + [
                "--output", str(tmp_path / "b.json"),
                "--resume-from", str(checkpoint),
            ]
        )
        captured = capsys.readouterr().out
        assert seeded and seeded[0] > 0
        assert "fresh brain" in captured
