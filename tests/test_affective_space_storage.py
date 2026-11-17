import json
from pathlib import Path

import pytest

from affective_space import AffectiveSpace
from genome import GENE_REGISTRY
from storage import AgentStorage
from hippocampus import NOWAHippocampus
from cortex import CortexMemory
from selector import ActionSelector


def test_affective_space_save_load(tmp_path):
    hip = NOWAHippocampus()
    cortex = CortexMemory()
    selector = ActionSelector(actions=["a"])

    space = AffectiveSpace(
        axes={"valence": 0.3, "stress": 0.2},
        baseline={"valence": 0.1},
        alpha=0.9,
        lambda_reg=0.07,
        # Inside af_baseline_adapt_rate (tau 1.5 h .. 24 h). 0.015 is outside
        # that gene and storage.load now clamps it; see the legacy load test.
        baseline_adapt_rate=1.0 / (3.0 * 3600.0),
        norm_cap_base=1.5,
        norm_cap_max=2.0,
        norm_cap_adapt_rate=0.1,
        norm_cap_release_rate=0.03,
        norm_cap_global_release_rate=0.011,
        legacy_compat_weight=0.35,
        axis_decay={"valence": 0.91, "arousal": 0.77, "dominance": 0.96},
        decay={"valence": 0.2},
        inertia={"valence": 0.1},
        noise_sigma={"valence": 0.0},
        fall_rate={"valence": 0.4},
    )

    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        hip,
        cortex,
        selector,
        affective_space=space,
        filename="affective_space.pkl",
    )

    restored = AffectiveSpace()
    storage.load_agent(
        hip,
        cortex,
        selector,
        path,
        affective_space=restored,
    )

    assert abs(restored.axes["valence"] - space.axes["valence"]) < 1e-6
    assert abs(restored.axes["stress"] - space.axes["stress"]) < 1e-6
    assert abs(restored.baseline["valence"] - space.baseline["valence"]) < 1e-6
    assert abs(restored.alpha - space.alpha) < 1e-6
    assert abs(restored.lambda_reg - space.lambda_reg) < 1e-6
    assert abs(restored.baseline_adapt_rate - space.baseline_adapt_rate) < 1e-6
    assert abs(restored.norm_cap_base - space.norm_cap_base) < 1e-6
    assert abs(restored.norm_cap_max - space.norm_cap_max) < 1e-6
    assert abs(restored.norm_cap_adapt_rate - space.norm_cap_adapt_rate) < 1e-6
    assert abs(restored.norm_cap_release_rate - space.norm_cap_release_rate) < 1e-6
    assert abs(restored.norm_cap_global_release_rate - space.norm_cap_global_release_rate) < 1e-6
    assert abs(restored.legacy_compat_weight - space.legacy_compat_weight) < 1e-6
    assert abs(restored.axis_decay["valence"] - space.axis_decay["valence"]) < 1e-6
    assert abs(restored.axis_decay["arousal"] - space.axis_decay["arousal"]) < 1e-6
    assert abs(restored.axis_decay["dominance"] - space.axis_decay["dominance"]) < 1e-6
    assert abs(restored.affective_decay["valence"] - space.affective_decay["valence"]) < 1e-6
    assert abs(restored.decay["valence"] - space.decay["valence"]) < 1e-6
    assert abs(restored.inertia["valence"] - space.inertia["valence"]) < 1e-6
    assert abs(restored.fall_rate["valence"] - space.fall_rate["valence"]) < 1e-6


def _find_number(node, key):
    if isinstance(node, dict):
        value = node.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        for child in node.values():
            found = _find_number(child, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_number(child, key)
            if found is not None:
                return found
    return None


def test_load_clamps_legacy_baseline_adapt_rate(tmp_path):
    hip = NOWAHippocampus()
    cortex = CortexMemory()
    selector = ActionSelector(actions=["a"])
    space = AffectiveSpace(baseline_adapt_rate=0.002)
    storage = AgentStorage(save_dir=str(tmp_path))
    path = storage.save_agent(
        hip,
        cortex,
        selector,
        affective_space=space,
        filename="legacy.nowa",
    )

    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    assert _find_number(saved, "baseline_adapt_rate") == pytest.approx(0.002)

    restored = AffectiveSpace()
    with pytest.warns(RuntimeWarning, match="baseline_adapt_rate") as recorded:
        storage.load_agent(
            hip,
            cortex,
            selector,
            path,
            affective_space=restored,
        )

    assert len(recorded) == 1
    assert restored.baseline_adapt_rate == pytest.approx(
        GENE_REGISTRY["af_baseline_adapt_rate"].max_val
    )
