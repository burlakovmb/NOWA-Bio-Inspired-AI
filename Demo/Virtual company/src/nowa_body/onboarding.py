"""Offline lessons, sleep, and durable checkpoints for one named employee.

No EmployeeSession, transports, tool execution, or LLM are constructed here.
Evaluation calls the real Agent decision path and never supplies its answer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from unittest.mock import patch

from ._compat import ensure_core_src_on_path

ensure_core_src_on_path()
from agent_factory import AgentConfig, AgentFactory
from learning_guard import stable_fingerprint, stable_payload

from .employee_checkpoint import load_mind, save_mind
from .employee_config import AGENT_ID_RE, EmployeeConfig, save_employee_config
from .role_config import build_seeder, build_tool_registry, load_role_config
from .runtime import BusinessAgentRuntime
from .sleep_scheduler import SleepScheduler, configure_plasticity

WAIT = "wait_and_monitor"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def journal(path: Path, value) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def validate_lessons(corpus: dict, actions: set[str]) -> list[dict]:
    lessons = corpus.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        raise ValueError("a nonempty lesson list is required")
    identifiers = set()
    for lesson in lessons:
        if not isinstance(lesson, dict):
            raise ValueError("lesson must be an object")
        identifier = lesson.get("id")
        context = lesson.get("context_tokens")
        reward = lesson.get("reward")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("lesson ids must be nonempty and unique")
        identifiers.add(identifier)
        if not isinstance(context, list) or not context or any(
            not isinstance(t, str) or not t or t.startswith("action:") for t in context
        ):
            raise ValueError("context must contain nonempty observation tokens, not actions")
        if lesson.get("action") not in actions:
            raise ValueError("lesson action is outside the role vocabulary")
        if isinstance(reward, bool) or not isinstance(reward, (int, float)) or not math.isfinite(reward) or not -1 <= reward <= 1:
            raise ValueError("reward must be finite and in [-1, 1]")
        if not isinstance(lesson.get("provenance"), dict) or not lesson["provenance"].get("source"):
            raise ValueError("every lesson requires source provenance")
        if not isinstance(lesson.get("consequence"), str) or not lesson["consequence"]:
            raise ValueError("every lesson requires a consequence")
    return lessons


def make_runtime(role_path: Path, agent_id: str, seed: int):
    role = load_role_config(str(role_path))
    registry = build_tool_registry(agent_id, role)
    actions = [cap.tool_id for cap in registry.motor_capabilities()] + [WAIT]
    random.seed(seed)
    agent = AgentFactory(AgentConfig(actions=actions)).spawn_default(agent_id=agent_id)
    configure_plasticity(agent, SleepScheduler(circadian_window=(2, 5), min_interval_s=3600))
    runtime = BusinessAgentRuntime(agent, registry, approval_gate=None)
    return agent, runtime, role


def train(employee_dir: Path, role_path: Path, corpus_path: Path, *, seed: int = 20261103) -> dict:
    """Create a new employee only; an existing directory is never overwritten."""
    agent_id = employee_dir.name
    if not AGENT_ID_RE.fullmatch(agent_id):
        raise ValueError("invalid employee id")
    if employee_dir.exists():
        raise FileExistsError(f"employee directory already exists: {employee_dir}")
    corpus = read_json(corpus_path)
    agent, runtime, role = make_runtime(role_path, agent_id, seed)
    lessons = validate_lessons(corpus, set(agent.selector.actions))
    employee_dir.mkdir(parents=True, exist_ok=False)
    training = employee_dir / "training"
    training.mkdir()
    frozen = training / "corpus.json"
    shutil.copyfile(corpus_path, frozen)
    log = training / "lessons.jsonl"
    config = EmployeeConfig(agent_id=agent_id, display_name=corpus.get("display_name", agent_id),
                            role_ids=[role.role_id], seed_intuition=False, auto_execute=False)
    save_employee_config(config, employee_dir.parent, create_backup=False)
    seeded = build_seeder(role).seed_agent(agent)
    agent.sleep(cycles=3)
    save_mind(agent, training / "baseline.nowa")
    before = stable_fingerprint(agent)
    journal(log, {"event": "baseline", "seed_episodes": seeded, "fingerprint": before,
                  "checkpoint_sha256": digest(training / "baseline.nowa")})
    stored = []
    for lesson in lessons:
        episode = runtime.teach(lesson["context_tokens"], lesson["action"], lesson["reward"], lesson["consequence"])
        if episode is None or not getattr(episode, "td_outcome_committed", False):
            raise RuntimeError("lesson did not reach the real two-tier memory")
        stored.append(episode)
        journal(log, {"event": "lesson", "lesson": lesson, "episode_id": getattr(episode, "episode_id", None)})
    awake = stable_fingerprint(agent)
    if awake != before:
        raise RuntimeError("a lesson changed the stable tier while awake")
    save_mind(agent, training / "awake.nowa")
    sleep_result = agent.sleep(cycles=3)
    after = stable_fingerprint(agent)
    consolidated = sum(bool(getattr(e, "consolidated", False)) for e in stored)
    checkpoint = employee_dir / "mind.nowa"
    save_mind(agent, checkpoint)
    checkpoints = training / "checkpoints"
    checkpoints.mkdir()
    shutil.copyfile(checkpoint, checkpoints / "cycle-001.nowa")
    result = {"agent_id": agent_id, "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "seed": seed, "role_path": str(role_path.resolve()), "role_sha256": digest(role_path),
              "corpus_sha256": digest(frozen), "seed_episodes": seeded, "lessons": len(lessons),
              "consolidated_lessons": consolidated, "waking_stable_unchanged": awake == before,
              "sleep_changed_stable": after != before, "stable_before": before, "stable_after": after,
              "episode_count": len(agent.hippocampus.experiences), "cortex_patterns": len(agent.cortex.patterns),
              "checkpoint_sha256": digest(checkpoint), "sleep_result": sleep_result,
              "stable_components": component_hashes(agent),
              "network_policy": "denied_by_cli_audit_hook", "deployment_ready": False}
    journal(log, {"event": "checkpoint", "cycle": 1, "sha256": result["checkpoint_sha256"],
                  "stable_fingerprint": after, "consolidated_lessons": consolidated})
    write_json(training / "training-result.json", result)
    return result


def evaluate(employee_dir: Path, probes_path: Path) -> dict:
    """Separate-process, frozen-probe evaluation. Never teaches or saves the mind."""
    report = read_json(employee_dir / "training/training-result.json")
    role = Path(report["role_path"])
    if digest(role) != report["role_sha256"]:
        raise ValueError("role changed since this training cycle")
    mind = employee_dir / "mind.nowa"
    if digest(mind) != report["checkpoint_sha256"]:
        raise ValueError("mind changed since this training cycle")
    probes = read_json(probes_path)["probes"]
    rows = []
    fingerprints = []
    mismatched_components = set()
    for stage, path, elapsed, age in [("baseline", employee_dir / "training/baseline.nowa", 0, 0),
                                     ("reloaded", mind, 0, 0), ("host_time_24h", mind, 86400, 0),
                                     ("memory_age_24h", mind, 86400, 86400),
                                     ("memory_age_7d", mind, 604800, 604800)]:
        for index, probe in enumerate(probes):
            # Only this offline process sees the shifted clock. The OS clock
            # and saved files are unchanged; wall-clock memory recency ages too.
            # Anchor every run to that checkpoint's timestamp: evaluating a
            # baseline later must not silently age it relative to the trainee.
            with patch("time.time", return_value=path.stat().st_mtime + age):
                agent, _, _ = make_runtime(role, report["agent_id"], report["seed"])
                load_mind(agent, path)
                before = stable_fingerprint(agent)
                if stage == "reloaded":
                    fingerprints.append(before == report["stable_after"])
                    actual = component_hashes(agent)
                    mismatched_components.update(k for k, v in report["stable_components"].items() if actual.get(k) != v)
                random.seed(report["seed"] + index)
                action = agent.step(probe["context_tokens"], decision_only=True, dt=elapsed)
                rows.append({"stage": stage, "id": probe["id"], "group": probe["group"],
                             "expected_action": probe["expected_action"], "chosen_action": action,
                             "correct": action == probe["expected_action"],
                             "stable_unchanged": before == stable_fingerprint(agent)})
    result = {"agent_id": report["agent_id"], "probes_sha256": digest(probes_path),
              "new_process_pid": os.getpid(), "restored_stable_exactly": all(fingerprints),
              "completed_cycles": report.get("completed_cycles", 1),
              "trained_checkpoint_sha256": report["checkpoint_sha256"],
              "clock_policy": "checkpoint mtime + explicit memory age; process-local time.time patch",
              "mind_file_unchanged": digest(mind) == report["checkpoint_sha256"],
              "mismatched_stable_components": sorted(mismatched_components),
              "network_policy": "denied_by_cli_audit_hook", "rows": rows, "deployment_ready": False}
    write_json(employee_dir / "training/evaluation-result.json", result)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    write_json(employee_dir / f"training/evaluations/{stamp}.json", result)
    return result


def practice(employee_dir: Path, cycles: int = 3) -> dict:
    """Fixed repeated practice of the frozen lessons; no probe input."""
    if not 1 <= cycles <= 10:
        raise ValueError("practice requires 1 to 10 cycles")
    training = employee_dir / "training"
    report = read_json(training / "training-result.json")
    if report.get("active_phase") not in (None, "initial"):
        raise ValueError("practice requires the active phase corpus; use its audited training runner")
    role_path = Path(report["role_path"])
    if digest(role_path) != report["role_sha256"] or digest(employee_dir / "mind.nowa") != report["checkpoint_sha256"]:
        raise ValueError("role or checkpoint changed outside this training run")
    if digest(training / "corpus.json") != report["corpus_sha256"]:
        raise ValueError("frozen lesson corpus changed")
    agent, runtime, _ = make_runtime(role_path, report["agent_id"], report["seed"])
    load_mind(agent, employee_dir / "mind.nowa")
    lessons = validate_lessons(read_json(training / "corpus.json"), set(agent.selector.actions))
    completed = int(report.get("completed_cycles", 1))
    if (training / "evaluation-result.json").exists():
        archived = training / f"evaluation-cycle-{completed:03}.json"
        if archived.exists():
            raise FileExistsError("an evaluation archive already exists for this cycle")
        shutil.copyfile(training / "evaluation-result.json", archived)
    for cycle in range(completed + 1, completed + cycles + 1):
        before = stable_fingerprint(agent)
        stored = []
        for lesson in lessons:
            episode = runtime.teach(lesson["context_tokens"], lesson["action"], lesson["reward"], lesson["consequence"])
            if episode is None or not getattr(episode, "td_outcome_committed", False):
                raise RuntimeError("practice failed to store a known outcome")
            stored.append(episode)
            journal(training / "lessons.jsonl", {"event": "lesson", "cycle": cycle, "lesson": lesson})
        if stable_fingerprint(agent) != before:
            raise RuntimeError("practice changed stable memory while awake")
        sleep_result = agent.sleep(cycles=3)
        checkpoint = training / "checkpoints" / f"cycle-{cycle:03}.nowa"
        if checkpoint.exists():
            raise FileExistsError("cycle checkpoint already exists")
        save_mind(agent, employee_dir / "mind.nowa")
        shutil.copyfile(employee_dir / "mind.nowa", checkpoint)
        report.update(completed_cycles=cycle, distinct_lessons=len(lessons),
                      lessons=report["lessons"] + len(lessons),
                      consolidated_lessons=report["consolidated_lessons"] + sum(bool(getattr(e, "consolidated", False)) for e in stored),
                      stable_after=stable_fingerprint(agent), stable_components=component_hashes(agent),
                      checkpoint_sha256=digest(employee_dir / "mind.nowa"), sleep_result=sleep_result,
                      episode_count=len(agent.hippocampus.experiences), cortex_patterns=len(agent.cortex.patterns))
        journal(training / "lessons.jsonl", {"event": "checkpoint", "cycle": cycle,
                "sha256": report["checkpoint_sha256"], "stable_fingerprint": report["stable_after"]})
        write_json(training / "training-result.json", report)
    return report


def component_hashes(agent) -> dict:
    return {key: hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
            for key, value in stable_payload(agent).items()}


def offline_audit(event, args) -> None:
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.bind", "subprocess.Popen", "os.system"}:
        raise RuntimeError(f"offline onboarding forbids {event}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["train", "practice", "evaluate"])
    parser.add_argument("--employee-dir", type=Path, required=True)
    parser.add_argument("--role", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--probes", type=Path)
    parser.add_argument("--cycles", type=int, default=3)
    args = parser.parse_args()
    os.environ["NOWA_STRICT_LEARNING"] = "1"
    sys.addaudithook(offline_audit)
    if args.mode == "train":
        if not args.role or not args.corpus:
            parser.error("train requires --role and --corpus")
        result = train(args.employee_dir, args.role, args.corpus)
    elif args.mode == "practice":
        result = practice(args.employee_dir, args.cycles)
    else:
        if not args.probes:
            parser.error("evaluate requires --probes")
        result = evaluate(args.employee_dir, args.probes)
    print(json.dumps(result, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
