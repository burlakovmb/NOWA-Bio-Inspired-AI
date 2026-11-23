#!/usr/bin/env python3
"""Issue #86 bench: decision cost, memory size and learning quality as an agent ages.

Standard library only. From the repository root:

    python tools/bench_issue_86.py cost [--decisions 12000] [--json out.json]
    python tools/bench_issue_86.py learning [--seeds 12] [--learn-decisions 1500] [--json out.json]

cost: one agent, 8 actions; each decision the context is 7 features x 3 levels drawn uniformly (a deliberately
diverse stream); dt 1.5 s; sleep(cycles=3) every 800 decisions; hippocampus 256; expected wake interval 1200 s;
reward +0.5 when the action matches a fixed rule of two features, else -0.1. Per 1000 decisions: median and p90
wall time of one decision (step + commit, sleep excluded), temporal chains, visit-count rows, saved agent size.

learning: the issue #85 contingency task. 7 actions; 4 context tokens (danger with probability 0.4, food, energy,
light); in danger +0.5 for either of two evasive actions, else -0.5; in calm +0.25 for foraging. 1500 decisions by
default (7 nights; 6000 gives 30 nights, enough for pruning to act), sleep(cycles=3) every 200. Per seed, the evasive share in danger, mean of the last three 150-decision blocks.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent import Agent  # noqa: E402
from cortex import CortexMemory  # noqa: E402
from hippocampus import NOWAHippocampus  # noqa: E402
from intent_memory import IntentMemory  # noqa: E402
from labile_layer import PlasticityConfig  # noqa: E402
from selector import ActionSelector  # noqa: E402
from sleep import SleepManager  # noqa: E402
from storage import AgentStorage  # noqa: E402


def build_agent(actions, seed, capacity, wake_interval_s):
    random.seed(seed)  # the selector samples from the module-level generator (issue #14)
    hippocampus = NOWAHippocampus(max_experiences=capacity)
    cortex = CortexMemory()
    memory = IntentMemory()
    sleep_manager = SleepManager(hippocampus, cortex, memory)
    selector = ActionSelector(actions=list(actions))
    return Agent(hippocampus, cortex, selector, sleep_manager, memory, rng_seed=seed,
                 plasticity_config=PlasticityConfig(expected_wake_interval_s=wake_interval_s))


def decide(agent, context, actions, fallback):
    action = agent.step(context_events=context, reward=None, decision_only=True, dt=1.5)
    return action if action in actions else fallback


def commit(agent, context, action, reward):
    agent.commit_executed_transition(action=action, reward=reward, context_events=context)


def chain_count(agent):
    memory = getattr(agent.sleep_manager, "chain_memory", None)
    return len(getattr(memory, "chains", {}) or {})


def save_kb(agent):
    with tempfile.TemporaryDirectory() as folder:
        storage = AgentStorage(save_dir=folder)
        path = storage.save_agent(agent.hippocampus, agent.cortex, agent.selector, filename="bench.nowa", agent=agent)
        return round(Path(path).stat().st_size / 1024)


def run_cost(decisions):
    actions = tuple(f"a{k}" for k in range(8))
    agent = build_agent(actions, seed=11, capacity=256, wake_interval_s=1200.0)
    rng = random.Random(12)

    def context():
        return [f"f{k}:" + rng.choice(("lo", "mid", "hi")) for k in range(7)]

    def rule(ctx):
        return actions[(ctx[0].endswith("hi") * 2 + ctx[1].endswith("lo")) % 8]

    rows, times = [], []
    for index in range(decisions):
        ctx = context()
        start = time.perf_counter()
        action = decide(agent, ctx, actions, actions[0])
        commit(agent, ctx, action, 0.5 if action == rule(ctx) else -0.1)
        times.append((time.perf_counter() - start) * 1000.0)
        if (index + 1) % 800 == 0:
            agent.sleep(cycles=3)
        if (index + 1) % 1000 == 0:
            ordered = sorted(times)
            rows.append({
                "decisions": index + 1,
                "median_ms": round(statistics.median(ordered), 2),
                "p90_ms": round(ordered[int(len(ordered) * 0.9)], 2),
                "chains": chain_count(agent),
                "visit_rows": len(getattr(agent, "_action_visit_counts", {}) or {}),
                "save_kb": save_kb(agent),
            })
            print(json.dumps(rows[-1]), flush=True)
            times = []
    return {"mode": "cost", "rows": rows}


def run_learning(seeds, decisions=1500, visit_decay=True):
    actions = ("forage", "school", "flee", "hide", "rest", "explore", "mate")
    evasive = {"flee", "hide"}
    per_seed = []
    for seed in range(seeds):
        agent = build_agent(actions, seed=seed, capacity=128, wake_interval_s=300.0)
        if not visit_decay:
            agent.sleep_manager.visit_halving_sleeps = 0  # ablation: no visit-count fading
        rng = random.Random(seed + 1)
        blocks, danger_n, evade_n = [], 0, 0
        for index in range(decisions):
            danger = rng.random() < 0.4
            ctx = ["threat:near" if danger else "threat:none", "food:" + rng.choice(("near", "far")),
                   "energy:" + rng.choice(("mid", "high")), "light:day"]
            action = decide(agent, ctx, actions, "rest")
            if danger:
                danger_n += 1
                evade_n += action in evasive
                reward = 0.5 if action in evasive else -0.5
            else:
                reward = 0.25 if action == "forage" else 0.0
            commit(agent, ctx, action, reward)
            if (index + 1) % 200 == 0:
                agent.sleep(cycles=3)
            if (index + 1) % 150 == 0:
                blocks.append(evade_n / max(1, danger_n))
                danger_n = evade_n = 0
        per_seed.append({"seed": seed, "last3": round(sum(blocks[-3:]) / 3, 3), "chains": chain_count(agent)})
        print(json.dumps(per_seed[-1]), flush=True)
    values = [row["last3"] for row in per_seed]
    return {"mode": "learning", "per_seed": per_seed, "mean": round(statistics.mean(values), 3),
            "median": round(statistics.median(values), 3)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("cost", "learning"))
    parser.add_argument("--decisions", type=int, default=12000)
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--learn-decisions", type=int, default=1500)
    parser.add_argument("--no-visit-decay", action="store_true", help="ablation: turn visit-count fading off")
    parser.add_argument("--json", default=None)
    args = parser.parse_args(argv)
    result = run_cost(args.decisions) if args.mode == "cost" else run_learning(args.seeds, args.learn_decisions, not args.no_visit_decay)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
