# Hippocampal decay clock across save/load

Date: 2026-11-09. Status: independently confirmed P2 persistence defect.
Inspected upstream commit: `ff01ddcd6966e7298ed789e33fd4106fb05d16da`;
core tree: `0ca484475e9547fdab17a0c2b08638531500a25d`.
This report contains no Company data. No core fix has been made.
Published evidence: [supplement to issue #16](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16#issuecomment-6745692962).

The saved episode contains its already decayed `activation_energy`, but not the
signature's `last_decay_ts`. Rebuilding the signature uses `last_activated`,
which decay did not advance. Consequently the first decay after restoration
can apply an already accounted interval again.

## Minimal synthetic counterexample

Use one synthetic episode with energy `1.0` and both time anchors at `t0`.
Build its signature, then call `_apply_decay()` at `t0 + 3600`.
The default mixed kernel gives energy `0.5485`. Save with
`AgentStorage.save_agent`, load into a fresh `NOWAHippocampus` and rebuild
signatures. At the **same** `t0 + 3600`, call decay on both instances:

| Instance | Energy before call | Energy after call |
|---|---:|---:|
| Continuous | 0.5485 | 0.5485 |
| Restored | 0.5485 | 0.30085225 |

There is no elapsed time between the comparison calls. This rules out a
difference caused merely by partitioning a non-exponential kernel into
different time intervals. No Agent, decision, learning or sleep is involved.

## Source contract

- `src/hippocampus.py:535`: `_ensure_signature_store` reconstructs energy from
  the episode and the decay anchor from `last_activated`.
- `src/hippocampus.py:625`: `_apply_decay` updates episode energy and signature
  `last_decay_ts`; it leaves episode `last_activated` unchanged.
- `src/storage.py:16`: persistence saves experiences; signature decay anchors
  are not included. Episode serialization preserves energy and activation time.

Hippocampal constructor settings also are not serialized. Restoration uses
the caller's constructed settings; it does not forcibly reset an existing
host to defaults. The separate synthetic custom-half-life check demonstrates
that a fresh default host does not recover a producer's custom half-life.

## Evidence and limits

The standalone example below was extracted and executed successfully under
the project `.venv`, strict learning mode and no bytecode writes. It uses
actual core persistence and hippocampal decay on synthetic data. Product
and core sources remain unchanged.

Independent final QA reproduced the failure and passed `18` synthetic
checks. The same-time continuation invariant fails as shown above. The
standalone example's code is identical in both language versions.

This demonstrates a persistence asymmetry, not its effect on any employee's
choices. Correctness after restart needs a contract for preserving the decay
anchor alongside the already decayed energy, including legacy defaults and
unchanged-time continuation tests. The maintainer should choose that contract;
changing `last_activated` merely to carry a decay clock could alter its meaning.

## Standalone reproduction

Run this Python example with the repository's `src` on `PYTHONPATH`.
It creates and deletes only a temporary synthetic checkpoint.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import patch
from experience import Experience, Path as EventPath, Event, EventType
from hippocampus import NOWAHippocampus
from storage import AgentStorage

base = 1_790_000_000.0
with patch("time.time", return_value=base):
    episode = Experience(EventPath([Event("synthetic", EventType.CONTEXT)]))
episode.episode_id = "synthetic-1"
episode.activation_energy = 1.0
live = NOWAHippocampus()
live.experiences = [episode]
live._ensure_signature_store()
with patch("time.time", return_value=base + 3600):
    live._apply_decay()

with TemporaryDirectory(prefix="decay-contract-") as folder:
    storage = AgentStorage(folder)
    cortex = NS(patterns={})
    selector = NS(actions=[], confidence_threshold=0.0, action_metadata={})
    storage.save_agent(live, cortex, selector, filename="synthetic.pkl")
    restored = NOWAHippocampus()
    storage.load_agent(restored, cortex, selector, str(Path(folder) / "synthetic.pkl"))
    restored._ensure_signature_store()
    with patch("time.time", return_value=base + 3600):
        live._apply_decay()
        restored._apply_decay()
    continuous = live.experiences[0].activation_energy
    reloaded = restored.experiences[0].activation_energy
    assert abs(continuous - 0.5485) < 1e-12
    assert abs(reloaded - 0.30085225) < 1e-12
    print({"continuous": continuous, "reloaded": reloaded})
```
