"""Tests for the NEAT compatibility-distance diversity metrics."""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

from random import Random

import pytest

from src.config import SimConfig
from src.genome import Genome, InnovationTracker
from src.speciation import (
    assign_species,
    compatibility_distance,
    count_species,
    mean_pairwise_distance,
)

NUM_INPUTS = 33
NUM_OUTPUTS = 2


@pytest.fixture(name="spec")
def spec_fixture():
    return SimConfig.from_yaml("config/default.yaml").speciation


@pytest.fixture(name="gcfg")
def gcfg_fixture():
    return SimConfig.from_yaml("config/default.yaml").genome


def _fresh(seed: int) -> Genome:
    return Genome.new_fully_connected(
        SimConfig.from_yaml("config/default.yaml").genome,
        NUM_INPUTS,
        NUM_OUTPUTS,
        Random(seed),
        InnovationTracker(),
    )


# --------------------------------------------------------------------------- #
# compatibility_distance
# --------------------------------------------------------------------------- #
def test_identical_genomes_distance_zero(spec):
    genome = _fresh(1)
    assert compatibility_distance(genome, genome.clone(), spec) == 0.0


def test_two_empty_genomes_distance_zero(spec):
    empty_a = Genome([], [])
    empty_b = Genome([], [])
    assert compatibility_distance(empty_a, empty_b, spec) == 0.0


def test_weight_difference_drives_distance(spec):
    genome = _fresh(2)
    twin = genome.clone()
    delta = 4.0
    twin.connections[0].weight += delta
    n = len(genome.connections)
    # Only the weight term contributes (no structural difference).
    expected = spec.c_weight * (delta / n)
    assert compatibility_distance(genome, twin, spec) == pytest.approx(expected)


def test_structural_difference_increases_distance(spec, gcfg):
    # Base and mutant must share one tracker so split edges get genuinely new
    # innovation numbers — exactly the global-TRACKER invariant the simulation
    # upholds. A fresh tracker would restart innovations and collide with the base.
    tracker = InnovationTracker()
    genome = Genome.new_fully_connected(
        gcfg, NUM_INPUTS, NUM_OUTPUTS, Random(3), tracker
    )
    mutant = genome.clone()
    rng = Random(99)
    mutant.add_node(gcfg, rng, tracker)
    mutant.add_node(gcfg, rng, tracker)
    # Two splits introduce four brand-new (excess) innovations.
    dist = compatibility_distance(genome, mutant, spec)
    assert dist >= spec.c_excess * 4


# --------------------------------------------------------------------------- #
# count_species
# --------------------------------------------------------------------------- #
def test_clones_form_single_species(spec):
    genome = _fresh(4)
    population = [genome.clone() for _ in range(10)]
    assert count_species(population, spec) == 1


def test_divergent_genomes_form_multiple_species(spec, gcfg):
    tracker = InnovationTracker()
    base = Genome.new_fully_connected(gcfg, NUM_INPUTS, NUM_OUTPUTS, Random(5), tracker)
    far = base.clone()
    rng = Random(7)
    for _ in range(5):  # > compatibility_threshold worth of excess genes
        far.add_node(gcfg, rng, tracker)
    assert count_species([base, far], spec) == 2


def test_empty_population_zero_species(spec):
    assert count_species([], spec) == 0


# --------------------------------------------------------------------------- #
# assign_species (backs fitness sharing in Simulation, not just the metrics)
# --------------------------------------------------------------------------- #
def test_assign_species_clones_share_one_id(spec):
    genome = _fresh(4)
    population = [genome.clone() for _ in range(10)]
    assert assign_species(population, spec) == [0] * 10


def test_assign_species_divergent_genomes_get_distinct_ids(spec, gcfg):
    tracker = InnovationTracker()
    base = Genome.new_fully_connected(gcfg, NUM_INPUTS, NUM_OUTPUTS, Random(5), tracker)
    far = base.clone()
    rng = Random(7)
    for _ in range(5):
        far.add_node(gcfg, rng, tracker)
    assert assign_species([base, far], spec) == [0, 1]


def test_assign_species_empty_population():
    assert not assign_species([], SimConfig.from_yaml("config/default.yaml").speciation)


# --------------------------------------------------------------------------- #
# mean_pairwise_distance
# --------------------------------------------------------------------------- #
def test_mean_pairwise_needs_two(spec):
    assert mean_pairwise_distance([], spec) == 0.0
    assert mean_pairwise_distance([_fresh(6)], spec) == 0.0


def test_mean_pairwise_zero_for_clones(spec):
    genome = _fresh(7)
    assert mean_pairwise_distance([genome, genome.clone()], spec) == 0.0


def test_mean_pairwise_positive_when_divergent(spec, gcfg):
    base = _fresh(8)
    mutant = base.clone()
    rng = Random(11)
    tracker = InnovationTracker()
    tracker.bump_node_floor(NUM_INPUTS + NUM_OUTPUTS)
    mutant.add_node(gcfg, rng, tracker)
    assert mean_pairwise_distance([base, mutant], spec) > 0.0
