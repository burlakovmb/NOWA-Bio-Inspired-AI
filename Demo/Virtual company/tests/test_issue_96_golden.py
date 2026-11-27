"""Exact-float gate for the procurement slice frozen before issue #96.

The capture runs in a child process with ``PYTHONHASHSEED=0``. The script
freezes ``random.seed`` and ``time.time`` the same way it did when the
fixtures were written. A fallback buyer fails the run; the ninety-day
fixture must be the core agent, not an all-wait journal.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = DEMO_ROOT / "tools" / "golden_issue_96.py"
LONG_FIXTURE = (
    DEMO_ROOT / "tests" / "fixtures" / "issue_96_golden" / "seed42_q1_d90_price_on.json"
)


def test_issue_96_golden_matches_fixtures():
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--include-long"],
        cwd=str(DEMO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "core-agent agent.Agent" in proc.stderr
    assert "_FallbackAgent" not in proc.stderr


def test_ninety_day_fixture_is_the_core_agent():
    """The committed slice is the core buyer, not the all-wait fallback."""
    payload = json.loads(LONG_FIXTURE.read_text(encoding="utf-8"))
    quarter = payload["quarters"][0]
    accepted = sum(
        1
        for row in quarter["decisions"]
        if isinstance(row.get("result"), dict)
        and row["result"].get("status") == "accepted"
    )
    assert accepted == 34
    assert quarter["fitness"]["criteria"]["cost_efficiency"] == 0.2728340576406023
    assert quarter["cost_vs_chance"] == -0.09060087344927437
    actions = [row["action"] for row in quarter["decisions"]]
    assert any(action != "wait_and_monitor" for action in actions)
