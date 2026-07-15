"""Tests for the HyperNEAT MVP (poc2.5): CPPN -> fixed substrate.

Covers substrate coordinate generation, substrate construction from a CPPN,
and end-to-end wiring through Agent/Simulation — including the regression
guarantee that ``hyperneat.enabled`` absent/false leaves the legacy direct
encoding byte-for-byte in place (invariant: this whole chantier is additive,
never promoted to default.yaml without a validated campaign, see
docs/DESIGN-hyperneat-mvp.md).
"""

# pylint: disable=missing-function-docstring,redefined-outer-name

from __future__ import annotations

import dataclasses
import math
import random

import pytest

from src.agent import Agent
from src.config import SimConfig
from src.diagnostics import steer_score
from src.environment import Environment
from src.genome import INPUT, OUTPUT, TRACKER, Genome
from src.hyperneat import (
    CPPN_NUM_INPUTS,
    CPPN_NUM_OUTPUTS,
    build_substrate_genome,
    build_substrate_network,
    substrate_input_coords,
)
from src.simulation import Simulation


@pytest.fixture(name="cfg")
def cfg_fixture():
    return SimConfig.from_yaml("config/default.yaml")


@pytest.fixture(name="hn_cfg")
def hn_cfg_fixture(cfg):
    """``cfg`` with HyperNEAT switched on, otherwise identical."""
    return dataclasses.replace(
        cfg, hyperneat=dataclasses.replace(cfg.hyperneat, enabled=True)
    )


@pytest.fixture(name="cppn_genome")
def cppn_genome_fixture(cfg):
    TRACKER.reset()
    return Genome.new_fully_connected(
        cfg.genome, CPPN_NUM_INPUTS, CPPN_NUM_OUTPUTS, random.Random(0)
    )


# ------------------------------------------------------------------ #
# Substrate coordinates
# ------------------------------------------------------------------ #


def test_coords_length_matches_num_inputs_legacy_layout(cfg):
    coords = substrate_input_coords(cfg.sensors)
    assert len(coords) == cfg.sensors.num_inputs == 49


def test_coords_length_matches_num_inputs_rich_layout(cfg):
    rich_sensors = dataclasses.replace(
        cfg.sensors, split_distance=True, proprioception=True, apples_in_view=True
    )
    coords = substrate_input_coords(rich_sensors)
    assert len(coords) == rich_sensors.num_inputs == 67


def test_ring_coords_sit_on_unit_circle(cfg):
    coords = substrate_input_coords(cfg.sensors)
    # First block (16 rays) is a ring channel in the legacy (split_distance=false) layout.
    for x, y, _z in coords[: cfg.sensors.num_rays]:
        assert math.hypot(x, y) == pytest.approx(1.0)


def test_scalar_coords_sit_at_origin(cfg):
    coords = substrate_input_coords(cfg.sensors)
    # Legacy layout: last input is the energy scalar (no ray geometry).
    x, y, _z = coords[-1]
    assert (x, y) == (0.0, 0.0)


def test_channel_kinds_get_distinct_z(cfg):
    coords = substrate_input_coords(cfg.sensors)
    # Legacy layout = 3 ring channels (dist/apple_flag/wall_flag) + energy = 4 kinds.
    zs = {coords[i * cfg.sensors.num_rays][2] for i in range(3)} | {coords[-1][2]}
    assert len(zs) == 4


# ------------------------------------------------------------------ #
# Substrate construction from a CPPN
# ------------------------------------------------------------------ #


def test_substrate_genome_shape(cfg, cppn_genome):
    cppn_net = build_substrate_network(  # exercised indirectly below too
        cppn_genome, cfg.sensors, cfg.network, cfg.hyperneat
    )
    num_inputs = cfg.sensors.num_inputs
    assert sorted(cppn_net.input_ids) == list(range(num_inputs))
    assert sorted(cppn_net.output_ids) == [num_inputs, num_inputs + 1]


def test_substrate_genome_is_dense_and_enabled(cfg, cppn_genome):
    from src.network import NeuralNetwork  # local import: build genome directly

    cppn_network = NeuralNetwork(cppn_genome, cfg.network)
    substrate = build_substrate_genome(cppn_network, cfg.sensors, cfg.hyperneat)
    num_inputs = cfg.sensors.num_inputs
    assert len([n for n in substrate.nodes if n.node_type == INPUT]) == num_inputs
    assert len([n for n in substrate.nodes if n.node_type == OUTPUT]) == 2
    assert len(substrate.connections) == num_inputs * 2
    assert all(c.enabled for c in substrate.connections)


def test_substrate_connectivity_one_is_dense_legacy(cfg, cppn_genome):
    """connectivity=1.0 (default) keeps every edge — unchanged from the MVP."""
    from src.network import NeuralNetwork

    cppn_network = NeuralNetwork(cppn_genome, cfg.network)
    substrate = build_substrate_genome(cppn_network, cfg.sensors, cfg.hyperneat)
    num_inputs = cfg.sensors.num_inputs
    assert len(substrate.connections) == num_inputs * 2


def test_substrate_connectivity_below_one_prunes_per_output(cfg, cppn_genome):
    from src.network import NeuralNetwork

    sparse_hn = dataclasses.replace(cfg.hyperneat, connectivity=0.3)
    cppn_network = NeuralNetwork(cppn_genome, cfg.network)
    substrate = build_substrate_genome(cppn_network, cfg.sensors, sparse_hn)
    num_inputs = cfg.sensors.num_inputs
    expected_per_output = max(1, round(0.3 * num_inputs))
    by_output: dict[int, int] = {}
    for c in substrate.connections:
        by_output[c.out_node] = by_output.get(c.out_node, 0) + 1
    assert set(by_output.values()) == {expected_per_output}


def test_substrate_connectivity_keeps_at_least_one_edge_per_output(cfg, cppn_genome):
    """Floor guard: even a near-zero connectivity never silences an output."""
    from src.network import NeuralNetwork

    tiny_hn = dataclasses.replace(cfg.hyperneat, connectivity=0.001)
    cppn_network = NeuralNetwork(cppn_genome, cfg.network)
    substrate = build_substrate_genome(cppn_network, cfg.sensors, tiny_hn)
    num_inputs = cfg.sensors.num_inputs
    by_output: dict[int, int] = {}
    for c in substrate.connections:
        by_output[c.out_node] = by_output.get(c.out_node, 0) + 1
    assert len(by_output) == 2  # neither output silenced
    assert all(n >= 1 for n in by_output.values())


def test_substrate_connectivity_keeps_strongest_weights(cfg, cppn_genome):
    """Pruned edges are the top-|weight| ones, not an arbitrary subset."""
    from src.network import NeuralNetwork

    cppn_network = NeuralNetwork(cppn_genome, cfg.network)
    dense = build_substrate_genome(cppn_network, cfg.sensors, cfg.hyperneat)
    sparse_hn = dataclasses.replace(cfg.hyperneat, connectivity=0.2)
    sparse = build_substrate_genome(cppn_network, cfg.sensors, sparse_hn)

    num_inputs = cfg.sensors.num_inputs
    for out_id in (num_inputs, num_inputs + 1):
        dense_by_weight = sorted(
            (c for c in dense.connections if c.out_node == out_id),
            key=lambda c: abs(c.weight),
            reverse=True,
        )
        k = max(1, round(0.2 * num_inputs))
        expected_ids = {c.in_node for c in dense_by_weight[:k]}
        actual_ids = {c.in_node for c in sparse.connections if c.out_node == out_id}
        assert actual_ids == expected_ids


def test_substrate_weights_bounded_by_weight_scale(cfg, cppn_genome):
    from src.network import NeuralNetwork

    cppn_network = NeuralNetwork(cppn_genome, cfg.network)
    substrate = build_substrate_genome(cppn_network, cfg.sensors, cfg.hyperneat)
    scale = cfg.hyperneat.weight_scale
    assert all(abs(c.weight) <= scale for c in substrate.connections)


def test_substrate_network_activate_returns_two_outputs(cfg, cppn_genome):
    net = build_substrate_network(cppn_genome, cfg.sensors, cfg.network, cfg.hyperneat)
    senses = [0.5] * cfg.sensors.num_inputs
    out = net.activate(senses)
    assert len(out) == 2
    assert all(math.isfinite(v) for v in out)


def test_substrate_network_deterministic(cfg, cppn_genome):
    net_a = build_substrate_network(
        cppn_genome, cfg.sensors, cfg.network, cfg.hyperneat
    )
    net_b = build_substrate_network(
        cppn_genome, cfg.sensors, cfg.network, cfg.hyperneat
    )
    senses = [0.3] * cfg.sensors.num_inputs
    assert net_a.activate(senses) == net_b.activate(senses)


def test_dense_weight_scale_3_is_saturated_founder_diagnostic(cfg):
    """Locks in the FALSIFIED-hyperneat.md root cause as a regression check.

    At the (falsified) MVP default weight_scale=3.0, a majority of random
    CPPN founders produce a substrate whose turn output doesn't vary at all
    with which ray sees the apple (steer_score's near-zero-variance guard
    returns exactly 0.0) — the substrate is saturated, not just weak. If
    this ever stops reproducing, the diagnosis in docs/FALSIFIED-hyperneat.md
    needs revisiting.
    """
    rng = random.Random(0)
    zero_count = 0
    for _ in range(30):
        TRACKER.reset()
        cppn = Genome.new_fully_connected(
            cfg.genome, CPPN_NUM_INPUTS, CPPN_NUM_OUTPUTS, rng
        )
        net = build_substrate_network(cppn, cfg.sensors, cfg.network, cfg.hyperneat)
        if steer_score(net, cfg.sensors) == 0.0:
            zero_count += 1
    assert zero_count >= 15  # majority saturated at weight_scale=3.0 (default)


def test_lower_weight_scale_fixes_founder_saturation(cfg):
    """The V2 diagnosis: weight_scale, not density, drives the saturation.

    Same founders, only ``weight_scale`` lowered (0.5 instead of the
    default 3.0, ``connectivity`` left dense at 1.0) — zero saturated
    founders, matching the sweep behind ``config/lever_hyperneat_v2.yaml``.
    """
    low_scale_hn = dataclasses.replace(cfg.hyperneat, weight_scale=0.5)
    rng = random.Random(0)
    for _ in range(30):
        TRACKER.reset()
        cppn = Genome.new_fully_connected(
            cfg.genome, CPPN_NUM_INPUTS, CPPN_NUM_OUTPUTS, rng
        )
        net = build_substrate_network(cppn, cfg.sensors, cfg.network, low_scale_hn)
        assert steer_score(net, cfg.sensors) != 0.0


# ------------------------------------------------------------------ #
# End-to-end: Simulation / Agent wiring
# ------------------------------------------------------------------ #


def test_legacy_founder_genome_shape_unaffected(cfg):
    """hyperneat absent (default.yaml) -> founders keep the direct 49->2 shape."""
    assert cfg.hyperneat.enabled is False
    sim = Simulation(cfg, random.Random(1))
    genome = sim.population[0].genome
    assert len(genome.nodes) == cfg.sensors.num_inputs + 2
    assert len(genome.connections) == cfg.sensors.num_inputs * 2


def test_hyperneat_founder_genome_is_cppn_shape(hn_cfg):
    sim = Simulation(hn_cfg, random.Random(1))
    genome = sim.population[0].genome
    assert len(genome.nodes) == CPPN_NUM_INPUTS + CPPN_NUM_OUTPUTS
    assert len(genome.connections) == CPPN_NUM_INPUTS * CPPN_NUM_OUTPUTS


def test_hyperneat_agent_network_is_substrate_shaped(hn_cfg):
    env = Environment(hn_cfg, random.Random(1))
    TRACKER.reset()
    cppn_genome = Genome.new_fully_connected(
        hn_cfg.genome, CPPN_NUM_INPUTS, CPPN_NUM_OUTPUTS, random.Random(0)
    )
    agent = Agent(cppn_genome, (100.0, 100.0), hn_cfg, env, random.Random(2))
    assert sorted(agent.network.input_ids) == list(range(hn_cfg.sensors.num_inputs))
    assert sorted(agent.network.output_ids) == [
        hn_cfg.sensors.num_inputs,
        hn_cfg.sensors.num_inputs + 1,
    ]


def test_hyperneat_agent_decide_runs(hn_cfg):
    env = Environment(hn_cfg, random.Random(1))
    TRACKER.reset()
    cppn_genome = Genome.new_fully_connected(
        hn_cfg.genome, CPPN_NUM_INPUTS, CPPN_NUM_OUTPUTS, random.Random(0)
    )
    agent = Agent(cppn_genome, (100.0, 100.0), hn_cfg, env, random.Random(2))
    vx, vy = agent.decide(agent.sense())
    assert math.isfinite(vx) and math.isfinite(vy)


def test_hyperneat_simulation_runs_without_crash(hn_cfg):
    small_cfg = dataclasses.replace(
        hn_cfg,
        population=dataclasses.replace(hn_cfg.population, initial_size=10, max_size=15),
    )
    sim = Simulation(small_cfg, random.Random(3))
    for _ in range(200):
        sim.tick()
    assert sim.tick_count == 200
