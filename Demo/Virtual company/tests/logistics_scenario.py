"""Toy logistics scenario for issue 96 stage 4.

Lives under tests on purpose. It is not a host, not a YAML world, and not
a role under ``nowa_roles``. The generic sandbox modules are used as they
are.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional, Sequence

from nowa_sandbox.decision_consistency import (
    ConsistencyConfig,
    consistency_report,
    decision_fields,
)
from nowa_sandbox.numeric_memory import (
    NumericMemory,
    band_token,
    perceived_entity_ids,
)
from nowa_sandbox.scenario import Call, Observation, Outcome, Scenario
from nowa_sandbox.scenario_trainer import ScenarioTrainer
from nowa_sandbox.stage_mechanics import (
    check_non_regression,
    graduation_report,
    roster_period_boundary,
)


TOOL = "assign_carrier"
ACTIVE_ROUTE = "R7"
STAGE = "routes"
CRITERIA = ("on_time_share", "carrier_stability")
GATING = ("on_time_share", "carrier_stability")
THRESHOLDS = {"on_time_share": 0.0, "carrier_stability": 0.0}

# Both carriers quote the same fare for the booked route, so the cost band
# does not depend on which carrier the brain picks. R3 stays on time and is
# only there so the day has a second route token.
_FARE = {
    ("R7", "C1"): 100.0,
    ("R7", "C2"): 100.0,
    ("R3", "C1"): 40.0,
    ("R3", "C2"): 55.0,
}
_CARRIER_BY_ACTION = {
    "assign_reliable_carrier": "C1",
    "assign_fast_carrier": "C2",
    "wait_and_monitor": "C1",
}
_ACTIONS = (
    "assign_reliable_carrier",
    "assign_fast_carrier",
    "wait_and_monitor",
)

# Same clocks the procurement golden slice freezes, so two fresh processes
# with one seed replay the same journal.
FROZEN_RANDOM_SEED = 42
FROZEN_TIME = 1700000000.0


class LogisticsFitness:
    """Criterion vector. Names are this domain's; ``as_dict`` feeds summaries."""

    def __init__(
        self,
        n_days: int,
        n_orders: int,
        on_time_share: float,
        carrier_stability: float,
    ):
        self.n_days = n_days
        self.n_orders = n_orders
        self.on_time_share = on_time_share
        self.carrier_stability = carrier_stability

    def as_dict(self) -> dict:
        return {
            "on_time_share": self.on_time_share,
            "carrier_stability": self.carrier_stability,
        }


class LogisticsWorld:
    """Two routes and a replaceable carrier list. No clock of its own."""

    def __init__(
        self,
        carriers: Sequence[str] = ("C1", "C2"),
        routes: Sequence[str] = ("R7", "R3"),
    ):
        self.day = 0
        self.carriers = list(carriers)
        self.routes = list(routes)
        self.bankrupt = False
        self.history: list = []

    def tick(self) -> None:
        self.history.append({"events": [], "day": self.day})
        self.day += 1

    def summary(self) -> dict:
        return {
            "day": self.day,
            "routes": list(self.routes),
            "carriers": list(self.carriers),
        }

    def traffic(self, route_id: str) -> str:
        return "delayed" if route_id == ACTIVE_ROUTE else "on_time"

    def unit_cost(self, route_id: str, carrier_id: str) -> float:
        return float(_FARE[(route_id, carrier_id)])

    def quote_book(self) -> dict:
        book = {}
        for carrier_id in self.carriers:
            nested = {}
            for route_id in self.routes:
                nested[route_id] = {
                    "status": "ok",
                    "unit_cost": self.unit_cost(route_id, carrier_id),
                    "traffic": self.traffic(route_id),
                }
            book[carrier_id] = {"quotes": nested}
        return book

    def assign(self, route_id: str, carrier_id: str) -> dict:
        return {
            "status": "accepted",
            "route_id": route_id,
            "carrier_id": carrier_id,
            "unit_cost": self.unit_cost(route_id, carrier_id),
            "traffic": self.traffic(route_id),
        }


class LogisticsScenario(Scenario):
    """Route / carrier plugin. Memory prefix is ``cost``, entity prefix ``route``."""

    def __init__(
        self,
        *,
        days_per_period: int = 2,
        with_roster: bool = False,
        periods_per_roster: int = 2,
        alpha: float = 1.0,
    ):
        self.days_per_period = int(days_per_period)
        self.with_roster = bool(with_roster)
        self.periods_per_roster = int(periods_per_roster)
        self.memory = _cost_memory(alpha)
        self.consistency = ConsistencyConfig(
            entity_field="route_id",
            choice_field="carrier_id",
            attached_prefixes=("status:",),
            counted_statuses=("accepted",),
            min_decisions=3,
        )
        self.thresholds = dict(THRESHOLDS)
        self.monitored = list(CRITERIA)
        self._roster: Optional[list] = None
        self.journal: list = []
        self.hooks: list = []
        self.bucket_z = 0.5

    def observe(self, world: LogisticsWorld) -> Observation:
        return Observation(payload={
            "routes": list(world.routes),
            "carriers": list(world.carriers),
            "book": world.quote_book(),
            "traffic": {route_id: world.traffic(route_id) for route_id in world.routes},
            "memory_snapshot": self.memory.snapshot(),
        })

    def encode(self, world, tick_result, observation) -> list:
        payload = observation.payload
        snapshot = payload["memory_snapshot"]
        tokens = []
        for route_id in payload["routes"]:
            tokens.append(f"route:{route_id}")
            tokens.append(f"status:{payload['traffic'][route_id]}")
            tokens.append(band_token(
                route_id,
                payload["book"],
                snapshot.get(str(route_id)),
                self.bucket_z,
                token_prefix=self.memory.token_prefix,
                value_field=self.memory.value_field,
                nested_field=self.memory.nested_field,
            ))
        return tokens

    def action_label(self, intent: Any) -> str:
        if isinstance(intent, str) and intent:
            return intent
        if intent is None:
            return "wait_and_monitor"
        for attr in ("action_type", "action", "label", "name"):
            value = getattr(intent, attr, None)
            if isinstance(value, str) and value:
                return value
        return "wait_and_monitor"

    def resolve(self, action, observation, agent) -> Optional[Call]:
        carriers = list(observation.payload["carriers"])
        if not carriers:
            return None
        preferred = _CARRIER_BY_ACTION.get(action)
        if preferred in carriers:
            carrier_id = preferred
        else:
            carrier_id = carriers[0]
        routes = list(observation.payload["routes"])
        route_id = ACTIVE_ROUTE if ACTIVE_ROUTE in routes else routes[0]
        arguments = {"route_id": route_id, "carrier_id": carrier_id}
        return Call(tool=TOOL, arguments=arguments, raw=dict(arguments))

    def apply(self, world, call, observation) -> Outcome:
        result = world.assign(call.arguments["route_id"], call.arguments["carrier_id"])
        pending = {"route_id": result["route_id"], "traffic": result["traffic"]}
        return Outcome(result=result, pending=pending)

    def store(self, tokens, call, outcome) -> None:
        self.hooks.append("store")

    def note(self, action, call, outcome) -> None:
        self.hooks.append("note")

    def apply_feedback(self, pending: Mapping[str, Any]) -> dict:
        self.hooks.append("feedback")
        return {"traffic": pending.get("traffic"), "route_id": pending.get("route_id")}

    def remember(self, tokens, observation, call, outcome) -> None:
        self.hooks.append("remember")
        paid = None
        if (
            call is not None
            and outcome is not None
            and (outcome.result or {}).get("status") == "accepted"
        ):
            paid = (
                call.arguments["route_id"],
                (outcome.result or {}).get("unit_cost"),
            )
        self.memory.observe_day(
            perceived_entity_ids(tokens, self.memory.entity_prefix),
            observation.payload["book"],
            paid,
        )

    def row(self, *, day, action, call, outcome, tokens) -> dict:
        arguments = None if call is None else dict(call.arguments)
        result = None if outcome is None else outcome.result
        record = {
            "day": day,
            "action": action,
            "route_id": None if arguments is None else arguments.get("route_id"),
            "carrier_id": None if arguments is None else arguments.get("carrier_id"),
            "traffic": None if not isinstance(result, Mapping) else result.get("traffic"),
            "unit_cost": None if not isinstance(result, Mapping) else result.get("unit_cost"),
            "result": None if result is None else dict(result),
            "tokens": list(tokens),
            **decision_fields(
                arguments,
                None if call is None else call.tool,
                tokens,
                self.consistency,
            ),
        }
        self.journal.append(record)
        return record

    def evaluate(self, world, decision_log) -> LogisticsFitness:
        report = consistency_report(decision_log, self.consistency)
        accepted = [
            entry for entry in decision_log
            if isinstance(entry.get("result"), Mapping)
            and entry["result"].get("status") == "accepted"
        ]
        on_time = sum(
            1 for entry in accepted if entry["result"].get("traffic") == "on_time"
        )
        share = (on_time / len(accepted)) if accepted else 0.0
        return LogisticsFitness(
            n_days=len(decision_log),
            n_orders=len(accepted),
            on_time_share=share,
            carrier_stability=report.value,
        )

    def graduation_report(self, fitness) -> dict:
        return graduation_report(
            fitness, self.thresholds, self.stage_name(), GATING,
        )

    def non_regression(self, fitness, summary):
        baseline = summary.get("stage_1a_baseline")
        if not baseline:
            return None
        return check_non_regression(
            fitness,
            self.monitored,
            baseline,
            summary.get("stage_1a_spread_iqr"),
        )

    def config_for_step(self, world_config, period_index):
        days = self.days_per_period
        carriers = ("C1", "C2")
        if world_config is not None:
            days = int(getattr(world_config, "days_per_quarter", days))
            custom = getattr(world_config, "carriers", None)
            if custom:
                carriers = tuple(custom)
        return SimpleNamespace(
            days_per_quarter=days,
            carriers=carriers,
            period_index=period_index,
        )

    def open_period(self, config, period_index):
        carriers = tuple(config.carriers)
        # A later period opens on a different list so a carried roster is visible.
        if self.with_roster and period_index > 1:
            carriers = ("C9",)
        world = LogisticsWorld(carriers=carriers)
        return world, {"opened_carriers": list(carriers)}

    def stage_name(self) -> str:
        return STAGE

    def minimum_streak(self) -> int:
        return 1

    def has_roster(self) -> bool:
        return bool(self.with_roster and self._roster)

    def drop_roster(self) -> None:
        self._roster = None

    def apply_roster(self, world) -> None:
        if self._roster:
            world.carriers = list(self._roster)

    def capture_roster(self, world) -> None:
        if self.with_roster:
            self._roster = list(world.carriers)

    def roster_boundary(self, period_index, stage_start) -> bool:
        if not self.with_roster:
            return False
        return roster_period_boundary(
            period_index, stage_start, self.periods_per_roster,
        )


def _cost_memory(alpha: float) -> NumericMemory:
    return NumericMemory(
        alpha=alpha,
        value_field="unit_cost",
        token_prefix="cost",
        entity_prefix="route",
        record_key="routes",
        nested_field="quotes",
    )


def make_logistics_agent(seed: int = FROZEN_RANDOM_SEED):
    """One core agent. Action names are local; nothing is seeded from another domain."""
    from agent_factory import AgentConfig, AgentFactory

    return AgentFactory(AgentConfig(actions=list(_ACTIONS))).spawn_random(
        rng=random.Random(seed),
        agent_id="logistics-toy",
    )


def _install_freeze() -> None:
    """Patch clocks and unseeded ``random.Random()`` before the agent is built."""
    step = {"n": 0}
    unseeded = {"n": 0}

    def _clock() -> float:
        step["n"] += 1
        return 1000.0 + step["n"] * 1e-6

    def _frozen_seed(counter: int) -> int:
        # Golden uses a tuple here. This interpreter rejects tuple seeds,
        # so the same counter becomes an int.
        return FROZEN_RANDOM_SEED * 1_000_003 + counter

    class _FrozenRandom(random.Random):
        def __init__(self, x=None):
            if x is None:
                unseeded["n"] += 1
                x = _frozen_seed(unseeded["n"])
            super().__init__(x)

        def seed(self, a=None, version=2):
            if a is None:
                unseeded["n"] += 1
                a = _frozen_seed(unseeded["n"])
            super().seed(a, version)

    random.Random = _FrozenRandom  # type: ignore[misc]
    time.time = lambda: FROZEN_TIME  # type: ignore[method-assign]
    time.time_ns = lambda: int(FROZEN_TIME * 1_000_000_000)  # type: ignore[method-assign]
    time.perf_counter = _clock  # type: ignore[method-assign]
    time.perf_counter_ns = lambda: int(_clock() * 1_000_000_000)  # type: ignore[method-assign]
    time.monotonic = _clock  # type: ignore[method-assign]
    time.monotonic_ns = lambda: int(_clock() * 1_000_000_000)  # type: ignore[method-assign]


def run_journal(dump_path: Optional[str] = None, seed: int = FROZEN_RANDOM_SEED) -> dict:
    """Two short periods. Call this in a fresh process: the freeze is global.

    Memory is primed with a fare of 10 for R7. Today's fare is 100, so the
    first token is ``cost:R7:expensive`` only when encode runs before remember.
    """
    _install_freeze()
    random.seed(FROZEN_RANDOM_SEED)
    agent = make_logistics_agent(seed)
    scenario = LogisticsScenario(days_per_period=2, with_roster=True, alpha=1.0)
    scenario.memory.update(ACTIVE_ROUTE, [10.0])
    trainer = ScenarioTrainer(agent, scenario, sleep_every_n_days=7)
    result = trainer.run_quarters(
        n_quarters=2,
        stop_on_graduation=False,
        carry_roster=True,
    )
    payload = {
        "graduated": result.graduated,
        "graduated_at_quarter": result.graduated_at_quarter,
        "summary": result.summary(),
        "hooks": list(scenario.hooks),
        "journal": scenario.journal,
        "memory": scenario.memory.to_dict(),
        "quarters": [
            {
                "quarter_index": quarter.quarter_index,
                "graduation": quarter.graduation,
                "fitness": {
                    **quarter.fitness.as_dict(),
                    "n_days": quarter.fitness.n_days,
                    "n_orders": quarter.fitness.n_orders,
                },
                "carriers": quarter.world_summary.get("carriers"),
                "opened_carriers": quarter.world_summary.get("opened_carriers"),
                "non_regression": quarter.non_regression,
                "action_counts": quarter.world_summary.get("action_counts"),
            }
            for quarter in result.quarters
        ],
    }
    if dump_path:
        Path(dump_path).write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )
    return payload
