"""Exact-float gate for the procurement slice frozen before issue #96.

The capture runs in a child process with ``PYTHONHASHSEED=0``. The script
freezes ``random.seed`` and ``time.time`` the same way it did when the
fixtures were written.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = DEMO_ROOT / "tools" / "golden_issue_96.py"


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
