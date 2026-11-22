from __future__ import annotations

from colony_agent import ChinchillaAgent
from simulation_runner import SimulationRunner


def _track_bowl_intake(monkeypatch) -> tuple[list[float], list[float]]:
    """Amounts actually removed inside eat/drink acquisition."""
    eaten: list[float] = []
    drunk: list[float] = []
    original = ChinchillaAgent._try_acquire_resource

    def _tracked(self: ChinchillaAgent, resource: str) -> bool:
        resources = self.resources
        if resources is None:
            return original(self, resource)
        food_before = float(resources.food_pellets) + float(resources.hay)
        water_before = float(resources.water)
        acquired = original(self, resource)
        if resource == "food_pellets":
            taken = food_before - (float(resources.food_pellets) + float(resources.hay))
            if taken > 0.0:
                eaten.append(taken)
        elif resource == "water":
            taken = water_before - float(resources.water)
            if taken > 0.0:
                drunk.append(taken)
        return acquired

    monkeypatch.setattr(ChinchillaAgent, "_try_acquire_resource", _tracked)
    return eaten, drunk


def test_tc01_two_agents_basic_survival_loop(monkeypatch) -> None:
    eaten, drunk = _track_bowl_intake(monkeypatch)
    runner = SimulationRunner()
    agent_0 = ChinchillaAgent(sex="F", rng_seed=1)
    agent_1 = ChinchillaAgent(sex="M", rng_seed=2)
    runner.add_agent(agent_0)
    runner.add_agent(agent_1)
    agents = (agent_0, agent_1)

    runner.run_for(300.0, dt=1.0)

    assert runner.sim_time >= 300.0
    for agent in agents:
        if any(live.agent_id == agent.agent_id for live in runner.agents):
            assert agent.sim_time > 290.0
        else:
            assert runner.death_registry.is_deceased(agent.agent_id)

    assert len(agent_0.hippocampus.experiences) > 0
    # The bowl moves only when someone ate or drank. A waking animal does
    # not lower it by metabolizing.
    food_drop = (1.0 - float(runner.resources.food_pellets)) + (1.0 - float(runner.resources.hay))
    water_drop = 1.0 - float(runner.resources.water)
    assert abs(food_drop - sum(eaten)) <= 1e-9
    assert abs(water_drop - sum(drunk)) <= 1e-9
    assert (food_drop > 1e-12) is (len(eaten) > 0)
    assert (water_drop > 1e-12) is (len(drunk) > 0)


def test_tc01_two_agents_survive_300s() -> None:
    runner = SimulationRunner()
    agent_0 = ChinchillaAgent(sex="F")
    agent_1 = ChinchillaAgent(sex="M")
    runner.add_agent(agent_0)
    runner.add_agent(agent_1)

    runner.run_for(300.0, dt=1.0)

    assert agent_0.sim_time > 290.0
    assert agent_1.sim_time > 290.0


def test_tc04_wheel_is_exclusive_resource() -> None:
    runner = SimulationRunner()
    agent_0 = ChinchillaAgent(sex="F")
    agent_1 = ChinchillaAgent(sex="M")
    runner.add_agent(agent_0)
    runner.add_agent(agent_1)

    acquired_0 = agent_0._try_acquire_resource("wheel")
    acquired_1 = agent_1._try_acquire_resource("wheel")

    assert runner.resources.wheel_lock in {agent_0.agent_id, agent_1.agent_id}
    assert acquired_0 != acquired_1
    blocked = agent_0 if not acquired_0 else agent_1
    assert len(blocked.frustration_events) >= 1
