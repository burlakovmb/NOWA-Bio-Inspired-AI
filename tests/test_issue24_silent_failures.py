"""Regressions for silent swarm failures (issue 24)."""

from __future__ import annotations

import logging

import pytest

from fitness import FitnessEvaluator
from mortality import MortalitySystem
from swarm import (
    Position3D,
    SpaceBounds,
    SwarmConfig,
    SwarmEnvironment,
)
import swarm as swarm_module


class _Energy:
    def __init__(self, energy: float) -> None:
        self.energy = energy


class _Runtime:
    def __init__(self, energy: float) -> None:
        self.energy_system = _Energy(energy)


class _Wake:
    def __init__(self, wakefulness: float) -> None:
        self.wakefulness = wakefulness


class _Mortal:
    def __init__(self, agent_id: str, energy: float) -> None:
        self.agent_id = agent_id
        self.mortality_system = MortalitySystem()
        self.autonomous_runtime = _Runtime(energy)
        self.wakefulness = _Wake(0.2)
        self.age = 1.0
        self.lived_steps = 3


def _env() -> SwarmEnvironment:
    return SwarmEnvironment(
        config=SwarmConfig(bounds=SpaceBounds(x_max=40.0, y_max=40.0, z_max=10.0)),
        fitness_evaluator=FitnessEvaluator(),
    )


def test_add_agent_checks_the_cap_before_publishing_a_slot(monkeypatch) -> None:
    monkeypatch.setattr(swarm_module, "MAX_POPULATION_SIZE", 1)
    env = _env()
    first = _Mortal("first", energy=0.8)
    second = _Mortal("second", energy=0.8)
    env.add_agent(first, position=Position3D(1.0, 1.0, 0.0))

    with pytest.raises(ValueError, match="Population limit"):
        env.add_agent(second, position=Position3D(5.0, 5.0, 0.0))

    assert [agent.agent_id for agent in env.get_all_agents()] == ["first"]
    assert env.get_agent("second") is None


def test_add_agent_placement_failure_does_not_publish_a_slot(monkeypatch) -> None:
    env = _env()

    def boom(_preferred):
        raise RuntimeError("Unable to place agent without collisions")

    monkeypatch.setattr(env, "_find_free_position", boom)
    with pytest.raises(RuntimeError, match="Unable to place"):
        env.add_agent(_Mortal("lost", energy=0.8), position=Position3D(1.0, 1.0, 0.0))

    assert env.get_all_agents() == []


def test_mortality_exception_is_logged_and_still_removes_a_lethal_agent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = _env()
    agent = _Mortal("dying", energy=0.0)

    def boom(**_kwargs):
        raise RuntimeError("mortality broke")

    agent.mortality_system.update = boom
    env.add_agent(agent, position=Position3D(2.0, 2.0, 0.0))

    with caplog.at_level(logging.WARNING, logger="swarm"):
        env.tick()

    assert "mortality update failed" in caplog.text
    assert agent.mortality_system.is_dead() is True
    assert agent.mortality_system.cause_of_death == "exhaustion"
    assert env.get_agent("dying") is None


def test_mortality_exception_does_not_kill_a_fed_agent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    env = _env()
    agent = _Mortal("fed", energy=0.9)

    def boom(**_kwargs):
        raise RuntimeError("mortality sensor glitch")

    agent.mortality_system.update = boom
    env.add_agent(agent, position=Position3D(3.0, 3.0, 0.0))

    with caplog.at_level(logging.WARNING, logger="swarm"):
        env.tick()

    assert "mortality update failed" in caplog.text
    assert agent.mortality_system.is_dead() is False
    assert env.get_agent("fed") is agent
