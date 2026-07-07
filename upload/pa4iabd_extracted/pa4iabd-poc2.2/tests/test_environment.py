"""Tests for Environment and Apple (Phase 4)."""

# pylint: disable=missing-function-docstring,protected-access

from __future__ import annotations

import random

import pytest

from src.config import SimConfig
from src.environment import Environment


@pytest.fixture(name="cfg")
def cfg_fixture():
    return SimConfig.from_yaml("config/default.yaml")


@pytest.fixture(name="env")
def env_fixture(cfg):
    return Environment(cfg, random.Random(42))


# ------------------------------------------------------------------ #
# Apple count and placement
# ------------------------------------------------------------------ #


def test_apple_count(cfg, env):
    assert len(env.apples) == cfg.apple.count


def test_apples_full_body_in_safe_zone(cfg, env):
    zw = cfg.penalty_zone.width
    r = cfg.apple.radius
    for apple in env.apples:
        dist = env.dist_to_wall(apple.x, apple.y)
        assert dist >= zw + r, (
            f"Apple at ({apple.x:.1f}, {apple.y:.1f}) too close to wall: "
            f"dist={dist:.2f} < zw+r={zw+r}"
        )


def test_determinism(cfg):
    env_a = Environment(cfg, random.Random(42))
    env_b = Environment(cfg, random.Random(42))
    for a, b in zip(env_a.apples, env_b.apples):
        assert a.x == b.x and a.y == b.y


# ------------------------------------------------------------------ #
# Respawn
# ------------------------------------------------------------------ #


def test_respawn_changes_position(cfg, env):
    apple = env.apples[0]
    old_pos = (apple.x, apple.y)
    env.respawn(apple, random.Random(99))
    assert (apple.x, apple.y) != old_pos


def test_respawn_stays_in_safe_zone(cfg, env):
    zw = cfg.penalty_zone.width
    r = cfg.apple.radius
    apple = env.apples[0]
    env.respawn(apple, random.Random(7))
    assert env.dist_to_wall(apple.x, apple.y) >= zw + r


# ------------------------------------------------------------------ #
# Deferred respawn (mark_eaten + tick_respawns)
# ------------------------------------------------------------------ #


def test_mark_eaten_removes_from_live_and_starts_timer(cfg, env):
    apple = env.apples[0]
    start = len(env.apples)
    env.mark_eaten(apple)
    assert apple not in env.apples
    assert len(env.apples) == start - 1
    assert apple.respawn_timer == cfg.apple.respawn_delay


def test_tick_respawns_returns_apple_after_delay(cfg, env):
    apple = env.apples[0]
    env.mark_eaten(apple)
    rng = random.Random(7)
    # Not yet due for respawn_delay - 1 ticks.
    for _ in range(cfg.apple.respawn_delay - 1):
        env.tick_respawns(rng)
        assert apple not in env.apples
    # The final tick brings it back live.
    env.tick_respawns(rng)
    assert apple in env.apples
    assert apple.respawn_timer == 0


def test_respawn_returns_to_safe_zone(cfg, env):
    zw = cfg.penalty_zone.width
    r = cfg.apple.radius
    apple = env.apples[0]
    env.mark_eaten(apple)
    rng = random.Random(11)
    for _ in range(cfg.apple.respawn_delay):
        env.tick_respawns(rng)
    assert apple in env.apples
    assert env.dist_to_wall(apple.x, apple.y) >= zw + r


def test_tick_respawns_noop_without_pending(cfg, env):
    before = len(env.apples)
    env.tick_respawns(random.Random(1))
    assert len(env.apples) == before


# ------------------------------------------------------------------ #
# Penalty field
# ------------------------------------------------------------------ #


def test_penalty_at_wall(cfg, env):
    # (0, H/2): dist_to_wall == 0 → penalty == max_drain
    y_mid = cfg.world.height / 2.0
    assert env.penalty_at(0.0, y_mid) == pytest.approx(cfg.penalty_zone.max_drain)


def test_penalty_gradient_midpoint(cfg, env):
    zw = cfg.penalty_zone.width
    # Place point at dist == zw/2 from left wall
    y_mid = cfg.world.height / 2.0
    x = zw / 2.0
    expected = cfg.penalty_zone.max_drain * 0.5
    assert env.penalty_at(x, y_mid) == pytest.approx(expected)


def test_penalty_at_boundary(cfg, env):
    zw = cfg.penalty_zone.width
    y_mid = cfg.world.height / 2.0
    # Exactly at zone_width → 0
    assert env.penalty_at(zw, y_mid) == pytest.approx(0.0)


def test_penalty_zero_in_safe_zone(cfg, env):
    # World centre is deep in safe zone
    cx = cfg.world.width / 2.0
    cy = cfg.world.height / 2.0
    assert env.penalty_at(cx, cy) == 0.0


def test_penalty_strictly_decreasing(cfg, env):
    y_mid = cfg.world.height / 2.0
    zw = cfg.penalty_zone.width
    distances = [0.0, zw * 0.25, zw * 0.5, zw * 0.75]
    penalties = [env.penalty_at(d, y_mid) for d in distances]
    for i in range(len(penalties) - 1):
        assert (
            penalties[i] > penalties[i + 1]
        ), f"penalty not strictly decreasing at dist={distances[i]:.1f}"


# ------------------------------------------------------------------ #
# in_safe_zone helper
# ------------------------------------------------------------------ #


def test_in_safe_zone_center(cfg, env):
    cx = cfg.world.width / 2.0
    cy = cfg.world.height / 2.0
    assert env.in_safe_zone(cx, cy) is True


def test_not_in_safe_zone_near_wall(cfg, env):
    zw = cfg.penalty_zone.width
    # One pixel inside the penalty zone
    y_mid = cfg.world.height / 2.0
    assert env.in_safe_zone(zw - 1.0, y_mid) is False
