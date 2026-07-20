"""Tests for NeuralNetwork."""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import math
import random

import pytest

from src.config import HebbianConfig, SimConfig
from src.genome import (
    ConnectionGene,
    Genome,
    InnovationTracker,
    NodeGene,
    BIAS,
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
# Bias node
# --------------------------------------------------------------------------- #
def test_bias_activates_with_zero_inputs(cfg):
    """A bias-only output (no sensory input wired) still fires from the constant."""
    nodes = [
        NodeGene(0, INPUT),
        NodeGene(1, OUTPUT),
        NodeGene(2, OUTPUT),
        NodeGene(3, BIAS),
    ]
    conns = [ConnectionGene(3, 1, weight=3.0, enabled=True, innovation=0)]
    nn = NeuralNetwork(Genome(nodes, conns), cfg.network)
    vx, vy = nn.activate([0.0])
    assert vx == pytest.approx(3.0)  # 1.0 (bias) * 3.0, input never touched
    assert vy == pytest.approx(0.0)  # unwired output, no bias connection


def test_bias_not_counted_as_sensory_input(cfg):
    """Bias doesn't grow input_ids — the sensor vector length is unaffected."""
    nodes = [
        NodeGene(0, INPUT),
        NodeGene(1, OUTPUT),
        NodeGene(2, OUTPUT),
        NodeGene(3, BIAS),
    ]
    conns = [ConnectionGene(3, 1, weight=1.0, enabled=True, innovation=0)]
    nn = NeuralNetwork(Genome(nodes, conns), cfg.network)
    assert nn.input_ids == [0]
    nn.activate([0.0])  # would raise ValueError if bias were expected here too


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


# --------------------------------------------------------------------------- #
# Reward-modulated Hebbian plasticity (poc2.6)
# --------------------------------------------------------------------------- #


def _plastic(**kwargs) -> HebbianConfig:
    return HebbianConfig(enabled=True, **kwargs)


def _weights(net: NeuralNetwork) -> dict[int, list[tuple[int, float]]]:
    return {nid: list(srcs) for nid, srcs in net._incoming.items()}


def test_hebbian_off_by_default(cfg):
    assert cfg.hebbian.enabled is False
    net = NeuralNetwork(_small_genome(), cfg.network, cfg.hebbian)
    before = _weights(net)
    net.activate([1.0, 1.0])
    net.apply_hebbian(1.0)
    assert _weights(net) == before


def test_hebbian_no_config_behaves_like_disabled(cfg):
    net = NeuralNetwork(_small_genome(), cfg.network)
    before = _weights(net)
    net.activate([1.0, 1.0])
    net.apply_hebbian(3.0)
    assert _weights(net) == before


def test_no_update_when_reward_matches_baseline(cfg):
    """V2 is contrastive: an outcome equal to the expectation moves nothing.

    (V1 was reward-GATED — no update unless an apple was eaten. V2 replaces
    that with a contrast, so this holds for reward == baseline, not reward == 0.)
    """
    net = NeuralNetwork(_small_genome(), cfg.network, _plastic())
    net.activate([1.0, 1.0])
    net._reward_baseline = 0.7
    before = _weights(net)
    net.apply_hebbian(0.7)
    assert _weights(net) == before


def test_hebbian_before_first_activate_is_noop(cfg):
    net = NeuralNetwork(_small_genome(), cfg.network, _plastic())
    before = _weights(net)
    net.apply_hebbian(1.0)
    assert _weights(net) == before


def test_activate_alone_never_changes_weights(cfg):
    """Measuring an agent must not modify its brain.

    steer_score, the novelty descriptor and the HyperNEAT CPPN queries all call
    activate() purely to observe. Only apply_hebbian may move a weight.
    """
    net = NeuralNetwork(_small_genome(), cfg.network, _plastic())
    before = _weights(net)
    for _ in range(50):
        net.activate([1.0, -1.0])
    assert _weights(net) == before


def test_hebbian_update_matches_the_rule(cfg):
    """On the FIRST update (empty trace, zero baseline) V2 reduces to V1."""
    lr = 0.1
    net = NeuralNetwork(_small_genome(), cfg.network, _plastic(learning_rate=lr))
    net.activate([1.0, 1.0])
    values = dict(net._last_values)
    before = _weights(net)
    reward = 2.0
    net.apply_hebbian(reward)
    after = _weights(net)
    for nid, srcs in after.items():
        for pos, (src, w) in enumerate(srcs):
            post = values[nid]
            if net._node_type[nid] == OUTPUT:
                post = math.tanh(post)  # emitted value, not the raw linear sum
            expected = before[nid][pos][1] + lr * reward * values[src] * post
            assert w == pytest.approx(expected)


def test_hebbian_clamps_to_weight_max(cfg):
    net = NeuralNetwork(
        _small_genome(), cfg.network, _plastic(learning_rate=10.0, weight_max=1.5)
    )
    for _ in range(200):
        net.activate([1.0, 1.0])
        net.apply_hebbian(5.0)
    for srcs in net._incoming.values():
        for _, w in srcs:
            assert -1.5 <= w <= 1.5


def test_hebbian_does_not_touch_the_genome(cfg):
    """Learning is non-Lamarckian: children inherit the innate wiring."""
    genome = _small_genome()
    innate = [(c.in_node, c.out_node, c.weight) for c in genome.connections]
    net = NeuralNetwork(genome, cfg.network, _plastic(learning_rate=0.5))
    for _ in range(20):
        net.activate([1.0, 1.0])
        net.apply_hebbian(1.0)
    assert [(c.in_node, c.out_node, c.weight) for c in genome.connections] == innate
    assert _weights(net) != {
        nid: list(srcs)
        for nid, srcs in NeuralNetwork(genome, cfg.network)._incoming.items()
    }


def test_hebbian_changes_the_output(cfg):
    """The whole point: the same input maps to a different action after learning."""
    net = NeuralNetwork(_small_genome(), cfg.network, _plastic(learning_rate=0.2))
    before = net.activate([1.0, 1.0])
    for _ in range(10):
        net.activate([1.0, 1.0])
        net.apply_hebbian(1.0)
    assert net.activate([1.0, 1.0]) != before


# --------------------------------------------------------------------------- #
# V2 — eligibility trace + reward baseline (the two V1 defects)
# --------------------------------------------------------------------------- #


def test_trace_carries_credit_from_earlier_ticks(cfg):
    """Defect 1: V1 could only reinforce the capture tick.

    Here the rewarded tick is SILENT (all-zero input, so x*y == 0 for the input
    layer): any weight change on those connections can only come from activity
    banked on earlier ticks.
    """
    net = NeuralNetwork(
        _small_genome(), cfg.network, _plastic(learning_rate=0.1, eligibility_decay=0.9)
    )
    for _ in range(10):
        net.activate([1.0, 1.0])
        net.apply_hebbian(0.0)
    before = _weights(net)
    net.activate([0.0, 0.0])  # silent tick
    net.apply_hebbian(5.0)  # ...but rewarded
    assert _weights(net) != before


def test_zero_decay_ablates_the_trace(cfg):
    """eligibility_decay = 0 reduces the trace to the current tick (V1)."""
    net = NeuralNetwork(
        _small_genome(), cfg.network, _plastic(learning_rate=0.1, eligibility_decay=0.0)
    )
    for _ in range(10):
        net.activate([1.0, 1.0])
        net.apply_hebbian(0.0)
    before = _weights(net)
    net.activate([0.0, 0.0])
    net.apply_hebbian(5.0)
    assert _weights(net) == before  # nothing banked, silent tick moves nothing


def test_trace_decays(cfg):
    net = NeuralNetwork(_small_genome(), cfg.network, _plastic(eligibility_decay=0.5))
    net.activate([1.0, 1.0])
    net.apply_hebbian(0.0)
    peak = max(abs(e) for tr in net._trace.values() for e in tr)
    for _ in range(10):
        net.activate([0.0, 0.0])
        net.apply_hebbian(0.0)
    assert max(abs(e) for tr in net._trace.values() for e in tr) < peak / 10


def test_baseline_tracks_reward(cfg):
    net = NeuralNetwork(_small_genome(), cfg.network, _plastic(baseline_rate=0.5))
    assert net._reward_baseline == 0.0
    for _ in range(20):
        net.activate([1.0, 1.0])
        net.apply_hebbian(1.0)
    assert net._reward_baseline == pytest.approx(1.0, abs=1e-3)


def test_zero_baseline_rate_ablates_the_baseline(cfg):
    net = NeuralNetwork(_small_genome(), cfg.network, _plastic(baseline_rate=0.0))
    for _ in range(20):
        net.activate([1.0, 1.0])
        net.apply_hebbian(1.0)
    assert net._reward_baseline == 0.0


def test_dry_tick_reverses_the_update_once_baseline_is_positive(cfg):
    """Defect 2: V1 could only ever push weights up.

    With a baseline, a tick that produces nothing carries a NEGATIVE contrast,
    so it walks a weight back down.
    """
    net = NeuralNetwork(
        _small_genome(), cfg.network, _plastic(learning_rate=0.1, baseline_rate=0.5)
    )
    for _ in range(20):
        net.activate([1.0, 1.0])
        net.apply_hebbian(1.0)
    assert net._reward_baseline > 0.5
    rewarded = _weights(net)
    net.activate([1.0, 1.0])
    net.apply_hebbian(0.0)  # dry tick
    after = _weights(net)
    moved = [
        (after[nid][pos][1] - rewarded[nid][pos][1])
        for nid, srcs in rewarded.items()
        for pos in range(len(srcs))
    ]
    assert any(d != 0.0 for d in moved)
    # Every connection whose trace is positive must have been pushed DOWN.
    for nid, tr in net._trace.items():
        for pos, e in enumerate(tr):
            if e > 1e-9:
                assert after[nid][pos][1] < rewarded[nid][pos][1]


def test_baseline_keeps_lifetime_drift_bounded(cfg):
    """The point of the baseline: no runaway positive drift over a life.

    V1's failure mode was weights ratcheting up until the tanh saturated. Fed a
    realistic sparse reward stream (~3 apples per 2000 ticks), V2's net drift
    must stay small — much smaller than the same stream with the baseline off.
    """

    def drift(baseline_rate: float) -> float:
        net = NeuralNetwork(
            _small_genome(),
            cfg.network,
            _plastic(learning_rate=0.1, baseline_rate=baseline_rate),
        )
        start = _weights(net)
        rng = random.Random(0)
        for tick in range(2000):
            net.activate([rng.uniform(0.0, 1.0), rng.uniform(0.0, 1.0)])
            net.apply_hebbian(1.0 if tick % 666 == 0 else 0.0)
        end = _weights(net)
        return max(
            abs(end[nid][pos][1] - start[nid][pos][1])
            for nid, srcs in start.items()
            for pos in range(len(srcs))
        )

    assert drift(0.01) < drift(0.0) / 2
