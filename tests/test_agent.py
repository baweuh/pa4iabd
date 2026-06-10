"""Tests for Agent (Phase 5): raycasts, energy, life cycle, reproduction."""

# pylint: disable=missing-function-docstring,protected-access,redefined-outer-name

from __future__ import annotations

import math
import random

import pytest

from src.agent import _TYPE_APPLE, _TYPE_NOTHING, _TYPE_WALL, Agent
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


def make_agent(cfg, env, genome, position, seed=0):
    return Agent(genome, position, cfg, env, random.Random(seed))


# ------------------------------------------------------------------ #
# Raycasts
# ------------------------------------------------------------------ #


def test_sense_length(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    assert len(agent.sense()) == cfg.network.num_inputs  # 33


def test_energy_input_normalised(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    inputs = agent.sense()
    assert inputs[-1] == pytest.approx(cfg.agent.initial_energy / cfg.agent.max_energy)


def test_ray_hits_wall(cfg, env, genome):
    # Place the agent 50px from the right wall; ray 0 points +x straight at it.
    env.apples.clear()
    agent = make_agent(cfg, env, genome, (cfg.world.width - 50.0, cfg.world.height / 2))
    inputs = agent.sense()
    num_rays = cfg.sensors.num_rays
    assert inputs[0] == pytest.approx(50.0 / cfg.sensors.max_distance)  # distance
    assert inputs[num_rays + 0] == _TYPE_WALL  # type block


def test_ray_hits_apple(cfg, env, genome):
    # Single apple 100px along +x (ray 0); near surface at 100 - apple.radius.
    cx, cy = cfg.world.width / 2, cfg.world.height / 2
    env.apples[:] = [Apple(cx + 100.0, cy)]
    agent = make_agent(cfg, env, genome, (cx, cy))
    inputs = agent.sense()
    num_rays = cfg.sensors.num_rays
    expected = (100.0 - cfg.apple.radius) / cfg.sensors.max_distance
    assert inputs[0] == pytest.approx(expected)
    assert inputs[num_rays + 0] == _TYPE_APPLE


def test_ray_sees_nothing(cfg, env, genome):
    # World centre: every wall is >200px (max_distance) away, no apples.
    env.apples.clear()
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    inputs = agent.sense()
    num_rays = cfg.sensors.num_rays
    for i in range(num_rays):
        assert inputs[i] == pytest.approx(1.0)  # max normalised distance
        assert inputs[num_rays + i] == _TYPE_NOTHING


def test_apple_occludes_farther_wall(cfg, env, genome):
    # Apple closer than the wall along +x must win the first-hit.
    agent_x = cfg.world.width - 150.0
    cy = cfg.world.height / 2
    env.apples[:] = [Apple(agent_x + 50.0, cy)]  # apple 50px; wall 150px
    agent = make_agent(cfg, env, genome, (agent_x, cy))
    inputs = agent.sense()
    assert inputs[cfg.sensors.num_rays + 0] == _TYPE_APPLE


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


def test_eat_gains_energy_and_respawns(cfg, env, genome):
    cx, cy = cfg.world.width / 2, cfg.world.height / 2
    env.apples[:] = [Apple(cx, cy)]
    agent = make_agent(cfg, env, genome, (cx, cy))
    agent.energy = 1.0
    eaten = agent.eat()
    assert eaten == 1
    assert agent.energy == pytest.approx(1.0 + cfg.apple.energy)
    assert (env.apples[0].x, env.apples[0].y) != (cx, cy)  # respawned elsewhere


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


# ------------------------------------------------------------------ #
# update() helper
# ------------------------------------------------------------------ #


def test_update_advances_one_tick(cfg, env, genome):
    agent = make_agent(cfg, env, genome, (cfg.world.width / 2, cfg.world.height / 2))
    start_energy = agent.energy
    agent.update()
    assert agent.age == 1
    assert agent.energy <= start_energy  # metabolic cost paid (no apple eaten)
