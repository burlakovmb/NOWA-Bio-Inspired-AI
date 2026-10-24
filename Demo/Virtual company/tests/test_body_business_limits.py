"""Business limits: a role-declared rule of the body, checked between binding and the gate.

Domain-free on purpose: the limit below is a reservation quota, but the
module only knows "an amount available at a world path" and, optionally,
"a quantity parameter times a unit price at a world path". The procurement
budget on the same module: ``test_business_limits.py``.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from mcp_body import (
    ApprovalGate,
    CapabilityRisk,
    MCPCapability,
    MCPToolRegistry,
    WAIT_AND_MONITOR,
    WorldState,
)
from nowa_body.business_event_encoder import BusinessEventEncoder
from nowa_body.business_limits import (
    available_amount,
    apply_limits,
    check_limit,
    parse_business_limits,
)
from nowa_body.runtime import BusinessAgentRuntime

WRITE = "mcp__desk__reserve_slot"
QUOTA = "mcp__desk__get_quota"
PRICES = "mcp__desk__get_prices"
T0 = datetime(2026, 10, 5, 8, 0, 0)

QUOTA_ROW = {
    "name": "quota",
    "tools": [WRITE],
    "available": f"results.{QUOTA}.left",
    "cost": {"qty_param": "count", "unit_price": f"results.{PRICES}.slots.{{slot_id}}.price"},
    "on_exceed": "clip",
    "lesson_reward": 0.6,
    "consequence": "quota_kept",
}
PARAMS = {"slot_id": "S1", "count": 200}


def _world(left=5000.0, price=10.0):
    world = WorldState()
    if left is not None:
        world.update_from_read(QUOTA, {"status": "ok", "left": left})
    world.update_from_read(PRICES, {"status": "ok", "slots": {"S1": {"price": price}, "S2": {"price": 8.5}}})
    return world


def _limit(**overrides):
    return parse_business_limits([dict(QUOTA_ROW, **overrides)])[0]


class TestCheckLimit:

    def test_call_that_fits_goes_unchanged(self):
        check = check_limit(_limit(), PARAMS, _world(left=5000.0))
        assert check.verdict == "ok" and check.params == PARAMS and check.cost == 2000.0

    def test_too_large_call_is_clipped_to_what_is_available(self):
        check = check_limit(_limit(), PARAMS, _world(left=1234.0))
        assert check.verdict == "clipped"
        assert check.params["count"] == 123 and check.cost <= 1234.0
        assert PARAMS["count"] == 200  # the caller's params are not mutated

    def test_block_mode_does_not_clip(self):
        check = check_limit(_limit(on_exceed="block"), PARAMS, _world(left=1234.0))
        assert check.blocked and check.reason == "over_available"

    def test_nothing_left_blocks(self):
        check = check_limit(_limit(), PARAMS, _world(left=0.0))
        assert check.blocked and check.reason == "nothing_left"

    def test_less_than_min_qty_blocks(self):
        assert check_limit(_limit(), PARAMS, _world(left=5.0)).reason == "over_available"
        assert check_limit(_limit(min_qty=0.4), PARAMS, _world(left=5.0)).blocked
        assert check_limit(_limit(min_qty=10), PARAMS, _world(left=95.0)).blocked

    def test_unreadable_amount_blocks(self):
        check = check_limit(_limit(), PARAMS, _world(left=None))
        assert check.blocked and check.reason == "limit_unknown"

    def test_unpriced_call_only_needs_something_left(self):
        check = check_limit(_limit(), dict(PARAMS, slot_id="S9"), _world(left=10.0))
        assert check.verdict == "ok" and check.cost is None

    def test_price_path_follows_the_bound_params(self):
        check = check_limit(_limit(), dict(PARAMS, slot_id="S2"), _world(left=5000.0))
        assert check.cost == 200 * 8.5

    def test_available_amount_reads_the_world(self):
        assert available_amount(_limit(), _world(left=42.0)) == 42.0
        assert available_amount(_limit(), _world(left=None)) is None


class TestParseAndApply:

    def test_malformed_rows_are_skipped_and_defaults_apply(self):
        limits = parse_business_limits([{"name": "no_path"}, "junk", {"available": "results.x.y", "tools": WRITE}])
        assert len(limits) == 1
        limit = limits[0]
        assert limit.name == "limit_2" and limit.tools == (WRITE,)
        assert limit.on_exceed == "block" and limit.lesson_reward == 0.0
        assert limit.consequence == "limit_protected"

    def test_unknown_on_exceed_falls_back_to_block(self):
        assert _limit(on_exceed="shrug").on_exceed == "block"

    def test_limit_without_tools_guards_every_write(self):
        assert _limit(tools=[]).guards("mcp__any__write")

    def test_unguarded_tool_passes(self):
        params, checks = apply_limits([_limit()], "mcp__other__write", PARAMS, _world(left=0.0))
        assert params == PARAMS and checks == []

    def test_every_limit_must_fit_and_the_first_block_stops(self):
        second = _limit(name="cap", available=f"results.{QUOTA}.cap", on_exceed="block")
        third = _limit(name="never_checked")
        world = _world()
        world.update_from_read(QUOTA, {"status": "ok", "left": 5000.0, "cap": 100.0})
        _params, checks = apply_limits([_limit(), second, third], WRITE, PARAMS, world)
        assert [c.verdict for c in checks] == ["ok", "blocked"]

    def test_a_clip_is_seen_by_the_next_limit(self):
        second = _limit(name="cap", available=f"results.{QUOTA}.cap", on_exceed="block")
        world = _world()
        world.update_from_read(QUOTA, {"status": "ok", "left": 1000.0, "cap": 1000.0})
        params, checks = apply_limits([_limit(), second], WRITE, PARAMS, world)
        assert [c.verdict for c in checks] == ["clipped", "ok"] and params["count"] == 100


class _ActingAgent:
    def __init__(self):
        self.hippocampus = SimpleNamespace(experiences=[], store=self._store)
        self.selector = SimpleNamespace(actions=[])
        self.affective_space = None
        self.agent_id = "clerk"

    def _store(self, path, consequence=None, intensity=1.0, reward=0.0, **_kwargs):
        episode = SimpleNamespace(path=path, consequence=consequence, intensity=intensity, reward=reward)
        self.hippocampus.experiences.append(episode)
        return episode

    def step(self, events, decision_only=True):
        return WRITE

    def register_action_channel(self, *args, **kwargs):
        return None


def _runtime(schema=None, **row_overrides):
    registry = MCPToolRegistry("clerk")
    registry.register(MCPCapability(
        tool_id=WRITE, server_name="desk", display_name="Reserve", description="WRITE",
        risk_level=CapabilityRisk.LOW_WRITE, requires_approval=False,
        input_schema=schema or {"type": "object", "properties": {}},
    ))
    sent = []
    runtime = BusinessAgentRuntime(
        agent=_ActingAgent(),
        tool_registry=registry,
        approval_gate=ApprovalGate(
            mcp_executor=lambda tool_id, params: sent.append(tool_id) or {"status": "accepted"},
            capability_lookup=registry.get,
        ),
        encoder=BusinessEventEncoder(),
        business_limits=[dict(QUOTA_ROW, cost={}, **row_overrides)],
    )
    runtime.sent = sent
    return runtime


def _obs(left):
    return {"tool_results": {QUOTA: {"status": "ok", "left": left}}}


def _lessons(runtime, consequence="quota_kept"):
    return [e for e in runtime.agent.hippocampus.experiences
            if getattr(e.consequence, "name", "") == consequence]


class TestRuntimeHook:

    def test_raw_config_rows_are_parsed(self):
        assert [limit.name for limit in _runtime().business_limits] == ["quota"]

    def test_blocked_call_never_reaches_the_gate_and_files_wait(self):
        runtime = _runtime()
        result = runtime.run_cycle(_obs(0.0), now=T0)
        assert result["limit_blocked"] == "quota" and result["limit_reason"] == "nothing_left"
        assert result["waited"] is True and result["proposed"] is None
        assert runtime.sent == []
        lesson = _lessons(runtime)[0]
        assert any(getattr(ev, "name", "") == f"action:{WAIT_AND_MONITOR}" for ev in lesson.path.events)
        assert lesson.reward == 0.6

    def test_call_that_fits_goes_through(self):
        runtime = _runtime()
        result = runtime.run_cycle(_obs(500.0), now=T0)
        assert "limit_blocked" not in result and result["proposed"] is not None
        assert runtime.sent == [WRITE]

    def test_one_lesson_and_one_notice_per_shortage_episode(self):
        runtime = _runtime()
        notices = []
        runtime.limit_notifier = notices.append
        first = runtime.run_cycle(_obs(0.0), now=T0)
        second = runtime.run_cycle(_obs(0.0), now=T0)
        assert first["limit_episode_start"] is True and second["limit_episode_start"] is False
        assert len(_lessons(runtime)) == 1
        assert [n["limit"] for n in notices] == ["quota"]
        assert notices[0]["reason"] == "nothing_left" and notices[0]["tool_id"] == WRITE
        assert notices[0]["available"] == 0.0 and notices[0]["summary"]

    def test_a_call_that_fits_ends_the_episode(self):
        runtime = _runtime()
        notices = []
        runtime.limit_notifier = notices.append
        runtime.run_cycle(_obs(0.0), now=T0)
        assert "limit_blocked" not in runtime.run_cycle(_obs(500.0), now=T0)
        assert runtime.run_cycle(_obs(0.0), now=T0)["limit_episode_start"] is True
        assert len(notices) == 2

    def test_a_grown_amount_ends_the_episode_without_a_call(self):
        runtime = _runtime()
        runtime.run_cycle(_obs(0.0), now=T0)
        assert "quota" in runtime._limit_shortages
        runtime.world_state.update_from_read(QUOTA, {"status": "ok", "left": 3.0})
        runtime._close_refilled_shortages()
        assert runtime._limit_shortages == {}

    def test_unreadable_limit_opens_no_episode(self):
        runtime = _runtime()
        notices = []
        runtime.limit_notifier = notices.append
        result = runtime.run_cycle({"tool_results": {}}, now=T0)
        assert result["limit_reason"] == "limit_unknown" and result["limit_episode_start"] is False
        assert notices == [] and runtime._limit_shortages == {} and _lessons(runtime) == []

    def test_a_failing_notifier_does_not_break_the_cycle(self):
        runtime = _runtime()

        def broken(_notice):
            raise RuntimeError("notifier down")

        runtime.limit_notifier = broken
        assert runtime.run_cycle(_obs(0.0), now=T0)["limit_blocked"] == "quota"

    def test_zero_lesson_reward_blocks_silently(self):
        runtime = _runtime(lesson_reward=0.0)
        assert runtime.run_cycle(_obs(0.0), now=T0)["limit_blocked"] == "quota"
        assert runtime.agent.hippocampus.experiences == []

    def test_clipped_call_is_reported(self):
        schema = {"type": "object", "required": ["slot_id", "count"],
                  "properties": {"slot_id": {"type": "string"}, "count": {"type": "number"}}}
        runtime = _runtime(schema=schema)
        runtime.business_limits = parse_business_limits([QUOTA_ROW])
        runtime.param_bindings = {"slot_id": {"path": f"results.{PRICES}.pick"},
                                  "count": {"path": f"results.{PRICES}.want"}}
        obs = {"tool_results": {
            QUOTA: {"status": "ok", "left": 95.0},
            PRICES: {"status": "ok", "pick": "S1", "want": 20, "slots": {"S1": {"price": 10.0}}},
        }}
        result = runtime.run_cycle(obs, now=T0)
        assert result.get("limit_clipped") == ["quota"]
        assert result["proposed"].tool_params["count"] == 9
