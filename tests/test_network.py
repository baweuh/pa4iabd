"""Tests for NeuralNetwork."""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import math
import random

import pytest

from src.config import SimConfig
from src.genome import (
    ConnectionGene,
    Genome,
    InnovationTracker,
    NodeGene,
    INPUT,
    HIDDEN,
    OUTPUT,
)
from src.network import NeuralNetwork


@pytest.fixture(name="cfg")
def cfg_fixture():
    return SimConfig.from_yaml("config/default.yaml")


def _small_genome() -> Genome:
    """Hand-crafted genome: inputs 0,1 → hidden 4 → outputs 2,3.

    Node ids deliberately non-contiguous to stress topo-sort.
    """
    nodes = [
        NodeGene(0, INPUT),
        NodeGene(1, INPUT),
        NodeGene(4, HIDDEN),
        NodeGene(2, OUTPUT),
        NodeGene(3, OUTPUT),
    ]
    connections = [
        ConnectionGene(0, 4, weight=0.5, enabled=True, innovation=0),
        ConnectionGene(1, 4, weight=-1.0, enabled=True, innovation=1),
        ConnectionGene(4, 2, weight=2.0, enabled=True, innovation=2),
        ConnectionGene(4, 3, weight=-0.5, enabled=True, innovation=3),
    ]
    return Genome(nodes, connections)


def _cyclic_genome() -> Genome:
    """Enabled cycle: 0→1→2→0."""
    nodes = [NodeGene(0, INPUT), NodeGene(1, HIDDEN), NodeGene(2, OUTPUT)]
    connections = [
        ConnectionGene(0, 1, 0.5, True, 0),
        ConnectionGene(1, 2, 0.5, True, 1),
        ConnectionGene(2, 0, 0.5, True, 2),
    ]
    return Genome(nodes, connections)


# --------------------------------------------------------------------------- #
# Known topology
# --------------------------------------------------------------------------- #
def test_known_topology(cfg):
    g = _small_genome()
    nn = NeuralNetwork(g, cfg.network)

    x0, x1 = 1.0, 0.5
    h = math.tanh(0.5 * x0 + (-1.0) * x1)  # tanh(0.5 - 0.5) = tanh(0) = 0
    expected_vx = 2.0 * h  # linear output
    expected_vy = -0.5 * h
    vx, vy = nn.activate([x0, x1])
    assert vx == pytest.approx(expected_vx)
    assert vy == pytest.approx(expected_vy)


def test_known_topology_nonzero_hidden(cfg):
    g = _small_genome()
    nn = NeuralNetwork(g, cfg.network)

    x0, x1 = 2.0, -1.0
    h = math.tanh(0.5 * x0 + (-1.0) * x1)  # tanh(1 + 1) = tanh(2)
    vx, vy = nn.activate([x0, x1])
    assert vx == pytest.approx(2.0 * h)
    assert vy == pytest.approx(-0.5 * h)


# --------------------------------------------------------------------------- #
# Connection order must not matter
# --------------------------------------------------------------------------- #
def test_output_independent_of_connection_order(cfg):
    g1 = _small_genome()
    g2 = _small_genome()
    g2.connections.reverse()

    nn1 = NeuralNetwork(g1, cfg.network)
    nn2 = NeuralNetwork(g2, cfg.network)

    inputs = [1.0, 0.5]
    assert nn1.activate(inputs) == nn2.activate(inputs)


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_forward_deterministic(cfg):
    tracker = InnovationTracker()
    rng = random.Random(42)
    g = Genome.new_fully_connected(cfg.genome, 33, 2, rng, tracker)

    nn1 = NeuralNetwork(g, cfg.network)
    nn2 = NeuralNetwork(g, cfg.network)

    inputs = [float(i) / 33 for i in range(33)]
    out1a = nn1.activate(inputs)
    out1b = nn1.activate(inputs)
    out2 = nn2.activate(inputs)

    assert out1a == out1b
    assert out1a == out2


# --------------------------------------------------------------------------- #
# Cycle detection
# --------------------------------------------------------------------------- #
def test_cycle_raises(cfg):
    g = _cyclic_genome()
    with pytest.raises(ValueError, match="cycle"):
        NeuralNetwork(g, cfg.network)


# --------------------------------------------------------------------------- #
# Disabled connections
# --------------------------------------------------------------------------- #
def test_disabled_connection_ignored(cfg):
    g_enabled = _small_genome()
    g_disabled = _small_genome()
    # add an extra enabled connection 0→2 in g_enabled, disabled in g_disabled
    g_enabled.connections.append(ConnectionGene(0, 2, 99.0, True, 10))
    g_disabled.connections.append(ConnectionGene(0, 2, 99.0, False, 10))

    nn_e = NeuralNetwork(g_enabled, cfg.network)
    nn_d = NeuralNetwork(g_disabled, cfg.network)

    inputs = [1.0, 0.5]
    assert nn_e.activate(inputs) != nn_d.activate(inputs)

    # Now both disabled: should produce same result as g_disabled
    g_ref = _small_genome()
    nn_ref = NeuralNetwork(g_ref, cfg.network)
    assert nn_d.activate(inputs) == nn_ref.activate(inputs)


# --------------------------------------------------------------------------- #
# Output with no incoming edges = 0.0
# --------------------------------------------------------------------------- #
def test_output_with_no_incoming_is_zero(cfg):
    nodes = [NodeGene(0, INPUT), NodeGene(1, OUTPUT), NodeGene(2, OUTPUT)]
    conns: list[ConnectionGene] = []
    g = Genome(nodes, conns)
    nn = NeuralNetwork(g, cfg.network)
    vx, vy = nn.activate([1.0])
    assert vx == 0.0
    assert vy == 0.0


# --------------------------------------------------------------------------- #
# Input length validation
# --------------------------------------------------------------------------- #
def test_input_length_validation(cfg):
    g = _small_genome()
    nn = NeuralNetwork(g, cfg.network)
    with pytest.raises(ValueError, match="2 inputs"):
        nn.activate([1.0])  # expects 2, got 1


# --------------------------------------------------------------------------- #
# Eval order is cached (invariant n°4)
# --------------------------------------------------------------------------- #
def test_eval_order_cached(cfg):
    g = _small_genome()
    nn = NeuralNetwork(g, cfg.network)
    order_before = nn._eval_order
    nn.activate([1.0, 0.5])
    assert nn._eval_order is order_before  # same object, never replaced


# --------------------------------------------------------------------------- #
# Full network (33 inputs, 2 outputs) smoke test
# --------------------------------------------------------------------------- #
def test_full_network_finite(cfg):
    tracker = InnovationTracker()
    rng = random.Random(99)
    g = Genome.new_fully_connected(cfg.genome, 33, 2, rng, tracker)
    nn = NeuralNetwork(g, cfg.network)

    for _ in range(10):
        inputs = [rng.uniform(-1, 1) for _ in range(33)]
        vx, vy = nn.activate(inputs)
        assert math.isfinite(vx)
        assert math.isfinite(vy)
