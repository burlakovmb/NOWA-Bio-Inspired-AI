import random

import pytest

from genome import GENE_REGISTRY, GENOME_VERSION, GenomeVector


def test_tc_01_default_genome_creation():
    genome = GenomeVector.default()

    assert set(genome.genes.keys()) == set(GENE_REGISTRY.keys())
    for key, descriptor in GENE_REGISTRY.items():
        assert genome.genes[key] == descriptor.default, f"TC-01 fail: {key}"
    assert genome.validate() == []
    assert genome.generation == 0


def test_tc_02_mutation_does_not_change_original():
    original = GenomeVector.default()
    mutated = original.mutate(rate=1.0, sigma_scale=2.0, rng=random.Random(42))

    for key in GENE_REGISTRY:
        assert original.genes[key] == GENE_REGISTRY[key].default
    assert original.genes != mutated.genes
    for key, descriptor in GENE_REGISTRY.items():
        assert descriptor.min_val <= mutated.genes[key] <= descriptor.max_val


def test_tc_03_mutation_rate_zero_returns_exact_copy():
    genome = GenomeVector.default()
    clone = genome.mutate(rate=0.0, rng=random.Random(0))
    assert genome.genes == clone.genes
    assert genome.generation == clone.generation
    assert genome.lineage_id == clone.lineage_id


def test_tc_04_arithmetic_crossover():
    rng = random.Random(0)
    parent_a = GenomeVector.random(rng)
    parent_b = GenomeVector.random(rng)

    child_a, child_b = parent_a.crossover(parent_b, alpha=0.5, mode="arithmetic")

    for key in GENE_REGISTRY:
        value_a = parent_a.genes[key]
        value_b = parent_b.genes[key]
        expected = 0.5 * value_a + 0.5 * value_b
        assert abs(child_a.genes[key] - expected) < 1e-9
        assert abs(child_b.genes[key] - expected) < 1e-9

    assert child_a.generation == 1
    assert child_b.generation == 1


def test_tc_05_uniform_crossover_genes_come_from_parents():
    parent_a = GenomeVector.default()
    parent_b = GenomeVector.random(random.Random(42))
    child_a, child_b = parent_a.crossover(
        parent_b,
        mode="uniform",
        rng=random.Random(42),
    )

    for key in GENE_REGISTRY:
        value = child_a.genes[key]
        assert value == parent_a.genes[key] or value == parent_b.genes[key]
        opposite = child_b.genes[key]
        if value == parent_a.genes[key]:
            assert opposite == parent_b.genes[key]
        else:
            assert opposite == parent_a.genes[key]


def test_tc_06_distance_properties():
    genome_a = GenomeVector.default()
    genome_b = GenomeVector.default()

    assert genome_a.distance(genome_a) == 0.0
    assert genome_a.distance(genome_b) == 0.0

    genome_c = GenomeVector.random(random.Random(7))
    assert abs(genome_a.distance(genome_c) - genome_c.distance(genome_a)) < 1e-9
    assert 0.0 <= genome_a.distance(genome_c) <= 1.0

    min_genome = GenomeVector(genes={k: d.min_val for k, d in GENE_REGISTRY.items()})
    max_genome = GenomeVector(genes={k: d.max_val for k, d in GENE_REGISTRY.items()})
    assert abs(min_genome.distance(max_genome) - 1.0) < 1e-9


def test_tc_07_to_dict_from_dict_round_trip():
    genome = GenomeVector.random(random.Random(13))
    genome_dict = genome.to_dict()
    restored = GenomeVector.from_dict(genome_dict)

    assert genome.genes == restored.genes
    assert genome.generation == restored.generation
    assert genome.lineage_id == restored.lineage_id
    assert genome_dict["version"] == GENOME_VERSION


def test_tc_08_to_array_from_array_round_trip():
    genome = GenomeVector.random(random.Random(99))
    values = genome.to_array()

    assert len(values) == len(GENE_REGISTRY)

    restored = GenomeVector.from_array(values)
    assert genome.genes == restored.genes


def test_tc_09_from_array_wrong_length_raises():
    with pytest.raises(ValueError):
        GenomeVector.from_array([0.1, 0.2])


def test_tc_10_to_agent_params_contains_all_modules():
    genome = GenomeVector.default()
    params = genome.to_agent_params()

    required_modules = [
        "affective_space",
        "wakefulness",
        "neuromodulators",
        "autonomous",
        "mortality",
        "value_layer",
        "hippocampus",
        "sleep",
        "imagination",
    ]
    for module in required_modules:
        assert module in params

    assert params["affective_space"]["axis_decay"]["valence"] == genome.genes["af_decay_valence"]
    assert params["value_layer"]["gamma_default"] == genome.genes["lr_gamma"]
    assert params["wakefulness"]["circadian_amplitude"] == genome.genes["wk_circadian_amplitude"]
    assert params["autonomous"]["perception_radius_factor"] == genome.genes["dr_perception_radius_factor"]
    assert params["mortality"]["max_lifespan_factor"] == genome.genes["lt_max_lifespan_factor"]


def test_tc_11_validate_detects_violations():
    genome = GenomeVector.default()
    genome.genes["lr_gamma"] = 1.5

    warnings = genome.validate()
    assert len(warnings) > 0
    assert any("lr_gamma" in warning for warning in warnings)


def test_tc_12_crossover_unknown_mode_raises():
    parent_a = GenomeVector.default()
    parent_b = GenomeVector.default()
    with pytest.raises(ValueError):
        parent_a.crossover(parent_b, mode="unknown_mode")


def test_tc_13_determinism_with_fixed_rng():
    genome = GenomeVector.default()
    mutated_a = genome.mutate(rate=0.3, rng=random.Random(42))
    mutated_b = genome.mutate(rate=0.3, rng=random.Random(42))
    assert mutated_a.genes == mutated_b.genes


def test_tc_14_summary_contains_all_groups():
    genome = GenomeVector.default()
    summary = genome.summary()

    for group in ["NM", "AF", "WK", "DR", "LR", "IM", "LT"]:
        assert group in summary
        assert "mean" in summary[group]
        assert "std" in summary[group]
        assert "deviation_from_default" in summary[group]


def test_from_dict_fills_missing_genes_and_clamps():
    payload = {
        "generation": -10,
        "lineage_id": "line-a",
        "genes": {
            "lr_gamma": 100.0,
            "unknown_gene": 123.0,
        },
    }

    with pytest.warns(RuntimeWarning):
        genome = GenomeVector.from_dict(payload)

    assert genome.generation == 0
    assert genome.lineage_id == "line-a"
    assert genome.genes["lr_gamma"] == GENE_REGISTRY["lr_gamma"].max_val
    assert genome.genes["af_decay_valence"] == GENE_REGISTRY["af_decay_valence"].default


def test_sbx_crossover_is_deterministic_and_within_ranges():
    parent_a = GenomeVector.random(random.Random(11))
    parent_b = GenomeVector.random(random.Random(12))

    child_a_1, child_b_1 = parent_a.crossover(parent_b, mode="sbx", rng=random.Random(77))
    child_a_2, child_b_2 = parent_a.crossover(parent_b, mode="sbx", rng=random.Random(77))

    assert child_a_1.genes == child_a_2.genes
    assert child_b_1.genes == child_b_2.genes
    assert child_a_1.generation == max(parent_a.generation, parent_b.generation) + 1
    assert child_b_1.generation == max(parent_a.generation, parent_b.generation) + 1

    for key, descriptor in GENE_REGISTRY.items():
        assert descriptor.min_val <= child_a_1.genes[key] <= descriptor.max_val
        assert descriptor.min_val <= child_b_1.genes[key] <= descriptor.max_val


def test_crossover_lineage_id_is_built_and_truncated():
    long_a = "A" * 40
    long_b = "B" * 40
    parent_a = GenomeVector.default()
    parent_b = GenomeVector.default()
    parent_a.genes["lr_gamma"] = 0.9
    parent_b.genes["lr_gamma"] = 0.95
    parent_a = GenomeVector(genes=parent_a.genes, lineage_id=long_a)
    parent_b = GenomeVector(genes=parent_b.genes, lineage_id=long_b)

    child_a, child_b = parent_a.crossover(parent_b, mode="arithmetic")
    expected = f"{long_a}x{long_b}"[:64]
    assert child_a.lineage_id == expected
    assert child_b.lineage_id == expected


def _assert_baseline_adapt_tau(rate: float) -> None:
    tau_s = 1.0 / rate
    assert 1.5 * 3600.0 - 1e-6 <= tau_s <= 24.0 * 3600.0 + 1e-6


def test_af_baseline_adapt_rate_random_mutate_crossover_stay_on_hour_scale():
    gene = GENE_REGISTRY["af_baseline_adapt_rate"]
    assert gene.default == pytest.approx(1.0 / (6.0 * 3600.0))
    assert gene.min_val == pytest.approx(gene.default / 4.0)
    assert gene.max_val == pytest.approx(gene.default * 4.0)
    assert gene.sigma == pytest.approx(0.5 / (6.0 * 3600.0))

    rng = random.Random(74)
    for _ in range(1000):
        _assert_baseline_adapt_tau(GenomeVector.random(rng).genes["af_baseline_adapt_rate"])

    chain = GenomeVector.random(random.Random(7401))
    chain_rng = random.Random(7402)
    for step in range(200):
        scale = 5.0 if step % 2 == 0 else 1.0
        chain = chain.mutate(rate=1.0, sigma_scale=scale, rng=chain_rng)
        _assert_baseline_adapt_tau(chain.genes["af_baseline_adapt_rate"])
        other = GenomeVector.random(chain_rng)
        mode = "sbx" if step % 2 == 0 else "arithmetic"
        child_a, child_b = chain.crossover(other, mode=mode, rng=chain_rng)
        _assert_baseline_adapt_tau(child_a.genes["af_baseline_adapt_rate"])
        _assert_baseline_adapt_tau(child_b.genes["af_baseline_adapt_rate"])
        chain = child_a


def test_from_dict_clamps_legacy_baseline_adapt_rate():
    payload = {
        "generation": 3,
        "lineage_id": "legacy",
        "genes": dict(GenomeVector.default().genes),
    }
    payload["genes"]["af_baseline_adapt_rate"] = 0.002

    with pytest.warns(RuntimeWarning, match="af_baseline_adapt_rate") as recorded:
        genome = GenomeVector.from_dict(payload)

    assert len(recorded) == 1
    assert genome.generation == 3
    assert genome.lineage_id == "legacy"
    assert genome.genes["af_baseline_adapt_rate"] == pytest.approx(
        GENE_REGISTRY["af_baseline_adapt_rate"].max_val
    )
