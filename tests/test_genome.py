"""Tests for the genome data structure and mutation operators."""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import dataclasses
from random import Random

import pytest

from src.config import SimConfig
from src.genome import (
    BIAS,
    HIDDEN,
    INPUT,
    OUTPUT,
    ConnectionGene,
    Genome,
    InnovationTracker,
    NodeGene,
)

NUM_INPUTS = 49
NUM_OUTPUTS = 2


@pytest.fixture(name="config")
def config_fixture():
    return SimConfig.from_yaml("config/default.yaml").genome


@pytest.fixture(name="tracker")
def tracker_fixture():
    return InnovationTracker()


def _has_cycle(genome: Genome) -> bool:
    """Independent cycle detector over enabled connections (DFS, 3-colour)."""
    adjacency: dict[int, list[int]] = {}
    for conn in genome.connections:
        if conn.enabled:
            adjacency.setdefault(conn.in_node, []).append(conn.out_node)
    visiting, done = set(), set()

    def visit(node: int) -> bool:
        if node in visiting:
            return True
        if node in done:
            return False
        visiting.add(node)
        for nxt in adjacency.get(node, ()):
            if visit(nxt):
                return True
        visiting.discard(node)
        done.add(node)
        return False

    return any(visit(n.node_id) for n in genome.nodes)


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #
def test_new_fully_connected_shape(config, tracker):
    rng = Random(1)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    inputs = [n for n in g.nodes if n.node_type == INPUT]
    outputs = [n for n in g.nodes if n.node_type == OUTPUT]
    assert len(inputs) == NUM_INPUTS
    assert len(outputs) == NUM_OUTPUTS
    assert len(g.connections) == NUM_INPUTS * NUM_OUTPUTS
    assert all(c.enabled for c in g.connections)
    assert not _has_cycle(g)


def test_full_connectivity_preserves_original_weight_draw_order(config, tracker):
    """Connections must be drawn in (input outer, output inner) order.

    Regression guard for the initial_connectivity refactor (audit poc2.3
    volet 6): reordering the loops would silently change which RNG draw
    lands on which edge, breaking reproducibility for every existing seed
    even though initial_connectivity defaults to 1.0 (legacy behaviour).
    """
    rng = Random(7)
    g = Genome.new_fully_connected(config, 3, 2, rng, tracker)
    expected_pairs = [(i, 3 + j) for i in range(3) for j in range(2)]
    assert [(c.in_node, c.out_node) for c in g.connections] == expected_pairs


def test_sparse_initial_connectivity_reduces_connection_count(config, tracker):
    sparse = dataclasses.replace(config, initial_connectivity=0.1)
    rng = Random(1)
    g = Genome.new_fully_connected(sparse, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    expected_per_output = max(1, round(0.1 * NUM_INPUTS))
    assert len(g.connections) == expected_per_output * NUM_OUTPUTS
    assert len(g.connections) < NUM_INPUTS * NUM_OUTPUTS
    assert not _has_cycle(g)


def test_sparse_initial_connectivity_never_leaves_an_output_silent(config, tracker):
    # Even at the extreme low end, every output gets >= 1 input connection.
    sparse = dataclasses.replace(config, initial_connectivity=0.001)
    rng = Random(3)
    g = Genome.new_fully_connected(sparse, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    output_ids = {n.node_id for n in g.nodes if n.node_type == OUTPUT}
    wired_outputs = {c.out_node for c in g.connections}
    assert wired_outputs == output_ids


def test_bias_disabled_by_default_no_bias_node(config, tracker):
    rng = Random(1)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    assert not any(n.node_type == BIAS for n in g.nodes)
    assert len(g.connections) == NUM_INPUTS * NUM_OUTPUTS


def test_bias_enabled_adds_bias_node_wired_to_every_output(config, tracker):
    with_bias = dataclasses.replace(config, bias_enabled=True)
    rng = Random(1)
    g = Genome.new_fully_connected(with_bias, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    bias_nodes = [n for n in g.nodes if n.node_type == BIAS]
    assert len(bias_nodes) == 1
    bias_id = bias_nodes[0].node_id
    assert bias_id == NUM_INPUTS + NUM_OUTPUTS  # id right after the outputs
    # connectivity=1.0 (default) -> bias wired to every output, like an input.
    assert len(g.connections) == (NUM_INPUTS + 1) * NUM_OUTPUTS
    output_ids = {n.node_id for n in g.nodes if n.node_type == OUTPUT}
    bias_targets = {c.out_node for c in g.connections if c.in_node == bias_id}
    assert bias_targets == output_ids
    assert not _has_cycle(g)


def test_add_connection_never_targets_bias(config, tracker):
    """Mutation must never wire an edge INTO the bias node (it's a constant)."""
    with_bias = dataclasses.replace(config, bias_enabled=True)
    rng = Random(1)
    g = Genome.new_fully_connected(with_bias, 3, 2, rng, tracker)
    bias_id = next(n.node_id for n in g.nodes if n.node_type == BIAS)
    for _ in range(200):
        g.add_connection(with_bias, rng, tracker)
        g.add_node(with_bias, rng, tracker)
    assert all(c.out_node != bias_id for c in g.connections)


def test_remove_node_never_removes_bias(config, tracker):
    with_bias = dataclasses.replace(config, bias_enabled=True)
    rng = Random(1)
    g = Genome.new_fully_connected(with_bias, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    for _ in range(50):
        g.remove_node(rng)
    assert any(n.node_type == BIAS for n in g.nodes)


def test_node_ids_are_unique(config, tracker):
    rng = Random(1)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    ids = [n.node_id for n in g.nodes]
    assert len(ids) == len(set(ids))
    # Output ids follow input ids.
    assert {n.node_id for n in g.nodes if n.node_type == OUTPUT} == {49, 50}


def test_weights_within_init_range(config, tracker):
    rng = Random(7)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    assert all(
        -config.weight_init_range <= c.weight <= config.weight_init_range
        for c in g.connections
    )


def test_clone_is_independent(config, tracker):
    rng = Random(2)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    clone = g.clone()
    clone.connections[0].weight += 100.0
    clone.nodes.append(NodeGene(999, HIDDEN))
    assert g.connections[0].weight != clone.connections[0].weight
    assert len(g.nodes) != len(clone.nodes)


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #
def test_json_round_trip(config, tracker):
    rng = Random(3)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    restored = Genome.from_json(g.to_json())
    assert restored.to_dict() == g.to_dict()


# --------------------------------------------------------------------------- #
# Innovation tracker
# --------------------------------------------------------------------------- #
def test_innovation_same_edge_same_number(tracker):
    first = tracker.innovation_for(0, 33)
    again = tracker.innovation_for(0, 33)
    other = tracker.innovation_for(1, 33)
    assert first == again
    assert other != first


def test_tracker_node_floor(tracker):
    tracker.bump_node_floor(35)
    assert tracker.next_node_id() == 35
    assert tracker.next_node_id() == 36


def test_tracker_reset(tracker):
    tracker.next_node_id()
    tracker.innovation_for(0, 1)
    tracker.reset()
    assert tracker.next_node_id() == 0
    assert tracker.innovation_for(5, 6) == 0


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #
def test_mutate_weights_changes_weights(config, tracker):
    rng = Random(4)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    before = [c.weight for c in g.connections]
    g.mutate_weights(config, rng)
    after = [c.weight for c in g.connections]
    assert before != after


def test_add_node_splits_connection(config, tracker):
    rng = Random(5)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    n_nodes, n_conns = len(g.nodes), len(g.connections)
    assert g.add_node(config, rng, tracker) is True
    assert len(g.nodes) == n_nodes + 1
    assert len(g.connections) == n_conns + 2
    assert sum(1 for n in g.nodes if n.node_type == HIDDEN) == 1
    assert sum(1 for c in g.connections if not c.enabled) == 1
    assert not _has_cycle(g)


def test_add_connection_no_duplicates_or_cycles(config, tracker):
    rng = Random(6)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    # Add a hidden node so add_connection has valid targets/sources.
    g.add_node(config, rng, tracker)
    for _ in range(200):
        g.add_connection(config, rng, tracker)
    assert not _has_cycle(g)
    seen = {(c.in_node, c.out_node) for c in g.connections}
    assert len(seen) == len(g.connections)


def test_creates_cycle_detection():
    # Chain 0 -> 1 -> 2. Adding 2 -> 0 must be detected as a cycle.
    nodes = [NodeGene(0, INPUT), NodeGene(1, HIDDEN), NodeGene(2, OUTPUT)]
    conns = [
        ConnectionGene(0, 1, 0.5, True, 0),
        ConnectionGene(1, 2, 0.5, True, 1),
    ]
    g = Genome(nodes, conns)
    assert g._creates_cycle(2, 0) is True
    assert g._creates_cycle(0, 2) is False


def test_remove_connection(config, tracker):
    rng = Random(8)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    n = len(g.connections)
    assert g.remove_connection(rng) is True
    assert len(g.connections) == n - 1


def test_remove_node_removes_incident_edges(config, tracker):
    rng = Random(9)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    g.add_node(config, rng, tracker)
    hidden_id = next(n.node_id for n in g.nodes if n.node_type == HIDDEN)
    assert g.remove_node(rng) is True
    assert all(n.node_type != HIDDEN for n in g.nodes)
    assert not any(hidden_id in (c.in_node, c.out_node) for c in g.connections)


def test_remove_node_no_hidden_returns_false(config, tracker):
    rng = Random(10)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    assert g.remove_node(rng) is False


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_mutation_is_deterministic_with_seed(config):
    def build_and_mutate() -> dict:
        tracker = InnovationTracker()
        rng = Random(123)
        g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
        for _ in range(10):
            g.mutate(config, rng, tracker)
        return g.to_dict()

    assert build_and_mutate() == build_and_mutate()


def test_weights_clamped_after_mutation(config):
    tracker = InnovationTracker()
    rng = Random(99)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    # Force weights far outside the clamp range then mutate.
    for conn in g.connections:
        conn.weight = 100.0
    for _ in range(50):
        g.mutate_weights(config, rng)
    assert all(abs(c.weight) <= config.weight_max for c in g.connections)


# --------------------------------------------------------------------------- #
# Crossover (Lever C)
# --------------------------------------------------------------------------- #
def _diverged_pair(config):
    """Two genomes sharing an ancestor but grown apart via independent mutation."""
    tracker = InnovationTracker()
    rng = Random(7)
    base = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    a, b = base.clone(), base.clone()
    for _ in range(40):
        a.mutate(config, rng, tracker)
        b.mutate(config, rng, tracker)
    return a, b


def test_crossover_child_is_feedforward(config):
    a, b = _diverged_pair(config)
    rng = Random(0)
    for _ in range(30):
        child = Genome.crossover(a, b, rng)
        assert not _has_cycle(
            child
        ), "crossover must preserve the feedforward invariant"


def test_crossover_keeps_all_io_nodes(config):
    a, b = _diverged_pair(config)
    child = Genome.crossover(a, b, Random(1))
    inputs = [n for n in child.nodes if n.node_type == INPUT]
    outputs = [n for n in child.nodes if n.node_type == OUTPUT]
    assert len(inputs) == NUM_INPUTS
    assert len(outputs) == NUM_OUTPUTS


def test_crossover_keeps_bias_node(config):
    with_bias = dataclasses.replace(config, bias_enabled=True)
    a, b = _diverged_pair(with_bias)
    child = Genome.crossover(a, b, Random(1))
    assert sum(1 for n in child.nodes if n.node_type == BIAS) == 1


def test_crossover_inherits_only_parent_genes(config):
    a, b = _diverged_pair(config)
    parent_innovations = {c.innovation for c in a.connections} | {
        c.innovation for c in b.connections
    }
    child = Genome.crossover(a, b, Random(2))
    child_innovations = {c.innovation for c in child.connections}
    assert child_innovations <= parent_innovations
    # Every connection endpoint must have a matching node gene.
    node_ids = {n.node_id for n in child.nodes}
    for conn in child.connections:
        assert conn.in_node in node_ids
        assert conn.out_node in node_ids


def test_crossover_child_builds_valid_network(config):
    """A crossover child must yield a working NeuralNetwork (topo sort succeeds)."""
    from src.config import SimConfig  # local: reuse the full config for network dims
    from src.network import NeuralNetwork

    net_cfg = SimConfig.from_yaml("config/default.yaml")
    tracker = InnovationTracker()
    rng = Random(3)
    ni, no = net_cfg.network.num_inputs, net_cfg.network.num_outputs
    base = Genome.new_fully_connected(net_cfg.genome, ni, no, rng, tracker)
    a, b = base.clone(), base.clone()
    for _ in range(40):
        a.mutate(net_cfg.genome, rng, tracker)
        b.mutate(net_cfg.genome, rng, tracker)
    child = Genome.crossover(a, b, rng)
    net = NeuralNetwork(child, net_cfg.network)
    out = net.activate([0.5] * ni)
    assert len(out) == no


def test_crossover_identical_parents_preserves_structure(config):
    tracker = InnovationTracker()
    rng = Random(5)
    g = Genome.new_fully_connected(config, NUM_INPUTS, NUM_OUTPUTS, rng, tracker)
    for _ in range(20):
        g.mutate(config, rng, tracker)
    child = Genome.crossover(g, g.clone(), Random(6))
    # Same innovations in, same innovations out (matching-gene path only).
    assert {c.innovation for c in child.connections} == {
        c.innovation for c in g.connections
    }
    assert all(abs(c.weight) <= config.weight_max for c in g.connections)
