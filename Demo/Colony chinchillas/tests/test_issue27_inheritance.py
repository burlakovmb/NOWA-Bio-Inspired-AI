"""Mendelian colony inheritance (issue 27)."""

from __future__ import annotations

import logging
import random

import pytest

from colony_agent import NEWBORN_ENERGY, ChinchillaAgent
from genome import GENE_REGISTRY, GenomeVector
from neuromodulators import NeuromodulatorState


def _identity_mutate(self, rate=0.05, sigma_scale=1.0, rng=None):
    del rate, sigma_scale, rng
    return self


def _parents(seed: int) -> tuple[ChinchillaAgent, ChinchillaAgent]:
    rng = random.Random(seed)
    mother = ChinchillaAgent(
        sex="F",
        is_mature=True,
        genome=GenomeVector.random(rng),
        rng_seed=seed,
        name="mother",
    )
    father = ChinchillaAgent(
        sex="M",
        is_mature=True,
        genome=GenomeVector.random(rng),
        rng_seed=seed + 1,
        name="father",
    )
    mother.colony = [mother, father]
    father.colony = [mother, father]
    return mother, father


def _mean_gene_variance(genomes: list[GenomeVector]) -> float:
    count = float(len(genomes))
    total = 0.0
    for key in GENE_REGISTRY:
        values = [float(genome.genes[key]) for genome in genomes]
        mean = sum(values) / count
        total += sum((value - mean) ** 2 for value in values) / count
    return total / float(len(GENE_REGISTRY))


def _breed(founders: list[GenomeVector], mode: str, generations: int, seed: int) -> list[GenomeVector]:
    rng = random.Random(seed)
    population = list(founders)
    size = len(population)
    for _ in range(generations):
        nxt: list[GenomeVector] = []
        for _index in range(size):
            mother = population[rng.randrange(size)]
            father = population[rng.randrange(size)]
            child, _other = mother.crossover(father, alpha=0.5, mode=mode, rng=rng)
            nxt.append(child.mutate(rate=0.05, rng=rng))
        population = nxt
    return population


def test_siblings_differ_and_each_allele_comes_from_one_parent(monkeypatch) -> None:
    monkeypatch.setattr(GenomeVector, "mutate", _identity_mutate)
    mother, father = _parents(27)
    sister = mother._create_offspring(father)
    brother = mother._create_offspring(father)

    assert sister.genome is not None and brother.genome is not None
    assert sister.genome.genes != brother.genome.genes

    heterozygous = 0
    from_mother = 0
    for key, child_val in sister.genome.genes.items():
        maternal = float(mother.genome.genes[key])
        paternal = float(father.genome.genes[key])
        allele = float(child_val)
        assert allele == pytest.approx(maternal) or allele == pytest.approx(paternal)
        if abs(maternal - paternal) <= 1e-9:
            continue
        heterozygous += 1
        if allele == pytest.approx(maternal):
            from_mother += 1

    assert heterozygous > 0
    meta = sister.genome_inheritance_meta
    assert meta["crossover_mode"] == "uniform"
    assert "crossover_alpha" not in meta
    assert meta["mutation_rate"] == pytest.approx(0.05)
    assert meta["mother_contrib_mean"] == pytest.approx(from_mother / heterozygous)
    assert meta["father_contrib_mean"] == pytest.approx(1.0 - (from_mother / heterozygous))
    assert meta["mother_contrib_mean"] + meta["father_contrib_mean"] == pytest.approx(1.0)


def test_uniform_variance_does_not_collapse_like_arithmetic() -> None:
    rng = random.Random(270)
    founders = [GenomeVector.random(rng) for _ in range(24)]
    initial = _mean_gene_variance(founders)
    generations = 8
    uniform = _mean_gene_variance(_breed(founders, "uniform", generations, seed=271))
    arithmetic = _mean_gene_variance(_breed(founders, "arithmetic", generations, seed=271))

    assert initial > 0.0
    assert uniform > arithmetic * 5.0
    assert uniform > initial * 0.4


def test_maternal_stress_and_parent_energy_stay_with_the_parents(monkeypatch) -> None:
    monkeypatch.setattr(GenomeVector, "mutate", _identity_mutate)
    mother, father = _parents(2711)
    mother.neuromodulators.cortisol = 0.97
    father.neuromodulators.cortisol = 0.91
    mother.neuromodulators.dopamine = 0.88
    mother.energy = 0.04
    father.energy = 0.11
    mother.social_drive = 0.02
    father.social_drive = 0.97
    parental_energy_mean = (mother.energy + father.energy) / 2.0

    child = mother._create_offspring(father)

    assert child.neuromodulators.cortisol == pytest.approx(NeuromodulatorState.BASELINE_CORT)
    assert child.neuromodulators.dopamine == pytest.approx(NeuromodulatorState.BASELINE_DA)
    assert child.neuromodulators.cortisol < 0.2
    assert child.energy == pytest.approx(NEWBORN_ENERGY)
    assert child.energy != pytest.approx(parental_energy_mean)
    assert child.social_drive == pytest.approx(float(child.genome.genes["dr_social_drive_baseline"]))
    assert abs(child.social_drive - ((0.02 + 0.97) / 2.0)) > 0.05
    assert child.affective_space.axis_decay["stress"] == pytest.approx(
        float(child.genome.genes["af_decay_stress"])
    )


def test_birth_without_genome_still_warns_and_starts_fresh(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mother = ChinchillaAgent(sex="F", is_mature=True, genome=None, rng_seed=27)
    mother.colony = [mother]
    mother.neuromodulators.cortisol = 0.93
    mother.energy = 0.08

    with caplog.at_level(logging.WARNING, logger="colony_agent"):
        child = mother._create_offspring(None, father_id_hint="father-already-gone")

    assert "without a recombined genome" in caplog.text
    assert child.genome is None
    assert child.neuromodulators.cortisol == pytest.approx(NeuromodulatorState.BASELINE_CORT)
    assert child.energy == pytest.approx(NEWBORN_ENERGY)
    assert child.parents[1] == "father-already-gone"
