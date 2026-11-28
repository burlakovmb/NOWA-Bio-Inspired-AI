"""Issue #100. Dataset durations and action hold in the colony body."""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

import pytest

import colony_agent as colony_agent_module
from colony_action_durations import (
    FALLBACK_DURATION_S,
    load_action_durations,
    realizations_for,
)
from colony_agent import ChinchillaAgent
from colony_storage import ColonyStorage
from shared_resources import SharedResources
from simulation_runner import SimulationRunner


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    count = len(ordered)
    mid = count // 2
    if count % 2:
        return float(ordered[mid])
    return 0.5 * (float(ordered[mid - 1]) + float(ordered[mid]))


def _union_from_files(names: tuple[str, ...], intents: tuple[str, ...]) -> tuple[float, float]:
    dataset_dir = Path(__file__).resolve().parents[1] / "Datasets"
    lows: list[float] = []
    highs: list[float] = []
    for name in names:
        rows = json.loads((dataset_dir / name).read_text(encoding="utf-8"))
        for row in rows:
            if str(row.get("intent_type") or "") not in intents:
                continue
            output = row.get("output") or {}
            duration = output.get("duration")
            lows.append(float(duration[0]))
            highs.append(float(duration[1]))
    return (min(lows), max(highs))


def test_loader_reads_duration_and_maps_eat() -> None:
    assert "eat_pellets" in realizations_for("eat")
    assert "eat_hay" in realizations_for("eat")
    table = load_action_durations()
    expected = _union_from_files(
        (
            "chinchilla_realizations_basic.json",
            "chinchilla_realizations_extended.json",
            "chinchilla_realizations_advanced.json",
            "chinchilla_realizations_colony_social.json",
        ),
        realizations_for("eat"),
    )
    assert table.range_for("eat") == expected
    assert table.range_for("eat")[0] <= 10.0
    assert table.range_for("sniff_greet") == (3.0, 8.0)
    assert table.range_for("allogroom") == (10.0, 36.0)


def test_loader_fallback_warns_once_for_unknown_action(caplog: pytest.LogCaptureFixture) -> None:
    table = load_action_durations()
    caplog.set_level(logging.WARNING)
    assert table.range_for("not_a_real_action") == FALLBACK_DURATION_S
    assert table.range_for("still_unknown") == FALLBACK_DURATION_S
    warnings = [record for record in caplog.records if "fallback" in record.message]
    assert len(warnings) == 1
    assert "(10, 30)" in warnings[0].message


def test_loader_missing_file_falls_back(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    table = load_action_durations(tmp_path, ("missing_realizations.json",))
    assert table.range_for("eat") == FALLBACK_DURATION_S
    warnings = [record for record in caplog.records if "fallback" in record.message]
    assert len(warnings) == 1


def _ready(seed: int, *, action_hold: bool | None = True) -> ChinchillaAgent:
    agent = ChinchillaAgent(sex="F", rng_seed=seed, action_hold=action_hold)
    agent.colony = [agent]
    agent.resources = SharedResources()
    return agent


def test_one_commit_when_the_hold_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(colony_agent_module, "sample_action_duration", lambda _action, _rng: 1.0)
    agent = _ready(3)
    commits: list[str] = []
    steps: list[int] = []
    original_commit = agent.commit_executed_transition
    original_step = agent.step

    def commit(*args, **kwargs):
        commits.append(str(kwargs.get("action", args[0] if args else "")))
        return original_commit(*args, **kwargs)

    def step(*args, **kwargs):
        steps.append(1)
        return original_step(*args, **kwargs)

    agent.commit_executed_transition = commit  # type: ignore[method-assign]
    agent.step = step  # type: ignore[method-assign]
    agent.replaced_policy_action = "groom_self"
    for _ in range(4):
        agent.sim_step(0.25)
    assert steps == []
    assert commits == ["groom_self"]
    assert agent._hold_end_reason == "completed"
    assert agent._action_hold_s == 0.0


def test_action_hold_false_decides_every_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(colony_agent_module, "sample_action_duration", lambda _action, _rng: 30.0)
    agent = _ready(4, action_hold=False)
    steps: list[int] = []
    original_step = agent.step

    def step(*args, **kwargs):
        steps.append(1)
        return original_step(*args, **kwargs)

    agent.step = step  # type: ignore[method-assign]
    agent.wakefulness.wakefulness = 0.0
    for _ in range(8):
        agent.sim_step(0.25)
    assert len(steps) == 8


def _arm_play(agent: ChinchillaAgent) -> None:
    agent.replaced_policy_action = "play"
    agent.wakefulness.wakefulness = 0.1
    agent.hunger = 0.2
    agent.thirst = 0.2
    agent.sim_step(0.25)
    agent.replaced_policy_action = None
    assert agent.current_action == "play"
    assert agent._action_hold_s > 1.0


def test_danger_interrupts_hold_and_brain_decides_next_tick() -> None:
    agent = _ready(5)
    _arm_play(agent)
    steps: list[int] = []
    original_step = agent.step

    def step(*args, **kwargs):
        steps.append(1)
        return original_step(*args, **kwargs)

    agent.step = step  # type: ignore[method-assign]
    agent.affective_space.axes["stress"] = 0.95
    agent.sim_step(0.25)
    assert steps == []
    assert agent._hold_end_reason == "interrupted"
    assert agent._action_hold_s == 0.0
    agent.sim_step(0.25)
    assert steps == [1]


def test_forced_sleep_interrupts_hold() -> None:
    agent = _ready(6)
    _arm_play(agent)
    agent.wakefulness.wakefulness = 0.95
    agent.sim_step(0.25)
    assert agent._hold_end_reason == "interrupted"
    assert agent._action_hold_s == 0.0


def test_drive_above_threshold_interrupts_and_threshold_does_not() -> None:
    agent = _ready(7)
    _arm_play(agent)
    # Below both the penalty band (0.6) and the 0.9 gate.
    agent.hunger = 0.5
    agent.sim_step(0.25)
    assert agent._hold_end_reason != "interrupted"
    assert agent._action_hold_s > 0.0
    agent.hunger = 0.91
    agent.sim_step(0.25)
    assert agent._hold_end_reason == "interrupted"
    assert agent._action_hold_s == 0.0


def test_penalty_band_need_interrupts_a_hold_before_energy_runs_out() -> None:
    agent = _ready(11)
    _arm_play(agent)
    agent.action_hold_interrupt_threshold = 0.9
    agent.hunger = 0.61
    agent.sim_step(0.25)
    assert agent._hold_end_reason == "interrupted"


def _arm_action(agent: ChinchillaAgent, action: str) -> None:
    agent.replaced_policy_action = action
    agent.wakefulness.wakefulness = 0.1
    agent.hunger = 0.2
    agent.thirst = 0.2
    agent.sim_step(0.25)
    agent.replaced_policy_action = None
    assert agent.current_action == action
    assert agent._action_hold_s > 1.0


def test_both_need_bands_keep_the_worse_drive() -> None:
    """Thirst spends energy faster, so a drink hold survives both bands."""
    drinking = _ready(12)
    _arm_action(drinking, "drink")
    drinking.hunger = 0.70
    drinking.thirst = 0.70
    drinking.sim_step(0.25)
    assert drinking._hold_end_reason != "interrupted"
    assert drinking.current_action == "drink"
    assert drinking._action_hold_s > 0.0

    eating = _ready(13)
    _arm_action(eating, "eat")
    eating.hunger = 0.70
    eating.thirst = 0.40
    eating.sim_step(0.25)
    assert eating._hold_end_reason != "interrupted"
    assert eating.current_action == "eat"

    both = _ready(14)
    _arm_action(both, "eat")
    both.hunger = 0.70
    both.thirst = 0.70
    both.sim_step(0.25)
    assert both._hold_end_reason == "interrupted"
    assert both._action_hold_s == 0.0


def test_loader_rejects_non_positive_and_warns_on_swap(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = [
        {"intent_type": "eat_pellets", "output": {"duration": [0, 0]}},
        {"intent_type": "eat_hay", "output": {"duration": [-4, -1]}},
        {"intent_type": "drink_water", "output": {"duration": [-2, 5]}},
        {"intent_type": "groom_body", "output": {"duration": [30, 10]}},
    ]
    (tmp_path / "bad.json").write_text(json.dumps(payload), encoding="utf-8")
    caplog.set_level(logging.WARNING)
    table = load_action_durations(tmp_path, ("bad.json",))
    assert table.range_for("eat") == FALLBACK_DURATION_S
    assert table.range_for("drink") == FALLBACK_DURATION_S
    assert table.range_for("groom_self") == (10.0, 30.0)
    messages = [record.message for record in caplog.records]
    assert any("non-positive" in message and "fallback" in message for message in messages)
    assert any("swapped" in message for message in messages)
    assert sum("non-positive" in message for message in messages) == 1
    assert sum("swapped" in message for message in messages) == 1


def test_save_load_keeps_active_hold(tmp_path: Path) -> None:
    runner = SimulationRunner(seed=8)
    agent = ChinchillaAgent(sex="F", rng_seed=8, name="Holder", agent_id="hold-save")
    runner.add_agent(agent)
    agent.current_action = "eat"
    agent._action_hold_s = 12.5
    agent._hold_started_at = 1.0
    agent._hold_reward_sum = 0.2
    agent._hold_reward_n = 1
    agent._hold_commit = {
        "action": "eat",
        "decided": "eat",
        "overridden": False,
        "source": None,
        "context": ["zone:floor"],
        "novelty": 0.0,
        "conflict": 0.0,
        "intensity": 1.0,
        "affect": None,
    }
    storage = ColonyStorage(save_dir=tmp_path)
    path = storage.save_colony(runner, "hold.json")
    loaded_runner = storage.load_colony(path)
    loaded = loaded_runner.agents[0]
    assert loaded.current_action == "eat"
    assert loaded._action_hold_s == pytest.approx(12.5)
    assert loaded._hold_commit is not None
    assert loaded._hold_commit["action"] == "eat"
    steps: list[int] = []
    original_step = loaded.step

    def step(*args, **kwargs):
        steps.append(1)
        return original_step(*args, **kwargs)

    loaded.step = step  # type: ignore[method-assign]
    loaded.hunger = 0.2
    loaded.thirst = 0.2
    loaded.wakefulness.wakefulness = 0.1
    loaded.sim_step(0.25)
    assert steps == []
    assert loaded.current_action == "eat"
    assert loaded._action_hold_s == pytest.approx(12.25)


def test_restored_hold_closes_with_zero_neuromodulator_dt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(colony_agent_module, "sample_action_duration", lambda _action, _rng: 1.0)

    def _spy(agent: ChinchillaAgent, seen: list[float]) -> None:
        original = agent.neuromodulators.update_from_signals

        def wrapped(*args, **kwargs):
            seen.append(float(kwargs["dt"]))
            return original(*args, **kwargs)

        agent.neuromodulators.update_from_signals = wrapped  # type: ignore[method-assign]

    def _finish(agent: ChinchillaAgent) -> None:
        agent.hunger = 0.2
        agent.thirst = 0.2
        agent.wakefulness.wakefulness = 0.1
        for _ in range(8):
            agent.sim_step(0.25)
            if agent.hippocampus.experiences:
                return

    live = _ready(15)
    live.replaced_policy_action = "play"
    live_seen: list[float] = []
    _spy(live, live_seen)
    live.sim_step(0.25)
    assert live._action_hold_s > 0.0
    _finish(live)
    assert live.hippocampus.experiences
    assert live_seen[-1] == pytest.approx(0.0)

    runner = SimulationRunner(seed=16)
    agent = ChinchillaAgent(sex="F", rng_seed=16, name="NM", agent_id="nm-1")
    runner.add_agent(agent)
    agent.replaced_policy_action = "play"
    agent.hunger = 0.2
    agent.thirst = 0.2
    agent.wakefulness.wakefulness = 0.1
    agent.sim_step(0.25)
    assert agent._action_hold_s > 0.0
    storage = ColonyStorage(save_dir=tmp_path)
    path = storage.save_colony(runner, "nm.json")
    loaded = storage.load_colony(path).agents[0]
    loaded_seen: list[float] = []
    _spy(loaded, loaded_seen)
    _finish(loaded)
    assert loaded.hippocampus.experiences
    assert loaded_seen[-1] == pytest.approx(0.0)


def _measure(seed: int, duration_s: float, dt: float, *, action_hold: bool) -> dict:
    """Completed bouts plus raw current_action changes, scout-style."""
    bouts: list[tuple[str, float, bool]] = []
    changes = {"n": 0}
    original_finish = ChinchillaAgent._finish_action_hold
    original_step = ChinchillaAgent.sim_step

    def finish(self: ChinchillaAgent, *, interrupted: bool) -> None:
        commit = self._hold_commit if isinstance(self._hold_commit, dict) else {}
        action = str(commit.get("action") or self.current_action or "")
        started = self._hold_started_at
        original_finish(self, interrupted=interrupted)
        if started is not None and action:
            bouts.append((action, float(self.sim_time) - float(started), bool(interrupted)))

    previous: dict[str, str] = {}

    def sim_step(self: ChinchillaAgent, step_dt: float) -> None:
        original_step(self, step_dt)
        action = str(self.current_action)
        prior = previous.get(self.agent_id)
        if prior is not None and prior != action:
            changes["n"] += 1
        previous[self.agent_id] = action

    state = random.getstate()
    random.seed(seed)
    ChinchillaAgent._finish_action_hold = finish  # type: ignore[method-assign]
    ChinchillaAgent.sim_step = sim_step  # type: ignore[method-assign]
    try:
        runner = SimulationRunner(death_journal_path=f"/tmp/colony-hold-{seed}-{action_hold}.jsonl", seed=seed)
        for index in range(4):
            runner.add_agent(
                ChinchillaAgent(
                    sex="F" if index % 2 == 0 else "M",
                    rng_seed=seed + index,
                    name=f"c{index}",
                    agent_id=f"hold-{seed}-{index}",
                    action_hold=action_hold,
                )
            )
        founder_ids = {agent.agent_id for agent in runner.agents}
        runner.run_for(duration_s, dt=dt)
        living = [agent for agent in runner.agents if agent.agent_id in founder_ids]
        energies = [float(agent.energy) for agent in living]
        births = sum(1 for agent in runner.agents if agent.agent_id not in founder_ids)
        deaths = len(founder_ids) - len(living)
        alive = living
    finally:
        ChinchillaAgent._finish_action_hold = original_finish  # type: ignore[method-assign]
        ChinchillaAgent.sim_step = original_step  # type: ignore[method-assign]
        random.setstate(state)
    return {
        "bouts": bouts,
        "changes": changes["n"],
        "alive": len(alive),
        "energies": energies,
        "deaths": deaths,
        "births": births,
    }


def test_seed42_1200s_founders_survive_without_half_second_flicker() -> None:
    measured = _measure(42, 1200.0, 0.25, action_hold=True)
    assert measured["deaths"] == 0
    assert measured["alive"] == 4
    assert min(measured["energies"]) > 0.05
    bouts = measured["bouts"]
    assert bouts
    short = sum(1 for _action, duration, _cut in bouts if duration <= 0.5 + 1e-9)
    assert short / len(bouts) < 0.25


def test_headless_eat_median_and_dataset_ranges() -> None:
    measured = _measure(42, 120.0, 0.25, action_hold=True)
    table = load_action_durations()
    by_action: dict[str, list[float]] = {}
    for action, duration, interrupted in measured["bouts"]:
        if interrupted:
            continue
        by_action.setdefault(action, []).append(duration)
    eat = by_action.get("eat", [])
    assert eat, "expected at least one completed eat bout"
    assert _median(eat) >= 10.0
    for action, samples in by_action.items():
        low, high = table.range_for(action)
        # Last tick can land up to one runner slice past the sampled max.
        assert low - 1e-6 <= _median(samples) <= high + 0.25 + 1e-6


def test_dt_invariant_action_lengths() -> None:
    fine = _measure(42, 60.0, 0.1, action_hold=True)
    coarse = _measure(42, 60.0, 0.25, action_hold=True)

    def medians(rows: list[tuple[str, float, bool]]) -> dict[str, float]:
        grouped: dict[str, list[float]] = {}
        for action, duration, interrupted in rows:
            if not interrupted:
                grouped.setdefault(action, []).append(duration)
        return {action: _median(samples) for action, samples in grouped.items() if samples}

    fine_med = medians(fine["bouts"])
    coarse_med = medians(coarse["bouts"])
    shared = sorted(set(fine_med) & set(coarse_med))
    assert shared
    for action in shared:
        left = fine_med[action]
        right = coarse_med[action]
        span = max(left, right, 1.0)
        assert abs(left - right) <= 0.5 * span
