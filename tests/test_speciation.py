"""Tests for the genetic-distance diversity metrics (fixed topology, poc3)."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from random import Random

import numpy as np
import pytest

from src.config import SimConfig
from src.genome import Genome
from src.speciation import (
    assign_species,
    compatibility_distance,
    count_species,
    mean_pairwise_distance,
)

NUM_INPUTS = 33
NUM_OUTPUTS = 2
LAYER_SHAPES = [(NUM_INPUTS, NUM_OUTPUTS)]


@pytest.fixture(name="spec")
def spec_fixture():
    return SimConfig.from_yaml("config/default.yaml").speciation


@pytest.fixture(name="gcfg")
def gcfg_fixture():
    return SimConfig.from_yaml("config/default.yaml").genome


def _fresh(gcfg, seed: int) -> Genome:
    return Genome.new_random(gcfg, LAYER_SHAPES, Random(seed))


# --------------------------------------------------------------------------- #
# compatibility_distance
# --------------------------------------------------------------------------- #
def test_identical_genomes_distance_zero(spec, gcfg):
    genome = _fresh(gcfg, 1)
    assert compatibility_distance(genome, genome.clone(), spec) == 0.0


def test_empty_genomes_distance_zero(spec):
    empty_a = Genome([], np.array([]))
    empty_b = Genome([], np.array([]))
    assert compatibility_distance(empty_a, empty_b, spec) == 0.0


def test_weight_difference_drives_distance(spec, gcfg):
    genome = _fresh(gcfg, 2)
    twin = genome.clone()
    delta = 4.0
    twin.weights[0] += delta
    n = genome.weights.size
    expected = spec.c_weight * (delta / n)
    assert compatibility_distance(genome, twin, spec) == pytest.approx(expected)


def test_larger_divergence_increases_distance(spec, gcfg):
    base = _fresh(gcfg, 3)
    small_mutant = base.clone()
    small_mutant.mutate(gcfg, Random(1))
    big_mutant = base.clone()
    for _ in range(20):
        big_mutant.mutate(gcfg, Random(2))
        big_mutant.weights += 0.1  # force divergence beyond weight_mutation_rate luck

    dist_small = compatibility_distance(base, small_mutant, spec)
    dist_big = compatibility_distance(base, big_mutant, spec)
    assert dist_big > dist_small


# --------------------------------------------------------------------------- #
# count_species
# --------------------------------------------------------------------------- #
def test_clones_form_single_species(spec, gcfg):
    genome = _fresh(gcfg, 4)
    population = [genome.clone() for _ in range(10)]
    assert count_species(population, spec) == 1


def test_divergent_genomes_form_multiple_species(spec, gcfg):
    base = _fresh(gcfg, 5)
    far = base.clone()
    far.weights += 10.0  # well beyond compatibility_threshold
    assert count_species([base, far], spec) == 2


def test_empty_population_zero_species(spec):
    assert count_species([], spec) == 0


# --------------------------------------------------------------------------- #
# assign_species (backs fitness sharing in Simulation, not just the metrics)
# --------------------------------------------------------------------------- #
def test_assign_species_clones_share_one_id(spec, gcfg):
    genome = _fresh(gcfg, 4)
    population = [genome.clone() for _ in range(10)]
    assert assign_species(population, spec) == [0] * 10


def test_assign_species_divergent_genomes_get_distinct_ids(spec, gcfg):
    base = _fresh(gcfg, 5)
    far = base.clone()
    far.weights += 10.0
    assert assign_species([base, far], spec) == [0, 1]


def test_assign_species_empty_population():
    assert not assign_species([], SimConfig.from_yaml("config/default.yaml").speciation)


# --------------------------------------------------------------------------- #
# mean_pairwise_distance
# --------------------------------------------------------------------------- #
def test_mean_pairwise_needs_two(spec, gcfg):
    assert mean_pairwise_distance([], spec) == 0.0
    assert mean_pairwise_distance([_fresh(gcfg, 6)], spec) == 0.0


def test_mean_pairwise_zero_for_clones(spec, gcfg):
    genome = _fresh(gcfg, 7)
    assert mean_pairwise_distance([genome, genome.clone()], spec) == 0.0


def test_mean_pairwise_positive_when_divergent(spec, gcfg):
    base = _fresh(gcfg, 8)
    mutant = base.clone()
    mutant.weights += 1.0
    assert mean_pairwise_distance([base, mutant], spec) > 0.0


def test_mean_pairwise_matches_naive_definition(spec, gcfg):
    """Regression guard: the NumPy-vectorised path vs the O(pop²) definition.

    Independent reference — sums ``compatibility_distance`` over every pair
    directly. Population mixes clones and weight-mutated genomes.
    """
    rng = Random(21)
    base = Genome.new_random(gcfg, LAYER_SHAPES, rng)
    population = [base.clone() for _ in range(15)]
    for genome in population:
        genome.mutate(gcfg, rng)

    naive_total, naive_pairs = 0.0, 0
    for i in range(len(population)):
        for j in range(i + 1, len(population)):
            naive_total += compatibility_distance(population[i], population[j], spec)
            naive_pairs += 1
    naive = naive_total / naive_pairs

    assert mean_pairwise_distance(population, spec) == pytest.approx(naive)
