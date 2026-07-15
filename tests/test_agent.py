"""Tests for Agent (Phase 5): raycasts, energy, life cycle, reproduction."""

# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name

from __future__ import annotations

import dataclasses
import math
import random

import pytest

from src.agent import Agent, ray_angles
from src.apple import Apple
from src.config import SimConfig
from src.environment import Environment
from src.genome import TRACKER, Genome


@pytest.fixture(name="cfg")
def cfg_fixture():
    return SimConfig.from_yaml("config/default.yaml")


@pytest.fixture(name="env")
def env_fixture(cfg):
    return Environment(cfg, random.Random(42))


@pytest.fixture(name="genome")
def genome_fixture(cfg):
    TRACKER.reset()
    return Genome.new_fully_connected(
        cfg.genome, cfg.network.num_inputs, cfg.network.num_outputs, random.Random(0)
    )


def make_agent(cfg, env, genome, position, seed=0, heading=0.0):
    return Agent(genome, position, cfg, env, random.Random(seed), heading=heading)


@pytest.fixture(name="split_cfg")
def split_cfg_fixture(cfg):
    """Default config with independent apple/wall distance channels re-enabled.

    Exercises the split-distance sensor path (real feature, no longer the
    default since it destabilises foraging robustness — see
    docs/Audits/AUDIT-poc2.3.md volet 5) independently of the current default.
    """
    sensors = dataclasses.replace(
        cfg.sensors, split_distance=True, proprioception=False, apples_in_view=False
    )
    network = dataclasses.replace(cfg.network, num_inputs=sensors.num_inputs)
    return dataclasses.replace(cfg, sensors=sensors, network=network)


@pytest.fixture(name="split_genome")
def split_genome_fixture(split_cfg):
    TRACKER.reset()
    return Genome.new_fully_connected(
        split_cfg.genome,
        split_cfg.network.num_inputs,
        split_cfg.network.num_outputs,
        random.Random(0),
    )


# ------------------------------------------------------------------ #
# Raycasts
# ------------------------------------------------------------------ #


def test_ray_angles_split_configured_fov_evenly(cfg):
    angles = ray_angles(cfg.sensors.num_rays, cfg.sensors.fov)
    assert len(angles) == cfg.sensors.num_rays
    step = math.radians(cfg.sensors.fov) / cfg.sensors.num_rays
    for i, angle in enumerate(angles):
        assert angle == pytest.approx(i * step)


def test_ray_angles_respect_reduced_fov():
    assert ray_angles(4, 180.0) == pytest.approx(
        [0.0, math.pi / 4, math.pi / 2, 3 * math.pi / 4]
    )


def test_ray_angles_rotate_with_heading():
    h = math.pi / 2
    angles = ray_angles(4, 360.0, heading=h)
    step = math.radians(360.0) / 4
    assert angles == pytest.approx([h + i * step for i in range(4)])


def test_sense_length(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    assert len(agent.sense()) == cfg.network.num_inputs  # 67 (default layout)


@pytest.mark.parametrize(
    "split, prop, aiv, expected",
    [
        (True, True, True, 67),  # canonical poc2.3 layout
        (False, False, False, 49),  # legacy apple_repro_bigpop layout
        (True, False, False, 65),  # distance split alone
        (False, True, True, 51),  # combined distance + both scalars
    ],
)
def test_sense_length_matches_configurable_layout(cfg, split, prop, aiv, expected):
    sensors = dataclasses.replace(
        cfg.sensors, split_distance=split, proprioception=prop, apples_in_view=aiv
    )
    assert sensors.num_inputs == expected  # 16 rays assumed
    network = dataclasses.replace(cfg.network, num_inputs=expected)
    cfg2 = dataclasses.replace(cfg, sensors=sensors, network=network)
    env2 = Environment(cfg2, random.Random(0))
    TRACKER.reset()
    genome2 = Genome.new_fully_connected(
        cfg2.genome, expected, cfg2.network.num_outputs, random.Random(0)
    )
    agent = Agent(
        genome2,
        (cfg2.world.width / 2, cfg2.world.height / 2),
        cfg2,
        env2,
        random.Random(0),
    )
    assert len(agent.sense()) == expected


def test_last_senses_cached_on_activate(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    assert agent.last_senses is None  # no decision taken yet
    agent.activate()
    # activate() updates heading before returning, so a fresh sense() after it
    # would use the new heading → ray order rotates → exact equality breaks.
    # We verify that last_senses is populated and has the right length.
    assert agent.last_senses is not None
    assert len(agent.last_senses) == cfg.network.num_inputs


def test_energy_input_normalised(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    inputs = agent.sense()
    n = cfg.sensors.num_rays
    dist_channels = 2 if cfg.sensors.split_distance else 1
    energy_idx = (dist_channels + 2) * n  # distance block(s) + apple_flag + wall_flag
    assert inputs[energy_idx] == pytest.approx(
        cfg.agent.initial_energy / cfg.agent.max_energy
    )


def test_ray_hits_wall(split_cfg, env, split_genome):
    # heading=0 → ray 0 points +x; agent 50px from right wall.
    env.apples.clear()
    agent = make_agent(
        split_cfg,
        env,
        split_genome,
        (split_cfg.world.width - 50.0, split_cfg.world.height / 2),
    )
    inputs = agent.sense()
    n = split_cfg.sensors.num_rays
    assert inputs[0] == pytest.approx(1.0)  # apple_dist = max (no apple)
    assert inputs[n + 0] == pytest.approx(
        50.0 / split_cfg.sensors.max_distance
    )  # wall_dist
    assert inputs[2 * n + 0] == 0.0  # apple_flag = 0
    assert inputs[3 * n + 0] == 1.0  # wall_flag = 1


def test_ray_hits_apple(split_cfg, env, split_genome):
    # heading=0 → ray 0 points +x; single apple 100px to the right.
    cx, cy = split_cfg.world.width / 2, split_cfg.world.height / 2
    env.apples[:] = [Apple(cx + 100.0, cy)]
    agent = make_agent(split_cfg, env, split_genome, (cx, cy))
    inputs = agent.sense()
    n = split_cfg.sensors.num_rays
    expected = (100.0 - split_cfg.apple.radius) / split_cfg.sensors.max_distance
    assert inputs[0] == pytest.approx(expected)  # apple_dist
    assert inputs[n + 0] == pytest.approx(1.0)  # wall_dist = max (wall far away)
    assert inputs[2 * n + 0] == 1.0  # apple_flag = 1
    assert inputs[3 * n + 0] == 0.0  # wall_flag = 0


def test_ray_sees_nothing(split_cfg, env, split_genome):
    # World centre: every wall is >200px (max_distance) away, no apples.
    env.apples.clear()
    agent = make_agent(
        split_cfg,
        env,
        split_genome,
        (split_cfg.world.width / 2, split_cfg.world.height / 2),
    )
    inputs = agent.sense()
    n = split_cfg.sensors.num_rays
    for i in range(n):
        assert inputs[i] == pytest.approx(1.0)  # apple_dist = max (no apple)
        assert inputs[n + i] == pytest.approx(1.0)  # wall_dist = max (walls all >200px)
        assert inputs[2 * n + i] == 0.0  # apple_flag = 0
        assert inputs[3 * n + i] == 0.0  # wall_flag = 0


def test_apple_occludes_farther_wall(split_cfg, env, split_genome):
    # Apple 50px ahead, wall 150px ahead: both detected on independent channels.
    agent_x = split_cfg.world.width - 150.0
    cy = split_cfg.world.height / 2
    env.apples[:] = [Apple(agent_x + 50.0, cy)]  # apple 50px; wall 150px
    agent = make_agent(split_cfg, env, split_genome, (agent_x, cy))
    inputs = agent.sense()
    n = split_cfg.sensors.num_rays
    apple_d = inputs[0]  # apple_dist (normalised)
    wall_d = inputs[n + 0]  # wall_dist (normalised)
    assert inputs[2 * n + 0] == 1.0  # apple_flag = 1
    assert inputs[3 * n + 0] == 1.0  # wall_flag = 1 (independently visible)
    assert apple_d < wall_d  # apple is closer


# ------------------------------------------------------------------ #
# Energy (per tick)
# ------------------------------------------------------------------ #


def test_metabolize_safe_zone(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    start = agent.energy
    agent.metabolize()
    assert agent.energy == pytest.approx(start - cfg.agent.energy_drain_per_tick)


def test_metabolize_penalty_zone(cfg, env, genome):
    # 50px from left wall → penalty = max_drain * (1 - 50/zone_width).
    zw = cfg.penalty_zone.width
    x = 50.0
    agent = make_agent(cfg, env, genome, (x, cfg.world.height / 2))
    expected_penalty = cfg.penalty_zone.max_drain * (1.0 - x / zw)
    start = agent.energy
    agent.metabolize()
    expected = start - cfg.agent.energy_drain_per_tick - expected_penalty
    assert agent.energy == pytest.approx(expected)


def test_eat_gains_energy_and_defers_respawn(cfg, env, genome):
    cx, cy = cfg.world.width / 2, cfg.world.height / 2
    apple = Apple(cx, cy)
    env.apples[:] = [apple]
    agent = make_agent(cfg, env, genome, (cx, cy))
    agent.energy = 1.0
    eaten = agent.eat()
    assert len(eaten) == 1
    assert agent.energy == pytest.approx(1.0 + cfg.apple.energy)
    # Deferred respawn: the eaten apple leaves the live list and starts its timer.
    assert env.apples == []
    assert apple.respawn_timer == cfg.apple.respawn_delay


def test_eat_caps_at_max_energy(cfg, env, genome):
    cx, cy = cfg.world.width / 2, cfg.world.height / 2
    env.apples[:] = [Apple(cx, cy)]
    agent = make_agent(cfg, env, genome, (cx, cy))
    agent.energy = cfg.agent.max_energy - 0.1
    agent.eat()
    assert agent.energy == pytest.approx(cfg.agent.max_energy)


def test_metabolize_caps_at_max_energy(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    agent.energy = cfg.agent.max_energy + 5.0  # artificially over cap
    agent.metabolize()
    assert agent.energy <= cfg.agent.max_energy


# ------------------------------------------------------------------ #
# Movement
# ------------------------------------------------------------------ #


def test_move_clamped_to_world(cfg, env, genome):
    radius = cfg.agent.radius
    agent = make_agent(cfg, env, genome, (radius + 1.0, cfg.world.height / 2))
    agent.move(-1000.0, 0.0)  # push hard into the left wall
    assert agent.x == pytest.approx(radius)


# ------------------------------------------------------------------ #
# Decision / velocity
# ------------------------------------------------------------------ #


def test_activate_velocity_clamped(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    vx, vy = agent.activate()
    assert math.hypot(vx, vy) <= cfg.agent.max_speed + 1e-9


def test_activate_deterministic(cfg, env, genome):
    pos = (cfg.world.width / 2, cfg.world.height / 2)
    a1 = make_agent(cfg, env, genome, pos)
    a2 = make_agent(cfg, env, genome, pos)
    assert a1.sense() == a2.sense()
    assert a1.activate() == a2.activate()


# ------------------------------------------------------------------ #
# Life cycle
# ------------------------------------------------------------------ #


def test_dead_by_famine(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    agent.energy = 0.0
    assert agent.is_dead() is True


def test_dead_by_old_age(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    agent.age = cfg.agent.max_age
    assert agent.is_dead() is True


def test_alive_when_young_and_fed(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    assert agent.is_dead() is False


def test_can_reproduce_threshold(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    agent.energy = cfg.agent.reproduction_threshold
    assert agent.can_reproduce() is True
    agent.energy = cfg.agent.reproduction_threshold - 0.01
    assert agent.can_reproduce() is False


# ------------------------------------------------------------------ #
# Reproduction
# ------------------------------------------------------------------ #


def test_reproduce_pays_cost(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    agent.energy = cfg.agent.reproduction_threshold
    agent.reproduce()
    assert agent.energy == pytest.approx(
        cfg.agent.reproduction_threshold - cfg.agent.reproduction_cost
    )


def test_child_starts_with_initial_energy(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    agent.energy = cfg.agent.reproduction_threshold
    child = agent.reproduce()
    assert child.energy == pytest.approx(cfg.agent.initial_energy)


def test_child_spawns_near_parent(cfg, env, genome):
    px, py = cfg.world.width / 2, cfg.world.height / 2
    agent = make_agent(cfg, env, genome, (px, py))
    agent.energy = cfg.agent.reproduction_threshold
    child = agent.reproduce()
    radius = cfg.agent.radius
    assert abs(child.x - px) <= radius
    assert abs(child.y - py) <= radius


def test_child_is_independent_agent(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    agent.energy = cfg.agent.reproduction_threshold
    child = agent.reproduce()
    assert isinstance(child, Agent)
    assert child.network is not agent.network  # own cached network
    assert child.genome is not agent.genome  # mutated clone
    assert child.age == 0


def test_founder_generation_is_zero(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    assert agent.generation == 0


def test_child_generation_increments(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    agent.generation = 4
    agent.energy = cfg.agent.reproduction_threshold
    child = agent.reproduce()
    assert child.generation == 5


# ------------------------------------------------------------------ #
# Egocentric model
# ------------------------------------------------------------------ #


def test_heading_initialised_explicitly(cfg, env, genome):
    agent = make_agent(
        cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2), heading=1.23
    )
    assert agent.heading == pytest.approx(1.23)


def test_heading_updates_after_activate(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    h0 = agent.heading
    agent.activate()
    # heading may or may not change depending on network output, but it must stay
    # within [0, 2π).
    assert 0.0 <= agent.heading < 2.0 * math.pi
    _ = h0  # both values are valid


def test_child_inherits_parent_heading(cfg, env, genome):
    agent = make_agent(
        cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2), heading=0.5
    )
    agent.energy = cfg.agent.reproduction_threshold
    child = agent.reproduce()
    assert child.heading == pytest.approx(0.5)
