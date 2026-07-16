"""Tests for the fixed-topology genome (poc3) and its operators."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

from random import Random

import numpy as np
import pytest

from src.config import SimConfig
from src.genome import Genome, network_layer_shapes

NUM_INPUTS = 49
NUM_OUTPUTS = 2
LINEAR_SHAPES = [(NUM_INPUTS, NUM_OUTPUTS)]
HIDDEN_SHAPES = [(NUM_INPUTS, 8), (8, NUM_OUTPUTS)]


@pytest.fixture(name="config")
def config_fixture():
    return SimConfig.from_yaml("config/default.yaml").genome


@pytest.fixture(name="net_config")
def net_config_fixture():
    return SimConfig.from_yaml("config/default.yaml").network


# --------------------------------------------------------------------------- #
# Shape derivation
# --------------------------------------------------------------------------- #
def test_network_layer_shapes_zero_hidden_is_single_linear_layer(net_config):
    assert network_layer_shapes(net_config) == [(NUM_INPUTS, NUM_OUTPUTS)]


def test_network_layer_shapes_positive_hidden_is_two_layers(net_config):
    import dataclasses

    hn = dataclasses.replace(net_config, hidden_size=8)
    assert network_layer_shapes(hn) == [(NUM_INPUTS, 8), (8, NUM_OUTPUTS)]


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #
def test_new_random_shape_linear(config):
    rng = Random(1)
    g = Genome.new_random(config, LINEAR_SHAPES, rng)
    assert g.layer_shapes == LINEAR_SHAPES
    assert g.weights.shape == (NUM_INPUTS * NUM_OUTPUTS,)


def test_new_random_shape_with_hidden_layer(config):
    rng = Random(1)
    g = Genome.new_random(config, HIDDEN_SHAPES, rng)
    assert g.layer_shapes == HIDDEN_SHAPES
    expected = NUM_INPUTS * 8 + 8 * NUM_OUTPUTS
    assert g.weights.shape == (expected,)


def test_new_random_weights_within_init_range(config):
    rng = Random(7)
    g = Genome.new_random(config, LINEAR_SHAPES, rng)
    assert np.all(np.abs(g.weights) <= config.weight_init_range)


def test_new_random_is_deterministic_with_seed(config):
    a = Genome.new_random(config, LINEAR_SHAPES, Random(42))
    b = Genome.new_random(config, LINEAR_SHAPES, Random(42))
    assert np.array_equal(a.weights, b.weights)


def test_matrices_reshape_matches_layer_shapes(config):
    rng = Random(2)
    g = Genome.new_random(config, HIDDEN_SHAPES, rng)
    matrices = g.matrices()
    assert [m.shape for m in matrices] == HIDDEN_SHAPES
    # Round-trips back to the exact same flat vector.
    assert np.array_equal(np.concatenate([m.ravel() for m in matrices]), g.weights)


def test_clone_is_independent(config):
    rng = Random(2)
    g = Genome.new_random(config, LINEAR_SHAPES, rng)
    clone = g.clone()
    clone.weights[0] += 100.0
    assert g.weights[0] != clone.weights[0]
    assert g.layer_shapes == clone.layer_shapes


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #
def test_json_round_trip(config):
    rng = Random(3)
    g = Genome.new_random(config, LINEAR_SHAPES, rng)
    restored = Genome.from_json(g.to_json())
    assert restored.layer_shapes == g.layer_shapes
    assert np.array_equal(restored.weights, g.weights)


def test_json_round_trip_with_hidden_layer(config):
    rng = Random(4)
    g = Genome.new_random(config, HIDDEN_SHAPES, rng)
    restored = Genome.from_json(g.to_json())
    assert restored.layer_shapes == g.layer_shapes
    assert np.array_equal(restored.weights, g.weights)


# --------------------------------------------------------------------------- #
# Mutation
# --------------------------------------------------------------------------- #
def test_mutate_changes_weights(config):
    rng = Random(4)
    g = Genome.new_random(config, LINEAR_SHAPES, rng)
    before = g.weights.copy()
    g.mutate(config, rng)
    assert not np.array_equal(before, g.weights)


def test_mutate_is_deterministic_with_seed(config):
    def build_and_mutate() -> np.ndarray:
        rng = Random(123)
        g = Genome.new_random(config, LINEAR_SHAPES, rng)
        for _ in range(10):
            g.mutate(config, rng)
        return g.weights

    assert np.array_equal(build_and_mutate(), build_and_mutate())


def test_mutate_clamps_to_weight_max(config):
    rng = Random(99)
    g = Genome.new_random(config, LINEAR_SHAPES, rng)
    g.weights[:] = 100.0  # force weights far outside the clamp range
    for _ in range(50):
        g.mutate(config, rng)
    assert np.all(np.abs(g.weights) <= config.weight_max)


# --------------------------------------------------------------------------- #
# Crossover
# --------------------------------------------------------------------------- #
def _diverged_pair(config):
    """Two genomes sharing an ancestor but grown apart via independent mutation."""
    rng = Random(7)
    base = Genome.new_random(config, LINEAR_SHAPES, rng)
    a, b = base.clone(), base.clone()
    for _ in range(40):
        a.mutate(config, rng)
        b.mutate(config, rng)
    return a, b


def test_crossover_preserves_shape(config):
    a, b = _diverged_pair(config)
    child = Genome.crossover(a, b, Random(0))
    assert child.layer_shapes == a.layer_shapes
    assert child.weights.shape == a.weights.shape


def test_crossover_each_weight_from_either_parent(config):
    a, b = _diverged_pair(config)
    child = Genome.crossover(a, b, Random(1))
    from_a = np.isclose(child.weights, a.weights)
    from_b = np.isclose(child.weights, b.weights)
    assert np.all(from_a | from_b)


def test_crossover_identical_parents_preserves_weights(config):
    rng = Random(5)
    g = Genome.new_random(config, LINEAR_SHAPES, rng)
    for _ in range(20):
        g.mutate(config, rng)
    child = Genome.crossover(g, g.clone(), Random(6))
    assert np.array_equal(child.weights, g.weights)


def test_crossover_child_builds_valid_network(config):
    """A crossover child must yield a working NeuralNetwork."""
    from src.network import NeuralNetwork  # local: avoid a module-level cycle

    net_cfg = SimConfig.from_yaml("config/default.yaml")
    a, b = _diverged_pair(net_cfg.genome)
    child = Genome.crossover(a, b, Random(3))
    net = NeuralNetwork(child, net_cfg.network)
    out = net.activate([0.5] * NUM_INPUTS)
    assert len(out) == NUM_OUTPUTS
