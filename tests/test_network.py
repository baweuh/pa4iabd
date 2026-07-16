"""Tests for NeuralNetwork and batch_activate (fixed topology, poc3)."""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import dataclasses
import math
import random

import numpy as np
import pytest

from src.config import SimConfig
from src.genome import Genome, network_layer_shapes
from src.network import NeuralNetwork, batch_activate

NUM_INPUTS = 49
NUM_OUTPUTS = 2
LINEAR_SHAPES = [(NUM_INPUTS, NUM_OUTPUTS)]


@pytest.fixture(name="cfg")
def cfg_fixture():
    return SimConfig.from_yaml("config/default.yaml")


def _hand_crafted_genome() -> Genome:
    """2 inputs -> 1 hidden -> 2 outputs, known weights (exact-value tests)."""
    # Layer 0 (2 -> 1): [[0.5], [-1.0]]. Layer 1 (1 -> 2): [[2.0, -0.5]].
    weights = np.array([0.5, -1.0, 2.0, -0.5], dtype=np.float64)
    return Genome([(2, 1), (1, 2)], weights)


# --------------------------------------------------------------------------- #
# Known topology — exact values
# --------------------------------------------------------------------------- #
def test_known_topology(cfg):
    g = _hand_crafted_genome()
    nn = NeuralNetwork(g, cfg.network)

    x0, x1 = 1.0, 0.5
    h = math.tanh(0.5 * x0 + (-1.0) * x1)  # tanh(0.5 - 0.5) = tanh(0) = 0
    expected_vx = 2.0 * h  # linear output layer
    expected_vy = -0.5 * h
    vx, vy = nn.activate([x0, x1])
    assert vx == pytest.approx(expected_vx)
    assert vy == pytest.approx(expected_vy)


def test_known_topology_nonzero_hidden(cfg):
    g = _hand_crafted_genome()
    nn = NeuralNetwork(g, cfg.network)

    x0, x1 = 2.0, -1.0
    h = math.tanh(0.5 * x0 + (-1.0) * x1)  # tanh(1 + 1) = tanh(2)
    vx, vy = nn.activate([x0, x1])
    assert vx == pytest.approx(2.0 * h)
    assert vy == pytest.approx(-0.5 * h)


def test_zero_weights_give_zero_output(cfg):
    g = Genome(LINEAR_SHAPES, np.zeros(NUM_INPUTS * NUM_OUTPUTS))
    nn = NeuralNetwork(g, cfg.network)
    vx, vy = nn.activate([1.0] * NUM_INPUTS)
    assert vx == 0.0
    assert vy == 0.0


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_forward_deterministic(cfg):
    rng = random.Random(42)
    g = Genome.new_random(cfg.genome, LINEAR_SHAPES, rng)

    nn1 = NeuralNetwork(g, cfg.network)
    nn2 = NeuralNetwork(g, cfg.network)

    inputs = [float(i) / NUM_INPUTS for i in range(NUM_INPUTS)]
    out1a = nn1.activate(inputs)
    out1b = nn1.activate(inputs)
    out2 = nn2.activate(inputs)

    assert out1a == out1b
    assert out1a == out2


# --------------------------------------------------------------------------- #
# Input length validation
# --------------------------------------------------------------------------- #
def test_input_length_validation(cfg):
    g = _hand_crafted_genome()
    nn = NeuralNetwork(g, cfg.network)
    with pytest.raises(ValueError, match="2 inputs"):
        nn.activate([1.0])  # expects 2, got 1


# --------------------------------------------------------------------------- #
# Matrices are built once (invariant n°4)
# --------------------------------------------------------------------------- #
def test_matrices_cached(cfg):
    g = _hand_crafted_genome()
    nn = NeuralNetwork(g, cfg.network)
    matrices_before = nn._matrices  # pylint: disable=protected-access
    nn.activate([1.0, 0.5])
    assert nn._matrices is matrices_before  # pylint: disable=protected-access


# --------------------------------------------------------------------------- #
# Full network smoke test
# --------------------------------------------------------------------------- #
def test_full_network_finite(cfg):
    rng = random.Random(99)
    g = Genome.new_random(cfg.genome, LINEAR_SHAPES, rng)
    nn = NeuralNetwork(g, cfg.network)

    for _ in range(10):
        inputs = [rng.uniform(-1, 1) for _ in range(NUM_INPUTS)]
        vx, vy = nn.activate(inputs)
        assert math.isfinite(vx)
        assert math.isfinite(vy)


# --------------------------------------------------------------------------- #
# batch_activate — the core poc3 correctness guarantee
# --------------------------------------------------------------------------- #
def test_batch_activate_matches_per_agent_loop_linear(cfg):
    """batch_activate must equal calling NeuralNetwork.activate() per genome."""
    rng = random.Random(1)
    pop = 37  # deliberately not a round number
    genomes = [Genome.new_random(cfg.genome, LINEAR_SHAPES, rng) for _ in range(pop)]
    senses = np.array(
        [[rng.uniform(-1, 1) for _ in range(NUM_INPUTS)] for _ in range(pop)]
    )

    batched = batch_activate(genomes, senses, cfg.network)
    looped = np.array(
        [NeuralNetwork(g, cfg.network).activate(row) for g, row in zip(genomes, senses)]
    )
    assert batched.shape == (pop, NUM_OUTPUTS)
    np.testing.assert_allclose(batched, looped, rtol=1e-10, atol=1e-12)


def test_batch_activate_matches_per_agent_loop_with_hidden_layer(cfg):
    hn = dataclasses.replace(cfg.network, hidden_size=8)
    shapes = network_layer_shapes(hn)
    rng = random.Random(2)
    pop = 23
    genomes = [Genome.new_random(cfg.genome, shapes, rng) for _ in range(pop)]
    senses = np.array(
        [[rng.uniform(-1, 1) for _ in range(NUM_INPUTS)] for _ in range(pop)]
    )

    batched = batch_activate(genomes, senses, hn)
    looped = np.array(
        [NeuralNetwork(g, hn).activate(row) for g, row in zip(genomes, senses)]
    )
    np.testing.assert_allclose(batched, looped, rtol=1e-10, atol=1e-12)


def test_batch_activate_empty_population(cfg):
    result = batch_activate([], np.empty((0, NUM_INPUTS)), cfg.network)
    assert result.shape == (0, NUM_OUTPUTS)
